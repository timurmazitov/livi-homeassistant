"""Binary sensors: тревоги датчиков Livi + утечка у крана LiviWc."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN, device_kind, is_alarm_now, leak_active
from .coordinator import LiviCoordinator, LiviObject
from .entity import LiviEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Binary sensors: тревожные датчики + утечка крана LiviWc."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: LiviCoordinator = data["coordinator"]

    entities: list[BinarySensorEntity] = []
    for obj in coordinator.data.values():
        for device in obj.devices:
            kind = device_kind(device.get("TypeSensor"))
            if kind.style == "alarm":
                entities.append(LiviAlarmBinarySensor(coordinator, obj, device, kind))
            elif kind.style == "water_crane":
                entities.append(LiviWcLeakBinarySensor(coordinator, obj, device, kind))
    async_add_entities(entities)


def _common_attrs(device: dict[str, Any]) -> dict[str, Any]:
    """Общие атрибуты состояния устройства."""
    sensor = device.get("Sensor")
    return {
        "type_sensor": device.get("TypeSensor"),
        "signal_level": device.get("SignalLevel"),
        "connected": device.get("IsConnected"),
        "power_supplied": device.get("IsPowerSupplied"),
        "sensor_value": sensor.get("Value") if isinstance(sensor, dict) else None,
        "active_events": [
            ev.get("Type") if isinstance(ev, dict) else str(ev)
            for ev in (device.get("Events") or [])
        ],
    }


class LiviAlarmBinarySensor(LiviEntity, BinarySensorEntity):
    """«Тревога» датчика: Sensor.Value == 'True' (движение/открытие/дым...)."""

    def __init__(self, coordinator, obj: LiviObject, device: dict[str, Any], kind) -> None:
        super().__init__(coordinator, obj, device, kind, f"alarm_{kind.entity_suffix}")
        self._attr_name = "Тревога"
        self._update_state(device)

    def _update_state(self, device: dict[str, Any] | None) -> None:
        self._attr_available = device is not None
        if device is None:
            self._attr_is_on = None
            self._attr_extra_state_attributes = {}
            return
        self._attr_is_on = is_alarm_now(device, self._kind)
        self._attr_extra_state_attributes = _common_attrs(device)


class LiviWcLeakBinarySensor(LiviEntity, BinarySensorEntity):
    """«Утечка» крана LiviWc: любой канал LiquidLeakSensor.Value == 'True'."""

    def __init__(self, coordinator, obj: LiviObject, device: dict[str, Any], kind) -> None:
        super().__init__(coordinator, obj, device, kind, "leak")
        self._attr_name = "Утечка"
        self._update_state(device)

    def _update_state(self, device: dict[str, Any] | None) -> None:
        self._attr_available = device is not None
        if device is None:
            self._attr_is_on = None
            self._attr_extra_state_attributes = {}
            return
        self._attr_is_on = leak_active(device)
        self._attr_extra_state_attributes = _common_attrs(device)
