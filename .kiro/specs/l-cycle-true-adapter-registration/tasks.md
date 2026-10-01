# L 循环真双向改线（adapter 注册）— 任务

> **实施纪律**
> - 🔴 验收口径是 **manifest 现算翻转**，不接受「勾选完成」作为证据。
> - 🔴 所有计数现算，与 `design.md` 等值比对；禁写死行号（模板改版会漂，锚点用 marker / 常量名）。
> - 🔴 `[ ]*` 只用于**真**外部依赖。docker `audit-onlyoffice` 实测 healthy ⇒ OO evidence
>   **不得**标 `*`，跑不通要写出具体失败原因。
> - 🔴 `store_item_registry.py` 只追加一个 dict 条目（并发会话共同触点）。
> - 🔴 前序三份 L spec 与所有 `_archive/` 下 spec **一律不回填修改**，勘误只登记在本 spec。
> - 每一环独立 commit，任一环回滚不牵连其他环。
> - 守卫落 `backend/tests/workpaper_sync/test_l1_adapter_registration.py`。
>
> **实施状态（2026-09-28）**：阶段 0~3 共 **6 / 14** 条已完成（task 1~6），
> 守卫 `test_l1_adapter_registration.py` **55 test 全绿**。
> 零回归实测：29 个 `generate_phase5_*.py --check` 全过（51 份既有契约 digest 零漂移）·
> 框架层与 registry 相关 **301 test** 全绿 · `check_sheet_specs_fully_registered` 通过（42 adapter）。
>
> 🔴 **task 7/8 已就绪但需用户拍板后再执行**，两处高风险：
> ① **task 7 要写真库** —— `publish_definitions` + `finalize_candidate` 会在
> `working_paper_content_version` / `working_paper_content_representation` /
> `working_paper_sync_entry_state` 三表真实插行（当前 267 / 274 / 12）。
> ② **task 8 要重生成 `backend/data/workpaper_sync_entry_manifest.json`，而该文件正被并发会话
> 修改且未提交**（`git status` 为 `M`）⇒ 重生成可能**覆盖并发会话的未提交改动**。
> 必须先与该会话对齐（或等其提交）再跑生成器。
>
> 🔴 **并发会话造成的既有守卫红（本 spec 不代改，如实登记）**：
> · 7 个 L 守卫文件 30 红中 **27 条**属并发会话 —— 它已删 `useL5~L8DualMode.ts`、摘除 BP-4
> inert 开关、挂上 BP-7 notice、改动 `L5 长期应付款.xlsx` 与 `entry_manifest.json`，
> 使「orphan 存在 / inert 生效 / notice 未挂 / 模板 size / localStorage 站点数」等断言整体过期。
> · `test_d3_07_dual_zone_shift_and_verify.py` **10 红** —— 其 provider
> `phase5_d3_07_voucher_check.py` 与测试本身都是未跟踪新文件（`??`），而
> `d3.prepaid_receipts_detail.json` 契约现算只有 1 张表 `prepaid_receipts_detail_rows`、
> **无 `voucher_check_current_rows`** ⇒ 是「新 sheet 未扩进契约」的中间态，与本 spec 零关系。
> · `test_registration_isolation_and_alignment.py::[d3] DID NOT RAISE` —— d3 已被并发会话修对齐，
> 而该测试期望它仍不对齐（`_KNOWN_MISALIGNED` 过期）。
> · `PILOT_CONTRACT_OWNERS`（写死 10 项 vs 现算 **51** 份生产契约）在本 spec 之前就已整体过期。

## 阶段 0：前提复核与勘误落断言

- [x] 1. 把三处已失效前提钉成守卫
  - 真库现查三表行数，断言 `entry_state` 覆盖 entry 数 ≥ **11**，且逐个 entry_id 具名
    （`b60` / `d1` / `d2` / `d3` / `d4` / `d5` / `d6` / `d7` / `g7` / `h1` + opaque 1）
  - 🔴 断言 BP-61-1 的解除理由是「entry 覆盖面」而非「表非空」—— 变异：把行数改成非空但
    entry 覆盖为 0，断言结论翻回「仍阻塞」
  - 🔴 断言 D3/D5/D6/D7 有 representation 但 manifest 仍 `legacy_fake_bidirectional`
    （剩余差距在治理动作，本 spec 对 L 域自带该动作）
  - 按 `item_id ~ '^L[0-9]'` 逐域现算 remark/conclusion 非空数，**NULL 与空串分开计**，
    等值比对 design §1.2 表；断言 L2~L8 全部非零 ⇒ 前序「L6/L7/L8 真库 0 行」失效
  - 断言 `conclusion` 全域 **0** 仍成立，并配人造正样本变异证明扫描器非空转
  - _判据：LR-P1、LR-P2、LR-P3、LR-P4_
  - **实施证据**：`test_l1_adapter_registration.py::TestBP611PremiseInvalidated`（4 test）
    + `::TestLDomainRealPayload`（4 test）。真库现算 `entry_state` **12 行 / 11 entry**、
    `content_version` **267**、`representation` **274**；L2~L8 remark 非空逐域
    **8 / 7 / 6 / 7 / 5 / 5 / 5** 全非零；`conclusion` 全域 **0** 且配 C 域变异证明
    （C 域 conclusion 非空 > 0 ⇒ 扫描口径非空转）。`_bp611_released()` 三组入参变异：
    (553,11)=True · (553,0)=False · (0,11)=False ⇒ 解除理由锁定在 entry 覆盖面。
    D3/D5/D6/D7 四条现算「有 representation 但 manifest 仍 legacy」成立。

