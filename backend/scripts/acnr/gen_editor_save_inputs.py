"""生成 / 核对 T21 编辑器保存入参夹具 ``backend/tests/acnr/fixtures/editor_save_inputs.json``。

acnr-foundation-defect-closure T21（需求 9.3，design §10.2 / §10.4）：模拟编辑器保存
``useStaleImpact.notify`` 发出的 ``WP:{底稿}:{活动表名}:审定数``（D~N 循环）——

- 「目录名」组：目录里每张 D~N 父级表的 ``sheet_name``；
- 「模板 tab 名」组：``address_registry_l2_semantic.json`` 里 D~N 底稿的模板 tab 名。

每条记录旧逻辑（T21 之前的 stale 引擎：正则从表显示名猜 sheet_code 再拼 id、``setdefault`` 先到者胜出，
只在本脚本里冻结复现）命中且与输入同一身份的起点 ``old_correct_start``，以及新规则
``StalePropagationEngine._start_keys`` 的起点与原因码。不含时间戳；目录或依赖图变了须重新生成。

用法：
  python backend/scripts/acnr/gen_editor_save_inputs.py --check   # 与已提交夹具结构化比对，不一致退出 1
  python backend/scripts/acnr/gen_editor_save_inputs.py --write   # 重新生成（LF）
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_BACKEND = _REPO_ROOT / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

FIXTURE = _BACKEND / "tests" / "acnr" / "fixtures" / "editor_save_inputs.json"
_DATA = _BACKEND / "data"
_CYCLES = frozenset("DEFGHIJKLMN")
_DESCRIPTION = ("T21 编辑器保存入参模拟（D~N 循环）：目录名 / 模板 tab 名作活动表名，末段「审定数」。"
                "old_correct_start 为旧逻辑（正则归一 + 先到者胜出）命中且同一张表的起点；"
                "由 backend/scripts/acnr/gen_editor_save_inputs.py 生成，不含时间戳。")

# ─── 旧逻辑（T21 之前 stale 引擎的 _detect_and_normalize + _build_addr_id_index，冻结复现） ──────
_OLD_SHEET_CODE = re.compile(r"([A-Z]\d+(?:-\d+)?[A-Z]?)")
_OLD_WP4 = re.compile(r"^WP:([^:]+):([^:]+):(.+)$")
_OLD_CUSTOM = re.compile(r"^WP:([^:]+)::(.+)$")
_OLD_LEGACY = re.compile(r"^WP:[^:]+:[^:]+:")


def _old_norm(uri: str) -> str:
    m = _OLD_WP4.match(uri)
    if m:
        wp, sheet, cell = m.groups()
        code = _OLD_SHEET_CODE.search(sheet)
        return f"{wp}/{code.group(1) if code else sheet}/{cell}"
    m = _OLD_CUSTOM.match(uri)
    return f"{m.group(1)}/{m.group(1)}/{m.group(2)}" if m else uri


def _old_index(graph: dict) -> dict[str, str]:
    index: dict[str, str] = {}
    for key in graph:
        index[key] = key
        if _OLD_LEGACY.match(key):
            nk = _old_norm(key)
            if nk != key:
                index.setdefault(nk, key)
    return index


def build_payload() -> dict:
    """现算夹具内容（只读真实目录与数据文件，不写文件）。"""
    from app.services.acnr import v2_canonical
    from app.services.acnr.catalog import get_catalog
    from app.services.stale_propagation_engine import StalePropagationEngine

    catalog = get_catalog()
    engine = StalePropagationEngine()
    graph = engine._graph
    old_index = _old_index(graph)
    inputs = {("目录名", f"WP:{s['parent_wp_code']}:{s['sheet_name']}:审定数")
              for s in catalog.sheets_by_addr_id.values()
              if (s.get("parent_wp_code") or "")[:1] in _CYCLES and s.get("sheet_name")}
    l2 = json.loads((_DATA / "address_registry_l2_semantic.json").read_bytes())
    inputs |= {("模板 tab 名", f"WP:{wp}:{sheet}:审定数") for wp, files in l2.items() if wp[:1] in _CYCLES
               for sheets in files.values() for sheet in sheets}
    rows = []
    for group, uri in sorted(inputs):
        nk = _old_norm(uri) if _OLD_LEGACY.match(uri) else uri
        old_key = old_index.get(nk, nk)
        node = v2_canonical.canonical_uri(uri, index=catalog)
        old_correct = None
        if old_key in graph:
            old_node = v2_canonical.canonical_uri(old_key, index=catalog)
            if old_node.identity_key and old_node.identity_key == node.identity_key:
                old_correct = old_key
        keys, unresolved = engine._start_keys(uri)
        rows.append({"group": group, "input": uri, "old_correct_start": old_correct,
                     "new_start_keys": sorted(keys),
                     "unresolved_code": unresolved.unresolved_code if unresolved else None})
    return {"description": _DESCRIPTION, "catalog_version": catalog.registry_version, "inputs": rows}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--write", action="store_true")
    args = ap.parse_args(argv)
    payload = build_payload()
    if args.write:
        FIXTURE.write_bytes((json.dumps(payload, ensure_ascii=False, indent=1) + "\n").encode("utf-8"))
        print(f"已写 {FIXTURE.relative_to(_REPO_ROOT).as_posix()}：{len(payload['inputs'])} 条")
        return 0
    committed = json.loads(FIXTURE.read_bytes())
    if committed == payload:
        print(f"OK：夹具与现算一致（{len(payload['inputs'])} 条，目录 {payload['catalog_version']}）")
        return 0
    # 同一入参可同时出现在「目录名」「模板 tab 名」两组，按 (组, 入参) 比对，避免同名入参互相覆盖漏报
    old = {(r.get("group"), r.get("input")): r for r in committed.get("inputs", [])}
    new = {(r["group"], r["input"]): r for r in payload["inputs"]}
    diff = sorted(k for k in old.keys() | new.keys() if old.get(k) != new.get(k))
    meta = [k for k in ("description", "catalog_version") if committed.get(k) != payload[k]]
    print(f"漂移：夹具与现算不一致（目录 {committed.get('catalog_version')} → {payload['catalog_version']}，"
          f"{len(diff)} 条入参不同{('，元数据不同：' + '、'.join(meta)) if meta else ''}），请运行 --write 重新生成并复核：")
    for k in diff[:20]:
        print(f"  {k}: 夹具 {old.get(k)} / 现算 {new.get(k)}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
