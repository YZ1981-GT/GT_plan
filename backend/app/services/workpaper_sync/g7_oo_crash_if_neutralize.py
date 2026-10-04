"""G7 专用：中性化让 OnlyOffice 9.4 加载期崩溃的裸 `IF()`（zip 级）。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure

═══ 为什么是独立伴生模块 ═══

本段原先内联在 `pilot_g7_two_level_dynamic.py` 里，把该文件顶到 2662 行、触发仓库的
文件行数门禁（基线 2450 +5%）。门禁的处置顺序明写「优先拆分文件或抽伴生模块，确有必要
再更新 whitelist 基线」—— 打磨应让文件变小不变大，故按门禁指引外抽，而不是抬基线。

这段本身也是自洽的：纯函数、只吃一个 xlsx 路径、不碰 pilot 的 manifest/payload 状态，
与 pilot 的其余部分没有共享可变量。

═══ 唯一定义，多处再导出 ═══

`pilot_g7_two_level_dynamic` 从本模块 re-export `neutralize_oo_crash_if_formulas`
（及判据要用的 `_BARE_IF_CALL` / `_F_ELEMENT` / `_strip_bare_if_cells`），因此
`adapters/excel.py` 那两处 `from …pilot_g7_two_level_dynamic import
neutralize_oo_crash_if_formulas` 的延迟 import 形态**一字不改**仍然可解析。
定义只有一份，在这里。

═══ 这个函数为什么必须存在于生产模块里 ═══

`adapters/excel.py` 的 `materialize` 与 `verify_unmanaged_regions` 两处都在
`adapter_id == "g7.soe_subsidiary_disclosure"` 分支里 import 它。那两处调用点是 commit
`82f58ea44` 推上来的，而函数本体**从未随任何 commit 落地**（`git log -S
"def neutralize_oo_crash_if_formulas" --all -- ":(glob)backend/**/*.py"` 零命中）⇒ HEAD 上
G7 的整条 materialize/verify 路径带着一个 `ImportError` 在跑。本函数按已被真实 OO 栈验收
过的口径补齐（evidence：`.kiro/specs/workpaper-html-onlyoffice-bidirectional-writeback-
closure/evidence/g4-1-g7-host-unified-path/` README §「本轮修复」第 2 条：**zip 级剥离裸
`IF()` + 丢 `calcChain`；检测用 OOXML 词界 IF（忽略 SUMIF/COUNTIF）；verify_unmanaged
对比前同样 neutralize**）。
"""
from __future__ import annotations

import io
import re
import zipfile
from collections.abc import Mapping
from pathlib import Path
from typing import Final

__all__ = ("neutralize_oo_crash_if_formulas",)


# ═══════════════════════════════════════════════════════════════════════════
# OO 9.4 `editor_error_-82`：裸 IF() 中性化（zip 级）
# ═══════════════════════════════════════════════════════════════════════════
#
# 🔴 为什么这个函数必须存在于**生产**模块里：
# `adapters/excel.py` 的 `materialize` 与 `verify_unmanaged_regions` 两处都在
# `adapter_id == "g7.soe_subsidiary_disclosure"` 分支里 import 它。那两处调用点是
# commit `82f58ea44` 推上来的，而函数本体**从未随任何 commit 落地**（`git log -S
# "def neutralize_oo_crash_if_formulas" --all -- ":(glob)backend/**/*.py"` 零命中）
# ⇒ HEAD 上 G7 的整条 materialize/verify 路径带着一个 `ImportError` 在跑。
# 本函数按已被真实 OO 栈验收过的口径补齐（evidence：`.kiro/specs/workpaper-html-
# onlyoffice-bidirectional-writeback-closure/evidence/g4-1-g7-host-unified-path/`
# README §「本轮修复」第 2 条：**zip 级剥离裸 `IF()` + 丢 `calcChain`；检测用 OOXML
# 词界 IF（忽略 SUMIF/COUNTIF）；verify_unmanaged 对比前同样 neutralize**）。

#: 可再生的派生部件：留着它会指向被摘掉的公式格，OO 加载期照样炸。
#: 与 `excel_extract.DERIVED_PARTS` 同一判断（那里是「比对时放过」，这里是「物理丢弃」）。
_CALC_CHAIN_PART: Final[str] = "xl/calcChain.xml"

