"""权威模板里的**外部工作簿链接**普查 —— BP-25（B60 OOXML 安全门）的证据基础。

**Spec: published-representation-production-path-and-lane-adjudication** ·
`blocked_ooxml_gate` 的解除条件裁决

═══ 这个脚本回答的唯一问题 ══════════════════════════════════════════════════════

首版发布宿主对 `xlsx/b60/gt-b60-bundle` 恒落 `blocked_ooxml_gate`
（`gate=external_relationships`，命中 `xl/externalLinks/_rels/externalLink1.xml.rels`）。
当时提出过一条看起来很省的解除路径：**「那些外部链接是死元数据，剔掉即可」**。

本脚本用**生产分词器** `excel_row_shift.iter_qualified_references` 逐份判定：
带 `xl/externalLinks/` 的模板里，究竟有没有公式 / defined name **真的**引用了
外部工作簿（`[N]Sheet!A1` 形态）。

⇒ 如果「真引用数 = 0」，那条路径成立（剔除的是死元数据，不改变任何可见行为）；
⇒ 如果每一份都真引用，那条路径**不存在** —— 剔链接会静默改掉审计底稿的取数。

═══ 为什么必须用生产分词器而不是 grep `[1]` ════════════════════════════════════

`[` 在 Excel 公式里还出现在结构化引用（`Table1[列名]`）与字符串字面量里。
`iter_qualified_references` 与生产改写器 `_rewrite_formula_refs` **共用同一批原语**
（跳字符串字面量 / 实体形态 / 左边界判定），四类误命中防线自动继承。自己 grep 会同时
产生假命中（表名里的 `[`）与漏命中（`&quot;` 实体形态）。

═══ 用法 ════════════════════════════════════════════════════════════════════

    python backend/scripts/check/check_template_external_links.py
    python backend/scripts/check/check_template_external_links.py --json out.json
    # CI：断言「死元数据模板数」恰为 N（当前实测 0）
    python backend/scripts/check/check_template_external_links.py --expect-dead-metadata 0
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any, Final

_REPO_ROOT = Path(__file__).resolve().parents[3]
_BACKEND_ROOT = _REPO_ROOT / "backend"
if str(_BACKEND_ROOT) not in sys.path:  # pragma: no cover - import 自举
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.services.workpaper_sync.excel_row_shift import (  # noqa: E402
    iter_qualified_references,
)

#: 权威模板库（运行时权威，只读）。参考副本 `基础数据/…` 已落后，不扫它。
TEMPLATE_ROOT: Final[Path] = _BACKEND_ROOT / "wp_templates"

#: OOXML 里「外部工作簿链接」这件事的三个物证部件。
EXTERNAL_LINK_DIR: Final[str] = "xl/externalLinks/"
EXTERNAL_LINK_RELS: Final[str] = "xl/externalLinks/_rels/"

_F_TEXT_RE: Final[re.Pattern[str]] = re.compile(r"<f\b[^>]*>(?P<text>.*?)</f>", re.S)
_DEFINED_NAME_RE: Final[re.Pattern[str]] = re.compile(
    r"<definedName\b(?P<attrs>[^>]*)>(?P<text>.*?)</definedName>", re.S
)
_NAME_ATTR_RE: Final[re.Pattern[str]] = re.compile(r'\bname="(?P<v>[^"]*)"')
_TARGET_RE: Final[re.Pattern[str]] = re.compile(r'\bTarget="(?P<v>[^"]*)"')


def _unescape(raw: str) -> str:
    """XML 实体还原，**含数字字符引用**（`&#22351;`）—— 与生产 `_unescape` 同口径。"""
    text = (
        raw.replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&apos;", "'")
    )
    text = re.sub(r"&#(\d+);", lambda m: chr(int(m.group(1))), text)
    return text.replace("&amp;", "&")


def scan_one(path: Path) -> dict[str, Any]:
    """一份模板的外链事实。不抛：损坏的 zip 记 `error` 而不是让普查中断。"""
    row: dict[str, Any] = {
        "template": str(path.relative_to(TEMPLATE_ROOT)).replace("\\", "/"),
        "has_external_link_part": False,
        "has_external_link_rels": False,
        "external_targets": [],
        "external_reference_count": 0,
        "external_reference_samples": [],
        "carriers": {},
        "error": None,
    }
    try:
        with zipfile.ZipFile(path) as zf:
            names = zf.namelist()
            row["has_external_link_part"] = any(
                n.startswith(EXTERNAL_LINK_DIR) for n in names
            )
            row["has_external_link_rels"] = any(
                n.startswith(EXTERNAL_LINK_RELS) for n in names
            )
            if not row["has_external_link_part"]:
                return row
            for name in names:
                if name.startswith(EXTERNAL_LINK_RELS) and name.endswith(".rels"):
                    body = zf.read(name).decode("utf-8", "replace")
                    row["external_targets"].extend(
                        m.group("v") for m in _TARGET_RE.finditer(body)
                    )
            carriers: Counter[str] = Counter()
            samples: list[str] = []
            for name in names:
                if not (
                    name.startswith("xl/worksheets/") and name.endswith(".xml")
                ) and name != "xl/workbook.xml":
                    continue
                body = zf.read(name).decode("utf-8", "replace")
                if name == "xl/workbook.xml":
                    for match in _DEFINED_NAME_RE.finditer(body):
                        text = _unescape(match.group("text") or "")
                        dn_name = ""
                        attr = _NAME_ATTR_RE.search(match.group("attrs") or "")
                        if attr is not None:
                            dn_name = attr.group("v")
                        for ref in iter_qualified_references(text):
                            if ref.kind != "external":
                                continue
                            carriers["defined_name"] += 1
                            if len(samples) < 4:
                                samples.append(f"definedName {dn_name!r}: {ref.raw}")
                    continue
                for match in _F_TEXT_RE.finditer(body):
                    text = _unescape(match.group("text") or "")
                    for ref in iter_qualified_references(text):
                        if ref.kind != "external":
                            continue
                        carriers["formula"] += 1
                        if len(samples) < 4:
                            samples.append(f"{name}: {ref.raw}")
            row["carriers"] = dict(sorted(carriers.items()))
            row["external_reference_count"] = sum(carriers.values())
            row["external_reference_samples"] = samples
    except (zipfile.BadZipFile, OSError) as exc:
        row["error"] = f"{type(exc).__name__}: {exc}"
    return row


def run(*, json_path: Path | None, expect_dead: int | None) -> int:
    if not TEMPLATE_ROOT.is_dir():
        print(f"[FAIL] 权威模板库不存在: {TEMPLATE_ROOT}", file=sys.stderr)
        return 2
    # 🔴 跳过 `~$` 锁文件：用户开着 WPS 时它们会出现，不是模板。
    templates = sorted(
        p
        for p in TEMPLATE_ROOT.rglob("*.xlsx")
        if not p.name.startswith("~$")
    )
    rows = [scan_one(p) for p in templates]
    with_part = [r for r in rows if r["has_external_link_part"]]
    references = [r for r in with_part if r["external_reference_count"] > 0]
    dead = [r for r in with_part if r["external_reference_count"] == 0 and not r["error"]]
    errors = [r for r in rows if r["error"]]

    report = {
        "template_root": str(TEMPLATE_ROOT.relative_to(_REPO_ROOT)).replace("\\", "/"),
        "template_count": len(templates),
        "with_external_link_part": len(with_part),
        "with_external_link_rels": sum(1 for r in with_part if r["has_external_link_rels"]),
        "really_references_external": len(references),
        "dead_metadata": len(dead),
        "unreadable": len(errors),
        "total_external_references": sum(r["external_reference_count"] for r in with_part),
        "carrier_totals": dict(
            sorted(
                Counter(
                    carrier
                    for r in with_part
                    for carrier, n in r["carriers"].items()
                    for _ in range(n)
                ).items()
            )
        ),
        "dead_metadata_templates": [r["template"] for r in dead],
        "entries": rows,
    }
    if json_path is not None:
        json_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8"
        )

    print(f"模板总数                 {report['template_count']}")
    print(f"含 xl/externalLinks/     {report['with_external_link_part']}")
    print(f"  其中含 _rels           {report['with_external_link_rels']}")
    print(f"  **真引用**外部工作簿   {report['really_references_external']}")
    print(f"  死元数据（0 处引用）   {report['dead_metadata']}")
    print(f"外部引用总处数           {report['total_external_references']}")
    print(f"按载体                   {report['carrier_totals']}")
    print(f"读不出的模板             {report['unreadable']}")
    if dead:
        print("死元数据模板：")
        for r in dead[:20]:
            print(f"  - {r['template']}")
    sample = next((r for r in references if r["external_reference_samples"]), None)
    if sample is not None:
        print(f"样本（{sample['template']}）：")
        for line in sample["external_reference_samples"]:
            print(f"  {line}")
        for target in sample["external_targets"][:2]:
            print(f"  Target={target}")

    if expect_dead is not None and report["dead_metadata"] != expect_dead:
        print(
            f"[FAIL] 死元数据模板数 {report['dead_metadata']} != 期望 {expect_dead} —— "
            "「剔除死链接」这条解除路径的前提变了，请重新裁决 B60 的 OOXML 安全门",
            file=sys.stderr,
        )
        return 1
    print("[OK]")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", dest="json_path", default=None, help="报告落盘路径")
    parser.add_argument(
        "--expect-dead-metadata",
        dest="expect_dead",
        type=int,
        default=None,
        help="断言「有 externalLinks 部件但 0 处真引用」的模板数恰为该值",
    )
    args = parser.parse_args()
    return run(
        json_path=Path(args.json_path) if args.json_path else None,
        expect_dead=args.expect_dead,
    )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
