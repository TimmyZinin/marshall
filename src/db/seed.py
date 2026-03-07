"""Demo seed data — realistic logistics scenarios for Marshall AI Listener."""
import random
from datetime import datetime, timedelta, timezone
from src.api.auth import hash_password

CUSTOMERS = ["Тандер", "WB", "X5", "Магнит", "Сельта", "Сибур"]
CITIES = [
    ("Москва", "Краснодар"), ("Москва", "Ростов-на-Дону"), ("Санкт-Петербург", "Москва"),
    ("Новосибирск", "Красноярск"), ("Екатеринбург", "Челябинск"), ("Казань", "Нижний Новгород"),
    ("Самара", "Волгоград"), ("Воронеж", "Тула"), ("Краснодар", "Сочи"), ("Ростов-на-Дону", "Волгоград"),
    ("Москва", "Тверь"), ("Москва", "Рязань"), ("Санкт-Петербург", "Великий Новгород"),
]
DRIVERS = ["Иванов А.П.", "Петров С.В.", "Сидоров К.М.", "Козлов Д.И.", "Николаев В.А.",
           "Морозов И.Г.", "Волков Р.Т.", "Соколов А.Н.", "Лебедев П.О.", "Новиков Е.С."]
DISPATCHERS = ["Диспетчер_Анна", "Диспетчер_Мария", "Диспетчер_Олег", "Диспетчер_Сергей"]

STATUSES = ["assigned", "in_transit", "loading", "unloading", "completed", "problem"]
ALERT_TYPES = ["delay", "equipment_failure", "downtime", "safety_violation", "docs_missing"]
SEVERITIES = ["high", "medium", "low"]

CHAT_MESSAGES = [
    ("Рейс {trip}, {fr}-{to}, слот {cust} {time}. Водитель {drv} подтвердил выезд.", "assigned"),
    ("Рейс {trip}, водитель {drv} выехал из {fr}. ETA {to} — {time}.", "in_transit"),
    ("{drv}: Стою в пробке на М4, опоздание минут на 40. Рейс {trip}.", "problem"),
    ("{drv}: Прибыл на погрузку {cust}, {to}. Рейс {trip}. Жду очередь.", "loading"),
    ("{drv}: Реф не выходит на температуру +8, рейс {trip}. Нужна помощь.", "problem"),
    ("{drv}: Выгрузка завершена, рейс {trip}. Документы подписаны.", "completed"),
    ("{drv}: Рейс {trip}, забыл термограмму. Вернуться?", "problem"),
    ("{disp}: Рейс {trip} под {cust}. Водитель {drv}, маршрут {fr}-{to}. Слот на {time}.", "assigned"),
    ("{drv}: Рейс {trip}, на территории {cust}, каска и жилет на месте.", "loading"),
    ("{disp}: Рейс {trip}, водитель {drv} опаздывает. Предупредите {cust}.", "problem"),
    ("{drv}: Рейс {trip}, прибыл на {to}. Разгрузка начата.", "unloading"),
    ("{drv}: Рейс {trip}, все ок, еду по графику. {fr}-{to}.", "in_transit"),
    ("{disp}: Внимание! Рейс {trip}, клиент {cust} — штраф за опоздание >4ч = 15%!", "problem"),
    ("{drv}: Рейс {trip}, компрессор рефа отключился на трассе. Температура растёт.", "problem"),
    ("{drv}: Рейс {trip}, {cust}. ТСД не считывает штрихкод. Задержка на приёмке.", "problem"),
]

ALERT_MESSAGES = {
    "delay": [
        "Задержка рейса {trip}: водитель опаздывает на {mins} мин. Штраф {cust} >4ч = 15%.",
        "Рейс {trip}: превышено допустимое время прибытия. Задержка {mins} мин.",
    ],
    "equipment_failure": [
        "Рейс {trip}: рефрижератор не выходит на температуру. Текущая: +{temp}°C.",
        "Рейс {trip}: отказ компрессора рефа. Требуется техпомощь.",
    ],
    "downtime": [
        "Рейс {trip}: простой на территории {cust} > {hrs} часов.",
    ],
    "safety_violation": [
        "Рейс {trip}: водитель без каски/жилета на территории {cust}.",
    ],
    "docs_missing": [
        "Рейс {trip}: отсутствует термограмма. Штраф {cust}.",
        "Рейс {trip}: нет накладной ТТН. Задержка выгрузки.",
    ],
}


