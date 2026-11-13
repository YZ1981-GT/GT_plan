# 合并三码企业树与公式链路审查及优化建议

> 审查日期：2026-11-10（初稿）；本版修订：2026-11-11（v2：事实纠偏 + 缺口补录，见 §0）
> 唯一源码基线：`e25895b20b027422f5b2b1c8f2ce1b97bd5902bb`
> 基线提交：`fix(web-report): 报表取附注章节内容状态改用真实目录端点`（2026-11-09 20:22:46 +0800）

## 0. v2 修订摘要（2026-11-11）

初稿的审查方法、证据分级、验收边界成立，不需要重写；本版只做三类修订，全部基于同一固定提交 `e25895b20b027422f5b2b1c8f2ce1b97bd5902bb` 的只读复核，仍未运行任何测试、迁移或数据库操作。

### 0.1 事实纠偏（8 处：把已实现写成了待建）

初稿有 8 处把固定提交已具备的能力写成 `[REC]`，会让实施方重复建设。本版改为「已实现 / 部分实现 / 未实现」三态，并给出精确落点：

| # | 初稿位置 | 初稿说法 | 固定提交实际 | 修订后表述 |
| --- | --- | --- | --- | --- |
| 1 | §5.3 | 确认接口不得只依赖客户端 hash，服务端须重新计算 | **已实现**：`consol_scope_confirmation_service.py:317-350` 用服务端现算 `fingerprint` 与 `expected_fingerprint` / `expected_revision` 比对，不符返回 409 `SCOPE_FINGERPRINT_CONFLICT` / `SCOPE_REVISION_CONFLICT` | 已实现，仅需扩展到附注映射与推送确认 |
| 2 | §3.2 P0-2 | 服务端以年度为边界重建树，不信任客户端树 | **已实现**：`consol_group_tree.py:726` `load_year_records(db, year)` 从 projects 表重建；`group_links.py:430-433` 每次改上级都重新加载当年记录判环 | 已实现，不列为建议 |
| 3 | §3.2 P1-3 | 自动树与手工改上级都应携带 `tree_version` | **部分实现**：批量侧已有关系基线 CAS（`batch_project_plan.py:409-411`、`batch_project_execution.py:624` 比对 `entity_group_fields_hash` 与行内 `base_hash`）；**拖拽侧没有**（`group_links.py:399-473` 只有 USCC 校验 + `would_form_cycle` + `lock_topology_years`） | 收窄为「拖拽改上级缺 CAS」 |
| 4 | §3.6 | 提出 `SELF_ROOT` / `SELF_PARENT_NORMALIZED` / `INVALID_SELF_CYCLE` / `AMBIGUOUS_SELF_REFERENCE` 四类 | `SELF_ROOT`、`INVALID_SELF_CYCLE` 全仓 **0 命中**；现网枚举是 `group_relation.py:105-126` 的 `SELF_TOP` / `SELF_ULTIMATE` + `effective_parent_code()`（`:92-102`） | 改为「扩展既有 `self_reference_kind` 返回值域」，不新造枚举 |
| 5 | §5.1 | 建议明确三码相等三类语义 | **已实现**：三类语义即 `effective_parent_code` + `self_reference_kind`，注释已写明「空 ⇒ None；等于本企业代码 ⇒ None」 | 已实现，不列为建议 |
| 6 | §7.6 | 交付前应维护写入方清单并逐个证明 | **部分实现**：`note_writers.py:85-128` 登记表 + `:19-36` 五种 role + `note_write_ownership.py:166-200` `WriteGate` + `backend/data/note_write_ownership_matrix.json` + AST 守卫；**但治理对象只覆盖单体 `DisclosureNote`** | 改为「已有矩阵，合并附注未纳入」（见 §0.2 ①） |
| 7 | §5.2 | 建议引入四态 `preview_only` / `ready_for_mapping` / `ready_for_reaggregate` / `ready_for_push` | 现网是**七域五态**：`consol_readiness_service.py:28` `ready/not_ready/unknown/not_applicable/warning`，域见 `:30`、`:148-156` | 改为「在七域五态上补粒度，不新造状态枚举」 |
| 8 | §3.4 | 合并范围树与集团架构森林必须分离 | **已分离**：合并范围走 `consol_scope_members.tree_subsidiaries`（`:70`），展示森林走 `group_forest.py` / `consol_tree_service.build_group_trees_from_projects`（`:220-238`）；缺的只是回执显式标识（`tree_kind` 全仓 0 命中） | 收窄为「回执补 `tree_kind` 标识」 |

### 0.2 缺口补录（4 项：初稿未覆盖，且是更优先的破口）

| # | 缺口 | 固定提交证据 | 为什么优先 |
| --- | --- | --- | --- |
| ① | **合并附注完全未接写入归属矩阵** | `note_write_ownership` 在 `consol_note_formula_service.py` / `consol_note_subtree_reaggregate.py` / `consol_note_detail_apply_service.py` / `consol_node_scope.py` **全部 0 命中**；`WriteGate` 只被 `disclosure_engine.py` 引用；合并附注的 6 个写入点（`consol_node_scope.py:327`、`consol_note_detail_apply_service.py:566`、`consol_note_formula_service.py:1022,1334`、`consol_note_subtree_reaggregate.py:720,736`）都在矩阵外 | 初稿把「明细映射 / 子树重汇总 / 公式填入 / 推送回写」写成「应维护」，读者会以为已做完；实际合并侧零覆盖，是格级写权治理的真实盲区 |
| ② | **合并附注保存端点无 CAS，且失败返回 HTTP 200** | `consol_note_sections.py:399-409` 的 `except Exception` 分支 `return {"ok": False, ...}`，状态码仍是 200；底层 `consol_node_scope.py:281-363` 只有 `SELECT ... FOR UPDATE`（`:305`）+ 唯一键冲突兜底（`:345-356`），**无任何 revision CAS 参数**（`expected_content_revision` 全仓 0 命中；`content_revision` / `If-Match` 在合并附注 6 个文件逐文件计数为 0） | 比「缺 CAS」更严重的是「失败被 200 掩盖」，前端与审计人员都会误判为已保存 |
| ③ | **树版本记录是 fail-open，推送不因它失败而停** | `consol_push_service.py:386-414` 整段包在 `try/except` + `begin_nested()`，失败只 `warnings.append(...)` 后 `return ""` 继续推送；同文件 `:448-450` 在 `worksheet()` 步骤内调用 | 「版本是溯源信息不是计算前提」是刻意设计，但后果是**推进了业务数据却没留下树版本**，正是初稿 §7.3 版本链最实际的破口 |
| ④ | **合并附注自动刷新默认关闭** | `config.py:313` `CONSOL_NOTES_V2_ENABLED: bool = False`；`consol_note_gray_service.py:27-59` 全局关时查项目级 `wizard_state.consol_notes_v2_enabled`，异常 fail-open 返 `False`；`consol_note_formula_refresh_handler.py:168-175` 未开启即整段跳过 | 初稿 §9 讨论事件自动路径时未写前置门控，读者会以为 `TRIAL_BALANCE_UPDATED` 一到就会刷新 |

附带一条口径修正：`consol_note_data_models.py:31` 的 `node_key` **可空**，`:59-73` 是「legacy 项目级行 + 节点级行」两套部分唯一索引，`consol_node_scope.py:269-278` 还有「节点行优先覆盖 legacy 行」的读取回退。初稿 §7.1 把 `node_key` 写成必填四维之一，与这个双轨现实不符，本版已在 §7.1 注明。

### 0.3 与既有裁决冲突的建议（须重新拍板才能实施）

初稿有两条「建议」会推翻既有拍板结论，本版保留但加注冲突标记：

1. **初稿 §3.2 P1-1 / P1-2「重复项目与关系冲突应阻断推送」**：现网是刻意的诊断制——`consol_group_tree.py:301-312` 对重复项目只产 `duplicate_project` 诊断并择一进树，`_make_entity` 的 `:233-240` 对单户/合并不一致只产 `relation_conflict` 诊断并按选定来源建树；计算门 `require_calc_year`（`consol_scope_confirmation_service.py:419-438`）**只校年度不校确认**，注释写明「V206 起替代『必须先确认合并范围』的计算门」。这来自 2026-10-27「范围确认门改年度校验 + 推送时自动记树版本」的拍板。改为阻断须重新拍板。
2. **初稿 §3.6 新增四类自指枚举**：在仍有 `SELF_TOP` / `SELF_ULTIMATE` 在用的前提下另起一套，等于制造文档自己反对的第二套口径。应改为扩展既有函数返回值域。

### 0.4 证据表勘误

初稿 §12 的 **E01 引 `consol_node_naming.py:54-64` 无法支撑「`node_key` 角色身份统一入口」**：`node_key()` 实际在 `:44-45`，54-64 覆盖的是 `display_name` 尾部 + `consol_label` + `__all__` 开头。本版已改为 `:16-45`（角色常量 + `node_key()`），并新增 E13～E16 承载 §0.2 的四项缺口证据。其余 11 项已逐项复核，起止行能覆盖其结论。

### 0.5 v3 复盘勘误（2026-11-11，立 spec 前按 HEAD `39777a020` 现读）

立 spec 前对 v2 结论逐条回到生产代码核对（`e25895b20..39777a020` 未改动任何合并相关后端文件，结论对两者同样成立）。v2 有 5 处判断过重或方向错误，**以本节为准**，正文相应位置已同步改写：

| # | v2 说法 | 现读事实 | 修正 |
| --- | --- | --- | --- |
| 1 | §0.2 ①、§7.6「合并附注格级写权零治理，4 个自动写入方无保护」 | 自动写入方**都有**保护：`consol_note_detail_apply_service.py:332-340`、`consol_note_formula_service.py:1278-1328`、`consol_note_subtree_reaggregate.py:495,548`、`consol_note_topn.py:266,387` 均跳过整节锁定、并保留 `manual_cells` / `locked_cells` 格 | 真实缺口是**三份解析实现口径不一**：`detail_apply._parse_manual_cells`（`:506-523`）遇坏项静默丢弃，`formula._manual_cells`（`:1102-1133`）遇坏项抛错，锁定格解析在公式路径另写一份（`:1325-1328`）⇒ 元数据损坏时明细映射 / 重汇总 / 前 N 名重排会静默覆盖人工格；另外没有写入方登记与守卫。**不应把单体 `WriteGate` 矩阵套到合并附注**（单体按 章节×表×字段 声明所有权，合并附注按 行列坐标 保护，数据模型不同） |
| 2 | §0.2 ②「失败返回 200，用户与审计都无法察觉」 | 主保存路径前端已检查：`ConsolNoteTab.vue` `performSaveNoteData` 遇 `ok === false` 抛错并提示 | 真实影响面：①Excel 批量导入路径（同文件 `api.put(importUrl, …)`）**不检查** `ok`，失败仍计入「已导入 N 个」②HTTP 层、操作日志与监控把失败记成成功。并发后写覆盖前写（无 CAS）仍成立 |
| 3 | §0.2 ③、P0-4「树版本记录失败只进 warnings，不可观测」 | warnings 随推送运行记录落库（`consol_push_service.py:557` `_finish_run` 写 `warnings`），operation 回执带 `warning_count`（`consol_operation_runner.py:202`） | 已可查，降为 P2（缺的只是结构化字段，不是可观测性） |
| 4 | §5.3 第 1 条、P1-4「附注映射确认的企业 hash 由调用方传入」 | 路由在调用服务前已按企业树与单体附注现读重建（`routers/consol_note_detail_templates.py:478-509` `scan_all_entities`，不符即 409） | 已实现，从待办中删除 |
| 5 | 未提 | `cell_state` / `locked_cells` 两列**全仓没有写入方**（前后端均无赋值，只有读取与 `detail_apply` 的行号重映射） | 「整节锁定 / 锁定格」目前是不可达能力；是否做锁定入口属产品决策，不在本轮 |

据此立 spec：`.kiro/specs/consol-note-save-integrity-closure/`（保存失败如实报错 + 保存内容摘要 CAS + 人工保护格解析单一来源 + 写入方登记守卫 + 自定义查询单格回写标手工格）。同轮另立两份：

- `.kiro/specs/consol-group-code-entry-consistency/`：三码 NFKC + 去空白 + 大写后校验、按规范值入库（前后端同一测试向量）；报错统一为「{字段}：{原因}」；向导改企业代码补 USCC 与唯一性校验；Excel 代码列文本格式、数字单元格与无缓存公式给出针对性提示、导出不再回退旧 hash；拖拽改上级带「改前上级」比较（**不用** `entity_group_fields_hash`：森林接口不提供算它所需的字段）。立 spec 时新发现：`consol_worksheet.py` 的 recalc / pivot / pivot templates 三个端点按查询参数鉴权、按请求体项目执行，属跨项目越权，一并修复并加 AST 守卫。
- `.kiro/specs/consol-status-semantics-closure/`：合并附注待更新加原因与时间（迁移 + 写入方守卫 + 页面显示）；重新汇总「全部为手工格」不再算已更新、全部失败时任务失败、合并页完成提示改用正确的摘要函数；推送附注步骤区分跳过原因，上下文构建失败记失败；抵销审批回执说明重算事件是否发出、入队失败可见；调整分录审批回执按试算表落账状态汇总，不暗示报表 / 附注已刷新。

