# Implementation Plan

## Overview

**spec**：`h-cycle-sync-foundation-and-first-canary`　**创建**：2026-09-26　
**状态**：0/21（Task 0~20），Design-First 未实施

**上游**：umbrella Task 50（H slice 冻结口径）· FC-1~FC-13（`f1-sync-coverage-and-first-canary/design.md`）·
GC-1~GC-10（`g-cycle-sync-foundation-and-first-canary/design.md`）· D1 引擎 ·
`g7_oo_crash_if_neutralize.py`（HC-12 唯一复用 pilot 的产物）

`[ ]*` = 依赖外部供给（BP-1~BP-4 / OO 真栈 / 业务确认）。

🔴 **本 spec 是三份 lane spec 的共同前置**：HC-1~HC-16 在此裁一次，下游只引用。
canary 只做 **H9** 一条。

🔴 **不得修改 H1 pilot 的契约 / adapter / golden digest**（HC-8）。

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


## Tasks

### 阶段 0：前置门 + 红判据（先打红）

- [x] 0. 前置依赖核查（`git show HEAD:` 判定，不读工作树）
  - `RowTableSheetSpec` · `merge._protection` 格级判定 · `StoreMergePlan.oo_crash_neutralization_fn` ·
    `g7_oo_crash_if_neutralize.neutralize_oo_crash_if_formulas` **函数体**
  - 🔴 该函数曾有「调用点在 HEAD、函数体从未落地」的历史（`adapters/excel.py` 两处 import 跑在
    `ImportError` 上）⇒ 必须确认函数体，不能只看 import（HC-12 第 3 条）
  - 证据 `evidence/task0-prerequisites.md`

- [x] 1. 五处 slice 不一致的红判据（HF-P3 / HF-P4 先红）
  - 写消费方计数守卫，断言实测 10 项；**先让「照抄 slice 的删除清册」打红**
  - 写主表键解析守卫（含 `` `${CONST}-suffix` `` 拼接分支），断言 11 键命中数；
    **先让「无拼接分支」版本在 `H5-2-rows` 打红**
  - 证据 `evidence/task1-slice-discrepancies.md`（逐条 slice 原文 vs 实测值 vs 处置）

- [x] 2. manifest 现算红判据（HF-P1）
  - 现算 `workpaper_sync_entry_manifest.json`（155 entries）→ 断言 9 条
    `capability=='single_onlyoffice'` 且 `capability_target is None` 且 `adapter_id is None` 且 `mounts==2`
  - 变异「手改一条为 `bidirectional` 而 adapter 仍 None」SHALL 打红
  - 5 条子入口一并断言（含补齐的 `xlsx/h8/measurement/h8-tab-measurement-monthly`）

- [x] 3. 零回归基线现算（HF-P18，GC-10）
  - 现算契约目录 `*.json` 个数与文件名集合 · 现算 `register_from_manifest()` 已注册集合 ·
    现算 `DELIVERED_ENGINE_ADAPTERS` / `PENDING_ENGINE_ADAPTERS` 成员
  - 🔴 **禁止**在守卫或 spec 里写死个数（当前现算值：契约 13 个、注册集 `{d2,d4,g7,h1}`）

### 阶段 1：HC-1 ~ HC-16 裁决落地（本 spec 的核心交付）

- [x] 4. HC-1 manifest capability 口径 + 迁移路径
  - design 正文 + 守卫；迁移只能走 `register_from_manifest()`，禁手改 manifest
  - 登记「slice 三个字段值不是 manifest 字段」并标注来源为 slice 语义注记

- [x] 5. HC-2 载体族七分表（9 行）+ 族分派守卫（HF-P2）
  - 写 4 族 / 读 4 族 / TB 门 2 族逐条落表；守卫按族标签分派
  - 🔴 断言「F 循环守卫对 H 的 6 条假红」这一事实：写一个对照测试，
    让 F 版守卫在 H 的 host_inline 4 条 + H7 + H5 上打红，证明必须改族分派
  - 断言 `useAdjustmentCentralSync` 9/9 全覆盖、宿主层 0

- [x] 6. HC-3 消费方计数判据 + 可删名单定稿（HF-P3）
  - 可删 5 个：`useH5DualMode` / `useH7DualMode` / `useH6FormData` / `useH8FormData` / `useH9FormData`
  - 🔴 禁删名单：`useH7FormData`（承载 H7 唯一 TB 发布门）· `useH9DualMode`（宿主消费）
  - 登记 `useH4DualMode` 被 4 条 entry 链式复用 ⇒ 改它需 lane 2 与 lane 3 协调
  - 断言「additive 注入即死代码」守卫：必须校验宿主/Tab 侧确实引用了新载体

- [x] 7. HC-4 拼接键解析 + H5 十六个 PREFIX 实值表（HF-P4）
  - 落表 16 个 PREFIX（H5-1..H5-19）；断言 `useH5Detail.ts#L53 ITEM_PREFIX=='H5-2'`
  - 断言 `H10-detail-rows` 身份是 `id` 且 `useH10Detail.ts` 有 `addRow`/`removeRow`
    ⇒ 属 `generated_opaque_string` 族而非 `stable_template_row_key`

- [x] 8. HC-5 变体轴三维声明（HF-P5）
  - 三族 11 组双 sheet 落表；断言每组两张 sheet 全名不同、尾码相同
  - 登记与 E1-3 `currency_variant` 的差异（各有独立键 vs 共用一键）

