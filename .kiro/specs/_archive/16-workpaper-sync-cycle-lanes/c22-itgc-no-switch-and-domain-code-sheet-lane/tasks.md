# C22 ITGC 无开关与域码 sheet 名通道 — 任务

> 判据一律引用 `c-cycle-sync-foundation-and-first-canary` 的 CC 编号，本文件不重复裁决。
> 🔴 补开关（任务 2~5）是 BP-10 的前置硬约束，须在改裁 `bidirectional` 之前完成。

## 阶段 1：事实基线

- [x] 1. 冻结本 entry 事实基线
  - 断言 `entry_id` = `xlsx/gt-c22-itgc-bundle`、宿主 922 行、`group_id` = GRP-06、family = `c_class_bundle`
  - 断言 `switch_verdict` = **`no_switch_at_all`**、`dual_mode_carrier.kind` = **`no_carrier`**
  - 断言 BP 数 **8** 且含 **BP-10**（全 slice 仅 4 条，本条是其一）
  - 断言 `wp_code_patterns` = `['C22I']` 但解析为 **`None`**；`wp_codes_via_component_type` = `['C22']`
  - 断言真库 **0** 行、import 闭包 **8** 册（全 C 域最小）、持久化在 **D0**
  - _判据：CC-2、CC-43、CC-42、CC-46、CC-60_
  - **实施证据**：`backend/tests/workpaper_sync/test_c22_itgc_lane.py::TestC22FactBaseline`（12 test 全绿）

- [x] 2. 补开关前置三条论证（禁跳过）
  - 论证一：`html_counterpart_verdict` 现算为 **`exists`**
  - 论证二：`find_template_file_any('C22')` → `C22 IT一般控制测试.xlsx` 可解析
  - 论证三：册内非空 —— **34** sheets / 公式格 **61** / 带 fx sheet **31**（全 C 域最多）/ `#REF!` **2**（全域仅此）
  - 🔴 结论须是「需要补开关」，禁以「没有开关」为由裁 `single_onlyoffice`
  - _判据：CC-41、CC-9、CC-32_
  - **实施证据**：三项均现算落测 —— `test_c22_authority_book_exists` / `test_c22_book_34_sheets`（34）/
    `test_c22_book_61_formulas`（61）/ `test_c22_book_31_fx_sheets`（31）/ `test_c22_book_ref_errors`。
    🔴 **勘误（现算纠正）**：design.md 的「`#REF!` = 2」指**公式格内 `#REF!` 计数**，
    不是 `definedName` broken —— C22 册 definedName 共 2 个（`AS2DocOpenMode` / `TextRefCopyRangeCount`），
    **broken 为 0**。测试已按真实语义拆成两项断言。
  - **结论**：需要补开关（三条论证全部成立）

## 阶段 2：补模式开关（BP-10）

- [x] 3. 补开关现状断言
  - 断言 `el-segmented` **0** · mode 门控 OO 挂点 **0** · mode 比较字面量 **0** · `ref<泛型>` **0** · 宿主内 `modeOptions` **未声明**
  - 断言与 slice `switch_verdict = no_switch_at_all` 逐值吻合
  - _判据：CC-41_
  - **实施证据**：改造前五项现算全为 0（已冻结在 design.md §二.1）。补开关后
    `TestC22SwitchAbsence` 的断言已按 post-fix 状态改写（有 segmented / 有 renderMode /
    有 modeOptions / mode 值为 `'structured'` 与 `'online-edit'`）。

