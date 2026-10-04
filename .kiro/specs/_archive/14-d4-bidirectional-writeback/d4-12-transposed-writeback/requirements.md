# Requirements — D4-12 合同检查表 转置双向回写

## 背景与现状（2026-09-21 逐文件/openpyxl 实测冻结，非推断）

D4-12「合同检查表」是**转置动态表**：一列 = 一份合同（entity），一行 = 一个字段。与已落地的 D4-29「客户信息检查表」同范式。目标是把 D4-12 从 legacy 单向 `GtOnlyOfficeSheet` 升级为走统一 `useWorkpaperSyncBridge` + 转置引擎的真双向 sheet。

### 现状实测证据（承重锚点，实现时以此为准）

- **源模板** `backend/wp_templates/D/D4-12 营业收入-合同检查（Leap-常规程序）.xlsx`，唯一 sheet `合同检查表D4-12`，dims `A1:K57`。
- **转置几何**（openpyxl 实读冻结）：
  - 表头行 **R10**：`A10=索引号`，`B10..K10 = D4-12-1 .. D4-12-10`（模板预画 **10 个合同列 B–K**，A 列是字段标签列）。
  - 字段行 **R11–R31 = 21 个字段**（合同编号 / 交易对方名称 / 合同签订日期 / 服务内容 / 合同金额 / 交货时间 / 交货方式 / 结算方式 / 结算时间 / 质量保证条款 / 销售退回条款 / 违约条款 / 特殊约定 / 是否签字 / 是否盖章 / 时段法时点法 / 验收条款 / 收入确认时间 / 控制权转移单据 / 是否特定交易 / 结论）。
  - R32 `三、审计说明`、R36 `四、审计结论`、R38+ 编制提示 = footer 下静态文本（HTML-only）。
- **前端** `D4TabContract.vue` + `useD4ContractInspection.ts`：store 键 `D4-12-contracts-v2`（`ContractInspectionItem[]`，**已有本地行身份 `id`**=`c-{ts}-{rand}` + `indexNo`=`D4-12-N` + 21 业务字段 + 附件 OCR 字段）；在线编辑当前挂 **legacy `GtOnlyOfficeSheet`**（`sheet-name=合同检查表D4-12`），**未接** sync 桥；持久化走 `window.dispatchEvent('d4:save-items')` + 2s debounce。
- **后端行式 IO** `_d4_import_export.py`：`_SHEET_HEADERS["D4-12"]` 存在但只有 12 列（行式导入导出用，**非转置几何**）；无 `_parse_d4_12_row`（走 generic）；item_id 映射两处写死 `D4-12 → D4-12-contracts-v2`。
- **契约/宿主登记**：`backend/data/workpaper_sync_contracts/d4.revenue_detail.json` 中 `d4-12`/`d412` **零命中**；`isD4DedicatedSyncSheet`（`GtD4OperatingRevenue.vue`）**不含 'D4-12'**。

### 🔴 两处前置阻塞（本 spec 落地的硬约束）

1. **转置引擎完全绑死 D4-29**（`adapters/excel.py` 4 处旁路 + `is_enabled` 双重硬编码 `contract_id=="d4.revenue_detail"` + `sheet_key=="d4-29-managed"`；provider 全部几何常量/definedName/载体行硬编码）。落地 D4-12 必须先**泛化**这条转置轴，且**不得回归 D4-29**（逐字节 / 反读逐字段）。
2. **D4-12 源模板缺两件转置前置**：①无 workbook-scope RANGE definedName（实测只有 sheet-scoped `_xlnm.Print_Area` + 一堆 `#REF!` 垃圾名，无 `GT_MANAGED_REGION_D412`）；②无隐藏身份载体行（D4-29 是 R9 隐藏行存 `GT-CUSTOMER-{id}`）。两者须由 instrumentation 注入（源模板不手改，与 D4-29 一致由代码注入）。

### 关键裁决（DEC）

