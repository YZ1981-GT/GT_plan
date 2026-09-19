-- V156：guidance 发布生命周期（Task 6 / G0.5）
--
-- ═══ 为什么需要它（spec requirements 4.2 / 6.1–6.6 / 12.2 / 12.3）═══
--
-- guidance 域此前只有一套「静态 JSON + 加载期抽取」的链路：candidate 抽取出来的
-- 内容没有生命周期、没有 reviewer 留痕、没有 immutable 保证，也没有「项目级
-- supplement 与 canonical 分离版本」的模型。本迁移补齐四条表：
--
--   1. guidance_publication            发布主体（draft → reviewed → published）
--   2. guidance_publication_event      生命周期事件（actor/reviewer/diff/digests/reason）
--   3. project_guidance_supplement     项目级补充（独立版本，不写回 canonical）
--   4. guidance_exemption_record       有效豁免（独立 scope、approved_by、expires_at）
--
-- 🔴 关键约束（由服务端 enforcement，不由表结构保证）：
--   * published 后 content_json 冻结 —— 见 guidance_publication_service.py 的
--     _assert_mutable()；本表只保存状态，真正的 immutable gate 在服务层。
--   * actor ≠ reviewer —— 服务端 capability 复验，不靠客户端隐藏按钮。
--   * supplement 不得补齐 canonical 缺失段后推 complete —— 见
--     guidance_completion_guard.py 的 _canonical_section_presence。
--   * capability 前置 —— 见 _assert_can()；permission denied 走服务端 403。

-- ═══ 1. 发布主体 ═══
-- status 生命周期：draft → reviewed → published → withdrawn
-- superseded_at 与 withdrawn_at 二选一，同一行不会同时有值（由服务层保证）。

CREATE TABLE IF NOT EXISTS guidance_publication (
    id                 UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
    lineage_id         VARCHAR(128)  NOT NULL,
    version            VARCHAR(64)   NOT NULL,
    wp_code            VARCHAR(32)   NOT NULL,
    sheet_key          VARCHAR(128)  NOT NULL DEFAULT '*',
    status             VARCHAR(16)   NOT NULL DEFAULT 'draft'
                             CHECK (status IN ('draft', 'reviewed', 'published', 'withdrawn')),
    content_json       JSONB         NOT NULL DEFAULT '{}'::jsonb,
    source_refs_json   JSONB         NOT NULL DEFAULT '[]'::jsonb,
    content_digest     VARCHAR(64)   NOT NULL,
    source_digest      VARCHAR(64),
    schema_ref         VARCHAR(64),
    review_status      VARCHAR(16)   NOT NULL DEFAULT 'pending'
                             CHECK (review_status IN ('pending', 'approved', 'rejected')),
    author_user_id     UUID          NOT NULL,
    reviewer_user_id   UUID          NOT NULL,
    reviewed_at        TIMESTAMPTZ,
    published_at       TIMESTAMPTZ,
    withdrawn_at       TIMESTAMPTZ,
    withdrawn_reason   VARCHAR(256),
    superseded_by      UUID          REFERENCES guidance_publication(id) ON DELETE SET NULL,
    reason             VARCHAR(256),
    created_at         TIMESTAMPTZ   NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ   NOT NULL DEFAULT now()
);

COMMENT ON TABLE guidance_publication IS
    'guidance 发布主体：draft→reviewed→published 生命周期；published 后 content_json 冻结（immutable gate 在服务层，不由表约束）。';
COMMENT ON COLUMN guidance_publication.lineage_id IS
    '模板 lineage 标识（非 template_id、非 file name），用于跨版本绑定同一逻辑模板。';
COMMENT ON COLUMN guidance_publication.sheet_key IS
    'sheet 稳定键；"*" 表示整册（whole-workbook）口径。';
COMMENT ON COLUMN guidance_publication.content_digest IS
    'sha256(content_json) —— 与 source_digest 不同源；两者必须解耦（mutation C01 判据）。';
