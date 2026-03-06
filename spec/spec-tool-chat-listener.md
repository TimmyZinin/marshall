---
title: Marshall AI Listener — Спецификация Chat Listener (S0-F01)
version: "1.0"
date_created: 2026-03-06
owner: Тим Зинин (Zinin Corp)
tags: [tool, chat-listener, telegram, mtproto, sprint-0]
---

# Спецификация Chat Listener (S0-F01)

## Введение

Chat Listener (S0-F01) — первая компонента системы Marshall AI Listener, ответственная за пассивное подключение к Telegram-чатам диспетчеров и сбор текстовых сообщений. Модуль читает сообщения в реальном времени без отправки ответов, сохраняет raw-данные в PostgreSQL и передаёт информацию в AI Parser для дальнейшей обработки.

**Главный принцип:** нулевые изменения в работе людей. Диспетчеры пишут как обычно, система просто слушает и структурирует.

---

## 1. Цель и скоуп

### 1.1 Цель модуля

Обеспечить подключение к групповым чатам Telegram-диспетчеров, захватить ВСЕ текстовые сообщения (включая прямые сообщения) и сохранить raw-сообщения в структурированном формате для анализа AI Parser.

### 1.2 Границы скоупа

**Входит в скоуп:**
- Подключение через Telethon (MTProto) как основной транспорт для Sprint 0
- Чтение из 3 заранее выбранных групповых чатов (test-группы) + DM
- Асинхронный event listener на asyncio
- Сохранение raw-сообщений в таблицу `raw_messages`
- Graceful shutdown при SIGTERM/SIGINT
- Структурированное JSON-логирование
- Rate limiting (30 сообщений/сек)
- Обработка ошибок подключения и автоподключение
- Pluggable-адаптер: интерфейс для будущего Bot API и других мессенджеров

**Выходит из скоупа:**
- Bot API (будущий Sprint 1)
- Max, WhatsApp, Viber (будущие спринты)
- Голос, аудио-сообщения (будущий Sprint 1 с STT)
- Файлы, фото, документы (только текст)
- История сообщений старше 30 дней
- Отправка сообщений (только чтение)
- Ответы, реакции на сообщения

---

## 2. Определения

| Термин | Определение |
|--------|------------|
| **MTProto** | Собственный протокол Telegram для подключения клиентов, используется в Telethon |
| **Telethon** | Python-библиотека для работы с Telegram API через MTProto |
| **StringSession** | Сериализованная сессия Telethon, хранит токены доступа и состояние подключения |
| **Pluggable-адаптер** | Интерфейс, позволяющий переключать различные транспорты (MTProto, Bot API, Max) без изменения основной логики |
| **Event Listener** | Асинхронный обработчик событий (NewMessage), запускающийся при получении нового сообщения |
| **Raw message** | Неструктурированное текстовое сообщение из чата, сохранённое как есть без парсинга |
| **DM (Direct Message)** | Приватное сообщение от пользователя напрямую, не в групповом чате |
| **Chat ID** | Уникальный идентификатор чата в Telegram (положительный для групп, отрицательный) |
| **User ID** | Уникальный идентификатор пользователя в Telegram |
| **Message ID** | Уникальный идентификатор сообщения в пределах чата |
| **Rate limiting** | Механизм ограничения частоты обработки событий для защиты от перегруза |
| **Graceful shutdown** | Плавное завершение работы с закрытием соединений и очистки ресурсов |

---

## 3. Требования, ограничения и рекомендации

### 3.1 Функциональные требования (REQ-CL)

#### REQ-CL-001: Подключение через Telethon
**Описание:** Модуль должен подключиться к Telegram через Telethon, используя StringSession из переменной окружения `TG_SESSION_STRING`.

**Деталь:** Аутентификация происходит один раз при старте. При повторном запуске система использует сохранённую сессию без повторной авторизации.

**Приём:** Если StringSession невалидна или истекла → ошибка с логированием, система не запускается.

---

#### REQ-CL-002: Чтение из 3 групповых чатов
**Описание:** Система подключается к трём заранее выбранным чатам, IDs которых указаны в конфигурации (.env переменная `LISTENER_CHAT_IDS` как JSON-массив).

**Деталь:** Чаты загружаются при старте, хранятся в памяти. Если один чат недоступен (удалён, аккаунт выбит из чата) → логируется warning, система продолжает работать с остальными.

**Приём:** При запуске логируется успешно подключено N чатов из M. N должен быть ≥1, иначе warning.

---

#### REQ-CL-003: Чтение прямых сообщений (DM)
**Описание:** Система должна перехватывать входящие сообщения в личные чаты (DM), отправленные любыми участниками системы.