- **DEC-1（复用转置轴，不用 static-region 轴）**：D4-12 走「转置 provider + is_enabled 判据」既有轴（同 D4-29），**不**进 `BindingKind` enum（转置表刻意不构造 `ExcelIdentityBinding`，见 `excel_extract.py` 注释）。static-region 轴（D4-8/D4-33）是另一回事，不复用。
- **DEC-2（泛化而非复制）**：把 D4-29 provider 抽成参数化「转置表规格」（`TransposedSheetSpec`），D4-29 与 D4-12 各实例化一份；`is_enabled` 改为「命中哪个 spec / None」的注册表分派。**禁止**把 D4-29 provider 整体复制一份改名（会造第二套引擎，违单源铁律）。
- **DEC-3（行身份稳定化）**：前端 `id` 目前 `c-{ts}-{rand}` 是临时值，本 spec 须保证跨会话稳定 + 安全（不含 `/~{}`、唯一），写入隐藏载体行 `GT-CONTRACT-{id}`。
- **DEC-4（首列 = B）**：D4-12 第一合同列是 **B**（A 是字段标签列），与 D4-29 首列 C 不同——泛化 spec 的 `first_entity_column` 必须参数化，不能沿用 D4-29 的 C。
- **DEC-5（21 字段几何以模板为准）**：字段↔行号映射以 R11–R31 实测为准（21 条），**不**用后端行式 `_SHEET_HEADERS["D4-12"]` 的 12 列（那是导入导出投影头，非转置物理行）。
- **DEC-6（footer 下文本 HTML-only）**：R32/R36 审计说明/结论 + R38+ 提示保持 HTML-only，不进转置受管区（同 D4-29 `protected_regions.static_prompt`）。

## Requirements

### Requirement 1: 转置引擎泛化（GENERALIZE，不回归 D4-29）
**User Story:** 作为平台维护者，我要把绑死 D4-29 的转置引擎泛化为可复用的转置轴，以便 D4-12（及未来同类转置表）复用同一引擎而不复制代码。

#### Acceptance Criteria
1. WHEN 抽取 D4-29 的几何/身份常量 THEN 系统 SHALL 产出一个参数化 `TransposedSheetSpec`（含 managed_sheet / sheet_key / table_key / template_id / store_item_id / header_row / field_rows(有序字段↔行号) / footer_rows / static_prompt_first_row / first_entity_column / initial_entity_column / identity_carrier_row / identity_carrier_prefix / defined_name / managed_ref / identity_key），D4-29 由该 spec 实例化。
2. WHEN `is_enabled(contract)` 被调用 THEN 系统 SHALL 改为在转置 spec 注册表中查找命中的 spec（返回 spec 或 None），而非返回写死 D4-29 的布尔。
3. WHEN `adapters/excel.py` 的 4 处转置旁路（materialize 单 binding / materialize 多 binding / extract / verify_unmanaged_regions）执行 THEN 系统 SHALL 按注册表逐命中 spec 分派（支持同 contract 多张转置 sheet 各自 materialize/extract/before-副本重投影）。
4. WHEN 泛化落地后跑 D4-29 回归 THEN 系统 SHALL 保证 D4-29 materialize 产物 sha256 逐字节 == 泛化前、extract 反读逐字段 == 泛化前、`EXPECTED_MAPPING_DIGEST`（D4-29）逐字符不变。
5. WHEN 变异反证（把泛化改回写死 D4-29 单例 / 让注册表只认 D4-29）THEN D4-12 命中断言 SHALL 变红、D4-29 回归 SHALL 保持绿。

### Requirement 2: D4-12 模板 instrumentation（注入前置）
**User Story:** 作为编制人，我要 D4-12 模板在注入后具备转置引擎所需的 definedName 与隐藏身份载体行，以便受管列能被唯一定位、合同行身份能被稳定携带。

