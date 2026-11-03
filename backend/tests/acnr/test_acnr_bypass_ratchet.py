"""T24 守卫：ACNR 消费方绕过点棘轮与台账（需求 13 / design §14）。

扫描器 ``backend/scripts/check/acnr_bypass_scan.py`` 用 Python ast 现算 BP-1 / BP-2，与基线
``backend/data/acnr/bypass_baseline.json`` 逐条比对；台账 ``consumer_ledger.json`` 的文件与 Python 符号
由 AST 核对（前端 BP-3 / BP-4 与 TS 符号见 ``audit-platform/frontend/src/acnrBypassRatchet.spec.ts``）。
变异在仓库的临时副本或合成仓库里做，不改工作树。
"""
from __future__ import annotations

import ast
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
CHECK_DIR = REPO / "backend" / "scripts" / "check"
sys.path.insert(0, str(CHECK_DIR))

import acnr_bypass_scan as scan  # noqa: E402

BASELINE = json.loads((REPO / scan.BASELINE_REL).read_bytes().decode("utf-8"))
LEDGER = json.loads((REPO / scan.LEDGER_REL).read_bytes().decode("utf-8"))
_ENV = {**os.environ, "PYTHONIOENCODING": "utf-8"}


def _run_cli(script: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-S", str(script), *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=_ENV, cwd=str(REPO), stdin=subprocess.DEVNULL)


def test_real_repo_strict_green_and_counts_recomputed():
    result = scan.run(REPO)
    assert scan.violations(result) == 0, result
    # 现算冻结值：BP-1 8 处 / 7 个文件（design §14.1 同值），BP-2 窄定义下 1 个文件（linkage_graph_builder）
    assert result["bp1_statements"] == 8
    assert result["bp1_files"] == [
        "backend/app/routers/wp_structure.py",
        "backend/app/services/ai_chat/address_index_source.py",
        "backend/app/services/ai_chat/address_mention.py",
        "backend/app/services/ai_chat/mcp_tools.py",
        "backend/app/services/ai_chat/mention_service.py",
        "backend/app/services/event_handlers/_impl.py",
        "backend/app/services/wp_structure_bridge.py",
    ]
    assert result["bp2_files"] == ["backend/app/services/linkage_graph_builder.py"]
    assert len(result["ccr_readers"]) == 12
    # 基线前端段与 design §14.1 的文件集合（BP-3 现算 5 个文件：design 记 3 个，另有 commonApi / queryResultLinks）
    assert sorted({e["file"].rsplit("/", 1)[1] for e in BASELINE["bp4"]}) == [
        "WorkpaperHtmlTable.vue", "WorkpaperTraceView.vue", "useS34CrossRef.ts", "useS35CrossRef.ts",
        "useWorkpaperNavigation.ts"]
    assert len({e["file"] for e in BASELINE["bp3"]}) == 5


@pytest.mark.parametrize("script", ["acnr_bypass_scan.py", "check_acnr_consumer_coverage.py"])
def test_cli_strict_exit_zero_with_summary_without_site_packages(script):
    proc = _run_cli(CHECK_DIR / script, "--strict")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "BP-1 8 处 / 7 个文件" in proc.stdout
    assert "新增 0 条、失效 0 条、排除项问题 0 条、台账问题 0 条" in proc.stdout


def test_consumer_coverage_is_thin_shell_over_bypass_scan():
    tree = ast.parse((CHECK_DIR / "check_acnr_consumer_coverage.py").read_bytes().decode("utf-8"))
    imports = [(n.module, [a.name for a in n.names]) for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
    assert ("acnr_bypass_scan", ["main"]) in imports
    defs = [n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.ClassDef))]
    assert defs == [], f"薄壳不应再定义自己的扫描逻辑：{defs}"
    assert not (REPO / "backend/data/acnr/coverage_ledger.json").exists()


def test_ci_job_runs_consumer_coverage_strict_without_continue_on_error():
    import yaml

    jobs = yaml.safe_load((REPO / ".github/workflows/governance-checks.yml").read_bytes().decode("utf-8"))["jobs"]
    job = jobs["acnr-consumer-coverage"]
    assert not job.get("continue-on-error")
    assert not any(s.get("continue-on-error") for s in job["steps"])
    assert any(s.get("run") == "python backend/scripts/check/check_acnr_consumer_coverage.py --strict"
               for s in job["steps"])


