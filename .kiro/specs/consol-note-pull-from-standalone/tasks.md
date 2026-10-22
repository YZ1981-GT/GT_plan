# 合并附注从单体附注拉取数据 — 实施任务（v3：收口到 V186 明细映射链路）

## v3 勘误（2026-10-22 复盘，v2 记录的完成情况不成立的部分）

- 🔴 v2 Task 4.2「reaggregate 端点改走 reaggregate_from_standalone」**从未落地**：`consol_notes.py` 的 reaggregate 一直调 `fill_note_sections`（公式内核），`reaggregate_from_standalone` 零调用方。⇒ v2 Task 7.2 与 Phase 2「API 实测」（五-1-1 persisted、五-5-1 读到 1920.00、321 章 0 失败）测到的都是公式内核，**不是单体拉数** —— 假绿。
- 🔴 v2 Task 6.3「端到端」测试在测试里重写了汇总循环，没有调用 `aggregate_section` —— 假绿。
- 🔴 v2 另起的写入器与既有 V186 明细映射链路（明细模板 → 映射规则 → 逐企业绑定 → 用户弹窗确认 → apply，`_archive/48-consol-note-detail-template-and-mapping`）重复造轮子；而 V186 链路本身在真实数据上读不到数（合并章节号从不换算成单体章节号、只读顶层 `rows`、apply 首列错位）。
- 🔴 章节映射 JSON 自 五-10 起整体错一章：合并模板 `parent_section` 错位（五-11「合同资产」表的 parent 是「存货」），v2 生成器按 parent 映射 ⇒ 合同资产拉成存货、固定资产拉成投资性房地产。
- v2 用 try/except 包住 `formula_health` / `note_custom_section` 路由注册，是绕开不是修复（导入错误在别的会话的文件里）。

⇒ v3：删掉 v2 写入器，读取能力并入 V186 链路，修 V186 缺陷，映射改按表标题生成，详见 design §10。

## v3 任务

- [x] 1. 共用读取层 `backend/app/services/consol_note_standalone_reader.py`
  - 读用户实际看到的表：`effective_table_data`（workpaper 来源先投影 `sub_table_data`，与编辑器 / Word / 就绪判定同口径）
  - 选表：子表名 → 合并表标题（规范化：去空白 / 序号 / 「其中，」；去期间后缀；≥0.9 相似且唯一）；无名单表仅在映射没给表名或是主表时用；**不做包含匹配**（「货币资金」⊂「受限制的货币资金明细」）
  - 认列：两侧解析成列路径（multi_header 优先于错位的 headers；单体 headers + `_column_groups`），期末 / 期初同义词归一；规则 精确 → 期间上下文（「（期末数）」「（续：期初数）」、整表单期间）→ 去分组层后缀 → 前缀；命中不唯一或同列被多列认领一律不填并回报列名；比例 / 比率列不加总
  - 续表：同名「（续：期初数）」提供期初列，按「行名 + 同名序号」对行
  - AC：✅ `tests/test_consol_note_standalone_reader.py` 18 例（真库形态样本）

- [x] 2. V186 来源读取 `consol_note_detail_source_service`
  - `load_source_tables` 批量一次查（去 N+1）；合并章节号经映射换成单体章节号 + 子表名；按号取不到按章节标题取（国企集团含上市子公司，子企业模板与合并口径不同）；`is_empty` → 本期无此情形
  - 预览 / 建议返回逐企业来源状态 `entity_sources`（未生成 / 不适用 / 读不出表 / 未对上的列）；没读到来源的企业不参与分组与绑定；预览的已有绑定改批量查
  - 模板建议以合并附注模板该表的行（顺序 / 合计行类型）为骨架，来源独有行插在合计前由用户取舍；行名比较去空白（「合  计」=「合计」）
  - AC：✅ e2e + V186 既有测试

- [x] 3. V186 apply `consol_note_detail_apply_service`
  - 标准来源行 `values[k]` → 第 k+1 列（原实现丢 values[0] 并整体错一列）；空 / 占位符 / 非数值不加总（原 `Decimal("None")` 会抛未捕获异常）
  - `node_key` 给定时只汇总该节点子树内的数据叶子（原实现中间节点也加全树）；未知节点 404
  - 表头 / 列宽取合并模板表；合计 / 小计按本表数据行重算，整列无数据保持空白（原写 0.00）
  - 写入来源 `_last_write_source=detail_mapping` + 企业数；回报未确认映射 / 未读到来源的企业
  - AC：✅ e2e 断言金额、合计、子树

