"""Property 6 & 7: Version Conflict Detection + Substantive Conflict via Hash (PBT)

Property 6: file_version < server_version → 冲突; >= → 无冲突
Property 7: 导出时 hash == 当前 hash → 非实质冲突; 不同 → 实质冲突

**Validates: Requirements 4.2, 4.3, 4.5**

Testing framework: hypothesis
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.wp_export.conflict_detector import ConflictDetector

# ─── Shared fixture ───────────────────────────────────────────────────────────

_detector = ConflictDetector()

# Strategy: SHA-256 hex hash (64 characters, lowercase hex)
st_hash = st.text(
    alphabet="0123456789abcdef",
    min_size=64,
    max_size=64,
)

# Strategy: version numbers (positive integers)
st_version = st.integers(min_value=1, max_value=10000)


# ─── Property 6: Version Conflict Detection ──────────────────────────────────


class TestVersionConflictDetection:
    """Property 6: file_version < server_version → 冲突; >= → 无冲突

    **Validates: Requirements 4.2, 4.3**
    """

    @given(
        imported_version=st_version,
        server_version=st_version,
    )
    @settings(max_examples=5)
    def test_version_less_than_server_is_conflict(
        self, imported_version: int, server_version: int
    ) -> None:
        """imported_version < server_version → has_conflict=True.

        **Validates: Requirements 4.2, 4.3**
        """
        result = _detector.detect(
            imported_version=imported_version,
            server_version=server_version,
        )

        if imported_version < server_version:
            assert result.has_conflict is True, (
                f"Expected conflict for imported={imported_version} < server={server_version}, "
                f"but got has_conflict=False"
            )
            assert result.conflict_type is not None
        else:
            assert result.has_conflict is False, (
                f"Expected no conflict for imported={imported_version} >= server={server_version}, "
                f"but got has_conflict=True"
            )
            assert result.conflict_type is None

    @given(
        server_version=st_version,
        delta=st.integers(min_value=0, max_value=100),
    )
    @settings(max_examples=5)
    def test_version_gte_server_no_conflict(
        self, server_version: int, delta: int
    ) -> None:
        """imported_version >= server_version → has_conflict=False.

        **Validates: Requirements 4.2, 4.3**
        """
        imported_version = server_version + delta  # always >= server_version

        result = _detector.detect(
            imported_version=imported_version,
            server_version=server_version,
        )

        assert result.has_conflict is False, (
            f"Expected no conflict for imported={imported_version} >= server={server_version}"
        )
        assert result.is_substantive is False


# ─── Property 7: Substantive Conflict via Hash ───────────────────────────────


class TestSubstantiveConflictViaHash:
    """Property 7: 导出时 hash == 当前 hash → 非实质冲突; 不同 → 实质冲突

    **Validates: Requirements 4.5**
    """

    @given(
        server_version=st.integers(min_value=2, max_value=10000),
        hash_value=st_hash,
    )
    @settings(max_examples=5)
    def test_same_hash_non_substantive(
        self, server_version: int, hash_value: str
    ) -> None:
        """export_hash == current_hash → is_substantive=False.

        When there is a version conflict but the content hasn't actually
        changed (same hash), the conflict is non-substantive.

        **Validates: Requirements 4.5**
        """
        imported_version = server_version - 1  # force version conflict

        result = _detector.detect(
            imported_version=imported_version,
            server_version=server_version,
            export_hash=hash_value,
            current_hash=hash_value,  # same hash
        )

        assert result.has_conflict is True
        assert result.is_substantive is False, (
            f"Same hash should yield non-substantive conflict, "
            f"but got is_substantive=True"
        )
        assert result.conflict_type == "version"

    @given(
        server_version=st.integers(min_value=2, max_value=10000),
        export_hash=st_hash,
        current_hash=st_hash,
    )
    @settings(max_examples=5)
    def test_different_hash_substantive(
        self, server_version: int, export_hash: str, current_hash: str
    ) -> None:
        """export_hash != current_hash → is_substantive=True.

        When there is a version conflict AND the content has actually changed
        (different hashes), the conflict is substantive.

        **Validates: Requirements 4.5**
        """
        # Ensure hashes are different
        if export_hash == current_hash:
            # Flip one character to guarantee difference
            chars = list(current_hash)
            chars[0] = "a" if chars[0] != "a" else "b"
            current_hash = "".join(chars)

        imported_version = server_version - 1  # force version conflict

        result = _detector.detect(
            imported_version=imported_version,
            server_version=server_version,
            export_hash=export_hash,
            current_hash=current_hash,
        )

        assert result.has_conflict is True
        assert result.is_substantive is True, (
            f"Different hashes should yield substantive conflict, "
            f"but got is_substantive=False"
        )
        assert result.conflict_type == "both"
