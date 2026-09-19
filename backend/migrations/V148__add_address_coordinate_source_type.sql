-- V148: Add 'address_coordinate' to knowledge_source_type_enum
-- Feature: dsh-agent-panel-integration Task 22 (Req 6.2)
-- Idempotent: IF NOT EXISTS prevents duplicate enum values on re-run

DO $$
BEGIN
    -- Add address_coordinate enum value if not already present
    IF NOT EXISTS (
        SELECT 1
        FROM pg_enum
        WHERE enumlabel = 'address_coordinate'
          AND enumtypid = (
              SELECT oid FROM pg_type WHERE typname = 'knowledge_source_type_enum'
          )
    ) THEN
        ALTER TYPE knowledge_source_type_enum ADD VALUE 'address_coordinate';
    END IF;
END $$;

-- NOTE: Per migration convention, we do NOT write DML using the new enum value
-- in the same transaction (asyncpg cannot see new enum values within the
-- transaction that added them). IndexSource registration happens in application
-- code at runtime.
