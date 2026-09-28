# Implementation Plan: workpaper-sync-pure-static-lane-and-combined-workbook-resolution

## Overview

两条 lane 各自独立交付。**Lane A（Task 2 ~ 12）** 把纯静态 instrumentation 从「寄生在动态
primary 上」上提为平台一等通道，处置六处阻塞（3 处旁路 + 3 处加分派臂 + **零处**放宽既有
校验），并让 canary `xlsx/gt-a51-cashflow-audit` 走完发布链。**Lane B（Task 13 ~ 17）** 给
`wp_template_finder` 加合册声明码索引，使 `A3-8` / `A3-8-1` / `A2-2` 解析到真实所在的合册。
**Task 1 / Task 19** 是两条 lane 共用的前置现算与收尾登记。

实现语言 Python（`design.md` 的接口与 Data Models 段已是 Python，无需再选）。

生产代码模块集合交集为空；唯一共享文件是 `tests/workpaper_sync/test_a_entry_connection_blockers.py`，
其编辑边界与合并责任写成三条显式执行约束（Task 10.1 / Task 17.1 / Task 16.4）。

---

## Tasks

- [x] 1. 交付前置：现算全部承重分母与回归基线（两条 lane 共用，不动生产代码）

  - [x] 1.1 写探针现算并一次性钉死全部分母、A 域回归基线与预先存在失败
    - 探针 `backend/scripts/analyze/_psl_t1_denominators.py`，输出 `_psl_t1_denominators.txt`
    - 现算 Lane A 分母：`workpaper_sync_contracts/*.json` 总份数 / `.candidate.` 份数 / 缺
      `review_status` 份数 / `review_status == "reviewed"` 分母 / 「0 动态行表」成员集合在
      三个分母下各自的取值；`REQUIRED_GT_SYNC_KEYS` 键数（禁写死键数）
    - 现算寄生静态区 entry 的**完整**分母（即「动态 primary + 非空 `static_sheets`」的全部
      entry），作为 Task 9.1 的验收范围，禁写死成员清单
    - 现算 Lane B 分母：全域 wp_code 三源之并 —— `wp_templates/_index.json` 的 `wp_code`
      去重 ∪ `app/data/wp_code_overrides.json` 的键 ∪ `wp_render_schema/*.yaml` 的 stem；
      **口径须在本任务内一次性钉死并写入输出**，含两处同名目录
      （`app/data/wp_render_schema` 与 `data/ledger_adapters/wp_render_schema`）的归属裁决
      与是否递归；禁写死分母数
    - 现算多码册全域事实：总数与按首字母分布、分隔形态（顿号 / 「至」/ `~` / `～`）分布，
      并校验两集合无交叠且分形态之和 == 总数
    - 跑 A_Domain_Guard 全部 5 个文件（`test_a51_component_type_routing.py` /
      `test_a_cycle_foundation_canary.py` / `test_a_entry_connection_blockers.py` /
      `test_a_lane2_docx_authority.py` / `test_a_lane3_runtime_exceptions.py`）取改动前
      passed 基线（现算，禁把该数写死进任何断言）
    - 逐条复现 requirements 文末 5 条**预先存在失败**，记录 nodeid 与红因，作为
      「改动前后同样红」归因证据的前半段；禁顺手修
    - 含正则的核验一律走探针文件，禁 `python -c`；文件行数与编码一律 Python 读 bytes 后
      decode 判定（PowerShell 的行数与编码显示不可信）
    - _Requirements: 2.3, 7.3, 8.8, 15.1, 16.3, 16.5, 17.2, 17.4_

  - [x] 1.2 现算并记录「第 6 处阻塞在执行顺序上早于第 5 处」的实证
    - 探针 `backend/scripts/analyze/_psl_t2_observe_order.py`，输出 `_psl_t2_observe_order.txt`
    - 在 `PublishedIdentityObserver.observe()` 源码内取 `_observe_workbook` 与
      `_build_identity_binding` 的首现位置并比较（位置值现算，**禁把行号写进 spec 或断言**）
    - 记录结论：`_observe_workbook` 的裸 `AttributeError` 先触发 ⇒「静态主 binding 已支持」
      **不能**作为第 6 处已完成的证据；据此钉死 Task 7 必须先于 Task 8
    - _Requirements: 6.8_

- [x] 2. Lane A：纯静态 instrumentation 声明类型（`excel_instrumentation.py`）

  - [x] 2.1 新增 `StaticRegionSpec` 与 `ExcelStaticOnlyInstrumentationSpec` 及其静态语义校验
    - 两个 frozen dataclass 与 `ExcelInstrumentationSpec` 构成**兄弟**关系而非继承；字段集合
      不含 `first_data_row` / `last_data_row` / `footer_row` / `uuid_col` /
      `managed_last_col` / `table_name` 任何一个
    - `StaticRegionSpec` 恰含 `sheet_key` / `excel_name` / `template_id` / `defined_name` /
      `managed_ref` / `table_key` 六字段；`excel_name` 注释标明是构建期选择器而非运行时锚点
    - `__post_init__` 校验面限定为：空 `entry_id` / 空 `static_regions` / 非法 OOXML
      defined name / 非绝对矩形 `managed_ref` 或右下 < 左上 / 三键（`sheet_key` /
      `defined_name` / `table_key`）区内重复；逐区遍历时维持「已检查区均合法且三键未与更早
      的区冲突」不变式
    - **禁**给 `ExcelInstrumentationSpec` 加可选字段、**禁**把行表几何改成可选
      —— 该类字段集合与 `__post_init__` 逐条保持改动前形态
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 1.10_

  - [x]* 2.2 为 Static_Spec 校验面写单元测试
    - 新建 `backend/tests/workpaper_sync/test_static_only_instrumentation_lane.py`
    - 五类拒收各一例（含异常消息须含字段名与实得值）；三键重复的三种组合各一例
    - 负向：行区间 / footer 行 / UUID 列位置三类判据**不在**校验面（构造只给静态字段即通过）
    - 对照断言：`ExcelInstrumentationSpec` 的字段集合与 `__post_init__` 校验项未被放宽
    - _Requirements: 1.2, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 1.10_

