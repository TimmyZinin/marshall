---
title: Marshall AI Listener — Спецификация Alert Engine
version: "1.0"
date_created: 2026-03-06
owner: Тим Зинин (Zinin Corp)
module: S0-F03
tags: [tool, alert-engine, rules, detection, severity]
---

# Спецификация Alert Engine (S0-F03)

## 1. Цель и скоуп

### 1.1 Назначение
Alert Engine — модуль анализа структурированных данных, полученных от AI Parser, для детекции критических событий в логистических операциях. На основе парсированных данных (trip_id, маршрут, статус, заказчик, urgency, проблемы) и конфигурируемых бизнес-правил система выставляет алерты в базе данных. Алерты отображаются менеджерам через REST API в дашборде для принятия оперативных мер.

**Ключевой принцип:** Нулевой latency между детекцией проблемы и появлением алерта в дашборде. Алерты — это структурированное представление проблем, которые диспетчер уже видит в мессенджерах, но Alert Engine находит их автоматически и приводит к единому формату.

### 1.2 Входные и выходные интерфейсы

**ВХОДЫ:**
- Parsed message data от AI Parser (JSON-структура: trip_id, route_from, route_to, slot_time, status, customer, urgency, issue, confidence)
- Конфигурация правил (YAML-файл с правилами для каждого заказчика)
- Справочник заказчиков (customer_id → customer_name, правила, требования)

**ВЫХОДЫ:**
- Alert record в таблице PostgreSQL `alerts` (alert_id, trip_id, alert_type, severity, message, customer, parsed_data, created_at, status, reviewed_by, resolved_at)
- Запись доступна через REST API для дашборда (/api/alerts, /api/alerts/{alert_id})

### 1.3 Скоуп и ограничения

**Входит в скоуп:**
- Анализ парсированных данных в реальном времени (<100 мс)
- 5 типов алертов: delay, equipment_failure, downtime, safety_violation, docs_missing
- 3 уровня severity: HIGH (блокирует рейс), MEDIUM (требует внимания), LOW (информационный)
- Правила для 6 заказчиков: Тандер, WB, X5, Магнит, Сельта, Сибур
- Конфигурируемые правила в YAML-формате
- Дедупликация алертов (не создавать дубли на одном рейсе за 5 минут)
- Статусы алерта: created, reviewed (отмечен менеджером), resolved
- Структурированное JSON-логирование всех решений

**Выходит из скоупа:**
- Отправка алертов в Telegram/email/SMS (отложено на Sprint 1)
- Автоматическая эскалация (переводилась диспетчера на смену) — отложено на Sprint 1
- Push-уведомления браузер
- Интеграция с МОВИЗОР/GPS для верификации локации
- AI-переработка алертов (clustering, anomaly detection)
- Прогнозирование задержек на основе исторических данных

---

## 2. Определения

### 2.1 Ключевые сущности

| Термин | Определение |
|--------|-----------|
| **Alert** | Запись о детектированном критическом событии, связанная с рейсом (trip_id) или без (информационный) |
| **Severity** | Степень критичности алерта: HIGH (вызывает штраф/срыв рейса), MEDIUM (требует внимания), LOW (информационный) |
| **Alert Type** | Категория проблемы: delay, equipment_failure, downtime, safety_violation, docs_missing |
| **Trigger** | Условие, при котором создаётся алерт (например, urgency=high в парсированных данных) |
| **Rule** | Бизнес-правило для заказчика, определяющее какие события должны быть алертированы |
| **Reviewed** | Статус: менеджер видел алерт и подтвердил факт в дашборде |
| **Resolved** | Статус: проблема закрыта (рейс завершился, проблема исправлена) |
| **Customer** | Заказчик логистической услуги (Тандер, WB, X5, Магнит, Сельта, Сибур) |
| **Trip** | Рейс/доставка с уникальным trip_id, маршрутом, заказчиком |
| **Deduplication Window** | Временное окно (5 мин) в течение которого дубли одного типа алерта на один рейс не создаются |
| **Confidence** | Уверенность парсера (0–1), используется для фильтрации (не алертировать <0.6) |

### 2.2 Типы алертов (Alert Types)

| Type | Описание | Примеры | Severity |
|------|---------|---------|----------|
| **delay** | Опоздание водителя на слот или в пути | "Стою в пробке, опаздываю на 40 мин" | MEDIUM/HIGH |
| **equipment_failure** | Поломка ТС или оборудования | "Реф не выходит на температуру +8" | HIGH |
| **downtime** | Неоправданный простой на месте | "Жду разгрузки 3 часа" | MEDIUM/HIGH |
| **safety_violation** | Нарушение техники безопасности | "Водитель без каски" | MEDIUM |
| **docs_missing** | Отсутствие документов (информационный) | "Нет фото ТСД" | LOW |

### 2.3 Уровни severity

| Severity | Условие активации | Штраф | Действие |
|----------|-----------------|-------|---------|
| **HIGH** | Опоздание >4ч, оборудование сломано, простой >6ч на X5 | 15–100% рейса | Срочно связать диспетчера |
| **MEDIUM** | Опоздание 1–4ч, простой 2–6ч на X5, неполная техника ТБ | 5–15% рейса | Требует внимания |
| **LOW** | Информационные (документы отсутствуют) | 0% | Фоновое уведомление |

### 2.4 Статусы алерта

| Статус | Значение | Переход |
|--------|---------|---------|
| **created** | Алерт создан автоматически системой | → reviewed, resolved |
| **reviewed** | Менеджер видел алерт и подтвердил (клик на дашборде) | → resolved |
| **resolved** | Проблема закрыта (рейс завершился, проблема исправлена) | terminal |

---

## 3. Требования, ограничения и рекомендации

### 3.1 Функциональные требования (REQ)

#### REQ-AE-001: Анализ парсированных данных
**Требование:** Alert Engine должен получать парсированные данные от AI Parser (JSON с полями trip_id, route, status, customer, urgency, issue, confidence) и на основе них принимать решение о создании алерта.

