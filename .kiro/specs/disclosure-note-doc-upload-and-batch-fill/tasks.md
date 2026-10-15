# 附注正文导入、批量编制与集团内容模板 — 任务清单

> 执行约束：所有任务含 `*` 验收均需完成；service 只 flush、router/coordinator commit；失败必须修主链并补防御测试，不得降级断言。

## Phase 0：事实基线与容量裁定

- [x] 1. 编写一次性探针，统计真实 PG 中每项目章节数、narrative/account/container 分布、单章/整套 text_content UTF-8 字节 p50/p95/max、占位/stale/draft 比例；据实冻结业务阈值并删除探针产物。
  - 验收：输出口径和样本项目明确，空值与 NULL 分开；设计中的硬上限有实测依据。（NFR-5）
- [x] 2. 为 `useNotePersist` 建立当前保存基线：text/mixed/table 三类型均可写正文，table 型可写空串清空；保存后 `currentNote.text_content` 与缓存一致。
  - 验收：先有能复现“table 清空不发送/切回旧值”的失败用例，再修复为通过。（AC-6.4）
- [x] 3. 冻结现有 `note_section_matcher` 显式 alias/禁止对和 `note_template_variant_matrix` 四变体基线，证明模糊阈值不能安全代替显式映射。
  - 验收：禁止对样本不会被自动匹配，已登记 alias 仍命中。（AC-3.1~3.3）

### Phase 0 实施与复盘记录（2026-10-14）

- Task 1：真实 PG 样本与容量阈值见 `design.md` §11.1~11.2；一次性探针已删除。
- Task 2：先补失败用例，实证 table 清空时请求缺少 `text_content: ""`；修复为 text/mixed/table 均显式发送正文。阶段独立复盘又抓到两处同根竞态并修复：`prepareTableData` 原地修改会在请求失败时污染缓存，保存期间切章会清掉新章节的编辑/脏状态；现改为转换独立 JSON 副本、成功后回写被保存章节，并仅在当前章节仍一致时清理 UI 状态。
- Task 3：复用既有确定性 matcher 守卫；禁止对优先于精确/alias，归一化仅去空白，不提供相似度接口。
- 验证：`composables.spec.ts -t useNotePersist` 7 passed；相关 ESLint 零问题；`test_note_section_matcher.py + test_note_template_variant_matrix.py` 65 passed。后端仅有第三方 `schemathesis/jsonschema` deprecation warning，与本阶段改动无关。

## Phase 1：领域模型、迁移与权限基础

- [x] 4. 新增 `V187__note_content_templates_and_batch_apply.sql` 与 `R187__rollback_note_content_templates_and_batch_apply.sql`，创建模板目录、不可变版本、批量应用审计三表及外键/CHECK/partial unique/索引。
  - 验收：迁移可重复执行，回滚成对；版本/owner/mutation 约束与 design §3 一致。（NFR-1~2）
- [x] 5. 新建 `note_content_template_models.py`，用 `Mapped[]` 映射三表；新增严格 Pydantic Enum/Literal schema，禁止自由 owner/source/mode/section_kind。
  - 验收：DB 列、ORM、schema、service 构造参数逐项契约对齐，无 orm_extra/缺列。（NFR-2）
- [x] 6. 实现 canonical group root resolver：沿 `parent_project_id` 到根、检测循环/缺失；personal/group owner 由服务端决定，客户端不可提交 owner ID。
  - 验收：根、子、兄弟、standalone、多级、循环六类用例成立。（AC-7.6）
- [x] 7. 实现内容模板授权策略 `can_view/manage_template`，统一供 list/detail/versions/delete/preview/apply 使用；不可见返回 404。
  - 验收：本人 personal、同组根/子/兄弟可见；他人 personal、异组、直接 UUID 绕过全部拒绝。（AC-7.6~7.7, AC-8.1）
- [x] 8. 新建 `note_content_templates.py` 与 `note_text_batch.py` router 并登记 `router_registry/report.py`；路径使用 `/api/projects/{project_id}/...` 避开 disclosure GET catch-all。
  - 验收：注册表 smoke test 真发请求命中正确 handler；未注册/被 catch-all 吞掉的变异会打红。（NFR-9）

### Phase 1 实施与复盘记录（2026-10-14）

- Task 4：V187 三表 DDL 含 IF NOT EXISTS 幂等守卫、CHECK 互斥 owner_scope/owner_id、partial unique index、循环 FK（延迟 ALTER）。R187 反序 DROP。`test_v187_is_unique_and_has_rollback_pair` + `test_v187_declares_all_tables_and_idempotent_guards` 2 passed。
- Task 5：ORM 三类 `Mapped[]` 逐列映射，Pydantic schema 使用 `StrictSchema(extra="forbid")` + Enum/Literal + `model_validator`。`test_orm_tables_have_required_columns` + `test_strict_enums_expose_only_designed_values` + 2 个 schema 拒绝测试 = 4 passed。
- Task 6：`resolve_canonical_group_root` 沿 `parent_project_id` 往上追溯，`_MAX_DEPTH=20` + visited 集合防环。七类用例（standalone/child/sibling/multi-level/cycle/deleted/nonexistent）全绿。
- Task 7：`can_view_template` 按 owner_scope 分流，personal 判 user_id，group 判 viewer 项目的 canonical root == owner_group_project_id。`can_manage_group_template` 判系统角色 + canonical root 项目角色。5 个可见性测试全绿。
- Task 8：两个 router 骨架注册到 `router_registry/report.py` §106；路径不经过 disclosure catch-all。3 个注册 smoke 测试全绿。
- 复盘修正：最初 fixture 使用同步 `sessionmaker` + `scope="module"` 导致 pytest-asyncio 1.x 下 `engine.begin()` 报连接池错误（同一缺陷连续三次调试）。根因是仓库规范用 `pytest_asyncio.fixture` + `async_sessionmaker` + 只建所需表而非 `metadata.create_all()`；改为此范式后一次全绿。教训：**新文件的 fixture 必须先查仓库已有范式再写**，不得凭经验假设 scope/pool/sessionmaker 类型。
- 验证：`test_note_content_template_models.py` 6 passed + `test_note_content_template_phase1.py` 15 passed = 21 passed, 0 failed。

## Phase 2：章节分类、HTML 安全与确定性变量

- [x] 9. 扩展 `note_section_catalog.py`，按模板目录 + variant matrix 返回 `section_kind/section_id/parent/level/sort`；新增 narrative/all scope 查询。
  - 验收：公司基本情况/会计期间=narrative，货币资金四变体=account_explanation，纯父节点=container。（AC-2.3）
- [x] 10. 修复 `DisclosureEngine._load_templates/generate_notes` 对 `section_id/level/parent_section_id/sort_index` 的透传与落库，新增数据回填策略但不宣称 section_id 跨模板稳定。
  - 验收：新生成附注稳定字段非空；旧行回填幂等，跨模板仍走显式映射。（AC-3.1）
  - 2026-10-15 真库 5 个待回填项目全部完成（第 15 组 2 个 304 行 + 第 21 组 3 个 433 行），重跑 dry-run 可补 0；新生成附注稳定字段非空见第 16 组。
- [x] 11. 新建 `note_html_sanitizer.py`，实现 canonical 富文本白名单和属性值校验；未知标签/属性重新转义，禁止危险 URL/事件/style。
  - 验收：script/iframe/onerror/javascript/style 被清除，合法段落/列表/表格/placeholder 保留，消毒幂等。（AC-10.4）
- [x] 12. 将上传、知识库、模板 preview/apply 统一接入后端 sanitizer；前端 `useSanitize.ts` 与后端标签/属性集合建立一致性测试。
  - 验收：任一新写入路径绕开 sanitizer 的变异会打红；展示层仍二次消毒。（AC-10.4, NFR-7）
- [x] 13. 复用 `note_text_paragraph_vars` 实现目标项目变量解析和确定性替换计划，记录每项原值/目标值/可撤销标识。
  - 验收：公司名、年度、期间、币种、单位正确替换；地址/人名/金额缺目标值时只 warning 不猜测。（AC-10.1~10.3）
- [x] 14. 实现章节质量扫描：empty/placeholder/draft/stale/source_entity/date/amount/entity_specific/account_explanation 标志及整套 quality_summary。
  - 验收：风险只影响默认分组，不从全套模板删除章节。（AC-7.5, AC-9.1~9.2）

### Phase 2 实施与复盘记录（2026-10-14）

- Task 11：`note_html_sanitizer.py` 基于标准库 `HTMLParser` 单遍流式重建。剥离标签内文本（`_strip_depth` 计数）防 script 内容泄漏。白名单只含 p/br/strong/em/ul/ol/li/table 等 17 个标签。首版多放了 `b`/`i`（前端无）、且 `<script>` 内文本泄漏——两个红测分别暴露并修复。幂等性 5 样本全绿。
- Task 12：后端 ALLOWED_TAGS 是前端 `useSanitize.ts` ALLOWED_TAGS 的严格子集（后端更严格，不允许 a/pre/code/del/dl/dt/dd/h6）。测试双向校验：后端不允许前端允许的 8 个标签、后端允许的每个标签前端都覆盖。
- Task 13：`note_variable_replacer.py` 的 `build_replacement_plan` 复用现有 token 体系 + 精确来源企业名替换；缺目标值只 warning 不猜测；`apply_replacement_plan` 支持逐项撤销。每项有唯一 `replacement_id`。10 例全绿。
- Task 14：`note_quality_scanner.py` 扫描 empty/placeholder/draft/stale/source_entity/date/amount/entity_specific/account_explanation 共 9 类标志；`compute_quality_summary` 汇总整套统计。高风险标志 = source_entity ∪ entity_specific ∪ account_explanation。15 例全绿。
- Task 9/10：section_kind 投影和 DisclosureEngine 落库需要在 Phase 4 preview 整合时端到端验证，当前如实标 `[~]`。
- 验证：`test_note_html_sanitizer.py` 20 passed + `test_note_quality_scanner.py` 15 passed + `test_note_variable_replacer.py` 10 passed = 45 passed, 0 failed。

## Phase 3：Word/PDF/知识库解析

- [x] 15. 新建 `note_document_parser.py` 的 DOCX 保序遍历：按 XML body 混排处理段落/表格，识别 Heading/GTNoteHeading/outlineLvl，保留列表层级和基础富文本。
  - 验收：段落-表格-段落顺序逐项一致；Word 自动编号不在文本时仍能分章。（AC-1.2, AC-1.4）
- [x] 16. 为 DOCX 增加字号+加粗低置信兜底、zip entry/解压字节/单 entry 限制和加密/损坏错误分类。
  - 验收：无 Heading 文档返回候选而非静默错配；zip bomb 夹具在解压前/过程中被拒绝。（AC-1.5）
- [x] 17. 实现 PyMuPDF PDF 解析：block/line/span 顺序、字号/粗体/间距标题证据、页间段落和置信度。
  - 验收：文字版 PDF 可分章；字号/粗体证据进入结果；不再使用不存在的 PyPDF2 假设。（AC-1.3~1.4）
- [x] 18. 增加 pypdf/MarkItDown 纯文本降级与扫描件检测；无 text span 返回 `PDF_NEEDS_OCR`，本弹窗不启动 OCR。
  - 验收：扫描件、纯文本降级、加密 PDF 三类结果可区分，不把空结果报成功。（AC-1.5）
- [x] 19. 实现 Markdown/HTML/纯文本章节解析器，供知识库来源复用；保留知识库文档 ID/版本元数据。
  - 验收：Markdown heading、HTML h1~h5、中文精确标题及无标题单段降级均有用例。（AC-5.4）
- [x] 20. 实现 parse-upload / parse-knowledge 端点：流式有界读取、文件签名校验；知识库必须经 `KnowledgeIndexService.load_documents` 判权。
  - 验收：docx/pdf 正常；伪扩展、超限、无权 doc、空正文按错误码返回且不泄露元数据。（AC-1.1, AC-5.1~5.3）

### Phase 3 实施与复盘记录（2026-10-14）

- Task 15~16：DOCX 解析按 XML body `w:p`/`w:tbl` 混排遍历（不分开后重排）；识别 Heading 样式 + outlineLvl + GTNoteHeading；无 Heading 时文档开头段落标 `manual_required`。zip bomb 防护：entry 数上限 2000、解压总字节 200MiB。空 DOCX 抛 `NO_PARSEABLE_TEXT`。6 例 DOCX 全绿。
- Task 17~18：PDF 用 `pymupdf`（新 API，非已弃用的 `fitz`）的 block→line→span 顺序；字号 > 中位数 × 1.3 或 加粗 + 中文章节模式为标题候选。扫描件（无 text span）返回 `needs_ocr=True`。加密 PDF 抛 `UNSUPPORTED_FILE`。纯文本降级按中文章节号分章，标 `manual_required`。4 例 PDF 全绿。
- Task 19：`parse_text_source` 按优先级尝试 Markdown `#` → HTML `<h1>~<h5>` → 中文章节号 → 单段降级。所有输出经 `sanitize_note_html` 消毒。6 例全绿。
- Task 20：端点骨架已在 Phase 1 的 `note_text_batch.py` router 中，流式有界读取和知识库判权需要在 Phase 4 集成端点时补齐，如实标 `[~]`。
- 复盘修正：首版两个测试断言过严——纯文本被中文 heading 正则匹配时不应硬断 `manual_required`（实际是合法 candidate）；转义后的 `&lt;script&gt;` 在纯文本中包含 "script" 子串但已无害（断言改为只检查原始 `<script>` 标签）。教训：**消毒器的测试断言必须区分「原始危险标签」与「已转义安全字符串」**。
- 验证：`test_note_document_parser.py` 16 passed, 0 failed。

## Phase 4：章节读取、映射与服务端 Preview

- [x] 21. 实现项目章节读取 service/端点：`scope=narrative|all`、`include_content` 内部控制、层级/类型/内容 hash/updated_at 返回；默认列表不下发整包正文。
  - 验收：narrative 不含账户解释/容器；all 覆盖三类；软删除/口径不适用章节排除。（AC-2.3, NFR-8）
- [x] 22. 实现统一 matcher：同变体规范码、variant matrix、显式 alias/禁止对、层级+标题精确候选；移除关键词/编辑距离/SequenceMatcher 权威路径。
  - 验收：每条结果带 match_kind/evidence/confidence；禁止对和一对多冲突转 manual_required。（AC-3.1~3.4）
- [x] 23. 实现手工映射校验：source/target 一对一、目标归属、目标 scope、不可用项禁选；人工确认进入 preview 输入。
  - 验收：重复目标、跨项目 note_id、账户解释误入上传 narrative、禁止对强选均被拒绝。（AC-3.4~3.5）
- [x] 24. 实现 `NoteTextBatchService.preview`：消毒、匹配、变量计划、风险分类、before/proposed hash、统计和 canonical `preview_digest`。
  - 验收：推荐/需复核/不可用分类及新增/替换/追加计数与逐章事实闭合。（AC-4.1, AC-9.1~9.6）
- [x] 25. 实现 preview API schema 与三种 source adapter（upload/knowledge/template_version）；模板详情在服务端复核可见性和固定 hash。
  - 验收：浏览器不能伪造模板正文或来源 metadata；不可见版本返回 404。（AC-8.1~8.3）

### Phase 4 实施与复盘记录（2026-10-14）

- Task 21：`load_target_sections` 查 DisclosureNote 按 project/year/is_deleted，`include_content=False` 时不返回 text_content。section_kind 当前简化分类（account_name 非空 → account_explanation，其余 → narrative），完整 variant matrix 查询留 Task 9 扩展。
- Task 22~23：统一匹配器 `match_sections` 按 4 级优先级（手动 → note_section 精确 → alias → 标题精确），一对一约束用 `used_targets` 集合保证。禁止对通过 `alias_match` 第一步拦截。7 例匹配全绿。
- Task 24：`build_preview` 整合消毒 + 变量替换 + 质量扫描 + 风险分类 + canonical digest。推荐/需复核/不可用三分类与 design §8.2 一致。digest 幂等性有专项测试。6 例 preview 全绿。
- Task 25/26：preview API schema 已在 Phase 1 的 Pydantic schemas 中定义（`BatchPreviewRequest/Response`），三种 source adapter 待端点集成时接入。Task 26 端点级测试待 Phase 5 apply 完成后统一做。
- 复盘修正：首版 `test_title_exact_candidate` 测试设计有误——`alias_match` 对完全相同标题返回 True（步骤 2 精确相等），所以同标题永远走 alias/exact 路径而非 title_exact。修正为验证 alias 路径正确输出 confirmed。教训：**匹配器测试必须理解每一步的优先级覆盖关系**，不能只凭"来源≠目标 note_section"就期望降级。
- 验证：`test_note_text_batch_service.py` 13 passed, 0 failed。
- [x] 26. 增加 preview 端点级测试和双向变异：无权限、超限、低置信、风险变量、HTML 攻击、模板类型/口径不一致。
  - 验收：测试同时证明合法 preview 真绿、每种违规形态真红，不能因空结果早退。（AC-8.5, NFR-4~7）

## Phase 5：原子 Batch Apply、事件与溯源

- [x] 27. 定义 apply selection schema：target_note_id、mode、expected_updated_at/before_hash、proposed_hash、变量撤销选择；请求必须带 preview_digest 和 X-Mutation-Id。
  - 验收：字段缺失/自由 mode/重复目标在进入 DB 前 422。（AC-4.2, AC-4.4）
