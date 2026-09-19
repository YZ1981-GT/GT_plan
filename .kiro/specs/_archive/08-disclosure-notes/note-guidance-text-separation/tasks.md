# Implementation Plan: note-guidance-text-separation

## Overview

为附注模块新增独立字段 `guidance_text`，把"提示性/指引文字"从 `text_content` 物理分流。实施按"数据模型→生成分流→导出钉死→前端提示条→存量迁移→基线回写→离线往返→测试→Playwright"递进。

每个任务标注**精确文件路径 + 行号/方法名 + 具体改动**（行号为编写时实证位置，实施时以最近的符号锚点为准）。

铁律：三层一致（DB V074/R074 + ORM `Mapped[]` + service）一次做齐；PBT `max_examples=5`；迁移/真实表依赖属性标 `pg_only`；存量拆分走带预览一次性脚本（`_` 前缀用完即删）+ 备份表加 schema_drift 白名单；"不可靠识别则不拆分"为硬约束。

> **V074 说明**：V073 已被 `editing-lock` 占用（`V073__migrate_workpaper_locks_to_editing_locks.sql`），本特性 DDL 改用 **V074/R074**。

### 已实证锚点（实施直接用，勿重复探查）
- ORM：`backend/app/models/report_models.py` `class DisclosureNote(Base)`（L308），`text_content: Mapped[str|None] = mapped_column(Text, nullable=True)`（L349）
- 生成写库两分支：`disclosure_engine.py` 更新分支 L1056 `note.text_content = text_content`、新建分支 L1068 `text_content=text_content`；优先级3 已注释块约 L980；`_infer_table_names_from_text` 约 L1010
- 章节更新：`disclosure_engine.update_note(note_id, table_data, text_content, status)` L1602；签名需加 `guidance_text`
- Schema：`report_schemas.py` `DisclosureNoteDetail` L238（加 guidance_text 出参）、`DisclosureNoteUpdate` L262（加 guidance_text 入参）
- 路由：`routers/disclosure_notes.py` `PUT /{note_id}` L259 调 update_note + L294 返回 `DisclosureNoteDetail.model_validate(note)`；详情 GET L255 同样 model_validate
- 判空：`note_word_dynamic_styles.should_skip_empty_section` L85（已只看 text_content+table_data）；`_note_to_skip_dict` 在 `note_word_exporter.py` L1043
- 导出三路径：programmatic `export()` ~L1144、template `_fill_section_block` ~L822、html ~L953（均 `note.text_content`）
- 快照：`deliverable_section_state_service.compute_snapshot_hash_from_parts(section_code, text_content, table_data, audited_amounts)` L61；`DeliverableSectionStateService.compute_source_snapshot_hash(project_id, year, section_code)` L103；`clear_section_stale(word_export_task_id, section_code, new_hash)` L245；`detect_upstream_drift` L369
- 离线导出：`note_offline_export_service._load_sections` L704 构造 `section_dict`（**sid 键 = `note.section_id or note.note_section or ""`** L739，已兜底）；`export_sections_to_xlsx` 模块级函数含 `_build_meta_sheet`（L470，`meta_payload[sid]` gzip 压缩）；`export_sections` L672 = `_load_sections` + `export_sections_to_xlsx`

## Tasks