- [x] 4. 补入开关（采用正确形态）
  - 采用 `{label, value}` 分离形态，🔴 **禁**引入中文标签直接作 mode 值（A 域 17 条踩过该坑）
  - mode 值用 `'structured'` 与 canary 侧的 `'online-edit'` 保持一致，🔴 **禁引入第五种体系**
  - OO 挂点须被 mode 门控（补完后祖先链或自身须含 mode 条件）
  - _判据：CC-41、CC-13_
  - **实施证据**：`GtC22ItgcBundle.vue` 新增 `renderMode` ref（`'structured' | 'online-edit'`）+
    `modeOptions`（`{label,value}` 分离）+ `showModeToolbar` + `defaultModeForSection()` +
    **2 处** `el-segmented` 控件（C21 与 C21-1 各一）；**2 处** OO 挂点均受 mode 门控
    （`v-if="renderMode === 'online-edit' && activeDocTab && subWpId(activeDocTab)"`）。
    守卫 `test_no_chinese_label_as_mode_value` + `test_oo_mount_count_is_two`。
  - 🔴 **首版引入两个 UX 回归，已复查发现并修复**（本轮最重教训 —— 「补开关」不等于
    「把默认呈现也改掉」）：
    ① **C21 默认模式回归**：首版 `renderMode` 一律默认 `'structured'`，但 C21 **只有独立册
       文档、无结构化视图** ⇒ 用户进 C21 tab 看到「开发中」占位符，而**改造前直接显示文档**。
       修复 = `defaultModeForSection()` 单一函数按 section 派生默认值
       （`C21 → 'online-edit'`、`C21-1 → 'structured'`），并在
       **`activeSection` setter 与路由 `activateSheet()` 两条入口共用**（只改 setter 会让
       「路由直接进 C21」仍停在占位符）。守卫 `test_default_mode_per_section_not_hardcoded` +
       `test_default_mode_applied_on_both_entries`（断言该函数 ≥3 次出现 = 1 声明 + 2 调用）。
    ② **`showModeToolbar` 对 C21-1 是死条件**：首版该计算属性对 `'C21-1'` 返回 `true`，但
       模板里 `v-else-if="activeSection === 'C21-1'"` 分支**在 C21 分支之前**且不含工具栏
       ⇒ C21-1 永远看不到开关（声明与实际不符）。修复 = C21-1 分支补工具栏 + OO 挂点，
       形成**真双模式**（结构化 = `GtC21FindingsSummary` 缺陷联动汇总 ↔ 在线编辑 = C21-1 册），
       默认 `'structured'` 保持改造前行为。守卫 `test_c21_1_branch_has_mode_toolbar`。
  - 🔴 **两条回归的共同根因**：只看「script 里开关是否存在」不看「模板分支顺序 + 各 section
    的原默认呈现」。⇒ 补开关类改动必须逐 section 列「改造前默认呈现 → 改造后默认呈现」对照表，
    任一行发生变化即为回归。

- [x] 5. 补完后回改 foundation 基线（🔴 同一 commit）
  - foundation 现算基线为「C 域 segmented **1** / mode 门控 **1**」，补完后变为 **2 / 2**
  - 🔴 须与 foundation 基线守卫**在同一 commit 内同步修改**，否则基线假红
  - 重新执行与 slice `ui_toolbar_gate` 四项的双向对账
  - _判据：CC-13、CC-11_
  - **实施证据**：foundation 守卫 `test_c22_has_no_segmented` 已在同一批改动内改为断言
    「补开关后应含 el-segmented」，与 lane 守卫同步（两文件同 commit）。

## 阶段 3：sheet 名解析

- [x] 6. 命中 0 / 3 事实冻结
  - 断言传入 `'C21'` 对册 `C21 具有信息技术专业技能的项目组成员.xlsx`（sheet 名 `C21 具有信息技术专业技能的项目组成员` + `GT_Custom`）**不命中**
  - 断言传入 `'C21-1'` 对册 `C21-1  IT审计发现汇总表.xlsx`（sheet 名仅 **1** 个 `IT 审计发现汇总表`）**不命中**
  - 断言传入 `'C22'` 对册 `C22 IT一般控制测试.xlsx`（34 sheets）**不命中**
  - 🔴 断言两条机理：① 前缀不等于全名 ② **`C21-1` 册的 sheet 名与册名完全脱钩**（册名双空格、sheet 名单空格且无 `C21-1` 前缀）
  - _判据：CC-63、CC-10_
  - **实施证据**：`TestC22SheetNameHit`（8 test）逐条落地，含 `test_zero_out_of_three`（0/3）与
    `test_c21_1_sheet_name_decoupled_from_book_name`（脱钩机理）。openpyxl 现读确认：
    C21 册 = `['C21 具有信息技术专业技能的项目组成员', 'GT_Custom']`、C21-1 册 = `['IT 审计发现汇总表']`。

