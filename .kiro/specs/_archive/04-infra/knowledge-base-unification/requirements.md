# Requirements Document

## Introduction

统一知识库模块：将审计平台当前三套割裂的知识存储系统（文件系统全局知识库、PostgreSQL 文件夹型知识库、向量索引表）收敛为单一真源架构，使文档上传后自动完成文本提取、语义分块、向量索引，并通过 pgvector ANN 搜索 + jieba 中文 BM25 回退为 AI RAG 消费者提供有效的知识库上下文。

## Glossary

- **Knowledge_Folder_System**: PostgreSQL `knowledge_folders` + `knowledge_documents` 表构成的树形文件夹型知识库，支持访问控制（public/project_group/private）和版本链，作为统一后的单一存储真源
- **Global_File_KB**: 当前基于文件系统 `~/.gt_audit_helper/knowledge/{category}/` 的全局知识库，9 个分类，纯文件 CRUD，统一后将被废弃
- **Knowledge_Index**: PostgreSQL `knowledge_index` 表，存储文档分块及其向量嵌入，供语义搜索使用
- **Content_Extractor**: 文档文本提取服务，从 PDF/DOCX/XLSX/TXT/MD 等格式文件中提取纯文本内容
- **Semantic_Chunker**: 语义分块器，将提取的文本按段落/句子边界切分为带重叠的语义片段
- **Embedding_Service**: 向量嵌入生成服务，调用 Qwen 模型（经 vLLM）生成文本的高维向量表示
- **PgVector_Store**: 基于 pgvector 扩展的向量存储与 ANN 搜索后端，替代当前 TEXT 列内存暴力搜索
- **BM25_Fallback**: 基于 jieba 中文分词的 BM25 词法检索降级通道，当嵌入服务不可用时提供搜索能力
- **RAG_Consumer**: AI 辅助功能的知识检索消费者，包括 ReferenceDocService、ai_chat_service、b14_ai_generate 等
- **Indexing_Pipeline**: 文档上传后触发的异步处理流水线：提取 → 分块 → 嵌入 → 入库
- **Context_Signal**: 底稿上下文信号，包括当前 wp_code、account_code 等，用于搜索结果相关性加权

## Requirements

### Requirement 1: 统一存储真源

**User Story:** As a 审计助理, I want 所有知识库文档统一存储在一个系统中, so that 我不需要在多个地方搜索和管理参考资料。

#### Acceptance Criteria

1. THE Knowledge_Folder_System SHALL store all knowledge base documents exclusively in PostgreSQL `knowledge_documents` table with a non-null `folder_id` referencing `knowledge_folders`, and no document shall exist only on the file system without a corresponding `knowledge_documents` row
2. WHEN a document is uploaded via the Global_File_KB legacy endpoints, THE Knowledge_Folder_System SHALL store the document in the preset category folder matching the legacy category parameter using the 9-category mapping (workpaper_templates, regulations, accounting_standards, quality_control, audit_procedures, industry_guides, prompts, report_templates, notes), and SHALL return the created document's id in the response within 5 seconds
3. IF a document is uploaded via the Global_File_KB legacy endpoints with a category that does not match any of the 9 preset categories, THEN THE Knowledge_Folder_System SHALL reject the request with HTTP 400 indicating the invalid category
4. WHEN a client requests documents from the Global_File_KB endpoints, THE Knowledge_Folder_System SHALL return documents from the mapped preset category folder using the same response schema as the legacy endpoints
5. THE Knowledge_Folder_System SHALL enforce access control on every document query: public visible to all authenticated users, project_group visible only to users whose active project_id is in project_ids, private visible only to created_by user
6. IF the preset category folder does not exist when a legacy upload is received, THEN THE Knowledge_Folder_System SHALL auto-create the preset folder idempotently before storing the document
7. WHEN a document with the same filename already exists in the target preset folder, THE Knowledge_Folder_System SHALL create a new version rather than rejecting or creating a duplicate

### Requirement 2: 上传自动索引

**User Story:** As a 审计助理, I want 文档上传后自动被索引, so that 知识库内容能立即被 AI 辅助功能检索到。

#### Acceptance Criteria

