"""umbrella spec 的真源优先级与引用闭合性（tasks 0.2 / 0.5）。

spec: `workpaper-html-onlyoffice-bidirectional-writeback-closure`

本文件只做三件事，每条都可伪证：

1. **真源优先级**：`requirements.md` 的 AC 集合必须恰等于 paradigm JSON 登记的 AC 集合
   （逐字比对由 `test_migration_paradigm_contract.py::TestAcceptanceCriteriaVerbatim` 负责，
   这里只管「集合不多不少」，两者合起来才是「恰等于投影」）。
2. **引用闭合**：`tasks.md` 每条 `_AC:` 引用的编号必须都已登记（不存在未定义 AC 引用），
   且每条已登记 AC 至少被一条任务引用、至少有一个**存在于磁盘**的可执行验收面承接。
3. **归档只作引用**：已勾选任务的说明块里不得把 `_archive/` 路径当完成依据 —— 归档 spec 的
   复选框是别人的审计轨迹，不是本 spec 的状态输入（spec 开头的「完成标记规则」已写明）。

🔴 判据刻意**不**写死任务条数或 AC 条数：两者都会随 spec 推进变化，写死只会在推进时打红并
   指错人。分母用「非空 + 现算集合相等」表达。
"""
from __future__ import annotations

import ast
import json
import pathlib
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SPEC_DIR = (
    ROOT / ".kiro/specs/workpaper-html-onlyoffice-bidirectional-writeback-closure"
)
REQUIREMENTS = SPEC_DIR / "requirements.md"
TASKS = SPEC_DIR / "tasks.md"
PARADIGM = ROOT / "backend/data/workpaper_sync_migration_paradigm.json"

#: requirements.md 里 AC 行的形态：`1.3. …` / `12.8. …`
_AC_LINE = re.compile(r"^(?P<ac>\d+\.\d+)\.\s+(?P<text>\S.*)$", re.MULTILINE)
#: tasks.md 里的任务行与 AC 引用行
_TASK_LINE = re.compile(r"^- \[(?P<mark>[ x])\] (?P<id>\d+\.\d+) (?P<title>.+)$")
_AC_REF_LINE = re.compile(r"^\s*- _AC: (?P<refs>[\d., ]+)_\s*$")


def _registered_acs() -> set[str]:
    doc = json.loads(PARADIGM.read_text(encoding="utf-8"))
    return {
        str(item["ac"])
        for item in doc["adjudication_criteria"]["acceptance_criteria"]
    }


def _requirements_acs() -> set[str]:
    return {m.group("ac") for m in _AC_LINE.finditer(REQUIREMENTS.read_text(encoding="utf-8"))}


def _tasks() -> list[dict]:
    """逐任务取 (id, 勾选态, 标题, AC 引用集合, 说明块文本)。"""
    rows: list[dict] = []
    current: dict | None = None
    for line in TASKS.read_text(encoding="utf-8").split("\n"):
        task = _TASK_LINE.match(line)
        if task is not None:
            current = {
                "id": task.group("id"),
                "done": task.group("mark") == "x",
                "title": task.group("title"),
                "acs": set(),
                "body": [],
            }
            rows.append(current)
            continue
        if current is None:
            continue
        ref = _AC_REF_LINE.match(line)
        if ref is not None:
            current["acs"] |= {
                part.strip() for part in ref.group("refs").split(",") if part.strip()
            }
            continue
        if line.startswith("- [") or line.startswith("## "):
            current = None
            continue
        current["body"].append(line)
    return rows


