# L 循环双向回写地基与首张 canary — 设计

## 上游与边界

| 项 | 值 |
|---|---|
| slice | `backend/data/workpaper_sync_l_cycle_manifest_slice.json`（162,120 B，Task 54，冻结 2026-08-31） |
| 既存守卫 | `backend/tests/workpaper_sync/test_task54_l_cycle_migration.py`（**2505** 行 / 14 测试类） |
| 删除计划 | `backend/data/workpaper_sync_l_cycle_deletion_plan.json` |
| 前轮裁决 | FC-1~13 / GC-1~10 / HC-1~16 / IC-1~20 / JC-1~20 / **KC-1~24**（本轮以 KC 为重裁基准） |
| 本 spec entry | `xlsx/gt-l1-short-term-loans`（1 条） |
| canary | `L1-adj-*` 键组，宿主 sheet `审定表L1-1` |

**既存守卫锁的是「现状诚实记录」，本 spec 锁的是「改线后目标态」。** 既存 14 测试类：`TestGuardSelfChecks` / `TestSliceScopeIsRecomputable` / `TestAdjudicationLegality` / `TestHtmlCounterpartIsSourceBacked` / `TestLCycleFormDifferences` / `TestOrphanDualModeInventory` / `TestInertModeSwitch` / `TestSheetGranularityAndRouter` / `TestProperty20AndProperty3` / `TestProperty28DefinitionDriftFailClosed` / `TestProperty23StaticStructure` / `TestProperty69EvidenceAndCounters` / `TestProperty70CrossEntryIsolation` / `TestDeletionPlanConsistency` / `TestParadigmCompliance`。凡本文档判据与之重叠，实施时**引用测试名**，不重写。

## 8 条 entry 权威表（现算自 slice `independent_entries`，非推演）

| entry_id | wp_code | sheets | dispatch | HTML 覆盖 | OO 兜底 | mount | 载体 kind | redeemable | blocked_by |
|---|---|---|---|---|---|---|---|---|---|
| `xlsx/gt-l1-short-term-loans` | L1S | 13 | 13 | 13 | 0 | 2 | shared_cycle_composable | `true` | 1,2,3,5,7,9,**10** |
| `xlsx/gt-l2-interest-payable` | L2I | 8 | 8 | 8 | 0 | 2 | shared_cycle_composable | `true` | 1,2,3,5,7,9 |
| `xlsx/gt-l3-long-term-loans` | L3L | 14 | 13 | 13 | `GT_Custom` | 1 | none | `null` | 1,2,3,5,7,9 |
| `xlsx/gt-l4-bonds-payable` | L4B | 16 | 13 | 15 | `GT_Custom` | 1 | none | `null` | 1,2,3,5,7,**8**,9 |
| `xlsx/gt-l5-long-term-payables` | L5L | 12 | 11 | 11 | `GT_Custom` | 1 | child_tab_dedicated_composable | `false` | 1,2,3,**4**,**6**,7,9 |
| `xlsx/gt-l6-special-payables` | L6S | 9 | 8 | 8 | `GT_Custom` | 1 | child_tab_dedicated_composable | `false` | 1,2,3,4,6,7,9 |
| `xlsx/gt-l7-other-noncurrent-liabilities` | L7O | 8 | 8 | 8 | 0 | 1 | child_tab_dedicated_composable | `false` | 1,2,3,4,6,7,9 |
| `xlsx/gt-l8-financial-expenses` | L8F | 10 | 10 | 10 | 0 | 1 | child_tab_dedicated_composable | `false` | 1,2,3,4,6,7,9 |

**算术自检**：sheets 13+8+14+16+12+9+8+10 = **90** ✓（owned）· HTML 覆盖 13+8+13+15+11+8+8+10 = **86** · OO 兜底 0+0+1+1+1+1+0+0 = **4** · 86 + 4 = 90 ✓ · mount 合计 **10** · dispatch 合计 **84**（L4 的 15 张 HTML sheet 折叠到 13 个 code，差 2 = 两对同码）

🔴 **4 + 4 二分由 slice 自身的 `capability_target_blocked_by` 支撑，非按科目相邻**：L1~L4 含 BP-5 且无 BP-4/BP-6；L5~L8 含 BP-4 + BP-6 且无 BP-5。两集合完全互斥。

## L 与前八轮的形态差异总表（LD-1 ~ LD-8 由 slice 提出，本节给现算复核结论）

