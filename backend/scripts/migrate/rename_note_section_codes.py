"""把数据文件 / 代码 / 前端映射里已改挂节的旧编号换成现行编号（可重跑）。

spec: disclosure-note-template-word-realignment Task 8（design §3.5）

旧 → 新 表取自两份种子的 ``legacy_section_numbers``（由 ``realign_note_templates_to_word.py`` 登记）。
匹配：旧编号前一字符不是中文数字（防「三、其他」误中「十三、其他」）、后一字符不是汉字 / 字母数字 / 左括号
（防误中以它开头的更长标题）。键、值、``note://旧/``、``旧:0`` 表格标记都覆盖。

范围：``backend/data/**/*.json``（种子、备份目录除外）、``backend/app`` / ``backend/tests`` / ``backend/scripts``
下的 ``.py``、前端 ``src`` 下的 ``.ts`` / ``.vue``。不改：种子（旧编号即别名）、``note_template_bindings_backup``、
Markdown（审计提示词里「十四、其他」不是附注编号）、真库快照、本工具与别名测试。

🔴 注释 / docstring / 用例名里的旧编号会一并换掉：描述旧编号**形态**的叙述（「上市侧是 md 截断值」「挂在三章，
不要修正」「长度 10」）换完即失真，判断函数里「旧章号 + 完整标题」的前缀写法（``startsWith('三、资产处置')``）
与展示常量也不在别名表里、换不到。2026-10-16 首跑后人工复核修正了 20 余处，``--write`` 之后必须同样复核；
注释里要提旧编号时写「原「三」章截断编号」，不写字面量（否则 ``--check`` 报红）。

用法（仓库根执行）：
    python backend/scripts/migrate/rename_note_section_codes.py           # 预演：逐文件计数
    python backend/scripts/migrate/rename_note_section_codes.py --write   # 写回
    python backend/scripts/migrate/rename_note_section_codes.py --check   # 仍有旧编号 exit 2 并点名
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "backend" / "data"
SCOPES = [
    (DATA, (".json",)),
    (ROOT / "backend" / "app", (".py",)),
    (ROOT / "backend" / "tests", (".py",)),
    (ROOT / "backend" / "scripts", (".py",)),
    (ROOT / "audit-platform" / "frontend" / "src", (".ts", ".vue")),
]
EXCLUDE_PARTS = {"note_template_bindings_backup", "node_modules", "__pycache__"}
EXCLUDE_FILES = {
    DATA / "note_template_soe.json",
    DATA / "note_template_listed.json",
    Path(__file__).resolve(),
    ROOT / "backend" / "tests" / "test_note_section_code_aliases.py",
    # 存量改编号用例：用真实种子别名（旧编号字面量）当输入，换成现行编号用例就失去意义
    ROOT / "backend" / "tests" / "test_note_project_realign.py",
    # 这两份镜像四版 Word 模板里的 ##SECTION## / {{section:…}} 标记（标记仍是旧编号，四版 Word 不改）；
    # 交付导出按标记编号找不到附注时按 section_id 兜底（section_id 不变），改它反而对不上标记
    DATA / "audit_report_templates" / "section_code_index.json",
    DATA / "audit_report_templates" / "section_content_analysis.json",
    # 真库快照（build_note_legacy_positional_pending.py 只读生成）：记的是库里现存编号，改了就是伪造快照；
    # 存量项目改编号后（spec Task 10~14）由生成脚本重跑
    DATA / "note_legacy_positional_pending.json",
    # 同为真库快照（e2e/trim_e2e_baseline.py --capture 抓的附注行，--restore 原样写回）
    DATA / "trim_e2e_baseline.json",
}


def load_aliases() -> dict[str, str]:
    out: dict[str, str] = {}
    for std in ("soe", "listed"):
        for s in json.loads((DATA / f"note_template_{std}.json").read_text(encoding="utf-8"))["sections"]:
            for old in s.get("legacy_section_numbers") or []:
                if old in out and out[old] != s["section_number"]:
                    raise SystemExit(f"旧编号 {old} 在两个准则指向不同的节：{out[old]} / {s['section_number']}")
                out[old] = s["section_number"]
    return out


def build_pattern(aliases: dict[str, str]) -> re.Pattern[str]:
    body = "|".join(re.escape(k) for k in sorted(aliases, key=len, reverse=True))
    return re.compile(rf"(?<![一二三四五六七八九十百])(?:{body})(?![\u4e00-\u9fffA-Za-z0-9（(])")


def iter_files():
    for root, suffixes in SCOPES:
        for p in sorted(root.rglob("*")):
            if p.is_file() and p.suffix in suffixes and p.resolve() not in EXCLUDE_FILES \
                    and not (set(p.parts) & EXCLUDE_PARTS) and not p.name.startswith("_"):
                yield p


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="附注旧编号 → 现行编号")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    parser.add_argument("--exclude", action="append", default=[],
                        help="跳过的文件（仓库相对路径，可重复）：并发会话未提交的文件等其提交后再跑")
    args = parser.parse_args(argv)
    aliases = load_aliases()
    pattern = build_pattern(aliases)
    skipped = {(ROOT / e).resolve() for e in args.exclude}
    total = 0
    for p in iter_files():
        if p.resolve() in skipped:
            print(f"   - 跳过 {p.relative_to(ROOT).as_posix()}")
            continue
        raw = p.read_bytes()
        text = raw.decode("utf-8", errors="strict")
        found = pattern.findall(text)
        if not found:
            continue
        total += len(found)
        rel = p.relative_to(ROOT).as_posix()
        print(f"{len(found):4d} {rel}")
        if args.write:
            p.write_bytes(pattern.sub(lambda m: aliases[m.group(0)], text).encode("utf-8"))
    print(f"旧编号 {len(aliases)} 个；命中 {total} 处")
    if args.check and total:
        print("🔴 --check：仍有旧编号，请运行 --write 或核对上列文件")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
