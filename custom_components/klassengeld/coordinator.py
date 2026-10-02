"""DataUpdateCoordinator für Klassengeld."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import slugify

from .api import KlassengeldAuthError, KlassengeldClient, KlassengeldConnectionError
from .const import DOMAIN, SCAN_INTERVAL
from .parser import Student

_LOGGER = logging.getLogger(__name__)


class KlassengeldCoordinator(DataUpdateCoordinator[dict[str, Student]]):
    """Holt alle 30 Minuten das Dashboard. Schlüssel = slugify(Name des Kindes)."""

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, client: KlassengeldClient
    ) -> None:
        super().__init__(
            hass, _LOGGER, config_entry=entry, name=DOMAIN, update_interval=SCAN_INTERVAL
        )
        self.client = client

    async def _async_update_data(self) -> dict[str, Student]:
        try:
            students = await self.client.async_get_data()
        except KlassengeldAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except KlassengeldConnectionError as err:
            raise UpdateFailed(str(err)) from err
        return {slugify(s.name): s for s in students}