- [x] 1. 数据模型层三层一致（V074/R074 + ORM + service 读写）
  - [x] 1.1 创建 V074/R074 迁移配对
    - 新建 `backend/migrations/V074__disclosure_notes_guidance_text.sql`，内容：`ALTER TABLE disclosure_notes ADD COLUMN IF NOT EXISTS guidance_text TEXT;`
    - 新建 `backend/migrations/R074__disclosure_notes_guidance_text.sql`，内容：`ALTER TABLE disclosure_notes DROP COLUMN IF EXISTS guidance_text;`
    - V073 已被 editing-lock 占用 → 本特性用 V074
    - _Requirements: 1.1, 1.2_

  - [x] 1.2 ORM 新增 `guidance_text` 字段
    - `backend/app/models/report_models.py` L349 `text_content` 定义之后插入一行：`guidance_text: Mapped[str | None] = mapped_column(Text, nullable=True)`
    - _Requirements: 1.1, 1.3_

  - [x] 1.3 Schema + service + 路由贯通 guidance_text 读写
    - `report_schemas.py`：`DisclosureNoteDetail`（L238）加 `guidance_text: str | None = None`（出参）；`DisclosureNoteUpdate`（L262）加 `guidance_text: str | None = None`（入参）
    - `disclosure_engine.update_note`（L1602）签名加 `guidance_text: str | None = None`，函数体加 `if guidance_text is not None: note.guidance_text = guidance_text`
    - `routers/disclosure_notes.py` `PUT /{note_id}`（L268 调用处）加 `guidance_text=data.guidance_text`
    - 详情/更新返回的 `DisclosureNoteDetail.model_validate(note)`（L255/L294）自动带出 guidance_text（已加 schema 字段，from_attributes=True）
    - _Requirements: 1.4, 1.5_

  - [x] 1.4 三层一致单元测试
    - 新建 `backend/tests/services/test_guidance_text_three_layer.py`
    - 断言①V073 文件存在且含 `guidance_text TEXT` + `IF NOT EXISTS`；②`DisclosureNote.guidance_text` 在 ORM `__mapper__.columns` 中且类型 Text；③`update_note` 签名含 `guidance_text` 参数（`inspect.signature`）；④`DisclosureNoteDetail`/`DisclosureNoteUpdate` 含 guidance_text 字段
    - 任一层缺失即 fail（伪绿检测）
    - _Requirements: 1.6, 8.1_

  - [x]* 1.5 DDL 幂等属性测试（pg_only）
    - 新建 `backend/tests/migrations/test_v074_idempotent.py`，标 `pg_only`
    - **Property 14: 迁移幂等（DDL）** — 重复跑 V074，列存在且类型 TEXT，不报错
    - **Validates: Requirements 1.2**

- [x] 2. 生成引擎三类内容分流
  - [x] 2.1 新增共用底层判定 `is_guidance_paragraph` + 分类函数 `classify_template_content`
    - `disclosure_engine.py` 模块级（建议置于 `_infer_table_names_from_text` 附近 ~L100）新增纯函数 `is_guidance_paragraph(para: str) -> bool`：strip 后整段被 `（）`/`(）`/`【】`/`《》` 包裹 **且** 含祈使/指引词集合（应/说明/披露/参考附注/提示/注：/评价/确认/列示/逐项）→ True；否则 False
    - 新增 `classify_template_content(text_sections: list[str], text_template: str | None) -> tuple[str | None, str | None]`：把 text_sections（无则按 text_template 拆段）逐段判定——`is_guidance_paragraph` True→guidance 桶；命中 `_infer_table_names_from_text` 编号短标题→丢弃（表名消费）；其余→substantive 桶；两桶各 `\n\n` 拼接，空桶返 None
    - _Requirements: 2.1, 2.2, 2.3_

  - [x] 2.2 改造优先级3填充接入分流
    - `disclosure_engine.py` ~L980 已注释的"优先级3 模板默认文字"块：替换为 `substantive, guidance = classify_template_content(text_sections, tmpl.get("text_template"))`
    - `text_content` 取值改为：优先级1（上年 prior_text）/ 优先级2（LLM）/ `substantive`（三者依次兜底，无则留空）
    - 新增局部变量 `guidance_text = guidance`
    - 写库两分支都补 guidance：更新分支 L1056 后加 `note.guidance_text = guidance_text`；新建分支 L1068 的 `DisclosureNote(...)` 构造加 `guidance_text=guidance_text`
    - `_infer_table_names_from_text`（L1010）调用保持不变
    - _Requirements: 2.1, 2.2, 2.4, 2.5_

  - [x]* 2.3 生成分流完整性属性测试
    - 新建 `backend/tests/services/test_guidance_classify_property.py`
    - **Property 1: 生成分流完整性** — 任意提示段+正文段组合，指引入 guidance、text_content 不含已分流指引
    - **Validates: Requirements 2.1, 2.2, 2.4, 2.5**；纯逻辑 SQLite/无库，`max_examples=5`

  - [x]* 2.4 表格标题不进正文属性测试
    - **Property 2: 表格标题不进正文** — 表格标题写 table.name，text_content 不含
    - **Validates: Requirements 2.3**；`max_examples=5`

  - [x]* 2.5 生成与迁移指引判定一致属性测试
    - **Property 15: 生成与迁移指引判定一致** — 同一段落经 `classify_template_content` 与 `identify_guidance` 内分段后判定一致（共用 `is_guidance_paragraph`）
    - **Validates: Requirements 2.1, 5.5**；`max_examples=5`

