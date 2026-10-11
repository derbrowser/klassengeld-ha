"""Parser für das Klassengeld-Dashboard (reine Python-Logik, ohne Home Assistant).

Der Parser arbeitet bewusst textbasiert: Er liest den sichtbaren Text der Seite
zeilenweise und erkennt Muster wie "Kontostand", "Projekt ...", "Frist:",
"Betrag:" und den Status ("zu bezahlen" / "bezahlt"). Das ist robuster gegen
Änderungen an CSS-Klassen als feste Selektoren.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup

AMOUNT_RE = re.compile(r"(?P<sign>[-−–])?\s*(?P<num>\d{1,3}(?:\.\d{3})*,\d{2}|\d+,\d{2})\s*€")
STUDENT_RE = re.compile(
    r"^(?P<name>.+?)\s*\((?P<cls>[^)]+)\)\s*[-–]\s*(?P<school>.+)$"
)
PROJECT_RE = re.compile(
    r"^\d+\.\s*Projekt\s*[\"„“]?(?P<title>.*?)[\"“”]?\s*$", re.IGNORECASE
)
DATE_RE = re.compile(r"(?P<d>\d{1,2}\.\d{1,2}\.\d{4})")
SALDO_RE = re.compile(r"show_saldo_info\((\d+)\)")  # onclick von "Alle Transaktionen anzeigen"
TABLEDATA_RE = re.compile(r"var\s+tabledata_\w+\s*=\s*")
PLAIN_NUM_RE = re.compile(r"^[-+−–]?\s*\d+(?:[.,]\d+)?$")
IBAN_RE = re.compile(r"\b([A-Z]{2}\d{2})[A-Z0-9]{11,30}\b")
OPEN_HINTS = (
    "zu bezahlen",
    "offen",
    "nicht bezahlt",
    "überfällig",
    "unbezahlt",
    "teilweise",
)


def _amount_only(line: str) -> bool:
    """True, wenn die Zeile nur aus einem Betrag besteht ('210,00 €')."""
    return AMOUNT_RE.fullmatch(line.strip()) is not None


def _find_date(lines: list[str], start: int) -> date | None:
    """Datum in Zeile start oder den nächsten drei Zeilen suchen.

    Auf der echten Seite steht die Frist auf mehreren Zeilen:
    'Frist:' / '{20261008}' / '08.10.2026'.
    """
    for j in range(start, min(start + 4, len(lines))):
        if j > start and PROJECT_RE.match(lines[j]):
            return None  # nächstes Projekt beginnt, keine Frist gefunden
        if m := DATE_RE.search(lines[j]):
            try:
                return datetime.strptime(m.group("d"), "%d.%m.%Y").date()
            except ValueError:
                return None
    return None


@dataclass
class Payment:
    """Eine Zahlungsaufforderung (Projekt)."""

    title: str
    due: date | None = None
    amount: float | None = None
    status: str = "unknown"  # "open" | "paid" | "unknown"
    status_text: str = ""


@dataclass
class Transaction:
    """Eine Buchung aus "Alle Transaktionen anzeigen" (Schülerkonto)."""

    date: date | None = None
    kind: str = ""  # z. B. "Banküberweisung", "Transfer in Projekt"
    description: str = ""
    amount: float | None = None  # positiv = Einzahlung, negativ = Abbuchung


@dataclass
class Reserved:
    """Zeile aus "Reservierte Beträge" (z. B. "nicht zugeordnete Summe")."""

    label: str
    amount: float | None = None


@dataclass
class Student:
    """Ein Kind mit Kontostand, Projekten (Zahlungsaufforderungen) und Transaktionen."""

    name: str
    school_class: str | None = None
    school: str | None = None
    balance: float | None = None
    payments: list[Payment] = field(default_factory=list)
    account_id: str | None = None  # ID für /ajax/saldo_account/<id>
    transactions: list[Transaction] = field(default_factory=list)
    reserved: list[Reserved] = field(default_factory=list)

    @property
    def open_payments(self) -> list[Payment]:
        return [p for p in self.payments if p.status == "open"]

    @property
    def paid_payments(self) -> list[Payment]:
        return [p for p in self.payments if p.status == "paid"]

    @property
    def unassigned_amount(self) -> float | None:
        """"nicht zugeordnete Summe" aus den reservierten Beträgen."""
        for r in self.reserved:
            if "nicht zugeordnet" in r.label.lower():
                return r.amount
        return None


def parse_amount(text: str) -> float | None:
    """'1.234,56 €' -> 1234.56, '-12,00 €' -> -12.0."""
    m = AMOUNT_RE.search(text)
    if not m:
        return None
    value = float(m.group("num").replace(".", "").replace(",", "."))
    return -value if m.group("sign") else value


def is_login_page(html: str) -> bool:
    """True, wenn die Seite ein Passwortfeld enthält (= Login-Formular)."""
    return BeautifulSoup(html, "html.parser").select_one("input[type=password]") is not None


def parse_login_form(html: str, page_url: str) -> tuple[str, dict[str, str], str, str]:
    """Liest das Login-Formular aus.

    Rückgabe: (Ziel-URL, versteckte Felder wie _token, Feldname Benutzer, Feldname Passwort)
    """
    soup = BeautifulSoup(html, "html.parser")
    pw_input = soup.select_one("input[type=password]")
    if pw_input is None:
        raise ValueError("Kein Passwortfeld gefunden")
    form = pw_input.find_parent("form")
    if form is None:
        raise ValueError("Passwortfeld liegt in keinem <form>")

    hidden = {
        i["name"]: i.get("value", "")
        for i in form.select("input[type=hidden][name]")
    }
    # Laravel: Token ggf. aus dem <meta>-Tag nehmen
    if "_token" not in hidden:
        meta = soup.find("meta", attrs={"name": "csrf-token"})
        if meta and meta.get("content"):
            hidden["_token"] = meta["content"]

    user_input = form.select_one(
        "input[type=text][name], input[type=email][name], input:not([type])[name]"
    )
    if user_input is None:
        raise ValueError("Kein Benutzerfeld gefunden")

    action = urljoin(page_url, form.get("action") or page_url)
    return action, hidden, user_input["name"], pw_input["name"]


def _page_lines(html: str) -> list[str]:
    """Sichtbaren Text in saubere Zeilen zerlegen."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "option"]):
        tag.decompose()
    raw = [re.sub(r"\s+", " ", ln).strip() for ln in soup.get_text("\n").splitlines()]
    lines: list[str] = []
    for ln in raw:
        if not ln:
            continue
        # Zeilen, die mit "- " beginnen, gehören zur vorherigen (Name - Schule)
        if lines and re.match(r"^[-–]\s+\S", ln) and STUDENT_RE.match(lines[-1] + " " + ln):
            lines[-1] = lines[-1] + " " + ln
        else:
            lines.append(ln)
    return lines