#: OOXML **词界** `IF(`：
#: * `SUMIF(` / `COUNTIF(` / `AVERAGEIF(` 的 `IF(` 前面是字母 ⇒ 被 lookbehind 挡住；
#: * `IFERROR(` / `IFS(` / `IFNA(` 的 `IF` 后面不是 `(` ⇒ 压根不命中。
#: 命中的只有真正走 `cIF.Calculate` 的那一族（含嵌在 `IFERROR(IF(...))` 里的内层 IF —— 它
#: 一样进 `cIF`，所以**故意**也算命中）。
_BARE_IF_CALL: Final[re.Pattern[str]] = re.compile(r"(?<![A-Za-z0-9_.])IF\s*\(")

_CELL_ELEMENT: Final[re.Pattern[str]] = re.compile(
    r"<c(?P<attrs>[^>]*?)(?:/>|>(?P<body>.*?)</c>)", re.DOTALL
)
_F_ELEMENT: Final[re.Pattern[str]] = re.compile(
    r"<f(?P<attrs>[^>]*?)(?:/>|>(?P<body>.*?)</f>)", re.DOTALL
)
_R_ATTR: Final[re.Pattern[str]] = re.compile(r'\br="([^"]+)"')
_SI_ATTR: Final[re.Pattern[str]] = re.compile(r'\bsi="([^"]+)"')
_CALC_CHAIN_OVERRIDE: Final[re.Pattern[str]] = re.compile(
    r'<Override\b[^>]*PartName="/xl/calcChain\.xml"[^>]*/>'
)
_CALC_CHAIN_REL: Final[re.Pattern[str]] = re.compile(
    r'<Relationship\b[^>]*Target="calcChain\.xml"[^>]*/>'
)


def _strip_bare_if_cells(xml: str) -> tuple[str, list[str]]:
    """摘掉一张 sheet 里所有含裸 `IF(` 的 `<f>` 元素，**保留** `<v>` 缓存值。

    保留 `<v>` 是这条口径的要点：摘的是「让 OO 崩的计算」，不是「格子里的数」。实测
    G7 权威模板 1065 个裸 IF 格**全部**带 `<v>` ⇒ 摘完仍是原样的静态呈现。

    共享公式（`<f t="shared" si="N">`）：主格命中就把同 `si` 的从格
    （`<f t="shared" si="N"/>`，自身无公式文本）一起摘 —— 否则从格会指向一个已经
    不存在的主格，比原来的崩法更隐蔽。实测本工作簿 shared 计数为 0，这条是防御。
    """
    poisoned: set[str] = set()
    for fm in _F_ELEMENT.finditer(xml):
        if not _BARE_IF_CALL.search(fm.group("body") or ""):
            continue
        si = _SI_ATTR.search(fm.group("attrs") or "")
        if si is not None:
            poisoned.add(si.group(1))

    refs: list[str] = []

    def _rewrite_cell(match: re.Match[str]) -> str:
        body = match.group("body")
        if body is None or "<f" not in body:
            return match.group(0)
        attrs = match.group("attrs") or ""
        dropped = False

        def _drop_f(fm: re.Match[str]) -> str:
            nonlocal dropped
            si = _SI_ATTR.search(fm.group("attrs") or "")
            hit = bool(_BARE_IF_CALL.search(fm.group("body") or "")) or (
                si is not None and si.group(1) in poisoned
            )
            if not hit:
                return fm.group(0)
            dropped = True
            return ""

        new_body = _F_ELEMENT.sub(_drop_f, body)
        if not dropped:
            return match.group(0)
        ref = _R_ATTR.search(attrs)
        refs.append(ref.group(1) if ref is not None else "?")
        return f"<c{attrs}>{new_body}</c>"

    return _CELL_ELEMENT.sub(_rewrite_cell, xml), refs


