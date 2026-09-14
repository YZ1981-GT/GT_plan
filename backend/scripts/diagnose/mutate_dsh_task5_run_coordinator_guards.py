"""Task 5 run coordinator / SSE replay / 取消 / drain 守卫变异检验
（spec dsh-agent-panel-integration / Task 5）。

## 为什么需要它

"45 条守卫全绿"只证明当前代码没触发断言，**不证明断言有效**。Task 5 承载的是整条对话
的执行内核，最贵的假绿形态集中在这几处：

- **帧不再自定界**（少发帧尾空行、data 里留裸换行）⇒ 客户端在真实网络分片下把两条事件
  并成一条或把半条 JSON 当完整帧。单机不分片时看起来完全正常。
- **drain 帧带上 id** ⇒ 客户端把它当业务事件推进 ``Last-Event-ID``，重连后**跳过**真正
  的下一条事件。表现是"偶尔少一段回答"，几乎无法从日志定位。
- **回放不按 Last-Event-ID 过滤** ⇒ 重连重复下发已收事件（用户看到回答重复一遍）。
- **租约闸被放宽** ⇒ 同一个 run 两个 executor，两条流交织写同一条消息。
- **终态门被绕过** ⇒ error/cancel 之后还能发 ``done``、还能写 completed assistant 消息。
- **取消不传播到后代** ⇒ 点了取消，子 Agent 与工具继续跑（Property 8 明令计数不再增长）。
- **草稿逐 token 插行** ⇒ 一次回答在库里留下几百行消息（Req 4.12 明令只存摘要）。
- **恢复扫描无视外部副作用/重试上限** ⇒ 有工具调用的 run 被重跑（重复外部影响），
  或崩溃循环里无限重排。
- **配额被摘掉** ⇒ 队列无界堆积，6000 用户目标下直接把进程拖死。

## 两条锚点边界（本会话实测过的坑）

1. **不动 import 期契约**：``run_contract`` 在 import 时校验"终态 ↔ terminal event 一一
   对应"，破坏它会让整个文件 collection ERROR，短摘要里是文件路径而不是测试名 ⇒ 判定
   落成 WRONG-TEST 而不是 RED。
2. **枚举只改取值、不改成员名**：成员名参与守卫文件的模块级引用，改名同样炸 import。

## 四态判定

由 ``_mutation_kit`` 统一给出：RED（新增失败含期望项）/ WRONG-TEST（新增失败不含期望项）
/ GREEN（无新增失败 = 守卫缺陷）/ ANCHOR-MISS（锚点未唯一命中 = 本脚本缺陷）。
退出码不作判据。

用法::

    python backend/scripts/diagnose/mutate_dsh_task5_run_coordinator_guards.py --list
    python backend/scripts/diagnose/mutate_dsh_task5_run_coordinator_guards.py --check-anchors
    python backend/scripts/diagnose/mutate_dsh_task5_run_coordinator_guards.py --run all
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _mutation_kit import Mutation as Mut  # noqa: E402
from _mutation_kit import run_cli  # noqa: E402

REPO = Path(__file__).resolve().parents[3]

#: 本 Task 创建的守卫文件全集（覆盖面分母）。新增守卫文件必须同时加一条变异。
GUARD_FILES: dict[str, str] = {
    "test_task5_run_coordinator.py": (
        "Task 5 新建（Property 7/8/9 + 有界队列/租约/取消/drain/恢复）"
    ),
}

#: 冻结基线（本会话实测 2026-08-22）：46 passed（本文件单独跑，Redis 与 PG 均在线）。
#: 45 → 46 的来源：M21 需要一条针对"带外签发终态撞号"的专属判据，为此补了
#: ``test_cross_worker_cancel_event_is_not_swallowed_by_dedup``（该缺陷是本会话守卫实测抓到的）。
#: 🔴 Redis 或 PG 不在线时会有 skip，passed 数会变小 —— 改这个数必须说明来源。
BASELINE_BE_PASSED = 46

#: 🔴 `-rfE` 而不是 `-rf`：绝大多数判据挂在**模块级 fixture**（`coordinated`）上，变异一旦
#: 让该 fixture 抛异常，pytest 把它们记为 **ERROR** 而非 FAILED。`-rf` 的 short summary
#: 只列 failed，于是 `_mutation_kit` 的 `^ERROR\s+(\S+)` 一条都抓不到 ⇒ 明明打红了却被判
#: WRONG-TEST（Task 3/4 实测踩过）。
BE_PYTEST_ARGS = [
    "backend/tests/dsh_agent_panel/test_task5_run_coordinator.py",
    "-q",
    "--tb=no",
    "-rfE",
    "-p",
    "no:randomly",
]

EVENTS = "backend/app/services/ai_chat/run_events.py"
COORD = "backend/app/services/ai_chat/run_coordinator.py"
SERVICE = "backend/app/services/ai_chat/run_service.py"
ROUTER = "backend/app/routers/doc_ai_chat.py"

MUTATIONS: list[Mut] = [
    # ── SSE 帧自定界（Req 4.8 / Property 9 前半）────────────────────────────
    Mut(
        id="M01",
        side="be",
        path=EVENTS,
        kind="replace",
        anchor='    return "".join(f"{line}\\n" for line in lines) + "\\n"',
        new='    return "".join(f"{line}\\n" for line in lines)',
        want="test_every_frame_ends_with_blank_line",
        wants=(
            "test_property9_arbitrary_fragmentation_parses_identically",
            "test_multi_line_payload_is_split_into_multiple_data_lines",
        ),
        why=(
            "去掉帧尾空行 ⇒ 相邻两条事件被客户端并成一条（后一条的 data 追加到前一条）。"
            "服务端日志、事件条数、库里状态全都正常，只有真正解析字节流的判据能抓到 —— "
            "这正是「逐 chunk 直接拆行」那类实现的真实后果。"
        ),
        tags=("req4.8", "property9"),
    ),
    Mut(
        id="M02",
        side="be",
        path=EVENTS,
        kind="replace",
        anchor='    return normalized.split("\\n")',
        new="    return [normalized]",
        want="test_multi_line_payload_is_split_into_multiple_data_lines",
        wants=("test_property9_arbitrary_fragmentation_parses_identically",),
        why=(
            "多行负载不再拆成多个 data 行 ⇒ 裸换行进入帧内，半条 JSON 被当成完整帧、"
            "剩下半条变成未知字段被丢掉。JSON 负载平时不含裸换行，所以只有显式构造"
            "多行 data 的判据才拦得住（未来 engine 传多行文本就会踩）。"
        ),
        tags=("req4.8", "property9"),
    ),
    Mut(
        id="M03",
        side="be",
        path=EVENTS,
        kind="replace",
        anchor="        event=DRAINING_EVENT_NAME,",
        new='        event=DRAINING_EVENT_NAME,\n        event_id="999999999999",',
        want="test_draining_frame_carries_no_id",
        wants=("test_drain_emits_identifiable_abort_frame_without_id",),
        why=(
            "给 drain 帧加上 id ⇒ 客户端把传输层信号当业务事件推进 Last-Event-ID，"
            "重连时从 999999999999 之后开始 ⇒ **跳过**真正的下一条业务事件。"
            "表现是滚动更新后偶尔少一段回答，日志里毫无异常。"
        ),
        tags=("req4.9", "property9"),
    ),
    Mut(
        id="M04",
        side="be",
        path=EVENTS,
        kind="replace",
        anchor='    return f": {safe}\\n\\n"',
        new='    return f"data: {safe}\\n\\n"',
        want="test_heartbeat_and_comment_do_not_dispatch_or_move_last_event_id",
        wants=("test_property9_arbitrary_fragmentation_parses_identically",),
        why=(
            "心跳从注释帧变成真事件帧 ⇒ 客户端每 15 秒 dispatch 一条内容为 heartbeat 的"
            "假消息（面板里插入乱码气泡）。连接仍然活着，所以只有解析事件序列的判据能抓到。"
        ),
        tags=("req4.8",),
    ),
    Mut(
        id="M05",
        side="be",
        path=EVENTS,
        kind="replace",
        anchor="    lines.extend(f\"data: {line}\" for line in _data_lines(data))",
        new="    lines.extend(f\"data: {line}\" for line in _data_lines(data) if line)",
        want="test_empty_payload_still_emits_a_data_line",
        why=(
            "空负载不再发 data 行 ⇒ 整帧只剩 id/event，客户端按 SSE 规范**不 dispatch**"
            "（data buffer 为空即丢弃）。一个 quota 或 tool_finished 事件就这样静默消失。"
        ),
        tags=("req4.8",),
    ),
    # ── Last-Event-ID 续传（Property 9 后半）────────────────────────────────
    Mut(
        id="M06",
        side="be",
        path=EVENTS,
        kind="replace",
        anchor="        return [e for e in merged if event_seq(e.event_id) > after]",
        new="        return merged",
        want="test_property9_resume_by_last_event_id_loses_nothing_and_duplicates_nothing",
        wants=("test_reconnect_replays_tail_without_reinvoking_engine",),
        why=(
            "回放不再按 Last-Event-ID 过滤 ⇒ 每次重连把整条流从头重发，用户看到回答"
            "重复一遍甚至多遍。流仍然是完整的（不丢），所以只查「有没有丢」的判据抓不到，"
            "必须同时断言「不重」。"
        ),
        tags=("req4.8", "property9"),
    ),
    Mut(
        id="M07",
        side="be",
        path=EVENTS,
        kind="replace",
        anchor="                by_seq.setdefault(event_seq(ev.event_id), ev)",
        new="                by_seq[len(by_seq)] = ev",
        want="test_stream_merges_backends_without_loss_or_duplication",
        wants=(
            "test_property9_resume_by_last_event_id_loses_nothing_and_duplicates_nothing",
        ),
        why=(
            "跨后端合并不再按事件序号去重 ⇒ Redis 与本地镜像各有一份的事件被下发两次"
            "（Redis 短暂掉线又恢复时必然发生）。事件内容完全正确，只有去重判据能抓到。"
        ),
        tags=("req4.12", "property9"),
    ),
    Mut(
        id="M08",
        side="be",
        path=EVENTS,
        kind="replace",
        anchor="        self._maxlen = max(1, int(maxlen))",
        new="        self._maxlen = None",
        want="test_local_mirror_is_bounded_by_maxlen_and_run_count",
        why=(
            "等价有界缓冲变成**无界** deque ⇒ 长会话把事件全留在内存（Req 4.12 明确要求"
            "有界 + TTL，NFR-4 要求一切缓存有容量上限）。功能表现完全正常，只有容量判据"
            "能抓到 —— 这类退化通常要到生产 OOM 才暴露。"
        ),
        tags=("req4.12", "nfr4"),
    ),
    Mut(
        id="M09",
        side="be",
        path=EVENTS,
        kind="replace",
        anchor="                maxlen=self._maxlen,",
        new="                maxlen=None,",
        want="test_publish_is_readable_from_a_fresh_instance_with_ttl",
        why=(
            "Redis Stream 不再设 MAXLEN ⇒ 单个 run 的 stream 可以无限增长（Req 4.12 要求"
            "有界）。回放仍然正确，因此只有直接查 stream 长度/容量的判据能抓到。"
        ),
        tags=("req4.12",),
    ),
    Mut(
        id="M10",
        side="be",
        path=EVENTS,
        kind="replace",
        anchor="            await client.expire(key, self._ttl)",
        new="            pass",
        want="test_publish_is_readable_from_a_fresh_instance_with_ttl",
        why=(
            "Stream 不设 TTL ⇒ 回放缓冲**永不过期**，Redis 里按 run 无限累积（Req 4.12 "
            "明文要求 TTL）。功能正常、回放正常，只有查 TTL 的判据能抓到。"
        ),
        tags=("req4.12",),
    ),
    Mut(
        id="M11",
        side="be",
        path=EVENTS,
        kind="replace",
        anchor="                if ev.type in TERMINAL_EVENT_TYPES:",
        new="                if False:",
        want="test_reconnect_replays_tail_without_reinvoking_engine",
        wants=("test_drain_emits_identifiable_abort_frame_without_id",),
        why=(
            "终态事件之后不再结束订阅 ⇒ 每个已完成的 run 都把连接挂到 max_seconds"
            "（默认 1800s）。6000 用户目标下这是直接的连接耗尽，而单个用户完全看不出异常。"
        ),
        tags=("req4.5", "req4.9"),
    ),
    # ── 租约：一个 run 恰好一个 executor（Design 第 2 步）────────────────────
    Mut(
        id="M12",
        side="be",
        path=COORD,
        kind="replace",
        anchor="                        AIChatRun.lease_expires_at <= sa.func.now(),",
        new="                        AIChatRun.lease_expires_at.isnot(None),",
        want="test_two_owners_racing_one_run_yield_one_execution",
        why=(
            "把「租约已过期」放宽成「租约存在」 ⇒ 后到的 executor 直接抢走**未过期**的租约，"
            "同一个 run 两个 engine 同时跑：两条流交织、同一条 assistant 消息被两边写。"
            "顺序执行时完全正常，只有真并发 + 真 PG 行锁的判据能抓到。"
        ),
        tags=("req4.1", "req4.5"),
    ),
    Mut(
        id="M13",
        side="be",
        path=COORD,
        kind="replace",
        anchor="            if grant is None:",
        new="            if False:",
        want="test_two_owners_racing_one_run_yield_one_execution",
        why=(
            "拿不到租约也照样执行 ⇒ 租约退化成一句没人看的日志。这是「加了机制但没接线」"
            "那类假绿的标准形态：代码在、指标在、约束不生效。"
        ),
        tags=("req4.1",),
    ),
    Mut(
        id="M14",
        side="be",
        path=COORD,
        kind="replace",
        anchor="                    await self._lease.release(db, run_id, self._owner)",
        new="                    pass",
        want="test_lease_is_released_after_terminal",
        why=(
            "终态后不释放租约 ⇒ 启动恢复扫描会把这些**已完成**的 run 当成僵尸（虽然状态"
            "已是终态所以不会被误重排），且租约列长期脏数据让运维无法判断谁在跑。"
        ),
        tags=("req4.9",),
    ),
    # ── 有界队列与 typed quota（Req 13.6）──────────────────────────────────
    Mut(
        id="M15",
        side="be",
        path=COORD,
        kind="replace",
        anchor="            self._queue.put_nowait(execution)",
        new="            await self._queue.put(execution)",
        want="test_queue_full_raises_typed_quota_with_retry_after",
        wants=("test_over_quota_run_ends_as_typed_error_with_quota_event",),
        why=(
            "``put_nowait`` 改成 ``await put`` ⇒ 队列满时请求**挂住等**而不是返回 typed "
            "quota error（Req 13.6 要求带 retry_after 的可见配额）。表现是创建请求随机"
            "超时，前端草稿丢失，日志里没有任何「限流」痕迹。"
        ),
        tags=("req13.6", "nfr4"),
    ),
    Mut(
        id="M16",
        side="be",
        path=COORD,
        kind="replace",
        anchor="            await self._reject_over_quota(execution, quota)",
        new="            pass",
        want="test_over_quota_run_ends_as_typed_error_with_quota_event",
        why=(
            "队列满只抛异常、不落终态 ⇒ 那个 run 永远停在 queued，客户端订阅事件流后"
            "一直转圈（既没有 quota 事件也没有终态）。Req 12.9 明令失败不得表现为成功，"
            "这里是更糟的「既不成功也不失败」。"
        ),
        tags=("req13.6", "req4.5"),
    ),
    Mut(
        id="M17",
        side="be",
        path=COORD,
        kind="replace",
        anchor='            "reset": (_now() + timedelta(seconds=self.retry_after)).isoformat(),',
        new='            "reset_at": (_now() + timedelta(seconds=self.retry_after)).isoformat(),',
        want="test_queue_full_raises_typed_quota_with_retry_after",
        wants=("test_over_quota_run_ends_as_typed_error_with_quota_event",),
        why=(
            "配额负载的字段名漂移一个词 ⇒ 前端读 ``reset`` 得到 undefined，中文倒计时"
            "显示 NaN（Req 13.6 点名要求 remaining/reset/retry_after 三项）。"
            "后端一切正常，只有断言负载键集合的判据能抓到。"
        ),
        tags=("req13.6",),
    ),
    Mut(
        id="M18",
        side="be",
        path=COORD,
        kind="replace",
        anchor="        if not creation.should_invoke_engine:",
        new="        if False:",
        want="test_idempotent_replay_is_not_enqueued",
        why=(
            "幂等命中的重复请求也入队 ⇒ 同一个 run 被 engine 跑两次（Req 4.6 明令不重复"
            "调用模型）。第二次执行会因租约被挡住，所以库里状态**看起来**正常 —— 只有"
            "断言「重复提交不入队」的判据能抓到这次多余的模型调用。"
        ),
        tags=("req4.6",),
    ),
    # ── 终态恰好一个（Property 7）──────────────────────────────────────────
    Mut(
        id="M19",
        side="be",
        path=COORD,
        kind="replace",
        anchor="                    if etype in TERMINAL_EVENT_TYPES:",
        new="                    if False:",
        want="test_engine_error_then_done_yields_only_error",
        why=(
            "engine 的终态意图不再被识别 ⇒ error 被当成普通事件跳过，随后的 done 让 run "
            "落成**成功**（Property 7 与 Req 12.9 双重违反：engine 报错却给用户成功回答）。"
        ),
        tags=("req4.5", "property7"),
    ),
    Mut(
        id="M20",
        side="be",
        path=EVENTS,
        kind="replace",
        anchor="            if time.monotonic() - last_activity >= heartbeat_interval:",
        new="            if False:",
        why=(
            "空转时不再发心跳 ⇒ 长时间等模型首个 token 的连接被反向代理/网关按 idle "
            "掐断（Req 4.8 明列心跳）。本地直连测不出来，只有断言心跳条数的判据能抓到。"
        ),
        want="test_drain_emits_identifiable_abort_frame_without_id",
        tags=("req4.8",),
    ),
    Mut(
        id="M21",
        side="be",
        path=COORD,
        kind="replace",
        anchor="            await self._seed_sequencer(run_id)",
        # `cancel` 与 `recover_lease_expired_runs` 各有一处同形调用（同缩进），
        # 用 cancel 独有的后随行相对定位。
        scope="            event = await svc.finish_cancelled(run_id=run_id)",
        offset=-2,
        new="            pass",
        want="test_cross_worker_cancel_event_is_not_swallowed_by_dedup",
        why=(
            "带外签发终态前不再对齐序号 ⇒ 另一个 worker 处理 POST /cancel 时，它的序号"
            "从 2 重新开始，与执行 worker 已发布的事件**撞号**；而回放按序号去重 ⇒ "
            "那条 cancelled 事件被静默丢掉，客户端点了取消却一直转圈。"
            "🔴 这是本会话守卫真实抓到的缺陷，不是假想形态。"
        ),
        tags=("req4.4", "req4.7", "property9"),
    ),
    Mut(
        id="M22",
        side="be",
        path=SERVICE,
        kind="replace",
        # 20 空格缩进那一处是 `_promote_draft`（另两处是 16 空格的 update/settle），
        # 因此锚点本身已唯一，无需 scope 消歧。
        anchor="                    AIChatMessage.status == ChatMessageStatus.draft.value,",
        new="                    AIChatMessage.id == message_id,",
        want="test_external_terminal_stops_engine_events",
        wants=("test_engine_error_then_done_yields_only_error",),
        why=(
            "草稿提升不再要求当前状态是 draft ⇒ 已被结算为 failed/cancelled 的消息会被"
            "后到的 finish_success 重新改成 completed，于是 error/cancelled 终态下**存在**"
            "completed assistant 消息（Property 7 明令不存在）。"
        ),
        tags=("req4.5", "property7"),
    ),
    Mut(
        id="M23",
        side="be",
        path=SERVICE,
        kind="replace",
        anchor="        if status is ChatMessageStatus.completed:",
        new="        if False:",
        want="test_run_completes_and_publishes_monotonic_events",
        wants=("test_engine_error_then_done_yields_only_error",),
        why=(
            "允许经草稿结算旁路写 completed ⇒ 出现**第二条**终态写入路径，"
            "compare-and-set 形同虚设（Property 7 的唯一保证就来自那次 CAS）。"
        ),
        tags=("req4.5", "property7"),
    ),
    # ── 取消传播（Property 8）─────────────────────────────────────────────
    Mut(
        id="M24",
        side="be",
        path=COORD,
        kind="replace",
        anchor="        for child in list(self._children):",
        new="        for child in []:",
        want="test_request_reaches_every_registered_descendant",
        wants=("test_cancel_reaches_engine_and_child_and_freezes_tool_calls",),
        why=(
            "取消不再向下传播到子信号 ⇒ 子 Agent 与它名下的 MCP 进程继续跑（Req 4.7 要求"
            "传播到 engine/tool/child/排队任务）。父层看起来已取消，run 也落了终态，"
            "残留进程只能靠人工发现。"
        ),
        tags=("req4.7", "property8"),
    ),
    Mut(
        id="M25",
        side="be",
        path=COORD,
        kind="replace",
        anchor="        if parent is not None:",
        new="        if parent is None:",
        want="test_descendant_registered_after_cancel_is_immediately_cancelled",
        wants=("test_request_reaches_every_registered_descendant",),
        why=(
            "派生的子信号不再挂到父信号上 ⇒ 「取消与工具启动竞态」时新派生的后代永远收不到"
            "那次取消，工具调用计数继续增长（Property 8 明令不得增长）。"
        ),
        tags=("req4.7", "property8"),
    ),
    Mut(
        id="M26",
        side="be",
        path=COORD,
        kind="replace",
        anchor="        if self.is_set:",
        # `if self.is_set:` 在 add_callback 与 request 里各一次；用 add_callback 独有的
        # 前一行（唯一）相对定位，不用绝对行号（文件一改就失效）。
        scope="        self._callbacks.append(callback)",
        offset=1,
        new="        if False:",
        want="test_descendant_registered_after_cancel_is_immediately_cancelled",
        why=(
            "取消之后才登记的停止回调不再立即执行 ⇒ 那个后代（正在启动的工具/子进程）"
            "永远等不到取消信号。这是取消竞态里最容易漏的一格。"
        ),
        tags=("req4.7", "property8"),
    ),
    Mut(
        id="M27",
        side="be",
        path=COORD,
        kind="replace",
        anchor="                    if signal.is_set:",
        new="                    if False:",
        want="test_cancel_reaches_engine_and_child_and_freezes_tool_calls",
        wants=("test_queued_run_cancel_never_starts_engine",),
        why=(
            "协调器主循环不再检查取消 ⇒ 即使信号已置位，engine 的剩余事件继续被签发、"
            "工具继续被记数，直到脚本自然跑完（Property 8 的「取消后计数不再增长」直接塌）。"
        ),
        tags=("req4.7", "property8"),
    ),
    Mut(
        id="M28",
        side="be",
        path=COORD,
        kind="replace",
        anchor="        if await self._cancels.is_marked_remote(run_id):",
        new="        if False:",
        want="test_queued_run_cancel_never_starts_engine",
        why=(
            "排队期间的取消不再被 executor 看见 ⇒ 用户取消了一个还没开跑的 run，它照样"
            "被完整执行一遍（Req 4.7 明确排队任务也要收到取消）。"
        ),
        tags=("req4.7", "property8"),
    ),
    Mut(
        id="M29",
        side="be",
        path=COORD,
        kind="replace",
        anchor="        if self.is_set:",
        # 同 M26，但定位到 `request` 里那一处：用它独有的后随赋值行相对定位。
        scope="        self._reason = reason",
        offset=-2,
        new="        if False:",
        want="test_request_reaches_every_registered_descendant",
        why=(
            "取消不再幂等 ⇒ 每次调用都重新遍历并触发一轮后代回调（重复 kill、重复审计），"
            "``POST /cancel`` 被连点几下就会把清理动作跑好几遍。"
        ),
        tags=("req4.7",),
    ),
    Mut(
        id="M30",
        side="be",
        path=COORD,
        kind="replace",
        anchor="        if status in (",
        new="        if False and status in (",
        want="test_cancel_is_idempotent_and_terminal_safe",
        why=(
            "已终态的 run 也走一遍取消流程 ⇒ 对一次早已成功的回答写 cancel_requested_at、"
            "并可能签发第二个终态事件（Req 4.5）。前端会把已完成的消息显示成「已取消」。"
        ),
        tags=("req4.5", "req4.7"),
    ),
    # ── 不逐 token 写行（Req 4.12）─────────────────────────────────────────
    Mut(
        id="M31",
        side="be",
        path=COORD,
        kind="replace",
        anchor="                            await svc.update_assistant_draft(",
        new="                            await svc.append_assistant_draft(",
        want="test_two_hundred_deltas_do_not_create_two_hundred_message_rows",
        wants=("test_delta_and_done_share_one_server_issued_message_id",),
        why=(
            "草稿节流从「原地更新」改成「追加新行」 ⇒ 一次回答在库里留下每个节流窗口一行"
            "（Req 4.12 明令数据库只存摘要）。功能完全正常、事件流完全正常，"
            "只有真实行数判据能抓到；history 会因此变成一堆重复的半截回答。"
        ),
        tags=("req4.12",),
    ),
    Mut(
        id="M32",
        side="be",
        path=COORD,
        kind="replace",
        anchor="            draft_message_id=draft_id,",
        new="            draft_message_id=None,",
        want="test_delta_and_done_share_one_server_issued_message_id",
        wants=("test_two_hundred_deltas_do_not_create_two_hundred_message_rows",),
        why=(
            "定稿不再提升草稿而是另插一行 ⇒ delta 引用的 message_id 与 done/history 的"
            "不一致，前端手里的流式消息永远等不到自己的终态，刷新后还会看到「两条消息」"
            "（一条 draft 一条 completed）。"
        ),
        tags=("req4.4", "req4.12"),
    ),
    # ── 序号单调与带外签发（Req 4.4）───────────────────────────────────────
    Mut(
        id="M33",
        side="be",
        path=SERVICE,
        kind="replace",
        anchor="        self._seq[run_id] = max(current, int(last_seq), RUN_STARTED_EVENT_SEQ)",
        new="        self._seq[run_id] = int(last_seq)",
        want="test_sequencer_seed_only_moves_forward",
        why=(
            "seed 允许把计数**拉回去** ⇒ 重排接手或带外签发时新事件与已发布事件撞号，"
            "而回放按序号去重 ⇒ 那条事件（很可能就是终态）被静默丢掉。"
            "本会话实测过这个形态：跨进程取消的 cancelled 事件消失，客户端一直转圈。"
        ),
        tags=("req4.4", "property9"),
    ),
    Mut(
        id="M34",
        side="be",
        path=COORD,
        kind="replace",
        anchor="        history = await self._stream.history(run_id)",
        new="        history = []",
        want="test_side_effect_free_run_is_requeued_and_actually_reruns",
        why=(
            "序号不再从流里对齐 ⇒ 换进程接手同一个 run 时事件 ID 从 2 重新开始，"
            "与前一轮已发布的事件撞号（Req 4.4 的单调性正是为此）。"
        ),
        tags=("req4.4", "req4.9"),
    ),
    # ── 启动恢复（Design 第 7 步 / Req 4.9）───────────────────────────────
    Mut(
        id="M35",
        side="be",
        path=COORD,
        kind="replace",
        anchor="        if tool_calls:",
        new="        if False:",
        want="test_run_with_external_side_effects_is_not_requeued",
        why=(
            "恢复扫描无视已发生的工具调用 ⇒ 有外部副作用的 run 被整条重跑，"
            "取数/写入类工具再执行一遍（Design 第 7 步的前置条件就是「无副作用」）。"
        ),
        tags=("req4.9",),
    ),
    Mut(
        id="M36",
        side="be",
        path=COORD,
        kind="replace",
        anchor="                not side_effects and int(row.retry_count or 0) < self._max_retries",
        new="                not side_effects",
        want="test_retry_limit_is_enforced",
        why=(
            "去掉 retry limit ⇒ 一个每次都让进程崩掉的 run 会被无限重排（崩溃循环）。"
            "单次恢复看起来完全正常，只有「已达上限的 run 必须标失败」的判据能抓到。"
        ),
        tags=("req4.9",),
    ),
    Mut(
        id="M37",
        side="be",
        path=COORD,
        kind="replace",
        anchor="                    AIChatRun.lease_expires_at <= sa.func.now(),",
        new="                    AIChatRun.lease_expires_at >= sa.func.now(),",
        want="test_report_counts_are_consistent",
        wants=(
            "test_side_effect_free_run_is_requeued_and_actually_reruns",
            "test_run_with_external_side_effects_is_not_requeued",
        ),
        why=(
            "恢复扫描的条件反过来 ⇒ 扫到的是**租约仍然有效**（正在跑）的 run，把活着的"
            "执行打断成 interrupted，而真正的僵尸 run 永远不被接管。两头都错。"
        ),
        tags=("req4.9",),
    ),
    Mut(
        id="M38",
        side="be",
        path=COORD,
        kind="replace",
        anchor="        if row is None or row.status != ChatRunStatus.queued.value:",
        new="        if False:",
        want="test_side_effect_free_run_is_requeued_and_actually_reruns",
        why=(
            "重排不再校验 run 仍处于 queued ⇒ 已经终态或正在跑的 run 也会被重新入队执行"
            "（同一个 run 两条执行流）。"
        ),
        tags=("req4.9",),
    ),
    # ── engine 接缝与不假成功（Req 10.5）──────────────────────────────────
    Mut(
        id="M39",
        side="be",
        path=COORD,
        kind="replace",
        anchor="        if engine is None:",
        new="        if False:",
        want="test_broken_engine_provider_yields_typed_error",
        why=(
            "engine 为 None 时不再落 typed error ⇒ 直接 AttributeError 冒到 worker 的"
            "``except Exception``，run 永远停在 running（既没有终态也没有错误码），"
            "客户端一直转圈。Req 10.5 要求的是明确的 engine_unavailable。"
        ),
        tags=("req10.5", "req4.5"),
    ),
    Mut(
        id="M40",
        side="be",
        path=COORD,
        kind="replace",
        anchor='        from app.services.ai_chat import engine as engine_mod  # type: ignore[attr-defined]',
        new="        raise ImportError('forced')",
        want="test_default_engine_provider_really_binds_to_the_engine_module",
        why=(
            "把 engine 模块的接线掐断 ⇒ 每个 run 都以 engine_unavailable 结束，"
            "而这条路径**不抛异常**（Req 10.5 要求它是 typed error）⇒ 典型 fail-open："
            "整个功能不工作但日志只有一行 ERROR。只有真调一次 provider 的判据能抓到。"
        ),
        tags=("req10.5",),
    ),
    Mut(
        id="M41",
        side="be",
        path=COORD,
        kind="replace",
        anchor="        if text_parts:",
        new="        if True:",
        want="test_broken_engine_provider_yields_typed_error",
        why=(
            "engine 一个字都没产出也按成功定稿 ⇒ 用户收到一条**空的** assistant 消息并"
            "看到 done（Req 12.9 明令 fail-soft 空结果不得产生 success 终态）。"
        ),
        tags=("req12.9", "req4.5"),
    ),
    # ── 事件流授权与路由同源 ──────────────────────────────────────────────
    Mut(
        id="M42",
        side="be",
        path=ROUTER,
        kind="replace",
        anchor="    if row is None or row.actor_id != actor_id:",
        new="    if row is None:",
        want="test_events_route_denies_other_users_run",
        why=(
            "事件流不再校验 run 归属 ⇒ 知道 run_id 就能订阅**别人**的对话流，"
            "里面有模型正文、citations 与 Context Manifest（Req 2.1/2.5 的直接违反）。"
        ),
        tags=("req2.1", "req4.1"),
    ),
    Mut(
        id="M43",
        side="be",
        path=ROUTER,
        kind="replace",
        anchor='RUN_EVENTS_ROUTE = RUN_EVENTS_URL_TEMPLATE.removeprefix("/api/ai-chat")',
        new='RUN_EVENTS_ROUTE = "/runs/{run_id}/event-stream"',
        want="test_events_route_is_derived_from_the_url_template",
        why=(
            "真实路由与创建响应里回给前端的 ``events_url`` 分叉 ⇒ 前端拿到一个 404 地址，"
            "表现是发完消息永远等不到回复。Task 4 的守卫只锁「模板 ↔ design」这一边，"
            "本条锁「模板 ↔ 真实路由」那一边。"
        ),
        tags=("req4.1",),
    ),
    Mut(
        id="M44",
        side="be",
        path=ROUTER,
        kind="replace",
        anchor="    current_user: User = Depends(get_current_user_sse),",
        new="    current_user: User = Depends(get_current_user),",
        want="test_events_route_uses_sse_capable_auth",
        why=(
            "事件流改用普通鉴权依赖 ⇒ 原生 ``EventSource`` 无法设置 Authorization 头，"
            "所有 SSE 订阅 401（面板永远连不上）。这类问题在 fetch-based 客户端上测不出来。"
        ),
        tags=("req4.1",),
    ),
]

if __name__ == "__main__":
    raise SystemExit(
        run_cli(
            mutations=MUTATIONS,
            guard_files=GUARD_FILES,
            repo=REPO,
            description=(
                "dsh-agent-panel-integration Task 5 run coordinator / SSE / 取消守卫变异检验"
            ),
            backend_args=BE_PYTEST_ARGS,
            baseline_backend_passed=BASELINE_BE_PASSED,
        )
    )