**Деталь:** DM обрабатываются как отдельный вид "чата", с chat_id == sender_id. Это позволяет диспетчерам писать Listener напрямую.

**Приём:** При получении DM система сохраняет его в `raw_messages` с пометкой is_direct_message=true.

---

#### REQ-CL-004: Event Listener на NewMessage
**Описание:** Модуль должен использовать asyncio event handler Telethon для захвата новых сообщений в реальном времени.

**Деталь:** Используется `@client.on(events.NewMessage(...))` с фильтром на чаты из конфигурации. При получении сообщения запускается асинхронная функция-обработчик.

**Приём:** Сообщение захватывается и обработано за <100 мс (задержка передачи в очередь AI Parser).

---

#### REQ-CL-005: Сохранение raw-сообщений в PostgreSQL
**Описание:** Каждое полученное сообщение сохраняется в таблицу `raw_messages` с полными metadata.

**Структура записи:**
```
- raw_message_id (SERIAL PRIMARY KEY)
- chat_id (INTEGER) — ID чата в Telegram
- message_id (INTEGER) — ID сообщения в Telegram (уникален в пределах чата)
- sender_id (INTEGER) — ID отправителя (User ID)
- sender_name (VARCHAR) — Имя/никнейм отправителя
- text (TEXT) — Полный текст сообщения (без форматирования, plain text)
- timestamp (TIMESTAMP) — Время получения сообщения (UTC)
- created_at (TIMESTAMP) — Время сохранения в БД (UTC)
- is_direct_message (BOOLEAN DEFAULT false) — True если это DM, false если групповой чат
- raw_data_json (JSONB) — Полный JSON с metadata (forward_from, reply_to_msg_id, etc.)
```

**Приём:** Для каждого поступившего сообщения существует запись в таблице за <200 мс.

---

#### REQ-CL-006: Только текстовые сообщения
**Описание:** Система обрабатывает ТОЛЬКО текстовые сообщения. Игнорирует голосовые сообщения, фото, видео, документы, стикеры, геолокацию и прочие медиа.

**Деталь:** При получении мультимедийного сообщения система логирует факт (для статистики), но не сохраняет в `raw_messages`.

**Приём:** Сообщение без text-контента → пропущено, не сохранено в БД.

---

#### REQ-CL-007: Передача в AI Parser
**Описание:** После сохранения в `raw_messages`, сообщение должно быть передано в следующий модуль (AI Parser) для обработки.

**Интерфейс:** Передача происходит через asyncio queue с объектом содержащим:
```python
{
    "raw_message_id": int,
    "chat_id": int,
    "text": str,
    "sender_name": str,
    "timestamp": datetime,
    "is_direct_message": bool
}
```

**Приём:** После сохранения в БД сообщение помещено в очередь в течение 50 мс.

---

#### REQ-CL-008: Rate limiting 30 сообщений/сек
**Описание:** Система должна ограничивать обработку сообщений до 30 в секунду для защиты от перегруза LLM и БД.

**Деталь:** Превышающие лимит сообщения помещаются в очередь диска (SQLite буфер). При восстановлении пропускная способность сообщение обрабатывается из очереди.

**Приём:** При нагрузке >30/сек система логирует "Rate limit hit, N messages queued" и обрабатывает их в порядке очереди без потерь.

---

#### REQ-CL-009: Graceful shutdown
**Описание:** При получении сигнала SIGTERM или SIGINT (ctrl+c) система должна плавно завершиться без потери данных.

**Процесс:**
1. Прекратить приём новых событий
2. Дождаться завершения обработки очереди (max 30 сек timeout)
3. Закрыть соединение с Telegram
4. Закрыть соединение с PostgreSQL
5. Завершиться с exit code 0

**Приём:** После SIGTERM → логирование "Shutdown initiated", очередь обработана, соединения закрыты за <5 сек.

---

#### REQ-CL-010: Структурированное логирование (JSON)
**Описание:** Все события (подключение, сообщение, ошибка, shutdown) логируются в формате JSON для удобства парсинга.

**Формат:**
```json
{
  "timestamp": "2026-03-06T14:32:10.123Z",
  "level": "INFO",
  "component": "ChatListener",
  "event": "message_received",
  "raw_message_id": 12345,
  "chat_id": -1001234567890,
  "sender_id": 987654321,
  "text_length": 45,
  "processing_time_ms": 87
}
```

**Приём:** Каждая значимая операция залогирована. Логи отправляются в stdout (Docker подхватит).

---

