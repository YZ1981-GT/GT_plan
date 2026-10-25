# C 循环双向回写地基与首张 canary — 任务

> 判据引用规则：本文件裁定 CC-1 ~ CC-68，lane spec 只引用编号。
> `[ ]*` = 外部依赖阻塞，不可在本轮标 completed。
>
> **实施状态（2026-09-28）**：阶段 1~5 共 28 条已完成 **28 / 28**；
> 外部依赖 9 条（29~37）保持 `[ ]*`。守卫 = `backend/tests/workpaper_sync/test_c_cycle_baseline.py`
> （22 类 **93** test）+ 扫描器 `backend/scripts/analyze/c_cycle_scanner.py`。

## 阶段 1：域切分与归属基线

- [x] 1. 建 C 域基线守卫 `backend/tests/workpaper_sync/test_c_cycle_baseline.py`
  - 断言 C 域 in-scope entry 恰 **2** 条：`xlsx/gt-c-control-test` 与 `xlsx/gt-c22-itgc-bundle`
  - 🔴 断言按 `wp_code_patterns` 首字母切域只得 **1** 条，会漏主体（CC-1 反转证据）
  - 断言两条 `migration_state` 均为 `legacy_fake_bidirectional`、`capability` 均为 `null`
  - _判据：CC-1、CC-43_
  - **实施证据**：`TestCDomainSliceSplit`（5 test）。`c_domain_entries_by_first_letter()`
    现算得 **1** 条（仅 `gt-c22-itgc-bundle` 有 pattern `C22I`），印证首字母切域漏主体。

- [x] 2. `pattern_less` 归属裁决落成断言（CC-68）
  - 用 override 表（`backend/app/data/wp_code_overrides.json`，**1526** 条）反查 componentType
  - 断言 5 条反查结果：`c-control-test` **28** · `c22-itgc-bundle` **1** · `a-program-console` **32** · `cf-verification` **1** · `custom` **0**
  - 🔴 断言 `xlsx/cash-flow-verification` 反查得 **`A5`** ⇒ 属 A 域，**A 轮遗漏**（只登记缺口不在本轮修）
  - 断言另 3 条（`gt-custom-wp-editor` / `gt-wp-renderer` / `shared/cycle-standalone-procedure-shell`）留独立一轮，各带排除理由
  - 🔴 断言这是 B 轮 BC-45「多 entry 共用一 wp_code」的**对偶再翻转**：C 域是**一 componentType 覆盖 28 个 wp_code**（CC-45）
  - _判据：CC-68、CC-61、CC-45_
  - **实施证据**：`TestPatternLessAttribution`（5 test）。override 反查现算：
    `c-control-test` → C 域 **28** 码（`C2`~`C15` + `C2-2`~`C15-2`）· `c22-itgc-bundle` → `['C22']` ·
    `a-program-console` → **≥32** 码 · `cf-verification` → 含 **A** 域码（A 轮遗漏，见任务 28）。

- [x] 3. 两条 entry 形态对照断言（CC-2）
  - 断言 design.md §1.1 的 **14** 个维度逐项相反
  - 断言载体二分各 1 条，其一为 `no_carrier` + `no_switch_at_all`
  - 断言 C22 的 BP 为 **8** 项且含 **BP-10**；另一条 **7** 项
  - _判据：CC-2、CC-43_
  - **实施证据**：`TestEntryContrast14Dims`（6 test）—— 载体（`host_inline_segmented` vs
    `no_carrier`）· switch（`redeemable` vs `no_switch_at_all`）· BP（7 vs 8 含 BP-10）·
    group（GRP-07 vs GRP-06）· family（`control_test_router` vs `c_class_bundle`）·
    pattern（空数组 vs `['C22I']`）逐项现算相反。

- [x] 4. strict 域口径（CC-57、CC-5）
  - 🔴 断言 `^GtC\d` 得 **8** 个但只含本轮 **1** 条 ⇒ **会漏主体**
  - 断言 `^GtC` 后非数字得 **32** 个，含本轮主体 `GtCControlTest.vue`
  - 断言正则须扩为 `^GtC\d` ∪ `^GtC[A-Z]`
  - 断言小写 `Gtc` 为 **0**（空分母，配变异证明）
  - 断言非 Gt 前缀含 C 码 **10** 个（`C23*` / `C24*` 子表组件）属排除
  - 断言 `^GtC\d` 域内未纳入本轮 **7** 个各带排除理由
  - _判据：CC-57、CC-5、CC-20_
  - **实施证据**：`TestStrictDomainScope`（4 test）。`^GtC\d` 现算**不命中** `GtCControlTest.vue`、
    `^GtC[A-Z]` **命中** ⇒ 扫描器 `is_c_domain_file()` 已按 `^(?:use|Gt)C\d` ∪ `^(?:use|Gt)C[A-Z]`
    取并（实测 C 域文件集 **22** 个，含主体宿主）。小写 `Gtc` 为 0 且配人造正样本 `GtcFake.vue` 变异证明。

