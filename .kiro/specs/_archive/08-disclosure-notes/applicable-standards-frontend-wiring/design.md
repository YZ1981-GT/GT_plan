# Design: applicable_standards 前端全链接通

## Overview

只补链路中断的三段，不改权威源、不改任何门控判定逻辑：

1. **后端派生**：新增纯函数 `derive_applicable_standards(standard: dict) -> list[str]`，
   放在 `standard_unification_service` 旁（与 `VALID_*` 枚举同文件，避免第二真源）
2. **后端注入**：`wp_render_config.get_render_config` 在构造 response 前**统一注入**一次
   —— 顶层 `applicable_standards` + 每个 sheet 的
   `html_data.project_context.applicable_standards`。
   一处改动覆盖全部 60+ 份 `_load_project_context`（含 I1~I6 下发原始 v2 对象的情形，
   统一注入会覆盖成规范列表）
3. **前端归一**：`normalizeApplicableStandards` 增加 v2 对象分支（与后端同口径）；
   `GtD3PrepaidAccounts` 改为经归一函数取值

> 为什么不改 `/api/projects/{id}`：披露 Tab 的数据入口是 render-config（宿主组件的
> `htmlData`），改 projects 端点还要再改一遍宿主取值路径。render-config 是最短路径，
> 且 `useF2FormData` 走 projects 端点的那条路已有 `normalizeApplicableStandards` 兜住
> （R2 修好后它也一并受益）。

## Architecture

```
projects.applicable_standard_v2  {entity_type, scope, stage}
        │
        │ StandardUnificationService.get_standard()   ← 已存在，永不返回 None
        ▼
derive_applicable_standards()  →  ["soe_standalone", "soe", "standalone"]
        │                          （新增纯函数，前后端同口径）
        ▼
wp_render_config.get_render_config()
        ├─ response["applicable_standards"]                     （顶层，新增）
        └─ sheet["html_data"]["project_context"]["applicable_standards"]  （逐 sheet，统一覆盖）
        │
        ▼
Gt{Cycle}*.vue  ── normalizeApplicableStandards() ──▶  :applicable-standards
        │
        ▼
isXDisclosureApplicable / resolveXCurrentStandard   ← 判定逻辑一行不改
```

## Components and Interfaces

### 后端 `derive_applicable_standards`

```python
def derive_applicable_standards(standard: dict | None) -> list[str]:
    """{entity_type, scope, stage} → 前端可直接匹配的字符串列表（去重、保序）。

    输出 = [f"{entity}_{scope}", entity, scope]
    - 组合值在前：`resolveXCurrentStandard` 优先匹配 `soe_consolidated` 这类整体值
    - 维度值兜底：部分循环按 `['soe']` / `['listed']` 精确比较
    - `stage` 不入列表：披露版本只由 entity_type × scope 决定（ipo/fraud 走 S 循环）
    - 非法/缺失维度按 `DEFAULT_STANDARD` 补齐（永不返回空列表）
    """
```

### 后端注入点

`wp_render_config.py` 的 `get_render_config`，在 `response = {...}` 之前：

```python
_standards: list[str] = []
try:
    _standards = derive_applicable_standards(
        await StandardUnificationService(db).get_standard(project_id)
    )
    for _s in sheets:
        hd = _s.get("html_data")
        if isinstance(hd, dict):
            ctx = hd.setdefault("project_context", {})
            if isinstance(ctx, dict):
                ctx["applicable_standards"] = list(_standards)
except Exception:            # 注入失败不阻断渲染（R1.5）
    logger.warning(...)
```

> 沿用 `wp_render_config_helpers` 注入 `population_amount` 的同款 `setdefault` 范式。

### 前端归一分支

`useF2FormData.normalizeApplicableStandards` 的 object 分支前置一条：

```ts
const entity = o.entity_type ?? o.entityType
const scope = o.scope
if (entity || scope) {
  // 与后端 derive_applicable_standards 同口径
  return dedupe([entity && scope ? `${entity}_${scope}` : '', entity, scope])
}
```

### 宿主取值

`GtD3PrepaidAccounts`：`applicableStandards` 由 `ref('')` 改为 `ref<string[]>([])`，
赋值走 `normalizeApplicableStandards(htmlData.project_context?.applicable_standards ?? htmlData.applicable_standards)`。
子组件的 `applicableStandardsRef` 已用 `Array.isArray` 兼容，无需改。

## Data Models

无 DB 变更。传输结构：

```jsonc
// GET /api/workpapers/{id}/render-config
{
  "wp_id": "...",
  "applicable_standards": ["soe_standalone", "soe", "standalone"],
  "sheets": [
    { "sheet_name": "...", "html_data": { "project_context": {
        "applicable_standards": ["soe_standalone", "soe", "standalone"] } } }
  ]
}
```

## Correctness Properties

### Property 1: 派生结果永不为空
对任意输入（含 `None` / `{}` / 非法枚举值），`derive_applicable_standards` 返回长度 ≥ 2 的列表。
**Validates: Requirements 1.4, 3.3**

### Property 2: 组合值优先且元素去重
返回列表首项为 `{entity}_{scope}`，且无重复元素。
**Validates: Requirements 1.3**

### Property 3: 前后端同口径
对同一 v2 对象，前端 `normalizeApplicableStandards` 与后端 `derive_applicable_standards`
返回相同序列。
**Validates: Requirements 2.1, 2.5**

### Property 4: 既有形态零回归
对既有输入样本（字符串 / 数组 / `{type}` / `{code}` / `{standards:[]}` / JSON 串），
`normalizeApplicableStandards` 结果与改动前一致。
**Validates: Requirements 2.4**

### Property 5: 逐 sheet 注入覆盖
render-config 返回的每个含 `html_data` dict 的 sheet，其
`project_context.applicable_standards` 均等于顶层值，且**类型为 list**
（不得残留原始 v2 对象）。
**Validates: Requirements 1.2, 4.3**

## Error Handling

- 注入整体包在 `try/except`：任何异常只记 warning，render-config 正常返回（R1.5）
- 前端缺字段时归一返回 `[]`，各循环既有的「空列表 = 全部适用」宽松回退不变（R3.3）
- 非法 entity_type / scope 按 `DEFAULT_STANDARD` 补齐，不抛异常

## Testing Strategy

1. 后端 `backend/tests/test_applicable_standards_derive.py`：Property 1/2 + 四类输入
2. 后端 `backend/tests/test_render_config_applicable_standards.py`：注入逻辑
   （用纯函数化的注入 helper 直接测，避免起全栈）
3. 前端 `composables/__tests__/normalizeApplicableStandards.spec.ts`：
   Property 3/4（含与后端同口径的样本表）
4. 浏览器实测：D3 两版 Tab + render-config 响应体
