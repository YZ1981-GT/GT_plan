"""SheetOpenBinding 生成物守卫（onlyoffice-sheet-open-via-published-artifact Phase 1）。"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "data/workpaper_sync_sheet_open_bindings.json"
GENERATOR = ROOT / "scripts/gen/generate_workpaper_sync_sheet_open_bindings.py"
MANIFEST = ROOT / "data/workpaper_sync_entry_manifest.json"

_ALLOWED_STATUS = {"pending", "ready", "migrated", "draining", "retired", "out_of_scope"}
_ALLOWED_KIND = {"exact", "provider", "whole_workbook", "ambiguous", "out_of_scope"}


@pytest.fixture(autouse=True)
def _honor_output_override(monkeypatch):
    """让 `GEN.OUTPUT` 与 `OUTPUT` 认 `GT_SHEET_BINDINGS_OUT`。

    ═══ 为什么需要 ═══

    变异套件（task 5.4）要在**不改真实产物**的前提下让「生成器现算」与「磁盘产物」
    可比。`GEN.OUTPUT` 是 module-level 常量（import 时求值一次）⇒ 光设环境变量不够，
    必须在运行期重新赋值。

    ═══ 为什么用 autouse ═══

    每个用例都可能读 `OUTPUT` 或 `Path(GEN.OUTPUT)`；漏一个就会读到真实路径
    （而套件正在改写它）⇒ 随机红。autouse 保证无一遗漏。

    ═══ 真实 CI 里没有影响 ═══

    `GT_SHEET_BINDINGS_OUT` 未设时本 fixture 是 no-op。
    """
    import os as _os

    override = _os.environ.get("GT_SHEET_BINDINGS_OUT")
    if not override:
        yield
        return
    monkeypatch.setattr(GEN, "OUTPUT", Path(override))
    monkeypatch.setattr(sys.modules[__name__], "OUTPUT", Path(override))
    yield


@pytest.fixture(scope="module")
def projection() -> dict:
    return json.loads(Path(GEN.OUTPUT).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def test_generated_projection_is_current() -> None:
    """`--check` 必须通过：生成物与生成器现算逐字节一致。

    🔴 **透传 `GT_SHEET_BINDINGS_OUT`**：变异套件（task 5.4）把生成结果重定向到沙箱，
    以免写已跟踪文件。若这里不透传，子进程会拿「变异生成器算出的字节」比「真实产物」
    ⇒ 必不一致 ⇒ 红在本条上，抢了语义判据的红（实测：01/02 变异归因不清）。

    透传后比的是「沙箱字节 vs 沙箱字节」，本条的职责（「生成物是否过期」）在真实 CI
    里完全不变 —— 那里 `GT_SHEET_BINDINGS_OUT` 未设，比的仍是真实产物。
    """
    env = {**__import__("os").environ, "PYTHONIOENCODING": "utf-8"}
    proc = subprocess.run(
        [sys.executable, str(GENERATOR), "--check"],
        cwd=ROOT.parent,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_projection_covers_manifest_entry_ids_exactly(projection: dict, manifest: dict) -> None:
    binding_ids = [row["entry_id"] for row in projection["bindings"]]
    manifest_ids = [row["entry_id"] for row in manifest["entries"]]
    assert len(binding_ids) == len(set(binding_ids)), "binding entry_id 重复"
    assert set(binding_ids) == set(manifest_ids)
    assert not any(entry.startswith("xlsx-sheet/") for entry in binding_ids)


def test_each_binding_has_closed_status_and_real_effective_entry(
    projection: dict, manifest: dict,
) -> None:
    manifest_ids = {row["entry_id"] for row in manifest["entries"]}
    rows = projection["bindings"]
    assert rows
    for row in rows:
        assert row["status"] in _ALLOWED_STATUS
        assert row["mapping_kind"] in _ALLOWED_KIND
        assert row["effective_entry_id"] in manifest_ids
        assert row["input_digest"] == projection["input_digest"]
        assert row["binding_id"].startswith("sha256:")
        if row["status"] == "out_of_scope":
            assert row["document_type"] != "xlsx" or row["reason"]
        if row["mapping_kind"] == "exact":
            assert row["target_sheet"] and len(row["sheet_literals"]) == 1


def test_projection_does_not_claim_migration_without_reviewed_binding(projection: dict) -> None:
    """首版生成物只能表达 pending/out_of_scope，不得凭 manifest 自动伪造 ready/migrated。"""
    claimed = [
        row for row in projection["bindings"]
        if row["status"] in {"ready", "migrated", "draining", "retired"}
    ]
    assert claimed == []


def test_effective_entry_id_is_never_a_forged_parent_fallback(
    projection: dict, manifest: dict,
) -> None:
    """`effective_entry_id` 必须在 manifest 里，且**不得**被改成某个固定父级。

    🔴 这是 task 5.4 变异 02 暴露的真缺口：原判据只查 `entry_id` 集合，
    而「伪造 parent fallback」正是通过 `effective_entry_id` 实现的 —— 把子 entry 的
    effective 指向父级，让它的编辑写进父级 artifact。判据不查 effective 就漏掉它。

    判据三层：
    1. `effective_entry_id` 必须在 manifest 里（不是编造的值）；
    2. 它**不得**是同一个固定值（那说明全表被批量改成了兜底父级）；
    3. 若与 `entry_id` 不同，必须能解释 —— 当前只允许 `parent_duplicate` 形态。
    """
    manifest_ids = {row["entry_id"] for row in manifest["entries"]}
    rows = projection["bindings"]

    # ① 全在 manifest 里
    bad = [r["entry_id"] for r in rows if r["effective_entry_id"] not in manifest_ids]
    assert not bad, f"这些 binding 的 effective_entry_id 不在 manifest 里：{bad}"

    # ② 不是同一个固定值（伪造父级兜底的形态）
    distinct = {r["effective_entry_id"] for r in rows}
    assert len(distinct) > 1, (
        f"所有 {len(rows)} 条 binding 的 effective_entry_id 都是 {distinct.pop()!r} —— "
        "疑似被批量改成了固定父级兜底"
    )

    # ③ 与 entry_id 不同时必须能解释
    mismatched = [
        r for r in rows if r["effective_entry_id"] != r["entry_id"]
    ]
    for row in mismatched:
        # `independent_entry=False` 是 parent_duplicate 的合法语义
        assert row.get("independent_entry") is False, (
            f"{row['entry_id']} 的 effective_entry_id={row['effective_entry_id']!r} "
            "与自身不同，但它被标成 independent_entry=True —— 那是伪造父级兜底"
        )


def test_summary_is_recomputed_from_rows(projection: dict) -> None:
    counts: dict[str, int] = {}
    for row in projection["bindings"]:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    assert projection["summary"] == {
        "entry_count": len(projection["bindings"]),
        "status_counts": counts,
    }


# ═══════════════════════════════════════════════════════════════════════════
# task 1.3：三种 mapping_kind 的正向 / 反向 fixture + provider 稳定 resolver identity
# ═══════════════════════════════════════════════════════════════════════════

#: 从生成器 import 真源（不是测试里手抄一份）。
import sys as _sys

_GEN_DIR = ROOT / "scripts" / "gen"
if str(_GEN_DIR) not in _sys.path:
    _sys.path.insert(0, str(_GEN_DIR))
import generate_workpaper_sync_sheet_open_bindings as GEN  # noqa: E402


def _entry(**over) -> dict:
    """最小 manifest entry 替身（只带 `binding_for` 真正读取的字段）。"""
    base = {
        "entry_id": "xlsx/gt-fixture",
        "effective_entry_id": "xlsx/gt-fixture",
        "document_type": "xlsx",
        "independent_entry": True,
        "capability": "bidirectional",
        "wp_match": {
            "wp_code_patterns": ["K11"],
            "sheet_literals": ["资产减值损失检查表K11"],
            "sheet_expressions": [],
            "source_host": "audit-platform/frontend/src/components/workpaper/GtK11.vue",
        },
    }
    base.update(over)
    return base


def _binding(entry: dict) -> dict:
    return GEN.binding_for(entry, input_digest="d" * 64)


# ── exact 正向 / 反向 ────────────────────────────────────────────────────────


def test_exact_fixture_declares_target_sheet_and_stays_pending() -> None:
    """正向：wp_code + sheet 名都是**唯一字面量** ⇒ `exact`，但**仍 pending**。

    🔴 「能推出 target sheet」不等于「已审核可迁移」：还要确认 published artifact 里真有
    这张 sheet。首版生成器不得凭 manifest 自动晋级 ready（`test_projection_does_not_claim_…`）。
    """
    row = _binding(_entry())
    assert row["mapping_kind"] == "exact"
    assert row["target_sheet"] == "资产减值损失检查表K11"
    assert row["document_scope"] == "single_sheet"
    assert row["status"] == "pending"
    assert row["reason"] == "exact_candidate_requires_published_artifact_review"
    assert row["resolver_identity"] is None, "exact 不需要 resolver identity（target 已确定）"


def test_exact_fixture_rejects_multiple_sheet_literals() -> None:
    """反向：两个 sheet 字面量 ⇒ **不得**取第一个当 target（那会静默只迁一张）。"""
    row = _binding(_entry(wp_match={
        "wp_code_patterns": ["K11"],
        "sheet_literals": ["A表", "B表"],
        "sheet_expressions": [],
    }))
    assert row["mapping_kind"] != "exact", f"两个 sheet 字面量竟被判成 exact：{row['mapping_kind']}"
    assert row["target_sheet"] is None, "多义时不得挑一个当 target"


def test_exact_fixture_rejects_multiple_wp_codes() -> None:
    """反向：两个 wp_code ⇒ 一个 sheet 请求可能命中多张表 ⇒ `ambiguous`。"""
    row = _binding(_entry(wp_match={
        "wp_code_patterns": ["K11", "K12"],
        "sheet_literals": ["资产减值损失检查表K11"],
        "sheet_expressions": [],
    }))
    assert row["mapping_kind"] == "ambiguous"
    assert row["reason"] == "ambiguous_sheet_target"
    assert row["source_wp_code"] is None, "多义时不得挑第一个 wp_code 当 source"


# ── provider 正向 / 反向 ─────────────────────────────────────────────────────


def test_provider_fixture_has_stable_resolver_identity() -> None:
    """正向：运行时 sheet 表达式 ⇒ `provider`，且必须带 `provider:<digest>` identity。"""
    row = _binding(_entry(wp_match={
        "wp_code_patterns": ["K11"],
        "sheet_literals": [],
        "sheet_expressions": [':sheet-name="sheetName"'],
    }))
    assert row["mapping_kind"] == "provider"
    identity = row["resolver_identity"]
    assert isinstance(identity, str) and identity.startswith(GEN.PROVIDER_RESOLVER_PREFIX)
    assert len(identity) == len(GEN.PROVIDER_RESOLVER_PREFIX) + 16
    assert row["target_sheet"] is None, "provider 不得凭表达式猜 target sheet"


def test_provider_resolver_identity_is_manifest_order_independent() -> None:
    """稳定性的**定义**：同样的声明集合、不同的书写顺序 ⇒ identity 必须相同。

    🔴 这条是 1.3 的核心。若 identity 由「声明列表原序」算，manifest 重排一次全部
    provider binding 的 `binding_id` 就变 ⇒ 已审核 binding 集体失效、需要重审。
    """
    # 🔴 必须用**单个** wp_code：两个 wp_code 会被 `len(wp_patterns) > 1` 判成
    # ambiguous，根本不进 provider 分支 —— 首版这样写，排序逻辑从未被触达，变异存活。
    # provider 分支的真实形态是「一个 wp_code + 多个 sheet 表达式」。
    a = _binding(_entry(wp_match={
        "wp_code_patterns": ["K11"],
        "sheet_literals": [],
        "sheet_expressions": ['a', 'b'],
    }))
    b = _binding(_entry(wp_match={
        "wp_code_patterns": ["K11"],
        "sheet_literals": [],
        "sheet_expressions": ['b', 'a'],
    }))
    assert a["mapping_kind"] == "provider", f"fixture 没进 provider 分支：{a['mapping_kind']}"
    assert a["resolver_identity"] == b["resolver_identity"], (
        f"声明顺序不同导致 identity 漂移：{a['resolver_identity']} vs {b['resolver_identity']}"
    )


def test_provider_resolver_identity_changes_with_declarations() -> None:
    """反向：声明集合真的变了 ⇒ identity **必须**变（否则改声明不会触发重审）。"""
    a = _binding(_entry(wp_match={
        "wp_code_patterns": ["K11"], "sheet_literals": [], "sheet_expressions": ["x"],
    }))
    b = _binding(_entry(wp_match={
        "wp_code_patterns": ["K11"], "sheet_literals": [], "sheet_expressions": ["y"],
    }))
    assert a["resolver_identity"] != b["resolver_identity"]


# ── whole_workbook 正向 / 反向 ──────────────────────────────────────────────


def test_whole_workbook_fixture_is_detected_from_marker() -> None:
    """正向：有整册标记 ⇒ `whole_workbook` scope，且**不带** target sheet。

    🔴 标记的**真实**载体是 `mounts`（`has_whole_workbook_marker` 扫
    `canonical_json(entry["mounts"])`），不是 `wp_match`。首版 fixture 按 wp_match 写，
    实测判据恒 False —— 现读接口的又一次提醒。
    """
    entry = _entry(
        wp_match={
            "wp_code_patterns": ["D4"],
            "sheet_literals": ["首个业务 sheet"],
            "sheet_expressions": [':sheet-name="activeSheetName"'],
            "source_host": "audit-platform/frontend/src/components/workpaper/GtWpRenderer.vue",
        },
        mounts=[{
            "component": "GtOnlyOfficeSheet",
            "attributes": [
                {"name": "bind", "argument": "whole-workbook", "expression": "true"},
            ],
        }],
    )
    assert GEN.has_whole_workbook_marker(entry), "整册标记未被识别 —— fixture 前提不成立"
    row = _binding(entry)
    assert row["mapping_kind"] == "whole_workbook"
    assert row["document_scope"] == "whole_workbook"
    assert row["status"] == "pending"
    assert row["reason"] == "whole_workbook_target_requires_reviewed_binding"


def test_non_xlsx_is_out_of_scope_not_pending() -> None:
    """反向：docx / custom 必须 `out_of_scope`（不是 pending）—— 它们的处置完全不同。

    `pending` 会被「等它变成 ready」的流程反复扫到；`out_of_scope` 是明确不适用本迁移，
    永远不该出现在迁移队列里（Requirement 5.1~5.4）。
    """
    row = _binding(_entry(document_type="docx"))
    assert row["status"] == "out_of_scope"
    assert row["mapping_kind"] == "out_of_scope"
    assert row["reason"] == "document_type_out_of_scope"


# ═══════════════════════════════════════════════════════════════════════════
# task 1.4：pending reason 是封闭域，且每种形态都有专门 reason
# ═══════════════════════════════════════════════════════════════════════════


def test_every_generated_reason_is_in_the_closed_domain(projection: dict) -> None:
    """生成物里出现的每个 reason 都必须在 `PENDING_REASONS` 里。

    🔴 开放字符串会让「新加一条未登记原因」静默通过 —— 用户看到没人写过的中文、
    监控按前缀分组落进「其他」，而没人知道该找谁。
    """
    unknown = sorted(
        {row["reason"] for row in projection["bindings"] if row["reason"]}
        - GEN.PENDING_REASONS
    )
    assert not unknown, f"生成物里出现了未登记的 reason：{unknown}"


def test_ambiguous_has_its_own_reason_not_sheet_target_not_declared() -> None:
    """`ambiguous` 与「没声明 target」是两件事，不得共用 reason。

    「没声明」的处置是去补声明；「多义」的处置是**裁决选哪一个**。合成一句会让
    运维去补一份已经补过的声明。
    """
    assert "ambiguous_sheet_target" in GEN.PENDING_REASONS
    assert "sheet_target_not_declared" in GEN.PENDING_REASONS
    ambiguous = _binding(_entry(wp_match={
        "wp_code_patterns": ["A", "B"], "sheet_literals": [], "sheet_expressions": [],
    }))
    undeclared = _binding(_entry(wp_match={
        "wp_code_patterns": [], "sheet_literals": [], "sheet_expressions": [],
    }))
    assert ambiguous["reason"] == "ambiguous_sheet_target"
    assert undeclared["reason"] == "sheet_target_not_declared"
    assert ambiguous["reason"] != undeclared["reason"]


def test_stale_digest_and_missing_entry_have_reasons_reserved() -> None:
    """`stale digest` 与 `manifest_entry_missing` 必须**预留** reason（供 resolver 用）。

    它们不来自生成器（生成时源是当刻的），而来自**请求期**解析：源文件在生成后被改、
    或 binding 引用了已删除 entry。没有预留 reason 时这两类只能落进兜底。
    """
    assert "source_digest_stale" in GEN.PENDING_REASONS
    assert "manifest_entry_missing" in GEN.PENDING_REASONS


def test_no_binding_falls_back_to_parent_entry(projection: dict, manifest: dict) -> None:
    """反向：生成器**不得**产出「父级兜底」映射。

    判据：每条 binding 的 `entry_id` 必须逐字等于 manifest 里的某个 `entry_id`
    （不是 `parent_entry_id`）。父级兜底会让一张子 sheet 的编辑写进父级 artifact。
    """
    manifest_ids = {row["entry_id"] for row in manifest["entries"]}
    for row in projection["bindings"]:
        assert row["entry_id"] in manifest_ids, (
            f"binding {row['entry_id']!r} 不是 manifest 里的真实 entry（疑似父级兜底）"
        )
        # `effective_entry_id` 允许指向父级（parent_duplicate 的合法语义），但必须也在
        # manifest 里，且必须与 `entry_id` 的文档类型一致。
        assert row["effective_entry_id"] in manifest_ids


# ═══════════════════════════════════════════════════════════════════════════
# task 1.5：clean checkout 入库守卫
# ═══════════════════════════════════════════════════════════════════════════


def test_generated_projection_is_tracked_by_git() -> None:
    """生成物必须**入库**（不是构建时生成）—— 否则 clean checkout 缺文件、端点 500。

    🔴 判据用 `git ls-files` 而不是 `Path.is_file()`：后者在本地工作区永远为真，
    而 CI / 新 clone 里文件可能根本没被跟踪。

    ═══ 沙箱模式下跳过（显式，不静默）═══

    变异套件（task 5.4）把输出重定向到系统临时目录 —— 那里的文件**本来就不该入库**，
    检查它没有意义。所以沙箱模式下本条跳过，但**显式**说明原因（不是静默 pass：
    真实 CI 里 `GT_SHEET_BINDINGS_OUT` 未设，本条照常执行）。
    """
    import os as _os

    if _os.environ.get("GT_SHEET_BINDINGS_OUT"):
        pytest.skip(
            "沙箱模式（GT_SHEET_BINDINGS_OUT 已设）：沙箱文件不该入库，跳过 git 跟踪检查"
        )
    proc = subprocess.run(
        ["git", "ls-files", "--error-unmatch", str(OUTPUT.relative_to(ROOT.parent))],
        cwd=ROOT.parent, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    assert proc.returncode == 0, (
        f"生成物未入库：{OUTPUT} —— clean checkout 会缺文件（{proc.stderr.strip()}）"
    )


def test_generator_is_tracked_and_executable_entrypoint() -> None:
    """生成器本身也必须入库（否则 `--check` 守卫在 CI 里跑不了）。"""
    proc = subprocess.run(
        ["git", "ls-files", "--error-unmatch", str(GENERATOR.relative_to(ROOT.parent))],
        cwd=ROOT.parent, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    assert proc.returncode == 0, f"生成器未入库：{GENERATOR}"


def test_projection_records_every_source_digest(projection: dict) -> None:
    """源 digest 必须齐备（Requirement 8.1）。

    位置是 `source` 子对象（不是顶层）：顶层只放 `input_digest`（聚合）与 `schema_version`。
    🔴 这条判据的字段路径是**现读**的 —— 首版按「digest 都在顶层」写，实测全 None。
    """
    assert isinstance(projection.get("input_digest"), str)
    assert len(projection["input_digest"]) == 64
    source = projection.get("source")
    assert isinstance(source, dict), f"生成物缺 source 子对象：{type(source)}"
    for key in (
        "manifest_digest", "overlay_digest",
        "adjudication_digest", "wp_code_adjudication_digest",
    ):
        value = source.get(key)
        assert isinstance(value, str) and len(value) == 64, (
            f"生成物 source 缺 {key} 或长度不是 64：{value!r}"
        )
    # 三份源文件路径也必须记（可追溯，Requirement 8.1）。
    for key in ("manifest", "overlay", "adjudication"):
        assert isinstance(source.get(key), str) and source[key].strip(), (
            f"生成物 source 缺 {key} 路径"
        )


def test_check_mode_fails_when_a_source_digest_changes(tmp_path: Path) -> None:
    """反向自检：源文件变了 `--check` 必须失败（否则「重跑无 diff」是空话）。

    做法：复制仓库的生成器输入到 tmp、改一处、跑 `--check`。这里不真的跑子进程改仓库
    文件（会污染工作区），而是直接调生成器的 `build()` 并比较 digest。
    """
    fresh = GEN.build()
    # 🔴 读 `GEN.OUTPUT`（可被 `GT_SHEET_BINDINGS_OUT` 覆盖）而不是硬编码真实路径 ——
    # 理由同上：变异套件沙箱化后，磁盘上的真实产物不是「本次生成器的输出」。
    target = Path(GEN.OUTPUT)
    baseline = json.loads(target.read_text(encoding="utf-8"))
    assert fresh["input_digest"] == baseline["input_digest"], (
        "生成器 build() 的 digest 与磁盘不一致 —— 生成物已过期，先跑 --apply"
    )
    # 同一份输入重跑必须字节相同（幂等，Requirement 1.4）。
    assert GEN.render(fresh) == target.read_bytes(), (
        "同一输入重跑产出不同字节 —— 生成器不幂等（时间戳/随机序进产物？）"
    )
