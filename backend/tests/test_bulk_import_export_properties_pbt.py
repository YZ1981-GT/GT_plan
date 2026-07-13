"""Consolidated Property-Based Tests for workpaper-bulk-tab-import-export (P1–P8).

Spec: .kiro/specs/workpaper-bulk-tab-import-export/design.md — Correctness
Properties P1–P8. Task 7.1 (optional). Feature (Tasks 1–6) is complete and
live-verified.

This file formalises the correctness properties that are NOT already covered
elsewhere. It follows the repo convention `@settings(max_examples=5)` (the
`fast` Hypothesis profile is auto-loaded via conftest.py; explicit low counts
keep runs fast).

Coverage map (see module docstring per test):
  - P1 拓扑顺序满足依赖         → thin reference PBT (full PBT lives in
                                   test_bulk_topological_sort_pbt.py)
  - P2 manifest 路由仅来自 ACNR  → mocked async PBT (build_manifest provenance)
  - P3 跳过项不影响其余          → pure PBT (manifest.exportable + align)
  - P4 ConflictStrategy 语义正确 → pure PBT (resolve_conflict, 3 strategies)
  - P5 DryRun 不写库             → mocked async PBT (dry_run performs no writes)
  - P6 失败回滚恢复导入前状态     → thin invariant PBT (heavy integration lives
                                   in test_bulk_import_service.py)
  - P7 工作流状态门禁            → pure PBT (WorkflowGate.classify) + mocked
                                   revert permission-gate examples
  - P8 ZIP 路径规范且不含敏感信息 → pure PBT (_build_zip_path + check_no_secrets)

Subjects under test are pure functions where possible (ConflictResolver,
WorkflowGate.classify, manifest field provenance, zip_path formatting). For the
DB/async orchestration (P2/P5) we mock like test_bulk_import_service.py does and
drive the coroutine via a synchronous `_run` wrapper so Hypothesis stays happy.
"""
from __future__ import annotations

import asyncio
import io
import os
import re
import uuid
import zipfile
from typing import Any, Coroutine
from unittest import mock
from unittest.mock import AsyncMock, MagicMock

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-unit-tests")

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

# ─── Subjects under test ─────────────────────────────────────────────────────
from app.services.bulk_tab.conflict_resolver import (
    ConflictRejected,
    is_field_empty,
    is_row_empty,
    resolve_conflict,
)
from app.services.bulk_tab.manifest_builder import (
    BulkManifest,
    ManifestFileEntry,
    _build_zip_path,
    build_manifest,
)
from app.services.bulk_tab.bulk_import_service import (
    ImportReport,
    align,
    dry_run,
)
from app.services.bulk_tab.workflow_gate import WorkflowGate
from app.services.bulk_tab.zip_handler import check_no_secrets
from app.services.wp_bulk_tab_export import _topological_sort


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _run(coro: Coroutine[Any, Any, Any]) -> Any:
    """Drive a coroutine to completion on a fresh event loop.

    Hypothesis cannot await coroutines directly, so mocked-async properties run
    each generated example through this synchronous wrapper (repo convention).
    """
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _make_zip(files: dict[str, bytes], manifest: dict) -> bytes:
    """Build an in-memory ZIP with the given files + manifest.json."""
    import json

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for path, data in files.items():
            zf.writestr(path, data)
        zf.writestr(
            "manifest.json",
            json.dumps(manifest, ensure_ascii=False).encode("utf-8"),
        )
    return buf.getvalue()


# ═══════════════════════════════════════════════════════════════════════════
# Property 1: 导入拓扑顺序满足依赖 (thin reference)
# Feature: workpaper-bulk-tab-import-export, Property 1
# Validates: Requirements 2.2
#
# Full PBT lives in test_bulk_topological_sort_pbt.py (150 examples, DAG/flat/
# cyclic strategies). Here we only assert the orchestration layer relies on the
# same _topological_sort and that it preserves the dependency invariant — we do
# NOT duplicate the heavy DAG generation.
# ═══════════════════════════════════════════════════════════════════════════


