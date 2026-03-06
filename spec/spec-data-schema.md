---
title: Marshall AI Listener -- Спецификация схемы данных
version: "1.0"
date_created: 2026-03-06
owner: Тим Зинин (Zinin Corp)
tags: [schema, database, postgresql]
depends_on: [master_brief.md, product_brief.md, spec-v1.yaml]
sprint: "Sprint 0"
module: data-schema
---

# Marshall AI Listener -- Спецификация схемы данных

## 1. Цель и скоуп

### 1.1 Цель

Определить полную схему базы данных PostgreSQL для системы Marshall AI Listener (Sprint 0), обеспечивающую хранение сырых сообщений из диспетчерских чатов, результатов LLM-парсинга, алертов, агрегированных данных по рейсам и пользователей дашборда.

### 1.2 Скоуп

Схема покрывает четыре модуля Sprint 0:

| Модуль | Таблицы | Назначение |
|--------|---------|-----------|
| Chat Listener (S0-F01) | `raw_messages` | Сырые текстовые сообщения из Telegram-чатов |
| AI Parser (S0-F02) | `parsed_messages` | Структурированные данные, извлечённые LLM |
| Alert Engine (S0-F03) | `alerts` | Критические события, обнаруженные по правилам |
| Dashboard (S0-F04) | `trips`, `dashboard_users` | Агрегированные рейсы и авторизация |

### 1.3 Границы

**Входит в скоуп:**
- 5 таблиц, перечисленных в модульном брифе
- Индексы для типичных запросов дашборда
- CHECK-ограничения для бизнес-правил
- Миграционные SQL-файлы (plain SQL, без ORM/Alembic)
- Seed data для 3 тестовых чатов

**Выходит из скоупа (отложено на Sprint 1+):**
- Таблицы Sprint 1: `users`, `trip_assignments`, `checklist_responses`, `status_events`, `shift_schedules`, `documents`, `customer_memos`, `guides`
- Партиционирование таблиц (оценить после 3 месяцев эксплуатации)
- Read-реплики и шардинг
- Полнотекстовый поиск (GIN-индексы по `text`)
- Хранение медиафайлов (MinIO/S3 -- отдельный сервис)

---

## 2. Определения

| Термин | Описание |
|--------|----------|
| **PostgreSQL** | Реляционная СУБД, версия 15+. Используется вместо SQLite для масштаба 500+ партнёров |
| **TIMESTAMPTZ** | Тип данных PostgreSQL `TIMESTAMP WITH TIME ZONE`. Все временные метки хранятся в UTC |
| **BIGSERIAL** | Автоинкрементный 64-битный целочисленный тип для первичных ключей |
| **FK** | Foreign Key -- внешний ключ, обеспечивающий ссылочную целостность между таблицами |
| **Индекс** | Структура данных для ускорения поиска по столбцам. B-tree по умолчанию |
| **Миграция** | SQL-скрипт, изменяющий схему БД. Нумерация: `001_`, `002_`, ... Идемпотентный |
| **trip_id** | Идентификатор рейса в системе Marshall (например, "4521"). Извлекается LLM из текста |
| **confidence** | Уверенность LLM в результате парсинга. Диапазон 0.0--1.0 |
| **severity** | Критичность алерта: `high` (блокирует рейс), `medium` (требует внимания), `low` (информационный) |
| **raw_message** | Исходное текстовое сообщение из чата, без обработки |
| **parsed_message** | Результат парсинга raw_message через LLM -- структурированные поля |
| **CHECK constraint** | Ограничение уровня строки, проверяющее допустимость значений при вставке/обновлении |
| **seed data** | Тестовые данные для разработки и демонстрации. Не для продакшна |

---

## 3. Требования, ограничения и рекомендации

### 3.1 Требования

| ID | Категория | Описание | Приоритет |
|----|-----------|----------|-----------|
| REQ-DS-001 | Хранение | Все сырые сообщения из мониторимых чатов сохраняются в `raw_messages` с метаданными отправителя, чата и временной меткой | MUST |
| REQ-DS-002 | Уникальность | `message_id` в `raw_messages` уникален -- защита от дублирования при переподключении Telethon | MUST |
| REQ-DS-003 | Парсинг | Каждый результат LLM-парсинга привязан к исходному сообщению через FK `raw_message_id` | MUST |
| REQ-DS-004 | Допустимые значения | Поля `status`, `urgency`, `severity`, `alert type` ограничены фиксированными наборами через CHECK constraints | MUST |
| REQ-DS-005 | Агрегация | Таблица `trips` агрегирует данные из `parsed_messages` по `trip_id`, обновляясь при каждом новом сообщении по рейсу | MUST |
| REQ-DS-006 | Индексация | Индексы на столбцах, используемых в фильтрах дашборда: `chat_id`, `trip_id`, `customer`, `severity`, `status`, `timestamp` | MUST |
| REQ-DS-007 | Временные зоны | Все временные метки хранятся в типе `TIMESTAMPTZ` (UTC). Приложение конвертирует в MSK (UTC+3) при отображении | MUST |
| REQ-DS-008 | Каскадное удаление | При удалении `raw_message` каскадно удаляются связанные `parsed_messages`. При удалении `parsed_message` каскадно удаляются связанные `alerts` | SHOULD |
| REQ-DS-009 | Авторизация | Таблица `dashboard_users` хранит bcrypt-хеш пароля и роль пользователя | MUST |
| REQ-DS-010 | Аудит | Все таблицы содержат поле `created_at` с автоматическим заполнением `DEFAULT NOW()`. Таблица `alerts` дополнительно содержит `reviewed_at` для аудита обработки | MUST |
| REQ-DS-011 | Метрики LLM | `parsed_messages` хранит модель LLM, количество потреблённых токенов и длительность парсинга в миллисекундах для контроля расходов | SHOULD |
| REQ-DS-012 | Масштаб | Схема рассчитана на 500+ партнёров, тысячи сообщений/день. Типы данных выбраны с запасом (BIGSERIAL, TEXT) | MUST |
| REQ-DS-013 | Миграции | Схема поставляется как plain SQL миграции (без Alembic/ORM). Каждая миграция идемпотентна (`IF NOT EXISTS`) | MUST |
| REQ-DS-014 | Тестовые данные | Seed data покрывает 3 тестовых чата (WB, Тандер, Общая Диспетчерская) с реалистичными сценариями из master_brief | SHOULD |

### 3.2 Ограничения

| ID | Описание |
|----|----------|
| CON-DS-001 | PostgreSQL 15+ -- минимальная поддерживаемая версия |
| CON-DS-002 | Деплой через Docker Compose на RUVDS (88.218.248.114). Образ `postgres:15` |
| CON-DS-003 | Sprint 0 -- без ORM. Запросы через `asyncpg` (асинхронный драйвер) или `psycopg2` |
| CON-DS-004 | Sprint 0 -- без партиционирования. Единая таблица `raw_messages` (оценить после 100K записей) |
| CON-DS-005 | Sprint 0 -- без полнотекстового поиска. Поиск по `text` через `LIKE` или приложение |
| CON-DS-006 | Авторизация дашборда -- простой пароль (bcrypt), без OAuth/SSO |
| CON-DS-007 | Нет хранения медиафайлов в БД. Поле `media_type` зарезервировано для Sprint 1 |
| CON-DS-008 | Часовой пояс по умолчанию -- UTC. Бизнес-логика отображения в MSK (UTC+3) на уровне API |

### 3.3 Рекомендации

| ID | Описание | Обоснование |
|----|----------|-------------|
| REC-DS-001 | Использовать `BIGSERIAL` для PK вместо UUID | Компактнее, быстрее для JOIN, достаточно для однопроцессной системы Sprint 0 |
| REC-DS-002 | CHECK constraints вместо ENUM types | Проще мигрировать (ALTER TABLE vs DROP/CREATE TYPE). Допустимые значения явно видны в DDL |
| REC-DS-003 | Индексы создавать с `CONCURRENTLY` в продакшне | Не блокирует таблицу. В миграции Sprint 0 допустимо без CONCURRENTLY (пустая БД) |
| REC-DS-004 | Рассмотреть партиционирование `raw_messages` по месяцам после 3 месяцев | При объёме >1M строк. Партиция по `timestamp` (RANGE) |
| REC-DS-005 | Добавить `updated_at` с триггером на `trips` | Отслеживание последнего обновления агрегата без ручного управления |
| REC-DS-006 | Использовать connection pool (pgbouncer или asyncpg pool) | FastAPI + asyncio -> конкурентные подключения. Pool size: 10-20 |

---

## 4. Интерфейсы и контракты данных

### 4.1 ER-диаграмма (текстовое описание)

```
raw_messages (1) ----< (N) parsed_messages (1) ----< (N) alerts
     |                           |
     |                           |
     |                     trips (агрегат по trip_id,
     |                      обновляется из parsed_messages)
     |
     +-- dashboard_users (независимая таблица)
```

**Связи:**

- `raw_messages` 1:N `parsed_messages` -- одно сообщение может быть распаршено повторно (при ошибке или обновлении промпта)
- `parsed_messages` 1:N `alerts` -- одно распаршенное сообщение может породить несколько алертов (например, и опоздание, и поломка)
- `trips` агрегируется из `parsed_messages` по полю `trip_id` -- нет FK, связь логическая через значение `trip_id`
- `dashboard_users` -- независимая таблица, не связана FK с остальными

### 4.2 Полные CREATE TABLE statements

#### 4.2.1 Таблица `raw_messages`

Хранит все сырые текстовые сообщения из мониторимых Telegram-чатов. Одна строка = одно сообщение.