- [x] 3. Lane A：纯静态注入器（`excel_instrumentation.py`）

  - [x] 3.1 新增 `instrument_workbook_bytes_static_only(source, spec, *, gate, identity_carriers)`
    - 只写 `_GT_SYNC` 与 workbook-scope definedNames；每个 `defined_name` 在
      `xl/workbook.xml` 的 `<definedNames>` 里恰 1 次，ref =
      `_quote_sheet_name(excel_name) + "!" + managed_ref`
    - `_GT_SYNC` 键集合 ⊇ `REQUIRED_GT_SYNC_KEYS`（按常量现算，禁写死键数）；
      `GT_ROW_UUID_COLUMN` 写空串 `""` 作「无 UUID 列」哨兵；`GT_MANAGED_SHEET_ID` 写
      definedName 所指 sheet 的真实 sheetId 并保留「降级、非运行时锚点」标注
    - 零新增 `xl/tables/` 部件、零新增隐藏列、`assert_no_runtime_binding(pair_map)` 通过、
      非 `_GT_SYNC` sheet 逐格值与公式不变
    - 签名**只**接受四项入参，使「写 Excel Table」与「写隐藏 UUID 列」在结构上无从表达 ——
      DEC-3 由类型边界保证而非由自觉保证
    - 错误路径：`excel_name` 在 `source` 内不存在 ⇒ `InstrumentationError`（消息同时含缺失
      sheet 名与源册现有 sheet 名清单）；definedName 重名 ⇒ 沿用既有静态支的
      `Duplicate static definedName` 消息形态
    - `instrument_workbook_bytes_multi` **一字不改**：拒空 specs 判据与六项 `primary.*` 取值
      （`footer_row` / `uuid_col` / `table_name` / `table_ref` / `first_data_row` /
      `last_data_row`）逐条保留
    - 「静态注入正确」判据是 R2.4 + R2.5 + R2.6 **三条同时成立**；只验哨兵一条即判通过不合格
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 2.10, 2.11, 2.12, 2.13, 2.14_

  - [x]* 3.2 为 Property 1 写属性测试
    - **Property 1: 静态注入不改可见业务面**
    - **Validates: Requirements 2.12**
    - `hypothesis`，`max_examples=5`；生成合法 xlsx 源册 × 合法静态 spec 集合
      （sheet 数 / 区数 / 矩形位置随机），断言非 `_GT_SYNC` sheet 逐格值与公式相等

  - [x]* 3.3 为 Property 2 写属性测试 + 变异证明④
    - **Property 2: 静态注入不引入动态载体**
    - **Validates: Requirements 2.5, 2.6, 2.9, 2.14**
    - `hypothesis`，`max_examples=5`；断言 `xl/tables/` 部件数与源册相等 + 每张受管 sheet
      列集合逐列相等
    - 变异证明④：人为往产物注一个 Table 部件后，「无新增 Table 部件」判据必须变红
      （结构性零须配变异证明）

  - [x]* 3.4 为 Property 3 写属性测试
    - **Property 3: `_GT_SYNC` 键完备且 UUID 列取空串哨兵**
    - **Validates: Requirements 2.3, 2.4, 2.8**
    - `hypothesis`，`max_examples=5`；键集合 ⊇ `REQUIRED_GT_SYNC_KEYS`（现算常量，禁写死
      键数）+ `GT_ROW_UUID_COLUMN == ""` + 5 个 runtime binding 键零写入

  - [x]* 3.5 为注入器两条错误路径写单元测试
    - 缺 sheet：异常消息同时含缺失 sheet 名与源册现有 sheet 名清单
    - definedName 重名：消息形态与既有静态支一致
    - _Requirements: 2.10, 2.11_

- [x] 4. Lane A：静态 payload 构建器与 digest 不变式（Lane A 的收口判据）

  - [x] 4.1 新增 `build_static_only_instrumentation_payload`
    - 签名 `(*, spec, template_definition_sha256, template_sha256, gate, identity_carriers,
      identity_anchors)`，新增于 `excel_instrumentation.py`
    - 载体清单从**入参** `identity_carriers` 取，**不**从 `gate.allowed_carriers` 推导
      （A5-1 的 `IDENTITY_CARRIERS` 现算项数 < gate 放行项数，按 gate 推导即语义过度声明）
    - `payload["managed_sheets"] == []`；`len(payload["static_sheets"]) ==
      len(spec.static_regions)`；**不含** `row_uuid_disposition`、**不含** `transposed_sheets`
    - `payload["hidden_metadata_sheet"]["keys"] == list(REQUIRED_GT_SYNC_KEYS)` ——
      原样复用该常量，**禁**新建静态子集
    - 过 `validate_instrumentation_payload()` 与 `_assert_no_forbidden_anchor_declared()`
    - `build_instrumentation_payload_for_sheets` 保持改动前形态：拒空 specs 判据与
      `identity_carriers = list(sorted(gate.allowed_carriers))` 取值逻辑逐条保留
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7_

  - [x] 4.2 Canary_Provider 改为委派门面并更正过期分母注释（`phase5_a51_cashflow_audit.py`）
    - `build_instrumentation_payload()` 保留为委派 Static_Payload_Builder 的门面
      （使 §6 阻塞④ 的 provider 状态断言保持绿）
    - 更正该函数注释里「实测 60 份契约里唯一如此的 reviewed 契约」这一过期分母：改为现算口径
      描述（`review_status == "reviewed"` 分母下唯一 0 动态行表成员），**改写后的注释不写死
      任何分母数字**
    - _Requirements: 3.10, 3.11_

  - [x]* 4.3 为 digest 不变式写**样例**判据（EXAMPLE，禁写成随机化属性测试）
    - 以 canary 的固定入参调用 Static_Payload_Builder，断言
      `canonical_digest(新平台构建器输出)` 逐位等于
      `canonical_digest(Canary_Provider.build_instrumentation_payload() 输出)`
    - 断言该值与三方同值：契约 `a51.cashflow_audit.json` 的
      `instrumentation_definition_sha256`、守卫常量
      `CANARY_INSTRUMENTATION_DEFINITION_SHA256`、真库 artifact 行
      —— **判据以常量为锚，禁在判据文本里写死全值**
    - 不相等时须输出两份 payload 的 key 级差异
    - 执行约束（本任务的验收条件，三条禁止）：修法**只能**修 Static_Payload_Builder；
      改契约 / 改守卫常量 / 改真库 artifact 去迁就 = 不合格，须回退
    - 入参是单一冻结值 ⇒ 本条是 EXAMPLE 不是属性；写成 `hypothesis` 随机化测试即误用
    - _Requirements: 3.8, 3.9_

- [x] 5. Checkpoint —— Lane A 注入与 payload 段
  - Ensure all tests pass, ask the user if questions arise.
  - 特别核对：digest 不变式（Task 4.3）已绿；`instrument_workbook_bytes_multi` 与
    `ExcelInstrumentationSpec` 的 `git diff` 为空

