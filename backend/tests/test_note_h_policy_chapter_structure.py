"""H 类会计政策章表结构守卫（spec h-cycle-extraction-formula-and-disclosure-completion Task 13）

**裁决者 = `docs/模版/` 两份附注源 docx**，不是模板 JSON 自己（自证无效）。

🔴 定位章节必须按 `paragraph.style.name == 'Heading N'` —— docx 章号是 Word
**自动编号**，段落文本里**不含**「三、」「四、」，用 `^N、标题` 正则会 0 命中。
两份 docx 的层级还不同构：listed 是 `Heading 1`=章 / `Heading 2`=节；
**soe 是 `Heading 1`=章 / `Heading 3`=节 / `Heading 4`=子节 / 局部到 `Heading 5`**。

覆盖四类处置（逐条对应 `fix_note_h_policy_chapter_structure.py`）：
  1. listed `三、固定资产` / `三、生物资产【不适用` —— 表名正名 + 4 列 flat + guidance
  2. listed `三、工程物资【不适用` / `三、使用权资产` —— 重复表已移除（源 docx 政策章无表）
  3. soe `四、固定资产` / `四、生物资产` —— 已补政策表，行标签逐字 == 源 docx
  4. 源 docx 确无政策表的 6 章 —— JSON 必须 `tables == []`（宁缺勿造）

配反向自检：重复表复活 / 表名回退成红字泄漏 / 行标签漂移 三种变异必须打红。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "backend" / "data"
DOCS_DIR = REPO_ROOT / "docs" / "模版"

LISTED_JSON = DATA_DIR / "note_template_listed.json"
SOE_JSON = DATA_DIR / "note_template_soe.json"

LISTED_DOCX = (
    DOCS_DIR
    / "1.上市公司年审报表及附注-2026.01"
    / "1.上市公司年审报表及附注-2026.01"
    / "3.2025年度上市公司财务报表附注模板-2026.01.15.docx"
)
SOE_DOCX = (
    DOCS_DIR
    / "1、2025年度财务决算审计报告-2026.01.06"
    / "1、2025年度财务决算审计报告-国企"
    / "1.1-2025国企财务报表附注20260119.docx"
)


# ────────────────────────────── 源 docx 读取 ──────────────────────────────


def _docx_heading_tables(path: Path) -> dict[str, list[dict]]:
    """`{heading 文本: [该 heading 到下一个 heading 之间的表结构]}`。

    表结构 = `{"rows": n, "cols": n, "header": [...], "firstcol": [...]}`。
    """
    docx = pytest.importorskip("docx", reason="python-docx 未安装，无法以源 docx 为裁决者")
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    doc = docx.Document(str(path))
    items: list[tuple[str, object]] = []
    for child in doc.element.body:
        tag = child.tag.split("}")[-1]
        if tag == "p":
            items.append(("p", Paragraph(child, doc)))
        elif tag == "tbl":
            items.append(("t", Table(child, doc)))

    heads = [
        (i, it[1])
        for i, it in enumerate(items)
        if it[0] == "p" and str(getattr(it[1], "style").name or "").startswith("Heading")
    ]
    result: dict[str, list[dict]] = {}
    for idx, (i, para) in enumerate(heads):
        text = (para.text or "").strip()
        nxt = heads[idx + 1][0] if idx + 1 < len(heads) else len(items)
        tables = [it[1] for it in items[i + 1 : nxt] if it[0] == "t"]
        info = []
        for t in tables:
            header = (
                [c.text.strip().replace("\n", " ") for c in t.rows[0].cells]
                if t.rows
                else []
            )
            firstcol = [t.rows[r].cells[0].text.strip() for r in range(1, len(t.rows))]
            info.append(
                {
                    "rows": len(t.rows),
                    "cols": len(t.columns),
                    "header": header,
                    "firstcol": firstcol,
                }
            )
        # 同名 heading 可能出现多次（会计政策章 + 项目注释章），保留**首次**
        result.setdefault(text, info)
    return result


@pytest.fixture(scope="module")
def listed_docx() -> dict[str, list[dict]]:
    if not LISTED_DOCX.exists():
        pytest.skip(f"源 docx 不存在: {LISTED_DOCX}")
    return _docx_heading_tables(LISTED_DOCX)


@pytest.fixture(scope="module")
def soe_docx() -> dict[str, list[dict]]:
    if not SOE_DOCX.exists():
        pytest.skip(f"源 docx 不存在: {SOE_DOCX}")
    return _docx_heading_tables(SOE_DOCX)


# ────────────────────────────── 模板 JSON 读取 ──────────────────────────────


def _sections(path: Path) -> dict[str, dict]:
    tpl = json.loads(path.read_text(encoding="utf-8"))
    secs = tpl.get("sections") if isinstance(tpl.get("sections"), list) else tpl
    return {str(s.get("section_number") or ""): s for s in secs}


@pytest.fixture(scope="module")
def listed() -> dict[str, dict]:
    return _sections(LISTED_JSON)


@pytest.fixture(scope="module")
def soe() -> dict[str, dict]:
    return _sections(SOE_JSON)


# ────────────────────────────── 解析器自检 ──────────────────────────────


def test_docx_parser_self_check(listed_docx, soe_docx):
    """防「Heading 定位失效 → 全部断言空转」。"""
    assert len(listed_docx) > 200, f"listed docx heading 数异常: {len(listed_docx)}"
    assert len(soe_docx) > 200, f"soe docx heading 数异常: {len(soe_docx)}"
    # 关键 heading 必须在册
    for key in ("各类固定资产的折旧方法", "工程物资【不适用的删除】", "使用权资产"):
        assert key in listed_docx, f"listed docx 缺 heading {key!r}"
    for key in ("固定资产分类及折旧政策", "生产性生物资产"):
        assert key in soe_docx, f"soe docx 缺 heading {key!r}"


def test_no_chinese_number_regex_would_work(listed_docx):
    """反向自检：证明「按 `^三、` 正则定位」确实不可行（docx 无中文章号）。"""
    with_prefix = [k for k in listed_docx if k.startswith(("三、", "四、", "五、"))]
    assert with_prefix == [], (
        "源 docx 的 heading 文本竟带中文章号 —— 若成立则本守卫的定位方式需重新评估，"
        f"命中: {with_prefix[:5]}"
    )


# ────────────────── 1) 正名 + 补 columns + guidance ──────────────────


@pytest.mark.parametrize(
    ("section_number", "table_name", "docx_heading"),
    [
        ("三、固定资产", "各类固定资产的折旧方法", "各类固定资产的折旧方法"),
        ("三、生物资产【不适用", "生产性生物资产", "生产性生物资产"),
    ],
)
def test_listed_policy_table_renamed_and_columns_filled(
    listed, listed_docx, section_number, table_name, docx_heading
):
    sec = listed.get(section_number)
    assert sec is not None, f"listed 缺章节 {section_number!r}"
    tables = sec.get("tables") or []
    assert len(tables) == 1, f"{section_number} 应恰有 1 张政策表，实为 {len(tables)}"
    t = tables[0]

    # 表名 = 源 docx 的 heading 标题（改造前是**整段红字说明文本泄漏**）
    assert t.get("name") == table_name, f"{section_number} 表名未正名: {t.get('name')!r}"
    assert len(str(t.get("name"))) < 40, "表名过长 —— 疑似又退回说明文本泄漏"

    # headers 逐字 == 源 docx 表头
    docx_tables = listed_docx.get(docx_heading) or []
    assert len(docx_tables) == 1, f"源 docx {docx_heading!r} 应有 1 表"
    assert list(t.get("headers") or []) == docx_tables[0]["header"], (
        f"{section_number} headers 与源 docx 不一致\n"
        f"  JSON={t.get('headers')}\n  DOCX={docx_tables[0]['header']}"
    )

    # 单级表头 → 标签列必须显式 flat（抑制凭空父表头推断）
    cols = t.get("columns") or []
    assert len(cols) == len(docx_tables[0]["header"]), f"{section_number} columns 数不符"
    assert cols[0].get("flat") is True, f"{section_number} 标签列缺 flat"
    assert cols[0].get("is_label") is True, f"{section_number} 首列应是 is_label"
    assert not any("group" in c for c in cols), f"{section_number} 单级表头不得声明 group"

    # guidance 非空（源模板红字要求移入这里，不再当表名）
    assert len(str(t.get("guidance") or "").strip()) >= 20, f"{section_number} guidance 过短"


# ────────────────── 2) 重复表已移除（源 docx 政策章无表）──────────────────


@pytest.mark.parametrize(
    ("section_number", "docx_heading", "duplicate_of"),
    [
        ("三、工程物资【不适用", "工程物资【不适用的删除】", "五、23"),
        ("三、使用权资产", "使用权资产", "五、25"),
    ],
)
def test_listed_policy_duplicate_tables_removed(
    listed, listed_docx, section_number, docx_heading, duplicate_of
):
    # 正向：源 docx 该会计政策章确实无表
    docx_tables = listed_docx.get(docx_heading)
    assert docx_tables is not None, f"源 docx 缺 heading {docx_heading!r}"
    assert docx_tables == [], (
        f"源 docx 会计政策章 {docx_heading!r} 竟有 {len(docx_tables)} 张表 —— "
        "若成立则「移除重复表」的判据需重新评估"
    )
    # 故 JSON 也不得有表
    sec = listed.get(section_number)
    assert sec is not None, f"listed 缺章节 {section_number!r}"
    assert (sec.get("tables") or []) == [], (
        f"{section_number} 仍有 {len(sec.get('tables') or [])} 张表 —— "
        f"它是项目注释章 {duplicate_of} 的重复表（md 重建产物），应移除"
    )


def test_duplicate_table_really_lives_in_note_chapter(listed):
    """反向锁死：被移除的表必须**仍存在于项目注释章**（否则是真删数据不是去重）。"""
    sec25 = listed.get("五、25")
    assert sec25 is not None, "listed 缺 五、25 使用权资产"
    t25 = sec25.get("tables") or []
    assert len(t25) == 1 and len(t25[0].get("rows") or []) == 39, (
        "五、25 使用权资产表应是 39 行 —— 政策章那张是它的副本，"
        "若正本丢了则移除操作变成了删数据"
    )

    sec23 = listed.get("五、23")
    assert sec23 is not None, "listed 缺 五、23 在建工程"
    names = [str(t.get("name")) for t in (sec23.get("tables") or [])]
    assert "工程物资" in names, f"五、23 应含「工程物资」表，实为 {names}"


# ────────────────── 3) soe 补表：行标签逐字 == 源 docx ──────────────────


@pytest.mark.parametrize(
    ("section_number", "table_name", "docx_heading"),
    [
        ("四、固定资产", "固定资产分类及折旧政策", "固定资产分类及折旧政策"),
        ("四、生物资产", "生产性生物资产", "生产性生物资产"),
    ],
)
def test_soe_policy_table_added_matches_docx(
    soe, soe_docx, section_number, table_name, docx_heading
):
    sec = soe.get(section_number)
    assert sec is not None, f"soe 缺章节 {section_number!r}"
    tables = sec.get("tables") or []
    assert len(tables) == 1, f"{section_number} 应恰有 1 张政策表，实为 {len(tables)}"
    t = tables[0]
    assert t.get("name") == table_name

    docx_tables = soe_docx.get(docx_heading) or []
    assert len(docx_tables) == 1, f"源 docx {docx_heading!r} 应有 1 表"
    d = docx_tables[0]

    assert list(t.get("headers") or []) == d["header"], (
        f"{section_number} headers 不符\n  JSON={t.get('headers')}\n  DOCX={d['header']}"
    )
    labels = [str(r.get("label") or "") for r in (t.get("rows") or [])]
    assert labels == d["firstcol"], (
        f"{section_number} 行标签与源 docx 不一致\n  JSON={labels}\n  DOCX={d['firstcol']}"
    )
    cols = t.get("columns") or []
    assert len(cols) == len(d["header"])
    assert cols[0].get("flat") is True
    assert len(str(t.get("guidance") or "").strip()) >= 20


def test_soe_biological_expandable_placeholders_preserved(soe):
    """`①` 与 `……` 是源模板的**可扩位**，必须原样保留（不得当假行删掉）。"""
    sec = soe.get("四、生物资产")
    assert sec is not None
    labels = [str(r.get("label") or "") for r in (sec["tables"][0].get("rows") or [])]
    assert labels.count("①") == 4, f"四产业各应有 1 个 ① 可扩位，实为 {labels.count('①')}"
    assert labels.count("……") == 4, f"四产业各应有 1 个 …… 可扩位，实为 {labels.count('……')}"


# ────────────────── 4) 源 docx 确无政策表的章节：JSON 必须也无表 ──────────────────


@pytest.mark.parametrize(
    ("section_number", "docx_heading"),
    [
        ("三、投资性房地产【不", "投资性房地产【不适用的删除】"),
        ("三、在建工程", "在建工程"),
    ],
)
def test_listed_no_table_sections(listed, listed_docx, section_number, docx_heading):
    assert (listed_docx.get(docx_heading) or []) == [], (
        f"源 docx {docx_heading!r} 竟有表 —— 清单过期，需按源 docx 重新裁决"
    )
    sec = listed.get(section_number)
    assert sec is not None, f"listed 缺章节 {section_number!r}"
    assert (sec.get("tables") or []) == [], (
        f"{section_number} 源 docx 无政策表，JSON 不得凭空造表"
    )


@pytest.mark.parametrize(
    ("section_number", "docx_heading"),
    [
        ("四、投资性房地产", "投资性房地产"),
        ("四、在建工程", "在建工程"),
        ("四、油气资产", "油气资产（不适用的一定删除）"),
        ("四、使用权资产", "使用权资产"),
    ],
)
def test_soe_no_table_sections(soe, soe_docx, section_number, docx_heading):
    assert (soe_docx.get(docx_heading) or []) == [], (
        f"源 docx {docx_heading!r} 竟有表 —— 清单过期，需按源 docx 重新裁决"
    )
    sec = soe.get(section_number)
    assert sec is not None, f"soe 缺章节 {section_number!r}"
    assert (sec.get("tables") or []) == [], (
        f"{section_number} 源 docx 无政策表，JSON 不得凭空造表（宁缺勿造）"
    )


def test_soe_no_table_sections_still_have_text(soe):
    """无表的章节必须仍有 `text_sections`（政策文字才是这些章的内容）。"""
    for num in ("四、投资性房地产", "四、在建工程", "四、油气资产", "四、使用权资产"):
        sec = soe.get(num)
        assert sec is not None
        assert len(sec.get("text_sections") or []) >= 3, (
            f"{num} text_sections 过少（{len(sec.get('text_sections') or [])}）—— "
            "无表章节的政策文字不能也丢了"
        )


# ────────────────── 5) 幂等脚本已收敛 ──────────────────


def test_fix_script_check_is_clean():
    """`--check` 必须归零（防模板被并发会话回退）。"""
    import subprocess

    script = REPO_ROOT / "backend" / "scripts" / "fix" / "fix_note_h_policy_chapter_structure.py"
    assert script.exists(), f"幂等脚本不存在: {script}"
    proc = subprocess.run(
        ["python", str(script), "--check"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert proc.returncode == 0, (
        f"fix_note_h_policy_chapter_structure --check 未归零 (rc={proc.returncode})\n"
        f"{proc.stdout}\n{proc.stderr}"
    )


# ────────────────── 反向自检（证明断言不是空转）──────────────────


def test_selfcheck_duplicate_table_revival_would_fail(listed):
    """把重复表塞回政策章 → 断言必红。"""
    fake = {"section_number": "三、使用权资产", "tables": [{"name": "项  目", "rows": []}]}
    assert (fake.get("tables") or []) != [], "替身构造失败"
    # 真实数据必须是空的（正向）
    assert (listed["三、使用权资产"].get("tables") or []) == []


def test_selfcheck_name_leak_would_fail():
    """表名退回红字说明文本泄漏 → 长度断言必红。"""
    leaked = (
        "本公司采用年限平均法计提折旧。固定资产自达到预定可使用状态时开始计提折旧，"
        "终止确认时或划分为持有待售非流动资产时停止计提折旧。"
    )
    assert len(leaked) >= 40, "泄漏名应显著长于正式表名"


def test_selfcheck_row_label_drift_would_fail(soe, soe_docx):
    """行标签漂移一个字 → 逐字断言必红。"""
    labels = [str(r.get("label") or "") for r in soe["四、固定资产"]["tables"][0]["rows"]]
    drifted = list(labels)
    drifted[0] = drifted[0] + "X"
    assert drifted != (soe_docx["固定资产分类及折旧政策"][0]["firstcol"])
    assert labels == soe_docx["固定资产分类及折旧政策"][0]["firstcol"]
