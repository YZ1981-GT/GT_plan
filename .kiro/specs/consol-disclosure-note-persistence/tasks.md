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

- [x] 2. 读端 schema `ConsolDisclosureSection` **不新增** `consolidation_breakdown` 字段（P1-A(a)：
  曾试加 Optional 字段但无消费者，已删；穿透唯一来源=落库 DB 列 + `consol-breakdown` 端点）
  - _Requirements: 2.2, 5.3_

- [x] 3. `_adapt_v2_sections_to_schema` **不向读端 schema 透传** breakdown（V2 章节 dict 内 breakdown
  仍供 Step 8 落库读取；适配器输出 shape 与老版逐字节一致）
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

- [x] 9. 灰度端点路由契约测试 `test_consol_note_gray_endpoint.py`（复盘补 Req4 覆盖缺口，
  ASGITransport DB-free/auth-free：GET/PUT 已注册不 404、路径不被 `{year}` 吞掉不 422、
  命中端点鉴权拦截 401/403、路由表存在 GET+PUT，3 测）
  - _Requirements: 4.1, 4.4_

## 复盘改进 Backlog（2026-07-27，未落地，待决策）

- **P1-A（已决策=(a)删字段，已落地）**：新增的 `ConsolDisclosureSection.consolidation_breakdown` 字段
  无消费者（前端穿透走既有 `ConsolBreakdownDialog` 读 `consol-breakdown` 端点，非读该内存字段）= 死重量。
  **用户选 (a) 删字段**：已删 `consolidation_schemas.py` 该字段 + 移除 `_adapt_v2_sections_to_schema` 透传；
  穿透显示唯一来源=Step 8 落库 DB 列 + 端点弹窗路径（保持不动）。备选 (b)「前端改读内存字段」未采纳。
- **P1-B（未言明副作用）**：opt-in 项目 `GET /consolidation/notes`（readonly）现每次读都跑完整 V2 生成
  （加载子公司树 + 聚合 173 章节，比 legacy 重）+ Step 8 写 180 章节到 DB（读时写库）。落库幂等无重复，
  但大集团 opt-in 有重算/写放大成本。建议 design 补决策：接受此代价（大集团慎用 / 后续加缓存）或落库
  只在显式生成/reaggregate 触发。若采纳 P1-A(b) 内存读，显示层不再依赖落库，仅剩重算成本。
- **P2**：wizard_state 读改写整 JSONB 存在 lost-update 竞态（平台所有 wizard 写者共有）；全局 True 时
  项目关 effective 仍 True（响应透明但无 UI 提示被覆盖）；Property 9 off-path 引入 benign
  "coroutine never awaited" 警告（测试通过，无生产影响）。

## Notes

- **前端无改动**：穿透显示复用既有 `ConsolBreakdownDialog`（source=note，读 `consol-breakdown` 端点）；
  opt-in 后落库 provenance 使其返回真实数据。原设计的 `consolBreakdown.ts` 内存路径基于「无既有弹窗」
  误判，实际弹窗已存在，不重建（避免冗余死代码）。
- **provenance-only**：落库仅写三字段，表格渲染唯一真源保留 `consol_note_data`。
- **级联步骤 6**：保持全局门控（读端 dispatcher 已按项目触发落库；改级联会破坏 `patch({module}.settings)` 单测）。
