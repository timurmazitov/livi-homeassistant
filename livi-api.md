# Livi API — справочник (восстановлен из APK Livi 2.1.7-374 + живая проверка)

Источник: статическая декомпиляция `Livi-2.1.7-374-local-google-release.apk` (jadx),
подтверждено живыми запросами (fixtures/). Пути — относительно базового URL, если не указано иное.
Декомпилированные исходники: `work/src-out/sources/ru/livicom/` (git-ignored).

> ⚠️ Неофициальный API. Сервер может измениться без уведомления. Для v2 (управление)
> каждый эндпоинт перед продакшеном проверять тест-скриптом.

---

## 1. Серверы

Из `data/Constants.java` (класс `Constants.Server`):

| Среда | URL |
| --- | --- |
| **PROD** | `https://api.livicom.ru:11201/api/v3/` |
| STAGE | `https://testapi.livicom.ru:11201/api/v3/` |
| TEST | `https://api.livicom.ru:11401/api/v3/` |
| DEV | `https://testapi.livicom.ru:11401/api/v3/` |

Статус сервера (веб-страница): `https://livi.ru/support/status-servera`

Прочие хосты в APK: Firebase (FCM/Analytics/Crashlytics), RuStore push (`auth.vkpns.rustore.ru`),
AppTracer (`sdk-api.apptracer.ru`), Mail.ru трекер. Для интеграции не нужны.

**Важно про `/Token`:** в Retrofit путь объявлен как `@POST("/Token")` — со слэша,
поэтому резолвится от корня хоста: `https://api.livicom.ru:11201/Token`,
а НЕ `.../api/v3/Token` (там 404 — проверено живьём).

---

## 2. Авторизация

Классический ASP.NET Identity (OWIN). Источник: `AccountApi.login`, `ApiAuthResponse`.

### POST https://api.livicom.ru:11201/Token

`Content-Type: application/x-www-form-urlencoded`

| Поле | Значение |
| --- | --- |
| `username` | **телефон без плюса**: `79001234567` (проверено; `+79001234567` → 400) |
| `password` | пароль |
| `grant_type` | `password` |

Ответ 200 (реальный пример из живого теста):

```json
{
  "access_token": "…длинная строка…",
  "token_type": "bearer",
  "expires_in": 31535999,
  "userName": "79001234567",
  ".issued": "Thu, 29 Oct 2026 02:51:35 GMT",
  ".expires": "Fri, 29 Oct 2027 02:51:35 GMT"
}
```

- Токен живёт **~1 год** (`expires_in=31535999`).
- Ошибка: HTTP 400, тело содержит `invalid_grant` (ASP.NET standard).
- Все авторизованные запросы: заголовок `Authorization: Bearer <access_token>`
  (источник: `AuthInterceptor$intercept$1`).
- При 401 приложение перелогинивается; в интеграции — то же (сброс токена → новый /Token).

### Обязательные заголовки приложения (`ClientInfoInterceptor`, `ClientInfoHeaders`)

Шлются на **каждый** запрос (в т.ч. /Token):

| Заголовок | Значение (из живого приложения) |
| --- | --- |
| `Client-Type` | `mobile-app` |
| `Client-Platform` | `android` |
| `Client-Version` | `2.1.7` (BuildConfig.VERSION) |
| `Client-Build` | `374` (BuildConfig.BUILD) |
| `Client-OS-Version` | версия Android, напр. `14` |
| `Client-Device` | модель устройства, напр. `Pixel 8` |
| `Accept-Language` | `ru` |

(интеграция шлёт `Client-Device: HomeAssistant-Bridge` — сервер принимает).
Таймауты OkHttp приложения: connect 15s, read 60s, write 50s.

### Регистрация / SMS (для справки)

- `POST Account/SendCodeSms` → код на телефон (регистрация/восстановление)
- `POST Account/ConfirmPhoneNumber` (form: `PhoneNumber`, `Code`) → `ApiSetPasswordTokenResponse`
- `POST Account/Register` (form: `PhoneNumber`, `Email`, `AcceptAgreement`)
- `POST Account/SetPassword` (form: `PasswordToken`?, `NewPassword`, `ConfirmPassword`)

