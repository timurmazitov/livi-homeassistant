# Livi для Home Assistant

Кастомная интеграция Home Assistant для охранно-умной системы **Livi** (livicom.ru).
v1 — read-only: список объектов, хабов и датчиков.

## Возможности (v1)

- Авторизация по логину (телефон `+79061234567`) и паролю — тот же API, что у приложения Livi
- Сенсор **«Охрана»** на каждый объект: `disarmed` / `armed` / `armed_home` / `alarm` / `alarm_delay` / `disarming` / `error`
- Хаб → устройство в HA (online/offline/no_channel, GSM-сигнал, питание)
- Датчики → устройства, привязанные к хабу:
  - **binary_sensor «Тревога»**: движение, открытие, протечка, дым, вибрация, газ, CO, разбитие стекла
  - **sensor «Состояние»**: температура/влажность (у LIVI_TS/HTS), реле, брелоки, клавиатуры и пр.
- Опрос раз в 30 сек (настраивается), автопродление токена

## Установка (тестовый стенд)

```bash
docker compose up -d          # HA на http://localhost:8123
```

Затем: Настройки → Устройства и службы → Добавить интеграцию → **Livi** → логин/пароль.

Файлы:
- `custom_components/livi/` — сама интеграция (монтируется в контейнер read-only)
- `ha-config/` — конфиг тестового HA (`/config`)
- `scripts/test_livi_api.py` — живой тест API без HA

## Тест API вручную

```bash
export LIVI_LOGIN="+79001234567"
export LIVI_PASSWORD="пароль"
.venv/bin/python scripts/test_livi_api.py
```

Скрипт логинится, скачивает объекты и устройства, сохраняет ответы в `fixtures/`
(токен не сохраняется). Используется как источник правды для парсеров.

## Добытые знания об API (из APK Livi 2.1.7)

- PROD: `https://api.livicom.ru:11201/api/v3/` (STAGE: `testapi.livicom.ru:11401`)
- `POST /Token` (form-urlencoded: `username`, `password`, `grant_type=password`)
  → `{access_token, token_type, expires_in, .issued, .expires}` — ASP.NET Identity
- Заголовки приложения: `Client-Type: mobile-app`, `Client-Platform: android`,
  `Client-Version: 2.1.7`, `Client-Build: 374`, `Client-OS-Version`, `Client-Device`
- Далее: `Authorization: Bearer <token>`
- `GET Object/ListObjects` → `[{Id, IdConsole, Name, ProtectionMode, ProtectionStatus, ConsoleState, ...}]`
- `GET ConsoleState/ListDevices?idConsole=...` → `{Devices: [{Id, Name, SerialNumber, TypeSensor, Events[], IsConnected, SignalLevel, IsPowerSupplied, Sensor{...}}]}`
- Режимы охраны: `IS_DISARMED, DISARMING, PROTECTION, ARM, ARM_APP, ARM_PART, PARTIAL_PROTECTION, ERROR_PROTECTION`
- Статусы: `NORMA, ALARM, ALARM_DELAY`
- Реального времени нет (push в приложение) → polling; локального API управления нет
  (`http://192.168.1.1` в приложении — только веб-настройка WiFi хаба)

Декомпилированные исходники APK лежат в `work/` (git-ignored) — пригодятся для v2.

## Roadmap

- v2: `alarm_control_panel` (постановка/снятие), реле/сирена как `switch`
- v3: события в реальном времени (исследование push-протокола), архив событий, графики

## Структура

```
custom_components/livi/
├── __init__.py        # setup/unload entry
├── api.py             # клиент API (aiohttp, Bearer, автопродление токена)
├── config_flow.py     # UI-настройка + интервал опроса
├── const.py           # маппинги ApiTypeSensor → HA
├── coordinator.py     # DataUpdateCoordinator (30 c)
├── entity.py          # базовая сущность (DeviceInfo, паттерн _attr_*)
├── binary_sensor.py   # тревоги датчиков
├── sensor.py          # охрана/хабы/климат
├── manifest.json
└── strings.json
```
