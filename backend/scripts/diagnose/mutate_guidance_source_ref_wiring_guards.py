#!/usr/bin/env python
"""受控破坏 source_ref 接线并证明行为守卫会 RED，最后恢复原字节。"""
from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class Mutation:
    mutation_id: str
    relative_path: str
    original: bytes
    replacement: bytes
    test_node: str
    expected_failure: str


MUTATIONS = (
    Mutation(
        mutation_id="M01_BATCH_ALL_VALID_SHORT_CIRCUIT",
        relative_path="backend/app/services/guidance_source_refs.py",
        original=b"return bool(self.results) and all(item.valid for item in self.results)",
        replacement=b"return True",
        test_node="backend/tests/test_guidance_source_ref_integration.py::test_source_ref_four_states_reach_every_exact_gate",
        expected_failure="test_source_ref_four_states_reach_every_exact_gate",
    ),
    Mutation(
        mutation_id="M02_COVERAGE_REUSES_UNVALIDATED_STATIC",
        relative_path="backend/app/services/guidance_coverage_service.py",
        original=(
            b"context_static = revalidate_static_guidance_inventory(\n"
            b"            relevant_static,\n"
            b"            source_ref_contexts=source_ref_contexts,\n"
            b"        )"
        ),
        replacement=b"context_static = tuple(relevant_static)",
        test_node="backend/tests/test_guidance_global_coverage.py::test_static_is_revalidated_per_active_template_context",
        expected_failure="test_static_is_revalidated_per_active_template_context",
    ),
    Mutation(
        mutation_id="M03_CUSTOM_CONFIRMED_BECOMES_EXACT",
        relative_path="backend/app/services/guidance_runtime_inventory.py",
        original=(
            b"elif custom is not None:\n"
            b"            status = \"invalid\"\n"
            b"            missing = static.missing_sections if static else CANONICAL_SECTION_KEYS"
        ),
        replacement=(
            b"elif custom is not None:\n"
            b"            status = \"exact\"\n"
            b"            missing = ()"
        ),
        test_node="backend/tests/test_guidance_global_coverage.py::test_confirmed_custom_without_binary_authority_is_not_exact",
        expected_failure="test_confirmed_custom_without_binary_authority_is_not_exact",
    ),
    Mutation(
        mutation_id="M04_PARENT_INHERITED_MASKS_INVALID",
        relative_path="backend/app/services/wp_guidance_service.py",
        original=(
            b"elif runtime_status in {\"missing\", \"invalid\"}:\n"
            b"            resolution_status = runtime_status\n"
            b"        elif runtime_entry is None and result.source == \"static_json\":\n"
            b"            resolution_status = \"invalid\"\n"
            b"        elif force_resolution_status:\n"
            b"            resolution_status = force_resolution_status"
        ),
        replacement=(
            b"elif force_resolution_status:\n"
            b"            resolution_status = force_resolution_status\n"
            b"        elif runtime_status in {\"missing\", \"invalid\"}:\n"
            b"            resolution_status = runtime_status\n"
            b"        elif runtime_entry is None and result.source == \"static_json\":\n"
            b"            resolution_status = \"invalid\""
        ),
        test_node="backend/tests/test_guidance_source_ref_integration.py::test_source_ref_four_states_reach_every_exact_gate",
        expected_failure="test_source_ref_four_states_reach_every_exact_gate",
    ),
)


def _assert_anchor(mutation: Mutation) -> None:
    payload = (ROOT / mutation.relative_path).read_bytes()
    eol = b"\r\n" if payload.count(b"\r\n") else b"\n"
    original, replacement = mutation.original.replace(b"\n", eol), mutation.replacement.replace(b"\n", eol)
    count = payload.count(original)
    replacement_count = payload.count(replacement)
    if count != 1 or replacement_count:
        raise RuntimeError(
            f"{mutation.mutation_id}: anchor={count} replacement={replacement_count}"
        )


def _apply(mutation: Mutation) -> None:
    path = ROOT / mutation.relative_path
    payload = path.read_bytes()
    eol = b"\r\n" if payload.count(b"\r\n") else b"\n"
    original = mutation.original.replace(b"\n", eol)
    replacement = mutation.replacement.replace(b"\n", eol)
    if payload.count(original) != 1:
        raise RuntimeError(f"{mutation.mutation_id}: apply anchor 不唯一")
    path.write_bytes(payload.replace(original, replacement, 1))


def _restore(mutation: Mutation) -> None:
    path = ROOT / mutation.relative_path
    payload = path.read_bytes()
    eol = b"\r\n" if payload.count(b"\r\n") else b"\n"
    original = mutation.original.replace(b"\n", eol)
    replacement = mutation.replacement.replace(b"\n", eol)
    if payload.count(replacement) != 1:
        raise RuntimeError(f"{mutation.mutation_id}: restore anchor 不唯一")
    path.write_bytes(payload.replace(replacement, original, 1))


def _run_test(mutation: Mutation) -> tuple[bool, str]:
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            mutation.test_node,
            "-q",
            "--tb=short",
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
        print(f"[OK] source_ref wiring mutation anchors={len(MUTATIONS)}")
        return 0

    red_count = 0
    restored_count = 0
    for mutation in MUTATIONS:
        _apply(mutation)
        try:
            red, output = _run_test(mutation)
            if not red:
                print(f"[GREEN] {mutation.mutation_id}")
                print(output[-4000:])
            else:
                red_count += 1
                print(f"[RED] {mutation.mutation_id}")
        finally:
            _restore(mutation)
            _assert_anchor(mutation)
            restored_count += 1
    print(
        f"source_ref wiring mutations RED={red_count}/{len(MUTATIONS)} "
        f"restored={restored_count}/{len(MUTATIONS)}"
    )
    return 0 if red_count == len(MUTATIONS) and restored_count == len(MUTATIONS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
