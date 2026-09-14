# Design Document

## Overview

把知识库 RAG 检索接入附注 AI 正文生成，是一个**加法式、可开关、fail-open** 的改造：在 `DisclosureEngine` 的 LLM 正文生成上游插入一层"检索 → 拼上下文 → 附 Citation"，并在上年附注缺失时增加"知识库文档回退"。前端在 DisclosureEditor 增加"AI 填充 / 参照文档填充"入口并展示 Citation，采纳仍走既有 AI 治理确认流。

核心原则：
- **不新建检索实现**：复用 `KnowledgeIndexService.semantic_search`（已核实签名/返回结构）。
- **不改数据表 / 不改模板骨架 / 不改底稿→附注同步**：仅在正文生成链路与前端填充入口加料。
- **Fail-Open + 开关**：任何一环失败或开关关闭 → 逐字退回现有三级填充；现有测试零回归。
- **AI 治理不变**：Grounded_Draft 经现有 `wrap_ai_output_with_log`/采纳流，pending 才落库。

## Architecture

```
┌─────────────────────────── 后端 ───────────────────────────┐
│                                                            │
│  DisclosureEngine.generate_notes / refill_sections         │
│        │  (每章节正文填充，优先级链)                          │
│        ▼                                                    │
│  ┌──────────────────────────────────────────────┐          │
│  │ NoteKnowledgeEnricher  (新增，薄编排层)          │          │
│  │  - build_note_context_query(section,account)   │          │
│  │  - retrieve(query, scope, doc_filter, ctxboost)│──┐       │
│  │  - build_grounded_prompt(chunks) + citations   │  │       │
│  │  - fail-open: 异常/空命中 → 返回 None            │  │       │
│  └──────────────────────────────────────────────┘  │       │
│        │ 注入点1: _generate_text_with_llm 上游         │       │
│        │ 注入点2: 上年缺失 → prior-year 知识库回退       │       │
│        ▼                                             ▼       │
│  llm_client.chat_completion         KnowledgeIndexService     │
│  (system+grounded user prompt)      .semantic_search          │
│                                     (scope='knowledge_doc')   │
└────────────────────────────────────────────────────────────┘
                    │ 生成结果 = {text, citations}
                    ▼
┌─────────────────────────── 前端 ───────────────────────────┐
│  DisclosureEditor.vue                                       │
│   ├─ "AI 填充" / "参照文档填充" 按钮（当前章节）              │
│   ├─ NoteAiFillDialog（新增）: 参照范围选择 + 预览草稿+Citation │
│   └─ 采纳 → 现有 AI 治理确认流（不直接写 text_content）        │
└────────────────────────────────────────────────────────────┘
```

### 架构决策

| 决策 | 选择 | 理由 |
|------|------|------|
| 检索实现 | 复用 `semantic_search`，不新建 | 已有 pgvector+BM25+ilike 三级降级+权限过滤+enrich，Req1.6/4.4 |
| 编排层位置 | 新建 `NoteKnowledgeEnricher` 薄服务，不把逻辑塞进 `_generate_text_with_llm` | 隔离 RAG 逻辑便于单测+开关，`_generate_text_with_llm` 仅多一次调用 |
| 开关 | `settings.DISCLOSURE_NOTE_RAG_ENABLED`（默认由配置定，可关）| Req6.2/6.3 零回归可回退 |
| 失败策略 | 一律 fail-open 返回 None → caller 退回现有路径 | Req6.1/6.4，RAG 是增强非依赖 |
| 上年回退顺序 | DB(year-1) → 知识库检索 → LLM → 模板 | Req2.2 保持 DB 优先，知识库仅补缺 |
| AI 治理 | 不改确认流，只在上游补上下文+Citation | Req5.3 |
| Citation 传递 | Grounded_Draft 返回 `{text, citations[]}`；前端展示、采纳时随附注留痕 | Req1.5/3.2/5.2 |

## Components and Interfaces

### 后端

**`NoteKnowledgeEnricher`（新增 `app/services/note_knowledge_enricher.py`）**