- [x] 7. 🔴 裁决：方案 A 还是方案 B（须显式裁决，禁默认）
  - 方案 A：保持 OO 挂点加载 C21 / C21-1，只把传入值改为真实 sheet 名 —— 代价是 C22 册仍缺席链路
  - 方案 B：让 OO 挂点也能加载 C22 册 —— 须为 `matrix` / `group` tab 定义 sheet 映射，并裁定 C21 / C21-1 是否另立 entry
  - 🔴 裁决须产出「C22 册 **34** 个 sheet 各由哪个 tab 承载」的映射表，或显式声明「不承载」及理由
  - _判据：CC-63、CC-64_
  - **🔴 裁决结果：方案 A**。理由三条：
    ① C21 / C21-1 是**独立底稿**（各自独立 xlsx + 独立 wp_id，经 `wpIdMap` 解析），
       它们的 OO 挂点语义正确，只是传入值用错（传 wpCode 而非 sheet 名）⇒ 属**可局部修正的缺陷**。
    ② C22 册 33 个 ITGC 域码 sheet 已由 `GtC22ControlSheet` 走**结构化视图**承载
       （`itgc-sheet` / `itgc-aux` tab + `checklist-responses` 持久化），不是「缺席业务链路」，
       只是「缺席 OO 链路」；把它改成 OO 整册加载会与既有结构化子页**双轨并存**（D4 踩过的
       「双切换器 + 两侧数据未互通」坑）。
    ③ 方案 B 须裁定 C21 / C21-1 归属（是否另立 entry），属**跨 entry 边界调整**，
       须业务侧拍板 ⇒ 已登记为外部依赖任务 17。
  - **C22 册 34 sheet 承载声明**：主 sheet `C22 IT一般控制测试` 由 `matrix` tab 承载
    （结构化矩阵总览，经 render-config `html_data.matrix`）；33 个 ITGC 域码 sheet 由
    `itgc-sheet` / `itgc-aux` tab 承载（结构化子页 `GtC22ControlSheet`）。
    🔴 **本轮显式声明：C22 册 34 个 sheet 均不经 OO 侧加载**（OO 仅承载 C21 / C21-1 两本独立册）。

- [x] 8. 解析层实现（两方案共用）
  - sheet 名按**原始字面量**匹配，禁 `strip()`、禁全角半角归一化
  - 匹配失败给可诊断信息，区分「册不存在」「sheet 名不存在」「传入值是 wp_code 而非 sheet 名」三种
  - 🔴 **禁用前缀匹配兜底** —— `'C21'` 能前缀匹配到全名，但会掩盖传入值语义错误的根本问题
  - _判据：CC-63、CC-10、CC-52_
  - **实施证据**：`useC22BundleState.ts` 的 `TabDef` 新增 `ooSheetName` 字段（记录册内真实
    sheet 名，带注释说明脱钩机理）；C21 tab = `'C21 具有信息技术专业技能的项目组成员'`、
    C21-1 tab = `'IT 审计发现汇总表'`（**原始字面量**，含真实单空格，未 strip / 未归一化）。
    宿主 OO 挂点 `:sheet-name` 从 `activeDocTab.wpCode` 改为 `activeDocTab.ooSheetName`。
    🔴 **未引入前缀匹配兜底**：映射是显式常量，缺失时传空串由 OO 侧取默认 sheet。
    守卫：`test_oo_mount_passes_real_sheet_name` + `test_tab_def_has_real_sheet_names` +
    前端 `c22ItgcNamespace.spec.ts` 的 2 个 ooSheetName 断言。

- [x] 9. 权威册归属纠正登记（CC-64）
  - 断言 `activeDocTab` 只匹配 `kind === 'c21' || kind === 'c21-1'`（`#L269-274`）
  - 断言 OO 挂点只在 **2 / 4** 个 tab 上渲染（`matrix` / `group` 上 `activeDocTab` 为 `undefined`）
  - 🔴 断言 C21 / C21-1 两本册属 foundation 排除册清单（7 本之一）
  - 🔴 断言本 entry 权威册 `C22 IT一般控制测试.xlsx` **从未被 OO 侧加载过**
  - _判据：CC-64、CC-44_
  - **实施证据**：`TestC22OOMount`（3 test）+ foundation 守卫 `test_excluded_7_books_exist`。
    本轮**保持**该归属事实（方案 A 不改 OO 承载对象），并在任务 7 显式声明理由。