**Обоснование:** Парсер выходит, данные структурированы. Alert Engine использует эти данные как триггеры.

**Пример:**
```
Вход от Parser:
{
  "trip_id": "4521",
  "customer": "WB",
  "urgency": "medium",
  "issue": "Опоздание на слот на 40 мин",
  "confidence": 0.85
}

Вывод Alert Engine:
{
  "alert_type": "delay",
  "severity": "MEDIUM",
  "message": "Возможная задержка на 40 мин по рейсу WB-4521",
  "trip_id": "4521",
  "customer": "WB"
}
```

---

#### REQ-AE-002: Конфигурируемые правила заказчиков (YAML)
**Требование:** Правила для каждого заказчика хранятся в YAML-файле конфигурации. Правила определяют:
1. Какие события триггируют алерт (условия)
2. Какой type и severity присваивается
3. Какой текст сообщения алерта

**Обоснование:** Разные заказчики имеют разные требования (Тандер требует +2..+4, WB требует слотов, X5 не разрешает стоять). Конфиг должен быть менялся без перекомпиляции кода.

**Пример структуры:**
```yaml
customers:
  WB:
    rules:
      - condition: "urgency = 'medium' AND trip_status != 'completed'"
        alert_type: "delay"
        severity: "MEDIUM"
        message_template: "Возможная задержка рейса {{trip_id}}"
      - condition: "issue.contains('slot')"
        alert_type: "delay"
        severity: "HIGH"
        message_template: "Критическое опоздание на слот {{slot_time}}"
```

---

#### REQ-AE-003: Пять типов алертов
**Требование:** Alert Engine должен создавать алерты пяти типов: delay, equipment_failure, downtime, safety_violation, docs_missing.

**Обоснование:** Каждый тип соответствует категории проблемы в логистике. Дашборд фильтрует по типам.

| Type | Триггер | Severity по умолчанию |
|------|---------|----------------------|
| delay | urgency >= medium + issue содержит "опоздан", "пробка", "слот" | MEDIUM/HIGH |
| equipment_failure | issue содержит "реф", "температура", "поломка", "сломана" | HIGH |
| downtime | issue содержит "простой", "жду", "стою" + duration > 2h | MEDIUM |
| safety_violation | issue содержит "каска", "жилет", "ботинки", "техника ТБ" | MEDIUM |
| docs_missing | issue содержит "документ", "фото", "ТСД", "чек" | LOW |

---

#### REQ-AE-004: Три уровня severity
**Требование:** Каждый алерт должен иметь severity: HIGH, MEDIUM или LOW.

**Обоснование:** Severity определяет:
- Порядок в дашборде (HIGH вверху)
- Цвет в UI (красный, жёлтый, синий)
- Потенциальный размер штрафа

**Логика severity:**
- **HIGH:** Опоздание >4ч, оборудование сломано, простой на X5 >6ч, документ критичен → потеря 15–100% рейса
- **MEDIUM:** Опоздание 1–4ч, простой на X5 2–6ч, нарушение ТБ → потеря 5–15% рейса
- **LOW:** Документы отсутствуют (справочные) → потеря 0% рейса, но требует ревью

---

#### REQ-AE-005: Дедупликация алертов (5-минутное окно)
**Требство:** На один рейс (trip_id) + тип алерта (alert_type) система не должна создавать дубли в течение 5 минут.

**Обоснование:** Если парсер сделает 3 попытки одного сообщения (retry), Alert Engine создаст 3 дубля. Дедупликация спасает от шума.

**Алгоритм:**
```
ЕСЛИ существует alert.trip_id=X AND alert.alert_type=Y
    AND alert.created_at > NOW() - 5 мин
ТО не создавать новый алерт
ИНАЧЕ создать новый
```

**Исключение:** Если это другой тип алерта или другой рейс → создать.

---

#### REQ-AE-006: Фильтрация по confidence парсера
**Требование:** Алерты создаются только если confidence (уверенность парсера) >= 0.60.

**Обоснование:** Если парсер не уверен (confidence < 0.60), алерт может быть ложным, лучше пропустить.

**Пример:**
```
Парсер: confidence=0.55, issue="может быть пробка"
Alert Engine: НЕ создавать алерт (0.55 < 0.60)

Парсер: confidence=0.92, issue="Реф не выходит на температуру"
Alert Engine: СОЗДАТЬ алерт (0.92 >= 0.60)
```

---

#### REQ-AE-007: Определение severity на основе правил
**Требство:** Severity каждого алерта определяется на основе бизнес-правил заказчика и типа проблемы.

**Логика:**
1. Парсер выдал urgency (low, medium, high)
2. Правило заказчика присваивает severity (HIGH, MEDIUM, LOW)
3. Если парсер urgency=high → severity >= MEDIUM
4. Если urgency=medium И duration > порога → severity=HIGH

**Примеры:**
- Тандер + urgency=high + issue="температура +8" → severity=HIGH
- WB + urgency=medium + опоздание 40 мин → severity=MEDIUM
- X5 + простой 7 часов → severity=HIGH (x5 не разрешает стоять)
- Магнит + простой 7 часов → severity=LOW (Магнит разрешает стоять)

---

#### REQ-AE-008: Сохранение в таблицу alerts
**Требство:** Каждый созданный алерт должен сохраняться в PostgreSQL-таблицу `alerts` с полями:
- alert_id (UUID, PK)
- trip_id (VARCHAR, может быть NULL для информационных)
- alert_type (ENUM: delay, equipment_failure, downtime, safety_violation, docs_missing)
- severity (ENUM: HIGH, MEDIUM, LOW)
- message (TEXT)
- customer (VARCHAR, заказчик)
- parsed_data (JSONB, полные данные от парсера)
- created_at (TIMESTAMP)
- status (ENUM: created, reviewed, resolved)
- reviewed_by (VARCHAR NULL, имя менеджера)
- resolved_at (TIMESTAMP NULL)