@st.composite
def _small_dag(draw: st.DrawFn) -> list[dict]:
    n = draw(st.integers(min_value=1, max_value=5))
    codes = [f"S{i}" for i in range(n)]
    orders = draw(st.permutations(list(range(n))))
    entries: list[dict] = []
    for i in range(n):
        deps = (
            draw(st.lists(st.sampled_from(codes[:i]), unique=True, max_size=i))
            if i
            else []
        )
        entries.append(
            {"sheet_code": codes[i], "depends_on_sheets": deps, "import_order": orders[i]}
        )
    return list(draw(st.permutations(entries)))


@settings(max_examples=5)
@given(entries=_small_dag())
def test_p1_topological_order_reference(entries: list[dict]) -> None:
    """Every sheet appears after its declared dependencies (reference-assert)."""
    result = _topological_sort(entries)
    assert {e["sheet_code"] for e in result} == {e["sheet_code"] for e in entries}
    pos = {e["sheet_code"]: i for i, e in enumerate(result)}
    for e in entries:
        for dep in e["depends_on_sheets"]:
            assert pos[dep] < pos[e["sheet_code"]]


# ═══════════════════════════════════════════════════════════════════════════
# Property 2: manifest 路由元数据仅来自 ACNR
# Feature: workpaper-bulk-tab-import-export, Property 2
# Validates: Requirements 7.1, 7.2
#
# For any ACNR entry set, every generated manifest file's routing fields
# (api_prefix, item_id, sheet_code, wp_id, addr_id) equal the source ACNR
# entry's — no fabricated routing appears.
# ═══════════════════════════════════════════════════════════════════════════


@st.composite
def _acnr_export_entries(draw: st.DrawFn) -> list[dict]:
    n = draw(st.integers(min_value=1, max_value=5))
    entries: list[dict] = []
    for i in range(n):
        entries.append(
            {
                "addr_id": f"D2/D2-{i}/item{i}",
                "sheet_code": f"D2-{i}",
                "api_prefix": draw(st.sampled_from(["d1", "d2", "d3", "d4"])),
                "item_id": f"D2-item-{i}",
                "storage_field": draw(st.sampled_from(["remark", "conclusion"])),
                "wp_id": str(uuid.uuid4()),
                "import_order": i,
                "depends_on_sheets": [],
                "parent_wp_code": "D2",
            }
        )
    return entries


@settings(max_examples=5)
@given(entries=_acnr_export_entries())
def test_p2_manifest_routing_only_from_acnr(entries: list[dict]) -> None:
    """Every manifest file's routing fields trace back to an ACNR entry."""
    catalog = [
        {
            "addr_id": e["addr_id"],
            "sheet_name": f"明细表{e['sheet_code']}",
            "origin": "standard",
            "cycle": "D",
        }
        for e in entries
    ]

    with mock.patch(
        "app.services.wp_bulk_tab_export.list_export_sheets",
        new_callable=AsyncMock,
        return_value=entries,
    ), mock.patch(
        "app.services.acnr.manifest.list_import_export",
        new_callable=AsyncMock,
        return_value=entries,  # all listed → no skipped
    ), mock.patch(
        "app.services.acnr.catalog.list_sheets",
        return_value=catalog,
    ):
        manifest: BulkManifest = _run(
            build_manifest(
                db=AsyncMock(),
                project_id=uuid.uuid4(),
                cycles=["D"],
                mode="template",
            )
        )

    source_by_addr = {e["addr_id"]: e for e in entries}
    # Every generated file's routing metadata equals its ACNR source.
    for f in manifest.files:
        assert isinstance(f, ManifestFileEntry)
        assert f.addr_id in source_by_addr, "manifest introduced an unknown addr_id"
        src = source_by_addr[f.addr_id]
        assert f.api_prefix == src["api_prefix"]
        assert f.item_id == src["item_id"]
        assert f.sheet_code == src["sheet_code"]
        assert f.wp_id == src["wp_id"]
        assert f.import_order == src["import_order"]

    # Provenance is total: every ACNR entry with a wp_id yields exactly one file.
    assert {f.addr_id for f in manifest.files} == set(source_by_addr)


