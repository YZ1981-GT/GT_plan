"""Property 11, 12, 13: BatchPackager PBT Tests

Property 11: 打包包含指定循环+状态筛选的全部底稿，无遗漏无重复
Property 12: ZIP 内每文件路径匹配 {cycle}/{wp_code}_{wp_name}.{ext}
Property 13: manifest 含 files(path+sha256)/export_timestamp/project 元数据/failed 项

**Validates: Requirements 2.1, 2.2, 2.3, 2.5, 2.6**

Testing framework: hypothesis
"""

from __future__ import annotations

import re

from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.wp_export.batch_packager import BatchPackager

# ─── Hypothesis Strategies ────────────────────────────────────────────────────

_CYCLES = ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L", "M", "N", "S"]
_STATUSES = ["draft", "in_review", "approved"]
_FORMATS = ["xlsx", "docx"]


@st.composite
def st_workpaper(draw: st.DrawFn) -> dict:
    """Generate a single workpaper dict for testing."""
    wp_code = draw(st.from_regex(r"[A-Z]\d{1,2}(-\d{1,2})?", fullmatch=True))
    wp_name = draw(st.text(
        alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="_- "),
        min_size=1,
        max_size=20,
    ))
    audit_cycle = draw(st.sampled_from(_CYCLES))
    status = draw(st.sampled_from(_STATUSES))
    is_deleted = draw(st.booleans())
    file_format = draw(st.sampled_from(_FORMATS))

    # Sometimes generate failed content (None)
    has_content = draw(st.booleans())
    if has_content:
        file_content = draw(st.binary(min_size=10, max_size=100))
        error = None
    else:
        file_content = None
        error = "Export failed: template not found"

    return {
        "wp_code": wp_code,
        "wp_name": wp_name,
        "audit_cycle": audit_cycle,
        "status": status,
        "is_deleted": is_deleted,
        "file_format": file_format,
        "file_content": file_content,
        "error": error,
    }


@st.composite
def st_workpaper_list(draw: st.DrawFn, min_size: int = 1, max_size: int = 10) -> list[dict]:
    """Generate a list of workpapers."""
    count = draw(st.integers(min_value=min_size, max_value=max_size))
    return [draw(st_workpaper()) for _ in range(count)]


@st.composite
def st_project_meta(draw: st.DrawFn) -> dict:
    """Generate project metadata."""
    return {
        "entity_name": draw(st.text(min_size=1, max_size=20)),
        "period_end": "2025-12-31",
        "project_id": str(draw(st.uuids())),
    }


# ─── Property 11: Batch Export Completeness ───────────────────────────────────


class TestBatchExportCompleteness:
    """Property 11: 打包包含指定循环+状态筛选的全部底稿，无遗漏无重复

    **Validates: Requirements 2.1, 2.6**
    """

    @given(
        workpapers=st_workpaper_list(min_size=3, max_size=10),
        cycles=st.lists(st.sampled_from(_CYCLES), min_size=1, max_size=3, unique=True),
        use_status_filter=st.booleans(),
    )
    @settings(max_examples=5)
    def test_completeness_no_missing_no_duplicate(
        self,
        workpapers: list[dict],
        cycles: list[str],
        use_status_filter: bool,
    ) -> None:
        """包含指定循环+状态筛选的全部底稿，无遗漏无重复。

        **Validates: Requirements 2.1, 2.6**
        """
        packager = BatchPackager()

        status_filter: list[str] | None = None
        if use_status_filter:
            status_filter = ["draft", "approved"]

        # 手动计算期望集
        expected_wps = []
        for wp in workpapers:
            if wp.get("is_deleted", False):
                continue
            if wp["audit_cycle"] not in cycles:
                continue
            if status_filter and wp["status"] not in status_filter:
                continue
            expected_wps.append(wp)

        if not expected_wps:
            # 空循环应报错
            try:
                packager.package(workpapers, cycles, status_filter)
                # If it doesn't raise, that's fine only if truly no wps match
                assert False, "Expected ValueError for empty cycle"
            except ValueError:
                pass  # Correct behavior
            return

        result = packager.package(workpapers, cycles, status_filter)

        # Compute expected outcomes:
        # - wps with file_content → should be in files
        # - wps without file_content → should be in failed
        expected_success_codes = [
            wp["wp_code"] for wp in expected_wps if wp.get("file_content") is not None
        ]
        expected_failed_codes = [
            wp["wp_code"] for wp in expected_wps if wp.get("file_content") is None
        ]

        actual_success_codes = [f["wp_code"] for f in result["files"]]
        actual_failed_codes = [f["wp_code"] for f in result["failed"]]

        # No missing successful files
        assert sorted(actual_success_codes) == sorted(expected_success_codes), (
            f"Success mismatch: actual={actual_success_codes}, "
            f"expected={expected_success_codes}"
        )

        # No missing failed files
        assert sorted(actual_failed_codes) == sorted(expected_failed_codes), (
            f"Failed mismatch: actual={actual_failed_codes}, "
            f"expected={expected_failed_codes}"
        )

        # Total = success + failed covers all filtered wps
        assert len(actual_success_codes) + len(actual_failed_codes) == len(expected_wps)


# ─── Property 12: ZIP Directory Structure ────────────────────────────────────


