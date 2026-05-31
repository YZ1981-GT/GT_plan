"""
Property-based test for H1: 死文件无引用.

**Validates: Requirements C1, Property H1**

验证 address_registry_l1_physical.json 删除后：
1. 全仓 Python/TS/JS/Vue 代码 0 引用
2. app import OK（无运行时依赖该文件）
"""

import importlib
import os
import re
from pathlib import Path

import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

# 仓库根目录
REPO_ROOT = Path(__file__).parent.parent.parent

# 需要扫描的代码目录
CODE_DIRS = [
    REPO_ROOT / "backend",
    REPO_ROOT / "audit-platform",
]

# 代码文件扩展名
CODE_EXTENSIONS = {".py", ".ts", ".js", ".vue", ".tsx", ".jsx"}

# 排除目录
EXCLUDE_DIRS = {
    "node_modules", "__pycache__", ".git", ".venv", "venv",
    "dist", "build", ".hypothesis", ".kiro",
}

# 死文件标识符（各种可能的引用形式）
DEAD_FILE_PATTERNS = [
    "address_registry_l1_physical",
    "l1_physical.json",
    "l1_physical",
]


def _collect_code_files() -> list[Path]:
    """收集全仓代码文件。"""
    files = []
    for code_dir in CODE_DIRS:
        if not code_dir.exists():
            continue
        for root, dirs, filenames in os.walk(code_dir):
            # 排除不需要扫描的目录
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
            for fname in filenames:
                fpath = Path(root) / fname
                if fpath.suffix in CODE_EXTENSIONS:
                    files.append(fpath)
    return files


def _scan_for_dead_file_references(files: list[Path]) -> list[tuple[Path, int, str]]:
    """扫描代码文件中对死文件的引用，返回 (文件路径, 行号, 行内容) 列表。"""
    hits = []
    pattern = re.compile("|".join(re.escape(p) for p in DEAD_FILE_PATTERNS), re.IGNORECASE)
    # 排除本测试文件自身
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


class TestH1DeadFileNoReference:
    """H1: 死文件无引用 — 确定性验证。"""

    def test_l1_physical_file_not_on_disk(self):
        """L1 物理文件已从磁盘删除。"""
        target = REPO_ROOT / "backend" / "data" / "address_registry_l1_physical.json"
        assert not target.exists(), f"死文件仍存在: {target}"

    def test_zero_code_references(self):
        """全仓代码文件 0 处引用 address_registry_l1_physical。"""
        files = _collect_code_files()
        hits = _scan_for_dead_file_references(files)
        assert hits == [], (
            f"发现 {len(hits)} 处代码引用死文件:\n"
            + "\n".join(f"  {h[0]}:{h[1]}: {h[2]}" for h in hits[:10])
        )

    def test_app_import_ok(self):
        """删除后 app 模块仍可正常 import。"""
        # 重新 import app 模块确认无 ImportError
        import app.main  # noqa: F401

        # 确认 address_registry_v2 router 也正常（它用 l2/l3/resolved 不用 l1）
        import app.routers.address_registry_v2  # noqa: F401


# ─── 属性测试（Hypothesis）─────────────────────────────────────────


# 生成随机代码文件路径子集进行抽样验证
@st.composite
def code_file_sample(draw):
    """从全仓代码文件中随机抽样一批文件。"""
    all_files = _collect_code_files()
    if not all_files:
        return []
    sample_size = draw(st.integers(min_value=1, max_value=min(50, len(all_files))))
    indices = draw(
        st.lists(
            st.integers(min_value=0, max_value=len(all_files) - 1),
            min_size=sample_size,
            max_size=sample_size,
            unique=True,
        )
    )
    return [all_files[i] for i in indices]


class TestH1Property:
    """H1 属性测试：任意代码文件子集均不含死文件引用。"""

    @given(files=code_file_sample())
    @settings(max_examples=10, suppress_health_check=[HealthCheck.too_slow])
    def test_no_dead_file_reference_in_random_sample(self, files: list[Path]):
        """
        **Validates: Requirements C1**

        属性：对全仓代码文件的任意子集，均不存在对
        address_registry_l1_physical 的引用。
        """
        hits = _scan_for_dead_file_references(files)
        assert hits == [], (
            f"随机抽样发现 {len(hits)} 处引用:\n"
            + "\n".join(f"  {h[0]}:{h[1]}: {h[2]}" for h in hits[:5])
        )