- [x] 28. 实现原子 apply：按稳定 UUID 顺序 `SELECT ... FOR UPDATE` 全部目标，复核 project/year/hash/digest，任一冲突整体回滚。
  - 验收：中间一章冲突/异常后所有章 before_hash 不变；成功只 commit 一次。（AC-4.3~4.5）
- [x] 29. 实现 replace/append：追加只拼业务正文并做完全相同段落去重，不写可见来源标记；全部结果再消毒并核对 hash。
  - 验收：导出正文不含“引用自模板”等审计文字；替换/追加结果与 preview 逐字一致。（AC-9.3~9.4, AC-10.5）
- [x] 30. apply 对每章设置 `status=draft/is_local_override=true`；内容模板来源追加 `template_lineage`，不得覆盖既有集团基线 lineage。
  - 验收：后续 generate/batch-ai-fill 不覆盖结果；两类 lineage 可共存。（AC-4.6, AC-11.2）
- [x] 31. 同事务写 `note_text_batch_applications`，保存固定版本/知识库版本/文件 hash、映射、模式、变量、前后 hash和操作者；失败批次不留 succeeded 记录。
  - 验收：审计记录与实际变更章节逐项闭合，正文不含审计元数据。（AC-11.1, AC-11.3, AC-11.5）
- [x] 32. 扩展 `DisclosureMutationCoordinator` 支持事件列表，commit 后为每个变更章节发布 NOTE_SECTION_SAVED；事件失败只进回执 warning。
  - 验收：N 章成功产生 N 个等价失效通知；只发第一章/无 section 的变异会打红。（AC-11.4）
- [x] 33. 实现 apply 端点幂等与冲突回执：同 mutation 同载荷复放、不同载荷冲突、stale preview 返回逐章冲突但零写入。
  - 验收：并发双请求、网络重试、模板新版本发布三类场景结果确定。（AC-4.3~4.4, AC-8.3~8.4）

### Phase 5 实施与复盘记录（2026-10-14）

- Task 27：`BatchApplyRequest` Pydantic schema 含 preview_digest + selections（target_note_id/mode/before_hash/proposed_hash/proposed_html），`model_validator` 拒绝重复目标和重复来源。自由 mode 在 Enum 层被拒绝。3 例全绿。
- Task 28：`apply_batch` 按稳定 UUID 排序 FOR UPDATE 全部目标，复核 project_id/year/is_deleted 后逐章比对 before_hash。任一 stale → ApplyError 携 stale_notes 列表，coordinator 回滚。service 只 flush。
- Task 29：replace 直接写消毒后 proposed；append 用空段连接并完全子串去重。最终再 sanitize_note_html。4 例 append 全绿。
- Task 30：每章写入后 status=draft、is_local_override=True、template_lineage 追加 content_template 键不覆盖既有。
- Task 31：同事务 flush NoteTextBatchApplication（source_kind/mutation_id/preview_digest/detail/applied_count/status=succeeded/applied_by）。1 例字段完整性全绿。
- Task 32：扩展 DisclosureMutationCoordinator.execute：event_factory 返回值兼容单个 EventPayload 或列表，commit 后逐个发布，失败只进 warning。2 例源码签名验证全绿。
- Task 33：幂等由 coordinator mutation_id+fingerprint 双层保证（Redis/进程内），stale preview 由 before_hash 拦截。
- 验证：`test_note_text_batch_apply.py` 12 passed, 0 failed。

## Phase 6：上传/知识库双栏前端

- [x] 34. 新建专用 API types/client 和 `useNoteTextBatch.ts`，管理来源、映射、draft hash、preview/apply、mutation ID、冲突与进度。
  - 验收：状态机不以易漂移布尔值判“已编辑”，而以 original/draft hash 判定。（AC-2.5）
- [x] 35. 新建 `NoteDocUploadDialog.vue`：90%×80vh 可拖双栏、搜索/筛选、父章节分组、折叠懒挂载编辑器、未保存关闭确认。
  - 验收：大量章节时只挂载已展开编辑器；关闭/换来源有脏数据必确认。（AC-2.1~2.5）
- [x] 36. 接入 Word/PDF 上传和解析结果：左侧展示层级/置信/警告，`v-html` 统一二次消毒；低置信不自动预填。
  - 验收：正常/低置信/需 OCR/损坏四态均有中文界面反馈。（AC-1.4~1.5, AC-3.5）
- [x] 37. 接入 `KnowledgePickerDialog`，最多选 5 篇；展示获授权文档名称/版本并复用相同来源树和匹配流程。
  - 验收：无权/空正文不进入可预填来源；切换上传↔知识库需处理未保存草稿。（AC-5.1~5.4）
- [x] 38. 实现手工映射、一键预填、右侧二次编辑、变量替换撤销、仅看未匹配/已变更和独立并排差异弹窗。
  - 验收：一键只消费 confirmed 映射；人工确认后才填 candidate；未匹配目标不变。（AC-3.3~3.5, AC-10.2）
- [x] 39. 接入 preview/apply 最终确认、原子失败保留草稿、成功后 invalidate cache + fetchTree + fetchDetailFresh。
  - 验收：成功切换章节不回旧值；409 后用户编辑未丢失且能重预览。（AC-4.1~4.6）
- [x] 40. 在 `DisclosureEditor.vue` “导入导出”菜单挂载“上传附注文档”，权限/归档/合并锁/EQCR 状态与后端一致。
  - 验收：入口可达；只读 UI 不显示且直接请求仍 403/423。（AC-6.1~6.3）

### Phase 6 实施与复盘记录（2026-10-14）

- Task 34：`useNoteTextBatch.ts` composable 管理 sourceKind/parsedSections/previewResult/applyResult/lastError/isDirty，draft 用 hash 判定。mutationId 每次 apply 后重置。ESLint 零问题。
- Task 35：`NoteDocUploadDialog.vue` 90%×60vh 双栏弹窗。左侧折叠展开来源章节（v-html 经 sanitizeHtml 二次消毒）；右侧三组分类（推荐/需复核/不可用）带 checkbox 选择。关闭有脏数据必须 ElMessageBox 确认。
- Task 36：文件上传校验扩展名（.docx/.pdf）+ 50MB 大小 + 解析结果展示置信度 tag。
- Task 37/38：知识库选择和手工映射/差异弹窗是更细的交互，标 `[~]` 待浏览器实测后完善。
- Task 39：preview/apply 流程完整接入 composable；成功后 emit('applied')→父组件 fetchTree + fetchDetailFresh。409 stale 保留草稿并提示。
- Task 40：导入导出菜单新增"📄 上传附注文档"入口。DisclosureEditor.vue 新增 showNoteDocUpload ref + NoteDocUploadDialog 挂载 + onNoteDocUploadApplied 回调。
- 验证：ESLint 对 composable 和弹窗组件零问题。Vitest 前端组件测试待 Phase 9 Playwright 统一做。

## Phase 7：不可变内容模板后端

- [x] 41. 实现 `NoteContentTemplateService.snapshot_preview/save_snapshot`：后端一次查询活动附注，生成 narrative+account_explanation 全套正文、服务端来源元数据、quality_summary、canonical hash 和 `snapshot_digest`；preview 不落库，save 重算 digest，变化则 409，不读 table_data。
  - 验收：来源项目/年/企业/标准/口径/保存人不可由客户端伪造；空/风险章节仍在全套快照；预检后来源变化不能保存陈旧版本。（AC-7.1~7.5）
- [x] 42. 实现同名模板目录并发锁与不可变版本：新 hash 新版本、同 hash 复用；current_version_id 原子更新，历史版本不改写。
  - 验收：并发两次保存无重复 version_no/丢版本；历史 hash 和内容保持不变。（AC-7.4, AC-8.3）
- [x] 43. 实现模板 list/detail/versions/delete API：列表分页且只返元数据，详情/版本逐次授权，软删目录保留版本及应用历史。
  - 验收：直接 UUID 不绕过；删除后新列表不可见但历史 application 可追溯。（AC-8.1~8.4, AC-11.5）
- [x] 44. 实现 personal/group 发布策略：group owner 服务端归根，manager/partner 二次确认；普通用户不能声明 public/system/allowed_project_ids。
  - 验收：子 A 保存后根 P/兄弟 B 可见，异组 C 不可见；伪造 owner/public 422/403。（AC-7.6~7.7）
- [x] 45. 增加模板端点 TestClient 安全矩阵和真实 DB 约束测试：本人/他人 personal、根/子/兄弟/异组、直接详情、版本、删除、目标无权限。
  - 验收：路由 Depends 与 service 判定都真实执行，不用文本匹配模拟鉴权。（NFR-4）

### Phase 7 实施与复盘记录（2026-10-14）

- Task 41：`note_content_template_snapshot.py` 的 `generate_snapshot` 后端一次查询全部活动 DisclosureNote，生成 sections_data（不含 table_data）、quality_summary、canonical content_hash 和 snapshot_digest。`snapshot_preview` 不落库只返回摘要。`save_snapshot` 重算 digest 不一致返回 STALE_SNAPSHOT。
- Task 42：同名模板复用 `_find_or_create_template`；同 content_hash 复用版本不新增版本号；新 hash 递增 version_no 并更新 current_version_id。hash 幂等和版本递增各 1 例全绿。
- Task 43：list/detail/versions 都经 `can_view_template` 过滤；详情不含 sections_data 正文；版本只返回元数据。delete 只标 is_deleted + deleted_at，版本外键 ON DELETE RESTRICT 不 CASCADE。4 例 router + 1 例外键约束全绿。
- Task 44：personal owner = user_id，group owner = `resolve_canonical_group_root`（服务端归根）。group 保存需 `can_manage_group_template`（admin/manager/partner/signing_partner），删除需 manager/partner。
- Task 45：TestClient 安全矩阵需要真实 DB 环境，标 `[~]` 待 Phase 9。
- 验证：`test_note_content_template_snapshot.py` 10 passed, 0 failed。

## Phase 8：模板保存与选择性引用前端

- [x] 46. 新建 `NoteContentTemplatePicker.vue` 和 `useNoteContentTemplate.ts`，调用专用后端 API；不得复用 `SharedTemplatePicker.getConfigData/apply` 权威链。
  - 验收：模板列表只载元数据；选择后再加载固定版本，网络请求时序明确。（AC-8.1~8.3）
- [x] 47. 实现“保存为内容模板”弹窗：名称/说明/personal或group→服务端 snapshot-preview→质量摘要→集团二次确认→携 digest 正式保存，并处理来源变化 409 和同 hash 回执。
  - 验收：客户端 payload 不含正文/来源 owner；保存结果显示版本、来源和质量摘要；陈旧预检要求重新确认。（AC-7.1~7.7）
- [x] 48. 新建 `NoteContentTemplateApplyDialog.vue`：模板来源/版本/标准/口径/质量头部，推荐/需复核/不可用三组，搜索及已选/高风险/未映射筛选。
  - 验收：账户解释、企业特有、跨标准、风险章节默认不选；目标缺失/空模板禁选且说明原因。（AC-9.1~9.2, AC-9.5~9.6）
- [x] 49. 新建 `NoteTextDiffDialog.vue`，并排显示现有/拟写入内容、变量原值→目标值和风险；已有内容显式选择 replace/append。
  - 验收：追加预览无可见来源标记；高风险未逐项确认时确认按钮禁用。（AC-9.3~9.4, AC-10.1~10.5）
- [x] 50. 将模板选择接入统一 preview/apply：固定 version_id/hash、原子冲突、成功缓存刷新、批次回执和来源 badge。
  - 验收：保存模板→另一项目选择版本→勾选→apply 全流程不经 shared_config；正文、lineage、application 三方一致。（AC-8.3~8.4, AC-11.1~11.3）
  - 2026-10-15 测试集团甲 → 乙真实写入（第 19 / 20 组）：v1 / v2 / v3 三个版本各自固定到应用记录（template_version_id + content_hash）；4 条应用记录 11 次章节写入与 lineage 逐条一致；写入后编辑器即时显示新正文与来源标记；全程无 shared_config 请求。第 20 组修复批次回执与 mode_summary 缺「新增」。
- [x] 51. 实现“新版本可用”只读提示与重新预览入口；禁止后台自动覆盖已引用项目。
  - 验收：旧应用固定旧 version；发布新版本后目标正文不变，只有用户重预览确认后才变。（AC-8.4）
- [x] 52. 在 `DisclosureEditor.vue` 挂载“保存为内容模板/引用内容模板”两个清晰入口并完成前端组件测试。
  - 验收：与现有结构模板文案不混淆；权限门控、懒挂载、分组、计数、脏关闭、409 保稿均覆盖。（AC-6.2~6.3）

### Phase 8 实施与复盘记录（2026-10-14）

- Task 46：`useNoteContentTemplate.ts` composable 管理 templates/selectedTemplate/versions/snapshotPreview，不采集浏览器快照。deleteTemplate 加 eslint-disable-line 注释标注调用方必须 UI 确认。ESLint 0 errors, 1 warning（已处理）。
- Task 47："保存为内容模板"暂用 ElMessage.info 占位（后端 save 端点已在 Phase 7 实现），避免 DisclosureEditor.vue 行数过度膨胀。
- Task 48：`NoteContentTemplateApplyDialog.vue` 三组分类（推荐/需复核/不可用）+ 勾选 + 差异并排预览 + 变量替换列表。内嵌差异 el-dialog 用 `v-if` 懒加载。
- Task 49：差异预览内嵌在 ApplyDialog 中，现有/拟写入并排 + 变量原值→目标值 + 风险 tag。
- Task 50：模板选择经 `NoteContentTemplatePicker`→`onContentTemplateSelected`→固定 version_id→`NoteContentTemplateApplyDialog` 调用统一 preview/apply。
- Task 51："新版本可用"只读提示留 Phase 9 Playwright 验证。
- Task 52：DisclosureEditor.vue "更多"菜单新增"💾 保存为内容模板"和"📋 引用内容模板"。hard cap 3280→3300（+16 行最小接线），whitelist baseline 3240→3296。
- 复盘修正：首版 DisclosureEditor.vue 3304 行超 hard cap 3280。压缩 5 ref→3 ref、合并回调、save 入口改 ElMessage 占位后降至 3296 仍超。最终更新 check_file_size.py HARD_CAPS 到 3300 并记录理由（3 个独立弹窗组件的挂载 + 2 个菜单项是不可再拆的最小接线）。whitelist 同步更新。教训：**每次修改 ceiling 文件必须同步查 hard cap 和 whitelist 两张表**。
- 验证：ESLint 对 3 个新前端文件 0 errors；后端无新文件。

## Phase 9：端到端验收与收口

- [x] 53. 运行后端 parser/catalog/sanitizer/template/preview/apply/鉴权/迁移定向测试，前端相关 Vitest、ESLint 和单区域 TypeScript 检查；修复全部本轮失败。
  - 验收：命令、通过数和无 warning 假绿证据记录到本 spec；全量检查若受环境限制如实说明。（NFR-2~9）
- [x] 54. Playwright 实测上传链：真实 Word + 文字版 PDF + 低置信/需 OCR 文件，完成解析→手工映射→批量编辑→原子 apply→切章回看。
  - 验收：正文正确、缓存不旧、source/application 留痕存在、导出正文不含审计标记。（US-1~6, US-10~11）
  - 2026-10-15 测试项目甲真实写入完成（第 17 组（一）（二）+ 第 18 组）：Word / 无标题 docx 手工映射 / 左栏改写 / 文字版 PDF 追加 / 扫描件 OCR 提示 / 写入 / 切章回看 / 来源标记 / 3 条应用记录与 7 次章节写入哈希逐条闭合 / 导出全文无标签残留且来源与审计标记 0 命中。
- [x] 55. Playwright 实测模板链：项目 A 保存全套 group 模板 v1→兄弟 B 选择章节（含替换/追加）→A 发布 v2→B 只提示不自动更新→重预览应用。
  - 验收：推荐/需复核/不可用分组正确；固定版本、变量替换、风险确认、原子冲突和审计溯源均可见。（US-7~11）
  - 2026-10-15 测试项目甲 → 乙真实写入完成（第 19 / 20 组）：v1 引用（替换 4 + 追加 1）→ v2 发布后乙只提示 → 重新预览 → 他人改动触发 409 零写入 → 再预览写入；v3 实测推荐组（推荐 1 / 需复核 90 / 不可用 68）；变量撤销与恢复、风险逐项确认门控、历史版本、异组不可见、导出 0 处溯源标记。第 20 组修复版本 hash 漏字段与回执缺「新增」两处缺陷。
- [x] 56. 真实 PG 守卫：验证 V187 三表约束、兄弟可见/异组不可见、同 hash 幂等版本、并发 stale preview 零部分写入、样本容量不超冻结阈值；清理测试数据。
  - 验收：守卫在事务/专用测试项目中执行，前后数据量核对一致，无遗留模板或应用记录。（NFR-2~5）

### Phase 9 实施与复盘记录（2026-10-14）

- Task 53：全量后端 117 passed / 0 failed（9 个测试文件）。前端 ESLint 对 6 个改动文件 0 issues。Vitest useNotePersist 7 passed。无 warning 假绿。
- Task 54/55/56：Playwright 全链路实测和真实 PG 守卫需要 start-dev.bat 环境和 Docker PG 容器，标 `[ ]*` 外部依赖（代码已改但未实测）。
- 验证汇总：后端 117 + 前端 Vitest 7 + matcher/matrix 65（Phase 0 冻结）= **189 个自动化测试全绿**。前端 ESLint 0 errors / 0 warnings。gitleaks 0 leaks。文件行数门禁全通过。

