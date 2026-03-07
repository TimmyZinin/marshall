# Marshall AI Listener — Бэклог

> **Дашборд:** https://marshall.timzinin.com (RUVDS, nginx + HTTPS)
> **Репо:** github.com/TimmyZinin/marshall
> **Спецификации:** timzinin.com/marshall/spec/
> **Ставка:** Sprint 0 FREE, далее $250/час

## Роли

| Роль в системе | Кто | Доступ |
|----------------|-----|--------|
| `manager` | Диспетчер / оператор Marshall | Дашборд: рейсы, алерты (PATCH), статистика |
| `viewer` | Руководство (Николя Бобров) | Дашборд: только просмотр |
| `admin` | Тим Зинин | Всё + управление пользователями |

> **Уточнение:** диспетчер = менеджер = оператор дашборда.

## Архитектурные решения

- **Telegram-интеграция: Bot API** (не Telethon/MTProto). Бот добавляется в групповые чаты, читает все сообщения. Надёжнее, не рискуем баном аккаунта.
- **Демо-режим (Demo Mode):** переключатель в UI и API. Когда включён — система показывает реалистичные синтетические данные (рейсы, алерты, чат-сообщения). Позволяет показать продукт до подключения реальных чатов. Toggle в TopNav: `[DEMO] / [LIVE]`.
- **Дашборд:** marshall.timzinin.com — RUVDS + nginx + Let's Encrypt.

---

## Sprint 1: Dashboard (Frontend + API + DB + Demo Mode)

**Цель:** Работающий дашборд с демо-данными на marshall.timzinin.com. Можно показать Николе Боброву. Демо-режим включён по умолчанию.

| # | Задача | Модуль | Оценка | Зависимости |
|---|--------|--------|--------|-------------|
| 1.1 | Repo setup: структура проекта, Dockerfile, docker-compose.yml (app + postgres) | Infra | 2ч | — |
| 1.2 | DNS: A-запись marshall.timzinin.com → 88.218.248.114, nginx reverse proxy + Let's Encrypt | Infra | 1ч | — |
| 1.3 | DB: миграции — 5 таблиц (dashboard_users, trips, alerts, raw_messages, parsed_messages) + индексы | DB | 3ч | 1.1 |
| 1.4 | Demo data generator: реалистичные данные — 6 заказчиков, ~50 рейсов, ~100 алертов, ~200 сообщений. Скрипт `seed_demo.py`, запускается при `DEMO_MODE=true` | DB | 3ч | 1.3 |
| 1.5 | Demo Mode: API middleware — если `DEMO_MODE=true`, данные из demo-таблиц; если `false`, из реальных. Endpoint `GET /api/config` возвращает текущий режим | API | 2ч | 1.4 |
| 1.6 | FastAPI skeleton: структура, CORS, error handling, healthcheck | API | 2ч | 1.1 |
| 1.7 | JWT auth: POST /api/auth/login, middleware, 3 роли (admin/manager/viewer) | API | 3ч | 1.6 |
| 1.8 | API endpoints: GET /api/trips, GET /api/trips/{id}, фильтры, пагинация | API | 3ч | 1.3, 1.7 |
| 1.9 | API endpoints: GET /api/alerts, PATCH /api/alerts/{id}, фильтры | API | 3ч | 1.3, 1.7 |
| 1.10 | API endpoints: GET /api/stats/summary, GET /api/stats/timeline | API | 2ч | 1.3, 1.7 |
| 1.11 | Dashboard: Login экран (email + password, JWT) | Frontend | 2ч | 1.7 |
| 1.12 | Dashboard: Active Trips — таблица рейсов, фильтры по заказчику/статусу, polling 3сек | Frontend | 4ч | 1.8 |
| 1.13 | Dashboard: Alerts Feed — карточки алертов, severity-бейджи, кнопки статусов (manager: взять в работу / решено) | Frontend | 4ч | 1.9 |
| 1.14 | Dashboard: Trip Details — инфо о рейсе + история чата + алерты по рейсу | Frontend | 3ч | 1.8, 1.9 |
| 1.15 | Dashboard: Statistics — KPI-карточки + Chart.js графики (алерты/день, по заказчикам, средняя задержка) | Frontend | 3ч | 1.10 |
| 1.16 | Dashboard: TopNav — навигация, роутинг (hash-based SPA), responsive. **Demo/Live toggle** (бейдж `DEMO` в хедере, admin может переключить) | Frontend | 2ч | 1.11 |
| 1.17 | Demo simulator: фоновый процесс, который каждые 30-60сек добавляет новый "алерт" или обновляет статус рейса в demo-данных, чтобы дашборд выглядел живым | API | 2ч | 1.4, 1.5 |
| 1.18 | Деплой Sprint 1 на RUVDS, проверка HTTPS | Deploy | 2ч | Все |
| | **Итого Sprint 1** | | **~46ч** | |