#### REQ-CL-011: Автоподключение при разрыве соединения
**Описание:** Если соединение с Telegram разорвано (таймаут, сеть упала), система должна попытаться переподключиться с экспоненциальной задержкой.

**Стратегия:**
- 1-й раз: 5 сек
- 2-й раз: 10 сек
- 3-й раз: 20 сек
- 4-й раз и далее: 60 сек (max)
- После 5 неудачных попыток → graceful shutdown с ошибкой

**Приём:** При разрыве логируется "Connection lost, reconnecting in X sec", сообщения новые не приходят, но система не падает.

---

#### REQ-CL-012: Обработка ошибок БД
**Описание:** При ошибке сохранения в PostgreSQL система должна логировать ошибку и повторить попытку 3 раза с экспоненциальной задержкой.

**Деталь:** Если после 3 попыток БД недоступна → поместить сообщение в очередь диска (на будущую обработку). Система продолжает слушать новые сообщения.

**Приём:** При отказе БД → логируется "DB error, retrying (attempt X/3)", затем сообщение в очередь диска.

---

### 3.2 Ограничения (CON-CL)

#### CON-CL-001: Только Sprint 0 — MTProto
**Описание:** На Sprint 0 используется ТОЛЬКО Telethon (MTProto). Bot API отложена на Sprint 1.

**Риск:** Риск бана аккаунта Telegram при активном использовании. Требуется сервисный аккаунт (не личный диспетчера).

**Смягчение:** Используется отдельный номер телефона для сессии, логируются все операции для аудита.

---

#### CON-CL-002: Нет интеграции с АРМ Marshall
**Описание:** Chat Listener НЕ подключается к АРМ Marshall, не читает API Marshall. Sprint 0 автономен.

**Последствие:** Нет возможности привязать trip_id из сообщения к данным АРМ. Это делается в следующих спринтах.

---

#### CON-CL-003: Только текст, no media
**Описание:** Система игнорирует все мультимедийные сообщения (фото, видео, голос, документы).

**Обоснование:** STT и распознавание документов требуют специальной обработки и отложены на платные спринты.

---

#### CON-CL-004: История ≤30 дней
**Описание:** При подключении система может загрузить последние 30 дней истории каждого чата. Старшую историю загружать дорого и не нужно для пилота.

**Практика:** При запуске система загружает историю за последние 7 дней (компромисс между покрытием и скоростью).

---

#### CON-CL-005: 3 тестовых чата
**Описание:** Sprint 0 подключается к 3 тестовым чатам, созданным для разработки и демонстрации. В production будут все чаты диспетчеров (7-10 групп).

**Практика:** Конфигурация через .env позволяет легко добавить новые чаты.

---

### 3.3 Рекомендации (GUD-CL)

#### GUD-CL-001: Сохранить контекст отправителя
**Рекомендация:** Для каждого сообщения сохранять полное имя/никнейм отправителя (sender_name). Это помогает при парсинге + аналитике.

**Пример:** "Диспетчер Алексей" вместо "Алексей" — более специфично.

---

#### GUD-CL-002: Логировать версию Telethon и TG API
**Рекомендация:** При старте логировать версию используемых библиотек для отладки.

**Пример:**
```json
{
  "event": "startup",
  "telethon_version": "1.34.0",
  "telegram_api_version": "183"
}
```

---

#### GUD-CL-003: Метрика: сообщения в секунду
**Рекомендация:** Отслеживать в логах средний throughput (сообщений в секунду) для мониторинга нагрузки и оптимизации.

---

#### GUD-CL-004: Тестовые данные: синтетические сообщения
**Рекомендация:** Создать скрипт генерации синтетических сообщений в test-чаты для нагрузочного тестирования без зависимости от реальных данных.

---

#### GUD-CL-005: Pluggable-адаптер — создать интерфейс NOW
**Рекомендация:** Хотя Bot API отложена на Sprint 1, создать абстракцию TransportAdapter прямо в Chat Listener, чтобы переключение было простым.

**Архитектура:**
```python
class TransportAdapter:
    async def connect(self, config: Dict) -> None: ...
    async def listen(self) -> AsyncGenerator[RawMessage]: ...
    async def disconnect(self) -> None: ...

class TelethonAdapter(TransportAdapter): ...
class BotAPIAdapter(TransportAdapter): ...  # Пусто, заглушка на Sprint 1

listener = ChatListener(transport=TelethonAdapter(...))
```

---

## 4. Интерфейсы и контракты данных

### 4.1 Конфигурация (входные переменные окружения)

