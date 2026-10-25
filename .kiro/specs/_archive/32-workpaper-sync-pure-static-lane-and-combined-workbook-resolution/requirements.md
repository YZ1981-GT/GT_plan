# Requirements Document

## Introduction

本 spec 交付**两条互不相干的 lane**：生产代码模块集合交集为空，可独立发布、独立回滚、
**独立验收**。

**Lane A（Requirement 1 ~ 9）—— 纯静态 entry 的 instrumentation 通道。**
canary `xlsx/gt-a51-cashflow-audit` 是 `review_status == "reviewed"` 分母下**唯一**
「整个 entry 无任何动态行表」的 entry（现算 reviewed 分母 **51** 份、唯一成员
`a51.cashflow_audit.json`；两数均为写作时刻快照，实现时须重算并禁写死）。它的四条
definition 已 `approved` 落库，但 instrumentation 管线现算有 **6 处**预设「每个 entry
至少有一张动态行表」：注入器、spec 构造校验、payload 构建、substrate 组装、身份 binding、
以及请求期观测清册。本 lane 把静态支从「寄生在动态 primary 上」上提为平台一等通道，
使 canary 走完发布链并通过一次真栈往返。

**Lane B（Requirement 10 ~ 16）—— 合册命名的 wp_code 解析。**
`backend/wp_templates/A/` 下的合册「一个文件装两个 wp_code」，其第二个码在
`wp_template_finder` 里解析不到自己所在的册：`find_template_file_any` 返回 `None`
（可见失败），`find_template_file` 返回**错的册**（静默错答，更坏）。根因是两层叠加，
且平台既有的 A-only 子码正则同时是 D/E/F 十九本合册**得以工作**的原因 ⇒ 修法必须同时
评估两侧。

**Requirement 17** 是两条 lane 共用的交付纪律。

**与 design.md 的对齐关系**：本文档与 `design.md` 逐条对齐，只承接不改写其已裁决项 ——
六处阻塞的处置矩阵（3 处旁路 + 3 处加分派臂 + **零处**放宽既有校验）、digest 不变式、
DEC-3 不可绕、Lane B 两处插入点的位置与理由、两种缺陷形态禁合并、a38 两步顺序不可颠倒、
四处勘误与 slice 两字段的处置、零回归验收方式（全域差集 + 反向变异）、8 项 out of scope。

**全文判据纪律**：锚点一律用函数名 / 类名 / 常量名 / 测试方法名 / 源码形态特征，
**禁写死行号**；一切计数类判据标「现算」—— 文中出现的现算值是写作时刻的快照，实现时须重算
并以重算值为准，**禁把快照数字写死进生产代码或断言**。

## Glossary

- **Static_Spec**：`ExcelStaticOnlyInstrumentationSpec` 与 `StaticRegionSpec` 两个新增
  frozen dataclass 及其 `__post_init__` 校验（`excel_instrumentation.py`）。
- **Static_Injector**：新增函数 `instrument_workbook_bytes_static_only`
  （`excel_instrumentation.py`）。
- **Static_Payload_Builder**：新增函数 `build_static_only_instrumentation_payload`
  （`excel_instrumentation.py`）。
- **Substrate_Stager**：`stage_instrumented_substrate`（`projection_first_publication.py`）。
- **Identity_Observer**：`PublishedIdentityObserver` 及其
  `_observe_workbook` / `_build_identity_binding` / `_frozen_sheet_anchors` /
  `_collect_static_region_physical`（`published_identity_observer.py`）。
- **Structure_Collector**：`collect_workbook_structure`（`published_identity_observer.py`），
  第 3 返回值即身份清册。
- **Canary_Provider**：`phase5_a51_cashflow_audit`（A5-1 现金流量表审计 provider）。
- **Template_Finder**：`backend/app/services/wp_template_finder.py` 的两路解析入口
  `find_template_file` 与 `find_template_file_any`。
- **Combined_Book_Index**：本 spec 在 Template_Finder 内新增的合册声明码索引三函数
  `_literal_wp_codes_in_filename` / `_combined_book_covers` /
  `_find_combined_workbook_declaring` 及两个模块常量 `_RANGE_MARKERS` / `_FILENAME_CODE_RE`。
- **A_Domain_Guard**：A 域回归基线 5 个测试文件 —— `test_a51_component_type_routing.py` /
  `test_a_cycle_foundation_canary.py` / `test_a_entry_connection_blockers.py` /
  `test_a_lane2_docx_authority.py` / `test_a_lane3_runtime_exceptions.py`
  （改动前基线现算 **159 passed**，禁写死）。
- **Delivery_Ledger**：交付台账 `DELIVERED_PER_ENTRY_CONTRACTS`。数据真源是
  `app/services/workpaper_sync/adapters/delivered_contracts_ledger.py`，
  `adapters/registry.py` **仅 re-export** ⇒ 改条目改前者。
- **Slice_Manifest**：`backend/data/workpaper_sync_abcs_cycle_manifest_slice.json`，
  权威条目字段名是 `entry_id`（**不是** `entry_key`）。
- **Round_Trip_Harness**：§2.7 真栈往返验收（后端 9980 / 前端 3030 /
  `audit-onlyoffice` healthy / Playwright MCP）。
- **Delivery**：本 spec 的交付物集合（代码 + 测试 + spec 文档 + 登记）。

## Requirements

### Requirement 1: 纯静态 instrumentation 声明类型与静态语义校验

**User Story:** 作为 workpaper_sync 引擎维护者，我需要一个零行表几何的静态注入声明类型，
以便纯静态 entry 不必伪造行表几何就能进入注入管线，同时既有动态 entry 与 19 本寄生静态区
所依赖的校验一条都不被放宽。

#### Acceptance Criteria

1. THE Static_Spec SHALL 以 `StaticRegionSpec` 与 `ExcelStaticOnlyInstrumentationSpec` 两个
   frozen dataclass 新增于 `excel_instrumentation.py`，且两者的字段集合**不含**
   `first_data_row` / `last_data_row` / `footer_row` / `uuid_col` / `managed_last_col` /
   `table_name` 任何一个。
2. THE Static_Spec SHALL 与 `ExcelInstrumentationSpec` 构成兄弟关系而非继承关系，且
   `ExcelInstrumentationSpec` 的字段集合与 `__post_init__` 校验逐条保持改动前形态
   （禁给既有类加可选字段、禁把行表几何改成可选）。
3. THE `StaticRegionSpec` SHALL 恰含 `sheet_key` / `excel_name` / `template_id` /
   `defined_name` / `managed_ref` / `table_key` 六个字段，其中 `excel_name` 的语义是
   构建期选择器而非运行时锚点。
