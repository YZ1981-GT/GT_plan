# Design Document

## Overview

本 spec 在**不改数据库 schema、不新增端点、不新增依赖**的前提下，为 D4-33/34/35/36 补齐三块能力：

1. **导入导出修复**：后端 `_d4_import_export.py` 新增 4 组专用 parser / export 行构造 + item_id 映射分支，删除 2 个死配置；
2. 双向回写统一消费平台既有 `ContentMutationService`、`useWorkpaperSyncBridge`、durable callback、三方合并及批准的 contract-bundle representation；禁止新增 D4 自同步 composable 或仅 emit 事件。
3. **公式管理**：接线既有 `useD4FormulaEngine` + 新增一层用户覆盖（存 `checklist_responses`），覆盖值三处同口径。

同时**删除死代码** `useD4OtherGroup.ts` 与 **2 个死配置**（`D4-34`/`D4-36` 主键）。

## Architecture

### 分层与新增文件

```
后端（backend/app/routers/wp_render_strategies/_d4_import_export.py，单文件扩展）
├─ _SUPPORTED_SHEETS / _SHEET_HEADERS      ← 删除 D4-34(12列) / D4-36(12列) 主键
├─ _ITEM_ID 映射（import/export 两处的 elif 链）
│     D4-33              → D4-33-data
│     D4-34-rental       → D4-34-data   (合并写回，不覆盖 consults)
│     D4-34-consult      → D4-34-data   (合并写回，不覆盖 rentals)
│     D4-35              → D4-35-data
│     D4-36-forward      → D4-36-data   (合并写回，不覆盖 backward)
│     D4-36-backward     → D4-36-data   (合并写回，不覆盖 forward)
├─ import 分发 elif 链：_parse_d4_33_row / _parse_d4_34_rental_row /
│     _parse_d4_34_consult_row / _parse_d4_35_row /
│     _parse_d4_36_forward_row / _parse_d4_36_backward_row
└─ export 分发 elif 链：对应 6 个行构造函数（D4-33 既有分支保留，补对称 import）

前端（audit-platform/frontend/src/components/workpaper/）
├─ composables/useD4FormulaEngine.ts        ← 接线为主 + 可能新增方向化跨期判定
├─ composables/d4OtherGroupFormulaOverrides.ts   ← 【新增】公式覆盖层（单一读取入口）
├─ composables/d4OtherGroupPushPredicates.ts     ← 【新增】可推送判据单一真源
├─ composables/useD4OtherGroupDualWriteback.ts   ← 【新增】双模式同步 + A13 推送共享件
├─ composables/useD4InspectionWriteback.ts       ← 复用（已存在），必要时仅扩可选参数
├─ d4/other/D4TabOtherMargin.vue               ← D4-33 接线
├─ d4/other/D4TabOtherContract.vue             ← D4-34 接线（两区 adapter）
├─ d4/other/D4TabOtherCheck.vue                ← D4-35 接线（含 sampling 保护）
├─ d4/other/D4TabOtherCutoff.vue               ← D4-36 接线（两区 adapter，方向化判定）
└─ composables/useD4OtherGroup.ts              ← 【删除】死代码

守卫（后端 backend/tests/，前端 audit-platform/frontend/src/**/__tests__/）
├─ test_d4_33_36_import_export_roundtrip.py    ← 后端 6 个 parser 逐字段结构断言
├─ test_d4_33_36_item_id_and_dead_config.py    ← item_id 字面量 + 死配置删除断言
├─ d4OtherGroupWriteback.spec.ts               ← A13 推送 payload 字面量 + 空项不 emit
├─ d4OtherGroupFormulaOverride.spec.ts         ← 三处同口径 + 百分比口径 + 失败不静默
└─ mutate_d4_33_36_guards.py                   ← 变异检验 harness（12+ 锚点）
```

### 数据流

**导入导出（修复后）**