---

## 3. Объекты (объект = дом/квартира с хабом)

Источник: `ObjectsApi`, `ApiProtectionObject`, живой fixtures/objects.json.

### GET `Object/ListObjects`

→ **список** объектов (json array). Поля элемента (живой пример):

```json
{
  "TypeConsole": "SmartHub4G",          // тип хаба (строка PascalCase!)
  "Id": 56886,                           // числовой id объекта
  "IdConsole": "20000001",               // id хаба — ключ для всех device-запросов
  "Name": "Дом",
  "City": {...}, "Address": "…",
  "IsOwner": true, "Role": "Owner",
  "PerimeterProtectionModeAvailable": false,
  "IsBlocked": false, "IsConfirmed": true,
  "IsNotificationsEnabled": true,
  "ProtectionStatus": "Norma",           // Norma | ALARM | ALARM_DELAY
  "ProtectionMode": "Protection",        // см. §5
  "ProtectionStatusChangeDate": "2026-10-28T12:23:23.0990000Z",
  "UnreadNotificationsCount": 197,
  "Owner": {...}, "ActiveEvents": [...], // активные события (ApiEventArch)
  "ConsoleState": { ... },               // состояние хаба, см. §4
  "Image": {...}, "Favorites": [...], "Widgets": [...],
  "PermissionControl": {...}, "StatusGroups": [...]
}
```

### Остальное (Object/*)

| Метод | Путь | Параметры | Заметки |
| --- | --- | --- | --- |
| GET | `Object/Object` | `?idConsole=` | один объект → `ApiProtectionObject` |
| PUT | `Object/Object` | form-map (`Name`, `Address`…) | сохранить свойства |
| DELETE | `Object/Object` | `?idConsole=` | удалить объект |
| GET | `Object/GetSettingsObject` | `?idConsole=` | настройки объекта |
| POST | `Object/AddObject` | form: `Name`, `IdConsole`, `Address`, `Timezone` | привязка нового хаба |
| GET | `Object/CheckConsole` | `?idConsole=` | проверка серийника хаба |
| GET | `Object/ReadyAddObject` | `?idConsole=` | завершение привязки |
| POST | `Object/ConfirmObject` / `CancelObject` | `?idConsole=` | подтверждение/отмена |
| POST | `Object/ReplaceConsole` | `?idConsole=`, `?idNewConsole=` | замена хаба |
| GET | `Object/CheckStateReplaceConsole` | `?idConsole=`, `?idNewConsole=` | статус замены |
| DELETE | `UsersObject/User` (HTTP w/ body) | body `LeaveObjectRequest` | выйти из объекта |
| GET | `SettingsApp/Firmware` | `?consoleId=` | статус прошивки хаба |
| POST | `ConsoleState/RunUpdateFirmware` | `?idConsole=` | запустить обновление |
| PUT | `Object/SetDefaultAvatar` | `?idConsole=` | аватар по умолчанию |
| POST | `Object/UploadImage` | multipart 2 части | фото объекта |

---

## 4. Устройства и состояние хаба

Источник: `ConsoleApi`, `ApiDevice`, `ApiListDeviceResponse`, живые fixtures.

### GET `ConsoleState/ListDevices?idConsole=20000001`

Ответ: `{"Devices": [...], "ProtectionPermissionControl": {...}}`

Поля устройства (живой пример):

```json
{
  "ConsoleId": "20000001",
  "Name": "Входная дверь",
  "SerialNumber": "13000001",
  "SignalLevel": 9,                 // 1..9 (конвертированный RSSI)
  "RawSignalLevel": -74,            // дБм
  "TypeSensor": "LiviCs",           // ⚠️ PascalCase, не enum!
  "IsConnected": true,
  "IsBodyClosed": true,
  "IsPowerSupplied": true,
  "IsPowerReserveSupplied": true,
  "Events": [],                     // активные события (обычно пуст; см. §6)
  "IsRunningSignalLevelTest": false,
  "RepeaterData": null,
  "FirmwareVersion": "3.2.1",
  "CaseType": "Classic", "CaseColor": "White",
  "Sensor": { ... }                 // типо-зависимое состояние, см. ниже
}
```

