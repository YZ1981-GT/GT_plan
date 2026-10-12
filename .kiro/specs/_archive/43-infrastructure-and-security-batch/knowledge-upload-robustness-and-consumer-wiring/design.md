# 知识库上传健壮性与下游消费方接线 — 设计

## 一、上传写路径（`routers/knowledge_folders.py::_store_uploaded_files`）

```
for file in files:
    落盘（唯一名）→ 抽正文（txt/md/csv 走 _decode_text_bytes；其余走既有 _extract_text_with_ocr）
    try:
        async with db.begin_nested():          # R1.1 每文件一个 SAVEPOINT
            doc = await svc.create_document(...) # 内部 flush → 约束错误在此抛出
    except Exception as exc:
        删除已落盘文件（R1.3）; failed.append({filename, reason: _upload_failure_reason(exc)})
        continue
await db.commit()   # 只提交成功的文件
return {"uploaded", "files", "failed", "folder_id"}
```

- 为什么是 SAVEPOINT 而不是「每文件 commit」：commit 会让「同名重传建版本链」的读写跨事务，并破坏调用方（A17-3 项目上传）先 `ensure_project_folder` 再上传的原子性；SAVEPOINT 失败只回滚本文件语句，与平台既有做法一致（`_trigger_index_delete`、`ensure_project_folder`）。
- `_upload_failure_reason(exc)`：按异常类别给中文原因（名称/类型过长、含无法存储的字符、写库失败），**不**回显 SQL 与异常原文（可能含路径 / 参数）。
- 抽正文失败 ≠ 上传失败：正文为空的文件照常入库（原文件可下载），由 `text_extracted=false` 告知前端（R4.2）。

## 二、ORM 层清洗（`models/knowledge_models.py`）

```python
# KnowledgeDocument
@validates("name", "content_text", "content_summary", "tags")
def _strip_nul(self, key, value): ...   # str 去 \x00；tags 为 list 时逐项去

@validates("file_type")
def _norm_type(self, key, value): return normalize_file_type(value)

# KnowledgeFolder（同类：文件夹名来自 JSON，"\u0000" 同样让 PG 500）
@validates("name", "description")
def _strip_nul(self, key, value): ...
```

- 放在 ORM 而非上传入口：现查写 `knowledge_documents` 的路径 7 条（文件夹上传、项目上传、`POST /documents`、AI 笔记转存、版本回滚、批量建文档、索引流水线回填正文），全部经 ORM 实例构造或属性赋值；只修上传会漏其余 6 条（触类旁通）。`tags` 为 JSONB，PG 同样拒收 `\u0000`。
- `normalize_file_type`（`knowledge_folder_service.py`，纯函数）：去首点、去空白、小写；`len > 20` 或不匹配 `^[a-z0-9_+-]+$` → `None`。与 `KnowledgeDocument.file_type` 列宽（String(20)）绑定为常量并加断言，防止两边漂移。
- 小写化的影响面：后端无按大小写比较 `file_type` 的代码（现查仅 `attachment_service` 且它自己先 `.lower()`）；前端 `docExt` 已 `.toLowerCase()`。

## 三、文本解码（`_decode_text_bytes(content) -> str`，纯函数）

| 顺序 | 判据 | 解码 |
|------|------|------|
| 1 | BOM `EF BB BF` / `FF FE` / `FE FF` | `utf-8-sig` / `utf-16` |
| 2 | 无 BOM 且样本（前 4KB）一侧奇偶位 NUL ≥ 10%、另一侧 ≤ 2% | `utf-16-le` / `utf-16-be` |
| 3 | 严格 `utf-8` 成功 | `utf-8` |
| 4 | 严格 UTF-8 失败：合法多字节字符 ≥ 4 × 替换符（零星损坏的 UTF-8） | `utf-8` + `errors="replace"` |
| 5 | 否则严格 `gb18030` 成功 | `gb18030`（GBK 超集，覆盖中文 Windows 默认编码） |
| 6 | 以上皆失败 | `utf-8` + `errors="replace"` |

- 第 4 步按「多字节字符 / 替换符」之比裁决，而不是按替换符占全文比例：大半是 ASCII 的 GBK 文件（数字 + 几个中文表头）替换符比例很低，按比例判会被误留在 UTF-8，恰好把仅有的中文变成乱码。
- **已知局限**：全中文、无 BOM 的 UTF-16 几乎不含 NUL 字节，第 2 步识别不到，会按 GB18030 解成乱码（不会失败，只是检索不到）。NUL 分布无法区分它与「混入零星 NUL 的 UTF-8」；记事本 / Excel / PowerShell 另存 Unicode 时均写 BOM，实际罕见，不加统计模型。
- 结果截断 50,000 字（与既有上限一致）；NUL 由 R2 的 ORM 层统一剔除，本函数不重复处理。
- 抽正文前实测：anydoc 把 GBK 编码的 CSV 按 Latin-1 解读（`¿ÆÄ¿`），故 `.csv` 也走本函数；`.xlsm` 经 anydoc 正常抽出（4055 字）。