- [x] 2. 把 candidate contract 的两处实质错误钉成守卫
  - 现算真库 `L1-adj-*` 的字段段集合，断言恰为 8 个：
    `aje` `audited` `beginning` `creditAmount` `debitAmount` `endBalance` `rje` `unadjusted`
  - 断言 candidate 声明的 `beginUnadjusted` / `beginAje` / `beginRje` / `beginAudited` /
    `endUnadjusted` / `endAje` / `endRje` / `endAudited` 在真库命中 **0** ⇒ 字段名不匹配
  - 🔴 逐格判 `审定表L1-1` 的 R7~R11 × B..L，断言**可输入格数 == 0**（全部 `str.startswith("=")`）
  - 断言 B7 公式含 `SUMIF` 且引用 `明细表L1-2`，K7 含裸 `IF(` 且不含 `IFERROR`
  - 断言「按 candidate 接线会覆盖 SUMIF」这一结论有可复算依据（把 B 列列入可写集合即打红）
  - _判据：LR-P5、LR-P6_
  - **实施证据**：`::TestCandidateContractDefects`（5 test）。真库字段段现算恰 8 个
    （`aje/audited/beginning/creditAmount/debitAmount/endBalance/rje/unadjusted`）；
    candidate 声明的 8 个字段名（`beginUnadjusted`…`endAudited`）真库命中 **全 0**
    且与真集合**零交集**；`审定表L1-1` R7~R11 × B..L 可输入格数 **0**；
    B7 含 `SUMIF` 且引用 `明细表L1-2`、E7 == `=B7+C7+D7`、K7 是裸 `IF(` 无 `IFERROR`；
    变异：把 B/C/D 当可写格时三格全部被识别为「会覆盖公式」。

- [x] 3. `明细表L1-2` 几何基线冻结
  - openpyxl 现算八项并等值比对 design §2.2：`dims A1:AD49` / `max_row 49` / `max_col 30` /
    表头 R8+R9 / `header_rows=2` / 数据区 R10~R25 / footer R26 / 有效列 A..AB
  - 断言公式列**恰** K/R/S/T/U 五列，逐列公式行区间现算；断言 K=`H+I-J`、R=`H+L+M`、
    S=`I+N+P`、T=`J+O+Q`、U=`R+S-T` 的形态
  - 断言 footer R26 的 SUM 公式落在 H/I/J/L/M/N/O/P/Q 九列
  - 🔴 footer 标签文本与空格形态**现算**，禁抄 d6 的「合   计（3 半角空格）」
  - 现算整册裸 IF **112** 格，逐 sheet 分布等于 design §4.3；断言受管表 `明细表L1-2` **0** 格
  - 现算 definedName **0 / broken 0**，配人造正样本（造一个含 `#REF!` 的 defined name）变异证明
  - 现算合并单元格集合，断言 R8/R9 叶子组存在且不跨数据区
  - _判据：LR-P7、LR-P8、LR-P9、LR-P10_
  - **实施证据**：`::TestManagedSheetGeometry`（8 test）。几何八项现算全中；数据区
    （R10~R25）公式列恰 **K/R/S/T/U** 且形态 `=H+I-J` / `=H+L+M` / `=I+N+P` /
    `=J+O+Q` / `=R+S-T` 逐条成立；整册裸 IF **112** 格逐 sheet 分布全中、受管表 **0**；
    definedName **0** 且注入 `#REF!` 探针后扫描器命中 ⇒ 空分母可信。
  - 🔴 **两处首版判据被实测打红并改正**（design §2.3 留痕）：① footer SUM 列首版写
    9 列，实测 **H..U 连续 14 列全 SUM** —— 根因是把探针 `rows[:12]` 的截断输出当全集
    ② footer 标签首版按 d6 假定在 A 列，实测在 **C26 = `合计`**（A26 为空，无 3 空格形态）。
    另现算 K 列在 **R3/R4 页眉区也有公式** ⇒ 新增判据锁「公式列扫描必须限定数据区」，
    否则 `formula_mask` 跨度会从 R10 错扩到 R3。

## 阶段 1：provider 落成

- [x] 4. 建 `backend/app/services/workpaper_sync/phase5_l1_short_term_loans.py`
  - 按 design §3 的接口全集同构 `phase5_d6_contract_assets.py`，常量全部取自 task 3 的现算值
  - `ADAPTER_ID = "l1.short_term_loans"`、`ENTRY_ID = "xlsx/gt-l1-short-term-loans"`、
    `MANAGED_SHEET = "明细表L1-2"`、`TEMPLATE_RELATIVE_PATH = "L/L1 短期借款.xlsx"`
  - `TEMPLATE_SHA256` 现算落常量；`instrumentation_spec()` 单数（本轮单受管 sheet）
  - 🔴 `MANAGED_FIELD_SPECS` 逐列声明：19 个可输入列 + 5 个 `mode=formula` 列，
    `value_type` 按实测（序号 number / 日期 string / 年利率 number / 索引 string / 核对 boolean-ish）
  - `FORMULA_MASK` 覆盖 K/R/S/T/U；`row_identity` 用隐藏 UUID 列，列号取 `max_col+1` 现算
  - 断言 provider 全部接口 `callable`，且 `assert_entry_selectable` /
    `assert_no_implicit_template_fallback` 真实生效（变异：换个不存在的模板名必抛）
  - _判据：LR-P11_
  - **实施证据**：`phase5_l1_short_term_loans.py` 落成，`::TestProviderInterface`（6 test）
    断言 **25** 个接口全 `callable`、身份常量与 manifest 现算一致（`wp_code_patterns=['L1S']`、
    profile `xlsx.editable.shared.single.room_service_wired.v1`）、模板 sha256 哨兵
    `78033d80…` 现算相符、几何常量与 task 3 基线逐项对齐、28 字段、UUID 列 `AE` 现算
    在 `max_column=30` 之外。
  - 🔴 **比 d6 样板更省**：发现框架层 `RowTableSheetSpec` + `spec_to_contract_sheet_payload`
    已能自动派生 sheet payload 与 formula_mask ⇒ provider 只声明 `SPEC_L12` 一处，
    不手写字段展开（d6 那版 `_rows_table_payload()` 手写逻辑无需复制）。
    `aging_layout=None` / `aging_groups=()` —— L1 无账龄组，两级表头是「调整类型 × 增减方向」。
    `ghost_row_anchor_index=2`（`bank` 贷款单位）：`[0]` `seq_no` 是整数序号（`0` 是合法真值，
    同 d6 不可用）、`[1]` `loan_type` 是枚举（同 d5 `category` 不适合）。
  - 🔴 **框架层补了一个声明位**：`spec_to_contract_sheet_payload` 原把 footer
    `search_column` **硬编码成 `"A"`**，而 L1 标签在 C26（A26 为空）⇒ 自动派生出的契约会让
    `excel_materialize._find_marker_row` 一处都找不到 marker 并抛 `FooterAnchorDriftError`
    （`phase5_d3_05_long_term` 踩过同一坑，当时是改模板绕开）。已给 `RowTableSheetSpec`
    加 `footer_search_column: str = "A"`，**默认值不变 ⇒ 既有七家零回归**
    （守卫 `test_framework_default_search_column_stays_A_for_other_providers` 钉住默认值）。