```sql
CREATE TABLE IF NOT EXISTS raw_messages (
    -- Первичный ключ
    id              BIGSERIAL       PRIMARY KEY,

    -- Идентификаторы Telegram
    chat_id         BIGINT          NOT NULL,           -- ID чата Telegram
    chat_name       VARCHAR(255),                       -- Название чата (для отображения)
    sender_id       BIGINT,                             -- ID отправителя (NULL для системных)
    sender_name     VARCHAR(255),                       -- Имя отправителя (для отображения)
    message_id      BIGINT          NOT NULL UNIQUE,    -- Telegram message_id, защита от дублей

    -- Содержимое
    text            TEXT            NOT NULL,            -- Текст сообщения

    -- Метаданные
    timestamp       TIMESTAMPTZ     NOT NULL,            -- Время отправки сообщения (из Telegram)
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW() -- Время записи в БД
);

-- Комментарии к таблице
COMMENT ON TABLE  raw_messages IS 'Сырые текстовые сообщения из Telegram-чатов диспетчеров';
COMMENT ON COLUMN raw_messages.chat_id IS 'Telegram chat ID. Отрицательный для групповых чатов';
COMMENT ON COLUMN raw_messages.message_id IS 'Уникальный Telegram message_id. Предотвращает дубли при переподключении';
COMMENT ON COLUMN raw_messages.timestamp IS 'Время отправки сообщения в Telegram (UTC)';
COMMENT ON COLUMN raw_messages.created_at IS 'Время записи сообщения в БД (UTC). Может отличаться от timestamp при пакетной загрузке';
```

#### 4.2.2 Таблица `parsed_messages`

Результаты LLM-парсинга. Каждая строка -- результат обработки одного сырого сообщения.

```sql
CREATE TABLE IF NOT EXISTS parsed_messages (
    -- Первичный ключ
    id                  BIGSERIAL       PRIMARY KEY,

    -- Связь с исходным сообщением
    raw_message_id      BIGINT          NOT NULL
                        REFERENCES raw_messages(id) ON DELETE CASCADE,

    -- Извлечённые поля рейса
    trip_id             VARCHAR(50),                    -- Номер рейса (NULL если не распознан)
    route_from          VARCHAR(255),                   -- Пункт отправления
    route_to            VARCHAR(255),                   -- Пункт назначения
    slot_time           TIME,                           -- Время слота погрузки/выгрузки (только время, без даты)

    -- Классификация
    status              VARCHAR(30)
                        CHECK (status IN (
                            'assigned',       -- Рейс назначен
                            'in_transit',     -- В пути
                            'loading',        -- Погрузка
                            'unloading',      -- Выгрузка
                            'completed',      -- Рейс завершён
                            'problem',        -- Проблема
                            'cancelled'       -- Рейс отменён
                        )),
    customer            VARCHAR(100),                   -- Заказчик (Тандер, WB, X5, Магнит, Сельта, Сибур)
    urgency             VARCHAR(10)     NOT NULL DEFAULT 'low'
                        CHECK (urgency IN ('low', 'medium', 'high')),
    issue               TEXT,                           -- Описание проблемы (NULL если нет)

    -- Метрики LLM
    confidence          REAL            NOT NULL DEFAULT 0.0
                        CHECK (confidence >= 0.0 AND confidence <= 1.0),
    llm_model           VARCHAR(50),                    -- Модель: 'minimax' или 'groq'
    llm_tokens_used     INTEGER         CHECK (llm_tokens_used IS NULL OR llm_tokens_used >= 0),
    parse_duration_ms   INTEGER         CHECK (parse_duration_ms IS NULL OR parse_duration_ms >= 0),

    -- Метаданные
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE  parsed_messages IS 'Результаты LLM-парсинга сырых сообщений. Структурированные логистические данные';
COMMENT ON COLUMN parsed_messages.trip_id IS 'Номер рейса, извлечённый LLM. NULL если не распознан';
COMMENT ON COLUMN parsed_messages.slot_time IS 'Время слота (TIME без даты). Дата определяется из контекста сообщения';
COMMENT ON COLUMN parsed_messages.confidence IS 'Уверенность LLM в парсинге. 0.0 = не уверен, 1.0 = полная уверенность. Порог для алертов: 0.7';
COMMENT ON COLUMN parsed_messages.llm_model IS 'Какая LLM использовалась: minimax (основная) или groq (fallback)';
COMMENT ON COLUMN parsed_messages.parse_duration_ms IS 'Время парсинга в миллисекундах. Для мониторинга latency (цель: <5000 мс)';
```

#### 4.2.3 Таблица `alerts`

Алерты, созданные Alert Engine на основе распаршенных сообщений и бизнес-правил.

```sql
CREATE TABLE IF NOT EXISTS alerts (
    -- Первичный ключ
    id                  BIGSERIAL       PRIMARY KEY,

    -- Привязка к рейсу и источнику
    trip_id             VARCHAR(50),                    -- Номер рейса (может быть NULL для общих алертов)
    parsed_message_id   BIGINT          NOT NULL
                        REFERENCES parsed_messages(id) ON DELETE CASCADE,

    -- Классификация алерта
    type                VARCHAR(30)     NOT NULL
                        CHECK (type IN (
                            'delay',              -- Опоздание
                            'equipment_failure',  -- Поломка оборудования (реф, компрессор)
                            'downtime',           -- Простой (превышение допустимого)
                            'safety_violation',   -- Нарушение техники безопасности
                            'docs_missing'        -- Отсутствие документов
                        )),
    severity            VARCHAR(10)     NOT NULL
                        CHECK (severity IN ('high', 'medium', 'low')),
    message             TEXT            NOT NULL,        -- Человекочитаемое описание алерта

    -- Контекст
    customer            VARCHAR(100),                    -- Заказчик (для правил, специфичных заказчику)
    rule_id             VARCHAR(50),                     -- ID правила из конфигурации (напр. 'X5_NO_IDLE')

    -- Жизненный цикл
    status              VARCHAR(15)     NOT NULL DEFAULT 'new'
                        CHECK (status IN ('new', 'reviewed', 'resolved')),
    reviewed_by         VARCHAR(100),                    -- Имя пользователя, обработавшего алерт
    reviewed_at         TIMESTAMPTZ,                     -- Время обработки

    -- Метаданные
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE  alerts IS 'Алерты о критических событиях. Отображаются в дашборде. Sprint 0 -- без отправки в Telegram';
COMMENT ON COLUMN alerts.type IS 'Тип алерта. 5 категорий: delay, equipment_failure, downtime, safety_violation, docs_missing';
COMMENT ON COLUMN alerts.severity IS 'high = блокирует рейс (штраф), medium = требует внимания, low = информационный';
COMMENT ON COLUMN alerts.rule_id IS 'Ссылка на правило из конфигурации Alert Engine (YAML). Например: DELAY_GT_4H, X5_NO_IDLE, REEFER_TEMP';
COMMENT ON COLUMN alerts.status IS 'Жизненный цикл: new -> reviewed (менеджер увидел) -> resolved (проблема закрыта)';
```

#### 4.2.4 Таблица `trips`

Агрегированные данные по рейсам. Собирается и обновляется из `parsed_messages` при каждом новом сообщении, содержащем `trip_id`.

```sql
CREATE TABLE IF NOT EXISTS trips (
    -- Первичный ключ
    id                  BIGSERIAL       PRIMARY KEY,

    -- Идентификатор рейса
    trip_id             VARCHAR(50)     NOT NULL UNIQUE, -- Номер рейса (из парсинга)

    -- Маршрут
    route_from          VARCHAR(255),                    -- Пункт отправления
    route_to            VARCHAR(255),                    -- Пункт назначения

    -- Участники
    customer            VARCHAR(100),                    -- Заказчик
    driver_name         VARCHAR(255),                    -- Имя водителя (из sender_name)
    dispatcher_name     VARCHAR(255),                    -- Имя диспетчера (из sender_name)

    -- Статус и тайминги
    status              VARCHAR(30)     NOT NULL DEFAULT 'assigned'
                        CHECK (status IN (
                            'assigned',
                            'in_transit',
                            'loading',
                            'unloading',
                            'completed',
                            'problem',
                            'cancelled'
                        )),
    slot_time           TIMESTAMPTZ,                     -- Плановое время слота (дата + время)
    departure_time      TIMESTAMPTZ,                     -- Фактическое время выезда
    arrival_time        TIMESTAMPTZ,                     -- Фактическое время прибытия

    -- Счётчики
    alert_count         INTEGER         NOT NULL DEFAULT 0
                        CHECK (alert_count >= 0),

    -- Метаданные
    last_update         TIMESTAMPTZ,                     -- Время последнего обновления из parsed_messages
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE  trips IS 'Агрегированные данные по рейсам. Обновляется при каждом новом parsed_message с trip_id';
COMMENT ON COLUMN trips.trip_id IS 'Номер рейса Marshall (напр. 4521). Уникален. Источник -- LLM-парсинг';
COMMENT ON COLUMN trips.alert_count IS 'Количество алертов по рейсу. Инкрементируется при создании алерта';
COMMENT ON COLUMN trips.last_update IS 'Время последнего обновления агрегата. Для определения "устаревших" рейсов на дашборде';
COMMENT ON COLUMN trips.updated_at IS 'Автоматически обновляется триггером при любом изменении строки';
```

#### 4.2.5 Таблица `dashboard_users`

Пользователи веб-дашборда. Простая авторизация без OAuth.

```sql
CREATE TABLE IF NOT EXISTS dashboard_users (
    -- Первичный ключ
    id                  SERIAL          PRIMARY KEY,

    -- Учётные данные
    username            VARCHAR(100)    NOT NULL UNIQUE,
    password_hash       VARCHAR(255)    NOT NULL,        -- bcrypt hash

    -- Роль
    role                VARCHAR(20)     NOT NULL DEFAULT 'viewer'
                        CHECK (role IN ('admin', 'manager', 'viewer')),

    -- Метаданные
    is_active           BOOLEAN         NOT NULL DEFAULT TRUE,
    last_login_at       TIMESTAMPTZ,
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE  dashboard_users IS 'Пользователи веб-дашборда. Простая авторизация bcrypt. Sprint 0 -- без OAuth';
COMMENT ON COLUMN dashboard_users.password_hash IS 'bcrypt hash пароля. Длина 60 символов для bcrypt, 255 с запасом';
COMMENT ON COLUMN dashboard_users.role IS 'admin = полный доступ, manager = просмотр + управление алертами, viewer = только просмотр';
```