```bash
# .env файл
LISTENER_MODE=mtproto                    # mtproto | bot_api (будущее)
TG_SESSION_STRING=<string_session_base64> # Telethon StringSession
LISTENER_CHAT_IDS='[-1001234567890, -1009876543210, -1005555555555]'  # JSON array
LISTENER_RATE_LIMIT=30                   # сообщений в сек
LISTENER_HISTORY_DAYS=7                  # дней истории при подключении
DB_HOST=localhost
DB_PORT=5432
DB_NAME=marshall_listener
DB_USER=postgres
DB_PASSWORD=<password>
LOG_LEVEL=INFO                           # DEBUG | INFO | WARNING | ERROR
SHUTDOWN_TIMEOUT=30                      # сек для graceful shutdown
QUEUE_BUFFER_PATH=/tmp/listener_queue.db # SQLite буфер для rate limiting
```

---

### 4.2 Структура данных: RawMessage (Python класс)

```python
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Dict

@dataclass
class RawMessage:
    """Сырое сообщение из Telegram"""
    chat_id: int                    # ID чата (-1001234567890)
    message_id: int                 # ID сообщения в чате (12345)
    sender_id: int                  # User ID отправителя (987654321)
    sender_name: str                # Имя/никнейм отправителя
    text: str                       # Полный текст сообщения
    timestamp: datetime             # Время отправки (UTC)
    is_direct_message: bool = False # True если DM, False если группа
    raw_data_json: Dict = None      # Полный JSON с Telegram metadata
```

---

### 4.3 Таблица PostgreSQL: raw_messages

```sql
CREATE TABLE raw_messages (
    raw_message_id SERIAL PRIMARY KEY,
    chat_id BIGINT NOT NULL,              -- ID чата Telegram
    message_id BIGINT NOT NULL,           -- ID сообщения в чате
    sender_id BIGINT NOT NULL,            -- ID отправителя
    sender_name VARCHAR(255),             -- Имя отправителя
    text TEXT NOT NULL,                   -- Полный текст
    timestamp TIMESTAMP WITH TIME ZONE,   -- Время отправки
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    is_direct_message BOOLEAN DEFAULT false,
    raw_data_json JSONB,                  -- Полный JSON Telegram

    -- Индексы для быстрого поиска
    INDEX idx_chat_timestamp ON raw_messages(chat_id, timestamp DESC),
    INDEX idx_sender_id ON raw_messages(sender_id),
    INDEX idx_timestamp ON raw_messages(timestamp DESC),
    INDEX idx_is_direct_message ON raw_messages(is_direct_message)
);

-- Партиционирование по времени (для больших объёмов)
-- Для Sprint 0 можно опустить, добавить в Sprint 1
```

---

### 4.4 Очередь для AI Parser (asyncio.Queue)

**Интерфейс отправки в Parser:**

```python
message_queue: asyncio.Queue[ProcessingMessage]

@dataclass
class ProcessingMessage:
    """Сообщение для передачи в AI Parser"""
    raw_message_id: int
    chat_id: int
    text: str
    sender_name: str
    timestamp: datetime
    is_direct_message: bool
```

**Использование в Parser:**
```python
while True:
    msg = await message_queue.get()
    parsed_data = await ai_parser.parse(msg)
    # сохранить в parsed_data таблицу
    message_queue.task_done()
```

---

### 4.5 Обработка ошибок (контракт исключений)

```python
class ChatListenerError(Exception):
    """Базовое исключение Chat Listener"""
    pass

class ConnectionError(ChatListenerError):
    """Ошибка подключения к Telegram"""
    pass

class DatabaseError(ChatListenerError):
    """Ошибка БД"""
    pass

class ConfigError(ChatListenerError):
    """Ошибка конфигурации"""
    pass

class ShutdownError(ChatListenerError):
    """Ошибка при shutdown"""
    pass
```

---

## 5. Критерии приёмки (Acceptance Criteria)

### AC-CL-001: Telethon подключение
**Given** переменная окружения `TG_SESSION_STRING` содержит валидную StringSession
**When** система запущена
**Then** она подключается к Telegram за <5 сек и логирует "Connected to Telegram"
**And** обработчик NewMessage зарегистрирован

---

### AC-CL-002: Чтение из 3 чатов
**Given** 3 чата с IDs из `LISTENER_CHAT_IDS` активны и аккаунт добавлен в них
**When** система запущена
**Then** логируется "Listening to 3 chats" (или "Listening to N chats")
**And** при новом сообщении в чат N события попадают в обработчик

---

### AC-CL-003: Захват DM
**Given** другой пользователь отправляет DM в аккаунт системы
**When** сообщение доставлено в Telegram
**Then** оно захватывается, сохраняется с `is_direct_message=true`
**And** попадает в очередь Parser