# ═══════════════════════════════════════════════════════════════════════════
# Property 3: 跳过项不影响其余导出/导入
# Feature: workpaper-bulk-tab-import-export, Property 3
# Validates: Requirements 1.6, 1.8, 2.7, 2.8, 2.9
#
# For any mix of exportable/skipped entries (export side) and missing/unlisted
# files (import side), the pure helpers process every processable item, record
# the skipped ones separately, and never raise.
# ═══════════════════════════════════════════════════════════════════════════


@settings(max_examples=5)
@given(
    flags=st.lists(st.booleans(), min_size=1, max_size=8),
)
def test_p3_export_skips_do_not_drop_others(flags: list[bool]) -> None:
    """manifest.exportable() returns exactly the wp_id-bearing entries."""
    files: list[ManifestFileEntry] = []
    for i, has_wp in enumerate(flags):
        files.append(
            ManifestFileEntry(
                addr_id=f"D2/D2-{i}/x",
                wp_code="D2",
                parent_wp_code="D2",
                sheet_code=f"D2-{i}",
                sheet_name=f"明细表D2-{i}",
                origin="standard",
                api_prefix="d2",
                item_id=f"item-{i}",
                storage_field="remark",
                wp_id=str(uuid.uuid4()) if has_wp else None,
                import_order=i,
                depends_on_sheets=[],
                zip_path=f"D/D2/D2-{i}_明细表_模板.xlsx",
                sha256="",
            )
        )
    manifest = BulkManifest(files=files)

    exportable = manifest.exportable()
    expected = [f for f in files if f.wp_id is not None]
    # skipped entries (wp_id=None) are excluded, all others preserved, no raise.
    assert exportable == expected
    assert all(f.wp_id is not None for f in exportable)


@settings(max_examples=5)
@given(
    n_files=st.integers(min_value=1, max_value=5),
    missing_idx=st.integers(min_value=0, max_value=4),
    add_unlisted=st.booleans(),
)
def test_p3_import_align_records_missing_and_unlisted(
    n_files: int, missing_idx: int, add_unlisted: bool
) -> None:
    """align() flags missing/unlisted separately without dropping valid items."""
    manifest_files = []
    topo_sheets = []
    for i in range(n_files):
        code = f"D2-{i}"
        manifest_files.append(
            {
                "sheet_code": code,
                "zip_path": f"D/D2/{code}.xlsx",
                "wp_id": str(uuid.uuid4()),
                "api_prefix": "d2",
                "import_order": i,
            }
        )
        topo_sheets.append(
            {
                "sheet_code": code,
                "wp_id": manifest_files[-1]["wp_id"],
                "api_prefix": "d2",
                "import_order": i,
                "depends_on_sheets": [],
            }
        )

    missing = missing_idx % n_files
    zip_file_list = ["manifest.json"]
    for i in range(n_files):
        if i == missing:
            continue  # simulate a missing file in the ZIP
        zip_file_list.append(f"D/D2/D2-{i}.xlsx")
    if add_unlisted:
        zip_file_list.append("D/D2/EXTRA_未登记.xlsx")

    plan = align(manifest_files, topo_sheets, zip_file_list)

    # Every manifest sheet still produces an aligned item (nothing dropped).
    assert len(plan.items) == n_files
    # Exactly the one missing file is flagged missing.
    assert sum(1 for it in plan.items if it.missing) == 1
    assert plan.items[missing].missing is True
    # Unlisted files are recorded separately, never merged into items.
    if add_unlisted:
        assert "D/D2/EXTRA_未登记.xlsx" in plan.unlisted_paths
    else:
        assert plan.unlisted_paths == []


# ═══════════════════════════════════════════════════════════════════════════
# Property 4: ConflictStrategy 语义正确
# Feature: workpaper-bulk-tab-import-export, Property 4
# Validates: Requirements 8.1, 8.2, 8.3
#
# overwrite → full replace; fill-empty → non-empty existing preserved, only
# empty positions filled; reject → any non-empty existing target aborts the
# whole sheet (no partial write).
# ═══════════════════════════════════════════════════════════════════════════

_CELL = st.one_of(
    st.none(),
    st.just(""),
    st.just("   "),
    st.text(min_size=1, max_size=6),
    st.integers(min_value=-5, max_value=5),
)