```
xlsx → load_workbook → 列头名校验（补齐后真实列头，非 _GENERIC_HEADERS）
     → 分发到 _parse_d4_XX_row（中文列头名 → 英文 key，金额走 _safe_float）
     → item_id 映射（不再走 f"{sheet}-rows" 兜底）
     → 多子区表：读既有 remark → 反序列化 → 合并本次子区 → 序列化写回（不覆盖另一区）
     → INSERT ... ON CONFLICT (wp_id, item_id) DO UPDATE SET remark
前端 watch(allResponses.get('D4-36-data')?.remark) → loadData() 重算派生值
```

**双模式回写**

```
excel 侧（OO 保存成功回调）
  → syncExcelToHtml(sheet, adapter)     [人工触发 or 保存后显式动作]
  → OO 侧取最新行列 → adapter.toStructured(rows) → persistAll → d4:save-items
  → 失败: fail-closed（中文报错 + 同步态不置「已同步」+ html 保持原值）

html 侧（人工点「同步到在线编辑」）
  → syncHtmlToExcel(sheet, adapter)     [仅人工触发，html 保存时绝不自动反写]
  → adapter.toRows(structured) → OO 侧写入 → 保存

读侧校对（只读）
  → compareBothSides(sheet) → 差异列表（行/字段级）→ 仅提示，绝不自动覆盖任一侧
```

**公式覆盖层**

```
统一公式参数入口：effective definition 由 F-SHELL v2 mutation 管理，后端权威执行并投影 HTML/OO；不读取 `field_overrides` 或 checklist remark 作为公式覆盖。

消费方（三处，必须同一个入口）：
  ① 表格渲染值   ← 组件 computed 调 getFormulaParam
  ② A13 推送判据 ← pushPredicates 调 getFormulaParam
  ③ 导出行构造   ← 后端 export 读同一 item_id（后端也读覆盖层，见下）
```

> 🔴 **一个必须显式设计的点**：导出行构造在**后端**执行，而覆盖层默认值在**前端引擎**里。为保证「三处同口径」（Property 4），后端导出必须**从 DB 读同一个 `{sheet}-formula-override` item_id** 取覆盖值，默认值表必须在**后端也有一份且与前端常量字面量一致**（由契约测试锁死双向一致，防止只改一侧）。这是本 spec 唯一需要跨端同步的常量清单，集中在 `d4OtherGroupFormulaDefaults.json`（`backend/data/`，前端运行时通过既有静态数据端点读取或直接 import 同源文件）。

## Key Decisions

| # | 决策 | 理由 |
|---|---|---|
| DEC-1 | item_id 错位改后端映射，不改前端键 | 前端键已被 watch/persistAll/onBeforeUnmount 多处引用；后端 `-rows` 键零消费者。与姊妹 spec 同方向 |
| DEC-2 | 毛利率统一到引擎**百分比**口径 | 引擎是单一真源；`*100` 局部补丁会造第四套口径（Property 5） |
| DEC-3 | 主 sheet 死配置 `D4-34`/`D4-36` 删除（非报错短路） | 前端从未有主键入口，保留即 Property 12 死配置 |
| DEC-4 | `useD4OtherGroup.ts` 直接删除 | 平台铁律「死代码立即删除」；其类型与真实组件全不符（`isAnomalous: boolean` vs 实际 string），留着只会误导 |
| DEC-5 | 科目码统一 `6051`/`其他业务收入` | 本 spec 与姊妹 spec（`6001`）的唯一科目差异，必须守卫锁死防照抄错 |
| DEC-6 | 公式覆盖层存 `checklist_responses`，不新增表 | 平台铁律禁止新增数据库表；三元组 `(wp_id, sheet, key)` 天然映射现有 `(wp_id, item_id)` + JSON |
| DEC-7 | 跨期判定按方向拆分（`isCrossPeriodForward`/`Backward`） | 引擎现有 `isCrossPeriod` 是不区分方向的「分居两侧」判定；D4-36 两区方向语义相反，混用会误判 |
| DEC-8 | D4-35 的 `sampling`/`periodAmount` 导入时不覆盖 | 抽样设计是审计判断，不该被一批凭据导入冲掉 |
| DEC-9 | 双模式同步在共享层，四表传 adapter | 四张表结构差异大（`{bizTypes}`/`{rentals,consults}`/`{rows,sampling,periodAmount}`/`{forward,backward}`），adapter 显式声明，禁止通用 JSON 猜测 |
| DEC-10 | html→excel 仅人工触发 | D2-2 门控纪律：防双写冲突；html 保存时自动反写会造成回环 |

