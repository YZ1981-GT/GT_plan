# 公式管理模块新功能 vs S 类底稿 spec 精确对照分析

> 只读调查，2026-10-25 生成。所有结论基于代码现读。

## 总结

**S 类 spec 三件套整体设计仍然成立**，公式管理模块的新功能未构成颠覆性冲突。但存在 **6 处需要修订/补充** 的地方（详见第 10 节），其中最重要的是：

1. `formula_settings` 的 `wp` 域已经覆盖底稿公式的全局/项目层有效定义管理，S34 前端公式引擎（`useS34FormulaEngine.ts`）需要明确与之的关系——**前端引擎是计算层，后端治理是定义层，两层正交**，但 spec 应显式声明这一边界。
2. `formula_push_rules.json` **0 条 S 规则**，这是预期结果（S 类底稿不参与公式推送），但 spec 应显式声明。
3. `match_workpapers` 和 `chain_orchestrator` **仍未实现 `applicable_when`**，spec P0 计划的改动完全未被其他 spec 抢先。

---

## 逐条证据

### Q1: resolver 签名——formula-fetch-followup 是否改了基础签名/注册方式/调用协议？

**结论：未改。签名完全兼容，spec 计划的 3 个新 resolver 可直接接入。**

**证据：**

1. `backend/app/services/auto_data_resolvers/__init__.py` 第 34 行：
   ```python
   # resolver 签名: async (db, project_id, year, **kwargs) -> dict[str, Any]
   ResolverFn = Callable[..., Awaitable[dict[str, Any]]]
   ```
   签名定义未变。

2. 注册装饰器 `@auto_resolver("name")` 机制完全保持原样（`_REGISTRY` dict + `resolve_auto_data_source` 调度器）。

3. 调度器增加了可观测性（`_RESOLVER_FAILURE_COUNTS` 失败计数器 + `get_resolver_failure_counts()`），但不影响 resolver 实现方。

4. `_s_transaction.py` 中现有 6 个 S resolver 仍然用 `async (db, project_id, year, **kw)` 签名。

5. `__init__.py` 末尾的子模块导入列表新增了多个循环的 resolver 模块（`_h1_fixed_assets`、`_h2_construction_in_progress`、`_h3_investment_property`、`_f5_cost_of_sales` 等），但注册机制不变。

6. formula-fetch-followup 的 R7a（取数严格化）改的是 `formula_ref_preload` 模块——严格取数路径（PREV/AUX/ROW/NOTE 等），与 resolver 调度器是完全独立的两个系统。

**对 spec 的影响：Task 21 新建 `_s_linkage.py` 的计划不需要修改，直接按 `@auto_resolver("name")` 模式注册即可。**

---

### Q2: S34 公式引擎——formula-global-settings-sync 引入的"公式全局设置/项目适配"影响 S34 吗？

**结论：不影响。两者是正交的两层：前端引擎是运行时计算层，后端治理是定义管理层。但 spec 应显式声明边界。**

**证据：**

1. **后端 `formula_settings/` 是什么**（`definitions.py` 第 1-97 行）：
   - 管理 7 个域的公式**定义**（report/tb_detail/cross_check/wp/note/consol_note/push）
   - 三层有效定义优先级：本项目适配 → 订阅模板 → 全局 → 系统预设
   - 其中 `wp` 域（`DomainSpec("wp", "底稿公式", ("expression", "formula_type"), ...)`）管理底稿公式的**声明式定义**

2. **`wp_effective.py`（底稿域有效公式接入预填）**：
   - 预填路径是 `effective_slots → 映射单元格换成有效公式`
   - 处理的是 xlsx 内置公式的覆盖/补充（A1 坐标定位）
   - 说明了局限：`公式运行时（formula_runtime）与各循环 Tier A 预设只读 wp_formula 行，不读全局层`

