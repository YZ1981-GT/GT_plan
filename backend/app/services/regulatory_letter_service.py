"""regulatory_letter_service — A18-2 与监管层沟通函 Word 导出编排

调用共享 docx_template_filler 生成 Word；
导出前执行完整性检查（适用议题已填写、不适用议题删除）。

设计要点（见 .kiro/specs/a18-regulatory-communication/design.md）：
- 颜色语义处理统一由 docx_template_filler.fill_and_export 负责
- 本模块负责：数据组装、完整性检查、模板定位、调用 filler
- 议题数据从 checklist_responses 表加载，item_id 前缀见 :data:`ITEM_PREFIX`
- issue_hints 从 issue_tickets 表读取舞弊/违规标题启发式

═══ 判据：item_id 前缀以实际写入方为准（spec api-prefix-fix-recovery 任务 4）═══

本模块原先按 ``A18-2-%`` 读议题、按 ``A18-2-header`` 读表头，而**两个真正的写入方**都用
小写 ``a182-``：前端 ``components/workpaper/composables/useA182RegulatoryCommunication.ts``
（组件 ``GtA182RegulatoryCommunication.vue``，componentType
``a18-2-regulatory-communication``，``wp_code_overrides.json`` 里 ``A18-2`` 就指向它）与
渲染策略 ``routers/wp_render_strategies/_a182_regulatory_communication.py``。
2026-11-12 真库现算：``item_id LIKE 'a182-%'`` = 1 行、``LIKE 'A18-2-%'`` = 0 行。

⇒ 按 ``A18-2-%`` 读的结果是「一个议题都读不到」：导出永远是空函（正文议题全空）、
完整性检查恒报 4 项未填写。**不保留 ``A18-2-%`` 兼容回退** —— 真库 0 行，没历史数据；
唯一写 ``A18-2-*`` 的是 ``GtRegulatoryLetter.vue``（componentType ``regulatory-letter``），
而 ``wp_code_overrides.json`` 里 0 个 wp_code 指向它 ⇒ 运行期不可达。
"""

from __future__ import annotations

import logging
from pathlib import Path
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.docx_template_filler import (
    export_to_bytes,
    fill_and_export,
)

logger = logging.getLogger(__name__)

# ─── 模板路径 ────────────────────────────────────────────────────────────────

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_TEMPLATE_PATH = _BACKEND_ROOT / "wp_templates" / "A" / "A18-2 与监管层沟通函 (通用)2019.docx"

#: 本 entry 的底稿编码（``wp_export_word_service`` 的分发表键也是它）
WP_CODE = "A18-2"

# ─── 议题 ID 映射 ────────────────────────────────────────────────────────────

#: item_id 前缀 —— 与实际写入方一致（见模块 docstring 的现算依据）
ITEM_PREFIX = "a182-"

#: 4 个议题的 item_id 基名：``{基名}-applicability``（适用性）与 ``{基名}-content``（沟通内容）。
#: 与前端 ``useA182RegulatoryCommunication.ts`` 的 ``a182-matter${id}-${field}`` 逐字一致。
TOPIC_IDS = [f"{ITEM_PREFIX}matter{i}" for i in range(1, 5)]

#: 议题名（与前端 ``MATTER_TITLES`` 一致；同时用作「未完成项」的可读标签）
TOPIC_LABELS = ["舞弊", "重大违反法律法规行为", "年度报告中信息不一致或错报", "其他事项"]

#: 收件机构（``authority`` 值为「其他」时改读 ``custom``）
RECIPIENT_AUTHORITY_ID = f"{ITEM_PREFIX}recipient-authority"
RECIPIENT_CUSTOM_ID = f"{ITEM_PREFIX}recipient-custom"

#: 适用性取值：前端 ``updateMatter`` 把选中的 ``Y`` / ``N`` / ``NA`` 写进 **remark**（conclusion 恒 null）
_APPLICABLE_YES = frozenset({"Y", "是", "适用"})


def _clean(value: object) -> str:
    """去空白后的字符串；None → 空串。"""
    return str(value).strip() if value is not None else ""