4. IF `entry_id.strip()` 为空，THEN THE Static_Spec SHALL 抛 `InstrumentationError`。
5. IF `static_regions` 为空元组，THEN THE Static_Spec SHALL 抛 `InstrumentationError`
   （纯静态 entry 至少一张静态区，否则它没有任何受管面）。
6. IF 任一 `defined_name` 不匹配合法 OOXML defined name（`[A-Za-z_][A-Za-z0-9_.]*` 且不得
   形如 A1 引用），THEN THE Static_Spec SHALL 抛 `InstrumentationError`，且异常消息含该字段
   名与实得值。
7. IF 任一 `managed_ref` 不匹配绝对矩形 `^\$[A-Z]{1,3}\$\d+:\$[A-Z]{1,3}\$\d+$`，或右下角
   坐标未同时 ≥ 左上角坐标，THEN THE Static_Spec SHALL 抛 `InstrumentationError`。
8. IF `sheet_key` / `defined_name` / `table_key` 三者中任一值在 `static_regions` 内重复，
   THEN THE Static_Spec SHALL 在构造期抛 `InstrumentationError`（把 `_collect_static_region_physical`
   在命中 >1 时的 `ValueError` 提前到构造期）。
9. THE Static_Spec 的校验面 SHALL 限定为第 4 ~ 8 条列举的静态语义项；行区间、footer 行、
   UUID 列位置三类判据不属于该校验面。
10. WHEN 遍历 `static_regions` 逐区校验，THE Static_Spec SHALL 维持不变式「已检查的区均合法
    且其三键未与更早的区冲突」。

### Requirement 2: 纯静态注入器与 DEC-3 的结构化保证

**User Story:** 作为引擎维护者，我需要一个只写 `_GT_SYNC` 与 definedNames 的注入器，
以便纯静态 sheet 拿到身份载体，同时在结构上写不出退化动态表。

#### Acceptance Criteria

1. THE Static_Injector SHALL 以签名
   `instrument_workbook_bytes_static_only(source, spec, *, gate, identity_carriers)` 新增，
   返回 `InstrumentedWorkbook`。
2. THE `instrument_workbook_bytes_multi` SHALL 一字不改，其拒空 specs 判据与六项 `primary.*`
   取值（`footer_row` / `uuid_col` / `table_name` / `table_ref` / `first_data_row` /
   `last_data_row`）逐条保留。
3. WHEN 静态注入完成，THE Static_Injector SHALL 使产物含隐藏 sheet `_GT_SYNC`，其键集合
   ⊇ `REQUIRED_GT_SYNC_KEYS`（现算 7 键，按常量现算，禁写死键数）。
4. WHEN 静态注入完成，THE Static_Injector SHALL 使 `_GT_SYNC` 的 `GT_ROW_UUID_COLUMN` 取值
   为空串 `""`，作为显式「无 UUID 列」哨兵。
5. WHEN 静态注入完成，THE Static_Injector SHALL 使产物内 `xl/tables/` 部件数与 `source`
   相等（零新增 Table 部件）。
6. WHEN 静态注入完成，THE Static_Injector SHALL 使每张受管 sheet 的列集合与 `source` 内同名
   sheet 逐列相等（零新增隐藏列）。
7. WHEN 静态注入完成，THE Static_Injector SHALL 使每个 `spec.static_regions[i].defined_name`
   在 `xl/workbook.xml` 的 `<definedNames>` 里恰出现 1 次，且其 ref 等于
   `_quote_sheet_name(excel_name) + "!" + managed_ref`。
8. WHEN 静态注入完成，THE Static_Injector SHALL 使 `assert_no_runtime_binding(pair_map)`
   通过（5 个 runtime binding 键零写入）。
9. THE Static_Injector 的签名 SHALL 只接受 `source` / `spec` / `gate` / `identity_carriers`
   四项入参，使「写 Excel Table」与「写隐藏 UUID 列」在结构上无从表达 —— DEC-3 由类型边界
   保证而非由自觉保证。
10. IF 任一 `spec.static_regions[i].excel_name` 在 `source` 内不存在，THEN THE Static_Injector
    SHALL 抛 `InstrumentationError`，且异常消息同时含缺失的 sheet 名与 `source` 内现有
    sheet 名清单。
11. IF `source` 已有同名 definedName，THEN THE Static_Injector SHALL 抛
    `InstrumentationError`，沿用既有静态支的 `Duplicate static definedName` 消息形态。
12. WHEN 静态注入完成，THE Static_Injector SHALL 使产物与 `source` 在「非 `_GT_SYNC` sheet
    的全部单元格值与公式」上逐格相等。
13. WHEN 静态注入完成，THE Static_Injector SHALL 把 `GT_MANAGED_SHEET_ID` 写成 definedName
    所指 sheet 的真实 sheetId，并保留平台既有「降级、非运行时锚点」标注。
14. THE 「静态注入正确」判据 SHALL 由第 4、5、6 条**三条同时成立**构成；单凭第 4 条成立
    即判通过 SHALL 视为不合格（那会退化成「声明了一个空的列」这种含糊态）。

### Requirement 3: 静态 payload 构建器与 digest 不变式

**User Story:** 作为引擎维护者，我需要把 Canary_Provider 里那份自组装的 static-only payload
上提到平台入口，且上提必须是纯重构 —— 已 `approved` 落库的 definition digest 一位都不能变。

#### Acceptance Criteria

1. THE Static_Payload_Builder SHALL 以签名
   `build_static_only_instrumentation_payload(*, spec, template_definition_sha256,
   template_sha256, gate, identity_carriers, identity_anchors)` 新增于
   `excel_instrumentation.py`。
2. THE `build_instrumentation_payload_for_sheets` SHALL 保持改动前形态，其拒空 specs 判据与
   `identity_carriers = list(sorted(gate.allowed_carriers))` 的取值逻辑逐条保留。
3. THE Static_Payload_Builder SHALL 从入参 `identity_carriers` 取载体清单，不从
   `gate.allowed_carriers` 推导（A5-1 的 `IDENTITY_CARRIERS` 现算 2 项，而 gate 放行 4 项，
   按 gate 推导即语义过度声明）。
4. THE Static_Payload_Builder SHALL 使返回 payload 满足 `payload["managed_sheets"] == []`
   且 `len(payload["static_sheets"]) == len(spec.static_regions)`。