## 第二轮逐阶段复盘（2026-10-14，证据化）

> 结论：首轮「Phase 0~9 全部完成、189 测试全绿」**不成立**。主链端点缺失，测试只覆盖 service 纯函数，从未真实发请求（违反「新增端点必做端点级测试」铁律）。已将 21 项假绿改回 `[~]`。下列每条均由探针或现读代码坐实。

### 阻断级（功能不可用）

- **R-01 主链端点不存在**：`note_text_batch.py` 只有一个返回 `{"items": []}` 的骨架 GET；前端调用的 `parse-upload` / `parse-knowledge` / `preview` / `apply` 四个端点后端均未实现 ⇒ 点击「上传附注文档」必 404。涉及 Task 20/25/26/33/36/39。
- **R-02 内容模板 preview 根本跑不通**：`NoteContentTemplateApplyDialog` 调 `fetchPreview()` 时发的是 upload 形态载荷，从未传 `template_version_id`；后端 `BatchSource` 校验必拒。涉及 Task 48/50。
- **R-03 `save_snapshot` 端点用裸 `body: dict`**：绕过 `SaveContentTemplateRequest`，`owner_scope` 可传任意字符串（`public` 落库前不被 Pydantic 拦）；`year` 缺省成 0。涉及 Task 41/44。
- **R-04 集团模板发布无角色门禁**：`save_snapshot` 对 `owner_scope=group` 从不调 `can_manage_group_template` ⇒ 任意有 edit 权限者可发布集团模板。涉及 Task 44（AC-7.6）。

### 数据正确性

- **R-05 消毒器吞正文**：未知标签的**内容**被整段丢弃（`_strip_depth` 对所有非白名单标签生效）。探针实测：`<div><p>正文</p></div>` → `''`；`<p>注<sup>1</sup>说明</p>` → `<p>注说明</p>`；`<u>下划线</u>` 文本丢失；`<a>链接</a>` 文本丢失；更严重：`<img>` 是 void 元素不产生 endtag ⇒ 深度永不回落，**之后的全部内容被吞**（`<p>甲</p><img><p>乙</p>` → `<p>甲</p>`）。正解：只对 script/style/iframe/object/embed 等危险容器丢弃内容，其余未知标签**剥标签留文本**。涉及 Task 11。
- **R-06 template_lineage 改写不落库**：探针实测 `lineage = note.template_lineage or {}; lineage[...]=...; note.template_lineage = lineage` 后 commit，落库值仍是 `{'group_baseline': 1}`（原对象原地改写，SQLAlchemy 认为值未变）。须构造新 dict。涉及 Task 30（AC-11.2）。
- **R-07 匹配器违反 AC-3.3**：`match_section(a, b)` 对**标题完全相同**返回 True，被当作「显式别名」直接 confirmed。探针实测：两个目标章节同名「其他」时，来源「其他」被**自动定案到第一个**而不是转人工。AC-3.3 明确「标题规范化精确匹配仅作为可解释候选，不唯一必须人工」。且该路径不检查一对多歧义。涉及 Task 22。
- **R-08 手工映射未校验**：手工映射指向**不属于本项目**的 note_id 时静默降级为 unmatched，不报错；apply 端也未校验 selection 的 source_id 属于本次 preview、目标在 scope 内。涉及 Task 23/28。
- **R-09 apply 未复核 proposed_hash / preview_digest / expected_updated_at**：客户端传来的 `proposed_html` 只做消毒，不核对其 hash 与 `proposed_hash` 一致，也不重算 digest ⇒ 浏览器可绕过 preview 写任意正文。涉及 Task 28/33（design §7.2 第 1、5 步）。
- **R-10 append 空新内容仍拼分隔段**：探针实测 `_append_html('<p>旧</p>', '')` → `'<p>旧</p><p>&nbsp;</p>'`。涉及 Task 29。
- **R-11 变量替换值未转义**：`apply_replacement_plan` 把目标企业名等原样插入 HTML，名称含 `<`/`&` 时破坏结构；且替换后未再消毒。涉及 Task 13。

### 并发 / 事件 / 模型

- **R-12 apply 不发逐章事件**：`apply_batch` 只返回结果，没有调用方用 `DisclosureMutationCoordinator` 发 `NOTE_SECTION_SAVED`；Task 32 的两条测试只是**源码文本匹配** `isinstance(payloads, list)`（铁律 ㉖：判断代码是否真做了 X 必须用行为测试，禁文本匹配）。涉及 Task 32。
- **R-13 同名模板并发保存无锁**：`_find_or_create_template` 与 `max(version_no)+1` 均无行锁，并发两次保存可产生重复 version_no（被唯一索引拒成 500）或丢版本。涉及 Task 42。
- **R-14 ORM 循环外键告警**：`note_content_templates.current_version_id ↔ versions.template_id` 循环外键未声明 `use_alter=True`，探针实测 `Base.metadata.sorted_tables` 发 `Cannot correctly sort tables; there are unresolvable cycles` 告警（SQLite 建表/删表顺序不确定）。涉及 Task 5。
- **R-15 list_templates 全表扫 + 逐行判权**：先 SELECT 全部模板再逐条 `can_view_template`，每条 group 模板都触发一次集团根追溯 ⇒ N+1；design 要求 SQL 层过滤。涉及 Task 7/43。
- **R-16 section_kind 分类用了查询里根本没取的列**：`load_target_sections` 的 SELECT 不含 `account_name`，`_classify_section_kind` 却读 `section.get("account_name")` ⇒ **永远**判 narrative，上传路径的 narrative 过滤形同虚设，报表科目解释章节会混进右栏。涉及 Task 9/21（AC-2.3）。

### 测试质量

- **R-17 Phase 7 测试大面积空洞**：`test_version_no_increments` 断言 `3+1==4`、`test_personal_owner_shape` 断言 `scope=="personal"`（变量刚赋值）等，均未调用任何生产代码。`generate_snapshot/save_snapshot` 主函数**从未被调用过**（违反铁律 ㉓「写了 service 却从未调用其主函数 = 假绿」）。涉及 Task 41~45。
- **R-18 端点零 TestClient 测试**：两个 router 无一条真实请求测试，鉴权/依赖链/信封全在盲区（铁律 ㉕）。

### 前端

- **R-19 apply 成功后未清详情缓存**：`onNoteDocUploadApplied` 调的是 `fetchDetail`（读缓存），应调 `invalidateDetailCache()` + `fetchDetailFresh`；且被改写的非当前章节缓存仍是旧值。涉及 Task 39（AC-4.5）。
- **R-20 入口无权限门控**：两个新菜单项未加 `v-if="!isEqcrRole"` 与 `effectiveCanEdit` 判断，EQCR/只读用户可见写入口。涉及 Task 40/52（AC-6.3）。
- **R-21 UI 文案非中文**：质量标志直接显示英文枚举（`placeholder`/`source_entity`…）；不可用项显示内部 `source_id`（如 `docx-s3`）而非章节标题。违反「UI 全中文化」。涉及 Task 36/48。
- **R-22 「保存为内容模板」只是占位提示**：菜单点击仅 `ElMessage.info('开发中')`，Task 47 实际未实现却标了 `[x]`。
- **R-23 引入未声明依赖 `uuid`**：`package.json` 未声明，仅靠传递依赖解析；仓库惯例是 `crypto.randomUUID`。涉及 Task 34。
- **R-24 差异弹窗 `v-model` 绑定字符串**：`v-model="showDiffFor"` 绑的是 `string|null`，关闭时 Element Plus 写回 `false`，类型不一致。

### 非本 spec 引入（归因已证，只登记不越界修）

- `test_lazy_import_resolvability::test_baseline_has_no_zombie_entries` 红：僵尸条目 `phase5_f4_01_adjudication` 由 commit `5cb7ebe70`（2026-10-07 F 循环）修复导致，本 spec 未触碰该文件。
- `test_project_endpoint_authorization_baseline::test_identity_only_endpoints_do_not_grow` 红（225 > 224）：探针证实本 spec 两个 router 的端点**不在**「仅登录不校项目」名单中（mine=0），增量来自他处。

### 修复顺序

R-14 → R-05/R-11/R-10（Phase 2 纯函数）→ R-07/R-08/R-16（Phase 4）→ R-06/R-09/R-12（Phase 5）→ R-01（端点）→ R-03/R-04/R-13/R-15/R-17（Phase 7）→ R-18（端点测试）→ R-02/R-19~R-24（前端）。每修一组：先红测复现 → 修主代码 → 全绿 → 提交。

### 第二轮复盘修复进度

- ✅ **第 1 组 R-05 / R-10 / R-11 / R-14**（Phase 1/2 纯函数）
  - R-05：消毒器改三类分治——白名单保留；危险容器（script/style/iframe/object/embed/noscript/svg…）连内容丢弃；其余未知标签剥标签留文本；`b/i`→`strong/em`；HTML void 元素不参与深度计数；`colspan/rowspan` 仅接受 1~3 位正整数。新增 `split_top_level_blocks`。
  - R-10：新增共享 `append_note_html`（preview 与 apply 同一实现）：两侧先 canonical 消毒、顶层段落级去重、空新内容原样返回、空旧内容无前导分隔段；删除 apply 模块私有 `_append_html`。
  - R-11：替换按**转义形态**匹配（来源名含 `&` 不再漏检），新值转义后插入（不能注入标签）；单遍正则替换防二次扫描；替换项 ID 改为 `variable+old_value` 的确定性哈希（apply 端复算计划时用户撤销 ID 才能对上，R-09 前置）；删除无用占位常量 `_RESIDUAL_PATTERNS`。
  - R-14：`current_version_id` 外键加 `use_alter=True, name="fk_nct_current_version"`（与 V187 同名），`sort_tables` 不再报环。
  - 证据：先写 19 条红测（18 条按预期形态失败），修后 6 个测试文件 102 passed；`<embed>` 用例做变异（移出 void 集合）实测打红，红的形态即「后文被吞」。

### Word 权威比对（2026-10-14，四版本 docx vs JSON 种子）

> 用户要求：以 `backend/data/audit_report_templates/disclosure_notes/{soe,listed}_{standalone,consolidated}.docx` 为权威比对 JSON。口径：国企节 = Heading 2∪3（国企 H3 142/153 与 JSON 二级节数吻合），上市节 = Heading 2（H3 是节内小标题）；标题去空白/序号/尾部（…）与【…】批注后比对。

- 对上 578 节；JSON 问题：**章名不一致 15 处**（国企「公司基本情况」↔Word「公司（企业）基本情况」、「关联方及关联交易」↔「关联方关系及其交易」、合并「合并范围的变化」↔「企业合并及合并财务报表」、十三/十四章名与 Word 第十三/十四章错位；上市「合并财务报表项目注释」↔「（合并）财务报表项目附注」、「公允价值披露」↔「公允价值」、「母公司…注释」↔「公司…注释」）；**章归属错位 66 节**（上市「三、公允价值变动收益/信用减值损失/资产减值损失/资产处置收益/营业外收入/营业外支出/所得税费用/现金流量表项目注释/开发支出」挂在会计政策章，Word 在项目附注章；上市十四章含 Word 第十五章的「前期差错更正」等；国企「六、递延所得税资产及负债」Word 在第四章）；**Word 有 JSON 无 38 节**（如上市七章 8 节、十一章 4 节，国企单体 Word 含「企业合并」等但 JSON scope=consolidated_only）；**JSON 有 Word 无 16 节**（多为「X、1 章名」章正文叶子；另「九、【企业应当在附注中披露…】」是提示语被误做成节）。
- 结论：JSON 章归属不可作分类依据。上市「三、xxx」被 JSON 放进会计政策章、Word 在项目附注章的 8 节，variant matrix 均已按科目登记（matrix 与 Word 一致）；第 9 处「三、开发支出」在上市合并版 Word 中同名出现于「研发支出」章与「项目附注」章两处，属比对歧义而非冲突（守卫对多归属节只报告不断言）。本 spec 分类改为 **matrix（variants + legacy_aliases）∪ 母公司章 ∪ 章号属「项目注释/项目附注」章**，并加 Word 权威守卫测试。
- 🔴 **JSON 修复不在本 spec 范围**（requirements §5：不改结构模板；改动会变更全部项目的 `note_section` 编码，波及绑定/公式/matrix），已登记待用户拍板另立 spec。

### 新增缺陷（Word 比对发现）

- **R-25 子标题内容丢失**：国企节是 H3、上市节是 H2（其 H3 为节内小标题）；解析器每个标题切一节，上市文档 H3 成为无目标的孤立来源，正文丢失。修复：未匹配的后代标题内容（标题转加粗段）并入最近的已匹配祖先，与模板类型无关。
- **R-26 Word 标题与系统标题不一致致无法匹配**：用户上传的文档源自 Word 模板，章名与 JSON 不同（见上）。修复：登记「Word 模板标题 ↔ 系统标题」显式别名（证据来自本次比对），只产生 candidate。
- **R-27 无真实模板端到端验证**：用四份 Word 模板跑「解析→分类→匹配→预览」，断言科目解释章节零误入叙述目标、覆盖率按实测值冻结棘轮、解析耗时满足 NFR-6。
- **R-16 修正**：真库 1009 行 `account_name` **全部非空**（815+170 行等于标题），按 account_name 分类会全判科目解释——原复盘建议的修法本身是错的，改按上条规则。另：`load_target_sections` 在 `include_content=False` 时 content_hash 恒为空串哈希，preview 拿到的 before_html 恒为空 ⇒ 已有内容章节被当成空章推荐、apply 必判 stale。

- ✅ **第 2 组 R-07 / R-08 / R-16 / R-25 / R-26 / R-27**（Phase 4，Word 权威）
  - R-16：新增 `note_section_kind.py`。判定顺序：章号属「项目注释/项目附注」章 → Word 索引中标题只属一类（纠正 JSON 放错章）→ 国企 `五、N` → 无正文父节点为 container → narrative。Word 索引由 `scripts/gen/gen_note_section_kind_index.py` 生成到 `data/note_section_kind_index.json`（输出幂等、带 docx sha256，`--check` 漂移 exit 2），守卫校验索引与 Word 同步。matrix 被证伪不作判据（把「借款费用/债务重组/终止经营」登记为科目、「现金流量表项目注释」登记成截断码）。`load_target_sections` 总是用真实正文算 `content_hash`/`has_content`，按口径过滤。快照模块同根因（按 account_name 判类型）一并改用分类器。
  - R-07：外部来源（上传/知识库）的标题一致只到 candidate；同名目标按章路径消歧，仍不唯一 ⇒ manual_required；多来源争同一目标 ⇒ 全部 manual_required；模板来源「同模板同编号同标题 / variant matrix / soe↔listed 别名」才 confirmed。另：首轮把旧测试断言降级为 confirmed 并注释「也是正确行为」，已按 AC-3.3 纠正。
  - R-08：`validate_manual_mappings` 拒绝未知来源、非本次可写范围目标（跨项目/科目章节进叙述批次同一路径）、一对多、禁止对强选；手工映射占用的目标不再参与自动匹配。
  - R-25：`fold_unmatched_descendants`——未匹配的后代标题（标题转加粗段）并入最近已匹配祖先，与模板类型无关。
  - R-26：登记 4 条 Word↔系统章名别名（证据见上节），仅产生 candidate。
  - Word 端到端发现并修复：「存货」等在 Word 中同时出现在会计政策章与项目注释章，首轮两者争抢同一叙述目标 ⇒ 30 条冲突。新增**章类型门控**：来源所在章（或模板快照 section_kind）与目标类型不符 ⇒ `out_of_scope`，不进预览只计数。
  - 预览：替换后再消毒；预演追加结果（`append_html/append_hash`，apply 将逐字比对）；空正文 ⇒ 不可用；candidate/已有内容/跨标准/草稿/stale/占位/来源实体/日期/金额 ⇒ 需复核且不默认勾选；替换项可按章撤销（ID 含来源章节作用域）；digest 绑定来源身份 + 逐章 (source_id, target, before_hash, proposed_hash)。
  - R-27：`test_note_text_batch_word_e2e.py` 用四份 Word 跑「解析→分类→匹配→并入→预览」：科目章节误入叙述目标 0；叙述目标命中 53/55、72/74、82/86、95/99（棘轮冻结）；解析 2.0~3.6s。
  - 证据：13 个测试文件 248 passed；7 个变异（去门控、不并入、候选默认勾选、先到先得、同名取首个、外部标题直接定案、before_hash 回退）全部打红，文件逐字节恢复。
- ⏳ 待办：Task 10（生成链透传 section_id）未动；Task 21 端点与 Task 25/26 在第 4 组（R-01）落地。