| 差异 | slice 的说法 | 本轮现算复核 |
|---|---|---|
| LD-1 载体三分 | `shared_cycle_composable` 2 / `none` 2 / `child_tab_dedicated_composable` 4 | ✅ 属实。K 是二分，**照抄 K 的二分判据必假红** |
| LD-2 L5~L8 死开关 | 4 子 Tab 各 1 `el-segmented`，mode 门控 `v-if` 0、`GtOnlyOfficeSheet` 0 | ✅ 属实，与 G7 两级表头 0/38 同型 |
| LD-3 HTML 对端不经 `useChecklistPersistence` | L 域命中 0，8 条各有 `useL{n}FormData` 直调 `api` | ✅ 属实 ⇒ K 的「每个宿主都 import 共享持久化适配器」判据**照抄必假红** |
| LD-4 宿主消费 FormData 只 2/8 | 仅 L1 / L3 宿主有 import 边 | ⚠️ **须分两口径**：`useL{n}FormData` **模块 8/8 全存在且有活边**（slice 自己的 `html_counterpart_source_refs` 逐条给了读写位置）；「宿主文件直接 import」才是 2。🔴 判据落**前者**，落后者会让 6 条误判「无 HTML 对端」 |
| LD-5 9 个 dual-mode 分居两处 + L3 两份 | `src/composables/` 2 + `components/workpaper/composables/` 7 | ✅ 属实。三值枚举含 `matrix` 的 2 个（L1 / L3 的 `src/composables/` 版），L 域 `matrix` 消费方 0 ⇒ 接上也是死分支；🔴 口径须限 L 域（C22/D2/D4/N1 真有矩阵视图） |
| LD-6 `useL3DualMode` 未按 wpId 分区 | 「其余 8 个是 `STORAGE_KEY_PREFIX + wpId`」 | ⚠️ **结论对，理由错**。未分区的确实只 1 个（`components/workpaper/composables/useL3DualMode.ts`，`const STORAGE_KEY` 无拼接）；但其余 8 个是**两种**形态：`` `${PREFIX}${wpId}` `` 3 个（PREFIX 自带尾连字符）+ `` `${PREFIX}:${wpId}` `` 5 个（`:` 分隔，取键函数名亦不同）。🔴 判据写「key == PREFIX + wpId」会让 5 条假红，须落「**key 含 wpId**」 |
| LD-7 9 本模板 vs 8 entry | 多出 `L0 债务循环函证.xlsx` | ✅ 属实，且排除证据与 K0 不同：靠「第 2 张 sheet 名含 `函证程序表F0A`（F0 而非 L0）+ manifest 里 `'l0'` 命中 0 + `_index.json` 有独立条目故不能靠模板不存在排除」 |
| LD-8 L4 sheet 粒度折叠（唯一） | 16 sheets / 13 dispatch，两对同尾码 | ✅ 属实，且**本轮补出 router 层危害路径**：`'…(分期付息到期一次还本) L4-8'` 带内部空格，与 `'…(到期一次还本付息)L4-8'` **同时 `endswith('L4-8')`**，解析器取第一个 |

### 🔴 slice 的扫描盲区（本轮新增，slice 无对应节）

| 盲区 | slice 值 | 本轮现算 | 性质 |
|---|---|---|---|
| 位置化行身份 | `total_hits: 1`（family_a 1 / b 0 / c 0 / d 9 不计） | 口径 ① 同 slice；**口径 ②（item_id 拼接里的行序号段）另有一整族** | slice 的 `dynamic_row_identity` 口径不覆盖 item_id 拼接。🔴 **不是 slice 记错**——它口径内结论正确 |
| 跨 entry 隔离 | `cross_entry_isolation`「8 个持久化命名空间互异」 | **代码层成立，数据层已污染**（真库有 L2 键落在 `wp_code='G8'` 底稿上） | slice 只扫代码不查库 |

## LC-1 ~ LC-26 共同裁决

> **承接策略**：以 KC-1~24 为基准逐条重裁。KC 各条自带「JC-x / IC-x 在 K 的扩展」标注，故 FC/GC/HC/IC/JC 经 KC 间接覆盖。**KC-17 判 ❌ 不适用，必须显式声明。**
> lane spec 只引用 `LC-x` 编号，不复述内容。

### LC-1 manifest 口径与 BP-9 分歧必须显式登记（KC-1 ✅ 适用）

8 条 entry 的 `manifest_mirror` 一致记 `capability: single_onlyoffice` / `html_store: unresolved`，`why_not_adopted` 明写这两个值来自 **overlay 的 `defaults_by_component.GtOnlyOfficeSheet` 默认值填充，不是逐 entry 裁决**。manifest entry 上**不存在** `capability_target` 字段（那是 slice 自有字段）。🔴 表述为「数据冲突」或「manifest 错了」即违规。

### LC-2 载体族在 L 内部三种并存（KC-2 ⚠️ 扩展）

2 + 2 + 4 = 8 互斥。`switch_is_redeemable` **三态**：`true`（L1/L2，宿主有 mode 门控的 OO 挂点）· `null`（L3/L4，**无开关可谈**）· `false`（L5~L8，开关存在但 inert）。🔴 `null ≠ false`；把「无开关」读成「开关坏了」会让 L3/L4 挂到错误的修复动作上。

