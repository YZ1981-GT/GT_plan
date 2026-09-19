# -*- coding: utf-8 -*-
"""Task 19 + 20 —— 验证侧按**声明**归一化（Property 21 / 22 / 23）。

spec: excel-workbook-wide-row-change-propagation / Wave 4 Task 19, 20
Requirements: 5.1, 5.2, 5.3, 5.4

═══ 这一层判的是什么 ═══

传播会改引用侧 sheet 的字节。而那些 sheet 落在 `excel_extract` 的
**`other_sheet_parts`** 桶里，原本是**逐字节**比对的 ⇒ 传播必然被判成漂移。

所以要么放宽比对，要么按声明归一化。本 spec 选后者，而两者的差别是**判据的全部意义**：

| 做法 | 实测 == 声明 | 实测 != 声明 | 传播之外的改动 |
|---|---|---|---|
| 放宽（跳过该桶） | 过 | **过**（错） | **过**（错） |
| 整体反向 remap | 过 | 过（错） | 形态像位移的**过**（错） |
| **逐条逆替换声明**（本实现） | 过 | **红** | **红** |

🔴 关键在「按**声明**归一化，不按**观测**」：事后从 diff 推断位移量等于让被检查对象
自己声明自己合法 —— design.md 明确拒绝的方案。
"""

from __future__ import annotations

import io
import os
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

from app.services.excel_structure_fingerprint import (  # noqa: E402
    _normalise_part,
    _parse_workbook_xml,
)
from app.services.workpaper_sync import excel_workbook_row_change as N1  # noqa: E402

TEMPLATE_ROOT = _BACKEND / "wp_templates"
D2_REL = "D/D2-1至D2-4  应收账款- 审定表明细表（Leap-常规程序）.xlsx"
D2_SHEET = "明细表D2-2"
D2_REGION = (13, 25)
D2_AT, D2_COUNT, D2_STYLE_FROM = 15, 1, 14


@pytest.fixture(scope="module")
def d2_insert() -> tuple[bytes, bytes, dict[str, str], N1.WorkbookRowChangePlan]:
    """真实 D2 上插一行，返回 `(改前, 改后, sheet_parts, 计划)`。"""
    path = TEMPLATE_ROOT / D2_REL
    if not path.is_file():  # pragma: no cover
        pytest.skip(f"D2 权威模板不在磁盘上：{D2_REL}")
    data = path.read_bytes()
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        sheets, defined = _parse_workbook_xml(zf)
        parts = {s["name"]: _normalise_part(s["rel_target"]) for s in sheets}
        scan = N1.scan_reference_carriers(
            zf, target_sheet=D2_SHEET, sheet_parts=parts, defined_names=defined
        )
    plan = N1.build_insert_plan(
        scan,
        managed_sheet_name=D2_SHEET,
        managed_sheet_part=parts[D2_SHEET],
        at=D2_AT,
        count=D2_COUNT,
        style_from=D2_STYLE_FROM,
        region_first_row=D2_REGION[0],
        region_last_row=D2_REGION[1],
    )
    produced, _report = N1.apply_workbook_row_change(data, plan, sheet_parts=parts)
    return data, produced, parts, plan


def _text(data: bytes, part: str) -> str:
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        return zf.read(part).decode("utf-8")


def _reference_side_parts(plan: N1.WorkbookRowChangePlan) -> list[str]:
    return sorted(
        {
            e.part
            for e in plan.propagations
            if e.part.startswith("xl/worksheets/") and e.part != plan.managed_sheet_part
        }
    )


# ═══════════════════════════════════════════════════════════════════════════
# Property 21 —— 按声明归一化后逐字节相等（Requirement 5.1）
# ═══════════════════════════════════════════════════════════════════════════


