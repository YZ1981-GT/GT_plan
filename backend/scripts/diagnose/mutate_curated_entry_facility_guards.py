# -*- coding: utf-8 -*-
"""curated-entry facility 变异检验：证明 Task 4 的守卫真的锁死了每条结构约束。

spec: `workpaper-sync-curated-entry-facility` / Task 4
Requirements: 5.2（Property 6：mutation coverage）

对**真实生产文件** `backend/scripts/gen/generate_workpaper_sync_manifest.py` 逐条施加变异，
跑相关 curated 守卫测试，期望每条变异都被**至少一条**守卫打红（RED）。这是 anti-false-green
机制：若某条变异没打红（GREEN），说明守卫是重言式/字符串存在性判据，是**守卫缺陷**。

## 四态判定（只看失败/出错测试名集合，不看退出码）

- RED         打红了且**正是**预期那条测试（守卫有效）
- GREEN       改了生产行为却无任何判据变红（守卫缺陷，必修，不删变异）
- ANCHOR-MISS 锚点未命中或命中 >1 处（脚本缺陷）。含 \\n 跨行锚点在 CRLF 必 MISS，故全部单行片段
- WRONG-TEST  打红了但不是预期项（污染残留 / 锚点错行 / 收集期整模块 ERROR 但 want 不在其中）

## 锚点（Requirement 5.2 逐字点名的 4 条）

  A1 allow bidirectional WITHOUT adapter/evidence
     —— 把 `if capability == "bidirectional":` 短路成 `if False:`，三条 bidirectional 纪律
        （adapter_id / html_store / contract_test）全部失效 ⇒ builder 的 bidirectional 守卫红
  A2 drop the collision guard
     —— 把 `if entry_id in discovery_entry_ids:` 短路成 `if False:` ⇒ curated id 撞 discovery
        id 不再 fail-closed ⇒ collision 守卫红
  A3 drop the host_path existence guard
     —— 把 host_path 存在性判断短路成 `if False:` ⇒ 挂在不存在 host 上不再 fail-closed ⇒
        missing-host 守卫红
  A4 exclude curated from manifest_digest
     —— 把 `manifest["curated_source_digest"] = _curated_source_digest(` 改成赋给一个
        丢弃变量 ⇒ curated_source_digest 不再进入 manifest 字典/预映像 ⇒
        「curated_source_digest 参与 manifest_digest」的自洽守卫红

## 用法（仓库根 d:\\GT_plan）

    python backend/scripts/diagnose/mutate_curated_entry_facility_guards.py --list
    python backend/scripts/diagnose/mutate_curated_entry_facility_guards.py --check-anchors
    python backend/scripts/diagnose/mutate_curated_entry_facility_guards.py --run all
    python backend/scripts/diagnose/mutate_curated_entry_facility_guards.py --run A1,A4

🔴 铁律：
- 单行 exact 锚点（\\n 跨行在 CRLF 必 MISS），每条须命中**恰好一次**。
- 生产文件用**原始字节备份**在 finally 里还原，即使测试运行被 ^C 中断也还原。
- pytest 经 `subprocess.run([...])` **不经 shell** 调（`-k "a or b"` 才不被拆），
  且 `PYTHONIOENCODING=utf-8`（中文输出 + GBK 控制台会静默吞成 None ⇒ 误判 GREEN）。
- 收集 FAILED 与 ERROR 两者（`-rAE`）：契约漂移会让 module fixture 抛异常 ⇒ 整模块 ERROR 非 FAILED。
- 禁后台执行（孤儿 python + 前台同时变异 ⇒ 还原失败）；无 --restore 子命令。
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

# 本脚本在 backend/scripts/diagnose/ ⇒ 仓库根是 parents[3]（坑：parents[2] 会双拼 backend/backend）。
_REPO = Path(__file__).resolve().parents[3]
_SRC = _REPO / "backend" / "scripts" / "gen" / "generate_workpaper_sync_manifest.py"

# 短 nodeid（basename），带 backend/ 前缀会让 want 子串匹配失败。
_FACILITY = "test_curated_entry_facility.py"
_BUILDER = "test_curated_entry_builder.py"
_INTEGRATION = "test_curated_entry_integration.py"
_BASELINE = "test_curated_entry_facility_baseline.py"

# 变异跑的守卫文件集合（含 Task 1/2/3 三文件，确保「现有测试仍能捕获」也被验证）。
_TEST_FILES = [
    f"backend/tests/workpaper_sync/{_FACILITY}",
    f"backend/tests/workpaper_sync/{_BUILDER}",
    f"backend/tests/workpaper_sync/{_INTEGRATION}",
    f"backend/tests/workpaper_sync/{_BASELINE}",
]


@dataclass
class Mutation:
    mid: str
    intent: str
    anchor: str  # 单行 exact 片段（原样出现在生产文件里）
    new: str  # 替换后的行内容（缩进自动沿用原行）
    want: str  # 预期打红的测试方法名（短 nodeid 子串）
    result: str = ""
    fired: list[str] = field(default_factory=list)


MUTATIONS: list[Mutation] = [
    Mutation(
        "A1",
        "allow bidirectional WITHOUT adapter/evidence（短路 bidirectional 纪律门）",
        anchor='        if capability == "bidirectional":',
        new='        if False:  # (mutated A1: allow bidirectional without adapter/evidence)',
        want="test_bidirectional_without_adapter_fails_closed",
    ),
    Mutation(
        "A2",
        "drop the collision guard（curated id 撞 discovery id 不再 fail-closed）",
        anchor="        if entry_id in discovery_entry_ids:",
        new="        if False:  # (mutated A2: drop collision guard)",
        want="test_collision_fails_closed",
    ),
    Mutation(
        "A3",
        "drop the host_path existence guard（挂不存在 host 不再 fail-closed）",
        anchor="        if not isinstance(host_path, str) or host_path not in discovered_host_paths:",
        new="        if False:  # (mutated A3: drop host_path existence guard)",
        want="test_missing_host_fails_closed",
    ),
    Mutation(
        "A4",
        "exclude curated from manifest_digest（curated_source_digest 不进 manifest 字典）",
        anchor='        manifest["curated_source_digest"] = _curated_source_digest(',
        new="        _curated_digest_excluded_from_manifest = _curated_source_digest(",
        want="test_curated_source_digest_actually_covers_manifest_digest",
    ),
]


def _locate(lines: list[str], anchor: str) -> list[int]:
    return [i for i, ln in enumerate(lines) if anchor in ln]


def _check_anchors() -> int:
    """只读校验每条锚点在生产文件里命中恰好一次（不施加变异，秒级、可反复复验）。"""
    text = _SRC.read_text(encoding="utf-8")
    lines = text.splitlines()
    bad = 0
    for m in MUTATIONS:
        hits = _locate(lines, m.anchor)
        status = "OK" if len(hits) == 1 else f"MISS({len(hits)})"
        if len(hits) != 1:
            bad += 1
        print(f"[{m.mid}] anchor {status}: {m.intent}")
    if bad:
        print(f"🔴 {bad} 条锚点未命中恰好一次 ⇒ 脚本需修（生产源可能已漂移）。")
        return 1
    print("✅ 全部锚点各命中恰好一次。")
    return 0


def _run_tests() -> tuple[set[str], set[str]]:
    """跑守卫文件集，返回 (FAILED 方法名集合, ERROR 方法名集合)。

    🔴 UTF-8 显式解码：pytest 中文输出在 Windows GBK 控制台会 UnicodeDecodeError；
    text=True 会静默吞成 None ⇒ 解析到 0 个 FAILED，把有效守卫误判 GREEN。
    契约漂移让 fixture 抛异常 ⇒ pytest 报 **ERROR** 而非 FAILED，故两者都收集（-rAE）。
    subprocess 传 list 不经 shell，避免参数被拆。
    """
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", *_TEST_FILES, "-rAE", "--tb=no", "-p", "no:cacheprovider"],
        cwd=str(_REPO),
        capture_output=True,
        env=env,
    )
    out = proc.stdout.decode("utf-8", "replace") + proc.stderr.decode("utf-8", "replace")
    failed: set[str] = set()
    errored: set[str] = set()
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("FAILED "):
            failed.add(line[len("FAILED "):].split(" ")[0].split("::")[-1])
        elif line.startswith("ERROR "):
            errored.add(line[len("ERROR "):].split(" ")[0].split("::")[-1])
    return failed, errored


def _apply(m: Mutation) -> tuple[bool, str]:
    """把单行锚点替换成 m.new（沿用原行缩进与行尾）。命中数 != 1 拒绝施加。"""
    text = _SRC.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    hits = [i for i, ln in enumerate(lines) if m.anchor in ln]
    if len(hits) != 1:
        return False, f"命中 {len(hits)} 行"
    idx = hits[0]
    orig = lines[idx]
    indent = orig[: len(orig) - len(orig.lstrip())]
    lines[idx] = indent + m.new.lstrip() + ("\n" if orig.endswith(("\n", "\r\n")) else "")
    _SRC.write_text("".join(lines), encoding="utf-8")
    return True, orig


def _run(selected: list[str]) -> int:
    original = _SRC.read_bytes()  # 原始字节备份，finally 里无条件还原。
    try:
        for m in MUTATIONS:
            if selected != ["all"] and m.mid not in selected:
                continue
            ok, note = _apply(m)
            if not ok:
                m.result = "ANCHOR-MISS"
                print(f"[{m.mid}] ANCHOR-MISS: {note}")
                _SRC.write_bytes(original)
                continue
            try:
                failed, errored = _run_tests()
            finally:
                _SRC.write_bytes(original)  # 每条变异测完立即还原，即使中断也还原。
            fired = failed | errored
            m.fired = sorted(fired)
            if not fired:
                m.result = "GREEN"
            elif any(m.want in f for f in fired):
                m.result = "RED"
            else:
                m.result = "WRONG-TEST"
            print(f"[{m.mid}] {m.result} fired={m.fired or '()'}  <= {m.intent}")
    finally:
        _SRC.write_bytes(original)

    # 还原后必须回到全绿（证明变异脚本没留下污染）。
    restored_fail, restored_err = _run_tests()
    restored = sorted(restored_fail | restored_err)
    considered = [m for m in MUTATIONS if m.result]
    red = sum(1 for m in considered if m.result == "RED")
    bad = [m.mid for m in considered if m.result in {"GREEN", "ANCHOR-MISS", "WRONG-TEST"}]
    print("=" * 72)
    print(f"汇总: RED={red}/{len(considered)}  问题项={bad or '无'}  还原后失败={restored or '无'}")
    # 还原验证：生产文件字节必须与运行前逐字节一致。
    restored_ok = _SRC.read_bytes() == original
    print(f"生产文件字节还原: {'✅ 一致' if restored_ok else '🔴 不一致（污染！）'}")
    if bad or restored or not restored_ok:
        print("🔴 GREEN=守卫缺陷 / ANCHOR-MISS=脚本缺陷 / WRONG-TEST=锚点错行 / 还原后不绿或字节漂移=污染")
        return 1
    print("✅ 全部变异被守卫捕获（RED），还原后回到全绿且生产文件字节完全一致。")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--list", action="store_true", help="列出锚点与预期打红的测试")
    ap.add_argument("--check-anchors", action="store_true", help="只读校验锚点命中数（不变异）")
    ap.add_argument("--run", nargs="?", const="all", default=None, help="all 或逗号分隔的锚点 id")
    args = ap.parse_args()
    if args.list:
        for m in MUTATIONS:
            print(f"{m.mid}: {m.intent}\n    want={m.want}")
        return 0
    if args.check_anchors:
        return _check_anchors()
    if args.run is not None:
        selected = ["all"] if args.run == "all" else [s.strip() for s in args.run.split(",")]
        return _run(selected)
    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
