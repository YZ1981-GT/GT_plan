# S 类底稿联动、裁剪与组件接线 — 设计

## §0 现状 grep 确认

**G1 — Task 21 产物是否存在**
归档 `_archive/10-A~S-workpaper-all-cycles-complete/s-cycle-workpapers/tasks.md` Task 21
标 `[x]`「实现 evaluateApplicability」。全仓 grep `evaluateApplicability` → 活动代码 0 命中。
`match_workpapers` 完整代码已读（85 行）：只有 `account_codes` / `trigger=must_have` /
`trigger=conditional + applies_when(str)` 三条路径，无 `applicable_when` 分支。
**结论：Task 21 假绿，产物从未实现。**

**G2 — resolveProcedureSheetKey.ts 接入模式**
位于 `src/utils/resolveProcedureSheetKey.ts`（107 行）。纯 if-chain 按
`wpCode.toUpperCase().startsWith(prefix)` 路由。有 D/E/F/G/H/I/J/K/L/M/N 段路由，**无 S 段**。
已有多位编号优先模式：G14/G13/G12/G11/G10 在 G1 之前、H10 在 H1 之前、M10 在 M1 之前、
K13/K12/K11/K10 在 K1 之前。H10/K10/K12/K13 显式 fallback → `'e1a'`。

**G3 — match_workpapers 中 applicable_when 与 applies_when**
已读 `wp_generation_matching.py` 全文。`applies_when` 是 str（如 `"has_lease"`），
`applicable_when` 是 dict（如 `{business_category: ["ipo","listed"]}`），**match_workpapers 不识别此字段**。
映射表中 `applicable_when` 使用两类键：`business_category`（S32~S35/D4-22/F2-61~72）和
`industry`（H5/H7/M8）。

**G4 — chain_orchestrator 的 SELECT**
不含 `Project.business_category`。但 `Project.business_category` 在 ORM 中存在（`core.py:82`，`String(10)`）。

**G5 — s-checklist 组件清册**
`s-checklist/index.ts` 导出 **12** 个组件（S1×1 + S8×1 + S9×4 + S10×3 + S17×3）。
全仓 grep 非测试、非 `components.d.ts` 的 import → 0 命中。**12 个均为孤儿死代码。**

子码在 overrides 分两组：
- **组 A（7 个在 overrides）**：S9-1/S9-2/S10-1/S10-2/S17-1/S17-2/S17-3，当前映射 `a-program-console`
- **组 B（5 个不在 overrides）**：S1-1/S8-1/S9-3/S9-4/S10-3（内部 sheet 非独立 wp_code）

⚠ S17-11/S17-21 在 overrides 中存在（映射 `a-program-console`），无对应 s-checklist 组件，保持不改。

**G6 — GtWpRenderer 架构与 applicable_when 数据来源**
`GtWpRenderer.vue` 按 per-sheet componentType 查 `HTML_RENDERER_REGISTRY` 分发。
14 个 S 类型已注册，**无 s1/s2/s8/s9/s10/s11/s16/s17**。
GtWpRenderer 内**无 applicable_when 逻辑**。S32~S35 走 bundle 组件不经 GtAProgramConsole，
故 `isNotApplicable` 对 bundle 不生效。→ 必须在 GtWpRenderer 层面新增拦截（§1.3.2）。

**关键：applicable_when 数据来源路径**（评审 MEDIUM-2 修正）
`applicable_when` 定义在 `wp_account_mapping.json`，**不在** `wp_code_overrides.json`。
`wp_render_config.py` 没有导入 `wp_account_mapping`（grep 零命中）。
`_WP_CODE_OVERRIDE` 在 `wp_classification_service.py` 中加载，来源是 `wp_code_overrides.json`。
→ 需在 `wp_classification_service.py` 新增 `_WP_APPLICABLE_WHEN` 字典（§1.3.2）。

**G7 — 既有 S resolver 计数**
已注册 **11** 个 S 相关 resolver：`_s_transaction.py` 6 个（s4~s10）+ `_tax_income.py` 4 个 +
`_cycle.py` 1 个。

**G8 — risk_assessments 字段**
`collaboration_models.py:66-70`：`account_or_cycle` String(100) / `is_significant_risk` Boolean /
`combined_risk` Enum(RiskLevel)。真库值域须实施时 SELECT DISTINCT 对照。

**G9 — wp_index.assigned_to FK**
`workpaper_models.py:227-229`：FK 指向 **users.id**。
正确 JOIN：`wp_index.assigned_to → users.id → staff_members.user_id → staff_members.name`。

