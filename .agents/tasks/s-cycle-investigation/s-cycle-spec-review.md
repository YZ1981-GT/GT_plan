# S 类底稿 spec 三件套设计评审（第二轮）

> 评审对象：`s-cycle-linkage-trimming-and-component-wiring` spec 三件套（修订版，回应首轮 MEDIUM-1~3 / NIT-1~2）
> 权威证据：`.agents/tasks/s-cycle-investigation/findings.md`
> 评审日期：基于当前 HEAD 快照源码验证

---

## 评审结论：CHANGES_REQUESTED

首轮 3 个 MEDIUM + 2 个 NIT 全部已修复。第二轮发现 1 个新 MEDIUM（IPO 关键词集合与消费方迁移歧义），需修复后方可进入实施。

---

## 首轮修复确认

| 编号 | 问题 | 修复状态 | 验证方式 |
|------|------|---------|---------|
| MEDIUM-1 | S11/S16 被 `startsWith('S1')` 误捕获 | ✅ 已修复 | §1.6 代码 S16→e1a / S11→e1a 在 S15/S10/S1 之前，顺序正确 |
| MEDIUM-2 | applicable_when 数据来源路径前提错误 | ✅ 已修复 | §1.3.2 改为 `wp_classification_service.py` 新增 `_WP_APPLICABLE_WHEN`（从 `wp_account_mapping.json` 加载），路径正确 |
| MEDIUM-3 | match_workpapers 只实现 business_category | ✅ 已修复 | §1.1 改为 `_KEY_FLAG_PREFIX` 映射全键遍历（business_category→biz_ / industry→ind_） |
| NIT-1 | 行号写死 | ✅ 已修复 | §0 G10 改为描述机制位置，不引用行号 |
| NIT-2 | S17-11/S17-21 未提及 | ✅ 已修复 | §1.5 组 A 表格下添加了保持不改的说明 |

---

## 已验证假设（Verified Assumptions）

以下设计声明均经源码对照确认正确：

| 编号 | 声明 | 验证方式 |
|------|------|---------|
| G1 | Task 21 假绿，`evaluateApplicability` 产物从未实现 | 全仓 grep `evaluateApplicability` → 活动代码 0 命中；完整读取 `wp_generation_matching.py`（85 行），只有 account_codes / must_have / conditional+applies_when 三条路径 |
| G2 | `resolveProcedureSheetKey.ts` 无 S 段路由 | 完整读取文件（107 行），确认只有 D/E/F/G/H/I/J/K/L/M/N 段路由 |
| G3 | `match_workpapers` 不识别 `applicable_when` dict | 同 G1，文件内 `applicable_when` 零出现 |
| G4 | `chain_orchestrator` SELECT 不含 `business_category` | grep `business_category` 在 `chain_orchestrator.py` 中零命中 |
| G5 | s-checklist 导出 **12** 个组件 | 读取 `s-checklist/index.ts`，逐行数：S1×1 + S8×1 + S9×4 + S10×3 + S17×3 = **12** |
| G6 | 14 个 S componentType 在 specialized.ts 注册 | 逐条确认：s3/s4/s5/s6/s12/s13/s14/s15/s20/s21/s32/s33/s34/s35 |
| G7 | 既有 S resolver 为 **11** 个 | `_s_transaction.py` 6 个（s4~s10）+ `_tax_income.py` 4 个（revenue_audited_for_s20 / eps_data_from_tb / s3_policy_change_data / non_recurring_items_from_tb）+ `_cycle.py` 1 个（cycle_audited_amounts）= **11** |
| G8 | `risk_assessments` 模型字段 | `collaboration_models.py:66-70` 逐字段确认 |
| G9 | `wp_index.assigned_to` FK → `users.id` | `workpaper_models.py:227-229` 确认 |
| G10 | per-sheet override 机制存在 | `wp_render_config.py` 确认 `_WP_CODE_OVERRIDE.get(f"{wp_code}-{cls.sheet_name}")` 三级 fallback |
| 新 V1 | §1.2 `Project.industry` 不存在 | `core.py` grep `industry` → 零命中。`Project.business_category` 确在 `core.py:82`。设计正确表述为"实施时现读确认"并给出不存在时的降级方案 |
| 新 V2 | §1.3.2 `wp_render_config.py` 不导入 `wp_account_mapping` | grep 确认零命中，`_WP_APPLICABLE_WHEN` 新增路径合理 |
| 新 V3 | §1.6 S11/S16 优先级正确 | S16(→e1a) 在 S15 之前，S11(→e1a) 在 S10 之前，S10 在 S1 之前，与 H10/K12/K13 模式一致 |

