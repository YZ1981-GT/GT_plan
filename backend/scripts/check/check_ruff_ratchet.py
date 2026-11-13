#!/usr/bin/env python
"""Ruff 违规棘轮门禁（只许减少，不许增加）。

背景
----
``backend-lint`` job 自 2026-05-06（commit ``4194e886f``）引入
``python -m ruff check backend/`` 以来**从未通过过**：仓库存量违规 6,566 条，横跨 2,259 个
文件。长期全红的门禁等于没有门禁（没人看），而它同时掩盖了真正的缺陷 —— 本轮就在
``F821`` 里抓出 7 处真实 ``NameError``（``logger`` / ``savepoint`` /
``_cascade_delete_project`` / ``actor_user_id`` / ``tmp_path`` 等），那些在运行时会让端点
直接 500。

处置方式与仓库既有惯例一致（``check_file_size.py`` 的 whitelist 只减不增、
``domain_boundary_governance`` 的 exact-debt baseline）：
**把当前存量冻结成基线，只允许向下**。新增违规立即打红；降到更低时用 ``--update`` 收紧。

规则
----
1. 实测总数 > 基线 ⇒ 退出 1，并列出新增的 (文件, 规则码, 行) 明细。
2. 实测总数 < 基线 ⇒ 退出 0 但提示可以 ``--update`` 收紧（不强制，允许分批偿还）。
3. ``F821``（undefined-name）**不参与棘轮**：它必须恒为 0。该规则只反映真实的未定义名字，
   没有「存量太多」的正当理由 —— 已在本轮清零，回归即时打红。

用法
----
    python backend/scripts/check/check_ruff_ratchet.py            # 校验（CI）
    python backend/scripts/check/check_ruff_ratchet.py --update   # 收紧基线到当前实测值
    python backend/scripts/check/check_ruff_ratchet.py --diff     # 只打印明细

退出码：0=通过 / 1=新增违规或 F821 非零 / 2=ruff 自身执行失败
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
BASELINE = REPO / "backend" / "scripts" / "ruff_ratchet_baseline.json"

#: 不参与棘轮的规则：必须恒为 0。``F821`` = 未定义名字，只有真 bug 才会命中。
MUST_BE_ZERO = ("F821",)


def run_ruff(repo: Path) -> list[dict]:
    proc = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "backend/", "--output-format", "json"],
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8-sig",
        errors="replace",
    )
    if not proc.stdout.strip():
        raise RuntimeError(f"ruff 无输出（rc={proc.returncode}）: {proc.stderr[:400]}")
    return json.loads(proc.stdout)


def fingerprint(repo: Path, item: dict) -> list:
    rel = Path(item["filename"]).resolve().relative_to(repo.resolve()).as_posix()
    return [rel, item["code"], int(item["location"]["row"])]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--update", action="store_true", help="把基线收紧到当前实测值")
    parser.add_argument("--diff", action="store_true", help="只打印明细")
    args = parser.parse_args()

    try:
        items = run_ruff(REPO)
    except Exception as exc:  # noqa: BLE001
        print(f"[ruff-ratchet] ruff 执行失败: {exc}")
        return 2

    by_code = Counter(item["code"] for item in items)
    hard = [item for item in items if item["code"] in MUST_BE_ZERO]
    ratcheted = [item for item in items if item["code"] not in MUST_BE_ZERO]
    total = len(ratcheted)

    if args.diff:
        rows = sorted(fingerprint(REPO, i) for i in ratcheted)
        for rel, code, row in rows[:80]:
            print(f"  {rel}:{row}  {code}")
        print(f"... 共 {total} 条（排除 {', '.join(MUST_BE_ZERO)}）")
        return 0

    if hard:
        print(f"[ruff-ratchet] FAIL: {'/'.join(MUST_BE_ZERO)} 必须为 0，实测 {len(hard)} 条")
        for rel, code, row in sorted(fingerprint(REPO, i) for i in hard)[:40]:
            print(f"    {rel}:{row}  {code}")
        print("    这类规则只反映真实未定义名字，没有「存量豁免」的正当理由。")
        return 1

    if not BASELINE.exists():
        print(f"[ruff-ratchet] 缺少基线文件 {BASELINE}；用 --update 生成")
        return 2

    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    limit = int(baseline["total"])
    known = {tuple(x) for x in baseline.get("fingerprints", [])}

    if args.update:
        baseline["total"] = total
        baseline["by_code"] = dict(sorted(by_code.items()))
        BASELINE.write_text(
            json.dumps(baseline, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"[ruff-ratchet] 基线已收紧: {limit} -> {total}")
        return 0

    if total > limit:
        print(
            f"[ruff-ratchet] FAIL: ruff 违规增加（基线 {limit} -> 实测 {total}，多 {total - limit} 条）"
        )
        # 逐条指纹不落盘（32955 行太大），改为列出当前最多的前 30 条供定位；
        # 与基线的精确差集可用 `--diff` 对照 base ref 的两份输出。
        rows = sorted(fingerprint(REPO, i) for i in ratcheted)
        for rel, code, row in rows[:30]:
            print(f"    {rel}:{row}  {code}")
        print(f"    ... 共 {total} 条；按规则码分布: {dict(sorted(by_code.items(), key=lambda x: -x[1])[:6])}")
        print("    修掉新增项，或（确属历史债）用 --update 收紧基线并说明原因。")
        return 1

    if total < limit:
        print(
            f"[ruff-ratchet] OK: 优于基线（{limit} -> {total}，"
            f"清偿 {limit - total} 条）；建议 --update 收紧"
        )
        return 0

    print(f"[ruff-ratchet] OK: {total} 条，与基线持平")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
