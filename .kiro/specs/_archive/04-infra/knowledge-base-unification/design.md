# Technical Design

## Overview

将三套割裂的知识存储（文件系统全局KB、PG文件夹型、向量索引）收敛为**单一真源+自动索引流水线**架构。文档上传后自动：提取文本→语义分块→向量嵌入→pgvector入库，AI RAG消费者通过统一`semantic_search`获取知识上下文。

## Architecture

### Component Diagram

```
┌─────────────────┐     ┌──────────────────────────────────────────────┐
│  Frontend       │     │  Backend                                      │
│  KnowledgeBase  │────▶│  knowledge_folders.py (upload/CRUD)           │
│  .vue           │     │       │                                       │
└─────────────────┘     │       ▼ (async background task)              │
                        │  ┌─────────────────────────────────┐         │
┌─────────────────┐     │  │  Indexing Pipeline               │         │
│  Legacy Clients │     │  │  ┌───────────┐ ┌────────────┐  │         │
│  /api/knowledge │─────│──│  │ Content   │→│ Semantic   │  │         │
│  (proxy shim)   │     │  │  │ Extractor │ │ Chunker    │  │         │
└─────────────────┘     │  │  └───────────┘ └─────┬──────┘  │         │
                        │  │                       ▼         │         │
                        │  │              ┌──────────────┐   │         │
                        │  │              │ Embedding    │   │         │
                        │  │              │ (AIService)  │   │         │
                        │  │              └──────┬───────┘   │         │
                        │  │                     ▼           │         │
                        │  │         ┌────────────────────┐  │         │
                        │  │         │ PgVector Upsert    │  │         │
                        │  │         │ knowledge_index    │  │         │
                        │  │         └────────────────────┘  │         │
                        │  └─────────────────────────────────┘         │
                        │                                               │
                        │  ┌─────────────────────────────────┐         │
                        │  │  Search Layer                    │         │
                        │  │  KnowledgeIndexService           │         │
                        │  │  ├─ pgvector <=> (primary)       │         │
                        │  │  ├─ jieba BM25 (fallback)        │         │
                        │  │  └─ ilike (last resort)          │         │
                        │  └──────────────┬──────────────────┘         │
                        │                 ▼                             │
                        │  ┌─────────────────────────────────┐         │
                        │  │  RAG Consumers                   │         │
                        │  │  - ReferenceDocService           │         │
                        │  │  - ai_chat_service               │         │
                        │  │  - b14_ai_generate               │         │
                        │  └─────────────────────────────────┘         │
                        └──────────────────────────────────────────────┘
```

### Data Flow: Upload → Search

1. User uploads file via `POST /api/knowledge/folders/{id}/documents`
2. Router stores file to `storage/`, creates `KnowledgeDocument` row
3. Router schedules async `_run_indexing_pipeline(doc_id)` background task
4. Pipeline: ContentExtractor → SemanticChunker → AIService.embedding → pgvector upsert
5. On success: `index_status='indexed'`; on failure: `index_status='failed'` + `index_error`
6. RAG consumer calls `semantic_search(project_id, query)` → pgvector ANN → top-k results

## Components and Interfaces

### 1. Unified Storage Layer (Req 1, 9)

**Legacy endpoint proxy** (`knowledge_base.py` 改造):

```python
# 现有 upload_global_document 改为委托 KnowledgeFolderService
@router.post("/api/knowledge/{category}/documents")
async def upload_global_document(category, file, db, current_user):
    folder = await _get_or_create_preset_folder(db, category)
    doc = await KnowledgeDocumentService(db).create_document(
        folder_id=folder.id, name=file.filename,
        storage_path=str(dest), file_size=len(content),
        created_by=current_user.id,
    )
    # trigger indexing pipeline
    background_tasks.add_task(_run_indexing_pipeline, db_url, doc.id)
    return {"id": str(doc.id), "name": file.filename, ...}
```

**Category → Folder 映射**: `PRESET_CATEGORIES` (已存在于 `knowledge_folder_service.py`) 的 9 个分类 key 与 `LIBRARY_DEFS` 的 9 个 key 完全一致。`_get_or_create_preset_folder` 按 category 查或建。

**迁移脚本**: `scripts/migrate_global_kb_to_pg.py`
- 遍历 `~/.gt_audit_helper/knowledge/{category}/` 每个文件
- 幂等: `SELECT ... WHERE folder_id=? AND name=?` 存在则 version+1
- 调 ContentExtractor + IndexingPipeline

