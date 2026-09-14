"""
Knowledge Base Unification — All 12 PBT Properties

Run: python -m pytest backend/tests/test_knowledge_unification_pbt.py -v

Aggregates P1-P12 correctness properties from the design specification.
"""

from __future__ import annotations

# Re-export all PBT tests from individual test files for unified execution

from tests.test_semantic_chunker import (
    test_round_trip_chunking,         # P1
    test_chunk_size_bounds,           # P11
)
from tests.test_content_extractor import (
    test_extraction_idempotence_txt,  # P2
)
from tests.test_indexing_pipeline_pbt import (
    test_mark_chunks_deleted_idempotent,    # P3
    test_delete_cascade_marks_chunks_deleted,  # P8
    test_version_stale_marks_previous_chunks,  # P9
)
from tests.test_permission_filter_pbt import (
    test_private_docs_never_leak,     # P4
)
from tests.test_zh_tokenize_pbt import (
    test_audit_term_single_token,     # P5
)
from tests.test_context_boost_pbt import (
    test_context_boost_bounded,       # P6
)
from tests.test_migration_idempotence_pbt import (
    test_migration_idempotence,       # P7
)
from tests.test_legacy_endpoint_pbt import (
    test_legacy_response_schema_contains_required_fields,  # P10
)
from tests.test_pgvector_search_pbt import (
    test_cosine_similarity_recall,    # P12
)

# All 12 properties imported and runnable via this single file.
# P1:  Round-trip chunking
# P2:  Content extraction idempotence
# P3:  Indexing idempotence
# P4:  Private docs never leak
# P5:  Audit terms as single tokens
# P6:  Context boost bounded
# P7:  Migration idempotence
# P8:  Soft-delete cascades to index
# P9:  Version update stale marking
# P10: Legacy response schema compatibility
# P11: Chunk size bounds
# P12: pgvector recall accuracy