## 阶段 2：contract 交付（③环）

- [x] 5. contract 从 candidate 转 reviewed 并与代码锁死
  - 实现 `build_contract_payload()`，`review_status="reviewed"`、`semantic_version="1.0.0"`、
    `contract_id="l1.short_term_loans"`
  - 🔴 模板哈希字段名必须是 `template_sha256` 与 `normalized_structure_hash`
    （写 `sha256`/`structure_hash` 会被 `definitions._SELF_REFERENCE_KEYS` 递归拒绝）
  - 断言 payload 过 `contracts.py::parse_contract`；断言无 `bundle_*` 前向引用
  - 建 `backend/scripts/gen/generate_phase5_l_contracts.py`（多 entry 合一，对标
    `generate_phase5_h_contracts.py`），`--check` 与 `--apply` 双模式
  - 落盘 `backend/data/workpaper_sync_contracts/l1.short_term_loans.json`，
    **删除** `l1.short_term_loans.candidate.json`；`review.entry_id` 改为真 entry_id
  - 断言 `assert_contract_file_matches_source()` 磁盘与代码逐字节相等
  - 🔴 同步更新 `test_task54_l_cycle_migration.py::test_no_pilot_contract_belongs_to_the_l_cycle`：
    期望从「L 域零 contract」改为「恰 1 条且为 `l1.short_term_loans`」——
    **禁删断言、禁加豁免**；并在该测试里写明本 spec 名作为变更依据
  - 断言 `identity_carriers` 只含 `hidden_uuid_column`，锚点不含 `sheet_id` / `sheet_display_name`
  - 断言字段级六件齐、`row_identity.kind == "field"`、`json_pointer` 恰一个 `{row_uuid}`、
    `delete_policy == "tombstone"`、`header_rows == 2`、`footer_anchor` 用 marker 非行号
  - 断言无 `^col_[a-z]+$` 形态字段
  - _判据：LR-P12、LR-P13、LR-P14、LR-P15、LR-P16、LR-P17_
  - **实施证据**：`::TestContractDelivery`（14 test）+ `::TestContractOwnershipInLDomain`（5 test）。
    生产契约 `backend/data/workpaper_sync_contracts/l1.short_term_loans.json` 已落盘
    （`canonical_digest=0567f0106127c6e97781fc8ecd8e66984c67bed3d26ce76d0249da858bdc7952`），
    `review_status=reviewed` / `semantic_version=1.0.0` / `review.entry_id=xlsx/gt-l1-short-term-loans`；
    28 字段、`formula_mask=['K10:K25','R10:R25','S10:S25','T10:T25','U10:U25']`、
    `header_rows=2`、`anchor=A8`、`row_identity={kind:field, json_pointer:/rows/*/rowId}`、
    `footer_anchor={marker:合计, search_column:C, carries_total_formula:True}`。
    `assert_contract_file_matches_source()` 双向锁通过。candidate 草案已删。
  - 生成器 `backend/scripts/gen/generate_phase5_l_contracts.py`（多 entry 合一，L2~L8 只加一行），
    带 `--check` / `--apply` / `--only`，并内建**双源检测**（已转 reviewed 却仍留
    `.candidate.json` 即报错退 1 —— 实测在删草案前正确报出）。
  - 🔴 **既有守卫按新事实重写 2 条**（不删断言、不加豁免，期望从「零」改为「恰 1 条且具名」）：
    `test_task54_l_cycle_migration.py::test_no_slice_entry_has_a_contract`（改为
    `migrated={l1}` 白名单 + 反方向 L2~L8 冒出契约照样红）与
    `test_l_foundation_p3_template_and_canary.py::test_l_prefix_contract_count`
    （总数仍锁 2，l1 必须 reviewed + entry_id 具名、l4 必须 candidate + entry_id 为 null、
    candidate 文件必须不存在）。两条现已绿。
  - 交付登记表 `adapters/delivered_contracts_ledger.py` **末尾追加**一条（不重排既有条目），
    否则 `test_task13_contract_registry.py::test_contract_directory_matches_the_delivery_ledger`
    会红（「仅在磁盘 ['l1.short_term_loans']」）。
  - 🔴 **零回归实测**：29 个 `generate_phase5_*.py` 全部 `--check` 通过、**0 失败** ⇒
    框架层新增 `footer_search_column` 对既有 **51** 份契约 digest 零漂移；
    框架层与 registry 相关 301 test 全绿。
  - 🔴 **一处自纠**：`value_type` 首版给年利率写 `number`，被 schema 打红
    （封闭枚举是 `['amount','boolean','date','datetime','enum','integer','json','rate','ratio','text']`）
    ⇒ 改用 `rate`，起止日期同时从 `text` 升为 `date`。
  - 🔴 **责任划分（不代改并发会话）**：跑既有 7 个 L 守卫文件得 30 红，其中**仅 3 条与本 spec
    相关**（上述 2 条已改 + 交付登记表 1 条已补）；其余 **27 条属并发会话**
    （分支 `work/2026-09-27-k-lane1-template-orphan-keys`）—— 它已删
    `useL5~L8DualMode.ts`、摘除 BP-4 inert 开关、挂上 BP-7 notice 组件、改动 `L5 长期应付款.xlsx`
    与 `entry_manifest.json`，使既有守卫的「orphan 存在 / inert 生效 / notice 未挂 / 模板 size」
    等断言整体过期。另 `a51.cashflow_audit.json`（并发新增，未跟踪）`review_status=reviewed`
    却缺 `review.entry_id`，已登记进本 spec 守卫的 `KNOWN_CONCURRENT_GAPS`
    （平台既有范式，见 `test_registration_isolation_and_alignment.py::_KNOWN_MISALIGNED`），
    并配「已修好就必须移除」的反向断言防登记表长期留过期条目。
  - 🔴 **`PILOT_CONTRACT_OWNERS` 已整体过期，不在本 spec 修**：该常量写死 10 项，而生产契约
    现算 **51** 份（D/E/F/G/H/I/J 全域陆续交付）—— 依赖它的 2 条测试在本 spec 之前就已红。
    本 spec 改为在自己的守卫里按「计数现算、禁写死」重建其实质判据
    （`TestContractOwnershipInLDomain`：L 域生产契约恰 1 条且为 l1 / 每份生产契约都要声明
    owner / `contract_id` 必须等于文件名 / candidate 的 entry_id 必须为 null）。