1. WHEN a document is successfully uploaded to the Knowledge_Folder_System AND its content_text is non-null after extraction, THE Indexing_Pipeline SHALL be triggered asynchronously within 5 seconds via a background task
2. WHEN the Indexing_Pipeline completes successfully, THE Knowledge_Index SHALL contain the document's chunked embeddings with source_id equal to KnowledgeDocument.id and doc_version equal to KnowledgeDocument.version
3. IF the Indexing_Pipeline fails, THEN THE Knowledge_Folder_System SHALL update KnowledgeDocument.index_status to "failed" and write the error message to KnowledgeDocument.index_error without affecting the document's availability for non-search operations
4. WHEN a document is updated (new version via _resolve_version_chain), THE Indexing_Pipeline SHALL mark the previous version's index entries as is_stale=True and index the new version
5. WHEN a document is soft-deleted, THE Knowledge_Index SHALL immediately mark all chunks with matching source_id as is_deleted=True
6. THE Indexing_Pipeline SHALL be idempotent: triggering it multiple times for the same document version SHALL produce identical index entries (upsert by project_id + source_id + chunk_index)

### Requirement 3: 文本内容提取

**User Story:** As a 审计助理, I want 上传的 PDF/DOCX/Excel 文件能被自动解析出文本, so that 文件内容可以被搜索和 AI 引用。

#### Acceptance Criteria

1. WHEN a PDF file is uploaded, THE Content_Extractor SHALL extract all text content preserving paragraph structure with double newline separators between paragraphs
2. WHEN a DOCX file is uploaded, THE Content_Extractor SHALL extract text content including headings, paragraphs, and table cell text in document order
3. WHEN a TXT or MD file is uploaded, THE Content_Extractor SHALL read the file content directly as UTF-8 text
4. WHEN an XLSX file is uploaded, THE Content_Extractor SHALL extract cell text from all sheets containing at least one non-blank cell, with each sheet's content prefixed by the sheet name
5. IF the Content_Extractor encounters an unsupported file format, THEN it SHALL set content_text to NULL and index_status to "unsupported_format"
6. WHEN extraction completes successfully, THE Content_Extractor SHALL write the extracted text to KnowledgeDocument.content_text and set index_status to "extracted"
7. IF extraction encounters a corrupted or password-protected file, THEN it SHALL set index_status to "extraction_failed" and record the reason in KnowledgeDocument.index_error
8. IF extraction exceeds 60 seconds for a single document, THEN it SHALL abort, set index_status to "extraction_failed" with timeout indication in index_error

### Requirement 4: 语义分块

**User Story:** As a 现场经理, I want 长文档被智能切分为语义片段, so that 搜索返回的片段具有完整的上下文含义而非被截断的碎片。

#### Acceptance Criteria

1. THE Semantic_Chunker SHALL split text at paragraph boundaries (two or more consecutive newlines) or sentence boundaries (。！？ followed by whitespace/newline) rather than at fixed character positions
2. THE Semantic_Chunker SHALL produce chunks of 300-800 characters with 50-100 character overlap; IF a single semantic unit exceeds 800 characters, THEN it SHALL be split at the nearest sentence boundary within that unit
3. WHEN processing regulation or accounting standard documents, THE Semantic_Chunker SHALL start a new chunk at each article/clause marker (第X条/CAS X) so the marker appears as first content of the new chunk
4. Each chunk SHALL include metadata: chunk_index (0-based), total_chunks (positive integer), source section heading (from nearest preceding heading marker; empty string if none detected)
5. Chunking then concatenating all chunks in order (removing overlap regions) SHALL produce output character-for-character identical to original input (round-trip property)
6. IF input text contains fewer than 300 characters, THEN exactly one chunk SHALL be produced containing the entire input without overlap
7. Chunking SHALL complete within 2 seconds for documents up to 200,000 characters

### Requirement 5: pgvector 高效搜索

**User Story:** As a 审计助理, I want 知识库搜索在毫秒级返回结果, so that AI 辅助功能不会因检索延迟而影响使用体验。

#### Acceptance Criteria

1. THE PgVector_Store SHALL store embedding vectors using the pgvector `vector(dim)` column type where dim matches the embedding model output dimension
2. THE PgVector_Store SHALL create an HNSW index (m=16, ef_construction=200) on the embedding column for approximate nearest neighbor search
3. WHEN performing semantic search, THE PgVector_Store SHALL use pgvector's cosine distance operator (`<=>`) for similarity computation entirely within PostgreSQL without loading vectors into Python memory
4. THE PgVector_Store SHALL return top_k (k≤50) results within 200ms p95 for up to 100,000 chunks
5. THE PgVector_Store SHALL support pre-filtering by project_id and source_type using WHERE clauses before vector similarity computation
6. IF pgvector extension is unavailable at query time, THE system SHALL fall back to BM25_Fallback and log a warning

### Requirement 6: 中文 BM25 降级搜索

**User Story:** As a 审计助理, I want 即使 AI 嵌入服务不可用也能搜索知识库, so that 系统在部分故障时仍然可用。

