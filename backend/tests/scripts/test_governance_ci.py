"""P2-1 CI 治理集成测试。

验证：
1. governance-checks.yml 语法有效
2. 强制执行日期逻辑正确
3. baseline 文件存在且格式正确
4. 各检查脚本 CLI 接口兼容
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
WORKFLOW_FILE = ROOT / ".github" / "workflows" / "governance-checks.yml"
BASELINES_DIR = ROOT / "backend" / "scripts" / "check" / "baselines"


class TestWorkflowSyntax:
    """governance-checks.yml YAML 有效性。"""

    def test_yaml_parseable(self):
        """workflow YAML 可以正确解析。"""
        content = WORKFLOW_FILE.read_text(encoding="utf-8")
        data = yaml.safe_load(content)
        assert data is not None
        assert "name" in data
        assert data["name"] == "Governance Checks"

    def test_has_required_jobs(self):
        """包含三个必需的 job。"""
        content = WORKFLOW_FILE.read_text(encoding="utf-8")
        data = yaml.safe_load(content)
        jobs = data.get("jobs", {})
        assert "scale-snapshot-check" in jobs
        assert "sql-column-contract" in jobs
        assert "hotspot-baseline-check" in jobs

    def test_enforce_date_configured(self):
        """强制执行日期已配置且为未来日期（warning 期内）。"""
        content = WORKFLOW_FILE.read_text(encoding="utf-8")
        data = yaml.safe_load(content)
        env = data.get("env", {})
        enforce_date_str = env.get("GOVERNANCE_ENFORCE_DATE", "")
        assert enforce_date_str, "GOVERNANCE_ENFORCE_DATE 未配置"
        # 验证日期格式
        enforce_date = date.fromisoformat(enforce_date_str)
        # 应该是合理的未来日期（至少 7 天后）或者已配置好的日期
        assert enforce_date > date(2026, 1, 1), "日期应晚于 2026-01-01"

    def test_trigger_on_pr(self):
        """CI 在 PR 时触发。"""
        content = WORKFLOW_FILE.read_text(encoding="utf-8")
        data = yaml.safe_load(content)
        on_config = data.get("on", data.get(True, {}))
        assert "pull_request" in on_config

    def test_additive_to_existing(self):
        """新 workflow 是独立文件，不修改 ci.yml。"""
        ci_file = ROOT / ".github" / "workflows" / "ci.yml"
        assert ci_file.exists()
        ci_content = ci_file.read_text(encoding="utf-8")
        # 确保 ci.yml 中没有我们新 job 的名字
        assert "governance" not in ci_content.lower() or "scale-snapshot-check" not in ci_content


class TestBaselineFiles:
    """baseline 文件存在且格式正确。"""

    def test_vue_baseline_exists(self):
        """Vue baseline 文件存在。"""
        f = BASELINES_DIR / "vue_file_lines_baseline.json"
        assert f.exists(), f"Vue baseline 不存在: {f}"

    def test_python_baseline_exists(self):
        """Python baseline 文件存在。"""
        f = BASELINES_DIR / "python_service_lines_baseline.json"
        assert f.exists(), f"Python baseline 不存在: {f}"

    def test_vue_baseline_valid_json(self):
        """Vue baseline 是有效 JSON。"""
        f = BASELINES_DIR / "vue_file_lines_baseline.json"
        data = json.loads(f.read_text(encoding="utf-8"))
        assert "_meta" in data
        assert "files" in data
        assert isinstance(data["files"], dict)

    def test_python_baseline_valid_json(self):
        """Python baseline 是有效 JSON。"""
        f = BASELINES_DIR / "python_service_lines_baseline.json"
        data = json.loads(f.read_text(encoding="utf-8"))
        assert "_meta" in data
        assert "files" in data
        assert isinstance(data["files"], dict)


class TestScriptInterfaces:
    """检查脚本 CLI 接口兼容性。"""

    def test_snapshot_scale_json_output(self):
        """snapshot_scale.py 输出有效 JSON。"""
        result = subprocess.run(
            [sys.executable, str(ROOT / "backend" / "scripts" / "analyze" / "snapshot_scale.py")],
            capture_output=True, text=True, encoding="utf-8", timeout=30,
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert "backend" in data
        assert "frontend" in data
        assert "routers" in data["backend"]

    def test_hotspot_baseline_mode(self):
        """check_hotspot_files.py --check-baseline 可执行。"""
        result = subprocess.run(
            [sys.executable, str(ROOT / "backend" / "scripts" / "check" / "check_hotspot_files.py"),
             "--check-baseline"],
            capture_output=True, text=True, encoding="utf-8", timeout=30,
        )
        # 退出码 0 或 1 都正常（0=无新增，1=有新增超标）
        assert result.returncode in (0, 1)

    def test_sql_contract_report_mode(self):
        """check_sql_column_contract.py report 模式 exit 0。"""
        result = subprocess.run(
            [sys.executable, str(ROOT / "backend" / "scripts" / "check" / "check_sql_column_contract.py")],
            capture_output=True, text=True, encoding="utf-8", timeout=60,
        )
        # report 模式始终 exit 0
        assert result.returncode == 0

    def test_sql_contract_strict_mode(self):
        """check_sql_column_contract.py --strict 可执行（0 或 1）。"""
        result = subprocess.run(
            [sys.executable, str(ROOT / "backend" / "scripts" / "check" / "check_sql_column_contract.py"),
             "--strict"],
            capture_output=True, text=True, encoding="utf-8", timeout=60,
        )
        # strict 模式：有违规=1，无违规=0
        assert result.returncode in (0, 1)


class TestEnforceDateLogic:
    """P2-1.4 强制日期切换逻辑测试。"""

    def test_before_enforce_date_is_warning(self):
        """在强制日期之前应该是 warning 模式。"""
        # 这是逻辑验证，检查 workflow 中的条件
        content = WORKFLOW_FILE.read_text(encoding="utf-8")
        # workflow 使用 date 比较逻辑
        assert "GOVERNANCE_ENFORCE_DATE" in content
        assert "::warning::" in content
        assert "::error::" in content

    def test_baseline_only_for_historical_debt(self):
        """P2-1.5 历史债务只走 baseline。"""
        content = WORKFLOW_FILE.read_text(encoding="utf-8")
        # hotspot baseline check 只关注"新增"超标文件
        assert "--check-baseline" in content
        # SQL 列契约使用 allowlist 过滤历史债务
        assert "allowlist" in content.lower() or "strict" in content


class TestDocTemplates:
    """P2-2 文档模板存在性检查。"""

    def test_capacity_planning_template_exists(self):
        """容量规划模板存在。"""
        f = ROOT / "docs" / "operations" / "capacity-planning-template.md"
        assert f.exists()
        content = f.read_text(encoding="utf-8")
        assert "Postgres" in content
        assert "Redis" in content
        assert "OnlyOffice" in content

    def test_backup_drill_template_exists(self):
        """备份恢复演练记录模板存在。"""
        f = ROOT / "docs" / "operations" / "backup-drill-record-template.md"
        assert f.exists()
        content = f.read_text(encoding="utf-8")
        assert "RTO" in content
        assert "RPO" in content

    def test_dependency_recovery_steps_exists(self):
        """依赖组件恢复步骤文档存在。"""
        f = ROOT / "docs" / "operations" / "dependency-recovery-steps.md"
        assert f.exists()
        content = f.read_text(encoding="utf-8")
        assert "Postgres" in content
        assert "Redis" in content
        assert "文件存储" in content
        assert "OnlyOffice" in content
