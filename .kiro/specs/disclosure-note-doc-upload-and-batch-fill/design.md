# 附注正文导入、批量编制与集团内容模板 — 技术设计

## §1 现状核验与问题边界

### 1.1 已验证事实

1. `DisclosureNote.text_content` 存富文本 HTML；`text/mixed/table` 三种类型都可能有正文。
2. 当前单章保存走 `PUT /api/disclosure-notes/{note_id}`；一次请求一次 commit，逐章调用不是原子批次。
3. `DisclosureEditor.vue` 有详情缓存；批量写后必须清缓存并强制刷新，否则会显示旧正文。
4. `SharedTemplatePicker.getConfigData` 是同步函数，无法等待全套章节网络快照；其 apply 只记引用，不真正写附注。
5. `shared_config` 路由只校验登录，直接 template UUID 可绕过列表可见性；子企业将自身 ID 作为 group owner 后，兄弟企业不可见。
6. `shared_config_templates.config_data` 是覆盖式可变 JSONB，整数 `config_version` 不保留历史内容，不能证明当时引用哪一版。
7. `GroupNoteTemplateBaseline` 有服务端快照/单事务写先例，但会处理 `table_data`、建章节并承担集团基线语义，不适合直接作为正文引用入口。
8. `section_id` 当前可空且标准生成链未完整落库；`note_section` 只在同模板内可靠；标题可能重名/改名。
9. `note_section_matcher` 明确禁止模糊匹配，并已有显式别名/禁止对；`note_template_variant_matrix` 是报表科目章节跨四变体映射真源。
10. 后端依赖为 `python-docx`、PyMuPDF、`pypdf`、MarkItDown；知识库正文权威读取入口是 `KnowledgeIndexService.load_documents`。
11. 后端尚无“保留安全富文本”的 HTML 白名单消毒器；前端已有 `useSanitize.sanitizeHtml`。
12. `GET /{project_id}/{year}/{note_section}` 是 catch-all；其后声明的三段静态 GET 会被吞掉。

### 1.2 本设计修复的核心矛盾

- “一次性填写”与“逐章独立提交、部分成功”矛盾 → 改为服务端原子批量 apply。
- “全套模板”与“只应默认引用通用政策”矛盾 → 全套保存，引用时按风险分组。
- “跨企业复用”与“来源企业特有信息泄漏”矛盾 → 确定性变量替换 + 风险标记 + 人工确认。
- “复用已有共享模板”与“现有链安全/版本语义不足”矛盾 → 新建附注专用领域模型，不扩散旧缺陷。

## §2 架构决策

### ADR-DNT-001：专用领域模型，不复用可变 shared_config 权威载荷

新增 `note_content_templates`、`note_content_template_versions`、`note_text_batch_applications`。可复用已有组件视觉样式，但不调用 `SharedTemplatePicker` 的保存/apply 逻辑。

### ADR-DNT-002：服务端生成全套快照

保存模板时客户端只提交项目、年度、名称、说明和 owner_scope。章节内容、来源企业、标准、口径、保存人和时间均由后端查询生成，避免 N+1、空 Promise 和伪造来源。

### ADR-DNT-003：确定性匹配，模糊结果不得自动应用

同变体用规范 section_code；跨变体用 variant matrix/显式 alias；外部标题只能精确归一或人工确认。禁止相似度阈值、关键词重合率和 LLM 决策映射。

### ADR-DNT-004：preview → apply 原子闭环

服务端 preview 计算消毒、替换、匹配、风险和目标 hash；apply 锁定全部目标并复核预期 hash。任一失败整体回滚；`X-Mutation-Id` 保证重试幂等。

### ADR-DNT-005：模板不可变版本，应用固定版本

同名再次保存创建新 version row；旧版本永久可追溯。应用记录绑定 `template_version_id + content_hash`，不自动随最新版漂移。

### ADR-DNT-006：溯源元数据不污染最终附注

来源、版本、模式、前后 hash 只写 application/template_lineage。追加正文不插入“引用自模板”等用户可见审计标记。

