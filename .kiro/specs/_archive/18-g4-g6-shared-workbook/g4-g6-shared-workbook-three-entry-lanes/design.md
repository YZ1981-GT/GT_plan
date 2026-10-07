# Design Document

## Overview

G4 / G6 各 3 条 entry 共 6 条，两册是 G 目录最大的两本（999,788 B / 981,008 B）。
本 spec 的三个难点是 G 循环独有的：**BP-8 一册三 entry 的 pointer 互顶** · **两张 ECL 主表是转置形态且
`max_column`=16384** · **四条 entry 用 `http` 而非 `api` 客户端**。

GC-1~GC-10 见 `g-cycle-sync-foundation-and-first-canary/design.md`（本 spec 引用、不复述）。

## 上游锚定

沿用 foundation spec 的锚定表。额外：
- **D4-29 `phase5_transposed_sheet.py` + `transposed_registry.py`** —— 转置形态唯一先例（已把 D4-29 从单例
  泛化成「引擎 + 两份 spec」且逐字节零回归）⇒ G4-9 / G6-11 是它的第三、第四个消费方
- **F2 spec 裁决 F2-H1**（`sheet_keys` 互斥域）—— 同码多 entry 的 matcher 解法，本 spec 直接复用
- **`g4StorageContract.ts` / `g6StorageContract.ts`** —— FD-1 mode ③/④ 的实现；G6 的 `g6CrossHelpers` 派生别名是
  BP-10 的正面样本

## Architecture

### 接入顺序（前置驱动）

```
[BP-7 两处行身份修复]                    ← 硬前置（G6-sppi 确定有；G4-main 待按值定位）
[BP-8 pointer 隔离守卫]                  ← 由 foundation GC-1 交付规则，本 spec 落六条实施
G4-sppi（G4-7：数据区零公式 / 无 footer / 7 列，本 spec 最简 → 首条）
  → G4-main（G4-2 两区 + 模板自带插行声明）
  → G6-main（G6-2 多区，几何待 Task 2 补全）
  → G6-sppi（G6-5 无表头行 + 行级 mask，依赖 BP-7 已修）
  → [16384 列裁决] G4-ecl（G4-9 转置三块）
  → G6-ecl（G6-11 转置三块 + 区标题）
G4-3 / G6-4 调整分录：FC-6 可行性核　两册附注披露与参考 sheet：不接
```

### 声明层结构

```
backend/app/services/workpaper_sync/
  phase5_g4_bond_investment.py          ← G4 三条共用 entry 层（各自 ENTRY_ID / ADAPTER_ID）
  phase5_g4_02_main_detail.py           ← G4-main 两区
  phase5_g4_07_sppi_inventory.py        ← G4-sppi（首条）
  phase5_g4_09_ecl_stage.py             ← G4-ecl 转置
  phase5_g6_other_bond.py               ← G6 三条共用 entry 层
  phase5_g6_02_main_detail.py
  phase5_g6_05_sppi_fair_value.py       ← 行级 mask
  phase5_g6_11_ecl_stage.py             ← 转置
backend/data/workpaper_sync_contracts/g4.{bond_main,sppi_inventory,ecl_stage}.json
backend/data/workpaper_sync_contracts/g6.{other_bond_main,sppi_fair_value,ecl_stage}.json
backend/scripts/e2e/seed_g4_g6_publish_e2e.py   ← 🔴 六条主表真库全零，验收前必 seed
```

🔴 **一册三 entry 用三个独立 `ADAPTER_ID`**（`g4.bond_main` / `g4.sppi_inventory` / `g4.ecl_stage`），
但**共用一个 `TEMPLATE_SHA256`**（`da3a3480…`）—— 这是 GC-1 的直接体现：契约钉的是同一份字节，
pointer 靠 `entry_id` 区分。

### 受管区清单（逐格实测）

