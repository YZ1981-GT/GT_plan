r"""Task 65 变异检验 —— opaque lane 登记表、消费门与 application identity 守卫的强度。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 6 Task 65
被检验的守卫：
* ``backend/tests/workpaper_sync/test_task65_opaque_authority_bundle.py``（离线）
* ``backend/tests/workpaper_sync/test_task65_opaque_authority_bundle_pg.py``（真实 PG）

## 为什么每条变异都不是无效变异

Task 65 的三条正文各对应一组最贵缺陷，每组都有变异：

1. **登记表退化成一张漏得掉的手写清单** —— 登记表本身没有约束力，全部约束力来自
   `assert_lane_registry_covers_source` 的三个方向与 `commit_bytes(lane_id=)` 实参比对。
   短路任一条（M01~M06），「新加一条 opaque writer 没登记」「entry_id 命名空间被悄悄换掉」
   「lane_id 传错导致 authority model 静默切换」就都能通过。
2. **「先发布后消费」退化回「写路径顺手 approve」** —— M14~M20 覆盖：写路径改回调
   `provision()`、gate 的 slot 判据被跳过、gate 拿到发布器、`lane_id` 恢复默认值、
   provision 脚本不再消费生产 gate / 不再从登记表现算目标 / 根本不调 provisioner。
3. **application identity 折叠** —— M22/M23 把 `compute_application_key` 的两个身份
   digest 判据短路，于是「相同 incoming 在不同 bundle / authority model 下」会算出同一
   个 key（Property 64 明令禁止）。

另有 M11~M13 落在 **DB 拦不住的那一格**：V151 的 `wpsync_check_bundle_slots` 只对
`projection_contract` 要求三 slot 全 definition，对 opaque **不**要求全 marker ——
`assert_slots_are_typed_null_markers` 是唯一防线，短路它即失守。

M21 是**反向**变异（往源码里插入一段重复定义），检验「死代码判据」是 AST 计数而不是
grep：既有守卫 `assert "def resolve_is_custom_sync(" in code` 对插入第二份定义无感。

## 用法（仓库根；PATH 上的 `python` 可能指向坏掉的解释器）

    .\.venv\Scripts\python.exe backend/scripts/diagnose/mutate_task65_opaque_authority_bundle_guards.py --list
    .\.venv\Scripts\python.exe backend/scripts/diagnose/mutate_task65_opaque_authority_bundle_guards.py --check-anchors
    .\.venv\Scripts\python.exe backend/scripts/diagnose/mutate_task65_opaque_authority_bundle_guards.py --run all --out tmp_task65_mutation.json

🔴 **禁后台执行**（孤儿 python + 前台同时变异 ⇒ RestoreFailed）；**绝不 `--restore`**
（除非 `--run` 明确报出残留备份）。

🔴 真库判据要求已 provision：先跑
`backend/scripts/fix/fix_task65_provision_opaque_authority_bundles.py --apply`，
否则 `_pg.py` 的基线本身就是红的（kit 会 ABORT）。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/scripts

from _mutation_kit import Mutation, run_cli  # noqa: E402

REPO = Path(__file__).resolve().parents[3]

GATE = "backend/app/services/workpaper_sync/opaque_entry_gate.py"
WM = "backend/app/services/workpaper_sync/writer_migration.py"
MODELS = "backend/app/services/workpaper_sync/models.py"
CTX = "backend/app/services/custom_workpaper_context.py"
SCRIPT = "backend/scripts/fix/fix_task65_provision_opaque_authority_bundles.py"

#: 🔴 kit 按**短 nodeid**（basename::类::方法）匹配新增失败集合 —— 带
#: `backend/tests/...` 前缀会让「实际打红的正是预期那条」被误判 WRONG-TEST。
_T = "test_task65_opaque_authority_bundle.py"
_G = "test_task65_opaque_authority_bundle_pg.py"

MUTATIONS: list[Mutation] = [
    # ═══ 一、登记表的三个方向 + lane_id 实参（约束力的全部来源）═════════════════
    Mutation(
        id="M01", side="be", path=GATE, kind="replace",
        anchor="    if unregistered or stale or drifted:",
        new="    if False:",
        want=f"{_T}::test_unregistered_call_site_fails_closed",
        wants=(
            f"{_T}::test_registration_without_call_site_fails_closed",
            f"{_T}::test_entry_id_source_drift_fails_closed",
        ),
        why="登记表 ≡ 源码调用点的**总闸**。短路后三个方向（未登记调用点 / 无调用点的"
            "登记 / 实参形态漂移）全部只算不报 —— 登记表当场退化成一张纯装饰清单，"
            "而它是 custom/opaque 的唯一可枚举分母（manifest 的 capability 封闭四值里"
            "没有 custom）",
    ),
    Mutation(
        id="M02", side="be", path=GATE, kind="replace",
        anchor="        if len(matched) != 1:",
        scope="            and _qualname_matches(lane.writer_qualname, site.enclosing_qualname)",
        offset=2,
        new="        if False:",
        want=f"{_T}::test_unregistered_call_site_fails_closed",
        why="方向①单点：新加一条 opaque writer 却没进登记表时不再被发现。它与 M01 分开是"
            "因为 M01 短路的是**报告**、本条短路的是**收集** —— 只测总闸时删掉收集分支"
            "会让 unregistered 恒空，总闸照样不触发 ⇒ 判 GREEN",
    ),
    Mutation(
        id="M03", side="be", path=GATE, kind="replace",
        anchor="    stale = sorted(lane_id for lane_id, hits in by_lane.items() if not hits)",
        new="    stale = []",
        want=f"{_T}::test_registration_without_call_site_fails_closed",
        why="方向②：登记了一条已经消失的 lane（与 manifest 生成器的 `stale overlay` 判据"
            "同款）。恒空之后「登记表与事实脱钩」永远不会被发现，而 provision 脚本会按它"
            "去发布一个没有消费方的 bundle",
    ),
    Mutation(
        id="M04", side="be", path=GATE, kind="replace",
        anchor="        if site.entry_id_source is not lane.entry_id_source:",
        new="        if False:",
        want=f"{_T}::test_entry_id_source_drift_fails_closed",
        why="方向③：`wp_code=ctx.wp_code` 被改成 `wp_code=None` 不再被发现。这不是形式"
            "问题 —— `opaque_entry_id` 对 None 退回 `str(wp_id)`，同一份权威文件会落到"
            "另一个 entry 下，rollback 与 evidence 查不到对方的行",
    ),
    Mutation(
        id="M05", side="be", path=GATE, kind="replace",
        anchor="        if arg.lane_id != lane.lane_id:",
        new="        if False:",
        want=f"{_T}::test_wrong_lane_id_argument_fails_closed",
        why="把 custom 的 `lane_id=\"custom_cells\"` 改成别的 lane 不再被发现。lane_id "
            "单向决定 authority model，传错即把 custom 底稿的权威模型从 "
            "`custom_authoritative_ooxml` 静默换成 `opaque_single_onlyoffice` ⇒ evidence "
            "分桶与 `application_key` 一起失真",
    ),
    Mutation(
        id="M06", side="be", path=GATE, kind="replace",
        anchor="            if not (isinstance(arg, ast.Constant) and isinstance(arg.value, str)):",
        new="            if False:",
        want=f"{_T}::test_non_literal_lane_id_is_rejected_by_discovery",
        why="`lane_id=some_var` 被放行。允许运行期变量之后，「这条写入路径用的是哪个 "
            "authority model」变成运行期才知道的事，本模块与 Task 67 的 structural "
            "pre-reconcile 的静态判据当场退化成猜测",
    ),

    # ═══ 二、lane 登记自洽（四条各自可 falsify）═══════════════════════════════
    Mutation(
        id="M07", side="be", path=GATE, kind="replace",
        anchor="        if lane.instrumentation_required:",
        new="        if False:",
        want=f"{_T}::test_instrumentation_required_true_fails_closed",
        why="AC 6.19：无显式 contract 的 custom/user-upload 文件不得被强行 instrumentation。"
            "放开这一列等于给自己开一条「给用户原文件注入 `_GT_SYNC` 隐藏表」的后门"
            "（sidecar 不得改变原文件语义）",
    ),
    Mutation(
        id="M08", side="be", path=GATE, kind="replace",
        anchor="        if lane.authority_model is not expected:",
        new="        if False:",
        want=f"{_T}::test_html_counterpart_and_authority_model_are_cross_locked",
        why="design §「authority model 的选择由有没有 HTML 对端决定」。短路后 "
            "`has_html_counterpart` 就只是一列注释，改了不会有任何后果 —— 那正是"
            "「声明存在但不生效」的形态",
    ),
    Mutation(
        id="M09", side="be", path=GATE, kind="replace",
        anchor="        if lane.authority_model not in OPAQUE_AUTHORITY_MODELS:",
        new="        if False:",
        want=f"{_T}::test_projection_contract_lane_is_rejected",
        why="OG-2：`projection_contract` 被允许登记成 opaque lane。两条通道的 slot 规则"
            "相反（projection 要三 child 全 approved definition，opaque 只能三 marker），"
            "混用即 AC 2.3 失守",
    ),
    Mutation(
        id="M10", side="be", path=GATE, kind="replace",
        anchor="        if lane.lane_id in seen:",
        new="        if False:",
        want=f"{_T}::test_duplicate_lane_id_is_rejected",
        why="lane_id 是稳定 key，重复之后 `_LANES_BY_ID` 只保留最后一条 ⇒ 前一条的 "
            "authority model 真源静默消失，而 `lane_for()` 仍然返回一个看起来正常的登记",
    ),

    # ═══ 三、slot marker 判据（V151 对 opaque 不设约束，这里是唯一防线）═════════
    Mutation(
        id="M11", side="be", path=GATE, kind="replace",
        anchor="        if spec.is_definition:",
        new="        if False:",
        want=f"{_T}::test_marker_slots_pass_and_definition_slot_is_rejected",
        wants=(f"{_G}::test_slot_marker_guard_is_reachable_through_the_gate",),
        why="OG-4 的核心：`models.validate_bundle_slot` 对 `definition` 是**放行**的"
            "（它不知道调用方在哪条通道），V151 的 `wpsync_check_bundle_slots` 对 opaque "
            "也不要求三 slot 全 marker ⇒ 这条 `if` 是「opaque bundle 不得带 definition "
            "child」的唯一防线。短路后一个 projection bundle 可被 opaque lane 消费",
    ),
    Mutation(
        id="M12", side="be", path=GATE, kind="replace",
        anchor="        if spec.slot_digest != expected.slot_digest:",
        new="        if False:",
        want=f"{_T}::test_forged_marker_digest_is_rejected",
        why="伪造 typed null digest 被放行。marker registry 是 marker 的唯一来源"
            "（V151 的 seed 与 `definitions.TYPED_NULL_MARKERS` 逐字节同源）；不比 digest "
            "就等于只认 `type` 字符串，而 digest 才是进 bundle canonical bytes 的那一项",
    ),
    Mutation(
        id="M13", side="be", path=GATE, kind="replace",
        anchor="        if spec is None:",
        new="        if False:",
        want=f"{_T}::test_missing_slot_is_rejected",
        why="缺 slot 不再报专属错误，改由后续 `validate_bundle_slot` 以 AttributeError "
            "崩掉 —— 「三个 typed slot 必须全出现」这条判据从 fail-closed 退化成 crash，"
            "错误码消失（调用方按 error_code 分支就走不到 fail-closed 分支）",
    ),

    # ═══ 四、消费门只查不发布 / provision 与 consume 分离 ══════════════════════
    Mutation(
        id="M14", side="be", path=WM, kind="replace",
        anchor="        bundle = await self._provisioner.resolve(lane_id=lane_id)",
        new="        bundle = await self._provisioner.provision("
            "project_id=project_id, wp_id=wp_id, "
            "authority_model=AuthorityModel.custom_authoritative_ooxml)",
        want=f"{_T}::test_commit_bytes_calls_resolve_not_provision",
        why="把「写路径顺手 approve 自己要用的 bundle」原样复活 —— 这正是 Task 65 要消灭"
            "的形态。AC 6.19 要求「先发布」，写路径自己发证会让任何时刻库里都恰好有它"
            "需要的 bundle ⇒ 那条承诺没有任何可 falsify 的判据",
    ),
    Mutation(
        id="M15", side="be", path=GATE, kind="replace",
        anchor="        assert_slots_are_typed_null_markers(",
        # 🔴 换成一个吃掉同样实参的空 lambda 而不是 `_ = (`：后者让
        #    `where=f"..."` 落进一个 tuple 字面量 ⇒ SyntaxError ⇒ 整模块 import 失败 ⇒
        #    全部测试红 ⇒ 判定 WRONG-TEST（首版实测）。空 lambda 语法合法，精确模拟
        #    「gate 不再调 slot 判据」这一件事。
        new="        (lambda *a, **k: None)(",
        want=f"{_G}::test_slot_marker_guard_is_reachable_through_the_gate",
        why="gate 的 slot 判据被跳过（改成一个求值即弃的表达式，语法仍合法）。这条专门"
            "检验**可达性**判据：首版 `_pg.py` 只用真库的 projection bundle 试，而那条"
            "路径永远先被 `_build` 的 authority 判据挡住 ⇒ slot 判据从未被真实执行过"
            "（additive 注入即死代码）。补了 `_StubSession` 用例之后这条才打得红",
    ),
    Mutation(
        id="M16", side="be", path=GATE, kind="replace",
        anchor="    def __init__(self, *, session: AsyncSession) -> None:",
        new="    def __init__(self, *, session: AsyncSession, publisher: object = None) -> None:",
        want=f"{_T}::test_gate_constructor_cannot_publish",
        why="给消费门装上发布器入口。判据落在**构造签名**而不是「源码里没出现 publish "
            "这个词」：后者是 grep 式判据，改个变量名就绿。拿到 publisher 之后"
            "「消费路径顺手 approve」在装配层重新可表达",
    ),
    Mutation(
        id="M17", side="be", path=WM, kind="replace",
        anchor="        lane_id: str,",
        scope="        substrate_path: Path,",
        offset=1,
        new='        lane_id: str = "custom_cells",',
        want=f"{_T}::test_missing_lane_id_argument_fails_closed",
        why="给身份参数恢复默认值 —— 与改造前 `authority_model=custom_authoritative_ooxml` "
            "同型：user-upload 的 opaque 文件漏传即静默落成 custom，四层静态检查"
            "（Volar / vitest / get_diagnostics / HEAD-swap）全查不出",
    ),

    # ═══ 五、provision 宿主唯一 + 真跑生产 gate + 目标从登记表现算 ══════════════
    Mutation(
        id="M18", side="be", path=SCRIPT, kind="replace",
        anchor="                snapshot = await provisioner.provision(",
        new="                raise ProvisionScriptError(\"provisioner 未接线\")  # (",
        want=f"{_T}::test_provision_has_exactly_one_host",
        why="与 Task 76 的 M18 同款：provisioner 若没有任何消费宿主，它就是一段谁都不跑的"
            "代码，而 gate 的 fail-closed 错误消息里那句「请先运行 …」变成假指引",
    ),
    Mutation(
        id="M19", side="be", path=SCRIPT, kind="replace",
        anchor="    assert_lane_registry_covers_source()",
        new="    pass",
        want=f"{_T}::test_provision_targets_derive_from_registry_not_a_second_list",
        why="发布前置判据被摘掉：给一个「登记表已与源码脱钩」的库发布 bundle，发出来的"
            "东西没有消费方（或消费方拿不到）。三条前置判据里这条管的是分母完整性",
    ),
    Mutation(
        id="M20", side="be", path=SCRIPT, kind="replace",
        anchor="            resolved = await gate.resolve_approved_bundle(lane_id=lane_id)",
        new="            resolved = None  # 不再消费生产 gate",
        want=f"{_T}::test_provision_script_consumes_the_production_gate",
        why="脚本改成自己抄一段判据而不跑生产那份 gate。后果是「脚本说 OK 但业务请求仍然 "
            "500」—— `--check` 的全部价值就在于它跑的是消费路径那一份代码",
    ),

    # ═══ 六、死代码判据必须是 AST 计数而不是 grep ══════════════════════════════
    Mutation(
        id="M21", side="be", path=CTX, kind="insert",
        anchor="async def load_custom_context(",
        new="def resolve_is_custom_sync(wp: WorkingPaper, wp_code: str | None) -> bool:\n"
            "    \"\"\"变异注入的第二份定义（覆盖前一份 ⇒ 前一份成为死代码）。\"\"\"\n"
            "    return False\n"
            "\n"
            "\n",
        want=f"{_T}::test_resolve_is_custom_sync_is_defined_exactly_once",
        why="**反向变异**：往源码里插入第二份同名定义，重现改造前真实存在的缺陷"
            "（原 L118 与 L138 各一份，后者覆盖前者）。既有守卫 "
            "`assert \"def resolve_is_custom_sync(\" in code` 是 grep 式判据，对此无感 —— "
            "本条打红证明新守卫用的是 AST 计数",
    ),

    # ═══ 七、application identity 不得折叠（Property 64 / AC 5.5）══════════════
    Mutation(
        id="M22", side="be", path=MODELS, kind="replace",
        anchor='        _require_digest("definition_bundle_sha256", definition_bundle_sha256),',
        # 🔴 `compute_application_key` 与 `compute_frozen_request_fingerprint` 各有一份
        #    同形行；用 application key 独有的 `frozen_client_base_version_id` 锚定作用域。
        scope="        str(frozen_client_base_version_id),",
        offset=3,
        new="        str(definition_bundle_sha256),",
        want=f"{_G}::test_empty_or_all_zero_digests_are_rejected",
        why="AC 5.5 「definition bundle digest 与 authority model digest 永远非空」的"
            "单点。绕过 `_require_digest` 之后空串与全零 hash 都能进 key —— 全零在 "
            "`char(64)` 与 hex 正则层面都合法，是典型的「忘了算 hash 就填 0」伪身份",
    ),
    Mutation(
        id="M23", side="be", path=MODELS, kind="replace",
        anchor='            "authority_model_definition_sha256", authority_model_definition_sha256',
        # 同 M22：三处同形行（application key / request fingerprint / 另一处），
        # 按 application key 独有的那行相对定位。
        scope="        str(frozen_client_base_version_id),",
        offset=5,
        new='            "authority_model_definition_sha256", "f" * 64',
        want=f"{_G}::test_same_incoming_different_authority_model_yields_different_key",
        wants=(f"{_G}::test_empty_or_all_zero_digests_are_rejected",),
        why="把 authority model digest 钉成常量 ⇒ 它不再参与 application key。于是"
            "「相同 incoming 在不同 authority model 下」会算出同一个 key，custom 与 "
            "opaque 两条 lane 的写入被折叠成一次 application（Property 64 明令禁止）",
    ),
]


GUARD_FILES = {
    _T: "Task 65 离线守卫：lane 登记表三向对齐、登记自洽、slot marker、消费门结构、"
        "provision 宿主、死代码 AST 计数",
    _G: "Task 65 真库守卫：五条 lane 可消费、两 authority model bundle digest 不同、"
        "越权三形态、slot 判据可达性、application identity 不折叠",
}


if __name__ == "__main__":  # pragma: no cover - CLI
    raise SystemExit(
        run_cli(
            mutations=MUTATIONS,
            guard_files=GUARD_FILES,
            repo=REPO,
            description="Task 65 opaque authority bundle 守卫变异检验",
            backend_args=[
                "backend/tests/workpaper_sync/test_task65_opaque_authority_bundle.py",
                "backend/tests/workpaper_sync/test_task65_opaque_authority_bundle_pg.py",
            ],
        )
    )
