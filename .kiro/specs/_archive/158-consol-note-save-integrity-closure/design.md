# 合并附注保存完整性收口 — 设计

需求见 `requirements.md`（R1~R5）。本文只写现状落点、方案取舍、接口与测试，不复述需求。

## 1. 现状确认（HEAD `39777a020` 现读）

| 事实 | 位置 |
| --- | --- |
| 保存端点 `except Exception` 回滚后 `return {"ok": False, "error": str(e)}`，状态码 200 | `backend/app/routers/consol_note_sections.py` `save_note_data`（:375-409） |
| GET 用 `load_scoped_note_record(allow_root_legacy_fallback=True)` 取行，返回 `content / updated_at / node_key`，无摘要 | 同文件 `get_note_data`（:353-372）；`backend/app/services/consol_node_scope.py:209-234` |
| 保存：`FOR UPDATE` 锁精确行后整份替换；根节点首次写入锁 legacy 行；撞唯一键后重读赢家并写入，赢家路径漏写来源投影 | `consol_node_scope.py:281-363`（:305、:323、:345-361） |
| 主保存路径检查 `ok === false`；批量导入 `api.put(importUrl, …)` 不检查，异常时整批中断且已写章节不回报 | `audit-platform/frontend/src/components/consolidation/ConsolNoteTab.vue` `performSaveNoteData`（:2366-2425）、导入段（:2686-2697） |
| 5xx 自动重试只对 GET 或带幂等键 / `_retrySafe` 的写请求 | `audit-platform/frontend/src/utils/http.ts` `shouldRetry5xx`（:400-411） |
| 人工保护解析三份：`_parse_manual_cells` / `_parse_locked_cells` 遇坏项静默跳过；`_manual_cells` 遇坏项抛 `NoteFormulaError`；公式路径另有内联锁定格解析 | `consol_note_detail_apply_service.py:506-538`；`consol_note_formula_service.py:1102-1133`、:1325-1328 |
| 使用宽松解析的写入方 | `consol_note_detail_apply_service.py:340`、`consol_note_subtree_reaggregate.py:548`、`consol_note_topn.py:266` |
| 写 `data` 的原生 SQL：自定义查询单格回写，不标手工格、不写来源投影 | `backend/app/services/custom_query/snapshot_writer_modules.py:218-224` |
| 只改状态列的写入方：推送标待更新、公式设置传播、stale 标记 | `consol_push_service.py:216-219`、`formula_settings/propagation.py:181`、`formula_settings/stale_marks.py:99` |
| `cell_state` / `locked_cells` 全仓无赋值写入方 | 全仓 grep `cell_state\s*=`、`.locked_cells =` 仅 `detail_apply:464` 行号重映射 |
| 可复用的摘要算法 | `consol_note_source_projection.source_digest`（`canonical_json` + SHA-256） |
| 守卫范式 | `backend/tests/formula_writer_ownership/test_note_writers_guard.py`（单体附注写入方 AST 扫描） |
| 行数门（Python `splitlines` 口径，HEAD 与工作区一致） | `consol_note_sections.py` 1016 / 白名单 1032（+5% 上限 1083）；`ConsolNoteTab.vue` 3527 / 白名单 3439（上限 3610）；`consol_note_formula_service.py` 1455 / 白名单 1470（上限 1543） |
| 共享库：3518 行，`manual_cells` 3 行 5 项全合法，`locked_cells` 非空 0，`cell_state≠auto` 0 | 2026-11-11 只读查询 |

## 2. 方案取舍

### 2.1 CAS 令牌：内容摘要，不加 revision 列

| 方案 | 结论 | 理由 |
| --- | --- | --- |
| A 内容摘要（选用） | ✅ | 不需要迁移；任何改了 `data` 的写入方（含原生 SQL 单格回写）都会自然改变摘要，不依赖每个写入方记得自增版本；只改 `is_stale` 的写入方不造成假冲突 |
| B 新增 `content_revision` 列 | ❌ | 需迁移 + 全部写入方（ORM 与原生 SQL 共 7 处以上）同步自增，漏一处即「丢更新检测不到」，且无法用守卫完全证明 |
| C SQLAlchemy `version_id_col` | ❌ | `sa.update()` 与原生 SQL 不自增；并发 ORM 更新会在自动写入方里抛 `StaleDataError`，改变重汇总等既有失败语义 |
| D 用 `updated_at` | ❌ | SQLite 秒级精度，且推送标待更新等只改状态的写入也会刷新时间 ⇒ 假冲突 |

