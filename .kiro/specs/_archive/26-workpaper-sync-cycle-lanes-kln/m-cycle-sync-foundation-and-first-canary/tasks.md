# M 循环双向回写地基与首张 canary — 任务

> **实施纪律**
> - 🔴 **所有计数一律现算**，与 `design.md` 等值比对；多一处少一处都红。**禁写死**。
> - 🔴 **判据锚点用常量名 / 端点字面量 / 形态特征，禁写死行号**（`.vue` 行号会漂）。
> - 🔴 **行数口径统一 `len(text.split("\n"))`**；与 slice / 删除清册比对时按 MC-29 加偏移量（orphan 11 / live 9 / 基类 1）。
> - 🔴 **M 域文件集 strict 口径**，且 `M10` 正则分支必须排在 `M1` 之前并带 `(?![0-9])`（MC-5）。
> - 🔴 **sheet 名禁 `.strip()`** —— 任何归一化都会让 BP-4 的 6 处丢空格缺陷凭空消失（MC-10）。
> - 🔴 **含正则的核验一律写探针文件**，禁用 `python -c`（shell 传参会把 `\d` 变字面反斜杠）。
> - 🔴 **PG 查询首条失败会使事务 aborted 连带后续全挂**，每条查询独立事务；`checklist_responses` 的列名是 `wp_id`（非 `workpaper_id`），底稿主表是 `working_paper`（单数）。
> - 🔴 **不得抄 L 的四条公式层缺陷**（`#REF!` / 越界 / dangling / 倒挤链）—— M 侧全为 0，抄了就是误立（MC-20）。
> - 既存守卫 `backend/tests/workpaper_sync/test_task55_m_cycle_migration.py` 锁「现状诚实记录」，本 spec 锁「改线后目标态」；重叠处**引用测试名**不重写，且不得抄 L 的测试类名（M 无 `TestProperty20AndProperty3` / `TestProperty23StaticStructure`）。
> - `[ ]*` = 依赖外部供给（BP-1 / BP-2 / BP-3），或真库无业务载荷须先造数据（canary 闭环），本 spec **不承诺完成**。
> - 并发会话正在实施 F3/F4/F5 与 H9 的 spec，其契约与关联产物**一律不碰**。

---

## 阶段 0：口径基线与红判据（Task 0 ~ 5）

- [x] 0. 建立 M 域文件集与扫描口径基线
  - 实现 `m_domain_files()`（strict）：`audit-platform/frontend/src/` 下路径含 `m{1..10}/` 目录段，或文件名匹配 `^(?:use|Gt)?M(?:10|[1-9])(?![0-9])(?:[A-Z]|$|\.)` 的 `.ts`/`.vue`
  - 🔴 **正则顺序自检**：构造 `useM10DualMode.ts` 与 `useM1DualMode.ts` 两个样本，断言各归各类（去掉 `M10` 优先或去掉 `(?![0-9])` 后必红）
  - 🔴 **反向断言**：现算 `loose_only` 差集大小 == **0**（与 L 相反，L 的差集非空撞 G Level-3）
  - 实现 `strip_comments()`：块/行/HTML 注释同长空白替换保留行号，行注释正则用 `(?<!:)//`
  - _Property: MF-P47, MF-P48_

- [x] 1. manifest 与 slice 分歧门（BP-9 / MC-1）
  - 按 slice `selection_rule` 从 `backend/data/workpaper_sync_entry_manifest.json` 现算 entry 集合，与 `independent_entries` 等值比对，断言大小 == 10
  - 断言 manifest 侧 10 条 `capability == 'single_onlyoffice'` / `html_store == 'unresolved'` / **无 `capability_target` 键**
  - 断言 slice 侧 10 条 `capability is None` / `capability_target == 'bidirectional'` / `adapter_id is None` / `html_counterpart_verdict == 'exists'`
  - 🔴 断言守卫方向是「**必须不一致且已登记 BP-9**」：写 `assert manifest_capability != slice_capability`，**不得**写 `assert ==`
  - _Property: MF-P1, MF-P2, MF-P3, MF-P4_

