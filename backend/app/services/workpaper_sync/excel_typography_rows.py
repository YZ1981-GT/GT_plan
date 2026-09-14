"""受管区尾部「排版占位行」的**平台级**单一真源（BP-21）。

═══ 为什么需要一个独立模块 ══════════════════════════════════════════════════

中文审计模板普遍在数据区末尾放一行**续行省略号**（整格文本为 `……`），紧跟其后才是
`合计` / `小计` / `总计`。它是排版符号，不是业务行：

```
A13..A26 = 1 .. 14      整数 seq，业务数据
A27      = ……            ← 排版占位（模板里常写成 &#8230;&#8230;）
A28      = 合计          footer 锚点
```

而受管区行范围是**派生**的（`first_data_row` + 骨架行数 → `last_data_row`，footer 锚点在其后
一行）。派生规则「表头与合计之间都是数据行」会把这行省略号一并吞进受管区，后果是
`materialize` 试图把 `……` 按 `integer` 写回业务字段 —— 首版发布实测就卡在这里
（`EditableCellWriteError`，H1 的 `A27`）。

全模板库实测（349 份 xlsx / 2602 张 sheet）：整格为纯省略号的 A/B/C 列格 **842** 个，
其中「`……` 行紧跟合计/小计/总计行」**170** 处，涉及 **37 份**模板、**35 个** wp_code。

⇒ 逐契约写 `excluded_rows` 等于要写 170 条声明，且每份新契约都得记得写 —— 那是**必然遗漏**
的形态。故本模块把判据下沉成平台级规则，并由
:func:`assert_last_data_row_is_not_typography_placeholder` 在 instrumentation 期
**fail closed**：provider 声明的 `last_data_row` 落在排版占位行上时直接抛错并给出应声明的值。

═══ 为什么是 fail closed 而不是「引擎自动收缩」 ═══════════════════════════════

自动收缩会让 `spec.last_data_row`（provider 的声明）与引擎实际用的行区间**不一致** ——
`GT_ROW_UUID_LAST_ROW` 写 27 而 UUID 只写到 26。那种「声明与实况不符」自己就是一类缺陷，
且它把问题变成隐性的：下一个 provider 作者永远不会知道这条规则存在。
fail closed 让作者撞一次、改一次、从此声明正确，而声明是可被 digest 冻结的。

═══ 与 `excel_materialize._decode_numeric_char_refs` 的关系 ═════════════════

本模块自带数字字符引用还原，**不 import** `excel_materialize` —— 后者是写入侧、位于
instrumentation 下游，反向 import 会成环（`excel_instrumentation` 是 `excel_materialize`
的上游）。两处口径由 :func:`decode_cell_text` 的判据与 `excel_materialize` 的守卫各自锁死；
它们解的是同一个 OOXML 事实（`&#NNNN;` / `&#xHH;`），不是两套业务规则。

🔴 必须解**全部**数字字符引用：H1 权威模板把中文**全部**写成 `&#21512;&#35745;` 形态
（`sharedStrings` 为 0 条）。只解自己关心的那一个（如 `&#8230;`）会让判据在恰好用实体编码
的模板上静默失效 —— 而那批模板恰恰是被 openpyxl 之类工具重写过的，也就是最需要判据的那批。
"""

from __future__ import annotations

import re
import zipfile
from typing import Final, Mapping, Sequence

__all__ = [
    "ASCII_DOT_PLACEHOLDER_CENSUS",
    "ELLIPSIS",
    "FOOTER_MARKERS",
    "MANAGED_LABEL_COLUMN",
    "SHARED_STRINGS_PART",
    "TYPOGRAPHY_CHARS",
    "TypographyRowError",
    "assert_label_column_matches_spec",
    "assert_last_data_row_is_not_typography_placeholder",
    "decode_cell_text",
    "is_ascii_dot_placeholder",
    "is_typography_placeholder",
    "last_business_data_row",
    "read_column_text",
    "read_shared_strings",
    "read_shared_strings_from_entries",
    "shared_strings_from_xml",
    "trailing_typography_rows",
]


#: 水平省略号 U+2026。模板里常见两个连写（`……`），也有写成 `&#8230;&#8230;` 的。
ELLIPSIS: Final[str] = "\u2026"