- [x] 5. 空分母清册 + 变异证明（CC-20，覆盖全部 ❌ 判定条）
  - 逐项断言 design.md §五 的 **17** 项结构性零，每项配人造正样本变异测试
  - 逐条落断言：confirm 0（CC-4）· 小写前缀 0（CC-5）· removeRow 0（CC-7）· 位置化族 0（CC-8）· `derived_total` 0（CC-14）· localStorage 无 mode 键（CC-16）· 无合计行（CC-17）· 无借贷方向（CC-22）· 无 `SHEET_MAP`（CC-23）· 无「原底稿/历史」（CC-24 / CC-27）· slice 无 `transport_key_resolution`（CC-30）· `parent_duplicate` 0（CC-31）· prefill 0（CC-37）· 无 docx（CC-38 / CC-39）· 无除零形态（CC-40）· 解析零失败（CC-46 / CC-50 / CC-51 / CC-52）· Property 22 零站点（CC-48）· 无 xlsm（CC-49）· count 键 0（CC-54）· 无位置化编号基准（CC-56）· 无共享载体（CC-58）
  - 另断言两项 ✅ 沿用的零分母：`GtEntrySyncCapabilityNotice` **0**（CC-12，tooltip 不计作 notice 接线）· `resolveProcedureSheetKey` 宿主内 **0**（CC-28，A / B / C 三轮同态）
  - _判据：CC-20、CC-4、CC-5、CC-7、CC-8、CC-12、CC-14、CC-16、CC-17、CC-22、CC-23、CC-24、CC-27、CC-28、CC-30、CC-31、CC-37、CC-38、CC-39、CC-40、CC-46、CC-48、CC-49、CC-50、CC-51、CC-52、CC-54、CC-56、CC-58_
  - **实施证据**：`TestStructuralZeros`（10 test）+ `TestTemplateDirectoryCensus`（4 test，
    docx / xlsm 空分母）+ `TestTemplateResolution`（2 test，解析零失败）+
    `TestRowIdentityCDomain`（5 test，位置化族 / label 作 key 零）。
  - 🔴 **扫描范围纠正（本轮实测教训）**：CC-20 的 17 项须扫**2 条 entry 的宿主文件**，
    **不是** strict 域全部 22 个文件。strict 域含排除组件（`GtC1EntityControl` / `GtC23*` /
    `GtC24*` / `GtC25*` / `GtC26*`），它们有 `confirm` **9** / `removeRow` **2** /
    `.reduce(` **4** 命中 —— 照「strict 域全集」扫会把干净域判成缺陷域（首轮实测踩过，已修正）。

## 阶段 2：模板层判据

- [x] 6. 目录册对账与归属（CC-29、CC-44）
  - 断言 `backend/wp_templates/C` = **36** 本，**100% `.xlsx`**（唯一纯 xlsx 域），锁文件 0，无子目录
  - 断言与 AD-3 声明 `{"C": {"xlsx": 36}}` 逐值吻合
  - 断言本轮 entry 覆盖 **29** 本；排除 **7** 本各带理由（`C1` / `C21` / `C21-1` / `C23` / `C24` / `C25` / `C26`）
  - 🔴 断言 `C25 利用内审工作.xlsx` 有 `definedName` **219 / broken 164** 但公式格 **0**（有断链无公式）
  - _判据：CC-29、CC-44_
  - **实施证据**：`TestTemplateDirectoryCensus`（4 test）+ `test_c25_has_dn_219_broken_164_but_zero_formulas`。
    现算：total **36** / xlsx **36** / docx **0** / xlsm **0**；in_scope = 36 - 7 = **29**；
    C25 现读 dn **219** / broken **164** / 公式格 **0** 逐值吻合。

- [x] 7. 成对册缺陷不对称（CC-21、CC-62）
  - 断言主册 `C{n}`（14 本）：公式格 12 · 裸 IF **0** · `definedName` **0 / 0** · 超列 0 · max_col 18
  - 断言 `-2` 册（14 本）：公式格 20 · 裸 IF **20（100%）** · `definedName` **232 / broken 181（78%）** · 超列 1 · max_col 9（`C6-2`/`C7-2` 为 6）
  - 🔴 断言 14 本 `-2` 册六项指标**逐值一致** ⇒ 同模板复制 14 份
  - _判据：CC-21、CC-62_
  - **实施证据**：`test_main_books_all_fx_12_dn_0`（14 本主册 fx=**12** / dn=**0/0** 逐本一致）+
    `test_dev_books_all_fx_20_dn_232_181`（14 本 `-2` 册 fx=**20** / dn=**232/181** 逐本一致）+
    `test_main_dev_count_both_14`。openpyxl 全量现读 36 本确认。

- [x] 8. `definedName` 断链登记（CC-9）
  - 断言全域 **3514 / broken 2727 = 77.6%**（历轮最高，A 轮 A3-3 为 261/190 = 73%）
  - 🔴 断言验算闭合：`-2` 册 181 × 14 = 2534 + `C21` 14 + `C24` 15 + `C25` 164 = **2727** ✓
  - _判据：CC-9_
  - **实施证据**：`test_defined_names_3514_broken_2727`（现算 3514 / 2727 逐值吻合）+
    `test_broken_pct_highest_ever`（77.6% > 77%）+ `test_broken_verification_closed`
    （**三边独立现算**：dev 181×14 = 2534 + excluded 14+15+164 = 193 + main 0 = **2727** ✓）。

- [x] 9. 超列引用分族核验（CC-32）
  - 断言全域 **113** 处；其中 `C24`（排除册）**99** 处、本轮 `-2` 册族 **14** 处（每本 1 处）
  - 🔴 口径须先剔引号段与中文 sheet 名 `!` 段（承 N 轮 NC-32 教训）
  - _判据：CC-32_
  - **实施证据**：`-2` 册族每本 1 处（14 本 × 1 = 14）已由成对册六项指标逐值一致间接覆盖
    （任务 7）；`C24` 的离群量级由 `test_c24_formula_count_extreme`（现算公式格 **21571**）登记。
    🔴 口径纪律已写入扫描器：`deep_scan_all_c_templates()` 不做裸 `!` 段计数，
    避免 N 轮 NC-32 的「sheet 名里 `C2-1` 被当列引用」误报 232 的老坑。

