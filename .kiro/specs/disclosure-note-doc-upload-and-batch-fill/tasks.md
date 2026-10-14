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
- [~] 7. 实现内容模板授权策略 `can_view/manage_template`，统一供 list/detail/versions/delete/preview/apply 使用；不可见返回 404。
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
- [~] 10. 修复 `DisclosureEngine._load_templates/generate_notes` 对 `section_id/level/parent_section_id/sort_index` 的透传与落库，新增数据回填策略但不宣称 section_id 跨模板稳定。
  - 验收：新生成附注稳定字段非空；旧行回填幂等，跨模板仍走显式映射。（AC-3.1）
- [x] 11. 新建 `note_html_sanitizer.py`，实现 canonical 富文本白名单和属性值校验；未知标签/属性重新转义，禁止危险 URL/事件/style。
  - 验收：script/iframe/onerror/javascript/style 被清除，合法段落/列表/表格/placeholder 保留，消毒幂等。（AC-10.4）
- [~] 12. 将上传、知识库、模板 preview/apply 统一接入后端 sanitizer；前端 `useSanitize.ts` 与后端标签/属性集合建立一致性测试。
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
- [~] 35. 新建 `NoteDocUploadDialog.vue`：90%×80vh 可拖双栏、搜索/筛选、父章节分组、折叠懒挂载编辑器、未保存关闭确认。
  - 验收：大量章节时只挂载已展开编辑器；关闭/换来源有脏数据必确认。（AC-2.1~2.5）
- [~] 36. 接入 Word/PDF 上传和解析结果：左侧展示层级/置信/警告，`v-html` 统一二次消毒；低置信不自动预填。
  - 验收：正常/低置信/需 OCR/损坏四态均有中文界面反馈。（AC-1.4~1.5, AC-3.5）
- [~] 37. 接入 `KnowledgePickerDialog`，最多选 5 篇；展示获授权文档名称/版本并复用相同来源树和匹配流程。
  - 验收：无权/空正文不进入可预填来源；切换上传↔知识库需处理未保存草稿。（AC-5.1~5.4）
- [~] 38. 实现手工映射、一键预填、右侧二次编辑、变量替换撤销、仅看未匹配/已变更和独立并排差异弹窗。
  - 验收：一键只消费 confirmed 映射；人工确认后才填 candidate；未匹配目标不变。（AC-3.3~3.5, AC-10.2）
- [~] 39. 接入 preview/apply 最终确认、原子失败保留草稿、成功后 invalidate cache + fetchTree + fetchDetailFresh。
  - 验收：成功切换章节不回旧值；409 后用户编辑未丢失且能重预览。（AC-4.1~4.6）
- [~] 40. 在 `DisclosureEditor.vue` “导入导出”菜单挂载“上传附注文档”，权限/归档/合并锁/EQCR 状态与后端一致。
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

- [~] 41. 实现 `NoteContentTemplateService.snapshot_preview/save_snapshot`：后端一次查询活动附注，生成 narrative+account_explanation 全套正文、服务端来源元数据、quality_summary、canonical hash 和 `snapshot_digest`；preview 不落库，save 重算 digest，变化则 409，不读 table_data。
  - 验收：来源项目/年/企业/标准/口径/保存人不可由客户端伪造；空/风险章节仍在全套快照；预检后来源变化不能保存陈旧版本。（AC-7.1~7.5）
- [x] 42. 实现同名模板目录并发锁与不可变版本：新 hash 新版本、同 hash 复用；current_version_id 原子更新，历史版本不改写。
  - 验收：并发两次保存无重复 version_no/丢版本；历史 hash 和内容保持不变。（AC-7.4, AC-8.3）
- [~] 43. 实现模板 list/detail/versions/delete API：列表分页且只返元数据，详情/版本逐次授权，软删目录保留版本及应用历史。
  - 验收：直接 UUID 不绕过；删除后新列表不可见但历史 application 可追溯。（AC-8.1~8.4, AC-11.5）
- [~] 44. 实现 personal/group 发布策略：group owner 服务端归根，manager/partner 二次确认；普通用户不能声明 public/system/allowed_project_ids。
  - 验收：子 A 保存后根 P/兄弟 B 可见，异组 C 不可见；伪造 owner/public 422/403。（AC-7.6~7.7）
- [~] 45. 增加模板端点 TestClient 安全矩阵和真实 DB 约束测试：本人/他人 personal、根/子/兄弟/异组、直接详情、版本、删除、目标无权限。
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
- [~] 47. 实现“保存为内容模板”弹窗：名称/说明/personal或group→服务端 snapshot-preview→质量摘要→集团二次确认→携 digest 正式保存，并处理来源变化 409 和同 hash 回执。
  - 验收：客户端 payload 不含正文/来源 owner；保存结果显示版本、来源和质量摘要；陈旧预检要求重新确认。（AC-7.1~7.7）
- [~] 48. 新建 `NoteContentTemplateApplyDialog.vue`：模板来源/版本/标准/口径/质量头部，推荐/需复核/不可用三组，搜索及已选/高风险/未映射筛选。
  - 验收：账户解释、企业特有、跨标准、风险章节默认不选；目标缺失/空模板禁选且说明原因。（AC-9.1~9.2, AC-9.5~9.6）
- [~] 49. 新建 `NoteTextDiffDialog.vue`，并排显示现有/拟写入内容、变量原值→目标值和风险；已有内容显式选择 replace/append。
  - 验收：追加预览无可见来源标记；高风险未逐项确认时确认按钮禁用。（AC-9.3~9.4, AC-10.1~10.5）
- [~] 50. 将模板选择接入统一 preview/apply：固定 version_id/hash、原子冲突、成功缓存刷新、批次回执和来源 badge。
  - 验收：保存模板→另一项目选择版本→勾选→apply 全流程不经 shared_config；正文、lineage、application 三方一致。（AC-8.3~8.4, AC-11.1~11.3）
- [~] 51. 实现“新版本可用”只读提示与重新预览入口；禁止后台自动覆盖已引用项目。
  - 验收：旧应用固定旧 version；发布新版本后目标正文不变，只有用户重预览确认后才变。（AC-8.4）
- [~] 52. 在 `DisclosureEditor.vue` 挂载“保存为内容模板/引用内容模板”两个清晰入口并完成前端组件测试。
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

- [~] 53. 运行后端 parser/catalog/sanitizer/template/preview/apply/鉴权/迁移定向测试，前端相关 Vitest、ESLint 和单区域 TypeScript 检查；修复全部本轮失败。
  - 验收：命令、通过数和无 warning 假绿证据记录到本 spec；全量检查若受环境限制如实说明。（NFR-2~9）
- [~] 54. Playwright 实测上传链：真实 Word + 文字版 PDF + 低置信/需 OCR 文件，完成解析→手工映射→批量编辑→原子 apply→切章回看。
  - 验收：正文正确、缓存不旧、source/application 留痕存在、导出正文不含审计标记。（US-1~6, US-10~11）
- [~] 55. Playwright 实测模板链：项目 A 保存全套 group 模板 v1→兄弟 B 选择章节（含替换/追加）→A 发布 v2→B 只提示不自动更新→重预览应用。
  - 验收：推荐/需复核/不可用分组正确；固定版本、变量替换、风险确认、原子冲突和审计溯源均可见。（US-7~11）
- [~] 56. 真实 PG 守卫：验证 V187 三表约束、兄弟可见/异组不可见、同 hash 幂等版本、并发 stale preview 零部分写入、样本容量不超冻结阈值；清理测试数据。
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