def _repack_dropping(
    data: bytes, replacements: Mapping[str, bytes], dropped: frozenset[str]
) -> bytes:
    """只换 `replacements`、只丢 `dropped`，其余部件连 `ZipInfo` 一起原样搬过去。

    🔴 与 `excel_sheet_visibility._replace_workbook_part` /
    `excel_workbook_row_change._repack` 同形（ZipInfo 克隆逻辑逐字相同）；本函数多一件
    「丢部件」的事，那两个都做不了。保留 `date_time` / `compress_type` / 属性位，让
    「除声明部件外一个字节都没动」在 zip 元数据层面也成立。
    """
    buffer = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as src:
        with zipfile.ZipFile(buffer, "w") as out:
            for info in src.infolist():
                if info.filename in dropped:
                    continue
                payload = replacements.get(info.filename, src.read(info.filename))
                clone = zipfile.ZipInfo(info.filename, date_time=info.date_time)
                clone.compress_type = info.compress_type
                clone.external_attr = info.external_attr
                clone.internal_attr = info.internal_attr
                clone.create_system = info.create_system
                clone.flag_bits = info.flag_bits & ~0x08  # 不用 data descriptor
                out.writestr(clone, payload)
    return buffer.getvalue()


def neutralize_oo_crash_if_formulas(path: Path) -> tuple[str, ...]:
    """**就地**中性化 `path` 这份 xlsx 里让 OO 9.4 加载期崩溃的裸 `IF()`。

    OnlyOffice 9.4 在文档加载完成**之前**就跑依赖图计算，G7 整册里有 `IF()` 的参数在
    OO 侧解析成 undefined，`cIF.Calculate` 读 `tocBool` 抛 TypeError ⇒ 前端收
    `editor_error_-82`。容器 healthy、sdk 已加载 —— 不是「OO 不可用」，是**这份文档的
    内容**让 OO 崩了（诊断全文见 `docs/operations/
    oo-html-bidirectional-writeback-5-lane-assignment.md`）。

    做两件事，都在 zip 部件层面，**不过 openpyxl**（openpyxl 全量重写会丢部件、把共享
    公式展平、把缓存值写成 `<v></v>` —— `excel_sheet_visibility` 模块头记着实测账）：

    1. 每张 `xl/worksheets/*.xml` 里含词界 `IF(` 的 `<f>` 元素整个摘掉，`<v>` 留着；
    2. 丢 `xl/calcChain.xml`，并把 `[Content_Types].xml` 的 Override 与
       `xl/_rels/workbook.xml.rels` 的 Relationship 一并摘干净（留着悬空引用 Excel 会
       报「需要修复」）。

    **幂等**：跑完第二遍既找不到裸 IF 也找不到 calcChain ⇒ 直接返回 `()` 且**一个字节
    都不写**。这条是 `verify_unmanaged_regions` 能用同一口径比 before/after 的前提：
    materialize 侧在 substrate 副本上中性化过，verify 侧必须对 before 做**同样**的事，
    否则「清 IF」会被判成 unmanaged 公式漂移，commit 永远进不去，OO 继续吃带 IF 的
    published 表示 → 又是 -82。

    :param path: 要就地改写的 xlsx。调用方**必须**先 `shutil.copy2` 出副本再传进来 ——
        durable / published artifact 一字不动是 AC 8.10，也是本 spec 吃过的教训
        （手改 published immutable artifact 致 digest 漂移 → store-projection 500）。
    :returns: 被摘掉公式的格子，形如 ``("xl/worksheets/sheet15.xml!C9", ...)``；
        没改动则为空元组。
    """
    target = Path(path)
    data = target.read_bytes()
    replacements: dict[str, bytes] = {}
    neutralized: list[str] = []

    with zipfile.ZipFile(io.BytesIO(data)) as src:
        names = tuple(src.namelist())
        for name in names:
            if not (name.startswith("xl/worksheets/") and name.endswith(".xml")):
                continue
            xml = src.read(name).decode("utf-8")
            new_xml, refs = _strip_bare_if_cells(xml)
            if new_xml == xml:
                continue
            replacements[name] = new_xml.encode("utf-8")
            neutralized.extend(f"{name}!{ref}" for ref in refs)

        dropped: frozenset[str] = frozenset(
            {_CALC_CHAIN_PART} if _CALC_CHAIN_PART in names else ()
        )
        if dropped:
            for part, pattern in (
                ("[Content_Types].xml", _CALC_CHAIN_OVERRIDE),
                ("xl/_rels/workbook.xml.rels", _CALC_CHAIN_REL),
            ):
                if part not in names:
                    continue
                text = src.read(part).decode("utf-8")
                cleaned = pattern.sub("", text)
                if cleaned != text:
                    replacements[part] = cleaned.encode("utf-8")

    if not replacements and not dropped:
        return ()
    target.write_bytes(_repack_dropping(data, replacements, dropped))
    return tuple(neutralized)