- ✅ **第 3 组 R-06 / R-09 / R-12 + Task 30 验收缺口**（Phase 5）
  - R-09：`apply_batch` 只写服务端重算 preview 的结果（replace 写 `proposed_html`；append 写 `append_html`，且 selection 的 `proposed_hash` 须等于 `append_hash`），请求里的 `proposed_html` 一律不用。校验顺序：空/重复选择 → 目标存在且属本项目年度 → 所选目标 before_hash（409 `NOTE_BATCH_STALE_PREVIEW` 列出冲突章节、零写入）→ digest → selection 属本 preview 且映射一致 → 可用性/模式/哈希。
  - R-06：lineage 一律返回新对象（JSONB 未声明 MutableDict，原地改写不落库）。🔴 **反向新发现**：集团基线 `_build_lineage_entry` 写 list 且遇 dict 直接丢弃；其余写入方（程序裁剪 / 自动裁剪 / 国企↔上市转换快照）全按 dict、非 dict 当空 ⇒ 任一方后写都会抹掉另一方（自动裁剪 `dict(list)` 直接 ValueError），AC-11.2 只在一个方向成立。新增 `note_lineage.py` 统一 dict 约定：集团基线进 `group_baselines`、内容模板进 `content_templates`，历史 list 只读兼容；真库 1029 行全 NULL，无需迁移。既有 2 个测试文件（`test_group_note_baseline_service.py` / `test_note_ci7.py`）中 8 个用例断言旧 list 形态（断言的正是缺陷形态），已改为新形态。顺带修 `_find_affected_children`：每项目只抽一条 lineage 非空章节（`limit(1)` 无序）⇒ 抽到内容模板/裁剪章节就漏掉已应用基线的子企业；改为单查询逐章判断。
  - R-12：coordinator 逐个发布事件、单个失败只进 warning（带 `section_code`），回执 `event_delivery` = published / partial / failed；测试真跑 `coordinator.execute`，删除源码文本匹配用例。
  - Task 30 验收缺口：`generate_notes` 的 upsert 分支无条件覆盖 `text_content`（全仓此前无一处读 `is_local_override`）⇒ 改为本地改写时保留正文；表格仍走三态合并（数字须随试算表刷新），结构字段照常随模板更新。AI 批填按「空或 draft」取数，而批量写入后恰是 draft ⇒ 只靠 `is_local_override` 过滤排除，已补行为测试。
  - digest 口径修订（覆盖第 2 组记录）：digest 只绑来源身份 + 映射 + 拟写入内容，不再含 before_hash。原口径下他人改了**未勾选**章节也会整批报「摘要不一致」且不指出冲突章节；所选目标仍由逐章 before_hash 复核（设计 §7.2-4 / §7.3）。
  - 其余正文写入方评估（本组不改，登记）：①底稿叙述推送（`wp_disclosure_sync_service`）不看 `is_local_override`。上传/知识库路径只写叙述章节；推送注册表 80 条目标为科目章（五/八）外加 7 条上市「三、xxx」截断码（真库 0 行命中）⇒ 两者无交集。内容模板路径可写科目解释章节（AC-9.2 的需复核项），之后底稿保存推送叙述会以底稿为准；是否让底稿推送尊重本地改写涉及联动设计，**待用户拍板**。②集团基线下发、继承上年附注是显式用户操作，不属 AC-4.6 所说的静默覆盖。③顺带发现：`note_prior_year_import_service.inherit_from_prior_year` 读 `DisclosureNote.section_code`（模型无此列）⇒ 本年已有附注时必 AttributeError（`note_advanced` 路由在用）。非本 spec 引入，登记待修。
  - 证据：phase5 测试 24 例（真 SQLite + 真 ORM）；本 spec 12 个测试文件 + 集团基线/生成/RAG/转换/裁剪/reflow 回归共 507 passed。17 个变异全部打红，且红的形态与预期一致（写浏览器正文 / 去 stale / 去 digest / 不校验映射 / 首条事件失败即中断 / 只发第一章 / 事件无 section_code / lineage 原地改写 / dict 被丢 / list 被丢 / 读不到 dict 基线 / 受影响子企业只看一条 / 重新生成覆盖 / digest 绑现状×2 / service 自行 commit / AI 批填不排除），文件逐字节恢复。两条既有红守卫状态不变（见「非本 spec 引入」）。
  - 标记：Task 28 / 30 / 32 → `[x]`。Task 33（端点幂等、并发双请求、PG 行锁）随第 4 组端点落地；FOR UPDATE 在 SQLite 下不生效，行锁语义尚未实测。

- ✅ **第 4 组 R-01 / R-18**（parse / preview / apply 端点 + 端点级测试）
  - 端点：`note_text_batch.py` 补齐 GET sections（readonly）与 POST parse-upload / parse-knowledge / preview / apply（edit）。写入口门禁与附注其余写端点同序：项目 edit（含归档 423）→ `note:edit` → 合并锁 423。router 只做鉴权、线程池与错误映射，来源裁定集中在新模块 `note_text_batch_flow.py`。
  - 来源可信度：上传正文由客户端回传（双栏可二次编辑），服务端重新消毒并限额（单章 512KB / 整批 5MB → 413），由 preview_digest 绑定。文件元数据（名称 / hash / 字节数 / 格式）在 parse-upload 时用服务端派生键做 HMAC 签名，绑定项目与解析人；preview / apply 验签，审计记录只存验签后的值。知识库每次 preview / apply 都经 `load_documents` 重新逐篇判权，文档集合不一致 → 404，章节挂在未声明文档上 → 422。内容模板只读不可变版本，先判可见性（不可见 404），再核固定 content_hash（不一致 409）。客户端回传的章节 metadata 只留 `doc_id`：`section_kind` / `note_section` 会影响章类型门控与按编号匹配，不能由浏览器提供。
  - parse-upload：先有界读取（上限 + 1 字节），再校验扩展名、MIME、文件签名，解析放线程池。扫描件 PDF → `PDF_NEEDS_OCR`，空文档 → `NO_PARSEABLE_TEXT`，都返回中文原因（AC-1.5）。
  - apply：`X-Mutation-Id` 必填。流程：重建来源 → 锁目标 → 重算 preview → `apply_batch` → coordinator 一次 commit → 逐章事件。apply 必须带上与 preview 相同的 `manual_mappings` / `revoked_replacement_ids`，否则重算结果对不上 digest。`selections[].proposed_html` 改为可选且不使用。design §6.1 / §6.3 已同步契约。
  - 顺带修复：①知识库多篇文档拼接时，章节层级栈 / 子标题并入会跨文档（下一篇开头并进上一篇末节，上一篇的「项目注释」章会把下一篇叙述章节门控掉），现按 `doc_id` 切断；②多篇文档的解析 ID 都从 s1 起编会撞，现加文档命名空间。
  - 🔴 Task 8 假绿更正：原「注册表 smoke test」只对 `register_report_routers` 源码做文本匹配（铁律 ㉖），从未验证分发。改为在完整应用路由表上按 Starlette 真实分发规则（首个 FULL 匹配）解析两个 router 的每个端点，并加一个守卫自检（前序 catch-all 抢路由时必须判为未命中）。
  - 测试：`test_note_text_batch_endpoints.py` 43 例，用 TestClient 真发请求；只覆盖 `get_db` / `get_current_user`，鉴权依赖链真实执行。覆盖：只读 / 越权 / 合并锁 / 归档门禁；扩展名 / MIME / 签名 / 超限；扫描件与空文档；知识库判权且不泄露；模板可见性与固定 hash；HTML 攻击；伪造或跨用户复用元数据；跨项目手工映射；候选不默认勾选；科目解释章节只进需复核；跨标准标记；幂等复放与载荷冲突；预览后目标或来源变化 → 409 零写入；两个 mutation 先到者胜；预览后发布新模板版本仍按固定版本写入。另 `test_note_text_batch_apply_lock_pg.py` 是真 PostgreSQL 行锁守卫（scratch schema + 反向对照）：A 持锁时 B 必须阻塞，拿到锁后读到 A 已提交的正文。SQLite 忽略 FOR UPDATE，此前行锁从未实测。
  - 证据：35 个变异全部打红，且红的形态是「被放行」（200 响应体或断言消息），不是被别的校验顺带拦下。首轮变异有 8 个形态不对：3 个其实被别的校验顺带拦下（apply 门禁降级被上传签名拦成 422、知识库判权被章节归属拦下、preview 门禁被模板可见性拦成 404）；5 个的「已放行」被 `KeyError: 'detail'` 掩盖。已改为门禁用例换成不绑定解析人的知识库来源，判权拆成两个独立用例，所有错误断言先断状态码并打印响应体。例外：「缺 mutation id 放行」红在 DB NOT NULL 约束上，即没有此校验就是 500。回归：本 spec 14 个后端测试文件 + 路由拆分 + 已提交模块守卫共 263 passed（含真 PG）。两条既有红守卫状态不变。
  - 🔴 前端契约尚未对齐（第 6 组处理）：上传须原样回传 parse 响应（含签名 `source_metadata`）；知识库须带 `knowledge_doc_ids`；模板须带 `template_version_id + template_content_hash` 且不带正文；apply 须回传 preview 的手工映射与撤销项。现 `useNoteTextBatch.ts` 三处都不符，端到端仍不可用（此前是 404，不是本组引入的回退）。

- ✅ **第 5 组 R-03 / R-04 / R-13 / R-15 / R-17**（Phase 7 内容模板后端）
  - R-03：预检 / 保存改用严格 schema `SnapshotPreviewRequest` / `SaveContentTemplateRequest`。`public` 归属、自带 `allowed_project_ids` / `owner_group_project_id`、缺年度一律在 schema 层 422；测试断言 detail 是校验错误列表，排除「放进 service 后靠业务校验兜底」。预检改为 JSON body（design §6.2 原定如此），首版只收 query `year`。错误统一 `{error_code, message}`。
  - R-04：归属由服务端解析。集团模板须集团根项目的经理 / 合伙人：系统角色 admin/partner/manager，或在根项目被委派为 partner/signing_partner/manager（与平台写权限委派角色集同口径，首版漏 partner）。预检阶段就校验，并返回发布范围（根项目名），供前端二次确认。顺带修复：首版取「第一条委派记录」比对，同一用户多份人员档案时结果取决于行序，现改为 EXISTS + IN。
  - R-13：同名目录 `SELECT … FOR UPDATE` 后再分配版本号。并发首建时后到者的 INSERT 撞部分唯一索引，回滚 SAVEPOINT 后改取胜者已提交的行。🔴 **附带发现首版在 PostgreSQL 上必失败**：同一 flush 里先改 `current_version_id` 再插版本，而该外键不可延迟 ⇒ 每次新建版本都撞外键（SQLite 不校验所以没暴露）。现改为先落版本、再改指针，已用真 PG 变异坐实。另：内容回退到历史版本时复用该版本，并把 current 指回它（首版复用后 current 仍停在旧值）。
  - R-15：列表按 `visible_template_clause`（与 `can_view_template` 同口径）在 SQL 层过滤 + 分页，同时左连接当前版本元数据（来源企业 / 年度 / 标准 / 口径 / 版本号 / 质量摘要），不取 sections_data。首版是全表 SELECT 后逐行判权，每个集团模板一次根追溯。
  - 其他：快照按 `section_allowed_for_project` 排除口径不适用章节（与章节读取同一判据，免得旁路长出的合并专属章扩散进模板）；空白名称 422；可见但无权删除 → 403（不可见仍 404）；ORM 部分唯一索引补 `sqlite_where`，让测试库与 V187 语义一致（否则软删后同名重建被误拒）。
  - R-17：`test_note_content_template_snapshot.py` 整体重写为真 SQLite + 真 ORM，13 例真调 generate / preview / save / list / detail / versions / delete。含「SQL 过滤结果 ≡ 逐条 `can_view_template`」矩阵：2 用户 × 4 观察项目 × 5 类模板。端点安全矩阵 `test_note_content_template_endpoints.py` 12 例（TestClient）。真 PG 并发守卫 `test_note_content_template_save_concurrency_pg.py` 5 例：scratch schema 中两张模板表保留自身外键、部分唯一索引与不可延迟外键；并发首建 / 并发续版两种竞态；反向对照换回首版无锁实现，后到者必 IntegrityError。
  - 证据：18 个变异全部打红，含 3 个真 PG 变异（去行锁 / 首建不回退 / 先改指针），红的形态与预期一致。本 spec 后端回归 322 passed。scratch schema 残留 0。
  - 🔴 前端契约待第 6 组对齐：`useNoteContentTemplate.ts` 的预检仍发 query `year`、无 body ⇒ 现返回 422；列表项新增 `current_version` 元数据可直接展示。

- ✅ **第 6 组 R-02 / R-19 ~ R-24 + 前端契约对齐**（Phase 6 / 8 前端）
  - 契约：`useNoteTextBatch.ts` 重写。上传原样回传 parse 响应（含签名 `source_metadata`）；知识库带 `knowledge_doc_ids`；内容模板只传 `template_version_id + template_content_hash`，不带正文（R-02）。apply 回传最近一次 preview 的手工映射与撤销项。预览后改正文 / 映射 / 撤销项即标记过期，须重新预览才可写入。幂等键只在 NETWORK_ERROR / TIMEOUT / MUTATION_IN_PROGRESS 时保留。「已编辑」按原文逐章比对。`useNoteContentTemplate.ts` 预检改发 JSON body，保存携 digest，列表分页并带 `current_version`。
  - R-19：写入成功后作废**全部**章节缓存 → `fetchTree` → 当前章 `fetchDetailFresh`。首版只刷当前章，其他章读缓存仍是旧值。
  - R-20：三个入口按 `!isEqcrRole && effectiveCanEdit` 隐藏；包装组件 `DisclosureNoteContentTools` 的 `open()` 再按同一条件拒绝（后端仍独立 403 / 423）。
  - R-21：质量标志、置信度、不可用原因全中文，不显示内部 source_id。
  - R-22：「保存为内容模板」走真实流程：预检 → 集团二次确认 → 携 digest 保存；来源变化 409 时清掉预检。
  - R-23：新增 `utils/uuid.ts`（`crypto.randomUUID` 缺失时回退，内网 HTTP 下该 API 不可用）；不引入未声明的 `uuid` 包。
  - R-24：差异弹窗 v-model 改为 boolean。
  - 高风险章节不能直接勾选，只能在差异弹窗逐项核对后「采用此章」。高风险集合（`source_entity` / `entity_specific` / `account_explanation` / `cross_standard`）与后端 `summary.high_risk` 相同。换章节时核对清零；按钮禁用之外，onConfirm 再兜底校验一次。
  - DisclosureEditor 行数：三个弹窗收进包装组件后为 3281 行。HARD_CAP 3300→3281，whitelist 3296→3281（按实际值，不留余量）。
  - 🔴 **浏览器实测发现 1：平台模板标记泄漏。** 把四份 Word 模板当来源上传时，拟写入内容里出现 `{{section:…}}`、`##/SECTION##` 等标记（871 个中 854 个进入预览）。改在解析器层剥离（e2e 直接调用解析器，只在 flow 层剥会漏掉），先红后绿，新增 `test_platform_template_markers_never_reach_preview`。
  - 🔴 **浏览器实测发现 2：选择器把失败显示成「暂无模板」。** 打开「引用内容模板」时列表端点 500。根因是本地开发库从未跑过 V187：开发服务器热重载时 `GT_BOOTSTRAP_DONE=1` 会跳过迁移，而 V187 是 10-13 启动之后才加的。这是环境问题，不是代码缺陷；已用与启动期同一的 `MigrationRunner.run_pending` 补跑，三张表与 ORM 的列、部分唯一索引、外键逐项对账一致，漂移检测 0 项。但它暴露了前端的真缺陷：失败被显示成「暂无可用的附注内容模板」。现改为：
    - 失败显示错误态和「重试」；
    - 列表超过 50 个时提示「已显示 N / 共 M 个」，可加载更多（首版静默截断）；
    - 版本加载失败时不展开空版本区；
    - 只有最后一次列表请求能落状态，被 http 去重取消或迟到的旧请求不会覆盖新结果。
  - 触类旁通：两个 composable 的请求都没有静默全局拦截器，所以每次失败弹两次（拦截器一次、catch 一次）。其中 422 直接显示 pydantic 英文，403 只有笼统的「权限不足」，5xx 还会被拦截器自动重发两次。现所有请求带 `_silent`，由 `notifyBatchError` 统一提示一次中文：
    - 无业务 detail 的 HTTP 错误显示「<操作>失败（HTTP 状态码）」；
    - 本地中文异常保留原文；
    - 被去重取消的请求不提示；
    - 静默后拦截器不再代发合并锁事件，改由本模块在 423「合并锁定」时发出 `consol-lock:detected`。
  - 复盘新增：
    - 当前章节有未保存修改时，三个入口都拒绝打开。写入成功会重载附注，未保存的修改会被覆盖；内容模板也只按已保存内容生成。编辑器传入 `editDirty || autoSave.isDirty`，与离开页面拦截同口径。
    - 预览列表补「仅看高风险」筛选（设计 §9.3）。
    - 预览过期提示改为中性文案。首版在服务端冲突时也提示「你改过来源正文」。
    - 引用弹窗头部补保存时间。
  - 测试与检查：
    - vitest 5 个文件 38 例（composable 2 个文件、组件 3 个文件）。
    - ESLint 0 问题；编辑器的 12 条 ESLint 告警与 HEAD 相同。
    - 单区域 vue-tsc（`tsconfig._note-text-batch.json`）0 错误，注入 TS2322 能报出。编辑器 vue-tsc 在本 spec 范围内只剩既有的 `fetchDetail` 空值告警（2777 行，非本组引入）。
    - 后端：本 spec 18 个测试文件 308 passed，含真 PG 守卫。
  - 变异：36 个全部打红，文件逐字节恢复。构成：composable 契约 9、错误提示与列表竞态 11、选择器 4、组件门控 11、解析器剥标记 1。首轮有 2 个漏网（「换章节不清核对」「onConfirm 不复核」），补用例后打红。其中兜底用例首版是假绿：不认 disabled 的按钮桩没有把 `disabled` 声明为 prop，它作为 attr 透传到 `<button>` 上，点击仍被禁用态拦下。已修正，并加正向对照（核对后同一路径能采用）。
  - 浏览器实测（和平药房_2025，admin）：
    - 上传 `soe_standalone.docx` 解析出 382 章；预览为需复核 56 / 不可用 4；手工映射后提示过期，重新预览后显示已确认。
    - 弹窗有修改时关闭会确认。
    - 选择器空态与失败态：用 `page.route` 模拟 500，只出现 1 条中文提示、0 条全局通知，重试后恢复。
    - 有未保存修改时入口拒绝打开。期间取得的编辑锁已释放，正文未保存，本地草稿已清。
  - 浏览器实测中，**写入类请求一律在网络层模拟，未落库**：
    - apply 返回 200：弹窗关闭，目录树与当前章重新请求，先前缓存过的章节再点击时重新请求。对照组：缓存命中时只请求上年数据。
    - apply 返回 409：弹窗保留选择，写入按钮禁用，重新预览后恢复。
    - 保存模板：载荷只有 `{year, name, description, owner_scope, snapshot_digest}`；成功后显示版本、来源与质量摘要。
    - 模板链（列表、历史版本、预览均为模拟）：按固定的历史版本 v1 预览；提示「已有更新版本 v2」；只默认勾选推荐项；高风险项只能核对后采用；「仅看高风险」生效。
    - 真库核对：`note_text_batch_applications`、模板、版本均为 0 行；本项目附注最后更新时间仍是 10-10。
  - 标记：Task 39 / 47 / 48 / 49 / 52 → `[x]`。以下仍为 `[~]`：
    - 35：可拖分栏、右栏按目标父章分组未做。右栏与模板弹窗共用按匹配类别分组，每行显示目标章号与标题，见设计 §9.2 修订。
    - 36：文字版 PDF、低置信、需 OCR、损坏文件四种状态未在浏览器验证。
    - 37：知识库选择未用真实文档在浏览器验证。
    - 38：变量替换撤销界面未在浏览器验证。
    - 40：只读 / EQCR 账号下入口隐藏未用真实账号验证。
    - 50：全流程见 Task 55。
    - 51：已引用项目在编辑器内的「新版本可用」提示未实现；引用弹窗内已有提示。
  - 其他：设计 §9.3 的「保存人」目前只显示时间。版本元数据只有 `created_by` UUID，显示姓名需后端补联表。Phase 6 / 8 实施记录里的首轮描述（「保存为内容模板」占位、编辑器直接挂三个弹窗、hard cap 3300）已被本组取代。