## 与既有系统的集成点

- **复用不改**：`useD4InspectionWriteback`（`pushToA13` + `appendToD41Note`）、`useD4ImportExport`（三端点，四表前端已接）、`d4:save-items` → `GtD4OperatingRevenue` PUT 通道、`a13:push-misstatement` 白名单事件 → `useA13MisstatementBridge` 落 `unadjusted_misstatements`。
- **可能扩展（仅共享件内）**：`useD4InspectionWriteback.pushToA13` 如需 `sourceSheet` 中文表名，只允许**加可选参数**，不动既有调用方（D4-13~20）。
- **不接入**：`sync-from-workpaper` 附注推送（四表 `note_workpaper_sync_registry.json` 零命中）、`TB()`/`WP()` 运行时求值、`trial_balance` 回写。

## 风险与缓解

| 风险 | 缓解 |
|---|---|
| D4-33 毛利率改百分比口径会改到既有数据展示 | 改的是**运行时派生值**（不落库），无存量数据迁移问题；但必须有变异锚点断言百分比口径（RED 防回归小数比率） |
| 后端与前端默认公式常量清单漂移 | 集中到 `d4OtherGroupFormulaDefaults.json` 单一真源，契约测试双向锁死；禁止在两端各写一份 |
| 多子区合并写回把另一区冲掉 | Property 3 专测（租→咨询不丢、forward→backward 不丢），变异锚点把导入改成整对象覆盖必红 |
| D4-36 backward 按列序映射交叉错位 | parser 一律按列头名映射（`_safe_header_map`），变异锚点把 backward 改成按列序必红 |
| 公式覆盖层 fail-open 掩盖配置损坏 | Property 11 专测三类异常，守卫断言必须有可见错误信号而非静默返回默认值 |
| 照抄姊妹 spec 把 `6001` 抄成 D4-33~36 | Property 8 + 变异锚点（改 `6001` 必红）双保险 |

## 边界与不做

- 不做 D4-33~36 的源模板字段扩充（严禁自造检查维度，字段以组件现有类型为准）。
- 不做 D4-33 与 D4-3（主营明细）的取数联动（`auto_data_source` 机制另有 spec）。
- 不做四张表的 AI 生成增强（现有 AI 辅助说明/结论保留不动）。
- 不做 OO 引擎的公式求值改造（OO 侧公式留在 OOXML 里）。


## Cross-Spec Governance Constraints

双向回写统一消费平台既有 `ContentMutationService`、`useWorkpaperSyncBridge`、durable callback、三方合并及批准的 contract-bundle representation；禁止新增任何 D4 自同步 bridge。HTML/OO 为真双向内容，冲突必须由用户裁决并留痕。

F-SHELL v2 mutation 为唯一公式入口，effective definition 同时投影 HTML/OO；mask 只保护普通值写入，公式授权编辑沿统一解析、权限、CAS、审计路径。支持 expression/refs/params 自定义；不使用 checklist remark 伪装 override，不维护前后端双默认，不把纯函数当声明。预设升级不覆盖 custom，删除/恢复默认分开，scope 为 wp/sheet/row/field，单位显式，空/除零/error 不写 0，未知函数 blocked。

A13 推送独立且须人工认定金额方向；不以 amount=0 汇总定性风险，不 abs 化差异，不把抽凭金额直接当错报。模板 finder/index 身份未核定前阻塞；验收逐张覆盖双向、重新打开公式编辑、导出与项目隔离。