**Обоснование:** Таблица служит источником для REST API дашборда.

---

#### REQ-AE-009: Обработка алертов без trip_id
**Требство:** Некоторые события критичны, но не связаны с конкретным рейсом (например, ДТП на трассе, проблема с цистерной). Alert Engine должен создавать алерты и без trip_id.

**Пример:**
```
Парсер: urgency=high, issue="ДТП на М4, пробка"
Alert Engine создаёт:
{
  "trip_id": null,  // информационный алерт
  "alert_type": "downtime",
  "severity": "MEDIUM",
  "message": "Инцидент на трассе М4, пробка может повлиять на рейсы",
  "customer": null
}
```

---

#### REQ-AE-010: Структурированное логирование
**Требство:** Все решения Alert Engine (создание алерта, дедупликация, фильтрация по confidence) должны логироваться в JSON-формате с полями:
- timestamp
- alert_id (если создан)
- trip_id
- decision (created, deduplicated, skipped_low_confidence, skipped_no_rules)
- reason (текст причины)
- parsed_data (JSON)

**Обоснование:** Для отладки, аудита и улучшения правил.

**Пример лога:**
```json
{
  "timestamp": "2026-03-06T14:30:15.123Z",
  "decision": "created",
  "alert_id": "ae-550e8400-e29b-41d4-a716-446655440000",
  "trip_id": "4521",
  "customer": "WB",
  "alert_type": "delay",
  "severity": "MEDIUM",
  "parsed_data": {
    "urgency": "medium",
    "issue": "Стою в пробке, опаздываю на 40 мин",
    "confidence": 0.85
  }
}
```

---

#### REQ-AE-011: API-интерфейс для статусов
**Требство:** Alert Engine должен поддерживать REST API методы для изменения статуса алерта:
- POST /api/alerts/{alert_id}/review — отметить как reviewed
- POST /api/alerts/{alert_id}/resolve — отметить как resolved

**Обоснование:** Менеджер видит алерт в дашборде, кликает на него → статус меняется с created на reviewed.

**Контракт:**
```
POST /api/alerts/{alert_id}/review
Body: { "reviewed_by": "Виктория Фимина" }
Response: { "alert_id": "...", "status": "reviewed", "reviewed_at": "2026-03-06T14:35:00Z" }

POST /api/alerts/{alert_id}/resolve
Body: { }
Response: { "alert_id": "...", "status": "resolved", "resolved_at": "2026-03-06T18:00:00Z" }
```

---

#### REQ-AE-012: Метрики для мониторинга
**Требство:** Alert Engine должен выставлять метрики для Prometheus/мониторинга:
- `alerts_created_total` (счётчик)
- `alerts_deduplicated_total` (счётчик пропущенных дубликатов)
- `alerts_by_type` (распределение по типам)
- `alerts_by_severity` (распределение по severity)
- `alert_processing_latency_ms` (latency парсированные данные → алерт создан)

**Обоснование:** Для наблюдения и отладки системы.

---

### 3.2 Ограничения (CON)

#### CON-AE-001: Нет отправки в Telegram/email/SMS в Sprint 0
**Ограничение:** Alert Engine создаёт алерты в БД. Отправку в Telegram, email, SMS отложено на Sprint 1.

**Причина:** Простота MVP, фокус на дашборде.

---

#### CON-AE-002: Нет автоматической эскалации
**Ограничение:** HIGH-алерт не автоматически переводит диспетчера на смену. Только дашборд.

**Причина:** Нужна информация о расписании смен диспетчеров, которой нет.

---

#### CON-AE-003: Нет интеграции с МОВИЗОР/GPS
**Ограничение:** Alert Engine не проверяет реальную геолокацию из МОВИЗОР. Использует только текст от водителя.

**Причина:** МОВИЗОР подключает только диспетчер вручную, нет API.

---

#### CON-AE-004: Confidence порог = 0.60
**Ограничение:** Алерты не создаются для данных с confidence < 0.60.

**Причина:** Ниже уверенность = выше риск ложных алертов.

---

#### CON-AE-005: Дедупликация на 5 минут
**Ограничение:** Дубли на один рейс/тип создаются не чаще одного раза в 5 минут.

**Причина:** Баланс между точностью и шумом. Если проблема не устранена, она появится в дашборде через 5 мин.

---

#### CON-AE-006: Конфиг только YAML (не база)
**Ограничение:** Правила хранятся в YAML-файле, а не в БД.

**Причина:** Простота для MVP. На платные спринты → миграция в админ-интерфейс.

---

### 3.3 Рекомендации (REC)

#### REC-AE-001: Кеширование правил
**Рекомендация:** При запуске Alert Engine загрузить правила из YAML в памяти (in-memory cache). При изменении YAML перезагружать кеш.

**Обоснование:** Быстрее чем читать файл для каждого алерта.

---

#### REC-AE-002: Асинхронная обработка
**Рекомендация:** Alert Engine должен быть асинхронным (asyncio), чтобы не блокировать входящие сообщения от парсера.

**Обоснование:** Если БД медленно пишет, очередь не должна застревать.

---

#### REC-AE-003: Fallback на базовые триггеры
**Рекомендация:** Если правила не покрывают сценарий, Alert Engine должен использовать базовые триггеры (urgency=high → создать MEDIUM-алерт).

**Обоснование:** Лучше слабый алерт, чем пропустить проблему.

---

## 4. Интерфейсы и контракты данных

### 4.1 Входной интерфейс (от AI Parser)

Alert Engine получает JSON-сообщение от парсера через очередь (RabbitMQ/Kafka) или синхронный вызов.

