"""章节映射守卫的变异检验 —— 逐条施加变异、按「失败测试名差集」判红，字节级还原 + md5 核验.

spec: soe-listed-note-conversion-correctness / Task 11（Task 18 在此基础上扩清单）

被测守卫 = ``backend/tests/test_note_conversion_section_mapping.py``（Property 5~10 /
16~19 / 24~26 / 35 / 36）。design.md「变异检验清单」里属章节映射的 4 条
（``_map_disclosure_notes`` 改回 ``count(*)`` / 去掉 ``legacy_section_ids`` 追加 /
改 ``note_section`` 而不改 ``binding_id`` 前缀 / 对 ``section_id IS NULL`` 静默跳过）
已在 M1/M2/M3/M4 落地；另补 5 条（失败隔离、归档留痕、新建章节号、``format_adapted``
无条件计数、**Property 24 判据被改严**）。

🔴 **M9 是口径锁死**：design.md Property 24 明写「同类内调用也算」。M9 把判据改成
「必须有服务文件之外的调用方」，守卫必须打红 —— 否则 ``_map_*`` 这类正常私有子步骤
会被误判成孤儿，逼人把私有子步骤提成公开 API（制造第二个入口 = 双真源）。

判据三态（memory 铁律）：
  RED         = 变异后新增失败测试 -> 守卫有效
  GREEN       = 变异后无新增失败   -> **守卫缺陷**
  ANCHOR-MISS = 锚点未命中或命中数 != 1 -> **脚本缺陷**（不得当 GREEN 处理）

用法：
  python backend/scripts/check/mutate_note_conversion_section_mapping_guards.py            # 全量
  python backend/scripts/check/mutate_note_conversion_section_mapping_guards.py --only M3  # 单条
  python backend/scripts/check/mutate_note_conversion_section_mapping_guards.py --restore  # 从 .bak 强制还原
"""
from __future__ import annotations

import argparse
import hashlib
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent / "mutate_note_conversion_section_mapping_guards.report.txt"

SVC = ROOT / "backend" / "app" / "services" / "note_conversion_service.py"
V2R = ROOT / "backend" / "tests" / "test_note_conversion_v2_removal.py"
TARGET_TESTS = "backend/tests/test_note_conversion_section_mapping.py"


@dataclass
class Mutation:
    mid: str
    desc: str
    path: Path
    #: 锚点：整行原文（含缩进）。``line`` 非 None 时改按行号定位（用于同形多处出现）
    old_line: str
    new_line: str
    line: int | None = None
    expect_tests: tuple[str, ...] = ()


