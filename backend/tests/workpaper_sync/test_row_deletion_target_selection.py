"""为什么 K11 不能当删行靶子 —— 靶子选择依据的可伪证登记。

spec: workpaper-sync-row-deletion-multi-region-propagation
Tasks: 13 · 23

═══ 为什么从 `test_row_deletion_convergence_dispatch.py` 拆出来 ═══

原文件 890 行，超 pre-commit 的 800 行上限。切缝按**判据对象**取：原文件问
「分流树对不对」，本文件问「靶子选得对不对」—— 后者是前者的**前提**而不是它的一部分。

本文件存在的理由：上游整节改用 D1-8 是因为 K11 走不通。那个结论如果只写在注释里，
哪天 K11 的形态变了（跨 sheet 引用被清掉 / 静态格挪走），注释就变成谎言而没人知道。
这里把「为什么换靶子」变成会打红的事实。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:  # pragma: no cover - import 环境自举
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

# 🔴 拆分时我在这里写过「依赖全部在方法体内按需 import」—— 那是**凭印象写的假事实**，
#    AST 现算缺 `C` 与 `M` 两个模块别名（`NameError: name 'C' is not defined`）。
#    其余依赖（`excel_extract` / `excel_workbook_row_change` /
#    `test_clear_path_byte_zero_regression`）确实都在方法体内 import，搬过来后逐字不变。
from app.services.workpaper_sync import contracts as C  # noqa: E402
from app.services.workpaper_sync import excel_materialize as M  # noqa: E402



class TestWhyK11CannotBeTheDeletionTarget:
    """🔴 靶子选择依据的**可伪证登记**（不只写在注释里）。

    本节存在的理由：上面整节改用 D1-8 是因为 K11 走不通。那个结论如果只写在注释里，
    哪天 K11 的形态变了（跨 sheet 引用被清掉 / 静态格挪走），注释就变成谎言而没人知道。
    这两条判据把「为什么换靶子」变成会打红的事实。
    """

    def test_k11_managed_rows_are_locked_by_cross_sheet_references(self) -> None:
        """K11 受管区的行被跨 sheet 单格引用指着 ⇒ 门面按 Requirement 1.8 拒绝删除。"""
        import io
        import zipfile

        from app.services.workpaper_sync import excel_extract as X
        from app.services.workpaper_sync import excel_workbook_row_change as N1

        import test_clear_path_byte_zero_regression as BASE
        from test_task37_excel_extract import BINDING, MANAGED_SHEET

        data = BASE.make_substrate_bytes()
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            entries = {n: zf.read(n) for n in zf.namelist() if not n.endswith("/")}
            part = X._sheet_parts(zf).get(MANAGED_SHEET)
        assert part, MANAGED_SHEET

        with pytest.raises(N1.DanglingReferenceError) as err:
            N1.plan_workbook_row_change_for_delete(
                entries,
                managed_sheet_name=MANAGED_SHEET,
                managed_sheet_part=part,
                deleted_rows=(BASE.STALE_ROW,),
                region_first_row=7,
                region_last_row=25,
                row_uuids={BASE.STALE_ROW: BASE.STALE_IDENTITY},
            )
        text = str(err.value)
        assert "#REF!" in text and str(BASE.STALE_ROW) in text, text
        assert MANAGED_SHEET in text, (
            f"错误文案没点名被引用的那张表：{text[:200]}"
        )

    def test_k11_insert_lane_is_also_blocked(self) -> None:
        """K11 连插行都走不通（静态格落在插入点之下）⇒ 它也造不出共存输入。

        这条解释了为什么共存判据也必须换靶子，而不是「删行用 D1-8、共存用 K11」。
        """
        import zipfile

        from app.services.excel_structure_fingerprint import identity_inventory
        from app.services.workpaper_sync import excel_extract as X
        from app.services.workpaper_sync.adapters.base import SubstrateRole
        from app.services.workpaper_sync.models import ArtifactKind, ArtifactState

        import test_clear_path_byte_zero_regression as BASE
        from test_task37_excel_extract import (
            BINDING,
            CONTRACT_ID,
            contract_payload,
            make_definitions,
        )

        import dataclasses
        import tempfile

        data = BASE.make_substrate_bytes()
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "k11.xlsx"
            base.write_bytes(data)
            contract = C.parse_contract(contract_payload(), adapter_id=CONTRACT_ID)
            inventory = identity_inventory(
                data,
                expected_table=BINDING.table_name,
                uuid_column_letter=BINDING.uuid_column,
            )
            outcome = X.extract_projection(
                artifact=base,
                definitions=make_definitions(contract, inventory),
                binding=BINDING,
                substrate_role=SubstrateRole.published_representation,
                artifact_kind=ArtifactKind.canonical,
                artifact_state=ArtifactState.published,
            )
            with zipfile.ZipFile(base) as zf:
                runtime_binding = X.read_runtime_binding_pairs(zf)
                entries = {n: zf.read(n) for n in zf.namelist() if not n.endswith("/")}

            projection = outcome.projection
            row_keys = dict(projection.row_keys)
            key = next(iter(row_keys))
            row_keys[key] = (*row_keys[key], "GTROW-MINTED-K11PROBE001")
            projection = dataclasses.replace(projection, row_keys=row_keys)

            with pytest.raises(M.RowSetDivergenceError) as err:
                M.plan_managed_writes(
                    projection=projection,
                    contract=contract,
                    binding=BINDING,
                    region=outcome.region,
                    scan=outcome.scan,
                    substrate_entries=entries,
                    substrate_formulas=outcome.formula_inventory,
                    runtime_binding=runtime_binding,
                )
        assert "contract_static_row_below_insertion" in str(err.value), str(err.value)[:200]