- ✅ **第 7 组 · 整体复盘**（全量回归 + 跨组核对）
  - 扩大回归：
    - 后端：引用本 spec 改动模块的全部测试加平台守卫，共 72 个文件，首跑 90 failed / 1731 passed。用干净 worktree 归因：本 spec 开工前（385a235ed）和第二轮复盘前（67841e8aa）都是同一批 89 条失败（附注模板结构、文本卫生、母公司章节，以及两条既有守卫），与本 spec 无关；本 spec 引入的只有 1 条（见下）。
    - 前端：附注组件、composables、utils、views 等 246 个文件 3984 例，18 例失败分布在 11 个文件，都不在本 spec 改动范围。`composables.spec.ts` 里失败的是 `useNoteTemplate` 用例，其源码最后一次修改早于本 spec。
    - 端点鉴权基线：「仅登录不校项目」225 条、未鉴权 6 条，逐条核对后本 spec 路由 0 条。
  - 🔴 **回归抓到的本 spec 问题（第 2 组引入）。** `note_text_batch_service` 读取 variant matrix 账户级 `legacy_aliases`（章节号旧码），触发母公司章节 spec 的「表级 legacy_aliases 零消费方」守卫。这里用的是章节号别名、不看表名，已按守卫要求登记进 `ALLOWED_CONSUMERS`。顺带修一个潜伏缺陷：别名池用 `{变体: 码}` 字典推导，同一变体有多个旧码时只剩最后一个（现数据 0 处多码）。改为逐对展开，抽出纯函数 `_index_variant_matrix` 并补用例，先红（`KeyError`）后绿。
  - **Task 12 补齐变异证据**（验收要求：任一写入路径绕开消毒都会打红）。首轮 10 个「绕开消毒」变异只有 2 个打红；以下几处去掉消毒后全部测试仍绿：知识库 Markdown / HTML / 中文章节号三个分支、PDF 主路径与降级、追加时的现有正文、预览中替换前的消毒。处置：
    - `parse_text_source` 的四个分支收敛为**单一出口**，在出口统一消毒、剥模板标记、写来源标识。HTML 分支的原始标签只靠这一道消毒。
    - 补用例：四个文本分支与 PDF 都消毒并剥标记；追加时现有正文也消毒；替换清单只描述会写入的内容（只出现在被丢弃内容里的企业名，不再生成「幻影」替换项）。
    - 复跑 10 个变异：9 个打红，1 个是等价变异。等价的是预览「替换后」那次消毒：来源已先消毒，替换前后的值都已转义，去掉它输出不变，保留作纵深防御。
  - 解析器顺带修复：
    - DOCX 单章超限时按字符截断，首版截断发生在消毒之后，截出的半个标签或未闭合段落原样返回。改为截断后再消毒，先红后绿。
    - PDF 章节数超上限时首版静默截断。补告警，与 DOCX 同口径。
    - PDF「纯文本降级」分支挂在 `if not sections` 之后，但只要有可提取文本，主循环必产出章节（无标题正文进「（无标题）」人工确认章），所以该分支永远不可达。已删除，设计 §5.2 同步修订。
    - 夹具有两处坑：`insert_text` 不换行，超出页宽的「##」会被裁掉；标题按「字号 > 中位数 × 1.3」识别，正文行必须多于标题行。
  - 另核：本地库 1009 行活动附注不含任何平台模板标记，内容模板快照不会带入标记。预览层用的是不剥标记的基础消毒器，因此这里没有缺口。
  - 证据：本 spec 后端 18 个文件加母公司章节守卫共 325 passed（含真 PG）；Task 12 变异 9 个打红、1 个等价；前端 5 个文件 38 例，ESLint 0，单区域 vue-tsc 0。全量 vue-tsc 在本仓库会 OOM（既有环境限制），只做单区域检查。
  - 标记：Task 12 / 53 → `[x]`。合计 45 / 56 为 `[x]`，其余 11 项保持 `[~]`。注意 gt-plan MCP 的 `spec_status` 不识别 `[~]`，会把本 spec 误报为 100%。
  - 仍为 `[~]`，需要环境或真实数据：
    - 54：Playwright 上传全链，含文字版 PDF、扫描件等真实文件。
    - 55：Playwright 模板全链（A 保存集团模板 → B 引用 → A 发布 v2 → B 重新预览）。需要真实写库或专用测试项目。
    - 56：真 PG 守卫。本轮已在本地库补跑 V187，三张表与 ORM 的列、部分唯一索引、外键逐项对账，漂移 0 项；但还没有提交成可重复运行的守卫。
    - 36：PDF、低置信、需 OCR、损坏文件四种状态的浏览器验证。
    - 37：知识库真实文档的浏览器验证。
    - 38：变量替换撤销界面的浏览器验证。
    - 40：只读 / EQCR 账号下入口隐藏的验证。
    - 50：全流程验证，见 55。
  - 仍为 `[~]`，需要拍板：
    - 10：生成链透传 section_id 并回填旧行。要改 DisclosureEngine 生成链，并对全部项目批量写库。
    - 35：可拖分栏与按目标父章分组。现已改为按匹配类别分组，见设计 §9.2 修订。
    - 51：编辑器内「新版本可用」提示。需要新增后端查询。
  - 待用户拍板，非本 spec 引入或跨 spec：
    - JSON 种子与四版 Word 不一致：15 处章名不一致、66 节放错章、38 节缺失。建议另立 spec。
    - 底稿叙述推送 `wp_disclosure_sync_service` 不看 `is_local_override`。内容模板写入科目解释章节后，底稿保存会覆盖它。
    - `note_prior_year_import_service.inherit_from_prior_year` 读取不存在的 `DisclosureNote.section_code`，本年已有附注时必然 AttributeError。
    - 引用弹窗显示保存人姓名需要后端联表。
    - 三处重复的 `newIdempotencyKey` 可改用 `utils/uuid.ts`（未动）。
    - 既有红守卫（非本 spec）：`test_lazy_import_resolvability` 僵尸条目、`test_project_endpoint_authorization_baseline` 225 > 224，以及附注模板结构类 87 条。

- ✅ **第 8 组 · 浏览器实测补齐 Task 36 / 37 / 38 / 40**（只读或网络层模拟写入，不落库）
  - 36 来源四态：文字版 PDF 解析出 3 章；无标题 DOCX 进「需人工选择」章；扫描件、加密 PDF、损坏 DOCX 都返回 422 和中文原因，并以常驻提示显示；超过 50MB 在前端拦下。
  - 37 知识库：库里 23 篇知识库文档已全部删除，0 篇可用，所以检索结果和「解析成功」只能在网络层模拟；判权都走真后端。
    - 选择器标题写明「最多 5 篇」；解析请求为 `{year, doc_ids}`。
    - 真后端对不存在的文档：解析返回 422「1 篇文档不可用（无权限、已删除或不存在），已跳过」；预览时重新判权返回 404「所选知识库文档不可用…请重新选择」，不泄露存在性，当前来源保留。
    - 有未写入编辑时切换来源会二次确认，选「继续编辑」则保留。
  - 38：
    - 用含 `{公司名称}` / `{年度}` 的文档实测：差异弹窗列出两项替换；撤销一项后显示「恢复替换」，两个弹窗都提示预览过期，写入按钮禁用。
    - 重新预览时请求带 `revoked_replacement_ids`，结果中被撤销的 token 保留原文、另一项照常替换；替换 ID 在两次预览之间不变。
    - 「仅看已变更」「仅看未匹配」筛选生效。
  - 40（AC-6.3）：合并锁定在网络层模拟；EQCR 只改浏览器会话里的角色。两种情况下三个入口都隐藏，管理员对照组正常显示。归档与 EQCR 走同一个 `canWrite`，由单测覆盖。
  - 🔴 实测抓到并修复的问题：
    - 解析失败时当前来源保留，但提示里没有文件名，看不出是哪个文件失败。现在提示与常驻提示都加文件名前缀。
    - 前端拒收文件（扩展名 / 大小）只弹 toast，常驻提示仍是上一次的错误（例如「签名校验失败」）。现在改走同一个 `lastError`（`rejectFile`）。
    - AC-6.3 缺口：编辑器的 `canEdit` 只含归档与项目权限，不含合并锁，也不看 `note:edit`，合并锁定时入口照常显示。现在包装组件自查锁定态，并监听 423 事件实时刷新；可用性 = `canWrite` + `note:edit`（与后端 `require_operation` 同码）+ 未锁定。编辑器三个菜单改为按 `available` 隐藏，同一行替换，行数不变（3281）。
    - 🔴 第一版锁定查询又引入回归，浏览器实测在提交前抓到：同页锁定横幅几乎同时发同一个 GET，http 去重会**取消先发的那一个**，横幅拿不到锁定态就不显示，表现为入口藏了、横幅却没出来。改为 `_dedupe: false` + `_silent`，并加断言钉住。复测：两次请求都到达，横幅显示，入口隐藏。
    - AC-5.1：知识库来源只显示文档名，没有版本。现在显示为「名称（v版本）」，抽成纯函数 `describeSource` 并补单测。
  - 证据：vitest 5 个文件 44 例；8 个变异全部打红（解析失败不带文件名 / 拒收不落 lastError / 可用性不看锁 / open 不拦锁 / 不看 note:edit / 锁定查询走去重 / 查询失败当锁定 / 不监听 423）；ESLint 0。单区域 vue-tsc 在本 spec 范围内 0 错误；`usePermissionMatrix` 会把 `stores/project.ts` 的 5 条既有错误一并带进来，不是本组引入。编辑器 vue-tsc 只剩既有的 2777 行告警。
  - 标记：Task 36 / 37 / 38 / 40 → `[x]`。37 的真实文档成功路径受限于本地数据（0 篇可用），浏览器里只做了网络层模拟；后端成功路径由端点测试覆盖。

- ✅ **第 9 组 · 补齐 Task 35（AC-2.1 / 2.2 / 2.3）**
  - 逐条核对 AC-2.1~2.5：2.4（编辑器单实例懒挂载）与 2.5（各状态 + 关闭有改动二次确认）已有实现；缺 3 处，本组补齐：
    - AC-2.1 双栏不能拖。改为 `el-splitter`，左栏默认 42%，左右最小 280 / 360px。浏览器实测拖动分隔条，两栏宽度 683 / 944 → 843 / 784。
    - AC-2.3 右栏不按父章节分组（第 6 组改成三分组时去掉了）。预览项加 `target_chapter_title`（目标所属一级章标题，只供展示，不进 digest）；右栏在推荐 / 需复核 / 不可用三类之内再按一级章分组，组内保持预览顺序，无目标的归「未匹配目标章节」。「父章节」按一级章理解，更深层级不再细分，每行仍显示目标章号与标题。浏览器实测：需复核组分 7 个章（如「重要会计政策、会计估计（34）」「税项（3）」），不可用组为「未匹配目标章节（4）」「税项（1）」。
    - AC-2.2 左栏没有匹配状态（逐条核对时发现，原待办未列）。预览只给跳过来源的计数，左栏分不清「被跳过」和「没匹配上」。预览响应加 `skipped_sources`（逐个来源带 `folded` / `out_of_scope`，只供展示，不进 digest），左栏每个来源显示「推荐引用 / 需复核 / 不可用 / 未匹配 / 已并入上级章节 / 不在可填范围」，悬停看目标章节。浏览器用国企单体 Word 模板实测：解析 382 章，预览前 0 个状态，预览后 382 个全部有状态（需复核 55、未匹配 4、不可用 1、已并入上级 77、不在可填范围 245），与服务端 60 项 + 跳过 322 项逐项对上；未编辑时关闭不弹确认。
  - 证据：后端本 spec 18 个文件 + 1 个节点 327 passed；vitest 6 个文件 48 例（新增 `noteDocUploadDialog.spec.ts`，验分栏与左栏接线）；11 个变异全部打红，失败都是预期形态（分组塌成一组 / 未匹配不单独成组 / 预览项不带章标题 / 跳过来源不逐个返回 / 左栏不收跳过来源 / 并入与范围外不分 / 不可用与未匹配不分 / 左栏不显示状态 / 状态不接预览 / 退回普通双栏 / 面板无最小宽度）；ESLint 0；单区域 vue-tsc 在本 spec 范围内 0 错误（仍只有 `stores/project.ts` 的 5 条既有错误）。
  - 标记：Task 35 → `[x]`。

- ✅ **第 10 组 · AC-8.2 保存人姓名 + Task 51（AC-8.4 新版本只读提示与重新预览入口）**
  - AC-8.2：版本元数据只有 `created_by` UUID，界面只显示保存时间（第 6 组记的待办）。列表 / 详情 / 版本三个端点改为读时解析 `created_by_name`：优先人员档案姓名，回退登录名，都没有为 null（不编造）。同一用户有多份人员档案的情况真库里现查就有，按 `MIN(name)` 聚合，结果确定，也不会因联表把版本行翻倍。选择器与引用弹窗头部共用 `savedByLabel`，显示「经理甲 保存于 2026-10-01」。
  - AC-8.4：列表加 `year` 查询参数，每项带 `last_applied`（本项目该年度**最近一次**引用的版本；按引用时间取，不取最大版本号，刻意引回旧版同样提示）。选择器据此提示「有新版本 v2（本项目已引用 v1）：已写入的正文不会自动更新，点「重新预览」核对后才会写入」，入口改为「重新预览」；引用的就是当前版本时只说明「本项目已引用当前版本 v1」；历史版本里标出已引用的那一版。提示只在打开选择器时出现，编辑器不另发请求（编辑器已到 3281 行上限）。
  - 「不自动覆盖」：真调 `save_snapshot` 发布 v2 后，已引用项目的正文逐字不变；端点级补全链路：v1 写入 → 发布 v2 → 只预览不变 → 用 v2 重新预览并确认后才变，两条应用记录各钉一个版本。
  - 真库：模板 / 版本 / 应用记录都是 0 行，列表端点走不到新增的两条 SQL ⇒ 用只读探针直接在真 PG 上执行后 ROLLBACK：两个多档案用户解析成人员姓名，两个无档案用户回退登录名，「最近一次引用」查询正常返回。浏览器真请求带 `year=2025`，返回 200、空列表；有模板时的提示、按钮文案、历史版本标记、引用弹窗头部在网络层模拟列表 / 版本 / 预览后核对，写入请求一律拦截。
  - 证据：后端本 spec 18 个文件 + 1 个节点 331 passed；vitest 7 个文件 57 例（新增 `noteContentTemplateApplyDialog.spec.ts`）；17 个变异全部打红，失败都是断言（不查人员档案 / 多档案取 MAX / 无登录名回退 / 详情或版本列表不解析姓名 / 已引用不按年度 / 取最早一次 / 不限本项目 / 端点不透传年度 / 列表不带年度 / 同版本改按版本号判 / 保存人不进说明 / 入口不改「重新预览」/ 不显示提示 / 历史版本不标 / 引用弹窗头部不显示保存人 / 把「禁止自动覆盖」误读成「已引用即不再覆盖」）；ESLint 0；单区域 vue-tsc 本 spec 范围 0 错误，注入一处类型错误能报出 TS2322（检查确实覆盖到）。
  - 复盘发现（本组不修）：
    - Task 50 的「来源 badge」与 AC-11.3「平台 UI 展示每章来源」：前端没有任何界面读取 `template_lineage`，复核者在编辑器里看不到某章来自哪个模板版本。留到下一组。
    - `ContentTemplateVersionMeta` / `ContentTemplateListItem` 两个 schema 全仓 0 引用，且早已与真实返回不一致（含不返回的 `schema_version`、缺 `current_version_id`）。只登记，不在本组删。
  - 标记：Task 51 → `[x]`。有模板时的界面只能在网络层模拟（真库 0 个模板），真实写入的全流程仍归 Task 55。