```python
class GroundedDraft:
    text: str | None            # None = 未生成（fail-open / reference-only）
    citations: list[Citation]   # 命中来源；空列表 = 无 RAG 依据
    degraded: bool = False      # True = 检索/LLM 降级（无依据的通用生成 或 无生成）

class Citation:
    document_name: str | None
    folder_path: str | None
    snippet: str                # 截断后的片段摘要
    score: float
    source_id: str
    is_stale: bool = False       # 知识库索引过期标记（Req1.5 透传供新鲜度判断）

# 反幻觉 system prompt（Req9.2）——Narrative_Only：约束只依据所供资料/数据，
# 不虚构未提供的金额/比例/日期/主体名称；数值以表格/resolver/底稿为准。
_GROUNDED_SYSTEM_PROMPT_ZH = (
    "你是资深审计师，用中文起草财务报表附注正文。"
    "严格要求：①只依据下方提供的参照资料与数据表述，优先沿用参照资料的口径与结构；"
    "②绝不虚构未提供的金额、比例、日期、主体名称；③披露数值以附注表格为准，"
    "你只起草文字叙述、不编造数字。"
)

class NoteKnowledgeEnricher:
    def __init__(self, db, *, knowledge_service=None): ...

    def build_query(self, section_title: str, account_name: str,
                    account_code: str | None) -> str:
        """Note_Context_Query：标题+科目名+关键词，不含整段模板（Req7.1）。"""

    async def retrieve(self, project_id, query, *, user=None,
                       account_code=None, audit_area=None,
                       doc_filter: list[UUID] | None = None,
                       top_k: int = 5) -> list[Citation]:
        """复用 semantic_search(scope='knowledge_doc', 含 project + Global_KB); 
        异常/空 → []（fail-open, Req1.3/6.1）。doc_filter 非空时按 document/folder
        过滤（Req4.1）；权限过滤经 semantic_search user 参数（Req4.4）。
        content 字段读结果 dict 的 'content'；透传 is_stale。"""

    def build_grounded_user_prompt(self, base_context: str,
                                   citations: list[Citation],
                                   char_budget: int = 3000) -> str:
        """拼参照上下文（标注 document_name），超预算截断（Req7.3）。"""

    async def generate_note_text(self, project_id, year, note_section,
                                 section_title, account_name, *,
                                 account_code=None, audit_area=None,
                                 user=None, doc_filter=None,
                                 reference_only: bool = False) -> GroundedDraft:
        """检索→（reference_only 则直接返回 citations 不生成，text=None, degraded=True, Req4.5）
        →拼prompt（Narrative_Only system prompt, Req9）→chat_completion；
        任一环失败返回 GroundedDraft(text=None, citations=[], degraded=True)。生成中文（Req1.7）。"""

    async def retrieve_prior_year_note(self, project_id, note_section,
                                       section_title, account_name) -> GroundedDraft | None:
        """Req2：上年附注知识库回退；无命中→None。"""

    async def batch_prefill(self, project_id, year, sections: list[dict], *,
                            user=None, on_progress=None) -> list[dict]:
        """Req10：对空/草稿章节逐个 generate_note_text；单章 try/except 隔离降级，
        返回逐章节 {note_section, status(generated|degraded|skipped), text, citations}。
        跳过已有实质正文/锁定/manual_override 章节（Req10.4）。"""
```

**`DisclosureEngine` 改造（注入点，最小侵入）**

- `_generate_text_with_llm`：开关开启时先调 `enricher.generate_note_text(...)`；返回 `text` 非空则用之（附 citations 上浮给 caller），否则退回现有通用 LLM 路径。
- `generate_notes` 优先级 1（上年）分支：`_prior_notes_cache` 缺失该 section 时，开关开启则调 `enricher.retrieve_prior_year_note(...)`，命中则作为上年来源 + 记 Citation。
- `_generate_text_with_llm` 返回签名保持返回 `str | None` 不破坏现有 caller；Citation 通过引擎实例上的 `_last_citations: dict[note_section, list[Citation]]` 暂存，供生成结果落库/返回时附带（避免改多处签名）。

**新增/复用 API 端点（`routers/disclosure_notes.py`）**

