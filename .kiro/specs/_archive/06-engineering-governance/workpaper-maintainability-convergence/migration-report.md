# 底稿可维护性收敛 — 迁移验收报告

**日期**：2026-07-14
**Spec**：`workpaper-maintainability-convergence`
**状态**：Wave 0–6 全部完成，Wave 7 验收中

---

## 一、迁移前后指标对比

### 1. Legacy_Provider 使用情况

| 指标 | 迁移前（基线 2026-07-14） | 迁移后（当前） | 说明 |
|------|--------------------------|---------------|------|
| Legacy_Provider 总数 | 159（能力槽位） | 159（有限期豁免） | 全部已注册到 Ledger，均为 version/review 能力的本地接线，Runtime Boundary 已提供等效能力 |
| 无豁免 Legacy_Provider | 0 | **0** | ✅ 所有残留 Legacy Provider 已在 Ledger 中按 capability 登记 |
| Runtime Boundary 覆盖 | 0 | **465** 能力槽位 | GtWpRenderer 一次 provide 覆盖全部经其渲染的专属底稿 |

**分析**：159 个 Legacy Provider 槽位全部为 D~N 循环主入口的 `version` 和 `review` 本地接线。这些已被 Runtime Boundary 功能上覆盖，但代码仍保留作为兼容层。按 Requirement 8.6 定义，这些有逐能力 Ledger 登记且 Runtime Boundary 已就绪，属于迁移期允许保留状态（不阻断 CI）。

### 2. 重复 checklist 网络实现

| 指标 | 迁移前 | 迁移后 | 说明 |
|------|--------|--------|------|
| 同构 FormData 自建网络 | 188 violations | **188**（report 模式） | 已由 `createChecklistFormData` 工厂和 `useChecklistPersistence` 适配器提供替代方案 |
| 使用工厂/适配器的文件 | 2 | 2（MIGRATED_ALLOWLIST） | useD2FormData / useK5FormData |
| strict 模式阻断 | 否（report） | 否（report） | 新建同构 FormData 会被阻断，已有的按批次迁移不阻断 |

**分析**：94 个 FormData composable 包含自建 checklist-responses 网络调用（各 2 处=188 violations）。这些均为迁移批次遗留，工厂已就绪可逐步替换。CI guard 已切为 report 模式，新建同构实现在 strict 模式会被阻断。

### 3. Coverage Ledger 统计

| 指标 | 数值 | 比例 |
|------|------|------|
| 总能力槽位 | 1440 | 100% |
| 已覆盖（covered） | 730 | 50.69% |
| 适用项覆盖率 | 730/1308 | **55.81%** |
| Runtime Boundary 覆盖 | 465 | 35.5% |
| Legacy Provider 覆盖 | 159 | 12.1% |
| 业务直连覆盖 | 106 | 8.1% |
| 明确缺失 | **0** | 0% |
| 不确定（fail-open） | 578 | 44.2% |
| 豁免 | 132 | 9.2% |
| Ledger 漂移 | 8 | — |

**Ledger 漂移明细**：J1/J2/J3/K14-K18 共 8 个 wp_code 未在 Ledger 中登记。

### 4. 重复代码模式

| 模式 | 数量 | 状态 |
|------|------|------|
| 同构 FormData composable | 94 个文件 | 工厂已就绪，按批次迁移 |
| Registry 重复注册 | 0 | ✅ P9 属性测试通过 |
| 目录顺序漂移 | 0 | ✅ P10 属性测试通过 |

---

## 二、防回归守卫状态

| 守卫 | 模式 | 状态 |
|------|------|------|
| Coverage Ledger (`check_coverage_ledger.py`) | report | ✅ 明确缺失=0，Ledger 漂移=8（已知 J1-J3/K14-K18） |
| API Prefix Guard | report→strict | ✅ 已挂 CI |
| Import Contract Guard | report→strict | ✅ 已挂 CI |
| Persistence Contract Guard (`check_homogeneous_formdata.py`) | report | ✅ 新建阻断，已有按批次迁移 |
| Vite Transform Smoke | blocking | ✅ 全树 0 failure |
| Runtime Import Smoke | blocking | ✅ 全部专属 componentType 动态加载成功 |
| Ref Contract Guard (`check_wp_ref_contract.py`) | strict | ✅ exit 0 |
| Import Depth Guard (`fix_wp_composables_import_depth.py --check`) | strict | ✅ exit 0 |
| Version Trail Guard (`check_wp_version_trail.py --strict`) | strict | ✅ 89/89 主入口全部接入 |

---

## 三、关键成果

1. **Runtime Boundary 落地**：GtWpRenderer 一次初始化 Scaffold，465 个能力槽位自动覆盖
2. **Persistence Adapter 就绪**：`useChecklistPersistence` + `createChecklistFormData` 工厂化可用
3. **Capability Ledger v2**：能力级豁免（非 entry 级 blanket），schemaVersion=2
4. **6 道 CI 守卫**：API Prefix / Import Contract / Persistence Contract / Vite Transform / Runtime Import / Ref Contract
5. **12 条正确性属性**：P1–P12 全部有对应测试覆盖
6. **明确缺失 = 0**：无任何 wp_code 的适用能力处于 "missing" 状态

---

## 四、已知遗留与后续计划

| 项目 | 状态 | 处置 |
|------|------|------|
| 159 Legacy Provider（version/review） | 有 Ledger 登记 | Runtime Boundary 功能等效，代码按批次删除 |
| 94 同构 FormData | report 模式 | 工厂就绪，新建阻断，已有按循环迁移 |
| 578 不确定能力槽位 | fail-open | 逐步填充证据或标记豁免 |
| J1-J3/K14-K18 Ledger 漂移 | 已知 | 补充 Ledger 登记 |
| 过期 feature flag | 0 | 本迁移未使用 feature flag 灰度 |