class TestProperty21NormaliseByDeclaration:
    """逆归一化后引用侧 sheet 必须与改前**逐字节**相等。"""

    def test_reference_side_parts_are_non_empty(
        self,
        d2_insert: tuple[bytes, bytes, dict[str, str], N1.WorkbookRowChangePlan],
    ) -> None:
        """分母：D2 上必须真有引用侧 sheet 被改，否则整个文件空转。"""
        _before, _after, _parts, plan = d2_insert
        refs = _reference_side_parts(plan)
        assert len(refs) >= 3, refs

    def test_normalised_after_equals_before_byte_for_byte(
        self,
        d2_insert: tuple[bytes, bytes, dict[str, str], N1.WorkbookRowChangePlan],
    ) -> None:
        """🔴 核心判据：逐条逆替换声明之后，与改前**一个字节都不差**。"""
        before, after, _parts, plan = d2_insert
        checked = 0
        for part in _reference_side_parts(plan):
            N1.assert_propagation_declared_exactly(
                _text(before, part), _text(after, part), plan, part=part
            )
            checked += 1
        assert checked >= 3, f"只核了 {checked} 张引用侧 sheet"

    def test_every_declared_entry_is_found_in_the_product(
        self,
        d2_insert: tuple[bytes, bytes, dict[str, str], N1.WorkbookRowChangePlan],
    ) -> None:
        """🔴 声明的每一条都必须在产物里找到 —— 否则「声明了但没做」会静默过。

        `normalise_propagated_part` 返回的 `reverted` 与该 part 的声明数必须相等。
        """
        _before, after, _parts, plan = d2_insert
        for part in _reference_side_parts(plan):
            declared = len([e for e in plan.propagations if e.part == part])
            _out, reverted = N1.normalise_propagated_part(
                _text(after, part), plan, part=part
            )
            assert reverted == declared, (
                f"{part}：声明 {declared} 条，产物里只找到 {reverted} 条"
            )

    def test_untouched_sheets_are_not_normalised(
        self,
        d2_insert: tuple[bytes, bytes, dict[str, str], N1.WorkbookRowChangePlan],
    ) -> None:
        """未被传播触及的 sheet 不进归一化 —— 归一化只作用于声明过的 part。"""
        before, _after, parts, plan = d2_insert
        touched = set(_reference_side_parts(plan)) | {plan.managed_sheet_part}
        untouched = [p for p in parts.values() if p not in touched]
        assert untouched, "所有 sheet 都被传播了 ⇒ 本条空转"
        for part in untouched[:4]:
            text = _text(before, part)
            out, reverted = N1.normalise_propagated_part(text, plan, part=part)
            assert out == text and reverted == 0


# ═══════════════════════════════════════════════════════════════════════════
# Property 22 —— 实测 != 声明时判漂移（Requirement 5.2）
# ═══════════════════════════════════════════════════════════════════════════