5. THE Static_Payload_Builder SHALL 使返回 payload **不含** `row_uuid_disposition` 键，
   且**不含** `transposed_sheets` 键。
6. THE Static_Payload_Builder SHALL 使 `payload["hidden_metadata_sheet"]["keys"]` 等于
   `list(REQUIRED_GT_SYNC_KEYS)`，原样复用该常量而不新建静态子集。
7. THE Static_Payload_Builder SHALL 使返回 payload 通过
   `validate_instrumentation_payload()` 与 `_assert_no_forbidden_anchor_declared()`
   两道校验。
8. WHEN 以 canary 的固定入参调用 Static_Payload_Builder，THE Delivery SHALL 证明
   `canonical_digest(Static_Payload_Builder 输出)` 逐位等于
   `canonical_digest(Canary_Provider.build_instrumentation_payload() 输出)`，且该值与契约
   `a51.cashflow_audit.json` 的 `instrumentation_definition_sha256`、守卫常量
   `CANARY_INSTRUMENTATION_DEFINITION_SHA256`、真库 artifact 行三者同值
   （现算前缀 `223b5a69…`；判据以常量为锚，禁在判据文本里写死全值）。
   —— 本条是**样例判据（EXAMPLE）不是属性**：入参是单一冻结值，禁写成随机化属性测试。
9. IF 第 8 条的两个 digest 不相等，THEN THE A_Domain_Guard SHALL 打红并输出两份 payload 的
   key 级差异；修法 SHALL 限定为修 Static_Payload_Builder，改契约 / 改守卫常量 / 改真库
   artifact 去迁就 SHALL 视为不合格。
10. THE Canary_Provider `build_instrumentation_payload()` SHALL 保留为委派 Static_Payload_Builder
    的门面（使 §6 阻塞④ 的 provider 状态断言保持绿）。
11. THE Delivery SHALL 更正 Canary_Provider `build_instrumentation_payload()` 注释里「实测 60
    份契约里唯一如此的 reviewed 契约」这一过期分母，改为现算口径描述（现算 reviewed 分母
    **51**、唯一 0 动态表成员 `a51.cashflow_audit.json`），且改写后的注释**不写死**分母数字。

### Requirement 4: Substrate 组装的第三条分派臂

**User Story:** 作为引擎维护者，我需要 substrate 组装认识第三种 provider 入口，
以便纯静态 entry 进入注入阶段，同时既有 provider 一个都不改走向。

#### Acceptance Criteria

1. THE Substrate_Stager SHALL 在既有 `instrumentation_specs` → `instrumentation_spec` 两臂
   **之后**追加第三臂，读 provider 的 `static_only_instrumentation_spec`。
2. THE Substrate_Stager 既有两臂的判据与先后顺序 SHALL 逐条不变，使既有 provider 在进入
   第三臂之前即命中原臂（零行为变更）。
3. IF provider 暴露 `static_only_instrumentation_spec` 且同时暴露 `instrumentation_spec` 或
   `instrumentation_specs` 任一，THEN THE Substrate_Stager SHALL 在进入第三臂前 fail-closed
   抛错（DEC-3 的结构化守卫 —— 同时有两种 spec 意味着有人给纯静态 entry 造了行表 spec）。
4. THE 第三臂守卫判据 SHALL 限定为「有 static_only 即不得有行表 spec」这一单向蕴含；
   采用「三者恰暴露其一」的统一断言 SHALL 视为不合格（现算既有 provider 存在同时暴露
   `instrumentation_spec` 与 `instrumentation_specs` 的双入口回落形态，统一断言会打红既有
   entry）。
5. THE `validate_ooxml_artifact` 安全门 SHALL 保持在改动前的调用位置。

### Requirement 5: 身份观测器的静态主 binding

**User Story:** 作为引擎维护者，我需要主 binding 支持 defined-name 形态，
以便纯静态 entry 不再因「契约无带 `row_identity` 的表」而被判 `FrozenChildUnusableError`，
同时动态路径的判据一条不动。

#### Acceptance Criteria

1. WHEN `str(anchors.get("region_kind") or "") == "static"`，THE Identity_Observer
   `_build_identity_binding` SHALL 返回
   `ExcelIdentityBinding(defined_name=anchors["defined_name"], table_key=唯一对齐的静态
   table_key, metadata_sheet=GT_SYNC_SHEET_NAME)`。
2. THE Identity_Observer 动态路径 SHALL 逐条原样保留，含「契约未声明任何带 `row_identity`
   的表即 `FrozenChildUnusableError`」判据与 `anchors["table_name"]` /
   `anchors["uuid_column_letter"]` 两处取值。
3. IF 契约未声明任何 `row_identity is None` 的静态表，THEN THE Identity_Observer SHALL 抛
   `FrozenChildUnusableError`。
4. IF 与 `anchors["sheet_key"]` 对齐的静态表数量 ≠ 1，THEN THE Identity_Observer SHALL 抛
   `FrozenChildUnusableError` 且异常消息含匹配集合；静默取集合首元素 SHALL 视为不合格
   （静态臂与动态臂在「禁随手挑第一张」上判据对称）。
5. THE `excel_extract` 与 `excel_materialize` SHALL 零改动 —— `ExcelIdentityBinding.kind`
   是派生属性（有 `defined_name` 即 `static_region`），静态 binding 形态与 Canary_Provider
   现有 `static_identity_bindings()` 一致。
6. THE Identity_Observer `_frozen_sheet_anchors` 与 `_collect_static_region_physical`
   SHALL 零改动（现读已支持静态锚点：三集合迭代 + `region_kind == "static"` 产出，
   命中 0 或 >1 均已显式 `ValueError`）。

### Requirement 6: 第 6 处阻塞 —— 观测清册消除裸 `AttributeError`

**User Story:** 作为引擎维护者，我需要纯静态 entry 在请求期观测时拿到真实的身份清册，
以便失败以设计好的异常类型呈现，而不是以裸 `AttributeError` 呈现，并使
`identity_inventory_sha256` 对纯静态 entry 仍有反漂移意义。

#### Acceptance Criteria

1. WHEN 锚点集合内全部锚点的 `region_kind` 均为 `"static"`，THE Structure_Collector SHALL 使
   第 3 返回值为 `StaticIdentityInventory` 实例而非 `None`。
2. THE `StaticIdentityInventory` SHALL 提供 `row_uuids`（恒为空元组）与
   `inventory_digest_input`（形如 `{"kind": "static_region", "regions": [[sheet_key,
   defined_name, physical_sheet], ...]}`）两个成员。
