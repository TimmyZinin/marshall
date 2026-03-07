-- Marshall AI Listener — Initial Schema
-- Sprint 0: 5 tables + indexes

-- 1. Raw messages from Telegram chats
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

-- 2. LLM-parsed structured data
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
                            'assigned', 'in_transit', 'loading',
                            'unloading', 'completed', 'problem', 'cancelled'
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

-- 3. Alerts
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

-- 4. Aggregated trips
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
                            'assigned', 'in_transit', 'loading',
                            'unloading', 'completed', 'problem', 'cancelled'
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

-- 5. Dashboard users
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

-- Indexes: raw_messages
CREATE INDEX IF NOT EXISTS idx_raw_messages_chat_id ON raw_messages(chat_id);
CREATE INDEX IF NOT EXISTS idx_raw_messages_timestamp ON raw_messages(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_raw_messages_chat_timestamp ON raw_messages(chat_id, timestamp DESC);

-- Indexes: parsed_messages
CREATE INDEX IF NOT EXISTS idx_parsed_messages_raw_message_id ON parsed_messages(raw_message_id);
CREATE INDEX IF NOT EXISTS idx_parsed_messages_trip_id ON parsed_messages(trip_id);
CREATE INDEX IF NOT EXISTS idx_parsed_messages_customer ON parsed_messages(customer);
CREATE INDEX IF NOT EXISTS idx_parsed_messages_status ON parsed_messages(status);
CREATE INDEX IF NOT EXISTS idx_parsed_messages_created_at ON parsed_messages(created_at DESC);

-- Indexes: alerts
CREATE INDEX IF NOT EXISTS idx_alerts_severity ON alerts(severity);
CREATE INDEX IF NOT EXISTS idx_alerts_status ON alerts(status);
CREATE INDEX IF NOT EXISTS idx_alerts_trip_id ON alerts(trip_id);
CREATE INDEX IF NOT EXISTS idx_alerts_customer ON alerts(customer);
CREATE INDEX IF NOT EXISTS idx_alerts_created_at ON alerts(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_alerts_active_high ON alerts(severity, status) WHERE status != 'resolved';

-- Indexes: trips
CREATE INDEX IF NOT EXISTS idx_trips_customer ON trips(customer);
CREATE INDEX IF NOT EXISTS idx_trips_status ON trips(status);
CREATE INDEX IF NOT EXISTS idx_trips_created_at ON trips(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_trips_active ON trips(status) WHERE status NOT IN ('completed', 'cancelled');