#: AC → 承接它的可执行验收面（测试文件 / 检查脚本，仓库相对路径）。
#:
#: 判据是「至少一个承接面**存在于磁盘**」，不是「写了名字」—— 名字写错或文件被删都必须打红。
_ACCEPTANCE_SURFACES: dict[str, tuple[str, ...]] = {
    "1.3": (
        "backend/tests/test_workpaper_sync_manifest_contract.py",
        "backend/tests/workpaper_sync/test_current_state_projection.py",
        "backend/tests/workpaper_sync/test_cycle_current_projection.py",
    ),
    "1.4": (
        "backend/tests/workpaper_sync/test_entry_readiness.py",
        "backend/tests/workpaper_sync/test_entry_readiness_endpoint.py",
        "audit-platform/frontend/src/components/workpaper/sync/__tests__/entrySyncPresentation.spec.ts",
    ),
    "1.5": (
        "audit-platform/frontend/src/components/workpaper/sync/__tests__/entrySyncPresentation.spec.ts",
        "audit-platform/frontend/src/components/workpaper/sync/__tests__/workpaperEntrySyncNotice.spec.ts",
    ),
    "1.7": (
        "backend/scripts/check/check_workpaper_sync_closure.py",
        "backend/tests/workpaper_sync/test_task66_legacy_deletion_plan.py",
    ),
    "12.1": (
        "backend/scripts/check/check_workpaper_sync_closure.py",
        "backend/tests/workpaper_sync/test_task13_contract_registry.py",
        "backend/tests/workpaper_sync/test_pending_runtime_adjudication.py",
    ),
    "12.8": (
        "backend/tests/test_workpaper_sync_manifest_contract.py",
        "backend/tests/workpaper_sync/test_pending_runtime_adjudication.py",
    ),
    "12.9": (
        "backend/scripts/check/check_workpaper_sync_closure.py",
        "backend/tests/test_workpaper_sync_manifest_contract.py",
    ),
}


# ════════════════════════════════════════════════════════════════════════════
# 1. 真源优先级
# ════════════════════════════════════════════════════════════════════════════


def test_requirements_ac_set_equals_the_paradigm_projection() -> None:
    disk, registered = _requirements_acs(), _registered_acs()
    assert disk, "requirements.md 里一条 AC 都没解析出来 —— 判据会在空集上恒真"
    assert disk == registered, (
        f"仅在 requirements.md：{sorted(disk - registered)}；"
        f"仅在 paradigm：{sorted(registered - disk)} —— "
        "requirements 是 paradigm 的投影，改 AC 必须先改 JSON 再重生成"
    )


# ════════════════════════════════════════════════════════════════════════════
# 2. 引用闭合
# ════════════════════════════════════════════════════════════════════════════


def test_task_denominator_is_not_empty() -> None:
    rows = _tasks()
    assert len(rows) >= 40, f"只解析出 {len(rows)} 条任务 —— 解析口径失锚"
    assert all(row["acs"] for row in rows), (
        "以下任务没有 _AC: 引用："
        + ", ".join(row["id"] for row in rows if not row["acs"])
    )


def test_no_task_cites_an_undefined_ac() -> None:
    registered = _registered_acs()
    offenders = {
        row["id"]: sorted(row["acs"] - registered)
        for row in _tasks()
        if row["acs"] - registered
    }
    assert not offenders, f"任务引用了未登记的 AC：{offenders}"


def test_every_registered_ac_is_carried_by_some_task() -> None:
    cited: set[str] = set()
    for row in _tasks():
        cited |= row["acs"]
    missing = sorted(_registered_acs() - cited)
    assert not missing, f"以下 AC 没有任何任务承接：{missing}"


@pytest.mark.parametrize("ac", sorted(_registered_acs()))
def test_every_registered_ac_has_an_executable_surface_on_disk(ac: str) -> None:
    surfaces = _ACCEPTANCE_SURFACES.get(ac)
    assert surfaces, f"AC {ac} 没登记可执行验收面 —— 请在 _ACCEPTANCE_SURFACES 里补"
    present = [rel for rel in surfaces if (ROOT / rel).is_file()]
    assert present, (
        f"AC {ac} 登记的验收面一个都不在磁盘上：{list(surfaces)} —— "
        "写了名字不算承接，文件必须真实存在"
    )