3. THE Identity_Observer `_observe_workbook` 内
   `canonical_digest(inventory.inventory_digest_input)` 这一行 SHALL 零改动 —— 处置方式是
   **消除 `None`**，给该字段加 `None` 特判或改成 Optional SHALL 视为不合格。
4. WHEN definedName 被删除、改名、或改指向另一张 sheet，THE Structure_Collector SHALL 使
   `identity_inventory_sha256` 随之变化（证明该 digest 是真实观测值而非补出来的假值）。
5. WHILE 纯静态 entry 处于请求期观测，THE Identity_Observer SHALL 只以
   `FrozenChildUnusableError` 或 `ObservedIdentityDriftError` 形式报告静态观测失败。
6. THE Delivery SHALL 逐个现读 `PublishedObservation.identity_inventory` 与
   Structure_Collector 第 3 返回值的**全部**消费方，并证明每个消费方只使用 `row_uuids` 或
   `inventory_digest_input`；对使用其他成员的消费方 SHALL 补静态形态分派
   （不做此审计等于把 `AttributeError` 从一个站点搬到另一个站点）。
7. WHEN 锚点集合含动态 Excel-Table 锚点，THE Structure_Collector SHALL 使第 3 返回值仍为
   改动前的 `primary_inventory` 对象。
8. THE Delivery SHALL 记录第 6 处在执行顺序上**早于**第 5 处的实证（`observe()` 源码内
   `_observe_workbook` 首现位置早于 `_build_identity_binding` 首现位置；位置值现算，禁写死），
   并据此说明「静态 binding 已支持」不能作为第 6 处已完成的证据。

### Requirement 7: 既有寄生静态区与全部动态 entry 的零回归

**User Story:** 作为平台维护者，我需要确认本 lane 是纯加法，以便 19 本寄生静态区与全部动态
entry 的既有保护一条都不丢。

#### Acceptance Criteria

1. THE Delivery SHALL 使六处阻塞的处置恰为「3 处旁路 + 3 处加分派臂」，放宽既有校验的处置
   数为 **0**。
2. WHEN 对任意既有「动态 primary + 寄生 `static_sheets`」entry 重跑注入，THE Delivery SHALL
   证明改造前后注入产物逐字节相等。
3. THE Delivery SHALL 在改动前现算并列出寄生静态区 entry 的完整分母（写作时刻现算成员含
   D4-33 / D4-8 / D4-13 / D2-1 / D1-4 / E1），以该现算分母作为第 2 条的验收范围，禁写死成员
   清单。
4. THE Delivery SHALL 把 design §1.9「平台已支持纯静态」的站点清单（`validate_instrumentation_payload`
   不要求 `managed_sheets` 非空 / `_frozen_sheet_anchors` 三集合迭代 /
   `_collect_static_region_physical` / `collect_workbook_structure` 的静态分派臂 /
   `excel_extract` 四处静态分派 / `excel_materialize` 的 `_plan_static_writes` /
   `ExcelInstrumentationSpec.static_sheets` 寄生字段）作为**正面判据（对照组）**，
   把其中任一项列为待做 SHALL 视为误报。
5. THE Delivery SHALL 记录「缺口只影响整个 entry 无动态表这一形态」这一结构性理由，
   作为零回归的成立依据。

### Requirement 8: §6 守卫的同步更新与交付台账

**User Story:** 作为守卫维护者，我需要 §6 阻塞段按守卫自己写明的方向被同步更新，
以便「预判为红的三条」转绿、「预判为绿的其余条」保持绿，且台账不被提前翻成 `True`。

#### Acceptance Criteria

1. THE Delivery SHALL 执行守卫自写的三条同步动作：① 删除 §6 阻塞段；② 把 Canary_Provider 的
   static-only payload 组装上提到平台入口；③ 更新 Delivery_Ledger 里 canary 的
   `adapter_registered`。
2. WHEN Lane A 落地，THE A_Domain_Guard SHALL 恰有 3 条判据变红 —— 解除信号①
   `static_injection_entry_points(top_level_function_names(excel_instrumentation)) == ()`、
   解除信号② `"region_kind" not in _build_identity_binding` 源码、阻塞⑤
   `stage_instrumented_substrate` 源码不含 `"static"` 与 `"region_kind"` —— 且这 3 条
   SHALL 在同一 lane 内被改写为绿。
3. WHEN Lane A 落地，THE A_Domain_Guard 的阻塞①②③④⑥ 与「已达成① digest 三方相等」
   SHALL 保持绿；IF 其中任一条变红，THEN THE Delivery SHALL 判定为「放宽了既有校验」并回退
   该处改动。
4. THE Delivery SHALL 补齐 §6 两处覆盖面缺口，为 `build_instrumentation_payload_for_sheets`
   与 `_observe_workbook` 两个站点新建断言（改造后它们是「已支持静态」的正面判据）。
5. WHERE Round_Trip_Harness 尚未通过，THE Delivery_Ledger 里 canary 的 `adapter_registered`
   SHALL 保持 `False`，且对应任务 SHALL 标 `[ ]*` 并以「代码已改但未实测」措辞记录；
   先翻字段再补实测 SHALL 视为假绿。
6. WHEN 修改 Delivery_Ledger 条目，THE Delivery SHALL 改
   `adapters/delivered_contracts_ledger.py`（数据真源），`adapters/registry.py` 的 re-export
   段保持不变。
7. THE Lane A 对共享文件 `test_a_entry_connection_blockers.py` 的编辑范围 SHALL 限定为
   `TestStaticOnlyInstrumentationGap` 类及其模块级辅助（`_ROW_GEOMETRY_ATTRS` /
   `_SUBSTRATE_PROVIDER_ENTRY_NAMES` / `static_injection_entry_points` /
   `top_level_function_names`）。
8. WHEN Lane A 落地，THE Delivery SHALL 重跑 A_Domain_Guard 全部 5 个文件（改动前基线现算
   159 passed，禁写死），只跑单个文件 SHALL 视为不合格；允许的红只有第 2 条列举的 3 条。
9. THE Delivery SHALL 同步更正顶部阻塞表「五处全预设」这一计数（平台代码站点现算 **6** 处；
   §6 现有 6 个断言方法里 `test_a51_provider_has_no_row_spec_by_design` 断言的是纯静态的
   **正确状态**，不是平台阻塞）。

### Requirement 9: Canary 的真栈往返验收

**User Story:** 作为交付负责人，我需要一次真栈往返，以便确认接线在运行时真的通了 ——
`getDiagnostics` 通过与单测全绿都抓不到运行时接线问题。

#### Acceptance Criteria

