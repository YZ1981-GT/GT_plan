# 任务清单：知识库上传健壮性与下游消费方接线

> 需求：#[[file:.kiro/specs/knowledge-upload-robustness-and-consumer-wiring/requirements.md]]
> 设计：#[[file:.kiro/specs/knowledge-upload-robustness-and-consumer-wiring/design.md]]
> 纪律：每个任务开始前现读相关文件（工作树有并发会话改动）；标完成必须有代码与测试证据；
> 改带自动保存页面的前端源码前浏览器先停 `about:blank`；探针 `_` 前缀用完即删。

- [x] 1. 基线：改动前跑知识库相关后端 / 前端测试集，记录预存红（逐条归因，不算本 spec）
  - 后端 30 文件 385 例 = 383 过 / 2 红：`test_knowledge_index.py::test_service_instantiation`（断言 `service.db`，现为 `self._db`）、`::test_chunk_text`（调类方法 `_chunk_text`，现为模块级函数）——测试过期，与本 spec 无关
  - 前端 5 文件 68 例全绿
  - _需求：8.1_

- [x] 2. ORM 清洗与类型规范化
  - [x] 2.1 `normalize_file_type`（纯函数，列宽常量 `FILE_TYPE_MAX_LEN` / `DOCUMENT_NAME_MAX_LEN` 由列定义直接引用）
  - [x] 2.2 `KnowledgeDocument`（name / content_text / content_summary / tags / index_error）与 `KnowledgeFolder`（name / description）NUL validator
  - _需求：2.1, 2.2_

- [x] 3. 上传写路径
  - [x] 3.1 `decode_text_bytes`（BOM → UTF-16 启发式（比例 + 绝对下限 4 个 0 字节）→ 严格 UTF-8 → 合法多字节 ≥ 4×替换符保留 UTF-8 → GB18030 → 替换解码），txt / md / csv 走它
  - [x] 3.2 每文件 SAVEPOINT（`_insert_document_isolated`）+ 写库失败删盘 + commit 失败删本请求全部已落盘文件 + `failed[{filename, reason}]`（SQLSTATE → 中文原因，不回显 SQL）；文件名 > 500 字直接进 `failed`；落盘名按 UTF-8 字节截断并替换 Windows 非法字符
  - _需求：1.1–1.3, 3.1_

- [x] 4. 后端测试
  - [x] 4.1 纯函数 `test_knowledge_text_decode.py`（**34** 例，含 PBT `max_examples=5`；勘误：本条首次记作 35，2026-10-01 收尾时 `--collect-only` 现算为 34，逐个参数化组合复数也是 34 ⇒ 首记数错，以现算为准）
  - [x] 4.2 真库 scratch `test_knowledge_upload_robustness_pg.py`（14 例）：混批 5 文件 / NUL / 超长类型名 / 编码样本 / 空白正文回执与列表 `has_text` 同口径 / 两种故障形态 × 现行与旧实现；反向对照：旧 flush 形态 500 整批丢、旧 execute 形态 200 但静默全丢 + 孤儿文件、绕过 ORM 写 NUL 被 PG 拒
    - 🔴 真库守卫抓到真缺陷：UTF-16 启发式只按比例判，19 字节含 1 个 NUL 的 UTF-8 被误判 → 补绝对下限
    - 🔴 Task 8 抓到守卫自身缺陷：故障注入原本替换 `_insert_document_isolated` 为测试里的 SAVEPOINT 拷贝 ⇒ 删生产 `begin_nested` 仍全绿（M1 SURVIVED）；改为 service 层注故障 + `production_path` 自检后 M1 KILLED
  - [x] 4.3 既有上传 / 授权用例回归：32 文件 432 例 = 430 过 / 2 红（同基线预存两条）
  - _需求：1.4, 2.3, 3.2, 8.1_

