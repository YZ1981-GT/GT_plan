# L2 / L3 / L4 孤儿孪生与 sheet 粒度折叠车道 — 设计

## 上游与边界

| 项 | 值 |
|---|---|
| 共同裁决出处 | `.kiro/specs/l-cycle-sync-foundation-and-first-canary/design.md` 的 **LC-1 ~ LC-26** |
| 共同 Property 出处 | 同上的 **LF-P1 ~ LF-P48** |
| slice | `backend/data/workpaper_sync_l_cycle_manifest_slice.json` |
| 既存守卫 | `backend/tests/workpaper_sync/test_task54_l_cycle_migration.py` |
| 本 spec entry | `xlsx/gt-l2-interest-payable` · `xlsx/gt-l3-long-term-loans` · `xlsx/gt-l4-bonds-payable`（3 条） |

🔴 **本 spec 不复述任何 LC-x 的判据内容。** 出现 `LC-x` 即指 foundation 处的裁决原文。本文档只写三条 entry 的**专属事实**与**本车道的落地方案**。

## 为什么这三条合并（切分依据）

slice 自身 `capability_target_blocked_by` 的集合关系：

```
含 BP-5、不含 BP-4/BP-6：{L1, L2, L3, L4}   ← canary entry L1 归 foundation，余三条归本 spec
含 BP-4+BP-6、不含 BP-5：{L5, L6, L7, L8}   ← 归 lane 3
```

两集合**完全互斥**（现算可验）。L4 额外含 **BP-8**，是全 L 域唯一的 sheet 粒度折叠 entry。

⚠️ 注意：本 spec 的载体族**不齐整**（L2 是 `shared_cycle_composable`、L3/L4 是 `none`），这是**故意的**——切分按缺陷集合（BP 归属）而非按载体形态，因为 BP-5 的收口动作（删 orphan）与载体形态无关。载体形态差异按 **LC-2** 分支处理。

## 三条 entry 专属事实

### L2（`xlsx/gt-l2-interest-payable`）

| 维度 | 事实 |
|---|---|
| 载体 | `shared_cycle_composable`，与 L1 共用 `useCycleHtmlOoDualMode.ts`；`switch_is_redeemable == true` |
| orphan 孪生 | `components/workpaper/composables/useL2DualMode.ts`（1 份） |
| 前缀载体 | 🔴 **无 `ITEM_PREFIX` 常量**，用字面量 `startsWith('L2-')`（引用 LC-17 ④） |
| 行身份 | ✅ **正面样板**：`useL2Detail` / `useL2VoucherCheck` 两个模块生成真 rowId，是全 L 域唯二/唯三能按行身份删的模块之一（引用 LC-6） |
| derived_total | TAIL 型（引用 LC-16） |
| 真库 | 🔴 三行，唯一非空载荷**落在 `wp_code='G8'` 底稿上**（LC-22）⇒ 闭环须标 `[ ]*` |
| 模板缺陷 | 两张附注披露的裸 IF 密度最高（各 48/70）· 程序表 footer 重复两次（LC-12） |

### L3（`xlsx/gt-l3-long-term-loans`）

| 维度 | 事实 |
|---|---|
| 载体 | `none`；`switch_is_redeemable == null`（**无开关可谈，非 false**，引用 LC-2） |
| orphan 孪生 | 🔴 **两份**：`src/composables/useL3DualMode.ts`（三值含 `matrix`）+ `components/workpaper/composables/useL3DualMode.ts`（二值，**且不按 wpId 分区**，引用 LC-18） |
| OO 兜底 | 1 张 `GT_Custom`（hidden），是 `v-else` 兜底渲染器而非模式切换 |
| 与 L1 的同构 | 🔴 模板层 4 张 sheet 逐项等同（含 `逾期贷款检查表L3-7` 的 4 处 `#REF!`）+ 代码层四项同构（引用 **LC-25**） |
| definedName | 有污染，broken 数与 L6/L7 相同；**L1 册为 0** ⇒ 污染另有来源，不是从 L1 复制 |
| OCR | `L3TabContractCheck.vue` 借 D4 端点、按 `$index` 传行（引用 LC-19） |
| 行身份 | `useL3VoucherCheck` 生成真 rowId（正面样板）；但 `L3TabDetail.vue` 用 `removeRow(originalIndex)`（负面，与 L1 同形） |
| 真库 | 六行：四行 `NULL` + 两行 `'[]'` ⇒ 无有效载荷，闭环须标 `[ ]*` |
| 幽灵行 | `审定表L3-1` 是全 L 域最大（引用 LC-12 邻域口径） |