## §3 数据模型与迁移

新增 `V187__note_content_templates_and_batch_apply.sql` 与 `R187__rollback_note_content_templates_and_batch_apply.sql`。

### 3.1 `note_content_templates`（模板目录）

| 字段 | 说明 |
|---|---|
| id | UUID 主键 |
| name / description | 模板名称与说明 |
| owner_scope | `personal` / `group`；CHECK 约束 |
| owner_user_id | personal 所有者；group 时为空 |
| owner_group_project_id | 服务端解析的 canonical group root；personal 时为空 |
| current_version_id | 当前不可变版本指针 |
| is_deleted / deleted_at | 软删除 |
| created_by / created_at / updated_at | 审计字段 |

约束：
- personal：活动行 `(owner_user_id, lower(name))` 唯一；
- group：活动行 `(owner_group_project_id, lower(name))` 唯一；
- owner_scope 与两个 owner 字段的互斥 CHECK；
- 外键均显式 `ON DELETE RESTRICT/SET NULL`，历史引用不得级联丢失。

### 3.2 `note_content_template_versions`（不可变快照）

| 字段 | 说明 |
|---|---|
| id / template_id | 版本主键与模板外键 |
| version_no / schema_version | 模板内递增版本与载荷 schema 版本 |
| source_project_id / source_year | 来源项目和年度 |
| source_project_name | 保存时名称快照，项目后续改名不影响历史 |
| template_type / report_scope | 国企/上市与单体/合并口径 |
| sections_data | 全套正文快照 JSONB，不含 table_data |
| quality_summary | 空白、占位、stale、草稿、企业特有风险统计 |
| content_hash / byte_size | canonical JSON SHA-256 与字节数 |
| created_by / created_at | 保存人和时间 |

约束：`(template_id, version_no)` 唯一，`(template_id, content_hash)` 唯一。内容未变化时返回既有版本，不新增版本号。

`sections_data[]` 规范结构：

```json
{
  "source_note_id": "uuid",
  "section_id": "nullable-stable-id",
  "note_section": "四、金融工具",
  "section_title": "金融工具",
  "section_kind": "narrative|account_explanation|container",
  "parent_section_id": "nullable",
  "content_type": "text|mixed|table",
  "text_content": "<p>...</p>",
  "content_hash": "sha256",
  "status": "draft|confirmed|not_applicable",
  "is_stale": false,
  "quality_flags": ["source_entity_name", "placeholder_text"]
}
```

### 3.3 `note_text_batch_applications`（统一批量应用审计）

同时记录 upload / knowledge / content_template 三种来源：

| 字段 | 说明 |
|---|---|
| id | UUID 主键 |
| source_kind | `upload` / `knowledge` / `content_template` |
| template_version_id | 模板来源时必填 |
| source_metadata | 文件名/hash、知识库 doc/version 或其他只读来源摘要 |
| target_project_id / target_year | 目标项目与年度 |
| mutation_id / preview_digest | 幂等键与预览摘要 |
| applied_count / mode_summary | 写入数量及新增/替换/追加统计 |
| detail | 逐章 source/target/mode/before_hash/after_hash/变量替换 JSONB |
| applied_by / applied_at | 操作人和时间 |

约束：`(target_project_id, mutation_id)` 唯一；模板版本、项目、用户均有外键/索引。只有 commit 成功后才插入 `status=succeeded` 的应用记录。

### 3.4 ORM / schema 一致性

三个 ORM 使用 `Mapped[]`；Pydantic 对 owner_scope、source_kind、mode、section_kind 使用 Literal/Enum，禁止自由字符串。迁移、ORM、schema、service 四层字段必须由契约测试逐项对齐。

## §4 章节目录、分类与匹配

### 4.1 `NoteSectionCatalog` 扩展

新增服务端只读投影 `classify_note_section(template_type, report_scope, note_section)`：

