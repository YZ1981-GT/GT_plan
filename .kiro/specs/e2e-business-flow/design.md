# 业务流程端到端联调 — 技术设计 v2.0

> 对应 requirements.md F1-F29

## D1 报表全零根因定位与修复（F1-F2）

### 根因分析路径

1. 确认 ReportFormulaParser 的 regex 能匹配已填充的公式格式
2. 确认 _resolve_tb 查询条件（project_id + year + standard_account_code + is_deleted=false）
3. 确认 trial_balance.standard_account_code 的值格式（是 '1001' 还是 '1001.00' 等）
4. 确认 generate_all_reports 的 applicable_standard 参数与 report_config 表中的值一致

### 已知事实

- trial_balance 中 standard_account_code = '1001', '1002', '1012' 等（纯 4 位数字字符串）
- 公式格式 TB('1001','期末余额') — 引号内是纯数字
- _TB_PATTERN = `TB\('([^']+)','([^']+)'\)` — 能匹配
- _COLUMN_MAP 有 '期末余额' → 'audited_amount' 映射
- trial_balance.audited_amount 有非零值（31 行）

### 根因定位结果（2026-05-13 代码锚定核验）

**原假设错误**：不是 applicable_standard 参数问题。实测发现：
1. 项目表已有 `template_type='soe'` + `report_scope='standalone'`
2. `resolve_applicable_standard()` 正确返回 `"soe_standalone"`
3. HTTP 端点 `/api/reports/generate` 已正确调用 resolve 逻辑
4. report_config 表中 soe_standalone 的 formula 已填充（55 行 BS）

**真正根因**：之前测试脚本 `_test_report_generation.py` 检查的字段名错误：
- 脚本检查 `r.get("amount") or r.get("current_amount")`
- 实际返回字段名是 `"current_period_amount"`（str 类型）
- 所以"全零"是测试脚本的误报，**报表引擎可能已经正常工作**

**待验证**：用正确字段名重新测试，确认 `Decimal(r["current_period_amount"]) != 0` 的行数。

### 修复方案

1. **Sprint 1 Task 1 改为**：修正测试脚本字段名，重新验证报表生成结果
2. 如果确认报表引擎已正常工作，Sprint 1 大幅简化（跳过根因排查）
3. 如果仍有问题，再逐步排查 _resolve_tb 查询逻辑
4. 前端 ReportView 已通过 HTTP 端点调用，applicable_standard 自动 resolve，无需改动

### 代码锚定

| 文件 | 位置 | 改动 |
|------|------|------|
| report_engine.py:451 | generate_all_reports | 默认值 "enterprise" 已无影响（HTTP 层 resolve 正确） |
| report_engine.py:583 | _generate_report 返回 | 字段名 current_period_amount（str 类型） |
| reports.py:41 | _resolve_applicable_standard | 已正确实现，从 Project.template_type+report_scope 组合 |
| report_config_service.py:35 | resolve_applicable_standard | 已正确实现 |
| scripts/_test_report_generation.py | 字段名检查 | 需修正为 current_period_amount |

## D2 公式 seed 端点化（F5, F22）

### 设计

将 scripts/fill_report_formulas.py 的核心逻辑封装为 service 函数：

```python
# app/services/report_formula_service.py
class ReportFormulaService:
    async def fill_all_formulas(self, db, standard: str = "all") -> dict:
        """幂等填充 report_config.formula，返回统计"""
        # 复用 fill_report_formulas.py 的匹配逻辑
        # 已有公式的行跳过（幂等）
        # 返回 {total, updated, skipped, coverage_pct}
```

端点：`POST /api/report-config/fill-formulas`
- 参数：`{standard: "all"|"soe"|"listed"}`
- 响应：`{total: 1191, updated: 316, skipped: 0, coverage: "26.5%"}`
- 权限：admin

### 代码锚定

| 文件 | 改动 |
|------|------|
| app/services/report_formula_service.py | 新建，从 scripts/ 迁移核心逻辑 |
| app/routers/report_config.py | 新增 fill-formulas 端点 |
| scripts/fill_report_formulas.py | 保留作 CLI 入口，内部调 service |

## D3 数据质量校验（F7-F8, F29）

### 设计

基础版（F7-F8）实现余额表 vs 序时账一致性检查，套件版（F29）扩展为 5 种检查。
统一由 `DataQualityService` 承载，详见 D10 套件设计。

端点：`GET /api/projects/{pid}/data-quality/check?checks=all|debit_credit|balance_vs_ledger|mapping|report_balance`

响应：
```json
{
  "total_accounts": 100,
  "checks_run": ["debit_credit_balance", "balance_vs_ledger", "mapping_completeness"],
  "summary": {"passed": 2, "warning": 1, "blocking": 0},
  "results": {
    "debit_credit_balance": {"status": "passed", "message": "借贷平衡"},
    "balance_vs_ledger": {
      "status": "warning",
      "checked": 85,
      "passed": 70,
      "differences": [...]
    },
    "mapping_completeness": {"status": "passed", "unmapped_count": 0}
  }
}
```

