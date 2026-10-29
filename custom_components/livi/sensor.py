"""Sensors: охрана объекта, хаб (ConsoleState), реле/сирены, климат, краны."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    UnitOfTemperature,
    UnitOfVolume,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import (
    DOMAIN,
    HUB_MODELS,
    PROTECTION_MODE_RU,
    PROTECTION_STATUS_RU,
    DeviceKind,
    device_kind,
    extract_humidity,
    extract_temperature,
    sensor_value,
)
from .coordinator import LiviCoordinator, LiviObject
from .entity import LiviEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Сенсоры: на объект — «Охрана» и хаб; на устройства — по стилю."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: LiviCoordinator = data["coordinator"]

    entities: list[SensorEntity] = []
    for obj in coordinator.data.values():
        hub_kind = _hub_kind(obj)
        entities.append(LiviProtectionSensor(coordinator, obj, hub_kind))
        entities.append(LiviHubSensor(coordinator, obj, hub_kind))
        for device in obj.devices:
            kind = device_kind(device.get("TypeSensor"))
            style = kind.style
            if style == "switch":
                entities.append(LiviValueSensor(coordinator, obj, device, kind))
            elif style == "temp":
                entities.append(LiviTempSensor(coordinator, obj, device, kind))
            elif style == "temp_hum":
                entities.append(LiviTempSensor(coordinator, obj, device, kind))
                entities.append(LiviHumiditySensor(coordinator, obj, device, kind))
            elif style == "water_crane":
                entities.extend(_crane_entities(coordinator, obj, device, kind))
            elif style == "online":
                entities.append(LiviOnlineSensor(coordinator, obj, device, kind))
            # style == "alarm" представлен в binary_sensor.py
    async_add_entities(entities)


def _hub_kind(obj: LiviObject) -> DeviceKind:
    """DeviceKind хаба по ConsoleState.Type / TypeConsole."""
    console_type = obj.raw.get("TypeConsole") or (obj.raw.get("ConsoleState") or {}).get("Type")
    model = HUB_MODELS.get(str(console_type), "Livi Hub")
    return DeviceKind(model, "hub", "hub")


def _crane_entities(
    coordinator: LiviCoordinator, obj: LiviObject, device: dict[str, Any], kind: DeviceKind
) -> list[SensorEntity]:
    """Кран LiviWc: 2 клапана + 2 счётчика воды."""
    entities: list[SensorEntity] = []
    sensor = device.get("Sensor") or {}
    for n in (1, 2):
        valve = sensor.get(f"ControlValve{n}")
        if isinstance(valve, dict):
            entities.append(LiviWcValveSensor(coordinator, obj, device, kind, n, valve))
        meter = sensor.get(f"SensorMeasurement{n}")
        if isinstance(meter, dict):
            entities.append(LiviWcMeterSensor(coordinator, obj, device, kind, n, meter))
    return entities


class LiviProtectionSensor(LiviEntity, SensorEntity):
    """Сенсор «Охрана» объекта: disarmed / armed / armed_home / alarm..."""

    def __init__(self, coordinator: LiviCoordinator, obj: LiviObject, hub_kind: DeviceKind) -> None:
        super().__init__(coordinator, obj, None, hub_kind, "protection")
        self._attr_name = "Охрана"
        self._update_state(None)

    def _update_state(self, device: dict[str, Any] | None) -> None:
        obj = self._current_object()
        self._attr_available = obj is not None
        if obj is None:
            self._attr_native_value = None
            self._attr_extra_state_attributes = {}
            return
        mode = obj.raw.get("ProtectionMode")
        status = obj.raw.get("ProtectionStatus")
        mode_str = str(mode).upper() if mode else ""
        status_str = str(status).upper() if status else ""
        if status_str in PROTECTION_STATUS_RU:
            value: str = PROTECTION_STATUS_RU[status_str]
        else:
            value = PROTECTION_MODE_RU.get(mode_str, "unknown")
        self._attr_native_value = value
        self._attr_extra_state_attributes = {
            "console_id": obj.console_id,
            "protection_mode": mode,
            "protection_status": status,
            "status_change_date": obj.raw.get("ProtectionStatusChangeDate"),
            "address": obj.raw.get("Address"),
        }


class LiviHubSensor(LiviEntity, SensorEntity):
    """Состояние хаба: online/offline + GSM, питание, прошивка, баланс SIM."""

    _attr_icon = "mdi:hub"

    def __init__(self, coordinator, obj: LiviObject, hub_kind: DeviceKind) -> None:
        super().__init__(coordinator, obj, None, hub_kind, "hub")
        self._attr_name = "Хаб"
        self._update_state(None)

    def _hub_state(self) -> dict[str, Any]:
        obj = self._current_object()
        if obj is None:
            return {}
        state = obj.raw.get("ConsoleState")
        return state if isinstance(state, dict) else {}

    def _update_state(self, device: dict[str, Any] | None) -> None:
        state = self._hub_state()
        obj = self._current_object()
        self._attr_available = obj is not None
        if not state:
            self._attr_native_value = None
            self._attr_extra_state_attributes = {}
            return
        self._attr_native_value = "online" if state.get("IsConnected") else "offline"
        self._attr_extra_state_attributes = {
            "console_type": state.get("Type"),
            "firmware_version": state.get("FirmwareVersion"),
            "gsm_status": state.get("StatusGsm"),
            "gsm_signal_level": state.get("GsmSignalLevel"),
            "network_standard": state.get("MobileNetworkStandard"),
            "power_source": state.get("PowerSource"),
            "power_supply_ok": state.get("IsPowerSupplyOk"),
            "temperature": state.get("Temperature"),
            "sim_balance": state.get("BalanceSim"),
            "sim_phone": state.get("PhoneNumber"),
        }


class LiviValueSensor(LiviEntity, SensorEntity):
    """Реле/сирена/термостат: значение Sensor.Value (On/Off)."""

    def __init__(self, coordinator, obj: LiviObject, device: dict[str, Any], kind) -> None:
        super().__init__(coordinator, obj, device, kind, kind.entity_suffix)
        self._attr_name = "Состояние"
        self._update_state(device)

    def _update_state(self, device: dict[str, Any] | None) -> None:
        self._attr_available = device is not None
        if device is None:
            self._attr_native_value = None
            self._attr_extra_state_attributes = {}
            return
        value = sensor_value(device)
        if value is not None:
            self._attr_native_value = value.lower()
        else:
            self._attr_native_value = "online" if device.get("IsConnected") else "offline"
        self._attr_extra_state_attributes = {
            "type_sensor": device.get("TypeSensor"),
            "signal_level": device.get("SignalLevel"),
            "connected": device.get("IsConnected"),
            "power_supplied": device.get("IsPowerSupplied"),
        }


class LiviTempSensor(LiviEntity, SensorEntity):
    """Температура из Sensor.Channels (канал 3)."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, obj: LiviObject, device: dict[str, Any], kind) -> None:
        super().__init__(coordinator, obj, device, kind, "temperature")
        self._attr_name = "Температура"
        self._update_state(device)

    def _update_state(self, device: dict[str, Any] | None) -> None:
        self._attr_available = device is not None
        if device is None:
            self._attr_native_value = None
            self._attr_extra_state_attributes = {}
            return
        self._attr_native_value = extract_temperature(device)
        channels = (device.get("Sensor") or {}).get("Channels") or []
        self._attr_extra_state_attributes = {
            "signal_level": device.get("SignalLevel"),
            "connected": device.get("IsConnected"),
            "channels": [
                {"number": ch.get("Number"), "name": ch.get("Name"), "value": ch.get("Value")}
                for ch in channels
                if isinstance(ch, dict)
            ],
        }