**G10 — per-sheet override 机制**
`wp_render_config.py` 中（render-config 的 per-sheet 循环）：
`_WP_CODE_OVERRIDE.get(f"{wp_code}-{cls.sheet_name}")` 是第三级 fallback。
此机制已被 D0 函证 confirmation-* 精细组件使用。
→ 组 B 通过添加 `"{parent_wp_code}-{sheet_tab_name}"` 键来路由。

---

## §1 P0 裁剪执行链 + 孤儿接线

### §1.1 match_workpapers 增加 applicable_when 判定（R-P0-1，评审 MEDIUM-3 修复）

改动文件：`backend/app/services/wp_generation_matching.py`

追加第四条路径，**遍历 dict 全部键**（评审要求不只实现 business_category）：

```python
elif m.get("applicable_when"):
    aw = m["applicable_when"]
    # 各键之间 OR：business_category / industry 等，任一键命中即 hit
    _KEY_FLAG_PREFIX = {"business_category": "biz_", "industry": "ind_"}
    for key, values in aw.items():
        prefix = _KEY_FLAG_PREFIX.get(key, f"{key}_")
        if any(project_flags.get(f"{prefix}{v}") for v in values):
            hit = True
            break
```

影响面：`test_wp_account_mapping_single_source.py` 补 applicable_when 测试路径（hit + miss 各一例）。

### §1.2 chain_orchestrator 加载项目分类（R-P0-1）

改动文件：`backend/app/services/chain_orchestrator.py`

SELECT 增加 `Project.business_category`。构建布尔 flag：
```python
biz_cat = str(proj_row.business_category or "").lower()
project_flags.update({
    "biz_ipo": "ipo" in biz_cat,
    "biz_listed": "listed" in biz_cat or template_type == "listed",
    "biz_neeq": "neeq" in biz_cat,
    "biz_refinancing": "refinancing" in biz_cat,
})
```

`industry` 键的 flag 需从项目属性读取，`Project.industry` 字段实施时现读确认是否存在。
如不存在则本次 industry 键路径 **只声明框架**（for 循环可遍历到 `ind_` 前缀但 flag 恒为空），
不构成延迟风险（industry 条目通常先通过 `account_codes` 命中）。

### §1.3 前端 applicable_when 全路径覆盖（R-P0-2，评审 MEDIUM-2 修复）

#### §1.3.1 useAProgramData 扩展

改动文件：`audit-platform/frontend/src/composables/useAProgramData.ts`

`applicableWhen` ref 类型扩展为 `string | Record<string, string[]> | null`。
`isNotApplicable` computed 增加 dict 分支调用 `isIpoProject`（§1.4）。

#### §1.3.2 GtWpRenderer 层拦截 + applicable_when 数据加载

**后端数据来源**（MEDIUM-2 修正）：

在 `wp_classification_service.py` 新增 `_WP_APPLICABLE_WHEN` 字典，与 `_WP_CODE_OVERRIDE`
并列。从 `wp_account_mapping.json` 预加载 `wp_code → applicable_when` 映射（仅非 None 条目，
约 60 条）。热重载机制复用 `load_wp_code_overrides` 的 mtime 模式。

```python
# wp_classification_service.py 新增
_WP_APPLICABLE_WHEN: dict[str, dict] = _load_applicable_when()

def _load_applicable_when() -> dict[str, dict]:
    """从 wp_account_mapping.json 加载 wp_code → applicable_when 映射（非 None 条目）。
    🔴 bundle 父码聚合：S32/S33/S34/S35 父码自身 applicable_when=None，
    但全部子码有相同 business_category 限制——须从子码向上聚合。
    """
    import json, re
    from pathlib import Path
    from collections import defaultdict
    mapping_path = Path(__file__).parent.parent / "data" / "wp_account_mapping.json"
    raw = json.loads(mapping_path.read_bytes())
    data = raw["mappings"] if isinstance(raw, dict) else raw
    result = {}
    # 先加载所有非 None 条目
    for m in data:
        if m.get("applicable_when"):
            result[m["wp_code"]] = m["applicable_when"]
    # 聚合 bundle 父码：对 skip 子码按父前缀分组，取交集
    BUNDLE_PARENTS = {"S32", "S33", "S34", "S35"}
    for parent in BUNDLE_PARENTS:
        if parent in result:
            continue  # 父码已有声明则跳过
        children_aw = [m["applicable_when"] for m in data
                       if m.get("wp_code", "").startswith(parent + "-") and m.get("applicable_when")]
        if children_aw:
            # 取所有子码 business_category 的并集（宽松策略：任一子码适用即父码适用）
            all_cats = set()
            for aw in children_aw:
                all_cats.update(aw.get("business_category", []))
            if all_cats:
                result[parent] = {"business_category": sorted(all_cats)}
    return result
```

