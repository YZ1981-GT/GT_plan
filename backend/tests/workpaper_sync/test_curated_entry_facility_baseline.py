# -*- coding: utf-8 -*-
"""Task 1 守卫：curated-entry facility 的「空/缺省即字节不变」基线（Property 1）。

spec: `workpaper-sync-curated-entry-facility`
Requirements 1.3
Property 1（Empty case byte-identity）

## 这个文件要证明什么

curated-entry facility 是**加法式**改动：当 reviewed overlay 里没有（或为空）
`curated_entries` 时，真实 `build_manifest` 产出的 manifest JSON + 前端 TS 必须与
「纯 discovery」基线逐字节一致（Requirement 1.3 / Property 1）。这条守卫**必须先于
facility 存在**，否则 facility 落地后就没有独立判据能证明它没扰动 discovery 路径
（加法式不变量将不可证）。

## 为什么用「重建的 discovery 定影」而不是活源码（环境阻塞，实测非假设）

本分支上真实 `build_manifest` **无法**端到端跑活源码，两个独立且都已实测的原因：

1. `discover_source()`（Node AST）算出的 sourceDigest = `a18a531d…`，已不等于 reviewed
   `overlay.approved_source_digest` = `d9fddb64…` ⇒ `build_manifest` 内的 digest 门
   **按设计** fail closed（宿主挂载清单在本分支漂移了）。实测：
   `python backend/scripts/gen/generate_workpaper_sync_manifest.py --check`
   报 `source mounts changed since the reviewed overlay`。
2. 即使绕过该门，`derive_entry_profile` 会扫活的前端文件，而自 manifest 提交以来入边
   引用集已漂移（如新增 `registry/entries/programs.ts` 把某宿主 inbound_reference_count
   从 1 顶到 2）⇒ 活源派生无法复现已提交的 manifest 字节。旁证：同区
   `test_task73_entry_profile_manifest.py::…test_provenance_points_at_real_source_lines`
   在本分支已因行号漂移而 RED（与本任务无关，恰好佐证「活源 ≠ 已提交 manifest」）。

已提交的 manifest 内嵌了跑真实 `build_manifest` 所需的全部 discovery 事实：277 条
mounts（276 template_ast 物理挂载 + 1 registry_ast 动态分发器）、reviewed sourceDigest、
以及 stats.byComponent。`data/_capture_curated_baseline.py` 从这些内嵌事实**重建**出一个
忠实的 discovery dict——喂给真实 `build_manifest` 能逐条复现已提交 entry 的结构（entry_id
集合、mounts、capability 等全等），唯一与已提交字节不同的字段是 `profile_source`（因为
`build_manifest` 会对活源重新派生它）。我们把这次**真实运行**的输出定影为基线
`curated_baseline_manifest.json` / `curated_baseline_frontend.generated.ts`。

## 判据不是重言式

- 基线定影（`test_absent_curated_matches_frozen_baseline`）：跑**真实** `build_manifest`
  （非 stub），比对磁盘上冻结的字节。facility 落地后若空/缺省路径被扰动，这里会 RED。
- 漂移免疫的相对不变量（`test_absent_run_matches_itself_deterministically`）：同进程内跑
  两次真实 `build_manifest`（缺省 curated），要求逐字节一致——排除「基线定影只是自我比对」
  的嫌疑，也证明活源派生在一次会话内稳定。
- facility 目标（`test_empty_curated_list_equals_absent_baseline`）：`curated_entries: []`
  今天会改 `overlay_digest` ⇒ 与缺省**不**等（pre-facility 事实）。标为 strict xfail，
  Task 3 把空列表规范化出 overlay_digest 后它会 xpass→在 strict 下转为「必须改测试」信号，
  从而驱动 facility 真正实现 Requirement 1.3 的「空 or 缺省」两种写法都字节不变。
"""
from __future__ import annotations

import copy
import importlib.util
import json
import os
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