def test_acceptance_surface_registry_has_no_stale_entries() -> None:
    """登记表不得留失效路径（改名/删除后必须同步），也不得给未登记 AC 挂面。"""
    registered = _registered_acs()
    stale_acs = sorted(set(_ACCEPTANCE_SURFACES) - registered)
    assert not stale_acs, f"登记表里有已不存在的 AC：{stale_acs}"
    missing_files = {
        ac: [rel for rel in surfaces if not (ROOT / rel).is_file()]
        for ac, surfaces in _ACCEPTANCE_SURFACES.items()
        if any(not (ROOT / rel).is_file() for rel in surfaces)
    }
    assert not missing_files, f"登记表里有不存在的路径：{missing_files}"


# ════════════════════════════════════════════════════════════════════════════
# 3. 归档只作引用
# ════════════════════════════════════════════════════════════════════════════


#: 「把归档当完成依据」的措辞特征。只要与 `_archive/` 同行出现，即判为拿别人的审计轨迹
#: 充本 spec 的状态。
_ARCHIVED_COMPLETION_CLAIM = re.compile(
    r"(复选框|已勾选|标绿|完成度|已完成|全绿|✅|\d+\s*/\s*\d+)"
)


def _cites_archive_as_completion(line: str) -> bool:
    """这一行是「拿归档的完成状态当依据」，还是只是「引用归档里的冻结文档」？

    🔴 原判据是「说明块里出现 `_archive/` 就红」。它把两件不同的事混成一件：

    * **真正要防的**：拿归档 spec 的复选框 / 完成度当本 spec 的完成依据
      （「归档里 77/77 全绿 ⇒ 本条完成」）—— 那是别人的审计轨迹。
    * **必须允许的**：引用归档里的**冻结文档快照**作为解析契约。task 0.6 把 Wave 6 形态的
      消费方按内容标记重绑到归档快照，说明块必须写清楚绑到哪里 —— 那是 trace，不是状态
      声明；不让写只会逼着把路径描述得含糊，反而更难复核。

    判别用「同一行是否带完成度措辞」，并配双向用例（下面那条判据）。
    """
    return "_archive/" in line and bool(_ARCHIVED_COMPLETION_CLAIM.search(line))


def test_completed_tasks_do_not_cite_archived_specs_as_evidence() -> None:
    offenders = {
        row["id"]: [line.strip() for line in row["body"] if _cites_archive_as_completion(line)]
        for row in _tasks()
        if row["done"] and any(_cites_archive_as_completion(line) for line in row["body"])
    }
    assert not offenders, (
        f"已勾选任务把归档 spec 的完成状态当依据：{offenders} —— "
        "归档 spec 的复选框是别人的审计轨迹，不是本 spec 的状态输入"
    )


def test_archive_citation_predicate_is_falsifiable() -> None:
    """判别谓词两个方向都要对，否则上一条要么恒绿要么误伤 trace。"""
    claim = "  - 依据：`_archive/17-xxx/<spec>/tasks.md` 已 77/77 全绿 ⇒ 本条完成"
    assert _cites_archive_as_completion(claim) is True, "拿归档完成度当依据竟未被认出"
    claim2 = "  - 归档 spec 的复选框显示 `_archive/17-xxx/<spec>` 已完成"
    assert _cites_archive_as_completion(claim2) is True
    trace = (
        "  - 冻结契约绑定：`_archive/17-2026-10-03-verified-batch/<同名目录>` "
        "（Wave 6 文档形态，按内容标记解析）"
    )
    assert _cites_archive_as_completion(trace) is False, "引用冻结文档快照被误伤"
    plain = "  - 产物：`backend/data/x.json`"
    assert _cites_archive_as_completion(plain) is False