摘要值 ABA（内容改了又改回）视为未冲突：比较对象是「用户看到的内容」，内容相同即不存在被覆盖的他人修改。

### 2.2 缺令牌：严格 428，不做渐进放行

当前生产调用方只有 `ConsolNoteTab.vue` 两处（保存、批量导入），后端测试一处（`test_consol_task15_p0p2_http_orm.py:507-527`），e2e 只列路由不发请求。调用方可一次改完，放行缺令牌只会留下一条不受保护的旁路。服务层 `save_scoped_note_record` 新增仅限关键字参数，默认「不检查」，供既有服务层测试与非 HTTP 调用方保持原语义；HTTP 层强制二选一。

### 2.3 保护元数据损坏：fail-closed

现读共享库没有坏数据，改严格解析对现有数据零影响（§1 末行）。宽松解析的后果是「坏一项、丢一格保护、该格被自动值覆盖」，且没有任何回报，属静默丢数据；严格解析的代价是该章节本次不写入并给出原因，用户可见、可修。

### 2.4 写入方治理：合并附注自建登记，不复用单体 `WriteGate`

单体矩阵按 `(准则, 章节, 表, 字段)` 声明唯一自动写方；合并附注是同一章节多个写入方按行列坐标共存（明细映射写个别数列、差额节点写调整抵销列、汇总节点按列求和，见归档 spec `65-consol-note-pull-from-standalone` 任务 12 裁决②）。两者数据模型不同，套用矩阵会把合法的共存判成冲突。合并侧只需要：①所有自动写入方走同一保护函数；②新写入方必须登记。

## 3. 接口

### 3.1 GET `/api/consol-note-sections/data/{project_id}/{year}/{section_id}`

响应新增 `data_digest`：

```json
{ "content": {}, "updated_at": "...", "node_key": "G:consol", "data_digest": "<64 hex>|null" }
```

摘要对 `content` 本身计算（即 `record.data` 为对象时取其值，否则 `{}`），与返回体逐字节同源。

### 3.2 PUT 同路径

请求体：

```json
{ "data": {}, "expected_digest": "<64 hex>|null" }
{ "data": {}, "force_overwrite": true }
```

| 情形 | 状态码 | `detail.error_code` |
| --- | --- | --- |
| 两个字段都缺 | 428 | `CONSOL_NOTE_DIGEST_REQUIRED` |
| 两个都给 / `expected_digest` 非 64 位小写十六进制且非 null / `force_overwrite` 非 true | 422 | `CONSOL_NOTE_SAVE_INVALID` |
| 基准内容摘要 ≠ 期望 | 409 | `CONSOL_NOTE_CONFLICT`（另含 `current_digest` / `updated_at` / `last_write_source` / `message`） |
| 作用域错误 / 合并锁定 / `data` 非对象 | 原状态码（400/404/409/423/400） | 原文案 |
| 其他异常 | 500 | `CONSOL_NOTE_SAVE_FAILED`（中文通用文案；原始异常进日志） |
| 成功 | 200 | 响应 `{ok: true, updated_at, node_key, data_digest}` |

`last_write_source` 取 `data._last_write_source`，没有时 `manual`，前端据此显示「最近写入：子树汇总 / 明细映射 / 公式计算 / 手工」。

### 3.3 POST `fill-by-formula`

`fill_note_by_formula` 在 `await db.commit()` 前对写入行计算摘要，响应追加 `data_digest`；跳过类结果（`skipped_locked` / `kept_pulled`）同样回当前行摘要，前端照常采用。

### 3.4 服务层