class RegulatoryLetterService:
    """编排 A18-2 议题数据 → Word 文档"""

    async def check_completeness(
        self, db: AsyncSession, project_id: UUID, wp_id: UUID
    ) -> dict:
        """检查 4 个议题是否都已处理。

        判据（与实际写入方 ``useA182RegulatoryCommunication.ts`` 一致）：
        - 适用性 = ``Y`` ⇒ 必须填了沟通内容，否则该项未完成
        - 适用性 = ``N`` / ``NA`` ⇒ 视为已完成（不适用无需内容）
        - 适用性未选（无该行 / 空值）⇒ 该项未完成

        Returns:
            {
                has_incomplete: bool,
                count: int,
                incomplete_topics: list[str],   # 可读中文标签，直接给前端展示
                wp_code: "A18-2",
            }
        """
        matters = await self._load_matters(db, wp_id)
        incomplete_topics: list[str] = []

        for i, matter in enumerate(matters):
            applicability = _clean(matter.get("applicability")).upper()
            if applicability in _APPLICABLE_YES:
                if not _clean(matter.get("content")):
                    incomplete_topics.append(
                        f"{TOPIC_LABELS[i]}（已标注适用但未填写沟通内容）"
                    )
            elif applicability not in ("N", "NA"):
                incomplete_topics.append(f"{TOPIC_LABELS[i]}（未选择适用性）")

        return {
            "has_incomplete": len(incomplete_topics) > 0,
            "count": len(incomplete_topics),
            "incomplete_topics": incomplete_topics,
            "wp_code": WP_CODE,
        }

    async def export_word(
        self, db: AsyncSession, project_id: UUID, wp_id: UUID
    ) -> bytes:
        """导出 A18-2 Word 文档。

        流程：
        1. 加载议题数据 + 收件人 / 签发信息
        2. 打开模板，调用 fill_and_export 处理颜色语义（红色替换/蓝色删/注释表删）
        3. 把适用议题的内容填进模板对应位置（不适用议题的蓝色提示已被 filler 删掉）
        4. 返回 docx 字节流
        """
        try:
            from docx import Document
        except ImportError:
            raise RuntimeError("python-docx 未安装，无法导出 Word")

        matters = await self._load_matters(db, wp_id)
        header = await self._load_header(db, wp_id)
        project_ctx = await self._load_project_context(db, project_id)

        audit_year = _clean(header.get("auditYear")) or _clean(project_ctx.get("audit_year"))
        client_name = _clean(header.get("companyName")) or _clean(project_ctx.get("client_name"))
        authority = _clean(header.get("authority"))

        context: dict = {
            "client_name": client_name,
            "audit_year": audit_year,
            # 模板里「贵公司 201X 年度财务报表」指被审计年度，不是上年度
            # （build_replacements 默认把 201X 映射成 audit_year - 1，这里显式覆盖）
            "placeholders": {"XX监管机构": authority or "XX监管机构"},
        }
        if audit_year.isdigit():
            context["placeholders"]["201X"] = audit_year

        if not _TEMPLATE_PATH.exists():
            logger.error("A18-2 Word 模板不存在: %s", _TEMPLATE_PATH)
            raise FileNotFoundError(f"模板不存在: {_TEMPLATE_PATH}")

        doc = Document(str(_TEMPLATE_PATH))

        # 🔴 先记住「内容占位段」与「议题标题行」再跑 filler：
        #    蓝色 run 会被 filler 删掉，删完就再也定位不到（``【请描述具体内容。】`` 全是蓝色；
        #    模板里议题 4 的序号 ``4`` 偏偏也是蓝色 ⇒ 删完只剩「、其他事项」，序号消失）。
        content_slots = _find_content_slots(doc)
        title_prefixes = _find_matter_title_prefixes(doc)

        doc, _fill_result = fill_and_export(doc, context)

        # 🔴 filler 的占位符替换是**逐 run** 做的，而真模板把「201X年度」拆成了
        #    `20` / `1` / `X年度` 三个红色 run ⇒ 逐 run 匹配永远命中不了，导出的 Word 里
        #    年份一直是「201X」。这里再按**段落全文**扫一遍（只补 filler 漏掉的占位符，
        #    并在命中时把整段并进首个 run，保留其字体）。
        _replace_across_runs(doc, {"201X": audit_year} if audit_year.isdigit() else {})

        # 蓝色删除把「4、」的序号一起带走了 ⇒ 按填充前记下的标题补回序号
        _restore_matter_title_prefixes(doc, title_prefixes)

        self._inject_topic_content(doc, matters, content_slots)

        return export_to_bytes(doc)

    def _inject_topic_content(
        self, doc, matters: list[dict], content_slots: list
    ) -> None:
        """把适用议题的内容写入模板对应位置。

        ``content_slots`` 是模板里「请描述具体内容」三段（对应议题 1 / 2 / 4）的段落对象；
        议题 3（年报信息）在模板里没有内容占位段，内容接在同段说明文字之后。
        模板结构与段落数的对应关系由 :func:`_find_content_slots` 现读确定，不写死行号。
        """
        for i, matter in enumerate(matters):
            applicability = _clean(matter.get("applicability")).upper()
            if applicability not in _APPLICABLE_YES:
                continue
            content = _clean(matter.get("content"))
            if not content:
                continue

            if i == 2:  # 议题3：模板段 13 是说明文字，正文接在它后面
                target = _find_paragraph_containing(doc, "我们阅读贵公司的")
                if target is not None:
                    _insert_paragraph_after(target, content)
                    continue

            slot_index = _slot_index_for_matter(i)
            if slot_index is not None and slot_index < len(content_slots):
                paragraph = content_slots[slot_index]
                paragraph.add_run(content)
                continue

            # 兜底：模板结构与预期不符时追加到文末，绝不静默丢内容
            logger.warning("A18-2 议题 %s 未找到模板占位段，内容追加到文末", i + 1)
            doc.add_paragraph(f"【{TOPIC_LABELS[i]}】{content}")

    # ─── Private helpers ─────────────────────────────────────────────────────

    async def _load_topic_items(self, db: AsyncSession, wp_id: UUID) -> dict[str, dict]:
        """加载本底稿的 A18-2 响应行（``item_id → {conclusion, remark}``）。"""
        result = await db.execute(
            text(
                "SELECT item_id, conclusion, remark "
                "FROM checklist_responses "
                "WHERE wp_id = :wp_id AND item_id LIKE :prefix"
            ),
            {"wp_id": str(wp_id), "prefix": f"{ITEM_PREFIX}%"},
        )
        return {
            row["item_id"]: {
                "conclusion": _clean(row["conclusion"]),
                "remark": _clean(row["remark"]),
            }
            for row in result.mappings().all()
        }

    async def _load_matters(self, db: AsyncSession, wp_id: UUID) -> list[dict]:
        """4 个议题的适用性与沟通内容。

        取值口径与渲染策略 ``_a182_regulatory_communication.py`` 一致：以 ``remark`` 为准
        （前端把单选值与文本都写 remark，``conclusion`` 恒 null）。
        """
        items = await self._load_topic_items(db, wp_id)
        matters: list[dict] = []
        for i in range(1, 5):
            applicability_item = items.get(f"{ITEM_PREFIX}matter{i}-applicability") or {}
            content_item = items.get(f"{ITEM_PREFIX}matter{i}-content") or {}
            matters.append(
                {
                    "applicability": applicability_item.get("remark")
                    or applicability_item.get("conclusion")
                    or "",
                    "content": content_item.get("remark")
                    or content_item.get("conclusion")
                    or "",
                }
            )
        return matters

    async def _load_header(self, db: AsyncSession, wp_id: UUID) -> dict:
        """加载收件人 / 签发信息（模板表头用）。

        表头字段在本 entry 里是逐个 item 存的（``a182-recipient-*`` / ``a182-sign-*``），
        没有 ``*-header`` 聚合行 —— 原先读 ``A18-2-header`` 恒读不到。
        """
        items = await self._load_topic_items(db, wp_id)

        def value(item_id: str) -> str:
            row = items.get(item_id) or {}
            return _clean(row.get("remark")) or _clean(row.get("conclusion"))

        authority = value(RECIPIENT_AUTHORITY_ID)
        if authority == "其他":
            authority = value(RECIPIENT_CUSTOM_ID)
        return {
            "authority": authority,
            "companyName": "",
            "auditYear": "",
            "cpa1": value(f"{ITEM_PREFIX}sign-cpa1"),
            "cpa2": value(f"{ITEM_PREFIX}sign-cpa2"),
            "date": value(f"{ITEM_PREFIX}sign-date"),
        }

    async def _load_project_context(
        self, db: AsyncSession, project_id: UUID
    ) -> dict:
        """加载项目上下文（公司名、审计年度）"""
        result = await db.execute(
            text(
                "SELECT client_name, audit_period_end "
                "FROM projects WHERE id = :pid"
            ),
            {"pid": str(project_id)},
        )
        row = result.mappings().first()
        if not row:
            return {}
        audit_year = ""
        if row["audit_period_end"]:
            audit_year = str(row["audit_period_end"].year)
        return {"client_name": row["client_name"] or "", "audit_year": audit_year}


