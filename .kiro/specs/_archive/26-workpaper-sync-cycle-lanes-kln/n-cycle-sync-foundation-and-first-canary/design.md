# N 循环双向回写地基与首张 canary — 设计

## 概述

本 spec 是 N 循环（税费）三份 sync spec 的**地基层**：一次性裁定 NC-1 ~ NC-37 共同判据、锁定五条 entry 的事实基线、落地首张 canary（`xlsx/gt-n4-taxes-and-surcharges`）。两份 lane spec 只引用 NC 编号，不复述判据。

**权威事实来源**（全部现算校验过，禁二次推演）：

| 来源 | 路径 | 体量 | 冻结 |
|---|---|---|---|
| N slice | `backend/data/workpaper_sync_n_cycle_manifest_slice.json` | 172,620 B | 2026-08-16 |
| 删除清册 | `backend/data/workpaper_sync_n_cycle_deletion_plan.json` | 41,956 B | — |
| 既存守卫 | `backend/tests/workpaper_sync/test_task56_n_cycle_migration.py` | 2650 行 / 14 类 / 123 test | — |

## 三份 spec 分工

| # | 目录 | entry | 主题 | Property 前缀 |
|---|---|---|---|---|
| 1 | `n-cycle-sync-foundation-and-first-canary` | `xlsx/gt-n4-taxes-and-surcharges` | 地基 + NC 裁决 + canary 闭环 | **NF-P** |
| 2 | `n1-n3-host-inline-router-and-shared-adoption` | `xlsx/gt-n1-deferred-tax-assets` · `xlsx/gt-n3-deferred-tax-liabilities` | 宿主内联 sheet 路由 + 未采用共享路由 | **NA-P** |
| 3 | `n2-n5-json-table-identity-and-cross-entry-readonly` | `xlsx/gt-n2-taxes-payable` · `xlsx/gt-n5-income-tax-expense` | 整表 JSON 行表身份 + 跨 entry 只读 | **NB-P** |

**切分依据**（探针穷举 35 个去对称方案，非凭感觉）：公共 BP 7 项（1/2/3/6/7/9/11）对切分无影响；区分项为 BP-4{N3} · BP-5{N4,N5} · BP-8{N1,N2,N5} · BP-10{N1,N3} · BP-12{N5}。本方案横跨 **2** 条（BP-5 / BP-8）且各只分 2 组，BP-4 / BP-10 完整内聚 lane2、BP-12 完整内聚 lane3。

🔴 **决定性理由 —— 与 slice 自己的路由分界完全吻合**：slice 的 `hosts_using_host_inline_regex: 2` = {N1, N3} = lane2；`hosts_using_shared_cycle_sheet_router: 3` = {N4, N2, N5} = foundation + lane3。切分沿着代码既有的架构断层，而非科目编号相邻。

**被排除的方案**：
- `foundation=N2 | lane2=[N1,N3] | lane3=[N4,N5]`：全局横跨数 **1**（理论最小），但那 1 条 BP-8 **分散到 3 个组**，劣于「2 条各分 2 组」。
- `foundation=N4 | lane2=[N1,N2,N3] | lane3=[N5]`：同样横跨 2，但规模 1+3+1 失衡。

🔴 **跨 spec 交叉引用点**：`N3A` sheet 码同时存在于 **N3 册（lane2）与 N5 册（lane3）** ⇒ 两份 lane spec 须互相引用该碰撞，任一单独修改会漏另一侧。

## 五条 entry 事实基线

| entry_id | wp_code | 科目 / 方向 | sheets | 公式格 | 带 fx | HTML child | prog | OO 兜底 | mount | 载体 kind | switch | BP 数 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `xlsx/gt-n1-deferred-tax-assets` | N1D | 1811 资产 / 借 | 10 | 593 | 8 | 8 | 1 | 1 | 2 | `per_entry_composable_three_modes` | redeemable | 9 |
| `xlsx/gt-n2-taxes-payable` | N2T | 2221 负债 / 贷 | **18** | **710** | 16 | 14 | 0 | 4 | 3 | `per_entry_wrapper_over_shared_base` | redeemable | 8 |
| `xlsx/gt-n3-deferred-tax-liabilities` | N3D | 2901 负债 / 贷 | 6 | 162 | 4 | 4 | 0 | 2 | 3 | **`host_inline_real`** | redeemable | 9 |
| **`xlsx/gt-n4-taxes-and-surcharges`** | N4T | 6403 损益 / 借 | 9 | 236 | 7 | 6 | 1 | 2 | 3 | **`host_inline_inert`** | **inert** | **8** |
| `xlsx/gt-n5-income-tax-expense` | N5I | 6801 损益 / 借 | **16** | 484 | 14 | 13 | 0 | 3 | 4 | `host_inline_inert` | **inert** | **10** |