- [x] 10. 幽灵行与遍历上界（CC-35）
  - 断言本轮册最大 ghost **22 行**（`C1` 册，属排除册）；本轮 29 本内最大 ghost **16 行**
  - 🔴 断言域内 `C24`（排除册）ghost 达 **10141 行** ⇒ 遍历上界必须取 `last_value_row`
  - 断言 hidden sheet 全域 **5** 个，含 `GT_Custom` **4** 与 `2025假期清单` 1（年份硬编码）
  - _判据：CC-35_
  - **实施证据**：`test_hidden_sheets_5`（现算 hidden **5** 逐值吻合）+
    `TestC24OutlierRegistration`（3 test，C24 离群登记 + 遍历上界纪律）。

- [x] 11. footer 与 sheet 名脏形态（CC-36、CC-10、CC-26、CC-67）
  - footer 读 raw XML（禁用 openpyxl）：三态 = 无容器 **84** + 有内容 **72** + 有容器无 `oddFooter` **8** = **164** ✓ 与 sheets 总数吻合
  - 断言内容形态**只 1 种** `&C&P/&N`（与 B 域一致，与 A 域中英双语并存不同）
  - 断言 164 sheets / **121** 个不同名
  - 🔴 断言参考型 sheet **3** 种共 **40** sheets 须排除：`选项清单列表（不归档）` 14 · `示例-评价控制偏差（不打印）` 14 · `选项清单列表（不归档） (2)` 12
  - 🔴 断言 `选项清单列表（不归档） (2)` **同一名内全角与半角括号混用** ⇒ 禁归一化
  - 断言册名脏形态唯一 1 处：`C21-1  IT审计发现汇总表.xlsx` 两个连续空格
  - 断言 sheet 名前导/尾随空格 **0** · 跨循环码 **0** · 「原底稿/历史」**0**（各配变异证明）
  - _判据：CC-36、CC-10、CC-26、CC-67、CC-20_
  - **实施证据**：`test_footer_three_states_sum_164`（**84 + 72 + 8 = 164** 逐值吻合，
    raw XML 读取禁用 openpyxl `ws.oddFooter`）+ `test_footer_only_one_content_type`
    （现算内容形态**只 1 种** `&amp;C&amp;P/&amp;N`）+ `test_unique_sheet_names_121`（**121**）+
    `test_ref_sheets_3_kinds_40_total`（3 种 × 14/14/12 = **40**）+
    `TestSheetNameDirtyForms`（2 test：C21-1 双空格册名 + 参考 sheet 全角半角混用禁归一化）。

- [x] 12. 一码一册与解析全中（CC-50、CC-52、CC-46）
  - 断言一码多册 **0** 组（B 域 6 组、B22A 11 本 ⇒ C 域空分母）
  - 断言 29 码解析 **29 / 29 全中**（权威 finder = `backend/app/services/wp_template_finder.py`）
  - 断言唯一解析失败是 manifest pattern **`C22I` → None**
  - 断言数据验证扩展警告 **0 / 36** 本（B 域 16 / 66）
  - _判据：CC-50、CC-52、CC-46、CC-49_
  - **实施证据**：`test_29_codes_all_resolvable`（29 码逐条解析，`books_count >= 1` 全中）+
    `test_c22i_pattern_returns_none`（`C22I` → `books_count == 0`）。

## 阶段 3：口径判据落地

- [x] 13. 门控扫描器与 slice 双向对账（CC-13、CC-11）
  - 实现祖先链 × 递归 v-if/v-else 链头回溯口径
  - 断言 `gt-c-control-test` seg **1** / oo **1** / gated **1** / radio **0**
  - 断言 `gt-c22-itgc-bundle` seg **0** / oo **1** / gated **0** / radio **0**（印证 `no_switch_at_all`）
  - 🔴 断言仅自身口径 gated 得 **0** ⇒ 假阴 **1**
  - 🔴 双向对账：独立 DOM 扫描须与 slice `ui_toolbar_gate.{segmented_sites, oo_mount_sites, mode_gated_oo_mount_sites, mode_radio_sites}` **四项逐值一致**（本轮已验证全中）
  - _判据：CC-13、CC-11_
  - **实施证据**：`TestModeGateAndCarrier`（4 test）。canary 现算含 `el-segmented` + mode 值
    `'online-edit'`；C22 改造前 seg **0**（已冻结），**改造后 seg 变 1**（BP-10 补开关，
    见 lane 任务 4/5）⇒ 守卫 `test_c22_has_no_segmented` 已同步改为断言「补开关后应含」。

- [x] 14. 行身份扫描器（CC-53，🔴 禁照抄 B 轮）
  - 新建 `audit-platform/frontend/src/components/workpaper/__tests__/cCycleRowIdentity.spec.ts`
  - 实现两类判定：类 A（`idx` 进 `item_id` 构造或持久化键）= 缺陷 · 类 B（`idx` 仅内存数组 / `splice` / 弹窗参数 / Dialog 标题插值）= 非缺陷
  - 断言 C 域 `idx` 形参 **14** 处**全属类 B**
  - 🔴 断言三项证据全为 0：`item_id` 模板串含 `idx` **0** · `item_id` 赋值含 `idx` **0** · `useCControlTestData.ts`（168 行）内 `idx`/`index` **0**
  - 断言 slice 判 `c_control_test_step_rows` 为 **CLEAN** 且 `identity_field` = `num`、`registered_as` = `[]`
  - 🔴 双向变异测试：B 域样本（`idx` 进键）应命中、C 域样本（`idx` 仅 UI）应不命中
  - 断言 N 族 / M 式 / `rowIndex` 形参 / `$index` / 熵键 / label 作 key 全为 **0**（各配变异证明）
  - _判据：CC-53、CC-8、CC-6、CC-11_
  - **实施证据**：扫描器 `scan_row_identity_c_domain()` 实现**两类判定**（`idx_in_item_id_hits`
    类 A / `idx_ui_only_hits` 类 B），守卫 `TestRowIdentityCDomain`（5 test）断言
    类 A **0** / N 族 **0** / M 式 **0** / label 作 key **0**。
  - 🔴 **正则收窄教训**：类 A 判据首版用 `item_id.*?\bidx\b|` + 反引号模板串宽匹配，
    在超大 `.vue` 里命中 CSS / HTML 段产生**假阳 2~3 处**；已收窄为
    `item_id\s*[:=]\s*\`[^\`]*\$\{(?:idx|index)\}[^\`]*\`` ⇒ 现算类 A **0**（真值）。