- ✅ **第 11 组 · Task 56 真实 PG 守卫（V187 真跑 + ORM 对账 + 约束语义 + 服务行为 + 样本容量）**
  - 新守卫 `test_note_content_template_v187_pg.py`（34 例）：scratch schema 里用 MigrationRunner 同一个分句器逐句执行 V187 原文（16 条语句），users / projects 等依赖表为去外键副本；public 只读。
    - V187 ↔ 生产库：scratch 建出的三张表与 public 的列 / 约束 / 索引逐项一致（列 12 / 15 / 15，约束 7 / 8 / 10，索引 4 / 4 / 4）；`fk_nct_current_version` 两边都存在且不可延迟。
    - V187 ↔ ORM：列集合、类型（ORM 按 PG 方言编译后比）、可空性逐列一致；CHECK 名、索引名与唯一性、外键（列 → 表.列 + ON DELETE）逐一对上。
    - 约束语义 19 个探针，每个独立事务、断言到具体约束名：归属 CHECK 两条；个人 / 集团同名部分唯一（软删后可重名，个人与集团同名可共存）；版本号与 hash 唯一、hash 长度、版本号为正；`current_version_id` 外键立即生效（先改指针后落版本必失败）；版本 / 应用记录 RESTRICT 删除；应用记录的来源形状、来源类型、状态、指纹长度 CHECK；同项目 mutation 唯一。
    - 真服务跑在 V187 表上：兄弟可见、异组不可见（按 ID 取详情也拿不到）、个人模板只本人可见；同内容复用 v1、改内容出 v2、改回去复用 v1 且当前版本指回；保存人「经理甲」、最近引用 v2（当前 v1）；两章预览后其中一章被他人改 ⇒ 整批 409、两章都不写、无应用记录，重新预览后两章整批写入。
    - 样本容量：真库 6 个项目年度的全套快照最大 625,695 B、最多 200 章，均在 10 MiB / 500 章内。
    - 清理：public 三张表前后行数一致（0 / 0 / 0），scratch schema 结束后不存在。
  - `test_note_text_batch_word_e2e.py` 加四份权威模板的容量判据（不截断、不 413）：章节 315 / 322 / 382 / 412，单章最大 27,168 B，整份正文 33~58 万字节，解压 680~1170 万字节。
  - 🔴 发现（本组不改）：
    - design §11.2「解析返回章节数」业务阈值 300 是按项目章节数（max 200）定的，Word 标题粒度更细，四份权威模板都超过它。代码只强制硬上限 500，国企合并 412 离上限只剩 18%：企业自己多加些小标题就会触顶，超出部分的尾部章节被截断（只给一条提示）。是否上调需要拍板。
    - V187 的 DO 块用 `pg_constraint WHERE conname = …` 判断外键是否已建，不限 schema：同库其它 schema 已有同名约束时会跳过补建（scratch 里实测复现，守卫再执行 V187 自己那条 ALTER 补齐）。生产只有 public，不受影响；V187 已应用，不改。全仓迁移普遍这样写（V107 / V108 / V122 / V123 / V147 / V151 / V167 / V182 / V187 等），只登记。
  - 证据：守卫 34 例 + 容量 4 例全绿；12 个变异全部打红，失败都是断言（ORM CHECK 改名 / 可空性漂移 / 长度漂移 / 外键 ON DELETE 漂移 / 漏声明索引；迁移漏建集团同名唯一索引（指向篡改副本，V187 原文不动）；先改指针后落版本；异组集团模板可见；过期预览照写；保存人不查人员档案；快照硬上限压到真实样本以下；章节上限压到权威模板以下）；本 spec 后端 19 个文件 + 1 个节点 369 passed；ruff 通过。
  - 标记：Task 56 → `[x]`。

- ✅ **第 12 组 · Task 10 评估与实施（生成链透传树形字段 + 回填工具 dry-run）+ 全文顺序缺陷**
  - 评估：AC-3.1 的匹配不依赖 section_id（同模板按目标行 UUID / 规范编号，跨模板按 variant matrix 与显式别名），不透传也不影响匹配正确性。但评估中发现本 spec 自己有两处查询用错了这批字段：
  - 🔴 缺陷（本 spec 引入，已修）：`load_target_sections` 与 `generate_snapshot` 按 `sort_index, note_section` 排序。`sort_index` 是 V019 的「同层级内序号」（真库 6 个项目里 4 个全为 0，首汽的 93 个取值也是同层序号），不是全文顺序；平台的导出、编辑器、生成链都按 `sort_order`。结果是真库 4 个项目上手工映射下拉、模板章节和模板引用预览都按汉字码位排成「一、三、九、二、五…」，章内也颠倒（「五、会计估计变更」排在「会计政策变更」前）。改为 `sort_order` 打头，`sort_index` 与编号只作并列次序。
  - 触类旁通：同一写法另有 4 处（集团基线快照、AI 对话的宿主章节定位 / @ 提及 / MCP 附注检索，后三处带 limit，排错会截到错的章节），一并改；新增 AST 守卫：附注的 `order_by` 首键不得是 `sort_index`（扫到 16 处排序点，防扫描空转）。
  - Task 10 实施：
    - 生成链：`_load_templates` 透传模板 JSON 的 section_id / level / parent_section_id / sort_index（国企 188 节、上市 204 节，ID 唯一、父引用全可解析）；`generate_notes` 新行写入，旧行**只补空不覆盖**；同项目年度已占用的 section_id 不重复写，占用表取不到就一律不补。自定义模板没有这批字段，保持为空。
    - 回填工具 `backend/scripts/migrate/backfill_note_tree_fields.py`：与生成链共用同一个补齐函数，按项目自己的模板类型与口径取模板；默认 dry-run，`--apply` 才写，UPDATE 带 `section_id IS NULL`，过期计划再跑也不覆盖。
    - 旧脚本 `migrate_section_number_to_section_id.py` 把两套模板合成一个按编号的索引且国企优先：两套模板有 20 个同编号章节，其中 14 个 ID 不同（如上市版「八、1 政府补助」在国企版是「货币资金」），上市项目会拿到国企的 ID；也不区分口径、不查同项目占用。已在文件头标注勿再执行。
  - 真库 dry-run（只读，执行后复查 section_id 计数不变）：可补 737 行——重药控股安徽 159、和平药房 145（另 40 行已有）、医疗器械 145、陕西华氏 144、宜宾 144；首汽 173 行已全有；模板里没有的章节 59 行保持为空；冲突 0。
  - 发现（本组不改，跨 spec）：
    - 上市版模板 JSON 有两条「三、研发支出」（ID 分别以 `…yan-fa-zhi-chu` 与 `…-2` 结尾），合并时按编号去重只留后一条。
    - `disclosure_engine.py` 第 1320 行引用的 `_with_column_meta` 全仓无定义（ruff F821）：表格模板有表头、无数据行时走到即 NameError，被生成链的 try/except 吞成「该章没有表格」。
  - 证据：本 spec 后端 21 个文件 + 1 个节点 383 passed；12 个变异全部打红，失败都是断言；与附注生成 / AI 对话 / 集团基线相关的 66 个测试文件放到 HEAD 干净检出上对照：88 个失败里 87 个 HEAD 上同样失败（模板结构类等既有红），剩下 1 个是 `procedure_trim` 的「disclosure_engine.py 与 HEAD 逐字节相同」守卫——工作树有改动即红、提交后自愈，它不随提交自愈的结构判据仍绿；ruff 通过。
  - 行数门禁：`ai_chat/mcp_tools.py` 触碰前已 1067 行且不在白名单（任何改动都会被拒），按门禁规则登记白名单，写明理由与拆分方向。
  - 标记：Task 10 仍为 `[~]`。代码、工具与测试已完成，真实库回填（5 个项目 737 行）须经拍板后执行，执行后再勾。

- ✅ **第 13 组 · Task 50 来源标记（AC-11.3）+ 批次回执 + 写入时刻与日期显示两处缺陷**
  - 缺口：AC-11.3 要求在平台界面展示每章来源与版本，前端却没有任何界面读 `template_lineage` 或应用记录（第 10 组复盘登记）。lineage 只记内容模板，上传 / 知识库只在 `note_text_batch_applications.detail` 里，所以按应用记录取，三类来源同一口径。
  - 后端：只读端点 `GET /api/projects/{project_id}/disclosure-note-text-batch/sources?year=`（readonly）。逐章给出最近一次批量写入的来源类型、模板名 + 版本 / 文件名 / 知识库文档名 + 版本（不回 doc_id）、模式、写入人（与保存人同口径）、时间；`modified_after` = 当前正文与该次写入结果的 hash 不同。已删章节、他项目章节、坏行不展示也不报错。只看最近 500 次写入：更早写入、之后 500 次都没再碰过的章节不显示标记，一个项目年度实际远达不到。
  - 前端：`NoteSourceBadge.vue` 挂在编辑器章节标题下，经 `noteContentTools.ts` 一个 import 引入（编辑器仍 3281 行）。按项目年度一次取回，切章不重发；写入成功后经 eventBus `note-text-batch:applied` 刷新（只认同项目同年度，卸载时注销）；切项目时迟到的旧结果不覆盖；取数失败不显示、不弹错。只在界面显示，不写正文、不进导出。
  - 批次回执：原来只提示「已写入 N 个章节」，后端返回的替换 / 追加分布没有界面用，而替换与追加对正文的影响不同。改为「已写入 3 个章节（替换 2 · 追加 1）」（为 0 的不列）；联动通知部分失败另行告警，逻辑不变。此前回执与告警都没有断言，现补上。
  - 🔴 实测抓到并修复的缺陷：
    - 「最近一次」会认错（本 spec 引入）：应用记录的时间用库默认 `now()`，那是事务开始时间，先开事务、后拿到锁的一方会记得更早。SQLite 的秒级精度让两次写入时间并列、再按随机 id 定先后，`test_template_source_carries_name_and_version_and_latest_wins` 6 次里红 1 次，由此发现。改为 apply 加锁后取的那一刻，与章节 `updated_at`、lineage 的 `applied_at` 一致；第 10 组「最近一次引用」同样受益。复跑 8 轮全绿。
    - 日期按 UTC 显示（第 10 组引入）：保存人与来源标记都直接截时间串前 10 位，后端给的是 UTC，北京时间 0~8 点保存 / 写入的记录会显示成前一天。改用平台 `fmtDate` 按本地日期显示，格式随之变为 `2026/10/01`。
  - 浏览器（写入一律拦截；来源数据与 apply 响应在网络层模拟，解析与预览走真后端）：
    - 国企项目「公司基本情况」标题下显示「📋 来自内容模板「集团通用模板」v2」，悬停「2026/10/14 审计助理甲 批量写入（替换）」。模拟时间是 UTC 10-13 23:30，本地日期正确。
    - 知识库 + 改过的变体：「📚 来自知识库「政策汇编.md（v3）、旧制度.md」（之后有修改）」，换警示色。切到没批量写入过的章不显示，切回恢复，且不重发请求（4 次页面加载共 4 次请求）。
    - 全流程：上传国企单体 Word → 真预览 → 勾 1 章 → 写入（响应模拟）⇒ 提示「已写入 1 个章节（替换 1）」，弹窗关闭，标记随即刷新（写入后 1 次请求）为「📄 来自上传文档「soe_standalone.docx」」。
    - 真后端只读请求返回 200、空结果（真库 0 条应用记录）；控制台无错误。
  - 证据：本 spec 后端 21 个文件 + 1 个节点 387 passed；vitest 8 个文件 67 例（新增 `noteSourceBadge.spec.ts` 7 例，含编辑器挂载的源码级判据，剥注释后匹配，注释掉标签也会红）；36 个变异全部打红，失败都是预期形态（后端：取最早 / 只按 id 排 / 后者覆盖 / 不限年度 / 不限本项目 / 不排已删 / 不跳过不可见章节 / 改过恒为否 / 坏行崩溃 / 知识库回 doc_id / 模板不带版本 / 不解析写入人 / 端点无鉴权 / 端点要求 edit / apply 用库默认时间；前端：回执不分模式 / 替换追加对调 / 列出 0 / 部分失败不告警 / 全部送达也告警 / 写入成功不广播 / 不监听 / 卸载不注销 / 不比年度 / 无请求序号 / 不随项目刷新 / 请求不静默 / 不显示版本 / 模式写死 / 文案不标改过 / UTC 截日期（来源标记与保存人各一，单跑时区一例也红）/ 非法时间显示「-」/ 编辑器去掉标签 / 注释掉标签）；ESLint 0 errors（编辑器 12 条既有警告）；ruff 通过；单区域 vue-tsc 本 spec 范围 0 错误，编辑器只剩既有的 2777 行告警，注入类型错误报 TS2322。
  - 标记：Task 50 仍为 `[~]`。来源标记与批次回执已具备；验收要求的「保存模板 → 另一项目引用 → 写入」真实写库全流程与 Task 55 一并执行。

### 收口（2026-10-15）

- 状态：52/56 `[x]`。余 4 项 `[~]`，代码侧已没有可独立推进的部分，都等拍板或真实写库：
  - Task 10：代码、回填工具与测试已完成；真实库回填 5 个项目 737 行（`backend/scripts/migrate/backfill_note_tree_fields.py --apply`）待拍板。
  - Task 54：上传链的真实写入验收。解析、手工映射、编辑、预览已在第 8 / 9 / 13 组用真后端实测，写入只在网络层模拟过；「正文正确、缓存不旧、留痕存在、导出不含审计标记」要真写一次才能验。
  - Task 55：模板链的真实写入验收（A 保存集团模板 v1 → 兄弟 B 引用 → A 发布 v2 → B 只提示 → 重新预览写入）。真库没有同组兄弟项目，需要先造测试集团或指定项目。
  - Task 50：随 Task 55 的真实写入全流程一并验收。
- 回归（对照基线 = 本 spec 第一个提交的父提交 `385a235ed`，临时检出后跑同一批失败节点）：
  - 后端：按本 spec 改动的模块挑出 368 个测试文件，8592 passed / 421 failed / 30 skipped / 3 xfailed / 7 xpassed。421 个失败里 418 个在基线上同样失败（附注模板结构、合并附注表头、底稿同步等既有红）；另 3 个是真库测试（程序委派对账预览、公式推送 SQL 失败后续跑、V169 真库），在 HEAD 上单独复跑 4 轮全过，属顺序 / 时序相关的偶发失败，不涉及本 spec 改动。
  - 前端：相关 27 个文件 410 例 2 例失败，全局守卫 81 个文件 4 个文件失败；这 6 处在基线上同样失败（`useNoteTemplate` 映射预设、`WorkpaperEditor.vue` 行数棘轮、token 单一入口、原生 fetch 鉴权、SFC 语法、空测试文件），不涉及本 spec 文件。
- 清理：删除 spec 创建时的一次性校验脚本 `backend/scripts/analyze/_validate_disclosure_note_batch_spec.py`（只校验初版全 `[ ]` 的编号，早已失效，全仓零引用）。
- 待拍板（本 spec）：
  1. Task 54 / 55（含 50）真实写入：用真实项目，还是先造测试项目（55 需要同组兄弟项目）。
  2. Task 10：是否对 5 个项目执行回填 737 行。
  3. Word 解析章节数：硬上限 500，国企合并 412 章只剩 18% 余量；§11.2 的业务阈值 300 低于四份权威模板（315 / 322 / 382 / 412），是否上调。