# ─── Module-level convenience functions ──────────────────────────────────────


async def a18_export_word(db: AsyncSession, project_id: UUID, wp_id: UUID) -> bytes:
    """模块级快捷函数（``wp_export_word_service.EXPORT_DISPATCH["A18-2"]``）"""
    return await RegulatoryLetterService().export_word(db, project_id, wp_id)


async def a18_check_incomplete(db: AsyncSession, project_id: UUID, wp_id: UUID) -> dict:
    """分发接口（``wp_export_word_service.CHECK_DISPATCH["A18-2"]``）：按统一检查契约返回。

    分发端点 ``GET …/export-word/check-incomplete`` 用 ``CheckIncompleteResponse(**result)``
    回包，统一契约是 ``{complete, missing_fields, wp_code, reason}``（A17 两个检查函数同契约）。
    原先这里原样返回 ``check_completeness`` 的 ``{has_incomplete, count, incomplete_topics}``
    ⇒ 缺 ``complete`` 字段，端点一调即 ``ValidationError`` ⇒ 500（该端点此前被同路径的
    ``completion_phase`` 通用实现遮蔽、从未可达，故一直没暴露；spec ``api-prefix-fix-recovery``
    任务 4 删除遮蔽实现后才修）。
    """
    raw = await RegulatoryLetterService().check_completeness(db, project_id, wp_id)
    topics = list(raw.get("incomplete_topics") or [])
    return {
        "complete": not raw.get("has_incomplete"),
        "missing_fields": topics,
        "wp_code": raw.get("wp_code") or WP_CODE,
        "reason": f"{len(topics)} 项议题未完成" if topics else None,
    }


