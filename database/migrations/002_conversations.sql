CREATE TABLE conversations (
    id uuid PRIMARY KEY,
    owner_id varchar(128) NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX conversations_owner_updated_idx
    ON conversations (owner_id, updated_at DESC);

CREATE TABLE conversation_turns (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    conversation_id uuid NOT NULL
        REFERENCES conversations(id)
        ON DELETE CASCADE,

    turn integer NOT NULL
        CHECK (turn > 0),

    query text NOT NULL
        CHECK (length(btrim(query)) > 0),

    answer text NOT NULL
        CHECK (length(btrim(answer)) > 0),

    domain varchar(32) NOT NULL,
    risk varchar(32) NOT NULL,
    source varchar(64) NOT NULL,

    created_at timestamptz NOT NULL DEFAULT now(),

    UNIQUE (conversation_id, turn)
);
