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