### LC-3 写路径与发布门按端点字面量判定，且必须认反引号（KC-3 ✅ 适用）

端点字面量 `audit-determination/publish-to-tb`，真实调用在反引号模板串里。旧端点 `trial-balance/writeback` 在 L 域的命中**全部是迁移记录注释**（`* 此前直调旧端点 …`）⇒ 铁律未违反。🔴 只数命中数不判注释/代码，会把 8 处注释误立成 8 处违规。

### LC-4 发布门全覆盖，但确认门与发布门分居不同文件（KC-4 ⚠️ 变形）

发布门代码命中所在文件集 = 8 个 `useL{n}FormData`；`ElMessageBox.confirm` 所在文件集 = 8 个 `useL{n}Adjudication` + 若干 `L{n}Tab*.vue`；**两集合交集为空（8/8）**。这是分层设计（Adjudication 弹确认 → FormData 发布），不是缺陷。🔴 判据必须落「**调用链上有 confirm**」；写成「同文件有 confirm」会让 8 条全假红。
Adjudication 模块分居两路径：`src/composables/`（L1 / L3）与 `components/workpaper/composables/`（L2 / L4~L8）。

### LC-5 L 域文件集口径必须 strict（KC-22 的 L 特化，独立成条）

宽口径 `L[1-8]` 会撞 **G 循环的 Level-3 公允价值**命名（`useG9L3Reconciliation` / `useG10L3Reconciliation` / `G9TabL3Reconciliation.vue` / `G10TabL3Reconciliation.vue` / `g10L3Cross*`）以及 H2 的跨用文件（`h2L1LoanPull`）。strict 口径 = 路径含 `l{1..8}/` 目录段 **或** 文件名匹配 `^(?:use|Gt)?L[1-8](?:[A-Z]|$|\.)`。🔴 所有比例类判据的分母必须声明口径；混用即判据失效。

### LC-6 行身份族与判别式（KC-6 ✅ 适用）

`removeRow` 首参判别：匹配 `^\$?(?:original)?[Ii]ndex(?::\s*number)?$` 或含 `index` ⇒ **按索引删**；含 `rowId` ⇒ **按行身份删**。L 域实测两者比例严重倾斜（按索引删远多于按行身份删，现算值见 tasks），且能按行身份删的模块**恰好就是**生成了真 rowId 的那三个动态行表模块 ⇒ 二者一一对应，可交叉验证。

### LC-7 removeRow 契约需四元组（KC-7 ✅ 适用）

L 域实测 **9 种签名**：`(index: number)` / `(index)` / `($index)` / `(originalIndex)` / `(rowId: string)` / `(row.rowId)` / `(rowId)` / `(section: L8CutoffSection, index: number)` / `handleRemove($index)` 与 `handleRemove(index: number)`。契约须记「函数名 + 首参形态 + 身份来源 + 所属模块」四元组，禁只记函数名。

### LC-8 item_id 层位置化行身份必须纳入 BP-10（**L 独有**，KC-20 只覆盖其中一小部分）

slice 的 `dynamic_row_identity` 只扫 `rowKey:` / `rowId:` 赋值（`total_hits: 1`）。本轮新增口径 ②：**`item_id` / `itemId` 模板串里的 `row-${…}` / `row${…}` / `-${n}-` 序号段**，另有一整族命中（现算值见 tasks，须按模块列分布）。
🔴 两处次级差异同样要登记：① 分隔符两型（`row-${…}` 带连字符 vs `row${…}` 不带，后者仅两个 L6 Disclosure 组件）；② 索引基准两型（写侧 `${i + 1}` vs 读侧 `${i}`）⇒ 「读写键形态不闭合」候选风险，归 lane 3。

### LC-9 definedName 断链登记（KC-9 ✅ 适用）

owned 4 册有污染（L3 / L5 / L6 / L7），另 4 册（L1 / L2 / L4 / L8）为 0。污染名是**跨软件残留**：`AS2DocOpenMode`（Aspose）· `SAPBEXrevision` / `SAPBEXsysID` / `SAPBEXwbID`（SAP BEX，L5 独有）· `XREF_COLUMN_1/2` · `TextRefCopyRangeCount` · 以及 `AFV` `b` `bs` `CCD` `CDE` `DEX` `EDC` `FAD` `FASD` `FEDC` `RDES` `VFE` `XAP` `XAQ` `XCD` 等无语义短名。与审计业务无关。🔴 四册的 broken 数完全相同 ⇒ 同一污染源，须一次清完。

### LC-10 sheet 名字符缺陷禁归一化（KC-10 ✅ 适用）

三处空格缺陷（L1 程序表前导空格 / L4 程序表**尾随**空格 / L4 账面核对表内部空格）。危害按 router 的解析规则逐条判：
- 前导空格：`endswith(code)` 成立，但**精确匹配失败**
- **尾随空格**：🔴 `endswith(code)` **不成立**，只能靠 `code in name` 兜底命中
- 内部空格：与同码姊妹 sheet **同时** `endswith('L4-8')` ⇒ 解析器取第一个 = BP-8 在 router 层的具体危害