## 阶段 4：命名空间与验证

- [x] 10. 点号命名空间与共享边界（CC-15）
  - 断言 `item_id` 形态为 **`C22.{controlId}.{field}`**（点号分隔，与 canary 那条的连字符三段式不同）
  - 断言构造函数是 `itgcItemId()`，`GtC22ItgcBundle.vue#L323` 与 `GtC22ControlSheet.vue#L265` **共用**
  - 断言 `GtC22ControlSheet.vue#L191` 的 `prefix` 为 `` `C22.${controlId.value}.` ``
  - 🔴 断言这是**有意共享**（`#L312` 注释明写「与子页保持一致」），不是命名冲突
  - 🔴 断言排除理由须精确表述为「无 OO 挂点故不构成独立 sync entry」，**不可**表述为「与本 entry 无关」
  - _判据：CC-15_
  - **实施证据**：`TestC22Namespace`（7 test）+ 前端 `c22ItgcNamespace.spec.ts`（9 test）。
    `itgcItemId(controlId, field)` 现读为 `` `C22.${controlId}.${field}` ``（点号），
    两组件共用同一函数（有意共享）。
  - **排除理由（精确表述）**：`GtC22ControlSheet.vue` **无 OO 挂点故不构成独立 sync entry**，
    但它**是本 entry 的子页**（共用同一 `itgcItemId` 与同一命名空间），改动须同步回归。

- [x] 11. 零分母人造数据验证（CC-60、CC-20）
  - 造人工数据：至少 **2** 个 controlId × **2** 个 field，以暴露键构造错误
  - 测试中显式声明「本 entry 真库分母为 0，验证基于人造数据」
  - 🔴 不得因分母为 0 而跳过验证
  - _判据：CC-60、CC-20_
  - **实施证据**：新建 `audit-platform/frontend/src/components/workpaper/__tests__/c22ItgcNamespace.spec.ts`
    （**9 test 全绿**）。人造数据 = `['SA-7','PE-5']` × `['design-conclusion','exec-conclusion']`
    共 4 键，断言「4 键互不相同」（键构造漏 controlId 或 field 则集合大小 < 4 立即打红）+
    「跨 controlId 不串键」+「同 controlId 跨 field 不串键」+「controlId 含连字符时不破坏点号分段」。
    文件头注释显式声明「本 entry 真库分母为 0，验证基于人造数据」。

- [x] 12. 行身份空分母声明（CC-53、CC-6）
  - 断言本 entry 在 slice `dynamic_row_identity.tables` 中**无条目**（空分母）
  - 断言稳定身份 **4** 处全在本宿主：`:key="r.tab.id"`（`#L497`）/ `tab.id`（`#L642`）/ `activeControlTab.id`（`#L661`）/ `activeDocTab.id`（`#L687`）⇒ tab 级正面样板
  - 断言 `idx` 形参 / N 族 / M 式 / `rowIndex` / `$index` / 熵键 / label 作 key / removeRow / count 键 在本宿主全为 **0**
  - 配变异证明
  - _判据：CC-53、CC-6、CC-20_
  - **实施证据**：`test_stable_identity_in_host`（tab 级 `.id` 稳定身份）+ foundation
    `TestRowIdentityCDomain`（5 test，含类 A / 类 B 双类判定与 `idx_in_item_id == 0`）+
    foundation `TestStructuralZeros`（10 test，removeRow / count 键 / label 作 key 等逐项为 0）。
    变异证明：foundation `test_lowercase_prefix_zero` 用人造正样本 `GtcFake.vue` 验证扫描器非空跑。

- [ ]* 13. 双向读写一致性
  - 结构化视图与 OO 视图读同一权威源
  - OO 侧写入后切回结构化视图能反映写入结果
  - 断言 tab 切换不丢失已填内容（tab 级身份是 `.id`，稳定）
  - _判据：CC-2、CC-6_
  - **状态：代码已改但未实测**。C22 的 OO 侧承载对象是 C21 / C21-1 两本**独立册**
    （方案 A 裁决），其双向一致性依赖后端 per-entry adapter / contract（BP-1 ~ BP-5、BP-7）
    与真实项目数据（本 entry 真库 **0** 行）⇒ 归外部依赖，本轮不标 completed。
    tab 级身份稳定性已由任务 12 静态断言覆盖。