- [x] 4. 章节映射生成器按表标题映射 + 重生成
  - 表标题 = 单体子表名 → 该子表所在章节（主章节优先；同名子表散在多章时取本合并章节投票所在章）；「续：」接上一张；定章兜底只认主章节
  - soe：167 条章节号修正、带子表名 140 → 289；listed：49 条修正
  - AC：✅ `tests/test_consol_note_section_mapping.py` 18 例（含错位回归）

- [x] 5. stale 联动
  - `NOTE_SECTION_SAVED` 按明细映射绑定找受影响的合并章节（号或标题一致）→ 交 `consol_note_value_change_service.on_note_section_saved`（新增合并项目过滤、按年度、值指纹不再跳过 values[0]）→ 每个合并项目一条 `consol.note_stale`
  - 根因修复：`disclosure_notes` 更新事件 `section_code` 原为 `getattr(note, "section_code")`（模型无此属性）⇒ 恒为记录 id，stale 引擎 / 交付件 / 合并附注订阅全部对不上章节；改取 `note_section`，handler 仍兼容记录 id
  - AC：✅ e2e 3 例

- [x] 6. 删除 v2 重复写入器与假测试，清理前端
  - 删 `consol_note_aggregator.py`（写入器 + 已被读取层取代的读取工具）与 `test_consol_note_aggregator.py`；行数白名单删条目
  - `ConsolNoteTab`：恢复「重新汇总」原提示（响应里从没有 leaf_summary）、提示文案改为如实说明是公式重算、来源标签改认 `detail_mapping`；公式管理面板路径说明更正
  - 明细映射弹窗显示企业来源读取问题与 apply 未计入企业；模板编辑器带上建议别名
  - 公式内核删除无读取方的 `_cell_sources`
  - 🔴 顺带修复（HEAD 即坏）：明细映射弹窗 `empty-text="请先点击"刷新预览"…"` 引号嵌套 ⇒ 模板编译失败，`ConsolNoteTab.spec` 整个套件收集即失败、浏览器里合并附注页加载不了该组件；`apiPaths/formula.ts` 注释被截断成 `*/（…） */` ⇒ esbuild 转换失败，引用它的组件测试全挂；`ConsolNoteTab` 用 `confirmBatch` 却没导入 ⇒ ReferenceError 被「用户取消」的 catch 吞掉，合并附注「删除行」恒静默无效（迟到确认用例因此假绿，已补正向用例）；`consol-note-mapping-changed` 补进 eventBus 事件类型；两处 el-tag 空串类型
  - AC：✅ vitest 合并附注相关 4 文件 51+38 passed；ESLint 0 error（5 条 warning 均为 HEAD 既有）；单区域 vue-tsc 0 error（变异注入 TS2322 能报出）

- [x] 7. 端到端测试 `tests/services/test_consol_note_pull_e2e.py`（全程调用生产函数）
  - 真实形态：安徽式 `_tables` + 宜宾式 workpaper 投影（行名「现金」→ 别名）；三层树中间节点子树；预览后结构变化 409；stale 定位 / 记录 id 回查 / 无关章节不标；上市集团 + 国企子企业
  - AC：✅ 9 例；进程内注入 5 个下层变异（首列错位 / 不换算章节号 / 不限子树 / stale 不看章节 / 不投影）全部打红

- [x] 8. 真库验证（整段一个事务，结束 rollback，零残留）
  - 【测试】公式同步集团（上市版）+ 拷入安徽 / 宜宾「八、1」真实 table_data：按标题认到 → 2 组结构 → apply 8 格、合计 9182683.29 / 29093059.01 = 数据行之和 → stale 定位 + 值变化标 is_stale
  - 读取覆盖：soe 316 个已映射合并章节 × 3 个真实单体项目 = 948：found 710（其中 234 有部分列未对上）/ unreadable 214 / missing 24

