"""
Property-based test for H1: unified_dependency_graph.json 评估结果 — 运行时用，保留。

**Validates: Requirements C1, Property H1**

验证 unified_dependency_graph.json 是运行时缓存文件（非死数据）：
1. 存在至少 1 个 Python 运行时消费方（import/读取该文件）
2. linkage_graph_builder 是生产方（写入该文件）
3. 文件存在于磁盘（运行时需要）
结论：保留，不做 git rm。
"""

import os
import re
from pathlib import Path

import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

# 仓库根目录
REPO_ROOT = Path(__file__).parent.parent.parent

# 目标文件
TARGET_FILE = REPO_ROOT / "backend" / "data" / "unified_dependency_graph.json"

# 需要扫描的代码目录
CODE_DIRS = [
    REPO_ROOT / "backend" / "app",
]

# 排除目录
EXCLUDE_DIRS = {
    "node_modules", "__pycache__", ".git", ".venv", "venv",
    "dist", "build", ".hypothesis", ".kiro",
}

# 运行时引用模式（代码中读取/加载该文件的模式）
RUNTIME_LOAD_PATTERNS = [
    r'unified_dependency_graph\.json',
]


def _collect_py_files() -> list[Path]:
    """收集 backend/app 下所有 .py 文件。"""
    files = []
    for code_dir in CODE_DIRS:
        if not code_dir.exists():
            continue
        for root, dirs, filenames in os.walk(code_dir):
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
            for fname in filenames:
                if fname.endswith(".py"):
                    files.append(Path(root) / fname)
    return files


def _find_runtime_consumers(files: list[Path]) -> list[tuple[Path, int, str]]:
    """找到运行时加载 unified_dependency_graph.json 的代码行。"""
    hits = []
    pattern = re.compile("|".join(RUNTIME_LOAD_PATTERNS), re.IGNORECASE)
    this_file = Path(__file__).resolve()
    for fpath in files:
        if fpath.resolve() == this_file:
            continue
        try:
            content = fpath.read_text(encoding="utf-8", errors="ignore")
            for i, line in enumerate(content.splitlines(), 1):
                if pattern.search(line):
                    hits.append((fpath, i, line.strip()))
        except (OSError, UnicodeDecodeError):
            continue
    return hits


# ─── 确定性验证测试 ───────────────────────────────────────────────


class TestH1UnifiedGraphEvaluation:
    """H1: unified_dependency_graph.json 评估 — 确认运行时用，保留。"""

    def test_file_exists_on_disk(self):
        """unified_dependency_graph.json 存在于磁盘（运行时缓存）。"""
        assert TARGET_FILE.exists(), (
            f"unified_dependency_graph.json 不存在: {TARGET_FILE}\n"
            "该文件是运行时缓存，应保留在仓库中。"
        )

    def test_has_runtime_consumers(self):
        """至少存在 1 个运行时消费方加载该文件。"""
        files = _collect_py_files()
        hits = _find_runtime_consumers(files)
        # 排除 linkage_graph_builder（它是生产方，不是消费方）
        consumers = [
            h for h in hits
            if "linkage_graph_builder" not in str(h[0])
        ]
        assert len(consumers) >= 1, (
            "未找到 unified_dependency_graph.json 的运行时消费方。\n"
            "如果确实无消费方，该文件应按死数据处理。"
        )

    def test_known_consumers_exist(self):
        """已知消费方文件存在：linkage_bus.py + stale_propagation_engine.py。"""
        consumer_files = [
            REPO_ROOT / "backend" / "app" / "routers" / "linkage_bus.py",
            REPO_ROOT / "backend" / "app" / "services" / "stale_propagation_engine.py",
        ]
        for f in consumer_files:
            assert f.exists(), f"已知消费方不存在: {f}"

    def test_linkage_graph_builder_is_producer(self):
        """linkage_graph_builder.py 是该文件的生产方。"""
        producer = REPO_ROOT / "backend" / "app" / "services" / "linkage_graph_builder.py"
        assert producer.exists(), f"生产方不存在: {producer}"
        content = producer.read_text(encoding="utf-8", errors="ignore")
        assert "unified_dependency_graph.json" in content, (
            "linkage_graph_builder.py 中未找到对 unified_dependency_graph.json 的写入引用"
        )

    def test_file_is_valid_json(self):
        """文件内容是合法 JSON（运行时可解析）。"""
        import json
        content = TARGET_FILE.read_text(encoding="utf-8")
        data = json.loads(content)
        # 应有 nodes 和 edges 结构
        assert "nodes" in data or "edges" in data, (
            "unified_dependency_graph.json 缺少 nodes/edges 结构"
        )


# ─── 属性测试（Hypothesis）─────────────────────────────────────────


@st.composite
def py_file_sample(draw):
    """从 backend/app 下随机抽样 .py 文件。"""
    all_files = _collect_py_files()
    if not all_files:
        return []
    sample_size = draw(st.integers(min_value=1, max_value=min(30, len(all_files))))
    indices = draw(
        st.lists(
            st.integers(min_value=0, max_value=len(all_files) - 1),
            min_size=sample_size,
            max_size=sample_size,
            unique=True,
        )
    )
    return [all_files[i] for i in indices]


class TestH1UnifiedGraphProperty:
    """H1 属性测试：unified_dependency_graph.json 运行时引用验证。"""

    @given(files=py_file_sample())
    @settings(max_examples=10, suppress_health_check=[HealthCheck.too_slow])
    def test_runtime_reference_discoverable_in_samples(self, files: list[Path]):
        """
        **Validates: Requirements C1**

        属性：在 backend/app 的随机文件子集中，如果包含已知消费方文件，
        则必能发现对 unified_dependency_graph.json 的运行时引用。
        这证明该文件是活跃的运行时依赖，非死数据。
        """
        hits = _find_runtime_consumers(files)
        # 检查抽样中是否包含已知消费方
        known_consumers = {
            "linkage_bus.py",
            "stale_propagation_engine.py",
        }
        sampled_names = {f.name for f in files}
        has_known_consumer = bool(sampled_names & known_consumers)

        if has_known_consumer:
            # 如果抽样包含已知消费方，必须能发现引用
            assert len(hits) >= 1, (
                f"抽样包含已知消费方 {sampled_names & known_consumers}，"
                "但未发现 unified_dependency_graph.json 引用"
            )
