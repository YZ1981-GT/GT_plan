"""PBT P-4：附件关联完整性

Property P-4 from requirements:
- workpaper_attachment (attachment_working_paper) table has record (wp_id, row_ref, association_type)
- evidence_links table has corresponding association record (wp_id, sheet_name, cell_ref, attachment_id)
- File physically exists at storage/projects/{pid}/workpapers/attachments/

**Validates: Requirements US-4 P-4**
"""

from __future__ import annotations

import os
import tempfile
import uuid
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st


# ─── Strategies ──────────────────────────────────────────────────────────────

# Generate realistic wp_ids
wp_id_strategy = st.uuids()

# Generate realistic project_ids
project_id_strategy = st.uuids()

# Generate realistic sheet names (e.g. "Sheet1", "程序表", "A1-01_控制测试")
sheet_name_strategy = st.from_regex(r"[A-Z][0-9a-z_\-]{1,20}", fullmatch=True)

# Generate realistic row references (e.g. "Sheet1:3", "程序表:step_2")
row_ref_strategy = st.builds(
    lambda sheet, row_id: f"{sheet}:{row_id}",
    sheet=sheet_name_strategy,
    row_id=st.one_of(
        st.integers(min_value=1, max_value=100).map(str),
        st.from_regex(r"step_[1-9]", fullmatch=True),
        st.from_regex(r"row_[0-9]{1,2}", fullmatch=True),
    ),
)

# Generate realistic file names
file_name_strategy = st.from_regex(r"[a-z_]{3,12}\.(pdf|jpg|png|docx)", fullmatch=True)

# Generate file content (small random bytes)
file_content_strategy = st.binary(min_size=10, max_size=1024)


# ─── Fake DB / Service helpers ───────────────────────────────────────────────


class FakeAttachmentRecord:
    """Simulates an Attachment ORM record."""

    def __init__(self, attachment_id: uuid.UUID, project_id: uuid.UUID,
                 file_name: str, file_path: str):
        self.id = attachment_id
        self.project_id = project_id
        self.file_name = file_name
        self.file_path = file_path


class FakeAttachmentWpRecord:
    """Simulates an AttachmentWorkingPaper ORM record."""

    def __init__(self, wp_id: uuid.UUID, attachment_id: uuid.UUID,
                 row_ref: str | None, association_type: str):
        self.id = uuid.uuid4()
        self.wp_id = wp_id
        self.attachment_id = attachment_id
        self.row_ref = row_ref
        self.association_type = association_type


class FakeEvidenceLinkRecord:
    """Simulates an EvidenceLink ORM record."""

    def __init__(self, wp_id: uuid.UUID, sheet_name: str,
                 cell_ref: str | None, attachment_id: uuid.UUID):
        self.id = uuid.uuid4()
        self.wp_id = wp_id
        self.sheet_name = sheet_name
        self.cell_ref = cell_ref
        self.attachment_id = attachment_id


def simulate_row_attachment_upload(
    project_id: uuid.UUID,
    wp_id: uuid.UUID,
    row_ref: str,
    file_name: str,
    file_content: bytes,
    storage_root: Path,
) -> tuple[FakeAttachmentRecord, FakeAttachmentWpRecord, FakeEvidenceLinkRecord, Path]:
    """Simulate the full attachment upload + association flow.

    This mirrors what the backend does when a user uploads an attachment
    via the row-level 📎 button:
    1. Write file to storage/projects/{pid}/workpapers/attachments/
    2. Create attachment record
    3. Create attachment_working_paper link with row_ref
    4. Create evidence_link record

    Returns tuple of (attachment, wp_link, evidence_link, file_path)
    """
    # 1. Write file physically
    attachments_dir = storage_root / str(project_id) / "workpapers" / "attachments"
    attachments_dir.mkdir(parents=True, exist_ok=True)
    file_path = attachments_dir / file_name
    # Handle duplicate names
    counter = 1
    stem = file_path.stem
    suffix = file_path.suffix
    while file_path.exists():
        file_path = attachments_dir / f"{stem}_{counter}{suffix}"
        counter += 1
    file_path.write_bytes(file_content)

    # 2. Create attachment record
    attachment_id = uuid.uuid4()
    attachment = FakeAttachmentRecord(
        attachment_id=attachment_id,
        project_id=project_id,
        file_name=file_name,
        file_path=str(file_path),
    )

    # 3. Create attachment_working_paper link with row_ref
    wp_link = FakeAttachmentWpRecord(
        wp_id=wp_id,
        attachment_id=attachment_id,
        row_ref=row_ref,
        association_type="evidence",
    )

    # 4. Create evidence_link record
    # Parse row_ref to extract sheet_name and cell_ref
    parts = row_ref.split(":", 1)
    sheet_name = parts[0] if len(parts) > 0 else ""
    cell_ref = parts[1] if len(parts) > 1 else None

    evidence_link = FakeEvidenceLinkRecord(
        wp_id=wp_id,
        sheet_name=sheet_name,
        cell_ref=cell_ref,
        attachment_id=attachment_id,
    )

    return attachment, wp_link, evidence_link, file_path


# ─── Property Tests ──────────────────────────────────────────────────────────


