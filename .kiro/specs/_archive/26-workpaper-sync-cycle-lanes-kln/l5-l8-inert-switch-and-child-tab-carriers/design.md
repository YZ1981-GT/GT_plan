# L5 ~ L8 死开关与子 Tab 专属载体车道 — 设计

## 上游与边界

| 项 | 值 |
|---|---|
| 共同裁决出处 | `.kiro/specs/l-cycle-sync-foundation-and-first-canary/design.md` 的 **LC-1 ~ LC-26** |
| 共同 Property 出处 | 同上的 **LF-P1 ~ LF-P48** |
| 参考实现出处 | `.kiro/specs/l2-l3-l4-orphan-twins-and-sheet-granularity-collapse/design.md` 的 **rowId 正面样板** |
| slice | `backend/data/workpaper_sync_l_cycle_manifest_slice.json` |
| 既存守卫 | `backend/tests/workpaper_sync/test_task54_l_cycle_migration.py` |
| 本 spec entry | `xlsx/gt-l5-long-term-payables` · `xlsx/gt-l6-special-payables` · `xlsx/gt-l7-other-noncurrent-liabilities` · `xlsx/gt-l8-financial-expenses`（4 条） |

🔴 **本 spec 不复述任何 LC-x 的判据内容。** 出现 `LC-x` 即指 foundation 处的裁决原文。

## 为什么这四条合并（切分依据）

slice 自身 `capability_target_blocked_by` 的集合关系（现算可验、完全互斥）：

```
含 BP-4 + BP-6、不含 BP-5：{L5, L6, L7, L8}   ← 本 spec，四条 blocked_by 完全一致（各 7 项）
含 BP-5、不含 BP-4/BP-6：  {L1, L2, L3, L4}   ← foundation(L1) + lane 2(L2/L3/L4)
```

这四条比 lane 2 更齐整：载体 kind 全同（`child_tab_dedicated_composable`）· `switch_is_redeemable` 全为 `false` · `orphan_twin` 全为 `null` · `mode_values` 全为 `["structured","onlyoffice"]` · localStorage 键形态全同。**唯一的异质点是 L8 的科目性质**（损益类，LC-26）。

## 与 foundation 的形态差异（判据不可照抄）

| 维度 | foundation（L1 / L2） | 本 spec（L5 ~ L8） |
|---|---|---|
| 载体位置 | **宿主**层（`GtL{n}*.vue`） | **子 Tab** 层（`l{n}/core/L{n}TabAdjudication.vue`） |
| `mode_values` | `["html", "onlyoffice"]` | `["structured", "onlyoffice"]` |
| `switch_is_redeemable` | `true`（宿主有 mode 门控的 OO 挂点） | `false`（开关存在但 inert） |
| localStorage 键 | `` `${PREFIX}${wpId}` ``（PREFIX 自带尾连字符） | `` `${PREFIX}:${wpId}` ``（`:` 分隔，取键函数名不同） |
| `ui_toolbar_gate.anchor` | 非空（宿主有工具条） | `null`，但 `child_level_segmented_site` **非空** |
| notice 落位点 | 宿主层 | 🔴 **子 Tab 层** |
| `orphan_twin` | 非空（有孤儿孪生） | `null`（无孤儿，载体就是 live 模块） |

🔴 **BP-5 在本 spec 不适用**：这四条的载体模块是 live 的（有真实消费边），不是 orphan。故本 spec **没有删 orphan 的动作**——这与 lane 2 的主线完全不同。

## 四条 entry 专属事实

### 共性（四条全同，现算可验）

- 载体 site 全在 `l{n}/core/L{n}TabAdjudication.vue`；消费到的 dualMode 成员只有 `mode` / `modeOptions` / `switchMode`
- `mode` 只作 `v-model` 双绑，**无任何分支以它为条件**；该文件内 `GtOnlyOfficeSheet` 命中 0 ⇒ inert 三条件成立（LC-2 / LC-15）
- `evidence.unverifiable_reasons` 比 L1~L4 **多一条**（BP-4 造成的「连『切过去看得到什么』都无法观察」），且 BP-4 **只**出现在这四条的 reasons 里
- 真库载荷：L5 两行 `'[]'`；L6 / L7 / L8 **0 行** ⇒ 四条闭环全标 `[ ]*`

### 逐条差异

