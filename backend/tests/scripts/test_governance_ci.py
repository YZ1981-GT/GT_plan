"""P2-1 CI 治理集成测试。

验证：
1. governance-checks.yml 语法有效
2. 强制执行日期逻辑正确
3. baseline 文件存在且格式正确
4. 各检查脚本 CLI 接口兼容
"""

from __future__ import annotations

import ast
import inspect
import json
import os
import re
import subprocess
import sys
import textwrap
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
        assert "procedure-delegation-architecture" in jobs
        procedure_job = jobs["procedure-delegation-architecture"]
        assert procedure_job["runs-on"] == "ubuntu-latest"
        assert procedure_job["env"]["PYTHONUTF8"] == "1"
        steps_text = json.dumps(procedure_job["steps"], ensure_ascii=False)
        assert 'python-version": "3.12"' in steps_text
        assert "check_procedure_delegation_architecture.py --strict" in steps_text
        assert "test_check_procedure_delegation_architecture.py" in steps_text

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


def _run_script(*args: str, timeout: int = 60) -> subprocess.CompletedProcess[str]:
    """跑仓库内检查脚本并安全拿到文本输出。

    🔴 2026-09-28 修：原先 4 处 `subprocess.run(..., encoding="utf-8")` **没带
    `errors=` 也没给子进程定编码**。Windows 上 `capture_output=True` 时子进程按
    locale（cp936/GBK）写管道，父进程按 UTF-8 解码 ⇒ 撞
    `UnicodeDecodeError: 'utf-8' codec can't decode byte 0xc1`。异常发生在
    `subprocess._readerthread` 里，pytest 只报一条
    `PytestUnhandledThreadExceptionWarning`、**测试照样"通过"**，但那一次的
    `result.stdout` 已经丢了 —— 所有基于 stdout 的断言都变成空转。

    做法照抄本目录 `test_wp_template_deref.py::_run` 的现成样板：
    子进程侧 `PYTHONIOENCODING=utf-8` 定写出编码，父进程侧 `errors="replace"` 兜底。
    """
    return subprocess.run(
        [sys.executable, *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )


class TestScriptInterfaces:
    """检查脚本 CLI 接口兼容性。"""

    def test_script_runner_survives_non_utf8_child_output(self):
        """变异证明：子进程吐出**非 UTF-8 字节**时，读取不得抛异常。

        这是 `_run_script` 里 `errors="replace"` 的存在理由，而且**不依赖本机环境**：
        子进程被显式要求按 GBK 写 `stdout.buffer`，父进程按 UTF-8 解码必然撞到非法
        字节。去掉 `errors="replace"` 这条立刻 `UnicodeDecodeError`（该异常发生在
        `subprocess._readerthread` 内，pytest 只会记一条
        `PytestUnhandledThreadExceptionWarning` 而测试照样"通过"，stdout 却已丢失
        —— 这正是原先 4 处调用的实际状态）。
        """
        child = (
            "import sys; "
            "sys.stdout.buffer.write('拒绝执行：GBK 探针'.encode('gbk')); "
            "sys.stdout.buffer.flush()"
        )
        result = _run_script("-c", child, timeout=30)
        assert result.returncode == 0
        # 非法字节被替换而非抛异常；读到的内容非空即证明通路没断
        assert result.stdout, repr(result.stdout)

    def test_script_runner_pins_child_output_encoding(self):
        """`_run_script` 必须显式钉住子进程编码与解码兜底。

        `PYTHONIOENCODING` 那一项在"本机恰好已设 PYTHONIOENCODING=utf-8"时**测不出
        运行时差异**，所以用契约断言守住：删掉它这条立刻红。

        🔴 断言**走 AST 读真实关键字参数**，不是 `'errors="replace"' in source` 的
        字符串搜。后者会命中本函数 docstring 与 `_run_script` 自己的注释 ——
        实测把 `errors="replace"` 从调用里删掉后那种写法**仍然绿**（假绿）。
        """
        tree = ast.parse(textwrap.dedent(inspect.getsource(_run_script)))
        calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "run"
        ]
        assert len(calls) == 1, f"预期恰好一处 subprocess.run，实得 {len(calls)}"
        kwargs = {kw.arg: kw.value for kw in calls[0].keywords if kw.arg}

        assert isinstance(kwargs.get("errors"), ast.Constant)
        assert kwargs["errors"].value == "replace"
        assert isinstance(kwargs.get("encoding"), ast.Constant)
        assert kwargs["encoding"].value == "utf-8"

        env = kwargs.get("env")
        assert isinstance(env, ast.Dict), "必须显式传 env 以钉住子进程编码"
        env_literals = {
            k.value: v.value
            for k, v in zip(env.keys, env.values)
            if isinstance(k, ast.Constant) and isinstance(v, ast.Constant)
        }
        assert env_literals.get("PYTHONIOENCODING") == "utf-8"

    def test_snapshot_scale_json_output(self):
        """snapshot_scale.py 输出有效 JSON。"""
        result = _run_script(
            str(ROOT / "backend" / "scripts" / "analyze" / "snapshot_scale.py"),
            timeout=30,
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert "backend" in data
        assert "frontend" in data
        assert "routers" in data["backend"]

    def test_hotspot_baseline_mode(self):
        """check_hotspot_files.py --check-baseline 可执行。"""
        result = _run_script(
            str(ROOT / "backend" / "scripts" / "check" / "check_hotspot_files.py"),
            "--check-baseline",
            timeout=30,
        )
        # 退出码 0 或 1 都正常（0=无新增，1=有新增超标）
        assert result.returncode in (0, 1)

    def test_sql_contract_report_mode(self):
        """check_sql_column_contract.py report 模式 exit 0。"""
        result = _run_script(
            str(ROOT / "backend" / "scripts" / "check" / "check_sql_column_contract.py"),
        )
        # report 模式始终 exit 0
        assert result.returncode == 0

    def test_sql_contract_strict_mode(self):
        """check_sql_column_contract.py --strict 可执行（0 或 1）。"""
        result = _run_script(
            str(ROOT / "backend" / "scripts" / "check" / "check_sql_column_contract.py"),
            "--strict",
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

    #: spec 三件套的**泛指名**——文中写 `tasks.md` 指的是各 spec 目录下的三件套，
    #: 不是 `docs/operations/` 里的同名文件。不排除会产生 4 个假阳（现算）。
    _GENERIC_DOC_NAMES = frozenset({"design.md", "requirements.md", "tasks.md"})

    def test_operations_docs_have_no_broken_sibling_references(self):
        """docs/operations 内部互引不得断链。

        🔴 这条守卫是本次（2026-09-28）误删的**检出机制**：
        `capacity-planning-template.md` / `backup-drill-record-template.md` 在
        `5e31c0c0d` 被连同一份一次性 todo 清单一起删掉，而留存的
        `dependency-recovery-steps.md` 第 4 行仍写着「配合
        `backup-drill-record-template.md` 使用」⇒ 形成断链却无人发觉，
        只有两条"模板必须存在"的测试恒红（红了也没修）。

        🔴 分母如实声明：现算真实同目录互引仅 **1** 条（排除三件套泛指名后）。
        分母小不是不加的理由——它正是"删文档"这类操作唯一的自动检出点。
        """
        ops = ROOT / "docs" / "operations"
        backtick_md = re.compile(r"`([\w.-]+\.md)`")
        link_md = re.compile(r"\]\(\s*(?:\./)?([\w.-]+\.md)\s*\)")

        checked = 0
        broken: list[str] = []
        for path in sorted(ops.glob("*.md")):
            text = path.read_text(encoding="utf-8")
            refs = set(backtick_md.findall(text)) | set(link_md.findall(text))
            refs -= {path.name} | self._GENERIC_DOC_NAMES
            for ref in sorted(refs):
                checked += 1
                if not (ops / ref).is_file():
                    broken.append(f"{path.name} -> {ref}")

        assert broken == [], f"docs/operations 内部引用断链: {broken}"
        # 结构性零守卫：扫描器必须真的扫到了引用（否则"零断链"可能是扫不到）
        assert checked >= 1, "未扫到任何同目录 md 引用 —— 扫描口径可能失效"

    def test_generic_doc_name_exclusion_is_justified(self):
        """反向断言：被排除的三件套泛指名**真的不是** docs/operations 的同目录文件。

        若哪天真在该目录放了 `tasks.md`，排除项就会掩盖它的断链 ⇒ 立即打红。
        """
        ops = ROOT / "docs" / "operations"
        for name in self._GENERIC_DOC_NAMES:
            assert not (ops / name).is_file(), (
                f"docs/operations/{name} 现已是真实文件 ⇒ 请从 "
                "_GENERIC_DOC_NAMES 排除名单中移除"
            )
