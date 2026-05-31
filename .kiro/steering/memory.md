---
inclusion: always
---

# 持久记忆

每次对话自动加载。详见 `#architecture` / `#conventions` / `#dev-history`。
**保持本文件 ≤ 200 行**：完成事项 → dev-history / INDEX.md / git 历史；技术决策 → architecture；规范铁律 → conventions。
精简归档历史（含 V3/附注/合并 A-P 系列详细 sprint 日志）见 `git show <旧commit>:.kiro/steering/memory.md` + `docs/proposals/` + `.kiro/specs/INDEX.md`。

## 用户偏好

- 语言中文；本地优先轻量方案；启动 `start-dev.bat`（后端 9980 + 前端 3030）；打包 `build_exe.py`（PyInstaller 不要 .bat）
- **输出控制铁律（反复强调）**：分步输出，一次不要太长，大改动拆小批次；**但要连续做完整个任务直到完成，不要每段都停问**（分步 ≠ 频繁征求确认，只在真正需决策时停）
- **tasks.md `*` 标记任务也要做**：run-all-tasks 时 `*` 可选任务也必须做完，除非用户明确说跳过
- **任务标记不能假绿**：标 completed 必须有实际代码+测试通过证据；外部依赖/待环境如实标 `[ ]*`，用"代码已改但未实测"措辞
- **彻底解决不绕开**：错误必复现+定位根因+修主代码+加防御测试，绝不"换参数避开"
- **触类旁通 grep**：发现一处反模式立即 grep 全仓找同类一次修完
- **改动前先 spec 三件套**：>500 行文件 / 3+ 组件 / 跨前后端 = 先写 spec
- **改动后必 Playwright 实测**：getDiagnostics 过 ≠ 运行时无错
- **UI 全中文化**：所有用户可见文本中文（技术术语 SQL/PDF/LLM/API/UUID/CAS/编号 保留英文）；不接入 i18n 硬编码 + ESLint 卡点
- 功能收敛停加新功能，核心 6-8 页做到极致，空壳标 developing；前后端必须联动；删除二次确认+先进回收站；一次性脚本用完即删
- git 单 commit 提交所有变更；**push 前必先 fetch 同步**（stash → fetch --prune → 评估 ahead/behind → 决策 → pop → commit/push）
- **协作走 PR 不直推 main**（紧急修 main 崩溃可一次性例外，需用户拍板）；默认分支 `main`（非 master）
- 提建议前先验证不引用过时记录；完整复盘诚实暴露问题不粉饰；PDCA：建议→spec→实施→复盘；5 角色轮转（合伙人/项目经理/质控/审计助理/EQCR）
- 目标并发 6000 人；底稿编码致同 2025 修订版（`backend/data/wp_account_mapping.json` 206 条 v2025-R5）
- 审计循环代号：A 报表/调整 / B 控制了解 / C 控制测试 / D 销售收入 / E 货币资金 / F 采购存货 / G 投资 / H 固定资产 / I 无形资产 / J 职工薪酬 / K 管理 / L 筹资 / M 股东权益 / N 税费 / S 专项

## 环境配置

- Python 3.12（仓库根 `.venv`）/ Docker / PG 16 / Redis 6379；后端 9980 / 前端 3030 / vLLM 8100；DB 名 `audit_platform`；测试用户 admin/admin123
- **venv 路径**：backend cwd 用 `..\.venv\Scripts\python.exe`；仓库根 cwd 用 `.venv\Scripts\python.exe`（勿混）
- Docker 容器：`audit-postgres`(5432) / `audit-redis`(6379→6379) / `audit-metabase`(3000)；health 端点 `/api/health`
- **前端唯一路径**：`audit-platform/frontend/`（仓库根无 `frontend/`）；views/components/composables 在其 `src/` 下
- Playwright MCP 已装（workspace `.kiro/settings/mcp.json`）；新增依赖见 #dev-history（locust/marked+dompurify/decimal.js/python-docx/PyYAML/fast-check/Jinja2/jsonpatch + 外部 LibreOffice）
- **scripts 规约**：`_` 前缀=一次性用完即删，无前缀=正式工具；`backend/scripts/` 分 8 子目录（check/seed/gen/analyze/ops/fix/migrate/e2e）；仓库根 `scripts/run.py` 统一入口
- **D6 MigrationRunner 是运行时迁移**（不是 alembic）：启动跑 `backend/migrations/V*.sql`；新加列写 `V0XX__*.sql`+`R0XX__*.sql` 配对，CREATE/ALTER 必 `IF NOT EXISTS`；按 version **数字**去重（撞名字母序靠后者静默丢失）
- **真实 PG 数据**：5 项目多为 standalone，**0 个 consolidated 项目**（合并模块真实 UAT 全卡此）；首汽租车_2025(df5b8403) tb 最全
- **本地 PG schema 漂移已修**（commit 508393da，965→critical=0）：drift detector 用 pkgutil walk import 全 model 子模块 + 过滤 Metabase 共库污染 + health 按 critical_count（orm_extra+enum_mismatch）判 degraded

## 任务状态