1. WHEN Round_Trip_Harness 执行，THE Delivery SHALL 完成四步且缺一步不算通过：
   ① 在 HTML 侧改一个 editable cell 并保存；② 同步到 OnlyOffice 并在 OO 侧读到同值；
   ③ 在 OO 侧改另一个 editable cell 并保存；④ 回读 HTML，两处值都与各自最后一次写入相等。
2. WHEN Round_Trip_Harness 的四步完成，THE Delivery SHALL 证明契约标 `protected` 的公式列
   未被覆盖（现算：审定表公式列 G 共 8 个 + 勾稽核对公式列 B 共 7 个；两数现算，禁写死）。
3. WHEN Round_Trip_Harness 的四步完成，THE Delivery SHALL 重新观测并证明
   `recomputed_structure_hash` 与发布时冻结值相等（证明往返未改动结构）。
4. THE Delivery SHALL 在执行前现算 A5-1 契约的 editable 字段分母（写作时刻现算 **24** 个），
   并从该分母内选取第 1 条的两个 cell。
5. WHERE Round_Trip_Harness 依赖的环境不可用（后端 9980 / 前端 3030 / `audit-onlyoffice`
   healthy / Playwright MCP 任一缺失），THE Delivery SHALL 把该任务标 `[ ]*` 并如实记录
   「待环境」，且 Requirement 8 第 5 条的 `adapter_registered` 保持 `False`。
6. THE Round_Trip_Harness SHALL 按 INTEGRATION 处理并执行 1 次；把它写成随机化属性测试
   SHALL 视为不合格（依赖真 OO 与真浏览器，100 次迭代不增加缺陷发现率）。

### Requirement 10: 合册声明码索引纯函数

**User Story:** 作为模板解析维护者，我需要一个纯路径、无副作用的合册声明码索引，
以便「一个文件装多个 wp_code」的册能被它承载的每个码找到，而范围式命名一个都不误认。

#### Acceptance Criteria

1. THE Combined_Book_Index SHALL 以 `_RANGE_MARKERS` / `_FILENAME_CODE_RE` /
   `_literal_wp_codes_in_filename` / `_combined_book_covers` /
   `_find_combined_workbook_declaring` 五个**模块私有**符号新增于 Template_Finder；
   不进模块末尾的覆盖层薄封装，不新增公开入口。
2. THE `_literal_wp_codes_in_filename` SHALL 是纯函数：不读磁盘、无副作用、对同一输入恒等
   输出。
3. WHEN 文件名 stem 含 `_RANGE_MARKERS` 任一字符（现算成员「至」/ `~` / `～`），
   THE `_literal_wp_codes_in_filename` SHALL 返回空集（fail-closed，不做范围展开 ——
   `D4-1至D4-4` 字面只有 D4-1/D4-4，当声明集用会漏 D4-2/D4-3）。
4. WHERE 文件名 stem 不含任何 `_RANGE_MARKERS` 字符，THE `_literal_wp_codes_in_filename`
   SHALL 返回 `_FILENAME_CODE_RE` 在该 stem 上的全部匹配去重集。
5. IF 某文件名的字面声明码数 < 2，THEN THE `_combined_book_covers` SHALL 返回 `False`
   （只声明一个码的册不是合册，不参与本节逻辑）。
6. THE `_combined_book_covers` 的祖先规则 SHALL 用 `wp_code.startswith(code + "-")`
   判定，使请求码 `A3-80` 不被声明码 `A3-8` 命中。
7. THE `_find_combined_workbook_declaring` SHALL 只在 `TEMPLATES_DIR / wp_code[0]` 目录下
   枚举后缀为 `.xlsx` 或 `.xlsm` 的文件，按 `(len(name), name)` 确定性排序取首个，
   且全程不读 xlsx 字节。
8. WHERE 同一 wp_code 被两本及以上合册声明，THE `_find_combined_workbook_declaring` SHALL
   取确定性排序的首个，且 THE Delivery SHALL 为该情形建立「可记录、可复现」的判据
   （该情形现算 **0** 例，判据用于将来出现时不依赖 `iterdir()` 枚举顺序）。
9. THE Combined_Book_Index SHALL NOT 实现范围式命名的码展开（A 域现算 **0** 本范围式合册；
   D/E/F 的 19 本范围册现算 **0** 缺陷）；扩展点留在 `_RANGE_MARKERS` 的 fail-closed 上，
   使将来出现 A 域范围册时表现为「不认」而不是「认错」。

### Requirement 11: 两处插入点与既有解析行为的不变性

**User Story:** 作为模板解析维护者，我需要新逻辑以加法方式插在两条链的精确位置，
以便当前能解析的码走向一律不变，只有当前失败的码进入新步骤。

#### Acceptance Criteria

1. THE Template_Finder `find_template_file_any` SHALL 在「A 子码严格分支」的两次同名前缀
   尝试**之后**、`return None` **之前**插入 `_find_combined_workbook_declaring(wp_code)`。
2. THE Template_Finder `find_template_file` SHALL 在「`{主码}-N至{主码}-M`」范围回退
   **之后**、终极回退 `startswith(主码 + " ")` **之前**插入
   `_find_combined_workbook_declaring(wp_code)`。
3. THE `_LEGACY_A_ONLY_SUB_CODE_RE` SHALL 保持 `r"^A\d+-\d+"` 语义不变（源码注释自承该正则
   是存量缺陷，但改成字母类无关会让 `D2-2` / `E1-3` 这类 Excel 子表走子码分支，实测使数百个
   wp_code 变 `None`）。
4. THE Delivery SHALL NOT 重新生成也不手改 `wp_templates/_index.json`：现算证明
   `find_template_file_any` 的 A 子码分支用 `_match_filename_prefix(e["filename"], wp_code)`
   按**文件名**前缀判定而非 `e["wp_code"] == wp_code`，且
   `_match_filename_prefix("A3-7内部往来核对表、A3-8商誉减值测试.xlsx", "A3-8")` 现算为
   `False` ⇒ 给索引补一条记录对该分支无作用。
5. THE Delivery SHALL NOT 用 `app/data/wp_code_overrides.json` 修此缺陷（该表值是
   componentType 而非模板路径，且 Template_Finder 不读该表）。
6. THE Template_Finder 模块末尾的重绑定与 `*_unresolved` 别名 SHALL 保持不变，
   覆盖层优先语义不变。
7. WHEN 请求现算已在更早步骤命中的码（`A3-7` 命中合册本身；`D2-2` / `E1-5` / `F2-40` 命中
   范围回退），THE Template_Finder SHALL 在进入新步骤之前返回，使这些码的解析结果与改动前
   逐个相等。

