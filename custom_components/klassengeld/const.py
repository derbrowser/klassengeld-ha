"""Konstanten der Klassengeld-Integration."""

from datetime import timedelta

DOMAIN = "klassengeld"
BASE_URL = "https://klassengeld.app"
LOGIN_URL = f"{BASE_URL}/login"
DASHBOARD_URL = f"{BASE_URL}/dashboard"
SCAN_INTERVAL = timedelta(minutes=30)
CURRENCY = "EUR"