def page_lines(html: str) -> list[str]:
    """Öffentlich für Diagnose-Zwecke."""
    return _page_lines(html)


def mask_iban(text: str) -> str:
    """IBANs kürzen ('DE83…'), damit sie nicht in Attributen oder Diagnosen landen."""
    return IBAN_RE.sub(r"\1…", text)


def mask_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Rohzeilen für die Diagnose: IBANs maskiert."""
    return json.loads(mask_iban(json.dumps(rows, ensure_ascii=False)))


def _plain(value: Any) -> str:
    """HTML-Fragment -> reiner Text."""
    text = BeautifulSoup(str(value or ""), "html.parser").get_text(" ")
    return re.sub(r"\s+", " ", text).strip()


def _amount_value(text: str) -> float | None:
    """'-160.00' / '50,00' / '50,00 €' -> float."""
    t = text.strip()
    if PLAIN_NUM_RE.match(t):
        num = float(t.lstrip("+-−– ").replace(",", "."))
        return -num if t[0] in "-−–" else num
    return parse_amount(t)


def extract_tabledata(html: str) -> list[dict[str, Any]]:
    """Zeilen der DevExtreme-Tabelle ('var tabledata_… = [...]') aus dem Skript lesen."""
    m = TABLEDATA_RE.search(html)
    if m is None:
        return []
    try:
        data, _ = json.JSONDecoder().raw_decode(html, m.end())
    except ValueError:
        return []
    return [r for r in data if isinstance(r, dict)] if isinstance(data, list) else []


def parse_transactions(html: str) -> list[Transaction]:
    """Antwort von /ajax/saldo_account/<id> -> Buchungen (neueste zuerst, wie auf der Seite).

    Spalten der Tabelle: 0 Richtungs-Icon, 1 Datum, 2 Betrag (mit Vorzeichen),
    3 Art, 4 Beschreibung, 5 Schüler.
    """
    result: list[Transaction] = []
    for row in extract_tabledata(html):
        def cell(i: int) -> str:
            return _plain(row.get(f"fieldtxt{i}") or row.get(f"field{i}"))

        m = DATE_RE.search(cell(1))
        try:
            d = datetime.strptime(m.group("d"), "%d.%m.%Y").date() if m else None
        except ValueError:
            d = None
        result.append(
            Transaction(
                date=d,
                kind=cell(3),
                description=mask_iban(cell(4)),
                amount=_amount_value(cell(2)),
            )
        )
    return result


def parse_reserved(html: str) -> list[Reserved]:
    """Tabelle unter "Reservierte Beträge" (inkl. "nicht zugeordnete Summe")."""
    soup = BeautifulSoup(html, "html.parser")
    heading = next(
        (s for s in soup.find_all("strong") if "reservierte" in s.get_text().lower()),
        None,
    )
    table = heading.find_next("table") if heading else None
    if table is None:
        return []
    result: list[Reserved] = []
    for tr in table.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) >= 2:
            result.append(
                Reserved(
                    label=tds[0].get_text(" ", strip=True),
                    amount=parse_amount(tds[1].get_text(" ", strip=True)),
                )
            )
    return result


def parse_dashboard(html: str) -> list[Student]:
    """Dashboard-HTML -> Liste von Kindern mit Kontostand und Zahlungen."""
    lines = _page_lines(html)
    students: list[Student] = []
    student: Student | None = None
    payment: Payment | None = None
    saldo_ids = SALDO_RE.findall(html)  # in Seitenreihenfolge, eine pro Kind
    saldo_seen = 0

    def ensure_student() -> Student:
        nonlocal student
        if student is None:
            student = Student(name="Unbekannt")
            students.append(student)
        return student

    i = 0
    while i < len(lines):
        line = lines[i]

        if m := STUDENT_RE.match(line):
            student = Student(
                name=m.group("name").strip(),
                school_class=m.group("cls").strip(),
                school=m.group("school").strip(),
            )
            students.append(student)
            payment = None

        elif line.lower().startswith("kontostand"):
            bal = parse_amount(line)
            # Auf der echten Seite steht der Betrag VOR dem Label ('210,00 €' / 'Kontostand')
            if bal is None and i > 0 and _amount_only(lines[i - 1]):
                bal = parse_amount(lines[i - 1])
            if bal is None and i + 1 < len(lines) and _amount_only(lines[i + 1]):
                bal = parse_amount(lines[i + 1])
                i += 1
            ensure_student().balance = bal

        elif m := PROJECT_RE.match(line):
            payment = Payment(title=m.group("title").strip())
            ensure_student().payments.append(payment)

        elif line.lower().startswith("alle transaktionen"):
            if saldo_seen < len(saldo_ids):
                ensure_student().account_id = saldo_ids[saldo_seen]
            saldo_seen += 1

        elif payment is not None:
            if line.lower().startswith("frist"):
                payment.due = _find_date(lines, i)
            elif line.lower().startswith("betrag"):
                amount = parse_amount(line)
                if amount is None and i + 1 < len(lines) and _amount_only(lines[i + 1]):
                    amount = parse_amount(lines[i + 1])
                payment.amount = amount
            elif not payment.status_text and len(line) < 40:
                low = line.lower()
                if any(h in low for h in OPEN_HINTS):
                    payment.status, payment.status_text = "open", line
                elif low.startswith("bezahlt"):
                    payment.status, payment.status_text = "paid", line
        i += 1

    # Fallback: Button-Text nicht erkannt, aber genau eine ID je Kind vorhanden
    if saldo_seen == 0 and len(saldo_ids) == len(students):
        for s, account_id in zip(students, saldo_ids, strict=True):
            s.account_id = account_id

    return students
