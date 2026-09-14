# 底稿渲染配置重构 — 设计

## 变更记录

| 版本 | 日期 | 摘要 |
|------|------|------|
| v1.0 | 2026-06-19 | 初始设计 |

## 1. 策略拆分架构

### 1.1 目标文件结构

```
backend/app/routers/
├── wp_render_config.py          # 主入口（≤800行），含 dispatch + 公共逻辑
└── wp_render_strategies/        # 新建目录
    ├── __init__.py              # 导出 RENDERER_DISPATCH dict
    ├── _context.py              # RenderContext dataclass
    ├── _b_index.py              # B-Index 自动生成
    ├── _a_program.py            # A-程序表中控台
    ├── _audit_sheet.py          # 审定表 TB 取数
    ├── _checklist.py            # 核对表
    ├── _analytical_review.py    # 分析性复核
    ├── _c_note.py               # C-附注披露
    └── _univer_grid.py          # Univer 网格
```

### 1.2 RenderContext dataclass

```python
@dataclass
class RenderContext:
    db: AsyncSession
    project_id: UUID
    wp_id: UUID
    wp_code: str
    working_paper: WorkingPaper
    classification: ClassificationResult
    component_type: str
    sheet_html_data: dict | None  # 已有持久化数据
    sheet_schema: dict | None     # YAML schema
    template_file_path: str | None
    year: int | None
    business_category: str
    cross_ref_items: list[CrossRefItem]
    prep_info: dict[str, str] | None  # _build_preparation_info 结果（lazy，仅 b-index/c-note 用时填充）
```

注：`prep_info` 为 lazy 字段——RenderContext 构造时置 None，策略函数内部按需调用 `_build_preparation_info` 填充（避免所有 sheet 都做 JOIN 查询）。

### 1.3 策略函数签名

```python
async def render(ctx: RenderContext) -> dict | None:
    """返回 sheet_html_data，None 表示不变（使用已有）"""
```

### 1.4 Dispatch 机制

```python
# wp_render_strategies/__init__.py
from ._b_index import render as render_b_index
from ._a_program import render as render_a_program
...

RENDERER_DISPATCH: dict[str, Callable] = {
    "b-index": render_b_index,
    "a-program-console": render_a_program,
    "a1-dashboard": render_a_program,
    "a2-adjustment-console": render_a_program,
    "a3-consolidation-console": render_a_program,
    "audit-sheet": render_audit_sheet,
    "checklist-table": render_checklist,
    "analytical-review": render_analytical_review,
    "c-note-table": render_c_note,
    "univer": render_univer_grid,
}
```

主函数：
```python
renderer = RENDERER_DISPATCH.get(component_type)
if renderer:
    result = await renderer(ctx)
    if result is not None:
        sheet_html_data = result
```

## 2. derive_component_type 共享核心

```python
# backend/app/services/wp_component_type_mapping.py（新文件）

_CLASS_TO_COMPONENT = { ... }  # 从 wp_classification_service 迁移
_D_SUB_ROUTING = { ... }
_F_SUB_ROUTING = { ... }

def class_code_to_component(class_code: str) -> str | None:
    """纯函数映射，返回 None 表示未匹配"""
    if class_code.startswith("D-"):
        return _D_SUB_ROUTING.get(class_code, "d-form-table")
    if class_code.startswith("F-"):
        r = _F_SUB_ROUTING.get(class_code)
        if r: return r
        return "univer"
    for prefix, ctype in _CLASS_TO_COMPONENT.items():
        if class_code.startswith(prefix):
            return ctype
    return None
```

- `wp_classification_service.derive_component_type` → 调 `class_code_to_component`，None 时抛异常
- `generate_wp_render_schema.derive_component_type` → 调 `class_code_to_component`，None 时返 "univer"

## 3. Legacy Resolver 清理

在 `auto_data_resolvers.py` 的 `_REGISTRY` 新增：

```python
"control_deficiency_count": _resolve_control_deficiency_count,
```

函数体从 `procedure_table_auto_service.py:216~229` 搬迁。

然后删除 `_resolve_legacy_source` 方法 + 调用处 fallback 逻辑。

## 4. 联动 Handler 测试设计

测试文件：`backend/tests/test_cycle_linkage_handlers_integration.py`

```python
@pytest.mark.asyncio
async def test_d_audit_determination_writes_back_tb():
    """发 WORKPAPER_SAVED with wp_code=D1-1 + rows → TB audited_amount 被更新"""

@pytest.mark.asyncio
async def test_c_control_test_writes_field_override():
    """发 WORKPAPER_SAVED with wp_code=C2-1 → field_overrides 写入 scope=c_control_test"""

@pytest.mark.asyncio
async def test_f_conclusion_writes_field_override():
    """发 WORKPAPER_SAVED with wp_code=F1-3 → field_overrides scope=f_procedure_status"""
```

每个测试：mock `async_session_factory` 返回 in-memory DB session，构造 EventPayload，直调 handler 函数，断言 DB 写入。

## 5. _WP_CODE_OVERRIDE 分组方案

选方案 A（区域注释，最小改动）：

```python
_WP_CODE_OVERRIDE: dict[str, str] = {
    # ═══════════════════════════════════════════════════════════════
    # A 循环 — 完成与报告阶段
    # ═══════════════════════════════════════════════════════════════
    "A1": "a-program-console",
    "A1-11": "wp-popup-signing",
    ...
    # ═══════════════════════════════════════════════════════════════
    # B 循环 — 计划与了解阶段
    # ═══════════════════════════════════════════════════════════════
    "B1": "a-program-console",
    ...
}
```

排序规则：同循环内按 wp_code 自然排序。

## 6. 风险与降级

| 风险 | 缓解 |
|------|------|
| 拆分后冒烟测试回归 | 每步拆 1 个策略后立即跑 1096 冒烟 |
| import 循环 | strategies 目录只 import models/services，不反向 import router |
| 前端 API 不兼容 | 不改 response 结构，只内部重组 |
