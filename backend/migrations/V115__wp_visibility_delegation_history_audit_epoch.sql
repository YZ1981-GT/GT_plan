-- V113: 统一委派历史、安全审计 outbox 与持久 policy epoch/invalidation outbox
-- Spec: procedure-delegation-visibility-isolation / Task 2
-- Requirements: 3.13-3.15, 5.18, 9.8-9.11, 14.20-14.21
-- Design: Data Models §New persistent records（C1 Persistence）
--
-- 迁移 head 已重扫为 V112（真实最高版本；不静态占用），本文件为下一空闲版本 V113。
-- additive-only：无 DROP / TRUNCATE / 改既有列。
-- 幂等：CREATE TABLE/INDEX IF NOT EXISTS + CREATE OR REPLACE FUNCTION/TRIGGER；
--       `IF NOT EXISTS` 不作为结构正确性证明，由
--       tests/procedure_delegation_visibility/test_v113_schema_contract.py
--       用 information_schema/pg_catalog 精校。
--
-- Append-only 强制方式（设计选择，记录在此）：
--   history 与两个 outbox 采用 BEFORE UPDATE OR DELETE 触发器抛异常（'55000'）实现
--   append-only；正常应用 session 禁止 UPDATE/DELETE。受控维护/回滚/测试清理须显式
--   `SET LOCAL app.wp_visibility_maintenance = 'on'`（与 V112
--   prevent_procedure_row_task_history_mutation 逃生舱一致）。DROP TABLE（回滚脚本）
--   不受行级触发器影响。
--   wp_visibility_policy_epoch 是可变单调计数器（递增），不作 append-only，改用
--   非递减触发器保证持久单调。
--   敏感正文/名称/文件字节/prompt/token 一律不入任何表（仅 request_id/actor/绑定 id/
--   reason/脱敏 detail）。

-- ============================================================
-- 0. 共享触发器函数（append-only + epoch 单调）
-- ============================================================

CREATE OR REPLACE FUNCTION wp_visibility_forbid_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $fn$
BEGIN
    -- 受控维护逃生舱：SET LOCAL app.wp_visibility_maintenance = 'on'
    IF current_setting('app.wp_visibility_maintenance', true) = 'on' THEN
        RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
    END IF;
    RAISE EXCEPTION '% 为 append-only 表，禁止 % (id=%)',
        TG_TABLE_NAME, TG_OP,
        CASE WHEN TG_OP = 'DELETE' THEN OLD.id ELSE NEW.id END
        USING ERRCODE = '55000';
END;
$fn$;

CREATE OR REPLACE FUNCTION wp_visibility_epoch_monotonic()
RETURNS trigger
LANGUAGE plpgsql
AS $fn$
BEGIN
    IF NEW.epoch < OLD.epoch THEN
        RAISE EXCEPTION 'wp_visibility_policy_epoch.epoch 必须单调非递减 (project=%, old=%, new=%)',
            OLD.project_id, OLD.epoch, NEW.epoch
            USING ERRCODE = '55000';
    END IF;
    RETURN NEW;
END;
$fn$;

-- ============================================================
-- 1. workpaper_delegation_history —— History_Set 唯一来源（不可变委派历史快照）
--    同时覆盖 lead / assignee / reviewer 三种事件；快照即真源，History_Set 计算
--    禁止回查当前 staff/task/sheet 归属。
-- ============================================================

CREATE TABLE IF NOT EXISTS workpaper_delegation_history (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id          VARCHAR(80),
    project_id          UUID NOT NULL REFERENCES projects(id),
    wp_index_id         UUID NOT NULL REFERENCES wp_index(id),
    wp_id               UUID REFERENCES working_paper(id),         -- 底稿可能尚未生成
    -- 委派层与目标角色
    layer               VARCHAR(20) NOT NULL,                      -- 'lead' | 'row'
    target_role         VARCHAR(20) NOT NULL,                      -- 'lead' | 'assignee' | 'reviewer'
    action              VARCHAR(20) NOT NULL,                      -- 'assign' | 'reassign' | 'clear'
    task_id             UUID REFERENCES procedure_row_tasks(id),   -- row 层事件的目标程序行任务
    sheet_key           VARCHAR(160),                              -- row 层快照页面；lead 层为 NULL(整稿)
    -- 事件时身份快照（同一自然人 user+staff 均固定，禁止后续回查当前映射反推）
    old_user_id         UUID REFERENCES users(id),
    new_user_id         UUID REFERENCES users(id),
    old_staff_id        UUID REFERENCES staff_members(id),
    new_staff_id        UUID REFERENCES staff_members(id),
    -- 操作人与理由
    actor_user_id       UUID NOT NULL REFERENCES users(id),
    reason              TEXT,
    -- scope 快照（扩权前/后并集），脱敏为 audit_cycle 列表
    scope_before        JSONB NOT NULL DEFAULT '[]',
    scope_after         JSONB NOT NULL DEFAULT '[]',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_wp_deleg_history_layer CHECK (layer IN ('lead', 'row')),
    CONSTRAINT ck_wp_deleg_history_role  CHECK (target_role IN ('lead', 'assignee', 'reviewer')),
    CONSTRAINT ck_wp_deleg_history_action CHECK (action IN ('assign', 'reassign', 'clear'))
);