- [x] 5. 附注 AI 接知识库
  - [x] 5.1 删 query 版 `ai/complete`；续写 / 改写加 `knowledge_doc_ids`（≤5）+ `_load_selected_knowledge`（`load_documents` 逐篇判权，空正文不计，6000 字预算按篇均分）+ `knowledge_count` + `require_project_access("readonly")`
  - [x] 5.2 端点测试 `test_note_ai_knowledge_context.py`（12 例）：body 版可达、可见注入 / 不可见跳过、无正文不计、预算均分、非成员 403、query 形态 422
  - [x] 5.3 重复路由棘轮 `test_duplicate_route_registration_baseline.py`（5 例，基线 10 组只许减）；平台鉴权棘轮 `_IDENTITY_ONLY_BASELINE` 227 → 224（现算）
  - _需求：6.2–6.5, 7.1_

- [x] 6. 前端接线
  - [x] 6.1 `apiPaths.knowledge` 只留 `libraries`、`projects.knowledge` 删除；`useKnowledge` 改 `P_kl.search` / `P_kl.documentPreview`；守卫 `test_frontend_knowledge_paths_exist.py`（6 例，KnowledgeBasePanel 零挂载死链 5 条登记且可伪证）
  - [x] 6.2 `useNoteAi` / `commonApi` 传 `knowledge_doc_ids`，按 `knowledge_count` 提示（0 篇 warning、部分可用说明实际篇数）
  - [x] 6.3 审计报告编辑器「📚 知识库」标开发中，删无效的选择器挂载与「已加载 N 篇」
  - [x] 6.4 A17-3 成功回调显示 `failed[0].reason`、`on-error` 解析 `message / detail`
  - vitest：`useKnowledge.spec.ts`（8）、`composables.spec.ts` 追加 useNoteAi 知识库用例；🔴 顺带修 vitest 陷阱 `beforeEach(() => spy.mockReset())`（表达式体把 spy 当 teardown 返回），全仓同类 3 处
  - _需求：4.3, 6.1, 6.5, 6.6, 7.2_

- [x] 7. 知识库页面
  - [x] 7.1 `utils/knowledgeUpload.ts`（`readAllEntries` 读尽 + `collectFromEntries` 按 `fullPath` 保留层级 + 跳过系统临时文件）接入拖拽；相对路径经 WeakMap 旁存（`webkitRelativePath` 只读）
  - [x] 7.2 结束汇总 `ElNotification`（不自动关闭）逐条列失败原因、「未提取到正文」、子文件夹失败、已跳过临时文件；通知正文样式**内联**（`h()` 在渲染上下文外调用无 scopeId，scoped 规则匹配不到）；列表 `has_text=false` 行标「未提取到正文，AI 无法引用」；XHR 接 `ontimeout`（旧实现超时整批卡死）；重开弹窗重置跳过计数；`accept` 补 `.xlsm/.csv/.ppt`
  - [x] 7.3 vitest：`knowledgeUpload.spec.ts`（34）+ `KnowledgeBase.deepLinkAndGating.spec.ts`（21，新增 4）+ `GtA173ConsultationRecord.spec.ts`（15，新增上传结果 2）；前端 11 文件回归 161 例 = 160 过 / 1 红（`FrontendReferenceIntegrity`：`components.d.ts` 被并发会话临时 `_head_*.vue` 自动登记，HEAD 无、磁盘无，非本 spec）
  - _需求：4.1, 4.2, 5.1–5.3_

