# L 循环双向回写地基与首张 canary — 任务

> **实施纪律**
> - 🔴 **所有计数一律现算**，与 `design.md` 等值比对；多一处少一处都红。**禁写死**。
> - 🔴 **判据锚点用常量名 / 端点字面量 / 形态特征，禁写死行号**（`.vue` 行号会漂）。
> - 🔴 **行数口径统一 `len(text.split("\n"))`**（LF-P48）。
> - 🔴 **L 域文件集必须 strict 口径**（LC-5），宽口径会撞 G 循环 Level-3 公允价值命名。
> - 🔴 **含正则的核验一律写探针文件**，禁用 `python -c`（shell 传参会把 `\d` 变字面反斜杠）。
> - 🔴 **PG 查询首条失败会使事务 aborted 连带后续全挂**，每条查询独立事务；`checklist_responses` 的列名是 `wp_id`（非 `workpaper_id`），底稿主表是 `working_paper`（单数）。
> - 既存守卫 `backend/tests/workpaper_sync/test_task54_l_cycle_migration.py` 锁「现状诚实记录」，本 spec 锁「改线后目标态」；重叠处**引用测试名**不重写。
> - `[ ]*` = 依赖外部供给（BP-1 / BP-2 / BP-3），本 spec **不承诺完成**。
> - 并发会话正在实施 F3/F4/F5 与 H9 的 spec，其契约与关联产物**一律不碰**。

---

## 阶段 0：口径基线与红判据（Task 0 ~ 4）

- [x] 0. 建立 L 域文件集与扫描口径基线
  - 实现 `l_domain_files()`（strict）：`audit-platform/frontend/src/` 下路径含 `l{1..8}/` 目录段，或文件名匹配 `^(?:use|Gt)?L[1-8](?:[A-Z]|$|\.)` 的 `.ts`/`.vue`
  - 🔴 **两侧都验**：断言 strict 现算值；并断言宽口径 `L[1-8](?:[A-Z]|FormData|DualMode|Tab)` 的差集恰为 G/H 跨用文件（`useG9L3Reconciliation` / `useG10L3Reconciliation` / `G9TabL3Reconciliation.vue` / `G10TabL3Reconciliation.vue` / `g10L3Cross*` / `h2L1LoanPull` 及其 spec），且断言其中无一属 L entry
  - 实现 `strip_comments()`：块/行/HTML 注释同长空白替换保留行号，行注释正则用 `(?<!:)//`
  - _Property: LF-P6, LF-P7_

- [x] 1. manifest 与 slice 分歧门（BP-9 / LC-1）
  - 按 slice `selection_rule` 从 `workpaper_sync_entry_manifest.json` 现算 entry 集合，与 `independent_entries` 等值比对
  - 断言 manifest 侧 8 条 `capability == 'single_onlyoffice'` / `html_store == 'unresolved'` / **无 `capability_target` 键**
  - 断言 slice 侧 8 条 `capability is None` / `capability_target == 'bidirectional'` / `adapter_id is None`
  - 断言 `manifest_mirror.why_not_adopted` 含 overlay 默认值填充的表述
  - _Property: LF-P1, LF-P2, LF-P3, LF-P4, LF-P5_

- [x] 2. L0 册排除的三条证据门（LD-7）
  - ① manifest 全量 entry 现算 `'l0' in entry_id.lower()` 命中 == 0
  - ② `backend/wp_templates/_index.json` 里 L0 **有**独立条目（故不能靠「模板不存在」排除）
  - ③ openpyxl 现读 L0 册第 2 张 sheet 名，断言含 `函证程序表F0A`
  - _Property: LF-P24_

- [x] 3. 五处扫描误报的自检门（LC-13）
  - 对 ①越界 ②跨 sheet 断链 ③合计漏加 ④OCR ⑤L 域文件集，各写一对用例：**错误口径会红、正确口径应绿**
  - 断言修正后 ①②③ 均为 **0**；④⑤ 现算值与 `design.md` 等值
  - 🔴 在代码注释里写明 `审定表L4-1` 的 `=B11+B16+B17` 是正确避重复，不得列为缺陷
  - _Property: LF-P26 的前置, LC-13_

- [x] 4. 行数与计数口径自检
  - 断言 `len(text.split("\n"))` 与 `len(text.splitlines())` 在至少一个真实文件上差 1（证明口径生效）
  - 建立「现算 vs design 等值」的统一断言辅助函数，所有后续 task 复用
  - _Property: LF-P48_

---

## 阶段 1：载体族与门控形态（Task 5 ~ 9）

- [x] 5. 载体三分现算门（LC-2）
  - 现算 8 条 `dual_mode_carrier.kind`，断言三类互斥求和 == 8（2 / 2 / 4）
  - 断言 `switch_is_redeemable` 三态计数 2 / 2 / 4，且 `null` 与 `false` **分开统计**
  - _Property: LF-P8, LF-P9_