### `Sensor` по типам (живые данные):

| TypeSensor | Sensor содержит | Семантика Value |
| --- | --- | --- |
| `LiviCs`, `LiviMs`, `LiviFs`, `LiviFs2` (+IsCleaningNeeded), `LiviLs`, `LiviVs`... | `Value: "False"/"True"` + флаги охраны (`IsExcludeFromGuard`, `IsAutoGuardEnabled`, `IsAttachedToDoor`, `IsRefersToPerimeter`, `IsAlarmDelayEnabled`, `IsAlwaysGuardEnabled`, `ReactToAnimals` у Ms) | **тревога**: "True" = тревога |
| `LiviTs`, `LiviHTS` | `Channels: [{Value: 19.4, IsExternal, IsEnabled, IsFaulty, Number, Name}]` | канал 3 = температура °C, канал 4 = влажность % (у HTS), канал 4 `IsExternal:true` = внешний сенсор |
| `LiviRelay`, `LiviRelay1224` | `Value: "Off"/"On"`, `IsTemperatureProtection`, `IsPowerProtection`, `IsThermostat`, `ThermostatSetting` | состояние реле |
| `LiviSiren` | `Value: "Off"/"On"`, `IsSecurityConfirmationAllowed`, `EntryExitDelaySound`, `Duration`, `Volume` | состояние сирены |
| `LiviWc` (кран) | `ControlValve1/2: {Value: "Off", Name, Number}`, `SensorMeasurement1/2: {PulseValue, AccMonthValue, Value, TypeMesurringChannel: "ColdWaterMeasurement"/"HotWaterMeasurement", Name}`, `LiquidLeakSensor: {Channels: [{Value: "False", Number, Name}]}` | клапаны Off/On; счётчики в m³; утечка по каналам |

⚠️ У LiviWc поле `TypeMesurringChannel` — именно с опечаткой «Mesurring» (живой JSON).

### GET `ConsoleState/StateConsole?idConsole=…` → состояние хаба

(то же самое лежит в `ConsoleState` объекта из ListObjects). Живой пример:

```json
{
  "Type": "SmartHub4G", "IdConsole": "20000001", "IdOwner": "79001234567",
  "CaseType": "Classic", "CaseColor": "White",
  "Temperature": 0.0,                 // температура внутри хаба
  "PowerSource": "Main",              // Main | …
  "IsConnected": true, "IsPowerSupplyOk": true, "IsCaseOk": true,
  "FirmwareVersion": "2.7", "FirmwareStatus": "LatestInstalled",
  "StatusEthernet": "NoCommunicationChannel",
  "StatusGsm": "Connected", "GsmSignalLevel": 10, "MobileNetworkStandard": "4G",
  "StatusWiFi": "NotConfigured", "WiFiSignalLevel": 0, "WiFiSSID": "",
  "PhoneNumber": "79001234568",       // SIM хаба
  "BalanceSim": 123.45, "IsBalanceSimValid": true,
  "Timezone": "GMT+7",
  "BackgroundRSSI1": -120, "BackgroundRSSI2": -120, "BackgroundRssiConverted1": 9,
  "KeepEthernetOnBattery": false, "KeepWifiOnBattery": false,
  "NotifyOfStatusEthernet": false, "NotifyOfStatusGSM": true, "NotifyOfStatusWiFi": false
}
```

### Управление устройствами (для v2)

