"""HTTP-Client für klassengeld.app (Login per Formular, danach Dashboard lesen)."""

from __future__ import annotations

import logging

import aiohttp

from .const import BASE_URL, DASHBOARD_URL, LOGIN_URL
from .parser import Student, is_login_page, page_lines, parse_dashboard, parse_login_form

_LOGGER = logging.getLogger(__name__)
TIMEOUT = aiohttp.ClientTimeout(total=30)


class KlassengeldError(Exception):
    """Basisklasse."""


class KlassengeldAuthError(KlassengeldError):
    """Zugangsdaten falsch oder Login nicht möglich."""


class KlassengeldConnectionError(KlassengeldError):
    """Server nicht erreichbar oder unerwartete Antwort."""


class KlassengeldClient:
    """Meldet sich an und liest das Dashboard. Nur lesende Zugriffe außer dem Login."""

    def __init__(
        self, session: aiohttp.ClientSession, username: str, password: str
    ) -> None:
        self._session = session
        self._username = username
        self._password = password
        self.last_lines: list[str] = []

    async def async_login(self) -> None:
        try:
            async with self._session.get(LOGIN_URL, timeout=TIMEOUT) as resp:
                html = await resp.text()
                page_url = str(resp.url)

            if not is_login_page(html):
                return  # Sitzung ist noch gültig

            try:
                action, hidden, user_field, pw_field = parse_login_form(html, page_url)
            except ValueError as err:
                raise KlassengeldConnectionError(f"Login-Formular nicht lesbar: {err}") from err

            payload = {**hidden, user_field: self._username, pw_field: self._password}
            async with self._session.post(
                action,
                data=payload,
                headers={"Referer": page_url, "Origin": BASE_URL},
                timeout=TIMEOUT,
            ) as resp:
                if resp.status == 419:
                    raise KlassengeldConnectionError(
                        "Login abgelehnt (419, CSRF-Token/Sitzung abgelaufen)"
                    )
                if resp.status >= 400:
                    raise KlassengeldConnectionError(f"Login-Antwort HTTP {resp.status}")
                result = await resp.text()

            if is_login_page(result):
                raise KlassengeldAuthError("Anmeldung fehlgeschlagen")
        except (aiohttp.ClientError, TimeoutError) as err:
            raise KlassengeldConnectionError(str(err)) from err

    async def _fetch_dashboard(self) -> str:
        async with self._session.get(DASHBOARD_URL, timeout=TIMEOUT) as resp:
            if resp.status >= 500:
                raise KlassengeldConnectionError(f"Serverfehler {resp.status}")
            return await resp.text()

    async def async_get_data(self) -> list[Student]:
        try:
            html = await self._fetch_dashboard()
            if is_login_page(html):  # Sitzung abgelaufen -> neu anmelden
                _LOGGER.debug("Sitzung abgelaufen, melde neu an")
                await self.async_login()
                html = await self._fetch_dashboard()
                if is_login_page(html):
                    raise KlassengeldAuthError("Dashboard nach Login nicht erreichbar")
        except (aiohttp.ClientError, TimeoutError) as err:
            raise KlassengeldConnectionError(str(err)) from err

        self.last_lines = page_lines(html)
        students = parse_dashboard(html)
        if not students:
            raise KlassengeldConnectionError(
                "Keine Daten im Dashboard erkannt (Layout geändert?). "
                "Diagnose-Download der Integration enthält den Seitentext."
            )
        for s in students:
            _LOGGER.debug(
                "Gelesen: %s, Kontostand=%s, %d Zahlungen (%d offen)",
                s.name,
                s.balance,
                len(s.payments),
                len(s.open_payments),
            )
            if s.balance is None:
                _LOGGER.warning(
                    "Kontostand für %s nicht gefunden – Seitenlayout geändert? "
                    "Bitte Diagnose-Download der Integration anhängen.",
                    s.name,
                )
            for p in s.payments:
                if p.status == "unknown" or p.due is None or p.amount is None:
                    _LOGGER.warning(
                        "Zahlung '%s' unvollständig gelesen (Status=%s, Frist=%s, Betrag=%s)",
                        p.title,
                        p.status,
                        p.due,
                        p.amount,
                    )
        return students
