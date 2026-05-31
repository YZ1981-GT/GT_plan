# Bugfix 需求文档：底稿模块防退化卡点治理

## 问题陈述

底稿模块的防退化护城河（pre-commit 卡点）因路径 bug、假绿基线、卡点缺失而**形同虚设**。具体表现为 6 个相互关联的 bug，共同后果是"瘦身成果不被保护、大文件可无限增长、死代码残留、金额精度可自由退化"。

## Bug 条件分析

### Bug 1 — 已瘦身 view 的白名单假绿

**当前错误行为 C(X)**：`file_size_whitelist.txt` 中 `WorkpaperEditor.vue` 基线锁 2342、`WorkpaperList.vue` 锁 3464，但两文件实测仅 758 / 476 行。卡点允许文件涨回 3 倍才报警——瘦身成果完全不被保护。

**触发条件**：WorkpaperEditor 在 759–2342 行之间增长时，pre-commit check_file_size 不报警（假绿）。

**期望正确行为**：白名单基线贴近实测值 + 合理余量（WorkpaperEditor→820 / WorkpaperList→520），超出即报警。

**修复成功标准**：
- WHEN WorkpaperEditor.vue 行数超过 820，THEN pre-commit check_file_size SHALL 报警阻断
- WHEN WorkpaperList.vue 行数超过 520，THEN pre-commit check_file_size SHALL 报警阻断

### Bug 2 — 游离子组件未登记白名单

**当前错误行为**：`GtDFormConfirmation.vue`（1311 行）和 `GtEControlTest.vue`（1279 行）未在 whitelist 登记。一旦 check_file_size 卡点正常运行，这两个文件会直接触发 pre-commit 阻断（因超过默认上限 1500/800 行）。

**触发条件**：任何 commit 触碰这两个文件时 pre-commit 报错阻断（误报，因为它们是已知的待拆大文件）。

**期望正确行为**：登记现状值 + 合理余量（GtDFormConfirmation→1380 / GtEControlTest→1350），标注"待拆"注释。真正拆分是 `gtdform-test-and-shrink` spec 的事。

**修复成功标准**：
- WHEN 开发者 commit 触碰 GtDFormConfirmation/GtEControlTest，THEN pre-commit SHALL 通过（不误报）
- WHEN 这两个文件超过登记基线，THEN pre-commit SHALL 报警

### Bug 3 — float 金额防退化卡点已丢失

**当前错误行为**：V3 spec Req 2 建立的 `_check_no_float_amount.py` 卡点**已不存在**（fileSearch 0 命中），CI 也从未调用。底稿后端 10+ service 用 `float()` 处理金额无防退化保护。

**触发条件**：任何 service 新增 `float()` 金额计算时，无卡点阻止退化。

**期望正确行为**：存在 `backend/scripts/check/check_no_float_amount.py`（正式工具，无 `_` 前缀），接入 pre-commit，有明确 baseline。

**风险分级（非一刀切）**：
- 安全（可豁免）：`float()` 仅用于 JSON 序列化输出（如 wp_cross_check_service 用 Decimal+容差做核心计算，float 仅序列化）
- 需复核：`float(debit) - float(credit)` 差额计算（如 wp_ai_service / wp_explanation_service），若结果回写底稿有精度损失风险

**修复成功标准**：
- WHEN 新增 `float()` 金额计算代码，THEN pre-commit check_no_float_amount SHALL 报警
- THE 卡点 SHALL 有 baseline 文件记录已知豁免项（区分安全 vs 需复核）

### Bug 4 — EDITOR_MAP 死路由

**当前错误行为**：`WorkpaperEditor.vue` 中 EDITOR_MAP 路由分支（table/form/word/hybrid 4 个子编辑器）是死代码——docker psql 实测 `wp_template_metadata` 表不存在、`derive_component_type` 白名单永不产出这 4 个值、零底稿命中。

**触发条件**：永远不触发（死代码），但占用代码体积 + 维护认知负担 + 误导新开发者以为这是活跃路径。

**期望正确行为**：删除 EDITOR_MAP 路由分支 + 4 个子编辑器的路由注册。**保留 SFC 文件本身**（WorkpaperTableEditor/FormEditor/WordEditor/HybridEditor）作为 composable 素材库（增删行逻辑后续可抽 useEditableTableRows）。

**修复成功标准**：
- WHEN 删除后，THEN WorkpaperEditor.vue 中无 EDITOR_MAP 引用
- WHEN 删除后，THEN `useEditorMode.ts` 中无 table/form/word/hybrid 分支
- Preservation：现有 vitest / vue-tsc 0 回归

### Bug 5 — backend/scripts/ 子目录化路径 bug（成批债）

**当前错误行为**：脚本从 `backend/scripts/` 迁入子目录后，`Path(__file__).parent` 或 `parents[N]` 层级未同步更新，导致读外部数据文件路径失效且**静默不报错**（返回空/默认值）。已知 4 个同款 bug 已修，但可能还有未发现的。

**触发条件**：任何 `backend/scripts/{subdir}/` 下的脚本用 `Path(__file__).parent` 读仓库根或 backend 根的数据文件。

**期望正确行为**：grep 全 `backend/scripts/` 子目录排查同款，统一改为 `ROOT / 显式相对路径`。

**修复成功标准**：
- WHEN grep `Path(__file__).parent` 在 `backend/scripts/` 子目录下，THEN 结果为 0（或仅读同目录文件的合法用法）
- THE 所有脚本读外部数据文件 SHALL 用 `ROOT / "backend" / "scripts" / "..."` 显式路径

### Bug 6 — INDEX.md 计数过时

**当前错误行为**：`.kiro/specs/INDEX.md` §1/§2/§4 写 WorkpaperEditor 2167 / WorkpaperList 3241 / active 11，实测 758/476/15。

**期望正确行为**：刷新为实测值。

**修复成功标准**：INDEX.md 中 WorkpaperEditor/WorkpaperList 行数与 `wc -l` 实测一致，active spec 数与 `ls .kiro/specs/ | wc -l` 一致。

## Preservation 检查（修复不破坏）

- 修复后 pre-commit `check_file_size` 全绿（白名单生效 + 无新增超限 + 无膨胀）
- 修复后 vitest 0 fail / vue-tsc 0 errors（EDITOR_MAP 删除不引入回归）
- 修复后现有 pytest 0 回归（float 卡点是新增检查，不改业务代码）
- 修复后 `git status --porcelain` 无意外文件变更

## 范围边界（不做）

- 不修改任何业务逻辑（纯治理/卡点/配置/死代码清理）
- 不拆分 GtDFormConfirmation/GtEControlTest（那是 gtdform-test-and-shrink spec 的事，本 spec 只登记白名单防阻断）
- 不改 float() 业务代码（只建卡点 + 定 baseline，真正的 Decimal 化改造是另一个 spec）
- 不改 DB schema / migration / router 路径

## 立项注意

本文档所有行数为 2026-05-30 实测值。依"实测有效期=单次 grep 时刻"铁律，**实施时需按当时分支重测真实行数**再定白名单基线。