括号全半角混用：附注披露类多为全角 `（）`，但 L4 的四张后续计量/账面核对表用半角 `()`，🔴 **L7 是唯一「同册内附注披露两张 sheet 括号宽度不一致」**（上市公司版全角 vs 国企版半角）⇒ 判据用全角字面量会漏 L7。

### LC-11 `#REF!` 死公式（KC-11 ✅ 适用）

命中集中在 `逾期贷款检查表L1-7` 与 `逾期贷款检查表L3-7` 两张**同构** sheet，公式整条死掉（逾期天数计算 `=IF(#REF!=0,0,IF((#REF!-#REF!)=365,…))`）。其余六册 0。按 LC-25，**两张都要断言**；改一不改二 = 半修。

### LC-12 footer 形态（KC-12 ⚠️ 变形）

K 是三形态（无 SUBTOTAL）；L 是 `&P/&N` **重复两次**型，只出现在三张实质性程序表上，另五册的程序表正常 ⇒ **5 正 3 误**。判据按「footer 串等于单个 `&P/&N`」比对，不按「含 `&P/&N`」（后者两型都过）。

### LC-13 五处扫描误报必须如实登记（KC-13 ✅ 适用；K 是 2 处，L 是 5 处）

| # | 错误口径 | 正确口径 | 修正后 |
|---|---|---|---|
| ① 越界引用 | 拿**本 sheet** 的 `max_row` 去比 `='明细表X'!O23` 里的行号 | 按**引用目标 sheet** 的 `max_row` 判；无 sheet 前缀的才用本 sheet | **0** |
| ② 跨 sheet 断链 | 正则把 `#REF!` 里的 `REF` 当 sheet 名 | 先排除含 `#REF!` 的公式 | **0** |
| ③ 合计漏加小计 | 「SUM 区间内含合计标签行」——对**横向** SUM（span=1）无意义 | 逐行核结构 | **0** |
| ④ OCR | `recognize` 撞 L5 的 `unrecognizedRows`（未确认融资费用） | 排除 `unrecognized*` 等业务词 | 现算值（数量级从百降到十几） |
| ⑤ L 域文件集 | 宽口径 `L[1-8]` 撞 G Level-3 | strict 口径（LC-5） | 现算值 |

🔴 第 ③ 项须写明：`审定表L4-1` 的 `=B11+B16+B17` 是**正确的避重复**（r11 小计 = SUM(r8:r10)、r16 小计 = SUM(r13:r15)、r17 单行、r18 合计 = 小计1 + 小计2 + 单行），**不是缺陷**。
守卫须对每项构造「用错误口径会红、用正确口径应绿」的自检用例。

### LC-14 BP-7 notice 从零补，判据必须写明符号（KC-14 ✅ 适用）

L 域 notice 符号命中 0，8 条 entry 的 `mounts_ac14_notice` 全 `false`。L3~L8 连**宿主锚点都没有**（`ui_toolbar_gate.anchor` 为 `null`，`anchor_absent_because` 已说明），故 notice 须与 sync bridge 的编辑宿主**一并落位**。判据 SHALL 写明所用组件符号名，不得只写「有提示」。

### LC-15 el-segmented 门控形态 + 判据必须先剥注释（KC-15 ✅ 适用）

L 域三形态：宿主门控式 2（L1/L2）· 无开关 2（L3/L4）· 子 Tab inert 4（L5~L8）。
🔴 **L4 有一处 `el-segmented` 但不是模式开关**——它是 `bondBranch` 分期/到期分支选择器，slice 的 `segmented_sites_that_are_not_mode_switches` 已登记。判据须先剥注释（slice 同时给了 `segmented_sites_before_comment_strip` 与 `segmented_sites_in_gate` 两组数，差集即注释里的）。

### LC-16 derived_total 双正则必需（KC-16 ✅ 适用）

两种位置形态都真实存在且都非零：**TAIL**（`-total` 结尾，L2/L3/L4/L5）与 **MID**（`-total-` 中置，L6/L7/L8）。🔴 L8 二次分裂——键少了重复的 sheet 段。L1 无 total 键（其利息测算已改 JSON 整表存储）。单一正则只能覆盖一半。

### LC-17 item_id 命名空间四轴分裂（KC-5 ⚠️ 放大）

| 轴 | 分裂 |
|---|---|
| ① 前缀重复轴 | `L{n}-L{n}-{sheet}-…`（L2/L3/L7 及 L5/L6 部分）vs `L{n}-{sheet}-…`（L4/L8 及 L5 部分） |
| ② field 命名风格 | snake_case · kebab-case · **camelCase** 三种并存 |
| ③ JSON 整表键命名 | 四样：`L3-L3-2-rows`（重复前缀）· `L4-2-rows`（不重复）· `L3-overdue-check-rows`（纯语义名无 sheet 码）· `L2-L2-3-entries`（后缀 `entries` 而非 `rows`） |
| ④ `ITEM_PREFIX` 常量 | 只 6 个模块有；L1 / L2 用**字面量** `startsWith('L{n}-')` |