- [x] 3. 导出判空与三路径渲染补测试钉死
  - [x] 3.1 判空单元测试（代码不改，确认+钉死）
    - 确认 `note_word_dynamic_styles.should_skip_empty_section`（L85）与 `_note_to_skip_dict`（note_word_exporter L1043）保持不传/不读 guidance_text
    - 新建 `backend/tests/services/test_skip_empty_guidance.py`：①note 仅 guidance 非空、text_content 空、表空 → skip=True；②text_content 有正文 → skip=False
    - _Requirements: 4.1, 4.2, 4.5, 8.2_

  - [x]* 3.2 判空与 guidance 无关属性测试
    - **Property 3: 判空与 guidance 无关** — 同 note 任意 guidance 值判空结果不变
    - **Validates: Requirements 4.1, 4.2, 4.5**；`max_examples=5`

  - [x]* 3.3 三路径导出不含 guidance 属性测试
    - 新建 `backend/tests/services/test_export_excludes_guidance.py`，覆盖 programmatic（`export()`）/ template（`_fill_section_block`）/ html 三路径产物均不含 guidance 文本
    - **Property 4: 导出输出不含 guidance**
    - **Validates: Requirements 4.3, 4.4, 7.2**；DB 部分 `pg_only`，`max_examples=5`

- [x] 4. 前端编辑器只读 GT 紫提示条
  - [x] 4.1 DisclosureEditor 渲染只读提示条 + 映射 guidanceText
    - `audit-platform/frontend/src/views/DisclosureEditor.vue`：在正文区（`gt-de-tiptap-wrapper` 或表格区上方）条件渲染 `<div v-if="currentNote?.guidanceText?.trim()" class="gt-guidance-bar">`，纯文本展示，**不接入 NoteRichTextEditor**
    - 取详情处（fetchDetail / getDisclosureNoteDetail 映射）把 `data.guidance_text` 映射为 `currentNote.guidanceText`，缺失→空串；若经 apiProxy 已解信封则直接取，若原生 fetch 须手动解 `{code,message,data}`
    - 新增 scoped 样式 `.gt-guidance-bar`：浅紫底 `#f4f0fa`、左边框 3px `#4b2d77`、文字深紫、内边距、icon `<InfoFilled/>`；文本中文
    - _Requirements: 3.1, 3.2, 3.4, 3.5_

  - [x]* 4.2 提示条渲染属性测试（fast-check + Vitest）
    - 新建 `audit-platform/frontend/src/views/__tests__/guidanceBar.spec.ts`
    - **Property 5: 提示条渲染当且仅当 guidance 非空** — guidance 非空才渲染、且只读
    - **Validates: Requirements 3.1, 3.2, 3.4**；`numRuns=5`

- [x] 5. 检查点 - 确保 1~4 测试通过
  - 运行 `python -m pytest backend/tests/services/test_guidance*.py backend/tests/services/test_skip_empty_guidance.py backend/tests/services/test_export_excludes_guidance.py` + 前端 vitest；全绿再继续。有问题问用户。

