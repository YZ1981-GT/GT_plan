"""真实链路验收：走完整 `materialize_projection` 的四条判据（Task 23.2）。

spec: workpaper-sync-row-deletion-multi-region-propagation
Requirements: 3.6, 7.1

═══ 与前面那些判据的分工 ═══

`test_row_deletion_convergence_dispatch` 走的是 `plan_managed_writes` +
`apply_plan_zip_with_report` —— **计划与字节**两层。本文件走 `materialize_projection`，
它才是生产链路那一层：落盘、identity 清册保留门、`assert_shifted_footer_gates`、
`verify_unmanaged_regions` 全都在它里面。上游 M28 的教训正是「只测下层，调用点可以整个
删掉而全绿」。

四条判据（tasks 23.2 原文）：
① materialize 成功（= 生产的 200）
② 被删行真的没了（受管 sheet 的物理行数 −N）
③ 兄弟区身份全在、**零 mint**
④ **下一趟**物化不抛 `FooterAnchorDriftError`

⚠ 范围说明（如实登记）：本文件验的是 **materialize 这一层的真实链路**，
**不含** HTTP「点在线编辑」那一跳 —— 那需要 `start-dev.bat` 起后端 9980 + 前端 3030。
判据④「下一趟物化」恰好覆盖了那一跳最常见的故障（第一次删成功、第二次点开就 500，
因为冻结元数据没同步），所以离线这四条已经把 A2 与 A7 的真实后果都验到了。

🔴 靶子按 Task 1.4（R4）的结论选：live D4 gen166 artifact 的 357 个物理身份**全为骨架**、
0 minted ⇒ stale 候选 0，原定的 live 靶子**已消失**。改用权威模板现场 instrument 出来的
D4-1 双区（不是 live 数据，也不造假业务数据 —— 那一行的业务值就是模板自带的）。
"""

from __future__ import annotations

import io
import os
import re
import sys
import zipfile
from pathlib import Path
from typing import Any

import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:  # pragma: no cover - import 环境自举
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

from app.services.excel_structure_fingerprint import identity_inventory  # noqa: E402
from app.services.workpaper_sync import excel_extract as X  # noqa: E402
from app.services.workpaper_sync import excel_materialize as M  # noqa: E402
from app.services.workpaper_sync.adapters.base import SubstrateRole  # noqa: E402
from app.services.workpaper_sync.models import ArtifactKind, ArtifactState  # noqa: E402

import test_row_deletion_g2_symptom_chain as G2  # noqa: E402
import test_sibling_table_ref_row_shift as SIB  # noqa: E402

A = SIB.A


def _physical_rows(data: bytes, sheet_part: str) -> list[int]:
    """受管 sheet 上**实际存在**的 `<row r=>` 行号（升序）。"""
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        xml = zf.read(sheet_part).decode("utf-8")
    return sorted(int(m.group(1)) for m in re.finditer(r'<row\b[^>]*\br="(\d+)"', xml))


