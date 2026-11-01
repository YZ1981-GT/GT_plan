# 公式链路 E2E 测试指南

> spec: `formula-e2e-ci-gate`（ADR-FEC-01~05）

## CI 自动运行

推送到 `master`、`main`、`work/**`、`spec/**` 分支且改动涉及公式链路代码时，
`.github/workflows/formula-e2e.yml` 自动触发。

**CI 做的事：**
1. 起 PG 16 + Redis 7 服务容器
2. 安装 Python / Node 依赖 + Playwright Chromium
3. `MigrationRunner.run_pending()` 跑迁移
4. `seed_formula_e2e.py` 种子（幂等）
5. `uvicorn` 启动后端（`GT_BACKEND_NO_RELOAD=1`）
6. 等 `/api/health` 返回 `healthy`
7. `npx playwright test --config=playwright.formula-e2e.config.ts`
8. 失败时上传 trace + 截图到 Artifacts

## 本地运行

### 一次性库方式（推荐）

```bash
# 1. 建库 + 跑迁移
python backend/scripts/e2e/create_formula_e2e_db.py

# 2. 设环境变量指向一次性库
# PowerShell:
$env:DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/gt_e2e_formula"
# Bash:
export DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:5432/gt_e2e_formula"

# 3. 种子
python backend/scripts/e2e/seed_formula_e2e.py

# 4. 启动后端（另一个终端，带同样的 DATABASE_URL）
cd backend
python -m uvicorn app.main:app --port 9980

# 5. 启动前端（另一个终端）
cd audit-platform/frontend
npm run dev

# 6. 跑 Playwright
cd audit-platform/frontend
npx playwright test --config=playwright.formula-e2e.config.ts
```

### 连共享库方式

```bash
# 种子脚本默认拒绝连接 audit_platform，需显式允许：
python backend/scripts/e2e/seed_formula_e2e.py --allow-shared

# 然后照常启动 start-dev.bat 并跑 Playwright
cd audit-platform/frontend
npx playwright test --config=playwright.formula-e2e.config.ts
```

## 规格目录结构

```
e2e/formula-hub/
├── global-setup.ts       # 种子脚本，失败即终止
├── manifest.ts           # 读清单的唯一入口
├── helpers.ts            # 登录 / 健康检查 / 项目 id
├── 01~07-*.spec.ts       # 母 spec 发布验收清单 7 项
├── 08~10-*.spec.ts       # 现有规格的 CI 适配版
```

## 种子清单

写入 `backend/data/e2e_formula_manifest.json`（无时间戳，幂等）。
包含：5 个角色账号、2 个【测试】项目（国企单体 + 国企合并）、每个项目 2 份底稿。

## 与现有 Playwright 配置的关系

| 配置文件 | testDir | 用途 |
|---|---|---|
| `playwright.config.ts` | `e2e/` | 通用本地 E2E |
| `playwright.formula-e2e.config.ts` | `e2e/formula-hub/` | 公式链路 CI |
| `tests/render-smoke/playwright.config.ts` | `tests/render-smoke/` | 渲染冒烟 |

## 不纳入 CI 的规格

以下规格依赖本机真实项目/模板库数据，只在本地运行：
- `e2e/custom-workpaper-formula-binding.spec.ts`（写死辽宁卫生项目）
- `e2e/template-library-uat.spec.ts`（写死陕西华氏项目 + 模板数断言）
- `tests/e2e/draft-refresh-regression.spec.ts`（五角色 + 真实审计数据）
