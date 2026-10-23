"""覆盖集合端点的测试配方（partner-manager-edit-permission Task 10.2）。

每条配方定义一个端点的方法、路径、请求体与业务桩目标。
``test_note_edit_gate_endpoints.py`` 读清册产物取覆盖集合，与本配方表求交后参数化。

配方键 = ``(method, path_template)``，``path_template`` 使用清册中的路径（含路径参数占位符）。
``build_request`` 接受一个 ``AuthzWorld`` 并返回填好参数的 ``(method, url, kwargs)``。
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from tests.authz_world import TARGET_NOTE_ID, TARGET_PROJECT_ID


# ---------------------------------------------------------------------------
# 路径填充辅助
# ---------------------------------------------------------------------------

_YEAR = 2025
_SECTION = "五、1"
_NOTE_ID = TARGET_NOTE_ID
_VALIDATION_ID = uuid.UUID("5a1d0c3e-7b2f-4e61-9c84-2f0d6b9a1e10")


# ---------------------------------------------------------------------------
# 配方数据类
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class StubTarget:
    """一个业务桩的位置。``owner_import`` 是 ``import`` 路径（模块），``attr`` 是属性名。

    ``is_class``: 被替换的是一个类（如 ``DisclosureEngine``）——桩返回的对象会被实例化然后调方法。
    ``awaitable``: 桩返回的值是否包在协程里。
    """
    owner_import: str
    attr: str
    is_class: bool = False
    awaitable: bool = True


@dataclass(frozen=True)
class Recipe:
    """一个覆盖集合端点的测试配方。"""
    #: 清册里的 (method, path_template) 键
    method: str
    path_template: str
    #: 填好参数的真实 URL（发往 httpx）
    url: str
    #: 请求 kwargs：json / content / params / headers 等
    request_kwargs: dict[str, Any] = field(default_factory=dict)
    #: 业务桩：至少一个，放行时各桩恰 1 次
    stubs: tuple[StubTarget, ...] = ()
    #: 是否是对象 id 端点（路径上没有 project_id，按对象反查确定项目）
    object_id_endpoint: bool = False
    #: 对象 id 端点的对象不存在时的 URL（用随机 UUID 替换对象 id）
    nonexistent_url: str | None = None

    @property
    def key(self) -> tuple[str, str]:
        return (self.method, self.path_template)


# ---------------------------------------------------------------------------
# A1–A12 配方
# ---------------------------------------------------------------------------

def _stub_engine(attr: str) -> StubTarget:
    """disclosure_engine 模块里的业务函数。"""
    return StubTarget("app.services.disclosure_engine", attr)


def _stub_validation() -> StubTarget:
    return StubTarget("app.services.note_validation_engine", "NoteValidationEngine")


def _stub_mapping(attr: str) -> StubTarget:
    return StubTarget("app.services.note_wp_mapping_service", attr)


def _stub_formula(attr: str) -> StubTarget:
    return StubTarget("app.services.note_formula_service", attr)


# A1: POST /api/disclosure-notes/generate — 请求体含 project_id，函数体形态，consol_lock=True
_A1 = Recipe(
    method="POST",
    path_template="/api/disclosure-notes/generate",
    url="/api/disclosure-notes/generate",
    request_kwargs={
        "json": {
            "project_id": str(TARGET_PROJECT_ID),
            "year": _YEAR,
            "template_type": "soe",
        },
    },
    stubs=(
        StubTarget("app.services.prerequisite_checker", "PrerequisiteChecker", is_class=True),
        StubTarget("app.services.disclosure_engine", "DisclosureEngine", is_class=True),
    ),
)

# A2: PUT /api/disclosure-notes/{note_id} — 对象反查，consol_lock=True
_A2 = Recipe(
    method="PUT",
    path_template="/api/disclosure-notes/{note_id}",
    url=f"/api/disclosure-notes/{_NOTE_ID}",
    request_kwargs={
        "json": {
            "table_data": None,
            "text_content": "测试正文",
            "guidance_text": None,
            "status": "draft",
        },
    },
    stubs=(
        StubTarget("app.services.disclosure_engine", "DisclosureEngine", is_class=True),
    ),
    object_id_endpoint=True,
    nonexistent_url=f"/api/disclosure-notes/{uuid.uuid4()}",
)

# A3: DELETE /api/disclosure-notes/{project_id}/{year}/sections/{note_section:path}
_A3 = Recipe(
    method="DELETE",
    path_template="/api/disclosure-notes/{project_id}/{year}/sections/{note_section:path}",
    url=f"/api/disclosure-notes/{TARGET_PROJECT_ID}/{_YEAR}/sections/{_SECTION}",
    stubs=(),
)

# A4: PATCH /api/disclosure-notes/{project_id}/{year}/sections/{note_section:path}
_A4 = Recipe(
    method="PATCH",
    path_template="/api/disclosure-notes/{project_id}/{year}/sections/{note_section:path}",
    url=f"/api/disclosure-notes/{TARGET_PROJECT_ID}/{_YEAR}/sections/{_SECTION}",
    request_kwargs={"json": {"status": "not_applicable"}},
    stubs=(),
)

# A5: PATCH /api/disclosure-notes/{project_id}/{year}/restore/{note_id}
_A5 = Recipe(
    method="PATCH",
    path_template="/api/disclosure-notes/{project_id}/{year}/restore/{note_id}",
    url=f"/api/disclosure-notes/{TARGET_PROJECT_ID}/{_YEAR}/restore/{_NOTE_ID}",
    stubs=(),
)

# A6: POST /api/disclosure-notes/{project_id}/{year}/pull-from-workpapers
_A6 = Recipe(
    method="POST",
    path_template="/api/disclosure-notes/{project_id}/{year}/pull-from-workpapers",
    url=f"/api/disclosure-notes/{TARGET_PROJECT_ID}/{_YEAR}/pull-from-workpapers",
    stubs=(),
)

# A7: POST /api/disclosure-notes/{project_id}/{year}/validate
_A7 = Recipe(
    method="POST",
    path_template="/api/disclosure-notes/{project_id}/{year}/validate",
    url=f"/api/disclosure-notes/{TARGET_PROJECT_ID}/{_YEAR}/validate",
    request_kwargs={"params": {"template_type": "soe"}},
    stubs=(StubTarget("app.services.note_validation_engine", "NoteValidationEngine", is_class=True),),
)

# A8: PUT /api/disclosure-notes/findings/{validation_id}/confirm — 对象反查
_A8 = Recipe(
    method="PUT",
    path_template="/api/disclosure-notes/findings/{validation_id}/confirm",
    url=f"/api/disclosure-notes/findings/{_VALIDATION_ID}/confirm",
    request_kwargs={
        "json": {"reason": "已确认"},
        "params": {"finding_index": 0},
    },
    stubs=(StubTarget("app.services.note_validation_engine", "NoteValidationEngine", is_class=True),),
    object_id_endpoint=True,
    nonexistent_url=f"/api/disclosure-notes/findings/{uuid.uuid4()}/confirm",
)

# A9: POST /api/disclosure-notes/{project_id}/{year}/{note_section}/clear-formulas
_A9 = Recipe(
    method="POST",
    path_template="/api/disclosure-notes/{project_id}/{year}/{note_section}/clear-formulas",
    url=f"/api/disclosure-notes/{TARGET_PROJECT_ID}/{_YEAR}/{_SECTION}/clear-formulas",
    stubs=(StubTarget("app.services.note_wp_mapping_service", "NoteWpMappingService", is_class=True),),
)

# A10: POST /api/disclosure-notes/{project_id}/{year}/{note_section}/restore-auto
_A10 = Recipe(
    method="POST",
    path_template="/api/disclosure-notes/{project_id}/{year}/{note_section}/restore-auto",
    url=f"/api/disclosure-notes/{TARGET_PROJECT_ID}/{_YEAR}/{_SECTION}/restore-auto",
    stubs=(StubTarget("app.services.note_wp_mapping_service", "NoteWpMappingService", is_class=True),),
)

# A11: POST /api/disclosure-notes/{project_id}/{year}/{note_section}/apply-formulas
_A11 = Recipe(
    method="POST",
    path_template="/api/disclosure-notes/{project_id}/{year}/{note_section}/apply-formulas",
    url=f"/api/disclosure-notes/{TARGET_PROJECT_ID}/{_YEAR}/{_SECTION}/apply-formulas",
    stubs=(StubTarget("app.services.note_formula_generator", "execute_note_formulas"),),
)

# A12: PUT /api/disclosure-notes/{project_id}/{year}/{note_section}/formulas
_A12 = Recipe(
    method="PUT",
    path_template="/api/disclosure-notes/{project_id}/{year}/{note_section}/formulas",
    url=f"/api/disclosure-notes/{TARGET_PROJECT_ID}/{_YEAR}/{_SECTION}/formulas",
    request_kwargs={"json": {"formulas": []}},
    stubs=(StubTarget("app.services.note_formula_service", "note_formula_service"),),
)


# A13: POST /api/disclosure-notes/{project_id}/{year}/offline-import/execute
_A13 = Recipe(
    method="POST",
    path_template="/api/disclosure-notes/{project_id}/{year}/offline-import/execute",
    url=f"/api/disclosure-notes/{TARGET_PROJECT_ID}/{_YEAR}/offline-import/execute",
    request_kwargs={"data": {"decisions": "{}"}, "files": {"file": ("import.docx", b"PK" + b"\x00" * 100, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}},
    stubs=(StubTarget("app.services.note_offline_import_service", "NoteOfflineImportService", is_class=True),),
)

# A14: POST /api/projects/{project_id}/disclosure-note-import/parse-upload
_A14 = Recipe(
    method="POST",
    path_template="/api/projects/{project_id}/disclosure-note-import/parse-upload",
    url=f"/api/projects/{TARGET_PROJECT_ID}/disclosure-note-import/parse-upload",
    request_kwargs={"files": {"file": ("附注.docx", b"PK" + b"\x00" * 100, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}},
    stubs=(StubTarget("app.routers.note_text_batch", "parse_upload_bytes", awaitable=False),),
)

# A15: POST /api/projects/{project_id}/disclosure-note-import/parse-knowledge
_A15 = Recipe(
    method="POST",
    path_template="/api/projects/{project_id}/disclosure-note-import/parse-knowledge",
    url=f"/api/projects/{TARGET_PROJECT_ID}/disclosure-note-import/parse-knowledge",
    request_kwargs={"json": {"doc_ids": []}},
    stubs=(StubTarget("app.routers.note_text_batch", "knowledge_source_payload"),),
)

# A16: POST /api/projects/{project_id}/disclosure-note-text-batch/preview
_A16 = Recipe(
    method="POST",
    path_template="/api/projects/{project_id}/disclosure-note-text-batch/preview",
    url=f"/api/projects/{TARGET_PROJECT_ID}/disclosure-note-text-batch/preview",
    request_kwargs={"json": {"year": _YEAR, "source": {"source_kind": "upload", "parsed_source": {}}}},
    stubs=(StubTarget("app.routers.note_text_batch", "resolve_source"),),
)

# A17: POST /api/projects/{project_id}/disclosure-note-text-batch/apply
_A17 = Recipe(
    method="POST",
    path_template="/api/projects/{project_id}/disclosure-note-text-batch/apply",
    url=f"/api/projects/{TARGET_PROJECT_ID}/disclosure-note-text-batch/apply",
    request_kwargs={
        "json": {"year": _YEAR, "source": {"source_kind": "upload", "parsed_source": {}},
                 "selections": [], "preview_digest": "0" * 64},
        "headers": {"X-Mutation-Id": "test-mut-12345678"},
    },
    stubs=(StubTarget("app.routers.note_text_batch", "resolve_source"),),
)

# A18: POST /api/projects/{project_id}/note-content-templates/snapshot-preview
_A18 = Recipe(
    method="POST",
    path_template="/api/projects/{project_id}/note-content-templates/snapshot-preview",
    url=f"/api/projects/{TARGET_PROJECT_ID}/note-content-templates/snapshot-preview",
    request_kwargs={"json": {"year": _YEAR, "owner_scope": "personal"}},
    stubs=(StubTarget("app.routers.note_content_templates", "snapshot_preview"),),
)

# A19: POST /api/projects/{project_id}/note-content-templates
_A19 = Recipe(
    method="POST",
    path_template="/api/projects/{project_id}/note-content-templates",
    url=f"/api/projects/{TARGET_PROJECT_ID}/note-content-templates",
    request_kwargs={"json": {"year": _YEAR, "name": "测试模板", "owner_scope": "personal", "snapshot_digest": "0" * 64}},
    stubs=(StubTarget("app.routers.note_content_templates", "save_snapshot"),),
)

# A20: DELETE /api/projects/{project_id}/note-content-templates/{template_id}
_A20 = Recipe(
    method="DELETE",
    path_template="/api/projects/{project_id}/note-content-templates/{template_id}",
    url=f"/api/projects/{TARGET_PROJECT_ID}/note-content-templates/5a1d0c3e-7b2f-4e61-9c84-2f0d6b9a1e20",
    stubs=(StubTarget("app.routers.note_content_templates", "soft_delete_template"),),
)

# A21: POST /api/projects/{project_id}/notes/import-prior-year
_A21 = Recipe(
    method="POST",
    path_template="/api/projects/{project_id}/notes/import-prior-year",
    url=f"/api/projects/{TARGET_PROJECT_ID}/notes/import-prior-year",
    request_kwargs={"params": {"year": _YEAR}, "files": {"file": ("prior.docx", b"PK" + b"\x00" * 100, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}},
    stubs=(StubTarget("app.services.note_prior_year_import_service", "NotePriorYearImportService", is_class=True),),
)

# A22: POST /api/projects/{project_id}/notes/inherit-prior-year
_A22 = Recipe(
    method="POST",
    path_template="/api/projects/{project_id}/notes/inherit-prior-year",
    url=f"/api/projects/{TARGET_PROJECT_ID}/notes/inherit-prior-year",
    request_kwargs={"params": {"year": _YEAR}},
    stubs=(StubTarget("app.services.note_prior_year_import_service", "NotePriorYearImportService", is_class=True),),
)

# A23: POST /api/projects/{project_id}/notes/cross-references/update
_A23 = Recipe(
    method="POST",
    path_template="/api/projects/{project_id}/notes/cross-references/update",
    url=f"/api/projects/{TARGET_PROJECT_ID}/notes/cross-references/update",
    request_kwargs={"params": {"year": _YEAR}},
    stubs=(StubTarget("app.services.note_cross_reference_service", "NoteCrossReferenceService", is_class=True),),
)


# ---------------------------------------------------------------------------
# A24（note_wp_mapping）+ B1 / B2 配方
# ---------------------------------------------------------------------------

# A24: POST /api/disclosure-notes/{project_id}/{year}/{note_id}/toggle-mode
_A24 = Recipe(
    method="POST",
    path_template="/api/disclosure-notes/{project_id}/{year}/{note_id}/toggle-mode",
    url=f"/api/disclosure-notes/{TARGET_PROJECT_ID}/{_YEAR}/{_NOTE_ID}/toggle-mode",
    request_kwargs={
        "json": {"row_label": "应收账款", "col_index": 0, "mode": "manual", "manual_value": "1000.00"},
    },
    stubs=(StubTarget("app.services.note_wp_mapping_service", "NoteWpMappingService", is_class=True),),
)

# B1: POST /api/disclosure-notes/{project_id}/{year}/refresh-from-workpapers
_B1_REFRESH_FROM_WP = Recipe(
    method="POST",
    path_template="/api/disclosure-notes/{project_id}/{year}/refresh-from-workpapers",
    url=f"/api/disclosure-notes/{TARGET_PROJECT_ID}/{_YEAR}/refresh-from-workpapers",
    stubs=(
        StubTarget("app.services.note_wp_mapping_service", "NoteWpMappingService", is_class=True),
        StubTarget("app.services.note_readiness_service", "run_validation_best_effort"),
    ),
)

# B1: POST /api/disclosure-notes/{project_id}/{year}/{note_section}/refresh-from-workpaper
_B1_REFRESH_SECTION = Recipe(
    method="POST",
    path_template="/api/disclosure-notes/{project_id}/{year}/{note_section}/refresh-from-workpaper",
    url=f"/api/disclosure-notes/{TARGET_PROJECT_ID}/{_YEAR}/{_SECTION}/refresh-from-workpaper",
    stubs=(
        StubTarget("app.services.note_wp_mapping_service", "NoteWpMappingService", is_class=True),
        StubTarget("app.services.note_readiness_service", "run_validation_best_effort"),
    ),
)

# B2: PUT /api/disclosure-notes/{project_id}/wp-mapping
_B2_UPDATE_MAPPING = Recipe(
    method="PUT",
    path_template="/api/disclosure-notes/{project_id}/wp-mapping",
    url=f"/api/disclosure-notes/{TARGET_PROJECT_ID}/wp-mapping",
    request_kwargs={"json": {"五、1": {"wp_code": "D1-1", "sheet": "明细"}}},
    stubs=(StubTarget("app.services.note_wp_mapping_service", "NoteWpMappingService", is_class=True),),
)

# B2: POST /api/disclosure-notes/{project_id}/{year}/refresh-all-bindings
_B2_REFRESH_ALL_BINDINGS = Recipe(
    method="POST",
    path_template="/api/disclosure-notes/{project_id}/{year}/refresh-all-bindings",
    url=f"/api/disclosure-notes/{TARGET_PROJECT_ID}/{_YEAR}/refresh-all-bindings",
    stubs=(
        StubTarget("app.services.disclosure_engine", "DisclosureEngine", is_class=True),
        StubTarget("app.services.note_formula_gray_service", "is_note_formula_enabled"),
        StubTarget("app.services.note_readiness_service", "run_validation_best_effort"),
    ),
)




# ---------------------------------------------------------------------------
# B1: note_custom_template save / restore, group_note_baseline apply
# ---------------------------------------------------------------------------

# B1: POST /api/projects/{project_id}/note-template/save
_B1_SAVE_CUSTOM_TEMPLATE = Recipe(
    method="POST",
    path_template="/api/projects/{project_id}/note-template/save",
    url=f"/api/projects/{TARGET_PROJECT_ID}/note-template/save",
    request_kwargs={"json": {"sections": []}},
    stubs=(StubTarget("app.routers.note_custom_template", "NoteCustomTemplateService", is_class=True),),
)

# B1: POST /api/projects/{project_id}/note-template/restore
_B1_RESTORE_CUSTOM_TEMPLATE = Recipe(
    method="POST",
    path_template="/api/projects/{project_id}/note-template/restore",
    url=f"/api/projects/{TARGET_PROJECT_ID}/note-template/restore",
    request_kwargs={"params": {"version": 1}},
    stubs=(StubTarget("app.routers.note_custom_template", "NoteCustomTemplateService", is_class=True),),
)

# B1: POST /api/projects/{project_id}/apply-group-baseline
_B1_APPLY_GROUP_BASELINE = Recipe(
    method="POST",
    path_template="/api/projects/{project_id}/apply-group-baseline",
    url=f"/api/projects/{TARGET_PROJECT_ID}/apply-group-baseline",
    request_kwargs={"json": {"baseline_id": "5a1d0c3e-7b2f-4e61-9c84-2f0d6b9a1e99", "year": 2025}},
    stubs=(StubTarget("app.routers.group_note_baseline", "GroupNoteBaselineService", is_class=True),),
)


# ---------------------------------------------------------------------------
# B2: note_trim save/auto-trim, note_custom_section create/save-as-template/apply-template
# ---------------------------------------------------------------------------
# B2: PUT /api/disclosure-notes/{project_id}/sections/trim
_B2_SAVE_TRIM = Recipe(
    method="PUT",
    path_template="/api/disclosure-notes/{project_id}/sections/trim",
    url=f"/api/disclosure-notes/{TARGET_PROJECT_ID}/sections/trim",
    request_kwargs={"json": {"items": [{"id": "\u4e94\u3001\uff11", "status": "applicable", "skip_reason": None}]}},
    stubs=(StubTarget("app.routers.note_trim", "NoteTrimService", is_class=True),),
)

# B2: POST /api/disclosure-notes/{project_id}/{year}/auto-trim
_B2_AUTO_TRIM = Recipe(
    method="POST",
    path_template="/api/disclosure-notes/{project_id}/{year}/auto-trim",
    url=f"/api/disclosure-notes/{TARGET_PROJECT_ID}/{_YEAR}/auto-trim",
    stubs=(StubTarget("app.routers.note_trim", "NoteTrimService", is_class=True),),
)

# B2: POST /api/projects/{project_id}/notes/custom-sections/create
_B2_CUSTOM_SECTION_CREATE = Recipe(
    method="POST",
    path_template="/api/projects/{project_id}/notes/custom-sections/create",
    url=f"/api/projects/{TARGET_PROJECT_ID}/notes/custom-sections/create",
    request_kwargs={"json": {"year": _YEAR, "section_type": "mixed", "title": "\u6d4b\u8bd5\u7ae0\u8282"}},
    stubs=(StubTarget("app.routers.note_custom_section", "NoteCustomSectionService", is_class=True),),
)

# B2: POST /api/projects/{project_id}/notes/custom-sections/save-as-template
_B2_CUSTOM_SECTION_SAVE_AS_TEMPLATE = Recipe(
    method="POST",
    path_template="/api/projects/{project_id}/notes/custom-sections/save-as-template",
    url=f"/api/projects/{TARGET_PROJECT_ID}/notes/custom-sections/save-as-template",
    request_kwargs={"json": {"section_id": str(TARGET_NOTE_ID), "template_name": "\u6d4b\u8bd5\u6a21\u677f"}},
    stubs=(StubTarget("app.routers.note_custom_section", "NoteCustomSectionService", is_class=True),),
)

# B2: POST /api/projects/{project_id}/notes/custom-sections/apply-template
_B2_CUSTOM_SECTION_APPLY_TEMPLATE = Recipe(
    method="POST",
    path_template="/api/projects/{project_id}/notes/custom-sections/apply-template",
    url=f"/api/projects/{TARGET_PROJECT_ID}/notes/custom-sections/apply-template",
    request_kwargs={"json": {"year": _YEAR, "template_id": "5a1d0c3e-7b2f-4e61-9c84-2f0d6b9a1e30"}},
    stubs=(StubTarget("app.routers.note_custom_section", "NoteCustomSectionService", is_class=True),),
)

# ---------------------------------------------------------------------------
# B3: note_section_lock acquire / heartbeat, note_data_lock snapshot,
#     note_group_template save / detach — require_note_edit_access(consol_lock=False)
# ---------------------------------------------------------------------------

# B3: POST /api/projects/{project_id}/notes/locks/acquire
_B3_ACQUIRE_LOCK = Recipe(
    method="POST",
    path_template="/api/projects/{project_id}/notes/locks/acquire",
    url=f"/api/projects/{TARGET_PROJECT_ID}/notes/locks/acquire",
    request_kwargs={"json": {"year": _YEAR, "section_code": "\u4e94\u30011"}},
    stubs=(StubTarget("app.routers.note_section_lock", "NoteSectionLockService", is_class=True),),
)

# B3: POST /api/projects/{project_id}/notes/locks/heartbeat
_B3_HEARTBEAT = Recipe(
    method="POST",
    path_template="/api/projects/{project_id}/notes/locks/heartbeat",
    url=f"/api/projects/{TARGET_PROJECT_ID}/notes/locks/heartbeat",
    request_kwargs={"json": {"year": _YEAR, "section_code": "\u4e94\u30011"}},
    stubs=(StubTarget("app.routers.note_section_lock", "NoteSectionLockService", is_class=True),),
)

# B3: POST /api/projects/{project_id}/data-lock/snapshot
_B3_SNAPSHOT = Recipe(
    method="POST",
    path_template="/api/projects/{project_id}/data-lock/snapshot",
    url=f"/api/projects/{TARGET_PROJECT_ID}/data-lock/snapshot",
    request_kwargs={"json": {"year": _YEAR}},
    stubs=(StubTarget("app.routers.note_data_lock", "NoteDataLockService", is_class=True),),
)

# B3: POST /api/projects/{project_id}/notes/group-template/save
_B3_SAVE_GROUP_TEMPLATE = Recipe(
    method="POST",
    path_template="/api/projects/{project_id}/notes/group-template/save",
    url=f"/api/projects/{TARGET_PROJECT_ID}/notes/group-template/save",
    request_kwargs={"json": {"year": _YEAR, "template_name": "\u6d4b\u8bd5\u96c6\u56e2\u6a21\u677f"}},
    stubs=(StubTarget("app.routers.note_group_template", "NoteGroupTemplateService", is_class=True),),
)

# B3: POST /api/projects/{project_id}/notes/group-template/detach
_B3_DETACH_GROUP_TEMPLATE = Recipe(
    method="POST",
    path_template="/api/projects/{project_id}/notes/group-template/detach",
    url=f"/api/projects/{TARGET_PROJECT_ID}/notes/group-template/detach",
    stubs=(StubTarget("app.routers.note_group_template", "NoteGroupTemplateService", is_class=True),),
)


# ---------------------------------------------------------------------------
# 配方注册表
# ---------------------------------------------------------------------------
ALL_RECIPES: dict[tuple[str, str], Recipe] = {}
for _recipe in [_A1, _A2, _A3, _A4, _A5, _A6, _A7, _A8, _A9, _A10, _A11, _A12,
                _A13, _A14, _A15, _A16, _A17, _A18, _A19, _A20, _A21, _A22, _A23,
                _A24, _B1_REFRESH_FROM_WP, _B1_REFRESH_SECTION, _B2_UPDATE_MAPPING,
                _B2_REFRESH_ALL_BINDINGS,
                _B1_SAVE_CUSTOM_TEMPLATE, _B1_RESTORE_CUSTOM_TEMPLATE,
                _B1_APPLY_GROUP_BASELINE,
                _B2_SAVE_TRIM, _B2_AUTO_TRIM,
                _B2_CUSTOM_SECTION_CREATE, _B2_CUSTOM_SECTION_SAVE_AS_TEMPLATE,
                _B2_CUSTOM_SECTION_APPLY_TEMPLATE,
                _B3_ACQUIRE_LOCK, _B3_HEARTBEAT, _B3_SNAPSHOT,
                _B3_SAVE_GROUP_TEMPLATE, _B3_DETACH_GROUP_TEMPLATE]:
    ALL_RECIPES[_recipe.key] = _recipe