### 4.3 Индексы

```sql
-- =============================================================================
-- raw_messages: поиск по чату и временному диапазону
-- =============================================================================
CREATE INDEX IF NOT EXISTS idx_raw_messages_chat_id
    ON raw_messages (chat_id);

CREATE INDEX IF NOT EXISTS idx_raw_messages_timestamp
    ON raw_messages (timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_raw_messages_chat_timestamp
    ON raw_messages (chat_id, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_raw_messages_sender_id
    ON raw_messages (sender_id)
    WHERE sender_id IS NOT NULL;

-- =============================================================================
-- parsed_messages: поиск по trip_id, customer, status
-- =============================================================================
CREATE INDEX IF NOT EXISTS idx_parsed_messages_raw_message_id
    ON parsed_messages (raw_message_id);

CREATE INDEX IF NOT EXISTS idx_parsed_messages_trip_id
    ON parsed_messages (trip_id)
    WHERE trip_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_parsed_messages_customer
    ON parsed_messages (customer)
    WHERE customer IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_parsed_messages_status
    ON parsed_messages (status)
    WHERE status IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_parsed_messages_created_at
    ON parsed_messages (created_at DESC);

-- =============================================================================
-- alerts: поиск по severity, status, trip_id, customer
-- =============================================================================
CREATE INDEX IF NOT EXISTS idx_alerts_severity
    ON alerts (severity);

CREATE INDEX IF NOT EXISTS idx_alerts_status
    ON alerts (status);

CREATE INDEX IF NOT EXISTS idx_alerts_trip_id
    ON alerts (trip_id)
    WHERE trip_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_alerts_customer
    ON alerts (customer)
    WHERE customer IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_alerts_created_at
    ON alerts (created_at DESC);

-- Составной индекс: активные HIGH-алерты (основной запрос дашборда)
CREATE INDEX IF NOT EXISTS idx_alerts_active_high
    ON alerts (severity, created_at DESC)
    WHERE status = 'new';

CREATE INDEX IF NOT EXISTS idx_alerts_parsed_message_id
    ON alerts (parsed_message_id);

-- =============================================================================
-- trips: поиск по trip_id, customer, status
-- =============================================================================
-- trip_id уже имеет UNIQUE constraint -> автоматический индекс

CREATE INDEX IF NOT EXISTS idx_trips_customer
    ON trips (customer)
    WHERE customer IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_trips_status
    ON trips (status);

CREATE INDEX IF NOT EXISTS idx_trips_created_at
    ON trips (created_at DESC);

-- Составной индекс: активные рейсы для дашборда
CREATE INDEX IF NOT EXISTS idx_trips_active
    ON trips (status, last_update DESC)
    WHERE status NOT IN ('completed', 'cancelled');
```

### 4.4 Триггер автообновления `updated_at`

```sql
-- Функция триггера для автоматического обновления updated_at
CREATE OR REPLACE FUNCTION trigger_set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Триггер на таблице trips
CREATE TRIGGER trg_trips_updated_at
    BEFORE UPDATE ON trips
    FOR EACH ROW
    EXECUTE FUNCTION trigger_set_updated_at();
```

### 4.5 Контракты данных между модулями

#### Chat Listener -> raw_messages

Listener записывает строку при каждом новом сообщении из Telegram:

```python
# Контракт вставки (asyncpg)
INSERT INTO raw_messages (chat_id, chat_name, sender_id, sender_name, message_id, text, timestamp)
VALUES ($1, $2, $3, $4, $5, $6, $7)
ON CONFLICT (message_id) DO NOTHING  -- Идемпотентность при переподключении
RETURNING id
```

#### AI Parser -> parsed_messages

Parser читает из `raw_messages`, парсит через LLM, записывает результат:

```python
# Контракт чтения (необработанные сообщения)
SELECT id, text, chat_name, sender_name, timestamp
FROM raw_messages
WHERE id NOT IN (SELECT raw_message_id FROM parsed_messages)
ORDER BY timestamp ASC
LIMIT 100

# Контракт вставки
INSERT INTO parsed_messages
    (raw_message_id, trip_id, route_from, route_to, slot_time,
     status, customer, urgency, issue, confidence,
     llm_model, llm_tokens_used, parse_duration_ms)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
RETURNING id
```

#### Alert Engine -> alerts

Alert Engine читает из `parsed_messages`, применяет правила, создаёт алерты:

```python
# Контракт чтения (новые parsed_messages с проблемами)
SELECT pm.id, pm.trip_id, pm.status, pm.customer, pm.urgency, pm.issue,
       pm.confidence, rm.text, rm.chat_name, rm.sender_name
FROM parsed_messages pm
JOIN raw_messages rm ON rm.id = pm.raw_message_id
WHERE pm.id > $1  -- last_processed_id
  AND pm.confidence >= 0.7
  AND (pm.urgency IN ('medium', 'high') OR pm.status = 'problem')
ORDER BY pm.id ASC

# Контракт вставки
INSERT INTO alerts
    (trip_id, parsed_message_id, type, severity, message, customer, rule_id)
VALUES ($1, $2, $3, $4, $5, $6, $7)
RETURNING id
```

#### Dashboard API -> trips, alerts

Dashboard читает агрегированные данные для отображения:

```python
# Активные рейсы
SELECT t.trip_id, t.route_from, t.route_to, t.customer, t.status,
       t.driver_name, t.slot_time, t.alert_count, t.last_update
FROM trips t
WHERE t.status NOT IN ('completed', 'cancelled')
ORDER BY t.last_update DESC

# Активные алерты (лента)
SELECT a.id, a.trip_id, a.type, a.severity, a.message, a.customer,
       a.status, a.created_at, a.reviewed_by, a.reviewed_at
FROM alerts a
WHERE a.created_at >= $1  -- фильтр по дате
ORDER BY
    CASE a.severity WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END,
    a.created_at DESC

# Статистика за период
SELECT
    COUNT(DISTINCT t.trip_id) AS total_trips,
    COUNT(DISTINCT t.trip_id) FILTER (WHERE t.status = 'completed') AS completed_trips,
    COUNT(a.id) AS total_alerts,
    COUNT(a.id) FILTER (WHERE a.severity = 'high') AS high_alerts,
    AVG(EXTRACT(EPOCH FROM (t.arrival_time - t.departure_time)) / 3600)
        FILTER (WHERE t.departure_time IS NOT NULL AND t.arrival_time IS NOT NULL) AS avg_transit_hours
FROM trips t
LEFT JOIN alerts a ON a.trip_id = t.trip_id
WHERE t.created_at BETWEEN $1 AND $2
```

---

## 5. Критерии приёмки

| ID | Критерий |
|----|----------|
| AC-DS-001 | **Given** Chat Listener получает новое сообщение из Telegram, **When** Listener выполняет INSERT в `raw_messages`, **Then** строка создаётся с заполненными `chat_id`, `message_id`, `text`, `timestamp`; повторная вставка того же `message_id` не вызывает ошибку (ON CONFLICT DO NOTHING) |
| AC-DS-002 | **Given** AI Parser обработал сообщение через LLM, **When** Parser выполняет INSERT в `parsed_messages`, **Then** строка содержит валидный `raw_message_id` (FK), `confidence` в диапазоне 0.0--1.0, `status` из допустимого набора |
| AC-DS-003 | **Given** `parsed_messages` содержит запись со `status = 'problem'` и `confidence >= 0.7`, **When** Alert Engine обрабатывает эту запись, **Then** создаётся запись в `alerts` с `type`, `severity`, `message`; `status` алерта = 'new' |
| AC-DS-004 | **Given** дашборд запрашивает активные рейсы, **When** API выполняет SELECT из `trips` с фильтром по `status` и `customer`, **Then** ответ возвращается за время <100 мс благодаря индексам `idx_trips_active` и `idx_trips_customer` |
| AC-DS-005 | **Given** менеджер отмечает алерт как 'reviewed' в дашборде, **When** API выполняет UPDATE `alerts SET status = 'reviewed'`, **Then** поля `reviewed_by` и `reviewed_at` заполняются; алерт перестаёт отображаться в ленте 'new' |
| AC-DS-006 | **Given** пользователь дашборда вводит логин и пароль, **When** API проверяет credentials, **Then** `password_hash` сверяется через bcrypt; при успехе записывается `last_login_at`; при неверном пароле -- отказ без раскрытия причины |
| AC-DS-007 | **Given** `parsed_messages` содержит запись с `trip_id = '4521'`, **When** агрегатор обновляет `trips`, **Then** строка в `trips` с `trip_id = '4521'` обновляется: `status`, `last_update`, `alert_count` актуальны; если строки нет -- создаётся (UPSERT) |
| AC-DS-008 | **Given** запись в `raw_messages` удаляется, **When** CASCADE срабатывает, **Then** все связанные `parsed_messages` удаляются; все связанные `alerts` удаляются каскадно через `parsed_messages` |
| AC-DS-009 | **Given** попытка вставить `parsed_messages` со `status = 'unknown_value'`, **When** INSERT выполняется, **Then** PostgreSQL возвращает ошибку CHECK constraint violation |
| AC-DS-010 | **Given** миграция `001_initial_schema.sql` применяется к пустой БД, **When** скрипт выполняется повторно, **Then** ошибок нет (все CREATE используют IF NOT EXISTS). Все 5 таблиц, индексы и триггеры созданы |

