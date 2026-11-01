-- 附件输出溯源幂等身份：迁移前不静默删除重复行。
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM attachment_lineage
        WHERE project_id IS NOT NULL AND target_ref IS NOT NULL
        GROUP BY project_id, attachment_id, target_type,
                 COALESCE(target_id, '00000000-0000-0000-0000-000000000000'::uuid), target_ref
        HAVING COUNT(*) > 1
    ) THEN
        RAISE EXCEPTION 'attachment_lineage 存在重复身份，请先运行重复清册并人工裁决';
    END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS uq_attachment_lineage_identity
ON attachment_lineage (
    project_id,
    attachment_id,
    target_type,
    COALESCE(target_id, '00000000-0000-0000-0000-000000000000'::uuid),
    target_ref
)
WHERE project_id IS NOT NULL AND target_ref IS NOT NULL;