- [x] 2. M0 不存在的两条证据门 + 无 pilot 门
  - ① manifest 全量 entry 现算 `'m0' in entry_id.lower()` == 0；② `backend/wp_templates/_index.json` 里 `M/M0` 条目现算 == 0
  - 🔴 注释写明「M 是**根本不存在**，L 是**有条目但排除**」，两者判据不可互抄
  - 逐文件读 `backend/data/workpaper_sync_contracts/*.json` 的 `review.entry_id`，断言已迁移集合**无一属 M**；集合大小现算（禁写死）
  - 🔴 断言该集合与 manifest `adapter_id` 非空数是**两个不同分母**，并在注释写明 manifest 无 `adapter_registered` 字段
  - _Property: MF-P5, MF-P6_

- [x] 3. 五处口径差自检门（MC-11）
  - 对 ①熵键正则 ②共享基类消费边 ③行数 ④「小计」标签 ⑤OO 兜底分类，各写一对用例：**错误口径会红、正确口径应绿**，并在注释里写明两个口径各自的值
  - 🔴 第 ④ 项的反例必须是 M10 `明细表M10-2` 的 `R10='小计'`（两级表头列名，非行标签）
  - 🔴 第 ⑤ 项断言两套分解：按 dispatch 13（含 `pre_revision_q == 0`）vs 按 hidden 状态 14
  - _Property: MF-P50, MF-P56_

- [x] 4. 行数与计数口径自检（MC-29）
  - 断言 `len(text.split("\n"))` 与 `len(text.splitlines())` 在至少一个真实文件上差 1
  - 建立「现算 vs design 等值」统一断言辅助函数，所有后续 task 复用；辅助函数接受 `offset` 参数用于与 slice 口径比对
  - 🔴 断言偏移量可完全解释：orphan 11 文件 ⇒ 11 · live 9 文件 ⇒ 9 · 共享基类 1 文件 ⇒ 1
  - _Property: MF-P57, MF-P76_

- [x] 5. 结构性零清单与变异证明（MC-20）
  - 逐项现算 19 项结构性零，每项带非空分母或显式「结构性零」标注
  - 🔴 对「M 域 adapter_id 0」「barrel 0」「越界引用 0」「按行身份删 0」四项各构造反例，注入后守卫必红
  - 🔴 公式层四项零（`#REF!` / 越界 / dangling / 倒挤链）的分母声明为**权威册全部公式格 2937**，并在注释写明 L 侧对应值 8 / 0 / 0 / 6
  - _Property: MF-P43, MF-P44, MF-P45, MF-P8_

---

## 阶段 1：载体族与门控形态（Task 6 ~ 11）

- [x] 6. 成对孪生现算门（MC-2）
  - `FRONTEND.rglob('useM*DualMode.ts')` 现算 **20** 个，断言 `== entry 数 × 2`
  - 逐个算 statement-position 生产边与测试边，两者皆 0 者为 orphan（现算 **11**）、否则 live（现算 **9**）；断言 orphan ∪ live 恰是全集且交集为空
  - 🔴 断言 `entries_with_two_orphan_twins == 1`（M9），并在注释写明「抄 L 的 orphan == live 会红」
  - _Property: MF-P16_

- [x] 7. 载体只两种 kind + 无宿主内联门（MC-2）
  - 现算 10 条 `dual_mode_carrier.kind`，断言 `per_entry_wrapper_over_shared_base == 9` + `none == 1`，且**不存在** `child_tab_dedicated_composable`
  - 对 10 个 `GtM*.vue` 逐个断言 `const dualMode = (() =>` 命中 **0**（M 无 K/H 的宿主内联等价实现）
  - _Property: MF-P14, MF-P15_

