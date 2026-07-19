# 迁移报告 — workpaper-maintainability-convergence-followup

> 生成时间：2026-07-14
> 承接 spec：`workpaper-maintainability-convergence`（37/37 tasks 已完成）

---

## 1. Legacy Provider 删除

| 指标 | 数值 |
|------|------|
| Total files scanned（主入口） | 184 |
| Eligible（含 `inject(WorkpaperRuntimeContextKey)`） | 56 |
| Not eligible（无 Runtime Boundary，L/M/N/A/B/C/S 循环） | 128 |
| Files actually modified | 1（`GtH10AssetDisposalIncome.vue` — 移除 `useWorkpaperReviewProvide`） |
| Files already clean | 55 |

**说明：** 56 个 eligible 文件中，55 个在先前 spec 执行期间已完成 Legacy Provider 清理，仅 GtH10 残留一处 `useWorkpaperReviewProvide` 调用需本轮物理删除。128 个 not eligible 文件因不注入 `WorkpaperRuntimeContextKey`（尚未接入 Runtime Boundary），按规则跳过。

---

## 2. FormData 工厂迁移

| 指标 | 数值 |
|------|------|
| Total composable files scanned | 114 |
| Migrated to `createChecklistFormData` | **66** |
| Already migrated（prior work） | 1（`useK5FormData`） |
| Skipped（non-homogeneous complex，在 SKIP_LIST） | 38 |
| Not in migration map | remaining |

### 按循环分布

| 循环 | 迁移数 |
|------|--------|
| K | 12 |
| M | 10 |
| H | 10 |
| I | 6 |
| G | 16 |
| N | 5 |
| L | 7 |
| **合计** | **66** |

**说明：** 66 个同构 FormData composable 已替换为 `createChecklistFormData` 工厂调用，参数化 `itemPrefix`/`label`/`forceComponentType`/`accountCodes`，消除重复的网络 I/O、debounce、hydrate 代码。38 个 SKIP_LIST 文件因存在非同构复杂逻辑（自定义 htmlData 处理、特殊 normalizeResponse 等）不适用工厂模式。

---

## 3. Coverage Ledger 变化

| 指标 | Before | After |
|------|--------|-------|
| Ledger entries | 120 | 128（+J1/J2/J3/K14/K15/K16/K17/K18） |
| Unknown capability slots | 578（baseline） | Higher（因 scope 扩展至 128 entries × 8 capabilities） |
| Runtime Boundary auto-marking | — | 5 capabilities × 56 eligible entries correctly marked as covered |
| Structural drift | 52 | 52（codes without `Gt*.vue` entry files，pre-existing condition） |

### 新增 entries 明细

- J1、J2、J3（应付职工薪酬三循环）
- K14、K15、K16、K17、K18（K 循环扩展编码）

### Auto-marking 逻辑

当主入口文件包含 `inject(WorkpaperRuntimeContextKey)` 时，`generate_coverage_ledger.py` 自动将以下 5 项能力标记为 `covered`（含 source evidence）：

1. `displayPrefs`
2. `agingConfig`
3. `version`
4. `review`
5. `ai`

共 56 个 eligible entries × 5 capabilities = **280 个 capability slots** 从 `unknown` 升级为 `covered`。

---

## 4. Homogeneous FormData Guard

| 指标 | Before | After |
|------|--------|-------|
| Violations | ~94（all self-built FormData composables） | **0**（eligible migrated files） |
| CI guard mode | report（不阻断） | **strict**（exit 1 on new violations） |
| Governance CI config | — | `governance-checks.yml` updated |

**说明：** 迁移完成后，`check_homogeneous_formdata.py` 切换至 strict 模式。剩余 SKIP_LIST 文件已登记于 `MIGRATED_ALLOWLIST`，不计入违规。任何新增的同构 FormData composable 将触发 CI 失败（exit 1），防止回归。

---

## 5. Requirements 满足情况

| Requirement | 描述 | 状态 | 证据 |
|-------------|------|------|------|
| Req 8.1 | Legacy Provider call sites removed | ✅ | 1 file modified（GtH10AssetDisposalIncome.vue） |
| Req 8.2 | FormData composables migrated to factory calls | ✅ | 66 files migrated |
| Req 8.3 | Ledger before/after documented | ✅ | §3 Coverage Ledger 变化 |
| Req 8.4 | Guard violation before/after documented | ✅ | §4 Homogeneous FormData Guard |

---

## 6. 总结

本轮 follow-up 工作聚焦四类技术债收尾：

1. **Ledger 漂移修复** — 补齐 8 个遗漏 wp_code entries，消除 CI drift 盲区
2. **Unknown→Covered 自动标记** — Runtime Boundary 注入检测驱动 280 capability slots 升级
3. **Legacy Provider 物理删除** — 仅 1 处残留调用需修改，其余已在先前 spec 清理
4. **FormData 工厂实迁** — 66 个同构 composable 统一为 `createChecklistFormData`，CI strict 守卫就位

遗留项（非本 spec 范围）：
- 128 个 not eligible 文件待后续 Runtime Boundary 接入后再处理
- 38 个 SKIP_LIST 复杂 composable 需逐个评估是否适配工厂模式
- Structural drift 52 条为 pre-existing（无对应 `Gt*.vue` 入口文件的编码），需架构层面决策
