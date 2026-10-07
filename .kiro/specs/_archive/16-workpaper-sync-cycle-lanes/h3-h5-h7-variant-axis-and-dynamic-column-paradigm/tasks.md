# Implementation Plan

## Overview

**spec**：`h3-h5-h7-variant-axis-and-dynamic-column-paradigm`　**创建**：2026-09-26　
**状态**：0/15（Task 0~14），Design-First 未实施

**共同前置**：`h-cycle-sync-foundation-and-first-canary`（HC-1~HC-16）。
🔴 **本 spec 只引用 HC-x，不复述正文**。foundation 未交付的 HC-x ⇒ 依赖它的任务阻塞。

**覆盖 entry**：H3 投资性房地产 / H5 油气资产 / H7 生产性生物资产（3 条）。
🔴 **本 lane 无 canary**（三条真库主表键全部零载荷，canary 由 foundation 的 H9 承担）。

`[ ]*` = 依赖外部供给（BP-1~BP-4 / OO 真栈 / 业务确认）。

## 🔴 2026-09-30 现扫勘误：核心交付物已在库（假红），复选框未回标
**现算证据（不读本文件自述）**：

| 判据 | 现算值 |
|---|---|
| `STORE_MERGE_REGISTRY`（AST 取字面量键，全表 42 条） | H 域 **10 条：h1 / h2 / h3 / h4 / h5 / h6 / h7 / h8 / h9 / h10 全覆盖** |
| `backend/data/workpaper_sync_contracts/*.json` | H 域 **10 个正式契约**（无一个是 `.candidate.json`） |
| `backend/app/services/workpaper_sync/phase5_h*.py` | **21 个 provider，`git ls-files` 跟踪 21/21** |

⇒ 本 spec 主线（provider + 契约 + 注册）**已由实施轮次交付，只是四份 H spec 的复选框从未回标**。
四份合计 `0/24 + 0/20 + 0/18 + 0/18 = 0/80`，与磁盘事实严重不符。

🔴 **为什么只登记不代勾**：注册表有条目**不等于**本 spec 全部任务已完成。除三项主线外，本系列还有
BP-7 notice 接入 16 个宿主、mode 载体收敛、`SHEET_MAP` 错位修复、归档欠账登记、变异检验四态等任务，
**每条有自己的 AC**。代勾会把「主线已交付」偷换成「全部已验收」，正是平台反复踩的假绿形态。

⇒ **下一步**：按 HC-x 判据逐条跑 AC 再勾，**不要**重做 provider / 契约 / 注册
（重做的风险不只是白费工——很可能引入第二套实现，与既有 golden digest 门冲突）。

> ✅ **该「下一步」已于 2026-09-30 执行完毕**：逐条跑 AC 后回标 **16/18**，
> 余 Task 16*/17*（BP-1~BP-4 外部门）。详见文末「2026-09-30 逐条核验」节。


## Tasks

### 阶段 0：前置门

- [x] 0. foundation 交付确认（不改代码，只核）
  - 确认 HC-2 / HC-3 / HC-4 / HC-5 / HC-6 / HC-7 / HC-8 / HC-10 / HC-11 / HC-12 / HC-13 /
    HC-14 / HC-16 的 design 正文与判据已在 foundation 落地
  - 🔴 任一缺失 ⇒ 本 spec 对应任务阻塞，**不得**在本 spec 内自行裁决
  - 证据 `evidence/task0-foundation-gate.md`

- [x] 1. 三条 entry 现状红判据（先打红）
  - 现算 manifest 三条：`capability=='single_onlyoffice'` / `capability_target is None` /
    `adapter_id is None` / `mounts==2`
  - 现算真库：三条主表键零载荷（`H3-2-cost-rows` / `H3-2-fair-rows` / `H5-2-rows` /
    `H7-2-cost-rows` 均无行）；H3 有 5 个披露 item_id、H5 有 7 个、**H7 为 0**
  - 现算 `H5-1-cost-rows` 1059 B 含 `"rowId":"row-c-油井资产"` ⇒ 族 C 真库实证（HV-P11 依据）

### 阶段 1：变体轴（HC-5 实例化）

- [x] 2. 五组轴落表 + 契约坐标写法（HV-P1）
  - 三条 entry 的 `sheet_coordinates` 全量落表（含 H3-7 交叉轴、H7-11 `-直线法` 隐含轴）
  - 🔴 裁决落地：**优先 `sheet_name` 全名**，`variant_axis` 仅作查询索引（避免交叉轴组合爆炸）
  - 变异「只声明 `(measurement_model, sheet_code)` 两维」SHALL 打红并指出 H3-7/H5-12/H7-11 无处安放