## 阶段 2.5：HTML 侧对齐（契约的前置，见 design §2.4）

- [x] 5b. `det` 表切 d6 式稳定行身份通道
  - 现算确认真库 `L1-det-*` 为 **0 行 / 0 distinct item**（零迁移负担的前提，变了就停）
  - 给 `useL1FormData.ts` 的 `det` 表新增一条通道：单条 item `L1-2-rows`，
    载荷是整行数组 `JSON.stringify(rows)`，每行带稳定 `rowId`（对标 d6 的 `ROW_IDENTITY_STORE_KEY`）
  - 🔴 **只改 `det`**：`_parseDynamicRows` / `_serializeRows` 通用函数与
    `int` / `cred` / `ovd` / `plg` 四表**一行不改** —— `int` 被 `h2L1LoanPull.ts`
    跨循环消费（`L1-int-{n}-{field}`），改它会连带 H2
  - 断言旧路径 `L1-det-{n}-{field}` 的序列化调用点已移除，且其余 4 个 prefix 的调用点**仍在**
  - `DetailRow` 扩展到对齐模板 28 列：补 G 固定/浮动 · L/M 期初调整 · N/O 账项调整 ·
    P/Q 重分类调整 · **R/S/T/U 审定数四列** · Y 是否逾期 · Z 询证函 · AA 征信核对 · AB 备注
  - `amount` / `currency` 保留为 HTML-only，**不入契约**，在契约里登记不映射原因
  - 🔴 断言 `endBalance` 仍由 `calcLiabilityEndBalance(beginning, creditAmount, debitAmount)`
    计算，且与模板 `K=H+I-J` 语义等价（增加=贷方 / 减少=借方）
  - 前端 vitest 覆盖：新增行→rowId 唯一、删中间行→其余行 rowId 不变（位置化缺陷的反例）
  - _判据：LR-P12 前置、LR-P17、LR-P24 前置_
  - **实施证据**：前端 `l1DetailStableRowId.spec.ts`（**9 test 全绿**）
    + 后端跨端对账 `TestHtmlStoreShapeAgreesWithProvider`（**6 test**，合计 60 passed）。
    `DetailRow` 扩到 **28 个受管字段**（逐字段对齐模板 A..AB）+ `rowId` + 2 个 HTML-only
    （`amount` / `currency`）；新增 `createEmptyDetailRow()` 工厂与导出常量
    `DETAIL_ROWS_ITEM_ID = 'L1-2-rows'`；`_parseDetailRows` 改为读单条 item 的 JSON 数组
    （坏载荷给空表不半解析、缺 `rowId` 当场补铸）；序列化改为只发一条 item，
    空表落 `null`；`useL1Detail` 的 `_triggerSave`/`_triggerSaveAll` 换成整表 `_persist()`，
    并新增 `removeRowById()`（排序/筛选后下标不可信时的正解）。
  - 🔴 **复用既有 `newRowIdentity(prefix)`**（`composables/shared/rowIdentity.ts`），
    不新造第 6 个同型铸号模块 —— 该文件头已登记平台上 5 个同型模块与「是否收敛」的技术债。
  - 🔴 **只改 `det`**：`_parseDynamicRows` / `_serializeRows` 通用函数与 `int`/`cred`/`ovd`/`plg`
    四表一行未动，并加**反向判据** `test_sibling_tables_keep_their_positional_channel`
    钉住它们仍走位置化通道（哪天被改会红，提醒先核对 H2 对 `L1-int-*` 的消费）。
  - 🔴 **死代码已删不留回落**：`DETAIL_FIELDS` 常量、`_serializeRows(items,'det',…)` 调用点
    全部移除（真库 `L1-det-*` 现算 0 行 ⇒ 回落路径永不执行，留着就是死路径）。
  - 🔴 **一处判据自纠**：首版用裸文本扫 `L1-det-` 判「旧通道已拆除」，结果命中**自己写的
    注释**（两份文件都要解释旧形态为何被换掉）⇒ 改为剥 TS 注释后再扫，并补
    `test_comment_stripper_is_not_vacuous` 变异证明（注释里的键被剥掉、代码里的留得住、
    `https://` 的 `//` 不被当行注释）。与平台铁律「命中后必须判注释/代码」同源。
  - 零回归：`npx tsc --noEmit` 对 L1 **零错误**（21 个既有错误全在 G 循环 4 个语法破损文件）；
    前端 L1 既有测试 28 passed；全量 vitest 2110 passed / 15 failed，失败的 7 个文件
    （C/G/D 循环 + 通用 PBT）对 L1 模块引用**现算全为 0** ⇒ 与本改动无关。
  - 🔴 **未做**：`DETAIL_SEGMENTS` 的 UI 列展示只覆盖原 14 字段，新增 16 列尚未进分段
    （纯展示层，需 Playwright 实测），登记为 task 5c。

