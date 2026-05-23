---
inclusion: always
---

# 持久记忆

每次对话自动加载。详见 `#architecture` / `#conventions` / `#dev-history`。
保持本文件 ≤ 100 行：完成事项 → dev-history，技术决策 → architecture，规范/铁律 → conventions。

## 用户偏好

- 语言中文；本地优先轻量方案；启动 `start-dev.bat`（后端 9980 + 前端 3030）；打包 `build_exe.py`（PyInstaller，不要 .bat）
- **输出控制**：分步输出/修改，大改动拆小批次；不一次出过多内容
- 功能收敛：停加新功能，核心 6-8 页做到极致，空壳标 developing
- 前后端必须联动；删除二次确认 + 先进回收站；一次性脚本用完即删
- git 提交不分多区，单 commit 提交所有变更
- 提建议前先验证（不引用过时记录），反复论证给最仔细可落地方案
- 判断前端模块存在性必须同时检查 `views/` 根目录 + `components/` 子目录
- 文档同步：功能变更后同步更新需求文档
- 死代码立即删除，不留 DEPRECATED/fallback 注释
- 复杂重构先做 spec 三件套（体系化、精准、可回滚，"全部改完再跑一次测试"）
- 避免折中方案，要"根本解决"
- **彻底解决问题不调整错误呈现**：错误绝不"换个参数避开"，必须复现 + 定位根因 + 修主代码 + 加防御测试
- **文档标 ⚠️ 必须配套修复**：标注前评估能否本轮修复，可修则一次修完代码+文档+测试+memory；设计选择类用中性 📌 替代
- 完整复盘要诚实暴露问题不粉饰
- PDCA 迭代模式：建议→spec 三件套→实施→复盘→新需求；5 角色轮转（合伙人/项目经理/质控/审计助理/EQCR）
- 目标并发规模 6000 人
- 底稿编码：致同 2025 修订版 D/F/K/N 循环（`backend/data/wp_account_mapping.json` 206 条 v2025-R5）
- 审计循环代号：A=报表/调整 / B=控制了解 / C=控制测试 / D=销售收入 / E=货币资金 / F=采购存货 / G=投资 / H=固定资产+在建工程+使用权资产+租赁负债 / I=无形资产+商誉+开发支出 / J=职工薪酬+股份支付 / K=管理 / L=筹资 / M=股东权益 / N=税费 / S=专项程序

## UI 视觉偏好（详 #conventions）

- 表格列宽充足不折行不省略号；数字列统一 `.gt-amt`
- 表格选中行 ≥14% 透明度 + 左 3px 紫竖线 + hover 浅反馈
- 工具栏按钮合并到 Tab 栏右侧（不独占行）；简单 CRUD 不用 GtPageHeader 紫渐变
- 所有表格统一 el-table（底稿编辑器仍 Univer，不引入 AG Grid）
- 标准分页非"加载更多"；四表联查支持全屏+行选择+右键菜单
- 溯源/穿透跳转支持 Backspace 返回（DefaultLayout `initGlobalBackspace`）
- 表格编辑支持查看/编辑模式切换；复制按钮命名"复制整表" vs 右键"复制选中区域"

## 环境配置

