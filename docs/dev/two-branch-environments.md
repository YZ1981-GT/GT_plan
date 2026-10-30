# 双分支并行开发环境（dev1.0 / sw-dev1.0）

> 2026-10-30 建立。起因：两个分支长期共用同一个工作目录来回 `git checkout`，
> 导致「切了分支但 Vite 还在跑旧分支代码」——dev1.0 新建项目被 sw 分支的
> 「法定代表人必填」规则拦住，而 dev1.0 代码里根本没有这个字段。

## 目录与分支

| | dev1.0 | sw-dev1.0（税务 demo） |
|---|---|---|
| 工作目录 | `D:\zaqcwrok\GT_plan` | `D:\zaqcwrok\GT_plan_sw` |
| 启动脚本 | `start-dev.bat` | `start-dev-sw.bat` |
| 前端 | `:3030` | `:3031` |
| 后端 | `:9980` | `:9981` |

两个目录是同一个 git 仓库的 **worktree**，共享 `.git` 对象库但各自独立检出，
**不需要也不应该再 `git checkout` 切分支**。

```powershell
git worktree list   # 查看
```

## 容器与数据库

| | dev1.0 | sw-dev1.0 |
|---|---|---|
| Compose 项目 | `gt-new-plan` | `sw-plan` |
| 容器名 | `audit-postgres` / `audit-redis` / `audit-onlyoffice` | `sw-postgres` / `sw-redis` / `sw-onlyoffice` |
| PostgreSQL | `localhost:5432` → `audit_platform` | `localhost:5532` → `sw_audit_platform` |
| Redis | `localhost:6379` | `localhost:6479` |
| ONLYOFFICE | `localhost:8080` | `localhost:8180` |
| 数据卷 | `gt_workplan_pg_data` 等 | `sw-plan_sw_*` |

两套容器可同时运行，端口与数据卷零交叉。

### sw-plan 容器管理

```powershell
cd D:\zaqcwrok\GT_plan_sw
.\scripts\sw-plan.ps1 up      # 启动 postgres + redis + onlyoffice
.\scripts\sw-plan.ps1 ps      # 查看状态
.\scripts\sw-plan.ps1 logs    # 跟随日志
.\scripts\sw-plan.ps1 env     # 打印连接串
.\scripts\sw-plan.ps1 down    # 停止（数据卷保留）
```

dev1.0 的容器照旧用根 `docker-compose.yml`（项目名 `gt-new-plan`）。

## 日常启动

```powershell
# dev1.0
cd D:\zaqcwrok\GT_plan
.\start-dev.bat                 # → http://localhost:3030

# sw-dev1.0
cd D:\zaqcwrok\GT_plan_sw
.\scripts\sw-plan.ps1 up        # 容器（首次 / 重启 Docker 后）
.\start-dev-sw.bat              # → http://localhost:3031
```

## 未跟踪文件（worktree 不会自动带）

以下文件被 `.gitignore` 排除，新建 worktree 后必须手动准备：

- `.env`、`backend/.env` —— **已按各自环境改好，两边内容不同，不要互相覆盖**
- `.venv/`、`audit-platform/frontend/node_modules/` —— 各自独立安装
- `.env.sw-plan`、`docker-compose.sw-plan.yml`、`scripts/sw-plan.ps1`、
  `start-dev-sw.bat` —— sw-plan 环境定义（尚未提交到 git）

🔴 `GT_plan_sw/backend/.env` 已指向 5532 / `sw_audit_platform`。
这一点很关键：即使不经 `start-dev-sw.bat`（例如直接跑 pytest 或运维脚本），
也不会误写 dev1.0 的业务库。

🔴 **不要**用目录联接（junction）让两个 worktree 共用 `node_modules`：
Windows PowerShell 5.1 的 `Remove-Item -Recurse` 会顺着联接删掉真实目录。

## 常见问题

**改了代码但页面没变 / 行为像另一个分支**
Vite 把模块图与依赖预构建缓存在内存和 `node_modules/.vite`。确认你访问的端口
与所在目录匹配（3030→GT_plan，3031→GT_plan_sw）。必要时清缓存重启：

```powershell
Remove-Item -Recurse -Force audit-platform\frontend\node_modules\.vite
```

**后端连到了另一个库**
按上表核对 `backend/.env` 的 `DATABASE_URL` 端口（5432 vs 5532）。
`start-dev-sw.bat` 会用真实环境变量覆盖（pydantic-settings 中环境变量优先于
`env_file`），但手工跑脚本时读的就是 `backend/.env`。

**Docker Desktop 重启后连不上**
宿主端口转发可能陈旧（vpnkit 仍指向容器旧 IP），表现为容器 healthy 但宿主
连不上、登录 500。处置：`docker restart <容器名>`（数据卷保留）。
