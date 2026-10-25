"""F2 E2E seed 夹具：模板文件与 manifest 契约。

🔴 2026-09-28 修：本文件原先**手抄**了一份 `F2_E2E_WP_CODES` / `F2_WP_TEMPLATE_FILES`
（10 条），而权威源 `scripts/e2e/seed_fix_projects.py` 是 11 条（含检查类 bundle
`F2-29`）⇒ `test_e2e_manifest_json_has_fix_f_and_f2_codes` 恒红。

根因是**双源手抄**，不是产物错：manifest 由 seed 脚本生成，与脚本常量天然一致，
只有测试那份副本过期。故改为**从权威源导入**，同时补一条「清单非空 + 含已知锚点」
的反向断言（防止 import 到空列表后"零检查"静默通过）。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent.parent
if str(_BACKEND) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(_BACKEND))

from scripts.e2e.seed_fix_projects import (  # noqa: E402
    F2_E2E_WP_CODES,
    F2_WP_TEMPLATE_FILES,
)

_TEMPLATES_F = _BACKEND / "wp_templates" / "F"

#: 锚点：这几条是 F2 E2E 的最小骨架（审定明细 / 监盘 / 跌价 / 履约 / IPO 各一）。
#: 只断言"清单非空"不够——import 到别的空 list 也能过；锚点确保拿到的是 F2 清单。
_ANCHOR_CODES = frozenset({"F2-1", "F2-21", "F2-47", "F2-55", "F2-70"})


def test_wp_code_list_is_non_empty_and_has_anchors():
    """反向断言：权威源清单必须非空且含已知锚点（结构性零守卫）。"""
    assert F2_E2E_WP_CODES, "F2_E2E_WP_CODES 为空 —— 权威源被清空或 import 错了对象"
    assert _ANCHOR_CODES <= set(F2_E2E_WP_CODES), sorted(
        _ANCHOR_CODES - set(F2_E2E_WP_CODES)
    )
    assert len(F2_E2E_WP_CODES) == len(set(F2_E2E_WP_CODES)), "清单含重复 wp_code"


def test_every_wp_code_has_template_mapping():
    """每个 E2E wp_code 都必须有模板映射（漏一条 = seed 时静默少回填一本）。"""
    missing = [code for code in F2_E2E_WP_CODES if code not in F2_WP_TEMPLATE_FILES]
    assert missing == [], f"缺模板映射: {missing}"


def test_f2_wp_template_files_exist_on_disk():
    for code in F2_E2E_WP_CODES:
        tpl_name = F2_WP_TEMPLATE_FILES[code]
        tpl_path = _TEMPLATES_F / tpl_name
        assert tpl_path.is_file(), f"缺少 F2 模板: {code} → {tpl_path}"


def test_e2e_manifest_json_has_fix_f_and_f2_codes():
    manifest_path = _BACKEND / "data" / "e2e_fix_projects.json"
    assert manifest_path.is_file(), "请先运行 seed_fix_projects.py --fix"
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert data["f2_e2e_wp_codes"] == F2_E2E_WP_CODES
    assert data["env"]["TEST_PROJECT_ID_FIX_F"]
    fix_f = data["fixtures"]["FIX-F"]
    assert fix_f["ready"] is True
    assert fix_f["missing_wp_codes"] == []