**Legacy response 兼容**: 响应加 `X-Deprecated: true` + `X-New-Endpoint: /api/knowledge/folders/{id}/documents`

### 2. Content Extraction Service (Req 3)

**新文件**: `backend/app/services/content_extractor.py`

```python
class ContentExtractor:
    """工厂模式按文件扩展名分派提取器"""
    
    EXTRACTORS = {
        '.pdf': _extract_pdf,
        '.docx': _extract_docx,
        '.doc': _extract_docx,
        '.xlsx': _extract_xlsx,
        '.xls': _extract_xlsx,
        '.txt': _extract_text,
        '.md': _extract_text,
    }
    
    @classmethod
    async def extract(cls, file_path: str, timeout: int = 60) -> ExtractResult:
        """提取文本，超时60s，返回 ExtractResult(content_text, status, error)"""
        ext = Path(file_path).suffix.lower()
        extractor = cls.EXTRACTORS.get(ext)
        if not extractor:
            return ExtractResult(None, "unsupported_format", None)
        try:
            text = await asyncio.wait_for(
                asyncio.to_thread(extractor, file_path), timeout=timeout
            )
            return ExtractResult(text, "extracted", None)
        except asyncio.TimeoutError:
            return ExtractResult(None, "extraction_failed", "timeout_60s")
        except Exception as e:
            return ExtractResult(None, "extraction_failed", str(e))
```

**依赖**:
- PDF: `PyMuPDF` (fitz) — 用 `fitz.open(path)` 逐页 `page.get_text("text")` 拼接双换行
- DOCX: `python-docx` — 遍历 `Document(path).paragraphs` + `tables`
- XLSX: `openpyxl` (已有) — 遍历 sheets，非空 cell 拼接，sheet 名前缀
- TXT/MD: `Path(path).read_text("utf-8")`

**新列** (KnowledgeDocument 模型):
- `index_status: Mapped[str | None]` — 'pending'/'extracted'/'indexed'/'failed'/'unsupported_format'/'extraction_failed'
- `index_error: Mapped[str | None]` — 错误描述

### 3. Semantic Chunker (Req 4)

**新文件**: `backend/app/services/semantic_chunker.py`

替代现有 `_chunk_text` (固定500字符无重叠)。

```python
@dataclass
class Chunk:
    text: str
    chunk_index: int
    total_chunks: int  # 后填充
    section_heading: str
    overlap_start: int  # 重叠起始位置(用于round-trip还原)

def semantic_chunk(text: str, min_size=300, max_size=800, overlap=80) -> list[Chunk]:
    """语义分块：段落→句子→字符三级降级"""
    # Step 1: 按条款标记(第X条/CAS X)预分割
    # Step 2: 按双换行(\n\n+)分段落
    # Step 3: 段落>max_size → 按句子(。！？)分割
    # Step 4: 句子仍>max_size → 按max_size硬切(极端情况)
    # Step 5: 合并小片段直到达min_size
    # Step 6: 添加overlap(从前一块尾部取80字符到当前块头部)
```

**条款标记正则**: `r'^(?:第[一二三四五六七八九十百千\d]+条|CAS\s*\d+|ISA\s*\d+|[（(]\d+[)）])'`

**Heading 提取**: 最近前驱 `一、/（一）/# ` 格式标题

### 4. Indexing Pipeline (Req 2)

**新文件**: `backend/app/services/indexing_pipeline.py`

```python
async def run_indexing_pipeline(doc_id: UUID) -> None:
    """完整索引流水线（作为background task运行）"""
    async with get_async_session() as db:
        doc = await db.get(KnowledgeDocument, doc_id)
        if not doc or doc.is_deleted:
            return
        
        # Step 1: Content Extraction (如果content_text为空)
        if not doc.content_text and doc.storage_path:
            result = await ContentExtractor.extract(doc.storage_path)
            doc.content_text = result.content_text
            doc.index_status = result.status
            doc.index_error = result.error
            if result.status != "extracted":
                await db.commit()
                return
        
        # Step 2: Semantic Chunking
        chunks = semantic_chunk(doc.content_text)
        
        # Step 3: Embedding + Upsert
        svc = KnowledgeIndexService(db)
        project_id = _resolve_index_project_id(doc)
        await svc.incremental_update(
            project_id=project_id,
            source_type="knowledge_doc",
            source_id=doc.id,
            content=doc.content_text,
            doc_version=doc.version,
        )
        
        doc.index_status = "indexed"
        doc.index_error = None
        await db.commit()
```