🔴 判据落「存在 `L{n}-` 前缀过滤（**常量或字面量二者之一**）」；写「8 个模块各有 `ITEM_PREFIX` 常量」会让 L1 / L2 假红。
🔴 **L1 内部还有至少 5 套键前缀**：`L1-adj-`（审定表）· `L1-int-`（利息测算旧 flat）· `L1-L1-5-rows`（利息测算新 JSON）· `L1-chk-`（检查表）· `L1-con-`（结论），外加泛型工厂 `` `L1-${prefix}-${n}-${field}` ``。且 `useL1FormData.ts` 的注释**自曝已知 bug**：「不含 `L1-chk` 前缀 / `L1-con` 前缀等自定义 item_id → 刷新后数据丢失」——真库的 `L1-chk-conclusion` 正属这类。

### LC-18 localStorage 分区三形态（KC-18 ⚠️ 扩展）

`` `${PREFIX}${wpId}` ``（PREFIX 自带尾连字符）· `` `${PREFIX}:${wpId}` ``（`:` 分隔，取键函数名亦不同）· **完全不分区**（`components/workpaper/composables/useL3DualMode.ts` 的 `const STORAGE_KEY`，无拼接）。前八个按 wpId 分区、最后一个不分区 ⇒ 「orphan 不是无害」的实证（它一旦被接上，所有底稿共享一个模式偏好）。
🔴 判据落「**key 含 wpId**」；写「key == PREFIX + wpId」会让 5 条假红。

### LC-19 OCR 借用 D4 端点 + 按 $index 传行（KC-19 ⚠️ 变形）

K 是「两种 URL 形态并存」；L 是**跨循环借端点**——L1 / L3 的贷款合同 OCR 调的是 D4 的 `contract-ocr` 端点（形如 `` `/api/workpapers/${wpId}/d4/contract-ocr` ``）。且上传回调按 **`$index`** 传行 ⇒ 又一处位置化（并入 LC-8 口径 ① 的邻域，但因它不写 item_id，单独登记）。

### LC-20 倒挤减法链（**L 独有**）

模板层双向回写高危点，**两种形态**：
- `L5 '附注披露信息（国企）'`：`='明细表L5-2'!O25 − 本表B12 − B13 − B14 − B15 − B16`（**减本表已列项**）
- `L6 '附注披露（国企）信息'`：`='明细表L6-2'!P20 − 明细表L6-2!P10 … − P14`（**减对方表明细行**）

共性 = **硬编码固定行号窗口**。HTML 侧增行后 OO 侧窗口不扩展 ⇒ 「其他」项吞掉新增金额（漏减，是「合计漏加」的镜像）。🔴 **只出现在「国企」版附注，上市公司版无** ⇒ 变体轴不对称，判据不可只扫一个变体。

### LC-21 审定表结构对偶（KC-21 ⚠️ 对偶）

K 裁的是「审定表可以是纯派生表（无 OO 侧输入位）」；L 的对偶是 **部分列只在小计行有值**：`审定表L4-1` 双期六列（`期初数` / `期末数` 各六列 = 未审数 · 账项调整 · 重分类调整 · 审定数 · 减：一年内到期的应付债券 · 最终审定数），其中「减：一年内到期」列**只在两个小计行有值**，明细行为空。🔴 回写不可按「每行每列皆可写」，否则会写进本不该有值的格。
🔴 同列还有**两种等价写法混用**：审定数列在明细行用 `=SUM(B:D)` 形态、在单行项用 `=B+C+D` 形态 ⇒ 回写解析须同时认两种。

### LC-22 真库跨 entry 键污染（**L 独有**，slice 未记录）

真库 `checklist_responses` 里存在 `item_id` 为 L2 命名空间、但 `wp_id` 指向 **`wp_code='G8'`** 底稿的行（同项目，载荷 581 字节 JSON，含 AJE 测试数据）。
⇒ slice 的 `cross_entry_isolation`「8 个持久化命名空间互异」在**代码层成立**、**数据层已污染**。原因是 slice 只扫代码不查库。
🔴 判据须**查库不只查码**：断言「任一 `item_id ~ '^L{n}-'` 的行，其 `wp_id` 对应的 `wp_code` 必以 `L{n}` 开头」，并把现存违例行登记为待清理数据（本 spec 不动数据，只登记 + 加守卫）。

### LC-23 跨循环键冻结 H2 ← L1（KC-8 ✅ 适用）

