# -*- coding: utf-8 -*-
r"""Task 51 守卫变异检验 —— I 循环 Excel 独立 entry 迁移。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 5 Task 51

用平台共享件 `backend/scripts/_mutation_kit`（`test_mutation_kit_adoption.py` 对新脚本强制
采纳：共享件的 `run_cli` 把 `guard_files`（覆盖面分母）做成签名层面必填，把「锚点含换行」
「new == anchor」「id 重复」「want 定位不到」全部拦在声明期）。

═══ 本脚本的四条硬约束 ═══

1. **每条变异都带 `scope_check`**。四态判定式「新增失败集合是否为空」识别不出「锚点落在被测
   判据的作用域之外」—— 改到了别处会被判 GREEN（守卫缺陷），而真相是脚本缺陷。数据文件的
   回调解析 JSON 后断言目标字段真的变成了期望值；源码文件的回调断言改动确实落在那段文本上。

2. **重复形态字段用 `scope` + `offset` 相对定位，绝不用绝对行号**。slice 是逐 entry 同构的
   生成物：`"capability": null,` 出现 6 次、`"write_carrier": "host_inline",` 5 次、
   `"verification_state": "UNVERIFIABLE",` 6 次、`"in_runtime_index": true,` 6 次。绝对行号
   一改文件就失效。`scope` 取该 entry 唯一的 `entry_id` 行（或 CD-N 唯一的 `"id"` 行），
   `offset` 由 `tmp_task51_anchor_probe*.py`（一次性诊断，跑完即删）实算；行内已唯一（dup=1）
   的锚点则直接用整行，不做多余消歧。

3. **capability 变异按「裁决错法」而不是「逐 entry 复制」枚举**。本 slice 6 条 entry 的
   capability 全是同一形态（null + 三字段齐备的待裁决态），逐条各写一次是 6 份同信息量的变异
   （每条要跑一遍全量守卫 ≈ 40s）。这里按**可被区分的错法**枚举：填 bidirectional / 填
   single_onlyoffice / 自造能力态 / 三个待裁决必填字段各破坏一次 / blockers 指向不存在的前置 /
   adapter_id 非 null / verdict 写成 unresolved（AP-3）/ manifest_mirror 与 slice 相等
   （BP-9 前提消失），并分布在 6 条不同 entry 上，从而同时把 6 组不同的 offset 走通。

4. **Task 51 正文点名的「source_ref 三边锁」必须三条边各自变异**。这是本任务的核心判据，
   单验一边等于没验：
   * **第①边（声明）** —— 改 `cells` 区间（M21）、改 `source_read_mode`（M22）；
   * **第②边（源真读）** —— 改 slice 冻结的 `expected_source_labels`（M16），
     以及**真改源模板** 不做（模板是权威字节，不允许变异）⇒ 用「改声明基线」等价覆盖；
   * **第③边（impl 现读）** —— 既改 slice 冻结的 `impl_labels`（M17），
     也**真改前端常量**（M25~M28 四条源码变异），后者才能证明「impl 侧是现读的而不是抄的」；
   * **合成边（verdict）** —— 把 MISMATCH / PREFIX_MATCH 篡改成 MATCH（M18/M19/M20）。
   另外 M26 是**反向**变异：把 BP-7 的缺陷「修一半」（`采矿权` → `矿产权`）而不改登记 ——
   声明与实现的差集变了，判据必须同样打红。只验一个方向的穷举判据是半个判据。

用法（仓库根；本仓库 PATH 上的 `python` 指向坏掉的 `.venv_depprobe`，必须用显式解释器）::

    .\.venv\Scripts\python.exe backend/scripts/diagnose/mutate_task51_i_cycle_migration_guards.py --list
    .\.venv\Scripts\python.exe backend/scripts/diagnose/mutate_task51_i_cycle_migration_guards.py --check-anchors
    .\.venv\Scripts\python.exe backend/scripts/diagnose/mutate_task51_i_cycle_migration_guards.py --run M01,M02,M03

🔴 **禁止后台执行**：外层 shell 被杀会让 python 变成孤儿进程，与前台运行同时变异同一文件 ⇒
`RestoreFailed` rc=5。分批跑用 `--run M01,M02,...`（子集运行不做覆盖面结论，见 kit 的
`CoverageTally.report`）。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/scripts

from _mutation_kit import Mutation, run_cli  # noqa: E402

REPO = Path(__file__).resolve().parents[3]

# ── 被变异的对象 ───────────────────────────────────────────────────────────
SLICE = "backend/data/workpaper_sync_i_cycle_manifest_slice.json"
PLAN = "backend/data/workpaper_sync_i_cycle_deletion_plan.json"
FE = "audit-platform/frontend/src"
WP = f"{FE}/components/workpaper"
COMP = f"{WP}/composables"
HOST_I1 = f"{WP}/GtI1IntangibleAssets.vue"
I1_SCOPE_TS = f"{COMP}/i1CategoryScope.ts"
I1_SOE_TS = f"{COMP}/i1SoeDisclosureModel.ts"
I5_DETAIL_TS = f"{COMP}/useI5Detail.ts"
I4_DETAIL_TS = f"{COMP}/useI4Detail.ts"
I6_DETAIL_TS = f"{COMP}/useI6Detail.ts"
I3_DISCLOSURE_TS = f"{COMP}/useI3Disclosure.ts"
I3_DUAL_TS = f"{COMP}/useI3DualMode.ts"

# ── 期望打红的守卫（文件::类::方法，与 pytest 的 short nodeid 同形）─────────
T51 = "test_task51_i_cycle_migration.py"
_SELF = f"{T51}::TestGuardSelfChecks"
_SCOPE = f"{T51}::TestSliceScopeIsRecomputable"
_ADJ = f"{T51}::TestAdjudicationLegality"
_HTML = f"{T51}::TestHtmlCounterpartIsSourceBacked"
_CLS = f"{T51}::TestClassificationRowModelDerivation"
_P22 = f"{T51}::TestProperty22StaticStructure"
_P23 = f"{T51}::TestProperty23RowIdentityStaticPrereq"
_ORPHAN = f"{T51}::TestOrphanComposablesAndPseudoConsumers"
_P20 = f"{T51}::TestProperty20And21NotClaimed"
_P28 = f"{T51}::TestProperty28DefinitionDriftFailClosed"
_P69 = f"{T51}::TestProperty69EvidenceAndCounters"
_P70 = f"{T51}::TestProperty70CrossEntryIsolation"
_AC14 = f"{T51}::TestAc14HonestModeVisibility"
_DEL = f"{T51}::TestDeletionPlanConsistency"
_PARA = f"{T51}::TestParadigmCompliance"

# ── 相对定位用的唯一 scope 锚 ──────────────────────────────────────────────
E_I1 = "xlsx/gt-i1-intangible-assets"
E_I2 = "xlsx/gt-i2-development-expenditure"
E_I3 = "xlsx/gt-i3-goodwill"
E_I4 = "xlsx/gt-i4-long-term-prepaid"
E_I5 = "xlsx/gt-i5-other-noncurrent-assets"
E_I6 = "xlsx/gt-i6-research-development-expense"


def S(entry_id: str) -> str:
    return '      "entry_id": "%s",' % entry_id


def CD(n: int) -> str:
    return '        "id": "CD-%d",' % n


#: 逐 entry 的字段 offset（相对 `entry_id` 行；由一次性诊断实算，非估计值）。
#: 之所以不是一个常量 —— 各 entry 的 blocked_by 条数与 html_counterpart 子结构不同宽。
OFF_CAPABILITY = 5          # 6 条 entry 一致
OFF_STAGE = 6
OFF_TARGET = 7
OFF_ADAPTER = {E_I1: 18, E_I2: 16, E_I3: 17, E_I4: 18, E_I5: 16, E_I6: 18}
OFF_VERDICT = {E_I1: 29, E_I2: 27, E_I3: 28, E_I4: 29, E_I5: 27, E_I6: 29}
OFF_WRITE_CARRIER = {E_I1: 33, E_I2: 31, E_I3: 32, E_I4: 33, E_I5: 31, E_I6: 33}
OFF_READ_CARRIER = {E_I1: 40, E_I2: 38, E_I3: 39, E_I4: 40, E_I5: 38, E_I6: 41}
OFF_PAYLOAD_MODE = {E_I1: 46, E_I2: 44, E_I3: 45, E_I4: 46, E_I5: 44, E_I6: 47}
OFF_ITEM_ID = {E_I1: 67, E_I2: 67, E_I3: 67, E_I4: 70, E_I5: 68, E_I6: 68}
OFF_IDENTITY_CELL = {E_I1: 75, E_I2: 75, E_I3: 75, E_I4: 78, E_I5: 76, E_I6: 76}
OFF_VERIF_STATE = 128       # I1 / I5 实测一致

# ═══════════════════════════════════════════════════════════════════════════
# 作用域自证回调（每条变异必带）
#
# 🔴 为什么每条都要带：共享件的四态判定只看「新增失败集合」，锚点若命中了同名的文档说明 /
# 注释 / 另一个结构，判定会报 GREEN（守卫缺陷），而真相是脚本缺陷。回调在变异写盘后立刻
# 解析 JSON（或读文本）并断言目标**真的**变成了期望值 —— 不成立即判 ANCHOR-MISS。
# ═══════════════════════════════════════════════════════════════════════════
def _json_at(expected, *path):
    """JSON 里 `path`（dict 键 / list 下标混用）指向的节点必须**恰好**等于期望值。"""

    def check(data: bytes) -> bool:
        node = json.loads(data.decode("utf-8"))
        for key in path:
            try:
                node = node[key]
            except (KeyError, IndexError, TypeError):
                return False
        return node == expected

    return check


def _entry_field(entry_id: str, *path):
    """slice / plan 里某 entry 的嵌套字段必须恰好等于期望值（`path` 末位是期望值）。

    按 `entry_id` 找而不是按下标 —— 下标会在 slice 增删 entry 时静默指向别人。
    """
    expected = path[-1]
    keys = path[:-1]

    def check(data: bytes) -> bool:
        payload = json.loads(data.decode("utf-8"))
        rows = payload.get("independent_entries") or payload.get("entries") or []
        for entry in rows:
            if entry.get("entry_id") != entry_id:
                continue
            node = entry
            for key in keys:
                try:
                    node = node[key]
                except (KeyError, IndexError, TypeError):
                    return False
            return node == expected
        return False

    return check


def _declaration_field(dec_id: str, *path):
    """classification_row_model_derivation 里某条 CD-N 的字段必须恰好等于期望值。

    按 `id` 找而不是按下标 —— 增删 declaration 时下标会静默指向别人。
    """
    expected = path[-1]
    keys = path[:-1]

    def check(data: bytes) -> bool:
        payload = json.loads(data.decode("utf-8"))
        for dec in payload["classification_row_model_derivation"]["declarations"]:
            if dec.get("id") != dec_id:
                continue
            node = dec
            for key in keys:
                try:
                    node = node[key]
                except (KeyError, IndexError, TypeError):
                    return False
            return node == expected
        return False

    return check


def _template_field(name: str, key: str, expected):
    """authoritative_templates.files 里某本工作簿的某个字段必须等于期望值。"""

    def check(data: bytes) -> bool:
        payload = json.loads(data.decode("utf-8"))
        for record in payload["authoritative_templates"]["files"]:
            if record["name"] == name:
                return record.get(key) == expected
        return False

    return check


def _gate_field(entry_id: str, key: str, expected):
    """i_cycle_form_differences 的 ID-5 gates 里某 entry 的字段必须等于期望值。"""

    def check(data: bytes) -> bool:
        payload = json.loads(data.decode("utf-8"))
        for diff in payload["i_cycle_form_differences"]["differences"]:
            if diff.get("id") != "ID-5":
                continue
            return diff["gates"].get(entry_id, {}).get(key) == expected
        return False

    return check


def _text_contains(needle: str, *, absent: bool = False):
    """源码类（.ts/.vue）变异的作用域自证：变异后必须（或必须不）含该串。

    🔴 源码侧没有 JSON 结构可解析，但仍然需要自证 —— 否则「锚点命中了注释里的同名行」
    这类脚本缺陷会被判成 GREEN。这里最少也要证明「改动确实落在我关心的那段文本上」。
    """

    def check(data: bytes) -> bool:
        text = data.decode("utf-8", errors="replace")
        return (needle not in text) if absent else (needle in text)

    return check


def _text_all(*needles: str):
    """多个串必须同时出现（用于「删了 A 同时加了 B」的双向自证）。"""

    def check(data: bytes) -> bool:
        text = data.decode("utf-8", errors="replace")
        return all(n in text for n in needles)

    return check


def _text_gone_and_new(gone: str, new: str):
    """旧串必须消失且新串必须出现（反向变异「把缺陷修一半」的自证）。"""

    def check(data: bytes) -> bool:
        text = data.decode("utf-8", errors="replace")
        return gone not in text and new in text

    return check


MUTATIONS: list[Mutation] = [
    # ═══════════════════════════════════════════════════════════════════════
    # ① AC 1.3 / 12.1 / 12.8 / 12.9：capability 裁决（按错法枚举，见 docstring 第 3 条）
    # ═══════════════════════════════════════════════════════════════════════
    Mutation(
        id="M01", side="be", path=SLICE, kind="replace",
        scope=S(E_I1), offset=OFF_CAPABILITY,
        anchor='      "capability": null,',
        new='      "capability": "bidirectional",',
        want=f"{_ADJ}::test_capability_matches_honest_capability",
        wants=(
            f"{_P69}::test_summary_counters_recompute_from_the_entries",
            f"{_DEL}::test_plan_entries_mirror_the_slice_adjudication",
            f"{_PARA}::test_the_slice_passes_the_paradigm_nominated_validator",
        ),
        why="把终态未定改成 bidirectional 而五个身份字段仍为 null 仍绿 ⇒ AC 12.1 的 SR-6 与"
            "SR-4 双口径判据都是死的，而这正是「假双向」最直接的入口",
        scope_check=_entry_field(E_I1, "capability", "bidirectional"),
        tags=("adjudication", "data"),
    ),
    Mutation(
        id="M02", side="be", path=SLICE, kind="replace",
        scope=S(E_I2), offset=OFF_CAPABILITY,
        anchor='      "capability": null,',
        new='      "capability": "single_onlyoffice",',
        want=f"{_ADJ}::test_single_onlyoffice_requires_no_html_counterpart",
        wants=(
            f"{_ADJ}::test_capability_matches_honest_capability",
            f"{_P69}::test_summary_counters_recompute_from_the_entries",
        ),
        why="html_counterpart_verdict == exists 却裁 single_onlyoffice 仍绿 ⇒ AC 12.8 的唯一"
            "合法判据（无 HTML 对端）没有被执行，全部 entry 都可以这样裁 ⇒ spec 空转",
        scope_check=_entry_field(E_I2, "capability", "single_onlyoffice"),
        tags=("adjudication", "data"),
    ),
    Mutation(
        id="M03", side="be", path=SLICE, kind="replace",
        scope=S(E_I3), offset=OFF_CAPABILITY,
        anchor='      "capability": null,',
        new='      "capability": "dual",',
        want=f"{_ADJ}::test_capability_is_enum_or_explicitly_pending",
        wants=(f"{_PARA}::test_the_slice_passes_the_paradigm_nominated_validator",),
        why="自造能力态 `dual` 仍绿 ⇒ AC 1.3 明禁的「含糊 dual 布尔」判据是死的",
        scope_check=_entry_field(E_I3, "capability", "dual"),
        tags=("adjudication", "data"),
    ),
    Mutation(
        id="M04", side="be", path=SLICE, kind="replace",
        scope=S(E_I4), offset=OFF_STAGE,
        anchor='      "capability_verdict_stage": "pipeline_entry_pending_definition_delivery",',
        new='      "capability_verdict_stage": "",',
        want=f"{_ADJ}::test_capability_is_enum_or_explicitly_pending",
        wants=(
            f"{_PARA}::test_the_slice_passes_the_paradigm_nominated_validator",
            f"{_DEL}::test_plan_entries_mirror_the_slice_adjudication",
        ),
        why="待裁决三字段之一变空串仍绿 ⇒ SR-3 右支退化成「留空即可」，未裁决就能伪装成已裁决",
        scope_check=_entry_field(E_I4, "capability_verdict_stage", ""),
        tags=("adjudication", "data"),
    ),
    Mutation(
        id="M05", side="be", path=SLICE, kind="replace",
        scope=S(E_I5), offset=OFF_TARGET,
        anchor='      "capability_target": "bidirectional",',
        new='      "capability_target": "maybe_someday",',
        want=f"{_ADJ}::test_capability_is_enum_or_explicitly_pending",
        wants=(
            f"{_PARA}::test_the_slice_passes_the_paradigm_nominated_validator",
            f"{_DEL}::test_plan_entries_mirror_the_slice_adjudication",
        ),
        why="capability_target 落在枚举外仍绿 ⇒「不知道往哪走」被当成待裁决，"
            "而范式明写那不是待裁决、是没调查",
        scope_check=_entry_field(E_I5, "capability_target", "maybe_someday"),
        tags=("adjudication", "data"),
    ),
    Mutation(
        id="M06", side="be", path=SLICE, kind="replace",
        scope=S(E_I6), offset=OFF_ADAPTER[E_I6],
        anchor='      "adapter_id": null,',
        new='      "adapter_id": "i6.detail",',
        want=f"{_ADJ}::test_pending_entries_carry_no_identity",
        wants=(
            f"{_PARA}::test_the_slice_passes_the_paradigm_nominated_validator",
            f"{_P20}::test_no_slice_entry_has_a_registered_adapter",
        ),
        why="未裁决 entry 挂上 adapter_id 仍绿 ⇒ AP-5（裁 single/未裁决不得挂身份）判据是死的",
        scope_check=_entry_field(E_I6, "adapter_id", "i6.detail"),
        tags=("adjudication", "data"),
    ),
    Mutation(
        id="M07", side="be", path=SLICE, kind="replace",
        scope=S(E_I1), offset=OFF_VERDICT[E_I1],
        anchor='      "html_counterpart_verdict": "exists",',
        new='      "html_counterpart_verdict": "unresolved",',
        want=f"{_ADJ}::test_every_entry_has_a_binary_html_counterpart_verdict",
        wants=(f"{_P69}::test_summary_counters_recompute_from_the_entries",),
        why="verdict 写成 unresolved 仍绿 ⇒ AP-3（「还没查」不是结论）判据是死的",
        scope_check=_entry_field(E_I1, "html_counterpart_verdict", "unresolved"),
        tags=("adjudication", "data"),
    ),
    Mutation(
        id="M08", side="be", path=SLICE, kind="replace",
        anchor='        "BP-6"',
        new='        "BP-99"',
        want=f"{_ADJ}::test_capability_blockers_reference_real_preconditions",
        wants=(f"{_ADJ}::test_every_entry_scoped_blocker_has_a_carrier",),
        why="blockers 指向不存在的 BP-99 仍绿 ⇒「阻断项必须真存在」判据是死的，"
            "于是可以用任意编号冒充「已登记」。锚点取 I3 的 blocked_by 末项（全文件 dup=1，"
            "因为只有 I3 的列表以 BP-6 结尾）",
        scope_check=_entry_field(
            E_I3, "capability_target_blocked_by", ["BP-1", "BP-2", "BP-3", "BP-4", "BP-99"]
        ),
        tags=("adjudication", "data"),
    ),
    Mutation(
        id="M09", side="be", path=SLICE, kind="replace",
        scope=S(E_I2), offset=103,
        anchor='        "capability": "single_onlyoffice",',
        new='        "capability": null,',
        want=f"{_ADJ}::test_manifest_mirror_divergence_is_registered_not_silently_equal",
        why="🔴 manifest overlay 陷阱：把 manifest_mirror 改成与 slice 相等（都是 null）仍绿 ⇒"
            "判据写成了「断言相等」而不是「断言必须不相等且已登记为 BP-9」，"
            "于是「slice 抄了 manifest 的错值」这条最容易犯的错查不出来",
        scope_check=_entry_field(E_I2, "manifest_mirror", "capability", None),
        tags=("adjudication", "manifest-overlay", "data"),
    ),

    # ═══════════════════════════════════════════════════════════════════════
    # ② HTML 对端 source-backed（step 3）
    # ═══════════════════════════════════════════════════════════════════════
    Mutation(
        id="M10", side="be", path=SLICE, kind="replace",
        scope=S(E_I5), offset=OFF_WRITE_CARRIER[E_I5],
        anchor='        "write_carrier": "formdata_composable",',
        new='        "write_carrier": "host_inline",',
        want=f"{_HTML}::test_write_carrier_families_cover_every_entry_exactly_once",
        wants=(
            f"{_HTML}::test_i5_host_really_has_no_http_client_import",
            f"{_P69}::test_summary_counters_recompute_from_the_entries",
        ),
        why="把唯一的 formdata_composable 载体改标成 host_inline 仍绿 ⇒ ID-1 的分族判据没有"
            "回源核对，而 I5 宿主根本没有 client import（写死「全宿主都有」会让它静默通过）",
        scope_check=_entry_field(E_I5, "html_counterpart", "write_carrier", "host_inline"),
        tags=("html-counterpart", "data"),
    ),
    Mutation(
        id="M11", side="be", path=SLICE, kind="replace",
        scope=S(E_I5), offset=OFF_PAYLOAD_MODE[E_I5],
        anchor='        "payload_column_mode": "passthrough_remark_and_conclusion",',
        new='        "payload_column_mode": "remark_only_conclusion_null",',
        want=f"{_HTML}::test_payload_column_mode_matches_the_write_site",
        why="I5 的写入点是 `conclusion: item.conclusion || null` 双列透传，改标成 remark_only"
            "仍绿 ⇒ 写列判据没有剥空占位后回源核对（G2 踩过的同一个坑的镜像）",
        scope_check=_entry_field(
            E_I5, "html_counterpart", "payload_column_mode", "remark_only_conclusion_null"
        ),
        tags=("html-counterpart", "data"),
    ),
    Mutation(
        id="M12", side="be", path=SLICE, kind="replace",
        scope=S(E_I2), offset=OFF_READ_CARRIER[E_I2],
        anchor='        "read_carrier": "host_inline_render_config_refetch",',
        new='        "read_carrier": "formdata_composable",',
        want=f"{_HTML}::test_read_carrier_matches_its_declared_family",
        why="读载体族改错仍绿 ⇒ ID-2 的「全走 render-config、0 条宿主直接 GET checklist」"
            "这条实况判据没有回源核对",
        scope_check=_entry_field(
            E_I2, "html_counterpart", "read_carrier", "formdata_composable"
        ),
        tags=("html-counterpart", "data"),
    ),
    Mutation(
        id="M13", side="be", path=SLICE, kind="replace",
        scope=S(E_I1), offset=OFF_IDENTITY_CELL[E_I1],
        anchor='          "identity_cell": "A8",',
        new='          "identity_cell": "A9",',
        want=f"{_HTML}::test_primary_table_identity_cell_matches_the_authoritative_template",
        why="primary table 的模板依据单元格改到别的格仍绿 ⇒ 「声明的 sheet!cell 真读出来等于"
            "声明的标签」这条三边锁的第一处应用是死的（A9 真读为 None）",
        scope_check=_entry_field(E_I1, "html_counterpart", "primary_table", "identity_cell", "A9"),
        tags=("html-counterpart", "source-ref-lock", "data"),
    ),
    Mutation(
        id="M14", side="be", path=SLICE, kind="replace",
        scope=S(E_I6), offset=OFF_ITEM_ID[E_I6],
        anchor='          "item_id": "I6-2-detail-rows",',
        new='          "item_id": "I6-2-rows",',
        want=f"{_HTML}::test_primary_table_owner_constant_is_real",
        wants=(f"{_HTML}::test_i6_legacy_alias_key_is_still_read_compatible",),
        why="🔴 I6 的主表键改成它的 legacy 别名仍绿 ⇒「owner 常量现读」判据是死的。"
            "这条同时验 ID-4 的「按命名规律推断会推错」结论：I6-2-rows 确实存在于源码里"
            "（是 LEGACY_STORAGE_KEY），所以只 grep 字符串存在的判据一定会放过它",
        scope_check=_entry_field(E_I6, "html_counterpart", "primary_table", "item_id", "I6-2-rows"),
        tags=("html-counterpart", "data"),
    ),
    Mutation(
        id="M15", side="be", path=SLICE, kind="replace",
        anchor='          "xlsx/gt-i2-development-expenditure": "i2-development-expenditure",',
        new='          "xlsx/gt-i2-development-expenditure": "i2-dev-expenditure",',
        want=f"{_HTML}::test_read_carrier_matches_its_declared_family",
        wants=(f"{_HTML}::test_host_has_a_real_module_edge_in_the_renderer_registry",),
        why="force_component_type 的值改错仍绿 ⇒ 读路径的 render-config 重取判据没有把"
            "componentType 落到源码字面量上（宿主里写的是 'i2-development-expenditure'）",
        scope_check=_text_contains('"i2-dev-expenditure"'),
        tags=("html-counterpart", "data"),
    ),

    # ═══════════════════════════════════════════════════════════════════════
    # ③ 🔴 source_ref 三边锁（Task 51 正文第一条）—— 三条边 + 合成边各自变异
    # ═══════════════════════════════════════════════════════════════════════
    Mutation(
        id="M16", side="be", path=SLICE, kind="replace",
        scope=CD(1), offset=14,
        anchor='          "土地使用权",',
        new='          "土地使用权X",',
        want=f"{_CLS}::test_declared_source_cells_read_back_exactly_the_frozen_labels",
        wants=(f"{_CLS}::test_verdicts_equal_the_actual_comparison",),
        why="**第②边（源侧基线）**：改 slice 冻结的 expected_source_labels 仍绿 ⇒ 源侧从未被"
            "openpyxl 现读，「声明」变成了自说自话",
        scope_check=_declaration_field(
            "CD-1", "expected_source_labels", 0, "土地使用权X",
        ),
        tags=("classification", "source-ref-lock", "data"),
    ),
    Mutation(
        id="M17", side="be", path=SLICE, kind="replace",
        scope=CD(1), offset=27,
        anchor='          "土地使用权",',
        new='          "土地使用权Y",',
        want=f"{_CLS}::test_impl_constants_read_back_exactly_the_frozen_labels",
        wants=(f"{_CLS}::test_verdicts_equal_the_actual_comparison",),
        why="**第③边（impl 侧现读）**：改 slice 冻结的 impl_labels 仍绿 ⇒ impl 常量从未被现读，"
            "「实现」也变成了自说自话",
        scope_check=_declaration_field("CD-1", "impl_labels", 0, "土地使用权Y"),
        tags=("classification", "source-ref-lock", "data"),
    ),
    Mutation(
        id="M18", side="be", path=SLICE, kind="replace",
        scope=CD(2), offset=54,
        anchor='        "verdict": "MISMATCH",',
        new='        "verdict": "MATCH",',
        want=f"{_CLS}::test_verdicts_equal_the_actual_comparison",
        wants=(
            f"{_CLS}::test_cd2_diverges_from_both_declared_sources",
            f"{_CLS}::test_summary_status_counts_recompute",
        ),
        why="**合成边**：把 BP-7 的 MISMATCH 篡改成 MATCH 仍绿 ⇒ verdict 是自述而不是可复算的，"
            "「声明与实现同错仍自洽」的洞根本没堵上",
        scope_check=_declaration_field("CD-2", "verdict", "MATCH"),
        tags=("classification", "source-ref-lock", "data"),
    ),
    Mutation(
        id="M19", side="be", path=SLICE, kind="replace",
        scope=CD(4), offset=28,
        anchor='        "verdict": "PREFIX_MATCH_WITH_UNSOURCED_TAIL",',
        new='        "verdict": "MATCH",',
        want=f"{_CLS}::test_verdicts_equal_the_actual_comparison",
        wants=(
            f"{_CLS}::test_cd4_unsourced_tail_has_zero_hits_in_every_authoritative_source",
            f"{_CLS}::test_summary_status_counts_recompute",
        ),
        why="把 I6 的「前缀相等但尾部无源」篡改成完全相等仍绿 ⇒ 两种缺陷强度分不开，"
            "「补了 4 个无真源的分类」会被当成已核对",
        scope_check=_declaration_field("CD-4", "verdict", "MATCH"),
        tags=("classification", "source-ref-lock", "data"),
    ),
    Mutation(
        id="M20", side="be", path=SLICE, kind="replace",
        scope=CD(8), offset=23,
        anchor='        "verdict": "PREFIX_MATCH_WITH_UNSOURCED_TAIL",',
        new='        "verdict": "MATCH",',
        want=f"{_CLS}::test_verdicts_equal_the_actual_comparison",
        wants=(
            f"{_CLS}::test_cd8_i4_category_enum_has_an_unsourced_tail",
            f"{_CLS}::test_summary_status_counts_recompute",
        ),
        why="CD-8 是本轮据守卫打红新增的实体声明（初版误记为「I4 无分类常量」）—— 把它的 verdict"
            "篡改成 MATCH 仍绿就意味着那次改正等于没做",
        scope_check=_declaration_field("CD-8", "verdict", "MATCH"),
        tags=("classification", "source-ref-lock", "data"),
    ),
    Mutation(
        id="M21", side="be", path=SLICE, kind="replace",
        scope=CD(3), offset=11,
        anchor='        "cells": "A11:A20",',
        new='        "cells": "A12:A21",',
        want=f"{_CLS}::test_declared_source_cells_read_back_exactly_the_frozen_labels",
        why="**第①边（声明）**：把区间整体下移一行（仍是 10 格）仍绿 ⇒ 源真读要么没做、要么做成了"
            "「数量对得上就算过」。A12:A21 真读是 预付工程款..…… ，与冻结基线不等",
        scope_check=_declaration_field("CD-3", "cells", "A12:A21"),
        tags=("classification", "source-ref-lock", "data"),
    ),
    Mutation(
        id="M22", side="be", path=SLICE, kind="replace",
        scope=CD(7), offset=2,
        anchor='        "source_read_mode": "formula",',
        new='        "source_read_mode": "value",',
        want=f"{_CLS}::test_cd7_source_labels_are_formulas_pointing_at_the_detail_sheet",
        wants=(f"{_CLS}::test_declared_source_cells_read_back_exactly_the_frozen_labels",),
        why="CD-7 的源标签本身是公式串（源模板自己声明「披露行由明细行派生」），改成 value 读法"
            "仍绿 ⇒ 第三种 source_ref 形态（公式判据）根本没跑",
        scope_check=_declaration_field("CD-7", "source_read_mode", "value"),
        tags=("classification", "source-ref-lock", "data"),
    ),
    Mutation(
        id="M23", side="be", path=SLICE, kind="replace",
        scope=CD(5), offset=6,
        anchor='        "impl_constant": null,',
        new='        "impl_constant": "COURSE_OPTIONS",',
        want=f"{_CLS}::test_impl_constants_read_back_exactly_the_frozen_labels",
        wants=(
            f"{_CLS}::test_negative_declarations_really_have_no_impl_copy",
            f"{_P69}::test_derived_counters_recompute_from_their_own_sections",
        ),
        why="否定式声明（CD-5：源模板占位不得被抄成常量）被塞进一个不存在的常量名仍绿 ⇒"
            "kind=none 与实体声明的一致性判据是死的，而「照源模板补全分类常量」这个危险动作"
            "只有这条否定式能拦",
        scope_check=_declaration_field("CD-5", "impl_constant", "COURSE_OPTIONS"),
        tags=("classification", "source-ref-lock", "data"),
    ),
    Mutation(
        id="M24", side="be", path=SLICE, kind="replace",
        anchor='      "clean": 4,',
        new='      "clean": 5,',
        want=f"{_CLS}::test_summary_status_counts_recompute",
        wants=(f"{_P69}::test_derived_counters_recompute_from_their_own_sections",),
        why="分类核对的 status 计数被篡改（4→5，即把一条缺陷记成 clean）仍绿 ⇒ 摘要与明细脱节，"
            "「本 slice 分类全对」这种结论可以凭空写出来",
        scope_check=_json_at(5, "classification_row_model_derivation", "summary", "clean"),
        tags=("classification", "counters", "data"),
    ),
    # ── 第③边的**真源码**变异（证明 impl 侧是现读的，不是抄 slice）──────────
    Mutation(
        id="M25", side="be", path=I1_SCOPE_TS, kind="replace",
        anchor="  { key: 'mining_right', label: '矿产权', seq: 9, removable: true },",
        new="  { key: 'mining_right', label: '采矿权', seq: 9, removable: true },",
        want=f"{_CLS}::test_impl_constants_read_back_exactly_the_frozen_labels",
        wants=(f"{_CLS}::test_verdicts_equal_the_actual_comparison",),
        why="🔴 **真改前端分类常量**（把 CD-1 正例的 `矿产权` 改成 `采矿权`，即把它改成与 I1 SOE "
            "那份错常量一致）仍绿 ⇒ impl 侧是抄 slice 而不是现读源码，三边锁只有两边",
        scope_check=_text_gone_and_new(
            "{ key: 'mining_right', label: '矿产权', seq: 9, removable: true }",
            "{ key: 'mining_right', label: '采矿权', seq: 9, removable: true }",
        ),
        tags=("classification", "source-ref-lock", "source"),
    ),
    Mutation(
        id="M26", side="be", path=I1_SOE_TS, kind="replace",
        anchor="  { key: 'mining', label: '采矿权', shortLabel: '采矿权' },",
        new="  { key: 'mining', label: '矿产权', shortLabel: '矿产权' },",
        want=f"{_CLS}::test_impl_constants_read_back_exactly_the_frozen_labels",
        wants=(
            f"{_CLS}::test_cd2_diverges_from_both_declared_sources",
            f"{_CLS}::test_verdicts_equal_the_actual_comparison",
        ),
        why="🔴 **反向变异**：把 BP-7 的缺陷「修一半」（`采矿权` → 源标签 `矿产权`）而不改登记，"
            "impl-only 差集从 4 项变 3 项 ⇒ 判据必须同样打红。只验「新增缺陷」一个方向的穷举"
            "判据是半个判据：缺陷被修好而登记没删，报告会长期挂着一条已解决的债",
        scope_check=_text_gone_and_new(
            "{ key: 'mining', label: '采矿权', shortLabel: '采矿权' }",
            "{ key: 'mining', label: '矿产权', shortLabel: '矿产权' }",
        ),
        tags=("classification", "source-ref-lock", "reverse", "source"),
    ),
    Mutation(
        id="M27", side="be", path=I5_DETAIL_TS, kind="replace",
        anchor="  { name: '预付工程款', indexRef: '' },",
        new="  { name: '预付工程费', indexRef: '' },",
        want=f"{_CLS}::test_impl_constants_read_back_exactly_the_frozen_labels",
        wants=(f"{_CLS}::test_verdicts_equal_the_actual_comparison",),
        why="把 CD-3（全 slice 唯一的三向一致正例）的第 2 个分类改名仍绿 ⇒ 正例锚点是死的，"
            "而没有正例的穷举判据无法区分「守卫在跑」与「守卫恒返回空」",
        scope_check=_text_gone_and_new(
            "{ name: '预付工程款', indexRef: '' }", "{ name: '预付工程费', indexRef: '' }"
        ),
        tags=("classification", "source-ref-lock", "source"),
    ),
    Mutation(
        id="M28", side="be", path=I4_DETAIL_TS, kind="replace",
        anchor="  '开办费',",
        new="  '筹建费',",
        want=f"{_CLS}::test_impl_constants_read_back_exactly_the_frozen_labels",
        wants=(
            f"{_CLS}::test_cd8_i4_category_enum_has_an_unsourced_tail",
            f"{_CLS}::test_verdicts_equal_the_actual_comparison",
        ),
        why="把 CD-8 无真源尾部的一项改名（`开办费` → `筹建费`，两者在权威模板里都是 0 命中）"
            "仍绿 ⇒ 「无真源尾部」的穷举比对没有落到 impl 现读上，只是抄了一份快照",
        scope_check=_text_gone_and_new("  '开办费',", "  '筹建费',"),
        tags=("classification", "source-ref-lock", "source"),
    ),

    # ═══════════════════════════════════════════════════════════════════════
    # ④ Property 22 / 23 的穷举等值（双向）
    # ═══════════════════════════════════════════════════════════════════════
    Mutation(
        id="M29", side="be", path=I3_DISCLOSURE_TS, kind="insert",
        anchor="      rowId: `cgu-${i}`,",
        new="      extraRowId: 0, // mutation probe\n      rowId: `probe-${idx}`,",
        want=f"{_P23}::test_positional_identity_inventory_is_exhaustive_and_partitioned",
        why="注入第 7 条位置化行身份仍绿 ⇒ 穷举清单只对声明过的 6 条打红，"
            "新出现的第 7 条不会被发现（清单于是不是穷举的）",
        scope_check=_text_contains("rowId: `probe-${idx}`"),
        tags=("property-23", "source"),
    ),
    Mutation(
        id="M30", side="be", path=I3_DISCLOSURE_TS, kind="replace",
        anchor="      rowId: `cgu-${i}`,",
        new="      rowId: `cgu-${String(name).replace(/\\s/g, '_')}`,",
        want=f"{_P23}::test_positional_identity_inventory_is_exhaustive_and_partitioned",
        wants=(f"{_P23}::test_family_a_hit_writes_to_the_declared_persisted_key",),
        why="🔴 **反向变异**：把 BP-6 的 family_a 那条（唯一纯下标且真落库的）改成稳定身份，"
            "命中数从 6 降到 5 ⇒ 判据必须同样打红。修好而不删登记会让 BP-6 永久挂着",
        scope_check=_text_gone_and_new(
            "rowId: `cgu-${i}`", "rowId: `cgu-${String(name).replace(/\\s/g, '_')}`"
        ),
        tags=("property-23", "reverse", "source"),
    ),
    Mutation(
        id="M31", side="be", path=SLICE, kind="replace",
        anchor='        "count": 20,',
        new='        "count": 19,',
        want=f"{_P23}::test_display_sequence_sites_are_not_flagged",
        wants=(f"{_P69}::test_derived_counters_recompute_from_their_own_sections",),
        why="family_c（20 处展示序号 `seq: idx + 1`）的计数被改仍绿 ⇒ 反向自检的分母没有现扫，"
            "而这 20 处正是「判据口径是否回到错误的整行判」的唯一探针",
        scope_check=_json_at(
            19, "dynamic_row_identity", "positional_identity_inventory",
            "family_c_display_ordinal_must_not_be_flagged", "count",
        ),
        tags=("property-23", "counters", "data"),
    ),
    Mutation(
        id="M32", side="be", path=I6_DETAIL_TS, kind="insert",
        anchor="export const I6_DETAIL_DEFAULT_CATEGORIES = [",
        new="  '试制费',",
        want=f"{_CLS}::test_impl_constants_read_back_exactly_the_frozen_labels",
        wants=(
            f"{_CLS}::test_cd4_unsourced_tail_has_zero_hits_in_every_authoritative_source",
            f"{_CLS}::test_verdicts_equal_the_actual_comparison",
        ),
        why="🔴 **真改前端分类常量**：往 I6 默认类别的**首位**插入一条无真源的 `试制费` ⇒"
            "前缀不再等于源 xlsx 的 A9:A12，verdict 应从 PREFIX_MATCH 变成 MISMATCH。仍绿 ⇒"
            "CD-4 的 impl 侧是抄 slice 快照而不是现读源码，而且「前缀相等」这个较弱的判据"
            "连顺序都没验",
        scope_check=_text_contains("  '试制费',"),
        tags=("classification", "source-ref-lock", "source"),
    ),
    Mutation(
        id="M33", side="be", path=I3_DISCLOSURE_TS, kind="insert",
        anchor="      rowId: `cgu-${i}`,",
        new="      padding: blankRows(rows, 3),",
        want=f"{_P22}::test_no_hardcoded_blank_rows_or_horizontal_columns",
        why="注入一处 `blankRows(expr, 3)`（memory 铁律 ⑥ 与任务正文明禁的「动态区骨架行数写死」）"
            "仍绿 ⇒ 硬编码扫描的 0 命中是空跑出来的",
        scope_check=_text_contains("blankRows(rows, 3)"),
        tags=("property-22", "source"),
    ),
    Mutation(
        id="M34", side="be", path=I3_DISCLOSURE_TS, kind="insert",
        anchor="      rowId: `cgu-${i}`,",
        new="      col: { key: c.label, label: c.label },",
        want=f"{_P22}::test_label_as_key_hits_are_exactly_zero",
        why="注入一处 `key: c.label`（H8 的 DV-1 形态）仍绿 ⇒「I 循环 label-as-key 0 命中」"
            "这条结论是空跑出来的，而它正是 Property 22 的反例分母",
        scope_check=_text_contains("key: c.label"),
        tags=("property-22", "source"),
    ),
    Mutation(
        id="M35", side="be", path=I3_DISCLOSURE_TS, kind="insert",
        anchor="      rowId: `cgu-${i}`,",
        new="      seedId: `seed-${i}`,",
        want=f"{_P23}::test_four_table_seed_family_is_really_absent",
        why="注入 H 循环 BP-6 那种四表种子位置化形态（`seed-${i}`）仍绿 ⇒ family_d 的 0 命中"
            "是分母为空的重言式，而「I 循环没有这一族」正是靠它成立",
        scope_check=_text_contains("seedId: `seed-${i}`"),
        tags=("property-23", "source"),
    ),

    # ═══════════════════════════════════════════════════════════════════════
    # ⑤ 孤儿 composable 与「注释伪消费边」（BP-5 / ID-3）
    # ═══════════════════════════════════════════════════════════════════════
    Mutation(
        id="M36", side="be", path=SLICE, kind="replace",
        scope='            "module": "audit-platform/frontend/src/components/workpaper/composables/useI4FormData.ts",',
        offset=3,
        anchor='            "production_consumers": [],',
        new='            "production_consumers": ["audit-platform/frontend/src/components/workpaper/GtI4LongTermPrepaid.vue"],',
        want=f"{_ORPHAN}::test_declared_orphan_formdata_composables_really_have_no_consumer",
        wants=(f"{_P69}::test_derived_counters_recompute_from_their_own_sections",),
        why="把孤儿的消费方列表从空改成「宿主」仍绿 ⇒ 孤儿判据只验了一侧（声称零消费的真零），"
            "没验另一侧（声明有消费方就必须真有）。宿主实际只在注释里提到它",
        scope_check=_text_contains(
            '"production_consumers": ["audit-platform/frontend/src/components/workpaper/GtI4LongTermPrepaid.vue"]'
        ),
        tags=("orphan", "data"),
    ),
    Mutation(
        id="M37", side="be", path=I3_DUAL_TS, kind="replace",
        anchor=" * - Follow useI1DualMode pattern",
        new="import { useI1DualMode } from './useI1DualMode'",
        want=f"{_ORPHAN}::test_mention_only_edges_are_not_import_edges",
        wants=(
            f"{_ORPHAN}::test_declared_dual_mode_consumers_match_the_source",
            f"{_SELF}::test_import_specifier_consumers_is_path_literal_not_symbol_name",
        ),
        why="🔴 把「仅注释提及」变成**真 import 边**仍绿 ⇒ 判归属的口径退回符号名 grep，"
            "而这 4 处注释正是 I 循环里「符号名口径会误报 4 条消费边」的实证",
        scope_check=_text_gone_and_new(
            " * - Follow useI1DualMode pattern",
            "import { useI1DualMode } from './useI1DualMode'",
        ),
        tags=("orphan", "pseudo-consumer", "source"),
    ),
    Mutation(
        id="M38", side="be", path=SLICE, kind="replace",
        anchor='        "lines": 142,',
        new='        "lines": 143,',
        want=f"{_ORPHAN}::test_declared_dual_mode_consumers_match_the_source",
        why="legacy composable 的行数登记改错仍绿 ⇒ 待删对象的规模是抄的而不是现算的"
            "（首轮就是把 splitlines 与 split('\\n') 口径搞混，全部 6 条各多算 1 行）",
        scope_check=_text_contains('"lines": 143,'),
        tags=("orphan", "data"),
    ),

    # ═══════════════════════════════════════════════════════════════════════
    # ⑥ Property 28：template identity 漂移 fail closed
    # ═══════════════════════════════════════════════════════════════════════
    Mutation(
        id="M39", side="be", path=SLICE, kind="replace",
        anchor='        "sha256": "924a1e8348a897c268dcef7231c6c3d0db2f8382446a729d051e825ea71748eb",',
        new='        "sha256": "924a1e8348a897c268dcef7231c6c3d0db2f8382446a729d051e825ea71748eb0",',
        want=f"{_P28}::test_authoritative_template_digests_recompute",
        why="权威模板 digest 改一字仍绿 ⇒ Property 28 的 template identity 层判据没有 hashlib 现算",
        scope_check=_template_field(
            "I6 研发费用.xlsx", "sha256",
            "924a1e8348a897c268dcef7231c6c3d0db2f8382446a729d051e825ea71748eb0",
        ),
        tags=("property-28", "data"),
    ),
    Mutation(
        id="M40", side="be", path=SLICE, kind="replace",
        anchor='        "sheet_count": 11,',
        new='        "sheet_count": 12,',
        want=f"{_P28}::test_authoritative_template_digests_recompute",
        why="sheet 数改错仍绿 ⇒ 「OO 侧有真实业务价值」这条 not_single_html_because 的证据"
            "（每册多少张业务 sheet）是自述而不是 openpyxl 现读",
        scope_check=_template_field("I6 研发费用.xlsx", "sheet_count", 12),
        tags=("property-28", "data"),
    ),
    Mutation(
        id="M41", side="be", path=SLICE, kind="replace",
        scope='        "wp_code": "I6-6",',
        offset=1,
        anchor='        "resolved": "I6 研发费用.xlsx"',
        new='        "resolved": "I2 开发支出.xlsx"',
        want=f"{_P28}::test_template_resolution_audit_recomputes",
        why="模板解析审计的冻结结果改成另一本册仍绿 ⇒ 31 条 wp_code 没有真跑 wp_template_finder，"
            "「I 循环没有 F2 那种整册码回落」这条结论就是文档声明",
        scope_check=_text_contains('"resolved": "I2 开发支出.xlsx"'),
        tags=("property-28", "data"),
    ),
    Mutation(
        id="M42", side="be", path=SLICE, kind="replace",
        anchor='    "reference_copy_status": "absent_in_worktree",',
        new='    "reference_copy_status": "verified_against_reference_copy",',
        want=f"{_P28}::test_reference_copy_status_is_honest",
        why="把「参考副本不在工作树」改成「已与参考副本比对」仍绿 ⇒ 能力缺口可以被写成豁免，"
            "而 G4/G5/G6 正是因为据落后的参考副本重建而返工过",
        scope_check=_json_at(
            "verified_against_reference_copy", "authoritative_templates", "reference_copy_status"
        ),
        tags=("property-28", "data"),
    ),

    # ═══════════════════════════════════════════════════════════════════════
    # ⑦ Property 69 / 70：evidence 蕴含 + 计数现算 + 跨 entry 隔离
    # ═══════════════════════════════════════════════════════════════════════
    Mutation(
        id="M43", side="be", path=SLICE, kind="replace",
        scope=S(E_I1), offset=OFF_VERIF_STATE,
        anchor='        "verification_state": "UNVERIFIABLE",',
        new='        "verification_state": "VERIFIED",',
        want=f"{_P69}::test_unverifiable_entries_carry_non_empty_reasons",
        wants=(f"{_P69}::test_summary_counters_recompute_from_the_entries",),
        why="声称 VERIFIED 而 sync_test_run_id / required_scenario_set_digest 仍为 null 仍绿 ⇒"
            "「声称已验收必须有 run id + digest」这条蕴含关系是死的 ⇒ 可以空口宣称验收",
        scope_check=_entry_field(E_I1, "evidence", "verification_state", "VERIFIED"),
        tags=("property-69", "data"),
    ),
    Mutation(
        id="M44", side="be", path=SLICE, kind="replace",
        anchor='    "total_independent": 6,',
        new='    "total_independent": 7,',
        want=f"{_P69}::test_summary_counters_recompute_from_the_entries",
        wants=(f"{_PARA}::test_the_slice_passes_the_paradigm_nominated_validator",),
        why="SR-1 的核心计数被篡改仍绿 ⇒ 摘要与明细脱节，「已迁移 N 条」可以凭空写大",
        scope_check=_json_at(7, "honest_adjudication_summary", "total_independent"),
        tags=("property-69", "counters", "data"),
    ),
    Mutation(
        id="M45", side="be", path=SLICE, kind="replace",
        anchor='      "unadjudicated": 6,',
        new='      "unadjudicated": 0,',
        want=f"{_P69}::test_slice_counters_are_all_zero_except_unadjudicated",
        wants=(
            f"{_P69}::test_summary_counters_recompute_from_the_entries",
            f"{_PARA}::test_the_slice_passes_the_paradigm_nominated_validator",
            f"{_PARA}::test_the_validator_really_catches_a_counter_mismatch",
        ),
        why="把待裁决计数归零（=「全绿冒充进度」的经典形态）仍绿 ⇒ SR-9 是死的，"
            "SR-3 右支就成了后门：全记待裁决同时报 0",
        scope_check=_json_at(
            0, "honest_adjudication_summary", "slice_counters", "unadjudicated"
        ),
        tags=("property-69", "counters", "data"),
    ),
    Mutation(
        id="M46", side="be", path=SLICE, kind="replace",
        anchor='    "positional_identity_hits_total": 6,',
        new='    "positional_identity_hits_total": 7,',
        want=f"{_P69}::test_derived_counters_recompute_from_their_own_sections",
        why="派生计数（位置化命中总数）与它自己的来源节脱节仍绿 ⇒ 摘要里的每个数都可以手填",
        scope_check=_json_at(
            7, "honest_adjudication_summary", "positional_identity_hits_total"
        ),
        tags=("property-69", "counters", "data"),
    ),
    Mutation(
        id="M47", side="be", path=SLICE, kind="replace",
        scope='        "name": "I6 研发费用.xlsx",',
        offset=3,
        anchor='        "belongs_to_entry": "xlsx/gt-i6-research-development-expense",',
        new='        "belongs_to_entry": "xlsx/gt-i1-intangible-assets",',
        want=f"{_P28}::test_template_owner_mapping_is_a_bijection",
        wants=(f"{_P70}::test_six_slices_are_pairwise_disjoint",),
        why="把模板归属改到另一 entry（I1 于是有两本册、I6 一本都没有）仍绿 ⇒ Property 70 的"
            "**双射**判据只验了单射或只验了满射。I 循环是 6↔6 双射，比 F/G/H 更严的那条"
            "判据必须真的两个方向都验",
        scope_check=_template_field(
            "I6 研发费用.xlsx", "belongs_to_entry", "xlsx/gt-i1-intangible-assets"
        ),
        tags=("property-70", "data"),
    ),
    Mutation(
        id="M48", side="be", path=SLICE, kind="replace",
        anchor='    "backend/data/workpaper_sync_h_cycle_manifest_slice.json"',
        new='    "backend/data/workpaper_sync_zz_cycle_manifest_slice.json"',
        want=f"{_P70}::test_sibling_slices_declared_match_the_disk",
        why="兄弟 slice 清单把 H 换成一份不存在的 slice 仍绿 ⇒ 跨 slice 互斥判据的分母可以被悄悄"
            "改掉，「与 H 循环无交集」这条最容易撞车的判据就不跑了。"
            "🔴 首版用 kind=delete 删掉这一行（它是数组末元素）⇒ 前一行留下尾逗号、JSON 失效、"
            "scope_check 的 json.loads 抛 JSONDecodeError ⇒ 判定 ERROR。这是**脚本缺陷**"
            "（四态里的 ANCHOR-MISS 同类），不是守卫缺陷 —— 改成 replace 后 JSON 仍合法",
        scope_check=lambda data: json.loads(data.decode("utf-8"))["sibling_slices"][-1]
        == "backend/data/workpaper_sync_zz_cycle_manifest_slice.json",
        tags=("property-70", "data"),
    ),

    # ═══════════════════════════════════════════════════════════════════════
    # ⑧ AC 1.4 的 UI 义务（step 11 / BP-10）
    # ═══════════════════════════════════════════════════════════════════════
    Mutation(
        id="M49", side="be", path=SLICE, kind="replace",
        scope='        "gates": {',
        offset=11,
        anchor='            "segmented_second_level_gate": null,',
        new='            "segmented_second_level_gate": "dualMode.isOoAvailable.value",',
        want=f"{_AC14}::test_second_level_gate_presence_matches_the_declaration",
        wants=(f"{_P69}::test_derived_counters_recompute_from_their_own_sections",),
        why="🔴 把 I2 的「无二级门控」这一实况改成「有」仍绿 ⇒ 判据写死了「全 slice 都有二级门控」，"
            "于是在 I2 上静默恒真 —— 而 I2 恰恰是 AC 1.5 最严重的那条（OO 不可用也显示切换按钮）",
        scope_check=_gate_field(E_I2, "segmented_second_level_gate", "dualMode.isOoAvailable.value"),
        tags=("ac-1.4", "data"),
    ),
    Mutation(
        id="M50", side="be", path=SLICE, kind="replace",
        scope='        "gates": {',
        offset=6,
        anchor='            "extra_unrelated_segmented_at": "L171"',
        new='            "extra_unrelated_segmented_at": "L172"',
        want=f"{_AC14}::test_extra_unrelated_segmented_sites_are_declared_and_outside_the_toolbar",
        why="Tab 内部分段用的 el-segmented 站点行号改错仍绿 ⇒「不能全文件 grep el-segmented」"
            "这条口径判据没有落到真实行号上",
        scope_check=_gate_field(E_I1, "extra_unrelated_segmented_at", "L172"),
        tags=("ac-1.4", "data"),
    ),
    Mutation(
        id="M51", side="be", path=HOST_I1, kind="insert",
        anchor='      <div v-if="isHtmlSheet && currentSheet !== \'I1\'" class="i1-header-toolbar">',
        new="        <GtEntrySyncCapabilityNotice :entry-id=\"'xlsx/gt-i1-intangible-assets'\" />",
        want=f"{_AC14}::test_bp10_is_registered_because_no_host_mounts_the_notice",
        why="🔴 **反向变异**：在宿主里真挂上 AC 1.4 的 notice 组件而 BP-10 仍登记为未修 ⇒"
            "判据必须打红提示「可以解除 BP-10 了」。只拦「没挂」不拦「挂了但登记未更新」"
            "会让阻断项永久挂着（H 循环报告里的同型问题）",
        scope_check=_text_contains("<GtEntrySyncCapabilityNotice"),
        tags=("ac-1.4", "reverse", "source"),
    ),

    # ═══════════════════════════════════════════════════════════════════════
    # ⑨ deletion plan 与范式合规
    # ═══════════════════════════════════════════════════════════════════════
    Mutation(
        id="M52", side="be", path=PLAN, kind="replace",
        anchor='    "composables_to_delete": 6,',
        new='    "composables_to_delete": 5,',
        want=f"{_DEL}::test_plan_counters_recompute",
        why="清册计数被篡改仍绿 ⇒ 待删对象数量是手填的，删除执行方（Task 72）无从核对",
        scope_check=_json_at(5, "counters", "composables_to_delete"),
        tags=("deletion-plan", "counters", "data"),
    ),
    Mutation(
        id="M53", side="be", path=PLAN, kind="replace",
        anchor='    "result": "none",',
        new='    "result": "found",',
        want=f"{_ORPHAN}::test_no_host_inlined_second_implementation",
        why="把「I 循环没有宿主内联第二份实现」改成「有」仍绿 ⇒ 那个「没有」是文档声明而非实测，"
            "而它正是「删 composable + 改宿主的常规套路在 I 循环是安全的」这条结论的依据",
        scope_check=_json_at("found", "host_inlined_second_implementation", "result"),
        tags=("deletion-plan", "data"),
    ),
    Mutation(
        id="M54", side="be", path=PLAN, kind="replace",
        anchor='  "pilot_already_migrated": null,',
        new='  "pilot_already_migrated": {"entry_id": "xlsx/gt-i1-intangible-assets"},',
        want=f"{_DEL}::test_plan_has_no_pilot_branch",
        why="给 I 循环编一个 pilot 仍绿 ⇒「I 循环没有 pilot」这条排除项是自述而非实证，"
            "而它直接决定 selection_rule 里有没有第四条排除条件",
        scope_check=_json_at(
            {"entry_id": "xlsx/gt-i1-intangible-assets"}, "pilot_already_migrated"
        ),
        tags=("deletion-plan", "data"),
    ),
    Mutation(
        id="M55", side="be", path=SLICE, kind="replace",
        anchor='  "properties_verified": [',
        new='  "properties_verified": [21,',
        want=f"{_P20}::test_property_denominator_block_declares_what_is_not_claimed",
        why="properties_verified 里塞进一条分母为空的 Property（21）仍绿 ⇒「不宣称通过」的"
            "边界是散文，空分母重言式可以重新长回来",
        scope_check=lambda data: json.loads(data.decode("utf-8"))["properties_verified"][0] == 21,
        tags=("property-20", "data"),
    ),
    Mutation(
        id="M56", side="be", path=SLICE, kind="replace",
        anchor='    "residual_inconsistency": null,',
        new='    "residual_inconsistency": "范式与 slice 仍有未收口的字段级冲突",',
        want=f"{_PARA}::test_new_sections_are_declared_as_non_conflicting",
        why="范式冲突登记从「已收口」改成「仍有残留」而判据仍绿 ⇒ paradigm_schema_conflict"
            "整块变成自述散文，「本 slice 未改范式 JSON / 未扩充 capability_enum」也就无从核对",
        scope_check=_json_at(
            "范式与 slice 仍有未收口的字段级冲突", "paradigm_schema_conflict",
            "residual_inconsistency",
        ),
        tags=("paradigm", "data"),
    ),
]

GUARD_FILES = {
    T51: "Task 51 新建（AC 1.3/1.4/12.1/12.8/12.9 裁决合法性、**source_ref 三边锁**"
         "（声明 → openpyxl 真读源 xlsx → impl 常量现读，8 条 declaration 逐条比对 + verdict "
         "可复算 + 区间边界主张 + 否定式声明 + 双真源否证）、HTML 对端 5:1 偏斜写载体 + 全"
         " render-config 读路径 + I6 键/身份字段双例外的逐 entry 回源核对、Property 22 的"
         " label-as-key 与硬编码列数/行数穷举 0 命中、Property 23 的 6 个行身份构造点 + 6 条"
         "位置化命中四族划分（含 family_d 的 0 与 family_c 的 20 处反向自检）、BP-5 孤儿"
         " FormData composable 两侧断言 + 4 处注释伪消费边反向断言、Property 28 的 6 个模板"
         " digest/sheet 数 + 31 条模板解析实跑（含 I{n}A / I0 断言 None）、selection_rule 与"
         " 22 个计数现算、六 slice 不相交 + 模板归属双射、AC 1.4 的逐宿主门控形态判据"
         "（含 I2 无二级门控这一实况）、deletion plan 同源与计数、范式 slice_schema 校验器"
         "与两条反向自检）",
}

if __name__ == "__main__":
    raise SystemExit(
        run_cli(
            mutations=MUTATIONS,
            guard_files=GUARD_FILES,
            repo=REPO,
            description="Task 51 I 循环 Excel 独立 entry 迁移守卫变异检验",
            backend_args=[
                "backend/tests/workpaper_sync/test_task51_i_cycle_migration.py",
                "-q",
                "--tb=no",
                "-rfE",
                "-p",
                "no:randomly",
            ],
            baseline_backend_passed=123,
        )
    )