## 四、附注 AI 接知识库（`routers/note_ai.py`）

- 删除 L153 的 query 版 `ai_complete`（被 FastAPI 先注册先匹配，body 版从未可达）；保留 body 版。
- `ContinueWriteRequest` / `RewriteRequest` 追加 `knowledge_doc_ids: list[str] = Field(default_factory=list, max_length=5)`。
- 共享 helper：

```python
async def _load_selected_knowledge(db, project_id, user, doc_ids) -> list[str]:
    docs = await KnowledgeIndexService(db).load_documents(doc_ids, user=user, project_id=project_id)
    return [f"【知识库 - {d['document_name']}】\n{(d['content'] or '')[:4000]}" for d in docs if d.get("content")]
```

  - `load_documents` 已实现：逐篇过 `can_retrieve(project, user, P, …)`、SAVEPOINT 内读、失败返回 `[]`、保序、允许点名旧版本。
  - 注入顺序：知识文档在前、上年附注在后（`chat_completion` 截断 8000 字时优先保留用户点选的资料）。
- 两个端点改挂 `require_project_access("readonly")`（D4：其余 note_ai 端点不在本 spec）；响应追加 `knowledge_count`。
- 不接受前端拼好的正文：前端文本不可信（可被伪造成任意内容注入提示词），且 `buildContext` 依赖的取正文端点不存在。

## 五、前端

| 文件 | 改动 |
|------|------|
| `apiPaths/system.ts` | `knowledgeLibrary` 为唯一知识库路径源；`knowledge` 只保留后端确有的 `libraries`（其余 4 个删除） |
| `composables/useKnowledge.ts` | `search` → `P_kl.search`；`buildContext` 改为纯本地（名称 + snippet，仅作界面回显）；`getDocContent` → `P_kl.documentPreview` |
| `views/composables/useNoteAi.ts` | 维护 `knowledgeDocIds`；续写/改写传 `knowledge_doc_ids`；按响应 `knowledge_count` 提示 |
| `services/commonApi.ts` | `noteAiContinueWrite` / `noteAiRewrite` 参数类型改 `knowledge_doc_ids?: string[]` |
| `views/AuditReportEditor.vue` | 「📚 知识库」→ 点击提示开发中；移除无效果的「已加载 N 篇」状态与选择器挂载 |
| `views/KnowledgeBase.vue` | 上传逐文件收集后端 `failed[].reason` 与 `text_extracted=false`，结束后一次性 `ElNotification` 列出；拖拽改用 `utils/dropEntries.ts` |
| `utils/dropEntries.ts`（新） | `collectDroppedFiles(items)`：`readEntries` 循环读尽；按 `entry.fullPath` 计算相对路径，返回 `{file, relativePath}[]` |
| `GtA173ConsultationRecord.vue` | 成功回调读 `failed[0].reason`；`on-error` 解析响应体 `message/detail` |

拖拽相对路径不能写回 `File.webkitRelativePath`（只读 getter），故上传侧改读 `relPath(f) = relativePathMap.get(f) ?? f.webkitRelativePath ?? f.name`。

## 六、守卫

| 守卫 | 判据 | 防空转 |
|------|------|--------|
| `test_knowledge_upload_robustness_pg.py`（真库） | R1.4 / R2.3：三文件混批、NUL、file_type 超长 | 反向对照：无 SAVEPOINT 旧实现三文件全失；绕过 ORM 清洗写 NUL 必失败 |
| `test_knowledge_text_decode.py` | R3.2 三种编码逐字相等；`normalize_file_type` 边界 | 纯函数 |
| `test_note_ai_knowledge_context.py`（端点） | body 版续写可达（不再 422）；`knowledge_doc_ids` 可见文档注入、不可见静默跳过、`knowledge_count` 如实；未授权 403 | override 内层 `get_current_user`/`get_db`，真判定跑 |
| `test_duplicate_route_registration_baseline.py` | 重复 (method,path) 集合 ⊆ 冻结基线（10 组），且 `ai/complete` 不在其中 | 路由总数 ≥ 2000；注入一个重复路由必命中 |
| `test_frontend_knowledge_paths_exist.py` | `apiPaths` 中 `/api/knowledge*` 静态路径全部在后端路由表可解析 | 反向：注入 `/api/knowledge/search` 必报 |
| `dropEntries.spec.ts` / `useKnowledge.spec.ts` / `useNoteAi` 用例 | R5.3、R6.1、R6.2 | 250 条目替身；断言请求 URL 与 body |

## 七、变异清单