`components/workpaper/composables/h2L1LoanPull.ts` 为 **H2-10 一般借款表**从 L1 拉借款测算明细：靠 `wp-id-by-code` 解析 L1 的 wpId → 读 `checklist-responses` → **双路径**（`L1-L1-5-rows` JSON 优先 → 旧 flat `^L1-int-(\d+)-(\w+)$` 按行号归并回退）。
🔴 利率归一化函数靠 **`> 1` 启发式**判「小数 vs 百分数」⇒ 年利率恰为 1（100%）时判错。已知缺陷，登记但不在本 spec 修（属 H2 spec 范围）。
🔴 H2 属**已交付** spec `h2-h6-h10-pilot-cross-reference-lanes` ⇒ 改这两组键前须在 H2 侧同步。canary `L1-adj-*` 与之正交（现算确认不被引用）。

### LC-24 空分母纪律与十项结构性零（KC-24 ✅ 适用）

| # | 项 | 性质 |
|---|---|---|
| 1 | L 前缀契约数 0 | 结构性零（契约目录总数已增长，但无一属 L） |
| 2 | L 域 `adapter_id` 非空数 0 | 结构性零；🔴 须与「全 manifest 非空数」分开算，且声明 manifest **无 `adapter_registered` 字段**（「契约已发」≠「adapter 已注册」） |
| 3 | `parent_duplicate` 0 | 结构性零 ⇒ slice **不含** `parent_duplicate_summary` 节（触发条件不成立时写空节 = additive 死声明） |
| 4 | `excluded_pilot` 0 | 结构性零 |
| 5 | barrel 不存在 | 结构性零 ⇒ **二阶 orphan 恒 0** |
| 6 | 二阶 orphan 0 | 由第 5 项推出，须写明推出关系 |
| 7 | 真实越界引用 0 | **修正后**为零（LC-13 ①） |
| 8 | 真实跨 sheet 断链 0 | **修正后**为零（LC-13 ②） |
| 9 | 真库 `conclusion` 非空 0 | 结构性零 ⇒ L 域只用 `remark`，契约映射时 `conclusion` 是死字段 |
| 10 | L6 / L7 / L8 真库载荷 0 | 结构性零 ⇒ 这三条**不可做 canary**，其闭环验证须标 `[ ]*` 待造数据 |

🔴 每项零 SHALL 附非空分母或显式标「结构性零」；只写「为 0 故通过」即违规。至少第 2 / 5 / 7 项须有变异证明（人为注入反例后守卫必红）。

### LC-25 L1 ↔ L3 模板级同构对（**L 独有**）

L3（长期借款）= L1（短期借款）复制 + 微调，**模板层与代码层双重同构**：

| 层 | 同构证据 |
|---|---|
| 模板 | `利息测算表L{n}-5` 几何与公式数、`逾期贷款检查表L{n}-7`（**含各 4 处 `#REF!`**）、`贷款合同检查L{n}-6`、`征信报告核对表L{n}-4` 逐项等同；仅抵质押资产检查表略异 |
| 代码 | 两份 dual-mode **都叫 `useL3DualMode`**（分居两目录，LD-5）· Adjudication 都在 `src/composables/`（LC-4）· ContractCheck 都借 D4 OCR 端点（LC-19）· `removeRow(originalIndex)` 都在各自 TabDetail（LC-7） |

🔴 **判据须两条都断言**。L1 属本 spec、L3 属 lane 2 ⇒ 两份 spec 的对应 task 必须交叉引用，改一不改二 = 半修。

### LC-26 科目性质分支（KC-23 ✅ 适用）

L1 ~ L7 是**负债类**（资产负债表科目，TB 取期末余额）；🔴 **L8 财务费用是损益类**（TB 取本期发生额，slice 在其 adjudication 里注明 `amount_kind=occurrence`）。四表判据必须按此分支，不可统一按余额口径。

### KC-x 在 L 的不适用项（显式声明）

- **KC-17（prefill sheet 名逐字一致）❌ 不适用**：L 域 `prefill` 命中仅 2 处，不构成 K 那样的 51 条分母 ⇒ **空分母，不宣称通过**。承载该 Property 的既有测试保持原样。🔴 静默沿用即违规。

## canary 裁决：`L1-adj-*`（`审定表L1-1`）

| 硬标准 | `L1-adj-*` | 其余候选被排除的现算理由 |
|---|---|---|
| 真库有非空载荷 | ✅ `item_id ~ '^L1-'` 现算 33 行、`remark` 非空 33 | L2 唯一非空载荷落在 `wp_code='G8'` 底稿（LC-22）· L3/L4/L5 载荷全 `'[]'` 或 `NULL` · L6/L7/L8 **0 行** |
| 在 entry 内 | ✅ `xlsx/gt-l1-short-term-loans` | — |
| 非 parent_duplicate | ✅（L 域全域 0） | — |
| 单 sheet 单键组 | ✅ 全属 `审定表L1-1`，键段单一 `adj` | — |