---

## 6. Стратегия тестирования

### 6.1 Уровни тестирования

| Уровень | Что тестируем | Инструмент | Количество |
|---------|--------------|-----------|-----------|
| Unit (схема) | CHECK constraints, NOT NULL, UNIQUE, FK | SQL-тесты в транзакции | >= 15 тестов |
| Unit (индексы) | EXPLAIN ANALYZE на типовых запросах | SQL + pytest | >= 5 тестов |
| Интеграция | Полный flow: raw -> parsed -> alert -> trip | pytest + asyncpg | >= 5 тестов |
| Нагрузка | 10K сообщений, время вставки и запросов | pgbench / скрипт | 1 сценарий |
| Миграция | Идемпотентность, откат | SQL-скрипт | 1 тест |

### 6.2 Тестовые сценарии (SQL)

```sql
-- =============================================================================
-- Тест 1: CHECK constraint на status
-- =============================================================================
-- Ожидание: ошибка (невалидный статус)
BEGIN;
INSERT INTO parsed_messages (raw_message_id, status, confidence)
VALUES (1, 'invalid_status', 0.5);
-- ERROR: new row violates check constraint
ROLLBACK;

-- =============================================================================
-- Тест 2: CHECK constraint на confidence (диапазон)
-- =============================================================================
BEGIN;
INSERT INTO parsed_messages (raw_message_id, confidence)
VALUES (1, 1.5);
-- ERROR: value 1.5 violates check constraint
ROLLBACK;

-- =============================================================================
-- Тест 3: UNIQUE constraint на message_id
-- =============================================================================
BEGIN;
INSERT INTO raw_messages (chat_id, message_id, text, timestamp)
VALUES (-100123, 999, 'Test', NOW());
INSERT INTO raw_messages (chat_id, message_id, text, timestamp)
VALUES (-100123, 999, 'Duplicate', NOW());
-- ERROR: duplicate key violates unique constraint
ROLLBACK;

-- =============================================================================
-- Тест 4: CASCADE delete
-- =============================================================================
BEGIN;
INSERT INTO raw_messages (chat_id, message_id, text, timestamp)
VALUES (-100, 1000, 'Test cascade', NOW());
INSERT INTO parsed_messages (raw_message_id, confidence) VALUES (currval('raw_messages_id_seq'), 0.9);
INSERT INTO alerts (parsed_message_id, type, severity, message)
VALUES (currval('parsed_messages_id_seq'), 'delay', 'high', 'Test alert');
DELETE FROM raw_messages WHERE message_id = 1000;
-- parsed_messages и alerts каскадно удалены
SELECT COUNT(*) FROM parsed_messages WHERE raw_message_id = currval('raw_messages_id_seq');
-- Ожидание: 0
ROLLBACK;

-- =============================================================================
-- Тест 5: FK нарушение
-- =============================================================================
BEGIN;
INSERT INTO parsed_messages (raw_message_id, confidence)
VALUES (999999999, 0.5);
-- ERROR: foreign key violation
ROLLBACK;

-- =============================================================================
-- Тест 6: Индекс используется (EXPLAIN)
-- =============================================================================
EXPLAIN ANALYZE
SELECT * FROM alerts
WHERE severity = 'high' AND status = 'new'
ORDER BY created_at DESC
LIMIT 20;
-- Ожидание: Index Scan using idx_alerts_active_high
```

### 6.3 Нагрузочный тест

Сценарий: загрузка 10 000 сообщений, парсинг, создание алертов. Измерение:

| Метрика | Целевое значение |
|---------|-----------------|
| INSERT в `raw_messages` (bulk 1000) | < 500 мс |
| INSERT в `parsed_messages` (одиночный) | < 5 мс |
| SELECT активных рейсов (50 строк) | < 50 мс |
| SELECT алертов HIGH + NEW (50 строк) | < 50 мс |
| SELECT статистики за день (агрегация) | < 200 мс |

---

## 7. Зависимости

### 7.1 Входящие зависимости (от чего зависит схема)

| Зависимость | Источник | Влияние |
|-------------|---------|--------|
| PostgreSQL 15+ | Docker образ `postgres:15` | Минимальная версия для поддержки всех конструкций DDL |
| Стек Sprint 0 | `master_brief.md` раздел 5 | Python 3.11+, asyncpg, FastAPI |
| Модель данных LLM-парсера | `spec-v1.yaml` раздел S0-F02 | Набор полей `parsed_messages` |
| Типы алертов | `product_brief.md` раздел S0-F03 | 5 типов, 3 уровня severity |
| Тестовые чаты | `master_brief.md` раздел 14 | 3 чата, синтетические данные |

### 7.2 Исходящие зависимости (кто зависит от схемы)

| Зависимый модуль | Спецификация | Что использует |
|-----------------|-------------|---------------|
| Chat Listener | `spec-tool-chat-listener.md` | Таблица `raw_messages`, контракт вставки (раздел 4.5) |
| AI Parser | `spec-tool-ai-parser.md` | Таблицы `raw_messages` (чтение), `parsed_messages` (запись) |
| Alert Engine | `spec-tool-alert-engine.md` | Таблицы `parsed_messages` (чтение), `alerts` (запись), `trips` (обновление `alert_count`) |
| Dashboard API | `spec-tool-dashboard-api.md` | Все таблицы (чтение), `dashboard_users` (авторизация), `alerts` (обновление статуса) |

### 7.3 Порядок инициализации

```
1. PostgreSQL контейнер стартует (docker-compose)
2. Миграция 001_initial_schema.sql применяется (initdb или entrypoint)
3. Миграция 002_seed_data.sql (только dev/test)
4. Chat Listener подключается к БД и начинает запись
5. AI Parser подключается к БД и начинает обработку
6. Alert Engine подключается к БД и начинает мониторинг
7. Dashboard API подключается к БД и обслуживает запросы
```

---

## 8. Примеры и граничные случаи

### 8.1 Граничные случаи

| Случай | Поведение | Обработка |
|--------|----------|-----------|
| Сообщение без текста (медиа) | В Sprint 0 -- пропускается | Listener фильтрует: `if not message.text: skip` |
| Дубль сообщения (переподключение Telethon) | Идемпотентность | `ON CONFLICT (message_id) DO NOTHING` |
| LLM вернул невалидный JSON | Запись с `confidence = 0.0` | Parser записывает строку с пустыми полями, issue = 'LLM parse error' |
| LLM не извлёк trip_id | `trip_id = NULL` | Сообщение парсится, но не агрегируется в `trips` |
| Два сообщения с разным trip_id в одном тексте | Парсится только первый | Ограничение Sprint 0. В Sprint 1 -- multi-trip парсинг |
| Алерт для неизвестного заказчика | `customer = NULL` в алерте | Alert Engine создаёт алерт без привязки к правилам заказчика |
| Очень длинный текст (>10 000 символов) | TEXT без ограничения | PostgreSQL TEXT -- до 1 GB. LLM может обрезать на своей стороне |
| Отрицательный `chat_id` | Нормально для групповых чатов Telegram | BIGINT поддерживает отрицательные значения |
| `sender_id = NULL` | Системное сообщение Telegram | Допускается: `sender_id BIGINT` (nullable) |
| Конкурентные INSERT (два экземпляра Listener) | Конфликт на `message_id` | `ON CONFLICT DO NOTHING` -- второй INSERT просто пропускается |

### 8.2 Примеры записей

#### raw_messages

| id | chat_id | chat_name | sender_id | sender_name | message_id | text | timestamp |
|----|---------|-----------|-----------|-------------|------------|------|-----------|
| 1 | -100001 | Marshall Test -- WB Рейсы | 501 | Диспетчер Алексей | 10001 | Рейс 4521, Москва-Краснодар, слот на погрузку WB 14:00, реф охладить до +2. Водитель Иванов подтверди. | 2026-03-06 09:15:00+00 |
| 2 | -100001 | Marshall Test -- WB Рейсы | 502 | Водитель Иван | 10002 | Принял, выезжаю через 30 мин. Реф включил. | 2026-03-06 09:18:00+00 |

#### parsed_messages

| id | raw_message_id | trip_id | route_from | route_to | status | customer | urgency | confidence | llm_model |
|----|----------------|---------|-----------|---------|--------|----------|---------|-----------|-----------|
| 1 | 1 | 4521 | Москва | Краснодар | assigned | WB | low | 0.95 | minimax |
| 2 | 2 | 4521 | NULL | NULL | in_transit | WB | low | 0.85 | minimax |

#### alerts

| id | trip_id | parsed_message_id | type | severity | message | customer | rule_id | status |
|----|---------|-------------------|------|----------|---------|----------|---------|--------|
| 1 | 4521 | 5 | delay | medium | Возможное опоздание ~40 мин на рейс 4521 WB | WB | DELAY_REPORTED | new |

---

## 9. ER-диаграмма

### 9.1 Текстовое описание связей

