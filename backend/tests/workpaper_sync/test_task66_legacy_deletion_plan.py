"""Task 66 守卫 —— legacy 删前清册 / replacement map / rollback 隔离门。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 6 Task 66
点名 Property：**3 / 46 / 47 / 48 / 51**；点名 AC：1.4 · 1.5 · 1.7 · 11.1 · 11.2 ·
11.5 · 11.8 · 11.10 · 12.7 · 12.8 · 12.9 · 12.13 · 12.14。

═══ 被守的产物 ═══

* `backend/scripts/gen/generate_task66_legacy_deletion_plan.py`（生成器；本文件
  **import 它并现读它的推导函数**，不抄第二份规则）
* `backend/data/workpaper_sync_task66_legacy_deletion_plan.json`（清册）

═══ 本轮判据与前几轮守卫的关键差异（照抄会假绿的点）═══

1. **本任务只生成计划**。「没改源码」不能靠人说 —— 本文件用 **AST** 断言生成器
   不 import DB 层、不调用发布/删除链、`write_text` 只对 `OUTPUT_PATH`，并且
   `unlink`/`rmtree`/`os.remove` 一个都不出现。
2. **清册最贵的缺陷是「名单过期」**。所以每一族都把记录里的事实喂回生成器的检测器
   重算：import 图（剥注释后按 specifier 解析）、mode key 前缀解析、路由 AST、
   `paragraph_index` 站点、成功文案站点 —— 记录被手改即打红。
3. **五个形态必须唯一归属**，且**逐条**独立断言（不合成一条集合判据）。两侧都归、
   两侧都不归、落到 `preserved_*` 上，三种都要红。
4. **rollback 门必须被真正度量，不能是重言式**。本文件做**反事实多臂实验**：把
   「replacement 未入库」「待删项未入库」「共用路径整文件删」「站点级删除未登记」
   四个前提逐一在内存里**移除**，门的 verdict 必须随之改变；不变即说明该判据
   度量的是别的东西（Task 61 的教训 13）。
5. **分母不得为空**。每族计数都要求 >0 或有显式的非空分母；空集恒真是假绿第⑥源。

用法（仓库根；PATH 上的 `python` 可能指向坏掉的解释器）::

    .\\.venv\\Scripts\\python.exe -m pytest backend/tests/workpaper_sync/test_task66_legacy_deletion_plan.py -q
"""

from __future__ import annotations

import ast
import copy
import json
import re
import sys
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

for _p in (BACKEND, GEN_DIR):
    if str(_p) not in sys.path:  # pragma: no cover - import 自举
        sys.path.insert(0, str(_p))

import generate_task66_legacy_deletion_plan as GEN  # noqa: E402

RECORD_PATH = DATA / "workpaper_sync_task66_legacy_deletion_plan.json"
GENERATOR_PATH = GEN_DIR / "generate_task66_legacy_deletion_plan.py"


# ════════════════════════════════════════════════════════════════════════════
# fixtures
# ════════════════════════════════════════════════════════════════════════════


@pytest.fixture(scope="module")
def record() -> dict[str, Any]:
    assert RECORD_PATH.is_file(), (
        f"{RECORD_PATH.name} 不存在 —— 先跑生成器 `--write`；缺文件时本套件必须打红而不是 skip"
    )
    payload = json.loads(RECORD_PATH.read_text(encoding="utf-8"))
    assert payload.get("schema_version") == GEN.SCHEMA_VERSION
    assert payload.get("task") == GEN.OWNER_TASK
    return payload


@pytest.fixture(scope="module")
def items(record: dict[str, Any]) -> list[dict[str, Any]]:
    rows = record["items"]
    assert rows, "清册 `items` 为空 —— 空清单会让本套件几乎全部恒真（假绿第⑥源）"
    return rows


@pytest.fixture(scope="module")
def sources() -> GEN.FrontendSources:
    return GEN.FrontendSources()


#: 昂贵对象一律进程内缓存：`ManifestFacts` 要对 186 个 entry × 3 个 authority model
#: 现算 required scenario，`GitFacts` 要跑一次 `git ls-files`。每个测试各建一次会把
#: 整套件从秒级拖到分钟级，而变异检验要跑 27 轮。
_MANIFEST_CACHE: dict[str, GEN.ManifestFacts] = {}
_GIT_CACHE: dict[str, GEN.GitFacts] = {}


def manifest_facts() -> GEN.ManifestFacts:
    if "v" not in _MANIFEST_CACHE:
        _MANIFEST_CACHE["v"] = GEN.ManifestFacts()
    return _MANIFEST_CACHE["v"]


def git_facts() -> GEN.GitFacts:
    if "v" not in _GIT_CACHE:
        _GIT_CACHE["v"] = GEN.GitFacts()
    return _GIT_CACHE["v"]