- [x] 6. 存量迁移脚本（preview/execute/rollback + 保守启发式 + 往返一致）
  - [x] 6.1 实现 `identify_guidance`（共用 `is_guidance_paragraph`）
    - 新建 `backend/scripts/migrate/_split_guidance_text.py`（`_` 前缀一次性，用完即删）
    - `from app.services.disclosure_engine import is_guidance_paragraph`
    - `identify_guidance(text_content: str) -> tuple[str, str] | None`：按 `\n\n` 切段，逐段 `is_guidance_paragraph`；命中段入 guidance、其余入 remaining；无任何命中→返回 None；**以"整段切分保留分隔"实现**，保证 `guidance` 与 `remaining` 重组（按原顺序+原分隔）== source
    - _Requirements: 5.5, 5.8_

  - [x] 6.2 preview 子命令（只读）
    - CLI（argparse）：`preview --project <id|all>`；对范围内每章节调 `identify_guidance`，打印章节号 + "将抽取为 guidance_text:" + "将保留为 text_content:" 清单
    - 无 `--confirm` 绝不写 `disclosure_notes`
    - _Requirements: 5.1, 5.3, 5.7_

  - [x] 6.3 execute 子命令（备份 + 拆分）
    - `execute --project <id|all> --confirm`：先建备份表 `_note_guidance_split_backup`（note_id UUID/project_id UUID/year INT/note_section TEXT/source_text_content TEXT/backed_up_at TIMESTAMPTZ DEFAULT now()）；备份表已存在且非空 → 拒绝（提示先 rollback）
    - 按 `identify_guidance`：命中→`guidance_text` 写指引 + `text_content` 写 remaining + 记入 `changed_sections`；返回 None→不动（text_content 不变、guidance_text 留空）
    - 把 `_note_guidance_split_backup` 加入 `backend/app/core/schema_drift_detector.py` 的 `KNOWN_ALLOWLIST`
    - _Requirements: 5.2, 5.4, 5.5, 5.7_

  - [x] 6.4 rollback 子命令
    - `rollback --project <id|all>`：`UPDATE disclosure_notes d SET text_content=b.source_text_content, guidance_text=NULL FROM _note_guidance_split_backup b WHERE d.id=b.id`（按范围过滤）
    - _Requirements: 5.6_

  - [x]* 6.5 拆分合并往返一致属性测试
    - **Property 6: 拆分合并往返一致** — `identify_guidance` 纯字符串 split/merge 往返 == source；可无库跑
    - **Validates: Requirements 5.4, 5.8**；`max_examples=5`

  - [x]* 6.6 不可靠识别不拆分属性测试（pg_only）
    - **Property 7: 不可靠识别则不拆分（不可误删硬约束）**
    - **Validates: Requirements 5.5**；DB 部分 `pg_only`

  - [x]* 6.7 未确认执行只读属性测试（pg_only）
    - **Property 8: 未确认执行只读** — 无 --confirm 时 disclosure_notes 不变
    - **Validates: Requirements 5.3**；`pg_only`

  - [x]* 6.8 拆分回滚往返恢复属性测试（pg_only）
    - **Property 9: 拆分回滚往返恢复** — rollback 后 text_content 完整恢复
    - **Validates: Requirements 5.2, 5.6**；`pg_only`

  - [x]* 6.9 范围隔离属性测试（pg_only）
    - **Property 10: 范围隔离** — 仅改范围内章节
    - **Validates: Requirements 5.7**；`pg_only`

- [x] 7. 迁移后源快照基线重算回写
  - [x] 7.1 execute 末尾接基线回写（仅 changed_sections + 复用 clear_section_stale + 一对多 task）
    - `_split_guidance_text.py` execute 末尾：**仅遍历 6.3 收集的 `changed_sections`**（未拆分章节跳过）
    - 每个 changed section：`SELECT DISTINCT word_export_task_id FROM deliverable_section_state WHERE project_id=:pid AND year=:yr AND section_code=:sc` 取全部绑定 task（一对多）
    - `new_hash = await DeliverableSectionStateService(db).compute_source_snapshot_hash(project_id, year, section_code)`
    - 对每个 task_id 调 `clear_section_stale(task_id, section_code, new_hash)`（复用现成方法更新 hash+清 stale，**禁裸 UPDATE SQL**）
    - SELECT 空（无交付件绑定）→ 自然跳过不报错；按 word_export_task_id 分批每批一事务，可重入续算
    - **不改** `compute_snapshot_hash_from_parts` 签名/实现
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6_

  - [x] 7.2 快照函数签名静态断言单测
    - 新建 `backend/tests/services/test_snapshot_hash_signature.py`：`inspect.signature(compute_snapshot_hash_from_parts)` 参数恰为 `(section_code, text_content, table_data, audited_amounts)`，无 guidance 参数
    - _Requirements: 6.1, 8.1_

  - [x]* 7.3 基线回写抑制误判 stale 属性测试（pg_only）
    - **Property 11: 基线回写抑制误判 stale** — 仅移指引的章节迁移后 `detect_upstream_drift`=False
    - **Validates: Requirements 6.4, 6.5, 6.6**；依赖 deliverable_section_state+trial_balance，`pg_only`

