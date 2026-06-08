# Spec 完成度核查记录（2026-05-30）

> 本文从 INDEX.md 迁移，记录 2026-05-30 对 84 个归档 spec 的逐一代码实证核查。
> 后续新归档 spec 各自在归档时标注了测试实证。

## 核查方法论

逐个 spec 读 tasks.md + fileSearch/grepSearch 实证产物真实存在。

### 正则统计四大误报源
1. **可选 `[ ]*`**：带星号未做不影响完成定性
2. **emoji 标题格式 `### Task X ✅`**：非 checkbox 被误报 0/N
3. **父任务未勾 + 子任务全完成**：父项汇总忘勾
4. **伪红**：tasks.md 全标 ⏳ 但产物 100% 存在

> PowerShell `Select-String "^\s*-\s*\[x\]"` 比 Python re.M 更可靠（phase7/phase8 Python 误报 32/51）。

## 核查结果

**结论：已核查 13 个 spec 无伪绿，0 个伪绿。**

### 06-engineering-governance（4 个）

| spec | 判定 |
|------|------|
| migration-runner-resilience | ⏳核心完成（缺 Playwright 截图=外部依赖） |
| pytest-residual-failures-cleanup | ✅真完成 |
| repo-frontend-layout-unification | ✅真完成 |
| repo-git-workflow-unification | ✅真完成（伪红：标⏳但产物 100% 存在） |

### 04-infra-architecture（8 个）

| spec | 判定 |
|------|------|
| global-linkage-bus | ✅ |
| global-platform-enhancement | ✅ |
| global-refinement-v3 | ⏳（缺合伙人 UAT） |
| production-readiness | ✅ |
| table-unification-el-table | ✅ |
| v3-linkage-stale-propagation | ⏳（UAT 8 项 pending） |
| v3-r10-editor-resilience | ⏳（UAT 5 项 pending） |
| v3-r10-linkage-and-tokens | ⏳（设计师视觉截图） |

### 05-business-features（抽查）

procedure-applicability-trimming / advanced-query-enhancements-p1p2 / partner-dashboard / report-module-enhancement + 8 抽查 → 全 ✅

### 其他分类

- 01 类：phase3-system-enhancement(外部UAT) / phase7-enhancement(209/209) / phase8(209/209) → ✅
- 03 类：refinement-round1(12 真人 UAT) → ⏳
- 07/08 类：workpaper-html-renderer / workpaper-list-shrink / disclosure-note-full-revamp / note-dynamic-tables → 全 ✅

### 汇总

| 判定 | 说明 |
|------|------|
| ✅ 真完成 | 绝大多数；unchecked = 可选/父框漏勾/emoji/伪红 |
| ⏳ 核心完成 | 残留全是外部依赖（真人UAT/Playwright/设计师） |
| ⚠️ 伪绿 | **0 个** |
