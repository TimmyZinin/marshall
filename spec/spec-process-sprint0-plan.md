# План реализации Sprint 0

Marshall AI Listener — WBS, оценки, зависимости, таймлайн и критерии сдачи


**Sprint 0 — бесплатный пилот**
Показать ценность AI Listener за 2 недели: пассивное прослушивание чатов, парсинг через LLM, алерты и дашборд с метриками. Нулевые изменения для пользователей. Цель — зацепить клиента для платных спринтов ($250/час).



## Сводка плана


 
4
Фазы реализации
 
 
28
Задач в WBS
 
 
~68
Часов суммарно
 
 
14
Рабочих дней (5ч/день)
 


 

### Ключевые решения, зафиксированные в плане

 
**- Язык: Python 3.11+ — как в существующем авто-респондере

**- БД: PostgreSQL 15+ в Docker — апгрейд с SQLite для масштаба

**- Listener: Telethon (MTProto) для Sprint 0 — pluggable-адаптер, Bot API — Sprint 1

**- LLM: MiniMax M2.5 + Groq fallback — 100K бесплатных токенов/день

**- API: FastAPI — async, лёгкий, OpenAPI из коробки

**- Dashboard: HTML + Chart.js — без фреймворка, единая страница

**- Деплой: Docker Compose на RUVDS 88.218.248.114

**- Алерты: только в дашборде — никаких ботов/пушей в Sprint 0

 



## Фаза 1 — Инфраструктура и Chat Listener (S0-F01)


Фаза 1
Инфраструктура + Подключение к чатам
Задачи: P1-01 — P1-07  |  Оценка: ~16 часов  |  Зависимости: нет (стартовая точка)
Настройка репозитория, Docker-окружения, PostgreSQL и подключения к Telegram через Telethon (MTProto). Реализация Chat Listener (S0-F01) из спецификации.


 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
````
 
 
 
 
 
 
````````
 
 
 
 
 
 
 
 
 
 
 
 
 
````
 
 
 
 
 
 
 
 
 
 
 
 
 
``
 
 
 
 
 

| ID | Задача | Часы | Спека | Зависит от |
| --- | --- | --- | --- | --- |
| P1-01 | Инициализация репозитория: структура каталогов, .gitignore, .env.example, pre-commit hooks | 1 | — | — |
| P1-02 | Docker Compose: сервисы app + postgres:15, healthcheck, volumes, сети | 2 | — | P1-01 |
| P1-03 | Схема PostgreSQL: миграции Alembic для таблиц raw_messages, parsed_events, alerts, monitored_chats | 3 | Схема БД | P1-02 |
| P1-04 | Настройка структурированного JSON-логирования (python-json-logger), конфиг через Pydantic Settings | 1 | — | P1-01 |
| P1-05 | Pluggable-адаптер транспорта: абстрактный класс MessengerTransport + реализация TelethonTransport | 3 | Chat Listener | P1-04 |
| P1-06 | Chat Listener: asyncio event loop, NewMessage handler, подключение к 3 тестовым чатам + DM, rate limiting 30 msg/s | 4 | Chat Listener | P1-03, P1-05 |
| P1-07 | Сохранение raw-сообщений в raw_messages, graceful shutdown (SIGTERM/SIGINT), reconnect с backoff | 2 | Chat Listener | P1-06 |


**Риск P1: StringSession** — Telethon требует активной сессии пользовательского аккаунта Telegram. Необходимо сгенерировать StringSession для тестового аккаунта Marshall на этапе P1-05. Если аккаунт заблокируют — переключить на Bot API (P1-05 сделан как pluggable-адаптер).



## Фаза 2 — AI Parser и Alert Engine (S0-F02, S0-F03)


Фаза 2
LLM-парсинг + Алерты
Задачи: P2-01 — P2-08  |  Оценка: ~20 часов  |  Зависит от: Фаза 1 (P1-03, P1-07)
LLM-пайплайн для парсинга текстов диспетчеров. Извлечение структурированных полей. Генерация и сохранение алертов. Переиспользуем 5-слойный пайплайн из авто-респондера.


 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