- [x] 8. 9 条 redeemable 三条件门（MC-13）
  - 对 9 个宿主各验：① 剥注释后有 `el-segmented`；② 以 mode 为条件的 `v-if`/`v-else-if` 命中 > 0；③ `v-else` 分支下真挂 `GtOnlyOfficeSheet`
  - 🔴 三条必须同时成立才判 redeemable
  - _Property: MF-P18_

- [x] 9. inert 恒零门 + M9 无开关门（MC-13）
  - 🔴 断言 `inert == 0` 且删除清册 `inert_switch_blocks_to_remove == 0`，并在注释写明「抄 L 的 `switch_present_but_inert` verdict 会直接判错」
  - 🔴 断言 `segmented_sites_that_are_not_mode_switches` 在 M **为空**（L4 的 `bondBranch` 无对应物）
  - 断言 slice 顶层 `verdict == 'switch_redeemable_but_mis_targeted'` 且 `verdict_is_binary is False` ⇒ **不得**把顶层 verdict 当三值枚举成员比对
  - M9：断言宿主无 `el-segmented`、`ui_toolbar_gate.anchor is None`、两个孪生生产边与测试边均 0
  - _Property: MF-P17, MF-P19_

- [x] 10. 共享基类消费面收缩门（MC-11 / MC-29）
  - 现算窄口径 statement 边总数与其中 M 路径条数，断言扣除后剩余值（**会收缩**）
  - 🔴 两侧都验：窄口径 statement 边 vs 宽口径 token 文件数，差集逐项解释
  - 🔴 与删除清册的 `shared_base_consumers_before/after` 比对时按 Task 4 的 `offset` 口径，注释写明「抄 L 的『删完不变』会红」
  - _Property: MF-P20_

- [x] 11. localStorage 与 legacy 端点门（MC-16）
  - 断言活路径 **0 键**（共享基类把 mode 存内存 `ref`）；键只在 **10 个 orphan**（`m{n}-dual-mode`）且全部按 wpId 分区
  - 🔴 断言 M9 的第二个 orphan `useM9EntryDualMode.ts` **无键**，且其 mode 类型是**类型引用** `WorkpaperRenderMode` 而非字面量联合（扫字面量会漏）
  - 断言 orphan 的 mode 枚举分裂：M1~M4 `'structured' | 'onlyoffice'`（BP-6）· M5~M10 `'html' | 'onlyoffice'`
  - 断言 legacy health 直调点删 orphan 后 == **1**（非 0，基类不删）；`onlyoffice-config` == 0；barrel 文件**不存在** ⇒ 二阶 orphan == 0
  - _Property: MF-P21, MF-P29_

---

## 阶段 2：写路径与门（Task 12 ~ 15）

- [x] 12. TB 发布门端点字面量（MC-3）
  - 按 `audit-determination/publish-to-tb` 扫描，🔴 **必须能匹配反引号模板串**
  - 区分代码行与注释行，断言代码命中恰 **10**（10 个 `useM{n}FormData` 各 1），注释命中为现算值
  - _Property: MF-P9_

- [x] 13. 旧端点全注释门（MC-3）
  - 扫 `trial-balance/writeback`，断言**代码命中 0**、总数现算且全为注释
  - 🔴 注释里写明「只数命中数不判注释会把迁移注释误立成违规」
  - _Property: MF-P10_

- [x] 14. 确认门在调用链上（MC-4）
  - 现算 `ElMessageBox.confirm` 所在文件集与发布门文件集，断言**交集为空**
  - 验「`useM{n}Adjudication` → `useM{n}FormData` 调用边存在且 Adjudication 侧有 confirm」
  - 🔴 注释里写明「写成『同文件有 confirm』会让 10 条全假红」
  - _Property: MF-P11, MF-P12_

- [x] 15. 调整中心联动门
  - 现算 `useAdjustmentCentralSync` 的 import 与调用命中（成对），与 `design.md` 等值
  - _Property: MF-P13_

---

## 阶段 3：SHEET_MAP 基线与历史 sheet 过滤（平台级，Task 16 ~ 23）