### 合并模块（consolidation）四阶段 — 代码+测试完成，未见真实数据
- **4 Phase spec 全 ✅ 代码+测试**（2026-05-31 merge 后四阶段套件 **147 passed/0 failed**）：Phase0 核心管线（B1 汇总/B2 对账/schema 基线/锁定闭环）+ Phase1 架构锁定（AmountResolver 统一引擎/ELIMINATION_APPROVED 事件重算/全端点锁定+ConsolLockedBanner/B6 负商誉/B7 少数股东/A3 async）+ Phase2 编排接线（cascade_refresh/refresh-all SSE/V2 附注 flag/自动抵销 draft/报表穿透/cross_template/公式联动/签字冻结）+ Phase3 前端穿透（ConsolBreakdownDialog/provenance/双向导航/自动建树）
- **16 ADR**（CONSOL-001~003/101~106/201~206/301~304）+ 24 consol service
- **🔴 四阶段最大盲区 = 无全链路集成测试**（各阶段 mock 掉相邻阶段，merge 已两次咬人：async 签名漂移 + Phase1 删 _execute_formula 令 Phase2 测试失效）；**统一卡点 = PG 0 个 consolidated 项目**（真实 UAT 全 data-blocked）
- **封板待办（按 ROI）**：①🔴 全链路集成测试（合成母子数据跑 建树→recalc→trial→对账→报表→附注→穿透）②🟠 `seed_consol_uat.py` 幂等造最小合成集团一脚本解锁四阶段 UAT ③🟡 Phase2/3 Playwright 复用 Phase1 已跑通环境补实测；**收手判断：地基已正确，无真实集团客户前不深做打磨，封板做①②后转回核心模块**

### git 当前状态（2026-05-31）
- 当前分支 `work/2026-05-30-wp-specs`，已 merge origin/main 的 Phase1（merge commit `60088d42`）+ 后续 fix（`398dc5ab`），**ahead origin/work 未推送**
- 历史已闭环：合并模块 Phase0~3 全在 main / 底稿模块 14 spec 已实施归档 / schema drift 三层修复 / git 治理 spec（GIT_MODE 双模式 + 分支命名 hook + 6 维核查 CLI `check_git_sync_state.py`）

### 已完成 spec 总览
- 详见 `.kiro/specs/INDEX.md`（active + _archive 9 分类）；归档/状态核实必须 grep/fileSearch 实证产物存在，不信 README/INDEX 自述
- active 仅剩合并 4 Phase + consol-note stub；底稿模块（wp-* / gtdform / multi-standard 等 13 spec）+ V3 + 附注 spec + 11 审计循环 + phase1~8 全已归档

### 真正待办（外部依赖）
- LLM 真实接入（6 stub 引擎 `WP_AI_SERVICE_ENABLED` 一键切换）/ 6000 并发压测（Locust+真 PG 大数据）/ 钉集成 / 合并模块真实集团数据 UAT
- 待捞回：`origin/spec/frontend-consistency-m1` 4 commit（GtAmountCell 全量化/状态硬编码消除/6 PBT，待用户评估）

## 操作铁律（标题级，详见 #conventions）

- **三层一致校验**：DB 迁移 + ORM `Mapped[]` + service 方法，任一缺失即伪绿
- **router_registry 必查**：新建 router 必在 `backend/app/router_registry/{group}.py` 注册，否则前端 404；FastAPI 不热加载 router（改后需 start-dev.bat 重启）
- **service 只 flush 不 commit**：跨 service 编排的 router 端点各 service 只 flush，router 统一 commit 保原子
- **PG 运维**：SET 不支持绑定参数（用 set_config）/ ALTER TYPE ADD VALUE 不可事务内即用 / PG-only SQL（jsonb cast/advisory lock/set_config）必加 SQLite dialect 检测
- **历史档案不回填修改**：dev-history / spec-tasks 是 append-only 审计轨迹
- **PowerShell**：写中文/emoji 用 fsWrite（禁 `-replace`/`Set-Content` 处理中文会乱码，用 `python -c read_text/write_text`）；长 commit msg 用 `git commit --% -m "..."` 后不接 `;`；读中文输出先 `chcp 65001 + [Console]::OutputEncoding=UTF8`
- **fsWrite ≥100 行会截断**：大文件分 fsWrite(≤50)+多次小 fsAppend；大块结构删除用临时 python 脚本动态定位边界
- **apiProxy 单层解构**：`api.get/post` 已返业务数据不再 `const {data}=`；但 `http.get/post`（utils/http）返完整响应体需 `.data`
- **ReviewStatusEnum 等枚举成员核对**：引用前用 `python -c "getattr(Enum,'X','MISSING')"` 实证大小写（小写 draft/approved），不信测试与代码哪个对
- **xfail 标"production code bug"= 根因修复信号**：先验证真实定义，修根因后去 xfail 让其真实通过，不留假绿
- **merge 跨阶段签名变更必 grep 调用方**：sync↔async 改 / 删公开方法时全仓 grep 调用点同步改（单阶段 mock 测试全绿不代表跨阶段不断裂）
- **改动后必 Playwright 实测**（运行时 bug 单测/getDiagnostics 抓不到，如包装体解包/CSS 样式孤儿）；改动前后 6 维 git 核查
- **hypothesis PBT 调速**：max_examples 10~15（禁默认 100）
- 详细规约（UI 视觉 17 条 / ESLint AST / 测试 fixture / 启动 lifecycle / CI 卡点 / EventBus / 中间件 等）→ `#conventions` + `#dev-history`

## 关键引用指南
- **仅 memory.md 是 `inclusion: always`（≤200 行约束只针对它）**；architecture/conventions/dev-history 均 `inclusion: manual` 仅 `#` 引用时加载，体量符合参考文档定位**无需裁剪**（dev-history 还是 append-only 审计轨迹）
- 技术事实 / 端点速查 / PG schema / spec 历史详细 → `#dev-history` grep 关键词
- 架构 / 系统规模 / 数据流 → `#architecture`
- 编码规范 / UI 视觉补充 / 操作铁律详解 / PG 运维 → `#conventions`
- spec 状态总览 → `.kiro/specs/INDEX.md`
- 合并模块完整体检 → `docs/proposals/consolidation-module-status-and-proposal.md`
