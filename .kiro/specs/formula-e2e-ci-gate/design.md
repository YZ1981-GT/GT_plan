# 设计文档：S8　公式 Playwright 规格接入真实运行的 CI（formula-e2e-ci-gate）

> 需求编号：requirements §1 两条记 R1（公式 Playwright 规格接入会实际运行的 CI job）、R2（判据「没有违规时真的会绿」，与既有门禁合并口径）；§4 的母 spec「浏览器实测」项记 R3。
> 现状基线：分支 HEAD `4c0a1e0a6` 的 `.github/workflows/` 与 `audit-platform/frontend` 的 Playwright 配置；GitHub 接口在本机未授权，CI 运行历史没有取到，以下只按工作流文件现读。

## 0. 结论

CI 不跑 Playwright 不是因为「CI 跑不了浏览器」（`governance-checks.yml` 的 `render-smoke` 已经在 CI 里装 chromium，`backend-tests` 已经起 PG 16 并跑迁移），而是缺三样东西：一个把库、Redis、后端、前端和种子数据都起起来的 job；不依赖本机数据的公式规格（现有 6 个都依赖本机：写死真实或已删的项目、固定账号、要手工设环境变量，环境不就绪即 skip）；以及触发条件 —— 现在的工作分支 `spec/…` 推送时 CI 根本不触发。现有两处与 Playwright 相关的 job 都是恒绿：`render-smoke` 缺环境变量就 `exit 0`，`formula-runtime-completion` 只查规格文件存在。本设计新建一个独立工作流，先只跑公式链路，按母 spec 发布验收清单里的 7 项浏览器检查写成可在空库上跑的规格。

## 1. 现状复核

| # | 交接结论 | 现算 | 判定 |
|---|---|---|---|
| 1 | R1：规格存在但 CI 不跑 | `ci.yml` 有 11 个 job（后端测试、PG 测试、导入冒烟、lint、gitleaks、行数门、迁移兼容、SQL lint、种子校验、xlsx 漂移、前端构建），都不碰 Playwright。`governance-checks.yml` 有 182 个 job，其中 `render-smoke` 装 chromium，但运行步骤在 `RENDER_SMOKE_BACKEND_URL` 未设时 `exit 0`，而工作流从不设置它 ⇒ 恒跳过；`formula-runtime-completion` 跑 `check_formula_runtime_completion.py --strict`，对 Playwright 只检查 `draft-refresh-regression.spec.ts` 存在、不少于 200 个字符、至少 1 个 `test(`、2 处 `expect`，不运行它（现读 `backend/scripts/check/check_formula_runtime_completion.py`，与评估报告 §11.3 第 17 条一致） | 成立：没有任何 job 真正运行 Playwright |
| 2 | 依赖 CI 能跑浏览器 | `backend-tests` 已用 `services: postgres:16` 起库并以 `MigrationRunner` 跑迁移；GitHub 托管 runner 可 `npx playwright install --with-deps chromium` | 交接判断不准确：缺的是 job，不是能力 |
| 3 | （交接未列）触发条件 | 两个工作流都是 `push: [master, main, 'work/**']` + `pull_request: [master, main]`；当前工作分支 `spec/disclosure-note-doc-upload-and-batch-fill`（上游 `origin/spec/…`）推送时不触发任何 CI | 新增 |
| 4 | 公式相关规格 | 6 个（评估报告 §11.3 第 17 条的口径与清单）：`e2e/custom-workpaper-formula-binding.spec.ts`（写死项目 `37814426…`，该项目已软删；环境未就绪即 skip）、`tests/e2e/draft-refresh-regression.spec.ts`（五个角色账号默认取本机账号密码，地址默认本机 3030 / 9980）、`e2e/formula-manager-runtime-gate.spec.ts`（按名称前缀「【E2E】公式管理运行时门禁_」找现成项目）、`e2e/formula-engine-e2e.spec.ts`（不设 `RUN_FULL_E2E=1` 与 `TEST_PROJECT_ID` 即整组 `test.skip`，且直连 `localhost:9980`）、`e2e/workpaper-formula-toolbar-shell.spec.ts`（默认项目是重药安徽 `0ec33ac9…`，后端或前端不通即 skip）、`e2e/template-library-uat.spec.ts`（写死陕西华氏 2025 项目与 admin 账号，含公式覆盖率看板与 `PUT prefill-formulas` 返回 405 的用例）。评估口径之外另有 `e2e/report-config-baseline-e2e.spec.ts`（报表配置主模板，同样要 `RUN_FULL_E2E=1`），是否纳入在任务 0 判断 | 不能直接接 CI |
| 5 | Playwright 配置 | `playwright.config.ts`：`globalSetup` 跑 `backend/scripts/e2e/seed_fix_projects.py --fix`（失败只告警继续）；`webServer: npm run dev`（CI 下不复用已有服务）；`baseURL 127.0.0.1:3030`；CI 下 `retries: 2`、`workers: 1` | 可复用；种子失败继续是假绿入口 |
| 6 | R3：母 spec 浏览器实测项 | 发布验收清单的 7 项：中央调试 / 报表试算失败原因；全局刷新各状态文案；待确认弹窗陈旧决策；回滚按钮只在可回滚条目；删除冲突提示；门禁五态标签与只提示文案；附件溯源只见本项目 —— 现由 TestClient 用例等效覆盖，界面一项未自动化 | 成立 |
| 7 | R2：既有门禁口径 | memory 方法论㉗：生成类产物须输出幂等、判据不得含时间戳或随机值、修 CI 要看整个 job（`backend-tests` 用 `-x` 且有预存红，加在同一 job 里会被前面的红中断） | 新 job 必须独立 |

