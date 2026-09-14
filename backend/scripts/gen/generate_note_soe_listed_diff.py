"""Generate backend/data/note_soe_listed_diff.json from the SOE/Listed templates.

spec: soe-listed-note-conversion-correctness / Task 1（Requirements 1.1, 1.4）

------------------------------------------------------------------------------
本脚本是**薄壳**：差异计算的唯一真源是
``app.services.note_template_diff.compute_diff_from_templates``
------------------------------------------------------------------------------

改造前它自带一份 ``generate_diff()`` 独立实现（与 service 逐行雷同），属平台
已登记的「未完成的重构 / 双真源」缺陷模式 —— 改 service 的匹配口径不会传导到
落盘 JSON，于是 ``load_diff_data()`` 的「落盘 vs 实时」交叉校验会永久报不一致。
现改为委托，落盘与实时**由构造保证一致**。

另修一个路径缺陷：脚本从 ``backend/scripts/`` 移入 ``backend/scripts/gen/`` 时
``DATA_DIR`` 未跟着改，实际指向不存在的 ``backend/scripts/data`` ⇒ 直接运行必
``FileNotFoundError``（也就是说这个「重生成」入口在移动之后从未成功跑过）。

Usage::

    python backend/scripts/gen/generate_note_soe_listed_diff.py            # 写盘
    python backend/scripts/gen/generate_note_soe_listed_diff.py --check    # 只校验
    python backend/scripts/gen/generate_note_soe_listed_diff.py --dry-run  # 只打印

退出码：0 = 一致/已写盘；2 = ``--check`` 下落盘与实时不一致（需重跑写盘）。

控制台输出一律 ASCII 标记（Windows GBK 控制台下 emoji 会 ``UnicodeEncodeError``
且崩点在写盘之后，会让「已落盘」被误判成失败）。
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

# --- 定位 backend/ 根：用两个哨兵文件向上找，禁写死回退级数 -------------------
_HERE = pathlib.Path(__file__).resolve()


def _find_backend_root(start: pathlib.Path) -> pathlib.Path:
    for cand in [start, *start.parents]:
        if (cand / "data" / "note_template_soe.json").is_file() and (
            cand / "app" / "services" / "note_template_diff.py"
        ).is_file():
            return cand
    raise RuntimeError(f"未能从 {start} 向上定位 backend/ 根（缺哨兵文件）")


BACKEND_ROOT = _find_backend_root(_HERE.parent)
DATA_DIR = BACKEND_ROOT / "data"
SOE_PATH = DATA_DIR / "note_template_soe.json"
LISTED_PATH = DATA_DIR / "note_template_listed.json"
OUTPUT_PATH = DATA_DIR / "note_soe_listed_diff.json"

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.note_template_diff import (  # noqa: E402
    DIFF_BUCKETS,
    compare_diff_payloads,
    compute_diff_from_templates,
)

DESCRIPTION = (
    "SOE vs Listed template section diff — auto-generated from "
    "note_template_{soe,listed}.json via "
    "app.services.note_template_diff.compute_diff_from_templates. "
    "Do not hand-edit; rerun scripts/gen/generate_note_soe_listed_diff.py."
)


def _load_sections(path: pathlib.Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    sections = data.get("sections")
    return sections if isinstance(sections, list) else []


def generate_diff() -> dict:
    """委托 service 计算差异，仅补 ``description`` 元数据。

    ``is_mock`` 由 service 返回 ``False`` —— 本脚本**不得**自己写 ``is_mock``，
    否则又形成第二真源（原实现硬写 ``True``，正是落盘长期自标 mock 的成因）。
    """
    diff = compute_diff_from_templates(
        _load_sections(SOE_PATH),
        _load_sections(LISTED_PATH),
    )
    return {
        "version": diff.get("version", "1.0.0"),
        "is_mock": diff.get("is_mock", False),
        "description": DESCRIPTION,
        **{b: diff.get(b, []) for b in DIFF_BUCKETS},
    }


def _serialize(diff: dict) -> str:
    return json.dumps(diff, ensure_ascii=False, indent=2) + "\n"


def _print_counts(diff: dict, prefix: str = "  ") -> None:
    for bucket in DIFF_BUCKETS:
        print(f"{prefix}{bucket}: {len(diff.get(bucket, []))}")
    print(f"{prefix}is_mock: {diff.get('is_mock')}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="只校验落盘是否与实时一致，不写盘")
    parser.add_argument("--dry-run", action="store_true", help="只打印结果，不写盘")
    args = parser.parse_args(argv)

    diff = generate_diff()

    stored: dict | None = None
    if OUTPUT_PATH.exists():
        try:
            loaded = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                stored = loaded
        except (json.JSONDecodeError, OSError) as exc:
            print(f"[WARN] 落盘 {OUTPUT_PATH.name} 读取失败: {exc}")

    if args.check:
        if stored is None:
            print(f"[ERR] 落盘缺失或不可读: {OUTPUT_PATH}")
            return 2
        cmp = compare_diff_payloads(stored, diff)
        if cmp["consistent"] and stored.get("is_mock") is False:
            print(f"[OK] {OUTPUT_PATH.name} 与实时计算一致，is_mock=false")
            _print_counts(diff)
            return 0
        print(f"[ERR] {OUTPUT_PATH.name} 与实时计算不一致或仍标 is_mock")
        print(f"      is_mock: stored={stored.get('is_mock')} live={diff.get('is_mock')}")
        for bucket, detail in cmp["buckets"].items():
            if detail["only_stored"] or detail["only_live"]:
                print(
                    f"      {bucket}: stored={detail['stored_count']} live={detail['live_count']}"
                    f" only_stored={len(detail['only_stored'])} only_live={len(detail['only_live'])}"
                )
        print("      -> 重跑本脚本（不带 --check）写盘")
        return 2

    if args.dry_run:
        print(f"[DRY-RUN] 不写盘。{OUTPUT_PATH}")
        _print_counts(diff)
        if stored is not None:
            cmp = compare_diff_payloads(stored, diff)
            print(f"  consistent_with_stored: {cmp['consistent']}")
        return 0

    if stored is not None:
        print("[INFO] 重生成前落盘计数:")
        _print_counts(stored, prefix="    ")

    OUTPUT_PATH.write_text(_serialize(diff), encoding="utf-8")
    print(f"[OK] 已写入 {OUTPUT_PATH}")
    _print_counts(diff)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