# ─── 模板结构定位（导出时用；现读模板，不写死行号）─────────────────────────────


def _content_slot_marker() -> str:
    """模板里内容占位段的标识文字。

    A18-2 模板用「【请描述具体内容。】」标出议题 1 / 2 的填写位置（议题 4 另有一段
    「【请描述审计中出现的…】」）。两段都是蓝色 run ⇒ ``fill_and_export`` 会删掉它们，
    所以必须在跑 filler **之前** 取到段落对象（见 ``export_word``）。
    """
    return "【请描述"


def _slot_index_for_matter(matter_index: int) -> int | None:
    """议题序号（0-based）→ ``content_slots`` 下标。

    模板里只有议题 1 / 2 / 4 有内容占位段（顺序即 ``【请描述具体内容。】`` ×2 +
    ``【请描述审计中出现的…】``）；议题 3（年报信息）没有占位段，内容接在同段说明文字之后。
    """
    return {0: 0, 1: 1, 3: 2}.get(matter_index)


def _replace_across_runs(doc, replacements: dict[str, str]) -> int:
    """按**段落全文**替换占位符（补 ``fill_and_export`` 逐 run 替换的盲区）。

    ``docx_template_filler._replace_in_run`` 只在单个 run 的文本里找占位符，而真模板把
    「201X年度」拆成 ``20`` / ``1`` / ``X年度`` 三个红色 run ⇒ 逐 run 匹配恒不命中，
    导出的 Word 里年份停留在「201X」（2026-11-12 用真模板实测到）。

    命中时把该段所有 run 合并进首个 run（保留其字体），因此只在**确实有占位符**时做，
    不改动其它段落。返回替换次数。
    """
    if not replacements:
        return 0
    replaced = 0
    for paragraph in doc.paragraphs:
        text = paragraph.text
        if not any(key in text for key in replacements):
            continue
        new_text = text
        for key, value in replacements.items():
            new_text = new_text.replace(key, value)
        if new_text == text:
            continue
        runs = paragraph.runs
        if not runs:
            paragraph.add_run(new_text)
            replaced += 1
            continue
        runs[0].text = new_text
        for run in runs[1:]:
            run._r.getparent().remove(run._r)
        replaced += 1
    return replaced