**Формат входа:**
```json
{
  "msg_id": "msg-123456",
  "chat_id": "12345678",
  "sender": "Диспетчер Мария",
  "text": "Рейс 4521, опаздываю на 40 мин из-за пробки",
  "timestamp": "2026-03-06T14:30:00Z",
  "parsed_data": {
    "trip_id": "4521",
    "route_from": "Москва",
    "route_to": "Краснодар",
    "slot_time": "14:00",
    "status": "in_progress",
    "customer": "WB",
    "urgency": "medium",
    "issue": "Опоздание на 40 мин из-за пробки",
    "confidence": 0.87
  }
}
```

**Валидация:**
- `parsed_data` должен быть присутствовать
- `confidence` >= 0.60 (иначе skip)
- `timestamp` в ISO 8601 формате

---

### 4.2 Выходной интерфейс (в БД)

Alert Engine пишет в таблицу PostgreSQL `alerts`.

**Структура таблицы:**
```sql
CREATE TABLE alerts (
  alert_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  trip_id VARCHAR(50) NULL,
  alert_type VARCHAR(50) NOT NULL CHECK (alert_type IN ('delay', 'equipment_failure', 'downtime', 'safety_violation', 'docs_missing')),
  severity VARCHAR(10) NOT NULL CHECK (severity IN ('HIGH', 'MEDIUM', 'LOW')),
  message TEXT NOT NULL,
  customer VARCHAR(100) NULL,
  parsed_data JSONB NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT NOW(),
  status VARCHAR(20) NOT NULL DEFAULT 'created' CHECK (status IN ('created', 'reviewed', 'resolved')),
  reviewed_by VARCHAR(255) NULL,
  reviewed_at TIMESTAMP NULL,
  resolved_at TIMESTAMP NULL,
  INDEX idx_trip_id (trip_id),
  INDEX idx_customer (customer),
  INDEX idx_created_at (created_at),
  INDEX idx_severity (severity),
  INDEX idx_status (status)
);
```

---

### 4.3 Правила (YAML-конфигурация)

**Расположение:** `/opt/marshall-listener/config/alert_rules.yaml`

**Структура:**
```yaml
version: "1.0"
customers:
  # Тандер: Предохлаждение +2..+4, термописец обязателен
  Тандер:
    enabled: true
    rules:
      - id: "thander_temp_violation"
        condition: |
          issue.contains_any(['температура', 'реф', '+8', '+6'])
          AND (urgency = 'high' OR confidence > 0.85)
        alert_type: "equipment_failure"
        severity: "HIGH"
        message_template: "КРИТИЧНО: Нарушение температуры у Тандер {{trip_id}}: {{issue}}"
        dedup_window_min: 5

      - id: "thander_delay_4h"
        condition: |
          urgency IN ('medium', 'high')
          AND (issue.contains('опоздание') OR issue.contains('пробка'))
          AND estimated_delay_min > 240
        alert_type: "delay"
        severity: "HIGH"
        message_template: "ШТРАФ 15%: Опоздание >4ч на рейс {{trip_id}} Тандер"
        dedup_window_min: 5

      - id: "thander_delay_1h"
        condition: |
          urgency IN ('low', 'medium')
          AND (issue.contains('опоздание') OR issue.contains('пробка'))
          AND estimated_delay_min > 60 AND estimated_delay_min < 240
        alert_type: "delay"
        severity: "MEDIUM"
        message_template: "Опоздание {{estimated_delay_min}} мин на рейс {{trip_id}} Тандер"
        dedup_window_min: 5

  # WB (Wildberries): Регистрация WB Drive, строгие слоты
  WB:
    enabled: true
    rules:
      - id: "wb_slot_miss_critical"
        condition: |
          urgency = 'high'
          AND (issue.contains('слот') OR issue.contains('опаздываю'))
          AND customer = 'WB'
        alert_type: "delay"
        severity: "HIGH"
        message_template: "СРЫВ СЛОТА: Рейс {{trip_id}} WB критически опаздывает на слот {{slot_time}}"
        dedup_window_min: 5

      - id: "wb_delay_1h"
        condition: |
          urgency = 'medium'
          AND (issue.contains('пробка') OR issue.contains('опаздываю'))
          AND customer = 'WB'
          AND estimated_delay_min >= 40
        alert_type: "delay"
        severity: "MEDIUM"
        message_template: "Возможное опоздание {{estimated_delay_min}} мин на слот WB {{slot_time}} рейс {{trip_id}}"
        dedup_window_min: 5

      - id: "wb_docs_missing"
        condition: |
          urgency IN ('low', 'medium')
          AND issue.contains_any(['документ', 'чек', 'ТСД', 'фото'])
          AND customer = 'WB'
        alert_type: "docs_missing"
        severity: "LOW"
        message_template: "WB {{trip_id}}: Отсутствуют документы — {{issue}}"
        dedup_window_min: 10

  # X5 Retail Group: НЕЛЬЗЯ стоять на территории
  X5:
    enabled: true
    rules:
      - id: "x5_downtime_critical"
        condition: |
          urgency IN ('medium', 'high')
          AND issue.contains_any(['стою', 'простой', 'жду разгрузки'])
          AND customer = 'X5'
          AND downtime_hours > 2
        alert_type: "downtime"
        severity: "HIGH"
        message_template: "НАРУШЕНИЕ: X5 запрещает стоять, уже {{downtime_hours}}ч простоя на {{trip_id}}"
        dedup_window_min: 5

      - id: "x5_downtime_warning"
        condition: |
          urgency = 'medium'
          AND issue.contains_any(['стою', 'простой', 'жду'])
          AND customer = 'X5'
          AND downtime_hours > 1 AND downtime_hours <= 2
        alert_type: "downtime"
        severity: "MEDIUM"
        message_template: "Осторожно: X5 {{trip_id}} в простое {{downtime_hours}}ч"
        dedup_window_min: 5

  # Магнит: МОЖНО стоять на территории (отличается от X5!)
  Магнит:
    enabled: true
    rules:
      - id: "magnet_delay_only"
        condition: |
          urgency IN ('medium', 'high')
          AND (issue.contains('опоздание') OR issue.contains('пробка'))
          AND customer = 'Магнит'
        alert_type: "delay"
        severity: "MEDIUM"
        message_template: "Магнит {{trip_id}}: {{issue}}"
        dedup_window_min: 5

      - id: "magnet_equipment"
        condition: |
          urgency = 'high'
          AND issue.contains_any(['реф', 'температура', 'поломка'])
          AND customer = 'Магнит'
        alert_type: "equipment_failure"
        severity: "HIGH"
        message_template: "КРИТИЧНО Магнит: {{issue}} на {{trip_id}}"
        dedup_window_min: 5

  # Сельта: Каска + жилет + ботинки с железным носом
  Сельта:
    enabled: true
    rules:
      - id: "selta_safety_violation"
        condition: |
          urgency = 'high'
          AND issue.contains_any(['каска', 'жилет', 'ботинки', 'техника ТБ', 'техника безопасности'])
          AND customer = 'Сельта'
        alert_type: "safety_violation"
        severity: "MEDIUM"
        message_template: "Сельта {{trip_id}}: Нарушение ТБ — {{issue}}"
        dedup_window_min: 5

  # Сибур: Особые требования безопасности
  Сибур:
    enabled: true
    rules:
      - id: "sibur_safety_violation"
        condition: |
          urgency = 'high'
          AND issue.contains_any(['безопасность', 'требование', 'договор'])
          AND customer = 'Сибур'
        alert_type: "safety_violation"
        severity: "HIGH"
        message_template: "Сибур {{trip_id}}: Критическое требование безопасности не соблюдено"
        dedup_window_min: 5

# Глобальные правила (для всех заказчиков)
global:
  # ДТП и инциденты на трассе
  - id: "global_traffic_incident"
    condition: |
      urgency = 'high'
      AND issue.contains_any(['ДТП', 'авария', 'инцидент', 'пробка M4', 'пробка М4'])
    alert_type: "downtime"
    severity: "MEDIUM"
    message_template: "Инцидент на трассе: {{issue}} — возможны задержки"
    dedup_window_min: 10

  # Критическое оборудование
  - id: "global_critical_equipment"
    condition: |
      urgency = 'high'
      AND issue.contains_any(['реф сломана', 'компрессор', 'температура не держит'])
    alert_type: "equipment_failure"
    severity: "HIGH"
    message_template: "КРИТИЧНО: Поломка оборудования {{trip_id}} — {{issue}}"
    dedup_window_min: 5
```

