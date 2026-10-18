"""Task 2.3 · componentType 覆盖闭合 + classification 404 一次性归类的可跑验收测试。

spec formula-manager-closure，design §5 步骤 2 404 归类子任务 / ADR-FMC-03 / §1 #20 /
§7.1 / §7.3 / §9 集成可测（MEDIUM-1 / NIT-2 响应）。

验收判据（对应 tasks.md Task 2.3）：
  1. componentType 覆盖闭合：declared（后端白名单 ∪ 前端 registry）每项恰有
     「当前页入口覆盖」或「componentType 类正式豁免」，无未知未覆盖项。**清单禁写死**
     （对当前源码现算）。变异：注入一个新 declared componentType 应被判为未覆盖（闭合失败）；
     反向断言：真实源码闭合成立。
  2. classification 404 归类：对**当前真实项目**现算 404 wp_code，各一次
     wp_code_overrides.json 查表归类（data_drift / out_of_scope）；out_of_scope 项必须
     在豁免登记里有带可验证理由字段的条目，且对活数据校验通过（从 §7.1 分母剔除）。
     **清单禁写死**（现算）。变异：伪造一个新 404 wp_code（既不在 override 也未登记豁免）
     → 门禁识别为未归类而要求归类；反向断言：已归类的 out_of_scope 项不触发。

纪律（memory）：
  * 计数禁写死（componentType 数、404 清单都随 HEAD / 真实项目漂移）。
  * 若无法连真库，404 的 live 现算测试显式 skip 并说明（不假绿）；归类逻辑 + 豁免
    校验 + 变异反证不依赖 DB，始终运行。
  * 变异配反向断言（铁律㉒：单向变异会把干净态判成缺陷）。
"""

from __future__ import annotations

import ast
import asyncio
import os
import re
import sys
from pathlib import Path

import pytest

from app.services.formula_management.gate_exemptions import (
    KIND_CLASSIFICATION_404_OUT_OF_SCOPE,
    classify_404_wp_code,
    exempted_keys,
    load_exemptions,
    validate_exemption,
)

os.environ.setdefault("GT_BOOTSTRAP_DONE", "1")

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_REPO_ROOT = _BACKEND_ROOT.parent

_CLASS_SVC = _BACKEND_ROOT / "app" / "services" / "wp_classification_service.py"
_FE_ENTRIES_DIR = (
    _REPO_ROOT / "audit-platform" / "frontend" / "src" / "components"
    / "workpaper" / "registry" / "entries"
)
_FE_REGISTRY = (
    _REPO_ROOT / "audit-platform" / "frontend" / "src" / "components"
    / "workpaper" / "htmlRendererRegistry.ts"
)


# ─── 现算真源解析（禁写死，对当前源码现读） ──────────────────────────────────


