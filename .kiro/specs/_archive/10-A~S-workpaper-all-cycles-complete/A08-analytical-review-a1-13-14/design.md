# 分析性复核底稿 Design

## Overview

A1-13（母公司/单体，6 sheet）和 A1-14（合并，8 sheet）是完成阶段分析性复核底稿。新增 `analytical-review` componentType，从 trial_balance 自动取数计算横向/纵向趋势 + 46 财务比率，变动原因列预留科目底稿审计说明引用接口。

## 架构设计

### componentType 路由

```python
# wp_classification_service.py
_WP_CODE_OVERRIDE["A1-13"] = "analytical-review"
_WP_CODE_OVERRIDE["A1-14"] = "analytical-review"
# VALID_COMPONENT_TYPES 加 "analytical-review"
```

### 后端数据服务

**File**: `backend/app/services/analytical_review_service.py`（新建）

核心职责：从 trial_balance 取数 + 计算变动/比率 + 组装前端所需结构。

```python
async def get_analytical_review_data(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    wp_code: str,  # "A1-13" or "A1-14"
    scope: str = "standalone",  # standalone | consolidated
) -> dict:
    """生成分析性复核全量数据"""
```

**输出结构**：
```json
{
  "wp_code": "A1-13",
  "scope": "standalone",
  "year": 2025,
  "sheets": {
    "bs_horizontal": {
      "title": "已审资产负债表（母公司）横向趋势分析",
      "index": "A1-13-1",
      "columns": ["项目", "行次", "上年审定数", "本年审定数", "变动额", "变动%", "变动状况", "显著变动原因分析"],
      "rows": [
        {"row_code": "BS-001", "name": "流动资产", "prior": 1000000, "current": 1200000, "change": 200000, "change_pct": 20.0, "status": "significant", "reason": null}
      ]
    },
    "bs_vertical": {
      "title": "已审资产负债表（母公司）纵向结构分析",
      "index": "A1-13-2",
      "columns": ["项目", "行次", "上年审定数", "比重%", "本年审定数", "比重%", "本年比上年增长差异", "变动状况", "显著变动原因分析"],
      "rows": [...]
    },
    "is_horizontal": { "title": "已审利润表横向分析", "index": "A1-13-3", ... },
    "is_vertical": { "title": "已审利润表纵向分析", "index": "A1-13-4", ... },
    "ratio_analysis": {
      "title": "已审报表财务比率分析",
      "index": "A1-13-5",
      "categories": [
        {
          "name": "一、盈利能力分析",
          "items": [
            {"seq": 1, "name": "长期资本报酬率", "formula": "(利润总额+利息支出净额)/(长期负债平均值+所有者权益平均值)", "prior_numerator": null, "prior_denominator": null, "prior_value": null, "current_numerator": null, "current_denominator": null, "current_value": null, "change": null, "conclusion": null}
          ]
        }
      ],
      "notes": ["凡涉及平均数的比率按年末年初算术平均计算", "时期数据年化处理(annualized)=本期数据÷本期月份数×12", "流动比率正常值为2,速动比率正常值为1,现金比率正常值为0.3"]
    },
    "industry_comparison": null,
    "eps_roe": null
  }
}
```

### 取数逻辑

**BS/IS 横向纵向分析**：
```python
# 从 trial_balance 按 row_code 取本年/上年审定数
rows = await db.execute(
    sa.select(TrialBalance.row_code, TrialBalance.audited_amount)
    .where(TrialBalance.project_id == project_id, TrialBalance.year == year)
)
# 上年数据
prior_rows = await db.execute(
    sa.select(TrialBalance.row_code, TrialBalance.audited_amount)
    .where(TrialBalance.project_id == project_id, TrialBalance.year == year - 1)
)
```

**比率计算**：
```python
RATIO_FORMULAS = {
    "current_ratio": {"numerator": ["BS-020"], "denominator": ["BS-058"], "name": "流动比率"},
    "quick_ratio": {"numerator": ["BS-020", "-BS-018"], "denominator": ["BS-058"], "name": "速动比率"},
    # ... 46 个比率
}
```

**变动状况判定**：
```python
SIGNIFICANT_THRESHOLD = 0.20  # 变动% > 20% 标为显著
MATERIALITY_FACTOR = 0.05     # 或变动额 > 重要性水平 * 5%

def classify_change(change_pct: float, change_amount: float, materiality: float) -> str:
    if abs(change_pct) > SIGNIFICANT_THRESHOLD or abs(change_amount) > materiality:
        return "significant"  # 红色
    elif abs(change_pct) > 0.10:
        return "attention"    # 黄色
    return "normal"           # 无标记
```

### render-config 集成

```python
# wp_render_config.py
if component_type == "analytical-review":
    from app.services.analytical_review_service import get_analytical_review_data
    data = await get_analytical_review_data(db, project_id, year, wp_code, scope)
    sheet_html_data = {"analytical_review": data}
```

### 前端组件

**File**: `audit-platform/frontend/src/components/workpaper/GtAnalyticalReview.vue`（新建）

**布局**：
```
┌───────────────────────────────────────────────────────────┐
│ 📊 已审报表分析性复核（母公司）     Tab: BS横向|BS纵向|IS横向|IS纵向|比率|同行业|EPS │
├───────────────────────────────────────────────────────────┤
│ [当前 Tab 内容 — 表格]                                      │
│ ┌──────┬────┬────────┬────────┬──────┬──────┬──────┬─────┐│
│ │ 项目 │行次│上年审定│本年审定│变动额│变动% │状况  │原因 ││
│ ├──────┼────┼────────┼────────┼──────┼──────┼──────┼─────┤│
│ │货币资金│ 1 │ 100万 │ 120万 │ 20万│ 20% │🔴显著│     ││
│ │...   │    │        │        │      │      │      │     ││
│ └──────┴────┴────────┴────────┴──────┴──────┴──────┴─────┘│
└───────────────────────────────────────────────────────────┘
```

**交互**：
- Tab 切换 6~8 个分析维度
- 科目行点击跳转对应循环底稿
- 变动原因列可手动编辑（自动保存 debounce 2s）
- 显著变动红色底、关注黄色底
- 比率表增减列用 ▲绿/▼红 箭头

### 变动原因引用接口（预留）

```python
async def get_audit_explanation_for_row(
    db: AsyncSession, project_id: UUID, year: int, row_code: str
) -> str | None:
    """从对应科目底稿的审定表审计说明中获取变动原因（预留接口）
    
    当前返回 None（各科目底稿未修订完成）。
    后续实现：按 row_code → account_codes → wp_code 映射找到审定表，
    读取其 audit_explanation 字段。
    """
    return None  # TODO: 各科目底稿修订完成后实现
```

### htmlRendererRegistry 注册

```typescript
{
  componentType: 'analytical-review',
  component: () => import('./GtAnalyticalReview.vue'),
  icon: '📊',
  label: '分析性复核',
  emits: ['save'],
}
```

## Testing Strategy

1. `analytical_review_service` 单测：mock trial_balance 数据验证变动计算/比率计算
2. render-config 集成测试：in-process httpx 验证 A1-13 返回正确数据结构
3. 前端 vitest：registry 注册 + 组件 props 渲染
4. 回归：其他 wp_code 路由不受影响
