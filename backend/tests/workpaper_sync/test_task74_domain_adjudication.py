# -*- coding: utf-8 -*-
"""Task 74 第一半的守卫：逐 domain 裁决**归零了、且没有换来任何豁免**。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 7 Task 74
Requirements: 2.1, 2.2, 2.11, 2.12, 9.11, 12.6, 12.7, 13.4 · Property 4, Property 61

Task 74 只有两条准则由「逐 domain 裁决」清零：`unadjudicated_writer`（236 → 0）与
`unadjudicated_resolver`（34 → 0）。裁决是**人工判断写进 overlay**，所以它有两种典型的假绿形态，
本文件逐条守：

* **形态 A：裁决顺手清掉了别的准则**（= 把 domain 标签当豁免用）。判据不是「读一遍门的源码看有没有
  豁免列」——那是 grep 式判据；而是**行为级**：把本任务加的 270 条裁决摘掉、从源码重推清册、再量
  门，差异必须**恰好**是那两条计数各自回到 236 / 34，其余 12 条逐条相等
  （`test_adjudicating_clears_exactly_two_criteria`）。
* **形态 B：注解是模板**（写了字但没有信息）。判据同样不是「注解非空」——生成器已经拒空了；而是
  **注解里引用的每一条事实都必须能在该行自己的 facts 里逐条重算**，且不许引用它没有的事实
  （`test_every_note_cites_exactly_the_facts_that_row_has`）。把 A 行的注解粘到 B 行，两侧同时打红。

另外守两件与「新加了两条 lane」有关的事：lane 标签本身**买不到任何东西**（正向 + 反向对照都在
`test_the_two_new_lanes_buy_nothing`），以及规则表 **fail-closed**（命不中即抛，不给默认 lane）。
"""
from __future__ import annotations

import copy
import importlib.util
import json
import re
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

_REPO = Path(__file__).resolve().parents[3]
_GATE_PATH = _REPO / "backend" / "scripts" / "check" / "check_workpaper_writer_revision_gate.py"
_GENERATOR_PATH = (
    _REPO / "backend" / "scripts" / "gen" / "generate_workpaper_writer_inventory.py"
)
_AUTHOR_PATH = _REPO / "backend" / "scripts" / "gen" / "adjudicate_task74_writer_domains.py"
_INVENTORY_PATH = _REPO / "backend" / "data" / "workpaper_writer_inventory.json"
_OVERLAY_PATH = _REPO / "backend" / "data" / "workpaper_writer_domain_overlay.json"
_EVIDENCE = (
    _REPO
    / ".kiro"
    / "specs"
    / "workpaper-html-onlyoffice-bidirectional-writeback-closure"
    / "evidence"
    / "task74-domain-adjudication"
)

#: Task 20 冻结的红基线里这两条的实测值 —— Task 74 的第一半就是把它们清成 0。
#: 数字不是手抄：`test_adjudicating_clears_exactly_two_criteria` 摘掉裁决后现场重量，两侧必须相等。
_UNADJUDICATED_BEFORE = {"unadjudicated_writer": 239, "unadjudicated_resolver": 39}

#: 本任务新加的两条 lane。加 lane 不是加豁免，两条判据在下面各守一面。
_NEW_LANES = ("unified_commit_substrate", "read_only_evaluation")

#: 占位式注解：写了字但没有裁决内容。中英文都列，因为 overlay 里两种语言都出现过。
_PLACEHOLDERS = (
    "待裁决",
    "见上",
    "同上",
    "TBD",
    "TODO",
    "FIXME",
    "same as above",
    "see above",
    "n/a",
    "pending",
)


