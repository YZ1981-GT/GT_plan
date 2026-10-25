"""模板索引生命周期守卫的受控变异验证。

每条变异只改一个唯一锚点、只跑对应测试，并在 ``finally`` 中按字节 CAS 恢复。
退出 0 表示所有变异都由预期测试精确打红且源文件已恢复。
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class Mutation:
    mutation_id: str
    path: str
    old: str
    new: str
    test_file: str
    test_name: str
    reason: str


MUTATIONS: tuple[Mutation, ...] = (
    Mutation(
        mutation_id="M01",
        path="backend/scripts/ops/setup_wp_templates_dir.py",
        old="    unexpected = set(disk) - set(indexed)\n",
        new="    unexpected = set()  # MUTATION: 忽略 disk→index 差集\n",
        test_file="backend/tests/test_wp_template_index_lifecycle.py",
        test_name="test_validate_index_locks_both_projection_directions",
        reason="删除 disk→index 反向比较必须被双向集合锁打红",
    ),
    Mutation(
        mutation_id="M02",
        path="backend/scripts/ops/setup_wp_templates_dir.py",
        old=(
            "        candidates = sorted(remaining_by_stem.get("
            "_stem_identity(old[\"relative_path\"]), []))\n"
        ),
        new="        candidates = []  # MUTATION: 禁用扩展名同 stem 继承\n",
        test_file="backend/tests/test_wp_template_index_lifecycle.py",
        test_name="test_full_projection_preserves_extension_slot_parent_code_and_roles",
        reason="A17 .doc→.docx 不继承旧槽位/人工字段时必须打红",
    ),
    Mutation(
        mutation_id="M03",
        path="backend/app/services/wp_template_finder.py",
        old=(
            "        if e[\"wp_code\"] == wp_code\n"
            "        and e[\"format\"] in (\"xlsx\", \"xlsm\", \"docx\")\n"
            "        and _is_bundle_entry(e)\n"
        ),
        new=(
            "        if e[\"wp_code\"] == wp_code\n"
            "        and e[\"format\"] in (\"xlsx\", \"xlsm\", \"docx\")\n"
        ),
        test_file="backend/tests/test_wp_template_index_lifecycle.py",
        test_name="test_finder_role_separation_uses_index_as_single_source",
        reason="whole_workbook/dedicated_subtemplate 重新混入普通 merge 时必须打红",
    ),
    Mutation(
        mutation_id="M04",
        path="backend/app/services/wp_template_finder.py",
        old="    fingerprint = hashlib.sha256(raw).hexdigest()\n",
        new="    fingerprint = \"fixed-fingerprint\"  # MUTATION: 永不感知内容替换\n",
        test_file="backend/tests/test_wp_template_index_lifecycle.py",
        test_name="test_finder_cache_reloads_same_size_atomic_replace_and_returns_copies",
        reason="同尺寸且 mtime 回拨的原子替换仍命中旧缓存时必须打红",
    ),
)


def _anchor_for_bytes(text: str, sample: str) -> str:
    if "\r\n" in text:
        return sample.replace("\n", "\r\n")
    return sample


def _check_anchor(mutation: Mutation) -> tuple[Path, bytes, bytes]:
    path = REPO_ROOT / mutation.path
    original = path.read_bytes()
    text = original.decode("utf-8")
    old = _anchor_for_bytes(text, mutation.old)
    new = _anchor_for_bytes(text, mutation.new)
    count = text.count(old)
    if count != 1:
        raise RuntimeError(
            f"{mutation.mutation_id} ANCHOR-MISS: {mutation.path} 命中 {count} 次（应为 1）"
        )
    mutated = text.replace(old, new, 1).encode("utf-8")
    return path, original, mutated


def run_mutation(mutation: Mutation) -> bool:
    path, original, mutated = _check_anchor(mutation)
    path.write_bytes(mutated)
    restore_ok = False
    try:
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                mutation.test_file,
                "-q",
                "--tb=short",
                "-k",
                mutation.test_name,
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )
        output = proc.stdout + proc.stderr
        red = proc.returncode != 0 and mutation.test_name in output
        state = "RED" if red else "WRONG-TEST/GREEN"
        print(f"[{state}] {mutation.mutation_id} {mutation.reason}")
        if not red:
            print(output[-3000:])
        return red
    finally:
        current = path.read_bytes()
        if current == mutated:
            path.write_bytes(original)
            restore_ok = path.read_bytes() == original
        elif current == original:
            restore_ok = True
        else:
            print(
                f"[RESTORE-BLOCKED] {mutation.mutation_id} {mutation.path} "
                "在变异期间被其他进程改写；为避免覆盖并发工作，未强制恢复",
                file=sys.stderr,
            )
        if not restore_ok:
            raise RuntimeError(f"{mutation.mutation_id} 未能按字节恢复 {mutation.path}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check-anchors",
        action="store_true",
        help="只验证每个锚点恰命中一次，不执行变异",
    )
    parser.add_argument(
        "--run",
        help="逗号分隔的 mutation id；默认执行全部",
    )
    args = parser.parse_args(argv)
    selected_ids = set(args.run.split(",")) if args.run else None
    selected = [
        mutation
        for mutation in MUTATIONS
        if selected_ids is None or mutation.mutation_id in selected_ids
    ]
    if not selected:
        print("[FAIL] 没有选中任何变异", file=sys.stderr)
        return 2

    try:
        for mutation in selected:
            _check_anchor(mutation)
    except (OSError, UnicodeDecodeError, RuntimeError) as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 2
    print(f"[ANCHORS] {len(selected)}/{len(selected)} unique")
    if args.check_anchors:
        return 0

    results = [run_mutation(mutation) for mutation in selected]
    passed = sum(results)
    print(f"[SUMMARY] RED={passed}/{len(results)} restored={len(results)}/{len(results)}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