DROP TRIGGER IF EXISTS trg_wp_deleg_history_append_only ON workpaper_delegation_history;
CREATE TRIGGER trg_wp_deleg_history_append_only
    BEFORE UPDATE OR DELETE ON workpaper_delegation_history
    FOR EACH ROW EXECUTE FUNCTION wp_visibility_forbid_mutation();

COMMENT ON TABLE workpaper_delegation_history IS
    'History_Set 唯一来源：append-only 委派历史快照（lead/assignee/reviewer 事件）。'
    '快照事件时 user/staff/wp/task/sheet/scope；History_Set 计算禁止 JOIN 当前 StaffMember/'
    'ProcedureRowTask/sheet 反推。仅存标识与脱敏 scope，不存正文/名称/token。';
COMMENT ON COLUMN workpaper_delegation_history.new_user_id IS
    '事件时被委派自然人的 user 快照（lead 与 row 层均固定），History_Set 直接按此列查，不回查当前映射';
COMMENT ON COLUMN workpaper_delegation_history.sheet_key IS
    'row 层委派的页面快照（Req 5.18 历史只读 row 参与者页面来源）；lead 层为 NULL 表示整稿';

-- ============================================================
-- 2. wp_access_security_outbox —— 内部安全审计发件箱（append-only）
--    仅记录 request/actor、可空绑定、entrypoint/family/action、内部真实 reason 与
--    enqueue 期投递元数据；正文/名称/文件字节/prompt/token 禁止入表。
-- ============================================================

CREATE TABLE IF NOT EXISTS wp_access_security_outbox (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id          VARCHAR(80),
    actor_user_id       UUID REFERENCES users(id),          -- 认证后 principal；可空以兜底早期拒绝
    -- 可空绑定（拒绝时资源可能未解析/不存在，故全部 nullable）
    project_id          UUID REFERENCES projects(id),
    wp_index_id         UUID REFERENCES wp_index(id),
    wp_id               UUID REFERENCES working_paper(id),
    sheet_key           VARCHAR(160),
    requested_version   VARCHAR(80),
    -- 入口与动作
    entrypoint          VARCHAR(200) NOT NULL,
    entry_family        VARCHAR(60),
    route_name          VARCHAR(200),
    http_method         VARCHAR(10),
    action              VARCHAR(60),
    -- 内部真实拒绝原因（对外统一 404/429，内部保留真值）
    reason              VARCHAR(40) NOT NULL,
    -- enqueue 期投递元数据（append-only：不在本表 UPDATE；投递跟踪由消费方 checkpoint 处理）
    delivery_state      VARCHAR(20) NOT NULL DEFAULT 'pending',
    delivery_attempt    INTEGER     NOT NULL DEFAULT 0,
    -- 脱敏 detail（无正文/名称/token/文件字节/绝对路径/完整 traceback）
    detail              JSONB NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_wp_access_security_outbox_reason CHECK (reason IN (
        'not_found', 'cross_project', 'out_of_scope', 'not_delegated', 'sheet_unmapped',
        'action_denied', 'historical_version', 'binding_conflict', 'token_invalid', 'rate_limited'
    ))
);

DROP TRIGGER IF EXISTS trg_wp_access_security_outbox_append_only ON wp_access_security_outbox;
CREATE TRIGGER trg_wp_access_security_outbox_append_only
    BEFORE UPDATE OR DELETE ON wp_access_security_outbox
    FOR EACH ROW EXECUTE FUNCTION wp_visibility_forbid_mutation();