| Метод | Путь | Параметры | Ответ |
| --- | --- | --- | --- |
| POST | `ConsoleState/OnDevice` | `?idConsole=`, `?serialNumber=`, `?channelNumber=` | `IsDoneResponse` |
| POST | `ConsoleState/OffDevice` | те же | `IsDoneResponse` |
| POST | `ConsoleState/StopDevice` | те же | `IsDoneResponse` |
| POST | `ConsoleState/ChangeDeviceSetpoint` | body `{"IdConsole","SerialNumber","NumberChannel","Setpoint"}` | `IsDoneResponse` |
| POST | `ConsoleState/SetTargetValueDevice` | ? | ? |
| POST | `ConsoleState/DeviceRunToSetpoint` | ? | ? |
| PUT | `ConsoleState/Sensor` | body `ApiDevice` (переименование/настройки) | `IsDoneResponse` |
| DELETE | `ConsoleState/Sensor` | `?idConsole=`, `?serialNumber=` | — |
| GET | `ConsoleState/Sensor` | `?idConsole=`, `?serialNumber=` | `ApiDevice` |
| GET | `ConsoleState/ListAvailableSensors` | `?idConsole=` | поиск в эфире |
| POST | `ConsoleState/AttachSensors` | ? | привязка найденных |
| POST | `ConsoleState/SearchSensors` | ? | старт поиска |
| GET/PUT | `ConsoleState/WiFiSettingsState`, `ConnectWiFiNetwork`, `DisconnectWiFiNetwork` | form `wSsid`, `wPass` (у хаба локально: `http://192.168.1.1` POST form, Origin/Referer `http://192.168.1.1/`) | WiFi хаба |
| GET | `ConsoleState/GetRestartStatus` | `?idConsole=` | статус перезагрузки |
| POST | `ConsoleState/RestartHub` | `?idConsole=` | перезагрузка хаба |
| POST/GET/STOP | `ConsoleState/StartTestDetectionZone` / `StopTestDetectionZone` | ? | тест зоны PIR |

`IsDoneResponse`: `{"IsDone": bool, "DescriptionError": string}`.

⚠️ `http://192.168.1.1` в приложении — ТОЛЬКО веб-морда настройки WiFi хаба
(HTML-страница, form-urlencoded, заголовки Origin/Referer обязательны).
Локального API устройств нет — всё через облако.

---

## 5. Охрана: режимы и постановка/снятие

### Перечисления (из APK)

`ProtectionMode` (ApiProtectionMode / domain/group/ProtectionMode):

| Значение | Смысл |
| --- | --- |
| `IS_DISARMED` | снято |
| `DISARMING` | идёт снятие |
| `PROTECTION` / `ARM` | под охраной (полной) |
| `ARM_APP` | под охраной (периметр/домой) |
| `ARM_PART` | частичная охрана |
| `PARTIAL_PROTECTION` | частичная |
| `ERROR_PROTECTION` | ошибка постановки |
| `UNKNOWN` | неизвестно |

`ProtectionStatus` (ApiProtectionStatus): `NORMA` | `ALARM` | `ALARM_DELAY` (предтревога — обратный отсчёт).

⚠️ В живом JSON значения **PascalCase**: `Protection` / `Norma` — сравнивать без учёта регистра.

### Постановка/снятие — механизм v2

Смена режима выполняется командой **Favorites/RunCmd** («избранное» = сцена охраны):

- `GET Favorites/All` → список избранного; элементы с `Type` guard имеют
  `TypeFavoriteGuard`: `ARM`, `ARM_PART`, `PANIC_BUTTON`
- `ApiFavorite`: `Id`, `Name`, `Number`, `IsSelected`, `Concrete`, `AnalogState`
- `POST Favorites/RunCmd` body `{"FavoriteId": id, "ObjectId": id, "State": "…", "IsForce": bool}`
  → `IsDoneResponse` — выполнить команду охраны (State — целевое состояние)
- `PUT Favorites/Selected`, `GET Favorites/Selected?`

Альтернативы: `PUT ConsoleState/StateConsole` (body `ApiConsoleStatus`) — запись
поля состояния хаба; `ConsoleState/ActionsKeyFob`, `ActionsKeypad`, `GetActionsRfid` —
действия кнопок/брелоков (в т.ч. постановка).

