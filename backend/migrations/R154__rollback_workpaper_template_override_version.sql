-- R154: 回滚 V154（Excel 模板覆盖层版本表）
--
-- Spec: excel-template-override-layer-and-onlyoffice-template-editor / Wave 3 Task 10
--
-- ⚠️ 回滚会丢弃（整表 DROP）：全部模板覆盖版本记录 —— 谁在何时把哪份模板改成了什么、
--    父版本链、当前版本指向，全部消失。
--
-- ⚠️ **覆盖层物理文件不会被删除**：DROP 表后
--    `backend/storage/template_overrides/{scope}/{wp_code}/{stem}/` 下的
--    `current{ext}` 与 `versions/` 仍在磁盘上。
--
--    后果比"留下孤儿文件"更具体：`wp_template_override.resolve_template()` 的解析判据是
--    **文件系统**（`current{ext}` 是否存在），不查本表 —— 所以回滚 DB **不会**让解析回落到
--    权威目录，覆盖仍然生效，只是失去了版本元数据与回滚能力。
--
--    ⇒ 若回滚意图是"彻底撤掉覆盖层"，必须**先**清理文件再 DROP 表：
--       1. 导出清单：SELECT wp_code, authoritative_stem, scope, project_id, group_id,
--                           file_relpath, sha256, is_current FROM workpaper_template_override_version;
--       2. 删除 OVERRIDE_ROOT 下对应的 current{ext}（解析立即回落权威目录）；
--       3. 再执行本脚本。
--    顺序颠倒会留下"生效但无台账"的覆盖，审计师看到的是改过的模板而系统说不出它来自哪里。

-- ── 1. 触发器（表存在时才有意义，DROP 表会带走触发器，但函数需单独回收） ──────
DROP TRIGGER IF EXISTS trg_wptov_parent_same_scope ON workpaper_template_override_version;
DROP TRIGGER IF EXISTS trg_wptov_forbid_delete ON workpaper_template_override_version;
DROP TRIGGER IF EXISTS trg_wptov_immutable ON workpaper_template_override_version;

-- ── 2. 表（含其上的部分唯一索引与全部 CHECK） ────────────────────────────────
--
-- 🔴 表上有 BEFORE DELETE 触发器禁止行删除，但 DROP TABLE 是 DDL，不触发行级触发器
--    ⇒ 无需先摘触发器即可 DROP。上面先摘是为了让"函数已无引用"这件事显式。
DROP TABLE IF EXISTS workpaper_template_override_version CASCADE;

-- ── 3. 触发器函数 ────────────────────────────────────────────────────────────
DROP FUNCTION IF EXISTS wptov_check_parent_same_scope() CASCADE;
DROP FUNCTION IF EXISTS wptov_forbid_delete() CASCADE;
DROP FUNCTION IF EXISTS wptov_check_immutable() CASCADE;

-- ⚠️ **不 DROP `wpsync_is_digest()`**：它是 V151 建立的 digest 单一真源，V154 只是复用。
--    在这里删掉会连带打断 V151 建的十几个 CHECK 约束（ck_wpa_sha256 / ck_wpsda_sha256 …）。
