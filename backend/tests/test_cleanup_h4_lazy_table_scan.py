"""
Property-based test for H4: 懒建表入 D6 — 全仓扫描清单验证.

**Validates: Requirements C5, Property H4**

验证全仓 `CREATE TABLE IF NOT EXISTS` 扫描结果：
1. 业务路由中的懒建表已被完整识别并记录
2. 排除 migrations/tests 后，所有懒建表均在清单中
3. 清单文档存在且内容与实际扫描一致
"""

import os
import re
from pathlib import Path

import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

# 仓库根目录
REPO_ROOT = Path(__file__).parent.parent.parent

# 扫描目标目录
SCAN_DIRS = [
    REPO_ROOT / "backend" / "app",
    REPO_ROOT / "backend" / "scripts",
]

# 排除目录（migrations / tests / .hypothesis / node_modules / __pycache__）
EXCLUDE_DIRS = {
    "migrations", "tests", ".hypothesis", "node_modules",
    "__pycache__", ".git", ".venv", "venv", "dist", "build",
    ".kiro",
}

# 已知的懒建表清单（与 docs/lazy-create-tables-inventory.md 一致）
# 注：account_note_mapping + consol_cell_comments 已由 Task 8 迁移入 D6（V040），
# consol_worksheet_data + consol_note_data 已由复盘补充迁移入 D6（V041），
# formula_audit_log 已由实施后复盘（2026-06-01）彻底收口哈希链（rollback 端点
#   最后一处 ensure_table 已删），不再在 router 中懒建，仍记录在清单文档中
KNOWN_LAZY_TABLES: dict[str, str] = {
    # 业务路由懒建表（仍存在）—— 已全部收口/迁移，当前为空
}

# 已迁移入 D6 的表（V040/V041，不再在 router 中懒建）
MIGRATED_TO_D6_TABLES = {
    "account_note_mapping": "backend/app/routers/account_note_mapping.py",
    "consol_cell_comments": "backend/app/routers/consol_cell_comments.py",
    "consol_worksheet_data": "backend/app/routers/consol_worksheet_data.py",
    "consol_note_data": "backend/app/routers/consol_note_sections.py",
}

# 已收口哈希链 / 彻底消除懒建的表（不再有 CREATE TABLE IF NOT EXISTS）
ELIMINATED_LAZY_TABLES = {
    "formula_audit_log": "backend/app/routers/formula_audit_log.py",
}

# 基础设施表（合理使用，不算绕 D6）
INFRA_TABLES = {
    "schema_version": "backend/app/core/migration_runner.py",
    "schema_migration_failures": "backend/app/core/migration_runner.py",
    "schema_drift_log": "backend/app/core/schema_drift_detector.py",
}

# 本 spec 处理的表（已迁移入 D6）
THIS_SPEC_TABLES = {"account_note_mapping", "consol_cell_comments"}

# formula-engine-unification spec 处理的表
FORMULA_SPEC_TABLES = {"formula_audit_log"}

# 合并模块待评估的表
CONSOL_TABLES = {"consol_worksheet_data", "consol_note_data"}

# CREATE TABLE IF NOT EXISTS 正则
CREATE_TABLE_PATTERN = re.compile(
    r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+(\w+)",
    re.IGNORECASE,
)


def _collect_python_files() -> list[Path]:
    """收集扫描目标目录中的 Python 文件。"""
    files = []
    for scan_dir in SCAN_DIRS:
        if not scan_dir.exists():
            continue
        for root, dirs, filenames in os.walk(scan_dir):
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
            for fname in filenames:
                if fname.endswith(".py"):
                    files.append(Path(root) / fname)
    return files


def _scan_lazy_create_tables(files: list[Path]) -> dict[str, list[Path]]:
    """扫描文件中的 CREATE TABLE IF NOT EXISTS，返回 {表名: [文件列表]}。"""
    results: dict[str, list[Path]] = {}
    for fpath in files:
        try:
            content = fpath.read_text(encoding="utf-8", errors="ignore")
            matches = CREATE_TABLE_PATTERN.findall(content)
            for table_name in matches:
                results.setdefault(table_name, []).append(fpath)
        except (OSError, UnicodeDecodeError):
            continue
    return results


# ─── 确定性验证测试 ───────────────────────────────────────────────


