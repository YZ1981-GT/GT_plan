"""Task 7 采纳 fail-closed 守卫变异检验（spec dsh-agent-panel-integration / Task 7）。

## 为什么需要它

Task 7 修的是本仓库最贵的一类缺陷：**fail-open**。旧端点

1. 把客户端 ``content`` 原样写进 ``ai_content_log``（"AI 说过什么"由浏览器决定）；
2. ``wrap_ai_output_with_log`` 内部 ``except Exception`` 把日志写失败吞成 WARNING，
   端点不看返回值就 ``commit`` + ``success: True``（界面显示"已进入确认流"，实际没有）。

这类缺陷的共同特征是**四层静态检查全绿**：`get_diagnostics`、pytest 收集、类型注解、
符号 grep 都发现不了，只有"真的跑一遍并检查库里有没有那一行"才暴露。因此 Task 7 的
守卫全部落在真实 PostgreSQL 上，而"守卫是否有效"只能靠把生产代码**改坏**来反证。

## 四态判定

由 ``_mutation_kit`` 统一给出：RED（新增失败含期望项）/ WRONG-TEST（新增失败不含期望
项）/ GREEN（无新增失败 = 守卫缺陷）/ ANCHOR-MISS（锚点未唯一命中 = 本脚本缺陷）。
退出码不作判据。

## 一条刻意留白：`if log_id is None` 分支没有独立变异

``_write_content_log`` 里有三道闸门（log ID 非空 → 行真实存在 → confirm_action 为
pending）。把第一道改成 ``if False:`` 之后，第二道会以 ``AiContentLog.id IS NULL``
查不到行为由继续拒绝 ⇒ 判定必然报 **GREEN**，但那不是守卫缺陷而是**纵深防御**。
与其写一条注定 GREEN 的变异去污染判定，不如在此写明：该分支的价值是让失败原因可读
（"日志写入被内部吞掉"而不是"行不存在"），其行为等价性已被 M11（存在性核验）覆盖。

用法::

    python backend/scripts/diagnose/mutate_dsh_task7_adopt_guards.py --list
    python backend/scripts/diagnose/mutate_dsh_task7_adopt_guards.py --check-anchors
    python backend/scripts/diagnose/mutate_dsh_task7_adopt_guards.py --run be
    python backend/scripts/diagnose/mutate_dsh_task7_adopt_guards.py --run fe
    python backend/scripts/diagnose/mutate_dsh_task7_adopt_guards.py --restore
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _mutation_kit import Mutation as Mut  # noqa: E402
from _mutation_kit import run_cli  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
FRONTEND = REPO / "audit-platform" / "frontend"

#: 本 Task 涉及的守卫文件全集（覆盖面分母）。新增守卫文件必须同时加一条变异。
GUARD_FILES: dict[str, str] = {
    "test_task7_adopt_fail_closed.py": "Task 7 新建（Property 22/32/33 + 采纳归属链）",
    "test_doc_ai_chat_router.py": "Task 7 改写 adopt 类（请求契约 + 失败映射）",
    "test_doc_ai_chat_integration.py": "Task 7 改写 D4 端到端（服务层唯一出口）",
    "test_doc_ai_chat_pbt.py": "Task 7 改写 D4 PBT（请求契约拒绝夹带正文）",
    "test_disclosure_note_ai_fill_endpoint.py": "Task 7 扩展（草稿消息签发 + P11 收紧）",
    "useDocAiChat.spec.ts": "Task 7 改写采纳用例（服务端 ID / 幂等键 / 无正文）",
    "useDocAiChat.d4.spec.ts": "Task 7 改写 D4 PBT（占位 ID 拒绝 + 无正文）",
    "DocAiChatPanel.spec.ts": "Task 7 扩展（占位 ID 不 emit adopt）",
    "NoteAiFillDialog.spec.ts": "Task 7 扩展（无 message_id 时采纳禁用）",
}

#: 冻结基线（本会话实测 2026-08-22，来源 = 本脚本 ``--run`` 打印的基线行）：
#:   后端 5 个守卫文件合并跑 = 55 passed
#:   前端 4 个守卫文件合并跑 = 40 passed
#: 改这两个数必须同时说明来源。
BASELINE_BE_PASSED = 55
BASELINE_FE_PASSED = 40

#: 🔴 `-rfE` 而不是 `-rf`：真实 PG 判据挂在 ``run_with_fixture`` 里，变异一旦让夹具
#: 构建阶段抛异常，pytest 记为 **ERROR** 而非 FAILED；`-rf` 的 short summary 只列
#: failed ⇒ `_mutation_kit` 的 `^ERROR\s+(\S+)` 抓不到，明明打红却被判 WRONG-TEST。
BE_PYTEST_ARGS = [
    "backend/tests/dsh_agent_panel/test_task7_adopt_fail_closed.py",
    "backend/tests/test_doc_ai_chat_router.py",
    "backend/tests/test_doc_ai_chat_integration.py",
    "backend/tests/test_doc_ai_chat_pbt.py",
    "backend/tests/test_disclosure_note_ai_fill_endpoint.py",
    "-q",
    "--tb=no",
    "-rfE",
    "-p",
    "no:randomly",
]

FE_FILTERS = [
    "src/composables/__tests__/useDocAiChat.spec.ts",
    "src/composables/__tests__/useDocAiChat.d4.spec.ts",
    "src/components/__tests__/DocAiChatPanel.spec.ts",
    "src/components/disclosure/__tests__/NoteAiFillDialog.spec.ts",
]

ADOPT = "backend/app/services/ai_chat/adopt.py"
ROUTER = "backend/app/routers/doc_ai_chat.py"
CONTRACTS = "backend/app/services/ai_chat/contracts.py"
NOTES = "backend/app/routers/disclosure_notes.py"
FE_CHAT = "audit-platform/frontend/src/composables/useDocAiChat.ts"
FE_DIALOG = "audit-platform/frontend/src/components/disclosure/NoteAiFillDialog.vue"

#: 生产代码里"进入确认流"三段式的 except 分支首行（相对定位用的唯一 scope）。
_GENERIC_EXCEPT = (
    "    except Exception as exc:  # noqa: BLE001 — 下游任一步失败都不得产生成功响应"
)
_COMMIT_LOG_LINE = '            "采纳 commit 失败（已回滚）message=%s: %s: %s",'

MUTATIONS: list[Mut] = [
    # ── 权威正文：正文与哈希只能来自数据库 ────────────────────────────────
    Mut(
        id="M01",
        side="be",
        path=ADOPT,
        kind="replace",
        anchor="        content=source.text,",
        new='        content="采纳时另行拼装的正文",',
        want="test_adopted_content_equals_stored_message_not_any_client_input",
        wants=(
            "test_arbitrary_server_bodies_enter_confirm_flow_verbatim",
            "test_ai_fill_draft_message_can_be_adopted_end_to_end",
        ),
        why=(
            "送进确认流的正文不再是数据库里那条 assistant 消息。这正是旧端点的形态"
            "（当年是客户端 content，现在换成任何非权威来源都一样危险）。守卫必须比对"
            "`ai_content_log.generated_content` 与消息正文**逐字相等**，只断言"
            "「有 log id / 状态是 pending」的判据查不出来。"
        ),
        tags=("property22", "req8.1"),
    ),
    Mut(
        id="M02",
        side="be",
        path=ADOPT,
        kind="replace",
        anchor='    log_id = coerce_uuid(result.get("ai_content_log_id"))',
        new='    log_id = coerce_uuid(result.get("id"))',
        want="test_adopted_content_equals_stored_message_not_any_client_input",
        wants=(
            "test_arbitrary_server_bodies_enter_confirm_flow_verbatim",
            "test_second_adopt_with_same_key_replays_single_confirm_record",
        ),
        why=(
            "读错键：``wrap_ai_output_with_log`` 返回的 ``id`` 是与数据库**无关**的临时"
            "uuid4，只有 ``ai_content_log_id`` 才是落库主键。真实项目里这类「看着有值就"
            "当成功」的错接极常见，且只有「按该 ID 真的查得到行」的判据能抓住。"
        ),
        tags=("property22", "req8.7"),
    ),
    Mut(
        id="M03",
        side="be",
        path=ADOPT,
        kind="replace",
        anchor='            "confirm_action": "pending",',
        new='            "confirm_action": "confirmed",',
        # 🔴 want 指向**响应形状**的判据，不是真实 PG 那条（后者断言的是库里那行的
        # confirm_action，与响应字段是两个不同的接线点；把 want 写成前者会被判 WRONG-TEST，
        # 本会话实测踩过）。
        want="test_adopt_success_reports_confirm_flow_and_pending",
        wants=(
            "test_d4_all_host_types_go_through_server_authoritative_service",
            "test_full_chain_context_to_chat_to_adopt",
            "test_adopt_never_writes_directly_to_document",
        ),
        why=(
            "响应把状态说成已确认 ⇒ 前端会以为无需人工复核，D4 确认流门禁在 UI 层被绕开。"
            "只查库里那行是 pending 的判据不够，响应本身也要断言。"
        ),
        tags=("req8.7",),
    ),
    Mut(
        id="M04",
        side="be",
        path=ROUTER,
        kind="replace",
        anchor='    model_config = ConfigDict(extra="forbid")',
        # 该行在 AdoptHostRef 与 AdoptRequest 中逐字相同；用 AdoptRequest 独有的
        # message_id 字段声明作 scope 相对定位（offset=-2 回到目标行）。
        scope='    message_id: UUID = Field(..., description="服务端签发的 assistant 消息 ID")',
        offset=-2,
        new='    model_config = ConfigDict(extra="ignore")',
        want="test_adopt_request_rejects_client_content_and_requires_server_ids",
        wants=(
            "test_request_model_forbids_client_supplied_content",
            "test_d4_adopt_request_never_accepts_client_supplied_content",
        ),
        why=(
            "把越权字段从「拒绝」改成「静默丢弃」。残留的旧客户端仍然发 content，"
            "服务端不再报错、也不会使用它 —— 表面上没事，实际是「客户端以为提交了正文、"
            "服务端悄悄换了一份」的静默语义漂移。Req 8.1 要的是**拒绝**。"
        ),
        tags=("property22", "req8.1"),
    ),
    # ── 幂等：收据是唯一去重依据 ─────────────────────────────────────────
    Mut(
        id="M05",
        side="be",
        path=ADOPT,
        kind="replace",
        anchor="        if replay is not None:",
        new="        if False:",
        want="test_second_adopt_with_same_key_replays_single_confirm_record",
        why=(
            "命中既有成功收据时不再短路 ⇒ 同一幂等键第二次采纳又写一条 ai_content_log，"
            "确认流里出现两条待确认记录（复核人不知道该确认哪条）。只断言「两次都返回"
            "成功」的判据查不出来，必须数库里的行数。"
        ),
        tags=("req8.7",),
    ),
    Mut(
        id="M06",
        side="be",
        path=ADOPT,
        kind="replace",
        anchor=(
            "    if receipt.source_message_hash and receipt.source_message_hash "
            "!= source.content_hash:"
        ),
        new="    if False:",
        want="test_same_key_for_a_different_message_is_a_conflict_not_a_replay",
        why=(
            "幂等键被复用到**另一条**消息时按重放处理 ⇒ 用户以为采纳了 B，确认流里其实"
            "是 A。幂等的正确语义是「同一请求重放同一结果」，不是「同一 key 任意请求都"
            "返回第一次的结果」。"
        ),
        tags=("req8.7",),
    ),
    # ── 归属链：message → run → session → actor → HostContext ─────────────
    Mut(
        id="M07",
        side="be",
        path=ADOPT,
        kind="replace",
        anchor="    if row is None:",
        new="    if False:",
        want="test_unknown_message_id_is_non_enumerable_404_without_side_effects",
        why=(
            "消息不存在时不再拒绝 ⇒ 篡改 message ID 的请求走进后续逻辑（在当前实现里"
            "会以 AttributeError 500 收场，而 Req 2.5 要求不可枚举 404）。判据必须落在"
            "「抛的是 ExternalNotFound」而不是「反正失败了」。"
        ),
        tags=("property22", "req8.6"),
    ),
    Mut(
        id="M08",
        side="be",
        path=ADOPT,
        kind="replace",
        anchor="    if row.session_user_id is None or row.session_user_id != actor_id:",
        new="    if False:",
        want="test_message_owned_by_another_actor_is_rejected",
        why=(
            "去掉 actor 绑定 ⇒ 只要知道别人的 message ID 就能把别人会话里的 AI 回复"
            "送进自己项目的确认流。这是最直接的跨账号数据借用。"
        ),
        tags=("property22", "req8.6"),
    ),
    Mut(
        id="M09",
        side="be",
        path=ADOPT,
        kind="replace",
        anchor="    if row.session_host_id != host.resource_id:",
        new="    if False:",
        want="test_message_bound_to_another_host_or_project_is_rejected",
        why=(
            "去掉宿主绑定 ⇒ 在 A 底稿的会话里生成的结论可以被采纳到 B 底稿。审计追溯"
            "链（哪份底稿的 AI 说了什么）从此对不上。"
        ),
        tags=("property22", "req8.6"),
    ),
    Mut(
        id="M10",
        side="be",
        path=ADOPT,
        kind="replace",
        anchor="    if stored_hash != content_hash(text):",
        new="    if False:",
        want="test_body_edited_behind_the_hash_is_rejected",
        why=(
            "不再复核服务端哈希 ⇒ 直接改写 ai_chat_message.message_text 就能把任意正文"
            "送进确认流，且 V147 之前无哈希的存量行也一并放行（来源不可证明）。"
        ),
        tags=("property22", "req8.6"),
    ),
    Mut(
        id="M11",
        side="be",
        path=ADOPT,
        kind="replace",
        anchor="    if role != ADOPT_SOURCE_ROLE.value:",
        new="    if False:",
        want="test_user_and_unfinished_messages_are_not_adoptable",
        why=(
            "user 消息也可采纳 ⇒ 用户自己的提问被当成「AI 生成内容」进确认流，"
            "AI 溯源日志里出现根本不是模型产出的文本。"
        ),
        tags=("req8.1",),
    ),
    Mut(
        id="M12",
        side="be",
        path=ADOPT,
        kind="replace",
        anchor="    if str(row.status) != ADOPT_SOURCE_STATUS.value:",
        new="    if False:",
        want="test_user_and_unfinished_messages_are_not_adoptable",
        why=(
            "draft / failed / cancelled 消息也可采纳 ⇒ 流式中断的半截回复、错误占位串"
            "都能进确认流。Req 8.1 明确只有 completed 可被复制/转存/采纳。"
        ),
        tags=("req8.1",),
    ),
    Mut(
        id="M13",
        side="be",
        path=ADOPT,
        kind="replace",
        anchor="    if instance_id is None:",
        new="    if False:",
        want="test_report_host_has_no_instance_uuid_so_adopt_is_refused",
        why=(
            "报表宿主没有实例 UUID（稳定 ID 是 report type）。去掉这道闸门后，"
            "``instance_id=None`` 会让 wrap 的五参检查落空 ⇒ 日志根本不写，"
            "却不是以「不可采纳」的语义拒绝。Req 3.5 明令不得用 project_id 顶替。"
        ),
        tags=("req8.6",),
    ),
    Mut(
        id="M14",
        side="be",
        path=CONTRACTS,
        kind="replace",
        anchor="    AiChatAction.adopt: frozenset(",
        # 🔴 必须用 `and` 不能用 `or`：空 frozenset 是 falsy，`frozenset() or X` 求值成 X
        # ⇒ 行为完全没变（无效变异，本会话实测报 GREEN 一次）。`frozenset() and X`
        # 短路返回空集，同时保住后续多行括号结构合法。
        new="    AiChatAction.adopt: frozenset() and frozenset(",
        want="test_readonly_review_roles_cannot_adopt_even_when_they_can_read",
        why=(
            "把采纳的 capability 要求清空 ⇒ QC / EQCR 这两个「默认只读」的复核角色"
            "拿到写类动作。Req 8.8 明确：能读资源不等于能发起确认流。"
        ),
        tags=("req8.8",),
    ),
    # ── fail-closed：日志、审计、commit 任一失败都回滚 ────────────────────
    Mut(
        id="M15",
        side="be",
        path=ADOPT,
        kind="replace",
        anchor="    if exists is None:",
        new="    if False:",
        want="test_fabricated_log_id_without_a_real_row_is_a_failure",
        why=(
            "不再核验「该 log ID 真的有行」⇒ 只要返回值里有个 UUID 就当成功。"
            "这正是 Req 8.7「非空**且真实存在**」里后半句的存在理由：wrap 的返回值与"
            "落库是两件事，前者不能证明后者。"
        ),
        tags=("property33", "req8.7"),
    ),
    Mut(
        id="M16",
        side="be",
        path=ADOPT,
        kind="replace",
        anchor="            await savepoint.rollback()",
        # 两处逐字相同（AdoptFailed 分支 / 通用 except）；用通用 except 首行作 scope。
        scope=_GENERIC_EXCEPT,
        offset=2,
        new="            pass",
        want="test_log_creation_exception_rolls_back_everything",
        wants=("test_missing_log_id_from_swallowed_error_is_a_failure",),
        why=(
            "下游失败后不再回滚 SAVEPOINT ⇒ 幂等收据留在库里（status=pending），"
            "该幂等键从此永久占用：重试会命中 pending 收据被判 adopt_in_progress，"
            "用户再也采纳不了这条消息。判据必须数「失败后三类副作用是否为 0」。"
        ),
        tags=("property33", "req8.7"),
    ),
    Mut(
        id="M17",
        side="be",
        path=ADOPT,
        kind="replace",
        anchor="        await _safe_rollback(db)",
        # 三处逐字相同；用通用 except 首行作 scope 定位第二处。
        scope=_GENERIC_EXCEPT,
        offset=3,
        new="        pass",
        want="test_log_creation_exception_rolls_back_everything",
        why=(
            "失败后不回滚整事务 ⇒ 请求级 session 带着脏状态返回给 FastAPI，"
            "后续任何 commit 都可能把半成品写进去。判据断言 rollback 真的被调用过。"
        ),
        tags=("property33", "req8.7"),
    ),
    Mut(
        id="M19",
        side="be",
        path=ADOPT,
        kind="replace",
        anchor="        logger.error(",
        # 通用 except 内的 logger.error（该行在本文件有多处，故用通用 except 首行
        # 作 scope 相对定位；offset=4 落在 `logger.error(` 那一行）。
        scope=_GENERIC_EXCEPT,
        offset=4,
        new="        logger.warning(",
        want="test_log_creation_exception_rolls_back_everything",
        why=(
            "采纳失败只记 WARNING —— 与 ``wrap_ai_output_with_log`` 内部那句被吞掉的"
            "WARNING 一模一样。运维在告警里看不到「确认流没建立」，这正是本仓库最贵的"
            "fail-open 表现形态。判据必须断言 **ERROR** 级别真的产生了。"
        ),
        tags=("property33", "req12.9"),
    ),
    Mut(
        id="M20",
        side="be",
        path=ADOPT,
        kind="replace",
        anchor="        raise AdoptFailed(ADOPT_LOG_FAILED, str(exc)) from exc",
        # 两处逐字相同（通用 except / commit except）；用 commit 的日志行作 scope。
        scope=_COMMIT_LOG_LINE,
        offset=3,
        new="        pass",
        want="test_commit_exception_returns_failure_not_success",
        why=(
            "commit 抛异常后不再上抛失败 ⇒ 函数继续走到 ``return AdoptOutcome(...)``，"
            "端点返回「已进入确认流」而事务其实整体丢失。Req 8.7 把 commit 失败与日志"
            "写失败并列要求同一处置，正是为了堵这条缝。"
        ),
        tags=("property33", "req8.7"),
    ),
    Mut(
        id="M21",
        side="be",
        path=ADOPT,
        kind="replace",
        anchor="    ADOPT_LOG_FAILED: 503,",
        new="    ADOPT_LOG_FAILED: 200,",
        want="test_failure_response_shape_is_typed_and_chinese",
        wants=("test_adopt_log_failure_maps_to_typed_non_success_response",),
        why=(
            "失败码映射到 2xx ⇒ 前端 ``res.ok`` 为真，采纳失败被当成功。"
            "错误码到 HTTP 状态的映射本身也是可漂移的接线点，必须有判据锁住。"
        ),
        tags=("property33", "req12.5"),
    ),
    # ── 哈希链审计：只存 ID 与 hash ───────────────────────────────────────
    Mut(
        id="M22",
        side="be",
        path=ADOPT,
        kind="replace",
        anchor='            "resource_type": "ai_content_log",',
        new='            "resource_type": "ai_chat_message",',
        want="test_audit_row_carries_ids_and_hashes_but_never_the_body",
        why=(
            "审计行的 object_type 指向错误资源域 ⇒ 按「确认流记录」检索审计时找不到这条"
            "采纳事件，Req 12.6 的可还原性断掉。字段值也要有判据，不能只查字段存在。"
        ),
        tags=("property32", "req8.9"),
    ),
    Mut(
        id="M23",
        side="be",
        path=ADOPT,
        kind="replace",
        anchor='        "target": target_cell or target_field,',
        new='        "target": source.text,',
        want="test_audit_row_carries_ids_and_hashes_but_never_the_body",
        wants=(
            "test_adopted_content_equals_stored_message_not_any_client_input",
            "test_generate_and_adopt_audit_events_are_both_present",
        ),
        why=(
            "把消息正文塞进审计载荷 ⇒ Req 12.7 明令禁止的「重复存储完整敏感正文」。"
            "本条同时验证生产侧那道自检（发现载荷疑似带正文即拒绝写审计）真的在跑，"
            "而不是只写在注释里。"
        ),
        tags=("property32", "req12.7"),
    ),
    Mut(
        id="M24",
        side="be",
        path=ADOPT,
        kind="replace",
        anchor='ADOPT_AUDIT_ACTION = "ai_content_adopt"',
        new='ADOPT_AUDIT_ACTION = "ai_content_generate"',
        want="test_generate_and_adopt_audit_events_are_both_present",
        wants=("test_audit_row_carries_ids_and_hashes_but_never_the_body",),
        why=(
            "采纳事件与「日志创建」事件同名 ⇒ 审计里两条一样的记录，无法区分"
            "「谁生成了这条 AI 内容」与「谁把它送进确认流」。Property 32 的成对完整"
            "要求两个事件各自可识别。"
        ),
        tags=("property32", "req12.6"),
    ),
    # ── 附注 ai-fill：服务端签发可采纳的草稿消息 ──────────────────────────
    Mut(
        id="M25",
        side="be",
        path=NOTES,
        kind="replace",
        anchor="            str(note_instance_id),",
        new="            str(project_id),",
        want="test_ai_fill_draft_message_can_be_adopted_end_to_end",
        why=(
            "草稿会话的 host_id 用了项目 ID 而不是附注**实例 UUID** ⇒ 采纳时"
            "「会话宿主 == 已授权宿主」判 host_context_mismatch，附注 AI 填充的采纳"
            "整条链断掉。这正是 Req 3.5「不得把 project ID 当 doc ID」的老坑。"
        ),
        tags=("req8.1",),
    ),
    Mut(
        id="M26",
        side="be",
        path=NOTES,
        kind="replace",
        anchor='    if note_instance_id is None or reference_only or not (text or "").strip():',
        new="    if False:",
        want="test_reference_only_and_unresolved_section_issue_no_message",
        wants=("test_ai_fill_message_id_is_none_when_not_issued",),
        why=(
            "reference_only（只回检索片段、没有生成正文）与章节未实例化时也签发消息 ⇒"
            "库里出现空正文/挂在 ``host_id='None'`` 的垃圾会话，且前端会把它当成可采纳。"
        ),
        tags=("req8.1",),
    ),
    # ── 前端：只提交服务端 ID，不提交正文 ─────────────────────────────────
    Mut(
        id="M27",
        side="fe",
        path=FE_CHAT,
        kind="replace",
        anchor="    if (!isServerMessageId(messageId)) {",
        new="    if (false) {",
        want="adoptContent 对本地占位 ID 直接拒绝",
        wants=(
            "本地占位 ID 一律在发请求前被拒",
            "采纳：本地占位 ID 不 emit adopt",
        ),
        why=(
            "不再识别本地占位 ID（`ai_…` / `hist_N`）⇒ 前端把注定 422/404 的请求发出去，"
            "用户只看到「采纳失败请稍后重试」这种无从下手的提示，而真正的原因"
            "（该回复还没有服务端编号）被吞掉。"
        ),
        tags=("req8.1", "req8.5"),
    ),
    Mut(
        id="M28",
        side="fe",
        path=FE_CHAT,
        kind="replace",
        anchor="          idempotency_key: newIdempotencyKey(),",
        new="          idempotency_key: newIdempotencyKey(),\n          content: msg.text,",
        want="adoptContent 提交服务端 message ID + 幂等键，且不提交正文",
        wants=("adoptContent 对任意服务端消息 ID 必调用 adopt 端点且不提交正文",),
        why=(
            "把正文加回请求体 —— 旧实现的原始形态。服务端现在会以 422 拒绝，但前端仍不该"
            "发送：判据落在「请求体里不存在正文」，而不是「后端反正会拒」。"
        ),
        tags=("property22", "req8.1"),
    ),
    Mut(
        id="M29",
        side="fe",
        path=FE_CHAT,
        kind="replace",
        anchor="            id: m.message_id || m.id || `hist_${idx}`,",
        new="            id: m.id || `hist_${idx}`,",
        want="fetchHistory 保留服务端 message_id",
        why=(
            "历史消息的 ID 回落到 `hist_N` 占位（后端 history 返回的键是 `message_id`，"
            "没有 `id`）⇒ 任何历史消息都过不了服务端 ID 检查，采纳对历史永久不可用。"
            "这类「读了一个不存在的键」的缺陷在 TS 里也不报错。"
        ),
        tags=("req8.1",),
    ),
    Mut(
        id="M30",
        side="fe",
        path=FE_DIALOG,
        kind="replace",
        anchor=(
            "  () => mode.value === 'ai' && !!draftText.value "
            "&& !!draftMessageId.value && !props.locked,"
        ),
        new="  () => mode.value === 'ai' && !!draftText.value && !props.locked,",
        want="服务端未签发 message_id 时采纳禁用",
        why=(
            "后端没签发 message_id（reference_only / 章节未实例化 / 登记失败）时仍允许点"
            "采纳 ⇒ 要么发出必然失败的请求，要么退回「本地造 ID + 提交正文」的老路。"
            "Req 8.1 的底线是：宁可采纳不可用，也不让客户端决定正文。"
        ),
        tags=("req8.1",),
    ),
]

if __name__ == "__main__":
    raise SystemExit(
        run_cli(
            mutations=MUTATIONS,
            guard_files=GUARD_FILES,
            repo=REPO,
            description="dsh-agent-panel-integration Task 7 采纳 fail-closed 守卫变异检验",
            backend_args=BE_PYTEST_ARGS,
            frontend_filters=FE_FILTERS,
            frontend_dir=FRONTEND,
            vitest_json=REPO / "tmp_task7_vitest.json",
            baseline_backend_passed=BASELINE_BE_PASSED,
            baseline_frontend_passed=BASELINE_FE_PASSED,
        )
    )
