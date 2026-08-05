"""交付件 OnlyOffice 文档标识（``doc_key``）单一真源。

Spec: deliverable-lineage-wiring-and-writeback-closure — Task 13 / 需求 7.4、7.5

为什么要有这个模块：历史实现里同一份文档有**两个**不同的 key ——

- 编辑器配置：``f"{task.id}_{version.version_no}_{int(time.time())}"``（带时间戳）
- 并发席位计数：``f"deliverable-{task_id}-{version_no}"``

两个后果：

1. **协同编辑失效**：OnlyOffice 用 ``document.key`` 标识一次编辑会话，带时间戳
   ⇒ 每次请求 config 都是"新文档"，两人同开同一版本进入两个互不相干的会话，
   各自 forcesave，后者静默覆盖前者。
2. **席位占用与释放不同源**：占用走 ``deliverable-*``、编辑器认另一个 key，
   席位统计只能靠 1h TTL 兜底自愈。

故这里是 ``doc_key`` 的**唯一**生成处，编辑器配置与席位 key 共用。

格式选择：沿用**席位侧**既有格式 ``deliverable-{task_id}-{version_no}``，
使既有 Redis 席位 key 逐字不变（零回归）；改变的只有编辑器侧。
该格式同时满足 OnlyOffice 对 key 的约束（≤128 字符，仅 ``0-9a-zA-Z.=_-``）：
UUID 只含十六进制与 ``-``，版本号是十进制整数。
"""

from __future__ import annotations

from uuid import UUID

#: doc_key 前缀（交付中心域，与底稿编辑器的 key 空间区分开）
DOC_KEY_PREFIX = "deliverable"


def deliverable_doc_key(task_id: UUID | str, version_no: int | str) -> str:
    """由 ``(task_id, version_no)`` 确定性派生 OnlyOffice ``doc_key``（需求 7.4）。

    确定性 = 同输入必得同输出，**不含时间戳/随机数**。

    Args:
        task_id: 交付物（``word_export_task``）主键。
        version_no: 版本号（1 起）。

    Returns:
        形如 ``deliverable-<uuid>-<n>`` 的字符串。
    """
    return f"{DOC_KEY_PREFIX}-{task_id}-{version_no}"


def parse_deliverable_doc_key(doc_key: str) -> tuple[UUID, int] | None:
    """反解 ``doc_key`` 为 ``(task_id, version_no)``；不是本域 key 则返回 ``None``。

    用途：OnlyOffice 回调体自带 ``key`` 字段（就是我们下发的 doc_key），
    回调侧据此校验「这个 key 确实属于本交付物」，避免直接采信外部字符串。

    **与 :func:`deliverable_doc_key` 构成 round-trip**（守卫用它做互逆断言）——
    任何一侧改格式，另一侧立刻打红，杜绝两处各写一份格式。

    解析失败一律返回 ``None``（不抛异常）：回调体由 Document Server 组装，
    格式不符时应如实判「未知」而非崩掉整个保存流程。
    """
    if not isinstance(doc_key, str):
        return None
    prefix = f"{DOC_KEY_PREFIX}-"
    if not doc_key.startswith(prefix):
        return None
    rest = doc_key[len(prefix):]
    # task_id 是 UUID（含 4 个 '-'），版本号在最后一段 → 从右侧切一次
    task_part, sep, ver_part = rest.rpartition("-")
    if not sep or not task_part or not ver_part:
        return None
    try:
        return UUID(task_part), int(ver_part)
    except ValueError:
        return None