def test_completion_count_in_the_header_matches_the_checkboxes() -> None:
    """标题里的 `N/M` 必须与实际勾选数一致 —— 手改任一侧都要打红。"""
    text = TASKS.read_text(encoding="utf-8")
    header = re.search(r"\*\*状态\*\*：(?P<done>\d+)/(?P<total>\d+)", text)
    assert header is not None, "tasks.md 开头缺 `**状态**：N/M`"
    rows = _tasks()
    assert int(header.group("total")) == len(rows), (
        f"标题写总数 {header.group('total')}，实际解析 {len(rows)} 条"
    )
    done = sum(1 for row in rows if row["done"])
    assert int(header.group("done")) == done, (
        f"标题写已完成 {header.group('done')}，实际勾选 {done} 条"
    )

# ════════════════════════════════════════════════════════════════════════════
# 4. 外部机器消费方闭合（doc → 脚本解析器）
# ════════════════════════════════════════════════════════════════════════════
#
# 🔴 这一节的**第一版是一张手写的 7 条清单**，而仓库里真实的消费方按 AST 现算是 **35 个**。
#    也就是说那张清单覆盖约两成，剩下八成「改文档会打坏谁」完全在视野之外 —— 而 0.5 的
#    全部目的正是补上「doc → 外部解析器」这条边。手写清单也不可能**发现**新消费方：
#    加一个脚本不会让任何判据打红。
#
#    现在分母**现算**：扫 `backend/{scripts,app,tests}` 的 `.py`，取 AST 里**非 docstring**
#    的字符串常量，凡同时出现 spec 目录名与三件套文件名之一即判为消费方。用 AST 而不是
#    文本匹配，是因为注释与 docstring 会正反两向骗过扫描器（本 spec 已为同一形态付过两次
#    代价）；docstring 显式剔除。
#
#    登记表落在 `backend/data/workpaper_sync_spec_doc_consumers.json`：**发现**是机器算的，
#    **分类与状态**是人工复核字段。分类刻意不自动填 —— 实测启发式会把 `10.1` 一类版本号
#    当成「旧 AC 编号」，把本文件（读 active）误判成 Wave 6 消费方。

CONSUMERS_JSON = ROOT / "backend/data/workpaper_sync_spec_doc_consumers.json"
SPEC_NAME = "workpaper-html-onlyoffice-bidirectional-writeback-closure"
_DOC_NAMES = ("requirements.md", "tasks.md", "design.md")
_DISCOVERY_ROOTS = ("backend/scripts", "backend/app", "backend/tests")
_ALLOWED_STATUS = {"ok", "retired", "registered_unreviewed"}
#: `registered_unreviewed` 只许变少。写下它时现算 26 条。
_UNREVIEWED_CEILING = 26