| entry | OO 兜底 | 位置化命中 | 模板专属缺陷 | 科目性质 |
|---|---|---|---|---|
| `xlsx/gt-l5-long-term-payables` | 1 张 `GT_Custom` | `useL5Detail` / `useL5RelatedParty` 的 `removeRow(index: number)` | 🔴 **倒挤减法链（减本表已列项）**；definedName 污染且**独有 SAPBEX 三名**（LC-9） | 负债类 |
| `xlsx/gt-l6-special-payables` | 1 张 `GT_Custom` | 🔴 **全 L 域最密集**：`useL6SpecialCheck` / `useL6Adjudication` / `useL6Detail` / `L6TabAdjudication.vue` / 两个 `L6TabDisclosure*.vue` / `L6TabSpecialCheck.vue` | 🔴 **倒挤减法链（减对方表明细行）**；definedName 污染 | 负债类 |
| `xlsx/gt-l7-other-noncurrent-liabilities` | 0 | `useL7Adjudication` / `useL7Detail`；两个 Disclosure 的 `removeRow($index)` | 🔴 **同册附注披露括号全半角不一致**（唯一，LC-10）；definedName 污染 | 负债类 |
| `xlsx/gt-l8-financial-expenses` | 0 | `useL8CutoffTest` 的 `removeRow(section, index)` 双参 | `非金融机构利息支出测算表L8-4` 四固定槽 + 硬编码加法链 + **单元格值带尾随空格**；definedName 为 **0** | 🔴 **损益类** |

🔴 **L6 的两个 Disclosure 组件是分隔符异常的唯一来源**：它们用 `row${…}`（无连字符），其余全用 `row-${…}`（LC-8）。

## BP-4 的两条收口路线（须显式裁定）

| 路线 | 动作 | 前置 | 代价 |
|---|---|---|---|
| ① **兑现** | 子 Tab 里补 `GtOnlyOfficeSheet` 挂点 + 以 `mode` 为条件的分支，使切换真实生效 | 🔴 依赖 **BP-1/2/3**：无 approved authority model / per-entry contract / non-null bundle 时，补出来的 OO 侧没有权威定义 | 相应 task 必标 `[ ]*` |
| ② **摘除** | 删子 Tab 的 `el-segmented` + 删 `useL{n}DualMode.ts` 载体，回到单形态 | 无外部依赖 | 删后四个载体模块消费边归零 ⇒ **须同 commit 一并删**，不留 orphan |

🔴 **本 spec 不预先裁定**，而是在 tasks 里把裁定本身作为一个 task（须写明理由与所选路线）。理由：路线 ① 的价值取决于 BP-1/2/3 何时到位，这是 spec 编写时无法确定的外部条件；预先裁定会让 spec 在条件变化后失效。

🔴 **无论选哪条路线，收口后都须现算断言**：inert 计数从 4 变为 0，且 `switch_is_redeemable` 不再有 `false` 值。

🔴 **立场约束（引用 slice 的 `adjudication.not_single_html_because`）**：「**开关坏了」≠「无 OO 业务价值**」。四册模板各有真实业务 sheet（现算 sheet 数分别为 12 / 9 / 8 / 10），不得借 inert 把 entry 裁成 `single_html`——那是把 AC 12.9 的判据换掉。

## BP-6 的准确形态（不可表述错）

L 域对 OO 端点的直调**只有探活一种**：

- `onlyoffice/health` —— 有命中（现算数见 tasks）
- `onlyoffice-config` —— 🔴 **命中 0**（与 K 循环不同，K 有该端点命中）

⇒ **L 域只探活不取配置**。表述为「L 域两个端点都在直调」即错。
收口方案：把探活收敛到单一入口（共享 composable 或 service），现算断言收敛后直调点数为 0、入口调用点数 == 收敛前的直调点数（守恒校验）。守卫按端点字面量卡点，不按符号名（同 LC-3 口径）。

## L6 索引基准差异的取证要求（🔴 不得预设结论）

现象：写侧模块用 `${i + 1}`，两个 L6 Disclosure 读侧用 `${i}`，且分隔符也不同（`row-` vs `row`）。

两种可能，**取证前不得下结论**：

| 可能 | 判据 | 结论 |
|---|---|---|
| A. 读写键不成对 | 逐键核对：写入的完整 item_id 集合 ∩ 读取的完整 item_id 集合 == ∅（或部分缺失） | **真缺陷**，单列修复项 |
| B. 两套键各管各的 field | 写侧与读侧的 field 名不同（如写 `end_balance`、读 `audited_end`）⇒ 本就是两套独立键 | 如实登记为「两套键并存」，**不是 bug** |

取证方法：把写侧与读侧的 item_id 模板**各自展开成完整键模式集合**（field 名一并取出），求交集与差集。🔴 只看分隔符不同就判 bug 是误判。

## 倒挤减法链的修复方案（LC-20）

| entry | 现状形态 | 修复方向 |
|---|---|---|
| L5 国企版附注 | `='明细表L5-2'!{列}{行} − 本表{列}12 − … − {列}16`（减本表已列项，硬编码 5 行窗口） | 换成「整列 SUM 减去固定标签行」或 `SUBTOTAL`，使窗口随行数扩展 |
| L6 国企版附注 | `='明细表L6-2'!{列}{合计行} − 明细表L6-2!{列}10 − … − {列}14`（减对方表明细行，硬编码 5 行窗口） | 同上，且须处理跨 sheet 引用的区间扩展 |

