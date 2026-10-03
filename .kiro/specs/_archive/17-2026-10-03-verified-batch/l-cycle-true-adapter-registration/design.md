# L 循环真双向改线（adapter 注册）— 设计

## 一、前序 spec 的三处前提已失效（本轮现算推翻，逐条给证据）

三份已归档/已完成的 L spec 一律不回填修改，勘误登记在此。

### 1.1 BP-61-1「三表近空，186 个 planned entry 一个都注册不上」❌ 已失效

| 表 | spec 前提 | 2026-09-28 真库现算 |
|---|---|---|
| `working_paper_sync_entry_state` | 近空 | **12 行 / 11 个不同 entry_id** |
| `working_paper_content_version` | 近空 | **267 行** |
| `working_paper_content_representation` | 近空 | **274 行** |

`entry_state` 覆盖 `b60` / `d1` / `d2` / `d3` / `d4`（generation 164）/ `d5` / `d6` / `d7` /
`g7`（gen 6）/ `h1`（2 个 wp）+ 1 条 opaque。

🔴 **解除证据的正确表述**：不是「三表非空」而是「**11 个 entry 已真实跑通五环发布链**」。
三表非空只证明链路跑过；真正推翻「一个都注册不上」的是 entry 级覆盖面。
🔴 **并非全部解除**：D3/D5/D6/D7 有 published representation 却仍标
`legacy_fake_bidirectional` ⇒ 剩余差距在「manifest 重生成 + capability 裁决」这个
治理动作，不在平台供给。本 spec 对 L 域自带该动作，不等待他人裁决。

### 1.2 「L3/L4/L5 全 NULL、L6/L7/L8 真库 0 行」❌ 已失效

真库 `checklist_responses` 按 `item_id ~ '^L[0-9]'` 现算（NULL 与空串分开计）：

| 域 | 行数 | `remark` 非空 | `conclusion` 非空 |
|---|---|---|---|
| L1 | 33 | **33** | 0 |
| L2 | 8 | **8** | 0 |
| L3 | 11 | **7** | 0 |
| L4 | 6 | **6** | 0 |
| L5 | 7 | **7** | 0 |
| L6 | 5 | **5** | 0 |
| L7 | 5 | **5** | 0 |
| L8 | 5 | **5** | 0 |

⇒ L2~L8 **全部有真实载荷**。前序 spec 的「L1 是唯一合格 canary」结论建立在已失效前提上。
`conclusion` 全域 0 这一条**仍成立**（与前序一致，沿用）。

### 1.3 `l1.short_term_loans.candidate.json` 的 field_mapping ❌ 两处实质错误

**错误 A —— 字段名与真库键名不匹配**：

| candidate 声明 | 真库实际 item_id 字段段 |
|---|---|
| `beginUnadjusted` / `beginAje` / `beginRje` / `beginAudited` | `beginning` / `unadjusted` / `aje` / `rje` / `audited` |
| `endUnadjusted` / `endAje` / `endRje` / `endAudited` | `debitAmount` / `creditAmount` / `endBalance` |

真库 33 行 = 4 分类 × **8 字段**（`aje` `audited` `beginning` `creditAmount`
`debitAmount` `endBalance` `rje` `unadjusted`）+ `L1-chk-conclusion` 1 行。
HTML 侧是「期初 + 本期借贷发生额 → 期末」口径，模板侧是「期初四栏 + 期末四栏」口径，
**两侧语义不同构**，不能逐格映射。

**错误 B —— 把公式格声明成可写 number 字段**：

`审定表L1-1` 实测 R7~R11 无一个可输入格：

```
B7 = SUMIF('明细表L1-2'!$B:$B,'审定表L1-1'!$A7,'明细表L1-2'!$H:$H)   ← candidate 声明为可写
E7 = =B7+C7+D7            I7 = =F7+G7+H7        J7 = =F7-B7
K7 = =IF(AND(B7=0,J7=0),0,IF(AND(B7=0,J7>0),1,J7/B7))   ← 裸 IF
R11 合计 = =SUM(B7:B10) …
```

⇒ 按 candidate 接线会把 SUMIF 写掉，**破坏整册取数联动**。

