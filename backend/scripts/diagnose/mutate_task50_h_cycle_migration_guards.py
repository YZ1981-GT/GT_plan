# -*- coding: utf-8 -*-
r"""Task 50 守卫变异检验 —— H 循环（除 H1）Excel 独立 entry 迁移。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 5 Task 50

用平台共享件 `backend/scripts/_mutation_kit`（`test_mutation_kit_adoption.py` 对新脚本强制
采纳：共享件的 `run_cli` 把 `guard_files`（覆盖面分母）做成签名层面必填，把「锚点含换行」
「new == anchor」「id 重复」「want 定位不到」全部拦在声明期）。

═══ 本脚本的四条硬约束 ═══

1. **每条变异都带 `scope_check`**。四态判定式「新增失败集合是否为空」识别不出「锚点落在被测
   判据的作用域之外」—— 改到了别处会被判 GREEN（守卫缺陷），而真相是脚本缺陷。数据文件的
   回调解析 JSON 后断言目标字段真的变成了期望值；源码文件的回调断言改动确实落在那段文本上。

2. **重复形态字段用 `scope` + `offset` 相对定位，绝不用绝对行号**。slice 是逐 entry 同构的
   生成物：`"capability": null,` 出现 9 次、`"capability_verdict_stage": …` 9 次、
   `"verification_state": "UNVERIFIABLE",` 9 次、`"in_runtime_index": true,` 11 次。绝对行号
   一改文件就失效（Task 47 的 M12 写死 `line=155` 而那行早已是别的内容，`--list` 当场拦住）。
   `scope` 取该 entry 唯一的 `entry_id` 行，`offset` 由 `tmp_t50_anchor_probe*.py`（一次性
   诊断，跑完即删）实算；行内已唯一（dup=1）的锚点则直接用整行，不做多余消歧。

3. **capability 变异按「裁决错法」而不是「逐 entry 复制」枚举**。本 slice 9 条 entry 的
   capability **全是同一形态**（null + 三字段齐备的待裁决态），逐条各写一次是 9 份同信息量的
   变异（每条要跑一遍全量守卫 ≈ 45s），换不来任何新判据。这里按**可被区分的错法**枚举：四个
   枚举值各填一次 + 自造枚举值 + 三个待裁决必填字段各破坏一次 + blockers 指向不存在的前置 +
   adapter_id 非 null + verdict 写成 `unresolved`（AP-3）+ manifest_mirror 与 slice 相等
   （BP-9 前提消失），并分布在 9 条不同 entry 上，从而同时把 9 组不同的 offset 走通。

4. **任务正文点名的两条 Property 必须双向变异**。Property 22（动态列 key 与 label 解耦）与
   Property 23（动态行身份不使用下标）的判据是**穷举等值**：
   * 正向 —— 把 H7 范式的四个结构要素（SK-1 key/label 分离 · SK-2 `max + 1` 不复用 ·
     SK-3 合计对动态数组 reduce · SK-4 行模型是声明式数组）各破坏一次；再注入一处
     `blankRows(expr, 3)` 与一处 `'公司1'` 横向列字面量（= 任务正文明禁的「硬编码列数/行数」）。
   * 反向 —— 把 H8 已登记的那处背离**修好**（`key: c.label` → `key: c.key`）而不删登记：
     实测命中 0 条 ≠ 声明 1 条，必须同样打红。只验一个方向的穷举判据是半个判据。
   同理 Property 23 既注入「新增第 18 条位置化命中」，也把已登记的 H2 种子点改成非位置化
   （命中减到 16 条），两个方向都要红。

用法（仓库根；本仓库 PATH 上的 `python` 指向坏掉的 `.venv_depprobe`，必须用显式解释器）::

    .\.venv\Scripts\python.exe backend/scripts/diagnose/mutate_task50_h_cycle_migration_guards.py --list
    .\.venv\Scripts\python.exe backend/scripts/diagnose/mutate_task50_h_cycle_migration_guards.py --check-anchors
    .\.venv\Scripts\python.exe backend/scripts/diagnose/mutate_task50_h_cycle_migration_guards.py --run all \
        --out .kiro/specs/workpaper-html-onlyoffice-bidirectional-writeback-closure/evidence/task50-h-cycle-migration/mutation_report.json

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
SLICE = "backend/data/workpaper_sync_h_cycle_manifest_slice.json"
PLAN = "backend/data/workpaper_sync_h_cycle_deletion_plan.json"
H1_CONTRACT = "backend/data/workpaper_sync_contracts/h1.disposal_check.json"
PRESETS = "backend/app/services/d_cycle_extraction/presets.py"

FE = "audit-platform/frontend/src"
WP = f"{FE}/components/workpaper"
COMP = f"{WP}/composables"
NOTICE_TS = f"{WP}/sync/workpaperEntrySyncNotice.ts"
NOTICE_VUE = f"{WP}/sync/GtEntrySyncCapabilityNotice.vue"
REGISTRY_TS = f"{WP}/htmlRendererRegistry.ts"
HOST_H2 = f"{WP}/GtH2ConstructionInProgress.vue"
HOST_H4 = f"{WP}/GtH4EngineeringMaterials.vue"
H7_LISTED = f"{COMP}/h7ListedDisclosureModel.ts"
H7_SOE = f"{COMP}/h7SoeDisclosureModel.ts"
H8_PAYLOAD = f"{COMP}/h8DisclosureSyncPayload.ts"
H8_DISCLOSURE = f"{COMP}/useH8Disclosure.ts"
H8_DETAIL = f"{COMP}/useH8Detail.ts"

# ── 期望打红的守卫（文件::类::方法，与 pytest 的 short nodeid 同形）─────────
T50 = "test_task50_h_cycle_migration.py"
_ADJ = f"{T50}::TestAdjudicationLegality"
_HTML = f"{T50}::TestHtmlCounterpartIsSourceBacked"
_P22 = f"{T50}::TestProperty22DynamicColumnKeyDecoupling"
_P23 = f"{T50}::TestProperty23DynamicRowIdentity"
_SEED = f"{T50}::TestOrphanSeedKey"
_ORPHAN = f"{T50}::TestOrphanLegacyComposables"
_P20 = f"{T50}::TestProperty20And21NotClaimed"
_P28 = f"{T50}::TestProperty28DefinitionDriftFailClosed"
_P69 = f"{T50}::TestProperty69EvidenceAndCounters"
_P70 = f"{T50}::TestProperty70NoCrossEntryReuse"
_AC14 = f"{T50}::TestAc14HonestModeVisibility"
_PARA = f"{T50}::TestParadigmCompliance"
_SRC = f"{T50}::TestSourceCodeStructure"

# ── 相对定位用的唯一 scope 锚（每条 entry 的 entry_id 行）───────────────────
S_H2 = '      "entry_id": "xlsx/gt-h2-construction-in-progress",'
S_H3 = '      "entry_id": "xlsx/gt-h3-investment-property",'
S_H4 = '      "entry_id": "xlsx/gt-h4-engineering-materials",'
S_H5 = '      "entry_id": "xlsx/gt-h5-oil-gas-assets",'
S_H6 = '      "entry_id": "xlsx/gt-h6-asset-disposal-clearing",'
S_H7 = '      "entry_id": "xlsx/gt-h7-biological-assets",'
S_H8 = '      "entry_id": "xlsx/gt-h8-right-of-use-assets",'
S_H9 = '      "entry_id": "xlsx/gt-h9-lease-liabilities",'
S_H10 = '      "entry_id": "xlsx/gt-h10-asset-disposal-income",'

E_H2 = "xlsx/gt-h2-construction-in-progress"
E_H3 = "xlsx/gt-h3-investment-property"
E_H4 = "xlsx/gt-h4-engineering-materials"
E_H5 = "xlsx/gt-h5-oil-gas-assets"
E_H6 = "xlsx/gt-h6-asset-disposal-clearing"
E_H7 = "xlsx/gt-h7-biological-assets"
E_H8 = "xlsx/gt-h8-right-of-use-assets"
E_H9 = "xlsx/gt-h9-lease-liabilities"
E_H10 = "xlsx/gt-h10-asset-disposal-income"

#: 逐 entry 的字段 offset（相对 `entry_id` 行；由一次性诊断实算，非估计值）。
#: 之所以不是一个常量 —— 各 entry 的 blocked_by 条数与 html_counterpart 子结构不同宽。
OFF_ADAPTER = {E_H2: 17, E_H3: 16, E_H4: 17, E_H5: 17, E_H6: 17, E_H7: 17, E_H8: 20,
               E_H9: 17, E_H10: 16}
OFF_VERDICT = {E_H2: 28, E_H3: 27, E_H4: 28, E_H5: 28, E_H6: 28, E_H7: 28, E_H8: 31,
               E_H9: 28, E_H10: 27}
OFF_BLOCKED_CLOSE = {E_H2: 14, E_H3: 13, E_H4: 14, E_H5: 14, E_H6: 14, E_H7: 14,
                     E_H8: 17, E_H9: 14, E_H10: 13}


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


def _template_field(name: str, key: str, expected):
    """authoritative_templates.files 里某本工作簿的某个字段必须等于期望值。"""

    def check(data: bytes) -> bool:
        payload = json.loads(data.decode("utf-8"))
        for record in payload["authoritative_templates"]["files"]:
            if record["name"] == name:
                return record.get(key) == expected
        return False

    return check


def _text_contains(needle: str, *, absent: bool = False):
    """源码类（.ts/.vue/.py）变异的作用域自证：变异后必须（或必须不）含该串。

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


