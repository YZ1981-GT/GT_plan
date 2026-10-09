# M1 / M5 / M8 / M9 —— mode 取值与载体例外收口 · 设计

## 上游与边界

| 项 | 值 |
|---|---|
| 共同裁决唯一出处 | `.kiro/specs/m-cycle-sync-foundation-and-first-canary/design.md` 的 **MC-1 ~ MC-29** |
| BP-6 / BP-8 判据定义方 | `.kiro/specs/m2-m3-m4-m7-m10-sheet-map-drift-and-collapse`（本 spec **引用**，不另写） |
| slice | `backend/data/workpaper_sync_m_cycle_manifest_slice.json` |
| 删除清册 | `backend/data/workpaper_sync_m_cycle_deletion_plan.json` |
| 既存守卫 | `backend/tests/workpaper_sync/test_task55_m_cycle_migration.py`（锁现状，本 spec 锁改线后目标态） |
| Property 前缀 | **`MB-P`**（foundation 用 `MF-P`，lane 2 用 `MA-P`） |

🔴 本 spec 的 `MC-x` **只引用编号不复述**。

## 🔴 为什么本 spec 的缺陷集合不齐整（必读）

切分以 **BP-4** 为主轴：lane 2 = 含 BP-4 的 5 条，本 spec = **补集**（扣掉 canary entry `xlsx/gt-m6-retained-earnings`）。

**排除的替代方案**：
| 方案 | 为什么不用 |
|---|---|
| 按 BP-6 二分（M1~M4 / M5~M10） | 🔴 **BP-4 会横跨两份 spec**（M2/M3/M4 在一侧，M7/M10 在另一侧）⇒ 最贵的一条缺陷判据必然漂移 |
| 按互斥集合切（L 轮方式） | 🔴 M 的 BP 集合**交叉重叠**不是互斥：M2 含 4/6/8 · M10 含 4/8/12 · M1 只含 6 · M8 只含 8 ⇒ 不存在互斥二分 |
| 按科目相邻切（M1~M5 / M6~M10） | 🔴 会把 BP-4 与 BP-6 同时切断，且 canary 落在边界上 |

**本 spec 内部按 entry 分支处理**：**M1 → BP-6**（唯一含 6 不含 4）· **M8 → BP-8** · **M9 → 载体 `none` + 双孪生皆 orphan + SHEET_MAP 2 处 orphan 错位** · **M5 → 只公共项（干净对照组）**。

🔴 **M5 与 M9 的 BP 集合完全相同（都是公共 8 项）却归属不同缺陷组** —— 差异不在 BP 层而在**载体层**与 **SHEET_MAP 层**。判据若只看 `blocked_by` 会认为两者同质，必须按载体 kind 与 MAP 现算区分。

## 4 条 entry 权威表（现算自 slice + 删除清册）