``
 
 
 
 
 
 
 
 
 
 
 
 
 
````
 
 
 
 
 
 
 
 
 
 
 
 
 
``
 
 
 
 
 
 
 
 
 
 
 
 

| ID | Задача | Часы | Спека | Зависит от |
| --- | --- | --- | --- | --- |
| P2-01 | LLM-клиент: обёртка над MiniMax M2.5 API + Groq fallback (Llama 3.3 70B), retry с экспоненциальным backoff | 3 | AI Parser | P1-04 |
| P2-02 | Системный промпт для парсинга: извлечение trip_id, route_from, route_to, slot_time, status, customer, urgency, issue, confidence | 2 | AI Parser | P2-01 |
| P2-03 | Валидация и нормализация JSON-ответа LLM: Pydantic-модель ParsedEvent, обработка невалидного ответа, confidence=0 при ошибке | 2 | AI Parser | P2-02 |
| P2-04 | Кеш дедупликации: Redis или in-memory TTL 5 мин — не парсить одинаковые сообщения повторно | 2 | AI Parser | P2-03 |
| P2-05 | Сохранение parsed_events в PostgreSQL, привязка к raw_message_id, batch-запись | 2 | AI Parser | P1-03, P2-03 |
| P2-06 | Alert Engine: правила генерации алертов по urgency (high/critical), cooldown 30 мин, дедупликация по trip_id + issue_type | 3 | Alert Engine | P2-05 |
| P2-07 | Сохранение алертов в таблицу alerts: severity, status (new/acked/resolved), expires_at (TTL 24ч) | 2 | Alert Engine | P2-06, P1-03 |
| P2-08 | Интеграционный тест: синтетические сообщения из master_brief → проверка парсинга + алертов end-to-end | 4 | — | P2-07 |


 

#### Синтетические тестовые сообщения (из мастер-брифа)

Используем для тестирования парсера без реальных данных клиента:


 
**- "Рейс 4521, Москва-Краснодар, слот WB 14:00, реф охладить до +2" → urgency: low, trip_id: 4521

**- "Стою в пробке на МКАД, опаздываю минут на 40" → urgency: medium, issue: Traffic 40min

**- "Реф не выходит на температуру, показывает +8. Мастер смотрит." → urgency: high, issue: Refrigerator malfunction

**- "ДТП на М4 Дон км 680. Наш водитель НЕ участвует, но пробка" → urgency: high, issue: Road incident

 



## Фаза 3 — Dashboard API и фронтенд (S0-F04)


Фаза 3
FastAPI + HTML Дашборд
Задачи: P3-01 — P3-08  |  Оценка: ~22 часа  |  Зависит от: Фаза 2 (P2-07)
REST API на FastAPI с эндпоинтами для дашборда. Одностраничный HTML-дашборд с Chart.js. Базовая JWT-авторизация. Реалтайм-обновление через polling (SSE опционально).


 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
``
 
 
 
 
 
 
``
 
 
 
 
 
 
````
 
 
 
 
 
 
``
 
 
 
 
 
 
``
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 

| ID | Задача | Часы | Спека | Зависит от |
| --- | --- | --- | --- | --- |
| P3-01 | FastAPI приложение: структура модулей, SQLAlchemy async, зависимости, CORS | 2 | Dashboard API | P1-03 |
| P3-02 | JWT-авторизация: POST /api/auth/token, middleware проверки токена, env-конфиг пользователей | 2 | Dashboard API | P3-01 |
| P3-03 | Эндпоинт GET /api/trips: список рейсов с пагинацией, фильтрация по customer/status/urgency, сортировка | 3 | Dashboard API | P3-02, P2-05 |
| P3-04 | Эндпоинт GET /api/alerts: список алертов (new/acked/resolved), PATCH /api/alerts/{id}/ack | 3 | Dashboard API | P3-02, P2-07 |
| P3-05 | Эндпоинт GET /api/stats: агрегаты за период — total_trips, active_alerts, by_urgency, by_customer, messages_today | 2 | Dashboard API | P3-03, P3-04 |
| P3-06 | Эндпоинт GET /api/chats: список мониторируемых чатов, статус подключения, last_message_at | 1 | Dashboard API | P3-02 |
| P3-07 | HTML-дашборд: лента алертов (real-time polling 10s), KPI-карточки (trips/alerts/messages), статус чатов | 5 | Дизайн | P3-04, P3-05 |
| P3-08 | Графики Chart.js: urgency distribution (pie), активность по часам (line), рейсы по заказчикам (bar) | 4 | Дизайн | P3-07 |