```
+-------------------+
|   raw_messages    |
|-------------------|
| id (PK, BIGSERIAL)|
| chat_id           |
| chat_name         |
| sender_id         |
| sender_name       |
| message_id (UQ)   |
| text              |
| timestamp         |
| created_at        |
+--------+----------+
         |
         | 1:N (raw_message_id FK, ON DELETE CASCADE)
         |
+--------v----------+
| parsed_messages   |
|-------------------|
| id (PK, BIGSERIAL)|
| raw_message_id(FK)|-----> raw_messages.id
| trip_id           |
| route_from        |
| route_to          |
| slot_time         |
| status            |
| customer          |
| urgency           |
| issue             |
| confidence        |
| llm_model         |
| llm_tokens_used   |
| parse_duration_ms |
| created_at        |
+--------+----------+
         |
         | 1:N (parsed_message_id FK, ON DELETE CASCADE)
         |
+--------v----------+        +-------------------+
|      alerts       |        |      trips        |
|-------------------|        |-------------------|
| id (PK, BIGSERIAL)|        | id (PK, BIGSERIAL)|
| trip_id           |        | trip_id (UQ)      |
| parsed_message_id |---->   | route_from        |
|   parsed_msgs.id  |        | route_to          |
| type              |        | customer          |
| severity          |        | driver_name       |
| message           |        | dispatcher_name   |
| customer          |        | status            |
| rule_id           |        | slot_time         |
| status            |        | departure_time    |
| reviewed_by       |        | arrival_time      |
| reviewed_at       |        | alert_count       |
| created_at        |        | last_update       |
+-------------------+        | created_at        |
                              | updated_at        |
                              +-------------------+

+-------------------+
| dashboard_users   |
|-------------------|         Связь trips <-> parsed_messages:
| id (PK, SERIAL)  |         Логическая, по значению trip_id.
| username (UQ)    |         Нет FK -- trips агрегат,
| password_hash    |         обновляется программно.
| role             |
| is_active        |         Связь trips <-> alerts:
| last_login_at    |         Логическая, по значению trip_id.
| created_at       |         Нет FK -- для гибкости
+-------------------+         (алерт без trip_id допустим).
```

### 9.2 Кардинальности

| Связь | Кардинальность | FK constraint |
|-------|---------------|--------------|
| raw_messages -> parsed_messages | 1:N | `parsed_messages.raw_message_id -> raw_messages.id` ON DELETE CASCADE |
| parsed_messages -> alerts | 1:N | `alerts.parsed_message_id -> parsed_messages.id` ON DELETE CASCADE |
| trips <-> parsed_messages | Логическая по `trip_id` | Нет FK. Агрегат обновляется программно |
| trips <-> alerts | Логическая по `trip_id` | Нет FK. `alert_count` инкрементируется программно |

---

## 10. Миграции

### 10.1 Файл: `001_initial_schema.sql`

Полная миграция для создания всех таблиц, индексов и триггеров Sprint 0.

```sql
-- =============================================================================
-- Marshall AI Listener -- Миграция 001: Начальная схема
-- Sprint 0
-- Версия: 1.0
-- Дата: 2026-03-06
-- Автор: Zinin Corp
--
-- Запуск: psql -h localhost -U marshall -d marshall_db -f 001_initial_schema.sql
-- Идемпотентно: да (все CREATE используют IF NOT EXISTS)
-- =============================================================================

BEGIN;

-- =============================================================================
-- 1. ТАБЛИЦЫ
-- =============================================================================

-- 1.1 raw_messages
CREATE TABLE IF NOT EXISTS raw_messages (
    id              BIGSERIAL       PRIMARY KEY,
    chat_id         BIGINT          NOT NULL,
    chat_name       VARCHAR(255),
    sender_id       BIGINT,
    sender_name     VARCHAR(255),
    message_id      BIGINT          NOT NULL UNIQUE,
    text            TEXT            NOT NULL,
    timestamp       TIMESTAMPTZ     NOT NULL,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE  raw_messages IS 'Сырые текстовые сообщения из Telegram-чатов диспетчеров';
COMMENT ON COLUMN raw_messages.chat_id IS 'Telegram chat ID. Отрицательный для групповых чатов';
COMMENT ON COLUMN raw_messages.message_id IS 'Уникальный Telegram message_id. Предотвращает дубли при переподключении';
COMMENT ON COLUMN raw_messages.timestamp IS 'Время отправки сообщения в Telegram (UTC)';

-- 1.2 parsed_messages
CREATE TABLE IF NOT EXISTS parsed_messages (
    id                  BIGSERIAL       PRIMARY KEY,
    raw_message_id      BIGINT          NOT NULL
                        REFERENCES raw_messages(id) ON DELETE CASCADE,
    trip_id             VARCHAR(50),
    route_from          VARCHAR(255),
    route_to            VARCHAR(255),
    slot_time           TIME,
    status              VARCHAR(30)
                        CHECK (status IN (
                            'assigned', 'in_transit', 'loading', 'unloading',
                            'completed', 'problem', 'cancelled'
                        )),
    customer            VARCHAR(100),
    urgency             VARCHAR(10)     NOT NULL DEFAULT 'low'
                        CHECK (urgency IN ('low', 'medium', 'high')),
    issue               TEXT,
    confidence          REAL            NOT NULL DEFAULT 0.0
                        CHECK (confidence >= 0.0 AND confidence <= 1.0),
    llm_model           VARCHAR(50),
    llm_tokens_used     INTEGER         CHECK (llm_tokens_used IS NULL OR llm_tokens_used >= 0),
    parse_duration_ms   INTEGER         CHECK (parse_duration_ms IS NULL OR parse_duration_ms >= 0),
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE  parsed_messages IS 'Результаты LLM-парсинга сырых сообщений';
COMMENT ON COLUMN parsed_messages.confidence IS 'Уверенность LLM: 0.0-1.0. Порог для алертов: 0.7';
COMMENT ON COLUMN parsed_messages.llm_model IS 'minimax (основная) или groq (fallback)';

-- 1.3 alerts
CREATE TABLE IF NOT EXISTS alerts (
    id                  BIGSERIAL       PRIMARY KEY,
    trip_id             VARCHAR(50),
    parsed_message_id   BIGINT          NOT NULL
                        REFERENCES parsed_messages(id) ON DELETE CASCADE,
    type                VARCHAR(30)     NOT NULL
                        CHECK (type IN (
                            'delay', 'equipment_failure', 'downtime',
                            'safety_violation', 'docs_missing'
                        )),
    severity            VARCHAR(10)     NOT NULL
                        CHECK (severity IN ('high', 'medium', 'low')),
    message             TEXT            NOT NULL,
    customer            VARCHAR(100),
    rule_id             VARCHAR(50),
    status              VARCHAR(15)     NOT NULL DEFAULT 'new'
                        CHECK (status IN ('new', 'reviewed', 'resolved')),
    reviewed_by         VARCHAR(100),
    reviewed_at         TIMESTAMPTZ,
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE  alerts IS 'Алерты о критических событиях. Sprint 0 -- только дашборд';
COMMENT ON COLUMN alerts.rule_id IS 'ID правила: DELAY_GT_4H, X5_NO_IDLE, REEFER_TEMP и т.д.';

-- 1.4 trips
CREATE TABLE IF NOT EXISTS trips (
    id                  BIGSERIAL       PRIMARY KEY,
    trip_id             VARCHAR(50)     NOT NULL UNIQUE,
    route_from          VARCHAR(255),
    route_to            VARCHAR(255),
    customer            VARCHAR(100),
    driver_name         VARCHAR(255),
    dispatcher_name     VARCHAR(255),
    status              VARCHAR(30)     NOT NULL DEFAULT 'assigned'
                        CHECK (status IN (
                            'assigned', 'in_transit', 'loading', 'unloading',
                            'completed', 'problem', 'cancelled'
                        )),
    slot_time           TIMESTAMPTZ,
    departure_time      TIMESTAMPTZ,
    arrival_time        TIMESTAMPTZ,
    alert_count         INTEGER         NOT NULL DEFAULT 0
                        CHECK (alert_count >= 0),
    last_update         TIMESTAMPTZ,
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE  trips IS 'Агрегированные данные по рейсам. Обновляется из parsed_messages';
COMMENT ON COLUMN trips.trip_id IS 'Номер рейса Marshall. Уникален. Источник -- LLM-парсинг';

-- 1.5 dashboard_users
CREATE TABLE IF NOT EXISTS dashboard_users (
    id                  SERIAL          PRIMARY KEY,
    username            VARCHAR(100)    NOT NULL UNIQUE,
    password_hash       VARCHAR(255)    NOT NULL,
    role                VARCHAR(20)     NOT NULL DEFAULT 'viewer'
                        CHECK (role IN ('admin', 'manager', 'viewer')),
    is_active           BOOLEAN         NOT NULL DEFAULT TRUE,
    last_login_at       TIMESTAMPTZ,
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE  dashboard_users IS 'Пользователи дашборда. bcrypt авторизация';

-- =============================================================================
-- 2. ИНДЕКСЫ
-- =============================================================================

-- raw_messages
CREATE INDEX IF NOT EXISTS idx_raw_messages_chat_id
    ON raw_messages (chat_id);
CREATE INDEX IF NOT EXISTS idx_raw_messages_timestamp
    ON raw_messages (timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_raw_messages_chat_timestamp
    ON raw_messages (chat_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_raw_messages_sender_id
    ON raw_messages (sender_id) WHERE sender_id IS NOT NULL;

-- parsed_messages
CREATE INDEX IF NOT EXISTS idx_parsed_messages_raw_message_id
    ON parsed_messages (raw_message_id);
CREATE INDEX IF NOT EXISTS idx_parsed_messages_trip_id
    ON parsed_messages (trip_id) WHERE trip_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_parsed_messages_customer
    ON parsed_messages (customer) WHERE customer IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_parsed_messages_status
    ON parsed_messages (status) WHERE status IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_parsed_messages_created_at
    ON parsed_messages (created_at DESC);

-- alerts
CREATE INDEX IF NOT EXISTS idx_alerts_severity
    ON alerts (severity);
CREATE INDEX IF NOT EXISTS idx_alerts_status
    ON alerts (status);
CREATE INDEX IF NOT EXISTS idx_alerts_trip_id
    ON alerts (trip_id) WHERE trip_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_alerts_customer
    ON alerts (customer) WHERE customer IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_alerts_created_at
    ON alerts (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_alerts_active_high
    ON alerts (severity, created_at DESC) WHERE status = 'new';
CREATE INDEX IF NOT EXISTS idx_alerts_parsed_message_id
    ON alerts (parsed_message_id);

-- trips
CREATE INDEX IF NOT EXISTS idx_trips_customer
    ON trips (customer) WHERE customer IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_trips_status
    ON trips (status);
CREATE INDEX IF NOT EXISTS idx_trips_created_at
    ON trips (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_trips_active
    ON trips (status, last_update DESC)
    WHERE status NOT IN ('completed', 'cancelled');

-- =============================================================================
-- 3. ТРИГГЕРЫ
-- =============================================================================

CREATE OR REPLACE FUNCTION trigger_set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_trips_updated_at ON trips;
CREATE TRIGGER trg_trips_updated_at
    BEFORE UPDATE ON trips
    FOR EACH ROW
    EXECUTE FUNCTION trigger_set_updated_at();

COMMIT;

-- =============================================================================
-- Проверка: все объекты созданы
-- =============================================================================
DO $$
DECLARE
    tbl TEXT;
    tables TEXT[] := ARRAY['raw_messages', 'parsed_messages', 'alerts', 'trips', 'dashboard_users'];
BEGIN
    FOREACH tbl IN ARRAY tables LOOP
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = tbl
        ) THEN
            RAISE EXCEPTION 'Таблица % не создана!', tbl;
        END IF;
    END LOOP;
    RAISE NOTICE 'Миграция 001: все 5 таблиц успешно созданы';
END $$;
```

