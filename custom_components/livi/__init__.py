"""Интеграция Livi (Livicom) для Home Assistant."""
from __future__ import annotations

import logging
from typing import Any

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr

from .api import LiviApiError, LiviAuthError, LiviClient
from .const import (
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    HUB_MODELS,
    PLATFORMS,
)
from .coordinator import LiviCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Настройка интеграции из config entry."""
    hass.data.setdefault(DOMAIN, {})

    session = aiohttp.ClientSession()
    client = LiviClient(
        username=entry.data["username"],
        password=entry.data["password"],
        session=session,
    )
    coordinator = LiviCoordinator(
        hass,
        client,
        scan_interval=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
    )

    try:
        await coordinator.async_config_entry_first_refresh()
    except ConfigEntryNotReady:
        await session.close()
        raise

    hass.data[DOMAIN][entry.entry_id] = {
        "client": client,
        "coordinator": coordinator,
        "session": session,
    }

    # Регистрируем устройства хабов ДО платформ: дочерние устройства ссылаются
    # на них через via_device_id (registry id), как в ядре HA (enphase_envoy).
    device_registry = dr.async_get(hass)
    for obj in coordinator.data.values():
        console_type = obj.raw.get("TypeConsole") or (obj.raw.get("ConsoleState") or {}).get(
            "Type"
        )
        device_registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, f"{obj.console_id}:{obj.console_id}")},
            manufacturer="Livicom",
            model=HUB_MODELS.get(str(console_type), "Livi Hub"),
            name=obj.name,
        )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Выгрузка интеграции."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        data: dict[str, Any] = hass.data[DOMAIN].pop(entry.entry_id)
        await data["session"].close()
    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Перезагрузка при изменении опций."""
    await hass.config_entries.async_reload(entry.entry_id)


__all__ = ["LiviApiError", "LiviAuthError"]
