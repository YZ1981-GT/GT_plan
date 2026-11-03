"""鉴权清册检查模式的两处判据缺陷（spec note-pull-followup-closure R20 / R21）。

- R20 edit 级影响清单比对键：同一函数里同一种门禁可以有好几处（不同级别 / 条件分支），原先只按 (file, function, form)
  比对 ⇒ 「已提交的产物里有重复的条目键」恒报错、盖住真实差异（HEAD 实测 6 组）。比对改用 (… , level, ordinal)。
- R21 换行：生成器恒写 LF，index 也是 LF，Windows（autocrlf）检出是 CRLF；检查模式原来比原始字节 ⇒ 干净检出恒红。
"""
from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

GEN = Path(__file__).resolve().parents[1] / "scripts" / "gen"


def _load(name: str):
    # 与 test_authz_inventory_failures 同一导入方式：脚本里有 dataclass，按文件路径 exec 而不登记 sys.modules 会在
    # dataclass 装饰时取不到模块（AttributeError: 'NoneType' object has no attribute '__dict__'）
    if str(GEN) not in sys.path:
        sys.path.insert(0, str(GEN))
    return importlib.import_module(name)


@pytest.fixture(scope="module")
def impact():
    return _load("gen_edit_level_impact_inventory")


@pytest.fixture(scope="module")
def note_inv():
    return _load("gen_note_write_inventory")


def _point(level: str, ordinal: int, **kw):
    return {"file": "app/routers/x.py", "function": "f", "form": "assert_project_permission",
            "level": level, "ordinal": ordinal, "conditional": False, **kw}


def test_same_gate_twice_in_one_function_is_not_a_duplicate(impact) -> None:
    old = [_point("review", 1), _point("edit", 1, conditional=True)]
    new = [_point("review", 1), _point("edit", 1, conditional=False)]
    lines = impact._drift({"gate_points": old, "direct_comparisons": [], "appendix_non_auth_reads": []},
                          {"gate_points": new, "direct_comparisons": [], "appendix_non_auth_reads": []})
    assert not any("重复的条目键" in line for line in lines), lines
    assert any("conditional" in line for line in lines), "真实差异（第二处变成无条件）要能报出来"


def test_build_rejects_truly_duplicated_points(impact) -> None:
    assert impact._duplicate_point_keys([_point("edit", 1), _point("edit", 2)]) == []
    assert impact._duplicate_point_keys([_point("edit", 1), _point("edit", 1)]) == [
        ("app/routers/x.py", "f", "assert_project_permission", "edit", 1)]


def test_old_key_would_have_collided(impact) -> None:
    """反向：只按排序键（file, function, form）比对时，上面两处就是重复键（判据不空转）。"""
    from authz_inventory import render

    with pytest.raises(render.RenderError, match="重复的条目键"):
        render.diff_entries([_point("review", 1), _point("edit", 1)], [], impact._POINT_SORT)


def test_newline_normalization() -> None:
    from authz_inventory import render

    assert render.normalize_newlines(b'{\r\n  "a": 1\r\n}\r\n') == b'{\n  "a": 1\n}\n'
    assert render.normalize_newlines(b"x\ny") == b"x\ny"


@pytest.mark.parametrize("which", ["impact", "note_inv"])
def test_check_mode_accepts_crlf_checkout(which, request, tmp_path, capsys) -> None:
    mod = request.getfixturevalue(which)
    payload = {"schema": "t", "gate_points": [], "direct_comparisons": [], "appendix_non_auth_reads": [],
               "endpoints": [], "counts": {}, "scan": {}}
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    built = SimpleNamespace(payload=payload, text=text, summary=())
    out = tmp_path / "product.json"
    out.write_bytes(text.replace("\n", "\r\n").encode("utf-8"))
    assert mod.check_against(out, built) == mod.EXIT_OK, capsys.readouterr().err
    out.write_bytes(text.replace('"t"', '"u"').encode("utf-8"))
    assert mod.check_against(out, built) == mod.EXIT_DRIFT, "内容不同仍要判漂移"