#### Acceptance Criteria
1. WHEN instrumentation 处理 D4-12 THEN 系统 SHALL 注入 workbook-scope（无 localSheetId）RANGE definedName `GT_MANAGED_REGION_D412`，几何 = 合同列区 `$B$10:$K$31`（首列 B、末预留列 K、字段行到 R31）。
2. WHEN instrumentation 处理 D4-12 THEN 系统 SHALL 在合同列区上方注入隐藏身份载体行（行号 = spec.identity_carrier_row），逐合同列写 `GT-CONTRACT-{id}` + locked protection。
3. WHEN `resolve_managed_sheet` 校验注入产物 THEN definedName SHALL 唯一 + workbook-scope + type=RANGE + 几何等于 managed_ref；违反 SHALL fail-closed（窄异常）。
4. WHEN instrumentation 注入 THEN 系统 SHALL 不手改源模板磁盘文件（与 D4-29 一致，注入发生在 materialize/provision 链路的运行时字节上）。
5. WHEN 注入触发既有 Tier-A 保鲜门 THEN 系统 SHALL 刷新 gate digest 并重跑重新实证（不得绕过）。

### Requirement 3: D4-12 provider + 契约登记
**User Story:** 作为编制人，我要 D4-12 的合同列经转置 provider 双向读写，以便在线编辑 OO 改的合同列能回写 HTML store、HTML 改的能投影到 OO。

#### Acceptance Criteria
1. WHEN D4-12 provider 实例化 `TransposedSheetSpec` THEN 系统 SHALL 用实测几何（managed_sheet=`合同检查表D4-12`、sheet_key=`d4-12-managed`、table_key=`contract_inspection_transposed`、template_id=`D412`、store_item_id=`D4-12-contracts-v2`、header_row=10、first_entity_column=`B`、initial_entity_column=`K`、identity_carrier_row=注入行、field_rows=R11–R31 的 21 条有序映射、identity_key=`id`）。
2. WHEN provider 生成 store projection THEN stable_key SHALL = `contract_inspection_transposed/{id}/{field_key}`，row_key = 合同 id，`row_keys[table_key]` = 合同 id 序列。
3. WHEN materialize 写盘 THEN 系统 SHALL 逐合同写列（超出预留列 K 用样式克隆扩列，同 D4-29 `_copy_column`）、载体行写 `GT-CONTRACT-{id}` 隐藏 + locked、字段格按 field_rows 写值、sheet protection=True。
4. WHEN extract 反读 THEN 系统 SHALL 要求载体行 hidden、carrier 以 prefix 开头且非公式、字段格非公式，返回 `[{id, <21 字段>}]`；占位空列（模板预画的 `D4-12-N` 空槽）SHALL 被识别为非业务列跳过而非报错。
4a. WHEN 合同金额字段（`contractAmount`）反读 THEN 系统 SHALL 保持数值语义（空值往返仍为空/0 按 value_type 约定，不静默投 0 覆盖）。
5. WHEN 契约 `d4.revenue_detail.json` 重生成 THEN 系统 SHALL 新增 `d4-12-managed` sheet descriptor（locator=defined_name_ref、layout=customer_columns 或等价转置 layout、transposed_columns、protected_regions、21 字段 transposed_row 映射）+ sibling store item（`D4-12-contracts-v2`）；`assert_contract_file_matches_source` SHALL OK；D4-12 的 mapping_digest SHALL 冻结。
6. WHEN 契约新增后跑既有 D4 entry THEN 系统 SHALL 不打挂同 entry 其它张（D4-2/3/29 等 store-projection 不因 D4-12 返 500）。

### Requirement 4: 发布链（provision + rematerialize）
**User Story:** 作为发布者，我要 D4-12 的 representation 真实发布到 live PG，以便宿主能对含 D4-12 的 entry materialize。

#### Acceptance Criteria
1. WHEN 跑发布链 THEN 系统 SHALL 依次 `generate_phase5_d4_contract.py --apply` → provision → `d43_rematerialize --apply`，判据查库不看退出码。
2. WHEN rematerialize 完成 THEN entry 当前 bundle SHALL = desired（含 d4-12-managed）、generation++、无 `RoundtripEquivalenceError` / `FooterAnchorDriftError`。
3. WHEN D4-12 加入后整册 materialize THEN 系统 SHALL 在 materialize soft_limit（120s，Wave 5 后基线 ~82s）内不抛 `MaterializeSoftTimeoutError`（不得为过关而提高 soft_limit）。
4. WHEN 发布后真栈 GET store-projection THEN 系统 SHALL 返 200 且 field_count 含 D4-12 的转置字段。

