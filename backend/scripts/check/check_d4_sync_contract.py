#!/usr/bin/env python
"""D4 C1 共享同步契约守卫（governance spec Task 2 / Property 2）。

冻结契约不得指向不存在的符号（防「冻结了一份 fiction」）。守卫核对：

1. `shared_commit_boundary` 引用的后端类/前端 composable 在源码里真实存在。
2. `durable_ack_not_applied` 不变式引用的前端符号（`WP_BRIDGE_IN_FLIGHT_STATES`、
   `reloadAfterApplied`）真实存在，且 `applied` 确实在 in-flight 集合里
   （即「applied 后未 reload 就离开要阻断」这条判据没被删）。
3. `no_publish_on_mode_switch` 引用的 D4 `publishAdjudicated` 与 `useCycleHtmlOoDualMode`
   真实存在。
4. 反向自检：把一个必不存在的符号塞进核对逻辑必须判缺失。

只读；退出码 1 表示契约与代码漂移。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
_REPO = _BACKEND.parent
_CONTRACT = _BACKEND / "data" / "d4_sync_contract_frozen.json"
_FRONTEND = _REPO / "audit-platform" / "frontend" / "src"


def _read(rel: Path) -> str:
    try:
        return rel.read_text(encoding="utf-8")
    except Exception:  # noqa: BLE001
        return ""


def _module_to_path(module: str) -> Path:
    return _BACKEND / (module.replace(".", "/") + ".py")


def _symbol_present(text: str, symbol: str) -> bool:
    return symbol in text


def main() -> int:
    errs: list[str] = []
    contract = json.loads(_CONTRACT.read_text(encoding="utf-8"))

    scb = contract["shared_commit_boundary"]
    # 1. backend class exists
    be = scb["backend"]
    be_path = _module_to_path(be["module"])
    be_text = _read(be_path)
    if not be_text:
        errs.append(f"后端模块不存在：{be_path}")
    elif f"class {be['class']}" not in be_text:
        errs.append(f"{be['module']} 内找不到 class {be['class']}")

    # frontend composable exists
    fe = scb["frontend"]
    fe_path = _REPO / fe["module"]
    fe_text = _read(fe_path)
    if not fe_text:
        errs.append(f"前端桥文件不存在：{fe_path}")
    elif f"export function {fe['composable']}" not in fe_text:
        errs.append(f"{fe['module']} 内找不到 export function {fe['composable']}")

    # 2. durable_ack_not_applied evidence
    inv = contract["invariants"]["durable_ack_not_applied"]["frontend_evidence"]
    sym = inv["in_flight_states_symbol"]
    if fe_text and sym not in fe_text:
        errs.append(f"桥内找不到 {sym}（durable-ack≠applied 判据面缺失）")
    if fe_text and "reloadAfterApplied" not in fe_text:
        errs.append("桥内找不到 reloadAfterApplied（applied→reload 判据缺失）")
    # applied 必须在 in-flight 集合里：粗判 —— 集合定义块内含 'applied'
    if fe_text and sym in fe_text:
        blk_start = fe_text.index(sym)
        blk = fe_text[blk_start : blk_start + 800]
        if "'applied'" not in blk and '"applied"' not in blk:
            errs.append(
                "WP_BRIDGE_IN_FLIGHT_STATES 不含 'applied' —— "
                "applied 后未 reload 离开的阻断被删（Property 14 判据失守）"
            )

    # 3. no_publish_on_mode_switch — D4 evidence
    d4ev = contract["invariants"]["no_publish_on_mode_switch"]["d4_evidence"]
    adj_path = (
        _FRONTEND
        / "components"
        / "workpaper"
        / "composables"
        / "useD4Adjudication.ts"
    )
    adj_text = _read(adj_path)
    if not adj_text:
        errs.append(f"D4 审定 composable 不存在：{adj_path}")
    elif f"function {d4ev['adjudication_publish_fn']}" not in adj_text:
        errs.append(
            f"useD4Adjudication 内找不到 {d4ev['adjudication_publish_fn']}"
            "（显式发布动作缺失）"
        )
    mode_path = (
        _FRONTEND
        / "components"
        / "workpaper"
        / "composables"
        / "useCycleHtmlOoDualMode.ts"
    )
    if not _read(mode_path):
        errs.append(f"模式切换 composable 不存在：{mode_path}")

    # 4. 反向自检：不存在的符号必被判缺失
    if _symbol_present(fe_text, "__definitely_absent_symbol_xyz__"):
        errs.append("反向自检失败：不存在符号却被判存在")

    if errs:
        print(f"[FAIL] D4 C1 同步契约守卫检出 {len(errs)} 项漂移：")
        for e in errs:
            print(f"  - {e}")
        return 1
    print("[OK] D4 C1 同步契约：commit boundary / 桥 / durable-ack≠applied / 发布边界 引用全部命中源码。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