---

### 4.4 REST API методы

#### GET /api/alerts
Получить список алертов с фильтрацией.

**Запрос:**
```
GET /api/alerts?
  customer=WB&
  severity=HIGH&
  status=created&
  limit=20&
  offset=0&
  sort=created_at:desc

Authorization: Bearer {token}
```

**Ответ (200 OK):**
```json
{
  "data": [
    {
      "alert_id": "ae-550e8400-e29b-41d4-a716-446655440000",
      "trip_id": "4521",
      "alert_type": "delay",
      "severity": "MEDIUM",
      "message": "Возможное опоздание на 40 мин на слот WB 14:00 рейс 4521",
      "customer": "WB",
      "created_at": "2026-03-06T14:30:15Z",
      "status": "created",
      "reviewed_by": null
    }
  ],
  "total": 45,
  "limit": 20,
  "offset": 0
}
```

---

#### GET /api/alerts/{alert_id}
Получить деталь одного алерта.

**Запрос:**
```
GET /api/alerts/ae-550e8400-e29b-41d4-a716-446655440000
Authorization: Bearer {token}
```

**Ответ (200 OK):**
```json
{
  "alert_id": "ae-550e8400-e29b-41d4-a716-446655440000",
  "trip_id": "4521",
  "alert_type": "delay",
  "severity": "MEDIUM",
  "message": "Возможное опоздание на 40 мин на слот WB 14:00 рейс 4521",
  "customer": "WB",
  "parsed_data": {
    "trip_id": "4521",
    "route_from": "Москва",
    "route_to": "Краснодар",
    "slot_time": "14:00",
    "status": "in_progress",
    "customer": "WB",
    "urgency": "medium",
    "issue": "Стою в пробке, опаздываю на 40 мин",
    "confidence": 0.87
  },
  "created_at": "2026-03-06T14:30:15Z",
  "status": "created",
  "reviewed_by": null,
  "reviewed_at": null,
  "resolved_at": null
}
```

---

#### POST /api/alerts/{alert_id}/review
Отметить алерт как просмотренный.

**Запрос:**
```
POST /api/alerts/ae-550e8400-e29b-41d4-a716-446655440000/review
Authorization: Bearer {token}
Content-Type: application/json

{
  "reviewed_by": "Виктория Фимина"
}
```

**Ответ (200 OK):**
```json
{
  "alert_id": "ae-550e8400-e29b-41d4-a716-446655440000",
  "status": "reviewed",
  "reviewed_by": "Виктория Фимина",
  "reviewed_at": "2026-03-06T14:35:20Z"
}
```

---

#### POST /api/alerts/{alert_id}/resolve
Отметить алерт как разрешённый.

**Запрос:**
```
POST /api/alerts/ae-550e8400-e29b-41d4-a716-446655440000/resolve
Authorization: Bearer {token}
Content-Type: application/json

{}
```

**Ответ (200 OK):**
```json
{
  "alert_id": "ae-550e8400-e29b-41d4-a716-446655440000",
  "status": "resolved",
  "resolved_at": "2026-03-06T18:00:00Z"
}
```

---

## 5. Критерии приёмки

### AC-AE-001: Алерт создаётся при urgency >= medium
**Given** парсер вернул parsed_data с urgency='medium' и confidence >= 0.60
**When** Alert Engine обрабатывает это сообщение
**Then** алерт создаётся в таблице alerts с severity MEDIUM или выше

