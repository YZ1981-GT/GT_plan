#!/usr/bin/env python
"""生成「附注章节 ↔ 底稿披露 sheet」同步注册表（附注联动复盘 P0-1 看板真源）。

背景
----
底稿→附注结构化推送的权威映射散落在前端 ``*NoteSectionMap.ts``（每科目一份，
``X_NOTE_SECTION = { listed: '五、N', soe: '八、N' }`` + 披露 sheet 真实 tab 名）。
后端做「披露同步就绪度看板」需要同一份映射，但不能再手工维护第二份（会漂移），
也不能用陈旧的 ``note_wp_mapping_service.DEFAULT_WP_MAPPING``（其编号仍是老体系：
D1→五、2 / D2→五、3，与权威 五、4 / 五、5 不符）。

故本脚本从前端唯一真源**生成** ``backend/data/note_workpaper_sync_registry.json``，
committed 供后端只读消费；前端 map 变更后重跑本脚本即可。

用法
----
    python backend/scripts/gen_note_wp_sync_registry.py            # 打印摘要
    python backend/scripts/gen_note_wp_sync_registry.py --write    # 写入 JSON
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
FRONTEND_SRC = REPO_ROOT / "audit-platform" / "frontend" / "src"
OUT_PATH = Path(__file__).resolve().parent.parent / "data" / "note_workpaper_sync_registry.json"

# X_NOTE_SECTION = { listed: '五、4', soe: '八、4' }
#
# 🔴 必须锚定 `const/let/var` 声明 + 常量名在 `_NOTE_SECTION` 处收尾（`(?![\w])`）：
#    ①不锚定声明时，注释里提到常量名会让 `[^=]*=` 跨过注释咬到下一条语句
#      （与 `_SHEET_CONST` 同款陷阱）；
#    ②不收尾时 `X_NOTE_SECTION_DISPLAY`（界面展示用、非定位用）也会命中并**覆盖**
#      真正的定位常量 —— 实测 H10 因此把 `八、75` 写成 `八、75 资产处置收益`，
#      而 registry 是「同步就绪度看板」的章节定位真源。
#    ③body 允许**一层嵌套**（`(?:[^{}]|\{[^{}]*\})*`）：G1/G10 一个循环覆盖两个附注
#      章节，形态是 `listed: { trading: '五、2', derivative: '五、3' }`。原 `[^}]*`
#      在第一个 `}` 处截断 → `listed:` 后面不是引号 → 两个变体都抽不到 → 整条
#      wp_code 从 registry 消失（实测 G1/G10 长期缺失）。
_SECTION_BLOCK = re.compile(
    r"(?:const|let|var)\s+\w*_NOTE_SECTION(?![\w])"
    r"(?P<anno>\s*:[^=]{0,200})?\s*=\s*\{(?P<body>(?:[^{}]|\{[^{}]*\})*)\}",
    re.S,
)
_LISTED = re.compile(r"listed\s*:\s*['\"](?P<v>[^'\"]+)['\"]")
_SOE = re.compile(r"soe\s*:\s*['\"](?P<v>[^'\"]+)['\"]")
# 嵌套形态：`listed: { trading: '五、2', derivative: '五、3' }`（一个循环两个章节）
_LISTED_NESTED = re.compile(r"listed\s*:\s*\{(?P<body>[^{}]*)\}")
_SOE_NESTED = re.compile(r"soe\s*:\s*\{(?P<body>[^{}]*)\}")
_SUB_ENTRY = re.compile(r"(?P<key>\w+)\s*:\s*['\"](?P<v>[^'\"]+)['\"]")
# X_DISCLOSURE_SHEET_LISTED / _SOE / _NAME（sheet 真实 tab 名，尽力提取；找不到留空不臆造）
#
# 🔴 必须锚定 `const/let/var` 声明：否则文档注释里提到常量名时，`[^=]*=` 会跨过注释
#    咬到**下一条语句**的等号（实测 G12 因此把 `export type XVariant = 'listed'` 的
#    `'listed'` 当成 sheet 名，两个变体都写成 `listed`）。
_SHEET_CONST = re.compile(
    r"(?:const|let|var)\s+\w*_DISCLOSURE_SHEET_(?P<kind>LISTED|SOE|NAME)\b"
    r"(?P<anno>\s*:[^=]{0,200})?\s*=\s*(?P<body>[^;]{0,400})",
    re.S,
)
_WP_CODE = re.compile(r"^(?P<code>[a-z]+\d+)NoteSectionMap\.ts$")


def _wp_code_from_filename(name: str) -> str | None:
    m = _WP_CODE.match(name)
    return m.group("code").upper() if m else None


def _extract_sheet_names(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for m in _SHEET_CONST.finditer(text):
        kind = m.group("kind")
        body = m.group("body")
        direct = re.match(r"\s*['\"](?P<v>[^'\"]+)['\"]", body)
        if direct:
            if kind == "LISTED":
                out.setdefault("listed", direct.group("v"))
            elif kind == "SOE":
                out.setdefault("soe", direct.group("v"))
            else:
                out.setdefault("listed", direct.group("v"))
                out.setdefault("soe", direct.group("v"))
            continue
        lm = _LISTED.search(body)
        sm = _SOE.search(body)
        if lm:
            out.setdefault("listed", lm.group("v"))
        if sm:
            out.setdefault("soe", sm.group("v"))
    return out


def _is_section_code(v: str | None) -> bool:
    """章节号形态校验：``五、4`` / ``八、52`` / ``三、公允价值变动收益``。

    防把 sheet 名常量（``附注披露信息（上市公司）``）误当章节号（H6 复用 H1 常量时会命中）。
    """
    return bool(v) and bool(re.match(r"^[一二三四五六七八九十]+、", v or ""))


def _extract_nested_sections(body: str, pattern: re.Pattern[str]) -> dict[str, str]:
    """抽 `listed: { trading: '五、2', derivative: '五、3' }` 形态的子章节。

    返回 ``{子键: 章节号}``，只保留通过 :func:`_is_section_code` 的值（防把
    sheet 名或其它字面量当章节号）。
    """
    m = pattern.search(body)
    if not m:
        return {}
    out: dict[str, str] = {}
    for sub in _SUB_ENTRY.finditer(m.group("body")):
        v = sub.group("v")
        if _is_section_code(v):
            out[sub.group("key")] = v
    return out


_REVERSE_MAP_PATH = (
    FRONTEND_SRC / "views" / "composables" / "noteDisclosureReverseJump.ts"
)
# E1: { listed: '五、1', soe: '八、1' },  /  G13: { listed: '三、公允价值变动收益', soe: '八、72' },
_REVERSE_ENTRY = re.compile(
    r"^\s*(?P<key>[A-Z][A-Z0-9_]*)\s*:\s*\{(?P<body>[^}]*)\}", re.M
)


def load_reverse_map() -> dict[str, dict[str, str | None]]:
    """读前端反向跳转 map（``DISCLOSURE_NOTE_SECTION_MAP``）补全变体章节号。

    NoteSectionMap 里部分损益类科目（G13/G14/H10）只声明 listed（soe 走关键词章节，
    定义在反向 map 里）；两者同源（守卫已 cross-check 一致），此处合并取并集。
    """
    out: dict[str, dict[str, str | None]] = {}
    if not _REVERSE_MAP_PATH.exists():
        return out
    text = _REVERSE_MAP_PATH.read_text(encoding="utf-8")
    start = text.find("DISCLOSURE_NOTE_SECTION_MAP")
    if start < 0:
        return out
    for m in _REVERSE_ENTRY.finditer(text[start:]):
        body = m.group("body")
        lm = _LISTED.search(body)
        sm = _SOE.search(body)
        lv = lm.group("v") if lm else None
        sv = sm.group("v") if sm else None
        if not (_is_section_code(lv) or _is_section_code(sv)):
            continue
        out[m.group("key")] = {
            "listed": lv if _is_section_code(lv) else None,
            "soe": sv if _is_section_code(sv) else None,
        }
    return out


def build_entries() -> list[dict]:
    reverse = load_reverse_map()
    entries: list[dict] = []
    for path in sorted(FRONTEND_SRC.rglob("*NoteSectionMap.ts")):
        wp_code = _wp_code_from_filename(path.name)
        if not wp_code:
            continue
        text = path.read_text(encoding="utf-8")
        listed = soe = None
        listed_sections: dict[str, str] = {}
        soe_sections: dict[str, str] = {}
        for block in _SECTION_BLOCK.finditer(text):
            body = block.group("body")
            lm = _LISTED.search(body)
            sm = _SOE.search(body)
            lv = lm.group("v") if lm else None
            sv = sm.group("v") if sm else None
            if _is_section_code(lv) or _is_section_code(sv):
                listed = lv if _is_section_code(lv) else None
                soe = sv if _is_section_code(sv) else None
                break
            # 嵌套形态（一个循环两个章节，如 G1 交易性金融资产/衍生金融资产）
            nested_l = _extract_nested_sections(body, _LISTED_NESTED)
            nested_s = _extract_nested_sections(body, _SOE_NESTED)
            if nested_l or nested_s:
                listed_sections = nested_l
                soe_sections = nested_s
                # `listed`/`soe` 取首个子章节保持既有消费方兼容；全集见 *_sections
                listed = next(iter(nested_l.values()), None)
                soe = next(iter(nested_s.values()), None)
                break
        if not (listed or soe):
            continue
        # 反向 map 补全缺失变体（同源，不覆盖已有）
        rev = reverse.get(wp_code) or {}
        listed = listed or rev.get("listed")
        soe = soe or rev.get("soe")
        sheets = _extract_sheet_names(text)
        entry = {
            "wp_code": wp_code,
            "listed": listed,
            "soe": soe,
            "sheet_listed": sheets.get("listed"),
            "sheet_soe": sheets.get("soe"),
            "source_file": str(path.relative_to(REPO_ROOT)).replace("\\", "/"),
        }
        # 多章节循环：附加字段（可选，既有消费方只读 listed/soe 不受影响）
        if listed_sections:
            entry["listed_sections"] = listed_sections
        if soe_sections:
            entry["soe_sections"] = soe_sections
        entries.append(entry)
    return entries


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="写入 JSON")
    args = ap.parse_args()

    entries = build_entries()
    payload = {
        "_source": (
            "生成自前端 *NoteSectionMap.ts（唯一真源），勿手工编辑；"
            "重生成：python backend/scripts/gen_note_wp_sync_registry.py --write"
        ),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "entries": entries,
    }
    print(f"[OK] entries={len(entries)}")
    missing_sheet = [e["wp_code"] for e in entries if not (e["sheet_listed"] or e["sheet_soe"])]
    if missing_sheet:
        print(f"[WARN] no sheet name extracted (not fabricated): {missing_sheet}")
    if args.write:
        OUT_PATH.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"[OK] written {OUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
