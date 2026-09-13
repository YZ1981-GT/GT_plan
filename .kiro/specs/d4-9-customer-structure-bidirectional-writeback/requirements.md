# Requirements Document

D4-9 重要客户结构分析 HTML↔OnlyOffice 双向回写

## Introduction

D4-9「重要客户结构分析」是 D4 营业收入底稿的一张分析表。它目前只有结构化视图 + 一个 legacy `GtOnlyOfficeSheet` 单向在线编辑入口，**不在统一双向回写路径上**。

本 spec 把 D4-9 作为一个**新产品**接入 D4-2/3 已落地的统一双向路径（`WorkpaperSyncEditorHost` + `useWorkpaperSyncBridge` + `phase5_*` bridge + per-entry contract + registry），使 HTML 结构化视图与 OnlyOffice Excel 编辑经同一 content version、adapter、callback/application、three-way merge 真实往返。

D4-9 与 D4-2/3 的结构差异（本 spec 的核心难点）：

1. **同一张 sheet 内有两个平行的动态行区域**（本期 Top10 客户 + 上期 Top10 客户），而不是 D4-2/3 的「一 sheet 一 table」或「两 sheet 各一 table」。
2. **有 4 个表级标量单元格**（本期销售总额 C24 / 本期销售总量 E24 / 上期销售总额 C38 / 上期销售总量 E38），它们不是行内列，是固定单元格。
3. **占比列是物理公式**（D 列 `=IF(C=0,0,C/$C$24)`、F 列 `=IF(E=0,0,E/$E$24)`），合计行是 `=SUM(...)`，且占比公式引用了表级标量单元格（跨行引用）。

同时本 spec 覆盖两件与双向强相关的事：

- **公式管理**：让审计师能对 D4-9 的可编辑单元格自定义公式（落 `wp_formula` 表，写进物理 xlsx），并做上下游血缘追溯（占比/合计/总额引用链），且自定义公式单元格必须纳入双向的受保护区（OO 侧不得覆盖用户公式结果）。
- **修复 D4-9 导入导出**：现有 `_d4_import_export.py` 对 D4-9 的表头只有「客户名称/销售金额/销售数量/上期排名」，未区分本期/上期、无总额、无专用 parser，走通用 flatten 会错处理 `{current,prior}` 嵌套结构。本 spec 补齐本期/上期分区 + 总额 + `_parse_d4_9_row` 专用解析器，使导入导出与真实 store 结构相符。

真源优先级遵循 `docs/operations/workpaper-html-onlyoffice-bidirectional-writeback-master-control.md`：数据库约束与运行态请求 > source-backed manifest/生成器/机器门禁 > 本 spec。

## Glossary

术语与冻结事实（openpyxl 直读 `backend/wp_templates/D/D4 收入底稿.xlsx` 实测）

| 项 | 值 |
|---|---|
| 源模板 sheet 名 | `重要客户结构分析D4-9` |
| 宿主组件 | `GtD4OperatingRevenue.vue`（sheetName 末段 `D4-9` → `D4TabCustomerStructure.vue`） |
| HTML store item | `D4-9-data`（`checklist_responses`，remark 存 `{current:{rows,totalAmount,totalQuantity}, prior:{...}}`） |
| 本期表 | 表头 R12；数据 R13-R22（10 行）；合计 R23；本期销售总额 R24（C24 金额 / E24 数量） |
| 上期表 | 表头 R26；数据 R27-R36（10 行）；合计 R37；上期销售总额 R38（C38 金额 / E38 数量） |
| 列 | A 序号 / B 客户名称 / C 销售金额 / D 销售金额占比(公式) / E 销售数量 / F 销售数量占比(公式) / G 上期排名 |
| 占比公式（本期） | `D13=IF(C13=0,0,C13/$C$24)`，`F13=IF(E13=0,0,E13/$E$24)` |
| 占比公式（上期） | `D27=IF(C27=0,0,C27/$C$38)`，`F27=IF(E27=0,0,E27/$E$38)` |
| 合计行公式 | `C23=SUM(C13:C22)`、`E23=SUM(E13:E22)`；上期 `C37=SUM(C27:C36)`、`E37=SUM(E27:E36)` |

## Requirements

### Requirement 1: D4-9 作为独立 entry 接入统一双向路径