**Пример:** Парсер — "Стою в пробке, опаздываю на 40 мин", confidence=0.87, urgency='medium', customer='WB'
**Expected:** Алерт (trip_id=4521, alert_type=delay, severity=MEDIUM, message="Возможное опоздание на 40 мин...")

---

### AC-AE-002: Алерт НЕ создаётся при confidence < 0.60
**Given** парсер вернул parsed_data с confidence=0.55
**When** Alert Engine обрабатывает это сообщение
**Then** алерт НЕ создаётся, логируется decision='skipped_low_confidence'

---

### AC-AE-003: Дедупликация за 5 минут
**Given** алерт с trip_id=4521, alert_type=delay создан в 14:30:00
**When** в 14:32:00 приходит ещё одно сообщение с тем же trip_id и типом
**Then** новый алерт НЕ создаётся, логируется decision='deduplicated'
**And** через 5 минут (14:35:00) дубль может быть создан

---

### AC-AE-004: Severity HIGH для опоздания >4 часов
**Given** issue содержит "опоздание на 5 часов" и customer=WB
**When** Alert Engine обрабатывает parsed_data
**Then** severity = 'HIGH' (потому что 5ч > 4ч = 15% штраф)

---

### AC-AE-005: Severity MEDIUM для опоздания 1–4 часа
**Given** issue содержит "опоздание на 2 часа" и customer=WB
**When** Alert Engine обрабатывает parsed_data
**Then** severity = 'MEDIUM'

---

### AC-AE-006: Магнит разрешает простой, X5 нет
**Given** issue содержит "стою в простое 7 часов"
**When** Alert Engine обрабатывает для customer='X5'
**Then** severity = 'HIGH' (X5 не разрешает)
**And** When customer='Магнит'
**Then** severity = 'LOW' или вообще не создаётся (Магнит разрешает)

---

### AC-AE-007: API /api/alerts возвращает отфильтрованный список
**Given** в БД 45 алертов (20 HIGH, 15 MEDIUM, 10 LOW)
**When** запрос GET /api/alerts?severity=HIGH&limit=10
**Then** возвращает первые 10 HIGH-алертов с total=20

---

### AC-AE-008: API /api/alerts/{alert_id}/review обновляет статус
**Given** алерт со статусом 'created'
**When** POST /api/alerts/{alert_id}/review с reviewed_by="Виктория"
**Then** status обновляется на 'reviewed', reviewed_by="Виктория", reviewed_at=NOW()

---

### AC-AE-009: Алерт с trip_id=NULL допустим (информационный)
**Given** ДТП на М4 не связано с конкретным рейсом
**When** Alert Engine создаёт алерт без trip_id
**Then** запись создана с trip_id=NULL, severity=MEDIUM, alert_type=downtime, customer=NULL

---

### AC-AE-010: Логирование в JSON-формате
**Given** Alert Engine создан алерт
**When** событие логируется
**Then** лог содержит JSON с полями: timestamp, decision, alert_id, trip_id, customer, alert_type, severity, reason

**Пример:**
```json
{
  "timestamp": "2026-03-06T14:30:15.123Z",
  "decision": "created",
  "alert_id": "ae-550e8400...",
  "trip_id": "4521",
  "customer": "WB",
  "alert_type": "delay",
  "severity": "MEDIUM"
}
```

---

### AC-AE-011: Правила загружаются из YAML
**Given** файл `/opt/marshall-listener/config/alert_rules.yaml` содержит правила для 6 заказчиков
**When** Alert Engine запускается
**Then** правила загружаются в кеш, 6 заказчиков готовы к обработке

---

### AC-AE-012: Equipment_failure алерт для поломки рефа
**Given** issue содержит "реф не выходит на температуру +8" и urgency=high
**When** Alert Engine обрабатывает данные
**Then** alert_type='equipment_failure', severity='HIGH'

---

## 6. Стратегия тестирования

### 6.1 Юнит-тесты

**Модуль:** `alert_engine/rules_matcher.py`

```python
def test_urgency_low_not_triggered():
    """urgency < medium должен пропускаться"""
    alert = process_parsed_data({
        "urgency": "low",
        "issue": "небольшой вопрос",
        "confidence": 0.95
    })
    assert alert is None  # Не создаётся

def test_confidence_threshold():
    """confidence < 0.60 должен пропускаться"""
    alert = process_parsed_data({
        "urgency": "high",
        "issue": "может быть проблема",
        "confidence": 0.55
    })
    assert alert is None

def test_deduplication_window():
    """Алерт в окне 5 мин не дублируется"""
    alert1 = process_parsed_data({"trip_id": "4521", ...}, time=0)
    alert2 = process_parsed_data({"trip_id": "4521", ...}, time=120)  # 2 мин позже
    assert alert1.id != alert2.id  # Это один алерт
    assert count_alerts(trip_id="4521") == 1

def test_severity_mapping_thander_temp():
    """Тандер + температура +8 → severity=HIGH"""
    alert = process_parsed_data({
        "customer": "Тандер",
        "urgency": "high",
        "issue": "температура +8 вместо +2",
        "confidence": 0.92
    })
    assert alert.severity == "HIGH"

def test_severity_mapping_x5_vs_magnet():
    """X5 простой 7ч → HIGH, Магнит 7ч → LOW"""
    alert_x5 = process_parsed_data({
        "customer": "X5",
        "issue": "стою 7 часов",
        "urgency": "medium",
        "confidence": 0.85
    })
    assert alert_x5.severity == "HIGH"

    alert_magnet = process_parsed_data({
        "customer": "Магнит",
        "issue": "стою 7 часов",
        "urgency": "medium",
        "confidence": 0.85
    })
    assert alert_magnet.severity == "LOW"
```

### 6.2 Интеграционные тесты

**Модуль:** `alert_engine/integration_test.py`