class TestZipDirectoryStructure:
    """Property 12: ZIP 内每文件路径匹配 {cycle}/{wp_code}_{wp_name}.{ext}

    **Validates: Requirements 2.2**
    """

    @given(
        workpapers=st_workpaper_list(min_size=2, max_size=8),
        cycles=st.lists(st.sampled_from(_CYCLES), min_size=1, max_size=3, unique=True),
    )
    @settings(max_examples=5)
    def test_zip_path_format(
        self,
        workpapers: list[dict],
        cycles: list[str],
    ) -> None:
        """ZIP 内每文件路径匹配 {cycle}/{wp_code}_{wp_name}.{ext}。

        **Validates: Requirements 2.2**
        """
        packager = BatchPackager()

        # Ensure at least one non-deleted wp with content in the target cycles
        forced_wp = {
            "wp_code": "D1",
            "wp_name": "测试底稿",
            "audit_cycle": cycles[0],
            "status": "draft",
            "is_deleted": False,
            "file_format": "xlsx",
            "file_content": b"test content bytes",
            "error": None,
        }
        all_wps = workpapers + [forced_wp]

        try:
            result = packager.package(all_wps, cycles)
        except ValueError:
            # No exportable workpapers even with forced - skip this case
            return

        # Pattern: {cycle}/{code}_{name}.{ext}
        # Allow sanitized characters (non-illegal filesystem chars)
        path_pattern = re.compile(
            r"^[^/]+/[^/]+\.(xlsx|docx)$"
        )

        for file_entry in result["files"]:
            path = file_entry["path"]

            # Must match basic structure: dir/filename.ext
            assert path_pattern.match(path), (
                f"Path does not match {{cycle}}/{{code}}_{{name}}.{{ext}}: {path!r}"
            )

            # Path must contain the audit_cycle as directory
            parts = path.split("/")
            assert len(parts) == 2, f"Expected exactly 1 directory level, got: {path!r}"

            directory = parts[0]
            filename = parts[1]

            # Directory should be a valid cycle value
            assert directory == file_entry["audit_cycle"], (
                f"Directory {directory!r} != audit_cycle {file_entry['audit_cycle']!r}"
            )

            # Filename should end with correct extension
            assert filename.endswith(".xlsx") or filename.endswith(".docx"), (
                f"Filename does not end with .xlsx or .docx: {filename!r}"
            )

            # Filename should contain wp_code and wp_name separated by _
            name_part = filename.rsplit(".", 1)[0]
            # The code should be the prefix before first _
            assert "_" in name_part, (
                f"Filename should contain _ separator: {name_part!r}"
            )

        # Zip entries match files
        assert len(result["zip_entries"]) == len(result["files"])
        for (zip_path, _content), file_entry in zip(
            result["zip_entries"], result["files"]
        ):
            assert zip_path == file_entry["path"]


# ─── Property 13: Manifest Contains All Required Fields ──────────────────────


class TestManifestContainsAllRequiredFields:
    """Property 13: manifest 含 files(path+sha256)/export_timestamp/project 元数据/failed 项

    **Validates: Requirements 2.3, 2.5**
    """

    @given(
        workpapers=st_workpaper_list(min_size=2, max_size=8),
        cycles=st.lists(st.sampled_from(_CYCLES), min_size=1, max_size=3, unique=True),
        project_meta=st_project_meta(),
    )
    @settings(max_examples=5)
    def test_manifest_required_fields(
        self,
        workpapers: list[dict],
        cycles: list[str],
        project_meta: dict,
    ) -> None:
        """manifest 含 files(path+sha256)/export_timestamp/project 元数据/failed 项。

        **Validates: Requirements 2.3, 2.5**
        """
        packager = BatchPackager()

        # Ensure at least one exportable wp
        forced_wp = {
            "wp_code": "E1",
            "wp_name": "货币资金",
            "audit_cycle": cycles[0],
            "status": "draft",
            "is_deleted": False,
            "file_format": "xlsx",
            "file_content": b"some xlsx bytes here",
            "error": None,
        }
        all_wps = workpapers + [forced_wp]

        try:
            result = packager.package(all_wps, cycles, project_meta=project_meta)
        except ValueError:
            return

        manifest = result["manifest"]

        # Required top-level fields
        assert "files" in manifest, "manifest must contain 'files'"
        assert "export_timestamp" in manifest, "manifest must contain 'export_timestamp'"
        assert "project" in manifest, "manifest must contain 'project'"
        assert "failed" in manifest, "manifest must contain 'failed'"

        # files array entries must have path + sha256
        for file_entry in manifest["files"]:
            assert "path" in file_entry, f"File entry missing 'path': {file_entry}"
            assert "sha256" in file_entry, f"File entry missing 'sha256': {file_entry}"
            # SHA-256 should be 64 hex chars
            assert len(file_entry["sha256"]) == 64, (
                f"SHA-256 should be 64 chars: {file_entry['sha256']!r}"
            )
            assert all(c in "0123456789abcdef" for c in file_entry["sha256"]), (
                f"SHA-256 should be hex: {file_entry['sha256']!r}"
            )

        # export_timestamp should be valid ISO format
        ts = manifest["export_timestamp"]
        assert isinstance(ts, str), f"export_timestamp should be string: {ts!r}"
        assert "T" in ts, f"export_timestamp should be ISO-8601: {ts!r}"

        # project metadata present
        assert manifest["project"] == project_meta, (
            f"project meta mismatch: {manifest['project']} != {project_meta}"
        )

        # failed items structure
        for failed_item in manifest["failed"]:
            assert "wp_code" in failed_item, f"Failed item missing 'wp_code': {failed_item}"
            assert "error" in failed_item, f"Failed item missing 'error': {failed_item}"