**全局文档的project_id策略**:
- 全局公共文档(access_level=public，无project_ids)使用**哨兵UUID** `GLOBAL_KB_PROJECT_ID = UUID("00000000-0000-0000-0000-000000000000")` 索引
- `semantic_search` 查询时**同时搜索**项目自有文档 + 全局文档：`WHERE project_id IN (:user_project_id, :GLOBAL_KB_PROJECT_ID)`
- project_group 文档按其 project_ids 列表中的每个项目各索引一份
- private 文档只按创建者关联的项目索引

```python
GLOBAL_KB_PROJECT_ID = UUID("00000000-0000-0000-0000-000000000000")

def _resolve_index_project_id(doc: KnowledgeDocument) -> UUID:
    """确定文档应索引到哪个project_id"""
    folder = doc.folder  # eager load or separate query
    effective_access = doc.access_level or folder.access_level
    if effective_access == KnowledgeAccessLevel.public:
        return GLOBAL_KB_PROJECT_ID
    if effective_access == KnowledgeAccessLevel.project_group and doc.project_ids:
        return UUID(str(doc.project_ids[0]))  # 主项目
    return GLOBAL_KB_PROJECT_ID  # fallback
```

**触发点** (在 `knowledge_folders.py`):
- `upload_documents` 端点成功后: `background_tasks.add_task(run_indexing_pipeline, doc.id)`
- 文档更新(新版本): 同上 + mark_previous_stale
- 文档删除: 直接 `mark_chunks_deleted(doc.id)`

### 5. PgVector Search Backend (Req 5)

**迁移 V116**: 
```sql
-- 启用 pgvector (已安装)
CREATE EXTENSION IF NOT EXISTS vector;

-- 新增 vector 列 (保留旧 TEXT 列兼容)
ALTER TABLE knowledge_index 
  ADD COLUMN IF NOT EXISTS embedding_vec vector(1024);
-- dim=1024 for BAAI/bge-m3 embedding output (DEFAULT_EMBEDDING_MODEL)

-- HNSW 索引
CREATE INDEX IF NOT EXISTS ix_knowledge_index_embedding_hnsw
  ON knowledge_index USING hnsw (embedding_vec vector_cosine_ops)
  WITH (m = 16, ef_construction = 200);

-- knowledge_documents 新增列
ALTER TABLE knowledge_documents 
  ADD COLUMN IF NOT EXISTS index_status VARCHAR(30) DEFAULT 'pending',
  ADD COLUMN IF NOT EXISTS index_error TEXT;
```

**`_vector_search` 改写**:
```python
async def _vector_search(self, project_id, query, top_k, scope):
    query_vec = await self._ai_svc.embedding(query)
    # 同时搜索项目文档 + 全局公共文档
    from app.services.indexing_pipeline import GLOBAL_KB_PROJECT_ID
    project_ids = [project_id, GLOBAL_KB_PROJECT_ID]
    conditions = [
        KnowledgeIndex.project_id.in_(project_ids),
        KnowledgeIndex.is_deleted == False,
    ]
    # ... scope filter ...
    stmt = (
        select(
            KnowledgeIndex,
            (1 - KnowledgeIndex.embedding_vec.cosine_distance(query_vec)).label("score")
        )
        .where(*conditions)
        .order_by(KnowledgeIndex.embedding_vec.cosine_distance(query_vec))
        .limit(top_k)
    )
    result = await self._db.execute(stmt)
    ...
```

**`_upsert_chunk` 同步写两列**: 旧 `embedding_vector` TEXT + 新 `embedding_vec` vector(1024)，迁移期双写，稳定后废弃TEXT列。

### 6. Jieba BM25 Fallback (Req 6)

**替换 `_zh_tokenize.py`**:

```python
import jieba

# 加载审计领域词典
_DICT_LOADED = False
def _ensure_dict():
    global _DICT_LOADED
    if not _DICT_LOADED:
        dict_path = Path(__file__).parent.parent.parent / "data" / "jieba_audit_dict.txt"
        if dict_path.exists():
            jieba.load_userdict(str(dict_path))
        _DICT_LOADED = True

def zh_tokenize(text: str) -> list[str]:
    _ensure_dict()
    return [w for w in jieba.cut(text) if w.strip()]

def zh_tokenize_batch(texts: list[str]) -> list[list[str]]:
    _ensure_dict()
    return [zh_tokenize(t) for t in texts]
```