MUTATIONS: list[Mutation] = [
    Mutation(
        "M1",
        "mapped 改回 count(*) 冒充（存量行数当映射数）",
        SVC,
        "        notes = list(notes_result.scalars().all())",
        '        notes = list(notes_result.scalars().all()); result["mapped"] = len(notes)  # MUT',
        # 🔴 Task 15/16 落地后该行形态在 `_rollback_section_state`(L954) 也出现一次
        # ⇒ 必须按行号锚定到 `_map_disclosure_notes`(1638-2146) 内那一处，否则
        # 「锚点命中 2 处」= ANCHOR-MISS，变异根本没施加（既不是 RED 也不是 GREEN）。
        line=1781,
        expect_tests=("test_zero_common_sections_returns_mapped_zero",),
    ),
    Mutation(
        "M2",
        "去掉 template_lineage.legacy_section_ids 追加",
        SVC,
        '            changed |= _append_unique(lineage, "legacy_section_ids", legacy_section_id)',
        "            pass  # MUT: 不再追加 legacy_section_ids",
        expect_tests=("test_legacy_section_ids_recorded_for_every_mapped",),
    ),
    Mutation(
        "M3",
        "改 note_section 但不改 binding_id 前缀（binding 静默失联）",
        SVC,
        "                        rewritten = _rewrite_binding_id_prefix(new_td, old_number, new_number)",
        "                        rewritten = 0  # MUT: 不改 binding 前缀",
        expect_tests=("test_prefix_rewritten_and_old_number_recorded",),
    ),
    Mutation(
        "M4",
        "section_id IS NULL 回填不出时静默跳过（不登记 skipped）",
        SVC,
        '                            await skip(how, detail="按 (note_section, section_title) 回填源侧 sid 失败")',
        "                            pass  # MUT: 静默跳过，不登记原因码",
        expect_tests=("test_unresolvable_rows_are_skipped_with_reason_not_silently",),
    ),
    Mutation(
        "M5",
        "逐章节失败隔离失效（异常冒出 _map_disclosure_notes）",
        SVC,
        "            except Exception as exc:  # noqa: BLE001 — 逐章节隔离，失败不阻断其余",
        "            except ValueError as exc:  # MUT: 只捕 ValueError，注入的 RuntimeError 会冒泡",
        # 🔴 行号随 Task 15/16（preview 端点 + rollback）增长而漂移：1189 现在是
        # `)`。目标是 `_map_disclosure_notes` 的 **map_section** 阶段隔离（注入点
        # `_record_lineage` 在其内），不是 2105 的 create_section 阶段。
        line=2000,
        expect_tests=("test_single_section_failure_does_not_block_the_rest",),
    ),
    Mutation(
        "M6",
        "归档不写 template_lineage.archived_sections",
        SVC,
        '                lineage["archived_sections"] = items',
        "                pass  # MUT: 不写 archived_sections",
        expect_tests=("test_source_only_archived_with_sid_and_reason",),
    ),
    Mutation(
        "M7",
        "新建空章节把 note_section 写成 sid（历史 v2 缺陷形态）",
        SVC,
        "                        note_section=new_number,",
        "                        note_section=tgt_sid,  # MUT: legacy compat 缺陷形态",
        expect_tests=("test_created_notes_are_empty_drafts_with_real_chapter_number",),
    ),
    Mutation(
        "M8",
        "format_adapted 改回无条件计数（空操作被上报成已适配）",
        SVC,
        "                            if report.changed:",
        "                            if True:  # MUT: 无条件计数",
        expect_tests=("test_format_adapted_is_zero_while_field_mapping_all_null",),
    ),
    Mutation(
        "M9",
        "把 Property 24 判据改严：排除服务文件自身（私有子步骤会被误判成孤儿）",
        V2R,
        '        if "/tests/" in f"/{rel}" or path.name.startswith("test_"):',
        '        if "/tests/" in f"/{rel}" or path.name.startswith("test_") or rel.endswith("note_conversion_service.py"):  # MUT',
        expect_tests=(
            "test_self_call_counts_as_consumer",
            "test_no_method_is_orphaned",
        ),
    ),
]


def md5(p: Path) -> str:
    return hashlib.md5(p.read_bytes()).hexdigest()


def run_tests() -> tuple[set[str], str]:
    """跑目标测试文件，返回（失败测试名集合, 摘要行）。"""
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", TARGET_TESTS, "-q", "--tb=no", "-rf",
         "-p", "no:cacheprovider"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    text = proc.stdout + proc.stderr
    names = set(re.findall(r"^(?:FAILED|ERROR)\s+\S+?::(?:\w+::)?(\w+)", text, re.M))
    tail = [ln for ln in text.splitlines() if re.search(r"\d+ (passed|failed|error)", ln)]
    return names, (tail[-1] if tail else "(无摘要)")