`consol_node_scope.save_scoped_note_record(db, scope, data, *, now=None, expected_digest=_UNCHECKED)`：

1. `base = load_scoped_note_record(db, scope, allow_root_legacy_fallback=True, for_update=True)`；
2. `expected_digest is not _UNCHECKED` 时比较 `digest_of(base)`（无行为 `None`），不等抛 `NoteSaveConflict(current_digest, updated_at, last_write_source)`；
3. 精确行存在 ⇒ 原地替换 + `update_source_projection(record, "manual")`；不存在 ⇒ 原有创建流程；
4. 撞唯一键：重读赢家；`expected_digest` 受检时用赢家内容再比较一次（不等即冲突）；通过后写入并补 `update_source_projection(winner, "manual")`。

`digest_of(record)` 与 `NoteSaveConflict` 放在 `consol_node_scope.py`，摘要直接调 `source_digest`。路由只做参数校验与错误映射。

## 4. 人工保护模块

新文件 `backend/app/services/consol_note_protection.py`：

| 函数 | 说明 |
| --- | --- |
| `parse_manual_cells(data) -> set[tuple[int,int]]` | `data.manual_cells`；缺失或 `None` ⇒ 空集；非列表 / 坏项 ⇒ `ProtectionMetadataError` |
| `parse_locked_cells(record) -> set[tuple[int,int]]` | `record.locked_cells`；同上，项为 `{row_index, col_index}` |
| `section_locked(record) -> bool` | `cell_state == 'locked'` |
| `protected_cells(record, data) -> set[tuple[int,int]]` | 上两者并集；四个自动写入方的唯一入口 |

`ProtectionMetadataError(ValueError)` 带 `status = 422` 与中文消息（「人工保护标记第 N 项无效：…，本章节未写入」）。

写入方改动：

| 写入方 | 改动 | 坏元数据时 |
| --- | --- | --- |
| `consol_note_detail_apply_service.apply_detail_refresh` | 改调 `section_locked` / `protected_cells`；删两个私有解析 | 抛 `ApplyError(422, "PROTECTED_CELLS_INVALID", msg)`，重汇总按既有 `except ApplyError` 记为跳过并回报 |
| `consol_note_formula_service.fill_by_formula` 内部 | 删 `_manual_cells` 与内联锁定格解析，改调 `protected_cells` | 转 `NoteFormulaError(msg, status=422)`（沿用路由 `_note_error`） |
| `consol_note_subtree_reaggregate` 汇总节点写入（:548） | 改调 `protected_cells` | 异常由章节级 `except Exception` 整章回滚并回报原因 |
| `consol_note_topn.write_topn` | 改调 `protected_cells` | 同上（重汇总调用）；`apply_topn_refresh` 的 HTTP 入口映射 422 |

`remap_protected` 等仍需分开的 manual / locked 两个集合，改为分别调用 `parse_manual_cells` / `parse_locked_cells`，保持重映射语义。

### 4.1 自定义查询单格回写标手工格（R3.6）

现状：`write_note_cell`（`snapshot_writer_modules.py:62-224`）行锁 → 归属复验 → 乐观锁 → 按 `cell_ref` 定位 `data.rows[row-1]` → 数组行写 `target_row[col_idx]` → 原生 SQL 整份 `UPDATE data`。坐标与 `manual_cells` 同一套（行下标进 `data.rows`、列下标进行数组），与前端 `markManual` 的「第 0 列不标」一致。

改动（都在写 SQL 之前、同一事务内）：

1. 数组行且 `col_idx >= 1`：`existing = parse_manual_cells(data)`（严格，坏数据抛 `ProtectionMetadataError` ⇒ 端点 422，事务回滚）；`(data_row_idx, col_idx)` 不在其中则追加 `{"row": data_row_idx, "col": col_idx}`；回执 `marked_manual = True`。
2. 第 0 列或字典行：不改 `manual_cells`，回执 `marked_manual = False` 与 `manual_skip_reason`（「项目名列不参与取数」/「旧格式字典行没有格坐标」）。
3. 来源投影不在本条处理（原生 SQL 不经 ORM；`source_mode` 是「最后写入方」的粗分类，保存 CAS 与保护判定都不读它）。

