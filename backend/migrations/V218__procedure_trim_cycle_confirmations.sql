-- V218：粗裁确认当前态投影（spec trim-generation-plan-followup-optimizations R3）
--   每项目每循环一行，记最近一次成功保存粗裁的来源预览凭证、操作人、时间、请求号、决定指纹与保存次数。
--   真源仍是已消费的 trim 预览凭证（procedure_operation_previews，不可变）；本表是派生投影。
--   原计划写在 V217 后半部分；V217 已在共享开发库按第一部分登记，故独立成本版本（不改已登记文件）。
-- 🔴 MigrationRunner 的分句器不识别单引号字符串：字符串里禁用 ASCII 分号与连字符注释符。

CREATE TABLE IF NOT EXISTS procedure_trim_cycle_confirmations (
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    audit_cycle VARCHAR(10) NOT NULL,
    source_preview_id UUID NOT NULL REFERENCES procedure_operation_previews(id) ON DELETE RESTRICT,
    confirmed_by UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    confirmed_at TIMESTAMPTZ NOT NULL,
    request_id VARCHAR(80) NOT NULL,
    cycle_revision_hash CHAR(64) NOT NULL,
    revision_no BIGINT NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (project_id, audit_cycle),
    CONSTRAINT ck_procedure_trim_cycle_confirmation_cycle CHECK (
        audit_cycle = upper(btrim(audit_cycle)) AND btrim(audit_cycle) <> ''
    ),
    CONSTRAINT uq_procedure_trim_cycle_confirmation_source UNIQUE (source_preview_id, audit_cycle),
    CONSTRAINT ck_procedure_trim_cycle_confirmation_revision CHECK (revision_no >= 1)
);

COMMENT ON TABLE procedure_trim_cycle_confirmations IS
    '每项目每循环最近一次成功保存粗裁的当前态（派生投影），真源是已消费的 trim 预览凭证。'
    '最新 = (confirmed_at, source_preview_id) 最大，revision_no = 含该循环的已消费预览数，'
    'cycle_revision_hash 与 app.services.procedure_trim_confirmation.cycle_revision_hash 同算法';

-- 回填：只从已消费 trim 预览的 scope 条目生成（不从旧方案 / 行历史猜测）。
-- 条目字段只认 JSON 字符串（损坏的旧 JSON 记空串），循环按 upper(btrim()) 归一，
-- 超过 10 个字符的循环不可能对应任何程序行（procedure_instances.audit_cycle 是 VARCHAR(10)），忽略。
WITH raw_entries AS (
    SELECT p.project_id,
           p.id AS preview_id,
           p.actor_user_id,
           p.consumed_at,
           COALESCE(p.consumed_request_id, 'legacy:' || p.id::text) AS request_id,
           upper(btrim(e.value->>'cycle')) AS audit_cycle,
           CASE WHEN jsonb_typeof(e.value->'wp_index_code') = 'string'
                THEN e.value->>'wp_index_code' ELSE '' END AS code,
           CASE WHEN jsonb_typeof(e.value->'target_status') = 'string'
                THEN e.value->>'target_status' ELSE '' END AS status,
           CASE WHEN jsonb_typeof(e.value->'skip_reason') = 'string'
                THEN e.value->>'skip_reason' ELSE '' END AS reason
    FROM procedure_operation_previews AS p
    CROSS JOIN LATERAL jsonb_array_elements(
        CASE WHEN jsonb_typeof(p.request_payload_snapshot->'entries') = 'array'
             THEN p.request_payload_snapshot->'entries' ELSE '[]'::jsonb END
    ) AS e(value)
    WHERE p.operation = 'trim'
      AND p.consumed_at IS NOT NULL
      AND jsonb_typeof(e.value) = 'object'
      AND e.value->>'kind' = 'scope'
      AND jsonb_typeof(e.value->'cycle') = 'string'
      AND btrim(e.value->>'cycle') <> ''
      AND length(btrim(e.value->>'cycle')) <= 10
),
per_preview AS (
    SELECT project_id, audit_cycle, preview_id, actor_user_id, consumed_at, request_id,
           encode(sha256(convert_to(
               jsonb_agg(
                   jsonb_build_array(code, status, reason)
                   ORDER BY code COLLATE "C", status COLLATE "C", reason COLLATE "C"
               )::text,
               'UTF8'
           )), 'hex') AS cycle_revision_hash
    FROM raw_entries
    GROUP BY project_id, audit_cycle, preview_id, actor_user_id, consumed_at, request_id
),
ranked AS (
    SELECT per_preview.*,
           row_number() OVER (
               PARTITION BY project_id, audit_cycle
               ORDER BY consumed_at DESC, preview_id DESC
           ) AS rn,
           count(*) OVER (PARTITION BY project_id, audit_cycle) AS revision_no
    FROM per_preview
)
INSERT INTO procedure_trim_cycle_confirmations (
    project_id, audit_cycle, source_preview_id, confirmed_by, confirmed_at,
    request_id, cycle_revision_hash, revision_no
)
SELECT project_id, audit_cycle, preview_id, actor_user_id, consumed_at,
       request_id, cycle_revision_hash, revision_no
FROM ranked
WHERE rn = 1
ON CONFLICT (project_id, audit_cycle) DO NOTHING;

-- 回填自检（另一种写法：DISTINCT ON）：投影必须与已消费预览逐项目逐循环一致，否则整份迁移回滚（fail-closed）。
DO $$
DECLARE
    mismatch_count integer;
BEGIN
    WITH scope_previews AS (
        SELECT DISTINCT p.project_id,
               upper(btrim(e.value->>'cycle')) AS audit_cycle,
               p.id AS preview_id,
               p.actor_user_id,
               p.consumed_at,
               COALESCE(p.consumed_request_id, 'legacy:' || p.id::text)::text AS request_id
        FROM procedure_operation_previews AS p
        CROSS JOIN LATERAL jsonb_array_elements(
            CASE WHEN jsonb_typeof(p.request_payload_snapshot->'entries') = 'array'
                 THEN p.request_payload_snapshot->'entries' ELSE '[]'::jsonb END
        ) AS e(value)
        WHERE p.operation = 'trim'
          AND p.consumed_at IS NOT NULL
          AND jsonb_typeof(e.value) = 'object'
          AND e.value->>'kind' = 'scope'
          AND jsonb_typeof(e.value->'cycle') = 'string'
          AND btrim(e.value->>'cycle') <> ''
          AND length(btrim(e.value->>'cycle')) <= 10
    ),
    expected AS (
        SELECT DISTINCT ON (project_id, audit_cycle)
               project_id, audit_cycle, preview_id, actor_user_id, consumed_at, request_id,
               count(*) OVER (PARTITION BY project_id, audit_cycle) AS revision_no
        FROM scope_previews
        ORDER BY project_id, audit_cycle, consumed_at DESC, preview_id DESC
    ),
    actual AS (
        SELECT project_id, audit_cycle::text, source_preview_id, confirmed_by, confirmed_at,
               request_id::text, revision_no
        FROM procedure_trim_cycle_confirmations
    )
    SELECT count(*) INTO mismatch_count
    FROM (
        (SELECT * FROM expected EXCEPT SELECT * FROM actual)
        UNION ALL
        (SELECT * FROM actual EXCEPT SELECT * FROM expected)
    ) AS diff;
    IF mismatch_count > 0 THEN
        RAISE EXCEPTION 'V218: % trim cycle confirmation rows differ from consumed previews', mismatch_count;
    END IF;
END
$$;
