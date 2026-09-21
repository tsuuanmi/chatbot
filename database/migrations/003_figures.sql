CREATE TABLE figure_descriptions (
    figure_id text PRIMARY KEY,
    content_hash text NOT NULL,
    mime_type text NOT NULL,
    source_name text NOT NULL,
    description_version integer NOT NULL,
    description text NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT figure_descriptions_id_check
        CHECK (
            figure_id ~ '^[a-z0-9][a-z0-9_-]{0,127}$'
        ),

    CONSTRAINT figure_descriptions_hash_check
        CHECK (
            content_hash ~ '^[0-9a-f]{64}$'
        ),

    CONSTRAINT figure_descriptions_mime_check
        CHECK (
            mime_type IN (
                'image/png',
                'image/jpeg',
                'image/webp'
            )
        ),

    CONSTRAINT figure_descriptions_version_check
        CHECK (
            description_version > 0
        ),

    CONSTRAINT figure_descriptions_description_check
        CHECK (
            btrim(description) <> ''
        )
);