- [x] 16. SHEET_MAP 三方等值门（MC-23）
  - 正则从 10 个 `useM{n}EntryDualMode.ts` / `useM9DualMode.ts` 现读 `M{n}_SHEET_MAP` 键值对，断言 `declared == 84`
  - 对每个 value 断言它 ∈ openpyxl 真读的 `wb.sheetnames`，🔴 **不得 strip**；得 `hit == 73` / `missing == 11`
  - 断言三方等值：现算 == slice `m_cycle_form_differences` 的 MD-3 counters == 删除清册 `oo_sheet_map_defects_to_fix_not_delete.counters`
  - _Property: MF-P58_

- [x] 17. 缺陷归属双计数门（MC-23）
  - 断言 `entries_with_defects == 6` 且逐 entry 分解 `M2 3 + M3 1 + M4 1 + M7 1 + M9 2 + M10 3 == 11`
  - 断言 `defect_pairs_in_live_modules == 9` + `defect_pairs_in_orphan_modules == 2`
  - 🔴 断言「BP-4 登记 5 条 entry」与「6 个 entry 有缺陷」**两个数并存**，不得互相覆盖；注释写明 M9 的 MAP 在 orphan 模块里不可达
  - _Property: MF-P59_

- [x] 18. 三种错法分类门（MC-23）
  - 断言 `6 + 4 + 1 == 11`，每类逐条列出「声明值 → 权威册真名」，🔴 列举项数必须与计数相等
  - 🔴 「丢空格」类的判据是「去空格后能命中真 sheet」；不得写成「含空格」（M4 / M9 / M10 只有中间空格，M7 是三重）
  - _Property: MF-P60_

- [x] 19. 反向判据门（证明比对器不是恒判不存在）（MC-23）
  - 断言 `procedure` 键 10 条声明现算 `hit == 3`（M1 不带 `A` / M5 带中间空格 / M8 带中间+尾随）、`miss == 6`、**M6 无此键**
  - 断言 10 条 fallback 字面量 `审定表M{n}-1` **全部命中**真 sheet（现算 10）
  - 🔴 注释写明「`procedure` 一个键 4 种写法 + 1 处缺键 = 逐模块手写无单一真源的铁证」
  - _Property: MF-P61_

- [x] 20. 危害不可见机制门 + M6 侧基线（MC-23）
  - 断言 MAP miss 时回落 fallback、而 fallback 全部命中真 sheet ⇒ 「错的 tab 但不是空白」
  - 断言 AC 6.10 现状 **零 fail closed**
  - 断言 M6 的 6 对全命中、可原样迁移，且 M6 **没有 `procedure` 键**
  - 🔴 新增守卫「SHEET_MAP 的每个 value 必须在权威册 sheet 名集合里」，并使之对现状**红**（登记为待修基线，不强制此刻绿）
  - _Property: MF-P62, MF-P26_

- [x] 21. 历史 sheet 过滤规则与反向判据门（MC-24）
  - 用 importlib 真加载 `backend/app/services/wp_template_finder.py`，逐条断言 `_should_skip_historical_sheet` 的规则集（「修订前」/「（原）」/「(原)」/ `G\d+` + 删除/移至 / `-删除` 结尾 / 「（示例）」或「示例」结尾）
  - 断言对 M 的 4 张历史 sheet 命中 **4/4**（3 张 Q 表 + `针对性测试M8-5-删除`）
  - 🔴 反向判据：正常 sheet 全部保留，样本至少含 `审定表M6-1` / `明细表M10-2` / 一个带前导空格的程序表名
  - _Property: MF-P63, MF-P64_

- [x] 22. 🔴 两侧口径不一致门（MC-24 核心）
  - 现算 `_should_skip_historical_sheet` 的消费方，断言恰 **2** 处（`backend/app/routers/wp_onlyoffice_router.py` · `backend/app/services/wp_template_init_service.py`）
  - 🔴 断言 `backend/app/services/wp_render_config.py` **无**该过滤 ⇒ 两侧 sheet 集合不等
  - 构造对照用例：同一 wpId 下现算 HTML 侧 sheet 列表与 OO 侧 sheet 列表，断言**当前不等**（差额恰为该册的历史 sheet 数），修后相等
  - _Property: MF-P65_

