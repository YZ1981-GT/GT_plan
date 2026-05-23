"""统一日志配置 — 结构化 JSON 日志格式 + request_id 链路追踪

[proposal-remaining-18 / MT-8 / 任务 5.7]
新增 JSON 文件 handler（jsonl 格式，按日轮转），供 admin 日志查看面板读取。
"""

import logging
import logging.handlers
import os
import sys
import json
from datetime import datetime, timezone
from pathlib import Path


class JSONFormatter(logging.Formatter):
    """结构化 JSON 日志格式（含 request_id）"""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "request_id": getattr(record, "request_id", "-"),
        }
        if record.exc_info and record.exc_info[1]:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry, ensure_ascii=False)


# ---------------------------------------------------------------------------
# JSON 文件 handler 配置
# ---------------------------------------------------------------------------

# 默认日志文件路径（环境变量 LOG_FILE_PATH 可覆盖；为空字符串时禁用文件 handler）
DEFAULT_LOG_FILE_PATH = "logs/app.jsonl"


def _resolve_log_file_path() -> str | None:
    """解析 JSON 日志文件路径。

    返回 None 表示禁用文件 handler（环境变量显式设为空字符串时）。
    """
    env_path = os.environ.get("LOG_FILE_PATH")
    if env_path is None:
        return DEFAULT_LOG_FILE_PATH
    if env_path.strip() == "":
        return None
    return env_path


def _build_file_handler(log_file_path: str) -> logging.handlers.TimedRotatingFileHandler:
    """构建 JSON 日志文件 handler（按日轮转，保留 14 天）。"""
    log_path = Path(log_file_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    handler = logging.handlers.TimedRotatingFileHandler(
        filename=str(log_path),
        when="midnight",
        interval=1,
        backupCount=14,  # 保留 14 天
        encoding="utf-8",
        delay=True,  # 首次写入时才打开文件，避免空文件占用
    )
    handler.setFormatter(JSONFormatter())
    return handler


def setup_logging(
    level: str = "INFO",
    json_format: bool = False,
    enable_file_handler: bool = True,
):
    """配置全局日志

    Args:
        level: 日志级别 (DEBUG/INFO/WARNING/ERROR)
        json_format: stdout handler 是否使用 JSON 格式（生产环境推荐）
        enable_file_handler: 是否启用 JSON 文件 handler（默认 True，输出到 logs/app.jsonl）
    """
    from app.middleware.request_id import RequestIDFilter

    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    # 清除已有 handler
    root.handlers.clear()

    # ─── stdout handler ───
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.addFilter(RequestIDFilter())
    if json_format:
        stdout_handler.setFormatter(JSONFormatter())
    else:
        stdout_handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)-8s [%(name)s] [%(request_id)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        ))
    root.addHandler(stdout_handler)

    # ─── JSON 文件 handler（用于 admin 日志查看面板）───
    if enable_file_handler:
        log_file_path = _resolve_log_file_path()
        if log_file_path:
            try:
                file_handler = _build_file_handler(log_file_path)
                file_handler.addFilter(RequestIDFilter())
                root.addHandler(file_handler)
            except OSError as exc:
                # 文件创建失败不阻断启动；stdout handler 仍生效
                root.warning(
                    "Failed to attach JSON log file handler at %s: %s",
                    log_file_path,
                    exc,
                )

    # 降低第三方库日志级别
    for noisy in ("uvicorn.access", "sqlalchemy.engine", "httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