1. 当前变体 section_code 命中 `note_template_variant_matrix`（含 parent_company_sections）→ `account_explanation`；
2. 模板节点有子节点且本身无正文载荷 → `container`；
3. 其余可编辑正文节点 → `narrative`。

端点返回 `section_id/parent_section_id/level/sort_index/section_kind`。基线用例至少锁定：
- `一、1 公司基本情况`、`四、会计期间` → narrative；
- 国企 `八、1` / 上市 `五、1` 货币资金 → account_explanation；
- 仅承载子节的顶层“重要会计政策” → container。

上传/知识库目标查询使用 `scope=narrative`；模板快照使用 `scope=all`。

### 4.2 匹配优先级

1. **目标行定位**：apply 永远使用目标项目内 `DisclosureNote.id`；
2. **同模板候选**：规范 `note_section` + 标题一致；
3. **跨模板科目章节**：`note_template_variant_matrix.account_key`；
4. **跨模板叙述章节**：`note_section_matcher.match_section` 的显式 alias，且先排除 `FORBIDDEN_MATCH_PAIRS`；
5. **外部来源**：层级路径 + 去空白后的标题精确匹配；
6. 其余返回 `manual_required`，前端由用户明确选择。

匹配结果包含 `match_kind`、`evidence`、`confidence=confirmed|candidate|manual_required`。只有 confirmed 默认参与一键预填；candidate 经用户点击确认后转为 manual。

## §5 文档与知识库解析

### 5.1 DOCX

`note_document_parser.py` 使用 python-docx + 底层 XML body 顺序遍历 `w:p/w:tbl`：
- Heading/GTNoteHeading/outlineLvl 为主；字体大小+加粗仅作候选；
- Word 自动编号通常不在段落文本中，不能要求标题正则必须含“一、”；
- 表格转安全 `<table><tr><th|td>`；段落 run 转 `<strong>/<em>`；
- 列表按 numId/ilvl 保留层级；不保留 Word class/style/XML 命名空间；
- zip entry 数、总解压字节、单 entry 字节设硬上限防 zip bomb。

### 5.2 PDF

PyMuPDF `page.get_text("dict")` 遍历 block→line→span：
- `span.size` 与 `TEXT_FONT_BOLD` 作为标题候选证据；
- 结合页面字号中位数、短行、上下间距和中文章节模式打解析置信度；
- 文字顺序按坐标重建，跨页保留段落；
- 仅有图像/无文本 span 返回 `needs_ocr=true`，本弹窗不自行 OCR；
- pypdf/MarkItDown 仅作纯文本降级，降级标题均标低置信并需人工确认。

> 第二轮复盘第 7 组修订：实现里从未接入 pypdf/MarkItDown。原「纯文本降级」分支挂在「主循环未产出章节」之后，而只要有可提取文本，主循环必产出章节（无标题正文进「（无标题）」人工确认章），该分支不可达，已删除——降级形态就是这个人工确认章。章节数超过上限时截断并告警（首版静默截断）。

### 5.3 知识库

`parse-knowledge` 接收最多 5 个 doc_id。先调用 `KnowledgeIndexService.load_documents` 完成项目模式授权，再解析返回的 Markdown/HTML/纯文本。无权 ID 与不存在 ID使用同一不可见语义；响应不得回显未授权文档元数据。

### 5.4 双重 HTML 消毒

后端新建 `note_html_sanitizer.py`，基于标准库 `HTMLParser` 实施最小白名单：
- 标签：`p/br/strong/em/ul/ol/li/table/thead/tbody/tr/th/td/h1-h5/blockquote/span/hr`；
- 属性：仅 `colspan/rowspan/data-placeholder/contenteditable`，以及值严格等于 `gt-note-placeholder` 的 class；
- 禁止任意 style/href、其他 class、事件属性、危险协议和未知标签；
- 所有文本/属性重新转义，输出 canonical HTML。

前端所有 `v-html` 及编辑器装载前再调用 `useSanitize.sanitizeHtml`，且前端允许列表与后端契约测试保持一致。