- [x] 9. 启动与迁移
  - 根因修复 4 处导入：`formula_health` / `formula_timeline` / `formula_push_verify` 从 `app.core.security` 取 `require_project_access`（应为 `app.deps`）；`note_custom_section` 导入不存在的 `app.models.disclosure`（应为 `report_models`）；去掉 router_registry 里的 try/except
  - 删除重复的 `V200/R200__consol_note_mapping_reuse_and_reference.sql`（与 V202 逐字节相同，干净检出时与 V200 partner 同号 RuntimeError）；V202 全部 IF NOT EXISTS

- [ ]* 10. 浏览器实测「📋 明细映射」完整流程（建议 → 编辑模板 → 预览 → 确认并写入 → 附注页来源标签）
  - `[ ]*` 本会话浏览器 MCP 未连接；后端链路已由 e2e + 真库事务验证

- [ ]* 11. 合并附注模板数据缺陷（模板数据修正另立 spec）
  - 五-5-1（按账龄披露应收账款）multi_header 第一层「期初数」错放到第 2 列 ⇒ 列路径出现两个「期初数/坏账准备」，读取层按歧义不填
  - 五-10（存货）混入 5 张「其他应收款」表；全章 `parent_section` 自 五-10 起错一章
  - 五-5-4 / 五-5-5 单体列名「应收账款」与合并「账面余额/金额」措辞不同 ⇒ 金额列对不上

- 范围外发现（HEAD 干净检出复现，未改，归各自 spec）
  - `ai_content.py`：调用不存在的 `ai_content_log_service.get_by_id` ⇒ AI 内容确认 / 修订 / 驳回端点全部 500（12 例红）；同文件 `from app.services.consol_lock_service import check_consol_lock` 模块不存在，且应按关键字调用 `app.deps.check_consol_lock`
  - `note_section_pairing.py` 导入不存在的 `resolve_alias_counterparts`（matcher 里是单数 `resolve_alias_counterpart`，返回值形态也不同）
  - `test_disclosure_note_edit_stamp.py` 8 例 setup 错误：patch 的 `disclosure_notes._assert_project_edit` 已不存在
  - `test_consol_note_headers.py` 147 例红（合并模板表头与 Word 权威表头对不上，与 Task 11 的模板数据缺陷同源）

- [ ] 12. 待用户拍板（拍板后落地）
  - ①「🔄 重新汇总」保持公式重算（ADR-CNFO-006）还是改为对本节点全部已确认章节批量执行明细映射 apply
  - ② 同一合并章节「个别数（明细映射）」与「调整 / 抵销（公式内核）」如何合成：现在两条路径整表后写覆盖先写
  - ③ 旧 V2 汇总服务（mock CSV、`disclosure_notes.section_id` 口径、`CONSOL_NOTES_V2_ENABLED=False`）、`resolve_consol_aggregation`、`useNoteAggregation` / `ConsolNoteTreeEnhanced`、无界面的 V202 值确认端点：退役还是接线

## 附：v2 任务原文（已被 v3 取代；✔ 仍成立 / ✘ 已删除或勘误为不成立）

- ✔ 1.1 生成脚本 / 1.3 运行时映射服务 / 1.4 映射测试 —— 保留，v3 Task 4 改为按表标题映射
- ✘ 1.2「仅 6 个 consol_only」—— 按 parent 映射的匹配率掩盖了五-10 起错一章
- ✘ 2.1~2.4 读取工具（sub_table_data 优先 → _tables → 首表兜底）—— 首表兜底会取错表、自写 F2/F3 解析与投影器重复；由 v3 Task 1 取代并删除
- ✘ 3.1~3.4 `aggregate_section` 等 —— 与 V186 重复的写入器，已删除
- ✘ 4.1~4.3 `reaggregate_from_standalone` 与端点改造 —— 端点从未改动（假绿），已删除
- ✘ 5.1 前端解析 leaf_summary —— 响应里从没有该字段，已恢复原提示；5.2 随之作废
- ✘ 6.1 / 6.3 汇总器测试与「端到端」—— 端到端在测试里重写循环（假绿），已删除；6.4 由 v3 Task 7 / 8 取代
- ✘ 7.2「API 实测通过」与 Phase 2「API 实测」—— 测的是公式内核
- ✘ Phase 2 stale 联动（按 `parent_project_id` 找上级、读 `extra.note_section`）—— 企业树早已不读 parent_project_id、发布方给的是 section_code，由 v3 Task 5 重做
- ✘ 启动修复「try/except 包住路由注册」—— 由 v3 Task 9 根因修复取代