### Requirement 5: 前端接桥 + 宿主登记
**User Story:** 作为编制人，我要 D4-12 在线编辑走统一同步桥，以便双向回写生效且不叠加 legacy 双切换器。

#### Acceptance Criteria
1. WHEN `D4TabContract.vue` 在线编辑模式渲染 THEN 系统 SHALL 用 `useWorkpaperSyncBridge`（entryId=`xlsx/gt-d4-operating-revenue`、sheetKey=`d4-12-managed`、capability=`capabilityForEntry(...)`）+ `WorkpaperSyncEditorHost`，替换 legacy `GtOnlyOfficeSheet`。
2. WHEN flushHtml THEN 系统 SHALL 先 `flushPendingSave` 再 `readStoreProjection`（防投影旧值）。
3. WHEN 宿主 `GtD4OperatingRevenue.vue` 渲染 D4-12 THEN `isD4DedicatedSyncSheet` SHALL 含 'D4-12'（子组件自管切换器，宿主不叠加 legacy）。
4. WHEN OO 不可用 THEN 系统 SHALL fail-visible（同步态三态中文 tag），表格/卡片视图 CRUD 不受影响。
5. WHEN 行身份 id 生成 THEN 系统 SHALL 稳定 + 安全（不含 `/~{}`、唯一、跨会话不变），OCR 合并 / CRUD 保持既有能力不回归。
6. WHEN 既有 OCR/AI/导入导出/合同卡片能力 THEN 系统 SHALL 全部保留不回归（本 spec 只加双向同步，不重建已通链路）。

### Requirement 6: 守卫、变异与真栈验收
**User Story:** 作为质控，我要机器化守卫钉死泛化不回归 D4-29、D4-12 转置往返正确、消费侧接线完整。

#### Acceptance Criteria
1. WHEN 后端守卫 THEN 系统 SHALL 覆盖：`TransposedSheetSpec` 注册表分派（D4-12/D4-29 各命中自己）、D4-12 materialize→extract 往返逐字段一致、占位空列跳过、载体行 hidden 强校验、公式格拒绝、契约 parse 含 d4-12-managed。
2. WHEN OO→HTML 消费侧（`oo_to_html` mirror）THEN 系统 SHALL 覆盖第四维判据（转置 store item 被 mirror 正确消费 + merge 基线非空，防静默不回写）。
3. WHEN 变异反证 THEN 系统 SHALL 对 ≥4 锚点四态判定 RED：把泛化改回 D4-29 单例、first_entity_column 改回 C、去 identity carrier hidden 强校验、契约去 d4-12-managed。
4. WHEN D4-29 回归 THEN 系统 SHALL 全绿（materialize 逐字节 / extract 逐字段 / mapping_digest 不变）。
5. WHEN 真栈 e2e THEN 系统 SHALL 在 env 可用时产 `evidence/.../D4-12.json`（L1 统一路径 + L2 转置往返）；env 不可用（OO canvas 非 DOM）SHALL 如实标 `UNVERIFIABLE` 不假绿，往返正确性由后端 materialize→extract 单测 + 发布链真 PG 无 `RoundtripEquivalenceError` 保证。

### Requirement 7: 收口与清册同步
**User Story:** 作为维护者，我要落地后清册与 spec 三件套一致、产物全部入库。

#### Acceptance Criteria
1. WHEN 落地完成 THEN `docs/operations/d4-bidirectional-writeback-inventory.md` 中 D4-12 SHALL 从「⏸ 待专项 spec」转对应态（✅ 三维代码全绿 / 真 OO env 门），统计段（32→33 张三维全绿、⏸ 2→1 张）同步更新。
2. WHEN 收口 THEN spec 三件套 SHALL 过结构校验（Property 整数、Validates X.Y、waves JSON 唯一），行数门禁同步，全部正式产物无 `??` 未跟踪（provider + 泛化改动 + 契约 + 前端 + 守卫全部 `git add`）。
3. WHEN 泛化解除了其它 spec 的阻塞 THEN 两边 tasks.md + 清册 SHALL 同步登记（如 D4-14 若也走转置轴，标注可复用本 spec 的泛化成果）。