class TestProperty22DriftIsDetected:
    """🔴 三类「实测与声明不符」都必须打红。缺任一类都留下一条静默通道。"""

    def test_extra_undeclared_change_is_drift(
        self,
        d2_insert: tuple[bytes, bytes, dict[str, str], N1.WorkbookRowChangePlan],
    ) -> None:
        """🔴 **变异**：产物里多改一处没进声明的引用 ⇒ 必须打红。

        这条是「逐条逆替换」优于「整体反向 remap」的**唯一可执行证据**：整体 remap 会
        把这处未声明的改动一并还原掉从而放过它。
        """
        before, after, _parts, plan = d2_insert
        part = _reference_side_parts(plan)[0]
        before_text = _text(before, part)
        after_text = _text(after, part)
        # 找一处**没被声明**的引用，偷偷改掉它的行号
        declared_after = {e.ref_after for e in plan.propagations if e.part == part}
        victim = None
        for ref in N1.iter_qualified_references(N1._unescape(after_text)):
            if ref.kind != "sheet" or ref.raw in declared_after:
                continue
            if ref.sheet_name == D2_SHEET:
                continue  # 指向受管 sheet 的都已声明
            victim = ref
            break
        if victim is None:  # pragma: no cover - D2 上实测有
            pytest.skip("这张 sheet 上没有未声明的跨 sheet 引用可供变异")
        tampered = after_text.replace(victim.raw, victim.raw.replace("!", "!") + "", 1)
        # 真正的变异：把该引用的行号 +1
        import re as _re

        bumped = _re.sub(
            r"(\d+)$", lambda m: str(int(m.group(1)) + 1), victim.token, count=1
        )
        tampered = after_text.replace(
            victim.raw, victim.raw.replace(victim.token, bumped), 1
        )
        assert tampered != after_text, "变异没生效 ⇒ 本条空转"
        with pytest.raises(N1.PropagationDriftError, match="未声明"):
            N1.assert_propagation_declared_exactly(
                before_text, tampered, plan, part=part
            )

    def test_missing_declared_change_is_drift(
        self,
        d2_insert: tuple[bytes, bytes, dict[str, str], N1.WorkbookRowChangePlan],
    ) -> None:
        """🔴 声明了但产物里没做 ⇒ 打红（`reverted != declared`）。"""
        before, _after, _parts, plan = d2_insert
        part = _reference_side_parts(plan)[0]
        # 拿**改前**文本当「产物」：声明的改动一条都没做
        with pytest.raises(N1.PropagationDriftError, match="只找到"):
            N1.assert_propagation_declared_exactly(
                _text(before, part), _text(before, part), plan, part=part
            )

    def test_non_shift_change_is_drift(
        self,
        d2_insert: tuple[bytes, bytes, dict[str, str], N1.WorkbookRowChangePlan],
    ) -> None:
        """🔴 非位移性改动（改了个**值**）⇒ 归一化碰不到它 ⇒ 打红。

        这条钉住 Requirement 5.3 的另一半：归一化只动行号，`v` 之类的内容照旧参与比对。
        """
        before, after, _parts, plan = d2_insert
        part = _reference_side_parts(plan)[0]
        after_text = _text(after, part)
        import re as _re

        m = _re.search(r"<v>([^<]+)</v>", after_text)
        assert m, "这张 sheet 上没有 <v> 可供变异"
        tampered = (
            after_text[: m.start(1)] + "__TAMPERED__" + after_text[m.end(1) :]
        )
        with pytest.raises(N1.PropagationDriftError, match="未声明"):
            N1.assert_propagation_declared_exactly(
                _text(before, part), tampered, plan, part=part
            )

    def test_style_only_change_is_drift(
        self,
        d2_insert: tuple[bytes, bytes, dict[str, str], N1.WorkbookRowChangePlan],
    ) -> None:
        """样式（`s=`）改动同样打红 —— 传播不碰样式。"""
        before, after, _parts, plan = d2_insert
        part = _reference_side_parts(plan)[0]
        after_text = _text(after, part)
        import re as _re

        m = _re.search(r'\bs="(\d+)"', after_text)
        if m is None:  # pragma: no cover
            pytest.skip("这张 sheet 上没有 s= 属性")
        tampered = (
            after_text[: m.start(1)]
            + str(int(m.group(1)) + 7)
            + after_text[m.end(1) :]
        )
        with pytest.raises(N1.PropagationDriftError):
            N1.assert_propagation_declared_exactly(
                _text(before, part), tampered, plan, part=part
            )

    def test_detector_is_not_vacuous(
        self,
        d2_insert: tuple[bytes, bytes, dict[str, str], N1.WorkbookRowChangePlan],
    ) -> None:
        """🔴 反面自检：**未**变异时必须**不**抛。

        上面四条 `pytest.raises` 在「检测器恒抛」时也会绿。本条是它们的分母。
        """
        before, after, _parts, plan = d2_insert
        for part in _reference_side_parts(plan):
            N1.assert_propagation_declared_exactly(
                _text(before, part), _text(after, part), plan, part=part
            )

    def test_occurrence_count_not_distinct_text_count(
        self,
        d2_insert: tuple[bytes, bytes, dict[str, str], N1.WorkbookRowChangePlan],
    ) -> None:
        """🔴 计量单位必须是**出现次数**，不是「不同文本段数」。

        ═══ 这条判据来自一次实测打红 ═══

        `normalise_propagated_part` 首版按条目逐条 `replace` 并 `reverted += 1`，
        在 D2 上 **18 条声明只数出 4** —— 因为 `SUMIF('明细表D2-2'!$AI$13:$AI$25,…)`
        这段文本出现在 18 个不同单元格里，而 `str.replace()` 一次就把全部出现换掉了，
        余下 14 条条目再也找不到可替换的文本。

        改成按出现次数计量后判据**更强**：不只要求「这段文本出现过」，还要求出现的
        **次数**恰好等于声明数。本条把「同一段文本对应多条条目」这个真实形态钉住 ——
        没有它，实现退回按条目计量时只会在 D2 上红，而在「每条文本都唯一」的合成样本上
        依然绿。
        """
        _before, _after, _parts, plan = d2_insert
        part = _reference_side_parts(plan)[0]
        entries = [e for e in plan.propagations if e.part == part]
        distinct_texts = {(e.ref_after, e.ref_before) for e in entries}
        assert len(entries) > len(distinct_texts), (
            f"{part} 上条目数 {len(entries)} 未超过不同文本数 {len(distinct_texts)}"
            " ⇒ 本条空转，换一张有重复文本的 sheet"
        )
        assert len(entries) == 18 and len(distinct_texts) == 4, (
            f"D2 实测冻结值变了：条目 {len(entries)} / 不同文本 {len(distinct_texts)}"
        )


# ═══════════════════════════════════════════════════════════════════════════
# Property 23 —— 接入真实验证入口（Requirement 5.4）
# ═══════════════════════════════════════════════════════════════════════════