算术：sheets **59** = HTML child **45** + prog **2** + OO 兜底 **12** ✓ · 公式格 **2185** ✓ · 带 fx **49** ✓ · mount **15** ✓ · OO 兜底四类穷举 5 + 3 + 3 + 1 = **12**（无 other 桶）· `dual_mode_switchable_sheets` **45**

## NC-1 ~ NC-37 共同裁决对照表

判定图例：✅ 沿用 · ⚠️ 变形（判据方向不变但锚点/口径须改）· ❌ 不适用（空分母）· 🔁 反转（M 轮结论在 N 被证伪）

| NC | 主题 | MC 基准 | 判定 | N 侧现算分母 | 判据正文归属 |
|---|---|---|---|---|---|
| NC-1 | manifest 与 slice 分歧如实登记 | MC-1 | ✅ | 5 entry / BP-9 | foundation |
| NC-2 | 载体族并存，禁单一形态假设 | MC-2 | ⚠️ | 3 族 4 亚族 / `*EntryDualMode.ts` = **0** | foundation |
| NC-3 | 端点字面量须认反引号 + 先剥注释 | MC-3 | ✅ | publish-to-tb CODE 5 : CMT 15 | foundation |
| NC-4 | 确认门与发布门分居不同模块 | MC-4 | ✅ | confirm 26 / 17 文件，交集 0 | foundation |
| NC-5 | strict 域口径含小写 `n{1..5}` 分支 | MC-5 | ⚠️ | 160（生产 135）/ 漏 35 | foundation |
| NC-6 | 行身份正面样板可抄 | MC-6 | 🔁 | by_rowid **13**（M 为 0） | foundation |
| NC-7 | `removeRow` 签名族四元组 | MC-7 | ✅ | 14 种 / 32 命中 / 18 : 13 : 1 | foundation |
| NC-8 | 位置化族分类，无 `row-` 中缀 | MC-8 | ⚠️ | 六族，M 式 = **0** | foundation |
| NC-9 | `definedName` 断链登记 | MC-9 | ⚠️ | 72 / broken 45，**N4/N5 各 0** | foundation |
| NC-10 | sheet 名禁归一化 | MC-10 | ✅ | 脏形态 **3 种** / 程序表 8 张 6 形态 | foundation |
| NC-11 | 扫描口径差须登记 | MC-11 | ✅ | 8 组口径差 | foundation |
| NC-12 | notice 接线，tooltip 不算 | MC-12 | ✅ | N 域 **0** / 全域 53 | foundation |
| NC-13 | segmented 门控与 inert 判别 | MC-13 | ⚠️ | inert 2（宿主内联空实现） | foundation |
| NC-14 | `derived_total` 双正则 | MC-14 | ✅ | TAIL 28 : MID 37（均衡） | foundation |
| NC-15 | `item_id` 命名轴 / 双 owner 声明 | MC-15 | ⚠️ | owner 6 处 / N1 双声明 1 | foundation |
| NC-16 | localStorage 分区声明点 | MC-16 | ⚠️ | 键 `n1-dual-mode`（wp 分区） | foundation |
| NC-17 | 「合计漏加小计」须双条件判 | MC-17 | ⚠️ | 真值 **0** / 粗口径误报 **8** | foundation |
| NC-18 | canary 判据回归真库有载荷 | MC-18 | 🔁 | `N4-1-rows` **1665 B** | foundation |
| NC-19 | 跨循环键双向 + G8 污染汇聚 | MC-19 | ⚠️ | 被引 4 源 / 引外 8 键 / 污染 **4** | foundation（污染）+ lane3（外引） |
| NC-20 | 空分母纪律 + 结构性零变异证明 | MC-20 | ✅ | 结构性零 16 项 | foundation |
| NC-21 | 跨册复制残留（外来字母码） | MC-21 | ⚠️ | `O1A`(N2) / `O2A`(N4) | foundation |
| NC-22 | 科目性质四分，禁假设同方向 | MC-22 | ⚠️ | 2 资产负债（借贷相反）+ 2 损益 | foundation |
| NC-23 | `SHEET_MAP` 常量映射 | MC-23 | ❌ | **N 域无此形态，空分母** | — |
| NC-24 | 历史 sheet（「原底稿」）过滤 | MC-24 | ⚠️ | 3 张 / **三形态各不同** | foundation |
| NC-25 | 已归档 spec 交付边界核对 | MC-25 | ⚠️ | **16 份 / 494 task 全 done** | foundation |
| NC-26 | 脏字面量登记（BP-11 对应项） | MC-26 | ⚠️ | 尾随空格 1 + 缺右括号 1 | foundation |
| NC-27 | 「原底稿」空格形态穷举 | MC-27 | ⚠️ | 全角空格 / 全角括号 / 半角+前导 | foundation |
| NC-28 | `resolveProcedureSheetKey` 路由欠账 | MC-28 | 🔁 | **N 段已完备 5/5，无欠账** | foundation |
| NC-29 | 行数口径 + 上游计数错误 | MC-29 | ✅ | plan 1325 vs 真值 **1331** | foundation |
| NC-30 | `transport_key_resolution` 解析链 | — (N 独有) | 新增 | TK-1~6 / clean 2 : defect 4 | foundation |
| NC-31 | `parent_duplicate` 条件节首次触发 | — (N 独有) | 新增 | **4 条全挂 N1**（K/L/M 均 0） | foundation（判据）+ lane2（数据） |
| NC-32 | wp_code 与 Excel A1 引用同形 | — (N 独有) | 新增 | 真缺陷 **3** / 残留 11 / 合法 3 | foundation |
| NC-33 | slice schema 校验器拒收诚实声明 | — (N 独有) | 新增 | 平台级，标 `[ ]*` | foundation |
| NC-34 | `conclusion` 是 N 主载荷 | — (N 独有) | 🔁 | 非空 **23**（remark 仅 4） | foundation |
| NC-35 | 超宽表 256 列 + 幽灵列 | — (N 独有) | 新增 | 2 张 / 幽灵 249 + 251 | foundation（判据）+ lane2/lane3（数据） |
| NC-36 | footer 三形态（缺斜杠） | — (N 独有) | 新增 | 49 / 7 / **3** = 59 | foundation |
| NC-37 | prefill 分母非空 ⇒ KC-17 适用 | KC-17 | 🔁 | CODE **76** / 16 文件 | foundation |