> 第 7 组：消毒点按出口收敛。文本来源（Markdown / HTML / 中文章节号 / 整篇降级）只在 `parse_text_source` 的单一出口消毒并剥平台模板标记；DOCX / PDF 各在返回前消毒，DOCX 超限截断后再消毒一次。写入以预览为准：来源先消毒再生成替换清单，替换后再消毒一次（纵深防御，属等价变异）；追加时现有正文与新内容两侧都消毒。每个出口都有「去掉即打红」的变异证据（tasks.md 第 7 组）。

## §6 API 与服务边界

新建独立 router `note_text_batch.py` 和 `note_content_templates.py`，登记到 `router_registry/report.py`。路径以 `/api/projects/{project_id}/...` 开头，避免 `disclosure_notes` catch-all 顺序冲突。

### 6.1 章节读取与来源解析

- `GET /api/projects/{project_id}/disclosure-note-text-sections?year=&scope=narrative|all&include_content=false`
  - readonly 权限；列表默认不返回正文；`include_content=true` 仅内部模板快照 service 使用，不向普通列表开放整包下载。
- `POST /api/projects/{project_id}/disclosure-note-import/parse-upload`
  - multipart；edit 权限；有界读取，扩展名 + MIME + 文件签名三重校验后返回 ParsedSource；
  - `source_metadata`（文件名/hash/字节数/格式）带服务端 HMAC 签名，绑定项目与解析人；preview/apply 验签，审计记录只用验签后的值。
- `POST /api/projects/{project_id}/disclosure-note-import/parse-knowledge`
  - JSON `{year, doc_ids}`；edit 权限 + 每篇知识库判权。

### 6.2 内容模板

- `POST /api/projects/{project_id}/note-content-templates/snapshot-preview`
  - body `{year,name,description,owner_scope}`；后端一次查询生成不落库快照摘要、质量统计和 `snapshot_digest`。
- `POST /api/projects/{project_id}/note-content-templates`
  - body `{year,name,description,owner_scope,snapshot_digest}`；后端重算全套快照，digest 不一致返回 409，匹配后才创建/复用不可变版本。
- `GET /api/projects/{project_id}/note-content-templates`
  - readonly；SQL 层过滤 personal 或 canonical group，列表只返回元数据/质量摘要。
- `GET /api/projects/{project_id}/note-content-templates/{template_id}`
  - readonly + 统一 `can_view_template`；不可见返回 404。
- `GET /api/projects/{project_id}/note-content-templates/{template_id}/versions`
  - 返回版本元数据，不默认返回 sections_data。
- `DELETE /api/projects/{project_id}/note-content-templates/{template_id}`
  - personal 仅本人；group 仅 canonical group 的经理/合伙人；软删除目录，不删版本/应用历史。

集团 owner 由服务端调用 lineage resolver 向上追溯到根项目，检测循环/缺失；客户端不能提交 owner_group_project_id。保存子企业 A 的 group 模板后，根项目 P 和同根兄弟 B 可见，异组 C 不可见。

### 6.3 统一预览与应用

- `POST /api/projects/{project_id}/disclosure-note-text-batch/preview`
  - body `{year, source, manual_mappings[], revoked_replacement_ids[]}`；source 为 upload parse result（原样回传 parse-upload 响应）/ knowledge parse result + `knowledge_doc_ids`（每次重新判权）/ `template_version_id + template_content_hash`（复核可见性与固定 hash）；客户端章节 metadata 只保留 `doc_id`；
  - 输出分类、映射证据、消毒后内容、变量替换、风险、目标 before_hash/updated_at、统计和 `preview_digest`。
- `POST /api/projects/{project_id}/disclosure-note-text-batch/apply`
  - body `{year, source, preview_digest, selections[], manual_mappings[], revoked_replacement_ids[]}`（后两项须与 preview 一致，否则重算结果对不上 digest）；header `X-Mutation-Id` 必填；
  - 服务端重新鉴权、重新判权/验签来源、锁行后重算 preview，比对 digest 与逐章 hash 后一次 commit；`selections[].proposed_html` 不使用（只写服务端重算结果）。