2026-11-11 拍板（§10.1）：向导改企业代码须有新代码的建项授权；重复项目与关系冲突弹窗提示、不阻断；其余待拍板项按建议处理（树版本失败不阻断、不加 `AMBIGUOUS_SELF_REFERENCE`、就绪门不在服务端强制、企业代码有下游引用时拒绝修改并列出影响）。

经核对不做：回执 `tree_kind`（森林与合并树键格式不同，合并类接口都在服务端自建树，无误用路径）、树指纹加规则版本号（指纹由树的输出算出，规则变化即输出变化）。仍未纳入：树版本结构化、headless 后台化、全链路追溯与 worker 观测（需先与 `platform-heavy-jobs-and-capacity-closure` 划边界）。

### 0.5.1 consol-note-save-integrity-closure 实施复核（2026-11-12）

本节保留 v3 对立项前 HEAD `39777a020` 的历史判断；以下只记录该 spec 在当前工作区的实施后状态，不把未提交工作区的其他会话改动纳入结论。

| v3 缺口 / 本 spec 范围 | 当前状态 | 代码、测试与运行时证据 | 仍需如实保留的限制 |
| --- | --- | --- | --- |
| 保存异常返回 200、Excel 批量导入误报成功 | **已落地** | `backend/app/routers/consol_note_sections.py:459-478` 记录异常并返回 500 `CONSOL_NOTE_SAVE_FAILED`，不回显原始异常；`ConsolNoteTab.vue:2651-2762` 逐 Sheet/章节处理并汇总失败。后端保存/路由选集 127 passed；前端批量导入部分失败、全部失败和 PUT 5xx 不重试用例通过。 | 更宽的前端 ConsolNoteTab 选集仍有两个 HEAD 同样失败的异步用例，不能写成全量前端无失败。 |
| 合并附注人工保护格解析不一致、无写入方登记 | **已落地** | `backend/app/services/consol_note_protection.py:104-166` 提供严格单一解析；明细映射、公式填入、子树汇总、TopN 和自定义查询回写均已接入；`consol_note_writers.py:82-309` + `test_consol_note_writers_guard.py` 完成登记、双向 AST 对账和两类变异。后端选集通过。 | `cell_state` / `locked_cells` 仍无生产写入入口，这是本轮明确的非目标，不应写成“锁定设置已完成”。 |
| 保存无 CAS、并发后写覆盖前写 | **已落地** | `consol_node_scope.py` 的 `digest_of` / `NoteSaveConflict` / `save_scoped_note_record` 以及章节路由实现 428/422/409、赢家重读比较、来源投影和 `data_digest`；`test_consol_note_save_cas.py` 覆盖真实 ORM/ASGI 依赖链，前端定向 9 tests passed。 | 已迁入正文的 Task 7.3 对账摘要证明真实 PG 上带摘要修改与恢复一致；任务 7.1 的双标签冲突过程没有保留截图或响应拦截报告，不能只按 tasks 勾选宣称已独立复核。 |
| 自定义查询单格回写不标手工格 | **已落地** | `snapshot_writer_modules.py:198-255` 严格解析已有标记，数组行第 1 列起追加 `manual_cells`，第 0 列/字典行返回 `marked_manual=false` 与原因；`test_custom_query_note_writeback_manual.py` 走生产回写后再走生产公式填入并通过。 | 当前没有前端入口；虚拟列到真实表头的映射仍是 §6 用户决策，不因后端 API 已修而视为 UI 已开放。 |
| R5.1 浏览器与恢复对账 | **部分证据可复核** | Task 7.3 的正式 PUT、CAS 恢复、三阶段摘要和 PG 全字段对账摘要已内嵌于 §0.5.2；【测试】项目真实 PG 上的目标节点恢复一致，正式认证请求 5 次均 200，未捕获页面运行时错误。 | 该证据是 Task 7.3；7.1/7.2 的执行历史虽存在，但没有留存截图或拦截响应文件。当前没有把 gitleaks 写成通过：本轮未找到 gitleaks 执行记录。 |

#### 0.5.2 Task 7.3 正式 PUT 恢复对账摘要（2026-11-12）

本次执行记录已迁入本节。该记录只证明 Task 7.3 的真实 PostgreSQL 修改、恢复和对账，不替代 Task 7.1/7.2 的浏览器冲突与拦截响应证据。

- **对象范围**：测试项目 `【测试】公式同步集团有限公司_2025`（`project_id=3a3930db-3f14-431c-a919-913d04a23eca`），年度 `2025`，章节 `五-5-6`，节点 `9150000FGXUAT000P1:consol`；目标 `consol_note_data.id=41c48347-3b61-4c84-8b66-25e453e7dfaf`。
- **正式写入路径**：`PUT /api/consol-note-sections/data/{project_id}/2025/五-5-6?node_key=9150000FGXUAT000P1%3Aconsol`。修改与恢复均使用带 `expected_digest` 的正式 PUT；两次请求均未使用 `force_overwrite`。恢复载荷是 before GET 的完整 `content`，不是直接 SQL 或数据库强制覆盖。
- **可逆修改**：将 `data.rows[1][1]`（「1至2年」行的「期末余额/账面余额」列）从空字符串改为 `"7.00"`。修改 PUT 以 before 摘要为 `expected_digest`；恢复 PUT 以修改后摘要为 `expected_digest`，提交 before 的完整内容。

三阶段摘要为：

| 阶段 | `data_digest` |
| --- | --- |
| before GET | `0d97b8a4f7a7eb81e0b5ac23a81c24914c981bbe3fd5ac1432a3ddd2e59201fd` |
| 修改后 GET（after） | `b28e7a191b708877b92942442e1874c0ba9efb85f6a11588405d28231af7c130` |
| 恢复后 PUT / GET（restore） | `0d97b8a4f7a7eb81e0b5ac23a81c24914c981bbe3fd5ac1432a3ddd2e59201fd` |

恢复后 API 摘要、before PG `source_digest` 和恢复后 PG `source_digest` 逐值一致。PG 全字段对账中，`data` 深度比较无差集，行值、表头、`_last_write_source`、`_subtree_provenance` 和 `_subtree_child_count` 均恢复；`data.manual_cells` before/after 均为缺失/null，无差集。`locked_cells` 保持 `[]`，`cell_state` 保持 `auto`；`source_mode` 保持 `manual`，`source_operation_id`、`source_revision` 保持 `null`，`source_digest` 保持 before 摘要；`is_stale` 保持 `true`，`last_formula_run_id` 与 `last_formula_value` 保持 `null`。因此 data、manual、locked、source、stale 字段及 `id`、`project_id`、`year`、`section_id`、`node_key` 主键/范围字段均无差集；章节仍为 0 条 legacy 行 + 2 条节点行，另一节点未被触碰。

在最终 before/after 对账中，**唯一差异是 `updated_at`**：`2026-11-12T02:45:30.290274+00:00` → `2026-11-12T03:14:00.188810+00:00`，这是正式平台保存重新赋值的系统时间，不是内容差异。PostgreSQL 仅用于只读快照和对账，没有直接 SQL 写入；恢复没有使用 `force_overwrite`。浏览器正式认证请求为 before GET、修改 PUT、修改后 GET、恢复 PUT、恢复后 GET，5 次 HTTP 状态均为 **200**。操作前 2 条无 Bearer token 的故意认证探针返回 401，不属于正式操作路径；正式请求没有 401/4xx/5xx，也没有未捕获页面运行时错误。此次没有截图；观察到的 `amount_unit` 警告属于既有项目元数据问题，与保存恢复无关。

据此，Task 7.3 通过：业务 payload、摘要、人工/锁定元数据、来源字段、stale 状态和主键/范围均恢复一致，只有预期的 `updated_at` 系统时间变化；本次未修改源代码或 `tasks.md`。

本轮将 v3 的“未实现”结论收窄为：R1 保存失败可见性、R2 内容摘要 CAS、R3 保护解析/回写标手工格、R4 写入方登记守卫已在当前工作区实现并有后端/前端定向测试；树版本 fail-open、stale 状态语义、后台 headless、树身份和 Excel 代码列仍由原 review 或后续 spec 管理，不能因本轮完成而前移为已实现。

### 0.5.3 consol-status-semantics-closure 实施复核（2026-11-13）

本节是对 `consol-status-semantics-closure` 的追加复核，只更新原 review 的 P0-5、P1-6 与就绪门裁决；§0.5~§0.5.2 的立项前判断和前置 spec 收尾记录保持不变。依据本 spec `tasks.md` 的实现记录、定向回归记录和状态更新，未把尚未完成的 clean-HEAD 对拍、R270 回滚或浏览器证据写成独立验收通过。

| 条目 | 实际落地方式 | 证据与边界 |
| --- | --- | --- |
| **P0-5 审批成功 / 事件入队 / 任务完成 / 页面可见四态** | 抵销审批响应改为 `EliminationReviewResponse`，按发布结果返回 `recalc_trigger`：`event_published`、`event_failed` 或 `not_applicable`；发布失败附 `recalc_notice`。重算处理器入队失败经 `consol_push_failure_record` 写入失败的推送运行记录，并广播 `consol.push_failed`。调整分录批量审批回执保留逐笔 `tb_update_status`，增加 `downstream` 的发布数/失败数；前端按这些字段分别提示已审批、事件投递失败和下游刷新失败，不再把审批成功说成报表/附注已经完成。 | 后端落点为 `models/consolidation_schemas.py`、`routers/consolidation.py`、`services/consol_elimination_recalc_handler.py`、`services/consol_push_failure_record.py`、`routers/adjustment_review.py` 与 `services/adjustment_review_service.py`；前端落点为 `ConsolElimNodePanel.vue`、`worksheets/EliminationSheet.vue`、`useAdjustmentHallActions.ts`。`test_consol_elimination_review_response.py`、`test_consol_status_mutations.py`、`test_consol_status_r5_mutations.py` 及相关 Vitest 已覆盖三态回执、失败记录、`tb_update_status` 汇总和 `downstream.failed` 提示。代码与定向回归已有证据；浏览器拦截响应的独立最终证据仍按 tasks 状态保留为未闭合。 |
| **P1-6 stale、重新汇总与推送附注步骤如实报状态** | V270/R270 与 ORM 增加 `stale_reason` / `stale_at`；`consol_note_stale_state.py` 统一置位、清除和复制继承，章节 GET 与 `consol.note_stale` 载荷补齐原因，前端 `ConsolNoteStaleTag.vue` 显示待更新原因和时间。重新汇总以 `kept_manual` 区分“全部为手工格”，按 `computed_value` 统计差异，只有 `persisted` 计入更新章节，全部失败时执行器抛出业务错误。推送和级联刷新统一使用 `note_step_verdict`：`no_template_type`、`no_sections`、`no_tree` 记 skipped，`context_failed` 记 failed，不再把这些结果记为 succeeded。 | 后端/前端落点包括 `services/consol_note_stale_state.py`、`services/consol_push_notes.py`、`services/consol_note_subtree_reaggregate.py`、`services/consol_note_reaggregate_executor.py`、`ConsolNoteTab.vue` 与 `ConsolidationIndex.vue`；守卫和变异覆盖见 `test_consol_note_stale_writers_guard.py`、`test_consol_note_stale_state.py`、`test_consol_status_r1_mutations.py`、`test_consol_status_mutations.py`、`test_consol_phase2_cascade_pbt.py`。任务记录的本 spec 定向后端回归为 110 passed，5 个相关前端 Vitest 共 161 passed；共享 PG 已只读核对 V270 已应用且 checksum 一致。R270 回滚、完整 clean-HEAD 对拍及最终浏览器复测仍未闭合。 |
| **就绪门服务端强制的裁决** | **不在服务端强制可执行动作。** 保留既有七域五态就绪状态和前端按钮禁用；推送、重新汇总、operations 在未就绪时仍可由服务端受理，由页面按就绪条提示并禁用入口。 | 该裁决承接 2026-11-11 用户确认和 design §8：重复项目、关系冲突继续提示而不阻断，`require_calc_year` 仍只校年度；把就绪门变成服务端拒绝会把诊断提示升级成阻断，违反既有裁决。该决定不放宽登录/项目权限、CAS、锁、请求校验、事务原子性或失败留痕。 |

---

## 1. 范围、结论与证据边界

本文只对上述固定提交做只读静态审查，提出中文优化建议，不把当前工作区源码、其他会话改动或之后的提交当作事实基线。文中的源码证据统一使用 `[E01]`～`[E16]`，每项均指向固定提交；证据项总数为 16。

### 1.1 总体结论

固定提交已经形成了较完整的设计骨架：

