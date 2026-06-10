"""构建版本读取模块。

提供 get_build_version() 作为真实构建版本的单一来源。
优先级：环境变量 BUILD_VERSION_JSON > _build_version.json 文件 > 兜底默认值。
运行时不执行 git 命令（生产镜像可能无 .git 或 git 二进制）。
任何错误（文件缺失、JSON 解析失败）均返回兜底值，不抛异常。

# Feature: zero-downtime-deployment, Component 1a
"""

from functools import lru_cache
import json
import os
from pathlib import Path

_BUILD_VERSION_FILE = Path(__file__).resolve().parent.parent / "_build_version.json"

_FALLBACK_VERSION: dict = {
    "semantic_version": "dev",
    "git_commit": "unknown",
    "build_time": "unknown",
}


@lru_cache(maxsize=1)
def get_build_version() -> dict:
    """返回 {semantic_version, git_commit, build_time}。

    优先级：
      1. 环境变量 BUILD_VERSION_JSON（JSON 字符串，容器注入）
      2. backend/app/_build_version.json 文件（构建期 CI 写入）
      3. 兜底默认值（本地开发未注入时）

    任何环节出错（环境变量 JSON 格式错、文件不存在/不可读、文件 JSON 解析失败）
    均静默返回兜底值，不抛异常。
    """
    # 1. 环境变量（容器注入）
    env_json = os.getenv("BUILD_VERSION_JSON")
    if env_json:
        try:
            return json.loads(env_json)
        except (json.JSONDecodeError, ValueError):
            return dict(_FALLBACK_VERSION)

    # 2. 构建期写入的文件
    try:
        if _BUILD_VERSION_FILE.exists():
            return json.loads(_BUILD_VERSION_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return dict(_FALLBACK_VERSION)

    # 3. 兜底（本地开发未注入）
    return dict(_FALLBACK_VERSION)