- [x] 9. HC-6 `derived_total_keys` + 重算责任方（HF-P6）
  - 现算全 H total 键集合并按 entry 分组落表（当前现算 **89**，H1 侧 4 + 9 条 entry 侧 **85**；
    **H8 21 最多** · H4 15 · H3 14 · H9 9 · H6 8 · H7 6 · H5 5 · H2 4 · H10 3）
  - 🔴 判据与**现算基线**比对，**禁止写死阈值**（写死会在功能演进后造假红）
  - 断言 `H7-2-cost-rows` / `H7-2-fair-rows` 命中 1 判**正常**（有对应 total 键）
  - 断言 `H8-2-detail-prefill` 判**缺陷**（无对应 total 键 + 真库零载荷）⇒ BP-5

- [x] 10. HC-7 行身份三族分治 + 族 C 扫描口径扩充（HF-P7）
  - 族 A/B/C 落表；扩充 slice `positional_identity_inventory` 正则以识别族 C
  - 断言族 C 命中 **7 处**；断言 `useH8Adjudication.ts#L145` 属族 A（有 `${rand5}`）
  - 🔴 登记迁移映射需求：真库已落库族 C 身份（`row-c-油井资产`）

- [x] 11. HC-8 跨引用图 + 6 键冻结（HF-P8）
  - 跨引用图 9 行落表；冻结 `H2-2-rows` / `H6-1-rows` / `H6-2-rows` /
    `H6-1-end-balance-audited` / `H10-detail-rows` / `H3-2-fair-rows`
  - 变异「改 `H6-2-rows`」SHALL 使 H1 侧 3 个 Pull 文件打红

- [x] 12. HC-9 猜键回退链判据（HF-P9）
  - 扫描 `const keys\s*=\s*\[` 形态，逐键断言 H 侧生产命中 > 0
  - `H6-detail-rows` / `H6-clearing-rows` SHALL 打红；修复归 lane 3

- [x] 13. HC-10 localStorage 前置断言（HF-P10）
  - 断言 roundtrip 前 `h10-draft:` 前缀键数 == 0；变异「造一条草稿」SHALL 打红
  - 登记 `useH5DualMode.STORAGE_PREFIX='h5-dual-mode:'` 的第四存储风险（处置归 lane 1）

- [x] 14. HC-11 中文枚举 + derived 字段声明（HF-P11）
  - 枚举域声明为中文字面量集合；`terminatedFromH8` 标 derived/readonly
  - 变异「把 `isConfirmed` 声明为 boolean」SHALL 打红
  - `isSubtotal` / `isEditable` 按同类处理（实测恒 false / true）

- [x] 15. HC-12 per-file 裸 IF 中性化（HF-P12）
  - 9 册计数落表（H8 3710 … H6 12）；per-file 挂 `oo_crash_neutralization_fn`
  - 变异「整册统一挂」SHALL 打红

- [x] 16. HC-13 宽表有效列 + UUID 落位（HF-P13）
  - 11 张宽表有效列落表；UUID 放「有效内容列 +1」，同源引用 G 的 16384 列规则
  - 变异「按 `max_column` 放 UUID」SHALL 打红（落在 251+ 列）

- [x] 17. HC-14 四个干净点断言「保持为无」（HF-P14）
  - definedName 0 / 漏加小计 0 / 越界引用 0 / 整册码回落 clean（26 码）/ `H2A` 返 None
  - 三条变异（塞未索引册子 / 加 definedName / `H2A` 守卫写反）SHALL 打红

- [x] 18. HC-15 wp_index 规避判据 + HC-16 footer 形态表（HF-P15 / HF-P16）
  - 契约 schema 校验断言 `source_ref` 不依赖 `wp_name` 与 wp_index 子码
  - 9 条 footer 形态落表；H6 全角空格容错 · H4 派生单价 + 除零守卫 · H10 双 footer
  - 登记 H8-6 语义冲突（wp_index vs 模板）待平台侧修正

### 阶段 2：canary H9 端到端

- [x] 19. canary 真库前置实证（HF-P17）
  - 现算 `checklist_responses`（载荷列 `remark`）断言 `H9-2-rows` 非空（≥ 819 B / 2 行）
  - 同时断言其余 8 条主表键零载荷或 `[]`（`H8-2-rows`=`[]` · `H10-detail-rows`=`[]` · 其余无行）
  - 🔴 若该断言失败（真库被清空）THEN canary 选型失效，须回到 Task 4 重选，**不得造数据顶上**
  - 证据 `evidence/task19-canary-db-evidence.md`

- [x] 20. canary 契约 + representation + provider
  - 产出 `backend/data/workpaper_sync_contracts/h9.lease_liability_detail.json`
    （字段见 design §canary 契约，`derived_total_keys` 现算补全）
  - representation 覆盖真库实证 **23 字段**：3 中文枚举 + 1 derived(`terminatedFromH8`) +
    `rowId` identity + `terminationDate` 可空
  - provider `phase5_lease_liability_detail`（`phase5_*` 范式，**不照** `pilot_*`）
  - 走 `register_from_manifest()` 注册；注册后 `capability` 才变 `bidirectional`（HC-1）
  - 几何：两级表头 R7/R8 · 数据区 R9-13 · footer R14 `SUM(B9:B13)` · 22 列 ·
    公式列 E/I/J/K/L/N · UUID 列 23

- [ ] 20a.* roundtrip 实证（依赖 BP-4 真 OO 9.4 场景集）
  - 前置断言四条（design §roundtrip 前置断言）：草稿键 0 · 冻结调整分录中央同步 ·
    排除 `derived_total_keys` · 不改 `H9-2-rows` 键名
  - 🔴 H9 **无 TB 发布门** ⇒ 本 canary **不覆盖发布链**，不得在此补发布链断言

- [ ] 20b.* 人工审核契约与 approved bundle 发布（依赖 BP-2 / BP-3）

### 阶段 3：交接给三份 lane spec