| sheet_key | entry | managed_sheet | store_item_id | 行身份 | 表头 | 数据 | footer | formula_columns | payload 列 |
|---|---|---|---|---|---|---|---|---|---|
| `g407-managed` | G4-sppi | 有价证券盘点表G4-7 | `G4-7-items` | `id` | R13(B-G) | R14-22 | R23 锚行 | （无） | dual_write |
| `g402-managed` | G4-main | 明细表G4-2 | `G4-2-rows` | `id` | R9/R10 | 两区 R12-17 / R20-25 | 小计 R18/R26 + 合计 R27 | J,L,O,S,T,U,V,X,AC,AF,AG | conclusion 权威 + remark 镜像 |
| `g602-managed` | G6-main | 明细表G6-2 | `G6-2-rows` | `id` | R9/R10 | 多区（Task 2 补全） | 多小计 | J,O,Q,U,V,W,X,Y,AD,AF | dual_write |
| `g605-managed` | G6-sppi | 公允价值测试表G6-5 | `G6-5-fair-value-data` | `id` | **无** | R9-18 | R19 合计 | D(仅 R9/R10),H,J | conclusion_only |
| `g409-managed` | G4-ecl | 债权投资三阶段划分G4-9 | `G4-9-rows` | `id`(uuid) | R9 | 转置三块 | R24/R32/R46 锚行 | （无） | dual_write |
| `g611-managed` | G6-ecl | 其他债权投资三阶段划分G6-11 | `G6-11-rows` | `id`(uuid) | R10 | 转置三块 | R25/R33/R47 锚行 | （无） | dual_write |

不受管：审定表G4-1 / G6-1（后置 spec）· 调整分录 G4-3 / G6-4（FC-6）· 两册附注披露 ×4 ·
参考 sheet ×4 · 底稿目录 ×2 · 程序表 G4A / G6A · 其余检查/测算表（Task 2 出可行性核结论）。

## Data Models

不新增数据模型。两类 store 形态：`rows` + `id`（四条行表）· 转置块（两条 ECL，走
`TransposedSheetSpec` 的实体列 × 属性行投影）。

## 关键裁决

### 裁决 G46-H1：首条选 G4-sppi（有价证券盘点表G4-7）

| 候选 | 数据区公式 | 表头 | footer | BP-7 | 转置/16384 | 结论 |
|---|---|---|---|---|---|---|
| **G4-sppi (G4-7)** | **0** | R13 单级(B 起) | 无（锚行） | 无 | 无 | ✅ |
| G4-main (G4-2) | 11 列 | R9/R10 | 两区小计+合计 | 🔴 待定位 | 无 | 次选 |
| G6-main (G6-2) | 10 列 | R9/R10 | 多小计 | 无 | 无 | 几何未全测 |
| G6-sppi (G6-5) | 3 列 | **无表头行** | 合计 | 🔴 有 | 无 | 两处特殊 |
| G4-ecl / G6-ecl | 0 | — | 锚行 ×3 | 无 | 🔴 两条都有 | 面最大 |

G4-7 同时验通三件事：**BP-8 的 pointer 隔离**（首次为同码三条之一发布 representation）·
**A 列空、表头从 B 起**的几何 · **无合计 footer 的锚行处置**。且它数据区零公式 ⇒ 失败面最小。

🔴 与 foundation 的 canary（G2）不同：G2 是全 G 循环首条，验的是「从零打通」；
G4-7 是本 spec 首条，验的是「同码三条之一能独立注册且 pointer 不互顶」。两者不可互相替代。

### 裁决 G46-H2：一册三 entry ⇒ 三 `ADAPTER_ID` + 一 `TEMPLATE_SHA256` + pointer 按 `entry_id`

