# -*- coding: utf-8 -*-
r"""Task 64 守卫变异检验 —— 证明裁决记录的守卫不是重言式。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 6 Task 64
守卫: backend/tests/workpaper_sync/test_task64_dedicated_word_chain.py

用法（仓库根，**禁止后台执行** —— 孤儿进程与前台同时变异同一文件会 RestoreFailed）::

    .\.venv\Scripts\python.exe backend/scripts/diagnose/mutate_task64_dedicated_word_chain_guards.py --list
    .\.venv\Scripts\python.exe backend/scripts/diagnose/mutate_task64_dedicated_word_chain_guards.py --check-anchors
    .\.venv\Scripts\python.exe backend/scripts/diagnose/mutate_task64_dedicated_word_chain_guards.py --run all

═══ 三类变异，缺一类判据就不完整 ═══

* **数据侧**（M01~M09）：改产物 JSON。只能证明「守卫读了产物」；
* **真源码侧**（M10~M15）：改生产解析器 / 前端宿主 / registry 常量。这类还打红才证明
  守卫是**现读 impl**，而不是把产物里的数字当基线抄一遍；
* **反向变异**（M16~M18）：把记录在案的「缺陷」**修好**也必须打红 —— 每条 BP 都有一条
  `xfail(strict=True)` 解除探测，缺陷真修好时它 XPASS ⇒ pytest 判 failed ⇒ 强制回来
  更新裁决与 BP 表，不给「代码改好了但记录还挂着 open」留缝。

═══ 运行纪律（本 spec 反复踩过）═══

1. 跑之前把并发遗留的 `backend/scripts/**/*.mutbak` 移到 `%TEMP%`，跑完原位放回并核
   sha256；**绝不** `--restore`（那会把并发方的备份一起还原掉）。
2. 锚点禁含 `\n`（工作树 CRLF，跨行锚点必 ANCHOR-MISS）—— 声明期校验会拦。
3. JSON 数组末元素禁用 `delete`（尾逗号让 `json.loads` 抛 ⇒ 判 ERROR）；一律 `replace`。
4. 每条变异都带 `scope_check`：解析变异后的字节并断言改动确实落在目标结构里。
   四态判定识别不出「锚点落在被测判据作用域之外」，那种情况会被误判成 GREEN。
5. 结果按 RED / GREEN / ANCHOR-MISS / WRONG-TEST 四态读，不看退出码。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

_THIS = Path(__file__).resolve()
_REPO = _THIS.parents[3]
if str(_THIS.parents[1]) not in sys.path:  # pragma: no cover - import 自举
    sys.path.insert(0, str(_THIS.parents[1]))

from _mutation_kit import Mutation, run_cli  # noqa: E402

RECORD = "backend/data/workpaper_sync_a16_a17_word_chain_adjudication.json"
PARSER = "backend/app/services/wp_docx_template_parser.py"
REGISTRY = "backend/app/services/workpaper_sync/adapters/registry.py"
A17_VUE = "audit-platform/frontend/src/components/workpaper/GtA17Bundle.vue"
WORD_EDITOR_VUE = "audit-platform/frontend/src/components/workpaper/WorkpaperWordEditor.vue"

GUARD_FILES = {
    "test_task64_dedicated_word_chain.py": (
        "Task 64 裁决记录守卫：分母现算、HTML 投影字段面、不可达三要素、"
        "跨 entry 隔离、未越 Task 61 门、Property 不过度宣称、BP 登记完整性"
    ),
}


# ════════════════════════════════════════════════════════════════════════════
# scope_check 助手 —— 解析变异后的字节，断言改动落在目标结构里
# ════════════════════════════════════════════════════════════════════════════
def _record_json(data: bytes) -> dict:
    return json.loads(data.decode("utf-8"))


def _counter_is(name: str, value: object):
    def check(data: bytes) -> bool:
        try:
            return _record_json(data)["counters"][name] == value
        except (ValueError, KeyError):
            return False

    return check


def _verdict_multiset_collapsed(data: bytes) -> bool:
    """entries 的 verdict 去重后少于 4 种 ⇒ 变异确实把两条裁决改成同一个。"""
    try:
        verdicts = [e["verdict"] for e in _record_json(data)["entries"]]
    except (ValueError, KeyError):
        return False
    return len(verdicts) == 4 and len(set(verdicts)) < 4


def _property_claim_is(prop: str, prefix: str):
    def check(data: bytes) -> bool:
        try:
            return str(
                _record_json(data)["properties_verified"][prop]["claim"]
            ).startswith(prefix)
        except (ValueError, KeyError):
            return False

    return check


def _property47_denominator_is(value: int):
    def check(data: bytes) -> bool:
        try:
            return (
                _record_json(data)["properties_verified"]["Property 47"]["denominator"]
                == value
            )
        except (ValueError, KeyError):
            return False

    return check


def _isolation_field_is(name: str, value: object):
    def check(data: bytes) -> bool:
        try:
            return _record_json(data)["cross_entry_isolation"][name] == value
        except (ValueError, KeyError):
            return False

    return check


def _gate_field_is(name: str, value: object):
    def check(data: bytes) -> bool:
        try:
            return _record_json(data)["task61_gate_compliance"][name] == value
        except (ValueError, KeyError):
            return False

    return check


def _registry_fact_is(name: str, value: object):
    def check(data: bytes) -> bool:
        try:
            return _record_json(data)["registry_facts"][name] == value
        except (ValueError, KeyError):
            return False

    return check


def _bp_ids_lost(bp_id: str):
    def check(data: bytes) -> bool:
        try:
            ids = {bp["id"] for bp in _record_json(data)["blocking_preconditions"]}
        except (ValueError, KeyError):
            return False
        return bp_id not in ids

    return check


def _digests_section_renamed(data: bytes) -> bool:
    """`denominator` 下不再有 `popup_source_digests`，但改名后的节仍在。"""
    try:
        denom = _record_json(data)["denominator"]
    except (ValueError, KeyError):
        return False
    return (
        "popup_source_digests" not in denom
        and "popup_source_digests_RENAMED" in denom
    )


def _text_contains(needle: str):
    def check(data: bytes) -> bool:
        return needle in data.decode("utf-8")

    return check


def _text_lacks(needle: str):
    def check(data: bytes) -> bool:
        return needle not in data.decode("utf-8")

    return check


def _legacy_patterns_matches_cjk_company(data: bytes) -> bool:
    """变异后的解析器常量表里必须出现能命中 A16 正文的宽泛模式。"""
    text = data.decode("utf-8")
    return '(r"公司", "placeholder_generic"' in text


def _a17_tabs_use_word_kind(data: bytes) -> bool:
    text = data.decode("utf-8")
    return "kind: 'word'" in text and "kind: 'closing-meeting'" not in text


# ════════════════════════════════════════════════════════════════════════════
# 变异声明
# ════════════════════════════════════════════════════════════════════════════
MUTATIONS: list[Mutation] = [
    # ── 数据侧：证明守卫读了产物 ──────────────────────────────────────────
    Mutation(
        id="M01",
        side="be",
        path=RECORD,
        kind="replace",
        anchor='    "templates_with_dollar_tokens": 0,',
        new='    "templates_with_dollar_tokens": 1,',
        want="test_no_declarative_dollar_token_exists_anywhere",
        why=(
            "「15 份模板零 `${}` 声明式 token」是裁决的事实基础之一。把计数改成 1 "
            "必须打红，否则这条事实没人把守。"
        ),
        tags=("data", "counters"),
        scope_check=_counter_is("templates_with_dollar_tokens", 1),
    ),
    Mutation(
        id="M02",
        side="be",
        path=RECORD,
        kind="replace",
        anchor='    "templates_with_tables": 15,',
        new='    "templates_with_tables": 14,',
        want="test_every_template_has_tables",
        why=(
            "15/15 有 `w:tbl` 钉死「WORD_ONLY_COVERAGE_REQUIRED 不能照抄 F2（那边 "
            "w:tbl=0）」。改成 14 必须打红。"
        ),
        tags=("data", "counters"),
        scope_check=_counter_is("templates_with_tables", 14),
    ),
    Mutation(
        id="M03",
        side="be",
        path=RECORD,
        kind="replace",
        anchor='    "production_contract_dir_untouched": true,',
        new='    "production_contract_dir_untouched": false,',
        want="test_no_reusable_artifact_was_produced",
        why="「本任务没往生产契约目录放东西」被改成 false 必须打红。",
        tags=("data", "isolation"),
        scope_check=_isolation_field_is("production_contract_dir_untouched", False),
    ),
    Mutation(
        id="M04",
        side="be",
        path=RECORD,
        kind="replace",
        anchor='    "delivered_contract_rows_added": 0,',
        new='    "delivered_contract_rows_added": 1,',
        want="test_no_reusable_artifact_was_produced",
        why="本任务裁决为不发契约；登记「加了 1 行」必须打红。",
        tags=("data", "isolation"),
        scope_check=_isolation_field_is("delivered_contract_rows_added", 1),
    ),
    Mutation(
        id="M05",
        side="be",
        path=RECORD,
        kind="replace",
        anchor='    "forbidden_paths_still_absent": true,',
        new='    "forbidden_paths_still_absent": false,',
        want="test_word_adapter_module_still_absent",
        why="Task 61 门的合规声明被改成 false 必须打红（不能只写在记录里没人验）。",
        tags=("data", "gate"),
        scope_check=_gate_field_is("forbidden_paths_still_absent", False),
    ),
    Mutation(
        id="M06",
        side="be",
        path=RECORD,
        kind="replace",
        anchor='    "task64_added_contract_rows": 0,',
        new='    "task64_added_contract_rows": 1,',
        want="test_contract_registry_row_count_unchanged_by_this_task",
        why="「本任务没往交付登记表加行」被改成 1 必须打红。",
        tags=("data", "gate"),
        scope_check=_registry_fact_is("task64_added_contract_rows", 1),
    ),
    Mutation(
        id="M07",
        side="be",
        path=RECORD,
        kind="replace",
        anchor='      "claim": "NOT_CLAIMED_NO_TAGGED_SDT_ENTRY_IN_THIS_LANE",',
        new='      "claim": "PASS",',
        want="test_zero_denominator_properties_are_not_claimed",
        why=(
            "Property 30 分母为 0，宣称 PASS 就是空集恒真的假绿。必须打红。"
        ),
        tags=("data", "properties"),
        scope_check=_property_claim_is("Property 30", "PASS"),
    ),
    Mutation(
        id="M08",
        side="be",
        path=RECORD,
        kind="replace",
        anchor='      "verdict": "unreachable_stub",',
        new='      "verdict": "opaque_ooxml_authority",',
        want="test_the_four_verdicts_are_actually_different",
        why=(
            "四条 entry 必须有四种不同裁决（否则是一刀切而非逐 entry 裁决）。"
            "把 A17 bundle 的 unreachable 改成与 A16 相同的 opaque 必须打红。"
            "注意 `unreachable_stub` 在 `unreachable_findings` 里还有一处不带尾逗号，"
            "本锚点带尾逗号 ⇒ 只命中 entries 里那条。"
        ),
        tags=("data", "verdict"),
        scope_check=_verdict_multiset_collapsed,
    ),
    Mutation(
        id="M09",
        side="be",
        path=RECORD,
        kind="replace",
        anchor='      "denominator": 2,',
        new='      "denominator": 0,',
        want="test_property_47_denominator_is_not_zero",
        why=(
            "BP-15 的教训：承载者存在且形态相反时分母不是 0 而是反例。把 Property 47 "
            "的分母改成 0 等于把「没有承载者所以通过」这种假绿锁死，必须打红。"
        ),
        tags=("data", "properties"),
        scope_check=_property47_denominator_is(0),
    ),
    # ── 数据侧：BP 表完整性 ───────────────────────────────────────────────
    Mutation(
        id="M10",
        side="be",
        path=RECORD,
        kind="replace",
        anchor='      "id": "BP-16",',
        new='      "id": "BP-99",',
        want="test_all_bps_are_registered_and_open",
        wants=("test_every_entry_blocked_by_points_at_a_registered_bp",),
        why=(
            "BP-16 是 A16 裁 opaque 的阻断项，且被 entry 的 blocked_by 引用。改掉编号后"
            "「BP 集合等值」与「entry 指向已登记 BP」两条都该打红。"
        ),
        tags=("data", "bp"),
        scope_check=_bp_ids_lost("BP-16"),
    ),
    # ── 真源码侧：证明守卫现读 impl，而不是抄产物数字 ──────────────────────
    Mutation(
        id="M11",
        side="be",
        path=PARSER,
        kind="replace",
        anchor='    (r"××", "placeholder_generic", "待填内容"),',
        new='    (r"公司", "placeholder_generic", "待填内容"),',
        want="test_a16_chain_has_zero_html_field_surface",
        why=(
            "把 legacy 模式放宽到能命中 A16 正文里的「公司」⇒ 生产解析器对 A16 会解析出"
            "非 0 个 placeholder。守卫在这里**重新跑一次** `parse_template` 并与产物对数，"
            "所以这条必须打红；只抄产物数字的守卫会 GREEN。"
        ),
        tags=("source", "parser"),
        scope_check=_legacy_patterns_matches_cjk_company,
    ),
    Mutation(
        id="M12",
        side="be",
        path=A17_VUE,
        kind="replace",
        anchor=(
            "  { id: 'A17-6', label: '总结会会议纪要', kind: 'closing-meeting', "
            "wpCode: 'A17-6', tracked: true },"
        ),
        new=(
            "  { id: 'A17-6', label: '总结会会议纪要', kind: 'word', "
            "wpCode: 'A17-6', tracked: true },"
        ),
        want="test_a17_word_mount_is_gated_by_a_kind_never_used",
        wants=("test_bp18_a17_word_kind_is_now_used",),
        why=(
            "让静态 TABS 真的用上 `kind: 'word'` ⇒ Word 挂载点变可达，unreachable 裁决"
            "的第三要素失效。同时 BP-18 的 xfail(strict) 解除探测会 XPASS ⇒ 也判 failed。"
            "两条都该红：一条护裁决，一条护「缺陷修好后记录必须同步」。"
        ),
        tags=("source", "frontend", "reverse"),
        scope_check=_a17_tabs_use_word_kind,
    ),
    Mutation(
        id="M13",
        side="be",
        path=REGISTRY,
        kind="replace",
        anchor='            "app/services/workpaper_sync/adapters/word.py",',
        new='            "app/services/workpaper_sync/adapters/word_DISABLED.py",',
        want="test_word_adapter_module_still_absent",
        why=(
            "把 pending adapter 的被禁路径改成一个不存在的名字，等于把 Task 61 的门"
            "悄悄挪开：Word adapter 换个文件名就能落地。"
            "🔴 本条首轮实测判 **WRONG-TEST** 并因此抓出一个真实的守卫缺陷 —— 原守卫只"
            "断言「清单非空 + 逐条不存在」，而改名后两条**仍然满足**（改名后的路径当然也"
            "不存在）⇒ 门被挪开却全绿。守卫已补一条「清单必须**包含**真实的 "
            "`app/services/workpaper_sync/adapters/word.py`」，本条才转 RED。"
        ),
        tags=("source", "registry", "gate"),
        scope_check=_text_lacks('"app/services/workpaper_sync/adapters/word.py",'),
    ),
    Mutation(
        id="M14",
        side="be",
        path=REGISTRY,
        kind="replace",
        anchor='        "delivered_by_task": "40",',
        new='        "delivered_by_task": "64",',
        want="test_contract_registry_row_count_unchanged_by_this_task",
        why=(
            "把一条既有契约登记的归属改成 Task 64 ⇒ 「本任务名下 0 行」被打破。"
            "判据刻意用「本任务名下 0 行」而不是「总数等于 4」——后者会被并发方"
            "（Task 62/63）加行时误判成本任务打红。"
        ),
        tags=("source", "registry", "gate"),
        scope_check=_text_contains('"delivered_by_task": "64",'),
    ),
    # ── 反向变异：把记录在案的缺陷修好，也必须打红 ────────────────────────
    Mutation(
        id="M15",
        side="be",
        path=PARSER,
        kind="replace",
        anchor="_LEGACY_PATTERNS: list[tuple[str, str, str]] = [",
        new="_LEGACY_PATTERNS: list[tuple[str, str, str]] = [] and [",
        want="test_bp17_production_locator_no_longer_uses_cjk_regex",
        why=(
            "反向变异：把 legacy 中文正则表清空 = BP-17 的缺陷被修好。此时该 BP 的 "
            "xfail(strict) 解除探测 XPASS ⇒ pytest 判 failed ⇒ 强制回来把 BP-17 "
            "标 resolved 并重算裁决。没有这条，代码改好后记录会永远挂着 open。"
        ),
        tags=("source", "parser", "reverse"),
        scope_check=_text_contains("= [] and ["),
    ),
    Mutation(
        id="M16",
        side="be",
        path=WORD_EDITOR_VUE,
        kind="replace",
        anchor="const isA16Mode = computed(() => wpCode.value === 'A16')",
        new=(
            "const isA16Mode = computed(() => wpCode.value === 'A16')\n"
            "const descriptor = null\ndefineExpose({ descriptor })"
        ),
        want="test_property_47_denominator_is_not_zero",
        wants=("test_bp19_word_hosts_become_descriptor_consumers",),
        why=(
            "反向变异：给 Word 宿主加上 `defineExpose` 与 `descriptor` = BP-19 的缺陷"
            "被修好（形态上）。Property 47 的反例判据与 BP-19 的解除探测都该打红，"
            "提醒重新验「它是不是真的 descriptor consumer」而不是静静变绿。"
        ),
        tags=("source", "frontend", "reverse"),
        scope_check=_text_contains("defineExpose({ descriptor })"),
    ),
    # ── 数据侧：popup 观测值口径 ──────────────────────────────────────────
    Mutation(
        id="M17",
        side="be",
        path=RECORD,
        kind="replace",
        anchor='    "popup_source_digests": {',
        new='    "popup_source_digests_RENAMED": {',
        want="test_popup_total_is_recorded_as_observation_with_digests",
        why=(
            "把 popup 源文件 digest 整节改名 ⇒ 守卫取不到 digest。这条护住「popup 总数是"
            "带 digest 的观测值」这个口径：没有 digest 锚，并发方改 B/S 文件后就无法"
            "区分「上游正常推进」与「本任务数字错了」。"
            "🔴 锚点刻意用**节名**而不是某个 digest 值那一行 —— digest 值会随并发方改动"
            "而变，把它写进变异声明等于让脚本自带一个必然过期的字面量。"
        ),
        tags=("data", "popup"),
        scope_check=_digests_section_renamed,
    ),
]


if __name__ == "__main__":
    raise SystemExit(
        run_cli(
            mutations=MUTATIONS,
            guard_files=GUARD_FILES,
            repo=_REPO,
            description="Task 64 A16/A17 Word 链裁决记录守卫变异检验",
            backend_args=[
                "backend/tests/workpaper_sync/test_task64_dedicated_word_chain.py",
                "-q",
                "-rf",
                "--no-header",
            ],
            baseline_backend_passed=28,
        )
    )
