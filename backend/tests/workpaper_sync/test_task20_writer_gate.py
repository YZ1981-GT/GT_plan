# -*- coding: utf-8 -*-
"""Task 20：writer / version domain 门的判据本身是否可信。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 1 Task 20
Requirements: 2.1, 2.2, 2.12, 9.11 · Property 4, Property 61

Task 20 是一道**门**。门的危险不是「一直红」，而是「因为某个谓词被放宽而变绿」。所以本文件
守的不是「计数是否为零」，而是三件事：

1. **有测试** 这条证据必须落在**调用点**上。Task 19 实测到两条 false credit：一条新守卫只
   提到了 `wp_storage_service`，同模块**没被碰过**的 `list_versions` 就被记成「有
   characterization 测试」；`WpMigrationService.rollback` 被记在一条用 `copy.deepcopy`
   模拟回滚、**从未调用**它的属性测试上。两条同一形态 —— 判据从未到达调用点。
2. **artifact-snapshot 是正面类别，不是豁免**。`WpStorageService.save_version` 把**当前**
   文件复制进 `.versions/`，内容零变化 ⇒ 它没有业务内容可提交，`bypasses_unified_commit`
   对它永远到不了零。给它一个**从目标路径派生**的类别是合法的；把这一行悄悄排除掉不是。
   类别自带义务（须裁决 + 须读统一计数器 + 不得碰 legacy 字段），义务能打红。
3. **文档与门必须双向对齐到全部 14 条准则，且正文冻结的计数由门现算派生**。门的
   `has_debt` 是 14 条的 `any()`；Task 20 正文原先只点名五条，判据也只做单向断言（「正文点名
   的都要有 key」）—— 于是「门里多一条、文档里没人认领」不会红，「没评过」与「评过且为零」
   在报告里仍然长得一样。现在两边都能反驳对方（§5），且正文里那 14 个计数是**冻结的红基线**，
   与 `evaluate_gate()` 逐条比对：数字写错红，源码变了没同步更新正文也红。
4. **「移交」不得变成「无人守」**。`多 resolver writer=0` 从 Task 20 移到 Task 30，Task 30
   实测后又移到 Task 71（两跳的成环理由分别见 tasks.md Task 20 / Task 30 正文），但门
   **仍在算** `multi_resolver` —— 当前归属方要靠它验零。所以准则换了归属而不是离场：本文件
   按现归属单独立判据（§6），并把「归属」与**整条移交链**都交给 tasks.md 派生，doc 与本文件
   的分组一旦不一致就红。`unadjudicated_writer` 等七条移交 Task 74 时套用同一形态。
5. **`writes_business_content` 刻意不参与 `bypasses_unified_commit`**。清册里 14 个 writer
   行「零业务内容事实」纯粹是因为它们的 artifact 目标追不到（`artifact_write_targets` 全
   `unclassified`）。把「没量到内容」当成「没有权威内容」就是一条 fail-open 豁免 —— 生成器里
   那段注释曾经承诺了这件事而算式没做，现已改成显式声明「刻意不参与」，并在 §2 末尾立行为级
   判据 + 变异 M21 锁死。

反向变异脚本：`backend/scripts/diagnose/mutate_task20_writer_gate_guards.py`。
"""
from __future__ import annotations

import ast
import copy
import importlib.util
import json
import re
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

_REPO = Path(__file__).resolve().parents[3]
_GENERATOR_PATH = (
    _REPO / "backend" / "scripts" / "gen" / "generate_workpaper_writer_inventory.py"
)
_GATE_PATH = (
    _REPO / "backend" / "scripts" / "check" / "check_workpaper_writer_revision_gate.py"
)
_INVENTORY_PATH = _REPO / "backend" / "data" / "workpaper_writer_inventory.json"
_OVERLAY_PATH = _REPO / "backend" / "data" / "workpaper_writer_domain_overlay.json"

_STORAGE = "app.services.wp_storage_service"
_SAVE_VERSION = f"{_STORAGE}::WpStorageService.save_version"
_LIST_VERSIONS = f"{_STORAGE}::WpStorageService.list_versions"
_MIGRATION_ROLLBACK = "app.services.wp_migration_service::WpMigrationService.rollback"
#: 那条用 `copy.deepcopy` 模拟回滚、从未调用 `rollback()` 的属性测试。
_DEEPCOPY_ROLLBACK_TEST = "backend/tests/test_wp_template_migration_property.py"
#: Task 20 正文冻结的红基线里那 **14** 条准则标签 → 门里的 issue key。
#:
#: 标签一侧（`X=N` 那串中文）由 `_task20_criteria_labels_from_tasks_md()` 从 tasks.md 现场
#: 解析并与本表 key 集**双向**比对，所以「点名几条」不是这里手抄的数字；label → issue key 的
#: 映射是人工裁决（散文标签与门内 key 之间没有可派生的对应关系），故留在源码里。
#:
#: 🔴 表从 5 条扩到 14 条是本轮整改的核心：门的 `has_debt` 由 14 条 `any()` 构成，而旧表只
#: 覆盖 5 条 ⇒ 剩下 9 条「在通过条件里、不在验收条件里」，文档与判据的静默分叉入口就在这里。
#: 现在 `set(_GATE_CRITERIA.values()) == set(evaluate_gate(...))` 双向成立：门里多一条、
#: 文档里少一条，两个方向都红。
_GATE_CRITERIA = {
    "生产写路径未裁决": "unadjudicated_writer",
    "绕过统一 commit": "bypasses_unified_commit",
    "resolver 未裁决": "unadjudicated_resolver",
    "写 legacy 版本字段": "writes_legacy_version_field",
    "自有直接 commit": "owns_direct_commit",
    "只有非 canonical resolver": "non_canonical_resolver_only",
    "writer 无 characterization 测试": "writer_without_characterization_test",
    "多 resolver writer": "multi_resolver",
    "bidirectional projection-only/双 revision": "keeps_legacy_write_path_beside_unified_commit",
    "after-save 增 revision": "after_save_still_increments_revision",
    "representation upgrade 增 business revision": (
        "representation_upgrade_increments_business_revision"
    ),
    "artifact-snapshot writer 不可验证": "artifact_snapshot_writer_not_verifiable",
    "retired writer 不可验证": "retired_writer_not_verifiable",
    "缺必需 domain": "missing_required_domain",
}
#: 已从 Task 20 移交出去的准则（移交链 Task 20 → Task 30 → Task 71）。**移交不是离场**：
#: 门必须仍然评估它（当前归属方靠它验零），所以它在这里另立一张表而不是被删掉 ——
#: 一条准则从所有分母里消失，和它归零长得一样。归属任务号不写在表里，由 tasks.md 派生。
#:
#: 🔴 它同时也在 `_GATE_CRITERIA` 里（冻结基线必须报出它的实测计数 4），这**不是重复登记**：
#: `_GATE_CRITERIA` 回答「门评没评、算得对不对」，本表回答「谁负责清零」。旧版判据靠
#: 「`多 resolver writer` 不得出现在 Task 20 的准则行里」来表达移交，那等于用「从基线里消失」
#: 冒充「换了归属」—— 与 fail-open 同形，故改为：它必须留在基线里，但归属行必须指向别的任务。
_RELOCATED_CRITERIA = {
    "多 resolver writer": "multi_resolver",
}
#: 当前归属方正文点名的、必须清零的那 4 条 resolver 行（`wp_onlyoffice_router`）。从 tasks.md
#: 现场解析，不在这里抄；解析结果与门实测报出的行逐个比对。
_TASKS_MD = (
    _REPO
    / ".kiro"
    / "specs"
    / "workpaper-html-onlyoffice-bidirectional-writeback-closure"
    / "tasks.md"
)
_REQUIREMENTS_MD = _TASKS_MD.parent / "requirements.md"
_DESIGN_MD = _TASKS_MD.parent / "design.md"
_TASK_HEAD_RE = re.compile(r"^- \[[ x~\-]\] (\d+)\.\s")
#: `**`多 resolver writer=0`（gate issue key `multi_resolver`…` —— 门内 key 的文档侧字面量。
_GATE_ISSUE_KEY_RE = re.compile(r"gate issue key `([a-z_]+)`")
#: 「已移交 Task N」= 本任务**放手**；「自 Task M 移交至本门」= 本任务**接手**。
#:
#: 🔴 两条措辞都只描述**本任务自己的**交接动作。追述别人那一跳时 tasks.md 用的是
#: 「已**再**移交 Task 71」/「移交链 Task 20 → Task 30 → Task 71」，两者都不匹配这两个
#: 正则 —— 否则一句历史注解会改写归属推导。移交链因此由**放手/接手事件的文档顺序**
#: 拼出来（见 `_gate_issue_key_homing`），而不是从散文里读一条箭头串。
_RELINQUISH_RE = re.compile(r"已移交 Task (\d+)")
_ASSUME_RE = re.compile(r"自 Task (\d+) 移交至本门")
#: Task 20「当期红基线（冻结）」那行里的 `标签=计数` 串（`生产写路径未裁决=236、…=0、…`）。
#:
#: 🔴 计数从 `=0` 放宽到 `=(\d+)` 是本轮整改的另一半：旧形态只能表达「已归零」，于是 Task 20
#: 的正文与实测（236 / 261）自相矛盾，而正文第 4 条又写着「本门未过」。现在正文冻结的是**实测
#: 红基线**，`test_the_frozen_red_baseline_is_derived_from_the_live_gate` 把它和门现算的计数
#: 逐条比对 —— 数字不再是手抄常量（否则源码一变就与文档静默分叉，平台假绿第③源）。
_CRITERION_LABEL_RE = re.compile(r"([^、；;]+)=(\d+)")
#: 基线行末尾的 `合计 N 条 blocking facts` —— 与 14 条之和交叉验证，防「逐条对了总数写错」。
_BASELINE_TOTAL_RE = re.compile(r"合计 (\d+) 条 blocking facts")
#: 归属行的分段：`归属 Task 74：`a`、`b`；`。分段边界用 `；`/`。`，段内只有反引号包住的 key。
_HOMING_SEGMENT_RE = re.compile(r"归属 Task (\d+)：([^；。]+)")
#: 反引号里的门内 issue key 字面量（与 `_GATE_ISSUE_KEY_RE` 不同：本条**不要求**
#: `gate issue key` 前缀，只在归属行的分段内使用，故不会把散文里的其他反引号词收进来）。
_BACKTICKED_KEY_RE = re.compile(r"`([a-z_]+)`")