- Python 3.12（.venv），Docker 28.3.3，PG 16（188 表），Redis 6379；后端 9980 / 前端 3030 / vLLM 8100
- 测试用户 admin/admin123（role=admin）；git 分支 feature/e2e-business-flow（HEAD）
- **数据库初始化命令**（2026-05-23 重命名后）：`python backend/scripts/init_tables.py` + `python backend/scripts/create_admin.py`（旧 `_init_tables.py` / `_create_admin.py` 已重命名，文档/spec 引用已同步）
- **scripts 命名规约**：`_` 前缀 = 一次性脚本（用完即删），无前缀 = 正式工具（保留可复用）；本轮清理 backend/scripts 65→49 / scripts/ 19→14
- **docs 目录新结构**（2026-05-23 重组）：从平铺 29 文件 → 8 子目录（`adr/` / `architecture/` / `deployment/` / `reference/` / `frontend/` / `operations/` / `proposals/` / `templates/`）+ 顶层 `README.md` 索引 + `requirements.md`；新增文档必须按子目录归类不要平铺；文件名英文小写连字符；活跃代码引用 14 处已同步更新
- **双 storage 目录职责**（2026-05-23 厘清）：仓库根 `storage/projects/{UUID}/workpapers/` = 底稿文件落地（DB `working_papers.file_path` 引用）+ `storage/consume` 是 docker-compose Paperless 挂载点；`backend/storage/{knowledge,projects,users,ledger_uploads}/` = 附件/知识库/上传文件落地；两边都 gitignored 但代码 hardcode 路径
- **空目录清理判定原则**：纯安装残骸（如 univer-server）= 直接删；运行时数据目录（storage 下 UUID 目录）即使空也不能简单删，必须先比对 DB 引用作"数据维护"，建议走 `cleanup_orphan_storage_dirs.py` dry-run 工具 + 回收站
- **程序规模**：后端 routers 271 / services 345 / models 58 / workers 12 / tests 464 / Alembic 61 + 28 SQL；前端 views 99 / components 353 / composables 81 / stores 9 / services 37 / utils 39
- **数据规模**：模板 456 / cross_wp_ref 400 / prefill 1035 cells / VR 114 条 / Spec 70
- **新增依赖（Phase 3+）**：locust / marked + dompurify / Storybook 8.6.14 / xlsx-js-style / decimal.js / python-docx / prometheus_client；外部 LibreOffice（4 路径 fallback，本地已装 2026-05-23）
- **文档/表格生成职责边界**（2026-05-23 厘清，禁止越界）：Univer Sheets = 底稿在线编辑（纯前端） / Univer Docs + TipTap + textarea 三级降级 = WorkpaperWordEditor 看 docx / python-docx = 程序化生成附注/EQCR/年报（内容可控可单测） / LibreOffice = 仅承担 docx+xlsx → PDF 转换（weasyprint 优先 → LibreOffice 降级，office_preview + archive_pdf_generators 共享 `_find_libreoffice`）；LibreOffice 不替换 python-docx 不接入编辑回环；6000 并发场景需队列化 + 信号量保护避免 soffice 被打挂；中文字体（仿宋/楷体_GB2312/宋体/Arial Narrow）必须装齐否则 PDF 出方块
- **底稿右栏附件 Tab**（2026-05-23 接入 AT-2）：`WorkpaperSidePanel` 附件 Tab = `AttachmentTabPanel`（列表 + 拖拽上传 + 点击预览） / `AttachmentPreviewDrawer` Office 文件走 `attachments.previewPdf` 端点 LibreOffice 转 PDF iframe，503 时降级下载提示（`officePreview.health` 探测结果模块级缓存避免重复打）；扩展点：模板库 `WpTemplateDetail` 主文件预览待接入同款管线

## 任务状态

### 全部已完成 spec ✅

11 审计循环（D~N，548/548）/ phase 1~7（239/239）/ phase 8（116 tests）/ proposal-remaining-18（30/30）/ k-admin-cycle-post-review-fix / partner-dashboard / procedure-trimming / role-view-switching / 角色体系治理（145 vitest）/ e2e-business-flow（58/58）/ template-library-coordination（64/64）/ audit-chain-generation（101/101）/ enterprise-linkage（56/56）/ **ledger-import-view-refactor（243/243）** —— 详见 INDEX.md。

小迭代 v2（2026-05-22 完成，详 #dev-history）：S-3 v2 JOIN 白名单 + DT-3 枚举覆盖 + AT-3 KB 版本接入，67 tests passed。

### 真正待办（外部依赖）

- LLM 真实接入：phase3 UAT-3 + K-1 / 6 stub 引擎（H/I/G/K/J/N，`settings.WP_AI_SERVICE_ENABLED` 一键切换）
- 6000 并发压测：phase3 UAT-5（需真 PG 大数据量 + Locust）
- W-3 钉钉/企微集成（外部对接）
- Sentinel failover 真实验证：phase4 UAT-8
- 业务测试：合并模块需真实项目（技术 85%/业务 60%）

## 关键引用指南

- 详细技术事实 / 端点速查 / PG schema → `#dev-history` grep 关键词
- 项目架构 / 系统规模 / 数据流 → `#architecture`
- 编码规范 / UI 规范 / Spec 工作流 / PG 运维铁律 / 批量入库脚本 → `#conventions`
- spec 状态总览 → `.kiro/specs/INDEX.md`

## 操作铁律（标题级，详细规则见 #conventions）

- **彻底解决不绕开**：错误必须复现+根因+修主代码+防御测试
- **三层一致校验**：DB 迁移 + ORM `Mapped[]` + service 方法，任一缺失即伪绿（AT-3 实战教训）
- **可复用脚本沉淀**：批量入库/UAT/迁移类工具放 `backend/scripts/{name}.py`（非 `_{tmp}.py`）配 docstring + 多场景；判定 = 操作目标可能再发生即保留
- **PG 运维**：SET 不支持绑定参数（用 set_config）/ superuser bypass RLS / CONCURRENTLY 必须 asyncpg raw conn + lock_timeout / 失败留 _ccnew 残骸需先 cleanup
- **PowerShell**：写中文/emoji 用 fsWrite 工具；`Out-File` 文件锁需先 Stop-Process powershell + 用 `cmd /c "... > log 2>&1"`
- **agent 调 service 优于 Playwright UI**：大文件入库直调 ledger_import 管线快 10x，Playwright 仅做前端可见性验证
- **历史档案不回填修改铁律**（2026-05-23 沉淀）：`.kiro/steering/dev-history.md` / `.kiro/specs/*/tasks.md` 等历史记录是 append-only 审计轨迹；做目录重组/路径迁移时**不回填**这些文档中的旧路径（保持时点准确性），只更新活跃代码 + 当前文档；判定边界 = "记录写入时该路径是真的吗" → 是即保留
