---
inclusion: always
---

# 持久记忆

每次对话自动加载，**保持 ≤ 200 行**。完成事项明细 → `#dev-history`；技术决策 → `#architecture`；规范铁律 → `#conventions`；spec 状态 → `.kiro/specs/INDEX.md`。

## 用户偏好

- 语言中文；本地优先轻量方案；启动 `start-dev.bat`（后端 9980 + 前端 3030）；打包 `build_exe.py`（PyInstaller 不要 .bat）
- **输出分步但连续做完**；**任务标记不能假绿**；**彻底解决不绕开**
- **🔴 codegraph 优先于 grep（铁律）**：搜符号/查调用链/看影响面第一选择永远是 codegraph（77k 节点/157k 边）；**grep 仅用于**非符号文本
- **触类旁通**：发现一处反模式立即全仓找同类一次修完
- **改动前先 spec 三件套**（>500 行/3+组件/跨前后端）；**改动后必 Playwright 实测**
- **UI 全中文化**；**报表金额默认"元"**；**中文场景全链路不能崩**
- 功能收敛；git 单 commit；**push 前必先 fetch**；**协作走 PR 不直推 main**
- 目标并发 6000 人；底稿编码致同 2025 修订版（`wp_account_mapping.json`）
- 审计循环代号：A报表 B控制了解 C控制测试 D销售 E货币 F采购存货 G投资 H固定 I无形 J薪酬 K管理 L筹资 M权益 N税费 S专项

## 底稿开发铁律

- **风险导向审计**：B50风险→D~N程序表→A13评价错报，全链可追溯
- **componentType 选型**：结构化联动=d-form-table / 复杂Excel=OnlyOffice / 文档=word-template / 程序表=a-program-console
- **三表HTML渲染**：底稿目录+审定表+附注全走HTML，仅复杂公式/DCF/图表保留OnlyOffice
- **联动是核心价值**：ref_index chip跳转/弹窗+auto_data_source实时取数；孤立底稿=无价值
- **通用schema复用**：`{wp_code}-generic.yaml` + pattern matching
- **开发前必先逐sheet读取源xlsx/docx模板**：从 `backend/wp_templates/{cycle}/` 实物提取
- **导入导出支持三级**（单个/勾选批量/全部一键）
- **适用性自动判断**：`applicable_when` 控制可见性

## 环境配置

- Python 3.12 / Docker / PG 16 / Redis；后端 9980 / 前端 3030 / vLLM 8100；DB `audit_platform`
- **rtk 0.42.1**：CLI token 压缩代理（git/pytest/vitest/playwright/eslint/tsc/docker 加前缀）
- Docker：`audit-postgres`(5432)/`audit-redis`(6379)/`audit-metabase`(3000)/`audit-pgbouncer`(6432)
- **host→Docker 连接失败**=vpnkit 端口转发卡死，`docker restart` 即恢复
- **DB_DISABLE_SSL=True**；连接池 150 但 PG max_connections=200（已提）
- **前端唯一路径**：`audit-platform/frontend/`
- **codegraph v0.9.8**：`npx -y @colbymchenry/codegraph`，双机免改配置；hook 自动 sync
- **OnlyOffice 9.4.0**：JWT secret=`onlyoffice-dev-2026`（config.py+docker-compose+local.json 三处一致）
- **scripts 规约**：`_` 前缀=临时用完即删；`backend/scripts/` 分 8 子目录
- **部署v2.0**：瘦客户端(Electron)+内网全栈服务器(FastAPI+PG+Redis+vLLM+MinIO)
- **MinerU 装服务器端**；OCR 走异步任务队列

## 迁移与 PG schema