- [x] 23. fail-open 兜底收口 + 单一真源改造（MC-24）
  - 用形态锚点（非行号）定位 `wp_onlyoffice_router.py` 里 `if not sheet_names: sheet_names = all_names`，断言它与 AC 6.10 的 fail-closed 冲突
  - 改造：抽出单一过滤函数供两侧共用；过滤结果为空时 **fail closed**（抛错并指出首个被过滤掉的 sheet 名），不回落全集
  - 🔴 改造后重跑 Task 22 的对照用例，断言两侧 sheet 集合**相等**
  - 🔴 本任务是平台级改动，须同时跑既存后端测试确认零回归
  - _Property: MF-P66_

---

## 阶段 4：模板层基线（Task 24 ~ 30）

- [x] 24. 权威册对账门（MC-9）
  - openpyxl 现读 `backend/wp_templates/M/`，断言 **10** 册 / **102** sheets（无 M0）
  - 断言 10 册的 sha256（hashlib 现算）与 `sheet_count` 与 slice `template_ref` **10/10 等值**
  - _Property: MF-P35_

- [x] 25. sheet 归属双口径门（MC-11）
  - 断言 `102 == HTML 覆盖 89 + OO 兜底 13`
  - 🔴 同时声明按 hidden 状态的 **14**，并写出两套分解（slice 的 13 含 `pre_revision_q == 0`；hidden 的 14 含 3 张 Q 表）
  - _Property: MF-P36_

- [x] 26. sheet 名字符缺陷冻结门（MC-10）
  - 断言 10 册程序表 sheet 名**全部含中间空格**；M2/M3/M7 有前导；M6/M7/M8 有尾随；**M7 是三重**
  - 🔴 构造反例：对同一集合做 `.strip()` 后重跑 Task 16 的比对，断言 6 处丢空格缺陷**凭空消失** ⇒ 证明禁归一化是判据
  - 断言参考页属 **M3** 册、名为 `参考－会计规定`（全角连字符 `－`）；带「删除」的属 M8 且不得据此裁 single
  - _Property: MF-P37, MF-P38_

- [x] 27. definedName 断链基线门（MC-9）
  - 现算 10 册的 `total` / `broken`（🔴 禁写死）并与 `design.md` 等值比对
  - 断言分布形态：**M9 与 M1 显著高于其余 8 册、其余 8 册的 broken 数彼此相同**
  - 🔴 断言解析器能容忍两种新形态不崩：`{#N/A,…,"BBPREP"}`（打印区域宏残留）· `[1]Breakdown!#REF!`（外部工作簿引用）
  - 断言 M1 / M9 另含中文名与跨循环名（至少列出 3 个样本），据此登记「从别的底稿册复制」的结论
  - _Property: MF-P39_

- [x] 28. footer 与幽灵行门（MC-11 / MC-20）
  - 断言 footer 全域 == 单个 `&P/&N`（LC-12 空分母，不宣称通过）
  - 幽灵行用 `max_row − last_value_row` 现算并在注释声明该口径；断言最大值在 M6 `调整分录汇总M6-3`
  - _Property: MF-P40, MF-P41_

- [x] 29. 「合计 / 小计」标签门（MC-11）
  - 现算中文分散对齐写法的处数（`合  计` / `合   计` / `小  计`），并声明它们**业务上正常**、按标签文本精确匹配回写会失配
  - 🔴 扫标签**限 A 列或首个非空列**；构造反例证明不限列会把 M10 `明细表M10-2` 的 `R10='小计'` 当小计行
  - _Property: MF-P42_