## 2. 架构裁定

**ADR-FEC-01 独立工作流 `formula-e2e.yml`。** 一个 job：`services` 起 `postgres:16` 与 `redis:7`；步骤 = 装 Python 与 Node 依赖 → `npx playwright install --with-deps chromium` → `MigrationRunner(...).run_pending()` → 种子脚本 → 后台启动后端（`uvicorn app.main:app --port 9980`，设 `GT_BACKEND_NO_RELOAD=1`），轮询 `/api/health` 直到 `healthy` 或超时失败 → `npx playwright test --config=playwright.formula-e2e.config.ts` → 失败时上传 trace 与截图。触发：`push`（`master`、`main`、`work/**`、`spec/**`）、`pull_request`（`master`、`main`）、`workflow_dispatch`；`paths` 只含公式链路相关目录（`backend/app/services/formula*`、`formula_settings/`、`formula_runtime/`、`formula_management/`、`consistency_gate/`、`report_*`、`audit-platform/frontend/src/components/formula/`、本工作流与规格目录），避免无关提交触发（§4 D1）。不改 `ci.yml` 与 `governance-checks.yml` 的现有 job。

**ADR-FEC-02 专用种子，失败即失败。** 新脚本 `backend/scripts/e2e/seed_formula_e2e.py`：在目标库建五个角色账号（合伙人、经理、审计员、质控、EQCR，密码来自环境变量，CI 用 secrets 之外的固定测试值）、两个【测试】项目（一个国企单体、一个国企合并），给出最小试算表、报表配置、两节附注、一份底稿、一条附件；幂等（第二次运行 0 变更）；输出清单 `backend/data/e2e_formula_manifest.json`（项目 id、账号名、底稿 id；无时间戳）。本地运行时拒绝连接库名为 `audit_platform` 的共享库（必须显式传 `--allow-shared` 才允许，CI 不传）。新配置 `playwright.formula-e2e.config.ts` 的 `globalSetup` 调该脚本，**失败直接抛错**，不再「告警后继续」。

**ADR-FEC-03 规格只依赖种子清单。** 新目录 `audit-platform/frontend/e2e/formula-hub/`，按 §1 第 6 行的 7 项各写一个规格，项目、账号、底稿一律从清单读；登录走界面；每个规格只断言用户可见结果（文案、按钮有无、提示）与一次接口读回。现有 6 个规格的处置：`formula-manager-runtime-gate`、`workpaper-formula-toolbar-shell` 改为读清单后纳入；`formula-engine-e2e` 去掉 `RUN_FULL_E2E` 跳过开关、改相对地址后纳入；`custom-workpaper-formula-binding`、`draft-refresh-regression`、`template-library-uat` 改读清单，改不动的部分（依赖本机真实项目或全局模板库现有数据的断言，如「模板数 ≥ 179」）拆出留在本地脚本，不进 CI（逐条写明原因）。`report-config-baseline-e2e` 按任务 0 的判断决定是否同样改造纳入。

**ADR-FEC-04 判据会绿、也会红（R2）。** 工作流里不得有「缺环境变量或服务就 `exit 0` / `test.skip`」的步骤或用例（`render-smoke` 与现有规格的 skip 就是这种恒绿形态）：环境缺失必须让 job 失败。规格不得用固定等待（`waitForTimeout`）与日期相关断言；接口读回用清单里的 id；CI `retries: 2` 只用于网络抖动，同一规格重试才通过的记入 job 摘要（`--reporter=github,list` 的 flaky 计数），连续出现即修，不加入任何「允许失败」名单。工作流本身先以 `continue-on-error: false` 上线，前提是本地按同一配置连续跑 3 次全绿（任务 4）。

**ADR-FEC-05 本地等价运行。** `npm run test:e2e:formula-hub`：读 `.env.e2e`（本地一次性库 `gt_e2e_formula` 的连接串，由脚本 `backend/scripts/e2e/create_formula_e2e_db.py` 建库并跑迁移），与 CI 同一配置；文档写在 `docs/testing/formula-e2e.md`。

## 3. 风险与待拍板

| # | 事项 | 建议 |
|---|---|---|
| D1 | 是否让 `spec/**` 分支推送触发本工作流 | 是（只本工作流、带路径过滤）；否则规格只在开到 `master` 的 PR 上跑 |
| D2 | 是否把本 job 设为合并必过项（GitHub 分支保护） | 本地连续 3 次全绿、CI 连续 5 次全绿后再设；需仓库管理员在 GitHub 设置 |
| D3 | 现有 6 个规格里依赖本机真实项目的断言 | 留在本地脚本，不进 CI |
| D4 | 依赖母 spec X1 | 母 spec 代码入库后规格才有被测对象；本 spec 在 X1 之后实施 |

| 风险 | 处理 |
|---|---|
| CI 起后端时迁移失败或启动任务失败 | 健康检查要求 `status == healthy`，`degraded` 也判失败并打印 `/api/health` 全文 |
| 前端 dev 服务在 CI 首次编译慢 | `webServer.timeout` 180 秒；或改为 `vite build` + `vite preview`（实施时现读 `vite.config` 的代理是否对 preview 生效再选） |
| 规格互相污染数据 | 每个规格只写自己专属的【测试】对象（种子按规格名建），`workers: 1` |