- 企业树以企业代码、上级代码、最终控制方代码和与上级关系推导，节点身份用 `node_key` 区分企业角色，而不是只用企业代码或展示名称。三码自指的语义已由 `group_relation.effective_parent_code` / `self_reference_kind` 统一裁决，不是各入口自行比较字符串。
- 普通调整审批、抵销审批、outbox、operation、durable executor 和 worker 已有分层边界；业务提交、事件投递和任务终态并未简单混成一个事务。
- 合并附注已具备项目 × 年度 × 章节 × `node_key` 的节点隔离方向，并持久化 `stale`、手工/锁定状态、公式快照、来源投影和摘要。
- 公式刷新有明确事件边界：`TRIAL_BALANCE_UPDATED` 是金额变化的自动刷新入口，`ADJUSTMENT_APPROVED` 不直接重复订阅；显式离屏入口与事件驱动刷新是两条不同路径。
- 企业树版本已有服务端权威校验：`confirm_scope` 比对服务端现算 fingerprint 与 revision，不符返回 409；树由 `load_year_records` 按年度从 projects 表重建，不信任客户端结构。
- 附注写入归属已有成体系的治理设施：写入方登记表 + 五类 role + `WriteGate` 判定 + 生成式归属矩阵 + AST 守卫。

主要风险不在“完全没有实现”，而在于四类**尚未覆盖或覆盖不全**的具体缺口，以及跨入口一致性、真实数据库竞争、Excel 类型往返、跨进程恢复及前后端链路的运行时证据仍需补齐：

1. **合并附注人工保护格解析口径不一、写入方无登记**：自动写入方都保护人工格，但三份解析实现对坏元数据一份抛错、两份静默丢弃；没有写入方登记与守卫（§0.5 第 1 条、§7.6）。
2. **合并附注保存无 CAS，且失败返回 200**：并发下后写覆盖前写；主保存路径前端能识别失败，Excel 批量导入路径不能（§0.5 第 2 条、§7.4）。
3. **树版本记录 fail-open**：失败随推送运行记录的 warnings 落库、可查，但推送继续（§0.5 第 3 条、§7.3，降为 P2）。
4. **合并附注自动刷新默认关闭**：全局与项目级双开关默认关，事件到达也整段跳过（§0.2 ④、§9.2）。

建议按「先补齐这四项 → 再固化身份/版本/幂等契约 → 最后扩大自动刷新范围」的顺序推进。

### 1.2 本次静态审查能证明什么

静态代码可以证明：字段和节点身份如何计算、事务边界如何书写、哪些入口创建 operation、哪些事件注册 handler、哪些查询包含项目/年度/章节/节点条件、哪些地方使用 savepoint、租约和 revision 围栏，以及显式 headless API 的调用方式。

静态代码不能证明：真实 PostgreSQL 下的锁竞争和唯一键冲突、多个 worker 的接管时序、进程崩溃后的恢复、取消与重试的最终一致性、Excel 在不同版本客户端中的前导零往返、浏览器页面显示、API 全链路、构建产物新鲜度、Node 执行器可用性或生产数据分布。因此本文把这些内容列为验收矩阵，而不写成“已经通过”。

### 1.3 结论标签与证据等级

为避免把“源码存在”误读成“全链路已验收”，本文后续建议按以下语义阅读：

| 标签/等级 | 含义 |
| --- | --- |
| `[FACT]` / L1 | 固定提交源码或固定提交元数据直接可见的事实 |
| `[INFER]` / L2 | 由多个固定提交模块组合后可以合理推断，但未经过运行时证明 |
| `[GAP]` / L3 | 需要真实数据库、API、worker、浏览器或 Excel 验证；当前不能下通过结论 |
| `[REC]` | 面向后续实现或治理的优化建议，不代表固定提交已经具备 |
| L4 | 固定提交无法确认接线、产物或运行时行为，需先补证据再判断 |

本文原有“当前事实”段落按 `[FACT]` 理解；“建议”“应”“必须”均属于 `[REC]`；验收矩阵中的“未执行/部分通过/阻塞”属于 `[GAP]` 或运行时记录。对于同一主题，字段存在、写入方接入和最终用户可见必须分别验收，不能用前者替代后两者。

## 2. 固定提交中的当前链路事实

1. **[FACT/L1] 企业树层**：以同一年度、同一企业代码和报表口径分组，选择项目记录并输出重复诊断；再按上级/最终控制方关系生成实体图、断环和节点树。展示名称只是 UI 语义，`node_key` 才是数据身份。[E01][E02][E03]
2. **[FACT/L1] 映射与附注层**：映射规则带模板版本、来源结构 hash、版本号和绑定状态；结构变化可使绑定进入 `stale`。合并附注数据同时保存节点维度、单元格状态、公式快照、来源模式、operation、revision 和 digest。[E04][E07]
3. **[FACT/L1] 重汇总层**：请求先解析目标节点并校验项目、年度、树和 DAG；执行时拿处理锁/数据库 advisory lock，按后序处理节点，每章节使用 savepoint，汇总只读取直接下级已保存数据。[E05][E06]
4. **[FACT/L1 + INFER/L2] 审批与推送层**：普通调整审批按组隔离，提交后再发布下游事件；抵销审批独立请求持久 operation 并唤醒 worker。outbox 的入队与业务事务同一提交边界，worker 负责重放；这可以支持可靠投递方向，但重复业务副作用仍需运行时验证。[E10][E11]
5. **[FACT/L1 + GAP/L3] 公式与附注层**：试算表事件 handler 在独立会话中按节点刷新，保留已从单体附注拉入的数据并标记待更新；显式 `pull-from-workpapers` 与 `headless-refresh` 由用户入口触发，不能因为存在 API 就推断后台已经自动调用 Node 执行器。[E09][E12]

## 2.1 固定提交事实、推断、缺口与建议的阅读规则

为保持审查边界清晰，后文使用以下约定：

- **固定提交事实**：只描述在 `e25895b20b027422f5b2b1c8f2ce1b97bd5902bb` 中可直接定位的源码或元数据；不把当前工作区变更带入结论。
- **静态推断**：由多个模块的调用关系、字段和事务结构得到的合理判断；必须同时注明仍需什么运行时证据。
- **缺口/待验收**：静态代码无法证明，或需要真实 PG、API、worker、浏览器、Excel、Node、构建产物或生产数据才能判断的事项。
- **优化建议**：面向后续实现的目标状态，不代表固定提交已经完成。

同一事实不应重复写成“现状已经安全”。例如“有 `revision` 字段”只证明数据模型具备承载能力；只有证明全部 writer 都读写 CAS、冲突可观测且真实并发测试通过，才能称为“版本保护已闭环”。

## 2.2 不能作为通过依据的表象

以下表象不能单独作为验收通过依据：

- API 返回 200 不等于 worker 已完成；
- 创建 operation 不等于 operation 已被消费；
- outbox 有记录不等于消费者已经处理；
- `source_mode` 存在不等于每个格都有正确来源和唯一写入权；
- `is_stale=False` 不等于数据已经与最新来源一致；
- 页面能展示企业树不等于树可以正式推送；
- 存在 `headless-refresh` 路由不等于后台事件已经自动接线；
- 任务状态为 `success` 不等于业务副作用数量、摘要和节点范围正确；
- 单元测试通过不等于真实 PG 锁竞争、租约接管和唯一键冲突安全；
- Python 能读取 xlsx 不等于真实 Excel 客户端往返安全；
- revision 字段存在不等于所有 writer 都执行 CAS；
- 使用 `node_key` 的一个模块不等于全链路没有把 `company_code` 当成错误唯一键；
- worker 旧 owner 收到取消信号不等于外部文件、通知或 Node 子进程的副作用已经回滚；
- **保存接口返回 200 不等于数据已落库**：合并附注保存的非 `HTTPException` 异常走 `return {"ok": false}` + 200，静默失败（§7.4、[E14]）；
- **存在写入归属矩阵不等于所有写入方都受它约束**：`WriteGate` 目前只覆盖单体 `DisclosureNote`，合并附注四个写入方在治理域外（§7.6、[E13]）；
- **推送成功不等于企业树版本已记录**：`_record_tree_version` 失败只进 warnings，推送继续（§7.3、[E15]）。

## 3. 自动构树与三码归一：建议把“可计算身份”和“展示身份”彻底分开

### 3.1 当前设计的优点

固定提交已经把企业树的真源放在企业代码、上级代码、最终控制方代码和与上级关系上，并将 `parent_project_id` 作为派生值而不是树构建输入。企业代码相同但角色不同的节点，通过 `node_key = 企业代码:角色` 区分；合并户、差额户、母公司户、本部单体户和单体数据节点也有明确角色。

这避免了两个常见错误：

- 用展示名称作为主键，导致名称调整时历史数据迁移或错绑；
- 用 `company_code` 作为唯一节点，导致同一企业的合并户、差额户和单体户互相覆盖。

### 3.2 优化建议

**P0-1：统一三码规范化函数和错误分类。（部分实现，需补齐输出结构）**

`group_relation.effective_parent_code`（`:92-102`）、`_clean_code`（`:85-89`）和 `uscc_validator.validate_uscc`（`:19-45`）已经是共用的规范化与校验入口，`batch_project_workbook.parse_row`（`:247-297`）、`consol_group_tree._clean`（`:77-81`）、`group_links.reparent_project`（`:426-433`）都经这些函数判定，未各自 `strip()` 后另作比较。

仍缺的是**统一输出结构**：现网各入口只返回规范化后的值或布尔 + 中文消息，没有同时返回 `raw_value` / `normalized_value` / `validation_status` / 来源位置（文件行、列、项目 id、字段名）。建议给上述函数补一个结构化回执 DTO，让单建、批量预览、Excel 预览、树构建、关系变更共用同一形状；不要新写一套规范化函数。

**P0-2：服务端以项目年度为边界重建树，不信任客户端树和 `parent_project_id`。（已实现）**

已实现，不作为建议：`consol_group_tree.load_year_records`（`:726`）按年度从 projects 表重建记录集合，`build_entity_graph`（`:283-339`）在服务端完成代码归一、重复诊断、断环与最终控制方挂靠；`group_links.reparent_project`（`:419-433`）在每次改上级时先 `lock_topology_years` 再重新 `load_year_records` 判环，不接受客户端传树。

唯一可补的增量是「树版本包含规则版本」：现有 `confirm_scope` 的 fingerprint 已覆盖规范化后的三码与关系（`consol_scope_confirmation_service.py:99-115`），但未显式记录规则版本号，属 P2。

**P1-1：重复项目不能只“择一进入树”而无待处理门。（⚠️ 与既有裁决冲突，须重新拍板）**

现网行为是刻意的：`consol_group_tree.build_entity_graph` 对同企业代码同年度同报表口径的重复记录只产出 `duplicate_project` 诊断（`:308-312`），并在 `:304` 按 `(是否 preferred, id)` 排序后取第一条进树（`:305`），不阻断。这是 2026-10-27 拍板的「范围确认门改年度校验」方案的一部分——计算门 `require_calc_year`（`consol_scope_confirmation_service.py:419-438`）注释明确写着「V206 起替代『必须先确认合并范围』的计算门」，只校年度边界。

若采纳本建议把重复诊断提升为阻断门，等于恢复「必须先确认范围」的旧门禁。**须先请用户重新拍板**，并在实施时同步修改 `require_calc_year` 与该注释，否则文档建议与代码注释会长期互相矛盾。

**P1-2：同一企业的合并项目与单户项目关系冲突应阻断写入而非只提示。（⚠️ 同上，须重新拍板）**

现网同样只诊断不阻断：`consol_group_tree._make_entity`（`:227-240`）发现单户与合并的上级代码、关系或控制方不一致时 `flags.add("relation_conflict")` 并产诊断，然后按 `:214-222` 的既定来源规则（单体优先，缺则取合并）继续建树。

纳入阻断须与 P1-1 一并重新拍板。若最终决定保留诊断制，则应把 `relation_conflict` 提升到就绪门的 `warning` 或 `not_ready` 可见位置，让用户在推送前至少看到它——这属于 §5.2 就绪门粒度问题，不需要推翻裁决。

**P1-3：自动树与手工改上级必须使用同一 CAS。（部分实现：批量侧已有，拖拽侧缺失）**

- **批量侧已实现**：`batch_project_plan.py:409-411` 与 `batch_project_execution.py:624` 都用 `entity_group_fields_hash(entity_projects) != row.base_hash` 做关系基线校验，不一致即拒绝执行该行。
- **拖拽侧缺失**：`group_links.reparent_project`（`:399-473`）目前只有 USCC 校验（`:426-429`）、`would_form_cycle` 判环（`:430-433`）和 `lock_topology_years`（`:421`）；没有请求级基线摘要，后提交者会覆盖先提交者的结构修复。
- 建议范围因此收窄为：**给拖拽入口补一个与批量同口径的 `base_hash` 参数**（复用 `entity_group_fields_hash`），而不是给四个入口统一新造 `tree_version`。这样批量与拖拽天然同源，也不引入第二套摘要算法。

### 3.3 单建与批量规则统一

- 单建和批量都先进入同一份 `ProjectRecord`/规范化 DTO，再调用同一个图构建器；不要为批量另写一套“宽松导入树”。
- 预览与正式提交必须共享同一规范化、重复裁决、断环、最终控制方挂靠和诊断排序逻辑；预览返回的摘要 hash 由服务端生成，正式提交只接受该 hash 的未过期版本。
- 单建保存必须复用批量导入的逐字段错误结构，至少能定位文件行、列、项目 id 和字段名；批量失败不得静默把原值置空。
- 树版本与项目字段版本分开：项目字段 CAS 防止单条覆盖，树版本 CAS 防止跨项目批量结构覆盖。

### 3.4 合并范围树与集团架构森林：已在实现层分离，只缺回执标识

