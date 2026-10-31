# 设计：AI 待确认列表的目标标签修复

## 后端（`backend/app/routers/ai_content.py`）

- `_parse_target(target_cell)`：`split(":", 2)` 拆成（类型、实例 id、位置）；位置是第二个冒号之后的全部原文（可再含冒号）。
  `_serialize` 用它给出 `instance_type`（与原来同值）和新增的 `target_position`（需求 5）。
- `_enrich_target_labels(db, project_id, items)`：
  - 收集第二段能解析成 UUID 的底稿 id、附注 id（需求 4）。
  - `_workpaper_labels`：`select(WorkingPaper.id, WpIndex.wp_code, WpIndex.wp_name).join(WpIndex, …)` 限定
    `WorkingPaper.project_id`；没取到的 id 再 `select(WpIndex.id, …)` 限定 `WpIndex.project_id`（需求 1）。
  - `_note_labels`：`select(DisclosureNote.id, note_section, section_title)` 限定 `DisclosureNote.project_id`（需求 2）。
  - `_lookup_labels`：每类一个 `begin_nested()`，失败记 warning 后该类返回空字典（需求 3）。
  - 标签文本 `f"{code} {name}".strip()`，与 `host_context._label_workpaper` / `_label_note` 同式。
  - 不过滤 `is_deleted`：目标删了仍显示原名，便于认出这段 AI 内容写给谁（写回仍只认未删除附注，不受影响）。
- `list_pending_ai_content` 把路径上的 `project_id` 传进去。
- 用 ORM 而非原生 SQL：`in_()` 展开为绑定参数；SQLite 里 UUID 存 32 位十六进制，原生 SQL 绑 `str(uuid)` 恒不命中，ORM 两边同一写法。

## 前端（`audit-platform/frontend/src/components/ai/AiContentPendingBanner.vue`）

- `PendingAiItem` 加 `target_label` / `target_position`。
- 卡片元信息：有 `target_label` ⇒ 来源类型后显示标签（`gt-aip-card__target`），有位置再显示 `<code>` 位置；无标签 ⇒ 原样
  `<code>{{ target_cell }}</code>`（需求 6）。

## 采纳事件与复制按钮（需求 8、9）

- `utils/eventBus.ts` 的 `Events` 加 `'ai-content:adopted': { projectId: string }`。
- `usePlatformAiChat.adoptContent` / `useDocAiChat.adoptContent`：`res.ok` 且宿主有项目时发事件，失败不发。
- 横幅 `onMounted` 订阅、`onBeforeUnmount` 取消；`payload.projectId === props.projectId` 才 `load()`。
- 卡片操作区加「📋 复制」（`copyContent(item)`，原有函数）。

## 裸 SQL 守卫（需求 10，`backend/tests/test_raw_sql_schema_contract.py`）

- `_extract_sql_strings` 正则 `sa\.text` 放宽为 `(?:[A-Za-z_]\w*\.)+text`（覆盖 `_sa.text` / `sa_mod.text` / `sqlalchemy.sql.text`）。
  现算放宽后只多扫到 1 段且无违规。
- 每段 SQL 的表名抽取拆成 `_table_refs_in_sql`：`FROM 名字` 后紧跟 `(` 视为函数式表源跳过（PG 表的列别名必须先写表别名）。
- 自检：`test_extract_sql_strings_recognizes_call_forms`、`test_table_refs_skip_function_sources_but_keep_tables`。

## 测试

| 文件 | 内容 |
|------|------|
| `backend/tests/test_ai_content_pending_labels.py` | SQLite + 真 ORM：working_paper id / wp_index id 两种底稿、附注两段 / 三段、混合列表、别的项目的 id 不取名、附注查询失败底稿标签照有、第二段非 UUID 不报错、`target_position`；经真实路由 |
| `backend/tests/test_ai_content_pending_labels_pg.py` | `pg_only`：回滚事务 + `TEMP TABLE … (LIKE public.x INCLUDING DEFAULTS)` 遮住正式表，真实列名下两类标签都取到 |
| `AiContentPendingBanner.spec.ts` | 有标签显示标签与位置、不显示原始 target_cell；无标签回退原始 target_cell；复制按钮；卸载后取消订阅 |
| `composables/__tests__/aiContentAdoptedEvent.spec.ts` | 两个采纳实现：成功发一次带项目、失败不发 |