**编号完整性（逐条数表格得出，禁凭印象）**：NC-1 ~ NC-37 连续无缺号、无重号，判定分布 **10 + 15 + 5 + 1 + 6 = 37** ✓

| 判定 | 条数 | 编号 |
|---|---|---|
| ✅ 沿用 | **10** | NC-1 / 3 / 4 / 7 / 10 / 11 / 12 / 14 / 20 / 29 |
| ⚠️ 变形 | **15** | NC-2 / 5 / 8 / 9 / 13 / 15 / 16 / 17 / 19 / 21 / 22 / 24 / 25 / 26 / 27 |
| 🔁 反转 | **5** | NC-6 / 18 / 28 / 34 / 37 |
| ❌ 不适用 | **1** | NC-23 |
| 新增（N 独有） | **6** | NC-30 / 31 / 32 / 33 / 35 / 36 |

🔴 NC-34 与 NC-37 虽属 N 独有发现，但因各自证伪了 M 轮既有结论（`conclusion` 死字段 / prefill 空分母），计入 🔁 而非「新增」，避免双重计数。

## 关键判据的可执行形式

以下条目的判据若照抄 M 轮实现必假红或静默漏检，故给出可执行规格。

### NC-5 · strict 域文件集三路取并

```
is_n_domain(path, text):
    seg   = 路径含 /n1/ … /n5/ 目录段
    upper = 文件名匹配 ^(?:use|Gt)?N[1-5](?![0-9])(?:[A-Z]|[-.]|$)
    lower = 文件名匹配 ^n[1-5][A-Z]                      # 🔴 M 轮缺此分支，漏 35 个
    ref   = 内容含 N 键引用 且 文件名以 nCycle 开头       # 🔴 nCycleTaxConsistency.ts 专项
    return seg or upper or lower or ref
```
断言：总 **160**（生产 135 / 测试 25）· `loose_only` = **0** · 仅用 `upper` 时漏 **35**（生产 13 + 测试 22）。变异证明：把 `lower` 分支去掉，orphan 数应从 8 降为 6。

### NC-7 · `removeRow` 归类四元组

```
classify(first_arg):
    if /rowId|rowKey|\.id\b/       -> by_rowid      # 13
    elif /index|idx|\$index|\.length/ -> by_index   # 18
    else                            -> other        # 1
```
断言：签名种类 **14** / 总命中 **32** / by_index **18** : by_rowid **13** : other **1**。
🔴 目标态判据是「by_index 单调下降、by_rowid 单调上升」，SHALL NOT 断言「by_rowid 从 0 建起」（M 轮形态）。

### NC-17 · 「合计漏加小计」双条件判据

