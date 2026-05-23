"""logging_config JSON 文件 handler 单测

spec proposal-remaining-18 task 5.7 (MT-8)

覆盖：
- enable_file_handler=True 时挂载 TimedRotatingFileHandler，写入 jsonl
- LOG_FILE_PATH="" 环境变量禁用文件 handler
- enable_file_handler=False 不挂载文件 handler
- JSONFormatter 输出合法 JSON 含 timestamp/level/message
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from app.core.logging_config import JSONFormatter, setup_logging


def _drop_handlers():
    """清理 root logger handlers，避免测试间相互干扰。"""
    root = logging.getLogger()
    for h in list(root.handlers):
        try:
            h.close()
        except Exception:
            pass
        root.removeHandler(h)


def test_json_formatter_emits_valid_json():
    """JSONFormatter 输出可解析为 JSON，含必备字段"""
    fmt = JSONFormatter()
    record = logging.LogRecord(
        name="test.module", level=logging.INFO, pathname="x.py",
        lineno=42, msg="hello %s", args=("world",), exc_info=None,
    )
    line = fmt.format(record)
    parsed = json.loads(line)
    assert parsed["level"] == "INFO"
    assert parsed["message"] == "hello world"
    assert parsed["logger"] == "test.module"
    assert "timestamp" in parsed
    assert parsed["request_id"] == "-"


def test_setup_logging_creates_file_handler(tmp_path, monkeypatch):
    """enable_file_handler=True 时创建文件 handler，日志写入 jsonl"""
    log_file = tmp_path / "app.jsonl"
    monkeypatch.setenv("LOG_FILE_PATH", str(log_file))
    _drop_handlers()
    try:
        setup_logging(level="DEBUG", json_format=False, enable_file_handler=True)
        logger = logging.getLogger("test.file_handler")
        logger.info("test message for file handler")
        # flush all handlers
        for h in logging.getLogger().handlers:
            h.flush()
        assert log_file.exists(), f"log file should have been created at {log_file}"
        content = log_file.read_text(encoding="utf-8").strip().splitlines()
        assert len(content) >= 1
        last_line = json.loads(content[-1])
        assert last_line["message"] == "test message for file handler"
        assert last_line["logger"] == "test.file_handler"
    finally:
        _drop_handlers()


def test_setup_logging_disabled_via_env(tmp_path, monkeypatch):
    """LOG_FILE_PATH='' 时不创建文件 handler"""
    monkeypatch.setenv("LOG_FILE_PATH", "")
    _drop_handlers()
    try:
        setup_logging(level="INFO", json_format=False, enable_file_handler=True)
        # 仅有 stdout handler，无 TimedRotatingFileHandler
        from logging.handlers import TimedRotatingFileHandler
        handlers = logging.getLogger().handlers
        file_handlers = [h for h in handlers if isinstance(h, TimedRotatingFileHandler)]
        assert len(file_handlers) == 0
    finally:
        _drop_handlers()


def test_setup_logging_disabled_via_param(tmp_path, monkeypatch):
    """enable_file_handler=False 时不创建文件 handler"""
    log_file = tmp_path / "app.jsonl"
    monkeypatch.setenv("LOG_FILE_PATH", str(log_file))
    _drop_handlers()
    try:
        setup_logging(level="INFO", json_format=False, enable_file_handler=False)
        from logging.handlers import TimedRotatingFileHandler
        handlers = logging.getLogger().handlers
        file_handlers = [h for h in handlers if isinstance(h, TimedRotatingFileHandler)]
        assert len(file_handlers) == 0
        assert not log_file.exists()
    finally:
        _drop_handlers()