class LiviHumiditySensor(LiviEntity, SensorEntity):
    """Влажность из Sensor.Channels (канал 4, LiviHTS)."""

    _attr_device_class = SensorDeviceClass.HUMIDITY
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, obj: LiviObject, device: dict[str, Any], kind) -> None:
        super().__init__(coordinator, obj, device, kind, "humidity")
        self._attr_name = "Влажность"
        self._update_state(device)

    def _update_state(self, device: dict[str, Any] | None) -> None:
        self._attr_available = device is not None
        if device is None:
            self._attr_native_value = None
            self._attr_extra_state_attributes = {}
            return
        self._attr_native_value = extract_humidity(device)
        self._attr_extra_state_attributes = {
            "signal_level": device.get("SignalLevel"),
            "connected": device.get("IsConnected"),
        }


class LiviOnlineSensor(LiviEntity, SensorEntity):
    """Прочие устройства (брелок, RFID, клавиатура): online/offline."""

    def __init__(self, coordinator, obj: LiviObject, device: dict[str, Any], kind) -> None:
        super().__init__(coordinator, obj, device, kind, kind.entity_suffix)
        self._attr_name = "Состояние"
        self._update_state(device)

    def _update_state(self, device: dict[str, Any] | None) -> None:
        self._attr_available = device is not None
        if device is None:
            self._attr_native_value = None
            self._attr_extra_state_attributes = {}
            return
        self._attr_native_value = "online" if device.get("IsConnected") else "offline"
        self._attr_extra_state_attributes = {
            "type_sensor": device.get("TypeSensor"),
            "signal_level": device.get("SignalLevel"),
            "power_supplied": device.get("IsPowerSupplied"),
        }


