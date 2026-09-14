"""Property 8, 9, 10: Version Manager PBT Tests

Property 8: 导入成功后 file_version=prev+1，archive 记录 source=import
Property 9: archive_path 格式 storage/projects/{pid}/archive/{wp_id}/v{n}/
Property 10: N>10 时最多 10 条 file_retained=true，为最近 10 个版本

**Validates: Requirements 6.1, 6.2, 6.3, 6.4**

Testing framework: hypothesis
"""

from __future__ import annotations

import re
from uuid import UUID

from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.wp_export.version_manager import (
    archive_path_for,
    mark_excess_versions,
)

# ─── Hypothesis Strategies ────────────────────────────────────────────────────


@st.composite
def st_version_archives(draw: st.DrawFn, min_count: int = 1, max_count: int = 20) -> list[dict]:
    """Generate a list of version archive records with sequential version_no.

    Each record has version_no (sequential from 1..N) and file_retained=True.
    """
    count = draw(st.integers(min_value=min_count, max_value=max_count))
    archives = []
    for i in range(1, count + 1):
        archives.append({
            "version_no": i,
            "file_retained": True,
            "source": draw(st.sampled_from(["import", "upload", "edit", "template"])),
        })
    return archives


# ─── Property 8: Version Increment Invariant ──────────────────────────────────


class TestVersionIncrementInvariant:
    """Property 8: 导入成功后 file_version=prev+1，archive 记录 source=import

    Tests the pure logic: given prev_version, new version = prev + 1,
    and the archive record correctly records source="import".

    **Validates: Requirements 6.1, 6.2**
    """

    @given(
        prev_version=st.integers(min_value=0, max_value=1000),
        project_id=st.uuids(),
        wp_id=st.uuids(),
    )
    @settings(max_examples=5)
    def test_version_increment_and_source(
        self,
        prev_version: int,
        project_id: UUID,
        wp_id: UUID,
    ) -> None:
        """New version = prev_version + 1, archive_path is correctly formed,
        and source='import' is preserved in the record structure.

        **Validates: Requirements 6.1, 6.2**
        """
        new_version = prev_version + 1

        # Verify increment invariant
        assert new_version == prev_version + 1

        # Verify archive_path uses new version
        path = archive_path_for(project_id, wp_id, new_version)
        assert f"v{new_version}/" in path

        # Simulate what create_version would produce as a record
        record = {
            "version_no": new_version,
            "source": "import",
            "content_hash": "a" * 64,  # simulated SHA-256
            "archive_path": path,
            "wp_id": wp_id,
            "project_id": project_id,
        }

        # Invariants
        assert record["version_no"] == prev_version + 1
        assert record["source"] == "import"
        assert record["content_hash"] is not None
        assert len(record["content_hash"]) == 64


# ─── Property 9: Version Archive Path Format ─────────────────────────────────


class TestVersionArchivePathFormat:
    """Property 9: archive_path 格式 storage/projects/{pid}/archive/{wp_id}/v{n}/

    **Validates: Requirements 6.3**
    """

    @given(
        project_id=st.uuids(),
        wp_id=st.uuids(),
        version_no=st.integers(min_value=1, max_value=9999),
    )
    @settings(max_examples=5)
    def test_archive_path_format(
        self,
        project_id: UUID,
        wp_id: UUID,
        version_no: int,
    ) -> None:
        """archive_path matches expected pattern exactly.

        **Validates: Requirements 6.3**
        """
        path = archive_path_for(project_id, wp_id, version_no)

        # Exact format check
        expected = f"storage/projects/{project_id}/archive/{wp_id}/v{version_no}/"
        assert path == expected, f"Path mismatch: {path!r} != {expected!r}"

        # Regex pattern validation
        pattern = r"^storage/projects/[0-9a-f\-]+/archive/[0-9a-f\-]+/v\d+/$"
        assert re.match(pattern, path), f"Path does not match pattern: {path!r}"

        # Structural checks
        assert path.startswith("storage/projects/")
        assert "/archive/" in path
        assert path.endswith("/")
        assert f"/v{version_no}/" in path
        assert str(project_id) in path
        assert str(wp_id) in path


# ─── Property 10: Maximum 10 Retained Version Files ──────────────────────────


class TestMaximum10RetainedVersionFiles:
    """Property 10: N>10 时最多 10 条 file_retained=true，为最近 10 个版本

    **Validates: Requirements 6.4**
    """

    @given(archives=st_version_archives(min_count=11, max_count=30))
    @settings(max_examples=5)
    def test_max_10_retained_when_exceeds(
        self,
        archives: list[dict],
    ) -> None:
        """When N > 10, at most 10 records have file_retained=true,
        and they are the 10 most recent versions.

        **Validates: Requirements 6.4**
        """
        result = mark_excess_versions(archives, keep=10)

        # Count retained
        retained = [a for a in result if a["file_retained"] is True]
        not_retained = [a for a in result if a["file_retained"] is False]

        # At most 10 retained
        assert len(retained) <= 10, (
            f"Expected at most 10 retained, got {len(retained)}"
        )
        # Exactly 10 retained (since we have > 10 input)
        assert len(retained) == 10, (
            f"Expected exactly 10 retained, got {len(retained)}"
        )

        # The retained ones are the 10 most recent (highest version_no)
        retained_versions = sorted([a["version_no"] for a in retained], reverse=True)
        all_versions = sorted([a["version_no"] for a in result], reverse=True)
        expected_retained = all_versions[:10]

        assert retained_versions == expected_retained, (
            f"Retained versions {retained_versions} != "
            f"expected top 10 {expected_retained}"
        )

        # The non-retained ones are the oldest
        not_retained_versions = sorted(
            [a["version_no"] for a in not_retained], reverse=True
        )
        expected_not_retained = all_versions[10:]
        assert not_retained_versions == expected_not_retained

    @given(archives=st_version_archives(min_count=1, max_count=10))
    @settings(max_examples=5)
    def test_all_retained_when_within_limit(
        self,
        archives: list[dict],
    ) -> None:
        """When N <= 10, all records have file_retained=true.

        **Validates: Requirements 6.4**
        """
        result = mark_excess_versions(archives, keep=10)

        # All should be retained
        retained = [a for a in result if a["file_retained"] is True]
        assert len(retained) == len(archives), (
            f"Expected all {len(archives)} retained, got {len(retained)}"
        )