- [x] 20c. 交接清单核验（不改代码，只核）
  - HC-1~HC-16 全部有 design 正文 + 判据；三份 lane spec **无一条复述** HC 正文
  - 每条 lane spec 的 entry 归属与本 spec §三份下游 lane spec 表一致
  - 逐条确认后置项归属：BP-5/6(H4/H8 部分)/7 → lane 2 · BP-6(H2 部分)/BP-12/HC-10(H10) → lane 3 ·
    BP-8 可删 5 个 + HC-10(H5) + HC-5 实例化 → lane 1 · TB 发布链首例 → lane 3

## 阻塞项对齐

| BP | 归属 | 本 spec 交付 |
|---|---|---|
| BP-1 ~ BP-4 | 平台级（全循环共有） | 只标 `[ ]*`，不承诺 |
| BP-5 | lane 2 | HC-6 + HC-7 判据 |
| BP-6 | lane 2（H4/H8）+ lane 3（H2） | HC-7 判据 |
| BP-7 | lane 2 | SK-1 判据 |
| BP-8 | 各 lane | HC-3 判据（成员按实测重算，非 slice 名单） |
| BP-9 | 本 spec | HC-1 全文 |
| BP-10 | 已兑现（AC 1.4） | — |
| **BP-11**（新） | lane 1/2/3 分头修 | HC-7 族 C 判据 + 扫描口径扩充 |
| **BP-12**（新） | lane 3 | HC-9 判据 |

---

## 2026-09-30 逐条核验并回标：22/24（原 0/24 是**假红**）

**为什么原来是 0/24**：主线交付（provider + 契约 + 台账注册 + 前端接桥）由实施轮次
（commit `91933bd68` / `4189c913f` / `98ec759e2` / `4590f15ab`）完成，但四份 H spec 的
复选框从未回标。本轮按「跑它自己的 AC 再勾」逐条核验后回标，**不代勾**。

### 判据锚点（现算，不引用 spec 自述）

| 维度 | 现算值 |
|---|---|
| H 循环 sync 测试文件 | **8 个**（`test_h9_canary_and_contract` / `test_h_cycle_migration_progress_state` / `test_h_cycle_registered_defects_fixed` / `test_h_foundation_hc4_key_resolution` / `test_h_foundation_hc_guards` / `test_h_frontend_managed_sheet_parity` / `test_h_lane2_seed_and_disclosure_defects` / `test_task50_h_cycle_migration`）+ 3 个事实模块 |
| 全量结果 | **364 passed / 0 failed**（126s） |
| HC-1~HC-16 | design 正文 **16/16 齐**；守卫 **16/16 齐**（HC-11 / HC-15 的守卫在 `test_h9_canary_and_contract.py`，不在 `test_h_foundation_hc_guards.py`） |
| HF-P1~HF-P18 | **18/18** 在 `test_h_foundation_hc_guards.py` 有判据 |
| 台账（Task 20 锚） | `DELIVERED_PER_ENTRY_CONTRACTS` 里 H 域 **10 条**（h1 pilot + 9），每条 `provider_module` **import 全部 OK**、契约文件全部在盘 |
| 已接桥（Task 20c 锚） | `migrated_entry_ids()` = **9/9**（真源 = 前端 `H_OO_WIRED_ROWS_CODES`，非手写名单） |
| BP-8 删除账本 | 5 个 legacy 载体 **全部确已不存在** |
| 证据文件 | `evidence/task0-prerequisites.md` · `task1-slice-discrepancies.md` · `task19-canary-db-evidence.json` 均在库 |

### Task 20c 交接核验（本轮机械核）

* **entry 归属零重叠零遗漏**：lane1={h3,h5,h7} · lane2={h4,h8} · lane3={h2,h6,h10} · canary h9
  ⇒ 3+2+3+1 = **9** ✓
* **lane spec 只引用编号不复述正文**：三份各引用 HC 编号 **14 / 12 / 11** 个；
  以「foundation design 的 HC 段落里 ≥60 字长句」做整句复制检测，命中 **1 / 0 / 2** 处，
  且这 3 处全是**同一批实测事实的表格行**（如 `` | `H3-2-cost-rows` | 8 | `rowId` | ``），
  不是裁决正文 ⇒ 判「未复述裁决」。🔴 如实记这 3 处存在，不写成「无一条复述」。

### 🔴 两处 `[ ]*` 保持未勾（外部门，不假绿）

| # | 阻塞 | 现算依据 |
|---|---|---|
| 20a* | BP-4 真 OO 9.4 场景集 | 9 条 H entry 在 manifest 里 `capability` 仍是 `single_onlyoffice` / `adapter_id=None`（前端 `capabilityForEntry` 读的就是这份 generated manifest，全平台 `bidirectional` 现算仅 **4** 条 = {d2,d4,g7,h1}）⇒ H9 走不到真 roundtrip |
| 20b* | BP-2 人工审核契约 + BP-3 approved bundle | 同上；正向门按设计**仍关着**，`test_h_cycle_migration_progress_state` 就是在断言它关着 |

⇒ **「契约已交付 + 已接桥」与「capability 已放开」是两件事**：前者本轮已 9/9，后者是
平台级 approved-bundle 门，不在本 spec 权限内。

### 🔴 本轮自查抓到的两处**我自己的探针假阴**（口径教训）

1. **「fail-loud」不能靠数 `throw` / `Error(`**：我的首版探针对 `h10RelatedH6Pull.ts` 报
   `throw=0 Error=0 reason=0` ⇒ 差点判「BP-12 只收敛了键、没做 fail-loud」。现读代码发现
   它的 fail-loud 形态是**判别式返回值** `status: 'ok' | 'wp_missing' | 'empty' | 'error'`
   + `message`，正是 AC 要的「返回显式失败原因」。