MUTATIONS: list[Mutation] = [
    # ═══════════════════════════════════════════════════════════════════════
    # ① AC 1.3 / 12.1 / 12.8 / 12.9：capability 裁决（按错法枚举，见 docstring 第 3 条）
    # ═══════════════════════════════════════════════════════════════════════
    Mutation(
        id="M01", side="be", path=SLICE, kind="replace",
        scope=S_H2, offset=5,
        anchor='      "capability": null,',
        new='      "capability": "bidirectional",',
        want=f"{_ADJ}::test_capability_matches_honest_capability",
        wants=(
            f"{_P69}::test_summary_counters_are_recomputed_from_entries",
            f"{_P70}::test_deletion_plan_matches_slice",
            f"{_PARA}::test_the_slice_passes_the_paradigm_nominated_validator",
        ),
        why="把终态未定改成 bidirectional 而五个身份字段仍为 null 仍绿 ⇒ AC 12.1 的"
            "「缺 approved contract/bundle 不得进入 bidirectional 验收」与 slice_schema 的"
            " SR-4 / SR-6 整条失守",
        scope_check=_entry_field(E_H2, "capability", "bidirectional"),
        tags=("adjudication", "data"),
    ),
    Mutation(
        id="M02", side="be", path=SLICE, kind="replace",
        scope=S_H3, offset=5,
        anchor='      "capability": null,',
        new='      "capability": "single_onlyoffice",',
        want=f"{_ADJ}::test_single_onlyoffice_requires_no_html_counterpart",
        wants=(
            f"{_ADJ}::test_capability_matches_honest_capability",
            f"{_P69}::test_summary_counters_are_recomputed_from_entries",
        ),
        why="html_counterpart_verdict=exists 却裁 single_onlyoffice 仍绿 ⇒ AC 12.8 唯一合法"
            "判据（无 HTML 对端）失守，而这正是 AP-1 循环论证的落点",
        scope_check=_entry_field(E_H3, "capability", "single_onlyoffice"),
        tags=("adjudication", "data"),
    ),
    Mutation(
        id="M03", side="be", path=SLICE, kind="replace",
        scope=S_H4, offset=5,
        anchor='      "capability": null,',
        new='      "capability": "single_html",',
        want=f"{_ADJ}::test_capability_matches_honest_capability",
        wants=(
            f"{_P69}::test_summary_counters_are_recomputed_from_entries",
            f"{_PARA}::test_the_slice_passes_the_paradigm_nominated_validator",
        ),
        why="裁 single_html（= 声称 OO 侧无业务价值，AC 12.9）而 honest_capability 仍为 null "
            "仍绿 ⇒ 对外字段与诚实裁决可以双口径（SR-4 失守）",
        scope_check=_entry_field(E_H4, "capability", "single_html"),
        tags=("adjudication", "data"),
    ),
    Mutation(
        id="M04", side="be", path=SLICE, kind="replace",
        scope=S_H5, offset=5,
        anchor='      "capability": null,',
        new='      "capability": "unreachable",',
        want=f"{_ADJ}::test_capability_matches_honest_capability",
        wants=(
            f"{_P69}::test_summary_counters_are_recomputed_from_entries",
            f"{_PARA}::test_the_slice_passes_the_paradigm_nominated_validator",
        ),
        why="把一个有宿主、有 registry 入边、有 HTML 通道的 entry 裁成 unreachable 仍绿 ⇒ "
            "AC 1.7 的「不可达旧桩 SHALL 删除」会被误用到活入口上（删掉在用的宿主）",
        scope_check=_entry_field(E_H5, "capability", "unreachable"),
        tags=("adjudication", "data"),
    ),
    Mutation(
        id="M05", side="be", path=SLICE, kind="replace",
        scope=S_H6, offset=5,
        anchor='      "capability": null,',
        new='      "capability": "dual",',
        want=f"{_ADJ}::test_capability_is_enum_or_explicitly_pending",
        wants=(f"{_PARA}::test_the_slice_passes_the_paradigm_nominated_validator",),
        why="自造能力态 dual 仍绿 ⇒ AC 1.3 明令禁止的「含糊 dual 布尔值」回来了，"
            "而 dual 既不是四个终态之一也不是待裁决态",
        scope_check=_entry_field(E_H6, "capability", "dual"),
        tags=("adjudication", "data"),
    ),
    Mutation(
        id="M06", side="be", path=SLICE, kind="replace",
        scope=S_H7, offset=6,
        anchor='      "capability_verdict_stage": "pipeline_entry_pending_definition_delivery",',
        new='      "capability_verdict_stage": "",',
        want=f"{_ADJ}::test_capability_is_enum_or_explicitly_pending",
        wants=(f"{_PARA}::test_the_slice_passes_the_paradigm_nominated_validator",),
        why="待裁决态的 stage 变空串仍绿 ⇒ SR-3 右支的 non_empty_string 语义没人执行，"
            "「留空而不解释」就能冒充待裁决",
        scope_check=_entry_field(E_H7, "capability_verdict_stage", ""),
        tags=("adjudication", "data", "sr3"),
    ),
    Mutation(
        id="M07", side="be", path=SLICE, kind="replace",
        scope=S_H8, offset=7,
        anchor='      "capability_target": "bidirectional",',
        new='      "capability_target": "maybe_later",',
        want=f"{_ADJ}::test_capability_is_enum_or_explicitly_pending",
        wants=(f"{_PARA}::test_the_slice_passes_the_paradigm_nominated_validator",),
        why="capability_target 填一个不在枚举内的值仍绿 ⇒ SR-3 右支的 member_of_capability_enum"
            " 失守，「不知道往哪走」就能算成待裁决（范式原话：那不是待裁决，是没调查）",
        scope_check=_entry_field(E_H8, "capability_target", "maybe_later"),
        tags=("adjudication", "data", "sr3"),
    ),
    Mutation(
        id="M08", side="be", path=SLICE, kind="insert",
        scope=S_H9, offset=OFF_BLOCKED_CLOSE[E_H9],
        anchor="      ],",
        new='      "capability_target_blocked_by": [],',
        want=f"{_ADJ}::test_capability_is_enum_or_explicitly_pending",
        wants=(f"{_PARA}::test_the_slice_passes_the_paradigm_nominated_validator",),
        why="blocked_by 变空数组仍绿 ⇒ SR-3 右支的 non_empty_list 失守（声称有阻塞却说不出"
            "是什么 = 自由文本豁免）。用「在数组闭合行后插入同名空数组」实现：JSON 重复键取"
            "最后一个，故生效值为 []，且文件仍是合法 JSON —— 单行 replace 无法在不破坏 JSON "
            "的前提下清空一个多元素数组",
        scope_check=_entry_field(E_H9, "capability_target_blocked_by", []),
        tags=("adjudication", "data", "sr3"),
    ),
    Mutation(
        id="M09", side="be", path=SLICE, kind="replace",
        scope=S_H10, offset=9,
        anchor='        "BP-1",',
        new='        "BP-404",',
        want=f"{_ADJ}::test_capability_blockers_reference_real_preconditions",
        why="阻断项指向一个不存在的前置仍绿 ⇒ blocked_by 退化成自由文本标签，"
            "「缺什么已逐条登记」这句话失去可核对性",
        scope_check=_entry_field(
            E_H10, "capability_target_blocked_by", ["BP-404", "BP-2", "BP-3", "BP-4"]
        ),
        tags=("adjudication", "data"),
    ),
    Mutation(
        id="M10", side="be", path=SLICE, kind="replace",
        scope=S_H2, offset=OFF_ADAPTER[E_H2],
        anchor='      "adapter_id": null,',
        new='      "adapter_id": "h2.construction_detail",',
        want=f"{_ADJ}::test_single_or_pending_entries_carry_no_identity",
        wants=(
            f"{_P20}::test_no_slice_entry_has_a_registered_adapter",
            f"{_AC14}::test_registered_entry_ids_agree_with_the_slice",
            f"{_PARA}::test_the_slice_passes_the_paradigm_nominated_validator",
        ),
        why="待裁决 entry 挂上 adapter_id 仍绿 ⇒ AP-5 / SR-5 失守（裁 single 或未定的 entry"
            "不得挂 adapter / contract / bundle / candidate / representation），且前端通知真源的"
            "已注册集合与 slice 会双口径",
        scope_check=_entry_field(E_H2, "adapter_id", "h2.construction_detail"),
        tags=("adjudication", "data"),
    ),
    Mutation(
        id="M11", side="be", path=SLICE, kind="replace",
        scope=S_H6, offset=OFF_VERDICT[E_H6],
        anchor='      "html_counterpart_verdict": "exists",',
        new='      "html_counterpart_verdict": "unresolved",',
        want=f"{_ADJ}::test_every_entry_has_a_binary_html_counterpart_verdict",
        wants=(
            f"{_P69}::test_summary_counters_are_recomputed_from_entries",
            f"{_P70}::test_deletion_plan_matches_slice",
        ),
        why="把「还没查」当结论（AP-3 的 unresolved）仍绿 ⇒ step 3 的二值结论要求形同虚设，"
            "而裁 single_onlyoffice 的合法性完全建立在这个二值结论上",
        scope_check=_entry_field(E_H6, "html_counterpart_verdict", "unresolved"),
        tags=("adjudication", "data"),
    ),
    Mutation(
        id="M12", side="be", path=SLICE, kind="replace",
        scope=S_H4, offset=105,
        anchor='        "capability": "single_onlyoffice",',
        new='        "capability": null,',
        want=f"{_ADJ}::test_manifest_mirror_divergence_is_registered_not_silently_equal",
        why="把 manifest_mirror 抄成与 slice 相同仍绿 ⇒ BP-9 的前提（overlay 组件级默认值不是"
            "裁决真源）消失，且「必须不一致且已登记」这条判据退化成「随便写都行」",
        scope_check=_entry_field(E_H4, "manifest_mirror", "capability", None),
        tags=("adjudication", "data"),
    ),

    # ═══════════════════════════════════════════════════════════════════════
    # ② step 3：HTML 对端结论必须 source-backed（载体三族 / 读路径五种 / 传输键三形态）
    # ═══════════════════════════════════════════════════════════════════════
    Mutation(
        id="M13", side="be", path=SLICE, kind="replace",
        scope=S_H2, offset=34,
        anchor='        "write_client": "http",',
        new='        "write_client": "api",',
        want=f"{_HTML}::test_write_carrier_client_and_put_site_agree_with_the_source",
        why="声明的 HTTP 客户端与源码不符仍绿 ⇒ 探针退化成「`api.` 或 `http.` 二选一」的固定"
            "并集（任一族改名都不会红），H 循环恰好两族并存，并集判据必然恒真",
        scope_check=_entry_field(E_H2, "html_counterpart", "write_client", "api"),
        tags=("counterpart", "data"),
    ),
    Mutation(
        id="M14", side="be", path=SLICE, kind="replace",
        anchor='        "endpoint_write_source": "audit-platform/frontend/src/components/'
               'workpaper/GtH2ConstructionInProgress.vue#L522",',
        new='        "endpoint_write_source": "audit-platform/frontend/src/components/'
            'workpaper/GtH2ConstructionInProgress.vue#L1",',
        want=f"{_HTML}::test_write_carrier_client_and_put_site_agree_with_the_source",
        why="写入点行号指向一行不是 `client.put(` 的代码仍绿 ⇒ 判据只验「文件里有 put」而不验"
            "「声明的那一行就是 put」，行号从此变成装饰",
        scope_check=_entry_field(
            E_H2, "html_counterpart", "endpoint_write_source",
            "audit-platform/frontend/src/components/workpaper/GtH2ConstructionInProgress.vue#L1",
        ),
        tags=("counterpart", "data"),
    ),
    Mutation(
        id="M15", side="be", path=SLICE, kind="replace",
        scope=S_H2, offset=39,
        anchor='        "read_carrier": "render_config_snapshot_passthrough",',
        new='        "read_carrier": "formdata_composable",',
        want=f"{_HTML}::test_read_carrier_matches_its_declared_family",
        wants=(
            f"{_HTML}::test_read_carrier_families_cover_every_entry_exactly_once",
            f"{_P69}::test_summary_counters_are_recomputed_from_entries",
        ),
        why="读路径族声明错了仍绿 ⇒ 五种读路径各自的判据（GET /checklist-responses vs "
            "props.htmlData vs render-config 强刷）没有一种在真正生效，而 F 循环那套"
            "「持久化 composable 必须自带 GET+PUT」对 H 的 4 条 entry 本就失配",
        scope_check=_entry_field(E_H2, "html_counterpart", "read_carrier", "formdata_composable"),
        tags=("counterpart", "data"),
    ),
    Mutation(
        id="M16", side="be", path=SLICE, kind="replace",
        anchor='        "payload_column_mode": "remark_only_with_explicit_null_conclusion",',
        new='        "payload_column_mode": "dual_write_remark_and_conclusion",',
        want=f"{_HTML}::test_payload_column_mode_matches_the_write_site",
        why="把 H7 的「remark + 显式 null 占位」谎报成双写仍绿 ⇒ `conclusion: null`（= **不**往"
            "这列写内容）会被当成真双写，contract 会声明一个根本不存在的字段通道（G 循环在 G2 "
            "上踩过同一个坑）",
        scope_check=_entry_field(
            E_H7, "html_counterpart", "payload_column_mode", "dual_write_remark_and_conclusion"
        ),
        tags=("counterpart", "data"),
    ),
    Mutation(
        id="M17", side="be", path=SLICE, kind="replace",
        scope=S_H2, offset=75,
        anchor='          "identity_cell": "A9",',
        new='          "identity_cell": "A10",',
        want=f"{_HTML}::test_primary_table_identity_cell_matches_the_authoritative_template",
        why="主表身份单元格坐标写错仍绿 ⇒ 「模板依据已 openpyxl 逐格核验」这句话没有承载者，"
            "对端结论退回自由文本",
        scope_check=_entry_field(
            E_H2, "html_counterpart", "primary_table", "identity_cell", "A10"
        ),
        tags=("counterpart", "data", "property28"),
    ),
    Mutation(
        id="M18", side="be", path=SLICE, kind="replace",
        scope=S_H2, offset=69,
        anchor='          "owner_constant": "ROWS_KEY",',
        new='          "owner_constant": "ROWS_KEY_V2",',
        want=f"{_HTML}::test_transport_key_kind_matches_the_source",
        why="owner 常量名与源码不符仍绿 ⇒ 三种键声明形态（module_constant / 前缀拼接 / Tab 内联"
            "字面量）的判据全部空转，而 H 循环的主表键命名恰好不统一（H10 无 sheet 尾码、"
            "H5 是前缀拼接、H7 内联在 Tab）",
        scope_check=_entry_field(
            E_H2, "html_counterpart", "primary_table", "owner_constant", "ROWS_KEY_V2"
        ),
        tags=("counterpart", "data"),
    ),
    Mutation(
        id="M19", side="be", path=SLICE, kind="replace",
        anchor='            "xlsx/gt-h6-asset-disposal-clearing",',
        new='            "xlsx/gt-h3-investment-property",',
        want=f"{_HTML}::test_write_carrier_families_cover_every_entry_exactly_once",
        why="HD-1 的写载体分族摘要与逐 entry 声明脱节仍绿 ⇒ 「三族覆盖每条 entry 恰好一次」"
            "退化成一句自述（D 循环的 slice 曾出现摘要写 0 个而明细 7 个的同型缺陷）",
        scope_check=_json_at(
            ["xlsx/gt-h2-construction-in-progress", "xlsx/gt-h3-investment-property",
             "xlsx/gt-h8-right-of-use-assets", "xlsx/gt-h9-lease-liabilities"],
            "h_cycle_form_differences", "differences", 0, "entries_by_family", "host_inline",
        ),
        tags=("counterpart", "data"),
    ),
    Mutation(
        id="M20", side="be", path=SLICE, kind="replace",
        scope='        "entries_by_read_carrier": {', offset=1,
        anchor='          "formdata_composable": [',
        new='          "formdata_composable_v2": [',
        want=f"{_HTML}::test_read_carrier_families_cover_every_entry_exactly_once",
        why="HD-2 的读路径分族键改名仍绿 ⇒ 摘要与明细的等值比对没在跑；本条同时证明分族判据"
            "认的是**键与成员的整体等值**而不是「成员数量对得上」",
        scope_check=_json_at(
            ["xlsx/gt-h3-investment-property", "xlsx/gt-h4-engineering-materials",
             "xlsx/gt-h10-asset-disposal-income"],
            "h_cycle_form_differences", "differences", 1, "entries_by_read_carrier",
            "formdata_composable_v2",
        ),
        tags=("counterpart", "data"),
    ),
    Mutation(
        id="M21", side="be", path=SLICE, kind="replace",
        anchor='              "client": "api",',
        new='              "client": "http",',
        want=f"{_HTML}::test_h7_second_write_path_is_real",
        why="H7 是全 slice 唯一「两个写路径 × 两个不同 HTTP 客户端」的 entry；把两条写成同一个"
            "客户端仍绿 ⇒ 「两个客户端确实不同」这条判据空转，step 6 的 contract 会漏掉一半"
            "写路径",
        scope_check=_json_at(
            "http", "independent_entries", 5, "html_counterpart", "second_write_path",
            "paths", 0, "client",
        ),
        tags=("counterpart", "data"),
    ),
    Mutation(
        id="M22", side="be", path=SLICE, kind="replace",
        anchor='          "kind": "localStorage_draft_fallback",',
        new='          "kind": "localStorage_draft_v2",',
        want=f"{_HTML}::test_h10_third_client_side_store_is_declared_and_unique",
        why="H10 的第三处存储（localStorage 草稿）种类改名仍绿 ⇒ 「特例不得当通例」的判据"
            "（其余 8 条载体里不得出现 draft 形态）失去锚点",
        scope_check=_json_at(
            "localStorage_draft_v2", "independent_entries", 8, "html_counterpart",
            "extra_client_store", "kind",
        ),
        tags=("counterpart", "data"),
    ),
    Mutation(
        id="M23", side="be", path=SLICE, kind="replace",
        anchor='              "primary_table": "H3-2-cost-rows",',
        new='              "primary_table": "H3-2-cost-rows-v2",',
        want=f"{_HTML}::test_measurement_variants_are_real_sheets_with_separate_owners",
        why="双计量模式（H3/H7）某个 variant 的主表键与 owner 模块不符仍绿 ⇒ 「两套 sheet 各有"
            "独立键与独立 owner」这条判据空转，contract 抄单模式形态就会漏掉一半 sheet",
        scope_check=_json_at(
            "H3-2-cost-rows-v2", "independent_entries", 1, "html_counterpart",
            "measurement_variant", "variants", 0, "primary_table",
        ),
        tags=("counterpart", "data"),
    ),
    Mutation(
        id="M24", side="be", path=SLICE, kind="replace",
        anchor='        "row_identity_generator_source": "audit-platform/frontend/src/components/'
               'workpaper/composables/useH2Detail.ts#L260",',
        new='        "row_identity_generator_source": "audit-platform/frontend/src/components/'
            'workpaper/composables/useH2Detail.ts#L1",',
        want=f"{_P23}::test_every_entry_declares_its_identity_key_and_generator",
        why="行身份生成器行号指向一行看不出生成来源的代码仍绿 ⇒ 9 个生成点的 source-backed 判据"
            "只验「文件存在」，不验「那一行真是生成器」",
        scope_check=_entry_field(
            E_H2, "html_counterpart", "row_identity_generator_source",
            "audit-platform/frontend/src/components/workpaper/composables/useH2Detail.ts#L1",
        ),
        tags=("property23", "data"),
    ),

    # ═══════════════════════════════════════════════════════════════════════
    # ③ Property 22：动态列 key 与 label 解耦（H7 稳定 key 范式 —— 任务正文第一条要求）
    # ═══════════════════════════════════════════════════════════════════════
    Mutation(
        id="M25", side="be", path=H7_LISTED, kind="replace",
        anchor="    key: `${ind.key}_1`,",
        new="    key: ind.label,",
        want=f"{_P22}::test_sk1_column_key_and_label_are_separate_fields",
        wants=(f"{_P22}::test_label_as_key_hits_are_exactly_the_declared_deviations",),
        why="SK-1 被破坏：默认列的 key 直接取 label 仍绿 ⇒ 「key 与 label 解耦」退化成"
            "「interface 里有两个字段」这种声明级判据。源模板四个产业的默认叶子列名都是同一个"
            "字面 `类别`，用 label 作 key 必然四列撞成一列 —— 这正是 H7 范式存在的原因",
        scope_check=_text_all("    key: ind.label,"),
        tags=("property22", "source"),
    ),
    Mutation(
        id="M26", side="be", path=H7_LISTED, kind="replace",
        anchor="  return `${prefix}${max + 1}`",
        new="  return `${prefix}${keys.length + 1}`",
        want=f"{_P22}::test_sk2_next_key_takes_max_plus_one_and_never_reuses",
        why="SK-2 被破坏：序号取 `length + 1` 而非 `max + 1` 仍绿 ⇒ 删掉中间一列再新增会复用"
            "已删序号，历史金额串到新列（判据必须同时拦 `length + 1` 与 `${i}` 两种写法）",
        scope_check=_text_all("  return `${prefix}${keys.length + 1}`"),
        tags=("property22", "source"),
    ),
    Mutation(
        id="M27", side="be", path=H7_SOE, kind="replace",
        anchor="  return `${prefix}${max + 1}`",
        new="  return `${prefix}${list.length + 1}`",
        want=f"{_P22}::test_sk2_next_key_takes_max_plus_one_and_never_reuses",
        why="同 M26 但打在**国企侧**同形实现上 —— 判据是对两个模块循环的，只变异上市侧无法"
            "证明国企侧那份也在分母里（漏掉一侧 = 半个判据）",
        scope_check=_text_all("  return `${prefix}${list.length + 1}`"),
        tags=("property22", "source"),
    ),
    Mutation(
        id="M28", side="be", path=H7_LISTED, kind="replace",
        anchor="  return categories.reduce((s, c) => s + h7CellValue(map, def, c.key, rows), 0)",
        new="  return h7CellValue(map, def, 'agriculture_1', rows)",
        want=f"{_P22}::test_sk3_total_column_reduces_over_the_dynamic_array",
        why="SK-3 被破坏：合计列不再对动态 categories 数组 reduce，而是对写死的一个列 key 求和"
            " ⇒ 任务正文明禁的「硬编码列数」以最隐蔽的形态回来（列数不在类型里、在求和式里）",
        scope_check=_text_all("  return h7CellValue(map, def, 'agriculture_1', rows)"),
        tags=("property22", "source", "no-hardcode"),
    ),
    Mutation(
        id="M29", side="be", path=H7_LISTED, kind="insert",
        anchor="export const H7_COST_MOVEMENT_ROWS: H7MovementRowDef[] = [",
        new="  ...blankRows(baseRows, 3),",
        want=f"{_P22}::test_sk4_row_model_is_a_declarative_array_not_fixed_blank_rows",
        why="SK-4 被破坏：注入一处 `blankRows(expr, 整数字面量)` 仍绿 ⇒ 任务正文明禁的"
            "「硬编码行数」扫描是空跑的。预置空占位行会被推成占位披露行（平台已有前例）",
        scope_check=_text_all("  ...blankRows(baseRows, 3),"),
        tags=("property22", "source", "no-hardcode"),
    ),
    Mutation(
        id="M30", side="be", path=H7_LISTED, kind="insert",
        anchor="export const H7_FAIR_MOVEMENT_ROWS: H7MovementRowDef[] = [",
        new="  { key: '公司1', label: '公司1', kind: 'data' },",
        want=f"{_P22}::test_no_hardcoded_horizontal_company_columns",
        why="注入一处 `'公司1'` 横向展开列字面量仍绿 ⇒ 任务正文明禁的「按公司/单位横向展开写死"
            "列名」扫描是空跑的（H7 范式的整个存在意义就是把这种列改成动态 + 稳定 key）",
        scope_check=_text_all("  { key: '公司1', label: '公司1', kind: 'data' },"),
        tags=("property22", "source", "no-hardcode"),
    ),
    Mutation(
        id="M31", side="be", path=SLICE, kind="replace",
        anchor='        "column_key_is_label": 1,',
        new='        "column_key_is_label": 2,',
        want=f"{_P22}::test_label_as_key_hits_are_exactly_the_declared_deviations",
        why="穷举扫描的声明值被改大仍绿 ⇒ 「实测命中必须恰好等于声明」退化成单向判据，"
            "凭空多登记一处背离（或漏登记）都不会被发现",
        scope_check=_json_at(
            2, "dynamic_column_identity", "hardcoded_scan_result", "patterns",
            "column_key_is_label",
        ),
        tags=("property22", "data"),
    ),
    Mutation(
        id="M32", side="be", path=H8_PAYLOAD, kind="replace",
        anchor="      ...cats.map((c) => ({ key: c.label, label: c.label, "
               "format: 'amount' as const })),",
        new="      ...cats.map((c) => ({ key: c.key, label: c.label, "
            "format: 'amount' as const })),",
        want=f"{_P22}::test_label_as_key_hits_are_exactly_the_declared_deviations",
        why="**反方向**变异：把 BP-7 那处背离真修好（label→key）而不删登记 ⇒ 实测 0 条 ≠ 声明"
            " 1 条也必须打红。只验「多一处」不验「少一处」是半个穷举判据：已修好的缺陷会以"
            "登记的形式永久留在 slice 里，读者以为平台还有这个缺陷",
        scope_check=_text_all(
            "      ...cats.map((c) => ({ key: c.key, label: c.label, format: 'amount' as const })),"
        ),
        tags=("property22", "source", "reverse"),
    ),
    Mutation(
        id="M33", side="be", path=H8_DISCLOSURE, kind="replace",
        anchor="    const key = `cat_${Date.now().toString(36)}`",
        new="    const key = label",
        want=f"{_P22}::test_h8_deviation_is_reachable_from_user_input",
        why="底稿内的类别 key 从稳定串改成用户输入的 label 仍绿 ⇒ BP-7 的 scope_note"
            "（「只影响同步边界、底稿内一直按 c.key」）失去承载者，缺陷范围的描述就变成了猜测",
        scope_check=_text_all("    const key = label"),
        tags=("property22", "source"),
    ),
    Mutation(
        id="M34", side="be", path=SLICE, kind="replace",
        anchor='        "registered_as": "BP-7"',
        new='        "registered_as": "BP-99"',
        want=f"{_P22}::test_label_as_key_hits_are_exactly_the_declared_deviations",
        why="背离条目指向一个不存在的阻断项仍绿 ⇒ 「查出来的形态缺陷已阻断 bidirectional」"
            "这条链断在中间而没人发现",
        scope_check=_json_at(
            "BP-99", "dynamic_column_identity", "deviations", 0, "registered_as"
        ),
        tags=("property22", "data"),
    ),

    # ═══════════════════════════════════════════════════════════════════════
    # ④ Property 23：动态行身份不使用下标（三族划分 + 反向自检）
    # ═══════════════════════════════════════════════════════════════════════
    Mutation(
        id="M35", side="be", path=SLICE, kind="replace",
        scope=S_H2, offset=50,
        anchor='        "row_identity_key": "rowId",',
        new='        "row_identity_key": "id",',
        want=f"{_P23}::test_dynamic_row_identity_tables_cover_every_entry",
        wants=(f"{_P23}::test_every_entry_declares_its_identity_key_and_generator",),
        why="身份字段名声明错了仍绿 ⇒ H 循环两族身份字段（rowId 八条 / H10 是 id）的判据可以"
            "写死任一族而不被发现，另一族会被整体判成缺身份",
        scope_check=_entry_field(E_H2, "html_counterpart", "row_identity_key", "id"),
        tags=("property23", "data"),
    ),
    Mutation(
        id="M36", side="be", path=SLICE, kind="replace",
        anchor='      "total_hits": 17,',
        new='      "total_hits": 18,',
        want=f"{_P23}::test_positional_identity_inventory_is_exhaustive_and_partitioned",
        why="位置化命中总数被改大仍绿 ⇒ 「新增第 18 条不会被发现」，而这份清单正是 BP-6 的分母",
        scope_check=_json_at(
            18, "dynamic_row_identity", "positional_identity_inventory", "total_hits"
        ),
        tags=("property23", "data"),
    ),
    Mutation(
        id="M37", side="be", path=SLICE, kind="replace",
        anchor='        "count": 3,',
        new='        "count": 4,',
        want=f"{_P23}::test_positional_identity_inventory_is_exhaustive_and_partitioned",
        why="family_a（真缺陷族）的条数与 hits 数组脱节仍绿 ⇒ 三族划分退化成三个自述数字，"
            "「只有 family_a 是真缺陷」这个结论无从核对",
        scope_check=_json_at(
            4, "dynamic_row_identity", "positional_identity_inventory",
            "family_a_true_defect_primary_table_seed", "count",
        ),
        tags=("property23", "data"),
    ),
    Mutation(
        id="M38", side="be", path=SLICE, kind="replace",
        anchor='            "writes_to_key": "H2-2-rows",',
        new='            "writes_to_key": "H2-99-rows",',
        want=f"{_P23}::test_family_a_hits_write_to_the_declared_key",
        why="位置化身份「写进哪个键」写错仍绿 ⇒ 无法区分 H2/H4（写进 primary managed table，"
            "真错位风险）与 H8（写进零消费键，当下无后果但一修 BP-5 就变真缺陷）两种性质",
        scope_check=_json_at(
            "H2-99-rows", "dynamic_row_identity", "positional_identity_inventory",
            "family_a_true_defect_primary_table_seed", "hits", 0, "writes_to_key",
        ),
        tags=("property23", "data"),
    ),
    Mutation(
        id="M39", side="be", path=HOST_H2, kind="replace",
        anchor="    rowId: `seed-${i}`,",
        new="    rowId: `seed-${crypto.randomUUID()}`,",
        want=f"{_P23}::test_positional_identity_inventory_is_exhaustive_and_partitioned",
        wants=(f"{_P23}::test_family_a_hits_write_to_the_declared_key",),
        why="**反方向**变异：把已登记的 H2 种子行身份真改成非位置化 ⇒ 实测 16 条 ≠ 声明 17 条"
            "也必须打红。与 M36 合起来把「穷举等值」的两个方向都锁死",
        scope_check=_text_all("    rowId: `seed-${crypto.randomUUID()}`,"),
        tags=("property23", "source", "reverse"),
    ),
    Mutation(
        id="M40", side="be", path=SLICE, kind="replace",
        anchor='          "audit-platform/frontend/src/components/workpaper/composables/'
               'useH3DetailCost.ts#L142(seq: raw.seq ?? idx + 1)",',
        new='          "audit-platform/frontend/src/components/workpaper/'
            'GtH2ConstructionInProgress.vue#L616",',
        want=f"{_P23}::test_display_sequence_sites_are_not_flagged",
        why="把反向自检的「不得被点名」清单指向一个**真**位置化站点仍绿 ⇒ 该自检恒真，判据"
            "随时可以退回「整行判」的错口径（G 循环在 G12 上踩过：`seq: raw.seq ?? idx + 1` 的"
            "整行含位置 token，按整行判会把三条 entry 误判成位置化行身份）",
        scope_check=_json_at(
            "audit-platform/frontend/src/components/workpaper/GtH2ConstructionInProgress.vue#L616",
            "dynamic_row_identity", "positional_identity_inventory", "false_positive_guard",
            "must_not_be_flagged", 0,
        ),
        tags=("property23", "data", "reverse"),
    ),
    Mutation(
        id="M41", side="be", path=SLICE, kind="replace",
        scope='        "persistence_key": "H2-2-rows",', offset=2,
        anchor='          "kind": "generated_opaque_string_with_prefill_array_index_seed",',
        new='          "kind": "array_index",',
        want=f"{_P23}::test_dynamic_row_identity_tables_cover_every_entry",
        wants=(f"{_P23}::test_positional_seed_entries_match_the_summary_counter",),
        why="把 row_identity.kind 直接写成 forbidden_identity_kinds 里的 array_index 仍绿 ⇒ "
            "conditional section 声明的禁用身份种类清单是死数据，没有任何判据在读它",
        scope_check=_json_at(
            "array_index", "dynamic_row_identity", "tables", 0, "row_identity", "kind"
        ),
        tags=("property23", "data"),
    ),

    # ═══════════════════════════════════════════════════════════════════════
    # ⑤ BP-5（零消费种子键）/ BP-8（孤儿与错位 legacy 载体）
    # ═══════════════════════════════════════════════════════════════════════
    Mutation(
        id="M42", side="be", path=SLICE, kind="replace",
        anchor='          "key": "H8-2-detail-prefill",',
        new='          "key": "H8-2-rows",',
        want=f"{_SEED}::test_h8_real_primary_key_is_a_different_literal",
        wants=(f"{_SEED}::test_h8_seed_key_has_exactly_one_occurrence_in_the_repo",),
        why="把孤儿种子键写成与主表键相同仍绿 ⇒ BP-5 的前提（种子键 != 主表键）自我消解，"
            "「结构性死代码」这个结论失去可复核的分母",
        scope_check=_entry_field(
            E_H8, "html_counterpart", "orphan_seed_key", "key", "H8-2-rows"
        ),
        tags=("bp5", "data"),
    ),
    Mutation(
        id="M43", side="be", path=H8_DETAIL, kind="insert",
        anchor="const ROWS_KEY = 'H8-2-rows'",
        new="const ORPHAN_SEED_KEY = 'H8-2-detail-prefill'",
        want=f"{_SEED}::test_h8_seed_key_has_exactly_one_occurrence_in_the_repo",
        why="给零消费键加一个引用点仍绿 ⇒ 「某个键零消费」这件事是写死的「只有 1 处」而不是"
            "现扫复算，将来有人真接上消费方（BP-5 该解除）也不会提醒任何人",
        scope_check=_text_all("const ORPHAN_SEED_KEY = 'H8-2-detail-prefill'"),
        tags=("bp5", "source"),
    ),
    Mutation(
        id="M44", side="be", path=PRESETS, kind="insert",
        anchor="def tier_b_provenance(wp_code: str) -> list[dict]:",
        new='    _H8_LEGACY_ANCHOR = "H8-2-detail-prefill"',
        want=f"{_SEED}::test_backend_preset_anchor_points_at_the_real_key_not_the_orphan",
        why="后端 preset 里出现孤儿键仍绿 ⇒ BP-5 的第 2 条可观察后果（后端登记的取数锚点与前端"
            "实际写入的键不一致）没有承载者，两侧口径漂移不会被发现",
        scope_check=_text_all('    _H8_LEGACY_ANCHOR = "H8-2-detail-prefill"'),
        tags=("bp5", "source"),
    ),
    Mutation(
        id="M45", side="be", path=SLICE, kind="replace",
        anchor='          "audit-platform/frontend/src/components/workpaper/'
               'GtH2ConstructionInProgress.vue"',
        new='          "audit-platform/frontend/src/components/workpaper/'
            'GtH3InvestmentProperty.vue"',
        want=f"{_ORPHAN}::test_declared_dual_mode_consumers_match_the_source",
        why="legacy composable 的消费方清单与实测不符仍绿 ⇒ BP-8 的两侧断言只剩一侧"
            "（「声称零消费的真零」而不查「声称有消费方的真有」），删除时会打断在用的入口",
        scope_check=_entry_field(
            E_H2, "legacy_dual_mode", "consumers",
            ["audit-platform/frontend/src/components/workpaper/GtH3InvestmentProperty.vue"],
        ),
        tags=("bp8", "data"),
    ),
    Mutation(
        id="M46", side="be", path=SLICE, kind="replace",
        scope=S_H2, offset=94,
        anchor='        "host_consumes_it": true,',
        new='        "host_consumes_it": false,',
        want=f"{_ORPHAN}::test_declared_dual_mode_consumers_match_the_source",
        wants=(
            f"{_SRC}::test_hosts_still_import_their_legacy_composable_or_inline_it",
            f"{_P69}::test_summary_counters_are_recomputed_from_entries",
        ),
        why="宿主是否消费 legacy 声明反了仍绿 ⇒ 「4 个宿主内联了第二份实现」这个 H 循环特有形态"
            "无法与「宿主真用 composable」区分，step 9 会把 adapter 挂到没人调用的 composable 上",
        scope_check=_entry_field(E_H2, "legacy_dual_mode", "host_consumes_it", False),
        tags=("bp8", "data"),
    ),
    Mutation(
        id="M47", side="be", path=SLICE, kind="replace",
        anchor='        "module": "audit-platform/frontend/src/components/workpaper/composables/'
               'useH6FormData.ts",',
        new='        "module": "audit-platform/frontend/src/components/workpaper/composables/'
            'useH3FormData.ts",',
        want=f"{_ORPHAN}::test_non_orphan_formdata_composables_are_not_registered_as_orphans",
        wants=(
            f"{_ORPHAN}::test_declared_orphan_formdata_composables_really_have_no_production_consumer",
        ),
        why="把**真载体** useH3FormData 登记成孤儿仍绿 ⇒ 反向判据失守，Task 72 会删掉在用的"
            "持久化通道（H 循环 9 条 entry 里 4 条的 FormData 是真载体、4 条是孤儿，只差一个"
            "文件名）",
        scope_check=_entry_field(
            E_H6, "orphan_formdata_composable", "module",
            "audit-platform/frontend/src/components/workpaper/composables/useH3FormData.ts",
        ),
        tags=("bp8", "data"),
    ),
    Mutation(
        id="M48", side="be", path=PLAN, kind="replace",
        anchor='    "remaining_consumers_after_h_cycle": 30,',
        new='    "remaining_consumers_after_h_cycle": 29,',
        want=f"{_ORPHAN}::test_shared_base_is_preserved_with_its_real_consumer_count",
        why="共享基类的剩余消费方数写错仍绿 ⇒ legacy_deletion_paradigm 的 shared_base_preserved"
            " 约束（被其他非 H 模块使用的共享基类不删）失去可复核的分母",
        scope_check=_json_at(29, "shared_base_preserved", "remaining_consumers_after_h_cycle"),
        tags=("bp8", "data"),
    ),
    Mutation(
        id="M49", side="be", path=PLAN, kind="replace",
        anchor='        "inline_mode_state": "audit-platform/frontend/src/components/workpaper/'
               'GtH5OilGasAssets.vue#L381",',
        new='        "inline_mode_state": "audit-platform/frontend/src/components/workpaper/'
            'GtH5OilGasAssets.vue#L1",',
        want=f"{_ORPHAN}::test_host_inlined_second_implementation_is_real",
        why="宿主内联实现的行号指向一行不是 `currentMode = ref<>` 的代码仍绿 ⇒ Task 72 的验收"
            "判据会退回「composable 文件已删除」，而那对这 4 条 entry 恒真（本来就没人用它）",
        scope_check=_json_at(
            "audit-platform/frontend/src/components/workpaper/GtH5OilGasAssets.vue#L1",
            "host_inlined_second_implementation", "hosts", 0, "inline_mode_state",
        ),
        tags=("bp8", "data"),
    ),

    # ═══════════════════════════════════════════════════════════════════════
    # ⑥ Property 28：immutable definition 漂移 fail closed（真分母）
    # ═══════════════════════════════════════════════════════════════════════
    Mutation(
        id="M50", side="be", path=SLICE, kind="replace",
        anchor='        "sha256": "de9426a33e8d51e9351c8dd2393fe8502433d2cf810f30318f254a474ec480fe",',
        new='        "sha256": "de9426a33e8d51e9351c8dd2393fe8502433d2cf810f30318f254a474ec480ff",',
        want=f"{_P28}::test_authoritative_templates_digests_recompute",
        why="模板 sha256 漂移一位仍绿 ⇒ Requirement 6.10 的 fail closed 只是登记了 digest 而"
            "从不现算，「权威模板未被为满足数字修改过」（AP-2）无从证明",
        scope_check=_template_field(
            "H2 在建工程.xlsx", "sha256",
            "de9426a33e8d51e9351c8dd2393fe8502433d2cf810f30318f254a474ec480ff",
        ),
        tags=("property28", "data"),
    ),
    Mutation(
        id="M51", side="be", path=SLICE, kind="replace",
        anchor='        "normalized_structure_hash": '
               '"15f530571527da67d6770cb838536866840ca329d59427ce0995542afa04ebdb",',
        new='        "normalized_structure_hash": '
            '"15f530571527da67d6770cb838536866840ca329d59427ce0995542afa04ebdc",',
        want=f"{_P28}::test_normalized_structure_hash_recomputes",
        why="normalized_structure_hash 漂移仍绿 ⇒ 该字段没有被生产实现"
            "（excel_instrumentation.normalized_structure_hash）现算过，instrumentation 的"
            "结构等值判据从此只是一串装饰",
        scope_check=_template_field(
            "H2 在建工程.xlsx", "normalized_structure_hash",
            "15f530571527da67d6770cb838536866840ca329d59427ce0995542afa04ebdc",
        ),
        tags=("property28", "data"),
    ),
    Mutation(
        id="M52", side="be", path=SLICE, kind="replace",
        anchor='        "belongs_to_entry": "xlsx/gt-h2-construction-in-progress"',
        new='        "belongs_to_entry": "xlsx/gt-h3-investment-property"',
        want=f"{_P28}::test_template_owner_mapping_is_a_bijection_over_the_entries",
        why="模板归属出现一对多仍绿 ⇒ H 循环「一册对一 entry」这个比 F/G 更强的判据（既单射也"
            "满射）空转，跨 entry 借用模板结论不会被发现（Property 70）",
        scope_check=_template_field(
            "H2 在建工程.xlsx", "belongs_to_entry", "xlsx/gt-h3-investment-property"
        ),
        tags=("property28", "property70", "data"),
    ),
    Mutation(
        id="M53", side="be", path=SLICE, kind="replace",
        scope='        "sha256": "de9426a33e8d51e9351c8dd2393fe8502433d2cf810f30318f254a474ec480fe",',
        offset=2,
        anchor='        "in_runtime_index": true,',
        new='        "in_runtime_index": false,',
        want=f"{_P28}::test_in_runtime_index_flag_recomputes_and_h_has_no_unreachable_workbook",
        why="in_runtime_index 与 `_index.json` 不符仍绿 ⇒ 「11 个文件全部在索引里」这句结论"
            "没有承载者，运行时不可达的工作簿（wp_template_finder 找不到）会被当成可达",
        scope_check=_template_field("H2 在建工程.xlsx", "in_runtime_index", False),
        tags=("property28", "data"),
    ),
    Mutation(
        id="M54", side="be", path=SLICE, kind="replace",
        anchor='    "result": "clean",',
        new='    "result": "dirty",',
        want=f"{_P28}::test_template_resolution_audit_recomputes",
        why="模板解析审计结论被改仍绿 ⇒ 21 条 wp_code 的 find_template_file / _any 实跑判据"
            "空转，F2 那种「子码回落到父级工作簿」的缺陷在 H 循环不会被发现",
        scope_check=_json_at("dirty", "template_resolution_audit", "result"),
        tags=("property28", "data"),
    ),

    # ═══════════════════════════════════════════════════════════════════════
    # ⑦ Property 69：selection_rule 现算 / 18 个计数现算 / evidence 蕴含关系
    # ═══════════════════════════════════════════════════════════════════════
    Mutation(
        id="M55", side="be", path=SLICE, kind="replace",
        anchor='    "independent_entry_count": 9,',
        new='    "independent_entry_count": 10,',
        want=f"{_P69}::test_slice_scope_is_recomputable_from_the_manifest",
        why="slice 的 entry 计数与 selection_rule 现算不符仍绿 ⇒ 「多写一条（凑数）或少写一条"
            "（漏迁）都红」这条 step 1 的核心判据失守",
        scope_check=_json_at(10, "slice_scope", "independent_entry_count"),
        tags=("property69", "data"),
    ),
    Mutation(
        id="M56", side="be", path=SLICE, kind="replace",
        anchor='    "total_independent": 9,',
        new='    "total_independent": 8,',
        want=f"{_P69}::test_summary_counters_are_recomputed_from_entries",
        wants=(f"{_PARA}::test_the_slice_passes_the_paradigm_nominated_validator",),
        why="摘要总数与明细脱节仍绿 ⇒ SR-1（total_independent == len(entries) =="
            " slice_scope.independent_entry_count）没在跑，18 个计数全变成手填数字",
        scope_check=_json_at(8, "honest_adjudication_summary", "total_independent"),
        tags=("property69", "data"),
    ),
    Mutation(
        id="M57", side="be", path=SLICE, kind="replace",
        scope=S_H3, offset=139,
        anchor='        "verification_state": "UNVERIFIABLE",',
        new='        "verification_state": "VERIFIED",',
        want=f"{_P69}::test_evidence_state_and_reasons",
        wants=(
            f"{_P69}::test_no_entry_claims_verified_without_a_test_run",
            f"{_P69}::test_summary_counters_are_recomputed_from_entries",
        ),
        why="空口声称 VERIFIED（无 sync_test_run_id / 无 required_scenario_set_digest）仍绿 ⇒ "
            "AC 12.12 与 BP-4 的「真实 OO 未跑就只能是 UNVERIFIABLE」失守，假验收从此可通行",
        scope_check=_entry_field(E_H3, "evidence", "verification_state", "VERIFIED"),
        tags=("property69", "data"),
    ),
    Mutation(
        id="M58", side="be", path=SLICE, kind="replace",
        anchor='      "status": "PARTIALLY_FIXED_AC_1_4_DONE",',
        new='      "status": "FIXED",',
        want=f"{_P69}::test_blocking_preconditions_are_complete",
        why="阻断项状态填一个未登记的值仍绿 ⇒ 10 条阻断项的完整性判据（编号连续 + 六个必填字段"
            " + 后果二形态之一 + source_refs 真实存在）整体空转，「已修好」可以随口宣称",
        scope_check=_json_at("FIXED", "blocking_preconditions", 9, "status"),
        tags=("property69", "data"),
    ),
    Mutation(
        id="M59", side="be", path=SLICE, kind="replace",
        anchor='        "entry_id": "xlsx/h4/impairment/h4-tab-impairment",',
        new='        "entry_id": "xlsx/h4/impairment/h4-tab-ghost",',
        want=f"{_P69}::test_parent_duplicate_children_are_registered_and_disjoint",
        why="parent_duplicate 子入口登记与 manifest 现算不等仍绿 ⇒ AC 1.6（子入口复用父 entry 的"
            " adapter、不独立计数）失去承载者，H4/H8 的 5 条子入口可以凭空增删",
        scope_check=_json_at(
            "xlsx/h4/impairment/h4-tab-ghost", "parent_duplicate_summary", "children", 0,
            "entry_id",
        ),
        tags=("property69", "data"),
    ),
    Mutation(
        id="M60", side="be", path=SLICE, kind="replace",
        anchor='        "id": "HD-6",',
        new='        "id": "HD-7",',
        want=f"{_P69}::test_form_difference_block_is_complete",
        why="形态差异登记的编号断档仍绿 ⇒ 「H 循环与 F/G 的六处不同」这份清单可以被悄悄删条，"
            "而判据逐 entry 从它取分族真源",
        scope_check=_json_at("HD-7", "h_cycle_form_differences", "differences", 5, "id"),
        tags=("property69", "data"),
    ),

    # ═══════════════════════════════════════════════════════════════════════
    # ⑧ Property 70：不得跨 entry / 跨 slice 复用
    # ═══════════════════════════════════════════════════════════════════════
    Mutation(
        id="M61", side="be", path=SLICE, kind="replace",
        anchor='    "backend/data/workpaper_sync_g_cycle_manifest_slice.json"',
        new='    "backend/data/workpaper_sync_x_cycle_manifest_slice.json"',
        want=f"{_P70}::test_h_entries_disjoint_from_the_four_sibling_slices",
        why="兄弟 slice 清单指向一个不存在的文件仍绿 ⇒ 「与 D/E/F/G 四份 slice 两两不相交」的"
            "分母可以被悄悄换掉，跨 slice 重复计数不会被发现",
        scope_check=_json_at(
            "backend/data/workpaper_sync_x_cycle_manifest_slice.json", "sibling_slices", 3
        ),
        tags=("property70", "data"),
    ),
    Mutation(
        id="M62", side="be", path=SLICE, kind="replace",
        scope=S_H2, offset=118,
        anchor='        "contract_test": "backend/tests/workpaper_sync/'
               'test_task50_h_cycle_migration.py",',
        new='        "contract_test": "backend/tests/workpaper_sync/'
            'test_task49_g_cycle_migration.py",',
        want=f"{_P69}::test_contract_test_points_at_this_file",
        why="evidence.contract_test 指向**别的循环**的守卫文件仍绿 ⇒ Property 70 最典型的形态"
            "（借用别人的 evidence 承载者）不会被发现",
        scope_check=_entry_field(
            E_H2, "evidence", "contract_test",
            "backend/tests/workpaper_sync/test_task49_g_cycle_migration.py",
        ),
        tags=("property70", "data"),
    ),
    Mutation(
        id="M63", side="be", path=PLAN, kind="replace",
        anchor='          "lines": 157,',
        new='          "lines": 156,',
        want=f"{_P70}::test_deletion_plan_composables_are_distinct_and_real",
        why="待删文件的行数声明与磁盘不符仍绿 ⇒ deletion plan 的 13 个 composable 只被验了"
            "「文件存在」，「删的就是登记的那一份」无从证明",
        scope_check=_json_at(156, "entries", 0, "legacy_composables_to_delete", 0, "lines"),
        tags=("property70", "data"),
    ),
    Mutation(
        id="M64", side="be", path=H1_CONTRACT, kind="replace",
        anchor='    "entry_id": "xlsx/gt-h1-fixed-assets",',
        new='    "entry_id": "xlsx/gt-h2-construction-in-progress",',
        want=f"{_P20}::test_no_slice_entry_has_a_contract_and_h1_is_the_only_h_contract",
        why="**正向**核验：把同循环 pilot 契约的归属改到本 slice 的 entry 上仍绿 ⇒ Property "
            "20/21「分母为空」的前提（本 slice 9 条 entry 的 contract 数 = 0）没人守，而"
            " h1.disposal_check 正是最容易被误借的那一份（同循环、同类型）",
        scope_check=_json_at("xlsx/gt-h2-construction-in-progress", "review", "entry_id"),
        tags=("property20", "data"),
    ),

    # ═══════════════════════════════════════════════════════════════════════
    # ⑨ AC 1.4：诚实的模式可见性（step 11 —— 裁决自带的 UI 义务）
    # ═══════════════════════════════════════════════════════════════════════
    Mutation(
        id="M65", side="be", path=NOTICE_VUE, kind="replace",
        anchor='      <span class="entry-sync-notice__summary">{{ notice.summary }}</span>',
        new='      <span class="entry-sync-notice__summary">详情</span>',
        want=f"{_AC14}::test_notice_component_renders_summary_and_binds_entry_id",
        why="常显摘要从模板里消失（原因只剩 hover 才出现的 tooltip）仍绿 ⇒ AC 1.4 的"
            "「显示可操作原因」退化成默认看不见（EP tooltip 内容是 teleport 出去的，"
            "不 hover 根本不在 DOM 里）",
        scope_check=_text_all('__summary">详情</span>'),
        tags=("ac14", "source"),
    ),
    Mutation(
        id="M66", side="be", path=NOTICE_VUE, kind="replace",
        anchor='    :data-entry-sync-notice="props.entryId"',
        new='    data-entry-sync-notice="static"',
        want=f"{_AC14}::test_notice_component_renders_summary_and_binds_entry_id",
        why="entry-id 的 DOM 绑定退化成静态串仍绿 ⇒ DOM 级判据失去锚点，无法证明「用户看到的"
            "那条原因属于当前 entry」（抄别的 entry 也不会被发现）",
        scope_check=_text_all('data-entry-sync-notice="static"'),
        tags=("ac14", "source"),
    ),
    Mutation(
        id="M67", side="be", path=HOST_H4, kind="replace",
        anchor='        <GtEntrySyncCapabilityNotice '
               'entry-id="xlsx/gt-h4-engineering-materials" />',
        new='        <GtEntrySyncCapabilityNotice '
            'entry-id="xlsx/gt-h2-construction-in-progress" />',
        want=f"{_AC14}::test_every_pending_entry_host_mounts_the_notice",
        wants=(f"{_AC14}::test_notice_mount_sits_inside_the_declared_mode_toolbar",),
        why="宿主把通知绑到**别的 entry** 的 id 上仍绿 ⇒ 9 个宿主可以互相抄挂载点，"
            "「显示可操作原因」变成显示别人的原因",
        scope_check=_text_all(
            '<GtEntrySyncCapabilityNotice entry-id="xlsx/gt-h2-construction-in-progress" />'
        ),
        tags=("ac14", "source"),
    ),
    Mutation(
        id="M68", side="be", path=SLICE, kind="replace",
        anchor='      "ui_toolbar_gate": "class=\\"h2-header-toolbar\\"",',
        new='      "ui_toolbar_gate": "class=\\"loading-container\\"",',
        want=f"{_AC14}::test_notice_mount_sits_inside_the_declared_mode_toolbar",
        why="把工具栏门控锚点指向模板里**另一个**区块仍绿 ⇒ 「通知在声明的工具栏区块内」这条"
            "判据空转（H 循环 9 个宿主的工具栏 class 与门控表达式逐个不同，写死任一种都会让"
            "其余判据静默恒真）",
        scope_check=_entry_field(E_H2, "ui_toolbar_gate", 'class="loading-container"'),
        tags=("ac14", "data"),
    ),
    Mutation(
        id="M69", side="be", path=NOTICE_TS, kind="replace",
        anchor="export const SYNC_ADAPTER_REGISTERED_ENTRY_IDS: readonly string[] = []",
        new="export const SYNC_ADAPTER_REGISTERED_ENTRY_IDS: readonly string[] = "
            "['xlsx/gt-h2-construction-in-progress']",
        want=f"{_AC14}::test_registered_entry_ids_agree_with_the_slice",
        why="前端通知真源声称某 entry 已注册 adapter 而 slice 的 adapter_id 仍为 null 仍绿 ⇒ "
            "AC 1.4 的「未注册 adapter 不得显示可双向回写」被前端单方面绕过（双口径）",
        scope_check=_text_all("['xlsx/gt-h2-construction-in-progress']"),
        tags=("ac14", "source"),
    ),
    Mutation(
        id="M70", side="be", path=HOST_H4, kind="insert",
        anchor='        <GtEntrySyncCapabilityNotice '
               'entry-id="xlsx/gt-h4-engineering-materials" />',
        new='        <span class="h4-sync-claim">可双向回写</span>',
        want=f"{_AC14}::test_hosts_do_not_claim_bidirectional_writeback",
        why="宿主模板里出现「可双向回写」文案仍绿 ⇒ AC 1.4 的禁令只是写在文档里，"
            "而这 9 条 entry 一件双向前置都没交付（BP-1..BP-4）",
        scope_check=_text_all('<span class="h4-sync-claim">可双向回写</span>'),
        tags=("ac14", "source"),
    ),
    Mutation(
        id="M71", side="be", path=SLICE, kind="replace",
        scope=S_H2, offset=134,
        anchor='        "audit-platform/frontend/src/components/workpaper/sync/'
               'workpaperEntrySyncNotice.ts"',
        new='        "audit-platform/frontend/src/components/workpaper/sync/'
            'GtEntrySyncCapabilityNotice.vue"',
        want=f"{_AC14}::test_notice_module_is_the_single_source",
        why="ui_gate_source_refs 不再指向文案真源仍绿 ⇒ 「文案/判据一律复用单一真源」的约束"
            "失守，某个宿主抄第二份文案不会被发现",
        scope_check=_entry_field(
            E_H2, "ui_gate_source_refs",
            [
                "audit-platform/frontend/src/components/workpaper/GtH2ConstructionInProgress.vue",
                "audit-platform/frontend/src/components/workpaper/sync/GtEntrySyncCapabilityNotice.vue",
                "audit-platform/frontend/src/components/workpaper/sync/GtEntrySyncCapabilityNotice.vue",
            ],
        ),
        tags=("ac14", "data"),
    ),

    # ═══════════════════════════════════════════════════════════════════════
    # ⑩ 范式合规与源码可达性
    # ═══════════════════════════════════════════════════════════════════════
    Mutation(
        id="M72", side="be", path=SLICE, kind="replace",
        scope='  "properties_verified": [', offset=1,
        anchor="    22,",
        new="    21,",
        want=f"{_PARA}::test_properties_and_requirements_are_declared",
        why="properties_verified 与任务正文点名的 Property 22/23/69/70 不符仍绿 ⇒ slice 可以"
            "声称验了别的 Property（或悄悄删掉一条）而没人核对",
        scope_check=_json_at([21, 23, 69, 70], "properties_verified"),
        tags=("paradigm", "data"),
    ),
    Mutation(
        id="M73", side="be", path=SLICE, kind="replace",
        anchor='    "residual_inconsistency": null,',
        new='    "residual_inconsistency": "范式与 slice 仍有未收口的字段级冲突",',
        want=f"{_PARA}::test_paradigm_conflict_is_registered_and_not_stale",
        why="范式冲突登记从「已收口」改成「仍有残留」而判据仍绿 ⇒ paradigm_schema_conflict "
            "整块变成自述散文，「本 slice 未改范式 JSON / 未扩充 capability_enum」也就无从核对",
        scope_check=_json_at(
            "范式与 slice 仍有未收口的字段级冲突", "paradigm_schema_conflict",
            "residual_inconsistency",
        ),
        tags=("paradigm", "data"),
    ),
    Mutation(
        id="M74", side="be", path=REGISTRY_TS, kind="replace",
        anchor="    component: GtH2ConstructionInProgress,",
        new="    component: GtH3InvestmentProperty,",
        want=f"{_SRC}::test_hosts_exist_and_are_reachable_from_the_renderer_registry",
        why="htmlRendererRegistry 里某宿主的 component 绑定被换掉仍绿 ⇒ 「入口可达」这个"
            "「不裁 unreachable」的前提是按符号名 grep 出来的，而不是按真实入边"
            "（G6 的 GtG6OtherBondEcl 同名局部别名就是这个坑）",
        scope_check=_text_all("    component: GtH3InvestmentProperty,"),
        tags=("source-structure", "source"),
    ),
]

