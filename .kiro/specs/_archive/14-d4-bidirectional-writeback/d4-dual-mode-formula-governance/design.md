# Design — D4双模式公式治理总纲

## 统一范围与分母
本总纲治理36个逻辑 `wp_code`，不把物理 Excel sheet、sheet 变体或程序表纳入分母。`D4-22A`、`D4-31T`、D422A 等仅作为实现证据。公式定义 key 必须使用 `wp_id`；`preset_version`只表示定义版本，不属于业务 target identity。

## R1 逐表 owner 矩阵（唯一真源）
| wp_code | owner | 目标/边界 | 状态 |
|---|---|---|---|
| D4-1 | d4-dual-mode-formula-governance | 审定表 | 专属 |
| D4-2 | d4-revenue-matrix-bidirectional | 主营明细矩阵 | 专属 |
| D4-3 | d4-revenue-matrix-bidirectional | 其他收入明细 | 专属 |
| D4-4 | d4-adjustment-and-analysis-gap-closure | 调整分录；复用A13/集中调整 | gap |
| D4-5 | d-cycle-sheet-bidirectional-expansion | 政策检查；既有d-cycle扩展 | 已有owner |
| D4-6 | d-cycle-sheet-bidirectional-expansion | 指标分析；既有d-cycle扩展 | 已有owner |
| D4-7 | d-cycle-sheet-bidirectional-expansion | 月度毛利；既有d-cycle扩展 | 已有owner |
| D4-8 | d4-adjustment-and-analysis-gap-closure | 产品毛利；复用现有计算 | gap |
| D4-9 | d4-9-customer-structure-bidirectional-writeback | 客户结构双区 | 专属 |
| D4-10 | d4-price-analysis-writeback-linkage | 客户价格联动 | 专属 |
| D4-11 | d4-price-analysis-writeback-linkage | 产品价格联动 | 专属 |
| D4-12 | d4-adjustment-and-analysis-gap-closure | 合同检查；复用卡片/OCR/AI | gap |
| D4-13 | d4-inspection-writeback-formula-io | ERP检查 | d-cycle扩展 |
| D4-14 | d4-inspection-writeback-formula-io | 发生检查 | d-cycle扩展 |
| D4-15 | d4-inspection-writeback-formula-io | 完整性检查 | d-cycle扩展 |
| D4-16 | d4-inspection-writeback-formula-io | 出口检查 | d-cycle扩展 |
| D4-17 | d4-cutoff-return-writeback-formula-io | 截止前向 | d-cycle扩展 |
| D4-18 | d4-cutoff-return-writeback-formula-io | 截止后向 | d-cycle扩展 |
| D4-19 | d4-cutoff-return-writeback-formula-io | 折扣检查 | d-cycle扩展 |
| D4-20 | d4-cutoff-return-writeback-formula-io | 退货检查 | d-cycle扩展 |
| D4-21 | d4-21-24-oo-bidirectional-and-cross-sheet-formula | 关联方价格 | d-cycle扩展 |
| D4-22 | d4-21-24-oo-bidirectional-and-cross-sheet-formula | IPO指标 | d-cycle扩展 |
| D4-23 | d4-21-24-oo-bidirectional-and-cross-sheet-formula | 发票比较 | d-cycle扩展 |
| D4-24 | d4-21-24-oo-bidirectional-and-cross-sheet-formula | 第三方检查 | d-cycle扩展 |
| D4-25 | d4-ipo-fraud-writeback-formula | IPO经销商 | d-cycle扩展 |
| D4-26 | d4-ipo-fraud-writeback-formula | 境外收入 | d-cycle扩展 |
| D4-27 | d4-ipo-fraud-writeback-formula | 未披露关联方 | d-cycle扩展 |
| D4-28 | d4-ipo-fraud-writeback-formula | 客户核查 | d-cycle扩展 |
| D4-29 | d4-ipo-fraud-writeback-formula | 客户明细 | d-cycle扩展 |
| D4-30 | d4-ipo-fraud-writeback-formula | 访谈汇总 | d-cycle扩展 |
| D4-31 | d4-ipo-fraud-writeback-formula | 访谈明细 | d-cycle扩展 |
| D4-32 | d4-ipo-fraud-writeback-formula | 资金流 | d-cycle扩展 |
| D4-33 | d4-33-36-writeback-formula-and-io-closure | 其他收入毛利 | d-cycle扩展 |
| D4-34 | d4-33-36-writeback-formula-and-io-closure | 其他收入合同 | d-cycle扩展 |
| D4-35 | d4-33-36-writeback-formula-and-io-closure | 其他收入检查 | d-cycle扩展 |
| D4-36 | d4-33-36-writeback-formula-and-io-closure | 其他收入截止 | d-cycle扩展 |