def test_ledger_statuses_and_coverage():
    statuses = {e["status"] for e in LEDGER["entries"]}
    assert statuses == set(scan.LEDGER_STATUSES)
    consumers = " ".join(e["consumer"] for e in LEDGER["entries"])
    for area in ("公式选址", "公式保存校验", "高级查询", "导航", "追溯", "报表", "附注", "合并", "同步", "导入导出", "AI 对话提及"):
        assert area in consumers, area


# ─── 变异：仓库临时副本 ───────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def repo_copy(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("bypass_repo")
    for base in ("backend/app", "backend/scripts"):
        for p in (REPO / base).rglob("*.py"):
            if "__pycache__" in p.parts:
                continue
            dst = root / p.relative_to(REPO)
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(p.read_bytes())
    for rel in (scan.BASELINE_REL, scan.LEDGER_REL):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_bytes((REPO / rel).read_bytes())
    for e in LEDGER["entries"]:
        for f in e["files"]:
            if not f.endswith(".py"):
                (root / f).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(REPO / f, root / f)
    assert scan.violations(scan.run(root)) == 0
    return root


def _mutated(root: Path, rel: str, transform):
    path = root / rel
    original = path.read_bytes()
    path.write_bytes(transform(original.decode("utf-8-sig")).encode("utf-8"))
    try:
        return scan.run(root)
    finally:
        path.write_bytes(original)


def test_injected_v1_import_is_new_bypass(repo_copy):
    rel = "backend/app/services/formula_reverse_index.py"
    inject = "\n\ndef _probe():\n    from app.services.address_registry import address_registry\n    return address_registry\n"
    result = _mutated(repo_copy, rel, lambda t: t + inject)
    assert result["extra"] == [("BP-1", (rel, "_probe", "address_registry"), 1)]
    assert result["stale"] == []


def test_comment_or_docstring_mention_is_not_a_bypass(repo_copy):
    rel = "backend/app/services/formula_reverse_index.py"
    inject = ("\n# from app.services.address_registry import address_registry\n"
              "def _probe():\n    \"\"\"from app.services.address_registry import address_registry；"
              "读 address_registry_l3_dependencies.json\"\"\"\n    return None\n")
    result = _mutated(repo_copy, rel, lambda t: t + inject)
    assert scan.violations(result) == 0, result


def test_removed_baseline_call_is_stale_entry(repo_copy):
    rel = "backend/app/services/wp_structure_bridge.py"
    result = _mutated(repo_copy, rel, lambda t: t.replace(
        "from app.services.address_registry import build_uri, build_jump_route",
        "from app.services.address_registry import build_uri\n    build_jump_route = None"))
    assert result["stale"] == [("BP-1", (rel, "get_workpaper_addresses", "build_jump_route"), 1)]
    assert result["extra"] == []


def test_new_identity_json_loader_and_unadjudicated_ccr_reader(repo_copy):
    rel = "backend/app/services/wp_trace_service.py"
    inject = "\n\n_L3 = 'data/address_registry_l3_dependencies.json'\n"
    result = _mutated(repo_copy, rel, lambda t: t + inject)
    assert result["extra"] == [("BP-2", (rel, "<module>", "identity_json", "address_registry_l3_dependencies.json"), 1)]
    new_reader = "backend/app/services/_probe_ccr.py"
    (repo_copy / new_reader).write_text("P = 'data/cross_wp_references.json'\n", encoding="utf-8")
    try:
        problems = scan.run(repo_copy)["ledger_problems"]
    finally:
        (repo_copy / new_reader).unlink()
    assert problems == [f"未裁决的 CCR 读取方（须进基线 ccr_identity 或台账）：{new_reader}"]