变异（磁盘注入、逐字节恢复，均配阴性对照）：

| 变异 | 打红的用例 |
|------|-----------|
| 底稿查询改回原生 SQL 查 `working_paper.wp_name` | SQLite 混合列表 / 单类失败；PG 标签用例 |
| 两类合回同一保存点 | 单类失败用例（两个参数） |
| 附注按 `target_cell` 末段取 | SQLite 混合列表；PG 标签用例 |
| 去掉三处项目限定（各一条） | 跨项目条目；PG「别的项目看不到」 |
| 去掉 `wp_index.id` 兜底 | SQLite 混合列表；PG 标签用例 |
| 附注查询改成 f-string 拼 SQL | 动态 SQL AST 判据 |
| 横幅不显示标签 / 有标签仍显示原始 target_cell | 横幅两条标签用例 |
| 横幅不订阅 / 不取消订阅 / 不判项目 | 横幅采纳事件三条用例 |
| 去掉复制按钮 | 复制按钮用例 |
| 两个采纳实现各自不发事件 | `aiContentAdoptedEvent.spec.ts` 对应一条 |
| 裸 SQL 抽取退回只认 `sa.text` / 去掉或放宽函数表源规则 | 两条自检；`test_raw_sql_tables_are_known` |

变异时发现：别名写法 `from sqlalchemy import text as _t` 的 `_t(` 守卫不扫（现算全仓 0 处，未放宽，只在本 spec 的 AST 判据里认别名）。

## 范围外（登记，不改）

- `tsj_structured_output_service` 调 `wrap_ai_output_with_log` 不传 `user_id` ⇒ 五参不齐、从不写 `ai_content_log`
  （其注释「Task 4.1 同时写入以触发门禁」没生效）。
- `workpaper_ai_conclusion_draft_service` 拼好的 `target_cell` 局部变量没用上（传 `field_id`，经 `create()` 编码后格式碰巧一致）。
- 共享库 6 条 `target_cell` 为 NULL 的待确认记录（重药安徽，2026-07-16）来源未查。
- `ai-chat-adopt-and-note-target-picker` R1 / R3 的前端接线不在库：`ChatAdoptTargetDialog.vue` / `ChatNoteSaveDialog.vue` 由
  021a47269「收集并发会话未提交产物」入库，但没有任何组件挂载它们；前者 import 的 `AdoptTarget` 类型
  `usePlatformAiChat` 从未导出，`PlatformAiChatPanel.handleAdopt` 只调 `adoptContent(msg.id)`（不带 `source_host`）。
  （更正：上句之后曾写「`git log --all -S` 查不到任何提交有过这段接线」，不对 —— `git log -S` 默认不看合并提交，而 stash 提交是合并。实际：11 个已跟踪文件的改动 10-21 17:56 被收进 stash 112bfabec、17:57 pop 回来，18:15 被并发会话 `git checkout --force` 冲掉；完整改动仍在本地救援标签 `rescue/2026-10-21-1756-temp-for-push-reconcile`。）
  `ChatAdoptNoteTarget.spec.ts` 8 例因此在 HEAD 上一直红；要恢复需重做接线，另立 spec。
  （2026-10-31 结案：另立的是 `stash-1021-lost-changes-recovery`，没有重做接线 —— 直接从救援标签取回原改动并逐文件三方合并，
  12 个已跟踪文件已随本条所在提交入库；本条前三句「不在库 / 无挂载点 / `AdoptTarget` 未导出」自此不再成立。
  同时实测确认本 spec 要修的 `target_label` 现在真的有值：待确认弹窗与 `GET /api/projects/{pid}/ai-content/pending`
  对底稿项都返回「D2 应收账款审定表」。）

## 勘误（已归档 spec 不回填）

- `_archive/55-batch-2026-10-21/ai-chat-adopt-and-note-target-picker` design §6.6 R6「target_label 全 None ⇒ 修 key +
  savepoint 降级」：没修好，原因见本 spec 需求 F2~F8。
