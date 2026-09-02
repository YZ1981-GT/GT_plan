# -*- coding: utf-8 -*-
"""Task 13 守卫：通用 adapter protocol、canonical contract/bundle schema、fail-closed registry。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 1 Task 13
Requirements: 1.4, 6.1, 6.2, 6.3, 6.10, 6.14, 6.20, 9.8, 12.1
Properties: P3（未注册 adapter 不得宣称双向）/ P20（generated col 占位不可注册生产
adapter）/ P21（contract 字段完整）/ P28（immutable definition 漂移 fail closed）

═══ 判据落在哪 ═══

* **P21 contract 字段完整** —— 每个受管字段的 6 个语义面（stable key / JSON Pointer /
  OO 位置 / value type / source_ref / mode）逐个**单独抽掉**都必须被拒，且错误文案
  可区分。判据落在 `parse_contract` 的真实执行上，不是「源码里有没有这个词」。
* **P20 col 占位** —— `col_[a-z]+` 形态**无条件**被拒（即使 `source_ref` 齐全），
  与「缺 source_ref」是两条独立判据。`TestGuardSelfCheck` 用一个只查 source_ref 的
  替身证明：合成一条之后 col 反例会被 source_ref 判据遮蔽 ⇒ 变异必 GREEN。
* **P28 definition 漂移** —— 三条互不遮蔽的漂移：契约 ↔ frozen bundle slot（RG-10）、
  契约 ↔ 磁盘真源（RG-11）、契约声明结构 ↔ 实测结构（`assert_no_structure_drift`）。
  加 bundle 侧的 slot omission / NULL / 空串 / 全零 hash / 非法 marker / marker 冒充
  contract。
* **P3 未注册不得宣称双向** —— `assert_bidirectional_ready` 的三条缺失路径
  （adapter / bundle / contract）抛**三种不同**异常类型，守卫双向断言它们不是继承
  关系，否则删任一分支会被另一条遮蔽。
* **跨语言 canonical** —— golden fixture 与 `canonical_json_bytes` 的新鲜度、键序/
  换行扰动、typed marker 版本变化、XL-1~XL-6 反例。TS 侧同一份 fixture 由
  `audit-platform/frontend/src/components/workpaper/sync/__tests__/canonicalJson.spec.ts`
  断言（42 例），本文件断言 Python 侧 + 两侧共享真源的存在性与自反性。

═══ 本任务边界（守卫也锁住「不做的事」）═══

`TestTask13ScopeBoundary` 断言：本 Wave 不引入 Excel/Word engine（零 openpyxl /
python-docx import）、不发布任何 representation、不 finalize upgrade candidate、
且 registry 不提供任何按 alias 反查历史 bundle 的入口。后两条是**否定式承诺**，
变异脚本用**注入**反例证明判据可 falsify（M21 / M22）。

═══ 反向自检 ═══

`TestGuardSelfCheck` 用替身复现三种已实证的假绿形态：只查 source_ref 的宽松解析器、
把 `declared_capability` 定义成 `descriptor.mode`（让 RG-18 结构性不可达）、
projection key 只比前缀。
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import re
import sys
import uuid
from pathlib import Path
from typing import Any, Mapping

import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:  # pragma: no cover - import 环境自举
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

from app.services.workpaper_sync import canonical_interop as XL  # noqa: E402
from app.services.workpaper_sync import contracts as C  # noqa: E402
from app.services.workpaper_sync import definitions as D  # noqa: E402
from app.services.workpaper_sync import entry_profile as EP  # noqa: E402
from app.services.workpaper_sync.adapters import base as AB  # noqa: E402
from app.services.workpaper_sync.adapters import registry as RG  # noqa: E402
from app.services.workpaper_sync.models import (  # noqa: E402
    ArtifactKind,
    ArtifactState,
    AuthorityModel,
    BundleIntegrityError,
    BundleSlot,
    BundleSlotSpec,
    DefinitionKind,
    DefinitionState,
    IncomingNotDurableError,
    QuarantinedIncomingError,
    validate_definition_child,
)
from app.services.workpaper_sync.resolution import DefinitionBundleSnapshot  # noqa: E402

_SYNC_DIR = _BACKEND / "app" / "services" / "workpaper_sync"
_CONTRACTS_PY = _SYNC_DIR / "contracts.py"
_BASE_PY = _SYNC_DIR / "adapters" / "base.py"
_REGISTRY_PY = _SYNC_DIR / "adapters" / "registry.py"
_INTEROP_PY = _SYNC_DIR / "canonical_interop.py"
_PROFILE_PY = _SYNC_DIR / "entry_profile.py"
_CLOSURE_PY = _BACKEND / "scripts" / "check" / "check_workpaper_sync_closure.py"
_TS_CANONICALIZER = (
    _REPO / "audit-platform" / "frontend" / "src" / "components" / "workpaper" / "sync"
    / "canonicalJson.ts"
)

# 双哨兵：单哨兵会被历史空目录骗停。
assert (_BACKEND / "app" / "main.py").is_file(), "哨兵失效：backend/app/main.py 不存在"
assert (_BACKEND / "wp_templates").is_dir(), "哨兵失效：backend/wp_templates 不存在"


# ═══════════════════════════════════════════════════════════════════════════
# 0. 工具
# ═══════════════════════════════════════════════════════════════════════════


def _d(label: str) -> str:
    """稳定的假 digest（64 位小写 hex、非全零）。"""
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _read(path: Path) -> str:
    assert path.is_file(), f"文件不存在: {path}"
    return path.read_text(encoding="utf-8")


def _stripped(path: Path) -> str:
    """剥注释/docstring 后的源码 —— 防「说明文字里的反例」被数成真实代码。"""
    sys.path.insert(0, str(_BACKEND / "scripts" / "gen"))
    from generate_workpaper_resolver_migration_matrix import (  # noqa: PLC0415
        strip_comments_and_docstrings,
    )

    return strip_comments_and_docstrings(_read(path))


def _func_body(source: str, signature_prefix: str) -> str:
    """按缩进逐行截取一个 def 的函数体（不含签名行）。

    🔴 刻意不用正则：`(?:(?:\\s{4}.*)?\\n)+?` 这类「可选组套在重复里」的写法会灾难性
    回溯 —— 本文件首轮实测让整个 pytest 跑挂到 5 分钟超时。行级 + 缩进判定是 O(n)。
    """
    lines = source.splitlines()
    starts = [i for i, line in enumerate(lines) if line.strip().startswith(signature_prefix)]
    assert len(starts) == 1, (
        f"签名 {signature_prefix!r} 命中 {len(starts)} 次，无法唯一定位"
    )
    start = starts[0]
    base_indent = len(lines[start]) - len(lines[start].lstrip())
    body: list[str] = []
    for line in lines[start + 1:]:
        if line.strip() and (len(line) - len(line.lstrip())) <= base_indent:
            break
        body.append(line)
    assert body, f"{signature_prefix!r} 的函数体为空"
    return "\n".join(body)


def _strip_ts_comments(source: str) -> str:
    """剥掉 TS 的 `/* */` 与 `//` 注释，保留字符串字面量内的 `//`。

    刻意手写一个字符级扫描而不是用正则：正则会把 `"http://x"` 里的 `//` 当注释起点，
    于是「字符串里的内容被误剥」和「注释没被剥」两种错都会出现，而两者都会让上层
    判据静默失真（一个假绿、一个假红）。:meth:`test_ts_comment_stripper_self_check`
    对这两个方向各有一条反例。
    """
    out: list[str] = []
    index = 0
    length = len(source)
    quote: str | None = None
    while index < length:
        char = source[index]
        if quote is not None:
            out.append(char)
            if char == "\\" and index + 1 < length:
                out.append(source[index + 1])
                index += 2
                continue
            if char == quote:
                quote = None
            index += 1
            continue
        if char in "\"'`":
            quote = char
            out.append(char)
            index += 1
            continue
        if source.startswith("//", index):
            end = source.find("\n", index)
            index = length if end == -1 else end
            continue
        if source.startswith("/*", index):
            end = source.find("*/", index + 2)
            index = length if end == -1 else end + 2
            continue
        out.append(char)
        index += 1
    return "".join(out)


TEMPLATE_DEF = _d("template-definition")
INSTR_DEF = _d("instrumentation-definition")
AUTHORITY_DEF = _d("authority-model-definition")


def def_slot(slot: BundleSlot, digest: str) -> BundleSlotSpec:
    return D.definition_slot_spec(slot, definition_id=uuid.uuid4(), definition_sha256=digest)


def marker_slot(slot: BundleSlot, *, version: int = 1) -> BundleSlotSpec:
    return D.marker_slot_spec(slot, version=version)


def make_bundle(
    *,
    authority_model: AuthorityModel = AuthorityModel.projection_contract,
    template_digest: str = TEMPLATE_DEF,
    instrumentation_digest: str | None = INSTR_DEF,
    contract_digest: str | None = None,
    state: DefinitionState = DefinitionState.approved,
    authority_digest: str = AUTHORITY_DEF,
    drop_slots: tuple[BundleSlot, ...] = (),
) -> DefinitionBundleSnapshot:
    """构造 frozen bundle 快照。

    `None` digest 表示该 slot 使用版本化 typed null marker；`drop_slots` 用于制造
    slot omission 反例（真实 DB 有 NOT NULL，但 snapshot 可被调用方直接构造，
    因此服务层必须自己验）。
    """
    slots: dict[BundleSlot, BundleSlotSpec] = {}
    for slot, digest in (
        (BundleSlot.template, template_digest),
        (BundleSlot.instrumentation, instrumentation_digest),
        (BundleSlot.contract, contract_digest),
    ):
        if slot in drop_slots:
            continue
        slots[slot] = def_slot(slot, digest) if digest is not None else marker_slot(slot)
    return DefinitionBundleSnapshot(
        bundle_id=uuid.uuid4(),
        bundle_sha256=_d("bundle"),
        schema_version=D.BUNDLE_SCHEMA_VERSION,
        state=state,
        authority_model=authority_model,
        authority_model_definition_id=uuid.uuid4(),
        authority_model_definition_sha256=authority_digest,
        slots=slots,
    )


# ── contract payload 构造器 ────────────────────────────────────────────────
#
# 刻意用「先造合法体、再逐项破坏」的形态：反例与正例共享同一个骨架，
# 因此「被拒是因为我改的那一项」而不是因为骨架本来就不合法。


def xlsx_payload(contract_id: str = "g7.disclosure.listed") -> dict[str, Any]:
    return {
        "schema_version": C.CONTRACT_SCHEMA_VERSION,
        "contract_id": contract_id,
        "semantic_version": "1.0.0",
        "review_status": "reviewed",
        "document_type": "xlsx",
        "template_definition_sha256": TEMPLATE_DEF,
        "instrumentation_definition_sha256": INSTR_DEF,
        "template": {
            "relative_path": "G/G7 权益工具投资.xlsx",
            "template_sha256": _d("template-blob"),
            "normalized_structure_hash": _d("template-structure"),
        },
        "identity_carriers": ["hidden_sheet", "defined_name", "hidden_uuid_column"],
        "sheets": [
            {
                "sheet_key": "g7-disclosure",
                "excel_name": "G7 披露表",
                "locator": {"anchor": "defined_name_ref"},
                "tables": [
                    {
                        "table_key": "equity_changes",
                        "anchor": "A7",
                        "header_rows": 2,
                        "row_identity": {"kind": "field", "json_pointer": "/rows/*/rowUuid"},
                        "delete_policy": "tombstone",
                        "dynamic_columns": {
                            "identity": "{slot}_{seq}",
                            "source_ref": "源xlsx!B6:Z6",
                        },
                        "footer_anchor": {"marker": "合计", "search_column": "A"},
                        "formula_mask": ["I8:I200"],
                        "fields": [
                            {
                                "stable_field_key": "equity_changes/{row_uuid}/closing_amount",
                                "json_pointer": "/rows/{row_uuid}/closingAmount",
                                "column_key": "closing_amount",
                                "cell": {"column": "H", "row_from": "row_identity"},
                                "mode": "editable",
                                "value_type": "amount",
                                "source_ref": "源xlsx!H8",
                            },
                            {
                                "stable_field_key": "equity_changes/{row_uuid}/subtotal",
                                "json_pointer": "/rows/{row_uuid}/subtotal",
                                "column_key": "subtotal",
                                "cell": {"column": "I", "row_from": "row_identity"},
                                "mode": "formula",
                                "value_type": "amount",
                                "source_ref": "源xlsx!I8",
                            },
                        ],
                    },
                    {
                        "table_key": "header_block",
                        "anchor": "A1",
                        "header_rows": 1,
                        "fields": [
                            {
                                "stable_field_key": "header_block/period_label",
                                "json_pointer": "/header/periodLabel",
                                "column_key": "period_label",
                                "cell": {"column": "B", "row_from": 2},
                                "mode": "editable",
                                "value_type": "text",
                                "source_ref": "源xlsx!B2",
                            }
                        ],
                    },
                ],
            }
        ],
    }


def docx_payload(contract_id: str = "f2.stocktake.plan") -> dict[str, Any]:
    return {
        "schema_version": C.CONTRACT_SCHEMA_VERSION,
        "contract_id": contract_id,
        "semantic_version": "1.0.0-sdt1",
        "review_status": "reviewed",
        "document_type": "docx",
        "template_definition_sha256": TEMPLATE_DEF,
        "instrumentation_definition_sha256": INSTR_DEF,
        "template": {
            "relative_path": "F/F2 存货监盘计划.docx",
            "template_sha256": _d("docx-blob"),
            "normalized_structure_hash": _d("docx-structure"),
        },
        "identity_carriers": ["field_sdt_inline", "cell_level_field_sdt_tag_carrying_row_uuid"],
        "fields": [
            {
                "stable_field_key": "plan/location",
                "json_pointer": "/plan/location",
                # tag 必须绑本契约 id —— 骨架里不能写死某个具体 contract_id，否则
                # 换 id 的反例会被「tag 的 contract 段不符」提前挡住（原因指错）。
                "sdt_tag": f"gt:field:{contract_id}:plan/location",
                "mode": "editable",
                "value_type": "text",
                "source_ref": "源docx!监盘地点",
            }
        ],
        "repeaters": [
            {
                "stable_field_key": "plan/members/{row_uuid}/name",
                "json_pointer": "/plan/members/{row_uuid}/name",
                "sdt_tag": f"gt:field:{contract_id}:plan/members/{{row_uuid}}/name",
                "mode": "editable",
                "value_type": "text",
                "source_ref": "源docx!监盘人员表",
                "instances": "many",
            }
        ],
    }


def first_field(payload: Mapping[str, Any]) -> dict[str, Any]:
    """xlsx payload 的第一个受管字段（可原地修改）。"""
    return payload["sheets"][0]["tables"][0]["fields"][0]


def first_table(payload: Mapping[str, Any]) -> dict[str, Any]:
    return payload["sheets"][0]["tables"][0]


@pytest.fixture()
def contracts_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """把契约目录指到 tmp —— 生产 `backend/data/workpaper_sync_contracts/` 不被污染。"""
    target = tmp_path / "workpaper_sync_contracts"
    target.mkdir()
    monkeypatch.setattr(C, "CONTRACTS_DIR", target)
    return target


def install_contract(directory: Path, payload: Mapping[str, Any]) -> C.SyncContract:
    """把 payload 写进契约目录并解析（模拟真实注册前的加载路径）。"""
    path = directory / f"{payload['contract_id']}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return C.load_contract(str(payload["contract_id"]))


# ═══════════════════════════════════════════════════════════════════════════
# Property 21：contract 字段完整
# ═══════════════════════════════════════════════════════════════════════════


class TestProperty21ContractFieldCompleteness:
    """每个 editable field 均有 stable key、JSON Pointer、OO 位置、value type、
    source_ref 和模式。逐项抽掉都必须被拒，且文案可区分。"""

    def test_valid_xlsx_contract_parses_with_all_six_facets(self) -> None:
        contract = C.parse_contract(xlsx_payload())
        assert contract.document_type == "xlsx"
        assert contract.review_status is C.ContractReviewStatus.reviewed
        assert contract.all_fields(), "契约必须有受管字段"
        for spec in contract.all_fields():
            assert spec.stable_field_key
            assert spec.json_pointer.startswith("/")
            assert isinstance(spec.mode, C.FieldMode)
            assert isinstance(spec.value_type, C.ValueType)
            assert spec.source_ref
            # xlsx 的 OO 位置 = cell；docx 的 OO 位置 = sdt_tag。
            assert spec.cell is not None, f"{spec.stable_field_key} 缺 OO 位置"

    def test_valid_docx_contract_parses(self) -> None:
        contract = C.parse_contract(docx_payload())
        assert contract.document_type == "docx"
        assert [f.stable_field_key for f in contract.fields] == ["plan/location"]
        assert contract.repeaters[0].row_scoped is True
        for spec in contract.all_fields():
            assert spec.sdt_tag, f"{spec.stable_field_key} 缺 OO 位置（sdt_tag）"
            assert spec.cell is None, "docx 字段不得带 Excel cell"

    @pytest.mark.parametrize(
        ("facet", "needle"),
        [
            ("stable_field_key", "stable_field_key"),
            ("json_pointer", "JSON Pointer"),
            ("mode", "mode"),
            ("value_type", "value_type"),
            ("source_ref", "source_ref"),
            ("cell", "cell"),
        ],
    )
    def test_each_missing_facet_is_rejected(self, facet: str, needle: str) -> None:
        payload = xlsx_payload()
        first_field(payload).pop(facet)
        with pytest.raises(C.ContractSchemaError) as ei:
            C.parse_contract(payload)
        assert needle in str(ei.value), (
            f"抽掉 {facet} 之后的错误文案必须能指向它，实得: {ei.value}"
        )

    def test_docx_missing_sdt_tag_is_rejected(self) -> None:
        payload = docx_payload()
        payload["fields"][0].pop("sdt_tag")
        with pytest.raises(C.ContractSchemaError, match="sdt_tag"):
            C.parse_contract(payload)

    def test_missing_facet_messages_are_pairwise_distinct(self) -> None:
        """六个面的错误文案两两不同 —— 否则「到底缺哪一项」不可分辨。"""
        messages: dict[str, str] = {}
        for facet in (
            "stable_field_key", "json_pointer", "mode", "value_type", "source_ref", "cell",
        ):
            payload = xlsx_payload()
            first_field(payload).pop(facet)
            with pytest.raises(C.ContractSchemaError) as ei:
                C.parse_contract(payload)
            messages[facet] = str(ei.value)
        assert len(set(messages.values())) == len(messages), (
            f"文案重复，无法定位缺失面: {messages}"
        )

    @pytest.mark.parametrize("mode", ["editable", "auto_source"])
    def test_every_mode_field_still_needs_cell(self, mode: str) -> None:
        """不只 editable —— formula/auto_source 也必须有 OO 位置，否则保护无处施加。"""
        payload = xlsx_payload()
        field = first_field(payload)
        field["mode"] = mode
        field.pop("cell")
        with pytest.raises(C.ContractSchemaError, match="cell"):
            C.parse_contract(payload)

    def test_unknown_mode_and_value_type_are_closed_enums(self) -> None:
        payload = xlsx_payload()
        first_field(payload)["mode"] = "writable"
        with pytest.raises(C.ContractSchemaError, match="mode 未登记"):
            C.parse_contract(payload)
        payload = xlsx_payload()
        first_field(payload)["value_type"] = "money"
        with pytest.raises(C.ContractSchemaError, match="value_type 未登记"):
            C.parse_contract(payload)

    def test_editable_and_protected_keys_are_partitioned(self) -> None:
        contract = C.parse_contract(xlsx_payload())
        editable = set(contract.editable_field_keys())
        protected = set(contract.protected_field_keys())
        assert editable and protected
        assert not (editable & protected), "editable 与 protected 必须互斥"
        assert editable | protected == {f.stable_field_key for f in contract.all_fields()}

    @pytest.mark.parametrize(
        ("pointer", "needle"),
        [
            ("rows/closingAmount", "必须以"),      # 缺前导 /
            ("/rows/closingAmount/", "结尾"),      # 尾随 /
            ("/rows//closingAmount", "空 token"),  # 空 token
            ("", "缺失或为空"),                     # 空串
        ],
    )
    def test_json_pointer_must_be_rfc6901(self, pointer: str, needle: str) -> None:
        """🔴 反例落在**非行域**字段上，且断言各自的专属文案。

        首轮实测教训：把这些反例挂在行域字段上时，`{row_uuid}` 缺失判据会先抛
        （消息里也含「JSON Pointer」），于是关掉任一形态判据都不会打红 ⇒ 变异 GREEN。
        判据必须落在**能区分彼此**的文案上。
        """
        payload = xlsx_payload()
        payload["sheets"][0]["tables"][1]["fields"][0]["json_pointer"] = pointer
        with pytest.raises(C.ContractSchemaError, match=needle):
            C.parse_contract(payload)

    def test_json_pointer_tilde_escape_is_its_own_judgement(self) -> None:
        """RFC 6901 的 `~0`/`~1` 转义是独立一条 —— 断言它自己的文案。"""
        payload = xlsx_payload()
        payload["sheets"][0]["tables"][1]["fields"][0]["json_pointer"] = "/header/~2bad"
        with pytest.raises(C.ContractSchemaError, match="~0"):
            C.parse_contract(payload)

    def test_row_scoped_pointer_needs_exactly_one_row_placeholder(self) -> None:
        payload = xlsx_payload()
        first_field(payload)["json_pointer"] = "/rows/closingAmount"
        with pytest.raises(C.ContractSchemaError, match="row_uuid"):
            C.parse_contract(payload)

    def test_non_row_field_must_not_carry_row_placeholder(self) -> None:
        payload = xlsx_payload()
        payload["sheets"][0]["tables"][1]["fields"][0]["json_pointer"] = (
            "/header/{row_uuid}/periodLabel"
        )
        with pytest.raises(C.ContractSchemaError, match="不得含"):
            C.parse_contract(payload)

    def test_wildcard_only_allowed_in_row_identity(self) -> None:
        payload = xlsx_payload()
        first_field(payload)["json_pointer"] = "/rows/*/closingAmount"
        with pytest.raises(C.ContractSchemaError, match=r"row_identity"):
            C.parse_contract(payload)
        # row_identity 侧必须恰好一个 `*`
        payload = xlsx_payload()
        first_table(payload)["row_identity"]["json_pointer"] = "/rows/*/*/rowUuid"
        with pytest.raises(C.ContractSchemaError, match="恰好一个"):
            C.parse_contract(payload)

    def test_row_scoped_cell_must_not_hardcode_row_number(self) -> None:
        payload = xlsx_payload()
        first_field(payload)["cell"]["row_from"] = 8
        with pytest.raises(C.ContractSchemaError, match="不得写死行号"):
            C.parse_contract(payload)

    def test_static_field_must_not_claim_row_identity(self) -> None:
        payload = xlsx_payload()
        payload["sheets"][0]["tables"][1]["fields"][0]["cell"]["row_from"] = "row_identity"
        with pytest.raises(C.ContractSchemaError, match="row_identity"):
            C.parse_contract(payload)

    def test_non_ascii_identity_is_rejected(self) -> None:
        """identity 不得依赖中文 label（Requirement 6.14）。"""
        payload = xlsx_payload()
        first_field(payload)["stable_field_key"] = "权益变动/期末金额"
        with pytest.raises(C.ContractSchemaError, match="非 ASCII"):
            C.parse_contract(payload)
        payload = docx_payload()
        payload["fields"][0]["sdt_tag"] = "gt:field:f2.stocktake.plan:监盘地点"
        with pytest.raises(C.ContractSchemaError, match="非 ASCII"):
            C.parse_contract(payload)

    def test_duplicate_stable_keys_rejected_within_and_across_tables(self) -> None:
        payload = xlsx_payload()
        table = first_table(payload)
        table["fields"].append(dict(table["fields"][0]))
        with pytest.raises(C.ContractSchemaError, match="重复"):
            C.parse_contract(payload)
        payload = xlsx_payload()
        payload["sheets"][0]["tables"][1]["fields"][0]["stable_field_key"] = (
            "equity_changes/{row_uuid}/closing_amount"
        )
        with pytest.raises(C.ContractSchemaError, match="重复"):
            C.parse_contract(payload)

    @pytest.mark.parametrize("header_rows", [0, 4, "2", True])
    def test_header_rows_domain(self, header_rows: Any) -> None:
        payload = xlsx_payload()
        first_table(payload)["header_rows"] = header_rows
        with pytest.raises(C.ContractSchemaError, match="header_rows"):
            C.parse_contract(payload)

    def test_float_header_rows_is_rejected_earlier_by_cross_language_gate(self) -> None:
        """`2.0` 不是「域外整数」而是 float ⇒ 由更早的跨语言判据拦下（XL-6）。

        两条判据的顺序有语义：float 在 Python 与 JS 的 repr 会分叉，所以它必须在
        canonicalization **之前**被拒，而不是等到「header_rows 必须是 1..3 整数」。
        """
        payload = xlsx_payload()
        first_table(payload)["header_rows"] = 2.0
        with pytest.raises(XL.CrossLanguageCanonicalError, match="XL-6"):
            C.parse_contract(payload)

    def test_two_level_header_is_expressible(self) -> None:
        """Requirement 6.3：contract 必须能表达两级表头。"""
        contract = C.parse_contract(xlsx_payload())
        table = contract.sheets[0].tables[0]
        assert table.header_rows == 2
        assert table.two_level_header is True
        assert contract.sheets[0].tables[1].two_level_header is False

    def test_structure_facets_required_by_ac_6_3_are_all_parsed(self) -> None:
        """merge/公式 mask/动态行列/footer anchor/删除策略/row identity 全部落库。"""
        table = C.parse_contract(xlsx_payload()).sheets[0].tables[0]
        assert table.formula_mask == ("I8:I200",)
        assert table.row_identity is not None
        assert table.row_identity.kind is C.RowIdentityKind.field
        assert table.dynamic_columns is not None
        assert table.dynamic_columns.identity == C.DYNAMIC_COLUMN_IDENTITY_TEMPLATE
        assert table.footer_anchor is not None
        assert table.footer_anchor.marker == "合计"
        assert table.delete_policy is C.DeletePolicy.tombstone
        assert table.has_dynamic_rows is True


# ═══════════════════════════════════════════════════════════════════════════
# Property 20：generated col 占位不可注册生产 adapter
# ═══════════════════════════════════════════════════════════════════════════


class TestProperty20GeneratedColumnPlaceholder:
    """`col_[a-z]+` 无条件被拒；「缺 source_ref」是另一条独立判据。"""

    @pytest.mark.parametrize("placeholder", ["col_a", "col_b", "col_bc", "col_zzz"])
    def test_col_placeholder_in_stable_key_rejected(self, placeholder: str) -> None:
        payload = xlsx_payload()
        first_field(payload)["stable_field_key"] = f"equity_changes/{{row_uuid}}/{placeholder}"
        first_field(payload)["json_pointer"] = f"/rows/{{row_uuid}}/{placeholder}"
        with pytest.raises(C.ContractSchemaError, match="col_"):
            C.parse_contract(payload)

    def test_col_placeholder_rejected_even_with_full_source_ref(self) -> None:
        """🔴 Property 20 的关键：**有** source_ref 也不放行。

        Property 20 原文是「含无语义 col_* **且**无人工 stable key/source_ref 时失败」，
        但两者合成一条之后，把 col 形态检查删掉仍会被 source_ref 缺失挡住 ⇒ 变异 GREEN。
        故实现对 col 形态无条件拒绝，本例正是那条独立判据的反例。
        """
        payload = xlsx_payload()
        field = first_field(payload)
        field["stable_field_key"] = "equity_changes/{row_uuid}/col_h"
        field["json_pointer"] = "/rows/{row_uuid}/col_h"
        field["source_ref"] = "源xlsx!H8"       # 来源齐全
        field["column_key"] = "closing_amount"  # 列名已人工命名
        with pytest.raises(C.ContractSchemaError, match="col_"):
            C.parse_contract(payload)

    def test_col_placeholder_in_column_key_rejected(self) -> None:
        payload = xlsx_payload()
        first_field(payload)["column_key"] = "col_h"
        with pytest.raises(C.ContractSchemaError, match="col_"):
            C.parse_contract(payload)

    def test_col_placeholder_in_table_and_sheet_key_rejected(self) -> None:
        payload = xlsx_payload()
        first_table(payload)["table_key"] = "col_a"
        with pytest.raises(C.ContractSchemaError, match="col_"):
            C.parse_contract(payload)
        payload = xlsx_payload()
        payload["sheets"][0]["sheet_key"] = "col_ab"
        with pytest.raises(C.ContractSchemaError, match="col_"):
            C.parse_contract(payload)

    def test_missing_source_ref_is_an_independent_judgement(self) -> None:
        """键完全语义化、只缺 source_ref ⇒ 仍拒（无来源自造字段）。"""
        payload = xlsx_payload()
        field = first_field(payload)
        assert "col_" not in field["stable_field_key"]
        field.pop("source_ref")
        with pytest.raises(C.ContractSchemaError, match="source_ref"):
            C.parse_contract(payload)

    def test_dynamic_columns_source_ref_required(self) -> None:
        payload = xlsx_payload()
        first_table(payload)["dynamic_columns"].pop("source_ref")
        with pytest.raises(C.ContractSchemaError, match="source_ref"):
            C.parse_contract(payload)

    def test_semantic_column_key_is_accepted(self) -> None:
        """判据不是「凡带 col 就拒」—— `column_key` 语义命名必须通过。"""
        contract = C.parse_contract(xlsx_payload())
        keys = {f.column_key for f in contract.sheets[0].tables[0].fields}
        assert keys == {"closing_amount", "subtotal"}

    def test_candidate_contract_cannot_register(self) -> None:
        """generator 只产候选；未经人工审核不得注册生产 adapter。"""
        payload = xlsx_payload()
        payload["review_status"] = "candidate"
        with pytest.raises(C.ContractSchemaError, match="review_status"):
            C.parse_contract(payload)

    def test_shipped_example_candidate_is_rejected_by_the_real_parser(self) -> None:
        """磁盘上的候选示例必须被真解析器拒绝（不是只在文档里说）。"""
        example = C.CONTRACTS_DIR / "_example.candidate.json"
        assert example.is_file(), "候选示例缺失，Property 20 的磁盘反例消失"
        payload = json.loads(example.read_text(encoding="utf-8"))
        with pytest.raises(C.ContractSchemaError, match="review_status"):
            C.parse_contract(payload)

    def test_example_candidate_is_excluded_from_production_inventory(self) -> None:
        """`_` 前缀文件不进生产清册 —— 否则会被报成「有契约无 adapter」的伪欠账。"""
        assert "_example.candidate" not in C.available_contract_ids()


# ═══════════════════════════════════════════════════════════════════════════
# contract 结构判据（Requirement 6.3 / 6.4 / 6.5 / 6.6 / 6.9）
# ═══════════════════════════════════════════════════════════════════════════


class TestContractStructuralRules:
    @pytest.mark.parametrize(
        "kind", sorted(C.FORBIDDEN_ROW_IDENTITY_KINDS)
    )
    def test_positional_row_identity_rejected(self, kind: str) -> None:
        payload = xlsx_payload()
        first_table(payload)["row_identity"] = {"kind": kind}
        with pytest.raises(C.ContractSchemaError, match="位置/下标"):
            C.parse_contract(payload)

    def test_template_row_key_identity_requires_key(self) -> None:
        payload = xlsx_payload()
        first_table(payload)["row_identity"] = {"kind": "template_row_key"}
        with pytest.raises(C.ContractSchemaError, match="template_row_key"):
            C.parse_contract(payload)

    @pytest.mark.parametrize(
        "identity", ["{slot}", "{seq}", "公司{seq}", "{slot}-{seq}", "{label}_{seq}"]
    )
    def test_dynamic_column_identity_must_be_exact_template(self, identity: str) -> None:
        payload = xlsx_payload()
        first_table(payload)["dynamic_columns"]["identity"] = identity
        with pytest.raises(C.ContractSchemaError, match=r"\{slot\}_\{seq\}"):
            C.parse_contract(payload)

    @pytest.mark.parametrize("forbidden", ["row", "row_index", "row_number"])
    def test_footer_anchor_must_not_hardcode_row(self, forbidden: str) -> None:
        payload = xlsx_payload()
        first_table(payload)["footer_anchor"][forbidden] = 200
        with pytest.raises(C.ContractSchemaError, match="写死行号"):
            C.parse_contract(payload)

    def test_formula_field_must_be_covered_by_formula_mask(self) -> None:
        payload = xlsx_payload()
        first_table(payload)["formula_mask"] = ["K8:K200"]
        with pytest.raises(C.ContractSchemaError, match="formula_mask"):
            C.parse_contract(payload)

    def test_formula_field_without_any_mask_rejected(self) -> None:
        payload = xlsx_payload()
        first_table(payload).pop("formula_mask")
        with pytest.raises(C.ContractSchemaError, match="formula_mask"):
            C.parse_contract(payload)

    def test_dynamic_rows_require_delete_policy_and_vice_versa(self) -> None:
        payload = xlsx_payload()
        first_table(payload).pop("delete_policy")
        with pytest.raises(C.ContractSchemaError, match="delete_policy"):
            C.parse_contract(payload)
        payload = xlsx_payload()
        payload["sheets"][0]["tables"][1]["delete_policy"] = "tombstone"
        with pytest.raises(C.ContractSchemaError, match="row_identity"):
            C.parse_contract(payload)

    @pytest.mark.parametrize("bad", ["I8:I", "8:200", "i8:i200", "AAAA8", ""])
    def test_formula_mask_a1_range_form(self, bad: str) -> None:
        payload = xlsx_payload()
        first_table(payload)["formula_mask"] = [bad]
        with pytest.raises(C.ContractSchemaError, match="A1"):
            C.parse_contract(payload)

    def test_document_type_crossover_is_rejected_four_ways(self) -> None:
        """xlsx↔docx 串用的四个方向各自有独立判据。"""
        payload = xlsx_payload()
        first_field(payload)["sdt_tag"] = "gt:field:g7.disclosure.listed:x"
        with pytest.raises(C.ContractSchemaError, match="sdt_tag"):
            C.parse_contract(payload)

        payload = xlsx_payload()
        payload["fields"] = [dict(first_field(xlsx_payload()))]
        with pytest.raises(C.ContractSchemaError, match="顶层"):
            C.parse_contract(payload)

        payload = docx_payload()
        payload["fields"][0]["cell"] = {"column": "H", "row_from": 8}
        with pytest.raises(C.ContractSchemaError, match="cell"):
            C.parse_contract(payload)

        payload = docx_payload()
        payload["sheets"] = xlsx_payload()["sheets"]
        with pytest.raises(C.ContractSchemaError, match="sheets"):
            C.parse_contract(payload)

    def test_word_only_mode_rejected_in_xlsx(self) -> None:
        payload = xlsx_payload()
        first_field(payload)["mode"] = "word_only"
        with pytest.raises(C.ContractSchemaError, match="word_only"):
            C.parse_contract(payload)

    def test_sdt_tag_must_bind_contract_id(self) -> None:
        payload = docx_payload()
        payload["fields"][0]["sdt_tag"] = "gt:field:other.contract:plan/location"
        with pytest.raises(C.ContractSchemaError, match="contract"):
            C.parse_contract(payload)

    def test_row_scoped_docx_field_tag_must_carry_row_uuid(self) -> None:
        """row 级 SDT 在 OO 9.4 上失效 ⇒ 行身份必须由单元格内 field SDT tag 承载。"""
        payload = docx_payload()
        payload["repeaters"][0]["sdt_tag"] = "gt:field:f2.stocktake.plan:plan/members/name"
        with pytest.raises(C.ContractSchemaError, match="row_uuid"):
            C.parse_contract(payload)

    def test_contract_id_must_match_adapter_id(self) -> None:
        with pytest.raises(C.ContractSchemaError, match="adapter_id"):
            C.parse_contract(xlsx_payload(), adapter_id="other.adapter")

    def test_template_path_traversal_rejected(self) -> None:
        for bad in ("/abs/G7.xlsx", "../outside/G7.xlsx", "G/../../etc/passwd"):
            payload = xlsx_payload()
            payload["template"]["relative_path"] = bad
            with pytest.raises(C.ContractSchemaError, match="relative_path"):
                C.parse_contract(payload)

    def test_template_digests_must_be_real_digests(self) -> None:
        from app.services.workpaper_sync.models import IdentityError

        for name in ("template_sha256", "normalized_structure_hash"):
            payload = xlsx_payload()
            payload["template"][name] = "0" * 64
            with pytest.raises(IdentityError, match=name):
                C.parse_contract(payload)

    def test_sheet_and_table_must_be_non_empty(self) -> None:
        payload = xlsx_payload()
        payload["sheets"] = []
        with pytest.raises(C.ContractSchemaError, match="sheet"):
            C.parse_contract(payload)
        payload = xlsx_payload()
        payload["sheets"][0]["tables"] = []
        with pytest.raises(C.ContractSchemaError, match="table"):
            C.parse_contract(payload)
        payload = xlsx_payload()
        first_table(payload)["fields"] = []
        with pytest.raises(C.ContractSchemaError, match="field"):
            C.parse_contract(payload)


# ═══════════════════════════════════════════════════════════════════════════
# Requirement 6.16 / 6.20：identity 载体 probe gate 与 extract 载体优先级
# ═══════════════════════════════════════════════════════════════════════════


class TestCarrierProbeGate:
    """载体/锚点 allowlist 的真源是 Task 5/6 的真实 OO 9.4 探针裁决，不是代码常量。"""

    def test_gate_allowlist_comes_from_probe_contract_files(self) -> None:
        xlsx_gate = C.load_excel_carrier_gate()
        docx_gate = C.load_word_carrier_gate()
        assert xlsx_gate.source_path.is_file() and docx_gate.source_path.is_file()
        for gate in (xlsx_gate, docx_gate):
            assert gate.allowed_carriers, "allowlist 为空等于放行一切"
            assert gate.allowed_anchors
            assert gate.verdicts, "每个载体/锚点必须有机器可读 probe_verdict"

    def test_allowlist_is_not_hardcoded_in_module_source(self) -> None:
        """反向自检：载体名单若被复制进代码，探针裁决就不再是唯一真源。"""
        body = _stripped(_CONTRACTS_PY)
        for carrier in ("hidden_uuid_column", "excel_table", "field_sdt_block"):
            assert f'"{carrier}"' not in body, (
                f"载体 {carrier!r} 出现在 contracts.py 源码里 —— allowlist 必须只从 "
                "probe 契约 JSON 读"
            )

    def test_failed_word_row_sdt_carrier_is_rejected(self) -> None:
        """design.md 的 Word 示例用 row 级 SDT，但它在 OO 9.4 上 failed ⇒ 必须拒。

        🔴 断言 **blocklist 专属文案**而不只是载体名：blocklist 与 allowlist 两条分支
        抛同一异常类型、消息里都带载体名，只断言名字会让「关掉 blocklist 判据」被
        allowlist 分支遮蔽 ⇒ 变异 GREEN（首轮实测）。
        """
        payload = docx_payload()
        payload["identity_carriers"] = ["row_sdt"]
        with pytest.raises(C.ContractCarrierGateError) as ei:
            C.parse_contract(payload)
        message = str(ei.value)
        assert "row_sdt" in message
        assert "blocklist" in message, (
            f"必须由 blocklist 判据拒绝（而非兜底 allowlist），实得: {message}"
        )
        assert C.load_word_carrier_gate().verdicts["row_sdt"] == "failed"

    @pytest.mark.parametrize("anchor", ["sheet_id", "sheet_display_name"])
    def test_failed_excel_anchors_are_rejected(self, anchor: str) -> None:
        payload = xlsx_payload()
        payload["sheets"][0]["locator"]["anchor"] = anchor
        with pytest.raises(C.ContractCarrierGateError) as ei:
            C.parse_contract(payload)
        message = str(ei.value)
        assert anchor in message
        assert "blocklist" in message, (
            f"必须由 blocklist 判据拒绝（而非兜底 allowlist），实得: {message}"
        )

    def test_unregistered_carrier_is_rejected(self) -> None:
        payload = xlsx_payload()
        payload["identity_carriers"] = ["magic_marker_column"]
        with pytest.raises(C.ContractCarrierGateError, match="未在"):
            C.parse_contract(payload)

    def test_empty_carrier_list_is_rejected(self) -> None:
        payload = xlsx_payload()
        payload["identity_carriers"] = []
        with pytest.raises(C.ContractSchemaError, match="identity_carriers"):
            C.parse_contract(payload)

    def test_sheet_locator_required(self) -> None:
        payload = xlsx_payload()
        payload["sheets"][0].pop("locator")
        with pytest.raises(C.ContractSchemaError, match="locator"):
            C.parse_contract(payload)

    def test_gate_errors_are_distinguishable_from_schema_errors(self) -> None:
        """载体未过门（契约错）与运行态无载体（运行错）必须是两类异常。"""
        assert issubclass(C.ContractCarrierGateError, C.ContractError)
        assert issubclass(C.ContractCarrierUnavailableError, C.ContractError)
        assert not issubclass(C.ContractCarrierUnavailableError, C.ContractCarrierGateError)
        assert not issubclass(C.ContractCarrierGateError, C.ContractCarrierUnavailableError)

    def test_extract_carrier_tier_prefers_instrumented_identity(self) -> None:
        contract = C.parse_contract(xlsx_payload())
        assert (
            contract.resolve_extract_carrier(
                instrumented_identity_present=True, native_anchors_present=True
            )
            is C.ExtractCarrierTier.instrumented_identity
        )
        assert (
            contract.resolve_extract_carrier(
                instrumented_identity_present=False, native_anchors_present=True
            )
            is C.ExtractCarrierTier.native_structural_anchor
        )

    def test_extract_fails_closed_without_any_carrier(self) -> None:
        """Requirement 6.20：两者均不存在时 fail closed，不得降级中文标题/位置猜测。"""
        contract = C.parse_contract(xlsx_payload())
        with pytest.raises(C.ContractCarrierUnavailableError, match="fail closed"):
            contract.resolve_extract_carrier(
                instrumented_identity_present=False, native_anchors_present=False
            )


# ═══════════════════════════════════════════════════════════════════════════
# Requirement 6.2 / 6.14 / 9.8：发布 DAG 与 contract payload 的引用方向
# ═══════════════════════════════════════════════════════════════════════════


class TestPublishDagAndReferenceDirection:
    """`template → instrumentation → contract → bundle → representation` 单向。"""

    def test_dag_is_the_fixed_five_stage_chain(self) -> None:
        assert [stage.value for stage in D.PUBLISH_DAG] == [
            "template", "instrumentation", "contract", "bundle", "representation",
        ]

    def test_contract_requires_published_template_and_instrumentation(self) -> None:
        with pytest.raises(D.PublishOrderError, match="template"):
            D.assert_publish_order(stage="contract", approved_stages={"instrumentation"})
        with pytest.raises(D.PublishOrderError, match="instrumentation"):
            D.assert_publish_order(stage="contract", approved_stages={"template"})
        D.assert_publish_order(stage="contract", approved_stages={"template", "instrumentation"})

    def test_bundle_comes_after_contract_and_representation_last(self) -> None:
        with pytest.raises(D.PublishOrderError, match="contract"):
            D.assert_publish_order(stage="bundle", approved_stages={"template", "instrumentation"})
        D.assert_publish_order(
            stage="bundle", approved_stages={"template", "instrumentation", "contract"}
        )
        with pytest.raises(D.PublishOrderError, match="bundle"):
            D.assert_publish_order(
                stage="representation",
                approved_stages={"template", "instrumentation", "contract"},
            )

    def test_contract_payload_must_reference_both_child_digests(self) -> None:
        for key in ("template_definition_sha256", "instrumentation_definition_sha256"):
            payload = xlsx_payload()
            payload.pop(key)
            with pytest.raises(Exception) as ei:
                C.parse_contract(payload)
            assert key in str(ei.value), (
                f"缺 {key} 的错误文案必须指向它，实得: {ei.value}"
            )

    @pytest.mark.parametrize(
        "self_key", ["definition_artifact_id", "definition_sha256", "artifact_id", "sha256", "id"]
    )
    def test_contract_payload_must_not_embed_self_identity(self, self_key: str) -> None:
        """AC 6.2：payload 禁止内嵌自身 artifact UUID/hash（含 definition identity）。"""
        payload = xlsx_payload()
        payload[self_key] = _d("self")
        with pytest.raises(Exception) as ei:
            C.parse_contract(payload)
        assert "自" in str(ei.value) or "self" in str(ei.value).lower(), (
            f"自引用 {self_key} 的拒绝文案不可辨识: {ei.value}"
        )

    def test_self_identity_is_rejected_even_when_nested(self) -> None:
        """判据是递归的 —— 塞进嵌套结构里同样必须拒。"""
        payload = xlsx_payload()
        payload["sheets"][0]["definition_artifact_id"] = str(uuid.uuid4())
        with pytest.raises(Exception):
            C.parse_contract(payload)

    @pytest.mark.parametrize(
        "forward_key", ["definition_bundle_sha256", "bundle_sha256", "definition_bundle_id"]
    )
    def test_contract_payload_must_not_forward_reference_bundle(self, forward_key: str) -> None:
        payload = xlsx_payload()
        payload[forward_key] = _d("bundle")
        with pytest.raises(Exception) as ei:
            C.parse_contract(payload)
        assert forward_key.split("_")[0] in str(ei.value) or "bundle" in str(ei.value)

    def test_instrumentation_payload_must_not_backward_reference_contract(self) -> None:
        """instrumentation 禁止反向引用 contract/bundle digest（AC 6.14）。"""
        base = {
            "schema_version": "instrumentation-definition:v1",
            "template_definition_sha256": TEMPLATE_DEF,
            "template_sha256": _d("template-blob"),
            "instrumentation_version": "1.0.0",
            "identity_schema_version": "1.0.0",
        }
        D.validate_instrumentation_payload(dict(base))
        for backward in ("contract_definition_sha256", "definition_bundle_sha256", "bundle_id"):
            payload = dict(base)
            payload[backward] = _d(backward)
            with pytest.raises(Exception):
                D.validate_instrumentation_payload(payload)

    def test_parse_contract_delegates_payload_level_rules(self) -> None:
        """结构判据：字段级校验器不重写 payload 级判据（单一真源在 definitions）。"""
        body = _stripped(_CONTRACTS_PY)
        assert "validate_contract_payload(payload)" in body, (
            "contracts.parse_contract 必须委托 definitions.validate_contract_payload"
        )
        assert "_SELF_REFERENCE_KEYS" not in body, (
            "自引用键名单不得在 contracts.py 复制一份 —— 两份重合实现让任一侧被短路都"
            "不改变行为（变异必 GREEN）"
        )

    def test_contract_schema_version_is_pinned(self) -> None:
        payload = xlsx_payload()
        payload["schema_version"] = "contract-definition:v2"
        with pytest.raises(C.ContractSchemaError, match="schema_version"):
            C.parse_contract(payload)


# ═══════════════════════════════════════════════════════════════════════════
# Requirement 6.2：统一 canonicalizer 的跨语言等价
# ═══════════════════════════════════════════════════════════════════════════


class TestCrossLanguageCanonicalizer:
    """golden bytes、键序/换行扰动、typed marker 版本变化与非法空值反例。"""

    def test_golden_fixture_is_fresh(self) -> None:
        """磁盘 fixture 必须与当前 `canonical_json_bytes` 逐字节一致（新鲜度）。"""
        document = XL.load_golden_document()
        assert document["cases"], "golden 用例为空 = 无判据"
        for case in document["cases"]:
            raw = D.canonical_json_bytes(case["payload"])
            assert raw.hex() == case["canonical_utf8_hex"], (
                f"golden 用例 {case['case_id']} 的期望字节已过期 —— 重跑 "
                "generate_workpaper_sync_canonical_golden.py --apply"
            )
            assert hashlib.sha256(raw).hexdigest() == case["canonical_sha256"]

    def test_golden_fixture_declares_both_canonicalizers(self) -> None:
        document = XL.load_golden_document()
        assert document["python_canonicalizer"] == (
            "app.services.workpaper_sync.definitions.canonical_json_bytes"
        )
        assert document["typescript_canonicalizer"] == (
            "audit-platform/frontend/src/components/workpaper/sync/canonicalJson.ts"
        )
        assert _TS_CANONICALIZER.is_file(), "TS 侧 canonicalizer 缺失 ⇒ 跨语言判据只剩一侧"

    def test_ts_canonicalizer_shares_the_same_numeric_domain(self) -> None:
        """两侧的 `MAX_SAFE_INTEGER` 必须同值，否则 XL-3 的门限一侧宽一侧紧。"""
        ts = _read(_TS_CANONICALIZER)
        assert "Number.MAX_SAFE_INTEGER" in ts
        assert XL.MAX_SAFE_INTEGER == 2**53 - 1
        assert XL.load_golden_document()["max_safe_integer"] == XL.MAX_SAFE_INTEGER

    def test_ts_canonicalizer_does_not_use_default_sort(self) -> None:
        """JS 默认 `sort()` 是 UTF-16 code unit 序，对星平面字符与 Python 相反。

        🔴 必须先剥注释：`canonicalJson.ts` 的模块注释里正解释了「不能用
        `Array.prototype.sort()`」，直接扫全文会把这句说明数成真实代码（假红）。
        """
        code = _strip_ts_comments(_read(_TS_CANONICALIZER))
        assert "compareByCodePoint" in code
        assert re.search(r"\.sort\(\s*\)", code) is None, (
            "TS 侧出现裸 `.sort()` —— 必须显式传 code-point 比较器"
        )

    def test_ts_comment_stripper_self_check(self) -> None:
        """反向自检：剥注释确实剥掉了注释、也确实保留了代码。"""
        code = _strip_ts_comments(_read(_TS_CANONICALIZER))
        assert "Array.prototype.sort()" not in code, "块注释未被剥掉 ⇒ 上一条判据会假红"
        assert "export function canonicalJsonText" in code, "代码被误剥 ⇒ 判据会假绿"
        sample = _strip_ts_comments(
            'const a = 1 // .sort()\n/* .sort() */\nconst b = "http://x//y" // t\n'
        )
        assert ".sort()" not in sample
        assert 'const b = "http://x//y"' in sample, "字符串字面量里的 `//` 不得被当注释"

    def test_key_order_perturbation_is_byte_stable(self) -> None:
        a = D.canonical_json_bytes({"z": 1, "a": 2, "m": {"y": 1, "x": 2}})
        b = D.canonical_json_bytes({"m": {"x": 2, "y": 1}, "a": 2, "z": 1})
        assert a == b

    def test_newline_inside_values_is_significant_not_normalized(self) -> None:
        """换行扰动：字符串内的换行是**语义**，不得被规范化掉。

        与「键序扰动不改变字节」是相反方向的两条判据：键序无语义所以必须归一，
        值内换行有语义所以必须保留。只测一条会让另一条被静默改坏。
        """
        lf = D.canonical_json_bytes({"s": "a\nb"})
        crlf = D.canonical_json_bytes({"s": "a\r\nb"})
        assert lf != crlf
        assert lf == b'{"s":"a\\nb"}'
        assert crlf == b'{"s":"a\\r\\nb"}'

    def test_canonical_bytes_have_no_incidental_whitespace(self) -> None:
        assert D.canonical_json_bytes({"a": 1, "b": [1, 2]}) == b'{"a":1,"b":[1,2]}'

    def test_chinese_is_not_escaped(self) -> None:
        assert D.canonical_json_bytes({"u": "元"}) == '{"u":"元"}'.encode("utf-8")

    @pytest.mark.parametrize(
        "kind",
        [kind for kind, _note, langs in XL.REJECT_KINDS if "python" in langs],
    )
    def test_every_registered_reject_kind_is_rejected(self, kind: str) -> None:
        payload = XL.build_reject_payload(kind)
        with pytest.raises(XL.CrossLanguageCanonicalError):
            XL.assert_cross_language_safe(payload)

    def test_reject_kind_messages_carry_distinct_xl_classes(self) -> None:
        """不同 XL 分类的文案必须不同 —— 否则删一条会被另一条遮蔽。"""
        classes = {
            "nan": "XL-1", "positive_infinity": "XL-1", "negative_infinity": "XL-1",
            "negative_zero": "XL-2", "unsafe_integer": "XL-3", "lone_surrogate": "XL-4",
            "non_string_key": "XL-5", "plain_float": "XL-6", "exponential_float": "XL-6",
        }
        seen: dict[str, set[str]] = {}
        for kind, label in classes.items():
            with pytest.raises(XL.CrossLanguageCanonicalError) as ei:
                XL.assert_cross_language_safe(XL.build_reject_payload(kind))
            assert label in str(ei.value), f"{kind} 的文案缺 {label} 标记: {ei.value}"
            seen.setdefault(label, set()).add(str(ei.value))
        assert len(seen) == len({*classes.values()})

    def test_reject_kinds_cover_both_languages(self) -> None:
        langs = {lang for _kind, _note, ls in XL.REJECT_KINDS for lang in ls}
        assert langs == {"python", "typescript"}
        python_only = [k for k, _n, ls in XL.REJECT_KINDS if ls == ("python",)]
        ts_only = [k for k, _n, ls in XL.REJECT_KINDS if ls == ("typescript",)]
        assert "non_string_key" in python_only, "非字符串键只存在于 Python 侧"
        assert "undefined_value" in ts_only, "undefined 只存在于 TS 侧"

    def test_boundary_integers_are_allowed(self) -> None:
        XL.assert_cross_language_safe({"v": XL.MAX_SAFE_INTEGER})
        XL.assert_cross_language_safe({"v": -XL.MAX_SAFE_INTEGER})
        with pytest.raises(XL.CrossLanguageCanonicalError, match="XL-3"):
            XL.assert_cross_language_safe({"v": XL.MAX_SAFE_INTEGER + 1})

    def test_contract_payload_goes_through_the_cross_language_gate(self) -> None:
        """接线判据：不安全值塞进真实契约 payload 必须在解析期被拒。"""
        for kind in ("plain_float", "lone_surrogate", "unsafe_integer", "nan"):
            payload = xlsx_payload()
            payload["semantic_version_probe"] = XL.build_reject_payload(kind)["v"]
            with pytest.raises(XL.CrossLanguageCanonicalError):
                C.parse_contract(payload)

    def test_contract_canonical_digest_is_reproducible_across_key_order(self) -> None:
        """同一 semantic payload 在不同环境（键序不同）必须得到相同 SHA。"""
        payload = xlsx_payload()
        shuffled = {key: payload[key] for key in reversed(list(payload))}
        assert C.parse_contract(payload).canonical_sha256 == (
            C.parse_contract(shuffled).canonical_sha256
        )

    def test_typed_marker_version_change_changes_digest(self) -> None:
        """typed null marker 版本变化 ⇒ digest 必变（不能悄悄兼容）。"""
        v1 = D.marker_canonical_payload(BundleSlot.contract)
        v2 = {**v1, "schema_version": "definition-bundle-marker:v2"}
        assert D.canonical_digest(v1) != D.canonical_digest(v2)
        assert D.marker_digest(BundleSlot.contract) == D.canonical_digest(v1)

    def test_unregistered_marker_version_is_rejected(self) -> None:
        with pytest.raises(BundleIntegrityError):
            D.marker_for(BundleSlot.contract, version=2)


# ═══════════════════════════════════════════════════════════════════════════
# Requirement 6.2 / 6.19：bundle schema 的 typed canonical slots
# ═══════════════════════════════════════════════════════════════════════════


def _bundle_kwargs(**over: Any) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "authority_model": AuthorityModel.projection_contract,
        "authority_model_definition_sha256": AUTHORITY_DEF,
        "slots": {
            BundleSlot.template: def_slot(BundleSlot.template, TEMPLATE_DEF),
            BundleSlot.instrumentation: def_slot(BundleSlot.instrumentation, INSTR_DEF),
            BundleSlot.contract: def_slot(BundleSlot.contract, _d("contract")),
        },
    }
    kwargs.update(over)
    return kwargs


class TestBundleSchemaFailClosed:
    """authority model + 三类 typed canonical slots 全部强制；非法空值立即拒绝。"""

    def test_projection_contract_bundle_payload_shape(self) -> None:
        payload = D.build_bundle_canonical_payload(**_bundle_kwargs())
        assert payload["schema_version"] == "definition-bundle:v1"
        assert set(payload) == {
            "schema_version", "authority_model", "template", "instrumentation", "contract",
        }
        assert payload["authority_model"] == {"type": "definition", "sha256": AUTHORITY_DEF}
        for slot in BundleSlot:
            assert payload[slot.value]["type"] == "definition"
            assert re.fullmatch(r"[0-9a-f]{64}", payload[slot.value]["sha256"])

    @pytest.mark.parametrize("dropped", list(BundleSlot))
    def test_slot_omission_is_rejected(self, dropped: BundleSlot) -> None:
        slots = dict(_bundle_kwargs()["slots"])
        slots.pop(dropped)
        with pytest.raises(BundleIntegrityError, match=dropped.value):
            D.build_bundle_canonical_payload(**_bundle_kwargs(slots=slots))

    def test_sql_null_slot_is_rejected(self) -> None:
        slots = dict(_bundle_kwargs()["slots"])
        slots[BundleSlot.contract] = None
        with pytest.raises(BundleIntegrityError, match="NULL"):
            D.build_bundle_canonical_payload(**_bundle_kwargs(slots=slots))

    def test_json_null_field_is_rejected(self) -> None:
        slots = dict(_bundle_kwargs()["slots"])
        slots[BundleSlot.contract] = {"type": "definition", "ref": None, "digest": _d("c")}
        with pytest.raises(BundleIntegrityError, match="NULL"):
            D.build_bundle_canonical_payload(**_bundle_kwargs(slots=slots))

    def test_missing_dict_key_is_rejected(self) -> None:
        slots = dict(_bundle_kwargs()["slots"])
        slots[BundleSlot.contract] = {"type": "definition", "digest": _d("c")}
        with pytest.raises(BundleIntegrityError, match="omission"):
            D.build_bundle_canonical_payload(**_bundle_kwargs(slots=slots))

    def test_empty_string_field_is_rejected(self) -> None:
        slots = dict(_bundle_kwargs()["slots"])
        slots[BundleSlot.contract] = {"type": "  ", "ref": "definition:x", "digest": _d("c")}
        with pytest.raises(BundleIntegrityError):
            D.build_bundle_canonical_payload(**_bundle_kwargs(slots=slots))

    def test_all_zero_digest_is_rejected_as_pseudo_identity(self) -> None:
        slots = dict(_bundle_kwargs()["slots"])
        slots[BundleSlot.contract] = {
            "type": "definition",
            "ref": f"definition:{uuid.uuid4()}",
            "digest": "0" * 64,
        }
        with pytest.raises(BundleIntegrityError, match="伪身份"):
            D.build_bundle_canonical_payload(**_bundle_kwargs(slots=slots))

    def test_cross_slot_marker_is_rejected(self) -> None:
        marker = D.marker_for(BundleSlot.instrumentation)
        slots = dict(_bundle_kwargs()["slots"])
        slots[BundleSlot.contract] = BundleSlotSpec(
            BundleSlot.contract, marker.slot_type, marker.slot_ref, marker.slot_digest
        )
        with pytest.raises(BundleIntegrityError):
            D.build_bundle_canonical_payload(
                **_bundle_kwargs(
                    authority_model=AuthorityModel.custom_authoritative_ooxml, slots=slots
                )
            )

    def test_marker_cannot_impersonate_contract_in_projection_bundle(self) -> None:
        """`projection_contract` 的三个 child 必须均为 approved definition。"""
        slots = dict(_bundle_kwargs()["slots"])
        slots[BundleSlot.contract] = marker_slot(BundleSlot.contract)
        with pytest.raises(BundleIntegrityError, match="marker"):
            D.build_bundle_canonical_payload(**_bundle_kwargs(slots=slots))

    def test_custom_authority_model_may_use_typed_null_markers(self) -> None:
        """custom/opaque 的可选 child 必须是**显式版本化 marker**，不是省略。"""
        slots = {
            BundleSlot.template: def_slot(BundleSlot.template, TEMPLATE_DEF),
            BundleSlot.instrumentation: marker_slot(BundleSlot.instrumentation),
            BundleSlot.contract: marker_slot(BundleSlot.contract),
        }
        for model in (
            AuthorityModel.custom_authoritative_ooxml,
            AuthorityModel.opaque_single_onlyoffice,
        ):
            payload = D.build_bundle_canonical_payload(
                **_bundle_kwargs(authority_model=model, slots=slots)
            )
            assert payload["contract"]["type"] == "contract:none:v1"
            assert payload["contract"]["sha256"] == D.marker_digest(BundleSlot.contract)

    def test_authority_digest_null_and_malformed_rejected(self) -> None:
        with pytest.raises(BundleIntegrityError, match="NULL"):
            D.build_bundle_canonical_payload(
                **_bundle_kwargs(authority_model_definition_sha256=None)
            )
        for bad in ("", "0" * 64, "ABC", _d("x").upper()):
            with pytest.raises(BundleIntegrityError):
                D.build_bundle_canonical_payload(
                    **_bundle_kwargs(authority_model_definition_sha256=bad)
                )

    def test_unknown_authority_model_rejected(self) -> None:
        with pytest.raises(BundleIntegrityError, match="枚举"):
            D.build_bundle_canonical_payload(**_bundle_kwargs(authority_model="freeform"))

    def test_child_kind_state_digest_must_agree(self) -> None:
        slot_digest = _d("contract")
        validate_definition_child(
            slot=BundleSlot.contract,
            child_kind=DefinitionKind.contract,
            child_state=DefinitionState.approved,
            child_sha256=slot_digest,
            slot_digest=slot_digest,
        )
        with pytest.raises(BundleIntegrityError, match="kind"):
            validate_definition_child(
                slot=BundleSlot.contract,
                child_kind=DefinitionKind.template,
                child_state=DefinitionState.approved,
                child_sha256=slot_digest,
                slot_digest=slot_digest,
            )
        for state in (DefinitionState.candidate, DefinitionState.retired):
            with pytest.raises(BundleIntegrityError, match="approved"):
                validate_definition_child(
                    slot=BundleSlot.contract,
                    child_kind=DefinitionKind.contract,
                    child_state=state,
                    child_sha256=slot_digest,
                    slot_digest=slot_digest,
                )
        with pytest.raises(BundleIntegrityError, match="digest"):
            validate_definition_child(
                slot=BundleSlot.contract,
                child_kind=DefinitionKind.contract,
                child_state=DefinitionState.approved,
                child_sha256=_d("other"),
                slot_digest=slot_digest,
            )

    def test_bundle_digest_changes_when_any_child_changes(self) -> None:
        base = D.bundle_canonical_digest(**_bundle_kwargs())
        for slot in BundleSlot:
            slots = dict(_bundle_kwargs()["slots"])
            slots[slot] = def_slot(slot, _d(f"drifted-{slot.value}"))
            assert D.bundle_canonical_digest(**_bundle_kwargs(slots=slots)) != base
        assert (
            D.bundle_canonical_digest(
                **_bundle_kwargs(authority_model_definition_sha256=_d("other-authority"))
            )
            != base
        )

    def test_bundle_canonical_bytes_never_contain_forbidden_tokens(self) -> None:
        raw = D.bundle_canonical_bytes(**_bundle_kwargs())
        for token in (b"null", b'""', b"0" * 64):
            assert token not in raw, f"canonical bytes 出现禁用形态 {token!r}"


# ═══════════════════════════════════════════════════════════════════════════
# registry 测试脚手架
# ═══════════════════════════════════════════════════════════════════════════


class StubAdapter:
    """满足 protocol 形态的最小 adapter。

    刻意**不**继承任何基类：`WorkpaperSyncAdapter` 是 Protocol，registry 的形态判据
    必须靠「属性 + 可调用方法」而不是继承关系（否则一个把方法写成 None 的桩也能过）。
    """

    def __init__(self, adapter_id: str, document_type: str = "xlsx") -> None:
        self.adapter_id = adapter_id
        self.document_type = document_type
        self.contract_version = "1.0.0"

    async def read_current_projection(self, ctx: Any) -> Any:  # pragma: no cover - 形态桩
        raise NotImplementedError

    async def stage_projection_mutation(
        self, ctx: Any, merged: Any, *, expected_revision: int
    ) -> Any:  # pragma: no cover - 形态桩
        raise NotImplementedError

    def materialize(self, **kwargs: Any) -> Any:  # pragma: no cover - 形态桩
        raise NotImplementedError

    def extract(self, **kwargs: Any) -> Any:  # pragma: no cover - 形态桩
        raise NotImplementedError

    def verify_unmanaged_regions(self, **kwargs: Any) -> Any:  # pragma: no cover - 形态桩
        raise NotImplementedError


GOOD_DESCRIPTOR = EP.DescriptorFacts(
    mode=EP.DescriptorMode.bidirectional, exposes_mode_switch=True
)
GOOD_ROOM = EP.RoomFacts(
    shared_doc_key=True, doc_key_includes_mtime=False, participant_lease=True
)


def manifest_entry(
    entry_id: str = "g7.disclosure.listed@GtOnlyOfficeSheet",
    *,
    capability: str = "bidirectional",
    document_type: str = "xlsx",
    independent: bool = True,
    editability: str | None = "editable",
    room_model: str | None = "shared",
    scenario_profile: Any = "bidirectional_shared_room",
    parent_entry_id: str | None = None,
) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "entry_id": entry_id,
        "host_path": "audit-platform/frontend/src/components/workpaper/G/G7Tab.vue",
        "independent_entry": independent,
        "parent_entry_id": parent_entry_id,
        "document_type": document_type,
        "capability": capability,
        "html_store": "parsed_data",
        "canonical_resolver": "workpaper_sync",
        "adapter_id": None,
        "migration_state": "adapter_candidate",
        "evidence": {},
    }
    if editability is not None:
        entry["editability"] = editability
    if room_model is not None:
        entry["room_model"] = room_model
    if scenario_profile is not None:
        entry["scenario_profile"] = scenario_profile
    return entry


def manifest_of(*entries: Mapping[str, Any]) -> dict[str, Any]:
    return {"schema_version": 1, "manifest_digest": _d("manifest"), "entries": list(entries)}


def registration(
    *,
    contract: C.SyncContract | None,
    entry_id: str = "g7.disclosure.listed@GtOnlyOfficeSheet",
    adapter_id: str = "g7.disclosure.listed",
    document_type: str = "xlsx",
    wp_codes: frozenset[str] = frozenset({"G7-1"}),
    sheet_keys: frozenset[str] = frozenset(),
    bundle: DefinitionBundleSnapshot | None = None,
    descriptor: EP.DescriptorFacts = GOOD_DESCRIPTOR,
    room: EP.RoomFacts = GOOD_ROOM,
    declared: EP.Capability = EP.Capability.bidirectional,
) -> RG.AdapterRegistration:
    if bundle is None:
        bundle = make_bundle(
            contract_digest=contract.canonical_sha256 if contract is not None else None
        )
    return RG.AdapterRegistration(
        adapter=StubAdapter(adapter_id, document_type),
        entry_id=entry_id,
        matcher=RG.EntryMatcher(
            document_type=document_type, wp_codes=wp_codes, sheet_keys=sheet_keys
        ),
        bundle=bundle,
        descriptor=descriptor,
        room=room,
        declared_capability=declared,
        contract=contract,
    )


@pytest.fixture()
def reviewed_contract(contracts_dir: Path) -> C.SyncContract:
    return install_contract(contracts_dir, xlsx_payload())


# ═══════════════════════════════════════════════════════════════════════════
# Property 3：未注册 adapter 不得宣称双向
# ═══════════════════════════════════════════════════════════════════════════


class TestProperty3BidirectionalRequiresAdapter:
    """bidirectional entry 必须解析到唯一 adapter + approved authority model +
    非空 immutable bundle；`projection_contract` 还必须有 approved per-entry contract。
    删 adapter / bundle / contract 任一项都必须打红，且**三种不同**异常类型。"""

    def test_full_registration_resolves(self, reviewed_contract: C.SyncContract) -> None:
        registry = RG.WorkpaperSyncAdapterRegistry(manifest=manifest_of(manifest_entry()))
        registry.register(registration(contract=reviewed_contract))
        resolved = registry.resolve(wp_code="G7-1", document_type="xlsx")
        assert resolved.adapter_id == "g7.disclosure.listed"
        ready = registry.assert_bidirectional_ready(manifest_entry()["entry_id"])
        assert ready.authority_model is AuthorityModel.projection_contract
        assert ready.contract is not None
        assert ready.bundle.state is DefinitionState.approved
        assert ready.declares_bidirectional is True

    def test_missing_adapter_forbids_bidirectional_claim(self) -> None:
        """入口未注册 adapter ⇒ 前端不得显示「可双向回写」（AC 1.4）。"""
        registry = RG.WorkpaperSyncAdapterRegistry(manifest=manifest_of(manifest_entry()))
        with pytest.raises(RG.AdapterNotRegisteredError):
            registry.resolve(wp_code="G7-1", document_type="xlsx")
        with pytest.raises(RG.AdapterNotRegisteredError):
            registry.assert_bidirectional_ready(manifest_entry()["entry_id"])
        report = registry.build_report()
        assert manifest_entry()["entry_id"] in report.bidirectional_without_adapter
        assert report.closed is False

    def test_missing_bundle_approval_forbids_bidirectional_claim(
        self, reviewed_contract: C.SyncContract
    ) -> None:
        registry = RG.WorkpaperSyncAdapterRegistry(manifest=manifest_of(manifest_entry()))
        candidate_bundle = make_bundle(
            contract_digest=reviewed_contract.canonical_sha256,
            state=DefinitionState.candidate,
        )
        with pytest.raises(BundleIntegrityError, match="approved"):
            registry.register(registration(contract=reviewed_contract, bundle=candidate_bundle))

    def test_bundle_with_missing_slot_forbids_registration(
        self, reviewed_contract: C.SyncContract
    ) -> None:
        registry = RG.WorkpaperSyncAdapterRegistry(manifest=manifest_of(manifest_entry()))
        holed = make_bundle(
            contract_digest=reviewed_contract.canonical_sha256,
            drop_slots=(BundleSlot.instrumentation,),
        )
        with pytest.raises(BundleIntegrityError, match="instrumentation"):
            registry.register(registration(contract=reviewed_contract, bundle=holed))

    def test_missing_contract_forbids_projection_bundle(self) -> None:
        """`projection_contract` 缺 approved contract ⇒ 不得进入 bidirectional 验收。"""
        registry = RG.WorkpaperSyncAdapterRegistry(manifest=manifest_of(manifest_entry()))
        bundle = make_bundle(contract_digest=_d("contract"))
        with pytest.raises(RG.AuthorityModelMismatchError, match="contract"):
            registry.register(registration(contract=None, bundle=bundle))

    def test_marker_cannot_impersonate_contract_at_registration(self) -> None:
        registry = RG.WorkpaperSyncAdapterRegistry(manifest=manifest_of(manifest_entry()))
        bundle = make_bundle(contract_digest=None)  # contract slot = typed null marker
        with pytest.raises(BundleIntegrityError, match="marker"):
            registry.register(registration(contract=None, bundle=bundle))

    def test_three_failure_paths_have_pairwise_distinct_types(self) -> None:
        """🔴 三条缺失路径的异常类型不得互相继承，否则删一条会被另一条遮蔽。"""
        types = (
            RG.AdapterNotRegisteredError,
            BundleIntegrityError,
            RG.AuthorityModelMismatchError,
        )
        for left in types:
            for right in types:
                if left is right:
                    continue
                assert not issubclass(left, right), (
                    f"{left.__name__} 继承了 {right.__name__} —— 「缺 adapter」「缺 bundle」"
                    "「缺 contract」必须可分辨"
                )

    def test_error_codes_are_distinct(self) -> None:
        codes = {
            RG.AdapterNotRegisteredError.error_code,
            BundleIntegrityError.error_code,
            RG.AuthorityModelMismatchError.error_code,
            RG.StaleAdapterError.error_code,
            RG.FakeBidirectionalError.error_code,
            RG.MatcherOverlapError.error_code,
            EP.EntryProfileMissingError.error_code,
            EP.EntryProfileDriftError.error_code,
        }
        assert len(codes) == 8, f"error_code 重复，运维无法区分: {codes}"

    def test_non_bidirectional_entry_cannot_be_accepted_as_bidirectional(self) -> None:
        entry = manifest_entry(capability="single_onlyoffice", room_model="exclusive")
        registry = RG.WorkpaperSyncAdapterRegistry(manifest=manifest_of(entry))
        with pytest.raises(RG.FakeBidirectionalError):
            registry.assert_bidirectional_ready(entry["entry_id"])

    def test_real_manifest_has_no_bidirectional_entry_yet(self) -> None:
        """实况判据：186 条 entry 里**零** bidirectional、零 adapter_id。

        因此「未注册 adapter 不得宣称双向」现在覆盖全部入口 —— 任何 UI 上出现的
        双向宣称都是 legacy 假双向（`migration_state=legacy_fake_bidirectional`）。
        本条不锁数字基线，只锁不变式：capability=bidirectional 的 entry 必须有
        adapter_id，否则 registry 报告非空。
        """
        registry = RG.WorkpaperSyncAdapterRegistry(manifest=EP.load_entry_manifest())
        report = registry.build_report()
        entries = registry.manifest_entries
        expected = sorted(
            entry_id
            for entry_id, entry in entries.items()
            if entry.get("independent_entry")
            and entry.get("capability") == "bidirectional"
        )
        assert sorted(report.bidirectional_without_adapter) == expected
        assert report.registered_adapter_ids == ()
        assert all(entry.get("adapter_id") is None for entry in entries.values())


# ═══════════════════════════════════════════════════════════════════════════
# registry fail-closed 清册（RG-1 ~ RG-19）
# ═══════════════════════════════════════════════════════════════════════════


class TestRegistryFailClosedRules:
    def test_rg1_adapter_shape(self) -> None:
        class Hollow:
            adapter_id = "x.y"
            document_type = "xlsx"
            contract_version = "1.0.0"
            read_current_projection = None
            stage_projection_mutation = None
            materialize = None
            extract = None
            verify_unmanaged_regions = None

        with pytest.raises(RG.AdapterShapeError, match="不可调用"):
            RG.assert_adapter_shape(Hollow())

        class NoId(StubAdapter):
            def __init__(self) -> None:
                super().__init__("")

        with pytest.raises(RG.AdapterShapeError, match="非空字符串"):
            RG.assert_adapter_shape(NoId())

    def test_rg2_empty_matcher(self) -> None:
        with pytest.raises(RG.MatcherError, match="wp_codes"):
            RG.EntryMatcher(document_type="xlsx", wp_codes=frozenset())
        with pytest.raises(RG.MatcherError, match="document_type"):
            RG.EntryMatcher(document_type="pdf", wp_codes=frozenset({"G7-1"}))

    def test_rg3_matcher_overlap(self, contracts_dir: Path) -> None:
        first = install_contract(contracts_dir, xlsx_payload("a.one"))
        second = install_contract(contracts_dir, xlsx_payload("a.two"))
        manifest = manifest_of(
            manifest_entry("a.one@Host"), manifest_entry("a.two@Host")
        )
        registry = RG.WorkpaperSyncAdapterRegistry(manifest=manifest)
        registry.register(
            registration(
                contract=first, entry_id="a.one@Host", adapter_id="a.one",
                wp_codes=frozenset({"G7-1"}), sheet_keys=frozenset({"s1"}),
            )
        )
        with pytest.raises(RG.MatcherOverlapError, match="重叠"):
            registry.register(
                registration(
                    contract=second, entry_id="a.two@Host", adapter_id="a.two",
                    wp_codes=frozenset({"G7-1"}),  # 空 sheet_keys ⇒ 覆盖全部 sheet
                )
            )

    def test_matcher_overlap_is_symmetric_and_sheet_aware(self) -> None:
        broad = RG.EntryMatcher(document_type="xlsx", wp_codes=frozenset({"G7-1"}))
        narrow = RG.EntryMatcher(
            document_type="xlsx", wp_codes=frozenset({"G7-1"}), sheet_keys=frozenset({"s1"})
        )
        other_sheet = RG.EntryMatcher(
            document_type="xlsx", wp_codes=frozenset({"G7-1"}), sheet_keys=frozenset({"s2"})
        )
        other_type = RG.EntryMatcher(document_type="docx", wp_codes=frozenset({"G7-1"}))
        assert broad.overlaps(narrow) == ("G7-1",)
        assert narrow.overlaps(broad) == ("G7-1",)
        assert narrow.overlaps(other_sheet) == ()
        assert broad.overlaps(other_type) == ()

    def test_rg4_adapter_id_must_equal_contract_id(
        self, reviewed_contract: C.SyncContract
    ) -> None:
        registry = RG.WorkpaperSyncAdapterRegistry(manifest=manifest_of(manifest_entry()))
        with pytest.raises(RG.RegistrationError, match="contract_id"):
            registry.register(registration(contract=reviewed_contract, adapter_id="other.id"))

    def test_rg5_duplicate_adapter_and_entry(self, contracts_dir: Path) -> None:
        first = install_contract(contracts_dir, xlsx_payload("a.one"))
        manifest = manifest_of(
            manifest_entry("a.one@Host"), manifest_entry("a.dup@Host")
        )
        registry = RG.WorkpaperSyncAdapterRegistry(manifest=manifest)
        registry.register(
            registration(contract=first, entry_id="a.one@Host", adapter_id="a.one")
        )
        with pytest.raises(RG.RegistrationError, match="重复注册"):
            registry.register(
                registration(contract=first, entry_id="a.dup@Host", adapter_id="a.one")
            )
        second = install_contract(contracts_dir, xlsx_payload("a.two"))
        with pytest.raises(RG.RegistrationError, match="已由 adapter"):
            registry.register(
                registration(
                    contract=second, entry_id="a.one@Host", adapter_id="a.two",
                    wp_codes=frozenset({"G7-9"}),
                )
            )

    @pytest.mark.parametrize("source", ["adapter", "matcher", "manifest", "contract"])
    def test_rg6_document_type_must_agree_across_four_sources(
        self, contracts_dir: Path, source: str
    ) -> None:
        payload = docx_payload("a.doc") if source == "contract" else xlsx_payload("a.doc")
        contract = install_contract(contracts_dir, payload)
        entry = manifest_entry(
            "a.doc@Host", document_type="docx" if source == "manifest" else "xlsx"
        )
        registry = RG.WorkpaperSyncAdapterRegistry(manifest=manifest_of(entry))
        reg = registration(
            contract=contract,
            entry_id="a.doc@Host",
            adapter_id="a.doc",
            document_type="docx" if source in {"adapter", "matcher"} else "xlsx",
        )
        if source == "adapter":
            reg.matcher.__dict__  # noqa: B018 - matcher 保持 xlsx，仅 adapter 声明 docx
            object.__setattr__(
                reg,
                "matcher",
                RG.EntryMatcher(document_type="xlsx", wp_codes=frozenset({"G7-1"})),
            )
        if source == "matcher":
            reg.adapter.document_type = "xlsx"
        with pytest.raises(RG.DocumentTypeMismatchError, match="document_type"):
            registry.register(reg)

    def test_rg9_custom_authority_model_must_not_carry_contract(
        self, reviewed_contract: C.SyncContract
    ) -> None:
        registry = RG.WorkpaperSyncAdapterRegistry(manifest=manifest_of(manifest_entry()))
        bundle = make_bundle(
            authority_model=AuthorityModel.custom_authoritative_ooxml,
            instrumentation_digest=None,
            contract_digest=None,
        )
        with pytest.raises(RG.AuthorityModelMismatchError, match="custom/opaque"):
            registry.register(registration(contract=reviewed_contract, bundle=bundle))

    def test_rg10_contract_digest_must_equal_bundle_slot_digest(
        self, reviewed_contract: C.SyncContract
    ) -> None:
        registry = RG.WorkpaperSyncAdapterRegistry(manifest=manifest_of(manifest_entry()))
        drifted = make_bundle(contract_digest=_d("some-other-contract"))
        with pytest.raises(RG.StaleAdapterError, match="frozen bundle"):
            registry.register(registration(contract=reviewed_contract, bundle=drifted))

    def test_rg11_on_disk_contract_drift_is_a_separate_judgement(
        self, contracts_dir: Path
    ) -> None:
        """🔴 与 RG-10 是两条不同的漂移：这条比「注册 ↔ 磁盘真源」。"""
        contract = install_contract(contracts_dir, xlsx_payload())
        registry = RG.WorkpaperSyncAdapterRegistry(manifest=manifest_of(manifest_entry()))
        # 磁盘契约被改（新增一个字段），注册时仍挂旧对象 ⇒ stale adapter。
        drifted = xlsx_payload()
        drifted["semantic_version"] = "1.0.1"
        (contracts_dir / "g7.disclosure.listed.json").write_text(
            json.dumps(drifted, ensure_ascii=False), encoding="utf-8"
        )
        with pytest.raises(RG.StaleAdapterError, match="磁盘契约"):
            registry.register(registration(contract=contract))

    def test_rg11_missing_contract_file_is_stale(self, contracts_dir: Path) -> None:
        contract = install_contract(contracts_dir, xlsx_payload())
        (contracts_dir / "g7.disclosure.listed.json").unlink()
        registry = RG.WorkpaperSyncAdapterRegistry(manifest=manifest_of(manifest_entry()))
        with pytest.raises(RG.StaleAdapterError, match="契约文件不存在"):
            registry.register(registration(contract=contract))

    def test_rg12_entry_not_in_manifest_is_stale(
        self, reviewed_contract: C.SyncContract
    ) -> None:
        registry = RG.WorkpaperSyncAdapterRegistry(manifest=manifest_of(manifest_entry()))
        with pytest.raises(RG.StaleAdapterError, match="source-backed manifest"):
            registry.register(
                registration(contract=reviewed_contract, entry_id="ghost@Nowhere")
            )
        assert "g7.disclosure.listed" in registry.build_report().stale_adapters

    def test_rg13_parent_duplicate_and_unreachable_entries_rejected(
        self, contracts_dir: Path
    ) -> None:
        child = install_contract(contracts_dir, xlsx_payload("a.child"))
        dup_entry = manifest_entry(
            "a.child@Parent", independent=False, parent_entry_id="a.child@Host"
        )
        registry = RG.WorkpaperSyncAdapterRegistry(manifest=manifest_of(dup_entry))
        with pytest.raises(RG.RegistrationError, match="父组件重复入口"):
            registry.register(
                registration(contract=child, entry_id="a.child@Parent", adapter_id="a.child")
            )

        gone = manifest_entry(
            "a.child@Dead", capability="unreachable", editability="unreachable",
            room_model="none",
        )
        registry = RG.WorkpaperSyncAdapterRegistry(manifest=manifest_of(gone))
        with pytest.raises(RG.RegistrationError, match="unreachable"):
            registry.register(
                registration(contract=child, entry_id="a.child@Dead", adapter_id="a.child")
            )

    @pytest.mark.parametrize("missing", list(EP.PROFILE_KEYS))
    def test_rg14_profile_fields_are_mandatory(
        self, reviewed_contract: C.SyncContract, missing: str
    ) -> None:
        entry = manifest_entry()
        entry.pop(missing)
        registry = RG.WorkpaperSyncAdapterRegistry(manifest=manifest_of(entry))
        with pytest.raises(EP.EntryProfileMissingError, match=missing):
            registry.register(registration(contract=reviewed_contract))

    def test_rg15_profile_must_agree_with_capability(
        self, reviewed_contract: C.SyncContract
    ) -> None:
        entry = manifest_entry(editability="readonly")
        registry = RG.WorkpaperSyncAdapterRegistry(manifest=manifest_of(entry))
        with pytest.raises(EP.EntryProfileDriftError, match="editability"):
            registry.register(registration(contract=reviewed_contract))

        entry = manifest_entry(room_model="none")
        registry = RG.WorkpaperSyncAdapterRegistry(manifest=manifest_of(entry))
        with pytest.raises(EP.EntryProfileDriftError, match="room_model"):
            registry.register(registration(contract=reviewed_contract))

    def test_rg16_descriptor_mode_must_agree_with_capability(
        self, reviewed_contract: C.SyncContract
    ) -> None:
        entry = manifest_entry()
        registry = RG.WorkpaperSyncAdapterRegistry(manifest=manifest_of(entry))
        lying = EP.DescriptorFacts(
            mode=EP.DescriptorMode.single_onlyoffice, exposes_mode_switch=True
        )
        with pytest.raises(EP.EntryProfileDriftError, match="descriptor mode"):
            registry.register(registration(contract=reviewed_contract, descriptor=lying))

    def test_rg16_mode_switch_only_for_bidirectional(self, contracts_dir: Path) -> None:
        """不得显示不可兑现的切换按钮（AC 1.5）。"""
        contract = install_contract(contracts_dir, xlsx_payload("a.single"))
        entry = manifest_entry(
            "a.single@Host", capability="single_onlyoffice", room_model="exclusive"
        )
        registry = RG.WorkpaperSyncAdapterRegistry(manifest=manifest_of(entry))
        descriptor = EP.DescriptorFacts(
            mode=EP.DescriptorMode.single_onlyoffice, exposes_mode_switch=True
        )
        with pytest.raises(EP.EntryProfileDriftError, match="切换"):
            registry.register(
                registration(
                    contract=contract, entry_id="a.single@Host", adapter_id="a.single",
                    descriptor=descriptor,
                    room=EP.RoomFacts(
                        shared_doc_key=False, doc_key_includes_mtime=False,
                        participant_lease=True,
                    ),
                    declared=EP.Capability.single_onlyoffice,
                )
            )

    def test_rg17_room_facts_must_agree_and_dockey_must_drop_mtime(
        self, reviewed_contract: C.SyncContract
    ) -> None:
        registry = RG.WorkpaperSyncAdapterRegistry(manifest=manifest_of(manifest_entry()))
        mtime_room = EP.RoomFacts(
            shared_doc_key=True, doc_key_includes_mtime=True, participant_lease=True
        )
        with pytest.raises(EP.EntryProfileDriftError, match="mtime"):
            registry.register(registration(contract=reviewed_contract, room=mtime_room))

        registry = RG.WorkpaperSyncAdapterRegistry(manifest=manifest_of(manifest_entry()))
        per_client = EP.RoomFacts(
            shared_doc_key=False, doc_key_includes_mtime=False, participant_lease=True
        )
        with pytest.raises(EP.EntryProfileDriftError, match="shared"):
            registry.register(registration(contract=reviewed_contract, room=per_client))

        registry = RG.WorkpaperSyncAdapterRegistry(manifest=manifest_of(manifest_entry()))
        no_lease = EP.RoomFacts(
            shared_doc_key=True, doc_key_includes_mtime=False, participant_lease=False
        )
        with pytest.raises(EP.EntryProfileDriftError, match="participant lease"):
            registry.register(registration(contract=reviewed_contract, room=no_lease))

    def test_rg18_fake_bidirectional_both_directions(self, contracts_dir: Path) -> None:
        """single entry 伪 bidirectional，以及 bidirectional entry 只声明单向。"""
        contract = install_contract(contracts_dir, xlsx_payload("a.fake"))
        entry = manifest_entry(
            "a.fake@Host", capability="single_onlyoffice", room_model="exclusive"
        )
        registry = RG.WorkpaperSyncAdapterRegistry(manifest=manifest_of(entry))
        with pytest.raises(RG.FakeBidirectionalError, match="伪装"):
            registry.register(
                registration(
                    contract=contract, entry_id="a.fake@Host", adapter_id="a.fake",
                    descriptor=EP.DescriptorFacts(
                        mode=EP.DescriptorMode.single_onlyoffice, exposes_mode_switch=False
                    ),
                    room=EP.RoomFacts(
                        shared_doc_key=False, doc_key_includes_mtime=False,
                        participant_lease=True,
                    ),
                    declared=EP.Capability.bidirectional,
                )
            )

        registry = RG.WorkpaperSyncAdapterRegistry(manifest=manifest_of(manifest_entry()))
        reviewed = install_contract(contracts_dir, xlsx_payload())
        with pytest.raises(RG.RegistrationError, match="两侧必须一致"):
            registry.register(
                registration(contract=reviewed, declared=EP.Capability.single_onlyoffice)
            )

    def test_rg18_declared_capability_is_independent_of_descriptor_mode(self) -> None:
        """🔴 结构判据：`declares_bidirectional` 不得由 `descriptor.mode` 派生。

        早先把它定义成 `descriptor.mode is bidirectional`，而 RG-16 又要求
        `descriptor.mode == manifest capability` ⇒ RG-18「伪双向」永远不可能触发，
        成了结构性死代码（假绿第①源，已实测）。
        """
        impl = _func_body(_stripped(_REGISTRY_PY), "def declares_bidirectional")
        assert "descriptor" not in impl, (
            "declares_bidirectional 引用了 descriptor ⇒ RG-18 与 RG-16 互相遮蔽"
        )
        assert "declared_capability" in impl

    def test_rg19_ungated_carrier_blocks_registration(self, contracts_dir: Path) -> None:
        """未过 probe gate 的载体在契约加载期就被拒 ⇒ 根本到不了注册。"""
        payload = docx_payload("a.rowsdt")
        payload["identity_carriers"] = ["row_sdt"]
        path = contracts_dir / "a.rowsdt.json"
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        with pytest.raises(C.ContractCarrierGateError):
            C.load_contract("a.rowsdt")

    def test_resolution_is_matcher_scoped(self, reviewed_contract: C.SyncContract) -> None:
        registry = RG.WorkpaperSyncAdapterRegistry(manifest=manifest_of(manifest_entry()))
        registry.register(registration(contract=reviewed_contract))
        with pytest.raises(RG.AdapterNotRegisteredError):
            registry.resolve(wp_code="G7-9", document_type="xlsx")
        with pytest.raises(RG.AdapterNotRegisteredError):
            registry.resolve(wp_code="G7-1", document_type="docx")
        with pytest.raises(RG.AdapterNotRegisteredError):
            registry.resolve_for_entry("nobody@Nowhere")

    def test_sheet_scoped_matcher_requires_sheet_key(
        self, reviewed_contract: C.SyncContract
    ) -> None:
        registry = RG.WorkpaperSyncAdapterRegistry(manifest=manifest_of(manifest_entry()))
        registry.register(
            registration(contract=reviewed_contract, sheet_keys=frozenset({"g7-disclosure"}))
        )
        assert registry.resolve(
            wp_code="G7-1", document_type="xlsx", sheet_key="g7-disclosure"
        ).adapter_id == "g7.disclosure.listed"
        with pytest.raises(RG.AdapterNotRegisteredError):
            registry.resolve(wp_code="G7-1", document_type="xlsx", sheet_key="other")
        with pytest.raises(RG.AdapterNotRegisteredError):
            registry.resolve(wp_code="G7-1", document_type="xlsx")

    def test_production_registry_starts_empty(self) -> None:
        """当前刻意零 adapter：逐 entry 注册由 Tasks 40~57 / 62~64 承接。"""
        registry = RG.build_production_registry()
        assert registry.registrations() == ()
        assert registry.build_report().registered_adapter_ids == ()


# ═══════════════════════════════════════════════════════════════════════════
# Property 28：immutable definition 漂移 fail closed
# ═══════════════════════════════════════════════════════════════════════════


class TestProperty28DefinitionDriftFailsClosed:
    """三条互不遮蔽的漂移路径 + 结构漂移必须指出首个位置。"""

    def test_contract_bundle_slot_digests_are_locked_both_ways(
        self, reviewed_contract: C.SyncContract
    ) -> None:
        good = make_bundle(contract_digest=reviewed_contract.canonical_sha256)
        reviewed_contract.assert_matches_bundle_slots(good.slots)
        RG.assert_contract_identity_frozen(
            contract=reviewed_contract, bundle=good, entry_id="e"
        )

        for slot in (BundleSlot.template, BundleSlot.instrumentation):
            drifted = make_bundle(
                contract_digest=reviewed_contract.canonical_sha256,
                **{
                    "template_digest" if slot is BundleSlot.template
                    else "instrumentation_digest": _d("drifted")
                },
            )
            with pytest.raises(C.ContractDriftError, match=slot.value):
                reviewed_contract.assert_matches_bundle_slots(drifted.slots)

    def test_marker_in_template_slot_is_drift_for_projection_contract(
        self, reviewed_contract: C.SyncContract
    ) -> None:
        markered = make_bundle(
            template_digest=None, contract_digest=reviewed_contract.canonical_sha256
        )
        with pytest.raises(C.ContractDriftError, match="template"):
            reviewed_contract.assert_matches_bundle_slots(markered.slots)

    def test_missing_slot_prevents_comparison(
        self, reviewed_contract: C.SyncContract
    ) -> None:
        holed = make_bundle(
            contract_digest=reviewed_contract.canonical_sha256,
            drop_slots=(BundleSlot.template,),
        )
        with pytest.raises(C.ContractDriftError, match="typed slot"):
            reviewed_contract.assert_matches_bundle_slots(holed.slots)

    def test_structure_drift_reports_first_position(self) -> None:
        contract = C.parse_contract(xlsx_payload())
        declared = C.declared_structure_inventory(contract)
        assert declared, "受管结构清册不得为空"
        assert C.first_structure_drift(contract, declared) is None
        C.assert_no_structure_drift(contract, declared)

        # 把首项的 locator 改掉（模拟模板列位移）
        observed = list(declared)
        sheet_key, table_key, stable_key, locator = observed[0]
        observed[0] = (sheet_key, table_key, stable_key, "ZZ:row_identity")
        with pytest.raises(C.ContractDriftError) as ei:
            C.assert_no_structure_drift(contract, observed)
        message = str(ei.value)
        assert stable_key in message and locator in message, (
            f"漂移诊断必须指出首个 sheet/field/cell，实得: {message}"
        )

    def test_structure_drift_detects_missing_and_extra_fields(self) -> None:
        contract = C.parse_contract(xlsx_payload())
        declared = list(C.declared_structure_inventory(contract))
        with pytest.raises(C.ContractDriftError):
            C.assert_no_structure_drift(contract, declared[:-1])
        with pytest.raises(C.ContractDriftError):
            C.assert_no_structure_drift(contract, [*declared, ("s", "t", "extra", "A:static")])

    def test_structure_inventory_is_order_independent(self) -> None:
        """判据按稳定序比对 —— 实测清册的枚举顺序不同不得被误判成漂移。"""
        contract = C.parse_contract(xlsx_payload())
        declared = list(C.declared_structure_inventory(contract))
        C.assert_no_structure_drift(contract, list(reversed(declared)))

    def test_structure_inventory_carries_no_display_names(self) -> None:
        """清册只含稳定 identity，不含 sheet 展示名/中文 label（否则改名即假漂移）。"""
        contract = C.parse_contract(xlsx_payload())
        for row in C.declared_structure_inventory(contract):
            joined = "".join(row)
            assert joined.isascii(), f"结构清册含非 ASCII（展示名/中文 label）: {row}"
            assert "G7 披露表" not in joined

    def test_alias_can_never_be_used_for_history(self) -> None:
        """只改 registry alias 不得改变历史 retry（单一真源在 definitions）。"""
        aliases = D.DefinitionAliasRegistry()
        target = D.DefinitionAliasTarget(
            alias="g7.current",
            definition_id=uuid.uuid4(),
            definition_sha256=_d("bundle"),
            kind=DefinitionKind.contract,
        )
        aliases.register(target)
        assert aliases.resolve_for_publish("g7.current") == target
        with pytest.raises(D.AliasResolutionForbiddenError):
            aliases.resolve_for_history("g7.current")

    def test_registry_exposes_no_alias_based_history_lookup(self) -> None:
        """🔴 否定式承诺：registry 不提供任何按 alias 反查历史 bundle 的入口。

        历史 operation/retry 只读自己 frozen 的 `definition_bundle_id + sha256`。
        判据落在**结构**上（registry 源码零 alias 符号 + 无 history 入口），因为
        「不做某件事」无法用短路变异证明 —— 变异脚本用**注入**一个 alias 历史解析
        方法来证明本条可 falsify（M22）。
        """
        body = _stripped(_REGISTRY_PY)
        for forbidden in (
            "DefinitionAliasRegistry", "resolve_for_publish", "set_alias", "aliases",
        ):
            assert forbidden not in body, (
                f"registry.py 出现 alias 符号 {forbidden!r} —— 历史读取一律读 frozen "
                "bundle FK+digest，registry 只服务「当前该用哪个 adapter」"
            )
        public = [
            name
            for name in dir(RG.WorkpaperSyncAdapterRegistry)
            if not name.startswith("_")
        ]
        assert not [name for name in public if "history" in name or "alias" in name], (
            f"registry 暴露了历史/alias 入口: {public}"
        )

    def test_registration_freezes_bundle_object_not_a_lookup(
        self, reviewed_contract: C.SyncContract
    ) -> None:
        """注册记录持有的是**快照对象**，不是「按 id 现查」的回调。"""
        registry = RG.WorkpaperSyncAdapterRegistry(manifest=manifest_of(manifest_entry()))
        reg = registration(contract=reviewed_contract)
        registry.register(reg)
        resolved = registry.resolve_for_entry(manifest_entry()["entry_id"])
        assert resolved.bundle is reg.bundle
        assert isinstance(resolved.bundle, DefinitionBundleSnapshot)
        assert resolved.bundle.typed_slot_inventory == reg.bundle.typed_slot_inventory


# ═══════════════════════════════════════════════════════════════════════════
# adapter protocol 面（Requirement 3.1 的 adapter 侧 / 6.11 / 6.18）
# ═══════════════════════════════════════════════════════════════════════════


class _FakeSession:
    """伪 AsyncSession —— 只要暴露 commit/execute 就该被副作用面守卫拦住。"""

    async def commit(self) -> None:  # pragma: no cover - 仅需存在且可调用
        raise AssertionError("adapter 不得 commit")

    async def execute(self, *args: Any) -> None:  # pragma: no cover
        raise AssertionError("adapter 不得写库")


def make_context(
    *,
    contract: C.SyncContract | None,
    bundle: DefinitionBundleSnapshot | None = None,
    document_type: str = "xlsx",
    substrate_role: AB.SubstrateRole = AB.SubstrateRole.incoming,
) -> AB.SyncContext:
    if bundle is None:
        bundle = make_bundle(
            contract_digest=contract.canonical_sha256 if contract is not None else None,
            authority_model=(
                AuthorityModel.projection_contract
                if contract is not None
                else AuthorityModel.custom_authoritative_ooxml
            ),
            instrumentation_digest=INSTR_DEF if contract is not None else None,
        )
    return AB.SyncContext(
        project_id=uuid.uuid4(),
        wp_id=uuid.uuid4(),
        entry_id="g7.disclosure.listed@GtOnlyOfficeSheet",
        adapter_id="g7.disclosure.listed",
        adapter_build_digest=_d("adapter-build"),
        content_version_id=uuid.uuid4(),
        content_revision=7,
        representation_id=uuid.uuid4(),
        representation_generation=1,
        document_type=document_type,
        bundle=bundle,
        substrate_path=Path("/tmp/incoming.xlsx"),
        substrate_role=substrate_role,
        contract=contract,
    )


class TestAdapterProtocolSurface:
    def test_protocol_required_members_match_the_protocol(self) -> None:
        """清册与 Protocol 定义必须同源，否则改 Protocol 后 registry 判据失真。"""
        annotated = set(getattr(AB.WorkpaperSyncAdapter, "__annotations__", {}))
        assert AB.ADAPTER_REQUIRED_ATTRS <= annotated, (
            f"protocol 属性清册与 Protocol 注解不符: {AB.ADAPTER_REQUIRED_ATTRS} vs {annotated}"
        )
        methods = {
            name
            for name in dir(AB.WorkpaperSyncAdapter)
            if not name.startswith("_") and callable(getattr(AB.WorkpaperSyncAdapter, name))
        }
        assert AB.ADAPTER_REQUIRED_METHODS <= methods, (
            f"protocol 方法清册与 Protocol 不符: {AB.ADAPTER_REQUIRED_METHODS} vs {methods}"
        )
        assert len(AB.ADAPTER_REQUIRED_METHODS) == 5

    def test_stub_adapter_satisfies_protocol(self) -> None:
        RG.assert_adapter_shape(StubAdapter("x.y"))

    def test_context_rejects_any_mutation_surface(
        self, reviewed_contract: C.SyncContract
    ) -> None:
        """adapter 上下文不得握着 commit/写库/发事件的能力面（构造上不可能）。"""
        ctx = make_context(contract=reviewed_contract)
        AB.assert_no_mutation_surface(ctx, label="SyncContext")
        with pytest.raises(AB.AdapterSideEffectError, match="commit"):
            AB.assert_no_mutation_surface(_Carrier(_FakeSession()), label="probe")

    def test_context_field_names_have_no_session_or_outbox(self) -> None:
        names = {spec for spec in AB.SyncContext.__dataclass_fields__}
        assert not (names & {"session", "db", "repository", "outbox", "publisher"}), (
            f"SyncContext 出现写库/发事件字段: {sorted(names)}"
        )

    def test_forbidden_attr_list_covers_the_three_real_entry_points(self) -> None:
        for name in ("commit", "execute", "publish", "set_entry_pointer", "finalize_candidate"):
            assert name in AB.FORBIDDEN_SIDE_EFFECT_ATTRS

    def test_frozen_identity_consistency(self, reviewed_contract: C.SyncContract) -> None:
        make_context(contract=reviewed_contract).assert_frozen_identity_consistent()

        drifted = make_context(
            contract=reviewed_contract,
            bundle=make_bundle(contract_digest=_d("other")),
        )
        with pytest.raises(AB.AdapterProtocolError, match="不一致"):
            drifted.assert_frozen_identity_consistent()

        markered = make_context(
            contract=reviewed_contract,
            bundle=make_bundle(
                contract_digest=None,
                instrumentation_digest=None,
                authority_model=AuthorityModel.custom_authoritative_ooxml,
            ),
        )
        with pytest.raises(AB.AdapterProtocolError, match="marker"):
            markered.assert_frozen_identity_consistent()

        contractless = make_context(
            contract=None, bundle=make_bundle(contract_digest=_d("approved-contract"))
        )
        with pytest.raises(AB.AdapterProtocolError, match="没有解析出"):
            contractless.assert_frozen_identity_consistent()

        holed = make_context(
            contract=reviewed_contract,
            bundle=make_bundle(
                contract_digest=reviewed_contract.canonical_sha256,
                drop_slots=(BundleSlot.contract,),
            ),
        )
        with pytest.raises(AB.AdapterProtocolError, match="slot omission"):
            holed.assert_frozen_identity_consistent()

    def test_marker_bundle_without_contract_is_valid(self) -> None:
        """custom/opaque：contract slot 是显式 typed null marker ⇒ 合法。"""
        ctx = make_context(contract=None)
        ctx.assert_frozen_identity_consistent()

    def test_document_type_must_agree_with_contract(
        self, reviewed_contract: C.SyncContract
    ) -> None:
        ctx = make_context(contract=reviewed_contract, document_type="docx")
        with pytest.raises(AB.AdapterProtocolError, match="document_type"):
            ctx.assert_frozen_identity_consistent()

    def test_context_identity_forms_are_validated(
        self, reviewed_contract: C.SyncContract
    ) -> None:
        with pytest.raises(AB.AdapterProtocolError, match="adapter_build_digest"):
            AB.SyncContext(
                project_id=uuid.uuid4(), wp_id=uuid.uuid4(), entry_id="e",
                adapter_id="a", adapter_build_digest="0" * 64,
                content_version_id=uuid.uuid4(), content_revision=1,
                representation_id=uuid.uuid4(), representation_generation=1,
                document_type="xlsx",
                bundle=make_bundle(contract_digest=reviewed_contract.canonical_sha256),
                substrate_path=Path("/tmp/x.xlsx"),
                substrate_role=AB.SubstrateRole.incoming,
            )

    # ── substrate 准入 ──────────────────────────────────────────────────
    def test_incoming_substrate_must_be_durable(self) -> None:
        AB.assert_substrate_usable(
            role=AB.SubstrateRole.incoming,
            artifact_kind=ArtifactKind.incoming,
            artifact_state=ArtifactState.durable,
        )
        with pytest.raises(IncomingNotDurableError):
            AB.assert_substrate_usable(
                role=AB.SubstrateRole.incoming,
                artifact_kind=ArtifactKind.incoming,
                artifact_state=ArtifactState.staged,
            )

    def test_quarantined_substrate_is_rejected(self) -> None:
        with pytest.raises(QuarantinedIncomingError):
            AB.assert_substrate_usable(
                role=AB.SubstrateRole.incoming,
                artifact_kind=ArtifactKind.incoming,
                artifact_state=ArtifactState.quarantined,
            )

    def test_upgrade_candidate_substrate_is_rejected(self) -> None:
        """Requirement 6.18：candidate 永不可被 adapter/resolver/room 消费。"""
        with pytest.raises(AB.AdapterCandidateSubstrateError):
            AB.assert_substrate_usable(
                role=AB.SubstrateRole.published_representation,
                artifact_kind=ArtifactKind.upgrade_candidate,
                artifact_state=ArtifactState.candidate,
            )
        with pytest.raises(AB.AdapterCandidateSubstrateError):
            AB.assert_substrate_usable(
                role=AB.SubstrateRole.published_representation,
                artifact_kind=ArtifactKind.canonical,
                artifact_state=ArtifactState.candidate,
            )

    def test_three_substrate_rejection_reasons_are_distinguishable(self) -> None:
        assert not issubclass(QuarantinedIncomingError, AB.AdapterSubstrateError)
        assert issubclass(AB.AdapterCandidateSubstrateError, AB.AdapterSubstrateError)
        assert not issubclass(AB.AdapterSubstrateError, AB.AdapterCandidateSubstrateError)
        assert not issubclass(IncomingNotDurableError, AB.AdapterCandidateSubstrateError)

    def test_published_substrate_must_be_canonical_and_published(self) -> None:
        AB.assert_substrate_usable(
            role=AB.SubstrateRole.published_representation,
            artifact_kind=ArtifactKind.canonical,
            artifact_state=ArtifactState.published,
        )
        with pytest.raises(AB.AdapterSubstrateError, match="incoming"):
            AB.assert_substrate_usable(
                role=AB.SubstrateRole.published_representation,
                artifact_kind=ArtifactKind.incoming,
                artifact_state=ArtifactState.durable,
            )
        with pytest.raises(AB.AdapterSubstrateError, match="published"):
            AB.assert_substrate_usable(
                role=AB.SubstrateRole.published_representation,
                artifact_kind=ArtifactKind.canonical,
                artifact_state=ArtifactState.staged,
            )
        with pytest.raises(AB.AdapterSubstrateError, match="kind=incoming"):
            AB.assert_substrate_usable(
                role=AB.SubstrateRole.incoming,
                artifact_kind=ArtifactKind.canonical,
                artifact_state=ArtifactState.published,
            )

    # ── projection ─────────────────────────────────────────────────────
    def test_projection_is_keyed_by_stable_key_not_position(
        self, reviewed_contract: C.SyncContract
    ) -> None:
        row = "3f1a5c7e"
        projection = AB.Projection(
            contract_id=reviewed_contract.contract_id,
            semantic_version=reviewed_contract.semantic_version,
            document_type="xlsx",
            values={
                f"equity_changes/{row}/closing_amount": AB.FieldValue(
                    stable_key=f"equity_changes/{row}/closing_amount",
                    value="1234567.50",
                    value_type=C.ValueType.amount,
                    mode=C.FieldMode.editable,
                    row_key=row,
                ),
                "header_block/period_label": AB.FieldValue(
                    stable_key="header_block/period_label",
                    value="2025年度",
                    value_type=C.ValueType.text,
                    mode=C.FieldMode.editable,
                ),
            },
            row_keys={"equity_changes": (row,)},
        )
        projection.assert_matches_contract(reviewed_contract)
        assert projection.stable_keys() == (
            f"equity_changes/{row}/closing_amount", "header_block/period_label",
        )
        assert "header_block/period_label" in projection
        assert projection.get("nope") is None

    def test_projection_rejects_unregistered_key(
        self, reviewed_contract: C.SyncContract
    ) -> None:
        projection = AB.Projection(
            contract_id=reviewed_contract.contract_id,
            semantic_version="1.0.0",
            document_type="xlsx",
            values={
                "equity_changes/ghost": AB.FieldValue(
                    stable_key="equity_changes/ghost",
                    value=1,
                    value_type=C.ValueType.integer,
                    mode=C.FieldMode.editable,
                )
            },
        )
        with pytest.raises(AB.ProjectionShapeError, match="未登记"):
            projection.assert_matches_contract(reviewed_contract)

    def test_projection_key_matching_is_not_prefix_only(
        self, reviewed_contract: C.SyncContract
    ) -> None:
        """同前缀但段数不同的键不得被放行（否则 D2 那类大表会串数据）。"""
        row = "abc"
        projection = AB.Projection(
            contract_id=reviewed_contract.contract_id,
            semantic_version="1.0.0",
            document_type="xlsx",
            values={
                f"equity_changes/{row}/closing_amount/extra": AB.FieldValue(
                    stable_key=f"equity_changes/{row}/closing_amount/extra",
                    value=1,
                    value_type=C.ValueType.integer,
                    mode=C.FieldMode.editable,
                    row_key=row,
                )
            },
        )
        with pytest.raises(AB.ProjectionShapeError):
            projection.assert_matches_contract(reviewed_contract)

    def test_projection_contract_identity_is_checked(
        self, reviewed_contract: C.SyncContract
    ) -> None:
        projection = AB.Projection(
            contract_id="other.contract",
            semantic_version="1.0.0",
            document_type="xlsx",
            values={},
        )
        with pytest.raises(AB.ProjectionShapeError, match="contract_id"):
            projection.assert_matches_contract(reviewed_contract)
        projection = AB.Projection(
            contract_id=reviewed_contract.contract_id,
            semantic_version="1.0.0",
            document_type="docx",
            values={},
        )
        with pytest.raises(AB.ProjectionShapeError, match="document_type"):
            projection.assert_matches_contract(reviewed_contract)

    def test_field_value_protection_follows_mode(self) -> None:
        for mode, protected in (
            (C.FieldMode.editable, False),
            (C.FieldMode.formula, True),
            (C.FieldMode.auto_source, True),
            (C.FieldMode.word_only, False),
        ):
            value = AB.FieldValue(
                stable_key="k", value=None, value_type=C.ValueType.text, mode=mode
            )
            assert value.is_protected is protected

    def test_projection_mutation_has_no_write_capability(
        self, reviewed_contract: C.SyncContract
    ) -> None:
        projection = AB.Projection(
            contract_id=reviewed_contract.contract_id,
            semantic_version="1.0.0",
            document_type="xlsx",
            values={
                "header_block/period_label": AB.FieldValue(
                    stable_key="header_block/period_label",
                    value="x",
                    value_type=C.ValueType.text,
                    mode=C.FieldMode.editable,
                )
            },
        )
        mutation = AB.ProjectionMutation(
            entry_id="e",
            contract_id=reviewed_contract.contract_id,
            expected_revision=7,
            projection=projection,
            staged_payload={"header": {"periodLabel": "x"}},
            changed_stable_keys=("header_block/period_label",),
        )
        assert mutation.pending_mutation_id is None
        with pytest.raises(AB.ProjectionShapeError, match="expected_revision"):
            AB.ProjectionMutation(
                entry_id="e", contract_id="c", expected_revision=-1,
                projection=projection, staged_payload={}, changed_stable_keys=(),
            )
        with pytest.raises(AB.ProjectionShapeError, match="changed_stable_keys"):
            AB.ProjectionMutation(
                entry_id="e", contract_id="c", expected_revision=1,
                projection=projection, staged_payload={}, changed_stable_keys=("ghost",),
            )

    def test_materialize_result_requires_real_digests(self) -> None:
        good = AB.MaterializeResult(
            output_path=Path("/tmp/out.xlsx"),
            document_type="xlsx",
            artifact_sha256=_d("artifact"),
            structure_hash=_d("structure"),
            identity_inventory_sha256=_d("identity"),
            managed_field_count=3,
        )
        assert good.managed_field_count == 3
        for name in ("artifact_sha256", "structure_hash", "identity_inventory_sha256"):
            kwargs: dict[str, Any] = {
                "output_path": Path("/tmp/out.xlsx"),
                "document_type": "xlsx",
                "artifact_sha256": _d("artifact"),
                "structure_hash": _d("structure"),
                "identity_inventory_sha256": _d("identity"),
                "managed_field_count": 1,
            }
            kwargs[name] = "0" * 64
            with pytest.raises(AB.AdapterProtocolError, match=name):
                AB.MaterializeResult(**kwargs)

    def test_unmanaged_region_report_requires_first_difference(self) -> None:
        ok = AB.UnmanagedRegionReport(equivalent=True, inspected_aspects=("formula", "merge"))
        ok.assert_equivalent()
        with pytest.raises(AB.AdapterProtocolError, match="aspect"):
            AB.UnmanagedRegionReport(equivalent=True, inspected_aspects=())
        with pytest.raises(AB.AdapterProtocolError, match="first_difference"):
            AB.UnmanagedRegionReport(equivalent=False, inspected_aspects=("formula",))
        with pytest.raises(AB.AdapterProtocolError):
            AB.UnmanagedRegionReport(
                equivalent=True, inspected_aspects=("formula",), first_difference="Sheet1!A1"
            )
        bad = AB.UnmanagedRegionReport(
            equivalent=False, inspected_aspects=("formula",), first_difference="Sheet1!I8"
        )
        with pytest.raises(AB.UnmanagedRegionDriftError, match="Sheet1!I8"):
            bad.assert_equivalent()


@dataclasses.dataclass(frozen=True)
class _Carrier:
    """真 dataclass 载体：把任意对象塞进字段位置，用来测副作用面守卫本身。

    刻意用真 dataclass 而不是伪造 `__dataclass_fields__` —— `dataclasses.fields()`
    会读 `_field_type`，伪造品只会抛 AttributeError，那测到的是「守卫崩了」而不是
    「守卫拦住了」（WRONG-TEST 形态）。
    """

    payload: Any


# ═══════════════════════════════════════════════════════════════════════════
# registry 报告与它的**生产消费方**（防假绿第①源：additive 死代码）
# ═══════════════════════════════════════════════════════════════════════════


def _load_closure_gate() -> Any:
    import importlib.util

    spec = importlib.util.spec_from_file_location("wp_sync_closure_gate", _CLOSURE_PY)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestRegistryReportHasAProductionConsumer:
    """registry 现在零 adapter，因此它唯一的「真消费方」是闭合门。

    Requirement 1.4/1.8 正是这条：未裁决/未注册/伪双向的条目数必须**可见且阻断**。
    没有这层接线，整个 registry 就是 additive 死代码（假绿第①源）。
    """

    def test_closure_gate_consumes_the_registry_report(self) -> None:
        gate = _load_closure_gate()
        manifest = json.loads(
            (_BACKEND / "data" / "workpaper_sync_entry_manifest.json").read_text(
                encoding="utf-8"
            )
        )
        facts = gate.build_registry_facts(manifest)
        assert set(facts) == set(gate.REGISTRY_ISSUE_KEYS), (
            "registry facts 与登记键不符 ⇒ 新增事实不会进阻断总数"
        )
        # 与直接问 registry 得到的答案必须一致（不是另算一份）。
        registry = RG.WorkpaperSyncAdapterRegistry(manifest=manifest)
        report = registry.build_report(contract_ids=C.available_contract_ids())
        assert facts["registry_missing_entry_profile"] == list(report.missing_profile)
        assert facts["registry_bidirectional_without_registered_adapter"] == list(
            report.bidirectional_without_adapter
        )
        # 🔴 接线判据：门的 `main()` 必须真的把 facts 传进去。只测 `build_registry_facts`
        # 可被调用不够 —— 那样它仍可能是没人调的死代码（假绿第①源）。
        main_body = _func_body(_stripped(_CLOSURE_PY), "def main(")
        assert "build_registry_facts(manifest)" in main_body, (
            "closure gate 的 main() 没有把 registry facts 传给 evaluate_closure ⇒ "
            "registry 报告是死代码"
        )

    def test_registry_facts_participate_in_the_blocking_total(self) -> None:
        gate = _load_closure_gate()
        manifest = json.loads(
            (_BACKEND / "data" / "workpaper_sync_entry_manifest.json").read_text(
                encoding="utf-8"
            )
        )
        baseline = json.loads(
            (_BACKEND / "data" / "workpaper_sync_legacy_baseline.json").read_text(
                encoding="utf-8"
            )
        )
        without = gate.evaluate_closure(manifest, baseline)
        with_facts = gate.evaluate_closure(
            manifest, baseline, {"registry_missing_entry_profile": ["x/y"]}
        )
        assert without["registry_missing_entry_profile"] == []
        assert with_facts["registry_missing_entry_profile"] == ["x/y"]
        assert sum(len(v) for v in with_facts.values()) == (
            sum(len(v) for v in without.values()) + 1
        )

    def test_unregistered_registry_fact_is_rejected(self) -> None:
        """新增事实必须登记 —— 否则会静默不计入阻断总数。"""
        gate = _load_closure_gate()
        manifest = json.loads(
            (_BACKEND / "data" / "workpaper_sync_entry_manifest.json").read_text(
                encoding="utf-8"
            )
        )
        baseline = json.loads(
            (_BACKEND / "data" / "workpaper_sync_legacy_baseline.json").read_text(
                encoding="utf-8"
            )
        )
        with pytest.raises(gate.ClosureGuardError, match="unregistered"):
            gate.evaluate_closure(manifest, baseline, {"registry_brand_new_fact": ["x"]})

    def test_gate_import_failure_is_fail_closed_not_fail_open(self) -> None:
        """结构判据：registry 导入失败必须抛，不得被吞成「无事实」。"""
        impl = _func_body(_stripped(_CLOSURE_PY), "def build_registry_facts")
        assert "raise ClosureGuardError" in impl, (
            "registry 导入失败必须 fail closed —— 吞掉异常会让全部 registry 事实静默消失"
        )
        assert "return {}" not in impl

    def test_report_invariant_holds_on_the_real_manifest(self) -> None:
        """不变式（Task 1 补齐 profile 前后都成立）：

            每条独立、可达 entry 要么有完整合法 profile，要么**不可能**注册 adapter。

        判据不锁「当前 142 条缺 profile」这个数字（那是把错值当基线，假绿第③源），
        而是把两侧都从 manifest 现算：缺任一 profile 键的 entry 必须恰好等于报告里
        的 `missing_profile`，且逐条 register 必抛。
        """
        manifest = EP.load_entry_manifest()
        registry = RG.WorkpaperSyncAdapterRegistry(manifest=manifest)
        report = registry.build_report()
        expected_missing = sorted(
            entry_id
            for entry_id, entry in registry.manifest_entries.items()
            if entry.get("independent_entry")
            and entry.get("capability") != "unreachable"
            and any(entry.get(key) is None for key in EP.PROFILE_KEYS)
        )
        assert sorted(report.missing_profile) == expected_missing
        assert report.independent_entry_count == sum(
            1 for entry in registry.manifest_entries.values() if entry.get("independent_entry")
        )
        assert report.entry_count == len(registry.manifest_entries)

    def test_entries_missing_profile_cannot_register(
        self, reviewed_contract: C.SyncContract
    ) -> None:
        """不变式的另一半，按 Task 73 补齐 profile 后的形态。

        原判据是「缺 profile 的 entry 逐条注册必抛」，并在 docstring 里写明：
        *若已无缺 profile 的 entry，本条判据应改为断言全部可注册*。Task 73 已让 186 条
        entry 全部带上 source-backed profile，于是这里换成两条更强的判据：

        1. 每条独立可达 entry 的 profile 都能**合法解析**（不再有 `missing_profile`）；
        2. 注册仍然 fail closed —— 但理由从「缺字段」变成 RG-15/16/17 的**真实漂移**
           （今天全部 entry 的 doc_key 仍来自 legacy provider）。

        判据不锁「142 条」这个数字：两侧都从 manifest 与实测事实现算。
        """
        manifest = EP.load_entry_manifest()
        registry = RG.WorkpaperSyncAdapterRegistry(manifest=manifest)
        report = registry.build_report()
        assert report.missing_profile == (), (
            "Task 73 之后不应再有缺 source-backed profile 的 entry；若这里又非空，"
            f"说明生成器又漏了字段: {report.missing_profile[:5]}"
        )
        independent = sorted(
            entry_id
            for entry_id, entry in registry.manifest_entries.items()
            if entry.get("independent_entry") and entry.get("capability") != "unreachable"
        )
        assert independent, "manifest 必须有独立可达 entry，否则本判据被 vacuous truth 掏空"
        for entry_id in independent:
            EP.extract_entry_profile(registry.manifest_entries[entry_id])
        for entry_id in independent[:5]:
            entry = registry.manifest_entries[entry_id]
            with pytest.raises(
                (EP.EntryProfileError, RG.RegistryError, RG.FakeBidirectionalError)
            ):
                registry.register(
                    registration(
                        contract=reviewed_contract,
                        entry_id=entry_id,
                        document_type=str(entry.get("document_type") or "xlsx"),
                        room=EP.RoomFacts(
                            shared_doc_key=True,
                            doc_key_includes_mtime=True,  # 实测：legacy provider 仍含 mtime
                            participant_lease=False,
                        ),
                    )
                )

    def test_contract_file_without_adapter_is_surfaced(
        self, contracts_dir: Path
    ) -> None:
        install_contract(contracts_dir, xlsx_payload("orphan.contract"))
        registry = RG.WorkpaperSyncAdapterRegistry(manifest=manifest_of(manifest_entry()))
        report = registry.build_report(contract_ids=C.available_contract_ids())
        assert report.contract_files_without_adapter == ("orphan.contract",)
        assert report.blocking_counts["contract_files_without_adapter"] == 1
        assert report.blocking_total >= 1
        assert report.closed is False

    def test_closed_report_is_reachable(self, reviewed_contract: C.SyncContract) -> None:
        """闭合报告不是恒红的空转：profile 齐备 + adapter 注册齐 ⇒ closed。"""
        registry = RG.WorkpaperSyncAdapterRegistry(manifest=manifest_of(manifest_entry()))
        registry.register(registration(contract=reviewed_contract))
        report = registry.build_report(contract_ids=("g7.disclosure.listed",))
        assert report.blocking_total == 0, report.blocking_counts
        assert report.closed is True


# ═══════════════════════════════════════════════════════════════════════════
# 本任务边界（守卫锁住「不做的事」）
# ═══════════════════════════════════════════════════════════════════════════

_TASK13_MODULES = (
    _CONTRACTS_PY, _BASE_PY, _REGISTRY_PY, _INTEROP_PY, _PROFILE_PY,
)


class TestTask13ScopeBoundary:
    """「只建文档无关 schema/registry」是可验证的承诺，不是自我声明。"""

    def test_no_excel_or_word_engine_dependency(self) -> None:
        for path in _TASK13_MODULES:
            body = _stripped(path)
            for forbidden in ("openpyxl", "docx", "python-docx", "lxml", "xlsxwriter"):
                assert f"import {forbidden}" not in body, (
                    f"{path.name} 引入了载体库 {forbidden} —— Excel/Word engine 由 "
                    "Tasks 36~38 / 59~61 在各自 gate 通过后实现"
                )

    def test_engine_adapters_match_the_delivery_registry_exactly(self) -> None:
        """`adapters/` 里的模块集合必须与 engine 交付登记**双向等值**。

        🔴 本判据取代 Task 13 时期的 `test_engine_packages_do_not_exist_yet`（写死
        `== ["__init__.py","base.py","registry.py"]`）。Task 38 落地 Excel adapter 后那条
        绝对清单必然过期，但判据**翻转而不是删除** —— 删掉之后「谁能往 `adapters/` 里塞
        engine」就再无人把守。四种偏离各自打红：

        * 出现未登记的 `adapters/*.py` ⇒ 有人绕过载体 gate 塞了个 engine adapter；
        * 登记了却没有文件 ⇒ 登记表与事实脱钩（同 `merge.RETIRED_DEFERRALS` 的形态）；
        * 登记的 `engine_modules` 缺一个 ⇒ adapter 是空壳（假绿第①源）；
        * `PENDING_ENGINE_ADAPTERS.forbidden_paths` 出现 ⇒ 载体门未过就先落地
          （Word engine 必须先过 F2-22/F2-23 的真实 OO 9.4 pilot）。
        """
        adapters_dir = _SYNC_DIR / "adapters"
        delivered = list(RG.DELIVERED_ENGINE_ADAPTERS)
        assert delivered, (
            "engine 交付登记为空 —— 若真的一个 engine adapter 都没交付，"
            "本判据应回到「只有 Task 13 三份文件」那一版，而不是留一张空表"
        )
        registered_names: list[str] = []
        for entry in delivered:
            for field_name in (
                "document_type", "delivered_by_task", "adapter_module",
                "engine_modules", "identity_gate", "reason",
            ):
                assert entry.get(field_name), (
                    f"{entry.get('document_type')!r} 的 engine 交付登记缺 {field_name}"
                )
            assert str(entry["delivered_by_task"]).isdigit(), entry["delivered_by_task"]
            assert len(str(entry["reason"])) >= 40, "交付理由过短，无法核对是否绕过载体门"
            module = str(entry["adapter_module"])
            assert module.startswith("app/services/workpaper_sync/adapters/"), module
            target = _BACKEND / "app" / module.split("app/", 1)[1]
            assert target.is_file(), (
                f"登记的 adapter 模块 {target} 不存在 —— 登记表与事实不符"
            )
            registered_names.append(target.name)
            for engine in entry["engine_modules"]:
                engine_path = _BACKEND / "app" / str(engine).split("app/", 1)[1]
                assert engine_path.is_file(), (
                    f"{module} 登记的 engine 模块 {engine_path} 不存在 —— "
                    "adapter 是空壳，protocol 方法没有真实实现可转手"
                )
            gate = _BACKEND / "data" / str(entry["identity_gate"])
            assert gate.is_file(), (
                f"{module} 登记的载体 gate 证据 {gate} 不存在 —— "
                "「探针已过门」这句话必须有可核对的落点（Requirement 6.16）"
            )
        assert sorted(p.name for p in adapters_dir.glob("*.py")) == sorted(
            set(RG.TASK13_ADAPTER_MODULES) | set(registered_names)
        ), (
            "`adapters/` 的模块集合与 engine 交付登记不等值 —— 多出来的文件意味着有人"
            "绕过载体 gate，少掉的意味着登记表过期"
        )
        for entry in RG.PENDING_ENGINE_ADAPTERS:
            for field_name in (
                "document_type", "blocking_task", "forbidden_paths",
                "identity_gate", "reason",
            ):
                assert entry.get(field_name), (
                    f"{entry.get('document_type')!r} 的未交付登记缺 {field_name}"
                )
            for rel in entry["forbidden_paths"]:
                banned = _BACKEND / "app" / str(rel).split("app/", 1)[1]
                assert not banned.exists(), (
                    f"{banned} 已存在，但 {entry['document_type']} engine 的载体门仍挂在 "
                    f"任务 {entry['blocking_task']} 上 —— 未过 pilot 门不得落地 adapter"
                )
        delivered_types = {str(e["document_type"]) for e in delivered}
        pending_types = {str(e["document_type"]) for e in RG.PENDING_ENGINE_ADAPTERS}
        assert not (delivered_types & pending_types), (
            f"同一 document_type 同时登记为已交付与未交付: "
            f"{sorted(delivered_types & pending_types)}"
        )

    def test_no_representation_publish_or_candidate_finalize(self) -> None:
        """本任务不发布 representation、也不 finalize upgrade candidate。

        🔴 判据是「**调用**」而不是「出现这个词」：`base.py` 的
        `FORBIDDEN_SIDE_EFFECT_ATTRS` 恰恰要把 `finalize_candidate` /
        `set_entry_pointer` 写进**禁用名单字符串**里。按词出现判会把「明令禁止」
        误判成「正在调用」（首轮实测假红）。
        """
        for path in _TASK13_MODULES:
            body = _stripped(path)
            for forbidden in (
                "finalize_candidate", "publish_representation", "set_entry_pointer",
                "RepresentationService",
            ):
                calls = re.findall(rf"{re.escape(forbidden)}\s*\(", body)
                assert not calls, (
                    f"{path.name} 调用了 {forbidden} —— representation finalize 归 "
                    "Tasks 15/17/36，本任务只建 schema/registry"
                )

    def test_scope_judgement_distinguishes_denylist_from_call(self) -> None:
        """反向自检：名单里写着的名字不算调用，真调用必须被抓。"""
        denylist_only = 'FORBIDDEN = {"finalize_candidate", "set_entry_pointer"}'
        real_call = "await service.finalize_candidate(candidate_id)"
        pattern = r"finalize_candidate\s*\("
        assert not re.findall(pattern, denylist_only), "名单字符串被误判成调用 ⇒ 假红"
        assert re.findall(pattern, real_call), "真调用没被抓 ⇒ 假绿"

    def test_no_session_or_repository_import(self) -> None:
        """schema/registry 层不连库：AsyncSession/repository 一律不 import。"""
        for path in (_CONTRACTS_PY, _BASE_PY, _REGISTRY_PY, _INTEROP_PY, _PROFILE_PY):
            body = _stripped(path)
            assert "AsyncSession" not in body, f"{path.name} import 了 AsyncSession"
            assert "repository" not in body, f"{path.name} 依赖 repository"

    def test_contract_directory_matches_the_delivery_ledger(self) -> None:
        """逐 entry 契约由 Tasks 36 / 40~57 / 62~64 填；目录 ↔ 登记表**双向等值**。

        Task 13 交付时这里断言的是「空清册」。Task 40 发布第一份生产契约后那条绝对清册
        必然过期，但判据不能删 —— 删掉之后「谁能往契约目录里放生产契约」就无人把守。
        改成与 :data:`RG.DELIVERED_PER_ENTRY_CONTRACTS` 双向锁死：

        * 出现未登记的生产契约 ⇒ 打红（绕过 pilot 门）；
        * 登记了却没有文件 ⇒ 打红（登记表与事实脱钩）；
        * 登记的 entry 不在 source-backed manifest ⇒ 打红（契约指向已消失的入口）。

        「契约有了但 adapter 还没注册」仍是**可见欠账**：
        `RegistryReport.contract_files_without_adapter` 持续报它。
        """
        on_disk = set(C.available_contract_ids())
        ledger = {str(row["contract_id"]) for row in RG.DELIVERED_PER_ENTRY_CONTRACTS}
        assert on_disk == ledger, (
            f"契约目录与交付登记表不符：仅在磁盘 {sorted(on_disk - ledger)}；"
            f"仅在登记表 {sorted(ledger - on_disk)}"
        )
        manifest = json.loads(
            (_BACKEND / "data" / "workpaper_sync_entry_manifest.json").read_text(
                encoding="utf-8"
            )
        )
        entry_ids = {str(item["entry_id"]) for item in manifest["entries"]}
        for row in RG.DELIVERED_PER_ENTRY_CONTRACTS:
            contract = C.load_contract(str(row["contract_id"]))
            assert contract.document_type == row["document_type"], row["contract_id"]
            assert str(row["entry_id"]) in entry_ids, (
                f"登记的 entry {row['entry_id']!r} 不在 source-backed manifest 里"
            )
            assert str(row["reason"]).strip(), f"{row['contract_id']} 缺交付理由"
        assert (C.CONTRACTS_DIR / "README.md").is_file(), "契约目录必须有 schema 说明"

    def test_task13_modules_declare_spec_and_requirements(self) -> None:
        """可追溯性：每个模块 docstring 必须写明 spec 与 Requirements。"""
        for path in _TASK13_MODULES:
            head = _read(path)[:2000]
            assert "workpaper-html-onlyoffice-bidirectional-writeback-closure" in head, (
                f"{path.name} 缺 spec 溯源"
            )
            assert "Requirement" in head, f"{path.name} 缺 Requirements 溯源"


# ═══════════════════════════════════════════════════════════════════════════
# 反向自检：判据不是空转
# ═══════════════════════════════════════════════════════════════════════════


class TestGuardSelfCheck:
    """用替身复现三种已实证的假绿形态，证明真实判据确实在起作用。"""

    def test_source_ref_only_parser_would_accept_col_placeholder(self) -> None:
        """把 Property 20 合成一条（只查 source_ref）会放过 col 占位。"""

        def lenient(field: Mapping[str, Any]) -> bool:
            # 旧写法：「无语义 col_* **且** 无 source_ref」才拒 ⇒ 有 source_ref 就放行
            return bool(field.get("source_ref"))

        offender = {
            "stable_field_key": "equity_changes/{row_uuid}/col_h",
            "source_ref": "源xlsx!H8",
        }
        assert lenient(offender) is True, "替身必须放行，否则本自检没意义"
        with pytest.raises(C.ContractSchemaError):
            C.assert_stable_key(offender["stable_field_key"], location="probe")

    def test_descriptor_derived_capability_makes_fake_bidirectional_unreachable(
        self,
    ) -> None:
        """把 `declared_capability` 定义成 `descriptor.mode` ⇒ RG-18 结构性不可达。

        RG-16 要求 `descriptor.mode == manifest capability`，因此派生定义下
        「declared=bidirectional 而 capability≠bidirectional」这个组合根本构造不出来。
        """
        capability = EP.Capability.single_onlyoffice
        descriptor = EP.DescriptorFacts(
            mode=EP.DescriptorMode.single_onlyoffice, exposes_mode_switch=False
        )
        derived = descriptor.mode.value == EP.Capability.bidirectional.value
        assert derived is False, "派生定义下伪双向永远为 False ⇒ RG-18 是死代码"
        # 真实实现用独立字段，因此该组合可构造、可被拒。
        independent = EP.Capability.bidirectional is not capability
        assert independent is True

    def test_prefix_only_projection_matching_would_accept_wrong_key(
        self, reviewed_contract: C.SyncContract
    ) -> None:
        templates = [f.stable_field_key for f in reviewed_contract.all_fields()]
        wrong = "equity_changes/abc/closing_amount/extra"
        assert any(
            wrong.startswith(t.split("{row_uuid}")[0]) for t in templates
        ), "替身（只比前缀）必须放行"
        projection = AB.Projection(
            contract_id=reviewed_contract.contract_id,
            semantic_version="1.0.0",
            document_type="xlsx",
            values={
                wrong: AB.FieldValue(
                    stable_key=wrong,
                    value=1,
                    value_type=C.ValueType.integer,
                    mode=C.FieldMode.editable,
                    row_key="abc",
                )
            },
        )
        with pytest.raises(AB.ProjectionShapeError):
            projection.assert_matches_contract(reviewed_contract)

    def test_json_stringify_style_canonicalizer_would_diverge(self) -> None:
        """反向自检：不排序键的序列化在键序扰动下字节不同 ⇒ 排序判据真的在起作用。"""
        naive_a = json.dumps({"z": 1, "a": 2}, ensure_ascii=False, separators=(",", ":"))
        naive_b = json.dumps({"a": 2, "z": 1}, ensure_ascii=False, separators=(",", ":"))
        assert naive_a != naive_b, "替身必须分叉，否则本自检没意义"
        assert D.canonical_json_bytes({"z": 1, "a": 2}) == D.canonical_json_bytes(
            {"a": 2, "z": 1}
        )

    def test_marker_impersonation_would_pass_a_presence_only_check(self) -> None:
        """只查「contract slot 是否存在」会放过 marker 冒充 approved contract。"""
        slots = {
            BundleSlot.template: def_slot(BundleSlot.template, TEMPLATE_DEF),
            BundleSlot.instrumentation: def_slot(BundleSlot.instrumentation, INSTR_DEF),
            BundleSlot.contract: marker_slot(BundleSlot.contract),
        }
        assert BundleSlot.contract in slots, "存在性检查放行 ⇒ 必须有 is_definition 判据"
        assert slots[BundleSlot.contract].is_definition is False
        with pytest.raises(BundleIntegrityError):
            D.build_bundle_canonical_payload(
                authority_model=AuthorityModel.projection_contract,
                authority_model_definition_sha256=AUTHORITY_DEF,
                slots=slots,
            )
