---
inclusion: always
---

# 持久记忆

每次对话自动加载，**保持 ≤ 200 行**。完成事项明细 → `#dev-history`；技术决策 → `#architecture`；规范铁律 → `#conventions`；spec 状态 → `.kiro/specs/INDEX.md`。

## 用户偏好

- 语言中文；本地优先轻量方案；启动 `start-dev.bat`（后端 9980 + 前端 3030）
- **输出分步但连续做完**；**任务标记不能假绿**；**彻底解决不绕开**
- **🔴 codegraph 优先于 grep**：77k 节点/157k 边；grep 仅用于非符号文本
- **触类旁通**；**改动前先 spec 三件套**（>500行/3+组件/跨前后端）；**改动后必 Playwright 实测**
- **UI 全中文化**；**报表金额默认"元"**；**中文场景全链路不能崩**
- 功能收敛；git 单 commit；**push 前必先 fetch**；**协作走 PR 不直推 main**
- 目标并发 6000 人；底稿编码致同 2025 修订版
- 5 角色轮转：审计助理/现场经理/业务合伙人/质量控制复核合伙人/EQCR技术复核人
- **v3.0 愿景方向**：项目级知识自动提取+跨年度续审继承（当前不做）

## 底稿开发铁律

- **风险导向审计**：B50风险→D~N程序表→A13评价错报，全链可追溯
- **componentType 选型**：结构化=d-form-table / 复杂Excel=OnlyOffice / 文档=word-template / 程序表=a-program-console / 函证=confirmation-*（9类）
- **三表HTML渲染**：底稿目录+审定表+附注全走HTML，仅复杂公式/DCF/图表留OnlyOffice
- **联动是核心价值**：ref_index chip+auto_data_source实时取数；孤立底稿=无价值
- **通用schema复用**：`{wp_code}-generic.yaml` + pattern matching
- **开发前必先逐sheet读源模板**；**导入导出三级**；**适用性自动判断**

## 环境配置

- Python 3.12 / Docker / PG 16 / Redis；后端 9980 / 前端 3030 / vLLM 8100；DB `audit_platform`
- **vLLM**：`cu130-nightly`，Qwen3.5-27B-NVFP4，APC+fp8 kv-cache；LMCache CPU offload 待引入
- **rtk 0.42.1**：CLI token 压缩代理
- Docker：postgres(5432)/redis(6379)/metabase(3000)/pgbouncer(6432)
- **host→Docker 连接失败**=vpnkit 卡死，`docker restart` 恢复
- **DB_DISABLE_SSL=True**；连接池 150 / PG max_connections=200
- **前端唯一路径**：`audit-platform/frontend/`
- **codegraph v0.9.8**：hook 自动 sync；双机免改
- **OnlyOffice 9.4.0**：见"踩坑"节 OnlyOffice 条目
- **部署v2.0**：瘦客户端(Electron)+内网全栈(FastAPI+PG+Redis+vLLM+MinIO)

## 迁移与 PG schema

- MigrationRunner（非 alembic）；V+R 配对；`IF NOT EXISTS`；**最高 V091**
- **真实列速查**：trial_balance=standard_account_code/unadjusted_amount/aje_adjustment/audited_amount；working_paper 无 wp_code（在 wp_index，JOIN）
- **recalc 铁律**：`tb_balance` v1 口径（借正贷负），`trial_balance` v2 正数；只汇总叶子；损益取发生额
- **报表引擎**：统一从 trial_balance 取数，TB()/SUM_TB() 公式路径
- **契约测试**：schema_contract(表级)+column_contract(列级)+componentType 契约 vitest

## 任务状态

### 🟢 里程碑（全部已归档，169 spec / 0 active）
- **D0 函证模块**（2026-06-22）：10 spec / 283 任务 / 118 文件 / 9 componentType / 协同层 coordination/（状态机12态+枚举11类+UI Kit+分发+舞弊收集+跨表导航+交互基线）。待 Playwright E2E + 跨底稿引用真实接入。
- **A~S 全循环底稿**（2026-06-19）：13循环 / 568 任务 / ~815 wp_code / 2457 测试
- **OnlyOffice 端到端**（2026-06-21）：4层根因修 / Playwright 0 warning
- **workpaper-account-multifile-aggregation**（V090）+ **bad-debt-sheet-enhancement**（V091）
- **底稿模块治理 6 spec + 底稿优化 4 项 + A1-12 核查表**

