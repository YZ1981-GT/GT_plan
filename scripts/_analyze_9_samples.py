"""深度分析 9 家真实样本的结构特征（sheet / columns / 行数 / 识别率）。用完即删。"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.services.ledger_import.detector import detect_file_from_path
from app.services.ledger_import.identifier import identify


ROOT = Path(__file__).resolve().parent.parent / "数据"

SAMPLES = [
    ("YG36 四川物流", [ROOT / "YG36-重庆医药集团四川物流有限公司2025.xlsx"]),
    ("YG2101 四川医药", [ROOT / "YG2101-重庆医药集团四川医药有限公司2025年-科目余额表+序时账.xlsx"]),
    ("YG4001-30 新健康大药房", [ROOT / "YG4001-30重庆医药集团宜宾医药有限公司新健康大药房临港店-余额表+序时账.xlsx"]),
    ("和平物流", [ROOT / "和平物流25加工账-药品批发.xlsx"]),
    ("安徽骨科", [ROOT / "余额表+序时账-安徽-骨科.xlsx"]),
    ("和平药房（余额+2CSV序时）", list((ROOT / "和平药房").iterdir())),
    ("辽宁卫生（分离2文件）", list((ROOT / "辽宁卫生服务有限公司").iterdir())),
    ("医疗器械（分离2文件）", list((ROOT / "重庆医药集团医疗器械有限公司-医疗设备").iterdir())),
    ("陕西华氏 2024（1余额+12月度）", list((ROOT / "陕西华氏医药有限公司-需加工24和25年的AUD文件/2024").iterdir())),
    ("陕西华氏 2025（1余额+11月度）", list((ROOT / "陕西华氏医药有限公司-需加工24和25年的AUD文件/2025").iterdir())),
]


def _analyze_file(path: Path) -> dict:
    t = time.time()
    try:
        fd = detect_file_from_path(str(path), path.name)
        sheets_info = []
        for sh in fd.sheets:
            sh2 = identify(sh)
            mapped = sum(1 for cm in sh2.column_mappings if cm.standard_field and cm.confidence >= 50)
            total_cols = len(sh2.column_mappings)
            sheets_info.append({
                "sheet": sh2.sheet_name[:15],
                "type": sh2.table_type,
                "conf": sh2.table_type_confidence,
                "rows": sh2.row_count_estimate,
                "map": f"{mapped}/{total_cols}",
            })
        return {
            "size_mb": round(path.stat().st_size / 1e6, 2),
            "sheets": sheets_info,
            "elapsed": round(time.time() - t, 1),
        }
    except Exception as exc:
        return {"size_mb": round(path.stat().st_size / 1e6, 2), "error": str(exc)[:80]}


def main():
    print(f"{'样本名':<30} {'文件':<50} {'MB':<8} {'Sheets / Type / Conf / Rows / Mapping'}")
    print("-" * 150)
    for name, files in SAMPLES:
        # 过滤掉临时文件
        files = [f for f in files if not f.name.startswith("~$")]
        # 文件太大的跳过详细解析（>100MB xlsx）
        total_mb = sum(f.stat().st_size for f in files) / 1e6
        print(f"\n【{name}】  文件数={len(files)}  总大小={total_mb:.1f}MB")
        for f in sorted(files, key=lambda p: p.name):
            size_mb = f.stat().st_size / 1e6
            if size_mb > 100 or f.suffix.lower() == ".csv":
                # 大文件 / CSV 仅记录大小，不做完整解析
                print(f"  └ {f.name[:60]:<62} {size_mb:<6.1f}MB  [大文件/CSV 跳过详细解析]")
                continue
            info = _analyze_file(f)
            if "error" in info:
                print(f"  └ {f.name[:60]:<62} {size_mb:<6.1f}MB  ERROR: {info['error']}")
                continue
            sheets_str = " | ".join([
                f"{s['sheet']}:{s['type']}({s['conf']}%,{s['rows']}行,{s['map']})"
                for s in info["sheets"]
            ])
            print(f"  └ {f.name[:60]:<62} {size_mb:<6.1f}MB  {sheets_str}")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    main()