### 10.2 Файл: `002_seed_data.sql`

Тестовые данные для 3 чатов из master_brief (раздел 14). Только для разработки и демо.

```sql
-- =============================================================================
-- Marshall AI Listener -- Миграция 002: Тестовые данные (Seed)
-- ТОЛЬКО для dev/test. НЕ запускать в продакшне.
-- Источник: master_brief.md, раздел 14 (синтетические тестовые данные)
-- =============================================================================

BEGIN;

-- =============================================================================
-- 1. DASHBOARD USERS (тестовые аккаунты)
-- =============================================================================
-- Пароли: admin -> 'admin123', manager -> 'manager123', viewer -> 'viewer123'
-- bcrypt хеши сгенерированы: python -c "import bcrypt; print(bcrypt.hashpw(b'...', bcrypt.gensalt()).decode())"

INSERT INTO dashboard_users (username, password_hash, role) VALUES
    ('admin',   '$2b$12$LJ3m4ys3GZ.ZG0R1XdKqYeCGZi7YRGXO8nTqJ7yVzHlOySYNmEVWW', 'admin'),
    ('nikolya', '$2b$12$5v5K0M7z8R1QzJhP4uO9s.E7BwAx2vR8dH9kL3nY6tM1wX4pZ7qWe', 'manager'),
    ('viewer',  '$2b$12$8dH9kL3nY6tM1wX4pZ7qWe5v5K0M7z8R1QzJhP4uO9s.E7BwAx2vR', 'viewer')
ON CONFLICT (username) DO NOTHING;

-- =============================================================================
-- 2. RAW MESSAGES: Чат "Marshall Test -- WB Рейсы"
-- =============================================================================
INSERT INTO raw_messages (chat_id, chat_name, sender_id, sender_name, message_id, text, timestamp) VALUES
    (-100001, 'Marshall Test -- WB Рейсы', 501, 'Диспетчер Алексей', 10001,
     'Рейс 4521, Москва-Краснодар, слот на погрузку WB 14:00, реф охладить до +2. Водитель Иванов подтверди.',
     '2026-03-06 06:15:00+00'),
    (-100001, 'Marshall Test -- WB Рейсы', 502, 'Водитель Иван', 10002,
     'Принял, выезжаю через 30 мин. Реф включил.',
     '2026-03-06 06:18:00+00'),
    (-100001, 'Marshall Test -- WB Рейсы', 502, 'Водитель Иван', 10003,
     'Выехал на погрузку. Навигатор показывает 2.5 часа.',
     '2026-03-06 06:45:00+00'),
    (-100001, 'Marshall Test -- WB Рейсы', 502, 'Водитель Иван', 10004,
     'Стою в пробке на МКАД, опаздываю минут на 40.',
     '2026-03-06 08:30:00+00'),
    (-100001, 'Marshall Test -- WB Рейсы', 501, 'Диспетчер Алексей', 10005,
     'Иванов, успеваешь на слот? WB штрафует за опоздание.',
     '2026-03-06 09:15:00+00'),
    (-100001, 'Marshall Test -- WB Рейсы', 502, 'Водитель Иван', 10006,
     'Пробка рассосалась, буду к 13:50, успею.',
     '2026-03-06 09:20:00+00'),
    (-100001, 'Marshall Test -- WB Рейсы', 502, 'Водитель Иван', 10007,
     'На месте WB, встал в очередь на погрузку.',
     '2026-03-06 11:05:00+00'),
    (-100001, 'Marshall Test -- WB Рейсы', 502, 'Водитель Иван', 10008,
     'Погрузка началась.',
     '2026-03-06 11:30:00+00'),
    (-100001, 'Marshall Test -- WB Рейсы', 502, 'Водитель Иван', 10009,
     'Погрузка завершена, 18 паллет, температура +3, выезжаю.',
     '2026-03-06 12:45:00+00'),
    (-100001, 'Marshall Test -- WB Рейсы', 502, 'Водитель Иван', 10010,
     'Прибыл Краснодар, выгрузка завтра с 6:00.',
     '2026-03-06 19:10:00+00')
ON CONFLICT (message_id) DO NOTHING;

-- =============================================================================
-- 3. RAW MESSAGES: Чат "Marshall Test -- Тандер Логистика"
-- =============================================================================
INSERT INTO raw_messages (chat_id, chat_name, sender_id, sender_name, message_id, text, timestamp) VALUES
    (-100002, 'Marshall Test -- Тандер Логистика', 503, 'Диспетчер Мария', 20001,
     'Доброе утро. Сергей, рейс 7803, Ростов-Воронеж, Тандер, слот 12:00. Охлаждение +2..+4 обязательно! Проверь термописец.',
     '2026-03-06 04:00:00+00'),
    (-100002, 'Marshall Test -- Тандер Логистика', 504, 'Водитель Сергей', 20002,
     'Принял. Термописец работает, бумага есть. Санобработка свежая.',
     '2026-03-06 04:15:00+00'),
    (-100002, 'Marshall Test -- Тандер Логистика', 503, 'Диспетчер Мария', 20003,
     'Олег, рейс 7804, Краснодар-Сочи, Тандер, слот 15:00.',
     '2026-03-06 04:20:00+00'),
    (-100002, 'Marshall Test -- Тандер Логистика', 505, 'Водитель Олег', 20004,
     'Мария, у меня проблема — реф не выходит на температуру, показывает +8. Мастер смотрит.',
     '2026-03-06 04:25:00+00'),
    (-100002, 'Marshall Test -- Тандер Логистика', 503, 'Диспетчер Мария', 20005,
     'Олег, сколько по времени ремонт? Если больше часа — ищу замену.',
     '2026-03-06 04:30:00+00'),
    (-100002, 'Marshall Test -- Тандер Логистика', 505, 'Водитель Олег', 20006,
     'Мастер говорит компрессор, минимум 3-4 часа. Не успею.',
     '2026-03-06 04:45:00+00'),
    (-100002, 'Marshall Test -- Тандер Логистика', 503, 'Диспетчер Мария', 20007,
     'Понятно, снимаю тебя с рейса. Ищу замену. @Алексей нужен реф на Краснодар-Сочи, слот 15:00, срочно.',
     '2026-03-06 04:50:00+00'),
    (-100002, 'Marshall Test -- Тандер Логистика', 504, 'Водитель Сергей', 20008,
     'Выехал на Ростов. ETA 11:30.',
     '2026-03-06 05:10:00+00'),
    (-100002, 'Marshall Test -- Тандер Логистика', 504, 'Водитель Сергей', 20009,
     'Прибыл Тандер Ростов. Температура +3, норма.',
     '2026-03-06 08:25:00+00'),
    (-100002, 'Marshall Test -- Тандер Логистика', 504, 'Водитель Сергей', 20010,
     'Жду слот, очередь 2 машины передо мной.',
     '2026-03-06 08:30:00+00'),
    (-100002, 'Marshall Test -- Тандер Логистика', 504, 'Водитель Сергей', 20011,
     'Погрузка началась, опоздание 40 мин из-за очереди на складе.',
     '2026-03-06 09:40:00+00')
ON CONFLICT (message_id) DO NOTHING;

-- =============================================================================
-- 4. RAW MESSAGES: Чат "Marshall Test -- Общий Диспетчерская"
-- =============================================================================
INSERT INTO raw_messages (chat_id, chat_name, sender_id, sender_name, message_id, text, timestamp) VALUES
    (-100003, 'Marshall Test -- Общий Диспетчерская', 503, 'Диспетчер Мария', 30001,
     'Смена началась. На сегодня: 12 рейсов активных, 3 на погрузке, 5 в пути, 4 назначены.',
     '2026-03-06 05:00:00+00'),
    (-100003, 'Marshall Test -- Общий Диспетчерская', 506, 'Менеджер Виктория', 30002,
     'Мария, по X5 вчера был простой 6 часов, они прислали претензию. Нужны данные кто стоял и почему.',
     '2026-03-06 05:05:00+00'),
    (-100003, 'Marshall Test -- Общий Диспетчерская', 503, 'Диспетчер Мария', 30003,
     'Это был Петров, рейс 7790. Стоял на территории X5 — они не разгружали. У нас фото и переписка есть.',
     '2026-03-06 05:10:00+00'),
    (-100003, 'Marshall Test -- Общий Диспетчерская', 501, 'Диспетчер Алексей', 30004,
     'Внимание, ДТП на М4 Дон км 680. Наш водитель НЕ участвует, но пробка — рейсы 4521 и 4525 могут опоздать.',
     '2026-03-06 07:30:00+00'),
    (-100003, 'Marshall Test -- Общий Диспетчерская', 506, 'Менеджер Виктория', 30005,
     'Итого за первую половину дня: 2 опоздания, 1 срыв (реф Олега). Нормально?',
     '2026-03-06 11:00:00+00'),
    (-100003, 'Marshall Test -- Общий Диспетчерская', 503, 'Диспетчер Мария', 30006,
     'Срыв закрыли заменой, опоздания в пределах 1 часа, штрафов не будет.',
     '2026-03-06 11:05:00+00')
ON CONFLICT (message_id) DO NOTHING;

-- =============================================================================
-- 5. PARSED MESSAGES (результаты LLM-парсинга тестовых сообщений)
-- =============================================================================

-- WB Рейсы: назначение рейса 4521
INSERT INTO parsed_messages (raw_message_id, trip_id, route_from, route_to, slot_time, status, customer, urgency, issue, confidence, llm_model, llm_tokens_used, parse_duration_ms)
SELECT id, '4521', 'Москва', 'Краснодар', '14:00', 'assigned', 'WB', 'low', NULL, 0.95, 'minimax', 320, 1200
FROM raw_messages WHERE message_id = 10001
ON CONFLICT DO NOTHING;

-- WB: подтверждение водителя
INSERT INTO parsed_messages (raw_message_id, trip_id, route_from, route_to, slot_time, status, customer, urgency, issue, confidence, llm_model, llm_tokens_used, parse_duration_ms)
SELECT id, '4521', NULL, NULL, NULL, 'assigned', 'WB', 'low', NULL, 0.85, 'minimax', 280, 980
FROM raw_messages WHERE message_id = 10002
ON CONFLICT DO NOTHING;

-- WB: выезд
INSERT INTO parsed_messages (raw_message_id, trip_id, route_from, route_to, slot_time, status, customer, urgency, issue, confidence, llm_model, llm_tokens_used, parse_duration_ms)
SELECT id, '4521', NULL, NULL, NULL, 'in_transit', 'WB', 'low', NULL, 0.88, 'minimax', 290, 1050
FROM raw_messages WHERE message_id = 10003
ON CONFLICT DO NOTHING;

-- WB: пробка, опоздание (MEDIUM urgency)
INSERT INTO parsed_messages (raw_message_id, trip_id, route_from, route_to, slot_time, status, customer, urgency, issue, confidence, llm_model, llm_tokens_used, parse_duration_ms)
SELECT id, '4521', NULL, NULL, NULL, 'problem', 'WB', 'medium', 'Пробка на МКАД, опоздание ~40 мин', 0.90, 'minimax', 350, 1150
FROM raw_messages WHERE message_id = 10004
ON CONFLICT DO NOTHING;

-- WB: погрузка началась
INSERT INTO parsed_messages (raw_message_id, trip_id, route_from, route_to, slot_time, status, customer, urgency, issue, confidence, llm_model, llm_tokens_used, parse_duration_ms)
SELECT id, '4521', NULL, NULL, NULL, 'loading', 'WB', 'low', NULL, 0.92, 'minimax', 260, 900
FROM raw_messages WHERE message_id = 10008
ON CONFLICT DO NOTHING;

-- WB: погрузка завершена
INSERT INTO parsed_messages (raw_message_id, trip_id, route_from, route_to, slot_time, status, customer, urgency, issue, confidence, llm_model, llm_tokens_used, parse_duration_ms)
SELECT id, '4521', NULL, NULL, NULL, 'in_transit', 'WB', 'low', NULL, 0.93, 'minimax', 310, 1020
FROM raw_messages WHERE message_id = 10009
ON CONFLICT DO NOTHING;

-- WB: прибытие
INSERT INTO parsed_messages (raw_message_id, trip_id, route_from, route_to, slot_time, status, customer, urgency, issue, confidence, llm_model, llm_tokens_used, parse_duration_ms)
SELECT id, '4521', NULL, 'Краснодар', NULL, 'unloading', 'WB', 'low', NULL, 0.91, 'minimax', 300, 1100
FROM raw_messages WHERE message_id = 10010
ON CONFLICT DO NOTHING;

-- Тандер: назначение рейса 7803
INSERT INTO parsed_messages (raw_message_id, trip_id, route_from, route_to, slot_time, status, customer, urgency, issue, confidence, llm_model, llm_tokens_used, parse_duration_ms)
SELECT id, '7803', 'Ростов', 'Воронеж', '12:00', 'assigned', 'Тандер', 'low', NULL, 0.94, 'minimax', 340, 1180
FROM raw_messages WHERE message_id = 20001
ON CONFLICT DO NOTHING;

-- Тандер: назначение рейса 7804
INSERT INTO parsed_messages (raw_message_id, trip_id, route_from, route_to, slot_time, status, customer, urgency, issue, confidence, llm_model, llm_tokens_used, parse_duration_ms)
SELECT id, '7804', 'Краснодар', 'Сочи', '15:00', 'assigned', 'Тандер', 'low', NULL, 0.93, 'minimax', 300, 1050
FROM raw_messages WHERE message_id = 20003
ON CONFLICT DO NOTHING;

-- Тандер: ПОЛОМКА РЕФА (HIGH urgency)
INSERT INTO parsed_messages (raw_message_id, trip_id, route_from, route_to, slot_time, status, customer, urgency, issue, confidence, llm_model, llm_tokens_used, parse_duration_ms)
SELECT id, '7804', NULL, NULL, NULL, 'problem', 'Тандер', 'high', 'Поломка рефрижератора, температура +8 вместо нормы', 0.92, 'minimax', 380, 1350
FROM raw_messages WHERE message_id = 20004
ON CONFLICT DO NOTHING;

-- Тандер: рейс отменён (компрессор, 3-4 часа ремонта)
INSERT INTO parsed_messages (raw_message_id, trip_id, route_from, route_to, slot_time, status, customer, urgency, issue, confidence, llm_model, llm_tokens_used, parse_duration_ms)
SELECT id, '7804', NULL, NULL, NULL, 'cancelled', 'Тандер', 'high', 'Ремонт компрессора 3-4 часа, водитель снят с рейса', 0.89, 'minimax', 360, 1280
FROM raw_messages WHERE message_id = 20007
ON CONFLICT DO NOTHING;

-- Тандер: Сергей выехал (рейс 7803)
INSERT INTO parsed_messages (raw_message_id, trip_id, route_from, route_to, slot_time, status, customer, urgency, issue, confidence, llm_model, llm_tokens_used, parse_duration_ms)
SELECT id, '7803', NULL, 'Ростов', NULL, 'in_transit', 'Тандер', 'low', NULL, 0.87, 'minimax', 270, 950
FROM raw_messages WHERE message_id = 20008
ON CONFLICT DO NOTHING;

-- Тандер: Сергей прибыл
INSERT INTO parsed_messages (raw_message_id, trip_id, route_from, route_to, slot_time, status, customer, urgency, issue, confidence, llm_model, llm_tokens_used, parse_duration_ms)
SELECT id, '7803', NULL, NULL, NULL, 'loading', 'Тандер', 'low', NULL, 0.91, 'minimax', 290, 1030
FROM raw_messages WHERE message_id = 20009
ON CONFLICT DO NOTHING;

-- Тандер: опоздание на погрузке
INSERT INTO parsed_messages (raw_message_id, trip_id, route_from, route_to, slot_time, status, customer, urgency, issue, confidence, llm_model, llm_tokens_used, parse_duration_ms)
SELECT id, '7803', NULL, NULL, NULL, 'loading', 'Тандер', 'medium', 'Опоздание 40 мин из-за очереди на складе', 0.88, 'minimax', 330, 1200
FROM raw_messages WHERE message_id = 20011
ON CONFLICT DO NOTHING;

-- Общий: простой X5 (рейс 7790)
INSERT INTO parsed_messages (raw_message_id, trip_id, route_from, route_to, slot_time, status, customer, urgency, issue, confidence, llm_model, llm_tokens_used, parse_duration_ms)
SELECT id, '7790', NULL, NULL, NULL, 'problem', 'X5', 'high', 'Простой 6 часов на территории X5, претензия от заказчика', 0.86, 'minimax', 370, 1300
FROM raw_messages WHERE message_id = 30003
ON CONFLICT DO NOTHING;

-- Общий: ДТП на трассе
INSERT INTO parsed_messages (raw_message_id, trip_id, route_from, route_to, slot_time, status, customer, urgency, issue, confidence, llm_model, llm_tokens_used, parse_duration_ms)
SELECT id, NULL, NULL, NULL, NULL, 'problem', NULL, 'high', 'ДТП на М4 Дон км 680, пробка, рейсы 4521 и 4525 могут опоздать', 0.88, 'minimax', 350, 1250
FROM raw_messages WHERE message_id = 30004
ON CONFLICT DO NOTHING;

-- =============================================================================
-- 6. ALERTS (сгенерированные Alert Engine из тестовых данных)
-- =============================================================================

-- Алерт: опоздание WB рейс 4521 (~40 мин)
INSERT INTO alerts (trip_id, parsed_message_id, type, severity, message, customer, rule_id, status)
SELECT '4521', pm.id, 'delay', 'medium',
       'Возможное опоздание ~40 мин на рейс 4521 WB. Водитель Иван: пробка на МКАД.',
       'WB', 'DELAY_REPORTED', 'reviewed'
FROM parsed_messages pm
JOIN raw_messages rm ON rm.id = pm.raw_message_id
WHERE rm.message_id = 10004
ON CONFLICT DO NOTHING;

-- Алерт: поломка рефа рейс 7804 (HIGH)
INSERT INTO alerts (trip_id, parsed_message_id, type, severity, message, customer, rule_id, status)
SELECT '7804', pm.id, 'equipment_failure', 'high',
       'КРИТИЧНО: Поломка рефрижератора на рейсе 7804 Тандер. Температура +8 вместо +2..+4. Ремонт 3-4 часа.',
       'Тандер', 'REEFER_TEMP', 'resolved'
FROM parsed_messages pm
JOIN raw_messages rm ON rm.id = pm.raw_message_id
WHERE rm.message_id = 20004
ON CONFLICT DO NOTHING;

-- Алерт: рейс 7804 отменён (HIGH)
INSERT INTO alerts (trip_id, parsed_message_id, type, severity, message, customer, rule_id, status)
SELECT '7804', pm.id, 'equipment_failure', 'high',
       'Рейс 7804 Тандер отменён. Компрессор рефрижератора сломан. Ищут замену.',
       'Тандер', 'TRIP_CANCELLED_EQUIPMENT', 'resolved'
FROM parsed_messages pm
JOIN raw_messages rm ON rm.id = pm.raw_message_id
WHERE rm.message_id = 20007
ON CONFLICT DO NOTHING;

-- Алерт: простой X5 рейс 7790 (HIGH -- X5 запрещает стоять)
INSERT INTO alerts (trip_id, parsed_message_id, type, severity, message, customer, rule_id, status)
SELECT '7790', pm.id, 'downtime', 'high',
       'Простой 6 часов на территории X5 (рейс 7790). X5 ЗАПРЕЩАЕТ простой! Претензия от заказчика.',
       'X5', 'X5_NO_IDLE', 'new'
FROM parsed_messages pm
JOIN raw_messages rm ON rm.id = pm.raw_message_id
WHERE rm.message_id = 30003
ON CONFLICT DO NOTHING;

-- Алерт: ДТП на трассе (информационный)
INSERT INTO alerts (trip_id, parsed_message_id, type, severity, message, customer, rule_id, status)
SELECT NULL, pm.id, 'delay', 'low',
       'ДТП на М4 Дон км 680. Наш водитель не участвует, но пробка может задержать рейсы 4521 и 4525.',
       NULL, 'TRAFFIC_INCIDENT', 'reviewed'
FROM parsed_messages pm
JOIN raw_messages rm ON rm.id = pm.raw_message_id
WHERE rm.message_id = 30004
ON CONFLICT DO NOTHING;

-- Алерт: опоздание на погрузке рейс 7803 (MEDIUM)
INSERT INTO alerts (trip_id, parsed_message_id, type, severity, message, customer, rule_id, status)
SELECT '7803', pm.id, 'delay', 'medium',
       'Опоздание 40 мин на погрузке рейса 7803 Тандер. Причина: очередь на складе.',
       'Тандер', 'DELAY_LOADING', 'new'
FROM parsed_messages pm
JOIN raw_messages rm ON rm.id = pm.raw_message_id
WHERE rm.message_id = 20011
ON CONFLICT DO NOTHING;

-- =============================================================================
-- 7. TRIPS (агрегированные данные по рейсам)
-- =============================================================================

INSERT INTO trips (trip_id, route_from, route_to, customer, driver_name, dispatcher_name, status, slot_time, departure_time, arrival_time, alert_count, last_update) VALUES
    ('4521', 'Москва', 'Краснодар', 'WB', 'Водитель Иван', 'Диспетчер Алексей',
     'unloading', '2026-03-06 11:00:00+00', '2026-03-06 06:45:00+00', '2026-03-06 19:10:00+00',
     2, '2026-03-06 19:10:00+00'),

    ('7803', 'Ростов', 'Воронеж', 'Тандер', 'Водитель Сергей', 'Диспетчер Мария',
     'loading', '2026-03-06 09:00:00+00', '2026-03-06 05:10:00+00', NULL,
     1, '2026-03-06 09:40:00+00'),

    ('7804', 'Краснодар', 'Сочи', 'Тандер', 'Водитель Олег', 'Диспетчер Мария',
     'cancelled', '2026-03-06 12:00:00+00', NULL, NULL,
     2, '2026-03-06 04:50:00+00'),

    ('7790', NULL, NULL, 'X5', 'Петров', 'Диспетчер Мария',
     'problem', NULL, NULL, NULL,
     1, '2026-03-06 05:10:00+00')
ON CONFLICT (trip_id) DO NOTHING;

COMMIT;

-- Проверка seed data
DO $$
BEGIN
    RAISE NOTICE 'Seed data загружены:';
    RAISE NOTICE '  raw_messages: % строк', (SELECT COUNT(*) FROM raw_messages);
    RAISE NOTICE '  parsed_messages: % строк', (SELECT COUNT(*) FROM parsed_messages);
    RAISE NOTICE '  alerts: % строк', (SELECT COUNT(*) FROM alerts);
    RAISE NOTICE '  trips: % строк', (SELECT COUNT(*) FROM trips);
    RAISE NOTICE '  dashboard_users: % строк', (SELECT COUNT(*) FROM dashboard_users);
END $$;
```