- [x] 30. 公式规模与受保护欠账门（MC-26）
  - openpyxl `data_only=False` 现算公式格 **2937** / 带公式 sheet **81**，逐 entry 与 slice `protected_formula_and_classification_summary.per_entry` 等值
  - 🔴 **显式断言 `data_only=True` 会得到 0**（证明扫描口径是判据不是巧合）
  - 现算消费侧两族（公式重算列判据是「`row.<f> = calc*(…)` 赋值」**且**「`String(row.<f>)` 持久化」两条同时成立 + 分类/汇总派生值），与 `design.md` 等值
  - 🔴 断言 M 侧 contract 数 == 0 且 `formula_mask` 声明数 == 0，端到端部分标 `不宣称通过`；**不造 contract、不猜掩码**
  - 断言 M6 册公式格 == **175** 且是 10 册最小值
  - _Property: MF-P70, MF-P71, MF-P27, MF-P46_

---

## 阶段 5：位置化行身份与跨循环冻结（Task 31 ~ 36）

- [x] 31. 位置化四族现算门（MC-8）
  - 分别现算四族：① 渲染键（`rowKey:` / `rowId:` 赋值）② 持久化键（`itemId` 里的 `row-${…}` 段）③ 展示序号（`seq: idx + 1`）④ 熵键
  - 🔴 断言族 ② 与 slice `dynamic_row_identity` **一致**，并在注释写明「与 L 反转 —— L 的 slice 有此盲区、M 的没有」
  - 断言族 ② 配套事实：命中文件 == 10 个 `useM{n}Adjudication.ts` + `useM9OciReconcile.ts`，每个恰 **1** 处 `const n = idx + 1`
  - 族 ④ 两侧口径值都报（本 spec 更宽 vs slice 更窄），不择一
  - _Property: MF-P49, MF-P50_

- [x] 32. 熵键假象与双索引基准门（MC-8）
  - 断言内存行身份是 `${Date.now()}-${Math.random()}` 形态、落库 `item_id` 是 `row-1 … row-N` 纯位置 ⇒ 🔴 只看内存会误判已达标
  - 🔴 真库现算断言存在 **0-based** 行 `M7-disclosure-soe-row-0-policy`，与代码侧 `idx + 1` 的 1-based **并存**
  - 迁移映射须同时处理两种基准；构造用例证明只处理一种会整表错位一行
  - _Property: MF-P51_

- [x] 33. item_id 命名轴门（MC-15）
  - 断言 10 个 `useM{n}FormData.ts` **全有** `const ITEM_PREFIX`（10/10，L 是 6/8）
  - 断言前缀重复轴 **3 : 7**（M1/M2/M3 重复型 vs M4~M10 不重复型），且 field 命名风格**同步分裂**（snake_case vs kebab-case）
  - 断言 `'M10-'.startswith('M1-')` == `False`（键层安全）；文件名层仍靠 Task 0 的正则顺序保证
  - 🔴 断言**两条分界线不重合**：mode 枚举分界 M1~M4 / M5~M10 vs item_id 分界 M1~M3 / M4~M10 ⇒ M4 两侧归属不同
  - _Property: MF-P52 的前置, MC-15_

- [x] 34. removeRow 四元组与零正面样板门（MC-6 / MC-7）
  - 现算 `removeRow` / `handleRemove` 全部命中，逐一登记「函数名 + 首参形态 + 身份来源 + 所属模块」四元组
  - 断言签名种类 == **13**（逐种列出，🔴 列举项数与计数相等）
  - 🔴 断言**按行身份删 == 0**（零正面样板），并在注释写明「L 有 3 个可抄模块，M 必须自建样板」
  - 🔴 断言双套索引映射存在（`rawIdx` / `globalIdx` / `displayIndex` / `tableIndex`），去位置化须同时消除两层
  - _Property: MF-P52_

- [x] 35. derived_total 双正则门（MC-14）
  - 两个正则分别现算 TAIL（`-total` 结尾）与 MID（`-total-` 中置），断言两者都非零
  - 🔴 断言 MID 占绝对多数（与 L 的比例反向），并在注释写明「单正则只扫 TAIL 会漏八成」
  - _Property: MF-P50 的旁证, MC-14_