固定提交同时存在两种不同用途的树语义：合并树要求最终控制方具备集内合并项目；集团架构森林用于展示集团关系时，不要求控制方具备合并项目。

| 树类型 | 用途 | 是否要求控制方有合并项目 | 是否允许作为正式计算/推送输入 | 固定提交落点 |
| --- | --- | --- | ---: | --- |
| 合并范围树 | 合并试算、抵销、报表和附注重汇总 | 是 | 是，仍需通过业务层就绪门 | `consol_scope_members.tree_subsidiaries`（`:70`） |
| 集团架构森林 | 展示、导航、筛选和关系维护 | 否 | 否 | `group_forest.py`；`consol_tree_service.build_group_trees_from_projects`（`:220-238`） |

**[FACT/L1]** 两类树在实现层**已经是两套函数**，不是同一份状态被两处复用：`consol_group_tree._attach_by_ultimate`（`:355-362`）委托 `_controller_hosts(require_consol=True)`（`:342-352`），即合并树挂靠要求控制方有合并项目；而 `group_forest` 用的 `attach_to_controllers`（`:365-...`）明确「**不要求**控制方有合并项目」。因此初稿「必须分离」的表述已不成立，不列为待建项。

**[REC/P1]** 真正缺的只有**回执显式标识**：`tree_kind` 全仓 0 命中。建议在合并范围树的 API 回执与前端状态里带上 `tree_kind`（如 `consol_scope` / `group_forest`），让调用方无法把展示森林误当计算输入，而不是依赖「传的 id 是哪个接口来的」这种隐式约定。

### 3.5 企业代码更正与主体变更

`node_key` 以企业代码和角色组成时，企业代码更正会影响历史附注、合并范围、公式来源和审计轨迹。建议明确：

- 企业代码格式修正或录入错误更正，不等同于企业主体变更；应保留 `old_code → new_code` 的受控映射及理由；
- 企业主体变更应创建新的节点身份，禁止直接覆盖原历史 `node_key`；
- 历史年度默认继续使用当时的节点身份，新年度是否继承应经过明确迁移/映射；
- 附注映射、来源投影、operation 和交付件回溯必须能识别代码更正前后的身份关系；
- 代码变更审批、树版本变化和下游 stale 标记应是一个可追踪 operation，不能只更新项目表字段。

**[GAP/L3]** 固定提交静态范围没有验证代码更正、主体变更、历史年度迁移和 `node_key` alias 的完整策略；该事项应进入树身份迁移验收，而不是默认视为普通字段更新。

### 3.6 三码自指应落成确定性业务枚举（在既有枚举上扩展）

**[FACT/L1]** 固定提交已有一套自指枚举，不是空白：`group_relation.py:105-126` 定义 `SELF_TOP`（上级=本企业，集团顶层企业）与 `SELF_ULTIMATE`（三码相同，本企业即最终控制方），`SELF_REFERENCE_NOTICES`（`:108-111`）提供对应中文提示，`self_reference_kind`（`:114-126`）是唯一判定入口，`effective_parent_code`（`:92-102`）负责归一化返回 `None`。

初稿提出的 `SELF_ROOT`、`SELF_PARENT_NORMALIZED`、`INVALID_SELF_CYCLE`、`AMBIGUOUS_SELF_REFERENCE` 四类在固定提交中 **`SELF_ROOT` / `INVALID_SELF_CYCLE` 全仓 0 命中**，即并不存在；另起一套会与 `SELF_TOP` / `SELF_ULTIMATE` 并存，正是初稿自己在 §3.2 反对的「两套口径」。

**[REC/P0]** 因此本条改为在既有函数上**扩展返回值域**，而非新建枚举：

| 初稿分类 | 与既有枚举的关系 | 建议处置 |
| --- | --- | --- |
| `SELF_ROOT` | 已由 `effective_parent_code` 返回 `None` 表达，无需新枚举 | 不改，仅在回执里显式输出「已归一为无上级」这一诊断码 |
| `SELF_ULTIMATE` | **已存在同名枚举**（`:106`） | 复用 |
| `SELF_PARENT_NORMALIZED` | 是 `SELF_TOP` 的「原值自指 + 已归一」过程描述 | 复用 `SELF_TOP`，在诊断里额外带 `raw_value` |
| `INVALID_SELF_CYCLE` | 实际环由 `_break_cycles`（`consol_group_tree.py:253-...`，调用 `:327`）与 `would_form_cycle`（`group_links.py:430-433`）拦截 | 不需要新枚举；断环诊断已存在 |
| `AMBIGUOUS_SELF_REFERENCE` | **确实缺**：现网三码相同一律判 `SELF_ULTIMATE` | 只在业务确需「无法判断」时给 `self_reference_kind` 增加一个返回值 |

**结论**：真正需要新增的只有 `AMBIGUOUS_SELF_REFERENCE` 一种，且须挂在 `self_reference_kind` 上。其余四类要么已实现，要么已由别的机制覆盖。所有入口（单建、批量、Excel 预览、树构建、关系编辑）都应调用该函数并回传 `raw_value` / 归一值 / 分类 / 诊断码，这一条与 §3.2 P0-1 是同一件事。

## 4. Excel 模板往返与前导零风险

统一社会信用代码、上级代码和最终控制方代码必须按**文本**处理，不能按 Excel 通用数值处理。即使代码通常为 18 位，Excel 仍可能把其解析为数字、科学计数法或丢失前导零；空值、公式结果、带空格字符串和导入后重新导出的值也可能产生差异。

### 4.1 建议的导入/导出契约

1. 模板列明确设置为文本格式，并在模板说明中标记“代码字段不可改为数值格式”；导出时写入字符串单元格，必要时同时设置文本 number format。
2. 导入时保留原始单元格类型和值，先做类型诊断再规范化：数字、科学计数法、公式、错误值、前导零丢失和超过安全整数范围分别给出中文提示。
3. 对疑似被 Excel 数值化的代码，不要直接补零或猜测原值。若无法从原始文本恢复，应拒绝正式导入，只允许用户修正后重试。
4. 导入预览显示“原始值 / 规范化值 / 风险 / 处理建议”，并把每个代码的单元格坐标写入预览回执；正式写入保存模板文件摘要、导入批次和规范化规则版本。
5. 导出后再导入必须做 round-trip 检查：代码、空值、关系枚举、项目年度和报表口径逐字段比较；发现差异时报告差异，不自动覆盖数据库。
6. xlsx、xlsm 和 CSV 不应共用“按字符串读取”的假设。xlsm 需保留宏的专门路径；CSV 需约定编码、引号和前导零策略。上述格式差异必须进入验收矩阵。

### 4.2 前导零专项验收

至少准备以下样本：前导零代码、全数字代码、含字母的非法值、18 位边界值、科学计数法显示值、空值、公式返回文本、公式返回数字、带首尾空格值和重复代码。每个样本都应验证：预览值、错误码、数据库最终值、再导出值和再导入值。没有真实 Excel 客户端往返前，不能声称前导零风险已解决。

## 5. 三码相等确认、树校验与项目级 CAS

### 5.1 三码相等的语义（已实现，无需新建）

“三码相等”不能只比较未经规范化的字符串，也不能把“企业代码等于上级代码”直接判为环。固定提交已把这三类语义收敛到两个函数：

| 场景 | 固定提交落点 | 现网语义 |
| --- | --- | --- |
| `company_code == parent_company_code` | `group_relation.effective_parent_code`（`:92-102`） | 返回 `None`，视为「本企业就是上级企业」，不生成自环边；原值照存，用户回填时仍看到自己填的值 |
| `company_code == ultimate_company_code` | `group_relation.self_reference_kind`（`:114-126`） | 上级为空而控制方=本企业属常规集团顶层写法，不算自引用、不生成挂靠边 |
| 三码全相等 | 同上 | 返回 `SELF_ULTIMATE`，按「本企业即为最终控制方」处理，附中文提示 `SELF_REFERENCE_NOTICES`（`:108-111`） |

`effective_parent_code` 的注释已写明「树构建、关系默认、控制方补齐、批量预校验都经此判定，不各自比较字符串」，与初稿建议一致，故本条从 `[REC]` 改为 `[FACT/L1]`。

**唯一可补**：上表第三类目前仅返 `SELF_ULTIMATE` 并给提示，没有「无法判断是合法根还是录入错误」的第三态。若业务确需要该态，应在 `self_reference_kind` 的返回值域上**扩展**（见 §3.6），不要另起一套枚举。

### 5.2 树校验分层（分层已实现，缺的是粒度）

固定提交的校验已分四层，且各层都产出结构化诊断：

1. **字段层**：`batch_project_workbook.parse_row`（`:247-297`，USCC 格式、年度区间、关系枚举）+ `uscc_validator.validate_uscc`（`:19-45`）。
2. **实体层**：`consol_group_tree.build_entity_graph` 的 `duplicate_project`（`:308-312`）与 `_make_entity` 的 `relation_conflict`（`:227-240`）。
3. **图层**：`detached`（`:315-326`）、`_break_cycles`（`:253-...`，调用在 `:327`）、`_attach_by_ultimate`（`:355-362`，调用在 `:328`），以及 `group_links.would_form_cycle`（`:430-433`）。
4. **业务层**：`consol_readiness_service` 的七域就绪门（见下）。

**[FACT/L1]** 就绪门现网是**七域五态**，不是初稿建议的四态：`Status = ready | not_ready | unknown | not_applicable | warning`（`consol_readiness_service.py:28`），域为 `tree / worksheet / elimination / calc / report / note / lifecycle`（`:30`、`:148-156`）。附注域 `_note`（`:105-121`）已把 `stale_count`、`pending_mappings` 作为 blocker，并把「来源混合」降为 `warning`，正是初稿想要的粒度差异。

**[REC/P1]** 因此本条改为：**在既有七域五态上补粒度，不要新造 `preview_only` / `ready_for_mapping` / `ready_for_reaggregate` / `ready_for_push` 四态枚举**。具体可做的是给 `DomainReadiness` 增加「可执行动作白名单」字段（哪些动作在该域状态允许），让 `tree=not_ready` 时推送按钮与 API 都拒，而不是靠前端各页自行判断。这样不引入第二套状态机。

### 5.3 CAS 与确认回执（树确认已实现，附注映射与推送未全覆盖）

**[FACT/L1] 树确认已实现服务端权威校验**：`consol_scope_confirmation_service.confirm_scope`（`:317-350`）接收 `expected_fingerprint` 与 `expected_revision`，但**不信任它们**——先 `_load_state`（`:122-209`）现算 `fingerprint_payload`（`:115-120`）得到真实 fingerprint，再比对：

- fingerprint 不符 ⇒ 409 `SCOPE_FINGERPRINT_CONFLICT`「企业树已变化，请刷新后再记录」；
- revision 不符 ⇒ 409 `SCOPE_REVISION_CONFLICT`「企业树版本已变化，请刷新后再记录」。

版本落库为 `ConsolScopeConfirmation`（`consol_scope_confirmation_models.py:18-73`）：`revision` 唯一约束、`fingerprint` 长度校验、partial unique index 保证同项目同年度同口径只有一条 `active`、`confirmation_mode ∈ user|auto`、`confirmed_by` 可空（auto 记录无触发人）。这已覆盖初稿要求的「请求摘要、输入版本、树版本、操作者、确认模式、结果版本」。

**仍缺的三处（本条保留为 `[REC]`）**：

1. **附注映射确认**：`consol_note_mapping_rule_service.confirm_mapping`（`:194-230`）有 `source_structure_hash` 与 `template_version_id` 校验、409 `TEMPLATE_VERSION_CONFLICT`，但 `current_entity_hashes` 是**调用方传入**（`:207`），服务端不重新计算全部企业当前 hash ⇒ 与树确认不同源。
2. **推送确认**：`consol_push_service._record_tree_version`（`:386-414`）记录失败只告警（见 §0.2 ③、§7.3）。
3. **合并附注内容保存**：完全无 revision CAS（见 §0.2 ②、§7.4）。

## 6. 四表 → 底稿 → 报表 → 附注 → 公式链路

### 6.1 建议采用“事件事实 + 读取投影 + 显式重建”三层模型

固定提交已经把金额变化的自动入口收敛到 `TRIAL_BALANCE_UPDATED`，并在附注刷新 handler 中区分来源行、公式值和 stale 状态；这比每个页面各自监听审批、保存和刷新事件更容易保持一致。[E08][E10][E12]

建议将全链路明确为以下五层：

1. **四表事实层**：四表录入、调整或审核产生可追溯的业务事实，记录项目、年度、底稿、科目/行身份、变更版本和操作者。
2. **试算表发布层**：只有显式发布门把审定结果写入试算表；普通审批成功本身不等于所有下游金额已完成刷新。发布回执需要包含受影响的项目、年度、账户范围和事件 id。
3. **底稿/报表计算层**：底稿取数、报表生成和审定表计算使用统一年度、节点和科目身份；失败时保留原因和输入版本，不把缺数默认为零。
4. **附注投影层**：附注按章节、表、行和格保存来源投影，公式值、手工值、锁定值和 stale 状态分开表达；不能用章节级来源标签推断每个格的写权限。[E04]
5. **公式刷新与交付层**：公式推送、附注刷新、交付件生成分别有 operation/任务回执；“事件已产生”“任务已入队”“任务已完成”“页面已读到新值”必须是四个可观测状态。