D4-5/6/7按实际 `D4TabPolicyCheck`、`D4TabIndicator`、`D4TabMarginMonthly` 及 d-cycle bridge 核定；D4-4/8/12只收口双向身份、公式和验收，不重做已有A13/调整、产品月度计算、合同卡片/OCR/AI。

## R2-R8
### R2 共享同步协议
HTML、Excel、导入导出统一经过 `ContentMutationService` 与 `useWorkpaperSyncBridge`。不同字段自动合并；同字段冲突保留 base/current/incoming、决策和轨迹。durable ack仅表示决策已持久化，不等于applied；canonical rematerialize及目标content version确认后才算applied。禁止Excel优先、最后写胜出和文件直读回调。

### R3 公式定义
key=`wp_id + stable_sheet_key + row_key + field_key + custom`；`preset_version`只参与定义版本比较，不进入业务target identity。升级保留custom，删除custom恢复preset；缺失、损坏、blocked、stale分态。F-SHELL v2和编辑schema白名单，禁止eval、外链和remark/field_overrides冒充公式库。

### R4 DAG与联动
表内、表间公式均可二次编辑，同scope单writer，按真实引用建DAG。循环、冲突、stale显式失败。公式同步不是TB/A13；TB/A13只能由独立显式确认发布。

### R5-R8 验收
风险发现不等于错报；四表取数复用 `app/services/four_table/`。导入保留sheet/table/region/stable row key/formula mask。按角色、scope、wp_id、content version做CAS。C0模板/identity、C1sync、C2formula、C3linkage、C4逐表验收只门控相关平台产物，不等待全平台77项；UNVERIFIABLE不计GREEN。

## Correctness Properties
### Property 1
36个且仅36个 `wp_code` 各有一条owner记录；物理sheet/变体/程序表不扩张分母。
**Validates: Requirements 1.1, 1.2, 8.1**
### Property 2
不同字段自动合并，同字段冲突保留三方轨迹；durable ack在applied前不会伪装为applied。
**Validates: Requirements 2.1, 2.2**
### Property 3
公式key使用 `wp_id`，preset/custom/stale/损坏/缺失可区分，禁止eval和外链。
**Validates: Requirements 3.1, 3.2, 3.3**
### Property 4
表内表间真实DAG支持二次编辑，循环和单writer冲突失败；同步不触发TB/A13。
**Validates: Requirements 4.1, 4.2, 5.1**
### Property 5
各owner的C0-C4只门控相关产物，UNVERIFIABLE不假绿。
**Validates: Requirements 8.1**


## P0 修复设计（2026-09-14 实施，append-only）

> 落实总纲 R1-R8 中的 5 项 P0 修复的**实现设计 + 现状 grep 证据**。均遵守：迁移 V/R 配对幂等可回滚查最新 version 防重号、service 只 flush router 统一 commit、单一真源禁平行体系、中文 UI、PBT max_examples=5。

