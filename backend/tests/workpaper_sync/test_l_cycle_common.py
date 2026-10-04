# -*- coding: utf-8 -*-
"""L 循环公共骨架守卫（spec `l-cycle-true-adapter-registration` · Task 11，LR-P11 邻域）。

判据落在三处：
1. **回迁零漂移** —— L1 回迁到骨架后，契约 canonical digest 等于已发布值，磁盘双向锁仍成立；
2. **骨架不含业务字面量** —— AST 级扫描，wp_code / sheet 名 / item 键一个都不许出现；
3. **骨架自身语义** —— manifest 门比 H 严（adapter_id 空串不放行）、extra_review 不得覆盖既有键、
   H 骨架装配段委派后与 L 自算逐字节等价（这是「委派而不复制」的成立条件）。
"""
from __future__ import annotations

import ast
import copy
import re
from pathlib import Path

import pytest

from app.services.workpaper_sync import phase5_h_cycle_common as H
from app.services.workpaper_sync import phase5_l1_short_term_loans as L1
from app.services.workpaper_sync import phase5_l_cycle_common as L
from app.services.workpaper_sync.definitions import canonical_digest
from app.services.workpaper_sync.entry_profile import load_entry_manifest

#: L1 已发布契约的 canonical digest（2026-10-01 真库 definition `0477a2f1…` 的 sha256）。
#: 🔴 改了这个值 = 改了已发布契约，必须走新 semantic_version + 重发布，不是改常量了事。
L1_PUBLISHED_CONTRACT_DIGEST = "0567f0106127c6e97781fc8ecd8e66984c67bed3d26ce76d0249da858bdc7952"

COMMON_SRC = Path(L.__file__)


class TestL1MigrationIsByteNeutral:
    def test_contract_digest_unchanged_after_migration(self) -> None:
        assert canonical_digest(L1.build_contract_payload()) == L1_PUBLISHED_CONTRACT_DIGEST

    def test_disk_lock_still_holds(self) -> None:
        contract = L1.assert_contract_file_matches_source()
        assert contract.canonical_sha256 == L1_PUBLISHED_CONTRACT_DIGEST

    def test_l1_routes_through_the_common_skeleton(self) -> None:
        """L1 不再自带装配实现：关键函数体里必须引用 `_L.`（防回迁被悄悄撤回成复制）。"""
        tree = ast.parse(Path(L1.__file__).read_text(encoding="utf-8"))
        funcs = {n.name: n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
        for name in (
            "build_contract_payload", "template_definition_payload",
            "instrumentation_definition_payload", "attach_adapters", "publish_definitions",
            "manifest_capability_enabled",
        ):
            refs = {
                n.value.id for n in ast.walk(funcs[name])
                if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name)
            }
            assert "_L" in refs, f"L1.{name} 未委派公共骨架"

    def test_error_class_is_shared(self) -> None:
        assert L1.EntrySelectionError is L.LEntrySelectionError


class TestSkeletonHasNoBusinessLiterals:
    #: wp_code 形态（L1 / L1-2 / L1S）与本循环 sheet 名关键字
    _CODE = re.compile(r"\bL[0-9]+(?:-[0-9]+)*[A-Z]?\b")
    _SHEET_WORDS = ("明细表", "审定表", "短期借款", "应付债券", "长期借款")

    def _string_constants(self) -> list[str]:
        tree = ast.parse(COMMON_SRC.read_text(encoding="utf-8"))
        doc_nodes = {
            id(n.body[0].value)
            for n in ast.walk(tree)
            if isinstance(n, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
            and n.body and isinstance(n.body[0], ast.Expr)
            and isinstance(n.body[0].value, ast.Constant)
        }
        return [
            n.value for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in doc_nodes
        ]

    def test_no_wp_code_or_sheet_literal_in_code(self) -> None:
        offenders = [
            s for s in self._string_constants()
            if self._CODE.search(s) or any(w in s for w in self._SHEET_WORDS)
        ]
        assert offenders == [], f"骨架代码里出现业务字面量：{offenders}"

    def test_scanner_is_not_vacuous(self) -> None:
        """变异证明：同一口径对 L1 provider 源码必须命中（它满是业务字面量）。"""
        tree = ast.parse(Path(L1.__file__).read_text(encoding="utf-8"))
        hits = [
            n.value for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
            and any(w in n.value for w in self._SHEET_WORDS)
        ]
        assert hits, "扫描口径对 L1 provider 零命中 ⇒ 判据空转"


class TestSkeletonSemantics:
    def test_delegated_assembly_equals_h_skeleton(self) -> None:
        """「委派而不复制」的成立条件：同一组 spec，L 与 H 两边装配逐字节等价。"""
        assert canonical_digest(L.instrumentation_definition_payload(L1.IDENTITY, L1.SPECS)) == \
            canonical_digest(H.instrumentation_definition_payload(L1.IDENTITY, L1.SPECS))  # type: ignore[arg-type]
        assert L.build_contract_payload(L1.IDENTITY, L1.SPECS)["sheets"] == H.sheets_payload(L1.SPECS)

    def test_manifest_gate_rejects_blank_adapter_id(self) -> None:
        """比 H 严：capability=bidirectional 但 adapter_id 空串 ⇒ 不放行。"""
        manifest = copy.deepcopy(load_entry_manifest())
        for e in manifest["entries"]:
            if e["entry_id"] == L1.ENTRY_ID:
                assert e["capability"] == "bidirectional"
                e["adapter_id"] = ""
        assert L.manifest_capability_enabled(L1.IDENTITY, manifest=manifest) is False
        assert L.manifest_capability_enabled(L1.IDENTITY) is True
        with pytest.raises(L.LEntrySelectionError):
            L.assert_manifest_capability_enabled(L1.IDENTITY, manifest=manifest)

    def test_extra_review_cannot_overwrite_existing_keys(self) -> None:
        import dataclasses

        bad = dataclasses.replace(L1.IDENTITY, extra_review={"html_store": {"x": 1}})
        with pytest.raises(L.LEntrySelectionError, match="不得覆盖"):
            L.build_contract_payload(bad, L1.SPECS)

    def test_template_bytes_drift_fails_closed(self) -> None:
        import dataclasses

        drifted = dataclasses.replace(L1.IDENTITY, template_sha256="0" * 64)
        with pytest.raises(L.LEntrySelectionError, match="权威模板字节已变"):
            L.read_authoritative_template(drifted)
