# -*- coding: utf-8 -*-
"""净化 F2 存货三册权威模板（过 OOXML 安全门）。

spec: `f2-sync-coverage-four-entry-lanes`
（2026-10-07 首版发布 `--check` 三册被 `ooxml_security_rejected` 挡下后）

范式：照 `sanitize_i_cycle_template_external_links.py`

逐册现查（2026-10-07）：

| 册 | 外链部件 | 嵌入 | `[n]` 公式 | `[n]` dn | 外部 hl | OLE |
|---|---|---|---|---|---|---|
| F2-21至F2-26 盘点类 | 0 | 1（Word 97-2003 doc） | 0 | 0 | 0 | 0 |
| F2-47至F2-49 跌价准备 | 14 | 0 | 0 | 7 | 0 | 0 |
| F2-55至F2-58 合同履约 | 8 | 0 | 6 | 5 | 0 | 0 |

用法（仓库根）::

    & .venv/Scripts/python.exe backend/scripts/fix/sanitize_f2_template_external_links.py
    & .venv/Scripts/python.exe backend/scripts/fix/sanitize_f2_template_external_links.py --apply
"""
from __future__ import annotations

import hashlib
import importlib.util
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_SPEC = importlib.util.spec_from_file_location(
    "_sanitize_i_cycle", _HERE / "sanitize_i_cycle_template_external_links.py"
)
assert _SPEC and _SPEC.loader
_I = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _I
_SPEC.loader.exec_module(_I)

_Target = _I._Target
_TPL_DIR = _I._REPO / "backend" / "wp_templates" / "F"

TARGETS: tuple[_Target, ...] = (
    # stocktake: 1 embed (Word doc) + 1 OLE object
    _Target(
        "F2-21至F2-26 存货及跌价准备 - 盘点类（Leap应对措施- 存货监盘）.xlsx",
        "抽盘结果汇总表F2-25", 1, 0, 0, 0, 1,
    ),
    # valuation: 14 ext_link parts + 7 ext defined names
    _Target(
        "F2-47至F2-49 存货及跌价准备 -跌价准备测试（Leap应对措施-会计估计）.xlsx",
        "长库龄 呆滞 超过保质期存货明细表F2-48", 14, 0, 7, 0, 0,
    ),
    # special: 8 ext_link parts + 6 ext formulas + 5 ext defined names
    _Target(
        "F2-55至F2-58 合同履约成本.xlsx",
        "合同履约成本减值准备测算表F2-57", 8, 6, 5, 0, 0,
    ),
)


def main() -> int:
    apply = "--apply" in sys.argv[1:]
    ok = True
    for t in TARGETS:
        path = _TPL_DIR / t.file_name
        bak = path.with_suffix(path.suffix + ".preclean.bak")
        src = bak.read_bytes() if bak.exists() else path.read_bytes()
        out, stats = _I.sanitize_bytes(src)
        b_snap, b_merged = _I._snapshot(src, t.managed_sheet)
        a_snap, a_merged = _I._snapshot(out, t.managed_sheet)
        diffs = [k for k in sorted(set(b_snap) | set(a_snap))
                 if b_snap.get(k) != a_snap.get(k)]
        gate_before, gate_after = _I._gate(src), _I._gate(out)
        expected = {
            "dropped_parts": t.expect_parts,
            "neutralized_formulas": t.expect_formulas,
            "dropped_defined_names": t.expect_defined_names,
            "dropped_hyperlinks": t.expect_hyperlinks,
            "dropped_ole_objects": t.expect_ole_objects,
        }
        print(f"== {t.file_name}")
        print(f"   before sha256={hashlib.sha256(src).hexdigest()} size={len(src)}"
              f" gate={gate_before[1]}")
        print(f"   after  sha256={hashlib.sha256(out).hexdigest()} size={len(out)}"
              f" gate={gate_after[1]}")
        print(f"   stats={stats} expected={expected}")
        print(f"   managed {t.managed_sheet}: cells {len(b_snap)}->{len(a_snap)}"
              f" diffs={diffs[:8]} merged_same={b_merged == a_merged}")
        passed = (
            not gate_before[0]
            and gate_after[0]
            and not diffs
            and b_merged == a_merged
            and stats == expected
        )
        if not passed:
            print("   [FAIL] 判据不满足 —— 不写盘")
            ok = False
            continue
        if apply:
            if not bak.exists():
                import shutil
                shutil.copy2(path, bak)
                print(f"   [apply] 备份门负例 -> {bak.name}")
            if path.read_bytes() != out:
                path.write_bytes(out)
                print("   [apply] 已净化写盘")
            else:
                print("   [apply] 已是净化态（幂等）")
    print("ALL OK" if ok else "SOME FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
