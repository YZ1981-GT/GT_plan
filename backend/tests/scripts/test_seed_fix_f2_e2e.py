"""F2 E2E seed 夹具：模板文件与 manifest 契约。"""
from __future__ import annotations

import json
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent.parent
_TEMPLATES_F = _BACKEND / "wp_templates" / "F"

F2_E2E_WP_CODES = [
    "F2-1",
    "F2-21", "F2-22", "F2-23", "F2-24", "F2-25", "F2-26",
    "F2-47",
    "F2-55",
    "F2-70",
]

F2_WP_TEMPLATE_FILES: dict[str, str] = {
    "F2-1": "F2-1至F2-14 存货及跌价准备-审定明细表类（Leap-常规程序）.xlsx",
    "F2-21": "F2-21至F2-26 存货及跌价准备 - 盘点类（Leap应对措施- 存货监盘）.xlsx",
    "F2-22": "F2-21至F2-26 存货及跌价准备 - 盘点类（Leap应对措施- 存货监盘）.xlsx",
    "F2-23": "F2-21至F2-26 存货及跌价准备 - 盘点类（Leap应对措施- 存货监盘）.xlsx",
    "F2-24": "F2-21至F2-26 存货及跌价准备 - 盘点类（Leap应对措施- 存货监盘）.xlsx",
    "F2-25": "F2-21至F2-26 存货及跌价准备 - 盘点类（Leap应对措施- 存货监盘）.xlsx",
    "F2-26": "F2-21至F2-26 存货及跌价准备 - 盘点类（Leap应对措施- 存货监盘）.xlsx",
    "F2-47": "F2-47至F2-49 存货及跌价准备 -跌价准备测试（Leap应对措施-会计估计）.xlsx",
    "F2-55": "F2-55至F2-58 合同履约成本.xlsx",
    "F2-70": "F2-61至F2-72 存货及跌价准备-IPO 上市 新三板 重组 舞弊应对.xlsx",
}


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