2. **「族 C 身份未修」是子串匹配骗的**：探针用 `` `row-total-${ `` 命中
   `useH2Adjudication.ts#L194`，看起来 BP-11 没修；现读发现真实代码是
   `` `row-total-${name}-${Math.random().toString(36).slice(2, 7)}` `` —— **已经是族 A**
   （带随机后缀）。子串匹配无法区分「族 C `xxx-${name}`」与「族 A `xxx-${name}-${rand5}`」。

⇒ 两条都是同一条纪律的实例：**判据形态未知时先读代码再定口径**，keyword 计数只能用来
「找候选」，不能用来「下结论」。

---

## 2026-09-30 追加：capability 正向门的前置六项审计 + 数字勘误

用户授权「像 D4-4 T10* 那样把阻塞项都解决」。按 G 循环已翻 13 条时留下的可复核先例，
翻 `capability` 的前置是**六项同时成立**（口径逐字取自 overlay 里 G 条目的 `reason`）。
逐条现算结果如下 —— **五项全过，第⑤项只覆盖 1/9，因此本轮不翻**。

### 🔴 数字勘误（先纠正我自己写进 spec 的两个过期值）

🔴 **这个数必须连「在哪个状态」一起报**（方法论㉖的第 4 条）：manifest 现在
**工作树与 HEAD 不同**，而且 **HEAD 自己的 `stats` 与自己的 `entries` 还不一致**。

| 状态 | entries | `stats.capability_counts.bidirectional` | **逐条扫 entries 得到的真值** |
|---|---|---|---|
| **HEAD（已入库）** | **155** | **4** | **5** —— `d1` / `d2` / `d4` / `g7` / `h1` 🔴 stats 与 entries 自相矛盾 |
| **工作树（未提交，并发会话）** | **138** | **18** | **18**（自洽） |

工作树比 HEAD 多出的 13 条**全是 G 循环**（`g1,g2,g3,g4,g5,g6,g8,g9,g10,g11,g12,g13,g14`）
—— 即 overlay 里早已裁决、等着 manifest 重生成的那 13 条；并发会话已改 overlay 并跑了
`--apply`，但**还没提交**（`git status` 对这三个生成产物显示 M）。

| 我写错的位置 | 原写 | 更正 |
|---|---|---|
| 本文件 Task 2 判据 · design §现状 | manifest **155 entries** | HEAD 155 / **工作树 138** |
| 三份 lane spec 的 16*/18* 说明 + lane1 证据 | `bidirectional` **仅 4 条**（d2/d4/g7/h1） | HEAD 真值 **5**（stats 写 4 是 HEAD 自身的陈旧字段）/ 工作树 **18** |

成因两层：① 我读的是**前端 generated.ts 的 `stats` 字段**，而那个字段在 HEAD 上本身就比
自己的 entries 旧（少算了 d1）；② 读数之后、复核之前并发会话重生成了 manifest。

口径（可复现）：读 `backend/data/workpaper_sync_entry_manifest.json`，**逐条扫 `entries`
的 `capability` 字段**而不是读 `stats`（stats 会漂）；工作树侧
后端 `manifest_digest` 与前端 `WORKPAPER_SYNC_MANIFEST_DIGEST` 同为 `c17ad880…`、
`generate_workpaper_sync_manifest.py --check` **exit 0**（自洽）；HEAD 侧 digest 是
`afdffafd…`。

⇒ 附带结论：**`stats` 不可作判据真源**，要数就逐条扫 `entries`。我这次正是栽在 stats 上。

⚠️ 原始 Task 2 / design 正文**不回填改写**（append-only 审计轨迹），勘误登记在此。
下次引用那条判据时按 138 现算，不要照抄 155。
🔴 这正是方法论㉖的实例：**过期数字换新数字时，新数字必须同标准验证并写明口径**，
否则只是把一个错数换成另一个错数。

### 前置六项逐条现算（H 九条 entry）

| # | 前置 | 现算 |
|---|---|---|
| ① | 正式契约 `review_status == reviewed` | ✅ **9/9**（与已翻的 d2/d4/g7/h1 同级） |
| ② | `STORE_MERGE_REGISTRY` 已注册 | ✅ **9/9**（全表 42 条，H 域 10 条全覆盖） |
| ③ | `DELIVERED_PER_ENTRY_CONTRACTS` 台账登记 | ✅ **9/9**，`provider_module` 全部 import OK |
| ④ | `build_manifest_registration_plan` 判可注册 | ✅ **9/9** `blocked_reason=None`（plan 138 条） |
| ⑤ | `check_sync_provider_golden_digest` **覆盖**且零漂移 | 🔴 **只覆盖 1/9（仅 h9）** |
| ⑥ | 宿主已改线（`WorkpaperSyncEditorHost` + syncBridge） | ✅ **9/9**（`migrated_entry_ids()`） |

### 🔴 第⑤项：8 家 H provider 从未进过 golden 基线 —— 而且**缺口远不止 H**

> ⚠️ **本节标题里的「8 家」是我的局部视角**。把台账整个拉出来比之后，真实缺口是
> **24 个 family / 27 条契约**（台账 48 个 family，登记表只有 24 个）—— 见本节末尾
> 「触类旁通」小节。H 的 8 家只是其中一部分。

`check_sync_provider_golden_digest.py` 跑出来是绿的：
「✅ golden digest 零回归：161 个 digest 逐个不变（覆盖 24 家，**零跳过**）」。
但现算基线文件 `backend/scripts/check/_sync_provider_golden_digest.json`：

```
h9.lease_liability_detail            命中 1
h2 / h3 / h4 / h5 / h6 / h7 / h8 / h10   命中 0
```