## 二、canary 改选：`审定表L1-1` → `明细表L1-2`

### 2.1 裁决依据

| 维度 | 审定表L1-1（前序选择） | 明细表L1-2（本 spec 选择） |
|---|---|---|
| 可输入格 | **0**（R7~R11 全公式） | 19 个可输入列 |
| 形态 | 固定 4 行分类派生表 | 动态行表（标准范式） |
| 数据方向 | 由明细表 SUMIF 汇总而来 | **数据源头** |
| 裸 IF | **34 格** | 0 格 |
| 与既有样板同构 | 无对应范式 | 与 `d6` 几乎逐项同构 |
| 真库载荷 | 33 行 | 0 行 |

🔴 **真库零载荷不是阻碍**：`phase5_d6_contract_assets.py` 的 `_REVIEWED_BASIS` 原文记着
「载荷落点：D6-2-rows 全库 0 行同 H1/D3 空表单」—— D6/H1/D3 三条都是空表单，
却都已是 reviewed contract + registry 注册 + published representation。
⇒ 「真库有载荷」是**选 canary 时的加分项**，不是 contract 交付的前置。

🔴 `审定表L1-1` 不被丢弃，改为 **formula_mask 全覆盖的只读投影**：R7~R11 一格不写。
其 `L1-adj-*` 33 行载荷属 HTML 侧既有数据，本 spec 不动它，留待「审定表引擎」统一处置
（与 H5/H7 的缺口登记结论同向：明细表前端字段不补，正解指向审定表引擎）。

### 2.2 `明细表L1-2` 实测几何（provider 常量真源，禁写死于别处）

```
sheet          明细表L1-2            dims A1:AD49   max_row 49   max_col 30
表头           R8（组标题）+ R9（叶子）        header_rows = 2
数据区         R10 ~ R25
footer/合计    R26 —— 标签在 **C26 = `合计`**（🔴 不在 A 列，A26 为空）；D/E/F 占位 `——`
               H26~U26 **连续 14 列全是 `=SUM(X10:X25)`**（含 K/R/S/T/U）
有效列         A..AB
公式列         K(=H+I-J) · R(=H+L+M) · S(=I+N+P) · T(=J+O+Q) · U(=R+S-T)
可输入列       A 序号 · B 借款种类 · C 贷款单位 · D 起始日期 · E 讫止日期 · F 年利率
               G 固定/浮动 · H 未审期初 · I 本期增加 · J 本期减少 · L/M 期初调整
               N/O 账项调整增减 · P/Q 重分类调整增减 · V 借款用途 · W 保证人/抵押物
               X 借款合同索引 · Y 是否逾期 · Z 询证函索引 · AA 与征信报告核对 · AB 备注
合并单元格     R8/R9 叶子组 14 处 + 标题区
```

🔴 上表每个数字在 provider 落成时必须由 openpyxl 现算断言，不得只写在注释里。

### 2.3 首版判据的两处自纠（实测打红后改正，留痕）

| 项 | 首版写法 | 实测真值 | 根因 |
|---|---|---|---|
| footer SUM 列 | H/I/J/L/M/N/O/P/Q **9 列** | **H..U 连续 14 列**（含 K/R/S/T/U） | 我读探针输出时把 `rows={fx[:12]}` 的**截断列表**当成完整集合，于是以为 K/R/S/T/U 不含 R26 |
| footer 标签 | 按 d6 假定在 A 列 | 在 **C26**，文本 `合计`（无 d6 的 3 半角空格） | 照抄样板的 marker 列 |

⇒ 两条教训已落成守卫：① 计数类判据必须取完整现算结果，截断输出不可当全集
② 「合计」标签定位**不限 A 列**（N 轮有一处在 B 列，L1 这处在 C 列），
按 A 列找 marker 会得空并误判「无 footer」。
另现算确认 **K 列在 R3/R4 页眉区也有公式**（`=底稿目录!...`）⇒ 公式列扫描必须限定数据区，
否则 `formula_mask` 跨度会从 R10 错扩到 R3。

## 2.4 HTML 侧现状：两侧字段不同构 + 位置化行身份（本轮新发现）