BP-8 的根因是 pointer 用了 wp_code。裁决（= GC-1 的六条实施）：
- `ADAPTER_ID` 三个独立（`g4.bond_main` / `g4.sppi_inventory` / `g4.ecl_stage`），G6 同款
- `TEMPLATE_SHA256` 三条**相同**（契约钉的是同一份字节，这是诚实表达 1:N）
- entry pointer / `entry_state` 主键 / representation generation 一律 `entry_id`
- matcher 用 `sheet_keys` 互斥（F2-H1 解法）；运行时 `resolve_for_entry(entry_id)`

否决「给 G4/G6 各发明三个幻影码」（要动 manifest 生成器 + `wp_code_overrides`，影响面超本批）；
否决「三条合并成一个 adapter」（materialize 是整册的，合并会让三个宿主的灰度开关互相牵连）。

### 裁决 G46-H3：两张 ECL 走 `TransposedSheetSpec`；16384 列按「有效内容列 +1」放 UUID

转置形态由前端三元组 + 模板表头共同判定（FC-4）：表头是 `投资1：`~`投资X：` 横排 ⇒ 实体在列。
用 `RowTableSheetSpec` 会把「需要考虑的信息」当行身份，而它是属性名不是业务行 ⇒ 投影恒空。

16384 列三方案取①（有效内容列 11 + 1 = 第 12 列放 UUID），理由：
- ②清列级格式化污染要改权威模板字节（`backend/wp_templates/` 运行时只读 + sha 冻结）⇒ 须走覆盖层，代价远大于收益
- ③不受管等于放弃两个 ECL entry 的双向能力，而它们的业务价值（三阶段划分是减值核心）最高
判据：UUID 写入第 12 列后 `print_area` / `page_setup` 与基线一致；且 `max_column` 仍为 16384 时
instrumentation 定位不退化为全宽扫描（性能）。

### 裁决 G46-H4：BP-7 在 G4-main 侧「先定位、定位不到就如实登记 slice 不一致」

slice 的 `capability_target_blocked_by` 给 G4-main 列了 BP-7，但 BP-7 正文只展开了 G6-sppi 一处
（`useG6SppiFairValue.ts#L331/#L128`）。裁决：Task 2 **按值 grep** G4-main 的载入路径；
- 若实测确有下标回退 ⇒ 一并修（两处同型一次修完，触类旁通）
- 若实测**没有** ⇒ 如实登记「slice 的 `blocked_by` 与 BP 正文不一致」并给出证据，
  🔴 **不得**为对齐 slice 而伪造一处缺陷，也不得静默把 G4-main 的 BP-7 抹掉

### 裁决 G46-H5：四条 `http` entry 的守卫按登记名拼探针

FD-2 实测四条用 `import http from '@/utils/http'`（G4-ecl / G6-main / G6-sppi / G6-ecl），
两条用 `api`（G4-main / G4-sppi）。裁决：守卫从 slice 的 `html_counterpart.http_client_binding`
**读绑定名再拼探针**，不二选一硬编码。否决「统一改成 `api`」——那是 17 条 entry 级的重构，不属本 spec。

### 裁决 G46-H6：G4 的 4 条重复字面量照 G6 的派生别名范式改

BP-10 在本 spec 的份额：G4 有 storage contract 却仍在 `g4CrossHelpers` 重复 4 条字面量
（`G4-1-rows` / `G4-9-rows` / `G4-10-rows` / `G4-11-ecl-measurement`）；G6 已做对
（`g6CrossHelpers.G6_11_ROWS_KEY = G6_ITEM_IDS.G6_11_ROWS`）。
裁决：G4 照 G6 改（`g4CrossHelpers.X = G4_ITEM_IDS.X`），**G6 侧不动**（它是正面样本）。

## Error Handling

