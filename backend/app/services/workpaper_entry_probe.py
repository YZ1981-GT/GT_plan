# -*- coding: utf-8 -*-
"""底稿「是否已有实质录入」批量探测（只读）。

Feature: procedure-trimming-and-delegation-intelligence — Task 10
Requirements: 9.1, 9.2, 9.4, 9.5

服务于裁剪决策的**底稿已录入保护**：程序状态仍为「待执行」而底稿已录入数据时，
智能裁剪不得把它判成不适用（否则审计师已做的工作白做）。

═══ 🔴 判据不能照 spec 字面写成「``parsed_data`` 非空」（2026-08-09 真实库实证）═══

tasks.md / design.md 写的判据是「存在 ``checklist_responses`` 行（``conclusion`` 或
``remark`` 非空）**或** ``working_paper.parsed_data`` 非空」。后半句照字面实现会让本保护
**把智能裁剪整体吃掉**：

真实库 ``working_paper``（2798 行未软删）的 ``parsed_data`` 键全集实测：

| 键 | 持有行数 | 性质 |
|---|---|---|
| ``audit_checks`` / ``audit_checks_at`` | 341 / 341 | **系统写**（一致性检查结果，其中 310 行数组为空） |
| ``html_data`` | 73 | 渲染载荷（**含**真录入，也含模板表头文字） |
| ``wp_code`` / ``generated_at`` | 63 / 63 | 模板渲染元数据 |
| ``procedure_status`` | 15 | 程序状态（系统同步） |
| ``schema_version`` / ``_version`` / ``last_modified_at`` / ``last_modified_by`` / ``changed_sheets_last_save`` | 8 each | 保存副产元数据 |
| ``audit_explanation`` / ``ai_content`` / ``cross_refs`` / ``conclusion`` / ``conclusion_text`` / ``unadjusted_amount`` / ``aje_adjustment`` / ``rje_adjustment`` / ``audited_amount`` / ``extracted_at`` | 1 each | 真实内容 |

即 410 个「``parsed_data`` 非空」里 **310 个恰好是 ``{"audit_checks": [], "audit_checks_at": …}``**
（系统写的空数组），另约 63 个是 ``{"wp_code", "generated_at", "html_data"}`` 的模板表头
（``html_data`` 里只有「致同会计师事务所（特殊普通合伙）」「编制单位：」这类模板文字）。

在程序实例最多的项目（``0ec33ac9`` 重药控股安徽，331 个 ``wp_code``）上两种判据实测：

| 判据 | 判「已有录入」 | 占比 |
|---|---|---|
| 朴素（``parsed_data`` 非空 **或** 有任意 checklist 行） | **224** | 68% |
| 本模块（剥系统副产键 + checklist 内容非空） | **57** | 17% |

68% 的程序恒 ``keep`` ⇒ 底稿已录入保护把智能裁剪吃掉，而单测/诊断全绿看不出来。
故本模块在 spec 字面之上做两处**收窄**（守卫钉死，见
``backend/tests/procedure_trim/test_workpaper_entry_probe.py``）：

1. ``parsed_data`` 先剥 :data:`SYSTEM_PARSED_DATA_KEYS`（系统副产键）再判非空。
2. ``checklist_responses`` 必须有**内容非空**的行 —— 全表 1,034,515 行里 1,033,820 行
   ``conclusion``/``remark`` 双空（其中 1,033,230 行集中在一张 ``C24`` 底稿、仅 10 行有内容），
   「有行即有录入」会让 131 张底稿全部误判。

═══ ``html_data`` 有意**不**剥（方向安全的假阳性）═══

``html_data`` 是 grid / 自定义底稿的录入落点（前端 ``buildPayload()`` → ``wp_html_save``
写回 ``parsed_data.html_data[sheet]``），**同时**也会在模板渲染期被写入表头文字。二者在
SQL 层无通用判据（每个循环的 ``html_data`` 形态不同）。

处置 = 保留为正信号，接受「只有模板表头也判已录入」这一假阳性，理由是**误判方向**：

- 假阳性（判有录入 → ``keep``）⇒ 审计师多手工裁一次，代价可控。
- 假阴性（判无录入 → 被裁）⇒ 审计师已录的数据所在底稿被判不适用，**正是 Requirement 9
  存在的全部理由**。

与 ``procedure_trim_scope`` 的既有取向一致（其 docstring：「无法判定时倾向"有数据/保留"，
避免误裁」）。

═══ 其它约束 ═══

- **一次查询**（Requirement 9.4 / Property 36）：查询次数与 ``wp_codes`` 长度无关。
- **每个请求 wp_code 都返回显式布尔**（未建底稿 → ``False``）。这样「探测过且都没录入」
  与「探测不可用」（调用方拿到空 dict + degradation）**结构性可区分** —— 后者若被当成前者，
  底稿已录入保护会整体失效而无人察觉。
- **查询失败 → 全部 ``True``**（保守保留，Requirement 9.5）+ WARNING，并经
  :class:`ProbeResult.degraded` 如实上报（``probe_workpaper_entries`` 薄壳丢弃该标记，
  取数装配层用 :func:`probe_workpaper_entries_detailed`）。
- ``checklist_responses`` **无 ORM 模型**，故本模块走 ``sa.text``；底稿外键列名是
  **``wp_id``**（不是 ``workpaper_id``），唯一约束 ``(wp_id, item_id)``。
- 表关系链：``wp_index.wp_code`` → ``wp_index.id`` = ``working_paper.wp_index_id``
  → ``working_paper.id`` = ``checklist_responses.wp_id``。
  ⚠️ **不走 ``procedure_instances.wp_id``** —— 该列实测仅 26/452 行非空。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# ── 系统副产键：出现在 parsed_data 里但**不代表审计师录入** ──────────────────────
# 🔴 顺序无关，但清单是判据真源：删任一项都会让对应形态被误判成「已录入」。
#    守卫 `test_workpaper_entry_probe.py` 按真实库键盘存钉死本清单，并有反向自检证明
#    移除 `audit_checks` 会让占比最大的那一类（310 行）重新被误判。
SYSTEM_PARSED_DATA_KEYS: tuple[str, ...] = (
    # 一致性检查结果（系统写，341 行；其中 310 行 audit_checks 为空数组）
    "audit_checks",
    "audit_checks_at",
    # 模板渲染 / 提取元数据（63 行）
    "wp_code",
    "generated_at",
    "extracted_at",
    # 程序状态同步（15 行）
    "procedure_status",
    # wp_html_save 的保存副产元数据（8 行）
    "schema_version",
    "_version",
    "last_modified_at",
    "last_modified_by",
    "changed_sheets_last_save",
)

# 🔴 有意**不在**剥除清单内的键（删除本常量即失去这条设计意图的留痕）
DELIBERATELY_KEPT_PARSED_DATA_KEYS: tuple[str, ...] = ("html_data",)

# 🔴 SQL 首行标记：供测试替身按 SQL 文本分流用（该查询同时含 wp_index / working_paper /
#    checklist_responses 三张表名，靠表名分流会与既有路由撞车）。**勿删**，守卫按此断言。
PROBE_SQL_MARKER = "-- workpaper_entry_probe"

# 一次性批量探测 SQL。
#
# 结构说明：
#   wps    —— wp_code → working_paper.id + 「剥系统副产键后 parsed_data 是否非空」
#   filled —— 在候选底稿范围内、一次 GROUP BY 求出「哪些底稿有内容非空的 checklist 行」
#
# 🔴 `filled` 有意写成独立 CTE + GROUP BY，**不用相关子查询 EXISTS** —— 实测 331 个
#    wp_code 的相关 EXISTS 在 `C24`（1,033,230 行 checklist_responses）上 30s 超时，
#    改成一次分组聚合后秒级返回。
_PROBE_SQL = f"""
{PROBE_SQL_MARKER}
WITH wps AS (
    SELECT wi.wp_code AS wp_code,
           wp.id      AS wp_id,
           ((wp.parsed_data - string_to_array(:sys_keys, ',')) <> '{{}}'::jsonb)
               AS parsed_has
    FROM wp_index wi
    JOIN working_paper wp
      ON wp.wp_index_id = wi.id
     AND wp.project_id = wi.project_id
     AND wp.is_deleted = false
    WHERE wi.project_id = CAST(:pid AS uuid)
      AND wi.is_deleted = false
      AND wi.wp_code IN :codes
),
filled AS (
    SELECT cr.wp_id AS wp_id
    FROM checklist_responses cr
    WHERE cr.wp_id IN (SELECT wp_id FROM wps)
      AND (btrim(coalesce(cr.conclusion, '')) <> ''
           OR btrim(coalesce(cr.remark, '')) <> '')
    GROUP BY cr.wp_id
)
SELECT w.wp_code AS wp_code,
       bool_or(coalesce(w.parsed_has, false) OR f.wp_id IS NOT NULL) AS has_entry