COMMENT ON COLUMN guidance_publication.source_digest IS
    '源材料 digest（xlsx/docx/bcd 抽取输入），与 content_digest 不得同源。';
COMMENT ON COLUMN guidance_publication.reviewer_user_id IS
    '必须 ≠ author_user_id —— 服务端 capability 复验，非仅 UI 隐藏。';
COMMENT ON COLUMN guidance_publication.superseded_by IS
    '被新版本取代时指向新版本行 id；NULL 表示当前有效版本。';

-- active 判定：未 supersede 且未 withdraw。同一 (lineage, version, wp, sheet)
-- 下至多一行 active（partial unique index）。
CREATE UNIQUE INDEX IF NOT EXISTS ux_guidance_publication_active
    ON guidance_publication (lineage_id, version, wp_code, sheet_key)
    WHERE superseded_by IS NULL AND withdrawn_at IS NULL;

CREATE INDEX IF NOT EXISTS ix_guidance_publication_status
    ON guidance_publication (status, wp_code);

-- ═══ 2. 生命周期事件 ═══
-- 每次状态迁移（draft→reviewed / reviewed→published / published→withdrawn /
-- published→superseded / withdrawn→restored）写一行；actor/reviewer/diff/digests/
-- reason 全留痕，供审计与 outbox 消费。

CREATE TABLE IF NOT EXISTS guidance_publication_event (
    id              UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
    publication_id  UUID          NOT NULL REFERENCES guidance_publication(id) ON DELETE CASCADE,
    event_type      VARCHAR(32)   NOT NULL
                          CHECK (event_type IN (
                              'drafted', 'submitted_for_review', 'review_approved',
                              'review_rejected', 'published', 'withdrawn',
                              'restored', 'superseded'
                          )),
    from_status     VARCHAR(16),
    to_status       VARCHAR(16),
    actor_user_id   UUID          NOT NULL,
    reviewer_user_id UUID,
    reason          VARCHAR(256),
    diff_json       JSONB         NOT NULL DEFAULT '{}'::jsonb,
    before_digest   VARCHAR(64),
    after_digest    VARCHAR(64),
    audit_ref       VARCHAR(128),
    outbox_ref      VARCHAR(128),
    created_at      TIMESTAMPTZ   NOT NULL DEFAULT now()
);

COMMENT ON TABLE guidance_publication_event IS
    'guidance 发布生命周期事件：状态迁移的 actor/reviewer/diff/digests/reason 全留痕，供审计与 outbox 消费。';
COMMENT ON COLUMN guidance_publication_event.diff_json IS
    'content_json 的差异（键级 patch，非全量快照），diff 是留痕，不是可重放指令。';
COMMENT ON COLUMN guidance_publication_event.before_digest IS
    '变更前的 content_digest；drafted 时 NULL。';
COMMENT ON COLUMN guidance_publication_event.after_digest IS
    '变更后的 content_digest；withdrawn/restored 时通常与 before 相同。';

CREATE INDEX IF NOT EXISTS ix_guidance_publication_event_pub
    ON guidance_publication_event (publication_id, created_at);

-- ═══ 3. 项目级 supplement ═══
-- 独立版本：不与 canonical publication 共享版本号；base_publication_id 只作
-- 「锚定基准」，supplement 内容不写回 canonical。runtime subject 三元组必须齐全
-- （project_id / entry_id / sheet_key），且 project_evidence 非空 —— 见
-- project_guidance_supplement_service.py 的 _assert_runtime_subject_bound()。