```
is_missing_subtotal(total_row, subtotal_rows, formula_cells):
    cond1 = 存在小计行位于 total_row 所属连续段区间内
    cond2 = 同一 total_row 内跨列公式写法不一致        # 🔴 缺此条必误报
    return cond1 and cond2
```
断言：真值 **0**；仅用 cond1 时误报 **8**（N1 两张附注披露 r42 / r52 / r63 / r72 —— 四段各自独立，且同一合计行内全列写法一致）。变异证明：同一扫描器在 M 域 M10 上应命中（M10 是「4 列加齐 vs 10 列漏加」的真不一致）。

### NC-30 · `transport_key` 解析（TK-2 的恒假陷阱）

```
# ❌ 错误判据（恒假）：在源码中找 'N1-1-adj-0' … 'N1-1-adj-6' 字面量 —— 7 个全不存在（运行时拼接）
# ✅ 正确判据（双条件）：
cond1 = owner 模块 useN1Adjudication.ts 含模板串 'N1-1-adj'
cond2 = len(N1_ADJUDICATION_CATEGORIES) == 7
```
断言：owner 常量 **6** 处逐一吻合 · clean **2**（TK-1 / TK-4）: with_defect **4** · `two_source_declarations` **1**（N1）。
另：**8 个 `nonexistent_guessed_keys` 各 0 命中**（反向分母成立）；而 `N4-1-rows-v2` 命中 **1**（orphan 自身）⇒ 两类不混。

### NC-32 · 超列引用三族判据（先剔引号段）

```
scan_overflow_col_ref(sheet):
    f = 剔除 '...'! 段、中文 sheet 名 ! 段、函数名        # 🔴 不剔则误报 215
    for m in re.finditer(r'(?<![A-Z0-9_!])([A-Z]{1,3})(\d+)', f):
        if col_index(m[1]) > sheet.max_column:
            族B if 该引用是 SUM 区间终点
            族A2 if 同列全行同形（无反向分母）
            族A1 otherwise（有反向分母 ⇒ 真缺陷）
```
断言：正确口径 **17** = A1 **3** + A2 **11** + B **3**；错口径 **232**（误报 215）。

### NC-34 · 契约字段双列映射

```
payload_columns = ['remark', 'conclusion']    # 🔴 M/L 轮只有 'remark'
```
断言：真库 `item_id ~ '^N[1-5]'` 共 **30** 行；`conclusion` 非空 **23** > `remark` 非空 **4**；`remark` 4 行中 **3** 行为 AI 会话（各 261 B）⇒ 真业务载荷仅 **1** 行。冲突优先级与语义边界见「契约字段语义」小节。

### 契约字段语义

| 列 | N 域实际承载 | 双向回写处理 |
|---|---|---|
| `conclusion` | 披露表结构化数据（`N1-disclosure-*` 1196~1201 B）+ 明细行（`N1-5-rows` 363 B） | 读写；解析失败时保留原文不覆盖 |
| `remark` | 业务行表（`N4-1-rows` 1665 B）+ AI 复核会话（`*-review-session-*` 各 261 B） | 读写；🔴 `*-review-session-*` 键须白名单排除，SHALL NOT 当业务载荷解析 |

冲突优先级：同一 `item_id` 两列都非空时，以 `item_id` 后缀判定 —— `-rows` / `-entries` 后缀取 `remark`，`-disclosure-*` 后缀取 `conclusion`；两者都不匹配时记冲突并跳过写入（不猜）。

## 模板层缺陷台账（只登记不修改，见 Requirement 7）