#### Acceptance Criteria

1. THE BM25_Fallback SHALL use jieba word segmentation with an audit-domain custom dictionary loaded from `backend/data/jieba_audit_dict.txt`
2. The audit dictionary SHALL contain at minimum 500 domain terms covering: 会计科目名称, 审计准则术语, 监管机构名称, 审计程序术语
3. WHEN the Embedding_Service is unavailable or returns an error, THE system SHALL automatically fall back to BM25_Fallback without user intervention
4. THE BM25_Fallback SHALL produce results within 500ms p95 for up to 100,000 chunks
5. FOR ALL terms in the audit dictionary, tokenization SHALL produce the full term as a single token (e.g. "应收账款" → ["应收账款"] not ["应收", "收账", "账款"])
6. WHEN both embedding and BM25 are unavailable, THE system SHALL fall back to ilike substring search as last resort and log a critical warning

### Requirement 7: 底稿上下文感知搜索

**User Story:** As a 审计助理, I want 知识库搜索能理解我当前编辑的底稿上下文, so that 返回的参考资料与我正在做的审计工作高度相关。

#### Acceptance Criteria

1. WHEN a search includes wp_code Context_Signal, THE service SHALL boost documents tagged with matching audit cycle categories (e.g. wp_code starting with "D" boosts receivables-related standards)
2. WHEN a search includes account_code Context_Signal, THE service SHALL boost documents mentioning the corresponding standard account name (looked up from trial_balance standard_account_code)
3. THE service SHALL accept optional context parameters (wp_code, account_code, audit_area) maintaining backward compatibility — omitting them produces unmodified vector scores
4. Final ranking SHALL use: final_score = 0.7 * vector_similarity + 0.3 * context_boost, where context_boost = 1.0 if both signals match, 0.5 if one matches, 0.0 if none match

### Requirement 8: RAG 消费者接入

**User Story:** As a 业务合伙人, I want AI 辅助功能在生成意见和笔记时引用知识库中的法规准则, so that 生成的内容有据可依。

#### Acceptance Criteria

1. WHEN ReferenceDocService.load_from_knowledge_base is called with keywords AND matching indexed documents exist, THE service SHALL return at least 1 result (guaranteed non-empty when data exists)
2. WHEN ai_chat_service processes a query with knowledge_base scope, THE service SHALL inject top-3 relevant chunks into the LLM context messages
3. WHEN b14_ai_generate invokes _load_knowledge_base_docs, THE service SHALL return results using semantic_search with proper embeddings (not just ilike fallback)
4. Each search result SHALL include: source_type, source_id, content, score, chunk_index, doc_version, is_stale, document_name, and folder_path for citation display

### Requirement 9: 全局知识库兼容迁移

**User Story:** As a 现场经理, I want 现有全局知识库的文档在统一后仍然可用, so that 团队积累的参考资料不会丢失。

#### Acceptance Criteria

1. A migration script `scripts/migrate_global_kb_to_pg.py` SHALL import all files from `~/.gt_audit_helper/knowledge/{category}/` into corresponding preset category folders in Knowledge_Folder_System
2. WHEN the migration processes a file with parseable content (PDF/DOCX/TXT/MD/XLSX), THE Indexing_Pipeline SHALL be triggered for the migrated document
3. The Global_File_KB legacy endpoints SHALL proxy to Knowledge_Folder_System immediately upon deployment (no separate migration step required for endpoint compatibility)
4. Legacy endpoint responses SHALL include `X-Deprecated: true` and `X-New-Endpoint` headers pointing to the folder-type API paths
5. The migration SHALL be idempotent: matching by (folder_id, filename) — existing documents get version incremented, not duplicated

### Requirement 10: 搜索结果权限过滤

**User Story:** As a 质量控制复核合伙人, I want 搜索结果遵守文档的访问权限设置, so that 私有文档不会被未授权用户看到。

#### Acceptance Criteria

1. THE service SHALL determine effective access_level per document: document-level access_level if non-null, else folder-level access_level (inheritance model)
2. WHEN effective access_level is "public", THE service SHALL include the result for all authenticated users
3. WHEN effective access_level is "project_group", THE service SHALL include the result only for users whose current project_id is in the document's (or folder's) project_ids array
4. WHEN effective access_level is "private", THE service SHALL include the result only for the user whose id matches document's created_by
5. Permission filtering SHALL occur AFTER vector scoring and BEFORE returning results to the caller to avoid re-ranking artifacts
6. IF a document's KnowledgeDocument row is not found (orphaned index entry), THE service SHALL exclude it from results and log a warning