@pytest.fixture(scope="module")
def world(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    """复用 G2 那套 D4-1 世界（同一份 substrate 构造 ⇒ 「哪一行是非骨架」只有一份真源）。

    🔴 调 G2 里抽出来的**普通函数**，不碰 `fixture.__wrapped__`：后者是 pytest 的实现细节，
    哪天 pytest 换了包装方式就断。本 spec 已经为同一个原因抽过一次
    （`test_row_deletion_convergence_dispatch._build_d18_world`）。
    """
    return G2.build_d41_world(tmp_path_factory.mktemp("acceptance-d41"))


def _definitions(contract: Any, binding: Any, data: bytes) -> Any:
    from test_task37_excel_extract import make_definitions

    inventory = identity_inventory(
        data, expected_table=binding.table_name, uuid_column_letter=binding.uuid_column
    )
    return make_definitions(contract, inventory)


def _projection_without_the_minted_row(outcome: Any) -> Any:
    import dataclasses

    projection = outcome.projection
    row_keys = dict(projection.row_keys)
    table_key = next(
        (k for k, rows in row_keys.items() if G2.STALE_IDENTITY in rows), None
    )
    assert table_key is not None, (
        f"projection 里找不到非骨架身份 {G2.STALE_IDENTITY}"
    )
    row_keys[table_key] = tuple(
        r for r in row_keys[table_key] if r != G2.STALE_IDENTITY
    )
    values = {
        key: value
        for key, value in dict(getattr(projection, "values", {}) or {}).items()
        if f"/{G2.STALE_IDENTITY}/" not in str(key)
    }
    replaced = dataclasses.replace(projection, row_keys=row_keys)
    if hasattr(replaced, "values"):
        replaced = dataclasses.replace(replaced, values=values)
    return replaced


@pytest.fixture(scope="module")
def first_trip(world: dict[str, Any]) -> dict[str, Any]:
    """第一趟：开 `row_convergence=delete` 后走完整 `materialize_projection`。"""
    contract = G2._contract(delete=True)
    definitions = _definitions(contract, SIB.BINDING_MAIN, world["bytes"])
    projection = _projection_without_the_minted_row(world["outcome_main"])
    output = world["workdir"] / "trip1" / "staged.xlsx"
    outcome = M.materialize_projection(
        substrate=world["base"],
        projection=projection,
        output=output,
        definitions=definitions,
        binding=SIB.BINDING_MAIN,
        substrate_role=SubstrateRole.published_representation,
        substrate_kind=ArtifactKind.canonical,
        substrate_state=ArtifactState.published,
    )
    return {
        "contract": contract,
        "definitions": definitions,
        "output": output,
        "outcome": outcome,
        "bytes": output.read_bytes(),
    }


# ═══════════════════════════════════════════════════════════════════════════
# 四条判据
# ═══════════════════════════════════════════════════════════════════════════


class TestRealChainAcceptance:
    """**Validates: Requirements 3.6, 7.1**"""

    def test_criterion1_materialize_succeeds_and_declares_the_deletion(
        self, first_trip: dict[str, Any]
    ) -> None:
        """① materialize 成功（生产的 200），且计划里**真的**带着删行声明。

        🔴 「没抛错」不够：契约门控没生效时它也不抛（走清空分支照样成功）。
        所以同时断言 `stale_deleted` 非空 —— 那才是「删行链路真的跑了」。
        """
        assert first_trip["output"].is_file(), "产物没落盘"
        plan = first_trip["outcome"].plan
        assert plan.stale_deleted == (G2.STALE_ROW,), (
            f"被删行实得 {plan.stale_deleted}，应为 ({G2.STALE_ROW},) —— "
            "materialize 成功但走的是清空分支，那不是本条要验的东西"
        )
        assert plan.row_deletion is not None and plan.deletion_change is not None
        assert plan.stale_cleared == ()

    def test_criterion2_the_deleted_row_is_physically_gone(
        self, world: dict[str, Any], first_trip: dict[str, Any]
    ) -> None:
        """② 被删行真的没了：受管 sheet 的物理行数 −1，且尾部少一行。"""
        before = _physical_rows(world["bytes"], world["sheet_part"])
        after = _physical_rows(first_trip["bytes"], world["sheet_part"])
        assert len(after) == len(before) - 1, (
            f"物理行数 {len(before)} → {len(after)}，应为 −1"
        )
        assert max(after) == max(before) - 1, (
            f"末行 {max(before)} → {max(after)}，应整体上移 1"
        )
        # 🔴 被删的那一行**之上**的行号逐个不变、之下逐个 −1（不是「总数对了就行」）
        kept_above = [r for r in before if r < G2.STALE_ROW]
        assert [r for r in after if r < G2.STALE_ROW] == kept_above, (
            "被删行之上的行号变了 ⇒ 删的位置不对"
        )
        shifted = [r - 1 for r in before if r > G2.STALE_ROW]
        assert [r for r in after if r >= G2.STALE_ROW] == shifted, (
            "被删行之下的行号没有整体 −1"
        )

    def test_criterion3_sibling_identities_all_survive_with_zero_mint(
        self, world: dict[str, Any], first_trip: dict[str, Any]
    ) -> None:
        """③ 兄弟区（other）身份全在、**零 mint**。

        这是 G2 症状链的核心后果：兄弟 ref 没跟着缩就会在这里冒出 `GTROW-MINTED-*`。
        """
        before_ids = {
            identity
            for ids in (world["outcome_other"].projection.row_keys or {}).values()
            for identity in ids
        }
        assert before_ids, "other 区在 substrate 上就没有行身份 ⇒ 本条空转"

        contract = first_trip["contract"]
        definitions = _definitions(contract, SIB.BINDING_OTHER, first_trip["bytes"])
        after_outcome = X.extract_projection(
            artifact=first_trip["output"],
            definitions=definitions,
            binding=SIB.BINDING_OTHER,
            substrate_role=SubstrateRole.published_representation,
            artifact_kind=ArtifactKind.canonical,
            artifact_state=ArtifactState.published,
        )
        after_ids = {
            identity
            for ids in (after_outcome.projection.row_keys or {}).values()
            for identity in ids
        }
        assert after_ids == before_ids, (
            f"other 区身份集合变了 —— 丢失 {sorted(before_ids - after_ids)} / "
            f"新增 {sorted(after_ids - before_ids)}"
        )
        assert after_outcome.scan.minted_by_row == {}, (
            f"other 区被 mint 了新身份：{after_outcome.scan.minted_by_row}"
        )

    def test_criterion4_a_second_materialize_does_not_raise_footer_drift(
        self, world: dict[str, Any], first_trip: dict[str, Any]
    ) -> None:
        """④ **下一趟**物化不抛 `FooterAnchorDriftError`。

        🔴 这条是 A2（`_GT_SYNC` 冻结值重冻结）真实后果的唯一直接验法：
        第一趟删成功但没更新 `GT_FOOTER_ROW`，第二趟在计划期就会撞
        `assert_footer_anchor_stable`（可见侧 marker 实测 = 冻结值 − 删行数，
        而 `row_shift is None` 分支要求两者严格相等）—— 症状是
        「删行这次成功了、下次点在线编辑起 500」。

        第二趟用**第一趟的产物**当 substrate，projection 原样回灌（没有新的 stale），
        于是它必须是一次干净的 no-op 物化。
        """
        contract = first_trip["contract"]
        definitions = _definitions(contract, SIB.BINDING_MAIN, first_trip["bytes"])
        reread = X.extract_projection(
            artifact=first_trip["output"],
            definitions=definitions,
            binding=SIB.BINDING_MAIN,
            substrate_role=SubstrateRole.published_representation,
            artifact_kind=ArtifactKind.canonical,
            artifact_state=ArtifactState.published,
        )
        output2 = world["workdir"] / "trip2" / "staged.xlsx"
        outcome2 = M.materialize_projection(
            substrate=first_trip["output"],
            projection=reread.projection,
            output=output2,
            definitions=definitions,
            binding=SIB.BINDING_MAIN,
            substrate_role=SubstrateRole.published_representation,
            substrate_kind=ArtifactKind.canonical,
            substrate_state=ArtifactState.published,
        )
        assert output2.is_file()
        # 第二趟不该再删任何行（没有新的 stale）
        assert outcome2.plan.stale_deleted == (), (
            f"第二趟又删了行 {outcome2.plan.stale_deleted} ⇒ 收敛不收敛（反复删）"
        )
        assert outcome2.plan.row_deletion is None
        # 行数与第一趟产物一致（no-op）
        assert _physical_rows(output2.read_bytes(), world["sheet_part"]) == _physical_rows(
            first_trip["bytes"], world["sheet_part"]
        )

    def test_the_second_trip_would_have_failed_without_the_rebinding(
        self, world: dict[str, Any], first_trip: dict[str, Any], monkeypatch: Any
    ) -> None:
        """🔴 变异反证：把第一趟产物里的 `GT_FOOTER_ROW_*` **还原成删行前的值**
        ⇒ 第二趟必须抛 `FooterAnchorDriftError`。

        没有这条，判据④ 可能只是因为「footer 门在第二趟根本没跑」而绿。
        """
        entries = G2._entries(first_trip["bytes"])
        gt_part = next(
            (n for n in entries if "_GT_SYNC" in n or "gt_sync" in n.lower()), None
        )
        if gt_part is None:
            # 找不到就从 runtime binding 反查：它必然落在某个 sheet part 上
            with zipfile.ZipFile(io.BytesIO(first_trip["bytes"])) as zf:
                pairs = X.read_runtime_binding_pairs(zf)
            gt_part = next(
                (
                    n
                    for n in entries
                    if n.startswith("xl/worksheets/")
                    and any(
                        k.encode("utf-8") in entries[n]
                        for k in pairs
                        if k.startswith("GT_FOOTER_ROW")
                    )
                ),
                None,
            )
        assert gt_part is not None, (
            f"定位不到 `_GT_SYNC` 部件，实测条目 {sorted(entries)[:12]}"
        )

        with zipfile.ZipFile(io.BytesIO(first_trip["bytes"])) as zf:
            pairs = X.read_runtime_binding_pairs(zf)
        footer_keys = {k: v for k, v in pairs.items() if k.startswith("GT_FOOTER_ROW")}
        assert footer_keys, f"没有 GT_FOOTER_ROW* 键，实测 {sorted(pairs)[:12]}"

        xml = entries[gt_part].decode("utf-8")
        mutated = xml
        for key, value in footer_keys.items():
            raw = str(value).strip()
            if not raw.isdigit():
                continue
            # 把删行后的值 +1 还原成删行前的值
            mutated = mutated.replace(f">{raw}<", f">{int(raw) + 1}<")
        assert mutated != xml, "没能改动任何 footer 冻结值 ⇒ 本条判据空转"
        entries[gt_part] = mutated.encode("utf-8")
        tampered = world["workdir"] / "trip2-tampered.xlsx"
        tampered.write_bytes(M._write_entries(entries))

        definitions = _definitions(
            first_trip["contract"], SIB.BINDING_MAIN, tampered.read_bytes()
        )
        # 🔴 `extract_projection` 放在 `raises` **之外**：把两个调用一起裹进去的话，
        #    哪一个抛都算通过 —— 而本条要证的是**物化**那一层的 footer 门在叫。
        reread = X.extract_projection(
            artifact=tampered,
            definitions=definitions,
            binding=SIB.BINDING_MAIN,
            substrate_role=SubstrateRole.published_representation,
            artifact_kind=ArtifactKind.canonical,
            artifact_state=ArtifactState.published,
        )
        with pytest.raises(M.FooterAnchorDriftError) as err:
            M.materialize_projection(
                substrate=tampered,
                projection=reread.projection,
                output=world["workdir"] / "trip2-tampered-out.xlsx",
                definitions=definitions,
                binding=SIB.BINDING_MAIN,
                substrate_role=SubstrateRole.published_representation,
                substrate_kind=ArtifactKind.canonical,
                substrate_state=ArtifactState.published,
            )
        assert "footer" in str(err.value).lower() or "GT_FOOTER_ROW" in str(err.value), (
            f"抛的是 FooterAnchorDriftError 但文案不像 footer 冻结值漂移：{err.value}"
        )


def test_http_hop_is_not_covered_here() -> None:
    """🔴 如实登记范围：HTTP「点在线编辑」那一跳**没有**被本文件覆盖。

    它需要 `start-dev.bat` 起后端 9980 + 前端 3030 + OnlyOffice 容器。本文件验的是
    materialize 这一层的真实链路（落盘 + 三道门 + 反读），判据④ 已覆盖那一跳最常见的
    故障形态（第一次删成功、第二次点开 500）。

    写成判据而不是注释，是为了让「离线四条全绿」不被读成「端到端已验收」。
    """
    assert True, "本条只承载范围声明"