Точный контракт RunCmd (набор State) перед реализацией v2 проверить живым тестом
+ mitmproxy.

---

## 6. События (журнал, архив)

Источник: `EventsArchiveApi`, `ApiEventArch`, `ApiTypeEvent`.

| Метод | Путь | Параметры |
| --- | --- | --- |
| GET | `EventsArchive/EventObjectPagination` | `?idConsole=`, пагинация (страница/размер — уточнить) |
| GET | `EventsArchive/CountNewEventsAllObjects` | — |
| POST | `EventsArchive/MarkReadEvents` | body ? |
| POST | `EventsArchive/MarkReadAllEvents` | `?idConsole=`? |

`ApiEventArch`: `Id`, `IdDevice`, `IdObject`, `NumChannel`, `Title`, `Description`,
`NameSensor`, `TypeSensor`, `Type` (ApiTypeEvent), `EventTime`, `IsUnread`.

`ApiTypeEvent` — большой enum, ключевые значения: `ALARM`, `ALARM_FIRE`, `ALARM_CASE`,
`ALARM_MAIN_POWER`, `ALARM_SECONDARY_POWER`, `EMERGENCY_ALARM`, `ARMED`, `ARMED_TO_PCN`,
`DISARMED`, `DISARMED_UNDER`, `CASE`, `CASE_OK`, `CHANNEL_FAULTY`, `CHANNEL_NORMA`,
`ACTIVE_CHNL`, `COMMUNICATION_ERROR`, `DEVICE_LOCKED`, `DEVICE_UNLOCKED`, `CAMERA_NORMA`…

`Device.getEvents()` в ListDevices — АКТИВНЫЕ события устройства (в живых данных пусто,
наполняется при событии). `Object.ActiveEvents` — активные события объекта.

---

## 7. Сценарии (автоматизации Livi)

`ScenarioApi`: `GET Scenario/ObjectScenarios?idConsole=`, `GET Scenario/Scenario?id=`,
`POST/PUT Scenario/Scenario` (body `ApiScenario`), `DELETE Scenario/Scenario`,
`GET Scenario/Actions`, `GET Scenario/SourceEventsObject?idConsole=`,
`POST Scenario/StartScenario?consoleId=&scenarioId=`,
`PUT Scenario/Status` (body `ChangeScenarioStatusRequest`).

Доменные типы действий: `ActionSettings` (Device/Group/Scenario/Guard/Thermostat/Other),
`ActionTypeBearer` —Bearer-токен в ActionSettings.

## 8. Группы

`GroupApi`: `GET Groups/Groups?idConsole=`, `POST/DELETE Groups/Group`,
`PUT Groups/GroupDevices`, `PUT Groups/MoveDeviceToGroup`, `PUT Groups/GroupSettings`.

## 9. Виджеты

`WidgetsApi`: `GET Widgets/All?idConsole=`, `POST Widgets/Selected` (body `PostSelectedWidgetsRequest`).
`ApiWidget`: `SerialNumber`, `TypeSensor`, `ChannelNumber`, `Value`, `DataType`, `TypeUnit`, `IsFaulty`, `IsSelected`…

## 10. Пользователи объекта

`UserObjectApi`: `GET UsersObject/UsersObject?idConsole=`, `GET/PUT/DELETE UsersObject/User`,
`POST UsersObject/AddDeleteUserObject`, `PUT UsersObject/ChangeOwner`, `PUT UsersObject/UpdateUserRole`,
`POST UsersObject/SaveAccessKeyForUser`, `SaveKeypadPwdForUsers`, `DeleteKeyRfid`, `DeleteKeypadPwd`,
`StartBindingRfid`, `WaitingKeyRfid`, `OffNotification`, `OnNotification`, `UploadAvatar`.

## 11. Видео

