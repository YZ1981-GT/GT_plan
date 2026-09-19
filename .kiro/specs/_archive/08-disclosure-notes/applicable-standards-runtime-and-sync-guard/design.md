# Design: applicable_standards runtime provide + 同步端跨准则守卫

## Overview

两段独立改动，共用一个口径来源（`derive_applicable_standards` / `normalizeApplicableStandards`
的同口径样本表已在前序 spec 锁定）：

- **前端**：`useWorkpaperScaffold` 新增 `applicableStandards: Ref<string[]>` 并 provide；
  两条渲染路径（`GtWpRenderer` / `GtWorkpaperShell`）注入；宿主取值收敛到
  `useHostApplicableStandards`。
- **后端**：`sync_from_workpaper` 在任何写入之前校验 `current_standard` 的 **entity 维度**
  与项目 v2 准则一致；不一致抛 `StandardMismatchError` → 路由 409。

判定逻辑（`isXDisclosureApplicable` / `resolveXCurrentStandard`）一行不改。

## Architecture

```
projects.applicable_standard_v2  ← DB 权威源
        │
        ├─ derive_applicable_standards()  ──► render-config Step 9.5
        │                                      ├─ 响应顶层 applicable_standards
        │                                      └─ 逐 sheet html_data.project_context
        │                                              │
        │                        GtWpRenderer ─────────┤
        │                        GtWorkpaperShell(prop)─┤
        │                                              ▼
        │                            useWorkpaperScaffold
        │                            provide(runtime.applicableStandards)
        │                                              │
        │                            useHostApplicableStandards（宿主唯一入口）
        │                            explicit > htmlData > runtime > []
        │
        └─ detect_standard_conflict()  ◄── sync_from_workpaper(current_standard)
                   │ 冲突
                   ▼
             StandardMismatchError → 409 STANDARD_MISMATCH
```

### 为什么只守 entity 维度

附注模板只有 `note_template_listed.json` / `note_template_soe.json` 两份，章节号编制
差异也只由 entity 维度决定；`scope` 影响的是合并报表口径（另有 `CONSOL_NOTES_V2` 流程）。
只拦 entity 冲突可以做到「拦住全部真实污染场景、零误杀」：

| 项目准则 | 请求 current_standard | 判定 |
|---|---|---|
| soe_standalone | `soe_standalone` / `soe` / `standalone` | 放行（命中派生列表） |
| soe_standalone | `soe_consolidated` | 放行 + warning（scope 差异，R4.3） |
| soe_standalone | `listed_standalone` / `listed` | **409 拒绝**（R4.1） |
| soe_standalone | `general` / `default` / `''` | 放行（非准则字面量，R4.5） |
| 无准则字段 / 查询失败 | 任意 | 放行 + warning（R4.4） |

### DB 往返（R4.7）

`sync_from_workpaper` 原本已为 `audit_year` 查一次项目。改为一次性取
`(audit_year, applicable_standard_v2, template_type, report_scope)`，守卫与年度解析共用
（`_resolve_project_sync_context`）。既有 `_resolve_target_year` / `_resolve_project_audit_year`
保留不动（`sync_from_html` 与 `_autorun_validation` 仍在用）。

## Components and Interfaces

### 后端

```python
# app/services/standard_unification_service.py（纯函数，无 DB）
def detect_standard_conflict(
    project_standard: dict | None,
    requested_standard: str | None,
) -> dict | None:
    """返回 None=放行；否则返回 {"project_entity","requested_entity","allowed"} 冲突详情。"""

# app/services/wp_disclosure_sync_service.py
class StandardMismatchError(ValueError):
    """current_standard 与项目 entity_type 冲突（继承 ValueError 以便既有 422 兜底仍生效）。"""
    code = "STANDARD_MISMATCH"

async def _resolve_project_sync_context(db, project_id) -> tuple[int | None, dict | None]:
    """一次查询 → (审计年度, 结构化准则)；任何异常 fail-open 返回 (None, None)。"""
```

`sync_from_workpaper` 顺序：校验 section_id → `_resolve_project_sync_context` →
**守卫** → 其余原逻辑不变。

### 路由

`wp_disclosure_sync.py` 两个端点在 `except ValueError` **之前**加
`except StandardMismatchError` → `HTTPException(409, detail={code, detail, project_standard,
requested_standard, allowed})`。

### 前端