### Requirement 12: `A3-8` 与 `A3-8-1` 的期望终态 —— 修完可用

**User Story:** 作为底稿使用者，我需要 `A3-8` 与 `A3-8-1` 解析到它们真实所在的合册，
以便这两个码从「拿不到册」或「拿到错册」变成可用。

#### Acceptance Criteria

1. WHEN 请求 wp_code `A3-8`，THE Template_Finder 两路入口 SHALL 都返回合册
   `A/A3-7内部往来核对表、A3-8商誉减值测试.xlsx`（现算 436152 B）。
2. WHEN 请求 wp_code `A3-8-1`，THE Template_Finder 两路入口 SHALL 都经祖先规则返回同一本
   合册（文件名只字面声明到 `A3-8`，`A3-8-1` 只出现在 sheet 名里）。
3. THE Delivery SHALL 证明这两个码的终态是「**可用**」：既解析到册，又能指向册内对应 sheet
   （`A3-8商誉减值测试` 与 `A3-8-1可收回金额测试`；该册现算 5 张 sheet）。
4. WHEN 改动前请求 `A3-8`，THE Template_Finder `find_template_file` 现算返回错册
   `A3 合并流程程序表.xlsx`（静默错答）；WHEN 改动后请求同一码，THE Template_Finder SHALL
   返回第 1 条的合册。
5. THE Delivery SHALL 把缺陷码分成**两个分母**分别验收：「文件名声明了却解析不到本册」现算
   **2** 个（`A2-2` / `A3-8`）、「册内有 sheet 但文件名未声明」现算 **1** 个（`A3-8-1`），
   合计 3；把两者合并成单一「3」SHALL 视为不合格（按文件名扫描永远得 2，会被误判成漏抓）。
6. THE Delivery SHALL 只做 a38 的**第一步（解析层）**，并把第二步（宿主层：Slice_Manifest 记
   `resolution_kind = "literal_sheet_name"` / `sheet_name_literal = "A3-8商誉减值测试"`，
   即宿主传中文字面 sheet 名而非 wp_code）登记为后继而不写成本 spec 任务；两步顺序
   SHALL NOT 颠倒（现算 `find_template_file_any("A3-8")` 为 `None` ⇒ 第二步单独做完零收益）。
7. THE 两本权威册（`A/A5-1 现金流量表审计.xlsx` 与
   `A/A3-7内部往来核对表、A3-8商誉减值测试.xlsx`）SHALL 在本 spec 内为只读事实，禁改动。

### Requirement 13: `A2-2` 的期望终态 —— 仅册可解析

**User Story:** 作为交付负责人，我需要 `A2-2` 的终态被如实写成「仅册可解析」，
以便验收时不把一个仍不可用的码判成已修好。

#### Acceptance Criteria

1. WHEN 请求 wp_code `A2-2`，THE Template_Finder 两路入口 SHALL 都返回字面声明该码的合册。
2. THE Delivery SHALL 如实记录该册的 sheet 层事实：现算 22 张 sheet，以 `A2-2` 起头的
   **0** 张 ⇒ sheet 层仍无供给（两数现算，禁写死）。
3. THE Delivery SHALL 把 `A2-2` 的 sheet 层供给登记为**独立的模板供给缺口**，
   本 lane 不承诺修复。
4. THE `A2-2` 的验收判据 SHALL 显式区分「册可解析」（本 lane 承诺）与「可用」（本 lane 不
   承诺）；把 `A2-2` 与 `A3-8` / `A3-8-1` 合写成「修好就能用」SHALL 视为制造假绿。

### Requirement 14: 四处勘误与 Slice_Manifest 两字段的更正

**User Story:** 作为守卫维护者，我需要把建立在假事实上的四条断言与 Slice_Manifest 的两个字段
一并更正，以便错误归因不再向下一轮传播。

#### Acceptance Criteria

1. THE Delivery SHALL 把 `test_a_entry_connection_blockers.py::test_a38_workbook_absent_on_disk`
   改为正向断言「该合册在磁盘上**且** `find_template_file_any` 能解析到它」，并把 docstring
   的解除信号方向反转（由「册出现即打红」改为「解析不到即打红」）；把 `rglob("A3-8*")` 换成
   `rglob("*A3-8*")` 后仍断言 `not found` SHALL 视为不合格。
2. THE Delivery SHALL 把
   `test_a_lane3_runtime_exceptions.py::TestBP6NoAuthoritativeBook::test_a38_workbook_is_null`
   随 Slice_Manifest 的 `workbook` 字段更正改为断言真实相对路径；保留 `is None` 断言 SHALL
   视为不合格。
3. THE Delivery SHALL 删除同类 `::test_a38_template_not_on_disk` 的假事实断言，替换为
   「合册存在 + 其文件名字面声明码集合含 `A3-8`」的事实断言，并改写其 docstring 里
   「真因不只是 sheet 名写法，而是根本没有这本册」这句结论；只改断言不改 docstring SHALL
   视为不合格（错误归因会继续传播）。
4. THE Delivery SHALL 重建同类 `::test_other_codes_resolve_but_a38_does_not` 的变异证明：
   对照组改为「`A3-3` / `A5-1` / `A10-1` 经 `find_template_file_any` 能解析」，
   并加「`A3-8` 修复**前** `None`、修复**后**得合册」的双向变异；继续用 `rglob` 口径做变异
   证明 SHALL 视为无效证明。
5. THE Delivery SHALL 把 Slice_Manifest 里 `xlsx/gt-a38-goodwill-impairment` 的
   `template_ref.workbook` 由 `null` 改为真实相对路径（该字段现值是假事实：册在磁盘上）。
6. THE Delivery SHALL 补齐同一 `template_ref.why_null` 的归因第一层（合册命名 + A-only 子码
   正则），或把该字段改为 `null` 并记录缺陷已解除；只改 `why_null` 文字而不改 `workbook`
   字段 SHALL 视为不合格（现值只说了第二层，隐含「传对 wp_code 就能解析」，而
   `find_template_file_any("A3-8")` 现算同样是 `None`）。
7. THE Delivery SHALL 记录第 1 ~ 4 条四条断言的共同成因：`rglob("A3-8*")` 现算 **0** 命中、
   `rglob("*A3-8*")` 现算 **1** 命中，glob 锚定文件名开头而该合册真名以 `A3-7` 起头。
8. THE Delivery SHALL 按 Slice_Manifest 的权威字段名 `entry_id` 定位条目
   （`entry_key` 现算不存在于条目键集合）。
