"""附注交付过滤：交付件只输出可直接出具的正文（spec ``deliverable-trio-generation-accuracy`` §2.6）。

为什么需要（2026-10-16 四个真实项目附注正文按块解析统计）
------------------------------------------------------
库内正文大量是大模型草稿：重药安徽 159 章里 152 章首段重复标题、127 段「[请补充…]」、142 段「审计师提示 /
审计师备注」、129 张大模型自拟的 markdown 表（数字可能是编的），另有「我将为您生成最终版的附注正文」「（注：以上
文本为基于通用企业会计准则的标准模板…）」之类；和平同量级；宜宾是模板原文（「[或：…]」备选段、「XX」）。
交付件原样输出这些内容。生成源头已由 ``disclosure-note-template-word-realignment`` US-5 改为不自动调大模型，
库内存量只能在交付时过滤。

规则（按行，行 = 段落内以换行分开的一行；段落 = 解析后的块）
--------------------------------------------------------
- **提示段起点**（「审计师提示：」「【审计师备注】」「⚠️ 数据缺失提示」「编制说明：」「附注说明：」…）：该行及其后
  本章全部内容删除 —— 大模型把提示写在正文末尾，之后都是「请提供以下数据」清单；
- 大模型口吻 / 对用户的请求 / 免责声明（我将为您… / 请提供… / 贵司 / 以上文本为…模板）、条件式编制指引
  （若…请补充 / 应注明）、整行指引括注（（注：…）（若…））、「[或：…]」备选段、以「【注 / 【提示…」开头的
  【…】段（可跨行，直到「】」）、「[ ]」清单项、只剩占位符的行 —— 删除该行；
- 首行与章节标题（含「八、2 交易性金融资产」「10」「存货」这类编号 / 标题行）重复 —— 删除；
- 「【需补充信息】」补充清单标签连同同段清单项（「* …」「…？」）删除；括号内 ≥13 字的【…】（模板编制指引 / 可选披露，
  行首可跨行、行内剔除）删除；短【…】（「【A 公司】」「【和投资性房地产】」）是待填 / 待选，保留并计入待补充提醒；
- 行内指引括注（（如未限定经营期限，请删除）（若适用））剔除；行内「[请补充]」保留并计数（导出提醒）；
- 正文里的表格：章节有结构化表格时删除（重复）；任一单元格是占位（[待补充] / XX / 待填）时删除。

过滤只作用于交付件，不改库。
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, replace
from typing import Any, Iterable

__all__ = [
    "FilterStats",
    "deliverable_text_blocks",
    "filter_note_blocks",
    "is_guidance_line",
    "is_placeholder_text",
    "table_blank_for_delivery",
    "make_block_filter",
    "note_has_deliverable_content",
    "structured_tables_nonempty",
]


@dataclass
class FilterStats:
    """一次过滤的统计（汇总进导出提醒）。"""

    dropped_lines: int = 0
    dropped_tables: int = 0
    hint_tail_cut: bool = False
    placeholders_left: int = 0

    def merge(self, other: "FilterStats") -> None:
        self.dropped_lines += other.dropped_lines
        self.dropped_tables += other.dropped_tables
        self.hint_tail_cut = self.hint_tail_cut or other.hint_tail_cut
        self.placeholders_left += other.placeholders_left


def _nfkc(text: str) -> str:
    return unicodedata.normalize("NFKC", text or "")


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", _nfkc(text))


# ── 行判据（作用于 NFKC + 去首尾空白后的行文字）────────────────────────────────

_HINT_HEADER_RE = re.compile(
    r"^(?:\d{1,2}[.、．]\s*)?(?:⚠️?\s*)?[【\[]?\s*"
    r"(?:审计师|注册会计师|会计师|编制|附注编制|重要|数据(?:缺失|不足|补充)|需补充信息|待补充信息|补充信息|信息补充)"
    r"[^】\]:：]{0,16}?(?:提示|备注|说明|清单|注意)"
    r"[^】\]]{0,30}?[】\]]?\s*(?:[:：]|$)"
)
_META_HEADER_RE = re.compile(r"^(?:附注说明|填写说明|编制要点|填报说明)\s*[:：]\s*$")
_AI_VOICE_RE = re.compile(
    r"我将|我可以?为|您|贵司|如需进一步|希望(?:以上|本)"
    r"|以上(?:内容|文本|模板|附注正文|正文)(?:为|是|基于|仅)|以上为(?:基于|标准|通用|示例)"
    r"|本附注(?:正文)?(?:为|是)(?:标准化|通用|标准)?(?:披露)?模板"
    r"|标准化?披露模板|仅供参考|示例模板|当前(?:提供|生成)的(?:数据|附注|信息|正文)"
    # 附注是被审计单位的陈述：出现「审计师」、写给编制人的元说明（「由于缺乏…需由财务部门提供…以确保附注的完整性」）
    r"|审计师|由于(?:缺乏|缺少|未提供|数据不足)|需由[^。]{0,10}(?:提供|补充|确认)|以确保(?:附注|披露)"
    r"|当前(?:数据|资料)(?:未|不)|标准模板|待数据齐备|数据暂缺"
)
#: 「若上述数据暂缺，建议先按以下标准模板表述，待数据齐备后替换：」—— 其后是模板样例，本章到此截断
_TEMPLATE_INTRO_RE = re.compile(r"(?:以下|如下)[^。]{0,10}(?:模板|示例|格式|范本)[^。]{0,12}[:：]$")
#: 「票据分类明细：需列示银行承兑汇票…」—— 短标签 + 对编制人的要求
_LABEL_REQUEST_RE = re.compile(
    r"^(?:\d{1,2}[.、．]\s*)?[^。：:]{1,16}[:：]\s*(?:需|请|应(?!收|付|交|缴))[^。]{0,30}?"  # 「账龄分析：需按账龄（如…）列示」
    r"(?:列示|说明|披露|补充|提供|确认|核实|填写|填入|明确)"
)
#: 「4.应披露与持有待售…有关的其他综合收益累计金额。】」「…测算过程等信息。）」—— 开头已被删掉的【…】/（…）指引的尾巴
_GUIDE_TAIL_RE = re.compile(r"(?:应当?|需)(?:披露|说明|列示)[^【（(]*[】）)]$")
#: 「（①披露未办妥产权证书的土地使用权有关情况，…」—— 跨行的（…）编制指引开头（本行没有收括号）
_PAREN_GUIDE_OPEN_RE = re.compile(
    # 判定前已做 NFKC：「（①」变成「(1」，故序号后的分隔符可省
    r"^[（(]\s*(?:[①②③④⑤⑥⑦⑧⑨⑩]|\d{1,2}[.、．]?)?\s*(?:披露|说明|应当?|注\s*[:：]|企业应|根据|如|若)"
)
#: 「本期无此项业务。」—— 旧导入在每个表题下写的占位句；交付件里无业务的项目不出具
_NO_BUSINESS_RE = re.compile(r"^(?:本期|本年|报告期)?(?:内)?无此(?:项|类)?业务[。.]?$|^不适用[。.]?$")
#: 行首列表记号（「* 」「• 」）：判定前去掉
_BULLET_RE = re.compile(r"^[*•·\-–]\s+")
#: 句子特征字：带这些字的短编号行是陈述（「1、本公司无受限资金」）不是小标题
_SENTENCE_HINT_RE = re.compile(r"[无未为系已是有将均不]")
#: 去掉行首编号后是「需补充 / 需说明…」：对编制人的要求（「（1）需补充“账面余额”的具体数值。」）
_NEED_RE = re.compile(r"^(?:需|需要|应(?!收|付|交|缴))(?:补充|说明|披露|提供|列示|填写|填入|明确|核实|确认)")
#: 一行里占位达到这个数：是待填模板（「押金及保证金[需补充数据][需补充数据]备用金[需补充数据]…」），不是可出具的正文
_PLACEHOLDER_LINE_LIMIT = 4
_REQUEST_RE = re.compile(r"^(?:请|务必请|烦请)(?:提供|补充|根据|确认|核实|务必|将|在正式|结合|填写|替换|明确)")
_COND_GUIDE_RE = re.compile(
    # 「说明：1. 若本公司存在多层级股权结构，需补充披露…」「受限资金说明：若存在使用受限的现金…需单独列示」
    r"^(?:[^。：:]{1,12}[:：]\s*)?(?:\d{1,2}[.、．]\s*)?"
    r"(?:若|如|如果|如有|如存在|若存在|若无|若公司|若本公司|若\s*\d{4}\s*年度)[^。]{0,80}?"
    r"(?:请|需|应(?!收|付|交|缴)|则需|建议|可直接)[^。]{0,20}?"  # 「若数据缺失，请根据实际工商登记信息…补充」
    r"(?:补充|披露|注明|填|提供|说明|核实|表述|删除|修改|替换|列示|参照)"
)
_NOTE_GUIDE_RE = re.compile(
    r"^[（(]?\s*注\s*[:：][^。]{0,80}?(?:请|需补充|需要补充|若|如有|根据实际|模板|填写|示例|应与|应在)"
)
_PAREN_LINE_RE = re.compile(
    r"^[（(]\s*(?:注|提示|说明|若|如有|如果|如未|应(?:与|在|当|根据|填|补充|披露|注明)|企业应|根据|填写|以下|此处|如"
    r"|需补充|待补充|请补充)"
    r"[^（）()]*[）)][。.;；]?$"
)
_ALT_RE = re.compile(r"^\[\s*或\s*[:：]")
#: 「（《企业数据资源相关会计处理暂行规定》：企业应当披露…）」—— 引用规定的编制指引括注（整行）
_REG_GUIDE_RE = re.compile(r"^[（(]\s*《[^》]{1,40}》.*?(?:应当披露|应披露|可以|应在|应当)")
_BRACKET_GUIDE_RE = re.compile(r"^【\s*(?:注|提示|根据|披露|企业应|说明|如|若|适用)")
#: 「【需补充信息】：…」「【待补充信息】」—— 大模型写给编制人的补充清单标签：本行删除，同段紧跟的清单项一并删
_BRACKET_HINT_RE = re.compile(r"^【\s*(?:需|待)?(?:补充|提供|完善)[^】]{0,8}】")
#: 补充清单项：「* 持有待售资产的具体类别…」「是否存在关联方应付账款？」
_HINT_ITEM_RE = re.compile(r"^[*•·\-–]\s*|[？?]$")
#: 长【…】（括号内 ≥13 字）：模板编制指引 / 可选披露（「【或者，按地理区域…】」「…调整的内容和原因。【包括其他调整事项的陈述…】」）
#: 剔除，括号外的正文保留；本行没收括号（「【存在下列情况的，可能说明…」）时删到行尾、后续行删到「】」。
#: 短的（「【A 公司】」「【和投资性房地产】」）是待填 / 待选占位，保留并计入待补充提醒
_INLINE_BRACKET_RE = re.compile(r"【[^】]{13,}】")
_INLINE_BRACKET_OPEN_RE = re.compile(r"【[^】]{13,}$")
_CHECKBOX_RE = re.compile(r"^\[\s*\]")
_SUGGEST_RE = re.compile(r"^(?:建议|提示\s*[:：]|注意\s*[:：])")
_PLACEHOLDER_RE = re.compile(
    r"[\[［【][^\]］】]{0,40}?(?:补充|待填|待定|填写|需填|待核实|待确认)[^\]］】]{0,40}[\]］】]"
    r"|[\[［]\s*X{1,4}\s*[\]］]|X{2,}|×{2,}|ｘ{2,}|x{2,}(?=元|家|%|号|年|月|日|名)"
)
#: 计数 / 判「只剩占位」用的宽口径：正文里的方括号几乎都是占位（「[成立年份]」「[注册地]」）
_PLACEHOLDER_COUNT_RE = re.compile(
    r"[\[［][^\]］\n]{1,40}[\]］]|【[^】\n]{1,12}】|X{2,}|×{2,}|ｘ{2,}|x{2,}(?=元|家|%|号|年|月|日|名)"
)
_INLINE_GUIDE_RE = re.compile(
    r"[（(]\s*(?:注\s*[:：]|提示|若|如有|如果|如未|应(?:与|在|根据|填|补充|披露|注明)|企业应|请|需补充|待补充)"
    r"[^（）()]{0,120}[）)]"
    r"|[（(]\s*根据[^（）()]{0,120}?(?:请|需补充|模板)[^（）()]{0,60}[）)]"
)
_PUNCT_ONLY_RE = re.compile(r"^[\s\W_]*$")
_LEAD_CODE_RE = re.compile(r"^(?:[一二三四五六七八九十百]+、)?\d*(?:[.、．]\d+)*[.、．]?")


def _strip_lead_code(text: str) -> str:
    return _LEAD_CODE_RE.sub("", text, count=1)


def _is_dup_title(line: str, title_key: str, code: str) -> bool:
    from app.services.note_deliverable_outline import title_key as _title_key

    c = _compact(line)
    if not c:
        return False
    if re.fullmatch(r"\d{1,3}", c):
        return True  # 「10」—— 序号行
    if code and c == _compact(code):
        return True  # 「四、存货」—— 编号本身就带标题
    if code and c.startswith(_compact(code)):
        c = c[len(_compact(code)):]
    c = _strip_lead_code(c).strip(".、．:：")
    return bool(title_key) and _title_key(c) == title_key


def _is_jumble(line: str, title_key: str) -> bool:
    """「10存货存货分类本期无此项业务。八、10 存货1. …」—— 序号 + 标题粘连的旧导入残片。"""
    c = _compact(line)
    return bool(title_key) and bool(re.match(r"^\d{1,3}" + re.escape(title_key), c))


def _placeholder_only(line: str) -> bool:
    """只剩占位：去掉占位、短标签（「期末余额：」）与单位后没有实际内容。"""
    text = _nfkc(line)
    if not _PLACEHOLDER_COUNT_RE.search(text):
        return False
    rest = _PLACEHOLDER_COUNT_RE.sub("", text).strip()
    rest = re.sub(r"^[^。：:]{1,12}[:：]", "", rest)
    rest = re.sub(r"万?元|%|家|个", "", rest)
    return bool(_PUNCT_ONLY_RE.match(rest))


@dataclass
class _LineVerdict:
    drop: bool = False
    cut_tail: bool = False
    open_bracket: bool = False
    open_paren: bool = False
    hint_list: bool = False


def _judge(line: str) -> _LineVerdict:
    t = _BULLET_RE.sub("", _nfkc(line).strip())
    if not t:
        return _LineVerdict()
    if _HINT_HEADER_RE.match(t) or _META_HEADER_RE.match(t) or _TEMPLATE_INTRO_RE.search(t):
        return _LineVerdict(drop=True, cut_tail=True)
    if _BRACKET_HINT_RE.match(t):
        return _LineVerdict(drop=True, hint_list=True)
    if _BRACKET_GUIDE_RE.match(t):
        return _LineVerdict(drop=True, open_bracket="】" not in t)
    if _PAREN_GUIDE_OPEN_RE.match(t) and "）" not in t and ")" not in t:
        return _LineVerdict(drop=True, open_paren=True)
    bare = _ANY_LEAD_ENUM_RE.sub("", t)
    if (
        _AI_VOICE_RE.search(t)
        or _NO_BUSINESS_RE.match(t)
        or _REQUEST_RE.match(t)
        or _NEED_RE.match(bare)
        or len(_PLACEHOLDER_COUNT_RE.findall(t)) >= _PLACEHOLDER_LINE_LIMIT
        or _LABEL_REQUEST_RE.match(t)
        or ("【" not in t and "（" not in t and "(" not in t and _GUIDE_TAIL_RE.search(t))
        or _COND_GUIDE_RE.match(t)
        or _NOTE_GUIDE_RE.match(t)
        or _PAREN_LINE_RE.match(t)
        or _REG_GUIDE_RE.match(t)
        or _ALT_RE.match(t)
        or _CHECKBOX_RE.match(t)
        or _SUGGEST_RE.match(t)
        or _placeholder_only(t)
    ):
        return _LineVerdict(drop=True)
    return _LineVerdict()


def is_placeholder_text(text: str | None) -> bool:
    """正文只是无业务占位话（「本期无此项业务。」「不适用。」）：每个非空行规范化后都是这类句子。

    交付件按 ``_NO_BUSINESS_RE`` 删的就是这些行；上年附注导入 / 继承用同一判定：上年正文是占位话就不导入、
    不覆盖本年（spec consol-note-header-library-and-node-reaggregate R7.3）。HTML 正文按交付件提取口径取文字；
    空文本不算占位（调用方另判空）。
    """
    from app.services.note_text_word_render import note_text_plain

    lines = [_BULLET_RE.sub("", _nfkc(line).strip()) for line in note_text_plain(text).splitlines()]
    lines = [line for line in lines if line]
    return bool(lines) and all(_NO_BUSINESS_RE.match(line) for line in lines)


# ── 块操作 ────────────────────────────────────────────────────────────────────


def _block_types():
    from app.services.note_text_word_render import _Para, _Run, _Table

    return _Para, _Run, _Table


def _para_lines(para) -> list[list[Any]]:
    """段落按换行拆成行（保留 run 的粗斜体）。"""
    _Para, _Run, _Table = _block_types()
    lines: list[list[Any]] = [[]]
    for r in para.runs:
        parts = r.text.split("\n")
        for i, part in enumerate(parts):
            if i:
                lines.append([])
            if part:
                lines[-1].append(_Run(part, r.bold, r.italic))
    return lines


def _line_text(runs: list[Any]) -> str:
    return "".join(r.text for r in runs)


def _clean_inline(runs: list[Any]) -> list[Any]:
    out = []
    for i, r in enumerate(runs):
        text = _INLINE_BRACKET_RE.sub("", _INLINE_GUIDE_RE.sub("", r.text))
        if text != r.text and i == 0:
            text = re.sub(r"^[：:，,；;。\s]+", "", text)  # 行首括注删掉后不留孤立标点
        if text:
            out.append(replace(r, text=text))
    return out


def _truncate_runs(runs: list[Any], end: int) -> list[Any]:
    """行内前 ``end`` 个字符（跨 run，保留各 run 格式）。"""
    out, pos = [], 0
    for r in runs:
        if pos >= end:
            break
        keep = r.text[: end - pos]
        if keep:
            out.append(replace(r, text=keep))
        pos += len(r.text)
    return out


def _table_has_placeholder(table) -> bool:
    texts = []
    for row in table.rows:
        for cell in row:
            for p in cell.paragraphs:
                texts.append("".join(r.text for r in p.runs))
    joined = "".join(texts)
    if not _compact(joined) or _table_all_zero(table):
        return True  # 全空表 / 只有 0
    return any(_PLACEHOLDER_RE.search(_nfkc(t)) or re.search(r"待(?:补充|填|定)|需补充|X\.XX", _nfkc(t)) for t in texts)


_INTRO_RE = re.compile(r"如下\s*[:：]\s*$")
_HEADING_LIKE_RE = re.compile(
    r"^(?:\d{1,2}[.、．]|[（(]\d{1,2}[）)]|[一二三四五六七八九十]{1,3}、|[（(][一二三四五六七八九十]{1,3}[）)])\s*[^。；;]{1,32}$"
)
_ANY_LEAD_ENUM_RE = re.compile(
    r"^(?:\d{1,2}[.、．]|[（(]\d{1,2}[）)]|[一二三四五六七八九十]{1,3}、|[（(][一二三四五六七八九十]{1,3}[）)])\s*"
)
_NUM_CELL_RE = re.compile(r"^[-－—–]?[\d,，.]+%?$")


def _table_all_zero(table) -> bool:
    """正文表（除表头行、首列）只有 0 / 空：大模型拼的「在建工程 0.00 0.00 合计 0.00」。"""
    if len(table.rows) < 2:
        return False
    for row in table.rows[1:]:
        for cell in row[1:]:
            t = _compact("".join("".join(r.text for r in p.runs) for p in cell.paragraphs))
            if not t or t in ("-", "—", "－", "/"):
                continue
            if not _NUM_CELL_RE.match(t):
                return False
            try:
                if abs(float(t.replace(",", "").replace("，", "").rstrip("%"))) >= 0.005:
                    return False
            except ValueError:
                return False
    return True


def _post_pass(seq: list[list[Any]], st: FilterStats) -> list[list[Any]]:
    """行级收尾：表被删掉后悬空的「…如下：」引导句、其下已无内容的小标题行一并删除。

    ``seq`` 元素：``["L", 段序, runs]`` / ``["T", table]`` / ``["D"]``（被删的正文表）/ ``["B", 段序]``（空段）/
    ``["Z"]``（主过滤删掉的一行）/ ``["X"]``（本轮收尾删掉的行）。
    """
    changed = True
    while changed:
        changed = False
        for i, item in enumerate(seq):
            if item[0] != "L":
                continue
            nxt = next((x for x in seq[i + 1:] if x[0] != "B"), None)
            nxt_kept = next((x for x in seq[i + 1:] if x[0] not in ("B", "Z")), None)
            text = _nfkc(_line_text(item[2])).strip()
            if _INTRO_RE.search(text) and (nxt_kept is None or nxt_kept[0] != "T"):
                seq[i] = ["X"]
                changed = True
            elif _is_orphan_heading(text, nxt):
                seq[i] = ["X"]
                changed = True
        if changed:
            dropped = sum(1 for x in seq if x[0] == "X")
            st.dropped_lines += dropped
            seq = [["Z"] if x[0] == "X" else x for x in seq]  # 删掉的行留 Z 记号：上一级小标题可能随之悬空
    return [x for x in seq if x[0] != "Z"]


def _is_orphan_heading(text: str, nxt: list[Any] | None) -> bool:
    """其下内容都被过滤掉的小标题（「3. 重要披露事项」后面全是「需补充…」）。

    只认短的名词性编号行：带句子特征字的（「1、本公司无受限资金」）是列表项陈述，不删；
    末行只在以冒号结尾时删（「2. 其他说明：」）。
    """
    m = _HEADING_LIKE_RE.match(text)
    if not m:
        return False
    noun = not _SENTENCE_HINT_RE.search(_ANY_LEAD_ENUM_RE.sub("", text))
    if nxt is None:
        # 正文末尾：冒号结尾，或「1. / （1）」编号的名词性小标题（其下什么都没有）；
        # 「八、1 …」「一、…」这类章节式编号行不按末行规则删（可能就是整段正文）
        return text.endswith((":", "：")) or (noun and not re.match(r"^[一二三四五六七八九十]{1,3}、", text))
    if nxt[0] not in ("D", "X", "Z"):
        return False
    return noun


def _is_structure_dup(line: str, keys: set[str]) -> bool:
    """正文里与模板子标题 / 表题重复的短行（「1. 预付款项按账龄列示」↔ 模板「（1）预付款项按账龄列示」；
    旧导入把模板表题「无形资产情况」写进了正文）。交付件按模板结构出这些标题，正文里的重复删除。"""
    from app.services.note_deliverable_outline import title_key as _title_key

    t = _nfkc(line).strip()
    if not keys or len(t) > 40 or t.endswith(("。", "；", ";")):
        return False
    return _title_key(_ANY_LEAD_ENUM_RE.sub("", t).strip(":：")) in keys


def filter_note_blocks(
    blocks: Iterable[Any],
    *,
    title: str | None = None,
    code: str | None = None,
    has_structured_tables: bool = False,
    stats: FilterStats | None = None,
    extra_titles: Iterable[str] = (),
    structure_titles: Iterable[str] = (),
) -> list[Any]:
    """过滤解析后的正文块（``note_text_word_render._parse`` 的产物）。

    ``extra_titles``：章首重复判定额外比对的标题（所在章标题：正文首行「九、或有事项」）；
    ``structure_titles``：模板块里已有的子标题 / 表题，正文里同名的编号短行删除（交付件按模板结构出这些标题）。
    """
    _Para, _Run, _Table = _block_types()
    from app.services.note_deliverable_outline import title_key as _title_key

    st = stats if stats is not None else FilterStats()
    tkey = _title_key(title or "")
    extra_keys = [k for k in (_title_key(t) for t in extra_titles) if k]
    structure_keys = {k for k in (_title_key(t) for t in structure_titles) if k}
    paras: list[Any] = []  # 段序 → 原段落（取段落属性）
    seq: list[list[Any]] = []
    leading = True  # 仍在章首（只在章首判重复标题）
    in_bracket = False
    in_paren, paren_left = False, 0
    in_hint_list = False  # 「【需补充信息】」之后同段的清单项
    cut = False
    for block in blocks:
        if cut:
            break
        if isinstance(block, _Table):
            if has_structured_tables or _table_has_placeholder(block):
                st.dropped_tables += 1
                seq.append(["D"])
                continue
            seq.append(["T", block])
            leading = False
            continue
        if not isinstance(block, _Para):
            continue
        pi = len(paras)
        paras.append(block)
        in_hint_list = False
        if not block.has_text():
            seq.append(["B", pi])
            continue
        for runs in _para_lines(block):
            text = _line_text(runs)
            if in_bracket:
                st.dropped_lines += 1
                seq.append(["Z"])
                if "】" in text:
                    in_bracket = False
                continue
            if in_paren:  # 跨行的（…）编制指引：删到收括号所在行（最多 8 行，防括号不配对误删正文）
                st.dropped_lines += 1
                seq.append(["Z"])
                paren_left -= 1
                if "）" in text or ")" in text or paren_left <= 0:
                    in_paren = False
                continue
            if not text.strip():
                continue
            if in_hint_list and _HINT_ITEM_RE.search(_nfkc(text).strip()):
                st.dropped_lines += 1
                seq.append(["Z"])
                continue
            if leading and (
                _is_dup_title(text, tkey, code or "") or _is_jumble(text, tkey)
                or any(_is_dup_title(text, k, "") for k in extra_keys)
            ):
                st.dropped_lines += 1
                continue
            if _is_structure_dup(text, structure_keys):  # 模板已有这个子标题 / 表题
                st.dropped_lines += 1
                seq.append(["Z"])
                continue
            verdict = _judge(text)
            if verdict.cut_tail:
                st.dropped_lines += 1
                st.hint_tail_cut = True
                seq.append(["Z"])
                cut = True
                break
            if verdict.drop:
                st.dropped_lines += 1
                seq.append(["Z"])  # 记下「这里删过一行」：其上的小标题若因此悬空，收尾时一并删
                in_bracket = verdict.open_bracket
                in_paren, paren_left = verdict.open_paren, 8
                in_hint_list = verdict.hint_list or in_hint_list  # 清单前的「请提供以下…：」不打断
                continue
            in_hint_list = False
            m_open = _INLINE_BRACKET_OPEN_RE.search(text)
            if m_open:  # 行内长【…】本行没收括号：删到行尾，后续行删到「】」
                runs = _truncate_runs(runs, m_open.start())
                in_bracket = True
                st.dropped_lines += 1
            cleaned = _clean_inline(runs)
            if not _compact(_line_text(cleaned)):
                st.dropped_lines += 1
                seq.append(["Z"])
                continue
            seq.append(["L", pi, cleaned])
            leading = False
    seq = _post_pass(seq, st)

    # 重组：同一原段落的相邻行合回一段（行间换行）；空段压缩
    out: list[Any] = []
    cur_pi: int | None = None
    cur_runs: list[Any] = []

    def _flush() -> None:
        nonlocal cur_pi, cur_runs
        if cur_pi is not None and cur_runs:
            out.append(replace(paras[cur_pi], runs=cur_runs))
        cur_pi, cur_runs = None, []

    for item in seq:
        if item[0] == "L":
            if item[1] != cur_pi:
                _flush()
                cur_pi = item[1]
            elif cur_runs:
                cur_runs.append(_Run("\n"))
            cur_runs.extend(item[2])
            st.placeholders_left += len(_PLACEHOLDER_COUNT_RE.findall(_nfkc(_line_text(item[2]))))
        elif item[0] == "T":
            _flush()
            out.append(item[1])
        elif item[0] == "B":
            _flush()
            if out and not (isinstance(out[-1], _Para) and not out[-1].has_text()):
                out.append(paras[item[1]])
    _flush()
    compact = out
    while compact and isinstance(compact[-1], _Para) and not compact[-1].has_text():
        compact.pop()
    return compact


def _zero_like(v: Any) -> bool:
    """交付口径的「空值」：None / 空串 / 数值 0 / 「0.00」「-」这类只表示零的文本。"""
    if isinstance(v, dict):
        v = v.get("value", v.get("manual_value"))
    if v is None or isinstance(v, bool):
        return not v
    if isinstance(v, (int, float)):
        return abs(float(v)) < 0.005
    s = str(v).strip().replace(",", "").replace("，", "")
    if s in ("", "-", "—", "－", "/"):
        return True
    try:
        return abs(float(s)) < 0.005
    except ValueError:
        return False


def table_blank_for_delivery(rows: Any, columns: Any = None) -> bool:
    """交付口径的空表：``is_empty_table`` 为空，或（缺列定义时）数值全为 0。

    ``is_empty_table`` 在没有列定义时把 0 当「文本列里填了 0」算非空 —— 模块页口径；交付件里全 0 的表
    渲染出来是一张只有行名的空表（金额 0 显示为空白），与「本期无此业务」同义，不出具。
    """
    from app.services.note_empty_table_detector import (
        SKIP_ROW_TYPES, is_empty_table, is_total_row, total_row_has_amount,
    )

    if is_empty_table(rows, columns):
        return True
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict) or str(row.get("row_type") or "") in SKIP_ROW_TYPES:
            continue
        if is_total_row(row):
            if total_row_has_amount(row, columns):
                return False  # 合计行有数（公式推送的合计行兜底）：有业务
            continue
        values = row.get("values")
        if isinstance(values, list) and not all(_zero_like(v) for v in values):
            return False
    return True


def structured_tables_nonempty(note: Any) -> bool:
    """章节结构化表格（``table_data``，含底稿投影）里有非空、可导出的表。"""
    from app.services.note_content_utils import effective_table_data

    try:
        td = effective_table_data(getattr(note, "table_data", None))
        if not isinstance(td, dict):
            return False
        tables = td.get("_tables") or [td]
        for t in tables:
            if not isinstance(t, dict) or not t.get("export_enabled", True):
                continue
            if t.get("rows") and not table_blank_for_delivery(t.get("rows"), t.get("columns")):
                return True
    except Exception:  # noqa: BLE001 — 判空失败按无表处理
        return False
    return False


def deliverable_text_blocks(
    note: Any,
    *,
    stats: FilterStats | None = None,
    extra_titles: Iterable[str] = (),
    structure_titles: Iterable[str] = (),
) -> list[Any]:
    """章节正文过滤后的块列表（``extra_titles`` / ``structure_titles`` 见 :func:`filter_note_blocks`）。"""
    from app.services.note_text_word_render import _as_html, _parse

    text = getattr(note, "text_content", None) or ""
    if not text.strip():
        return []
    return filter_note_blocks(
        _parse(_as_html(text)),
        title=getattr(note, "section_title", None),
        code=getattr(note, "note_section", None),
        has_structured_tables=structured_tables_nonempty(note),
        stats=stats,
        extra_titles=extra_titles,
        structure_titles=structure_titles,
    )


def is_guidance_line(text: str) -> bool:
    """单行文字是否编制指引 / 大模型提示（模板表题候选判定用：指引段不当表题）。"""
    verdict = _judge(text)
    return verdict.drop or verdict.cut_tail


def note_has_deliverable_content(
    note: Any, *, extra_titles: Iterable[str] = (), structure_titles: Iterable[str] = (),
) -> bool:
    """交付口径的「有内容」：结构化表格非空，或过滤后的正文非空（过滤口径与导出渲染同一组标题）。"""
    _Para, _Run, _Table = _block_types()
    if structured_tables_nonempty(note):
        return True
    for b in deliverable_text_blocks(note, extra_titles=extra_titles, structure_titles=structure_titles):
        if isinstance(b, _Table):
            return True
        if isinstance(b, _Para) and _compact(_line_text(b.runs)):
            return True
    return False


def make_block_filter(
    note: Any,
    stats: FilterStats | None = None,
    *,
    extra_titles: Iterable[str] = (),
    structure_titles: Iterable[str] = (),
):
    """给 ``append_note_text`` / ``fill_paragraph_with_note_text`` 的 ``block_filter`` 参数用。"""
    has_tables = structured_tables_nonempty(note)
    extra = tuple(t for t in extra_titles if t)
    structure = tuple(t for t in structure_titles if t)

    def _filter(blocks: list[Any]) -> list[Any]:
        return filter_note_blocks(
            blocks,
            title=getattr(note, "section_title", None),
            code=getattr(note, "note_section", None),
            has_structured_tables=has_tables,
            stats=stats,
            extra_titles=extra,
            structure_titles=structure,
        )

    return _filter
