# Design Document

## Current closure scope
D4-30/31/32 must use the unified sync bridge and registered providers before OnlyOffice is advertised. D4-32 unknown groups are a visible, durable intermediate state: preserve source label and row identity, expose explicit human mapping, and never silently discard or reclassify rows. D4-29 is explicitly out of scope for this continuation and existing dirty D4-29 changes must remain untouched.

D4-29 为客户粒度 `D4-29-rows`；D4-30 为 `{customers,customDimensions}` 转置矩阵；D4-31 为单份 `InterviewData` 问卷，保留多选数组 `q1_relation` 与四章节；D4-32 为六组 `GroupData` 流水。源 xlsx 逐 sheet 核定后才能确定列头和稳定 row/column ids。

## Architecture
IO 使用 `_d4_import_export.py` 专用 parser/exporter 与正确 item_id 映射，前端使用 `useD4ImportExport`。D4-29 的客户导入必须先核定 D4-2/D4-3 的真实客户明细来源，禁止沿用错误的 `D2-detail-rows` 路径或产品汇总替代客户粒度。D4-30 维度列与 customDimensions 合并保留；D4-31 单行 gate 保留问卷结构和 q1_relation 数组；D4-32 通过显式分组列恢复六组，未知值进入人工映射。

公式由 F-SHELL effective definition 统一治理，preset/custom 可编辑 expression/refs/params；后端权威执行，前端预览，Excel 投影同声明。统一平台 mutation、sync、三方合并、contract/representation/durable ack。IPO 风险先形成发现记录，人工确认方向/金额/证据后才调用 `useD4InspectionWriteback`；A13 与 D4-1 说明使用独立持久 ack、source identity、去重、重试和防回环。

## Boundaries
不得把整笔客户收入、资金流水或 amount=0 描述项自动推 A13；不得把 reason/“否”非空当异常；不得猜未知分组/科目；不得丢动态 id、问卷多选或自定义维度；不得以 A13 代替双模式同步或以 Excel 优先。

## D4-29 observer repair continuation
本次用户明确重开 D4-29，覆盖此前 continuation 的排除声明。真实 store 为 `D4-29-customers`。复现专用测试 1 failed / 6 passed：磁盘 contract 与 provider instrumentation digest 不一致，provider 当前关闭转置表。
转置 sheet 必须由真实 workbook-scope definedName `GT_MANAGED_REGION_D429` 定位，固定模板范围 `$C$10:$M$41`，客户允许扩至 N 列之后。运行态仅按冻结 name 解析物理 sheet；禁止伪造 Table、按中文展示名兜底或将客户列号当作行号。
第 9 行 GT-CUSTOMER-{id} 必须为隐藏字面量，空客户合法；有业务值却缺身份、重复或公式身份均拒绝，不能静默解释为客户删除。29 个字段按 transposed_row 物理行校验，发布与请求共用观测；hash 前拒绝 fingerprint errors 和不完整结构清册。
锚须在实际 instrumentation 编译中注入，并纳入冻结清册。新 definition/bundle/representation 走正式升级及 finalize；禁止更改旧 hash、禁用触发器或运行临时 heal 脚本。真实 OO 验收仍属 task 7，必须有 callback、revision 和 operation 实证才完成。

### Task 2 implementation boundary
主 ExcelInstrumentationSpec 通过独立 transposed_sheets 声明传递转置载体，真实 instrument_workbook_bytes_multi 编译写入 workbook.xml；普通 instrumentation_specs 仍只表示 Table，避免通用行绑定误收转置表。冻结 instrumentation 与首版 anchors_from_instrumentation_specs 同时展开转置声明。
collect_workbook_structure 为发布与请求唯一采集入口：普通 Table 关联与转置 definedName 分派，转置先校验原始 XML 中锚的唯一性、全局作用域、固定范围及真实工作表，再检查隐藏身份行与客户身份，逐字段核实物理转置行两端单元格。结构清册完整性与 fingerprint errors 均在 hash 前校验。物化只从稳定锚定位；首次模板含预置客户标题，因此不能把物化前模板当业务客户反读，客户读回与观测始终严格拒绝缺失/重复身份。
本次只生成源码 contract，不发布数据库 definition/bundle/representation，不改既存 hash；真实 OO 验收继续留 task 7。