def apply_mutation(m: Mutation) -> str | None:
    """施加变异。返回 None 表示成功，否则返回 ANCHOR-MISS 原因。"""
    src = m.path.read_text(encoding="utf-8")
    lines = src.splitlines(keepends=True)
    if m.line is not None:
        idx = m.line - 1
        if idx >= len(lines):
            return f"行号 {m.line} 越界（文件 {len(lines)} 行）"
        if lines[idx].rstrip("\r\n") != m.old_line:
            return f"L{m.line} 内容与锚点不符：{lines[idx].rstrip()!r}"
        targets = [idx]
    else:
        targets = [i for i, ln in enumerate(lines) if ln.rstrip("\r\n") == m.old_line]
        if len(targets) != 1:
            return f"锚点命中 {len(targets)} 处（要求恰好 1 处）"
    eol = "\r\n" if lines[targets[0]].endswith("\r\n") else "\n"
    lines[targets[0]] = m.new_line + eol
    m.path.write_bytes("".join(lines).encode("utf-8"))
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only")
    ap.add_argument("--restore", action="store_true")
    args = ap.parse_args()

    paths = sorted({m.path for m in MUTATIONS})
    baks = {p: p.with_suffix(p.suffix + ".t11bak") for p in paths}

    if args.restore:
        report = []
        for p, b in baks.items():
            if b.exists():
                p.write_bytes(b.read_bytes())
                b.unlink()
                report.append(f"[RESTORED] {p.name} md5={md5(p)}")
            else:
                report.append(f"[SKIP] 无备份 {b.name}")
        print("\n".join(report))
        return 0

    # 备份 + 记基线 md5
    original: dict[Path, bytes] = {}
    base_md5: dict[Path, str] = {}
    for p in paths:
        original[p] = p.read_bytes()
        base_md5[p] = md5(p)
        baks[p].write_bytes(original[p])

    log: list[str] = []
    log.append("=== 基线 ===")
    for p in paths:
        log.append(f"  {p.name} md5={base_md5[p]}")
    baseline_fails, baseline_tail = run_tests()
    log.append(f"  baseline: {baseline_tail}")
    log.append(f"  baseline 失败集合: {sorted(baseline_fails) or '[]'}")
    log.append("")

    verdicts: list[tuple[str, str]] = []
    try:
        for m in MUTATIONS:
            if args.only and m.mid != args.only:
                continue
            log.append(f"=== {m.mid} {m.desc} ===")
            miss = apply_mutation(m)
            if miss:
                verdicts.append((m.mid, "ANCHOR-MISS"))
                log.append(f"  [ANCHOR-MISS] {miss}")
                # 还原以防半成品
                for p in paths:
                    p.write_bytes(original[p])
                continue
            fails, tail = run_tests()
            new_fails = fails - baseline_fails
            log.append(f"  {tail}")
            log.append(f"  新增失败: {sorted(new_fails) or '[]'}")
            if new_fails:
                verdicts.append((m.mid, "RED"))
                missing = [t for t in m.expect_tests if t not in new_fails]
                if missing:
                    log.append(f"  [注意] 预期打红但未红的用例: {missing}")
            else:
                verdicts.append((m.mid, "GREEN=守卫缺陷"))
            # 逐条还原（字节级）
            for p in paths:
                p.write_bytes(original[p])
            for p in paths:
                assert md5(p) == base_md5[p], f"{p.name} 还原后 md5 不符"
            log.append("  [还原] md5 核验通过")
            log.append("")
    finally:
        for p in paths:
            p.write_bytes(original[p])
        ok = all(md5(p) == base_md5[p] for p in paths)
        log.append(f"=== 收尾还原: {'md5 全部一致' if ok else '🔴 md5 不一致，请用 --restore'} ===")
        for p in paths:
            log.append(f"  {p.name} md5={md5(p)}")

    log.append("")
    log.append("=== 判定汇总 ===")
    for mid, v in verdicts:
        log.append(f"  {mid}: {v}")
    reds = sum(1 for _, v in verdicts if v == "RED")
    log.append(f"  RED {reds} / {len(verdicts)}")

    OUT.write_text("\n".join(log), encoding="utf-8")
    print("\n".join(log[-25:]))
    return 0 if reds == len(verdicts) else 1


if __name__ == "__main__":
    raise SystemExit(main())