COMMENT ON TABLE wp_access_security_outbox IS
    '内部安全审计发件箱（append-only）：记录拒绝事实的 request/actor、可空绑定、'
    'entrypoint/family/action 与内部真实 reason（not_found/cross_project/out_of_scope/'
    'not_delegated/sheet_unmapped/action_denied/historical_version/binding_conflict/'
    'token_invalid/rate_limited）。写入/投递失败只触发 Operational_Alert，不改变 404/429。'
    '正文/名称/文件字节/prompt/token 不得入表。';

-- ============================================================
-- 3. wp_visibility_policy_epoch —— 每项目持久单调 policy epoch（可变，非 append-only）
-- ============================================================

CREATE TABLE IF NOT EXISTS wp_visibility_policy_epoch (
    project_id          UUID PRIMARY KEY REFERENCES projects(id),
    epoch               BIGINT NOT NULL DEFAULT 1,
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_wp_visibility_policy_epoch_positive CHECK (epoch >= 1)
);

DROP TRIGGER IF EXISTS trg_wp_visibility_policy_epoch_monotonic ON wp_visibility_policy_epoch;
CREATE TRIGGER trg_wp_visibility_policy_epoch_monotonic
    BEFORE UPDATE ON wp_visibility_policy_epoch
    FOR EACH ROW EXECUTE FUNCTION wp_visibility_epoch_monotonic();

COMMENT ON TABLE wp_visibility_policy_epoch IS
    '每项目持久单调 policy epoch；权限/委派/history/scope/角色/项目成员变更须在同一业务事务内'
    '原子递增 epoch 并写 invalidation outbox。缓存 key 含此 epoch，节点最多缓存 1 秒后核对 DB。'
    'BEFORE UPDATE 触发器强制 epoch 非递减（持久单调）。';

-- ============================================================
-- 4. wp_visibility_invalidation_outbox —— 失效发件箱（append-only）
--    权限变更事务内与 epoch 递增同事务写入一行；Redis 仅在提交后 fan-out。
-- ============================================================

CREATE TABLE IF NOT EXISTS wp_visibility_invalidation_outbox (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id          UUID NOT NULL REFERENCES projects(id),
    epoch               BIGINT NOT NULL,                    -- 与 policy_epoch 递增后一致
    change_type         VARCHAR(20) NOT NULL,               -- permission/delegation/history/scope/role/membership
    request_id          VARCHAR(80),
    actor_user_id       UUID REFERENCES users(id),
    -- enqueue 期投递元数据（append-only：不在本表 UPDATE）
    delivery_state      VARCHAR(20) NOT NULL DEFAULT 'pending',
    delivery_attempt    INTEGER     NOT NULL DEFAULT 0,
    detail              JSONB NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_wp_visibility_invalidation_change_type CHECK (change_type IN (
        'permission', 'delegation', 'history', 'scope', 'role', 'membership'
    ))
);

DROP TRIGGER IF EXISTS trg_wp_visibility_invalidation_outbox_append_only ON wp_visibility_invalidation_outbox;
CREATE TRIGGER trg_wp_visibility_invalidation_outbox_append_only
    BEFORE UPDATE OR DELETE ON wp_visibility_invalidation_outbox
    FOR EACH ROW EXECUTE FUNCTION wp_visibility_forbid_mutation();

COMMENT ON TABLE wp_visibility_invalidation_outbox IS
    '可见性失效发件箱（append-only）：权限/委派/history/scope/角色/项目成员变更事务内与'
    'policy epoch 递增同事务写入。Redis 仅在提交后 fan-out；投递失败靠持久 epoch 校验兜底'
    '（≤1s 发现 stale 重查或拒绝），绝不 stale-allow。';

-- ============================================================
-- 5. 支撑索引 —— 按 spec 仅在 PostgreSQL EXPLAIN 实证必要时 additive 增加。
--    本任务对 delegation-history 反查集查询形状先跑 EXPLAIN (ANALYZE, BUFFERS)：
--    空表/低基数下规划器选顺序扫描，索引不被采用，故本迁移不预置二级支撑索引；
--    可见性支撑索引由 Task 5/15 在具备代表性数据后经 EXPLAIN 证明计划改善再 additive 增加。
--    （PK 及 FK 目标列的唯一性由上面约束保证。）
