"""D2 store 值等价判定 —— 「这次回写到底有没有带回新东西」的单一判据。

═══ 为什么单独一个模块 ═══

`d2_bidirectional_bridge` 已 1100+ 行（超行数门上限），而这里两个函数是**纯函数**：
不碰 xlsx、不碰 DB、不依赖契约，只回答「旧值与新值算不算变了」。抽出来既让宿主
不再膨胀，也让这条判据可以被独立测试与复用。

═══ 它修的是什么 ═══

2026-09-06 D2-2 浏览器实测：pull 读到尚未落盘的陈旧 xlsx，把每一格都「回写」成
旧值，报告照样显示「1260 行 / 40320 个字段」全量成功 —— 因为原实现无条件写入并
恒返 ``True``，那个数字其实是「遍历了多少格」而不是「多少格真变了」。审计师因此
无法区分「Excel 的编辑真回写了」与「把一模一样的值重写一遍」。
"""

from __future__ import annotations

from typing import Any

__all__ = ["same_store_value", "assign_store_value"]


def same_store_value(existing: Any, incoming: Any) -> bool:
    """判定 store 里的旧值与 Excel 读回的新值是否等价。

    不能直接 ``==``：同一个金额在 store 里可能是 ``int`` ``5200``、从 xlsx 读回是
    ``float`` ``5200.0``；空值一侧是 ``None``、另一侧是 ``""``。这些都不是真变化，
    若当成变化会让 ``rows_changed`` 恒等于全量，退回「无法区分真假回写」。
    """
    if existing is incoming:
        return True

    # 空值家族互等（None / "" / 纯空白串）
    empty_existing = existing is None or (
        isinstance(existing, str) and not existing.strip()
    )
    empty_incoming = incoming is None or (
        isinstance(incoming, str) and not incoming.strip()
    )
    if empty_existing or empty_incoming:
        return empty_existing and empty_incoming

    # bool 不并入数值：``True`` 与 ``1`` 在业务上是不同字段语义
    # （``isConfirmation`` 是勾选，``postPayment`` 是金额）。
    if isinstance(existing, bool) or isinstance(incoming, bool):
        return bool(existing) == bool(incoming) and (
            isinstance(existing, bool) == isinstance(incoming, bool)
        )

    if isinstance(existing, (int, float)) and isinstance(incoming, (int, float)):
        return float(existing) == float(incoming)

    return str(existing) == str(incoming)


def assign_store_value(
    target: dict[str, Any], store_key: str, value: Any
) -> bool:
    """把一个受管字段值写回 store 行的正确位置。

    :param target: store 行（就地修改）
    :param store_key: 契约声明的 store 路径，嵌套用 ``/`` 分段（如 ``agingPrior/within1``）
    :param value: Excel 侧读回的值
    :returns: 值是否**真的发生了变化**

    🔴 只在真变化时写并返回 ``True``。原实现无条件写入且恒返 ``True``，
    使 ``rows_changed`` 恒等于全量 —— ``rows_changed=0`` 现在能一眼看出
    「这次回写什么都没带回来」（通常意味着读到了尚未落盘的陈旧文件）。

    路径**只**取契约声明的 ``store_key``，不在此自造前缀表 —— 那会变成与契约并行的
    第二份映射真源，契约改了不会跟着改。
    """
    segments = [s for s in str(store_key or "").split("/") if s]
    if not segments:
        return False

    cursor: dict[str, Any] = target
    for seg in segments[:-1]:
        nxt = cursor.get(seg)
        if not isinstance(nxt, dict):
            nxt = {}
            cursor[seg] = nxt
        cursor = nxt

    leaf = segments[-1]
    if leaf in cursor and same_store_value(cursor[leaf], value):
        return False
    cursor[leaf] = value
    return True