def _non_docstring_str_constants(source: str) -> set[str]:
    """AST 里**非 docstring** 的字符串常量。

    注释天然不进 AST；docstring 是 `Expr(Constant)`，这里显式剔除 —— 否则「某个脚本的
    文档里提到了 tasks.md」会被算成「它解析 tasks.md」。
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:  # pragma: no cover - 语法错误由别的门负责
        return set()
    docstrings: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(node, "body", None)
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                docstrings.add(id(body[0].value))
    return {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
    }


def _is_consumer(source: str) -> list[str]:
    """这份源码解析本 spec 的哪几份文档（空列表 = 不是消费方）。"""
    consts = _non_docstring_str_constants(source)
    if not any(SPEC_NAME in value for value in consts):
        return []
    docs = {
        name
        for name in _DOC_NAMES
        for value in consts
        if value == name
        or value.endswith("/" + name)
        or (SPEC_NAME in value and value.endswith(name))
    }
    return sorted(docs)


def _discover_consumers() -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for rel_root in _DISCOVERY_ROOTS:
        base = ROOT / rel_root
        if not base.exists():
            continue
        for path in base.rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            docs = _is_consumer(path.read_text(encoding="utf-8", errors="replace"))
            if docs:
                found[str(path.relative_to(ROOT)).replace("\\", "/")] = docs
    return found


@pytest.fixture(scope="module")
def registry() -> dict:
    return json.loads(CONSUMERS_JSON.read_text(encoding="utf-8"))


def test_consumer_discovery_is_falsifiable() -> None:
    """发现谓词必须认出真消费方，且不把「只在文档里提过」算进来。"""
    real = f'SPEC = "{SPEC_NAME}"\nTASKS = SPEC_DIR / "tasks.md"\n'
    assert _is_consumer(real) == ["tasks.md"]

    only_docstring = (
        '"""这个模块跟 ' + SPEC_NAME + ' 的 tasks.md 有关，但它一行都不读。"""\nX = 1\n'
    )
    assert _is_consumer(only_docstring) == [], "docstring 里提一句被算成消费方 ⇒ 分母虚高"

    only_comment = f"# 见 {SPEC_NAME} 的 design.md\nY = 2\n"
    assert _is_consumer(only_comment) == [], "注释被算成消费方 ⇒ 分母虚高"

    other_spec = 'SPEC = "formula-runtime-convergence"\nT = SPEC_DIR / "tasks.md"\n'
    assert _is_consumer(other_spec) == [], "别的 spec 的消费方不该进本分母"


def test_every_discovered_consumer_is_registered(registry: dict) -> None:
    """现算发现集合必须与登记表**逐条相等**。

    少登记 = 改文档时不知道会打坏谁（0.5 原本的缺口）；多登记 = 登记表里留着已删文件。
    """
    discovered = _discover_consumers()
    assert len(discovered) >= 20, (
        f"只发现 {len(discovered)} 个消费方 —— 扫描面塌了，本节判据会在小分母上恒绿"
    )
    registered = set(registry["consumers"])
    missing = sorted(set(discovered) - registered)
    stale = sorted(registered - set(discovered))
    assert not missing, (
        "以下文件解析本 spec 的文档却没登记（改文档不会有判据因它们打红）：\n"
        + "\n".join(f"  {rel} ← {discovered[rel]}" for rel in missing)
    )
    assert not stale, f"登记表里有已不再解析本 spec 文档的条目：{stale}"


def test_registered_consumers_exist_on_disk(registry: dict) -> None:
    missing = [rel for rel in registry["consumers"] if not (ROOT / rel).is_file()]
    assert not missing, f"登记表里有不存在的路径：{missing}"


def test_registry_counts_are_recomputed_not_asserted(registry: dict) -> None:
    """摘要必须与明细逐项相等（摘要从明细算，不是手写）。"""
    tally: dict[str, int] = {}
    for row in registry["consumers"].values():
        tally[row["status"]] = tally.get(row["status"], 0) + 1
    expected = {"total": len(registry["consumers"]), **{k: tally[k] for k in sorted(tally)}}
    assert registry["counts"] == expected, f"摘要 {registry['counts']} ≠ 明细现算 {expected}"


def test_consumer_status_vocabulary_is_closed(registry: dict) -> None:
    bad = {
        rel: row["status"]
        for rel, row in registry["consumers"].items()
        if row["status"] not in _ALLOWED_STATUS
    }
    assert not bad, f"status 不在封闭集合 {_ALLOWED_STATUS}：{bad}"
    ownerless = [
        rel for rel, row in registry["consumers"].items() if not str(row.get("owner_task") or "")
    ]
    assert not ownerless, f"以下条目没有 owner_task：{ownerless}"


def test_unreviewed_consumers_only_shrink(registry: dict) -> None:
    """未复核分类的消费方只许变少。

    🔴 这是**过渡量**不是不变量：它写明「还有多少个消费方的解析形态没人逐个看过」。
       清零的唯一路径是逐个复核改成 `ok` / `retired`，不是把上限抬上去。
    """
    unreviewed = sorted(
        rel
        for rel, row in registry["consumers"].items()
        if row["status"] == "registered_unreviewed"
    )
    assert len(unreviewed) <= _UNREVIEWED_CEILING, (
        f"未复核消费方从 {_UNREVIEWED_CEILING} 涨到 {len(unreviewed)}：{unreviewed}"
    )
    assert _UNREVIEWED_CEILING - len(unreviewed) <= 5, (
        f"上限 {_UNREVIEWED_CEILING} 比现算 {len(unreviewed)} 虚高太多 —— 棘轮要跟着收"
    )


def test_ok_frozen_consumers_bind_by_content_not_by_hardcoded_path(registry: dict) -> None:
    """判 `ok` 的 Wave 6 消费方必须按**内容标记**定位快照，不得写死 active 路径。

    写死 active 的那一版，报的是「tasks.md 里找不到 Task 68」这种**指错地方**的错误：
    契约没丢，它在归档快照里。
    """
    offenders: list[str] = []
    for rel, row in registry["consumers"].items():
        if row["status"] != "ok" or row["contract_kind"] != "frozen_wave6":
            continue
        source = (ROOT / rel).read_text(encoding="utf-8", errors="replace")
        if "resolve_spec_dir" not in source or "require_matches" not in source:
            offenders.append(rel)
    assert not offenders, (
        "以下 Wave 6 消费方标了 ok 却没按内容标记绑定快照：\n"
        + "\n".join(f"  {rel}" for rel in offenders)
    )
    ok_frozen = [
        rel
        for rel, row in registry["consumers"].items()
        if row["status"] == "ok" and row["contract_kind"] == "frozen_wave6"
    ]
    assert len(ok_frozen) >= 6, f"ok 的 Wave 6 消费方只有 {len(ok_frozen)} 个 ⇒ 判据失锚"


def test_frozen_contract_snapshot_really_carries_the_legacy_shape() -> None:
    """冻结快照必须真的含 Wave 6 形态 —— 否则「按内容绑定」绑到的是空气。

    并且 active 投影**不得**含这些锚点：两边都含的话「按内容选快照」就选不出东西，
    这条判据也就不是在守什么了。
    """
    import sys as _sys

    check_dir = str(ROOT / "backend" / "scripts" / "check")
    if check_dir not in _sys.path:
        _sys.path.insert(0, check_dir)
    from _spec_dir import resolve_spec_dir

    frozen = resolve_spec_dir(
        SPEC_NAME,
        require_files=["requirements.md", "design.md", "tasks.md"],
        require_matches={
            "requirements.md": (r"^### Requirement \d+", r"^7\.7\.", r"^14\.10\."),
            "design.md": (r"^### Property \d+", r"^## Acceptance Oracle Matrix$"),
        },
    )
    assert "_archive" in frozen.parts, (
        f"冻结形态竟解析到 {frozen} —— 若 active 已回到 Wave 6 形态，本 spec 的 0.5 / 0.6 "
        "结论需要重判，不能默默通过"
    )
    active_req = REQUIREMENTS.read_text(encoding="utf-8")
    assert not re.search(r"^### Requirement \d+", active_req, re.MULTILINE), (
        "active requirements 里出现了 `### Requirement N` 标题 —— 它应该是 7 条扁平 AC 投影"
    )


def test_retired_consumers_are_not_in_any_gate(registry: dict) -> None:
    """退役的消费方不得留在门禁里（与 test_task66_execution_ledger 同族逻辑）。"""
    retired = [rel for rel, row in registry["consumers"].items() if row["status"] == "retired"]
    assert retired, "一个退役条目都没有 ⇒ 本判据在空集上恒绿（task 5.5 已判 task66 生成器退役）"
    for rel in retired:
        script_name = pathlib.Path(rel).name
        for gate_rel in (
            ".github/workflows/ci.yml",
            ".github/workflows/governance-checks.yml",
            ".pre-commit-config.yaml",
            ".git-hooks/pre-commit",
            ".git-hooks/pre-push",
        ):
            gate_path = ROOT / gate_rel
            if not gate_path.is_file():
                continue
            assert script_name not in gate_path.read_text(encoding="utf-8", errors="replace"), (
                f"退役脚本 {script_name} 仍被 {gate_rel} 引用 —— 会长期全红"
            )