字典行判定按行实际类型，不按全表推断；共享库 0 行字典行，该分支只为兼容旧数据保留。

## 5. 写入方登记与守卫

新文件 `backend/app/services/consol_note_writers.py`：`ConsolNoteWriterSpec(writer_id, entrypoint, trigger, role)` 元组 + `CONSOL_NOTE_WRITER_EXCLUSIONS`（入口 → 理由）。角色：

- `automatic`：明细映射、按公式填入、子树重新汇总、前 N 名重排（写入自动值，必须引用保护函数）；
- `manual`：手工保存、自定义查询单格回写；
- `structural`：只复制或搬移已有内容、不产生新值的入口，如根节点 legacy 行复制（`consol_note_formula_service._copy_note_data_record`）；其余扫描到的入口实施时逐个裁决并写明理由；
- `stale`：只改 `is_stale` 等状态列的入口，单独列表，不要求引用保护函数。

守卫 `backend/tests/test_consol_note_writers_guard.py`：

1. 扫描 `backend/app/**/*.py`，观测四种形态（requirements R4.2），以「模块:限定名」记录；
2. 观测集合 = 登记 ∪ 排除；登记表多出的条目同样失败；
3. `automatic` 入口函数体（含嵌套函数）必须有 `Name` / `Attribute` 引用 `protected_cells` 或 `section_locked`；
4. 原生 SQL 形态：字符串常量去注释后匹配 `UPDATE\s+consol_note_data\s+SET[^;]*\bdata\s*=`；
5. 变异证明在测试内用临时源码字符串跑同一扫描器完成，不改磁盘文件。

自定义查询单格回写登记为 `manual`；它在 §4.1 起会调用 `parse_manual_cells`，守卫不要求 `manual` 角色引用保护函数，但本条由 §7 的回写用例钉住。

## 6. 范围外与待确认

| 项 | 处置 |
| --- | --- |
| 自定义查询单格回写不更新 `manual_cells` | 已纳入本轮（R3.6、§4.1），按 Excel 导入「人工录入标手工」的既有口径处理 |
| 附注回写的虚拟列表 `_NOTE_COLUMNS = [code, name, year_end, year_begin, formula]` 是旧字典行口径，数组行按列下标直写，列名与当前表头不对应 | 前端暂无附注回写入口，本轮不改；若开放前端入口须先重做列映射 |
| `cell_state` / `locked_cells` 无写入方 | 非目标；读取侧保持兼容 |
| 拖拽改上级 CAS、三码规范化、Excel 代码列 | 已立 spec `consol-group-code-entry-consistency`；`tree_kind` 与树指纹规则版本经核对不做（见该 spec design §6） |
| stale 原因、重新汇总 / 推送 / 审批回执的状态语义 | 已立 spec `consol-status-semantics-closure`（以本 spec 为前置） |
| 树版本结构化 | review 文档 §10 P2，未纳入 |

### 6.1 本轮实施后的已决项与证据（2026-11-12）

以下状态以当前工作区代码和实际验证结果为准，不以 `tasks.md` 的勾选或执行历史单独作为完成证据：