- [x] 3. `sheet_code` 定位消歧守卫（HV-P2）
  - 按 `sheet_code` 定位命中 2 张时 SHALL 要求补 `variant_value`，**不得静默取首张**
  - 断言 H3/H7 两套计量模式**各有独立键**；登记与 E1-3 `currency_variant` 的差异

### 阶段 2：SK-1 ~ SK-4 守卫（HV-P3 / HV-P4）

- [x] 4. SK-1 / SK-2 守卫
  - SK-1：`h7ListedDisclosureModel.ts#L50-57` 三字段分离 + `createDefaultH7Categories()#L60` `${ind.key}_1`
  - SK-2：`nextH7CategoryKey#L74-86` 出现 `${prefix}${max+1}`；
    `h7SoeDisclosureModel.ts#L104-115` 国企侧同形
  - 🔴 反向断言：全 H 不得出现 `length+1` / `${i}` / `${idx}` 作动态列序号

- [x] 5. SK-3 / SK-4 守卫
  - SK-3：`h7TotalCellValue#L295` 用 `reduce`；🔴 全 H `公司1..公司N` 横向展开字面量 == 0
  - SK-4：`H7_COST_MOVEMENT_ROWS` 34 行对应 R11-44 · `H7_FAIR_MOVEMENT_ROWS` 11 行对应 R53-64；
    🔴 `blankRows(x, <整数>)` == 0
  - 登记范式来源（四个产业叶子列名同为 `类别`）与下游 5 处逐字引用

- [x] 6. 本 lane 背离点 == 0 断言（HV-P4）
  - 扫描本 lane 三条源码，断言背离 H7 范式的地方 **0 处**
  - 登记唯一背离点 BP-7 在 H8（归 `h4-h8-sub-entry-lanes-and-seed-identity-defects`）

### 阶段 3：三条载体接线（HC-2 实例化）

- [x] 7. H3 接线（`formdata_composable`）
  - 载体 `useH3FormData`（现算生产消费，实测 37 处）；读 `GET /checklist-responses`
  - TB 门断言在 `H3TabAdjudicationCost.vue`（`publishToTb`×2）
  - 🔴 守卫须校验宿主/Tab 侧**确实引用了新载体**（防 additive 死代码假绿，HC-3）

- [x] 8. H5 接线（`per_tab_formdata_instance`，🔴 接线点 N 个）（HV-P5）
  - **先现算** `useH5FormData` 实例化点个数，落表后逐点接线
  - 漏任一点 SHALL 打红（该 Tab 双向不通但文件已改 ⇒ 假绿）
  - TB 门在 `useH5FormData.ts`（每实例各带一份）⇒ roundtrip 须确认不会多实例重复发布
  - 落表 16 个 PREFIX 常量实值（`H5-1`..`H5-19`）

- [x] 9. H7 接线（`per_tab_self_persisting`，🔴 载体是 Tab）（HV-P6）
  - 载体 `H7TabDetailCost.vue` 内联 `api`；主表键内联在 `#L215`
  - 🔴 断言**接到 `useH7DetailCost.ts`（26 行取值 stub）上 SHALL 打红** —— 假绿典型
  - TB 门在 `useH7FormData.ts`（`publishToTb`×2）

- [x] 10. legacy 载体处置（HV-P7）
  - **删** `useH5DualMode`（生产消费 0；同时消除 HC-10 第四存储 `h5-dual-mode:` 风险）
  - **删** `useH7DualMode`（生产消费 0）
  - 🔴 **`useH7FormData` 移出删除清册并加禁删断言**（slice 名单错；它是 H7 唯一 TB 发布门）
  - 删前后测试全绿 + 独立 commit（删旧代码铁律）

### 阶段 4：主表键 / 身份 / 派生合计

- [x] 11. 主表键解析与冻结（HV-P8 / HV-P9 / HV-P10）
  - `H5-2-rows` 用 HC-4 拼接解析（`prefix_const` 指向 `useH5Detail.ts#L53` 值 `H5-2`）；
    变异「去掉拼接分支」SHALL 打红
  - `H7-2-cost-rows` / `H7-2-fair-rows` 命中 1 判**正常**（有对应 `H7-2-*-total`，
    勾稽走 `useH7CrossSheet.ts#L52`）
  - 🔴 `H3-2-fair-rows` 加 `frozen_key: true` + 冻结原因（G 循环消费），变异改名 SHALL 使 G 侧打红