⇒ 门之所以绿，是因为那 8 家**压根不在 `PROVIDERS` 登记表里**，没有东西可比。
这与本仓登记过的「f1 被 `[SKIP]` 吞掉」是**同一缺陷类、不同机制**：
f1 是「登记了但跑挂被跳过」（已修，现在 skip 会判失败）；
这 8 家是「**从未登记**」—— 覆盖面缺口在登记表那一层，`skipped` 判据管不到它。

脚本自己的注释已经写明了这条纪律：「刻意**不设** skip 白名单 …… provider 真的不适用某一段时，
正确做法是在 `PROVIDERS` 里把那一段的开关关掉，而不是让它整家抛异常然后被跳过」——
而「整家没登记」比「整家被跳过」更隐蔽，因为连 stderr 都不会有一行。

**正确修法（已确定，本轮不执行，理由见下）**：把 8 家按 h9 同形加进 `PROVIDERS`
（`("h2", "phase5_h2_construction_in_progress", "ADAPTER_ID", True, True)` 这种形态，
`plural_instr=True` —— H2/H4/H5/H7/H8 是四级表头、`instrumentation_specs()` 走复数），
再把这 8 条的 digest **逐条**补进基线。

#### 触类旁通：把台账整个拉出来比，缺口是 **24 个 family**（一半）

发现一处反模式就全仓找同类。现算 `DELIVERED_PER_ENTRY_CONTRACTS`（51 条 / **48 个
family**）对 `PROVIDERS`（**24 家**）：

| | family |
|---|---|
| **已 bidirectional 却不在门内** | 🔴 **`g7` · `h1`** —— 两条都是 `pilot_*` 命名的早期 pilot，当初按 `phase5_*` 收录时漏了 |
| 其余 22 家（契约+provider 已交付，capability 仍 `single_onlyoffice`） | `a51` `c2` `f2`(4 条契约) `f3` `f4` `f5` · `h2` `h3` `h4` `h5` `h6` `h7` `h8` `h10` · `i1` `i2` `i3` `i4` `i5` `i6` · `j1` `l1` |

⇒ 那句「覆盖 24 家，零跳过」读起来像全覆盖，实际是 **24/48**。
更要紧的是 `g7` / `h1` ——**用户正在用的两条双向底稿**不在零回归门内。

#### 已落地的处置：把缺口做成会打红的事实（棘轮）

补齐要在干净树上取基线（见下），但「洞是看不见的」这件事可以**现在就修**。新增
`backend/tests/workpaper_sync/test_golden_digest_coverage_ratchet.py`（**5 passed**）：

* **记账等式**：`len(登记) + len(缺口) == len(台账 family)` —— 不设「覆盖率 ≥ X%」阈值
  （阈值允许静默退化，而且 X 是拍脑袋数字）；
* **双向棘轮**：缺口集合必须**恰好等于**登记的 24 家。只查一个方向都会 fail-open ——
  只查「缺口 ⊆ 棘轮」则新交付一家忘登记不会红；只查「棘轮 ⊆ 缺口」则补齐后忘删不会红；
* 🔴 **真正要守的不变量**：`capability=bidirectional` ⟹ 该 family 在门内。
  现状两个历史违反（`g7`/`h1`）被钉死，**第三个立刻打红** —— 这就是把前置第⑤项从
  spec 文字变成机制：**任何 entry 想翻 bidirectional，必须先进 golden 门**；
* 豁免是**可伪证声明**而非理由文本：去台账核实 `g7`/`h1` 的 `provider_module` 真的是
  `pilot_*`；哪天改名成 `phase5_*`，豁免理由不成立，判据就红。

**变异反证（两处都真打红后还原）**：① 从棘轮里删掉 `h2`
⇒ `test_coverage_gap_matches_the_ratchet_exactly` 红；② 把 `g2` 从 `PROVIDERS` 注释掉
（`g2` 是 bidirectional）⇒ **两条**同时红，其中
`test_no_bidirectional_entry_escapes_the_golden_gate_beyond_the_two_pilots` 正是
「带着覆盖缺口上线」这个场景 —— 也就是说将来谁把 H 某条翻成 bidirectional 而没先进门，
红的就是这一条。

判据对「工作树 vs HEAD」稳定：两种状态下违反集合都恰好是 `{g7, h1}`
（工作树新增的 13 条 G 全都已在门内）。

### 🔴 为什么本轮**不**执行：共享引擎正处于半程重构（未提交）

现算工作树 `backend/app/services/workpaper_sync/` 有 **11 个文件被并发会话改动但未提交**：

```
excel_instrumentation.py        +473
oo_to_html.py                   -477      ← 两者合看是一次「把代码从 A 搬到 B」的进行中重构
published_identity_observer.py  +148
projection_first_publication.py +110
entry_source_facts.py            +63
phase5_d3_prepaid_receipts.py    +37      phase5_entry_orchestration.py +25
excel_entry_gate.py              +29      phase5_d4_adjustment_sheet.py +16
phase5_d567_expansion_contract.py +13     adapters/delivered_contracts_ledger.py +11
合计 925 insertions / 477 deletions
```

golden digest 的三段里有两段（`instrumentation_spec(s)()` 与 `build_store_projection()`）
**直接依赖 `excel_instrumentation.py` 与引擎层**。此刻为 8 家取基线，等于把**别人没写完的
引擎状态**冻进基线：那个会话落地最终形态（或回退）时，这 8 条基线会悄悄变成错的，
而它们看上去是「已验证」。

⇒ 这正是我自己这两轮反复在修的「假绿」形态，只是载体从测试判据换成了 golden 基线。
**不在脏树上冻结基线**，也因此**不翻 capability** —— 六项前置的意义就在于**同时**成立。

另两条次级理由，一并记明：

* `--update` 是**全量**重写（24 家一起重算），本仓已有「拒绝 `--update`、只改 d4 一行」的
  先例正是为了避开这个；本轮即便要补，也只能逐条拼接 8 条，不能全量。