3. **前端 `useS34FormulaEngine.ts` 是什么**：
   - 纯函数 composable，**无副作用**
   - 硬编码公式定义（如 `S34_16_1_FORMULAS`、工厂函数 `createRatioFormula` 等）
   - 提供运行时计算：`computeFormulas(data, formulaDefs) → FormulaResult`
   - 已接入 ACNR：`getS34FormulaDescriptors(sheetCode)` 生成 addr_id 供公式管理弹窗展示

4. **两者关系**：
   - 后端 `formula_settings` 管理的是「这个公式位的公式文本是什么」（声明式）
   - 前端引擎是「给定数据网格，按公式计算值」（运行时）
   - S34 公式引擎的公式定义是**硬编码在前端的**，不走后端 `formula_settings` 的全局/项目层治理链
   - 已接入 ACNR 描述元数据（`S34FormulaCellDescriptor`），但**计算逻辑独立**

5. **`push_settings.py`** 已将推送规则纳入公式治理内核（`push` 域），但 S 类底稿在 `formula_push_rules.json` 中有 0 条规则（见 Q9），不受影响。

**对 spec 的影响**：
- spec §2.3（Task 25-28）计划补齐 12 张子表公式定义是**前端纯函数层**的工作，与后端公式治理无交集
- **建议在 design.md §2.3 显式声明**："S34 前端公式引擎是运行时计算层，与 `formula_settings` 的公式定义管理层正交。S34 子表公式不纳入后端治理（无按项目覆盖需求），但已通过 `getS34FormulaDescriptors` 在公式管理弹窗展示元数据。"

---

### Q3: 地址库扩到 50000 条——是否有新端点替代 `cycle_audited_amounts`？

**结论：没有替代。`cycle_audited_amounts` resolver 仍是 S32~S35 跨引用展示的最佳数据源，地址库扩容只是前端可查询容量增大。**

**证据：**

1. `formula_catalog.py` 路由（`GET /api/projects/{project_id}/formula-catalog`）是**公式目录的只读视图**，返回各域的 `CatalogEntry`（addr_id/domain/formula_text/layer/function_refs），不提供审定额数据。

2. `formula_catalog.py` 的 `check-rules` 端点是校对规则目录，与审定额无关。

3. `cycle_audited_amounts` resolver（`_cycle.py` 第 286-321 行）仍然存在且功能完好：按 standard_account_code 首位分类，返回 asset_total/liability_total/equity_total/revenue_total/expense_total，正是 S32~S35 跨引用需要的数据。

4. formula-fetch-followup 的地址库改动（R4）是把前端 `address_registry` store 从 5000 条扩到 50000 条（`/api/address-registry` 端点增大分页），以及增加鉴权（R4.1）。这是**可查询坐标数量**的扩容，不是新增取数能力。

5. `formula_ref_preload` 模块提供的 `load_note_values`/`load_report_rows` 等函数是严格代入取数（给公式求值引擎用），不是给前端 chip hover 展示用。

**对 spec 的影响：Task 29-30（`useS34CrossRef.ts` / `useS35CrossRef.ts` chip hover 展示审定额）计划调用 `cycle_audited_amounts` resolver 不需要修改。**

---

### Q4: linked_workpapers——formula-governance-coverage-closure 改了 wp_account_mapping.json 的 S 条目吗？

**结论：未改。92 个 S 条目的 `linked_workpapers` 全部为 `None`。**

**证据（probe 脚本输出）：**

```
=== wp_account_mapping.json S entries ===
Total S entries: 92
  S1: trigger=?, applicable_when=None, linked_workpapers=None
  S2: trigger=?, applicable_when=None, linked_workpapers=None
  ...
  S20: trigger=?, applicable_when=None, linked_workpapers=None
  S32-1: trigger=?, applicable_when={'business_category': ['ipo', 'listed', 'neeq']}, linked_workpapers=None
  ...（全部 92 条 linked_workpapers=None）
```

formula-fetch-followup 的 R1（映射表）改了 M/J/L/K4/D5/H6~H9/I/F2/E0/G 等循环的映射码和科目码，**未触碰 S 条目**。R1.4 清理了 `J2/K1/K2/K4/K5/L3/L6/L7` 的错码残留，与 S 无关。