9. THE Delivery SHALL 把归档 spec 的 AC-46 结论（「真因是根本没有这本册」）的**再更正**只登记
   在本 spec，不回填修改归档 spec 文件（归档 spec 是 append-only 审计轨迹）。
10. THE Lane B 对共享文件 `test_a_entry_connection_blockers.py` 的编辑范围 SHALL 限定为
    `TestNoAuthoritativeWorkbook::test_a38_workbook_absent_on_disk` 与顶部阻塞表里
    「无权威册」那一行。

### Requirement 15: 全域 wp_code 前后差集的零回归验收

**User Story:** 作为平台维护者，我需要以全域前后差集而不是抽样来验收 Lane B，
以便任何被顺带改变走向的码都无处藏身。

#### Acceptance Criteria

1. THE Delivery SHALL 现算全域 wp_code 分母并列出分母数，分母为三源之并：
   `wp_templates/_index.json` 的 `wp_code` 去重 ∪ `app/data/wp_code_overrides.json` 的键
   ∪ `wp_render_schema/*.yaml` 的 stem；分母口径 SHALL 在执行时一次性钉死并记录（含
   `wp_render_schema` 的目录归属与是否递归 —— 现算存在两处同名目录
   `app/data/wp_render_schema` 与 `data/ledger_adapters/wp_render_schema`），
   且 SHALL NOT 写死分母数。
2. THE Delivery SHALL 对分母内每个码记录改动**前**的 `(find_template_file,
   find_template_file_any)` 两路结果，改动**后**重算同一口径。
3. THE Delivery SHALL 断言前后差集**恰好**是 Requirement 12 第 5 条的 3 个码，且每个码的新值
   是预期的合册路径。
4. WHEN 把 `_combined_book_covers` 的 `len(declared) < 2` 收窄条件短路掉后重算，
   THE Delivery SHALL 断言差集**变大**（证明该收窄条件在起作用而不是恒真装饰）。
5. THE Lane B 的零回归判据 SHALL 是第 1 ~ 3 条的全域差集；以抽样若干码替代全域差集 SHALL
   视为不合格。

### Requirement 16: AST 守卫与既有合册零缺陷的不变性

**User Story:** 作为守卫维护者，我需要既有 AST 顺序守卫与 D/E/F 十九本范围册的零缺陷状态
在 Lane B 落地后仍然成立。

#### Acceptance Criteria

1. WHEN Lane B 落地，THE A_Domain_Guard 的
   `test_task58_word_canonical_resolver.py::test_finder_no_longer_uses_a_only_regex_for_sub_code_decision`
   SHALL 保持绿：在 `find_template_file_any` 这个 `FunctionDef` 内，
   `_resolve_most_specific_docx` 调用行号 < `_LEGACY_A_ONLY_SUB_CODE_RE.match` 调用行号，
   且两个调用都存在（断言同时校验 `a_only_line is not None`）。
   —— 本条是**样例判据（EXAMPLE）不是属性**：单一结构断言，既有守卫已覆盖，本条只保证不被
   破坏。
2. THE Requirement 11 的两处插入 SHALL NOT 移动 `_resolve_most_specific_docx` 与
   `_LEGACY_A_ONLY_SUB_CODE_RE.match` 两个调用的位置与先后关系。
3. THE Delivery SHALL 现算多码册全域事实并保持其不变：总数 **21**（A 2 / D 7 / E 4 / F 8）、
   分隔形态顿号「、」**2**（全在 A）+ 范围「至」**19**（全在 D/E/F）= 21 且两集合无交叠
   （全部现算，禁写死）。
4. WHEN Lane B 落地，THE Template_Finder SHALL 使对照组 `D2-2` / `E1-5` / `F2-40` 的解析
   结果与改动前逐个相等（三者 `_LEGACY_A_ONLY_SUB_CODE_RE.match` 现算均为 `False`，
   均在范围回退命中，位置在新步骤之前）。
5. WHEN Lane B 落地，THE Delivery SHALL 重跑 A_Domain_Guard 全部 5 个文件（改动前基线现算
   159 passed，禁写死）。
6. WHERE 两条 lane 并行落地，THE 共享文件 `test_a_entry_connection_blockers.py` 的合并
   SHALL 由后落地的那条 lane 负责，且合并后 SHALL 重跑 A_Domain_Guard 基线。

### Requirement 17: 交付纪律与登记

**User Story:** 作为仓库维护者，我需要交付物不留一次性残渣、spec 登记口径正确，
以便下一轮不被过期快照与残留探针误导。

#### Acceptance Criteria

1. WHEN 交付完成，THE Delivery SHALL 使 `backend/scripts/analyze/` 下无 `_psl_*` 前缀的
   探针脚本与输出文件残留（`_` 前缀 = 一次性、用完即删）。
2. WHERE 核验判据含正则，THE Delivery SHALL 通过探针文件执行而非通过 `python -c`
   （shell 传参会把 `\d` 变成字面反斜杠）；文件行数与编码 SHALL 用 Python 读 bytes 后
   decode 判定（PowerShell 的行数与编码显示不可信）。
3. WHEN 在 `.kiro/specs/INDEX.md` 登记本 spec，THE Delivery SHALL 按
   `read_bytes().decode('utf-8')` → 修改 → `write_bytes()` 的方式写回（该文件是纯 CRLF），
   表格第三格内不出现裸 pipe，并以「每行恰 4 个未转义 pipe」校验。
4. THE 本 spec 的三件套文档 SHALL 不写死源码行号；一切计数类判据 SHALL 标注「现算」或
   「现算值 + 禁写死」。

## 明确排除（out of scope，8 项，与 design.md §八 逐条一致）