```
POST /api/disclosure-notes/{project_id}/{year}/{note_section}/ai-fill
  body: { doc_filter?: [uuid], reference_only?: bool }
  resp: { text, citations:[{document_name, folder_path, snippet, score, is_stale}],
          degraded: bool, skipped_docs?: [uuid] }
  —— 供前端"AI 填充/参照文档填充"预览；不落库（Req3.1/5.1/Property11）

POST /api/disclosure-notes/{project_id}/{year}/batch-ai-fill
  body: { doc_filter?: [uuid] }
  resp: { results:[{note_section, status, text, citations}], generated, degraded, skipped }
  —— 一键批量预填充空/草稿章节，逐章降级隔离；不落库（Req10）
```

采纳仍走既有 `/api/ai-chat/adopt`（`useDocAiChat.adoptContent`），落库仅写 `text_content`（substantive），不碰 `guidance_text`（Req5.2）。

**配置（`app/core/config.py`）**

- `DISCLOSURE_NOTE_RAG_ENABLED: bool`（默认值由部署定）
- `DISCLOSURE_NOTE_RAG_TOP_K: int = 5`
- `DISCLOSURE_NOTE_RAG_CHAR_BUDGET: int = 3000`

### 前端

**`NoteAiFillDialog.vue`（新增，`components/disclosure/`）**
- 模式切换：AI 生成 / 参照文档（Reference_Only，仅展示片段供人工复制，Req4.5）
- 参照范围选择（知识库文档/文件夹多选，可空=项目+Global_KB）
- 触发 `POST .../ai-fill` → 展示 Grounded_Draft 预览 + Citation 列表（document_name/folder_path 可点选，`is_stale` 标"参照资料索引已过期"提示）
- 数字提示：草稿含金额时提示"AI 文字中的数字须与附注表格核对"（Req9.3）
- "采纳"→ 走现有 `useDocAiChat.adoptContent` 确认流（仅写 text_content）；"不采纳"→ 关闭，`text_content` 不变
- WHERE 章节被 `sectionLocks` 锁定 → "采纳"禁用（可预览不可写，Req3.6）

**`DisclosureEditor.vue` 改造**
- 当前章节工具栏加"AI 填充""参照文档填充"按钮 → 打开 `NoteAiFillDialog`
- 顶部工具栏加"一键 AI 预填充"→ `POST .../batch-ai-fill`，进度反馈 + 逐章结果供确认（Req10）
- 无命中时 dialog 明确提示"未检索到可参照的知识库文档，已用通用生成"（Req3.4）

## Data Models

不新增/不修改数据库表。

- 检索结果沿用 `semantic_search` 返回的 dict：`{content, source_type, source_id, score, document_name, folder_path}`。
- `GroundedDraft`/`Citation` 为进程内 DTO，不落库。
- 采纳后 Citation 溯源随现有 AI 采纳流的日志记录（`wrap_ai_output_with_log` 的 payload 附 `citations`），不新建表。

## Correctness Properties

### Property 1: 检索命中即注入上下文
WHEN retrieve 返回 ≥1 条 citation THEN build_grounded_user_prompt 的输出必须包含至少一条命中片段文本与其 document_name 标注。
**Validates: Requirements 1.1, 1.2**

### Property 2: Fail-Open 不抛
WHEN semantic_search 抛异常 OR 返回空 THEN generate_note_text 返回 `GroundedDraft(text=None, citations=[])`，绝不向上抛异常。
**Validates: Requirements 1.3, 6.1, 6.4**

### Property 3: 上年来源优先级
GIVEN year-1 DB 附注存在 THEN 该章节正文来源必为 DB 记录，retrieve_prior_year_note 不被调用（或其结果不覆盖 DB）。
**Validates: Requirements 2.1, 2.2**

### Property 4: 上年知识库回退仅在缺失时
WHEN year-1 DB 附注缺失 AND 知识库检索命中 THEN 正文取知识库片段且 citations 非空且标注来源为 knowledge_doc。
**Validates: Requirements 2.1, 2.3**

### Property 5: Citation 与命中一致
THE Grounded_Draft.citations 的每条 (document_name, source_id, score) 必须来自本次 retrieve 命中的 chunk，无凭空构造。
**Validates: Requirements 1.5, 3.2**