## 阶段 3：adapter 注册

- [x] 6. 在 `STORE_MERGE_REGISTRY` 追加 `l1.short_term_loans`
  - 🔴 只**追加**一个 dict 条目，不重排既有条目、不改既有注释（并发会话共同触点）
  - `provider_module="phase5_l1_short_term_loans"`，item 恰 1 条：
    `StoreItemSpec(item_id="L1-2-rows", kind=StoreKind.rows)`
  - 现算真库 `item_id LIKE 'L1-2-%'` 命中 **0**，断言新键是干净命名空间，
    且与 `L1-adj-*`（32 行）/ `L1-chk-conclusion`（1 行）无撞名
  - 挂 `oo_crash_neutralization_fn="neutralize_oo_crash_if_formulas"`（per-file 策略，
    受管表零命中也挂 —— 同册 `审定表L1-1` 34 格等需要它）
  - 🔴 断言 `_resolve_oo_crash_neutralization_fn("l1.short_term_loans")` 返回的函数对象
    与 `g7.soe_subsidiary_disclosure` 解析结果**是同一个对象**（`is` 判定，不是同名替身）
  - 🔴 断言 `adapters/excel.py` 源码里不含 `adapter_id == "l1` 字面量分支
  - 断言 `check_sheet_specs_fully_registered` 通过，且分母只增 1
  - _判据：LR-P18、LR-P19、LR-P20_
  - **实施证据**：`::TestAdapterRegistration`（9 test）。`STORE_MERGE_REGISTRY` 末尾
    **追加**一条（不重排既有条目、不改既有注释）：`provider_module="phase5_l1_short_term_loans"`、
    `items=(StoreItemSpec(item_id="L1-2-rows", kind=StoreKind.rows),)` 恰 1 条、
    挂 `oo_crash_neutralization_fn="neutralize_oo_crash_if_formulas"`。
  - 🔴 `_resolve_oo_crash_neutralization_fn("l1.short_term_loans")` 与
    `("g7.soe_subsidiary_disclosure")` 现算返回**同一个函数对象**（`is` 判定通过）⇒
    是共用而非同名替身；`adapters/excel.py` 源码内 `adapter_id == "l1` 现算 **0** 次。
  - 🔴 四张未接线的位置化表（`L1-int-*` / `L1-cred-*` / `L1-ovd-*` / `L1-plg-*`）
    确认**未预登记**；真库 `L1-2-*` 与 `L1-det-*` 现算均 **0 行**（干净命名空间 + 零迁移负担，
    两条都配了「若非 0 则必须重选键 / 先写迁移脚本」的失败提示）。
  - 门禁 `check_sheet_specs_fully_registered.py` 通过：**42 个 adapter 已注册**（分母只增 1）。
  - 🔴 **顺序门正面判据已落**：`test_manifest_capability_gate_still_blocks_registration`
    断言「contract + registry 就位 ≠ 可挂 adapter」—— manifest 仍是 legacy 时
    `manifest_capability_enabled()` 必须为 False 且 `assert_manifest_capability_enabled()`
    必须抛错。Task 8 翻转后本断言自动走另一分支（不需要删）。

## 阶段 4：五环发布与 manifest 翻转

- [x] 7a. ④⑤ 两环的前置全部就位，只读预演跑通（**不写库**）
  - 🔴 **纠正入口**：首版设计写的 `excel_entry_gate.finalize_candidate(...)` 是错的 ——
    它是「同一 content version 的新代际」路径，硬要求既存 `candidate_id` + `staged_candidate`
    + 等值报告；L1 从无 representation ⇒ 走不通（门禁也印证 `R3a candidate 产不出首版`）。
    正解是两步式首版发布，详见 design §4.0。
  - 补 `workpaper_sync_entry_wp_code_adjudication.json` 的 L1 条目：`wp_codes=["L1"]`
  - 补 `registry._ALLOWED_PROVIDER_MODULES` 白名单 + provider 三个别名
    （`publish_pilot_definitions` / `attach_pilot_adapters` / `PILOT_WP_CODES`）与
    `attach_adapters` 本体
  - 修 `fix_projection_first_publication.py` 的 `--entry` 连坐缺陷
  - 两个宿主脚本的 `--check` 均跑通并记录预演结果
  - _判据：LR-P21 前置_
  - **实施证据**：
    - 新建 `backend/scripts/fix/fix_l_cycle_wp_code_adjudication.py`（正式工具，L2~L8 复用）：
      带 digest 自检（磁盘 digest 与现算不一致就拒绝继续，不顺手掩盖他人手改）+ 幂等
      + `--check` / `--apply`。落盘后条目数 **35 → 36**，
      digest `7e4c6d67…` → `c2c40b04…`，幂等复跑报「已是目标态」。
    - 🔴 **裁决依据现算（不照抄 D6）**：`wp_code=L1`「短期借款」4 项目各 1 行、file_path 是
      **真路径** `storage/projects/{pid}/workpapers/L/L1.xlsx`；而 `L1-2`「短期借款明细表」
      虽也 4 行，file_path 全是**空字符串 `''`**（非 NULL）⇒ 索引行非真底稿。
      **判据陷阱**：`count(wp.file_path)` 只排除 NULL 不排除空串，按它判会把目标码定到
      没有工作簿的索引行上 —— 本条首版即踩过，改用 `file_path <> ''` 复算后纠正。
      受管 sheet `明细表L1-2` 只是 `L1.xlsx` 里的一张 sheet，不是独立文件 ⇒ 取 `L1`。
    - `fix_projection_first_publication.py --check --entry` 预演：
      `裁决码族=['L1'] 选中=L1 wp_id=c65dc760 store=0B`，10 阶段执行 2 个后止步于
      `blocked_missing_approved_bundle`（缺 `l1.short_term_loans.authority-model` 的
      approved bundle），解除方指向 task76 脚本 —— 链路解析全部正确。
    - `fix_task76_provision_projection_definitions.py --check --entry` 预演 **EXIT=0**：
      `would_create_total=5`（authority_model / template / instrumentation / contract / bundle）、
      `reused=[]`、`errors=[]`、`representation.settlement=blocked`（符合首版预期）。
      🔴 预演算出的 contract digest `0567f010…` **与 provider 现算逐字相同** ⇒
      契约的两条单向引用判据（template/instrumentation digest 必须等于契约声明）真跑过了。
    - 守卫回归：309 test 全绿（含 contract registry 与 store registry）。

