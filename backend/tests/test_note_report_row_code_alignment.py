"""附注模板 `report_row_code` 与 `report_config` 编号体系一致性守卫。

134 行陈旧编号（固定资产→BS-014 实为其他流动资产、短期借款→BS-031 实为使用权资产等）
已用 `remap_note_report_row_codes.py --apply` 按**标签反查**重映射（位移量不一致，
统一偏移会出错）。本守卫防止再次漂移。

数据源 = `report_row_code_index.json`（离线快照，由 `--dump-index` 从
`report_config` DB 表物化，CI 无 DB 时用它）。

spec: .kiro/specs/h-cycle-legacy-cleanup-and-platform-hygiene/ R6（Property 4/5）
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
_FIX = _ROOT / "scripts" / "fix" / "remap_note_report_row_codes.py"
_INDEX_PATH = _ROOT / "data" / "report_row_code_index.json"
_PATHS = [
    _ROOT / "data" / "note_template_listed.json",
    _ROOT / "data" / "note_template_soe.json",
]

# 每条须写理由：'ambiguous' = 库内该标签本身对应多个编号；'not_found' = 标签在
# report_config 查不到（如「其他货币资金」是货币资金子分类，不是独立报表行）。
_MANUAL_ALLOWLIST: dict[str, str] = {
    "listed|三、重要会计政策、会|资本公积|BS-052": "ambiguous：BS-079/BS-083 两码同名『资本公积』",
    "listed|五、1|其他货币资金|BS-002": "not_found：『其他货币资金』是货币资金子分类，report_config 无独立行",
    "soe|八、18|其他综合收益|BS-053": "ambiguous：BS-085/BS-115 两码同名『其他综合收益』",
    "soe|八、31|递延所得税负债|BS-067": "ambiguous：BS-067/BS-096 两码同名『递延所得税负债』",
    "soe|八、81|短期借款|BS-031": "ambiguous：BS-041/BS-055 两码同名『短期借款』",
    "soe|八、91|短期借款|BS-031": "ambiguous：BS-041/BS-055 两码同名『短期借款』",
    "soe|八、91|其他应付款|BS-037": "ambiguous：BS-050/BS-075 两码同名『其他应付款』",
    "soe|八、92|短期借款|BS-031": "ambiguous：BS-041/BS-055 两码同名『短期借款』",
    "soe|八、93|存货|BS-008": "ambiguous：BS-010/BS-018 两码同名『存货』",
}


def _load_fix():
    import sys

    spec = importlib.util.spec_from_file_location("_fix_row_code", _FIX)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    # 🔴 `@dataclass` 内部按 `sys.modules[cls.__module__]` 反查模块做类型解析，
    # 未注册进 sys.modules 时该查找返回 None → AttributeError。
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


FIX = _load_fix()


@pytest.fixture(scope="module")
def index() -> dict:
    if not _INDEX_PATH.exists():
        pytest.skip(f"缺 {_INDEX_PATH.name}，先跑 --dump-index（需 DATABASE_URL）")
    return json.loads(_INDEX_PATH.read_text(encoding="utf-8"))


def test_index_not_empty(index: dict) -> None:
    """反向自检：索引确实有内容，否则后续断言全在空转。"""
    assert index["row_count"] > 100
    for family in ("listed", "soe"):
        assert len(index["label_to_codes"][family]) > 50


def test_normalize_label_strips_prefixes() -> None:
    assert FIX.normalize_label("其中：短期借款") == "短期借款"
    assert FIX.normalize_label("减：坏账准备") == "坏账准备"
    assert FIX.normalize_label("△结算备付金") == "结算备付金"
    assert FIX.normalize_label("一、流动资产：") == "流动资产"
    assert FIX.normalize_label(None) == ""


@pytest.mark.parametrize("path", _PATHS, ids=lambda p: p.name)
def test_no_stale_report_row_codes(path: Path, index: dict) -> None:
    """Property 4/5: 全库带 report_row_code 的行，标签唯一解析时必与当前编号一致。"""
    doc = json.loads(path.read_text(encoding="utf-8"))
    variant = "listed" if "listed" in path.name else "soe"
    results = FIX.resolve_doc(doc, variant, index, apply=False)
    stale = [r for r in results if r.reason == "ok"]
    assert not stale, (
        f"{path.name} 残留 {len(stale)} 处陈旧编号：" + " / ".join(str(r) for r in stale[:10])
        + "；请重跑 python backend/scripts/fix/remap_note_report_row_codes.py --apply"
    )


@pytest.mark.parametrize("path", _PATHS, ids=lambda p: p.name)
def test_manual_entries_are_allowlisted(path: Path, index: dict) -> None:
    """`ambiguous`/`not_found` 必须逐条登记在 allowlist 并写明理由。"""
    doc = json.loads(path.read_text(encoding="utf-8"))
    variant = "listed" if "listed" in path.name else "soe"
    results = FIX.resolve_doc(doc, variant, index, apply=False)
    manual = [r for r in results if r.reason in ("ambiguous", "not_found")]
    undeclared = []
    for r in manual:
        raw_label = r.label.split("（现")[0]
        key = f"{r.variant}|{r.section}|{raw_label}|{r.old_code}"
        if key not in _MANUAL_ALLOWLIST:
            undeclared.append(key)
    assert not undeclared, (
        f"以下待人工条目未登记 allowlist：{undeclared}"
    )


def test_allowlist_has_no_stale_entries(index: dict) -> None:
    """allowlist 不得残留已可唯一解析的条目（否则守卫形同虚设）。"""
    all_keys: set[str] = set()
    for path in _PATHS:
        doc = json.loads(path.read_text(encoding="utf-8"))
        variant = "listed" if "listed" in path.name else "soe"
        results = FIX.resolve_doc(doc, variant, index, apply=False)
        for r in results:
            if r.reason in ("ambiguous", "not_found"):
                raw_label = r.label.split("（现")[0]
                all_keys.add(f"{r.variant}|{r.section}|{raw_label}|{r.old_code}")
    stale = sorted(k for k in _MANUAL_ALLOWLIST if k not in all_keys)
    assert not stale, f"以下 allowlist 条目已可解析或已消失，请移出：{stale}"


def test_resolve_doc_does_not_touch_account_codes() -> None:
    """Property 5: 改写只动 report_row_code，其余字段逐字不变。"""
    fixture = {
        "sections": [
            {
                "section_number": "测、1",
                "rows": [
                    {
                        "label": "短期借款",
                        "report_row_code": "BS-031",
                        "account_codes": ["2001"],
                        "unrelated": {"x": 1},
                    }
                ],
            }
        ]
    }
    index = {
        "label_to_codes": {"fixture": {"短期借款": ["BS-041"]}},
        "code_to_labels": {"fixture": {}},
    }
    before = json.dumps(fixture, sort_keys=True)
    results = FIX.resolve_doc(fixture, "fixture", index, apply=True)
    assert len(results) == 1 and results[0].reason == "ok"
    row = fixture["sections"][0]["rows"][0]
    assert row["report_row_code"] == "BS-041"
    assert row["account_codes"] == ["2001"]
    assert row["unrelated"] == {"x": 1}
    assert row["label"] == "短期借款"
    # 除 report_row_code 外没有其它字段被动过
    after_without_code = dict(row)
    after_without_code.pop("report_row_code")
    before_dict = json.loads(before)["sections"][0]["rows"][0]
    before_dict.pop("report_row_code")
    assert after_without_code == before_dict


def test_resolve_doc_ambiguous_and_not_found_unchanged() -> None:
    """反向自检：多义/查不到时原样保留，脚本不猜。"""
    fixture = {
        "sections": [
            {
                "section_number": "测、1",
                "rows": [
                    {"label": "多义行", "report_row_code": "BS-999"},
                    {"label": "查不到", "report_row_code": "BS-888"},
                ],
            }
        ]
    }
    index = {
        "label_to_codes": {
            "fixture": {"多义行": ["BS-001", "BS-002"]},
        },
        "code_to_labels": {"fixture": {}},
    }
    results = FIX.resolve_doc(fixture, "fixture", index, apply=True)
    reasons = {r.reason for r in results}
    assert reasons == {"ambiguous", "not_found"}
    assert fixture["sections"][0]["rows"][0]["report_row_code"] == "BS-999"
    assert fixture["sections"][0]["rows"][1]["report_row_code"] == "BS-888"


def test_check_mode_returns_ok() -> None:
    if not _INDEX_PATH.exists():
        pytest.skip("缺索引快照")
    index = json.loads(_INDEX_PATH.read_text(encoding="utf-8"))
    for path in _PATHS:
        ok, log = FIX.process(path, index, apply=False, check_only=True)
        assert ok, "\n".join(log)