**Результат Sprint 1:** Николя Бобров открывает marshall.timzinin.com → логин → видит живой дашборд. Бейдж `DEMO` в хедере. Данные реалистичные, обновляются каждые 30-60 сек — новые алерты приходят, рейсы меняют статус. Визуально неотличимо от реальной работы.

---

## Sprint 2: Bot API Listener + AI Parser

**Цель:** Подключение к реальным Telegram-чатам через Bot API. Сообщения парсятся LLM и попадают в БД.

| # | Задача | Модуль | Оценка | Зависимости |
|---|--------|--------|--------|-------------|
| 2.1 | Telegram Bot: создание бота Marshall, настройка прав (read all messages в группах) | Listener | 1ч | — |
| 2.2 | Bot API listener: python-telegram-bot или aiogram, webhook/polling, получение всех сообщений из групповых чатов | Listener | 4ч | 2.1 |
| 2.3 | Pluggable adapter: абстракция ListenerTransport (Bot API сейчас, MTProto/Max позже) | Listener | 2ч | 2.2 |
| 2.4 | Сохранение raw_messages в PostgreSQL (chat_id, user, text, timestamp) | Listener | 1ч | 2.2 |
| 2.5 | AI Parser: промпт-шаблон для извлечения структурированных данных из сообщений диспетчеров | Parser | 3ч | — |
| 2.6 | LLM integration: MiniMax M2.5 (primary) + Groq Llama 3.3 (fallback) | Parser | 3ч | 2.5 |
| 2.7 | Парсинг → structured JSON: trip_id, route, status, customer, urgency, issue, confidence | Parser | 3ч | 2.6 |
| 2.8 | Сохранение parsed_messages в PostgreSQL | Parser | 1ч | 2.7 |
| 2.9 | Pipeline: Bot listener → asyncio.Queue → Parser → DB | Integration | 2ч | 2.4, 2.8 |
| 2.10 | Demo/Live switch: при переключении в LIVE API читает из реальных таблиц | Integration | 1ч | 2.9 |
| 2.11 | Тесты: unit + integration (pytest) | Tests | 3ч | Все |
| | **Итого Sprint 2** | | **~24ч** | |

**Результат Sprint 2:** Бот Marshall добавлен в чаты диспетчеров. Реальные сообщения парсятся и попадают в БД. Admin переключает toggle Demo → Live — дашборд показывает реальные данные.

---

## Sprint 3: Alert Engine + E2E Integration

**Цель:** Автоматическое обнаружение проблем. Полный пайплайн от сообщения до алерта в дашборде.

