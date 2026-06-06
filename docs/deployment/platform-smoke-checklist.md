# 平台上线 Smoke Checklist

> 每次部署或重大变更后按环境执行。通过项打 ✅，异常项记录并报告。

## 1. 本地开发环境

| # | 检查项 | 命令/URL | 预期结果 |
|---|--------|----------|----------|
| 1 | 后端健康检查 | `curl localhost:9980/api/health` | `{"status":"ok"}` |
| 2 | 前端构建 | `npm run build` (frontend cwd) | exit 0，无 error |
| 3 | 前端开发服务器 | `http://localhost:3030` | 页面可访问 |
| 4 | PostgreSQL 连接 | `docker exec audit-postgres pg_isready` | "accepting connections" |
| 5 | Redis 连接 | `docker exec audit-redis redis-cli ping` | "PONG" |
| 6 | 数据库迁移状态 | 后端启动日志 | "Applied N migrations" 无报错 |
| 7 | OnlyOffice 健康 | `curl localhost:8090/healthcheck` | "true" |
| 8 | WOPI 健康 | `curl localhost:9980/wopi/health` | 200 |
| 9 | 类型检查 | `npx tsc --noEmit` (frontend) | 无新增错误 |
| 10 | 测试套件 | `npx vitest run` (frontend) | 无新增失败 |
| 11 | 后端测试 | `python -m pytest backend/tests/ -x --tb=short` | 无新增失败 |
| 12 | Schema drift | `python backend/scripts/check/check_file_size.py` | exit 0 |

## 2. 试点部署环境

| # | 检查项 | 确认方式 | 预期结果 |
|---|--------|----------|----------|
| 1 | 后端 API 可达 | `/api/health` | 200 ok |
| 2 | 前端页面加载 | 浏览器访问 | 登录页可见 |
| 3 | 数据库迁移完成 | 启动日志或 version 查询 | 最新 V0xx 已执行 |
| 4 | Worker 进程存活 | 进程列表 | celery/rq worker 存活 |
| 5 | SSE 连接 | 浏览器 DevTools Network | EventSource 连接正常 |
| 6 | Degraded 状态 | `/api/system/status` 或日志 | 无 critical degraded |
| 7 | 登录认证 | admin/admin123 登录 | JWT 正常签发 |
| 8 | 项目列表 | `/projects` 页面 | 可见测试项目 |

## 3. 生产部署环境

| # | 检查项 | 确认方式 | 预期结果 |
|---|--------|----------|----------|
| 1 | 备份已执行 | 备份脚本日志 | 今日备份文件存在 |
| 2 | API 健康 | `/api/health` | 200 |
| 3 | 迁移无报错 | 部署日志 | V0xx 全部 applied |
| 4 | 证书有效 | HTTPS 访问 | 证书未过期 |
| 5 | 容量告警 | 磁盘/内存/CPU | 未超阈值 |
| 6 | 日志可写 | 最新日志时间 | 近 5 分钟有日志 |
| 7 | 回滚准备 | 回滚脚本/镜像 | 可回退 |

## 恢复操作速查

| 场景 | 操作 |
|------|------|
| 迁移失败 | 执行 R0xx 回滚 SQL |
| 前端白屏 | 检查 nginx 配置 + 静态文件部署 |
| 后端 5xx | 查日志最后 error，重启 uvicorn |
| Redis 异常 | `docker restart audit-redis` |
| PG 连接满 | 检查 pgbouncer，kill idle |
| OnlyOffice 不可用 | 降级为只读预览 |

## 变更历史

| 日期 | 变更 |
|------|------|
| 2026-06-06 | 初始创建 |
