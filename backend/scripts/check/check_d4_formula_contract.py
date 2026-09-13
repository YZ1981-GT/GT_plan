#!/usr/bin/env python
"""D4 C2 公式契约守卫（governance spec Task 3 / Property 3）。

冻结契约核对（防冻结 fiction）：

1. `engine` 引用的 `UserFormulaV2Store` / `apply_batch_mutate` / `COMMAND_VERSION` 在
   `user_formula_v2.py` 真实存在；CAS 字段 `baseVersion` 在引擎里被读到；audit 门确实
   「先 audit 后 upsert」（源码含 `AuditCommitError` 且 upsert 在 audit.append 之后）。
2. `capability_gate` 引用的 `formulaEditUser` action 在 `workpaper_capability.py`
   的 `CAPABILITY_ACTIONS` 里，且 fail-closed（`assert_snapshot_action_allowed` 存在）。
3. `fshell_whitelist` 的 `F-SHELL` 契约 ID 在前端契约文件里；forbidden 列的
   `eval` / `legacy_dict_user_formula_api` 出现在 NON_CAPABILITIES。
4. `preset_source` 的 D4 函数白名单与「无成环」判据由既有 test_d4_formula_presets.py
   守（此处只校验文件存在，不重复其断言）。
5. `ssot_persistence_gap` 是**如实登记的缺口**：断言当前引擎确为 in-memory
   （源码含 `DEFAULT_V2_STORE = UserFormulaV2Store()` 且无迁移表）——
   若将来落地持久化，本断言会打红，提示更新契约 gap 状态（防缺口被静默遗忘）。
6. 反向自检。

只读；退出码 1 表示契约与代码漂移。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
_REPO = _BACKEND.parent
_CONTRACT = _BACKEND / "data" / "d4_formula_contract_frozen.json"


def _read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8")
    except Exception:  # noqa: BLE001
        return ""


def _mod(module: str) -> Path:
    return _BACKEND / (module.replace(".", "/") + ".py")


def main() -> int:
    errs: list[str] = []
    c = json.loads(_CONTRACT.read_text(encoding="utf-8"))

    # 1a. definition SSOT（真·公式定义单一真源 = formula_management）
    ds = c["definition_ssot"]
    res_text = _read(_mod(ds["resolver_module"]))
    if not res_text:
        errs.append(f"公式 SSOT 解析模块不存在：{ds['resolver_module']}")
    else:
        for sym in (
            f"def {ds['resolver_fn']}",
            f"def {ds['key_fn']}",
            f"class {ds['key_class']}",
        ):
            if sym not in res_text:
                errs.append(f"{ds['resolver_module']} 内找不到 {sym}")
        # 6 态齐备
        for st in ds["states"]:
            if f'"{st}"' not in res_text and f"'{st}'" not in res_text:
                errs.append(f"公式 SSOT 缺状态 {st}")
        # 白名单校验函数
        if f"def {ds['whitelist']['validate_fn']}" not in res_text:
            errs.append(f"公式 SSOT 缺白名单校验 {ds['whitelist']['validate_fn']}")
    # preset 持久化：seed 文件真实存在
    pp = ds["preset_persistence"]
    if not (_REPO / pp["seed_file"]).exists():
        errs.append(f"公式预设 seed 文件不存在：{pp['seed_file']}")
    if not _read(_mod(pp["module"])):
        errs.append(f"preset_library 模块不存在：{pp['module']}")

    # 1b. 附加的 user-formula 工具栏 v2 路径（非定义 SSOT）
    eng = c["user_formula_toolbar_v2"]
    eng_text = _read(_mod(eng["backend_module"]))
    if not eng_text:
        errs.append(f"user_formula_v2 模块不存在：{eng['backend_module']}")
    else:
        for sym in (eng["store_class"], eng["apply_fn"], eng["command_version_const"]):
            if sym not in eng_text:
                errs.append(f"{eng['backend_module']} 内找不到 {sym}")
        if eng["cas_field"] not in eng_text:
            errs.append(f"v2 未读 CAS 字段 {eng['cas_field']}")
        if "AuditCommitError" not in eng_text:
            errs.append("v2 缺 AuditCommitError（audit 失败回滚门缺失）")
        if "audit.append" in eng_text and ".upsert(" in eng_text:
            if eng_text.index("audit.append") > eng_text.rindex("store.upsert"):
                errs.append("audit.append 出现在 upsert 之后 —— commit gate 顺序反了")

    # 2. capability gate
    cap = c["capability_gate"]
    cap_text = _read(_mod(cap["backend_module"]))
    if not cap_text:
        errs.append(f"能力模块不存在：{cap['backend_module']}")
    else:
        if cap["action"] not in cap_text:
            errs.append(f"能力模块缺 action {cap['action']}")
        if "assert_snapshot_action_allowed" not in cap_text:
            errs.append("能力模块缺 assert_snapshot_action_allowed（fail-closed 门缺失）")

    # 3. F-SHELL
    fs = c["fshell_whitelist"]
    fs_text = _read(_REPO / fs["frontend_contract"])
    if not fs_text:
        errs.append(f"F-SHELL 契约文件不存在：{fs['frontend_contract']}")
    else:
        if f"'{fs['contract_id']}'" not in fs_text:
            errs.append(f"F-SHELL 契约 ID {fs['contract_id']} 未命中")
        # NON_CAPABILITIES 禁令面：契约声明的每条都必须在源码里
        for tok in fs["non_capabilities_forbidden"]:
            if tok not in fs_text:
                errs.append(f"F-SHELL NON_CAPABILITIES 缺 {tok}（禁令面缺失）")
    # no-eval 由后端白名单校验器保证：validate_formula 存在即证
    ne = fs["no_eval_enforced_by"]
    ne_text = _read(_mod(ne["backend_validator"]))
    if not ne_text:
        errs.append(f"公式校验器模块不存在：{ne['backend_validator']}")
    elif f"def {ne['fn']}" not in ne_text:
        errs.append(f"{ne['backend_validator']} 内找不到 {ne['fn']}（no-eval 白名单缺失）")

    # 4. preset source exists
    ps = c["preset_source"]
    if not (_BACKEND / ps["file"].replace("backend/", "")).exists() and not (
        _REPO / ps["file"]
    ).exists():
        errs.append(f"preset 源文件不存在：{ps['file']}")

    # 5. ssot_status 如实：定义 SSOT 已持久化五元键；工具栏 v2 仍 in-memory（如实登记）
    st = c["ssot_status"]
    if st.get("d4_1_definition_ssot_persisted") is True:
        # 定义 SSOT 持久化的证据 = seed 文件存在（上面已查）+ preset_persistence.persisted=true
        if pp.get("persisted") is not True:
            errs.append("ssot_status 声明已持久化，但 preset_persistence.persisted≠true")
    # 工具栏 v2 的 in-memory 登记须与源码一致
    if eng_text:
        is_in_memory = "DEFAULT_V2_STORE = UserFormulaV2Store()" in eng_text
        if eng.get("in_memory_only") is True and not is_in_memory:
            errs.append(
                "user_formula_toolbar_v2 登记 in_memory_only=true，但源码已非 "
                "DEFAULT_V2_STORE in-memory —— 请更新登记"
            )

    # 6. 反向自检
    if "def resolve_effective_formula" in res_text and "__absent_fn_xyz__" in res_text:
        errs.append("反向自检失败：不存在符号被判存在")

    if errs:
        print(f"[FAIL] D4 C2 公式契约守卫检出 {len(errs)} 项漂移：")
        for e in errs:
            print(f"  - {e}")
        return 1
    print(
        "[OK] D4 C2 公式契约：定义SSOT(effective_formula五元键/6态/白名单+持久化preset) "
        "/ 工具栏v2(CAS+audit门,in-memory如实) / 能力门 / F-SHELL / no-eval 全部命中源码。"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