---

## 未验证/错误假设（Unverified/Wrong Assumptions）

| 编号 | 声明 | 问题 |
|------|------|------|
| W1 | §1.4 `IPO_BIZ_KEYWORDS = ['ipo', 'listed', 'neeq', 'restructuring', 'refinancing']` 可统一替换 D4 `isIpoGroupVisible` 与 F2 `IPO_CATEGORIES` | **语义不等价**。D4 现有 `IPO_KEYWORDS` 含 `'fraud_risk'` 不含 `'refinancing'`；F2 现有多字段判定（`project_type → template_type → business_category`）且 `business_category` 比对的是中文值 `['IPO', '上市公司年审', '新三板', '重大资产重组']`。见 MEDIUM-1 |
| W2 | Tasks 25-27 列出的 S34 hasSubTable 覆盖 12 张 | **缺 S34-3**。Tasks 列 10 个父码（S34-2/4/8/9/11/18/20/25/30/34）+ 已有 S34-16 = 11，findings 的 12 条中含 S34-3-1 子表。见 NIT-1 |

---

## 发现列表

### MEDIUM-1：IPO 关键词集合与消费方迁移歧义

**位置**：design.md §1.4 / §1.5 Task 8

**问题**：设计提议统一 `IPO_BIZ_KEYWORDS = ['ipo', 'listed', 'neeq', 'restructuring', 'refinancing']`，但两个现有消费方的语义与此不等价，直接替换会引入行为回归：

**D4 回归**（`useD4FormulaEngine.ts:266`）：
- 现有 `IPO_KEYWORDS = ['ipo', 'listed', 'neeq', 'restructuring', 'fraud_risk']`
- 新集合**丢弃 `fraud_risk`、新增 `refinancing`**
- 结果：`business_category` 含 `fraud_risk` 的项目不再显示 D4 "IPO/舞弊"组 tab——这是一个可观察到的功能回归，且 D4 已有 6 条 vitest 明确测试 `isIpoGroupVisible('fraud_risk_high')` 等为 `true`

**F2 回归**（`useF2SpecialFormData.ts:47-52`）：
- 现有判定是三级瀑布：`project_type === 'ipo'` → `template_type === 'listed'` → `IPO_CATEGORIES.includes(business_category)`
- 代码注释明确说明："`business_category` 仅作历史兼容兜底"，且 `IPO_CATEGORIES` 含中文值 `['IPO', '上市公司年审', '新三板', '重大资产重组']`
- 新工具函数 `isIpoProject(businessCategory: string)` 只接收一个参数，**无法替代三级瀑布**；如果 `business_category` 存的是中文值（如 `'上市公司年审'`），英文子串匹配 `'listed'.includes()` 匹配不到

**修复**（三选一，但必须在设计中明确选择）：

- **方案 A（推荐）**：扩展工具函数签名为 `isIpoProject(ctx: { businessCategory?: string; projectType?: string; templateType?: string }, allowedCats?: string[])`，内部保留三级瀑布逻辑。§1.4 代码同步更新。Task 8 明确 D4 迁移时传 `allowedCats: ['ipo', 'listed', 'neeq', 'restructuring', 'fraud_risk']` 以保留 fraud_risk 语义。
- **方案 B**：保留 `isIpoProject(biz, cats?)` 单参数签名，但 Task 8 明确声明：① D4 调用时传 `allowedCats` 包含 `'fraud_risk'`；② F2 保留自身多字段逻辑、仅将 `IPO_CATEGORIES` 替换为 `isIpoProject(biz)` 作为第三级 fallback；③ AC-7 从"收敛到 ≤2 个函数"改为"收敛到 ≤2 个 IPO 判定来源 + 各消费方保留多字段 wrapper"。
- **方案 C**：将 D4 / F2 排除出本次消费方改造范围（只让 `useAProgramData` 和 `GtWpRenderer` 使用新工具函数），D4/F2 保持原样。AC-7 对应调整。

---

### NIT-1：S34-3 缺失于公式引擎任务列表