- [x] 7b. 执行两步写库
  - 第一步 `fix_task76_provision_projection_definitions.py --apply --entry xlsx/gt-l1-short-term-loans`
    —— 预演已明确：**纯新增 5 行**（4 definition + 1 bundle），逐 entry 独立事务，
    digest 幂等（重跑走 `reused` 不重建），**不碰** content_version / representation / entry_state
  - 第二步 `fix_projection_first_publication.py --apply --entry xlsx/gt-l1-short-term-loans`
    —— 走完 10 阶段（substrate_instrumented → ooxml_gate_passed → adapter_built →
    projection_composed → materialized → roundtrip_verified → unmanaged_regions_verified），
    写 `working_paper_content_version` / `working_paper_content_representation` /
    `working_paper_sync_entry_state`
  - 🔴 目标底稿 = wp_id `c65dc760`（项目 `2aa00f57`，`storage/.../workpapers/L/L1.xlsx`）
  - 🔴 判成败**一律查数据不看退出码**（脚本自身明令：`--apply` 可能被中断而部分已提交）
  - 标 `*` 的理由：写生产库属需用户确认的操作，不是外部依赖缺失
  - 断言真库 `working_paper_sync_entry_state` 出现 `xlsx/gt-l1-short-term-loans` 行、
    `working_paper_content_representation` 行数 +1（动作前后各拍快照）
  - _判据：LR-P21_
  - **实施证据（2026-10-01）**：
    - 🔴 **目标底稿与 7a 预演不同**：7a 记的是 wp `c65dc760`（项目 `2aa00f57`），本轮现算
      `wp_code=L1` 有效底稿是 wp `a028104d`（项目 `005a6f2d`，`storage/projects/.../L/L1.xlsx`）——
      脚本按 `(wp_code, created_at, id)` 确定性取第一条，库里底稿集合变了结果就变，不是脚本错。
    - 🔴 **本地 PG 出现非整库回退**：动手前三表 `entry_state / content_version / representation`
      **全为 0**（09-28 登记 12 / 267 / 274），`checklist_responses` 只剩 42 行、L 域 0 行；
      `projects` 139 / `working_paper` 997 仍在 ⇒ 不是重建库。成因未查明，只登记现象
      （`l1_adapter_facts.MEASURED_SUPPLY_2026_10_01`）。
    - 第一步 `--apply --entry …`：`created_total=5`、`reused=[]`、`errors=[]`；
      `definition_artifact` 36 → 40、`definition_bundle` 9 → 10；四段 digest 与 7a 预演**逐字相同**
      （contract `0567f010…` / bundle `5efd6233…`）。blob 落 `backend/definition_store/` 5 个文件。
    - 第二步先 `--check` 得 `ready_to_publish`、**10/10 阶段**通过，再 `--apply`：
      `revision=1`、`representation_generation=1`、`representation_id=baff7afc…`。

- [x] 7c. 发布后查数据验证（依赖 7b）
  - **实施证据**：查库（非看退出码）`working_paper_sync_entry_state` 现有
    `(xlsx/gt-l1-short-term-loans, wp a028104d, current_representation_id baff7afc…, generation 1)`；
    `content_version` 0 → 1、`representation` 0 → 1。守卫
    `TestBP611PremiseInvalidated::test_entry_state_covers_registered_entries` 钉住 L1 必须在库。
  - 原 task 7c 正文：
  - 🔴 断言真库 `working_paper_sync_entry_state` 出现 `xlsx/gt-l1-short-term-loans` 行，
    且 `current_representation_id` 非空、`representation_generation >= 1`
  - 断言 `working_paper_content_representation` 行数比动作前 +1（前后各拍一次快照）
  - 🔴 失败时不得降级为「合成 publisher」冒充通过 —— 真实失败要写出 error_code
  - _判据：LR-P21_