- [x] 6. Lane A：Substrate 组装的第三条分派臂（`projection_first_publication.py`）

  - [x] 6.1 在 `stage_instrumented_substrate` 既有两臂之后追加第三臂
    - 顺序：`instrumentation_specs` → `instrumentation_spec` → **新增**
      `static_only_instrumentation_spec`；既有两臂的判据与先后**逐条不变**，使既有 provider
      在进入第三臂之前即命中原臂
    - 进入第三臂前 fail-closed：provider 暴露 `static_only_instrumentation_spec` 时**不得**
      同时暴露 `instrumentation_spec` 或 `instrumentation_specs` 任一（DEC-3 结构化守卫）
    - 守卫判据限定为「有 static_only 即不得有行表 spec」这一**单向蕴含**；采用「三者恰暴露
      其一」的统一断言 = 不合格（既有 provider 存在同时暴露两个入口的双入口回落形态）
    - `validate_ooxml_artifact` 安全门保持在改动前的调用位置
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

  - [x]* 6.2 为第三臂写单元测试
    - 既有 provider 零走向变更：现算分母内每个既有 provider 命中的臂与改动前相同
    - 双 spec 并存 ⇒ fail-closed 抛错
    - 负向：构造「同时暴露 `instrumentation_spec` 与 `instrumentation_specs`」的既有形态
      provider，断言它**不**被打红（证明没有误用统一断言）
    - _Requirements: 4.2, 4.3, 4.4_

- [x] 7. Lane A：第 6 处阻塞 —— 观测清册消除裸 `AttributeError`（**必须整体先于 Task 8**）

  - [x] 7.1 新增 `StaticIdentityInventory` 并让 Structure_Collector 静态臂返回真实清册
    - 与 Structure_Collector 同模块新增 frozen dataclass，提供 `row_uuids`（恒空元组）与
      `inventory_digest_input`（`{"kind": "static_region", "regions": [[sheet_key,
      defined_name, physical_sheet], ...]}`）两个成员
    - `collect_workbook_structure` 静态分派臂累积 `(sheet_key, defined_name,
      physical_sheet_name)` 三元组；循环结束时若 `primary_inventory is None` 且存在静态观测
      结果，则构造静态清册作为第 3 返回值
    - `_observe_workbook` 内 `canonical_digest(inventory.inventory_digest_input)` 这一行
      **零改动** —— 处置方式是**消除 `None`**；给该字段加 `None` 特判或改成 Optional = 不合格
    - 含动态 Excel-Table 锚点时第 3 返回值仍为改动前的 `primary_inventory` 对象
    - _Requirements: 6.1, 6.2, 6.3, 6.7_

  - [x] 7.2 消费方审计：逐个现读 `identity_inventory` 与 Structure_Collector 第 3 返回值的
        全部消费方
    - 用 codegraph / grep 取 `PublishedObservation.identity_inventory` 与
      `collect_workbook_structure` 第 3 返回值的**全部**消费方，逐个现读并列表
    - 证明每个消费方只使用 `row_uuids` 或 `inventory_digest_input`；对使用其他成员的消费方
      补静态形态分派
    - 不做此审计等于把 `AttributeError` 从一个站点搬到另一个站点 ⇒ 本任务不得跳过、不得以
      「假设为零成本」结论代替逐个现读
    - _Requirements: 6.6_

  - [x]* 7.3 为 Property 6 写属性测试
    - **Property 6: 全静态锚点下观测无裸异常**
    - **Validates: Requirements 6.1, 6.5**
    - `hypothesis`，`max_examples=5`；锚点集合含单区与多区两形态；断言请求期观测不抛
      `AttributeError` 且第 3 返回值不为 `None`；失败只以 `FrozenChildUnusableError` 或
      `ObservedIdentityDriftError` 形式呈现

  - [x]* 7.4 为 definedName 三种漂移写单元测试（清册 digest 的反漂移意义）
    - definedName 被删除 / 改名 / 改指向另一张 sheet，三种各一例
    - 断言 `identity_inventory_sha256` 随之变化（证明该 digest 是真实观测值而非补出来的假值）
    - _Requirements: 6.4_

- [x] 8. Lane A：第 5 处阻塞 —— 身份观测器的静态主 binding（**须在 Task 7 之后**）

  - [x] 8.1 为 `_build_identity_binding` 加静态臂
    - `str(anchors.get("region_kind") or "") == "static"` 时返回
      `ExcelIdentityBinding(defined_name=anchors["defined_name"], table_key=唯一对齐的静态
      table_key, metadata_sheet=GT_SYNC_SHEET_NAME)`
    - 契约无 `row_identity is None` 的静态表 ⇒ `FrozenChildUnusableError`
    - 与 `anchors["sheet_key"]` 对齐的静态表数量 ≠ 1 ⇒ `FrozenChildUnusableError` 且消息含
      匹配集合；**静默取集合首元素 = 不合格**（静态臂与动态臂在「禁随手挑第一张」上对称）
    - 动态路径逐条原样保留：含「契约未声明任何带 `row_identity` 的表即
      `FrozenChildUnusableError`」判据与 `anchors["table_name"]` /
      `anchors["uuid_column_letter"]` 两处取值
    - 前置：Task 7 已落地 —— `_observe_workbook` 在执行顺序上更早，Task 7 未做时本任务的
      运行时路径根本到不了（顺序实证见 Task 1.2）
    - _Requirements: 5.1, 5.2, 5.3, 5.4_

  - [x] 8.2 核验四处零改动
    - 探针 `backend/scripts/analyze/_psl_t8_zero_diff.py`：用 `git diff` 现算
      `excel_extract` / `excel_materialize` 两模块改动行数为 **0**
    - 现算 `_frozen_sheet_anchors` 与 `_collect_static_region_physical` 两函数源码与改动前
      逐字节相等
    - 记录理由：`ExcelIdentityBinding.kind` 是派生属性（有 `defined_name` 即
      `static_region`），静态 binding 形态与 Canary_Provider 现有 `static_identity_bindings()`
      一致 ⇒ 下游零改动
    - _Requirements: 5.5, 5.6_

  - [x]* 8.3 为 Property 5 写属性测试
    - **Property 5: 静态主 binding 唯一性**
    - **Validates: Requirements 5.1, 5.3, 5.4**
    - `hypothesis`，`max_examples=5`；契约表数与锚点随机；断言「唯一对齐」或「显式失败」
      二者之一成立，不存在「静默取集合首元素」的执行

  - [x]* 8.4 为 Property 4 写属性测试
    - **Property 4: 静态锚点往返**
    - **Validates: Requirements 2.7, 5.6**
    - `hypothesis`，`max_examples=5`；注入后经 `_frozen_sheet_anchors` +
      `_collect_static_region_physical` 读回的 `(sheet_key → 物理 sheet 名)` 映射等于 spec 声明

