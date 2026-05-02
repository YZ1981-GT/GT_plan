---
inclusion: always
---

# 持久记忆

每次对话自动加载。详细架构见 `#architecture`，编码规范见 `#conventions`，开发历史见 `#dev-history`。

## 用户偏好（核心）

- 语言：中文
- 部署：本地优先、轻量方案
- 启动：`start-dev.bat` 一键启动后端 9980 + 前端 3030
- 打包：build_exe.py（PyInstaller），不要 .bat
- 功能收敛：停止加新功能，核心 6-8 个页面做到极致，空壳标记 developing
- 前后端联动：不能只开发后端不管前端
- 删除必须二次确认，所有删除先进回收站
- 一次性脚本用完即删
- 文档同步：功能变更后同步更新需求文档
- 记忆拆分：memory.md 只放精简状态+待办，技术决策→architecture.md，规范→conventions.md，修复记录→dev-history.md，每次对话自动拆分
- 底稿精细化：每个科目需要单独规则配套，利用 LLM 辅助
- 底稿体系展示：要体现 B→C→实质性的循环递进关系，可视化、逻辑感强，包括准备和完成阶段
- 目标并发规模 6000 人，在线编辑考虑混合方案：日常用纯前端表格组件（Luckysheet/Univer）无并发限制 + 少数完整 Excel 场景走 ONLYOFFICE

## 环境配置

- Python 3.12（.venv），Docker 28.3.3，Ollama 0.11.10
- PG 141 张表，Redis 6379，后端 9980，前端 3030
- vLLM Qwen3.5-27B-NVFP4 端口 8100（enable_thinking: false）
- ONLYOFFICE 端口 8080（JWT_ENABLED=false，WOPI 协议）
- Paperless-ngx 端口 8010（admin/admin）
- 测试用户：admin/admin123（role=admin）
- WOPI_BASE_URL 必须用 http://host.docker.internal:9980/wopi（Docker 容器内）
- uvicorn --reload-dir app（限制监控范围，避免 347 个 JSON 拖慢）
- MAX_UPLOAD_SIZE_MB=800 / MAX_REQUEST_BODY_MB=850

## 当前系统状态（2026-05-02）

- 17 个开发阶段中 16 个完成，仅合并报表前端存在 211 个 TS 错误（developing）
- 后端约700路由正常加载，0 个 stub 残留
- 审计员 8 步全流程理论可走通（导入-查账-调整-试算表-底稿-附注-报告-Word导出）
- 附注 8 种校验器全部做实，预设公式国企 757 条 + 上市 804 条已集成到引擎，QC 28 条规则全部做实
- 底稿精细化规则 347 个 JSON（77 个 A 级精修 + 270 个 C 级程序表），明细行动态发现（detail_discovery），全部 v2025-R2
- 报表 4 套 x 6 张，1191 行种子数据
- 附注模板国企 14 章 170 节 / 上市 17 章 185 节
- 公式体系完整（三分类 + 跨表引用 + 拓扑排序 + 审计留痕）
- 企业级治理完整（门禁/留痕/SoD/版本链/一致性复算）

## 活跃待办

- ~~附注校验公式从 md 导入~~ ✅ 已完成：国企 757 条 + 上市 804 条（继承国企版+差异+特有）
- ~~上市版校验公式仅 179 条需补全~~ ✅ 已完成：上市版继承国企版全部公式，差异公式替换/排除，特有公式追加
- ~~上市版五章 29 个无表格章节排查~~ ✅ 已排查：实际仅 3 个第五章空表格（F19/F22/F26 各 1-2 个子表），其余为政策描述型表格无需数据行
- 合并报表前端 211 个 TS 错误专项修复（2-3 周）
- 用真实审计项目端到端验证（最高优先级）
- ~~D2 应收账款 / H1 固定资产等更多科目精细化规则打磨~~ ✅ 已完成：77 个核心科目精修（全循环 D-N 覆盖），剩余 270 个为函证/控制测试/风险评估等无需 key_rows 精修
- ~~统一 Excel 导入框架~~ ✅ 已完成：7 种模板 + 7 页面集成 + 14 项加固（数值校验/事务保护/RFC5987文件名/示例行宽松跳过/失败行反馈/覆盖追加模式/重试按钮）

## 关键技术决策（速查）

- 事件驱动：EventBus debounce 500ms，调整-试算表-报表-附注-底稿五环联动
- 四式联动：Excel + HTML + Word + structure.json（权威数据源）
- 三层模板：事务所默认-集团定制-项目级应用
- 数据集版本：LedgerDataset staged-active-superseded
- 在线编辑：Univer 纯前端方案（2026-05-02），完整保存链路：前端 snapshot → POST /univer-save → xlsx 回写（univer_to_xlsx.py）+ structure.json + 版本快照 + 审计留痕 + 事件发布（五环联动）
- 新增后端服务：xlsx_to_univer.py（xlsx→IWorkbookData）+ univer_to_xlsx.py（IWorkbookData→xlsx 回写）
- 新增前端依赖：@univerjs/presets + @univerjs/preset-sheets-core + opentype.js
- Vite 配置：需要 alias `opentype.js/dist/opentype.module.js` → `opentype.js/dist/opentype.mjs`
- ONLYOFFICE 全面替换完成：WOPI/wopi_service 保留向后兼容，所有前端 ONLYOFFICE 引用已清除，WopiPoc/UniverTest 已删除
- 文件存储三阶段：本地磁盘（进行中）- Paperless（OCR/检索）- 云端（归档）
- 附注正文三级填充：上年附注-LLM 生成-模板默认文字
- RAG：llm_client.chat_completion 支持 context_documents 参数，截断 8000 字符
- asyncpg 时区：datetime.utcnow()（naive），不能用 timezone.utc（aware）
- Alembic 已放弃，用 create_all + 手动 ALTER TABLE
- 底稿明细行：不硬编码行名，用 detail_discovery 动态发现（企业实际数据决定），key_rows 只定义结构性行
- 附注表格填充：结构/样式来自模板，明细行数据从底稿 fine_summary 动态提取，降级从试算表取数，合计行自动求和
- 统一导入架构：import_template_service（模板生成+校验+解析）+ import_templates 路由（4 API）+ UnifiedImportDialog 前端三步弹窗

## 底稿编码体系（致同 2025 修订版）

- D 循环：D0 函证/D1 应收票据/D2 应收账款/D3 预收账款/D4 营业收入/D5-D7 合同资产等
- F 循环：F1 预付账款/F2 存货/F3 应付票据/F4 应付账款/F5 营业成本
- K 循环：K1 其他应收款/K2-K5 费用/K6 持有待售/K7-K8 其他/K9 管理费用
- N 循环：N1 递延所得税资产/N2 应交税费/N3 所得税费用
- 映射文件：backend/data/wp_account_mapping.json（88 条，v2025-R4）
