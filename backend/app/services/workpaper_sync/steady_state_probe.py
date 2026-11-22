# -*- coding: utf-8 -*-
# """workbook/styles steady-state probe (spec onlyoffice-sheet-open 3.3, 2026-11-21).

# A published substrate produced by an older adapter build differs from the
# current adapter output in the workbook_and_styles bucket (xl/workbook.xml,
# xl/styles.xml, xl/theme/*). verify_unmanaged_regions compares that bucket
# byte-for-byte, so materialize on such a substrate fails closed forever with
# adapter_unmanaged_region_drift even though every managed region roundtrips
# exactly. This probe answers one yes/no question with byte digests only:
# does the substrate carry the same workbook/styles bytes the current adapter
# would produce? It reads nothing else, writes nothing, and never raises for
# readable files; unreadable/missing parts count as mismatch (fail-closed: the
# caller then normalizes the baseline via the first-publication kernel).
# """
from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path

# Same membership rule as excel_extract._classify_parts workbook_and_styles.
BUCKET_PARTS = (
    'xl/workbook.xml',
    'xl/styles.xml',
)
BUCKET_PREFIXES = ('xl/theme/',)


def _bucket_digests(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    try:
        with zipfile.ZipFile(path) as zf:
            names = set(zf.namelist())
            for name in sorted(names):
                if name in BUCKET_PARTS or name.startswith(BUCKET_PREFIXES):
                    out[name] = hashlib.sha256(zf.read(name)).hexdigest()
    except Exception:
        return {}
    return out


def workbook_styles_bucket_matches(*, substrate: Path, artifact: Path) -> bool:
    '''True when both files carry the identical workbook_and_styles bucket.

    Empty vs empty matches (both sides normalized away). A missing/unreadable
    bucket counts as a mismatch so the caller falls back to normalization
    instead of skipping the check. '''
    left = _bucket_digests(Path(substrate))
    right = _bucket_digests(Path(artifact))
    if not left and not right:
        return True
    if not left or not right:
        return False
    return left == right


__all__ = ['workbook_styles_bucket_matches']