- [x] 9. Lane A：既有寄生静态区与全部动态 entry 的零回归

  - [x]* 9.1 为 Property 7 写属性测试
    - **Property 7: 寄生静态区零回归**
    - **Validates: Requirements 7.2, 7.3**
    - `hypothesis`，`max_examples=5`；分母取 Task 1.1 现算的寄生静态区 entry **完整**清单
      （禁写死成员），对每个 entry 重跑注入并断言改造前后产物**逐字节相等**

  - [x] 9.2 核验处置矩阵与「平台已支持纯静态」正面判据清单
    - 探针 `backend/scripts/analyze/_psl_t9_disposition.py`：现算六处阻塞的处置恰为
      「3 处旁路 + 3 处加分派臂」，**放宽既有校验的处置数为 0**
    - 逐项现读 design §1.9 清单并断言存在：`validate_instrumentation_payload` 不要求
      `managed_sheets` 非空 / `_frozen_sheet_anchors` 三集合迭代 /
      `_collect_static_region_physical` / `collect_workbook_structure` 静态分派臂 /
      `excel_extract` 四处静态分派 / `excel_materialize` 的 `_plan_static_writes` /
      `ExcelInstrumentationSpec.static_sheets` 寄生字段
    - 把清单内任一项列为待做 = **误报**，须回退该条判据
    - 记录零回归的结构性理由：缺口只影响「整个 entry 无动态表」这一形态，既有静态区全部寄生在
      同 entry 的动态 primary spec 上
    - _Requirements: 7.1, 7.4, 7.5_

- [x] 10. Lane A：§6 守卫同步更新与交付台账

  - [x] 10.1 重写 `test_a_entry_connection_blockers.py` 的 §6 段
    - 🔴 **执行约束（R8.7 编辑边界）**：Lane A 对该共享文件的编辑范围**限定**为
      `TestStaticOnlyInstrumentationGap` 类及其模块级辅助（`_ROW_GEOMETRY_ATTRS` /
      `_SUBSTRATE_PROVIDER_ENTRY_NAMES` / `static_injection_entry_points` /
      `top_level_function_names`）；**不得**触碰 `TestNoAuthoritativeWorkbook` 或顶部阻塞表
      「无权威册」那一行（那是 Lane B 的边界，见 Task 17.1）
    - 执行守卫自写的两条同步动作：① 删除 §6 阻塞段；② 承接 payload 组装已上提到平台入口这一
      事实（Task 4.1 / 4.2 已落地）
    - 把预判为红的 **3** 条改写为绿：解除信号①
      `static_injection_entry_points(top_level_function_names(excel_instrumentation)) == ()`、
      解除信号② `"region_kind" not in _build_identity_binding` 源码、阻塞⑤
      `stage_instrumented_substrate` 源码不含 `"static"` 与 `"region_kind"`
    - 变异证明①：`static_injection_entry_points` 的双向变异须保持可用（他域样本命中 +
      本域样本不命中）
    - 补齐两处覆盖面缺口，为 `build_instrumentation_payload_for_sheets` 与 `_observe_workbook`
      两个站点新建断言（改造后它们是「已支持静态」的正面判据）
    - 更正顶部阻塞表「五处全预设」这一计数为现算 **6** 处；并写明 §6 现有 6 个断言方法里
      `test_a51_provider_has_no_row_spec_by_design` 断言的是纯静态的**正确状态**、不是平台阻塞
    - _Requirements: 8.1, 8.2, 8.4, 8.7, 8.9_

  - [x] 10.2 Lane A 落地后重跑 A_Domain_Guard 全部 5 个文件
    - 只跑单个文件 = 不合格；对照 Task 1.1 的改动前基线（现算，禁写死）
    - 断言阻塞①②③④⑥ 与「已达成① digest 三方相等」保持绿；其中任一条变红 ⇒ 判定为
      「放宽了既有校验」并**回退**该处改动
    - 允许的红只有 Task 10.1 列举的 3 条，且它们已在同一 lane 内被改写为绿
    - 逐条比对 Task 1.1 记录的 5 条预先存在失败，确认「改动前后同样红」作为归因证据
    - _Requirements: 8.3, 8.8_

  - [x] 10.3 处置交付台账 `DELIVERED_PER_ENTRY_CONTRACTS` 的 `adapter_registered`
    - 改数据真源 `app/services/workpaper_sync/adapters/delivered_contracts_ledger.py`；
      `adapters/registry.py` 的 re-export 段保持不变
    - **仅当** Task 12 的两条子任务均通过时才把 canary 的 `adapter_registered` 翻 `True`；
      Round_Trip_Harness 未通过则**保持 `False`**，并以「代码已改但未实测」措辞记录、对应任务
      标 `[ ]*`
    - 先翻字段再补实测 = 假绿
    - _Requirements: 8.1, 8.5, 8.6_

- [x] 11. Checkpoint —— Lane A 可独立发布点
  - Ensure all tests pass, ask the user if questions arise.
  - 此点 Lane A 的生产代码与守卫已自洽，可独立发布 / 独立回滚；`adapter_registered` 仍为
    `False`（待 Task 12）

- [ ] 12. Lane A：Canary 真栈往返验收（INTEGRATION，执行 1 次）

  - [ ]* 12.1 执行真栈往返四步
    - 环境：后端 9980 / 前端 3030 / `audit-onlyoffice` healthy / 登录 `admin/admin123`
      （token 在 **sessionStorage**）/ Playwright MCP；
      `wpId=2246b5c0-19c3-4d66-bfb2-72d9afdc2996` `projectId=c8621493-70aa-46a9-8285-e0674e4e1418`
    - 执行前现算 A5-1 契约的 editable 字段分母（禁写死），并从该分母内选取两个 cell
    - 四步缺一步不算通过：① HTML 侧改一个 editable cell 并保存 ② 同步到 OO 并在 OO 侧读到同值
      ③ 在 OO 侧改另一个 editable cell 并保存 ④ 回读 HTML，两处值都与各自最后一次写入相等
    - 按 INTEGRATION 处理、**执行 1 次**；写成随机化属性测试 = 不合格（依赖真 OO 与真浏览器，
      100 次迭代不增加缺陷发现率）
    - 环境任一项缺失 ⇒ 本任务保持 `[ ]*` 并如实写「待环境」「代码已改但未实测」，且 Task 10.3
      的 `adapter_registered` 保持 `False`
    - _Requirements: 9.1, 9.4, 9.5, 9.6_

  - [ ]* 12.2 往返后的两条负向判据
    - 现算契约标 `protected` 的公式列分母（审定表公式列 G 与勾稽核对公式列 B 两组，两数现算、
      禁写死），断言这些列未被覆盖
    - 重新观测并断言 `recomputed_structure_hash` 与发布时冻结值相等（证明往返未改动结构）
    - _Requirements: 9.2, 9.3_