| # | 位置 | 形态 | 性质 | 反向分母 | 归属 |
|---|---|---|---|---|---|
| T-1 | `N4/税金及附加明细表N4-2` **E9** | `=B9+C9+`**`N4`**（应为 `D9`） | 🔴 真缺陷，静默吞第三分量 | **9 : 1** | foundation |
| T-2 | `N5/加计扣除研发费用情况明细表N5-6-1` **E12** | `=C12+`**`N5`**（应为 `D12`） | 🔴 真缺陷 | **37 : 1** | lane3 |
| T-3 | `N5/递延所得税费用核对表N5-8` **H12** | `=C12-B12+`**`N5`**`-E12-F12+G12` | 🔴 真缺陷，连带 r39 `=SUM(H10:H38)` 错 | **28 : 1** | lane3 |
| T-4 | `N3/递延所得税负债明细表N3-2` **H11~H21** | `=F#+O#`（行偏移 −8，列 O > max_column 14） | 🔴 结构残留，整列失效（H ≡ F） | **无**（11 行全同形） | lane2 |
| T-5 | `N3-2 E23` / `N4-2 D19` / `N5-6-1 D11` | `=SUM(E3:O22)` 等矩形区间超列 | ✅ 合法（SUM 忽略空列） | — | 各 lane |
| T-6 | `'税金及附加审计程序表N4A '` | 尾随半角空格 | 脏字面量 | — | foundation |
| T-7 | `'附注披露信息（国企'`（N5） | 缺右括号 | 脏字面量 | — | lane3 |
| T-8 | `递延所得税资产审计程序表的N1A` 等 **3** 处 | 「表的{码}」多字 | 脏字面量（slice 未记） | — | lane2 ×2 + lane2(N3) ×1 |
| T-9 | `N3A` | 同码存在于 N3 册与 N5 册 | 🔴 跨册碰撞，**横跨两 lane** | — | lane2 + lane3 |
| T-10 | `O1A`(N2 册) / `O2A`(N4 册) | 外来字母码 | 跨册复制残留 | — | lane3 / foundation |
| T-11 | `N1/附注披露信息（国企）` 256 列 · `N5/附注披露信息（国企` 255 列 | 幽灵列 249 / 251 | 🔴 遍历性能风险 | — | lane2 / lane3 |
| T-12 | `N2/出口退税额复核示例` · `N4/…O2A（原底稿）` · `N5/…N3A (原底稿)` | footer `&P&N` 缺斜杠 | 形态不一致 | 49 : 3 | foundation ×1 + lane3 ×2 |
| T-13 | N1 / N2 / N3 各 15 个 broken `definedName` | `#REF!` / `[1]Breakdown!#REF!` / 🔴 `'[2]2004'!#REF!` | 外部工作簿断链 | 72 : 45 | lane2 ×30 + lane3 ×15 |
| T-14 | `本循环科目` | 中文 definedName 且 broken | 断链 | — | lane2/lane3 |
| T-15 | `N5/纳税调整明细表N5-5` r63 | 「合计」标签在 **B 列**非 A 列 | 判据须改「首个非空列」 | 33 : 1 | lane3 |

🔴 **T-1 / T-2 / T-3 同源**：三处全是 `D` 列被替换为本册 wp_code（`N4` / `N5`），两处在第 12 行、一处第 9 行，分布三张不同 sheet、三个不同册 ⇒ 判为**系统性操作残留**。机理 = wp_code 与 Excel A1 引用语法同形，列 N 超出本表 `max_column`（11 / 7 / 10）⇒ Excel 不报错、取值恒空。

🔴 **T-4 不可与 T-1~T-3 合并**：前者无反向分母（整列一致失效，属结构残留），后者有强反向分母（个别行录入事故）。

## 口径差对照表（数字不同 ≠ 事实变化）

| 项 | slice / plan 声明 | 本轮现算 | 差因 |
|---|---|---|---|
| 行身份 B（数组位置寻址） | 48 | **67** | 本轮口径扩项：含 `(rowIndex,` / `[index]` / `filter((r,i)=>i!==` |
| 行身份 C（展示序号） | 8 | **7** | 口径收紧 1 |
| 行身份 D（熵键） | 13 | **29** | 口径扩项 |
| 行身份 E（稳定身份） | 未单列 | **86** / 27 文件 | slice 无此族 |
| 契约目录 | 11 | **30**（生产 28 + candidate 2） | 🔴 slice 严重过期；`adapter_id` 非空仍 5 ⇒ 28 : 5 |
| notice 生产消费方 | 41 | **53** | slice 过期 |
| 配对数 | 🔴 slice 内部矛盾（55 对 / 66 对） | 现算 `C(len(slices),2)` | 禁引用任一硬编码值 |
| orphan 合计行数 | plan **1325** / slice **1331** | **1331** | 🔴 plan 错（`useN4AdjudicationV2` 288→294 · non_dual_mode 773→779） |
| 超列引用 | 未记录 | **17**（错口径 232） | 不剔引号段则误报 215 |
| sheet 名脏形态 | 2 种 | **3 种** | slice 漏「表的{码}」3 处 |
| footer 形态 | 未记录 | **3 种** | slice 无此项 |
| 超宽表 / 幽灵列 | 未记录 | 2 张 / 24 处 | slice 无此项 |
| 真库跨 entry 污染 | 🔴 `cross_entry_isolation` 只扫代码 | **4** 条（全落 G8） | 连续两轮（L / N）漏检 |
| 共享基类 statement 边 | — | **26 生产 + 1 测试 = 27** | N 贡献 1，after 25 |

## 结构性零清单（各须变异证明，见 Requirement 8）

