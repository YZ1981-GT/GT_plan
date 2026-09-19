#!/usr/bin/env python3
"""
update_abcs_confirmation_ledger.py — Task 5.4 底稿可维护性收敛

把 A/B/C/S 循环 + confirmation 跨循环共享底稿（D0/E0/F0/G0/H0/K0/L0 函证 bundle）
登记进 Capability Ledger v2，并按「能力级」而非「整条」记录覆盖/豁免：

  - displayPrefs/agingConfig/version/review/ai：由 GtWpRenderer Runtime Boundary
    一次性 provide，全部标 covered + evidence=["GtWpRenderer:Runtime_Boundary"]，
    check 会归类为 runtime-boundary（RUNTIME_CAPABILITIES 之内，不产生漂移）。
  - persistence/acnr/importExport：扫描该底稿的候选源文件（root Gt{code}*.vue +
    对应子目录）检出真实接线；检出→covered（带文件级证据）；
    未检出且为纯文档/目录/程序表类→importExport 能力级 exempt（理由：无动态明细行）；
    其余未检出→unknown（fail-open）。

绝不使用 entry 级 blanket exemption；每条 exemption 绑定单一 capability + 理由 +
批准角色 + 复核日期（Req 1.3）。仅重写 A/B/C/S + confirmation-bundle 条目，
不触碰 D1~D7/E1/F1~F5/G1~G14/H1~H10/I/J/K1~K18/L1~L8/M/N（并行 wave 负责）。

零依赖（仅 stdlib）。显式 UTF-8。

Usage:
    python update_abcs_confirmation_ledger.py            # 写回
    python update_abcs_confirmation_ledger.py --check    # 仅打印，不写

Feature: workpaper-maintainability-convergence / Task 5.4
Requirements: 1.3, 2, 7
"""
from __future__ import annotations

import json
import re
import sys
from datetime import date
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
from capability_ledger import CAPABILITIES, SCHEMA_VERSION, capability_record  # noqa: E402

PROJECT_ROOT = SCRIPT_DIR.parent.parent.parent
WP_CODE_OVERRIDES_PATH = PROJECT_ROOT / "backend" / "app" / "data" / "wp_code_overrides.json"
WORKPAPER_DIR = PROJECT_ROOT / "audit-platform" / "frontend" / "src" / "components" / "workpaper"
LEDGER_PATH = WORKPAPER_DIR / "coverage-ledger.json"

WP_ROOT_RE = re.compile(r"^([A-Z]\d+)")
SKIP_TYPES = {"skip", "onlyoffice-sheet", "word-template", "redirect-materiality"}

# confirmation 跨循环共享 bundle 的根编码（D0/E0/F0/G0/H0/K0/L0）
CONFIRMATION_BUNDLE_CODES = {"D0", "E0", "F0", "G0", "H0", "K0", "L0"}

RUNTIME_EVIDENCE = ["GtWpRenderer:Runtime_Boundary"]
RUNTIME_CAPS = ("displayPrefs", "agingConfig", "version", "review", "ai")
BUSINESS_CAPS = ("persistence", "acnr", "importExport")

TODAY = date.today().isoformat()

# 能力检测正则（对齐 generate_coverage_ledger.py）
DETECT = {
    "persistence": [re.compile(r"useChecklistPersistence"), re.compile(r"checklist-responses")],
    "acnr": [re.compile(r"useAcnr"), re.compile(r"GtIndexChip"), re.compile(r"address_registry", re.I)],
    "importExport": [
        re.compile(
            r"use[A-Z]\w*ImportExport|useWorkpaperImportExport|useXImportExport"
        )
    ],
}