---

### AC-CL-004: Сохранение в БД за <200 мс
**Given** новое сообщение получено из Telegram
**When** обработка начата
**Then** запись в таблицу `raw_messages` выполнена за <200 мс
**And** timestamp и created_at корректны (UTC)

---

### AC-CL-005: Только текст, no media
**Given** в чат отправлено фото, видео или стикер (без text)
**When** обработчик получает событие
**Then** сообщение логируется как "skipped_media_message"
**And** в таблицу `raw_messages` запись НЕ добавляется

---

### AC-CL-006: Передача в очередь Parser
**Given** текстовое сообщение сохранено в БД
**When** INSERT выполнен
**Then** объект `ProcessingMessage` помещён в `message_queue`
**And** очередь содержит >0 элементов

---

### AC-CL-007: Rate limit 30/сек
**Given** в течение 1 сек поступает 50 сообщений
**When** обработка начата
**Then** первые 30 обработаны синхронно
**And** оставшиеся 20 помещены в диск-буфер (SQLite)
**And** логируется "Rate limit hit, 20 messages queued"
**And** буферизованные сообщения обработаны после, в порядке очереди

---

### AC-CL-008: Graceful shutdown
**Given** система работает и обрабатывает сообщения
**When** отправлен сигнал SIGTERM (kill -15 pid)
**Then** логируется "Shutdown initiated"
**And** очередь сообщений обработана (или timeout 30 сек)
**And** соединения закрыты
**And** процесс завершился с exit code 0

---

### AC-CL-009: JSON-логирование
**Given** система работает
**When** происходит любое событие (start, message, error, shutdown)
**Then** каждое событие залогировано в формате JSON
**And** JSON содержит поля: timestamp, level, component, event, релевантные данные
**And** логи выводятся в stdout (подхватываются Docker)

---

### AC-CL-010: Автоподключение
**Given** соединение с Telegram разорвано
**When** connection.close() получено
**Then** логируется "Connection lost, reconnecting in 5 sec"
**And** система ждёт 5 сек и пытается переподключиться
**And** если успех → логируется "Reconnected", обработка продолжается
**And** если 5 попыток неудачны → graceful shutdown с ошибкой

---

### AC-CL-011: Обработка ошибок БД
**Given** PostgreSQL недоступна при попытке INSERT
**When** выполняется сохранение сообщения
**Then** логируется "DB error: [error message], retrying (attempt 1/3)"
**And** делается 3 попытки с паузами (1 сек, 2 сек, 3 сек)
**And** если все 3 неудачны → сообщение помещено в диск-буфер (SQLite)
**And** сообщение из буфера обработано когда БД восстановится

---

### AC-CL-012: Pluggable-адаптер (интерфейс)
**Given** код Chat Listener содержит абстракцию `TransportAdapter`
**When** инициализируется Chat Listener
**Then** можно передать любой адаптер (TelethonAdapter, BotAPIAdapter)
**And** интерфейс одинаков (connect, listen, disconnect)
**And** переключение на другой транспорт требует изменение только 1 строки конфигурации

---

## 6. Стратегия тестирования

### 6.1 Unit-тесты

**Модули для тестирования:**
1. `test_config.py` — парсинг конфигурации, валидация переменных окружения
2. `test_raw_message.py` — класс RawMessage, сериализация, десериализация
3. `test_queue.py` — asyncio queue, добавление/удаление элементов
4. `test_rate_limiter.py` — алгоритм rate limiting, диск-буфер

**Примеры тестов:**

```python
# test_config.py
def test_config_from_env():
    """Конфиг успешно парсится из .env"""
    os.environ['LISTENER_MODE'] = 'mtproto'
    config = load_config()
    assert config.listener_mode == 'mtproto'

def test_config_invalid_json():
    """Невалидный JSON в LISTENER_CHAT_IDS → ошибка"""
    os.environ['LISTENER_CHAT_IDS'] = 'not json'
    with pytest.raises(ConfigError):
        load_config()

# test_rate_limiter.py
async def test_rate_limit_allows_30_per_sec():
    """Лимит 30 сообщений в сек"""
    limiter = RateLimiter(limit=30)
    for i in range(30):
        assert await limiter.acquire() == True
    # 31-е должно быть отложено
    assert await limiter.acquire_nowait() == False
```

---

### 6.2 Integration-тесты

**Зависимости для тестов:**
- Test database PostgreSQL (test_marshall_listener)
- Test Telegram group (Marshall Test — Chat Listener Staging)
- Telethon client с test-аккаунтом

