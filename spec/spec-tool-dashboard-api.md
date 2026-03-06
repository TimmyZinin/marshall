---
title: Marshall AI Listener — Спецификация Dashboard REST API
version: "1.0"
date_created: 2026-03-06
owner: Тим Зинин (Zinin Corp)
tags: [tool, api, rest, fastapi, dashboard, sprint0]
depends_on: [master_brief.md, product_brief.md, spec-data-schema.md, spec-tool-alert-engine.md]
sprint: "Sprint 0 (Спринт 4)"
module: S0-F04 (Dashboard API)
---

# Marshall AI Listener — Спецификация Dashboard REST API

---

## 1. Цель и скоуп

### 1.1 Цель

Спецификация описывает REST API на FastAPI, который обеспечивает веб-дашборд менеджеров Marshall данными о рейсах, алертах и статистике. API является единственным публичным интерфейсом системы в Sprint 0: бизнес-логика (Chat Listener, AI Parser, Alert Engine) работает независимо, а API предоставляет только доступ на чтение к накопленным данным и ограниченное управление статусами алертов.

**Ключевые свойства:**
- Только REST (без WebSocket в Sprint 0 — дашборд использует polling каждые 3 секунды)
- Авторизация через JWT Bearer-токен с ролевым контролем доступа
- Асинхронная реализация на FastAPI + asyncpg
- Полная поддержка фильтрации, пагинации, сортировки

### 1.2 Скоуп

**Входит в скоуп Sprint 0:**
- 9 endpoint-групп: trips, alerts, stats, chats, auth, health
- JWT-авторизация с тремя ролями (admin, manager, viewer)
- Пагинация на основе page + limit для всех коллекций
- Фильтрация по всем основным параметрам (customer, status, severity, date)
- Ответы в JSON со стандартизированными кодами ошибок

**Выходит из скоупа (отложено на Sprint 1+):**
- WebSocket / Server-Sent Events (polling заменяет)
- Экспорт данных в CSV или Excel
- Кастомные фильтры и сохранённые запросы
- OAuth 2.0 / SSO / LDAP авторизация
- Webhook-уведомления
- Bulk-операции над алертами
- GraphQL

### 1.3 Пользователи API

| Роль | Описание | Разрешения |
|------|----------|-----------|
| `admin` | Полный доступ: просмотр, управление алертами, управление пользователями | Все endpoints |
| `manager` | Просмотр + управление статусами алертов | GET все + PATCH /alerts/{id} |
| `viewer` | Только чтение (руководство Marshall) | Только GET endpoints |

---

## 2. Определения

| Термин | Определение |
|--------|-------------|
| **JWT** | JSON Web Token — самодостаточный токен авторизации, подписанный секретным ключом HS256. Срок жизни 24 часа |
| **Bearer-токен** | Схема авторизации HTTP: `Authorization: Bearer <jwt>`. Требуется для всех endpoint-ов кроме /api/health и /api/auth/login |
| **Роль (role)** | Уровень доступа пользователя дашборда: admin, manager, viewer. Хранится в payload JWT |
| **Пагинация** | Разбивка коллекции на страницы с параметрами `page` (номер страницы, начиная с 1) и `limit` (размер страницы, дефолт 20, макс 100) |
| **Trip** | Рейс Marshall — перевозка с уникальным trip_id, маршрутом, заказчиком, статусом. Агрегируется из parsed_messages |
| **Alert** | Критическое событие, обнаруженное Alert Engine по бизнес-правилам. Имеет тип, severity, статус жизненного цикла |
| **Severity** | Критичность алерта: `high` (блокирует рейс, штраф), `medium` (требует внимания), `low` (информационный) |
| **Alert Status** | Жизненный цикл алерта: `new` (создан системой) → `reviewed` (менеджер увидел) → `resolved` (закрыт) |
| **Trip Status** | Статус рейса: assigned, in_transit, loading, unloading, completed, problem, cancelled |
| **Chat Message** | Сырое сообщение из чата диспетчеров с привязанным результатом парсинга LLM |
| **asyncpg** | Асинхронный PostgreSQL-драйвер для Python. Используется вместо SQLAlchemy ORM |
| **Pydantic v2** | Библиотека валидации данных Python. Используется для Request/Response схем FastAPI |
| **CORS** | Cross-Origin Resource Sharing. Настраивается для разрешения запросов от браузерного дашборда |
| **UTC** | Coordinated Universal Time. Все timestamps в API возвращаются в UTC (ISO 8601 с суффиксом Z) |
| **MSK** | Moscow Standard Time (UTC+3). Отображение временных меток на фронтенде — MSK |

---

## 3. Требования, ограничения и рекомендации

### 3.1 Функциональные требования

#### REQ-API-001: Список рейсов с фильтрацией
**Требование:** GET /api/trips должен возвращать список рейсов с поддержкой фильтров по заказчику (customer), статусу (status), диапазону дат (date_from, date_to), а также пагинацией (page, limit). Каждый объект Trip включает поле alert_count — количество связанных алертов.

**Обоснование:** Основной экран дашборда — список активных рейсов. Менеджер фильтрует по заказчику (Тандер, WB, X5) или по статусу (active/problem).

**Пример:** GET /api/trips?customer=WB&status=in_transit&page=1&limit=20

---

#### REQ-API-002: Детали одного рейса
**Требование:** GET /api/trips/{trip_id} должен возвращать полный объект Trip, список связанных алертов и последние 10 парсированных сообщений по этому рейсу в хронологическом порядке.

**Обоснование:** Менеджер кликает на рейс в дашборде и видит полный контекст: что происходит с рейсом, какие алерты созданы, что говорили в чате.

---

#### REQ-API-003: Лента алертов с фильтрацией
**Требование:** GET /api/alerts должен возвращать список алертов с фильтрами по severity (high, medium, low), status (new, reviewed, resolved), customer, alert_type, диапазону дат и пагинацией. Сортировка по умолчанию: created_at DESC, HIGH-алерты первыми.

**Обоснование:** Вкладка "Алерты" — второй основной экран дашборда. Менеджер видит критические события отсортированные по важности.

---

#### REQ-API-004: Управление статусом алерта
**Требование:** PATCH /api/alerts/{alert_id} должен позволять обновить статус алерта (reviewed, resolved, false_positive) и зафиксировать имя пользователя (reviewed_by). Операция доступна только ролям admin и manager.

**Обоснование:** Менеджер видит алерт, оценивает ситуацию и отмечает его как "просмотрен" или "закрыт". Это основное интерактивное действие в дашборде Sprint 0.

---

#### REQ-API-005: Сводная статистика
**Требование:** GET /api/stats должен возвращать агрегированные метрики за период (today, week, month): total_trips, active_trips, total_alerts, high_alerts, avg_latency_ms, messages_today.

**Обоснование:** Виджеты в заголовке дашборда — KPI-плитки для руководства Marshall. Николя хочет видеть "45 потенциальных штрафов за неделю".

---

#### REQ-API-006: Данные для графиков
**Требование:** GET /api/stats/chart должен возвращать временной ряд данных для построения графиков с параметрами metric (trips, alerts, latency), period (today, week, month) и granularity (hour, day). Ответ — массив объектов {timestamp, value}.

**Обоснование:** Дашборд отображает 3 графика на Chart.js. API должен готовить данные, сгруппированные по часам или дням.