### 10.3 Порядок применения миграций

```bash
# Создание базы данных
createdb -U postgres marshall_db

# Применение схемы
psql -U marshall -d marshall_db -f migrations/001_initial_schema.sql

# Загрузка тестовых данных (только dev/test)
psql -U marshall -d marshall_db -f migrations/002_seed_data.sql
```

### 10.4 Docker Compose интеграция

Миграции выполняются автоматически при старте контейнера PostgreSQL через volume-mount в `/docker-entrypoint-initdb.d/`:

```yaml
# Фрагмент docker-compose.yml
services:
  postgres:
    image: postgres:15
    environment:
      POSTGRES_DB: marshall_db
      POSTGRES_USER: marshall
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - pg_data:/var/lib/postgresql/data
      - ./migrations/001_initial_schema.sql:/docker-entrypoint-initdb.d/001_initial_schema.sql
      # Для dev/test:
      # - ./migrations/002_seed_data.sql:/docker-entrypoint-initdb.d/002_seed_data.sql
    ports:
      - "5432:5432"
```

---

## Приложение А. Эволюция схемы (Sprint 1+)

Для контекста: какие таблицы будут добавлены в Sprint 1 (не входят в текущую спецификацию, но влияют на архитектуру).

| Таблица | Назначение | Связь с текущей схемой |
|---------|-----------|----------------------|
| `users` | Регистрация водителей/диспетчеров/менеджеров | Заменит `sender_name` на FK к `users.id` |
| `trip_assignments` | Назначение рейсов через бота | Расширит `trips` данными назначения |
| `status_events` | Кнопки статусов (timeline) | Дополнит `trips` детальной историей |
| `checklist_responses` | Фото-чеклисты перед рейсом | FK к `trip_assignments` |
| `shift_schedules` | Расписание смен диспетчеров | Для авто-эскалации алертов |
| `customer_memos` | Памятки заказчиков | Для Alert Engine (правила по заказчикам) |
| `documents` | Термограммы, ТСД, чеки | FK к `trip_assignments`, URL в MinIO/S3 |

