"""Task 69 前端独立回归守卫的**变异检验**。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 7 Task 69

═══ 为什么必须做 ═══

守卫写完不做变异，就无法区分「代码没问题」与「守卫有缺陷」。本脚本对三类目标各自变异：

* **数据侧**（报告 JSON）—— 把某条结论改坏，对应的 pytest 判据必须打红；
* **门侧**（`check_task69_*.py`）—— 把某条现算逻辑改坏，逐字节锁或对应判据必须打红；
* **前端判据面侧**（`task69IndependentRegression.spec.ts`）—— 把某条断言改弱/把观测点删掉，
  vitest 侧必须打红（证明那条断言真的在起作用，不是摆设）。

═══ 流程与铁律 ═══

    .\\.venv\\Scripts\\python.exe backend/scripts/diagnose/mutate_task69_frontend_regression_guards.py --list
    ... --run M01,M02,M03
    ... --check-anchors

* **禁后台执行**（孤儿进程会让还原核验失败）；**绝不 `--restore`**（正常流程自动还原）。
* 四态判定 RED / GREEN（守卫缺陷）/ ANCHOR-MISS（脚本缺陷）/ WRONG-TEST（污染或锚点错行），
  退出码不作判据。
* `want` 一律用**短 nodeid**（后端）或**测试标题子串**（前端）。已知坑：kit 的 `_locate_want`
  对 parametrize nodeid 恒误报 ⇒ 本脚本的目标测试全部是**非** parametrize 的显式方法。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "backend" / "scripts"))

from _mutation_kit import Mutation, run_cli  # noqa: E402

REPORT_REL = "backend/data/workpaper_sync_task69_frontend_regression.json"
GATE_REL = "backend/scripts/check/check_task69_frontend_independent_regression.py"
#: 🔴 本门守卫**刻意不放在**上游后端独立回归所普查的那个测试目录里 —— 它把「目录内不引用
#: 被验生产单元的文件」这份普查冻结进了自己的逐字节锁，往那个目录新增任何一个测试文件都会
#: 让它的 `in_dir_but_out_of_surface` 变长、3 条上游守卫打红（本轮已实测因果，见 BP-69-6）。
GUARD_REL = "backend/tests/workpaper_sync_frontend/test_task69_frontend_regression.py"
SPEC_REL = (
    "audit-platform/frontend/src/components/workpaper/sync/__tests__/"
    "task69IndependentRegression.spec.ts"
)

GUARD_FILES = {
    "test_task69_frontend_regression.py": "本门守卫（读报告 + 门源码 AST + 判据面独立性）",
    "task69IndependentRegression.spec.ts": "本门前端独立回归判据面（真实挂载 + DOM/network 顺序）",
}


def _report_field(payload: bytes, *path: str) -> object:
    node: object = json.loads(payload.decode("utf-8"))
    for key in path:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    return node


MUTATIONS: list[Mutation] = [
    # ══════════════════════════════════════════════════════════════════════
    # 数据侧：报告 JSON 的结论被改坏
    # ══════════════════════════════════════════════════════════════════════
    Mutation(
        id="M01",
        side="be",
        path=REPORT_REL,
        kind="replace",
        anchor='      "production_host_chain_verified": false,',
        new='      "production_host_chain_verified": true,',
        want="test_verdict_honest_scope_does_not_overclaim",
        why="把「生产宿主链路已验」改成 true = 本任务最容易翻车的过度声称。守卫必须打红，"
            "否则「组件级全绿 ⇒ 宿主与 DOM 已回归」这句话就能悄悄成立。",
        scope_check=lambda payload: _report_field(
            payload, "verdict", "honest_scope", "production_host_chain_verified"
        )
        is True,
    ),
    Mutation(
        id="M02",
        side="be",
        path=REPORT_REL,
        kind="replace",
        anchor='    "all_arms_flip": true,',
        new='    "all_arms_flip": false,',
        want="test_every_adjacent_swap_flips_the_judgement_to_red",
        why="顺序判据的反事实臂不再全部翻红 = 判据可能是重言（三件事都发生过型）。守卫必须打红。",
        scope_check=lambda payload: _report_field(payload, "dom_network_order", "all_arms_flip")
        is False,
    ),
    Mutation(
        id="M03",
        side="be",
        path=REPORT_REL,
        kind="replace",
        anchor='    "forward_recompute_ok": true',
        new='    "forward_recompute_ok": false',
        want="test_forward_recompute_accepts_correct_and_rejects_missing",
        why="正向重算不成立 = 判据可能恒真（教训 15：反事实抓不到恒真）。守卫必须打红。",
        scope_check=lambda payload: _report_field(
            payload, "dom_network_order", "forward_recompute_ok"
        )
        is False,
    ),
    Mutation(
        id="M04",
        side="be",
        path=REPORT_REL,
        kind="replace",
        anchor='    "matched_zero_suites": false,',
        new='    "matched_zero_suites": true,',
        want="test_vitest_really_ran_and_matched_suites",
        why="vitest 匹配到 0 个 suite 却仍被读成「跑过了」正是本门首轮踩到的真实缺陷"
            "（过滤器按项目根解析，传仓库相对路径静默匹配 0 个）。守卫必须打红。",
        scope_check=lambda payload: _report_field(payload, "vitest_run", "matched_zero_suites")
        is True,
    ),
    Mutation(
        id="M05",
        side="be",
        path=REPORT_REL,
        kind="replace",
        anchor='    "reachability_semantics": "transitive（起点 = 替代面之外的生产文件直接 import 到的模块，再沿替代面内部的 import 边闭包）",',
        new='    "reachability_semantics": "direct",',
        want="test_reachability_semantics_are_stated_and_both_kinds_reported",
        why="口径说明被改掉后「19/22 不可达」这个数字说不清是哪个口径 —— 而首轮正是因为两个"
            "口径混用才与上游对不上。守卫必须打红。",
        scope_check=lambda payload: _report_field(
            payload, "replacement_reachability", "reachability_semantics"
        )
        == "direct",
    ),
    Mutation(
        id="M06",
        side="be",
        path=REPORT_REL,
        kind="replace",
        anchor='    "agrees": true,',
        new='    "agrees": false,',
        want="test_reachability_agrees_with_the_upstream_deletion_plan",
        why="与上游可达性登记不一致却仍判过 = 两次扫描看到的不是同一个世界。守卫必须打红。",
    ),
    Mutation(
        id="M07",
        side="be",
        path=REPORT_REL,
        kind="replace",
        anchor='    "executed": true,',
        new='    "executed": false,',
        want="test_locks_were_rerun",
        why="把上游锁复跑的「真跑过」标记改成 false ⇒ 「本门产物没打红上游报告」这条结论失去"
            "来源。守卫必须打红。",
        # 🔴 报告里有三处同缩进的 `\"executed\": true,`（辐射面 vitest / 全套基线 / 上游锁）
        # ⇒ 必须用 scope 相对定位，绝不用绝对行号（教训 8）。
        scope='  "upstream_lock_reruns": {',
        offset=2,
    ),
    Mutation(
        id="M28",
        side="be",
        path=REPORT_REL,
        kind="replace",
        anchor='    "outside_census_dir": true,',
        new='    "outside_census_dir": false,',
        want="test_placement_is_recomputed_and_passes",
        why="守卫被挪回上游普查目录后仍判过 ⇒ 上游逐字节锁会被本门产物打红，而表象是"
            "「上游报告过期」看上去像别人的问题。守卫必须打红。",
        scope_check=lambda payload: _report_field(
            payload, "guard_placement", "outside_census_dir"
        )
        is False,
    ),
    Mutation(
        id="M29",
        side="be",
        path=GATE_REL,
        kind="replace",
        anchor="    return not path_rel.startswith(UPSTREAM_CENSUS_DIR)",
        new="    return True",
        want="test_the_census_membership_rule_is_a_real_function_not_a_constant",
        why="把「不在普查目录」这条现算改成常量 True ⇒ 判据恒真。🔴 首轮（当时这段还是内联"
            "赋值）判 GREEN，追因为**等价变异**：当前取值本来就是 True ⇒ 报告一字不变 ⇒ 只读"
            "磁盘的判据天生不敏感（教训 17）。修法不是删变异，而是把规则抽成纯函数并用"
            "「就在普查目录里」的合成路径正向重算，补后转 RED。",
    ),
    Mutation(
        id="M30",
        side="be",
        path=REPORT_REL,
        kind="replace",
        anchor='    "measured_by_this_gate": true,',
        new='    "measured_by_this_gate": false,',
        want="test_baseline_really_ran_the_whole_suite",
        why="全套前端基线不是本门实测的（= 引用旧数 887 passed）⇒ 守卫必须打红。",
        scope_check=lambda payload: _report_field(
            payload, "frontend_baseline", "measured_by_this_gate"
        )
        is False,
    ),

    # ══════════════════════════════════════════════════════════════════════
    # 门侧：现算逻辑被改坏（逐字节锁或对应判据必须打红）
    # ══════════════════════════════════════════════════════════════════════
    Mutation(
        id="M08",
        side="be",
        path=GATE_REL,
        kind="replace",
        anchor="        if re.match(r\"^\\s{2}-\\s\", line) and \"_Requirements:\" not in line",
        new="        if re.match(r\"^\\s{2}-\\s\", line)",
        want="test_gate_check_passes",
        why="把 `_Requirements:` 行重新算进子条目数 ⇒ 子条目数变 5、判定出 blocker、逐字节锁不符。"
            "这是本门首轮真实踩到的偏差，必须有判据把住。",
    ),
    Mutation(
        id="M09",
        side="be",
        path=GATE_REL,
        kind="replace",
        anchor="            if previous[1] >= current[1]:",
        new="            if False:",
        want="test_gate_check_passes",
        why="顺序判据的比较被短路 ⇒ 交换顺序后仍判过 ⇒ 反事实臂全部不翻红 ⇒ blocker。"
            "这条直接检验「顺序判据真的在比下标」。",
    ),
    Mutation(
        id="M10",
        side="be",
        path=GATE_REL,
        kind="replace",
        anchor='            out[path] = "missing"',
        new='            out[path] = "tracked_clean"',
        want="test_absent_artifact_is_reported_as_missing_not_as_tracked_clean",
        why="缺失产物被登记成「已跟踪且干净」= 最贵的一种假绿（`git status --porcelain` 对不存在"
            "路径输出为空，与干净逐字节相同）。🔴 首轮判 GREEN，追因为**等价变异**：五个产物都"
            "在，那条分支当前世界永远走不到 ⇒ 磁盘记录一字不变。修法不是删变异，而是补一条用"
            "**确定不存在的探针路径**正向重算的判据（教训 5/15），补后转 RED。",
    ),
    Mutation(
        id="M11",
        side="be",
        path=GATE_REL,
        kind="replace",
        anchor="    for module_rel in graph.surface:",
        new="    for module_rel in []:",
        want="test_gate_check_passes",
        why="把替代面清单清空 ⇒ 可达性分母为空 ⇒ 「19/22 不可达」恒成立（空集恒等价，假绿第⑥源）。"
            "逐字节锁必须不符。",
    ),
    Mutation(
        id="M12",
        side="be",
        path=GATE_REL,
        kind="replace",
        anchor='            if not _MODE_HINT_RE.search(literal):',
        new='            if True:',
        want="test_gate_check_passes",
        why="把模式键筛选改成恒真跳过 ⇒ legacy 键分母塌成 0 ⇒ 覆盖率恒 100%。逐字节锁必须不符。",
    ),
    Mutation(
        id="M13",
        side="be",
        path=GATE_REL,
        kind="replace",
        anchor='            blockers.append("vitest 匹配到 0 个 suite —— 过滤器写错，行为侧结论无来源")',
        new='            pass',
        want="test_zero_matched_suites_becomes_a_blocker",
        why="删掉「0 个 suite」这条 blocker ⇒ 过滤器写错时门仍判 passed。🔴 首轮判 GREEN 且"
            "**这正是脚本预言的结果**：逐字节锁不变（当前 suite 数非零 ⇒ 判定结果不变），说明"
            "「0 suite 必红」这条能力当时没有任何判据。已补合成输入重算（喂 "
            "`matched_zero_suites=True` 给门的判定函数）后转 RED。",
    ),
    Mutation(
        id="M14",
        side="be",
        path=GATE_REL,
        kind="replace",
        anchor='        if not re.fullmatch(r"BP-69-\\d+", str(row.get("id")))',
        new='        if False',
        want="test_a_globally_numbered_blocking_point_becomes_a_blocker",
        why="BP id 的 task-scoped 校验被短路 ⇒ 全局 `BP-NN` 又能混进来（Tasks 60/61/63/64 已"
            "重复占用过）。🔴 首轮判 GREEN，追因为**等价变异**：本门六个 id 全合规 ⇒ 该分支"
            "走不到、逐字节锁不变。已补合成输入重算（把一个 id 换成 `BP-42` 再让判定现算）"
            "后转 RED。",
    ),
    Mutation(
        id="M15",
        side="be",
        path=GATE_REL,
        kind="replace",
        anchor="    for path in paths:",
        new="    for path in []:",
        want="test_gate_check_passes",
        why="git 状态逐产物核查被空转 ⇒ 产物清单变空 ⇒ 「产物是否入库」这条信息消失。"
            "逐字节锁必须不符。",
    ),
    # ══════════════════════════════════════════════════════════════════════
    # 前端判据面侧：断言被改弱 / 观测点被删（vitest 必须打红）
    # ══════════════════════════════════════════════════════════════════════
    Mutation(
        id="M16",
        side="fe",
        path=SPEC_REL,
        kind="replace",
        anchor="    if (positions[i - 1].index >= positions[i].index) {",
        new="    if (false) {",
        want="descriptor 链路的真实顺序是 mount",
        why="判据面自己的顺序比较被短路 ⇒ 反事实臂（交换顺序）不再抛 ⇒ 那条 expect(...).toThrow "
            "必须打红。这条直接检验「顺序判据不是三件事都发生过」。",
    ),
    Mutation(
        id="M17",
        side="fe",
        path=SPEC_REL,
        kind="replace",
        anchor="    await wrong.wrapper.setProps({ launchDescriptor: descriptor } as never)",
        new="    await wrong.wrapper.setProps({ descriptor } as never)",
        want="prop 名写错时零挂载",
        why="把「传一个不存在的 prop 名」这一支改成传**正确**的 prop 名 ⇒ 编辑器真的挂上 ⇒ "
            "`expect(wrong.editors).toHaveLength(0)` 必须打红。🔴 首轮打的是初始化那行 "
            "`props[descriptorProp] = null`，判 GREEN 且追因为**等价变异**：初值挂在哪个键上"
            "都是「没有 descriptor」，真正承载区分度的是这行 setProps。教训 11：修法是把变异"
            "移到真正载荷的那行，不是删掉它。",
    ),
    Mutation(
        id="M18",
        side="fe",
        path=SPEC_REL,
        kind="replace",
        anchor="    throw new Error(`[T69] ${label} 带 [${present.join(', ')}] —— claim 前/download-only 必须三者全空`)",
        new="    return",
        want="browser crash 进入 recovery_pending",
        why="三实体判据不再抛 ⇒ 反事实臂（喂一个带 operation 的三实体）不翻红 ⇒ 必须打红。",
    ),
    Mutation(
        id="M19",
        side="fe",
        path=SPEC_REL,
        kind="replace",
        anchor="    throw new Error(`[T69] 端点多重集 [${got.join(', ')}] ≠ 期望 [${want.join(', ')}]`)",
        new="    return",
        want="editor 不自行取 config",
        why="端点多重集判据不再抛 ⇒ 「多打了一次 config」这条反事实臂不翻红 ⇒ 立即失败②必须打红。",
    ),
    Mutation(
        id="M20",
        side="fe",
        path=SPEC_REL,
        kind="replace",
        anchor="          record('editor', 'doc-editor-constructed', { placeholderId })",
        new="          void placeholderId",
        want="descriptor 链路的真实顺序是 mount",
        why="删掉 DocEditor 构造的观测点 ⇒ 顺序链缺项 ⇒ `assertOrder` 必须因缺项打红"
            "（缺项不得被读成「顺序对」）。",
    ),
    Mutation(
        id="M21",
        side="fe",
        path=SPEC_REL,
        kind="replace",
        anchor="    return Promise.reject(",
        new="    return Promise.resolve({ data: {} }) || Promise.reject(",
        want="判据面自身 fail-closed",
        why="把「未登记端点」从拒绝改成静默成功 ⇒ 打错端点不再可见 ⇒ 其余判据的共同前提"
            "（每个被打到的端点都必须显式登记）失效。🔴 首轮判 GREEN，追因为**等价变异**："
            "正常路径上每个端点都登记了、那条分支走不到 ⇒ 33 条判据一条都不会红。修法是补一条"
            "「判据的判据」（I34）主动走一遍它，补后转 RED。",
    ),
    Mutation(
        id="M22",
        side="fe",
        path=SPEC_REL,
        kind="replace",
        anchor="      return { kind: node.attributes('data-kind') ?? '', text: node.text() }",
        new="      return { kind: node.attributes('data-kind') ?? '', text: '同步成功' }",
        want="状态条文案是逐状态派生值",
        why="把「从真实 DOM 读状态条文案」换成常量「同步成功」⇒ 逐状态文案塌成一条 ⇒ 「文案是"
            "派生值而非常量」与 AC 11.3「不得统一显示同步成功」同时失守，必须打红。"
            "🔴 首轮打的是那条 `expect(text.includes('同步成功')).toBe(false)`，判 GREEN —— "
            "**把断言改弱永远不会让通过的测试失败**（它只能检验冗余度，检验不了正确性）。"
            "教训 11：改成打**被观测的主体**（DOM 读取本身），判据才真的会响。",
    ),
    Mutation(
        id="M23",
        side="fe",
        path=SPEC_REL,
        kind="replace",
        anchor="        throw new Error('[T69] 表单 flush 失败')",
        new="        return { expectedRevision: 11, projection: {} }",
        want="flush 失败时 materialize 调用次数与编辑器挂载次数均为 0",
        why="把 Property 8 那一支的**前提**（flush 真的失败）去掉 ⇒ flush 成功 ⇒ materialize 与"
            "挂载都会发生 ⇒ 「均为 0」必须打红。这条检验的是「零调用是被 flush 失败**导致**的」"
            "而不是「这个 harness 本来就什么都不做」（教训 5：对照组必须先过）。"
            "🔴 首轮打的是 `toHaveLength(0)` 那行断言，判 GREEN —— 改弱断言不可能让通过的测试"
            "失败；必须改**被判据的前提**。",
    ),
    Mutation(
        id="M24",
        side="fe",
        path=SPEC_REL,
        kind="replace",
        anchor="    const extra = Object.keys(config).filter((key) => !Object.prototype.hasOwnProperty.call(source, key))",
        new="    const extra = Object.keys(config).filter(() => false)",
        want="editor 不自行取 config",
        why="把「宿主多补了哪些 config 键」这个**差集本身**算空 ⇒ 等值判据的左边恒为空 ⇒ "
            "「只多出 width/height/events」立刻不成立，必须打红。🔴 首轮打的是那行 `toEqual`"
            "断言并判 GREEN —— 改弱断言不可能让通过的测试失败；必须打**被断言的计算**。",
    ),
    Mutation(
        id="M25",
        side="fe",
        path=SPEC_REL,
        kind="replace",
        anchor="        entities[key] = UUID(970)",
        new="        entities[key] = null",
        want="claim 前不得伪三实体",
        why="把「claim 前预置一个实体」这个**前提**去掉 ⇒ 三实体全空 ⇒ 转换合法、不再抛 ⇒ "
            "「必须抛 bridge_recovery_premature_entities」立刻打红。这条证明拒绝是被那个伪实体"
            "**导致**的（教训 5：对照组必须先过）。🔴 首轮打的是拒绝码那行断言并判 GREEN —— "
            "改弱断言不可能让通过的测试失败。",
    ),
    Mutation(
        id="M26",
        side="fe",
        path=SPEC_REL,
        kind="replace",
        anchor="    respond('get_operation', () => codedFailure(500, 'merge_engine_failed', '合并引擎失败'))",
        new="    respond('get_operation', () => operationWire({ state: 'applied', application_id: APPLICATION, durable_at: '2026-09-01T00:01:00Z', result_revision: 12 }))",
        want="fail-open 文案被禁",
        why="把 Property 48 那一支的**前提**（一次真实的同步失败）换成成功 ⇒ 没有 error 可被"
            "覆盖 ⇒ 「refreshOperation 必须 rejects」与「状态条仍是 error」同时打红。"
            "🔴 首轮打的是 `toBe('error')` 那行断言并判 GREEN —— 改弱断言不可能让通过的测试"
            "失败；必须改**被判据的前提**。",
    ),
    Mutation(
        id="M27",
        side="fe",
        path=SPEC_REL,
        kind="replace",
        anchor="  EXPORTED_TRACES[name] = trace().map((row) => ({ ...row, detail: { ...row.detail } }))",
        new="  EXPORTED_TRACES[name] = []",
        want="判据面自身 fail-closed",
        why="导出给门的观测带变空 ⇒ 门侧的顺序/三实体现算全部失去输入。🔴 首轮判 GREEN：门的 "
            "`--check` 复用磁盘上**已记录**的观测带，所以连门也抓不到（只有重跑 --run-vitest "
            "才会）。修法是在判据面里正向断言「四个场景的导出带各自非空且含真实 network 行」，"
            "补后转 RED。",
    ),
]


def main() -> int:
    return run_cli(
        mutations=MUTATIONS,
        guard_files=GUARD_FILES,
        repo=REPO,
        description="Task 69 前端独立回归守卫变异检验",
        backend_args=[
            GUARD_REL,
            "-q",
            "--no-header",
            "--tb=no",
            "-rfE",
            "-p",
            "no:randomly",
        ],
        frontend_filters=[
            "src/components/workpaper/sync/__tests__/task69IndependentRegression.spec.ts"
        ],
        frontend_dir=REPO / "audit-platform" / "frontend",
        vitest_json=REPO / "backend" / "scripts" / "diagnose" / "_task69_vitest.json",
        guard_roots=("backend/tests", "audit-platform/frontend/src"),
    )


if __name__ == "__main__":
    raise SystemExit(main())