前端真源 `audit-platform/frontend/src/composables/useL1Detail.ts` +
`useL1FormData.ts`（`DetailRow` 定义在后者）。

### 2.4.1 `DetailRow` 只有 14 字段，模板有 28 列

```
bank · contractNo · loanType · amount · rate · startDate · endDate · purpose
guarantee · beginning · creditAmount · debitAmount · endBalance · currency
```

| 状况 | 明细 |
|---|---|
| 两侧都有（12） | bank↔C · contractNo↔X · loanType↔B · rate↔F · startDate↔D · endDate↔E · purpose↔V · guarantee↔W · beginning↔H · creditAmount↔I · debitAmount↔J · endBalance↔K |
| **模板有、前端缺（16）** | G 固定/浮动 · L/M 期初调整 · N/O 账项调整 · P/Q 重分类调整 · **R/S/T/U 审定数四列** · Y 是否逾期 · Z 询证函 · AA 征信核对 · AB 备注 |
| **前端有、模板无（2）** | `amount`（借款金额）· `currency`（币种） |

🔴 `endBalance` 两侧语义**一致**：前端 `calcLiabilityEndBalance(beginning, creditAmount,
debitAmount)`（负债口径 期初+贷方-借方）== 模板 `K=H+I-J`（期初+本期增加-本期减少）。
⇒ 增加=贷方、减少=借方，可映射，不是缺陷。

### 2.4.2 行身份是位置化的，contract schema 明令禁止

前端现状：`item_id = L1-det-{rowIndex + 1}-{field}`，`removeRow()` 之后
`_triggerSaveAll()` 重建整个序列 ⇒ 删中间行会让后续行 item_id 全部错位。

而 `workpaper_sync_contracts/README.md` 硬约束：`row_identity.kind` 只能
`field` / `template_row_key`，**`index` / `ordinal` / `position` / `row_number` /
`array_index` 一律拒绝** ⇒ 位置化形态**根本过不了契约校验**，必须先改。

### 2.4.3 改造面裁定：只改 `det`，不动通用函数

`_parseDynamicRows` / `_serializeRows` 是 L1 内部通用函数，被 **5 个表**共用：

| prefix | 表 | 本 spec 处置 |
|---|---|---|
| `det` | 明细表L1-2 | **改**：切 d6 式单条 rows item + 稳定 `rowId` |
| `int` | 利息测算表L1-5 | 不动 —— 🔴 被 `h2L1LoanPull.ts` 跨循环消费（`L1-int-{n}-{field}`），改它会连带 H2 |
| `cred` | 征信报告核对表L1-4 | 不动 |
| `ovd` | 逾期贷款检查表L1-7 | 不动 |
| `plg` | 抵质押资产检查表L1-8 | 不动 |

⇒ 只给 `det` 新增一条 d6 同形态通道（单条 item `L1-2-rows`，整行数组 JSON，
行身份用稳定 `rowId`），**通用函数与其余 4 表一行不改**。

🔴 **切换零迁移负担**：真库 `L1-det-*` 现算 **0 行 / 0 distinct item**（已实测）⇒
直接切新形态，无历史数据要搬。其余 4 表的位置化缺陷**登记为后续**，不在本 spec。

### 2.4.4 契约以模板列为权威

契约映射**模板全 28 列**（A..AB），前端 `DetailRow` 扩展到对齐；
`amount` / `currency` 模板无对应 ⇒ 保留为 HTML-only 字段，**不入契约**并在契约里登记原因。

理由：模板是致同标准底稿（权威源），前端缺的 16 列全是真实审计字段
（尤其 R/S/T/U 审定数四列 —— 缺了审定数，明细表就无法支撑 `审定表L1-1` 的 SUMIF 取数）。

## 三、复制样板逐项对照（`d6` → `l1`）

`phase5_d6_contract_assets.py` 是最贴近的样板，L1 按它同构落成。

