"""ACNR CCR 源身份检查（CI 守卫，报告 / blocking 双模式；acnr-foundation-defect-closure T22，design §10.3）。

每条 CCR（`backend/data/cross_wp_references.json`）的源端点按统一身份判定（`exact_identity.sheet_of` /
`cell_of`，经 `app.services.acnr.ccr_sources`）解析到目录；本脚本不再有私有的表名匹配。

不可解析的源必须在豁免清单 `backend/data/acnr/sources/acknowledgements.json` 里逐条登记为 `ccr_unresolved`
（`covers.ccr_ids`，带 owner / 到期日 / 两项证据缺哪一项）：

- report（默认）：打印汇总与清单，退出 0。
- blocking（`--blocking`）：清单外的不可解析源、或「已可解析 / 已不存在仍在清单」的豁免条目，任一存在即退出 1；
  目录、CCR 或豁免清单缺失 / 无法解析退出 2（不放行）。
- `--json`：把结构化结果（汇总、不可解析源、清单外、失效豁免、停用条目引用、目标端点统计）打印为 JSON。

解析到停用条目的源 / 目标计入 deprecated 组（不阻断，design §3.3）。

只依赖标准库与 `app.services.acnr` 中只导入标准库的模块（CI 作业不装依赖）。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.services.acnr import ccr_sources  # noqa: E402
from app.services.acnr.catalog import CatalogIndex  # noqa: E402

_ACNR_DATA_DIR = _BACKEND_ROOT / "data" / "acnr"
CATALOG_PATH = _ACNR_DATA_DIR / "global_catalog.json"
CCR_PATH = _BACKEND_ROOT / "data" / "cross_wp_references.json"
ACK_PATH = _ACNR_DATA_DIR / "sources" / "acknowledgements.json"


class InputError(RuntimeError):
    """输入文件缺失或无法解析。"""


def _read(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise InputError(f"读取 {path.name} 失败：{exc}") from exc


def acknowledged_ccr_ids(acks: Any) -> dict[str, str]:
    """豁免清单里 kind=ccr_unresolved 的条目：ccr_id → 豁免 id。"""
    out: dict[str, str] = {}
    entries = acks.get("entries") if isinstance(acks, dict) else None
    for e in entries or []:
        if isinstance(e, dict) and e.get("kind") == "ccr_unresolved":
            for cid in (e.get("covers") or {}).get("ccr_ids") or []:
                out[str(cid)] = str(e.get("id") or "")
    return out


def run(catalog_data: dict[str, Any], ccr_data: dict[str, Any], acks: Any) -> dict[str, Any]:
    """统一判定下逐条解析 CCR 源 / 目标，并与豁免清单对账。纯计算，供 main 与测试共用。"""
    index = CatalogIndex(catalog_data)
    refs = [r for r in ccr_data.get("references") or [] if isinstance(r, dict)]
    sources = [(r, ccr_sources.source_end(r, index)) for r in refs]
    unresolved = [{"ref_id": e.ref_id, "state": e.state, "reason": e.reason,
                   "source": f"{r.get('source_wp')}:{r.get('source_sheet')}:{r.get('source_cell')}"}
                  for r, e in sources if not e.ok and not r.get("semantic_only")]
    semantic_only = [e.ref_id for r, e in sources if not e.ok and r.get("semantic_only")]
    acked = acknowledged_ccr_ids(acks)
    unresolved_ids = {u["ref_id"] for u in unresolved}
    all_ids = {e.ref_id for _r, e in sources}
    stale = [{"ccr_id": cid, "ack_id": aid,
              "detail": "该 CCR 源已可解析" if cid in all_ids else "CCR 里已没有这条引用"}
             for cid, aid in sorted(acked.items()) if cid not in unresolved_ids]
    targets = [t for r in refs for t in ccr_sources.target_ends(r, index)]
    deprecated = [{"ref_id": e.ref_id, "role": e.role, "addr_id": e.addr_id}
                  for e in [e for _r, e in sources] + targets if e.ok and ccr_sources.is_deprecated(e.addr_id, index)]
    return {
        "registry_version": catalog_data.get("registry_version"),
        "total": len(sources),
        "resolved": sum(1 for _r, e in sources if e.ok),
        "unresolved": unresolved,
        "semantic_only_skipped": semantic_only,
        "outside_list": [u for u in unresolved if u["ref_id"] not in acked],
        "stale_acknowledgements": stale,
        "deprecated": {"count": len(deprecated), "items": deprecated},
        "targets": {"total": len(targets), "resolved": sum(1 for t in targets if t.ok)},
    }


def _print(result: dict[str, Any], mode_label: str) -> None:
    print("=" * 70)
    print(f"  ACNR CCR 源身份检查 — {mode_label}（目录 {result['registry_version']}）")
    print("=" * 70)
    print(f"  CCR 源总数：{result['total']}")
    print(f"  可解析：{result['resolved']}")
    print(f"  不可解析：{len(result['unresolved'])}（semantic_only 跳过 {len(result['semantic_only_skipped'])}）")
    print(f"  不可解析且不在豁免清单：{len(result['outside_list'])}")
    print(f"  失效豁免（已可解析或已不存在仍在清单）：{len(result['stale_acknowledgements'])}")
    print(f"  停用条目引用（deprecated 组，不阻断）：{result['deprecated']['count']}")
    print(f"  底稿目标端点可解析：{result['targets']['resolved']}/{result['targets']['total']}")
    print("=" * 70)
    for u in result["outside_list"]:
        print(f"  [清单外] {u['ref_id']} {u['source']}：{u['reason']}")
    for s in result["stale_acknowledgements"]:
        print(f"  [失效豁免] {s['ack_id']}（{s['ccr_id']}）：{s['detail']}")
    for d in result["deprecated"]["items"]:
        print(f"  [停用] {d['ref_id']}（{d['role']}）→ {d['addr_id']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ACNR CCR 源身份检查（统一身份判定 + 豁免清单对账）")
    parser.add_argument("--blocking", action="store_true",
                        help="清单外不可解析源或失效豁免即退出 1；输入缺失退出 2")
    parser.add_argument("--json", action="store_true", help="打印结构化结果 JSON")
    args = parser.parse_args(argv)
    try:
        result = run(_read(CATALOG_PATH), _read(CCR_PATH), _read(ACK_PATH))
    except InputError as exc:
        print(f"[ACNR ccr-resolve] 无法检查：{exc}", file=sys.stderr)
        return 2 if args.blocking else 0
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        _print(result, "blocking 模式" if args.blocking else "报告模式")
    out = sys.stderr if args.json else sys.stdout
    failed = bool(result["outside_list"] or result["stale_acknowledgements"])
    if not failed:
        print("[ACNR ccr-resolve] OK — 不可解析的 CCR 源全部在豁免清单里逐条登记，清单无失效条目", file=out)
        return 0
    print(f"[ACNR ccr-resolve] 清单外 {len(result['outside_list'])} 条、失效豁免 {len(result['stale_acknowledgements'])} 条"
          + ("，blocking 模式退出 1" if args.blocking else "（报告模式不阻断）"), file=out)
    return 1 if args.blocking else 0


if __name__ == "__main__":
    sys.exit(main())
