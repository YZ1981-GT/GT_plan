"""守卫脚本共享的 spec 目录解析 helper —— **薄壳 re-export**。

实现已收敛到 `app/core/spec_docs.py`（全仓唯一一份）。原因：消费方有三类 ——
check 脚本、gen 脚本、以及生产代码（`app/services/workpaper_sync/capacity_profile.py`
按 AC 原文校验容量登记值），三类都能 import 的地方只有 `app/`。

本文件保留是为了让 `backend/scripts/check/` 下**十余个**同目录脚本的
`from _spec_dir import resolve_spec_dir` 一个字都不用改。这里不得再写第二份归档回退
逻辑 —— 那正是本 helper 当初要消除的「多份拷贝漂移」反模式。
"""
from __future__ import annotations

import sys
from pathlib import Path

# 本文件位于 backend/scripts/check/_spec_dir.py ⇒ parents[2] = backend/
_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.core.spec_docs import resolve_spec_dir, specs_root  # noqa: E402

__all__ = ["resolve_spec_dir", "specs_root"]