```python
def test_alert_created_in_db():
    """Алерт создаётся в PostgreSQL"""
    parsed_data = {
        "trip_id": "4521",
        "customer": "WB",
        "urgency": "medium",
        "issue": "опаздываю 40 мин",
        "confidence": 0.87
    }

    engine = AlertEngine(config_path="config/alert_rules.yaml", db_url="postgres://...")
    alert_id = engine.process(parsed_data)

    # Проверить в БД
    row = db.query("SELECT * FROM alerts WHERE alert_id = %s", (alert_id,))
    assert row.trip_id == "4521"
    assert row.alert_type == "delay"
    assert row.severity == "MEDIUM"

def test_api_review_endpoint():
    """API endpoint /review обновляет статус"""
    alert_id = "ae-550e8400..."

    response = requests.post(
        f"http://localhost:8000/api/alerts/{alert_id}/review",
        json={"reviewed_by": "Виктория Фимина"}
    )

    assert response.status_code == 200
    assert response.json()["status"] == "reviewed"

def test_filtering_by_severity():
    """Фильтр по severity работает"""
    response = requests.get(
        "http://localhost:8000/api/alerts?severity=HIGH"
    )

    assert response.status_code == 200
    data = response.json()
    assert all(a["severity"] == "HIGH" for a in data["data"])
```

### 6.3 Сценарные тесты (E2E)

| Сценарий | Входные данные | Ожидаемый выход | Проверка |
|----------|---------------|----------------|---------|
| **Опоздание WB** | urgency=medium, issue="пробка", customer=WB, trip_id=4521 | alert_type=delay, severity=MEDIUM | Дашборд показывает алерт |
| **Поломка рефа** | urgency=high, issue="реф +8", customer=Тандер | alert_type=equipment_failure, severity=HIGH | HIGH красный в дашборде |
| **Простой X5** | issue="стою 3ч", customer=X5 | alert_type=downtime, severity=HIGH | HIGH для X5 |
| **Простой Магнит** | issue="стою 3ч", customer=Магнит | alert_type=downtime, severity=LOW | LOW в дашборде |
| **Low confidence** | confidence=0.55, urgency=high | Нет алерта | Лог: skipped_low_confidence |
| **Дедупликация** | Два одинаковых trip_id за 3 мин | Один алерт | Счётчик deduplicated_total +1 |

---

## 7. Зависимости

### 7.1 Зависимости от других модулей

| Модуль | Интерфейс | Причина |
|--------|-----------|--------|
| **AI Parser (S0-F02)** | Parsed message data (JSON) | Alert Engine работает с выходом парсера |
| **Chat Listener (S0-F01)** | Raw message → Parser | Цепочка: Listener → Parser → Alert Engine |
| **PostgreSQL** | alerts table | Хранилище алертов |
| **FastAPI (Dashboard)** | REST API endpoints | Дашборд читает через API |

### 7.2 Внешние зависимости

- PostgreSQL 15+ (таблица alerts)
- Python 3.11+ (asyncio, pydantic)
- PyYAML (загрузка конфига)
- python-json-logger (логирование)
- Prometheus client (метрики)

---

## 8. Примеры и граничные случаи

### 8.1 Пример 1: Опоздание на слот WB

**Сценарий:** Водитель сообщает об опоздании на слот WB.

**Входные данные:**
```json
{
  "trip_id": "4521",
  "customer": "WB",
  "urgency": "medium",
  "issue": "Стою в пробке на МКАД, опаздываю на 40 минут",
  "confidence": 0.87,
  "slot_time": "14:00"
}
```

**Обработка Alert Engine:**
1. Уверенность 0.87 >= 0.60 ✓
2. urgency='medium' >= 'low' ✓
3. Правило WB: condition содержит "опоздание" + urgency="medium" ✓
4. Severity: 40 мин < 4 часов → MEDIUM
5. Создать алерт

**Выход:**
```json
{
  "alert_id": "ae-550e8400-e29b-41d4-a716-446655440000",
  "trip_id": "4521",
  "alert_type": "delay",
  "severity": "MEDIUM",
  "message": "Возможное опоздание на 40 мин на слот WB 14:00 рейс 4521",
  "customer": "WB",
  "created_at": "2026-03-06T14:30:15Z",
  "status": "created"
}
```

**В дашборде:** Жёлтая строка в таблице алертов (MEDIUM).

---

### 8.2 Пример 2: Поломка рефрижератора (Тандер)

**Сценарий:** Компрессор отказал, температура поднялась до +8 (нужно +2..+4).

**Входные данные:**
```json
{
  "trip_id": "7803",
  "customer": "Тандер",
  "urgency": "high",
  "issue": "Реф не выходит на температуру, показывает +8. Мастер смотрит, компрессор.",
  "confidence": 0.92
}
```

**Обработка Alert Engine:**
1. Уверенность 0.92 >= 0.60 ✓
2. urgency='high' ✓
3. Правило Тандер (id: thander_temp_violation): issue содержит ['температура', 'реф', '+8'] ✓
4. Severity: HIGH (потеря груза)
5. Создать алерт

**Выход:**
```json
{
  "alert_id": "ae-550e8401-e29b-41d4-a716-446655440001",
  "trip_id": "7803",
  "alert_type": "equipment_failure",
  "severity": "HIGH",
  "message": "КРИТИЧНО: Нарушение температуры у Тандер 7803: Реф не выходит на температуру, показывает +8",
  "customer": "Тандер",
  "created_at": "2026-03-06T07:45:00Z",
  "status": "created"
}
```

**В дашборде:** Красная строка (HIGH). Диспетчер должен немедленно найти замену машины.

---

### 8.3 Пример 3: Простой на X5 vs Магнит

**Сценарий A: X5**

**Входные данные:**
```json
{
  "trip_id": "4590",
  "customer": "X5",
  "urgency": "medium",
  "issue": "Жду разгрузки 6 часов на территории X5, они не разгружают",
  "confidence": 0.85
}
```

**Обработка:** Правило X5 (id: x5_downtime_critical): downtime > 2h AND customer=X5 → severity=HIGH (X5 не разрешает стоять)

