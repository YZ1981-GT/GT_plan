-- V164: 未更正错报 durable 幂等键（source_identity）
--
-- 背景（B3 · spec d4-inspection/cutoff-writeback-formula-io，真栈实测印证）：
--   底稿"推送错报至 A13"经 useA13MisstatementBridge → createMisstatement 落库，
--   去重此前仅靠前端内存 Map（recentHashes，窗口 5000ms），跨窗口/刷新/长间隔失效
--   —— 真栈实测：同一差异两次点击（间隔 48s > 5s 窗口）产生 2 条重复错报。
--   本迁移把去重升级为**服务端 durable 幂等**：同一来源身份（source_identity）在
--   同项目下只落一条，重复推送返回既有记录（不新增），跨会话/刷新永久生效。
--
-- source_identity 语义：来源底稿维度的稳定身份串，由推送端按
--   {wpCode}|{description}|{amount}|{accountCode}|{misstatementType} 组装（与前端 draftHash 同字段），
--   为空时不参与幂等（兼容手工新建错报、AJE 转错报等既有路径）。
--
-- 幂等：ADD COLUMN IF NOT EXISTS + 部分唯一索引 IF NOT EXISTS；重复执行安全。
-- 可回滚：见 R164。

ALTER TABLE unadjusted_misstatements
    ADD COLUMN IF NOT EXISTS source_identity VARCHAR(200);

COMMENT ON COLUMN unadjusted_misstatements.source_identity IS
    'B3 durable 幂等键：底稿推送错报的来源身份串（wpCode|desc|amount|account|type）；同项目下唯一（软删除除外），重复推送不新增';

-- 部分唯一索引：同项目 + 同 source_identity 只允许一条未软删除记录。
-- WHERE 排除 NULL（手工/AJE 路径不受约束）与已软删除（删后可重推）。
CREATE UNIQUE INDEX IF NOT EXISTS uq_misstatement_source_identity
    ON unadjusted_misstatements (project_id, source_identity)
    WHERE source_identity IS NOT NULL AND is_deleted = false;