- [x] 8. manifest 重生成与 capability 翻转
  - **实施证据（2026-10-01）**：
    - 翻转走 **overlay `overrides` 末尾追加一条**（`GtL1ShortTermLoans.vue × GtOnlyOfficeSheet` →
      `adapter_registered` / `bidirectional` / `adapter_id=l1.short_term_loans` /
      `html_store=checklist_responses_l1_detail_rows` / resolver `workpaper_sync_published_representation`），
      与 D1/D2/D4/G7/H1 五条既有翻转同形；manifest 由生成器 `--apply` 产出，**未手改 JSON**。
    - 现算：L1 条目四字段全中；`legacy_fake_bidirectional` **136 → 135**；
      `stats` 段与 `entries` 段**逐值一致**（capability_counts 与 legacy 计数双向现算相等）——
      原文「stats 自报 137 实扫 135」的滞后在本次重生成后不复现。
    - 🔴 **原文判据两处需改口径**：①「135 → 134」是 09-28 读数；本轮前 manifest 实为 136（期间并发会话
      有 entry 进出），按「减 1」判成立。②`capability_target_blocked_by` **不是 manifest 字段**
      （manifest 无此键，它在 `workpaper_sync_l_cycle_manifest_slice.json` 里）；slice 是冻结快照、
      不随本次翻转改写，故 BP-1/2/3 的解除落在守卫
      `test_task54_l_cycle_migration.py::MIGRATED_L_ENTRIES` —— 已迁移 entry 断言 manifest 必须是真裁决，
      其余 7 条仍断言「与 overlay 默认值不一致且登记 BP-9」，**判据未放宽**。
    - 🔴 **两个使生成链跑不起来的预存阻塞，本轮修掉**：
      ① `b60/GtB60HourBudgetPanel.vue` 块注释里写了 `/rows/` + `*` + `/rowUuid`，`*/` 提前截断注释 ⇒
      该文件 `Vue AST parse failed`，discoverer 与前端构建双双炸；全仓 7475 个前端源文件同型扫描
      另 1 处命中（`find-missing-v-permission.mjs` 的 `**//*` 自行闭合，非破损）。
      ② overlay `approved_source_digest` 落后于已提交的宿主接桥工作（G 15 宿主 / g-single-region /
      K lane1）：mounts 244=244、hosts 154=154、byComponent 逐值不变、0 个 (file,component) 对数变化，
      **83 条 mountId 变更全有归因**（49 仅 ordinal 位移 + 34 ordinal 位移且门控改写），复核写进
      overlay `review_basis`。
    - 🔴 **digest 在干净 HEAD worktree 上算**：主工作树混着并发会话未提交的 I/K/N 宿主改动，
      在主树上算出的 digest 动手过程中连漂两次，提交后干净检出必 fail closed。故在
      `git worktree add --detach HEAD` 上只叠加本 spec 改动后跑生成器，再拷回生成物。
      ⇒ **主工作树上 `generate_workpaper_sync_manifest.py --check` 会因并发在途改动 fail**，
      那是对方提交时需自行重做的复核，不是本 spec 的回归。
    - 联动重生成 `workpaper_sync_legacy_baseline.json`（+ 前端 `.generated.ts`），否则
      `check_workpaper_sync_closure.py` 报 `legacy characterization is stale`。
  - 用 manifest 生成器重生成 `backend/data/workpaper_sync_entry_manifest.json`
    （先现算确认生成器入口与 `source_digest` fail-closed 机制，禁手改 JSON）
  - 🔴 断言 L1 条目现算得 `migration_state == "adapter_registered"` /
    `capability == "bidirectional"` / `adapter_id == "l1.short_term_loans"` /
    `html_store == "checklist_responses_l1_detail_rows"`（或生成器真实产出值，现算为准）
  - 断言 `legacy_fake_bidirectional` 总数从 **135** 减 1 变 **134**
  - 断言 `stats` 段与 `entries` 段一致（本轮已发现 stats 滞后：自报 137 而实扫 135 ⇒
    若生成器未同步 stats，登记为缺陷并修）
  - 断言 L1 的 `capability_target_blocked_by` 里 BP-1/BP-2/BP-3 已移除，
    且移除逐条有理由；其余 BP（BP-5/BP-7/BP-9/BP-10）保留或移除也逐条给理由
  - _判据：LR-P22_

## 阶段 5：零回归与真栈 roundtrip

- [x] 9. 零回归门
  - 相关子集全绿：`test_l1_*`（60）+ contract registry + store registry + 框架层等效性
    + 被改写的 2 条既有守卫 = **367 + 60 passed**
  - 前端 `npx vitest --run` 全量 **2110 passed / 15 failed**，失败的 7 个文件对 L1 模块
    引用现算**全为 0**（逐文件 grep 证明）⇒ 既有失败
  - `npx tsc --noEmit`：L1 **零错误**（21 个既有错误全在 G 循环 4 个语法破损文件）
  - `npx eslint` 对本轮 3 个前端文件：**零问题**
  - 29 个 `generate_phase5_*.py --check` 全过 ⇒ 51 份既有契约 digest 零漂移
  - 🔴 **golden digest 基线裁决（与原计划不同，给理由）**：原计划要「新增 l1 条目」，
    实测后改为**不加**并如实登记该基线已整体过期 ——
    `test_f2_p11_golden_digest_zero_regression.py::GOLDEN_BASELINE` 的语义是
    「**既有**契约文件在 F2 开发期间不得被改动」，l1 是本轮新增、不属「既有」；
    且该基线现已 **9 条红全属既有欠账**，把 l1 塞进去只会让过期基线更难辨。
    l1 自身的零回归由本 spec 守卫 `test_disk_and_source_are_byte_locked` 承担。
  - _判据：LR-P23_
  - **实施证据 / 既有欠账登记**：
    - `test_f2_p11_golden_digest_zero_regression.py` **6 条红**（d1/d3/d5/d6/d7/f1）：
      🔴 逐条证明与本轮无关 —— `git diff HEAD -- workpaper_sync_contracts/` **为空**
      （契约文件与 HEAD 逐字节一致），而 HEAD 版 d1 的 `sha256(file_bytes)` 现算
      `fc07076624a76e12` ≠ 基线写死的 `62b589551bd99050`。时序：d1 契约在 **09-27** 被
      commit `3c10c0279`（"修复 11 条预存/并发红…d1 契约…"）改过，而基线文件在 **09-28**
      的 commit `8d7a52059` 里只同步了 **b60 一项**，其余 6 项没跟上。
    - `test_check_sync_provider_golden_digest.py` **3 条红**：`labels` 断言写死 9 个
      （b60/d1~d7/e1）而 G/H/I/J 全域交付后早已远超；`digest_count` 139 vs 142；
      drift 列表是 **b60 的 sheet digest 漂移 + g4/g5/g6 缺基线**，**无 l1**。
    - ⇒ 两处基线都需由其 owner 按现算重刷，本 spec 不代改（改了等于替 F2/G 的 spec
      宣布它们的零回归基线换了口径）。