**对 spec 的影响：Task 20 为 S20/S15/S17/S6/S33-5 补 `linked_workpapers` 的计划完全有效。**

---

### Q5: ipoProjectUtils 收敛——formula-fetch-followup 是否动了 D4/F2 的 IPO 判定？

**结论：未动。D4 和 F2 各自的 IPO 判定仍分别存在，与 spec P0 规划的收敛不冲突。**

**证据：**

1. **`useD4FormulaEngine.ts`**（第 274 行）：`isIpoGroupVisible` 函数仍然存在，使用 `IPO_KEYWORDS.some(keyword => lower.includes(keyword))` 模式

2. **`useF2SpecialFormData.ts`**（第 22 行）：`IPO_CATEGORIES = ['IPO', '上市公司年审', '新三板', '重大资产重组']` 仍以中文字面量数组存在，且使用三级瀑布判定（project_type → template_type → IPO_CATEGORIES.includes）

3. **后端 `_f2_inventory_special.py`**（第 21 行）：`IPO_CATEGORIES = {"IPO", "上市公司年审", "新三板", "重大资产重组"}` 也独立存在

4. formula-fetch-followup R1.4（M 循环科目码清理）和 R3.3（4xxx 写死码统一）**只处理科目码**，不涉及 IPO/business_category 判定逻辑。

5. **三处 IPO 判定**仍各自独立：
   - D4: `isIpoGroupVisible`（关键词含 `ipo/listed/neeq/restructuring/fraud_risk`）
   - F2 前端: `isIpoProject` computed（三级：project_type → template_type → 中文 IPO_CATEGORIES）
   - F2 后端: `IPO_CATEGORIES` set 判定

**对 spec 的影响：spec §1.4 计划新建 `ipoProjectUtils.ts` + 收敛三处 IPO 判定的方案完全有效。注意 D4 的 `fraud_risk` 关键词在收敛时需保留（design 已规划 `allowedCats` 参数）。**

---

### Q6: applicable_when 执行链——formula-governance-coverage-closure 是否加了支持？

**结论：未加。`match_workpapers` 和 `chain_orchestrator` 中的 `applicable_when` 支持仍为零。**

**证据：**

1. **`wp_generation_matching.py`**（完整文件，86 行）：
   只有三条路径：
   - `account_codes` 匹配（第 67-68 行）
   - `trigger == "must_have"`（第 69 行）
   - `trigger == "conditional" + applies_when`（第 70-71 行）
   
   **无 `applicable_when` 分支**。spec §0 G3 的诊断（"match_workpapers 不识别此字段"）在当前代码中**仍然成立**。

2. **`chain_orchestrator.py`**（第 468-547 行）：
   - `project_flags` 构建只包含：`consolidated`/`listed`/`listed_or_ipo`/`scenario_*`/`has_foreign_currency`/`integrated_audit`/各种 `has_*`/TB 科目开关
   - **没有 `biz_ipo`/`biz_listed`/`biz_neeq`/`biz_refinancing` flag**
   - **没有 SELECT `Project.business_category`**
   - formula-fetch-followup 改的是 `TB_ACCOUNT_FLAGS`（第 25-37 行的 `has_lease`/`has_rd` 改正），不涉及 applicable_when

3. formula-governance-coverage-closure 的 R1~R7a（鉴权/推送/校对/零挂载/底稿公式/全局设置/取数严格化）**全部在公式治理层面**，没有触碰底稿生成链。

**对 spec 的影响：Task 1-3（match_workpapers + chain_orchestrator + 端到端验证）是 P0 的核心改动，完全未被其他 spec 抢先，需要完整实施。**

---

### Q7: formula-manager-closure spec 是否存在？是否与 S 类 spec 有重叠？

**结论：`.kiro/specs/` 下不存在 `formula-manager-closure` 目录。唯一与公式管理相关的活跃 spec 是 `formula-fetch-followup-defect-closure`（30/34，部分未完成）。**

**证据：**

probe 脚本扫描 `.kiro/specs/` 所有含 "formula" 的目录：
```
=== formula-related specs ===
  formula-fetch-followup-defect-closure: tasks.md=YES
```

