# 实施计划：S8　公式 Playwright 规格接入真实运行的 CI（formula-e2e-ci-gate）

> 以 design.md 为准，需求编号 R1~R3 见 design 页头。启动条件：母 spec 已入库（X1 执行后，design §3 D4）。
> 通用纪律：临时产物放仓库根 `tmp_formula_e2e/`；本地运行只连一次性库 `gt_e2e_formula`，不连共享库；标完成须有实际运行记录（本地 3 次 + CI 至少 1 次）与至少一条变异（让一个规格必然失败，确认 job 变红后还原）；推送用 `.git-hooks/push_version.py`。

- [x] 0. 现状复核
  - 重算 design §1 七行；判断 `report-config-baseline-e2e` 不纳入
  - **2026-11-01 完成**：基线报告 `tmp_formula_e2e/baseline/task0_baseline_report.md`

- [x] 1. 专用种子与一次性库（ADR-FEC-02/05）
  - **2026-11-01 完成**：`seed_formula_e2e.py`（5 角色 + 2 项目 + 底稿，幂等，拒连共享库）、`create_formula_e2e_db.py`、`playwright.formula-e2e.config.ts`、`e2e/formula-hub/{global-setup,manifest,helpers}.ts`

- [x] 2. 七项浏览器检查写成规格（R3，ADR-FEC-03/04）
  - **2026-11-01 完成**：`e2e/formula-hub/01~07-*.spec.ts`，全部从清单读数据

- [x] 3. 现有 6 个规格的处置（ADR-FEC-03）
  - **2026-11-01 完成**：3 个 CI 适配版（08~10），3 个本地专用加文件头说明

- [x] 4. 本地连续运行验证
  - **2026-11-01 完成**：连续 3 次全绿，flaky = 0
    - Run A：20 passed / 0 failed / 39.4s
    - Run B：20 passed / 0 failed / 36.6s
    - Run C：20 passed / 0 failed / 36.3s

- [x] 5. 工作流文件（R1、R2，ADR-FEC-01）
  - **2026-11-01 完成**：`.github/workflows/formula-e2e.yml`

- [x] 6. 收尾
  - **2026-11-01 完成**：`docs/testing/formula-e2e.md`