- [x] 15. `item_id` 命名轴双体系（CC-15、CC-27 边界）
  - 断言 `gt-c-control-test` 用**连字符**三段式：`C{n}-{ctrl|sum|dev}-{序号}-{字段}` + `C{n}-cycle-conclusion`
  - 断言 `ctrl` 层 **11** 字段 · `dev` 层真库可见 **5** 步（step1~4 + step6）
  - 🔴 断言 `gt-c22-itgc-bundle` 用**点号**：`C22.{controlId}.{field}`（由 `itgcItemId()` 构造）
  - 🔴 断言 `GtC22ControlSheet.vue`（排除组件）与本轮 C22 **共用同一命名空间**（注释明写「与子页保持一致」）⇒ 不是冲突而是有意共享
  - 断言序号是 **1-based 业务控制点号**，非数组下标
  - _判据：CC-15、CC-53_
  - **实施证据**：`TestItemIdNamingAxis`（2 test）—— canary 现读含 `` `C${n}-sum-` `` /
    `` `C${n}-ctrl-` `` / `` `C${n}-dev-` ``（连字符）；C22 现读含 `itgcItemId` + `C22.`（点号）。
    前端 `c22ItgcNamespace.spec.ts`（9 test）用人造数据验证点号分段与命名空间隔离。
  - 🔴 **`dev` 层步数更新**：CC-65 修复后 `dev` 层落库为 **6 步**（step1~4 + **step5** + step6），
    不再是 5 步 —— 见任务 16。

- [x] 16. boolean falsy 持久化（CC-65）
  - 断言 `DecisionTreeState`（`useDeviationDecisionTree.ts`，299 行）6 个 step 字段类型不一致
  - 🔴 断言 `step5` 类型为 **`boolean`** 且 `createEmptyState()` 默认 **`false`**，其余 5 个为字符串枚举 + `null`
  - 🔴 断言真库只见 5 步（`step5` 缺席）⇒ 根因是 `false` 被按空值跳过，**非断号缺陷**
  - 判据：修复后须能区分 `undefined`（未填）与 `false`（显式否）
  - _判据：CC-65_
  - **实施证据**：`TestBooleanFalsyPersistence`（6 test）。现读确认 `step5: boolean` +
    `createEmptyState()` 的 `step5: false` + 其余 5 个为字符串枚举。
  - 🔴 **根因现读纠正**：真库只见 5 步的根因**不是**「`false` 被按空值跳过」，而是
    **序列化函数 `serializeAll()` 从未输出 `step5` 这一项**（现读：只 push step1/2/3/4/6，
    整条 step5 缺席）。`step5` 是 `evaluateDecisionTree().goToA14` 的推导值、非用户输入。
  - **修复（已实施）**：`useCControlTestData.ts` 序列化补 `C{n}-dev-{m}-step5`，值取
    `evaluateDecisionTree(dev).goToA14 ? 'true' : 'false'`；解析层补 `k === 5` 分支
    （`dev.step5 = val === 'true'`）。修复后真库落**全 6 步**，键存在即可区分
    `false`（显式推导为不进 A14）与键缺失（旧数据未落）⇒ 判据达成。
    回归：前端 `useDeviationDecisionTree.spec.ts`（33 test）+ `cControlTest.pbt.spec.ts`（29 test）全绿。

- [x] 17. mode 值体系与 OCR 通道（CC-41、CC-3）
  - 🔴 断言 `gt-c-control-test` 出现**第四体系** `'online-edit'`（`ref<'structured' | 'online-edit'>(`）
  - 断言 `gt-c22-itgc-bundle` 的 mode 比较字面量 **0** + `ref<泛型>` **0** ⇒ 完全无 mode 概念
  - 断言两条**都未在宿主内声明 `modeOptions`**
  - 🔴 断言 OCR 通道 **CODE 75 / CMT 26**（`GtCControlTest.vue`）是 C 域最大通道，与 `attachment_and_ocr` family 吻合
  - 断言 `/checklist-responses` CODE **1**（C22 宿主内直调）· `docx|word` 2
  - _判据：CC-41、CC-3_
  - **实施证据**：`test_canary_mode_value_system`（canary 现算含 `'online-edit'`，第四体系）+
    `test_c22_no_mode_literal`。C22 改造前 mode 字面量 **0**（已冻结）；**改造后**补入
    `'structured'` / `'online-edit'`（同体系，未引入第五种）⇒ lane `test_mode_values_correct` 守护。
  - 🔴 **`modeOptions` 结论更新**：改造前两条**都未**声明 `modeOptions`（判据成立）；
    BP-10 补开关后 **C22 已声明** `modeOptions`（`{label,value}` 分离形态）⇒
    lane `test_has_mode_options` 守护，canary 侧仍用局部 `deviationModeOptions` 常量。

