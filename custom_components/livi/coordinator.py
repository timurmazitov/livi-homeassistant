"""Координатор данных Livi: один опрос на все объекты каждые SCAN_INTERVAL."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import LiviApiError, LiviAuthError, LiviClient

_LOGGER = logging.getLogger(__name__)


@dataclass
class LiviObject:
    """Один объект Livi (дом/квартира) + его устройства."""

    console_id: str
    name: str
    raw: dict[str, Any]
    devices: list[dict[str, Any]] = field(default_factory=list)


class LiviCoordinator(DataUpdateCoordinator[dict[str, LiviObject]]):
    """Опрашивает ListObjects + ListDevices для каждого объекта."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: LiviClient,
        scan_interval: int = 30,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name="Livi",
            update_interval=timedelta(seconds=max(10, scan_interval)),
        )
        self.client = client

    async def _async_update_data(self) -> dict[str, LiviObject]:
        try:
            objects_raw = await self.client.async_get_objects()
        except LiviAuthError as err:
            raise UpdateFailed(f"Авторизация Livi: {err}") from err
        except LiviApiError as err:
            raise UpdateFailed(f"Сеть Livi: {err}") from err

        result: dict[str, LiviObject] = {}
        for obj_raw in objects_raw:
            console_id = str(obj_raw.get("IdConsole") or obj_raw.get("Id") or "")
            if not console_id:
                continue
            obj = LiviObject(
                console_id=console_id,
                name=obj_raw.get("Name") or console_id,
                raw=obj_raw,
            )
            try:
                obj.devices = await self.client.async_get_devices(console_id)
            except LiviApiError as err:
                # один объект недоступен — не роняем остальные
                _LOGGER.warning("Объект %s: ошибка списка устройств: %s", obj.name, err)
            result[console_id] = obj
        return result