### Property 6: 关闭开关零回归
WHEN DISCLOSURE_NOTE_RAG_ENABLED=False THEN `_generate_text_with_llm` 与 generate_notes 的行为与接入前逐字一致（不调用 enricher）。
**Validates: Requirements 6.2, 6.3**

### Property 7: 查询串不含整段模板噪声
THE build_query 输出仅由 section_title + account_name + 派生关键词组成，不包含传入的整段 text_template/text_sections。
**Validates: Requirements 7.1**

### Property 8: 上下文字符预算
WHEN 命中片段总长超过 char_budget THEN build_grounded_user_prompt 输出被截断到 ≤ char_budget（含预留），不溢出。
**Validates: Requirements 7.3**

### Property 9: 参照范围过滤
WHEN doc_filter 非空 THEN retrieve 结果的 source_id 全部 ∈ doc_filter 指定文档（或其文件夹下文档）；不命中范围的片段不进上下文。
**Validates: Requirements 4.1, 4.3**

### Property 10: 权限不绕过
THE retrieve 传入 user 时，结果必经 semantic_search 的权限过滤（无权文档不出现在 citations）。
**Validates: Requirements 4.4**

### Property 11: AI 不自动写
WHEN ai-fill 端点返回 Grounded_Draft THEN `disclosure_notes.text_content` 未被本次调用修改（仅采纳流才写）。
**Validates: Requirements 5.1, 3.3, 3.5**

### Property 12: 批量单章降级隔离
WHEN generate_notes 遍历中某章节 enricher 抛错 THEN 仅该章节降级，其余章节正常生成，整体不失败。
**Validates: Requirements 6.4, 10.2**

### Property 13: Reference-Only 不生成
WHEN reference_only=True THEN generate_note_text 返回 text=None 且 citations 为检索命中片段，且不调用 llm_client.chat_completion（0 次生成调用）。
**Validates: Requirements 4.5, 8.6**

### Property 14: 反幻觉 system prompt 约束
THE build_grounded_user_prompt / 生成调用所用 system prompt 必须含 Narrative_Only 约束文本（不虚构金额/比例/日期/主体），且 AI 生成路径不写入任何附注表格数值单元格。
**Validates: Requirements 9.1, 9.2, 9.4**

### Property 15: 批量跳过既有内容
WHEN batch_prefill 遇到已有实质正文 / 锁定 / manual_override 的章节 THEN 该章节 status=skipped 且其 text_content 不被修改。
**Validates: Requirements 10.4**

### Property 16: 中文输出
THE generate_note_text 的 system prompt 要求中文输出（`_GROUNDED_SYSTEM_PROMPT_ZH`）。
**Validates: Requirements 1.7**

## Testing Strategy

- **单元/PBT**（`backend/tests/`）：`NoteKnowledgeEnricher` 各方法——build_query（P7）、retrieve fail-open（P2/P10）、build_grounded_user_prompt 截断（P8）、doc_filter（P9）、citations 一致（P5）；`hypothesis` 覆盖 P1/P8/P9（max_examples=5，遵循 fast profile）。
- **集成**（mock semantic_search + mock llm_client）：generate_notes 优先级链（P3/P4）、关闭开关零回归（P6，断言 enricher 未被调用）、批量单章降级（P12）、ai-fill 端点不写库（P11）。
- **前端 vitest**：NoteAiFillDialog 展示 Citation、无命中提示（Req3.4）、采纳走 adoptContent。
- **Playwright（可选收尾）**：DisclosureEditor AI 填充 → 预览 Citation → 采纳 → 确认流 → 附注文字更新（需知识库有已索引文档的实例化项目）。

## Error Handling

- 检索/LLM 任一失败 → fail-open 返回 None/空，日志 `logger.warning`，caller 退回现有路径。
- 配置缺省 → 开关按默认值，缺失参数用默认 top_k/char_budget。
- ai-fill 端点：知识库不可用返回 `{text:null, citations:[], degraded:true}`，前端据此提示（Req3.4），HTTP 仍 200（非错误）。
- 权限：doc_filter 含无权/已删文档 → 跳过并在响应 `skipped_docs` 标注，不 500。