| 场景 | 处理 | 依据 |
|---|---|---|
| pointer 用 wp_code | 三条 generation 互顶 ⇒ 判据必红 | BP-8 / G46-H2 |
| ECL 表用 `RowTableSheetSpec` | 投影恒空 ⇒ 判据必红 | G46-H3 |
| UUID 放 `max_col+1`（16384+1） | 超 Excel 上限、写入失败 ⇒ 判据必红 | B2 |
| 对 `http` entry 用 `api\.` 探针 | 失配（假红或被 if 兜住变假绿）⇒ 判据必红 | G46-H5 |
| G6-5 用矩形 mask | R11+ 的 D 列被误标 formula ⇒ 判据必红 | B6 |
| 为对齐 slice 伪造 G4-main 的 BP-7 | 判据要求「有缺陷给证据、无缺陷给不一致登记」 | G46-H4 |
| 两册「参考」sheet 排除用同一字面量 | G6 那张无连字符 ⇒ 漏排除必红 | B7 |
| 六条主表空载荷直接验收 | 必须先 seed，否则算假绿 | Req 5.5 |
| G4-main/G6-main 未等 GC-9 裁决就受管 | foundation 本地硬门必红 | Req 5.1 |

## Correctness Properties

🔴 编号 spec-scoped：`Property N` 读作 `G46-P{N}`。

### Property 1: 六条 pointer 按 entry_id 且 generation 互不影响
**Validates: 1.1, 1.4**　构造 G4 三条先后发布 representation ⇒ 三条 pointer / generation 独立；G6 同款。
变异：pointer 改 `wp_code` ⇒ 互顶必红。

### Property 2: 三条同码 entry 可同时注册且 sheet_keys 两两不相交
**Validates: 1.2**　**真跑** `registry.register()`（不 mock）；`overlaps()` 返回空。
变异：`sheet_keys` 置空 ⇒ RG-3 `MatcherOverlapError` 必抛。

### Property 3: 模板归属用复数字段且满射+唯一认领
**Validates: 1.3**　`belongs_to_entries` 并集 == 六条全集；每条恰被一册认领。
变异：断言单射（FC-3 原形态）⇒ 与 13 册覆盖 17 entry 的实测矛盾必红。

### Property 4: 两张 ECL 用 TransposedSheetSpec 且实体列逐格实测
**Validates: 2.1, 2.2**　实体列取自 G4-9 R9 / G6-11 R10 的 `投资1：`~`投资X：`；
G6-11 的 R9 区标题不被当表头。变异：改用 `RowTableSheetSpec` ⇒ 投影恒空必红。

### Property 5: 三块锚行按 footer_carries_total_formula=False 声明
**Validates: 2.3**　G4-9 R24/R32/R46 与 G6-11 R25/R33/R47 均为锚行、非合计行。
变异：置 `True` ⇒ 引擎期待合计公式而锚行无公式必红。

### Property 6: 16384 列表的 UUID 落在有效内容列 +1 且页面设置不变
**Validates: 2.4**　UUID 列 == 12（有效 11 + 1）；`print_area` / `page_setup` 与基线一致；
instrumentation 定位不做全宽扫描。变异：UUID 放 `max_col+1` ⇒ 超 XFD 必红。

### Property 7: 两表 formula_columns 为空且模板公式全在页眉区
**Validates: 2.5**

### Property 8: BP-7 两处（或一处 + 一条不一致登记）处置完整
**Validates: 3.1, 3.2, 3.3**　G6-sppi 载入后 id 不匹配 `^fv-\d+-\d+$`；G4-main 侧有「实测有缺陷并已修」
或「实测无缺陷 + slice 不一致登记」二者之一的证据。变异：恢复任一处下标回退 ⇒ 必红。

### Property 9: 六条 payload json_pointer 逐条取 FD-1 登记 mode
**Validates: 4.1**　G6-sppi 指 `conclusion`、G4-main 走 storage contract 的 canonical、其余四条双写。
变异：统一写死 `remark` ⇒ G6-sppi 投影恒空必红。

### Property 10: 守卫探针按 http_client_binding 拼装
**Validates: 4.2**　四条 `http` entry 用 `http\.` 探针命中、两条 `api` entry 用 `api\.` 命中。
变异：全用 `api\.` ⇒ 四条失配必红。