- [x] 13. Lane B：合册声明码索引纯函数（`wp_template_finder.py`）

  - [x] 13.1 新增五个模块私有符号
    - `_RANGE_MARKERS` / `_FILENAME_CODE_RE` / `_literal_wp_codes_in_filename` /
      `_combined_book_covers` / `_find_combined_workbook_declaring`；**不**进模块末尾的覆盖层
      薄封装、**不**新增公开入口
    - `_literal_wp_codes_in_filename` 是纯函数（不读磁盘、无副作用、同输入恒等输出）：stem 含
      任一 `_RANGE_MARKERS` 字符 ⇒ 返回空集（fail-closed，不做范围展开）；否则返回
      `_FILENAME_CODE_RE` 的全部匹配去重集
    - `_combined_book_covers`：字面声明码数 < 2 ⇒ `False`（只声明一个码的册不是合册）；
      祖先规则用 `wp_code.startswith(code + "-")`，使 `A3-80` 不被 `A3-8` 命中
    - `_find_combined_workbook_declaring`：只在 `TEMPLATES_DIR / wp_code[0]` 下枚举
      `.xlsx` / `.xlsm`，按 `(len(name), name)` 确定性排序取首个，**全程不读 xlsx 字节**
    - **不**实现范围式命名的码展开（A 域现算 0 本范围式合册；D/E/F 的范围册现算 0 缺陷）；
      扩展点留在 `_RANGE_MARKERS` 的 fail-closed 上，使将来出现 A 域范围册时表现为「不认」
      而不是「认错」
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7, 10.9_

  - [x]* 13.2 为 Property 10 写属性测试
    - **Property 10: 范围式命名 fail-closed**
    - **Validates: Requirements 10.3, 10.4**
    - 新建 `backend/tests/workpaper_sync/test_combined_workbook_wp_code_resolution.py`
    - `hypothesis`，`max_examples=5`；**双向变异证明**：含 `_RANGE_MARKERS` 字符的文件名恒空集，
      不含该类字符且含至少一个码的文件名恒非空集（结构性零必配非零变异）

  - [x]* 13.3 为 Property 11 写属性测试
    - **Property 11: 合册判据拒单码册**
    - **Validates: Requirements 10.5, 15.4**
    - `hypothesis`，`max_examples=5`；只声明一个码的文件名恒 `False`
    - 变异证明③：把 `_combined_book_covers` 的 `len(declared) < 2` 收窄条件短路掉后重算全域
      解析差集，断言差集**变大**（证明该条件在起作用而不是恒真装饰）

  - [x]* 13.4 为 Property 13 写属性测试
    - **Property 13: 祖先规则不越码边界**
    - **Validates: Requirements 10.6**
    - `hypothesis`，`max_examples=5`；「声明码 `C` + 直接拼数字」形态不命中（如声明 `A3-8` 对
      请求 `A3-80`）；「`C` + `-` + 后缀」形态命中

  - [x]* 13.5 为 Property 9 写属性测试
    - **Property 9: 祖先码解析到同一本合册**
    - **Validates: Requirements 10.6, 12.2**
    - `hypothesis`，`max_examples=5`；任意 wp_code 若其某祖先码被某合册字面声明且该码无自有
      载体，则解析结果是同一本合册

  - [x]* 13.6 为「同一 wp_code 被多本合册声明」建立可记录可复现判据
    - 该情形现算 **0** 例 ⇒ 判据须写成「将来出现 >1 时可记录、可复现，且结果不依赖
      `iterdir()` 枚举顺序」，用构造的临时目录做正面样本
    - 断言排序键是 `(len(name), name)`
    - _Requirements: 10.7, 10.8_

- [x] 14. Lane B：两处插入点与三码的期望终态

  - [x] 14.1 按加法方式插入两处调用
    - `find_template_file_any`：插在「A 子码严格分支」两次同名前缀尝试**之后**、
      `return None` **之前**
    - `find_template_file`：插在「`{主码}-N至{主码}-M`」范围回退**之后**、终极回退
      `startswith(主码 + " ")` **之前**
    - `_LEGACY_A_ONLY_SUB_CODE_RE` 保持 `r"^A\d+-\d+"` 语义不变（改成字母类无关会让
      `D2-2` / `E1-3` 这类 Excel 子表走子码分支，实测使数百个 wp_code 变 `None`）
    - 三条捷径显式否决，写进代码注释：① **禁**重新生成或手改 `wp_templates/_index.json`
      （该分支按**文件名**前缀判定而非 `e["wp_code"] == wp_code`，补索引记录对该分支无作用）
      ② **禁**用 `app/data/wp_code_overrides.json` 修此缺陷（该表值是 componentType 而非模板
      路径，且 Template_Finder 不读该表）③ **禁**动模块末尾的重绑定与 `*_unresolved` 别名
    - 两处都**不动** `_LEGACY_A_ONLY_SUB_CODE_RE.match` 与 `_resolve_most_specific_docx` 的
      调用位置与先后
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6_

  - [x]* 14.2 对照组走向不变测试
    - `A3-7` 现算在更早步骤命中合册本身；`D2-2` / `E1-5` / `F2-40` 现算在**范围回退**命中
      （三者 `_LEGACY_A_ONLY_SUB_CODE_RE.match` 均为 `False`），位置在新步骤之前
    - 断言这四个码两路解析结果与改动前**逐个相等**，且它们**不进**新步骤
    - _Requirements: 11.7, 16.4_

  - [x]* 14.3 为 Property 8 写属性测试
    - **Property 8: 合册声明码解析闭合**
    - **Validates: Requirements 11.1, 11.2, 12.1**
    - `hypothesis`，`max_examples=5`；分母是「全部合册 × 其字面声明的全部码」，断言
      `find_template_file` 与 `find_template_file_any` 两路都返回该合册本身

  - [x] 14.4 `A3-8` / `A3-8-1` 的期望终态验收 —— 修完**可用**
    - 两路入口都返回 `A/A3-7内部往来核对表、A3-8商誉减值测试.xlsx`；`A3-8-1` 经祖先规则返回
      同一本册
    - 证明终态是「可用」：既解析到册，又能指向册内对应 sheet（`A3-8商誉减值测试` 与
      `A3-8-1可收回金额测试`；该册 sheet 数现算）
    - 记录改动前 `find_template_file("A3-8")` 返回错册 `A3 合并流程程序表.xlsx`（静默错答）、
      改动后返回合册这一前后对照
    - 缺陷码分**两个分母**分别验收：「文件名声明了却解析不到本册」（现算 2 个：`A2-2` /
      `A3-8`）与「册内有 sheet 但文件名未声明」（现算 1 个：`A3-8-1`），合计 3；
      **合并成单一「3」= 不合格**（按文件名扫描永远得 2，会被误判成漏抓）
    - 🔴 **执行约束（R12.6 顺序不可颠倒）**：只做 a38 的**第一步（解析层）**；第二步（宿主层：
      Slice_Manifest 记 `resolution_kind = "literal_sheet_name"` /
      `sheet_name_literal = "A3-8商誉减值测试"`，即宿主传中文字面 sheet 名而非 wp_code）
      **登记为后继、不写成本 spec 任务**；顺序不可颠倒的实证 = 改动前
      `find_template_file_any("A3-8")` 为 `None` ⇒ 第二步单独做完零收益
    - 两本权威册（`A/A5-1 现金流量表审计.xlsx` 与
      `A/A3-7内部往来核对表、A3-8商誉减值测试.xlsx`）在本 spec 内为**只读事实，禁改动**
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5, 12.6, 12.7_

  - [x] 14.5 `A2-2` 的期望终态验收 —— **仅册可解析**
    - 两路入口都返回字面声明该码的合册
    - 如实记录 sheet 层事实：该册 sheet 数与「以 `A2-2` 起头的 sheet 数」两数**现算、禁写死**，
      现算结论是后者为 0 ⇒ sheet 层仍无供给
    - 把 `A2-2` 的 sheet 层供给登记为**独立的模板供给缺口**，本 lane 不承诺修复
    - 验收判据显式区分「册可解析」（承诺）与「可用」（不承诺）；与 `A3-8` / `A3-8-1` 合写成
      「修好就能用」= 制造假绿
    - _Requirements: 13.1, 13.2, 13.3, 13.4_