只有一个。而 `formula-governance-coverage-closure`（36/36 ✅）和 `formula-global-settings-sync`（35/36）都已归档到 `_archive/`。

`formula-fetch-followup-defect-closure` 的 tasks.md 剩余未完成项：
- 3.6：附注模板绑定按新映射重生成——待拍板
- 4.2：后端门禁——待并发 spec 入库
- 4.3：模板清单端点权限——同上
- 4.5：鉴权基线下调——待 4.2 后

**这些未完成项与 S 类 spec 无重叠**（S 类 spec 不涉及附注模板绑定、后端门禁或鉴权基线）。

---

### Q8: isNotApplicable 现状——formula-fetch-followup 是否改了 useAProgramData.ts？

**结论：未改。`isNotApplicable` 仍然只处理字符串 `"consolidated"` 一种情况。**

**证据（`useAProgramData.ts` 全文，50 行）：**

```typescript
const applicableWhen = ref<string | null>(null)

const isNotApplicable = computed<boolean>(() => {
    if (!applicableWhen.value) return false
    if (applicableWhen.value === 'consolidated' && projectStore.auditScope !== 'consolidated') {
      return true
    }
    return false
})
```

- `applicableWhen` 类型是 `string | null`，**不支持 dict 类型**
- 只判断 `'consolidated'`，**不判断 business_category dict**
- 没有调用 `isIpoProject` 或类似函数
- `loadProjectInfo` 从 `/api/projects/{projectId}` 取数据后没有解析 `applicable_when`（因为 render-config 端点还没附加这个字段）

**对 spec 的影响：Task 5（useAProgramData.ts 增加 dict 分支调用 isIpoProject）和 Task 6-7（后端 wp_render_config 附加 applicable_when + GtWpRenderer 层拦截）的计划完全有效。这是 P0 的关键改动。**

---

### Q9: formula_push_rules.json 变化——S 类相关规则是否受影响？

**结论：S 类在 formula_push_rules.json 中有 0 条规则，且从未有过。S 类底稿不参与公式推送链。**

**证据：**

probe 脚本输出：
```
=== formula_push_rules.json ===
Total rules: 375
S-related rules: 0
```

这是预期的：
- 公式推送链（`formula_push.engine.run`）是 `TRIAL_BALANCE_UPDATED` → 推送到底稿/附注。S 类底稿是**专项审计程序底稿**，它们的数据来自 TB 的 resolver 取数（`resolve_auto_data_source`），不需要被"推送"。
- 推送覆盖的是 D~N 循环的明细底稿/审定表/披露表/附注（当前 375 条规则 = 80 个 wp_code 的科目推送 + 附注种子推送）。
- formula-governance-coverage-closure R2 把 375 条推送规则纳入公式治理内核（`push` 域），只允许改写公式表达式和启停——对 S 无影响。

**对 spec 的影响：无。但建议在 spec 的 design.md 中添加一句声明："S 类底稿不参与公式推送（`formula_push_rules.json` 0 条 S 规则），审定额取数通过 resolver 完成。"**

---

### Q10: spec 三件套需要哪些修订？

#### 10.1 不需要修改的部分（核心设计仍成立）

| 模块 | 原因 |
|------|------|
| P0 Task 1-3：match_workpapers + chain_orchestrator 的 applicable_when | 完全未被其他 spec 实现 |
| P0 Task 4：ipoProjectUtils.ts 收敛 | 三处 IPO 判定仍分散，收敛有效 |
| P0 Task 5-7：前端 applicable_when 全路径 | useAProgramData 未变、render-config 未附加 applicable_when |
| P0 Task 10-16：s-checklist 孤儿接线 | 12 个组件仍是孤儿死代码 |
| P0 Task 17-19：resolveProcedureSheetKey S 段 | 仍无 S 段路由 |
| P1 Task 20：linked_workpapers | 92 个 S 条目全部 linked_workpapers=None |
| P1 Task 21：3 个新 resolver | 签名协议不变，可直接实现 |
| P1 Task 24-28：S34 公式引擎 12 张子表补齐 | 前端纯函数计算层，不受后端治理影响 |
| P1 Task 29-30：跨引用 chip 展示 | `cycle_audited_amounts` resolver 仍存在且可用 |
| P2 Task 31-35：风险映射 + 委派 | 与公式管理无交集 |

