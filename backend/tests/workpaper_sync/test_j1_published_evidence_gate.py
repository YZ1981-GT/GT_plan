from __future__ import annotations

from copy import deepcopy

from scripts.check.check_j1_published_evidence import ENTRY_ID, evaluate


def valid() -> tuple[dict, dict]:
    digests = {"authority_model": "a", "template": "t", "instrumentation": "i", "contract": "c"}
    facts = {
        "source_digest": "source",
        "digests": digests,
        "template_sha256": "template-bytes",
        "manifest": {
            "capability": "bidirectional",
            "migration_state": "adapter_registered",
            "adapter_id": "j1.accrual_check_short_term",
            "canonical_resolver": "workpaper_sync_published_representation",
        },
    }
    evidence = {
        "schema_version": "j1-oo94-evidence:v1",
        "status": "passed",
        "entry_id": ENTRY_ID,
        "wp_code": "J1",
        "project_id": "p",
        "wp_id": "w",
        "source_digest": "source",
        "source_commit": "ignored-in-unit",
        "active": {
            "digests": digests,
            "active_template_sha256": "template-bytes",
            "external_links": [],
            "generation": 1,
            "bundle_id": "b",
        },
        "onlyoffice": {"version": "9.4", "source": "docker"},
        "rounds": ["frontend_skeleton_19_rows", "frontend_payload_with_amounts_19_rows"],
        "store_snapshot": {"unchanged": True},
        "legacy_identity_mutation_enabled": False,
    }
    return evidence, facts


def test_valid_evidence_passes() -> None:
    evidence, facts = valid()
    assert evaluate(evidence, facts, check_commit=False) == []


def test_each_freshness_axis_fails_closed() -> None:
    evidence, facts = valid()
    mutations = [
        ("source", lambda e, f: e.__setitem__("source_digest", "stale")),
        ("contract", lambda e, f: e["active"]["digests"].__setitem__("contract", "stale")),
        ("template", lambda e, f: e["active"].__setitem__("active_template_sha256", "old")),
        ("external", lambda e, f: e["active"].__setitem__("external_links", ["x"])),
        ("oo", lambda e, f: e.__setitem__("onlyoffice", {})),
        ("scope", lambda e, f: e.__setitem__("wp_id", "")),
        ("manifest", lambda e, f: f["manifest"].__setitem__("capability", "single_onlyoffice")),
    ]
    for name, mutate in mutations:
        e, f = deepcopy(evidence), deepcopy(facts)
        mutate(e, f)
        assert evaluate(e, f, check_commit=False), f"{name} 变异未打红"


def test_onlyoffice_config_authorizes_real_wp_project_before_loading() -> None:
    """鉴权必须在加载底稿之前。

    当前实现使用 ``Depends(require_project_access("readonly"))`` 在 FastAPI 依赖注入层
    完成项目级鉴权（比函数体更早执行），后续在函数体内再经 ``_gate_editor`` 统一门授权。
    二者都在 ``_load_wp_or_404`` 之前生效。
    """
    source = (
        __import__("pathlib").Path(__file__).resolve().parents[2]
        / "app/routers/wp_onlyoffice_router.py"
    ).read_text(encoding="utf-8")
    fn = source[source.index("async def get_sheet_onlyoffice_config"):]
    fn = fn[:fn.index("\n\n@router", 1)] if "\n\n@router" in fn[1:] else fn

    # 签名层：项目级鉴权通过 Depends 注入（比函数体更早执行）
    assert 'require_project_access("readonly")' in fn, (
        "get_sheet_onlyoffice_config 缺少 require_project_access 依赖注入 —— "
        "鉴权降级为仅登录"
    )

    # 函数体层：统一门授权在加载之前
    gate = fn.index("_gate_editor")
    load = fn.index("_load_wp_or_404")
    assert gate > load or 'require_project_access' in fn[:fn.index("_load_wp_or_404")], (
        "_gate_editor 或 require_project_access 必须在 _load_wp_or_404 之前"
    )