| entry_id | wp_code | sheets | 公式格 | HTML | OO 兜底 | mount | 载体 kind | redeem | MAP d/h/m | BP 数 | 区分项 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `xlsx/gt-m1-dividends-payable` | M1D | 11 | 338 | 10 | 1 | 2 | per_entry_wrapper | `true` | 10/10/0 | **9** | **BP-6** |
| `xlsx/gt-m5-surplus-reserve` | M5S | 10 | 193 | 9 | 1 | 2 | per_entry_wrapper | `true` | 9/9/0 | **8** | 无（对照组） |
| `xlsx/gt-m8-general-risk-reserve` | M8G | 11 | 227 | 9 | **2** | 2 | per_entry_wrapper | `true` | 8/8/0 | **9** | **BP-8** |
| `xlsx/gt-m9-other-comprehensive-income` | M9O | 9 | **470** | 8 | 1 | **1** | **`none`** | **`false`** | 8/6/**2** | **8** | 载体 + MAP(orphan) |

**算术自检**：sheets `11+10+11+9 = 41` · HTML `10+9+9+8 = 36` · OO 兜底 `1+1+2+1 = 5` · 36 + 5 = **41** ✓ · 公式格 `338+193+227+470 = 1228` · MAP declared `10+9+8+8 = 35` = hit `10+9+8+6 = 33` + missing `0+0+0+2 = 2` ✓ · mount `2+2+2+1 = 7`

**与全域闭合**：sheets `41 + 51 + 10 = 102` ✓ · HTML `36 + 44 + 9 = 89` ✓ · OO `5 + 7 + 1 = 13` ✓ · 公式格 `1228 + 1534 + 175 = 2937` ✓ · MAP declared `35 + 43 + 6 = 84` ✓ · missing `2 + 9 + 0 = 11` ✓ · mount `7 + 10 + 2 = 19` ✓

**补集完备性**：全 M 域不含 BP-4 的 entry = 本 spec 4 条 + canary M6 = **5** 条；`5 + 5 = 10` ✓

## M9 是四重例外（唯一）

| 例外 | 现算 | 抄别处会怎样 |
|---|---|---|
| 载体 `kind == 'none'` | 10 条唯一 | 抄「per_entry_wrapper」判据 ⇒ M9 找不到活载体被误判 |
| **双孪生皆 orphan** | `entries_with_two_orphan_twins == 1` | 抄「orphan 数 == live 数」⇒ 全域分母算错（11 ≠ 9） |
| 宿主无 `el-segmented` + `anchor is None` | `entries_without_any_ui_gate_anchor == 1` | 抄「notice 挂宿主工具条」⇒ 无锚点可挂 |
| mode 用**类型引用** `WorkpaperRenderMode` + **无 storage 键** | — | 扫字面量枚举与扫 storage 键**都会漏掉它** |

🔴 **「没有开关」不是裁 single 的理由**：① M9 有 HTML 对端（`checklist_responses` 通道实测存在）⇒ AC 12.8 禁 `single_onlyoffice`；② M9 册 9 张 sheet / 公式格 **470**（10 册第二多）⇒ AC 12.9 的 `single_html` 不适用；③ 宿主经 `htmlRendererRegistry` 可达 ⇒ 非 `unreachable`。M9 的 `GtOnlyOfficeSheet` 挂点是**未迁移 sheet 的兜底渲染器**，不由 mode 决定。

## M9 的 SHEET_MAP 2 处错位：登记不修

| sheet code | 声明值 | 权威册真名 | 错法 |
|---|---|---|---|
| `procedure` | `其他综合收益实质性程序表M9A` | `'其他综合收益实质性程序表 M9A'` | 丢中间空格 |
| `M9-4` | `OCI核对表M9-4` | `其他综合收益核对表M9-4` | 整段不同（**中英混写**） |

🔴 这 2 处落在 **orphan 模块**里（`defect_pairs_in_orphan_modules == 2`）⇒ **M9 不挂 BP-4** ⇒ 本 spec **只登记不修**。删掉 M9 的两个 orphan 后这 2 处**随之消失**（现算验证 missing 从 11 降到 9）。
🔴 **误修风险**：若先「修」orphan 里的 SHEET_MAP 再删文件 = 无效功 ⇒ 判据须在删除前断言该模块**无人消费**。

## M8 与 M10 的 BP-8 成因不同（修法动作不同）

| entry | 成因 | 修法动作 | 归属 |
|---|---|---|---|
| **M8** | **完全没有拦截代码**（`实质性程序表` 先命中） | **新增**历史 sheet 判断并排到前面 | 本 spec |
| M10 | **写了拦截但排在后面**（不可达死代码） | **移动**已有判断到前面 | lane 2 |

🔴 两者目标态相同（历史 sheet 判断在前），但动作一个是「新增」一个是「移动」⇒ 判据可共用、实施步骤不可共用。
🔴 `针对性测试M8-5-删除`：「删除」二字是**源模板作者的标注**，落 OO 兜底是**正确处置** —— **不得据此裁 single、不得真删 sheet**（删除清册 `excluded_from_plan` 已登记）。M8 的 OO 兜底 **2** 张 = `GT_Custom` + 该 sheet。

## `procedure` 键的三条 hit 全在本 spec（正面样板但写法各异）

| entry | 声明值 | 与真名关系 | 特征 |
|---|---|---|---|
| M1 | `'应付股利实质性程序表M1'` | 一致 | 🔴 **10 册唯一不带 `A`**（真 sheet 名也不带） |
| M5 | `'盈余公积实质性程序表 M5A'` | 一致 | 带中间空格 |
| M8 | `'一般风险准备实质性程序表 M8A '` | 一致 | 带中间 **+ 尾随**空格 |

🔴 **hit 不等于写法统一** —— 三条写法互不相同 ⇒ 它们是「碰巧与真名一致」而非「按统一规则生成」⇒ **只能当逐条比对的参照，不能当规则抄**。
🔴 加上 lane 2 的 6 条 miss（均不带空格）与 **M6 根本没有这个键**，`procedure` 的状态是 **4 种写法 + 1 处缺键**（引用 MC-23）⇒ 逐模块手写、无单一真源的铁证。
🔴 M1 不带 `A` 这一点也是 canary 排除 M1 的理由之一（引用 foundation 的排除理由）。

## M1 的两项独有属性

| 属性 | 现算要求 |
|---|---|
| **科目性质是负债类**（10 条唯一） | 🔴 **必须现算科目码确认，不得推演**；四表判据按 **1 : 9 两分支**写（引用 MC-22）；判据写成「M 全域都是权益类」会让 M1 假绿 |
| **真库唯一非空行是 AI 会话记录** | `M1-review-session-20260725075149`（`remark` 现算约 261 字节，内容含 `session_id`）⇒ 🔴 不得用于闭环验证；且该键**不符合** `ITEM_PREFIX` + sheet 段 + field 段三段式命名 ⇒ 登记为「命名空间被非业务用途借用」的实证 |

## definedName 污染：两类来源不可一刀切

| 类别 | 分布 | 来源 |
|---|---|---|
| 短名污染（`AFV` / `bs` / `bs_1` / `CCD` / `CDE` / `DEX` / `EDC` / `FAD`） | 全 10 册 | 与 **L 循环同源** |
| **中文名与跨循环名**（`_1、受本循环影响的相关交易和账户余额` / `_2、主要业务活动` / `_1固定资产数据库_筛选打印` / `CarryKnown` / `_.dbf` / `_00510`） | **只 M1 / M9** | 🔴 **从别的底稿册复制来的** |

本 spec 4 册的分布：**M9 与 M1 显著高**，M5 / M8 的 broken 数与其余 6 册**彼此相同**（引用 MC-9）。
🔴 解析器须容忍两种新形态不崩：`{#N/A,…,"BBPREP"}`（打印区域宏残留）· `[1]Breakdown!#REF!`（外部工作簿引用）。
🔴 **本 spec 不清理污染**（归全域批次，避免清一半），只登记溯源结论 + 冻结基线。

## M5 是干净对照组（判据必须在它上面应绿）

| 项 | M5 现算 |
|---|---|
| `must_fix_before_wiring` | 只 8 项公共 |
| SHEET_MAP | **9 / 9 / 0** |
| `switch_is_redeemable` | `true` |
| 载体 kind | `per_entry_wrapper_over_shared_base` |

🔴 本 spec 的**每条缺陷判据都要在 M5 上跑一遍并应绿** ⇒ 证明判据能区分「有缺陷」与「无缺陷」，不是一律判红。
**与 canary M6 的差异只两项**：公式格 **193 > 175**、且 M5 册**无 Q 表**故无「正确处理先例」⇒ 这正是 canary 选 M6 不选 M5 的理由。M5 真库 **0** 行 ⇒ 闭环同样标 `[ ]*`。

## Property 清单 MB-P1 ~ MB-P30

| Property | 断言 | Req | MC |
|---|---|---|---|
| MB-P1 | 四条 `capability_target_blocked_by` 现算 9 / 8 / 9 / 8，且 🔴 **全部不含 BP-4** | 1.1 | MC-23 |
| MB-P2 | 补集完备性：不含 BP-4 的 entry = 本 spec 4 条 + canary M6 = 5；`5 + 5 == 10` | 1.2 | — |
| MB-P3 | 区分项：M1 独含 BP-6 · M8 独含 BP-8 · M5 与 M9 只含公共 8 项 | 1.3 | — |
| MB-P4 | 🔴 M5 与 M9 的 BP 集合相同但载体层与 MAP 层不同 ⇒ 判据不得只看 `blocked_by` | 1.4 | MC-2 / MC-23 |
| MB-P5 | BP-1/2/3 标 `[ ]*` 引用 foundation；BP-5/7/9/10/11 引用 MC-16/12/1/8/26 不重裁 | 1.5 / 1.6 | 多条 |
| MB-P6 | M9 `kind == 'none'` 且 `switch_is_redeemable` 为 `false`，10 条唯一 | 2.1 | MC-2 |
| MB-P7 | M9 两个孪生生产边与测试边**均 0**；`entries_with_two_orphan_twins == 1` | 2.2 | MC-2 |
| MB-P8 | M9 宿主剥注释后无 `el-segmented`、`anchor is None`、OO 挂点是未迁移 sheet 兜底 | 2.3 | MC-13 |
| MB-P9 | M9 mount == 1（其余各 2）⇒ 全域 19 | 2.4 | MC-2 |
| MB-P10 | M9 mode 用类型引用 `WorkpaperRenderMode` 且无 storage 键 ⇒ 🔴 两类判据都会漏掉它 | 2.5 | MC-16 |
| MB-P11 | 🔴 不得据 M9 无开关裁 single：三条反驳逐条现算（HTML 对端存在 / 9 sheet + 470 公式格 / registry 可达） | 2.6 | MC-2 |
| MB-P12 | M9 notice 须与 sync bridge 编辑宿主一并落位（无既成锚点） | 2.7 | MC-12 |
| MB-P13 | M9 SHEET_MAP `8 = 6 + 2`，两处逐字登记；🔴 在 orphan 模块 ⇒ 只登记不修 | 3.1 / 3.2 | MC-23 |
| MB-P14 | `全域 11 == lane 2 的 9 + M9 的 2`；`entries_with_defects == 6` 与「BP-4 五条」并存 | 3.3 | MC-23 |
| MB-P15 | 删 M9 两个 orphan 后 missing 从 11 降到 9（现算验证）；🔴 删除前断言该模块无人消费（防先修后删的无效功） | 3.4 / 3.5 | MC-16 |
| MB-P16 | M1 mode 枚举为 `'structured' \| 'onlyoffice'`；🔴 **引用 lane 2 的 BP-6 判据函数**；BP-6 总数 `3 + 1 == 4` | 4.1 ~ 4.3 | MC-16 |
| MB-P17 | 🔴 M1 同属「BP-6 批」与「item_id 重复前缀批」= 两条分界线同侧，与 M4 的两侧不同形成对照 | 4.4 | MC-15 |
| MB-P18 | M8 折叠：11 sheet → 10 code，来源 `Q8A  (修订前)`（双空格）；🔴 成因是**完全没有拦截**（M10 是死代码）⇒ 动作「新增」vs「移动」 | 5.1 ~ 5.3 | MC-27 |
| MB-P19 | `针对性测试M8-5-删除` 落 OO 兜底是正确处置；🔴 不裁 single 不真删；M8 OO 兜底 == 2 | 5.4 / 5.5 | MC-11 / MC-27 |
| MB-P20 | 🔴 引用 lane 2 的 BP-8 判据；BP-8 总数 `2 + 1 == 3`；后端过滤是根治、本条是补救 | 5.6 / 5.7 | MC-24 |
| MB-P21 | 🔴 M1 科目性质**现算科目码**确认为负债类（禁推演）；1 : 9 两分支；TB 发布口径结论如实登记（不预设） | 6.1 ~ 6.4 | MC-22 |
| MB-P22 | 已归档 spec 的「M1 键 ∩ K3 键 == ∅」守卫现算为**未完成**并落地；键集合从代码现算（禁只查真库）；扩展到任意两循环两两无交集 | 7.1 ~ 7.5 | MC-19 |
| MB-P23 | M1 真库 2 行；`M1-review-session-*` 定性为 AI 会话记录**不得用于闭环**；🔴 该键不符三段式命名 ⇒ 命名空间被借用的实证；处置裁定书存在 | 8.1 ~ 8.5 | MC-18 / MC-15 |
| MB-P24 | definedName：M9 与 M1 显著高、M5/M8 与其余 6 册相同；中文名与跨循环名样本 ≥ 3；两种新形态不崩；🔴 本 spec 不清理；两类来源不可一刀切 | 9.1 ~ 9.5 | MC-9 |
| MB-P25 | `procedure` hit 恰 3 条且全在本 spec；🔴 三条写法互不相同 ⇒ 只作逐条参照不作规则；M1 唯一不带 `A`；M6 无此键；产出「code → 真名」对照表且每值 ∈ 真 sheet 名集合 | 10.1 ~ 10.5 | MC-23 |
| MB-P26 | M5 四项全干净且**每条缺陷判据在 M5 上应绿**；与 M6 的差异只两项（193 > 175、无 Q 表先例）；M5 真库 0 行 | 11.1 ~ 11.4 | MC-18 |
| MB-P27 | 位置化四族本 spec 份额现算；🔴 `useM9OciReconcile.ts` 是 11 个持久化键命中文件里**唯一非 `useM{n}Adjudication.ts` 形态**的一个且同样恰 1 处 `const n = idx + 1` ⇒ 判据不能只扫 `Adjudication` 命名 | 12.1 / 12.2 | MC-8 |
| MB-P28 | removeRow 变体逐一登记四元组，含 `M9TabDetail.vue` 的 `handleRemove(displayIndex)` → `removeRow(globalIdx)` 双套映射链；🔴 两层**同时**消除（构造用例证明只改一层会新错位）；🔴 复用 foundation 在 M6 上的样板形态，**不新造第二种**；item_id 按 entry 分别写；双基准同时处理 | 12.3 ~ 12.7 | MC-6 / MC-7 / MC-15 |
| MB-P29 | 模板层 4 册逐册值现算（M9 公式格 470 第二多 / M9 明细表宽表 / M1 `明细表M1-2` 公式格最多 / M8 有「删除」sheet / M8 与 M6 的 Q 表双空格 / 「合计·小计」分散对齐在 M7·M8·M9 的分布）；🔴 4 册 sha256 本 spec 前后**不变**（与 lane 2 改 M10 册对照）；幽灵行声明 `max_row − last_value_row` 口径 | 13.1 ~ 13.4 | MC-9 / MC-10 / MC-11 / MC-27 |
| MB-P30 | 闭环标 `[ ]*`（M1 2 行含 AI 会话记录 / M9 1 行 `NULL` / M5 与 M8 各 0 行）；自检：`MC-x` 只编号不复述 · entry 用全名 4 条无重无漏 · 六组算术与全域闭合 · 「N 处」与列举项数相等 · `MB-P` 无缺号 · 无 U+FFFD | 14.1 ~ 14.7 | MC-18 |

## 闭环阻塞（标 `[ ]*`）

| entry | 真库行数 | 载荷 |
|---|---|---|
| `xlsx/gt-m1-dividends-payable` | **2** | `M1-M1-2-full-data` → `NULL` · `M1-review-session-20260725075149` → 🔴 **AI 复核会话记录不是业务数据** |
| `xlsx/gt-m9-other-comprehensive-income` | 1 | `M9-2-detail-rows` → `NULL` |
| `xlsx/gt-m5-surplus-reserve` | **0** | — |
| `xlsx/gt-m8-general-risk-reserve` | **0** | — |

⇒ 四条均无有效业务载荷，闭环标 `[ ]*`。`conclusion` 非空全域现算 **0** ⇒ contract 字段映射只映 `remark`。

## 算术自检（复盘必跑）

| 等式 | 值 |
|---|---|
| entry 数 | **4**；不含 BP-4 的 entry = 4 + canary M6 = 5；`5 + 5 = 10` ✓ |
| sheets | 11+10+11+9 = **41**；`41 + 51 + 10 = 102` ✓ |
| sheet 归属 | HTML 36 + OO 兜底 5 = **41** ✓；`36 + 44 + 9 = 89` ✓；`5 + 7 + 1 = 13` ✓ |
| 公式格 | 338+193+227+470 = **1228**；`1228 + 1534 + 175 = 2937` ✓ |
| SHEET_MAP | declared 35 = hit 33 + missing 2 ✓；`35 + 43 + 6 = 84` ✓；`2 + 9 + 0 = 11` ✓ |
| mount | 2+2+2+1 = **7**；`7 + 10 + 2 = 19` ✓ |
| BP-6 | 本 spec 1 条（M1）+ lane 2 的 3 条 = **4** ✓ |
| BP-8 | 本 spec 1 条（M8）+ lane 2 的 2 条 = **3** ✓ |
| `procedure` hit | 本 spec 3 条 == 全域 hit 3 条 ✓（lane 2 全 miss，M6 无此键） |
| 载体例外 | `none` 1 条（M9）== 全域 1 ✓；双孪生皆 orphan 1 条 == 全域 1 ✓ |
| Property 编号 | MB-P1 ~ MB-P30 连续无缺号 ✓ |
