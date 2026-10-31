# 实施计划：S8　公式 Playwright 规格接入真实运行的 CI（formula-e2e-ci-gate）

> 以 design.md 为准，需求编号 R1~R3 见 design 页头。启动条件：母 spec 已入库（X1 执行后，design §3 D4）。
> 通用纪律：临时产物放仓库根 `tmp_formula_e2e/`；本地运行只连一次性库 `gt_e2e_formula`，不连共享库；标完成须有实际运行记录（本地 3 次 + CI 至少 1 次）与至少一条变异（让一个规格必然失败，确认 job 变红后还原）；推送用 `.git-hooks/push_version.py`。

- [ ] 0. 现状复核
  - 重算 design §1 七行（工作流 job 清单与触发条件、6 个规格的环境依赖、Playwright 配置、母 spec 浏览器项清单）；判断 `report-config-baseline-e2e` 是否属公式链路、要不要纳入；若能取到 GitHub Actions 运行记录（`gh run list`），补记最近运行情况
  - Verify: 记录存 `tmp_formula_e2e/baseline/`

- [ ] 1. 专用种子与一次性库（ADR-FEC-02/05）
  - `backend/scripts/e2e/seed_formula_e2e.py`（幂等、清单无时间戳、拒连共享库）；`backend/scripts/e2e/create_formula_e2e_db.py`；`playwright.formula-e2e.config.ts`（`globalSetup` 失败即抛）
  - Verify: pytest：一次性库上跑两次，第二次 0 变更、清单字节相同；连 `audit_platform` 未带 `--allow-shared` ⇒ 退出码 2。变异：种子去掉幂等判断 ⇒ 第二次运行用例红

- [ ] 2. 七项浏览器检查写成规格（R3，ADR-FEC-03/04）
  - `e2e/formula-hub/` 下 7 个规格（中央调试失败原因、刷新状态文案、待确认陈旧决策、回滚按钮条件、删除冲突提示、门禁五态与只提示文案、附件溯源只见本项目）
  - Verify: 本地一次性库上全绿；ESLint 规则或源码守卫：规格内不得出现 `waitForTimeout` 与写死的 UUID / 端口

- [ ] 3. 现有 6 个规格的处置（ADR-FEC-03，design §3 D3）
  - 3 个改读清单后纳入（`formula-manager-runtime-gate`、`workpaper-formula-toolbar-shell`、`formula-engine-e2e`）；3 个改读清单、拆出依赖本机真实项目或全局模板库现有数据的部分留本地脚本（`custom-workpaper-formula-binding`、`draft-refresh-regression`、`template-library-uat`），并在规格文件头写明原因；`report-config-baseline-e2e` 按任务 0 的判断处理
  - 纳入 CI 的规格去掉全部「环境不就绪即 skip」分支（ADR-FEC-04）
  - Verify: 纳入的规格在一次性库上全绿；停掉后端再跑一次，纳入的规格必须红而不是 skip；拆出部分的本地脚本仍可运行（在本机共享环境跑一次，记录）

- [ ] 4. 本地连续运行验证
  - 同一配置在一次性库上连续跑 3 次，记录耗时与 flaky 次数
  - Verify: 3 次全绿、flaky = 0；记录贴入本任务

- [ ] 5. 工作流文件（R1、R2，ADR-FEC-01，design §3 D1）
  - `.github/workflows/formula-e2e.yml`（服务、迁移、种子、后端健康等待、Playwright、失败上传 trace）；触发按 D1
  - Verify: `actionlint`（若可用）或 YAML 语法校验；推送后 CI 至少运行 1 次全绿（需用户放行推送）。变异：在一个规格里加一条必然失败的断言推到临时分支 ⇒ job 红 ⇒ 删除该分支（用户放行后执行）

- [ ] 6. 收尾
  - `docs/testing/formula-e2e.md`（本地与 CI 运行方式）；母 spec 发布验收清单「浏览器实测」项由本 spec 的 CI 记录承接（在本 spec 记录，不改母 spec 文档）；设为合并必过项按 design §3 D2 交用户
  - INDEX.md 本行与 memory.md 任务状态
  - Verify: 推送带版本号与主要变动