**词典文件**: `backend/data/jieba_audit_dict.txt`
格式: `词 词频 词性`，至少500条审计领域词汇(会计科目/准则术语/监管机构)。

### 7. Context-Aware Search (Req 7)

**`semantic_search` 扩展签名**:
```python
async def semantic_search(
    self, project_id, query, top_k=10, *,
    scope="all", user=None,
    wp_code: str | None = None,
    account_code: str | None = None,
    audit_area: str | None = None,
) -> list[dict]:
```

**上下文加权**:
```python
def _apply_context_boost(results, wp_code, account_code):
    """对结果应用上下文加权: final = 0.7*vector + 0.3*boost"""
    for r in results:
        boost = 0.0
        if wp_code and _matches_cycle(r, wp_code):
            boost += 0.5
        if account_code and _matches_account(r, account_code):
            boost += 0.5
        r["score"] = 0.7 * r["score"] + 0.3 * boost
    results.sort(key=lambda x: x["score"], reverse=True)
```

### 8. RAG Consumer Wiring (Req 8)

**`ReferenceDocService.load_from_knowledge_base` 改造**:
- 主路径已正确调用 `KnowledgeIndexService.semantic_search`
- 问题是 knowledge_index 表为空→返回空。接通 Pipeline 后自动解决。
- 结果增加 `document_name` + `folder_path` 字段(JOIN KnowledgeDocument + KnowledgeFolder)

**`b14_ai_generate._load_knowledge_base_docs`**: 已正确调用 `load_from_knowledge_base`，Pipeline 接通后自动有数据。

**搜索结果结构扩展**:
```python
{
    "source_type": "knowledge_doc",
    "source_id": "uuid",
    "content": "chunk text...",
    "score": 0.85,
    "chunk_index": 2,
    "doc_version": 3,
    "is_stale": False,
    "document_name": "CAS 22 金融工具确认和计量.pdf",  # 新增
    "folder_path": "会计准则库",  # 新增
}
```

### 9. Permission Filtering (Req 10)

现有 `_filter_by_permission` 已实现完整的 public/project_group/private 过滤逻辑。
- 验证 orphan handling (source_id 在 KnowledgeDocument 中不存在时排除)
- 确保 post-scoring 时序正确

## Data Models

### Migration V116

```sql
-- 1. pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- 2. knowledge_documents 扩展
ALTER TABLE knowledge_documents 
  ADD COLUMN IF NOT EXISTS index_status VARCHAR(30) DEFAULT 'pending';
ALTER TABLE knowledge_documents 
  ADD COLUMN IF NOT EXISTS index_error TEXT;

-- 3. knowledge_index 向量列
ALTER TABLE knowledge_index 
  ADD COLUMN IF NOT EXISTS embedding_vec vector(1024);

-- 4. HNSW 索引
CREATE INDEX IF NOT EXISTS ix_ki_embedding_hnsw
  ON knowledge_index USING hnsw (embedding_vec vector_cosine_ops)
  WITH (m = 16, ef_construction = 200);

-- 5. 复合过滤索引 (pre-filtering 加速)
CREATE INDEX IF NOT EXISTS ix_ki_project_source_active
  ON knowledge_index (project_id, source_type)
  WHERE is_deleted = false;
```

### ORM 同步

- `KnowledgeDocument`: 加 `index_status`, `index_error` 列声明
- `KnowledgeIndex`: 加 `embedding_vec` 列声明 (pgvector Vector type)

## Correctness Properties

### Property 1: Round-trip chunking

chunk → concat(remove overlaps) = original. FOR ALL valid text inputs, chunking then concatenating chunks in order (removing overlap regions from each chunk after the first) SHALL produce output character-for-character identical to original input.

**Validates: Requirements 4.5**

### Property 2: Content extraction idempotence

Extracting the same file multiple times SHALL produce the identical content_text output.

**Validates: Requirements 3**

### Property 3: Indexing idempotence

Triggering the indexing pipeline N times for the same document version SHALL produce identical chunk entries in knowledge_index (upsert convergence).

**Validates: Requirements 2.6**

### Property 4: Permission never leaks private docs

FOR ALL search results, IF a document has effective access_level="private" AND the querying user.id != document.created_by, THEN that document SHALL NOT appear in results.

**Validates: Requirements 10.4**

### Property 5: Audit terms tokenize as single tokens

FOR ALL terms in jieba_audit_dict.txt, zh_tokenize(term) SHALL produce exactly [term] as a single-element list.

**Validates: Requirements 6.5**

