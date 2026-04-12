---
inclusion: always
---

# 持久记忆

这是 Kiro 的自动记忆文件。每次对话开始时自动加载，提供跨会话的上下文连续性。

## 用户偏好
- 语言偏好：中文
- 部署偏好：倾向本地部署、轻量方案，避免重依赖
- 打包偏好：优先用 build_exe.py 打包为 EXE（PyInstaller），不要 .bat 脚本方式；打包前先 npm run build + 复制到 backend/static/，再 python build_exe.py --skip-frontend
- TTS 声音偏好：默认声音觉得难听，需要能自选男女声/角色，且支持自录音频替代 TTS
- PPT 生成偏好：必须用 ppt-generator skill 工作流（ppt_helpers.py 命令）生成，不要手写 JSON/HTML
- PPT 内容密度偏好：每页内容不要太少，要充实
- 审计报告复核 UI 偏好：问题列表需要按附注表格+问题类别两级折叠分组，支持组头 checkbox 批量操作，避免逐条勾选
- 附注表格标题识别偏好：紧邻表格的上一行段落就是表格标题（section_title），account_name 必须通过向上回溯编号标题确定，紧邻段落不能直接当 account_name，关键词提取只作兜底
- 聊天面板尺寸偏好：默认宽度页面1/4、高度100%满屏高（靠右贴边，顶部从0开始），支持拖动标题栏移动位置、右下角手柄缩放大小、最大化/还原切换；输入框默认3行（minHeight 64px）
- 聊天面板全局可见偏好：💬按钮需要在所有页面（首页+四大工作模块）都显示，不能只在首页；ChatPanel 已从 renderSelectMode 提升到 App.tsx 顶层所有 return 分支
- 聊天消息操作按钮布局偏好：📋📄✏️📌等按钮不能叠在气泡内右上角（会被文字遮挡看不清），必须放在气泡外下方显示
- 聊天面板窗口控制偏好：需要支持最大化/还原切换（⊞/⊡按钮），已实现 520×720 小窗 ↔ 全屏切换
- 聊天 AI 回复排版偏好：Markdown 渲染必须有清晰层次，不能一大段纯文本；system prompt 用「## 【重要】回复格式强制要求」+禁止性措辞+示例模板强制 LLM 分段输出；CSS 中 h1/h2 加底部分隔线、段落间距 10px、列表项间距 6px

## 项目上下文

### 基础环境
- Git 远程仓库：https://github.com/YZ1981-GT/GT_digao.git，全局 HTTP/HTTPS 代理 127.0.0.1:7897
- Python 3.12 虚拟环境 (.venv)，本地已安装 Docker 28.3.3、Ollama 0.11.10
- 使用 Kiro steering + hooks 机制管理工作流
- 四大模块统一架构：四/五步工作流 + SSE 流式通信 + LLM 驱动 + Word 导出
- 项目文件结构：主项目（审计工具 React+FastAPI） + audit-platform/ 子项目（Vue 3 + FastAPI 审计作业平台，分离的两个前后端）

### 项目根目录
- `start.bat` — 开发模式一键启动（前后端分离，后端9980+前端3030）
- `build_exe.py` — PyInstaller EXE 打包脚本（含系统托盘、自动找端口、.env 加载）
- `pack_portable.py` — 绿色便携包打包（核心 .py 编译为 .pyc 保护源码）
- `audit-platform/` — 审计作业平台（Phase 2 进行中）

### 资源目录
- `TSJ/` — 预置提示词库（约70个 Markdown，按会计科目分类）
- `GT_底稿/` — 审计底稿模板（D销售循环~M权益循环+Q关联方循环，致同底稿模板）
- `MinerU/` — MinerU PDF 解析工具（web_ui.py Web 界面）
- `附注模版/` — 附注模版体系（国企版/上市版）
- `致同通用审计程序及底稿模板（2025年修订）/` — 2025年修订版底稿