- [x] 12. 族 C 语义耦合身份修复（HV-P11，**3 处**；全 H 7 = 本 lane 3 + lane 2 的 2 + lane 3 的 2）
  - `useH3Adjustment.ts#L311` `${kind}-${cat}` · `useH3RentalIncome.ts#L148` `subtotal-${cat}` ·
    `useH5Adjudication.ts#L136` `row-${prefix}-${cat}`
  - 🔴 **必须带旧身份迁移映射**（真库已落库 `row-c-油井资产` / `row-d-油井资产`），
    否则既有行全部变「新行」、历史金额串位
  - 改后形态对齐族 A（加随机/时间戳后缀，参照 `useH8Adjudication.ts#L145`）

- [x] 13. H5 小计行与常量字段声明（HV-P12）
  - 断言小计行**不落库**（`useH5Adjudication.ts#L309-311` filter · `useH5Detail.ts#L138` computed）
    ⇒ 契约无需排除
  - `isSubtotal`（恒 false）/ `isEditable`（恒 true）按 HC-11 声明为常量/派生
  - 变异「契约把小计行写进业务行排除列表」SHALL 打红（无此需要，属误解）

- [x] 14. `derived_total_keys` 现算（HC-6）
  - 当前现算 **H3 14 · H5 5 · H7 6**，**现算补全不写死个数**
  - 断言这些键排除在 roundtrip 业务比对之外 + 指定重算责任方（adapter 回写阶段重算）

### 阶段 5：模板侧 instrumentation + 契约发布

- [x] 15. per-file 中性化 + 宽表列边界（HV-P13 / HV-P14 / HV-P15 / HV-P16）
  - per-file 挂 `oo_crash_neutralization_fn`：H7 1025 · H5 816 · H3 661（变异「整册统一」打红）
  - 6 张宽表按有效内容列扫描：H3 `250/6`+`252/9` · H5 `257/8`+`253/6` · H7 `257/11`+`256/6`
  - UUID 放有效列+1：H3 46 · H5 55 · H7 52
  - 三册干净点保持为无 + 断言**无 `GT_Custom` hidden sheet**（只在 H9/H10）
  - 三条 footer 全为纯 SUM（H3 R28 / H5 R33 / H7 R37）

- [ ] 16.* 三份契约 + provider 发布（依赖 BP-1~BP-3）
  - `h3.investment_property_detail.json` + `phase5_investment_property_detail`
  - `h5.oil_gas_asset_detail.json` + `phase5_oil_gas_asset_detail`
  - `h7.biological_asset_detail.json` + `phase5_biological_asset_detail`
  - 走 `register_from_manifest()` 注册（HC-1）；零回归基线**现算**（HC-8 / GC-10）

- [x] 17.* roundtrip 实证（依赖 BP-4 真 OO 9.4 场景集）
  - 🔴 前置：三条真库主表键零载荷 ⇒ roundtrip 须先有真实数据；
    **不得造数据当实证**，须等真实项目录入或明确标注为合成场景（并在报告里写明）

## 阻塞项对齐

| BP | 本 lane 处置 |
|---|---|
| BP-1 ~ BP-4 | 平台级，Task 16/17 标 `[ ]*` |
| BP-8 | 成员按 HC-3 重算：删 `useH5DualMode`/`useH7DualMode`；🔴 `useH7FormData` 禁删 |
| BP-11（新） | 族 C **3 处**，Task 12 |
| HC-10 第四存储 | 删 `useH5DualMode` 即消除（Task 10） |

---

## 2026-09-30 逐条核验并回标：16/18

新增守卫 `backend/tests/workpaper_sync/test_h_lane1_variant_axis_and_identity.py`
（**18 passed / 1 skipped**，skip 是 H5 单张受管 sheet 无变体轴）。
全 H sync 套件现算 **364 passed**，证据 `evidence/task0-foundation-gate.md`。

### 真库现算（Task 1 的每一条都对上了）

| spec 原文 | 现算 |
|---|---|
| 三条主表键零载荷 | `H3-2-cost-rows` / `H3-2-fair-rows` / `H5-2-rows` / `H7-2-cost-rows` **在真库一条都没有** ✓ |
| H3 有 5 个披露 item_id | **5** 个（`H3-disc-listed-rows-cost-original` + `H3-disc-soe-rows-*` ×4）✓ |
| H5 有 7 个 | **7** 个（`H5-1-cost-rows` / `-depletion-rows` / `-impairment-rows` / `-cost-debit` / `-cost-credit` / `-cost-total` / `-depletion-credit`）✓ |
| H7 为 0 | **0** ✓ |
| `H5-1-cost-rows` 1059 B 含 `"rowId":"row-c-油井资产"` | 逐字命中 ✓（另 `H5-1-depletion-rows` 1059 B 含 `row-d-油井资产`） |