**宿主 sheet 归属实证**（符号锚点，非行号）：`useL1FormData.ts` 的 `DETERMINATION_SHEET_NAME == '审定表L1-1'`；解析正则 `^L1-adj-(\d+)-(\w+)$`；`useL1Adjudication.ts` 文件头注明「L1-1 短期借款审定表 composable（双期结构）」；发布时 sheet 名固定含子码，由后端 `extract_determination_wp_code` 解出 `L1-1`。

🔴 **`{n}` 的语义 = `categoryIndex`**，对应默认分类「信用 / 抵押 / 保证 / 质押」（对齐源模板顺序）⇒ **有语义锚但仍位置化**：改分类顺序或增删分类即错位。canary 的去位置化动作 = `{n}` → **分类稳定码**，contract 里登记 `stable_key` 与旧键映射，旧键保留只读兼容期。

🔴 **真库载荷只第 1 行有真数值**（其余三行字段值均为 `'0'`）⇒ 闭环用例断言针对第 1 行，不得假设四行都有业务值。
🔴 **字段映射只映 `remark`**；`conclusion` 标为不使用（LC-24 第 9 项）。
🔴 **与 H2 依赖正交**：`h2L1LoanPull.ts` 消费 `L1-L1-5-rows` 与 `L1-int-*`，不含 `L1-adj-*`（此断言须现算，不得引用本文档）。

## 三份 spec 的切分与算术自检

| # | spec 目录 | entry（全名） | 主缺陷集合 |
|---|---|---|---|
| 1 | `l-cycle-sync-foundation-and-first-canary`（本份） | `xlsx/gt-l1-short-term-loans` | BP-5 orphan · **BP-10** 位置化 · 5 套键前缀 · L1↔L3 同构源 · OCR 借 D4 · canary |
| 2 | `l2-l3-l4-orphan-twins-and-sheet-granularity-collapse` | `xlsx/gt-l2-interest-payable` · `xlsx/gt-l3-long-term-loans` · `xlsx/gt-l4-bonds-payable` | BP-5 orphan（含 L3 双份 / L3 不分区）· **BP-8** L4 粒度折叠 · LC-22 真库跨 entry 污染（L2） |
| 3 | `l5-l8-inert-switch-and-child-tab-carriers` | `xlsx/gt-l5-long-term-payables` · `xlsx/gt-l6-special-payables` · `xlsx/gt-l7-other-noncurrent-liabilities` · `xlsx/gt-l8-financial-expenses` | **BP-4** 死开关 · **BP-6** 直调 health · child_tab 载体 · LC-20 倒挤减法链（L5/L6）· LC-26 L8 损益分支 |

**算术自检**：1 + 3 + 4 = **8** ✓ 与 slice `independent_entries` 等值，无重无漏。
**BP 归属无冲突**：BP-5 → spec 1 + spec 2（L1~L4，两份都含，因 canary entry 在 spec 1）· BP-4 / BP-6 → 仅 spec 3 · BP-8 → 仅 spec 2（L4）· BP-10 → 仅 spec 1（L1）· BP-1/2/3/7/9 → 三份共有（平台级 + 全 entry 级）。

## Property 清单（LF-P1 ~ LF-P48）

> 口径：所有计数类 Property 一律**现算**并与本文档等值比对，**禁写死**。分母为空的显式标「不宣称通过」。