| 结构 | d6 | l1（本 spec） |
|---|---|---|
| 受管 sheet | `明细表D6-2` | `明细表L1-2` |
| 两级表头 | R12 组 / R13 叶子 | **R8 组 / R9 叶子** |
| 数据区 | R14~R25 | **R10~R25** |
| footer | R26 / 标签 A 列「合   计」（3 半角空格） | **R26 / 标签 C26 `合计`**（实测，不在 A 列） |
| footer 公式 | 部分列 SUM | **H..U 全 14 列 SUM** |
| 公式列 | J / Q / T | **K / R / S / T / U** |
| 有效列 | A..AF（32 列） | **A..AB** |
| store 形态 | 整表存一条 item 的 `remark`（JSON 数组字符串） | 同形态，键名待定见 §4.2 |
| 账龄分层 | FLAT top-level 键 | L1 无账龄，不适用 |

必须实现的 provider 接口（`d6` 现有全集，注册路径真实读取）：

```
excel_carrier_gate()                     authoritative_template_path() / read_authoritative_template()
assert_no_implicit_template_fallback()   assert_entry_selectable()
instrumentation_spec() 或 instrumentation_specs()（复数，多 sheet 时必须复数）
template_definition_payload()            instrumentation_definition_payload()
authority_model_payload()                stable_key_for() / _rows_table_payload()
build_contract_payload()                 contract_file_path() / load_contract_from_disk()
assert_contract_file_matches_source()    build_store_projection() / merge_projection_into_store_rows()
publish_definitions(publisher)           build_matcher() / build_registration() / register_adapter()
resolve_published_frozen_definitions()   attach_adapters()
manifest_capability_enabled() / assert_manifest_capability_enabled()
```

🔴 **contract JSON 是代码生成物**，不是手写：`build_contract_payload()` 产出 payload，
`assert_contract_file_matches_source()` 把磁盘文件与代码双向锁死。
⇒ 生成器落 `backend/scripts/gen/generate_phase5_l_contracts.py`（多 entry 合一，
对标既有 `generate_phase5_h_contracts.py` / `i_contracts.py` / `j_contracts.py`，
不为每条 entry 建单独脚本）。

## 四、五环落地

```
① template        → template_definition_payload()  得 template_definition_sha256
② instrumentation → instrumentation_definition_payload()  得 instrumentation_definition_sha256
③ contract        → build_contract_payload() review_status=reviewed → 落盘 l1.short_term_loans.json
④ definition bundle → publish_definitions(publisher)  得 approved projection bundle
⑤ representation  → 首版发布（**不是** finalize_candidate）
```

### 4.0 🔴 ④⑤ 两环的真实入口（首版设计写错，2026-09-28 实测纠正）

**首版设计写的 `excel_entry_gate.finalize_candidate(...)` 是错的入口**。现读其签名后确认：
它是「**同一 content version 的新代际**」路径，硬要求 `candidate_id` + `staged_candidate` +
`frozen_bundle_sha256` + `equivalence_report_bytes`（且报告里的 `instrumented_sha256` 必须等于
staged 字节 digest）+ 已装配 `MaterializeCoordinator`。L1 从无 representation ⇒ 无 candidate
可用，这条路走不通。门禁脚本也印证：`R3a candidate 产不出首版:
source_representation_id is_nullable=NO fk=True`。

正确入口是**两步式首版发布**，各带 `--check` 只读模式与 `--entry` 单条过滤：

| 步 | 脚本 | 写什么 |
|---|---|---|
| ④ | `backend/scripts/fix/fix_task76_provision_projection_definitions.py` | 4 条 definition + 1 条 bundle |
| ⑤ | `backend/scripts/fix/fix_projection_first_publication.py` | content_version / representation / entry_state |

`--check` **不是「跑一遍再回滚」**：④ 用 `DryRunPublisher`（payload 真、digest 真算、库查真查，
只是不 insert），因为 `publish_definition_blob()` 一旦调用就会往 definition store 写 blob，
回滚也留 orphan 文件。

### 4.0.1 三张登记表 + 一处宿主缺陷（都是 ④ 的硬前置，实测逐个踩出来）

