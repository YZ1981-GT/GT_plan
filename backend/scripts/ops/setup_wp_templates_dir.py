"""底稿模板目录与 `_index.json` 的生命周期工具。

`backend/wp_templates/` 是**运行时权威**：`wp_template_init_service` 据它生成底稿，
`wp_template_finder` 以 `_index.json` 索引它。所以本脚本的默认动作是**只检查不落盘**。

用法::

    python backend/scripts/ops/setup_wp_templates_dir.py                  # 检查漂移（默认）
    python backend/scripts/ops/setup_wp_templates_dir.py --check          # 同上（显式）
    python backend/scripts/ops/setup_wp_templates_dir.py --apply          # 按磁盘重建索引
    python backend/scripts/ops/setup_wp_templates_dir.py --sync-from-source --apply
                                                                          # 先从致同源目录补拷再重建

退出码：0 = 无漂移 / 已应用；1 = 有漂移（检查模式）；2 = 前置条件不满足（未落盘）。

🔴 **默认改成只检查，是修一个会静默毁索引的缺陷**（2026-09-30）。原实现只有一个模式：
遍历源目录拷文件，**且只为「本次真的拷过去的文件」追加索引条目**，最后无条件覆盖写
`_index.json`。于是第二次运行时所有文件都命中 `if target_path.exists(): skipped; continue`
⇒ `index_entries` 为空 ⇒ 把 476 条索引**整体写成 0 条**，而模板文件还在磁盘上。
索引是 finder 的唯一真源，写空等于全库底稿解析不到模板，且没有任何提示。
现在索引一律由**磁盘全量投影**产出（不依赖"这次拷了什么"），写盘走 CAS + 原子替换。
"""
import argparse
import hashlib
import io
import json
import os
import re
import shutil
import sys
import uuid
from pathlib import Path


def _force_utf8_console() -> None:
    """Windows 控制台按 UTF-8 输出（CLI 专用）。

    🔴 2026-09-30 修：这段原先在**模块级**执行，与 `scripts/e2e/seed_fix_projects.py`
    2026-09-28 修掉的是同一个缺陷 —— 模块级把 `sys.stdout` 换成一个**接管了
    `sys.stdout.buffer` 所有权**的新 `TextIOWrapper`，该 wrapper 被回收时会关掉底层
    buffer。于是 import 本模块的 pytest 进程在 teardown `readouterr()` 时撞
    `ValueError: I/O operation on closed file`，**整个测试会话崩在收尾**，报错位置还在
    `_pytest/capture.py`，完全看不出是哪个模块干的。

    实测后果：`tests/test_wp_template_index_lifecycle.py` 经
    `importlib.util.spec_from_file_location` 在**模块导入期**加载本文件，于是该测试
    文件的 7 个用例**从来没真正跑过**。

    🔴 搬进函数还不够 —— 本函数会被 `main()` 调用，而测试**在同进程里调 main()**。
    所以这里分三层，确保既不夺走别人的 buffer 也不破坏 pytest capture：
      1. 已经是 UTF-8（含 pytest capture）⇒ 直接返回，一个字节都不动；
      2. 有 `reconfigure` ⇒ **就地**改编码（不转移 buffer 所有权，无 close 隐患）；
      3. 兜底才新建 `TextIOWrapper`（真·GBK 控制台且 Python 老到没有 reconfigure）。
    """
    if sys.platform != "win32":
        return
    encoding = (getattr(sys.stdout, "encoding", "") or "").lower().replace("-", "")
    if encoding.startswith("utf8"):
        return
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if callable(reconfigure):
        reconfigure(encoding="utf-8", errors="replace")
        return
    buffer = getattr(sys.stdout, "buffer", None)
    if buffer is None:
        return
    sys.stdout = io.TextIOWrapper(buffer, encoding="utf-8", errors="replace")


