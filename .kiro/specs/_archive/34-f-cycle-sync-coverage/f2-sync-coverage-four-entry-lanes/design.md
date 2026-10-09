# Design Document

## Overview

F2 存货是 F 循环里唯一「一个科目四个 entry」的底稿：main（审定/明细册）、stocktake（监盘册）、valuation（跌价册）、
special（合同履约成本册）。本 spec 用**一个 Wave 0**解决三 entry 共用幻影码 `F2I` 的 matcher 冲突与 store 落点，
之后四条 lane 各自走 F1 同款的从零 canary 链路（FC-1）。

与 F1/F3/F4/F5 的差别：
- **四个 provider**（每 entry 一个），但共享一组 sheet 层声明模式（明细表族一个声明文件）。
- **BP-7 已在真库发生**（`F2-3-rows[0].id="1"`），main lane 必须先修行身份。
- **dict 子数组载荷占多数**（valuation / special 全部 7 张），行表路径要走 D1-7 式专用门面。
- **权威模板自身有公式缺陷**（`F2-26!J9`），走模板覆盖层修，不改字节。

## 上游锚定

沿用 F1 spec 上游锚定表；额外依赖：
- `excel-template-override-layer-and-onlyoffice-template-editor` —— F2-26 模板缺陷的修复通道（裁决 F2-H5）
- G7 三 entry 同码裁决（`workpaper_sync_entry_wp_code_adjudication.json` G7 条目）—— RG-3 同型先例
- D1-7 `phase5_d1_07_memo.py` —— dict 载荷内子数组行源的专用投影/合并门面（`_build_region_projection` / 区域合并）

## Architecture

### 四 lane 与 Wave 0

```
Wave 0（共用）：matcher 域裁决 F2-H1 + store 落点裁决 F2-H2 + 四条 wp_code 裁决条目 + RG-3 红判据
   ├─ lane M（main）      phase5_f2_inventory_main.py        canary F2-6 → F2-3/4/8/9 → F2-7 → F2-12 → F2-5 → F2-10/11/13 → [F2-2 核] → F2-1
   ├─ lane S（stocktake） phase5_f2_stocktake_bundle.py      canary F2-25（双区）→ F2-26（双区，模板覆盖层修 J9 后）
   ├─ lane V（valuation） phase5_f2_inventory_valuation.py   canary F2-48 → F2-49 → F2-47（FC-10 换算落地后）
   └─ lane P（special）   phase5_f2_inventory_special.py     canary F2-57 → F2-58 → F2-55 → F2-56（稳定 id 修后）
```

每条 lane 的 canary 选择原则同 F1-H1：验证发布链、失败面最小（单区 / 无 FC-10 命中 / 无 BP-7 / 无模板缺陷）。

| lane | canary | 理由 |
|---|---|---|
| M | F2-6 | 共享 `useF2DetailSheet`，footer 标记在 A 列（F2-3 在 B 列），无在手订单扩展列 |
| S | F2-25 | 双区但有合计行、无模板缺陷；F2-26 两区无 footer 且 J9 模板缺陷 ⇒ 后置 |
| V | F2-48 | dict `{products[]}` 最简（真库 16 B）、公式仅 `H=F*G`；F2-47 FC-10 命中后置 |
| P | F2-57 | dict `{products[]}`、单级表头、无 FC-10 列；F2-56 id 生成缺陷后置 |

## Components and Interfaces