- [x] 6. L5~L8 inert 三条件门（LC-2 / LC-15）
  - 对 4 个子 Tab 各验：① 剥注释后有 `el-segmented`；② 以 mode 为条件的 `v-if`/`v-else-if`/`v-show` 现算 **0**；③ 文件内 `GtOnlyOfficeSheet` 命中 **0**
  - 🔴 三条必须同时成立才判 inert；缺一即不成立
  - _Property: LF-P10_

- [x] 7. L1/L2 redeemable 对照门
  - 验宿主模板存在以 `currentMode` 为条件的 `GtOnlyOfficeSheet` 挂点（形态锚点，不写行号）
  - _Property: LF-P11_

- [x] 8. L3/L4 `none` 门 + L4 bondBranch 排除（LC-15）
  - 验 L3/L4 宿主不 import 任何 `use*DualMode`，唯一 OO 挂点是 `v-else` 兜底（服务 `GT_Custom`）
  - 🔴 断言 L4 剥注释后的 `el-segmented` 站点集合与 slice 的 `segmented_sites_that_are_not_mode_switches` 一致（`bondBranch` 分支选择器**不是**模式开关）
  - _Property: LF-P12_

- [x] 9. 共享件消费面门（LC-2 邻域）
  - 现算 `useCycleHtmlOoDualMode.ts` 的窄生产边 == 3（L1 宿主 + L2 宿主 + `shared/CycleStandaloneProcedureShell.vue`），断言改线后剩 **1**
  - 断言 Shell 自身仍被 `GtCycleAProgramRouter.vue` 消费 ⇒ 🔴 **该共享件是「部分收缩」不可删**
  - 现算 `useWorkpaperEntryDualMode.ts` 的 L 域贡献 == **0** ⇒ 消费面不变
  - _Property: LF-P46, LF-P47_

---

## 阶段 2：键与行身份（Task 10 ~ 16）

- [x] 10. item_id 前缀过滤门（LC-17 ④）
  - 现算 8 个 `useL{n}FormData` 的前缀载体，断言「常量 6 + 字面量 2 == 8」
  - 🔴 判据落「存在 `L{n}-` 前缀过滤（常量或字面量二者之一）」；写「各有 `ITEM_PREFIX` 常量」会让 L1/L2 假红
  - _Property: LF-P35_

- [x] 11. 前缀重复轴与 JSON 整表键命名门（LC-17 ①③）
  - 断言 `L{n}-L{n}-…` 与 `L{n}-…` 两组各自非空
  - 断言 JSON 整表键四种形态各自命中（重复前缀 / 不重复 / 纯语义名 / `entries` 后缀）
  - _Property: LF-P36, LF-P37_

- [x] 12. 位置化两口径并报门（LC-8 / Requirement 11）
  - 口径 ①：`rowKey:` / `rowId:` 赋值，现算值与 slice `dynamic_row_identity.total_hits` 等值
  - 口径 ②：`item_id` / `itemId` 模板串里 `row-${…}` / `row${…}` / `-${n}-` 序号段，**按模块列分布**并现算总数
  - 🔴 断言两口径结果**不相等**（证明 ② 是新增覆盖面，非重复计数）
  - _Property: LF-P19, LF-P20_

- [x] 13. 位置化次级差异门（LC-8）
  - 断言分隔符两型各自非空，且 `row${…}`（无连字符）仅出现在两个 L6 Disclosure 组件
  - 断言索引基准两型（写 `${i + 1}` / 读 `${i}`）同时存在，登记为「读写键形态不闭合」候选（归 lane 3，本 spec 只登记）
  - _Property: LF-P21, LF-P22_

- [x] 14. removeRow 九签名枚举门（LC-6 / LC-7）
  - 枚举 strict 口径下全部 `removeRow` / `handleRemove` 签名，按「按索引删 / 按行身份删 / 其他」分类计数
  - 🔴 交叉验证：能按行身份删的模块集合 **等于** 生成真 rowId 的三个动态行表模块集合
  - 契约记四元组（函数名 + 首参形态 + 身份来源 + 所属模块）
  - _Property: LF-P17, LF-P18_

- [x] 15. derived_total 双正则门（LC-16）
  - TAIL（`-total` 结尾）与 MID（`-total-` 中置）**两个正则都跑**，断言各自非空
  - 断言 L8 的键少了重复 sheet 段；断言 L1 无 total 键
  - _Property: LF-P34_

- [x] 16. localStorage 三形态门（LC-18）
  - 现算 9 个 dual-mode 的 storage 键构造，分类计数 3 / 5 / 1
  - 🔴 判据落「**key 含 wpId**」；断言不分区的那 1 个是 `components/workpaper/composables/useL3DualMode.ts` 的 `const STORAGE_KEY`
  - 断言三值枚举含 `matrix` 的 2 个模块在 **L 域**消费方为 0（口径限 L 域）
  - _Property: LF-P38_

