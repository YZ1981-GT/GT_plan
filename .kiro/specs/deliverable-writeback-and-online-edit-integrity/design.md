# 设计：交付件回填 / 在线编辑保存 / 签发清单完整性

## 0. 现状 grep 确认（2026-10-17，HEAD = bae191382）

| 项 | 位置 | 现状 | 证据 |
|---|---|---|---|
| 签发清单 SQL | `services/signoff_checklist_service.py` | 9 条 `text()`，8 条引用不存在的列 / 表 / 枚举值；共用会话无 SAVEPOINT | information_schema / pg_enum 现查；`cross_module_conflicts` 0 行、`ai_content` pending 257 行 |
| 签发清单鉴权 | `routers/signoff_checklist.py` | `get_current_user`；年度回落 `now().year-1` | 源码 |
| 可复用权威实现 | `stale_summary_aggregate.get_full_summary`、`conflict_resolution_service.count_pending/list_pending`、`TrialBalanceService.check_consistency`、`gate_rules_cross_module_conflict` | 列名与真库一致（现查） | — |
| 报表行常驻过期 | `financial_report` BS-042 / BS-053 | 7 个项目各 2 行 is_stale=true（report_engine 只清本次重算到的行，配置外历史行不清） | 现查；本 spec 只把它作为 warning 呈现，不修报表引擎（§10） |
| 回填路由 | `routers/deliverable_lineage.py::writeback_deliverable` | 无 commit；>100 节转 `_delegate_to_async_job`，`create_job(params=)` 签名不符 | 源码；同文件 refresh-* 已在上一 spec 删异步并补 commit |
| 回填提取 | `deliverable_writeback_service._extract_sections_from_docx` | 块内段落全拼；`resolve_section_blocks(doc)` 不传 known_codes | 源码 |
| 回填冲突 | `_detect_conflict` | 比 `source_snapshot_hash`（含 TB 金额）；`last_writeback_baseline_hash` 读了不用 | 源码 |
| 回填护栏 | `_classify_change` | 块内有数字表即判 TABLE，不看改动 | 源码 |
| 附注写入 | `writeback_target_adapters.DisclosureNoteAdapter.write_upstream` | 只写 text_content | 源码；盖章口径见 `note_edit_stamp.py`（已入库 f9aef98c8） |
| 正文渲染 | `note_template_block_fill.rebuild_block → _Rebuilt.text_elements`；`note_template_export_fill` 汇总后 `rewrite_cross_refs(text_elements, display)` | 生成时已知道哪些元素来自库内正文 | 源码 |
| 交付过滤 | `note_deliverable_filter.filter_note_blocks` | 按行删 / 截断 / 清理，依赖标题与模板结构标题（`extra_titles` / `structure_titles`）与 `has_structured_tables` | 源码 |
| 正文存储形态 | `disclosure_notes.text_content` | 非空 1044：纯文字无标记 687、markdown 表格 203、HTML 15、含【 189 | 现查 |
| OO 回调 | `onlyoffice_callback_service.handle_callback` | 只认 status 2；不比 key；不幂等；编辑人只查 ProjectUser | 源码；v15 `edited_by` NULL、admin 不在 project_users |
| 席位释放 | `routers/deliverable.py::onlyoffice_callback` | status 2/4/**6** 释放 | 源码；6 = 仍在编辑（[OnlyOffice 回调说明](https://api.onlyoffice.com/docs/docs-api/usage-api/callback-handler/)） |
| OO 编号 | v15 `numbering.xml` | 90 处 `<w:isLgl w:val="false" />`，v14 无 | 探针；LibreOffice 转文本 v15 原样「7、」、剥除后「七、」、v14「七、」 |
| 版本文件名 | `render_and_store(file_name=...)` 调用 9 处 | 5 处固定名（附注 / 报表 × 路由 + 全套生成） | 源码；真库 19 版本共用 3 文件、16 版本指纹不符 |
| 版本号分配 | `create_version` | `max+1` 无锁；无唯一索引 | `pg_indexes` 现查；当前无重复 |
| 下载 | `download_version` / `signed_download_version` | 不校验指纹（打包下载有） | 源码 |
| 列契约 | `tests/test_raw_sql_column_contract.py` | 只查 `alias.col` | 源码 |
| quality_score | `wp_quality_score_linkage.py` / `wp_quality_score_service.py` / `wp_health_dashboard.py` | 读写 `working_paper.quality_score / procedure_completion_rate`，ORM 与迁移均无 | 现查 |
| 溯源面板 | `LineagePanel.vue` | `/section-states` 为空即提示「请重新生成」 | 源码；financial_report 任务 0 行章节状态 |
| 迁移最高号 | `backend/migrations` | V188 → 实际并发会话已推进至 V190 | 本 spec 原定 V189，并发会话（trio）已占用 V189/V190 ⇒ **2026-10-18 改号至 V191** |

## 1. 签发一致性清单（US-1）

### 1.1 检查执行框架
```python
async def _run_check(self, name, label, fn) -> list[CheckItem]:
    try:
        async with self.db.begin_nested():      # 每项独立 SAVEPOINT：失败只回滚本项
            return await fn()
    except Exception as exc:                    # fail-closed：执行失败 = 无法确认 = 阻断
        logger.warning(...)
        return [CheckItem(severity=blocking, category=name,
                          message=f"{label}检查执行失败，无法确认一致性（{type(exc).__name__}）", route=None)]
```
`generate_checklist` 顺序跑六项；`can_signoff = 无 blocking`。删除原「暂不可用 → info」降级。

### 1.2 六项检查（只用真实 schema / 既有权威实现）
| category | 判据 | 级别 | route |
|---|---|---|---|
| `trial_balance` | `TrialBalanceService.check_consistency(project_id, year)` 返回的审定数公式不一致科目 | blocking（列前 5 + 计数） | `/projects/{pid}/trial-balance` |
| `adjustment` | `adjustments` 中 `review_status IN ('draft','pending_review') AND is_deleted = false` | blocking | `/projects/{pid}/adjustments` |
| `conflict` | `conflict_resolution_service.count_pending / list_pending(limit=5)`（与 `gate_rules_cross_module_conflict` 同口径） | blocking | 无页面 ⇒ `null` |
| `report` | `audit_report`（project, year, 未删除）：无记录 blocking；`is_stale` warning；否则 info「意见类型：…」（中文标签） | — | `/projects/{pid}/audit-report` |
| `stale` | `get_full_summary`：底稿 `stale + inconsistent`、报表行 `stale`、附注 `stale` 各一条 warning（附前 5 项名称） | warning | 底稿 `/workpapers`、报表 `/reports`、附注 `/disclosure-notes` |
| `ai_content` | `ai_content.confirmation_status = 'pending'`（未删除）+ `ai_content_governance.lifecycle_status IN ('draft','revised','stale')`（audit_year = year） | strict ⇒ blocking，否则 warning | 有底稿 id ⇒ `/projects/{pid}/workpapers/{wp}/edit`，否则 `null` |

- 报表行常驻过期（BS-042/053）因此表现为一条需确认的 warning，不阻断签发；根因（报表引擎不清配置外历史行）登记 §10。
- 「试算表 stale」原口径不存在（试算表无过期状态，审批调整分录即同步重算）；以「审定数 = 未审 + RJE + AJE + 底稿调整」不变式替代。
- 前端 `CATEGORY_LABELS` 补 `conflict: 跨模块冲突`、`stale: 数据过期`。

### 1.3 路由
- `current_user = Depends(require_project_access("readonly"))`；`confirm-warning` 同样（写审计日志的端点按 readonly：只有能看清单的人能确认）。
- 年度：query 优先 → `fetch_project_audit_year` → 取不到 422「无法确定审计年度」。
- 前端 `PartnerSignDecision` 给 `SignoffChecklist` 传 `:year="year"`。

### 1.4 守卫
- `test_signoff_checklist_service.py` 改为真 SQLite + 真 ORM 行（不再 mock execute）：每项正反例；注入某项失败 ⇒ 该项 blocking 且其余项照常；
  `can_signoff` 只在全部通过时为 true。
- pg_only：真库对四个真实项目各跑一次（事务回滚），断言无「执行失败」项（= SQL 全部对真实 schema 有效）。
- 变异：去掉 SAVEPOINT ⇒「一项失败其余照常」用例打红；把 `except` 改回 info ⇒ fail-closed 用例打红。

## 2. 版本文件完整性（US-6）

### 2.1 `render_and_store` 内收口（调用方零改动即生效）
1. 先锁任务行：`SELECT ... FROM word_export_task WHERE id = :tid FOR UPDATE`（SQLite 方言忽略 `with_for_update`）。同一交付物的
   「取最大版本号 → 落盘 → 建版本」整段串行；锁随请求事务提交释放。
2. 物理文件名 = `versioned_file_name(file_name, doc_type, next_no)`：给了 `file_name` 取其主名与后缀，主名已以 `_v{next_no}`
   结尾则不重复追加；没给按 `{doc_type}_v{next_no}.docx`（保持原默认）。纯函数，单测覆盖 9 个调用点的实参形态。
3. 建版本前若目标文件已存在且被其他版本记录引用 ⇒ 抛 `FileFingerprintError`（不覆盖、不建版本）。正常情况下文件名含版本号，
   只会在锁失效等异常下触发。
4. `create_version` 继续用 `max+1`；V191 加唯一索引 `uq_word_export_versions_task_no (word_export_task_id, version_no)` 兜底。

调用方 `file_name` 语义不变（仍是「展示名主体」），返回值 `StoreResult.file_path` 是带版本号的真实路径；路由回执里的
`file_name` 改为取真实文件名（下载名与磁盘一致）。

### 2.2 下载指纹校验
`download_version` 与 `signed_download_version` 在 `FileResponse` 前调 `verify_file_fingerprint(file_path, expected_size,
expected_sha256)`：
- `FileHashMismatch / FileSizeMismatch` ⇒ 409「该版本文件已被后续生成覆盖（历史缺陷），无法提供原始内容；请下载最新版本」；
- 文件缺失 ⇒ 维持 404；`file_hash` 为空的极老版本 ⇒ 只校验大小（不能比就不比，但不放过可比的）。
OO 签名下载被拒时 Document Server 打不开该版本，符合预期（打开的本来就不是那一版的内容）。

### 2.3 `verify_version_immutability`
改为：版本存在 且 `verify_file_fingerprint` 通过 ⇒ True；否则 False。两条既有单测改用真实临时文件。

### 2.4 守卫
- 单测：连续两次生成后两版文件路径不同、两版下载内容各自等于生成时字节；固定名调用点逐个走一遍（附注 / 报表 / 未审报表）。
- 变异：`versioned_file_name` 退回原样 ⇒ 第二次生成覆盖第一版 ⇒ 下载用例打红（409）；去掉下载校验 ⇒ 历史版本下载拿到新内容打红。
- 真库（只读）：16 个指纹不符的历史版本经下载端点返回 409；3 个指纹相符的照常 200。

补：`versioned_file_name` 先剥掉主名末尾已有的 `_v\d+` 再追加本版号（`audit_report_v5` + 第 6 版 ⇒ `audit_report_v6`），
避免路由预渲染文件名与锁内版本号不一致时出现 `_v5_v6`。

## 3. 在线编辑保存（US-5）

### 3.1 回调处理顺序（`handle_callback`）
1. `status ∉ {2, 6}` ⇒ `{"error": 0}`（1 / 4 / 3 / 7 只做席位与日志）。
2. `key` 校验：`parse_deliverable_doc_key(body["key"])` 必须得到 `(task_id == 路径 task_id, base_no)`；否则写安全日志
   `onlyoffice_callback_rejected`（reason=「回调 key 与交付物不符」）并返回 `{"error": 1}`。缺 key 同样拒绝。
3. 下载 `url` 内容 → `normalize_oo_docx(bytes)`（§3.3）→ 计算 SHA-256。
4. 在任务行锁内（`render_and_store` 已加，§2.1）先比较最新版本 `file_hash`：相同 ⇒ 不建版本，返回 `{"error": 0}`（重试 / 关闭时
   与最后一次强制保存同内容）。
5. 陈旧底版判定：`foreign = [v for v in versions if v.version_no > base_no and not (v.created_via == 'onlyoffice_edit'
   and v.oo_doc_key == key)]`；非空 ⇒ 仍保存（不丢编辑），版本记 `base_version_no = base_no`、`oo_doc_key = key`，写审计日志
   `deliverable_oo_stale_base_save`（details: base、overwritten 版本号列表、编辑人），日志 warning。
6. `render_and_store(..., created_via="onlyoffice_edit", inherit_snapshot_refs=True, edited_by, edited_at,
   base_version_no, oo_doc_key)`；`render_context` 继承底版（§4.2）。
7. 报表 drift 检测照旧。

强制保存（status 6）每次落一版；同一会话（同 key）后续保存不算陈旧。关闭时（status 2）内容与最后一次强制保存相同 ⇒ 第 4 步幂等。

### 3.2 编辑人
`_resolve_verified_editor`：`resolve_editor_id` 解析 → `users` 在册（未删除、`is_active`）→ `role == admin` 直接采信，否则须是
未删除的 `project_users` 成员（与 `assert_project_permission` 同口径：admin 免项目校验、其余查 project_users）。仍不回退创建人。

### 3.3 `normalize_oo_docx`
只改 `word/numbering.xml`：删除 `<w:isLgl w:val="false|0|off"/>`（ST_OnOff 假值与缺省等价，Word 渲染不变；LibreOffice 把显式 false
当开启 ⇒「七、」变「7、」）。其他部件逐字节不动；不是合法 zip 或无该部件 ⇒ 原样返回。只对 OO 回调入口调用（生成的文件不含
该写法）；已落库的 OO 版本不回改（会破坏其指纹）。

### 3.4 席位
路由释放条件改为 `status in (2, 3, 4)`（会话结束）；6 / 7 是会话中，保持占用。

### 3.5 版本链展示
`DeliverableVersionSchema` additive：`base_version_no`、`overwrote_versions: list[int]`（由版本链现算：本版 `base_version_no`
之后、本版之前、不属于本会话的版本号）。`DeliverableVersionList` 对 `overwrote_versions` 非空的版本显示警示标签
「基于第 N 版编辑，覆盖了第 M 版」，tooltip 说明「编辑期间有人刷新或重新生成，本版保存时以旧内容为底；请核对第 M 版的改动」。

### 3.6 守卫
- `test_deliverable_oo_edit_provenance.py` / `test_deliverable_onlyoffice.py` 扩：key 不符拒绝 + 安全日志；6 落版本；同内容幂等；
  会话内多次保存不算陈旧；他人刷新后保存标陈旧并留痕；admin 编辑人；非成员 None；席位 6 不释放。
- `normalize_oo_docx` 单测 + 用真 v15 副本的 LibreOffice 复验（pg_only 同级的 `libreoffice` 标记，可用时跑）。
- 变异：去掉 key 校验 / 去掉幂等 / 席位集合加回 6 / 去掉 isLgl 剥除，各自打红对应用例。

## 4. 附注回填下线 + 报告正文回填保留 + 导出前一致性闸门（US-2 / US-3 / US-4）

> 🔴 方向裁定（2026-10-17 用户确认）：附注唯一权威源 = 底稿披露表单项推送（底稿 → 附注），交付中心是附注的只读下游出口
> （附注 → 交付 docx）。原设计「交付 Word 改字回填附注」是逆流，整体下线。报告正文段落文字就在交付件里、不涉上游推送链，保留回填。
> 附注要改内容回底稿改；交付导出前加一致性确认闸门，列出附注与底稿不一致章节让用户确认或去同步。

### 4.1 附注回填下线
- `deliverable_capabilities`：`supports_writeback("disclosure_notes")` 置 **False**（从 `WRITEBACK_SUPPORTED_DOC_TYPES` 移除）；
  `audit_report` 保留。守卫 `test_deliverable_capabilities_matrix` 同步。
- `/writeback` 端点能力门控已有（`_require_capability`）：附注命中即 400「附注不支持从交付件回填，请回底稿修改后同步到附注」。
- 删除「> 100 节转异步」分支与 `_delegate_to_async_job`、`ASYNC_SECTION_THRESHOLD`（全仓无 worker，走到即 500）。
- `DeliverableWritebackService`：`_resolve_adapter` 对 `disclosure_notes` 不再返回 `DisclosureNoteAdapter`（返回 None ⇒ service 直接
  返回全空结果）；`DisclosureNoteAdapter.write_upstream` 保留类但标注 deprecated、不再被 `_resolve_adapter` 选中（避免误接）。
  **不动** `_classify_change` / `_extract_sections_from_docx` 等附注专用代码路径的删除面——只断开入口，减少回归面。
- 前端 `OnlyOfficeEditor`：`WritebackResultPanel` 的 `v-if="supportsWriteback"` 已按后端能力门控 ⇒ 附注自动不渲染回填面板，
  改为渲染说明「附注内容请回底稿编辑后同步到附注，交付件不支持回填」。报告正文仍渲染回填面板。

### 4.2 报告正文回填保留
- `audit_report` 回填路径不变（`ReportBodyAdapter` 写 `report_body_json.sections`，派生 / 模板固定段落拒绝）。
- 路由成功后 `await db.commit()`（修 `get_db` 不自动提交的历史缺陷）；回执按「已回填 / 已拒绝 / 未回填」分组。
- 报告正文不触发 `NOTE_SECTION_SAVED`（那是附注事件）；无跨模块联动。

### 4.3 导出前一致性确认闸门（附注）
数据源复用 `note_readiness_service.build_readiness`（不新造判定）：
- `needs_sync=True`：有对应底稿披露表（`note_workpaper_sync_registry`）但 `last_sync_at` 为空 ⇒ 从未同步；
- `is_stale=True`：上游变更后标记过期未刷新。

新服务 `deliverable_note_consistency.check_note_consistency(db, project_id, year, selected_sections) -> dict`：
```
{"consistent": bool,
 "never_synced": [{"note_section", "section_title", "wp_codes", "wp_ids", "wp_sheet"}...],
 "stale": [{"note_section", "section_title"}...]}
```
`selected_sections` 非空时只看选中章节。查询异常 ⇒ fail-open 返回 `consistent=True`（看板故障不阻断已完成的编制）。

端点 `render_disclosure_notes`（`POST /disclosure-notes/render`）请求体 additive `confirm_inconsistent: bool = False`：
1. 导出前调 `check_note_consistency`；`consistent=True` 或 `confirm_inconsistent=True` ⇒ 照常导出，响应 additive
   `consistency={"confirmed": bool, "never_synced": [...], "stale": [...]}`（已确认或本就一致）。
2. `consistent=False` 且未确认 ⇒ **不落交付件**，返回 `DeliverableExportResponse` 变体 `requires_confirmation=true` + `consistency` 清单
   （HTTP 200，前端据此弹确认框，不用 409 以便前端拿到结构化清单）。
3. 全套生成 `full_deliverables_executor._run_disclosure_notes` 一键流程：一致性不一致时在结果里标记该步 `needs_confirmation`，
   不阻断其余步骤（一键生成是批处理，逐项提示在交付中心列表侧呈现；不在批处理里弹窗）。

报告正文 / 财务报表导出端点不接此闸门。

### 4.4 前端
- `DisclosureNotesSelectionDialog` / 交付中心「生成附注」动作：先发 `confirm_inconsistent=false` 的导出请求；响应
  `requires_confirmation` 时弹 `ElMessageBox`（全中文）：标题「附注与底稿可能不一致」，正文列出 `never_synced`（章节号 + 名称 +
  「有底稿披露表但从未同步」）与 `stale`（「上游已变更，附注未刷新」）；按钮「返回同步」（关闭，可带跳转）/「仍要导出」
  （再发 `confirm_inconsistent=true`）。
- `WritebackResultPanel` 对附注交付件（`supportsWriteback=false`）显示只读说明，不再出现回填按钮。

### 4.5 守卫
- `test_deliverable_note_consistency.py`（真 SQLite + 真 ORM）：某章从未同步 ⇒ `needs_synced` 命中、`consistent=False`；
  某章 `is_stale` ⇒ `stale` 命中；全部已同步且非 stale ⇒ `consistent=True`；`selected_sections` 过滤只看选中；查询异常 fail-open。
- 端点级（TestClient）：不一致且未确认 ⇒ `requires_confirmation=true` 且**不新建版本**；带 `confirm_inconsistent=true` ⇒ 落版本；
  一致 ⇒ 直接落版本。
- 能力矩阵：`supports_writeback("disclosure_notes") is False` / `("audit_report") is True`；`/writeback` 对附注返回 400。
- 前端 vitest：附注交付件不渲染回填按钮、渲染只读说明；导出响应 `requires_confirmation` 时弹确认框并能「仍要导出」。
- 变异：一致性闸门短路（恒 `consistent=True`）⇒ 「不一致不建版本」用例打红；附注 `supports_writeback` 改回 True ⇒ 能力矩阵打红。

## 5. 迁移 V191（+ R191）
> 原定 V189，因并发会话（trio spec）已占用 V189（share_change_event）/ V190（orm_drift）⇒ 2026-10-18 改号至 V191。所操作的表（word_export_task_versions / deliverable_section_state / working_paper）与 V189/V190 完全不相交。
```sql
ALTER TABLE word_export_task_versions ADD COLUMN IF NOT EXISTS base_version_no INTEGER;
ALTER TABLE word_export_task_versions ADD COLUMN IF NOT EXISTS oo_doc_key VARCHAR(160);
ALTER TABLE word_export_task_versions ADD COLUMN IF NOT EXISTS render_context JSONB;
CREATE UNIQUE INDEX IF NOT EXISTS uq_word_export_versions_task_no ON word_export_task_versions (word_export_task_id, version_no);
ALTER TABLE deliverable_section_state ADD COLUMN IF NOT EXISTS text_baseline TEXT;
ALTER TABLE deliverable_section_state ADD COLUMN IF NOT EXISTS text_source_hash VARCHAR(64);
ALTER TABLE deliverable_section_state ADD COLUMN IF NOT EXISTS outside_hash VARCHAR(64);
ALTER TABLE deliverable_section_state ADD COLUMN IF NOT EXISTS text_render_context JSONB;
ALTER TABLE working_paper ADD COLUMN IF NOT EXISTS quality_score INTEGER;
ALTER TABLE working_paper ADD COLUMN IF NOT EXISTS procedure_completion_rate NUMERIC(5,2);
```
R191 逆序 `DROP ... IF EXISTS`。ORM 同步 `Mapped[]`（三层一致）。开发服务器热重载不跑迁移：落库后全量重启 start-dev 或手动
`MigrationRunner.run_pending()`，并用 drift detector 复核 critical=0。

## 6. 裸 SQL 无限定列契约（US-7）
- 新守卫 `tests/test_raw_sql_unqualified_column_contract.py`（pg_only）：复用 `_iter_python_files` / `_extract_sql_strings`；sqlglot 解析，
  对每个 SELECT / UPDATE / DELETE / INSERT 作用域：只有一张实体表、无子查询 / CTE / 同名输出别名歧义时，校验无限定列 ∈ 该表真实列；
  `INSERT INTO t (cols)` 的列、`UPDATE t SET col` 的列同样校验；表名 ∉ 真库 ⇒ 记「幽灵表」。排除：SELECT 列表别名、函数名、`:param`、
  `EXCLUDED.*`、PG 伪列 / 系统列。
- 基线 `_UNQUALIFIED_BASELINE: dict[str, set[str]]`（列键 → 引用文件），断言：现算违规 ⊆ 基线（新增即红）；基线每条仍真实出现（修复后必删）。
- 高影响修复（实施时重算后逐条核对调用链，标出活路径 / 死代码）：活路径的改列名或补迁移；死代码保留在基线并在 §10 登记。

## 7. 溯源能力标志（US-8）
`deliverable_capabilities.LINEAGE_SUPPORTED_DOC_TYPES = {disclosure_notes, audit_report}` + `supports_lineage()`；`DeliverableDTO /
DeliverableDTOSchema` additive `supports_lineage`；`DeliverableCenter → OnlyOfficeEditor → LineagePanel` 透传。`supports_lineage = false`
时面板只显示「财务报表按报表行取数，没有章节溯源；数字来源请在「财务报表」页穿透查看」，不请求 `/section-states`。
`test_deliverable_capabilities_matrix.py` 与 `deliverableCapabilityGating.spec.ts` 同步扩第三个标志。

## 8. 验证计划
- 后端：本 spec 新增 / 改动测试 + 既有交付中心、回填、OO、指纹、能力、列 / 表契约、鉴权基线全量回归；HEAD 干净检出（临时 worktree）复跑守卫。
- 真库（事务回滚、不落库）：四个真实项目签发清单无「执行失败」；安徽附注导出前一致性闸门列出 never_synced / stale 章节；
  16 个被覆盖版本下载 409。
- 浏览器（Playwright，start-dev 环境）：签字页清单显示真实阻断项；交付中心生成两次附注后两版各自可下载；在线编辑改一处正文 →
  点生成附注弹出一致性确认框 → 确认后落版本；附注交付件无回填按钮、报告正文有；版本链陈旧底版标签；财务报表溯源面板文案。
  改带自动保存页面前浏览器先停 `about:blank`。
- LibreOffice：OO 保存的新版本转文本，「七、」保持。

## 9. `*` 任务 ROI 判断
| 任务 | 改动面 | 收益 | 风险 | 结论 |
|---|---|---|---|---|
| 报告正文回填补 commit（§4.2） | 路由一行 | 报告正文回填从「随会话回滚」变真落库 | 低 | 做 |
| 无限定列基线中的死代码清理 | 视重算结果 | 减少基线条目 | 删死代码需逐个确认 0 调用方 | 只登记不删（本 spec 不扩范围） |
| 报表引擎清理配置外历史行过期标记 | report_engine | BS-042/053 不再常驻过期 | 动报表引擎，需另行评估 | 不做，登记 §10 |

## 10. 决策与登记
- 🔴 **附注回填方向裁定（2026-10-17 用户确认）**：附注唯一权威源是底稿披露表单项推送（底稿 → 附注），交付中心是附注的
  只读下游出口。原设计「交付 Word 改字回填附注」是逆流（下游改上游、可能与底稿事实不符），即使行级补丁 + 双校验不误写，
  方向仍错 ⇒ **整体下线附注回填**，改为导出前一致性确认闸门（列出不一致章节，用户确认或去底稿同步后再导出）。
  内容修改回底稿；在线编辑保存仍可另存交付件新版本（不碰附注模块）。
- 否决「把附注回填做得更安全（正文区书签 + 行级补丁 + 冲突裁决）」：方向错，安全化不解决逆流本质。
- 报告正文回填**保留**：段落文字在交付件里、不涉底稿→附注推送链，回填不构成逆流；仅补 commit + 回执语义。
- 否决「回调遇陈旧底版直接拒绝」：会丢用户编辑；改为保存 + 标记 + 留痕。
- 否决「签发清单检查失败降级为 info」：等于默认放行签字。
- 不修：已被覆盖的 16 个历史版本文件（不可恢复，下载如实 409）；报表行配置外历史过期标记（报表引擎范围）；交付中心路由整体仅按角色
  鉴权（冻结在前缀维鉴权基线，另立 spec）；报告正文预渲染文件在并发渲染时共用路径（同一交付物极少并发，锁内取号已避免版本号冲突）。

### 10.1 Task 29 无限定列违规「活路径 / 死代码」逐条裁决（2026-10-18 实施复算）

现算 `test_raw_sql_unqualified_column_contract` 全部违规 ⊆ 基线、基线每条仍真实出现（7 passed，pg_only 真库）。按调用链逐条核：

**活路径（已修 + 从基线移除，「修一条删一条」已由契约第 2 向断言守护）** —— 这三条在 Task 28 建基线时即已修复，故从未进入 `_UNQUALIFIED_BASELINE`：
| 列键 | 文件 | 原症状 | 修复 |
|---|---|---|---|
| `export_tasks.output_path`（+ `export_id`） | `routers/export_integrity.py` | `GET /exports/{id}/download` 单实体表裸 SQL 查真库不存在列 ⇒ 每次 UndefinedColumn **500** | 改 `SELECT file_path FROM export_tasks WHERE id::text=:eid` |
| `trial_balance.debit_amount` / `credit_amount` | `services/eqcr_shadow_compute_service.py::_get_team_result` | team 侧借贷平衡查错表（这两列在 `tb_balance` 非 `trial_balance`）⇒ 被外层 try/except 吞成 `None` ⇒ **影子计算 team 侧恒取不到真实值 / `has_diff` 恒 True**（静默失效） | 改 `FROM tb_balance`（与 Layer 1 口径一致） |
| `working_paper.wp_status` | `services/wp_quality_score_service.py::get_dashboard` | 质量看板 SELECT 死列（真名 `status`，且该方法从未读取它）⇒ 接线后首次调用即 UndefinedColumn **500** | 删除 SELECT 中的 `wp_status`（下游只用 quality_score / consistency） |

- 变异验证（修一条删一条真被守护）：磁盘把 `export_integrity.py` 的 `file_path` 改回 `output_path` ⇒ `test_no_new_unqualified_column_violations` 立即打红报 `🔴 export_tasks.output_path`（证明该活路径确不在基线、再次引入即被拦）；恢复后 7 passed，`git diff --stat` 空（逐字节还原）。

**`quality_score` / `procedure_completion_rate` 两列（V191 Task 7 已补迁移 + ORM，非基线项）** —— 这两列是**合法列名、单表限定**，补列前的症状不是「无限定列查错表」而是「列根本不存在」（`test_raw_sql_column_contract` 另一守卫维度）。补列后真库实测（事务内 + rollback，零落库）：
- 3 读方全部对真实 schema 有效：`wp_quality_score_service.get_dashboard`（SELECT quality_score，324 底稿 avg 0.0）、`wp_health_dashboard.py`（`AVG(quality_score)` 裸 SQL）、`wp_quality_score_service.calculate_score`（SELECT COALESCE(procedure_completion_rate,0)）。
- 2 写方在事务内 UPDATE 生效、读回一致：`calculate_score`（UPDATE quality_score，事务内读回 = 返回 score=47）、`wp_quality_score_linkage.recalc_quality_score`（UPDATE 两列，读回 (47, 0.00)）。
- 落库零影响复核：整体 rollback 后新开会话读回 `(NULL, NULL)`（原始值），确认未落库。

**死代码 / 守卫降级 / pgvector 条件路径（保留在基线、本 spec 不修，§9 ROI 表「只登记不删」）** —— 逐条确认其调用链在 `try/except` 内降级（不 500、功能静默失效）或仅在未启用的条件路径：
- `projects.audit_report_date` / `balance_sheet_date` / `industry`：A8-1 / A1-11 render strategy、h5 油气资产服务，均 try/except 降级默认值。
- `checklist_responses.value` / `content`：E0 发函清单、M1/M2/M6 服务、J2 import/export，try/except 降级（真实载荷在 remark JSON）。
- `working_paper.wp_code` / `wp_name`、`trial_balance.row_code` / `row_name`：`linkage_service`；现读确认唯一调用方 `linkage_facade_service._trace_from_tb` 用 `try/except Exception: logger.warning(...)` 包裹，异常只致联动提示缺失、不 500。
- `tb_balance.aux_type` / `aux_code` / `aux_name` / `audited_amount`：`note_ai_assistant_service`，两处查询 try/except 返回 None（一致性校核静默无结果）。语义层修复需厘清 binding 的 account_code 命名空间，超本 spec 范围。
- `audit_log_entries.action` / `created_at` / `details`：`wp_audit_trail_service` / `procedure_trim_engine`，try/except 降级（真实审计链在 app_audit_log / trace_events）。
- `workpaper_snapshots.wp_id` / `snapshot_data` / `trigger_event`：`wp_version_search_service`，调用方路由 try/except 降级（版本搜索静默返回空）。
- `confirmations.cycle` / `year` / `has_difference`：`auto_data_resolvers/_cycle.py`，try/except 降级为「尚未发起函证」。
- `knowledge_index.embedding`：`vector_store.PgVectorStore`，仅当 `VECTOR_STORE_BACKEND` 选中且 pgvector 扩展 + V043 落地时才走此路径（真库未 `CREATE EXTENSION`，恒降级 PgTextStore）。
- 幽灵表 `wp_template_registry`（`custom_query.py` / `wp_template_registry.py`）：两处访问前先 `SELECT EXISTS(information_schema.tables ...)` 判存在 ⇒ 表未建时不触达裸 SQL。

### 10.2 跨会话预存红登记（2026-10-18 Task 31/33，HEAD 干净检出复算，**非本 spec 引入**）

HEAD（`3e82df9bf`，分支 `spec/disclosure-note-doc-upload-and-batch-fill`）本身带有一批预存失败：临时 worktree 干净检出（无本 spec 任何改动）复跑逐条同红，归因均为**并发会话 trio-merge 提交 + 并发会话未提交工作**，**不属本 spec**。登记备查并明确责任归属：

| 预存红 | 现象 | clean-HEAD 复跑 | 归因 / 责任方 |
|---|---|---|---|
| `test_full_deliverables_executor` 5 例（all_steps_succeed done=3≠4 / single_step / first_step / unadjusted_step / progress_increments） | 全套生成步骤计数断言 | HEAD 逐例同红 | HEAD 的 16b 合并提交（`3e82df9bf` trio 采纳 refresh_rebuild）。本 spec 对该文件只**新增** `TestDisclosureNotesConsistencyFlag`（2 passed），未改这 5 例 |
| `test_raw_sql_tables_are_known`（`json_populate_recordset` 幽灵表） | 全量表契约假阳 | HEAD 同红 | 并发会话 `note_project_realign_apply.py`（已 staged、HEAD 含 2 处 `json_populate_recordset`）；函数式表源清单未同步。本 spec 不碰该文件（tasks Phase A #5 已记） |
| `test_migration_integrity_pg::test_no_unexplained_checksum_drift` + `::test_checksum_comparison_actually_ran` | 活库版本 **189** 校验和漂移、未登记 `KNOWN_CHECKSUM_DRIFTS` | HEAD 逐字同红（`assert [('189',...)]==[]`） | 并发 trio 的 V189（share_change_event）；与本 spec V191 无关 |
| `test_property_54_onlyoffice_unavailable_degradation` | OO 不可用降级 | HEAD 同红 | 预存（Phase C Task 16 已记），非本轮引入 |
| `test_lazy_import_resolvability::test_baseline_has_no_zombie_entries` | 僵尸基线项 `phase5_f4_accounts_payable.py → phase5_f4_01_adjudication` | HEAD 即红 | F 循环 workpaper-sync 基线陈旧（该 3 文件本 spec 未改、目标模块已在 HEAD） |

🔴 **CI 阻断提示（责任归属：trio / 并发会话，非本 spec）**：`.github/workflows/ci.yml` 的 `backend-tests` job 跑 `pytest backend/tests/ -x`（首个失败即整 job 中断）。上表预存红会在本 spec 任何提交推送后让 CI 在 `backend-tests` 第一条红处 halt —— **这是 HEAD 既存的 CI 阻断，源头是 trio-merge 提交与并发会话未提交工作，不是本 spec 引入**。本 spec 的提交不新增任何红（Task 31 全量回归 + 干净检出已证实）；CI 绿化需 trio / 并发会话各自登记其 `KNOWN_CHECKSUM_DRIFTS` / 修 `test_full_deliverables_executor` / 同步 `json_populate_recordset` 表源清单 / 刷新 lazy-import 基线，均在本 spec 范围外。

🔴 **Task 32 flow⑤（版本链陈旧底版标签）诚实部分登记**：版本链 DTO 的 additive 字段 `base_version_no` / `overwrote_versions` 已在浏览器实证对全部 18 版正确下发（schema 透传生效）；但真库现有 OnlyOffice-edit 版本（v3/v15）早于 V191 的 base 追踪，**无 `overwrote_versions` 非空的陈旧底版样本**，故「基于第 N 版编辑，覆盖了第 M 版」标签的**可视渲染无真实数据可触发**（构造需夹在 base 与当前之间的他人刷新 + OnlyOffice 回调，风险高未做）。⇒ DTO 管道 = 浏览器实证；标签可视 = `DeliverableVersionList` vitest（Task 16，32 例）守卫覆盖、无真实数据。属诚实部分完成，非假绿。

### 10.3 提交后复盘（2026-10-19，追加）

- **548318fb1 漏提交 5 个模型文件**：任务 20 / 22 的子代理把本 spec 自己的改动误判为「并发会话已实现」，任务 33 的提交清单据此排除了 `phase13_schemas` / `phase13_models` / `workpaper_models` / `ai_models` / `audit_platform_models`。干净检出探针：导入 `NoteConsistency` 报 ImportError（每次生成附注 500）；`WordExportTaskVersion(base_version_no=)` 报 TypeError（`render_and_store` 每次建版本都传这三个参数 ⇒ 报表 / 附注 / 报告正文 / 在线编辑保存全部失败，版本链列表也报错）；`DeliverableExportRequest` 无 `confirm_inconsistent`。补提交 **6c262c06f**（5 个模型文件 + `ai_models.py` 行数白名单 + 注释 V189 → V191），干净 worktree 跑本 spec 后端套件 107 passed 后推送。
- **同一提交反向带入了别的 spec 的两个测试**：`test_phase8_endpoint_auth_fires.py` 与 `test_project_endpoint_authorization_baseline.py` 的 Phase 8 改动属 disclosure-note-template-word-realignment Phase 8 Task 8，对应的 17 个路由改动仍在主工作区未提交 ⇒ HEAD 上这两个文件 8 例红。路由改动属并发会话，本 spec 不代提交。
- **主工作区暂存区落后于 HEAD**：HEAD 被前移后暂存区没同步，本 spec 18 个新文件显示为已删除、12 个文件为 `MM`，此时在主工作区提交会回退本 spec。已按路径 `git reset -q -- <本 spec 路径>` 对齐，其他会话已暂存的文件未动。
- **Task 32 验收在真实项目安徽留下残留**：附注任务 `file_path` 指向已删除的 `disclosure_notes_2025_v18.docx`、`selected_sections` 为测试值 `["八、1","八、4"]`、章节状态只剩 2 行且都指向第 18 版。已在一个事务内修复：任务投影（file_path / file_size / html_path / selected_sections / source_snapshot_refs）按 v16 恢复，删除 2 行孤儿章节状态，写审计日志 `deliverable_data_repair`（含修改前的值）。那次 2 章导出删掉的其余章节状态无法恢复，下次整份生成附注时重建；没有直接整份重新生成，因为 v15 是在线编辑版本，重新生成会让最新版丢掉这些人工修改。
- **前端两处修复**：①报告正文回填被拒原因改读 `rejection_reason`（原读 `item.reason`，后端被拒项没有这个字段 ⇒ 恒空；且对所有被拒项硬编码「金额变更须通过调整分录」，标题类拒绝也显示这句），按钮文案「回填到附注模块」改为「回填到报告正文」②附注一致性确认框正文抽到 `noteConsistencyMessage.ts` 统一转义（原把库里的章节标题 / 底稿编码原样拼进开了 `dangerouslyUseHTMLString` 的 HTML）。vitest 5 文件 74 passed；两处变异（回退读 `item.reason` / 转义失效）均打红并逐字节恢复；单区域 vue-tsc 改动文件 0 错（另 7 个错误在未改动的 DeliverableGroupList / DeliverablePreview / stores/project，属既有）。
- **待拍板**：①全套生成的 `needs_confirmation` 没有消费方（三件套接口不返回、不落 export_job_item、前端不展示），一键全套生成时不一致的附注照常导出且无提示 —— 接到接口 + 交付中心列表，或删除；②生成附注要确认两次：P2-10 质量预检与一致性闸门读的是同一份 `build_readiness` —— 建议预检只保留闸门不覆盖的校验错误 / 无数据项。Task 32 浏览器里看到的是预检框，新闸门的弹窗在界面上未被实际看到。
- 前端另有 9 处 `dangerouslyUseHTMLString`（OCR 预览 / 函证撤回 / 独立性声明等），是否转义未逐个审计。

### 10.4 两项待拍板的处理（2026-10-19，追加）

- **一键全套接导出前一致性闸门，删除 `needs_confirmation`**：一键全套（`POST /word-exports/full-deliverables`）是用户唯一的批量入口（三件套创建端点 `POST /deliverables/trio` 没有前端调用方），执行器直接导出附注、全程无提示；`needs_confirmation` 只在导出之后打标且无人读取 —— 方向裁定要求「导出附注前」让用户确认或去同步，导出后的标记做不到。改为路由在建任务之前用同一判定 `check_note_consistency` 拦截：会导出附注 + 未确认 + 不一致 ⇒ 409 `notes_inconsistent`（清单只带确认框要显示的 note_section / section_title / wp_codes），前端弹与「生成附注」同一个确认框，「仍要导出」带 `confirm_inconsistent=true` 重发（job payload 留痕）。删除执行器的 `needs_confirmation` 字段、两处计算与 `_disclosure_notes_needs_confirmation`；步骤口径抽 `resolve_full_steps` 给执行器与闸门共用。一键全套请求加 `_silent`：409 / 超时 / 失败由调用方提示，同时避免 5xx 自动重发把整套生成重跑两次。
- **生成附注只确认一次**：P2-10 预检只保留校验错误 / 无数据；未同步与过期由导出闸门按所选章节逐条列出。导出后的「附注出具提醒」去掉「从未同步」一条（确认框里刚列过同一清单）。
- **顺带修复：`check_note_consistency` 的 fail-open 在 PG 上不成立**。`build_readiness` 内部有 3 处查询失败即吞掉（最近校验结果 / 底稿 id 反查 / 公式灰度），PG 一条语句失败会让整个事务 aborted，吞掉异常救不回来 ⇒ 调用方随后的导出写入全部失败。改为看板在保存点内执行、无论成败都回滚到保存点（只读；回滚到保存点在 aborted 状态下照样可执行）。pg_only 守卫 `test_deliverable_note_consistency_pg.py` 在 `latest_findings_by_section` 注入非法 SQL 并吞掉，断言同一会话后续查询可用。
- **验证**：新增 / 改动后端 16 passed（一键闸门 6 + 一致性 10）；回归 50 passed / 5 failed（`test_full_deliverables_executor` 5 例，即 §10.2 已登记的 HEAD 预存红）；PG 1 passed；前端 vitest 5 文件 80 passed；变异 4 处全部打红并逐字节恢复（预检加回未同步 / 409 辨识不看 code / 闸门关闭 / 去掉保存点，后者单测与 PG 守卫同时打红）；单区域 vue-tsc 改动文件 0 错（另 7 个错误在未改动文件，属既有）。
- **未修登记**：`/word-exports/*` 整个路由只校验登录、不校验项目（含本次改的一键全套端点），任何登录用户都能为任意项目发起生成 —— 属项目级鉴权欠账（在 `_PREFIXED_IDENTITY_ONLY_BASELINE` 棘轮内），改访问控制需另行确认；本次只把 409 清单收窄到确认框所需三项。三件套 readiness 只拦过期附注、不拦从未同步，但三件套创建端点没有前端调用方，暂不处理。
