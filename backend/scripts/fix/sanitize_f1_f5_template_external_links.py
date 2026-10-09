# -*- coding: utf-8 -*-
"""净化 F1 预付账款 / F5 营业成本权威模板（过 OOXML `external_relationships` 安全门）。

spec: `f1-sync-coverage-and-first-canary` / `f5-sync-coverage-and-first-canary`
（2026-10-07 首版发布 `--check` 两册被 `ooxml_security_rejected` 挡下后）

范式：照 `sanitize_i_cycle_template_external_links.py`
（`backend/wp_templates/` 运行时只读，模板升级必须显式净化 + `.preclean.bak` + 重算 sha256）

逐册现查（2026-10-07，zip 内逐部件扫描）：

| 册 | 外链部件(含rels) | `[n]` 公式 | `[n]` defined name | 外部 hyperlink | OLE |
|---|---|---|---|---|---|
| F1 预付账款 | 10 | 6 | 12 | 0 | 0 |
| F5 营业成本 | 2 | 0 | 2 | 0 | 0 |

处置（与 I/J/D 系同口径）：
  ① 删 `xl/externalLinks/*` 部件与其 `_rels`；`[Content_Types].xml` 删对应 Override；
     `xl/_rels/workbook.xml.rels` 删对应 Relationship；`xl/workbook.xml` 删 `<externalReferences>`
  ② 含 `[n]` 的 defined name 删除（全部指向已断链外部工作簿）
  ③ 含 `[n]` 的公式格去 `<f>` 保 `<v>` 缓存值（可见内容不变）

用法（仓库根）::

    & .venv/Scripts/python.exe backend/scripts/fix/sanitize_f1_f5_template_external_links.py          # 预演
    & .venv/Scripts/python.exe backend/scripts/fix/sanitize_f1_f5_template_external_links.py --apply  # 写盘 + .bak

判成败：①净化后 OOXML 门 PASS 且 `.preclean.bak` 仍 REJECT ②受管 sheet 逐格 0 diff + merge 不变
③各项计数逐值等于期望。不看退出码。
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
    #: F1：10 个外链部件（5 个 xml + 5 个 rels）、6 个外部公式、12 个外部 defined name
    _Target("F1 预付账款.xlsx", "关联方及交易检查表F1-6", 10, 6, 12, 0, 0),
    #: F5：2 个外链部件（1 个 xml + 1 个 rels）、0 个外部公式、2 个外部 defined name
    _Target("F5 营业成本.xlsx", "重大调整核查表F5-8", 2, 0, 2, 0, 0),
)


def main() -> int:
    apply = "--apply" in sys.argv[1:]
    ok = True
    for t in TARGETS:
        # 覆盖 _TPL_DIR（I 循环内核指向 I 目录，这里要指向 F 目录）
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