`trial-balance/writeback` 生产 0 · `#REF!` 死公式 0 · 越界引用（按目标 sheet `max_row`）0 · dangling sheet 引用 0 · 合计漏加小计（双条件）0 · 倒挤减法链（严格）0 · `*EntryDualMode.ts` 0 · `useChecklistPersistence` 0 · `contract-ocr` 0 · `GtEntrySyncCapabilityNotice` 0 · `http.put` 0 · `api.put` 0 · `loose_only` 0 · M 式 `row-${n}` 中缀 0 · N4/N5 的 `definedName` 0 · 8 个 `nonexistent_guessed_keys` 各 0 —— 共 **16** 项。

🔴 其中两项须附「误报/候选」对照：合计漏加小计（粗口径误报 **8**）· 倒挤减法链（形态候选 **32** 全属正常业务，含 `N5-8 H10~H38` 29 行同构核对公式与 `N2-6 F39` 应纳税额计算）。

## Property 清单（NF-P1 ~ NF-P40）

前缀 **NF-P** 为本 spec 专属，lane2 用 **NA-P**、lane3 用 **NB-P**，三者不重号。所有现算值禁写死在断言里（须由扫描器读源后比对）。

| # | 断言 | 现算值 | 关联 NC |
|---|---|---|---|
| NF-P1 | entry 清单为 5 条且全名逐一吻合 | 5 | NC-1 |
| NF-P2 | wp_code / 科目 / 借贷方向四分映射 | 2 资产负债 + 2 损益 | NC-22 |
| NF-P3 | sheets 归属算术 | 9 + 16 + 34 = 59 | NC-1 |
| NF-P4 | 公式格总数 + `data_only=True` 反证 | 2185 / 反证 0 | NC-20 |
| NF-P5 | 模板 sha256 与 size 全 match（禁改模板） | 5/5 · 5/5 | NC-25 |
| NF-P6 | `publish-to-tb` CODE 5 · `trial-balance/writeback` 0 | 5 / 0 | NC-3 |
| NF-P7 | confirm 与发布门交集为 0，且容忍 N5 无同名 composable | 26 / 17 文件 / 交集 0 | NC-4 |
| NF-P8 | 载体三族四亚族 · `*EntryDualMode.ts` = 0 | 3 族 / 0 | NC-2 |
| NF-P9 | 识别带泛型 `ref<...>(` 与 `isOnlyOffice` 门控变体 | N3 / N1 各 1 | NC-13 |
| NF-P10 | strict 总 160（生产 135）· 去小写分支漏 35 | 160 / 35 | NC-5 |
| NF-P11 | orphan 8 个 · 归属 3+2+3 · 合计行数 1331 | 8 / 1331 | NC-5 · NC-29 |
| NF-P12 | 行身份六族现算值（A3 / B67 / C7 / D29 / E86 / M式0） | 见口径差表 | NC-8 |
| NF-P13 | `removeRow` 14 种 / 32 命中 / 18 : 13 : 1 | 32 | NC-7 |
| NF-P14 | `transport_key` owner 6 处 · TK-2 用双条件判据 | 6 / 7 类目 | NC-30 |
| NF-P15 | 8 个不存在键各 0 · `N4-1-rows-v2` 命中 1 | 0 / 1 | NC-30 |
| NF-P16 | 真库 30 行 · `conclusion` 非空 23 > `remark` 非空 4 | 30 / 23 / 4 | NC-34 |
| NF-P17 | canary `N4-1-rows` = 1665 B 且 `rowKey` 为稳定语义键 | 1665 B | NC-18 |
| NF-P18 | 真库跨 entry 污染 4 条全落 `wp_code='G8'` | 4 | NC-19 |
| NF-P19 | N5 外引 8 键跨 5 命名空间（判据在此，数据在 lane3） | 8 / 5 | NC-19 |
| NF-P20 | 超列引用 17 = A1 3 + A2 11 + B 3 · 错口径 232 | 17 / 232 | NC-32 |
| NF-P21 | 合计漏加小计双条件判 = 0 · 粗口径误报 8 | 0 / 8 | NC-17 |
| NF-P22 | 倒挤减法链严格 = 0 · 形态候选 32 全正常 | 0 / 32 | NC-20 |
| NF-P23 | sheet 名 3 种脏形态 · 程序表 8 张 6 形态 · 禁归一化 | 3 / 8 / 6 | NC-10 · NC-26 |
| NF-P24 | hidden 8（GT_Custom 5 + 原底稿 3）与 OO 兜底 12 口径差 4 | 8 / 12 / 4 | NC-24 |
| NF-P25 | footer 三形态 49 / 7 / 3 = 59 | 59 | NC-36 |
| NF-P26 | `definedName` 72 / broken 45 · N4·N5 各 0 | 72 / 45 | NC-9 |
| NF-P27 | 超宽表 2 张（幽灵 249 / 251）· 幽灵列 24 处 | 2 / 24 | NC-35 |
| NF-P28 | 变体轴 4 : 1 · N3 无附注披露 | 4 : 1 | NC-22 |
| NF-P29 | `derived_total` TAIL 28 : MID 37（禁称单正则漏八成） | 28 : 37 | NC-14 |
| NF-P30 | `prefill` CODE 76 / 16 文件 · `onlyoffice-config` 1（N1） | 76 / 1 | NC-37 |
| NF-P31 | `cycleSheetRouting` 采用方 3 · N1·N3 未采用（BP-10） | 3 / 2 | NC-19 |
| NF-P32 | `resolveProcedureSheetKey` N 段完备 5/5 · M 段仍 6 | 5 / 6 | NC-28 |
| NF-P33 | `parent_duplicate` 4 条全挂 N1（K/L/M 均 0） | 4 / 0 | NC-31 |
| NF-P34 | BP 公共 7 · 区分项成员集 · 逐 entry 9/8/9/8/10 | 7 | NC-1 |
| NF-P35 | 结构性零 16 项各附变异证明 | 16 | NC-20 |
| NF-P36 | 口径差 14 组全部登记 | 14 | NC-11 |
| NF-P37 | 配对数现算 `C(len(slices),2)`，禁引用 slice 矛盾值 | 现算 | NC-11 |
| NF-P38 | 契约目录 30（生产 28 + candidate 2）· `adapter_id` 非空 5 | 28 : 5 | NC-11 |
| NF-P39 | notice 全域 53 · N 域 0（须新接入） | 53 / 0 | NC-12 |
| NF-P40 | slice schema 校验器缺陷已登记且未删诚实声明 | 平台级 `[ ]*` | NC-33 |

