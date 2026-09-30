"""将致同 2025 修订版模板文件复制到 backend/wp_templates/ 目录

按循环/阶段分子目录组织，建立模板索引文件。
生成底稿时从此目录复制模板。

用法: python backend/scripts/setup_wp_templates_dir.py
"""
import io
import json
import re
import shutil
import sys
from pathlib import Path

def _force_utf8_console() -> None:
    """Windows 控制台按 UTF-8 输出（CLI 专用）。

    🔴 2026-09-30 修：这段原先在**模块级**执行，与 `scripts/e2e/seed_fix_projects.py`
    2026-09-28 修掉的是同一个缺陷 —— 它把 `sys.stdout` 换成一个**接管了
    `sys.stdout.buffer` 所有权**的新 `TextIOWrapper`，该 wrapper 被回收时会关掉底层
    buffer。于是 import 本模块的 pytest 进程在 teardown `readouterr()` 时撞
    `ValueError: I/O operation on closed file`，**整个测试会话崩在收尾**，
    报错位置还在 `_pytest/capture.py`，完全看不出是哪个模块干的。

    实测后果：`tests/test_wp_template_index_lifecycle.py` 经
    `importlib.util.spec_from_file_location` 在**模块导入期**加载本文件，于是该测试
    文件的 7 个用例**从来没有真正跑过**（现象是 `EEEEEFF` + 崩溃，不是失败）。
    守卫 `tests/scripts/test_script_import_safety.py` 本该拦住这类事，但它按
    `from scripts.x import` 的**点号形态**正则找被 import 的脚本，识别不到
    路径式动态加载 ⇒ 本文件一直在它的视野之外（该盲区已随本次修复补上）。

    搬进函数后 CLI 行为不变：唯一入口是 `main()`，重绑之前没有任何输出。
    """
    if sys.platform == "win32":
        sys.stdout = io.TextIOWrapper(
            sys.stdout.buffer, encoding="utf-8", errors="replace"
        )


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SOURCE_BASE = REPO_ROOT / "致同通用审计程序及底稿模板（2025年修订）" / "1.致同审计程序及底稿模板（2025年）"
TARGET_DIR = REPO_ROOT / "backend" / "wp_templates"
INDEX_FILE = TARGET_DIR / "_index.json"

# 源目录映射
SOURCE_DIRS = {
    "B": [
        SOURCE_BASE / "1.初步业务活动（B1-B5）",
        SOURCE_BASE / "2.风险评估（B11-B60）",
    ],
    "C": [SOURCE_BASE / "3.风险应对-一般性程序与控制测试（C1-C26）"],
    "D-N": [SOURCE_BASE / "4.风险应对-实质性程序（D-N）"],
    "A": [SOURCE_BASE / "5.完成阶段（A1-A30）"],
    "S": [SOURCE_BASE / "6.特定项目程序（S）"],
}

RE_WP_CODE = re.compile(r"^([A-Z]\d+)")


def parse_wp_code(filename: str) -> str:
    m = RE_WP_CODE.match(filename)
    return m.group(1) if m else ""


def main():
    _force_utf8_console()   # 必须在第一次 print 之前；守卫 test_script_import_safety 钉住这一行
    print("=" * 60)
    print("设置底稿模板目录: backend/wp_templates/")
    print("=" * 60)

    # 创建目标目录
    TARGET_DIR.mkdir(parents=True, exist_ok=True)

    # 收集所有模板文件
    all_files: list[tuple[Path, str]] = []  # (source_path, category)
    for category, dirs in SOURCE_DIRS.items():
        for d in dirs:
            if not d.exists():
                print(f"  跳过（不存在）: {d}")
                continue
            for f in d.rglob("*"):
                if f.is_dir():
                    continue
                if f.name.startswith("~$") or f.name.startswith("~WRL"):
                    continue
                if f.suffix.lower() not in (".xlsx", ".xlsm", ".xls", ".docx", ".doc"):
                    continue
                all_files.append((f, category))

    print(f"\n  源文件总数: {len(all_files)}")

    # 按 wp_code 分组复制
    index_entries = []
    copied = 0
    skipped = 0

    for source_path, category in sorted(all_files, key=lambda x: x[0].name):
        wp_code = parse_wp_code(source_path.name)
        if not wp_code:
            # 参考文件，放到 _reference/ 子目录
            sub_dir = TARGET_DIR / "_reference"
        else:
            # 按首字母分子目录
            prefix = wp_code[0]
            sub_dir = TARGET_DIR / prefix

        sub_dir.mkdir(parents=True, exist_ok=True)
        target_path = sub_dir / source_path.name

        if target_path.exists():
            skipped += 1
            continue

        shutil.copy2(source_path, target_path)
        copied += 1

        index_entries.append({
            "wp_code": wp_code or "_ref",
            "filename": source_path.name,
            "relative_path": str(target_path.relative_to(TARGET_DIR)),
            "format": source_path.suffix.lower().lstrip("."),
            "size_kb": round(source_path.stat().st_size / 1024, 1),
            "category": category,
        })

    # 写入索引文件
    index_data = {
        "description": "底稿模板文件索引（从致同 2025 修订版复制）",
        "total_files": len(index_entries),
        "files": index_entries,
    }
    with open(INDEX_FILE, "w", encoding="utf-8") as f:
        json.dump(index_data, f, ensure_ascii=False, indent=2)

    # 统计
    by_prefix = {}
    for e in index_entries:
        p = e["wp_code"][0] if e["wp_code"] != "_ref" else "_ref"
        by_prefix[p] = by_prefix.get(p, 0) + 1

    print(f"\n  复制: {copied} 文件")
    print(f"  跳过（已存在）: {skipped} 文件")
    print(f"  索引条目: {len(index_entries)}")
    print(f"\n  按目录分布:")
    for k in sorted(by_prefix.keys()):
        print(f"    {k}/: {by_prefix[k]} 文件")
    print(f"\n  输出目录: {TARGET_DIR}")
    print(f"  索引文件: {INDEX_FILE}")


if __name__ == "__main__":
    main()
