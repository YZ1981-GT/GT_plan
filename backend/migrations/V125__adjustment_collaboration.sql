-- V125: 调整分录协作接力（adjustment-collaboration-and-propagation）
-- 在集中登记 adjustments/adjustment_entry 之上，以 entry_group_id 为锚点建立
-- 「转派→知晓→补充明细行→确认→回写推送」多人协作工作流。
--   adjustment_collaboration        — 协作记录（可变状态 + 多轮 round）
--   adjustment_collaboration_event  — append-only 协作历史（仅 INSERT）
-- 幂等：CREATE TABLE / INDEX IF NOT EXISTS。additive，不改动既有表。
-- 协作是受控多人编辑通道：origin='workpaper' 组活跃协作期间锁定 sync_from_workpaper 防覆盖。

-- ── 协作记录表 ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS adjustment_collaboration (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id       UUID NOT NULL REFERENCES projects(id),
    year             INTEGER NOT NULL,
    entry_group_id   UUID NOT NULL,                 -- 锚点：集中登记分录组
    source_ref       VARCHAR(120),                  -- workpaper-origin 组溯源键（协作锁判定）
    initiator_id     UUID NOT NULL REFERENCES users(id),
    assignee_id      UUID NOT NULL REFERENCES users(id),
    status           VARCHAR(20) NOT NULL DEFAULT 'pending',
                     -- pending/acknowledged/contributed/confirmed/closed/rejected
    round            INTEGER NOT NULL DEFAULT 1,    -- 协作轮次（多轮再推）
    note             TEXT,                          -- 转派说明
    rejection_reason TEXT,                          -- 退回原因
    is_deleted       BOOLEAN NOT NULL DEFAULT false,
    deleted_at       TIMESTAMPTZ,
    created_by       UUID REFERENCES users(id),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_adj_collab_project_group
    ON adjustment_collaboration(project_id, entry_group_id)
    WHERE is_deleted = false;

CREATE INDEX IF NOT EXISTS idx_adj_collab_assignee_status
    ON adjustment_collaboration(assignee_id, status)
    WHERE is_deleted = false;

CREATE INDEX IF NOT EXISTS idx_adj_collab_project_status
    ON adjustment_collaboration(project_id, status)
    WHERE is_deleted = false;

-- ── append-only 协作历史 ─────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS adjustment_collaboration_event (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    collaboration_id UUID NOT NULL REFERENCES adjustment_collaboration(id),
    actor_id         UUID NOT NULL REFERENCES users(id),
    event_type       VARCHAR(20) NOT NULL,
                     -- assigned/reassigned/acknowledged/contributed/confirmed/rejected/commented/closed
    payload          JSONB,                         -- 补充明细行 diff / note / round 快照
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_adj_collab_event_collab_time
    ON adjustment_collaboration_event(collaboration_id, created_at);