**User Story:** 作为审计师，我希望在 D4-9 底稿上切换「结构化视图 / 在线编辑」并双向同步，使我在 Excel 里改的客户行与总额能回到结构化视图，反之亦然。

#### Acceptance Criteria

1. WHEN 系统装配双向 registry THEN D4-9 SHALL 有一个独立的 source-backed manifest entry（建议 `xlsx/gt-d4-customer-structure`）与独立 adapter（建议 `d4.customer_structure`），不复用 `d4.revenue_detail`。
2. WHEN manifest entry 的 capability 未被 reviewed overlay 裁决为 `bidirectional` THEN 系统 SHALL NOT 注册该 adapter，且前端能力开关 SHALL 保持非双向（fail-closed）。
3. WHEN 用户进入 D4-9 的在线编辑视图 THEN 宿主请求 SHALL 命中统一 `USER_SYNC_PREFIX` 路径，SHALL NOT 出现 legacy `sheets/{sheet}/onlyoffice-callback` 或 D2 专用旁路。
4. WHEN adapter 注册成功 THEN 该 entry 的 contract/instrumentation/template digest 与 `phase5` 模块现算 payload SHALL 双向锁死；任一漂移 SHALL fail closed。
5. WHERE 宿主实测不可达（产不出 descriptor 事实）THE 系统 SHALL NOT 注册 adapter。

### Requirement 2: 单 sheet 内两个动态行区域 + 表级标量的契约表达

**User Story:** 作为平台维护者，我希望 D4-9 的本期/上期两个客户区域与 4 个总额标量用现有契约模型正确表达，不引入契约内核改动。

#### Acceptance Criteria

1. WHEN 构造 D4-9 contract THEN 该 contract 的单张 sheet（`重要客户结构分析D4-9`）SHALL 声明 3 张 table：`customer_current_rows`（本期动态行）、`customer_prior_rows`（上期动态行）、`customer_totals`（表级标量，无 row_identity）。
2. WHEN 声明动态行 table THEN 每张动态行 table SHALL 有 `row_identity`（kind=field，pointer 含 `{row_uuid}`）与 `delete_policy`，客户行字段 SHALL 为 `product/客户名/金额/数量/上期排名` 等平面列。
3. WHEN 声明表级标量 table THEN `customer_totals` 的字段 SHALL 用 `cell.row_from = 静态行号`（C24/E24/C38/E38）且 `row_scoped=False`，SHALL NOT 含 `{row_uuid}`。
4. WHEN 声明占比列（D/F）与合计行 THEN 占比字段 SHALL 为 `mode=formula` 且其列 SHALL 落在该 table 的 `formula_mask` 内；合计行 SHALL 由 `footer_anchor.carries_total_formula=true` 承载。
5. WHEN contract 经 `parse_contract` 校验 THEN 全部字段 SHALL 通过（无 CS-1~CS-20 违规），且序号列（A）等模板内部公式/自增列 SHALL NOT 冒充可编辑业务字段。
6. IF 任一字段缺 `source_ref` THEN 校验 SHALL 失败（禁止无来源自造字段）。

### Requirement 3: HTML store 行补稳定行身份并迁移

**User Story:** 作为审计师，我希望删除/重排/新增客户行后数据不串行，因此每行需要稳定身份。

#### Acceptance Criteria

1. WHEN D4-9 store（`D4-9-data`）被读取用于投影 THEN 每个 `current.rows[]` / `prior.rows[]` 元素 SHALL 携带稳定 `rowId`（非数组下标）。
2. WHEN 历史 store 数据（无 rowId）首次加载 THEN 前端 SHALL 一次性补齐 rowId 并持久化，SHALL NOT 丢失既有客户名/金额/数量/上期排名/占比手工值。
3. WHEN 投影层遇到缺 rowId 或重复 rowId 的行 THEN 后端 SHALL fail closed（不得退回下标作身份，不得静默合并）。
4. WHERE 同一 store 的本期与上期区域 THE rowId SHALL 在两个区域内各自唯一，且区域归属 SHALL 由 table_key 决定，不得跨区域串号。

### Requirement 4: HTML→OO materialize 与 OO→HTML extract/merge

**User Story:** 作为审计师，我希望 HTML 改动生成的 Excel 与 Excel 改动提取回的行都正确落到本期/上期对应区域与总额单元格。

#### Acceptance Criteria

