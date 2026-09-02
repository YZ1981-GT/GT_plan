# -*- coding: utf-8 -*-
"""Task 28 变异检验：固定 guard 的阶段顺序、统一 404/403 envelope、显式 scope 路由与真实调用链。
spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 2 Task 28
Requirements: 3.1, 3.6, 3.7, 5.8, 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 11.4
Properties: **P10 / P11 / P45**

用法（仓库根目录，`py -3` 不是 `python`）::

    py -3 backend/scripts/diagnose/mutate_task28_sync_router_guards.py --list
    py -3 backend/scripts/diagnose/mutate_task28_sync_router_guards.py --check-anchors
    py -3 backend/scripts/diagnose/mutate_task28_sync_router_guards.py --run A01,A02 \\
        --report-path .kiro/specs/.../evidence/task28-sync-router/mutation_report.json

═══ 为什么用 `_mutation_kit.span` ═══

两条理由，与 Tasks 26/27 相同：

1. `span.run_cli` **不落 `.mutbak`**（内存持有变异前字节 + sha256 还原自证）。Task 27
   踩过一次「被 `^C` 打断的 runner 跳过 `finally`，把生产文件留在变异态」——
   `.mutbak` 形态下那份残留只能靠 `--restore` 找回，而并发会话可能已经读过它。
2. 本任务多条判据的**本体就是相邻若干行的组合**：guard 的「登记而不是就地 raise」、
   「404 待抛时不得进入阶段 ⑤」、legacy callback 的「委派分支在 legacy 逻辑之前」。
   拆成单行锚点就变成了另一条判据；而 `line=` 绝对行号一改文件就失效。

═══ 七类落点 ═══

1. **阶段顺序**（A01/A02/A19）—— AC 10.6 的「不可交换」。换序在功能上往往完全不变，
   只有位置判据会红。
2. **登记 vs 就地抛**（A03/A04/A05）—— 「同 envelope / 同阶段 / 同时序桶」三条的本体。
   A04 是**最贵的一条**：就地 raise 让「scope row 不存在」少跑一次 visibility 探针，
   于是响应时间成了存在性预言机，而所有「返回了 404」的功能判据全绿。
3. **六条 404 / 两条 403 / 一条 503 的逐条分型**（A06~A14）—— 每条分支各有独立异常
   类型与 error_code；共用类型时靠前的分支被短路后靠后的会顶上来，变异永久 GREEN
   （本 spec 已三次踩到）。
4. **AST 形态判据自身**（A15/A16/A17/A18）—— 「只读 scope index」「404 家族名单不漏」
   「HTTP 映射封闭」「依赖必填」。这些判据如果本身能被绕过，上面三类就全是空转。
5. **signed claim**（A20~A24）—— 签发面/消费面/验签/跨 scope/用途/过期。
6. **router 形态与统一 envelope**（B01~B18）—— 含两条**回归变异**：
   * B01 = entry 段写成默认转换器 `[^/]+` ⇒ 186 条含 `/` 的 entry 全部恒 404
     （真库首轮实测的真实缺陷，而「路径模板长得对」的形态判据全绿）；
   * B15 = 映射表键手写字面量 ⇒ `OperationScopeNotVisibleError` 落 422 ⇒
     「跨 scope 读」与「不存在」可区分（真实缺陷，5/16 条拼错）。
7. **真实调用链**（B07~B10）—— Task 26 留下的「`oo_to_html` 零生产调用方」欠账。
   删接线、把接线搬走、只靠「没抛异常」判成功，三种形态各有一条。

═══ 刻意避开的无效变异形态 ═══

* 改注释/docstring —— 不在任何判据的作用域内（本文件的 `why` 里逐字写着被禁符号，
  而判据全部走 AST，所以不会自伤）；
* 锚定 `try:` / `except` 行 —— 会把整个异常块的语义一起改掉，判定不可归因。
  A11 只替换 `except` **块内**的抛出语句，`except` 行本身逐字保留；
* 短路在正确实现下恒不触发的内嵌断言 —— 单独短路必判 GREEN。`_build_error_code_status`
  的「同 code 两个 status」分支原本就是这种形态（真实表上恒不触发 ⇒ 从测试侧不可达），
  所以本任务先给它开了只给判据用的 `spec` 注入口，B16 才有意义。

═══ 判定四态与它们的责任方 ═══

RED = 守卫有效；GREEN = **守卫缺陷**（该属性没被锁住）；WRONG-TEST = 污染残留或锚点
落错位置；ANCHOR-MISS = **脚本缺陷**。退出码不作判据 —— 只看失败名集合的差集，并逐条
核对 `restored`/`restored_sha256`。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/scripts

from _mutation_kit.span import SpanMutation, run_cli  # noqa: E402

REPO = Path(__file__).resolve().parents[3]

G = "backend/app/services/workpaper_sync/endpoint_guard.py"
R = "backend/app/routers/wp_sync_router.py"
P = "backend/app/services/workpaper_sync/endpoint_payloads.py"
L = "backend/app/routers/wp_onlyoffice_router.py"
#: Task 10 的仓储。本任务只锚它一处（A26），目的是证明**本任务的** tombstone 判据不空转。
AR = "backend/app/services/workpaper_sync/repository.py"
I = "backend/app/services/workpaper_sync/__init__.py"
REG = "backend/app/router_registry/workpaper.py"

OFF = "test_task28_sync_router"
PG = "test_task28_sync_router_pg"


def _off(node: str) -> str:
    return f"{OFF}.py::{node}"


def _pg(node: str) -> str:
    return f"{PG}.py::{node}"


MUTATIONS: list[SpanMutation] = [
    # ═══════════════════════════════════════════════════════════════════
    # A. guard：阶段顺序、登记 vs 就地抛、逐条分型
    # ═══════════════════════════════════════════════════════════════════
    SpanMutation(
        id="A01", path=G,
        anchor="REQUIRED_PHASES: Final[tuple[GuardPhase, ...]] = (\n"
               "    GuardPhase.authenticated,\n"
               "    GuardPhase.route_scope_parsed,\n"
               "    GuardPhase.scope_index_resolved,\n"
               "    GuardPhase.visibility_verified,",
        new="REQUIRED_PHASES: Final[tuple[GuardPhase, ...]] = (\n"
            "    GuardPhase.authenticated,\n"
            "    GuardPhase.route_scope_parsed,\n"
            "    GuardPhase.visibility_verified,\n"
            "    GuardPhase.scope_index_resolved,",
        want=_off(
            "TestGuardPhaseChain::"
            "test_required_phase_order_is_the_acceptance_criterion_order"
        ),
        why="把「先查 scope index 再判 visibility」换成反序 —— AC 10.6 的 authorization-"
            "before-resource 唯一要禁的就是这个交换。功能上两阶段都跑了，只有位置判据会红",
    ),
    SpanMutation(
        id="A02", path=G,
        anchor="        if tuple(self.phases) != REQUIRED_PHASES:",
        new="        if set(self.phases) != set(REQUIRED_PHASES):",
        want=_off("TestGuardPhaseChain::test_guarded_scope_rejects_reordered_phases"),
        why="逐位比对退化成集合包含 ⇒ 「阶段齐全但顺序被换」通过。缺阶段仍被拦，"
            "所以只有换序那一条判据会红 —— 这正是「集合判据抓不到换序」的证明",
    ),
    SpanMutation(
        id="A03", path=G,
        anchor="        self.enforced += 1\n"
               "        if refusals:\n"
               "            self.refused += 1\n"
               "            raise refusals[0]",
        new="        self.enforced += 1\n"
            "        if False:\n"
            "            self.refused += 1\n"
            "            raise refusals[0]",
        want=_off("TestGuardRefusals::test_missing_route_entry_is_404_not_422"),
        why="fail-open：登记的 404 永不抛出。`raise refusals[0]` 仍在源码里，所以"
            "`assert_single_refusal_site` 的「恰一个间接抛出点」照旧为 1 —— 形态判据"
            "抓不到它，只有行为判据能。同时证明「404 待抛时不得进阶段 ⑤」也真的被锁着",
        wants=(
            _off("TestConstantWorkRefusal::"
                 "test_the_action_callback_never_runs_when_a_404_is_pending"),
            _pg("TestUnifiedNotFoundOracle::test_all_five_causes_return_404"),
        ),
    ),
    SpanMutation(
        id="A04", path=G,
        anchor="            if row is None:\n"
               "                refusals.append(\n"
               "                    ScopeIndexMissError(\n"
               "                        f\"{ref.key} 在 scope index 中不可见（不存在或已 retire）—— \"\n"
               "                        \"与「跨 scope 使用」共用同一 404 语义，不得据此推断该 id 是否存在\"\n"
               "                    )\n"
               "                )\n"
               "                continue",
        new="            if row is None:\n"
            "                raise ScopeIndexMissError(\n"
            "                    f\"{ref.key} 在 scope index 中不可见\"\n"
            "                )",
        want=_off("TestGuardPhaseChain::test_the_404_family_has_exactly_one_throw_site"),
        why="就地 raise 而不是登记 —— 本任务**最贵**的一条：「scope row 不存在」于是少跑"
            "一次 visibility 探针，响应时间成为存在性预言机（攻击者拿两个 id 各打一次，"
            "快的那个=不存在）。返回码仍是 404，所有「返回了 404」的判据全绿",
        wants=(
            _off("TestConstantWorkRefusal::"
                 "test_all_three_404_causes_do_the_same_amount_of_work"),
        ),
    ),
    SpanMutation(
        id="A05", path=G,
        anchor="            if row is None:\n"
               "                refusals.append(\n"
               "                    ScopeIndexMissError(",
        new="            if row is not None and False:\n"
            "                refusals.append(\n"
            "                    ScopeIndexMissError(",
        want=_off("TestGuardRefusals::test_scope_index_miss_and_retired_share_one_type"),
        why="scope index 查不到时既不登记也不 continue ⇒ 落到下方 `ScopeAttribution("
            "project_id=row.project_id...)` 崩在 None 上。与 A04 分两条：A04 证明"
            "「登记而非就地抛」，本条证明「miss 这一支真的存在」",
    ),
    SpanMutation(
        id="A06", path=G,
        anchor="            if (\n"
               "                attribution.project_id != project_id\n"
               "                or attribution.wp_id != wp_id\n"
               "                or attribution.entry_id != str(entry_id)\n"
               "            ):",
        new="            if False:",
        want=_off("TestGuardRefusals::test_cross_scope_use_is_its_own_branch"),
        why="scope row 存在但属于别的 project/wp/entry 时放行 = 横向越权（Property 45 的"
            "本体）。这条分支被短路后**没有别的分支会顶上来**（row 查到了），"
            "所以它必须是独立类型才判得出来",
        wants=(_pg("TestUnifiedNotFoundOracle::test_all_five_causes_return_404"),),
    ),
    SpanMutation(
        id="A07", path=G,
        anchor="            if not is_opaque_resource_id(str(ref.resource_id)):",
        new="            if False:",
        want=_off("TestGuardRefusals::test_numeric_revision_as_route_key_is_refused"),
        why="numeric revision 当 scope key ⇒ 两个 wp 的 revision 1 在授权索引里碰撞成"
            "同一行（AC 10.6 / 8.7）。放行后 rollback 可以用 `/versions/1/rollback` "
            "定位到另一个 wp 的版本",
        wants=(_pg("TestUnifiedNotFoundOracle::"
                   "test_numeric_revision_as_a_route_key_is_404_not_422"),),
    ),
    SpanMutation(
        id="A08", path=G,
        anchor="            elif (\n"
               "                ref.resource_kind is ScopeResourceKind.content_version\n"
               "                and not is_uuid_text(str(ref.resource_id))\n"
               "            ):",
        new="            elif False:",
        want=_off("TestGuardRefusals::test_non_uuid_version_id_is_refused"),
        why="`\"rev-11\"` 是 opaque 的（不是纯数字），A07 那条判据拦不住它 —— 只有"
            "「content_version 必须是 immutable UUID」这条才行。两条分型的必要性就在这里",
    ),
    SpanMutation(
        id="A25", path=G,
        anchor="                refusals.append(\n"
               "                    VersionIdNotUuidError(",
        new="                refusals.append(\n"
            "                    OpaqueResourceIdRequiredError(",
        want=_off("TestGuardRefusals::test_non_uuid_version_id_is_refused"),
        why="**回归变异**（本任务变异检验实测出来的真实缺陷）：把两条 route-key 判据改回"
            "共用一个异常类型。后果不是「分型不好看」而是 A07 那条分支变成事实上的死代码 ——"
            "短路 `is_opaque_resource_id(...)` 之后本条会抛同一类型顶上来，于是"
            "「numeric revision 不得作 scope key」对 room/operation/recovery case 等"
            "全部非 version kind 从未被任何判据锁住（当时 A07 判 GREEN 就是这么来的）",
        wants=(_off("TestGuardRefusals::"
                    "test_the_two_opaque_id_branches_do_not_share_an_error_code"),),
    ),
    SpanMutation(
        id="A09", path=G,
        anchor="        if not bool(observed.get(\"project_visible\")):",
        new="        if False:",
        want=_off("TestGuardRefusals::test_project_invisible_is_404_and_the_probe_really_ran"),
        why="探针照样跑了、结果照样拿到了，只是不再据此拒绝 ⇒ 无 visibility 的 project "
            "被放行。「探针被调用过」这类弱判据抓不到它（调用次数不变）",
        wants=(_pg("TestUnifiedNotFoundOracle::test_all_five_causes_return_404"),),
    ),
    SpanMutation(
        id="A10", path=G,
        anchor="        if \"project_visible\" not in observed:\n"
               "            raise VisibilityProbeFailedError(",
        new="        if False:\n"
            "            raise VisibilityProbeFailedError(",
        want=_off("TestGuardRefusals::"
                  "test_probe_payload_missing_the_visibility_key_fails_closed"),
        why="探针少返一个键时按缺省值走 ⇒ `observed.get(...)` 得 None ⇒ 被当成「不可见」"
            "或（若判据写成 `is not False`）「可见」。两种都错：缺字段必须是探针故障，"
            "而不是一次可解读的观测",
    ),
    SpanMutation(
        id="A11", path=G,
        anchor="            raise VisibilityProbeFailedError(\n"
               "                f\"project visibility 探针失败（{type(exc).__name__}: {exc}）—— \"\n"
               "                \"不得降级为「无此限制」，也不得当作越权\"\n"
               "            ) from exc",
        new="            refusals.append(\n"
            "                ScopeProjectNotVisibleError(f\"probe failed: {exc}\")\n"
            "            )\n"
            "            return {}",
        want=_off("TestGuardRefusals::test_probe_failure_is_neither_403_nor_404"),
        why="把探针故障折进 404 家族 ⇒ 平台故障被报成「资源不存在」，运维会去查错误的"
            "地方，而攻击者也拿到一个假的存在性信号。刻意只替换 `except` **块内**的抛出"
            "语句，`except` 行本身逐字保留（锚定 except 行会把整块语义一起改掉，不可归因）",
    ),
    SpanMutation(
        id="A12", path=G,
        anchor="        if (\n"
               "            bool(observed.get(\"workflow_locked\"))\n"
               "            and str(request.action) not in self._read_only_actions\n"
               "        ):",
        new="        if False:",
        want=_off("TestGuardRefusals::test_workflow_locked_is_403_for_write_actions"),
        why="归档/复核通过的底稿被允许写入 ⇒ 已定稿底稿可被 OO 回写覆盖。403 与 404 的"
            "分型也一起塌掉（AC 10.6：可见但无权限才 403）",
        wants=(_pg("TestForbiddenIsDistinctFromNotFound::"
                   "test_workflow_lock_refuses_writes_with_403"),),
    ),
    SpanMutation(
        id="A13", path=G,
        anchor="            and str(request.action) not in self._read_only_actions\n"
               "        ):\n"
               "            self.refused += 1\n"
               "            raise SyncWorkflowLockedError(",
        new="            and True\n"
            "        ):\n"
            "            self.refused += 1\n"
            "            raise SyncWorkflowLockedError(",
        want=_off("TestGuardRefusals::"
                  "test_workflow_locked_still_allows_registered_read_actions"),
        why="只读白名单失效 ⇒ 归档底稿连 conflicts/timeline 都 403（AC 11.6「显示阻断"
            "原因」与 11.11「可追溯」直接落空）。这是真库实测抓到的真实缺陷方向：第一版"
            "无条件按 `workflow_locked` 拒绝，而当时的离线守卫只测了写 action 的否定侧",
        wants=(_pg("TestForbiddenIsDistinctFromNotFound::"
                   "test_workflow_lock_still_allows_reads"),),
    ),
    SpanMutation(
        id="A14", path=G,
        anchor="        if not verdict:\n"
               "            self.refused += 1\n"
               "            raise ActionNotPermittedError(",
        new="        if False:\n"
            "            self.refused += 1\n"
            "            raise ActionNotPermittedError(",
        want=_off("TestGuardRefusals::test_action_callback_denial_is_its_own_403_branch"),
        why="action/lease/generation/fence/bundle 重验的结果被忽略 ⇒ 「撤权后原 "
            "Idempotency-Key 重放」会一路走到 cache 并返回 cached descriptor"
            "（Property 45 末段明令禁止）",
        wants=(_off("TestRevokedReplayIsRefusedBeforeAnyCacheLookup::"
                    "test_replay_after_revocation_stops_at_the_guard"),),
    ),
    SpanMutation(
        id="A15", path=G,
        anchor="            row = await self._repo.resolve_scope(\n"
               "                resource_kind=ref.resource_kind, resource_id=str(ref.resource_id)\n"
               "            )",
        new="            row = await self._repo.resolve_scope(\n"
            "                resource_kind=ref.resource_kind, resource_id=str(ref.resource_id)\n"
            "            )\n"
            "            if False:\n"
            "                _leak = WorkpaperOoRoom  # noqa: F821",
        want=_off("TestGuardPhaseChain::test_authorization_phase_touches_only_the_scope_index"),
        why="在阶段 ③ 引用业务表符号 —— 运行期不可达（`if False:`），所以**行为**判据一条"
            "都不会红；只有 AST 形态判据会。AC 10.5/10.6 禁的正是代码形态"
            "（「严禁先查 room/operation/recovery/application 来反推 scope」）",
    ),
    SpanMutation(
        id="A16", path=G,
        anchor="        \"ScopeCrossBoundaryError\",\n"
               "        \"ScopeClaimMismatchError\",\n"
               "        \"ScopeProjectNotVisibleError\",\n"
               "    }\n"
               ")",
        new="        \"ScopeCrossBoundaryError\",\n"
            "        \"ScopeClaimMismatchError\",\n"
            "    }\n"
            ")",
        want=_off("TestGuardPhaseChain::"
                  "test_every_404_subclass_is_registered_for_the_throw_site_judgement"),
        why="404 家族名单漏一条 ⇒ `assert_single_refusal_site` 扫源码时看不见它，"
            "于是那条分支可以被就地 raise 而无人察觉（A04 的判据被悄悄削弱）。"
            "反向锁死靠 `__subclasses__()`，不靠维护第二份名单",
    ),
    SpanMutation(
        id="A17", path=G,
        anchor="    raise SyncEndpointGuardError(\n"
               "        f\"{type(exc).__name__} 未登记 HTTP 映射 —— guard 的拒绝分型必须逐条登记\"\n"
               "        f\"（当前登记：{sorted(f.__name__ for f in _REFUSAL_STATUS)}）\"\n"
               "    )",
        new="    return 500",
        want=_off("TestGuardPhaseChain::test_http_mapping_is_closed"),
        why="兜底 500 ⇒ 「新增一个拒绝类型但忘了登记」表现为平台故障，真正的原因"
            "（授权分型漏登记）永远不会被发现。这是 fail-open 的一种：状态码看起来"
            "「安全」，但分型信息全丢",
    ),
    SpanMutation(
        id="A18", path=G,
        anchor="        if authorize is None:\n"
               "            raise SyncEndpointGuardError(\n"
               "                \"action 重验回调是必填依赖：可选即等于默认放行\"\n"
               "            )",
        new="        if authorize is None:\n"
            "            authorize = lambda _scope: True  # noqa: E731",
        want=_off("TestGuardPhaseChain::test_both_probe_and_authorizer_are_mandatory"),
        why="「没配就放行」是 fail-open 的经典形态：忘记接线时不报错，而是静默给出一个"
            "恒真的 action 授权。构造期失败才能让漏接线在**部署前**暴露",
    ),
    # 🔴 刻意**不**登记的一条候选：把 `phases=tuple(phases) + (action_authorized,)` 换成
    # `phases=REQUIRED_PHASES`。在当前实现里 `enforce` 是一条线性路径、四个阶段都必然
    # 已经走过，所以两种写法**语义等价** ⇒ 那是「无效变异」，判 GREEN 也不代表守卫缺陷。
    # 登记它只会在报告里制造一条无法归因的 GREEN。等哪天 enforce 出现提前 return 的分支，
    # 它才成为一条有效变异，届时再加。
    SpanMutation(
        id="A20", path=G,
        anchor="        if not hmac.compare_digest(mac, self._mac(body)):",
        new="        if False:",
        want=_off("TestSignedScopeClaim::test_bad_claims_share_the_404_family[forged]"),
        why="不验签 ⇒ 任何人可以自造一份 base64 body 指向别人的 recovery case 并下载其"
            "incoming artifact。签发端仍然「看起来安全」（照旧签名），这就是"
            "「没有消费方验签的签名等于死代码」的另一半",
    ),
    SpanMutation(
        id="A21", path=G,
        anchor="        if (\n"
               "            claim.project_id != project_id\n"
               "            or claim.wp_id != wp_id\n"
               "            or claim.entry_id != str(entry_id)\n"
               "            or claim.user_id != request.user_id\n"
               "        ):",
        new="        if False:",
        want=_pg("TestDownloadOnlyKeepsAllThreeEntitiesAtZero::"
                 "test_a_claim_from_another_wp_scope_is_404"),
        why="claim 与 route scope 不做三向比对 ⇒ 在 A 项目拿到的合法 claim 可以在 B 项目"
            "的 route 上复用（验签会通过，因为签名本身是真的）。这条是横向越权，"
            "不是伪造 —— 所以 A20 抓不到它",
        wants=(_off("TestSignedScopeClaim::test_bad_claims_share_the_404_family[cross-wp]"),),
    ),
    SpanMutation(
        id="A22", path=G,
        anchor="        if self._claims is None:\n"
               "            refusals.append(\n"
               "                ScopeClaimMismatchError(\n"
               "                    \"请求携带 signed scope claim，但 guard 未装配 ScopeClaimCodec —— \"\n"
               "                    \"未验签的 claim 一律不得放行\"\n"
               "                )\n"
               "            )\n"
               "            return",
        new="        if self._claims is None:\n"
            "            return",
        want=_off("TestSignedScopeClaim::test_a_claim_without_a_codec_is_never_waved_through"),
        why="未装配 codec 时静默跳过验签 ⇒ 只要部署里漏了 secret，携带任意 claim 的请求"
            "都被当作「claim 校验通过」。这是「缺配置即放行」，比不验签更隐蔽："
            "有 codec 的环境全绿",
    ),
    SpanMutation(
        id="A23", path=G,
        anchor="        scope.assert_complete()\n"
               "        claim = ScopeClaim(",
        new="        claim = ScopeClaim(",
        want=_off("TestSignedScopeClaim::test_mint_requires_a_complete_guarded_scope"),
        why="签发面不再要求 scope 已过完整 guard ⇒ 在任何半途状态（例如只到阶段 ②）都能"
            "铸出一份**签名合法**的 claim，而它之后每次验签都通过。签发面的漏洞无法由"
            "消费面补救",
    ),
    SpanMutation(
        id="A24", path=G,
        anchor="        if request.claim_purpose is not None and claim.purpose != str(\n"
               "            request.claim_purpose\n"
               "        ):",
        new="        if False:",
        want=_off("TestSignedScopeClaim::test_bad_claims_share_the_404_family[wrong-purpose]"),
        why="claim 可跨用途复用 ⇒ 「最小权限短期凭证」失去最小权限那一半：为下载签发的"
            "claim 能拿去过别的端点。与 A21（跨 scope）分型：同一 scope、同一用户，"
            "只是用途不同",
    ),
    # ═══════════════════════════════════════════════════════════════════
    # B. router：显式 scope 路由、统一 envelope、真实调用链、legacy 委派
    # ═══════════════════════════════════════════════════════════════════
    SpanMutation(
        id="A26", path=AR,
        anchor="                    WorkpaperSyncScopeIndex.retired_at.is_(None),",
        new="",
        want=_pg("TestScopeTombstone::test_a_retired_resource_reads_like_a_nonexistent_one"),
        why="scope index 查询不过滤 `retired_at` ⇒ 已退役 child 的 opaque id 仍能通过 guard，"
            "「退役」退化成一个只写不读的字段。AC 10.6：tombstone 永久保留只为**防 id 复用**，"
            "用户侧必须与「不存在」同一个 404 oracle。本条锚在 Task 10 的仓储上"
            "（跨任务文件），目的是证明**本任务的 tombstone 判据不是空转** —— "
            "「行还在、retired_at 已设」这两条形态判据在本变异下仍然全绿",
    ),
    SpanMutation(
        id="B01", path=R,
        anchor="USER_SYNC_PREFIX = (\n"
               "    \"/api/projects/{project_id}/workpapers/{wp_id}/sync/entries/{entry_id:path}\"\n"
               ")",
        new="USER_SYNC_PREFIX = (\n"
            "    \"/api/projects/{project_id}/workpapers/{wp_id}/sync/entries/{entry_id}\"\n"
            ")",
        want=_off("TestRouterShape::test_the_entry_id_segment_uses_the_path_converter"),
        why="**回归变异**（真库首轮实测的真实缺陷）：默认转换器是 `[^/]+`，而 manifest 的"
            "186 条 entry_id **全部含 `/`**（最深四段）⇒ 每一个端点在生产上恒 404，"
            "而且是 Starlette 自己的 `{\"detail\":\"Not Found\"}`，连 guard 都进不去。"
            "`path.startswith(USER_SYNC_PREFIX)` 在两种转换器下都成立 ⇒ 形态判据全绿",
        wants=(
            _off("TestRouterShape::test_a_real_slashed_entry_id_routes"),
            _pg("TestUnifiedNotFoundOracle::test_all_five_causes_return_404"),
        ),
    ),
    SpanMutation(
        id="B02", path=R,
        anchor="    return HTTPException(status_code=404, detail=EXTERNAL_NOT_FOUND_DETAIL)",
        new="    return HTTPException(status_code=404, detail=\"资源不存在或无权访问\")",
        want=_off("TestUnifiedEnvelopes::test_the_404_body_is_the_platform_wide_detail"),
        why="404 文案偏离平台统一不可见响应 ⇒ 同步域的 404 与平台其他 404 可区分，"
            "而「资源不存在**或**无权访问」这类措辞本身就在暗示两种情况的存在。"
            "Property 45 要的是逐字节相同",
        wants=(_pg("TestUnifiedNotFoundOracle::"
                   "test_the_body_is_the_platform_wide_unified_detail"),),
    ),
    SpanMutation(
        id="B03", path=R,
        anchor="    return HTTPException(\n"
               "        status_code=409,\n"
               "        detail={\n"
               "            \"error_code\": error_code\n"
               "            or str(getattr(exc, \"error_code\", \"\") or \"conflict\"),\n"
               "            \"message\": str(exc),\n"
               "        },\n"
               "    )",
        new="    return HTTPException(\n"
            "        status_code=409,\n"
            "        detail={\n"
            "            \"error_code\": error_code\n"
            "            or str(getattr(exc, \"error_code\", \"\") or \"conflict\"),\n"
            "            \"message\": str(exc),\n"
            "            \"existing_request_id\": str(getattr(exc, \"existing_id\", \"\")),\n"
            "        },\n"
            "    )",
        want=_off("TestUnifiedEnvelopes::test_the_409_body_carries_no_resource_identifier"),
        why="AC 4.1 明文：跨 participant 复用同 Idempotency-Key「不得返回已有标识」。"
            "把旧 request id 放进冲突响应 = 把别人的资源 id 交给冲突方，而只断言"
            "「返回了 409」的判据全绿",
    ),
    SpanMutation(
        id="B04", path=R,
        anchor="    entry_id: str,\n"
               "    version_id: str,\n"
               "    payload: Mapping[str, Any] = Body(...),",
        new="    entry_id: str,\n"
            "    version_id: uuid.UUID,\n"
            "    payload: Mapping[str, Any] = Body(...),",
        want=_off("TestRouterShape::test_rollback_takes_an_opaque_version_id_typed_as_str"),
        why="声明成 UUID ⇒ `/versions/11/rollback` 被 FastAPI 的请求校验拦成 **422**，"
            "于是「numeric revision 不得作 route key」由框架顺手实现、本 spec 无从证伪，"
            "而且 422 与统一 404 oracle 不同桶（攻击者据此区分「格式错」与「不存在」）",
        wants=(_pg("TestUnifiedNotFoundOracle::"
                   "test_numeric_revision_as_a_route_key_is_404_not_422"),),
    ),
    SpanMutation(
        id="B05", path=R,
        anchor="    room_id: uuid.UUID = Query(...),\n"
               "    generation: int = Query(...),",
        new="    room_id: uuid.UUID | None = Query(default=None),\n"
            "    generation: int | None = Query(default=None),",
        want=_off("TestRouterShape::test_recovery_list_requires_room_and_generation"),
        why="AC 10.6 明文「recovery list 明确 entry/room scope」。可选化后「列出这个 wp "
            "下所有 case」成为存在性泄露面：不带 room 也能问出「有没有 case」",
        wants=(_pg("TestRecoveryListRequiresExplicitRoomAndGeneration::"
                   "test_omitting_generation_is_refused"),),
    ),
    SpanMutation(
        id="B32", path=R,
        anchor="    idempotency_key: str = Header(..., alias=\"Idempotency-Key\"),",
        new="    idempotency_key: str = Header(default=\"\", alias=\"Idempotency-Key\"),",
        want=_off("TestRouterShape::"
                  "test_the_idempotency_key_is_a_required_server_side_header"),
        why="把 Idempotency-Key 改成可选 ⇒ 复合幂等键 `(room, generation, participant, "
            "kind, key)` 的最后一项对所有请求恒为空串 ⇒ **同一 participant 的任意两次 "
            "forcesave 折叠成一次**（第二次拿到第一次的 request/operation，真实编辑内容"
            "再也不会被 correlate）。没有任何功能测试会因此失败 —— 这正是 bullet 1 说的"
            "「不得由前端约定代替」。`allow_multi` 一次改掉全部 7 个端点，"
            "因为该判据本身是端点集合级的（双向等值 + 逐个 required）",
        allow_multi=True,
        multi_reason="7 个幂等端点各自声明同一行；判据是集合级的（哪一个变可选都必须红），"
                     "逐个变异只会得到 7 条完全同因的记录",
    ),
    SpanMutation(
        id="B06", path=R,
        anchor="    indexed_generation = scope.generation_of(room_ref)\n"
               "    if indexed_generation is None or int(indexed_generation) != int(generation):",
        new="    indexed_generation = scope.generation_of(room_ref)\n"
            "    if False:",
        want=_pg("TestRecoveryListRequiresExplicitRoomAndGeneration::"
                 "test_a_generation_that_does_not_match_the_scope_index_is_404"),
        why="显式 generation 不与 scope index 的非敏感归属核对 ⇒ 客户端可以用任意 "
            "generation 值配合一个合法 room 去问 case（跨代际探测）。"
            "scope row 里的 generation 是非敏感字段，核对它不需要读 room 业务行",
    ),
    SpanMutation(
        id="B07", path=R,
        anchor="    await _apply_durable_incoming(db, outcome=outcome)\n"
               "    return {\"error\": 0}",
        new="    return {\"error\": 0}",
        want=_off("TestOoToHtmlHasARealProductionCallChain::"
                  "test_the_callback_handler_reaches_that_function"),
        why="Task 26 欠账的本体：删掉这一句后 incoming durable 之后**没人消费它**，"
            "整条 OO→HTML 方向是死的 —— 而 callback 照旧 `error=0`，OO 侧看起来一切正常，"
            "用户切回 HTML 只是重读旧数据库（这正是本 spec 要收口的假双向形态）",
    ),
    SpanMutation(
        id="B08", path=R,
        anchor="    result = await coordinator.apply_durable_incoming(",
        new="    result = await _noop_apply(  # noqa: F821",
        want=_off("TestOoToHtmlHasARealProductionCallChain::"
                  "test_apply_durable_incoming_is_really_called"),
        why="接线「搬去别处」：调用点还在、函数还在，只是不再落到 coordinator 上。"
            "`merge.RETIRED_DEFERRALS` 那种登记表判据查不出这个形态 —— 它只证明"
            "「登记了一个期望消费方」，不证明「真的调了」",
    ),
    SpanMutation(
        id="B09", path=R,
        anchor="    if outcome.response_error != 0:\n"
               "        return {\"error\": int(outcome.response_error)}",
        new="    if False:\n"
            "        return {\"error\": int(outcome.response_error)}",
        want=_off("TestOoToHtmlHasARealProductionCallChain::"
                  "test_the_callback_handler_checks_the_outcome_instead_of_absence_of_exception"),
        why="`handle_callback` 刻意不抛（AC 5.7/5.8 —— durable 后返非零会让 OO 丢件），"
            "所以「没抛异常」不等于成功。不读 `response_error` ⇒ durable **前**的失败"
            "（鉴权/下载/OOXML 校验失败）被当成 ack=0，OO 于是丢件（Task 4 实测它不重投）",
    ),
    SpanMutation(
        id="B10", path=R,
        anchor="    if result.result is not OoToHtmlResult.applied:\n"
               "        logger.warning(",
        new="    if False:\n"
            "        logger.warning(",
        want=_off("TestOoToHtmlHasARealProductionCallChain::"
                  "test_the_apply_step_checks_result_instead_of_absence_of_exception"),
        why="coordinator 在 durable **之后**也刻意不抛（失败留在 operation/recovery 上）。"
            "不读 `outcome.result` ⇒ apply 失败被静默当成成功，连日志都没有 —— "
            "Task 27 就是被同一形态咬到才加了 `assert_resolve_apply_landed`",
    ),
    SpanMutation(
        id="B11", path=R,
        anchor="    return str(scope.action) in _KNOWN_ACTIONS",
        new="    return True",
        want=_off("TestRouterDoesNotReimplementServiceLogic::"
                  "test_an_unknown_action_name_is_refused"),
        why="action 词汇表失效 ⇒ `_guard(action=\"reslove_conflicts\")` 这类笔误变成一个"
            "「未登记的写 action」：`workflow_locked` 白名单查不到它 ⇒ 归档下 403、"
            "其他情况一路放行，而端到端测试照样通过",
    ),
    SpanMutation(
        id="B12", path=R,
        anchor="            read_only_actions=_READ_ONLY_ACTIONS,\n"
               "        ),",
        new="        ),",
        want=_off("TestRouterDoesNotReimplementServiceLogic::"
                  "test_the_guard_is_built_with_the_read_only_action_set"),
        why="名单存在但没注入 guard = additive 死代码（假绿第①源）。后果与 A13 相同"
            "（归档底稿连 timeline 都 403），但根因在装配处 —— 只看 guard 内部实现的判据"
            "抓不到它",
        wants=(_pg("TestForbiddenIsDistinctFromNotFound::"
                   "test_workflow_lock_still_allows_reads"),),
    ),
    SpanMutation(
        id="B13", path=R,
        anchor="        \"read_timeline\",\n"
               "        \"download_recovery_artifact\",\n"
               "    }\n"
               ")",
        new="        \"read_timeline\",\n"
            "        \"download_recovery_artifact\",\n"
            "        \"forcesave\",\n"
            "    }\n"
            ")",
        want=_off("TestRouterDoesNotReimplementServiceLogic::"
                  "test_read_only_actions_match_the_read_endpoints_exactly"),
        why="写 action 落进只读白名单 ⇒ workflow 锁定（归档/复核通过）下 forcesave 被放行，"
            "已定稿底稿可被 OO 回写覆盖。判据必须是**双向等值**（读端点集合 ↔ 名单），"
            "单向包含查不出多登记",
    ),
    SpanMutation(
        id="B14", path=R,
        anchor="    if status == 404:\n"
               "        return _not_found()",
        new="    if False:\n"
            "        return _not_found()",
        want=_off("TestServiceErrorMapping::"
                  "test_404_family_of_service_errors_uses_the_unified_envelope"),
        why="service 域的 404（跨 scope 读 operation、content version 不存在）不走统一"
            "envelope ⇒ 响应体里带上 error_code/message，与「不存在」可区分。"
            "guard 侧的 404 仍然统一，所以只有 service 映射那一条判据会红",
    ),
    SpanMutation(
        id="B15", path=R,
        anchor="            code = str(cls.error_code)",
        new="            code = (\n"
            "                \"operation_scope_not_visible\"\n"
            "                if cls.__name__ == \"OperationScopeNotVisibleError\"\n"
            "                else str(cls.error_code)\n"
            "            )",
        want=_off("TestServiceErrorMapping::"
                  "test_every_mapped_error_code_really_exists_in_the_sync_domain"),
        why="**回归变异**（真实缺陷，第一版手写字面量 16 条里 5 条拼错）：映射表的键与真实"
            "`error_code` 不符 ⇒ `OperationScopeNotVisibleError` 落回默认 422 ⇒ "
            "「跨 scope 读 operation」与「不存在」在响应上可区分 = Property 45 的存在性"
            "预言机。拼错在功能测试里完全看不见（每条路径都还是「返回了一个错误」）",
        wants=(_off("TestServiceErrorMapping::"
                    "test_404_family_of_service_errors_uses_the_unified_envelope"),),
    ),
    SpanMutation(
        id="B16", path=R,
        anchor="            if code in table and table[code] != status:\n"
               "                raise SyncDomainError(",
        new="            if False:\n"
            "                raise SyncDomainError(",
        want=_off("TestServiceErrorMapping::"
                  "test_the_mapping_table_refuses_contradictory_registration"),
        why="同一 error_code 登记两个 status 时「后写的赢」⇒ 映射结果取决于表里的书写顺序。"
            "🔴 这条分支在真实表上恒不触发，从测试侧本来**不可达**（其变异必永久 GREEN）"
            "—— 所以本任务给 `_build_error_code_status` 开了只给判据用的 `spec` 注入口，"
            "让判据能真的喂一份矛盾登记。这就是「守卫缺陷」与「代码没问题」的区别",
    ),
    SpanMutation(
        id="B17", path=R,
        anchor="        raise HTTPException(\n"
               "            status_code=422,\n"
               "            detail={\n"
               "                \"error_code\": str(getattr(exc, \"error_code\", \"adapter_not_ready\")),\n"
               "                \"message\": str(exc),\n"
               "            },\n"
               "        ) from exc",
        new="        return None",
        want=_pg("TestFlushDoesNotAdvanceRevision::"
                 "test_an_entry_without_an_approved_adapter_fails_visible"),
        why="registry 当前**刻意**零注册（Tasks 40~57/62~64 逐 entry 接线）。兜底 None 会把"
            "「这个 entry 还没做 adapter」表现成「同步成功但什么都没变」——"
            "本 spec 引言里点名的假双向形态",
        wants=(_pg("TestOpaqueVersionIdRollback::"
                   "test_rollback_without_a_registered_adapter_fails_visible"),),
    ),
    SpanMutation(
        id="B18", path=R,
        anchor="    if kind != RequestKind.forcesave.value:",
        new="    if False:",
        want=_pg("TestForbiddenIsDistinctFromNotFound::"
                 "test_client_may_not_initiate_a_close_capture"),
        why="AC 4.4 / 4.10：`close_capture` 只能由 room arbiter 在 room lock 内 CAS 产生"
            "（generation 内 exactly-one）。允许客户端直接发起 ⇒ 两个客户端各造一个 "
            "capture，partial unique 只能保证 at-most-one，剩下那个的 durable 内容丢失",
    ),
    SpanMutation(
        id="B19", path=R,
        anchor="    scope = await _guard(\n"
               "        svc,\n"
               "        project_id=project_id,\n"
               "        wp_id=wp_id,\n"
               "        entry_id=entry_id,\n"
               "        action=\"download_only\",",
        new="    await svc.session.rollback()\n"
            "    scope = await _guard(\n"
            "        svc,\n"
            "        project_id=project_id,\n"
            "        wp_id=wp_id,\n"
            "        entry_id=entry_id,\n"
            "        action=\"download_only\",",
        want=_off("TestGuardIsTheFirstAwaitInEveryHandler::"
                  "test_every_user_handler_awaits_the_guard_first"),
        why="在 guard 之前插一次 await（`rollback()` 在干净 session 上是无操作 ⇒ **行为"
            "完全不变**）。这正是 authorization-before-resource 会被慢慢侵蚀的方式："
            "有人在 guard 前加一句「顺手」的 await，功能测试全绿，而下一个人会在同一位置"
            "加一次业务读",
    ),
    SpanMutation(
        id="B20", path=R,
        anchor="            ctx = await enforce_wp_gate(",
        new="            ctx = await _local_visibility_check(  # noqa: F821",
        want=_off("TestRegistrationAndLegacyDelegation::"
                  "test_the_probe_reuses_the_platform_visibility_gate"),
        why="可见性抄第二份 ⇒ 同步域比平台门更宽松（委派、历史版本、reviewer 白名单、"
            "跨项目这些规则住在 `wp_visibility` 域）。「偶尔不一致」不是主要风险，"
            "横向越权入口才是",
    ),
    SpanMutation(
        id="B21", path=REG,
        anchor="    app.include_router(wp_sync, tags=[\"渲染\"])",
        new="    app.include_router(wp_sync, tags=[\"渲染\"], dependencies=[])",
        want=_off("TestRegistrationAndLegacyDelegation::"
                  "test_both_routers_are_registered_outside_the_auto_gate_loop"),
        why="给 sync router 挂上 router-level 依赖 ⇒ 那个 gate 会在 handler **之前**跑完"
            "visibility，把 scope-index 与 visibility 的先后调换（AC 10.6 明文不可交换）。"
            "端点行为在多数场景下不变，只有顺序判据会红",
    ),
    SpanMutation(
        id="B22", path=I,
        anchor="from app.services.workpaper_sync.oo_to_html import OoToHtmlCoordinator\n",
        new="",
        want=_off("TestPackageExportsTheProductionSurface::"
                  "test_the_package_init_really_imports_the_wave2_services"),
        why="本包 `__init__` 原本一条 import 都没有，这正是 Tasks 25~27 守卫辐射面几乎为零"
            "的原因（改本包任何文件都不牵动别的测试）。删掉 import 面 ⇒ "
            "「谁是本包的对外形态」又只剩 docstring 里的自述",
    ),
    SpanMutation(
        id="B23", path=L,
        anchor="    if _has_room_bound_callback_query(request):\n"
               "        return await _delegate_room_bound_callback(request, db)",
        new="    if False:\n"
            "        return await _delegate_room_bound_callback(request, db)",
        want=_off("TestRegistrationAndLegacyDelegation::"
                  "test_the_legacy_callback_delegates_room_bound_requests"),
        why="新式（四项绑定）callback 落回 legacy 分支 ⇒ 被按 sheet 名整文件覆盖，"
            "既不建 delivery、也不做三方 merge。AC 「旧 config/callback URL 只委派新服务」"
            "直接落空，而 legacy 路径的既有测试全绿（它们本来就走 legacy）",
    ),
    SpanMutation(
        id="B24", path=L,
        anchor="    from app.services.workpaper_sync.callback_route import URL_BOUND_PARAMS\n"
               "\n"
               "    query = request.query_params\n"
               "    return all(str(query.get(name) or \"\").strip() for name in URL_BOUND_PARAMS)",
        new="    query = request.query_params\n"
            "    names = (\"room_id\", \"generation\", \"doc_key\", \"route_credential_id\")\n"
            "    return all(str(query.get(name) or \"\").strip() for name in names)",
        want=_off("TestRegistrationAndLegacyDelegation::"
                  "test_the_delegation_predicate_reads_the_single_source_of_bound_params"),
        why="委派判据自写一份参数名清单 ⇒ 新增一项 URL 绑定时它静默漏掉新式 callback，"
            "于是新式回调落进 legacy 分支（= B23 的后果），而两边的单测都绿。"
            "单一真源是 `callback_route.URL_BOUND_PARAMS`（`assert_url_binding` 用的同一组）",
    ),
    SpanMutation(
        id="B25", path=L,
        anchor="    return all(str(query.get(name) or \"\").strip() for name in URL_BOUND_PARAMS)",
        new="    return any(str(query.get(name) or \"\").strip() for name in URL_BOUND_PARAMS)",
        want=_off("TestRegistrationAndLegacyDelegation::"
                  "test_the_delegation_is_gated_on_all_four_bound_params"),
        why="`all` → `any` ⇒ 只带 `room_id` 的 legacy URL 也被委派到新服务，"
            "而它没有 route token/doc_key 绑定 ⇒ 新服务必拒 ⇒ legacy 编辑器的保存直接失效。"
            "形态判据（读了单一真源）在这条变异下仍然全绿",
    ),
    SpanMutation(
        id="B30", path=R,
        anchor="        return {\"error\": 1}",
        new="        return {\"error\": 0}",
        want=_pg("TestServiceScopeCallbackRoute::"
                 "test_a_pre_durable_rejection_returns_a_non_zero_ack"),
        why="durable **前**的失败（route 凭证不符、下载失败、OOXML 校验不过）回 ack=0 ⇒ "
            "OO 认为已保存、不再重投（Task 4 实测），文件永久丢失。AC 5.7 的方向与 durable "
            "**后**恰好相反（后者必须回 0），所以这两处不能共用一个返回值",
    ),
    SpanMutation(
        id="B31", path=R,
        anchor="@public_router.post(\"/api/workpaper-sync/rooms/{room_id}/onlyoffice-callback\")",
        new="@public_router.post(\"/api/workpaper-sync/rooms/{room_id}/oo-callback\")",
        want=_off("TestRouterShape::test_the_callback_route_is_a_service_scope_route"),
        why="路径不再含 `onlyoffice-callback` ⇒ 命不中 "
            "`ResponseWrapperMiddleware._SKIP_CONTAINS` ⇒ `{\"error\": N}` 被 "
            "`{code,message,data}` 包一层 ⇒ OO 读不到 error 字段，把失败当成功。"
            "真库侧同时红（端点路径变了 ⇒ 404 ⇒ 「已挂载」判据失效），"
            "两侧合起来证明「顶层信封」不是只靠子串判的",
        wants=(
            _off("TestRouterShape::test_response_wrapper_really_skips_that_path"),
            _pg("TestServiceScopeCallbackRoute::"
                "test_the_route_is_mounted_and_not_a_user_404"),
        ),
    ),
    SpanMutation(
        id="B26", path=P,
        anchor="    \"room_latest_durable_sequence\",\n"
               "    \"conflict_set_digest\",\n"
               ")",
        new="    \"room_latest_durable_sequence\",\n"
            ")",
        want=_off("TestResolvePayloadTranslation::"
                  "test_every_required_fence_field_is_really_required"),
        why="必填清单少登记一项 ⇒ 那一项变成「可缺省」，服务端替客户端声明「我看到的就是"
            "当前值」，fence 少比一项。AC 8.5 的八项乐观锁里少比 `conflict_set_digest` "
            "在功能测试里完全看不出来（裁决照样成功）",
    ),
    SpanMutation(
        id="B27", path=P,
        anchor="                stable_field_key=str(row.stable_field_key),",
        new="                stable_field_key=str(\n"
            "                    item.get(\"stable_field_key\") or row.stable_field_key\n"
            "                ),",
        want=_off("TestResolvePayloadTranslation::"
                  "test_the_stable_key_comes_from_the_server_row_not_the_request"),
        why="裁决落点改由客户端声明 ⇒ 审计师点的「取 incoming」可以被改一个字符落到另一个"
            "字段上（AC 8.3 要求服务端自行校验）。conflict_id 仍然合法、响应仍然 200，"
            "只有「stable key 来自服务端行」这条判据会红",
    ),
    SpanMutation(
        id="B28", path=P,
        anchor="            if \"value\" not in item:",
        new="            if item.get(\"value\") is None:",
        want=_off("TestResolvePayloadTranslation::"
                  "test_manual_with_an_explicit_null_means_delete_not_missing"),
        why="「缺 value 键」与「显式 value=null」是两件事：后者是 "
            "`ValueEnvelope(present=False)`，即「合并为删除」这一**合法裁决**。"
            "改成 `is None` 后审计师无法把一个字段裁决成删除（被当成没填而 422）",
    ),
    SpanMutation(
        id="B29", path=P,
        anchor="        if row is None:\n"
               "            raise UnknownConflictIdError(",
        new="        if row is None:\n"
            "            continue\n"
            "        if False:\n"
            "            raise UnknownConflictIdError(",
        want=_off("TestResolvePayloadTranslation::"
                  "test_an_unknown_conflict_id_is_its_own_refusal"),
        why="不属于本 canonical primary 的 conflict_id 被静默跳过 ⇒ ①用别人的 conflict_id "
            "试探不再报错（存在性预言机的输入面）②「已解决全部冲突」的判定会把被跳过的"
            "那条当作未提交，resolve 结果与审计师所见不符",
    ),
]

#: 覆盖面分母 —— 本任务全部守卫文件。少登记一个文件，那个文件里的判据就不参与覆盖核算。
GUARD_FILES: dict[str, str] = {
    "test_task28_sync_router.py": "Task 28 离线：guard 阶段链/统一 envelope/路由形态/调用链",
    "test_task28_sync_router_pg.py": "Task 28 真库：404 oracle、三实体计数、scope tombstone",
}

PYTEST_ARGS = [
    "backend/tests/workpaper_sync/test_task28_sync_router.py",
    "backend/tests/workpaper_sync/test_task28_sync_router_pg.py",
    "-q",
    "--tb=no",
    # 🔴 `-rE` 不可省：语法错误的替换体会让整文件**收集失败**，此时 `FAILED` 一行都不会
    # 打印 ⇒ 差集为空 ⇒ 判 GREEN。Task 27 的 H01 正是这样把脚本缺陷记成了「守卫缺陷」
    # （指纹是 4.2s vs 正常 66s 的运行时长）。`ERROR` 行进失败集合后它会如实变成 RED。
    "-rfE",
    "-p",
    "no:randomly",
]

if __name__ == "__main__":
    raise SystemExit(
        run_cli(
            mutations=MUTATIONS,
            guard_files=GUARD_FILES,
            repo=REPO,
            pytest_args=PYTEST_ARGS,
            description="Task 28 显式 scope router / 固定 guard 变异检验",
            # 147 = 100 离线 + 47 真库（实测 2026-08-28）。离线数含变异检验实测后补的五条：
            # A07 判 GREEN ⇒ +3 个跨 kind 参数 +1 条「两支不得共用 error_code」；
            # B26 判 GREEN ⇒ +1 条「必填清单 ↔ 域字段双向等值」（原判据是自证重言式）；
            # 另 +1 条「Idempotency-Key 必须服务端强制」（此前无任何判据，见 B32）。
            # 真库数含 +4 条 `TestServiceScopeCallbackRoute`：新 callback 端点此前只有 AST
            # 形态判据，没有任何判据证明它**真的挂上了**（legacy 侧 31 条红正是这个形态）。
            baseline_passed=147,
        )
    )
