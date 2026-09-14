# -*- coding: utf-8 -*-
"""Task 20：往生产源码里**注入**旧 `_version` / `file_version` / 直接 commit 路径，
看 writer/version domain 门是否真的打红。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 1 Task 20
Requirements: 2.1, 2.2, 2.12, 9.11 · Property 4, Property 61

═══ 为什么必须是「注入」而不是「短路」═══

Task 20 的判据是一句**否定式承诺**：「已迁移的 writer 不再有旧版本域路径」。否定式承诺不能
靠删代码来 falsify —— 删掉一行只会让「不存在」更成立。唯一的证伪方式是把那条路径**加回去**，
然后看门是否点名。

═══ 与变异脚本的分工 ═══

`mutate_task20_writer_gate_guards.py` 改的是**判据机器**（生成器 / 门），跑的是 pytest 守卫。
本脚本改的是**业务生产源码**，量的是**门自己的准则计数**：注入 → 重生成清册 → 跑门 → 记录每条
准则的行名变化 → 还原 → 重生成 → 校验 digest 回到注入前。

因此本脚本还顺带证明了一件事：清册的 fail-closed 是真的 —— 注入后**不**重生成时，门不是
「照旧评估」而是直接拒绝（`source digest is stale`，见 `stale_gate_exit` 字段）。

用法（仓库根）::

    python backend/scripts/diagnose/inject_task20_legacy_version_paths.py --list
    python backend/scripts/diagnose/inject_task20_legacy_version_paths.py --run all \\
        --out .kiro/specs/.../evidence/task20-writer-gate/injection_report.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[3]
GENERATOR = "backend/scripts/gen/generate_workpaper_writer_inventory.py"
GATE = "backend/scripts/check/check_workpaper_writer_revision_gate.py"
INVENTORY = REPO / "backend" / "data" / "workpaper_writer_inventory.json"

HTML_SAVE = "backend/app/routers/wp_html_save.py"
STORAGE = "backend/app/services/wp_storage_service.py"
UPGRADER = "backend/app/services/workpaper_sync/excel_instrumentation.py"


@dataclass(frozen=True)
class Injection:
    id: str
    path: str
    anchor: str
    inject: str
    #: 期望「这一行」出现在这些准则里（注入前不在）。
    expect_rows: dict[str, str]
    #: 期望这些准则的计数变小（例如某行离开了 artifact-snapshot 类别）。
    expect_lost_rows: dict[str, str] = field(default_factory=dict)
    why: str = ""


INJECTIONS: list[Injection] = [
    Injection(
        id="I1",
        path=HTML_SAVE,
        anchor="    try:\n        receipt = await mutation_service.commit_html_projection(",
        inject="    wp.file_version = int(wp.file_version or 0) + 1\n",
        expect_rows={
            "keeps_legacy_write_path_beside_unified_commit": "app.routers.wp_html_save::save_html_data",
            "writes_legacy_version_field": "app.routers.wp_html_save::save_html_data",
        },
        why="把 Task 18 删掉的 `file_version` 计数器加回到**已经**经过统一入口的 writer 旁边。"
            "这是 Property 4 的双 revision 形态：一次业务应用推进两个计数器",
    ),
    Injection(
        id="I2",
        path=HTML_SAVE,
        anchor="    try:\n        receipt = await mutation_service.commit_html_projection(",
        inject="    wp.parsed_data['_version'] = 2\n",
        expect_rows={
            "keeps_legacy_write_path_beside_unified_commit": "app.routers.wp_html_save::save_html_data",
            "writes_legacy_version_field": "app.routers.wp_html_save::save_html_data",
        },
        why="Task 3 的原始头号发现：HTML 保存自己拿 `parsed_data._version` 当乐观锁。"
            "旧域换个位置（parsed_data 里的键）也必须被认出来",
    ),
    Injection(
        id="I3",
        path=HTML_SAVE,
        anchor="    try:\n        receipt = await mutation_service.commit_html_projection(",
        inject="    await db.commit()\n",
        expect_rows={
            "keeps_legacy_write_path_beside_unified_commit": "app.routers.wp_html_save::save_html_data",
            "owns_direct_commit": "app.routers.wp_html_save::save_html_data",
        },
        why="第二个事务边界：一次业务写入落在两个事务里（Requirement 2.4 / 13.1）。"
            "注意它既不写 legacy 字段也不写 content_revision —— 只有把 commit 也算进"
            "双 revision 准则里才抓得到",
    ),
    Injection(
        id="I4",
        path=STORAGE,
        anchor="        shutil.copy2(str(file_path), str(version_path))",
        inject="        wp.file_version = int(wp.file_version or 0) + 1\n",
        expect_rows={
            "writes_legacy_version_field": "app.services.wp_storage_service::WpStorageService.save_version",
            "bypasses_unified_commit": "app.services.wp_storage_service::WpStorageService.save_version",
        },
        why="artifact-snapshot 类别的 falsifier：把 Task 19 删掉的伪版本推进加回来 ⇒ 该行重新"
            "持久化业务内容 ⇒ **失去**类别、回到门里。证明类别不是一张豁免名单",
    ),
    Injection(
        id="I5",
        path=UPGRADER,
        anchor="        candidate = await self._repo.create_upgrade_candidate(",
        inject="        await self._repo.bump_content_revision(wp_id=wp_id, expected=0)\n",
        expect_rows={
            "representation_upgrade_increments_business_revision": (
                "app.services.workpaper_sync.excel_instrumentation::"
                "ExcelInstrumentationUpgrader.stage_and_register_candidate"
            )
        },
        why="Property 4 的另一半：纯 representation 升级不得推进业务 revision。升级器不在"
            "`entries` 里，所以这条只能由 `representation_upgrade_lane` 分母来判",
    ),
]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run(args: list[str]) -> tuple[int, str]:
    proc = subprocess.run(
        [sys.executable, *args],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def _gate_issues() -> dict[str, list[str]]:
    code, out = _run([GATE, "--json"])
    # `--json` 只在结构合法时输出 issue map；结构非法（例如清册过期）时是 [FAIL] 文本。
    # 用 `raw_decode` 而不是 `json.loads(out[start:])`：JSON 后面还跟着 `[BLOCKED]` 一行，
    # 前面可能有 SyntaxWarning，两头都是 "Extra data"。
    decoder = json.JSONDecoder()
    start = out.find("{")
    while start >= 0:
        try:
            value, _ = decoder.raw_decode(out[start:])
        except json.JSONDecodeError:
            start = out.find("{", start + 1)
            continue
        if isinstance(value, dict) and "bypasses_unified_commit" in value:
            return value
        start = out.find("{", start + 1)
    raise RuntimeError(f"gate did not emit an issue map (exit={code}):\n{out[-800:]}")


def _regenerate() -> None:
    code, out = _run([GENERATOR, "--apply"])
    if code != 0:
        raise RuntimeError(f"regeneration failed (exit={code}):\n{out[-800:]}")


def _apply_injection(case: Injection) -> None:
    path = REPO / case.path
    text = path.read_text(encoding="utf-8")
    # 锚点按**规范化换行**定位，工作树是 CRLF 时跨行锚点否则必然 ANCHOR-MISS。
    eol = "\r\n" if "\r\n" in text else "\n"
    normalized = text.replace("\r\n", "\n")
    anchor = case.anchor.replace("\r\n", "\n")
    hits = normalized.count(anchor)
    if hits != 1:
        raise RuntimeError(f"{case.id}: anchor hit {hits} times (must be exactly 1)")
    patched = normalized.replace(anchor, case.inject.replace("\r\n", "\n") + anchor, 1)
    path.write_text(patched.replace("\n", eol) if eol == "\r\n" else patched, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--run", nargs="?", const="all")
    parser.add_argument("--out")
    args = parser.parse_args(argv)

    if args.list or not args.run:
        for case in INJECTIONS:
            print(f"{case.id}  {case.path}")
            print(f"      inject: {case.inject.strip()}")
            print(f"      expect: {sorted(case.expect_rows)}")
        return 0

    selected = (
        INJECTIONS
        if args.run == "all"
        else [case for case in INJECTIONS if case.id in args.run.split(",")]
    )
    if not selected:
        print(f"[FAIL] no injection matches {args.run!r}")
        return 2

    baseline_digest = json.loads(INVENTORY.read_text(encoding="utf-8"))["inventory_digest"]
    baseline_issues = _gate_issues()
    results: list[dict[str, Any]] = []
    verdicts: list[str] = []

    for case in selected:
        path = REPO / case.path
        original = path.read_bytes()
        original_sha = _sha256(path)
        record: dict[str, Any] = {
            "id": case.id,
            "path": case.path,
            "inject": case.inject.strip(),
            "why": case.why,
        }
        try:
            _apply_injection(case)
            # 先证明 fail-closed：注入后**不**重生成时，门必须拒绝评估而不是照旧评估。
            stale_code, stale_out = _run([GATE])
            record["stale_gate_exit"] = stale_code
            record["stale_gate_refused"] = "source digest is stale" in stale_out

            _regenerate()
            issues = _gate_issues()
            gate_code, _ = _run([GATE])
            record["gate_exit_after_injection"] = gate_code

            gained: dict[str, list[str]] = {}
            lost: dict[str, list[str]] = {}
            for name in sorted(set(issues) | set(baseline_issues)):
                before = set(baseline_issues.get(name, []))
                after = set(issues.get(name, []))
                if after - before:
                    gained[name] = sorted(after - before)
                if before - after:
                    lost[name] = sorted(before - after)
            record["criteria_gained"] = gained
            record["criteria_lost"] = lost
            record["counts_before"] = {k: len(v) for k, v in sorted(baseline_issues.items())}
            record["counts_after"] = {k: len(v) for k, v in sorted(issues.items())}

            missing = [
                f"{criterion}:{row}"
                for criterion, row in case.expect_rows.items()
                if row not in gained.get(criterion, [])
            ]
            unexpected_lost = [
                f"{criterion}:{row}"
                for criterion, row in case.expect_lost_rows.items()
                if row not in lost.get(criterion, [])
            ]
            if missing or unexpected_lost:
                record["verdict"] = "GREEN"
                record["missing"] = missing + unexpected_lost
            else:
                record["verdict"] = "RED"
        finally:
            path.write_bytes(original)
            restored_sha = _sha256(path)
            record["restored_byte_identical"] = restored_sha == original_sha
            _regenerate()
            record["inventory_digest_restored"] = (
                json.loads(INVENTORY.read_text(encoding="utf-8"))["inventory_digest"]
                == baseline_digest
            )
        verdicts.append(record.get("verdict", "ERROR"))
        results.append(record)
        print(
            f"[{record.get('verdict', 'ERROR')}] {case.id} "
            f"gained={ {k: len(v) for k, v in record.get('criteria_gained', {}).items()} } "
            f"stale_refused={record.get('stale_gate_refused')} "
            f"restored={record.get('restored_byte_identical')} "
            f"digest_back={record.get('inventory_digest_restored')}"
        )

    report = {
        "baseline_inventory_digest": baseline_digest,
        "baseline_counts": {k: len(v) for k, v in sorted(baseline_issues.items())},
        "verdict_histogram": {v: verdicts.count(v) for v in sorted(set(verdicts))},
        "injections": results,
    }
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"[OUT] {out}")

    failures = [item for item in results if item.get("verdict") != "RED"]
    dirty = [
        item
        for item in results
        if not item.get("restored_byte_identical")
        or not item.get("inventory_digest_restored")
    ]
    if dirty:
        print(f"[FAIL] {len(dirty)} injections did not restore cleanly: "
              f"{[item['id'] for item in dirty]}")
        return 2
    if failures:
        print(f"[FAIL] {len(failures)} injections did not turn the gate red: "
              f"{[item['id'] for item in failures]}")
        return 1
    print(f"[OK] all {len(results)} injected legacy paths are reported by the gate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