| 前置 | 缺了会怎样 |
|---|---|
| `workpaper_sync_entry_wp_code_adjudication.json` | `_adjudicated_wp_codes()` fail-closed 抛 `ProjectionTargetResolutionError`；回落启发式产的正是幻影码 `L1S` |
| `DELIVERED_PER_ENTRY_CONTRACTS`（交付登记表） | `test_contract_directory_matches_the_delivery_ledger` 红 |
| `registry._ALLOWED_PROVIDER_MODULES`（白名单） | `HostError: provider_module 不在 registry 白名单内`；判据 `len(白名单) == len(台账)` |
| provider 的 `publish_pilot_definitions` / `attach_pilot_adapters` / `PILOT_WP_CODES` 三个别名 | `ProviderModuleNotAllowedError: provider 是空壳` —— provisioning 只认别名，不认 `publish_definitions` |

🔴 **宿主缺陷（已修）**：`fix_projection_first_publication.py` 的 `--entry` 过滤原先只在
`run_check` / `run_apply` 里**事后 filter**，而 `_build_plan_rows()` 在建计划时就对**每条**
entry 调 fail-closed 的 `_adjudicated_wp_codes()` ⇒ `--entry l1` 会被**另一条无关 entry**
（实测 `xlsx/gt-e1-monetary-fund` 在交付登记表里但不在裁决表里）连坐，连只读预演都跑不起来。
已把过滤前移进 `_build_plan_rows(only_entry=...)`，语义等价。
**E1 的裁决缺口属其自己的 spec，本 spec 不代做裁决，如实登记。**

### 4.1 contract 硬约束（README 原文，逐条落断言）

- payload **单向**引用已发布的 `template_definition_sha256` / `instrumentation_definition_sha256`
- 禁 `bundle_*` / `definition_bundle_*` 前向引用；禁内嵌自身 artifact UUID/hash
- 模板哈希字段名必须写 `template_sha256` 与 `normalized_structure_hash`
  （**不是** `sha256` / `structure_hash` —— `definitions._SELF_REFERENCE_KEYS` 会递归拒绝裸键）
- `identity_carriers` 只用 `hidden_uuid_column`（+ 可选 `defined_name`）；
  🔴 L1 册 definedName 现算 **0 / broken 0** ⇒ 若用 `defined_name` 需新增，倾向只用隐藏 UUID 列
- sheet 定位锚点禁 `sheet_id` / `sheet_display_name`（OO 9.4 实测 failed）
- 字段级：`stable_field_key` / `json_pointer` / `mode` / `value_type` / `source_ref` / `cell` 六件齐
- `row_identity.kind = field`，`json_pointer` 含恰好一个 `{row_uuid}`，`cell.row_from = row_identity`
- 声明 `row_identity` 必同时声明 `delete_policy`（取 `tombstone`，同 d6）
- `footer_anchor` 用 `marker` + `search_column`，禁行号
- `mode=formula` 的字段其列必须落在 `formula_mask` 覆盖内 ⇒ K/R/S/T/U 必须进 mask
- `header_rows = 2`
- 禁 `^col_[a-z]+$` 形态的无语义列占位

### 4.2 store 通道

L1 的 HTML 侧持久化走 `checklist_responses`。明细表当前真库零载荷 ⇒ store item id
由本 spec 新建，命名对齐既有范式（`D6-2-rows` / `D5-2-rows` / `F3-5-rows`）：

```
store_item_id = "L1-2-rows"      kind = StoreKind.rows
```

🔴 新键不得与既有 `L1-adj-*`（审定表，32 行）/ `L1-chk-conclusion` 撞名 —— 现算确认前缀
`L1-2-` 在真库命中 **0**，是干净命名空间。
🔴 `STORE_MERGE_REGISTRY` 只登记本轮真受管的这一条 item，禁预登记其余 12 张 sheet 的键
（会让 `check_sheet_specs_fully_registered` 的分母失真）。

### 4.3 OO 崩溃中性化

L1 册裸 IF 现算 **112 格**（`审定表L1-1` 34 · `附注披露信息核对（上市公司）` 28 ·
`附注披露信息核对（国企）` 20 · `利息测算表L1-5` 22 · `逾期贷款检查表L1-7` 8；
**受管表 `明细表L1-2` 零命中**）。

按 GC-2 的 per-file 保守策略：受管表干净也必须挂中性化，因为同册其他 sheet 需要它。

```
StoreMergePlan(..., oo_crash_neutralization_fn="neutralize_oo_crash_if_formulas")
```

