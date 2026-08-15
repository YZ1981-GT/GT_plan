"""四态判定。

spec: .kiro/specs/e1-variant-recalc-and-mutation-denominator-closure/
Requirements: 6.1 · Property 20

## 四态与它们对应的责任方

| 态 | 含义 | 谁的问题 |
|---|---|---|
| ``RED`` | 新增失败集合非空且**包含** ``want`` | 无（守卫有效） |
| ``GREEN`` | 新增失败集合为空 | **守卫缺陷** —— 该属性没被真正锁死 |
| ``WRONG-TEST`` | 新增失败非空但不含 ``want`` | 污染残留 / 锚点落在错误位置 |
| ``ANCHOR-MISS`` | 锚点无法唯一定位、未落盘、或作用域自证失败 | **脚本缺陷** |

🔴 **退出码不作判据**：pytest 因收集错误也会非零，vitest 有噪声 warning 亦然。
判定只看**失败测试名集合的差集**。
"""

from __future__ import annotations

RED = "RED"
GREEN = "GREEN"
WRONG_TEST = "WRONG-TEST"
ANCHOR_MISS = "ANCHOR-MISS"
ERROR = "ERROR"

ALL_VERDICTS = (RED, GREEN, WRONG_TEST, ANCHOR_MISS, ERROR)


def matched(want: str, names: set[str]) -> list[str]:
    """``want`` 在失败名集合里的命中项。

    两种写法都支持：

    - 裸方法名 ``test_xxx``：按 nodeid **末段前缀**匹配（吃掉 parametrize 的 ``[...]``）
    - 带文件/类的片段或前端中文标题：按子串匹配
    """
    out: set[str] = set()
    for n in names:
        if want in n:
            out.add(n)
            continue
        if n.split("::")[-1].startswith(want):
            out.add(n)
    return sorted(out)


def judge(
    want: str,
    baseline_failed: set[str],
    current_failed: set[str],
) -> tuple[str, list[str], list[str], list[str]]:
    """返回 ``(verdict, added, gone, hit)``。

    ``gone``（基线里有而现在没有的失败项）不参与判定，但要报出来 —— 它通常意味着
    基线本身不稳定（随机顺序、共享状态），此时差集判定的可信度下降。
    """
    added = sorted(current_failed - baseline_failed)
    gone = sorted(baseline_failed - current_failed)
    hit = matched(want, set(added))
    if not added:
        return GREEN, added, gone, hit
    if hit:
        return RED, added, gone, hit
    return WRONG_TEST, added, gone, hit