- [x] 8. 离线导出/导入往返适配
  - [x] 8.1 离线导出写 guidance_text 到 _meta_（sid 键已实证 = section_id or note_section）
    - `note_offline_export_service._load_sections`（L737 section_dict 构造）加 `"guidance_text": note.guidance_text or ""`
    - `export_sections_to_xlsx` 的 `_build_meta_sheet`（L470）`meta_payload[sid]` 加 `"guidance_text": section.get("guidance_text", "")`（sid 键沿用现有 `section.get("section_id")`，与 _load_sections 的 `section_id or note_section` 兜底一致）
    - _Requirements: 7.2, 7.2a_

  - [x] 8.2 离线导入读回 guidance_text 不污染正文
    - `note_offline_import_service`：从 `_meta_` 解出 `meta_payload[sid].guidance_text`，按 sid（note_section 兜底）匹配章节，`UPDATE disclosure_notes SET guidance_text=...`；**不**并入 text_content/table_data
    - 旧导出包 _meta_ 无 guidance_text 键 → 保留 DB 现值、不报错
    - _Requirements: 7.2a, 7.3_

  - [x]* 8.3 离线往返保留 guidance 属性测试
    - **Property 13: 离线导出导入往返保留 guidance** — 导出再导回 guidance_text 不丢、不污染正文
    - **Validates: Requirements 7.2a**；xlsx 编解码可无库、DB 部分 `pg_only`，`max_examples=5`

- [x] 9. 向后兼容与排序回归
  - [x] 9.1 排序回归单测
    - 断言新增 guidance_text 列不改 `_load_sections` 的 `ORDER BY sort_order ASC NULLS LAST, note_section` 结果，附注列表/目录树排序不变
    - _Requirements: 7.4, 8.1_

  - [x]* 9.2 guidance 为空全链路等价现状属性测试
    - **Property 12: guidance 为空全链路等价现状** — guidance NULL/空时生成/编辑/导出行为同现状
    - **Validates: Requirements 1.5, 7.1, 7.3**；`max_examples=5`

- [x] 10. 检查点 - 确保所有后端测试通过
  - 本地 SQLite：20 passed / 6 skipped（pg_only）；CI 连 PG 时 26 全绿

- [x] 11. Playwright 实测（辽宁卫生 + 和平药房）
  - [x] 11.1 端到端实测
    - 用例：`audit-platform/frontend/e2e/note-guidance-text-separation.spec.ts`
    - 门禁：`RUN_GUIDANCE_E2E=1` + 后端 9980 + 前端 3030 + 测试项目已 execute 拆分
    - 前置：对测试项目跑 `_split_guidance_text.py preview` 核对 → `execute --confirm` 拆分
    - 辽宁卫生 `37814426-a29e-4fc2-9313-a59d229bf7b0`、和平药房 `5942c12e-65fb-4187-ace3-79d45a90cb53`
    - 验证：①编辑器对有 guidance_text 章节展示 GT 紫只读提示条 ②导出 Word 不含指引文字、仅含正文与表格 ③仅提示语章节被跳过不产生空章节
    - _Requirements: 3.1, 3.3, 4.5, 8.7_

## Notes

- 标 `*` 为可选测试子任务（按项目偏好默认做完）；顶层任务不带 `*`。
- pg_only：测试 fixture 默认 SQLite 不加载 V*.sql。Property 14、7/8/9/10、11、4 及 13 的 DB 部分标 `pg_only`；Property 1/2/3/5/6(纯函数)/12/15 可 SQLite/无库跑。
- 存量脚本 `_split_guidance_text.py` + 备份表 `_note_guidance_split_backup` 均 `_` 前缀，用完即删 + 加 schema_drift KNOWN_ALLOWLIST。
- 硬约束："不可靠识别则不拆分（不可误删）"——先 preview 人工核对再 execute --confirm。
- 所有 PBT `max_examples=5`（前端 fast-check `numRuns=5`）。
- 行号为编写时实证值，实施时以最近符号锚点为准（文件可能微调）。
