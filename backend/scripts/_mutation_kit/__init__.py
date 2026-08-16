"""变异检验共享件 —— 把「覆盖面分母 + 静态锚点自检 + 冻结基线 + 四态判定」变成默认能力。

spec: .kiro/specs/e1-variant-recalc-and-mutation-denominator-closure/
Requirements: 6.1~6.7 · Property 20~25

## 用法

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/scripts
from _mutation_kit import Mutation, run_cli

REPO = Path(__file__).resolve().parents[3]

MUTATIONS = [
    Mutation(
        id="M01", side="be", path="backend/app/x.py", kind="replace",
        anchor="    return get_active_filter(...)",
        new="    return True",
        want="test_no_naive_is_deleted_filter",
        why="裸过滤器跨 dataset 取数 → 账户合计翻倍；不能只删 if 分支，"
            "下方 except 会把异常吞成 0 而行为不变（= 无效变异）",
    ),
]

GUARD_FILES = {"test_x.py": "Task 1 新建"}

if __name__ == "__main__":
    raise SystemExit(run_cli(
        mutations=MUTATIONS,
        guard_files=GUARD_FILES,      # 必填：覆盖面分母
        repo=REPO,
        backend_args=["backend/tests/four_table", "-k", "x", "-q", "--tb=no", "-rf"],
        baseline_backend_passed=368,
    ))
```

## 为什么存在

平台 17 个变异脚本 / 9657 行，约三分之二是互相抄来的样板（备份、还原、md5 核验、
跑 pytest/vitest、判四态）。抄漏哪一项就是一个假绿入口，实测：**覆盖面分母 3/17 ·
静态锚点自检 1/17 · 冻结基线 1/17**。

更关键的是，光把约束写在文档里不管用 —— 本 spec 的 design.md 明文写着「锚点不含
`\\n`」，作者自己在做变异检验时仍写出多行锚点并吃到两条 ANCHOR-MISS。所以这里的
每条约束都落在**代码强制**上：`guard_files` 是必填关键字参数、锚点换行在声明期
就被拒绝、`--list` 不只打印而是校验、`--check-anchors` 跑完核验自己没写过文件。
"""

from .anchor import (
    AnchorMiss,
    block_range,
    eol_of,
    find_anchor,
    md5_bytes,
    md5_of,
    read_lines,
    strip_eol,
    write_lines,
)
from .apply import (
    BAK_SUFFIX,
    RestoreFailed,
    apply_mutation,
    mutated,
    restore_all,
    stale_backups,
)
from .cli import DEFAULT_GUARD_ROOTS, run_cli
from .coverage import CoverageTally, guard_files_of
from .runner import RunResult, run_pytest, run_vitest, short_nodeid
from .spec import KINDS, SIDES, Mutation, validate_all, validate_mutation
from .verdict import (
    ALL_VERDICTS,
    ANCHOR_MISS,
    ANY_RED,
    ERROR,
    GREEN,
    RED,
    WRONG_TEST,
    judge,
    matched,
)

__all__ = [
    # 声明
    "Mutation", "validate_mutation", "validate_all", "KINDS", "SIDES",
    # 锚点
    "AnchorMiss", "find_anchor", "block_range", "read_lines", "write_lines",
    "md5_of", "md5_bytes", "eol_of", "strip_eol",
    # 应用与还原
    "apply_mutation", "mutated", "restore_all", "stale_backups",
    "BAK_SUFFIX", "RestoreFailed",
    # 执行
    "RunResult", "run_pytest", "run_vitest", "short_nodeid",
    # 判定
    "judge", "matched", "RED", "GREEN", "WRONG_TEST", "ANCHOR_MISS", "ERROR",
    "ALL_VERDICTS", "ANY_RED",
    # 覆盖面
    "CoverageTally", "guard_files_of",
    # CLI
    "run_cli", "DEFAULT_GUARD_ROOTS",
]
