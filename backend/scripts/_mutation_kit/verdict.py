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

#: `want` 的特殊值：**任何**新增失败都算 RED，不指定具体期望目标。
#:
#: 🔴 这是**弱判据**，WRONG-TEST 在它下面永远不会出现 —— 也就是说它只能反证
#: 「变异被某个守卫抓到了」，不能反证「被**对的**那个守卫抓到了」。
#:
#: 保留它的唯一理由是迁移等价：`mutate_note_text_hygiene_and_expandable`（18 条）与
#: `mutate_trim_decision_guards` 的部分条目本来就是这个语义（后者用 `expect_red=()`）。
#: 迁移不该擅自加强判据 —— 那会把「迁移」变成「顺手改判据」，一旦改错就分不清是
#: 迁移引入的还是原本就有的。用 `"*"` 显式写出来，同时让「忘了写 want」仍被声明期拒绝。
ANY_RED = "*"


def matched(want: str, names: set[str], wants: tuple[str, ...] = ()) -> list[str]:
    """``want`` / ``wants`` 在失败名集合里的命中项（多目标取并集）。

    两种写法都支持：

    - 裸方法名 ``test_xxx``：按 nodeid **末段前缀**匹配（吃掉 parametrize 的 ``[...]``）
    - 带文件/类的片段或前端中文标题：按子串匹配

    多目标（``wants``）是迁移 `mutate_trim_decision_guards`（`expect_red: tuple`）与
    `mutate_note_conversion_section_mapping_guards`（`expect_tests: list`）时补的 ——
    一条变异常常同时打红多条判据，只允许单目标会逼作者挑一条写、丢掉其余信息。
    """
    patterns = [p for p in ((want,) + tuple(wants)) if p]
    if ANY_RED in patterns:
        # 弱判据：不指定目标，任何新增失败都算命中
        return sorted(names)
    out: set[str] = set()
    for n in names:
        for pat in patterns:
            if pat in n or n.split("::")[-1].startswith(pat):
                out.add(n)
                break
    return sorted(out)


def judge(
    want: str,
    baseline_failed: set[str],
    current_failed: set[str],
    wants: tuple[str, ...] = (),
) -> tuple[str, list[str], list[str], list[str]]:
    """返回 ``(verdict, added, gone, hit)``。

    ``gone``（基线里有而现在没有的失败项）不参与判定，但要报出来 —— 它通常意味着
    基线本身不稳定（随机顺序、共享状态），此时差集判定的可信度下降。
    （本 kit 在基线非空时直接 ABORT，故正常流程下 ``gone`` 恒为空。）
    """
    added = sorted(current_failed - baseline_failed)
    gone = sorted(baseline_failed - current_failed)
    hit = matched(want, set(added), wants)
    if not added:
        return GREEN, added, gone, hit
    if hit:
        return RED, added, gone, hit
    return WRONG_TEST, added, gone, hit