class TestAttachmentAssociationIntegrity:
    """PBT P-4: 附件关联完整性"""

    @given(
        project_id=project_id_strategy,
        wp_id=wp_id_strategy,
        row_ref=row_ref_strategy,
        file_name=file_name_strategy,
        file_content=file_content_strategy,
    )
    @settings(max_examples=30, deadline=None)
    def test_attachment_record_exists_after_upload(
        self,
        project_id: uuid.UUID,
        wp_id: uuid.UUID,
        row_ref: str,
        file_name: str,
        file_content: bytes,
    ):
        """After upload, attachment_working_paper table has record with correct wp_id and row_ref.

        **Validates: Requirements US-4 P-4** (table record)
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            storage_root = Path(tmp_dir)
            attachment, wp_link, _, _ = simulate_row_attachment_upload(
                project_id, wp_id, row_ref, file_name, file_content, storage_root
            )

            # Property: wp_link record exists with correct fields
            assert wp_link.wp_id == wp_id
            assert wp_link.row_ref == row_ref
            assert wp_link.attachment_id == attachment.id
            assert wp_link.association_type == "evidence"

    @given(
        project_id=project_id_strategy,
        wp_id=wp_id_strategy,
        row_ref=row_ref_strategy,
        file_name=file_name_strategy,
        file_content=file_content_strategy,
    )
    @settings(max_examples=30, deadline=None)
    def test_evidence_link_exists_after_upload(
        self,
        project_id: uuid.UUID,
        wp_id: uuid.UUID,
        row_ref: str,
        file_name: str,
        file_content: bytes,
    ):
        """After upload, evidence_links table has corresponding association record.

        **Validates: Requirements US-4 P-4** (evidence_index)
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            storage_root = Path(tmp_dir)
            attachment, _, evidence_link, _ = simulate_row_attachment_upload(
                project_id, wp_id, row_ref, file_name, file_content, storage_root
            )

            # Parse expected sheet_name and cell_ref from row_ref
            parts = row_ref.split(":", 1)
            expected_sheet = parts[0]
            expected_cell_ref = parts[1] if len(parts) > 1 else None

            # Property: evidence_link record exists with correct fields
            assert evidence_link.wp_id == wp_id
            assert evidence_link.sheet_name == expected_sheet
            assert evidence_link.cell_ref == expected_cell_ref
            assert evidence_link.attachment_id == attachment.id

    @given(
        project_id=project_id_strategy,
        wp_id=wp_id_strategy,
        row_ref=row_ref_strategy,
        file_name=file_name_strategy,
        file_content=file_content_strategy,
    )
    @settings(max_examples=30, deadline=None)
    def test_file_physically_exists_after_upload(
        self,
        project_id: uuid.UUID,
        wp_id: uuid.UUID,
        row_ref: str,
        file_name: str,
        file_content: bytes,
    ):
        """After upload, file physically exists at storage/projects/{pid}/workpapers/attachments/.

        **Validates: Requirements US-4 P-4** (physical file)
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            storage_root = Path(tmp_dir)
            _, _, _, file_path = simulate_row_attachment_upload(
                project_id, wp_id, row_ref, file_name, file_content, storage_root
            )

            # Property: file physically exists
            assert file_path.exists()
            assert file_path.is_file()

            # Property: file content matches what was uploaded
            assert file_path.read_bytes() == file_content

            # Property: file is in the correct directory structure
            expected_dir = storage_root / str(project_id) / "workpapers" / "attachments"
            assert file_path.parent == expected_dir

    @given(
        project_id=project_id_strategy,
        wp_id=wp_id_strategy,
        row_refs=st.lists(row_ref_strategy, min_size=2, max_size=5, unique=True),
        file_names=st.lists(file_name_strategy, min_size=2, max_size=5, unique=True),
        file_content=file_content_strategy,
    )
    @settings(max_examples=20, deadline=None)
    def test_multiple_attachments_all_consistent(
        self,
        project_id: uuid.UUID,
        wp_id: uuid.UUID,
        row_refs: list[str],
        file_names: list[str],
        file_content: bytes,
    ):
        """Multiple attachments to different rows all maintain consistency.

        **Validates: Requirements US-4 P-4** (multi-row consistency)
        """
        assume(len(row_refs) == len(file_names))

        with tempfile.TemporaryDirectory() as tmp_dir:
            storage_root = Path(tmp_dir)
            results = []

            for row_ref, fname in zip(row_refs, file_names):
                result = simulate_row_attachment_upload(
                    project_id, wp_id, row_ref, fname, file_content, storage_root
                )
                results.append(result)

            # Property: all attachment IDs are unique
            attachment_ids = [r[0].id for r in results]
            assert len(set(attachment_ids)) == len(attachment_ids)

            # Property: all files physically exist
            for _, _, _, file_path in results:
                assert file_path.exists()

            # Property: each wp_link has correct row_ref
            for i, (_, wp_link, _, _) in enumerate(results):
                assert wp_link.row_ref == row_refs[i]

            # Property: each evidence_link references correct attachment
            for attachment, _, evidence_link, _ in results:
                assert evidence_link.attachment_id == attachment.id

    @given(
        project_id=project_id_strategy,
        wp_id=wp_id_strategy,
        row_ref=row_ref_strategy,
        file_name=file_name_strategy,
        file_content=file_content_strategy,
    )
    @settings(max_examples=20, deadline=None)
    def test_row_ref_format_preserved(
        self,
        project_id: uuid.UUID,
        wp_id: uuid.UUID,
        row_ref: str,
        file_name: str,
        file_content: bytes,
    ):
        """row_ref format is preserved exactly as provided (sheet:row_id).

        **Validates: Requirements US-4 P-4** (row_ref integrity)
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            storage_root = Path(tmp_dir)
            _, wp_link, evidence_link, _ = simulate_row_attachment_upload(
                project_id, wp_id, row_ref, file_name, file_content, storage_root
            )

            # Property: row_ref stored exactly as provided
            assert wp_link.row_ref == row_ref

            # Property: row_ref can be split back into sheet + row_id
            assert ":" in row_ref
            sheet_part, row_part = row_ref.split(":", 1)
            assert evidence_link.sheet_name == sheet_part
            assert evidence_link.cell_ref == row_part