```
backend/app/services/workpaper_sync/
  phase5_f2_inventory_main.py          ← lane M provider（ENTRY_ID=xlsx/gt-f2-inventory-main，WP_CODES={"F2I"}）
  phase5_f2_main_detail_sheets.py      ← F2-3/4/6/8/9 五个 RowTableSheetSpec（一个文件，只差 sheetCode/列集/footer 列）
  phase5_f2_main_07_outsourced.py / _12_contract_perf.py / _05_turnover.py / _10_11_13_blocks.py
  phase5_f2_main_01_adjudication.py
  phase5_f2_stocktake_bundle.py        ← lane S provider（WP_CODES={"F2S"}）
  phase5_f2_stocktake_25_26.py         ← 四个 spec（25 两区 + 26 两区）
  phase5_f2_inventory_valuation.py     ← lane V provider
  phase5_f2_valuation_47_48_49.py      ← 三个 dict 子数组 spec + 专用门面
  phase5_f2_inventory_special.py       ← lane P provider
  phase5_f2_special_55_58.py           ← 四个 dict 子数组 spec + 专用门面
backend/data/workpaper_sync_contracts/f2.{inventory_main,stocktake,inventory_valuation,inventory_special}.json
```

sheet 层文件仍只含常量与 spec 实例；dict 子数组的投影/合并门面放在 provider 层（D1-7 同位置），不进框架层
（避免在引擎加 `if is_f2`）。若四张以上 dict 子数组 sheet 的门面逐字重复，SHALL 上提为框架层通用
`StoreKind.dict` + `rows_path` 声明位（需求 4.1 的演进路线，另立 task，不在 canary 阶段做）。

### 受管区清单（实测几何；UUID 列须 Task 2 逐格核空）

| lane | sheet_key | managed_sheet | store_item_id | 表头 | 数据 | footer | formula_columns |
|---|---|---|---|---|---|---|---|
| M | `f26-managed` | 四、自制半成品明细表F2-6 | `F2-6-rows` | R6/R7 | R9-24 | R25「合计」(A) | F,I,L,N,O,P |
| M | `f23-managed` | 一、原材料明细表F2-3 | `F2-3-rows` | R6/R7 | R9-24 | R25「合计」(**B**) | F,I,L,N,O,P |
| M | `f24/f28/f29-managed` | F2-4 / F2-8 / F2-9 | `F2-4/8/9-rows` | R6/R7 | R9-24 | R25 | 同上（F2-8 另 V/W/X 在手订单列） |
| M | `f27-managed` | 五、委托加工物资明细表F2-7 | `F2-7-rows` | R6/R7 | R8-16 | R17 | G（`=E*F`） |
| M | `f212-managed` | 十、合同履约成本F2-12 | `F2-12-rows` | R6/R7 | R8-19 | R20 | I（`=F+G-H`） |
| S | `f225-exist` / `f225-floor` | 抽盘结果汇总表F2-25 | `F2-25-rows` / `F2-25-floor-rows` | R14/R15 · R29/R30 | R16-26 · R31-41 | R27 · R42 | J,K,L |
| S | `f226-after` / `f226-before` | 盘点倒轧表F2-26 | `F2-26-after-rows` / `F2-26-rows` | R7 · R16 | R8-14 · R17-23 | 锚行 R15 · R24（无合计） | J,L,M |
| V | `f248-managed` | 长库龄 呆滞 超过保质期存货明细表F2-48 | `F2-48-rows`·`products` | R5/R6 | R7-16 | R17 | H |
| V | `f249-managed` | 跌价转回F2-49 | `F2-49-rows`·`products` | R5/R6 | R7-15 | R16 | T,X |
| V | `f247-managed` | 跌价准备测试表F2-47 | `F2-47-rows`·`products` | R18/R19 | R20-29 | R30 | G,Q,T,U,V,W,X,Z |
| P | `f257-managed` | 合同履约成本减值准备测算表F2-57 | `F2-57-rows`·`products` | R5 | R6-17 | R18 | E,H,I,J,L |
| P | `f258-managed` | 亏损合同预计损失测算表F2-58 | `F2-58-rows`·`products` | R5（R6 说明行） | R7-20 | R21 | F,G,H,J |
| P | `f255-managed` | 合同履约成本构成明细表F2-55 | `F2-55-rows`·`products` | R5/R6 | R7-24 | R25 | I,N,S,T,U,V,W,X,AE,AF,AG,AH,AI,AJ |
| P | `f256-managed` | 合同履约成本检查表F2-56 | `F2-56-rows`·`samples` | R15/R16 | R17-31 | R32 | （无） |