### L4（`xlsx/gt-l4-bonds-payable`）

| 维度 | 事实 |
|---|---|
| 载体 | `none`；`switch_is_redeemable == null` |
| orphan 孪生 | `components/workpaper/composables/useL4DualMode.ts`（1 份） |
| **BP-8 粒度折叠** | 🔴 16 sheet → 13 dispatch code；两对同尾码（后续计量一对 / 账面核对一对），靠页内 `bondBranch` 分支选择器区分 |
| router 歧义 | 🔴 **两个数都要断言**：歧义码总数 与 真正可达数（后者仅两个 L4 子码，其余是裸循环码） |
| sheet 名缺陷 | 程序表**尾随**空格（`endswith` 失效）+ 账面核对表**内部**空格（引用 LC-10） |
| 审定表结构 | 双期六列；「减：一年内到期」列只在小计行有值；两种等价写法混用（引用 **LC-21**） |
| 宽表 | `应付债券明细表L4-2` 是全 L 域最宽 |
| 前缀轴 | 不重复型 `L4-{sheet}-…`（引用 LC-17 ①） |
| 行身份 | `L4TabFinLiabOther.vue` 有 `L4-3-row-${n}-data`（位置化）+ `removeRow($index)`；`L4TabAdjustment.vue` 有两个 `handleRemove` 变体 |
| 真库 | 一行 `'[]'` ⇒ 无有效载荷，闭环须标 `[ ]*` |
| footer | 程序表重复两次（引用 LC-12） |

## BP-8 的落地方案（契约层区分，不改模板名）

**问题**：两对 sheet 同尾码 ⇒ ① 前端 dispatch 折叠成一个 code；② 后端解析器对同时 `endswith` 的两张取第一个；③ 契约若以尾码作 `sheet_key`，两张表共用一套字段映射。

**方案**：`sheet_key` 用**能区分两对的稳定标识**，候选两条路线：

| 路线 | 做法 | 代价 |
|---|---|---|
| A. 尾码 + 分支判别 | `sheet_key = "{尾码}#{bondBranch 值}"`，契约里登记两个分支的映射 | 需把 `bondBranch` 提升为契约级参数；前端 provide/inject 链路要暴露出来 |
| B. 全 sheet 名作 key | `sheet_key = 权威 sheet 名逐字` | 键含空格与半角括号（LC-10），须全链路禁归一化；换名即断 |

🔴 **裁定：走路线 A**。理由：① 路线 B 的键含 LC-10 登记的空格缺陷，把缺陷固化进契约；② `bondBranch` 已经是前端**当前唯一**的区分手段（现算可验），提升它比引入新键更少改动；③ 路线 A 保留了尾码这一业务语义（审计人员按尾码找表）。
🔴 **模板改名明确排除**：改名会打断既有 render schema 与 prefill 的 sheet 名匹配，须另立 spec。本 spec 只在契约层与解析层区分。

**解析层配套**：后端 sheet 解析在「同时 `endswith` 多张」时 SHALL 不再静默取第一个，而是**要求调用方带分支参数**，否则返回明确错误（fail-closed）。🔴 这是行为变更，须同时验 L1/L2 等无歧义 entry 不受影响。

## 本车道的位置化范围（不重不漏）

| 归属 | 命中 |
|---|---|
| foundation（L1） | `useL1FormData.ts` 的 `L1-adj-${n}-*` 与泛型工厂 + slice 口径 ① 的 1 处 |
| **本 spec（L2/L3/L4）** | L4 的 `L4-3-row-${n}-data`（`L4TabFinLiabOther.vue`）；L2 / L3 的 rowId 生成模块属**已安全侧**，只登记不改 |
| lane 3（L5~L8） | L6 / L7 的全部命中（含分隔符两型与索引基准两型） |