- MigrationRunner 运行时迁移（非 alembic）；V+R 配对；`IF NOT EXISTS`；**最高 V088**
- **🔴 `from backend.app.` 路径已全量修复（2026-06-19）**：源码7文件+测试19文件统一改为 `from app.`；`_execute_*` 抽到 `note_validation_executors.py`；`_chat_history` 已删（历史改DB持久化）；V083/V084/V086 补齐 R 回滚文件。16699 测试零 collection error
- **🔴 真实列速查**：trial_balance=standard_account_code/unadjusted_amount/aje_adjustment/audited_amount/opening_balance；working_paper 无 wp_code（在 wp_index，JOIN wp_index_id）
- **recalc 铁律**：`tb_balance` 保留 v1 口径（借正贷负），`trial_balance` 必 v2 正数；只汇总叶子；损益取发生额
- **报表引擎**：统一从 trial_balance 取数，TB()/SUM_TB() 公式路径
- **契约测试**：`test_raw_sql_schema_contract`(表级)+`test_raw_sql_column_contract`(列级)

## 任务状态

### 底稿模块（A~S 全循环 2026-06-19 完成）
- **568 任务全绿**，31 个 spec 统一归档到 `_archive/10-A~S-workpaper-all-cycles-complete/`
- wp_account_mapping 900+ 条；_WP_CODE_OVERRIDE 550+ 条；procedure_table_templates 100+ 程序表；auto_data_resolvers 35+ 个
- **render-config 冒烟测试 1096 passed**（覆盖全部 wp_code+componentType+端点调用链）
- **各循环验证测试**：C(75+43)+D(63)+E(50)+F(124)+G(172)+H(144)+I(107)+J(126)+K(262)+L(110)+M(114)+N(87)+S(72) = **2457 passed**
- **event_handlers_cycle_linkage.py**：C/F/D~N 联动（~500行拆出），`register_cycle_linkage_handlers()` 注册5个handler
- **auto_data_resolvers.py**：28 passed（含 control_deficiency_count），异常返回 `{"_error":True}` 供前端区分

### 其他已完成模块
- 合并模块 4 Phase ✅（归档 `_archive/09-consolidation-phases/`）；卡点=0个consolidated项目
- 全局 7 模块改进 ✅；LLM vLLM 跑通（embedding 404 降级 ilike）；知识库收口完成
- A7-A15/A16/A17/A18 完成阶段底稿 ✅；a21-a25 复核底稿 ✅；核对表/弹窗/分析复核 ✅

### git 状态（2026-06-19）
- 分支 `work/2026-05-30-wp-specs`，HEAD `864b7a78`（spec 归档命名统一），最高迁移 V088
- **🟡 待提交**：本次 `from backend.` 路径全量修复（源码7+测试19）+R083/R086/R084 迁移+文档更新 尚未 commit
- **active spec=1**：audit-report-template-integration 185/190；workpaper-module-health-pass2 ✅ 全部完成（2026-06-21）
- **远程默认分支隐患**：`origin/HEAD→origin/master` 落后 main 298 commit，需 GitHub 改

### wp_render_config 策略拆分（2026-06-19 完成，spec: workpaper-render-config-refactor）
- **✅ P0~P2 全部 21 任务完成**，3772 测试全绿零回归
- `wp_render_config.py` 1474→1156 行；`get_render_config` 475→119 行（dispatch 模式）
- 7 策略文件 `wp_render_strategies/`：_b_index/_a_program/_audit_sheet/_checklist/_analytical_review/_c_note/_univer_grid
- `_resolve_legacy_source` 已删；`control_deficiency_count` 迁入 _REGISTRY（28 测试）
- `wp_component_type_mapping.py` 单一真源；两处 derive_component_type 已改造
- `_WP_CODE_OVERRIDE` 910 条按 15 循环分区注释
- 新增 19 个 cycle_linkage_handlers 集成测试（D/C/F handler）
- **🟡 待 commit**（21 文件变更 + A1-11 修复）

### A1-11 签字流转控制表（2026-06-20 修复）
- **修复**：注册 `wp-popup-signing` componentType → `WpPopupSigning.vue`（已有组件，之前仅弹窗模式使用）
- override `"univer"` → `"wp-popup-signing"`；前后端 4 文件改动；1096 冒烟全绿