def _find_content_slots(doc) -> list:
    """按顺序取模板里所有「【请描述…】」占位段落（filler 删除前调用）。"""
    marker = _content_slot_marker()
    return [p for p in doc.paragraphs if marker in p.text]


#: 议题标题行在模板里的固定前缀（「1、舞弊」「2、重大违反法律法规行为」…）。
#: 序号那一位在议题 4 上是蓝色 run，会被 filler 的蓝删带走 ⇒ 需要事后补回。
_MATTER_TITLE_MARKERS = ("、舞弊", "、重大违反法律法规行为", "、中的信息", "、其他事项")


def _find_matter_title_prefixes(doc) -> dict[str, str]:
    """记下每个议题标题行的序号文本（filler 删除前调用）。返回 ``标记 → 序号``。

    模板里标题行形如 ``1、舞弊``。议题 4 的 ``4`` 是蓝色 run（``0000FF``），
    ``fill_and_export`` 的蓝删会把序号一并删掉，导出成「、其他事项」。
    """
    found: dict[str, str] = {}
    for paragraph in doc.paragraphs:
        text = paragraph.text
        for marker in _MATTER_TITLE_MARKERS:
            if marker in text:
                seq = text.split(marker, 1)[0].strip()
                if seq and marker not in found:
                    found[marker] = seq
    return found


def _restore_matter_title_prefixes(doc, prefixes: dict[str, str]) -> int:
    """把被蓝删带走的议题序号补回标题行（filler 之后调用）。返回补回条数。"""
    restored = 0
    for paragraph in doc.paragraphs:
        text = paragraph.text
        for marker, seq in prefixes.items():
            if not marker or marker not in text:
                continue
            head = text.split(marker, 1)[0]
            if head.strip():
                continue  # 序号还在（没被删）
            runs = paragraph.runs
            if not runs:
                paragraph.add_run(seq)
            else:
                runs[0].text = seq + runs[0].text
            restored += 1
    return restored


def _find_paragraph_containing(doc, text: str):
    """取首个包含 ``text`` 的段落（议题 3 的说明段）。"""
    for p in doc.paragraphs:
        if text in p.text:
            return p
    return None


def _insert_paragraph_after(paragraph, text: str):
    """在 ``paragraph`` 之后插入一个新段落（python-docx 没有原生 API）。"""
    from copy import deepcopy

    new_element = deepcopy(paragraph._p)
    paragraph._p.addnext(new_element)
    from docx.text.paragraph import Paragraph

    new_paragraph = Paragraph(new_element, paragraph._parent)
    for run in list(new_paragraph.runs):
        run._r.getparent().remove(run._r)
    new_paragraph.add_run(text)
    return new_paragraph


# ─── A8 其他信息步骤建议 ─────────────────────────────────────────────────────


async def get_a8_step_suggestion(
    db: AsyncSession, project_id: UUID
) -> dict:
    """读取 A8 程序表 seq 3/4/5 的完成状态，映射到议题3 radio 建议值。

    A8 步骤含义：
    - seq 3/4/5 对应年报其他信息审核程序
    - 全部 completed → "no_inconsistency"
    - 有 in_progress → "minor_uncorrected"
    - 有 pending/未完成 → 无建议

    Returns:
        {"suggested_radio": str | None, "a8_status": dict}
    """
    # 读取 A8 程序表响应
    result = await db.execute(
        text(
            "SELECT item_id, conclusion FROM checklist_responses cr "
            "JOIN wp_index wi ON cr.wp_id = wi.id "
            "WHERE wi.project_id = :pid AND wi.wp_code = 'A8' "
            "AND item_id IN ('A8-seq-3', 'A8-seq-4', 'A8-seq-5')"
        ),
        {"pid": str(project_id)},
    )
    rows = result.mappings().all()

    if not rows:
        return {"suggested_radio": None, "a8_status": {}}

    status_map = {r["item_id"]: r["conclusion"] for r in rows}
    statuses = list(status_map.values())

    suggested = None
    if all(s == "completed" for s in statuses):
        suggested = "no_inconsistency"
    elif any(s == "in_progress" for s in statuses):
        suggested = "minor_uncorrected"

    return {"suggested_radio": suggested, "a8_status": status_map}
