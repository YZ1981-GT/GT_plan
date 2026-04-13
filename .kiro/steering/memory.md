---
inclusion: always
---

# 持久记忆

这是 Kiro 的自动记忆文件。每次对话开始时自动加载，提供跨会话的上下文连续性。

## 用户偏好
- 语言偏好：中文
- 部署偏好：倾向本地部署、轻量方案，避免重依赖
- 打包偏好：优先用 build_exe.py 打包为 EXE（PyInstaller），不要 .bat 脚本方式；打包前先 npm run build + 复制到 backend/static/，再 python build_exe.py --skip-frontend
- 启动偏好：删掉了 .bat 启动文件，希望我直接用 Start-Process 自动启动后端(9980)+前端(3030)；用 `uvicorn app.main:app --host 0.0.0.0 --port 9980 --reload` 启动后端，`npm run dev` 启动前端
- pydantic-settings Node.js 路径问题：pydantic-settings 初始化时调用 `npm config get prefix`，.venv 里没有 node.exe 会报 `Could not determine Node.js install directory`；临时解决：在 .env 中设置 NPM_CONFIG_PREFIX 环境变量或确保系统 node 在 PATH 中
- TTS 声音偏好：默认声音觉得难听，需要能自选男女声/角色，且支持自录音频替代 TTS
- PPT 生成偏好：必须用 ppt-generator skill 工作流（ppt_helpers.py 命令）生成，不要手写 JSON/HTML
- PPT 内容密度偏好：每页内容不要太少，要充实
- 审计报告复核 UI 偏好：问题列表需要按附注表格+问题类别两级折叠分组，支持组头 checkbox 批量操作，避免逐条勾选
- 附注表格标题识别偏好：紧邻表格的上一行段落就是表格标题（section_title），account_name 必须通过向上回溯编号标题确定，紧邻段落不能直接当 account_name，关键词提取只作兜底
- 聊天面板尺寸偏好：默认宽度页面1/4、高度100%满屏高（靠右贴边，顶部从0开始），支持拖动标题栏移动位置、右下角手柄缩放大小、最大化/还原切换；输入框默认3行（minHeight 64px）
- 聊天面板全局可见偏好：💬按钮需要在所有页面（首页+四大工作模块）都显示，不能只在首页；ChatPanel 已从 renderSelectMode 提升到 App.tsx 顶层所有 return 分支
- 聊天消息操作按钮布局偏好：📋📄✏️📌等按钮不能叠在气泡内右上角（会被文字遮挡看不清），必须放在气泡外下方显示
- 聊天面板窗口控制偏好：需要支持最大化/还原切换（⊞/⊡按钮），已实现 520×720 小窗 ↔ 全屏切换
- 聊天 AI 回复排版偏好：Markdown 渲染必须有清晰层次，不能一大段纯文本；system prompt 用「## 【重要】回复格式强制要求」+禁止性措辞+示例模板强制 LLM 分段输出（温和措辞会被忽略）；CSS 中 h1/h2 加底部分隔线、段落间距 10px、列表项间距 6px

## 项目上下文

### 基础环境
- Git 远程仓库：https://github.com/YZ1981-GT/GT_plan.git（master分支），本地新初始化时需先 `git init` → `git remote add origin` → 用 `git config --global --unset http.proxy` 清代理后 pull/push；代理端口 127.0.0.1:7897 不通时会报 "Failed to connect to 127.0.0.1 port 7897"
- Python 3.12 虚拟环境 (.venv)，本地已安装 Docker 28.3.3、Ollama 0.11.10
- 使用 Kiro steering + hooks 机制管理工作流
- 四大模块统一架构：四/五步工作流 + SSE 流式通信 + LLM 驱动 + Word 导出

### 项目根目录文件
- `start.bat` — 开发模式一键启动（前后端分离，后端9980+前端3030）
- `build_exe.py` — PyInstaller EXE 打包脚本（含系统托盘、自动找端口、.env 加载）
- `pack_portable.py` — 绿色便携包打包（核心 .py 编译为 .pyc 保护源码）
- `README.md` — 项目说明文档
- `LICENSE` — MIT 许可证
- `.gitignore` — Git 忽略规则

### 后端文件清单 (backend/)

#### 入口与配置
- `backend/run.py` — 启动脚本（uvicorn 启动 FastAPI）
- `backend/app/main.py` — FastAPI 应用入口，路由注册，静态文件托管，CORS
- `backend/app/config.py` — 应用配置（CORS、文件上传限制等）
- `backend/app/__init__.py`
- `backend/.env.example` — 环境变量示例
- `backend/requirements.txt` — Python 依赖清单
- `backend/pytest.ini` — 测试配置

#### 数据模型 (backend/app/models/)
- `schemas.py` — 通用数据模型（ChapterContentRequest、ChapterRevisionRequest 等）
- `audit_schemas.py` — 审计相关数据模型（ReviewReport、ReviewFinding、StatementItem、NoteTable、NoteSection、ReportReviewFinding、ReportReviewSession 等 50+ 个 Pydantic 模型）
- `analysis_schemas.py` — 文档分析数据模型（AnalysisDocumentInfo、AnalysisProject、AnalysisChapter、AnalysisMode 等）
- `chat_schemas.py` — 聊天功能数据模型（ChatMessage、ChatStreamRequest、ChatUploadResponse、SpeechToTextResponse、ExportWordRequest、NoteCreateRequest、NoteItem、NoteGroup、NotesListResponse、CleanupSuggestion、CleanupSuggestResponse、PolishRequest、KnowledgeMoveRequest）

#### 路由层 (backend/app/routers/) — 16 个路由模块
- `review.py` — 底稿复核 API（/api/review，上传/批量上传/引用检查/补充材料/SSE复核/报告导出/状态更新/交叉引用）
- `generate.py` — 文档生成 API（/api/generate，大纲提取/确认/SSE逐章节生成/单章节生成/章节修改/Word导出）
- `analysis.py` — 文档分析 API（/api/analysis，上传解析含智能OCR/格式化/项目管理/大纲生成/章节生成/Word导出）
- `report_review.py` — 审计报告复核 API（/api/report-review，1300+行，上传/解析/科目对照/SSE复核/findings CRUD/批量操作/对话/追溯/导出/模板管理）
- `config.py` — AI 配置 API（/api/config，供应商CRUD/激活）
- `prompt.py` — 提示词管理 API（/api/prompt，列表/保存/Git同步推送冲突标签）
- `template.py` — 模板管理 API（/api/template，上传/列表/详情/删除/更新）
- `knowledge.py` — 知识库 API（/api/knowledge，库列表/文档CRUD/搜索）
- `project.py` — 项目管理 API（/api/project，创建/列表/详情/底稿关联/模板关联）
- `document.py` — 文档处理 API（/api/document，上传解析/SSE分析/Word导出）
- `outline.py` — 大纲 API（/api/outline，大纲生成）
- `content.py` — 内容生成 API（/api/content，知识库预加载/SSE章节生成/SSE章节修改）
- `search.py` — 搜索 API（/api/search，网络搜索辅助）
- `expand.py` — 扩展 API（文件上传）
- `chat.py` — 聊天 API（/api/chat，流式聊天/文档上传/语音识别/Word导出/笔记CRUD/AI润色）

#### 服务层 (backend/app/services/) — 29 个服务模块