- [x] 15. Lane B：全域 wp_code 前后差集的零回归

  - [x]* 15.1 为 Property 12 写属性测试 + 全域差集探针
    - **Property 12: 全域解析差集恰为预期三码**
    - **Validates: Requirements 15.1, 15.3**
    - 探针 `backend/scripts/analyze/_psl_t15_global_diff.py`：按 Task 1.1 钉死的分母口径，
      对每个码记录改动**前**的 `(find_template_file, find_template_file_any)` 两路结果，
      改动**后**按同一口径重算
    - 断言前后差集**恰好**是 Task 14.4 的 3 个码，且每个码的新值是预期合册路径
    - 🔴 **本条属性的量化域是全域分母本身 ⇒ 用穷举而非 `hypothesis` 抽样**（穷举严格强于
      `max_examples=5` 的抽样；把它降级成随机抽样反而弱化判据）
    - 零回归判据**必须**是全域差集；以抽样若干码替代 = 不合格
    - _Requirements: 15.1, 15.2, 15.3, 15.5_

- [x] 16. Lane B：AST 守卫、既有合册零缺陷与共享文件合并

  - [x]* 16.1 核验 AST 顺序守卫保持绿（EXAMPLE，禁写成随机化属性测试）
    - 跑 `test_task58_word_canonical_resolver.py::test_finder_no_longer_uses_a_only_regex_for_sub_code_decision`
    - 现算断言仍成立：在 `find_template_file_any` 这个 `FunctionDef` 内，
      `_resolve_most_specific_docx` 调用行号 < `_LEGACY_A_ONLY_SUB_CODE_RE.match` 调用行号，
      且两个调用都存在（`a_only_line is not None` 亦被断言）；**行号由 AST 现算，禁写死**
    - 断言 Task 14.1 的两处插入未移动这两个调用的位置与先后关系
    - 单一结构断言 + 既有守卫已覆盖 ⇒ 本条是 EXAMPLE 不是属性
    - _Requirements: 16.1, 16.2_

  - [x] 16.2 现算多码册全域事实并断言其不变
    - 探针 `backend/scripts/analyze/_psl_t16_combined_books.py`：现算总数与按首字母分布、
      分隔形态（顿号 / 「至」）分布，校验两集合无交叠且分形态之和 == 总数
    - 与 Task 1.1 的改动前现算值逐项比对，断言 Lane B 落地后该组事实不变（全部现算、禁写死）
    - _Requirements: 16.3_

  - [x] 16.3 Lane B 落地后重跑 A_Domain_Guard 全部 5 个文件
    - 只跑单个文件 = 不合格；对照 Task 1.1 的改动前基线（现算，禁写死）
    - 逐条比对 Task 1.1 记录的 5 条预先存在失败，确认「改动前后同样红」作为归因证据，禁顺手修
    - _Requirements: 16.5_

  - [x] 16.4 共享文件 `test_a_entry_connection_blockers.py` 的合并与合并后基线重跑
    - 🔴 **执行约束（R16.6）**：两条 lane 并行落地时，该文件的合并由**后落地的那一条**负责；
      合并后**必须**重跑 A_Domain_Guard 基线
    - 合并判据：文件同时含 Lane A 侧改动（`TestStaticOnlyInstrumentationGap` 段已按 Task 10.1
      重写）与 Lane B 侧改动（`TestNoAuthoritativeWorkbook::test_a38_workbook_absent_on_disk`
      与顶部阻塞表「无权威册」那行已按 Task 17.1 更正），两侧互不覆盖
    - 若两条 lane 在同一工作树顺序落地（无分支合并），本任务退化为「核验该文件同时含两侧改动
      且基线重跑通过」，仍须执行
    - _Requirements: 16.6_

- [x] 17. Lane B：四处勘误与 Slice_Manifest 两字段的更正

  - [x] 17.1 把 `test_a_entry_connection_blockers.py::test_a38_workbook_absent_on_disk` 改为
        正向断言
    - 🔴 **执行约束（R14.10 编辑边界）**：Lane B 对该共享文件的编辑范围**限定**为
      `TestNoAuthoritativeWorkbook::test_a38_workbook_absent_on_disk` 与顶部阻塞表里
      「无权威册」那一行；**不得**触碰 `TestStaticOnlyInstrumentationGap` 或其模块级辅助
      （那是 Lane A 的边界，见 Task 10.1）
    - 改为断言「该合册在磁盘上**且** `find_template_file_any` 能解析到它」
    - docstring 的解除信号方向**反转**：由「册出现即打红」改为「解析不到即打红」
    - 把 `rglob("A3-8*")` 换成 `rglob("*A3-8*")` 后仍断言 `not found` = 不合格（那会立刻红，
      但红的原因是假事实被纠正，不是阻塞解除）
    - _Requirements: 14.1, 14.10_

  - [x] 17.2 更正 `test_a_lane3_runtime_exceptions.py` 的三处同源勘误
    - `TestBP6NoAuthoritativeBook::test_a38_workbook_is_null`：随 Task 17.3 的 Slice_Manifest
      `workbook` 字段更正，改为断言真实相对路径；保留 `is None` 断言 = 不合格
    - `::test_a38_template_not_on_disk`：删除假事实断言，替换为「合册存在 + 其文件名字面声明码
      集合含 `A3-8`」的事实断言；并改写 docstring 里「真因不只是 sheet 名写法，而是根本没有
      这本册」这句结论 —— **只改断言不改 docstring = 不合格**（错误归因会继续传播）
    - `::test_other_codes_resolve_but_a38_does_not`：重建变异证明，对照组改为「`A3-3` /
      `A5-1` / `A10-1` 经 `find_template_file_any` 能解析」，并加「`A3-8` 修复**前** `None`、
      修复**后**得合册」的**双向变异**；继续用 `rglob` 口径做变异证明 = 无效证明
    - 本任务须在 Task 17.3 之后执行（`workbook` 字段的真实路径是断言的输入）
    - _Requirements: 14.2, 14.3, 14.4_

  - [x] 17.3 更正 Slice_Manifest 的两个字段
    - 文件 `backend/data/workpaper_sync_abcs_cycle_manifest_slice.json`；按权威字段名
      **`entry_id`** 定位 `xlsx/gt-a38-goodwill-impairment` 条目（`entry_key` 现算不存在于
      条目键集合）
    - `template_ref.workbook` 由 `null` 改为真实相对路径（现值是**假事实**：册在磁盘上）
    - `template_ref.why_null`：补齐归因第一层（合册命名 + A-only 子码正则），或改为 `null`
      并记录缺陷已解除；**只改 `why_null` 文字而不改 `workbook` 字段 = 不合格**（现值只说了
      第二层，隐含「传对 wp_code 就能解析」，而改动前 `find_template_file_any("A3-8")` 同样
      是 `None`）
    - _Requirements: 14.5, 14.6, 14.8_

  - [x] 17.4 登记四条断言的共同成因与 AC-46 的再更正
    - 新建 `.kiro/specs/workpaper-sync-pure-static-lane-and-combined-workbook-resolution/errata.md`
    - 记录共同成因：`rglob("A3-8*")` 现算 **0** 命中、`rglob("*A3-8*")` 现算 **1** 命中，
      glob 锚定文件名开头而该合册真名以 `A3-7` 起头（两数现算、禁写死）
    - 记录归档 spec 的 AC-46 结论（「真因是根本没有这本册」）的**再更正**：结论与磁盘事实矛盾；
      按项目铁律「已归档 spec 一律不回填修改（append-only）」，该再更正**只登记在本 spec**，
      **禁**回填修改归档 spec 文件
    - _Requirements: 14.7, 14.9_