`wp_render_config.py` 的 render-config 端点从 `_WP_APPLICABLE_WHEN` 查 wp_code，
附加 `applicable_when` 字段到响应体。

**前端消费**：GtWpRenderer 新增 computed `isWpNotApplicable`：
- 从 render-config 响应取 `applicable_when`（dict 或 null）
- 比对项目 business_category，不匹配渲染覆盖层：
```html
<el-result v-if="isWpNotApplicable" icon="info" title="不适用">
  <template #sub-title>当前项目类型不适用此底稿</template>
</el-result>
```

影响面：`GtWpRenderer.spec.ts` 补 applicable_when 拦截测试。

### §1.4 收敛 IPO 可见性（R-P0-3）

新建：`audit-platform/frontend/src/utils/ipoProjectUtils.ts`

```typescript
export const IPO_BIZ_KEYWORDS = ['ipo', 'listed', 'neeq', 'restructuring', 'refinancing'] as const

export function isIpoProject(businessCategory: string, allowedCats?: string[]): boolean {
  const lower = businessCategory.toLowerCase()
  if (allowedCats?.length) return allowedCats.some(cat => lower.includes(cat.toLowerCase()))
  return IPO_BIZ_KEYWORDS.some(kw => lower.includes(kw))
}
```

**消费方迁移策略**（评审 MEDIUM-1 修复——方案 B：保持签名单参数，D4/F2 保留各自 wrapper）：
- `useAProgramData.ts` / GtWpRenderer：直接调 `isIpoProject(biz)`
- `useD4FormulaEngine.ts`：删 `isIpoGroupVisible`，但 D4 的 `allowedCats` 须含 `'fraud_risk'`
  以保持现有 fraud_risk 检测行为，即 `isIpoProject(biz, [...IPO_BIZ_KEYWORDS, 'fraud_risk'])`
- `useF2SpecialFormData.ts`：F2 的三级瀑布（project_type→template_type→中文 IPO_CATEGORIES）
  **保留为 wrapper 函数**（`isF2IpoProject(project)`），内部调 `isIpoProject` 作第一级判定，
  三级瀑布作 fallback——不可用单参数替代多字段逻辑
- 最终收敛到 `isIpoProject`(核心) + `isF2IpoProject`(F2 wrapper) ≤2 个来源

### §1.5 s-checklist 孤儿组件接线（R-P0-4）

**组 A — 7 个已在 overrides 的独立 wp_code**

改动：`wp_code_overrides.json` componentType 从 `a-program-console` 改专属类型。

| wp_code | 新 componentType | 对应组件 |
|---------|-----------------|---------|
| S9-1 | s9-adjudication | S9AdjudicationSheet |
| S9-2 | s9-internal-control | S9InternalControlSheet |
| S10-1 | s10-adjudication | S10AdjudicationSheet |
| S10-2 | s10-internal-control | S10InternalControlSheet |
| S17-1 | s17-nonrecurring-detail | S17NonRecurringDetailSheet |
| S17-2 | s17-reconciliation | S17ReconciliationSheet |
| S17-3 | s17-tax-impact | S17TaxImpactSheet |

⚠ S17-11、S17-21 在 overrides 中存在但无对应专属组件，保持 `a-program-console` 不改。

**组 B — 5 个内部 sheet**

在 `wp_code_overrides.json` 添加 sheet 级 override 键 `"{parent_wp_code}-{sheet_tab_name}"`。
5 个 sheet_tab_name 须实施时 openpyxl 读模板确认精确值。

改动 2 — `htmlRendererRegistry.ts` 追加 12 个类型字面量。
改动 3 — `registry/entries/specialized.ts` 追加 12 个 HtmlRendererEntry。
改动 4 — 验证 s-checklist 组件字段绑定与当前模板一致。

影响面：`htmlRendererRegistry.spec.ts` / `GtWpRenderer.real-registry.contract.test.ts` 需覆盖新类型。

### §1.6 S 段侧边栏路由（R-P0-5，评审 MEDIUM-1 修复）

改动文件：`src/utils/resolveProcedureSheetKey.ts`

在 K 段之后、F 段之前追加 S 段。遵循既有模式（长前缀先于短前缀），**S16/S11 显式 fallback
到 e1a 必须在 S15/S10 和 S1 之前**。

