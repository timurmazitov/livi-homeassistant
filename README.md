# Livi для Home Assistant

[![HACS](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![Validate](https://github.com/timurmazitov/livi-homeassistant/actions/workflows/validate.yml/badge.svg)](https://github.com/timurmazitov/livi-homeassistant/actions/workflows/validate.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

Кастомная интеграция Home Assistant для охранно-умной системы **Livi** (livicom.ru).
v1 — read-only: список объектов, хабов и датчиков.

## Возможности (v1)

- Авторизация по логину (телефон `+79001234567`) и паролю — тот же API, что у приложения Livi
- Сенсор **«Охрана»** на каждый объект: `disarmed` / `armed` / `armed_home` / `alarm` / `alarm_delay` / `disarming` / `error`
- Хаб → устройство в HA (online/offline/no_channel, GSM-сигнал, питание, прошивка, баланс SIM)
- Датчики → устройства, привязанные к хабу:
  - **binary_sensor «Тревога»**: движение, открытие, протечка, дым, вибрация, газ, CO, разбитие стекла
  - **sensor «Состояние»**: температура/влажность (LiviTs/LiviHTS), реле, сирены, брелоки, клавиатуры
  - **Краны воды (LiviWc)**: 2 клапана + 2 счётчика воды (m³) + binary_sensor «Утечка»
- Опрос раз в 30 сек (настраивается), автопродление токена

## Установка через HACS

1. Установите [HACS](https://hacs.xyz/docs/setup/download), если ещё нет
2. **HACS → ⋮ → Настроить → Пользовательские репозитории**
3. URL: `https://github.com/timurmazitov/livi-homeassistant`, категория: **Integration**
4. Найдите **Livi (Livicom)** в HACS → нажмите **Скачать**
5. Перезапустите Home Assistant
6. Настройки → Устройства и службы → Добавить интеграцию → **Livi**

Или одной кнопкой (после установки HACS):

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=timurmazitov&repo=livi-homeassistant&category=integration)

## Установка вручную

Скопируйте `custom_components/livi/` в `config/custom_components/livi/` вашего HA
и перезапустите HA. Либо поднимите тестовый стенд Docker-ом:

```bash
docker compose up -d          # HA на http://localhost:8123
```

Затем: Настройки → Устройства и службы → Добавить интеграцию → **Livi** → логин/пароль.

## Тест API вручную (без HA)

```bash
export LIVI_LOGIN="+79001234567"
export LIVI_PASSWORD="пароль"
.venv/bin/python scripts/test_livi_api.py
```

Скрипт логинится, скачивает объекты и устройства, сохраняет ответы в `fixtures/`
(токен не сохраняется). Используется как источник правды для парсеров.

## Добытые знания об API (из APK Livi 2.1.7)

Полный справочник — в [livi-api.md](livi-api.md). Кратко:

- PROD: `https://api.livicom.ru:11201/api/v3/`
- `POST /Token` (form-urlencoded: `username` — телефон без плюса, `password`, `grant_type=password`)
  → `{access_token, token_type, expires_in, .issued, .expires}` — ASP.NET Identity
- Заголовки приложения: `Client-Type: mobile-app`, `Client-Platform: android`,
  `Client-Version`, `Client-Build`, `Client-OS-Version`, `Client-Device`
- Далее: `Authorization: Bearer <token>`
- `GET Object/ListObjects` + `GET ConsoleState/ListDevices?idConsole=...`
- Реального времени нет (push в приложение — только триггер) → polling;
  локального API управления нет (`http://192.168.1.1` — только веб-настройка WiFi хаба)

## Roadmap

- v2: `alarm_control_panel` (постановка/снятие через `Favorites/RunCmd`), реле/сирена/краны как `switch`
- v3: архив событий (`EventsArchive/*`), графики (`statistics/devices/*`)

## Структура

```text
custom_components/livi/
├── __init__.py        # setup/unload entry, регистрация хаба в device registry
├── api.py             # клиент API (aiohttp, Bearer, автопродление токена)
├── config_flow.py     # UI-настройка + интервал опроса
├── const.py           # маппинги TypeSensor → HA
├── coordinator.py     # DataUpdateCoordinator (30 c)
├── entity.py          # базовая сущность (DeviceInfo, паттерн _attr_*)
├── binary_sensor.py   # тревоги датчиков, утечка крана
├── sensor.py          # охрана/хабы/климат/краны
├── brand/icon.png     # иконка для HACS/HA
├── manifest.json
└── strings.json
```