### D-P0-1 公式稳定键（Req 3.1）
- **现状证据**：既有 identity = `(wp_id, sheet_name, target_cell)`（`WpFormula` 唯一索引 `uq_wp_formula_wp_sheet_cell`）；无 `preset_version` 列（故其"不进 identity"结构上已成立）。ACNR 已有 `addr_id`（`{wp_code}/{sheet_code}/{coordinate_key}`）稳定键概念，但 wp_formula 行无 wp_code/sheet_code 直取，无法直接复用为行级键。
- **设计**：新增单一真源 `formula_management/stable_key.py`：`normalize_sheet_key`（剥离排序前缀 + 折叠空白，使展示重命名不改键）+ `parse_cell`（A1 → row/col）。派生列 `stable_sheet_key/row_key/field_key` + `stable_key_needs_review`。旧列/旧索引保留一版，新部分唯一索引 `uq_wp_formula_stable_key` 仅对已回填行生效。回填在 V163 SQL 内用 PG regex 对齐 Python 逻辑；不可安全转换（非 A1）行标 needs_review 不丢。
- **降级/切换点**：迁移回滚（R163）后系统回退纯旧键，稳定键为派生列可重推。

### D-P0-2 公式四态（Req 3.2/3.3）
- **现状证据**：`formula_engine._eval_func_node` 对未注册函数**静默返 0**（trace "unknown"）——把配置错/注入伪装成诚实 0。`validate_formula` 已能检未知函数但求值路径不消费。
- **设计**：单一真源 `formula_management/formula_state.py`（枚举 + `classify_formula`，白名单取 `_REGISTRY.known_function_names()` 不另立清单）。引擎加 `FormulaResult.blocked`/`.state` + `FormulaBlockedError` + `_execute_ast` 前置 blocked 判定。`WpFormulaService.save` 对 damaged/blocked 拒绝写库返 issue 含原始 expression。`report_engine.evaluate_formula` 仅读 `.value`，blocked 为附加信号，报表生成零回归。

### D-P0-3 TB 显式发布确认（Req 5.1）
- **现状证据**：`_on_d_audit_determination_saved` 订阅 `WORKPAPER_SAVED`，wp_code ~ `^[D-N]\d+-1$` 即回写 TB，无确认门/幂等；产者 `wp_html_save._maybe_publish_determination_writeback` 在每次审定表保存时自动发该事件。
- **设计**：handler 仅在 `extra.publish_confirmed is True` 才回写；`_publisher_can_publish`（查 users.role + WORKPAPER_WRITE，fail-closed）；`tb_publish_ack`（publish_token 唯一）ON CONFLICT DO NOTHING 做耐久幂等。产者自动保存事件不带确认信号（对 TB no-op）。新增专用发布端点（authorize_wp_edit + consol_lock + 计算审定数 + 发确认事件）。前端 `GtAuditSheet.vue` 加"发布到试算表"按钮 + 二次确认。
- **外部依赖**：Playwright 端到端待前端 3030 启动；不向真实审计项目发布测试金额。

### D-P0-4 checklist_responses CAS（Req 7）
- **现状证据（核实真实表结构）**：`checklist_responses` 按 `(wp_id,item_id)` 唯一，导入以整表 JSON blob `ON CONFLICT DO UPDATE`（last-write-wins），**无版本列**——多编辑成员并发导入同表会静默覆盖，是真实并发写风险（非无风险，故加行级 CAS 而非仅记文档）。写的是 D4 应答表 `checklist_responses`，非 `working_paper.parsed_data`，不套 ContentMutationService。
- **设计**：V161 加 `content_version`；`_upsert_checklist_response`（`SELECT FOR UPDATE` → If-Match → 冲突 409 / 相符 +1 / 无 base_version 覆盖）。SQLite 忽略 FOR UPDATE，逻辑仍正确。

### D-P0-5 D4 导入权限门（Req 7）
- **现状证据修正**：`_d4_import_export.py` 三端点函数签名仅 Depends(get_current_user, get_db)，但 router_registry 注册时对含 `{wp_id}` 的 router **统一附加 router-level `dedicated_wp_gate`**（Wp_Bound_Gate 可见性/委派门）。旧契约报告漏看该 router-level 依赖误判"零权限"。可见性门**不查合并锁**。
- **设计**：import(写) 首句 `authorize_wp_edit` + `check_consol_lock`（纵深防御 + 补合并锁）；export(读) `authorize_wp_read`（新增，readonly 级，不误伤只读）。因可见性门用真实 DB，全 ASGI 集成需真实 seed wp，改直接单元测试新增授权逻辑。
