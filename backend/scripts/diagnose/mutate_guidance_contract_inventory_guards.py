#!/usr/bin/env python
"""受控破坏 C0 契约与 inventory/coverage 分母核算，证明行为守卫会 RED。

补齐 WIP 对账登记的另外两类缺口：
- contract 类：C0 evidence digest 漂移、exemption 分母扣除
- inventory 类：run_id 进 digest、分母缩水、closed 判定放水

锚点一律用**正则**而非固定缩进字符串，原因：
1. 目标文件是并发高频修改区（`wp_guidance_service.py` 曾被插入 stale 分支，
   导致旧 M04 字符串锚点整体错行 → ANCHOR-MISS）。
2. `schema.json` CRLF 入库，`read_text()` 默认做 universal-newline 转换，
   裸 `\\n` 锚点匹配的是转换后的视图而非磁盘字节。

每条变异在 `finally` 中按字节复原，并用唯一性断言确认锚点未污染。
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

# ---------------------------------------------------------------------------
# ANCHORS — inventory / coverage
# ---------------------------------------------------------------------------

#: contexts_digest 必须随 context 集合变化，且必须是稳定 digest 而非常量。
_ANCHOR_FACTS_DIGEST_COMPUTED = re.compile(
    rb'facts_digest = stable_digest\(\s*\[\s*\{\s*'
    rb'"global_entry_id": item\.global_entry_id,',
)

#: `closed` 必须同时要求 required==required_exact 且无 non_exact。
_ANCHOR_CLOSED_GATE = re.compile(
    rb'return \(\s*'
    rb'self\.counters\.get\("required",\s*0\)\s*==\s*self\.counters\.get\("required_exact",\s*0\)\s*'
    rb'and self\.counters\.get\("required_non_exact",\s*0\)\s*==\s*0\s*'
    rb'\)',
)

#: exemption 过期必须回 pending/stale，不得继续豁免。
_ANCHOR_EXEMPTION_EXPIRY = re.compile(
    rb'elif review_after <= now:\s*'
    rb'errors\.append\("exemption_expired"\)',
)

#: static 必须按 active template context 复验，禁止复用他项目 exact。
_ANCHOR_STATIC_REVALIDATED = re.compile(
    rb'context_static = revalidate_static_guidance_inventory\(\s*'
    rb'relevant_static,\s*'
    rb'source_ref_contexts=source_ref_contexts,\s*\)',
)

#: custom confirmed 缺 binary authority 不得 exact。
_ANCHOR_CUSTOM_NOT_EXACT = re.compile(
    rb'elif custom is not None:\s*'
    rb'status = "invalid"\s*'
    rb'missing = static\.missing_sections if static else CANONICAL_SECTION_KEYS',
)


@dataclass(frozen=True)
class CIAMutation:
    mutation_id: str
    relative_path: str
    anchor: re.Pattern[bytes]
    replacement: bytes
    test_node: str
    expected_failure: str


MUTATIONS = (
    CIAMutation(
        mutation_id="C01_DIGESTS_DECOUPLED_FROM_ENTRY_FACTS",
        relative_path="backend/app/services/guidance_coverage_service.py",
        anchor=_ANCHOR_FACTS_DIGEST_COMPUTED,
        replacement=(
            b'facts_digest = "constant"  # MUTATION C01: digest decoupled '
            b'from entry facts\n'
        ),
        test_node=(
            "backend/tests/test_guidance_global_coverage.py::"
            "test_global_coverage_uses_runtime_contexts_and_keeps_run_id_out_of_stable_digest"
        ),
        expected_failure=(
            "test_global_coverage_uses_runtime_contexts_and_keeps_run_id_out_of_stable_digest"
        ),
    ),
    CIAMutation(
        mutation_id="C02_CLOSED_GATE_FORCES_TRUE",
        relative_path="backend/app/services/guidance_coverage_service.py",
        anchor=_ANCHOR_CLOSED_GATE,
        replacement=(
            b'return True  # MUTATION C02: closed gate removed\n'
        ),
        test_node=(
            "backend/tests/test_guidance_global_coverage.py::"
            "test_prior_global_entry_digest_marks_changed_source_facts_stale"
        ),
        expected_failure=(
            "test_prior_global_entry_digest_marks_changed_source_facts_stale"
        ),
    ),
    CIAMutation(
        mutation_id="C03_EXEMPTION_EXPIRY_IGNORED",
        relative_path="backend/app/services/guidance_runtime_facts.py",
        anchor=_ANCHOR_EXEMPTION_EXPIRY,
        replacement=b'        pass\n',
        test_node=(
            "backend/tests/test_guidance_inventory_runtime.py::"
            "test_missing_or_expired_inheritance_cannot_shrink_required_denominator"
        ),
        expected_failure=(
            "test_missing_or_expired_inheritance_cannot_shrink_required_denominator"
        ),
    ),
    CIAMutation(
        mutation_id="C04_STATIC_NOT_REVALIDATED",
        relative_path="backend/app/services/guidance_coverage_service.py",
        anchor=_ANCHOR_STATIC_REVALIDATED,
        replacement=b'context_static = tuple(relevant_static)  # MUTATION C04\n',
        test_node=(
            "backend/tests/test_guidance_global_coverage.py::"
            "test_static_is_revalidated_per_active_template_context"
        ),
        expected_failure="test_static_is_revalidated_per_active_template_context",
    ),
    CIAMutation(
        mutation_id="C05_CUSTOM_CONFIRMED_BECOMES_EXACT",
        relative_path="backend/app/services/guidance_runtime_inventory.py",
        anchor=_ANCHOR_CUSTOM_NOT_EXACT,
        replacement=(
            b'elif custom is not None:\n'
            b'            status = "exact"  # MUTATION C05\n'
            b'            missing = ()'
        ),
        test_node=(
            "backend/tests/test_guidance_global_coverage.py::"
            "test_confirmed_custom_without_binary_authority_is_not_exact"
        ),
        expected_failure="test_confirmed_custom_without_binary_authority_is_not_exact",
    ),
)


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------


def _assert_anchor(mutation: CIAMutation) -> None:
    payload = (ROOT / mutation.relative_path).read_bytes()
    hits = len(mutation.anchor.findall(payload))
    replacement_hits = payload.count(mutation.replacement)
    if hits != 1 or replacement_hits:
        raise RuntimeError(
            f"{mutation.mutation_id}: anchor_hits={hits} "
            f"replacement_hits={replacement_hits}"
        )


def _apply(mutation: CIAMutation) -> bytes:
    path = ROOT / mutation.relative_path
    payload = path.read_bytes()
    mutated, n = mutation.anchor.subn(mutation.replacement, payload, count=1)
    if n != 1:
        raise RuntimeError(f"{mutation.mutation_id}: apply anchor 未唯一命中")
    path.write_bytes(mutated)
    return payload


def _restore(mutation: CIAMutation, original: bytes) -> None:
    path = ROOT / mutation.relative_path
    path.write_bytes(original)
    assert path.read_bytes() == original, (
        f"{mutation.mutation_id}: bytes not restored exactly"
    )


def _run_test(mutation: CIAMutation) -> tuple[bool, str]:
    completed = subprocess.run(
        [
            sys.executable, "-m", "pytest", mutation.test_node,
            "-q", "--tb=short",
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
        print(f"[OK] contract/inventory mutation anchors={len(MUTATIONS)}")
        return 0

    red_count = 0
    restored_count = 0
    for mutation in MUTATIONS:
        original = _apply(mutation)
        try:
            red, output = _run_test(mutation)
            if not red:
                print(f"[GREEN] {mutation.mutation_id}")
                print(output[-4000:])
            else:
                red_count += 1
                print(f"[RED] {mutation.mutation_id}")
        finally:
            _restore(mutation, original)
            _assert_anchor(mutation)
            restored_count += 1
    print(
        f"contract/inventory mutations RED={red_count}/{len(MUTATIONS)} "
        f"restored={restored_count}/{len(MUTATIONS)}"
    )
    return 0 if red_count == len(MUTATIONS) and restored_count == len(MUTATIONS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