| 项 | 当前结论 | 实现 / 验证证据 |
| --- | --- | --- |
| 保存失败如实报错（R1） | **已落地** | `backend/app/routers/consol_note_sections.py:459-478` 记录异常并返回 500 `CONSOL_NOTE_SAVE_FAILED`，不回显原始异常；批量导入逐章节收集成功/失败。后端相关选集 127 passed；前端批量导入部分失败、全部失败和 PUT 5xx 不重试用例通过。 |
| 内容摘要 CAS（R2） | **已落地** | `consol_node_scope.save_scoped_note_record` 与 `consol_note_sections.py` 实现 `expected_digest` / `force_overwrite`、GET/PUT/公式回执 `data_digest`、赢家重读比较和来源投影；`test_consol_note_save_cas.py` 及服务层回归通过。 |
| 人工保护格单一解析（R3.1~R3.5） | **已落地** | `backend/app/services/consol_note_protection.py:104-166` 严格解析三种 `manual_cells`、`locked_cells` 和整节锁定；四个自动写入方改用保护集合，坏元数据拒写。保护模块、明细映射、公式、重汇总和 TopN 相关后端选集通过。 |
| 自定义查询单格回写标手工（R3.6） | **已落地** | `backend/app/services/custom_query/snapshot_writer_modules.py:198-255` 对数组行数值列追加 `manual_cells`，第 0 列/字典行回报跳过原因；`test_custom_query_note_writeback_manual.py` 验证回写后生产公式填入仍保留值。 |
| 合并附注写入方登记与 AST 守卫（R4） | **已落地** | `backend/app/services/consol_note_writers.py:82-309` 登记内容写入、结构初始化和 stale 入口；`backend/tests/test_consol_note_writers_guard.py` 覆盖双向对账、automatic 保护引用、未登记入口和去保护引用变异，后端选集通过。 |
| 前端摘要/冲突/批量导入接线（R2.8） | **已落地，存在非本轮预存回归** | `ConsolNoteTab.vue:2409-2411,2741-2744` 和 `consolNoteSaveConflict.ts:58-93` 接入摘要、冲突弹窗、重读/保留本地修改与 `force_overwrite`。本次定向相关用例 9 passed；更宽的 ConsolNoteTab 选集仍有 2 个 HEAD 同样失败的异步重汇总用例，候选与 HEAD 对照均为 101/103 vs 85/87，未新增失败。 |
| 浏览器 / 真实 PG 证据（R5.1） | **仅部分证据可复核** | Task 7.3 的正式 PUT、CAS 恢复、三阶段摘要和 PG 全字段对账已内嵌于 §6.1.1「Task 7.3 正式 PUT 恢复对账」；测试项目真实 PG 上的目标节点恢复一致。 | 7.1/7.2 的执行历史虽存在，但没有保留截图或响应拦截报告，不能仅据勾选将两项写成可独立复核的浏览器通过。当前没有把 gitleaks 写成通过：本轮未找到 gitleaks 执行记录。 |
| 类型检查 / gitleaks | **不作通过结论** | 类型检查对照记录仍显示同一组预存类型错误；本次没有找到 gitleaks 执行记录，未把 gitleaks 写成通过。 |

本轮已决定的设计边界：摘要 CAS 不新增数据库列；Excel 批量导入使用 `force_overwrite=true`；自动写入方统一使用严格保护解析；`cell_state` / `locked_cells` 只保留读取兼容，不在本轮增加写入口。

#### 6.1.1 Task 7.3 正式 PUT 恢复对账（2026-11-12）

本次执行记录已迁入本节。该记录只证明 Task 7.3 的真实 PostgreSQL 修改、恢复和对账，不替代 Task 7.1/7.2 的浏览器冲突与拦截响应证据。

- **对象范围**：测试项目 `【测试】公式同步集团有限公司_2025`（`project_id=3a3930db-3f14-431c-a919-913d04a23eca`），年度 `2025`，章节 `五-5-6`，节点 `9150000FGXUAT000P1:consol`；目标 `consol_note_data.id=41c48347-3b61-4c84-8b66-25e453e7dfaf`。
- **正式写入路径**：`PUT /api/consol-note-sections/data/{project_id}/2025/五-5-6?node_key=9150000FGXUAT000P1%3Aconsol`。修改与恢复均使用带 `expected_digest` 的正式 PUT；两次请求均未使用 `force_overwrite`。恢复载荷是 before GET 的完整 `content`，不是直接 SQL 或数据库强制覆盖。
- **可逆修改**：将 `data.rows[1][1]`（「1至2年」行的「期末余额/账面余额」列）从空字符串改为 `"7.00"`。修改 PUT 以 before 摘要为 `expected_digest`，返回 HTTP 200 和修改后摘要；恢复 PUT 以修改后摘要为 `expected_digest`，返回 HTTP 200，并恢复 before 的完整内容。