class TemplateIndexError(RuntimeError):
    """索引投影不自洽 / 前置条件不满足 / CAS 冲突。"""


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SOURCE_BASE = REPO_ROOT / "致同通用审计程序及底稿模板（2025年修订）" / "1.致同审计程序及底稿模板（2025年）"
TARGET_DIR = REPO_ROOT / "backend" / "wp_templates"
INDEX_FILE = TARGET_DIR / "_index.json"

#: 源目录映射（只在 `--sync-from-source` 时用到）
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

#: 算模板的扩展名（与原拷贝逻辑同集合）
TEMPLATE_SUFFIXES = (".xlsx", ".xlsm", ".xls", ".docx", ".doc")

#: 特殊条目角色：`relative_path`（正斜杠）→ 角色。
#:
#: 这些条目**不是**该 wp_code 的普通候选，finder 按角色分流：
#:   * ``whole_workbook``       —— 整册合并本（D4/F2 那种一本装全循环的）
#:   * ``dedicated_subtemplate`` —— 专用子模板（如 F2-22 存货监盘计划.docx）
#: 真库 `_index.json` 现有 476 条**一条都没有 role**（现算）⇒ 眼下是空表，
#: 但键一旦登记，`build_index` 会把它投影进索引、finder 会据它分流。
SPECIAL_ENTRY_ROLES: dict[str, str] = {}


def parse_wp_code(filename: str) -> str:
    m = RE_WP_CODE.match(filename)
    return m.group(1) if m else ""


# ═══════════════════════════════════════════════════════════════════════════
# 磁盘 → 索引：全量投影
# ═══════════════════════════════════════════════════════════════════════════

#: 首字母 → category。D~N 归一为 "D-N"，与真库 476 条现状一致（现算：
#: A/B/C/S 用自身，D E F G H I J K L M N 全是 "D-N"）。
_DN_PREFIXES = frozenset("DEFGHIJKLMN")


def _category_for_relative(relative: str) -> str:
    """按顶层子目录推 category。

    `_reference/` 下的参考文件在真库里 category 随其源目录而异（实测 A 2 / D-N 3 / B 1），
    **无法从磁盘推**。因此新发现的参考文件给 `_ref`；已在索引里的那 6 条走条目继承，
    不受本函数影响。
    """
    top = relative.split("/")[0]
    if top == "_reference":
        return "_ref"
    if top in _DN_PREFIXES:
        return "D-N"
    return top


def iter_template_files(template_root: Path) -> list[Path]:
    """权威目录下的模板文件，确定性排序。

    排除 Office/WPS 锁文件（`~$` / `~WRL`）与非模板扩展名 —— `_index.json` 自然被
    扩展名过滤挡掉，所以「索引不会把自己算成模板」不依赖额外特判。
    """
    out = [
        p
        for p in template_root.rglob("*")
        if p.is_file()
        and p.suffix.lower() in TEMPLATE_SUFFIXES
        and not p.name.startswith(("~$", "~WRL"))
    ]
    out.sort(key=lambda p: p.relative_to(template_root).as_posix())
    return out


def _normalise_relative(value: str) -> str:
    """索引里的 `relative_path` 归一为正斜杠。

    🔴 真库 476 条现在全是**反斜杠**（`A\\A1 财务报告程序表.xlsx`）—— 那是原实现用
    `str(Path.relative_to())` 在 Windows 上写出来的。本模块统一产出正斜杠（可移植、
    与 `Path.as_posix()` 一致），读入时两种都认。因此 `--apply` 会把存量条目一并
    归一化 —— 这是**有意**的，但它是一次跨 476 条的形态变更，不在本次范围内执行。
    """
    return value.replace("\\", "/")


def _stem_identity(relative: str) -> tuple[str, str]:
    """扩展名槽位身份：(所在目录, 文件名主干)。

    `A/A17-7 独立性声明.doc` 与 `A/A17-7 独立性声明.docx` 是同一个"槽"的新旧两代
    （doc → docx 升级）。按槽继承，人工标注（category / manual_marker 等）才跟着走，
    否则升级一次扩展名就把标注丢了。
    """
    p = Path(_normalise_relative(relative))
    return (p.parent.as_posix(), p.stem)