def _task_bodies() -> dict[str, list[str]]:
    """tasks.md → {任务号: 该任务正文的行列表}。行首锚定，不用字符窗口。"""
    bodies: dict[str, list[str]] = {}
    current: list[str] | None = None
    for line in _TASKS_MD.read_bytes().decode("utf-8").split("\n"):
        head = _TASK_HEAD_RE.match(line)
        if head:
            current = bodies.setdefault(head.group(1), [])
            current.append(line)
            continue
        if line.startswith("#") or line.startswith("- "):
            current = None
            continue
        if current is not None:
            current.append(line)
    assert bodies, "tasks.md 一个任务都没解析出来 —— 本文件的 doc 派生判据会全部空跑"
    return bodies


def _frozen_red_baseline_from_tasks_md() -> tuple[dict[str, int], int]:
    """Task 20 冻结的当期红基线 → ``({准则标签: 计数}, 合计)``。

    锚在「当期红基线（冻结）」上，行首锚定 + 现场解析，不抄常量。返回的计数由
    `test_the_frozen_red_baseline_is_derived_from_the_live_gate` 与 `evaluate_gate()` 的实测
    结果逐条比对，所以这里解析出的每一个数字都必须能被门反驳。
    """
    for line in _task_bodies()["20"]:
        if "当期红基线（冻结）" not in line:
            continue
        baseline = {
            m.group(1).strip(): int(m.group(2)) for m in _CRITERION_LABEL_RE.finditer(line)
        }
        assert baseline, f"基线行解析不出任何「标签=计数」：{line[:160]}"
        total = _BASELINE_TOTAL_RE.search(line)
        assert total, f"基线行没有「合计 N 条 blocking facts」：{line[:160]}"
        return baseline, int(total.group(1))
    raise AssertionError("Task 20 正文里找不到「当期红基线（冻结）」那一行")


def _task20_criteria_labels_from_tasks_md() -> set[str]:
    """Task 20 正文点名的准则标签集 —— 现在等于冻结基线那一行点名的 14 条。"""
    return set(_frozen_red_baseline_from_tasks_md()[0])


def _gate_criteria_homing_from_tasks_md() -> dict[str, str]:
    """Task 20「14 条准则的归属」行 → ``{门内 issue key: 归属任务号}``。

    与 `_gate_issue_key_homing()` 是**两套独立派生**，故意的：后者只认两句显式交接语
    （`已移交 Task N` / `自 Task M 移交至本门`），描述的是**交接事件**；本函数读的是一张
    全量归属表，描述的是**当前状态**。两者在同一个 key 上不一致即红（见
    `test_the_criteria_homing_agrees_with_tasks_md`）—— 一份「谁负责清零」的答案有两个来源
    且都能各自解析成功、谁都不红，正是第一跳漂移的形态。
    """
    for line in _task_bodies()["20"]:
        if "14 条准则的归属" not in line:
            continue
        homing: dict[str, str] = {}
        for task, segment in _HOMING_SEGMENT_RE.findall(line):
            keys = _BACKTICKED_KEY_RE.findall(segment)
            assert keys, f"「归属 Task {task}」这一段里没有任何 issue key：{segment[:120]}"
            for key in keys:
                assert key not in homing, (
                    f"`{key}` 在归属行里出现两次（Task {homing[key]} 与 Task {task}）—— "
                    "「谁负责清零」不可有两个答案"
                )
                homing[key] = task
        assert homing, f"归属行解析不出任何 `归属 Task N：` 分段：{line[:160]}"
        return homing
    raise AssertionError("Task 20 正文里找不到「14 条准则的归属」那一行")


def _gate_issue_key_homing() -> tuple[dict[str, str], dict[str, list[str]], dict[str, list[str]]]:
    """从 tasks.md 派生每个门内 issue key 的**归属**与**整条移交链**。

    返回 ``(homed, relinquished, assumed)``：``homed[key]`` 是该 key 当前归属的任务号；
    ``relinquished[key]`` 是按文档顺序放手过它的任务号**列表**；``assumed[key]`` 同理是
    接手过它的任务号列表。

    判别只看两句显式交接语（`已移交 Task N` / `自 Task M 移交至本门`），因为「Task 20、
    Task 30、Task 71 都提到了 `multi_resolver`」本身分不出谁在守它 —— 这正是第一跳漂移的
    形态。

    🔴 三个返回值都是**列表而不是单值**：这条 criterion 已经移交两次（20 → 30 → 71），
    单值 dict 会被第二跳静默覆盖成 `relinquished={key: "30"}`，第一跳从判据里消失，
    于是「移交链」这件事在守卫里再也不可核对 —— 而它正是下一轮复盘最先要问的东西。
    """
    homed: dict[str, str] = {}
    relinquished: dict[str, list[str]] = {}
    assumed: dict[str, list[str]] = {}
    for task, body in _task_bodies().items():
        for line in body:
            keys = _GATE_ISSUE_KEY_RE.findall(line)
            if not keys:
                continue
            hand_off = _RELINQUISH_RE.search(line)
            take_over = _ASSUME_RE.search(line)
            for key in keys:
                if hand_off:
                    relinquished.setdefault(key, []).append(task)
                    homed[key] = hand_off.group(1)
                elif take_over:
                    assumed.setdefault(key, []).append(task)
                    homed.setdefault(key, task)
                else:
                    homed.setdefault(key, task)
    return homed, relinquished, assumed


def _load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def generator() -> ModuleType:
    return _load_module("task20_writer_inventory_generator", _GENERATOR_PATH)


@pytest.fixture(scope="module")
def gate() -> ModuleType:
    return _load_module("task20_writer_revision_gate", _GATE_PATH)