Текущая схема спроектирована так, чтобы добавление этих таблиц не требовало миграции существующих данных. Поля `trip_id` (VARCHAR) и `customer` (VARCHAR) в Sprint 1 могут стать FK к соответствующим таблицам через ALTER TABLE.

---

## Приложение Б. Быстрая справка по типовым запросам

```sql
-- Последние 50 сообщений из чата
SELECT * FROM raw_messages
WHERE chat_id = -100001
ORDER BY timestamp DESC
LIMIT 50;

-- Все parsed_messages по рейсу (хронология)
SELECT pm.*, rm.text, rm.sender_name, rm.timestamp
FROM parsed_messages pm
JOIN raw_messages rm ON rm.id = pm.raw_message_id
WHERE pm.trip_id = '4521'
ORDER BY rm.timestamp ASC;

-- Активные HIGH-алерты (лента дашборда)
SELECT a.*, rm.text AS original_text, rm.sender_name
FROM alerts a
JOIN parsed_messages pm ON pm.id = a.parsed_message_id
JOIN raw_messages rm ON rm.id = pm.raw_message_id
WHERE a.status = 'new' AND a.severity = 'high'
ORDER BY a.created_at DESC;

-- Статистика за сегодня
SELECT
    COUNT(DISTINCT trip_id) AS total_trips,
    COUNT(DISTINCT trip_id) FILTER (WHERE status = 'completed') AS completed,
    COUNT(DISTINCT trip_id) FILTER (WHERE status = 'problem') AS with_problems
FROM trips
WHERE created_at >= CURRENT_DATE;

-- Топ заказчиков по алертам за неделю
SELECT customer, COUNT(*) AS alert_count,
       COUNT(*) FILTER (WHERE severity = 'high') AS high_count
FROM alerts
WHERE created_at >= NOW() - INTERVAL '7 days'
  AND customer IS NOT NULL
GROUP BY customer
ORDER BY alert_count DESC;

-- Средние метрики LLM за день (контроль расходов)
SELECT
    llm_model,
    COUNT(*) AS messages_parsed,
    SUM(llm_tokens_used) AS total_tokens,
    AVG(parse_duration_ms)::INT AS avg_parse_ms,
    AVG(confidence)::NUMERIC(3,2) AS avg_confidence
FROM parsed_messages
WHERE created_at >= CURRENT_DATE
GROUP BY llm_model;

-- UPSERT для trips (используется агрегатором)
INSERT INTO trips (trip_id, route_from, route_to, customer, status, last_update)
VALUES ($1, $2, $3, $4, $5, NOW())
ON CONFLICT (trip_id) DO UPDATE SET
    route_from = COALESCE(EXCLUDED.route_from, trips.route_from),
    route_to = COALESCE(EXCLUDED.route_to, trips.route_to),
    customer = COALESCE(EXCLUDED.customer, trips.customer),
    status = EXCLUDED.status,
    last_update = NOW();
```