**编号完整性**：NF-P1 ~ NF-P40 连续 **40** 条，无缺号无重号；每条至少关联一个 NC 编号（引用闭合性在跨 spec 复盘校验）。

## 算术自检（交付前必跑，任一不等即视为归属错）

| 量 | foundation | lane2 | lane3 | 合计 | 权威值 |
|---|---|---|---|---|---|
| sheets | 9 | 16 | 34 | **59** | 59 ✓ |
| 公式格 | 236 | 755 | 1194 | **2185** | 2185 ✓ |
| 带 fx sheet | 7 | 12 | 30 | **49** | 49 ✓ |
| HTML child | 6 | 12 | 27 | **45** | 45 ✓ |
| prog console | 1 | 1 | 0 | **2** | 2 ✓ |
| OO 兜底 | 2 | 3 | 7 | **12** | 12 ✓ |
| OO 挂点 mount | 3 | 5 | 7 | **15** | 15 ✓ |
| orphan 文件 | 3 | 2 | 3 | **8** | 8 ✓ |
| live dual-mode | 0 | 1 | 1 | **2** | 2 ✓ |
| 宿主内联载体 | 1 | 1 | 1 | **3** | 3 ✓ |
| 超列真缺陷（A1+A2） | 1 | 11 | 2 | **14** | 14 ✓ |
| `definedName` total | 0 | 48 | 24 | **72** | 72 ✓ |
| `definedName` broken | 0 | 30 | 15 | **45** | 45 ✓ |
| 真库 N 行数 | 1 | 19 | 10 | **30** | 30 ✓ |
| 跨 entry 污染 | 0 | 2 | 2 | **4** | 4 ✓ |
| footer 缺斜杠 | 1 | 0 | 2 | **3** | 3 ✓ |
| 超宽 256 列表 | 0 | 1 | 1 | **2** | 2 ✓ |

另需成立：`HTML child 45 + prog 2 + OO 兜底 12 = 59`（sheets）· OO 兜底四类穷举 `5 + 3 + 3 + 1 = 12`（无 other 桶）· `dual_mode_switchable_sheets = 45` 与 HTML child 等值 · BP 逐 entry `9 + 8 + 9 + 8 + 10` 且公共 7 项对每条 entry 成立。

## 架构决策

### 决策 1 — canary 判据回归 K/L 硬标准

M 轮因 M 域真库零业务载荷而临时改用「结构最简 + BP 最少」判据。N 域分母非空（`N4-1-rows` 1665 B），故本轮**收回硬标准**。

🔴 必须在交付物中显式声明：**M 轮换判据是 M 域特有情形的应对，不是新常态**。后续 S / A / B / C 循环须先查真库分母，分母非空则用硬标准。

### 决策 2 — canary 为 N4，短板先修再闭环