main lane 的 F2-5（分组小计 R12/R16/R26 + 合计 R27）与 F2-10/11/13（多块）形态特殊，Task 2 实测后单列；
F2-2（派生汇总）、F2-14（hub）、F2-1（审定）见需求 6。

## Data Models

不新增数据模型。四类 store 形态：`rows`（main 明细 / stocktake）、`dict` + 子数组（valuation / special）、per-cell
（F2-1 `F2-1-${block}-${rowKey}-${field}`）、hub（F2-14）。

## 关键裁决

### 裁决 F2-H1：三 entry 共码 `F2I` 用 `sheet_keys` 互斥域解，不改 matcher 路由模型

`EntryMatcher.overlaps()`（registry.py L207-L220）：同 document_type、wp_codes 相交时，**任一侧 `sheet_keys` 为空即判重叠**；
两侧都非空且不相交则不重叠。⇒ 三个 F2I adapter 各声明自己受管 sheet_key 集合（main `f2x-*` / valuation `f24x-*` /
special `f25x-*`，互不相交）即可同时注册。运行时解析走 `resolve_for_entry(entry_id)`（按值实测两处调用点），不经
wp_code 路由，故 `sheet_keys` 只承担「注册期互斥」而不影响解析。
- 否决：改 `EntryMatcher` 为「按 entry 路由」—— G7 条目 `resolution` 字段已提出但标「独立设计决策，不在 provisioning
  范围内」，改动面是 registry 全局，不应由 F2 单方面引入。
- 否决：给三 entry 发明不同幻影码 —— manifest 由生成器从宿主 CamelCase 派生（`F2I` = GtF2**I**nventory*），改它要动生成器
  且影响所有循环。
- 风险：canary 阶段每个 lane 只有 1 张受管 sheet，`sheet_keys` 最小且互斥；后续扩 sheet 时 SHALL 有判据确保新 key 不跨 lane。

### 裁决 F2-H2：store 落点取父码 `F2`，子码孤立载荷只读登记

真库 35 键全在父码 wp（项目 `0ec33ac9`，无 `file_path`）；项目 `2aa00f57` 的 3 个子码 wp 各 1 键、且这些子码 wp 有
`file_path`（`F2-22.xlsx` 等，2026-07-04 生成）。provisioner 定位宿主取父码 `F2`（与 D/E 循环「store 落父码」一致）；
子码孤立载荷 SHALL 不迁移、不删除，只在证据中登记（删数据违反「先进回收站」铁律，迁移需业务确认）。

### 裁决 F2-H3：BP-7 修复先于 main lane 任何明细受管

`loadRows` 改为：缺 id 时 `crypto.randomUUID()` 铸 id，并在首次载入后立即 `persistRows()`（与 F1 `generateRowId` 同写法）；
真库 `id="1"` 这类纯数字下标 id SHALL 在迁移判据中被识别并重铸（纯数字 id 与下标无法区分，保留即等于保留 BP-7）。
同型 6 处 composable + `useF2ContractCostCheck.fillFromSampling` 一并修。

### 裁决 F2-H4：明细表族一个声明文件

F2-3/4/6/8/9 共享 `useF2DetailSheet`（`F2_DETAIL_SHEET_CONFIGS` L33-L81 按值读），前端只差 `sheetCode` / `hasQuantity` /
`noteProfile` / 在手订单列 ⇒ 声明层用一个 spec 工厂函数？—— 🔴 否：sheet 层文件禁 `def`（E1 Task 13 判据）。改为五个显式
spec 常量 + 共享字段元组常量（只差列集的部分各自声明），与 E1-7/8/9 同写法。

### 裁决 F2-H5：模板缺陷走覆盖层，不改权威字节

