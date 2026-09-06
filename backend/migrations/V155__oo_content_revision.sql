-- V155：OnlyOffice 内容修订号
--
-- ═══ 为什么需要它（2026-09-06 浏览器实测抓出）═══
--
-- D2 双向回写把 756 行写进了 `{project}/workpapers/onlyoffice/D2-2.xlsx`（磁盘实测
-- 228,711 字节、756 业务行），但 OnlyOffice 里**仍显示空模板**。根因：doc_key 由
-- `(wp_id, entry_id, generation)` 派生，无 room 时恒取 `BASELINE_GENERATION=1`
-- ⇒ 文件重写后 doc_key 不变 ⇒ OO 按 key 命中自己的服务端缓存，不重新下载。
--
-- 🔴 不能改回「doc_key 含 mtime」：Task 21 / AC 2.7 / Property 6 明确禁止 ——
-- 那会让任何一次写盘都轮转 key、打断进行中的协同会话。
--
-- 本表提供的是**内容修订号**：只在服务端真的改写了受管内容时 +1。
-- 与 mtime 的区别正是判据所在 —— 同内容重复写盘不涨，内容变了才涨。
--
-- 语义：`(wp_id, entry_id)` → `revision`，doc_key 的 generation 取
-- `BASELINE_GENERATION + revision`（仅在无存活 room 时生效，不干扰在途会话）。

CREATE TABLE IF NOT EXISTS working_paper_oo_content_revision (
    wp_id       UUID        NOT NULL,
    entry_id    VARCHAR(512) NOT NULL,
    revision    BIGINT      NOT NULL DEFAULT 0,
    reason      VARCHAR(128),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (wp_id, entry_id)
);

COMMENT ON TABLE working_paper_oo_content_revision IS
    'OO 内容修订号：服务端改写受管内容时 +1，用于轮转 doc_key 使 OO 放弃缓存副本。与 mtime 不同——同内容重复写盘不涨。';
COMMENT ON COLUMN working_paper_oo_content_revision.entry_id IS
    'OO room 口径的 entry_id（sheet_entry_id 派生），不是 sync manifest 的 entry_id。';
COMMENT ON COLUMN working_paper_oo_content_revision.reason IS
    '最近一次推进的原因（如 d2_push_html_to_excel），便于追溯谁改了内容。';
