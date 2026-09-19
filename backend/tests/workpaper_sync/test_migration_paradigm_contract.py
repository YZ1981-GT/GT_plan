# -*- coding: utf-8 -*-
"""`workpaper_sync_migration_paradigm.json` 四个新顶层键的**判据**（消除死数据）。

spec: .kiro/specs/workpaper-html-onlyoffice-bidirectional-writeback-closure/
Requirements: 1.3, 1.4, 1.5, 1.7, 12.1, 12.4, 12.8, 12.9

═══ 为什么存在这个文件 ═══

`backend/data/workpaper_sync_migration_paradigm.json` 在上一轮补出了四个新顶层键
（`paradigm_registry` / `definition_producer_paradigm` / `adjudication_criteria` /
`slice_schema`），但实测**零消费方**：全仓非 JSON 文件里对这三个新键名的引用为 0，
`backend/tests/**/*paradigm*` 与 `backend/scripts/**/*paradigm*` 都不存在。也就是说
新范式、AC 判据、slice schema 全是死数据 —— 平台铁律的「additive 注入即死代码」
（假绿第①源）。本文件就是那个缺失的消费方。

这也不是可选的：JSON 自己把本文件**点名**成检测器与校验器 ——
`adjudication_criteria.anti_patterns[0].detector` 指向
`::TestAntiPatternCircularJustification`，`slice_schema.validator` 指向
`::validate_slice_against_schema`。:class:`TestDeclaredConsumersExist` 反过来锁死这两个
声明：声明里写的符号在本模块里必须真的存在（否则又是一条「声明了但没人实现」的死数据）。

═══ 判据一律落在行为/结构上，不落在「字符串存在」═══

| 守什么 | 判据形态 |
|---|---|
| 步骤拓扑 | 现算 `blocks` 边方向 + DFS 找环（喂合成回边必须被抓） |
| AC 原文 | **现读** requirements.md 磁盘内容逐字 `==`（不是 `in`，见反向自检） |
| slice schema | 两侧断言：正例 = 事实范式 E slice **与 scan_glob 命中的每份 slice** 必须通过；反例 = 逐字段抽掉必须不通过 |
| SR-3 待裁决态 | 蕴含式两支各有正反例：右支正例 = 齐备的 `capability: null`；反例 = 三字段缺任一 / target 不在枚举内 / blocked_by 空数组 / 计数说谎 |
| 旧 `paradigm` | 字节 + canonical 双 digest 与守卫常量**双向**锁死 |
| 反模式 AP-1 | 扫全部 slice 现算违规集合，与 known_debt_inventory 做**子集**比对 |

═══ 存量欠账用 strict xfail，不用 skip ═══

实测 D 循环 slice 7 条 + E 循环 slice 1 条全部裁 `single_onlyoffice` 且都没有
step 3 的二值结论字段 ⇒ :class:`TestAntiPatternCircularJustification` 会打红它们，
**这是预期行为**。处置按 JSON 自己写的 `why_xfail_not_skip`：
`pytest.mark.xfail(strict=True)` —— skip 记为通过是 fail-open；strict 让欠账被清掉后
XPASS 反过来打红，逼作者回来删标记。两个方向都锁死。

数据源（全部现读磁盘，无硬编码副本）::

    backend/data/workpaper_sync_migration_paradigm.json
    backend/data/*_cycle_manifest_slice.json          （AP-1 的 scan_glob）
    backend/data/workpaper_sync_e_cycle_manifest_slice.json（slice_schema 的 reference_instance）
    .kiro/specs/.../requirements.md                   （AC 原文唯一真源）
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
import sys
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "backend" / "data"
PARADIGM_PATH = DATA / "workpaper_sync_migration_paradigm.json"
SPEC_DIR = ROOT / ".kiro" / "specs" / "workpaper-html-onlyoffice-bidirectional-writeback-closure"
REQUIREMENTS_PATH = SPEC_DIR / "requirements.md"

#: 本文件的仓库相对路径 —— JSON 里的 detector / validator 声明必须指向它。
SELF_REL = "backend/tests/workpaper_sync/test_migration_paradigm_contract.py"

# ════════════════════════════════════════════════════════════════════════════
# 冻结基线（有意的硬编码锁）
# ════════════════════════════════════════════════════════════════════════════
#
# Task 45 冻结的顶层 `paradigm` 是字节冻结对象：`test_task46_d_cycle_migration.py`
# 依赖它恰 7 步。这两个常量与 JSON 的 `paradigm_registry` 里同名字段**互为**期望值
# ⇒ 改了 `paradigm` 而不改守卫打红；改了守卫常量而不改 JSON 也打红。
FROZEN_PARADIGM_RAW_SHA256 = "363c477cd8042073049c627c9f7cf13cf906ace2a5139a13a79197a5897b7f09"
FROZEN_PARADIGM_CANONICAL_SHA256 = "81f7ce00ee2aa19813faad7b9716d821353ea84325960fc615684d57846245a2"

#: Task 45 冻结的七步名与顺序。
FROZEN_PARADIGM_STEP_NAMES: tuple[str, ...] = (
    "identify_legacy",
    "create_deletion_plan",
    "delete_legacy_composable",
    "update_host_imports",
    "unify_mode_values",
    "verify_no_legacy_endpoints",
    "run_post_delete_tests",
)

#: 任务正文点名必须逐字锁死的 AC（`adjudication_criteria` 可以登记更多，但不得少于这些）。
REQUIRED_ACS: tuple[str, ...] = ("1.3", "1.4", "1.5", "12.8", "12.9")

#: `slice_schema` 各必填字段组的**地板**（floor，不是等值）。
#:
#: 🔴 为什么必须有它：反例参数化是从 schema **现读**构造的 —— 把 `required_entry` 里
#: 某个字段删掉，它自己的反例也随之消失 ⇒ 「抽字段」这个动作反而没有任何测试变红
#: （守卫从被变异的源头推导期望值 = 假绿第③源的镜像形态）。地板把「不得缩水」变成
#: 独立判据。取 floor 而非等值：Tasks 48–57 合法扩充 schema 时不该被拦，新增字段会
#: 自动获得自己的反例。
FROZEN_REQUIRED_FLOOR: dict[str, frozenset[str]] = {
    "required_top_level": frozenset({
        "schema_version", "task", "spec", "description", "frozen_at", "source_manifest",
        "paradigm_ref", "sibling_slices", "slice_scope", "independent_entries",
        "authoritative_templates", "blocking_preconditions", "cross_entry_isolation",
        "honest_adjudication_summary", "properties_verified", "requirements_covered",
    }),
    "required_slice_scope": frozenset({
        "cycle", "document_type", "selection_rule", "independent_entry_count",
        "excluded_from_slice",
    }),
    "required_excluded_item": frozenset({"what", "reason"}),
    "required_authoritative_templates": frozenset({
        "root", "reference_copy_status", "lock_file_policy", "files",
    }),
    "required_template_file": frozenset({"name", "size", "sha256", "belongs_to_entry"}),
    "required_entry": frozenset({
        "entry_id", "wp_code_pattern", "document_type", "host", "host_path", "capability",
        "migration_state", "adapter_id", "authority_model", "definition_bundle",
        "instrumentation_candidate", "published_representation", "template_ref",
        "mount_count", "scenario_profile_id", "editability", "room_model",
        "canonical_resolver", "adjudication", "evidence",
    }),
    "presence_required_value_may_be_null": frozenset({
        "adapter_id", "authority_model", "definition_bundle", "instrumentation_candidate",
        "published_representation",
    }),
    "required_entry_adjudication": frozenset({
        "honest_capability", "reason", "not_single_html_because", "not_bidirectional_because",
    }),
    "required_entry_evidence": frozenset({
        "browser_case", "contract_test", "sync_test_run_id",
        "required_scenario_set_digest", "verification_state",
    }),
    "required_blocking_precondition": frozenset({"id", "blocks", "what"}),
    "required_cross_entry_isolation": frozenset({"rule", "assertions"}),
    "required_honest_adjudication_summary": frozenset({
        "total_independent", "adjudicated_as_bidirectional",
        "adjudicated_as_single_onlyoffice", "adjudicated_as_single_html",
        "adjudicated_as_unreachable", "reason", "slice_counters",
    }),
    "required_slice_counters": frozenset({
        "unadjudicated", "fake_bidirectional_claimed_verified", "bidirectional_unverified",
        "stale_evidence",
    }),
    # SR-3 右支（待裁决态）的有条件必填组。地板同样是「只许增不许减」：删掉其中任一字段
    # 就等于把「未裁决伪装成已裁决」的门重新打开，而它自己的反例会随声明一起消失。
    "required_pending_verdict_fields": frozenset({
        "capability_verdict_stage", "capability_target", "capability_target_blocked_by",
    }),
    "pending_verdict_field_semantics": frozenset({
        "capability_verdict_stage", "capability_target", "capability_target_blocked_by",
    }),
}

#: 待裁决态每个字段的语义 kind 冻结值。
#:
#: 🔴 为什么字段名的地板不够：`FROZEN_REQUIRED_FLOOR` 锁的是**键**，而语义 kind 是**值** ——
#: 把 `capability_target` 的 kind 从 `member_of_capability_enum` 悄悄改成 `non_empty_string`，
#: 键一个没少，判据却从「目标必须是四个终态之一」退化成「随便写点什么都行」
#: （`capability_target: "dual"` 当场放行）。放宽必须显式改本常量。
FROZEN_PENDING_VERDICT_SEMANTICS: dict[str, str] = {
    "capability_verdict_stage": "non_empty_string",
    "capability_target": "member_of_capability_enum",
    "capability_target_blocked_by": "non_empty_list",
}

#: SR-9 用的计数器名 —— 待裁决条目数必须等于 `slice_counters[该键]`。
FROZEN_PENDING_VERDICT_COUNTER = "unadjudicated"

#: 「后果」必须写明，但事实范式里有两种形态（BP-1..3 用 `consequence` 单串，
#: BP-4 用 `observable_consequences` 数组）⇒ 用 one-of 组表达，不能二者都设成必填。
FROZEN_ONE_OF_FLOOR: tuple[tuple[str, ...], ...] = (("consequence", "observable_consequences"),)

#: Task 48 起追加的必填字段（`effective_from_task_48`）的地板。
FROZEN_TASK48_FLOOR: dict[str, frozenset[str]] = {
    "required_entry": frozenset({"html_counterpart_verdict", "html_counterpart_source_refs"}),
    "required_blocking_precondition": frozenset({"status", "must_fix_before", "source_refs"}),
}

#: 「理由里给出了 HTML 对端结论」的文本标记。
#:
#: 🔴 这份清单是**守卫自有的启发式**，不是 JSON 里的声明 —— AP-1 只登记了循环论证
#: 标记（`circular_reason_markers`），没有登记「什么算结论」。机器可读的结论形态是
#: `html_counterpart_verdict` 二值字段（由 V1/V2 守）；本清单只用于第三条判据：
#: 理由**只**由「产物尚不存在」构成（连一句关于对端的话都没有）时打红。
COUNTERPART_CONCLUSION_MARKERS: tuple[str, ...] = (
    "html 对端",
    "html_counterpart",
    "html counterpart",
    "html 侧",
    "html side",
    "投影对端",
    "字段级对端",
    "对端不存在",
    "无对端",
    "两侧没有",
    "两侧无",
    "no html",
)


# ════════════════════════════════════════════════════════════════════════════
# 磁盘读取（一律现读，不缓存跨进程）
# ════════════════════════════════════════════════════════════════════════════
def load_paradigm_doc() -> dict:
    """现读 paradigm JSON。"""
    return json.loads(PARADIGM_PATH.read_text(encoding="utf-8"))


def load_paradigm_raw() -> str:
    """现读 paradigm JSON 的原始文本（用于字节级 digest）。"""
    return PARADIGM_PATH.read_text(encoding="utf-8")


def load_requirements_text() -> str:
    """现读 requirements.md —— AC 原文的唯一真源。"""
    return REQUIREMENTS_PATH.read_text(encoding="utf-8")


def _rel(p: Path) -> str:
    return str(p.relative_to(ROOT)).replace("\\", "/")


def slice_paths(scan_glob: str | None = None) -> list[Path]:
    """按 AP-1 声明的 `scan_glob` 现扫 slice 文件（glob 也是被守的声明之一）。"""
    if scan_glob is None:
        scan_glob = load_paradigm_doc()["adjudication_criteria"]["anti_patterns"][0]["scan_glob"]
    return sorted(ROOT.glob(scan_glob))


def reference_slice_path(schema: dict | None = None) -> Path:
    """`slice_schema.reference_instance` 指向的事实范式 slice。"""
    if schema is None:
        schema = load_paradigm_doc()["slice_schema"]
    return ROOT / schema["reference_instance"]


def load_reference_slice() -> dict:
    return json.loads(reference_slice_path().read_text(encoding="utf-8"))


# ════════════════════════════════════════════════════════════════════════════
# 判据一：步骤拓扑（纯函数，可喂合成图反证）
# ════════════════════════════════════════════════════════════════════════════
def find_edge_violations(steps: Sequence[dict]) -> list[str]:
    """`blocks` 必须只指向**更大**的 step 序号，且目标必须存在。

    返回违规说明列表（空 = 合规）。这是 `definition_producer_paradigm.ordering_rule`
    的机器判据：回边 / 自环 / 指向不存在的步骤都算违规。
    """
    numbers = [s.get("step") for s in steps]
    known = set(numbers)
    out: list[str] = []
    if len(known) != len(numbers):
        out.append(f"step 序号重复：{numbers}")
    for s in steps:
        me = s.get("step")
        name = s.get("name", "<无 name>")
        blocks = s.get("blocks")
        if blocks is None:
            out.append(f"step {me}({name}) 缺 `blocks` —— 阻断关系未声明等于没有拓扑")
            continue
        if not isinstance(blocks, list):
            out.append(f"step {me}({name}) 的 `blocks` 不是数组：{blocks!r}")
            continue
        for target in blocks:
            if target not in known:
                out.append(f"step {me}({name}) 的 blocks 指向不存在的 step {target}")
            elif isinstance(me, int) and isinstance(target, int) and target <= me:
                kind = "自环" if target == me else "回边"
                out.append(f"step {me}({name}) 的 blocks 含{kind} → step {target}")
    return out


def find_cycles(steps: Sequence[dict]) -> list[list[Any]]:
    """DFS 找 `blocks` 有向图上的环，返回环路径列表（空 = 无环）。

    前向边图必然无环，所以本函数在真实数据上恒返回空 —— 它的价值在于**独立**于
    :func:`find_edge_violations` 判「有没有环」这件事本身：万一将来 ordering_rule
    放宽成允许某些回边，环检测仍必须承重。反向自检喂合成回边验证它真会报。
    """
    graph: dict[Any, list[Any]] = {
        s.get("step"): [b for b in (s.get("blocks") or []) if isinstance(s.get("blocks"), list)]
        for s in steps
    }
    cycles: list[list[Any]] = []
    WHITE, GREY, BLACK = 0, 1, 2
    color: dict[Any, int] = {n: WHITE for n in graph}

    def dfs(node: Any, stack: list[Any]) -> None:
        color[node] = GREY
        stack.append(node)
        for nxt in graph.get(node, []):
            if nxt not in color:
                continue
            if color[nxt] == GREY:
                cycles.append(stack[stack.index(nxt):] + [nxt])
            elif color[nxt] == WHITE:
                dfs(nxt, stack)
        stack.pop()
        color[node] = BLACK

    for node in list(graph):
        if color.get(node) == WHITE:
            dfs(node, [])
    return cycles


# ════════════════════════════════════════════════════════════════════════════
# 判据二：AC 原文逐字（现读磁盘）
# ════════════════════════════════════════════════════════════════════════════
def ac_lines_on_disk(ac: str, req_text: str | None = None) -> list[str]:
    """requirements.md 里以 `{ac}. ` 开头的行（去掉前缀后的正文）。

    `quotation_rule` 明写「守卫现读磁盘按 `{ac}. ` 前缀定位该行并逐字比对」，故这里
    返回全部命中行 —— 调用方断言恰好一条（命中 0 条 = AC 编号漂移；≥2 条 = 定位不唯一，
    此时「逐字比对」的对象不确定，等于没有判据）。
    """
    if req_text is None:
        req_text = load_requirements_text()
    prefix = f"{ac}. "
    return [ln[len(prefix):] for ln in req_text.split("\n") if ln.startswith(prefix)]


# ════════════════════════════════════════════════════════════════════════════
# 判据三：旧 `paradigm` 字节冻结
# ════════════════════════════════════════════════════════════════════════════
def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def extract_raw_json_block(raw: str, key: str) -> str:
    """从原始 JSON 文本里切出 `"{key}": {...}` 整块（含键名），**字符串感知**。

    🔴 不用朴素花括号计数：`paradigm.steps[5].description` 里有
    `/api/workpapers/{wpId}/sheets/{sn}/onlyoffice-config` —— 今天这些花括号恰好成对，
    朴素计数能碰对，但那是巧合。逐字符跳过 JSON 字符串字面量（含 `\\"` 转义）才是
    正确的做法（平台铁律：截块一律配对扫描，别用固定窗口/朴素计数）。
    """
    needle = f'"{key}": {{'
    start = raw.find(needle)
    if start < 0:
        raise ValueError(f"原始文本里找不到 {needle!r}")
    if raw.find(needle, start + 1) >= 0:
        raise ValueError(f"{needle!r} 命中多处 —— 无法唯一定位")
    i = raw.index("{", start)
    depth = 0
    in_str = False
    escaped = False
    for pos in range(i, len(raw)):
        ch = raw[pos]
        if in_str:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return raw[start:pos + 1]
    raise ValueError(f"{needle!r} 的块未闭合")


def raw_block_digest(raw: str | None = None, key: str = "paradigm") -> str:
    """`"{key}": {...}` 原始字节的 sha256（行尾归一化为 LF）。

    归一化的理由：行尾不是语义内容。仓库当前该文件是纯 LF，故归一化在今天是空操作、
    不改变冻结值；但它让「某台机器 checkout 成 CRLF」不会伪装成「范式被改了」。
    """
    if raw is None:
        raw = load_paradigm_raw()
    return _sha256(extract_raw_json_block(raw, key).replace("\r\n", "\n"))


def canonical_digest(obj: Any) -> str:
    """`paradigm_registry.canonical_recipe` 声明的配方：indent=2 + sort_keys + UTF-8。"""
    return _sha256(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True))


# ════════════════════════════════════════════════════════════════════════════
# 判据四：slice_schema 校验器（JSON 点名 `::validate_slice_against_schema`）
# ════════════════════════════════════════════════════════════════════════════
def _task_number(slice_doc: dict) -> int | None:
    m = re.search(r"Task\s+(\d+)", str(slice_doc.get("task") or ""))
    return int(m.group(1)) if m else None


def _pending_verdict_violations(
    entry: dict,
    label: str,
    pending_fields: Sequence[str],
    semantics: dict[str, str],
    enum: Sequence[str],
) -> list[str]:
    """SR-3 **右支**：`capability: null`（待裁决态）是否把三件事都说清楚了。

    左支是「capability 落在 capability_enum 内」。右支存在的理由写在
    `adjudication_criteria.capability_enum_note`：迁移中的 entry 会被 AC 12.8 / 12.9 /
    1.7 / 12.1 同时排除掉四个终态，此时硬填任一枚举值就是伪造裁决。

    🔴 右支**不是**「null 一律通过」—— 那样「未裁决伪装成已裁决」原地复活。每个
    `required_pending_verdict_fields` 字段按 `pending_verdict_field_semantics` 声明的语义
    kind 校验，缺键 / 空值 / target 不在枚举内 / blocked_by 空数组一律仍报违规，且违规
    说明**点名该字段**（否则反例可能被别的规则误伤而看似通过，该字段仍是死声明）。

    没有声明语义 kind 的 pending 字段也报违规（fail closed）：否则「加字段不加语义」
    就能悄悄放宽右支。
    """
    problems: list[str] = []
    for field in pending_fields:
        kind = semantics.get(field)
        if kind is None:
            problems.append(
                f"{label}: `{field}` 列进 required_pending_verdict_fields 却没有 "
                "pending_verdict_field_semantics 语义声明 ⇒ 无法校验（SR-3 右支 fail closed）"
            )
            continue
        present = field in entry
        value = entry.get(field)
        if kind == "non_empty_string":
            ok = isinstance(value, str) and value.strip() != ""
            expectation = "是非空字符串"
        elif kind == "member_of_capability_enum":
            ok = value in enum
            expectation = f"落在 capability_enum 内（{list(enum)}）"
        elif kind == "non_empty_list":
            ok = isinstance(value, list) and bool(value)
            expectation = "是非空数组"
        else:
            problems.append(
                f"{label}: `{field}` 的语义 kind={kind!r} 校验器不认识 ⇒ 无法校验"
                "（SR-3 右支 fail closed）"
            )
            continue
        if not ok:
            problems.append(
                f"{label}: capability 为 null（待裁决态）⇒ `{field}` 必须{expectation}，"
                f"实际 {'缺键' if not present else repr(value)}"
                "（SR-3 右支 / required_pending_verdict_fields）"
            )
    return problems


def validate_slice_against_schema(
    slice_doc: dict,
    schema: dict | None = None,
    *,
    criteria: dict | None = None,
    enforce_task48: bool | None = None,
) -> list[str]:
    """按 `slice_schema` 校验一份 manifest slice，返回违规说明列表（空 = 通过）。

    :param enforce_task48: 是否施加 `effective_from_task_48` 的追加必填。默认由
        `slice_doc["task"]` 里的编号推导（≥48 才加）—— D/E 两个 slice 冻结在范式补全
        之前，追加项由 AP-1 的 known_debt_inventory 兑现，不追溯改写它们的字节。

    判据不抛异常而是**累积**违规：抽掉任一必填字段的反例都必须落在返回列表里，
    且说明文本必须提到该字段名（否则「反例打红了」可能是别的规则误伤，属于
    无归因的红）。

    SR-3 是**蕴含式**（G1 收口）：`capability` 落在 `capability_enum` 内 **或**
    为 null 且待裁决三字段齐备（右支见 :func:`_pending_verdict_violations`）。右支
    放行 null 之后由 SR-9 管住计数（待裁决条目数 == `slice_counters[pending_verdict_counter]`），
    否则「全记待裁决同时报 0」就能通过校验。schema 没声明右支时 null 一律按左支报 SR-3。
    """
    doc = None
    if schema is None or criteria is None:
        doc = load_paradigm_doc()
    if schema is None:
        schema = doc["slice_schema"]
    if criteria is None:
        criteria = doc["adjudication_criteria"]

    v: list[str] = []

    def need(obj: Any, keys: Iterable[str], label: str) -> bool:
        if not isinstance(obj, dict):
            v.append(f"{label}: 不是对象，无法校验必填字段 {sorted(keys)}")
            return False
        for k in keys:
            if k not in obj:
                v.append(f"{label}: 缺必填字段 `{k}`")
        return True

    # ── 顶层 ───────────────────────────────────────────────────────────────
    need(slice_doc, schema.get("required_top_level", []), "slice")
    target = schema.get("target_schema_version")
    if slice_doc.get("schema_version") != target:
        v.append(
            f"slice: `schema_version` 应为 {target!r}，实际 "
            f"{slice_doc.get('schema_version')!r}"
        )
    for ref_key in ("source_manifest", "paradigm_ref"):
        ref = slice_doc.get(ref_key)
        if isinstance(ref, str) and not (ROOT / ref).exists():
            v.append(f"slice: `{ref_key}` 指向不存在的文件 {ref!r}")

    # ── slice_scope ────────────────────────────────────────────────────────
    scope = slice_doc.get("slice_scope")
    if isinstance(scope, dict):
        need(scope, schema.get("required_slice_scope", []), "slice_scope")
        excluded = scope.get("excluded_from_slice")
        if excluded is not None:
            if not isinstance(excluded, list):
                v.append("slice_scope: `excluded_from_slice` 必须是数组")
            else:
                for i, item in enumerate(excluded):
                    need(
                        item, schema.get("required_excluded_item", []),
                        f"slice_scope.excluded_from_slice[{i}]",
                    )
    elif "slice_scope" in slice_doc:
        v.append("slice: `slice_scope` 必须是对象")

    # ── independent_entries ────────────────────────────────────────────────
    entries = slice_doc.get("independent_entries")
    if not isinstance(entries, list):
        if "independent_entries" in slice_doc:
            v.append("slice: `independent_entries` 必须是数组")
        entries = []
    entry_ids = {e.get("entry_id") for e in entries if isinstance(e, dict)}
    enum = list(criteria.get("capability_enum", []))
    identity_fields = list(schema.get("presence_required_value_may_be_null", []))
    # SR-3 右支（待裁决态）的声明。schema 没声明 ⇒ pending_fields 为空 ⇒ `capability: null`
    # 一律按左支报 SR-3（fail closed，不因声明缺失而放宽）。
    pending_fields = list(schema.get("required_pending_verdict_fields", []))
    pending_semantics = dict(schema.get("pending_verdict_field_semantics", {}))
    pending_counter = schema.get("pending_verdict_counter")
    pending_count = 0

    for i, entry in enumerate(entries):
        label = f"independent_entries[{i}]({entry.get('entry_id', '<无 entry_id>')})"
        if not need(entry, schema.get("required_entry", []), label):
            continue
        for k in identity_fields:
            if k not in entry:
                v.append(f"{label}: `{k}` 必须**出现**（值可为 null，键不得缺）")
        cap = entry.get("capability")
        if cap is None and pending_fields:
            v.extend(_pending_verdict_violations(entry, label, pending_fields,
                                                 pending_semantics, enum))
            pending_count += 1
        elif cap not in enum:
            v.append(f"{label}: capability={cap!r} 不在 capability_enum（SR-3 / AC 1.3）")
        adj = entry.get("adjudication")
        if isinstance(adj, dict):
            need(adj, schema.get("required_entry_adjudication", []), f"{label}.adjudication")
            if adj.get("honest_capability") != cap:
                v.append(
                    f"{label}: capability={cap!r} != adjudication.honest_capability="
                    f"{adj.get('honest_capability')!r}（SR-4：对外字段与诚实裁决双口径）"
                )
        elif "adjudication" in entry:
            v.append(f"{label}: `adjudication` 必须是对象")
        if isinstance(cap, str) and (cap.startswith("single_") or cap == "unreachable"):
            non_null = [k for k in identity_fields if entry.get(k) is not None]
            if non_null:
                v.append(
                    f"{label}: capability={cap} ⇒ {non_null} 必须为 null"
                    "（SR-5 / AP-5：裁 single 的 entry 不得挂 adapter/contract/bundle）"
                )
        if cap == "bidirectional":
            nulls = [k for k in identity_fields if entry.get(k) is None]
            if nulls:
                v.append(
                    f"{label}: capability=bidirectional ⇒ {nulls} 不得为 null"
                    "（SR-6 / AC 12.1）"
                )
        ev = entry.get("evidence")
        if isinstance(ev, dict):
            need(ev, schema.get("required_entry_evidence", []), f"{label}.evidence")
            if ev.get("verification_state") == "UNVERIFIABLE":
                reasons = ev.get("unverifiable_reasons")
                if not (isinstance(reasons, list) and reasons):
                    v.append(
                        f"{label}.evidence: verification_state=UNVERIFIABLE 必须带非空 "
                        "`unverifiable_reasons`（SR-7）"
                    )
        elif "evidence" in entry:
            v.append(f"{label}: `evidence` 必须是对象")

    # ── authoritative_templates ────────────────────────────────────────────
    templates = slice_doc.get("authoritative_templates")
    if isinstance(templates, dict):
        need(templates, schema.get("required_authoritative_templates", []),
             "authoritative_templates")
        files = templates.get("files")
        if files is not None and not isinstance(files, list):
            v.append("authoritative_templates: `files` 必须是数组")
        for i, f in enumerate(files or []):
            flabel = f"authoritative_templates.files[{i}]"
            if not need(f, schema.get("required_template_file", []), flabel):
                continue
            if "belongs_to_entry" in f:
                owner = f["belongs_to_entry"]
                if owner is None:
                    if not f.get("excluded_reason"):
                        v.append(
                            f"{flabel}: `belongs_to_entry` 为 null 必须给 `excluded_reason`"
                            "（SR-8：防悄悄夹带跨循环模板）"
                        )
                elif owner not in entry_ids:
                    v.append(
                        f"{flabel}: `belongs_to_entry`={owner!r} 不命中本 slice 的任何 "
                        f"entry_id（SR-8）"
                    )
    elif "authoritative_templates" in slice_doc:
        v.append("slice: `authoritative_templates` 必须是对象")

    # ── blocking_preconditions ─────────────────────────────────────────────
    bps = slice_doc.get("blocking_preconditions")
    if bps is not None and not isinstance(bps, list):
        v.append("slice: `blocking_preconditions` 必须是数组")
        bps = []
    one_of_groups = [tuple(g) for g in schema.get("required_blocking_precondition_one_of", [])]
    for i, bp in enumerate(bps or []):
        blabel = f"blocking_preconditions[{i}]({bp.get('id', '<无 id>') if isinstance(bp, dict) else '?'})"
        if not need(bp, schema.get("required_blocking_precondition", []), blabel):
            continue
        for group in one_of_groups:
            if not any(bp.get(k) for k in group):
                v.append(
                    f"{blabel}: {list(group)} 至少要有一个非空 —— 阻断项必须写明后果，"
                    "否则它只是一句「有问题」"
                )

    # ── cross_entry_isolation ──────────────────────────────────────────────
    isolation = slice_doc.get("cross_entry_isolation")
    if isinstance(isolation, dict):
        need(isolation, schema.get("required_cross_entry_isolation", []),
             "cross_entry_isolation")
        assertions = isolation.get("assertions")
        if "assertions" in isolation and not (isinstance(assertions, list) and assertions):
            v.append("cross_entry_isolation: `assertions` 必须是非空数组（Property 70）")
    elif "cross_entry_isolation" in slice_doc:
        v.append("slice: `cross_entry_isolation` 必须是对象")

    # ── honest_adjudication_summary（SR-1 / SR-2 现算）────────────────────
    summary = slice_doc.get("honest_adjudication_summary")
    if isinstance(summary, dict):
        need(summary, schema.get("required_honest_adjudication_summary", []),
             "honest_adjudication_summary")
        counters = summary.get("slice_counters")
        if isinstance(counters, dict):
            need(counters, schema.get("required_slice_counters", []),
                 "honest_adjudication_summary.slice_counters")
            # SR-9：SR-3 右支放行 null 之后必须有人管住计数，否则「全记待裁决 + 报 0」
            # 就能过校验 —— 右支被当后门用。与 SR-1/SR-2 同形：计数现算，不许手填。
            if pending_counter and pending_counter in counters:
                if counters[pending_counter] != pending_count:
                    v.append(
                        f"SR-9: slice_counters.{pending_counter}="
                        f"{counters[pending_counter]} != 待裁决态（capability=null）实际条数 "
                        f"{pending_count}"
                    )
        elif "slice_counters" in summary:
            v.append("honest_adjudication_summary: `slice_counters` 必须是对象")
        if "total_independent" in summary and summary["total_independent"] != len(entries):
            v.append(
                f"SR-1: honest_adjudication_summary.total_independent="
                f"{summary['total_independent']} != len(independent_entries)={len(entries)}"
            )
        if isinstance(scope, dict) and "independent_entry_count" in scope:
            if scope["independent_entry_count"] != len(entries):
                v.append(
                    f"SR-1: slice_scope.independent_entry_count="
                    f"{scope['independent_entry_count']} != "
                    f"len(independent_entries)={len(entries)}"
                )
        for cap in enum:
            key = f"adjudicated_as_{cap}"
            if key in summary:
                actual = sum(
                    1 for e in entries if isinstance(e, dict) and e.get("capability") == cap
                )
                if summary[key] != actual:
                    v.append(f"SR-2: {key}={summary[key]} != 实际条数 {actual}")
    elif "honest_adjudication_summary" in slice_doc:
        v.append("slice: `honest_adjudication_summary` 必须是对象")

    # ── conditional_sections（present 才必填；缺失不是违规）────────────────
    for cs in schema.get("conditional_sections", []):
        section = cs.get("section")
        if section not in slice_doc:
            continue
        body = slice_doc[section]
        if not need(body, cs.get("required_fields", []), section):
            continue
        table_fields = cs.get("required_table_fields")
        if table_fields:
            for i, table in enumerate(body.get("tables") or []):
                tlabel = f"{section}.tables[{i}]({table.get('table_key', '?')})"
                if not need(table, table_fields, tlabel):
                    continue
                row_fields = cs.get("required_row_identity_fields")
                if row_fields:
                    identity = table.get("row_identity")
                    if not need(identity, row_fields, f"{tlabel}.row_identity"):
                        continue
                    forbidden = body.get("forbidden_identity_kinds") or []
                    if identity.get("kind") in forbidden:
                        v.append(
                            f"{tlabel}.row_identity: kind={identity.get('kind')!r} 在 "
                            f"forbidden_identity_kinds 里（行身份不得用下标/序号）"
                        )

    # ── effective_from_task_48 ─────────────────────────────────────────────
    effective = schema.get("effective_from_task_48") or {}
    if enforce_task48 is None:
        number = _task_number(slice_doc)
        enforce_task48 = number is not None and number >= 48
    if enforce_task48:
        for i, entry in enumerate(entries):
            need(
                entry, effective.get("required_entry", []),
                f"independent_entries[{i}]"
                f"({entry.get('entry_id', '?') if isinstance(entry, dict) else '?'})"
                " [Task 48 起必填]",
            )
        for i, bp in enumerate(bps or []):
            need(
                bp, effective.get("required_blocking_precondition", []),
                f"blocking_preconditions[{i}] [Task 48 起必填]",
            )

    return v


# ════════════════════════════════════════════════════════════════════════════
# 判据五：AP-1 反模式检测器（circular justification）
# ════════════════════════════════════════════════════════════════════════════
def _ap(doc: dict, ap_id: str = "AP-1") -> dict:
    for ap in doc["adjudication_criteria"]["anti_patterns"]:
        if ap.get("id") == ap_id:
            return ap
    raise AssertionError(f"adjudication_criteria.anti_patterns 里没有 {ap_id}")


def _reason_blob(entry: dict) -> str:
    """裁决理由的全文（`reason` + `manifest_legacy_reasons`）。

    把 `manifest_legacy_reasons` 也算进来：否则把循环论证从 `reason` 挪进那个数组
    （E slice 就有 `missing_adapter`）就能绕过检测。**不**含
    `not_bidirectional_because` —— 那一栏本来就该罗列「五件事都不存在」，它是
    正确的位置，不是循环论证。
    """
    adj = entry.get("adjudication") or {}
    parts = [str(adj.get("reason") or "")]
    legacy = adj.get("manifest_legacy_reasons")
    if isinstance(legacy, list):
        parts.extend(str(x) for x in legacy)
    return "\n".join(parts)


def reason_is_circular_only(entry: dict, markers: Iterable[str]) -> bool:
    """理由是否**只**由「本任务应交付的产物尚不存在」构成。

    判据 = 命中循环论证标记 **且** 通篇没有任何关于「HTML 对端是否存在」的结论。
    这是 AC 12.8 的直接推论：single_onlyoffice 的唯一合法判据是「无 HTML 对端」，
    「还没有 adapter/contract/bundle」对任何未动工的 entry 都成立 ⇒ 判据恒真 ⇒
    全部 entry 都可裁 single ⇒ spec 空转。
    """
    blob = _reason_blob(entry).lower()
    circular = [m for m in markers if str(m).lower() in blob]
    if not circular:
        return False
    return not any(m in blob for m in COUNTERPART_CONCLUSION_MARKERS)


def evaluate_single_onlyoffice_entry(entry: dict, ap1: dict | None = None) -> list[str]:
    """AP-1 的核心判据：一个裁为 `single_onlyoffice` 的 entry 是否合规。

    返回违规说明列表（空 = 合规）。三件事，缺一不可：

    1. 必须携带 HTML 对端调查结论（`html_counterpart_verdict` ∈ {none, exists}）
       且带非空 `html_counterpart_source_refs`；`unresolved` / `unknown` / 空值
       都不是结论（AP-3）。
    2. 结论为 `exists` 时**禁止**裁 `single_onlyoffice`（AC 12.8 的唯一合法判据是
       「无 HTML 对端」）。
    3. 裁决理由不得只由「本任务应交付的产物尚不存在」构成（AP-1 循环论证）。

    字段名与取值域一律取自 JSON 声明（`required_remedy_fields` /
    `allowed_verdict_values` / `forbidden_verdict_for_single_onlyoffice` /
    `circular_reason_markers`）—— 守卫不写第二份真源。
    """
    if ap1 is None:
        ap1 = _ap(load_paradigm_doc())
    remedy = list(ap1.get("required_remedy_fields") or [])
    allowed = list(ap1.get("allowed_verdict_values") or [])
    forbidden = ap1.get("forbidden_verdict_for_single_onlyoffice")
    markers = list(ap1.get("circular_reason_markers") or [])

    verdict_field = remedy[0] if remedy else "html_counterpart_verdict"
    refs_field = remedy[1] if len(remedy) > 1 else "html_counterpart_source_refs"

    out: list[str] = []
    verdict = entry.get(verdict_field)
    if verdict is None or (isinstance(verdict, str) and not verdict.strip()):
        out.append(
            f"缺 `{verdict_field}` —— 裁 single_onlyoffice 的唯一合法判据是「无 HTML 对端」"
            f"（AC 12.8），而本 entry 根本没给出对端调查结论"
        )
    elif verdict not in allowed:
        out.append(
            f"`{verdict_field}`={verdict!r} 不在 {allowed} 内 —— "
            "unresolved / unknown 是「还没查」，不是结论（AP-3）"
        )
    elif verdict == forbidden:
        out.append(
            f"`{verdict_field}`={verdict!r} 却裁 single_onlyoffice —— "
            "有 HTML 对端就不满足 AC 12.8 的唯一合法判据"
        )

    refs = entry.get(refs_field)
    if not (isinstance(refs, (list, tuple)) and len(refs) > 0):
        out.append(
            f"缺非空 `{refs_field}` —— 结论必须带可核对的来源"
            "（宿主 .vue / 后端 router / 模板 sheet!cell）"
        )

    if reason_is_circular_only(entry, markers):
        hits = [m for m in markers if str(m).lower() in _reason_blob(entry).lower()]
        out.append(
            f"裁决理由只由「本任务应交付的产物尚不存在」构成（命中 {hits[:4]}），"
            "通篇没有关于 HTML 对端是否存在的结论 ⇒ 循环论证（AP-1）"
        )
    return out


def debt_inventory_keys(ap1: dict | None = None) -> set[tuple[str, str]]:
    """AP-1 已登记的存量欠账键集合 `{(slice 相对路径, entry_id)}`。"""
    if ap1 is None:
        ap1 = _ap(load_paradigm_doc())
    inventory = ap1.get("known_debt_inventory") or {}
    return {
        (str(e.get("slice")).replace("\\", "/"), str(e.get("entry_id")))
        for e in inventory.get("entries") or []
    }


def scan_single_onlyoffice_violations() -> dict[tuple[str, str], list[str]]:
    """扫全部 slice，返回 `{(slice, entry_id): 违规说明}`（只含违规项）。"""
    doc = load_paradigm_doc()
    ap1 = _ap(doc)
    out: dict[tuple[str, str], list[str]] = {}
    for path in slice_paths(ap1.get("scan_glob")):
        slice_doc = json.loads(path.read_text(encoding="utf-8"))
        for entry in slice_doc.get("independent_entries") or []:
            if entry.get("capability") != "single_onlyoffice":
                continue
            problems = evaluate_single_onlyoffice_entry(entry, ap1)
            if problems:
                out[(_rel(path), str(entry.get("entry_id")))] = problems
    return out


# ════════════════════════════════════════════════════════════════════════════
# fixtures
# ════════════════════════════════════════════════════════════════════════════
@pytest.fixture(scope="module")
def doc() -> dict:
    return load_paradigm_doc()


@pytest.fixture(scope="module")
def dpp(doc: dict) -> dict:
    return doc["definition_producer_paradigm"]


@pytest.fixture(scope="module")
def criteria(doc: dict) -> dict:
    return doc["adjudication_criteria"]


@pytest.fixture(scope="module")
def schema(doc: dict) -> dict:
    return doc["slice_schema"]


@pytest.fixture(scope="module")
def e_slice() -> dict:
    return load_reference_slice()


# ════════════════════════════════════════════════════════════════════════════
# 声明 ↔ 实现：JSON 点名的 detector / validator 必须真的存在
# ════════════════════════════════════════════════════════════════════════════
class TestDeclaredConsumersExist:
    """**Validates: Requirements 12.4**

    `adjudication_criteria` 与 `slice_schema` 都把本文件里的**具体符号**写进了声明。
    只写不实现 = 又一条死数据（这次是反向的：数据宣称有消费方而消费方不存在）。
    判据落在「模块属性是否存在」而不是「字符串里有没有这个名字」。
    """

    @staticmethod
    def _split(ref: str) -> tuple[str, str]:
        path, _, symbol = ref.partition("::")
        return path.replace("\\", "/"), symbol

    def test_ap1_detector_points_at_a_class_defined_here(self, criteria: dict) -> None:
        path, symbol = self._split(_ap({"adjudication_criteria": criteria})["detector"])
        assert path == SELF_REL, f"AP-1 detector 指向 {path!r}，本文件是 {SELF_REL!r}"
        target = getattr(sys.modules[__name__], symbol, None)
        assert isinstance(target, type), (
            f"AP-1 声明的 detector `{symbol}` 在本模块里不存在（或不是类）—— "
            "声明了检测器却没有检测器，等于没有判据"
        )

    def test_slice_schema_validator_points_at_a_callable_defined_here(
        self, schema: dict
    ) -> None:
        path, symbol = self._split(schema["validator"])
        assert path == SELF_REL, f"slice_schema.validator 指向 {path!r}"
        target = getattr(sys.modules[__name__], symbol, None)
        assert callable(target), (
            f"slice_schema 声明的 validator `{symbol}` 在本模块里不存在（或不可调用）"
        )

    def test_paradigm_registry_aliases_resolve_to_real_json_pointers(self, doc: dict) -> None:
        """`paradigm_registry` 的每个别名都必须能按 json_pointer 解析到真键。"""
        for item in doc["paradigm_registry"]["paradigms"]:
            pointer = item["json_pointer"]
            assert pointer.startswith("/"), f"{item['alias']}: json_pointer 形态非法 {pointer!r}"
            node: Any = doc
            for token in [t for t in pointer.split("/") if t]:
                assert isinstance(node, dict) and token in node, (
                    f"{item['alias']}: json_pointer {pointer!r} 解析不到 —— 别名指向空气"
                )
                node = node[token]
            assert isinstance(node, dict) and node, f"{item['alias']}: 解析到空对象"


# ════════════════════════════════════════════════════════════════════════════
# 判据一：definition_producer_paradigm 的步骤拓扑
# ════════════════════════════════════════════════════════════════════════════
class TestDefinitionProducerParadigmTopology:
    """**Validates: Requirements 12.4**

    `ordering_rule` 声明「`blocks` 只能指向更大的 step 序号，出现回边或环即打红」。
    判据是**现算图**（边方向 + DFS 找环），不是「文档里写了这句话」。
    """

    def test_steps_are_contiguous_and_unique(self, dpp: dict) -> None:
        numbers = [s["step"] for s in dpp["steps"]]
        assert numbers == list(range(1, len(numbers) + 1)), (
            f"step 序号必须是 1..N 连续无重复，实际 {numbers}"
        )

    def test_every_step_has_a_name_and_description(self, dpp: dict) -> None:
        for s in dpp["steps"]:
            assert s.get("name"), f"step {s.get('step')} 缺 name"
            assert len(str(s.get("description") or "")) >= 10, (
                f"step {s.get('step')} 的 description 缺失或过短"
            )

    def test_blocks_edges_are_forward_only(self, dpp: dict) -> None:
        violations = find_edge_violations(dpp["steps"])
        assert violations == [], (
            "definition_producer_paradigm.ordering_rule 被破坏：\n"
            + "\n".join("  !! " + v for v in violations)
        )

    def test_the_step_graph_is_acyclic(self, dpp: dict) -> None:
        cycles = find_cycles(dpp["steps"])
        assert cycles == [], f"步骤图成环：{cycles}"

    def test_the_last_step_blocks_nothing(self, dpp: dict) -> None:
        """收口步骤（close_slice_counters）不得阻断任何后继 —— 否则它不是终点。"""
        last = dpp["steps"][-1]
        assert last["blocks"] == [], f"末步 {last['name']} 的 blocks 应为空，实际 {last['blocks']}"

    def test_every_declared_activity_maps_to_an_existing_step(self, dpp: dict) -> None:
        """`activity_coverage` 的每件活都必须落在真实存在的步骤上。

        这是范式补全的**根因判据**：旧 `/paradigm` 漏掉的恰是这些活，
        「漏掉一整类活」在数据层的形态就是某件活没有归属步骤。
        """
        numbers = {s["step"] for s in dpp["steps"]}
        activities = dpp["activity_coverage"]["activities"]
        dangling = {k: v for k, v in activities.items() if v not in numbers}
        assert not dangling, f"以下活动映射到不存在的步骤：{dangling}"

    def test_the_gap_the_registry_names_is_fully_covered(self, doc: dict, dpp: dict) -> None:
        """`does_not_cover` 罗列的每件事都必须有一件 activity 兜住。

        判据是**计数关系**而不是逐条文本匹配（两侧措辞不同）：`does_not_cover` 有 N 条，
        `activities` 至少要有 N 条映射，且必须覆盖 step 2~11 这一整段
        （definition producer 流水线）—— 少覆盖一步就说明某类活又没人做。
        """
        registry = doc["paradigm_registry"]["paradigms"][0]
        gaps = registry["does_not_cover"]
        activities = dpp["activity_coverage"]["activities"]
        assert len(activities) >= len(gaps), (
            f"does_not_cover 有 {len(gaps)} 条，activities 只有 {len(activities)} 条 —— "
            "至少有一类活没有归属步骤"
        )
        covered = set(activities.values())
        expected = set(range(2, 12))
        assert expected <= covered, (
            f"definition producer 流水线未被完整覆盖，缺步骤 {sorted(expected - covered)}"
        )

    def test_step_9_reuses_the_frozen_legacy_paradigm_by_alias(self, doc: dict, dpp: dict) -> None:
        """复用声明必须指向 `paradigm_registry` 里真实存在的别名，不是自由文本。"""
        aliases = {p["alias"] for p in doc["paradigm_registry"]["paradigms"]}
        reuses = [(s["step"], s["reuses_paradigm"]) for s in dpp["steps"] if "reuses_paradigm" in s]
        assert reuses, "没有任何步骤声明复用 legacy 删除范式 —— 七步范式被孤立了"
        for step, alias in reuses:
            assert alias in aliases, f"step {step} 复用了不存在的范式别名 {alias!r}"

    def test_adjudication_step_is_before_the_producer_pipeline(self, dpp: dict) -> None:
        """裁决（step 4）必须早于发布流水线（step 5 起）—— 顺序反了就是先干活后裁决。"""
        by_name = {s["name"]: s["step"] for s in dpp["steps"]}
        assert by_name["resolve_html_counterpart"] < by_name["adjudicate_single_or_continue"], (
            "对端调查必须早于裁决 —— 否则裁决没有事实依据"
        )
        assert by_name["adjudicate_single_or_continue"] < by_name["publish_authority_model"]
        assert by_name["publish_per_entry_contract"] < by_name["publish_approved_definition_bundle"]
        assert by_name["publish_approved_definition_bundle"] < by_name["finalize_published_representation"]
        assert by_name["finalize_published_representation"] < by_name["register_adapter_and_wire_host"]


# ════════════════════════════════════════════════════════════════════════════
# 判据二：AC 原文逐字一致（现读磁盘）
# ════════════════════════════════════════════════════════════════════════════
_REGISTERED_ACS: tuple[str, ...] = tuple(
    item["ac"] for item in load_paradigm_doc()["adjudication_criteria"]["acceptance_criteria"]
)


class TestAcceptanceCriteriaVerbatim:
    """**Validates: Requirements 1.3, 1.4, 1.5, 1.7, 12.1, 12.8, 12.9**

    `quotation_rule` 明写：`acceptance_criteria[].text` 是 requirements.md 的原文逐字，
    守卫现读磁盘按 `{ac}. ` 前缀定位并逐字比对，requirements.md 改了而范式未跟 ⇒ 打红。
    """

    def test_the_required_acs_are_all_registered(self, criteria: dict) -> None:
        registered = {item["ac"] for item in criteria["acceptance_criteria"]}
        missing = [ac for ac in REQUIRED_ACS if ac not in registered]
        assert not missing, f"以下 AC 未登记进 adjudication_criteria：{missing}"

    def test_the_source_document_points_at_the_requirements_on_disk(
        self, criteria: dict
    ) -> None:
        declared = ROOT / criteria["source_document"]
        assert declared.exists(), f"source_document 指向不存在的文件：{criteria['source_document']}"
        assert declared.resolve() == REQUIREMENTS_PATH.resolve(), (
            "source_document 与本守卫读的 requirements.md 不是同一份文件 —— "
            "逐字比对会比到别的文档上"
        )

    @pytest.mark.parametrize("ac", _REGISTERED_ACS)
    def test_ac_text_is_verbatim_from_requirements_md(self, ac: str, criteria: dict) -> None:
        registered = next(
            item["text"] for item in criteria["acceptance_criteria"] if item["ac"] == ac
        )
        hits = ac_lines_on_disk(ac)
        assert len(hits) == 1, (
            f"requirements.md 里以 `{ac}. ` 开头的行有 {len(hits)} 条（应为 1）—— "
            "定位不唯一时「逐字比对」的对象不确定"
        )
        assert hits[0] == registered, (
            f"AC {ac} 与 requirements.md 磁盘内容不一致（不是转述问题，是逐字问题）：\n"
            f"  磁盘: {hits[0]!r}\n"
            f"  范式: {registered!r}"
        )

    def test_every_registered_ac_has_a_role(self, criteria: dict) -> None:
        for item in criteria["acceptance_criteria"]:
            assert item.get("role"), f"AC {item['ac']} 缺 role —— 无法说明它在裁决里的位置"

    def test_capability_enum_is_derived_from_ac_1_3_text(self, criteria: dict) -> None:
        """能力态四值必须逐个出现在 AC 1.3 原文里（AC 1.3 是它的来源声明）。"""
        source_ac = criteria["capability_enum_derived_from"]
        text = ac_lines_on_disk(source_ac)[0]
        for cap in criteria["capability_enum"]:
            assert cap in text, (
                f"capability_enum 的 {cap!r} 在 AC {source_ac} 原文里找不到 —— "
                "枚举与它声称的来源脱节"
            )
        assert "dual" not in criteria["capability_enum"], "AC 1.3 明确禁止含糊的 dual"

    def test_every_verdict_and_anti_pattern_cites_a_registered_ac(self, criteria: dict) -> None:
        registered = {item["ac"] for item in criteria["acceptance_criteria"]}
        for name, verdict in criteria["verdicts"].items():
            cited = verdict.get("derived_from_ac")
            assert cited in registered, f"verdicts.{name} 引用了未登记的 AC {cited!r}"
        for ap in criteria["anti_patterns"]:
            cited = ap.get("contradicts_ac")
            assert cited in registered, f"{ap['id']} 引用了未登记的 AC {cited!r}"


# ════════════════════════════════════════════════════════════════════════════
# 判据三：Task 45 冻结的 `paradigm` 未被改动（双向 digest 锁）
# ════════════════════════════════════════════════════════════════════════════
class TestFrozenLegacyParadigm:
    """**Validates: Requirements 12.4**

    `paradigm_registry.paradigms[0].immutability` 要求双向锁：改了 `paradigm` 而不改守卫
    打红；改了守卫常量而不改 `paradigm`（含本键里登记的 digest）也打红。
    """

    def test_raw_block_bytes_are_frozen(self) -> None:
        assert raw_block_digest() == FROZEN_PARADIGM_RAW_SHA256, (
            "顶层 `paradigm` 的原始字节被改动了。它是 Task 45 的字节冻结对象，"
            "test_task46_d_cycle_migration.py 依赖它恰 7 步。"
            "若确实需要改，必须同时更新本守卫常量与 JSON 的 frozen_raw_block_sha256。"
        )

    def test_canonical_digest_is_frozen(self, doc: dict) -> None:
        assert canonical_digest(doc["paradigm"]) == FROZEN_PARADIGM_CANONICAL_SHA256

    def test_registry_digests_equal_the_guard_constants(self, doc: dict) -> None:
        """两个方向的锁：JSON 登记值 == 守卫常量。"""
        registry = doc["paradigm_registry"]["paradigms"][0]
        assert registry["frozen_raw_block_sha256"] == FROZEN_PARADIGM_RAW_SHA256
        assert registry["frozen_canonical_sha256"] == FROZEN_PARADIGM_CANONICAL_SHA256
        assert registry["step_count"] == len(doc["paradigm"]["steps"]) == 7

    def test_the_seven_frozen_step_names_are_intact(self, doc: dict) -> None:
        names = tuple(s["name"] for s in doc["paradigm"]["steps"])
        assert names == FROZEN_PARADIGM_STEP_NAMES

    def test_the_frozen_digest_pins_one_recipe(self, doc: dict) -> None:
        """反向自检：换配方必须算出不同的 digest。

        否则「canonical_recipe」这句声明是装饰 —— 后人换成 compact / 不排序也能对上，
        digest 就不再锁任何东西。
        """
        para = doc["paradigm"]
        alternatives = {
            "indent2_nosort": json.dumps(para, ensure_ascii=False, indent=2),
            "compact": json.dumps(para, ensure_ascii=False),
            "ascii_indent2_sort": json.dumps(para, indent=2, sort_keys=True),
        }
        for label, text in alternatives.items():
            assert _sha256(text) != FROZEN_PARADIGM_CANONICAL_SHA256, (
                f"配方 {label} 也能算出冻结 digest ⇒ digest 没有锁住配方"
            )

    def test_the_new_keys_do_not_live_inside_the_frozen_block(self, doc: dict) -> None:
        """四个新键必须在顶层，不得塞进被冻结的 `paradigm` 里。"""
        for key in ("paradigm_registry", "definition_producer_paradigm",
                    "adjudication_criteria", "slice_schema"):
            assert key in doc, f"新键 {key} 不在顶层"
            assert key not in doc["paradigm"], (
                f"{key} 被塞进了冻结块 `paradigm` —— 会破坏字节冻结与 7 步依赖"
            )


# ════════════════════════════════════════════════════════════════════════════
# 判据四：slice_schema —— 正例（事实范式必须通过）
# ════════════════════════════════════════════════════════════════════════════
class TestSliceSchemaPositiveExample:
    """**Validates: Requirements 12.4**

    `negative_example_rule` 要求两侧都断言。这里是正例侧：`reference_instance`
    （Task 47 的 E 循环 slice，目前唯一形成完整字段集的事实范式）必须通过校验。
    只有反例的 schema 是死数据；只有正例的 schema 是恒真判据。
    """

    def test_reference_instance_is_a_real_file_on_disk(self, schema: dict) -> None:
        path = reference_slice_path(schema)
        assert path.exists(), f"reference_instance 指向不存在的文件：{schema['reference_instance']}"
        assert schema["derived_from"] == schema["reference_instance"], (
            "derived_from 与 reference_instance 不是同一份 slice —— schema 声称的来源不确定"
        )

    def test_the_reference_instance_passes(self, e_slice: dict) -> None:
        problems = validate_slice_against_schema(e_slice)
        assert problems == [], (
            "事实范式 slice 通不过自己的 schema —— schema 与事实脱节：\n"
            + "\n".join("  !! " + p for p in problems)
        )

    def test_conditional_sections_are_not_globally_required(self, e_slice: dict) -> None:
        """⚠ E 循环特有的两个条件段不得被当成全局必填。

        `why_not_global` 写得很清楚：设成全局必填会逼作者为不存在的动态行/币种变体
        编造声明 —— 那正是「additive 注入即死代码」的假绿源。判据 = 抽掉这两段后
        **仍然通过**。
        """
        stripped = copy.deepcopy(e_slice)
        for section in ("dynamic_row_identity", "currency_variant_model"):
            stripped.pop(section, None)
        problems = validate_slice_against_schema(stripped)
        assert problems == [], (
            "抽掉 E 循环特有条件段后 schema 就不通过了 ⇒ 它们被误当成全局必填：\n"
            + "\n".join("  !! " + p for p in problems)
        )

    def test_effective_from_task_48_does_not_apply_retroactively(self, e_slice: dict) -> None:
        """E slice 是 Task 47，追加必填项不追溯 —— 现状必须通过。"""
        assert _task_number(e_slice) == 47
        assert validate_slice_against_schema(e_slice, enforce_task48=False) == []

    def test_effective_from_task_48_bites_from_task_48_on(self, e_slice: dict) -> None:
        """同一份 slice 标成 Task 48 就必须被拒 —— 证明该键不是装饰。

        这是 `effective_from_task_48` 唯一的活体判据：Tasks 48–57 的 slice 若不带
        step 3 的二值结论，校验器当场拒绝，而不是等人工复核。
        """
        future = copy.deepcopy(e_slice)
        future["task"] = "Task 48"
        problems = validate_slice_against_schema(future)
        assert problems, "Task 48 起的 slice 缺 html_counterpart_verdict 却通过了校验"
        joined = "\n".join(problems)
        for field in FROZEN_TASK48_FLOOR["required_entry"]:
            assert field in joined, f"Task 48 追加必填项 {field} 未被校验器点名"

    def test_task_number_is_derived_not_guessed(self, e_slice: dict) -> None:
        assert _task_number({"task": "Task 57"}) == 57
        assert _task_number({"task": "Task 5"}) == 5
        assert _task_number({}) is None
        assert _task_number({"task": "no number here"}) is None

    def test_a_complete_pending_verdict_state_passes(self, e_slice: dict) -> None:
        """SR-3 **右支**的正例：齐备的待裁决态必须通过。

        没有这一条，右支就只有反例 —— 「null + 三字段齐备」到底算不算合法无从证明，而
        D/F 两份真实 slice 正是这个形态。左支的正例是 `reference_instance` 本身
        （E slice 的 entry 终态已定）。
        """
        pending = _as_pending_verdict(copy.deepcopy(e_slice))
        problems = validate_slice_against_schema(pending)
        assert problems == [], (
            "齐备的待裁决态（capability=null + stage + target + 非空 blocked_by）被拒 ⇒ "
            "SR-3 右支没生效，Tasks 49–57 每落一次都要新增一条豁免：\n"
            + "\n".join("  !! " + p for p in problems)
        )

    @pytest.mark.parametrize(
        "slice_rel", [_rel(p) for p in slice_paths()], ids=lambda r: Path(r).stem
    )
    def test_every_scanned_slice_passes_the_schema(self, slice_rel: str) -> None:
        """正例侧不止参照实例：`scan_glob` 命中的**每一份** slice 都要通过。

        🔴 `reference_instance` 仍是 E slice（`derived_from` 也仍指它，不动），但「schema 与
        事实脱节」这件事不能只由一份 slice 作证 —— G1 就是这么来的：严格校验器只被喂过
        E slice，D/F 两份带待裁决态的真实 slice 从没进过它的分母，于是同一条 SR-3 有两个
        互相矛盾的判官（范式校验器报违规，per-cycle 守卫放行），而严格的那个恰好不指向它们。

        与 `test_slice_schema_validator_coverage.py::test_every_slice_passes_the_json_nominated_validator`
        同判据、不同视角（那边守的是覆盖面与豁免登记，这边是 schema 的正例侧），且调用的是
        **同一个** `validate_slice_against_schema` —— 没有第二份实现，不会漂移。
        """
        slice_doc = json.loads((ROOT / slice_rel).read_text(encoding="utf-8"))
        problems = validate_slice_against_schema(slice_doc)
        assert problems == [], (
            f"{slice_rel} 通不过范式自己的 slice_schema（{len(problems)} 条）：\n"
            + "\n".join("  !! " + p for p in problems)
        )


# ════════════════════════════════════════════════════════════════════════════
# 判据四：slice_schema —— 反例（逐个必填字段都要能打红）
# ════════════════════════════════════════════════════════════════════════════
_ContainerGetter = Callable[[dict], Any]

#: 字段组 → 在 reference_instance 里的宿主容器。反例就是从这个容器里抽掉字段。
_SCHEMA_GROUPS: tuple[tuple[str, _ContainerGetter], ...] = (
    ("required_top_level", lambda s: s),
    ("required_slice_scope", lambda s: s["slice_scope"]),
    ("required_excluded_item", lambda s: s["slice_scope"]["excluded_from_slice"][0]),
    ("required_authoritative_templates", lambda s: s["authoritative_templates"]),
    ("required_template_file", lambda s: s["authoritative_templates"]["files"][0]),
    ("required_entry", lambda s: s["independent_entries"][0]),
    ("presence_required_value_may_be_null", lambda s: s["independent_entries"][0]),
    ("required_entry_adjudication", lambda s: s["independent_entries"][0]["adjudication"]),
    ("required_entry_evidence", lambda s: s["independent_entries"][0]["evidence"]),
    ("required_blocking_precondition", lambda s: s["blocking_preconditions"][0]),
    ("required_cross_entry_isolation", lambda s: s["cross_entry_isolation"]),
    ("required_honest_adjudication_summary", lambda s: s["honest_adjudication_summary"]),
    ("required_slice_counters", lambda s: s["honest_adjudication_summary"]["slice_counters"]),
)


def _drop(getter: _ContainerGetter, field: str) -> Callable[[dict], None]:
    def _mutate(slice_doc: dict) -> None:
        container = getter(slice_doc)
        assert isinstance(container, dict), f"反例构造失败：{field} 的宿主不是对象"
        assert field in container, (
            f"反例构造失败：reference_instance 的宿主里本来就没有 `{field}` —— "
            "正例侧应当先打红"
        )
        container.pop(field)
    return _mutate


def _blank_section(section: str) -> Callable[[dict], None]:
    def _mutate(slice_doc: dict) -> None:
        slice_doc[section] = {}
    return _mutate


#: one-of 组里在 reference_instance 里找不到宿主的字段（构造反例失败的记录）。
_ONE_OF_WITHOUT_HOST: list[str] = []


def _as_pending_verdict(slice_doc: dict) -> dict:
    """把 `reference_instance` 的首个 entry 就地改成**齐备的**待裁决态，返回同一份 dict。

    为什么要合成：E slice 的唯一 entry 终态已定（single_onlyoffice），SR-3 右支在真实
    参照实例里没有宿主。若不合成，右支的正反例都构造不出来 —— 而 D/F 两份真实 slice 正是
    这个形态。取值抄的是 D/F slice 的实际用法（`pipeline_entry_pending_definition_delivery`
    + target=bidirectional + 引用真实阻断项 id）。

    连带改掉 SR-2 与 SR-9 的两个计数：改了 capability 就得改摘要，否则合成体自带两条与
    待裁决态无关的违规，反例的归因会被污染（「打红了」但点名的是别的规则）。
    """
    entry = slice_doc["independent_entries"][0]
    previous = entry.get("capability")
    entry["capability"] = None
    if isinstance(entry.get("adjudication"), dict):
        entry["adjudication"]["honest_capability"] = None
    schema = load_paradigm_doc()["slice_schema"]
    blockers = [
        bp["id"] for bp in slice_doc.get("blocking_preconditions") or []
        if isinstance(bp, dict) and bp.get("id")
    ]
    seed: dict[str, Any] = {
        "capability_verdict_stage": "pipeline_entry_pending_definition_delivery",
        "capability_target": "bidirectional",
        "capability_target_blocked_by": blockers[:1] or ["BP-1"],
    }
    for field in schema["required_pending_verdict_fields"]:
        assert field in seed, (
            f"待裁决态新增了字段 `{field}` 但合成器没有给它取值 —— 正例会假红"
        )
        entry[field] = seed[field]
    summary = slice_doc.get("honest_adjudication_summary")
    if isinstance(summary, dict):
        key = f"adjudicated_as_{previous}"
        if key in summary and isinstance(summary[key], int):
            summary[key] -= 1
        counters = summary.get("slice_counters")
        if isinstance(counters, dict):
            counters[schema["pending_verdict_counter"]] = 1
    return slice_doc


def _pending_negative_cases() -> list[tuple[str, str, Callable[[dict], None]]]:
    """SR-3 右支的反例：待裁决态**不齐备**时必须仍被拒，且说明点名该字段。

    🔴 这一组是「不得简单放宽成 null 一律通过」的证人。三个「缺字段」的分母从 schema
    **现读**（新增 pending 字段自动获得反例）；另外四条是值层面的放宽形态（target 不在
    枚举内 / blocked_by 空数组 / stage 空白串 / 计数说谎），它们不是「缺键」，靠 presence
    判据一条都抓不到。
    """
    schema = load_paradigm_doc()["slice_schema"]
    cases: list[tuple[str, str, Callable[[dict], None]]] = []

    def _pending_then(
        field: str, tweak: Callable[[dict], None]
    ) -> Callable[[dict], None]:
        def _mutate(slice_doc: dict) -> None:
            _as_pending_verdict(slice_doc)
            tweak(slice_doc)
        return _mutate

    for field in schema["required_pending_verdict_fields"]:
        cases.append((
            f"pending:missing:{field}", field,
            _pending_then(field, lambda s, f=field: s["independent_entries"][0].pop(f)),
        ))
    cases.append((
        "pending:capability_target 不在枚举内", "capability_target",
        _pending_then(
            "capability_target",
            lambda s: s["independent_entries"][0].__setitem__("capability_target", "dual"),
        ),
    ))
    cases.append((
        "pending:capability_target_blocked_by 空数组", "capability_target_blocked_by",
        _pending_then(
            "capability_target_blocked_by",
            lambda s: s["independent_entries"][0].__setitem__(
                "capability_target_blocked_by", []
            ),
        ),
    ))
    cases.append((
        "pending:capability_verdict_stage 空白串", "capability_verdict_stage",
        _pending_then(
            "capability_verdict_stage",
            lambda s: s["independent_entries"][0].__setitem__(
                "capability_verdict_stage", "   "
            ),
        ),
    ))
    counter = schema["pending_verdict_counter"]
    cases.append((
        f"pending:SR-9 {counter} 计数说谎", counter,
        _pending_then(
            counter,
            lambda s, k=counter: s["honest_adjudication_summary"]["slice_counters"].__setitem__(
                k, 0
            ),
        ),
    ))
    return cases


def _negative_cases() -> list[tuple[str, str, Callable[[dict], None]]]:
    """`(case_id, 期望被点名的字段名, 变形函数)`，全部从 schema **现读**构造。

    现读的代价：把某个必填字段从 schema 里删掉，它自己的反例也会消失 ⇒ 由
    :class:`TestSliceSchemaFloor` 的地板判据独立兜住「不得缩水」。
    """
    schema = load_paradigm_doc()["slice_schema"]
    reference = load_reference_slice()
    cases: list[tuple[str, str, Callable[[dict], None]]] = []

    for group, getter in _SCHEMA_GROUPS:
        for field in schema.get(group, []):
            cases.append((f"{group}:{field}", field, _drop(getter, field)))

    for group in schema.get("required_blocking_precondition_one_of", []):
        for field in group:
            # 事实范式里两种形态各有代表：BP-1 用 consequence，BP-4 用 observable_consequences。
            hosts = [
                i for i, bp in enumerate(reference.get("blocking_preconditions") or [])
                if isinstance(bp, dict) and field in bp
            ]
            if not hosts:
                # 🔴 不在导入期 assert：一旦 schema 漂移（字段改名/组被换），import 期抛异常会让
                # 整个模块变成**收集错误** —— 报告里只剩一条无归因的 ERROR，真正该说话的
                # 地板判据与正例判据反而没机会跑（实测：M07 首轮因此判 WRONG-TEST）。
                # 改为登记下来，由 TestSliceSchemaFloor 里的独立判据点名。
                _ONE_OF_WITHOUT_HOST.append(field)
                continue
            index = hosts[0]
            cases.append((
                f"one_of:{field}@bp[{index}]",
                field,
                _drop(lambda s, i=index: s["blocking_preconditions"][i], field),
            ))

    for cs in schema.get("conditional_sections", []):
        section = cs["section"]
        present = section in reference
        for field in cs.get("required_fields", []):
            if present:
                cases.append((
                    f"conditional:{section}:{field}", field,
                    _drop(lambda s, sec=section: s[sec], field),
                ))
            else:
                # 条件段在事实范式里缺席（如 parent_duplicate_summary）⇒ 反例改为
                # 「把它放进来但不填必填字段」，否则该声明永远无人验证。
                cases.append((
                    f"conditional:{section}:{field}(injected-empty)", field,
                    _blank_section(section),
                ))
        if present and cs.get("required_table_fields"):
            for field in cs["required_table_fields"]:
                cases.append((
                    f"conditional:{section}.tables[0]:{field}", field,
                    _drop(lambda s, sec=section: s[sec]["tables"][0], field),
                ))
            for field in cs.get("required_row_identity_fields", []):
                cases.append((
                    f"conditional:{section}.tables[0].row_identity:{field}", field,
                    _drop(lambda s, sec=section: s[sec]["tables"][0]["row_identity"], field),
                ))
    cases.extend(_pending_negative_cases())
    return cases


_NEGATIVE_CASES = _negative_cases()


class TestSliceSchemaNegativeExamples:
    """**Validates: Requirements 12.4**

    反例侧：把正例**在内存里**抽掉任一必填字段后必须不通过，且违规说明必须**点名**
    该字段 —— 只要求「有违规」是不够的，那样某个字段的反例可能被别的规则误伤而通过，
    该字段仍是死声明。
    """

    @pytest.mark.parametrize(
        ("case_id", "field", "mutate"),
        _NEGATIVE_CASES,
        ids=[c[0] for c in _NEGATIVE_CASES],
    )
    def test_dropping_a_required_field_is_rejected(
        self, case_id: str, field: str, mutate: Callable[[dict], None], e_slice: dict
    ) -> None:
        broken = copy.deepcopy(e_slice)
        mutate(broken)
        problems = validate_slice_against_schema(broken)
        assert problems, f"{case_id}: 抽掉必填字段后仍然通过 ⇒ 该字段是死声明"
        assert any(field in p for p in problems), (
            f"{case_id}: 有违规但没有一条点名 `{field}` ⇒ 打红的是别的规则，"
            f"该字段仍无归因判据。实际违规：{problems}"
        )

    def test_the_negative_denominator_is_not_empty(self) -> None:
        assert len(_NEGATIVE_CASES) >= 60, (
            f"反例只有 {len(_NEGATIVE_CASES)} 条，疑似 schema 组名或宿主 getter 失效"
        )

    def test_behavioural_rules_bite_beyond_presence(self, e_slice: dict) -> None:
        """SR 系列是**行为**判据：字段都在但值互相矛盾时也必须被拒。"""
        checks: list[tuple[str, Callable[[dict], None], str]] = [
            (
                "SR-1 计数被篡改",
                lambda s: s["honest_adjudication_summary"].__setitem__("total_independent", 99),
                "SR-1",
            ),
            (
                "SR-2 摘要与明细脱节",
                lambda s: s["honest_adjudication_summary"].__setitem__(
                    "adjudicated_as_single_onlyoffice", 0
                ),
                "SR-2",
            ),
            (
                "SR-3 自造能力态",
                lambda s: s["independent_entries"][0].__setitem__("capability", "dual"),
                "capability_enum",
            ),
            (
                "SR-4 双口径",
                lambda s: s["independent_entries"][0]["adjudication"].__setitem__(
                    "honest_capability", "bidirectional"
                ),
                "SR-4",
            ),
            (
                "SR-5 裁 single 却挂 adapter",
                lambda s: s["independent_entries"][0].__setitem__("adapter_id", "excel:e1"),
                "SR-5",
            ),
            (
                "SR-6 bidirectional 却五项皆 null",
                lambda s: (
                    s["independent_entries"][0].__setitem__("capability", "bidirectional"),
                    s["independent_entries"][0]["adjudication"].__setitem__(
                        "honest_capability", "bidirectional"
                    ),
                ),
                "SR-6",
            ),
            (
                "SR-7 UNVERIFIABLE 无理由",
                lambda s: s["independent_entries"][0]["evidence"].__setitem__(
                    "unverifiable_reasons", []
                ),
                "SR-7",
            ),
            (
                "SR-8 模板挂到不存在的 entry",
                lambda s: s["authoritative_templates"]["files"][0].__setitem__(
                    "belongs_to_entry", "xlsx/does-not-exist"
                ),
                "SR-8",
            ),
            (
                "schema_version 漂移",
                lambda s: s.__setitem__("schema_version", "manifest-slice:v2"),
                "schema_version",
            ),
            (
                "行身份退回下标",
                lambda s: s["dynamic_row_identity"]["tables"][0]["row_identity"].__setitem__(
                    "kind", "array_index"
                ),
                "forbidden_identity_kinds",
            ),
        ]
        for label, mutate, token in checks:
            broken = copy.deepcopy(e_slice)
            mutate(broken)
            problems = validate_slice_against_schema(broken)
            assert any(token in p for p in problems), (
                f"{label}: 期望违规里出现 {token!r}，实际 {problems}"
            )


class TestSliceSchemaFloor:
    """**Validates: Requirements 12.4**

    地板判据：`slice_schema` 的必填字段集**只许增不许减**。

    没有它，「反例参数化从 schema 现读」这件事就有一个洞：删掉一个必填字段，它自己的
    反例随之消失 ⇒ 抽字段这个动作反而没有任何测试变红（守卫从被变异的源头推导期望值）。
    """

    def test_every_floor_group_still_exists(self, schema: dict) -> None:
        missing = [g for g in FROZEN_REQUIRED_FLOOR if g not in schema]
        assert not missing, f"schema 里这些字段组被整组删掉/改名了：{missing}"

    def test_required_field_groups_never_shrink(self, schema: dict) -> None:
        shrunk: dict[str, list[str]] = {}
        for group, floor in FROZEN_REQUIRED_FLOOR.items():
            current = set(schema.get(group, []))
            lost = sorted(floor - current)
            if lost:
                shrunk[group] = lost
        assert not shrunk, (
            "slice_schema 的必填字段集缩水了（放宽 schema 必须显式改本守卫的地板常量）：\n"
            + "\n".join(f"  !! {g} 丢了 {f}" for g, f in shrunk.items())
        )

    def test_one_of_groups_never_shrink(self, schema: dict) -> None:
        current = {tuple(g) for g in schema.get("required_blocking_precondition_one_of", [])}
        for group in FROZEN_ONE_OF_FLOOR:
            assert group in current, (
                f"one-of 组 {group} 消失了 ⇒ 阻断项可以不写后果了"
            )

    def test_every_one_of_field_has_a_host_in_the_reference_instance(self) -> None:
        """one-of 组的每个字段都要在事实范式里有代表，否则它的反例构造不出来。

        判据放在这里而不是导入期 assert：导入期抛异常 = 整模块收集错误，报告里只剩一条
        无归因的 ERROR，地板判据与正例判据都没机会说话（首轮 M07 实测踩过）。
        """
        assert _ONE_OF_WITHOUT_HOST == [], (
            f"one-of 字段 {_ONE_OF_WITHOUT_HOST} 在 reference_instance 里没有任何宿主 ⇒ "
            "它们是死声明（既没有正例也构造不出反例）"
        )

    def test_the_pending_verdict_contract_never_loosens(self, schema: dict) -> None:
        """SR-3 右支的三件事都不许悄悄放宽：字段名、语义 kind、SR-9 的计数器名。

        字段名由 :data:`FROZEN_REQUIRED_FLOOR` 兜住（只许增不许减），本条管**值**：
        语义 kind 与计数器名是值不是键，改了它们键一个不少而判据当场退化。
        """
        semantics = schema["pending_verdict_field_semantics"]
        for field, kind in FROZEN_PENDING_VERDICT_SEMANTICS.items():
            assert semantics.get(field) == kind, (
                f"待裁决态字段 `{field}` 的语义 kind 从 {kind!r} 变成 "
                f"{semantics.get(field)!r} ⇒ 判据被放宽（放宽必须显式改守卫常量）"
            )
        assert schema["pending_verdict_counter"] == FROZEN_PENDING_VERDICT_COUNTER, (
            f"SR-9 的计数器名变了：{schema['pending_verdict_counter']!r} ⇒ "
            "「待裁决条目数 == 计数」这条判据会指向另一个（或不存在的）计数器"
        )
        assert schema["pending_verdict_counter"] in schema["required_slice_counters"], (
            "SR-9 指向的计数器不在 required_slice_counters 里 ⇒ 它可以整键缺席，SR-9 空跑"
        )

    def test_the_sr3_rule_text_names_its_machine_declaration(self, schema: dict) -> None:
        """SR-3 的散文与它的机器声明不得漂移。

        判据形态与 `test_verdict_field_names_agree_across_three_declarations` 同源：同一件事
        声明两遍（`behavioral_rules[SR-3].rule` 的人读版 + `required_pending_verdict_fields` /
        `pending_verdict_field_semantics` 的机器版）时，漂移的那一份会变成死数据，且没人知道
        哪份是真的。校验器读机器版 ⇒ 散文必须点名机器版的组名与每个字段。
        """
        rule = next(r for r in schema["behavioral_rules"] if r["id"] == "SR-3")["rule"]
        assert "required_pending_verdict_fields" in rule, (
            "SR-3 的规则文本没点名 `required_pending_verdict_fields` ⇒ 读规则的人不知道"
            "「三字段」到底指哪三个，而校验器只认那个键"
        )
        for field in schema["required_pending_verdict_fields"]:
            assert field in rule, (
                f"SR-3 的规则文本没提 `{field}` ⇒ 机器声明加了字段而散文没跟（或反之）"
            )

    def test_pending_verdict_fields_are_conditional_not_global(self, schema: dict) -> None:
        """待裁决三字段必须**不**在 `required_entry` 里 —— 有条件必填，不是全局必填。

        设成全局必填会逼作者为终态已定的 entry 编造 stage/target/blocked_by
        （`conditional_sections.why_not_global` 里的同一条假绿源）；而 E slice 的唯一 entry
        终态已定、没有这三个字段，正例侧会当场打红。
        """
        base = set(schema["required_entry"]) | set(
            schema["effective_from_task_48"]["required_entry"]
        )
        overlap = sorted(base & set(schema["required_pending_verdict_fields"]))
        assert not overlap, (
            f"待裁决三字段 {overlap} 被列进无条件必填 ⇒ 终态已定的 entry 也得编造它们"
        )
        assert set(schema["pending_verdict_field_semantics"]) == set(
            schema["required_pending_verdict_fields"]
        ), (
            "required_pending_verdict_fields 与 pending_verdict_field_semantics 不是同一批"
            "字段 ⇒ 有字段没有语义（校验器 fail closed 会报违规）或有语义没人要求"
        )

    def test_task48_additions_never_shrink(self, schema: dict) -> None:
        effective = schema["effective_from_task_48"]
        for group, floor in FROZEN_TASK48_FLOOR.items():
            current = set(effective.get(group, []))
            assert floor <= current, f"effective_from_task_48.{group} 缩水：丢了 {sorted(floor - current)}"

    def test_task48_additions_are_strictly_additive(self, schema: dict) -> None:
        """`must_be_superset_of` 的机器含义：追加项非空且与基础项不重叠。"""
        effective = schema["effective_from_task_48"]
        for group in effective["must_be_superset_of"]:
            base = set(schema[group])
            extra = set(effective[group])
            assert extra, f"effective_from_task_48.{group} 为空 ⇒ 「Task 48 起加严」是空话"
            assert not (base & extra), (
                f"effective_from_task_48.{group} 与基础必填项重叠 {sorted(base & extra)} ⇒ "
                "追加项并非真正的加严"
            )
            assert (base | extra) > base

    def test_the_schema_targets_the_slice_version_it_validates(
        self, schema: dict, e_slice: dict
    ) -> None:
        assert schema["target_schema_version"] == e_slice["schema_version"]

    def test_applies_to_tasks_starts_after_the_two_grandfathered_slices(
        self, schema: dict
    ) -> None:
        """schema 适用范围从 Task 48 起 —— 与 `effective_from_task_48` 的名字一致。"""
        assert min(schema["applies_to_tasks"]) == 48
        assert max(schema["applies_to_tasks"]) == 57


# ════════════════════════════════════════════════════════════════════════════
# 判据五：AP-1 反模式（circular justification）—— JSON 点名的 detector
# ════════════════════════════════════════════════════════════════════════════
def _find_entry(slice_rel: str, entry_id: str) -> dict:
    """现读 slice，取出指定 entry（找不到即失败，不静默跳过）。"""
    slice_doc = json.loads((ROOT / slice_rel).read_text(encoding="utf-8"))
    for entry in slice_doc.get("independent_entries") or []:
        if entry.get("entry_id") == entry_id:
            return entry
    raise AssertionError(f"{slice_rel} 里找不到 entry {entry_id!r}")


def _single_onlyoffice_params() -> list:
    """全部 slice 里裁为 `single_onlyoffice` 的 entry，已登记的存量欠账带 strict xfail。

    参数化在**收集期**从磁盘现算 —— 新 slice / 新 entry 自动进入分母，不需要改守卫。
    """
    doc = load_paradigm_doc()
    ap1 = _ap(doc)
    inventory = ap1["known_debt_inventory"]
    owners = {
        (str(e["slice"]).replace("\\", "/"), str(e["entry_id"])): str(e.get("owner") or "")
        for e in inventory["entries"]
    }
    release = str(inventory.get("release_condition") or "")
    params: list = []
    for path in slice_paths(ap1.get("scan_glob")):
        slice_doc = json.loads(path.read_text(encoding="utf-8"))
        rel = _rel(path)
        for entry in slice_doc.get("independent_entries") or []:
            if entry.get("capability") != "single_onlyoffice":
                continue
            entry_id = str(entry.get("entry_id"))
            key = (rel, entry_id)
            marks: Any = ()
            if key in owners:
                marks = pytest.mark.xfail(
                    strict=True,
                    reason=(
                        f"已知存量欠账（AP-1 known_debt_inventory）· 责任方：{owners[key]}。"
                        f"解除条件：{release}"
                        " 本条由 D 循环整改与 E 循环回填任务兑现；strict=True ⇒ 欠账清掉后"
                        " XPASS 会打红，逼作者回来删标记。禁止改用 skip（skip 记为通过 = fail-open）。"
                    ),
                )
            params.append(
                pytest.param(rel, entry_id, marks=marks, id=f"{Path(rel).stem}|{entry_id}")
            )
    return params


_SINGLE_OO_PARAMS = _single_onlyoffice_params()

#: 合规样例：verdict 二值 + 非空 source_refs + 理由里有对端结论。
_CLEAN_SINGLE_OO_ENTRY: dict = {
    "entry_id": "xlsx/gt-synthetic-clean",
    "capability": "single_onlyoffice",
    "html_counterpart_verdict": "none",
    "html_counterpart_source_refs": [
        "audit-platform/frontend/src/components/workpaper/GtSynthetic.vue#mount",
        "backend/wp_templates/X/X1.xlsx!Sheet1!A1",
    ],
    "adjudication": {
        "honest_capability": "single_onlyoffice",
        "reason": "无 HTML 对端：宿主没有任何结构化持久化通道，HTML 侧不存在字段级对端。",
    },
}


class TestAntiPatternCircularJustification:
    """**Validates: Requirements 1.3, 12.1, 12.8, 12.9**

    AP-1：用「本任务应当交付的产物尚不存在」（无 adapter / contract / bundle / candidate /
    representation）当作裁 `single_onlyoffice` 的理由是**循环论证**。AC 12.8 的唯一合法
    判据是「无 HTML 对端」。

    实测存量：D 循环 slice 7 条 + E 循环 slice 1 条全裁 `single_onlyoffice`，
    `workpaper_sync_entry_manifest.json` 里这 8 条的 `html_store` 全是 `unresolved`
    ⇒ 本类会打红它们，**这是预期行为**，不放宽判据让它绿。处置 = strict xfail
    （见 :func:`_single_onlyoffice_params` 里逐条写明的责任方与解除条件）。
    """

    def test_the_scan_machinery_has_a_real_denominator(self) -> None:
        """扫描要有产出 —— 扫到 0 个 slice / 0 个 entry 会让本类恒绿。

        🔴 判据落在**扫描机制**（slice 文件数 + entry 总数）上，**不是**
        `len(_SINGLE_OO_PARAMS)`：后者会随欠账被兑现而下降到 0，那是本守卫追求的结果。
        拿它当下限就是「把错值当基线锁死」—— 2026-08-30 实测：并发的 D 循环回填把 7 条
        `single_onlyoffice` 改成带 `html_counterpart_verdict: exists` 的待裁决态后，
        初版的 `>= 8` 当场假红。
        """
        paths = slice_paths()
        assert len(paths) >= 2, f"scan_glob 只命中 {len(paths)} 个 slice 文件：{paths}"
        total = 0
        for path in paths:
            slice_doc = json.loads(path.read_text(encoding="utf-8"))
            total += len(slice_doc.get("independent_entries") or [])
        assert total >= 8, (
            f"全部 slice 合计只有 {total} 个独立 entry（D 循环 7 + E 循环 1 是已知下限）"
            " —— 疑似 scan_glob 或 independent_entries 键名失效"
        )

    @pytest.mark.parametrize(("slice_rel", "entry_id"), _SINGLE_OO_PARAMS)
    def test_single_onlyoffice_entry_states_its_html_counterpart(
        self, slice_rel: str, entry_id: str
    ) -> None:
        """裁 single_onlyoffice 必须带 step 3 的二值结论 + 来源，且理由不得是循环论证。"""
        problems = evaluate_single_onlyoffice_entry(_find_entry(slice_rel, entry_id))
        assert problems == [], (
            f"{slice_rel} 的 {entry_id} 违反 AC 12.8 / AP-1：\n"
            + "\n".join("  !! " + p for p in problems)
        )

    def test_violations_are_a_subset_of_the_registered_debt(self) -> None:
        """`subset_rule`：违规集合必须是 known_debt_inventory 的子集。

        清单内被修好 ⇒ 子集仍成立（不阻塞并发回填）；清单外出现新违规
        （Tasks 48–57 继续走老路）⇒ 本条**立刻打红**，且它没有 xfail 保护。
        """
        violations = scan_single_onlyoffice_violations()
        registered = debt_inventory_keys()
        new = sorted(set(violations) - registered)
        assert not new, (
            "以下 entry 裁了 single_onlyoffice 却没有 HTML 对端结论，且未登记为存量欠账：\n"
            + "\n".join(
                f"  ?? {slice_rel} :: {entry_id}\n"
                + "\n".join("       - " + p for p in violations[(slice_rel, entry_id)])
                for slice_rel, entry_id in new
            )
            + "\n\n处置：按 definition_producer_paradigm 的 step 3 调查 HTML 对端并给出"
              " none/exists 二值结论 + source_refs；不得以「adapter/contract/bundle 还不存在」"
              "为裁决理由（AP-1 循环论证）。"
        )

    def test_the_registered_debt_has_no_zombie_entries(self) -> None:
        """清单不得有僵尸项：登记的 slice/entry 必须真实存在。"""
        zombies: list[str] = []
        for slice_rel, entry_id in sorted(debt_inventory_keys()):
            path = ROOT / slice_rel
            if not path.exists():
                zombies.append(f"{slice_rel}（文件不存在）")
                continue
            slice_doc = json.loads(path.read_text(encoding="utf-8"))
            ids = {e.get("entry_id") for e in slice_doc.get("independent_entries") or []}
            if entry_id not in ids:
                zombies.append(f"{slice_rel} :: {entry_id}（slice 里没有这个 entry）")
        assert not zombies, (
            "known_debt_inventory 有僵尸项（登记了不存在的欠账，会让 xfail 标记挂空）：\n"
            + "\n".join("  !! " + z for z in zombies)
        )

    def test_the_debt_inventory_documents_its_own_release_condition(self) -> None:
        """欠账清单必须自带「为什么不用 skip」「子集规则」「解除条件」「逐条责任方」。"""
        inventory = _ap(load_paradigm_doc())["known_debt_inventory"]
        for key in ("why_xfail_not_skip", "subset_rule", "release_condition", "entries"):
            assert inventory.get(key), f"known_debt_inventory 缺 {key}"
        assert "skip" in inventory["why_xfail_not_skip"], (
            "why_xfail_not_skip 必须说明 skip 为什么不行（记为通过 = fail-open）"
        )
        for entry in inventory["entries"]:
            assert entry.get("owner"), f"欠账 {entry.get('entry_id')} 没有责任方"

    # ── 检测器的行为判据（合成输入，覆盖真实数据到不了的分支）─────────────
    def test_a_resolved_none_verdict_with_source_refs_is_clean(self) -> None:
        assert evaluate_single_onlyoffice_entry(copy.deepcopy(_CLEAN_SINGLE_OO_ENTRY)) == [], (
            "合规样例被误报 ⇒ 检测器有假阳性，存量红就无法归因"
        )

    def test_an_exists_verdict_forbids_single_onlyoffice(self) -> None:
        """AC 12.8 的核心：有 HTML 对端就不许裁 single_onlyoffice。

        真实数据里目前没有 `exists` 的 entry ⇒ 这条分支只能靠合成输入激活。
        没有它，`forbidden_verdict_for_single_onlyoffice` 就是死声明。
        """
        entry = copy.deepcopy(_CLEAN_SINGLE_OO_ENTRY)
        entry["html_counterpart_verdict"] = "exists"
        problems = evaluate_single_onlyoffice_entry(entry)
        assert any("exists" in p for p in problems), (
            f"verdict=exists 却被判合规 ⇒ AC 12.8 的唯一合法判据没被守住：{problems}"
        )

    @pytest.mark.parametrize("verdict", ["unresolved", "unknown", "", "   ", None])
    def test_unresolved_is_not_a_conclusion(self, verdict: Any) -> None:
        """AP-3：`unresolved` / `unknown` / 空值都是「还没查」，不是结论。"""
        entry = copy.deepcopy(_CLEAN_SINGLE_OO_ENTRY)
        entry["html_counterpart_verdict"] = verdict
        assert evaluate_single_onlyoffice_entry(entry), f"verdict={verdict!r} 被当成了结论"

    @pytest.mark.parametrize("refs", [None, [], ""])
    def test_a_conclusion_without_source_refs_is_rejected(self, refs: Any) -> None:
        entry = copy.deepcopy(_CLEAN_SINGLE_OO_ENTRY)
        entry["html_counterpart_source_refs"] = refs
        problems = evaluate_single_onlyoffice_entry(entry)
        assert any("source_refs" in p for p in problems), (
            f"refs={refs!r} 却通过 ⇒ 结论可以没有来源，等于自由文本"
        )

    def test_a_purely_circular_reason_is_caught(self) -> None:
        """理由只由「产物尚不存在」构成 ⇒ 循环论证（存量 D 循环 7 条的形态）。"""
        entry = copy.deepcopy(_CLEAN_SINGLE_OO_ENTRY)
        entry["adjudication"]["reason"] = (
            "No bidirectional adapter. No per-entry contract. "
            "No forcesave/durable ack pipeline."
        )
        assert reason_is_circular_only(
            entry, _ap(load_paradigm_doc())["circular_reason_markers"]
        ), "纯循环论证的理由没被识别"
        problems = evaluate_single_onlyoffice_entry(entry)
        assert any("循环论证" in p for p in problems), problems

    def test_a_reason_that_states_the_counterpart_is_not_flagged_as_circular(self) -> None:
        """反向：理由里同时给出对端结论时，不得因为提了一句「没有 adapter」就被判循环。

        没有这条，检测器会退化成「reason 里不许出现 adapter 字样」—— 那是字符串判据，
        会把已经调查清楚的 entry 一起误伤。
        """
        entry = copy.deepcopy(_CLEAN_SINGLE_OO_ENTRY)
        entry["adjudication"]["reason"] = (
            "无 bidirectional adapter / 无 per-entry contract。"
            "HTML 侧走 checklist_responses，OO 侧只按 sheet_name 打开模板副本；"
            "两侧没有字段级投影对端。"
        )
        assert not reason_is_circular_only(
            entry, _ap(load_paradigm_doc())["circular_reason_markers"]
        )
        problems = evaluate_single_onlyoffice_entry(entry)
        assert not any("循环论证" in p for p in problems), problems

    def test_moving_the_circular_claim_into_manifest_legacy_reasons_does_not_evade(self) -> None:
        """把循环论证从 `reason` 挪进 `manifest_legacy_reasons` 也不算绕过。"""
        entry = copy.deepcopy(_CLEAN_SINGLE_OO_ENTRY)
        entry["adjudication"]["reason"] = "见 manifest_legacy_reasons。"
        entry["adjudication"]["manifest_legacy_reasons"] = ["missing_adapter"]
        assert reason_is_circular_only(
            entry, _ap(load_paradigm_doc())["circular_reason_markers"]
        )

    # 「七条非法判据是否都能被 marker 认出」由
    # TestCrossKeyConsistency::test_every_illegal_criterion_has_a_detector_marker 承担
    # （那里用 latin token 子集匹配 —— 整串包含会因「approved / non-null / Task 17」这类
    # 修饰差异假红）。


# ════════════════════════════════════════════════════════════════════════════
# 四键互锁：同一件事被声明了两遍时，两份声明不得漂移
# ════════════════════════════════════════════════════════════════════════════
def _latin_tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", str(text).lower()))


def _suffixes(must_contain: Iterable[str], prefix: str) -> list[str]:
    return [m[len(prefix):] for m in must_contain if m.startswith(prefix)]


class TestCrossKeyConsistency:
    """**Validates: Requirements 12.1, 12.8**

    四个新键之间存在多处「同一件事说两遍」：step 3 的 `allowed_values` 与 AP-1 的
    `allowed_verdict_values`、step 4 的 `must_contain` 与 `required_entry_adjudication`、
    `effective_from_task_48.required_entry` 与 AP-1 的 `required_remedy_fields`……

    两份声明漂移 = 其中一份变成死数据（且没人知道哪份是真的）。这些互锁把它们钉在一起。
    """

    @staticmethod
    def _step(dpp: dict, number: int) -> dict:
        return next(s for s in dpp["steps"] if s["step"] == number)

    def test_verdict_field_names_agree_across_three_declarations(
        self, doc: dict, dpp: dict, schema: dict
    ) -> None:
        ap1 = _ap(doc)
        remedy = list(ap1["required_remedy_fields"])
        assert list(doc["adjudication_criteria"]["verdicts"]["single_onlyoffice"]["required_fields"]) == remedy, (
            "verdicts.single_onlyoffice.required_fields 与 AP-1.required_remedy_fields 漂移"
        )
        assert list(schema["effective_from_task_48"]["required_entry"]) == remedy, (
            "effective_from_task_48.required_entry 与 AP-1.required_remedy_fields 漂移 ⇒ "
            "schema 加严的字段和检测器要求的字段不是同一批"
        )
        must_contain = self._step(dpp, 3)["output"]["must_contain"]
        assert set(remedy) <= set(must_contain), (
            f"step 3 的 output.must_contain 未包含 {remedy} ⇒ 范式与检测器脱节"
        )

    def test_allowed_verdict_values_agree(self, doc: dict, dpp: dict) -> None:
        ap1 = _ap(doc)
        assert list(self._step(dpp, 3)["output"]["allowed_values"]) == list(
            ap1["allowed_verdict_values"]
        ), "step 3 的二值域与 AP-1 的 allowed_verdict_values 漂移"
        assert ap1["forbidden_verdict_for_single_onlyoffice"] in ap1["allowed_verdict_values"], (
            "被禁的 verdict 值必须是合法二值之一，否则这条禁令永不触发"
        )

    def test_step4_output_matches_the_schema_adjudication_fields(
        self, dpp: dict, schema: dict
    ) -> None:
        declared = set(_suffixes(self._step(dpp, 4)["output"]["must_contain"], "adjudication."))
        assert declared == set(schema["required_entry_adjudication"]), (
            f"step 4 声明的裁决字段 {sorted(declared)} 与 slice_schema 的 "
            f"{sorted(schema['required_entry_adjudication'])} 不一致"
        )

    def test_step1_output_matches_the_schema_slice_scope_fields(
        self, dpp: dict, schema: dict
    ) -> None:
        declared = set(_suffixes(self._step(dpp, 1)["output"]["must_contain"], "slice_scope."))
        assert declared <= set(schema["required_slice_scope"]), (
            f"step 1 要求的 slice_scope 字段 {sorted(declared)} 不在 schema 的必填集里"
        )
        assert "selection_rule" in declared, "step 1 必须要求 selection_rule（可复算的清单）"

    def test_step2_output_matches_the_schema_template_fields(
        self, dpp: dict, schema: dict
    ) -> None:
        must = self._step(dpp, 2)["output"]["must_contain"]
        file_fields = set(_suffixes(must, "files[]."))
        assert file_fields <= set(schema["required_template_file"]), (
            f"step 2 要求的模板文件字段 {sorted(file_fields)} 不在 schema 的必填集里"
        )
        bare = {m for m in must if "." not in m and "[" not in m}
        assert bare <= set(schema["required_authoritative_templates"])

    def test_step12_output_matches_the_schema_counters(self, dpp: dict, schema: dict) -> None:
        must = self._step(dpp, 12)["output"]["must_contain"]
        summary_fields = set(_suffixes(must, "honest_adjudication_summary."))
        assert summary_fields <= set(schema["required_honest_adjudication_summary"])
        bp_fields = set(_suffixes(must, "blocking_preconditions[]."))
        effective = set(schema["effective_from_task_48"]["required_blocking_precondition"])
        assert bp_fields <= effective, (
            f"step 12 要求的阻断项字段 {sorted(bp_fields)} 不在 Task 48 追加必填集里 ⇒ "
            "范式要求的东西 schema 不校验"
        )

    def test_ui_obligation_points_at_the_real_step(self, doc: dict, dpp: dict) -> None:
        ui = doc["adjudication_criteria"]["ui_obligation"]
        by_name = {s["name"]: s["step"] for s in dpp["steps"]}
        assert ui["paradigm_step"] == by_name["enforce_honest_mode_visibility"], (
            "ui_obligation.paradigm_step 与 enforce_honest_mode_visibility 的实际序号不一致"
        )
        assert set(ui["derived_from_ac"]) == {"1.4", "1.5"}

    def test_bidirectional_requires_the_producer_steps_that_exist(
        self, doc: dict, dpp: dict
    ) -> None:
        numbers = {s["step"] for s in dpp["steps"]}
        required = doc["adjudication_criteria"]["verdicts"]["bidirectional"]["required_paradigm_steps"]
        assert set(required) <= numbers, f"bidirectional 引用了不存在的步骤：{required}"
        assert required == sorted(required) and required[-1] - required[0] == len(required) - 1, (
            f"bidirectional 要求的步骤应当是连续区间，实际 {required}"
        )
        by_number = {s["step"]: s["name"] for s in dpp["steps"]}
        assert by_number[required[0]] == "publish_authority_model"
        assert by_number[required[-1]] == "emit_per_scenario_evidence"

    def test_every_illegal_criterion_has_a_detector_marker(self, doc: dict) -> None:
        """七条「非法判据」每条都要能被至少一个 circular marker 认出来。

        判据用 latin token 子集而不是整串包含：两侧措辞有「approved / non-null / Task 17」
        之类的修饰差异，整串比对会假红；但 token 子集仍然要求两侧说的是同一件事。
        """
        ap1 = _ap(doc)
        markers = [(m, _latin_tokens(m)) for m in ap1["circular_reason_markers"]]
        uncovered: list[str] = []
        for illegal in doc["adjudication_criteria"]["verdicts"]["single_onlyoffice"]["illegal_criteria"]:
            tokens = _latin_tokens(illegal)
            if not any(mt and mt <= tokens for _, mt in markers):
                uncovered.append(illegal)
        assert not uncovered, (
            "以下非法判据登记了却检测不到（写进理由也不会被 AP-1 抓到）：\n"
            + "\n".join("  !! " + u for u in uncovered)
        )

    def test_the_paradigm_registry_gap_list_and_the_producer_steps_agree(
        self, doc: dict, dpp: dict
    ) -> None:
        """`does_not_cover` 的每一条都必须能对上一个 producer 步骤的名字或活动键。"""
        activity_keys = set(dpp["activity_coverage"]["activities"])
        step_names = {s["name"] for s in dpp["steps"]}
        assert activity_keys, "activity_coverage.activities 为空"
        # 活动键与步骤名不必逐字相同，但活动数不得少于步骤覆盖数，且每个键都要有归属
        assert len(activity_keys) >= len(step_names) - 2, (
            "活动键数量明显少于步骤数 —— 说明有步骤没有任何活动归属"
        )


# ════════════════════════════════════════════════════════════════════════════
# 反向自检：判据自己必须能被「故意写错」打红
# ════════════════════════════════════════════════════════════════════════════
class TestReverseSelfChecks:
    """**Validates: Requirements 12.4**

    memory 铁律：每写完守卫必做变异检验，「没打红 = 守卫有缺陷，不是代码没问题」。
    这里把上面每条判据的核心函数喂**合成的坏输入**，确认它们真的会报。
    """

    def test_a_back_edge_is_reported(self) -> None:
        steps = [
            {"step": 1, "name": "a", "blocks": [2]},
            {"step": 2, "name": "b", "blocks": [1]},
        ]
        problems = find_edge_violations(steps)
        assert any("回边" in p for p in problems), problems

    def test_a_self_loop_is_reported(self) -> None:
        steps = [{"step": 1, "name": "a", "blocks": [1]}]
        assert any("自环" in p for p in find_edge_violations(steps))

    def test_an_unknown_target_is_reported(self) -> None:
        steps = [{"step": 1, "name": "a", "blocks": [9]}]
        assert any("不存在" in p for p in find_edge_violations(steps))

    def test_missing_blocks_is_reported(self) -> None:
        assert find_edge_violations([{"step": 1, "name": "a"}])

    def test_cycle_detection_finds_a_synthetic_cycle(self) -> None:
        steps = [
            {"step": 1, "name": "a", "blocks": [2]},
            {"step": 2, "name": "b", "blocks": [3]},
            {"step": 3, "name": "c", "blocks": [1]},
        ]
        cycles = find_cycles(steps)
        assert cycles, "三节点环没被 DFS 找到"
        assert cycles[0][0] == cycles[0][-1], f"环路径首尾应相同：{cycles[0]}"

    def test_cycle_detection_is_quiet_on_a_forward_only_graph(self) -> None:
        """反向：无环图不得误报（否则真实数据恒红，判据失去意义）。"""
        steps = [
            {"step": 1, "name": "a", "blocks": [2, 3]},
            {"step": 2, "name": "b", "blocks": [3]},
            {"step": 3, "name": "c", "blocks": []},
        ]
        assert find_cycles(steps) == []

    def test_ac_comparison_is_equality_not_containment(self, criteria: dict) -> None:
        """逐字比对必须是 `==`：截掉尾字的版本用 `in` 仍会通过，用 `==` 必须失败。"""
        item = next(i for i in criteria["acceptance_criteria"] if i["ac"] == "12.8")
        disk = ac_lines_on_disk("12.8")[0]
        truncated = item["text"][:-1]
        assert truncated in disk, "构造前提被破坏：截尾串应当仍是磁盘原文的子串"
        assert truncated != disk, "截尾串与磁盘原文相等 ⇒ 判据无法区分截断"

    def test_ac_comparison_catches_a_one_character_change(self, criteria: dict) -> None:
        item = next(i for i in criteria["acceptance_criteria"] if i["ac"] == "1.3")
        disk = ac_lines_on_disk("1.3")[0]
        mutated = disk.replace("SHALL", "SHOULD", 1)
        assert mutated != item["text"], "改一字后仍与登记原文相等 ⇒ 比对没有区分度"

    def test_ac_locator_requires_a_unique_line(self) -> None:
        """同一 AC 前缀出现两次时必须能被发现（`ac_lines_on_disk` 返回全部命中）。"""
        text = "1.3. a\n1.3. b\n"
        assert ac_lines_on_disk("1.3", text) == ["a", "b"]
        assert ac_lines_on_disk("9.9", text) == []

    def test_raw_block_extractor_is_string_aware(self) -> None:
        """块内字符串里的花括号不得影响配对（朴素计数在此会截错）。"""
        raw = '{\n  "k": {\n    "s": "a { unbalanced",\n    "t": "}"\n  },\n  "after": 1\n}'
        block = extract_raw_json_block(raw, "k")
        assert block.endswith("}"), block
        assert "after" not in block, f"块被截到了兄弟键上：{block!r}"
        assert json.loads("{" + block + "}")["k"]["t"] == "}"

    def test_raw_block_extractor_refuses_ambiguous_keys(self) -> None:
        raw = '{"k": {"a": 1}, "x": {"k": {"b": 2}}}'
        with pytest.raises(ValueError):
            extract_raw_json_block(raw, "k")

    def test_raw_block_digest_changes_when_the_block_changes(self) -> None:
        base = load_paradigm_raw()
        tampered = base.replace('"name": "identify_legacy"', '"name": "identify_legacyX"', 1)
        assert tampered != base, "构造前提被破坏：锚点串没找到"
        assert raw_block_digest(tampered) != FROZEN_PARADIGM_RAW_SHA256, (
            "改了冻结块的字节，digest 却没变 ⇒ 字节锁是装饰"
        )

    def test_raw_block_digest_ignores_only_line_endings(self) -> None:
        base = load_paradigm_raw()
        crlf = base.replace("\n", "\r\n")
        assert raw_block_digest(crlf) == FROZEN_PARADIGM_RAW_SHA256, (
            "CRLF checkout 会被误判成「范式被改了」"
        )

    def test_the_schema_validator_is_not_vacuous(self, e_slice: dict) -> None:
        """校验器对完全空对象必须报一堆违规（防它被改成恒返回空列表）。"""
        problems = validate_slice_against_schema({})
        assert len(problems) >= len(FROZEN_REQUIRED_FLOOR["required_top_level"]), (
            f"空 slice 只报了 {len(problems)} 条违规 ⇒ 校验器被短路了"
        )

    def test_the_detector_is_not_vacuous(self) -> None:
        """检测器对空 entry 必须报违规（防它被改成恒返回空列表）。"""
        assert evaluate_single_onlyoffice_entry({}) , "空 entry 被判合规 ⇒ 检测器被短路"