**Сценарии:**

```python
# test_integration_telegram.py
async def test_message_received_and_saved():
    """Сообщение в чат → сохранено в БД"""
    listener = ChatListener(config)
    await listener.connect()

    # Отправить тестовое сообщение из другого аккаунта
    # (симуляция через другого Telethon client или Telegram Web API)

    await asyncio.sleep(0.5)  # дать время на обработку

    # Проверить что запись в raw_messages
    result = await db.fetch(
        "SELECT text FROM raw_messages WHERE text = $1",
        "Test message"
    )
    assert len(result) == 1
    assert result[0]['text'] == "Test message"

async def test_rate_limit_integration():
    """Отправить 50 сообщений → первые 30 обработаны, остальные в буфер"""
    # Отправить 50 сообщений быстро
    for i in range(50):
        await send_test_message(f"Message {i}")

    await asyncio.sleep(2)

    # Проверить в БД и буфере
    db_count = await db.fetch("SELECT COUNT(*) FROM raw_messages")
    buffer_count = await sqlite_queue.fetch("SELECT COUNT(*) FROM queue")

    assert db_count[0]['count'] > 0
    assert buffer_count[0]['count'] > 0  # часть в буфере
```

---

### 6.3 E2E-тесты (система целиком)

```python
# test_e2e_listener.py
async def test_full_pipeline():
    """Сообщение из Telegram → БД → очередь для Parser"""
    listener = ChatListener(config)
    await listener.start()  # запустить фоновую задачу

    await asyncio.sleep(1)  # дать время на подключение

    # Отправить тестовое сообщение
    await send_test_message("Рейс 4521, Москва-Краснодар")

    await asyncio.sleep(0.5)  # обработка

    # Проверить в БД
    row = await db.fetchrow(
        "SELECT * FROM raw_messages WHERE text LIKE '%Рейс 4521%'"
    )
    assert row is not None
    assert row['text'] == "Рейс 4521, Москва-Краснодар"

    # Проверить очередь Parser
    msg = await listener.message_queue.get()
    assert msg.text == "Рейс 4521, Москва-Краснодар"
    assert msg.raw_message_id == row['raw_message_id']

async def test_shutdown_saves_queue():
    """Graceful shutdown → очередь сохранена"""
    listener = ChatListener(config)
    await listener.start()

    # Отправить 10 сообщений
    for i in range(10):
        await send_test_message(f"Test {i}")

    # Отправить SIGTERM
    listener.shutdown()

    # Дождаться завершения
    await asyncio.wait_for(listener.shutdown_event.wait(), timeout=5)

    # Проверить что все 10 в БД или буфере
    total = await db.fetch("SELECT COUNT(*) FROM raw_messages")
    # + проверить буфер при необходимости
    assert total >= 10
```

---

### 6.4 Нагрузочное тестирование

```python
# test_load.py
async def test_throughput_100_msg_per_sec():
    """100 сообщений в сек → система не падает, rate limit срабатывает"""
    listener = ChatListener(config)
    await listener.start()

    # Отправить 100 сообщений в течение 1 сек
    for i in range(100):
        await send_test_message(f"Load test {i}")
        await asyncio.sleep(0.01)  # 100 в сек

    await asyncio.sleep(5)

    # Все должны быть в БД или буфере, без потерь
    total_db = await db.fetch("SELECT COUNT(*) FROM raw_messages")
    # Проверить что 100 обработаны
    assert total_db[0]['count'] >= 100 or buffer_has_data()
```

---

### 6.5 Тестовые данные (fixtures)

```python
# conftest.py (pytest)
import pytest
from datetime import datetime

@pytest.fixture
async def listener_config():
    """Тестовая конфигурация"""
    return {
        'listener_mode': 'mtproto',
        'tg_session_string': os.getenv('TEST_TG_SESSION'),
        'listener_chat_ids': [-1001234567890],  # test chat
        'listener_rate_limit': 30,
        'db_host': 'localhost',
        'db_name': 'test_marshall_listener',
        # и т.д.
    }

@pytest.fixture
async def postgres_db():
    """БД для тестов"""
    db = await asyncpg.connect('postgresql://...')
    # Создать таблицы
    await db.execute(CREATE_TABLE_QUERIES)
    yield db
    # Очистить после теста
    await db.execute("TRUNCATE raw_messages")
    await db.close()

@pytest.fixture
async def chat_listener(listener_config, postgres_db):
    """ChatListener готов к использованию"""
    listener = ChatListener(listener_config, db=postgres_db)
    yield listener
    # Cleanup
    await listener.disconnect()
```

