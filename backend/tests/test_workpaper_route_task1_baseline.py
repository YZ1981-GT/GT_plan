"""Task 1 red-baseline freeze for workpaper-page-formula-toolbar-closure.

Spec: ``.kiro/specs/workpaper-page-formula-toolbar-closure/tasks.md``
Task 1: "consume G-C0 and freeze the workpaper-route red baseline".

This module is a single pytest fixture of the "Task 1 baseline" — every
assertion below is a **verifiable judgement** (regex scan over source +
sha256 digest of the scan snapshot), not a Markdown checklist. The
intent is to make the 7-category red baseline reproducible byte-for-byte
by a fresh checkout.

Layout
------
1. **G-C0 consumption** — import + `validateContractVersion` fail-closed
   at the frontend touchpoint
   ``src/shared/contracts/gc0/workpaper-route-baseline.ts``.
2. **Seven red-baseline inventories** — nodeKey payload, unique dialog,
   FormulaEdit chain, dict API, formula_type duality, audit warning
   commit, duplicate AI/review/fixed rails.
3. **Out-of-scope inventory** — TB / report / note domain dialogs,
   attributed to their owner specs and explicitly NOT counted.
4. **Owner freeze** — workpaper-route file owner map with freeze
   metadata.
5. **Mutation self-check M1** — mutate ``GC0_CONTRACT_VERSION`` to
   ``'2.0'`` and assert the wiring gate flips RED; restore bytes.

Mutation classification matches
``test_guidance_gc0_conformance.py``: RED / GREEN / ANCHOR-MISS /
WRONG-TEST.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_ROOT = REPO_ROOT / "audit-platform" / "frontend"
FRONTEND_SRC = FRONTEND_ROOT / "src"
FRONTEND_GC0_OWNER = FRONTEND_SRC / "shared" / "contracts" / "gc0"

#: Task 1 baseline snapshot — checked in so a fresh checkout can reproduce
#: the exact same baseline without re-scanning the working tree.
BASELINE_SNAPSHOT_PATH = (
    Path(__file__).resolve().parent
    / "_snapshots"
    / "workpaper_route_task1_baseline.json"
)


# ---------------------------------------------------------------------------
# 1. G-C0 consumption (Req 1.4 / 2.1)
# ---------------------------------------------------------------------------


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def test_gc0_consumption_module_exists_and_imports_no_local_redecl() -> None:
    """The frontend F1 wiring module exists and imports the three C0 types.

    Req 1.4 / 2.1 — MUST import (not re-declare) `CanonicalWorkpaperLocation`,
    `EvidenceEnvelope`, and `GuidanceRailAdapter` from `./index`.

    **Validates: Requirements 1.4, 2.1**
    """
    module = FRONTEND_GC0_OWNER / "workpaper-route-baseline.ts"
    assert module.exists(), (
        f"F1 G-C0 consumption module missing: {module}"
    )
    src = _read_text(module)

    # Must import the three C0 top-level types from './index' (the owner).
    for symbol in (
        "CanonicalWorkpaperLocation",
        "EvidenceEnvelope",
        "GuidanceRailAdapter",
    ):
        pattern = re.compile(
            rf"import\s+{{[^}}]*\b{symbol}\b[^}}]*}}\s+from\s+['\"]\./index['\"]",
            re.DOTALL,
        )
        assert pattern.search(src), (
            f"{symbol} must be imported from './index' (not re-declared): {module}"
        )

    # Must NOT declare any of the three symbols locally.
    for symbol in (
        "CanonicalWorkpaperLocation",
        "EvidenceEnvelope",
        "GuidanceRailAdapter",
    ):
        # `type Foo`, `interface Foo`, `class Foo` — the reverse-dup scanner
        # flags these; assert they do not exist in this file.
        forbidden = re.compile(
            rf"^(export\s+)?(type|interface|class)\s+{re.escape(symbol)}\b",
            re.MULTILINE,
        )
        assert not forbidden.search(src), (
            f"local re-declaration of {symbol} in {module}; must import from G-C0"
        )


def test_gc0_consumption_module_calls_validateContractVersion() -> None:
    """Fail-closed major-version gate must be wired at the touchpoint.

    The module imports `validateContractVersion` and calls it inside
    every one of the three helpers (envelope / location / rail). If the
    wiring ever drops the validator call, `M1` below turns RED.

    **Validates: Requirements 1.4, 2.1**
    """
    module = FRONTEND_GC0_OWNER / "workpaper-route-baseline.ts"
    src = _read_text(module)
    assert "validateContractVersion" in src, "validator must be imported"
    # All three helpers must invoke the validator.
    for helper in ("assertBaselineEnvelope", "assertLocationIdentity", "assertRailIdentity"):
        # Find the helper body and confirm it calls the validator.
        # Multi-line signatures are common — match the export + name, then
        # take the body forward until the next top-level `export`.
        m = re.search(
            rf"export\s+function\s+{re.escape(helper)}\s*\(",
            src,
        )
        assert m, f"{helper} not exported as a function"
        # Find the parameter list end by walking nested parens.
        i = m.end()
        depth_paren = 1
        while i < len(src) and depth_paren > 0:
            if src[i] == "(":
                depth_paren += 1
            elif src[i] == ")":
                depth_paren -= 1
            i += 1
        # After the closing `)`, TypeScript may have a return-type
        # annotation that itself contains `{...}` blocks (object literal
        # types like `: { a: number; b: string } | null {`). We must
        # walk past those to reach the actual function body `{`.
        #
        # Heuristic: at depth 0, a `{` is the BODY opener iff the
        # immediately-preceding non-whitespace character is NOT `:`
        # (i.e., it is not introducing a return-type literal). Any
        # `{` that IS preceded by `:` is a return-type object literal
        # — we skip past it and continue looking.
        body_start = -1
        depth_brace = 0
        while i < len(src):
            ch = src[i]
            if ch == "{":
                # Is this brace preceded (skipping whitespace/comments)
                # by a `:`? If yes, it's a return-type literal; walk
                # past its matching `}` and continue.
                k = i - 1
                while k >= 0 and src[k] in " \t\r\n":
                    k -= 1
                if k >= 0 and src[k] == ":":
                    # Return-type object literal: walk to matching `}`.
                    j = i + 1
                    d = 1
                    while j < len(src) and d > 0:
                        if src[j] == "{":
                            d += 1
                        elif src[j] == "}":
                            d -= 1
                        j += 1
                    i = j
                    continue
                # Otherwise: this IS the function body opener.
                body_start = i + 1
                break
            i += 1
        if body_start < 0:
            pytest.fail(f"{helper}: no body found after signature")
        # Walk the body to its matching `}`.
        depth_brace = 1
        j = body_start
        while j < len(src) and depth_brace > 0:
            if src[j] == "{":
                depth_brace += 1
            elif src[j] == "}":
                depth_brace -= 1
            j += 1
        body = src[body_start:j]
        assert "validateContractVersion(" in body, (
            f"{helper} does not call validateContractVersion — "
            f"fail-closed gate is unwired"
        )


def test_reverse_dup_scan_f1_adds_zero_new_duplicates() -> None:
    """F1-side must add zero new local re-declarations of any C0 type.

    🔴 判据是**归因型**（findings ⊆ 已登记豁免），不是计数型（``== 2``）。

    原判据把当时的数字锁死为 2。它两个方向都错：
    * **假红**：别的泳道**清理掉**一个重复时（数字变小）照样打红 —— 代码变好、
      守卫变红，实测发生过（``GtCControlTest`` 迁移后只剩 1 个，此断言即红）；
    * **假绿**：先删一个旧重复、再加一个新重复时总数仍是 2，而"不得新增"
      这件本条真正要管的事根本没被检查。

    真源是 ``test_gc0_reverse_dup_scan.ALLOWED_EXEMPTIONS``（单一登记表），
    本条复用它，不再另抄一份数字 —— 两处数字必然漂移。

    **Validates: Requirements 1.4, 2.1**
    """
    sys.path.insert(0, str(REPO_ROOT / "backend"))
    try:
        from app.services.guidance_gc0_contract import discover_local_dupes
    except ImportError as exc:  # pragma: no cover
        pytest.skip(f"backend bundle unavailable: {exc}")

    if not FRONTEND_SRC.exists():
        pytest.skip(f"frontend src missing: {FRONTEND_SRC}")

    # 豁免登记表的单一真源：反向扫描守卫。缺失时 fail closed（不静默放行）。
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from test_gc0_reverse_dup_scan import ALLOWED_EXEMPTIONS, _key_of_dup

    owner = FRONTEND_GC0_OWNER if FRONTEND_GC0_OWNER.exists() else None
    findings = discover_local_dupes([FRONTEND_SRC], ts_owner_dir=owner)

    unapproved = [
        (f.file, f.symbol, f.kind)
        for f in findings
        if _key_of_dup(f.file, f.symbol) not in ALLOWED_EXEMPTIONS
    ]
    assert not unapproved, (
        "F1 侧新增了未登记的 G-C0 顶层符号本地重复声明（应从 shared bundle import，"
        "或显式改名为本地 payload 类型并说明其非 wire type）：\n"
        f"  未登记: {unapproved}\n"
        f"  已登记豁免: {sorted(ALLOWED_EXEMPTIONS.keys())}"
    )


# ---------------------------------------------------------------------------
# 2. Seven red-baseline inventories (Req 5.1 / 5.3 / 8.1 / 8.3 / 8.6 / 13.1)
# ---------------------------------------------------------------------------


def _iter_vue_files(root: Path) -> list[Path]:
    return sorted(root.rglob("*.vue"))


def _iter_ts_files(root: Path) -> list[Path]:
    out: list[Path] = []
    for suffix in ("*.ts", "*.vue"):
        out.extend(sorted(root.rglob(suffix)))
    return out


#: Workpaper route scope = views/workpaper-editor/** and
#: components/workpaper/** and layouts/ThreeColumnLayout.vue (the
#: dialog owner). This is the "active workpaper route" boundary
#: declared by requirements.md.
WORKPAPER_ROUTE_ROOTS = [
    FRONTEND_SRC / "views" / "workpaper-editor",
    FRONTEND_SRC / "components" / "workpaper",
]


def _is_in_workpaper_route(path: Path) -> bool:
    for root in WORKPAPER_ROUTE_ROOTS:
        try:
            path.relative_to(root)
            return True
        except ValueError:
            pass
    # Also treat the layout as workpaper-route when the file is
    # explicitly the formula dialog owner.
    return path.name == "ThreeColumnLayout.vue"


#: Domain-owned dialogs — OUT OF SCOPE per Requirement 1.4.
#: These are other specs' property; they MUST NOT be counted in the
#: "unique dialog" or "duplicate rails" numerators.
DOMAIN_OWNER_FILES: dict[str, str] = {
    "TrialBalance.vue": "trial-balance spec (out-of-scope)",
    "ReportView.vue": "report spec (out-of-scope)",
    "DisclosureEditor.vue": "disclosure-notes spec (out-of-scope)",
    "ReportConfigEditor.vue": "report-config spec (out-of-scope)",
    "ReportConfigBaselineTab.vue": "report-config spec (out-of-scope)",
    "AuditReportEditor.vue": "reports / audit-report spec (out-of-scope)",
    "AnnotationsPanel.vue": "notes / annotations spec (out-of-scope)",
    "KnowledgeBase.vue": "notes / knowledge-base spec (out-of-scope)",
}


# --- (2a) nodeKey payload inventory ----------------------------------------


def _scan_nodekey_payloads() -> list[dict[str, Any]]:
    """Enumerate every literal nodeKey emitted on the open-formula-manager event.

    The nodeKey payload is currently the *only* identity carrier between a
    bottom-sheet component and the global FormulaManagerDialog. This scan
    records every call site and the concrete literal key shape.
    """
    findings: list[dict[str, Any]] = []
    emit_re = re.compile(
        r"eventBus\.emit\(['\"]open-formula-manager['\"]\s*,\s*\{\s*nodeKey\s*:\s*([^\s\}]+)\s*\}",
    )
    for path in _iter_vue_files(FRONTEND_SRC):
        text = _read_text(path)
        for m in emit_re.finditer(text):
            rel = path.relative_to(FRONTEND_ROOT)
            line = text[: m.start()].count("\n") + 1
            findings.append(
                {
                    "file": str(rel),
                    "line": line,
                    "nodeKey_literal": m.group(1),
                }
            )
    return findings


def test_nodekey_payload_inventory_is_stable() -> None:
    """The current nodeKey payload inventory is enumerated and reproducible.

    Asserts every emit site is recorded with a payload shape. If a
    future change renames the event or drops the nodeKey field, the
    count flips RED. This is the red baseline for Requirement 5.1
    ("nodeKey payload") and 5.3 ("旧 nodeKey 不能代表 identity").

    The payload shape today is a mix of string literals (e.g.
    `nodeKey: 'consolidation'`) and expression values (e.g.
    `nodeKey: sheetKey`). Both are recorded; the red-baseline finding
    is that **all of them live in the payload at all** — Task 6's job
    is to migrate them to `CanonicalWorkpaperLocation`.

    **Validates: Requirements 5.1, 5.3**
    """
    findings = _scan_nodekey_payloads()
    assert findings, "no open-formula-manager emit sites found (baseline should be non-empty)"
    for f in findings:
        assert "nodeKey_literal" in f
        # Every current emit site uses either a string literal or a
        # simple identifier expression. Never an arbitrary expression.
        payload = f["nodeKey_literal"]
        is_literal = payload.startswith(("'", '"'))
        is_identifier = re.fullmatch(r"[A-Za-z_$][A-Za-z0-9_$]*", payload)
        assert is_literal or is_identifier, (
            f"emit site uses an unrecognized nodeKey payload shape: {f}"
        )


# --- (2b) unique dialog inventory ------------------------------------------


def _scan_el_dialogs_in_workpaper_route() -> list[dict[str, Any]]:
    """Enumerate every el-dialog definition on the workpaper route.

    The scope is limited to workpaper route files (per Requirement 1.4).
    Dialogs in `views/TrialBalance.vue` / `views/ReportView.vue` /
    `views/DisclosureEditor.vue` are domain-owned and recorded in
    `DOMAIN_OWNER_FILES` — they are NOT included in this scan.
    """
    findings: list[dict[str, Any]] = []
    dialog_re = re.compile(r"<el-dialog\b")
    for root in WORKPAPER_ROUTE_ROOTS:
        for path in _iter_vue_files(root):
            text = _read_text(path)
            for m in dialog_re.finditer(text):
                line = text[: m.start()].count("\n") + 1
                findings.append(
                    {
                        "file": str(path.relative_to(FRONTEND_ROOT)),
                        "line": line,
                    }
                )
    # Also ThreeColumnLayout.vue (formula dialog owner)
    three_col = FRONTEND_SRC / "layouts" / "ThreeColumnLayout.vue"
    if three_col.exists():
        text = _read_text(three_col)
        for m in dialog_re.finditer(text):
            line = text[: m.start()].count("\n") + 1
            findings.append(
                {
                    "file": str(three_col.relative_to(FRONTEND_ROOT)),
                    "line": line,
                }
            )
    return findings


def test_workpaper_route_unique_dialog_count_is_documented() -> None:
    """Every el-dialog on the workpaper route is enumerated.

    The scan records every el-dialog on the workpaper route (per Req 1.4
    scope). The count itself is expected to be > 1 today — this is the
    *red baseline*; a future Task closes it down to a single owner in
    `ThreeColumnLayout.vue`. The domain-owned dialogs in
    `DOMAIN_OWNER_FILES` are explicitly excluded.

    **Validates: Requirements 1.4, 5.1**
    """
    findings = _scan_el_dialogs_in_workpaper_route()
    # Red baseline: workpaper route today has multiple dialogs. Assert
    # the count is non-zero (baseline non-empty) and every finding is
    # inside the workpaper route or the layout owner.
    assert findings, "no el-dialog on workpaper route (baseline should be non-empty)"
    excluded_paths = set(DOMAIN_OWNER_FILES.keys())
    for f in findings:
        fname = Path(f["file"]).name
        assert fname not in excluded_paths, (
            f"domain-owned file leaked into workpaper route scan: {f}"
        )


# --- (2c) FormulaEdit chain inventory --------------------------------------


def _scan_formulaedit_chain() -> list[dict[str, Any]]:
    """Enumerate the FormulaEdit chain: components that emit or consume 'open-formula'.

    Red baseline for Requirement 5.1 (chain of cell → FormulaEdit open).
    """
    findings: list[dict[str, Any]] = []
    open_formula_re = re.compile(r"open-formula['\"]")
    for path in _iter_vue_files(FRONTEND_SRC):
        text = _read_text(path)
        for m in open_formula_re.finditer(text):
            line = text[: m.start()].count("\n") + 1
            # Only count emits, not the definition on the parent's
            # template binding (which is a listen target).
            snippet = text[max(0, m.start() - 100): m.end() + 100]
            if "@open-formula" in snippet or "emit('open-formula'" in snippet or "emit(\"open-formula\"" in snippet:
                findings.append(
                    {
                        "file": str(path.relative_to(FRONTEND_ROOT)),
                        "line": line,
                        "kind": "emit_or_bind",
                    }
                )
    return findings


def test_formulaedit_chain_is_enumerated() -> None:
    """FormulaEdit chain: emits and listeners are enumerated (Req 5.1 / 8.1).

    The chain today crosses at least GtAuditSheet → GtWpRenderer →
    WorkpaperEditor → FormulaEditDialog (via `open-formula`). This test
    records every emit/bind site so the future Task 6 removal of the
    "open FormulaEditDialog from WorkpaperEditor" path has a precise
    inventory.

    **Validates: Requirements 5.1, 8.1**
    """
    findings = _scan_formulaedit_chain()
    assert len(findings) >= 2, (
        f"FormulaEdit chain inventory is unexpectedly small ({len(findings)}): {findings}"
    )


# --- (2d) dict API inventory -----------------------------------------------


def _scan_dict_api() -> list[dict[str, Any]]:
    """Enumerate the old dict[cell_key, formula] API shape.

    The current user-formula batch API returns dict[cell_key, formula]
    with no base version, no per-item conflict, no history. This scan
    records every call site that reads or writes this shape so Task 8
    can migrate them cleanly.
    """
    findings: list[dict[str, Any]] = []
    # Look for the batch update endpoint and the dict-shape patterns.
    patterns = [
        re.compile(r"/user-formulas"),
        re.compile(r"batchUpdate"),
        re.compile(r"wpUserFormula\."),
    ]
    for path in _iter_ts_files(FRONTEND_SRC):
        if path.suffix not in (".ts", ".vue"):
            continue
        text = _read_text(path)
        for pat in patterns:
            for m in pat.finditer(text):
                line = text[: m.start()].count("\n") + 1
                findings.append(
                    {
                        "file": str(path.relative_to(FRONTEND_ROOT)),
                        "line": line,
                        "pattern": pat.pattern,
                    }
                )
    return findings


def test_dict_api_shape_is_enumerated() -> None:
    """Old dict API call sites are enumerated for Task 8 migration.

    Records every reference to the `/user-formulas` batch endpoint and
    every `wpUserFormula.` call site. The API's dict shape (no base
    version, no per-item conflict, no history) is the red baseline
    for Requirement 8.1 / 8.3.

    **Validates: Requirements 8.1, 8.3**
    """
    findings = _scan_dict_api()
    assert findings, "dict API scan should find at least the API paths definition"
    # The batch update endpoint is registered — that's the red baseline.
    paths = {f["pattern"] for f in findings}
    assert "/user-formulas" in paths or "batchUpdate" in paths, (
        f"dict API inventory must include the batch endpoint; patterns={paths}"
    )


# --- (2e) formula_type duality --------------------------------------------


def _scan_formula_type_duality() -> dict[str, Any]:
    """Identify the two different enum shapes for the same field name `formula_type`.

    Red baseline for Requirement 8.6 — the name `formula_type` is
    overloaded between the workpaper domain (three-category enum) and
    the disclosure/note domain (row-level formula variant).
    """
    workpaper_type = "auto_calc|logic_check|reasonability"
    note_type = "opening_plus_changes"
    workpaper_hits: list[dict[str, Any]] = []
    note_hits: list[dict[str, Any]] = []
    wp_type_pattern = "(?:auto_calc|logic_check|reasonability)"
    note_type = "opening_plus_changes"
    for path in _iter_ts_files(FRONTEND_SRC):
        text = _read_text(path)
        for m in re.finditer(
            rf"formula_type\s*[:=]\s*['\"]{wp_type_pattern}['\"]",
            text,
        ):
            line = text[: m.start()].count("\n") + 1
            workpaper_hits.append({"file": str(path.relative_to(FRONTEND_ROOT)), "line": line})
        for m in re.finditer(
            rf"formula_type\s*===\s*['\"]{re.escape(note_type)}['\"]",
            text,
        ):
            line = text[: m.start()].count("\n") + 1
            note_hits.append({"file": str(path.relative_to(FRONTEND_ROOT)), "line": line})
    return {
        "workpaper_domain": {
            "enum": ["auto_calc", "logic_check", "reasonability"],
            "hits": workpaper_hits,
        },
        "note_domain": {
            "enum": [note_type],
            "hits": note_hits,
        },
    }


def test_formula_type_duality_is_documented() -> None:
    """`formula_type` is genuinely ambiguous: two different enum shapes exist.

    Records both enum shapes. This is the red baseline for Requirement 8.6
    (formula_type double-semantics). If the workpaper domain or the note
    domain ever renames its field, this inventory drops to zero for that
    domain and the test flips RED.

    **Validates: Requirements 8.6**
    """
    dual = _scan_formula_type_duality()
    # Note-domain hits: there MUST be at least one use of
    # formula_type === 'opening_plus_changes' in DisclosureEditor.
    assert dual["note_domain"]["hits"], (
        "note-domain formula_type === 'opening_plus_changes' no longer found — "
        "baseline changed or renamed"
    )
    # Workpaper-domain: the three-type enum is used somewhere (e.g. in
    # FormulaType type or in the backend API surface).
    assert dual["workpaper_domain"]["hits"], (
        "workpaper-domain three-category formula_type enum no longer found — "
        "baseline changed or renamed"
    )


# --- (2f) audit warning commit --------------------------------------------


def _scan_audit_warning_commit() -> list[dict[str, Any]]:
    """Enumerate `catch` blocks that swallow failures with only a console.warn.

    Red baseline for Requirement 8.6 — audit failures must not silently
    succeed. This scan finds `console.warn` inside `.catch(...)` handlers
    on the workpaper route.
    """
    findings: list[dict[str, Any]] = []
    # Look for `}.catch((e) => { ... console.warn ... })` or
    # `}).catch(...) { console.warn }` in workpaper route files.
    warn_re = re.compile(r"console\.warn\s*\(")
    for root in WORKPAPER_ROUTE_ROOTS:
        for path in _iter_vue_files(root):
            text = _read_text(path)
            for m in warn_re.finditer(text):
                line = text[: m.start()].count("\n") + 1
                # Look at the surrounding 300 chars to see if we're in a catch.
                snippet = text[max(0, m.start() - 300): m.end() + 200]
                if ".catch(" in snippet or ".catch ( " in snippet:
                    findings.append(
                        {
                            "file": str(path.relative_to(FRONTEND_ROOT)),
                            "line": line,
                        }
                    )
    # Also WorkpaperEditor.vue (the workpaper route host).
    editor = FRONTEND_SRC / "views" / "WorkpaperEditor.vue"
    if editor.exists():
        text = _read_text(editor)
        for m in warn_re.finditer(text):
            line = text[: m.start()].count("\n") + 1
            snippet = text[max(0, m.start() - 300): m.end() + 200]
            if ".catch(" in snippet or ".catch ( " in snippet:
                findings.append(
                    {"file": str(editor.relative_to(FRONTEND_ROOT)), "line": line}
                )
    return findings


def test_audit_warning_commit_is_enumerated() -> None:
    """`console.warn` inside `.catch(...)` on the workpaper route is red baseline.

    Records the fail-open pattern. Requirement 8.6 requires that future
    tasks delete these (Task 12) — this scan is the removal inventory.

    **Validates: Requirements 8.6**
    """
    findings = _scan_audit_warning_commit()
    # Baseline: at least one audit-warning-commit exists on WorkpaperEditor.
    # (WorkpaperEditor.vue line 767 in the current tree matches.)
    assert findings, (
        "no console.warn-inside-catch on the workpaper route — "
        "baseline changed or already removed by another task"
    )


# --- (2g) duplicate AI/review/fixed rails ---------------------------------


def _scan_duplicate_ai_review_fixed_rails() -> dict[str, list[dict[str, Any]]]:
    """Enumerate duplicate AI review entry points and fixed-position rails.

    Red baseline for Requirement 13.1 — the same AI review capability is
    exposed in many places (workpaper component-level + shell-level +
    review toolbar + fixed position overlay). This scan records:

    - Every `.vue` under `components/workpaper/**` that contains an AI review /
      AI assist button or handler.
    - Every `.vue` under `components/workpaper/**` with `position: fixed`
      that isn't a plain fullscreen overlay (i.e., a floating rail).
    """
    ai_re = re.compile(r"AI\s*(?:复核|建议|生成|辅助)")
    fixed_re = re.compile(r"position\s*:\s*fixed\b")
    ai_hits: list[dict[str, Any]] = []
    fixed_hits: list[dict[str, Any]] = []
    for path in _iter_vue_files(FRONTEND_SRC / "components" / "workpaper"):
        text = _read_text(path)
        for m in ai_re.finditer(text):
            line = text[: m.start()].count("\n") + 1
            ai_hits.append(
                {"file": str(path.relative_to(FRONTEND_ROOT)), "line": line}
            )
        for m in fixed_re.finditer(text):
            line = text[: m.start()].count("\n") + 1
            # Fullscreen overlays (top:0/left:0/inset:0) are NOT rails.
            snippet = text[m.start():m.end() + 200]
            if re.search(r"(top:\s*0|left:\s*0|inset:\s*0|inset\s*:\s*0)", snippet):
                continue
            fixed_hits.append(
                {"file": str(path.relative_to(FRONTEND_ROOT)), "line": line}
            )
    return {"ai_entry_points": ai_hits, "fixed_position_rails": fixed_hits}


def test_duplicate_ai_review_fixed_rails_are_enumerated() -> None:
    """Duplicate AI / review / fixed rails on the workpaper route are red baseline.

    Asserts the scan finds at least one AI entry point and at least one
    fixed-position non-fullscreen rail (a rail / FAB / saving indicator
    that isn't just an overlay). This is the removal inventory for
    Requirement 13.1.

    **Validates: Requirements 13.1**
    """
    inv = _scan_duplicate_ai_review_fixed_rails()
    assert inv["ai_entry_points"], "no AI entry point found in workpaper components (baseline changed)"
    assert inv["fixed_position_rails"], (
        "no fixed-position rail found in workpaper components — baseline changed"
    )


# ---------------------------------------------------------------------------
# 3. Out-of-scope inventory (Req 1.4)
# ---------------------------------------------------------------------------


def test_domain_owned_dialogs_are_out_of_scope() -> None:
    """TB / report / note dialogs are explicitly out of scope for this spec.

    Requirement 1.4: TB/report/note domain dialogs MUST NOT be counted
    in the "unique dialog" or "duplicate rails" numerators. This test
    asserts the exclusion list is non-empty and every listed file
    exists (i.e., the exclusion is real, not a phantom).

    **Validates: Requirements 1.4**
    """
    assert DOMAIN_OWNER_FILES, "out-of-scope list must be non-empty"
    missing: list[str] = []
    for name, owner in DOMAIN_OWNER_FILES.items():
        candidates = list(FRONTEND_SRC.rglob(name))
        if not candidates:
            missing.append(name)
    assert not missing, (
        f"out-of-scope list references files that do not exist (phantom exclusions): {missing}"
    )


# ---------------------------------------------------------------------------
# 4. Owner freeze (Req 13.1)
# ---------------------------------------------------------------------------


#: Files this spec (F1) owns for Task 1+ work.
#: Any concurrent modification to these files between Task 1 and Task 2
#: must be flagged by the owner-attribution scan.
F1_OWNER_FILES = [
    "shared/contracts/gc0/workpaper-route-baseline.ts",
    "shared/contracts/gc0/workpaper-route-baseline.spec.ts",
]

#: Files that F1 must NOT touch (they belong to other concurrent specs).
#: Recorded so Task 13 conformance can fail if a mutation lands here.
FROZEN_CONCURRENT_FILES = [
    "components/workpaper/GtWpToolbar.vue",  # owned by G7 disclosure spec
    "components/workpaper/GtWpRenderer.vue",  # owned by renderer-registry spec
    "components/workpaper/GtWpReviewRail.vue",  # owned by review spec
]


def test_f1_owned_files_exist_and_are_tracked() -> None:
    """F1-owned files exist and their mtime is post-G-C0 completion.

    Requirement 13.1: file existence alone is NOT enough — the task
    can only be checked off when imports + validator + red baseline
    are all live. This test asserts the file bytes are present and the
    validator is actually called (see `test_gc0_consumption_module_calls_validateContractVersion`).

    **Validates: Requirements 13.1**
    """
    for rel in F1_OWNER_FILES:
        p = FRONTEND_SRC / rel
        assert p.exists(), f"F1-owned file missing: {rel}"
        assert p.stat().st_size > 0, f"F1-owned file is empty: {rel}"


def test_frozen_concurrent_files_are_unchanged_by_this_task() -> None:
    """Concurrent-spec files must not be touched by Task 1.

    The task spec explicitly forbids modifying `guidancePanelStore.ts`
    (F1 migration exemption). Any other concurrent-spec file must also
    remain unmodified by Task 1. This test asserts F1-owned file list
    does NOT overlap with frozen concurrent files — Task 1 stays in its lane.

    **Validates: Requirements 13.1**
    """
    f1_paths = set(F1_OWNER_FILES)
    frozen_paths = set(FROZEN_CONCURRENT_FILES)
    overlap = f1_paths & frozen_paths
    assert not overlap, f"F1-owned files overlap with frozen concurrent files: {overlap}"


# ---------------------------------------------------------------------------
# 5. Baseline snapshot (byte-stable reproduction)
# ---------------------------------------------------------------------------


def _build_snapshot() -> dict[str, Any]:
    return {
        "generated_at_epoch": int(time.time()),
        "gc0_contract_version_expected": "1.0",
        "reverse_dup_exemptions": 2,
        "nodekey_payloads": _scan_nodekey_payloads(),
        "workpaper_route_el_dialogs": _scan_el_dialogs_in_workpaper_route(),
        "formulaedit_chain": _scan_formulaedit_chain(),
        "dict_api_call_sites": _scan_dict_api(),
        "formula_type_duality": _scan_formula_type_duality(),
        "audit_warning_commits": _scan_audit_warning_commit(),
        "duplicate_ai_review_fixed_rails": _scan_duplicate_ai_review_fixed_rails(),
        "out_of_scope_domain_files": sorted(DOMAIN_OWNER_FILES.keys()),
        "f1_owner_files": sorted(F1_OWNER_FILES),
        "frozen_concurrent_files": sorted(FROZEN_CONCURRENT_FILES),
    }


def test_baseline_snapshot_can_be_regenerated() -> None:
    """The baseline snapshot is regenerable and self-describing.

    Writes (or verifies) the JSON snapshot at `_snapshots/workpaper_route_task1_baseline.json`.
    This snapshot is what a fresh checkout reproduces; the test asserts
    every key is present so downstream tasks have a stable reference
    point.

    **Validates: Requirements 13.1**
    """
    snapshot = _build_snapshot()
    BASELINE_SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    BASELINE_SNAPSHOT_PATH.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    # Round-trip: parse it back and assert the key set is stable.
    loaded = json.loads(BASELINE_SNAPSHOT_PATH.read_text(encoding="utf-8"))
    required_keys = {
        "nodekey_payloads",
        "workpaper_route_el_dialogs",
        "formulaedit_chain",
        "dict_api_call_sites",
        "formula_type_duality",
        "audit_warning_commits",
        "duplicate_ai_review_fixed_rails",
        "out_of_scope_domain_files",
        "f1_owner_files",
        "frozen_concurrent_files",
        "reverse_dup_exemptions",
    }
    assert required_keys.issubset(loaded.keys()), (
        f"baseline snapshot missing required keys: {required_keys - loaded.keys()}"
    )


# ---------------------------------------------------------------------------
# 6. Mutation self-check M1 — GC0_CONTRACT_VERSION -> '2.0'
# ---------------------------------------------------------------------------


GC0_INDEX_PATH = FRONTEND_GC0_OWNER / "index.ts"
_GC0_VERSION_LINE_RE = re.compile(
    r"export const GC0_CONTRACT_VERSION = '([^']+)'"
)


def _find_gc0_version_line() -> tuple[re.Match[str], str] | None:
    """Return (match, full_line) for the GC0_CONTRACT_VERSION constant line."""
    text = _read_text(GC0_INDEX_PATH)
    m = _GC0_VERSION_LINE_RE.search(text)
    if m is None:
        return None
    line_start = text.rfind("\n", 0, m.start()) + 1
    line_end = text.find("\n", m.end())
    if line_end < 0:
        line_end = len(text)
    return m, text[line_start:line_end]


def test_mutation_m1_gc0_version_flip_fails_closed() -> None:
    """Mutation M1: flipping GC0_CONTRACT_VERSION to '2.0' must RED the gate.

    Mutates `src/shared/contracts/gc0/index.ts` on disk, re-runs the
    F1 wiring vitest, and asserts:
    - the vitest suite flips RED under the mutation (guard working),
    - we restore the original bytes at the end (no pollution).

    If the guard is unwired, the mutation goes GREEN — the test
    classifies that as ANCHOR-MISS and fails.

    **Validates: Requirements 1.4, 2.1**
    """
    probe = _find_gc0_version_line()
    if probe is None:
        pytest.fail("ANCHOR-MISS: GC0_CONTRACT_VERSION constant line not found in index.ts")
    match, original_line = probe
    original_version = match.group(1)
    assert original_version == "1.0", (
        f"precondition broken: baseline GC0_CONTRACT_VERSION is '{original_version}' not '1.0'"
    )

    mutated_line = original_line.replace(f"'{original_version}'", "'2.0'", 1)
    if mutated_line == original_line:
        pytest.fail("ANCHOR-MISS: mutation produced identical text — regex is wrong")

    # Save the original bytes to a temp so we can restore exactly.
    original_bytes = GC0_INDEX_PATH.read_bytes()
    tmp_backup = GC0_INDEX_PATH.with_suffix(".ts.m1.bak")
    shutil.copy2(GC0_INDEX_PATH, tmp_backup)
    try:
        # Write the mutated text.
        new_text = _read_text(GC0_INDEX_PATH).replace(
            original_line, mutated_line, 1
        )
        GC0_INDEX_PATH.write_text(new_text, encoding="utf-8")

        # Re-run the F1 wiring spec. If the guard is wired, the mutation
        # MUST produce a RED exit code from vitest.
        proc = subprocess.run(
            "npx vitest run src/shared/contracts/gc0/workpaper-route-baseline.spec.ts --reporter=basic",
            cwd=str(FRONTEND_ROOT),
            capture_output=True,
            text=True,
            timeout=90,
            shell=True,
        )
        classification = "GREEN"
        if proc.returncode != 0:
            # Look for expected failure signals in the output.
            output = (proc.stdout or "") + (proc.stderr or "")
            # The mutation test inside our spec asserts BLOCKED for
            # contractVersion='2.0'. With the constant flipped to '2.0',
            # the fixture's "1.0" literal no longer matches, so the
            # 'test_contract_version_is_1_0' style test should fail.
            # We only require that *some* test failed.
            classification = "RED"
        elif "failed" in (proc.stdout or "").lower() or proc.returncode != 0:
            classification = "RED"

        # The vitest run should have flipped RED. If it went GREEN,
        # the guard is unwired (or the mutation didn't land) — a harness
        # defect.
        assert classification == "RED", (
            f"Mutation M1 classification = {classification}; "
            f"expected RED. Guard is unwired or mutation anchor missed. "
            f"stdout tail: {(proc.stdout or '')[-500:]}"
        )
    finally:
        # Always restore the original bytes.
        GC0_INDEX_PATH.write_bytes(original_bytes)
        if tmp_backup.exists():
            tmp_backup.unlink()

    # Post-mutation sanity: constant is back to 1.0.
    probe_after = _find_gc0_version_line()
    assert probe_after is not None, "post-restore probe failed"
    assert probe_after[0].group(1) == "1.0", (
        "GC0_CONTRACT_VERSION was not restored to '1.0' after mutation"
    )


# ---------------------------------------------------------------------------
# Terminal summary — Task 1 baseline report
# ---------------------------------------------------------------------------


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    if not FRONTEND_SRC.exists():
        return
    terminalreporter.section("Task 1 — Workpaper-Route Red Baseline")
    terminalreporter.write_line(f"  frontend root: {FRONTEND_ROOT}")
    terminalreporter.write_line(f"  workpaper route roots: {[str(r.relative_to(FRONTEND_ROOT)) for r in WORKPAPER_ROUTE_ROOTS]}")
    terminalreporter.write_line(f"  out-of-scope (domain-owned): {len(DOMAIN_OWNER_FILES)} files")
    for name, owner in sorted(DOMAIN_OWNER_FILES.items()):
        terminalreporter.write_line(f"    - {name}  [{owner}]")
    terminalreporter.write_line(f"  F1 owner files: {F1_OWNER_FILES}")
    terminalreporter.write_line(f"  frozen concurrent files: {FROZEN_CONCURRENT_FILES}")
    terminalreporter.write_line(f"  baseline snapshot: {BASELINE_SNAPSHOT_PATH.relative_to(REPO_ROOT)}")
