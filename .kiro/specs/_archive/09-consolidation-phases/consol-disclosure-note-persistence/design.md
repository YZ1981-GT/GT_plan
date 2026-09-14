# Design Document

## Overview

将合并附注 V2 落库/穿透从「全局灰度默认关空转」收敛为「按项目 opt-in + 严格零回归」。核心是新增一个
镜像 `note_formula_gray_service` 的按项目灰度服务，替换 dispatcher 与 Step 8 落库两处全局门控；配套
灰度配置端点；前端穿透显示复用**既有** `ConsolBreakdownDialog`（读 `consol-breakdown` 端点从落库表取数），
无需新增前端。**穿透显示唯一来源=落库 + 端点**（P1-A(a) 决策：读端 `ConsolDisclosureSection` 不新增
`consolidation_breakdown` 字段——曾试加但无消费者，已删）。

## Architecture

```
PUT /config/consol-note-gray  ──► project.wizard_state.consol_notes_v2_enabled (JSONB)
                                          │
GET /consolidation/notes ──► generate_consol_notes_with_flag ──┐
                                                                │ is_consol_note_v2_enabled(db, pid)
级联步骤6(全局门控,不改) ──► generate_full_consol_notes ────────┤   (全局 OR 项目 opt-in, fail-open False)
                                     │ Step 8 ──► _persist_consol_sections_v2 (provenance-only)
                                     ▼
                          disclosure_notes.consolidation_breakdown
                                     ▲
右键"查看合并明细" ──► ConsolBreakdownDialog(source=note) ──► GET .../{section}/consol-breakdown ──┘
```

## Components and Interfaces

### 组件 1：`consol_note_gray_service.is_consol_note_v2_enabled(db, project_id) -> bool`（新增）

镜像 `note_formula_gray_service.is_note_formula_enabled`：全局 True 短路 → True；否则查
`project.wizard_state.consol_notes_v2_enabled`；异常 fail-open False。

### 组件 2：`generate_consol_notes_with_flag`（dispatcher，改门控）

`getattr(settings, "CONSOL_NOTES_V2_ENABLED", False)` → `await is_consol_note_v2_enabled(db, project_id)`。
生效则 V2 生成 + `_adapt_v2_sections_to_schema`；否则老版 `generate_consol_notes_sync`。

### 组件 3：`_adapt_v2_sections_to_schema`（不改，零回归）

**不新增字段透传**（P1-A(a)：读端不携带 breakdown）。适配器保持既有映射，穿透明细走落库 + 端点。

### 组件 4：`generate_full_consol_notes` Step 8（改门控）

Step 8 落库门控由全局改为 `await is_consol_note_v2_enabled(db, parent_project_id)`。

### 组件 5：灰度配置端点（新增，`consol_notes.py`）

`GET/PUT /api/consolidation/notes/{project_id}/config/consol-note-gray`（3 段静态路径，不冲突）。
PUT 写 `wizard_state.consol_notes_v2_enabled` + `flag_modified` + commit，edit 权限。

### 组件 6：`ConsolDisclosureSection`（读端 schema 不新增字段）

P1-A(a) 决策：读端 schema **不新增** `consolidation_breakdown` 字段。曾试加 Optional 字段但无消费者
（前端穿透走既有 `ConsolBreakdownDialog` 读 `consol-breakdown` 端点，非读该内存字段）→ 死重量已删。
落库 provenance 唯一来源=`_persist_consol_sections_v2` 写 DB 列 + 端点读取。

### 组件 7：前端穿透显示（复用既有，无改动）

`ConsolBreakdownDialog`（source=note）已存在，读 `consol-breakdown` 端点显示 by_company；opt-in 后落库
provenance 使其返回真实数据。**不新增前端 consolBreakdown.ts**（原设计基于「无既有弹窗」的误判，
实际弹窗已存在，重建为冗余死代码）。

## Data Models

### 项目级 opt-in（无新表，复用 wizard_state JSONB）

```
project.wizard_state = {
  ...,
  "consol_notes_v2_enabled": bool   # 默认缺省 → False；PUT 端点写入，flag_modified 落库
}
```

### `ConsolDisclosureSection`（读端 schema 不新增字段，逐字节同改造前）

```python
class ConsolDisclosureSection(BaseModel):
    section_code: str
    section_title: str
    content: str | None = None
    rows: list[ConsolDisclosureRow] = Field(default_factory=list)
    is_editable: bool = True
    is_group_header: bool = False
    # P1-A(a)：不新增 consolidation_breakdown 字段（无消费者，穿透走落库 + 端点）
```

### provenance breakdown 形态（仅落 `disclosure_notes.consolidation_breakdown` DB 列，端点读取，读端 schema 不携带）

```
{
  "by_company": [ {"company_code", "company_name", "source_project_id", "section_title", "amount"(str Decimal)} ],
  "section_title": str,
  "computed_at": ISO8601
}
```

### 灰度配置端点响应

```
ConsolNoteGrayResponse = { project_enabled: bool, global_enabled: bool, effective_enabled: bool }
```

## Correctness Properties

### Property 1: 灰度生效值 == 全局 OR 项目 opt-in
全局开/关 × opt-in 开/关四组合，`is_consol_note_v2_enabled` 返回 `global OR optin`。
**Validates: Requirements 1.1, 6.1**

### Property 2: fail-open 恒 False
项目不存在 / wizard_state 非 dict / 异常 → False。
**Validates: Requirements 1.2, 6.1**

### Property 3: 全局 True 短路零回归
全局 True → 不查库直接 True，既有 `monkeypatch(settings)` 单测通过。
**Validates: Requirements 1.3, 5.1**

### Property 4: Step 8 落库按项目门控
全局 True（Property 9 打桩）→ persist 调用一次；全局 False + 无 opt-in → persist 不调用。
**Validates: Requirements 3.1, 3.3**

### Property 5: 适配器不新增字段且不破坏契约
适配器输出的 `ConsolDisclosureSection` 不含 `consolidation_breakdown` 字段（P1-A(a)）；S4 随机形态的 V2
章节 dict 输入下适配器永不抛错，输出合法 `ConsolDisclosureSection`，与老版契约逐字节一致。
**Validates: Requirements 2.2, 5.3**

### Property 6: 未 opt-in 读端零回归
全局关 + 未 opt-in → 读端返回老版 7 骨架章节，结构与改造前逐字节一致（读端 schema 无 breakdown 字段）。
**Validates: Requirements 2.3, 5.1**

## Error Handling

- 灰度服务任何异常 → fail-open False（关闭态）。
- 落库整体异常 → logger.warning 不阻断附注返回（既有 Step 8 try/except 保留）。
- 配置端点项目不存在 → 404；权限不足 → require_project_access 拒绝。

## Testing Strategy

- 后端 `test_consol_note_gray_service.py`：Property 1/2/3 + PBT（service 层灰度判定）。
- 端点契约 `test_consol_note_gray_endpoint.py`：ASGITransport DB-free/auth-free 验 Req4 端点注册 +
  Req4.4 路径非冲突（不被 `{year}` 吞掉）+ 鉴权拦截；正向 200 round-trip / 404 由 service Property + live 覆盖。
- 回归门：`test_consol_notes_v2_persist`（Property 9）+ `test_consol_phase2_v2_contract`（S4）+
  `test_consol_phase2_cascade_pbt` 全绿。