| ID | 断言 | 分母 |
|---|---|---|
| LF-P1 | 按 slice `selection_rule` 从 manifest 现算得 8 条，与 `independent_entries` 等值 | 8（非空） |
| LF-P2 | manifest 侧 8 条 `capability == single_onlyoffice` 且 `html_store == unresolved` | 8 |
| LF-P3 | manifest entry 上**不存在** `capability_target` 字段 | 8 |
| LF-P4 | slice 侧 8 条 `capability is None` 且 `capability_target == bidirectional` 且 `adapter_id is None` | 8 |
| LF-P5 | `manifest_mirror.why_not_adopted` 含 overlay 默认值填充的表述（BP-9） | 8 |
| LF-P6 | L 域文件集 strict 口径现算值稳定；宽口径差集恰为 G/H 跨用文件且无一属 L entry | 两侧都验 |
| LF-P7 | `strip_comments()` 同长空白替换，行号不变（自检） | 自检 |
| LF-P8 | 载体 kind 三类互斥求和 == 8 | 8 |
| LF-P9 | `switch_is_redeemable` 三态计数 2/2/4，且 `null` 不被当 `false` | 8 |
| LF-P10 | L5~L8 inert 三条件同时成立（segmented 有 / mode 门控 v-if 0 / `GtOnlyOfficeSheet` 0） | 4 |
| LF-P11 | L1/L2 redeemable：宿主有以 `currentMode` 为条件的 OO 挂点 | 2 |
| LF-P12 | L3/L4 `none`：不 import 任何 `use*DualMode`，唯一 OO 挂点是 `v-else` 兜底 | 2 |
| LF-P13 | 发布门端点字面量代码命中 == 8，且每处在反引号模板串内 | 8 |
| LF-P14 | 旧端点 `trial-balance/writeback` 命中全为注释行 | 现算（非空） |
| LF-P15 | confirm 文件集 ∩ 发布门文件集 == ∅，且 Adjudication→FormData 调用边存在 | 8 |
| LF-P16 | Adjudication 模块 8 个，分居两路径（2 + 6） | 8 |
| LF-P17 | `removeRow` 九种签名全枚举，按索引/按行身份分类计数 | 现算（非空） |
| LF-P18 | 能按行身份删的模块集合 == 生成真 rowId 的模块集合（交叉验证） | 3 |
| LF-P19 | 位置化口径 ①（`rowKey`/`rowId` 赋值）现算值 == slice `total_hits` | 1 |
| LF-P20 | 位置化口径 ②（item_id 拼接序号段）现算值，按模块列分布 | 现算（非空） |
| LF-P21 | 分隔符两型（`row-${}` / `row${}`）各自非空，后者仅两个 L6 Disclosure 组件 | 两侧都验 |
| LF-P22 | 索引基准两型（写 `${i+1}` / 读 `${i}`）同时存在，登记为不闭合候选 | 现算 |
| LF-P23 | 9 册 100 sheets；owned 90；8 册 sha256 与 sheet_count 与 `template_ref` 等值 | 8 |
| LF-P24 | L0 排除靠三条证据（manifest `'l0'` 命中 0 / `_index.json` 有条目 / 第 2 张 sheet 名含 `函证程序表F0A`） | 3 |
| LF-P25 | `GT_Custom` hidden sheet 数 == OO 兜底数，且逐 entry 对应 | 4 |
| LF-P26 | sheet 名三处空格缺陷逐字断言，**未经归一化** | 3 |
| LF-P27 | 尾随空格那处 `endswith(code)` 为 **False**、`code in name` 为 True（两侧都验） | 1 |
| LF-P28 | 两张同码 sheet **同时** `endswith('L4-8')`，解析取第一个 | 2 |
| LF-P29 | L7 同册附注披露两张 sheet 括号宽度不一致（全角 vs 半角） | 1 |
| LF-P30 | `#REF!` 死公式集中在 `逾期贷款检查表L1-7` 与 `L3-7`，其余六册 0 | 8 册 |
| LF-P31 | definedName：4 册污染 / 4 册为 0；四册 broken 数相同；L1 册 0/0/0 | 8 册 |
| LF-P32 | footer：重复两次型恰 3 处，另 5 册程序表为单个 `&P/&N` | 8 |
| LF-P33 | 幽灵行按 `max_row − last_value_row` 现算，口径已声明 | 90 |
| LF-P34 | derived_total 双正则：TAIL 与 MID 各自非空，L8 少重复 sheet 段 | 两侧都验 |
| LF-P35 | `ITEM_PREFIX` 常量 6 个 + 字面量 2 个 == 8；判据按「二者之一」 | 8 |
| LF-P36 | 前缀重复轴两组各自非空 | 8 |
| LF-P37 | JSON 整表键四种命名形态各自命中 | 4 |
| LF-P38 | localStorage 三形态计数 3/5/1，判据按「key 含 wpId」 | 9 |
| LF-P39 | OCR 修正口径后命中集合只含 L1/L3 的 ContractCheck，端点含 `d4/contract-ocr` | 2 |
| LF-P40 | 倒挤减法链两形态各自非空，且只在「国企」版附注 | 两侧都验 |
| LF-P41 | `审定表L4-1` 的「减：一年内到期」列只在小计行有值；两种等价写法同时存在 | 两侧都验 |
| LF-P42 | 真库：`item_id ~ '^L{n}-'` 的行其 `wp_code` 必以 `L{n}` 开头；现存违例被登记 | 现算（非空，含违例） |
| LF-P43 | 真库 `conclusion` 非空数 == 0（结构性零 + 变异证明） | 45 |
| LF-P44 | `h2L1LoanPull` 双路径存在；不引用 `L1-adj-` | 两侧都验 |
| LF-P45 | 十项结构性零逐项现算，第 2/5/7 项有变异证明 | 10 |
| LF-P46 | 共享载体 `useCycleHtmlOoDualMode` 窄生产边 3 → 改线后 1；Shell 仍被 Router 消费 ⇒ 不可删 | 3 |
| LF-P47 | 共享基类 `useWorkpaperEntryDualMode` 的 L 域贡献 == 0 ⇒ 消费面不变 | 现算（非空） |
| LF-P48 | 行数口径统一 `len(text.split("\n"))`；`splitlines()` 结果恒少 1（自检） | 自检 |

**不宣称通过**：KC-17 对应的 prefill Property（L 域分母为空），承载者保持既有测试原样。