@st.composite
def _row_pair(draw: st.DrawFn) -> tuple[dict, dict]:
    keys = draw(st.lists(st.sampled_from(["a", "b", "c"]), unique=True, min_size=1, max_size=3))
    existing = {k: draw(_CELL) for k in keys}
    incoming = {k: draw(st.text(min_size=1, max_size=6)) for k in keys}
    return existing, incoming


@settings(max_examples=5)
@given(pair=_row_pair())
def test_p4_overwrite_full_replace(pair: tuple[dict, dict]) -> None:
    """overwrite → result equals a full replacement by incoming."""
    existing, incoming = pair
    resolved = resolve_conflict(
        {"item-1": existing}, {"item-1": incoming}, "overwrite", sheet_code="D2-2"
    )
    assert resolved["item-1"] == incoming


@settings(max_examples=5)
@given(pair=_row_pair())
def test_p4_fill_empty_preserves_non_empty(pair: tuple[dict, dict]) -> None:
    """fill-empty → non-empty existing fields never change; empties get filled."""
    existing, incoming = pair
    resolved = resolve_conflict(
        {"item-1": existing}, {"item-1": incoming}, "fill-empty", sheet_code="D2-2"
    )
    merged = resolved["item-1"]
    for key, ex_val in existing.items():
        if not is_field_empty(ex_val):
            # Non-empty existing value must be preserved verbatim.
            assert merged[key] == ex_val
        else:
            # Empty existing position filled from incoming.
            assert merged[key] == incoming[key]


@settings(max_examples=5)
@given(pair=_row_pair())
def test_p4_reject_aborts_when_target_non_empty(pair: tuple[dict, dict]) -> None:
    """reject → raises iff existing row has any non-empty field; no partial write."""
    existing, incoming = pair
    if is_row_empty(existing):
        # All-empty existing → reject behaves like overwrite (writes incoming).
        resolved = resolve_conflict(
            {"item-1": existing}, {"item-1": incoming}, "reject", sheet_code="D2-2"
        )
        assert resolved["item-1"] == incoming
    else:
        with pytest.raises(ConflictRejected) as exc:
            resolve_conflict(
                {"item-1": existing}, {"item-1": incoming}, "reject", sheet_code="D2-2"
            )
        assert "item-1" in exc.value.conflicting_item_ids


# ═══════════════════════════════════════════════════════════════════════════
# Property 5: DryRun 不写库
# Feature: workpaper-bulk-tab-import-export, Property 5
# Validates: Requirements 2.3
#
# For any input ZIP, dry_run performs no DB write (no add/commit/flush/delete)
# and returns a report with dry_run=True structurally isomorphic to a real run.
# ═══════════════════════════════════════════════════════════════════════════


@settings(max_examples=5)
@given(n_files=st.integers(min_value=1, max_value=4))
def test_p5_dry_run_performs_no_db_writes(n_files: int) -> None:
    """dry_run must not mutate the DB, regardless of ZIP contents."""
    import hashlib

    files_bytes: dict[str, bytes] = {}
    manifest_files = []
    topo_sheets = []
    statuses: dict[str, str] = {}
    for i in range(n_files):
        code = f"D2-{i}"
        wp_id = str(uuid.uuid4())
        data = f"fake xlsx {i}".encode("utf-8")
        zip_path = f"D/D2/{code}.xlsx"
        files_bytes[zip_path] = data
        manifest_files.append(
            {
                "sheet_code": code,
                "zip_path": zip_path,
                "wp_id": wp_id,
                "api_prefix": "d2",
                "import_order": i,
                "sha256": hashlib.sha256(data).hexdigest(),
            }
        )
        topo_sheets.append(
            {
                "sheet_code": code,
                "wp_id": wp_id,
                "api_prefix": "d2",
                "import_order": i,
                "depends_on_sheets": [],
            }
        )
        statuses[wp_id] = "draft"

    manifest = {"cycles": ["D"], "files": manifest_files}
    zip_bytes = _make_zip(files_bytes, manifest)

    db = AsyncMock()

    with mock.patch(
        "app.services.wp_bulk_tab_export.list_import_sheets",
        new_callable=AsyncMock,
        return_value=topo_sheets,
    ), mock.patch(
        "app.services.bulk_tab.bulk_import_service._get_wp_statuses",
        new_callable=AsyncMock,
        return_value=statuses,
    ):
        report = _run(dry_run(db, str(uuid.uuid4()), zip_bytes, "overwrite"))

    # No write path was exercised.
    db.add.assert_not_called()
    db.commit.assert_not_called()
    db.flush.assert_not_called()
    db.delete.assert_not_called()
    db.execute.assert_not_called()  # _get_wp_statuses mocked → no direct SQL

    # Report is dry_run and isomorphic (one sheet report per manifest file).
    assert report.dry_run is True
    success = [s for s in report.sheets if s.status == "success"]
    assert len(success) == n_files