- [x] 18. Checkpoint —— Lane B 可独立发布点
  - Ensure all tests pass, ask the user if questions arise.
  - 此点 Lane B 的生产代码、数据文件与守卫已自洽，可独立发布 / 独立回滚

- [x] 19. 收尾：文档纪律自查、INDEX 登记与探针清理（两条 lane 共用）

  - [x] 19.1 三件套文档纪律自查
    - 探针 `backend/scripts/analyze/_psl_t19_doc_discipline.py`：扫 `requirements.md` /
      `design.md` / `tasks.md` / `errata.md`，断言无写死的源码行号、一切计数类判据均标
      「现算」或「现算值 + 禁写死」
    - 文件行数与编码一律 Python 读 bytes 后 decode 判定；含正则的核验走探针文件而非 `python -c`
    - _Requirements: 17.4_

  - [x] 19.2 在 `.kiro/specs/INDEX.md` 登记本 spec
    - 该文件是**纯 CRLF** ⇒ 必须 `read_bytes().decode('utf-8')` → 修改 → `write_bytes()`
    - 行插入 `## 一、Active Specs` 表首（表头与分隔行之后），进度写「0/{现算叶子任务数}」
    - 表格第三格内**不出现裸 pipe**；写回后以「每行恰 4 个未转义 pipe」校验整表
    - 同步更新顶部「统计」与现扫说明，Active 数与目录数一律**现扫** `.kiro/specs/*/tasks.md`
      得出，**禁按增量推算**
    - _Requirements: 17.3_

  - [x] 19.3 清理全部一次性探针
    - 删除 `backend/scripts/analyze/` 下**全部** `_psl_*` 前缀文件，含 Phase 1 遗留的
      `_psl_p1` ~ `_psl_p5` 五个 `.py` 与其 `.txt` 输出，以及本阶段新增的 `_psl_t*` 系列
    - 清理后现算断言：`backend/scripts/analyze/` 下 `_psl_*` 命中数为 **0**
    - _Requirements: 17.1_

- [x] 20. Final checkpoint
  - Ensure all tests pass, ask the user if questions arise.
  - 收口核对：A_Domain_Guard 全部 5 个文件已在两条 lane 落地后各重跑一次 + 合并后重跑一次；
    5 条预先存在失败「改动前后同样红」已记录；`_psl_*` 零残留；INDEX.md 已登记

---

## Notes

### 任务分布

- 顶层任务 **20** 条（含 4 条 Checkpoint：Task 5 / 11 / 18 / 20）；叶子子任务 **52** 条
- **Lane A（Task 2 ~ 12）27 条** · **Lane B（Task 13 ~ 17）20 条** · **共用（Task 1 / 19）5 条**
- `*` 标记的是测试类子任务；按项目铁律 **`*` 任务同样要做完**，除非用户明确说跳过。
  唯一的例外形态是外部依赖（Task 12 的真栈往返：环境不可用时如实标「待环境」+「代码已改但
  未实测」，且 `adapter_registered` 保持 `False`）

### 两条 lane 的独立交付

生产代码模块集合交集为空 —— Lane A 动 `excel_instrumentation.py` /
`projection_first_publication.py` / `published_identity_observer.py` /
`phase5_a51_cashflow_audit.py` / `adapters/delivered_contracts_ledger.py`；
Lane B 动 `wp_template_finder.py` 与 `data/workpaper_sync_abcs_cycle_manifest_slice.json`。

下方 waves 把两条 lane 交错排布以体现可并行。**只发布一条 lane 时**：取该 lane 的子任务
子序列按原相对顺序执行即可，另一条 lane 的任务**不是**前置（Task 1 的现算除外，两条都依赖它）。

### 共享文件的三条执行约束

唯一共享文件 `tests/workpaper_sync/test_a_entry_connection_blockers.py`（它同时装着 a38 阻塞
与 §6 纯静态缺口，本 spec 不重排其组织方式）：

1. **Lane A 边界（R8.7 / Task 10.1）**：只动 `TestStaticOnlyInstrumentationGap` 类及其模块级
   辅助（`_ROW_GEOMETRY_ATTRS` / `_SUBSTRATE_PROVIDER_ENTRY_NAMES` /
   `static_injection_entry_points` / `top_level_function_names`）
2. **Lane B 边界（R14.10 / Task 17.1）**：只动
   `TestNoAuthoritativeWorkbook::test_a38_workbook_absent_on_disk` 与顶部阻塞表里
   「无权威册」那一行
3. **合并责任（R16.6 / Task 16.4）**：并行落地时由**后落地的那条 lane** 负责合并，且合并后
   **必须重跑** A_Domain_Guard 基线

### 两处顺序不可颠倒

1. **Lane A：Task 7（第 6 处）整体先于 Task 8（第 5 处）**。`_observe_workbook` 在 `observe()`
   内的执行顺序早于 `_build_identity_binding`（位置实证见 Task 1.2，现算、禁写死行号）⇒
   「静态主 binding 已支持」**不能**当作第 6 处已完成的证据；Task 7 未做时 Task 8 的运行时
   路径根本到不了，会撞裸 `AttributeError`