🔴 **正面样板抽取**：L2 / L3 的三个动态行表模块（`useL2Detail` / `useL2VoucherCheck` / `useL3VoucherCheck`）是全 L 域唯一生成真 rowId 的模块，其前缀两两不同（防串档）。它们的 rowId 生成形态 SHALL 被抽为其余 entry 去位置化的**参考实现**，写入本 spec 的产物。

## Property 清单（LA-P1 ~ LA-P26）

> 口径：所有计数类一律**现算**并与本文档等值比对，**禁写死**。共同 Property 见 foundation 的 LF-P1 ~ LF-P48，本清单不重复。

| ID | 断言 | 分母 |
|---|---|---|
| LA-P1 | 三条 entry 的 `capability_target_blocked_by` 现算：L2 6 项 / L3 6 项 / L4 7 项，且均不含 BP-4 与 BP-6 | 3 |
| LA-P2 | 「含 BP-5」与「含 BP-4+BP-6」两集合完全互斥（现算全 8 条） | 8 |
| LA-P3 | L4 是本 spec 唯一含 BP-8 的 entry，且全 L 域唯一 | 8 |
| LA-P4 | 三条的 orphan 孪生模块定位正确，L3 为**两份** | 4 个模块 |
| LA-P5 | 每个 orphan 的生产消费边 == 0（删前门） | 4 |
| LA-P6 | 四个 orphan 均为一阶（barrel 不存在，引用 LC-24） | 4 |
| LA-P7 | `components/workpaper/composables/useL3DualMode.ts` 的 storage 键**不含 wpId**（引用 LC-18） | 1 |
| LA-P8 | 删除后剩余 dual-mode 模块数与行数合计 == 删除前现算值 − 被删模块行数之和 | 两侧都验 |
| LA-P9 | L2 的前缀载体是**字面量**而非常量（引用 LC-17 ④） | 1 |
| LA-P10 | 真库：任一 `item_id ~ '^L{n}-'` 的行其 `wp_code` 以 `L{n}` 开头；违例逐行登记且数量与本文档等值 | 全 L 域行数（非空） |
| LA-P11 | 违例成因未取证前不断言（只登记现象）——用「无成因断言」作检查项 | 自检 |
| LA-P12 | 跨 entry 污染守卫覆盖 8 条 entry 全集 | 8 |
| LA-P13 | L4：16 权威 sheet → 13 dispatch code，重复码集合恰两个 | 16 |
| LA-P14 | L4 四张同码 sheet 名逐字不同，其中一张带内部空格 | 4 |
| LA-P15 | 两张账面核对表**同时** `endswith` 同尾码（引用 LC-10） | 2 |
| LA-P16 | router 歧义码**两个数都断言**：总数 与 真正可达数 | 两侧都验 |
| LA-P17 | `bondBranch` 是当前唯一区分手段，且**不是**模式开关（引用 LC-15） | 1 |
| LA-P18 | 契约 `sheet_key` 走路线 A（尾码 + 分支），且不含 LC-10 的空格缺陷 | 2 对 |
| LA-P19 | 解析层在多张同时 `endswith` 时 **fail-closed**，且无歧义 entry 不受影响 | 两侧都验 |
| LA-P20 | L3 的 `#REF!` 4 处与 L1 侧 4 处同源同形（引用 LC-11 / LC-25） | 8 |
| LA-P21 | L3 册 definedName 有污染且 broken 数与 L6/L7 相同；**L1 册为 0** ⇒ 非从 L1 复制 | 4 册 |
| LA-P22 | `L3TabContractCheck.vue` 与 L1 侧同借 D4 端点、同按 `$index` 传行（引用 LC-19） | 2 |
| LA-P23 | L2 / L3 的三个动态行表模块是全 L 域唯一按行身份删的模块（引用 LC-6 交叉验证） | 全 L 域 removeRow 集合 |
| LA-P24 | 这三个模块的 rowId 前缀**两两不同** | 3 |
| LA-P25 | L6 / L7 的位置化命中被显式声明「归 lane 3」（范围不重不漏自检） | 自检 |
| LA-P26 | L2 / L3 / L4 的真库载荷均不足以做闭环 ⇒ 三条闭环全标 `[ ]*` | 3 |

**不宣称通过**：三条 entry 的端到端闭环 Property（真库无有效载荷，L2 的唯一非空载荷还是违例数据）；KC-17 对应的 prefill Property（引用 foundation 的不适用声明）。