前端：DataQualityDialog.vue 分组展示，红/黄/绿三色。

### 代码锚定

| 文件 | 改动 |
|------|------|
| app/services/data_quality_service.py | 新建（套件模式） |
| app/routers/data_quality.py | 新建，注册到 router_registry |
| 前端 DataQualityDialog.vue | 新建 |
| 前端 TrialBalance.vue | 增加"数据质量检查"按钮 |

## D4 试算表 recalc 修复（F3-F4）

### F4 uvicorn --reload 问题

start-dev.bat 加 `--reload-exclude "*.pyc" --reload-exclude "__pycache__" --reload-exclude ".hypothesis"`

### F3 宜宾大药房 recalc

根因：该项目 trial_balance=0 但 tb_balance=812，说明 recalc 从未执行。
修复：前端进入试算表页面时，如果 trial_balance 为空但 tb_balance 有数据，自动提示"检测到账套数据但试算表为空，是否执行重算？"

## D5 流程引导（F18-F19）

### WorkflowProgress 组件

```vue
<!-- components/common/WorkflowProgress.vue -->
<template>
  <div class="workflow-progress">
    <el-steps :active="currentStep" finish-status="success" simple>
      <el-step title="导入" />
      <el-step title="映射" />
      <el-step title="试算表" />
      <el-step title="报表" />
      <el-step title="底稿" />
      <el-step title="附注" />
    </el-steps>
    <el-button v-if="nextAction" type="primary" @click="onNext">
      {{ nextAction.label }}
    </el-button>
  </div>
</template>
```

### 进度推导端点

`GET /api/projects/{pid}/workflow-status`
```json
{
  "steps": {
    "import": {"completed": true, "count": 812},
    "mapping": {"completed": true, "rate": 100},
    "trial_balance": {"completed": true, "count": 100},
    "report": {"completed": false, "count": 0},
    "workpaper": {"completed": false, "count": 0},
    "notes": {"completed": false, "count": 0}
  },
  "current_step": 3,
  "next_action": {"label": "生成报表", "route": "/projects/{pid}/reports"}
}
```

### 代码锚定

| 文件 | 改动 |
|------|------|
| app/routers/workflow_status.py | 新建 |
| components/common/WorkflowProgress.vue | 新建 |
| TrialBalance/ReportView/WorkpaperList/DisclosureEditor | 引入组件 |

## D6 报表展示（F9-F11, F27-F28）

### 6 种报表 Tab（F9）

ReportView 已有 BS/IS/CFS/EQ Tab，需确认 cash_flow_supplement 和 impairment_provision 也有 Tab。如缺失则新增。

### 穿透查询（F10）

已有 `drilldown` 端点，前端点击金额列时调用：
`GET /api/reports/{pid}/{year}/{report_type}/{row_code}/drilldown`

### 表样规范（F11, F27, F28）

详见 D9。核心：6 种行类型样式 + 金额格式化 + 缩进可视化 + 覆盖率摘要。

## D7 E2E 验证脚本（F25）

### 设计

```python
# scripts/e2e_business_flow_verify.py
"""端到端业务流程验证脚本，4 个项目全量检查"""

PROJECTS = [
    ("005a6f2d-...", "陕西华氏", 2025),
    ("5942c12e-...", "和平药房", 2025),
    ("37814426-...", "辽宁卫生", 2025),
    ("14fb8c10-...", "宜宾大药房", 2025),
]

# Layer 1: trial_balance 有数据
# Layer 2: 报表生成成功（BS/IS 非零行 ≥ 10）
# Layer 3: 数据质量检查能执行
# Layer 4: 底稿/附注生成（可选）
```

## D8 依赖链路图 + 前置条件校验器（F26）

### 依赖链路

```
tb_balance ──→ account_mapping ──→ trial_balance ──→ financial_report ──→ working_papers
    │              (auto-match)       (recalc)         (generate)          (generate)
    │                                                       │
    │                                                       └──→ disclosure_notes
    │                                                              (generate)
    └── tb_ledger（数据质量校验用，非主链路依赖）
```

### 前置条件校验器设计

```python
# app/services/prerequisite_checker.py
class PrerequisiteChecker:
    """通用前置条件校验器，每个操作调用前自动检查"""

    async def check(self, db, project_id, year, action: str) -> dict:
        """
        action: "recalc" | "generate_reports" | "generate_workpapers" | "generate_notes"
        返回: {ok: bool, message: str, prerequisite_action: str | None}
        """
        checks = {
            "recalc": self._check_recalc_prerequisites,
            "generate_reports": self._check_report_prerequisites,
            "generate_workpapers": self._check_workpaper_prerequisites,
            "generate_notes": self._check_notes_prerequisites,
        }
        checker = checks.get(action)
        if not checker:
            return {"ok": True, "message": "", "prerequisite_action": None}
        return await checker(db, project_id, year)

    async def _check_recalc_prerequisites(self, db, project_id, year):
        # 检查 account_mapping 是否存在且 rate >= 50%
        mapping_count = await db.scalar(
            sa.select(sa.func.count()).select_from(AccountMapping).where(...)
        )
        if mapping_count == 0:
            return {
                "ok": False,
                "message": "请先完成科目映射（当前无映射数据）",
                "prerequisite_action": "auto_match",
            }
        return {"ok": True, "message": "", "prerequisite_action": None}
```