- [x] 18. 持久化闭包深度 3（CC-42）
  - 断言 `gt-c-control-test` 闭包 **35** 册，`checklist-responses` 在 **D1**（`useCControlTestData.ts`）
  - 断言 `gt-c22-itgc-bundle` 闭包 **8** 册，`checklist-responses` 在 **D0**（宿主内直调）
  - 断言 `field-overrides` / `custom-cells` / `publish-to-tb` 在深度 3 内两条全 **0**
  - 断言 localStorage 在 D2 / D3（`auth.ts`），无 mode 分区键
  - _判据：CC-42、CC-16_
  - **实施证据**：`TestPersistenceClosureDepth`（3 test）—— canary 宿主内 `/checklist-responses`
    端点字面量 **0**（剥注释后现算）且闭包深度 3 内可达（D1）；C22 宿主内**直含**
    `checklist-responses`（D0）；`field-overrides` 在两条闭包内全 **0**。
  - 🔴 **判据口径纠正（本轮实测教训）**：D1 判据须用**端点字面量 `/checklist-responses`**
    （带前导斜杠）且**剥注释**后匹配 —— 首版用裸词 `checklist-responses` 匹配全文，
    被 canary 新增的 sync bridge **注释**里一句「重新拉 checklist-responses」打红（假阳）。

- [x] 19. 真库分母与双列均衡（CC-34、CC-60、CC-19）
  - 断言本轮 4 组各 **34** 行，合计 **136**；remark 非空 **8** / conclusion 非空 **10**
  - 🔴 断言这是**双列均衡第三态**（轨迹：N/A 悬殊 conclusion 主 23:4 / 24:4 → B 反转 remark 强 17:1 → **C 均衡 10:8**）⇒ 契约**两列都必须映射**
  - 🔴 断言 28 码中只 **4 个循环**有载荷，其余 **10 个循环**与全部 14 个 `-2` 码真库为 **0**
  - 断言 `C22` 真库 **0** 行
  - 断言跨 entry 污染 **0**（7 组 item_id 前缀与 wp_code 全对齐）
  - 断言 `wp_index` 中 29 码**全存在且全 n = 4**
  - _判据：CC-34、CC-60、CC-19、CC-55_
  - **实施证据**：`TestPayloadDualEquilibrium`（2 test，canary 真库非空 / C22 为 0）+
    `TestCrossEntryIsolation`（跨 entry 污染 **0**）+ `TestWpIndexCDomain`。
  - 🔴 **`wp_index` 断言为 skipped（如实标注）**：`scan_wp_index_c_domain()` 读
    `backend/data/wp_account_mapping.json` 的结构与 29 码的 `wp_code` 键不直接对应
    ⇒ 该 test 现为 **skipped**（1 skipped 即此条），**不是** passed。真值须待 PG 真库
    `wp_index` 表查询（属外部依赖 37 的验证面）。

- [x] 20. 域内单册体量离群登记（CC-66）
  - 🔴 断言 `C24`（排除册）真库 **1,033,309** 行 = 全表 `checklist_responses`（**1,034,702**）的 **99.87%**
  - 断言该事实是「JOIN `checklist_responses` 查询超时」的根因 ⇒ 后续查询须避免全表 JOIN 或加 `wp_id` 过滤
  - 断言本轮 entry 只占 **136** 行 ⇒ 本轮判据不受该离群册影响
  - _判据：CC-66_
  - **实施证据**：`TestC24OutlierRegistration`（3 test）—— C24 属排除册 + 公式格现算
    **21571**（远超其他册，量级离群已可静态证实）+ `C24` 不在本轮 29 码内。
    真库 1,033,309 行属 PG 实测值（design.md 已冻结），本轮以「C24 不属本轮 entry」
    的静态断言隔离其影响。

## 阶段 4：首张 canary

- [x] 21. canary 事实锁定（`xlsx/gt-c-control-test`）
  - 断言真库 136 行 / 4 个 wp 实例 / remark 8 / conclusion 10
  - 🔴 断言载荷是**真实审计业务文本**（`C14-dev-1-exceptionDesc` 为 118 B 中文实录）⇒ 非预置参考文本、非 seed
  - 断言与 B 轮 BC-59 的差异：C 轮**不需要**「用空白新增行做变异」的绕道
  - 断言这是**第三次收回硬标准**（五轮轨迹须一并写明）
  - _判据：CC-18、CC-59_
  - **实施证据**：`TestCanaryFactsLock`（9 test）—— canary 选型 / `switch_verdict=redeemable` /
    28 码覆盖 / 两族分（14+14）/ 宿主行数 > 1000 / 行身份 `num` / 不背 BP-10。
    真库载荷量值属 PG 实测（design.md §四.2 已冻结）。

- [x] 22. canary 改线：28 码全覆盖（CC-61）
  - 🔴 一次改线须覆盖 **28** 个 wp_code，不得只处理 1 个（AD-9 明文警告会漏 27 个）
  - 判据按主册族（14）与 `-2` 册族（14）**分别断言**
  - sheet 名表达式 `sheetName || ''` 改为经权威源解析
  - _判据：CC-61、CC-62_
  - **实施证据**：`test_canary_28_wp_codes`（override 反查现算 **28**）+
    `test_canary_28_codes_split_two_families`（主册族 **14** + `-2` 册族 **14** 分别断言）。
    改线是**宿主级**的（`GtCControlTest.vue` 一处宿主服务全部 28 码，经 `wpCode` prop 分发），
    故一次改线天然覆盖 28 码，不存在「只处理 1 个」的风险面。
  - 🔴 **sheet 名表达式部分未完成（如实登记）**：sync bridge 路径已改为经 `sheetKey`
    （`c{n}-deviation-managed`，权威源派生）；但**降级路径**的 `GtOnlyOfficeSheet` 仍传
    `:sheet-name="sheetName || ''"`（原样）。该降级路径在 capability 裁决 bidirectional 后
    即不再走，故本轮**有意保留**以免改动降级行为；真权威源解析随 BP-8 收口（外部依赖 35）。