## Фаза 4 — Деплой, тестирование и сдача


Фаза 4
Деплой + QA + Документация
Задачи: P4-01 — P4-06  |  Оценка: ~10 часов  |  Зависит от: Фаза 3 (P3-08)
Деплой Docker Compose на RUVDS, настройка nginx, unit и интеграционные тесты, документация для передачи Marshall.


 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 

| ID | Задача | Часы | Зависит от |
| --- | --- | --- | --- |
| P4-01 | Деплой Docker Compose на RUVDS (88.218.248.114): docker compose up -d, проверка healthcheck | 2 | P3-08 |
| P4-02 | nginx reverse proxy: дашборд на внешнем порту, SSL/HTTPS (Let's Encrypt или self-signed), basic auth как второй слой | 2 | P4-01 |
| P4-03 | Unit-тесты pytest: парсер (10 тест-кейсов с синтетическими данными), alert rules (5 кейсов), API endpoints (mock DB) | 3 | P2-08 |
| P4-04 | E2E smoke-тест: chat listener запущен, 3 синтетических сообщения → parsed → alert → виден в дашборде | 1 | P4-01, P4-03 |
| P4-05 | README.md: инструкция деплоя, .env переменные, как добавить новый чат, troubleshooting | 1 | P4-04 |
| P4-06 | Демо Marshall: подготовка 10-минутной демонстрации с синтетическими данными, доступ к дашборду | 1 | P4-05 |



## Сводка часов по фазам и модулям


 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 

| Фаза | Модуль / Задача | Задачи | Часов | Доля |
| --- | --- | --- | --- | --- |
| Фаза 1 | Инфраструктура + Chat Listener (S0-F01) | P1-01 — P1-07 | 16 | 24% |
| Фаза 2 | AI Parser (S0-F02) + Alert Engine (S0-F03) | P2-01 — P2-08 | 20 | 29% |
| Фаза 3 | Dashboard API + Frontend (S0-F04) | P3-01 — P3-08 | 22 | 32% |
| Фаза 4 | Деплой + QA + Документация | P4-01 — P4-06 | 10 | 15% |
| ИТОГО | ~68 | 100% |



## Диаграмма Гантта (2 недели)


gantt
title Marshall AI Listener — Sprint 0 (14 рабочих дней)
dateFormat YYYY-MM-DD
axisFormat %d.%m

section Фаза 1: Инфраструктура
P1-01 Репо и структура :done, p101, 2026-03-09, 1d
P1-02 Docker Compose :done, p102, after p101, 1d
P1-03 Схема БД (Alembic) :active, p103, after p102, 1d
P1-04 Логирование и конфиг : p104, 2026-03-09, 1d
P1-05 MessengerTransport адаптер: p105, after p104, 1d
P1-06 Chat Listener asyncio : p106, after p105, 1d
P1-07 Сохранение + shutdown : p107, after p106, 1d

section Фаза 2: AI Parser + Alerts
P2-01 LLM-клиент (MiniMax+Groq) : p201, after p104, 1d
P2-02 Промпт для парсинга : p202, after p201, 1d
P2-03 Pydantic ParsedEvent : p203, after p202, 1d
P2-04 Кеш дедупликации : p204, after p203, 1d
P2-05 Сохранение parsed_events : p205, after p203, 1d
P2-06 Alert Engine (правила) : p206, after p205, 1d
P2-07 Сохранение алертов : p207, after p206, 1d
P2-08 Интеграционный тест : p208, after p207, 1d

section Фаза 3: API + Dashboard
P3-01 FastAPI приложение : p301, after p103, 1d
P3-02 JWT авторизация : p302, after p301, 1d
P3-03 GET /api/trips : p303, after p302, 1d
P3-04 GET /api/alerts + PATCH : p304, after p302, 1d
P3-05 GET /api/stats : p305, after p303, 1d
P3-06 GET /api/chats : p306, after p302, 1d
P3-07 HTML дашборд : p307, after p304, 2d
P3-08 Chart.js графики : p308, after p307, 1d

section Фаза 4: Деплой + QA
P4-01 Docker Compose на RUVDS : p401, after p308, 1d
P4-02 nginx + SSL : p402, after p401, 1d
P4-03 Unit-тесты pytest : p403, after p208, 1d
P4-04 E2E smoke-тест : p404, after p402, 1d
P4-05 README.md : p405, after p404, 1d
P4-06 Демо Marshall :milestone, p406, after p405, 0d



## Карта зависимостей между задачами


flowchart TD
P101[P1-01\nРепозиторий] --> P102[P1-02\nDocker Compose]
P102 --> P103[P1-03\nСхема БД]
P101 --> P104[P1-04\nЛогирование]
P104 --> P105[P1-05\nTransport Adapter]
P103 --> P106[P1-06\nChat Listener]
P105 --> P106
P106 --> P107[P1-07\nГрейсфул shutdown]

P104 --> P201[P2-01\nLLM Client]
P201 --> P202[P2-02\nПромпт]
P202 --> P203[P2-03\nParsedEvent]
P203 --> P204[P2-04\nДедупликация]
P203 --> P205[P2-05\nparsed_events БД]
P103 --> P205
P205 --> P206[P2-06\nAlert Engine]
P206 --> P207[P2-07\nalerts БД]
P207 --> P208[P2-08\nИнтеграционный тест]

P103 --> P301[P3-01\nFastAPI]
P301 --> P302[P3-02\nJWT Auth]
P302 --> P303[P3-03\n/api/trips]
P302 --> P304[P3-04\n/api/alerts]
P302 --> P306[P3-06\n/api/chats]
P205 --> P303
P207 --> P304
P303 --> P305[P3-05\n/api/stats]
P304 --> P305
P305 --> P307[P3-07\nHTML Dashboard]
P304 --> P307
P307 --> P308[P3-08\nChart.js]

P308 --> P401[P4-01\nДеплой RUVDS]
P401 --> P402[P4-02\nnginx + SSL]
P208 --> P403[P4-03\nUnit тесты]
P402 --> P404[P4-04\nE2E тест]
P403 --> P404
P404 --> P405[P4-05\nREADME]
P405 --> P406[P4-06\nДемо]

style P406 fill:#10b981,color:#fff,stroke:#059669
style P101 fill:#2563eb,color:#fff,stroke:#1d4ed8



## Структура файлов проекта


```

marshall-ai-listener/
├── docker-compose.yml # app + postgres + (redis опционально)
├── Dockerfile
├── .env.example # шаблон переменных окружения
├── .gitignore
├── README.md
├── requirements.txt
│
├── alembic/ # миграции PostgreSQL
│ ├── env.py
│ ├── versions/
│ │ ├── 001_initial_schema.py
│ │ └── ...
│ └── alembic.ini
│
├── app/
│ ├── __init__.py
│ ├── main.py # точка входа: listener + FastAPI
│ ├── config.py # Pydantic Settings (из .env)
│ │
│ ├── listener/ # S0-F01: Chat Listener
│ │ ├── __init__.py
│ │ ├── base.py # абстрактный MessengerTransport
│ │ ├── telethon_transport.py # Telethon (MTProto)
│ │ └── event_handler.py # asyncio NewMessage → raw_messages
│ │
│ ├── parser/ # S0-F02: AI Parser
│ │ ├── __init__.py
│ │ ├── llm_client.py # MiniMax + Groq fallback
│ │ ├── prompts.py # системный промпт
│ │ ├── models.py # Pydantic: ParsedEvent
│ │ └── pipeline.py # orchestration: raw → parsed
│ │
│ ├── alerts/ # S0-F03: Alert Engine
│ │ ├── __init__.py
│ │ ├── rules.py # правила генерации алертов
│ │ └── engine.py # processed event → alert
│ │
│ ├── api/ # S0-F04: Dashboard API
│ │ ├── __init__.py
│ │ ├── app.py # FastAPI instance
│ │ ├── auth.py # JWT middleware
│ │ ├── routes/
│ │ │ ├── trips.py # GET /api/trips
│ │ │ ├── alerts.py # GET/PATCH /api/alerts
│ │ │ ├── stats.py # GET /api/stats
│ │ │ └── chats.py # GET /api/chats
│ │ └── schemas.py # Pydantic response models
│ │
│ ├── db/
│ │ ├── __init__.py
│ │ ├── session.py # SQLAlchemy async engine
│ │ └── models.py # ORM: RawMessage, ParsedEvent, Alert, MonitoredChat
│ │
│ └── dashboard/
│ └── index.html # SPA дашборд (Chart.js, polling)
│
└── tests/
├── conftest.py
├── test_parser.py # 10 тест-кейсов парсера
├── test_alert_rules.py # 5 тест-кейсов алертов
└── test_api.py # API эндпоинты (mock DB)

```



## Шаблон переменных окружения


```


# ======== Telegram / Telethon ========
TG_API_ID=your_api_id
TG_API_HASH=your_api_hash
TG_STRING_SESSION=your_string_session


# Режим подключения: mtproto | bot
LISTENER_MODE=mtproto


# Chat IDs для мониторинга (через запятую)
MONITORED_CHAT_IDS=-100123456789,-100987654321,-100111222333


# ======== LLM ========
MINIMAX_API_KEY=your_minimax_key
MINIMAX_GROUP_ID=your_group_id
GROQ_API_KEY=your_groq_key


# ======== PostgreSQL ========
DATABASE_URL=postgresql+asyncpg://marshall:secret@postgres:5432/marshall_listener


# ======== FastAPI / Dashboard ========
SECRET_KEY=your_jwt_secret_key_min_32_chars
DASHBOARD_USERNAME=manager
DASHBOARD_PASSWORD=your_secure_password


# ======== App Config ========
RATE_LIMIT_MESSAGES_PER_SEC=30
ALERT_COOLDOWN_MINUTES=30
DEDUP_CACHE_TTL_MINUTES=5
LOG_LEVEL=INFO

```



## Риски и план митигации


 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 

| Риск | Вероятность | Влияние | Митигация |
| --- | --- | --- | --- |
| Telegram заблокирует аккаунт (StringSession) | Средняя | Высокое | Pluggable-адаптер — переключить на Bot API за 1 час. Тестовый аккаунт, не аккаунт сотрудника. |
| MiniMax API недоступен / rate limit | Низкая | Среднее | Groq fallback (Llama 3.3 70B, 100K токенов/день). Retry с backoff уже в P2-01. |
| Telegram блокировка в РФ (1 апреля 2026) | Высокая | Высокое | Sprint 0 завершается до 1 апреля. Sprint 1 — Max (VK) как основная платформа. |
| LLM парсит неточно (confidence < 0.7) | Средняя | Низкое | Флаг для ревью в дашборде. Синтетические тесты для калибровки промпта на этапе P2-02. |
| PostgreSQL медленно на RUVDS | Низкая | Низкое | Индексы на chat_id, created_at, urgency — заложены в Alembic-миграции (P1-03). |
| Нет реальных данных клиента для тестирования | Гарантировано | Низкое | Синтетические данные из master_brief достаточны для демо. Реальные подключаются при сдаче. |



## Definition of Done (DoD) — Критерии сдачи Sprint 0


Sprint 0 считается завершённым, когда ВСЕ следующие пункты выполнены:


 

### Техническая готовность

 
- Chat Listener подключён к 3 тестовым чатам Telegram, захватывает сообщения в реальном времени (<100 мс)

- AI Parser обрабатывает все 4 синтетических сообщения с confidence ≥ 0.8 для структурированных и ≥ 0.7 для неструктурированных

- Alert Engine генерирует алерты для urgency=high/critical с дедупликацией по cooldown 30 мин

- Dashboard API: все 4 эндпоинта (/trips, /alerts, /stats, /chats) возвращают корректные данные

- HTML дашборд отображает ленту алертов, KPI-карточки и графики, обновляется автоматически каждые 10 секунд

- JWT-авторизация работает: неавторизованный запрос к /api/ возвращает 401

``- Docker Compose запускается командой docker compose up -d без ошибок, все healthcheck'и зелёные

- Система задеплоена на RUVDS (88.218.248.114), дашборд доступен по HTTPS

 


 

### Качество кода

 
- pytest: минимум 15 тест-кейсов, 0 failures (10 парсер + 5 alert rules)

- E2E smoke-тест: синтетическое сообщение → parsed_event → alert → виден в дашборде за <5 секунд

- Структурированное JSON-логирование: все критические ошибки логируются с контекстом (chat_id, message_id, error)

- Секретов нет в репозитории: .env в .gitignore, только .env.example в git

 


 

### Готовность к демо

 
- README.md: инструкция деплоя за <30 минут, описание всех .env переменных

- Синтетические данные загружены в БД: минимум 5 рейсов, 3 алерта разных severity

- Доступ к дашборду передан команде Marshall (URL + credentials)

- 10-минутная демонстрация проведена: listener → parser → alert → дашборд в реальном времени

 



## Что НЕ входит в Sprint 0


Следующие функции намеренно исключены из Sprint 0 и перенесены в платные спринты ($250/час):


 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
| Функция | Спринт | Обоснование |
| --- | --- | --- |
| Bot API транспорт (Telegram Bot) | Sprint 1 | Требует добавления бота в каждый чат клиента |
| Max (VK), WhatsApp, Viber | Sprint 1+ | Сначала показываем ценность на Telegram |
| STT (Whisper, голосовые сообщения) | Sprint 1 | Дополнительные расходы на инференс |
| Интерактивный бот для водителей | Sprint 1 | Нарушает принцип "нулевых изменений" для пилота |
| Чек-листы и кнопки статусов | Sprint 1 | Sprint 0 — только пассивное наблюдение |
| Интеграция с АРМ / ТМС Marshall | Sprint 2+ | Нет API доступа, нужно отдельное соглашение |
| Алерты в Telegram / push-уведомления | Sprint 1 | Sprint 0 — алерты только в дашборде |
| Многопользовательская авторизация / роли | Sprint 2 | В пилоте достаточно одного логина |
| Контроль документов (ТСД, термограммы) | Sprint 1 | Вне скоупа пассивного прослушивания |
| МОВИЗОР / GPS-интеграция | Sprint 2+ | Подключает только диспетчер вручную |



## Следующие шаги после Sprint 0


 

### Если демо успешно — Sprint 1 ($250/час)

 
- Подключение к реальным чатам диспетчеров Marshall (~7 аккаунтов)

- Bot API транспорт как альтернатива MTProto

- Интерактивный бот для водителей: кнопки статусов, чек-листы

- Whisper STT — голосовые сообщения водителей

- Max (VK) адаптер — готовность к блокировке Telegram 1 апреля 2026

- Push-уведомления алертов в Telegram менеджерам

- Контроль документов (ТСД, термограммы, фотоотчёты)

 


 

### Параллельно — коммерческое предложение

После демо подготовить ROI-расчёт на основе реальных данных:


 
**- Средний рейс Marshall: ~80 000 руб. Штраф 30% (срыв) = 24 000 руб потерь

- Если система предотвращает 1 штраф в месяц — окупаемость за 1 месяц

- Целевая аудитория: 500+ партнёров-перевозчиков Marshall как SaaS