#: 由文件本身**重算**的字段；其余键（wp_code / category / manual_marker / 自定义键）
#: 从被匹配上的旧条目**继承**。这条分界就是「人工标注不因重建而丢失」的全部机制。
_DERIVED_FIELDS = ("filename", "relative_path", "format", "size_kb")

#: 条目键的规范顺序。
#:
#: 🔴 **不是排版洁癖，是幂等性的前提**。`build_index` 先从旧条目继承非派生键、再补派生键，
#: 于是"首次生成"与"读回来再生成"的 dict **插入顺序不同**（首次 wp_code→…→category；
#: 二次 wp_code→category→filename→…）。`json.dumps` 按插入顺序出文本 ⇒ 内容完全相同的
#: 索引渲染出两份不同字节 ⇒ `--apply` 之后紧跟的 `--check` 报漂移、CI 永远红。
#: 实测踩过：`--apply` 返回 0 之后 `--check` 返回 1。
_CANONICAL_FIELD_ORDER = (
    "wp_code", "filename", "relative_path", "format", "size_kb", "category", "role",
)


def _canonicalise(entry: dict) -> dict:
    """按规范顺序重排条目键；未登记的自定义键按名字排序追加在后面。"""
    out = {k: entry[k] for k in _CANONICAL_FIELD_ORDER if k in entry}
    for key in sorted(set(entry) - set(_CANONICAL_FIELD_ORDER)):
        out[key] = entry[key]
    return out


def _project_entry(path: Path, template_root: Path, old: dict | None) -> dict:
    """单个磁盘文件 → 索引条目（派生字段重算、其余键从旧条目继承）。"""
    rel = path.relative_to(template_root).as_posix()
    entry: dict = {k: v for k, v in (old or {}).items() if k not in _DERIVED_FIELDS}
    entry["wp_code"] = entry.get("wp_code") or (parse_wp_code(path.name) or "_ref")
    entry["filename"] = path.name
    entry["relative_path"] = rel
    entry["format"] = path.suffix.lower().lstrip(".")
    entry["size_kb"] = round(path.stat().st_size / 1024, 1)
    entry.setdefault("category", _category_for_relative(rel))
    role = SPECIAL_ENTRY_ROLES.get(rel)
    if role:
        entry["role"] = role            # 角色以登记表为权威，覆盖旧值
    elif "role" in entry:
        del entry["role"]               # 从登记表摘掉后，索引里也不许留残影
    return _canonicalise(entry)


def build_index(*, template_root: Path, existing_payload: dict) -> dict:
    """按磁盘全量投影出索引（保留旧条目的人工标注与顺序）。

    与原实现的根本差别：条目集合来自**磁盘**，不是"这次拷了哪些文件"。
    因此重复运行是幂等的，也不会把索引写空。

    顺序：先按 `existing_payload["files"]` 的原顺序放"被继承上的"条目（diff 可读、
    人工排序不被打乱），再按 `relative_path` 追加新发现的文件。
    旧条目在磁盘上已无对应文件时**丢弃**（那正是 `validate_index` 要拦的 missing 态）。
    """
    files = iter_template_files(template_root)
    remaining: dict[str, Path] = {
        p.relative_to(template_root).as_posix(): p for p in files
    }
    remaining_by_stem: dict[tuple[str, str], list[str]] = {}
    for rel in remaining:
        remaining_by_stem.setdefault(_stem_identity(rel), []).append(rel)

    entries: list[dict] = []
    for old in list(existing_payload.get("files") or []):
        old_rel = _normalise_relative(str(old.get("relative_path") or ""))
        if not old_rel:
            continue
        rel = old_rel if old_rel in remaining else None
        if rel is None:
            # 同目录同主干的另一种扩展名 = 同一个槽的新一代（.doc → .docx）
            candidates = sorted(remaining_by_stem.get(_stem_identity(old["relative_path"]), []))
            rel = next((c for c in candidates if c in remaining), None)
        if rel is None:
            continue
        entries.append(_project_entry(remaining.pop(rel), template_root, old))

    for rel in sorted(remaining):
        entries.append(_project_entry(remaining[rel], template_root, None))

    return {
        "description": existing_payload.get("description")
        or "底稿模板文件索引（按磁盘全量投影）",
        "total_files": len(entries),
        "files": entries,
    }