- [x] 36. 跨循环键冻结门（MC-19）
  - 现算并定位四类生产文件（排除 `__tests__/`）：`useL6Adjustment.ts` · `g2NoteSectionMap.ts` · `factories/createChecklistFormData.ts` · `cycleImportExportRegistry.generated.ts`
  - 🔴 注释写明方向是 **M 被引用**（与 LC-23 的 L 被 H2 引用相反）；generated 文件标为生成物，改键须改生成器
  - 现算已归档披露 spec 的跨循环守卫「M1 键 ∩ K3 键 == ∅」为**未完成**，登记归 lane 3
  - 🔴 现算断言四类消费者**均不引用 `M6-` 前缀键** ⇒ canary 与跨循环依赖正交（禁引用本文档结论）
  - _Property: MF-P53, MF-P54, MF-P55_

---

## 阶段 6：canary 闭环（Task 37 ~ 42）

- [x] 37. canary 判据偏离登记门（MC-18）
  - 真库现算：`item_id` 匹配 M 命名空间的行数 == **6**、`remark` 非空 == **1**、`conclusion` 非空 == **0**
  - 断言那 1 行非空的 `item_id == 'M1-review-session-20260725075149'` 且内容含 `session_id` ⇒ **非业务数据**
  - 断言 M3 / M4 / M5 / M8 / M10 真库行数各 == 0
  - 🔴 在测试文件头注释写明「K/L 硬标准在 M 域无解」+ 五条替代判据，**不得只写结论**
  - _Property: MF-P22, MF-P23, MF-P24_

- [x] 38. canary 选型五条判据门（MC-18 / MC-23 / MC-26 / MC-27）
  - ① 断言 M6 `must_fix_before_wiring` == {BP-1,2,3,5,7,9,10,11}（8 项全公共项），且 M5 / M9 同 8 项、M2 最多
  - ② 断言 M6 SHEET_MAP == 6/6/0 且 declared 是最小值
  - ③ 断言 `switch_is_redeemable is True`
  - ④ 断言公式格 == 175 且是最小值
  - ⑤ 断言 M6 是 3 张 Q 表里唯一正确处理者
  - 排除理由逐条现算：M1（BP-6 + `procedure` 不带 `A` + 重复前缀型）· M5（公式格 193 > 175 且无判据 ⑤）· M9（载体 `none`）
  - _Property: MF-P25, MF-P26, MF-P27, MF-P28_

- [x] 39. M6 orphan 与活封装边界门（MC-2 / MC-16）
  - 断言 `useM6DualMode.ts` 零生产边零测试边、一阶 orphan、自带 `m6-dual-mode` 键（wpId 分区）、可在 step 9 之前直接删
  - 🔴 断言该 orphan **内容完整**（`currentMode` / `modeOptions` / `switchMode` / `checkOOHealth` 全在）⇒ `must_not_wire_to`；改线后宿主不再 import 它
  - 断言 `useM6EntryDualMode.ts` 恰 1 条生产边、委托共享基类、是 `resolveOoSheetName` 唯一实现方 ⇒ **不可在改线前删**（与 L5~L8 相反）
  - _Property: MF-P29, MF-P30, MF-P32_

- [x] 40. BP-7 notice 落位（MC-12）
  - 断言 M 域 notice 符号现算 **0**；AC 1.4 单一真源是 `sync/workpaperEntrySyncNotice.ts` + `sync/GtEntrySyncCapabilityNotice.vue`
  - 在 M6 宿主的模式工具条挂 notice（形态锚点定位，禁写行号）
  - 🔴 **常显摘要 + tooltip 细节双落位**；只放 `el-tooltip` 判不通过（EP teleport + 仅 hover 才进 DOM）
  - _Property: MF-P31_

