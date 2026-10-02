"""Parser für das Klassengeld-Dashboard (reine Python-Logik, ohne Home Assistant).

Der Parser arbeitet bewusst textbasiert: Er liest den sichtbaren Text der Seite
zeilenweise und erkennt Muster wie "Kontostand", "Projekt ...", "Frist:",
"Betrag:" und den Status ("zu bezahlen" / "bezahlt"). Das ist robuster gegen
Änderungen an CSS-Klassen als feste Selektoren.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup

AMOUNT_RE = re.compile(r"(?P<sign>[-−–])?\s*(?P<num>\d{1,3}(?:\.\d{3})*,\d{2}|\d+,\d{2})\s*€")
STUDENT_RE = re.compile(
    r"^(?P<name>.+?)\s*\((?P<cls>[^)]+)\)\s*[-–]\s*(?P<school>.+)$"
)
PROJECT_RE = re.compile(
    r"^\d+\.\s*Projekt\s*[\"„“]?(?P<title>.*?)[\"“”]?\s*$", re.IGNORECASE
)
DUE_RE = re.compile(r"Frist:\s*(?P<d>\d{1,2}\.\d{1,2}\.\d{4})", re.IGNORECASE)
OPEN_HINTS = ("zu bezahlen", "offen", "nicht bezahlt", "überfällig", "unbezahlt")


@dataclass
class Payment:
    """Eine Zahlungsaufforderung (Projekt)."""

    title: str
    due: date | None = None
    amount: float | None = None
    status: str = "unknown"  # "open" | "paid" | "unknown"
    status_text: str = ""


@dataclass
class Student:
    """Ein Kind mit Kontostand und Zahlungsaufforderungen."""

    name: str
    school_class: str | None = None
    school: str | None = None
    balance: float | None = None
    payments: list[Payment] = field(default_factory=list)

    @property
    def open_payments(self) -> list[Payment]:
        return [p for p in self.payments if p.status == "open"]


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


def parse_dashboard(html: str) -> list[Student]:
    """Dashboard-HTML -> Liste von Kindern mit Kontostand und Zahlungen."""
    lines = _page_lines(html)
    students: list[Student] = []
    student: Student | None = None
    payment: Payment | None = None

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
            if bal is None and i + 1 < len(lines):
                bal = parse_amount(lines[i + 1])
                if bal is not None:
                    i += 1
            ensure_student().balance = bal

        elif m := PROJECT_RE.match(line):
            payment = Payment(title=m.group("title").strip())
            ensure_student().payments.append(payment)

        elif payment is not None:
            if m := DUE_RE.search(line):
                try:
                    payment.due = datetime.strptime(m.group("d"), "%d.%m.%Y").date()
                except ValueError:
                    pass
            elif line.lower().startswith("betrag"):
                payment.amount = parse_amount(line)
            elif not payment.status_text and len(line) < 40:
                low = line.lower()
                if any(h in low for h in OPEN_HINTS):
                    payment.status, payment.status_text = "open", line
                elif low.startswith("bezahlt"):
                    payment.status, payment.status_text = "paid", line
        i += 1

    return students
