# Implementation Plan

## Overview

将合并附注 V2 落库/穿透按项目灰度化，加法式零回归。所有任务已实现完成。

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 0, "tasks": ["1"], "desc": "按项目灰度服务" },
    { "wave": 1, "tasks": ["2", "3"], "desc": "schema 字段 + 适配器透传" },
    { "wave": 2, "tasks": ["4", "5"], "desc": "dispatcher + Step8 门控改按项目" },
    { "wave": 3, "tasks": ["6"], "desc": "灰度配置端点" },
    { "wave": 4, "tasks": ["7", "8"], "desc": "测试 + 零回归门" }
  ]
}
```

## Tasks

- [x] 1. 新增 `consol_note_gray_service.is_consol_note_v2_enabled`（镜像 note_formula_gray：全局短路 /
  项目 opt-in / fail-open False）
  - _Requirements: 1.1, 1.2, 1.3_

- [x] 2. `ConsolDisclosureSection` 新增 Optional `consolidation_breakdown: dict | None = None`
  - _Requirements: 2.2, 5.3_

- [x] 3. `_adapt_v2_sections_to_schema` 透传 `consolidation_breakdown`（非 dict → None 防御 coerce）
  - _Requirements: 2.2, 5.3_

- [x] 4. `generate_consol_notes_with_flag` dispatcher 门控改为 `await is_consol_note_v2_enabled(db, pid)`
  - _Requirements: 2.1, 2.3, 5.1_

- [x] 5. `generate_full_consol_notes` Step 8 落库门控改为按项目灰度
  - _Requirements: 3.1, 3.2, 3.3_

- [x] 6. 灰度配置端点 `GET/PUT /api/consolidation/notes/{project_id}/config/consol-note-gray`
  （readonly / edit 权限，flag_modified 落库，3 段路径不冲突）
  - _Requirements: 4.1, 4.2, 4.3, 4.4_

- [x] 7. `test_consol_note_gray_service.py`：Property 1/2/3 + PBT（8 测）
  - _Requirements: 6.1_

- [x] 8. 零回归门：Property 9 + S4 契约 + 级联 PBT 全绿（41 passed）；级联步骤 6 门控保持全局不改
  - _Requirements: 5.1, 5.2_

## Notes

- **前端无改动**：穿透显示复用既有 `ConsolBreakdownDialog`（source=note，读 `consol-breakdown` 端点）；
  opt-in 后落库 provenance 使其返回真实数据。原设计的 `consolBreakdown.ts` 内存路径基于「无既有弹窗」
  误判，实际弹窗已存在，不重建（避免冗余死代码）。
- **provenance-only**：落库仅写三字段，表格渲染唯一真源保留 `consol_note_data`。
- **级联步骤 6**：保持全局门控（读端 dispatcher 已按项目触发落库；改级联会破坏 `patch({module}.settings)` 单测）。