* 真正让用户看到双向，除 capability 外还需每条 entry 有 **published representation +
  approved bundle**（`register()` 的供给门）。那一步是 D4-4 T10* 那套发布链，
  需要真实项目里有 H 底稿的 wp —— 与 capability 翻转是两件事，不能只翻 capability
  就宣布「阻塞已解」。

### 下一步（待引擎重构落地后，一次做完）

1. 等 `excel_instrumentation.py` / `oo_to_html.py` 那次重构**提交入库**（判据：
   `git status` 对 `backend/app/services/workpaper_sync/` 干净）；
2. 8 家 H 加进 `PROVIDERS`，逐条拼接基线（**不** `--update`），复跑门确认「覆盖 32 家 /
   零跳过」，**并同步从棘轮 `_UNCOVERED_BY_GOLDEN_GATE` 删掉这 8 行**
   （棘轮只许变短；忘删会被 `stale_entries` 那条判据打红）；
   🔴 顺手把 `g7` / `h1` 一起补进去 —— 它们是**已上线的双向底稿**却不在门内，
   优先级其实高于尚未翻门的 H；补完同步收缩 `_BIDIRECTIONAL_BUT_UNCOVERED` 到空集；
3. overlay 加 9 条 H override（`capability=bidirectional` / `adapter_id=<contract_id>` /
   `migration_state=adapter_registered` / `canonical_resolver=workpaper_sync_published_representation`
   + 六项前置现算值写进 `reason`，照 G 条目同形）；
4. `generate_workpaper_sync_manifest.py --apply`（注意它有
   `approved_source_digest == discovery.sourceDigest` 这道门：前端挂点一变就必须先复核
   mount diff 再更新 `approved_source_digest`）；
5. 同步把 `test_h_cycle_migration_progress_state` 那条「正向门必须关着」的判据**翻面**
   为「已翻的 9 条必须 `adapter_registered` 且 `adapter_id` 非空」，并对剩余未翻 entry 保持原判据；
6. 发布链（provision + rematerialize）+ 真栈 L1/L2 验收，H9 用真库载荷（canary 真库非空），
   H3/H5/H7/H4 主表键真库零载荷 ⇒ 只能标合成场景或等真实录入，**不造数据当实证**。

---

## 2026-10-01 capability 正向门已打开（commit `33e2a049b`），但 runtime 注册仍 0/9

### 做了什么
H 十条 entry（h1 pilot + 本轮 h2~h10 九条）现在全部是
`capability=bidirectional` · `adapter_id=<台账 contract_id>` ·
`migration_state=adapter_registered` ·
`canonical_resolver=workpaper_sync_published_representation` · `html_store` 已裁决。
入口是 overlay 的 9 条 override（`backend/data/workpaper_sync_entry_overlay.json`），
产物是 manifest / legacy baseline 两组共 5 个文件。

### 六项前置逐条现算 9/9（证据落在每条 override 的 `reason` 里）
| # | 判据 | 现算 |
|---|---|---|
| ① | 正式契约 `review.review_status == 'reviewed'` | 9/9 |
| ② | `STORE_MERGE_REGISTRY` 已注册该 `contract_id` | 9/9（H 域 10 个键齐） |
| ③ | `DELIVERED_PER_ENTRY_CONTRACTS` 登记 + provider 可 import | 9/9 |
| ④ | `build_manifest_registration_plan(entries)` `blocked_reason=None`，且 `provider_module ∈ _ALLOWED_PROVIDER_MODULES` | 9/9 |
| ⑤ | `check_sync_provider_golden_digest` 覆盖该 family 且零漂移 | 9/9（commit `88397deb5` 把 PROVIDERS 24→34，此前只覆盖 h9） |
| ⑥ | `h_migration_progress.migrated_entry_ids()` 含该 entry | 9/9 |

🔴 ④ 与 ⑥ 的接口路径**第一版全猜错了**：④ 不在 `manifest_registration_plan` 模块而在
`adapters/registry.py`，且签名是 `entries: Mapping[entry_id, entry]` 而不是 id 列表；
⑥ 不在 app 下而在 `backend/tests/workpaper_sync/h_migration_progress.py`。按猜的路径跑
出来是「六项全通过 **0/9**」——**一个全假的红**。改成现读后才是 9/9。（方法论㉑）

宿主改线另行现算（不看注释、不抽样）：模板有 `<WorkpaperSyncEditorHost` 挂点 +
`:bridge="hSync.syncBridge"` 绑定 + script 有该组件 import，九条 **9/9**；
反向对照 `GtI1IntangibleAssets.vue` 三项全 **0** ⇒ 扫描器有区分力，不是恒真。

### 🔴 `register_from_manifest()` 真 session 实证：九条 H 注册成功 **0/9**
capability 门确已打开（`blocked_reason` 9/9 为 `None`），但卡在**下一环** `_describe_entry_supply`：

> 该 entry 还没有 current published representation（`working_paper_sync_entry_state` 无行）
> —— 它由 `ContentMutationService.commit(...)` 产出首版 content version

即需要**真实底稿内容提交**，属真实录入，与 Task 20a* 的「不得造数据当实证」同源。

更要紧的是：**已翻门的 5 条（d1 / d2 / d4 / g7 / h1）同样注册不上**，报
`entry_source_fact_unavailable: 挂载组件不唯一 ['GtOnlyOfficeSheet','WorkpaperSyncEditorHost']`
—— 平台级预存缺陷，正是并发会话 spec `sync-editor-host-discovery-contract-closure`
在修的东西（`entry_source_facts.py` 此刻有其未提交改动）。本轮不碰。

