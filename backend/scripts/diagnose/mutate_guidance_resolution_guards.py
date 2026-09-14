#!/usr/bin/env python
"""受控破坏 resolution / provenance 判定链并证明行为守卫会 RED，最后恢复原字节。

补齐 WIP 对账登记的缺口：Task 2 的 `mutate_guidance_source_ref_wiring_guards.py`
只覆盖 source_ref 接线（M01~M04），缺 **resolution 类锚点**（cache race、
race gate 短路、证据失败态被继承伪装）。本脚本专攻后者。

锚点一律用**正则**而非固定缩进字符串，原因有二：
1. `wp_guidance_service.py` 是并发高频修改文件；判定块前每次插入新分支
   （如 `runtime_status == "stale"`）都会让多行字符串锚点整体错行 → ANCHOR-MISS。
2. `schema.json` 是 CRLF 入库，`Path.read_text()` 默认做 universal-newline
   转换，裸 `\\n` 锚点匹配的是转换后的视图而非磁盘字节。

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
# ANCHORS
# ---------------------------------------------------------------------------

#: 证据失败态优先于 parent_inherited。删掉这一整段即「继承内容伪装 stale/invalid」。
#:
#: The anchor is anchored on the ASCII ``if runtime_status == "stale":`` branch
#: rather than on the preceding Chinese comment line: Python bytes literals
#: cannot contain non-ASCII characters, and the comment text is also
#: reworded more often than the code it documents.
_ANCHOR_FAILED_STATUSES_WIN = re.compile(
    rb'if runtime_status == "stale":\s*'
    rb'resolution_status = "stale"\s*'
    rb'elif runtime_status in \{\s*"missing",\s*"invalid"\s*\}:\s*'
    rb'resolution_status = runtime_status\s*'
    rb'elif runtime_entry is None and result\.source == "static_json":\s*'
    rb'resolution_status = "invalid"\s*',
    re.DOTALL,
)

#: static_json 无 runtime contract 不得据 shape 判 exact。
_ANCHOR_STATIC_JSON_INVALID = re.compile(
    rb'elif runtime_entry is None and result\.source == "static_json":\s*'
    rb'resolution_status = "invalid"\s*'
)

#: 缺段必须标 missing，不得落进最终 else 的 "exact"。
_ANCHOR_MISSING_SECTIONS = re.compile(
    rb'elif missing_sections:\s*'
    rb'resolution_status = "missing"\s*'
)

#: parent_inherited 只能由调用方显式 force，不得凭空产生。
_ANCHOR_FORCE_PARENT_INHERITED = re.compile(
    rb'elif force_resolution_status:\s*'
    rb'resolution_status = force_resolution_status\s*'
)


@dataclass(frozen=True)
class ResolutionMutation:
    mutation_id: str
    anchor: re.Pattern[bytes]
    replacement: bytes
    test_node: str
    expected_failure: str


MUTATIONS = (
    ResolutionMutation(
        mutation_id="R01_FAILED_STATUSES_MASKED_BY_PARENT_INHERITED",
        anchor=_ANCHOR_FAILED_STATUSES_WIN,
        replacement=(
            b'        # MISSING: stale/invalid/missing-sections precedence removed\n'
        ),
        test_node=(
            "backend/tests/test_wp_guidance_service_ext.py::"
            "TestGuidanceServiceResolutionChain::"
            "test_stale_runtime_entry_overrides_parent_inherited_success_wording"
        ),
        expected_failure=(
            "test_stale_runtime_entry_overrides_parent_inherited_success_wording"
        ),
    ),
    ResolutionMutation(
        mutation_id="R02_STATIC_JSON_GETS_EXACT",
        anchor=_ANCHOR_STATIC_JSON_INVALID,
        replacement=b'        pass\n',
        test_node=(
            "backend/tests/test_guidance_source_ref_integration.py::"
            "test_source_ref_four_states_reach_every_exact_gate"
        ),
        expected_failure="test_source_ref_four_states_reach_every_exact_gate",
    ),
    ResolutionMutation(
        mutation_id="R03_MISSING_SECTIONS_NOT_DETECTED",
        anchor=_ANCHOR_MISSING_SECTIONS,
        replacement=b'        pass\n',
        test_node=(
            "backend/tests/test_wp_guidance_service_ext.py::"
            "TestGuidanceServiceResolutionChain::"
            "test_runtime_unmapped_blocker_prevents_complete_result_from_becoming_exact"
        ),
        expected_failure=(
            "test_runtime_unmapped_blocker_prevents_complete_result_from_becoming_exact"
        ),
    ),
    ResolutionMutation(
        mutation_id="R04_PARENT_INHERITED_FORCE_IGNORED",
        anchor=_ANCHOR_FORCE_PARENT_INHERITED,
        replacement=b'        pass\n',
        test_node=(
            "backend/tests/test_wp_guidance_service_ext.py::"
            "TestGuidanceServiceResolutionChain::"
            "test_whole_workbook_uses_parent_chain_with_explicit_context"
        ),
        expected_failure=(
            "test_whole_workbook_uses_parent_chain_with_explicit_context"
        ),
    ),
)


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------


def _assert_anchor(mutation: ResolutionMutation) -> None:
    payload = (ROOT / "backend/app/services/wp_guidance_service.py").read_bytes()
    hits = len(mutation.anchor.findall(payload))
    replacement_hits = payload.count(mutation.replacement)
    if hits != 1 or replacement_hits:
        raise RuntimeError(
            f"{mutation.mutation_id}: anchor_hits={hits} replacement_hits={replacement_hits}"
        )


def _apply(mutation: ResolutionMutation) -> tuple[Path, bytes, bytes]:
    path = ROOT / "backend/app/services/wp_guidance_service.py"
    payload = path.read_bytes()
    mutated, n = mutation.anchor.subn(mutation.replacement, payload, count=1)
    if n != 1:
        raise RuntimeError(f"{mutation.mutation_id}: apply anchor 未唯一命中")
    path.write_bytes(mutated)
    return path, payload, mutated


def _restore(mutation: ResolutionMutation, original: bytes) -> None:
    path = ROOT / "backend/app/services/wp_guidance_service.py"
    path.write_bytes(original)
    # Verify restoration byte-for-byte: a silent partial restore would mask a
    # real regression in the file under test.
    assert path.read_bytes() == original, (
        f"{mutation.mutation_id}: bytes not restored exactly"
    )


def _run_test(mutation: ResolutionMutation) -> tuple[bool, str]:
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
        print(f"[OK] resolution mutation anchors={len(MUTATIONS)}")
        return 0

    red_count = 0
    restored_count = 0
    for mutation in MUTATIONS:
        path, original, _ = _apply(mutation)
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
        f"resolution mutations RED={red_count}/{len(MUTATIONS)} "
        f"restored={restored_count}/{len(MUTATIONS)}"
    )
    return 0 if red_count == len(MUTATIONS) and restored_count == len(MUTATIONS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