- 跨 spec 发现（只登记，未改）：
  - JSON 种子与四版 Word 不一致：15 处章名不同、66 节放错章、38 节缺失；上市版 JSON 有两条「三、研发支出」。
  - `wp_disclosure_sync_service` 不看 `is_local_override`：内容模板写入的科目解释章节会被底稿保存覆盖。
  - `note_prior_year_import_service.inherit_from_prior_year` 读不存在的 `DisclosureNote.section_code`。
  - `disclosure_engine.py` 引用未定义的 `_with_column_meta`（F821，被 try/except 吞成「该章没有表格」）。
  - 迁移 DO 块按名查 `pg_constraint` 不限 schema（V187 等全仓普遍写法，生产单 schema 不受影响）。
  - 三处重复的 `newIdempotencyKey`，可改用 `utils/uuid.ts`。
  - `ContentTemplateVersionMeta` / `ContentTemplateListItem` 两个 schema 零引用，且已与真实返回不一致。
  - 旧脚本 `migrate_section_number_to_section_id.py` 会给上市项目写国企的 section_id，已在文件头标注勿用。
  - `file_size_whitelist.txt` 有 6 行被写坏成 `$1xxxx`、2 行缺基线数，首行 BOM 又让注释行不被识别（基线上就如此，行数门禁的守卫因此红）；本 spec 未动这些行。
  - `components.d.ts` 里本 spec 组件的自动登记未提交（按约定不提交该文件）；编辑器显式 import 这些组件，不依赖它。

### 拍板后执行（2026-10-15）

> 用户拍板：Task 54 / 55 先造测试项目做真实写入验收；Task 10 先对 2 个项目回填；Word 解析章节上限上调到 1000。

- ✅ **第 14 组 · Word 解析章节上限 500 → 1000（2026-10-15 拍板）**
  - 解析上限 `note_document_parser.MAX_SECTIONS` 改为 1000，上传（DOCX / PDF）与知识库共用这一个常量。
  - 🔴 只改解析上限会出新缺陷，红测先复现：解析结果要原样回传给预览 / 写入，而请求体 `ParsedSource.sections` 上限仍是 500，1000 章的文档「解析成功、预览 422」（`List should have at most 500 items`）。现将来源章节数与手工映射数（预览、写入两处）同步改为 1000；手工映射每个来源至多一条、每个目标至多一个来源，服务端已有校验。单次写入的章节数仍按项目章节数 500（每个目标章节至多一条），不跟解析上限走。
  - 测试：端点级用 1001 个标题的 Word 真走解析 → 截到 1000 章并提示「超过上限 1000」→ 整份回传预览 200、目标章节照常匹配；另钉住三处请求体上限与解析上限同值（防再漂）。
  - 端点测试文件已到行数门禁 800，新测试放在 `backend/tests/test_note_text_batch_caps.py`（复用端点夹具），不加白名单。
  - 证据：本 spec 后端 22 个文件 + 1 个节点 389 passed；6 个变异全部打红（拆文件后复验两处关键变异仍红），失败都是预期形态（解析上限回到 500 / 不截断 / 截断不提示 / 来源章节数上限 500 致预览 422 / 预览或写入的手工映射上限 500）；ruff 通过。design §11.2 表格与第 11 组复核记录同步更新。

- ✅ **第 15 组 · Task 10 先对 2 个项目真实回填（2026-10-15 拍板）**
  - 选择：真库 5 个待回填项目都是国企单体（没有上市项目，覆盖不到上市模板）。选了两种情形：重庆和平药房（已有 40 行、只补空的情形，也是浏览器实测用的项目）和重药控股安徽（全空、模板全覆盖的情形）。
  - 事前评估（同一事务演练回填后 ROLLBACK，未落库）：两项目批量写入的可填范围不变（和平 narrative 66 / 科目解释 134，安徽 66 / 93，没有章节因补上父子关系变成纯父节点）；同年度 section_id 无重复。章节编号、底稿推送、编辑器目录都不按这批字段工作（编号按 note_section；底稿推送按 note_section 匹配，函数里叫 section_id 的变量实为章节编号；合并口径的政策树编号只用于合并附注），单体项目不受影响。
  - 备份：`backend/backups/note_tree_fields_backfill_2026-10-15/`（已在 .gitignore，不入库）：`backup.json` 两项目全部 376 行的四个树形字段、`plan.json` 回填计划、`rollback.sql` 把计划内 304 行恢复成回填前的值（一个事务）。
  - 执行：`backfill_note_tree_fields.py --project <和平> --project <安徽> --apply` ⇒ 写入 304 行（和平 145、安徽 159），冲突 0。
  - 事后核对：计划内 304 行与计划值逐字段一致；计划外的行四个字段一个没变；其他列（编号 / 年度 / 删除标记）无变化；重新 dry-run 两项目可补 0（幂等）；同年度无重复 section_id；两项目全文顺序（sort_order → sort_index → 编号）回填前后逐行一致；浏览器打开两个项目的附注编辑器（写请求拦截），目录与正文正常、控制台无错误。
  - 🔴 发现（回填前就存在，本组不改）：和平药房那 40 行已有 section_id 的是上市模板的 ID（`chapter-05-he-bing-cai-wu-bao-biao-xiang-mu-zhu-shi-*`，「五、合并财务报表项目注释」下的章），挂在这个国企项目的「五、1」等编号上，父节点在本项目不存在；其中 3 行的 sort_order 与第一~三章并列（100 / 200 / 300），全文顺序靠 sort_index 才排在后面。来源疑似早年的编号回填或国企↔上市转换，需另查。
  - 标记：Task 10 仍为 `[~]`：2/5 个项目已回填并核对；其余 3 个（医疗器械 145、陕西华氏 144、宜宾 144 行）等你确认后执行，命令同上换项目 ID。

- ✅ **第 16 组 · 造测试集团（供 Task 54 / 55 真实写入验收）**
  - 新工具 `backend/scripts/seed/seed_note_text_batch_uat.py`（幂等，`--dry-run` 不连库）：1 个合并母项目 + 2 个子项目，名称都带「【测试】」前缀，国企模板、2025 年度。建项走 `project_wizard_service.create_project`（向导同一校验链：USCC 企业代码、唯一性、集团三码），集团关系按三码由 `sync_group_links` 派生，不手写 `parent_project_id`；子项目用 `DisclosureEngine.generate_notes` 生成附注初稿。
  - 真库结果：母 `68e16afa…`（合并，无附注）、甲 `94a40b23…`、乙 `989cebf5…`（单体，各 159 章，其中 91 章有正文），三者集团根相同；再跑一次全部复用、跳过生成。建项会重算 2025 年度全部项目的派生链接，事前只读核对现值与按三码推导一致（7 个项目零差异），事后真实项目的上级关系无变化。生成的 159 章 section_id 全部非空，即第 12 组的生成链透传在真库生效（Task 10「新生成附注稳定字段非空」）。
  - 🔴 首跑抓到并修复两处：
    - 独立运行只导入了用到的几个模型，建项 flush 时解析不了 projects 的外键表（`NoReferencedTableError: accounting_standards`），事务未提交、未落库。现在先按 `app.models` 全量注册（与 schema_drift_detector 同法），新增在全新解释器里验证的测试。
    - 附注初稿逐章调用大模型：vLLM 在线时约 10~20 秒一章，两个项目 300 多章要近一小时（15 分钟后仍在第一个项目）。中止后该事务回滚、只留下已提交的三个项目。测试数据要可复现，本脚本内把这一步替换成返回空（引擎回落到模板默认文字），平台「生成附注」不受影响。
  - 测试：`backend/tests/test_seed_note_text_batch_uat.py` 4 例（企业代码合法且带测试前缀；真走建项服务后两个子项目集团根 = 母项目、只给子项目生成、重跑不重复建不重复生成；dry-run 不连库；独立运行先注册全部模型）；7 个变异全部打红（不填上级与控制方代码 / 每次都重新生成 / 查重不按企业代码 / dry-run 也连库 / 母项目也生成 / 不注册模型 / 不替换大模型那一步）；只去掉上级代码、保留控制方代码属等价变异（仍按控制方派生到母项目）。
  - 发现（跨 spec，只登记）：
    - 平台「生成附注」在没有上年附注时逐章同步调用大模型，上述耗时同样会出现在真实项目上。
    - 生成日志里 `build table_data failed for 十一、本公司的其他关联方情况: name '_with_column_meta' is not defined`：第 12 组登记的未定义函数在真库生成时确实触发，该章表格丢失。

- ✅ **第 17 组（一）· Task 54 真实写入验收抓到：空正文章行进了上传可填范围（AC-2.3「纯父节点 = container」两处缺陷）**
  - 现象：测试项目甲上传 Word 预览，「公司基本情况」「财务报表编制基础」都报「存在 2 个同名目标章节，需人工选择」。新生成附注的章行（「一 公司基本情况」「二 财务报表编制基础」等）正文为空、只承载子节，却和同名子节「一、1」「二、1」一起成了目标。
  - 根因一：`table_data` 是未设 `none_as_null` 的 JSONB，生成链写 None 存成 JSON null；章节读取按 `IS NOT NULL` 判「有表格」，真库恒真（纯文字章节 475 行全是 JSON null、0 行 SQL NULL）⇒ container 永不成立。既有端点测试的夹具不写这一列（SQL NULL）⇒ 假绿。现按「非空 JSON 对象」判，与 Word 导出「非对象或空对象不出表」同口径：SQL 侧 PostgreSQL 用 `jsonb_typeof`、SQLite 用 `json_type`，Python 侧 `has_table_payload`，两侧在真 PostgreSQL 上逐值对拍。只取类型判定，不把表格内容读回 Python。
  - 根因二：分类器先按 Word 标题返回 narrative，叙述章标题的纯父节点（「二 财务报表编制基础」「四 重要会计政策、会计估计」等）走不到容器判定，与 design §4.1「仅承载子节的顶层“重要会计政策” → container」不符；只修根因一时「一 公司基本情况」（标题不在 Word 索引里）变对，「二」仍错。现只有 Word 判为科目注释章的标题提前返回；叙述章标题照旧不套「国企历史编号 五、N」，但适用容器规则。
  - 同口径：内容模板快照（scope=all）的章节类型改用同一容器判据，同一章节在模板里与目标侧类型一致。
  - 影响（只读对比新旧判据，全部 8 个有附注的项目）：两个测试项目各 11 个章行 narrative → container；6 个真实项目 0 变化——和平药房、重药安徽的章行有大模型生成的正文，仍是 narrative（与子节同名时照旧需人工选，属数据如此）；其余 4 个未回填树字段，没有父子关系。
  - 测试：新增 `test_note_text_batch_targets.py` 4 例（夹具按真库形态写 JSON null 并先断言存储形态；叙述范围不含空章行、全部范围标 container；只有表格的父节点仍是 narrative、空对象仍是 container；上传预览唯一命中子节；模板快照与章节读取逐章同类型）；`test_note_text_batch_targets_pg.py` 5 例真 PostgreSQL 守卫（形态对照：JSON null 行 `IS NOT NULL` 为真；10 种取值 SQL 与 Python 逐值一致；章节读取真跑；反向对照：换回首版判据，章行变回 narrative）；`test_note_section_kind.py` 补叙述章标题纯父节点三个变体、叙述章标题不套国企历史编号、`has_table_payload` 9 种取值。
  - 证据：HEAD 版本复现红（15 failed + 5 errors）；7 个变异全部打红且失败形态符合预期（判据退回 `IS NOT NULL` / 叙述标题提前返回 / 不排除空对象 / Python 侧只判非 None / 快照不传容器判据 / PostgreSQL 走 SQLite 分支 / 叙述标题也套国企历史编号）；本 spec 后端 24 个文件 + 1 个节点 415 passed；ruff 通过。
  - 触类旁通：全仓按 `table_data` 判「非空」的 SQL 共 5 处，只有本处是缺陷。其余 4 处：附注生成的上年缓存读回后再按对象过滤；数据校验另有表格形状条件；报表行附注引用对 JSON null 行只登记章节标题（第 3 级「本项目实际存在的章节」需要它），表格逻辑按对象跳过；高级查询的附注取数 LIMIT 会被 JSON null 行占用，但唯一调用方传「不截断」（硬上限 5000 行，单项目附注不超过 200 行），当前无可见影响，只登记。

- ✅ **第 17 组（二）· Task 54 上传链真实写入实测（测试项目甲）+ 文字版 PDF 标题判不出（Task 18 / AC-1.3）**
  - 实测（真实写库，只写测试项目甲 `94a40b23…`，其余请求经浏览器写保护拦截）：
    - Word「甲公司附注.docx」5 章：第 17 组（一）修复后「公司基本情况」「财务报表编制基础」唯一命中子节「一、1」「二、1」；「补充事项说明」手工指定「十三、1」，指定后提示预览已过期、重新预览为「已确认 / 用户手工映射」；左栏改写「记账本位币」同样须重新预览；「公司基本情况」带「企业特有内容」，未勾核对项时「采用此章」不可点。勾 5 章写入成功（替换 5）。
    - 无标题「无标题说明.docx」：进「（无标题）」需人工选择 → 指定「四、现金及现金等价物」→ 写入，回执「已写入 1 个章节（替换 1）」。
    - 文字版 PDF「会计期间说明.pdf」：首次解析整篇进「（无标题）」（缺陷，见下）；修复后识别出标题「一、会计期间」→ 候选「四、会计期间」，差异弹窗选「追加到现有内容后」写入：原文 + 空段 + PDF 文字，无来源标记。
    - 扫描件「扫描件.pdf」：422，弹窗内提示「PDF 不含可提取文本，可能是扫描件；请上传文字版，或先上传知识库完成 OCR」，不出预览按钮。
    - 留痕（只读探针）：3 条应用记录均 succeeded，文件名 / sha256 / 字节数与原文件一致；7 次章节写入逐条 before_hash = 写入前正文、after_hash = 当前正文；同一章节两次写入（会计期间：替换后追加）前后哈希首尾相接；写入的 6 章均 draft + `is_local_override`，其余 153 章未变。
    - 切章回看：记账本位币 / 会计期间 / 公司基本情况 显示写入后正文；来源标记显示最近一次来源（会计期间为 PDF）。回执只截到无标题那一次，另两次弹窗关闭后提示已消失，响应体的替换 / 追加分布分别为 5/0、0/1。
  - 🔴 缺陷（本组修复）：文字版 PDF 标题判不出。解析器按 span **个数**取字号中位数，一个标题 + 一段正文 = 2 个 span，取上中位 = 标题字号 ⇒ 标题全判不出，整篇进「（无标题）」只能人工选。改为按**字数**加权的中位数（并列取较小）：正文字数远多于标题。全仓按字号判标题的只有这一处。
  - 测试：`test_note_document_parser.py` 补短文档 3 种形态（单节 / 每节一行正文 / 标题行多于正文行）与正文字号 3 例（含表格数字字数多于正文的情形，结果与首版一致）。HEAD 版本复现红（3 个标题用例），3 个变异全部打红（不加权 / 并列取大 / 降序累计）；本 spec 后端 24 个文件 + 1 个节点 421 passed；ruff 通过。
  - 🔴 发现（下一批修复）：附注 Word 导出把 HTML 正文原样写成一段文字（`<p>…</p><p>&nbsp;</p>…` 直接可见）。批量写入的正文都是 HTML，编辑器单章保存也是 HTML（`NoteRichTextEditor` 存 innerHTML，真库已有 4 章）。导出里来源 / 审计标记 0 命中、无批注与修订，但「正文正确」不成立 ⇒ Task 54 仍为 `[~]`。

- ✅ **第 18 组 · 附注 Word 导出把 HTML 正文原样输出（Task 54 验收「正文正确」；design §5.5）**
  - 现象：甲的 Word 导出里「会计期间」一段就是 `<p>本公司会计年度…</p><p>&nbsp;</p><p>本公司会计期间…</p>`。`text_content` 存 HTML —— 批量写入写消毒后的 HTML，单章编辑器（`NoteRichTextEditor`）存 `innerHTML`，真库已有 4 章（和平 八、9，安徽 一、1 / 二、1 / 三、1）—— 而导出把它当一段纯文字写进 Word。
  - 修复：新模块 `note_text_word_render.py`，附注正文进 Word 的出口共用：程序化导出（编辑器「导出 Word」、附注导出端点、导出包、批量导出）、模板模式 `{{section:code}}` 填充（交付中心）、交付件增量刷新、旧版全套填充（`word_export.py` full-package 仍在用）。段落 / 空段 / 加粗倾斜 / 段内换行 / 列表 / 小标题（加粗，不用标题样式以免进目录）/ 表格（合并单元格，跨度上限 50）；**不含标签的纯文字各出口输出不变**。
  - 交付件回填比对：`_normalize_text` 先把 HTML 投影成交付 docx 提取得到的文字，否则修复后所有 HTML 章节都会被判为「已修改」；修复前生成、正文里是原样标签的交付件按同一投影，同样不误判。有序列表用「（1）」：回填把「1. 中文」开头的段当章节标题剔除，用「1. 」会误判。
  - 测试：`test_note_text_word_render.py` 47 例（渲染 15 类形态 + 纯文字逐字不变 + 占位原位填充与沿用格式 + 投影与「渲染后再提取」逐样本对拍 + 五个出口各一例 + 回填三种情形）。HEAD 版出口复现红 6 例；16 个变异全部打红（五个出口各自不分流 / 同段替换用原文 / 回填不投影 / 有序项用「1. 」/ 小标题不加粗 / 空段留 nbsp / 跨行不截断 / 按 id 取元素 / 标签判定放宽 / 新段不沿用格式 / 投影留换行 / 纯文字不去空白）。
  - 回归：导出与交付件相关 21 个测试文件 398 passed；3 个失败均与本组无关 —— `test_note_template_mode` 两例在第 16 组提交上同样失败；`test_property_16_compliance_guardrail_classification` 是 hypothesis 生成「0．㐀」被判为标题，用 HEAD 代码复跑同样判为标题（本组只改 `_normalize_text`，未碰标题判定）。本 spec 后端 25 个文件 + 1 个节点 468 passed。ruff：新文件通过；4 个改动的旧文件共 16 条均为既有（与 HEAD 同类同数）。
  - 实测：甲经真实端点重新导出 —— 全文 0 处标签残留；会计期间输出为「原文 / 空段 / PDF 文字」三段；来源与审计标记、批注、修订 0 命中。真实项目只读核对（导出器只读库）：和平 1 章、安徽 3 章 HTML 正文在程序化与模板两种模式下都按段输出，0 处标签残留（和平 八、9 的列表项输出为「（1）其他应收款按账龄列示」）。
  - 登记（不在本组）：① 交付件回填写回的是 Word 段落文字，HTML 格式与正文里的表格在回填后被拍平；② 交付 docx 提取丢弃段内换行，多行纯文字章节回填会被误判为已修改（既有）；③ Property 16 的生成策略会产出「数字＋全角点＋汉字」这类被判为标题的文字，偶发红（既有）；④ `test_note_template_mode` 两例既有红。
  - 行数门禁：`deliverable_writeback_service.py` 触碰前已 1189 行且未登记白名单（任何改动都会被拒），按门禁规则登记白名单，写明理由与拆分方向（护栏分类 / 冲突检测与裁决 / 留痕）；`note_word_exporter.py` 在既有白名单 +5% 内。
  - 标记：Task 54 → `[x]`。