所有 service 只 flush。router 使用扩展后的 `DisclosureMutationCoordinator`：`event_factory` 支持返回事件列表，commit 后为每个变更章节发布 `NOTE_SECTION_SAVED`，并在任一事件失败时返回 warning 但不回滚已提交数据。

## §7 preview → apply 算法

### 7.1 Preview

1. 校验目标项目 edit、年份、来源可见性和 payload 上限；
2. 加载目标 `scope`（upload/KB=narrative，模板=all）；
3. 对来源 HTML 做后端 canonical sanitize；
4. 计算确定性章节映射；低置信结果只作为待人工映射项；
5. 解析目标段落变量，替换公司名/年度/报表期间/币种/金额单位；
6. 扫描来源实体名、地址、人名、日期、金额、占位文本、stale/draft 等质量风险；
7. 按 recommended/review/unavailable 分类；
8. 返回逐章 before/proposed 内容摘要与 hash、`preview_digest = SHA256(canonical preview inputs)`。

### 7.2 Apply

1. 校验 `X-Mutation-Id` 与请求指纹；
2. 校验每个 selection 属于本 preview、目标 note 属于 project/year；
3. 单条 SELECT ... FOR UPDATE 锁定全部目标，按稳定顺序排序防死锁；
4. 比较 expected_updated_at + before_hash；任一变化返回 409 `NOTE_BATCH_STALE_PREVIEW`，零写入；
5. 重新消毒并验证 proposed hash；
6. `replace` 直接写拟稿；`append` 仅用规范空段连接旧/新正文，并对完全相同段落去重，不写来源标记；
7. 每章设置 `status=draft`、`is_local_override=true`，追加 template_lineage（如有）；
8. 写 `note_text_batch_applications` 及逐章前后 hash，flush；
9. coordinator commit 后逐章发事件并缓存幂等响应。

### 7.3 并发和重试

- 用户预览后他人改过任一目标：整批 409，前端保留本地草稿并展示冲突章节，重新预览后再提交；
- 网络重试使用同 mutation ID；不同 payload 不得复用；
- 模板在预览后发布新版本不影响本次：apply 固定旧 `version_id + content_hash`；
- 上传来源内容由 apply 请求携带并受 preview_digest/大小/消毒复核，不信任浏览器。

## §8 模板快照、质量与变量

### 8.1 保存流程

1. 用户输入名称/说明并选 personal 或 group；
2. 调用 snapshot-preview：后端查 Project，解析 template_type/report_scope/year/集团根和服务端用户，一次查询全部活动 DisclosureNote；
3. 结合模板目录计算 section_kind，生成全套正文快照、quality_summary、canonical hash/byte_size 和 `snapshot_digest`，不写库；
4. 前端展示质量摘要；group 发布要求 `admin/manager/partner/signing_partner` 并二次确认；
5. 正式保存携带 snapshot_digest，后端重新查询并重算；来源已变化返回 409，不保存陈旧快照；
6. 在事务中锁模板目录，创建下一不可变 version 或复用同 hash 版本，更新 current_version_id。

### 8.2 风险分级

- `safe_policy`：同标准/口径、映射确定、目标为空、无风险 → 推荐；
- `entity_specific`：公司基本情况、治理/税收优惠/或有事项等企业特有内容 → 需复核；
- `account_explanation`：报表科目解释正文 → 需复核；
- `quality_warning`：源章 draft/stale/占位文本/疑似来源实体、日期、金额 → 需复核；
- `unusable`：空正文、目标缺失、映射冲突/禁止对 → 不可用。

风险分类只决定默认选择和提示，不删除全套模板中的章节。

### 8.3 变量替换