### Property 11: G4-2 两区列集互不串用 + 模板插行声明被登记为正向证据
**Validates: 4.3**　两区 `field_specs` 不等；证据含 R11/R19 的「预留插行区」原文与 R41「每类默认6行」。

### Property 12: G4-7 / G6-5 的特殊几何逐格一致
**Validates: 4.4, 4.5**　G4-7 表头起于 B 列、footer 为 R23 锚行、`formula_columns=()`；
G6-5 无独立表头行、`D` 列仅 R9/R10 有公式（行级 mask）。变异：G6-5 用矩形 mask ⇒ 必红。

### Property 13: 两册「参考」sheet 排除清单不共用字面量
**Validates: 4.7**　G4 `参考-中证协…` 与 G6 `参考中证协…`（无连字符）分别登记；
变异：用同一字面量排除 ⇒ G6 那张漏排除必红。

### Property 14: TB 红线 + 键名按值取
**Validates: 5.1, 5.2**　sync 路径 TB 写次数 0；TB 键 == `G4-1-adj-tb-1501` / `G6-1-adj-tb-1503`。
变异：按 `G_ACCOUNT_CODES` 生成 `G4-1-adj-tb-1504` ⇒ 读不到真库数据必红。

### Property 15: 两册挂中性化
**Validates: 5.3**　G4 / G6 的 `StoreMergePlan` 带 `oo_crash_neutralization_fn`（裸 IF 186 / 192 格）。

### Property 16: G4 的 4 条重复字面量已改派生别名、G6 未被动
**Validates: 5.4**　`g4CrossHelpers` 的四处改为 `G4_ITEM_IDS.X` 派生；`g6CrossHelpers` digest 不变。

### Property 17: 六条验收先 seed 且断言载荷非空
**Validates: 5.5**　`seed_g4_g6_publish_e2e.py` 幂等造最小载荷；未 seed 时验收脚本显式失败。

### Property 18: 零回归现算逐项
**Validates: 5.6**　非 G4/G6 的 contract golden digest 逐项不变（不断言集合大小）。

## Testing Strategy

红判据先行：阶段 0 先打红 P1 / P2 / P4 / P6 / P8（BP-8 / 转置 / 16384 / BP-7 四条红基线）。
后端 pytest（`$env:PYTHONIOENCODING='utf-8'`，PBT `max_examples=5`）；前端 vitest；
真栈 Playwright `--workers=1`，fixture 分 `e2e/fixtures/g4-l2-cases.json` / `g6-l2-cases.json`。
🔴 六条主表真库全零 ⇒ 全部真栈用例前置 `seed_g4_g6_publish_e2e.py`（P17 守护该前置不被跳过）。
🔴 P2 的 RG-3 判据必须**真构造** `WorkpaperSyncAdapterRegistry` 跑，不 mock（F2 spec 同款纪律）。

## 顺带发现（登记，不在本 spec 处理）

1. 两册各带 `参考-根据剩余期限折算PD`(20r×2c/0 公式) —— 内容与文件名在两册**完全相同**，
   属模板重复件；建议模板治理时合并或标注同源。
2. G4 册 `债权投资三阶段划分G4-9` 与 G6 册 `其他债权投资三阶段划分G6-11` 的表头/三块结构近乎同构
   （仅 G6-11 多一行区标题）⇒ 若 `TransposedSheetSpec` 能参数化，两条声明应能共享 90% 结构；
   建议在 Task 实施时评估抽公共声明的 ROI（本 spec 默认各写一份，避免过早抽象）。
3. G4 有 29 个 definedName（`AFV` / `CCD` / `XRefCopy1Row` 等 legacy 残留），G6 为 0 ⇒
   G4 受管前须确认 instrumentation 不误伤命名区域（与 G3 的 480 个同族，归模板治理债）。