#: 受管区的**首列**（序号/标签列）。续行省略号恒写在这一列上。
#:
#: 取值 `"A"` 与 `ExcelInstrumentationSpec.managed_range` / `.table_ref` 两个 property
#: 里的 `f"A{first}:..."` 是同一个平台约定（受管矩形恒从 A 列起）。三处必须一致 ——
#: `assert_label_column_matches_spec` 把它与 spec 的 `table_ref` 首列双向锁死，
#: 哪天受管矩形改成从别的列起，本模块会当场打红而不是静默扫错列。
MANAGED_LABEL_COLUMN: Final[str] = "A"

#: 共享串表部件名。
SHARED_STRINGS_PART: Final[str] = "xl/sharedStrings.xml"

#: footer 锚点的三种中文写法。**只用于文档与诊断**，本模块的判据不依赖它 ——
#: 「这一行是不是排版占位」与「它后面是不是合计行」是两件事，混在一起判会让
#: 「省略号行后面恰好不是合计」的模板静默逃过。
FOOTER_MARKERS: Final[tuple[str, ...]] = ("合计", "小计", "总计")

#: 「纯排版」允许出现的字符集。除省略号本身外只放三类无语义符号：
#: 半角句点（`...` 写法）、全角句号（`。。。` 写法）、空格。
#:
#: 🔴 刻意**不含**数字与中文 —— `……1` / `合计……` 都不是纯排版占位，它们要么是业务数据
#: 要么是 footer，误判成占位会让真实业务行被剔出受管区（静默丢数据，比多写一行更贵）。
TYPOGRAPHY_CHARS: Final[frozenset[str]] = frozenset({ELLIPSIS, ".", "\u3002", " "})

#: 连续三个以上**半角点**（`......` 写法）。
#:
#: 🔴 这是一个**已登记但刻意不进门**的形态，见 :data:`ASCII_DOT_PLACEHOLDER_CENSUS`。
_ASCII_DOT_RUN: Final[re.Pattern[str]] = re.compile(r"\.{3,}")

#: 「ASCII 点写法的续行占位行」全库实测清册（2026-09-05，351 份 xlsx / 2722 张 sheet）。
#:
#: 把 :func:`is_typography_placeholder` 的「必须含 U+2026」这一条放宽成「含 U+2026 **或**
#: 含连续 ≥3 个半角点」后，全库变化量实测如下：
#:
#: =========================  ======  ======  ======
#: 指标                        窄判据   宽判据   多出
#: =========================  ======  ======  ======
#: 整格占位格数                   879     905      26
#: 紧跟合计/小计/总计的占位行       182     183       1
#: 涉及模板                        39      40       1
#: =========================  ======  ======  ======
#:
#: 🔴 **多出的那一行只有一处**：`K/K11 资产减值损失.xlsx` 的 `审定表K11-1!A25 = ' ......'`
#: （前导空格 + 6 个半角点）。它在语义上与 `……` 是同一种续行占位，只是写法不同 ——
#: 也就是说 BP-21 那份「170 处」的清册**漏计了这一形态**（口径要求含 U+2026）。
#:
#: ═══ 为什么不把它加进门 ═══════════════════════════════════════════════════
#:
#: 1. **换不到任何发布推进**：K11 没有 per-entry 契约（`DELIVERED_PER_ENTRY_CONTRACTS`
#:    只有 b60 / d2 / g7 / h1），不在任何 entry 的发布路径上。
#: 2. **代价却很大**：K11 是测试主力模板，8 个测试文件调 `instrument_workbook_bytes`
#:    并冻结了 `last_data_row=25` 及其派生的 structure hash / digest。加进门等于宣布这些
#:    冻结声明全部非法，波及 Task 17 / 37 / 38 与 `excel-structural-row-insertion-…`
#:    spec 的既有事实。
#: 3. **四个 pilot 的声明与它无关**：实测末行分别是 `''` / `'12'` / `'5'` / `'14'`，
#:    在窄宽两种判据下都不是占位行 ⇒ 窄判据对今天的发布路径是充分的。
#:
#: ⇒ 处置是**登记 + 锁死计数**而不是静默留洞：守卫
#: `test_excel_typography_rows.py::TestAsciiDotFormIsRegisteredNotSilent` 现算全库并断言
#: 这三个数**逐个相等**。哪天有新模板引入 ASCII 点写法，计数变化会打红，逼一次重新裁决，
#: 而不是让洞悄悄变大。
#:
#: **必须加进门的条件**：K11（或任何用 ASCII 点写法的模板）拿到 per-entry 契约。那时
#: 它就在发布路径上了，代价与收益关系反转。
ASCII_DOT_PLACEHOLDER_CENSUS: Final[Mapping[str, object]] = {
    "measured_at": "2026-09-05",
    "xlsx_scanned": 351,
    "sheets_scanned": 2722,
    "narrow_cells": 879,
    "wide_cells": 905,
    "narrow_rows_before_footer": 182,
    "wide_rows_before_footer": 183,
    "narrow_templates": 39,
    "wide_templates": 40,
    "only_wide_instances": (
        "K/K11 资产减值损失.xlsx::审定表K11-1!A25",
    ),
    "not_gated_because": (
        "K11 无 per-entry 契约（不在发布路径上），而它是 8 个测试文件的主力模板并冻结了 "
        "last_data_row=25 及派生 digest；加进门只打红既有冻结事实、换不到发布推进。"
        "加门条件 = 该模板拿到 per-entry 契约。"
    ),
}


