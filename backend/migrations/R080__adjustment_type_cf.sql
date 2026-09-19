-- Rollback: cannot remove enum value in PG, this is a no-op
-- ALTER TYPE ... REMOVE VALUE is not supported
SELECT 1;
