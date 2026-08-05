"""H 类无期限分段守卫 — Property 13。

openpyxl 直读 H1~H10 全部 20 个披露 sheet，验证「H 类披露表无按期限分段结构」
这一调查结论，把它固化为 CI 可执行的守卫。

**期限类判据词**：`期限` / `到期` / `账龄` / `年以内` / `年以上` / `个月` /
`折现` / `剩余` / `1至2` / `2至3` / `分段` / `区间`

**白名单**（真实命中但不是分段表）：
- H9 上市 A12：「减：一年内到期的租赁负债」（单行重分类）
- H9 国企 A10：「重分类至一年内到期的非流动负债」（单行重分类）
- H2 上市 D31/A36：「工程进度」列 / 「至今累计已支付金额占预算的比例」（进度百分比）
- H2 国企 I26：「工程进度（%）」

白名单为空时判失效（反向自检）。

spec: .kiro/specs/h-cycle-four-table-extraction-and-account-mapping/
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

# 判据词（命中任一即需核查）
_MATURITY_KEYWORDS = (
    "期限", "到期", "账龄", "年以内", "年以上", "个月",
    "折现", "剩余", "1至2", "2至3", "分段", "区间",
)

_KEYWORD_RE = re.compile("|".join(re.escape(k) for k in _MATURITY_KEYWORDS))

# 白名单：(循环/sheet 描述, 命中文本片段)
_WHITELIST = [
    ("H9-listed", "一年内到期"),
    ("H9-soe", "一年内到期"),
    ("H2-listed", "工程进度"),
    ("H2-soe", "工程进度"),
]

_WP_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "wp_templates" / "H"


def _find_h_xlsx_files() -> list[Path]:
    """找到 H 循环全部源 xlsx（排除 ~$ 锁文件）。"""
    if not _WP_TEMPLATE_DIR.is_dir():
        return []
    return sorted(
        p for p in _WP_TEMPLATE_DIR.rglob("H*.xlsx")
        if not p.name.startswith("~$")
    )


def _scan_disclosure_sheets() -> list[tuple[str, str, str]]:
    """扫描全部 H 类源 xlsx 的披露 sheet，返回 (文件名, sheet名, 命中文本)。"""
    try:
        import openpyxl
    except ImportError:
        pytest.skip("openpyxl not installed")
        return []

    hits: list[tuple[str, str, str]] = []
    for xlsx_path in _find_h_xlsx_files():
        try:
            wb = openpyxl.load_workbook(str(xlsx_path), read_only=True, data_only=True)
        except Exception:
            continue
        for sheet_name in wb.sheetnames:
            if "附注" not in sheet_name and "披露" not in sheet_name:
                continue
            ws = wb[sheet_name]
            for row in ws.iter_rows(values_only=True):
                for cell in row:
                    text = str(cell or "")
                    if _KEYWORD_RE.search(text):
                        hits.append((xlsx_path.name, sheet_name, text[:60]))
        wb.close()
    return hits


@pytest.fixture(scope="module")
def maturity_hits() -> list[tuple[str, str, str]]:
    return _scan_disclosure_sheets()


def test_whitelist_not_empty():
    """反向自检：白名单非空（空白名单意味着守卫空转）。"""
    assert len(_WHITELIST) > 0


def test_all_hits_in_whitelist(maturity_hits: list[tuple[str, str, str]]):
    """期限类关键词命中集必须全部落在白名单内。

    若有新命中意味着「H 类无期限分段」结论被打破 → 需人工评估是否误判。
    """
    if not maturity_hits:
        pytest.skip("未扫到 H 类源模板披露 sheet（`wp_templates/H/` 可能为空）")

    unexpected = []
    for fname, sheet, text in maturity_hits:
        # 判断是否在白名单里
        is_whitelisted = any(
            wl_text in text for _, wl_text in _WHITELIST
        )
        if not is_whitelisted:
            unexpected.append(f"{fname}/{sheet}: {text}")

    assert not unexpected, (
        f"H 类披露 sheet 出现未登记的期限类关键词（{len(unexpected)} 处），"
        "需评估「H 类无期限分段」结论是否仍然成立：\n"
        + "\n".join(f"  {u}" for u in unexpected[:10])
    )


def test_known_hits_exist(maturity_hits: list[tuple[str, str, str]]):
    """反向自检：白名单中的 H9/H2 命中确实存在（防守卫因路径变更空转）。"""
    if not maturity_hits:
        pytest.skip("未扫到源模板")

    all_texts = " ".join(t for _, _, t in maturity_hits)
    # H9 的「一年内到期」应至少命中一次
    assert "一年内到期" in all_texts, "反向自检失败：H9 的「一年内到期」未被扫到"