| # | Задача | Модуль | Оценка | Зависимости |
|---|--------|--------|--------|-------------|
| 3.1 | Alert Engine core: оценка parsed_messages по правилам, создание алертов | Alerts | 3ч | Sprint 2 |
| 3.2 | 5 типов алертов: delay, equipment_failure, safety_violation, docs_missing, general | Alerts | 2ч | 3.1 |
| 3.3 | YAML-правила по заказчикам: Тандер, WB, X5, Магнит, Сельта, Сибур | Alerts | 3ч | 3.1 |
| 3.4 | Trip aggregation: UPSERT trips из parsed_messages (группировка по trip_id) | Alerts | 2ч | 3.1 |
| 3.5 | Полный pipeline: Bot → Parser → Alert Engine → DB → Dashboard API | Integration | 3ч | 3.4 |
| 3.6 | E2E тест: сообщение в тестовый чат → алерт в дашборде за <30 сек | Tests | 2ч | 3.5 |
| 3.7 | Тесты: правила заказчиков, edge cases, confidence < threshold | Tests | 2ч | 3.3 |
| | **Итого Sprint 3** | | **~17ч** | |

**Результат Sprint 3:** Диспетчер пишет в Telegram "Рейс 4521, стою в пробке, опоздание 40 мин" → через 10-20 сек в дашборде появляется HIGH-алерт "delay" по рейсу 4521.

---

## Sprint 4: Production Deploy + Observability

**Цель:** Продакшн-готовый деплой. Мониторинг. Демо Николе Боброву.

| # | Задача | Модуль | Оценка | Зависимости |
|---|--------|--------|--------|-------------|
| 4.1 | Docker Compose production: resource limits, restart policies, env isolation | Deploy | 2ч | Sprint 3 |
| 4.2 | structlog JSON logging: все модули | Observability | 2ч | — |
| 4.3 | Healthcheck cron (5 мин) + TG-алерт при падении | Observability | 1ч | 4.2 |
| 4.4 | Security: секреты в .env, CORS whitelist, rate limiting API | Security | 2ч | — |
| 4.5 | pg_dump backup cron (daily) | Infra | 1ч | — |
| 4.6 | Тесты: полный pytest suite, coverage ≥70% | Tests | 3ч | Все |
| 4.7 | Финальный деплой на RUVDS, smoke test | Deploy | 1ч | Все |
| 4.8 | Демо-сессия: создать 3 аккаунта (admin, manager, viewer), подготовить тест-кейс для Николи | Demo | 1ч | 4.7 |
| | **Итого Sprint 4** | | **~13ч** | |

**Результат Sprint 4:** Система в продакшне. Николя Бобров логинится на marshall.timzinin.com, видит реальные данные из чатов диспетчеров, алерты, статистику.

---

## Сводка

| Sprint | Название | Часы | Результат |
|--------|----------|------|-----------|
| 1 | Dashboard + Demo Mode | ~46ч | Рабочий дашборд с живым демо-режимом на marshall.timzinin.com |
| 2 | Bot API Listener + AI Parser | ~24ч | Реальные сообщения из Telegram → БД через Bot API |
| 3 | Alert Engine + E2E | ~17ч | Автоалерты, полный pipeline, E2E |
| 4 | Production + Demo | ~13ч | Продакшн, мониторинг, демо Николе |
| **Всего** | | **~100ч** | **Полный Sprint 0 MVP** |

---

## Backlog (после Sprint 0 — платные спринты $250/час)

| Приоритет | Фича | Описание |
|-----------|-------|----------|
| P1 | Whisper STT | Голосовые сообщения → текст → парсинг |
| P1 | Интерактивный бот | Чек-листы, кнопки статусов для водителей |
| P1 | MTProto adapter | Telethon как альтернатива Bot API (чтение истории) |
| P2 | Max (VK) интеграция | TG блокируется в РФ с 1 апр 2026 |
| P2 | WebSocket | Замена polling на real-time обновления |
| P2 | Экспорт CSV/Excel | Выгрузка отчётов для руководства |
| P3 | WhatsApp/Viber | Мультиплатформа |
| P3 | OAuth/SSO | Корпоративная авторизация |
| P3 | Mobile PWA | Мобильная версия дашборда |