_GENERATOR_PATH = _BACKEND / "scripts" / "gen" / "generate_workpaper_sync_manifest.py"
_OVERLAY_PATH = _BACKEND / "data" / "workpaper_sync_entry_overlay.json"
_FIXTURE_DIR = Path(__file__).resolve().parent / "data"
_DISCOVERY_FIXTURE = _FIXTURE_DIR / "curated_baseline_discovery.json"
_BASELINE_MANIFEST = _FIXTURE_DIR / "curated_baseline_manifest.json"
_BASELINE_FRONTEND = _FIXTURE_DIR / "curated_baseline_frontend.generated.ts"


def _load(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def generator() -> ModuleType:
    return _load(_GENERATOR_PATH, "curated_baseline_generator")


@pytest.fixture(scope="module")
def overlay() -> dict[str, Any]:
    """『纯 discovery』overlay —— 把真实 overlay 的 `curated_entries` 段剥掉一份副本。

    Task 5 之后 reviewed overlay 已带 D4-9 的 curated 声明（这是本 spec 的目标改动）。
    但本文件证明的是「curated 缺省/空 ⇒ 字节与纯 discovery 基线一致」的**加法不变量**，
    该不变量只对『没有 curated 段』的 overlay 成立。所以这里剥掉 `curated_entries` 得到
    一份 curated-free 的副本，语义与 Task 5 之前一模一样（absent/empty ⇒ byte-identical），
    而不是断言真实 overlay 里没有 curated（那条前提已随 Task 5 目标改动而失效）。

    仍保留一条反向前提断言：真实 overlay **必须**已带 curated_entries（否则说明 Task 5 的
    overlay 声明丢了，本 strip 就成了空操作、基线不变量退化成对未改动 overlay 的自证）。
    """
    value = json.loads(_OVERLAY_PATH.read_text(encoding="utf-8"))
    assert "curated_entries" in value, (
        "真实 overlay 未带 curated_entries ⇒ Task 5 的 D4-9 curated 声明丢失；"
        "本文件的 strip-a-copy 基线会退化成对未改动 overlay 的自证"
    )
    stripped = copy.deepcopy(value)
    stripped.pop("curated_entries", None)
    return stripped


@pytest.fixture(scope="module")
def discovery() -> dict[str, Any]:
    """重建的 discovery 定影（见模块 docstring 的环境阻塞说明）。

    它把守卫与「活源码 / Node 发现」解耦：本分支活源已漂移，任何依赖 `discover_source()`
    的判据都会因 approved_source_digest 门 fail closed，无法证明 facility 的加法不变量。
    """
    if not _DISCOVERY_FIXTURE.is_file():
        pytest.fail(
            f"缺少 discovery 定影 {_DISCOVERY_FIXTURE.name}；"
            "先跑 python backend/tests/workpaper_sync/data/_capture_curated_baseline.py"
        )
    return json.loads(_DISCOVERY_FIXTURE.read_text(encoding="utf-8"))


def _read_baseline(path: Path) -> str:
    if not path.is_file():
        pytest.fail(
            f"缺少基线定影 {path.name}；"
            "先跑 python backend/tests/workpaper_sync/data/_capture_curated_baseline.py"
        )
    return path.read_text(encoding="utf-8")


class TestEmptyCaseByteIdentity:
    def test_baseline_fixtures_are_self_consistent(
        self, generator: ModuleType, discovery: dict[str, Any]
    ) -> None:
        """反空集：定影里 entry 数与 discovery 挂载数必须非平凡，否则下面全成 vacuous。"""
        baseline = json.loads(_read_baseline(_BASELINE_MANIFEST))
        assert baseline["entries"], "基线 manifest 无 entry ⇒ 字节比对是空操作"
        assert len(baseline["entries"]) >= 100, (
            f"基线只有 {len(baseline['entries'])} 条 entry，远少于生产的 186 ⇒ 定影可疑"
        )
        assert len(discovery["mounts"]) == baseline["stats"]["mount_count"]
        assert discovery["sourceDigest"] == baseline["source_digest"]
        # 基线确实是对整份 manifest 现算的 digest（否则字节比对与 digest 脱钩）。
        recomputed = copy.deepcopy(baseline)
        recomputed.pop("manifest_digest")
        assert generator._sha256_bytes(
            generator._stable_json(recomputed).encode("utf-8")
        ) == baseline["manifest_digest"], "基线 manifest_digest 与其内容不自洽"

    def test_absent_curated_matches_frozen_baseline(
        self, generator: ModuleType, discovery: dict[str, Any], overlay: dict[str, Any]
    ) -> None:
        """真实 build_manifest（curated 缺省）产出的两件产物逐字节 == 冻结基线。

        这是 Property 1 的锚点：facility 落地后若空/缺省路径被扰动，本条 RED。
        跑的是真实 `build_manifest` + 真实 overlay + 真实 render_* ——没有 stub。
        """
        built = generator.build_manifest(discovery, overlay)
        manifest_bytes = generator.render_manifest(built)
        frontend_bytes = generator.render_frontend(built)

        assert manifest_bytes == _read_baseline(_BASELINE_MANIFEST), (
            "curated 缺省时 manifest 字节偏离基线 ⇒ 加法不变量被破坏（Requirement 1.3）。"
            "若确因活源漂移，请复核 diff 后用 _capture_curated_baseline.py 重新定影"
        )
        assert frontend_bytes == _read_baseline(_BASELINE_FRONTEND), (
            "curated 缺省时前端 TS 字节偏离基线 ⇒ 加法不变量被破坏（Requirement 1.3）"
        )

    def test_absent_run_matches_itself_deterministically(
        self, generator: ModuleType, discovery: dict[str, Any], overlay: dict[str, Any]
    ) -> None:
        """漂移免疫的相对不变量：同进程两次真实 build_manifest 必须逐字节一致。

        它保证上一条不是「拿基线跟自己比」的重言式：两次独立运行的活源派生若不稳定，
        这里会 RED；也证明基线定影可复现。
        """
        first = generator.build_manifest(discovery, overlay)
        second = generator.build_manifest(discovery, overlay)
        assert generator.render_manifest(first) == generator.render_manifest(second)
        assert generator.render_frontend(first) == generator.render_frontend(second)

    def test_absent_key_equals_explicit_absence(
        self, generator: ModuleType, discovery: dict[str, Any], overlay: dict[str, Any]
    ) -> None:
        """`overlay` 不含 `curated_entries` 键 ⇒ 与手工 pop 掉该键结果一致（自洽性）。

        当前 overlay 本就无此键；本条把「无键」与「显式删键」两条路径对齐，作为 Task 2/3
        引入 facility 后区分『缺省键』与『空列表』语义的锚（缺省键必须永远等于基线）。
        """
        without = copy.deepcopy(overlay)
        without.pop("curated_entries", None)
        built = generator.build_manifest(discovery, without)
        assert generator.render_manifest(built) == _read_baseline(_BASELINE_MANIFEST)

    def test_empty_curated_list_equals_absent_baseline(
        self, generator: ModuleType, discovery: dict[str, Any], overlay: dict[str, Any]
    ) -> None:
        """Requirement 1.3 的『空 curated_entries』分支：`[]` 也必须字节等于纯 discovery 基线。

        Task 3 已落地：`build_manifest` 用 `_overlay_digest` 把空/缺省 `curated_entries`
        规范化出 overlay_digest（并仅在非空时加入 `curated_source_digest` / `curated_entry_count`），
        故显式 `curated_entries: []` 与缺省两种写法都字节等于纯 discovery 基线。跑的是真实
        build_manifest，非死代码。此前为 strict-xfail，Task 3 达成目标后转为常规通过测试。
        """
        with_empty = copy.deepcopy(overlay)
        with_empty["curated_entries"] = []
        built = generator.build_manifest(discovery, with_empty)
        assert generator.render_manifest(built) == _read_baseline(_BASELINE_MANIFEST)
