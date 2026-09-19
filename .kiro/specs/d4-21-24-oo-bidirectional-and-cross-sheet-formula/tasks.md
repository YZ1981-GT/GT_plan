# D4-21~24 任务

## Task Dependency Graph
```json
{"waves":[{"wave":1,"tasks":[1,2],"description":"模板裁决与descriptor"},{"wave":2,"tasks":[3,4],"description":"ContentMutationService与行身份"},{"wave":3,"tasks":[5,6],"description":"各表映射与动态store"},{"wave":4,"tasks":[7,8],"description":"F-SHELL公式与溯源"},{"wave":5,"tasks":[9,10,11],"description":"导入导出、A13和验证"}]}
```

## Wave 1
- [x] 1.1 用运行时 finder/index 及权威模板逐表记录 D4-21、D4-22A、D4-22、D4-23、D4-24 的几何、公式、身份、O列保留值和 digest，形成裁决证据。（census 脚本 + evidence/T01-adjudication-census.json + T01-T02-adjudication.md；workbook 裁决=父合册 D/D4 收入底稿.xlsx）
- [x] 1.2 对每表判 full_bidirectional、limited_bidirectional 或 single_html；D4-22A 无金额/公式/身份时记录不适用，不扩代码。（四表 full_bidirectional，D4-22A single_html）

## Wave 2
- [x] 2.1 为裁决允许的表实现 descriptor、行身份和 mask；D4-21 避开 O 列，D4-23 保护 D/I/J，D4-21 保护 I/K。（phase5_d4_ipo_related_sheets.py，四表全过 contracts._parse_table；digest 锁死）
- [x] 2.2 将 HTML/OO 同步接入 ContentMutationService，带版本、三方合并、durable callback；冲突/身份失败 fail-closed。（接入主模块 contract/instrumentation/store projection；live 激活：新 bundle + 重投影 gen4，attach OK，store 无损；OO→HTML bridge 泛型自动覆盖）

## Wave 3
- [x] 3.1 D4-21/22/23/24 对齐各自 store；D4-22 分槽保留 peers/transportExpense；同业列使用 `{slot}_{seq}`。（D4-21 已对齐 12 canonical 键 + 派生剥离；D4-24 内联类型 9 字段+rowId 改 canonical 名（seq 派生列豁免）；D4-23 收敛到唯一活实现 useD4InvoiceCompare + item_id D4-23-rows（修 loadData 读旧键的真 bug + getSummary/rowClassName 功能性残留）；D4-22 加 toPersistedRows 展平层（label→metricName、analysis→rationality、peers[i]→peer_${i+1}）+ loadData 逆投影。守卫 8 passed，三表各做变异检验 RED；vue-tsc 0 错误。详见 evidence/T3-store-field-alignment.md。🔴 useD4Ipo.ts 全面死代码（零 .vue 引用）未删，超本 spec 范围登记待单独任务）
- [x] 3.2 D4-21/24 专用 parser/export 按列头处理；D4-21 模板-only 列显式登记，派生列不采信。（_parse_d4_21_row/_parse_d4_24_row + export 分支；差异率派生列 import 不采信；round-trip 测试绿；D4-22 补入 useD4ImportExport union）

## Wave 4
- [x] 4.1 通过 F-SHELL 建立 preset/custom/effective definition、refs、params、version/hash 和失败状态；物理 OO 公式不重复入库。（四表内部 I/K/D/I/J 差异率是 OOXML 公式入 FORMULA_MASK、不复制进 wp_formula；preset/custom/effective/失败隔离/stale 复用平台 WpFormulaService+formula_runtime+Tier A resolve_effective）
- [x] 4.2 用 four_table scope/叶子聚合取数；D4-21 读取 D4-1 canonical snapshot；导航 refs 与公式 refs 分离但可追溯。（render _mirror_d4_1_revenue_to_d421 把 6001 Tier A 有效定义结果镜像到规范键 D4-21-revenue-audited；移除禁读旧键；单测+变异检验 RED）

## Wave 5
- [x] 5.1 溯源从 cross_wp_references 读取，补条目只增不删；D4-24 D2 引用先完成语义裁决。（cross_wp_references.json +2 navigation 条目 D4-24→E1-31/D2-7，formula=None 与公式 refs 分离；只增不删断言 + 消费方解析验证）
- [x] 5.2 A13 只消费 logic_check IssueItem，复用共享件并锁定 6001/营业收入。（复用 useD4InspectionWriteback，默认锁 6001/营业收入，唯一消费者 useA13MisstatementBridge；D4-24/D4-21 推送测试绿）
- [~] 5.3 运行 projection/OOXML/DB formula/stale/round-trip 守卫及 Playwright 四表实测；校验 AC 引用、唯一 waves JSON、任务为数字且未勾选。
  - **前端接桥缺口已补（2026-09-20，批次A）**：Wave 2.2 只做了后端 contract/instrumentation/store projection + OO→HTML 泛型覆盖，但前端宿主此前仍是 legacy `GtOnlyOfficeSheet` + 本地 `editorMode` ref（inventory 记的「半接入」= 主控 §6.4 假双向，OO→HTML 统一路径未消费）。批次A 把 D4-21(`D4TabRelatedPrice`)/D4-22(`D4TabIpoIndicator`)/D4-23(`D4TabInvoiceCompare`)/D4-24(`D4TabThirdParty`) 四组件从 legacy 迁到 `useWorkpaperSyncBridge` + `WorkpaperSyncEditorHost`（sheetKey d421~d424-managed，flushHtml 内 flushPendingSave 先于 readStoreProjection）；4 个 composable 补 `flushPendingSave`/`reload` 并暴露；宿主 `GtD4OperatingRevenue.isD4DedicatedSyncSheet` 加 D4-21~24；新增守卫 `d4RelatedIpoSyncHostWiring.spec.ts`（36 passed，含 flush 顺序/无 legacy OO/宿主登记/防恒真自检）。getDiagnostics 全 clean。→ 四表现三维全绿（REQUEST_PATH 级）。
  - **仍缺（未标 [x] 的原因）**：真 OO 往返 evidence（主控 §6.4 谓词 4-6 需真实 DB application 记录）+ Playwright 四表实测，待 start-dev.bat 全栈 + 真实 OO。


> **并发登记（D4-29 schema 阻塞，2026-09-13）**：`phase5_d4_29_customer_detail.py` 当前 `sheet_payload()` 返回 TableSpec 形态，却被 `phase5_d4_revenue_detail.py` 直接放入 `sheets`，缺少 SheetSpec 的 `sheet_key/excel_name/locator/tables` 包装；字段还缺 `cell`，且 `row_identity` 与 `delete_policy` 未成对声明，stable key 含 camelCase 也不符合 `_STABLE_KEY_RE`。该问题属于本 spec 的 D4-29 并发泳道，待其作者按 IPO 范式修正后再运行 D4 契约生成与 5.3 验证；本会话不修改上述实现文件。