**底稿智能复核相关：**
- `workpaper_parser.py` — 底稿解析器（支持 xlsx/xls/docx/doc/pdf，Excel 合并单元格处理，Word 标题样式解析，.doc 用 pywin32 COM，PDF 多引擎，自动识别底稿编号 B/C/D-M 类）
- `review_engine.py` — 复核引擎（review_workpaper_stream SSE 逐维度 LLM 复核，_review_dimension 构建 prompt，_parse_findings 解析 JSON，classify_risk_level 风险分级，check_required_references 关联底稿检查，analyze_cross_references B/C/D-M 交叉引用，_extract_entity_name 编制单位提取）
- `prompt_library.py` — 提示词库（从 TSJ/ 加载约70个预置提示词 Markdown，支持编辑/替换/追加/恢复，{{#sys.files#}} 占位符，Git 版本管理，usage_count 统计）
- `prompt_git_service.py` — 提示词 Git 版本管理（拉取/推送/冲突处理/标签管理）
- `report_generator.py` — 复核报告生成与导出（Word: 仿宋_GB2312+Arial Narrow 排版、页边距3/3.18/3.2/2.54cm、表格上下1磅边框无左右、高风险标红、页脚页码；PDF: WeasyPrint HTML→PDF）

**审计文档生成相关：**
- `document_generator.py` — 文档生成器（1400+行，extract_template_outline 大纲提取优先 Word 标题样式+中文序号检测+过滤目录页+统一阿拉伯数字编号，_match_preset_outline 预置大纲匹配，generate_document_stream SSE 逐章节生成注入父级/同级上下文，_generate_section_content 单章节生成，revise_section_stream AI 对话修改+选中文本局部修改+多轮历史，export_to_word Word 导出）
- `template_service.py` — 模板管理（5种预置类型：审计计划/审计小结/尽调报告/审计报告/其他，上传/存储/列表/详情）
- `word_service.py` — Word 导出服务（自定义中英文字体，Markdown 渲染到 Word 含标题/列表/表格/加粗斜体）

**文档分析相关：**
- `analysis_service.py` — 文档分析服务（1200+行，generate_outline AI 生成章节框架，generate_chapter_content 逐章节生成引用原文标注出处 `<source doc="" excerpt=""/>`，revise_chapter_content AI 修改，format_document_to_markdown 大文档分块格式化，export_to_word Word 导出复用审计报告复核排版风格）
- `ocr_service.py` — OCR 服务（Tesseract 中英文，MinerU GPU 加速 PDF→Markdown 可选，smart_parse 智能策略：检测 PDF 类型→文字层直接提取→扫描版/混合 OCR→质量检测→fallback，Word/Excel 嵌入图片 OCR 补充）
- `file_service.py` — 文件服务

**审计报告复核相关：**
- `report_parser.py` — 报告解析器（2000+行，parse_report_files 解析上传文件，classify_report_file 文件分类，extract_sheets Excel 报表提取含合并报表合并/母公司列识别，_detect_header_rows 表头检测，_detect_consolidated_columns 合并列检测，_merge_header_rows 多行表头合并，extract_statement_items 科目行提取，extract_note_tables 附注表格提取，extract_note_sections 附注章节提取，_find_table_heading 表格标题回溯，_detect_note_table_headers 附注表头检测，_merge_note_header_rows 附注多行表头合并含空列继承）
- `reconciliation_engine.py` — 对账引擎（8700+行，项目最大文件，30+种数值校验：check_amount_consistency 报表vs附注金额一致性，check_note_table_integrity 附注表格内部勾稽，check_balance_formula 期初+变动=期末，check_wide_table_formula 宽表公式，check_sub_items 子项合计，check_cross_table_consistency 跨表交叉含坏账/薪酬/存货/商誉/债权投资/合同资产/收入成本，check_cashflow_supplement_consistency 现金流量表补充资料，check_income_tax_consistency 所得税，check_equity_change_vs_notes 权益变动表，check_aging_transition 账龄衔接，check_ecl_three_stage_table 预期信用损失三阶段，check_book_value_formula 账面价值，check_data_completeness 数据完整性，check_ratio_columns 比例列，check_financial_expense_detail 财务费用明细，check_benefit_plan_movement 设定受益计划变动，check_equity_subtotal_detail 权益小计明细，check_restricted_asset_disclosure 受限资产披露LLM，check_text_reasonableness 文本合理性LLM，_make_finding 统一 finding 构造含≤40字截断）
- `report_body_reviewer.py` — 正文复核（LLM 辅助：check_entity_name_consistency 单位名称一致性，check_abbreviation_consistency 简称统一性，check_template_compliance 与致同模板逐段比对）
- `note_content_reviewer.py` — 附注内容复核（LLM 辅助：extract_narrative_sections 提取叙述性章节，check_expression_quality 表达通顺性，check_policy_template_compliance 会计政策与模板比对）
- `text_quality_analyzer.py` — 文本质量检查（_check_mixed_punctuation 本地规则中英文标点混用检测含行号页码定位，analyze_punctuation LLM 标点检查，analyze_typos LLM 错别字检查）
- `table_structure_analyzer.py` — 表格结构分析器（_find_preset_for_note 预设规则匹配，try_build_formula_from_preset 预设公式构建，analyze_table_structure 规则+LLM 分析，analyze_wide_table_formula 宽表公式 LLM 分析，is_wide_table_candidate 宽表候选判断，LRU 缓存）
- `report_template_service.py` — 报告模板服务（get_template/get_template_section/get_template_toc 模板读取，update_template 更新，import_from_word Word 导入，_parse_markdown_sections Markdown 章节解析，文件存储 ~/.gt_audit_helper/report_templates/）

**共享服务：**
- `openai_service.py` — LLM 服务（多供应商适配 OpenAI 兼容 API，支持 DeepSeek/通义千问/Kimi/MiniMax/智谱GLM/Ollama，stream_chat_completion SSE 流式，模型上下文限制管理 data/model_context_limits.json）
- `knowledge_service.py` — 知识库服务（9个审计专用分类：底稿模板库/监管规定库/会计准则库/质控标准库/审计程序库/行业指引库/提示词库/报告模板库/笔记库，LRU 缓存上限300文档，文件存储 ~/.gt_audit_helper/knowledge/）
- `knowledge_retriever.py` — 知识库智能检索（按章节标题关键词匹配，分批加载，token 预算控制，configure_for_model 按模型调整预算，get_formatted_for_chapter 格式化注入 prompt）
- `knowledge_vector_service.py` — 知识库向量服务
- `search_service.py` — 网络搜索服务
- `project_service.py` — 项目管理服务（4种角色：合伙人/项目经理/审计员/质控人员，按业务循环筛选）
- `session_store.py` — 会话存储（backend/data/sessions/{session_id}/session.json + findings.json）
- `chat_service.py` — 聊天服务（ChatService：build_messages RAG注入+上下文拼接、_truncate_messages 上下文窗口截断、should_suggest_save_note 本地规则检测、MODULE_DESCRIPTIONS 模块描述注入）
- `heading_utils.py` — 标题工具函数
- `account_mapping_template.py` — 科目映射模板
- `amount_check_presets.py` — 金额检查预设规则
- `statement_preset.py` — 报表预设
- `wide_table_presets.py` — 宽表预设规则
- `docx_to_md.py`（在 utils/ 下）— Word→Markdown 转换

#### 工具层 (backend/app/utils/)
- `config_manager.py` — 运行时配置管理（AI 供应商/模型配置，存储 ~/.gt_audit_helper/config.json）
- `prompt_manager.py` — 提示词模板管理
- `outline_util.py` — 大纲处理工具（编号规范化、层级调整）
- `json_util.py` — JSON 解析工具（容错解析 LLM 返回的 JSON）
- `docx_to_md.py` — Word→Markdown 转换
- `sse.py` — SSE 流式响应工具（sse_response、sse_with_heartbeat）

#### 测试 (backend/tests/) — 22 个测试文件
- `test_report_parser.py`、`test_report_review_engine.py`、`test_report_review_router.py`、`test_audit_report_review_models.py` — 审计报告复核测试
- `test_reconciliation_engine.py`、`test_change_threshold.py`、`test_gap_checks.py`、`test_new_checks.py`、`test_new_improvements.py`、`test_three_new_checks.py` — 对账引擎测试
- `test_note_table_headers.py`、`test_parent_scope.py`、`test_soe_column_swap.py`、`test_soe_income_statement.py` — 报表解析测试
- `test_table_structure_analyzer.py`、`test_wide_table_formula.py` — 表格结构测试
- `test_heading_utils.py`、`test_backend_services.py`、`test_template_structure_diff.py`、`test_template_type_presets.py` — 其他测试
- `_debug_formula.py` — 调试脚本

#### 数据目录
- `backend/data/model_context_limits.json` — 各模型上下文长度限制配置
- `backend/data/sessions/` — 审计报告复核会话数据（72个会话目录，每个含 session.json + findings.json）

### 前端文件清单 (frontend/src/)

#### 入口
- `App.tsx` — 主应用（工作模式路由：底稿复核/文档生成/文档分析/审计报告复核）
- `index.tsx` — React 入口

#### 组件 (frontend/src/components/) — 44 个组件

**工作模式选择：**
- `WorkModeSelector.tsx` — 工作模式选择首页（四大模式入口）
- `ConfigPanel.tsx` — AI 配置面板（供应商/模型/API Key 配置）
- `ModelSelector.tsx` — 模型选择器（章节编辑器内置）
- `StepBar.tsx` — 步骤指示器通用组件

**底稿智能复核（四步）：**
- `ReviewWorkflow.tsx` — 复核工作流容器（步骤管理、SSE 事件处理、IndexedDB 状态恢复）
- `WorkpaperUpload.tsx` — 底稿上传（单文件/批量，格式校验）
- `PromptSelector.tsx` — 提示词选择（从 TSJ 加载，按科目分类筛选）
- `ReviewDimensionConfig.tsx` — 维度配置（5个标准维度 + 自定义维度）
- `SupplementaryUpload.tsx` — 补充材料上传（文件或文本）
- `ReviewConfirmation.tsx` — 复核确认（参数汇总、启动复核）
- `ReviewReport.tsx` — 复核报告展示（结构化报告、风险统计）
- `CrossReferenceGraph.tsx` — 交叉引用关系图

**审计文档生成（四步）：**
- `GenerateWorkflow.tsx` — 文档生成工作流容器
- `TemplateSelector.tsx` — 模板上传与配置（模板类型选择、项目信息、知识库关联）
- `TemplateOutlineEditor.tsx` — 大纲可视化编辑（增删改、调整层级和顺序）
- `DocumentEditor.tsx` — 文档编辑器（三种生成模式：批量3并发/逐章节/停止）
- `SectionEditor.tsx` — 章节编辑器（手动编辑、AI 对话修改、选中文本局部修改+高亮、内置模型选择器）
- `ExportPanel.tsx` — 导出面板（Word 导出、字体设置）
- `FontSettings.tsx` — 字体设置组件

**文档分析（四步）：**
- `AnalysisWorkflow.tsx` — 文档分析工作流容器（多文档上传、三种分析模式、章节框架、逐章节生成、出处标注悬停预览）

**审计报告复核（五步）：**
- `AuditReportWorkflow.tsx` — 审计报告复核工作流容器
- `AuditReportUpload.tsx` — 报告上传（Word 报告 + Excel 报表，模板类型选择 soe/listed）
- `AccountMatchingView.tsx` — 科目对照确认（报表科目与附注表格自动匹配）
- `AuditReportConfig.tsx` — 复核配置
- `FindingConfirmationView.tsx` — 问题确认（两级折叠分组 account_name→category，组头 checkbox 含 indeterminate 半选态，批量确认/驳回）
- `FindingDetailPanel.tsx` — 问题详情面板
- `AuditReportResult.tsx` — 复核报告展示与导出
- `SourceDocPreview.tsx` — 源文档预览
- `TemplateEditorView.tsx` — 模板编辑视图

**知识库与项目：**
- `KnowledgePanel.tsx` — 知识库面板（7个分类、文档管理）
- `KnowledgeSearchPanel.tsx` — 知识库搜索面板
- `ProjectPanel.tsx` — 项目管理面板
- `WebSearchPanel.tsx` — 网络搜索面板

**首页聊天（新增）：**
- `ChatPanel.tsx` — 聊天面板主组件（可折叠、SSE流式对话、IndexedDB持久化、文件/图片上传、笔记保存）
- `ChatMessageList.tsx` — 消息列表（Markdown渲染、图片预览、知识库引用标签、笔记保存按钮、建议保存提示）
- `ChatInput.tsx` — 输入区域（@知识库触发、/快捷指令、📎上传、🎤语音、Ctrl+V粘贴图片、拖拽上传）
- `KnowledgePopup.tsx` — 知识库候选列表弹窗（forwardRef+useImperativeHandle键盘导航）
- `CommandPopup.tsx` — 快捷指令候选列表弹窗（同上模式）
- `NotesSidebar.tsx` — 笔记侧边栏（按日期分组、展开/收起、预览、删除确认、移动/复制操作）
- `ChatExportPanel.tsx` — 聊天导出预览编辑面板（Markdown编辑、AI润色SSE流式、导出Word、在线编辑）
- `ChatWelcome.tsx` — 欢迎引导组件（2x2模块卡片网格、使用提示）
- `DocumentEditorModal.tsx` — 文档在线编辑模态框（三模式：👁预览、✏️左右分栏编辑+实时预览、✨AI润色；🔄同步编辑内容回对话消息、📌转存笔记、⬇下载Word用编辑后内容重新生成）
- `LibraryTargetSelector.tsx` — 目标知识库选择器弹窗（移动/复制文档时选择目标库+笔记库日期子文件夹）

#### 页面 (frontend/src/pages/)
- `DocumentAnalysis.tsx` — 文档分析页
- `OutlineEdit.tsx` — 大纲编辑页
- `ContentEdit.tsx` — 内容编辑页

#### 服务与工具
- `services/api.ts` — API 封装（reviewApi/generateApi/analysisApi/reportReviewApi/configApi/promptApi/templateApi/knowledgeApi/projectApi/chatApi）
- `hooks/useAppState.ts` — 全局状态管理
- `utils/auditStorage.ts` — IndexedDB 缓存（审计工作状态持久化）
- `utils/draftStorage.ts` — 草稿存储
- `utils/sseParser.ts` — SSE 流解析（processSSEStream）
- `utils/chatStorage.ts` — 聊天会话 IndexedDB 持久化（chat_current + chat_archive 两个 store）
- `utils/markdownToHtml.ts` — Markdown→HTML 转换（unified pipeline，供富文本复制使用）
- `utils/copyRichText.ts` — 富文本复制（ClipboardItem text/html + text/plain，回退纯文本）
- `types/audit.ts` — 审计相关 TypeScript 类型定义
- `types/analysis.ts` — 文档分析 TypeScript 类型定义
- `types/index.ts` — 类型导出
- `types/chat.ts` — 聊天类型定义（ChatMessage、ChatAttachment、ChatSession、KnowledgeRef、QuickCommand、QUICK_COMMANDS、NoteItem、NoteGroup）
- `styles/gt-design-tokens.css` — GT 设计系统 Token（主色 #4b2d77、辅助色、间距、圆角等）

### 资源目录
- `TSJ/` — 预置提示词库（约70个 Markdown 文件，按会计科目分类：货币资金/应收账款/存货/固定资产/无形资产/长期股权投资/短期借款/长期借款/应付账款/应付职工薪酬/应交税费/收入/成本/费用等）
- `GT_底稿/` — 审计底稿模板（D销售循环~M权益循环+Q关联方循环，致同底稿模板，审计实务操作手册.html，审计实务操作手册-框架.md，致同GT审计手册设计规范.md）
- `MinerU/` — MinerU PDF 解析工具（web_ui.py Web 界面，fix_md_tables.py 表格修复脚本，启动Web界面.bat）

## 技术决策
- AI 记忆方案：放弃 mem0 本地部署（太重6GB+），改用 Kiro 原生 steering + hook 轻量方案
- 记忆系统架构：memory.md (always steering) + auto-save-memory hook (agentStop 触发自动保存)
- UTF-8 BOM 防御：所有 Python 脚本读取 JSON/HTML 文件统一用 `utf-8-sig` 编码
- Word 导出统一排版规范：仿宋_GB2312+Arial Narrow、页边距3/3.18/3.2/2.54cm、表格上下1磅边框无左右、高风险标红、页脚页码
- 底稿复核编制单位提取：ReviewEngine._extract_entity_name() 从 content_text 前2000字符正则匹配
- account_name 长度防御：三层修复（report_parser 回溯增强+后端≤40字截断+前端≤30字截断），核心 _fix_note_table_account_names() 用层级树修正
- 多行表头合并单元格空列继承：_merge_note_header_rows 和 _extract_from_total_row 的 first_row_h 均需对第一行做空列继承
- check_data_completeness 小计行误报修复：_is_total_row 新增 _summary_label_kw 列表，跳过「减：坏账准备」「账龄一年以内/以上的…」「其中：」「加：」等分类汇总行，这些行不是明细行不适用"期末有数但文本列为空"的完整性规则
- 母公司vs合并口径误报修复：① PARENT_COMPANY_NOTE_KEYWORDS 扩展6个变体提高 ancestor_map 识别率 ② 母公司补充校验逻辑从「主动报错」改为「被动确认」——只确认母公司口径是否有匹配，不再用母公司余额去比对合并附注生成 finding，避免母公司报表数被错误匹配到合并附注表格做校对
- 带括号编号子项分组标题识别：table_structure_analyzer._analyze_with_rules 新增第四遍检测，当连续2+个「（1）（2）」编号行前面有非编号 data 行时，将其标记为 subtotal
- 中文序号段落标题识别放宽：第三遍条件从「有中文序号+有编号子项+有合计行」改为「有中文序号+有合计行」即可标记为 subtotal，解决长期股权投资明细表中「一、子公司/二、合营企业/三、联营企业」未被识别为 subtotal 的问题
- _get_data_rows_for_total subtotal覆盖方向修复：判断标准模式vs段落标题模式时，增加检测 subtotal 后面是否紧跟带括号编号行，如果是则强制为段落标题模式（subtotal覆盖后面的编号子项），避免前面的独立行被错误覆盖
- subtotal纵向校验：check_note_table_integrity 新增 subtotal 子项求和校验（如「按组合计提」=（1）+（2）+...），仅对 _SUBTOTAL_VERIFY_ACCOUNTS（其他应收款/应收账款/应收票据）生效，风险等级 LOW
- 发放贷款及垫款专项校验：新增 check_loan_and_advance 函数（reconciliation_engine.py），含4项校验：①报表数vs附注最终账面价值行（从最后一行往前找）②表内计算（总额+应计利息-损失准备=中间账面价值）③表内计算（中间账面价值-一年内到期-应收利息=最终账面价值）④多表交叉（各子表贷款总额一致性）；SKIP_INTEGRITY_KEYWORDS 加入「发放贷款」「贷款和垫款」跳过通用纵向校验；amount_check_presets 新增发放贷款白名单规则；report_review_engine 中调用
- 应收股利专项校验：新增 check_dividend_receivable 函数，含4项校验：①账龄一年以内=明细行之和 ②账龄一年以上=明细行之和 ③小计=一年以内+一年以上 ④合计=小计-坏账准备；SKIP_INTEGRITY_KEYWORDS 加入「应收股利」；report_review_engine 中调用
- 跨表交叉校验口径分离：check_cross_table_consistency 新增 note_sections 参数，分组时用 _is_parent_company_note 区分合并/母公司口径（key 加 ::parent 后缀），避免合并总表和母公司变动表/分类表混在一起做交叉比对；check_impairment_loss_consistency 新增 _parent_note_ids 过滤，_is_movement_table/_is_provision_balance_table 中排除母公司附注，避免母公司坏账准备变动表被算入合并口径的信用/资产减值损失交叉核对；check_equity_method_income_consistency 新增 note_sections 参数+ancestor_map，_is_parent_company_note 传入 ancestor_titles 正确识别母公司长期股权投资明细表并跳过
- _check_asset_summary_cross 子集表格排除：识别明细表时跳过「暂时闲置」「未办妥」「抵押」「出租」「担保」等标题的表格，避免固定资产的子集表格被误识别为完整明细表参与汇总表vs明细表交叉比对
- 续表处理改进：_check_bad_debt_cross 和 _check_asset_summary_cross 中续表不参与表格类型识别，但记录到 continuation_tables，遍历所有续表分别提取期末/期初的坏账准备和账面余额补充首表缺失值（支持宽表拆分：首表有期初末表有期末，或首表有期末续表有期初）
- 在建工程减值准备交叉比对排除「本期计提」：_check_asset_summary_cross 识别 impairment_movement_table 时排除标题含「本期计提」「计提情况」的表格，这些只有当期计提金额不是变动表
- _is_total_row 非合计行排除：table_structure_analyzer._is_total_row 新增 _not_total_labels 列表（工资总额/薪金总额/薪酬总额），这些是薪酬类别名称不是合计行，避免长期应付职工薪酬表中「工资总额」被误判为 total 导致纵向校验误报
- 金融机构特有科目跳过纵向校验：SKIP_INTEGRITY_KEYWORDS 加入「吸收同业及存放」「拆入资金」「卖出回购」「买入返售」「财务费用」
- 财务费用专项校验重写：check_financial_expense_detail 含 F64-3（利息费用-资本化=净额）和 F64-4（合计=顶层行求和）；行识别支持「利息费用/利息支出」「手续费及其他」等变体；有净额时合计=净额-利息收入+汇兑+其他（净额只扣资本化不含利息收入）；每行可选兼容用户删减
- SKIP_INTEGRITY_KEYWORDS 完整列表：主要财务信息/重要合营联营企业/作为承租人/处于第/分部利润/政府补助/发放贷款/贷款和垫款/应收股利/吸收同业及存放/拆入资金/卖出回购/买入返售/财务费用/其他综合收益各项目/长期应付职工薪酬（未加入，通过修复_is_total_row解决）
- 合计行后「其中」行处理（仅其他收益）：_analyze_with_rules 第二遍中，仅对「其他收益」表格，当「其中」行在最后一个 total 行之后时，标记为 sub_item 但不设 parent、不向后扫描，避免「其中：政府补助」被错误关联到前面的 data 行
- 三阶段ECL表纵向校验修复：_check_ecl_column_movement 区分阶段间转移行（转入第X/转回第X，数值已带正负号直接累加）和普通减项行（本期转回/转销/核销，需取反）；「其他变动」行双向校验（加法和减法都试，有一种匹配就通过，都不匹配按减法差异输出）
- 科目匹配关键词精确化：account_mapping_template 和 amount_check_presets 中「所得税费用」的关键词从 ['所得税费用','所得税'] 改为 ['所得税费用']，避免宽泛的「所得税」匹配到「递延所得税资产/负债」表格导致真正的所得税费用表格被遗漏
- 其他权益工具/优先股/永续债匹配修复：account_mapping_template 主映射表新增「优先股」「永续债」作为独立 key（关键词分别含'其他权益工具'+'优先股'/'永续债'），使 get_keywords 能找到它们走模板映射而非模糊匹配，正确匹配到「优先股、永续债等金融工具」附注表格，不再误匹配到「其他权益工具投资」（资产类）
- check_sub_item_detail 匹配优先级：查找附注表格时优先使用子项自身在 matching_map 中的直接匹配（sub.id），无则回退到父科目匹配（parent_id）；新增 _skip_sub_item_kw 排除「优先股」「永续债」不参与二级明细比对（它们是独立权益科目，由 check_amount_consistency 处理）
- FindingDetailPanel「数据下载」按钮：原「数据下钻」改为数据下载功能，点击后生成当前 finding 的详细计算过程文本（含科目/描述/分析过程/数值明细/关联附注表格数据/建议），优先复制到剪贴板，失败则下载为 txt 文件
- 其他综合收益列匹配修复：check_oci_vs_income_statement 优先匹配「税后净额」列（利润表OCI是税后净额），跳过「税前金额」列，三级优先级（税后净额→本期金额排除税前→任何税后净额列）
- 母公司口径白名单：should_verify_note_table 新增 is_parent_note 参数，check_amount_consistency 调整为先判断口径再做白名单过滤；母公司口径的子表（对子公司/对联营/对合营）仍然被排除不参与余额校对（因为子表只是明细不是汇总，单独比对会产生误报），_parent_skip_exclude_kw 预留为空列表供未来扩展
- 前端 tsconfig 不支持 Map 迭代需用 Record 代替
- 表头标准化换行符修复：reconciliation_engine.py 中12处表头标准化统一加上 .replace("\n","").replace("\r","")，解决多行表头合并后含换行符（如「账面\n价值」）导致关键词匹配失败的问题
- 单行其中项识别：table_structure_analyzer 第二遍扫描增加检测，仅对 _SINGLE_LINE_SUB_ITEM_ACCOUNTS（当前仅含"长期应收款"）生效，当「其中：XXX」后面有具体内容（非编号）且该行有数值时不向后扫描子项，避免后续独立行被错误标记为 sub_item
- 附注表格数据全空时抑制「未提取到附注合计值」警告：check_amount_consistency 在生成 NOTE_VALUE_NOT_FOUND_TAG finding 前检查所有匹配表格的数据行是否全为空（_safe_float 均为 None），全空时跳过不报（附注本身没填数值不是结构识别问题）
- 续表期末/期初值提取修复：_extract_from_total_row 的 _is_closing_group/_is_opening_group 增加 is_move 排除变动列（本期增加/本期减少），bv_cols 回退分配时剩余变动列不分配给 opening/closing，解决续表结构（如其他权益工具期初期末分两个表格）中变动列值被错误提取为期末/期初的问题
- PowerShell 5.x 编码陷阱：Python 写给 PS5 的 .ps1 必须用 utf-8-sig（带 BOM）
- 复核流错误信息增强：report_review.py 错误捕获现在输出最内层文件名+行号到前端；report_review_engine.py 第一轮本地校验循环加 try-except 打印 note_id/account_name/section_title 到后端日志，方便定位 NoneType.__format__ 等运行时异常
- NoneType.__format__ 防御：report_review_engine.py 中 _check_preset_missing 和变动分析的 f-string 格式化已加 None 防御（closing_balance/opening_balance/change_amount）
- 预付账款等无"账面价值"列的科目：_extract_from_total_row 的 closing_cols 分支和 _pick_from_range 分支增加"账面余额 - 坏账准备 = 净值"计算逻辑，优先取账面价值列→次选计算净值→回退第一列
- 财务费用F64-4增强：无净额时利息资本化作为减项；增加银行手续费/贴现利息/融资费用/租赁负债利息行识别；兜底策略把所有未识别行加入求和（识别"减："前缀作为减项），全量一致则不报错
- _extract_from_total_row 优先列扩展：bv_cols/_pick_from_range/_pick_net_or_first/单行表头 closing_bv_idx 均增加"税后净额"/"税后"关键词与"账面价值"同等优先，解决其他综合收益明细表取到税前金额而非税后净额的问题（国企版）
- gitpython 崩溃防御：prompt_git_service.py 在 import git 前设置 GIT_PYTHON_REFRESH=quiet，__init__ 中用 shutil.which("git") 检测可用性，_ensure_configured 返回友好提示；build_exe.py launcher 中同样设置该环境变量
- EXE 打包使用期限：build_exe.py launcher main() 最前面加过期检查，当前设为 2026-09-30，过期后弹 MessageBoxW 提示联系致同研究院获取新版本后 sys.exit(1)
- 笔记库架构：在 knowledge_service.py LIBRARIES 中新增 'notes' 分类，与现有8个知识库并列管理，复用知识库全套 CRUD/搜索/RAG 检索能力，聊天中的 AI 回复、上传文档、整段对话均可保存为笔记，笔记可被其他四大工作模块关联使用；笔记按日期子文件夹管理（`~/.gt_audit_helper/knowledge/notes/{YYYY-MM-DD}/`），侧边栏按日期分组展示
- 聊天框特殊字符交互模式：`/` 触发快捷指令跳转工作模块，`@` 触发知识库引用（弹出候选列表，支持模糊过滤，选中显示为标签），不带 `@` 的消息不走知识库检索
- 聊天 Markdown 渲染依赖：前端需新增 react-markdown + remark-gfm + rehype-highlight + unified + remark-parse + remark-rehype + rehype-stringify（后四个用于富文本复制时 Markdown→HTML 转换）；@ranui/preview 已弃用，改用 iframe + markdownToHtml 方案做在线预览
- 富文本复制内联样式：markdownToHtml.ts 中自定义 rehypeInlineStyles 插件，给 table/th/td/blockquote/pre/code/h1-h3/hr 注入内联 style 属性，确保剪贴板 HTML 不依赖外部 CSS，粘贴到 Word/邮件/飞书等任何富文本环境都能正确显示格式
- 项目删除偏好：删除和批量删除操作必须有 ElMessageBox 二次确认弹窗，不能直接删除
- 文档同步偏好：每次功能变更后需同步更新需求文档（需求文档.md），保持文档与代码一致

## 待办 / 进行中
- 项目文件清理（2026-04）：已删除根目录 `__pycache__/`、`frontend/README.md`；`GT_底稿/审计实务操作手册-框架.md` 和 `致同GT审计手册设计规范.md` 待用户确认是否删除
- 用户计划对每个细分程序逐一打磨升级
- 首页聊天功能（全部60个子任务已完成）：spec 路径 .kiro/specs/homepage-chat/，待用户启动测试验收；复盘发现的优化点：①ChatPanel.tsx 超1000行，后续可拆分清理UI/导出逻辑为独立hook ②IndexedDB saveChatSession 流式输出时高频写入，可加debounce ③Whisper API 依赖供应商支持，不支持时需友好提示
- 在线文档编辑（第一步已完成）：homepage-chat 中已改用 iframe + markdownToHtml 方案（弃用 @ranui/preview，Web Component 加载不稳定且预览空白）；第二步单独开 spec 改造四大工作模块的导出流程
- 审计作业平台需求文档（2026-04）：`需求文档.md` 已迭代至 v6（约2200行+7个附录），涵盖23个能力模块、40+数据表、完整业务链路、技术架构、开发优先级。关键技术决策：底稿编辑器选定 ONLYOFFICE Document Server（AGPL，私有化Docker部署，WOPI协议集成，自定义函数实现取数公式，插件实现复核批注/AI标记/交叉索引）；底稿文件（.xlsx/.docx）为第一公民，支持在线编辑（ONLYOFFICE）和离线编辑（下载→本地Excel→上传）双模式；技术栈 FastAPI + PostgreSQL + Redis + Vue 3 + ONLYOFFICE + Ollama；配套 `致同GT审计手册设计规范.md` 定义品牌视觉规范；附录G已整合致同2025年修订版实际底稿编码体系（B/C/D-N/A/S/Q约600+底稿）、三测联动结构、附注模版体系（国企版/上市版各含科目对照+校验公式+宽表公式+正文模版4个配置文件）、6个内置模板集定义；工作区新增 `附注模版/` 和 `致同通用审计程序及底稿模板（2025年修订）/` 两个资源文件夹
- 审计作业平台spec拆分方案（2026-04）：全部8个阶段三件套已完成（Phase 0-4 + Phase 8 Extension），3个遗漏+2个新需求已全部修复，7阶段一致性分析已完成并修复5个中等问题。v7增量：①报表行次映射（余额表→报表科目AI自动匹配+人工确认+集团内企业一键参照+跨年继承），新增 `report_line_mapping` 表和 `ReportLineMappingService`；②调整分录独立编辑表（`adjustment_entries` 明细行表+报表一级/二级科目级联下拉+手动输入+科目标准化校验+底稿审定表自动汇总AJE/RJE明细+分录↔底稿双向穿透）；③TSJ审计复核提示词库应用（~70个按报表科目组织的Markdown提示词→三大应用场景：底稿AI智能复核system prompt驱动+AI分析性复核维度参考+B60审计方案自动生成）。需求文档已同步更新5.2节、5.4节和6.2.1节+6.2.1a节。Phase 4 spec已同步更新需求3.7-3.9+design WorkpaperFillService+tasks 7.2a/7.4。Phase 8 Extension spec新增（2026-04）：15个需求+29个任务组，涵盖多准则适配/多语言/审计类型扩展/自定义模板/电子签名/监管对接/致同编码体系/品牌视觉/附注模版/T型账户/AI插件/Metabase集成/Paperless-ngx集成/大数据优化，design.md含7个冲突解决方案（Metabase vs Phase 4 AI、Paperless-ngx vs Phase 3附件、分区表vs现有DB等）
- 审计作业平台代码实现（2026-04开始）：Phase 0 全部必需任务已完成，Phase 1 MVP Core 全部必需任务已完成（Task 1-23，可选属性测试任务跳过）。后端326个测试全部通过。已完成：Task 1 数据库迁移10张表、Task 2 ORM模型+Pydantic Schema（60+个Schema类覆盖10个模块）、Task 3 检查点、Task 4 项目向导后端（ProjectWizardService 5个方法+5个API端点+16个测试）、Task 5 项目向导前端（ProjectWizard.vue 6步向导+Pinia store+BasicInfoStep+ConfirmationStep+4个占位步骤）、Task 6 科目表管理（标准科目种子数据120个企业会计准则科目+客户科目CSV/Excel导入+3个API端点+AccountImportStep.vue+15个测试）、Task 7 科目映射引擎（auto_suggest 4级优先匹配+save/batch_confirm/update/get_completion_rate+6个API端点+AccountMappingStep.vue三栏布局+21个测试）、Task 7a 报表行次映射（report_line_mapping表+003迁移+规则匹配占位+confirm/batch_confirm/reference_copy/inherit+6个API端点+19个测试）、Task 8 检查点、Task 9 数据导入引擎（ParserFactory+GenericParser+7条校验规则责任链+ImportService同步导入+回滚+4个API端点+DataImportPanel.vue+37个测试）、Task 10 检查点、Task 11 四表穿透查询（DrilldownService 4个方法+4个API端点+Drilldown.vue面包屑导航+Pinia store+13个测试）、Task 12 试算表计算引擎（TrialBalanceService 增量/全量重算+一致性校验+3个API端点+8个测试）、Task 13 调整分录管理（AdjustmentService CRUD+复核状态机+科目下拉+底稿审定表+AdjustmentEntry明细行表+004迁移+8个API端点+28个测试）、Task 14 检查点、Task 15 重要性水平（MaterialityService 三级计算+自动取基准+手动覆盖+变更历史+5个API端点+MaterialityStep.vue+23个测试）、Task 16 事件总线（EventBus asyncio+事件处理器注册+SSE推送+14个测试）、Task 17 检查点、Task 18 前端页面（TrialBalance.vue分组小计+穿透交互+Adjustments.vue Tab切换+CRUD弹窗+批量复核+Materiality.vue独立页面）、Task 19 前端集成（Vue Router注册4个新路由+auditPlatformApi.ts API服务层）、Task 20 检查点、Task 21 未更正错报（UnadjustedMisstatement模型+005迁移+MisstatementService 7个方法+6个API端点+Misstatements.vue+18个测试）、Task 22-23 检查点
- 审计作业平台 Phase 1 MVP Report 全部必需任务已完成（Task 1-24，可选属性测试跳过）。后端466个测试全部通过。已完成：Task 1-3 数据库迁移8张报表表+ORM模型+Schema、Task 4-5 报表配置种子数据（四张报表121行含公式）+ReportConfigService+API、Task 6-7 报表生成引擎（ReportFormulaParser+ReportEngine公式驱动取数+增量更新+平衡校验+穿透查询+EventBus监听）、Task 8-9 现金流量表工作底稿引擎（CFSWorksheetEngine工作底稿法+自动调整项+CRUD+平衡状态+主表生成+间接法+勾稽校验+11个API端点+26个测试）、Task 10-12 附注生成与校验引擎（DisclosureEngine附注生成+NoteValidationEngine 8种校验器+种子数据+API+EventBus监听+17个测试）、Task 13-14 审计报告模板管理（AuditReportService模板加载+占位符填充+段落编辑+KAM校验+财务数据刷新+EventBus监听+25个测试）、Task 15-18 PDF导出引擎（PDFExportEngine HTML渲染+WeasyPrint可选+同步导出+API+15个测试）+报表联动（已通过EventBus实现）、Task 19-24 前端5个Vue页面（ReportView.vue四张报表Tab+穿透弹窗、CFSWorksheet.vue工作底稿+调整分录+间接法+勾稽、DisclosureEditor.vue三栏布局目录树+编辑+校验、AuditReportEditor.vue段落导航+编辑+财务数据、PDFExportPanel.vue文档选择+进度+历史）+Vue Router 5条新路由+auditPlatformApi.ts 25个新API函数
- 审计作业平台 Phase 1 MVP Workpaper 全部必需任务已完成（Task 1-24，可选属性测试跳过）。后端661个测试全部通过。已完成：Task 1-3 数据库迁移8张底稿表+ORM模型+Schema+16个测试、Task 4-5 取数公式引擎（FormulaEngine 5种Executor+Redis缓存+35个测试）、Task 6-8 底稿模板引擎（TemplateEngine+6个内置模板集+11个API端点+28个测试）+预填充/解析服务（10个测试）、Task 9 WOPI Host服务（WOPIHostService check_file_info/get_file/put_file+内存锁管理lock/unlock/refresh_lock+JWT访问令牌+WOPI API支持UUID和旧版POC双模式+Lock/Unlock/RefreshLock via X-WOPI-Override）、Task 10-11 底稿管理服务（WorkingPaperService list/get/download/upload冲突检测/update_status/assign+10个API端点）、Task 12-13 QC引擎（QCEngine 12条规则框架3阻断+8警告+1提示stub+get_project_summary+3个API端点）、Task 14 复核批注服务（WpReviewService add/reply/resolve状态机+4个API端点）、Task 15 事件联动（FormulaEngine.invalidate_cache注册到adjustment/import/mapping事件）、Task 16-17 ONLYOFFICE插件（audit-formula取数函数插件5个自定义函数TB/WP/AUX/PREV/SUM_TB+audit-review复核批注侧边栏插件）、Task 18-22 前端页面（WorkpaperList.vue索引树+筛选+详情面板、WorkpaperEditor.vue ONLYOFFICE iframe+降级模式、QCResultPanel.vue三级分组+阻断禁用提交、QCSummaryCard.vue五指标卡片、TemplateManager.vue模板+模板集Tab、Vue Router 3条新路由+workpaperApi.ts 25+个API函数）、Task 23 抽样记录管理（008迁移2张表+SamplingService样本量计算属性/MUS/随机+MUS评价+完整性检查+8个API端点+SamplingPanel.vue+46个测试）、Task 24 最终检查点
- 审计作业平台代码已推送到 GT_plan 仓库（2026-04）：git init → git remote add origin https://github.com/YZ1981-GT/GT_plan.git → git push -u origin master，1207个文件，.gitignore排除node_modules/__pycache__/.venv/storage/sessions/大Excel文件
- 审计作业平台 Phase 8 Extension 后端+前端全部必需任务已完成（2026-04）：Task 1-2 数据库迁移+ORM+Schemas全部完成、Task 3 多准则适配(3.1/3.5/3.6)、Task 4 多语言(4.2/4.7后端+19.1-19.5前端)、Task 5 审计类型(5.4)、Task 6 自定义模板(6.1-6.3/6.5-6.7后端+20.1-20.5前端)、Task 7 电子签名(7.1-7.7后端+21.1-21.5前端)、Task 8 监管对接(8.1-8.7后端+22.1-22.5前端)、Task 9 致同编码(9.1/9.2/9.5/9.6后端+23.1-23.4前端)、Task 10 品牌视觉(全部+27.1-27.6 SCSS)、Task 12 T型账户(12.1-12.8后端+24.1-24.4前端)、Task 13 AI插件(13.1-13.14后端含8个Executor stub+25.1-25.5前端)、Task 14 Metabase(14.1-14.4/14.6/14.7)、Task 15 Paperless-ngx(全部)、Task 16 大数据优化(全部)、Task 18 后端测试(18.1-18.10全部)、Task 19-27 前端42个Vue组件全部完成、Task 30 三栏布局(全部)、Task 31 vue-office(全部)；后端857个测试通过；extensionApi.ts API服务层+9条新路由；剩余未完成：5.1-5.3/5.5(审计类型模板)、28(集成测试)、29(文档)、32(Teable/Grist评估)
- Phase 8 三件套与需求文档一致性审查（2026-04）：8个问题已全部修复——requirements.md新增需求16(三栏布局)+17(vue-office)+18(Teable/Grist评估)，需求7补充模板集关联(附录G.6)，需求12移除与需求15冗余的分区表/索引定义，需求13补充Metabase与右侧栏功能边界说明；tasks.md新增任务组30(三栏布局,4/6已完成)+31(vue-office)+32(Teable/Grist)；design.md确认完整(1053行)；README.md更新为18个需求32个任务组
- 前端三栏布局（需求文档12.2.2）已完成初版：ThreeColumnLayout.vue核心组件（顶部导航+左侧9项功能导航可折叠220px+中间栏340px+右侧栏自适应+拖拽分隔线+localStorage偏好保存+响应式）、MiddleProjectList.vue中间栏项目列表（搜索/筛选/状态色条/选中高亮）、DetailProjectPanel.vue右侧详情面板（5个Tab概览/指标/底稿/试算表/报表+6个快捷操作）、DefaultLayout.vue重写为三栏容器（首页/项目列表三栏模式，具体项目子页面隐藏中间栏右侧全宽）
- 四表联查是用户强调的重中之重：Task 16已全部完成——012迁移将tb_ledger+tb_aux_ledger重建为PARTITION BY RANGE(year)分区表（复合主键id+year，预建2023-2027共5个年度分区，无生产数据直接重建）+011迁移3个补充索引+LedgerPenetrationService 6个查询方法+Redis缓存TTL=5min+7个API端点+VirtualScrollTable虚拟滚动组件+LedgerPenetration.vue穿透查询页面（面包屑5级导航：余额→序时账→凭证→辅助余额→辅助明细）+19个测试通过；实际数据量参考：凭证表26万行、核算项目明细表23万行
- 底稿跨企业汇总功能（已完成）：WorkpaperSummaryService（trial_balance按科目×企业透视+Excel导出）+ workpaper_summary router 3个端点 + WorkpaperSummary.vue（左侧科目树+企业树checkbox，右侧动态列el-table+合计行+导出Excel）+ 路由 /projects/:id/workpaper-summary + 详情面板快捷按钮（仅合并项目显示）

### 审计作业平台新增代码结构 (audit-platform/)

#### 项目根目录新增文件
- `.env` / `.env.example` — Docker Compose 环境变量（16个变量：PG/Redis/JWT/CORS/ONLYOFFICE/Storage）
- `docker-compose.yml` — 4服务编排（postgres:16-alpine + redis:7-alpine + backend本地构建 + onlyoffice/documentserver:8.2），健康检查+依赖启动顺序
- `storage/poc/` — WOPI POC 测试文件目录（含 test.xlsx 和 README.md）

#### 后端新增文件 (backend/)
- `backend/Dockerfile` — python:3.12-slim，uvicorn 启动
- `backend/app/core/config.py` — pydantic-settings Settings 类（DATABASE_URL/REDIS_URL/JWT_SECRET_KEY 等12项，extra="ignore"）
- `backend/app/core/database.py` — SQLAlchemy 2.0 异步引擎（pool_size=10, max_overflow=20）+ get_db 依赖注入
- `backend/app/core/redis.py` — redis.asyncio 连接池 + get_redis 依赖注入
- `backend/app/core/security.py` — JWT 编解码（access 2h + refresh 7d）+ bcrypt 密码哈希（cost=12）
- `backend/app/models/base.py` — DeclarativeBase + SoftDeleteMixin + TimestampMixin + AuditMixin + 5个枚举（UserRole/ProjectType/ProjectStatus/ProjectUserRole/PermissionLevel）
- `backend/app/models/core.py` — 5张核心表（User/Project/ProjectUser/Log/Notification）+ wizard_state JSONB列
- `backend/app/models/audit_platform_models.py` — 12张MVP核心表（AccountChart/AccountMapping/TbBalance/TbLedger/TbAuxBalance/TbAuxLedger/Adjustment/TrialBalance/Materiality/ImportBatch/AdjustmentEntry/UnadjustedMisstatement）+ ReportLineMapping表 + 10个枚举（含ReportType/ReportLineMappingType/MisstatementType）
- `backend/app/models/audit_platform_schemas.py` — 60+个Pydantic Schema（BasicInfoSchema/WizardState/MappingInput/MappingSuggestion/ImportProgress/AdjustmentCreate/AdjustmentUpdate/MaterialityInput/MaterialityResult/BalanceFilter/LedgerFilter/TrialBalanceRow/ConsistencyReport/MisstatementCreate/MisstatementSummary/ThresholdResult/EventPayload 等10个模块）
- `backend/app/models/report_models.py` — 8张报表相关表ORM模型（ReportConfig/FinancialReport/CfsAdjustment/DisclosureNote/AuditReport/AuditReportTemplate/ExportTask/NoteValidationResult）+ 10个枚举（FinancialReportType/CashFlowCategory/ContentType/SourceTemplate/NoteStatus/OpinionType/CompanyType/ReportStatus/ExportTaskType/ExportTaskStatus）
- `backend/app/models/report_schemas.py` — 报表模块Pydantic Schema（ReportRow/ReportDrilldown/CFSWorksheetData/CFSAdjustmentCreate/DisclosureNoteTree/NoteValidationFinding/AuditReportGenerate/ExportTaskCreate等7个API模块）
- `backend/app/schemas/auth.py` — LoginRequest/TokenResponse/RefreshRequest/UserCreate/UserResponse
- `backend/app/schemas/common.py` — ApiResponse[T] + ErrorResponse
- `backend/app/services/auth_service.py` — login（Redis失败计数+锁定）/refresh/logout/create_user/get_current_user_profile
- `backend/app/services/wopi_service.py` — WOPI Host（check_file_info/get_file/put_file，存储 {STORAGE_ROOT}/poc/）
- `backend/app/api/auth.py` — POST login/refresh/logout
- `backend/app/api/users.py` — POST / (admin only) + GET /me
- `backend/app/api/health.py` — GET /health（PG SELECT 1 + Redis PING，200/503）
- `backend/app/api/wopi.py` — WOPI CheckFileInfo/GetFile/PutFile
- `backend/app/deps.py` — get_current_user + require_role + require_project_access（edit>review>readonly层级）
- `backend/app/middleware/response.py` — ResponseWrapperMiddleware（2xx JSON→{"code","message","data"}，跳过/docs/wopi）
- `backend/app/middleware/error_handler.py` — HTTPException/ValidationError/通用Exception 三级处理
- `backend/app/middleware/audit_log.py` — AuditLogMiddleware（POST/PUT/PATCH/DELETE→logs表，异步写入不阻断响应）
- `backend/app/main.py` — FastAPI 入口（异常处理器+中间件LIFO注册+lifespan事件处理器注册+20路由模块：auth/users/health/wopi/project_wizard/account_chart/mapping/report_line_mapping/data_import/drilldown/trial_balance/adjustments/materiality/misstatements/events/formula/wp_template/working_paper/qc/wp_review/sampling）
- `backend/alembic/` — Alembic 异步迁移配置 + 8个迁移脚本（001_init_core_tables + 002_mvp_core_tables + 003_report_line_mapping + 004_adjustment_entries + 005_unadjusted_misstatements + 006_report_tables + 007_workpaper_tables + 008_sampling_tables）
- `backend/app/services/project_wizard_service.py` — 项目向导服务（create_project/get_wizard_state/update_step/validate_step/confirm_project，步骤依赖链校验，断点续做）
- `backend/app/services/account_chart_service.py` — 科目表服务（load_standard_template 从JSON种子数据加载/import_client_chart CSV+Excel解析/get_standard_chart/get_client_chart_tree 树形构建）
- `backend/app/routers/project_wizard.py` — 项目向导API（POST创建/GET状态/PUT更新步骤/POST校验/POST确认）
- `backend/app/routers/account_chart.py` — 科目表API（GET标准科目/POST导入客户科目/GET客户科目树）
- `backend/app/services/mapping_service.py` — 科目映射服务（auto_suggest 4级优先匹配/save_mapping/batch_confirm/get_completion_rate含unmapped_with_balance/update_mapping/get_mappings，用difflib.SequenceMatcher+Jaccard模糊匹配）
- `backend/app/routers/mapping.py` — 科目映射API（POST auto-suggest/GET列表/POST保存/PUT修改/POST批量确认/GET完成率）
- `backend/app/services/report_line_mapping_service.py` — 报表行次映射服务（ai_suggest_mappings规则匹配占位/confirm_mapping/batch_confirm/reference_copy/inherit_from_prior_year/get_mappings/get_report_lines）
- `backend/app/routers/report_line_mapping.py` — 报表行次映射API（POST ai-suggest/GET列表/PUT确认/POST批量确认/POST参照复制/GET报表行次）
- `backend/app/services/import_engine/__init__.py` — 导入引擎包
- `backend/app/services/import_engine/parsers.py` — 解析器工厂（BaseParser/GenericParser/YonyouParser/KingdeeParser/SAPParser，支持CSV+Excel四表数据，中英文列名映射）
- `backend/app/services/import_engine/validation.py` — 校验引擎（ValidationEngine责任链+7条规则：YearConsistency/DebitCreditBalance/Duplicate/OpeningClosing/AccountCompleteness/LedgerBalanceReconcile/AuxMainReconcile）
- `backend/app/services/import_service.py` — 导入服务（start_import同步导入+校验+批量写入/get_import_progress/rollback_import/queue_unmapped）
- `backend/app/routers/data_import.py` — 数据导入API（POST导入/GET进度/GET批次列表/POST回滚）
- `backend/data/standard_account_chart.json` — 企业会计准则标准科目种子数据（120个科目，一级+二级，5大类别）
- `backend/tests/conftest.py` — SQLite内存测试数据库+fakeredis+httpx AsyncClient+事务回滚隔离
- `backend/tests/test_response_middleware.py` — 7个测试
- `backend/tests/test_error_handler.py` — 7个测试
- `backend/tests/test_audit_log_middleware.py` — 28个测试
- `backend/tests/test_health.py` — 4个测试
- `backend/tests/test_wopi.py` — 12个测试
- `backend/tests/test_migration_002.py` — 47个测试
- `backend/tests/test_project_wizard_service.py` — 16个测试（向导服务：创建/状态/更新步骤/依赖校验/确认）
- `backend/tests/test_project_wizard_router.py` — 10个测试（向导API端点）
- `backend/tests/test_account_chart_service.py` — 15个测试（标准科目加载/客户科目导入/树形结构）
- `backend/tests/test_mapping_service.py` — 21个测试（auto_suggest/save/batch_confirm/completion_rate/update/get_mappings/fuzzy helpers）
- `backend/tests/test_report_line_mapping.py` — 19个测试（ai_suggest/confirm/batch_confirm/reference_copy/inherit/get_mappings/get_report_lines）
- `backend/tests/test_import_engine.py` — 37个测试（GenericParser四表解析/ParserFactory/7条校验规则/ImportService导入+回滚+进度+批次列表）
- `backend/app/services/drilldown_service.py` — 四表穿透查询服务（get_balance_list分页+筛选/drill_to_ledger/drill_to_aux_balance/drill_to_aux_ledger）
- `backend/app/routers/drilldown.py` — 穿透查询API（GET balance/GET ledger/{code}/GET aux-balance/{code}/GET aux-ledger/{code}）
- `backend/app/services/trial_balance_service.py` — 试算表计算引擎（recalc_unadjusted增量+全量/recalc_adjustments/recalc_audited/full_recalc/check_consistency/事件处理器on_adjustment_changed/on_mapping_changed/on_data_imported/on_import_rolled_back）
- `backend/app/routers/trial_balance.py` — 试算表API（GET试算表含重要性高亮/POST recalc/GET consistency-check）
- `backend/app/services/adjustment_service.py` — 调整分录服务（create_entry借贷平衡+自动编号+科目校验/update_entry/delete_entry/change_review_status状态机/get_summary/list_entries/get_account_dropdown报表行次级联/get_wp_adjustment_summary底稿审定表/事件发布）
- `backend/app/routers/adjustments.py` — 调整分录API（GET列表/POST创建/PUT修改/DELETE软删除/POST review/GET summary/GET account-dropdown/GET wp-summary）
- `backend/app/services/materiality_service.py` — 重要性水平服务（calculate三级计算/auto_populate_benchmark从试算表取基准/override手动覆盖+变更历史/get_current/get_change_history）
- `backend/app/routers/materiality.py` — 重要性水平API（GET获取/POST calculate/PUT override/GET history/GET benchmark）
- `backend/app/services/event_bus.py` — 进程内事件总线（asyncio，publish/subscribe/SSE队列管理，全局单例event_bus）
- `backend/app/services/event_handlers.py` — 事件处理器注册（lifespan启动时注册，工厂函数创建带独立DB会话的处理器）
- `backend/app/routers/events.py` — SSE事件流API（GET /events/stream，按project_id过滤，30s心跳）
- `backend/app/services/misstatement_service.py` — 未更正错报服务（create_misstatement/create_from_rejected_aje/get_summary按类型分组+重要性对比/get_cumulative_amount/check_materiality_threshold超限预警/carry_forward上年结转/check_evaluation_completeness）
- `backend/app/routers/misstatements.py` — 未更正错报API（GET列表/POST创建/POST from-aje/PUT更新/DELETE软删除/GET summary）
- `backend/tests/test_drilldown.py` — 13个测试（余额表筛选+分页/序时账日期+摘要+对方科目筛选/辅助余额穿透/辅助明细筛选）
- `backend/tests/test_trial_balance.py` — 8个测试（未审数全量+增量/调整列/审定数/全量重算/一致性校验/多对一映射）
- `backend/tests/test_adjustments.py` — 28个测试（CRUD+借贷平衡+自动编号+科目校验+复核状态机+汇总+API端点+科目下拉+底稿审定表）
- `backend/tests/test_materiality.py` — 23个测试（三级计算+自动取基准4种类型+手动覆盖+变更历史+API端点）
- `backend/tests/test_event_bus.py` — 14个测试（EventBus基础+SSE队列+事件处理器联动+AdjustmentService事件发布集成）
- `backend/tests/test_misstatements.py` — 18个测试（CRUD+从AJE创建+累计金额+汇总+超限预警+评价完整性+上年结转+API端点）
- `backend/tests/test_report_models.py` — 13个测试（8张报表表CRUD+枚举类型验证）
- `backend/app/services/report_config_service.py` — 报表配置服务（load_seed_data幂等加载/clone_report_config项目级克隆/list_configs/get_config/update_config）
- `backend/app/routers/report_config.py` — 报表配置API（GET列表/GET详情/POST克隆/PUT修改/POST加载种子数据）
- `backend/data/report_config_seed.json` — 四张报表种子数据（BS 44行+IS 21行+CFS 46行+EQ 10行，含TB/SUM_TB/ROW公式）
- `backend/app/services/report_engine.py` — 报表生成引擎（ReportFormulaParser regex解析+ReportEngine generate_all_reports/regenerate_affected/check_balance/drilldown/on_trial_balance_updated）
- `backend/app/routers/reports.py` — 报表API（POST生成/GET报表数据/GET穿透/GET一致性校验/GET导出Excel）
- `backend/tests/test_report_config.py` — 16个测试（种子数据加载+四张报表行次验证+公式语法+克隆+API端点）
- `backend/tests/test_report_engine.py` — 28个测试（公式解析器TB/SUM_TB/ROW/算术+报表生成+平衡校验+增量更新+穿透查询+API端点）
- `backend/app/services/cfs_worksheet_engine.py` — 现金流量表工作底稿引擎（generate_worksheet/auto_generate_adjustments/CRUD/get_reconciliation_status/generate_cfs_main_table/generate_indirect_method/verify_reconciliation）
- `backend/app/routers/cfs_worksheet.py` — CFS工作底稿API（11个端点：生成/获取/CRUD调整分录/平衡状态/自动生成/间接法/勾稽校验/主表）
- `backend/tests/test_cfs_worksheet.py` — 26个测试（工作底稿生成+自动调整+CRUD+平衡状态+主表+间接法+勾稽+API端点）
- `backend/app/services/disclosure_engine.py` — 附注生成引擎（generate_notes/update_note_values/on_reports_updated事件处理器）
- `backend/app/services/note_validation_engine.py` — 附注校验引擎（BalanceValidator/SubItemValidator等8种校验器+validate_all）
- `backend/app/routers/disclosure_notes.py` — 附注API（POST生成/GET目录树/GET章节/PUT更新/POST校验/GET校验结果/PUT确认发现）
- `backend/data/note_templates_seed.json` — 附注模版种子数据（6个关键科目的表格模板+校验预设）
- `backend/tests/test_disclosure_notes.py` — 17个测试（附注生成+编辑+校验+API端点）
- `backend/app/services/audit_report_service.py` — 审计报告服务（load_seed_templates/generate_report占位符填充/update_paragraph/refresh_financial_data/KAM校验/on_reports_updated事件处理器）
- `backend/app/routers/audit_report.py` — 审计报告API（POST生成/GET报告/PUT段落/GET模板/PUT状态/POST加载种子）
- `backend/data/audit_report_templates_seed.json` — 审计报告模板种子数据（4种意见×2种公司类型=8套，含7段落占位符）
- `backend/tests/test_audit_report.py` — 25个测试（模板加载+报告生成+占位符填充+段落编辑+KAM校验+状态更新+API端点）
- `backend/app/services/pdf_export_engine.py` — PDF导出引擎（render_document HTML渲染+WeasyPrint可选回退HTML/create_export_task/execute_export同步MVP/get_task_status/get_history）
- `backend/app/routers/export.py` — PDF导出API（POST创建任务/GET状态/GET下载/GET历史）
- `backend/tests/test_pdf_export.py` — 15个测试（HTML渲染+导出任务CRUD+API端点）
- `backend/app/models/workpaper_models.py` — 8张底稿相关表+2张抽样表ORM模型（WpTemplate/WpTemplateMeta/WpTemplateSet/WpIndex/WorkingPaper/WpCrossRef/WpQcResult/ReviewRecord/SamplingConfig/SamplingRecord）+ 9个枚举（WpTemplateStatus/RegionType/WpStatus/WpSourceType/WpFileStatus/ReviewCommentStatus/SamplingType/SamplingMethod/ApplicableScenario）
- `backend/app/models/workpaper_schemas.py` — 底稿模块Pydantic Schema（TemplateUpload/TemplateResponse/WPFilter/WPResponse/FormulaRequest/FormulaResult/QCFinding/QCResult/QCSummary/ReviewCommentCreate/ReviewReply/WOPIFileInfo/SamplingConfigCreate/SamplingConfigResponse/SamplingRecordCreate/SamplingRecordResponse/MUSEvaluation/SampleSizeCalculation等8个API模块）
- `backend/tests/test_workpaper_models.py` — 16个测试（8张底稿表CRUD+枚举类型验证+复核流程）
- `backend/app/services/formula_engine.py` — 取数公式引擎（FormulaEngine execute/batch_execute/invalidate_cache+TBExecutor/WPExecutor stub/AUXExecutor/PREVExecutor/SumTBExecutor+Redis缓存TTL=5min+FormulaError错误处理）
- `backend/app/routers/formula.py` — 取数公式API（POST execute/POST batch-execute）
- `backend/tests/test_formula_engine.py` — 35个测试（5种Executor+缓存+错误处理+批量执行+API端点）
- `backend/app/services/template_engine.py` — 底稿模板引擎（upload_template/create_version/delete_template引用校验/template_set CRUD+6个内置种子集/generate_project_workpapers）
- `backend/app/routers/wp_template.py` — 底稿模板API（11个端点：模板CRUD+版本+模板集CRUD+种子+项目底稿生成）
- `backend/tests/test_template_engine.py` — 28个测试（模板上传+Named Ranges+版本管理+删除校验+模板集+项目底稿生成+API端点）
- `backend/app/services/prefill_service.py` — 预填充与解析服务（PrefillService._scan_formulas regex+prefill_workpaper stub+ParseService.parse_workpaper stub+detect_conflicts版本比对）
- `backend/tests/test_prefill_parse.py` — 10个测试（公式扫描+预填充stub+解析stub+冲突检测）
- `backend/app/services/wopi_service.py` — WOPI Host服务（重写：WOPIHostService check_file_info从working_paper取元数据/get_file stub/put_file版本递增+内存锁管理lock/unlock/refresh_lock+JWT访问令牌generate/validate+clear_locks测试辅助）
- `backend/app/api/wopi.py` — WOPI API路由（重写：支持UUID working_paper模式+旧版POC文件模式双模式，新增Lock/Unlock/RefreshLock via X-WOPI-Override头）
- `backend/app/services/working_paper_service.py` — 底稿管理服务（list_workpapers筛选/get_workpaper含QC状态/download_for_offline stub/upload_offline_edit冲突检测+版本递增/update_status+状态映射/assign_workpaper）
- `backend/app/routers/working_paper.py` — 底稿管理API（10个端点：列表/详情/下载/上传/状态/分配/预填充/解析/索引/交叉引用）
- `backend/app/services/qc_engine.py` — QC引擎（QCRule抽象基类+QCContext+QCEngine.check执行12条规则+get_project_summary项目汇总，3阻断+8警告+1提示规则均为stub）
- `backend/app/routers/qc.py` — QC API（POST qc-check/GET qc-results/GET qc-summary）
- `backend/app/services/wp_review_service.py` — 复核批注服务（add_comment status=open/reply open→replied/resolve open|replied→resolved/list_reviews按状态筛选）
- `backend/app/routers/wp_review.py` — 复核批注API（GET列表/POST添加/PUT reply/PUT resolve）
- `backend/tests/test_wopi_working_paper_qc_review.py` — 62个测试（WOPI Host 15个+底稿管理11个+QC引擎7个+复核批注9个+事件处理器2个+API路由18个）
- `backend/app/services/sampling_service.py` — 抽样管理服务（SamplingService：calculate_sample_size属性/MUS/随机公式+create_config自动计算样本量+create_record+calculate_mus_evaluation污染因子+推断错报+上限+check_completeness供QC Rule 10+list/update CRUD）
- `backend/app/routers/sampling.py` — 抽样管理API（8个端点：GET/POST/PUT sampling-configs+POST calculate+GET/POST/PUT sampling-records+POST mus-evaluate）
- `backend/alembic/versions/008_sampling_tables.py` — 抽样表迁移（sampling_config+sampling_records+3个枚举）
- `backend/tests/test_sampling.py` — 46个测试（样本量计算14个+Config CRUD 5个+Record CRUD 5个+MUS评价6个+完整性检查5个+API端点11个）
- `backend/requirements.txt` — 新增 fastapi/uvicorn/sqlalchemy[asyncio]/asyncpg/alembic/pydantic-settings/email-validator/redis/python-jose/passlib/httpx/python-multipart/openpyxl + pytest/pytest-asyncio/fakeredis/aiosqlite

#### 前端新增文件 (audit-platform/frontend/)
- Vue 3 + TypeScript + Vite 项目骨架（与现有 React frontend/ 分离）
- `package.json` — vue/vue-router/pinia/element-plus/axios
- `vite.config.ts` — /api 和 /wopi 代理到 localhost:8000
- `src/styles/gt-tokens.css` — GT 品牌 CSS 变量（7色+6间距+3圆角+4字体+3阴影）
- `src/styles/global.css` — Element Plus 主题覆盖 + gt- 前缀工具类
- `src/router/index.ts` — /login + / (Dashboard) + /projects + /projects/new (ProjectWizard) + /poc + 404，beforeEach 认证守卫，含底稿模块3条路由+报表模块10条路由
- `src/stores/auth.ts` — Pinia useAuthStore（login/logout/refreshAccessToken/fetchUserProfile，localStorage 持久化）
- `src/utils/http.ts` — Axios 封装（Bearer token 自动附加 + 401 refresh 队列 + ElMessage 错误提示）
- `src/layouts/DefaultLayout.vue` — ElAside 侧边栏 + ElHeader + ElMain
- `src/views/Login.vue` — 登录表单（ElForm 校验 + POST /api/auth/login）
- `src/views/Dashboard.vue` — 仪表盘占位（3个统计卡片）
- `src/views/Projects.vue` — 项目列表占位
- `src/views/NotFound.vue` — 404 页面
- `src/views/WopiPoc.vue` — ONLYOFFICE WOPI POC 页面（iframe 编辑器 + 配置面板）
- `src/views/ProjectWizard.vue` — 项目向导页面（6步el-steps+动态内容区+上一步/下一步/确认按钮）
- `src/stores/wizard.ts` — Pinia向导状态管理（createProject/loadWizardState/saveStep/confirmProject/goNext/goPrev）
- `src/components/wizard/BasicInfoStep.vue` — 步骤1基本信息表单（6字段+ElForm校验+年度DatePicker+store恢复）
- `src/components/wizard/AccountImportStep.vue` — 步骤2科目导入（el-upload拖拽+导入结果分类标签+el-tree客户科目树）
- `src/components/wizard/AccountMappingStep.vue` — 步骤3科目映射（三栏布局：客户科目|映射状态+手动下拉|标准科目，自动匹配+批量确认+完成率进度条+未映射余额警告）
- `src/components/wizard/MaterialityStep.vue` — 步骤4重要性水平（基准类型选择+参数输入+从试算表取数+实时计算三级指标+手动覆盖折叠面板）
- `src/components/wizard/TeamAssignmentStep.vue` — 步骤5占位（待实现）
- `src/components/wizard/ConfirmationStep.vue` — 步骤6确认汇总（基本信息详情+各步骤完成状态标签）
- `src/components/wizard/ReportLineMappingStep.vue` — 报表行次映射独立页面（AI建议列表+确认/拒绝+一键参照+报表类型筛选）
- `src/components/import/DataImportPanel.vue` — 数据导入面板（文件上传+数据源/类型选择+进度显示+批次列表+回滚）
- `src/views/Drilldown.vue` — 四表穿透页面（面包屑导航+余额表筛选+序时账筛选+辅助余额/明细穿透+分页）
- `src/stores/drilldown.ts` — Pinia穿透查询状态管理（fetchBalance/drillToLedger/drillToAuxBalance/drillToAuxLedger/navigateTo/reset）
- `src/views/TrialBalance.vue` — 试算表页面（按类别分组+小计行+合计行+借贷平衡指示器+重要性高亮+未审数穿透+调整明细弹窗+全量重算+一致性校验+导出）
- `src/views/Adjustments.vue` — 调整分录页面（AJE/RJE Tab切换+汇总面板+CRUD弹窗动态行+借贷差额实时显示+批量审批/驳回+驳回原因弹窗）
- `src/views/Materiality.vue` — 重要性水平独立页面（双栏布局：左表单+右结果卡片+手动覆盖+变更历史表格）
- `src/views/Misstatements.vue` — 未更正错报页面（重要性对比卡片+超限预警横幅+按类型分组小计+CRUD弹窗+管理层原因/审计师评价编辑）
- `src/services/auditPlatformApi.ts` — API服务层（试算表/调整分录/重要性水平/未更正错报/报表/CFS工作底稿/附注/审计报告/PDF导出/SSE事件全部API封装+TypeScript类型定义，约50个函数）
- `src/router/index.ts` — 新增10个路由：/projects/:id/drilldown + trial-balance + adjustments + materiality + misstatements + reports + cfs-worksheet + disclosure-notes + audit-report + pdf-export
- `src/views/ReportView.vue` — 报表查看页（四张报表Tab切换+格式化表格行缩进/合计高亮+穿透弹窗+一致性校验+Excel导出）
- `src/views/CFSWorksheet.vue` — 现金流量表工作底稿页（工作底稿表格+调整分录CRUD+间接法补充资料+勾稽校验面板）
- `src/views/DisclosureEditor.vue` — 附注编辑页（三栏：左目录树+中编辑区表格/文字+右校验结果面板按severity分色）
- `src/views/AuditReportEditor.vue` — 审计报告编辑页（三栏：段落导航+编辑器+财务数据引用面板+意见类型/公司类型选择生成）
- `src/views/PDFExportPanel.vue` — PDF导出面板（文档勾选+密码保护+进度条轮询+历史记录列表+下载）
- `src/views/WorkpaperList.vue` — 底稿列表页（左侧el-tree按审计循环分组B/C/D-N+状态标签+右侧详情面板el-descriptions+操作按钮在线编辑/下载/上传/自检/提交复核+顶部筛选栏循环/状态/编制人+QC结果摘要）
- `src/views/WorkpaperEditor.vue` — ONLYOFFICE编辑器页（全屏iframe+顶部工具栏底稿编号名称状态返回+底部状态栏编制人复核人版本+降级模式检测不可用时显示下载编辑按钮+el-alert警告）
- `src/views/TemplateManager.vue` — 模板管理页（el-tabs模板列表+模板集，模板表格编号/名称/循环/版本/状态+新版本/查看/删除操作，模板集表格名称/模板数/适用类型+编辑/查看，上传模板弹窗）
- `src/components/workpaper/QCResultPanel.vue` — 质量自检结果弹窗（按severity三级分组blocking红/warning黄/info灰+每条finding规则编号+描述+可点击单元格引用+期望/实际值+提交复核按钮阻断时禁用）
- `src/components/workpaper/QCSummaryCard.vue` — QC汇总卡片（5指标total/passed/blocking/not_started/pass_rate+点击钻取事件）
- `src/components/workpaper/SamplingPanel.vue` — 抽样管理面板（双Tab抽样配置+抽样记录，配置表格+创建/编辑弹窗方法选择+参数+自动计算样本量，记录表格+CRUD+MUS评价结果展示）
- `src/services/workpaperApi.ts` — 底稿模块API服务层（模板管理8个+取数公式2个+底稿管理10个+QC 3个+复核批注4个+WOPI URL构造+抽样管理8个，共35+个函数+TypeScript类型定义）
- `src/router/index.ts` — 新增3个底稿路由：/projects/:id/workpapers + /projects/:id/workpapers/:wpId/edit + /projects/:id/templates

#### ONLYOFFICE POC 文件
- `onlyoffice/custom-functions/tb-function.js` — TB(account_code, column_name) 自定义函数（XHR→后端API取数）
- `onlyoffice/plugins/audit-sidebar/` — 审计侧边栏插件（config.json + index.html + index.js，静态底稿信息/复核状态/操作日志）
- `onlyoffice/plugins/audit-formula/` — 审计取数函数插件（config.json + index.html + code.js，注册TB/WP/AUX/PREV/SUM_TB五个自定义函数，同步XHR调用后端Formula API，中文列名映射，#REF!错误处理）
- `onlyoffice/plugins/audit-review/` — 审计复核批注侧边栏插件（config.json + index.html + index.js，复核意见列表+添加/回复/解决操作，珊瑚橙#FF5149未解决+水鸭蓝#0094B3已回复+绿色#28a745已解决左边框，30秒自动刷新）

#### Phase 8 Extension 新增后端文件
- `backend/app/schemas/extension.py` — 扩展模型Pydantic Schemas（AccountingStandard/SignatureRecord/CustomTemplate/RegulatoryFiling/GTWPCoding/AIPlugin 各含Create/Update/Response）
- `backend/app/schemas/core.py` — 核心模型扩展Schemas（UserCreateExtended/UserResponseExtended含language、ProjectCreateExtended/ProjectUpdateExtended含accounting_standard_id、ExtendedAuditType枚举）
- `backend/app/services/regulatory_service.py` — 监管对接服务（submit_cicpa_report/submit_archival_standard/check_filing_status/handle_filing_response/retry_filing/list_filings，状态机submitted→pending→approved/rejected，最大重试3次）
- `backend/app/routers/regulatory.py` — 监管对接API（6个端点：POST cicpa-report/archival-standard、GET filings/{id}/status、POST filings/{id}/retry/response、GET filings列表）
- `backend/app/services/i18n_service.py` — 多语言服务（TRANSLATIONS中英翻译字典+AUDIT_TERMS审计术语+set_user_language）
- `backend/app/routers/i18n.py` — 多语言API（GET languages/translations/{lang}/audit-terms/{lang}、PUT users/{id}/language）
- `backend/app/services/audit_type_service.py` — 审计类型服务（6种审计类型+推荐配置含模板集/程序/报告模板）
- `backend/app/routers/audit_types.py` — 审计类型API（GET audit-types、GET audit-types/{type}/recommendation）
- `backend/app/services/sign_service.py` — 电子签名服务（sign_document三级签名+verify_signature+get_signatures+revoke_signature）
- `backend/app/routers/signatures.py` — 电子签名API（POST sign、GET {type}/{id}、POST verify/revoke）
- `backend/app/services/ai_plugin_service.py` — AI插件服务（8个PluginExecutor stub+PLUGIN_EXECUTORS映射+execute_plugin方法+load_preset_plugins幂等加载）
- `backend/app/routers/ai_plugins.py` — AI插件API（GET列表、POST enable/disable、PUT config、GET presets、POST seed）
- `backend/tests/test_extension_services.py` — 77个测试（5个服务+5个API测试类）
- `backend/tests/test_regulatory_service.py` — 44个测试（备案提交/状态跟踪/重试/列表/API端点+AI插件Executor stub）
- `backend/data/multi_standard_charts.json` — 5种会计准则标准科目表（CAS引用/CAS_SMALL~60/GOV~49/FIN~61/IFRS~45）
- `backend/data/multi_standard_report_formats.json` — 5种准则×4张报表格式配置（BS/IS/CFS/EQ行次+公式）
- `backend/data/multi_standard_note_templates.json` — 5种准则附注模版配置（每种~10节）
- `backend/data/gt_template_library.json` — 致同底稿模板目录（70+条，覆盖B/C/D-N/Q/A/S/T/Z全类型）
- `backend/data/note_template_soe.json` — 国企版附注模版（40节，含科目对照/校验公式/宽表公式/正文模版）
- `backend/data/note_template_listed.json` — 上市版附注模版（45节，更详细披露要求）
- `backend/app/services/note_formula_engine.py` — 附注校验公式引擎（8种校验器：BalanceCheck/WideTableHorizontal/VerticalReconcile/CrossCheck/SubItemCheck/AgingTransition/CompletenessCheck/LLMReview stub + validate_note双层架构）
- `backend/app/services/note_template_service.py` — 附注模版自定义服务（CRUD+版本管理+回滚+SOE/Listed加载，文件存储~/.gt_audit_helper/note_templates/custom/）
- `backend/app/routers/note_templates.py` — 附注模版API（9个端点：POST validate/GET soe/GET listed/自定义CRUD/versions/rollback）
- `audit-platform/frontend/src/i18n/index.ts` — 轻量级i18n框架（useI18n composable，无vue-i18n依赖，t()翻译+setLocale切换+localStorage持久化+zh-CN回退）
- `backend/tests/test_multi_standard_notes.py` — 65个测试（多准则科目表/报表格式/附注模版+GT模板目录+SOE/Listed模版+8种校验器+自定义模版CRUD+API端点）
- `backend/tests/test_custom_dsl_coding.py` — 32个测试（公式DSL扩展+自定义编码CRUD+API端点）

#### Phase 8 Extension 新增前端文件
- `audit-platform/frontend/src/services/extensionApi.ts` — 扩展模块API服务层（会计准则/多语言/审计类型/自定义模板/电子签名/监管备案/致同编码/T型账户/AI插件全部API封装）
- `audit-platform/frontend/src/i18n/zh-CN.json` + `en-US.json` — 前端多语言翻译文件
- `audit-platform/frontend/src/components/extension/` — 30+个Vue组件（LanguageSwitcher/StandardSelector/AuditTypeSelector/TemplateUpload/TemplateValidator/SignatureLevel1-3/SignatureHistory/FilingStatus/FilingError/CICPAReportForm/ArchivalStandardForm/GTWPCodingTree/WPIndexGenerator/CustomCodingEditor/TAccountEditor/TAccountEntryForm/TAccountResult/PluginList/PluginConfig/ExternalAPIConfig/ModelSwitcher/DrillDownNavigator）
- `audit-platform/frontend/src/views/extension/` — 8个页面（CustomTemplateList/CustomTemplateEditor/TemplateMarket/SignatureManagement/RegulatoryFiling/GTCodingSystem/TAccountManagement/AIPluginManagement）
- `audit-platform/frontend/src/styles/` — 6个SCSS文件（gt-variables/gt-mixins/gt-typography/gt-markers/gt-print/gt-dark-mode）
- `audit-platform/frontend/src/router/index.ts` — 新增9条扩展路由（t-accounts/custom-templates/template-market/signatures/regulatory/gt-coding/ai-plugins）


## 技术决策（2026-04-12）
- deps.py 别名导出：`db = get_db`，供 consolidation 相关路由（使用 `db: Session = Depends(db)`）使用

## 技术决策（2026-04-13）
- config.py .env 路径修复：pydantic-settings 的 env_file 改为自动查找 backend/.env 和项目根目录 .env（向上回溯），解决从 backend/ 目录启动时找不到根目录 .env 的问题
- JWT_SECRET_KEY 默认值：从必填无默认改为 `dev-secret-key-change-in-production`，避免本地开发启动失败
- CORS_ORIGINS 类型修复：从 `list[str]` 改为 `str`（逗号分隔），main.py 中 split(",") 转列表；pydantic-settings 解析 .env 中的纯字符串 `http://localhost:5173` 会报 JSON 解析错误
- vite.config.ts 代理端口修复：proxy target 从 localhost:8001 改为 localhost:9980（匹配用户实际后端端口）
- CORS 默认源增加 localhost:3030 和 localhost:5173（前端开发端口）
- vite.config.ts 开发端口从 5173 改为 3030（与用户启动偏好一致），strictPort: false 允许自动递增
- .env REDIS_URL 修复：从 `redis://redis:6379/0`（Docker服务名）改为 `redis://localhost:6379/0`（本地开发）
- Alembic 多 head 冲突：迁移脚本 009-014 各有两个同名文件导致 `Multiple head revisions` 错误，暂用 `ALTER TABLE ADD COLUMN IF NOT EXISTS` 和 `CREATE TABLE IF NOT EXISTS` 直接补齐 Phase 8 变更，待后续合并迁移链
- Phase 8 手动创建的表（本地PG）：gt_wp_coding、t_accounts、t_account_entries、accounting_standards、signature_records、wp_template_custom、regulatory_filing、ai_plugins、attachments、attachment_working_paper；手动加的列：users.language、projects.accounting_standard_id/company_code/template_type/report_scope/parent_company_name/parent_company_code/ultimate_company_name/ultimate_company_code/parent_project_id/consol_level
- 测试用户：admin/admin123（role=admin）已创建，yangzhi/123456 密码已重置
- DefaultLayout 三栏路由判断：`/projects/new` 和 `/extension/*` 路径需特殊处理为全宽模式（hideMiddle=true, isBrowseMode=false），否则会被当成浏览模式显示 DetailProjectPanel 而非 router-view
- 合并报表集团架构信息放置方案：选择方案A（基本信息中展开折叠面板），不新增向导步骤；选择"合并报表"时自动展开"集团架构信息（三码体系）"折叠面板，填写上级企业名称/代码、最终控制方名称/代码；子公司清单和持股比例在后续"合并项目"模块中配置
- projects 表新增4列：parent_company_name/parent_company_code/ultimate_company_name/ultimate_company_code（合并报表三码体系），用 ALTER TABLE ADD COLUMN IF NOT EXISTS 直接加列
- 合并与单户联动架构：一个合并项目 = 一组单户项目 + 合并层；projects 表新增 parent_project_id（UUID FK→projects.id）和 consol_level（int 1-15）；前端用递归 ProjectTreeNode 组件构建树形列表，合并项目为父节点（紫色左边框+📁图标），单户项目为子节点
- 项目列表树形展示偏好：用 +/− 文字按钮展开/收起（非箭头图标），每级缩进20px，子节点区域左侧虚线连接线，最多15级嵌套
- UI 精致度偏好：状态色条不能太粗（2px+上下4px间距），合并项目左边框用浅紫色（primary-lighter）而非深紫色，整体要符合致同品牌规范的精致感
- 数据导入三阶段流程：上传→预览前20行+自动列映射→确认导入；后端 preview_file() API 返回 headers/rows/column_mapping/file_type_guess；前端每列上方 el-select 下拉按4组分类（科目/金额/凭证/辅助），已匹配绿✓未匹配橙⚠；_COLUMN_MAP 扩展到30+个中英文列名映射，支持自动识别科目表/序时账/余额表/辅助账4种文件类型
- 数据导入预览偏好：Excel 多 sheet 时每个 sheet 独立预览20行（el-tabs 卡片切换），默认跳过前2行（第3行作为表头，skip_rows=2）；_parse_excel 重构为 _parse_sheet + _parse_excel_multi_sheet
