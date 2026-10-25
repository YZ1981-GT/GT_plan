"""用例运行中产出的证据 / 报告文件的落点（formula-fetch-followup-defect-closure 6.6）。

🔴 不写回仓库。归档 spec 的 evidence 是 append-only 的历史证据，manifest 还钉了 sha256：
procedure-delegation-visibility-isolation 的 task17 每跑一次就把一组新的计时（p95、派生阈值、
容量报告 hash）写进 manifest 钉着的文件，task15 写进 EXPLAIN ANALYZE 的实测耗时，task14 写进本次样例数。
单跑一个文件看不出来，跑完一批 ``git status`` 冒出一串改动，还容易被顺手提交。

落点：环境变量 ``GT_TEST_ARTIFACT_DIR`` 指定的目录；未指定时为系统临时目录下的 ``gt_test_artifacts``。
想拿到这批文件（例如重做一次容量验收）时设该变量，再自行决定是否另起一次 evidence run。
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

ENV_VAR = "GT_TEST_ARTIFACT_DIR"


def artifact_dir(*parts: str) -> Path:
    """返回 ``<落点根>/<parts...>``（不创建目录，写入方自行 ``mkdir``）。"""
    root = os.environ.get(ENV_VAR) or os.path.join(tempfile.gettempdir(), "gt_test_artifacts")
    return Path(root).joinpath(*parts)