**位置**：tasks.md Tasks 25-27 / AC-5

**问题**：findings §2.3 列出 S34 `hasSubTable` **12** 条父码（含 S34-3，子 sheet = S34-3-1）。Tasks 25-27 只列 10 个（S34-2/4/8/9/11/18/20/25/30/34），加已有 S34-16 = 11。**S34-3 缺失**。AC-5 声称"全部 12 张 hasSubTable 子表全部有公式自动计算"，与任务列表不一致。

**修复**：在 Task 25 中加入 S34-3。

---

### NIT-2：S 段路由显式路由 vs e1a fallthrough 判据未说明

**位置**：design.md §1.6

**问题**：S12/S13/S14/S15/S20 获得显式路由（s12a / s13a 等），而 S3/S4/S5/S6（同样有专属组件）落默认 e1a。判据是"是否有专属程序表数据源"，但设计只用注释 `// 无专属程序表数据源，落默认 e1a` 隐式说明了 S2/S11/S16 的情况，未解释 S3~S6 为何也落 e1a。实施者看到 S3 有 `s3-policy-change` 专属组件却路由到 e1a 可能困惑。

**修复**：在 §1.6 代码段前或注释中添加一句判据说明："路由仅为有独立程序表 sheet（如 `审计程序S12`）的底稿分配专属 sheetKey，用于侧边栏状态数据源。S3/S4/S5/S6 虽有专属渲染组件，但无独立程序表 sheet，侧边栏状态复用 e1a。"

---

## 检查清单

| # | 检查项 | 结果 |
|---|--------|------|
| 1 | 现状 grep 确认（§0） | ✅ G1~G10 全部有据可依，Task 21 假绿结论明确（全仓 0 命中 + match_workpapers 无分支） |
| 2 | 10 条策略全覆盖 | ✅ P0(5) + P1(4) + P2(3) = 12 requirement items 覆盖 findings 全部 10 条核心策略 |
| 3 | 需求三段式完整 | ✅ 每条 R-Px-y 有「已有→缺口/要做→验收」 |
| 4 | 任务合并数 | ✅ 38 个任务，接近 40 下限，合理 |
| 5 | 任务有可测试验收条件 | ✅ 每个 task 附 vitest/openpyxl/grep/浏览器验证 |
| 6 | 阶段标注 `[ ]`/`[ ]*` | ✅ P0/P1 用 `[ ]`，P2 用 `[ ]*`（标可选/外部依赖） |
| 7 | 三件套总行数 ≤1500 | ✅ 约 350~550 行，远低于 1500 |
| 8 | 需求与设计不互相复述 | ✅ 需求只描述 what/验收，设计描述 how/改动点/代码示例 |
| 9 | 未写死迁移 V 号 | ✅ §4 明确"不涉及数据库迁移" |
| 10 | S 类只取数不回写 TB | ✅ R-P1-2 铁律声明；§2.2 三个 resolver 签名只读 |
| 11 | UI 全中文化 | ✅ §1.3.2 覆盖层文案全中文 |
| 12 | 证据追溯到 findings | ✅ R-P0-1→§3.3 / R-P0-4→§2.4 / R-P1-1→§3.1 / R-P1-3→§2.5 / R-P2-1→§3.2 等全部可追溯 |
| 13 | resolveProcedureSheetKey 接入模式 | ✅ §1.6 S11/S16 显式 fallback 正确；if-chain 顺序遵循既有长前缀优先模式 |
| 14 | applicable_when vs applies_when 差异 | ✅ G3 准确区分 dict vs str，§1.1 第四路径正确处理 |
| 15 | s-checklist 字段绑定一致性 | ✅ Task 10/11 安排 openpyxl 对账 + 偏移修复，合理延迟到实施阶段 |
| 16 | 消费方迁移语义保持 | ⚠ MEDIUM-1：isIpoProject 关键词集合与 D4/F2 不等价 |

---

## 汇总

| 级别 | 数量 | 编号 |
|------|------|------|
| HIGH | 0 | — |
| MEDIUM | 1 | MEDIUM-1（IPO 关键词集合与消费方迁移歧义） |
| NIT | 2 | NIT-1（S34-3 缺失） / NIT-2（路由判据未说明） |

**判定：CHANGES_REQUESTED**（MEDIUM > 0）