CREATE TABLE IF NOT EXISTS project_guidance_supplement (
    id                    UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id            UUID          NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    entry_id              VARCHAR(512)  NOT NULL,
    wp_code               VARCHAR(32)   NOT NULL,
    sheet_key             VARCHAR(128)  NOT NULL,
    supplement_version    VARCHAR(64)   NOT NULL,
    status                VARCHAR(16)   NOT NULL DEFAULT 'draft'
                                CHECK (status IN ('draft', 'reviewed', 'published')),
    content_json          JSONB         NOT NULL DEFAULT '{}'::jsonb,
    content_digest        VARCHAR(64)   NOT NULL,
    base_publication_id   UUID          REFERENCES guidance_publication(id) ON DELETE SET NULL,
    base_content_digest   VARCHAR(64),
    project_evidence_json JSONB         NOT NULL DEFAULT '[]'::jsonb,
    evidence_digest       VARCHAR(64)   NOT NULL,
    author_user_id        UUID          NOT NULL,
    reviewer_user_id      UUID          NOT NULL,
    reviewed_at           TIMESTAMPTZ,
    published_at          TIMESTAMPTZ,
    reason                VARCHAR(256),
    created_at            TIMESTAMPTZ   NOT NULL DEFAULT now(),
    updated_at            TIMESTAMPTZ   NOT NULL DEFAULT now()
);

COMMENT ON TABLE project_guidance_supplement IS
    '项目级 guidance 补充：独立版本号、独立生命周期；base_publication_id 仅作锚定基准，内容不写回 canonical。';
COMMENT ON COLUMN project_guidance_supplement.supplement_version IS
    'supplement 自有版本，与 base_publication.version 不同源；两版本变化各自触发 stale。';
COMMENT ON COLUMN project_guidance_supplement.project_evidence_json IS
    '绑定项目级证据（凭证号/函证编号/现场记录等），非空 —— 空 evidence 的 supplement 服务端拒绝。';
COMMENT ON COLUMN project_guidance_supplement.base_content_digest IS
    '锚定基准 publication 的 content_digest；base publication 变化时用于判定 stale。';

CREATE INDEX IF NOT EXISTS ix_project_guidance_supplement_subject
    ON project_guidance_supplement (project_id, entry_id, wp_code, sheet_key)
    WHERE status = 'published';

-- ═══ 4. 豁免记录 ═══
-- scope 三元组与 runtime key 对齐；expires_at 到期后不再 valid —— 见
-- guidance_exemption_service.py 的 _assert_expiry()。owner 与 approver 分离，
-- approver 不得等于 owner。

CREATE TABLE IF NOT EXISTS guidance_exemption_record (
    id                UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
    scope_type        VARCHAR(32)   NOT NULL
                            CHECK (scope_type IN ('project', 'entry', 'wp', 'sheet')),
    project_id        UUID          REFERENCES projects(id) ON DELETE CASCADE,
    entry_id          VARCHAR(512),
    wp_code           VARCHAR(32),
    sheet_key         VARCHAR(128),
    entry_ids_json    JSONB         NOT NULL DEFAULT '[]'::jsonb,
    reason            VARCHAR(256)  NOT NULL,
    owner_user_id     UUID          NOT NULL,
    approver_user_id  UUID          NOT NULL,
    approved_at       TIMESTAMPTZ   NOT NULL DEFAULT now(),
    expires_at        TIMESTAMPTZ   NOT NULL,
    source_digest     VARCHAR(64),
    revoked_at        TIMESTAMPTZ,
    created_at        TIMESTAMPTZ   NOT NULL DEFAULT now()
);

COMMENT ON TABLE guidance_exemption_record IS
    'guidance 有效豁免：独立 scope/owner/approver/reason/expires_at；approver ≠ owner，到期自动失效。';
COMMENT ON COLUMN guidance_exemption_record.scope_type IS
    '豁免粒度；project 级最宽，sheet 级最窄。entry_ids_json 用于同 scope 下的精确条目。';
COMMENT ON COLUMN guidance_exemption_record.expires_at IS
    '绝对到期时间；无 expires_at 视为永久豁免（服务端拒绝创建）。';
COMMENT ON COLUMN guidance_exemption_record.revoked_at IS
    '提前撤销时间；撤销后不再 valid，但保留留痕。';

CREATE INDEX IF NOT EXISTS ix_guidance_exemption_scope
    ON guidance_exemption_record (project_id, wp_code, sheet_key)
    WHERE revoked_at IS NULL;