---

## 阶段 3：写路径与发布门（Task 17 ~ 19）

- [x] 17. 发布门端点字面量门（LC-3）
  - 扫 `audit-determination/publish-to-tb`，**必须能匹配反引号模板串**
  - 区分代码行 / 注释行，断言代码命中 == **8**（8 个 `useL{n}FormData` 各 1）
  - 扫旧端点 `trial-balance/writeback`，断言命中全为注释 ⇒ 铁律未违反
  - _Property: LF-P13, LF-P14_

- [x] 18. 二次确认门在调用链上（LC-4）
  - 现算 confirm 文件集与发布门文件集，断言 **交集为空**
  - 验「`useL{n}Adjudication` → `useL{n}FormData` 调用边存在 且 Adjudication 侧有 `ElMessageBox.confirm`」
  - 🔴 判据不得写成「同文件有 confirm」
  - _Property: LF-P15_

- [x] 19. Adjudication 模块分居两路径门（LC-4 / LC-25）
  - 断言 8 个 Adjudication 模块：`src/composables/` 2（L1 / L3）+ `components/workpaper/composables/` 6
  - 🔴 登记这一分居是 L1↔L3 同构对的代码层证据之一
  - _Property: LF-P16_

---

## 阶段 4：模板层基线（Task 20 ~ 24）

- [x] 20. 9 册几何与摘要对账（LC-24 邻域）
  - openpyxl 现读 `backend/wp_templates/L/`，断言 9 册 / 100 sheets / owned 90
  - 断言 8 册 sha256 与 sheet_count 与 slice `template_ref` 等值
  - 断言 `GT_Custom` hidden sheet 数 == OO 兜底数，且逐 entry 对应
  - _Property: LF-P23, LF-P25_

- [x] 21. sheet 名字符缺陷门（LC-10）
  - 逐字断言三处空格缺陷，🔴 **未经归一化**
  - 🔴 **两侧都验**尾随空格那处：`endswith(code)` 为 **False** 且 `code in name` 为 True
  - 断言两张同码 sheet **同时** `endswith('L4-8')`
  - 断言 L7 同册附注披露两张 sheet 括号宽度不一致
  - _Property: LF-P26, LF-P27, LF-P28, LF-P29_

- [x] 22. `#REF!` 与 definedName 基线（LC-11 / LC-9）
  - 断言 `#REF!` 集中在 `逾期贷款检查表L1-7` 与 `逾期贷款检查表L3-7`，其余六册 0
  - 断言 definedName：4 册污染 / 4 册为 0，四册 broken 数相同，**L1 册 0/0/0**
  - 断言污染名集合含 `AS2DocOpenMode` 与 `SAPBEX*`（跨软件残留证据）
  - _Property: LF-P30, LF-P31_

- [x] 23. footer 与幽灵行基线（LC-12）
  - 断言 footer 重复两次型恰 3 处，另 5 册程序表为单个 `&P/&N`；判据按**等于**不按**含**
  - 按 `max_row − last_value_row` 现算幽灵行，声明口径
  - _Property: LF-P32, LF-P33_

- [x] 24. 倒挤减法链与审定表结构登记（LC-20 / LC-21）
  - 断言倒挤减法链两形态（减本表 / 减对方表）各自非空，且**只在「国企」版附注**
  - 断言 `审定表L4-1` 的「减：一年内到期」列只在小计行有值；明细行为空
  - 断言审定数列两种等价写法（`=SUM(B:D)` 形态 / `=B+C+D` 形态）同时存在
  - 🔴 本 spec **只冻结基线不修模板**；L5/L6 的修复归 lane 3、L4 归 lane 2
  - _Property: LF-P40, LF-P41_

---

## 阶段 5：canary 闭环（Task 25 ~ 30）

- [x] 25. canary 资格现算门（Requirement 5 / LC-22）
  - 真库现算 `item_id ~ '^L[1-8]-'` 的逐 cyc 分布（行数 / wp 数 / `remark` 非空 / `remark` NULL / `conclusion` 非空）
  - 断言 `L1-adj-*` 四条硬标准全过；逐条给出其余候选被排除的现算理由
  - 🔴 断言 L6/L7/L8 真库 **0 行** ⇒ 这三条不可做 canary
  - _Property: LF-P42, LF-P43_

- [x] 26. canary 宿主 sheet 归属门（Requirement 5.3）
  - 断言 `useL1FormData.ts` 的 `DETERMINATION_SHEET_NAME` 值等于 `'审定表L1-1'`（按**常量名**取值，不写行号）
  - 断言 `L1-adj-` 解析正则形如 `^L1-adj-(\d+)-(\w+)$`
  - 断言后端从 sheet 名解子码的函数 `extract_determination_wp_code` 真实存在
  - _Property: LF-P13 邻域_

