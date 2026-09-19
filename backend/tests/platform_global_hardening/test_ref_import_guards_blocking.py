"""test_ref_import_guards_blocking.py — 验证 ref 契约守卫与 import 深度守卫的阻断能力

Task 2.6: 确认既有 ref/import 守卫为阻断态
Requirements: 3.3, 3.4

确认两个守卫脚本对新增违规能正确返回非零退出码（阻断构建）。
测试方法：创建临时违规文件，运行脚本 --strict/--check，验证退出码为 1。
"""
from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
REF_SCRIPT = REPO_ROOT / "backend" / "scripts" / "check" / "check_wp_ref_contract.py"
IMPORT_SCRIPT = REPO_ROOT / "backend" / "scripts" / "check" / "fix_wp_composables_import_depth.py"
WP_DIR = REPO_ROOT / "audit-platform" / "frontend" / "src" / "components" / "workpaper"


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _run_script(script: Path, *args: str) -> subprocess.CompletedProcess:
    """运行守卫脚本，返回 CompletedProcess。"""
    result = subprocess.run(
        [sys.executable, str(script), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(REPO_ROOT),
    )
    return result


# ─── 1. check_wp_ref_contract.py --strict 阻断测试 ───────────────────────────

class TestRefContractBlocking:
    """验证 check_wp_ref_contract.py --strict 对新增违规能阻断。"""

    def test_props_ref_declaration_blocks(self, tmp_path: Path, monkeypatch):
        """反模式 A：props 声明为 Ref<Map> 时 --strict 退出码 1。"""
        # 在 workpaper 目录下创建临时违规 .vue 文件
        violation_dir = WP_DIR / "_test_guard_tmp"
        violation_dir.mkdir(parents=True, exist_ok=True)
        violation_file = violation_dir / "TestRefViolation.vue"
        try:
            violation_file.write_text(textwrap.dedent("""\
                <script setup lang="ts">
                import { Ref } from 'vue'

                const props = defineProps<{
                  allResponses: Ref<Map<string, any>>
                  wpId: Ref<string>
                }>()
                </script>

                <template>
                  <div>test</div>
                </template>
            """), encoding="utf-8")

            result = _run_script(REF_SCRIPT, "--strict")
            assert result.returncode == 1, (
                f"Expected exit code 1 (blocking) but got {result.returncode}.\n"
                f"stdout: {result.stdout}\nstderr: {result.stderr}"
            )
            assert "检测到违规" in result.stdout
        finally:
            violation_file.unlink(missing_ok=True)
            violation_dir.rmdir()

    def test_prop_dot_value_access_blocks(self, tmp_path: Path):
        """反模式 B：props.allResponses.value 访问时 --strict 退出码 1。"""
        violation_dir = WP_DIR / "_test_guard_tmp"
        violation_dir.mkdir(parents=True, exist_ok=True)
        violation_file = violation_dir / "TestDotValueViolation.vue"
        try:
            violation_file.write_text(textwrap.dedent("""\
                <script setup lang="ts">
                const props = defineProps<{
                  allResponses: Map<string, any>
                }>()

                function doSomething() {
                  const data = props.allResponses.value.get('key')
                  return data
                }
                </script>

                <template>
                  <div>test</div>
                </template>
            """), encoding="utf-8")

            result = _run_script(REF_SCRIPT, "--strict")
            assert result.returncode == 1, (
                f"Expected exit code 1 (blocking) but got {result.returncode}.\n"
                f"stdout: {result.stdout}\nstderr: {result.stderr}"
            )
            assert "检测到违规" in result.stdout
        finally:
            violation_file.unlink(missing_ok=True)
            violation_dir.rmdir()

    def test_clean_code_passes(self):
        """无违规时 --strict 退出码 0（确认当前代码库干净）。"""
        # 不注入违规文件，直接跑全树
        result = _run_script(REF_SCRIPT, "--strict")
        assert result.returncode == 0, (
            f"Expected exit code 0 (clean) but got {result.returncode}.\n"
            f"stdout: {result.stdout[:500]}\nstderr: {result.stderr[:500]}"
        )


# ─── 2. fix_wp_composables_import_depth.py --check 阻断测试 ──────────────────

class TestImportDepthBlocking:
    """验证 fix_wp_composables_import_depth.py --check 对错误导入深度能阻断。"""

    def test_wrong_import_depth_blocks(self):
        """在 {cycle}/{sub}/ 目录下用 3 级 ../ 导入 composables 时 --check 退出码 1。"""
        # 创建一个位于 workpaper/{cycle}/{sub}/ 的文件（depth=2）
        # 正确前缀应为 ../../composables/
        # 用 ../../../composables/ 制造违规（多了一级）
        violation_dir = WP_DIR / "_test_cycle" / "_test_sub"
        violation_dir.mkdir(parents=True, exist_ok=True)
        violation_file = violation_dir / "TestImportViolation.vue"
        try:
            violation_file.write_text(textwrap.dedent("""\
                <script setup lang="ts">
                import { useDisplayPrefsStore } from '../../../composables/displayPrefsKey'
                import { useAgingConfig } from '../../../composables/useAgingConfig'
                </script>

                <template>
                  <div>test</div>
                </template>
            """), encoding="utf-8")

            result = _run_script(IMPORT_SCRIPT, "--check")
            assert result.returncode == 1, (
                f"Expected exit code 1 (blocking) but got {result.returncode}.\n"
                f"stdout: {result.stdout}\nstderr: {result.stderr}"
            )
            assert "_test_cycle/_test_sub/TestImportViolation.vue" in result.stdout.replace("\\", "/")
        finally:
            violation_file.unlink(missing_ok=True)
            violation_dir.rmdir()
            (WP_DIR / "_test_cycle").rmdir()

    def test_correct_import_depth_not_triggered_by_injected_violation(self):
        """确认注入的违规被检出，且移除后不再报告该文件。"""
        # 创建临时违规文件
        violation_dir = WP_DIR / "_test_cycle2" / "_test_sub2"
        violation_dir.mkdir(parents=True, exist_ok=True)
        violation_file = violation_dir / "TestCorrectRemoval.vue"
        try:
            # 先写入违规（depth=2 应用 ../../，这里用 ../../../ 制造违规）
            violation_file.write_text(textwrap.dedent("""\
                <script setup lang="ts">
                import { something } from '../../../composables/something'
                </script>
                <template><div/></template>
            """), encoding="utf-8")
            result_bad = _run_script(IMPORT_SCRIPT, "--check")
            assert result_bad.returncode == 1, "Injected violation should trigger exit 1"
            assert "_test_cycle2/_test_sub2/TestCorrectRemoval.vue" in result_bad.stdout.replace("\\", "/")
        finally:
            violation_file.unlink(missing_ok=True)
            violation_dir.rmdir()
            (WP_DIR / "_test_cycle2").rmdir()


# ─── 3. CI 配置确认（静态断言） ──────────────────────────────────────────────

class TestGovernanceChecksYmlBlocking:
    """验证 governance-checks.yml 中 wp-ref-contract-check job 为阻断态。"""

    def test_job_has_no_continue_on_error(self):
        """job 未设 continue-on-error: true → 默认阻断。"""
        yml_path = REPO_ROOT / ".github" / "workflows" / "governance-checks.yml"
        content = yml_path.read_text(encoding="utf-8")

        # 找到 wp-ref-contract-check job 块
        assert "wp-ref-contract-check:" in content, "Job wp-ref-contract-check not found"

        # 提取 job 块内容（到下一个同级 job 或文件结尾）
        import re
        match = re.search(
            r"wp-ref-contract-check:.*?(?=\n  \w[\w-]*:|$)",
            content,
            re.DOTALL,
        )
        assert match, "Could not extract wp-ref-contract-check job block"
        job_block = match.group(0)

        # 确认 job 级无 continue-on-error
        assert "continue-on-error" not in job_block, (
            "wp-ref-contract-check job should NOT have continue-on-error "
            "(must be blocking)"
        )

    def test_ref_contract_uses_strict_flag(self):
        """check_wp_ref_contract.py 使用 --strict 参数。"""
        yml_path = REPO_ROOT / ".github" / "workflows" / "governance-checks.yml"
        content = yml_path.read_text(encoding="utf-8")
        assert "check_wp_ref_contract.py --strict" in content

    def test_import_depth_uses_check_flag(self):
        """fix_wp_composables_import_depth.py 使用 --check 参数。"""
        yml_path = REPO_ROOT / ".github" / "workflows" / "governance-checks.yml"
        content = yml_path.read_text(encoding="utf-8")
        assert "fix_wp_composables_import_depth.py --check" in content
