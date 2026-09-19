-- V133: attachment_working_paper (attachment_id, wp_id) 唯一索引 —— 支撑幂等关联 upsert
-- spec: attachment-workpaper-linkage-convergence (Wave 0 / Task 1.2)
--
-- 背景：associate_with_wp 历史无去重，每次调用都 INSERT 一行新 link；process-record
-- linkAttachment 将在 Wave 1 双写权威链表（attachment_working_paper）。为支撑幂等
-- upsert（ensure_wp_link）并防并发竞态产生重复 (attachment_id, wp_id) 行，建唯一索引
-- 作 DB 级防御（应用层 ensure_wp_link 先查后插为主防线，本索引为并发兜底）。
--
-- 幂等/可重跑：先删除存量重复 (attachment_id, wp_id) 行（保留每组最早 created_at 的一条，
-- 其次以最小 id 破平），再 CREATE UNIQUE INDEX IF NOT EXISTS。重跑时去重删 0 行 + 索引已存在跳过。
-- additive：无新表、无新业务列。

-- 1. 去重存量重复行（保留每组 (attachment_id, wp_id) 最早 created_at 的一条）
DELETE FROM attachment_working_paper
WHERE id IN (
    SELECT id FROM (
        SELECT id,
               ROW_NUMBER() OVER (
                   PARTITION BY attachment_id, wp_id
                   ORDER BY created_at ASC, id ASC
               ) AS rn
        FROM attachment_working_paper
    ) ranked
    WHERE ranked.rn > 1
);

-- 2. 建唯一索引（幂等）
CREATE UNIQUE INDEX IF NOT EXISTS uq_awp_attachment_wp
    ON attachment_working_paper (attachment_id, wp_id);