- [x] 8. 变异证明：20 条全部 KILLED，每条还原后 sha256 与变异前一致，失败形态逐条核对为预期形态（无变异基线：后端 65 例 / 前端 100 例全绿）
  - M1 去 SAVEPOINT → flush 形态 500、execute 形态只存 1 个 · M2 NUL validator 原样 → PG `CharacterNotInRepertoireError` · M3 file_type 不判列宽 → 「名称或类型超出长度限制」 · M4 去 GB18030 → GBK 乱码 · M5 恢复 query 版 → 续写 422 + 重复路由守卫 · M6 不判权直查 → 注入 5 篇（应 2） · M7 readEntries 一次 → 100/250
  - 补充：M8 列表 `has_text` 不去空白 · M9 回执 `text_extracted` 不去空白 · M10 UTF-16 去绝对下限 · M11 写库失败不删盘（孤儿） · M12 commit 失败不清理（仅旧实现对照可达） · M13 通知去内联样式 · M14 不重置跳过计数 · M15 不接 ontimeout · M16 忽略 fullPath（结构压平） · M17 丢后端 failed 原因 · M18 请求体不带 `knowledge_doc_ids` · M19 / M20 A17-3 丢原因
  - _需求：8.2_

- [x] 9. Playwright 真栈复测 + 测试数据清理（2026-10-01，真实 Chromium + 真后端 9980 + 真 PG）
  - 🔴 实测前环境故障：health 503 / 登录 500。根因 = Docker Desktop vpnkit 端口转发陈旧（宿主日志 `tcp forward from 0.0.0.0:6379 to 172.22.0.2:6379: connection refused`，而 `audit-redis` 实际是 172.22.0.4；Docker 重启后容器 IP 重排、转发表未更新；PG 转发正常）。Redis 本身 PONG、2948 key。处置 `docker restart audit-redis`（DBSIZE 前后均 2948）→ health 200、登录 200。另登记范围外缺陷：`auth_service.login` 在 `get_redis` 返回 `None` 时直接 `redis.get` → `AttributeError` 500（「Redis 降级」只在 deps 黑名单检查生效，登录 / refresh / logout 无降级，属 auth 域）
  - ① 9 个问题文件经 UI 一次上传（GBK txt / GBK csv / UTF-16 带 BOM / UTF-16 无 BOM / UTF-8-BOM / 含 NUL / 「扩展名」超长 / 空白 / 扫描 PDF）：**全部入库**（旧实现整批 500）；预览逐字正确、无 NUL / BOM / 替换符；超长扩展名 `file_type=null`；汇总通知 warning 型、不自动关闭，正文 computed `max-height: 240px; overflow-y: auto`（内联样式生效）
  - ② CDP `Input.dispatchDragEvent` 真实拖入目录：「2 个文件 2 个子文件夹 · 已跳过 3 个系统临时文件」（`~$` 锁文件 / `.DS_Store` / `__MACOSX/`），上传后建出 `_kb_drop/子目录A`、文件各进各的目录；重开弹窗不残留「已跳过」
  - ③ `page.route` 把首个上传拦成后端逐文件容错回执（200 + `failed[]`）→ 通知「上传完成：1 成功，1 失败 ✗ _kb_t9_fail.txt：文件内容含无法存储的字符」，第 2 个真入库
  - ④ 附注编辑器（「一、1」查看模式）「📚 知识库」选取器搜「函证程序」命中 GBK / UTF-16 / UTF-8-BOM 文件（显示 `folder_path` 与片段）
  - ⑤ UI 续写：请求体 keys = `knowledge_doc_ids / section_number / text / year`（无 `knowledge_context`），选 GBK + 扫描件 → `knowledge_count=1`、提示「续写完成（参考了 1/2 篇文档）」；附注「一、1」DB 快照 sha256 `099918947cf5c343` / `updated_at` 前后一致（未写库）
  - ⑥ fetch 直调：complete / rewrite 200 + `knowledge_count=2`（3 选 2，扫描件不计）· query 版 422 · 6 个 ID 422
  - ⑦ 审计报告页「📚 知识库（开发中）」点击给说明、不开选择器
  - ⑧ **用户原诉求**：选中文件夹 → 新建文件夹（位置默认当前文件夹、建后自动选中）→「上传到此文件夹」docx + xlsx → 两份 `has_text=true`、预览为文本、搜「回函金额」命中且 `folder_path` 指向新文件夹
  - 🔴 **实测抓到 R4.2 未达标并已修**：旧文案对**所有**无正文文件都说「扫描件需开启 OCR」——空白 txt、扩展名不规范的文件也被叫去开 OCR，而后端抽正文链只有 PDF 会走 MinerU OCR（R4.2 要求「区分扫描件」）。修 = `utils/knowledgeUpload.ts` 新增 `isLikelyScannedPdf` / `noTextHint`（按 `file_type` 优先、扩展名兜底判 PDF），列表标记与结束汇总分两类提示；vitest +12 例（`knowledgeUpload.spec.ts` 34→46：判定参数化 9 + 文案 1 + 汇总分类 / 分类折叠 2；`KnowledgeBase.deepLinkAndGating.spec.ts` 仍 21 例，列表用例改为扫描件 PDF 与空白 txt 双行对照）；变异 M21 判定恒真 / M22 汇总不分类 / M23 列表回到固定文案 → 全 KILLED、还原 sha256 一致；eslint 0 error；单区域 vue-tsc 0 错误（配故意类型错误的探针证明该配置确在做检查：TS2322 + TS6133 均报出）；**真浏览器复测**：扫描件 PDF「⚠ 未提取到正文（扫描件需 OCR），AI 无法引用」、空白 txt「⚠ 未提取到正文，AI 无法引用」（title 不含 OCR）、有正文 txt 无标记，汇总通知两行分开
  - 清理：测试文件夹「复现测试_上传」fc29490e 及子树（4 文件夹 / 20 文档 / 25 物理文件，含旧实现留下的 5 个孤儿文件）与「_kb_r42复测」60f1ba1a（1 / 3 / 3）均经产品端点 `DELETE /folders/{id}` 递归软删 + 删物理文件 + 删空目录；删除前核对子树外引用 0、`knowledge_index` 0 行；用户文件夹「1」不在子树内、前后均 0 文档
  - _需求：4.2, 8.3_