def _dotted(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        head = _dotted(node.value)
        return f"{head}.{node.attr}" if head else None
    return None


def _ast_facts(source: str) -> tuple[set[str], set[str], set[str], set[str]]:
    """AST 抽 `(import 模块名, 裸方法/函数名, 点分调用路径, write_* 的接收者名)`。

    走 AST 而不是子串：文档字符串里提到 `commit_bytes` 是**说明**，不是调用点
    （教训 12）。裸名与点分路径分开返回：`str.replace` 与 `os.replace` 同名不同义，
    只看裸 `replace` 会把路径分隔符规范化误判成文件改名（实测踩过）。
    """
    tree = ast.parse(source)
    imports: set[str] = set()
    calls: set[str] = set()
    dotted_calls: set[str] = set()
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
                full = _dotted(func)
                if full:
                    dotted_calls.add(full)
                if func.attr in {"write_text", "write_bytes"}:
                    recv = func.value
                    if isinstance(recv, ast.Name):
                        writes.add(recv.id)
                    elif isinstance(recv, ast.Attribute):
                        writes.add(recv.attr)
                    else:
                        writes.add(ast.dump(recv)[:40])
    return imports, calls, dotted_calls, writes


def _generator_ast_facts() -> tuple[set[str], set[str], set[str], set[str]]:
    return _ast_facts(GENERATOR_PATH.read_text(encoding="utf-8"))


# ════════════════════════════════════════════════════════════════════════════
# §1 守卫自检（比较器必须真的敏感；分母必须非空）
# ════════════════════════════════════════════════════════════════════════════


class TestGuardSelfChecks:
    def test_vocabularies_are_closed_non_empty_and_disjoint(self) -> None:
        for name, vocab in (
            ("CATEGORIES", GEN.CATEGORIES),
            ("DISPOSITIONS", GEN.DISPOSITIONS),
            ("FORMS", GEN.FORMS),
            ("ROLLBACK_MODES", GEN.ROLLBACK_MODES),
            ("DELETION_UNITS", GEN.DELETION_UNITS),
        ):
            assert vocab, f"{name} 为空 —— 封闭词表退化成任意字符串"
            assert len(set(vocab)) == len(vocab), f"{name} 有重复取值"
        # 七类与五形态不得共用取值，否则「category 是 form」这种混用无人把守。
        assert len(set(GEN.CATEGORIES) & set(GEN.FORMS)) == 1, (
            "只允许 `fail_open_success_message` 一个名字在两张表里同名同义；"
            f"实测交集 {sorted(set(GEN.CATEGORIES) & set(GEN.FORMS))}"
        )
        assert set(GEN.FORM_ADMISSIBLE_DISPOSITIONS) < set(GEN.DISPOSITIONS)
        assert "preserved_until_replacement_lands" not in GEN.FORM_ADMISSIBLE_DISPOSITIONS

    def test_comment_stripper_really_strips_and_keeps_line_count(self) -> None:
        """反向自检：注释里的 import 必须消失，行数必须不变，URL 里的 `//` 必须留。"""
        src = (
            "import A from './a'\n"
            "// import B from './b'\n"
            "/* import C from './c'\n"
            "   still comment */\n"
            "<!-- import D from './d' -->\n"
            "const u = 'https://example.com/x'\n"
        )
        out = GEN.strip_comments(src)
        assert out.count("\n") == src.count("\n"), "剥注释改变了行数 ⇒ 行号判据全错位"
        assert "./a" in out
        for gone in ("./b", "./c", "./d"):
            assert gone not in out, f"{gone} 没被剥掉"
        assert "https://example.com/x" in out, "URL 里的 `//` 被当成行注释"

    def test_the_import_graph_is_not_fooled_by_a_comment(
        self, sources: GEN.FrontendSources
    ) -> None:
        """🔴 本任务最核心的一条自检（教训 12 的原样复现）。

        `GtG7LongTermEquityMain.vue` 里有一句注释提到 `WorkpaperSyncEditorHost`。
        剥注释后的 import 图里它**不得**成为 `WorkpaperSyncEditorHost.vue` 的消费方；
        而未剥注释的子串判据一定会命中 —— 两侧都断言，缺一条就说明这条判据没在度量。
        """
        host = ROOT / "audit-platform/frontend/src/components/workpaper/sync/WorkpaperSyncEditorHost.vue"
        g7 = ROOT / "audit-platform/frontend/src/components/workpaper/GtG7LongTermEquityMain.vue"
        assert host.is_file() and g7.is_file()
        raw = sources.raw[g7]
        assert "WorkpaperSyncEditorHost" in raw, (
            "前提变了：G7 宿主里已经没有提到 WorkpaperSyncEditorHost 的那句注释，"
            "本自检失去对照 —— 请改用另一处真实注释"
        )
        assert "WorkpaperSyncEditorHost" not in sources.code[g7], (
            "剥注释后 G7 宿主里仍出现 WorkpaperSyncEditorHost ⇒ 它变成了真 import，"
            "本记录关于「替代面零生产消费方」的结论需要重算"
        )
        assert GEN.rel(g7) not in sources.production_importers(host)

    def test_brace_matcher_skips_the_parameter_list(self) -> None:
        """教训 14：TS 返回类型注解 `): Promise<{…}>` 会骗到「第一个 `{`」。"""
        code = (
            "function f(a: {x: number}): Promise<{y: string}> {\n"
            "  const p = 'pre-'\n"
            "  return `${p}${a.x}`\n"
            "}\n"
        )
        bodies = GEN._function_bodies(code)
        assert "f" in bodies, "函数体没截出来"
        assert "return `${p}${a.x}`" in bodies["f"]
        assert GEN._resolve_key_prefix("f()", code) == "pre-"

    def test_key_prefix_resolver_handles_all_three_real_forms(self) -> None:
        """常量相加 / 函数间接 / 直接模板 三种形态各造一个正例 + 一个解析不出的反例。"""
        const_form = "const STORAGE_PREFIX = 'k8-dual-mode:'\nlocalStorage.getItem(STORAGE_PREFIX + wpId.value)\n"
        assert GEN._resolve_key_prefix("STORAGE_PREFIX + wpId.value", const_form) == "k8-dual-mode:"
        fn_form = (
            "const STORAGE_KEY_PREFIX = 'l1-dual-mode-'\n"
            "function _getStorageKey(): string {\n"
            "  const id = wpId.value\n"
            "  return `${STORAGE_KEY_PREFIX}${id}`\n"
            "}\n"
        )
        assert GEN._resolve_key_prefix("_getStorageKey()", fn_form) == "l1-dual-mode-"
        tmpl = "const P = 'x-mode:'\n"
        assert GEN._resolve_key_prefix("`${P}${id}`", tmpl) == "x-mode:"
        assert GEN._resolve_key_prefix("someUnknown(a, b)", "") is None

    def test_mode_state_field_detector_requires_a_real_ref(self) -> None:
        """反向自检：**数据里**出现的 `currentMode` 不算状态机，`= ref(` 才算。

        反例刻意照抄 `workpaperSyncLegacyBaseline.generated.ts` 里真实的那一行形态
        （characterization 快照把宿主模板片段当**字符串数据**存了下来）：
        `"snippet": "v-if=\\"currentMode === 'onlyoffice'\\""`。
        这行里 `currentMode` 后面紧跟 `===`，宽松判据 `\\s*[:=]` 会命中它的第一个 `=`
        ⇒ 165 KB 的快照文件被判成一个 legacy 状态机（实测踩过的假阳性）。
        """
        data_only = "\"snippet\": \"v-if=\\\"currentMode === 'onlyoffice'\\\"\""
        assert GEN._mode_state_fields(data_only) == [], (
            "把快照数据里的 `currentMode ===` 当成状态机字段 ⇒ "
            "165 KB 的 generated baseline 会被误判成待删 legacy 状态机"
        )
        assert GEN._mode_state_fields('{ "currentMode": "html" }') == []
        real = "const currentMode = ref<DualModeType>('html')\nconst checking = ref(false)\n"
        assert GEN._mode_state_fields(real) == ["checking", "currentMode"]

    def test_success_site_detector_needs_both_success_and_oo_semantics(self) -> None:
        assert GEN._success_sites("ElMessage.success('OnlyOffice 拉取成功')")
        assert GEN._success_sites("ElMessage.success('已保存')") == [], (
            "与 OO 语义无关的成功文案被算进来 ⇒ 分子虚高"
        )
        assert GEN._success_sites("console.log('OnlyOffice 拉取成功')") == []


# ════════════════════════════════════════════════════════════════════════════
# §2 三边锁：源码边 / 替代面边 / 清册边逐条现算重算
# ════════════════════════════════════════════════════════════════════════════


class TestThreeWayLock:
    def test_every_item_path_exists_and_hash_matches_disk(
        self, items: list[dict[str, Any]]
    ) -> None:
        for item in items:
            path = ROOT / item["path"]
            assert path.is_file(), f"{item['item_id']}: 清册里的路径已不在磁盘上"
            assert GEN.sha256_of(path) == item["sha256"], (
                f"{item['item_id']}: sha256 与磁盘不符 —— 清册过期或被手改"
            )

    def test_legacy_composable_denominator_recomputes_from_disk(
        self, items: list[dict[str, Any]], sources: GEN.FrontendSources
    ) -> None:
        """C1/C2 的文件集合必须与磁盘现扫一致（多一个少一个都红）。"""
        on_disk = {
            GEN.rel(p)
            for p in sources.files
            if GEN._LEGACY_COMPOSABLE_NAME.match(p.name)
            and not GEN._is_test_path(GEN.rel(p))
        }
        pilot_deleted = set(
            GEN.load_json(GEN.PILOT_DELETION_PLAN_PATH)
            and [
                p["legacy_composable"]["file"]
                for p in GEN.load_json(GEN.PILOT_DELETION_PLAN_PATH)["pilots"]
            ]
        )
        recorded = {
            item["path"]
            for item in items
            if item["category"] in {"legacy_composable", "legacy_factory"}
        }
        expected = on_disk - pilot_deleted
        assert expected, "legacy composable 分母为空"
        assert expected <= recorded, f"漏登记：{sorted(expected - recorded)[:5]}"

    def test_task45_pilot_composables_are_absent_from_disk_and_from_the_plan(
        self, record: dict[str, Any], items: list[dict[str, Any]]
    ) -> None:
        """Task 66 正文第 2 条：Task 45 已删的 pilot 以其 post-delete 状态为准。"""
        planned = record["task45_pilot_post_delete_state"]["planned_deletions"]
        assert planned, "Task 45 的 pilot 删除清单为空 —— 交叉锁失效"
        assert record["task45_pilot_post_delete_state"]["still_on_disk"] == []
        recorded = {item["path"] for item in items}
        for path in planned:
            assert not (ROOT / path).is_file(), f"{path} 又回到磁盘上了"
            assert path not in recorded, f"{path} 已被 Task 45 删除却又被本清册列了一遍"

    def test_import_graph_facts_recompute(
        self, items: list[dict[str, Any]], sources: GEN.FrontendSources
    ) -> None:
        checked = 0
        for item in items:
            facts = item["facts"]
            if "production_importers" not in facts:
                continue
            path = ROOT / item["path"]
            assert facts["production_importers"] == sources.production_importers(path), (
                f"{item['item_id']}: 生产消费方清单与 import 图现算不符"
            )
            assert facts["production_importer_count"] == len(
                facts["production_importers"]
            )
            checked += 1
        assert checked >= 50, f"只重算了 {checked} 项的消费方 —— 覆盖面不足"

    def test_mode_key_prefixes_recompute_from_source(
        self, items: list[dict[str, Any]], sources: GEN.FrontendSources
    ) -> None:
        live = {
            site["key_prefix"] for site in GEN.mode_storage_sites(sources)
        }
        recorded = {
            item["symbols"][0]
            for item in items
            if item["category"] == "legacy_local_storage_key"
            and item["facts"]["storage_access_style"] == "direct_global_localStorage"
        }
        assert live, "现算的 mode key 前缀集合为空"
        assert live == recorded, (
            f"只在源码里 {sorted(live - recorded)[:5]}；只在清册里 {sorted(recorded - live)[:5]}"
        )

    def test_migration_regex_coverage_recomputes_against_the_replacement_source(
        self, items: list[dict[str, Any]]
    ) -> None:
        """旧键覆盖面必须用**替代面 TS 源码里现读的**正则重算。"""
        pattern, compiled = GEN.legacy_key_migration_regex()
        rows = [i for i in items if i["category"] == "legacy_local_storage_key"]
        assert rows, "localStorage 族为空"
        uncovered = 0
        for item in rows:
            facts = item["facts"]
            assert facts["migration_regex"] == pattern, (
                f"{item['item_id']}: 清册里的迁移正则与替代面源码不符"
            )
            expected = bool(compiled.match(facts["probe_key"]))
            assert facts["covered_by_migration_regex"] == expected, (
                f"{item['item_id']}: 覆盖判定与现算不符"
            )
            uncovered += 0 if expected else 1
        assert uncovered > 0, (
            "一个未被迁移正则覆盖的旧键都没有 ⇒ AC 11.8 的「过期值不得打开不支持模式」"
            "这条判据变成空转；实测存在 `f4-ap-mode:` / `g7-sub-mode-` 这类不带 "
            "`-dual-mode:` 的键"
        )

    def test_router_routes_recompute_by_ast(
        self, items: list[dict[str, Any]]
    ) -> None:
        recorded: dict[str, set[str]] = {}
        for item in items:
            if item["category"] != "legacy_endpoint":
                continue
            recorded.setdefault(item["path"], set()).add(item["facts"]["route"]["function"])
        assert recorded, "endpoint 族为空"
        for router_rel, functions in recorded.items():
            live = {r["function"] for r in GEN.router_routes(ROOT / router_rel)}
            assert live == functions, (
                f"{router_rel}: AST 现算 {sorted(live - functions)} 未登记 / "
                f"{sorted(functions - live)} 已不存在"
            )

    def test_paragraph_index_sites_recompute(
        self, items: list[dict[str, Any]]
    ) -> None:
        live = GEN.paragraph_fallback_sites()
        by_file: dict[str, list[int]] = {}
        for site in live:
            by_file.setdefault(site["file"], []).append(site["line"])
        rows = [i for i in items if i["category"] == "paragraph_index_fallback"]
        assert rows, "paragraph fallback 族为空"
        assert {i["path"] for i in rows} == set(by_file)
        for item in rows:
            assert [s["line"] for s in item["facts"]["sites"]] == sorted(
                by_file[item["path"]]
            )

    def test_ac_11_5_event_list_is_read_live_from_requirements(
        self, record: dict[str, Any]
    ) -> None:
        live = GEN.ac_11_5_required_events()
        assert record["ac_11_5_required_events"] == live
        # 分母非空且真含 AC 原文点名的关键事件（抓串了就会漏）。
        for event in ("ready", "dirty", "error"):
            assert event in live, f"AC 11.5 的事件清单里没有 {event} —— 抓取正则串了"

    def test_owner_tasks_all_exist_in_tasks_md(
        self, record: dict[str, Any], items: list[dict[str, Any]]
    ) -> None:
        known = GEN.tasks_md_task_ids()
        assert known, "tasks.md 任务集合为空"
        for item in items:
            owner = item["owner"]
            assert owner["replacement_owner_task"] in known, item["item_id"]
            assert owner["deletion_owner_task"] in known, item["item_id"]
        # 循环 → owner 映射必须与 tasks.md 现算一致（任务号漂移即红）。
        assert record["owner_derivation"]["cycle_owner_tasks"] == GEN.cycle_owner_tasks()
        assert (
            record["owner_derivation"]["deletion_execution_owner_task"]
            == GEN.deletion_execution_owner()
        )

    def test_deletion_owner_is_not_task66(self, record: dict[str, Any]) -> None:
        """本任务只生成计划：删除执行方必须是别的任务。"""
        assert (
            record["owner_derivation"]["deletion_execution_owner_task"] != GEN.OWNER_TASK
        )
        for item in record["items"]:
            assert item["owner"]["deletion_owner_task"] != GEN.OWNER_TASK, item["item_id"]


# ════════════════════════════════════════════════════════════════════════════
# §3 五个必绑字段
# ════════════════════════════════════════════════════════════════════════════


class TestFiveBindingsArePresentAndSound:
    def test_every_item_has_all_five_bindings(
        self, record: dict[str, Any], items: list[dict[str, Any]]
    ) -> None:
        required = record["required_bindings"]
        assert set(required) == set(GEN.REQUIRED_BINDINGS)
        assert len(required) == 5, f"必绑字段应为 5 个，实测 {len(required)}"
        for item in items:
            for field in required:
                assert item.get(field), f"{item['item_id']}: 必绑字段 {field} 为空"

    def test_replacement_targets_exist_and_are_on_the_replacement_surface(
        self, items: list[dict[str, Any]]
    ) -> None:
        for item in items:
            target = ROOT / item["replacement"]["path"]
            assert target.is_file(), f"{item['item_id']}: replacement 靶不存在"
            assert GEN.sha256_of(target) == item["replacement"]["target_sha256"], (
                f"{item['item_id']}: replacement 靶的 sha256 与磁盘不符"
            )
            assert item["replacement"]["kind"], f"{item['item_id']}: replacement kind 为空"

    def test_last_call_site_binding_is_exactly_one_of_site_or_reason(
        self, items: list[dict[str, Any]]
    ) -> None:
        with_site = 0
        with_reason = 0
        for item in items:
            binding = item["last_call_site_binding"]
            has_site = binding["site"] is not None
            has_reason = binding["absent_reason"] is not None
            assert has_site != has_reason, (
                f"{item['item_id']}: site 与 absent_reason 必须恰有一个非空 —— "
                "两个都填 = 自相矛盾，两个都空 = 「最后调用点」这一绑定形同不存在"
            )
            if has_site:
                assert binding["site"]["file"] and binding["site"]["line"] > 0
                with_site += 1
            else:
                with_reason += 1
        assert with_site > 0 and with_reason > 0, (
            f"两侧必须都有实例（site={with_site} reason={with_reason}）；"
            "只有一侧说明这条判据在当前数据上恒真"
        )

    def test_binding_helper_rejects_both_and_neither(self) -> None:
        """自检：XOR 约束必须由**实现**强制，不是靠当前数据恰好满足。

        当前 215 项里没有一项同时填了 site 与 absent_reason，所以只看记录的话，
        把实现里的 XOR 检查删掉也不会有任何一条判据变红（等价变异）。这条把它按住。
        """
        site = {"file": "a.ts", "line": 1, "snippet": "x"}
        with pytest.raises(GEN.Task66GeneratorError):
            GEN._last_call_site_binding(site, "some_reason", needles=["x"])
        with pytest.raises(GEN.Task66GeneratorError):
            GEN._last_call_site_binding(None, None, needles=["x"])
        with pytest.raises(GEN.Task66GeneratorError):
            GEN._last_call_site_binding(site, None, needles=[])
        ok = GEN._last_call_site_binding(site, None, needles=["x"])
        assert ok["site"] == site and ok["absent_reason"] is None

    def test_rollback_target_helper_distinguishes_tracked_from_untracked(self) -> None:
        """自检：rollback 形态必须随 tracked 事实分叉（对照组先过 —— 教训 5）。"""
        git = git_facts()
        tracked_path = "backend/app/routers/wp_onlyoffice_router.py"
        assert git.is_tracked(tracked_path), "对照组前提变了：该文件已不再被 git 跟踪"
        tracked = GEN._rollback_target(tracked_path, disposition="pending_delete", git=git)
        assert tracked["mode"] == "git_blob_at_plan_commit"
        untracked_path = "audit-platform/frontend/src/components/workpaper/sync/usePilotBridgeAdapter.ts"
        assert not git.is_tracked(untracked_path), (
            "对照组前提变了：替代面已入库 —— 请同步解除 BP-66-2"
        )
        untracked = GEN._rollback_target(
            untracked_path, disposition="pending_delete", git=git
        )
        assert untracked["mode"] == "pre_delete_snapshot_required"
        assert untracked["recoverable_from_git"] is False

    def test_recorded_last_call_site_really_contains_the_symbol(
        self, items: list[dict[str, Any]], sources: GEN.FrontendSources
    ) -> None:
        """反向守卫：登记的「最后调用点」必须在源码里真能定位到该符号。"""
        checked = 0
        for item in items:
            binding = item["last_call_site_binding"]
            site = binding["site"]
            if site is None:
                continue
            code = GEN.strip_comments(
                (ROOT / site["file"]).read_text(encoding="utf-8", errors="replace")
            ).split("\n")
            assert 1 <= site["line"] <= len(code), f"{item['item_id']}: 行号越界"
            line = code[site["line"] - 1]
            needles = binding["needles"]
            assert needles, f"{item['item_id']}: 绑定缺 needles"
            assert any(n and n in line for n in needles), (
                f"{item['item_id']}: 登记的最后调用点 {site['file']}#L{site['line']} 行上"
                f"找不到 {needles} 里任何一个字符串 —— 清册的行号已经漂移"
            )
            checked += 1
        assert checked >= 100, f"只核了 {checked} 处最后调用点 —— 覆盖面不足"
        del sources

    def test_rollback_targets_are_consistent_with_git(
        self, items: list[dict[str, Any]]
    ) -> None:
        git = git_facts()
        for item in items:
            target = item["rollback_target"]
            assert target["mode"] in GEN.ROLLBACK_MODES, item["item_id"]
            assert target["plan_commit"] == git.head_commit, (
                f"{item['item_id']}: rollback target 的 plan commit 不是当前 HEAD ⇒ "
                "清册是在别的 commit 上生成的"
            )
            tracked = git.is_tracked(item["path"])
            assert target["tracked_at_plan_time"] == tracked, item["item_id"]
            assert target["recoverable_from_git"] == tracked, item["item_id"]
            if item["disposition"] != "pending_delete":
                assert target["mode"] == "no_deletion_planned", item["item_id"]
            else:
                assert target["mode"] == (
                    "git_blob_at_plan_commit" if tracked else "pre_delete_snapshot_required"
                ), item["item_id"]

    def test_required_scenario_evidence_is_unverifiable_and_recomputes(
        self, record: dict[str, Any], items: list[dict[str, Any]]
    ) -> None:
        sets = record["manifest_required_scenario_sets"]
        assert sets, "顶层的 required scenario 集合为空"
        # 现算一次：只核记录会让「把 UNVERIFIABLE 改成已验收」变成等价变异。
        live_probe = manifest_facts().scenario_evidence(
            sorted(sets)[:1]
        )
        assert live_probe["status"] == "UNVERIFIABLE", (
            f"实现现算出的 evidence 状态是 {live_probe['status']!r} —— "
            "本任务不运行真实 OO 场景，approved bundle 供给实测为 0（AC 12.10）"
        )
        assert live_probe["refresh_owner_task"] == "70"
        for item in items:
            evidence = item["required_scenario_evidence"]
            assert evidence["status"] == "UNVERIFIABLE", (
                f"{item['item_id']}: 本任务不运行真实 OO 场景，evidence 不得宣称已验收"
            )
            assert evidence["refresh_owner_task"] == "70"
            union: set[str] = set()
            derived = 0
            for entry_id in evidence["bound_entry_ids"]:
                row = sets.get(entry_id)
                assert row is not None, f"{item['item_id']}: entry {entry_id} 不在顶层集合里"
                if row["status"] == "derived":
                    union |= set(row["scenario_ids"])
                    derived += 1
                else:
                    assert entry_id in evidence["underivable_entry_ids"]
            assert sorted(union) == evidence["scenario_id_union"], item["item_id"]
            assert derived == evidence["derived_entry_count"], item["item_id"]

    def test_scenario_sets_recompute_from_the_impl(
        self, record: dict[str, Any]
    ) -> None:
        """required set 必须由 impl 现算，不是抄的。"""
        live = manifest_facts()
        assert record["manifest_required_scenario_sets"] == live.scenarios
        underivable = [
            entry_id
            for entry_id, row in live.scenarios.items()
            if row["status"] != "derived"
        ]
        assert underivable, (
            "一个 required set 都推不出来的 entry 都没有 ⇒ 「drift 如实记 error」这条"
            "判据空转；实测有 capability=single_html 却 room_model=exclusive 的漂移 entry"
        )
        for entry_id in underivable:
            row = live.scenarios[entry_id]
            assert row["error_type"], f"{entry_id}: 推不出来却没记 error 类型（fail-open）"
            assert row["required_scenario_set_digest"] is None

    def test_scenario_probe_is_declared_as_a_probe_not_a_verdict(
        self, record: dict[str, Any]
    ) -> None:
        probe = record["required_scenario_probe"]
        assert probe["probe_authority_model"] in {
            m.value for m in GEN.AuthorityModel
        }
        assert probe["alternatives_probed"], "没探测别的 authority model ⇒ 敏感性未证明"
        assert probe["entries_whose_scenario_set_changes"] > 0, (
            "换 authority model 后一个 entry 的 scenario 集合都不变 ⇒ 「这只是探针」"
            "这句话没有实证支撑；反过来说，如果真的不变，本清册的 digest 就可以当最终值了"
        )


# ════════════════════════════════════════════════════════════════════════════
# §4 五个形态的唯一归属（逐条独立断言）
# ════════════════════════════════════════════════════════════════════════════


class TestFiveFormsAreUniquelyDisposed:
    def test_all_five_forms_are_present_in_the_record(
        self, record: dict[str, Any]
    ) -> None:
        findings = record["form_findings"]
        assert set(findings) == set(GEN.FORMS), (
            f"少了 {sorted(set(GEN.FORMS) - set(findings))} / "
            f"多了 {sorted(set(findings) - set(GEN.FORMS))}"
        )

    @pytest.mark.parametrize("form", GEN.FORMS)
    def test_each_form_has_a_non_vacuous_denominator(
        self, record: dict[str, Any], form: str
    ) -> None:
        """逐形态独立断言（不合成一条集合判据 —— 教训 3）。"""
        finding = record["form_findings"][form]
        assert finding["denominator"] > 0, f"{form}: 分母为 0 ⇒ 该形态的结论恒真"
        assert finding["denominator_meaning"], f"{form}: 分母没有口径说明"
        assert finding["count"] == len(finding["subjects"])

    @pytest.mark.parametrize("form", GEN.FORMS)
    def test_each_form_subject_has_exactly_one_admissible_disposition(
        self, record: dict[str, Any], form: str
    ) -> None:
        finding = record["form_findings"][form]
        assert finding["subjects"], (
            f"{form}: 一个 subject 都没有 —— Task 66 正文要求证明这五个形态"
            "「全部被唯一归入 replacement 或 pending-delete」，空集不算证明"
        )
        seen: set[str] = set()
        for subject in finding["subjects"]:
            disposition = subject["disposition"]
            assert disposition in GEN.FORM_ADMISSIBLE_DISPOSITIONS, (
                f"{form}/{subject['subject_id']}: disposition={disposition} 越出 "
                f"{GEN.FORM_ADMISSIBLE_DISPOSITIONS} —— 形态不得落在 preserved 上"
            )
            assert subject["subject_id"] not in seen, (
                f"{form}: subject {subject['subject_id']} 出现两次 ⇒ 归属不唯一"
            )
            seen.add(subject["subject_id"])

    def test_unconsumed_bridge_subjects_are_all_on_the_replacement_side(
        self, record: dict[str, Any]
    ) -> None:
        """形态①：无消费 bridge 必须归 `replacement`（它是靶，不是待删）。"""
        finding = record["form_findings"]["unconsumed_bridge"]
        for subject in finding["subjects"]:
            assert subject["disposition"] == "replacement", subject
            assert subject["transitive_production_importer_count"] >= 0
        paths = {s["path"] for s in finding["subjects"]}
        pending = {
            i["path"] for i in record["items"] if i["disposition"] == "pending_delete"
        }
        assert not (paths & pending), (
            f"同一路径既是无消费 bridge 又在待删清单里：{sorted(paths & pending)}"
        )

    def test_unconsumed_bridge_is_recomputed_from_the_import_graph(
        self, record: dict[str, Any], sources: GEN.FrontendSources
    ) -> None:
        for row in record["replacement_registry"]:
            if row["side"] != "frontend":
                continue
            path = ROOT / row["path"]
            transitive = sources.transitive_production_importers(path)
            outside = [
                p for p in transitive if not p.startswith(GEN.rel(GEN.SYNC_DIR) + "/")
            ]
            assert row["reachable_from_production_host"] == bool(outside), (
                f"{row['path']}: 可达性与 import 图现算不符"
            )

    def test_the_canonical_bridge_is_among_the_unconsumed_subjects(
        self, record: dict[str, Any]
    ) -> None:
        """禁令/名单类判据必须**包含那个真实目标**（Task 64 的 M13 教训）。

        只断言「清单非空 + 逐条成立」会被改名绕过：把 `useWorkpaperSyncBridge.ts`
        换个名字，清单照样非空、逐条照样成立。
        """
        paths = {s["path"] for s in record["form_findings"]["unconsumed_bridge"]["subjects"]}
        bridge = GEN.rel(GEN.BRIDGE_TS)
        host = GEN.rel(GEN.EDITOR_HOST_VUE)
        assert bridge in paths, (
            f"统一 bridge（{bridge}）不在无消费清单里 —— 要么它真的被宿主消费了"
            "（那 BP-66-1 应当解除），要么这条判据没有落到真实目标上"
        )
        assert host in paths, f"统一编辑器宿主（{host}）不在无消费清单里"

    def test_single_fake_switch_subjects_trace_to_a_non_bidirectional_entry(
        self, record: dict[str, Any], items: list[dict[str, Any]]
    ) -> None:
        """形态③：假切换必须能追到一个 capability 非 bidirectional 的真 entry。"""
        manifest = manifest_facts()
        live = set(manifest.single_switch_entries())
        assert live, "single 假切换的 entry 分母为空"
        by_id = {i["item_id"]: i for i in items}
        for subject in record["form_findings"]["single_fake_switch"]["subjects"]:
            item = by_id[subject["subject_id"]]
            bound = set(item["required_scenario_evidence"]["bound_entry_ids"])
            assert bound & live, (
                f"{subject['subject_id']}: 标了 single 假切换却追不到任何"
                "「capability 非 bidirectional 且仍显示切换」的 entry"
            )
        for entry_id in sorted(live)[:5]:
            entry = next(e for e in manifest.entries if e["entry_id"] == entry_id)
            assert entry["capability"] != "bidirectional"

    def test_fail_open_message_subjects_have_no_durable_ack_symbol(
        self, items: list[dict[str, Any]]
    ) -> None:
        """形态④：fail-open 文案的判据是「文件里没有任何 durable ack 符号」。"""
        rows = [i for i in items if i["category"] == "fail_open_success_message"]
        assert rows, "fail-open 文案族为空"
        for item in rows:
            code = GEN.strip_comments(
                (ROOT / item["path"]).read_text(encoding="utf-8", errors="replace")
            )
            assert GEN._durable_symbols(code) == [], (
                f"{item['item_id']}: 文件里其实有 durable ack 符号 "
                f"{GEN._durable_symbols(code)} ⇒ 不该判成 fail-open"
            )
            site = item["facts"]["site"]
            line = code.split("\n")[site["line"] - 1]
            assert GEN._SUCCESS_CALL.search(line) and GEN._OO_SEMANTICS.search(line), (
                f"{item['item_id']}: 登记的成功文案行已漂移"
            )

    def test_unreachable_stub_subjects_really_have_no_consumer_or_entry(
        self, record: dict[str, Any], items: list[dict[str, Any]], sources: GEN.FrontendSources
    ) -> None:
        """形态⑤：不可达桩必须真的零生产消费方，或绑定到 unreachable entry。"""
        manifest = manifest_facts()
        unreachable_entries = {
            str(e["entry_id"])
            for e in manifest.entries
            if str(e.get("capability")) == "unreachable"
            or str(e.get("migration_state")) == "unreachable_pending_delete"
        }
        assert unreachable_entries, "manifest 里没有 unreachable entry —— 该侧分母为空"
        by_id = {i["item_id"]: i for i in items}
        for subject in record["form_findings"]["unreachable_stub"]["subjects"]:
            item = by_id[subject["subject_id"]]
            zero_consumers = (
                item["facts"].get("production_importer_count") == 0
            )
            bound = set(item["required_scenario_evidence"]["bound_entry_ids"])
            assert zero_consumers or (bound & unreachable_entries), (
                f"{subject['subject_id']}: 既有生产消费方又不绑 unreachable entry"
            )
            if zero_consumers:
                assert sources.production_importers(ROOT / item["path"]) == []


# ════════════════════════════════════════════════════════════════════════════
# §5 rollback 隔离门：判据必须被真正度量（反事实多臂实验）
# ════════════════════════════════════════════════════════════════════════════


class TestRollbackIsolationGateIsMeasured:
    def test_declared_constraints_and_measured_checks_are_the_same_set(
        self, record: dict[str, Any]
    ) -> None:
        gate = record["rollback_isolation_gate"]
        declared = {c["constraint_id"] for c in gate["binding_constraints"]}
        assert declared == set(gate["checks"]), (
            f"只声明未度量 {sorted(declared - set(gate['checks']))}；"
            f"只度量未声明 {sorted(set(gate['checks']) - declared)}"
        )
        for constraint in gate["binding_constraints"]:
            assert constraint["statement"] and constraint["measured_by"]

    def test_verdict_follows_the_checks(self, record: dict[str, Any]) -> None:
        gate = record["rollback_isolation_gate"]
        expected = "open" if all(c["passed"] for c in gate["checks"].values()) else "blocked"
        assert gate["verdict"] == expected

    def test_gate_recomputes_from_the_recorded_inputs(
        self, record: dict[str, Any]
    ) -> None:
        """把记录里的 items / 替代面清册 / 形态归属原样喂回门的实现重算。

        这条是「门的某条约束被悄悄改成恒真」的唯一捕手：反事实多臂实验比的是
        **改前提后判定要变**，而恒真的判定在「前提被改好」那一臂上照样会变，
        所以还需要这条正向重算把它按住。
        """
        live = GEN.build_rollback_gate(
            record["items"],
            record["replacement_registry"],
            record["form_findings"],
            git_facts(),
        )
        recorded = record["rollback_isolation_gate"]
        assert live["verdict"] == recorded["verdict"]
        assert set(live["checks"]) == set(recorded["checks"])
        for key, value in live["checks"].items():
            assert value["passed"] == recorded["checks"][key]["passed"], (
                f"{key}: 现算 passed={value['passed']} 与记录 "
                f"{recorded['checks'][key]['passed']} 不符"
            )
            assert value["violation_count"] == recorded["checks"][key]["violation_count"], key

    def test_the_gate_is_currently_blocked_for_a_recorded_reason(
        self, record: dict[str, Any]
    ) -> None:
        """当前实测：替代面自身 `??` 未跟踪 ⇒ 门 blocked。结论与 BP 必须一致。"""
        gate = record["rollback_isolation_gate"]
        failing = [k for k, v in gate["checks"].items() if not v["passed"]]
        assert failing, (
            "门已经全过了 —— 若替代面真的都入库了，请同步解除 BP-66-2 并更新本判据"
        )
        for key in failing:
            assert gate["checks"][key]["violations"], f"{key}: 判失败却列不出违反项"
        bp_ids = {bp["id"] for bp in record["blocking_preconditions"]}
        assert "BP-66-2" in bp_ids

    @pytest.mark.parametrize(
        "arm",
        [
            "make_all_replacement_tracked",
            "make_all_pending_delete_tracked",
            "put_a_shared_path_into_whole_file_deletion",
            "misdeclare_a_site_level_deletion",
            "put_a_replacement_path_into_pending_delete",
        ],
    )
    def test_counterfactual_arms_change_the_gate_verdict(
        self, record: dict[str, Any], arm: str
    ) -> None:
        """🔴 教训 13：判据不能是重言式。逐臂在**内存里**改前提，门必须跟着变。

        这不是变异脚本的替代品 —— 它证明的是「门的每条约束都在度量某个可改变的事实」，
        而不是「某条恒真的事实被门重复陈述了一遍」。
        """
        items = copy.deepcopy(record["items"])
        rows = copy.deepcopy(record["replacement_registry"])
        findings = copy.deepcopy(record["form_findings"])
        git = git_facts()
        baseline = record["rollback_isolation_gate"]["checks"]

        if arm == "make_all_replacement_tracked":
            key = "replacement_surface_is_itself_recoverable"
            for row in rows:
                row["tracked_in_git"] = True
        elif arm == "make_all_pending_delete_tracked":
            key = "every_pending_delete_has_a_recoverable_rollback_target"
            for item in items:
                item["rollback_target"]["recoverable_from_git"] = True
        elif arm == "put_a_shared_path_into_whole_file_deletion":
            key = "shared_paths_are_not_whole_file_deletions"
            preserved = next(
                i
                for i in items
                if i["disposition"] == "preserved_until_replacement_lands"
            )
            victim = copy.deepcopy(preserved)
            victim["item_id"] += "@counterfactual"
            victim["disposition"] = "pending_delete"
            victim["deletion_unit"] = "whole_file"
            items.append(victim)
        elif arm == "misdeclare_a_site_level_deletion":
            key = "site_level_deletions_inside_shared_files_are_declared"
            target = next(
                i
                for i in items
                if i["disposition"] == "pending_delete"
                and i["deletion_unit"] in {"call_sites_within_file", "route_within_file"}
            )
            target["inside_preserved_file"] = not target["inside_preserved_file"]
        else:
            key = "no_path_is_both_replacement_and_pending_delete"
            victim = copy.deepcopy(items[0])
            victim["item_id"] += "@counterfactual"
            victim["disposition"] = "pending_delete"
            victim["deletion_unit"] = "whole_file"
            victim["path"] = rows[0]["path"]
            items.append(victim)

        mutated = GEN.build_rollback_gate(items, rows, findings, git)
        assert mutated["checks"][key]["passed"] != baseline[key]["passed"], (
            f"反事实臂 {arm} 改掉了前提，但约束 {key} 的判定没变 ⇒ 该判据度量的是别的东西"
        )


# ════════════════════════════════════════════════════════════════════════════
# §6 只生成计划：AST 断言生成器不碰生产代码
# ════════════════════════════════════════════════════════════════════════════


class TestGeneratorOnlyPlans:
    #: 裸方法名即可判定的危险动作（不与常见 str/list 方法同名）。
    FORBIDDEN_BARE_CALLS = frozenset(
        {
            "commit",
            "commit_bytes",
            "provision",
            "finalize_candidate",
            "publish",
            "execute",
            "unlink",
            "rmtree",
            "rmdir",
            "touch",
            "chmod",
            "mkdir",
        }
    )
    #: 必须看**点分路径**才能判定的（`str.replace` 合法、`os.replace` 不合法）。
    FORBIDDEN_DOTTED_CALLS = frozenset(
        {
            "os.remove",
            "os.unlink",
            "os.rename",
            "os.replace",
            "os.rmdir",
            "shutil.rmtree",
            "shutil.move",
            "shutil.copy",
        }
    )

    def test_generator_has_no_db_or_publication_surface(self) -> None:
        imports, calls, dotted, writes = _generator_ast_facts()
        forbidden_imports = {
            mod
            for mod in imports
            if any(
                token in mod
                for token in (
                    "sqlalchemy",
                    "asyncpg",
                    "app.db",
                    "app.core.database",
                    "repository",
                    "content_mutation",
                    "definitions_store",
                )
            )
        }
        assert not forbidden_imports, f"生成器 import 了 DB/写库层：{sorted(forbidden_imports)}"
        assert not (self.FORBIDDEN_BARE_CALLS & calls), (
            f"生成器调用了发布/删除链：{sorted(self.FORBIDDEN_BARE_CALLS & calls)} —— "
            "本任务只生成计划，不 feature-disable、不删除、不改调用点"
        )
        assert not (self.FORBIDDEN_DOTTED_CALLS & dotted), (
            f"生成器调用了文件系统改名/删除：{sorted(self.FORBIDDEN_DOTTED_CALLS & dotted)}"
        )
        assert writes == {"OUTPUT_PATH"}, (
            f"生成器的写盘接收者应恰为 OUTPUT_PATH，实测 {sorted(writes)}"
        )

    def test_the_ast_write_surface_detector_really_fires(self) -> None:
        """反向自检：把违规调用喂给同一个抽取器必须被抽到（否则上一条恒真）。

        同时证明**点分判据不误伤** `str.replace`：它必须出现在裸名里、
        但**不**出现在被禁的点分集合里。
        """
        imports, calls, dotted, writes = _ast_facts(
            "import sqlalchemy\n"
            "import os\n"
            "from app.db import session\n"
            "def f(p, TEMPLATE_ROOT, s):\n"
            "    p.write_text('x')\n"
            "    TEMPLATE_ROOT.write_text('y')\n"
            "    p.unlink()\n"
            "    os.replace('a', 'b')\n"
            "    return s.replace('\\\\', '/')\n"
        )
        assert "sqlalchemy" in imports and "app.db" in imports
        assert "unlink" in calls
        assert "os.replace" in dotted
        assert "replace" in calls, "裸名集合里应当同时看得到 str.replace"
        assert not (self.FORBIDDEN_BARE_CALLS & {"replace"}), (
            "`replace` 不得进裸名禁令集合 —— 否则路径分隔符规范化会被误判"
        )
        assert writes == {"p", "TEMPLATE_ROOT"}, writes

    def test_generator_declares_why_it_only_plans(self, record: dict[str, Any]) -> None:
        why = record["why_this_task_only_plans"]
        assert why["statement"] and why["machine_predicate"]
        assert "不 feature-disable" in why["task_body_quote"]

    def test_no_production_file_was_modified_after_the_plan_commit(
        self, record: dict[str, Any], items: list[dict[str, Any]]
    ) -> None:
        """清册里每个路径的 sha256 就是磁盘现值 —— 本任务没动它们任何一个字节。

        （已由 `test_every_item_path_exists_and_hash_matches_disk` 覆盖磁盘一致性，
        这条另外核对 plan commit 与当前 HEAD 一致，防「清册在别的 commit 上生成」。）
        """
        assert record["plan_commit"] == git_facts().head_commit
        assert all(item["rollback_target"]["plan_commit"] == record["plan_commit"] for item in items)


# ════════════════════════════════════════════════════════════════════════════
# §7 分类 / 处置 / 删除单位 / counters / BP / 入向义务
# ════════════════════════════════════════════════════════════════════════════


class TestCategoriesDispositionsAndUnits:
    def test_all_seven_categories_are_populated(
        self, record: dict[str, Any]
    ) -> None:
        counters = record["counters"]
        for category in GEN.CATEGORIES:
            key = f"items_category_{category}"
            assert counters[key] > 0, (
                f"{category} 一项都没清点到 —— Task 66 正文第 1 条逐字列了七类，"
                "任一类为 0 就说明该类的检测器空转"
            )

    def test_every_vocabulary_value_is_used_somewhere(
        self, record: dict[str, Any], items: list[dict[str, Any]]
    ) -> None:
        used_dispositions = {i["disposition"] for i in items} | {
            r["disposition"] for r in record["replacement_registry"]
        }
        assert used_dispositions == set(GEN.DISPOSITIONS), (
            f"未被使用的 disposition：{sorted(set(GEN.DISPOSITIONS) - used_dispositions)}"
        )
        used_units = {i["deletion_unit"] for i in items}
        assert used_units == set(GEN.DELETION_UNITS), (
            f"未被使用的 deletion_unit：{sorted(set(GEN.DELETION_UNITS) - used_units)}"
        )
        used_modes = {i["rollback_target"]["mode"] for i in items}
        assert used_modes == set(GEN.ROLLBACK_MODES), (
            f"未被使用的 rollback mode：{sorted(set(GEN.ROLLBACK_MODES) - used_modes)}"
        )

    def test_deletion_unit_is_derived_from_category_and_disposition(
        self, items: list[dict[str, Any]]
    ) -> None:
        for item in items:
            expected = (
                GEN._CATEGORY_DELETION_UNIT[item["category"]]
                if item["disposition"] == "pending_delete"
                else "none"
            )
            assert item["deletion_unit"] == expected, item["item_id"]

    def test_shared_router_is_preserved_but_its_paragraph_fallback_is_not(
        self, items: list[dict[str, Any]]
    ) -> None:
        """双重身份：共用端点必须留，同一文件里的段落降级必须删。"""
        router = "backend/app/routers/wp_onlyoffice_router.py"
        endpoints = [
            i for i in items if i["category"] == "legacy_endpoint" and i["path"] == router
        ]
        assert endpoints, "共用 router 的端点一条都没登记"
        assert all(
            i["disposition"] == "preserved_until_replacement_lands" for i in endpoints
        ), "共用 router 的端点被判成待删 ⇒ 未过 Task 70 的共用路径不得变更"
        fallback = [
            i
            for i in items
            if i["category"] == "paragraph_index_fallback" and i["path"] == router
        ]
        assert fallback, "共用 router 里的 paragraph_index 降级没登记"
        for item in fallback:
            assert item["disposition"] == "pending_delete"
            assert item["deletion_unit"] == "call_sites_within_file"
            assert item["inside_preserved_file"] is True, (
                "落在共用文件里的站点级删除必须显式登记，否则 Stage B 会误删整个文件"
            )

    def test_f2_dedicated_half_loop_endpoints_are_pending_delete(
        self, items: list[dict[str, Any]]
    ) -> None:
        """AC 12.7：F2 专用 to/from 端点是第二套半闭环，必须待删。"""
        rows = [
            i
            for i in items
            if i["category"] == "legacy_endpoint" and "_f2_stocktake_" in i["path"]
        ]
        assert rows, "F2 专用 to/from 端点一条都没登记"
        assert all(i["disposition"] == "pending_delete" for i in rows)
        directions = {i["facts"]["route"]["path"] for i in rows}
        assert any("to-oo" in p for p in directions) and any(
            "from-oo" in p for p in directions
        ), f"to/from 两个方向必须都在：{sorted(directions)}"

    def test_paragraph_index_is_really_refused_by_the_word_gate(
        self, items: list[dict[str, Any]]
    ) -> None:
        """载体/锚点恒拒判据必须**真喂进门看它抛**，不在源码里搜字符串。"""
        rows = [i for i in items if i["category"] == "paragraph_index_fallback"]
        gate = rows[0]["facts"]["word_anchor_gate"]
        assert "paragraph_index" in gate["blocked_anchors"]
        assert gate["paragraph_index_refusal"]["raised"] is True
        assert gate["control_anchor_accepted"] in gate["allowed_anchors"]
        live = GEN.word_anchor_gate()
        assert live["blocked_anchors"] == gate["blocked_anchors"]
        assert live["source_digest"] == gate["source_digest"]


class TestCountersRecomputeFromItems:
    def test_every_recomputable_counter_matches(
        self, record: dict[str, Any], items: list[dict[str, Any]]
    ) -> None:
        live = GEN.build_counters(
            items,
            record["replacement_registry"],
            record["form_findings"],
            manifest_facts(),
        )
        assert live == record["counters"], {
            k: (record["counters"].get(k), v)
            for k, v in live.items()
            if record["counters"].get(k) != v
        }

    def test_no_numeric_counter_escapes_the_guard(
        self, record: dict[str, Any]
    ) -> None:
        """覆盖面元判据：新增计数器而不补守卫必须打红。"""
        recorded = {k for k, v in record["counters"].items() if isinstance(v, int)}
        live = set(
            GEN.build_counters(
                record["items"],
                record["replacement_registry"],
                record["form_findings"],
                manifest_facts(),
            )
        )
        assert recorded == live, (
            f"记录里有 {sorted(recorded - live)} 未被 build_counters 现算 / "
            f"现算里有 {sorted(live - recorded)} 未落盘"
        )
        assert len(recorded) >= 20, f"计数器只有 {len(recorded)} 个 —— 口径过窄"


class TestBlockingPreconditions:
    def test_ids_are_task_scoped(self, record: dict[str, Any]) -> None:
        """🔴 全局 `BP-NN` 已被 Tasks 60/61/63/64 各自重复占用、同号不同义。"""
        bps = record["blocking_preconditions"]
        assert bps, "阻塞前置为空 ⇒ 门 blocked 却没有解除路径"
        for bp in bps:
            assert re.fullmatch(r"BP-66-\d+", bp["id"]), bp["id"]
        assert len({bp["id"] for bp in bps}) == len(bps)

    def test_each_precondition_is_complete_and_owned(
        self, record: dict[str, Any]
    ) -> None:
        known = GEN.tasks_md_task_ids()
        for bp in record["blocking_preconditions"]:
            assert bp["title"] and bp["statement"]
            assert bp["release_condition"]
            assert isinstance(bp["evidence"], list) and bp["evidence"]
            assert bp["owner_task"] in known, bp["id"]
            assert bp["owner_task"] != GEN.OWNER_TASK, (
                f"{bp['id']}: 阻塞前置的 owner 不能是本任务自己"
            )

    def test_bp_66_1_and_2_match_the_measured_facts(
        self, record: dict[str, Any]
    ) -> None:
        by_id = {bp["id"]: bp for bp in record["blocking_preconditions"]}
        counters = record["counters"]
        assert len(by_id["BP-66-1"]["blocked_paths"]) == (
            counters["replacement_surface_unreachable_from_production_host"]
        )
        assert len(by_id["BP-66-2"]["blocked_paths"]) == (
            counters["replacement_surface_untracked"]
        )
        assert len(by_id["BP-66-3"]["blocked_entry_ids"]) == (
            counters["manifest_entry_scenario_underivable"]
        )


class TestInboundObligations:
    def test_every_row_naming_task66_is_adjudicated_exactly_once(
        self, record: dict[str, Any]
    ) -> None:
        inbound = record["inbound_obligations_from_task12_matrix"]
        assert inbound["rows_naming_task66"] == len(inbound["rows"])
        assert inbound["rows"], "resolver 矩阵里没有一行点名 Task 66 ⇒ 入向义务分母恒空"
        seen: set[str] = set()
        for row in inbound["rows"]:
            assert row["verdict"] in GEN.INBOUND_VERDICTS, row
            assert row["reason"], row["writer_id"]
            assert row["writer_id"] not in seen, f"{row['writer_id']} 被裁决两次"
            seen.add(row["writer_id"])

    def test_inbound_rows_recompute_from_the_matrix(
        self, record: dict[str, Any]
    ) -> None:
        matrix = GEN.load_json(GEN.RESOLVER_MATRIX_PATH)
        live = {
            str(r["writer_id"])
            for r in matrix["rows"]
            if GEN.OWNER_TASK in re.split(r"[,\s]+", str(r.get("blocking_task") or ""))
        }
        recorded = {r["writer_id"] for r in record["inbound_obligations_from_task12_matrix"]["rows"]}
        assert live == recorded, (
            f"只在矩阵里 {sorted(live - recorded)[:5]}；只在清册里 {sorted(recorded - live)[:5]}"
        )

    def test_inbound_verdicts_are_derived_from_the_module_source(
        self, record: dict[str, Any]
    ) -> None:
        """裁决必须由「模块里有没有 legacy OO 端点字面量」这条事实派生。"""
        for row in record["inbound_obligations_from_task12_matrix"]["rows"]:
            path = ROOT / row["source_path"]
            code = path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""
            live = GEN._legacy_endpoint_hits(code)
            assert row["legacy_endpoint_literals"] == live, row["writer_id"]
            expected = (
                "inside_html_oo_writeback_surface"
                if live
                else "outside_html_oo_writeback_surface"
            )
            assert row["verdict"] == expected, row["writer_id"]

    def test_the_oo_room_resolver_rows_carry_the_owner_used_in_the_plan(
        self, record: dict[str, Any], items: list[dict[str, Any]]
    ) -> None:
        """endpoint 的 owner 必须来自矩阵的 `adjudication_owner_task` 现读。"""
        matrix = GEN.load_json(GEN.RESOLVER_MATRIX_PATH)
        by_qualname = {str(r["qualname"]): r for r in matrix["rows"]}
        matched = 0
        for item in items:
            if item["category"] != "legacy_endpoint":
                continue
            row = by_qualname.get(item["facts"]["route"]["function"])
            if row is None or not row.get("adjudication_owner_task"):
                continue
            assert item["owner"]["replacement_owner_task"] == str(
                row["adjudication_owner_task"]
            ), item["item_id"]
            matched += 1
        assert matched >= 5, f"只有 {matched} 个 endpoint 的 owner 来自矩阵 —— 交叉锁过弱"


# ════════════════════════════════════════════════════════════════════════════
# §8 幂等与 `--check` 严格性
# ════════════════════════════════════════════════════════════════════════════


class TestGeneratorIsIdempotentAndCheckIsStrict:
    def test_build_record_is_byte_stable(self) -> None:
        first = GEN.build_record()
        second = GEN.build_record()
        assert GEN._canonical_text(first) == GEN._canonical_text(second), (
            "两次现算不一致 —— 记录里有非确定性内容（集合迭代顺序 / 时间戳）"
        )

    def test_check_matches_the_file_on_disk(self) -> None:
        assert GEN.main(["--check"]) == 0

    def test_check_and_write_are_mutually_exclusive_and_required(self) -> None:
        with pytest.raises(SystemExit):
            GEN.main([])
        with pytest.raises(SystemExit):
            GEN.main(["--check", "--write"])

    def test_item_ids_are_unique(self, items: list[dict[str, Any]]) -> None:
        ids = [i["item_id"] for i in items]
        assert len(set(ids)) == len(ids)

    def test_record_declares_its_properties_and_requirements(
        self, record: dict[str, Any]
    ) -> None:
        assert record["properties_verified"] == [
            "Property 3",
            "Property 46",
            "Property 47",
            "Property 48",
            "Property 51",
        ]
        for ac in ("1.4", "1.5", "1.7", "11.1", "11.2", "11.5", "11.8", "11.10",
                   "12.7", "12.8", "12.9", "12.13", "12.14"):
            assert ac in record["requirements_covered"], ac