### 6.2 事件去重与依赖顺序

- `ADJUSTMENT_APPROVED` 只表示审批事实已确认；如该来源需要进入试算表，应由显式发布流程产生 `TRIAL_BALANCE_UPDATED`，避免审批和金额事件分别触发两次公式刷新。
- `TRIAL_BALANCE_UPDATED` 的事件 payload 应带项目、年度、影响范围、源 revision 和幂等键；下游 handler 先检查输入版本，再决定跳过、标 stale 或重算。
- 底稿刷新完成后才允许将依赖它的附注公式投影标为 `fresh`；如果底稿部分失败，附注应保持 `stale` 或 `blocked`，不能以“任务有成功项”覆盖整节状态。
- 报表与附注读取应使用同一个节点范围快照；树版本变化时，旧任务不得把旧节点结果写入新树。任务回执应保存 `tree_version` 与 `source_revision`。
- 四表、试算表、底稿、报表和附注的每一步都应有可追踪的 `operation_id`/`event_id`，并能从附注格反查上游写入事实。当前静态审查只能确认部分 operation 和来源字段存在，不能证明每条生产路径都完整携带这些字段。[E04][E08][E11]

### 6.3 建议补一条端到端一致性不变量

对同一项目、年度、树版本和节点范围，若输入版本未变化，则重复执行全链路必须满足：

- 业务金额、附注公式值、来源 revision 和输出摘要不变化；
- operation、outbox 和任务状态只增加幂等命中记录，不重复产生业务行；
- 手工格、锁定格和已确认的单体拉数格不被自动刷新覆盖；
- 任一步骤失败时不产生“下游 fresh、上游失败”的错误组合；
- 切换到新树版本后，旧任务最多被标为过期/拒绝，不能写入新节点身份。

## 7. 合并附注四维显示、版本和 CAS

### 7.1 四维显示模型

合并附注页面建议把以下四个维度作为显式上下文，不依赖页面局部变量或列标题猜测：

| 维度 | 作用 | 必须进入请求/回执 |
| --- | --- | --- |
| 项目 | 确定权限、数据范围和锁域 | `project_id` |
| 年度 | 确定期间、上期和模板版本 | `year` |
| 章节 | 确定映射规则、表结构和刷新范围 | `section_code`/章节标识 |
| `node_key` | 确定合并户、差额户、母公司户或单体节点 | `node_key` |

列表、详情、保存、拉数、重汇总、公式刷新和导出都应回显这四个维度。任何一个维度缺失都应返回可识别的参数错误或“无法确定上下文”，不能退回到“最近一次记录”或默认节点。

**[FACT/L1]** 上表第四维有兼容双轨，不能按“必填四维”实现：`consol_note_data_models.py:31` 的 `node_key` **可空**（`String(100), nullable=True`），`:59-73` 是两套部分唯一索引——`uq_cnd_legacy_project_year_section`（`node_key IS NULL`，项目级兼容行）与 `uq_cnd_project_year_section_node`（`node_key IS NOT NULL`，节点级行）。读取侧 `consol_node_scope.py:264-278` 在 `node_key` 为空时按 `IS NULL` 过滤，且根合并节点允许 legacy 行作基线、由节点行优先覆盖（`:269-278`）。

因此四维模型的正确表述是：**新写入必须带 `node_key`；读取要兼容 `node_key IS NULL` 的 legacy 行**。若把 `node_key` 做成非空或必填，会打断 `save_scoped_note_record`（`:315-338`）「根节点首次写入从 legacy 复制基线」的逻辑。

### 7.2 章节级来源与格级所有权分离

固定提交的数据模型同时保存 `source_mode`、`cell_state`、`locked_cells`、`last_formula_value`、来源 operation、revision 和 digest。建议继续保持两层语义：

- **章节级来源**回答“本节主要由哪条链路产生”；
- **格级所有权**回答“这一格当前能否被哪类自动写入方覆盖”。

因此，显示层至少应区分：公式自动值、单体拉数值、子树汇总值、手工值、锁定值、待更新值、冲突值、缺少来源和任务失败。不能只显示一个“来源：底稿/手工”标签就允许自动覆盖整节。

### 7.3 版本、摘要与 stale

映射绑定应将模板版本、来源结构 hash、版本号和绑定状态作为一个版本组处理。结构变化、表头变化、行身份变化、树版本变化或来源 revision 变化，都应使相应绑定或格状态进入待确认/过期状态，而不是默默套用旧坐标。[E03][E04][E07]

建议保存以下最小版本链：

- `tree_version`：企业树输入与规则版本；
- `template_version`：合并附注结构版本；
- `mapping_version`：章节/表/行/格映射版本；
- `source_revision`：底稿或公式来源版本；
- `content_revision`：当前附注内容版本；
- `operation_id` 与 `source_digest`：本次写入及其内容摘要。

版本比较必须由服务端读取真实数据后完成。客户端携带的 `source_structure_hash`、当前格 hash 或 node 列表只能用于提前提示，不能成为唯一安全边界。

**[GAP/L3 + FACT/L1] 树版本记录是 fail-open，是版本链最实际的破口。**

`consol_push_service._record_tree_version`（`:386-414`）把 `record_scope_version` 整段包在 `try/except Exception` + `db.begin_nested()` 里：失败只 `logger.warning` + `warnings.append(...)` 后 `return ""`，推送继续执行；`_push_one`（`:448-450`）在 `worksheet()` 步骤最先调用它。

Docstring（`:395-398`）明确解释这是刻意设计——「版本是溯源信息，不是计算前提」。后果是：**合并数、试算表、报表都被推进了，但企业树版本可能没留下**，且用户只看到一条 warning。初稿把 `tree_version` 列为最小版本链第一项，却没点出它自己就可能缺失。

**[REC/P0]** 二选一，需明确拍板：

- **方案 A（保 fail-open，但可观测）**：`record_scope_version` 失败时把 `tree_status=failed` + 原因写入推送 operation 回执与就绪门 `tree` 域，让「无版本」成为可查询状态，而不是只留在 warnings 数组里。
- **方案 B（改为阻断）**：只有确实需要「无版本不得推送」时才改；但这会推翻上述 docstring 的既有裁决，须重新拍板并同步改注释。

若维持现状不改代码，至少应把 §11 的 A14/A21 加上「推送后必须能查到本次 tree_version 或明确的记录失败原因」这条断言。

### 7.4 CAS、并发写入与重试（合并附注当前完全没有 CAS，且失败返回 200）

**[FACT/L1] 保存端点无任何 revision CAS。** 在合并附注链路的 6 个文件（`consol_note_sections.py` / `consol_notes.py` / `consol_node_scope.py` / `consol_note_formula_service.py` / `consol_note_subtree_reaggregate.py` / `consol_note_detail_apply_service.py`）中，`expected_content_revision` / `content_revision` / `If-Match` **逐文件计数均为 0**；其中 `expected_content_revision` 在 `backend/` 与前端 `src/` 全仓也是 0 命中（`content_revision` 在其他域有 61 个文件在用，属底稿/调整等模块，与合并附注无关）。`consol_node_scope.save_scoped_note_record`（`:281-363`）的并发保护只有两层：

1. `_load_exact_note_record(db, scope, for_update=True)`（`:305`）——`SELECT ... FOR UPDATE` 行锁；
2. `IntegrityError` 兜底（`:345-356`）——唯一键冲突后重查 winner 并把数据写进去（`:358-360`）。

两层都是「后写者赢」：先提交者的内容被完全覆盖，不会返回冲突，也不会告知调用方丢了谁的改动。

**[FACT/L1] 更严重的是失败被 HTTP 200 掩盖。** `consol_note_sections.py:399-409`：

```python
try:
    await _save_note_record(db, scope, payload, now=now)
    await db.commit()
    return {"ok": True, ...}
except HTTPException:
    await db.rollback(); raise
except Exception as e:
    await db.rollback()
    return {"ok": False, "error": str(e), "node_key": scope.node_key}   # ← 状态码 200
```

任何非 HTTPException 的失败（DB 断连、序列化错误、flush 失败）都会返回 **200 + `{"ok": false}`**。前端若只看状态码，会显示保存成功；审计人员也无从判断哪些格其实没落库。

**[REC/P0]** 按优先级：

1. **先把失败改成非 2xx**：`except Exception` 分支改为 `raise HTTPException(500, ...)`（或 503），保留错误码便于前端区分。这是最小改动、最高收益。
2. **再补 CAS**：保存请求带 `expected_content_revision`；服务端在 `FOR UPDATE` 之后、写入之前比对当前 `revision`，不匹配返回 409 + 冲突格清单。现网模型没有 revision 列（`consol_note_data_models.py:27-52` 只有 `updated_at` / `source_revision`），需新增列或复用 `source_revision`。
3. **完整事务序列**（2 落地后）：锁定目标项目/年度/章节/节点的版本行 → 重读 revision / stale / 锁定格 / 写入所有权 → 手工与锁定格字段级合并、自动格按来源 revision 判定可否覆盖 → 版本匹配才写入并递增 revision，冲突返回 409 及冲突格清单 → **提交后**才发布刷新事件或 outbox，不能在回滚后留下「已发布」假象。
4. 若同时涉及来源投影，还应带 `expected_source_revision` 与 `tree_version`。

重汇总已经按节点后序、章节 savepoint 和直接下级已保存数据执行；建议把每个章节的输入节点集合、跳过原因、写入格数、冲突格数和输出 digest 写进 operation 回执，便于区分“没有下级数据”“下级失败”“被手工锁定”和“实际写入零格”。[E05][E06]

### 7.5 stale 的用户语义

`stale` 不应只有布尔值。建议至少区分：`source_changed`、`mapping_changed`、`tree_changed`、`formula_failed`、`manual_conflict`、`job_cancelled` 和 `unknown`。页面应显示触发来源、发生时间、旧/新 revision 和可执行动作：重新拉数、重新汇总、查看冲突、保留手工值或确认覆盖。固定提交已能按绑定、章节号或标题匹配受影响章节并广播 stale；下一步是把原因和版本差异做成用户可解释回执。[E07]

### 7.6 附注写入方与格级权限矩阵（单体侧已落地；合并侧有格级保护但无登记守卫）

> **v3 勘误**：本节下文「合并侧零覆盖」「另外四个合并侧写入方都没有格级写权判定」的表述**不成立**，以 §0.5 第 1 条为准。合并侧 4 个自动写入方都跳过整节锁定并保留 `manual_cells` / `locked_cells`；缺的是解析口径统一与写入方登记守卫。下表「合并侧现状」列的「未接 `WriteGate`」只说明没有接单体矩阵，不代表没有保护；P0-2 改为在合并侧建自己的保护 helper 与写入方登记，不复用单体矩阵。

章节级 `source_mode` 不能替代格级写入权。**[FACT/L1] 固定提交已有一套完整治理设施，不是空白：**

| 组件 | 固定提交落点 | 作用 |
| --- | --- | --- |
| 写入方登记表 | `backend/app/services/note_writers.py:85-128` | 40 个 writer 的入口、触发点、可写字段、是否尊重格模式、事务模式 |
| 五种 role 分类 | `note_writers.py:19-36` + `:17` `ROLES` | `automatic` / `manual` / `derived` / `structural` / `stale`，决定是否受矩阵约束 |
| 判定内核 | `note_write_ownership.py:166-200` `WriteGate.check` | 判定顺序：locked → manual → 推送只写声明格 → 域外放行 → 容器 → 推送写定格 → 基础条目 |
| 归属矩阵（生成物） | `backend/data/note_write_ownership_matrix.json` | 按 `(template_type, note_section, table_key, field_key)` 声明唯一自动写方 |
| 生成器 | `backend/scripts/gen/gen_note_write_ownership_matrix.py` | 矩阵由脚本生成，不手改 |
| 拒绝回报 | `note_write_ownership.py:7-8`、`blocked_writes` | 所有权类拒绝记结构化日志 `note_write_blocked` 并回报；locked/manual 不进回报（`:47-48` `_SILENT_CODES`） |
| AST 守卫 | `note_writers.py:7` 注释声明「入口必须经 WriteGate 判定（守卫 AST 检查）」 | 防止 automatic writer 绕过判定 |
| 前后端对拍 | `audit-platform/frontend/src/utils/noteWriteOwnership.ts:8-9` + `noteWriteOwnershipParity.spec.ts` | 前端 `MANUAL_TAKEOVER_ADVICE`（`:9`）与后端 `reason_text` 同一句（`note_write_ownership.py:36-37`） |

**[FACT/L1 + GAP/L2] 但治理对象只覆盖单体 `DisclosureNote`，合并附注 `ConsolNoteData` 完全在矩阵之外。** 核对依据：

- `WriteGate` / `note_write_ownership` 在合并附注四个核心模块**全部 0 命中**：`consol_note_formula_service.py`、`consol_note_subtree_reaggregate.py`、`consol_note_detail_apply_service.py`、`consol_node_scope.py`。
- `WriteGate` 的唯一生产引用是 `backend/app/services/disclosure_engine.py`。
- 合并附注有 **6 个 `ConsolNoteData(` 写入点**，全部不经矩阵：`consol_node_scope.py:327`（用户保存）、`consol_note_detail_apply_service.py:566`（明细映射）、`consol_note_formula_service.py:1022` 与 `:1334`（公式填入 / 累积）、`consol_note_subtree_reaggregate.py:720` 与 `:736`（子树重汇总）。