#### 10.2 建议修订的 6 处

**修订 1：design.md §2.3 补充 S34 公式引擎与后端公式治理的边界声明**

> 当前表述只说"补齐全部 12 张 hasSubTable 子表"，未提及与 `formula_settings` 的关系。

建议在 §2.3 开头追加：

> "S34 前端公式引擎（`useS34FormulaEngine.ts`）是运行时计算层，与 `formula_settings`（后端公式定义管理层）正交。S34 子表公式不纳入后端六域治理链（无按项目覆盖需求，硬编码即可），但已通过 `getS34FormulaDescriptors` 在公式管理弹窗展示元数据（addr_id/expression），与 Task 13.2 试点接入一致。如未来有项目级覆盖 S34 公式的需求，再将 S34 子表公式定义迁入 `wp` 域。"

**修订 2：design.md 新增 §2.5 声明 S 类不参与公式推送**

> 当前 spec 完全未提及公式推送。应显式声明：

> "§2.5 S 类底稿与公式推送的关系
> S 类底稿不参与 `formula_push` 推送链（`formula_push_rules.json` 中 S 相关规则 = 0 条）。
> S 类审定额取数通过 `auto_data_resolvers` 的 resolver 完成（已有 S4~S10 六个 + `cycle_audited_amounts` 一个 = 7 个 resolver，本 spec 新增 3 个 = 10 个）。
> 推送治理内核（formula-governance-coverage-closure R2）对 S 类无影响。"

**修订 3：Task 22 措辞更新——"验证既有 11 个 S resolver"应改为实际数**

> design §0 G7 记"已注册 **11** 个 S 相关 resolver"，但 probe 扫描 `_s_transaction.py` 只有 6 个（s4/s5/s6/s8/s9/s10），加上 `_tax_income.py` 4 个和 `_cycle.py` 1 个（`cycle_audited_amounts`）= 11 个。这个计数本身没错。

但 formula-fetch-followup 新增了多个循环的 resolver 模块（`_h1_fixed_assets`、`_h2_construction_in_progress` 等），`__init__.py` 末尾导入列表从 ~15 增长到 22 个模块。**总已注册 resolver 数量已大幅增加**。Task 22 的"验证既有 11 个 S resolver 签名一致性"仍然有效，但建议改措辞为：

> "验证既有 11 个 S 相关 resolver 签名与调度器 `resolve_auto_data_source` 的调用协议一致（签名 `async (db, project_id, year, **kwargs) -> dict[str, Any]`）。注意：总 resolver 数已从 spec 编写时的 ~35 个增长到 ~50+ 个，但注册机制和签名协议不变。"

**修订 4：Task 8 措辞补充——deleteisIpoGroupVisible 需确认测试依赖**

> design §1.4 计划 `useD4FormulaEngine.ts` 删 `isIpoGroupVisible`。但该函数现有大量测试依赖：
> - `useD4FormulaEngine.spec.ts`：`describe('isIpoGroupVisible', ...)` 有 8 个用例
> - `useD4FormulaEngine.pbt.spec.ts`：PBT 用例引用 `isIpoGroupVisible`
> - `useD4CrossSheet.ts`：`import { isIpoGroupVisible } from './useD4FormulaEngine'`

建议 Task 8 补充：

> "同步修改 `useD4FormulaEngine.spec.ts`/`.pbt.spec.ts` 中 `isIpoGroupVisible` 测试用例，改为测试 `isIpoProject(biz, [...IPO_BIZ_KEYWORDS, 'fraud_risk'])`；修改 `useD4CrossSheet.ts` 的 import。"

**修订 5：design §1.2 的 project_flags 补充——确认 `scenario` 字段存在**

