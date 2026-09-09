#!/usr/bin/env python
"""受控破坏 G-HANDOFF-CONSUMER 守卫，证明行为守卫会 RED，最后按字节复原。

覆盖 spec Requirement 13 的五条 load-bearing 判据：

* M-CAND-EXACT  candidate handoff 若能产 ACCEPTED → 提前可见（13.1）
* M-SECTIONS    finalized 跳过九段校验 → 缺段被 ACCEPTED（13.3）
* M-DIGEST-CONST compute_handoff_digest 退化常量 → 内容变 digest 不变（13.2/13.7）
* M-VIS-REJECT  REJECTED ACK 仍置 ACTIVE → 未 ACK entry 暴露（13.5/13.6）
* M-ACK-IDEM    record_ack 丢幂等短路 → 重复提交产生第二行（13.4）

四态判定与锚点纪律沿用 ``mutate_common`` 约定，但本脚本按字节级读写（目标文件
为 LF），以便直接嵌在多行 Python 源码上做锚点。

用法：
    python backend/scripts/diagnose/mutate_guidance_handoff_consumer_guards.py --check-anchors
    python backend/scripts/diagnose/mutate_guidance_handoff_consumer_guards.py
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

SVC = "backend/app/services/guidance_handoff_consumer_service.py"
TEST = "backend/tests/test_guidance_handoff_consumer.py"


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
    Mutation(
        mutation_id="M-CAND-EXACT",
        relative_path=SVC,
        original=b'    return VerificationResult(verdict="review_pending", handoff_digest=digest)',
        replacement=b'    return VerificationResult(verdict=ACK_ACCEPTED, handoff_digest=digest)',
        test_node=f"{TEST}::test_candidate_handoff_is_review_pending_never_accepted",
        expected_failure="test_candidate_handoff_is_review_pending_never_accepted",
        why="candidate 也能产 ACCEPTED → candidate 提前成为 exact/可见",
    ),
    Mutation(
        mutation_id="M-SECTIONS",
        relative_path=SVC,
        original=b"    reasons.extend(_check_sections(handoff))",
        replacement=b"    reasons.extend([])  # BUG: skip section check",
        test_node=f"{TEST}::test_finalized_missing_section_rejected",
        expected_failure="test_finalized_missing_section_rejected",
        why="finalized 跳过九段/refs 校验 → 缺段 handoff 被 ACCEPTED",
    ),
    Mutation(
        mutation_id="M-DIGEST-CONST",
        relative_path=SVC,
        original=(
            b"    canonical = json.dumps(\n"
            b"        handoff, sort_keys=True, separators=(\",\", \":\"), ensure_ascii=False, default=str\n"
            b"    )\n"
            b"    return hashlib.sha256(canonical.encode(\"utf-8\")).hexdigest()"
        ),
        replacement=b'    return "0" * 64  # BUG: constant digest',
        test_node=f"{TEST}::test_handoff_digest_changes_with_content",
        expected_failure="test_handoff_digest_changes_with_content",
        why="digest 退化常量 → 内容变化检测不到 → 幂等键与 stale 判定失效",
    ),
    Mutation(
        mutation_id="M-VIS-REJECT",
        relative_path=SVC,
        original=b"    if all_accepted:\n        state = VISIBILITY_ACTIVE",
        replacement=b"    if True:\n        state = VISIBILITY_ACTIVE",
        test_node=f"{TEST}::test_visibility_rejected_keeps_zero",
        expected_failure="test_visibility_rejected_keeps_zero",
        why="REJECTED ACK 仍置 ACTIVE → 未通过验证的 entry 被暴露",
    ),
    Mutation(
        mutation_id="M-ACK-IDEM",
        relative_path=SVC,
        original=b"    if existing is not None:\n        return existing",
        replacement=b"    if False and existing is not None:\n        return existing",
        test_node=f"{TEST}::test_ack_ledger_is_durable_and_idempotent",
        expected_failure="test_ack_ledger_is_durable_and_idempotent",
        why="record_ack 丢幂等短路 → 重复提交产生第二行 → ledger 不再幂等",
    ),
)


def _assert_anchor(m: Mutation) -> None:
    payload = (ROOT / m.relative_path).read_bytes()
    count = payload.count(m.original)
    replacement_count = payload.count(m.replacement)
    if count != 1 or replacement_count:
        raise RuntimeError(f"{m.mutation_id}: anchor={count} replacement={replacement_count}")


def _apply(m: Mutation) -> None:
    path = ROOT / m.relative_path
    payload = path.read_bytes()
    if payload.count(m.original) != 1:
        raise RuntimeError(f"{m.mutation_id}: apply anchor 不唯一")
    path.write_bytes(payload.replace(m.original, m.replacement, 1))


def _restore(m: Mutation) -> None:
    path = ROOT / m.relative_path
    payload = path.read_bytes()
    if payload.count(m.replacement) != 1:
        raise RuntimeError(f"{m.mutation_id}: restore anchor 不唯一")
    path.write_bytes(payload.replace(m.replacement, m.original, 1))


def _run_test(m: Mutation) -> tuple[bool, str]:
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", m.test_node, "-q", "--tb=short", "-p", "no:cacheprovider"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    output = f"{completed.stdout}\n{completed.stderr}"
    red = completed.returncode != 0 and m.expected_failure in output
    return red, output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-anchors", action="store_true")
    args = parser.parse_args()

    if args.check_anchors:
        for m in MUTATIONS:
            _assert_anchor(m)
        print(f"[OK] handoff-consumer mutation anchors={len(MUTATIONS)}")
        return 0

    red_count = 0
    restored = 0
    for m in MUTATIONS:
        _assert_anchor(m)
        _apply(m)
        try:
            red, _ = _run_test(m)
        finally:
            _restore(m)
            restored += 1
        state = "RED" if red else "GREEN"
        if red:
            red_count += 1
        print(f"[{state:5}] {m.mutation_id}  {m.why}")

    print(f"handoff-consumer mutations RED={red_count}/{len(MUTATIONS)} restored={restored}/{len(MUTATIONS)}")
    return 0 if red_count == len(MUTATIONS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