复用 `note_text_paragraph_vars.resolve_paragraph_vars` 的目标上下文。仅处理明确 token 和精确来源值：
- `{公司名称}`、`{年度}`、`{报表期间}`、`{币种}`、`{金额单位}` 等；
- 来源企业名称精确命中时可建议替换为目标企业名称；
- 地址、法定代表人、金额等没有可靠目标值时不猜，保留并标 warning；
- 变量替换清单进入 preview 和 application detail。

## §9 前端设计

### 9.1 组件

| 文件 | 职责 |
|---|---|
| `NoteDocUploadDialog.vue` | 上传/知识库双栏解析与编辑 |
| `NoteContentTemplatePicker.vue` | 专用模板列表、来源/版本/质量展示 |
| `NoteContentTemplateApplyDialog.vue` | 三组选择、模式、并排差异、确认 |
| `NoteTextDiffDialog.vue` | 现有/拟写入并排富文本与纯文本摘要 |
| `useNoteTextBatch.ts` | 统一 preview/apply、选择、冲突与进度 |
| `useNoteContentTemplate.ts` | 模板目录/版本/保存 API，不采集浏览器快照 |

### 9.2 上传/知识库弹窗

- 左侧来源章节树，右侧目标父章分组；
- 只展开的目标挂载 `NoteRichTextEditor`，关闭时保留 draft state；
- 一键预填只填 confirmed 映射；手工选择后才能填 candidate；
- 右侧可二次编辑，状态由原始 hash 与 draft hash 计算，不靠易漂移布尔标记；
- 关闭、换来源、换模板前若有变更，统一二次确认。

> 第二轮复盘第 6 组修订：
> - 右栏改为与 §9.3 共用的服务端预览三分组（推荐 / 需复核 / 不可用），每行显示目标章号与标题，提供标题搜索与「仅看未匹配 / 已变更 / 已选 / 高风险」；不再按目标父章分组。
> - 二次编辑放在左栏来源正文（单个懒挂载 `NoteRichTextEditor`），改完须重新预览：R-09 之后写入只认服务端重算的预览结果，浏览器里改右栏拟写入内容也不会被提交，所以「右侧可二次编辑」改为「来源可二次编辑 + 重新预览」；「已编辑」按原文逐章比对。
> - 可拖分栏未实现（Task 35 仍为 `[~]`）。
>
> 第二轮复盘第 9 组修订（Task 35 → `[x]`）：
> - 可拖分栏：`el-splitter`，左栏默认 42%，左右最小 280 / 360px。
> - 恢复按父章分组，与三分组共存：先分推荐 / 需复核 / 不可用，类内再按目标所属一级章分组（预览项 `target_chapter_title`，只供展示，不进 digest）；无目标的归「未匹配目标章节」。「父章」按一级章理解，更深层级不再细分。
> - 左栏逐来源显示匹配状态（AC-2.2）：预览响应加 `skipped_sources`（`folded` / `out_of_scope`），与右栏用同一份预览。

### 9.3 模板引用弹窗

- 顶部显示来源企业、年度、标准、口径、版本、保存人/时间和质量摘要；
- 三组可折叠，提供搜索、只看已选/高风险/未映射；
- 推荐组默认勾选；需复核组默认不选；不可用组禁用；
- 替换/追加只在勾选已有内容章节后显示；
- “查看差异”打开独立并排弹窗，变量替换和风险逐项列出；
- 最终确认显示新增/替换/追加/高风险计数，并要求高风险已逐项确认。

> 第 6 组：头部目前显示保存时间、不显示保存人姓名——版本元数据只有 `created_by` UUID，显示姓名需后端补联表（待办）。

### 9.4 主页面刷新

apply 成功后：
1. `invalidateDetailCache()`；
2. `await fetchTree()`；
3. 若当前章节被修改，`await fetchDetailFresh(currentNote.note_section)`；
4. 清除弹窗草稿并显示批次回执。

同时补单章保存回归：table 型正文即使清空也必须发送 `text_content=""`；保存成功后回写 `currentNote.text_content`。