> chain_orchestrator 第 468 行的 `project_flags` 已有 `scenario_ipo_or_above: scenario in ("ipo", "listed", "transfer", "restructure", "fraud_response")`。但 `applicable_when` 用的是 `business_category` 字段，而非 `scenario`。

> 现读确认：chain_orchestrator 第 452 行 SELECT 包含 `Project.template_type`（第 440 行 `Template.template_type`）。`Project.business_category` 在 ORM 中存在（`core.py:82`，`String(10)`），但 **chain_orchestrator 的 SELECT 不包含它**（project_flags 里的 listed/listed_or_ipo 等来自 template_type 和 scenario，不来自 business_category）。

> 这与 design §1.2 的计划完全一致（"SELECT 增加 `Project.business_category`"），**但建议在 Task 2 更新确认清单**：
> - 确认 chain_orchestrator 的 SELECT 查询当前从哪些表/列取数（现读确认是从 `Project` + `Template` + wizard_state）
> - 确认 `Project.business_category` 在 ORM 中的类型（`String(10)`）是否足够（IPO/listed/neeq/refinancing 最长 11 字符，`String(10)` 可能不够存 "refinancing"）

**修订 6：tasks.md 增加前置检查任务——确认并发 spec 的入库状态**

> formula-fetch-followup Task 4.2 说"后端门禁在并发 spec `procedure-trim-generation-delegation-chain` 的工作树改动里（未入库）"。该 spec（19/23）可能会先于 S 类 spec 入库，改动 `chain_orchestrator.py`。

建议在 tasks.md Phase 1 前加一个前置确认任务：

> "Task 0. 前置确认：`procedure-trim-generation-delegation-chain` spec 是否已入库。如已入库，检查 `chain_orchestrator.py` 的 SELECT 和 project_flags 是否有变化，对照 spec §1.2 调整 Task 2 的改动基线。"

---

## 附录：关键文件路径清册

| 文件 | 角色 |
|------|------|
| `backend/app/services/auto_data_resolvers/__init__.py` | resolver 注册机制与调度器 |
| `backend/app/services/auto_data_resolvers/_s_transaction.py` | S4~S10 六个 resolver |
| `backend/app/services/auto_data_resolvers/_cycle.py:286` | `cycle_audited_amounts` resolver |
| `backend/app/services/wp_generation_matching.py` | 底稿生成匹配（无 applicable_when） |
| `backend/app/services/chain_orchestrator.py:468` | project_flags 构建（无 biz_ flag） |
| `backend/app/services/formula_settings/` | 后端公式治理内核（31 个 .py 文件） |
| `backend/app/services/formula_settings/definitions.py` | 七域定义（report/tb_detail/cross_check/wp/note/consol_note/push） |
| `backend/app/services/formula_settings/wp_effective.py` | 底稿域有效公式预填 |
| `backend/app/services/formula_settings/push_settings.py` | 推送规则纳入治理 |
| `backend/app/routers/formula_settings.py` | 全局设置/项目适配路由 |
| `backend/app/routers/formula_catalog.py` | 公式目录 + 校对规则目录路由 |
| `backend/data/formula_push_rules.json` | 推送规则清单（375 条，S = 0 条） |
| `backend/data/wp_account_mapping.json` | 底稿科目映射（92 个 S 条目） |
| `audit-platform/frontend/src/composables/useAProgramData.ts` | 程序表适用性判定（未变） |
| `audit-platform/frontend/src/components/workpaper/s34-ipo-bundle/useS34FormulaEngine.ts` | S34 前端公式引擎 |
| `audit-platform/frontend/src/components/workpaper/composables/useD4FormulaEngine.ts:274` | `isIpoGroupVisible`（待收敛） |
| `audit-platform/frontend/src/components/workpaper/composables/useF2SpecialFormData.ts:22` | `IPO_CATEGORIES`（待收敛） |
| `backend/app/routers/wp_render_strategies/_f2_inventory_special.py:21` | 后端 `IPO_CATEGORIES`（待收敛） |