- [x] 41. BP-10 去位置化改造（canary 范围）
  - 把 `useM6Adjudication.ts` 的 `itemId: …row-${n}…` 换成稳定行身份（采纳删除清册的修法：**内存里已有熵键，直接用它**）
  - 在 contract 里登记 `stable_key` 与旧键的迁移映射；旧键保留只读兼容期
  - 🔴 迁移映射须同时处理 0-based 与 1-based（Task 32）
  - _Property: MF-P51_

- [ ] 42.* canary 端到端闭环（🔴 阻塞：真库无业务载荷）
  - 🔴 本任务标 `[ ]*`：M6 真库唯一行 `M6-4-explanation` 的 `remark` 为 `NULL`，闭环须先造业务载荷
  - 预置动作（不阻塞）：起草 M6 的 per-entry contract 草案，字段映射**只映 `remark`**，`conclusion` 标为不使用（M 域 `conclusion` 非空现算 0）
  - 🔴 **不得用 `M1-review-session-*` 那行冒充业务数据**；不得把本任务标为已完成
  - 依赖 BP-1 / BP-2 / BP-3 外部供给
  - _Property: MF-P34, MF-P33_

---

## 阶段 7：平台工具与收口（Task 43 ~ 45）

- [x] 43. `resolveProcedureSheetKey.ts` 补 M1 / M3 / M7 / M8（MC-28）
  - 现算该文件行数与 M 段条数，断言现有 **6** 条（M2/M4/M5/M6/M9/M10）、缺 4 条
  - 补齐 M1 / M3 / M7 / M8；🔴 **M10 分支排在 M1 之前**并补写顺序约束注释（现状 G 段有、M 段无）
  - 🔴 新增分支的 sheetKey 取值与 openpyxl 真名对齐，**不是**与 SHEET_MAP 现有声明对齐（后者本身错 6 处）
  - 跑 4 个既存测试文件（`.spec.ts` / `.test.ts` / `.j-cycle.spec.ts` / `.m-cycle.spec.ts`），断言全绿且既有断言**不改**，仅新增用例
  - _Property: MF-P74, MF-P75_

- [x] 44. Q 表正确先例抽取为可复用判据（MC-27）—— 2026-10-06 确认已实现：TestQSheetPrecedent 3 passed（dispatch 顺序/空格差异/删除清册排除）+ test_t44 交叉验证 1 passed
  - 复刻 3 个宿主的 dispatch 顺序，对 3 张真 sheet 名各跑一遍，断言 M6 → `skip-q6a`、M8 → `procedure`、M10 → `procedure`
  - 断言 3 张 sheet 真名空格数不一致（M6/M8 双空格、M10 单空格）⇒ 🔴 按字面量比对必须逐张取真名，禁统一模板
  - 断言 wp 码前缀是 **Q** 不是 M；Q 表**不是删除对象**（引删除清册 `excluded_from_plan`）
  - 把 M6 的「先判历史 sheet、再判业务 sheet」顺序抽成共用判据函数，供 lane 2 / lane 3 引用
  - 🔴 注释写明与 MC-24 的关系：后端过滤是**根治**，本条是**前端侧补救**，两者不互相替代
  - _Property: MF-P72, MF-P73_

- [x] 45. 已归档 spec 假绿遗留勘误登记（MC-25）
  - 现读 `_archive/05-business-features/m10-other-equity-instruments/requirements.md`，断言其写「附注披露信息（国有企业）」与真名 `附注披露信息核对（国企）` 逐字不同
  - 现读同 spec 的 `m10_conflict_resolution.md`，断言其「Q10A 修订前 sheet 跳过 ✅ 通过」与 Task 44 实测结论**矛盾**
  - 现读 `_archive/08-disclosure-notes/m-cycle-four-table-extraction-and-disclosure-alignment/tasks.md`，断言**它记对了名** ⇒ 两份已归档 spec 结论不一致
  - 现算该披露 spec 未完成任务数（禁写死）并逐条列出
  - 🔴 **不回填修改已归档 spec**（历史档案 append-only）；勘误只登记在本 spec；SHEET_MAP 的实际修正归 lane 2
  - _Property: MF-P67, MF-P68, MF-P69_
