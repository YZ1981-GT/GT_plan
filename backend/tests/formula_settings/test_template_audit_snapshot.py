"""模板发布与回滚必须留存写入前旧值；使用真实 ORM 与生产审计链。"""
from copy import deepcopy
from types import SimpleNamespace
import uuid

import pytest
import sqlalchemy as sa

from app.models.audit_log_models import AuditLogEntry
from app.models.formula_setting_models import FormulaPublish, FormulaSetting, FormulaTemplateVersion
from app.services.formula_settings import template_service as svc, template_sync as sync
from app.services.formula_settings.definitions import normalize
from .test_templates import G2, MINE, SLOT, SLOT2, V2, _publish_previewed, _template, rdef, world  # noqa: F401


async def _definitions(db, template_id):
    rows = (await db.execute(sa.select(FormulaSetting.slot_key, FormulaSetting.definition).where(
        FormulaSetting.template_id == template_id, FormulaSetting.layer == "template",
        FormulaSetting.is_deleted == sa.false()))).all()
    return {key: definition for key, definition in rows}


@pytest.mark.parametrize("operation", ["publish", "rollback"])
async def test_persisted_template_audit_keeps_before_and_after(world, operation):
    db = world["db"]
    tpl = await _template(world)
    before = await _definitions(db, tpl.id)
    result = await _publish_previewed(db, tpl, expected_version=1, user_id=world["owner"].id,
        changes=[{"domain": "report", "slot_key": SLOT, "definition": rdef(V2)},
                 {"domain": "report", "slot_key": SLOT2, "definition": rdef(G2)}])
    action = "formula.template_published"
    if operation == "rollback":
        await db.commit()
        before = await _definitions(db, tpl.id)
        _diff, changes = await svc.rollback_changes(db, tpl, 1)
        result = await _publish_previewed(db, tpl, expected_version=2, user_id=world["owner"].id,
            changes=changes, publish_source="template_rollback", item_action="template_rollback",
            audit_action="template_rollback", audit_details={"source_version": 1})
        action = "template_rollback"
    await db.commit()
    after = await _definitions(db, tpl.id)
    publication = (await db.execute(sa.select(FormulaPublish.change_set).where(
        FormulaPublish.id == uuid.UUID(result["publish_id"])))).scalar_one()
    version_changes = (await db.execute(sa.select(FormulaTemplateVersion.change_set).where(
        FormulaTemplateVersion.template_id == tpl.id,
        FormulaTemplateVersion.version == result["version"]))).scalar_one()
    payloads = (await db.execute(sa.select(AuditLogEntry.payload).where(
        AuditLogEntry.action_type == action))).scalars().all()
    audit = next(p for p in payloads if p.get("publish_id") == result["publish_id"])
    assert publication == version_changes
    assert {c["slot_key"] for c in publication} == {SLOT, SLOT2}
    audit_rows = {c["slot_key"]: c for c in audit["changes"]}
    for change in publication:
        slot = change["slot_key"]
        assert change["old"] == before.get(slot), f"{operation} {slot} 旧定义被写入污染"
        assert change["new"] == after.get(slot)
        assert change["deleted"] is (slot not in after)
        recorded = audit_rows[slot]
        assert recorded.get("old_definition") == normalize("report", before.get(slot))
        assert recorded.get("new_definition") == normalize("report", after.get(slot))
        assert recorded["old_formula"] == (before.get(slot) or {}).get("formula", "")
        assert recorded["new_formula"] == (after.get(slot) or {}).get("formula", "")
    assert before[SLOT]["formula"] == (MINE if operation == "publish" else V2)
    assert after[SLOT]["formula"] == (V2 if operation == "publish" else MINE)
    assert audit["version"] == (2 if operation == "publish" else 3)


@pytest.mark.parametrize("side", ["old", "new"])
def test_change_rows_detaches_nested_definitions(side):
    old = {"formula": "10", "_structure": {"columns": [{"name": "旧列"}]}}
    new = {"formula": "21", "_structure": {"columns": [{"name": "新列"}]}}
    expected = deepcopy(old if side == "old" else new)
    frozen = sync._change_rows({"report": {SLOT: new}},
        {"report": {SLOT: SimpleNamespace(definition=old, slot_label="测试公式位")}})
    live = old if side == "old" else new
    live["formula"] = "999"
    live["_structure"]["columns"][0]["name"] = "后续修改"
    assert frozen[0][side] == expected, f"{side} 的嵌套定义仍与可写对象共享引用"
