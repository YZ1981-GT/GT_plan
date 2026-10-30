# 需求：AI 待确认列表的目标标签修复（ai-content-pending-target-label）

## 背景

`GET /api/projects/{project_id}/ai-content/pending` 给横幅 `AiContentPendingBanner` 返回待确认的 AI 内容，
`_enrich_target_labels` 本应给每条补「底稿名 / 附注章节标题」（`target_label`）。2026-10-21
`ai-chat-adopt-and-note-target-picker` 第二轮复盘 R6 把它标为已修，2026-10-30 同步复盘时复核：没修好。

## 现状事实（2026-10-30 现查）

| # | 事实 | 证据 |
|---|------|------|
| F1 | `target_cell` 由 `ai_content_log_service.create` 编码为 `{instance_type}:{instance_id}[:{位置}]`；共享库现有形态：`workpaper:<id>`、`workpaper:<id>:E5`、`note:<附注 id>`、`note:<附注 id>:正文第一段`、NULL | `create()` 源码；`ai_content_log` 现查 |
| F2 | 底稿标签查 `SELECT id, wp_name FROM working_paper`，`wp_name` 在 `wp_index` 上 ⇒ PG 上必报 UndefinedColumn | `WpIndex` 模型；PG 守卫 `test_raw_sql_unqualified_column_contract` 报「新增引用文件」 |
| F3 | 附注标签把 `target_cell` 末段当 `note_section` 去查，对 F1 的两种附注形态都不命中（第二段才是附注 id） | `_enrich_target_labels`；`host_context._locate_note` 的 `resource_id` |
| F4 | 两条查询放在同一个 `begin_nested` 里，任一失败则所有条目 `target_label=None` ⇒ 列表含底稿项时附注标签也没有 | 同上 |
| F5 | 两条查询用 f-string 拼 SQL，附注那条的值来自存储的 `target_cell` | 同上 |
| F6 | 共享库唯一一条待确认底稿项存的是 `wp_index.id`（`e24d6cf2…`，已删项目首汽租车_2025），不是 `working_paper.id` | 现查 |
| F7 | 唯一前端消费方 `AiContentPendingBanner.vue` 不显示 `target_label`，只显示来源类型和原始 `target_cell`（含 UUID） | 组件模板 |
| F8 | 现有用例都不断言 `target_label`（这是 R6 能标「已修」的原因） | `test_ai_content_router.py` / `test_ai_content_confirm_writeback.py` |

平台既有标签口径（`ai_chat/host_context.py` 的 `_label_workpaper` / `_label_note`）：底稿 `"{wp_code} {wp_name}"`、附注
`"{note_section} {section_title}"`。

## 需求

1. 底稿标签用平台口径：按 `target_cell` 第二段当 `working_paper.id`、经 `wp_index` 取编码与名称；没取到的再当 `wp_index.id`
   取一次（F6）。只取本项目的行。
2. 附注标签用平台口径：按 `target_cell` 第二段当 `disclosure_notes.id` 取。只取本项目的行。
3. 底稿、附注各自降级：一类查询失败只让该类标签为空，另一类照常；都不中止调用方事务。
4. 查询全部参数绑定，不拼 SQL；第二段不是 UUID 的条目不查、标签为空。
5. 每条返回补 `target_position`：`target_cell` 第二个冒号之后的原文（如 `E5`、`正文第一段`），没有则为空。
6. 横幅：有 `target_label` 时显示「来源类型 · 标签 · 位置」，不再显示原始 `target_cell`；没有标签时照旧显示原始
   `target_cell`。
7. 用例断言真实标签值（两种底稿 id、两种附注形态、混合列表、跨项目、单类失败、非 UUID）；PG 上有 `pg_only` 用例覆盖真实
   列名；PG 守卫 `test_raw_sql_unqualified_column_contract` 不再报 `ai_content.py`。

## 实施中补充的需求（同属 R6 未落地部分，2026-10-30 现查）

| # | 事实 | 证据 |
|---|------|------|
| F9 | 横幅用例「监听 `ai-content:adopted` 后重拉计数」自 10-21 起一直红：横幅没订阅，两个采纳实现（`usePlatformAiChat` / `useDocAiChat`）也从不发这个事件，`Events` 类型里也没有它 | `git log -S` 只有 6d6d093c8 加了用例；HEAD 版同一用例红 |
| F10 | 横幅里的 `copyContent` 没有任何按钮调用；后端对底稿类确认回「请在底稿页面复制到目标位置」，而确认后该条即移出列表 | 组件模板 |
| F11 | 裸 SQL 守卫的抽取正则只认字面 `sa.text(`，`import sqlalchemy as _sa` 后的 `_sa.text(` 整段不扫（现算 1 段：`_c24_import_export.py`）；`test_raw_sql_tables_are_known` 自 10-19 起把 `FROM json_populate_recordset(` 当幽灵表，一直红 | 现算探针；HEAD 上同一用例红 |

8. 采纳成功（两个实现）发 `ai-content:adopted`（带宿主项目），横幅挂载时订阅、卸载时取消，同项目才重拉。
9. 横幅每条卡片有「📋 复制」按钮，点了把该条原文写进剪贴板。
10. 裸 SQL 抽取认 `<标识符>[.<标识符>…].text(`；`FROM 名字(` 视为函数式表源不算表；两处都有自检用例。