def is_ascii_dot_placeholder(text: str | None) -> bool:
    """ASCII 点写法（`......`）的续行占位判据 —— **只供清册与守卫用，不进门**。

    与 :func:`is_typography_placeholder` 的关系：本函数是它的**超集**（含 U+2026 的一律
    也算）。刻意分成两个函数而不是给一个函数加开关：开关会让「门用哪一档」变成调用点的
    局部决定，而那正是 :data:`ASCII_DOT_PLACEHOLDER_CENSUS` 明确裁决过的全局问题。
    """
    value = "" if text is None else str(text)
    if is_typography_placeholder(value):
        return True
    if not _ASCII_DOT_RUN.search(value):
        return False
    return not (set(value) - TYPOGRAPHY_CHARS)


class TypographyRowError(ValueError):
    """provider 声明的受管行区间末行落在排版占位行上。

    继承 `ValueError` 而不是 `SyncDomainError`：本模块刻意零 `workpaper_sync` 内部依赖
    （它被 `excel_instrumentation` import，而后者是 domain 的上游）。调用方
    :func:`~app.services.workpaper_sync.excel_instrumentation.instrument_workbook_bytes`
    把它翻成 `InstrumentationError` 后再上抛，于是 error_code 仍然唯一。
    """

    error_code = "managed_last_row_is_typography_placeholder"


_CELL_TPL: Final[str] = r'<c\b[^>]*?\br="{col}(\d+)"([^>]*?)(?:/>|>(.*?)</c>)'
_V: Final[re.Pattern[str]] = re.compile(r"<v>(.*?)</v>", re.S)
_T: Final[re.Pattern[str]] = re.compile(r"<t[^>]*>(.*?)</t>", re.S)
_SI: Final[re.Pattern[str]] = re.compile(r"<si\b.*?</si>", re.S)
_NUMREF: Final[re.Pattern[str]] = re.compile(r"&#(x[0-9a-fA-F]+|\d+);")


def decode_cell_text(text: str) -> str:
    """还原全部数字字符引用 + 三个基础 XML 实体，并 strip。

    不用 `html.unescape`：它会把 `&nbsp;` 之类 HTML 专有实体一起换掉，而那些在 XML 里是
    **未定义实体** —— 静默替换会让「文档非法」这一事实消失。
    """

    def _sub(match: re.Match[str]) -> str:
        token = match.group(1)
        try:
            code = int(token[1:], 16) if token[0] in "xX" else int(token)
        except ValueError:  # pragma: no cover - 正则已限定形态
            return match.group(0)
        # 超出 Unicode 范围/非法码位原样保留：静默丢字符比留下引用更难查。
        return chr(code) if 0 < code <= 0x10FFFF else match.group(0)

    decoded = _NUMREF.sub(_sub, text)
    return (
        decoded.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").strip()
    )


