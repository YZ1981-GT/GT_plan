-- procedure-mainline-convergence Task 6: allow 'reviewer_update' action in delegation history
-- 幂等：IF NOT EXISTS 形式不适用于 CHECK 约束重建，改用 DROP + ADD

ALTER TABLE workpaper_delegation_history
    DROP CONSTRAINT IF EXISTS ck_wp_deleg_history_action;

ALTER TABLE workpaper_delegation_history
    ADD CONSTRAINT ck_wp_deleg_history_action
    CHECK (action IN ('assign', 'reassign', 'clear', 'reviewer_update', 'noop'));