> 第 6 组：第 3 步改为无条件刷新当前章（缓存已全部作废，代价只是一次请求）。三个入口在当前章节有未保存修改时拒绝打开（`editDirty || autoSave.isDirty`，与离开页面拦截同口径）：写入成功会重载附注，未保存的编辑会被覆盖；内容模板也只按已保存内容生成。

> 第 8 组（AC-6.3）：入口可用性 = `canWrite`（只读 / 归档 / EQCR / 编辑锁）+ `note:edit` 操作权限（与后端 `require_operation` 同码）+ 未合并锁定。编辑器的 `canEdit` 不含后两项，因此由包装组件自查锁定态（监听 423 事件实时刷新），编辑器菜单按其 `available` 隐藏。锁定查询必须关掉 http 的 GET 去重：同页锁定横幅几乎同时发同一个 GET，去重会取消先发的那一个。

### 9.5 错误提示（第 6 组）

`useNoteTextBatch` / `useNoteContentTemplate` 的请求一律带 `_silent`，由 `notifyBatchError` 统一提示一次中文：后端 message 原样显示；pydantic 校验错误换成中文；无业务 detail 的 HTTP 错误显示「<操作>失败（HTTP 状态码）」；本地中文异常保留原文；被 http 去重取消的请求不提示。不静默时全局拦截器会先弹一次（422 显示英文、403 只有笼统提示、5xx 还自动重发两次），catch 再弹一次。静默后拦截器不再代发合并锁事件，改由本模块在 423「合并锁定」时发 `consol-lock:detected`。

## §10 权限与安全矩阵

| 操作 | 项目权限 | 额外限制 |
|---|---|---|
| 解析上传/知识库 | edit | 知识库逐文档判权 |
| 保存 personal 模板 | edit | owner_user=当前用户 |
| 保存 group 模板 | edit | `admin/manager/partner/signing_partner`；owner=服务端集团根 |
| 列表/详情/版本 | readonly | personal 本人或同 canonical group；不可见 404 |
| preview/apply | edit | 来源可见 + 目标项目门禁 + 合并锁 |
| 删除 personal | edit | 仅本人 |
| 删除 group | edit | 同集团 manager/partner；仅软删目录 |

端点级测试必须覆盖：本人/他人 personal、同组根/子/兄弟、异组、伪造 owner、直接 UUID 详情/apply、无目标项目权限、EQCR、归档/合并锁。不能只测 service。

## §11 容量、错误与可观测性

### 11.1 真实 PG 探针结果（Task 1 冻结，2026-10-11）

探针统计 6 个项目（1009 活动章节），口径：`disclosure_notes WHERE NOT is_deleted`。

| 维度 | 实测值 |
|---|---|
| 项目章节数 | 158 ~ 200（p50=159，max=200；含已删最大 214） |
| content_type | text ~37%, mixed ~62%, table ~2%（仅和平药房有 33 张 table） |
| status | 100% draft, 0 confirmed |
| is_stale | 236/1009 = 23.4%（和平药房 199/200 = 99.5%） |
| text_content NULL | 3 项目有 NULL（首汽 22, 宜宾 73, 和平 34），其余 0 |
| text_content 空串 | 全库 0（PG 中 NULL 与空串严格区分） |
| 占位文本 | 4 项目共 58 章含"请在此输入/请输入/占位/placeholder" |
| 有实质内容 | 822/1009 = 81.5% |
| 单章字节 p50 | 1,716 B |
| 单章字节 p95 | 4,247 B |
| 单章字节 max | 49,586 B（陕西华氏 / 四、金融工具） |
| 整套字节 p50 | 325,394 B（318 KiB） |
| 整套字节 p95 | 504,749 B（493 KiB） |
| 整套字节 max | 556,290 B（543 KiB） |
| section_id 非空率 | 首汽 173/173=100%, 和平 40/200=20%, 其余 0% |
| template_lineage | 全库 0（从未写过） |
| is_local_override | 全库 0（从未写过） |

TOP-3 单章：49,586 B（金融工具）、18,148 B（长期股权投资）、17,114 B（租赁），均为叙述性政策章节（type=text）。