def render_index(payload: dict) -> str:
    """索引的**唯一**文本形态 —— 漂移比对与落盘都走它，保证 `--check` 幂等。"""
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def validate_index(payload: dict, *, template_root: Path) -> None:
    """双向锁死索引与磁盘的投影关系。

    两个方向都要查，缺一个就有一类静默故障漏网：
      * 索引有、磁盘无（**missing**）⇒ finder 解析出一个不存在的路径，
        底稿生成时才炸，且错误指向文件系统而不是索引；
      * 磁盘有、索引无（**unexpected**）⇒ 那份模板任何 wp_code 都解析不到，
        它在库里却永远用不上（真库的 `F2存货.xlsx` 就是这个形态）。
    """
    entries = list(payload.get("files") or [])
    indexed = {
        _normalise_relative(str(e.get("relative_path") or "")) for e in entries
    }
    indexed.discard("")
    disk = {
        p.relative_to(template_root).as_posix() for p in iter_template_files(template_root)
    }

    missing = set(indexed) - set(disk)
    if missing:
        raise TemplateIndexError(
            f"索引声明了 {len(missing)} 份磁盘上不存在的模板（missing on disk）："
            + ", ".join(sorted(missing)[:10])
        )
    unexpected = set(disk) - set(indexed)
    if unexpected:
        raise TemplateIndexError(
            f"磁盘上有 {len(unexpected)} 份模板不在索引里（unexpected on disk，"
            f"任何 wp_code 都解析不到它们）：" + ", ".join(sorted(unexpected)[:10])
        )
    total = payload.get("total_files")
    if total != len(entries):
        raise TemplateIndexError(
            f"total_files={total} 与 files 实际条数 {len(entries)} 不符"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 落盘：CAS + 原子替换
# ═══════════════════════════════════════════════════════════════════════════


def _sha256_of(path: Path) -> str:
    """文件内容的 sha256；文件不存在返回空串（= "本来没有"这一态）。"""
    if not path.is_file():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _atomic_write_index(
    path: Path, text: str, *, expected_old_sha256: str | None = None
) -> None:
    """写索引：先 CAS 比对旧内容，再临时文件 + `os.replace` 原子替换。

    * **CAS**（`expected_old_sha256`）防的是「读-算-写」窗口里别人也改了索引：
      并发 lane 同时跑一次 `--apply` 时，后写的会**拒绝覆盖**而不是静默吞掉前一次。
      传 `None` 表示不校验（首次创建）。
    * **原子替换**防的是半截文件：`_index.json` 是 finder 的唯一真源，写一半会让
      全库解析不到模板。临时文件与目标**同目录**（跨盘 `os.replace` 不原子）。
    * 失败路径必须清掉临时文件，否则权威目录里会积一堆 `.xxx.tmp`。
    """
    if expected_old_sha256 is not None:
        actual = _sha256_of(path)
        if actual != expected_old_sha256:
            raise TemplateIndexError(
                f"拒绝覆盖 {path.name}：CAS 不匹配（期望旧内容 sha256 "
                f"{expected_old_sha256[:12]}…，实际 {actual[:12] or '<不存在>'}…）"
                " —— 说明读取之后有别人改过它，请重跑检查再决定"
            )
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
    try:
        tmp.write_bytes(text.encode("utf-8"))
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


# ═══════════════════════════════════════════════════════════════════════════
# 可选前置动作：从致同源目录补拷
# ═══════════════════════════════════════════════════════════════════════════


def sync_from_source(*, source_dirs: dict, target_dir: Path) -> tuple[int, int]:
    """把源目录里缺的模板补拷进权威目录，返回 (拷入, 跳过)。

    🔴 **先把所有源目录校验完再动手**（fail-before-write）：源目录缺失往往意味着
    没挂载/改名/在别的机器上，这时"拷一半"比"一个字节都不拷"更难收拾 —— 而且
    索引随后会按"拷了一半"的磁盘状态重建，把残缺状态固化成权威。
    """
    missing = [
        str(d)
        for dirs in source_dirs.values()
        for d in dirs
        if not Path(d).is_dir()
    ]
    if missing:
        raise TemplateIndexError(
            f"源目录不存在，未执行任何拷贝（{len(missing)} 个）：" + ", ".join(missing[:5])
        )

    copied = skipped = 0
    for category, dirs in source_dirs.items():
        for directory in dirs:
            for src in sorted(Path(directory).rglob("*")):
                if not src.is_file():
                    continue
                if src.name.startswith(("~$", "~WRL")):
                    continue
                if src.suffix.lower() not in TEMPLATE_SUFFIXES:
                    continue
                wp_code = parse_wp_code(src.name)
                sub = target_dir / (wp_code[0] if wp_code else "_reference")
                sub.mkdir(parents=True, exist_ok=True)
                dst = sub / src.name
                if dst.exists():
                    skipped += 1
                    continue
                shutil.copy2(src, dst)
                copied += 1
    return copied, skipped


# ═══════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════


def _load_payload(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TemplateIndexError(f"现有索引无法解析：{path}（{exc}）") from exc
    return data if isinstance(data, dict) else {}


def main(argv: list[str] | None = None) -> int:
    """默认只检查不落盘；`--apply` 才写。返回码见模块 docstring。"""
    _force_utf8_console()   # 必须在第一次 print 之前；守卫 test_script_import_safety 钉住这一行

    parser = argparse.ArgumentParser(description="底稿模板目录与 _index.json 生命周期")
    parser.add_argument(
        "--apply", action="store_true", help="把重建后的索引写盘（默认只检查）"
    )
    parser.add_argument(
        "--check", action="store_true", help="只检查漂移（默认行为，显式写出用于 CI）"
    )
    parser.add_argument(
        "--sync-from-source", action="store_true",
        help="落盘前先从致同源目录补拷缺失模板（需 --apply 才真正生效）",
    )
    args = parser.parse_args(argv)

    target_dir, index_file = TARGET_DIR, INDEX_FILE
    if not target_dir.is_dir():
        print(f"[ERROR] 权威模板目录不存在：{target_dir}")
        return 2

    if args.sync_from_source:
        try:
            copied, skipped = sync_from_source(
                source_dirs=SOURCE_DIRS, target_dir=target_dir
            )
        except TemplateIndexError as exc:
            print(f"[ERROR] {exc}")
            return 2
        print(f"[SYNC] 补拷 {copied} 份，跳过（已存在）{skipped} 份")

    before_raw = index_file.read_bytes() if index_file.is_file() else b""
    try:
        payload = build_index(
            template_root=target_dir, existing_payload=_load_payload(index_file)
        )
        validate_index(payload, template_root=target_dir)
    except TemplateIndexError as exc:
        print(f"[ERROR] {exc}")
        return 2

    rendered = render_index(payload)
    drifted = rendered.encode("utf-8") != before_raw

    if not args.apply:
        if not drifted:
            print(f"[OK] 索引与磁盘一致（{payload['total_files']} 份模板）")
            return 0
        print(
            f"[DRIFT] 索引与磁盘不一致（磁盘 {payload['total_files']} 份模板）—— "
            "本次**未**写盘。确认无误后用 --apply 落盘："
        )
        print("        python backend/scripts/ops/setup_wp_templates_dir.py --apply")
        return 1

    if not drifted:
        print(f"[OK] 索引已是最新（{payload['total_files']} 份模板），无需写盘")
        return 0
    try:
        _atomic_write_index(
            index_file,
            rendered,
            expected_old_sha256=hashlib.sha256(before_raw).hexdigest()
            if before_raw
            else None,
        )
    except TemplateIndexError as exc:
        print(f"[ERROR] {exc}")
        return 2
    print(f"[APPLIED] 已重建 {index_file}（{payload['total_files']} 份模板）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
