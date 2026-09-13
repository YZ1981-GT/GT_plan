#!/usr/bin/env python
"""D4 C3 联动 + C0-C3 平台契约守卫（governance spec Task 4 + 5 / Property 4）。

反 fiction 核对（引用符号/测试/模块必须真实存在）：

1. real_dag：no-cycle 守卫测试文件存在且含 `TestNoCyclicReferences`。
2. single_writer：D4-1 值 writer `build_d4_adjudication_prefill` 在 render 策略里存在。
3. tb_a13_publish_boundary：`publishAdjudicated` 在 useD4Adjudication 里且 TB 回写走
   独立 `d4:writeback-trial-balance` channel（与公式保存/模式切换分离）。
4. four_table_reuse：`ReportLineAccountSpec` 在 four_table.report_line_accounts；D4
   消费者 `build_d4_tb_values` 存在且真的 import 了 four_table（不复制 SQL）。
5. import_identity：D4 roundtrip 测试文件存在。
6. permission_cas / idempotent_migration：能力模块存在；MigrationRunner 目录存在。
7. 反向自检。

只读；退出码 1 表示契约与代码漂移。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
_REPO = _BACKEND.parent
_CONTRACT = _BACKEND / "data" / "d4_linkage_platform_contract_frozen.json"


def _read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8")
    except Exception:  # noqa: BLE001
        return ""


def _mod(module: str) -> Path:
    return _BACKEND / (module.replace(".", "/") + ".py")


def _repo_read(rel: str) -> str:
    return _read(_REPO / rel)


def main() -> int:
    errs: list[str] = []
    c = json.loads(_CONTRACT.read_text(encoding="utf-8"))

    # 1. real DAG no-cycle guard
    dag = c["real_dag"]["no_cycle_guard"]
    dag_text = _repo_read(dag["test"])
    if not dag_text:
        errs.append(f"no-cycle 守卫测试不存在：{dag['test']}")
    elif f"class {dag['class']}" not in dag_text:
        errs.append(f"{dag['test']} 内找不到 class {dag['class']}")

    # 2. single writer — render prefill
    sw_fqn = c["single_writer"]["d4_1_value_writer"]
    sw_mod, sw_fn = sw_fqn.rsplit(".", 1)
    sw_text = _read(_mod(sw_mod))
    if not sw_text:
        errs.append(f"D4-1 值 writer 模块不存在：{sw_mod}")
    elif f"def {sw_fn}" not in sw_text:
        errs.append(f"{sw_mod} 内找不到 {sw_fn}")

    # 3. TB/A13 publish boundary
    adj_text = _repo_read(
        "audit-platform/frontend/src/components/workpaper/composables/useD4Adjudication.ts"
    )
    pub = c["tb_a13_publish_boundary"]["d4_publish_is_explicit"]
    if not adj_text:
        errs.append("useD4Adjudication.ts 不存在")
    else:
        if f"function {pub['fn']}" not in adj_text:
            errs.append(f"useD4Adjudication 内找不到 {pub['fn']}")
        if "d4:writeback-trial-balance" not in adj_text:
            errs.append("TB 回写 channel d4:writeback-trial-balance 缺失（发布边界失守）")

    # 4. four_table reuse
    ft = c["four_table_reuse"]
    ft_text = _read(_mod(ft["module"]))
    if not ft_text:
        errs.append(f"four_table 模块不存在：{ft['module']}")
    elif f"class {ft['spec_dataclass']}" not in ft_text:
        errs.append(f"{ft['module']} 内找不到 {ft['spec_dataclass']}")
    cons_mod, cons_fn = ft["d4_consumer"].rsplit(".", 1)
    cons_text = _read(_mod(cons_mod))
    if not cons_text:
        errs.append(f"D4 four_table 消费者模块不存在：{cons_mod}")
    else:
        if f"def {cons_fn}" not in cons_text:
            errs.append(f"{cons_mod} 内找不到 {cons_fn}")
        # 复用而非复制：消费者应 import four_table
        if "four_table" not in cons_text:
            errs.append(f"{cons_mod} 未 import four_table（疑似复制 SQL）")

    # 5. import identity roundtrip test
    rt = c["import_identity"]["d4_roundtrip_test"]
    if not _repo_read(rt):
        errs.append(f"D4 导入 roundtrip 测试不存在：{rt}")

    # 6. permission cas + migration runner dir
    cap_text = _read(_mod(c["permission_cas"]["capability_module"]))
    if not cap_text:
        errs.append(f"能力模块不存在：{c['permission_cas']['capability_module']}")
    if not (_BACKEND / "migrations").is_dir():
        errs.append("backend/migrations 目录不存在（MigrationRunner 源）")

    # 7. 反向自检
    if adj_text and "__absent_fn_zzz__" in adj_text:
        errs.append("反向自检失败：不存在符号被判存在")

    if errs:
        print(f"[FAIL] D4 C3+平台契约守卫检出 {len(errs)} 项漂移：")
        for e in errs:
            print(f"  - {e}")
        return 1
    print(
        "[OK] D4 C3+平台契约：真实DAG/单writer/TB-A13发布边界/四表复用/导入identity/权限CAS/幂等迁移 引用全部命中。"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