### 待办
- **✅ workpaper-module-health-pass2（2026-06-21 全部完成）**：9 项 P1/P2 治理，1152 测试零回归
  - `wp_render_config.py` 1156→747；`wp_classification_service.py` 1319→366；`wp_template_files.py` 1160→301
  - 新建 4 service + 2 router + 1 JSON（910 条热重载）+ 20 新测试；51 resolver docstring 全覆盖
  - router_registry 启动校验 + CI 测试就位；`_EXCLUDED_ROUTERS` 含 3 个待正式注册模块
- **P3 event_handlers_cycle_linkage 联动链路文档化**：5 handler 有级联但无 mermaid/注释说明完整链路
- **P3 孤儿 service 检测**：services/ 604 个文件，部分可能已无调用方，需定期 codegraph 扫描清理
- 外部依赖：LLM embedding / 合并 UAT 数据 / GitHub 默认分支改 main
- A 循环 docx 弹窗（30个待加 WpPopupDocxEditor）
- A3-8 商誉减值 / A4 经营分部 / A5 现金流（spec 已建未实施）
- 数据管理"删除"后重导入唯一约束冲突（需 hard_delete 或 DELETE+INSERT）
- 预设映射 seed 权益类 10 条待补

## 操作铁律摘要

完整明细见 `#conventions`（已补 event_bus/测试反模式/asyncpg/router/前端UI/附注/导入/OnlyOffice 各章节）。此处列最高频踩坑（带关键细节避免再犯）：

- **🔴 大文件导入期间禁改后端代码**：app/*.py mtime 变化→uvicorn `--reload` 杀 worker→导入卡死无报错。**含 git stash/pop/checkout/pull**（重写工作区文件）。诊断=`py-spy dump` 看 worker StartTime 晚于 job started_at
- **🔴 event_bus publish 只传 EventPayload**：禁裸 dict/关键字参数（`_build_dedup_key` 访问 `.event_type` 抛异常被 `try/except:pass` 吞→联动断裂）；轻量通知用 `broadcast_raw(event_type, extra)`
- **🔴 测试掩盖 bug 反模式**：mock 不存在的方法/错误签名=把 bug 编进测试（永绿但生产崩）；禁 `try/except:pass` 包被测调用；用 `assert_awaited_once` 验真调用
- **🔴 余额表 KEY_COLUMNS 勿加 account_name**（升 key 会整行跳过删汇总行）；SELECT tb_balance 返前端的端点必须含 direction 字段
- **🔴 同名项目陷阱**：报"修复没生效"先查 `client_name LIKE` 是否多个同名项目+比对 created_at
- **🔴 contenteditable v-model** 必加 isInternalChange/focus guard（否则光标丢失）
- **🔴 el-tooltip 包非单元素根组件**失效→套 `<span style="display:inline-block">`
- **🔴 附注按 sort_order 排序**，禁中文 note_section 字符串排序（Unicode 码点乱套）
- **🔴 freeze_panes xlsx 加载 crash**：`coordinate_to_tuple(str(ws.freeze_panes))`（影响所有冻结窗格底稿）
- **router_registry 必查**：新 router 必注册；静态路径在通配之前；改后重启
- **后端端点双态返回**必在前端 API 层归一化（`Array.isArray` 兜底）
- **service 只 flush 不 commit**：router 统一 commit 保原子；asyncpg 事务 aborted 后修最先失败的 SQL
- **数据管理删除后重导入唯一约束冲突**：需 `hard_delete:true` 或 recalc 改 DELETE+INSERT
- **OnlyOffice 调试**：先确认 git HEAD 正确→只改 .env 对齐 secret+重启；禁 docker exec 手改容器
- **PowerShell 写中文用 fsWrite**；fsWrite ≥100 行会截断→分批 append；长 commit msg 用 `git commit --% -m`

## 关键引用指南

- **仅 memory.md `inclusion: always`**（≤200 行）；其余 manual 引用
- 技术事实/修复明细 → `#dev-history`
- 架构/MCP/数据流 → `#architecture`
- 编码规范/UI/PG运维 → `#conventions`
- spec 状态 → `.kiro/specs/INDEX.md`