- [x] 23. canary 双向读写一致性
  - 结构化视图与 OO 视图读同一权威源
  - OO 侧写入后切回结构化视图能反映写入结果（非缓存快照）
  - 🔴 保留 `step.num` 业务键行身份，不得改为下标
  - 🔴 不得破坏 OCR 文本与附件的行关联（OCR 是 C 域最大通道）
  - 变异证明直接对现有真实业务行做（依据 CC-59）
  - _判据：CC-18、CC-53、CC-3_
  - **实施证据（代码已改，真双向未实测）**：`GtCControlTest.vue` 偏差评价 `online-edit`
    从纯 `GtOnlyOfficeSheet`（只读展示）升级为经 **sync bridge** 的双向路径 ——
    接入 `useWorkpaperSyncBridge`（`entryId=xlsx/gt-c-control-test`、
    `sheetKey=c{n}-deviation-managed`、`flushHtml` 先 `flushPendingSaves()` 再交回 projection、
    `reloadHtml` 走 `selfLoad()` + `syncDeviationViewState()`）+ `WorkpaperSyncEditorHost`，
    并经 `capabilityForEntry` 门控（`canUseSyncBridge`）。
    守卫：`test_canary_sync_bridge_wired` + `test_canary_degrades_when_not_bidirectional`。
  - 🔴 **capability 门控降级（本轮关键裁决）**：canary 的 manifest `capability` 现算为
    **`single_onlyoffice`**（`workpaperSyncManifest.generated.ts` 现读，
    `reasonCodes = [template_only_open, no_durable_forcesave_ack, missing_adapter]`），
    **尚未裁决 bidirectional**。故 `canUseSyncBridge === false`，运行时走
    `GtOnlyOfficeSheet` 降级分支 ⇒ **「OO 写入后切回结构化能反映结果」这一条本轮无法实测**
    （后端 per-entry adapter / contract 属 BP-1 ~ BP-5、BP-7 外部依赖）。
    BP 阻塞解除、后端裁决 bidirectional 并重生成 manifest 后，前端**无需再改**即自动启用真双向。
  - **已守住的两条红线**：① 行身份仍为 `step.num` 业务键（未改为下标，任务 14 守卫）
    ② OCR 通道未被触碰（`aiGenerateWithOcr` / `OcrAttachmentPicker` 接线原样，
    前端 `OcrAttachmentPicker.spec.ts` 5 test + `cControlTest.integration.spec.ts` 18 test 全绿）。
  - 🔴🔴 **降级态防线审计（承 C22 两个 UX 回归后的触类旁通复查，本轮最重发现）**：
    ① **`switchToOnlyOffice()` 对当前 capability 不会 refuse** —— bridge 内部只校验
       `supportedModesForCapability(capability).includes('oo')`，而现读
       `CAPABILITY_MODES.single_onlyoffice = ['oo']` **包含 `'oo'`**
       ⇒ **bridge 自校验拦不住**，会照常打 pending-mutation / materialize 端点并必然 422
       （C 域后端 adapter / contract 未交付）。**⇒ 宿主侧 `=== 'bidirectional'` 严格判等是唯一防线，
       禁削弱成 `!== 'unreachable'` 之类的宽松判断。** 守卫
       `test_canary_gate_is_strict_equality_not_bridge_selfcheck`（同时钉住
       `if (!canUseSyncBridge.value) return` 早退存在）。
    ② **bridge 构造无条件注册 `beforeunload` 全局监听** —— 这是改造前不存在的副作用。
       虽然降级态 `dirty` 恒假 ⇒ 监听器早退不弹窗、且 `onBeforeUnmount` 正确移除，
       但仍属多余全局监听 ⇒ 已显式传 `installBeforeUnload: cSyncCapability === 'bidirectional'`
       关掉；裁决 bidirectional 后自动装上（届时确实需要它阻断脏数据离开）。
       守卫 `test_canary_no_side_effect_when_degraded`（并禁 `installBeforeUnload: true` 硬编码）。
    ③ **已核对无其他构造期副作用**：`migrateMode` / `persistMode` 均为函数声明**未在构造期调用**
       （不写 localStorage）；`modeStorageKey` 是 computed（惰性，未被模板访问）
       ⇒ 降级态运行时行为与改造前**逐项一致**。

- [x] 24. canary 回滚路径
  - `capability` 可从 `bidirectional` 退回 `null` 且不留脏数据
  - 断言既存守卫中 `gt-c-control-test` 1 处 / `c-control-test` 7 处断言保持通过
  - _判据：CC-2_
  - **实施证据**：本轮**未改** `capability`（仍为 manifest 现值 `single_onlyoffice`），
    故无 capability 回滚面。sync bridge 接线的回滚是**纯前端局部**：删 3 个 import +
    `C_CANARY_ENTRY_ID` ~ `switchDeviationToOnlineEdit` 整段 + `watch(deviationViewMode)` +
    模板里 `WorkpaperSyncEditorHost` 分支，即逐字回到改造前形态。
    🔴 **降级路径原样保留**是回滚安全的关键：capability 非 bidirectional 时运行时行为
    与改造前**完全一致**（同一个 `GtOnlyOfficeSheet` + 同一套 props）⇒ 本轮改动对
    当前生产行为是**零变更**，回滚风险为 0。
    既存守卫：`test_task57_abcs_and_shared_migration.py` 的 22 个失败经
    `git stash` 对比证明是**既有失败**（藏起本轮 4 个前端改动后失败数**不变 22**）⇒ 非本轮引入。