GUARD_FILES = {
    T50: "Task 50 新建（AC 1.3/1.4/12.1/12.8/12.9 裁决合法性、HTML 对端三族写载体 + 五种读"
         "路径 + 三形态传输键的逐 entry 回源核对、Property 22 的 H7 稳定 key 范式四要素正例 +"
         " label-as-key 穷举反例 + 硬编码列数/行数扫描、Property 23 的 9 个行身份构造点 + 17 条"
         "位置化命中三族划分 + 3 条展示序号反向自检、BP-5 零消费种子键现扫、BP-8 孤儿/错位"
         " legacy 载体两侧断言、Property 28 的 11 个模板 digest + 9 个 structure hash + 21 条"
         "模板解析实跑、selection_rule 与 18 个计数现算、deletion plan 与五 slice 不相交、"
         "AC 1.4 的 UI 义务模板形态判据、范式 slice_schema）",
}

if __name__ == "__main__":
    raise SystemExit(
        run_cli(
            mutations=MUTATIONS,
            guard_files=GUARD_FILES,
            repo=REPO,
            description="Task 50 H 循环（除 H1）Excel 独立 entry 迁移守卫变异检验",
            backend_args=[
                "backend/tests/workpaper_sync/test_task50_h_cycle_migration.py",
                "-q",
                "--tb=no",
                "-rfE",
                "-p",
                "no:randomly",
            ],
            baseline_backend_passed=104,
        )
    )