**路由判据**（评审 NIT-2 补充）：获得显式路由的底稿 = **有独立程序表 sheet 且有专属组件的**。
S12/S13/S14/S15/S20 有专属程序表子组件需定向分发；S1/S10/S17 通过 §1.5 孤儿接线后
同样需要路由到专属 sheetKey。S3/S4/S5/S6/S21 虽有专属顶层组件，但其程序表 sheet
由顶层组件内部管理（GtWpRenderer 直接分发到 s3-policy-change 等），不需要
resolveProcedureSheetKey 额外路由——此函数仅服务于程序表侧边栏数据源。

```typescript
// S 循环路由
if (upper.startsWith('S20')) return 's20a'  // S20 营业收入扣除
if (upper.startsWith('S17')) return 's17a'  // S17 非经常性损益
if (upper.startsWith('S16')) return 'e1a'   // S16 套期活动，无专属程序表 fallback
if (upper.startsWith('S15')) return 's15a'  // S15 每股收益/ROE
if (upper.startsWith('S14')) return 's14a'  // S14 会计估计
if (upper.startsWith('S13')) return 's13a'  // S13 利用管理层专家
if (upper.startsWith('S12')) return 's12a'  // S12 利用专家
if (upper.startsWith('S11')) return 'e1a'   // S11 利用服务机构，无专属程序表 fallback
if (upper.startsWith('S10')) return 's10a'  // S10 环境事项
if (upper.startsWith('S8')) return 's8a'    // S8 租赁（S8AdjudicationSheet 需侧边栏数据源）
if (upper.startsWith('S1')) return 's1a'    // S1 违反法规行为
// S2~S6/S9/S21 无专属程序表数据源，落默认 e1a
// S32~S35 bundle 有自己的导航机制，不进此路由
```

验证要点：S11 不被 `startsWith('S1')` 捕获；S16 不被 `startsWith('S1')` 捕获。

---

## §2 P1 关联联动

### §2.1 linked_workpapers 补齐（R-P1-1）

改动：`backend/app/data/wp_account_mapping.json`

| S wp_code | linked_workpapers | 关联逻辑 |
|-----------|------------------|---------|
| S20 | `["D4"]` | 营收审定数依赖 |
| S15 | `["D4", "M2"]` | 净利润/股本/净资产 |
| S17 | `["K12", "K13"]` | 非经常性损益 = 营业外收支 |
| S6 | `["K1"]` | 关联方资金占用指标 |
| S33-5 | `["D4", "F5"]` | 收入毛利交叉检查 |

**消费方路径**（实施时须 grep `linked_workpapers` 现读确认）：
D~N 循环的 linked_workpapers 由底稿面板的 `GtWpPreparationHeader` 或 `WorkpaperSidePanel`
的"关联底稿"区域消费（展示为可点击 chip）。S 类底稿需走同一展示路径。如果消费组件按
componentType 过滤只认 D~N，需扩展白名单。

### §2.2 补缺 resolver（R-P1-2）

新建：`backend/app/services/auto_data_resolvers/_s_linkage.py`

三个 resolver 签名统一 `async (db, project_id, year, **kw)`，**只读不回写 TB**。

- `s6_related_party_summary`：按标准码前缀 1221/1222/2202 查 tb_balance 关联方维度。
  与已有 `s6_fund_occupation_data`（查大额净占用）区别明确。
- `s33_5_revenue_cost_check`：读 D4 营收 + F5 成本审定数，算毛利率。
- `s14_estimate_related_data`：读减值准备(1231/1471/1811)/公允价值变动(6101) tb 审定额。

**render-schema 绑定**（实施时必做）：resolver 注册后，须在对应底稿的 render-schema YAML
（`backend/data/.../wp_render_schema/` 下搜 S6/S33-5/S14）中补 `auto_data_source` 声明绑定到
具体单元格。如果 S 类底稿走 `a-program-console` 通用渲染且无 render-schema，则需通过
程序表中控台的通用取数机制注入（与 S4~S10 已有 resolver 同一路径）。

### §2.3 S34 公式引擎完整化（R-P1-3）

改动：`s34-ipo-bundle/useS34FormulaEngine.ts`

**边界声明**：S34 前端公式引擎是**运行时计算层**，与 `formula_settings`（后端公式定义管理层
七域：report/tb_detail/cross_check/wp/note/consol_note/push）**正交**。S34 子表公式不纳入
后端六域治理链（无按项目覆盖需求，硬编码前端工厂函数即可），但已通过
`getS34FormulaDescriptors` 在公式管理弹窗展示元数据（addr_id/expression），与 Task 13.2
试点接入一致。如未来有项目级覆盖 S34 公式的需求，再将定义迁入 `wp` 域。