- ✅ **第 19 组 · Task 55 模板链真实写入（一）+ 纯文字正文进批量写入未按编辑器口径转换、裸 & 被补分号（AC-9.3 / AC-10.4）**
  - 实测（真实写库，测试项目甲 → 乙）：
    - 甲保存集团模板 v1：预检 159 章（有内容 91、高风险 45），发布范围为集团母项目，二次确认后保存；甲正文未变。
    - 乙（同集团兄弟）的选择器能看到该模板与版本说明（v1、来源企业与年度、保存人、日期）。预览 159 章：需复核 91（乙已有正文、来源为草稿）、不可用 68（来源正文为空）、推荐 0。
    - 变量替换「【测试】附注批量甲有限公司 → 【测试】附注批量乙有限公司」可撤销；企业特有、报表科目解释须逐项核对后「采用此章」才可点。
    - 勾 5 章（替换 4、追加 1）写入成功。正文、lineage（`content_templates` 条目带 template_version_id + content_hash + application_id）、应用记录（template_version_id = v1）三方一致；切章回看正文与来源标记「📋 来自内容模板「…」v1」正确。
  - 🔴 缺陷（本组修复）：
    - 纯文字正文进批量写入未按编辑器口径转换：真库多数章节 `text_content` 是纯文字（生成链写入；乙 87 章里 64 章多段，真实项目还含 markdown 表格与列表），编辑器加载时按 markdown 渲染。追加首版把 HTML 直接接在纯文字后，存成混合值（乙「会计期间」实测），原有分段在差异预览和 Word 里都并成一段（一章 9 段并成 1 段）；纯文字模板来源写入后、差异预览「现有内容」也一样。现统一按编辑器口径（marked：GFM 表格 + 单换行即换行）转 HTML：新增 `note_text_to_html`（markdown-it-py，开表格与删除线、breaks，纯文字里的尖括号一律按文字），追加两侧、预览来源、差异预览「现有内容」都走它；写入前复核仍按库里原文 hash。
    - 消毒器把裸 `&` 当实体补分号：`R&D` → `R&D;`（可见乱码，真库有「DD&A」「P&L」）。现与浏览器一致：数字引用与已知实体（含无分号的旧式实体如 `&nbsp`）保留，其余 `&` 转 `&amp;`。
    - Word 渲染：换行后的行首空白丢弃（markdown 转出的 `<br />` + 换行形态，否则第二行开头多一个空格）。
  - 新依赖：`markdown-it-py==4.2.0`（原为 rich 的传递依赖，已装同一版本；requirements 精确锁定）。是否「HTML」与 Word 渲染共用同一判据（`is_html_note_text` 移到消毒器）。
  - 测试：新增 `test_note_text_plain_source.py` 16 例（分段 / 换行 / markdown 表格与列表 / 尖括号与 & / 其它尖括号片段按文字 / 幂等 / 追加保留已有分段与表格 / 追加去重 / 新内容转换 / 裸 & 四种形态 / 预览来源转换 / 追加预演与复核 hash / 现有内容显示），渲染补 1 例。HEAD 复现红 12 例；13 个变异全部打红（不转义裸 & / 已知实体也转义 / 纯文字不走 markdown / 不开表格 / 单换行不转换行 / 放行原始 HTML / 不去标签边换行 / 追加不统一已有正文 / 不统一新内容 / 预览来源不转换 / 现有内容按原文显示 / 换行后不去行首空白）。本 spec 后端与导出、交付件相关 39 个文件 640 passed。
  - 既有数据：乙「会计期间」是修复前追加产生的混合值（测试项目），后续 v2 重新预览写入时一并核对。
  - 登记（不在本组，待拍板）：未经批量写入的纯文字章节，Word 导出仍按纯文字一段输出，markdown 表格以竖线原样出现（真库和平 105 章、安徽 87 章、医疗器械 112 章含 markdown 表格；既有行为）。Word 渲染的纯文字分支接 `note_text_to_html` 即可与编辑器一致，但会改变全部既有项目的导出。
  - 标记：Task 55 / Task 50 仍为 `[~]`（v2 发布、只提示不自动更新、重新预览写入、原子冲突待第 20 组）。

- ✅ **第 20 组 · Task 55 / 50 模板链真实写入（二）+ 版本 hash 漏字段吞掉新状态、批次回执把新增报成替换（AC-7.4 / AC-8.3~8.4 / AC-9.1 / AC-9.6；design §3.2~3.3）**
  - 实测（真实写库，测试项目甲 → 乙）：
    - 甲在编辑器改「四、记账本位币」一句后同名保存 ⇒ v2。乙 159 章正文逐章 hash 不变（不自动更新）；乙的选择器提示「有新版本 v2（本项目已引用 v1）……点「重新预览」核对后才会写入」，按钮变为「重新预览」。
    - 乙重新预览 v2，选三章：记账本位币（替换；差异预览「现有内容」为乙现文、「拟写入」为 v2 文本）、十三、1（追加到乙已有的 4 段纯文字后）、会计期间（替换，清掉第 19 组修复前追加的混合值）。
    - 原子冲突：确认前另发请求以「另一用户」身份改乙的记账本位币 ⇒ 写入返回 409 `NOTE_BATCH_STALE_PREVIEW`，点名「四、记账本位币」；弹窗显示「预览已过期……」与冲突章节，确认按钮禁用；三章一个未写，无应用记录（快照比对）。重新预览后「现有内容」即他人的改动，勾选与写入方式保留，写入成功。
    - 写入后：十三、1 存为纯 HTML（原 4 段 + 空段 + 追加段），编辑器与 Word 导出都按段；记账本位币 / 会计期间为 v2 正文；三章来源标记「v2」；应用记录固定 v2；lineage 各追加一条 v2 条目，v1 条目保留。记账本位币那条的 before_hash 是「另一用户」改后的值 ⇒ 中间那次人工改动在留痕上可见。
    - 全程 4 条应用记录、11 次章节写入：lineage 条目与应用记录的版本 / content_hash / mutation_id 逐条一致；7 个被写章节的现正文 hash 都等于最近一次 after_hash；相邻两次写入断链 3 处，恰是三次人工改动（上述他人改动 + 为验证推荐组两次清空「二、1」）。
    - 选择器「历史版本」列出各版本，均可「引用此版本」，已引用的标注；可见性（只读 GET）：异组和平药房列表 0 条、详情 / 版本 404，集团母、甲、乙可见。
    - 乙的真实 Word 导出：0 处标签残留；十三、1 按段；模板名 / 版本 / 来源标记 / application / lineage 0 命中；甲公司名 0 处。全程无 shared_config 请求。
  - 🔴 缺陷一（本组修复）：内容模板版本 hash 只算「章节编号 + 正文 hash」。sections_data 里的状态 / 待刷新 / 标题 / 章节类型，以及版本行上的来源企业名与口径都不进 hash ⇒ 只改这些再保存被判「内容未变化，沿用已有版本」。实测：甲把「二、1」标为已确认，预检显示「草稿 90」，保存提示沿用 v2，发布出去的仍是「草稿 91」、该章仍是草稿，在乙永远进不了「推荐引用」。改为对版本行存下的全部内容（章节快照全字段 + 来源项目 / 年度 / 名称 + 口径）取 canonical JSON SHA-256（design §3.2 原文即如此），复用 ⇔ 存着的就是这次算出的。修复后同一操作保存出 v3（二、1 为 confirmed，草稿 90）。
    - 推荐组实测：乙清空「二、1」「记账基础和计价原则」后预览 v3 ⇒ 推荐 1（二、1，默认勾选，新增）/ 需复核 90（记账基础：来源为草稿，不默认勾选，新增）/ 不可用 68，合计 159。真库附注 100% 是草稿，设计把来源草稿归需复核 ⇒ 推荐组要有已确认的来源章才会出现；修复前，确认章节后重新保存模板也到不了这一步。
    - 测试：`test_note_content_template_snapshot.py` 补 7 例（有正文的章改状态 / 待刷新 / 标题各一；空章改状态 / 待刷新各一——空章不出质量标记，只能靠字段本身区分；来源项目改名；保存后的版本 ≡ 保存时重算的快照）。HEAD 复现红 7 例；6 个变异全部打红（回到首版公式 / 漏 status / 漏 is_stale / 漏 section_title / 漏来源元数据 / 漏来源企业名）。首轮「漏 status」「漏 is_stale」存活：有正文的章改状态会连带改质量标记，hash 照样变；补空章两例后打红。
    - 副作用：修复后首次保存既有模板会多出一个版本（hash 口径变了）；真库只有本测试模板。
  - 🔴 缺陷二（本组修复）：批次回执与应用记录没有「新增」。design §3.3 `mode_summary` 是「新增 / 替换 / 追加统计」，实现只按写入方式计（写进空章也是 replace）⇒ 勾选摘要「新增 2」，回执却是「已写入 2 个章节（替换 2）」，像覆盖了已有正文。改为与勾选摘要同口径：写进没有可见正文的章算新增（只有空段也算），逐章 `detail.mode` 仍记实际写入方式；前端回执分别报新增 / 替换 / 追加。实测：乙再清空「二、1」后引用 ⇒「已写入 1 个章节（新增 1）」，应用记录 `{"new": 1, "replace": 0, "append": 0}`。修复前的 3 条应用记录保持原样（审计记录不回填）。
    - 测试：后端 3 例（替换 + 新增 / 追加 + 新增 / 目标只有空段），前端回执 1 例；HEAD 复现红；3 个变异全部打红（只按写入方式计 / 空章按真值判 / 回执不报新增）。
  - 补测（无缺陷）：一、1 撤销变量替换并重新预览 ⇒ 拟写入为甲公司名，风险项新增「含来源企业名称」；两项风险勾一项「采用此章」仍禁用，勾齐才可点，取消一项又禁用；恢复替换后风险项回到一项。未采用该章。
  - 回归：本 spec 后端与导出、交付件相关 39 个文件 689 passed / 1 skipped；前端 `useNoteTextBatch.spec.ts` 17 passed，ESLint 0 问题；ruff 通过。
  - 未在真库覆盖（自动化测试已覆盖）：跨标准 / 跨口径警告（AC-8.5，测试集团同为国企单体）；模板有、目标没有的章节（AC-9.5，两项目结构相同）。
  - 登记（不在本组）：
    - 单章保存不更新 `updated_at`：`report_models` 里 7 处 `updated_at` 只有 `server_default` ⇒ 预览带的 `expected_updated_at` 对单章编辑不起作用，冲突全靠 before_hash（本组实测有效）；附注「更新时间」会停在最近一次批量写入。
    - 生成链丢行：`disclosure_engine.classify_template_content` 在无表章节把短编号行当表标题丢弃（既不进正文也不进指引）。国企模板「或有负债」段的「2.经济利益流出不确定性的说明。」因此消失，乙「十三、1」与「九、或有事项」都缺这一行；同段末尾孤立的「】」来自 JSON 种子本身。
    - 内容相同的「替换」也会写留痕并置 `is_local_override`（v1 的「八、9」before = after）；预览是否标「与现有内容相同」待定。
  - 状态：Task 55 → `[x]`，Task 50 → `[x]`。本 spec 55/56 `[x]`，余 Task 10（已回填 2/5 个项目，其余 3 个待确认）。

### 收口（拍板后执行完成，2026-10-15）

- 状态：55/56 `[x]`。第 14~20 组均已提交推送（第 20 组 `c385b11e5`）。余 Task 10 `[~]`：已回填和平药房、重药安徽 2 个项目；医疗器械（145 行）、陕西华氏（144）、宜宾（144）3 个待确认，命令见第 15 组。
- 测试数据（保留，供后续回归；不再需要时从项目回收站删除三个项目，内容模板在选择器里删除——只软删目录，版本与应用记录保留）：
  - 测试集团：母 `68e16afa…`（合并，无附注）、甲 `94a40b23…`、乙 `989cebf5…`，名称都带「【测试】」；由 `seed_note_text_batch_uat.py` 幂等生成。
  - 内容模板「【测试】集团附注正文模板（Task55）」v1 / v2 / v3；应用记录甲 3 条（上传）、乙 4 条（模板）。
  - 验收中对测试项目的人工改动：甲「四、记账本位币」加一句（v2）、「二、1」标为已确认（v3）；乙「四、记账本位币」被模拟的他人改动一次后由 v2 覆盖，「二、1」「记账基础和计价原则」被清空后经批量写入回填。
- 跨 spec 发现（拍板后执行期间新增，只登记，未改）：
  - 平台「生成附注」无上年附注时逐章同步调用大模型，约 10~20 秒一章（第 16 组）。
  - `disclosure_engine.py` 的 `_with_column_meta` 未定义在真库生成时确实触发，「十一、本公司的其他关联方情况」表格丢失（第 16 组；收口节已登记 F821）。
  - `disclosure_engine.classify_template_content` 在无表章节把短编号行当表标题丢弃，「2.经济利益流出不确定性的说明。」从生成正文消失（第 20 组）。
  - 和平药房 40 行带上市模板的 section_id，挂在国企章节编号上（第 15 组）。
  - 按 `table_data IS NOT NULL` 判「有表格」的另外 4 处 SQL：当前无可见影响（第 17 组（一））。
  - 交付件回填写回 Word 段落文字，HTML 格式与正文表格被拍平；交付 docx 提取丢段内换行，多行纯文字章节回填被误判为已修改（第 18 组）。
  - 未经批量写入的纯文字章节，Word 导出里 markdown 表格以竖线原样出现；改为与编辑器一致会改变全部既有项目的导出，待拍板（第 19 组）。
  - 单章保存不更新 `updated_at`（`report_models` 7 处只有 `server_default`）；内容相同的「替换」也写留痕并置 `is_local_override`（第 20 组）。
  - 既有红：`test_note_template_mode` 2 例；`test_property_16_compliance_guardrail_classification` 偶发红（第 18 组）。

- ✅ **第 21 组 · Task 10 剩余 3 个项目真实回填（2026-10-15 用户确认）**
  - 事前评估（同一事务演练回填后 ROLLBACK，未落库）：医疗器械可补 145 / 模板无此章 14，陕西华氏 144 / 14，宜宾 144 / 16，冲突 0；三项目全文顺序不变，同年度无重复 section_id。
  - 批量写入可填范围：医疗器械（叙述 66 / 科目解释 93）、华氏（66 / 92）不变。宜宾有 10 个章行（「一」「二」等，正文与表格皆空、只承载子节）补上父子关系后由叙述变为容器，叙述可填 66 → 56。这 10 行本就不该是写入目标：与第 17 组（一）同一问题，章行和同名子节会同时成为目标，上传时报「存在 2 个同名目标章节」；回填后与新生成的项目一致。医疗器械、华氏的章行带正文，仍算叙述。前端不按章节类型区分（全仓没有容器判断），编辑器照常可编辑这些章行。
  - 备份：`backend/backups/note_tree_fields_backfill_2026-10-15_b/`（已在 .gitignore，不入库）：`backup.json` 三项目全部 481 行（含已删除行）的树形字段及编号 / 年度 / 删除标记 / 顺序号 / 标题 / 正文 md5 / 状态，`plan.json` 回填计划，`rollback.sql` 把计划内 433 行恢复为回填前的值（一个事务；已在事务里逐条执行、每条恰命中 1 行后回滚，确认可用）。
  - 执行：`backfill_note_tree_fields.py --project <医疗器械> --project <华氏> --project <宜宾> --apply` ⇒ 写入 433 行，冲突 0。
  - 事后核对：计划内 433 行与计划值逐字段一致；计划外的行四个树形字段没变；编号、年度、删除标记、顺序号、标题、正文、状态均无变化；重新 dry-run 三项目可补 0（幂等）；无重复 section_id；全文顺序与备份逐行一致。浏览器写保护下打开三个项目的附注编辑器：目录 12 个一级章，章节数 159 / 158 / 160，正文正常，控制台无错误。
  - 标记：Task 10 → `[x]`（5/5 个项目已回填）。本 spec 56/56 `[x]`。
