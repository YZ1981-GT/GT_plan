# -*- coding: utf-8 -*-
# 4.2: drain ledger must carry the binding snapshot even when the legacy-URL
# switch is OFF. spec: onlyoffice-sheet-open-via-published-artifact 4.2 EQCR
# condition (2026-11-21). Background: the config endpoint used to fill
# legacy_verdict only when ONLYOFFICE_LEGACY_URL_ISSUE is False, so under the
# default True deployment every issued drain-ledger row had
# binding_id/binding_status == None (observed 4/4 null in the shared DB) and
# Requirement 6.4 per-binding issuance counts were untraceable. Mutation
# proof: deleting the else branch below must turn these guards red.
from __future__ import annotations

from pathlib import Path

NL = chr(10)

REPO = Path(__file__).resolve().parents[3]
ROUTER = REPO / 'backend' / 'app' / 'routers' / 'wp_onlyoffice_router.py'
GATE = REPO / 'backend' / 'app' / 'routers' / '_wp_onlyoffice_legacy_url_gate.py'


def _gate_block() -> str:
    src = ROUTER.read_text(encoding='utf-8')
    i = src.find('legacy_verdict: dict = {}')
    assert i > 0, 'legacy_verdict anchor not found'
    j = src.find('resolve_room_doc_key', i)
    assert j > i, 'gate block end anchor not found'
    return src[i:j]


def test_off_branch_resolves_binding_snapshot():
    block = _gate_block()
    assert 'else:' in block, 'OFF branch lost its else block (4.2 snapshot reverted)'
    assert '_binding_verdict(' in block, 'else block does not resolve the binding snapshot'
    assert 'legacy_verdict = {' in block, 'else block does not backfill legacy_verdict'
    assert '"entry_id"' in block and '"binding_status"' in block


def test_gate_refusal_behavior_untouched():
    block = _gate_block()
    assert '_refuse_legacy_url_when_room_ready(' in block
    assert 'if not settings.ONLYOFFICE_LEGACY_URL_ISSUE:' in block


def test_binding_verdict_is_pure_read_and_never_raises():
    src = GATE.read_text(encoding='utf-8')
    i = src.find('def _binding_verdict')
    assert i > 0
    nxt = src.find(NL + 'def ', i + 1)
    body = src[i:nxt]
    assert 'except Exception' in body, 'binding_verdict must swallow parse errors or the OFF branch 500s'
    assert 'return "unresolved", None' in body
