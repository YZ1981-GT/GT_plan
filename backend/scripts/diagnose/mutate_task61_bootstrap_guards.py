# -*- coding: utf-8 -*-
"""Task 61 首版引导器守卫的变异检验（四态：RED / GREEN / ANCHOR-MISS / WRONG-TEST）。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 5 Task 61

每条变异改一处真实产物（脚本源码或台账 JSON），跑**指定的那一条**测试，要求它变红。
GREEN = 守卫有洞；ANCHOR-MISS = 锚点没命中或命中多处（脚本缺陷）；
WRONG-TEST = 打红了但红的不是预期那条。

用法::

    python backend/scripts/diagnose/mutate_task61_bootstrap_guards.py --check-anchors
    python backend/scripts/diagnose/mutate_task61_bootstrap_guards.py --run all
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2].parent
_SCRIPT = _REPO / "backend/scripts/fix/fix_task61_bootstrap_first_published_representation.py"
_TEST = _REPO / "backend/tests/workpaper_sync/test_task61_first_published_representation_bootstrap.py"
_EVIDENCE = (
    _REPO
    / ".kiro/specs/workpaper-html-onlyoffice-bidirectional-writeback-closure"
    / "evidence/task61-oo94-word-pilot-gate/first_published_representation_bootstrap.json"
)

@dataclass(frozen=True)
class Mutation:
    mid: str
    target: Path
    anchor: str
    replacement: str
    expect_test: str
    intent: str


MUTATIONS: tuple[Mutation, ...] = (
    Mutation(
        "M01",
        _SCRIPT,
        "    assert_fixture_only(hit)\n",
        "",
        "TestNoBypassAndNoBusinessRowWrites::test_target_resolution_actually_calls_the_gate",
        "把夹具门的调用整行删掉（门退化成装饰）",
    ),
    Mutation(
        "M02",
        _SCRIPT,
        'FIXTURE_CLIENT_NAME: str = "测试客户"',
        'FIXTURE_CLIENT_NAME: str = "任意客户"',
        "TestFixtureGateIsARealGate::test_a_real_fixture_row_passes",
        "把夹具客户名换掉（真实客户项目会被放行）",
    ),
    Mutation(
        "M03",
        _SCRIPT,
        '    parser.add_argument("--contract", default=DEFAULT_CONTRACT_LOGICAL_ID)',
        '    parser.add_argument("--contract", default=DEFAULT_CONTRACT_LOGICAL_ID)\n'
        '    parser.add_argument("--force-non-fixture", action="store_true")',
        "TestNoBypassAndNoBusinessRowWrites::test_no_force_style_bypass_flag_exists",
        "加一个绕过夹具门的开关",
    ),
)
MUTATIONS = MUTATIONS + (
    Mutation(
        "M04",
        _SCRIPT,
        "    bad: list[str] = []\n",
        "    bad: list[str] = []\n    return ()\n",
        "TestFixtureGateIsARealGate",
        "让夹具门恒返回「无违规」（fail open）",
    ),
    Mutation(
        "M05",
        _SCRIPT,
        '        "only_fixture_business_row_touched": len(non_fixture) == 0,',
        '        "only_fixture_business_row_touched": True,',
        "TestVerdictFunctionCanFail::test_a_real_client_row_being_touched_fails_the_run",
        "把「只碰夹具行」判据钉成恒真",
    ),
    Mutation(
        "M06",
        _SCRIPT,
        '        "no_untouched_table_moved": all(a[t] == b[t] for t in UNTOUCHED_TABLES),',
        '        "no_untouched_table_moved": True,',
        "TestVerdictFunctionCanFail::test_touching_an_untouched_table_fails_the_run",
        "把「只读表未动」判据钉成恒真",
    ),
    Mutation(
        "M07",
        _EVIDENCE,
        '"only_fixture_business_row_touched": true',
        '"only_fixture_business_row_touched": false',
        "TestEvidenceLedgerIsRealAndComplete::test_every_check_passed_and_nothing_failed",
        "台账里把一条判据改成 false（应立刻打红，不得被 failed=[] 掩盖）",
    ),
)
MUTATIONS = MUTATIONS + (
    Mutation(
        "M08",
        _EVIDENCE,
        '"artifact_sha256": "31e7992ba1e83952620e1777d108b46f7e7817dcdc9484c07f079f1dd3af0afa"',
        '"artifact_sha256": "0000000000000000000000000000000000000000000000000000000000000000"',
        "TestEvidenceLedgerIsRealAndComplete::test_the_bytes_came_from_the_frozen_authoritative_template",
        "台账里把 representation digest 改掉（字节在途被改写）",
    ),
    Mutation(
        "M09",
        _EVIDENCE,
        '"working_paper_content_representation": 1',
        '"working_paper_content_representation": 0',
        "TestEvidenceLedgerIsRealAndComplete::test_the_three_supply_tables_went_from_zero_to_one",
        "台账里把首版供给改回 0",
    ),
    Mutation(
        "M10",
        _EVIDENCE,
        '"commit_count": 1',
        '"commit_count": 2',
        "TestEvidenceLedgerIsRealAndComplete::test_the_receipt_is_a_first_generation_opaque_commit",
        "台账里把 commit 次数改成 2（二次提交）",
    ),
    Mutation(
        "M11",
        _SCRIPT,
        "    if lane.entry_id_source is not EntryIdSource.wp_id:",
        "    if False:",
        "TestNoBypassAndNoBusinessRowWrites::test_a_lane_with_a_different_entry_id_scheme_is_rejected",
        "把 entry_id 口径校验短路成不可达（M11 首轮 GREEN，补行为判据后转 RED）",
    ),
)

def check_anchors() -> int:
    bad = 0
    for m in MUTATIONS:
        text = m.target.read_text(encoding="utf-8")
        hits = text.count(m.anchor)
        status = "OK" if hits == 1 else f"ANCHOR-MISS(hits={hits})"
        if hits != 1:
            bad += 1
        print(f"{m.mid} {status} {m.target.name} :: {m.intent}")
    print(f"anchors {len(MUTATIONS) - bad}/{len(MUTATIONS)} OK")
    return 1 if bad else 0


def _pytest(node: str) -> tuple[int, str]:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", f"{_TEST}::{node}" if "::" in node else str(_TEST),
         "-q", "--no-header", "-p", "no:cacheprovider", "--tb=no", "-rfE"],
        cwd=str(_REPO), capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")

def run_all() -> int:
    """跑全部变异。

    两条 harness 铁律（首轮实测踩到过）：
    ① **无条件还原** —— 起手对每个 target 各拍一份 pristine 快照，最后在 finally 里
       统一写回。首版把还原放在单条变异的 try/finally 里，ANCHOR-MISS 分支 continue
       直接跳过还原，于是上一轮的变异被留在盘上，下一轮把「已被变异」误判成
       ANCHOR-MISS/GREEN，级联出一串假结论。
    ② **判 GREEN 前先确认变异真的落盘** —— 读回来核对替换文本在位。落不了盘却报
       GREEN，等于把 harness 自己的缺陷记成「守卫有洞」。
    """
    # 🔴 起手基线门：pristine 快照必须拍在**干净**的树上。首版没有这道门，
    #    上一轮残留的变异被当成 pristine，于是每轮「还原」都把变异写回去，
    #    级联出一串 GREEN/ANCHOR-MISS 假结论（本任务实测到两轮）。
    pre, _ = _pytest("")
    if pre != 0:
        print("HARNESS-DIRTY-TREE：变异前基线就是红的，拒绝拍 pristine 快照。"
              "先把工作树恢复干净（很可能是上一轮变异残留）再跑。")
        return 2
    targets = {m.target for m in MUTATIONS}
    pristine = {t: t.read_text(encoding="utf-8") for t in targets}
    results: dict[str, str] = {}
    try:
        for m in MUTATIONS:
            m.target.write_text(pristine[m.target], encoding="utf-8", newline="\n")
            original = pristine[m.target]
            if original.count(m.anchor) != 1:
                results[m.mid] = "ANCHOR-MISS(" + str(original.count(m.anchor)) + ")"
                continue
            mutated = original.replace(m.anchor, m.replacement)
            m.target.write_text(mutated, encoding="utf-8", newline="\n")
            if m.target.read_text(encoding="utf-8") != mutated:
                results[m.mid] = "HARNESS-WRITE-FAILED"
                continue
            code, out = _pytest(m.expect_test)
            results[m.mid] = "GREEN" if code == 0 else "RED"
    finally:
        for t, text in pristine.items():
            t.write_text(text, encoding="utf-8", newline="\n")
            assert t.read_text(encoding="utf-8") == text, "还原失败: " + str(t)
    baseline, _ = _pytest("")
    print(json.dumps(results, ensure_ascii=False, indent=2))
    off = [k for k, v in results.items() if v != "RED"]
    print("RED " + str(len(results) - len(off)) + "/" + str(len(results)) + "；非 RED: " + str(off))
    print("还原后基线: " + ("PASS" if baseline == 0 else "FAIL"))
    return 1 if off or baseline != 0 else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__ or "")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check-anchors", action="store_true")
    mode.add_argument("--run", choices=["all"])
    args = parser.parse_args(argv)
    if args.check_anchors:
        return check_anchors()
    return run_all()


if __name__ == "__main__":  # pragma: no cover - CLI
    raise SystemExit(main())