-- R113: 回滚 V113（统一委派历史、安全审计 outbox 与 policy epoch/invalidation outbox）
-- Spec: procedure-delegation-visibility-isolation / Task 2
--
-- 逆序拆除 V113 新增对象：先 DROP 触发器与表（DROP TABLE 一并移除其上触发器与约束），
-- 再 DROP 共享触发器函数。DROP TABLE 不受行级 append-only 触发器影响（触发器只拦 DML，不拦 DDL）。
-- 幂等：全部 IF EXISTS。CASCADE 仅用于表内自身依赖，不外溢删除其它对象。

DROP TABLE IF EXISTS wp_visibility_invalidation_outbox;
DROP TABLE IF EXISTS wp_visibility_policy_epoch;
DROP TABLE IF EXISTS wp_access_security_outbox;
DROP TABLE IF EXISTS workpaper_delegation_history;

DROP FUNCTION IF EXISTS wp_visibility_epoch_monotonic();
DROP FUNCTION IF EXISTS wp_visibility_forbid_mutation();