@pytest.fixture(scope="module")
def inventory() -> dict[str, Any]:
    return json.loads(_INVENTORY_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def source_scan(generator: ModuleType) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    """一次 AST 走查，`(分类后的行, 每个函数的事实)`。

    第二项是 §7 的分母判据要的：它含**每一个**被走查到的函数，所以「生成器实际走过哪些
    模块」可以从它反推，而 `rows` 只剩 writer/resolver，反推不出发现面。
    """
    return generator.collect_source_facts()


@pytest.fixture(scope="module")
def regenerated(
    generator: ModuleType,
    source_scan: tuple[list[dict[str, Any]], dict[str, dict[str, Any]]],
) -> dict[str, Any]:
    """现场从源码重新推导的清册。

    🔴 清册级判据必须读**这个**，不是磁盘上那份。变异检验实测（M06）：把 derivation 放宽
    后，磁盘清册一个字节没动 ⇒ 所有只读磁盘的判据照旧全绿，放宽悄悄通过。磁盘那份与本份
    相等由 `test_workpaper_writer_inventory.py::test_inventory_on_disk_matches_the_ast`
    保证，所以这里读源码不会漏掉「有人手改了清册」这一面。
    """
    rows, function_facts = source_scan
    overlay = json.loads(_OVERLAY_PATH.read_text(encoding="utf-8"))
    return generator.build_inventory(rows, overlay, function_facts)


@pytest.fixture(scope="module")
def overlay() -> dict[str, Any]:
    return json.loads(_OVERLAY_PATH.read_text(encoding="utf-8"))


def _row(inventory: dict[str, Any], writer_id: str) -> dict[str, Any]:
    for entry in inventory["entries"]:
        if entry["writer_id"] == writer_id:
            return entry
    raise AssertionError(f"inventory has no row {writer_id}")


def _invoked(generator: ModuleType, source: str) -> set[str]:
    """跑真实谓词：一段合成测试源码「调用」了哪些 `module::qualname`。"""
    return generator._resolved_calls_in_test(ast.parse(source))


def _facts_of(generator: ModuleType, source: str, function_name: str) -> dict[str, Any]:
    tree = ast.parse(source)
    for qualname, node in generator._iter_functions(tree):
        if qualname.rsplit(".", 1)[-1] == function_name:
            return generator._collect_facts(node).as_dict()
    raise AssertionError(f"synthetic source has no function {function_name}")


def _synthetic_row(
    generator: ModuleType,
    *,
    writer_id: str,
    source: str,
    function_name: str,
    kind: str = "writer_resolver",
) -> dict[str, Any]:
    module, qualname = writer_id.split("::")
    return {
        "writer_id": writer_id,
        "module": module,
        "source_path": f"backend/app/{module.replace('.', '/')}.py",
        "qualname": qualname,
        "line": 1,
        "is_async": True,
        "kind": kind,
        "delegates_to_content_writer": [],
        "facts": _facts_of(generator, source, function_name),
        "characterization_tests": [],
    }


def _synthetic_inventory(
    generator: ModuleType,
    rows: list[dict[str, Any]],
    *,
    adjudications: dict[str, Any] | None = None,
    lane: list[dict[str, Any]] | None = None,
    unified_companion: bool = True,
) -> dict[str, Any]:
    """真跑 `build_inventory`，再挂上一条最小的 upgrade lane。

    verdict 由生产 derivation 算出来，不是测试里手抄的 —— 否则改 derivation 时守卫不会红。

    `unified_companion`：门刻意在「零个统一入口调用方」时抛错（那种分母下双 revision 准则
    恒为零）。合成清册因此默认带一条干净的统一入口行当分母，它自己不触发任何准则。
    """
    overlay = {
        "schema_version": 1,
        "review_status": "reviewed",
        "adjudications": adjudications or {},
    }
    seed = copy.deepcopy(rows)
    if unified_companion and not any(row["facts"]["unified_commit_calls"] for row in seed):
        seed.append(
            _synthetic_row(
                generator,
                writer_id="app.services.demo_unified_companion::Companion.save",
                source=_UNIFIED_CLEAN_SOURCE,
                function_name="save",
                kind="writer",
            )
        )
    inventory = generator.build_inventory(seed, overlay)
    inventory["representation_upgrade_lane"] = (
        lane
        if lane is not None
        else [
            {
                "function_id": "app.x::Upgrader.stage_and_register_candidate",
                "candidate_calls": ["stage_upgrade_candidate"],
                "version_fields_written": [],
                "revision_bump_calls": [],
                "sql_update_columns": [],
                "commit_receivers": [],
            }
        ]
    )
    return inventory


# ═══ §1 characterization 证据必须落在调用点上 ═══════════════════════════════


_MENTION_ONLY_TEST = '''
import ast
from pathlib import Path

from app.services.wp_storage_service import WpStorageService


def test_the_snapshot_helper_mentions_names_without_calling_them():
    """提到 WpStorageService / save_version / list_versions，但一个都没调用。"""
    source = Path("backend/app/services/wp_storage_service.py").read_text()
    tree = ast.parse(source)
    names = {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
    assert "save_version" in names
    assert "list_versions" in names
    assert WpStorageService is not None
'''

_CALL_SITE_TEST = '''
from app.services.wp_storage_service import WpStorageService


async def test_the_snapshot_writer_is_actually_invoked(session):
    result = await WpStorageService(session).save_version(wp_id)
    assert "error" not in result
'''

_UNRELATED_SAME_NAME_TEST = '''
import copy

from app.services.wp_migration_service import WpMigrationService


async def test_rollback_restores_data(session):
    """false credit #2 的形态：模拟回滚 + 在别的接收者上调用同名方法。"""
    before = copy.deepcopy({"a": 1})
    await session.rollback()
    assert WpMigrationService is not None
    assert before == {"a": 1}
'''


def test_a_mention_without_a_call_site_credits_nothing(generator: ModuleType) -> None:
    """**Validates: Requirements 9.11**

    false credit #1 的最小复现：导入模块、提到类名与两个方法名，一个都没调用。旧谓词
    （module 命中 ∧ qualname 任一段命中）会把**两个**方法都记成有测试。
    """
    invoked = _invoked(generator, _MENTION_ONLY_TEST)
    assert _SAVE_VERSION not in invoked
    assert _LIST_VERSIONS not in invoked
    assert not {key for key in invoked if key.startswith(_STORAGE)}, (
        f"提及不是调用，但谓词记了 {sorted(invoked)}"
    )


def test_a_resolved_call_site_credits_exactly_the_called_writer(
    generator: ModuleType,
) -> None:
    """`Cls(session).method(...)` 这条真实形态必须认得，且**只**记被调用的那个方法。"""
    invoked = _invoked(generator, _CALL_SITE_TEST)
    assert _SAVE_VERSION in invoked
    assert _LIST_VERSIONS not in invoked, "同类兄弟方法不得沾光"


def test_a_same_named_call_on_an_unrelated_receiver_credits_nothing(
    generator: ModuleType,
) -> None:
    """**Validates: Requirements 9.11**

    false credit #2 的形态：`session.rollback()` 与 `WpMigrationService.rollback` 同名。
    只按 leaf 名匹配调用点仍会误记 —— 接收者必须能解析到那个类。
    """
    invoked = _invoked(generator, _UNRELATED_SAME_NAME_TEST)
    assert _MIGRATION_ROLLBACK not in invoked, (
        "db.rollback() 被当成了 WpMigrationService.rollback 的调用点"
    )


def test_the_two_recorded_false_credits_are_gone(inventory: dict[str, Any]) -> None:
    """**Validates: Requirements 9.11**

    直接钉住 Task 19 记录的那两条，且**同时**证明守卫不是因为文件消失才绿：
    那条 deepcopy 属性测试必须仍然存在、仍然提到 `rollback`，只是不再算作证据。
    """
    assert _row(inventory, _LIST_VERSIONS)["characterization_tests"] == []

    deepcopy_test = _REPO / _DEEPCOPY_ROLLBACK_TEST
    assert deepcopy_test.is_file(), (
        f"{_DEEPCOPY_ROLLBACK_TEST} 不存在了 —— 本守卫会因为「文件没了」而假绿"
    )
    text = deepcopy_test.read_text(encoding="utf-8-sig")
    assert "rollback" in text.lower(), "那条属性测试不再谈回滚，本守卫钉的对象已不成立"
    assert "copy.deepcopy" in text, "它不再用 deepcopy 模拟回滚，须重新取证"
    assert "WpMigrationService" in text, "它不再引用被记账的那个类，须重新取证"
    credits = _row(inventory, _MIGRATION_ROLLBACK)["characterization_tests"]
    assert _DEEPCOPY_ROLLBACK_TEST not in credits, (
        f"用 deepcopy 模拟回滚的测试又被算作 characterization 证据：{credits}"
    )


def test_real_call_sites_are_still_credited(inventory: dict[str, Any]) -> None:
    """收紧不能把真的调用点也扫掉，否则判据只是变成了另一种噪声。"""
    for writer_id in (_SAVE_VERSION, _MIGRATION_ROLLBACK):
        credits = _row(inventory, writer_id)["characterization_tests"]
        assert "backend/tests/workpaper_sync/test_task19_writer_migration.py" in credits, (
            f"{writer_id} 在 Task 19 守卫里被真实调用，却没被记账：{credits}"
        )


def test_every_credit_in_the_inventory_re_derives_from_its_test_file(
    generator: ModuleType, inventory: dict[str, Any]
) -> None:
    """**Validates: Requirements 9.11**

    正面再推导：清册里每一条 `characterization_tests` 指向的文件，必须真的解析出对该 writer
    的调用点。手工往清册里塞一条证据、或谓词退回名称就近，都会在这里红。
    """
    resolved: dict[str, set[str]] = {}
    checked = 0
    for entry in inventory["entries"]:
        for relative in entry["characterization_tests"]:
            if relative not in resolved:
                path = _REPO / relative
                assert path.is_file(), f"{entry['writer_id']} 指向不存在的测试 {relative}"
                resolved[relative] = generator._resolved_calls_in_test(
                    ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
                )
            assert entry["writer_id"] in resolved[relative], (
                f"{entry['writer_id']} 记账在 {relative}，但该文件没有它的调用点"
            )
            checked += 1
    assert checked > 20, f"再推导的分母太小（{checked}），判据近乎空跑"


def test_a_sibling_in_the_same_module_is_not_credited(generator: ModuleType) -> None:
    """**Validates: Requirements 9.11**

    false credit #1 的判据级形态：`_tests_for` 只能按**完整** `module::qualname` 取证。
    退回「同模块任一 key 命中就算」时，一条只调用 `save_version` 的测试会连
    `list_versions` 一起点亮 —— 这正是 Task 19 实测到的那一条。
    """
    index = {f"{_STORAGE}::WpStorageService.save_version": ["backend/tests/t.py"]}
    assert generator._tests_for(index, _STORAGE, "WpStorageService.save_version") == [
        "backend/tests/t.py"
    ]
    assert generator._tests_for(index, _STORAGE, "WpStorageService.list_versions") == [], (
        "同模块的兄弟方法被顺带记成有 characterization 测试"
    )
    assert generator._tests_for(index, _STORAGE, "WpStorageService.archive_project") == []


def test_patching_a_target_string_is_not_an_invocation(generator: ModuleType) -> None:
    """旧谓词把 `monkeypatch.setattr("app.x.y", ...)` 的字符串当模块引用。打桩不是调用。"""
    invoked = _invoked(
        generator,
        'def test_x(monkeypatch):\n'
        '    monkeypatch.setattr("app.services.wp_storage_service.WpStorageService", 1)\n',
    )
    assert not {key for key in invoked if key.startswith(_STORAGE)}, sorted(invoked)


# ═══ §2 artifact-snapshot：正面类别，不是豁免 ═══════════════════════════════


_SNAPSHOT_ONLY_SOURCE = '''
import shutil


async def save_version(self, wp_id):
    wp = await self._load(wp_id)
    file_path = resolve_wp_file(wp.file_path)
    version_dir = file_path.parent / ".versions" / file_path.stem
    revision = int(wp.content_revision or 0)
    version_path = version_dir / f"v{revision}.xlsx"
    shutil.copy2(str(file_path), str(version_path))
    return {"content_revision": revision}
'''

_SNAPSHOT_PLUS_AUTHORITATIVE_SOURCE = '''
import shutil


async def save_version(self, wp_id):
    wp = await self._load(wp_id)
    file_path = resolve_wp_file(wp.file_path)
    version_dir = file_path.parent / ".versions" / file_path.stem
    revision = int(wp.content_revision or 0)
    version_path = version_dir / f"v{revision}.xlsx"
    shutil.copy2(str(file_path), str(version_path))
    file_path.write_bytes(b"new authoritative bytes")
    return {"content_revision": revision}
'''


def test_the_snapshot_category_is_exactly_the_snapshot_destination_writers(
    regenerated: dict[str, Any],
) -> None:
    """**Validates: Requirements 2.1, 2.2**

    类别的**爆炸半径**必须钉住。清册里有 15 个 writer「零业务内容事实」（excel_html 的
    structure.json 写入、模板落地、自定义底稿生成……），它们写的是**权威** artifact，一个
    宽泛的「无内容事实 ⇒ 不算绕过」会一次性放掉 15 行。类别按**目标路径**派生，因此只命中
    真的往 `.versions/` 复制的那一行。
    """
    snapshot_rows = {
        entry["writer_id"]
        for entry in regenerated["entries"]
        if entry["verdicts"]["artifact_snapshot_only"]
    }
    assert snapshot_rows == {_SAVE_VERSION}, f"类别爆炸半径漂移：{sorted(snapshot_rows)}"

    zero_content_writers = {
        entry["writer_id"]
        for entry in regenerated["entries"]
        if entry["kind"] in {"writer", "writer_resolver"}
        and not entry["verdicts"]["writes_business_content"]
    }
    assert len(zero_content_writers) > 10, (
        "「零业务内容事实」的 writer 不该只有一条 —— 分母塌了，爆炸半径判据就是空跑"
    )
    still_blocked = zero_content_writers - snapshot_rows
    assert len(still_blocked) == len(zero_content_writers) - 1
    for writer_id in still_blocked:
        assert _row(regenerated, writer_id)["verdicts"]["bypasses_unified_commit"], (
            f"{writer_id} 写的是权威 artifact，不得因为「没写 DB 列」就离开门"
        )


def test_writers_that_also_snapshot_do_not_get_the_category(
    regenerated: dict[str, Any],
) -> None:
    """**Validates: Requirements 2.1**

    真实反例：`save_univer_data` 与 `WOPIHostService.put_file` **也**往 `.versions/` 落
    备份，但同时写权威文件。「每一次 artifact 写都必须是快照」这条要求正是靠它们证明不是
    恒真的 —— 三个候选里只有一个拿到类别。
    """
    also_snapshot = {
        entry["writer_id"]
        for entry in regenerated["entries"]
        if any(
            item["target"] == "snapshot" for item in entry["facts"]["artifact_write_targets"]
        )
    }
    assert len(also_snapshot) >= 3, f"往快照目录写的行少于 3 条：{sorted(also_snapshot)}"

    reasons: set[str] = set()
    for writer_id in also_snapshot - {_SAVE_VERSION}:
        entry = _row(regenerated, writer_id)
        targets = {item["target"] for item in entry["facts"]["artifact_write_targets"]}
        withheld: set[str] = set()
        if "unclassified" in targets:
            withheld.add("has_an_unclassified_artifact_write")
        if entry["verdicts"]["writes_business_content"]:
            withheld.add("writes_business_content")
        assert withheld, (
            f"{writer_id} 往快照目录写、又没有任何扣分事实，却没拿到类别 —— 判据自相矛盾"
        )
        assert not entry["verdicts"]["artifact_snapshot_only"], (
            f"{writer_id} 拿到了快照类别，扣分事实={sorted(withheld)}"
        )
        # 它们要么仍在门里（未迁移），要么是**真的**经过了统一入口（`put_file` 已由
        # Task 19 迁走）。唯一不许出现的第三种是「靠快照类别离开门」。
        assert (
            entry["verdicts"]["bypasses_unified_commit"]
            or entry["facts"]["unified_commit_calls"]
        ), f"{writer_id} 既没经统一入口，也没留在门里"
        reasons |= withheld

    # 两个扣分项都必须有实测代表，否则其中一项是恒不生效的死条件：
    #   * `save_univer_data` 的 artifact 写**全部**落在 `.versions/`，只因为它同时推进
    #     `file_version` / 写 `working_paper` 才拿不到类别 ⇒ 证明「零业务内容」这项在干活；
    #   * `put_file` 还有两处非快照目标 ⇒ 证明「每一次写都必须是快照」这项在干活。
    assert reasons == {"has_an_unclassified_artifact_write", "writes_business_content"}, (
        f"两个扣分项没有各自的实测代表：{sorted(reasons)}"
    )


def test_one_authoritative_write_removes_the_category(generator: ModuleType) -> None:
    """判据级：加一行权威写（`file_path.write_bytes`）即失去类别、bypass 立刻回来。"""
    clean = _synthetic_row(
        generator,
        writer_id="app.services.demo_storage::DemoStorage.save_version",
        source=_SNAPSHOT_ONLY_SOURCE,
        function_name="save_version",
    )
    dirty = _synthetic_row(
        generator,
        writer_id="app.services.demo_storage::DemoStorage.save_version",
        source=_SNAPSHOT_PLUS_AUTHORITATIVE_SOURCE,
        function_name="save_version",
    )
    clean_verdicts = generator.build_inventory(
        [clean], {"schema_version": 1, "review_status": "reviewed", "adjudications": {}}
    )["entries"][0]["verdicts"]
    dirty_verdicts = generator.build_inventory(
        [dirty], {"schema_version": 1, "review_status": "reviewed", "adjudications": {}}
    )["entries"][0]["verdicts"]

    assert clean_verdicts["artifact_snapshot_only"] is True
    assert clean_verdicts["bypasses_unified_commit"] is False
    assert dirty_verdicts["artifact_snapshot_only"] is False
    assert dirty_verdicts["bypasses_unified_commit"] is True


def test_the_snapshot_writer_carries_its_own_positive_obligations(
    generator: ModuleType, gate: ModuleType
) -> None:
    """**Validates: Requirements 2.1, 2.2**

    类别不是「不用管了」：拿到类别的行必须被裁决、必须读**统一**计数器（快照名跟随真正在
    动的那个），且不得碰 legacy 字段。三条都能单独打红。
    """
    writer_id = "app.services.demo_storage::DemoStorage.save_version"
    row = _synthetic_row(
        generator,
        writer_id=writer_id,
        source=_SNAPSHOT_ONLY_SOURCE,
        function_name="save_version",
    )
    adjudicated = {
        writer_id: {"domain": "history_restore", "version_domain_note": "synthetic"}
    }

    ok = _synthetic_inventory(generator, [row], adjudications=adjudicated)
    assert gate.evaluate_gate(ok)["artifact_snapshot_writer_not_verifiable"] == []

    # (a) 未裁决
    unadjudicated = _synthetic_inventory(generator, [row])
    assert gate.evaluate_gate(unadjudicated)["artifact_snapshot_writer_not_verifiable"] == [
        writer_id
    ]

    # (b) 快照名不再跟随统一计数器（读回 file_version）
    legacy_source = _SNAPSHOT_ONLY_SOURCE.replace("wp.content_revision", "wp.file_version")
    legacy_row = _synthetic_row(
        generator,
        writer_id=writer_id,
        source=legacy_source,
        function_name="save_version",
    )
    assert legacy_row["facts"]["version_fields_read"] == ["file_version"]
    legacy = _synthetic_inventory(generator, [legacy_row], adjudications=adjudicated)
    assert gate.evaluate_gate(legacy)["artifact_snapshot_writer_not_verifiable"] == [writer_id]

    # (b2) 只读 legacy 字段会同时触发两条判据（「没读统一计数器」与「读了 legacy 字段」），
    # 于是任一条被拿掉都仍然打红 —— 那是 Task 19 记录过的「两条拒绝共用一个出口 ⇒ 第一条
    # 变成不可达分支」形态，变异检验（M08）实测为 GREEN。所以这里补一个**只**缺统一计数器
    # 的反例：快照名里干脆不含任何版本号，一个 version 字段都不读。
    timeless_source = _SNAPSHOT_ONLY_SOURCE.replace(
        "    revision = int(wp.content_revision or 0)\n", ""
    ).replace('f"v{revision}.xlsx"', '"snapshot.xlsx"').replace(
        '    return {"content_revision": revision}', "    return {}"
    )
    timeless_row = _synthetic_row(
        generator,
        writer_id=writer_id,
        source=timeless_source,
        function_name="save_version",
    )
    assert timeless_row["facts"]["version_fields_read"] == [], (
        "反例构造失败：它仍然读了某个版本字段，两条判据又会同时命中"
    )
    assert timeless_row["facts"]["artifact_write_targets"], "它必须仍是一个快照写"
    timeless = _synthetic_inventory(generator, [timeless_row], adjudications=adjudicated)
    assert gate.evaluate_gate(timeless)["artifact_snapshot_writer_not_verifiable"] == [
        writer_id
    ], "快照名不跟随任何计数器时，「必须读统一计数器」这条义务没有单独打红"


def test_a_snapshot_writer_that_invents_a_version_blocks_again(
    generator: ModuleType, gate: ModuleType
) -> None:
    """**Validates: Requirements 2.2** · Property 61

    注入 Task 19 删掉的那行私有计数器：类别消失、bypass 回来、legacy 准则同时点名。
    """
    writer_id = "app.services.demo_storage::DemoStorage.save_version"
    regressed_source = _SNAPSHOT_ONLY_SOURCE.replace(
        "    shutil.copy2(str(file_path), str(version_path))",
        "    shutil.copy2(str(file_path), str(version_path))\n"
        "    wp.file_version = int(wp.file_version or 0) + 1",
    )
    row = _synthetic_row(
        generator,
        writer_id=writer_id,
        source=regressed_source,
        function_name="save_version",
    )
    inventory = _synthetic_inventory(
        generator,
        [row],
        adjudications={
            writer_id: {"domain": "history_restore", "version_domain_note": "synthetic"}
        },
    )
    verdicts = inventory["entries"][0]["verdicts"]
    assert verdicts["artifact_snapshot_only"] is False
    assert verdicts["bypasses_unified_commit"] is True

    issues = gate.evaluate_gate(inventory)
    assert issues["writes_legacy_version_field"] == [writer_id]
    assert issues["bypasses_unified_commit"] == [writer_id]


# ═══ §3 projection-only / 双 revision ══════════════════════════════════════


_UNIFIED_CLEAN_SOURCE = '''
async def save(self, wp_id, payload):
    writer = build_content_mutation_service_writer(self.db)
    receipt = await writer.commit_bytes(wp_id=wp_id, payload=payload)
    return receipt
'''


def _unified_row(generator: ModuleType, source: str) -> dict[str, Any]:
    return _synthetic_row(
        generator,
        writer_id="app.services.demo_writer::DemoWriter.save",
        source=source,
        function_name="save",
        kind="writer",
    )


@pytest.mark.parametrize(
    "injection",
    [
        pytest.param("    wp.file_version = int(wp.file_version or 0) + 1", id="file_version"),
        pytest.param("    wp.parsed_data['_version'] = 2", id="parsed_data._version"),
        pytest.param(
            "    wp.content_revision = int(wp.content_revision or 0) + 1",
            id="own_content_revision",
        ),
        pytest.param("    await self.db.commit()", id="direct_commit"),
    ],
)
def test_a_private_write_path_beside_the_unified_commit_is_reported(
    generator: ModuleType, gate: ModuleType, injection: str
) -> None:
    """**Validates: Requirements 2.1, 2.2** · Property 4、Property 61

    「经过统一入口」只是一半。旁边再留一条私有路径（自己的 legacy 计数器、自己 bump
    `content_revision`、或者自己的事务边界）就是 Task 15 禁止的双 revision 形态。四种注入
    各自打红，缺任一都说明准则漏了一条路径。
    """
    clean = _unified_row(generator, _UNIFIED_CLEAN_SOURCE)
    clean_inventory = _synthetic_inventory(generator, [clean])
    assert clean_inventory["entries"][0]["facts"]["unified_commit_calls"], (
        "合成行没有被认成统一入口调用方，本判据会空跑"
    )
    assert (
        gate.evaluate_gate(clean_inventory)[
            "keeps_legacy_write_path_beside_unified_commit"
        ]
        == []
    )

    injected = _unified_row(generator, _UNIFIED_CLEAN_SOURCE + injection + "\n")
    issues = gate.evaluate_gate(_synthetic_inventory(generator, [injected]))
    assert issues["keeps_legacy_write_path_beside_unified_commit"] == [
        "app.services.demo_writer::DemoWriter.save"
    ], f"注入 {injection.strip()} 后准则没打红"


def test_the_double_revision_criterion_has_a_real_denominator(
    gate: ModuleType, inventory: dict[str, Any]
) -> None:
    """**Validates: Requirements 2.2**

    零个统一入口调用方时，这条准则恒为零 —— 一个恒真的准则比没有更糟。门在这种情况下必须
    抛错而不是报绿。
    """
    reaching = [
        entry["writer_id"]
        for entry in inventory["entries"]
        if entry["facts"]["unified_commit_calls"]
    ]
    assert len(reaching) >= 7, f"统一入口调用方只有 {reaching}"

    emptied = copy.deepcopy(inventory)
    for entry in emptied["entries"]:
        entry["facts"]["unified_commit_calls"] = []
    with pytest.raises(gate.WriterGateError, match="empty denominator"):
        gate.evaluate_gate(emptied)


# ═══ §4 representation upgrade lane ════════════════════════════════════════


def test_the_upgrade_lane_is_source_backed_and_moves_no_business_revision(
    inventory: dict[str, Any],
) -> None:
    """**Validates: Requirements 2.1** · Property 4

    纯表示升级不得推进业务 revision。升级器**不在** `entries` 里（它不写内容属性、不写被
    跟踪的 SQL 列、不解析底稿路径），所以这条准则必须有自己的源码分母。
    """
    lane = inventory["representation_upgrade_lane"]
    assert lane, "upgrade lane 空 ⇒ Property 4 的准则在空分母上评估"
    functions = {item["function_id"] for item in lane}
    assert (
        "app.services.workpaper_sync.excel_instrumentation::"
        "ExcelInstrumentationUpgrader.stage_and_register_candidate" in functions
    ), f"lane 里没有 Task 17 的升级器：{sorted(functions)}"
    for item in lane:
        assert item["version_fields_written"] == [], item
        assert item["revision_bump_calls"] == [], item
        assert item["sql_update_columns"] == [], item


def test_a_revision_bump_inside_the_upgrade_lane_is_reported(
    generator: ModuleType, gate: ModuleType
) -> None:
    """在 lane 里注入一次 `bump_content_revision` / 一列 SQL 写 ⇒ 准则打红。"""
    row = _unified_row(generator, _UNIFIED_CLEAN_SOURCE)
    base_lane = [
        {
            "function_id": "app.x::Upgrader.stage_and_register_candidate",
            "candidate_calls": ["stage_upgrade_candidate"],
            "version_fields_written": [],
            "revision_bump_calls": [],
            "sql_update_columns": [],
            "commit_receivers": [],
        }
    ]
    ok = _synthetic_inventory(generator, [row], lane=base_lane)
    assert (
        gate.evaluate_gate(ok)["representation_upgrade_increments_business_revision"] == []
    )

    for field, value in (
        ("revision_bump_calls", ["self._repo.bump_content_revision"]),
        ("version_fields_written", ["content_revision"]),
        ("sql_update_columns", ["working_paper.parsed_data"]),
    ):
        bad_lane = copy.deepcopy(base_lane)
        bad_lane[0][field] = value
        issues = gate.evaluate_gate(_synthetic_inventory(generator, [row], lane=bad_lane))
        assert issues["representation_upgrade_increments_business_revision"] == [
            "app.x::Upgrader.stage_and_register_candidate"
        ], f"lane 里的 {field} 没被判红"


def test_an_empty_upgrade_lane_is_refused_not_reported_green(
    generator: ModuleType, gate: ModuleType
) -> None:
    row = _unified_row(generator, _UNIFIED_CLEAN_SOURCE)
    empty = _synthetic_inventory(generator, [row], lane=[])
    with pytest.raises(gate.WriterGateError, match="upgrade lane is empty"):
        gate.evaluate_gate(empty)


def test_the_lane_is_part_of_the_freshness_contract(
    gate: ModuleType, generator: ModuleType, inventory: dict[str, Any]
) -> None:
    """lane 参与 `source_digest`：把 lane 改一个字，门必须拒绝评估而不是照旧评估。"""
    doctored = copy.deepcopy(inventory)
    doctored["representation_upgrade_lane"][0]["revision_bump_calls"] = ["injected"]
    doctored["inventory_digest"] = generator.recompute_inventory_digest(doctored)
    with pytest.raises(gate.WriterGateError, match="representation upgrade lane"):
        gate.assert_inventory_is_current(doctored)


# ═══ §5 文档与门在 14 条准则上双向对齐，且红基线由门现算派生 ═════════════════


def test_the_gate_evaluates_exactly_the_criteria_the_spec_names(
    gate: ModuleType, inventory: dict[str, Any]
) -> None:
    """**Validates: Requirements 2.1, 2.2, 2.12, 9.11**

    三段**双向**断言，缺任一方向都留下一个静默分叉入口：

    * doc ↔ 本文件的表：Task 20 基线行点名的标签集必须逐字等于 `_GATE_CRITERIA` 的键集；
    * 本文件的表 ↔ 门：`_GATE_CRITERIA` 的 value 集必须逐字等于 `evaluate_gate()` 的 key 集。
      旧版只断言「表里的 key 都在门里」（单向）—— 门里多一条、文档里没人认领时不会红，而
      `has_debt` 却由它构成，于是那一条「在通过条件里、不在验收条件里」；
    * doc 的归属行 ↔ 门：14 条必须逐条有归属任务，且归属行不许点名门里不存在的 key。

    「没评过」与「评过且为零」在报告里长得一样，所以这三段说的都是**形状**，与计数无关：债
    真的还完之后本条仍然全绿。
    """
    issues = gate.evaluate_gate(inventory)
    labels = _task20_criteria_labels_from_tasks_md()
    assert labels == set(_GATE_CRITERIA), (
        f"Task 20 基线行点名的准则与本文件的表不一致；"
        f"doc 独有 {sorted(labels - set(_GATE_CRITERIA))}，"
        f"表独有 {sorted(set(_GATE_CRITERIA) - labels)}"
    )
    assert set(_GATE_CRITERIA.values()) == set(issues), (
        f"门的 issue key 集与文档点名的准则不是同一件事；"
        f"门独有 {sorted(set(issues) - set(_GATE_CRITERIA.values()))}（在 `has_debt` 里却没人"
        f"在文档里认领），文档独有 "
        f"{sorted(set(_GATE_CRITERIA.values()) - set(issues))}（门里没有实现）"
    )

    homing = _gate_criteria_homing_from_tasks_md()
    assert set(homing) == set(issues), (
        f"归属行与门的 key 集不一致；门里无归属 {sorted(set(issues) - set(homing))}，"
        f"归属行点名了门里不存在的 key {sorted(set(homing) - set(issues))}"
    )


def test_the_frozen_red_baseline_is_derived_from_the_live_gate(
    gate: ModuleType, inventory: dict[str, Any], regenerated: dict[str, Any]
) -> None:
    """**Validates: Requirements 2.1, 2.2, 2.12, 9.11** · Property 61

    Task 20 的完成语义是「门可信 + **当期红基线冻结**」。冻结的那 14 个数字如果是手抄常量，
    源码一变就与文档静默分叉（平台假绿第③源），于是「基线」退化成一句陈述。所以这里现场解析
    正文那一行，与门的实测计数**逐条**比对，两个方向都能打红：

    * 文档里的数字写错（含「归零了但没改文档」）⇒ 红；
    * 源码/谓词变动使某条计数移动而正文没跟着改 ⇒ 红。

    比对同时对**磁盘清册**与**现场从 AST 重推的清册**各做一遍：只比磁盘会漏掉「改了生成器但
    没重生成清册」，只比重推会漏掉「手改了磁盘清册」。两份相等本身由
    `test_workpaper_writer_inventory.py::test_inventory_on_disk_matches_the_ast` 守。
    """
    baseline, declared_total = _frozen_red_baseline_from_tasks_md()
    assert set(baseline) == set(_GATE_CRITERIA), "基线行与 `_GATE_CRITERIA` 的标签集不一致"
    assert sum(baseline.values()) == declared_total, (
        f"基线行逐条之和 {sum(baseline.values())} ≠ 它自己声明的合计 {declared_total}"
    )

    for label, source in (("磁盘清册", inventory), ("现场重推的清册", regenerated)):
        issues = gate.evaluate_gate(source)
        measured = {key: len(values) for key, values in issues.items()}
        frozen = {_GATE_CRITERIA[name]: count for name, count in baseline.items()}
        drift = {
            key: (frozen[key], measured[key])
            for key in sorted(frozen)
            if frozen[key] != measured[key]
        }
        assert not drift, (
            f"{label}：Task 20 冻结的红基线与门实测不一致 "
            f"{{key: (文档, 实测)}} = {drift} —— 要么文档里的数字写错了，要么源码动了而正文"
            "没同步更新。两种都必须改到一致，不许只改一边"
        )
        assert sum(measured.values()) == declared_total, (
            f"{label}：blocking facts 合计实测 {sum(measured.values())}，"
            f"正文冻结 {declared_total}"
        )

    # 反重言式：基线不能是「全零」——那样它既不描述现状，也无法证明这条判据在干活。
    assert any(count for count in baseline.values()), (
        "冻结基线全为零 ⇒ 门已绿，那么 Task 20 的正文语义（「红基线冻结」）要整体重写，"
        "本判据也要随之改成「门必须保持绿」"
    )


def test_the_gate_is_red_and_names_its_blocking_rows(
    gate: ModuleType, inventory: dict[str, Any], overlay: dict[str, Any]
) -> None:
    """**Validates: Requirements 2.2, 9.11** · Property 61

    Task 20 收口时门**仍是红的**，这是实测结论而不是构造。红要红得**有名字**：被点名的行必须能
    在 overlay 里查到 lane 与理由。

    🔴 **Task 74 改写了这条判据的一半**。原文是「或者本来就是未裁决行（未裁决本身就是『还没人
    决定』这条信息）」，并断言 `unadjudicated_writer` 非空。Task 74 把 236 行未裁决清到 0 之后，
    那个逃生口不再存在 —— 判据因此**变强**：门点名的每一行都必须在 overlay 里有非空
    `version_domain_note`，没有「未裁决」可以兜底。同时保留原来的核心结论（门仍红、退出码 1、
    Task 19 交接的那一行仍在阻塞名单里且理由文本未被稀释）。
    """
    issues = gate.evaluate_gate(inventory)
    assert not issues["unadjudicated_writer"], (
        "Task 74 已把 `unadjudicated_writer` 清零；这里非空说明新增了 writer 却没写裁决："
        f"{issues['unadjudicated_writer'][:5]}"
    )
    assert not issues["unadjudicated_resolver"], (
        f"同上，resolver 侧：{issues['unadjudicated_resolver'][:5]}"
    )
    assert issues["bypasses_unified_commit"], (
        "绕过统一 commit 归零了？那 Task 74 的第二半（逐 writer 迁 `ContentMutationService`）"
        "已经做完，本判据要随之改写成「门必须保持绿」"
    )
    named = {
        writer_id
        for name, values in issues.items()
        if name != "missing_required_domain"
        for writer_id in values
    }
    unexplained = sorted(
        writer_id
        for writer_id in named
        if not (overlay["adjudications"].get(writer_id) or {}).get("version_domain_note")
    )
    assert not unexplained, (
        f"门点名 {len(unexplained)} 行却在 overlay 里查不到 lane 与理由：{unexplained[:5]}"
    )
    assert gate.main(["--skip-source-check"]) == 1

    blocked = "app.routers.excel_html::rollback_file_version"
    assert blocked in issues["bypasses_unified_commit"], (
        "Task 19 交接的那一行不再阻塞了 —— 若真迁移完成，这条守卫要随之改写"
    )
    note = overlay["adjudications"][blocked]["version_domain_note"]
    for token in ("wp_id", "10.6", "12.7"):
        assert token in note, f"阻塞理由里缺少 {token}：{note[:120]}"


def test_the_gate_can_still_reach_green(
    gate: ModuleType, inventory: dict[str, Any]
) -> None:
    """新增的三条准则不能把门变成永远打不开的门。"""
    cleared = copy.deepcopy(inventory)
    required = list(gate._REQUIRED_DOMAINS)
    for index, entry in enumerate(cleared["entries"]):
        entry["verdicts"] = {name: False for name in entry["verdicts"]}
        entry["verdicts"]["has_characterization_test"] = True
        entry["adjudication"] = {
            "status": "adjudicated",
            "domain": entry["adjudication"].get("domain") or required[index % len(required)],
            "version_domain_note": "simulated Task 20 end state",
        }
    issues = gate.evaluate_gate(cleared)
    assert not any(issues.values()), {k: v[:3] for k, v in issues.items() if v}


# ═══ §6 已移交出去的那一条：换了门，不是没了门 ═══════════════════════════════
#
# `多 resolver writer=0` 原本是 Task 20 的第六条，此后移交两次：
#
# * **第一跳 20 → 30**：那 4 行的 substrate 要先变成 Task 25/26 的 room/staged
#   representation，而 Task 25 又依赖 Task 20 —— 留在 Task 20 即成环。
# * **第二跳 30 → 71**：Task 30 在活体库上实测到供给为 0 行，而供给只能来自 Task 36 的逐
#   entry `finalizeCandidate`，**Task 36 又依赖 Task 30** —— 同形的第二次成环。它真正能归零
#   的时点是「每个 entry 都有 published representation」，恰是 legacy 回退可删的时点，故归属
#   落到 `legacy_delete` gate 成员 Task 71（Task 71 本就依赖 Task 30，方向不成环）。
#
# **门里的计算一行都不能删** —— 当前归属方正是靠 `check_workpaper_writer_revision_gate.py`
# 的 `multi_resolver` 计数验零。
#
# 于是这里守三件事：门是否**真的还在评**这条准则（键在但恒空是同一个 fail-open）、当前归属
# 方点名的行是否就是门报出的行，以及「归属」与**整条移交链**是否与 tasks.md 一致（第一跳
# 漂移的形态就是文档改了、判据表没改，而断言是单向的「Task 20 点名的都要有 key」，多一条
# 不会红）。移交方向本身是否造出新环，由
# `test_task30_closure_gate.py::test_relocating_the_criterion_did_not_invert_the_wave_order`
# 按依赖图断言。


#: 两个 resolver 符号 ⇒ `_resolver_identities` 长度 > 1 ⇒ `multi_resolver` 为真。
#: 形态照抄 `wp_onlyoffice_router` 里那 4 行（拿到底稿物理路径的方式不止一条）。
_TWO_RESOLVER_SOURCE = '''
async def get_sheet_onlyoffice_config(self, wp_id):
    path = resolve_wp_file(self.wp.file_path)
    template = find_template_file(self.wp.template_name)
    return {"path": str(path), "template": str(template)}
'''

_ONE_RESOLVER_SOURCE = '''
async def get_sheet_onlyoffice_config(self, wp_id):
    path = resolve_wp_file(self.wp.file_path)
    return {"path": str(path)}
'''

_MULTI_RESOLVER_ROW_ID = "app.routers.demo_oo_router::get_sheet_onlyoffice_config"


def _criterion_owner_task() -> str:
    """当前持有 `multi_resolver` 的任务号 —— 从 tasks.md 的显式接手语现场解析。

    🔴 不硬写任务号：归属已移交两次，硬写的常量会在第三次移交时与文档静默分叉。
    """
    homed, _, assumed = _gate_issue_key_homing()
    owners = assumed.get("multi_resolver") or []
    assert len(owners) == 1, (
        f"tasks.md 里接手 `multi_resolver` 的任务不是恰一个：{owners}"
        "（0 = 无人守，>1 = 两个门都自称归属）"
    )
    assert homed.get("multi_resolver") == owners[0], (
        f"放手侧指向 Task {homed.get('multi_resolver')}，接手侧却是 Task {owners[0]}"
    )
    return owners[0]


def _task71_multi_resolver_rows_from_tasks_md() -> tuple[int, set[str]]:
    """当前归属方正文点名的「N 条 resolver 行」→ ``(N, {函数名})``。

    锚在 `resolver 行（…）` 这个短语上而不是抄一份名单：名单一旦在文档里改了（迁走一行、
    换个函数名），这里解析出来的集合就跟着变，和门实测报出的行比对即可发现不一致。

    归属任务号同样是派生的 —— 第二跳（30 → 71）之前这里读的是 Task 30 的正文，硬写号会让
    「文档已经改了归属、判据还在读旧任务」这种漂移变成静默通过。
    """
    owner = _criterion_owner_task()
    for line in _task_bodies()[owner]:
        if "gate issue key `multi_resolver`" not in line:
            continue
        count = re.search(r"(\d+) 条 resolver 行", line)
        listed = re.search(r"resolver 行（([^）]+)）", line)
        assert count and listed, (
            f"Task {owner} 的 multi_resolver 那条正文形态变了：{line[:160]}"
        )
        return int(count.group(1)), set(re.findall(r"`([a-z_]+)`", listed.group(1)))
    raise AssertionError(
        f"Task {owner}（当前归属）正文里找不到 gate issue key `multi_resolver` 那条准则"
    )


def test_the_gate_still_evaluates_the_relocated_criterion(
    generator: ModuleType, gate: ModuleType, inventory: dict[str, Any]
) -> None:
    """**Validates: Requirements 2.12, 9.11**

    「移交」不得等于「无人守」。两层判据，因为只要一层都能被绕：

    * 键必须还在门的 issue map 里 —— 键被删掉时报告里这条准则**消失**，与「为零」无法区分；
    * 键在还不够。把 `if verdicts.get("multi_resolver")` 短路成 `if False` 时键仍在、计数
      恒为零，报告长得和「已清零」一模一样。所以要真喂一条多 resolver 行进去看它被点名，
      并用单 resolver 行证明这条准则不是恒真。
    """
    issues = gate.evaluate_gate(inventory)
    owner = _criterion_owner_task()
    for label, key in _RELOCATED_CRITERIA.items():
        assert key in issues, (
            f"门不再评估已移交 Task {owner} 的准则「{label}」（key `{key}`）"
        )

    multi = _synthetic_row(
        generator,
        writer_id=_MULTI_RESOLVER_ROW_ID,
        source=_TWO_RESOLVER_SOURCE,
        function_name="get_sheet_onlyoffice_config",
    )
    assert len(multi["facts"]["resolver_calls"]) == 2, (
        f"合成行没解析出两个 resolver，判据会空跑：{multi['facts']['resolver_calls']}"
    )
    reported = gate.evaluate_gate(_synthetic_inventory(generator, [multi]))["multi_resolver"]
    assert reported == [_MULTI_RESOLVER_ROW_ID], (
        f"注入一条真的多 resolver 行后 `multi_resolver` 没点名它：{reported}"
    )

    single = _synthetic_row(
        generator,
        writer_id=_MULTI_RESOLVER_ROW_ID,
        source=_ONE_RESOLVER_SOURCE,
        function_name="get_sheet_onlyoffice_config",
    )
    assert single["facts"]["resolver_calls"] == ["resolve_wp_file"]
    assert gate.evaluate_gate(_synthetic_inventory(generator, [single]))["multi_resolver"] == [], (
        f"单 resolver 行也被点名 ⇒ 这条准则恒真，Task {owner} 永远验不了零"
    )


def test_the_gate_names_exactly_the_rows_the_owner_must_clear(
    gate: ModuleType, inventory: dict[str, Any]
) -> None:
    """**Validates: Requirements 2.12, 9.11**

    doc ↔ 门实测双向对齐：当前归属方正文点名的那几条 resolver 行，必须就是门今天报出的行。
    一侧先动（文档里划掉一行、或某行真的迁走了）都会红，于是「移交后还剩几行要清」这件事
    不会只活在散文里。
    """
    count, names = _task71_multi_resolver_rows_from_tasks_md()
    assert names and len(names) == count, (
        f"Task {_criterion_owner_task()} 自称 {count} 条，却列了 {sorted(names)}"
    )

    reported = gate.evaluate_gate(inventory)["multi_resolver"]
    assert {writer_id.split("::")[-1] for writer_id in reported} == names, (
        f"门报出的多 resolver 行与 Task 30 点名的不一致：门={sorted(reported)} doc={sorted(names)}"
    )
    assert {writer_id.split("::")[0] for writer_id in reported} == {
        "app.routers.wp_onlyoffice_router"
    }, f"多 resolver 行不再全在 wp_onlyoffice_router：{sorted(reported)}"


def test_the_criteria_homing_agrees_with_tasks_md() -> None:
    """**Validates: Requirements 2.12, 9.11**

    本次漂移的直接判据。`_GATE_CRITERIA` 是手抄的（散文标签 → 门内 key 没法派生），所以
    「抄了几条、归给谁」必须能被 tasks.md 反驳：

    * Task 20 冻结基线那一行点名的标签集，必须逐字等于 `_GATE_CRITERIA` 的键集；
    * 已移交的准则必须**留在**基线与 `_GATE_CRITERIA` 里（移交不是离场），移交只体现在归属
      指向别的任务；
    * 归属有两套独立派生 —— 显式交接语（`已移交 Task N` / `自 Task M 移交至本门`）与全量
      归属行（`_gate_criteria_homing_from_tasks_md()`）—— 两者在同一个 key 上不一致即红。
    """
    labels = _task20_criteria_labels_from_tasks_md()
    assert labels == set(_GATE_CRITERIA), (
        f"Task 20 正文点名的准则与本文件的表不一致；"
        f"doc 独有 {sorted(labels - set(_GATE_CRITERIA))}，"
        f"表独有 {sorted(set(_GATE_CRITERIA) - labels)}"
    )
    # 🔴 新语义（见 `_RELOCATED_CRITERIA` 的声明注释）：**移交不是离场**。旧版这里断言「已移交
    # 的标签不得出现在 Task 20 的准则行里」= 用「从基线里消失」冒充「换了归属」，与 fail-open
    # 同形（一条准则从所有分母里消失，和它归零逐字相同）。故两个方向都反过来断言它**还在**。
    for label, key in _RELOCATED_CRITERIA.items():
        assert label in labels, (
            f"「{label}」被摘出了 Task 20 的冻结基线 —— 移交只改归属、不改基线，"
            "当前归属方正是靠这个计数验零"
        )
        assert key in set(_GATE_CRITERIA.values()), (
            f"`{key}` 不在 `_GATE_CRITERIA` 里 ⇒ 门的 14 条 `any()` 少一条，"
            "「没评过」与「评过且为零」在报告里长得一样"
        )

    homed, relinquished, assumed = _gate_issue_key_homing()
    assert relinquished and assumed, (
        "tasks.md 里一句显式交接语都没解析到 —— 本判据在空集上评估（假绿第②源）"
    )
    for label, key in _RELOCATED_CRITERIA.items():
        chain = list(relinquished.get(key) or [])
        taken = list(assumed.get(key) or [])
        # 移交链 = 放手事件序列 + 末端接手方。两跳（20 → 30 → 71）都必须在文档里留痕：
        # 只断言「当前归属是 71」会让第一跳从判据里消失，下一轮复盘又要重新推导一遍
        # 「为什么它不在 Task 20」。
        assert chain == ["20", "30"], (
            f"「{label}」的移交链不是 Task 20 → Task 30 → …：relinquished={relinquished}"
        )
        assert taken == ["71"], (
            f"「{label}」的接手方不是恰一个 Task 71：assumed={assumed}"
        )
        assert homed.get(key) == taken[0], (
            f"「{label}」放手侧指向 Task {homed.get(key)}，接手侧却是 Task {taken[0]}"
        )
        # 🔴 旧版这里断言「已移交的 key 不得留在 Task 20 的准则表里」。新语义下它**必须**留在
        # 表里（上面那段已正向断言），所以这条判据不能机械换个符号 —— 换了就与
        # `_GATE_CRITERIA` 自相矛盾、恒红。移交在新语义里只有一个可观测形态：**归属指向别人**，
        # 而 tasks.md 对「归属」有**两套独立派生**：全量归属行（当前状态）与显式交接语（交接
        # 事件）。`_gate_criteria_homing_from_tasks_md()` 的 docstring 承诺「两者在同一个 key 上
        # 不一致即红（见本判据）」，此前无人兑现 —— 两个来源各自解析成功、各自自洽、谁都不红，
        # 正是第一跳漂移的形态。这一条把承诺补上，同时也就表达了「归属不是 Task 20」：上面
        # 已把 `homed[key]` 钉到接手侧的 Task 71，两套一致即等价于归属指向别人。
        #
        # 不另写一条 `stated != "20"`：那句永远不可能**单独**打红（两套派生要同时说 20，就先
        # 撞上上面的 chain/taken 断言），一条永远不会成为唯一失败原因的断言就是不可反证的
        # 死声明 —— 正是本文件在守的东西。
        stated = _gate_criteria_homing_from_tasks_md().get(key)
        assert stated == homed.get(key), (
            f"「{label}」的归属在 tasks.md 里有两个答案：全量归属行说 Task {stated}，"
            f"显式交接语推出 Task {homed.get(key)} —— 「谁负责清零」不可有两个来源"
        )

    owners = {"20": _GATE_CRITERIA, homed["multi_resolver"]: _RELOCATED_CRITERIA}
    for key, owner in homed.items():
        table = owners.get(owner)
        if table is None:  # 归属别的任务的 key 不在本文件的分母里
            continue
        assert key in set(table.values()), (
            f"tasks.md 把 `{key}` 归给 Task {owner}，本文件的对应表里却没有它 —— "
            "一条准则从所有分母里消失，和它归零长得一样"
        )


# ═══ §7 门的**分母**（scope）本身也是一条判据 ═══════════════════════════════
#
# Task 20 两条结构性欠账（未裁决 writer、绕过统一 commit）落在**整个** `backend/app` 的生产
# writer 上，而 Task 3 的人工裁决只覆盖了 50 行。于是存在一条极便宜的「关门」路径：把分母改
# 小 —— 只算 Task 3 正文点名的那几个 lane，其余宣布「不在范围内」，两条计数当场归零。那不是
# 迁移，是**削弱谓词**，且削弱之后门看起来和真的迁完一模一样。
#
# 所以 scope 必须自己变成可打红的判据。三层：
#
# 1. **分母是什么**（行为级）：发现面 = `backend/app` 下**全部**生产模块。本文件独立重算一遍
#    这个模块集，与生成器实际走过的模块集**逐个**比对 —— 收窄 `_APP_ROOT`、或给
#    `_is_production_source` 加一条排除，都会红。用 `function_facts`（每个函数的事实）反推走
#    查面，不用 `rows`：`rows` 只剩 writer/resolver，一条业务模块「没有 writer」与「没被走
#    查」在它里面长得一样。
# 2. **谁定的**（provenance）：universal scope 不是本文件的主张，是 spec 自己的文字。把那四句
#    原话钉在这里 ⇒ 将来要收窄必须**先改 spec**，改动因此浮到人面前，而不是悄悄改个常量。
# 3. **Task 3 的 lane 枚举是地板不是天花板**：反证来自 Task 3 **自己的** reviewed overlay ——
#    它把 6 行裁决进了 `template_provisioning`，而这个 domain 既不在 Task 3 正文的 lane 枚举
#    里、也不在门的 `_REQUIRED_DOMAINS` 里。若枚举就是 scope，Task 3 自己那 6 条裁决越界了。
#
# 三层都**不**断言「欠账仍然存在」：它们说的是发现面、spec 文字与 domain 表的形状。欠账真的
# 还完之后（每行都裁决、每行都经统一入口）本节仍然全绿。

#: spec 把分母定成「全部生产 writer/resolver」的原话，逐句唯一。改 scope 必须先改这几句。
#:
#: 反向读法（「Task 3 正文那几个 lane 才是 scope」）在 spec 里找不到落脚点：
#: * AC 2.2 的主语是「任何绕过入口的 writer」，不是那几个 lane；
#: * Task 3 第三条「任何未裁决 writer 使统一 revision gate 保持红」在窄读法下是**恒真空句**
#:   —— 一份按裁决定义的清册里不可能存在未裁决行；
#: * design Rollout 第 3 条把 bulk 的前置条件写成「全部生产 writer/resolver」已归零。
_UNIVERSAL_SCOPE_PROVENANCE: dict[str, tuple[Path, str]] = {
    "requirements.md · Requirement 2 User Story": (
        _REQUIREMENTS_MD,
        "所有内容 writer 使用同一 revision 协议",
    ),
    "requirements.md · AC 2.2": (
        _REQUIREMENTS_MD,
        "任何绕过入口的 writer SHALL 被清册与 CI 阻断",
    ),
    "design.md · Property 61 标题": (
        _DESIGN_MD,
        "### Property 61: 所有 writer 进入唯一 revision 域",
    ),
    "design.md · Rollout 第 3 条": (
        _DESIGN_MD,
        "先将全部生产 writer/resolver 迁入唯一 content revision 域",
    ),
}

#: 生成器排除在发现面外的非交付目录段。四段各自都要能单独把一个路径挡住；同时**不得**把普通
#: 业务目录挡住 —— 两个方向都要断言，否则「加一条排除」与「删一条排除」只有一半能被抓到。
_NON_SHIPPING_PATH_SEGMENTS = ("tests", "test", "__pycache__", "migrations")
#: 业务目录取样：它们必须留在发现面里。挑的是真实存在且承载 writer 的包。
_SHIPPING_PACKAGE_SAMPLE = ("routers", "services", "utils", "workpaper_sync")

_BOTH_CONTENT_STORES_SOURCE = '''
import sqlalchemy as sa


async def save(db, wp_id, remark):
    await db.execute(
        sa.text("UPDATE working_paper SET parsed_data = :p WHERE id = :i"), {}
    )
    await db.execute(
        sa.text("UPDATE checklist_responses SET remark = :r WHERE wp_id = :w"), {}
    )
'''


def _expected_scan_surface() -> list[Path]:
    """`backend/app` 下的生产 `.py` 文件集，按与生成器同一条规则独立重算。"""
    root = _REPO / "backend" / "app"
    excluded = set(_NON_SHIPPING_PATH_SEGMENTS)
    return [
        path
        for path in sorted(root.rglob("*.py"))
        if not (excluded & {part.lower() for part in path.parts})
    ]


def _modules_with_at_least_one_function(paths: list[Path]) -> set[str]:
    """独立实现「这个模块里有函数吗」，不复用生成器的 `_iter_functions`/`_module_path`。

    两套实现比对才叫交叉验证：若两边都调生成器，收窄发现面时两边一起变小、判据不会红。
    """
    found: set[str] = set()
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        if any(
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            for node in ast.walk(tree)
        ):
            relative = path.relative_to(_REPO / "backend").with_suffix("")
            found.add(".".join(relative.parts))
    return found


def test_the_writer_denominator_is_every_production_module_under_backend_app(
    generator: ModuleType,
    source_scan: tuple[list[dict[str, Any]], dict[str, dict[str, Any]]],
) -> None:
    """**Validates: Requirements 2.2, 9.11** · Property 61

    发现面 = `backend/app` 下全部生产模块，逐模块比对。收窄 `_APP_ROOT`（只走 routers）或给
    `_is_production_source` 加一条排除，都会在这里红 —— 而不是安静地让两条欠账计数变小。
    """
    assert generator._APP_ROOT == _REPO / "backend" / "app", (
        f"发现面的根被改了：{generator._APP_ROOT}"
    )

    surface = _expected_scan_surface()
    assert len(surface) > 1500, (
        f"独立重算的生产文件只有 {len(surface)} 个 —— 本判据的分母塌了，比对会近乎空跑"
    )

    expected = _modules_with_at_least_one_function(surface)
    observed = {key.split("::", 1)[0] for key in source_scan[1]}
    assert observed == expected, (
        "生成器走过的模块集与独立重算的发现面不一致；"
        f"少走了 {sorted(expected - observed)[:8]}，多走了 {sorted(observed - expected)[:8]}"
    )

    # 发现面必须横跨多个顶层包：把它收窄成单个包（例如只剩 routers）时这条先红。
    # 模块名形如 `app.routers.wp_html_save` ⇒ 第 2 段是顶层包；只取真有包段的模块。
    packages = {module.split(".")[1] for module in observed if module.count(".") >= 2}
    assert {"routers", "services"} <= packages, f"发现面不再横跨 routers 与 services：{sorted(packages)[:12]}"


def test_the_production_source_predicate_excludes_exactly_the_non_shipping_trees(
    generator: ModuleType,
) -> None:
    """**Validates: Requirements 9.11**

    行为级、双向：四个非交付目录段各自都要被挡住（删掉任一条排除 ⇒ 红），普通业务包一个都
    不许被挡住（加一条排除把业务代码移出分母 ⇒ 红）。
    """
    for segment in _NON_SHIPPING_PATH_SEGMENTS:
        shadowed = _REPO / "backend" / "app" / segment / "mod.py"
        assert not generator._is_production_source(shadowed), (
            f"`{segment}/` 不再被排除出发现面 —— 非交付代码会混进 writer 分母"
        )

    for segment in _SHIPPING_PACKAGE_SAMPLE:
        shipping = _REPO / "backend" / "app" / segment / "mod.py"
        assert generator._is_production_source(shipping), (
            f"`{segment}/` 被排除出了发现面 —— 生产 writer 被移出分母，欠账计数会凭空变小"
        )


def test_both_workpaper_content_stores_stay_in_the_denominator(
    generator: ModuleType,
) -> None:
    """**Validates: Requirements 9.11**

    Requirement 9.11 的第二权威事实：底稿业务内容同时落在 `working_paper` 与
    `checklist_responses`（后者**没有任何版本列**）。把 `checklist_responses` 从内容存储表里
    拿掉，是把 97 行 writer 一次性移出分母的最短路径。

    判据落在**谓词行为**上而不是「实测计数 > 0」：迁移完成后这些 writer 会改走统一入口、不再
    自己写 SQL，计数式判据那时会变成假红。
    """
    assert set(generator._CONTENT_STORES) == {"working_paper", "checklist_responses"}, (
        f"内容存储表变了：{sorted(generator._CONTENT_STORES)}"
    )
    assert {"remark", "conclusion"} <= set(generator._CONTENT_STORES["checklist_responses"])
    assert {"parsed_data", "file_version", "file_path", "content_revision"} <= set(
        generator._CONTENT_STORES["working_paper"]
    )

    facts = _facts_of(generator, _BOTH_CONTENT_STORES_SOURCE, "save")
    assert "working_paper.parsed_data" in facts["sql_update_columns"]
    assert "checklist_responses.remark" in facts["sql_update_columns"], (
        "写 `checklist_responses.remark` 的函数不再被认成内容 writer"
    )
    # 正向到底：这样一个函数必须真的被分类成 writer，而不是只留下事实、分类时被丢掉。
    row = _synthetic_row(
        generator,
        writer_id="app.services.demo_two_stores::save",
        source=_BOTH_CONTENT_STORES_SOURCE,
        function_name="save",
        kind="writer",
    )
    assert set(
        generator.build_inventory(
            [row], {"schema_version": 1, "review_status": "reviewed", "adjudications": {}}
        )["stats"]["by_content_store"]
    ) == {"working_paper", "checklist_responses"}


def test_the_universal_scope_is_the_specs_own_definition_not_this_files(
    gate: ModuleType, generator: ModuleType, overlay: dict[str, Any]
) -> None:
    """**Validates: Requirements 2.2, 9.11** · Property 61

    provenance + 「枚举是地板」两件事。

    前者让收窄 scope 这个动作必须先改 spec 原话（于是有人会看到）；后者用 Task 3 自己的
    overlay 反驳窄读法 —— 它裁决进了一个正文枚举之外的 domain，若枚举就是 scope，那 6 条裁决
    自己越界了。
    """
    for label, (path, sentence) in _UNIVERSAL_SCOPE_PROVENANCE.items():
        text = path.read_bytes().decode("utf-8")
        assert text.count(sentence) == 1, (
            f"{label} 这句 scope 依据在 spec 里不再唯一存在（命中 {text.count(sentence)} 次）："
            f"「{sentence}」—— 分母的定义变了，Task 20 的结论要重算"
        )

    required = set(gate._REQUIRED_DOMAINS)
    declared = set(generator._DOMAINS)
    assert required < declared, (
        "门的必需 domain 集不再是生成器 domain 表的**真**子集 —— 「点名的 lane 是覆盖地板」"
        f"这层语义没了：required={sorted(required)} declared={sorted(declared)}"
    )

    adjudicated = {value["domain"] for value in overlay["adjudications"].values()}
    beyond = adjudicated - required
    assert beyond, (
        "Task 3 的 reviewed overlay 不再有任何裁决落在门点名的 lane 之外 —— 「枚举是地板不是"
        "天花板」这条反证消失了，窄读法就没有实证反驳了"
    )
