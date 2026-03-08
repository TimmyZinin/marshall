-- Migration 002: Add DM and voice support
-- Sprint 5: MTProto DM Listener
-- Sprint 6: Whisper STT

-- Add source_type and voice fields to raw_messages
ALTER TABLE raw_messages ADD COLUMN IF NOT EXISTS source_type VARCHAR(25) NOT NULL DEFAULT 'group_chat';
ALTER TABLE raw_messages ADD COLUMN IF NOT EXISTS is_voice BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE raw_messages ADD COLUMN IF NOT EXISTS audio_duration_sec INTEGER DEFAULT 0;

-- Index for filtering by source type
CREATE INDEX IF NOT EXISTS idx_raw_messages_source_type ON raw_messages(source_type);

-- Dispatcher sessions table (for MTProto multi-account)
CREATE TABLE IF NOT EXISTS dispatcher_sessions (
    id              SERIAL          PRIMARY KEY,
    dispatcher_name VARCHAR(255)    NOT NULL,
    phone           VARCHAR(20),
    telegram_id     BIGINT,
    session_string  TEXT            NOT NULL,
    is_active       BOOLEAN         NOT NULL DEFAULT TRUE,
    listen_dm       BOOLEAN         NOT NULL DEFAULT TRUE,
    listen_groups   BOOLEAN         NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_dispatcher_sessions_active ON dispatcher_sessions(is_active) WHERE is_active = TRUE;

-- Make message_id dedup smarter: same message_id can come from different chats/sources
-- Drop old unique constraint and add composite one
-- (Safely handle if constraint already exists)
DO $$
BEGIN
    -- Check if the old single-column unique constraint exists
    IF EXISTS (
        SELECT 1 FROM pg_indexes
        WHERE tablename = 'raw_messages'
        AND indexname = 'raw_messages_message_id_key'
    ) THEN
        ALTER TABLE raw_messages DROP CONSTRAINT raw_messages_message_id_key;
        CREATE UNIQUE INDEX IF NOT EXISTS idx_raw_messages_dedup
            ON raw_messages(chat_id, message_id);
    END IF;
END $$;