- [x] 10. 真 OO 9.4 roundtrip
  - **实施证据（2026-10-01）**：`backend/scripts/e2e/verify_l1_oo94_roundtrip.py` **EXIT 0**，
    全链生产代码无合成替身：生产 `attach_adapters` → 真 representation substrate（gen 1）→
    2 行 HTML 载荷 → materialize → **docker `audit-onlyoffice` 的 `ConvertService.ashx` xlsx→xlsx
    真引擎重存**（容器经 `host.docker.internal` 拉临时 HTTP 文件）→ extract → G1 等值门 →
    merge 回 store。
    - `L1-2-rows` 往返**逐字段相等**（2 行 × 24 键，rowId 稳定）；合并回 store 恰 2 行 ⇒
      substrate 里模板 R10~R25 的 16 条预印行（只有序号）被 ghost-row 锚点挡住，未成幽灵行
    - OO 重存后受管行 K/R/S/T/U **10 格全部仍是公式**（formula_mask 真生效）
    - `审定表L1-1` R7~R11×B..L 55 格：**OO 引擎改写 0 格**；materialize 中性化裸 IF 5 格
      （K7~K11 变动率公式 → 常量，task 6 有意挂的 per-file OO 崩溃中性化，GC-2 平台策略）
    - 真库 `L1-adj-*` 32 行快照 digest 前后不变（本脚本不写库）
  - 🔴 **如实登记两点**：①验证用 ConvertService（OO 自己的电子表格引擎解析+重写 OOXML），
    不是浏览器里人工编辑后 forcesave —— 能证「OO 不改坏受管区/公式/隐藏 UUID 列」，
    不能证「用户在 OO 里改值后回流」；后者需 Playwright 真浏览器，与 lane spec 的 `[ ]*` 端到端同属一件事。
    ②中性化让 OO 视图里 `审定表L1-1` K 列变动率**失去公式联动**（显示为常量），这是平台级取舍，
    不是 L1 的缺陷，但用户在 OO 里看到的变动率不随明细变化，需知情。
  - 原 task 10 正文：
  - 用 docker `audit-onlyoffice`（实测 healthy）跑 HTML→OO→HTML
  - 断言受管表往返后 `L1-2-rows` 载荷逐字节不变；断言 K/R/S/T/U 五列公式**往返后仍是公式**
    （不被值替换 —— 这是 formula_mask 真生效的唯一硬证据）
  - 断言 `审定表L1-1` 的 R7~R11 往返后一格未变（只读投影不被写坏）
  - 断言 `L1-adj-*` 33 行真库载荷往返后不变（本 spec 不动审定表数据）
  - 🔴 跑不通不得标 `[ ]*` 了事，要写出具体 error_code 与失败环节
  - _判据：LR-P24_

## 阶段 6：L2~L8 推进（L1 闭环后开工）

- [ ] 11. 抽 `phase5_l_cycle_common.py`
  - 🔴 L 域出现第二条 entry 时**必须先抽共性基类**，对标既有 `phase5_h_cycle_common.py`
    的 `instrumentation_specs_for(IDENTITY, specs)` / `template_definition_payload(identity, specs)`
  - 禁 8 份 provider 各复制一遍；L1 落成后回迁到基类，回迁前后 contract payload 逐字节不变
  - _判据：LR-P11 邻域_

- [ ] 12. L4 → L3 → L2 逐条接线
  - 顺序依据：L4 已有 candidate contract（起点最高）；L3 与 L1 模板层+代码层双重同构
    （LC-25，改一不改二 = 半修 ⇒ 必须交叉引用 L1 的 contract 改动）；L2 有 8 行真库载荷
  - 🔴 每条 entry 的受管表选型**重做 §2.1 那套裁决**，禁假设「都选明细表」——
    L2 是应付利息（8 sheet）、L4 是应付债券（16 sheet），几何与 L1 不同
  - 🔴 L2 的既知污染：其载荷落在 `wp_code='G8'`（LC-22 跨 entry 污染，L/N 两轮连续漏检）⇒
    接线前先确认归属，禁把 G8 的行当 L2 的
  - 每条独立 commit，manifest 逐条翻转，禁批量翻转后统一验证
  - _判据：LR-P22 逐条复用_

- [ ] 13.* L5~L8 接线（前置：先修 inert 开关）
  - 🔴 L5~L8 的 `ui_toolbar_gate.anchor is None`（连宿主锚点都没有）+ BP-4 模式开关 inert
    （切到 OnlyOffice 不渲染任何 OO 宿主）⇒ **必须先补锚点与开关**，否则 DOM 判据无对象
  - 标 `*` 的理由：开关修复属前端宿主改造，与本 spec 的 adapter 注册主线可分离，
    且需真实浏览器验证（Playwright）；不标 `*` 的部分（contract/provider）照常推进
  - _判据：LR-P22 逐条复用_

## 阶段 7：收尾

- [ ] 14. 清理与登记
  - 删除本 spec 期间产生的 `_` 前缀一次性探针
  - 在 `.kiro/specs/INDEX.md` 登记本 spec（现扫 `.kiro/specs/*/tasks.md` 重算 Active 数，
    禁按增量推算）
  - 🔴 把「前序三份 L spec 标 100% 但 manifest 未翻」这一结构性问题写进复盘，
    并登记同类待查：G/I/J/C 四轮同样标完成而 manifest 未翻，需同法复核
  - 移交登记：`审定表L1-1` 的 `L1-adj-*` 33 行载荷归「审定表引擎」统一处置，本 spec 未动
  - _判据：全判据闭合性自检 —— 断言 LR-P1~LR-P24 每条至少被一个任务引用_