三阶段摘要如下，恢复后的 API 摘要、before PG `source_digest` 和恢复后 PG `source_digest` 逐值一致：

| 阶段 | `data_digest` |
| --- | --- |
| before GET | `0d97b8a4f7a7eb81e0b5ac23a81c24914c981bbe3fd5ac1432a3ddd2e59201fd` |
| 修改后 GET（after） | `b28e7a191b708877b92942442e1874c0ba9efb85f6a11588405d28231af7c130` |
| 恢复后 PUT / GET（restore） | `0d97b8a4f7a7eb81e0b5ac23a81c24914c981bbe3fd5ac1432a3ddd2e59201fd` |

最终 PG 全字段对账结果：

- `data` 深度比较无差集，行值、表头、`_last_write_source`、`_subtree_provenance` 和 `_subtree_child_count` 均恢复；`data.manual_cells` before/after 均为缺失/null，无差集。
- `locked_cells` 保持 `[]`，`cell_state` 保持 `auto`；`source_mode` 保持 `manual`，`source_operation_id`、`source_revision` 保持 `null`，`source_digest` 保持 before 摘要；`is_stale` 保持 `true`，`last_formula_run_id` 与 `last_formula_value` 保持 `null`。因此 data、manual、locked、source、stale 五组字段除系统时间外均无差集。
- 主键与范围字段 `id`、`project_id`、`year`、`section_id`、`node_key` 无差集；该章节仍为 0 条 legacy 行 + 2 条节点行，未创建额外行；另一节点 `9150000FGXUAT000AQ:subsidiary` 全字段未被触碰。
- 在最终 before/after 对账中，**唯一差异是 `updated_at`**：`2026-11-12T02:45:30.290274+00:00` → `2026-11-12T03:14:00.188810+00:00`。这是正式平台保存重新赋值的系统时间，不把它误写成内容差异。相关审计/版本基线计数也未变化。
- PostgreSQL 仅用于只读 before/after 快照和逐字段对账，没有直接 SQL 写入；恢复没有使用 `force_overwrite`，而是由平台正式 PUT 的 CAS 路径完成。

浏览器正式认证请求为 before GET、修改 PUT、修改后 GET、恢复 PUT、恢复后 GET，5 次 HTTP 状态均为 **200**。操作前另有 2 条无 Bearer token 的故意认证探针返回 401，不属于正式操作路径；正式请求没有 401/4xx/5xx，也没有未捕获页面运行时错误。此次没有截图，页面观察到的 `amount_unit` 警告属于既有项目元数据问题，与保存恢复无关。

据此，Task 7.3 的可审计结论为：业务 payload、摘要、人工/锁定元数据、来源字段、stale 状态和主键/范围均恢复一致，只有预期的 `updated_at` 系统时间变化；本次未修改源代码或 `tasks.md`。

### 6.2 用户决策清单（未擅自改变）

| # | 待用户决定 | 当前事实 | 建议 / 影响 |
| --- | --- | --- | --- |
| 1 | 是否开放「整节锁定 / 锁定格」的设置入口 | 当前前后端没有写入方，平台只读取 `cell_state` / `locked_cells`；本轮已保证坏元数据 fail-closed，但没有新增设置 UI、权限和审计事件 | 建议先不开放。若开放，需另立设计明确角色、锁定范围、解锁规则、审计和与 CAS/自动写入方的交互；否则只能继续保持读取兼容。 |
| 2 | 未来若开放自定义查询附注回写入口，是否沿用虚拟列映射 | 当前后端仍有旧的 `_NOTE_COLUMNS = [code, name, year_end, year_begin, formula]`，数组行实际按列下标写；当前前端没有该入口 | 建议开放前先按真实附注表头重做映射，不要直接把旧虚拟列映射暴露给用户；否则可能把值写入错误列。 |
| 3 | 是否补做并留存 Task 7.1/7.2 的浏览器验收证据 | 代码和定向测试已覆盖冲突/错误提示，但本次已迁入的执行记录只包含 Task 7.3 的真实 PG 对账事实，7.1/7.2 没有可复核截图或拦截回执 | 建议在受控浏览器环境补跑并保存响应、页面状态和恢复对账；这只补证据，不改变本轮生产代码结论。 |