Облако: `VideoApi` (`AuthorizationUrl` — OAuth-редирект, `Cameras`, `Camera`, `Records`,
`BindToDevice`, `DeleteRecord`, `SetConfigCamera`, `Logout`).
RTSP: `VideoRtspApi` (`AddCamera`, `Cameras`, `Camera`, `DeleteCamera`, `UpdateSettingsCamera`).

## 12. Статистика (графики)

`DeviceStatisticsApi`:
- `GET statistics/devices/GetAvailableDeviceSources?idConsole=?`
- `GET statistics/devices/GetAvailableDevices?…`
- `POST statistics/devices/GetDeviceCharts` (body — устройство/каналы/период)
- `POST statistics/devices/GetChannelChart` (body — канал/период)

Пригодится для v3 (графики температуры).

## 13. Прочее

- Охранные компании (ЧОП): `GuardApi` — `GuardCompany/Guards`, `GuardsInCity`, `Guard`,
  `GuardCompanySelected`, `GuardCompanySettings`, `GuardCompanyDelete`, `NeedGuardInCity`,
  `SendRequest` (body `ApiGuardRequest`: `City`, `Email`, `GuardId`, `ObjectId`, `PcnAccessRights`, `PhoneNumber`, `UserName`)
- Города: `City/Cities`, `City/SetCityObjectById`, `City/SetCityObjectByIp`
- Магазин: `Products/GetProducts`, `Cart/*` (Add/Delete/DeleteProduct/Get/CountProducts/Update), `Order/SendOrder`
- Поддержка: `Support/SupportRequest`
- Инструкции: `SettingsApp/Instructions`
- Профиль: `GET/PUT Account/Profile` (`ApiCurrentUser`), `POST Account/ChangePassword`
- Push-регистрация: `POST AndroidServiceController/RegisterTokenGCM` (form `DeviceId`, `Token`),
  `RegisterTokenVKPNS` — интеграции не нужен (push только для приложения)
- Выход: `GET Account/Logout?deviceId=…`

---

## 14. Push-уведомления (FCM) — как приложение узнаёт в реальном времени

`PushNotificationServiceImpl` + `FirebasePushNotificationService`:
входящее FCM-сообщение содержит `data`: `consoleId`, ключи сообщений объекта
(`objectMessages`), флаг `isAlarm`, `notificationType` (`NotificationType`:
`ALARM` / `ERROR` / `DEFAULT`). По получении приложение перечитывает объект/события
через API (push = триггер, не данные).

Для интеграции это означает: real-time без своей реализации push невозможен,
обновление — только polling (текущий выбор: 30 с).

---

## 15. Сверено с живым сервером (2026-10-29, fixtures/)

| Что | Результат |
| --- | --- |
| Логин `+7906…` | ❌ 400 |
| Логин `79001234567` на `/Token` | ✅ 200, bearer, 1 год |
| `…/api/v3/Token` | ❌ 404 |
| `Object/ListObjects` | ✅ 1 объект «Дом», SmartHub4G |
| `ConsoleState/ListDevices` | ✅ 24 устройства, структуры §4 |
| `Events` устройств | пусто в спокойном состоянии |
| TypeSensor формат | PascalCase: LiviCs, LiviTs, LiviMs, LiviFs2, LiviRelay1224, LiviHTS, LiviWc… |

## 16. Правила маппинга для интеграции (реализовано в const.py)

1. `TypeSensor` нормализуется: upper → вставка `_` в `LIVIxxx` → словарь алиасов
   (`LIVI_FS2`→`LIVI_FS_2`, `LIVI_RELAY1224`→`LIVI_RELAY_1224`)
2. Состояние датчика — `Sensor.Value` (`"True"`=тревога, `"On"/"Off"`=реле/сирена/клапан)
3. Температура — `Sensor.Channels[Number==3].Value`; влажность — `Number==4` (HTS)
4. Хаб строится из `ConsoleState` объекта (в ListDevices хаб отсутствует)
5. `ProtectionMode`/`ProtectionStatus` сравниваются без учёта регистра
6. Телефон в `username` — без `+`