### git 状态
- 分支 `work/2026-05-30-wp-specs`，最高迁移 V091
- **远程默认分支隐患**：`origin/HEAD→origin/master` 落后 main 298 commit

### 待办
- D0 函证 Playwright E2E 实测 + 跨底稿引用 API 真实接入
- D2 聚合 12 空白 tab（9 a-program-console 无模板 + 3 audit-sheet 名不匹配）
- A 循环 docx 弹窗（30 个待加 WpPopupDocxEditor）
- A3-8 商誉减值 / A4 经营分部 / A5 现金流（spec 已建未实施）
- 数据管理删除后重导入唯一约束冲突（hard_delete 或 DELETE+INSERT）
- 外部依赖：LLM embedding / 合并 UAT / GitHub 默认分支改 main / MinerU+OCR

## 踩坑铁律（高频）

### 后端
- **🔴 大文件导入期间禁改后端代码**（含 git stash/pop）→ uvicorn reload 杀 worker
- **🔴 event_bus publish 只传 EventPayload**；轻量通知用 broadcast_raw
- **🔴 测试掩盖 bug**：mock 不存在方法 = 把 bug 编进测试；禁 try/except:pass 包被测调用
- **🔴 余额表 KEY_COLUMNS 勿加 account_name**；SELECT tb_balance 必含 direction
- **🔴 同名项目陷阱**：先查 client_name LIKE 多个 + 比对 created_at
- **router_registry 必查**；**后端双态返回必归一化**；**service 只 flush 不 commit**

### 前端
- **🔴 contenteditable v-model** 必加 isInternalChange/focus guard
- **🔴 附注按 sort_order 排序**，禁中文 note_section 字符串排序
- **多 sheet 底稿**：各 sheet 按 class_code 独立派生（ignore_wp_code_override=True）
- **聚合程序表**：用 sheet 级编码(D2A)查模板，非父码(D2)
- **registry sheet_name 必须与 xlsx tab 名完全一致**

### OnlyOffice（4 层坑，按此顺序排查）
1. **JWT**：开发环境 `JWT_ENABLED=false` + 后端 `ONLYOFFICE_JWT_SECRET` 默认空（非空→errorCode -20）
2. **URL**：`ONLYOFFICE_CALLBACK_BASE=http://host.docker.internal:9980`（容器需此 URL 回调+下载，localhost→-4 下载失败）；前端 `VITE_ONLYOFFICE_URL=http://localhost:8080`
3. **Middleware 信封**：callback 必须返回裸 `{"error":0}`，`_SKIP_CONTAINS` 须含连字符 `onlyoffice-callback`（非斜杠），否则 docserver 报 storeForgotten
4. **缓存**：改 URL 后需 touch xlsx（改 doc_key/mtime）或 `docker restart` 清 session，否则旧 URL 仍报错
- **config.py 读 `backend/.env`**（pydantic _env_file=".env" 相对于 cwd=backend 非根目录）

### 函证模块开发经验
- 10 组件统一模式：types→composable→UI→assembly→register；共享层 `coordination/`
- D0-5/D0-6 姊妹复用 CheckBlock+blockColumnConfigs，仅换列配置
- D0-8 跨循环复用（D0-8/E0-8/F0-8/K0-8 同 componentType）
- 状态机 12 态事件驱动；枚举 11 类统一 confirmationDicts；分发按科目路由 D0-5(合同负债)/D0-6(应收)
- 舞弊信号收集：D0-2红旗→第10条 / D0-7不可靠→第7条 / D0-3控制否→第15条 / D0-1低回函率→第14条

## 关键引用

- 技术事实/修复明细 → `#dev-history`
- 架构/MCP/数据流 → `#architecture`
- 编码规范/UI/PG运维 → `#conventions`
- 领域术语/决策阶梯 → glossary.md（inclusion:always）
- spec 状态 → `.kiro/specs/INDEX.md`（169 archived / 0 active）