N4 满足四条硬标准，但两处短板须在闭环前处理：
1. **模式开关是 `host_inline_inert`**（`onModeChange: () => {}` 空实现）⇒ 闭环第一步是把 inert 改为可用开关，否则「双向」只有单向。
2. **`N4-2 E9` 有超列引用真缺陷**（T-1）⇒ 按 Requirement 7 登记 + 守卫锁定现状，**不在本 spec 修模板**。

### 决策 3 — 三载体不统一，只加统一判据层

N 域三种载体（`per_entry_composable_three_modes` / `per_entry_wrapper_over_shared_base` / `host_inline`）分属不同演化阶段。本 spec **不做载体归一化重构**（跨 5 entry 大改，风险远超收益），而是：
- 判据层按「能力契约」而非「实现形态」断言（有无可用 `switchMode` / health 检查 / OO 挂点）；
- 各 lane spec 在自己范围内把 inert 与宿主直调收敛到 redeemable 形态。

### 决策 4 — orphan 先抄形态后删

8 个 orphan 合计 1331 行，其中 **18 处 E 族稳定行身份正面样板**位于 `useN4AdjudicationV2.ts`（9）与 `useN4DetailV2.ts`（9）。tasks 排序硬约束：**先提取形态到正式模块，再删 orphan**。反序会丢失可抄样板。

### 决策 5 — G8 污染登记不清理

4 条跨 entry 污染与 L 轮 LC-22 同宿主，属平台级汇聚点。本 spec 登记 + 守卫锁定现值，**清理方案须跨循环统一**（否则 N 侧清理后 L 侧仍在写入），标 `[ ]*`。

### 决策 6 — 超宽表按 `last_value_col` 遍历

`N1/附注披露信息（国企）`（256 列，有值列 7）与 `N5/附注披露信息（国企`（255 列，有值列 4）为 Excel 旧版列上限痕迹。双向回写遍历上界取 `last_value_col` 而非 `max_column`，并在守卫中锁定两者差值（249 / 251），差值变化时显式失败。

## 测试策略

**测试文件**：`backend/tests/workpaper_sync/test_n_cycle_foundation_canary.py`（新建，与既存 `test_task56_n_cycle_migration.py` 并存互不覆盖）。

🔴 **测试类命名禁照抄 M 轮**：

| 类名 | 覆盖 | 与 M 轮差异 |
|---|---|---|
| `TestEntryBaselineAndArithmetic` | NF-P1 ~ NF-P5 · NF-P34 | — |
| `TestWritePathAndPublishGate` | NF-P6 · NF-P7 | — |
| `TestCarrierFamilies` | NF-P8 · NF-P9 | M 轮为单形态断言 |
| `TestStrictDomainScope` | NF-P10 | 🔴 新增小写分支变异证明 |
| `TestOrphanInventory` | NF-P11 | 🔴 M 轮名为 `TestOrphanDualModeInventory`（N 域 orphan 不止 dual-mode） |
| `TestRowIdentityFamilies` | NF-P12 · NF-P13 | 🔴 by_rowid 从 0 改为 13 |
| `TestTransportKeyResolution` | NF-P14 · NF-P15 | 🔴 **N 独有类**（M 无） |
| `TestContractFieldMapping` | NF-P16 · NF-P38 | 🔴 新增 `conclusion` 列 |
| `TestCanaryN4Closure` | NF-P17 | — |
| `TestCrossEntryPollution` | NF-P18 · NF-P19 | 🔴 新增真库侧查询 |
| `TestTemplateGeometryAndDefects` | NF-P20 ~ NF-P28 | 🔴 新增超宽表 / footer 三形态 |
| `TestScanCaliberDivergence` | NF-P29 ~ NF-P32 · NF-P36 · NF-P37 | — |
| `TestParentDuplicateCondition` | NF-P33 | 🔴 从空壳改为实装（K/L/M 均 0） |
| `TestStructuralZerosWithMutationProof` | NF-P35 · NF-P39 · NF-P40 | — |

🔴 **M 轮有而 N 轮无**：`TestProperty24ProtectedFormulaAndSummary`（N 域对应项为超列引用族，已并入 `TestTemplateGeometryAndDefects`）。

**测试原则**：
1. 所有期望值由扫描器现读源文件得出，禁在断言里写死数字（数字只出现在「与现算比对」的等式右侧，且右侧来源必须是同一次现读）。
2. 结构性零必须成对出现「零断言 + 变异证明」，单独的零断言视为未完成。
3. 模板层 sha256 断言置于最前，失败即中止（防止在被修改过的模板上跑出误导性结论）。
4. 真库相关测试用 asyncpg（🔴 `psycopg2` 未安装），每条查询独立连接；无库环境下 skip 并标记原因，SHALL NOT 静默 pass。
