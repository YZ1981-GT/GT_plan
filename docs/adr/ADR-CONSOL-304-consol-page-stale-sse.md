# ADR-CONSOL-304: 合并页 stale 用 SSE 实时感知（复用既有基础设施，不轮询）

## 状态
已接受 (2026-05-31)

## 背景

后端 `consol_note_stale_handler` 已订阅 `NOTE_UPDATED` 标记母项目对应章节 stale，但前端合并页**无 SSE/轮询感知**（F5）→ 用户看到的可能是过时合并数，不知子公司已改。新增轮询会打爆 asyncpg pool（呼应 A5/Phase 2 R5 教训）。

## 决策

- `mark_consol_sections_stale` 标记 stale 行数 > 0 后调 `_emit_consol_note_stale` → `event_bus.broadcast_raw("consol.note_stale", {project_id, year, section_id, stale_count})`（复用既有 SSE 基础设施，**不新增轮询**）。
- 标记 0 行时不广播（无变化不打扰）；无 event loop 时静默回退 logger（断开时下次进合并页读最新 stale 态兜底）。
- 前端 `ConsolidationIndex` 经 `useProjectEvents().onAnyEvent` 监听 `consol.note_stale` → 显示 warning 级 banner「子公司数据已更新，建议重新汇总」+「立即重新汇总」快捷入口（跳合并附注 Tab）。warning 不阻断当前操作。

## 后果

- 正向：合并数过时可感知 + 闭环到重新汇总；复用 SSE 不打爆 pool。
- 代价：依赖 SSE 必达性（断开时靠下次进页面读最新 stale 态兜底）。
- 守护：6A.1 SSE 发射单测（4 测试）验证 broadcast_raw 调用 + 0 行不发 + 异常静默回退。