🔴 **只在「国企」版**，上市公司版无 ⇒ 判据必须扫两个变体（扫一个会误判「已修复」）。
🔴 **改模板后必须同步更新 slice `template_ref` 的 sha256 基线**，并在守卫里现算比对（引用 LF-P23）；不更新会让既存守卫红。
🔴 范围只含 L5 / L6 两册；L4 的审定表结构问题（LC-21）归 lane 2。

## Property 清单（LB-P1 ~ LB-P24）

> 口径：所有计数类一律**现算**并与本文档等值比对，**禁写死**。共同 Property 见 foundation 的 LF-P1 ~ LF-P48。

| ID | 断言 | 分母 |
|---|---|---|
| LB-P1 | 四条 `capability_target_blocked_by` 各 7 项且**完全一致**（BP-1/2/3/4/6/7/9），均不含 BP-5 / BP-8 / BP-10 | 4 |
| LB-P2 | 「含 BP-4+BP-6」与「含 BP-5」两集合完全互斥（现算全 8 条） | 8 |
| LB-P3 | BP-4 **只**出现在这四条的 `evidence.unverifiable_reasons` 里；四条 reasons 比 L1~L4 多一条 | 8 |
| LB-P4 | inert 三条件逐条现算成立（segmented 有 / mode 门控分支 0 / `GtOnlyOfficeSheet` 0） | 4 |
| LB-P5 | 对照组：L1 / L2 宿主的门控式挂点存在 ⇒ 判据能区分两形态而非一律判红（**两侧都验**） | 2 + 4 |
| LB-P6 | 每个 inert 开关消费到的 dualMode 成员恰 3 个（`mode` / `modeOptions` / `switchMode`），`mode` 只作 `v-model` | 4 |
| LB-P7 | 收口后 inert 计数 4 → **0**，`switch_is_redeemable` 不再有 `false` | 4 |
| LB-P8 | 路线 ② 若被选：四个载体删除后消费边归零，且**同 commit 一并删**（不留 orphan） | 4 |
| LB-P9 | 立场约束：四册模板各有真实业务 sheet（12 / 9 / 8 / 10），不得借 inert 裁成 `single_html` | 4 |
| LB-P10 | `onlyoffice/health` 命中数现算；`onlyoffice-config` 命中 == **0**（两个数都断言） | 两侧都验 |
| LB-P11 | health 直调点不经任何共享适配层（与 LD-3 同型） | 现算（非空） |
| LB-P12 | 收敛后直调点 == 0 且 入口调用点 == 收敛前直调点数（守恒校验） | 两侧都验 |
| LB-P13 | 载体族五项全同：kind / site 目录形态 / `mode_values` / `orphan_twin is None` / localStorage 键形态 | 4 |
| LB-P14 | 与 foundation 的七项形态差异逐项断言（载体位置 / mode 值 / redeemable / 键形态 / anchor / notice 落位 / orphan_twin） | 7 |
| LB-P15 | localStorage 键属 `` `${PREFIX}:${wpId}` `` 形态，判据落「key 含 wpId」（引用 LC-18） | 4 |
| LB-P16 | 本 spec 名下位置化命中按模块列分布并现算总数；断言是全 L 域最大份额 | 现算（非空） |
| LB-P17 | `row${…}`（无连字符）**只**出现在两个 L6 Disclosure 组件 | 两侧都验 |
| LB-P18 | L6 读写键取证：写侧 / 读侧完整键模式集合的交集与差集现算；**结论由数据决定**（A 真缺陷 / B 两套键并存） | 两侧都验 |
| LB-P19 | 去位置化复用 lane 2 的 rowId 正面样板形态，未自造第四种 | 3 样板 |
| LB-P20 | `removeRow` 本 spec 名下变体全枚举（含 L7 两个 `$index`、L8 的 `(section, index)` 双参） | 现算（非空） |
| LB-P21 | 倒挤减法链两形态各自非空，且**只在「国企」版**（两个变体都扫） | 两侧都验 |
| LB-P22 | 改模板后 slice `template_ref` sha256 基线同步更新，守卫现算比对通过 | 2 册 |
| LB-P23 | L8 是 8 条里唯一损益类；TB 发布参数走「本期发生额」；四表判据按两分支且两分支分母非空 | 7 + 1 |
| LB-P24 | L8 的 derived_total 属 MID 型且少重复 sheet 段；`L8-4` 单元格值带尾随空格 ⇒ 回写按坐标不按标签 | 两侧都验 |

**不宣称通过**：四条 entry 的端到端闭环 Property（真库 L6/L7/L8 为 0 行、L5 仅两行 `'[]'`）；BP-4 路线 ① 相关 Property（依赖 BP-1/2/3）；KC-17 对应的 prefill Property（引用 foundation 的不适用声明）。
