"""stale 传播引擎推迟加载依赖图（spec backend-startup-and-request-overhead R1.4 / 任务 3）。

判据：导入时不读图；第一次读到任一字段后的状态与「导入时加载、之后再改」逐字段相同；
先赋值 / monkeypatch / mock.patch 某个字段的写法结果与立即加载时相同；并发第一次读只加载一次。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from app.services import stale_propagation_engine as spe
from app.services.stale_propagation_engine import StalePropagationEngine

BACKEND = Path(__file__).resolve().parents[1]
FIELDS = sorted(spe._DEFERRED_FIELDS)

GRAPH = {
    "edges": [
        {"source": "TB:1001::期末", "target": "WP:E1:审定表E1-1:审定数"},
        {"source": "WP:E1:审定表E1-1:审定数", "target": "REPORT:BS001"},
        {"source": "REPORT:BS001", "target": "NOTE:五、1"},
        {"source": "E1/E1-1/B5", "target": "NOTE:五、1"},
    ]
}


@pytest.fixture
def graph_dir(tmp_path, monkeypatch):
    (tmp_path / "unified_dependency_graph.json").write_text(json.dumps(GRAPH, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(spe, "DATA_DIR", tmp_path)
    return tmp_path


def _state(engine: StalePropagationEngine) -> dict:
    return {f: getattr(engine, f) for f in FIELDS}


def test_module_singleton_does_not_read_graph_at_import():
    code = (
        "import json, app.services.stale_propagation_engine as m;"
        "print(json.dumps(sorted(m.stale_engine.__dict__)))"
    )
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    out = subprocess.run([sys.executable, "-c", code], cwd=BACKEND, env=env, capture_output=True,
                         text=True, encoding="utf-8", errors="replace", timeout=120)
    assert out.returncode == 0, out.stderr[-2000:]
    assert json.loads(out.stdout.strip().splitlines()[-1]) == ["_deferred_load"]


def test_first_read_gives_same_state_as_eager(graph_dir):
    eager = StalePropagationEngine()
    for first in FIELDS + ["is_degraded", "graph_size"]:
        lazy = StalePropagationEngine(defer_load=True)
        assert set(lazy.__dict__) == {"_deferred_load"}
        getattr(lazy, first)
        assert _state(lazy) == _state(eager), first
    assert eager._loaded and not eager._degraded and eager.graph_size == 4
    # 身份索引不在加载时建：首次按身份找起点时按当前目录版本构建（acnr-foundation-defect-closure T21）
    assert eager._identity_index == {} and eager._identity_version is None


def test_missing_graph_is_degraded_like_eager(tmp_path, monkeypatch):
    monkeypatch.setattr(spe, "DATA_DIR", tmp_path)
    lazy = StalePropagationEngine(defer_load=True)
    assert lazy.is_degraded is True
    assert _state(lazy) == _state(StalePropagationEngine())


def test_fields_set_before_first_read_are_kept(graph_dir):
    lazy = StalePropagationEngine(defer_load=True)
    preset = {"X": ["Y"]}
    lazy._graph = preset
    lazy._degraded = True
    eager = StalePropagationEngine()
    eager._graph = {"X": ["Y"]}
    eager._degraded = True
    assert lazy._identity_index == eager._identity_index
    assert lazy._identity_version == eager._identity_version
    assert lazy._graph is preset
    assert _state(lazy) == _state(eager)


def _count_loads(monkeypatch) -> list[int]:
    calls: list[int] = []
    original = StalePropagationEngine._load_graph

    def counted(self):
        calls.append(1)
        original(self)

    monkeypatch.setattr(StalePropagationEngine, "_load_graph", counted)
    return calls


def test_mock_patch_restores_loaded_objects(graph_dir, monkeypatch):
    """patch 是第一次访问：退出时 mock 先删属性再看还有没有，必须照常 AttributeError 才会把原值放回。"""
    loads = _count_loads(monkeypatch)
    lazy = StalePropagationEngine(defer_load=True)
    with patch.object(lazy, "_graph", {}):
        assert lazy.graph_size == 0
        loaded_reverse = lazy._reverse_graph
    assert lazy.graph_size == 4
    with patch.object(lazy, "_degraded", True):
        assert lazy.is_degraded is True
    assert lazy.is_degraded is False
    assert lazy._reverse_graph is loaded_reverse
    assert loads == [1]
    assert _state(lazy) == _state(StalePropagationEngine())


def test_monkeypatch_raising_false_restores_loaded_value(graph_dir):
    lazy = StalePropagationEngine(defer_load=True)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(lazy, "_degraded", True, raising=False)
        assert lazy.is_degraded is True
    assert lazy.is_degraded is False and lazy.graph_size == 4


def test_concurrent_first_reads_load_once(graph_dir, monkeypatch):
    calls: list[int] = []
    original = StalePropagationEngine._load_graph

    def slow_load(self):
        calls.append(threading.get_ident())
        time.sleep(0.2)
        original(self)

    monkeypatch.setattr(StalePropagationEngine, "_load_graph", slow_load)
    lazy = StalePropagationEngine(defer_load=True)
    seen: list[tuple[int, int]] = []
    barrier = threading.Barrier(8)

    def reader():
        barrier.wait()
        g = lazy._graph
        seen.append((id(g), sum(len(v) for v in g.values())))

    threads = [threading.Thread(target=reader) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(10)
    assert len(calls) == 1
    assert len(seen) == 8 and len(set(seen)) == 1 and seen[0][1] == 4


def test_reload_graph_on_deferred_engine_reads_current_file(graph_dir):
    lazy = StalePropagationEngine(defer_load=True)
    lazy.reload_graph()
    assert _state(lazy) == _state(StalePropagationEngine())


def test_unknown_attribute_raises_without_loading(graph_dir):
    lazy = StalePropagationEngine(defer_load=True)
    with pytest.raises(AttributeError):
        lazy.no_such_field  # noqa: B018
    assert set(lazy.__dict__) == {"_deferred_load"}


def test_instances_built_with_new_keep_attribute_error():
    engine = StalePropagationEngine.__new__(StalePropagationEngine)
    engine._graph = {}
    with pytest.raises(AttributeError):
        engine._identity_index  # noqa: B018