FROM wps w
LEFT JOIN filled f ON f.wp_id = w.wp_id
GROUP BY w.wp_code
"""


@dataclass(frozen=True)
class ProbeResult:
    """探测结果 + 降级标记。

    ``degraded`` 为真时 ``entries`` 全部为 ``True``（保守保留），调用方**必须**据此
    记一条 degradation —— 否则「探测失败导致全保留」与「确实全都有录入」在前端不可区分，
    而前者意味着智能裁剪本次整体失效。
    """

    entries: dict[str, bool] = field(default_factory=dict)
    degraded: bool = False
    reason: str | None = None


def _normalize_codes(wp_codes: list[str] | tuple[str, ...] | None) -> list[str]:
    """去空白、去空值、去重（保持首次出现顺序）。"""
    seen: set[str] = set()
    out: list[str] = []
    for raw in wp_codes or ():
        code = (raw or "").strip()
        if not code or code in seen:
            continue
        seen.add(code)
        out.append(code)
    return out


async def probe_workpaper_entries_detailed(
    db: AsyncSession, project_id: UUID | str, wp_codes: list[str],
) -> ProbeResult:
    """批量判定各 ``wp_code`` 对应底稿是否已有实质录入（带降级标记）。

    判据见模块 docstring。返回的 ``entries`` 对**每个**请求 wp_code 都有显式布尔。
    """
    codes = _normalize_codes(wp_codes)
    if not codes:
        # 无探测目标 —— 不发查询。空结果不是降级（调用方另行判断"目标为空"是否要标注）。
        return ProbeResult(entries={}, degraded=False)

    stmt = sa.text(_PROBE_SQL).bindparams(sa.bindparam("codes", expanding=True))
    try:
        rows = (
            await db.execute(
                stmt,
                {
                    "pid": str(project_id),
                    "sys_keys": ",".join(SYSTEM_PARSED_DATA_KEYS),
                    "codes": codes,
                },
            )
        ).fetchall()
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "底稿已录入探测失败 project=%s codes=%d: %s — 按「可能有录入」保守保留",
            project_id, len(codes), e,
        )
        return ProbeResult(
            entries={c: True for c in codes},
            degraded=True,
            reason="底稿已录入探测查询失败，本次按「可能有录入」保守保留全部程序",
        )

    found: dict[str, bool] = {}
    for r in rows:
        code = (getattr(r, "wp_code", None) or "").strip()
        if code:
            found[code] = bool(getattr(r, "has_entry", False))

    # 未建底稿 / 未命中的 wp_code 显式补 False —— 缺键会让调用方无法区分
    # 「没有这张底稿」与「探测没覆盖到它」。
    return ProbeResult(entries={c: found.get(c, False) for c in codes}, degraded=False)


async def probe_workpaper_entries(
    db: AsyncSession, project_id: UUID | str, wp_codes: list[str],
) -> dict[str, bool]:
    """design / tasks 约定的契约形态（薄壳）。

    ⚠️ 本形态**丢弃** ``degraded`` 标记 ⇒ 探测失败时调用方看到的是「全部 True」而不知道
    这是降级结果。取数装配层（``trim_decision_context``）一律用
    :func:`probe_workpaper_entries_detailed`。
    """
    return (await probe_workpaper_entries_detailed(db, project_id, wp_codes)).entries