也就是说：初稿下表列的五个写入方里，**只有「用户手工保存」通过 `save_scoped_note_record` 有锁定格/深拷贝保护（`consol_node_scope.py:307`），另外四个合并侧写入方都没有格级写权判定**。

| 写入方 | 可写范围 | 不可覆盖 | 失败处理 | 版本条件 | 合并侧现状 |
| --- | --- | --- | --- | --- | --- |
| 明细映射 | 已确认的明细映射格 | 手工格、锁定格 | 逐格结果 + 章节 savepoint | mapping/source revision | **未接 `WriteGate`** |
| 子树重汇总 | 汇总格、差额格 | 手工格、锁定格 | 章节回滚并保留原因 | tree/source revision | **未接 `WriteGate`** |
| 公式填入 | 公式拥有格 | 手工格、锁定格、域外格 | 保留缺数/错误原因 | formula/source revision | **未接 `WriteGate`** |
| 用户手工保存 | 被授权的手工格 | 锁定格、权限外格 | 409 + 冲突格清单 | content revision | 有行锁+深拷贝，无 CAS |
| 推送回写 | 明确登记的推送拥有格 | 人工覆盖格、域外格 | operation 失败且不清 stale | source revision | **未接 `WriteGate`** |

**[REC/P0]** 优先做，顺序不能颠倒：

1. **先把矩阵扩到合并附注模型**：`note_write_ownership_matrix.json` 与 `parse_matrix`（`note_write_ownership.py:83-93`）目前按 `(template_type, note_section, table_key, field_key)` 四元组索引，合并附注需要能表达「同一章节在合并模板下由谁写」。不加这一层，`WriteGate` 即使被调用也判不出来。
2. **再逐个给合并侧四类写入点接 `WriteGate`**，每接一个就加一条守卫断言（照 `note_writers.py` 的 AST 守卫范式）。
3. **不要新建第二套矩阵**：扩展现有生成器与 `WriteGate`，否则会出现单体/合并两套判定、同一格两个结论。

仅在完成 1、2 之后，初稿那句「存在绕过 helper 的裸 ORM/SQL 写入时不能判为闭环」才成立；按现状，合并侧**全部**都是绕过状态。

### 7.7 stale 状态机与局部失败聚合

`stale` 原因枚举还需要明确状态转换和任务聚合规则。建议采用最小状态机：

```text
fresh
  ├─ source_changed  → stale
  ├─ mapping_changed → blocked
  ├─ tree_changed    → stale
  ├─ formula_failed  → failed
  └─ manual_conflict → conflict

stale    → refreshing → fresh | failed | superseded
blocked  → remapped   → refreshing
conflict → resolved   → fresh
```

每个转换需定义触发方、是否需要用户确认、是否允许重试、是否可回滚以及保留的历史版本。章节结果聚合建议至少区分：

| 章节结果 | 整体任务状态 |
| --- | --- |
| 全部成功 | `success` |
| 成功 + 可重试失败 | `partial_retryable` |
| 成功 + 永久失败 | `partial_failed` |
| 全部跳过 | `skipped`，不能直接算成功 |
| 没有输入 | `no_input` |
| 被手工/锁定保护 | `protected` |
| 被取消 | `cancelled` |
| 输入版本已过期 | `superseded` |

**[REC/P1]** 禁止用 `failed == 0` 或 HTTP 200 代替任务成功判定；“零写入但全部受保护”应是 `protected`/`no_op`，不能伪装成刷新成功。

## 8. 审批、outbox、抵销 operation、幂等与 worker

### 8.1 普通调整审批

固定提交的普通调整审批在服务层按组执行并使用局部 savepoint，路由提交业务事务后再发布待投递事件；这有利于避免事件消费者读到尚未提交的审批结果。[E10]

建议补强以下契约：

- 审批结果、审批人、审批时间、输入 revision 和受影响范围必须在同一业务提交中落库；
- `publish_pending` 失败不能把审批回滚成未审批，但必须形成可查询的 outbox/投递失败状态；
- “审批成功”接口回执应明确是业务提交成功，还是事件已经被消费者处理成功；
- workpaper 来源若必须经过显式发布门，前端和 API 都应显示“等待发布”，不能误显示为已同步；
- 同一 review group 的重复通过、撤回与重试必须使用稳定幂等键，不能按请求时间生成新的业务事件。

### 8.2 抵销审批与 operation

固定提交把抵销审批后的重算放在独立 handler 中，由 handler 新建推送 operation，提交后唤醒任务；因此它与普通调整“审批后发布事件”的路径不是同一个事务模型。[E11]

建议在接口契约中显式返回：

- `approval_revision`：抵销审批事实版本；
- `operation_id`：本次重算/推送 operation；
- `idempotency_key`：请求方重试使用的稳定键；
- `queued_at`、`started_at`、`finished_at` 和当前状态；
- 受影响的合并项目、年度、树版本和节点范围。

审批事务与 operation 创建之间若发生异常，应允许“审批已提交、operation 待补偿”这一可观测状态；不能返回 500 后让调用方无法判断是否已审批，更不能通过重复点击创建多个等价 operation。

### 8.3 Outbox 幂等与投递

建议为 outbox 建立业务唯一键，例如“事件类型 + 项目 + 年度 + 源 revision + 影响范围摘要”，并把 payload schema version 一并保存。消费者侧以业务幂等键或事件 id 做去重，处理结果保存为成功、可重试失败、永久失败和已跳过；只依赖消息队列至少一次投递不能保证业务不重复。

outbox 事务测试应覆盖：

1. 业务提交失败：审批和 outbox 都不可见；
2. 业务提交成功、发布进程退出：outbox 可被 worker 接管；
3. 同一事件重复投递：只产生一次业务写入；
4. 消费成功后回执提交失败：重放仍不重复；
5. payload 版本不兼容：进入人工处理/永久失败，不静默丢弃。

### 8.4 Durable worker、租约和取消

固定提交的 platform job service/worker 已经包含 claim、heartbeat、lease、revision/owner 围栏、失败重试和取消路径；`CancelledError` 不直接写失败终态，租约失效后可以由其他 worker 接管。[E12]

建议继续强化：

- lease token 必须不可预测并绑定 job、attempt、worker owner；任何进度、成功、失败或取消写入都再次校验 token 和 revision；
- heartbeat 失败后，旧 worker 不得继续提交业务副作用；业务写入和任务终态应使用同一围栏；
- 取消要区分“已请求”“执行器已停止”“副作用已回滚”“不可回滚的外部副作用”；不能把收到取消信号直接显示为已取消完成；
- 每次 attempt 保存输入摘要、代码/规则版本、开始和结束时间、租约 owner、重试原因和异常分类；
- 任务恢复必须能从最后一个安全提交点继续，或明确从头重跑；不能依赖进程内内存状态；
- 任务完成后应有结果校验，例如输出 digest、写入数量、跳过数量和受影响节点集合，防止“终态成功但写入零行”被误认为正常。

## 9. Headless 显式入口与后台自动触发边界

固定提交提供 `headless-refresh` 显式 HTTP 入口，公式刷新 handler 也有事件驱动路径；静态代码只能确认这些入口和 handler 的存在，不能证明后台 Node 执行器已经被事件自动触发或在生产构建中可执行。[E08][E09]

建议把三条路径分开建模和验收：

### 9.1 用户显式路径

`POST /api/disclosure-notes/{project_id}/{year}/headless-refresh` 应返回 operation/job 回执，而不是只返回“已触发”。请求需包含章节或范围、树版本、来源 revision、幂等键和是否允许覆盖手工/锁定格。服务端必须再次检查项目权限、年度和当前树版本。

### 9.2 事件自动路径（受两项默认关闭的门控约束）

四表/试算表/底稿事件产生后，由平台任务或 outbox 消费者创建离屏刷新任务。必须在事件注册表、任务创建点、worker executor、Node 构建产物和结果回写处分别设置观测点。只有真实产生并完成一条事件驱动任务，才能把“后台自动刷新”标为已验收。

**[FACT/L1] 这条路径现在默认是关的，且有两道门，初稿未提。**

1. **项目级开关（默认关）**：`config.py:313` `CONSOL_NOTES_V2_ENABLED: bool = False`；`consol_note_gray_service.is_consol_note_v2_enabled`（`:27-59`）逻辑是「全局 True ⇒ 直接 True；否则查 `project.wizard_state.consol_notes_v2_enabled`（默认 False）；任何异常 fail-open 返 False」。开关读写端点为 `backend/app/routers/consol_notes.py:250-328` 的 `/{project_id}/config/consol-note-gray`（读 `require_project_access("readonly")`，写 `edit`）。
2. **handler 内二次判断**：`consol_note_formula_refresh_handler.py:168-175` 在新建独立会话（`:167`）后先 `is_consol_note_v2_enabled`，未开启就 `skipped.append({"reason": "项目未启用试算表事件自动刷新合并附注"})` 并整段返回。

3. **还有一道「归口短路」**：同文件 `:177-200`，若本次项目年度下 `stale_count == 0` 且 `note_total > 0`，认为推送内联 `_refresh_notes` 已刷完，直接跳过，避免审批 → push → TB 事件 → handler 的双重刷新。

因此「事件一到就自动刷新」在默认配置下**不成立**：需要全局或项目级开关打开，且当时确实存在 stale 行。

**[REC/P0]** 验收 A18 必须写明前置条件三件事：开关已开、存在 stale 行、以及确认短路逻辑没有把该次刷新吞掉。否则会出现「跑了事件、页面没变、也没报错」的假阴性，被误判成链路断裂。

### 9.3 前台刷新与后台刷新互斥

同一项目、年度、章节、节点和来源 revision 的前台 headless 请求与后台任务应共享幂等键/任务键，后到请求复用在途任务；不能因为浏览器点击和事件同时到达而重复写入。前端刷新按钮应显示“已排队/执行中/完成/失败/冲突”，不能用请求返回 200 直接显示为数据已更新。

**[FACT/L1] 前台 headless 当前是同步执行，不是任务回执。** `note_headless_refresh.py:9` docstring 明写「同步执行、跑完才返回（全部刷新实测几十秒级），上限 `RUN_TIMEOUT_SECONDS`。期 3 改为事件触发的后台任务（platform_jobs）」，`:47-48` 还先 `await db.commit()` 结束门禁事务再跑，避免长时间占连接。状态码映射（`:26-31`）为 409 busy / 503 跑不起来 / 504 超时 / 502 执行器错。

所以 §9.1 的第 1 条建议（返回 job 回执而非「已触发」）是**按现状不必改**：它现在返回的就是逐章节执行结果。真正需要补的是 §9.2 的后台化，以及本节的前后台互斥键——因为同步前台与后台任务并存时才需要互斥。

### 9.4 构建与运行时边界

Node headless 执行器必须有独立构建检查：源文件摘要、别名解析、依赖版本和 `dist/source-manifest` 一致；运行时要在真实后端配置下验证子进程启动、超时、取消、退出码、stdout/stderr 和结果 JSON。没有这些证据时，本文只把 headless 记为“存在显式入口，后台自动触发未证实”。

## 10. 优先级与实施顺序

优先级按 v2 复核后的真实状态重排：**先把「已有一套但漏了合并侧」和「假成功」修掉**，再做增量能力。

