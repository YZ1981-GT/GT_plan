r"""Task 76 变异检验 —— projection definition provisioner 与 candidate 受控 attach 的守卫强度。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 4 Task 76
被检验的守卫：
* ``backend/tests/workpaper_sync/test_task76_projection_definition_provisioner.py``（离线）
* ``backend/tests/workpaper_sync/test_task76_projection_definition_provisioner_pg.py``（真实 PG）

## 为什么每条变异都不是无效变异

本任务的三类最贵缺陷各自都有对应变异：

1. **伪造供给被放行** —— 把五种形态的任一条判据短路，守卫必须打红
   （M01~M06、M13、M17）；
2. **幂等退化成「每次都发一份新的」** —— 把复用查询的 digest 判据改成永不命中，
   真库上第二次 provision 就会造出第二份同内容 definition/bundle（M07、M08）；
3. **additive 死代码 / 越权** —— 把 attach 的状态、作用域、contract↔bundle 一致性判据
   短路，或把宿主脚本的 `ensure()`/`commit()` 摘掉，守卫必须打红（M09~M12、M14~M16、
   M18~M20）。

另有两条落在 **DB 层**（V153 的 append-only 触发器与 attach 边 CHECK）：应用层承诺
不算判据，触发器被改成 `BEFORE INSERT` 之后 `UPDATE`/`DELETE` 就能改写审计轨（M21、M22）。

## 用法（仓库根；PATH 上的 `python` 可能指向坏掉的解释器）

    .\.venv\Scripts\python.exe backend/scripts/diagnose/mutate_task76_projection_definition_provisioner_guards.py --list
    .\.venv\Scripts\python.exe backend/scripts/diagnose/mutate_task76_projection_definition_provisioner_guards.py --run M01,M02
    .\.venv\Scripts\python.exe backend/scripts/diagnose/mutate_task76_projection_definition_provisioner_guards.py --check-anchors

🔴 **禁后台执行**（孤儿 python + 前台同时变异 ⇒ RestoreFailed）；**绝不 `--restore`**。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/scripts

from _mutation_kit import Mutation, run_cli  # noqa: E402

REPO = Path(__file__).resolve().parents[3]

PP = "backend/app/services/workpaper_sync/projection_provisioning.py"
RP = "backend/app/services/workpaper_sync/repository.py"
MODELS = "backend/app/services/workpaper_sync/models.py"
SCRIPT = "backend/scripts/fix/fix_task76_provision_projection_definitions.py"
V153 = "backend/migrations/V153__workpaper_representation_candidate_attach_event.sql"

#: 🔴 kit 按**短 nodeid**（basename::类::方法）匹配新增失败集合 —— 带
#: `backend/tests/...` 前缀会让「实际打红的正是预期那条」被误判 WRONG-TEST。
_T = "test_task76_projection_definition_provisioner.py"
_G = "test_task76_projection_definition_provisioner_pg.py"
_FORGED = f"{_T}::TestForgedSupplyIsFailClosed"
_OPAQUE = f"{_T}::TestOpaqueChannelStaysClosed"
_SURFACE = f"{_T}::TestForbiddenSurfacesAndFailOpen"
_ATTACH = f"{_T}::TestCandidateAttachContract"
_REUSE = f"{_T}::TestIdempotentReuseScale"
_HOST = f"{_T}::TestConsumptionHost"
_V153T = f"{_T}::TestV153Shape"
_PROP = f"{_T}::TestProperties"
_PGROWS = f"{_G}::TestSupplyTablesGetRealRows"
_PGIDEM = f"{_G}::TestIdempotentRerun"
_PGATTACH = f"{_G}::TestControlledAttach"
_PGFORGED = f"{_G}::TestForgedIdentityAndFinalizeGate"

MUTATIONS: list[Mutation] = [
    # ═══ 五种伪造供给：每条判据各一条变异（AC 2.3 / 3.3 / 6.2 / 6.10）═══════════
    Mutation(
        id="M01", side="be", path=PP, kind="replace",
        anchor='    if review_status != "reviewed":',
        new="    if False:",
        want=f"{_FORGED}::test_form5_generator_candidate_cannot_pass_as_reviewed_contract",
        why="⑤ generator 候选冒充已人工审核契约。`definitions.validate_contract_payload` "
            "**不看** `review_status`，所以这一格只有 provisioner 自己在守；短路它之后把 "
            "generator 骨架直接发布成 per-entry 生产契约就可行了（AC 3.3 / 12.1）。"
            "改 `if` 而不是删 `raise`：要测的是「判断成立却不拦」这一形态",
    ),
    Mutation(
        id="M02", side="be", path=PP, kind="replace",
        anchor="    if declared_contract_id != supply.contract_id:",
        new="    if False:",
        want=f"{_FORGED}::test_form5_generator_candidate_cannot_pass_as_reviewed_contract",
        why="⑤ 的另一半：`review_status=reviewed` 但 contract_id 是**别的 entry** 的契约。"
            "短路后 A entry 的已审契约可被发布到 B entry ⇒ 跨 entry 复用 contract"
            "（Tasks 40~57 明令禁止），且 bundle digest 会指向错的语义身份",
    ),
    Mutation(
        id="M03", side="be", path=PP, kind="replace",
        anchor="        if child is None:",
        new="        if False:",
        want=f"{_PGFORGED}::test_forged_definition_uuid_is_refused_before_insert",
        wants=(f"{_PROP}::test_property_28_forged_identity_fails_closed",),
        why="① 自造 uuid。这条是把 `repository.assert_bundle_usable` 的 post-insert 判据"
            "提到 publish **之前**的那一格；短路后一个库里根本不存在的 definition id 会进入 "
            "bundle canonical bytes，事后只能靠 FK 报错（而 slot ref 是 varchar，没有 FK）",
    ),
    Mutation(
        id="M04", side="be", path=PP, kind="replace",
        anchor="    if model is not AuthorityModel.projection_contract:",
        new="    if False:",
        want=f"{_OPAQUE}::test_projection_provisioner_refuses_non_projection_authority",
        why="两条通道混用。`validate_bundle_slots` 对 opaque/custom 形态**允许** typed null "
            "marker，因此把 opaque authority 喂进本判据函数时它不会拒 —— 这条 guard 就是"
            "把「通道归属」从「调用顺序恰好经过 load_projection_supply」的偶然性变成结构判据",
    ),
    Mutation(
        id="M05", side="be", path=PP, kind="replace",
        anchor="    normalized = normalize_bundle_slot_map(slots)",
        new="    normalized = dict(slots)",
        want=f"{_FORGED}::test_form3_empty_or_all_zero_hash_is_rejected",
        wants=(
            f"{_FORGED}::test_form4_slot_omission_or_sql_null_is_rejected",
            f"{_PROP}::test_property_28_drift_fails_closed_with_first_illegal_slot",
        ),
        why="③ 空串/全零 hash 与 ④ slot omission / SQL NULL 的单点都在 "
            "`definitions.normalize_bundle_slot_map`。绕过它（直接 `dict(slots)`）之后"
            "缺键与非法 digest 都会带进 canonical bytes —— 这条同时证明 provisioner 是"
            "**委托**而不是自己抄了一份检查",
    ),
    Mutation(
        id="M06", side="be", path=MODELS, kind="replace",
        anchor="    if am is AuthorityModel.projection_contract:",
        new="    if False:",
        want=f"{_FORGED}::test_form2_typed_null_marker_cannot_impersonate_a_contract",
        why="② 版本化 typed null marker 冒充 contract。单点在 `models.validate_bundle_slots` "
            "的 projection 分支；短路它之后 `projection_contract` bundle 可以三 child 全 marker "
            "⇒ AC 2.3「三 child 必须全部 approved 非空 artifact」当场失守。变异落在**被委托方**"
            "正是要证明：Task 76 的 form2 判据不是自己抄的一份重言式",
    ),
    # ═══ 幂等复用不得退化（AC 3.6 / 6.2 / Property 10 / 28）═══════════════════
    Mutation(
        id="M07", side="be", path=PP, kind="replace",
        anchor="                        WorkpaperSyncDefinitionArtifact.sha256 == digest,",
        new="                        WorkpaperSyncDefinitionArtifact.sha256 != digest,",
        want=f"{_PGIDEM}::test_second_run_creates_nothing_and_reuses_every_stage",
        wants=(
            f"{_PGIDEM}::test_second_run_adds_no_row_to_any_supply_table",
            f"{_PGIDEM}::test_no_duplicate_definition_content_exists",
            f"{_PGROWS}::test_all_four_tables_hold_real_rows_after_the_full_chain",
        ),
        why="按 canonical bytes 复用是 Task 76 的核心承诺。判据取反后同内容 definition 每次"
            "都会再发一份 ⇒ 真库上第二次 provision 就多出 4 行（AC 6.2「不得产生第二份同内容"
            "definition」）。这条只有**真库跑第二遍**才能证伪，离线 AST 判据看不出来",
    ),
    Mutation(
        id="M08", side="be", path=PP, kind="replace",
        anchor="                        WorkpaperSyncDefinitionBundle.canonical_payload_sha256 == digest,",
        new="                        WorkpaperSyncDefinitionBundle.canonical_payload_sha256 != digest,",
        want=f"{_PGIDEM}::test_second_run_adds_no_row_to_any_supply_table",
        wants=(f"{_PGIDEM}::test_second_run_creates_nothing_and_reuses_every_stage",),
        why="同 M07 但落在 bundle：bundle 复用失效后每次 provision 多一行 bundle，且 candidate "
            "的 `target_definition_bundle_id` 会指向后发的那一份 ⇒ 同一 entry 出现两个"
            "「当前权威」bundle（Property 28 的身份漂移形态）",
    ),
    Mutation(
        id="M09", side="be", path=PP, kind="replace",
        anchor="        validate_definition_payload(k, payload)",
        new="        pass",
        want=f"{_REUSE}::test_payload_validation_runs_before_the_reuse_branch",
        why="复用分支之前必须先校验 payload：删掉它之后，只要库里已存在同 digest 的行，"
            "一份**非法** payload 就会被「已存在」免检放行（假绿：判据被缓存旁路绕过）",
    ),
    Mutation(
        id="M10", side="be", path=PP, kind="replace",
        anchor="        return await _revision_and_pointer(self._session, wp_id=wp_id, entry_id=entry_id)",
        new='        return {"content_revision": 0, "pointer": None}',
        want=f"{_PROP}::test_property_4_revision_orthogonality_has_an_observable_judgment",
        wants=(f"{_SURFACE}::test_revision_and_pointer_snapshot_has_a_single_implementation",),
        why="Property 4 的判据是**前后现读**比对。把 attach 侧的快照改成写死常量之后，"
            "「revision 没变」变成恒真重言式 —— 这正是本 spec 反复实测的假绿第③源"
            "（自我比对）。两处快照必须同源，否则短路一处仍然全绿",
    ),
    # ═══ representation 阶段结算与 attach 的越权禁令（AC 3.4 / 6.18 / P67）═════
    Mutation(
        id="M11", side="be", path=PP, kind="replace",
        anchor="        if current is not None and current.definition_bundle_id == definitions.bundle_id:",
        new="        if current is not None:",
        want=f"{_PGATTACH}::test_attach_moves_awaiting_contract_to_ready",
        wants=(f"{_PGIDEM}::test_post_attach_run_reuses_the_candidate",),
        why="幂等复用的尺度必须是「current representation 绑的正是**本次** bundle」。"
            "放宽成「只要有 current 就算复用」之后，存量 representation（绑旧 bundle）会让"
            "provisioner 报 `reused_current` 而永不 attach ⇒ 升级链在这一格静默停住"
            "（表现为「本项目无此数据」式的取空）",
    ),
    Mutation(
        id="M12", side="be", path=PP, kind="replace",
        anchor="        if candidate.state != CandidateState.awaiting_contract.value:",
        new="        if False:",
        want=f"{_PGATTACH}::test_attach_refuses_every_out_of_scope_request",
        why="受控 attach 只接受 `awaiting_contract`。短路后已 ready / 已 finalize 的 candidate "
            "都能被改写（AC 6.18 逐字禁止「修改已 finalize 的 candidate」）。"
            "注意状态机仍会拒绝，但**错误类型会变** ⇒ 判据要求错误可分辨，不是「反正拒了」",
    ),
    Mutation(
        id="M13", side="be", path=PP, kind="replace",
        anchor="        if candidate.wp_id != wp_id or candidate.entry_id != entry_id:",
        new="        if False:",
        want=f"{_PGATTACH}::test_attach_refuses_every_out_of_scope_request",
        why="跨 entry 复用 candidate。短路后 A entry 的 approved contract/bundle 可以绑到 "
            "B entry 的 candidate 上 ⇒ Tasks 40~57「不得跨 entry 复用 contract/bundle/"
            "candidate/evidence」失守，且 finalize 出来的 representation 身份是错的",
    ),
    Mutation(
        id="M14", side="be", path=RP, kind="replace",
        anchor="        if bundle.contract_slot_ref != contract_slot_ref:",
        new="        if False:",
        want=f"{_PGATTACH}::test_attach_refuses_every_out_of_scope_request",
        why="attach 的 contract 必须**正是** bundle 的 contract child。短路后可以把 A 的 "
            "contract 绑到 B 的 bundle 上，`assert_candidate_finalizable` 的 compatibility "
            "比对随后会以「不一致」失败 —— 但那时 candidate 已经是 `ready`，属半成功可见态",
    ),
    Mutation(
        id="M15", side="be", path=RP, kind="delete",
        anchor='        assert_transition("candidate", cand.state, CandidateState.ready)',
        want=f"{_ATTACH}::test_attach_delegates_state_edge_and_bundle_check",
        why="状态边的单点是 `models.CANDIDATE_EDGES`（`finalized` 出边为空集）。删掉委托之后"
            "仓储自己就没有状态边判据了 —— 只剩服务层那一条，短路它即可改写终态 candidate",
    ),
    Mutation(
        id="M16", side="be", path=RP, kind="replace",
        anchor="        bundle = await self.assert_bundle_usable(definition_bundle_id)",
        scope='        contract_slot_ref = f"definition:{contract_definition_id}"',
        offset=-1,
        new="        bundle = await self._session.get("
            "WorkpaperSyncDefinitionBundle, definition_bundle_id)",
        want=f"{_ATTACH}::test_attach_delegates_state_edge_and_bundle_check",
        why="bundle 可用性（approved + 四 slot + child kind/state/digest）的单点是 "
            "`assert_bundle_usable`。换成裸 `session.get` 之后 attach 可以绑一个 unapproved / "
            "typed-null-contract 的 bundle（AC 3.3 / Property 67 逐字禁止）。"
            "🔴 该行在本文件出现 3 次，用 `scope+offset` 相对定位到 attach 里那一处",
    ),
    Mutation(
        id="M17", side="be", path=RP, kind="replace",
        anchor='        if contract.state != "approved":',
        new="        if False:",
        # 🔴 首轮 want 指向 `test_attach_delegates_state_edge_and_bundle_check`（AST 判据：
        #    attach 调了哪些单点）—— 把 `if` 短路不会删掉调用，故它照样绿，实测 GREEN。
        #    更关键的是当时**根本没有**「未 approved contract 被拒」这条行为判据：拒绝确实
        #    发生，但是被后面的 `contract_slot_ref` 比对接住的（同类型不同原因）。
        #    现改指新增的行为判据，它比对**原因**而不只是异常类型。
        want=f"{_PGATTACH}::test_attach_refuses_an_unapproved_contract_for_that_reason",
        why="⑤ 的库侧一格：attach 的 target contract 必须 approved。短路后一份 `candidate` "
            "态 contract 就能绑上去，`ck_wpruc_ready_requires_bundle` 只检查非空、不检查 "
            "approved ⇒ 未审契约进入 ready candidate",
    ),
    # ═══ 消费宿主（additive 注入即死代码）═════════════════════════════════════
    Mutation(
        id="M18", side="be", path=SCRIPT, kind="replace",
        anchor="                outcome = await provisioner.ensure(entry_id=target.entry_id)",
        new='                raise ProvisionScriptError("provisioner 未接线")',
        want=f"{_HOST}::test_provisioner_is_consumed_by_the_apply_script",
        why="provisioner 没有宿主就是 additive 死代码（本 spec 实测最常见的假绿第①源）。"
            "判据必须落在**唯一消费方**：摘掉 `ensure()` 调用之后离线判据要立刻打红，"
            "而不是靠 grep 到符号名就算接上了",
    ),
    Mutation(
        id="M19", side="be", path=SCRIPT, kind="replace",
        anchor="                await session.commit()",
        new="                await session.rollback()",
        want=f"{_HOST}::test_provisioner_is_consumed_by_the_apply_script",
        why="`--apply` 不 commit 时四张供给表永远是 0 行 —— 「库里有真实行」这条验收标尺"
            "会被一个只在事务里跑一遍的脚本骗过去",
    ),
    Mutation(
        id="M20", side="be", path=SCRIPT, kind="replace",
        anchor='        wp_codes = tuple(sorted(getattr(supply.provider, "PILOT_WP_CODES", ()) or ()))',
        new='        wp_codes = ("B60",)',
        want=f"{_HOST}::test_apply_script_resolves_targets_from_a_single_source",
        why="`entry → wp_code` 只有一份真源（provider 自己的 `PILOT_WP_CODES`）。写死清单之后"
            "新 entry 的目标解析会悄悄错到别的底稿上，且第二份清单必然与真源漂移"
            "（平台级铁律：避免硬编码 + 单一真源）",
    ),
    # ═══ DB 层判据（应用层承诺不算判据）═══════════════════════════════════════
    Mutation(
        id="M21", side="be", path=V153, kind="replace",
        anchor="    BEFORE UPDATE OR DELETE ON working_paper_representation_candidate_event",
        new="    BEFORE INSERT ON working_paper_representation_candidate_event",
        want=f"{_PGATTACH}::test_audit_trail_rejects_mutation_at_the_database_layer",
        why="append-only 必须由 DB 触发器落实。改成 `BEFORE INSERT` 之后 SQL 仍然合法、迁移仍然"
            "应用成功，但 `UPDATE` / `DELETE` 就能改写审计轨 ⇒ 「谁绑了哪份身份」可被事后篡改"
            "（AC 6.18 / Property 67）。这条只有真库能证伪",
    ),
    Mutation(
        id="M22", side="be", path=V153, kind="replace",
        anchor="        OR (from_state = 'awaiting_contract' AND to_state = 'ready'))",
        new="        OR (from_state IS NOT NULL))",
        want=f"{_V153T}::test_attach_edge_is_constrained_in_the_database",
        why="审计轨自己也不得记录本入口无权做的迁移。放宽 CHECK 之后可以写一条 "
            "`ready → finalized` 的 `contract_bundle_attached` 事件 ⇒ 事后无法分辨"
            "「谁做的 finalize」（本入口只有 `awaiting_contract → ready` 这一条边）",
    ),
]

GUARD_FILES = {
    "test_task76_projection_definition_provisioner.py": "Task 76 新建（离线判据）",
    "test_task76_projection_definition_provisioner_pg.py": "Task 76 新建（真实 PG 判据）",
}

if __name__ == "__main__":
    raise SystemExit(
        run_cli(
            mutations=MUTATIONS,
            guard_files=GUARD_FILES,
            repo=REPO,
            backend_args=[
                "backend/tests/workpaper_sync/test_task76_projection_definition_provisioner.py",
                "backend/tests/workpaper_sync/test_task76_projection_definition_provisioner_pg.py",
                "-q",
                "--tb=no",
                "-rf",
                "-p",
                "no:randomly",
            ],
            baseline_backend_passed=88,
        )
    )