在 `S34_SHEET_FORMULA_DEFS` 中逐表补齐全部 12 张 hasSubTable 子表（每表具体公式列需实施时
openpyxl 读模板确认）。12 张 = S34-2/S34-3/S34-4/S34-8/S34-9/S34-11/S34-16/S34-18/S34-20/
S34-25/S34-30/S34-34（其中 S34-16 已有试点，只需验证）。
复用 `createRatioFormula` / `createSumFormula` / `createThresholdFormula` 工厂函数。

### §2.4 跨引用数值展示（R-P1-4）

改动：`useS34CrossRef.ts` / `useS35CrossRef.ts`

外部引用 chip 增加 hover 分支：调 `cycle_audited_amounts` 获取关联底稿审定额，
`el-popover` 只读展示。不回写，不修改目标底稿。

---

## §3 P2 风险导向 + 委派

### §3.1 风险映射查询（R-P2-1）

改动：`backend/app/services/s34_checklist_service.py`

新增 `_load_risk_indicators(db, project_id)`。`S_RISK_QUERY_MAP` 枚举值取自 B 循环
`useB50RiskData` 前端选项枚举（权威来源），**实施时须 `SELECT DISTINCT account_or_cycle
FROM risk_assessments LIMIT 50` 对照验证**。如真库值域不匹配据实调整。

### §3.2 清单适用性升级（R-P2-2）

四象限：风险指向+底稿存在 → applicable / 风险+无底稿 → recommended / 无风险+有底稿 →
applicable / 无风险+无底稿 → not_applicable。

### §3.3 委派展示（R-P2-3）

改动：4 个 bundle 组件。正确 JOIN 路径（G9 确认）：
`wp_index.assigned_to → users.id → staff_members.user_id → staff_members.name`。
无 staff_members 降级 `users.username`。仅 UI 展示不改 assignment_service 粒度。

---

## §4 不涉及数据库迁移

全部改动是代码层修改。P2 读现有 risk_assessments 表。

## §4.1 S 类与公式推送的关系

S 类底稿不参与 `formula_push` 推送链（`formula_push_rules.json` 中 S 相关规则 = 0 条）。
S 类审定额取数通过 `auto_data_resolvers` 的 resolver 完成（已有 S4~S10 六个 +
`cycle_audited_amounts` 一个 = 7 个 resolver，本 spec 新增 3 个 = 10 个）。
推送治理内核（formula-governance-coverage-closure R2）对 S 类无影响。

## §4.2 并发 spec 前置确认

`procedure-trim-generation-delegation-chain` spec（19/23）可能先于本 spec 入库并改动
`chain_orchestrator.py`。实施 Task 2 前须现读确认 chain_orchestrator 的 SELECT 和
project_flags 是否有变化,据实调整改动基线。
另：`Project.business_category` 为 `String(10)`（`core.py:82`），而 `"refinancing"` 为
11 字符——实施时须确认真库是否有长于 10 字符的值，如有则需迁移加宽此列。

## §5 评审意见回应

| 编号 | 处置 | 说明 |
|------|------|------|
| R4-MEDIUM-1 | **已修复** | §1.4 采用方案 B：保持单参数核心函数，D4 传 allowedCats 含 fraud_risk，F2 保留三级瀑布 wrapper |
| R4-NIT-1 | **已修复** | §2.3 + Tasks 25~27 补入 S34-3，12 张全部覆盖 |
| R4-NIT-2 | **已修复** | §1.6 添加路由判据说明：仅为有独立程序表 sheet 需定向分发的底稿分配专属 sheetKey |
| MEDIUM-1 | **已修复** | §1.6 在 S1 之前添加 S16→e1a 和 S11→e1a 的显式 fallback，遵循既有 H10/K12/K13 模式 |
| MEDIUM-2 | **已修复** | §1.3.2 改为在 `wp_classification_service.py` 新增 `_WP_APPLICABLE_WHEN`（从 `wp_account_mapping.json` 加载），纠正「从 _WP_CODE_OVERRIDE 查」的错误前提 |
| MEDIUM-3 | **已修复** | §1.1 改为遍历 dict 全部键（`_KEY_FLAG_PREFIX` 映射 business_category→biz_ / industry→ind_），不再只实现 business_category |
| NIT-1 | **已修复** | §0 G10 不再写死行号，改为描述机制位置 |
| NIT-2 | **已修复** | §1.5 组 A 表格下添加 S17-11/S17-21 保持不改的说明 |