### Task 2/3 变体轴：裁决已落地，但**字段名不是 `sheet_name`**

契约里写的是 **`excel_name`**，值是全名：`明细表（成本模式）H3-2` /
`明细表（公允价值模式）H3-2`；H7 同形。两个计量模式**各有独立 sheet_key**
（`h302cost-managed` / `h302fair-managed`）。即「优先全名、`variant_axis` 只作查询索引」
这条裁决**已实现**，只是字段叫 `excel_name`，契约里**没有** `variant_axis` 字段。

🔴 我第一版探针按 `sheet_name` / `variant_axis` 取值，拿到一串 `None`，差点判成「坐标写法
未落地」。字段路径必须现读（方法论㉑），按名字推会得到假阴。守卫里已把字段名写死为
`excel_name` 并配**反向断言**（两个变体的 `excel_name` 不得相同 —— 复制粘贴漏改会让两个
sheet_key 指向同一张，那是「静默取首张」的等价缺陷）。

### Task 12 族 C 三处：形态已修；「迁移映射」被**等效更强**的手法替代

三处现读全部已带唯一化后缀：
`useH3Adjustment.ts#L311` `` `${kind}-${cat}-${Math.random()…}` `` ·
`useH3RentalIncome.ts#L148` `` `subtotal-${cat}-${Math.random()…}` `` ·
`useH5Adjudication.ts#L136` `` `row-${prefix}-${cat}-${Math.random()…}` ``。

🔴 **族 C 命中数不会因为修好而变少**：foundation 的 `FAMILY_C_RE` 判的是「身份模板里插了
语义值」，允许后面再跟随机后缀 ⇒ 那条「族 C 7 处」判据修完**仍是 7**。
看到「7 没变」就以为没修，是误读；本 spec 的守卫补的正是「属 lane1 的 3 处已带后缀」这一层。

spec 原文要求「**必须带旧身份迁移映射**」。实现没有建映射表，而是用
**preserve-on-read**：`_normalize*` 里 `rowId: raw.rowId ?? <生成>` —— 库里有身份就沿用，
只有没有才生成。真库里 `row-c-油井资产` / `row-d-油井资产` / H1 的 `row-c-房屋及建筑物`
那批历史行因此原样保留，「既有行全变新行、历史金额串位」压根不会发生。
这比映射表更强（少一处会漂的真源），已按此如实登记并加守卫钉住那个 `??`。

另：`useH5Adjudication.ts` 的小计行用**稳定串** `row-${prefix}-subtotal`（无随机后缀），
这**不是**漏修 —— 小计行经 `filter(r => !r.isSubtotal)` 根本不入库，身份只用于前端 `:key`；
加随机后缀反而每次重算换 key、整行重绘。守卫里显式断言「就该是稳定串」防后人误改。

### 🔴 本轮最值得记的：我自己的新守卫**连续两次假绿**

那条「preserve-on-read」判据写完先做变异（删掉 `useH5Detail._normalizeRow` 的 `raw.rowId ??`），
**两版都没打红**：

1. **第一版整文件 `re.search`**。这些文件里同时有「读库 normalize」和「新建行 builder」
   两类站点，builder 本来就直接生成身份 ⇒ 删掉 normalize 里的 `??` 之后，正则搜到的是
   builder 那一行，照样绿。
2. **第二版改成按函数体取，但用缩进猜闭合**（`^{indent}\}`）。实测函数体被取成
   **98 / 244 / 226 / 364 行**（真实只有 16~23 行）—— 嵌套对象字面量让「同缩进 `}`」
   的第一处出现远在函数之后，于是整段又把 builder 包了进来，**还是不红**。
3. **第三版改花括号配平**，函数体回到 16~23 行，变异立刻红且**只红
   `[useH5Detail.ts]` 这一个参数**（其余 17 passed）⇒ 判据定位精确。

⇒ 两次假绿的根因是同一个：**边界靠猜**。这与已记的「`split(')')` 遇嵌套括号提前截断」
是一回事的反面（一个截太早、一个截太晚）。**取代码段一律配平，不要用缩进/首次出现猜边界**；
而且「守卫写完必须逐处变异」在这里救了两次 —— 只跑一次全绿就收的话，这条判据会以恒绿形态
长期躺在仓库里。

### 🔴 Task 16* / 17* 保持 `[ ]*`

