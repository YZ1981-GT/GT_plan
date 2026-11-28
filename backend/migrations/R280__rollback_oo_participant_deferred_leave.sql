-- R280: 回滚 V280（移除 working_paper_oo_participant.deferred_leave_at）
--
-- 该列是纯标记（无 FK / 无约束依赖）。回滚只丢「尚未被结算执行的延迟离开登记」——
-- 对应 participant 仍是 active/closing，行为回退到「等 lease 过期」的旧形态，
-- 不阻塞任何在途 apply。
ALTER TABLE working_paper_oo_participant
    DROP COLUMN IF EXISTS deferred_leave_at;