| 优先级 | 建议 | 当前状态 | 原因 | 验收出口 |
| --- | --- | --- | --- | --- |
| P0-1 | 合并附注保存失败改为非 2xx；批量导入逐表回报失败 | **未实现**（`consol_note_sections.py:399-409` 返 200；导入路径不检查 `ok`） | 导入失败仍报成功；HTTP 层与日志把失败记成成功 | 注入写库错误后返回 5xx，导入回执列出失败章节 |
| P0-2 | 合并附注人工保护格解析单一来源 + 写入方登记守卫（**不复用单体 `WriteGate` 矩阵**，见 §0.5） | **部分实现**（各写入方已保护，解析三份口径不一，无登记） | 元数据损坏时部分写入方静默覆盖人工格；新增写入方可能漏保护 | 坏元数据下所有自动写入方一致拒写并回报；未登记写入方守卫打红 |
| P0-3 | 合并附注保存补 CAS（按内容摘要比较，不加迁移） | **未实现**（无任何 revision 参数） | 并发下后写覆盖前写且不报冲突 | 两客户端并发保存，后者收 409，本地编辑不丢 |
| P0-4 | ~~树版本记录改为可观测~~ → 降为 P2（见 §0.5 第 3 条） | **已可查**（warnings 落推送运行记录） | — | — |
| P0-5 | 明确审批成功 / 事件入队 / 任务完成 / 页面可见四态 | 部分实现（`adjustment_review.py:163-192` 已分离）；**已立 spec `consol-status-semantics-closure`**（抵销回执 `recalc_trigger`、入队失败写失败运行记录；调整回执按 `tb_update_status` 汇总） | 避免前端与审计误判链路已完成 | API 回执与页面能区分四种阶段 |
| P1-1 | 拖拽改上级补 CAS：请求带「改前上级」，锁内比较（**不复用** `entity_group_fields_hash`：森林接口不给算它所需的口径与关系字段） | **已立 spec `consol-group-code-entry-consistency`** | 后提交者覆盖先提交者的结构修复 | 两客户端并发拖拽，后者 409 |
| P1-2 | 三码规范化单一来源（NFKC + 去空白 + 大写）、按规范值入库、报错统一「{字段}：{原因}」（保留字符串 detail，不改结构化回执） | **已立 spec `consol-group-code-entry-consistency`** | 各入口诊断口径不一致 | 四入口同一输入同结论、同入库值、同文案 |
| P1-3 | 就绪门在七域五态上补「可执行动作白名单」 | **已实现基础**（`consol_readiness_service.py:28,148-156`）；**已定（按建议）**：服务端不强制，前端按钮禁用保持（见 `consol-status-semantics-closure` design §8） | 避免各页自行判断能否推送 | `tree=not_ready` 时推送按钮禁用 |
| P1-4 | ~~附注映射确认改为服务端现算 hash~~ | **已实现**（`routers/consol_note_detail_templates.py:478-509` 现读重建，见 §0.5 第 4 条） | — | — |
| P1-5 | Excel 代码列文本格式、数字单元格与无缓存公式针对性提示、导出不再回退旧 hash（前导零经核对不现实：真实代码首位非 0） | **已立 spec `consol-group-code-entry-consistency`** | Excel 数值化不可逆 | 数字 / 公式 / 文本单元格各有确定结论 |
| P1-6 | stale 原因与时间、重新汇总与推送附注步骤如实报状态 | **已立 spec `consol-status-semantics-closure`** | 把技术状态变成可操作状态 | 页面显示原因与时间；部分失败、跳过不显示为成功 |
| P1-7 | headless 前台/后台共享任务键 + 后台化（期 3） | 前台已有（同步），后台未做 | 防止双写与「API 存在即已接线」 | 显式、事件、构建、运行时四组证据闭合 |
| P2-1 | ~~回执补 `tree_kind` 标识~~ → 不做 | 经核对无误用路径（森林键 `code@year`、合并树键 `code:role`，合并类接口服务端自建树） | — | — |
| P2-2 | ~~树版本 fingerprint 显式纳入规则版本号~~ → 不做 | 指纹由树的输出算出（`consol_scope_confirmation_service.py:45-120`），规则变化导致输出变化即被识别 | — | — |
| P2-3 | 任务观测面板、输入/输出 digest、历史诊断导出 | 未实现 | 降低长期运维成本 | 可按 operation/event/job 反查完整链路 |
| P2-4 | 端到端回放样本与故障注入工具 | 部分已有（`backend/tests/consol_operation/` 22 个文件） | 提高回归效率 | 可重放正常、冲突、重试、取消、恢复 |

### 10.1 须先拍板才能实施的项

| 项 | 冲突点 | 需要的决策 |
| --- | --- | --- |
| 初稿 P1-1 重复项目阻断推送 | `require_calc_year` 注释写明「V206 起替代必须先确认合并范围」，是 2026-10-27 拍板 | **已定（用户 2026-11-11）**：不阻断，改为弹窗提示（进入合并工作台与手工推送前），由 `consol-group-code-entry-consistency` R7 承接 |
| 初稿 P1-2 关系冲突阻断写入 | `_make_entity:214-222` 既定按单体/合并择一取值继续建树 | **已定（用户 2026-11-11）**：同上，弹窗提示不阻断 |
| 树版本改阻断（§7.3 方案 B） | `_record_tree_version` docstring「版本不是计算前提」 | **已定（按建议）**：不阻断，失败已随推送运行记录可查 |
| `AMBIGUOUS_SELF_REFERENCE` 新增 | 现网三码相同一律判 `SELF_ULTIMATE` | **已定（按建议）**：不加，没有「无法判断」的业务场景 |
| 向导修改企业代码是否受建项授权限制 | 建项授权只接在单建、批量、连续审计三处，向导保存可把项目改到任意合法代码 | **已定（用户 2026-11-11）**：要求对新代码有建项授权，由 `consol-group-code-entry-consistency` R2.5 承接；同时修复向导保存 / 确认只校登录的越权 |
| 企业代码更正 / 主体变更的 `node_key` | §3.5 | **已定（按建议）**：本轮只做「同年度有引用即拒绝并弹窗列出影响」（`consol-group-code-entry-consistency` R6）；`old → new` 迁移另立 spec |

### 10.2 本 spec 实施后状态（2026-11-12）

§10.1 是立 spec 前的实施顺序基线，保留其历史记录；本小节是 `consol-note-save-integrity-closure` 实施后的当前状态，P0-1/P0-2/P0-3 以本小节为准。

| 条目 | 当前状态 | 证据与边界 |
| --- | --- | --- |
| P0-1 保存失败改非 2xx、批量导入逐表回报 | **已落地** | `consol_note_sections.py:459-478` 500 错误映射；`ConsolNoteTab.vue:2651-2762` 逐章节 try/catch、成功/失败汇总。后端相关选集 127 passed；前端部分失败、全部失败和 PUT 5xx 不重试定向用例通过。 |
| P0-2 保护解析单一来源 + 写入方登记守卫 | **已落地** | `consol_note_protection.py` 严格 fail-closed；四个自动写入方和自定义查询回写已接入；`test_consol_note_writers_guard.py` 的双向 AST 对账和两类变异通过。单体 `WriteGate` 矩阵仍未被复用，符合 v3 勘误。 |
| P0-3 内容摘要 CAS | **已落地** | GET/PUT/公式回执均带 `data_digest`；PUT 强制 `expected_digest` / `force_overwrite` 二选一；服务层锁后比较且唯一键赢家再比较。`test_consol_note_save_cas.py` 与服务层回归通过；前端定向 9 tests passed。 |
| R3.6 自定义查询单格回写标手工格 | **已落地** | 数组行非项目名列追加 `manual_cells`，第 0 列/字典行返回未标记原因；生产回写后生产公式填入保留回写值。 |
| R4 写入方治理 | **已落地** | 登记表覆盖 manual/automatic/structural/stale 入口，排除表有可验证理由；未登记入口和自动写入方缺保护的变异均打红。 |
| R5.1 浏览器验收 | **部分证据可复核** | Task 7.3 的正式 PUT、CAS 恢复、三阶段摘要和 PG 全字段对账摘要已迁入 §0.5.2；【测试】项目目标节点恢复一致，正式认证请求 5 次均 200。 | Task 7.1/7.2 没有保留截图或响应拦截报告，不能仅按 tasks 勾选判为独立可复核通过。 |
| 预存回归与环境限制 | **如实保留** | 前端候选/HEAD 对照均为 2 个同名异步用例失败，候选没有新增失败；类型检查候选/HEAD 对照仍为同一组预存类型错误，行号随测试增量变化；本轮未找到 gitleaks 执行记录，未写成通过。 |
| 原 review 其他 P1/P2 | **未因本 spec 改变** | 树版本结构化、stale 状态语义、拖拽 CAS、三码/Excel 代码列、headless 后台化、全链路 worker 观测仍按 §10.1 和后续 spec 处理。 |

因此当前建议顺序应改读为：本 spec 的 P0-1 → P0-3 → P0-2 已完成；后续重点是补齐可复核的 R5.1 7.1/7.2 运行证据，以及按 `consol-status-semantics-closure`、`consol-group-code-entry-consistency` 各自边界继续推进。完成本 spec 不代表整个 §10 验收矩阵已通过。

### 10.3 consol-status-semantics-closure 实施后状态（2026-11-13）

§10.1 的优先级表和 §10.2 的前置 spec 状态均保留为历史记录；本小节追加记录 `consol-status-semantics-closure` 对 P0-5、P1-6 的当前落地方式，并单独记录就绪门不在服务端强制的裁决。完成本 spec 的代码与定向回归不等于整个 §10 验收矩阵全部通过。

| 条目 | 当前状态 | 落地方式与证据 | 边界 |
| --- | --- | --- | --- |
| **P0-5 审批成功 / 事件入队 / 任务完成 / 页面可见四态** | **代码已落地，定向回归有证据；运行时独立验收未闭合** | 抵销审批以 `recalc_trigger` / `recalc_notice` 区分事件已发布、事件失败和不适用；处理器入队失败写失败推送运行记录并广播 `consol.push_failed`。调整审批以 `tb_update_status` 汇总落账事实，回执增加 `downstream`，前端提示发布失败而不暗示下游已完成。相关后端/前端实现与变异用例见 §0.5.3。 | 任务记录的后端 110 passed、前端 161 passed 是定向回归，不替代 clean-HEAD 逐节点对拍；浏览器 `initScript` 拦截回执的最终独立证据仍待补。 |
| **P1-6 stale、重新汇总与推送附注步骤如实报状态** | **代码已落地，定向回归有证据；迁移/浏览器收尾未闭合** | V270/R270、stale 原因模块与写入方守卫形成统一原因链；章节标签显示原因和时间；`kept_manual`、`computed_value`、`manual_differs_count` 和全部失败异常使重新汇总摘要如实；`skip_reason`（`no_template_type`、`no_sections`、`no_tree`、`context_failed`）与共享 `note_step_verdict` 使推送/级联刷新区分失败和跳过。相关文件、守卫和变异证据见 §0.5.3。 | 共享 PG 只读确认 V270 已应用且 checksum 一致，尚未执行 R270 回滚；完整 clean-HEAD 对拍、全量类型对拍和最终浏览器复测继续按 tasks 状态保留。 |
| **就绪门是否在服务端强制可执行动作** | **已裁决：不强制** | 服务端保留七域五态状态计算；前端按就绪条禁用按钮并展示原因。未就绪时推送、重新汇总和 operations 不因就绪门被服务端拒绝，仍按各自权限、CAS、锁和业务错误处理。 | 这是 2026-11-11 用户确认的范围裁决，不是遗漏的服务端门禁任务；重复项目和关系冲突继续提示、不阻断，若未来要改为服务端阻断须另行拍板并另立范围。 |

## 11. 端到端验收矩阵

下表是建议的验收边界。本次仍为固定提交静态审查，**「本次状态」统一为未执行**；新增「既有测试」列列出平台已存在的相关用例，实施时应在这些文件上扩展而非从零新建。