2. **Lane B：a38 第一步（解析层，Task 14.4）先于第二步（宿主层）**。第二步**不在本 spec**，
   登记为后继；改动前 `find_template_file_any("A3-8")` 为 `None` ⇒ 第二步单独做完零收益

### digest 不变式是 Lane A 的收口判据

Task 4.3 是 Lane A 的收口验收条件：`canonical_digest(新平台构建器输出)` 必须**逐位等于**
`canonical_digest(Canary_Provider 现自组装输出)`，且与契约字段 / 守卫常量 / 真库 artifact
三方同值（现算前缀 `223b5a69…`，判据以常量为锚、禁写死全值）。

**三条禁止**：不相等时只能修 Static_Payload_Builder；**禁**改契约、**禁**改守卫常量、
**禁**改真库 artifact 去迁就 —— 触犯任一条即判不合格并回退。

### 测试分类纪律

- **13 条 Property → 属性测试**（`hypothesis`，`max_examples=5`，项目铁律禁默认 100）：
  P1→3.2 · P2→3.3 · P3→3.4 · P4→8.4 · P5→8.3 · P6→7.3 · P7→9.1 · P8→14.3 · P9→13.5 ·
  P10→13.2 · P11→13.3 · P12→15.1 · P13→13.4
  —— 唯一例外是 **P12（Task 15.1）**：它的量化域就是全域 wp_code 分母本身，**用穷举而非抽样**
  （穷举严格强于 `max_examples=5`；降级成随机抽样反而弱化判据）
- **2 条 EXAMPLE 不是属性，禁写成随机化测试**：A-4 digest 不变式（R3.8 / Task 4.3，单一冻结
  入参）· B-7 AST 顺序不变式（R16.1 / Task 16.1，单一结构断言）
- **1 条 INTEGRATION 执行 1 次**：真栈往返（R9 / Task 12.1 ~ 12.2，依赖真 OO 与真浏览器，
  100 次迭代不增加缺陷发现率）
- **四处变异证明**：① `static_injection_entry_points` 双向变异 → Task 10.1
  ② `_literal_wp_codes_in_filename` 无范围标记必非空 → Task 13.2
  ③ `_combined_book_covers` 的 `len(declared) < 2` 短路后全域差集必变大 → Task 13.3
  ④ 静态注入「无新增 Table 部件」在人为注一个 Table 后必变红 → Task 3.3

### 回归基线

A_Domain_Guard = 5 个文件（`test_a51_component_type_routing.py` /
`test_a_cycle_foundation_canary.py` / `test_a_entry_connection_blockers.py` /
`test_a_lane2_docx_authority.py` / `test_a_lane3_runtime_exceptions.py`）。改动前基线
**现算（写作时刻快照为 159 passed，实现时须重算并以重算值为准，禁写死进任何断言）**。

每条 lane 落地后都必须跑**全部** 5 个文件（Task 10.2 / Task 16.3），**只跑单文件不合格**；
合并后再跑一次（Task 16.4）。Lane A 允许的红只有 Task 10.1 列举的 3 条，且须在同一 lane 内
被改写为绿；阻塞①②③④⑥ 与「已达成① digest 三方相等」任一变红 ⇒ 判为「放宽了既有校验」并回退。

### 预先存在的失败（改动前已红，与本 spec 无因果，禁纳入范围也禁顺手修）

Task 1.1 记录改动前红态，Task 10.2 与 Task 16.3 记录改动后仍红，两段合起来构成
「改动前后同样红」的归因证据：

- `test_registration_isolation_and_alignment[d3]`
- `test_dedicated_component_registry_contract::test_whole_subset_of_valid_and_fe`
- `test_task57_abcs_and_shared_migration::TestGuardSelfChecks::test_the_n_style_per_entry_dual_mode_scanner_finds_nothing_here`
- `b60.hour_budget.json` CRLF 致字节稳定性 1 red
- `test_task75_published_identity_observer::TestDebtRemovedWithRealImpl` 4 项
  （`phase5_c_control_test` 缺 `resolve_published_frozen_definitions`）

### 探针与文件纪律

- 一次性探针一律 `backend/scripts/analyze/_psl_*.py` + 输出 `_psl_*.txt`；`_` 前缀 = 用完即删，
  Task 19.3 统一清理并断言零残留
- 含正则的核验**一律写探针文件**，禁 `python -c`（shell 传参会把 `\d` 变字面反斜杠）
- 文件行数与编码**一律** Python 读 bytes 后 decode 判定（PowerShell 的行数与编码显示不可信）
- 三件套文档**禁写死源码行号**；一切计数类判据标「现算」或「现算值 + 禁写死」
- `INDEX.md` 是**纯 CRLF** ⇒ `read_bytes().decode('utf-8')` → 改 → `write_bytes()`，
  表格第三格禁裸 pipe，校验「每行恰 4 个未转义 pipe」
- 两本权威册（`A/A5-1 现金流量表审计.xlsx` 与 `A/A3-7内部往来核对表、A3-8商誉减值测试.xlsx`）
  在本 spec 内为**只读事实，禁改动**

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2"] },
    { "id": 1, "tasks": ["2.1", "13.1"] },
    { "id": 2, "tasks": ["3.1", "13.2"] },
    { "id": 3, "tasks": ["4.1", "13.3"] },
    { "id": 4, "tasks": ["2.2", "4.2", "13.4"] },
    { "id": 5, "tasks": ["3.2", "6.1", "13.5"] },
    { "id": 6, "tasks": ["3.3", "7.1", "13.6"] },
    { "id": 7, "tasks": ["3.4", "7.2", "14.1"] },
    { "id": 8, "tasks": ["3.5", "8.1", "14.2", "16.2"] },
    { "id": 9, "tasks": ["4.3", "8.2", "10.1", "14.3"] },
    { "id": 10, "tasks": ["6.2", "14.4", "16.1", "17.3"] },
    { "id": 11, "tasks": ["7.3", "14.5", "17.2"] },
    { "id": 12, "tasks": ["7.4", "15.1", "17.1"] },
    { "id": 13, "tasks": ["8.3", "17.4"] },
    { "id": 14, "tasks": ["8.4"] },
    { "id": 15, "tasks": ["9.1"] },
    { "id": 16, "tasks": ["9.2", "16.4"] },
    { "id": 17, "tasks": ["10.2", "16.3"] },
    { "id": 18, "tasks": ["12.1"] },
    { "id": 19, "tasks": ["12.2"] },
    { "id": 20, "tasks": ["10.3"] },
    { "id": 21, "tasks": ["19.1"] },
    { "id": 22, "tasks": ["19.2"] },
    { "id": 23, "tasks": ["19.3"] }
  ]
}
```