### Property 6: Context boost bounded

FOR ALL combinations of wp_code and account_code inputs, the computed context_boost value SHALL be in [0.0, 1.0].

**Validates: Requirements 7.4**

### Property 7: Migration idempotence

Running the migration script twice on the same file system state SHALL NOT create duplicate documents (matched by folder_id + filename).

**Validates: Requirements 9.5**

### Property 8: Soft-delete cascades to index

WHEN a document is soft-deleted, ALL chunks in knowledge_index with matching source_id SHALL have is_deleted=True.

**Validates: Requirements 2.5**

### Property 9: Version update stale marking

WHEN a new version is indexed, ALL chunks from the previous version SHALL be marked is_stale=True AND the new version's chunks SHALL have is_stale=False.

**Validates: Requirements 2.4**

### Property 10: Legacy response schema compatibility

FOR ALL legacy endpoint responses, the JSON structure SHALL contain at minimum: id, name, size fields matching the original file-system-based response format.

**Validates: Requirements 1.4**

### Property 11: Chunk size bounds

FOR ALL chunks produced by semantic_chunk(), len(chunk.text) SHALL be in [1, 800] characters, EXCEPT when the entire input is < 300 chars (single chunk = full input).

**Validates: Requirements 4.2**

### Property 12: pgvector recall accuracy

FOR a test corpus of 1000 chunks, pgvector HNSW top-10 results SHALL have recall ≥ 0.95 compared to exact brute-force cosine similarity top-10.

**Validates: Requirements 5**

## Error Handling

- **ContentExtractor 超时**: 60s hard limit via `asyncio.wait_for`，超时设 `extraction_failed` + `index_error="timeout_60s"`
- **Embedding 服务不可用**: `_vector_search` 抛异常 → 捕获后降级 BM25 → BM25 也失败 → ilike 兜底
- **Pipeline 异常**: 任何阶段失败都写 `index_status="failed"` + `index_error`，不影响文档可用性
- **pgvector 不可用**: 查询时捕获 `ProgrammingError` → 降级 BM25
- **损坏文件**: ContentExtractor 返回 `extraction_failed`，不阻塞上传成功

## Testing Strategy

- **单元测试**: ContentExtractor(mock文件)、SemanticChunker(纯函数)、context_boost(纯函数)
- **PBT (Hypothesis)**: P1-P12 属性，`max_examples=5`
- **集成测试**: IndexingPipeline end-to-end (真实PG + 真实pgvector)
- **契约测试**: Legacy endpoint schema backward compatibility
- **Playwright**: 上传文件→等待索引→搜索→验证结果非空

## Implementation Phases

### Phase 1 — Core Pipeline (P0, Req 2/3/4/8)
**Wave 0-3**: ContentExtractor + SemanticChunker + IndexingPipeline + 触发接线 + RAG验证
- 最小闭环: 上传TXT→自动索引→semantic_search返回非空→AI生成引用知识库

### Phase 2 — Storage & Search (P0, Req 1/5/6)
**Wave 4-7**: V116迁移 + pgvector改写 + jieba词典 + 旧端点代理
- pgvector替代内存暴力 + 中文分词升级 + 存储统一

### Phase 3 — Enhancement (P1, Req 7/9/10)
**Wave 8-10**: Context-aware search + 迁移脚本 + 权限验证加固
- 上下文感知 + 全局KB数据迁移 + orphan清理

## Dependencies

| Package | Version | Purpose | Status |
|---------|---------|---------|--------|
| PyMuPDF (fitz) | ≥1.23 | PDF text extraction | **新增** |
| python-docx | ≥1.1 | DOCX text extraction | **新增** |
| jieba | ≥0.42 | Chinese word segmentation | **新增** |
| pgvector (extension) | ≥0.5 | Vector similarity search | 已安装 |
| openpyxl | 已有 | XLSX extraction | 已有 |
| bm25s | 已有 | BM25 retrieval | 已有 |
| numpy | 已有 | Vector operations | 已有 |

## Validates Requirements

| Design Section | Requirements |
|---------------|-------------|
| §1 Unified Storage | Req 1, Req 9 |
| §2 Content Extraction | Req 3 |
| §3 Semantic Chunker | Req 4 |
| §4 Indexing Pipeline | Req 2 |
| §5 PgVector Search | Req 5 |
| §6 Jieba BM25 | Req 6 |
| §7 Context-Aware | Req 7 |
| §8 RAG Wiring | Req 8 |
| §9 Permission | Req 10 |