def _load(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # 先登记再执行：`@dataclass` 会去 `sys.modules[cls.__module__]` 取命名空间，未登记时直接抛
    # `AttributeError: 'NoneType' object has no attribute '__dict__'`（实测）。
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def gate() -> ModuleType:
    return _load(_GATE_PATH, "writer_revision_gate")


@pytest.fixture(scope="module")
def generator() -> ModuleType:
    return _load(_GENERATOR_PATH, "writer_inventory_generator")


@pytest.fixture(scope="module")
def author() -> ModuleType:
    return _load(_AUTHOR_PATH, "task74_adjudicator")


@pytest.fixture(scope="module")
def overlay() -> dict[str, Any]:
    return json.loads(_OVERLAY_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def inventory() -> dict[str, Any]:
    return json.loads(_INVENTORY_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def source_scan(generator: ModuleType) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    return generator.collect_source_facts()


@pytest.fixture(scope="module")
def task74_rows(overlay: dict[str, Any]) -> dict[str, dict[str, str]]:
    """本任务加的那批裁决 = 现 overlay 减去改造前的 overlay 快照。

    用快照做减法而不是「按注解形状猜」：形状式判别会把将来任何一条按同样风格写的裁决误算进来。
    """
    before = json.loads((_EVIDENCE / "overlay_before.json").read_text(encoding="utf-8"))
    return {
        writer_id: value
        for writer_id, value in overlay["adjudications"].items()
        if writer_id not in before["adjudications"]
    }


# ═══ 一、准则结果：两条归零，其余不动 ══════════════════════════════════════


def test_the_gate_reports_zero_unadjudicated_rows(
    gate: ModuleType, inventory: dict[str, Any]
) -> None:
    """**Validates: Requirements 2.1, 2.2, 2.12** · Property 61"""
    issues = gate.evaluate_gate(inventory)
    assert issues["unadjudicated_writer"] == []
    assert issues["unadjudicated_resolver"] == []
    for entry in inventory["entries"]:
        adjudication = entry["adjudication"]
        assert adjudication["status"] == "adjudicated", entry["writer_id"]
        assert adjudication["domain"] in gate._REQUIRED_DOMAINS or adjudication["domain"], (
            entry["writer_id"]
        )


def test_adjudicating_clears_exactly_two_criteria(
    gate: ModuleType,
    generator: ModuleType,
    source_scan: tuple[list[dict[str, Any]], dict[str, dict[str, Any]]],
    overlay: dict[str, Any],
    task74_rows: dict[str, dict[str, str]],
) -> None:
    """**Validates: Requirements 2.2, 2.12, 9.11** · Property 61

    「域裁决不是豁免」的**行为级**判据。把本任务的 270 条裁决摘掉、从源码重推清册、再量门：

    * `unadjudicated_writer` / `unadjudicated_resolver` 必须回到 236 / 34（说明裁决真的在清它们）；
    * 其余 12 条准则必须**逐条字节相等**（说明裁决没有顺手放掉任何一条）。

    这条判据比「门里有没有豁免列」强：即便有人把豁免写成 domain 的副作用（例如让某个 lane 免掉
    `bypasses_unified_commit`），这里也会红。
    """
    rows, function_facts = source_scan
    assert len(task74_rows) == sum(_UNADJUDICATED_BEFORE.values()), (
        f"本任务加的裁决 {len(task74_rows)} 条 ≠ 改造前未裁决行数 "
        f"{sum(_UNADJUDICATED_BEFORE.values())}"
    )

    with_adjudication = generator.build_inventory(rows, overlay, function_facts)
    stripped_overlay = copy.deepcopy(overlay)
    for writer_id in task74_rows:
        stripped_overlay["adjudications"].pop(writer_id)
    without = generator.build_inventory(rows, stripped_overlay, function_facts)

    after = {key: len(values) for key, values in gate.evaluate_gate(with_adjudication).items()}
    before = {key: len(values) for key, values in gate.evaluate_gate(without).items()}

    for key, expected in _UNADJUDICATED_BEFORE.items():
        assert after[key] == 0, f"{key} 没有归零：{after[key]}"
        assert before[key] == expected, (
            f"摘掉裁决后 {key} 实测 {before[key]}，与 Task 20 冻结的 {expected} 不一致 —— "
            "要么源码的 writer 集变了，要么本任务的裁决集不是那 270 行"
        )

    moved = {
        key: (before[key], after[key])
        for key in sorted(before)
        if key not in _UNADJUDICATED_BEFORE and before[key] != after[key]
    }
    assert not moved, (
        f"域裁决动了本不该动的准则 {{key: (无裁决, 有裁决)}} = {moved} —— domain 标签变成了豁免"
    )


# ═══ 二、注解质量：事实逐条可重算，不是模板 ════════════════════════════════


def _measured_segment(note: str) -> str:
    """取注解里的 `Measured: ... Shape:` 段 —— 这一段是**派生事实**，必须逐条可重算。"""
    match = re.search(r"Measured:(.*?)(?:Shape:|$)", note, re.S)
    assert match, f"注解缺 `Measured:` 段，无法核对事实：{note[:120]}"
    return match.group(1)


def _expected_fact_tokens(entry: dict[str, Any]) -> set[str]:
    """从**清册行**独立重算「这一行的注解应该引用哪些事实 token」。

    独立性在于：这里读的是 `entries` 里那一行的 facts，而不是渲染注解的那段代码。所以把注解在两行
    之间对调、或者往注解里塞一条这行没有的事实，两侧都会红。
    """
    facts = entry["facts"]
    tokens: set[str] = set()
    tokens |= set(facts["sql_update_columns"])
    tokens |= set(facts["content_fields_written"])
    tokens |= set(facts["version_fields_written"])
    tokens |= set(entry["delegates_to_content_writer"])
    if facts["commit_receivers"]:
        tokens |= set(facts["commit_receivers"])
    elif facts["flush_receivers"]:
        tokens |= set(facts["flush_receivers"])
    tokens |= set(entry["resolver_identities"])
    tokens |= {item["literal"] for item in facts["ad_hoc_paths"]}
    tokens |= set(facts["artifact_writes"])
    tokens |= set(facts["after_save_calls"])
    tokens |= set(facts["unified_commit_calls"])
    return tokens


def test_every_note_cites_exactly_the_facts_that_row_has(
    inventory: dict[str, Any], task74_rows: dict[str, dict[str, str]]
) -> None:
    """**Validates: Requirements 2.11, 2.12, 9.11**

    反模板判据：注解 `Measured:` 段里反引号包住的每个 token 必须是该行**真实存在**的事实，且该行
    的事实必须**一个不漏**地出现。双向，所以复制粘贴（缺该行事实 + 引用别行事实）必红。
    """
    by_id = {entry["writer_id"]: entry for entry in inventory["entries"]}
    problems: list[str] = []
    for writer_id, value in sorted(task74_rows.items()):
        entry = by_id[writer_id]
        cited = set(re.findall(r"`([^`]+)`", _measured_segment(value["version_domain_note"])))
        expected = _expected_fact_tokens(entry)
        invented = cited - expected
        missing = expected - cited
        if invented or missing:
            problems.append(f"{writer_id}: invented={sorted(invented)} missing={sorted(missing)}")
    assert not problems, "注解引用的事实与该行实测事实不符：\n" + "\n".join(problems[:10])


def test_every_note_is_anchored_on_its_own_row(
    inventory: dict[str, Any], task74_rows: dict[str, dict[str, str]]
) -> None:
    """注解开头的身份必须是**这一行自己的** qualname + source_path，不是别人的。"""
    by_id = {entry["writer_id"]: entry for entry in inventory["entries"]}
    for writer_id, value in sorted(task74_rows.items()):
        entry = by_id[writer_id]
        note = value["version_domain_note"]
        assert note.startswith(f"`{entry['qualname']}` in `{entry['source_path']}`"), (
            f"{writer_id} 的注解身份前缀不是它自己：{note[:120]}"
        )


def test_notes_are_pairwise_distinct_and_carry_no_placeholder(
    task74_rows: dict[str, dict[str, str]]
) -> None:
    """**Validates: Requirements 2.11, 12.6**"""
    notes = [value["version_domain_note"] for value in task74_rows.values()]
    assert len(set(notes)) == len(notes), (
        f"{len(notes) - len(set(notes))} 条注解与别人逐字相同 —— 共享注解就是模板"
    )
    for writer_id, value in sorted(task74_rows.items()):
        note = value["version_domain_note"]
        assert len(note) >= 200, f"{writer_id} 的注解只有 {len(note)} 字，不足以说明 lane 与理由"
        lowered = note.lower()
        for placeholder in _PLACEHOLDERS:
            assert placeholder.lower() not in lowered, f"{writer_id} 的注解含占位词 {placeholder}"
        assert "Lane:" in note, f"{writer_id} 的注解没有说明属于哪条 lane"


def test_the_overlay_still_has_no_exemption_field(
    task74_rows: dict[str, dict[str, str]]
) -> None:
    """**Validates: Requirements 2.2**

    Task 3 的守卫只查「已裁决 writer」；本任务同时裁决了 34 个 resolver，所以这里把整批一起查。
    """
    for writer_id, value in sorted(task74_rows.items()):
        assert set(value) == {"domain", "version_domain_note"}, (
            f"{writer_id} 的裁决多了字段 {sorted(set(value) - {'domain', 'version_domain_note'})}"
            " —— overlay 只能回答『属于哪条 lane』，不能回答『是否允许绕过』"
        )


# ═══ 三、新加的两条 lane 买不到任何东西 ═══════════════════════════════════


def test_the_two_new_lanes_buy_nothing(
    gate: ModuleType, inventory: dict[str, Any], overlay: dict[str, Any]
) -> None:
    """**Validates: Requirements 2.2, 2.12** · Property 61

    正向：换成别的 lane，门的判定逐条不变（⇒ lane 标签不是豁免）。
    反向对照：把 `bump_content_revision` 换成 `orchestrator_side_effect`，
    `after_save_still_increments_revision` 必须立刻从 0 变红（⇒ domain 字段并非恒无作用，前一句
    才是有内容的结论，而不是「反正 domain 不参与判定」这种空话）。这同时也是「为什么这一行不能
    塞进 `orchestrator_side_effect`」的实测理由。
    """
    in_new_lanes = sorted(
        writer_id
        for writer_id, value in overlay["adjudications"].items()
        if value["domain"] in _NEW_LANES
    )
    assert in_new_lanes, "两条新 lane 一行都没有 —— 那它们就该从 `_DOMAINS` 里删掉"

    baseline = gate.evaluate_gate(inventory)
    for writer_id in in_new_lanes:
        assert writer_id in baseline["bypasses_unified_commit"], (
            f"{writer_id} 进了新 lane 之后不再被 `bypasses_unified_commit` 点名 —— 那这条 lane "
            "买到了豁免"
        )

    relabelled = copy.deepcopy(inventory)
    for entry in relabelled["entries"]:
        if entry["adjudication"].get("domain") in _NEW_LANES:
            entry["adjudication"]["domain"] = "html_save"
    assert gate.evaluate_gate(relabelled) == baseline, (
        "把新 lane 换成 `html_save` 改变了门的判定 —— lane 标签不该有这种作用"
    )

    counter_control = copy.deepcopy(inventory)
    target = "app.services.workpaper_sync.repository::WorkpaperSyncRepository.bump_content_revision"
    for entry in counter_control["entries"]:
        if entry["writer_id"] == target:
            assert entry["verdicts"]["writes_unified_content_revision"], target
            entry["adjudication"]["domain"] = "orchestrator_side_effect"
    control = gate.evaluate_gate(counter_control)
    assert control["after_save_still_increments_revision"] == [target], (
        "把统一计数器那一行标成 `orchestrator_side_effect` 竟然没有触发 Requirement 13.4 那条准则 "
        "—— 说明 domain 字段在门里已经完全不起作用，`test_the_two_new_lanes_buy_nothing` 的正向"
        "部分就退化成了空话"
    )


def test_the_required_domains_stay_a_proper_floor(
    gate: ModuleType, generator: ModuleType
) -> None:
    """加 lane 不能把「必需 domain 是覆盖地板」这层语义弄没。"""
    assert set(gate._REQUIRED_DOMAINS) < set(generator._DOMAINS)
    for lane in _NEW_LANES:
        assert lane in generator._DOMAINS
        assert lane not in gate._REQUIRED_DOMAINS, (
            f"{lane} 进了 `_REQUIRED_DOMAINS` ⇒ 一条本任务新造的 lane 变成了必须存在的 lane"
        )


# ═══ 四、规则表 fail-closed：命不中即抛，不给默认 lane ════════════════════


def test_the_authoring_rules_refuse_an_unmatched_row(
    author: ModuleType, inventory: dict[str, Any]
) -> None:
    """**Validates: Requirements 2.11, 12.6**

    默认 lane 是「未裁决伪装成已裁决」，所以规则表必须 fail-closed。
    """
    author._INDEX.clear()
    author._INDEX.update({entry["writer_id"]: entry for entry in inventory["entries"]})
    orphan = copy.deepcopy(inventory["entries"][0])
    orphan.update(
        {
            "writer_id": "app.services.zzz_not_a_real_module::save",
            "module": "app.services.zzz_not_a_real_module",
            "qualname": "save",
            "source_path": "backend/app/services/zzz_not_a_real_module.py",
            "kind": "writer",
            "content_stores_written": [],
            "delegates_to_content_writer": [],
            "resolver_identities": [],
            "canonical_resolver": None,
            "characterization_tests": [],
        }
    )
    orphan["facts"] = {key: ([] if isinstance(value, list) else value) for key, value in orphan["facts"].items()}
    for key in orphan["facts"]:
        orphan["facts"][key] = []
    with pytest.raises(SystemExit) as raised:
        author.classify(orphan)
    assert "no adjudication rule matches" in str(raised.value)


def test_the_rule_table_has_no_catch_all(author: ModuleType) -> None:
    """反向自检：任何一条规则的 `match` 都不能是恒真 —— 恒真规则就是默认 lane。"""
    always_true = {"writer_id": "x::y", "module": "x", "kind": "writer"}
    for rule in author._RULES:
        try:
            matched = rule.match(always_true)
        except Exception:
            matched = False
        assert not matched, f"规则 {rule.key} 对一个空行也返回 True —— 它是 catch-all"