def is_typography_placeholder(text: str | None) -> bool:
    """该单元格文本是否为**纯排版省略号**。

    判据两条同时成立：含至少一个 U+2026，且除 :data:`TYPOGRAPHY_CHARS` 外无其它字符。
    空串返回 `False` —— 空行不是排版占位行，它是「还没填的业务行」，两者处置完全不同。
    """
    value = "" if text is None else str(text)
    if ELLIPSIS not in value:
        return False
    return not (set(value) - TYPOGRAPHY_CHARS)


def shared_strings_from_xml(payload: str) -> list[str]:
    """`sharedStrings.xml` 文本 → 按序文本清册。**唯一**解析实现。

    两个入口（:func:`read_shared_strings` 走 zip、instrumentation 走已解出的 entries dict）
    都委派本函数 —— 各自写一份解析必然漂移。
    """
    return ["".join(_T.findall(item)) for item in _SI.findall(payload)]


def read_shared_strings(zf: zipfile.ZipFile) -> list[str]:
    """`xl/sharedStrings.xml` 的按序文本清册；无该部件返回空表。

    返回空表**不是**异常：H1 权威模板实测 `sharedStrings` 为 0 条（中文全部以数字字符
    引用写在 inline `<t>` 里）。把「无共享串表」当失败会让那批模板整体不可扫。
    """
    if SHARED_STRINGS_PART not in zf.namelist():
        return []
    return shared_strings_from_xml(
        zf.read(SHARED_STRINGS_PART).decode("utf-8", "replace")
    )


def read_shared_strings_from_entries(entries: Mapping[str, bytes]) -> list[str]:
    """已解出的 `{part 名: 字节}` → 共享串清册（instrumentation 侧入口）。

    instrumentation 已经把整个 zip 读成 dict 了，再开一次 `ZipFile` 是重复 I/O，
    而且那份新句柄的生命周期管理会污染本就复杂的注入流程。
    """
    payload = entries.get(SHARED_STRINGS_PART)
    if payload is None:
        return []
    return shared_strings_from_xml(payload.decode("utf-8", "replace"))


def assert_label_column_matches_spec(table_ref: str, *, where: str) -> None:
    """把 :data:`MANAGED_LABEL_COLUMN` 与 spec 的 `table_ref` 首列**双向锁死**。

    本模块扫的是「受管区首列」。如果哪天受管矩形不再从 A 列起（`table_ref` 变成
    `B13:...`），而本模块仍扫 A 列，判据就会在一列**与受管区无关**的数据上求值 ——
    那既可能漏判（A 列恰好没有省略号）也可能误判（A 列是别的说明列）。两种都无声。
    """
    head = re.match(r"^([A-Z]+)\d+:", str(table_ref or ""))
    if head is None:
        raise TypographyRowError(
            f"{where}: table_ref {table_ref!r} 形态无法解出首列 —— "
            "排版占位行判据要扫受管区首列，取不到首列时不得按默认值继续"
        )
    if head.group(1) != MANAGED_LABEL_COLUMN:
        raise TypographyRowError(
            f"{where}: 受管区首列实测为 {head.group(1)}，而本模块的 "
            f"MANAGED_LABEL_COLUMN={MANAGED_LABEL_COLUMN} —— 两者不一致时排版占位行判据会"
            "扫一列与受管区无关的数据（既可能漏判也可能误判，且都无声）。"
            "受管矩形起始列若真的变了，请同时更新 MANAGED_LABEL_COLUMN 与本判据"
        )


def read_column_text(
    sheet_xml: str, *, column: str, shared: Sequence[str] = ()
) -> dict[int, str]:
    """单次遍历取某一列全部**非空**格文本，返回 `{行号: 文本}`。

    🔴 单次遍历不是优化偏好，是必要条件：写成「逐行 `re.search` 回查」是 O(n²)，
    全库 2602 张 sheet 实测 15 分钟未出结果；单次遍历 1.4 秒。
    """
    out: dict[int, str] = {}
    pattern = re.compile(_CELL_TPL.format(col=re.escape(column)), re.S)
    for match in pattern.finditer(sheet_xml):
        row, attrs, inner = match.group(1), match.group(2) or "", match.group(3)
        if inner is None:
            continue
        value = _V.search(inner)
        raw = value.group(1) if value else "".join(_T.findall(inner))
        if 't="s"' in attrs and raw.isdigit():
            index = int(raw)
            raw = shared[index] if index < len(shared) else ""
        text = decode_cell_text(raw)
        if text:
            out[int(row)] = text
    return out


