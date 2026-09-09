#!/usr/bin/env python
"""受控破坏 G-C0 contract / inventory / resolution 守卫，证明行为守卫会 RED，最后恢复原字节。

覆盖 Task 2 reconciliation 矩阵中登记的四类缺口里尚未有锚点的三类：

* contract  —— schema.json / compatibility_matrix.json / canonical fixture 漂移；
* inventory —— exemption 过期不阻断、分母缩水、run_id 混进稳定 digest；
* resolution —— child exact 与 runtime contract 脱钩、parent_inherited 掩盖 invalid。

四态判定与锚点纪律沿用 ``backend/scripts/check/mutate_common.py`` 的约定，但本脚本按
字节级读写（与前一份 source_ref wiring 脚本一致），以便直接嵌在多行 Python 源码上做锚点。
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

GC0_DIR = "backend/data/guidance/contracts/gc0"


@dataclass(frozen=True)
class Mutation:
    mutation_id: str
    relative_path: str
    original: bytes
    replacement: bytes
    test_node: str
    expected_failure: str
    why: str


MUTATIONS: tuple[Mutation, ...] = (
    # ---------------- Contract: C0 单源漂移必须 RED ----------------
    Mutation(
        mutation_id="C01_SCHEMA_CONTRACT_VERSION_DRIFT",
        relative_path=f"{GC0_DIR}/schema.json",
        original=b'"contractVersion": "1.0",',
        replacement=b'"contractVersion": "1.1",',
        test_node=(
            "backend/tests/test_guidance_gc0_conformance.py"
            "::TestFixtures_AcceptAndParity::test_contract_version_constant_matches_schema"
        ),
        expected_failure="test_contract_version_constant_matches_schema",
        why="schema.json contractVersion 漂移 → 与 Python 常量 GC0_CONTRACT_VERSION 不等",
    ),
    Mutation(
        mutation_id="C02_MATRIX_UNKNOWN_MAJOR_OPEN",
        relative_path=f"{GC0_DIR}/compatibility_matrix.json",
        original=b'"unknownMajorPolicy": "fail-closed-blocked"',
        replacement=b'"unknownMajorPolicy": "accept-latest"',
        test_node=(
            "backend/tests/test_guidance_gc0_conformance.py"
            "::TestCompatibilityMatrix::test_matrix_unknown_major_policy_is_fail_closed"
        ),
        expected_failure="test_matrix_unknown_major_policy_is_fail_closed",
        why="unknown major 策略改为放行 → fail-closed 契约被破坏",
    ),
    Mutation(
        mutation_id="C03_CANDIDATE_FIXTURE_FORGES_FINALIZATION",
        relative_path=f"{GC0_DIR}/fixtures/handoff_candidate.json",
        original=b'  "phase": "candidate",\r\n  "authority": {',
        replacement=b'  "phase": "finalized",\r\n  "authority": {',
        test_node=(
            "backend/tests/test_guidance_gc0_conformance.py"
            "::TestReq14_HandoffPhaseFieldDiscipline::test_candidate_fixture_lacks_finalization_fields"
        ),
        expected_failure="test_candidate_fixture_lacks_finalization_fields",
        why="candidate fixture 伪装成 finalized → Req 1.4 字段纪律失守",
    ),
    # ---------------- Inventory: 分母与 exemption ----------------
    Mutation(
        mutation_id="INV01_EXPIRED_EXEMPTION_BECOMES_VALID",
        relative_path="backend/app/services/guidance_runtime_facts.py",
        original=(
            b"elif review_after <= now:\n"
            b"        errors.append(\"exemption_expired\")"
        ),
        replacement=b"elif False and review_after <= now:",
        test_node=(
            "backend/tests/test_guidance_inventory_runtime.py"
            "::test_missing_or_expired_inheritance_cannot_shrink_required_denominator"
        ),
        expected_failure="test_missing_or_expired_inheritance_cannot_shrink_required_denominator",
        why="过期 exemption 仍判有效 → 分母可被静默缩水",
    ),
    Mutation(
        mutation_id="INV02_UNVALIDATED_SOURCE_REF_LOSES_OWN_BLOCKER",
        relative_path="backend/app/services/guidance_runtime_inventory.py",
        # runtime invalid 分支的判定被 `exact_status=="exact"` 独立兜住，删 source_ref
        # 子句无法被这条测试察觉（GREEN 假象）。真正 load-bearing 的是 unvalidated
        # 走专属 blocker 而非默认 source_refs_invalid —— 删掉这条映射即 RED。
        original=b'                "unvalidated": "source_ref_context_missing",\n',
        replacement=b'                "unvalidated": "source_refs_invalid",\n',
        test_node=(
            "backend/tests/test_guidance_inventory_runtime.py"
            "::test_static_without_source_ref_validation_never_reaches_exact"
        ),
        expected_failure="test_static_without_source_ref_validation_never_reaches_exact",
        why="unvalidated 失去专属 blocker → 退回默认 source_refs_invalid，掩盖「无 runtime 校验」这一独立判定路径",
    ),
    # ---------------- Resolution: child exact 与 runtime 脱钩 ----------------
    Mutation(
        mutation_id="RES01_CHILD_EXACT_IGNORES_RUNTIME_CONTRACT",
        relative_path="backend/app/services/wp_guidance_service.py",
        # 锚点必须唯一定位到 resolve_guidance（integration test 走的路径），
        # 不能命中 resolve_authoritative_exact 的同形调用 —— 用其后紧跟的
        # `return self._build_response(` 作为区分尾锚（后者尾随的是 AC#5 注释）。
        original=(
            b"child = await self._extractor.extract_exact_static(\r\n"
            b"                requested,\r\n"
            b"                validated_entry=runtime_entry,\r\n"
            b"            )\r\n"
            b"            if child is not None:\r\n"
            b"                return self._build_response("
        ),
        replacement=(
            b"child = await self._extractor.extract_exact_static(\r\n"
            b"                requested,\r\n"
            b"            )\r\n"
            b"            if child is not None:\r\n"
            b"                return self._build_response("
        ),
        test_node=(
            "backend/tests/test_guidance_source_ref_integration.py"
            "::test_source_ref_four_states_reach_every_exact_gate"
        ),
        expected_failure="test_source_ref_four_states_reach_every_exact_gate",
        why="child exact 不再消费 runtime contract → stale/invalid 被静默放行",
    ),
)


def _assert_anchor(mutation: Mutation) -> None:
    payload = (ROOT / mutation.relative_path).read_bytes()
    count = payload.count(mutation.original)
    replacement_count = payload.count(mutation.replacement)
    if count != 1 or replacement_count:
        raise RuntimeError(
            f"{mutation.mutation_id}: anchor={count} replacement={replacement_count}"
        )


def _apply(mutation: Mutation) -> None:
    path = ROOT / mutation.relative_path
    payload = path.read_bytes()
    if payload.count(mutation.original) != 1:
        raise RuntimeError(f"{mutation.mutation_id}: apply anchor 不唯一")
    path.write_bytes(payload.replace(mutation.original, mutation.replacement, 1))


def _restore(mutation: Mutation) -> None:
    path = ROOT / mutation.relative_path
    payload = path.read_bytes()
    if payload.count(mutation.replacement) != 1:
        raise RuntimeError(f"{mutation.mutation_id}: restore anchor 不唯一")
    path.write_bytes(payload.replace(mutation.replacement, mutation.original, 1))


def _run_test(mutation: Mutation) -> tuple[bool, str]:
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            mutation.test_node,
            "-q",
            "--tb=short",
            "-p",
            "no:cacheprovider",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    output = f"{completed.stdout}\n{completed.stderr}"
    red = completed.returncode != 0 and mutation.expected_failure in output
    return red, output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-anchors", action="store_true")
    args = parser.parse_args()

    for mutation in MUTATIONS:
        _assert_anchor(mutation)
    if args.check_anchors:
        print(f"[OK] gc0/inventory/resolution mutation anchors={len(MUTATIONS)}")
        return 0

    red_count = 0
    restored_count = 0
    for mutation in MUTATIONS:
        _apply(mutation)
        try:
            red, output = _run_test(mutation)
            if not red:
                print(f"[GREEN] {mutation.mutation_id}  {mutation.why}")
                print(output[-4000:])
            else:
                red_count += 1
                print(f"[RED]   {mutation.mutation_id}  {mutation.why}")
        finally:
            _restore(mutation)
            _assert_anchor(mutation)
            restored_count += 1
    print(
        f"gc0/inventory/resolution mutations RED={red_count}/{len(MUTATIONS)} "
        f"restored={restored_count}/{len(MUTATIONS)}"
    )
    return 0 if red_count == len(MUTATIONS) and restored_count == len(MUTATIONS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