🔴 与 G7/G2/G9/G10/G8/H9/H6/H4/H8 **共用同一个函数**，禁新造；
禁在 `adapters/excel.py` 加 `if adapter_id == "l1…"` 字面量分支
（会打红 `test_excel_adapter_has_no_adapter_id_literal_branch` 与 P9 框架层零 wp_code 分支判据）。

## 五、判据清单（LR-P1 ~ LR-P24）

| ID | 判据 | 承载 |
|---|---|---|
| LR-P1 | 三表行数现算 ≥ 本文 §1.1 登记值，且 `entry_state` 覆盖 ≥ 11 entry | task 1 |
| LR-P2 | BP-61-1 裁决结论落成断言，理由是 entry 覆盖面非「表非空」 | task 1 |
| LR-P3 | L2~L8 真库 remark 非空数逐域现算，等于 §1.2 表 | task 1 |
| LR-P4 | `conclusion` 全域 0 仍成立（沿用前序结论，配变异证明） | task 1 |
| LR-P5 | candidate contract 字段名与真库键名不匹配 —— 8 个真键逐个现算 | task 2 |
| LR-P6 | `审定表L1-1` R7~R11 可输入格数 == **0**（逐格判 `str.startswith("=")`） | task 2 |
| LR-P7 | `明细表L1-2` 几何八项逐项现算等于 §2.2 | task 3 |
| LR-P8 | 公式列恰 K/R/S/T/U 五列，且各列公式行区间等于实测 | task 3 |
| LR-P9 | 受管表裸 IF == 0；整册 == 112，逐 sheet 分布等于 §4.3 | task 3 |
| LR-P10 | definedName == 0 且 broken == 0（空分母，配人造正样本变异） | task 3 |
| LR-P11 | provider 接口全集齐备，逐个 `callable` 断言 | task 4 |
| LR-P12 | `build_contract_payload()` 产出通过 `contracts.py::parse_contract` | task 5 |
| LR-P13 | 磁盘 contract 与代码 payload 逐字节相等（`assert_contract_file_matches_source`） | task 5 |
| LR-P14 | contract `review_status == reviewed` 且文件名无 `.candidate` 中缀 | task 5 |
| LR-P15 | `review.entry_id == "xlsx/gt-l1-short-term-loans"`（不再是 null） | task 5 |
| LR-P16 | 既有守卫 `test_no_pilot_contract_belongs_to_the_l_cycle` 已改为具名期望而非零期望 | task 5 |
| LR-P17 | `formula_mask` 覆盖 K/R/S/T/U，且 `mode=formula` 字段列 ⊆ mask | task 5 |
| LR-P18 | store item `L1-2-rows` 在真库前缀命中 0（干净命名空间） | task 6 |
| LR-P19 | `STORE_MERGE_REGISTRY["l1.short_term_loans"]` 存在且 item 恰 1 条 | task 6 |
| LR-P20 | `adapters/excel.py` 无 `l1` 字面量分支；中性化函数对象与 G7 解析结果**同一个** | task 6 |
| LR-P21 | 五环走完后 `working_paper_sync_entry_state` 出现 L1 行 | task 7 |
| LR-P22 | manifest 现算 `migration_state=adapter_registered` / `capability=bidirectional` / `adapter_id=l1.short_term_loans` | task 8 |
| LR-P23 | golden digest 基线含新增 contract，零回归 | task 9 |
| LR-P24 | roundtrip HTML→OO→HTML 值等价（真 OO 9.4，非合成） | task 10 |

## 六、风险与隔离

| 风险 | 处置 |
|---|---|
| 并发会话在 `work/2026-09-27-k-lane1-template-orphan-keys` 改 K lane1 与 A 类组件 | `store_item_registry.py` 只**追加**一个 dict 条目，不重排、不改既有注释 |
| contract 改名打红既有 L 守卫 | 同步把期望从「L 域零 contract」改为「恰 1 条且具名」，禁删断言 |
| golden digest 基线变动 | 按既有基线更新方式同步，禁跳过 |
| 审定表 33 行载荷 | 本 spec 不动，登记移交「审定表引擎」 |
| 真 OO evidence 跑不通 | 如实标 `[ ]*` 并写卡点，禁合成测试冒充真栈 |