1. WHEN HTML→OO materialize THEN 系统 SHALL 把 `customer_current_rows` 写入 R13 起、`customer_prior_rows` 写入 R27 起、4 个总额写入 C24/E24/C38/E38，SHALL NOT 覆盖 D/F 占比公式与合计行公式（受 formula_mask 保护）。
2. WHEN OO→HTML extract THEN 系统 SHALL 按 table_key + row identity 把两个区域的行分别提取回 `current.rows` / `prior.rows`，把 4 个总额提取回 `current.totalAmount/totalQuantity` 与 `prior.totalAmount/totalQuantity`。
3. WHEN 三方合并（base/current/incoming）THEN 不同字段 SHALL 自动合并；同字段冲突 SHALL 保留三值与解决轨迹，SHALL NOT 静默选边。
4. WHEN OO 侧新增/删除客户行 THEN 结构性行变更 SHALL 通过声明式 mutation plan 一次应用；合计公式区间 SHALL 随受管行区间伸缩（`carries_total_formula`），SHALL NOT 静默错行。
5. WHEN merge 结果与 incoming 不同 THEN 系统 SHALL canonical rematerialize 并要求 refresh/reopen；HTML 刷新 SHALL 读新 content version，SHALL NOT 直接读 callback 文件。
6. WHEN 业务变更提交 THEN 系统 SHALL 只经 `ContentMutationService.commit` 推进恰好一个 content version/revision，SHALL NOT 自增独立 `file_version`/`oo_content_revision`。

### Requirement 5: 用户自定义公式与上下游血缘

**User Story:** 作为审计师，我希望能对 D4-9 的可编辑单元格自定义公式（如占比口径微调、销售总额从 D4-7 取数），并追溯公式引用的上下游，同时不被在线编辑覆盖。

#### Acceptance Criteria

1. WHEN 审计师对 D4-9 某可编辑单元格设置自定义公式 THEN 公式 SHALL 落 `wp_formula` 表（`target_cell` 锚定），并在底稿实例化/导出时写进物理 xlsx（用户公式优先级高于模板内置公式）。
2. WHEN 自定义公式引用其它单元格/底稿 THEN 引用有效性 SHALL 经 ACNR `full_resolve` 校验；无法解析的引用 SHALL 给出可操作的中文错误，SHALL NOT 静默吞掉。
3. WHEN 某单元格存在用户自定义公式 THEN 该单元格 SHALL 纳入双向的受保护区（等效 formula_mask），OO 侧对该 cell 的编辑 SHALL 产生受保护字段冲突而非静默覆盖用户公式。
4. WHEN 展示公式上下游 THEN 系统 SHALL 能呈现 D4-9 占比/合计/总额的引用链（D→C 与 $C$24、合计→明细区间、总额←D4-7 取数），供审计追溯。
5. WHERE 表级标量总额来自上游 D4-7 THE 系统 SHALL 支持把该取数登记为可追溯来源，并在总额被手工覆盖时保留手工值（不被取数无条件覆盖）。
6. IF 用户公式与契约声明的 formula 字段冲突（同 cell 既是模板公式又被声明用户公式）THEN 系统 SHALL 以明确规则裁决（用户公式优先并纳入保护区），SHALL NOT 两套公式同时写入产生歧义。

### Requirement 6: 修复 D4-9 导入导出与真实结构相符

**User Story:** 作为审计师，我希望 D4-9 的导出模板/导出数据/导入数据与结构化视图看到的本期/上期两张表 + 总额一致。

#### Acceptance Criteria

1. WHEN 导出 D4-9 模板/数据 THEN xlsx SHALL 区分本期区与上期区两张表，SHALL 含本期/上期销售总额与总量，列头 SHALL 覆盖 序号/客户名称/销售金额/销售金额占比/销售数量/销售数量占比/上期排名。
2. WHEN 导入 D4-9 数据 THEN 系统 SHALL 用专用 `_parse_d4_9_row`（区分本期/上期归属 + 解析总额），把结果写回 `D4-9-data` 的 `{current,prior}` 嵌套结构，SHALL NOT 用通用 flatten 把嵌套结构处理错。
3. WHEN 导入行缺 rowId THEN 导入路径 SHALL 生成 rowId（与 Requirement 3 同一身份规则），使导入后的行可参与双向。
4. WHEN 导出的占比/合计为公式列 THEN 导出 SHALL 保留公式或导出计算值并标注，SHALL NOT 把公式列当可导入的手填列造成回导覆盖公式。
5. WHEN 导入列名不匹配 THEN 系统 SHALL 返回可操作的中文列名错误。

