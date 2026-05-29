"""将致同底稿模板文件复制到知识库目录

目标: ~/.gt_audit_helper/knowledge/workpaper_templates/{cycle}/
来源: gt_template_library.json 中的 file_path
"""
import json
import os
import shutil
from pathlib import Path

def main():
    # 知识库底稿模板目录
    base = Path(os.path.expanduser("~/.gt_audit_helper/knowledge/workpaper_templates"))
    base.mkdir(parents=True, exist_ok=True)

    # 加载模板索引
    lib_path = Path(__file__).resolve().parent.parent / "data" / "gt_template_library.json"
    if not lib_path.exists():
        print(f"模板索引不存在: {lib_path}")
        return

    with open(lib_path, "r", encoding="utf-8-sig") as f:
        data = json.load(f)

    templates = data.get("templates", data) if isinstance(data, dict) else data
    copied = 0
    skipped = 0
    missing = 0

    for t in templates:
        code = t.get("code", "")
        cycle = t.get("cycle_prefix", code[0] if code else "X")
        src_path = t.get("file_path", "")

        if not src_path:
            missing += 1
            continue

        src = Path(src_path)
        # 尝试多个位置查找源文件
        if not src.exists():
            # 从脚本所在目录的上上级（项目根目录）查找
            root = Path(__file__).resolve().parent.parent.parent
            src = root / src_path
        if not src.exists():
            missing += 1
            continue

        # 目标目录按循环分类
        dest_dir = base / cycle
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / src.name

        if dest.exists():
            skipped += 1
            continue

        shutil.copy2(src, dest)
        copied += 1

    print(f"完成: 复制 {copied} 个, 跳过 {skipped} 个已存在, {missing} 个源文件缺失")
    print(f"目标目录: {base}")

    # 统计各循环
    for d in sorted(base.iterdir()):
        if d.is_dir():
            count = len(list(d.glob("*.xlsx")))
            if count:
                print(f"  {d.name}: {count} 个文件")

if __name__ == "__main__":
    main()