- [x] 27. canary 与 H2 依赖正交门（LC-23 / Requirement 12）
  - 现算 `h2L1LoanPull.ts` 引用的 L1 键集合，断言含 `L1-L1-5-rows` 与 `L1-int-*`、**不含 `L1-adj-`**
  - 断言其双路径（JSON 优先 → 旧 flat 正则回退）都在
  - 登记利率归一化的 `> 1` 启发式为已知缺陷（不在本 spec 修）
  - 冻结这两组键：本 spec 内不改动
  - _Property: LF-P44_

- [x] 28. canary contract 起草（去位置化 + 字段映射）
  - `{n}` → **分类稳定码**（信用 / 抵押 / 保证 / 质押），contract 登记 `stable_key` 与旧键映射，旧键保留只读兼容期
  - 字段映射**只映 `remark`**；`conclusion` 标为不使用
  - 🔴 契约文件命名与归属：`review.entry_id == 'xlsx/gt-l1-short-term-loans'`，落 `backend/data/workpaper_sync_contracts/`
  - 🔴 并发会话正在实施 F3/F4/F5 与 H9 契约，**不碰其文件**
  - _Property: LF-P43 邻域_

- [x] 29. canary 闭环用例（真库载荷）
  - 断言只第 1 行有真数值、其余三行字段值为 `'0'`；🔴 用例断言针对第 1 行，不假设四行都有业务值
  - HTML 侧改值 → 发布门 → TB 落库 → OO 侧读回，逐步断言
  - _Property: LF-P42_

- [ ] 30.* canary 的 OO 侧真实验证（BP-3）
  - 依赖真实 OnlyOffice 9.4 探针对本 entry 执行，本 spec **不承诺完成**
  - _Property: 不宣称通过_

---

## 阶段 6：BP 收口与结构性零（Task 31 ~ 36）

- [x] 31. L1 的 blocked_by 逐项归位（Requirement 6）
  - 现算 L1 的 `capability_target_blocked_by` == 7 项，断言 L1 是唯一含 **BP-10** 的
  - 逐项标注归属：BP-1/2/3 → `[ ]*` 外部供给；BP-5 → Task 32；BP-7 → Task 33；BP-9 → Task 1；BP-10 → Task 12/13
  - _Property: LF-P1 邻域_

- [x] 32. BP-5 orphan 收口（L1 侧）
  - 现算 L1 的 orphan 孪生 = `src/composables/useL1DualMode.ts`，断言零生产消费边
  - 断言它是一阶 orphan（barrel 不存在 ⇒ 二阶恒 0）
  - 按删除计划确认可在 step 9 之前删；删前后测试全绿；独立 commit
  - _Property: LF-P45 第 5/6 项_

- [x] 33. BP-7 notice 落位（L1 侧）
  - 断言 L 域 notice 符号命中 0、8 条 `mounts_ac14_notice == false`
  - notice 与 sync bridge 编辑宿主**一并落位**；判据写明组件符号名
  - 🔴 L3~L8 连宿主锚点都没有（`ui_toolbar_gate.anchor is None`），本 spec 只做 L1
  - _Property: LC-14_

- [x] 34. 十项结构性零现算 + 变异证明（LC-24）
  - 逐项现算并标「结构性零」或给非空分母
  - 🔴 至少对「L adapter 0」「barrel 0」「真实越界 0」构造反例，证明守卫非空跑
  - 🔴 契约目录总数**现算禁写死**；`adapter_id` 分「全 manifest」与「L 域」两个分母；声明 manifest 无 `adapter_registered` 字段
  - _Property: LF-P45_

- [x] 35. LC-x 引用闭合性与 KC-17 不适用声明（Requirement 2 / 9）
  - 断言 LC-1 ~ LC-26 无缺号无重号，且每条至少被一份 spec 引用
  - 🔴 显式声明 **KC-17 ❌ 不适用**，理由写「分母为空」而非「L 没这个问题」
  - 断言所有「不宣称通过」项都指明了承载者
  - _Property: 全 Property 清单自检_

- [x] 36. L1↔L3 同构对交叉引用（LC-25）
  - 断言模板层同构证据（利息测算表 / 逾期贷款检查表含各 4 处 `#REF!` / 贷款合同检查 / 征信报告核对表）
  - 断言代码层同构证据（两份同名 dual-mode / Adjudication 同目录 / ContractCheck 同借 D4 OCR / `removeRow(originalIndex)` 同在 TabDetail）
  - 🔴 在本 spec 与 lane 2 的对应 task 之间建立交叉引用；改一不改二 = 半修
  - _Property: LF-P30, LF-P16_