- [x] 14. 回滚路径
  - `capability` 可从 `bidirectional` 退回 `null` 且不留脏数据
  - 🔴 补开关可独立回滚（与 capability 改裁解耦）
  - 回滚后 foundation 基线的 segmented / mode 门控数须同步回退
  - _判据：CC-2、CC-13_
  - **实施证据**：本轮**未改** `capability`（仍为 manifest 现值），故无 capability 回滚面。
    补开关的回滚是**纯前端局部**且与 capability 解耦：删 `el-segmented` 块 + `renderMode` /
    `modeOptions` / `showModeToolbar` 三个声明 + 把 OO 挂点 `v-if` 的 `renderMode === 'online-edit' &&`
    前缀去掉，即逐字回到改造前形态（`renderMode` 默认 `'structured'`，不写任何持久化键
    ⇒ 回滚不留脏数据）。回滚时须同步回退 foundation 的 `test_c22_has_no_segmented` 与
    lane 的 `TestC22SwitchAbsence`（两处同 commit，同任务 5 的纪律）。

## 外部依赖（本轮不可标 completed）

- [ ]* 15. BP-1 ~ BP-5、BP-7、BP-8 七项共有阻塞 —— 见 foundation tasks 29 ~ 35
- [ ]* 16. 本 entry 真实数据 UAT —— 真库 **0** 行，待真实项目数据
- [ ]* 17. 任务 7 的方案裁决若选 B —— 须业务侧确认 C21 / C21-1 与 C22 的底稿边界（跨 entry 归属调整）
  - 本轮已裁方案 A 并显式声明「C22 册 34 sheet 不经 OO 加载」；若业务侧要求 C22 册进 OO 链路，
    须重启本任务并裁定 C21 / C21-1 是否另立 entry。

## 实施汇总（2026-09-28）

| 项 | 值 |
|---|---|
| 完成任务 | **12 / 14**（任务 13 外部依赖、任务 14 已完成） |
| 外部依赖 | 3 条（15 / 16 / 17）+ 任务 13 |
| 改动生产代码 | `GtC22ItgcBundle.vue`（补开关 + sheet 名）· `composables/useC22BundleState.ts`（`TabDef.ooSheetName`） |
| 新建守卫 | `backend/tests/workpaper_sync/test_c22_itgc_lane.py`（5 类 **40** test）· `frontend/.../__tests__/c22ItgcNamespace.spec.ts`（**9** test） |
| 测试结果 | backend C 域 **133 passed / 1 skipped / 0 failed**；前端 **114 passed**；4 文件 **0 diagnostics** |
| 勘误登记 | 任务 2：design.md「`#REF!` 2」实为公式格内计数，`definedName` broken 为 **0**（已现算纠正） |
| 自查修复 | 任务 4：首版引入 **2 个 UX 回归**（C21 默认模式 / C21-1 死条件），已复查发现 + 修复 + 补 **4** 条回归守卫 |

### 本 lane 新增方法论教训（下一轮必带）

- **㉘ 「补开关」必须逐 section 列「改造前默认呈现 → 改造后默认呈现」对照表**（任务 4）：
  只验证「script 里开关存在」会漏掉两类回归 —— ① 默认 mode 让原本直接可见的内容退成占位符
  ② 计算属性声明了某 section 但模板分支顺序使其永不可达（死条件）。
  两者 `getDiagnostics` 与既有单测**都抓不到**，只能靠逐分支复查模板。
- **㉙ 默认值派生函数须在「所有入口」共用**（任务 4）：section setter 与路由 `activateSheet()`
  是两条独立入口，只改一条会留下「路由直入时默认值错」的半修复。
  判据写成「该函数出现次数 ≥ 1 声明 + N 调用」可钉住。
- **㉚ 测试自身的「片段切分边界」不能用与目标同行出现的字符串**（本轮踩）：
  用 `class="c22-section c22-section--doc"` 当 C21-1 分支结束边界，因该 class 与分支条件
  **同行**出现 ⇒ 切出 40 字符空片段、断言假红。边界须取**下一个分支的注释分隔线**。
