"""生成「Word 模板占位符补全清单」—— 交底稿模板编制方填写的可执行清单。

## 为什么需要这份清单（BP-20）

`workpaper_sync_task63_subcode_adjudication.json` 现读：

* `dollar_token_total = 0` —— 9 个 B 子码的权威 DOCX 里 `${token}` 占位符**一个都没有**
* HTML 侧字段全部由 `wp_docx_template_parser` 的 legacy 中文标记正则派生：
  `_LEGACY_PATTERNS` 里 `(r"××", "placeholder_generic", "待填内容")` 是唯一模式
* 字段 id 由 `_dedupe_field_id` 按**出现顺序**编号：`placeholder_generic`、
  `placeholder_generic_2`、…

⇒ 字段身份是**纯位置派生**的。模板中间插一个 `××`，后面全部字段 id 错位，
历史填写数据会串到别的字段上。这就是 `field_identity_admissible = false` 的含义，
也是 per-entry contract 发不出去的根因（BP-20）。

**解除条件只有一条**：模板编制方为每个 `××` 指定稳定的业务字段名，
改写成 `${field_name}` 或 `${field_name:标签}` 形态（`_NEW_PLACEHOLDER_RE` 认这个）。

## 本脚本做什么

用**解析器本身**（`wp_docx_template_parser.parse_template`）抽取，保证清单里的位置与
生产代码实际看到的逐一对应 —— 不手搓正则，避免清单与实现分叉。

对每个占位符输出：现派生 id、位置（段落序号 / 表格坐标）、上下文原文、推断数据类型、
**建议字段名**（供业务方确认或改写），并留两列空白给业务方填「确认字段名」与「业务含义」。

## 用法

    python backend/scripts/gen/generate_word_placeholder_completion_list.py --check
    python backend/scripts/gen/generate_word_placeholder_completion_list.py --apply

`--check` 只比对现算与磁盘是否一致（不写）；`--apply` 原子写入两个产物：

* `docs/operations/word-template-placeholder-completion-list.md` —— 交业务方填的清单
* `backend/data/word_template_placeholder_completion.json` —— 机器可读，业务填回后作落地依据

🔴 本脚本**只读模板、不改任何模板字节**。它是纯报告器。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass, field as dc_field
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
_REPO = _HERE.parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.services import wp_docx_template_parser as PARSER  # noqa: E402

TEMPLATE_ROOT = _BACKEND / "wp_templates"
ADJUDICATION = _BACKEND / "data" / "workpaper_sync_task63_subcode_adjudication.json"
OUT_MD = _REPO / "docs" / "operations" / "word-template-placeholder-completion-list.md"
OUT_JSON = _BACKEND / "data" / "word_template_placeholder_completion.json"

#: 上下文截取的左右字符数。太短业务方看不出这个 `××` 是什么，太长表格会撑爆。
CONTEXT_CHARS = 46


class CompletionListError(RuntimeError):
    """生成失败。error_code 供调用方编程判别。"""

    error_code = "word_placeholder_completion_list_failed"


# ═══════════════════════════════════════════════════════════════════════════
# 1. 建议字段名的推断
# ═══════════════════════════════════════════════════════════════════════════

#: 上下文关键词 → 建议字段名。**只是建议**，最终由业务方确认。
#: 顺序敏感：先匹配到的胜出，故把更具体的放前面。
_NAME_HINTS: tuple[tuple[str, str, str], ...] = (
    # ── 实测上下文命中的几类（优先，放最前）────────────────────────
    ("仲裁委员会", "arbitration_commission", "仲裁委员会名称"),
    ("年度财务报表审计", "fiscal_year_yy", "会计年度（20 之后两位）"),
    ("年度财务报表的期初余额", "fiscal_year_yy", "会计年度（20 之后两位）"),
    ("年度财务报表审计的相关工作底稿", "fiscal_year_yy", "会计年度（20 之后两位）"),
    # ── 通用 ────────────────────────────────────────────────────
    ("前任会计师事务所名称", "predecessor_firm_name", "前任会计师事务所名称"),
    ("被审计单位名称", "audited_entity_name", "被审计单位名称"),
    ("会计师事务所", "firm_name", "会计师事务所名称"),
    ("被审计单位", "audited_entity_name", "被审计单位名称"),
    ("项目组", "engagement_team", "项目组名称或成员"),
    ("联系人", "contact_person", "联系人姓名"),
    ("联系电话", "contact_phone", "联系电话"),
    ("电话", "contact_phone", "联系电话"),
    ("传真", "contact_fax", "传真号码"),
    ("邮箱", "contact_email", "电子邮箱"),
    ("地址", "contact_address", "联系地址"),
    ("签署日", "sign_date", "签署日期"),
    ("报告日", "report_date", "报告日期"),
    ("回复期限", "reply_deadline", "要求回复的截止日期"),
    ("截止日", "deadline", "截止日期"),
    ("年度", "fiscal_year", "会计年度"),
    ("期间", "period", "报告期间"),
    ("金额", "amount", "金额"),
    ("万元", "amount_wan", "金额（万元）"),
    ("比例", "ratio", "比例"),
    ("日期", "date", "日期"),
    ("姓名", "person_name", "姓名"),
    ("职务", "job_title", "职务"),
    ("单位", "entity_name", "单位名称"),
    ("名称", "name", "名称"),
)


#: 签署日期形态：`【20××】年【×】月【×】日`。实测 6 份模板各一处，共 6 个双 ×
#: 命中它，另有 12 个**单** × 落在「月」「日」上而完全未被识别（见 §未识别缺口）。
_SIGN_DATE_RE = re.compile(r"年.{0,4}月.{0,4}日")

#: 孤立的单个 `×`（左右都不是 `×`）。legacy 正则只认 `××`，故这些位置**完全不被识别**。
_SINGLE_X_RE = re.compile(r"(?<!×)×(?!×)")


def suggest_field_name(context: str, data_type: str, seq: int) -> tuple[str, str]:
    """按上下文关键词给一个建议字段名与建议标签。命中不了就给按序号的占位建议。"""
    # 签署日期形态优先于「年度」—— 两者都含「年」，但语义不同
    if _SIGN_DATE_RE.search(context):
        return "sign_date_yy", "签署日期的年份（20 之后两位）"
    for keyword, name, label in _NAME_HINTS:
        if keyword in context:
            return name, label
    if data_type == "date":
        return f"date_{seq}", f"日期{seq}"
    if data_type == "number":
        return f"amount_{seq}", f"金额{seq}"
    return f"field_{seq}", f"待命名字段{seq}"


# ═══════════════════════════════════════════════════════════════════════════
# 2. 抽取
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class Slot:
    """一个待补全的占位符。"""

    seq: int
    derived_field_id: str
    derived_label: str
    data_type: str
    location: str
    location_raw: dict[str, Any]
    context: str
    suggested_name: str
    suggested_label: str


@dataclass
class CarrierReport:
    """一份 docx 载体的抽取结果。"""

    wp_code: str
    relative_path: str
    exists: bool
    sha256: str
    size_bytes: int
    paragraph_count: int
    table_count: int
    dollar_token_count: int
    slots: list[Slot] = dc_field(default_factory=list)
    #: 🔴 孤立的单个 `×` —— legacy 正则只认 `××`（双 ×），单 × **完全不被识别**，
    #: 于是那些填写位在结构化字段里根本不存在。实测全部落在
    #: `【20××】年【×】月【×】日` 的「月」「日」两处。
    unrecognized_single_x: list[str] = dc_field(default_factory=list)
    note: str = ""


def _describe_position(position: dict[str, Any]) -> str:
    """把解析器的 position 字典变成人能读的坐标。"""
    if "paragraph_index" in position:
        return f"段落 #{position['paragraph_index']}"
    keys = ("table_index", "row_index", "col_index")
    if all(k in position for k in keys):
        return (
            f"表格 #{position['table_index']} "
            f"第 {position['row_index'] + 1} 行第 {position['col_index'] + 1} 列"
        )
    return json.dumps(position, ensure_ascii=False)


def _context_around(text: str, marker: str, occurrence: int) -> str:
    """取第 `occurrence` 个 marker 左右各 CONTEXT_CHARS 字符，并把 marker 高亮成 【××】。"""
    start = -1
    for _ in range(occurrence):
        start = text.find(marker, start + 1)
        if start < 0:
            break
    if start < 0:
        return text[: CONTEXT_CHARS * 2].strip()
    left = max(0, start - CONTEXT_CHARS)
    right = min(len(text), start + len(marker) + CONTEXT_CHARS)
    seg = (
        text[left:start]
        + "【"
        + marker
        + "】"
        + text[start + len(marker) : right]
    )
    return ("…" if left > 0 else "") + seg.strip() + ("…" if right < len(text) else "")


def extract_carrier(wp_code: str, relative_path: str) -> CarrierReport:
    """对一份 docx 跑解析器，产出待补全清单。"""
    path = TEMPLATE_ROOT / relative_path.replace("\\", "/")
    if not path.is_file():
        return CarrierReport(
            wp_code=wp_code,
            relative_path=relative_path,
            exists=False,
            sha256="",
            size_bytes=0,
            paragraph_count=0,
            table_count=0,
            dollar_token_count=0,
            note="🔴 权威模板文件不存在 —— 需模板编制方先补齐文件本身",
        )

    blob = path.read_bytes()
    structure = PARSER.parse_template(str(path))
    placeholders = list(structure.placeholders)
    dollar_tokens = [
        p for p in placeholders if not p.field_id.startswith("placeholder_generic")
    ]

    # 建立「同一段/同一格里第几个 ××」的计数，供上下文定位
    seen_per_location: dict[str, int] = {}
    slots: list[Slot] = []
    for seq, ph in enumerate(placeholders, start=1):
        if not ph.field_id.startswith("placeholder_generic"):
            continue  # 已是 ${token} 形态，无需补全
        position = dict(getattr(ph, "position", {}) or {})
        loc_key = json.dumps(position, sort_keys=True)
        seen_per_location[loc_key] = seen_per_location.get(loc_key, 0) + 1
        occurrence = seen_per_location[loc_key]

        source_text = _source_text_at(structure, position)
        context = _context_around(source_text, "××", occurrence)
        data_type = str(getattr(ph, "data_type", "") or "text")
        name, label = suggest_field_name(context, data_type, seq)
        slots.append(
            Slot(
                seq=seq,
                derived_field_id=ph.field_id,
                derived_label=str(getattr(ph, "label", "") or ""),
                data_type=data_type,
                location=_describe_position(position),
                location_raw=position,
                context=context,
                suggested_name=name,
                suggested_label=label,
            )
        )

    # 🔴 扫孤立单 × —— 它们不在 placeholders 里，是"根本没有身份"的填写位
    all_text: list[str] = [str(pa.text or "") for pa in structure.paragraphs]
    for tbl in structure.tables:
        for row in tbl.rows:
            all_text.extend(str(cell or "") for cell in row)
    single_x_lines = [
        ln.strip() for ln in all_text if ln and _SINGLE_X_RE.search(ln)
    ]

    note = ""
    if not placeholders:
        note = "⚠ 解析器现算 0 个占位符 —— 该模板结构化岛为空集，需模板编制方确认是否本就无需填写位"
    return CarrierReport(
        unrecognized_single_x=sorted(set(single_x_lines)),
        wp_code=wp_code,
        relative_path=relative_path,
        exists=True,
        sha256=hashlib.sha256(blob).hexdigest(),
        size_bytes=len(blob),
        paragraph_count=len(structure.paragraphs),
        table_count=len(structure.tables),
        dollar_token_count=len(dollar_tokens),
        slots=slots,
        note=note,
    )


def _source_text_at(structure: Any, position: dict[str, Any]) -> str:
    """按 position 取回原文，供上下文截取。"""
    if "paragraph_index" in position:
        idx = int(position["paragraph_index"])
        paras = list(structure.paragraphs)
        if 0 <= idx < len(paras):
            return str(paras[idx].text or "")
        return ""
    if all(k in position for k in ("table_index", "row_index", "col_index")):
        tables = list(structure.tables)
        ti = int(position["table_index"])
        if 0 <= ti < len(tables):
            rows = list(tables[ti].rows)
            ri, ci = int(position["row_index"]), int(position["col_index"])
            if 0 <= ri < len(rows):
                cells = list(rows[ri])
                if 0 <= ci < len(cells):
                    return str(cells[ci] or "")
    return ""


# ═══════════════════════════════════════════════════════════════════════════
# 3. 渲染
# ═══════════════════════════════════════════════════════════════════════════


def build_reports() -> list[CarrierReport]:
    """从 task63 裁决 JSON 取载体清单，逐份抽取。"""
    if not ADJUDICATION.is_file():
        raise CompletionListError(f"裁决 JSON 不存在：{ADJUDICATION}")
    data = json.loads(ADJUDICATION.read_text(encoding="utf-8"))
    reports: list[CarrierReport] = []
    for entry in data.get("entries") or []:
        wp_code = str(entry.get("wp_code") or "?")
        carriers = entry.get("own_docx_carriers") or []
        if not carriers:
            reports.append(
                CarrierReport(
                    wp_code=wp_code,
                    relative_path="",
                    exists=False,
                    sha256="",
                    size_bytes=0,
                    paragraph_count=0,
                    table_count=0,
                    dollar_token_count=0,
                    note="🔴 该 entry 无自有 docx 载体（裁决为 template_missing）—— 需模板编制方确认是否应有模板",
                )
            )
            continue
        for carrier in carriers:
            rel = carrier if isinstance(carrier, str) else str(carrier.get("relative_path") or "")
            reports.append(extract_carrier(wp_code, rel))
    return reports


def render_json(reports: list[CarrierReport]) -> str:
    payload = {
        "schema_version": "word-placeholder-completion:v1",
        "generated_by": "backend/scripts/gen/generate_word_placeholder_completion_list.py",
        "why": (
            "BP-20：9 个 B 子码的权威 DOCX 里 ${token} 现算共 0 个；字段身份由 "
            "wp_docx_template_parser 的 legacy 正则 `××` + 出现顺序派生 ⇒ 位置一变字段全错位，"
            "per-entry contract 发不出去。解除需模板编制方为每个 ×× 指定稳定字段名。"
        ),
        "legacy_pattern": "××",
        "target_form": "${field_name} 或 ${field_name:标签}",
        "parser_ref": "app/services/wp_docx_template_parser.py::_NEW_PLACEHOLDER_RE",
        "carriers": [
            {
                "wp_code": r.wp_code,
                "relative_path": r.relative_path,
                "exists": r.exists,
                "sha256": r.sha256,
                "size_bytes": r.size_bytes,
                "paragraph_count": r.paragraph_count,
                "table_count": r.table_count,
                "dollar_token_count": r.dollar_token_count,
                "slot_count": len(r.slots),
                "unrecognized_single_x_count": sum(
                    len(_SINGLE_X_RE.findall(ln)) for ln in r.unrecognized_single_x
                ),
                "unrecognized_single_x_lines": r.unrecognized_single_x,
                "note": r.note,
                "slots": [
                    {
                        "seq": s.seq,
                        "derived_field_id": s.derived_field_id,
                        "derived_label": s.derived_label,
                        "data_type": s.data_type,
                        "location": s.location,
                        "location_raw": s.location_raw,
                        "context": s.context,
                        "suggested_name": s.suggested_name,
                        "suggested_label": s.suggested_label,
                        # 业务方填这两个；填回后本 JSON 即落地依据
                        "confirmed_name": None,
                        "confirmed_label": None,
                        "business_meaning": None,
                    }
                    for s in r.slots
                ],
            }
            for r in reports
        ],
    }
    total_slots = sum(len(r.slots) for r in reports)
    payload["stats"] = {
        "carrier_count": len(reports),
        "missing_carrier_count": sum(1 for r in reports if not r.exists),
        "zero_slot_carrier_count": sum(1 for r in reports if r.exists and not r.slots),
        "slot_total": total_slots,
        "dollar_token_total": sum(r.dollar_token_count for r in reports),
        "unrecognized_single_x_total": sum(
            sum(len(_SINGLE_X_RE.findall(ln)) for ln in r.unrecognized_single_x)
            for r in reports
        ),
    }
    return json.dumps(payload, ensure_ascii=False, indent=1) + "\n"


def render_md(reports: list[CarrierReport]) -> str:
    total_slots = sum(len(r.slots) for r in reports)
    missing = [r for r in reports if not r.exists]
    zero_slot = [r for r in reports if r.exists and not r.slots]
    lines: list[str] = []
    A = lines.append

    A("# Word 模板占位符补全清单")
    A("")
    A("> 请**底稿模板编制方 / 业务方**填写最后两列。填完交还工程侧，即可解除 BP-20。")
    A("> 本清单由脚本从权威模板现算生成，勿手改；模板变动后重跑")
    A("> `backend/scripts/gen/generate_word_placeholder_completion_list.py --apply` 即可刷新。")
    A("")

    A("## 为什么需要你填这个")
    A("")
    A("这些 Word 底稿模板里用 `××` 表示「这里要填内容」。程序读到 `××` 时，只能按**出现顺序**")
    A("给它编号：第一个叫 `placeholder_generic`、第二个叫 `placeholder_generic_2`、依此类推。")
    A("")
    A("问题在于：**这个编号不稳定**。一旦有人在模板中间加一个 `××`，它后面所有 `××` 的编号")
    A("全部后移一位 —— 审计师之前填在「第 3 个空」的内容，会串到「第 4 个空」上去。已经归档的")
    A("底稿数据会指向错误的字段。")
    A("")
    A("所以在线填写与双向回写**无法启用**：程序不敢把数据存进一个随时会改名的字段里。")
    A("")
    A("**解决办法**：给每个 `××` 起一个**固定的名字**，把模板里的 `××` 改写成")
    A("`${名字}` 或 `${名字:显示标签}`。名字定了就永不改动，加减别的空也不影响它。")
    A("")
    A("举例：")
    A("")
    A("```")
    A("改前： 【前任会计师事务所名称】：××")
    A("改后： 【前任会计师事务所名称】：${predecessor_firm_name:前任会计师事务所名称}")
    A("```")
    A("")
    A("**你要做的**：看每一行的「上下文原文」，判断那个 `××` 实际要填什么，")
    A("在「确认字段名」列填一个英文名（小写字母 + 下划线），在「业务含义」列写一句中文说明。")
    A("「建议字段名」列是程序按上下文关键词猜的，**仅供参考**，不对请直接改。")
    A("")

    A("## 汇总")
    A("")
    A(f"- 待补全载体 **{len(reports)}** 份（其中缺文件 {len(missing)} 份、解析出 0 个空的 {len(zero_slot)} 份）")
    A(f"- 待补全占位符合计 **{total_slots}** 个")
    A(f"- 现有规范 `${{token}}` 占位符 **{sum(r.dollar_token_count for r in reports)}** 个")
    A("")
    A("| wp_code | 载体 | 段落 | 表格 | 待补全 | 状态 |")
    A("|---|---|---:|---:|---:|---|")
    for r in reports:
        name = Path(r.relative_path).name if r.relative_path else "（无载体）"
        state = "🔴 缺文件" if not r.exists else ("⚠ 0 个空" if not r.slots else "待填")
        A(
            f"| `{r.wp_code}` | {name[:46]} | {r.paragraph_count} | {r.table_count} "
            f"| {len(r.slots)} | {state} |"
        )
    A("")

    if missing:
        A("## 需先补齐文件本身")
        A("")
        for r in missing:
            A(f"- **`{r.wp_code}`** —— {r.note}")
            if r.relative_path:
                A(f"  - 期望路径：`backend/wp_templates/{r.relative_path}`")
        A("")

    if zero_slot:
        A("## 解析出 0 个填写位 —— 请确认是否本就无需填写")
        A("")
        for r in zero_slot:
            A(f"- **`{r.wp_code}`** `{Path(r.relative_path).name}`")
            A(f"  - {r.note}")
        A("")

    single_x_total = sum(
        sum(len(_SINGLE_X_RE.findall(ln)) for ln in r.unrecognized_single_x)
        for r in reports
    )
    if single_x_total:
        A("## 🔴 另一类问题：单个 `×` 的填写位**根本没被识别**")
        A("")
        A("上面说的是「字段编号不稳定」。还有一类更硬的问题：")
        A("")
        A("程序识别填写位的规则只认**两个连着的** `××`。模板里那些用**单个** `×` 表示的填写位，")
        A("程序完全看不见 —— 不是编号不稳，是压根没有这个字段。")
        A("")
        A(f"实测：双 `××` 被识别为 **{total_slots}** 个填写位；单个 `×` 未被识别的有 **{single_x_total}** 个。")
        A("")
        A("全部集中在签署日期上：")
        A("")
        A("```")
        A("【20××】年【×】月【×】日")
        A("     ↑↑        ↑     ↑")
        A("   被识别    看不见  看不见")
        A("```")
        A("")
        A("后果：双向回写启用后，审计师能在线填年份，但**月和日永远填不了**、也存不下。")
        A("")
        A("**你要做的**：这三处（年、月、日）一并改成规范形态，例如：")
        A("")
        A("```")
        A("改前： 【20××】年【×】月【×】日")
        A("改后： ${sign_date:签署日期}")
        A("```")
        A("")
        A("整个日期用**一个**日期字段即可（程序会按日期控件渲染），不必拆成年/月/日三个。")
        A("若业务上确实要拆，请在下表备注里说明。")
        A("")
        A("| wp_code | 载体 | 未识别单 `×` 个数 | 原文 |")
        A("|---|---|---:|---|")
        for r in reports:
            if not r.unrecognized_single_x:
                continue
            n = sum(len(_SINGLE_X_RE.findall(ln)) for ln in r.unrecognized_single_x)
            samples = " / ".join(ln.replace("|", "\\|") for ln in r.unrecognized_single_x[:3])
            A(f"| `{r.wp_code}` | {Path(r.relative_path).name[:38]} | {n} | {samples[:70]} |")
        A("")

    A("## 逐份补全表")
    A("")
    for r in reports:
        if not r.exists or not r.slots:
            continue
        A(f"### `{r.wp_code}` —— {Path(r.relative_path).name}")
        A("")
        A(f"- 路径：`backend/wp_templates/{r.relative_path}`")
        A(f"- sha256：`{r.sha256[:16]}` · {r.size_bytes:,} 字节 · 段落 {r.paragraph_count} · 表格 {r.table_count}")
        A(f"- 待补全 **{len(r.slots)}** 个")
        A("")
        A("| # | 现派生 id | 位置 | 上下文原文（`【××】` 是待填处） | 类型 | 建议字段名 | **确认字段名** | **业务含义** |")
        A("|---:|---|---|---|---|---|---|---|")
        for s in r.slots:
            ctx = s.context.replace("|", "\\|")
            A(
                f"| {s.seq} | `{s.derived_field_id}` | {s.location} | {ctx} | {s.data_type} "
                f"| `{s.suggested_name}` |  |  |"
            )
        A("")

    A("## 填写规范")
    A("")
    A("- **字段名**：小写英文字母、数字、下划线；首字符必须是字母或下划线")
    A("  （程序的校验正则是 `[a-zA-Z_][a-zA-Z0-9_]*`）")
    A("- **同一份模板内字段名不得重复**；不同模板之间可以重复（各自独立命名空间）")
    A("- 同一个业务含义在多份模板里出现时，**建议用同一个名字**（如「前任会计师事务所名称」")
    A("  统一叫 `predecessor_firm_name`），便于日后跨底稿取数")
    A("- **字段名一旦定下不要再改** —— 改名等于换字段，历史填写数据会失联")
    A("- 「业务含义」写一句话即可，会作为在线填写时的输入提示展示给审计师")
    A("")

    A("## 填完之后（工程侧动作，无需业务方操作）")
    A("")
    A("1. 工程侧按本表把模板里的 `××` 改写成 `${字段名:标签}`")
    A("   —— 🔴 改的是**模板副本**，不是运行时权威目录（`backend/wp_templates/` 运行时只读）")
    A('2. 重跑本脚本 --check，确认 dollar_token_total 从 0 变为待补全总数、slot_total 归零')

    A("3. 重跑 `generate_workpaper_task63_subcode_adjudication.py`，")
    A("   确认 `field_identity_admissible` 由 `false` 转 `true`、BP-20 可解除")
    A("4. 之后 per-entry contract 才能发布，Word 域的双向回写才谈得上启用")
    A("")

    A("## 变更记录")
    A("")
    A("| 日期 | 变更 | 人 |")
    A("|---|---|---|")
    A("| 待填 | 由脚本首次生成 | 工程侧 |")
    A("")
    return "\n".join(lines) + "\n"


# ═══════════════════════════════════════════════════════════════════════════
# 4. CLI
# ═══════════════════════════════════════════════════════════════════════════


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="与磁盘比对（不写）")
    mode.add_argument("--apply", action="store_true", help="原子写入 md 与 json")
    args = parser.parse_args(argv)

    reports = build_reports()
    md, js = render_md(reports), render_json(reports)

    total = sum(len(r.slots) for r in reports)
    missing = sum(1 for r in reports if not r.exists)
    zero = sum(1 for r in reports if r.exists and not r.slots)
    print(
        f"[SOURCE] 载体 {len(reports)} 份（缺文件 {missing} / 0 个空 {zero}）"
        f" · 待补全占位符 {total} 个"
        f" · 现有 ${{token}} {sum(r.dollar_token_count for r in reports)} 个"
    )
    for r in reports:
        flag = "缺文件" if not r.exists else ("0 个空" if not r.slots else f"{len(r.slots)} 个空")
        print(f"[SOURCE]   {r.wp_code:10s} {flag:10s} {Path(r.relative_path).name[:52]}")

    if args.check:
        stale: list[str] = []
        for path, text in ((OUT_MD, md), (OUT_JSON, js)):
            if not path.is_file():
                stale.append(f"{path.relative_to(_REPO).as_posix()}（不存在）")
            elif path.read_text(encoding="utf-8") != text:
                stale.append(path.relative_to(_REPO).as_posix())
        if stale:
            print(f"[FAIL] 与现算不一致：{stale}")
            return 1
        print("[OK] 两个产物与现算逐字一致")
        return 0

    for path, text in ((OUT_MD, md), (OUT_JSON, js)):
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(text, encoding="utf-8", newline="")
        tmp.replace(path)
        print(f"[WROTE] {path.relative_to(_REPO).as_posix()}  {len(text):,} 字符")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
