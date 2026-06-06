ALTER TABLE talleres.taller
ADD COLUMN IF NOT EXISTS radio_cobertura_km DOUBLE PRECISION NOT NULL DEFAULT 10.0;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'ck_taller_radio_cobertura_km_positive'
    ) THEN
        ALTER TABLE talleres.taller
        ADD CONSTRAINT ck_taller_radio_cobertura_km_positive
        CHECK (radio_cobertura_km > 0);
    END IF;
END $$;