⇒ **Task 20a* / 20b* 保持 `[]*`**，但欠账描述从「BP-1~BP-3 门关着」更新为：
门已开，卡 ① published representation 供给（真实录入）② 上述平台级 `挂载组件不唯一`。

🔴 接口勘误（三份 lane spec 的 AC 都写错了）：`register_from_manifest` **不是自由函数**，
是 `WorkpaperSyncAdapterRegistry` 的 **async 方法**且要 `session=`；生产构造点是
`build_production_registry()`（它自己 bind 计划，直接 `bind_registration_plan()` 会缺
`plan` 位置参数）。另 AC 里的 `frozen_key` / `frozen_reason` 字段**在实现里不存在**，
实际机制是生产者侧契约的 `review.frozen_cross_ref`（现算 h6 的 `H6-2-rows` → 3 个消费方、
h9 的 `H9-2-rows` → 2 个消费方）。

### 顺带修好 16 条预存红（纯净 worktree 串行归因）
| 状态 | 红 |
|---|---|
| S1 = `4209a7897`（仅 b60 注释修复） | **18**（12 failed + 6 errors） |
| S2 = S1 + 本轮翻门 + 两组产物重算 | **2** |

新引入 **0**；修好 **16** = `test_workpaper_sync_manifest_contract` 6 +
`test_workpaper_sync_legacy_baseline` 1 + `test_task73_entry_profile_manifest` 9。
余 2 条（`test_workpaper_writer_inventory` 的 inventory source digest 过期）S1 就红，
与本轮无关。重做 S2 幂等（manifest digest 两次均 `bbd486f5…`）。

根因链：`GtB60HourBudgetPanel.vue` 的 `<script setup>` 文件头注释里写了
`` `/rows/*/rowUuid` ``，`*/` 提前闭合块注释 ⇒ esbuild exit 1 ⇒ discoverer 报
`Vue AST parse failed` ⇒ **整个 mount discovery [FAIL]** ⇒ 自 2026-09-28（`8d7a52059`）起
`--check/--apply` 一次都跑不了、manifest 无法回灌。修复见 commit `4209a7897`。

🔴 **归因方法踩过一次坑并已改正**：第一版把归因脚本与另一个仍在跑的探针并行启动，
两者都在同一个 worktree 里 `git checkout`，结果脚本保存的「S2 产物」其实是 HEAD 内容
⇒ 跑出来的「新引入 0」是拿 HEAD 跟 HEAD 比，**不构成证据**。改成单进程串行重做，
并加「S1 必须只有 h1 一条 bidirectional」「S2' 必须与 S2 digest 相同」两条自检断言。

### 判据翻面三处（原判据变成「要求成果不许存在」）
`test_h_cycle_migration_progress_state.py`
* `test_no_slice_entry_has_a_registered_adapter` →
  `test_slice_entries_now_have_registered_adapters_in_the_source_manifest`：
  slice 侧仍断言 `adapter_id is None`（规划期冻结快照，append-only 不回填），
  live manifest 侧断言四项齐备，且 `adapter_id` 必须与台账 `contract_id` **逐字相等**。
* 台账 `adapter_registered` 那条由 `is False` 改为不再硬判：现算全台账 `True` 只有 **4** 条
  （d2/d4/g7/h1），而 live `bidirectional` 已 18→28 条 ⇒ 这个字段**整体滞后**，是平台级
  字段失修、不属本 spec 作业面。照它「对齐」会把滞后正当化（铁律㉗），直接改 True 又会
  造出第二套口径。改为只认 manifest 这个运行时真源，并新增
  `test_ledger_adapter_registered_lag_is_a_ratchet`：登记 flag=True 的**集合**
  （不写条数 —— 条数在不同检出状态下不同，写死必各错一次）+ 双向对账 +
  「flag 不得跑在 manifest 前面」+ 「H 域 live bidirectional 恰 10 条」。

`test_task50_h_cycle_migration.py`
* `test_manifest_mirror_divergence_is_registered_not_silently_equal`：mirror 侧断言它仍是
  规划期三个值（`single_onlyoffice` / `unresolved` / 非空 `legacy_reasons`），live 侧断言
  已前进到迁移后的值，BP-9 那条登记原样保留。
* `test_registered_entry_ids_agree_with_the_slice`：对账另一侧由冻结 slice 换成 live
  manifest（前端 TS 投影 vs 后端 JSON 是同一事实的两个投影）。

两文件合计 **101 passed**。

### approved_source_digest 复核（`b6291b9f…` → `c2d6926a…`）
mounts 245→244 / hosts 154。86 失 / 85 得 共涉 **45** 个宿主文件，逐文件 `git log -1`
查下来**全部落在已入库 commit**（`8d7a52059` G 循环 15 个 / `9c325aea4` K lane1 7 个 /
`7e23512bf` F2 四 entry / `4591f9bb7` H2·H6·H8·H9 等共 16 个 commit），零未提交代码参与。
85 组「失 2 得 2」是接桥造成的行号位移 re-hash。唯一净减 1 条是 `GtWpRenderer.vue` 的
`mount_d4b8a91cbb8386a448b3` —— 上一版复核已登记过的同一个度量口径差，Word 能力零损失。

### 提交方式（并发会话同时在改同一批文件）
并发会话在我核验期间重生成了主树 overlay/manifest（entries 138→189、overrides 20→30、
`approved_source_digest` `c2d6926a…`→`24a1b89a…`，其 spec 让发现器纳入
`WorkpaperSyncEditorHost`、新增 96 挂点 / 51 宿主）。故本 commit 用
`git hash-object -w` + `git update-index --cacheinfo` **只把纯净 worktree 的 5 件产物放进
索引、不动工作树文件**：入库的是自洽快照（clean checkout 上判据全绿），他们的工作树原样
保留，且他们的重生成**已把这 9 条 override 吃进去**（现算 9/9 在册、`reason` 是本轮写的
那段、`review_basis` 的链从 `c2d6926a…` 接上去）⇒ 后续他们提交时这 9 条不会丢。