M1 去掉每文件 SAVEPOINT → 混批用例红 · M2 去掉 NUL validator → NUL 用例红 · M3 `normalize_file_type` 不截断 → 超长用例红 · M4 `_decode_text_bytes` 去掉 GB18030 分支 → GBK 用例红 · M5 恢复 query 版 `ai/complete` → 重复路由守卫与续写 422 用例红 · M6 `load_documents` 换成不判权的直查 → 不可见文档注入用例红 · M7 `readEntries` 只调一次 → 250 条目用例红。

## 八、风险

| 风险 | 缓解 |
|------|------|
| GB18030 把非中文的二进制误判为「成功解码」 | 只对 txt/md/csv 生效；解码结果只进 `content_text` 供检索，原文件不变可下载 |
| ORM validator 对批量 `update()` 语句不生效 | 现查写正文的 5 条路径全部走 ORM 实例赋值；Core `update()` 只更新 `is_deleted`/`name`（重命名已有 `_clean_name`） |
| 删 query 版 `ai/complete` 影响未知调用方 | 全仓 grep：前端与 e2e 均用 JSON body；query 版自注册起从未可达（被遮蔽） |

## 九、实施勘误（2026-10-01 收尾时登记；上文原文不改）

1. **§五 文件名**：`utils/dropEntries.ts` / `collectDroppedFiles` 实际为 `utils/knowledgeUpload.ts` 的 `collectFromEntries` / `readAllEntries` / `entriesFromDataTransfer`（同文件还放了 `parseUploadResponse` / `buildUploadSummary` / `noTextHint` 等页面纯逻辑，便于单测）。§六 守卫表的 `dropEntries.spec.ts` 对应 `utils/__tests__/knowledgeUpload.spec.ts`。
2. **§五 `buildContext`**：不是「改为纯本地」，而是**删除**——续写 / 改写只发文档 ID，界面回显直接用选取结果的文档名，没有任何调用方再需要它。
3. **§四 预算**：`_load_selected_knowledge` 不是逐篇 4000 字，而是总预算 `_KNOWLEDGE_BUDGET_CHARS=6000` 按可用篇数均分（下限 500）。逐篇 4000 时 3 篇合计 12000 > `chat_completion` 的 8000 截断，第 3 篇会整篇丢失而 `knowledge_count` 仍计入。正文为空的文档不计入。`knowledge_doc_ids` 类型为 `list[UUID]`（非 `list[str]`），格式错误直接 422。
4. **§六 真库守卫的故障注入**：原写法把 `_insert_document_isolated` 整个替换成测试文件里的 SAVEPOINT 拷贝，导致删掉生产代码的 `begin_nested` 后守卫仍全绿（变异 M1 首跑 SURVIVED）。现改为在 **service 层**（`KnowledgeDocumentService.create_document`）注故障，「现行」路径原样跑生产写库函数；快照加 `production_path` 自检，`restored_hook` 同时核对 service 方法已还原。教训：测试只负责制造故障，被验证的写路径必须是生产代码本身。
5. **§七 变异清单**扩为 M1–M23：M8–M20 覆盖 `has_text` / `text_extracted` 去空白口径、UTF-16 绝对下限、写库失败删盘、commit 失败清理、通知内联样式、跳过计数重置、XHR `ontimeout`、拖拽 `fullPath`、后端 `failed` 原因透传、请求体 `knowledge_doc_ids`、A17-3 两个回调；M21–M23 覆盖下条 R4.2 修正。全部 KILLED、还原 sha256 一致。
6. **R4.2「区分扫描件」首版未达标**（Task 9 真浏览器实测发现）：首版对所有无正文文件都提示「扫描件需开启 OCR」，空白 txt 与扩展名不规范的文件也被叫去开 OCR。后端 `_extract_text_with_ocr` 只对 `.pdf` 走 MinerU OCR，其余类型开 OCR 也无济于事。修正：`isLikelyScannedPdf(name, fileType)`（`file_type` 优先、扩展名兜底、仅 PDF 为真）+ `noTextHint`；列表标记与结束汇总按「扫描件 PDF / 其余（文件为空、只含图片或类型不支持提取文字）」两类提示，两类都保留「未提取到正文，AI 无法引用」。
7. **§二 小写化影响面复核**：全仓现查后端无按带点 / 大写比较知识库 `file_type` 的代码或测试（附件域 `attachment_service` 自行 `.lower()`、属另一张表）；前端无 `file_type === '.xxx'` 之类比较。
8. **通知样式**：`showUploadSummary` 里的 `h()` 在组件渲染上下文之外调用，生成的 VNode 不带本组件 scopeId，且通知挂在 `body` 下 ⇒ `<style scoped>` 规则永远匹配不到。已改内联样式并删除对应 scoped 规则；真浏览器 computed style 已核对。