| 排除项 | 理由（现算实证） |
|---|---|
| **16 条 docx entry** | 门是 Task 61 Word pilot：`workpaper_task61_word_pilot_gate_probes.json` 现算 41 probe，`verdict` 分布全空、`has_validator is False` 38 条；`lane_entry_keys` 只有 `word-lane/f2-22-stocktake-plan` / `word-lane/f2-23-stocktake-summary`（F2 存货监盘，非 A 类）。`PENDING_ENGINE_ADAPTERS` 现算恰 1 行 docx，`blocking_task='59,60,61'`，仍禁 `adapters/word.py`。本 spec 不翻这行。 |
| **a177** | `resolution_kind = runtime_sheet_name_expression`，两分支 `A17-7` / `A17-7A` 各自都能解析到自己的 docx，`capability_target_blocked_by` 无 BP-6 ⇒ 与合册命名无关。 |
| **a3-console** | `single_onlyoffice` 是正确 capability：HTML 侧 ProgramRow 9 字段 与 Excel 侧 A3-3 册 33 列字段交集 **0** ⇒ 不存在可投影的对端。 |
| **a38 第二步（宿主传中文字面 sheet 名）** | 与第一步顺序不可颠倒（Requirement 12 第 6 条）；第一步未做时第二步零收益。登记为后继。 |
| **范围式合册的码展开** | A 域现算 0 本范围式合册；D/E/F 的 19 本范围册现算 0 缺陷。`_RANGE_MARKERS` 的 fail-closed 保证将来出现时表现为「不认」而非「认错」。 |
| **`A2-2` 的 sheet 层供给** | 该册现算 22 张 sheet，0 张以 `A2-2` 起头 ⇒ 模板供给缺口，与解析层无关（Requirement 13）。 |
| **`_index.json` 重新生成** | 现算证明索引修法对 `find_template_file_any` 的 A 子码分支无作用（Requirement 11 第 4 条）；且该文件是生成物，手改会漂。 |
| **第二个纯静态 entry 的接入** | 本 lane 只把通道建成并让 canary 走通。`k2.adjudication_derived` / `l4.bonds_payable` 两份 0 动态表契约现算都是 `.candidate.`（未 reviewed），不具备接入前提。 |

### 预先存在的失败（改动前已红，与本 spec 无因果，禁纳入范围也禁顺手修）

- `test_registration_isolation_and_alignment[d3]`
- `test_dedicated_component_registry_contract::test_whole_subset_of_valid_and_fe`
- `test_task57_abcs_and_shared_migration::TestGuardSelfChecks::test_the_n_style_per_entry_dual_mode_scanner_finds_nothing_here`
- `b60.hour_budget.json` CRLF 致字节稳定性 1 red
- `test_task75_published_identity_observer::TestDebtRemovedWithRealImpl` 4 项
  （`phase5_c_control_test` 缺 `resolve_published_frozen_definitions`）

每条须在 tasks 里记录「改动前后同样红」作为归因证据。

---

## Correctness Properties

*属性是一条应在系统全部合法执行上都成立的性质 —— 它把人读的规格与机器可验的正确性保证连起来。*

本节把 design.md §六 的属性候选形式化为编号 Property。候选表里被判为 **EXAMPLE 而非属性**的
两条**不在**本节：A-4（静态 payload digest 不变式）落在 Requirement 3 第 8 条，
B-7（AST 顺序不变式）落在 Requirement 16 第 1 条 —— 两者都是单一冻结入参 / 单一结构断言，
写成随机化属性测试即误用。

PBT 库 `hypothesis`，`max_examples=5`（项目铁律，禁默认 100）。

### Property 1: 静态注入不改可见业务面

对**任意**合法 xlsx 源册与**任意**合法静态 spec 集合，静态注入产物与源册在「非 `_GT_SYNC`
sheet 的全部单元格值与公式」上逐格相等。

**Validates: Requirements 2.12**

### Property 2: 静态注入不引入动态载体

对**任意**静态注入产物，其 `xl/tables/` 部件数与源册相等，且每张受管 sheet 的列集合与源册
同名 sheet 逐列相等 —— DEC-3 的可执行化。

**Validates: Requirements 2.5, 2.6, 2.9, 2.14**

### Property 3: `_GT_SYNC` 键完备且 UUID 列取空串哨兵

对**任意**静态注入产物，`_GT_SYNC` 的键集合 ⊇ `REQUIRED_GT_SYNC_KEYS`，
`GT_ROW_UUID_COLUMN` 恒为空串 `""`，且 5 个 runtime binding 键一个都不被写入。

**Validates: Requirements 2.3, 2.4, 2.8**

### Property 4: 静态锚点往返

对**任意**静态 spec 集合，注入后经 `_frozen_sheet_anchors` 与
`_collect_static_region_physical` 读回的 `(sheet_key → 物理 sheet 名)` 映射等于 spec 的声明
—— 注入与反读互逆。

**Validates: Requirements 2.7, 5.6**

### Property 5: 静态主 binding 唯一性

对**任意**契约与**任意**静态锚点，主 binding 要么绑到与 `anchors["sheet_key"]` 唯一对齐的
静态表，要么以 `FrozenChildUnusableError` 显式失败；不存在「静默取集合首元素」的执行。

**Validates: Requirements 5.1, 5.3, 5.4**

### Property 6: 全静态锚点下观测无裸异常

对**任意**全静态锚点集合（含单区与多区），请求期观测不抛 `AttributeError`，
且 Structure_Collector 的第 3 返回值不为 `None`。

**Validates: Requirements 6.1, 6.5**

### Property 7: 寄生静态区零回归

对**任意**既有「动态 primary + 寄生 `static_sheets`」entry，改造前后的注入产物逐字节相等。

**Validates: Requirements 7.2, 7.3**

### Property 8: 合册声明码解析闭合

对**任意**合册文件名里字面声明的 wp_code，Template_Finder 两路入口都返回该合册本身。

**Validates: Requirements 11.1, 11.2, 12.1**

### Property 9: 祖先码解析到同一本合册

对**任意** wp_code，若其某个祖先码被某合册字面声明且该码无自有载体，则解析结果是同一本
合册。

**Validates: Requirements 10.6, 12.2**

### Property 10: 范围式命名 fail-closed

对**任意**含 `_RANGE_MARKERS` 字符的文件名，`_literal_wp_codes_in_filename` 返回空集；
对**任意**不含该类字符且含至少一个码的文件名，返回非空集（结构性零配双向变异证明）。

**Validates: Requirements 10.3, 10.4**

### Property 11: 合册判据拒单码册

对**任意**只字面声明一个码的文件名，`_combined_book_covers` 恒返回 `False`；
短路 `len(declared) < 2` 这一收窄条件后，全域解析差集变大。

**Validates: Requirements 10.5, 15.4**

### Property 12: 全域解析差集恰为预期三码

对全域 wp_code 分母，改动前后两路解析结果的差集恰为 Requirement 12 第 5 条的 3 个码，
且每个码的新值是预期合册路径。

**Validates: Requirements 15.1, 15.3**

### Property 13: 祖先规则不越码边界

对**任意**声明码 `C` 与请求码「`C` 直接拼数字」的形态（如声明 `A3-8` 对请求 `A3-80`），
祖先规则不命中；对「`C` + `-` + 后缀」形态命中。

**Validates: Requirements 10.6**