async def seed_demo(pool):
    """Seed database with realistic demo data."""
    now = datetime.now(timezone.utc)

    # 1. Create demo users
    users = [
        ("admin", hash_password("admin123"), "admin"),
        ("manager", hash_password("manager123"), "manager"),
        ("viewer", hash_password("viewer123"), "viewer"),
    ]
    for username, pw_hash, role in users:
        await pool.execute(
            """INSERT INTO dashboard_users (username, password_hash, role)
               VALUES ($1, $2, $3) ON CONFLICT (username) DO NOTHING""",
            username, pw_hash, role,
        )

    msg_id_counter = 100000
    # 2. Create trips, messages, alerts
    for i in range(50):
        trip_id = str(4500 + i)
        fr, to = random.choice(CITIES)
        customer = random.choice(CUSTOMERS)
        driver = random.choice(DRIVERS)
        dispatcher = random.choice(DISPATCHERS)
        trip_status = random.choices(STATUSES, weights=[10, 30, 10, 10, 25, 15])[0]
        created = now - timedelta(hours=random.randint(1, 168))
        slot = created + timedelta(hours=random.randint(6, 24))

        # Insert trip
        await pool.execute(
            """INSERT INTO trips (trip_id, route_from, route_to, customer, driver_name,
               dispatcher_name, status, slot_time, created_at, updated_at, last_update)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$9,$9)
               ON CONFLICT (trip_id) DO NOTHING""",
            trip_id, fr, to, customer, driver, dispatcher, trip_status, slot, created,
        )

        # Insert 3-6 chat messages per trip
        chat_id = -1001000000000 - random.randint(1, 3)
        chat_name = random.choice(["Диспетчерская WB", "Общая диспетчерская", "Логистика Тандер"])
        num_msgs = random.randint(3, 6)
        msg_time = created

        for j in range(num_msgs):
            msg_time = msg_time + timedelta(minutes=random.randint(10, 180))
            template, msg_status = random.choice(CHAT_MESSAGES)
            text = template.format(
                trip=trip_id, fr=fr, to=to, cust=customer, drv=driver,
                disp=dispatcher, time=slot.strftime("%H:%M"),
            )
            msg_id_counter += 1
            sender = driver if random.random() > 0.3 else dispatcher
            sender_id = hash(sender) % 1000000000

            await pool.execute(
                """INSERT INTO raw_messages (chat_id, chat_name, sender_id, sender_name,
                   message_id, text, timestamp) VALUES ($1,$2,$3,$4,$5,$6,$7)
                   ON CONFLICT (message_id) DO NOTHING""",
                chat_id, chat_name, sender_id, sender, msg_id_counter, text, msg_time,
            )

            # Parse message
            confidence = round(random.uniform(0.7, 0.98), 2)
            raw_id = await pool.fetchval(
                "SELECT id FROM raw_messages WHERE message_id = $1", msg_id_counter
            )
            if raw_id:
                await pool.execute(
                    """INSERT INTO parsed_messages (raw_message_id, trip_id, route_from, route_to,
                       status, customer, urgency, confidence, llm_model, llm_tokens_used,
                       parse_duration_ms, created_at)
                       VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)""",
                    raw_id, trip_id, fr, to, msg_status, customer,
                    random.choice(["low", "low", "medium"]),
                    confidence, random.choice(["minimax", "minimax", "groq"]),
                    random.randint(100, 800), random.randint(500, 3000), msg_time,
                )

        # Insert 0-3 alerts per trip
        num_alerts = random.choices([0, 1, 2, 3], weights=[30, 35, 25, 10])[0]
        alert_count = 0
        for _ in range(num_alerts):
            atype = random.choice(ALERT_TYPES)
            severity = random.choices(SEVERITIES, weights=[25, 45, 30])[0]
            templates = ALERT_MESSAGES[atype]
            amsg = random.choice(templates).format(
                trip=trip_id, cust=customer, mins=random.randint(20, 180),
                temp=random.randint(5, 12), hrs=random.randint(2, 8),
            )
            astatus = random.choices(["new", "reviewed", "resolved"], weights=[40, 30, 30])[0]

            # Get a random parsed_message_id for this trip
            pm_id = await pool.fetchval(
                "SELECT id FROM parsed_messages WHERE trip_id = $1 ORDER BY RANDOM() LIMIT 1",
                trip_id,
            )
            if pm_id:
                alert_time = msg_time + timedelta(minutes=random.randint(1, 30))
                reviewed_at = alert_time + timedelta(minutes=random.randint(5, 60)) if astatus != "new" else None
                await pool.execute(
                    """INSERT INTO alerts (trip_id, parsed_message_id, type, severity, message,
                       customer, status, reviewed_by, reviewed_at, created_at)
                       VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)""",
                    trip_id, pm_id, atype, severity, amsg, customer, astatus,
                    "manager" if astatus != "new" else None, reviewed_at, alert_time,
                )
                alert_count += 1

        # Update alert_count on trip
        if alert_count > 0:
            await pool.execute(
                "UPDATE trips SET alert_count = $1 WHERE trip_id = $2", alert_count, trip_id
            )