| 编号 | 场景 | 验证方式 | 关键断言 | 本次状态 | 既有测试（可扩展） |
| --- | --- | --- | --- | --- | --- |
| A01 | 单建与批量导入同一三码输入 | API + 服务端单测 | 规范化值、错误码、诊断排序和树摘要一致 | 未执行 | `backend/tests/test_consol_group_tree.py`、`backend/tests/test_group_relation.py` |
| A02 | Excel 前导零/科学计数法/公式值 | 真实 Excel + xlsx/xlsm 回读 | 不猜补零；风险明确；可恢复值逐字节一致 | 未执行 | 无（需新建） |
| A03 | 重复项目与关系冲突 | API + PG 约束/事务 | 只读预览可展示；是否阻断取决于 §10.1 拍板 | 未执行 | `test_consol_group_tree.py`（`duplicate_project` / `relation_conflict` 诊断已有断言） |
| A04 | 三码自指、缺上级、断环、最终控制方环 | API + PG fixture | 四层诊断稳定；合法自指与非法环区分明确 | 未执行 | `test_group_relation.py`、`test_consol_group_tree.py` |
| A05 | 树确认并发 | 两个 API 客户端 + PG CAS | 旧树确认返回 409，不覆盖新树 | 未执行 | `backend/tests/test_consol_scope_confirmation.py` |
| A06 | 四表→TB 显式发布 | API + 真实测试项目 | 草稿/审批/发布各阶段状态分离，金额只发布一次 | 未执行 | `test_consol_trial.py`、`test_consol_trial_consistency.py` |
| A07 | TB→底稿→报表→附注正常链路 | API + worker + 读取回执 | event/operation/source revision 逐段可追溯，最终 digest 一致 | 未执行 | `backend/tests/services/test_consol_full_chain_integration.py` |
| A08 | 链路中间步骤失败 | 故障注入 + PG 回滚核对 | 下游不伪装 fresh；失败原因和可重试入口可见 | 未执行 | `backend/tests/consol_operation/test_snapshot_fault_injection_7_5.py` |
| A09 | 合并附注四维隔离 | API + 浏览器 + PG | 项目/年度/章节/`node_key` 交叉读取不串数据；兼容 `node_key IS NULL` legacy 行 | 未执行 | `backend/tests/services/test_consol_node_scope.py`、`test_note_standalone_consolidated_only_scope.py` |
| A10 | 附注手工格、锁定格与公式格并发保存 | 两客户端 + CAS | 冲突格返回 409；锁定/手工格不被自动覆盖；**失败不得返回 200** | 未执行 | `backend/tests/test_consol_note_entry_scope_lock.py` |
| A11 | stale 触发与清除 | API + worker + 页面刷新 | 来源/映射/树/公式失败原因准确，处理后按 revision 清除 | 未执行 | `backend/tests/services/test_consol_note_stale_sse.py`、`test_consol_trial_stale_handler.py` |
| A12 | 后序重汇总与章节 savepoint | PG 锁竞争 + 中途异常 | 直接下级口径稳定；单章失败不污染其他章；重试幂等 | 未执行 | `backend/tests/services/test_consol_note_subtree_reaggregate.py`、`test_consol_note_reaggregate_cache_unit.py` |
| A13 | 普通审批与 outbox | API + PG + 进程退出 | 业务提交和 outbox 原子；重复投递不重复写 | 未执行 | `backend/tests/consol_operation/test_operation_state_machine.py` |
| A14 | 抵销审批 operation | API + worker | 审批 revision、operation 和终态可关联；入队失败可补偿；**推送后能查到 tree_version 或失败原因** | 未执行 | `backend/tests/consol_operation/test_consol_evidence_identity.py` |
| A15 | worker 租约接管 | 两 worker + kill/超时 | 旧 owner 不能提交；新 owner 接管且业务副作用至多一次 | 未执行 | 无（需新建） |
| A16 | worker 取消/重试/恢复 | API + 进程信号 | 取消不伪造失败；重试保留 attempt；恢复从安全点继续 | 未执行 | 无（需新建） |
| A17 | headless 显式刷新 | API + Node 执行器 | 返回逐章节执行结果（现状已如此）；结果 JSON、stdout/stderr、退出码可核对 | 未执行 | `backend/tests/services/test_consol_note_pull_e2e.py` |
| A18 | 事件驱动后台 headless | 真实事件 + worker + Node | 确认事件确实创建并完成任务；**须先开全局或项目级开关，且当时存在 stale 行** | 未执行 | `backend/tests/services/test_consol_note_formula_refresh_handler.py`、`backend/tests/test_consol_note_gray_service.py` |
| A19 | 前台/后台并发刷新 | 浏览器 + API | 同任务键复用；不重复写；页面显示真实终态 | 未执行 | 无（需新建） |
| A20 | 构建产物新鲜度 | 前端/Node build + manifest | source manifest 与构建产物一致；干净检出可运行 | 未执行 | `audit-platform/frontend/src/views/composables/__tests__/noteHeadlessDisclosureCoverage.spec.ts` |
| A21 | 端到端幂等回放 | 真实测试项目/API/PG | 重放不增业务行，operation/outbox 只有幂等记录 | 未执行 | `backend/tests/consol_operation/test_push_calc_basis_reuse.py` |
| A22 | 权限与归档边界 | API + 不同角色 | 非成员、只读、复核和编辑角色结果符合项目级权限 | 未执行 | `backend/tests/consol_operation/test_readiness_role_views_endpoint_authz.py`、`test_workpaper_shell_endpoint_authz.py` |
| A23 | 合并附注格级写权（v2 新增） | 单测 + AST 守卫 + PG | 5 类合并侧写入方（明细映射/子树重汇总/公式填入/推送回写/手工）逐条经 `WriteGate`；绕过即红 | 未执行 | `backend/tests/formula_writer_ownership/test_note_write_ownership.py`（现有单体侧守卫，需扩合并侧） |
| A24 | 合并附注保存失败可见性（v2 新增） | API + 故障注入 | 非 HTTPException 失败返回非 2xx，前端显示失败 | 未执行 | 无（需新建） |

## 12. 固定提交源码证据目录

以下 16 项是本文全部源码证据。每项均以完整提交 `e25895b20b027422f5b2b1c8f2ce1b97bd5902bb` 为前缀读取；行号是该固定提交文件的静态定位，不能解释为当前工作区行号。为控制证据规模，未把同一结论的所有调用方都列出。

| 编号 | 固定提交源码位置 | 支持的结论 |
| --- | --- | --- |
| E01 | `e25895b20b027422f5b2b1c8f2ce1b97bd5902bb:backend/app/services/consol_node_naming.py:16-45` | 节点角色常量（`:16-25`）、`kind`（`:27-29`）、合并方式（`:31-40`）与 **`node_key()` 定义（`:44-45`）**；展示名称不作为唯一身份。**v2 勘误**：初稿引 `:54-64` 只覆盖 `display_name` 尾部与 `consol_label`，无法支撑本结论 |
| E02 | `e25895b20b027422f5b2b1c8f2ce1b97bd5902bb:backend/app/services/consol_group_tree.py:283-339` | `build_entity_graph`：按年度分组（`:291-297`）、重复诊断与择一（`:301-312`）、`_make_entity` 调用（`:313`，定义在 `:205-250`）、`detached`（`:315-326`）、`_break_cycles`（`:327`，定义 `:253`）、`_attach_by_ultimate`（`:328`，定义 `:355-362`）。**v2 修正**：初稿引 `:283-313` 漏掉 `_make_entity` 定义、断环与挂靠 |
| E03 | `e25895b20b027422f5b2b1c8f2ce1b97bd5902bb:backend/app/services/consol_note_mapping_rule_service.py:194-305,367-407` | 模板版本、来源结构 hash、绑定状态、版本号和结构变化处理；`confirm_mapping` 的 `current_entity_hashes` 由调用方传入（`:207`） |
| E04 | `e25895b20b027422f5b2b1c8f2ce1b97bd5902bb:backend/app/models/consol_note_data_models.py:22-75` | `node_key` **可空**（`:31`）、`is_stale`/`cell_state`/`locked_cells`/`last_formula_*`/`source_*`（`:34-52`）、legacy 与节点级两套部分唯一索引（`:59-73`） |
| E05 | `e25895b20b027422f5b2b1c8f2ce1b97bd5902bb:backend/app/services/consol_node_scope.py:63-180,178-278,281-363` | 节点范围解析与隔离（`:63-180`）、`node_key IS NULL` legacy 过滤与节点行优先覆盖（`:178-278`）、`save_scoped_note_record` 只有行锁 + 唯一键兜底、**无 CAS**（`:281-363`） |
| E06 | `e25895b20b027422f5b2b1c8f2ce1b97bd5902bb:backend/app/services/consol_note_subtree_reaggregate.py:98-129,221-280,344-373,484-592` | advisory/处理锁、后序遍历、章节 savepoint、直接下级汇总、重汇总结果 |
| E07 | `e25895b20b027422f5b2b1c8f2ce1b97bd5902bb:backend/app/services/consol_note_stale_handler.py:31-75,161-322` | `NOTE_UPDATED` / `NOTE_SECTION_SAVED` 两个 handler 注册（`:161-172`）、按绑定与章节号/标题定位受影响章节并标 stale、广播刷新事件 |
| E08 | `e25895b20b027422f5b2b1c8f2ce1b97bd5902bb:backend/app/services/consol_note_formula_refresh_handler.py:99-200,398-410` | `TRIAL_BALANCE_UPDATED` + `WORKPAPER_SAVED` 双订阅（`:404`）、项目级开关二次判断（`:167-175`）、stale 归口短路（`:177-200`） |
| E09 | `e25895b20b027422f5b2b1c8f2ce1b97bd5902bb:backend/app/routers/note_headless_refresh.py:1-56` | 显式 headless 入口；docstring 明写「同步执行」「期 3 改为事件触发」（`:9`），状态码映射（`:26-31`），先 commit 释放连接（`:47-48`） |
| E10 | `e25895b20b027422f5b2b1c8f2ce1b97bd5902bb:backend/app/services/adjustment_review_service.py:195-254`；`backend/app/routers/adjustment_review.py:71-75,168-193`；`backend/app/services/workpaper_sync/outbox.py:184-232,279-359` | 普通审批逐笔 savepoint、路由 commit 后才 `publish_review_events`、outbox `enqueue` 只 flush 不 commit |
| E11 | `e25895b20b027422f5b2b1c8f2ce1b97bd5902bb:backend/app/services/consol_elimination_recalc_handler.py:27-94` | 抵销审批后独立会话请求 operation + `wake()`，异常不回滚已提交审批；注册 `ELIMINATION_APPROVED` / `ELIMINATION_REVOKED`（`:90-91`） |
| E12 | `e25895b20b027422f5b2b1c8f2ce1b97bd5902bb:backend/app/services/platform_job_service.py:182-341,379-491,601-635`；`backend/app/workers/platform_job_worker.py:20-68,69-184,185-208` | **服务文件**：`claim_next`（service:182）、`renew_lease`（service:306）、`update_progress`（service:324）、`cancellation_requested`（service:379）、`finish_success` / `finish_failure` / `finish_cancelled`（service:395/446/601）、`acquire_admission_lock` / `enforce_active_capacity`（service:638/649）；**worker 文件**：`_persist_progress`（worker:20）、`_heartbeat` + `lost` 事件（worker:51）、`run_once`（worker:69）、`run`（worker:185） |
| E13 | `e25895b20b027422f5b2b1c8f2ce1b97bd5902bb:backend/app/services/note_writers.py:17-36,85-128`；`backend/app/services/note_write_ownership.py:83-108,166-200`；`backend/data/note_write_ownership_matrix.json` | **v2 新增**：写入方登记表 40 项、五类 role、`WriteGate.check` 判定顺序、生成式归属矩阵 |
| E14 | `e25895b20b027422f5b2b1c8f2ce1b97bd5902bb:backend/app/routers/consol_note_sections.py:375-409` | **v2 新增**：合并附注保存端点；`except Exception` 分支 `return {"ok": False, ...}` 状态码 200 |
| E15 | `e25895b20b027422f5b2b1c8f2ce1b97bd5902bb:backend/app/services/consol_push_service.py:386-414,447-457` | **v2 新增**：`_record_tree_version` fail-open（try/except + `begin_nested` 失败只告警），在 `worksheet()` 步骤内调用 |
| E16 | `e25895b20b027422f5b2b1c8f2ce1b97bd5902bb:backend/app/core/config.py:311-313`；`backend/app/services/consol_note_gray_service.py:27-59`；`backend/app/routers/consol_notes.py:250-328` | **v2 新增**：`CONSOL_NOTES_V2_ENABLED` 默认 False、项目级 opt-in 默认 False、异常 fail-open 返 False、开关读写端点与权限级 |

## 13. 本次未执行的验收与最终审查结论

### 13.1 明确未执行

本次没有启动应用、连接真实 PostgreSQL、创建或修改测试项目、运行 API、打开浏览器、运行真实 Excel 客户端、执行 Node headless、构建前端/Node 产物、运行业务单测/集成测试、做多 worker 竞争、模拟进程崩溃、验证 Redis/队列或核对生产数据分布。因此以下结论仍是待验收，不是已通过：

- 真实 PG 锁竞争、唯一键冲突、savepoint 回滚和跨进程租约接管；
- Excel/xlsx/xlsm/CSV 的类型往返、宏保留、前导零和公式值导入；
- 四表→TB→底稿→报表→附注的真实事件消费、公式结果和页面显示；
- 附注四维隔离、版本/CAS/stale 的两个客户端并发行为；
- 普通审批、抵销 operation、outbox 重投、worker 取消/恢复和幂等副作用；
- headless 显式 API 的 Node 执行、后台自动触发、构建 manifest 新鲜度和运行时超时/取消；
- 浏览器权限、错误提示、刷新状态、导出结果和真实业务数据验收。

v2 修订同样只做只读代码复核：未运行上表任一既有测试，也未验证 §11 新增的 A23 / A24。

### 13.2 审查结论

固定提交的静态结构足以支持「已有企业树身份、三码自指裁决、范围确认 CAS、附注版本/来源状态、审批事件、耐久任务、写入方归属矩阵和显式 headless 入口」这一判断；不足以支持「全链路已自动闭环、Excel 风险已解决、后台 headless 已自动触发、worker 在真实 PG 下已安全恢复」这一更强判断。

v2 复核把初稿的「整体偏缺」修正为**四个具体破口**，这也是最应优先修的部分：

1. 合并附注保存失败返回 200（`consol_note_sections.py:399-409`），Excel 批量导入路径据此误报成功——最小改动、最高收益。
2. 合并附注人工保护格解析三份口径不一、写入方无登记守卫（v3 勘误：不是「零保护」，见 §0.5）。
3. 合并附注保存无 CAS——并发下静默覆盖。
4. 树版本记录 fail-open——已随推送运行记录可查，降为 P2。

建议实施顺序：**P0-1 修假成功 → P0-3 补 CAS → P0-2 统一保护解析与写入方登记**，已立 spec `consol-note-save-integrity-closure`；P1-1 / P1-2 / P1-5 与新发现的差额表越权由 `consol-group-code-entry-consistency` 承接（与前者无代码交叉，可并行），P0-5 / P1-6 由 `consol-status-semantics-closure` 承接（在前者的章节 GET 与写入方登记上追加，须在其后实施）。每一项完成都应绑定验收矩阵编号和真实证据，不以「路由存在」「静态测试通过」或「任务返回 200」替代端到端验收。

---

**文档状态：** v2（2026-11-11）。固定提交静态审查稿 + 事实纠偏 8 处 + 缺口补录 4 项；源码证据 16 项（新增 E13~E16）；验收矩阵 24 项（新增 A23 / A24）；另附当前工作区实施复核，其中 Task 7.3 正式 PUT 恢复对账摘要已迁入 §0.5.2，Task 7.1/7.2 与其余运行时验收仍未独立复核。
**变更范围：** 本次迁移仅修改本文档与对应 spec `design.md`；未改动任何源码、迁移、测试、`tasks.md` 或数据库。工作区其他会话改动不属于本次审查范围。