class TestH4LazyTableScan:
    """H4: 懒建表扫描清单 — 确定性验证。"""

    def test_inventory_document_exists(self):
        """清单文档已创建。"""
        inventory = REPO_ROOT / "docs" / "lazy-create-tables-inventory.md"
        assert inventory.exists(), f"清单文档不存在: {inventory}"

    def test_inventory_contains_all_known_tables(self):
        """清单文档包含所有已知懒建表（含已迁移的）。"""
        inventory = REPO_ROOT / "docs" / "lazy-create-tables-inventory.md"
        content = inventory.read_text(encoding="utf-8")
        for table_name in KNOWN_LAZY_TABLES:
            assert table_name in content, (
                f"清单文档缺少表: {table_name}"
            )
        for table_name in MIGRATED_TO_D6_TABLES:
            assert table_name in content, (
                f"清单文档缺少已迁移表: {table_name}"
            )

    def test_scan_finds_all_known_lazy_tables(self):
        """实际扫描结果包含所有已知业务懒建表（仍在 router 中懒建的）。

        注：formula_audit_log 已收口消除（见 ELIMINATED_LAZY_TABLES），
        KNOWN_LAZY_TABLES 当前为空，本测试退化为空集断言（保留以防未来新增）。
        """
        files = _collect_python_files()
        found = _scan_lazy_create_tables(files)
        for table_name in KNOWN_LAZY_TABLES:
            assert table_name in found, (
                f"扫描未找到已知懒建表: {table_name}"
            )

    def test_eliminated_tables_no_longer_lazy_created(self):
        """已收口哈希链/消除懒建的表（formula_audit_log）不再有 CREATE TABLE IF NOT EXISTS。"""
        files = _collect_python_files()
        found = _scan_lazy_create_tables(files)
        for table_name in ELIMINATED_LAZY_TABLES:
            assert table_name not in found, (
                f"已收口消除的表仍在 router 中懒建: {table_name}"
            )

    def test_migrated_tables_no_longer_lazy_created(self):
        """已迁移入 D6 的表不再在 router 中懒建。"""
        files = _collect_python_files()
        found = _scan_lazy_create_tables(files)
        for table_name in MIGRATED_TO_D6_TABLES:
            assert table_name not in found, (
                f"已迁移入 D6 的表仍在 router 中懒建: {table_name}"
            )

    def test_no_unknown_lazy_tables(self):
        """扫描结果中无未记录的懒建表（排除基础设施表 + 已迁移表）。"""
        files = _collect_python_files()
        found = _scan_lazy_create_tables(files)
        all_known = set(KNOWN_LAZY_TABLES) | set(INFRA_TABLES) | set(MIGRATED_TO_D6_TABLES) | set(ELIMINATED_LAZY_TABLES)
        unknown = set(found.keys()) - all_known
        assert unknown == set(), (
            f"发现未记录的懒建表: {unknown}\n"
            + "\n".join(
                f"  {t}: {[str(p) for p in found[t]]}" for t in unknown
            )
        )

    def test_this_spec_tables_identified(self):
        """本 spec 处理的表（account_note_mapping + consol_cell_comments）已标记。"""
        inventory = REPO_ROOT / "docs" / "lazy-create-tables-inventory.md"
        content = inventory.read_text(encoding="utf-8")
        for table_name in THIS_SPEC_TABLES:
            assert table_name in content, (
                f"本 spec 处理的表未在清单中标记: {table_name}"
            )

    def test_formula_audit_log_delegated(self):
        """formula_audit_log 已标记为 formula-engine-unification spec 处理。"""
        inventory = REPO_ROOT / "docs" / "lazy-create-tables-inventory.md"
        content = inventory.read_text(encoding="utf-8")
        assert "formula_audit_log" in content
        assert "formula-engine" in content.lower() or "formula-engine-unification" in content


# ─── 属性测试（Hypothesis）─────────────────────────────────────────


@st.composite
def python_file_sample(draw):
    """从扫描目标中随机抽样 Python 文件。"""
    all_files = _collect_python_files()
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


class TestH4Property:
    """H4 属性测试：懒建表扫描完整性。"""

    @given(files=python_file_sample())
    @settings(max_examples=10, suppress_health_check=[HealthCheck.too_slow])
    def test_all_lazy_tables_in_sample_are_known(self, files: list[Path]):
        """
        **Validates: Requirements C5**

        属性：对扫描目标 Python 文件的任意子集，发现的
        CREATE TABLE IF NOT EXISTS 表名均在已知清单中
        （业务表 + 基础设施表）。
        """
        found = _scan_lazy_create_tables(files)
        all_known = set(KNOWN_LAZY_TABLES) | set(INFRA_TABLES) | set(MIGRATED_TO_D6_TABLES) | set(ELIMINATED_LAZY_TABLES)
        unknown = set(found.keys()) - all_known
        assert unknown == set(), (
            f"随机抽样发现未记录的懒建表: {unknown}\n"
            + "\n".join(
                f"  {t}: {[str(p) for p in found[t]]}" for t in unknown
            )
        )
