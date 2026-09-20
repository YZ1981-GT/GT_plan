r"""D4-14 穿行测试双向回写守卫变异检验 —— 证明守卫非重言式。

spec: d4-14-walkthrough-writeback · Wave 5 · Property 2/3/4/5

被检验的守卫：
* backend/tests/workpaper_sync/test_d4_14_occurrence_contract.py（契约结构/formula_mask/嵌套/item_id）
* backend/tests/workpaper_sync/test_d4_14_walkthrough_roundtrip.py（真 instrument 7 维嵌套往返 + HTML-only 保留）
* backend/tests/workpaper_sync/test_d4_14_mirror_consume.py（第四维：OO→HTML 消费侧）

## 为什么每条变异都不是无效变异

D4-14 三类最贵缺陷各有对应变异：
1. **7 维嵌套 json_pointer 被拍平** → 受管字段落到错的路径，前端 store 结构错配（M01）；
2. **formula_mask 漏格** → SUM 合计列被当录入回写，覆盖 Excel 公式（M02）；
3. **契约块整体脱落** → d414-managed 不进契约，双向回写形同虚设（M03）；
4. **merge 不真写** → OO→HTML 回读静默丢弃（M04）；
5. **value_type 金额退化 text** → 金额往返丢失数值语义（M05）。

## 用法（仓库根；PATH 上的 python 可能坏）

    .\.venv\Scripts\python.exe backend/scripts/diagnose/mutate_d4_14_guards.py --list
    .\.venv\Scripts\python.exe backend/scripts/diagnose/mutate_d4_14_guards.py --run M01,M02
    .\.venv\Scripts\python.exe backend/scripts/diagnose/mutate_d4_14_guards.py --check-anchors

🔴 禁后台执行（孤儿 python + 前台同时变异 ⇒ RestoreFailed）；绝不 --restore。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/scripts

from _mutation_kit import Mutation, run_cli  # noqa: E402

REPO = Path(__file__).resolve().parents[3]

PROV = "backend/app/services/workpaper_sync/phase5_d4_14_occurrence.py"
DETAIL = "backend/app/services/workpaper_sync/phase5_d4_revenue_detail.py"

_CONTRACT = "test_d4_14_occurrence_contract.py"
_ROUNDTRIP = "test_d4_14_walkthrough_roundtrip.py"
_MIRROR = "test_d4_14_mirror_consume.py"

MUTATIONS: list[Mutation] = [
    Mutation(
        id="M01", side="be", path=PROV, kind="replace",
        anchor='    ("voucher_customer_name", "B", "editable", "text", "voucher/customerName", "客户名称"),',
        new='    ("voucher_customer_name", "B", "editable", "text", "customerName", "客户名称"),',
        want=f"{_CONTRACT}::test_d414_fields_full_managed_set",
        wants=(
            f"{_CONTRACT}::test_d414_nested_pointers_cover_all_seven_dimensions",
            f"{_ROUNDTRIP}::test_materialize_extract_roundtrip_nested_7dim",
        ),
        why="7 维嵌套 json_pointer 被拍平成顶层 customerName：契约 json_pointer 不再是 "
            "/{row_uuid}/voucher/customerName，且 nested 维度集合缺 voucher.customerName 归属；"
            "真往返也读不到该嵌套字段。改 json_path 而非删整行——测的是「映射到错的路径」这一形态。",
    ),
    Mutation(
        id="M02", side="be", path=PROV, kind="replace",
        anchor='FORMULA_MASK_D414: Final[tuple[str, ...]] = ("G37", "X37", "AF37", "G39")',
        new='FORMULA_MASK_D414: Final[tuple[str, ...]] = ("X37", "AF37", "G39")',
        want=f"{_CONTRACT}::test_d414_table_geometry",
        why="formula_mask 去掉 G37（凭证金额 SUM 合计列）：合计公式格失去保护，会被当录入回写 "
            "覆盖 Excel 公式（对齐 Property 4 formula_mask 完整性）。",
    ),
    Mutation(
        id="M03", side="be", path=DETAIL, kind="replace",
        anchor="_INCLUDE_D414_OCCURRENCE_SHEET: Final[bool] = True",
        new="_INCLUDE_D414_OCCURRENCE_SHEET: Final[bool] = False",
        want=f"{_CONTRACT}::test_d414_present_in_contract_payload",
        wants=(
            f"{_CONTRACT}::test_d414_parses_and_item_id_literal",
            f"{_MIRROR}::test_d414_in_store_item_ids_rows_loop",
            f"{_MIRROR}::test_merge_all_returns_four_tuple_for_d414",
        ),
        why="契约块整体脱落：d414-managed 不进 build_contract_payload、STORE_ITEM_IDS、merge_all；"
            "双向回写形同虚设。这条同时证明契约/消费侧守卫都真的在查 D4-14 存在性。",
    ),
    Mutation(
        id="M04", side="be", path=PROV, kind="replace",
        anchor="        if set_json_path(target, json_path, new_val):",
        new="        if False and set_json_path(target, json_path, new_val):",
        want=f"{_ROUNDTRIP}::test_merge_preserves_html_only_derived_fields",
        wants=(
            f"{_MIRROR}::test_mirror_consume_preserves_html_only_and_not_empty",
        ),
        why="merge 不真写回：OO→HTML 回读虽 visited 但从不 set_json_path，applied 恒 0、"
            "受管字段静默丢弃（第四维「不静默投空」判据的反证）。",
    ),
    Mutation(
        id="M05", side="be", path=PROV, kind="replace",
        anchor='    ("invoice_amount", "AF", "editable", "amount", "invoice/amount", "发票金额"),',
        new='    ("invoice_amount", "AF", "editable", "text", "invoice/amount", "发票金额"),',
        want=f"{_CONTRACT}::test_d414_amount_columns_are_amount_type",
        why="发票金额 value_type 从 amount 退化 text：金额往返丢失数值语义（Excel 数值 vs 字符串），"
            "对齐裁决表「金额=amount」列口径。",
    ),
]

GUARD_FILES = {
    _CONTRACT: "Task 9 新建（契约结构/formula_mask/嵌套/item_id）",
    _ROUNDTRIP: "Task 9 新建（真 instrument 7 维嵌套往返 + HTML-only 保留）",
    _MIRROR: "Task 10 新建（第四维 OO→HTML 消费侧）",
}

if __name__ == "__main__":
    raise SystemExit(
        run_cli(
            mutations=MUTATIONS,
            guard_files=GUARD_FILES,
            repo=REPO,
            backend_args=[
                "backend/tests/workpaper_sync/test_d4_14_occurrence_contract.py",
                "backend/tests/workpaper_sync/test_d4_14_walkthrough_roundtrip.py",
                "backend/tests/workpaper_sync/test_d4_14_mirror_consume.py",
                "-q", "--tb=no", "-rf", "-p", "no:randomly",
            ],
            baseline_backend_passed=14,
        )
    )
