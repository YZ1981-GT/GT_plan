# -*- coding: utf-8 -*-
"""收口判据：范围边界 + 测试纪律（Task 22）。

spec: excel-structural-row-insertion-and-shift-aware-verification
Requirements: 5.5, 9.4, 11.6, 11.7, 12.1 ~ 12.6 · Properties: **P26** / **P31**

═══ 归因型判据，不是全局等值型 ═══════════════════════════════════════════════

🔴 本仓库当前有**多条泳道并行**（git 索引里同时存在 B 与 D 两条泳道的产物）。
所以「结构缺席」类判据必须按**归因**判 —— 变动是否落在**本 spec 的文件面**内 ——
而不能用全局等值型（「一个新迁移都没有」）：后者会被 D 泳道的 `V154` 打成假红，
而那与本 spec 毫无关系。

判据形态统一为：**在本 spec 声明的五个交付文件里**，某类东西必须缺席。
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Final

import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:  # pragma: no cover - import 自举
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

_SYNC: Final[Path] = _BACKEND / "app" / "services" / "workpaper_sync"

#: 本 spec 的**生产**交付文件面（分工书 §2 的 B 行 + 新增的 N1）。
DELIVERED_PRODUCTION: Final[tuple[Path, ...]] = (
    _SYNC / "excel_row_shift.py",
    _SYNC / "excel_materialize.py",
    _SYNC / "excel_extract.py",
    _SYNC / "contracts.py",
    _SYNC / "adapters" / "excel.py",
)

#: 本 spec 的测试与脚本产物。
DELIVERED_TESTS: Final[tuple[Path, ...]] = (
    _BACKEND / "tests" / "workpaper_sync" / "test_excel_row_shift.py",
    _BACKEND / "tests" / "workpaper_sync" / "test_excel_shift_aware_verification.py",
    _BACKEND / "tests" / "workpaper_sync" / "test_excel_row_insertion_wiring.py",
    _BACKEND / "tests" / "workpaper_sync" / "test_excel_row_insertion_readiness.py",
    _BACKEND / "tests" / "workpaper_sync" / "test_excel_row_insertion_openability.py",
    _BACKEND / "tests" / "workpaper_sync" / "test_excel_row_insertion_scope_closure.py",
)

DELIVERED_SCRIPTS: Final[tuple[Path, ...]] = (
    _BACKEND / "scripts" / "check" / "check_excel_row_insertion_readiness.py",
)


class TestAllDeliverablesExist:
    """先证明文件面本身在盘上 —— 否则下面的缺席判据全部空转。"""

    @pytest.mark.parametrize(
        "path", DELIVERED_PRODUCTION + DELIVERED_TESTS + DELIVERED_SCRIPTS,
        ids=lambda p: p.name,
    )
    def test_deliverable_is_on_disk(self, path: Path) -> None:
        assert path.is_file(), f"交付物缺失: {path}"


class TestStructuralAbsence:
    """**Feature: excel-structural-row-insertion-and-shift-aware-verification, Property 26: 范围边界的结构缺席判据**

    **Validates: Requirements 12.1, 12.2, 12.3, 12.4, 12.5, 12.6**
    """

    def test_no_structural_row_deletion_implementation(self) -> None:
        """AC 12.1：**不实现**结构性删行（已由下游 spec 承接）。

        判据落在 AST 的函数名与公开导出上，不是「源码里没出现 delete 字样」——
        后者会被注释里的「不做删行」这句话本身打红。
        """
        module = ast.parse((_SYNC / "excel_row_shift.py").read_text(encoding="utf-8"))
        names = {
            node.name
            for node in ast.walk(module)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        }
        offenders = sorted(
            n for n in names if re.search(r"delete_row|remove_row|drop_row|delete_sheet_rows", n)
        )
        assert offenders == [], f"出现结构性删行实现: {offenders}（AC 12.1 明列排除）"

    def test_no_external_relationship_permission_widening(self) -> None:
        """AC 12.2：不放宽外部关系许可。

        🔴 判据**不能**用「源码里不出现 `externalLink`」这种子串型：生产侧本来就有一个
        只读的部件分类表（`"external_link": re.compile(r"^xl/externalLinks/")`），
        它是**把外部链接部件识别出来**用的 —— 与「放宽许可」正好相反。
        本文件首版这么写，当场被那个常量打红。

        改判**放宽动作**本身：允许类开关、跳过检查、以及把外部关系写进产物的调用。
        """
        widening = (
            "allow_external_links",
            "ALLOW_EXTERNAL",
            "skip_relationship_check",
            "external_links_allowed",
            "permit_external",
        )
        for path in DELIVERED_PRODUCTION:
            source = path.read_text(encoding="utf-8")
            for forbidden in widening:
                assert forbidden not in source, (
                    f"{path.name}: 出现外部关系放宽面 {forbidden!r}（AC 12.2）"
                )
            # 只读分类可以有；**写入**外部关系部件不行
            assert not re.search(r"""entries\[["']xl/externalLinks""", source), (
                f"{path.name}: 往 xl/externalLinks/ 写入部件"
            )

    def test_no_h1_contract_change_attributable_to_this_spec(self) -> None:
        """AC 12.3：**本 spec** 不改 H1 契约。

        🔴 **按归因判，不用全局等值型** —— 与
        `test_no_new_migration_attributable_to_this_spec` 同一形态，理由也同一条：
        仓库是多泳道并行的，别的泳道**合法地**改契约时，全局判据（「契约目录 git 干净」）
        必假红。2026-09-05 实测发生过：A 泳道为 BP-21（受管区剔除排版占位行）与
        Open Gate 5（`footer_anchor.carries_total_formula`）改了 H1 / D2 两份契约，
        并走了完整发布链，本条却因全局 git 状态打红。

        本 spec 的归因判据：交付文件面里**没有任何一处**写契约 JSON ——
        既不引用契约目录，也不出现契约文件名，更没有写入调用。
        「谁改的」由此可判，而不是「有没有人改」。

        ⚠ 「契约被原地改写而没走发布链」这件事**仍然有人管**，见
        :meth:`test_published_contracts_are_carried_by_the_definition_store`
        —— 那是一条跨泳道不变量，与本条的 spec 范围判据是两件事，不得合并。
        """
        # 🔴 判据 = **双向锁**：磁盘契约必须逐字节等于其 provider 现算的 payload。
        #
        #    为什么这条能回答「谁改的」：手改契约 JSON 必然让 disk ≠ source（provider 没跟着
        #    改）⇒ 打红；而 provider 驱动的合法变更（改 provider + 跑生成器 + 走发布链）
        #    两侧同时变 ⇒ 通过。于是它对**任何**泳道的手改都敏感，却不会因别人合法改契约
        #    而假红 —— 这正是全局 git 判据做不到的。
        #
        #    试过并否掉的两种更粗的判据：
        #    * 「交付面不得引用契约目录」—— `contracts.py` 的 `contract_path_for()` /
        #      `load_contract()` 正当地**读**它，实测打红；
        #    * 「交付面不得有落盘动作」—— `excel_materialize.py` 的 `.write_bytes()` 是
        #      materialize 产物落盘，正当，实测打红。
        import importlib

        from app.services.workpaper_sync.adapters.registry import (
            DELIVERED_PER_ENTRY_CONTRACTS,
        )

        checked: list[str] = []
        for row in DELIVERED_PER_ENTRY_CONTRACTS:
            provider = importlib.import_module(str(row["provider_module"]))
            asserter = getattr(provider, "assert_contract_file_matches_source", None)
            assert callable(asserter), (
                f"{row['provider_module']}: 缺 assert_contract_file_matches_source ⇒ "
                "该 entry 的契约没有双向锁，手改无人能发现"
            )
            asserter()  # 不一致时自己抛，异常信息里带两侧 digest 与重生成命令
            checked.append(str(row["contract_id"]))
        # 分母非空：登记表为空时「全部一致」是空转
        assert len(checked) >= 4, checked

    def test_published_contracts_are_carried_by_the_definition_store(self) -> None:
        """AC 5.5：契约 payload 变更**必须**已走发布链，不得原地改写就算完。

        ═══ 这条替代了原来的全局 git 等值判据 ═══════════════════════════════════

        原判据是「契约目录 git 干净」。它有两个方向的毛病：
        * **假红**：别的泳道合法改契约并走完发布链时照样打红（实测发生过）；
        * **假绿**：契约**已提交**之后 git 就干净了，而「有没有走发布链」根本没被检查 ——
          原判据其实从未验证过 AC 5.5 说的那件事。

        现判据是语义的、且离线可算：磁盘上每份契约的 **canonical digest** 必须被
        `backend/definition_store/` 里的件承载（同名 blob，或被某个 bundle 引用）。
        走了发布链就必然有；只改 JSON 不发布就必然没有。与 git 状态无关，因此
        commit 前后都成立。
        """
        store = _BACKEND / "definition_store"
        assert store.exists(), f"definition store 不存在: {store}"
        carried: set[str] = set()
        for path in store.rglob("*"):
            if not path.is_file():
                continue
            carried.add(path.stem)
            if path.suffix == ".json":
                try:
                    carried.update(
                        re.findall(r"[0-9a-f]{64}", path.read_text(encoding="utf-8"))
                    )
                except (OSError, UnicodeDecodeError):
                    continue

        # 🔴 覆盖面取**已交付登记表**而不是目录 glob：目录里有 `_example.candidate.json`
        #    （故意的 generator 候选样例，`review_status=candidate`，`parse_contract` 明令
        #    拒绝注册），它本就不该有发布链。用登记表做真源，覆盖面随登记自动增长。
        from app.services.workpaper_sync.adapters.registry import (
            DELIVERED_PER_ENTRY_CONTRACTS,
        )
        from app.services.workpaper_sync.contracts import load_contract

        checked: list[str] = []
        orphans: list[str] = []
        for row in DELIVERED_PER_ENTRY_CONTRACTS:
            contract_id = str(row["contract_id"])
            digest = load_contract(contract_id).canonical_sha256
            checked.append(contract_id)
            if digest not in carried:
                orphans.append(f"{contract_id} digest={digest[:12]}…")
        # 分母非空：一份都没查到时「零孤儿」是空转
        assert len(checked) >= 4, checked
        assert orphans == [], (
            "以下契约的 canonical digest 不被 definition store 承载 ⇒ 它们被**原地改写**"
            f"而没走发布链（AC 5.5）：{orphans}。"
            "修法：跑 `backend/scripts/fix/fix_task76_provision_projection_definitions.py "
            "--apply` 重发 template → instrumentation → contract → bundle，"
            "随后按需重发 representation。"
            f"（已核查 {len(checked)} 份契约）"
        )

    def test_no_cross_sheet_propagation_rewrite(self) -> None:
        """AC 12.4：不做跨 sheet 联动改写（下游 spec 的 `propagate_sheets` 是它的活）。"""
        for path in DELIVERED_PRODUCTION:
            source = path.read_text(encoding="utf-8")
            module = ast.parse(source)
            names = {
                node.name
                for node in ast.walk(module)
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            }
            offenders = sorted(n for n in names if "propagate_sheet" in n or "cross_sheet" in n)
            assert offenders == [], f"{path.name}: 出现跨 sheet 联动改写 {offenders}"

    def test_openpyxl_roundtrip_reachability_criterion_unchanged(self) -> None:
        """AC 12.5：`openpyxl_roundtrip` 的可达性判据不变。

        本 spec 只**新增**了「与插行叠加时 fail closed」，不放宽原有策略门。
        """
        source = (_SYNC / "excel_materialize.py").read_text(encoding="utf-8")
        # 原有的 fail-closed 入口必须还在
        assert "if not decision.openpyxl_allowed:" in source
        assert "WriteStrategyForbiddenError" in source
        # 新增的叠加禁令也必须在（否则 openpyxl + 插行会互相掩盖）
        assert "excel_row_shift_strategy_conflict" in source

    def test_no_new_migration_attributable_to_this_spec(self) -> None:
        """AC 12.6：本 spec 不新增 `backend/migrations/V*.sql`。

        🔴 **按归因判，不用全局等值型。** 仓库里现在有 D 泳道的 `V154`（模板覆盖层），
        与本 spec 无关。全局判据（「一个新迁移都没有」）会被它打成假红。

        本 spec 的归因判据：交付文件面里**没有任何一处引用迁移文件**，且本 spec 声明的
        文件清单里不含 `migrations/`。
        """
        for path in DELIVERED_PRODUCTION + DELIVERED_SCRIPTS:
            source = path.read_text(encoding="utf-8")
            assert "migrations/" not in source, f"{path.name}: 引用了迁移目录"
            assert not re.search(r"\bV\d{3}__", source), f"{path.name}: 引用了迁移文件名"

    def test_definition_store_blobs_are_append_only(self) -> None:
        """AC 5.5 / 9.4：definition store 的 blob 是**内容寻址**的，只增不改。

        🔴 判据换成了「已入库的 blob 未被原地改写」，而不是原来的「契约目录 git 干净」：
        后者既假红（别的泳道合法改契约）又假绿（提交之后就永远干净）。
        「契约变更是否走了发布链」由
        :meth:`test_published_contracts_are_carried_by_the_definition_store` 判定。

        内容寻址的含义：文件名就是内容的 sha256 ⇒ 任何原地改写都会让「文件名 ≠ 内容
        digest」。这条离线可算、与 git 状态无关，且能抓到 git 抓不到的形态
        （比如某个 blob 被改了但恰好没被 git 跟踪）。
        """
        store = _BACKEND / "definition_store"
        if not store.exists():
            pytest.skip("definition store 尚未建立")
        checked = 0
        broken: list[str] = []
        for path in sorted(store.rglob("*")):
            if not path.is_file() or len(path.stem) != 64:
                continue
            checked += 1
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
            if actual != path.stem:
                broken.append(f"{path.relative_to(store)} 实算={actual[:12]}…")
        # 分母非空断言：store 空时「零破损」是空转
        assert checked >= 8, f"只查到 {checked} 个内容寻址 blob，分母太小"
        assert broken == [], f"definition store 里有被原地改写的 blob: {broken}"

    def test_template_library_git_state_is_untouched(self) -> None:
        """模板库是唯一权威源 —— 全仓**任何**泳道都不得改它。

        这一条**刻意保留全局等值型**：与契约不同，`backend/wp_templates/` 的
        「运行时只读」是平台级不变量（Requirement 9.9），没有任何泳道有权改它 ⇒
        全局判据正是想要的语义，不存在合法的其它泳道改动。
        """
        proc = subprocess.run(  # noqa: S603
            ["git", "status", "--porcelain", "--", str(_BACKEND / "wp_templates")],
            cwd=_REPO, capture_output=True, text=True, timeout=120,
        )
        dirty = [line for line in (proc.stdout or "").splitlines() if line.strip()]
        assert dirty == [], f"模板库被改动: {dirty}"

class TestTestingDiscipline:
    """**Feature: excel-structural-row-insertion-and-shift-aware-verification, Property 31: 测试纪律判据**

    **Validates: Requirements 11.6, 11.7**

    🔴 这两条 AC 在本 spec 的 tasks.md 里此前**无任何任务引用**（悬空 AC）。
    """

    def test_every_hypothesis_settings_has_at_least_100_examples(self) -> None:
        """AC 11.6：每条 `@settings` 的 `max_examples >= 100`。

        判据落在 **AST 取值**而非字符串存在：改成 50 必须打红。
        """
        checked = 0
        for path in DELIVERED_TESTS:
            module = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(module):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                name = (
                    func.attr if isinstance(func, ast.Attribute)
                    else func.id if isinstance(func, ast.Name) else ""
                )
                if name != "settings":
                    continue
                for kw in node.keywords:
                    if kw.arg != "max_examples":
                        continue
                    assert isinstance(kw.value, ast.Constant), (
                        f"{path.name}: max_examples 不是字面量 ⇒ 无从静态判据"
                    )
                    checked += 1
                    assert kw.value.value >= 100, (
                        f"{path.name}: max_examples={kw.value.value} < 100（AC 11.6）"
                    )
        # 本 spec 的属性测试以「实测形态驱动」为主，未必用 hypothesis。
        # 判据必须能区分「都 >= 100」与「一条都没有」—— 后者是空转。
        if checked == 0:
            pytest.skip(
                "本 spec 的属性测试不使用 hypothesis @settings（判据形态是实测 fixture + "
                "参数化）⇒ AC 11.6 在本 spec 上无载体。这条 skip 是**诚实标注**而不是通过："
                "一旦有人引入 hypothesis，本条会自动开始把关"
            )

    def test_radiation_set_is_computed_from_real_references_not_hardcoded(self) -> None:
        """AC 11.7：辐射面由**对本 spec 交付物的实际引用关系**现算得出。

        判据形态：现算「哪些测试文件 import 了本 spec 的交付模块」，与 CI/文档里声明的
        清单逐项相等。不是写死目录、不是全量 `backend/tests`。
        """
        modules = {p.stem for p in DELIVERED_PRODUCTION}
        assert modules, "交付模块集为空 ⇒ 判据空转"

        test_root = _BACKEND / "tests" / "workpaper_sync"
        live: set[str] = set()
        for path in sorted(test_root.glob("test_*.py")):
            source = path.read_text(encoding="utf-8", errors="replace")
            if any(re.search(rf"\b{re.escape(m)}\b", source) for m in modules):
                live.add(path.name)

        # 本 spec 自己的六份测试必须在辐射面里
        for path in DELIVERED_TESTS:
            assert path.name in live, (
                f"{path.name} 没被现算辐射面收进来 ⇒ 辐射面算法漏了它"
            )
        # 辐射面必须**小于**全量（否则「现算」等于「跑全部」，AC 11.7 的要求落空）
        every = {p.name for p in test_root.glob("test_*.py")}
        assert live < every, (
            f"现算辐射面 == 全量（{len(live)} 个）⇒ 它不是按引用关系算的"
        )
        assert len(live) >= len(DELIVERED_TESTS), sorted(live)

    def test_tests_resolve_paths_from_the_repository_root(self) -> None:
        """AC 11.7：测试从**仓库根**跑 pytest。

        🔴 判据不是「必须有 `sys.path.insert`」—— 那是**一种**自举形态而不是唯一形态：
        本目录有 `conftest.py`，pytest 的 rootdir 机制已经把包路径准备好了，所以 T1
        只用 `Path(__file__).resolve().parents[3]` 推出仓库根就够（本文件首版按
        `sys.path.insert` 判，把 T1 打成假红）。

        真正要守的性质是：**路径由 `__file__` 现推，不依赖进程当前工作目录**。
        依赖 cwd 的写法（取当前目录、或把相对路径字面量喂给文件 API）换个目录跑就碎。
        🔴 判据落在 **AST** 而不是子串：本条自己的 docstring 里就写着 `os.getcwd()`
        这几个字（用来说明什么形态不行），子串型判据会把**本文件**打红 —— 实测发生过。
        注释与文档字符串不是代码，判据必须能区分。
        """
        for path in DELIVERED_TESTS:
            source = path.read_text(encoding="utf-8")
            assert "Path(__file__).resolve()" in source, (
                f"{path.name}: 路径不是从 __file__ 现推 ⇒ 换工作目录即碎"
            )
            module = ast.parse(source)
            for node in ast.walk(module):
                # `os.getcwd()` / `os.curdir` 的**调用**（不是文本提及）
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                    dotted = f"{getattr(node.func.value, 'id', '')}.{node.func.attr}"
                    assert dotted != "os.getcwd", (
                        f"{path.name}: 真的调用了 os.getcwd() ⇒ 依赖当前工作目录"
                    )
                # 相对路径字面量喂给文件 API
                if isinstance(node, ast.Call):
                    name = (
                        node.func.attr if isinstance(node.func, ast.Attribute)
                        else getattr(node.func, "id", "")
                    )
                    if name not in ("open", "read_text", "read_bytes", "write_text"):
                        continue
                    for arg in node.args:
                        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                            assert not arg.value.startswith("backend/"), (
                                f"{path.name}: 相对路径字面量 {arg.value!r} ⇒ 依赖 cwd"
                            )


class TestNoDiagnosticLeftovers:
    """清理判据：本 spec 不得把临时诊断产物留在仓库里。"""

    def test_no_tmp_or_wip_artifacts_attributable_to_this_spec(self) -> None:
        """🔴 按**文件名归属**判，并发泳道在用的不动。

        本 spec 的临时产物统一用 `tmp_b_` 前缀（B 泳道）。判据只查这个前缀 ——
        查 `tmp_*` 全量会把别的泳道正在用的诊断脚本打成红。
        """
        leftovers = sorted(p.name for p in _REPO.glob("tmp_b_*"))
        assert leftovers == [], (
            f"B 泳道的临时诊断产物未清理: {leftovers} —— "
            "spec 全绿 ≠ 产物已入库，也 ≠ 工作区已清理"
        )

    def test_the_census_output_is_either_absent_or_valid_json(self) -> None:
        """清册落盘产物若存在，必须是能直接 `json.loads` 的 UTF-8。"""
        import json

        census = _BACKEND / "data" / "workpaper_excel_row_insertion_readiness.json"
        if not census.is_file():
            pytest.skip("清册未落盘（`--json` 是可选动作，不落盘也合法）")
        raw = census.read_bytes()
        assert not raw.startswith(b"\xef\xbb\xbf"), "清册带 BOM"
        payload = json.loads(raw.decode("utf-8"))
        assert payload["entries"], "清册是空的"
