-- V280: working_paper_oo_participant 加 deferred_leave_at（延迟离开标记）
--
-- 🔴 背景（spec 80 · D12 / R10 落地的后端半）：
--
-- 「保存并回到表单」在 incoming 已 durable、apply 仍在跑时，participant 主动 leave 被
-- in-flight 门（`RoomService._outstanding_request_ids_of` 查 `_OPEN_REQUEST_STATES`）
-- 拒绝 —— request 停在 `correlated` ⇒ 409 `participant_leave_refused_in_flight`。
-- 前端只能退回「等 lease 自然过期」，留下残留的 active 行（真库见过 g9 room closed
-- 后仍挂 active participant 的情形）。
--
-- 不能简单地提前放人走：`assert_final_authorization` 在 apply 提交时重验
-- `initiator_state ∈ {active, closing}`，提前转 `left` 会让这次合并「失权」收场。
-- 所以延迟离开只能是**标记列**：state 保持 `active/closing`（授权不受影响），
-- 真正的 `→ left` 迁移由 `settle_requests_of_terminal_application` 在终态结算时
-- **同一事务**执行（锁序 room → request → participant）。
--
-- 语义：`deferred_leave_at IS NOT NULL` = 「客户端已在 T 时刻登记了离开，等它发起的
-- 未终结 request 落终态后由服务端代落 left」。request 落非终态（conflict/error 未终态
-- application）时标记原样保留，裁决/重试/放弃走到终态后照常执行。
--
-- 幂等性：ADD COLUMN IF NOT EXISTS；列是纯标记，无 FK、无唯一约束依赖。
ALTER TABLE working_paper_oo_participant
    ADD COLUMN IF NOT EXISTS deferred_leave_at TIMESTAMPTZ NULL;

COMMENT ON COLUMN working_paper_oo_participant.deferred_leave_at IS
    '延迟离开登记时刻（D12）：非空表示客户端已登记离开，待其未终结 request 全部终态后'
    '由 settle_requests_of_terminal_application 同事务执行 active/closing → left。'
    'participant.state 在此期间保持 active/closing，apply 终态授权（initiator_state）不受影响。';