### Requirement 7: 前端宿主接入与视图切换

**User Story:** 作为审计师，我希望 D4-9 的视图切换与 D4-2/3 一致、可靠，切换时不丢在途改动。

#### Acceptance Criteria

1. WHEN `GtD4OperatingRevenue.vue` 判定当前 sheet 为 D4-9 THEN 在线编辑 SHALL 走 `WorkpaperSyncEditorHost` + `useWorkpaperSyncBridge`（新 entry_id），SHALL NOT 再走 `D4TabCustomerStructure.vue` 内的 legacy `GtOnlyOfficeSheet`。
2. WHEN 从 HTML 切到 OO THEN 前端 SHALL 先 flush 待存并读 store-projection（含 rowId 与总额），再 materialize。
3. WHEN 从 OO 切回 HTML THEN 前端 SHALL 按桥状态 forcesave 或 reloadAfterApplied，SHALL NOT 丢失 OO 侧改动。
4. WHEN 双向不可用（能力未裁决/OO 不健康）THEN 前端 SHALL 给出明确提示并保持结构化视图可编辑，SHALL NOT 呈现"看起来能切换实际会失败"的假入口。
5. WHEN D4-9 legacy 单向入口被替换 THEN `D4TabCustomerStructure.vue` 内的 `editorMode` 双模式与其 `GtOnlyOfficeSheet` 分支 SHALL 按 source-backed deletion 移除或改为不可达，避免双入口。

### Requirement 8: 验证、守卫与防假绿

**User Story:** 作为平台维护者，我希望每项能力都有行为级判据与变异检验，杜绝"类存在/字符串存在"式假绿。

#### Acceptance Criteria

1. WHEN 校验契约 THEN 后端守卫 SHALL 断言 3 table 结构、静态标量字段、formula_mask 覆盖、footer 承载，且这些断言 SHALL 是行为/结构级（parse_contract 真跑），非"符号存在"。
2. WHEN 校验双向往返 THEN SHALL 有 materialize→extract roundtrip 测试：HTML 行 + 总额 → xlsx → 提取回 store，逐字段对齐；OO 侧改一格能提取回正确区域。
3. WHEN 做变异检验 THEN SHALL 有变异脚本，锚点 ≥4：删 formula_mask 保护 / 把静态标量改成 row 域 / 把两 table 合并成一 table / 去 rowId 身份；四态判定（RED/GREEN/ANCHOR-MISS/WRONG-TEST），GREEN 即守卫缺陷。
4. WHEN 校验前端接入 THEN vitest SHALL 断言 D4-9 走新 entry 的 `WorkpaperSyncEditorHost`、字面量端点/entry_id 正确、能力未裁决时 fail-closed；变异改错 entry_id 前缀 SHALL 打红。
5. WHEN 真栈实测 THEN Playwright SHALL 在真实 OO 上跑 D4-9：HTML 编辑客户行 + 总额 → 在线编辑可见 → OO 改一行/改总额 → 切回 HTML 值正确；证据 JSON SHALL 记录 request 路径、content version、application、operation 终态、artifact digest。
6. WHERE 环境不可用 THE 相关判据 SHALL 记 `UNVERIFIABLE`（非实现失败），SHALL NOT 用人工说明改绿。


### Requirement 9: 统一治理边界与里程碑

**User Story:** 作为平台维护者，我希望 D4-9 的双向能力落在统一的 C0-C4 治理边界内，公式定义 key 与状态机语义一致，避免跨 spec 语义漂移。

#### Acceptance Criteria

1. WHEN 验收 D4-9 THEN C0模板/identity、C1sync、C2formula、C3linkage、C4逐表验收 SHALL 各有独立证据；物理sheet双区 SHALL NOT 被当作额外 wp_code。
2. WHEN 处理公式定义 THEN 公式 key SHALL 使用 wp_id，preset_version 仅为定义版本；preset 升级 SHALL 保留 custom，删除 custom SHALL 恢复 preset，缺失/损坏/stale/blocked 分态，schema 白名单 SHALL 禁 eval 和外链。
3. 不同字段自动合并，同字段保留三方冲突轨迹；durable ack不等于applied；同步不是TB/A13。
4. 只门控D4-9相关平台产物，不等待全平台77项。