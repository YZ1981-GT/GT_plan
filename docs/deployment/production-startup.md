# 生产启动命令规范

## 铁律：生产禁用 `uvicorn --reload`

`--reload` 启动 reloader 父子进程模式，SIGTERM 只到父进程，子进程可能不被干净终止：
- drain 不可靠（子进程被强杀，in-flight 请求中断）
- 信号处理不一致（SIGTERM handler 可能不生效）

## 推荐生产命令

```bash
# Docker Compose 模式（每副本单 worker）
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1

# 高吞吐模式（多容器副本替代多 worker）
# 不要用 --workers N，用 N 个独立容器

# 可选 gunicorn（uvicorn worker class）
gunicorn app.main:app -k uvicorn.workers.UvicornWorker --workers 1 --bind 0.0.0.0:8000
```

## `--reload` 仅用于本地开发

```bash
# 本地开发（start-dev.bat 中）
uvicorn app.main:app --reload --host 0.0.0.0 --port 9980
```