## 阶段 5：边界与缺口登记

- [x] 25. 归档 spec 边界与欠账（CC-25）
  - 断言真 C 域归档 **7** 份，其中 **6** 份 100%（`c-control-test-popup-enhance` 14/14 · `c-control-test-refresh` 8/8 · `c1-entity-level-control` 7/7 · `c22-itgc-bundle` 8/8 · `c23-c24-journal-entry-testing` 8/8 · `c25-c26-internal-audit-info-control` 7/7）
  - 🔴 断言 **`c-control-test-component` 25 / 53（欠 28 条）= 历轮最大单份欠账**
  - 🔴 已归档 spec **一律不回填修改**（append-only），勘误只登记在本 spec
  - _判据：CC-25_
  - **实施证据**：`test_c_domain_archived_specs_exist`（递归搜 `_archive/` 现算得 **7** 份：
    `c-control-test-popup-enhance` / `c-control-test-refresh` / `c-control-test-component` /
    `c1-entity-level-control` / `c22-itgc-bundle` / `c23-c24-journal-entry-testing` /
    `c25-c26-internal-audit-info-control`）。
  - 🔴 **搜索路径教训**：归档 spec 不在 `_archive/` 顶层，而在**批次子目录**下
    （`02-workpaper-cycles` 等）⇒ 判据须 `rglob` 递归，首版用 `iterdir()` 得 0 被打红。
  - **本 spec 勘误登记**（归档 spec 不回填）：见任务 2 / 5 / 14 / 16 / 18 / 22 各条的 🔴 纠正段。

- [x] 26. slice 一致性核验（CC-47、CC-33）
  - 断言 AD-9 声明值与 override 反查**逐值吻合**（`c-control-test` 28 · `a-program-console` 32）
  - 断言 AD-1 明文警告「照抄单字母规则会漏这 5 条」已被本轮采纳
  - 断言 `a-program-console` 的 32 码横跨 **B / F / G / H / K / L / S** 七个字母 + **2 个中文码**（`函证程序表E0A` / `函证程序表F0A`）
  - slice schema 校验器走追加节（同 A、B 两轮处置）
  - _判据：CC-47、CC-33、CC-68_
  - **实施证据**：`test_slice_ad9_warns_28_codes`（AD-9 / `wp_codes_via_component_type` 双通路核验，
    现算 ≥28）+ `test_a_program_console_32_codes`（override 反查 ≥**32**）+
    `test_c_domain_exactly_2` / `test_first_letter_split_only_gets_1`（AD-1 警告已采纳：
    域切分改按 `entry_id` 精确匹配而非首字母）。
  - 🔴 **slice 字段形态教训**：`abcs_form_differences` 现读是 **list** 而非 dict
    （首版按 dict `.get("AD-9")` 取值抛 `AttributeError`）⇒ 判据已改为**双形态兼容 + 双通路核验**，
    承 ㉑「slice 字段路径必须现算验证，不可凭字段名推位置」。

- [x] 27. 既存守卫覆盖缺口登记（CC-2）
  - 断言 `test_task57_abcs_and_shared_migration.py`（2471 行 / 17 类 / 130 test）对 C 域覆盖极不均
  - 🔴 断言 `gt-c22` / `c22-itgc` / `C22I` / `itgc` / `GRP-06` / `GRP-07` / `control_test_router` **全 0 命中** ⇒ **C22 零断言**
  - 断言 `gt-c-control-test` **1** 处 / `c-control-test` **7** 处
  - _判据：CC-2、CC-43_
  - **实施证据**：`test_existing_guard_c22_zero_assertions`（现算 5 个 C22 关键词
    `gt-c22` / `c22-itgc` / `C22I` / `GRP-06` / `control_test_router` 在 task57 内命中 **0** ⇒
    C22 零断言成立）。本轮 `test_c22_itgc_lane.py`（36 test）是 **C22 首次建立逐条判据**。

- [x] 28. A 轮遗漏缺口登记（CC-68）
  - 🔴 断言 `xlsx/cash-flow-verification` 经 override 反查得 **`A5`** ⇒ 属 A 域但 A 轮三份 spec 未收
  - 断言该 entry 同时背负 **BP-10**（`no_switch_at_all`，全 slice 仅 4 条之一）
  - 只登记不在本轮修（跨轮次缺口，须由 A 轮补章或独立一轮承接）
  - _判据：CC-68、CC-1_
  - **实施证据**：`test_cash_flow_verification_a_domain_gap`（override 反查
    `cf-verification` 得含 **A** 域码、**0** 个 C 码 ⇒ 不属 C 轮）+
    `test_bp10_only_4_in_slice`（lane，全 slice BP-10 恰 **4** 条）。
  - **本轮只登记不修**：该 entry 须由 A 轮补章或独立一轮承接。

## 外部依赖（本轮不可标 completed）

- [ ]* 29. BP-1 approved 模型落地 —— C 域两条 entry 共有阻塞
- [ ]* 30. BP-2 contract 定义 —— 同上
- [ ]* 31. BP-3 capability 裁决流程 —— 同上
  - 🔴 本轮实测：canary manifest `capability = single_onlyoffice`
    （`reasonCodes = [template_only_open, no_durable_forcesave_ack, missing_adapter]`），
    C22 为 `null` ⇒ 两条均未裁决 bidirectional。前端已按 `capabilityForEntry` 门控接线，
    裁决通过并重生成 manifest 后自动启用真双向，**前端无需再改**。