class LiviWcValveSensor(LiviEntity, SensorEntity):
    """Клапан крана LiviWc: On/Off."""

    _attr_icon = "mdi:valve"

    def __init__(
        self,
        coordinator,
        obj: LiviObject,
        device: dict[str, Any],
        kind,
        number: int,
        valve: dict[str, Any],
    ) -> None:
        self._valve_number = number
        super().__init__(coordinator, obj, device, kind, f"valve{number}")
        self._valve = valve
        self._attr_name = valve.get("Name") or f"Клапан {number}"
        self._update_state(device)

    def _update_state(self, device: dict[str, Any] | None) -> None:
        self._attr_available = device is not None
        if device is None:
            self._attr_native_value = None
            self._attr_extra_state_attributes = {}
            return
        valve = ((device.get("Sensor") or {}).get(f"ControlValve{self._valve_number}")) or {}
        value = valve.get("Value")
        self._attr_native_value = str(value).lower() if value is not None else None
        self._attr_extra_state_attributes = {
            "signal_level": device.get("SignalLevel"),
            "connected": device.get("IsConnected"),
        }


class LiviWcMeterSensor(LiviEntity, SensorEntity):
    """Счётчик воды крана LiviWc: накопленное значение (m³)."""

    _attr_device_class = SensorDeviceClass.WATER
    _attr_native_unit_of_measurement = UnitOfVolume.CUBIC_METERS
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_icon = "mdi:counter"

    def __init__(
        self,
        coordinator,
        obj: LiviObject,
        device: dict[str, Any],
        kind,
        number: int,
        meter: dict[str, Any],
    ) -> None:
        self._meter_number = number
        super().__init__(coordinator, obj, device, kind, f"meter{number}")
        self._attr_name = meter.get("Name") or f"Счётчик {number}"
        self._update_state(device)

    def _update_state(self, device: dict[str, Any] | None) -> None:
        self._attr_available = device is not None
        if device is None:
            self._attr_native_value = None
            self._attr_extra_state_attributes = {}
            return
        meter = ((device.get("Sensor") or {}).get(f"SensorMeasurement{self._meter_number}")) or {}
        value = meter.get("Value")
        self._attr_native_value = float(value) if isinstance(value, (int, float)) else None
        self._attr_extra_state_attributes = {
            "month_value": meter.get("AccMonthValue"),
            "pulse_value": meter.get("PulseValue"),
            "measurement_type": meter.get("TypeMesurringChannel"),
            "connected": device.get("IsConnected"),
        }