# 「纯文档/目录/静态程序表/检查清单」类 componentType —— 无动态明细行表格，
# 按项目铁律「动态行表格才需要导入导出」，importExport 能力级豁免。
DOC_LIKE_TYPES = {
    "a1-dashboard", "a2-adjustment-console", "a3-consolidation-console",
    "a-program-console", "b-index", "h-static-doc", "independence-signing",
    "wp-popup-signing", "a1-11-signing-form", "audit-legend", "review-checklist",
    "analytical-review", "a17-summary", "kam-workpaper", "regulatory-letter",
    "report-analysis", "misstatement-summary", "misstatement-workpaper",
    "contingent-liability", "discontinued-operations", "segment-report",
    "goodwill-impairment", "checklist-table", "a14-3-workbook",
    "b50-risk-assessment", "b22a-control-matrix", "b22b-deficiency-evaluation",
    "b23-process-control", "b30-group-audit", "c1-entity-level-control",
    "c22-itgc-bundle", "c23-journal-entry-control", "c24-journal-entry-detail",
    "c25-internal-audit-reliance", "c26-info-processing-control", "c-control-test",
    "c-note-table", "confirmation-summary", "confirmation-entity-verify",
    "confirmation-followup", "confirmation-diff-reconcile", "confirmation-reliability",
    "confirmation-fraud-risk", "confirmation-hub",
    "s3-policy-change", "s4-nonmonetary-exchange", "s5-debt-restructuring",
    "s6-fund-occupation", "s12-cpa-expert", "s13-mgmt-expert",
    "s14-accounting-estimate", "s15-eps-roe", "s20-revenue-deduction",
}
DOC_LIKE_SUFFIXES = ("-bundle",)


def _rel(p: Path) -> str:
    return p.relative_to(PROJECT_ROOT).as_posix()


def load_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def in_scope(code: str) -> bool:
    if code in CONFIRMATION_BUNDLE_CODES:
        return True
    return code[:1] in {"A", "B", "C", "S"}


def scope_root_codes(overrides: dict) -> set[str]:
    codes: set[str] = set()
    for code, ctype in overrides.items():
        if ctype in SKIP_TYPES:
            continue
        m = WP_ROOT_RE.match(code)
        if not m:
            continue
        root = m.group(1)
        if in_scope(root):
            codes.add(root)
    return codes


def representative_component_type(root: str, overrides: dict) -> str | None:
    exact = overrides.get(root)
    if exact and exact not in SKIP_TYPES:
        return exact
    from collections import Counter
    cands = [
        ctype for code, ctype in overrides.items()
        if ctype not in SKIP_TYPES and (m := WP_ROOT_RE.match(code)) and m.group(1) == root
    ]
    return Counter(cands).most_common(1)[0][0] if cands else None


# code → 候选子目录（相对 WORKPAPER_DIR），用于检出 S/confirmation 的能力接线
def candidate_dirs(root: str) -> list[Path]:
    dirs: list[Path] = []
    if root in CONFIRMATION_BUNDLE_CODES:
        dirs += [WORKPAPER_DIR / "confirmation", WORKPAPER_DIR / "g0-confirmation"]
        if root == "K0":
            dirs.append(WORKPAPER_DIR / "confirmation" / "k0-confirmation")
        if root == "L0":
            dirs.append(WORKPAPER_DIR / "confirmation" / "l0-confirmation")
    if root[:1] == "S":
        # 仅该编码专属的 s{n}-* 子目录（如 S3→s3-policy-change / S34→s34-ipo-bundle）；
        # 不扫描共享的 s-checklist，避免把通用检查表能力误挂到每个 S 编码。
        n = root[1:]
        for d in WORKPAPER_DIR.iterdir():
            if d.is_dir() and re.match(rf"^s{n}-", d.name):
                dirs.append(d)
    return [d for d in dirs if d.exists()]


# 从 GtXxx.vue 文件名精确提取编码根（A1 不得匹配 A10/A11）
_ENTRY_FILE_RE = re.compile(r"^Gt([A-Z]\d+(?:-\d+)?)\D*\.vue$")