- [x] 10. INDEX.md / memory.md 更新；探针删除
  - 最终回归（2026-10-01）：后端 35 个知识库 / RAG / note_ai / 鉴权 / 守卫相关文件 434 例 = 430 过 / 4 红，逐条归因均非本 spec：`test_knowledge_index.py` ×2 = 基线预存；`test_committed_code_imports_only_committed_modules::test_no_completed_spec_has_an_uncommitted_deliverable` = 并发会话 workpaper_sync 的未入库测试（该守卫只扫 workpaper_sync 两个目录）；`test_lazy_import_resolvability::test_checkout_dependent_entries_are_really_unresolved_on_head` = 并发提交 `4e3478686` 已入库 `phase5_d3_04..07` 而棘轮表未缩短
  - 前端 23 文件：R4.2 修正前 540 例 = 539 过 / 1 红；**修正后终版复跑 552 例 = 551 过 / 1 红**（+12 = R4.2 新增用例）。唯一红仍是 `FrontendReferenceIntegrity`：`components.d.ts` L14-16 被 vite 自动登记了并发会话的 `_head_*.vue` 临时文件（HEAD 0 处、磁盘无文件），非本 spec
  - eslint 18 文件 0 error，10 warning 逐行比对 HEAD 全部预存；单区域 vue-tsc（`noUnusedLocals`）未崩溃：本 spec 改动文件内的 TS 错误或 HEAD 已存在，或来自同文件里并发会话的 sync-bridge 改线段（`GtA173ConsultationRecord.vue` 的 `handleOOFallback` / `flushPendingSave` / `refreshData`），本 spec 未新增
  - 全仓触类旁通：后端无按带点 / 大写比较知识库 `file_type` 的代码与测试；续写 / 改写无其他调用方（`test_e2e_audit_flow` 9c 用 JSON body）；前端 / e2e 无已删函数与死路径引用
  - 探针 `_kb_*` 共 60+ 个全部删除（保留共享夹具 `tests/_kb_pg_scratch.py` / `tests/_kb_mock_session.py`）；临时 tsconfig 已删