---

## 7. Зависимости

### 7.1 Библиотеки Python

```
telethon==1.34.0              # MTProto подключение
asyncpg==0.29.0               # PostgreSQL асинхронный драйвер
python-dotenv==1.0.0          # Парсинг .env файлов
python-json-logger==2.0.7     # JSON логирование
aiofiles==23.2.1              # Асинхронная работа с файлами (для буфера)
aiosqlite==0.19.0             # SQLite3 буфер для rate limiting (асинхронно)
pydantic==2.5.0               # Валидация конфигурации
```

---

### 7.2 Инфраструктура

| Компонент | Версия | Примечания |
|-----------|--------|-----------|
| Python | 3.11+ | Ассинхронность, async/await |
| PostgreSQL | 15+ | Основное хранилище |
| Docker | Latest | Контейнеризация |
| RUVDS VPS | 88.218.248.114 | Хостинг (Тим) |
| Telegram API | V183+ | MTProto протокол |

---

### 7.3 Внешние зависимости

- **Telegram account** — аккаунт с номером телефона для StringSession (сервисный, не личный)
- **Test Telegram group** — 3 групповых чата для разработки
- **PostgreSQL экземпляр** — на RUVDS или локально
- **StringSession** — получена один раз от Telethon, сохранена в .env

---

## 8. Примеры и граничные случаи

### 8.1 Примеры использования

#### Пример 1: Простое сообщение в групповой чат

**Входные данные (Telegram):**
```
Чат: Marshall Test — WB Рейсы
Отправитель: Диспетчер Алексей (ID: 123456789)
Время: 2026-03-06 14:32:10 UTC
Текст: "Рейс 4521, Москва-Краснодар, слот на погрузку WB 14:00, реф охладить до +2."
```

**Сохранение в БД:**
```json
{
  "raw_message_id": 1,
  "chat_id": -1001234567890,
  "message_id": 12345,
  "sender_id": 123456789,
  "sender_name": "Диспетчер Алексей",
  "text": "Рейс 4521, Москва-Краснодар, слот на погрузку WB 14:00, реф охладить до +2.",
  "timestamp": "2026-03-06T14:32:10Z",
  "created_at": "2026-03-06T14:32:10.087Z",
  "is_direct_message": false,
  "raw_data_json": {
    "message_id": 12345,
    "from_id": 123456789,
    "chat_id": -1001234567890,
    "date": 1741265530,
    "edit_date": null,
    "fwd_from": null,
    "reply_to_msg_id": null
  }
}
```

**Передача в Parser:**
```python
ProcessingMessage(
    raw_message_id=1,
    chat_id=-1001234567890,
    text="Рейс 4521, Москва-Краснодар, слот на погрузку WB 14:00, реф охладить до +2.",
    sender_name="Диспетчер Алексей",
    timestamp=datetime(2026, 3, 6, 14, 32, 10),
    is_direct_message=False
)
```

---

#### Пример 2: Прямое сообщение (DM)

**Входные данные (Telegram):**
```
Тип: Private chat (DM)
Отправитель: Водитель Иван (ID: 987654321)
Время: 2026-03-06 15:45:30 UTC
Текст: "Выехал на погрузку. Навигатор показывает 2.5 часа."
```

**Сохранение в БД:**
```json
{
  "raw_message_id": 2,
  "chat_id": 987654321,          # chat_id == sender_id для DM
  "message_id": 54321,
  "sender_id": 987654321,
  "sender_name": "Водитель Иван",
  "text": "Выехал на погрузку. Навигатор показывает 2.5 часа.",
  "timestamp": "2026-03-06T15:45:30Z",
  "created_at": "2026-03-06T15:45:30.134Z",
  "is_direct_message": true,     # Флаг DM
  "raw_data_json": {
    "message_id": 54321,
    "from_id": 987654321,
    "chat_id": 987654321,
    "date": 1741266330,
    "is_private": true
  }
}
```

---

#### Пример 3: Фото (игнорируется)

**Входные данные (Telegram):**
```
Чат: Marshall Test — WB Рейсы
Отправитель: Водитель Иван
Медиа: Photo (документ ТСД)
Caption: "Вот чек погрузки"
```

**Обработка:**
```json
{
  "timestamp": "2026-03-06T16:20:15.456Z",
  "level": "DEBUG",
  "component": "ChatListener",
  "event": "skipped_media_message",
  "chat_id": -1001234567890,
  "message_id": 12346,
  "media_type": "photo",
  "reason": "text_content_empty"
}
```

**В БД:** Запись НЕ добавляется.