# ═══════════════════════════════════════════════════════════════════════════
# Property 6: 失败回滚恢复到导入前状态 (thin invariant)
# Feature: workpaper-bulk-tab-import-export, Property 6
# Validates: Requirements 2.4, 6.2
#
# Heavy rollback integration (SnapshotGuard.rollback called on injected failure)
# is covered in test_bulk_import_service.py::test_all_or_nothing_rollback. Here
# we only assert the report-level rollback invariant that the orchestrator
# exposes to callers, without duplicating the SnapshotGuard machinery.
# ═══════════════════════════════════════════════════════════════════════════


@settings(max_examples=5)
@given(
    marks=st.lists(
        st.sampled_from(["success", "partial", "failed"]), min_size=0, max_size=5
    )
)
def test_p6_rolled_back_flag_invariant(marks: list[str]) -> None:
    """mark_all_rolled_back() sets a monotonic, serialised rolled_back flag."""
    report = ImportReport(strategy="overwrite", dry_run=False)
    for i, status in enumerate(marks):
        report.mark(f"D2-{i}", status)  # type: ignore[arg-type]

    assert report.rolled_back is False
    assert report.to_dict()["rolled_back"] is False

    report.mark_all_rolled_back()
    assert report.rolled_back is True
    assert report.to_dict()["rolled_back"] is True
    # Idempotent — recording a rollback twice stays True.
    report.mark_all_rolled_back()
    assert report.rolled_back is True


# ═══════════════════════════════════════════════════════════════════════════
# Property 7: 工作流状态门禁
# Feature: workpaper-bulk-tab-import-export, Property 7
# Validates: Requirements 9.1, 9.2, 9.3, 4.3, 4.4
#
# review_passed/archived/locked → blocked; under_review → revert_needed; else →
# writable. Plus: revert only writes when the user has WORKPAPER_WRITE.
# ═══════════════════════════════════════════════════════════════════════════

_BLOCKED = ["review_passed", "archived", "review_level1_passed", "review_level2_passed"]
_REVERT = ["under_review"]
_WRITABLE = ["draft", "edit_complete", "revision_required", "", "unknown_status"]
_ALL_STATUSES = _BLOCKED + _REVERT + _WRITABLE


@settings(max_examples=5)
@given(statuses=st.lists(st.sampled_from(_ALL_STATUSES), min_size=1, max_size=8))
def test_p7_classify_state_gate(statuses: list[str]) -> None:
    """classify() maps each status to the correct gate classification."""
    items = [{"wp_id": uuid.uuid4(), "status": s} for s in statuses]
    gate = WorkflowGate()
    result = gate.classify(items)

    for item in items:
        cls = result[item["wp_id"]]
        status = item["status"]
        if status in _BLOCKED:
            assert cls.classification == "blocked"
            assert cls.reason == status  # blocked records the offending status
        elif status in _REVERT:
            assert cls.classification == "revert_needed"
        else:
            assert cls.classification == "writable"