### 集成方式

每个生成端点的第一行调用 checker：
```python
@router.post("/generate")
async def generate_reports(data, db, current_user):
    check = await PrerequisiteChecker().check(db, data.project_id, data.year, "generate_reports")
    if not check["ok"]:
        raise HTTPException(400, detail=check)
    # ... 正常逻辑
```

前端收到 400 时显示 `detail.message` + 按钮跳转到 `prerequisite_action` 对应页面。

### 代码锚定

| 文件 | 改动 |
|------|------|
| app/services/prerequisite_checker.py | 新建 |
| app/routers/reports.py | generate 前调用 checker |
| app/routers/trial_balance.py | recalc 前调用 checker |
| 前端各生成按钮 | catch 400 显示 message + 跳转按钮 |

## D9 报表表样规范（F27）

### CSS 类设计

```css
/* 报表行类型样式 */
.report-row--header {
  font-weight: 700;
  background: #f5f7fa;
}
.report-row--data {
  /* 正常 */
}
.report-row--total {
  font-weight: 700;
  border-top: 1px solid #dcdfe6;
}
.report-row--zero {
  opacity: 0.5;
}
.report-row--special {
  font-style: italic;
  opacity: 0.4;
}
.report-row--manual {
  /* 待手工填列 */
}

/* 金额列 */
.report-amount {
  text-align: right;
  font-family: 'Arial Narrow', monospace;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
.report-amount--negative {
  color: #f56c6c;
}

/* 缩进 */
.report-indent-0 { padding-left: 8px; }
.report-indent-1 { padding-left: 32px; }
.report-indent-2 { padding-left: 56px; }
```

### 行类型判定逻辑（前端）

```typescript
function getRowType(row: ReportRow): string {
  if (row.row_name.includes('：') || row.row_name.includes(':')) return 'header'
  if (row.is_total_row) return 'total'
  if (row.row_name.startsWith('△') || row.row_name.startsWith('▲')) return 'special'
  if (!row.formula_used && row.current_period_amount === '0') return 'manual'
  if (parseFloat(row.current_period_amount) === 0) return 'zero'
  return 'data'
}
```

### 代码锚定

| 文件 | 改动 |
|------|------|
| 前端 ReportView.vue | 表格行加 :class="getRowClass(row)" |
| 前端 styles 或 scoped | 上述 CSS 类 |
| 前端 formatAmount util | 千分位 + 负数括号 + 红色 |

## D10 数据质量检查套件（F29）

### 设计

扩展 D3 的 `DataQualityService` 为套件模式：

```python
class DataQualityService:
    async def run_all_checks(self, db, project_id, year) -> dict:
        """执行全部检查，返回分组结果"""
        results = {}
        results["debit_credit_balance"] = await self._check_debit_credit_balance(db, project_id, year)
        results["balance_vs_ledger"] = await self._check_balance_consistency(db, project_id, year)
        results["mapping_completeness"] = await self._check_mapping_completeness(db, project_id, year)
        results["report_balance"] = await self._check_report_balance(db, project_id, year)
        return results

    async def _check_debit_credit_balance(self, db, project_id, year):
        """借贷平衡：所有科目期末余额借方合计 = 贷方合计"""
        # 资产+费用类科目余额为正=借方余额
        # 负债+权益+收入类科目余额为正=贷方余额
        ...

    async def _check_mapping_completeness(self, db, project_id, year):
        """科目映射完整性：tb_balance 中所有科目都有 account_mapping"""
        unmapped = await db.execute(
            sa.select(TbBalance.account_code, TbBalance.account_name)
            .where(...)
            .where(~TbBalance.account_code.in_(
                sa.select(AccountMapping.original_account_code).where(...)
            ))
        )
        ...
```

端点：`GET /api/projects/{pid}/data-quality/check?checks=all|debit_credit|balance_vs_ledger|mapping`

### 代码锚定

| 文件 | 改动 |
|------|------|
| app/services/data_quality_service.py | 扩展为套件 |
| app/routers/data_quality.py | 支持 checks 参数 |
| 前端 DataQualityDialog.vue | 新建，分组展示检查结果 |


## 风险评估

| 风险 | 影响 | 缓解 |
|------|------|------|
| 报表引擎确认正常后仍有个别科目取不到值 | 中 | 容错：单行失败记录 warning 不阻断 |
| 宜宾大药房 auto-match 失败（无标准科目） | 中 | Task 5 先检查 account_chart source=standard 是否存在 |
| 附注模板格式不兼容 | 中 | 降级为空内容，不阻断生成 |
| 前端组件引入导致 vue-tsc 错误 | 低 | 每步 getDiagnostics 验证 |
| 数据质量检查 tb_ledger 为空 | 中 | 检查前先 COUNT，为空则跳过余额vs序时账检查项 |