`F2-26!J9=J2+H9-I9` 是致同权威模板缺陷（同列 13 行对照 + J2 在标题合并区内，按值实测）。`backend/wp_templates/` 运行时只读、
sha 冻结进契约 ⇒ 修复 SHALL 经模板覆盖层（既有 spec），覆盖后契约的 `template_sha256` 指向覆盖后字节；在覆盖层落地前
F2-26 区一 SHALL 不受管（区二不受影响，可先接）。

### 裁决 F2-H6：dict 子数组门面放 provider 层，重复四次再上提

valuation/special 7 张 dict sheet 各需「投影：`payload[rows_path]` → 行表投影；合并：只替换 `rows_path`、保留其余键」。
先照 D1-7 在 provider 层实现；当同形门面出现 ≥4 份时，SHALL 另立 task 把 `rows_path` 上提为 `RowTableSheetSpec` 声明位
（框架层改动需走 golden digest 零回归门）。

## Error Handling

| 场景 | 处理 | 依据 |
|---|---|---|
| 第二个 F2I adapter 注册 | `sheet_keys` 为空 ⇒ RG-3 拒绝（红判据必须先观测到）；互斥后注册成功 | F2-H1 |
| 明细行 id 为纯数字 | 迁移判据识别并重铸；受管前不得残留 | F2-H3 |
| footer 标记不在 A 列（F2-3） | 声明位 `footer_marker_column` 或暂不受管，不静默失配 | 需求 2.4 |
| 无合计行（F2-26） | footer 指向下一锚行 + `footer_carries_total_formula=False` | 需求 3.4 |
| 模板无承载列（F2-24） | HTML-only + 中文原因 | 需求 3.5 |
| 前端百分数 × 模板小数（F2-47 N/O） | 受管关闭直到 FC-10 换算落地 | 需求 4.3 |
| dict 合并 | 只替换 `rows_path`，其余键逐字保留 | F2-H6 |
| 他册 sheet（F2-16/18~20/29~32 等）在 main 宿主渲染 | 不进受管集合，保持 legacy 并登记假双向 | FC-3 |

## Correctness Properties

### Property 1: 四 entry migration_state 正确变更
**Validates: 7.4**　每个 entry 发布链通后 `legacy_fake_bidirectional` → `adapter_registered`。

### Property 2: RG-3 冲突先红后绿
**Validates: 1.1, 1.2**　①`sheet_keys` 为空的两个 F2I matcher 真跑 `register()` ⇒ `MatcherOverlapError`；
②互斥 `sheet_keys` 后三者同时注册成功。变异：给任一 matcher 加入另一 lane 的 sheet_key ⇒ 必红。

### Property 3: `store_item_id` 逐字等于按值实测（含模板化 `${sheetCode}-rows` 与 dict 子数组路径）
**Validates: 2.3, 4.1, 5.1**　变异：`F2-26-rows` 与 `F2-26-after-rows` 对调 ⇒ 区一/区二数据互串，必红。

### Property 4: BP-7 修复后行身份稳定
**Validates: 2.2**　载入缺 id / 纯数字 id 的载荷 ⇒ 铸 UUID 并回写；插删行后同一逻辑行 id 不变。
变异：恢复 `String(r.id || i + 1)` ⇒ 删首行后其余行 id 全部错位，必红。

### Property 5: 明细表族五 spec 只差声明，不含算法
**Validates: 2.3**　声明文件 AST 无 `def`/`class`；五 spec 字段元组共享部分逐字相同。

### Property 6: 明细派生列双模式等价（FC-5）
**Validates: 2.5**　hypothesis（`max_examples=5`）：前端 `enrichRow` 的 N/P/F/I/L/O 与模板公式等价。

### Property 7: F2-26 J9 模板缺陷覆盖后两模式相等
**Validates: 3.3**　覆盖层落地前判据红（记录）；落地后 OO 与 HTML 第 9 行实存数量相等。

### Property 8: dict 合并只动 `rows_path`
**Validates: 4.1, 5.1**　变异：整体替换 dict ⇒ `sampling` / `auditProcedure` / `statNote` 丢失，必红。