---

## 2026-10-04 Task 20a 受控 OO 9.4 roundtrip 实测：卡在 published artifact footer 几何漂移（仍 `[ ]*`）

### 这一轮做了什么
补了 provider 协议回归守卫 `backend/tests/workpaper_sync/test_registry_provider_protocol.py`
（5 passed）：真实 `WorkpaperSyncAdapterRegistry.register_from_manifest()` 下覆盖
同步 / 异步 provider、`session=` 转发、`SyncDomainError` 按 entry 隔离、provider 内部
真实 `TypeError` **不被吞**而继续上抛；外加 E1 `attach_pilot_adapters(session=…)` 回归。

然后按既有 `verify_l1_oo94_roundtrip.py` / `verify_n4_oo94_roundtrip.py` 的
`ConvertService.ashx` 范式，对 H9 做了一次**受控 OO 9.4 roundtrip 评估**。

🔴 **本轮探针与 L1/N4 验收脚本的关键区别（如实声明，未冒充生产注册）**：
L1/N4 的 ① 步走生产 `attach_adapters()`，那条路径要 manifest `capability==bidirectional`。
H9 当前 manifest `capability=single_onlyoffice` / `adapter_id=None`（generated manifest，
前端读的就是它）⇒ `phase5_h9.attach_pilot_adapters()` 必返回空元组。故探针
`backend/scripts/e2e/_h9_oo94_roundtrip_probe.py` **不翻 capability、不手改 manifest、
不冒充 `register_from_manifest` 注册成功**，改为直接用 H9 真实 published representation 的
冻结定义（`resolve_published_frozen_definitions`）+ 生产 `build_excel_adapter(direction=
'html_to_oo')` 组装 adapter 实例，仅做**文件级** roundtrip（真 OO 9.4 xlsx→xlsx 重存）。

### 实测逐环结果（真实数据、只读、不写 PG）
| 环 | 结果 |
|---|---|
| [0] 真库载荷 | `H9-2-rows` 1 行 / remark **819 B / 2 行**；lessor=`测试出租方_549786` / `测试出租方_E2E`（🔴 **E2E seed**，非真实业务录入） |
| [①] published representation | `46f12d1f` / bundle `aa821fd3` ✓ |
| [②] 冻结定义 + adapter | `resolve_published_frozen_definitions` OK，contract_digest `419c1729af5b`，`build_excel_adapter` 组装 `ExcelSyncAdapter` ✓ |
| [③] substrate artifact | `000000001-6e527d7572f2.xlsx` 59891 B ✓ |
| [④] baseline extract + overlay | `overlay_store_on_baseline_projection` 成功，projection values=28 / rows=2 ✓ |
| [⑤] materialize | 🔴 **`FooterAnchorDriftError`**：published artifact footer marker `合计` 实测在 **R16**，契约冻结 `GT_FOOTER_ROW=14` —— 生产写入侧 **fail-closed** |

openpyxl 直读该 artifact 的 `租赁负债明细表H9-2` 复核：受管表数据区 **R9-13 全空**，
2 行真实数据落在 **R14 / R15**，footer「合计」在 **R16**（R17 起是说明文字）。
⇒ 这份 published representation 的几何与契约冻结的模板几何（数据区 R9-13、footer R14）
**不一致**。

### 结论：这是真实供给态漂移，不是 20a 的通过证据
1. **链路到 extract 全通**（①②③④全绿）证明：H9 契约 + 真实冻结定义 + 真实 artifact +
   真实载荷在真 OO 9.4 引擎前的组装与反读是对的。
2. **materialize fail-closed 是生产门在正确工作**：它拦住「按契约 static_row（R14）反读、
   跟着 marker（R16）写」会造成的静默错值。这不是契约 bug，也不是守卫 bug。
3. **根因是 published representation artifact 的布局漂移**：该 representation 的受管表没有
   保留模板空白基线（R9-13 应为可写数据区），而是把 2 行数据写在 R14/R15、把 footer 顶到
   R16。要让 roundtrip 通过，必须有一份 footer 几何 == 契约冻结值（R14）的 published
   representation —— 这需要经 `ContentMutationService.commit(...)` 以**正确基线**重出首版，
   属真实录入 / 发布链动作，**不能在不写库、不改契约的前提下绕过**。
4. 载荷 lessor 含「E2E seed」字样 ⇒ 现有这份 representation 是测试种子产物，更坐实它不是
   可用于 20a 验收的真实业务 published representation。

⇒ **Task 20a* 保持 `[ ]*`**；欠账描述从 2026-10-01 的「门已开，卡 published representation
供给 + 平台级挂载组件不唯一」**进一步具体化**为：published representation 已存在且 attach
能走过 representation 门，真正卡住的是 **materialize footer 门** —— 现有 representation 的
artifact footer 几何（R16）与契约冻结（R14）不一致，需以正确基线重出首版 representation。

### Task 20b* 同步说明（仍 `[ ]*`）
本轮未触达人工审核契约 / approved bundle 发布链：真库虽有 `bundle_state='approved'` 的
bundle（`aa821fd3`），但那是发布链机械产物，**不等于**正式人工业务审核完成（审核 actor /
审核事件链 / approved 发布授权均缺）。不把数据库 `approved` 状态解释为人工审核完成。

### 一次性探针去留
`backend/scripts/e2e/_h9_oo94_roundtrip_probe.py` 是本轮一次性受控评估脚本（`_` 前缀，
用完即删），交付时删除；结论已固化在本节。`backend/scripts/analyze/_h9_runtime_probe.py`
（更早的只读 registration 探针）一并删除。
