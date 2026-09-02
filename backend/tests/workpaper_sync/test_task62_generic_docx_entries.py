"""Task 62 守卫 —— 18 个 generic DOCX entry 的逐 entry 裁决记录。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 6 Task 62
点名 Property：**30 / 31 / 32 / 33 / 34 / 69 / 70**；点名 AC：7.1 · 7.3 · 7.4 · 7.5 ·
7.6 · 7.8 · 12.1 · 12.5 · 12.10 · 12.11 · 12.12。

═══ 被守的产物 ═══

* `backend/scripts/gen/generate_task62_generic_docx_adjudication.py`（生成器；本文件
  **import 它并现读它的推导函数**，不抄一份 verdict 规则）
* `backend/data/workpaper_sync_task62_generic_docx_adjudication.json`（裁决记录）

═══ 本轮判据与 Task 60 守卫的关键差异（照抄会假绿的点）═══

1. **本轮没有契约、没有 bundle、没有 representation、没有 adapter** —— 18 个 entry 全部
   blocked。因此「六族 0」不能只断言 `== 0`：本文件对每一族都要求**分母 = 18** 且
   **判据能真命中**（合成一个正例让计数从 0 变 1），否则 `== 0` 只是空转。
2. **verdict 必须是推导出来的**。本文件把记录里的 `structure` / `anchor_analysis`
   原样喂回生成器的 `derive_verdict()` / `derive_blocking_reasons()` 重算并逐 entry 等值
   —— 有人把 JSON 里的 verdict 手改成「可迁移」时必须打红。
3. **「机制探针」与「契约」必须在结构上分得开**。探针跑通了 tagged-SDT 注入，很容易被
   误读成「这个 entry 可以迁移了」。本文件断言：探针 `is_not_a_contract=True`、
   `probe_id` 带 `probe.` 前缀且在 staged 契约目录里**没有**同名文件、entry 的
   `contract` 恒为 `None`、`entries_with_instrumentable_verdict == 0`。
4. **`literal_anchor_split_across_runs` 这一族要用两侧计数的差证明**，不能只信记录：
   python-docx 视图的候选数与原始 `word/document.xml` 的 verbatim 计数在本文件里各算
   一次，两者不一致的 entry 集合必须与记录一致。
5. **Task 62 不得往 F2 lane 写一个字节**。本文件断言 staged 契约目录里的文件集合**恰好**
   等于 F2 发布记录里登记的那些 contract_id，多一个即红。

═══ 判据强度约定 ═══

* 三边锁：清册（Task 58 JSON）→ 磁盘真读（`zipfile` + `python-docx` 现读
  `backend/wp_templates/`）→ impl 现读（`_LEGACY_COMPILED` / `_NEW_PLACEHOLDER_RE` /
  `WordSdtCarrierGate` / `PENDING_ENGINE_ADAPTERS`）。
* counters 全族现算等值 **+ 覆盖面元判据**（记录里每个数值键都必须被本文件的重算表覆盖，
  少一个即红 —— 新增计数器而不补守卫会打红）。
* 载体/锚点恒拒判据一律**真喂进门看它抛**，不在源码里搜字符串。
* 禁 `except Exception` fail-open；反向自检要「故意写错必失败」。

用法（仓库根；PATH 上的 `python` 可能指向坏掉的解释器）::

    .\\.venv\\Scripts\\python.exe -m pytest backend/tests/workpaper_sync/test_task62_generic_docx_entries.py -q
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path
from typing import Any

import pytest

# ════════════════════════════════════════════════════════════════════════════
# 路径与自举
# ════════════════════════════════════════════════════════════════════════════
_THIS = Path(__file__).resolve()
ROOT = _THIS.parents[3]
BACKEND = ROOT / "backend"
DATA = BACKEND / "data"
GEN_DIR = BACKEND / "scripts" / "gen"
TEMPLATE_ROOT = BACKEND / "wp_templates"

for _p in (BACKEND, GEN_DIR):
    if str(_p) not in sys.path:  # pragma: no cover - import 自举
        sys.path.insert(0, str(_p))

import generate_task62_generic_docx_adjudication as GEN  # noqa: E402

from app.services.wp_docx_template_parser import (  # noqa: E402
    _LEGACY_COMPILED,
    _NEW_PLACEHOLDER_RE,
    parse_template,
)
from app.services.workpaper_sync import contracts as C  # noqa: E402
from app.services.workpaper_sync import word_instrumentation as WI  # noqa: E402
from app.services.workpaper_sync.adapters import registry as RG  # noqa: E402

RECORD_PATH = DATA / "workpaper_sync_task62_generic_docx_adjudication.json"
LEDGER_PATH = DATA / "workpaper_word_template_adjudication.json"
F2_PUBLICATION_PATH = DATA / "workpaper_sync_f2_word_lane_publication.json"
STAGED_WORD_CONTRACT_DIR = DATA / "workpaper_sync_word_contracts"
GENERATOR_PATH = GEN_DIR / "generate_task62_generic_docx_adjudication.py"


# ════════════════════════════════════════════════════════════════════════════
# fixtures
# ════════════════════════════════════════════════════════════════════════════


@pytest.fixture(scope="module")
def record() -> dict[str, Any]:
    assert RECORD_PATH.is_file(), (
        f"{RECORD_PATH.name} 不存在 —— 先跑生成器 `--write`；"
        "缺文件时本套件必须打红而不是 skip"
    )
    payload = json.loads(RECORD_PATH.read_text(encoding="utf-8"))
    assert payload.get("schema_version") == GEN.SCHEMA_VERSION
    assert payload.get("task") == GEN.OWNER_TASK
    return payload


@pytest.fixture(scope="module")
def entries(record: dict[str, Any]) -> list[dict[str, Any]]:
    rows = record["entries"]
    assert rows, "记录里 `entries` 为空 —— 空清单会让本套件几乎全部恒真（假绿第⑥源）"
    return rows


@pytest.fixture(scope="module")
def ledger_codes() -> list[str]:
    ledger = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
    codes = [
        str(r["wp_code"])
        for r in ledger["rows"]
        if str(r.get("owner_task")) == GEN.OWNER_TASK
    ]
    assert codes, "Task 58 清册里 owner_task=62 为 0 条 —— 分母为空"
    return sorted(codes)


def _raw_document_xml(rel: str) -> str:
    with zipfile.ZipFile(TEMPLATE_ROOT / rel) as zf:
        return zf.read("word/document.xml").decode("utf-8")


def _ast_facts(source: str) -> tuple[set[str], set[str], set[str]]:
    """从源码 AST 抽出 `(import 的模块名, 被调用的名字, write_text 的接收者名)`。

    走 AST 而不是子串：文档字符串里提到 `finalize_candidate` 是**说明**，不是调用点。
    """
    tree = ast.parse(source)
    imports: set[str] = set()
    calls: set[str] = set()
    writes: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.add(node.module)
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                calls.add(func.id)
            elif isinstance(func, ast.Attribute):
                calls.add(func.attr)
                if func.attr == "write_text":
                    recv = func.value
                    if isinstance(recv, ast.Name):
                        writes.add(recv.id)
                    elif isinstance(recv, ast.Attribute):
                        writes.add(recv.attr)
                    else:
                        writes.add(ast.dump(recv)[:40])
    return imports, calls, writes


def _generator_ast_facts() -> tuple[set[str], set[str], set[str]]:
    return _ast_facts(GENERATOR_PATH.read_text(encoding="utf-8"))


def _generator_function_ast(name: str) -> ast.FunctionDef:
    """按名字取生成器里某个顶层函数的 AST（取不到即抛，不返回 None）。"""
    tree = ast.parse(GENERATOR_PATH.read_text(encoding="utf-8"))
    hits = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == name
    ]
    assert len(hits) == 1, f"生成器里名为 {name!r} 的顶层函数现算 {len(hits)} 个"
    return hits[0]


# ════════════════════════════════════════════════════════════════════════════
# §1 守卫自检（每条判据的分母都必须非空，且比较器真的敏感）
# ════════════════════════════════════════════════════════════════════════════


class TestGuardSelfChecks:
    def test_vocabularies_are_non_empty_and_disjoint(self) -> None:
        assert len(GEN.ENTRY_VERDICTS) >= 3
        assert len(set(GEN.ENTRY_VERDICTS)) == len(GEN.ENTRY_VERDICTS)
        assert len(GEN.BLOCKING_REASONS) >= 5
        assert len(set(GEN.BLOCKING_REASONS)) == len(GEN.BLOCKING_REASONS)
        # 两张封闭词表不得共用取值 —— 否则「verdict 是 reason」这种混用无人把守。
        assert not (set(GEN.ENTRY_VERDICTS) & set(GEN.BLOCKING_REASONS))

    def test_unrecognised_pattern_table_is_non_empty_and_compiles(self) -> None:
        assert GEN.UNRECOGNISED_PLACEHOLDER_PATTERNS, (
            "「parser 不认的占位形态」清单为空 ⇒ `partial_field_fragment_anchor` 与 "
            "`unrecognised_placeholder_forms_present` 两条判据全部退化成恒假"
        )
        for name, pattern in GEN.UNRECOGNISED_PLACEHOLDER_PATTERNS:
            assert name and re.compile(pattern)

    def test_the_unrecognised_detector_really_fires(self) -> None:
        """反向自检：合成文本必须被检出，空文本必须检不出。"""
        hit = GEN._unrecognised_in_text("系事务所第YY次会议记录", [])
        assert hit.get("ordinal_yy_slot") == 1, hit
        assert GEN._unrecognised_in_text("完全没有占位的一句话", []) == {}

    def test_the_unrecognised_detector_excludes_covered_spans(self) -> None:
        """已被 legacy 正则命中的 span 不得重复计入「未识别形态」。"""
        text = "截至202X年XX月XX日"
        spans = GEN._legacy_spans(text)
        assert spans, "分母为空：该合成文本必须至少被一条 legacy 正则命中"
        covered = GEN._unrecognised_in_text(text, spans)
        uncovered = GEN._unrecognised_in_text(text, [])
        assert uncovered != covered, (
            "把已命中 span 排除前后结果相同 ⇒ 排除逻辑是空操作，"
            "「未识别形态」会把 legacy 已认的占位重复计一遍"
        )

    def test_overlap_classifier_distinguishes_three_kinds(self) -> None:
        """三类重叠各造一个正例，防「分类器只会返回 0」。"""
        mk = lambda a, b: ("f", "l", "x", a, b)  # noqa: E731
        assert GEN._span_overlaps([mk(0, 5), mk(0, 5)])["identical"] == 1
        assert GEN._span_overlaps([mk(0, 9), mk(2, 5)])["contained"] == 1
        assert GEN._span_overlaps([mk(0, 5), mk(3, 9)])["partial"] == 1
        assert GEN._span_overlaps([mk(0, 3), mk(5, 9)]) == {
            "identical": 0,
            "contained": 0,
            "partial": 0,
        }


# ════════════════════════════════════════════════════════════════════════════
# §2 三边锁：清册 ↔ 磁盘 ↔ impl
# ════════════════════════════════════════════════════════════════════════════


class TestThreeWayLock:
    def test_entry_set_equals_the_task58_ledger(
        self, entries: list[dict[str, Any]], ledger_codes: list[str]
    ) -> None:
        recorded = [e["wp_code"] for e in entries]
        assert len(set(recorded)) == len(recorded), f"记录里 wp_code 重复: {recorded}"
        assert sorted(recorded) == ledger_codes, (
            "裁决记录的 entry 集合与 Task 58 清册的 owner_task=62 不等 —— "
            f"记录 {sorted(recorded)} vs 清册 {ledger_codes}"
        )

    def test_template_identity_recomputes_from_disk(
        self, entries: list[dict[str, Any]]
    ) -> None:
        for e in entries:
            rel = e["template"]["relative_path"]
            path = TEMPLATE_ROOT / rel
            assert path.is_file(), f"{e['wp_code']}: 权威模板不存在 {path}"
            data = path.read_bytes()
            assert e["template"]["size"] == len(data), e["wp_code"]
            assert e["template"]["template_sha256"] == hashlib.sha256(data).hexdigest(), (
                f"{e['wp_code']}: template_sha256 与磁盘不符"
            )
            assert e["template"]["normalized_structure_hash"] == WI.word_structure_hash(
                data
            ), f"{e['wp_code']}: normalized_structure_hash 与 impl 现算不符"

    def test_structure_facts_recompute_from_raw_xml(
        self, entries: list[dict[str, Any]]
    ) -> None:
        for e in entries:
            xml = _raw_document_xml(e["template"]["relative_path"])
            st = e["structure"]
            assert st["table_count"] == xml.count("<w:tbl>"), e["wp_code"]
            assert st["existing_sdt_count"] == xml.count("<w:sdt>") + xml.count(
                "<w:sdt "
            ), e["wp_code"]
            assert st["declared_dollar_token_count"] == len(
                _NEW_PLACEHOLDER_RE.findall(xml)
            ), f"{e['wp_code']}: `${{...}}` 声明 token 计数与原始 XML 现算不符"

    def test_html_counterpart_field_ids_recompute_from_the_parser(
        self, entries: list[dict[str, Any]]
    ) -> None:
        """HTML 对端的字段身份必须由 `parse_template` 现算，不是记录里手写的。"""
        for e in entries:
            st = parse_template(str(TEMPLATE_ROOT / e["template"]["relative_path"]))
            observed = [ph.field_id for ph in st.placeholders]
            hc = e["html_counterpart"]
            assert hc["parser_field_ids"] == observed, e["wp_code"]
            assert hc["parser_placeholder_count"] == len(observed), e["wp_code"]
            assert hc["ordinal_suffixed_field_ids"] == [
                fid for fid in observed if re.search(r"_\d+$", fid)
            ], e["wp_code"]
            assert hc["distinct_labels"] == sorted({ph.label for ph in st.placeholders})

    def test_legacy_pattern_table_is_the_parsers_own(self) -> None:
        """候选来源必须是 parser 那份已编译正则本身（对象同一性）。"""
        assert _LEGACY_COMPILED, "`_LEGACY_PATTERNS` 为空 ⇒ 候选分母恒 0"
        # 生成器不得自带第二份中文标记表：它的 span 函数在同一段文本上必须与
        # 直接用 parser 正则算出的 span 完全一致。
        text = "××公司于202X年12月31日"
        direct: list[tuple[str, str, str, int, int]] = []
        remaining = _NEW_PLACEHOLDER_RE.sub("", text)
        for regex, field_id, label in _LEGACY_COMPILED:
            for m in regex.finditer(remaining):
                direct.append((field_id, label, m.group(0), m.start(), m.end()))
        assert GEN._legacy_spans(text) == direct

    def test_requirement_7_7_declared_count_is_read_live(
        self, record: dict[str, Any], ledger_codes: list[str]
    ) -> None:
        declared = GEN.requirement_7_7_declared()
        assert declared["declared_generic_docx"] == len(ledger_codes), (
            "AC 7.7 声明的 generic DOCX 数与 Task 58 清册实算不等 —— "
            f"{declared} vs 清册 {len(ledger_codes)}"
        )
        assert (
            record["counters"]["requirement_7_7_declared_generic_docx"]
            == declared["declared_generic_docx"]
        )


# ════════════════════════════════════════════════════════════════════════════
# §3 counters 全族现算 + 覆盖面元判据
# ════════════════════════════════════════════════════════════════════════════


def _recompute_counters(entries: list[dict[str, Any]]) -> dict[str, int]:
    def s(fn) -> int:
        return sum(fn(e) for e in entries)

    return {
        "entries_total": len(entries),
        "templates_read_from_authoritative_root": len(entries),
        "templates_with_declared_dollar_token": s(
            lambda e: 1 if e["structure"]["declared_dollar_token_count"] > 0 else 0
        ),
        "templates_with_existing_sdt": s(
            lambda e: 1 if e["structure"]["existing_sdt_count"] > 0 else 0
        ),
        "candidate_occurrences_total": s(
            lambda e: e["anchor_analysis"]["candidate_occurrences"]
        ),
        "merged_cell_duplicate_occurrences_total": s(
            lambda e: e["anchor_analysis"]["merged_cell_duplicate_occurrences"]
        ),
        "parser_placeholders_total": s(
            lambda e: e["html_counterpart"]["parser_placeholder_count"]
        ),
        "ordinal_suffixed_field_ids_total": s(
            lambda e: len(e["html_counterpart"]["ordinal_suffixed_field_ids"])
        ),
        "span_overlap_identical_total": s(
            lambda e: e["anchor_analysis"]["span_overlap"]["identical"]
        ),
        "span_overlap_contained_total": s(
            lambda e: e["anchor_analysis"]["span_overlap"]["contained"]
        ),
        "span_overlap_partial_total": s(
            lambda e: e["anchor_analysis"]["span_overlap"]["partial"]
        ),
        "entries_with_literal_anchor_split_across_runs": s(
            lambda e: 1 if e["anchor_analysis"]["literals_not_verbatim_in_raw_xml"] else 0
        ),
        "entries_with_unrecognised_placeholder_forms": s(
            lambda e: 1 if e["anchor_analysis"]["unrecognised_placeholder_forms"] else 0
        ),
        "authority_models_published": s(lambda e: 1 if e["authority_model"] else 0),
        "contracts_published_reviewed": s(lambda e: 1 if e["contract"] else 0),
        "definition_bundles_published": s(lambda e: 1 if e["definition_bundle"] else 0),
        "published_representations_finalized": s(
            lambda e: 1 if e["published_representation"] else 0
        ),
        "adapters_registered": s(lambda e: 1 if e["adapter_id"] else 0),
        "entries_left_unverifiable": s(
            lambda e: 1 if e["evidence"]["verification_state"] == "UNVERIFIABLE" else 0
        ),
        "mechanism_probe_runs": s(lambda e: 1 if e["mechanism_probe"].get("ran") else 0),
        "entries_with_instrumentable_verdict": s(
            lambda e: 1 if e["verdict"] == "instrumentable_literal_anchor" else 0
        ),
    }


class TestCountersRecomputeFromEntries:
    def test_every_recomputable_counter_matches(
        self, record: dict[str, Any], entries: list[dict[str, Any]]
    ) -> None:
        want = _recompute_counters(entries)
        got = record["counters"]
        for key, value in want.items():
            assert got[key] == value, f"counter {key}: 记录 {got.get(key)} vs 现算 {value}"

    def test_no_numeric_counter_escapes_the_guard(self, record: dict[str, Any]) -> None:
        """覆盖面元判据：记录里每个数值计数器都必须被本文件重算或显式豁免。

        新增一个计数器而不补守卫 ⇒ 打红。豁免只有两类，各写清理由。
        """
        exempt = {
            # 由 requirements.md 现读，不由 entries 求和（另有 §2 的专门判据）。
            "requirement_7_7_declared_generic_docx",
            # 由 staged 目录现扫，不由 entries 求和（另有 §6 的专门判据）。
            "task62_contract_files_in_staged_dir",
        }
        numeric = {
            k
            for k, v in record["counters"].items()
            if isinstance(v, int) and not isinstance(v, bool)
        }
        covered = set(_recompute_counters(record["entries"])) | exempt
        assert numeric <= covered, (
            f"这些数值计数器没有任何守卫在算: {sorted(numeric - covered)} —— "
            "无人复算的计数器可以被任意手改"
        )

    def test_verdict_and_reason_histograms_match(
        self, record: dict[str, Any], entries: list[dict[str, Any]]
    ) -> None:
        verdicts: dict[str, int] = {}
        reasons: dict[str, int] = {}
        for e in entries:
            verdicts[e["verdict"]] = verdicts.get(e["verdict"], 0) + 1
            for r in e["blocking_reasons"]:
                reasons[r] = reasons.get(r, 0) + 1
        assert record["counters"]["verdicts"] == dict(sorted(verdicts.items()))
        assert record["counters"]["blocking_reasons"] == dict(sorted(reasons.items()))
        assert sum(verdicts.values()) == len(entries), "每个 entry 必须恰有一个 verdict"


# ════════════════════════════════════════════════════════════════════════════
# §4 verdict 是推导出来的，不是写在 JSON 里的
# ════════════════════════════════════════════════════════════════════════════


class TestVerdictsAreDerivedNotDeclared:
    def test_every_verdict_recomputes_from_the_recorded_facts(
        self, entries: list[dict[str, Any]]
    ) -> None:
        for e in entries:
            assert GEN.derive_verdict(e) == e["verdict"], (
                f"{e['wp_code']}: 记录里的 verdict={e['verdict']!r} 与按同一批事实"
                f"重算的 {GEN.derive_verdict(e)!r} 不符 —— verdict 被手改过"
            )
            assert GEN.derive_blocking_reasons(e) == e["blocking_reasons"], e["wp_code"]

    def test_verdicts_are_inside_the_closed_vocabulary(
        self, entries: list[dict[str, Any]]
    ) -> None:
        for e in entries:
            assert e["verdict"] in GEN.ENTRY_VERDICTS, e["wp_code"]
            for r in e["blocking_reasons"]:
                assert r in GEN.BLOCKING_REASONS, (e["wp_code"], r)

    def test_every_blocked_entry_lists_at_least_one_reason(
        self, entries: list[dict[str, Any]]
    ) -> None:
        for e in entries:
            if e["verdict"] == "instrumentable_literal_anchor":
                continue
            assert e["blocking_reasons"], (
                f"{e['wp_code']}: verdict={e['verdict']} 却一条阻塞原因都没有 —— "
                "无理由的阻塞无法区分「真阻塞」与「懒得裁决」"
            )

    def test_each_verdict_branch_is_reachable_on_synthetic_facts(self) -> None:
        """每个 verdict 取值都造一个合成事实命中它 —— 防「某个分支永久不可达」。"""

        def facts(**an: Any) -> dict[str, Any]:
            base = {
                "candidate_occurrences": 1,
                "merged_cell_duplicate_occurrences": 0,
                "max_literal_anchor_multiplicity": 1,
                "literals_not_verbatim_in_raw_xml": [],
                "span_overlap": {"identical": 0, "contained": 0, "partial": 0},
                "occurrences_whose_container_has_unrecognised_form": 0,
            }
            base.update(an)
            return {
                "wp_code": "SYNTH",
                "structure": {"declared_dollar_token_count": 0},
                "anchor_analysis": base,
            }

        assert GEN.derive_verdict(facts()) == "instrumentable_literal_anchor"
        assert (
            GEN.derive_verdict(
                {
                    "wp_code": "SYNTH",
                    "structure": {"declared_dollar_token_count": 3},
                    "anchor_analysis": facts()["anchor_analysis"],
                }
            )
            == "token_declared_template"
        )
        assert (
            GEN.derive_verdict(facts(candidate_occurrences=0))
            == "no_managed_field_candidate"
        )
        assert (
            GEN.derive_verdict(
                facts(span_overlap={"identical": 0, "contained": 1, "partial": 0})
            )
            == "blocked_nested_literal_anchor"
        )
        assert (
            GEN.derive_verdict(facts(max_literal_anchor_multiplicity=4))
            == "blocked_non_discriminating_literal_anchor"
        )
        assert (
            GEN.derive_verdict(facts(literals_not_verbatim_in_raw_xml=["202X年"]))
            == "blocked_literal_anchor_split_across_runs"
        )
        assert (
            GEN.derive_verdict(facts(occurrences_whose_container_has_unrecognised_form=1))
            == "blocked_partial_field_fragment_anchor"
        )

    def test_every_vocabulary_value_is_reachable_or_used(
        self, entries: list[dict[str, Any]]
    ) -> None:
        """封闭词表里不得有「既没人用、合成事实也命中不了」的死取值。"""
        used = {e["verdict"] for e in entries}
        # `token_declared_template` 与 `instrumentable_literal_anchor` 当前实测无 entry
        # 命中，但上一条测试已用合成事实证明它们可达 —— 这里只锁住「其余取值都真被用到」。
        synthetic_only = {"token_declared_template", "instrumentable_literal_anchor"}
        assert set(GEN.ENTRY_VERDICTS) - synthetic_only <= used, (
            f"这些 verdict 既无 entry 命中、也未登记为 synthetic-only: "
            f"{sorted(set(GEN.ENTRY_VERDICTS) - synthetic_only - used)}"
        )


# ════════════════════════════════════════════════════════════════════════════
# §5 「split across runs」这一族用两侧计数的差独立证明
# ════════════════════════════════════════════════════════════════════════════


class TestSplitAcrossRunsIsProvedByTwoViews:
    def test_raw_xml_verbatim_counts_recompute(
        self, entries: list[dict[str, Any]]
    ) -> None:
        for e in entries:
            xml = _raw_document_xml(e["template"]["relative_path"])
            want = {
                lit: xml.count(lit)
                for lit in e["anchor_analysis"]["literal_anchor_multiplicity"]
            }
            assert e["anchor_analysis"]["raw_xml_verbatim_counts"] == want, e["wp_code"]
            assert e["anchor_analysis"]["literals_not_verbatim_in_raw_xml"] == sorted(
                lit for lit, cnt in want.items() if cnt == 0
            ), e["wp_code"]

    def test_the_two_views_really_disagree_somewhere(
        self, record: dict[str, Any], entries: list[dict[str, Any]]
    ) -> None:
        """非空跑证明：至少一个 entry 的 python-docx 视图与原始 XML 视图不一致。

        这一族若为 0，`blocked_literal_anchor_split_across_runs` 就是恒假分支；
        本 spec 反复记录的假绿第①源正是这种「登记了但永不命中」的判据。
        """
        disagreeing = [
            e["wp_code"]
            for e in entries
            if e["anchor_analysis"]["literals_not_verbatim_in_raw_xml"]
        ]
        assert disagreeing, (
            "没有任何 entry 的候选 literal 在原始 XML 里找不到 ⇒ "
            "`literal_anchor_split_across_runs` 判据从未命中，分母为空"
        )
        assert (
            record["counters"]["entries_with_literal_anchor_split_across_runs"]
            == len(disagreeing)
        )

    def test_the_engines_own_locator_refuses_a_split_anchor(
        self, entries: list[dict[str, Any]]
    ) -> None:
        """真跑一次：被判 split 的 entry 喂给注入引擎必须 fail closed。

        判据落在**真实执行**（引擎抛 `WordTokenAnchorError`），不在源码里搜字符串。
        """
        split = [
            e
            for e in entries
            if e["verdict"] == "blocked_literal_anchor_split_across_runs"
        ]
        assert split, "分母为空：没有 split verdict 的 entry 可喂"
        e = split[0]
        anchor = e["anchor_analysis"]["literals_not_verbatim_in_raw_xml"][0]
        spec = WI.WordInstrumentationSpec(
            entry_id="probe.task62.selfcheck",
            contract_id="probe.task62.selfcheck",
            template_id="probe.task62.selfcheck",
            template_relative_path=e["template"]["relative_path"],
            fields=(
                WI.WordFieldInjection(
                    token=anchor,
                    stable_field_key="probe/split",
                    literal_anchor=True,
                    expected_token_occurrences=1,
                ),
            ),
        )
        source = (TEMPLATE_ROOT / e["template"]["relative_path"]).read_bytes()
        with pytest.raises(WI.WordTokenAnchorError):
            WI.instrument_docx_bytes(source, spec, gate=WI.WordSdtCarrierGate.load())


# ════════════════════════════════════════════════════════════════════════════
# §6 没有伪造供给：零契约、零 bundle、零 representation、零 adapter
# ════════════════════════════════════════════════════════════════════════════


class TestNoForgedSupply:
    @pytest.mark.parametrize(
        "field",
        [
            "authority_model",
            "contract",
            "definition_bundle",
            "published_representation",
            "adapter_id",
            "capability",
        ],
    )
    def test_supply_field_is_null_for_every_entry(
        self, entries: list[dict[str, Any]], field: str
    ) -> None:
        offenders = [e["wp_code"] for e in entries if e[field] is not None]
        assert not offenders, (
            f"{field} 在 {offenders} 上非空 —— 18 个 entry 全部 blocked（BP-20），"
            "任何非空供给都是伪造（Task 62 正文：不为满足数字伪造 contract/bundle/finalize）"
        )
        # 非空跑：分母确实是 18 个 entry，而不是空列表。
        assert len(entries) == len(entries) and entries

    def test_zero_families_have_a_real_denominator_and_a_live_predicate(
        self, record: dict[str, Any], entries: list[dict[str, Any]]
    ) -> None:
        """六族 0 各自证明：分母 = entry 数，且把某个 entry 合成为正例后计数变 1。"""
        families = {
            "authority_models_published": "authority_model",
            "contracts_published_reviewed": "contract",
            "definition_bundles_published": "definition_bundle",
            "published_representations_finalized": "published_representation",
            "adapters_registered": "adapter_id",
        }
        for counter, field in families.items():
            assert record["counters"][counter] == 0, counter
            mutated = [dict(e) for e in entries]
            mutated[0][field] = {"synthetic": True} if field != "adapter_id" else "x"
            assert _recompute_counters(mutated)[counter] == 1, (
                f"{counter} 的判据在合成正例上仍算 0 ⇒ 它是恒 0 的空转，"
                "而不是「实测没有」"
            )

    def test_staged_contract_dir_holds_only_the_f2_lane_files(
        self, record: dict[str, Any]
    ) -> None:
        """Task 62 往 staged 契约目录写 0 份 —— 目录内容必须恰等于 F2 登记的那些。"""
        f2 = json.loads(F2_PUBLICATION_PATH.read_text(encoding="utf-8"))
        expected = sorted(
            f"{(e.get('contract') or {}).get('contract_id')}.json"
            for e in f2["entries"]
        )
        assert expected and all(n != "None.json" for n in expected)
        on_disk = sorted(p.name for p in STAGED_WORD_CONTRACT_DIR.glob("*.json"))
        assert on_disk == expected, (
            f"staged 契约目录内容 {on_disk} 与 F2 发布记录登记的 {expected} 不等 —— "
            "Task 62 不得往 F2 lane 写入任何文件（cross_entry_isolation）"
        )
        assert record["counters"]["task62_contract_files_in_staged_dir"] == 0
        assert GEN.task62_contract_files() == []

    def test_the_generator_has_no_db_or_template_write_surface(self) -> None:
        """结构判据：生成器不 import DB 层，也不调用发布链 / 不往模板库写字节。

        🔴 判据走 **AST**，不走 substring：`BP-22` 的 evidence 文案里就写着
        「`WordEntryFinalizeGate.finalize_candidate` 要求 candidate 已绑 approved
        bundle」—— 按子串搜会把这句**说明文字**当成调用点误报（首版实测就是这个假红）。
        反过来，只搜注释外的字符串也不够：真正要判的是「有没有这个 import / 这个调用」。
        """
        imports, calls, write_targets = _generator_ast_facts()
        # 分母非空自检：AST 必须真的抽到东西，否则下面三条全是空集恒真。
        assert imports and calls, (imports, calls)

        forbidden_imports = ("sqlalchemy", "asyncpg", "app.models", "app.core.config")
        offending = sorted(
            m for m in imports if any(m == f or m.startswith(f + ".") for f in forbidden_imports)
        )
        assert not offending, (
            f"生成器 import 了 {offending} —— 本任务只产裁决记录，不得触碰 DB 层"
        )

        forbidden_calls = {
            "finalize_candidate",
            "finalize_definition_upgrade",
            "publish_definition",
            "publish_bundle",
            "stage_and_register_candidate",
            "create_upgrade_candidate",
            "commit",
            "ensure",
            "attach",
        }
        leaked = sorted(forbidden_calls & calls)
        assert not leaked, (
            f"生成器调用了发布链 / 写库入口 {leaked} —— 任何写入面都是越权（BP-20/22）"
        )

        assert write_targets == {"OUTPUT_PATH"}, (
            f"生成器的 `write_text` 接收者现算为 {sorted(write_targets)} —— "
            "只允许写裁决记录本身（OUTPUT_PATH），写模板库或契约目录都是越权"
        )

    def test_the_ast_write_surface_detector_really_fires(self) -> None:
        """反向自检：把一个违规调用喂给同一个抽取器，必须被抽到。"""
        imports, calls, writes = _ast_facts(
            "import sqlalchemy\n"
            "from app.models import x\n"
            "def f(p, gate):\n"
            "    gate.finalize_candidate()\n"
            "    p.write_text('x')\n"
            "    TEMPLATE_ROOT.write_text('y')\n"
        )
        assert "sqlalchemy" in imports and "app.models" in imports
        assert "finalize_candidate" in calls
        assert writes == {"p", "TEMPLATE_ROOT"}, writes

    def test_no_word_adapter_landed(self, record: dict[str, Any]) -> None:
        ban = record["word_adapter_ban"]
        assert ban["forbidden_paths"], "Word adapter 禁令的 forbidden_paths 为空 ⇒ 禁令失守"
        for rel in ban["forbidden_paths"]:
            assert not (BACKEND / rel).exists(), (
                f"{rel} 已存在 —— Task 61 门未过前不得落地 Word adapter"
            )
        assert ban["delivered_docx_engine_adapters"] == 0
        # impl 现读（不信记录）：禁令仍在，且没有 docx adapter 被登记为已交付。
        pending_docx = [
            r for r in RG.PENDING_ENGINE_ADAPTERS if r.get("document_type") == "docx"
        ]
        assert len(pending_docx) == 1
        assert all(
            r.get("document_type") != "docx" for r in RG.DELIVERED_ENGINE_ADAPTERS
        )

    def test_no_task62_entry_appears_in_the_per_entry_contract_registry(
        self, entries: list[dict[str, Any]]
    ) -> None:
        """本任务的 18 个 wp_code 一个都不得出现在生产契约交付登记表里。"""
        registered = {
            str(r.get("contract_id") or "") for r in RG.DELIVERED_PER_ENTRY_CONTRACTS
        }
        assert registered, "分母为空：交付登记表里一条都没有"
        for e in entries:
            probe = e["mechanism_probe"]
            candidate_ids = {
                f"generic.{e['wp_code'].lower().replace('-', '_')}",
                str(probe.get("probe_id") or ""),
            } - {""}
            leaked = candidate_ids & registered
            assert not leaked, (
                f"{e['wp_code']}: {sorted(leaked)} 出现在 "
                "`DELIVERED_PER_ENTRY_CONTRACTS` 里 —— blocked entry 不得进生产登记"
            )


# ════════════════════════════════════════════════════════════════════════════
# §7 载体 / 锚点恒拒（真喂进门，不搜字符串）
# ════════════════════════════════════════════════════════════════════════════


class TestBlockedCarriersAndAnchorsAreRefused:
    def test_probe_gate_lists_match_the_contract(self, record: dict[str, Any]) -> None:
        gate = C.load_word_carrier_gate()
        pg = record["probe_gate"]
        assert pg["carriers_allowed"] == sorted(gate.allowed_carriers)
        assert pg["carriers_blocked"] == sorted(gate.blocked_carriers)
        assert pg["anchors_allowed"] == sorted(gate.allowed_anchors)
        assert pg["anchors_blocked"] == sorted(gate.blocked_anchors)
        assert pg["carriers_blocked"], "blocked 载体为空集 ⇒ 「恒拒」是重言式"
        assert pg["anchors_blocked"], "blocked 锚点为空集 ⇒ 「恒拒」是重言式"
        assert not (set(pg["carriers_blocked"]) & set(pg["carriers_allowed"]))
        assert not (set(pg["anchors_blocked"]) & set(pg["anchors_allowed"]))

    def test_every_blocked_carrier_and_anchor_really_raises(
        self, record: dict[str, Any]
    ) -> None:
        gate = WI.WordSdtCarrierGate.load()
        for carrier in record["probe_gate"]["carriers_blocked"]:
            with pytest.raises(WI.WordCarrierGateError):
                gate.assert_carrier_allowed(carrier)
        for anchor in record["probe_gate"]["anchors_blocked"]:
            with pytest.raises(WI.WordCarrierGateError):
                gate.assert_anchor_allowed(anchor)
        # 正面：唯一正式锚点必须通过（防「门把一切都拒掉」的假强判据）。
        gate.assert_anchor_allowed("w_tag")

    def test_no_entry_declares_a_blocked_carrier(
        self, record: dict[str, Any], entries: list[dict[str, Any]]
    ) -> None:
        blocked = set(record["probe_gate"]["carriers_blocked"])
        for e in entries:
            probe = e["mechanism_probe"]
            if not probe.get("ran"):
                continue
            kinds = {
                v
                for values in probe["tag_readback"].get("kind_map", {}).values()
                for v in values
            }
            assert not (kinds & blocked), (e["wp_code"], kinds)


# ════════════════════════════════════════════════════════════════════════════
# §8 机制探针 ≠ 契约
# ════════════════════════════════════════════════════════════════════════════


class TestMechanismProbeIsNotAContract:
    def test_probe_eligibility_is_derived(self, entries: list[dict[str, Any]]) -> None:
        for e in entries:
            an = e["anchor_analysis"]
            eligible = (
                e["verdict"] == "blocked_partial_field_fragment_anchor"
                and int(an["max_literal_anchor_multiplicity"]) == 1
                and not an["literals_not_verbatim_in_raw_xml"]
            )
            assert bool(e["mechanism_probe"].get("ran")) is eligible, (
                f"{e['wp_code']}: 探针跑与否与实测资格不符 —— "
                f"ran={e['mechanism_probe'].get('ran')} eligible={eligible}"
            )
            assert (e["wp_code"] in GEN.MECHANISM_PROBE_ANCHORS) is eligible, (
                f"{e['wp_code']}: `MECHANISM_PROBE_ANCHORS` 的成员资格与实测不符"
            )

    def test_probe_ran_at_least_once(self, record: dict[str, Any]) -> None:
        assert record["counters"]["mechanism_probe_runs"] >= 1, (
            "一次机制探针都没跑 ⇒ 「tagged-SDT 机制在 generic 模板上可用」这条结论"
            "没有任何实测支撑（既不能宣称可用，也不能宣称不可用）"
        )

    def test_probe_is_explicitly_not_a_contract(
        self, entries: list[dict[str, Any]]
    ) -> None:
        staged_ids = {p.stem for p in STAGED_WORD_CONTRACT_DIR.glob("*.json")}
        for e in entries:
            probe = e["mechanism_probe"]
            assert probe.get("is_not_a_contract") is True, e["wp_code"]
            if not probe.get("ran"):
                continue
            assert probe["published"] is False
            assert probe["published_blocked_by"], e["wp_code"]
            assert probe["probe_id"].startswith("probe."), probe["probe_id"]
            assert probe["probe_id"] not in staged_ids, (
                f"{e['wp_code']}: 探针 id 与 staged 契约同名 ⇒ 会被误装载"
            )
            assert probe["fragment_of"] and probe["fragment_of"] != probe["literal_anchor"], (
                f"{e['wp_code']}: `fragment_of` 必须记录该锚点所属的完整人类占位，"
                "且不得等于锚点本身（等于就说明它不是片段，verdict 该改）"
            )

    def test_probe_equivalence_is_non_vacuous(
        self, entries: list[dict[str, Any]]
    ) -> None:
        """探针的「等价通过」必须建立在非空覆盖上，否则是空集恒真。"""
        for e in entries:
            probe = e["mechanism_probe"]
            if not probe.get("ran"):
                continue
            eq = probe["visible_equivalence"]
            assert eq["equivalent"] is True, e["wp_code"]
            cov = eq["coverage"]
            for key in ("visible_text_chars", "outside_sdt_text", "protected_parts"):
                assert int(cov.get(key, 0)) > 0, (
                    f"{e['wp_code']}: 等价覆盖 {key}=0 ⇒ 「注入前后可见等价」在空集上恒真"
                )
            rb = probe["tag_readback"]
            assert rb["tag_count"] >= 1 and rb["instance_count"] >= 1, e["wp_code"]
            assert rb["untagged_sdt_count"] == 0, e["wp_code"]
            assert probe["non_document_parts_byte_identical"] is True, (
                f"{e['wp_code']}: 除 word/document.xml 之外有 part 字节被改动 —— "
                "注入必须只动 document part"
            )
            assert int(probe["untouched_parts"]) > 0, e["wp_code"]

    def test_probe_occurrence_count_comes_from_the_raw_xml_view(
        self, entries: list[dict[str, Any]]
    ) -> None:
        """探针的 `expected_token_occurrences` 必须取**原始 XML** 的 verbatim 计数。

        🔴 为什么这条是**结构**判据而不是数值判据：当前两个探针 entry 上，
        python-docx 视图的计数（去重后 1）与原始 XML 的 verbatim 计数（1）**恰好相等**
        ⇒ 把取值换成另一侧是**等价变异**，任何数值断言都测不出来（变异 M15 实测 GREEN，
        原因是变异无效而不是守卫有缺陷）。但两者只在「该 entry 没有影响到该 literal 的
        合并单元格」时才相等，将来只要有一个探针 entry 落在合并单元格里就会分叉，
        而分叉的后果是 `_inject` 的 fail-closed 计数直接拒绝注入。
        故这里锁住**取值来源**：喂给 `occurrences` 的下标必须是
        `raw_xml_verbatim_counts`，且不得是 `literal_anchor_multiplicity`。
        """
        func = _generator_function_ast("mechanism_probe_evidence")
        targets = [
            node
            for node in ast.walk(func)
            if isinstance(node, ast.Assign)
            and any(
                isinstance(t, ast.Name) and t.id == "occurrences" for t in node.targets
            )
        ]
        assert len(targets) == 1, (
            f"`mechanism_probe_evidence` 里对 `occurrences` 的赋值现算 {len(targets)} 处 "
            "—— 判据要求恰一处，多处时无法判定「用的是哪一侧」"
        )
        keys = {
            n.value
            for n in ast.walk(targets[0].value)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
        }
        assert "raw_xml_verbatim_counts" in keys, (
            f"`occurrences` 的取值来源现算为 {sorted(keys)} —— 必须取原始 XML 的 "
            "verbatim 计数（注入引擎看到的那个数）"
        )
        assert "literal_anchor_multiplicity" not in keys, (
            "`occurrences` 取了 python-docx 视图的计数 —— 两侧在合并单元格上会分叉，"
            "喂错一侧会被 `_inject` 的 fail-closed 计数拒掉"
        )
        # 行为侧同时锁住：记录里两个视图都在，将来分叉时可见。
        for e in entries:
            probe = e["mechanism_probe"]
            if not probe.get("ran"):
                continue
            anchor = probe["literal_anchor"]
            assert probe["expected_token_occurrences"] == (
                e["anchor_analysis"]["raw_xml_verbatim_counts"][anchor]
            ), e["wp_code"]

    def test_probe_uses_only_a_one_time_locator(
        self, entries: list[dict[str, Any]]
    ) -> None:
        for e in entries:
            probe = e["mechanism_probe"]
            if not probe.get("ran"):
                continue
            assert probe["one_time_locator_kind"] in WI.ONE_TIME_LOCATOR_KINDS
            for tag in probe["injected_tags"]:
                assert tag.startswith("gt:field:") or tag.startswith("gt:block:")


# ════════════════════════════════════════════════════════════════════════════
# §9 跨 entry 隔离 + 阻塞前置结构
# ════════════════════════════════════════════════════════════════════════════


class TestCrossEntryIsolation:
    def test_template_identities_are_all_distinct(
        self, entries: list[dict[str, Any]]
    ) -> None:
        digests = [e["template"]["template_sha256"] for e in entries]
        assert len(set(digests)) == len(digests), (
            "两个 entry 的 template_sha256 相同 ⇒ 它们指向同一份模板，"
            "逐 entry 独立证据无从成立"
        )
        lanes = [e["lane_entry_key"] for e in entries]
        assert len(set(lanes)) == len(lanes), lanes

    def test_probe_ids_are_per_entry(self, entries: list[dict[str, Any]]) -> None:
        ids = [
            e["mechanism_probe"]["probe_id"]
            for e in entries
            if e["mechanism_probe"].get("ran")
        ]
        assert len(set(ids)) == len(ids), f"探针 id 被复用: {ids}"

    def test_lane_entry_key_is_not_claimed_to_be_a_manifest_entry(
        self, entries: list[dict[str, Any]]
    ) -> None:
        for e in entries:
            assert e["lane_entry_key_is_not_a_manifest_entry_id"] is True
            assert e["manifest_entry_state"] == "absent_from_source_manifest"


class TestBlockingPreconditions:
    def test_each_precondition_is_complete(self, record: dict[str, Any]) -> None:
        bps = record["blocking_preconditions"]
        assert bps, "阻塞前置为空 ⇒ 「全部 blocked」没有对应的解除路径"
        ids = [bp["id"] for bp in bps]
        assert len(set(ids)) == len(ids), ids
        for bp in bps:
            for key in (
                "title",
                "evidence",
                "consequence",
                "release_condition",
                "must_fix_before",
                "owner_task",
            ):
                assert bp.get(key), f"{bp['id']} 缺 {key}"
            assert isinstance(bp["evidence"], list) and bp["evidence"]

    def test_every_blocked_by_reference_resolves(
        self, record: dict[str, Any], entries: list[dict[str, Any]]
    ) -> None:
        known = {bp["id"] for bp in record["blocking_preconditions"]}
        for e in entries:
            for key, value in e.items():
                if not key.endswith("_blocked_by"):
                    continue
                assert value, f"{e['wp_code']}.{key} 为空 —— blocked 必须指向具体前置"
                unknown = set(value) - known
                assert not unknown, f"{e['wp_code']}.{key} 引用了未登记的前置 {unknown}"
            probe = e["mechanism_probe"]
            if probe.get("ran"):
                assert set(probe["published_blocked_by"]) <= known

    def test_precondition_ids_are_task_scoped(self, record: dict[str, Any]) -> None:
        """id 必须带 task-scoped 前缀，且不得与并发任务的全局 `BP-NN` 撞号。

        🔴 实测教训：Tasks 63 与 64 的裁决记录**各自**登记了 `BP-16`~`BP-20`
        （Task 64 到 `BP-22`），同号不同义 —— 全局单调编号在多会话并发下已被双重占用。
        本记录改用 `BP-62-N`，本条把它锁死：只要有人接回全局号就打红。
        """
        ids = [bp["id"] for bp in record["blocking_preconditions"]]
        assert ids, "分母为空"
        for bp_id in ids:
            assert re.fullmatch(r"BP-62-\d+", bp_id), (
                f"前置 id {bp_id!r} 不是 task-scoped 形态 —— 全局 `BP-NN` 已被 "
                "Tasks 63/64 双重占用（同号不同义），接回去会制造第三份冲突"
            )

    def test_the_field_identity_debt_is_out_of_scope_for_task62(
        self, record: dict[str, Any]
    ) -> None:
        """字段身份欠账那条必须写明它不属本任务权限，并指出与并发任务同根因。

        否则会被误读成「Task 62 自己改 parser / 模板库就行」—— 那会跨到
        `word-template-dual-mode` feature 与运行时权威模板库，两者都要自己的 spec。
        """
        hits = [
            bp
            for bp in record["blocking_preconditions"]
            if "稳定字段身份" in bp["title"]
        ]
        assert len(hits) == 1, f"字段身份欠账现算 {len(hits)} 条，应恰一条"
        bp = hits[0]
        text = bp["release_condition"] + bp["owner_task"]
        assert "spec" in text and "Task 62" in text, (
            "解除条件没写清「跨 feature、需自己的 spec、不属 Task 62 权限」"
        )
        assert bp.get("same_root_cause_as"), (
            "没有指出与 Tasks 63/64 的同根因登记 —— 三份独立记录各写一条「新欠账」会让"
            "同一根因看起来像三个问题"
        )
        assert bp.get("cross_lane_corroboration"), "缺跨 lane 复现说明"


# ════════════════════════════════════════════════════════════════════════════
# §10 生成器幂等 + `--check` 真的会拒绝漂移
# ════════════════════════════════════════════════════════════════════════════


class TestGeneratorIsIdempotentAndCheckIsStrict:
    def test_build_record_is_byte_stable(self, record: dict[str, Any]) -> None:
        again = GEN.build_record()
        assert GEN._canonical_text(again) == GEN._canonical_text(record), (
            "两次 build_record() 结果不一致 —— 记录含非确定性内容（时间戳/集合序），"
            "`--check` 会变成随机红"
        )

    def test_check_matches_the_file_on_disk(self) -> None:
        assert GEN.main(["--check"]) == 0

    def test_check_rejects_a_one_byte_drift(self, tmp_path: Path) -> None:
        """反向自检：把记录改一个字节，`--check` 必须抛而不是报成功。"""
        original = RECORD_PATH.read_text(encoding="utf-8")
        drifted = original.replace('"entries_total": ', '"entries_total":  ', 1)
        assert drifted != original, "构造漂移失败 —— 自检本身无效"
        RECORD_PATH.write_text(drifted, encoding="utf-8")
        try:
            with pytest.raises(GEN.Task62GeneratorError):
                GEN.main(["--check"])
        finally:
            RECORD_PATH.write_text(original, encoding="utf-8")
        assert RECORD_PATH.read_text(encoding="utf-8") == original