### Property 9: FC-10 单位守恒
**Validates: 4.3**　F2-47 N/O 列：store 3（%）⇄ OO 0.03；变异：去掉换算 ⇒ OO 显示 300%，必红。

### Property 10: prefill 三块修复且有 `--check` 守卫
**Validates: 4.5, 6.3, 7.2**　`[17]` → `存货审定表F2-1`、`[132]` 恢复原名、`[118]` 22 条 WP 按 ADR-F2 改写；新 `--check` 对三种错法各自必红。

### Property 11: 其余 contract golden digest 不变
**Validates: 7.3**

### Property 12: F2-1 受管后 TB 写次数为 0
**Validates: 6.4**

### Property 13: main 宿主不把他册 sheet 判为受管
**Validates: 7.1**　对 F2-16/F2-18/F2-29 等 sheetName 断言 `isF2SyncManagedSheet=false`。

### Property 14: BP-5 已修的那一半不复发 + 受管路径不经整册码回落
**Validates: 1.6**　①`find_template_file('F2')` == `F2-1至F2-14 …审定明细表类…`（== main 的 template_ref）
②`_PRIMARY_TEMPLATE_TIERS` 第一层「审定」在 F2 候选集命中数 **== 1**（BP-5 `latent_regression_shape` 的复发条件）
③四条 lane 的受管解析走 `resolve_for_entry(entry_id)`、调用链上无 `find_template_file(wp_code)`。
变异：向候选集注入第二本含「审定」的册名 ⇒ 第一层命中数 2 ⇒ 必红。
🔴 不覆盖 BP-5 的结构性缺口（约 60 sheet 无 sheet→模板映射，归另立 spec），只证明它不落在受管路径上。

### Property 15: 四条 lane 的模板字节锚取 slice 值，不可达合册不入契约
**Validates: 1.7**　①四个 `TEMPLATE_SHA256` 与 slice `authoritative_templates.files[].sha256` 逐字相等
②`afc762843ffee1c3…`（`F2存货.xlsx`）不出现在任何 F2 契约 / authority model 里
③「不在 `_index.json`」由现算得出（`files[].relative_path` 不含它），不读 slice 快照。
变异：把该合册 sha 填进任一 lane ⇒ 必红。

### Property 16: manifest 与 slice 的 capability 不一致是既登记事实，不被「对齐」
**Validates: 1.8**　断言 manifest `capability=="single_onlyoffice"` 且 slice 重裁 `capability is None`（必须不等，FC-12）；
overlay 的 `defaults_by_component.GtOnlyOfficeSheet` 未被本 spec 改动（文件 digest 不变）。
变异：改 overlay 使两者相等 ⇒ 翻掉 180 条其他 entry 且把默认值当裁决真源，必红。

## Testing Strategy

同 F1。四条 lane 的 e2e fixture 分文件（`e2e/fixtures/f2-{main,stocktake,valuation,special}-l2-cases.json`），
`--workers=1`；Wave 0 的 RG-3 判据在 pytest 层真构造 `WorkpaperSyncAdapterRegistry` 跑，不 mock。

## 顺带发现（登记，不在本 spec 处理）

1. 提交 `873ee7dce` 的批量替换误伤 sheet 名（块 `[132]`）⇒ 建议对 `prefill_formula_mapping.json` 加全局
   「sheet 名 ∈ 模板 tab」CI 守卫（各循环已有零散守卫，无全局统一）。
2. `F2-64!C101:C104` 引用形态离群（IPO 册）⇒ 移交 IPO 册 spec 人工判定。
3. `useF2ValuationDateSheet.ts` / `useF2ValuationTestSheet.ts` 零消费方死代码；F2-35 读 `F2-7-rows` 恒 null（宿主只载入 ≥33 的键）。
4. 模板 `F2-13!A55=A25` 标签引用（非缺陷，登记以免误报）。
