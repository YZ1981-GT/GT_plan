"""compute_snapshot_hash_from_parts 签名不变 — note-guidance-text-separation Task 7.2."""

from __future__ import annotations

import inspect

from app.services.deliverable_section_state_service import compute_snapshot_hash_from_parts


def test_snapshot_hash_signature_unchanged():
    sig = inspect.signature(compute_snapshot_hash_from_parts)
    assert list(sig.parameters.keys()) == [
        "section_code",
        "text_content",
        "table_data",
        "audited_amounts",
    ]