```ts
// composables/applicableStandards.ts（新建 leaf 模块，零依赖）
export function normalizeApplicableStandards(raw: unknown): string[]
// useF2FormData.ts 改为 re-export（存量 import 零改动）

// composables/useWorkpaperScaffold.ts
interface UseWorkpaperScaffoldOptions {
  applicableStandards?: unknown | Ref<unknown>   // 新增：数组/字符串/v2 对象皆可
}
interface WorkpaperRuntimeContext {
  applicableStandards: Ref<string[]>             // 新增
}

// composables/hostApplicableStandards.ts
export function useHostApplicableStandards(sources?: {
  explicit?: () => unknown     // props.applicableStandards / 自有 projectContext
  htmlData?: () => unknown     // props.htmlData
}): ComputedRef<string[]>
```

`useHostApplicableStandards` 在 setup 作用域 `inject(WorkpaperRuntimeContextKey, null)`
一次（🔴 setup 作用域 composable 不能写进函数体，否则运行时 TypeError），返回 computed
按 R3.2 顺序求值。

### 受影响宿主（20 份，统一改为 composable）

G1 G2 G3 G4 G5 G6 G8 G9 G11 G12 G13 G14 / H8 H10 / I2 I3 I5 I6 / F1 F3 F2
（F2/F3 的 `explicit` 来源是自有 `formData.projectContext`；H2 已有专属
`useH2ApplicableStandards`，其内部改为接受 fallback，不重写）

## Data Models

无 DB schema 变更。

- `projects.applicable_standard_v2` JSONB：`{entity_type, scope, stage}`（既有）
- render-config 响应：顶层 `applicable_standards: string[]`（既有，前序 spec 注入）
- 409 响应体：
  ```json
  {
    "code": "STANDARD_MISMATCH",
    "detail": "项目适用准则为 soe_standalone，不能以 listed_standalone 同步披露数据",
    "project_standard": "soe_standalone",
    "requested_standard": "listed_standalone",
    "allowed": ["soe_standalone", "soe", "standalone"]
  }
  ```

## Correctness Properties

### Property 1: scaffold 字段恒为字符串数组

任意输入形态（`undefined` / 字符串 / 数组 / v2 对象 / Ref），
`runtime.applicableStandards.value` 恒为 `string[]`，绝不为 `undefined`。

**Validates: Requirements 1.1, 1.2, 1.3**

### Property 2: 嵌套 scaffold 复用祖先实例

祖先已 provide 时，子 scaffold 返回的 `applicableStandards` 与祖先**同一 Ref**。

**Validates: Requirements 1.4**

### Property 3: 宿主取值优先级严格有序

`explicit`（非空）> `htmlData`（非空）> runtime（非空）> `[]`；
任一层为空数组时继续向下回退。

**Validates: Requirements 3.1, 3.2, 3.3**

### Property 4: 同 entity 恒放行 / 跨 entity 恒拒绝

对任意 `scope₁, scope₂ ∈ {standalone, consolidated}`：
`detect_standard_conflict({entity: E, scope: scope₁}, f"{E}_{scope₂}")` 恒为 `None`；
`E' ≠ E` 且 `E'` 合法时 `detect_standard_conflict({entity: E, ...}, f"{E'}_{scope₂}")` 恒非 `None`。

**Validates: Requirements 4.1, 4.2, 4.3**

### Property 5: 守卫永不因自身失败而阻断

`project_standard` 为 `None` / `{}` / 非 dict，或 `requested_standard` 为空 / 非准则字面量时，
恒返回 `None`（放行）。

**Validates: Requirements 4.4, 4.5**

### Property 6: 冲突时零写入

守卫拒绝的请求在 `disclosure_notes` 上不产生任何 INSERT/UPDATE
（守卫位于所有写入语句之前，且不 commit）。

**Validates: Requirements 4.1, 4.6**

## Error Handling

- 前端：runtime 缺失（无祖先 provide）→ inject 返回 `null` → 回退 `[]`，不抛
- 后端守卫查询异常 → warning + fail-open
- 409 被前端 `catch` 静默吞：可接受（宁可不写也不写错章节），服务端 `logger.warning`
  留证；后续如需用户可见提示另立

## Testing Strategy

| 层 | 文件 | 覆盖 |
|---|---|---|
| 后端纯函数 | `tests/test_standard_conflict_guard.py` | Property 4/5 + 参数化矩阵 |
| 后端服务 | 同上 | Property 6（fake DB 断言无 add/commit）+ fail-open |
| 后端路由 | `tests/test_wp_disclosure_sync.py` 追加 | 409 形状 + 批量端点同守卫 |
| 前端 scaffold | `composables/__tests__/useWorkpaperScaffold.spec.ts` 追加 | Property 1/2 |
| 前端宿主 | `__tests__/hostApplicableStandards.spec.ts` 改写 | Property 3 + 源码守卫（禁 `as any` 绕过 / 两条路径必须传值） |
| 实测 | chrome-devtools + postgres 只读 | R5.3 |
