# d567 Task 0 前置依赖核查证据

**核查日期**：2026-09-26　**判定方法**：`git show HEAD:<path>`（不读工作树，spec 纪律）＋全仓 grep

## 结论一句话

**前置 A/B/C/D 全部未满足（上游 D1 spec 框架层真 0% 未入 HEAD），前置 E 三家全 False。**
⇒ 除 **Task 1（聚合键缺陷，需求 5，不受任何前置阻塞）** 外，本 spec 全部任务阻塞。

## 逐前置判定

| 前置 | 内容 | 判定 | 证据 |
|---|---|---|---|
| A | 上游框架层 + `aging_layout` 参数化入 HEAD（D1 spec 任务 16） | ❌ **未满足** | `git show HEAD:backend/app/services/workpaper_sync/row_table_engine.py` Exit 1（文件不存在）；全仓 grep `class RowTableSheetSpec` / `aging_layout` 仅命中 `.kiro/specs/*` 文档，零生产代码 |
| B | `AdjudicationSheetSpec` 已交付 | ❌ **未满足** | `git show HEAD:.../adjudication_sheet_spec.py` Exit 1；grep `class AdjudicationSheetSpec` 零命中 |
| C | `merge._protection` 格级判定 + `_mask_spans_data_column` 入 HEAD | ❌ **未满足** | 上游 d1 spec tasks.md Task 0 自记「`merge.py` 的 `_mask_spans_data_column` HEAD 不含、仍是只比列旧实现」，且 d1 spec 整体 0/35 未实施 |
| D | 上游位移判据按 provider 参数化（D1 spec 任务 24） | ❌ **未满足** | 依赖 A 的框架层，D1 spec 0/35 未实施 |
| E | 三家 `adapter_registered` 是否 True | ❌ **全 False** | 真库 `register_from_manifest()` 只注册 `{d2,d4,g7,h1}`；实测 planned=186 / registered=0（见 `check_task70_oo94_full_entry_scenario_gate.py` S6 记录），D5/D6/D7 无 current published representation |

## 佐证：D5 provider 现状仍是老写法

`read_code phase5_d5_receivables_financing.py` 的符号表**无** `MANAGED_FIELD_SPECS`、无 `RowTableSheetSpec`，
仍是 `_rows_table_payload` / `build_contract_payload` 等各家手写函数 ⇒ provider 尚未声明化，上游任务 16 未落。

## 阻塞判定（按 tasks.md blocking 规则）

- IF A 未满足 THEN **全部阻塞** —— 现状即此。
- 唯一例外：**Task 1（需求 5 聚合键缺陷）不受任何前置阻塞**，纯前端 bugfix，本轮执行。
- 阶段 1~6（Task 2~22）的**声明层代码**在框架层落地前无类型可依（`RowTableSheetSpec`/`AdjudicationSheetSpec` 不存在，import 即报错），
  故本轮**不铺量**，如实停在 Task 1，避免造出依赖不存在符号的假绿声明。

## 处置

1. 本轮交付 Task 1（含红判据），独立 commit。
2. 其余任务标 `[ ]`（阻塞），在 tasks.md 顶部登记本核查结论与卡点，等上游 d1 spec 框架层入 HEAD 后解冻。

---

## Task 1 交付记录（2026-09-26，需求 5）

**改动文件**：
- `audit-platform/frontend/src/components/workpaper/composables/d6SheetLabels.ts` — 追加 `hasJsonRows` / `isD6SheetComplete` 纯函数导出
- `audit-platform/frontend/src/components/workpaper/composables/d7SheetLabels.ts` — 追加 `hasJsonRows` / `isD7SheetComplete` 纯函数导出
- `audit-platform/frontend/src/components/workpaper/d6/D6TabIndex.vue` — 删内联判定，改 import 纯函数
- `audit-platform/frontend/src/components/workpaper/d7/D7TabIndex.vue` — 同上
- `audit-platform/frontend/src/components/workpaper/__tests__/d67TabIndexAggregateKeyFix.spec.ts` — 红判据（新增）

**四处聚合键修复（需求 5.1/5.2）**：
| 位置 | 旧（无写入方聚合键） | 新（真实写入方分区键） |
|---|---|---|
| D6-6 | `D6-6-rows` | `D6-6-block1-rows` \|\| `D6-6-block2-rows`（任一有行即已填） |
| D6-8 | `D6-8-rows` | `D6-8-single-rows` |
| D7-4 | `D7-4-rows` | `D7-4-credit-rows` \|\| `D7-4-debit-rows` |
| D7-7 | `D7-7-rows` | `D7-7-period-rows` \|\| `D7-7-post-rows` |

真实写入方均已 grep 实证（`useD6Inspection` / `useD6EclCalculation` / `useD7Analysis` /
`useD7VoucherCheck` 及 `_d6/d7_import_export.py` 回写映射）。

**判据不镜像键名（需求 5.3 / Property 10）**：判据直接 import 生产纯函数 `isD6/D7SheetComplete`
（组件从同一处 import），不复刻键映射。变异验证：临时把生产 `isD6SheetComplete` 的 D6-6 case
改回 `D6-6-rows` ⇒ 对应用例 + Property 11 守卫用例实测打红（`expected true to be false`），还原后复绿。

**零残留（需求 5.4 / Property 11）**：前端 `audit-platform/frontend/src/**` grep
`'D6-6-rows'|'D6-8-rows'|'D7-4-rows'|'D7-7-rows'` 的 `hasJsonRows` 调用零命中（仅注释里提及旧键名说明）。

**验证**：`d67TabIndexAggregateKeyFix.spec.ts` 14 用例全绿；连同既有 `d6/d7SheetLabels.spec.ts`
共 20 用例全绿（零回归）；5 文件 0 diagnostics。

**说明**：`b23Property7And8.pbt.spec.ts` 的 `fc.stringOf is not a function` 是既有 fast-check v3
API 不兼容问题（v3 已移除 `fc.stringOf`），与本次改动无关（grep 实证该文件不引用任何本次改动文件）。