class TestProperty23WiredIntoRealVerifier:
    """🔴 归一化必须在**真实**验证入口 `verify_unmanaged_regions` 上生效。

    只测 N1 的 helper 不够 —— 那只证明「helper 会算」，不证明「验证真的用了它」。
    没有本类，`propagation` 参数可能挂在签名上却从未被读到（死参数），而所有 helper
    判据依然全绿。
    """

    def test_propagation_param_reaches_the_digest(self) -> None:
        """AST 级：`unmanaged_region_digest` 里 `propagation` 必须被真的用到。"""
        import ast
        import inspect
        import textwrap

        from app.services.workpaper_sync import excel_extract as EX

        source = textwrap.dedent(inspect.getsource(EX.unmanaged_region_digest))
        tree = ast.parse(source)
        names = {
            node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
        }
        assert "propagation" in names, (
            "`propagation` 出现在签名里但函数体从未读它 —— 死参数，"
            "归一化实际没接上"
        )
        # 且必须走 N1 的单一真源，不自己写一份逆替换
        normaliser = textwrap.dedent(
            inspect.getsource(EX._propagation_normalised_digest)
        )
        assert "normalise_propagated_part" in normaliser, (
            "验证侧自己写了一份逆替换逻辑 —— 必须复用 N1 的单一真源，"
            "抄第二份必然与执行侧漂移"
        )

    def test_verify_passes_propagation_to_after_side_only(self) -> None:
        """🔴 `propagation` 只能给 after 侧 —— 两侧都归一化等于什么都没归一化。

        与 `row_shift` 同一条纪律。用 AST 数 `unmanaged_region_digest` 的两次调用：
        带 `propagation=` 的必须**恰好一次**。
        """
        import ast
        import inspect
        import textwrap

        from app.services.workpaper_sync import excel_extract as EX

        source = textwrap.dedent(inspect.getsource(EX.verify_unmanaged_regions))
        tree = ast.parse(source)
        with_propagation = 0
        total_calls = 0
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            if name != "unmanaged_region_digest":
                continue
            total_calls += 1
            if any(kw.arg == "propagation" for kw in node.keywords):
                with_propagation += 1
        assert total_calls == 2, f"预期 before/after 两次调用，实得 {total_calls}"
        assert with_propagation == 1, (
            f"带 propagation= 的调用有 {with_propagation} 处 —— 必须恰好 1 处（after 侧）"
        )

    def test_digest_normalises_reference_side_part(
        self,
        d2_insert: tuple[bytes, bytes, dict[str, str], N1.WorkbookRowChangePlan],
        tmp_path: Path,
    ) -> None:
        """端到端：同一张引用侧 sheet，带 `propagation` 的 digest 与改前相等。

        判据形态：直接调 `_propagation_normalised_digest`（真实验证路径里算 digest 的
        那个函数），比对「改后归一化」与「改前逐字节」两个 digest。
        """
        import hashlib

        from app.services.workpaper_sync.excel_extract import (
            _propagation_normalised_digest,
        )
        from app.services.workpaper_sync.limits import load_limits

        before, after, _parts, plan = d2_insert
        lim = load_limits()
        checked = 0
        for part in _reference_side_parts(plan):
            before_digest = hashlib.sha256(
                _text(before, part).encode("utf-8")
            ).hexdigest()
            with zipfile.ZipFile(io.BytesIO(after)) as zf:
                after_normalised = _propagation_normalised_digest(
                    zf, part, plan=plan, limits=lim
                )
            assert after_normalised == before_digest, (
                f"{part}：归一化后的 digest 与改前不等 ⇒ 验证会判漂移"
            )
            checked += 1
        assert checked >= 3, f"只核了 {checked} 张"

    def test_digest_without_propagation_would_flag_drift(
        self,
        d2_insert: tuple[bytes, bytes, dict[str, str], N1.WorkbookRowChangePlan],
    ) -> None:
        """🔴 反面对照：**不**给 `propagation` 时，同一张 sheet 必须判不等。

        这条证明「归一化确实是必需的」而不是「反正都相等」。没有它，
        `_propagation_normalised_digest` 即便是个恒等函数也能让上一条绿。
        """
        import hashlib

        from app.services.workpaper_sync.excel_extract import _part_digest
        from app.services.workpaper_sync.limits import load_limits

        before, after, _parts, plan = d2_insert
        lim = load_limits()
        differing = 0
        for part in _reference_side_parts(plan):
            with zipfile.ZipFile(io.BytesIO(before)) as zb, zipfile.ZipFile(
                io.BytesIO(after)
            ) as za:
                if _part_digest(zb, part, limits=lim) != _part_digest(
                    za, part, limits=lim
                ):
                    differing += 1
        assert differing == len(_reference_side_parts(plan)) >= 3, (
            f"只有 {differing} 张引用侧 sheet 的原始字节不同 ⇒ "
            "要么传播没生效，要么归一化判据本来就不需要"
        )