def trailing_typography_rows(
    *, first_data_row: int, last_data_row: int, column_text: Mapping[int, str]
) -> tuple[int, ...]:
    """区间末尾**连续**的排版占位行（自底向上），按行号升序返回。

    🔴 只认**尾部连续**的，不是「区间内任意占位行」。理由是语义：续行省略号的位置在数据区
    末尾；出现在中间的省略号格是业务行里的一个省略号取值（例如某个说明列写了 `……`），
    剔掉它会把真实业务行挖空。判「尾部连续」使剔除动作等价于「把区间上界往回收」，
    这是唯一不改变区间连续性的处置。
    """
    if last_data_row < first_data_row:
        return ()
    tail: list[int] = []
    row = last_data_row
    while row >= first_data_row and is_typography_placeholder(column_text.get(row)):
        tail.append(row)
        row -= 1
    return tuple(sorted(tail))


def last_business_data_row(
    *, first_data_row: int, last_data_row: int, column_text: Mapping[int, str]
) -> int:
    """剔除尾部排版占位行后的真实末行。

    全部行都是占位行时返回 `first_data_row - 1`（空区间）—— 调用方必须把它当**错误**处理，
    本函数不代它抛：`trailing_typography_rows` 的结果与本函数的返回值是同一个事实的两种
    形态，让调用方按自己的语境选诊断措辞。
    """
    tail = trailing_typography_rows(
        first_data_row=first_data_row,
        last_data_row=last_data_row,
        column_text=column_text,
    )
    return last_data_row - len(tail)


def assert_last_data_row_is_not_typography_placeholder(
    *,
    sheet_xml: str,
    shared: Sequence[str],
    label_column: str,
    first_data_row: int,
    last_data_row: int,
    where: str,
) -> tuple[int, ...]:
    """**instrumentation 期的门**：声明的末行不得落在排版占位行上。

    返回本次实测到的尾部占位行清单（恒为空元组 —— 非空时已抛）。返回值让调用方能区分
    「通过」与「空转」：`label_column` 一个格都没读到时清单当然是空的，那不是通过。

    Args:
        where: 诊断前缀（通常是 `entry_id` + sheet 名），让报错能直接定位到 provider。

    Raises:
        TypographyRowError: 末行是排版占位行，附应声明的 `last_data_row`。
    """
    column_text = read_column_text(sheet_xml, column=label_column, shared=shared)
    if not column_text:
        raise TypographyRowError(
            f"{where}: 标签列 {label_column} 上一个非空格都没读到 —— "
            "「末行不是排版占位行」在空集上恒真，不得据此放行"
            "（模板结构或 label_column 声明有误）"
        )
    tail = trailing_typography_rows(
        first_data_row=first_data_row,
        last_data_row=last_data_row,
        column_text=column_text,
    )
    if not tail:
        return ()
    corrected = last_data_row - len(tail)
    if corrected < first_data_row:
        raise TypographyRowError(
            f"{where}: 声明的受管行区间 {first_data_row}..{last_data_row} **整段**都是排版"
            f"占位行（标签列 {label_column} 逐行为纯省略号）—— 该 sheet 没有业务数据行，"
            "受管区声明本身有误"
        )
    values = {row: column_text.get(row, "") for row in tail}
    raise TypographyRowError(
        f"{where}: 声明的受管行区间末行 {last_data_row} 落在**排版占位行**上"
        f"（标签列 {label_column} 取值 {values}）—— 中文审计模板在数据区末尾放续行省略号，"
        f"它不是业务行。应声明 last_data_row={corrected}"
        f"（剔除尾部 {len(tail)} 行占位行），footer 行保持不变。"
        "把占位行算进受管区会让 materialize 试图按业务字段类型写回 `……`（BP-21）"
    )