### 11.2 冻结业务阈值与硬上限

基于 §11.1 实测数据，按以下策略冻结（后续任务引用这些常量）：

| 限制项 | 业务阈值 | 硬上限 | 依据 |
|---|---|---|---|
| 单章 text_content | 64 KiB | 512 KiB | p95=4.1KiB, max=48.4KiB; 业务=max×1.3 上取整 64K; 硬=max×10 上取整 |
| 整套 text_content | 2 MiB | 5 MiB | p95=493KiB, max=543KiB; 业务=max×3.7 上取整 2M; 硬=max×9 上取整 |
| 每项目章节数 | 300 | 500 | max=200; 业务=max×1.5; 硬=max×2.5 |
| 上传文件体积 | 20 MiB | 50 MiB | AC-1.1 要求 50MB; 业务设保守值 |
| PDF 页数 | 200 | 500 | NFR-6 性能目标 50 页 ≤5s; 业务按 4× |
| DOCX zip entry 数 | 500 | 2,000 | 正常 docx ~100 entry; 防 zip bomb |
| DOCX 解压总字节 | 50 MiB | 200 MiB | 正常 docx 解压 <10MiB |
| 解析返回章节数 | 300 | 500 | 与项目章节数对齐 |
| 单次 batch apply 章节数 | 300 | 500 | 与项目章节数对齐 |
| 模板 sections_data 字节 | 5 MiB | 10 MiB | 整套 max=543KiB; 含 JSON 包装膨胀 |
| 知识库来源文档数 | 5 | 5 | AC-5.1 |

- 模板列表仅元数据分页；版本详情/preview 才加载 sections_data。
- 文件解析与 DB 写入分开计时，日志不打印正文，只记录文件 hash、章节数、字节数、耗时和错误码。
- 主要错误码：`UNSUPPORTED_FILE`、`FILE_TOO_LARGE`、`DOCX_ZIP_LIMIT`、`PDF_NEEDS_OCR`、`NO_PARSEABLE_TEXT`、`TEMPLATE_NOT_VISIBLE`、`MAPPING_MANUAL_REQUIRED`、`NOTE_BATCH_STALE_PREVIEW`、`MUTATION_ID_CONFLICT`、`PAYLOAD_TOO_LARGE`。
- 解析失败不污染 DB；preview 不写 DisclosureNote；apply 失败零写入；事件失败只作为已提交 warning 回执。

## §12 受影响文件

### 后端新增
- `backend/app/models/note_content_template_models.py`
- `backend/app/models/note_content_template_schemas.py`
- `backend/app/services/note_document_parser.py`
- `backend/app/services/note_html_sanitizer.py`
- `backend/app/services/note_text_batch_service.py`
- `backend/app/services/note_content_template_service.py`
- `backend/app/routers/note_text_batch.py`
- `backend/app/routers/note_content_templates.py`
- `backend/migrations/V187__note_content_templates_and_batch_apply.sql`
- `backend/migrations/R187__rollback_note_content_templates_and_batch_apply.sql`

### 后端修改
- `backend/app/services/note_section_catalog.py`：section_kind 投影；
- `backend/app/services/disclosure_mutation_coordinator.py`：commit 后多事件；
- `backend/app/router_registry/report.py`：注册两个 router；
- `backend/app/models/report_schemas.py`：章节读取补层级/身份字段（如复用 DTO）。

### 前端新增
- `NoteDocUploadDialog.vue`、`NoteContentTemplatePicker.vue`、`NoteContentTemplateApplyDialog.vue`、`NoteTextDiffDialog.vue`；
- `useNoteTextBatch.ts`、`useNoteContentTemplate.ts`；
- 专用 API types/client。

### 前端修改
- `DisclosureEditor.vue`：三个入口、弹窗挂载、缓存/当前章刷新；
- `useNotePersist.ts`：table 型正文清空与缓存回写回归；
- `useSanitize.ts`：与后端允许列表对齐。