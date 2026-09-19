# Implementation Plan: Knowledge Base Unification

## Overview

将三套割裂的知识存储系统统一为单一PG真源+自动索引流水线。Phase 1(核心流水线)→Phase 2(存储/搜索)→Phase 3(增强)。

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 0, "tasks": [1] },
    { "wave": 1, "tasks": [2, 3] },
    { "wave": 2, "tasks": [4, 6] },
    { "wave": 3, "tasks": [5, 7] },
    { "wave": 4, "tasks": [8, 9, 10, 11] },
    { "wave": 5, "tasks": [12] }
  ]
}
```

## Tasks

- [x] 1. DB Migration V116 + ORM Sync
  - [x] 1.1 Create `backend/migrations/V116__knowledge_base_unification.sql`: CREATE EXTENSION IF NOT EXISTS vector; ALTER knowledge_documents ADD index_status VARCHAR(30) DEFAULT 'pending', index_error TEXT; ALTER knowledge_index ADD embedding_vec vector(1024); CREATE HNSW index (m=16, ef_construction=200); CREATE composite index on (project_id, source_type) WHERE is_deleted=false
  - [x] 1.2 Update `backend/app/models/knowledge_models.py`: add index_status and index_error columns to KnowledgeDocument model
  - [x] 1.3 Update `backend/app/models/ai_models.py`: add embedding_vec column (pgvector Vector type) to KnowledgeIndex model
  - [x] 1.4 Run migration and verify schema drift = 0
- [x] 2. Content Extractor Service
  - [x] 2.1 Create `backend/app/services/content_extractor.py`: ContentExtractor class with factory dispatch by extension, 60s timeout, ExtractResult dataclass
  - [x] 2.2 Implement PDF extraction using PyMuPDF (fitz): page.get_text with paragraph separation
  - [x] 2.3 Implement DOCX extraction using python-docx: paragraphs + tables
  - [x] 2.4 Implement XLSX extraction using openpyxl: non-empty sheets with name prefix
  - [x] 2.5 Implement TXT/MD extraction: direct UTF-8 read
  - [x] 2.6 Add PyMuPDF and python-docx to backend/requirements.txt
  - [x] 2.7 Write unit tests + PBT P2 (extraction idempotence)
- [x] 3. Semantic Chunker
  - [x] 3.1 Create `backend/app/services/semantic_chunker.py`: semantic_chunk function with Chunk dataclass
  - [x] 3.2 Implement paragraph/sentence/clause splitting with article marker detection regex
  - [x] 3.3 Implement overlap strategy (80 chars from previous chunk tail)
  - [x] 3.4 Implement chunk metadata attachment (chunk_index, total_chunks, section_heading)
  - [x] 3.5 Write PBT P1 (round-trip), P11 (size bounds), performance test
- [x] 4. Indexing Pipeline + Trigger Wiring
  - [x] 4.1 Create `backend/app/services/indexing_pipeline.py`: run_indexing_pipeline(doc_id) orchestrating extract→chunk→embed→upsert
  - [x] 4.2 Wire pipeline trigger in knowledge_folders.py upload endpoint via background_tasks
  - [x] 4.3 Wire pipeline on version update + mark_previous_stale
  - [x] 4.4 Wire soft-delete cascade to mark chunks is_deleted=True
  - [x] 4.5 Write PBT P3 (idempotence), P8 (delete cascade), P9 (version stale)
  - [x] 4.6 Integration test: upload TXT → verify knowledge_index chunks → semantic_search non-empty
- [x] 5. pgvector Search Rewrite
  - [x] 5.1 Modify _upsert_chunk to dual-write TEXT embedding_vector + vector embedding_vec columns
  - [x] 5.2 Rewrite _vector_search to use pgvector cosine distance operator with pre-filtering WHERE clauses
  - [x] 5.3 Add pgvector unavailability fallback to BM25
  - [x] 5.4 Write PBT P12 (recall >= 0.95) + performance test
- [x] 6. Jieba BM25 Upgrade
  - [x] 6.1 Add jieba to backend/requirements.txt
  - [x] 6.2 Create `backend/data/jieba_audit_dict.txt` with 500+ audit domain terms
  - [x] 6.3 Rewrite `backend/app/services/_zh_tokenize.py` to use jieba.cut + load_userdict
  - [x] 6.4 Write PBT P5 (audit terms as single tokens)
  - [x] 6.5 Verify BM25 cache mechanism still works with jieba tokens
- [x] 7. Legacy Endpoint Proxy
  - [x] 7.1 Rewrite knowledge_base.py upload to delegate to KnowledgeFolderService + trigger pipeline
  - [x] 7.2 Rewrite list/download to query from mapped preset folders
  - [x] 7.3 Implement _get_or_create_preset_folder helper (idempotent)
  - [x] 7.4 Add X-Deprecated and X-New-Endpoint response headers
  - [x] 7.5 Write PBT P10 (legacy schema compat) + integration test
- [x] 8. Context-Aware Search
  - [x] 8.1 Extend semantic_search signature with optional wp_code, account_code, audit_area
  - [x] 8.2 Implement _apply_context_boost: final_score = 0.7*vector + 0.3*boost
  - [x] 8.3 Implement wp_code to cycle category mapping
  - [x] 8.4 Implement account_code to standard_account_name lookup
  - [x] 8.5 Write PBT P6 (boost bounded) + unit tests
- [x] 9. RAG Consumer Wiring
  - [x] 9.1 Verify ReferenceDocService.load_from_knowledge_base works with indexed data
  - [x] 9.2 Enrich search results with document_name + folder_path via JOIN
  - [x] 9.3 Verify ai_chat_service and b14_ai_generate consumption paths
  - [x] 9.4 Integration test: upload doc → load_from_knowledge_base → non-empty with citations
- [x] 10. Migration Script
  - [x] 10.1 Create `scripts/migrate_global_kb_to_pg.py`: scan file system, create documents in preset folders
  - [x] 10.2 Implement idempotence: check existence before create, version increment for duplicates
  - [x] 10.3 Trigger ContentExtractor + IndexingPipeline for each migrated document
  - [x] 10.4 Write PBT P7 (migration idempotence)
- [x] 11. Permission Verification
  - [x] 11.1 Verify _filter_by_permission handles orphaned entries (exclude + log)
  - [x] 11.2 Write PBT P4 (private docs never leak)
  - [x] 11.3 Integration test: private doc invisible to other users
- [x] 12. End-to-End Validation
  - [x] 12.1 Playwright: upload PDF → index_status=indexed → search returns results
  - [x] 12.2 Playwright: AI note generation with knowledge context injection
  - [x] 12.3 Run all 12 PBT properties: python -m pytest backend/tests/test_knowledge_unification_pbt.py -v

## Notes

- 新依赖: PyMuPDF (fitz), python-docx, jieba
- 最高迁移号 V116 (当前 V115)
- pgvector 扩展已安装在 PG16
- embedding 维度 1024 (BAAI/bge-m3, 独立服务 localhost:8101)
- Phase 1 (Task 1-4) 为 P0 核心闭环：上传→提取→分块→索引→搜索可用
- Phase 2 (Task 5-7) 为 P0 性能+存储统一（与Task 4并行Wave 2-3）
- Phase 3 (Task 8-12) 为 P1 增强+验证（Wave 4并行全出）
- 全局公共文档用哨兵UUID `00000000-0000-0000-0000-000000000000` 作project_id索引，搜索时同时查项目+全局