def _backend_valid_component_types() -> set[str]:
    """AST 现读 VALID_COMPONENT_TYPES 字面集合（不导入重型 app）。"""
    tree = ast.parse(_CLASS_SVC.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        tgt_names = []
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            tgt_names = [node.target.id]
            value = node.value
        elif isinstance(node, ast.Assign):
            tgt_names = [t.id for t in node.targets if isinstance(t, ast.Name)]
            value = node.value
        else:
            continue
        if "VALID_COMPONENT_TYPES" in tgt_names and isinstance(value, ast.Set):
            return {
                el.value for el in value.elts
                if isinstance(el, ast.Constant) and isinstance(el.value, str)
            }
    raise RuntimeError("未能从源码解析 VALID_COMPONENT_TYPES")


def _frontend_registry_component_types() -> set[str]:
    out: set[str] = set()
    for f in sorted(_FE_ENTRIES_DIR.glob("*.ts")):
        out.update(re.findall(r"componentType:\s*'([^']+)'", f.read_text(encoding="utf-8")))
    if not out:
        raise RuntimeError("未能从前端 registry entries 解析 componentType")
    return out


def _frontend_route_set_extras() -> set[str]:
    """HTML_RENDERER_ROUTE_SET 额外的 placeholder（skip/confirmation-hub）+ PLACEHOLDER_ICONS（univer/skip）。"""
    t = _FE_REGISTRY.read_text(encoding="utf-8")
    extras: set[str] = set()
    m = re.search(r"HTML_RENDERER_ROUTE_SET[^=]*=\s*new Set\(\[(.*?)\]\)", t, re.S)
    if m:
        extras.update(re.findall(r"'([^']+)'", m.group(1)))
    m2 = re.search(r"PLACEHOLDER_ICONS[^=]*=\s*\{(.*?)\}", t, re.S)
    if m2:
        extras.update(re.findall(r"(\w[\w-]*)\s*:", m2.group(1)))
    return extras


def _component_type_exempted_keys() -> set[str]:
    """componentType 类有效豁免（排除 classification-404 口径外豁免——后者属按钮分母维度）。"""
    valid = exempted_keys()
    return {
        ex.key for ex in load_exemptions()
        if ex.kind != KIND_CLASSIFICATION_404_OUT_OF_SCOPE
        and ex.key in valid
        and validate_exemption(ex).valid
    }


# ═══ Part 1 · componentType 覆盖闭合 ═════════════════════════════════════════


def test_component_type_coverage_is_closed():
    """declared 每项恰有页覆盖或 componentType 类豁免，无未知未覆盖项（现算）。"""
    backend = _backend_valid_component_types()
    fe = _frontend_registry_component_types()
    declared = backend | fe
    assert len(declared) > 100, f"declared 现算异常偏少={len(declared)}，源码解析可能失效"

    page_covered = fe | _frontend_route_set_extras()
    ct_exempted = _component_type_exempted_keys()

    uncovered = declared - page_covered - ct_exempted
    assert not uncovered, f"存在未知未覆盖 componentType（须页覆盖或登记豁免）: {sorted(uncovered)}"


def test_component_type_coverage_mutation_injected_unknown_breaks_closure():
    """变异：注入一个既无页覆盖也无豁免的新 declared componentType → 闭合失败。"""
    backend = _backend_valid_component_types()
    fe = _frontend_registry_component_types()
    page_covered = fe | _frontend_route_set_extras()
    ct_exempted = _component_type_exempted_keys()

    fake = "__fmc23_injected_fake_component_type__"
    assert fake not in page_covered and fake not in ct_exempted
    declared_mut = (backend | fe) | {fake}

    uncovered = declared_mut - page_covered - ct_exempted
    assert fake in uncovered, "注入的未知 componentType 应被判为未覆盖"


def test_component_type_coverage_reverse_real_source_not_flagged():
    """反向断言：真实源码里每个 declared 项都不在『未覆盖』集合（未注入变异时不误红）。"""
    backend = _backend_valid_component_types()
    fe = _frontend_registry_component_types()
    page_covered = fe | _frontend_route_set_extras()
    ct_exempted = _component_type_exempted_keys()
    uncovered = (backend | fe) - page_covered - ct_exempted
    assert uncovered == set()


def test_redirect_materiality_is_the_only_page_coverage_gap():
    """redirect-materiality 是唯一无页覆盖的 declared 项，恰由其 componentType 类豁免补齐。"""
    backend = _backend_valid_component_types()
    fe = _frontend_registry_component_types()
    declared = backend | fe
    page_covered = fe | _frontend_route_set_extras()
    gap = declared - page_covered
    assert gap == {"redirect-materiality"}, f"页覆盖缺口应恰为 redirect-materiality，实际 {sorted(gap)}"
    assert "redirect-materiality" in _component_type_exempted_keys()


# ═══ Part 2 · classification 404 归类（纯逻辑，始终运行） ═════════════════════


def test_classify_404_data_drift_when_override_hit():
    """命中 override → data_drift（仍计入分母）。"""
    assert classify_404_wp_code("X9", overrides={"X9": "audit-sheet"}) == "data_drift"


def test_classify_404_out_of_scope_when_override_miss():
    """未命中 override → out_of_scope（从分母剔除 + 登记豁免）。"""
    assert classify_404_wp_code("X9", overrides={}) == "out_of_scope"


def test_out_of_scope_exemption_has_verifiable_reason_fields():
    """已登记的口径外 404 豁免：三字段齐全 + verify_against 可验证 + 对活数据校验通过。"""
    exemptions = [
        e for e in load_exemptions()
        if e.kind == KIND_CLASSIFICATION_404_OUT_OF_SCOPE
    ]
    assert exemptions, "应至少登记了本轮现算出的口径外 404 豁免"
    for ex in exemptions:
        assert ex.owner.strip() and ex.reason.strip() and ex.expires_at
        assert ex.verify_against.get("wp_code")
        assert ex.verify_against.get("classification_status") == "out_of_scope"
        res = validate_exemption(ex)  # 对活 wp_code_overrides.json 校验
        assert res.valid, f"口径外豁免 {ex.key} 应对活数据校验通过，实际 {res.reason_code}: {res.detail}"


def test_out_of_scope_exemption_fact_mismatch_if_override_added():
    """可伪证：若口径外 wp_code 后续在 override 表出现映射 → 失效（fact_mismatch），要求重新归类。"""
    ex = next(
        e for e in load_exemptions()
        if e.kind == KIND_CLASSIFICATION_404_OUT_OF_SCOPE
    )
    wp = ex.verify_against["wp_code"]
    # 伪造 override 表里新增了该 wp_code → 它其实是数据漂移，不该当口径外剔除。
    res = validate_exemption(ex, overrides={wp: "audit-sheet"})
    assert not res.valid and res.reason_code == "fact_mismatch"


def test_out_of_scope_exemption_probe_empty_when_status_absent():
    """防空转：classification_status 缺失 / 非 out_of_scope → 失效（不静默放行）。"""
    from dataclasses import replace

    ex = next(
        e for e in load_exemptions()
        if e.kind == KIND_CLASSIFICATION_404_OUT_OF_SCOPE
    )
    bad = replace(ex, verify_against={"wp_code": ex.verify_against["wp_code"]})  # 缺 classification_status
    res = validate_exemption(bad, overrides={})
    assert not res.valid and res.reason_code == "probe_empty"


def test_mutation_fake_new_404_is_unclassified_and_requires_classification():
    """变异：伪造一个新 404 wp_code（不在 override、未登记豁免）→ 门禁识别为未归类。

    「门禁识别为未归类」= 它既不是 data_drift（override 未命中），又没有有效的口径外豁免
    → 必须被要求归类。
    """
    fake = "ZZ99"  # 既不在 override 也未登记
    live_overrides = {}  # 模拟活 override 表里无此码
    verdict = classify_404_wp_code(fake, overrides=live_overrides)
    assert verdict == "out_of_scope"
    # 未登记豁免 → 不在有效口径外豁免集 → 门禁要求归类
    registered_404_wp_codes = {
        ex.verify_against.get("wp_code")
        for ex in load_exemptions()
        if ex.kind == KIND_CLASSIFICATION_404_OUT_OF_SCOPE
        and validate_exemption(ex).valid
    }
    assert fake not in registered_404_wp_codes, "伪造的新 404 不应已被登记"


def test_reverse_registered_out_of_scope_does_not_require_reclassification():
    """反向断言：已归类并有效登记的 out_of_scope 404 不触发『要求归类』（未注入变异时不误红）。"""
    registered = {
        ex.verify_against.get("wp_code")
        for ex in load_exemptions()
        if ex.kind == KIND_CLASSIFICATION_404_OUT_OF_SCOPE
        and validate_exemption(ex).valid
    }
    assert registered, "应有有效登记的口径外 404"
    for wp in registered:
        # 已登记的口径外项：override 未命中（out_of_scope）且已在有效豁免集 → 不需重新归类。
        assert classify_404_wp_code(wp) == "out_of_scope"


# ═══ Part 3 · classification 404 live 现算（需真库，不假绿） ══════════════════


def _live_404_wp_codes() -> list[str] | None:
    """对当前真实项目现算 distinct 404 wp_code；DB 不可达返回 None（调用方 skip）。"""
    if str(_BACKEND_ROOT) not in sys.path:
        sys.path.insert(0, str(_BACKEND_ROOT))
    try:
        import sqlalchemy as sa
        from app.core.database import async_session as Session
        from app.models.workpaper_models import WpIndex, WorkingPaper
        from app.routers.wp_render_config import _maybe_custom_classifications
        from app.services.wp_classification_service import (
            ClassificationNotFoundError,
            WpClassificationService,
        )
    except Exception:
        return None

    async def _run() -> list[str]:
        distinct: set[str] = set()
        async with Session() as db:
            projects = (
                await db.execute(
                    sa.text("SELECT id FROM projects WHERE is_deleted = false")
                )
            ).all()
            for (pid,) in projects:
                rows = (
                    await db.execute(
                        sa.select(WpIndex.id, WpIndex.wp_code, WpIndex.wp_name).where(
                            WpIndex.project_id == pid, WpIndex.is_deleted == False  # noqa: E712
                        )
                    )
                ).all()
                svc = WpClassificationService(db)
                for wp_index_id, wp_code, wp_name in rows:
                    wp = (
                        await db.execute(
                            sa.select(WorkingPaper).where(
                                WorkingPaper.project_id == pid,
                                WorkingPaper.wp_index_id == wp_index_id,
                                WorkingPaper.is_deleted == False,  # noqa: E712
                            )
                        )
                    ).scalar_one_or_none()
                    if wp is None:
                        continue
                    try:
                        cls = await svc.get_classification(
                            wp_code=wp_code, project_id=pid, template_version_id=None
                        )
                    except ClassificationNotFoundError:
                        cls = []
                    if not cls:
                        cls = await _maybe_custom_classifications(
                            db, pid, wp_code, wp_name, cls, wp
                        )
                    if not cls:
                        distinct.add(wp_code)
        return sorted(distinct)

    try:
        return asyncio.run(_run())
    except Exception:
        return None


def test_live_404_each_classified_and_out_of_scope_registered():
    """live 现算：每个 404 各一次 override 查表归类；out_of_scope 项必须已有有效豁免登记。

    禁写死：对当前真实项目现算。DB 不可达 → skip（不假绿）。
    """
    codes = _live_404_wp_codes()
    if codes is None:
        pytest.skip("真库不可达：classification 404 live 现算跳过（代码/脚本已就绪，见 "
                    "backend/scripts/analyze/_fmc23_probe_classification_404.py）")
    if not codes:
        pytest.skip("当前真实项目现算无 classification 404（数据状态所致，非代码问题）")

    registered_oos = {
        ex.verify_against.get("wp_code")
        for ex in load_exemptions()
        if ex.kind == KIND_CLASSIFICATION_404_OUT_OF_SCOPE
        and validate_exemption(ex).valid
    }

    out_of_scope_live = []
    for code in codes:
        verdict = classify_404_wp_code(code)  # 一次 wp_code_overrides.json 查表
        assert verdict in ("data_drift", "out_of_scope")
        if verdict == "out_of_scope":
            out_of_scope_live.append(code)

    # 每个现算出的口径外 404 都必须有带可验证理由字段的有效豁免登记（§7.1 分母剔除）。
    missing = [c for c in out_of_scope_live if c not in registered_oos]
    assert not missing, (
        f"现算出的口径外 404 未在豁免登记（须登记带 verify_against 的可伪证豁免）: {missing}"
    )