def candidate_files(root: str) -> list[Path]:
    files: list[Path] = []
    # root 级 Gt{code}*.vue（按提取编码根精确匹配，避免 A1↔A10 交叉污染）
    if WORKPAPER_DIR.exists():
        for f in WORKPAPER_DIR.iterdir():
            if not f.is_file():
                continue
            m = _ENTRY_FILE_RE.match(f.name)
            if m and (WP_ROOT_RE.match(m.group(1)) or [None])[0] is not None:
                fm = WP_ROOT_RE.match(m.group(1))
                if fm and fm.group(1) == root:
                    files.append(f)
    for d in candidate_dirs(root):
        files += [p for p in d.rglob("*.vue")]
        files += [p for p in d.rglob("*.ts")]
    # 去重
    seen: set[Path] = set()
    out: list[Path] = []
    for f in files:
        if f not in seen:
            seen.add(f)
            out.append(f)
    return out


def detect_business(root: str) -> dict[str, list[str]]:
    """返回 {capability: [evidence...]}（仅 BUSINESS_CAPS，检出才有证据）。"""
    result: dict[str, list[str]] = {c: [] for c in BUSINESS_CAPS}
    for f in candidate_files(root):
        try:
            content = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for cap in BUSINESS_CAPS:
            if result[cap]:
                continue
            for pat in DETECT[cap]:
                if pat.search(content):
                    result[cap] = [f"{_rel(f)}:{pat.pattern}"]
                    break
    return result


def build_capabilities(root: str, ctype: str | None) -> dict:
    records: dict = {}
    for cap in RUNTIME_CAPS:
        records[cap] = capability_record("covered", list(RUNTIME_EVIDENCE))
    detected = detect_business(root)
    doc_like = bool(ctype) and (ctype in DOC_LIKE_TYPES or ctype.endswith(DOC_LIKE_SUFFIXES))
    for cap in BUSINESS_CAPS:
        ev = detected[cap]
        if ev:
            records[cap] = capability_record("covered", ev)
        elif cap == "importExport" and doc_like:
            records[cap] = capability_record(
                "exempt",
                exemption={
                    "reason": "文档/目录/程序表/检查清单类底稿无动态明细行表格，不适用导入导出（项目铁律：动态行表格才需要导入导出）",
                    "capability": "importExport",
                    "approvedBy": "manager",
                    "approvedAt": TODAY,
                    "reviewAt": TODAY,
                },
            )
        else:
            records[cap] = capability_record("unknown")
    return records


def main() -> int:
    check_only = "--check" in sys.argv
    overrides = load_json(WP_CODE_OVERRIDES_PATH)
    ledger = load_json(LEDGER_PATH)
    ledger["schemaVersion"] = SCHEMA_VERSION
    ledger.setdefault("capabilities", list(CAPABILITIES))
    entries = ledger.setdefault("entries", {})

    roots = sorted(scope_root_codes(overrides))
    updated = 0
    for root in roots:
        ctype = representative_component_type(root, overrides)
        caps = build_capabilities(root, ctype)
        entry = entries.get(root, {})
        # 保留/清理：确保无 entry 级 exemption（v2 禁止）
        entry.pop("exemption", None)
        entry["componentType"] = ctype
        # entryFile：优先 root Gt{code}*.vue，否则留空由 componentType 表达
        entry_file = None
        for f in candidate_files(root):
            if f.parent == WORKPAPER_DIR and f.name.startswith(f"Gt{root}"):
                entry_file = _rel(f)
                break
        if entry_file:
            entry["entryFile"] = entry_file
        elif "entryFile" not in entry:
            entry["entryFile"] = None
        entry["capabilities"] = caps
        entries[root] = entry
        updated += 1
        exempts = [c for c in BUSINESS_CAPS if caps[c]["status"] == "exempt"]
        covered = [c for c in BUSINESS_CAPS if caps[c]["status"] == "covered"]
        print(
            f"  {root:5s} [{ctype or '-'}] "
            f"covered(bus)={covered or '-'} exempt={exempts or '-'}"
        )

    print(f"\n[SCOPE] A/B/C/S + confirmation-bundle 共更新 {updated} 条")
    if check_only:
        print("[CHECK] 预演模式，未写入。")
        return 0
    with open(LEDGER_PATH, "w", encoding="utf-8") as f:
        json.dump(ledger, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"[OK] 已写入 {_rel(LEDGER_PATH)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