---

#### REQ-API-007: История сообщений по рейсу
**Требование:** GET /api/chats/{trip_id} должен возвращать хронологический список всех сырых сообщений по рейсу с результатами парсинга (если есть). Каждый элемент включает: текст сообщения, отправителя, время, данные парсинга (trip_id, urgency, issue, confidence).

**Обоснование:** Менеджер должен иметь возможность открыть "детали рейса" и прочитать переписку, которая привела к алерту. Это доказательная база для оспаривания штрафов.

---

#### REQ-API-008: Авторизация через JWT
**Требование:** POST /api/auth/login должен принимать {username, password}, валидировать по таблице dashboard_users (bcrypt-хеш), обновлять last_login_at и возвращать JWT-токен с expiry 24 часа и информацию о пользователе (username, role, display_name).

**Обоснование:** Дашборд требует авторизации. Sprint 0 использует простую пару username/password без OAuth.

---

#### REQ-API-009: Health check endpoint
**Требование:** GET /api/health должен возвращать статус системы (status: ok/degraded/down), доступность PostgreSQL (db: connected/disconnected) и uptime_seconds без авторизации.

**Обоснование:** Мониторинг Docker-контейнера. RUVDS cron-скрипт пингует этот endpoint каждые 5 минут.

---

#### REQ-API-010: Ролевой контроль доступа (RBAC)
**Требование:** Все endpoint-ы кроме /api/health и /api/auth/login требуют валидного JWT. PATCH /api/alerts/{alert_id} требует роль manager или admin. Viewer-роль имеет доступ только к GET-запросам.

**Обоснование:** Руководство Marshall (viewer) должно видеть данные, но не управлять алертами. Только оперативный персонал (manager, admin) изменяет статусы.

---

#### REQ-API-011: Стандартизированные ответы об ошибках
**Требование:** Все ошибочные ответы должны возвращать JSON в формате: {error_code, message, details (опционально), request_id}. HTTP-коды: 400 (валидация), 401 (не авторизован), 403 (нет прав), 404 (не найден), 422 (Pydantic validation), 500 (внутренняя ошибка).

**Обоснование:** Консистентный формат ошибок упрощает отладку и обработку на фронтенде.

---

#### REQ-API-012: Пагинация для всех коллекций
**Требование:** Все endpoint-ы, возвращающие массивы данных, должны поддерживать параметры page (дефолт 1, минимум 1) и limit (дефолт 20, максимум 100). Ответ включает метаданные: total, page, limit, pages (общее количество страниц).

**Обоснование:** Дашборд не должен загружать все 500+ рейсов сразу. Пагинация обязательна для производительности.

---

#### REQ-API-013: Фильтрация по диапазону дат
**Требование:** Endpoint-ы /api/trips, /api/alerts поддерживают параметры date_from и date_to в формате ISO 8601 (YYYY-MM-DD или полный datetime). Фильтрация применяется к полю created_at соответствующей таблицы.

**Обоснование:** Руководство Marshall просматривает данные за конкретные смены и дни для расследования инцидентов.

---

#### REQ-API-014: Структурированное логирование запросов
**Требование:** Каждый HTTP-запрос должен логироваться в JSON-формате с полями: timestamp, method, path, status_code, duration_ms, user (из JWT если авторизован), request_id.

**Обоснование:** Аудит доступа к данным. Отладка производительности. Соответствие правилу логирования из CLAUDE.md.

---