### 审计作业平台技术栈
- 后端：FastAPI + SQLAlchemy 2.0 异步 + PostgreSQL + Redis + Alembic 迁移
- 前端：Vue 3 + TypeScript + Vite + Pinia + Element Plus + Axios
- 底稿编辑器：ONLYOFFICE Document Server（AGPL，Docker 部署，WOPI 协议）
- AI：Ollama 本地，支持 DeepSeek/通义千问/Kimi 等多供应商 OpenAI 兼容 API

### 审计作业平台开发进度
- Phase 0（基础设施）：完成
- Phase 1 MVP Core（项目向导/科目映射/数据导入/穿透查询/试算表/调整分录/重要性水平/事件总线/未更正错报）：完成，后端326个测试通过
- Phase 1 MVP Report（报表生成/CFS工作底稿/附注生成校验/审计报告/PDF导出）：完成，后端466个测试通过
- Phase 1 MVP Workpaper（取数公式/模板引擎/WOPI/底稿管理/QC/复核批注/抽样）：完成，后端661个测试通过
- Phase 2 Consolidation（合并报表）：进行中，Task 11.1 MinorityInterestService 已完成，Task 11.2-11.3 待完成，Task 12-25 待完成

## 技术决策
- AI 记忆方案：Kiro steering + hook 轻量方案，memory.md 精简原则（不存文件清单），auto-save-memory hook 改为 userTriggered
- UTF-8 BOM 防御：所有 Python 脚本读取 JSON/HTML 文件统一用 `utf-8-sig` 编码
- Word 导出统一排版规范：仿宋_GB2312+Arial Narrow、页边距3/3.18/3.2/2.54cm、表格上下1磅边框无左右、高风险标红、页脚页码
- PowerShell 5.x 编码陷阱：Python 写给 PS5 的 .ps1 必须用 utf-8-sig（带 BOM）
- EXE 打包使用期限：build_exe.py launcher 最前面加过期检查，当前设为 2026-09-30
- gitpython 崩溃防御：prompt_git_service.py 和 build_exe.py 中设置 GIT_PYTHON_REFRESH=quiet
- 笔记库架构：knowledge_service.py 新增 'notes' 分类，按日期子文件夹管理
- 聊天框特殊字符：`/` 触发快捷指令，`@` 触发知识库引用（弹出候选列表）
- 前端 Markdown 渲染：react-markdown + remark-gfm + rehype-highlight；富文本复制用 unified pipeline + rehypeInlineStyles 内联样式
- 前端 tsconfig：不支持 Map 迭代需用 Record 代替
- 底稿复核编制单位提取：ReviewEngine._extract_entity_name() 从 content_text 前2000字符正则匹配
- 表头标准化：reconciliation_engine.py 中12处表头标准化统一加上 .replace("\n","").replace("\r","")
- 跨表交叉校验口径分离：check_cross_table_consistency 用 note_sections 分组合并/母公司口径
- SKIP_INTEGRITY_KEYWORDS：主要财务信息/重要合营联营企业/作为承租人/处于第/分部利润/政府补助/发放贷款/贷款和垫款/应收股利/吸收同业及存放/拆入资金/卖出回购/买入返售/财务费用/其他综合收益各项目
- 续表处理：首表+续表分别提取期末/期初值，续表不参与表格类型识别
- 母公司口径策略：只确认母公司口径是否有匹配，不主动用母公司余额去比对合并附注生成 finding
- account_name 长度防御：三层修复（report_parser 回溯增强+后端≤40字截断+前端≤30字截断）
- check_data_completeness 小计行误报修复：_is_total_row 新增 _summary_label_kw 列表跳过分类汇总行
- 附注表格数据全空时抑制「未提取到附注合计值」警告：全空跳过不报
- 三阶段ECL表纵向校验：区分阶段间转移行（直接累加）和普通减项行（需取反）

## 待办 / 进行中
- 项目文件清理（2026-04）：已删除根目录 `__pycache__/`、`frontend/README.md`；`GT_底稿/审计实务操作手册-框架.md` 和 `致同GT审计手册设计规范.md` 待确认是否删除
- 首页聊天功能：全部60个子任务已完成，待用户启动测试验收
- 审计作业平台 Phase 2 Consolidation：Task 11.2-11.3（generate_elimination+少数股东权益API路由）、Task 12-25 待完成