已转交而非本轮待决的事项：stale 原因与状态语义由 `consol-status-semantics-closure` 承接；拖拽 CAS、三码规范化和 Excel 代码列由 `consol-group-code-entry-consistency` 承接；树版本结构化仍是 review 文档 §10 的 P2 backlog。它们不因本轮完成而视为已实现。

## 7. 测试与验证

| 层 | 内容 | 文件 |
| --- | --- | --- |
| 服务层（SQLite） | 期望摘要一致写入 / 不一致冲突 / 根节点 legacy 基准 / 期望 `None` 遇已有行冲突 / 撞唯一键赢家内容不一致冲突、`_UNCHECKED` 保持旧语义 / 赢家路径来源投影为 manual / 仅改 `is_stale` 不冲突 | `backend/tests/services/test_consol_node_scope.py` 扩展 |
| 路由（TestClient，真实依赖链） | 428 / 422 / 409 / 500 / 200 摘要回传 / GET 摘要与 content 同源 / 合并锁 423 不变 / fill 回传摘要 | `backend/tests/test_consol_note_save_cas.py`（新）；`test_consol_task15_p0p2_http_orm.py` 改带 `force_overwrite` |
| 保护模块 | 三种合法写法、各类坏项、空值；四写入方坏元数据零写入且回报；合法元数据结果与改动前逐值一致 | `backend/tests/services/test_consol_note_protection.py`（新）+ 既有 `test_consol_note_detail_apply.py`、`test_consol_note_subtree_reaggregate.py`、`test_consol_note_topn.py`、`test_consol_note_formulas.py` 回归 |
| 回写标手工 | 数组行回写后 `manual_cells` 含该格且不重复；随后「按公式填入」保留回写值（端到端走生产函数）；第 0 列与字典行不标且回执说明；已有标记损坏时 422 且行内容不变 | `backend/tests/test_custom_query_note_writeback_manual.py`（新） |
| 守卫 | R4 全部断言 + 两个变异 | `backend/tests/test_consol_note_writers_guard.py`（新） |
| 前端 vitest | 加载 / 重读 / 保存成功 / 按公式填入后记录摘要；保存带摘要；409 保留脏与草稿、两按钮行为；先保存再执行动作在冲突时中止；导入带 `force_overwrite`、部分失败汇总、全失败无成功提示；PUT 不被 5xx 重试 | `ConsolNoteTab.spec.ts` 扩展；冲突判定纯函数单测 |
| 浏览器 | requirements R5.1 | 【测试】合并项目，chrome-devtools，`initScript` 拦截改响应 |

变异清单（每条须确认红在预期断言上）：去掉服务端摘要比较；比较改成用 `updated_at`；赢家路径不再比较；路由缺令牌改放行；500 分支改回 200；严格解析改回跳过坏项（逐个写入方各一条）；前端不带 `expected_digest`；409 分支清脏标记；导入失败仍计入成功。

## 8. 落点与行数预算

| 文件 | 预计 | 预算 |
| --- | --- | --- |
| `routers/consol_note_sections.py` | +35 | 上限 1083（现 1016；后续 spec `consol-status-semantics-closure` 再 +6，合计 ~1057） |
| `services/consol_node_scope.py` | +45 | 800 |
| `services/consol_note_protection.py`（新） | ~90 | 800 |
| `services/consol_note_writers.py`（新） | ~70 | 800 |
| `consol_note_detail_apply_service.py` / `formula_service.py` / `topn.py` / `subtree_reaggregate.py` | 净减 | 各自白名单 |
| `ConsolNoteTab.vue` | +40 | 上限 3610（现 3527；后续 spec 再 +8，合计 ~3575，余量约 35 行。超出时把加载 / 保存的摘要记录逻辑移进 `consolNoteSaveConflict.ts`，不抬白名单） |
| `components/consolidation/composables/consolNoteSaveConflict.ts`（新） | ~50 | 1500 |