@pytest.mark.asyncio
async def test_p7_revert_requires_write_permission() -> None:
    """Feature: workpaper-bulk-tab-import-export, Property 7 (9.2/9.3).

    under_review revert writes only with WORKPAPER_WRITE; without it, no state
    change and no DB write occur.
    """
    gate = WorkflowGate()
    wp_id = uuid.uuid4()

    # ── No write permission (role not in matrix) → returns False, no DB write.
    no_perm_user = MagicMock()
    no_perm_user.id = uuid.uuid4()
    no_perm_user.role = MagicMock()
    no_perm_user.role.value = "viewer"  # absent from ROLE_PERMISSION_MATRIX
    db_noperm = AsyncMock()

    reverted = await gate.revert_if_under_review(db_noperm, wp_id, no_perm_user)
    assert reverted is False
    db_noperm.execute.assert_not_called()
    db_noperm.flush.assert_not_called()

    # ── With write permission (auditor) → returns True and issues an update.
    perm_user = MagicMock()
    perm_user.id = uuid.uuid4()
    perm_user.role = MagicMock()
    perm_user.role.value = "auditor"  # has WORKPAPER_WRITE
    db_perm = AsyncMock()

    with mock.patch(
        "app.services.bulk_tab.workflow_gate.WorkflowGate._write_revert_audit_log",
        new_callable=AsyncMock,
    ):
        reverted2 = await gate.revert_if_under_review(db_perm, wp_id, perm_user)
    assert reverted2 is True
    db_perm.execute.assert_called()  # status update was issued


# ═══════════════════════════════════════════════════════════════════════════
# Property 8: ZIP 路径规范且不含敏感信息
# Feature: workpaper-bulk-tab-import-export, Property 8
# Validates: Requirements 6.3, 1.4
#
# zip_path matches {cycle}/{parent_wp_code}/{sheet_code}_…_(模板|数据).xlsx and
# contains no path-traversal; check_no_secrets flags secret patterns in text
# files and leaves binary xlsx untouched.
# ═══════════════════════════════════════════════════════════════════════════

_CYCLE = st.sampled_from(["D", "F", "G", "H", "K"])
_SHEET_CODE = st.from_regex(r"[A-K][0-9]{1,2}(-[0-9]{1,2})?", fullmatch=True)
_SHEET_NAME = st.text(
    alphabet="应收账款明细表审定坏账准备ABCabc123 ", min_size=0, max_size=20
)


@settings(max_examples=5)
@given(
    cycle=_CYCLE,
    parent=_SHEET_CODE,
    sheet_code=_SHEET_CODE,
    sheet_name=_SHEET_NAME,
    mode=st.sampled_from(["template", "data"]),
)
def test_p8_zip_path_format(
    cycle: str, parent: str, sheet_code: str, sheet_name: str, mode: str
) -> None:
    """zip_path follows the {cycle}/{parent}/{sheet_code}_..._(模板|数据).xlsx rule."""
    path = _build_zip_path(cycle, parent, sheet_code, sheet_name, mode)  # type: ignore[arg-type]

    assert path.startswith(f"{cycle}/{parent}/")
    assert path.endswith(".xlsx")
    mode_label = "模板" if mode == "template" else "数据"
    assert path.endswith(f"_{mode_label}.xlsx")
    # sheet_code prefixes the filename segment.
    filename = path.split("/")[-1]
    assert filename.startswith(f"{sheet_code}_")
    # No path traversal / no illegal separators beyond the two structural ones.
    assert ".." not in path
    assert path.count("/") == 2
    # Structural regex assertion.
    assert re.match(
        rf"^{re.escape(cycle)}/{re.escape(parent)}/{re.escape(sheet_code)}_.+_(模板|数据)\.xlsx$",
        path,
    )


@settings(max_examples=5)
@given(
    secret=st.sampled_from(
        [
            "Bearer abc.def.ghi",
            "Authorization: token",
            "-----BEGIN PRIVATE KEY-----",
            "sk-verysecretkey123",
            "aws_secret_access_key=xyz",
        ]
    ),
    filler=st.text(max_size=20),
)
def test_p8_check_no_secrets_flags_text(secret: str, filler: str) -> None:
    """check_no_secrets raises on secret patterns inside text files."""
    payload = (filler + secret + filler).encode("utf-8")
    # A text file carrying a secret must be rejected.
    with pytest.raises(ValueError):
        check_no_secrets(payload, "manifest.json")
    # The same bytes as a binary xlsx are NOT scanned (patterns don't apply).
    check_no_secrets(payload, "D/D2/D2-2_明细表_数据.xlsx")  # no raise


@settings(max_examples=5)
@given(text=st.text(alphabet="abc 123应收账款明细", max_size=40))
def test_p8_check_no_secrets_passes_clean_text(text: str) -> None:
    """Clean text files pass check_no_secrets without raising."""
    check_no_secrets(text.encode("utf-8"), "README.txt")  # no raise