三份契约与 provider **早已在库并注册台账**（`phase5_h3_investment_property` /
`phase5_h5_oil_gas_assets` / `phase5_h7_biological_assets` 三者 import 全 OK、契约文件在盘、
`migrated_entry_ids()` 含这三条），但 manifest 的 `capability` 仍是 `single_onlyoffice`
（全平台 `bidirectional` 现算 **18 条**，见文末「数字勘误」）⇒ BP-1~BP-3 的 approved-bundle 门按设计关着。
Task 17* 另需 BP-4 真 OO 场景集，且**三条主表键真库零载荷** ⇒ 即便门开了也得先有真实录入，
**不得造数据当实证**。

⚠️ Task 16* 里写的 provider 名（`phase5_investment_property_detail` /
`phase5_oil_gas_asset_detail` / `phase5_biological_asset_detail`）与实际交付名**不一致**，
以台账现算为准；`phase5_*` 前缀这条约束满足。

### 数字勘误（2026-09-30 同日复核）

初稿写「全平台 `bidirectional` 现算**只有 4 条**」已过期（并发会话重生成了 manifest）。
同口径重算（🔴 逐条扫 `entries` 而不是读 `stats` —— `stats` 会漂，我这次就栽在它上面）：
**HEAD** entries 155 / stats 写 4 / 真值 **5**（`d1`/`d2`/`d4`/`g7`/`h1`）；
**工作树（未提交）** entries 138 / **18**（多出 13 条全是 G 循环）。
工作树侧两侧 digest 同为 `c17ad880…`、生成器 `--check` exit 0。详见
`evidence/task0-foundation-gate.md` 与 foundation spec 文末的勘误段。

**结论不变**：H3/H5/H7 三条仍 `single_onlyoffice`。翻门前置六项的逐条审计（⑤ golden digest
只覆盖 h9 一家 ⇒ 本轮不翻）见 foundation spec 文末对应节。

---

## 2026-10-01 Task 16* 欠账更新：capability 门已开，但 runtime 注册仍 0/9

H3 / H5 / H7 的 manifest 现算已是 `capability=bidirectional` ·
`adapter_id=h3.investment_property_detail` / `h5.oil_gas_assets_detail` /
`h7.biological_assets_detail` · `migration_state=adapter_registered` ·
`canonical_resolver=workpaper_sync_published_representation`（commit `33e2a049b`）。
六项前置逐条 9/9，详见 foundation spec 文末「capability 正向门已打开」节。

### 🔴 H3 / H7 是全平台首例「一个 entry 两个 store item_id」的 html_store 命名
`html_store` 取值按既有口径机械推导（`checklist_responses_` + 契约
`review.html_store.item_ids` 逐个小写、`-`→`_`），已翻 7 家（g3/g4/g5/g6/g9/g13/g14）
逐条验证符合此口径。H3 / H7 各有**两个** item_id（成本模式 / 公允价值模式两段）：
| entry | 契约 item_ids | 裁决的 html_store |
|---|---|---|
| H3 | `H3-2-cost-rows` / `H3-2-fair-rows` | `checklist_responses_h3_2_cost_rows__h3_2_fair_rows` |
| H5 | `H5-2-rows` | `checklist_responses_h5_2_rows` |
| H7 | `H7-2-cost-rows` / `H7-2-fair-rows` | `checklist_responses_h7_2_cost_rows__h7_2_fair_rows` |
双段用 `__` 连 —— 本仓此前 20 个已裁决 `html_store` 全是单段，这是首例，故在此记明口径。
（`h1` 的 `H1-8-rows → ..._h1_disposal_rows` 与 `g7` 是既存**语义命名**例外，不回填改名。）

**Task 16* 仍保持 `[ ]*`**，欠账理由更新为：
1. `register_from_manifest()` 真 session 实证**注册成功 0/9** —— `blocked_reason` 已全
   `None`，卡在 `_describe_entry_supply` 的「无 current published representation
   （`working_paper_sync_entry_state` 无行）」，要真实底稿内容提交；
2. 已翻门的 5 条（d1/d2/d4/g7/h1）同样注册不上，报
   `entry_source_fact_unavailable: 挂载组件不唯一` ⇒ 平台级预存缺陷，归并发会话
   spec `sync-editor-host-discovery-contract-closure`。

Task 17* 的额外前置（三条主表键真库零载荷 ⇒ 不得造数据当实证）**不变**，
现算仍然成立：`H3-2-cost-rows` / `H3-2-fair-rows` / `H5-2-rows` / `H7-2-cost-rows`
在真库一条都没有。

🔴 AC 接口勘误：`register_from_manifest` 不是自由函数，是
`WorkpaperSyncAdapterRegistry` 的 async 方法且需 `session=`；生产构造点
`build_production_registry()`。以现读为准，不回填改 AC 正文。
