# -*- coding: utf-8 -*-
"""Task 61 首版引导器守卫的变异检验（走 `_mutation_kit` 共享件）。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 5 Task 61

每条变异改一处真实产物（引导脚本源码或证据台账 JSON），跑守卫文件，要求**预期那条**
判据变红。四态判读与覆盖面分母由共享件提供，本文件只声明变异。

═══ 2026-09-04 迁移记录（E 泳道 · L4 判据治理）═══

原实现自带 harness，被 `test_mutation_kit_adoption.py::test_new_scripts_must_use_the_shared_kit`
判为违规（本脚本 2026-09-02 入库，晚于冻结日 2026-08-16，故不可登记进 `_LEGACY_NOT_REQUIRED`
——该表只许缩小）。迁移同时修掉**两个实缺陷**，二者都让「RED n/n」比字面更弱：

🔴 **缺陷一：四态里的 WRONG-TEST 分支根本不存在。** 原 `run_all()` 的判定只有一行
``results[m.mid] = "GREEN" if code == 0 else "RED"`` —— 按**退出码**判，而 docstring 与
文件标题都声明四态。后果：变异让守卫文件产生收集错误（ERROR）、或打红的是**别的**判据，
一律记成 RED。共享件明令「只看退出码会把后三态误判成 RED」，判定改为**失败测试名集合差集**
（``added = current - baseline``），命中 `want` 才是 RED，有新增失败但未命中即 WRONG-TEST。
另注：原实现把 pytest 输出捕获进 ``out`` 后**从未使用** —— 那是「本想解析 nodeid 却没写」的痕迹。

🔴 **缺陷二：M04 的判据强度与其余十条不同且无声。** 其 `expect_test` 是裸类名
``TestFixtureGateIsARealGate``（不含 `::`），命中原 `_pytest()` 的
``f"{_TEST}::{node}" if "::" in node else str(_TEST)`` 回退分支 ⇒ 实际跑**整个守卫文件**、
文件内任何失败都算 RED。其余十条都写 ``Class::test`` 形态，可见这是漏写而非有意。迁移后
`want` 仍保持类级（不擅自改判据强度，Property 26），但共享件按 nodeid 子串匹配 ⇒ 只有
**该类内**的新增失败才算命中，类外失败落 WRONG-TEST。这是消除回退缺陷，不是加强判据。

🔴 **缺陷三（由迁移首跑当场揪出，原实现结构上不可能发现）：M11 的期望测试类名是错的。**
原写 ``TestNoBypassAndNoBusinessRowWrites::test_a_lane_with_a_different_entry_id_scheme_is_rejected``，
而该测试实际住在 ``TestEvidenceLedgerIsRealAndComplete`` 里。共享件首跑即判 **WRONG-TEST** 并
打印实际新增失败的完整 nodeid，据此更正后转 RED。原实现看不见它：变异确实打红了那条测试、
退出码非零 ⇒ 记 RED，于是「`want` 指向一个不存在的类」这个事实被永久掩盖。
这是 WRONG-TEST 四态的第三种成因（前两种是锚点错行、污染残留）：**`want` 声明与守卫实际
结构不符**。它也说明为什么「RED n/n」必须由差集判定得出 —— 按退出码判时，判据写错与判据
正确在报告里逐字相同。

**等价性**（Property 26）：11 条变异的 id / 目标文件 / 语义意图 / 预期打红判据逐条不变
（M11 的 `want` 仅更正类名，测试方法名一字未改）。
锚点按共享件语义改写为**去掉行尾的整行文本**（原实现用子串 `str.count`，共享件用行级定位）：
M01/M04 原锚点带 `\\n` 已去掉；M07~M10 原锚点是 JSON 行内子串，已补齐前导缩进与行尾逗号。
改写后逐条实测行级命中恰为 1（`--check-anchors`）。
`kind` 按原替换语义归类：M01 整行删除 → `delete`；M03/M04 原替换是「原行 + 新增行」
⇒ 语义即 `insert`；其余 6 条整行替换 → `replace`。

**保留的原有能力**：原 harness 有两条铁律（起手基线门 `HARNESS-DIRTY-TREE`、判 GREEN 前
核对变异真落盘）。共享件各有对应实现且更强 —— 基线非空直接 ABORT（退出 4）、
`apply_mutation` 写盘后核验并在 `finally` 还原 + md5 自证、残留 `.mutbak` 拦在起手。

**新增能力**：`guard_files` 覆盖面分母。「变异全 RED」按清单计数，「守卫都被反证过」按文件
计数，二者是两件事 —— 原实现没有分母，无法回答后者。

用法（仓库根）::

    python backend/scripts/diagnose/mutate_task61_bootstrap_guards.py --list
    python backend/scripts/diagnose/mutate_task61_bootstrap_guards.py --check-anchors
    python backend/scripts/diagnose/mutate_task61_bootstrap_guards.py --run all \\
        --out .kiro/specs/workpaper-html-onlyoffice-bidirectional-writeback-closure/evidence/task61-oo94-word-pilot-gate/bootstrap_mutation_report.json
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/scripts

from _mutation_kit import Mutation, run_cli  # noqa: E402

REPO = Path(__file__).resolve().parents[3]

#: 被变异的引导脚本（生产 fix 宿主）。
SCRIPT = "backend/scripts/fix/fix_task61_bootstrap_first_published_representation.py"
#: 被变异的证据台账 —— 台账自证判据必须能被「把台账改坏」打红，否则它只是装饰。
EVIDENCE = (
    ".kiro/specs/workpaper-html-onlyoffice-bidirectional-writeback-closure"
    "/evidence/task61-oo94-word-pilot-gate/first_published_representation_bootstrap.json"
)
#: 守卫文件（同时是 pytest 目标与覆盖面分母的唯一成员）。
GUARD = "backend/tests/workpaper_sync/test_task61_first_published_representation_bootstrap.py"

GUARD_FILES = {
    "test_task61_first_published_representation_bootstrap.py":
        "Task 61 首版引导器守卫：夹具门是真门（非装饰、无绕过开关、反例逐条被拒）、"
        "判定函数可失败（碰真实客户行 / 动只读表 / entry_id 口径不符均须打红）、"
        "证据台账真实完整（每条判据 passed、字节来自冻结权威模板、三表 0→1、首代单次 commit）",
}

MUTATIONS: list[Mutation] = [
    # ═══ ① 夹具门是不是真的门 ════════════════════════════════════════════
    Mutation(
        id="M01", side="be", path=SCRIPT, kind="delete",
        anchor="    assert_fixture_only(hit)",
        want="TestNoBypassAndNoBusinessRowWrites::test_target_resolution_actually_calls_the_gate",
        why="把夹具门的调用整行删掉 ⇒ 门退化成装饰。这是假绿第①源（additive 死代码）的"
            "镜像形态：函数还在、判据还在，只是没人调用它，而静态检查与单测都看不出",
    ),
    Mutation(
        id="M02", side="be", path=SCRIPT, kind="replace",
        anchor='FIXTURE_CLIENT_NAME: str = "测试客户"',
        new='FIXTURE_CLIENT_NAME: str = "任意客户"',
        want="TestFixtureGateIsARealGate::test_a_real_fixture_row_passes",
        why="把夹具客户名换掉 ⇒ 真实客户项目会被当成夹具放行。引导器会往真实业务行写"
            "首版 representation，这是本任务最不可逆的一种事故",
    ),
    Mutation(
        id="M03", side="be", path=SCRIPT, kind="insert",
        anchor='    parser.add_argument("--contract", default=DEFAULT_CONTRACT_LOGICAL_ID)',
        new='    parser.add_argument("--force-non-fixture", action="store_true")',
        want="TestNoBypassAndNoBusinessRowWrites::test_no_force_style_bypass_flag_exists",
        why="加一个绕过夹具门的开关 ⇒ 门还在但可被命令行关掉。「有豁免开关」与「无门」"
            "在后果上等价，且前者更难发现",
    ),
    Mutation(
        id="M04", side="be", path=SCRIPT, kind="insert",
        anchor="    bad: list[str] = []",
        new="    return ()",
        want="TestFixtureGateIsARealGate",
        why="让夹具门恒返回「无违规」（fail open）⇒ 任何行都通过。fail-open 是平台记录里"
            "最贵的一类缺陷：表现为「本来就没问题」，静态检查全绿",
    ),
    # ═══ ② 判定函数必须真的可能失败 ══════════════════════════════════════
    Mutation(
        id="M05", side="be", path=SCRIPT, kind="replace",
        anchor='        "only_fixture_business_row_touched": len(non_fixture) == 0,',
        new='        "only_fixture_business_row_touched": True,',
        want="TestVerdictFunctionCanFail::test_a_real_client_row_being_touched_fails_the_run",
        why="把「只碰夹具行」判据钉成恒真 ⇒ 判定函数永远给出通过。判据恒真与判据不存在"
            "在报告里逐字相同，只能靠「构造反例必须失败」反证",
    ),
    Mutation(
        id="M06", side="be", path=SCRIPT, kind="replace",
        anchor='        "no_untouched_table_moved": all(a[t] == b[t] for t in UNTOUCHED_TABLES),',
        new='        "no_untouched_table_moved": True,',
        want="TestVerdictFunctionCanFail::test_touching_an_untouched_table_fails_the_run",
        why="把「只读表未动」判据钉成恒真 ⇒ 引导器动了不该动的表也照样报通过",
    ),
    Mutation(
        id="M11", side="be", path=SCRIPT, kind="replace",
        anchor="    if lane.entry_id_source is not EntryIdSource.wp_id:",
        new="    if False:",
        # 🔴 原实现此处写 `TestNoBypassAndNoBusinessRowWrites::...`，**类名是错的** ——
        #    该测试实际住在 `TestEvidenceLedgerIsRealAndComplete` 里。迁移首跑当场判
        #    WRONG-TEST 并报出实际新增失败的完整 nodeid，据此更正。原 harness 结构上不可能
        #    发现这个错：它只看退出码，而变异确实打红了那条（写对了名字的）测试。
        want="TestEvidenceLedgerIsRealAndComplete::test_a_lane_with_a_different_entry_id_scheme_is_rejected",
        why="把 entry_id 口径校验短路成不可达 ⇒ 口径不同的 lane 也被放行，首版会落在错误的"
            "身份命名空间上。原实现记录该条首轮 GREEN，补行为判据后才转 RED —— 属守卫补强"
            "的实证，锚点与意图保持不变",
    ),
    # ═══ ③ 证据台账不得是装饰（改坏台账必须立刻打红）══════════════════════
    Mutation(
        id="M07", side="be", path=EVIDENCE, kind="replace",
        anchor='      "only_fixture_business_row_touched": true,',
        new='      "only_fixture_business_row_touched": false,',
        want="TestEvidenceLedgerIsRealAndComplete::test_every_check_passed_and_nothing_failed",
        why="台账里把一条判据改成 false ⇒ 必须立刻打红，不得被 `failed=[]` 掩盖。"
            "「逐条 passed」与「failed 列表为空」是两个判据，只看后者会漏掉这种形态",
    ),
    Mutation(
        id="M08", side="be", path=EVIDENCE, kind="replace",
        anchor='    "artifact_sha256": "31e7992ba1e83952620e1777d108b46f7e7817dcdc9484c07f079f1dd3af0afa",',
        new='    "artifact_sha256": "0000000000000000000000000000000000000000000000000000000000000000",',
        want="TestEvidenceLedgerIsRealAndComplete::test_the_bytes_came_from_the_frozen_authoritative_template",
        why="把 representation digest 改掉 ⇒ 声称「字节来自冻结权威模板」的判据必须红。"
            "全零 hash 是平台记录过的非法 digest 形态，守卫不该把它当合法值放过",
    ),
    Mutation(
        id="M09", side="be", path=EVIDENCE, kind="replace",
        anchor='      "working_paper_content_representation": 1,',
        new='      "working_paper_content_representation": 0,',
        want="TestEvidenceLedgerIsRealAndComplete::test_the_three_supply_tables_went_from_zero_to_one",
        why="把首版供给改回 0 ⇒ 「三表 0→1」这条判据必须红。注意台账里另有一处 after 之前的"
            "0 值（同键不同区段），故锚点取整行含行尾逗号以保证行级唯一",
    ),
    Mutation(
        id="M10", side="be", path=EVIDENCE, kind="replace",
        anchor='    "commit_count": 1,',
        new='    "commit_count": 2,',
        want="TestEvidenceLedgerIsRealAndComplete::test_the_receipt_is_a_first_generation_opaque_commit",
        why="把 commit 次数改成 2 ⇒ 「首代单次提交」这条判据必须红。二次提交正是 Task 15 "
            "禁止的双 revision 形态（projection-only commit 后再增一次）",
    ),
]


if __name__ == "__main__":
    raise SystemExit(
        run_cli(
            mutations=MUTATIONS,
            guard_files=GUARD_FILES,
            repo=REPO,
            description="Task 61 首版引导器守卫变异检验",
            backend_args=[
                GUARD,
                "-q",
                "--no-header",
                "-p",
                "no:randomly",
                "--tb=no",
                "-rfE",
            ],
            # 实测基线（2026-09-04，干净工作树）：31 passed。
            baseline_backend_passed=31,
        )
    )