def test_ledger_nonexistent_symbol_file_and_migrated_in_baseline(repo_copy):
    ledger_path = repo_copy / scan.LEDGER_REL
    original = ledger_path.read_bytes()
    data = json.loads(original.decode("utf-8"))
    by_id = {e["id"]: e for e in data["entries"]}
    by_id["ai-chat-mention"]["symbols"].append(
        {"file": "backend/app/services/ai_chat/mcp_tools.py", "name": "_no_such_function"})
    by_id["bulk-import-export"]["files"].append("backend/app/services/bulk_tab/_missing.py")
    by_id["sync-invalidation"]["status"] = "migrated"
    ledger_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    try:
        problems = scan.run(repo_copy)["ledger_problems"]
    finally:
        ledger_path.write_bytes(original)
    assert "ai-chat-mention：backend/app/services/ai_chat/mcp_tools.py 里没有定义 _no_such_function" in problems
    assert "bulk-import-export：文件不存在 backend/app/services/bulk_tab/_missing.py" in problems
    assert "sync-invalidation：标为 migrated，但 backend/app/services/wp_structure_bridge.py 仍在绕过基线里" in problems
    assert "基线文件未被任何非 migrated 台账条目登记：backend/app/routers/wp_structure.py" in problems


def test_missing_baseline_is_exit_2(repo_copy, capsys):
    path = repo_copy / scan.BASELINE_REL
    original = path.read_bytes()
    path.unlink()
    try:
        code = scan.main(["--strict", "--repo-root", str(repo_copy)])
    finally:
        path.write_bytes(original)
    assert code == 2
    assert "绕过基线缺失或无法解析" in capsys.readouterr().out


def test_strict_exit_1_names_new_bypass(repo_copy, capsys):
    rel = "backend/app/services/formula_reverse_index.py"
    path = repo_copy / rel
    original = path.read_bytes()
    path.write_bytes(original + b"\nfrom app.services.address_registry import parse_uri\n")
    try:
        assert scan.main(["--repo-root", str(repo_copy)]) == 0
        assert scan.main(["--strict", "--repo-root", str(repo_copy)]) == 1
    finally:
        path.write_bytes(original)
    out = capsys.readouterr().out
    assert f"[新增绕过] BP-1 {rel}（<module>）：parse_uri 超出基线 1 处" in out
    assert "strict 模式退出 1" in out


# ─── 扫描口径：合成仓库 ───────────────────────────────────────────────────────


def _mini_repo(tmp_path: Path, files: dict[str, str]) -> Path:
    for rel, text in files.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(text, encoding="utf-8")
    return tmp_path


def test_scope_rules_on_synthetic_repo(tmp_path):
    root = _mini_repo(tmp_path, {
        "backend/app/services/address_registry.py": "from app.services.address_registry import x\n",
        "backend/app/services/acnr/events.py": "from app.services.address_registry import address_registry\n",
        "backend/app/router_registry/system.py": "from app.routers.address_registry import router\n",
        "backend/app/services/formula_engine.py": "from app.services.address_registry import extract_custom_cells\n",
        "backend/app/services/rel.py": "from .address_registry import build_uri\nfrom . import address_registry\n",
        "backend/app/services/dyn.py": "import importlib\nm = importlib.import_module('app.services.address_registry')\n",
        "backend/app/services/note.py": "TEXT = '说明：见 cross_wp_references.json 的字段'\n",
    })
    bp1 = scan.scan_backend(root)["bp1"]
    assert sorted(bp1) == [
        ("backend/app/services/dyn.py", "<module>", "app.services.address_registry"),
        ("backend/app/services/rel.py", "<module>", "address_registry"),
        ("backend/app/services/rel.py", "<module>", "build_uri"),
    ]
    assert scan.scan_backend(root)["ccr_readers"] == {}


def test_exclusion_must_still_hit_and_import_v2_canonical(tmp_path):
    root = _mini_repo(tmp_path, {
        "backend/app/routers/address_registry_v2.py": "P = 'data/address_registry_l2_semantic.json'\n",
        "backend/scripts/acnr/reconcile_v2_canonical.py": "from app.services.acnr import v2_canonical\n",
    })
    problems = scan.scan_backend(root)["exclusion_problems"]
    assert "backend/app/routers/address_registry_v2.py：排除理由是身份经 v2_canonical，但该文件不导入 v2_canonical" in problems
    assert "backend/scripts/acnr/reconcile_v2_canonical.py：排除项已不加载 V2 身份 JSON / CCR（失效排除，应删去）" in problems
    assert "backend/scripts/acnr/gen_editor_save_inputs.py：排除项已不加载 V2 身份 JSON / CCR（失效排除，应删去）" in problems