#### REQ-API-015: CORS для браузерного дашборда
**Требование:** FastAPI должен настраивать CORS-заголовки для разрешения запросов от браузерного дашборда (Origin: http://localhost:* для разработки, http://88.218.248.114:* для продакшна на RUVDS).

**Обоснование:** Дашборд — HTML-страница, которая делает fetch-запросы к API. Браузер блокирует cross-origin запросы без CORS-заголовков.

---

### 3.2 Ограничения

#### CON-API-001: Нет WebSocket в Sprint 0
Polling каждые 3 секунды вместо real-time соединения. Фронтенд вызывает GET /api/alerts и GET /api/trips каждые 3 секунды.

#### CON-API-002: JWT без refresh-токена
Срок жизни 24 часа. При истечении — повторная авторизация через /api/auth/login. Refresh-токены отложены на Sprint 1.

#### CON-API-003: Пароли в .env, не в admin-интерфейсе
Создание пользователей дашборда — через SQL INSERT в dashboard_users. Управление пользователями через интерфейс не входит в Sprint 0.

#### CON-API-004: Нет rate limiting
Sprint 0 не реализует rate limiting на уровне API. Polling 3 сек от одного клиента допустим. Ограничения появятся в Sprint 1 при масштабировании.

#### CON-API-005: Нет кеширования ответов
Все запросы идут в PostgreSQL. Redis-кеш и CDN — Sprint 1+. Производительность обеспечивается индексами БД.

#### CON-API-006: Timestamp только в UTC
API возвращает все временные метки в UTC (ISO 8601 с `Z`). Конвертация в MSK — ответственность фронтенда.

#### CON-API-007: Максимальный размер ответа — 100 элементов
Параметр limit не может превышать 100. Для GET /api/chats/{trip_id} максимум — 500 сообщений (история рейса).

---

### 3.3 Рекомендации

#### REC-API-001: Использовать asyncpg connection pool
Pool size 10-20 соединений. FastAPI + asyncio создаёт конкурентные запросы при polling от нескольких клиентов.

#### REC-API-002: Добавить request_id в middleware
Каждый запрос получает UUID `request_id`, который включается в ответы ошибок и логи. Упрощает отладку по логам.

#### REC-API-003: Индекс idx_alerts_active_high для основного запроса
Запрос GET /api/alerts?status=new&severity=high выполняется каждые 3 секунды. Составной частичный индекс `(severity, created_at DESC) WHERE status = 'new'` критически важен.

#### REC-API-004: Возвращать Cache-Control: no-store для алертов
Алерты обновляются в реальном времени. Браузерный кеш должен быть отключён для /api/alerts и /api/trips.

#### REC-API-005: Использовать Pydantic v2 ResponseModel
Явно объявлять response_model для каждого endpoint. Это обеспечивает автодокументацию и фильтрацию полей (не возвращать password_hash из dashboard_users).

---

## 4. Интерфейсы и контракты данных

### 4.1 Базовая информация

| Параметр | Значение |
|----------|---------|
| Base URL (продакшн) | `http://88.218.248.114:8000` |
| Base URL (разработка) | `http://localhost:8000` |
| Версия API | v1 (без prefix в Sprint 0, добавить /v1/ в Sprint 1) |
| Content-Type | `application/json` |
| Авторизация | `Authorization: Bearer <jwt_token>` |
| Формат timestamp | ISO 8601, UTC: `2026-03-06T14:30:15.000Z` |
| Кодировка | UTF-8 |

### 4.2 Общие схемы

#### Схема пагинированного ответа
```json
{
  "data": [...],
  "pagination": {
    "total": 145,
    "page": 1,
    "limit": 20,
    "pages": 8
  }
}
```

#### Схема ошибки
```json
{
  "error_code": "ALERT_NOT_FOUND",
  "message": "Алерт с указанным ID не найден",
  "details": null,
  "request_id": "req-550e8400-e29b-41d4-a716"
}
```

#### Схема объекта Trip
```json
{
  "id": 42,
  "trip_id": "4521",
  "route_from": "Москва",
  "route_to": "Краснодар",
  "customer": "WB",
  "driver_name": "Иван Иванов",
  "dispatcher_name": "Алексей",
  "status": "in_transit",
  "slot_time": "2026-03-06T11:00:00.000Z",
  "departure_time": "2026-03-06T09:45:00.000Z",
  "arrival_time": null,
  "alert_count": 2,
  "last_update": "2026-03-06T12:20:00.000Z",
  "created_at": "2026-03-06T09:15:00.000Z",
  "updated_at": "2026-03-06T12:20:00.000Z"
}
```

#### Схема объекта Alert
```json
{
  "id": 101,
  "trip_id": "4521",
  "alert_type": "delay",
  "severity": "medium",
  "message": "Возможное опоздание на 40 мин на слот WB 14:00 рейс 4521",
  "customer": "WB",
  "rule_id": "wb_delay_1h",
  "status": "new",
  "reviewed_by": null,
  "reviewed_at": null,
  "created_at": "2026-03-06T11:30:15.000Z",
  "parsed_data": {
    "urgency": "medium",
    "issue": "Стою в пробке на МКАД, опаздываю на 40 мин",
    "confidence": 0.87,
    "slot_time": "14:00"
  }
}
```

#### Схема объекта ChatMessage
```json
{
  "id": 5003,
  "chat_id": -100123456789,
  "chat_name": "Marshall Test — WB Рейсы",
  "sender_name": "Водитель Иван",
  "text": "Стою в пробке на МКАД, опаздываю минут на 40",
  "timestamp": "2026-03-06T08:30:00.000Z",
  "created_at": "2026-03-06T08:30:01.000Z",
  "parsed": {
    "trip_id": "4521",
    "urgency": "medium",
    "issue": "Опоздание на 40 мин из-за пробки",
    "confidence": 0.87,
    "status": "problem"
  }
}
```

---

### 4.3 Endpoint: POST /api/auth/login

**Назначение:** Авторизация пользователя дашборда. Возвращает JWT-токен.

**Метод:** POST
**Путь:** `/api/auth/login`
**Авторизация:** Не требуется

**Request Body:**
```json
{
  "username": "victoria",
  "password": "securepassword123"
}
```

| Поле | Тип | Обязательное | Описание |
|------|-----|--------------|---------|
| username | string | Да | Логин из dashboard_users. Длина 1-100 символов |
| password | string | Да | Пароль. Проверяется по bcrypt-хешу |

**Response 200 OK:**
```json
{
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VybmFtZSI6InZpY3RvcmlhIiwicm9sZSI6Im1hbmFnZXIiLCJleHAiOjE3NDE4NzIwMDB9.signature",
  "expires_at": "2026-03-07T14:00:00.000Z",
  "user": {
    "username": "victoria",
    "role": "manager",
    "display_name": "Виктория Фимина"
  }
}
```

**JWT Payload:**
```json
{
  "sub": "victoria",
  "role": "manager",
  "display_name": "Виктория Фимина",
  "exp": 1741872000,
  "iat": 1741785600
}
```

**HTTP Status Codes:**
| Код | Условие |
|-----|---------|
| 200 | Успешная авторизация |
| 400 | Отсутствует username или password |
| 401 | Неверные учётные данные |
| 403 | Аккаунт деактивирован (is_active=false) |
| 422 | Ошибка валидации Pydantic (неверный тип данных) |
| 500 | Ошибка базы данных |

---

### 4.4 Endpoint: GET /api/trips

**Назначение:** Список рейсов с фильтрацией и пагинацией.

**Метод:** GET
**Путь:** `/api/trips`
**Авторизация:** Bearer token (любая роль)

**Query Parameters:**

| Параметр | Тип | Дефолт | Описание |
|----------|-----|--------|---------|
| customer | string | null | Фильтр по заказчику. Допустимые значения: Тандер, WB, X5, Магнит, Сельта, Сибур |
| status | string | null | Фильтр по статусу рейса: assigned, in_transit, loading, unloading, completed, problem, cancelled |
| date_from | string (ISO 8601) | null | Начало диапазона дат (по полю created_at) |
| date_to | string (ISO 8601) | null | Конец диапазона дат (по полю created_at) |
| page | integer | 1 | Номер страницы (минимум 1) |
| limit | integer | 20 | Размер страницы (минимум 1, максимум 100) |
| sort | string | created_at:desc | Сортировка: поле:направление. Допустимые поля: created_at, updated_at, alert_count, trip_id |

**Response 200 OK:**
```json
{
  "data": [
    {
      "id": 42,
      "trip_id": "4521",
      "route_from": "Москва",
      "route_to": "Краснодар",
      "customer": "WB",
      "driver_name": "Иван Иванов",
      "dispatcher_name": "Алексей",
      "status": "in_transit",
      "slot_time": "2026-03-06T11:00:00.000Z",
      "departure_time": "2026-03-06T09:45:00.000Z",
      "arrival_time": null,
      "alert_count": 2,
      "last_update": "2026-03-06T12:20:00.000Z",
      "created_at": "2026-03-06T09:15:00.000Z",
      "updated_at": "2026-03-06T12:20:00.000Z"
    }
  ],
  "pagination": {
    "total": 12,
    "page": 1,
    "limit": 20,
    "pages": 1
  }
}
```

**HTTP Status Codes:**
| Код | Условие |
|-----|---------|
| 200 | Успех (может быть пустой массив data) |
| 400 | Неверный формат date_from/date_to или недопустимое значение status/customer |
| 401 | Отсутствует или просрочен JWT-токен |
| 422 | Ошибка валидации Pydantic (например, page=-1) |
| 500 | Ошибка базы данных |

---

### 4.5 Endpoint: GET /api/trips/{trip_id}

**Назначение:** Детали одного рейса с алертами и последними сообщениями.

**Метод:** GET
**Путь:** `/api/trips/{trip_id}`
**Авторизация:** Bearer token (любая роль)

**Path Parameters:**

| Параметр | Тип | Описание |
|----------|-----|---------|
| trip_id | string | Идентификатор рейса (например, "4521"). Поиск по полю trips.trip_id |

**Response 200 OK:**
```json
{
  "trip": {
    "id": 42,
    "trip_id": "4521",
    "route_from": "Москва",
    "route_to": "Краснодар",
    "customer": "WB",
    "driver_name": "Иван Иванов",
    "dispatcher_name": "Алексей",
    "status": "in_transit",
    "slot_time": "2026-03-06T11:00:00.000Z",
    "departure_time": "2026-03-06T09:45:00.000Z",
    "arrival_time": null,
    "alert_count": 2,
    "last_update": "2026-03-06T12:20:00.000Z",
    "created_at": "2026-03-06T09:15:00.000Z",
    "updated_at": "2026-03-06T12:20:00.000Z"
  },
  "alerts": [
    {
      "id": 101,
      "trip_id": "4521",
      "alert_type": "delay",
      "severity": "medium",
      "message": "Возможное опоздание на 40 мин на слот WB 14:00",
      "customer": "WB",
      "rule_id": "wb_delay_1h",
      "status": "new",
      "reviewed_by": null,
      "reviewed_at": null,
      "created_at": "2026-03-06T11:30:15.000Z",
      "parsed_data": {
        "urgency": "medium",
        "issue": "Стою в пробке на МКАД, опаздываю на 40 мин",
        "confidence": 0.87,
        "slot_time": "14:00"
      }
    }
  ],
  "recent_messages": [
    {
      "id": 5003,
      "sender_name": "Водитель Иван",
      "text": "Стою в пробке на МКАД, опаздываю минут на 40",
      "timestamp": "2026-03-06T08:30:00.000Z",
      "parsed": {
        "urgency": "medium",
        "issue": "Опоздание на 40 мин из-за пробки",
        "confidence": 0.87
      }
    }
  ]
}
```

**Примечание:** `recent_messages` — последние 10 парсированных сообщений по рейсу в хронологическом порядке (от старых к новым).

**HTTP Status Codes:**
| Код | Условие |
|-----|---------|
| 200 | Рейс найден |
| 401 | Отсутствует или просрочен JWT-токен |
| 404 | Рейс с указанным trip_id не найден |
| 500 | Ошибка базы данных |

---

### 4.6 Endpoint: GET /api/alerts

**Назначение:** Лента алертов с фильтрацией и пагинацией.

**Метод:** GET
**Путь:** `/api/alerts`
**Авторизация:** Bearer token (любая роль)

**Query Parameters:**

| Параметр | Тип | Дефолт | Описание |
|----------|-----|--------|---------|
| severity | string | null | Фильтр: high, medium, low |
| status | string | null | Фильтр: new, reviewed, resolved |
| customer | string | null | Фильтр по заказчику (Тандер, WB, X5, Магнит, Сельта, Сибур) |
| alert_type | string | null | Фильтр: delay, equipment_failure, downtime, safety_violation, docs_missing |
| trip_id | string | null | Фильтр по номеру рейса |
| date_from | string (ISO 8601) | null | Начало диапазона дат (по created_at) |
| date_to | string (ISO 8601) | null | Конец диапазона дат (по created_at) |
| page | integer | 1 | Номер страницы |
| limit | integer | 20 | Размер страницы (максимум 100) |
| sort | string | severity_weight:desc,created_at:desc | Сортировка. Допустимые поля: created_at, severity_weight, status |

**Примечание по сортировке:** `severity_weight` — виртуальное поле: high=3, medium=2, low=1. Обеспечивает показ HIGH-алертов первыми.

**Response 200 OK:**
```json
{
  "data": [
    {
      "id": 105,
      "trip_id": "7803",
      "alert_type": "equipment_failure",
      "severity": "high",
      "message": "КРИТИЧНО: Нарушение температуры у Тандер 7803: Реф показывает +8",
      "customer": "Тандер",
      "rule_id": "thander_temp_violation",
      "status": "new",
      "reviewed_by": null,
      "reviewed_at": null,
      "created_at": "2026-03-06T07:45:00.000Z",
      "parsed_data": {
        "urgency": "high",
        "issue": "Реф не выходит на температуру, показывает +8",
        "confidence": 0.92
      }
    },
    {
      "id": 101,
      "trip_id": "4521",
      "alert_type": "delay",
      "severity": "medium",
      "message": "Возможное опоздание на 40 мин на слот WB 14:00 рейс 4521",
      "customer": "WB",
      "rule_id": "wb_delay_1h",
      "status": "new",
      "reviewed_by": null,
      "reviewed_at": null,
      "created_at": "2026-03-06T11:30:15.000Z",
      "parsed_data": {
        "urgency": "medium",
        "issue": "Стою в пробке на МКАД, опаздываю на 40 мин",
        "confidence": 0.87
      }
    }
  ],
  "pagination": {
    "total": 45,
    "page": 1,
    "limit": 20,
    "pages": 3
  }
}
```

**HTTP Status Codes:**
| Код | Условие |
|-----|---------|
| 200 | Успех (может быть пустой массив) |
| 400 | Недопустимое значение severity, status или alert_type |
| 401 | Отсутствует или просрочен JWT-токен |
| 422 | Ошибка валидации параметров |
| 500 | Ошибка базы данных |

---

### 4.7 Endpoint: PATCH /api/alerts/{alert_id}

**Назначение:** Обновить статус алерта (review/resolve/false_positive).

**Метод:** PATCH
**Путь:** `/api/alerts/{alert_id}`
**Авторизация:** Bearer token (только роли admin и manager)

**Path Parameters:**

| Параметр | Тип | Описание |
|----------|-----|---------|
| alert_id | integer | Первичный ключ алерта (alerts.id) |

**Request Body:**
```json
{
  "status": "reviewed",
  "reviewed_by": "Виктория Фимина"
}
```

| Поле | Тип | Обязательное | Допустимые значения | Описание |
|------|-----|--------------|---------------------|---------|
| status | string | Да | reviewed, resolved, false_positive | Новый статус алерта |
| reviewed_by | string | Да, если status = reviewed | — | Имя пользователя, обрабатывающего алерт |

**Примечание:** `false_positive` — специальный статус для ложных срабатываний. В БД сохраняется как `resolved` с пометкой в reviewed_by: "false_positive:{username}".

**Допустимые переходы статусов:**
- new → reviewed
- new → resolved
- new → false_positive
- reviewed → resolved
- reviewed → false_positive

**Недопустимые переходы:**
- resolved → любой (terminal state)
- false_positive → любой (terminal state)

**Response 200 OK:**
```json
{
  "id": 101,
  "trip_id": "4521",
  "alert_type": "delay",
  "severity": "medium",
  "message": "Возможное опоздание на 40 мин на слот WB 14:00 рейс 4521",
  "customer": "WB",
  "status": "reviewed",
  "reviewed_by": "Виктория Фимина",
  "reviewed_at": "2026-03-06T14:35:20.000Z",
  "created_at": "2026-03-06T11:30:15.000Z"
}
```

**HTTP Status Codes:**
| Код | Условие |
|-----|---------|
| 200 | Статус успешно обновлён |
| 400 | Недопустимый переход статуса (например, resolved → reviewed) |
| 401 | Отсутствует или просрочен JWT-токен |
| 403 | Роль viewer не может изменять алерты |
| 404 | Алерт с указанным ID не найден |
| 422 | Ошибка валидации (неверное значение status) |
| 500 | Ошибка базы данных |

---

### 4.8 Endpoint: GET /api/stats

**Назначение:** Сводная статистика для KPI-виджетов дашборда.

**Метод:** GET
**Путь:** `/api/stats`
**Авторизация:** Bearer token (любая роль)

**Query Parameters:**

| Параметр | Тип | Дефолт | Описание |
|----------|-----|--------|---------|
| period | string | today | Период: today, week, month |
| customer | string | null | Фильтр по заказчику (опционально) |

**Период "today"** — с 00:00:00 текущего дня UTC по текущий момент.
**Период "week"** — последние 7 дней (168 часов от текущего момента).
**Период "month"** — последние 30 дней.

**Response 200 OK:**
```json
{
  "period": "today",
  "generated_at": "2026-03-06T15:00:00.000Z",
  "trips": {
    "total": 12,
    "active": 8,
    "completed": 3,
    "with_problems": 2
  },
  "alerts": {
    "total": 15,
    "high": 2,
    "medium": 8,
    "low": 5,
    "new": 10,
    "reviewed": 3,
    "resolved": 2
  },
  "messages": {
    "today": 187,
    "parsed": 183,
    "parse_errors": 4
  },
  "performance": {
    "avg_parse_latency_ms": 1240,
    "avg_alert_latency_ms": 85,
    "uptime_seconds": 43200
  }
}
```

**HTTP Status Codes:**
| Код | Условие |
|-----|---------|
| 200 | Статистика рассчитана |
| 400 | Неверное значение period |
| 401 | Отсутствует или просрочен JWT-токен |
| 500 | Ошибка базы данных |

---

### 4.9 Endpoint: GET /api/stats/chart

**Назначение:** Временные ряды данных для построения графиков на Chart.js.

**Метод:** GET
**Путь:** `/api/stats/chart`
**Авторизация:** Bearer token (любая роль)

**Query Parameters:**

| Параметр | Тип | Дефолт | Описание |
|----------|-----|--------|---------|
| metric | string | trips | Метрика: trips (количество рейсов), alerts (количество алертов), latency (среднее время парсинга мс) |
| period | string | today | Период: today, week, month |
| granularity | string | auto | Гранулярность: hour, day. "auto" = hour для today/week, day для month |
| customer | string | null | Фильтр по заказчику |
| severity | string | null | Только для metric=alerts. Фильтр по severity: high, medium, low |

**Response 200 OK (пример для metric=alerts, period=today, granularity=hour):**
```json
{
  "metric": "alerts",
  "period": "today",
  "granularity": "hour",
  "customer": null,
  "data": [
    { "timestamp": "2026-03-06T00:00:00.000Z", "value": 0 },
    { "timestamp": "2026-03-06T01:00:00.000Z", "value": 1 },
    { "timestamp": "2026-03-06T07:00:00.000Z", "value": 3 },
    { "timestamp": "2026-03-06T08:00:00.000Z", "value": 5 },
    { "timestamp": "2026-03-06T09:00:00.000Z", "value": 2 },
    { "timestamp": "2026-03-06T14:00:00.000Z", "value": 4 }
  ],
  "summary": {
    "total": 15,
    "peak_value": 5,
    "peak_timestamp": "2026-03-06T08:00:00.000Z"
  }
}
```

**Примечание:** Временные метки в `data` — начало интервала. Для period=today + granularity=hour возвращается 24 точки (с нулями для часов без данных).

**HTTP Status Codes:**
| Код | Условие |
|-----|---------|
| 200 | Данные рассчитаны |
| 400 | Неверные значения metric, period или granularity |
| 401 | Отсутствует или просрочен JWT-токен |
| 500 | Ошибка базы данных |

---

### 4.10 Endpoint: GET /api/chats/{trip_id}

**Назначение:** Хронологическая история сообщений по рейсу.

**Метод:** GET
**Путь:** `/api/chats/{trip_id}`
**Авторизация:** Bearer token (любая роль)

**Path Parameters:**

| Параметр | Тип | Описание |
|----------|-----|---------|
| trip_id | string | Идентификатор рейса. Сообщения ищутся по полю parsed_messages.trip_id |

**Query Parameters:**

| Параметр | Тип | Дефолт | Описание |
|----------|-----|--------|---------|
| page | integer | 1 | Номер страницы |
| limit | integer | 50 | Размер страницы (максимум 500) |

**Response 200 OK:**
```json
{
  "trip_id": "4521",
  "data": [
    {
      "id": 5001,
      "chat_id": -100123456789,
      "chat_name": "Marshall Test — WB Рейсы",
      "sender_name": "Диспетчер Алексей",
      "text": "Рейс 4521, Москва-Краснодар, слот на погрузку WB 14:00, реф охладить до +2. Водитель Иванов подтверди.",
      "timestamp": "2026-03-06T06:15:00.000Z",
      "created_at": "2026-03-06T06:15:01.000Z",
      "parsed": {
        "trip_id": "4521",
        "route_from": "Москва",
        "route_to": "Краснодар",
        "status": "assigned",
        "customer": "WB",
        "urgency": "low",
        "issue": null,
        "confidence": 0.95
      }
    },
    {
      "id": 5003,
      "chat_id": -100123456789,
      "chat_name": "Marshall Test — WB Рейсы",
      "sender_name": "Водитель Иван",
      "text": "Стою в пробке на МКАД, опаздываю минут на 40",
      "timestamp": "2026-03-06T08:30:00.000Z",
      "created_at": "2026-03-06T08:30:01.000Z",
      "parsed": {
        "trip_id": "4521",
        "route_from": null,
        "route_to": null,
        "status": "problem",
        "customer": "WB",
        "urgency": "medium",
        "issue": "Опоздание на 40 мин из-за пробки",
        "confidence": 0.87
      }
    }
  ],
  "pagination": {
    "total": 18,
    "page": 1,
    "limit": 50,
    "pages": 1
  }
}
```

**Примечание:** Сообщения отсортированы по `timestamp ASC` (от старых к новым). Поле `parsed` может быть null, если сообщение не содержало данных о данном рейсе (парсинг не нашёл trip_id).

**HTTP Status Codes:**
| Код | Условие |
|-----|---------|
| 200 | История получена (может быть пустой массив) |
| 401 | Отсутствует или просрочен JWT-токен |
| 404 | Рейс с указанным trip_id не найден в таблице trips |
| 500 | Ошибка базы данных |

---

### 4.11 Endpoint: GET /api/health

**Назначение:** Health check для мониторинга и Docker healthcheck.

**Метод:** GET
**Путь:** `/api/health`
**Авторизация:** Не требуется

**Response 200 OK (система в норме):**
```json
{
  "status": "ok",
  "db": "connected",
  "uptime_seconds": 43200,
  "version": "1.0.0",
  "timestamp": "2026-03-06T15:00:00.000Z"
}
```

**Response 200 OK (деградированное состояние):**
```json
{
  "status": "degraded",
  "db": "disconnected",
  "uptime_seconds": 43200,
  "version": "1.0.0",
  "timestamp": "2026-03-06T15:00:00.000Z",
  "issues": ["PostgreSQL connection failed"]
}
```

**Примечание:** Endpoint возвращает HTTP 200 даже при `status: degraded` — это позволяет мониторингу получить детали. При полном падении процесса endpoint просто недоступен.

**HTTP Status Codes:**
| Код | Условие |
|-----|---------|
| 200 | Система работает или деградирована |
| 500 | Критическая ошибка самого API (крайне редко) |

---

### 4.12 Таблица всех endpoint-ов

| Метод | Путь | Авторизация | Роли | Описание |
|-------|------|-------------|------|---------|
| POST | /api/auth/login | Нет | — | Авторизация, получение JWT |
| GET | /api/health | Нет | — | Health check системы |
| GET | /api/trips | Bearer | admin, manager, viewer | Список рейсов |
| GET | /api/trips/{trip_id} | Bearer | admin, manager, viewer | Детали рейса |
| GET | /api/alerts | Bearer | admin, manager, viewer | Лента алертов |
| PATCH | /api/alerts/{alert_id} | Bearer | admin, manager | Обновить статус алерта |
| GET | /api/stats | Bearer | admin, manager, viewer | Сводная статистика |
| GET | /api/stats/chart | Bearer | admin, manager, viewer | Данные для графиков |
| GET | /api/chats/{trip_id} | Bearer | admin, manager, viewer | История чата по рейсу |

---

## 5. Критерии приёмки

### AC-API-001: Успешная авторизация возвращает JWT
**Given** пользователь "victoria" существует в dashboard_users с ролью "manager" и паролем "testpass"
**When** POST /api/auth/login с body {"username": "victoria", "password": "testpass"}
**Then** ответ 200 OK, поле token присутствует и является валидным JWT, role="manager", expires_at через 24 часа от текущего момента

---

### AC-API-002: Неверный пароль возвращает 401
**Given** пользователь "victoria" существует
**When** POST /api/auth/login с body {"username": "victoria", "password": "wrongpass"}
**Then** ответ 401 Unauthorized, body содержит error_code="INVALID_CREDENTIALS"

---

### AC-API-003: Запрос без токена возвращает 401
**Given** GET /api/trips без заголовка Authorization
**When** запрос отправлен
**Then** ответ 401 Unauthorized, body содержит error_code="MISSING_TOKEN"

---

### AC-API-004: Просроченный токен возвращает 401
**Given** JWT-токен с exp в прошлом
**When** GET /api/trips с этим токеном в Authorization
**Then** ответ 401 Unauthorized, body содержит error_code="TOKEN_EXPIRED"

---

### AC-API-005: Viewer не может изменять алерты
**Given** пользователь с ролью "viewer" и валидным JWT
**When** PATCH /api/alerts/101 с body {"status": "reviewed", "reviewed_by": "test"}
**Then** ответ 403 Forbidden, body содержит error_code="INSUFFICIENT_PERMISSIONS"

---

### AC-API-006: Список рейсов с фильтром по заказчику
**Given** в БД 12 рейсов: 5 WB, 4 Тандер, 3 X5
**When** GET /api/trips?customer=WB
**Then** ответ 200, data содержит 5 объектов, все с customer="WB", pagination.total=5

---

### AC-API-007: Пагинация работает корректно
**Given** в БД 45 алертов
**When** GET /api/alerts?page=2&limit=20
**Then** ответ 200, data содержит 20 объектов (элементы 21-40), pagination.total=45, pagination.pages=3, pagination.page=2

---

### AC-API-008: HIGH-алерты идут первыми в ленте
**Given** в БД 3 алерта: LOW (created 12:00), HIGH (created 10:00), MEDIUM (created 11:00)
**When** GET /api/alerts (без фильтра severity, сортировка по умолчанию)
**Then** первый элемент в data — HIGH-алерт, затем MEDIUM, затем LOW

---

### AC-API-009: Статус алерта обновляется с фиксацией reviewed_by
**Given** алерт id=101 со status="new"
**When** PATCH /api/alerts/101 с body {"status": "reviewed", "reviewed_by": "Виктория"}
**Then** ответ 200, status="reviewed", reviewed_by="Виктория", reviewed_at — текущее время UTC
**And** повторный GET /api/alerts/{101} возвращает обновлённый статус

---

### AC-API-010: Переход из resolved недопустим
**Given** алерт id=102 со status="resolved"
**When** PATCH /api/alerts/102 с body {"status": "reviewed", "reviewed_by": "test"}
**Then** ответ 400 Bad Request, error_code="INVALID_STATUS_TRANSITION"

---

### AC-API-011: GET /api/trips/{trip_id} возвращает алерты и сообщения
**Given** рейс trip_id="4521" с 2 алертами и 18 сообщениями
**When** GET /api/trips/4521
**Then** ответ 200, trip.trip_id="4521", alerts.length=2, recent_messages.length=10 (последние 10 из 18)

---

### AC-API-012: Несуществующий рейс возвращает 404
**Given** рейс с trip_id="9999" не существует в БД
**When** GET /api/trips/9999
**Then** ответ 404 Not Found, error_code="TRIP_NOT_FOUND"

---

### AC-API-013: GET /api/stats возвращает корректные счётчики
**Given** за сегодня: 12 рейсов (8 активных), 15 алертов (2 HIGH), 187 сообщений
**When** GET /api/stats?period=today
**Then** ответ 200, trips.total=12, trips.active=8, alerts.total=15, alerts.high=2, messages.today=187

---

### AC-API-014: GET /api/stats/chart возвращает 24 точки для period=today
**Given** period=today, granularity=hour, metric=alerts
**When** GET /api/stats/chart?metric=alerts&period=today&granularity=hour
**Then** ответ 200, data.length=24 (по одной точке на каждый час дня), timestamp первой точки — 00:00 текущего дня UTC

---

### AC-API-015: GET /api/chats/{trip_id} возвращает сообщения по времени
**Given** рейс "4521" с 18 сообщениями от 06:15 до 22:10
**When** GET /api/chats/4521
**Then** ответ 200, data содержит сообщения в порядке timestamp ASC (от 06:15 к 22:10), pagination.total=18

---

### AC-API-016: GET /api/health возвращает состояние БД
**Given** PostgreSQL доступен
**When** GET /api/health без авторизации
**Then** ответ 200, status="ok", db="connected", uptime_seconds > 0

---

### AC-API-017: Фильтр по диапазону дат работает
**Given** алерты созданы 5-го марта (20 штук) и 6-го марта (25 штук)
**When** GET /api/alerts?date_from=2026-03-06T00:00:00Z&date_to=2026-03-06T23:59:59Z
**Then** ответ 200, pagination.total=25

---

## 6. Стратегия тестирования

### 6.1 Юнит-тесты (pytest)

**Тестируемые компоненты:** Pydantic-схемы, функции валидации, JWT-логика.

```python
# tests/test_auth.py
def test_create_jwt_token():
    """JWT создаётся с корректными полями"""
    token = create_jwt_token(username="victoria", role="manager")
    payload = decode_jwt_token(token)
    assert payload["sub"] == "victoria"
    assert payload["role"] == "manager"
    assert payload["exp"] > time.time()

def test_expired_jwt_raises():
    """Просроченный JWT вызывает исключение"""
    token = create_jwt_token(username="test", role="viewer", expires_delta=-1)
    with pytest.raises(JWTError, match="Token expired"):
        decode_jwt_token(token)

def test_pagination_params_validation():
    """page < 1 вызывает ValidationError"""
    with pytest.raises(ValidationError):
        PaginationParams(page=0, limit=20)

def test_pagination_limit_max():
    """limit > 100 вызывает ValidationError"""
    with pytest.raises(ValidationError):
        PaginationParams(page=1, limit=101)
```

### 6.2 Интеграционные тесты (pytest + httpx + TestClient)

**Тестируемые компоненты:** Все endpoint-ы с реальной тестовой БД PostgreSQL.

```python
# tests/test_api_integration.py
@pytest.mark.asyncio
async def test_login_success(client, test_user):
    response = await client.post("/api/auth/login", json={
        "username": "victoria",
        "password": "testpass"
    })
    assert response.status_code == 200
    assert "token" in response.json()
    assert response.json()["user"]["role"] == "manager"

@pytest.mark.asyncio
async def test_get_trips_requires_auth(client):
    response = await client.get("/api/trips")
    assert response.status_code == 401
    assert response.json()["error_code"] == "MISSING_TOKEN"

@pytest.mark.asyncio
async def test_get_trips_filter_customer(client, auth_headers, seed_trips):
    response = await client.get("/api/trips?customer=WB", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert all(t["customer"] == "WB" for t in data["data"])

@pytest.mark.asyncio
async def test_patch_alert_viewer_forbidden(client, viewer_headers, seed_alert):
    response = await client.patch(
        f"/api/alerts/{seed_alert['id']}",
        json={"status": "reviewed", "reviewed_by": "test"},
        headers=viewer_headers
    )
    assert response.status_code == 403

@pytest.mark.asyncio
async def test_patch_alert_resolved_to_reviewed_fails(client, manager_headers, resolved_alert):
    response = await client.patch(
        f"/api/alerts/{resolved_alert['id']}",
        json={"status": "reviewed", "reviewed_by": "test"},
        headers=manager_headers
    )
    assert response.status_code == 400
    assert response.json()["error_code"] == "INVALID_STATUS_TRANSITION"
```

### 6.3 Сценарные тесты (E2E)

| Сценарий | Шаги | Ожидаемый результат |
|----------|------|---------------------|
| **Полный цикл алерта** | 1. Алерт создан Alert Engine → 2. GET /api/alerts?status=new → 3. PATCH /api/alerts/{id} status=reviewed → 4. GET /api/alerts?status=reviewed | Алерт прошёл весь жизненный цикл, зафиксирован reviewed_by |
| **Polling каждые 3 сек** | 5 запросов GET /api/alerts подряд с интервалом 3 сек | Все 5 запросов вернули 200, данные актуальны |
| **Фильтр по заказчику + период** | GET /api/alerts?customer=WB&date_from=2026-03-06 | Только WB-алерты за сегодня |
| **Детали рейса с историей** | GET /api/trips/4521 → GET /api/chats/4521 | Рейс найден, 18 сообщений в хронологическом порядке |
| **Health check без авторизации** | GET /api/health | 200 OK, нет заголовка Authorization требуется |

### 6.4 Нагрузочное тестирование

Целевые параметры для Sprint 0 (2-3 одновременных пользователя дашборда):

| Метрика | Цель |
|---------|------|
| P95 latency GET /api/alerts | < 200 мс |
| P95 latency GET /api/trips | < 150 мс |
| P95 latency GET /api/stats | < 300 мс |
| Throughput при polling 3 сек x 3 пользователя | > 3 RPS без деградации |

---

## 7. Зависимости

### 7.1 Зависимости от других модулей системы

| Модуль | Интерфейс | Причина |
|--------|-----------|--------|
| **spec-data-schema.md** | Таблицы: trips, alerts, raw_messages, parsed_messages, dashboard_users | API читает данные из этих таблиц |
| **spec-tool-alert-engine.md** | Таблица alerts, поля: type, severity, status, rule_id | Alert Engine пишет алерты, API их читает |
| **spec-tool-chat-listener.md** | Таблица raw_messages | /api/chats/{trip_id} читает raw_messages |
| **spec-tool-ai-parser.md** | Таблица parsed_messages | Поле parsed в ChatMessage, recent_messages в /api/trips/{trip_id} |

### 7.2 Внешние технологические зависимости

| Зависимость | Версия | Назначение |
|-------------|--------|-----------|
| FastAPI | 0.109+ | Web-фреймворк, автогенерация OpenAPI docs |
| Pydantic | v2.5+ | Валидация request/response схем |
| asyncpg | 0.29+ | Асинхронный PostgreSQL-драйвер |
| python-jose | 3.3+ | JWT encode/decode (алгоритм HS256) |
| passlib[bcrypt] | 1.7+ | Проверка bcrypt-хеша пароля |
| python-json-logger | 2.0+ | Структурированное JSON-логирование |
| uvicorn | 0.27+ | ASGI-сервер для FastAPI |
| PostgreSQL | 15+ | База данных (читать из таблиц) |

### 7.3 Переменные окружения

| Переменная | Описание | Пример |
|------------|---------|--------|
| `DATABASE_URL` | asyncpg-совместимый URL PostgreSQL | `postgresql://user:pass@postgres:5432/marshall` |
| `JWT_SECRET_KEY` | Секретный ключ для подписи JWT (минимум 32 символа) | `super-secret-key-change-in-production` |
| `JWT_EXPIRE_HOURS` | Срок жизни JWT в часах | `24` |
| `API_HOST` | Хост FastAPI-сервера | `0.0.0.0` |
| `API_PORT` | Порт FastAPI-сервера | `8000` |
| `CORS_ORIGINS` | Допустимые CORS Origins (через запятую) | `http://localhost:3000,http://88.218.248.114` |
| `LOG_LEVEL` | Уровень логирования | `INFO` |

---

## 8. Примеры и граничные случаи

### 8.1 Пример 1: Полный flow авторизации и получения алертов

```bash
# Шаг 1: Получить JWT-токен
curl -X POST http://88.218.248.114:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "victoria", "password": "manager123"}' \
  | jq '.token'
# → "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."

# Шаг 2: Получить HIGH-алерты
curl -X GET "http://88.218.248.114:8000/api/alerts?severity=high&status=new&limit=10" \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
```

**Ожидаемый ответ:**
```json
{
  "data": [
    {
      "id": 105,
      "trip_id": "7803",
      "alert_type": "equipment_failure",
      "severity": "high",
      "message": "КРИТИЧНО: Нарушение температуры у Тандер 7803: Реф показывает +8",
      "customer": "Тандер",
      "status": "new",
      "created_at": "2026-03-06T07:45:00.000Z"
    }
  ],
  "pagination": { "total": 2, "page": 1, "limit": 10, "pages": 1 }
}
```

---

### 8.2 Пример 2: Просмотр и закрытие алерта

```bash
# Шаг 1: Отметить алерт как просмотренный
curl -X PATCH http://88.218.248.114:8000/api/alerts/105 \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"status": "reviewed", "reviewed_by": "Виктория Фимина"}'

# Ожидаемый ответ: 200 OK
# { "id": 105, "status": "reviewed", "reviewed_by": "Виктория Фимина", "reviewed_at": "..." }

# Шаг 2: После устранения проблемы — закрыть алерт
curl -X PATCH http://88.218.248.114:8000/api/alerts/105 \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"status": "resolved", "reviewed_by": "Виктория Фимина"}'
```

---

### 8.3 Пример 3: Статистика и данные для графика

```bash
# Сводная статистика за сегодня
curl "http://88.218.248.114:8000/api/stats?period=today" \
  -H "Authorization: Bearer <token>"

# График алертов за неделю (по дням)
curl "http://88.218.248.114:8000/api/stats/chart?metric=alerts&period=week&granularity=day" \
  -H "Authorization: Bearer <token>"
```

**Ожидаемый ответ для графика:**
```json
{
  "metric": "alerts",
  "period": "week",
  "granularity": "day",
  "data": [
    { "timestamp": "2026-02-28T00:00:00.000Z", "value": 8 },
    { "timestamp": "2026-03-01T00:00:00.000Z", "value": 12 },
    { "timestamp": "2026-03-02T00:00:00.000Z", "value": 5 },
    { "timestamp": "2026-03-03T00:00:00.000Z", "value": 15 },
    { "timestamp": "2026-03-04T00:00:00.000Z", "value": 3 },
    { "timestamp": "2026-03-05T00:00:00.000Z", "value": 7 },
    { "timestamp": "2026-03-06T00:00:00.000Z", "value": 15 }
  ],
  "summary": { "total": 65, "peak_value": 15, "peak_timestamp": "2026-03-06T00:00:00.000Z" }
}
```

---

### 8.4 Пример 4: История чата по рейсу

```bash
curl "http://88.218.248.114:8000/api/chats/4521" \
  -H "Authorization: Bearer <token>"
```

**Ожидаемый ответ (сокращённый):**
```json
{
  "trip_id": "4521",
  "data": [
    {
      "id": 5001,
      "sender_name": "Диспетчер Алексей",
      "text": "Рейс 4521, Москва-Краснодар, слот на погрузку WB 14:00...",
      "timestamp": "2026-03-06T06:15:00.000Z",
      "parsed": { "trip_id": "4521", "status": "assigned", "urgency": "low", "confidence": 0.95 }
    },
    {
      "id": 5003,
      "sender_name": "Водитель Иван",
      "text": "Стою в пробке на МКАД, опаздываю минут на 40",
      "timestamp": "2026-03-06T08:30:00.000Z",
      "parsed": { "trip_id": "4521", "status": "problem", "urgency": "medium", "issue": "Опоздание 40 мин", "confidence": 0.87 }
    }
  ],
  "pagination": { "total": 18, "page": 1, "limit": 50, "pages": 1 }
}
```

---

### 8.5 Граничный случай 1: Пустой список (нет данных за период)

```bash
curl "http://88.218.248.114:8000/api/alerts?date_from=2026-01-01&date_to=2026-01-02" \
  -H "Authorization: Bearer <token>"
```

**Ожидаемый ответ:** 200 OK (не 404)
```json
{
  "data": [],
  "pagination": { "total": 0, "page": 1, "limit": 20, "pages": 0 }
}
```

---

### 8.6 Граничный случай 2: Рейс без парсированных данных

Рейс может существовать в таблице trips, но не иметь связанных записей в parsed_messages (если парсер ещё не обработал сообщения). В этом случае:
- GET /api/trips/{trip_id} — возвращает trip с alerts=[] и recent_messages=[]
- GET /api/chats/{trip_id} — возвращает пустой data=[]
- **Не** возвращает 404

---

### 8.7 Граничный случай 3: Информационный алерт без trip_id

Некоторые алерты создаются Alert Engine без привязки к рейсу (например, ДТП на трассе). В API:
- GET /api/alerts возвращает их с trip_id=null
- GET /api/trips/{trip_id} — такие алерты не включаются в alerts рейса
- PATCH /api/alerts/{id} работает для них как обычно

```json
{
  "id": 120,
  "trip_id": null,
  "alert_type": "downtime",
  "severity": "medium",
  "message": "Инцидент на трассе М4 Дон км 680 — возможны задержки",
  "customer": null,
  "status": "new",
  "created_at": "2026-03-06T10:30:00.000Z"
}
```

---

### 8.8 Граничный случай 4: Превышение лимита пагинации

```bash
curl "http://88.218.248.114:8000/api/alerts?limit=200" \
  -H "Authorization: Bearer <token>"
```

**Ожидаемый ответ:** 422 Unprocessable Entity
```json
{
  "error_code": "VALIDATION_ERROR",
  "message": "Параметр limit не может превышать 100",
  "details": { "field": "limit", "value": 200, "max": 100 },
  "request_id": "req-abc123"
}
```

---

### 8.9 Граничный случай 5: Неверный формат даты

```bash
curl "http://88.218.248.114:8000/api/trips?date_from=06.03.2026" \
  -H "Authorization: Bearer <token>"
```

**Ожидаемый ответ:** 400 Bad Request
```json
{
  "error_code": "INVALID_DATE_FORMAT",
  "message": "Параметр date_from должен быть в формате ISO 8601 (YYYY-MM-DD или YYYY-MM-DDTHH:MM:SSZ)",
  "details": { "field": "date_from", "value": "06.03.2026" },
  "request_id": "req-def456"
}
```

---

### 8.10 Граничный случай 6: Деактивированный пользователь

```bash
curl -X POST http://88.218.248.114:8000/api/auth/login \
  -d '{"username": "deactivated_user", "password": "correctpass"}'
```

**Ожидаемый ответ:** 403 Forbidden
```json
{
  "error_code": "ACCOUNT_DISABLED",
  "message": "Учётная запись деактивирована. Обратитесь к администратору.",
  "request_id": "req-ghi789"
}
```

---

## Приложение А: Каталог кодов ошибок

| error_code | HTTP | Условие |
|------------|------|---------|
| MISSING_TOKEN | 401 | Заголовок Authorization отсутствует |
| INVALID_TOKEN | 401 | Неверная подпись JWT |
| TOKEN_EXPIRED | 401 | JWT просрочен |
| INVALID_CREDENTIALS | 401 | Неверный логин или пароль |
| ACCOUNT_DISABLED | 403 | is_active=false в dashboard_users |
| INSUFFICIENT_PERMISSIONS | 403 | Роль не позволяет выполнить операцию |
| TRIP_NOT_FOUND | 404 | trips.trip_id не найден |
| ALERT_NOT_FOUND | 404 | alerts.id не найден |
| INVALID_STATUS_TRANSITION | 400 | Недопустимый переход статуса алерта |
| INVALID_DATE_FORMAT | 400 | date_from или date_to в неверном формате |
| VALIDATION_ERROR | 422 | Ошибка валидации параметров (Pydantic) |
| DATABASE_ERROR | 500 | Ошибка запроса к PostgreSQL |
| INTERNAL_ERROR | 500 | Непредвиденная внутренняя ошибка |

---

## Приложение Б: Структура проекта FastAPI

```
marshall-listener/
├── api/
│   ├── __init__.py
│   ├── main.py                 # FastAPI app, CORS, middleware, роутеры
│   ├── deps.py                 # Зависимости: get_db(), get_current_user()
│   ├── auth.py                 # JWT: create_token, verify_token, get_password_hash
│   ├── models/
│   │   ├── trip.py             # Pydantic-схемы Trip
│   │   ├── alert.py            # Pydantic-схемы Alert
│   │   ├── stats.py            # Pydantic-схемы Stats, ChartData
│   │   ├── chat.py             # Pydantic-схемы ChatMessage
│   │   └── common.py           # PaginationParams, ErrorResponse
│   └── routers/
│       ├── auth.py             # POST /api/auth/login
│       ├── trips.py            # GET /api/trips, GET /api/trips/{trip_id}
│       ├── alerts.py           # GET /api/alerts, PATCH /api/alerts/{id}
│       ├── stats.py            # GET /api/stats, GET /api/stats/chart
│       ├── chats.py            # GET /api/chats/{trip_id}
│       └── health.py           # GET /api/health
├── db/
│   ├── connection.py           # asyncpg pool, get_connection()
│   └── queries/
│       ├── trips.py            # SQL-запросы для trips
│       ├── alerts.py           # SQL-запросы для alerts
│       ├── stats.py            # SQL-запросы для stats
│       └── chats.py            # SQL-запросы для чатов
└── tests/
    ├── conftest.py             # Fixtures: test_db, client, auth_headers
    ├── test_auth.py
    ├── test_trips.py
    ├── test_alerts.py
    ├── test_stats.py
    └── test_chats.py
```

---

*Документ создан: 2026-03-06. Версия: 1.0. Статус: ГОТОВО К РЕАЛИЗАЦИИ.*