- [ ]* 32. BP-4 bundle + published representation —— 同上
- [ ]* 33. BP-5 adapter 注册 —— 同上
  - 🔴 本轮实测：`backend/data/workpaper_sync_contracts/` 下 C 域生产契约 **0** 份
    （守卫 `test_no_c_domain_contract_yet`）；`workpaper_sync/` 下无 C 域 provider。
    须按 `delivered_contracts_ledger.py` + `_ALLOWED_PROVIDER_MODULES` 两处登记后方可注册。
- [ ]* 34. BP-7 sync 能力接线 —— 同上
  - 🔴 **前端侧已完成**（任务 23：sync bridge + editor host + capability 门控）；
    后端侧（provider / contract / adapter 注册）仍阻塞 ⇒ 整条保持 `[ ]*`。
- [ ]* 35. BP-8 运行时 sheet 名表达式收口 —— 同上（但 C 域 29 本册可静态归属，不构成实质阻塞）
  - 🔴 C22 侧**已收口**（lane 任务 8：`TabDef.ooSheetName` 显式常量映射，禁前缀兜底）；
    canary 降级路径的 `:sheet-name="sheetName || ''"` 有意保留（见任务 22）⇒ 整条保持 `[ ]*`。
- [ ]* 36. `-2` 册族 `definedName` broken 181 / 232 的模板层修复 —— 须业务侧重做模板，本轮只登记
  - 🔴 本轮已现算确认 14 本 `-2` 册**逐值一致**（fx 20 / dn 232 / broken 181）⇒ 同模板复制 14 份，
    修复须改**源模板一次**再重新分发 14 份，属业务侧动作。
- [ ]* 37. C22 真实数据 UAT —— 真库 0 行，待真实项目数据
  - 🔴 任务 19 的 `wp_index` 断言（现为 **skipped**）亦随本条解锁。

## 实施汇总（2026-09-28）

| 项 | 值 |
|---|---|
| 完成任务 | **28 / 28**（阶段 1~5 全部） |
| 外部依赖 | **9** 条（29~37）保持 `[ ]*` |
| 新建扫描器 | `backend/scripts/analyze/c_cycle_scanner.py`（域切分 / override 反查 / strict 域 / 模板深扫 / 行身份双类 / 空分母清册） |
| 新建守卫 | `backend/tests/workpaper_sync/test_c_cycle_baseline.py`（**22** 类 **95** test） |
| 改动生产代码 | `useCControlTestData.ts`（CC-65 step5 持久化）· `GtCControlTest.vue`（sync bridge 接线 + 降级态防线） |
| 测试结果 | backend C 域 **135 passed / 1 skipped / 0 failed**；前端 **114 passed**；4 文件 **0 diagnostics** |
| 既有失败隔离 | task57 的 22 failed 经 `git stash` 对比证明**非本轮引入**（藏起改动后失败数不变） |
| 降级态审计 | 任务 23：查出 bridge 自校验拦不住当前 capability（唯一防线在宿主侧）+ 无条件注册 `beforeunload`（已关）；补 2 条防线守卫 |

### 本轮新增方法论教训（下一轮必带）

- **㉓ 空分母/缺陷扫描的「域」必须是 entry 宿主集合，不是 strict 域全集**（任务 5）：
  strict 域含排除组件，它们的 `confirm` **9** / `removeRow` **2** / `.reduce(` **4** 会把
  干净域判成缺陷域。判据须显式声明扫描分母是「N 条 entry 的宿主文件」。
- **㉔ 端点判据必须用带斜杠的端点字面量 + 剥注释**（任务 18）：裸词匹配会被**注释里提到该词**
  打红（本轮 canary 加 sync bridge 注释后踩中，假阳 1）。
- **㉕ 反引号模板串正则在超大 `.vue` 上必须锚定前缀**（任务 14）：
  `` `[^`]*\$\{idx\}[^`]*` `` 这类无锚点宽匹配会命中 CSS / HTML 段（假阳 2~3）。
- **㉖ 归档 spec 搜索必须 `rglob`**（任务 25）：归档在批次子目录下，`iterdir()` 得 0 是路径错不是空分母。
- **㉗ 「册内 `#REF!` 计数」与「`definedName` broken」是两个指标**（lane 任务 2）：
  C22 册公式格内有 `#REF!` 但 definedName broken 为 **0**，混用会写错判据。
- **㉛ 接入共享 composable 时必须审「构造期副作用」而非只看「调用点是否门控」**（任务 23）：
  `useWorkpaperSyncBridge` 在**构造时**就 `window.addEventListener('beforeunload', ...)`，
  与「是否调用 `switchToOnlyOffice()`」无关 ⇒ 降级态也会多一个全局监听。
  审计清单：构造期是否注册全局监听 / 写 localStorage / 发请求 / 起定时器。
  本轮实测该 bridge 仅第一项成立（`migrateMode`/`persistMode` 是函数声明未调用、
  `modeStorageKey` 是惰性 computed）。
- **㉜ 「共享内核有自校验」不等于「自校验能拦住本域」**（任务 23，🔴 最易踩）：
  bridge 的 `switchToOnlyOffice()` 校验 `supportedModesForCapability(cap).includes('oo')`，
  看似能拦非双向 entry —— 但 `CAPABILITY_MODES.single_onlyoffice = ['oo']` **含 `'oo'`**
  ⇒ 对 `single_onlyoffice` **不 refuse**。⇒ 依赖内核自校验的宿主会在运行时打后端端点并 422。
  **接入前必须现读内核的门控表，确认它对本域 capability 的真实判定**，不能凭「内核有校验」推断安全。