**Выход:**
```json
{
  "severity": "HIGH",
  "message": "НАРУШЕНИЕ: X5 запрещает стоять, уже 6ч простоя на 4590"
}
```

---

**Сценарий B: Магнит (тот же простой)**

**Входные данные:**
```json
{
  "trip_id": "4591",
  "customer": "Магнит",
  "urgency": "medium",
  "issue": "Жду разгрузки 6 часов на территории Магнит, они разгружают медленно",
  "confidence": 0.85
}
```

**Обработка:** Правило Магнит НЕ срабатывает (простой на территории разрешен). Может быть только LOW-алерт для информации.

**Выход:**
```json
{
  "severity": "LOW",
  "message": "Магнит 4591: Простой 6 часов (в норме для Магнит)"
}
```

**Ключевой момент:** Один и тот же сценарий (6 часов простоя) интерпретируется по-разному в зависимости от заказчика.

---

### 8.4 Пример 4: ДТП на трассе (информационный алерт)

**Сценарий:** Глобальное событие — ДТП на М4, не связано с конкретным рейсом.

**Входные данные:**
```json
{
  "trip_id": null,
  "customer": null,
  "urgency": "high",
  "issue": "ДТП на М4 Дон км 680. Наш водитель НЕ участвует, но пробка может повлиять на рейсы",
  "confidence": 0.88
}
```

**Обработка:** Глобальное правило (id: global_traffic_incident): issue содержит 'ДТП' AND urgency=high → severity=MEDIUM

**Выход:**
```json
{
  "alert_id": "ae-550e8402-e29b-41d4-a716-446655440002",
  "trip_id": null,
  "alert_type": "downtime",
  "severity": "MEDIUM",
  "message": "Инцидент на трассе: ДТП на М4 Дон км 680 — возможны задержки",
  "customer": null,
  "created_at": "2026-03-06T10:30:00Z",
  "status": "created"
}
```

**В дашборде:** Информационный алерт для менеджера (без trip_id, может затронуть несколько рейсов).

---

### 8.5 Граничный случай 1: Низкая уверенность парсера

**Входные данные:**
```json
{
  "urgency": "high",
  "issue": "может быть какая-то проблема?",
  "confidence": 0.45
}
```

**Обработка:** confidence=0.45 < 0.60 → SKIP

**Лог:**
```json
{
  "decision": "skipped_low_confidence",
  "confidence": 0.45,
  "reason": "Below threshold 0.60"
}
```

---

### 8.6 Граничный случай 2: Дедупликация

**Время 14:30:00 — Первое сообщение:**
```json
{
  "trip_id": "4521",
  "issue": "Стою в пробке, опаздываю",
  "confidence": 0.87
}
```
→ Алерт создан (alert_id=`ae-001`)

**Время 14:32:00 — Повторное сообщение (парсер retry):**
```json
{
  "trip_id": "4521",
  "issue": "Стою в пробке, опаздываю",
  "confidence": 0.87
}
```
→ В БД есть алерт с trip_id=4521, alert_type=delay, created_at > 14:27:00 (5 мин назад) → SKIP

**Лог:**
```json
{
  "decision": "deduplicated",
  "trip_id": "4521",
  "existing_alert_id": "ae-001",
  "reason": "Alert already exists for this trip and type within 5 min window"
}
```

**Счётчик:** `alerts_deduplicated_total` +1

---

### 8.7 Граничный случай 3: Неизвестный заказчик

**Входные данные:**
```json
{
  "trip_id": "9999",
  "customer": "UnknownCarrier",
  "urgency": "high",
  "issue": "Критическая проблема",
  "confidence": 0.90
}
```

**Обработка:** Правила для UnknownCarrier не найдены → fallback на базовые триггеры:
- urgency=high → severity >= MEDIUM
- issue содержит "критическая" → alert_type=delay (базовый)

**Выход:**
```json
{
  "alert_type": "delay",
  "severity": "MEDIUM",
  "message": "Неизвестный заказчик UnknownCarrier: Критическая проблема",
  "customer": "UnknownCarrier"
}
```

**Лог:**
```json
{
  "decision": "created",
  "reason": "No specific rules found, using fallback",
  "customer": "UnknownCarrier"
}
```

---

## 9. Метрики и мониторинг

### 9.1 Ключевые метрики

| Метрика | Тип | Примечание |
|---------|-----|-----------|
| `alerts_created_total` | Counter | Количество созданных алертов |
| `alerts_deduplicated_total` | Counter | Дубли, не созданные |
| `alerts_skipped_low_confidence_total` | Counter | Пропущены из-за низкой уверенности |
| `alerts_by_type` | Gauge | Распределение по типам (delay, equipment, downtime, safety, docs) |
| `alerts_by_severity` | Gauge | Распределение по severity (HIGH, MEDIUM, LOW) |
| `alerts_by_customer` | Gauge | Распределение по заказчикам |
| `alert_processing_latency_ms` | Histogram | Время парсированные данные → алерт создан |
| `db_write_latency_ms` | Histogram | Время записи в PostgreSQL |

### 9.2 SLA и целевые показатели

| Показатель | Целевое значение |
|-----------|-----------------|
| Alert latency (parsed data → created) | ≤ 100 мс |
| Деупликация работает | 0 ошибок в дедупе |
| Правила загружаются | При каждом рестарте |
| Логирование структурировано | 100% вывод в JSON |

---

## 10. Заключение

Alert Engine — критическое звено в цепочке Marshall AI Listener. Он преобразует неструктурированный текст диспетчеров в структурированные алерты, позволяя менеджерам оперативно действовать и избегать штрафов. Конфигурируемые правила, асинхронная обработка и строгие критерии приёмки гарантируют надёжность в production.

**Дата создания спеки:** 2026-03-06
**Версия:** 1.0
**Статус:** ГОТОВО К РЕАЛИЗАЦИИ
