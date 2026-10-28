"""V2 依赖图静态数据的双读对账（acnr-foundation-defect-closure T22，需求 9.4，design §10.2）。

遍历 V2 路由读取的四个静态文件（L2 语义锚点、resolved refs、L3 跨表依赖、CCR），把每个节点 / 边端点的
旧字段（底稿编码 + 表文字 + 末段）经 `app.services.acnr.v2_canonical`（与 V2 读端点同一函数）换成规范身份，
按「来源文件 × 分类」计数，每类附中文原因与前 20 个样本，写入 `backend/data/acnr/v2_canonical_reconcile.json`。

分类：`addr_id`（得到规范 addr_id，即目录登记格）或 `unresolved_code`（`cell_not_in_catalog` / `label_not_a1` /
`ambiguous_sheet_name` / `alias_forbidden` / `sheet_not_in_catalog` / `wp_not_in_catalog` / `not_wellformed` /
`not_workpaper_node`）。产物不含时间戳；`inputs` 记各输入文件的 LF 内容 sha256（含目录）。

用法（cwd 任意）：
    python backend/scripts/acnr/reconcile_v2_canonical.py --write   # 重算并写出（内容不变不写）
    python backend/scripts/acnr/reconcile_v2_canonical.py --check   # 重算与已提交产物比对，不同退出 1 并点名

只依赖标准库与 `app.services.acnr` 中只导入标准库的模块（CI 作业不装依赖）。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Iterator

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.services.acnr import reasons, v2_canonical  # noqa: E402
from app.services.acnr.catalog import CatalogIndex  # noqa: E402
from app.services.acnr.catalog_integrity import content_sha256  # noqa: E402

_DATA = _BACKEND_ROOT / "data"
OUTPUT_PATH = _DATA / "acnr" / "v2_canonical_reconcile.json"
CATALOG_PATH = _DATA / "acnr" / "global_catalog.json"
#: V2 路由 `_load()` 读取的四个静态文件（顺序即产物里的顺序）
SOURCE_FILES = (
    "address_registry_l2_semantic.json",
    "address_registry_resolved_refs.json",
    "address_registry_l3_dependencies.json",
    "cross_wp_references.json",
)
SAMPLE_LIMIT = 20
ADDR_CLASS = "addr_id"
ADDR_CLASS_REASON = "得到规范 addr_id（目录登记格）"


def _rel(p: Path) -> str:
    return p.resolve().relative_to(_BACKEND_ROOT.parent.resolve()).as_posix()


# ─── 每个文件的端点枚举：(角色, 底稿编码, 表文字, 末段, 非底稿模块) ────────────────────


def _ends_l2(data: dict) -> Iterator[tuple[str, Any, Any, Any, Any]]:
    for wp, files in data.items():
        for _fname, sheets in (files or {}).items():
            for sn, sd in (sheets or {}).items():
                for _anchor, cell in ((sd or {}).get("anchors") or {}).items():
                    yield "anchor", wp, sn, cell, None


def _end(role: str, end: dict) -> tuple[str, Any, Any, Any, Any]:
    if end.get("wp_code"):
        return role, end.get("wp_code"), end.get("sheet"), end.get("cell"), None
    return role, None, None, None, end.get("target_module") or "未知模块"


def _ends_resolved(data: dict) -> Iterator[tuple[str, Any, Any, Any, Any]]:
    for r in data.get("resolved") or []:
        yield _end("source", r.get("source") or {})
        for t in r.get("targets") or []:
            yield _end("target", t)


def _ends_l3(data: dict) -> Iterator[tuple[str, Any, Any, Any, Any]]:
    for d in data.get("dependencies") or []:
        yield "source", d.get("source_wp"), d.get("source_sheet"), d.get("source_cell"), None
        yield "target", d.get("source_wp"), d.get("target_sheet"), d.get("target_cell"), None


def _ends_ccr(data: dict) -> Iterator[tuple[str, Any, Any, Any, Any]]:
    for r in data.get("references") or []:
        yield "source", r.get("source_wp"), r.get("source_sheet"), r.get("source_cell"), None
        for t in r.get("targets") or []:
            yield _end("target", t)


_ENUMERATORS = {
    "address_registry_l2_semantic.json": _ends_l2,
    "address_registry_resolved_refs.json": _ends_resolved,
    "address_registry_l3_dependencies.json": _ends_l3,
    "cross_wp_references.json": _ends_ccr,
}


def _class_reason(code: str) -> str:
    return ADDR_CLASS_REASON if code == ADDR_CLASS else reasons.NODE_UNRESOLVED_REASONS[code]


def build(index: CatalogIndex, data_dir: Path = _DATA) -> dict[str, Any]:
    """重算对账产物（纯计算，不写文件）。"""
    cache: dict[tuple, v2_canonical.CanonicalNode] = {}
    files_out: dict[str, Any] = {}
    totals: dict[str, int] = {}
    inputs = [{"path": _rel(CATALOG_PATH), "sha256": content_sha256(CATALOG_PATH.read_bytes())}]
    for name in SOURCE_FILES:
        path = data_dir / name
        raw = path.read_bytes()
        inputs.append({"path": _rel(path), "sha256": content_sha256(raw)})
        by_class: dict[str, dict[str, Any]] = {}
        nodes = 0
        for role, wp, sheet, last, module in _ENUMERATORS[name](json.loads(raw)):
            key = (wp, sheet, last, module)
            node = cache.get(key)
            if node is None:
                node = (v2_canonical.non_workpaper_node(module) if module is not None
                        else v2_canonical.canonical_node(wp, sheet, last, index=index))
                cache[key] = node
            code = ADDR_CLASS if node.addr_id else str(node.unresolved_code)
            bucket = by_class.setdefault(code, {"count": 0, "reason": _class_reason(code), "samples": []})
            bucket["count"] += 1
            nodes += 1
            if len(bucket["samples"]) < SAMPLE_LIMIT:
                old = f"{module}" if module is not None else f"{wp}|{sheet}|{last}"
                bucket["samples"].append({"role": role, "old": old,
                                          "addr_id": node.addr_id, "sheet_addr_id": node.sheet_addr_id,
                                          "unresolved_reason": node.unresolved_reason})
            totals[code] = totals.get(code, 0) + 1
        files_out[f"backend/data/{name}"] = {"nodes": nodes, "by_class": dict(sorted(by_class.items()))}
    return {
        "description": ("V2 静态数据双读对账（T22，需求 9.4）：每个节点 / 边端点的旧字段经 v2_canonical 换成规范身份，"
                        "按来源文件 × 分类计数，每类附中文原因与前 20 个样本；由 "
                        "backend/scripts/acnr/reconcile_v2_canonical.py --write 生成，不含时间戳。"),
        "registry_version": index.registry_version,
        "inputs": inputs,
        "files": files_out,
        "totals": {"nodes": sum(totals.values()), "addr_id": totals.get(ADDR_CLASS, 0),
                   "by_class": dict(sorted(totals.items()))},
    }


def render(result: dict[str, Any]) -> str:
    return json.dumps(result, ensure_ascii=False, indent=2) + "\n"


def _diff(committed: Any, rebuilt: dict[str, Any]) -> list[str]:
    if not isinstance(committed, dict):
        return ["(产物): v2_canonical_reconcile.json 缺失或无法解析"]
    lines = [f"(顶层): {k}" for k in sorted(set(committed) | set(rebuilt))
             if k != "files" and committed.get(k) != rebuilt.get(k)]
    cf, rf = committed.get("files") or {}, rebuilt.get("files") or {}
    for f in sorted(set(cf) | set(rf)):
        a, b = (cf.get(f) or {}).get("by_class") or {}, (rf.get(f) or {}).get("by_class") or {}
        for code in sorted(set(a) | set(b)):
            if a.get(code) != b.get(code):
                ca, cb = (a.get(code) or {}).get("count"), (b.get(code) or {}).get("count")
                lines.append(f"{f} × {code}: 已提交 {ca} / 重算 {cb}" + ("（样本或原因不同）" if ca == cb else ""))
        if (cf.get(f) or {}).get("nodes") != (rf.get(f) or {}).get("nodes"):
            lines.append(f"{f}: 节点数 已提交 {(cf.get(f) or {}).get('nodes')} / 重算 {(rf.get(f) or {}).get('nodes')}")
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="V2 静态数据双读对账（写出 / 比对）")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true", help="重算并写出（内容不变不写）")
    mode.add_argument("--check", action="store_true", help="重算并与已提交产物比对，不同退出 1")
    args = parser.parse_args(argv)
    index = CatalogIndex(json.loads(CATALOG_PATH.read_text(encoding="utf-8")))
    result = build(index)
    text = render(result)
    if args.write:
        if OUTPUT_PATH.exists() and OUTPUT_PATH.read_bytes() == text.encode("utf-8"):
            print(f"[v2-reconcile] 内容未变化，不写文件（目录 {result['registry_version']}）")
            return 0
        with open(OUTPUT_PATH, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        t = result["totals"]
        print(f"[v2-reconcile] 已写出：节点 {t['nodes']}，规范 addr_id {t['addr_id']}（目录 {result['registry_version']}）")
        return 0
    committed = json.loads(OUTPUT_PATH.read_text(encoding="utf-8")) if OUTPUT_PATH.exists() else None
    lines = _diff(committed, result)
    if not lines and OUTPUT_PATH.read_bytes().replace(b"\r\n", b"\n") != text.encode("utf-8"):
        lines.append("(格式): 产物文本与生成结果不同（结构相同，可能被手改了格式或键序）")
    if lines:
        print(f"[v2-reconcile] 漂移 {len(lines)} 处（输入或判定变了未重新生成，或产物被手改）：", file=sys.stderr)
        for line in lines[:50]:
            print(f"  {line}", file=sys.stderr)
        return 1
    print(f"[v2-reconcile] OK — 对账产物与重算一致（节点 {result['totals']['nodes']}，目录 {result['registry_version']}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