---

### 8.2 Граничные случаи

#### Case 1: Пустая StringSession
**Входные данные:** `TG_SESSION_STRING=""` или не установлена
**Ожидаемое поведение:** Ошибка при старте, логирование "ConfigError: TG_SESSION_STRING is empty", exit code 1, система не запускается.

---

#### Case 2: Невалидный JSON в LISTENER_CHAT_IDS
**Входные данные:** `LISTENER_CHAT_IDS="[-123, abc, 456]"`
**Ожидаемое поведение:** Ошибка парсинга JSON, логирование "ConfigError: Invalid LISTENER_CHAT_IDS JSON", exit code 1.

---

#### Case 3: Аккаунт выбит из одного из 3 чатов
**Входные данные:** Аккаунт не участник в чате -1001111111111
**Ожидаемое поведение:** Логирование "WARNING: Unable to join chat -1001111111111, skipping", система продолжает слушать оставшиеся 2 чата.

---

#### Case 4: Очень длинное сообщение (>4096 символов)
**Входные данные:** Текст 10 000 символов
**Ожидаемое поведение:** Полный текст сохраняется в БД (text — TEXT, не ограничено), передаётся в Parser как есть. Parser может обрезать для LLM.

---

#### Case 5: Сообщение на иностранном языке (не русский)
**Входные данные:** "Delivered to London warehouse at 14:30"
**Ожидаемое поведение:** Сохраняется как есть, в БД есть язык не проверяется. Parser должен обрабатывать многоязычный контент.

---

#### Case 6: Спецсимволы и emoji
**Входные данные:** "✅ Рейс 4521 завершён 🎉 +5 бонусов!"
**Ожидаемое поведение:** Спецсимволы и emoji сохраняются в БД (UTF-8), передаются в Parser. No issues.

---

#### Case 7: Упомянутые пользователи (@username)
**Входные данные:** "@Алексей, это срочно! Рейс 4521 опаздывает."
**Ожидаемое поведение:** Сообщение сохраняется с упоминанием как есть. Parser должен распознавать упоминания при анализе контекста.

---

#### Case 8: Ответ на сообщение (reply)
**Входные данные:** Сообщение является ответом на сообщение ID 12344
**Ожидаемое поведение:** raw_data_json содержит `reply_to_msg_id`, text сохраняется полностью (не включает исходное сообщение), Parser может использовать контекст из linked message.

---

#### Case 9: PostgreSQL недоступна при старте
**Входные данные:** DB_HOST неправильный или БД упала
**Ожидаемое поведение:** Ошибка подключения при старте, логирование "DatabaseError: Unable to connect to PostgreSQL", попытка переподключения 3 раза, затем graceful shutdown, exit code 1.

---

#### Case 10: Rate limit — 100 сообщений в 1 сек
**Входные данные:** Flood из 100 сообщений за 1 сек
**Ожидаемое поведение:** Первые 30 обработаны, остальные 70 в диск-буфер (SQLite), логирование "Rate limit hit, 70 messages queued", буферизованные обработаны поочередно в следующие секунды.

---

#### Case 11: Дублирующееся сообщение (resend)
**Входные данные:** Одно сообщение получено дважды от Telegram (edge case MTProto)
**Ожидаемое поведение:** Второе получение — обработано как новое сообщение, добавлено в raw_messages. Дедупликация (если нужна) делается на уровне Parser или Alert Engine, не на уровне Listener.

---

#### Case 12: SIGTERM во время обработки большого буфера
**Входные данные:** Сигнал SIGTERM пришёл, в диск-буфере 200 сообщений
**Ожидаемое поведение:** Логирование "Shutdown initiated", система ждёт 30 сек (SHUTDOWN_TIMEOUT), пытается обработать буфер, затем закрывает БД и выходит с кодом 0. Необработанные сообщения остаются в буфере для обработки при следующем запуске.

---

## Заключение

Chat Listener (S0-F01) — критическая компонента для захвата данных из Telegram-чатов диспетчеров. Спецификация определяет:

1. **Функционал:** подключение через Telethon, чтение из 3 чатов + DM, сохранение в PostgreSQL, передача в Parser
2. **Надежность:** graceful shutdown, автоподключение, обработка ошибок БД
3. **Производительность:** rate limiting 30/сек, latency <200 мс для сохранения
4. **Интеграция:** pluggable-адаптер для будущего Bot API
5. **Логирование:** структурированное JSON для мониторинга

Спецификация полностью определяет требования, интерфейсы и критерии приёмки. Разработчик может реализовать модуль независимо, используя только этот документ.
