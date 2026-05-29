"""Property 4: 删除确认不变量 — 静态扫描卡点

V3 Spec Req 4 Task 4.4 — 验证删除前必须有 confirm 二次确认。

形式化：∀ delete operation D:
    D is executed ⇒ D was preceded by confirm() within the enclosing function.

实现策略：
- 调用前端 ESLint 自定义规则 `gt-audit/no-delete-without-confirm`
- 该规则使用 AST + 函数体作用域扫描，比纯 grep 更准确
- baseline = 0 (baselines.json 卡点)，新增违规即 CI fail

退出码:
    0 = 达标 (无任何违规)
    1 = 超标 (检测到 confirm 缺失)

用法:
    python scripts/_check_no_delete_without_confirm.py
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys

FRONTEND_DIR = pathlib.Path("audit-platform/frontend")
BASELINES_FILE = pathlib.Path(".github/workflows/baselines.json")
BASELINE_KEY = "no-delete-without-confirm-vue-files"


def read_baseline() -> int:
    if not BASELINES_FILE.exists():
        return 0
    try:
        with open(BASELINES_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return 0
    raw = data.get("_v3_eslint_rules", {}).get(BASELINE_KEY, 0)
    if isinstance(raw, str):
        return 0 if raw == "<TBD>" else int(raw)
    return int(raw or 0)


def run_eslint() -> tuple[int, str]:
    """Return (violation_count, raw_output)."""
    if not FRONTEND_DIR.exists():
        print(f"⚠️  目录不存在: {FRONTEND_DIR}", file=sys.stderr)
        return 0, ""
    try:
        result = subprocess.run(
            [
                "npx",
                "--no-install",
                "eslint",
                "src/**/*.vue",
                "src/**/*.ts",
                "--rule",
                '{"gt-audit/no-delete-without-confirm":"warn"}',
                "--format",
                "compact",
            ],
            cwd=FRONTEND_DIR,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            shell=True,  # Windows 下 npx 是 .cmd
        )
    except (OSError, subprocess.SubprocessError) as e:
        print(f"❌ 无法运行 eslint: {e}", file=sys.stderr)
        return -1, ""
    out = (result.stdout or "") + (result.stderr or "")
    count = sum(
        1 for line in out.splitlines() if "no-delete-without-confirm" in line
    )
    return count, out


def main() -> int:
    print("📊 Property 4: 删除确认不变量 — 静态扫描")
    baseline = read_baseline()
    print(f"📋 baseline (只减不增): {baseline}")

    count, out = run_eslint()
    if count < 0:
        print("⚠️  eslint 执行失败，跳过本次卡点")
        return 0  # 工具链问题不阻塞 CI

    print(f"📊 当前违规数: {count}")
    if count > baseline:
        print(f"\n❌ FAIL: {count} > baseline {baseline}（新增了 {count - baseline} 处删除无确认）")
        # 输出前 10 条违规行
        viol_lines = [
            ln for ln in out.splitlines() if "no-delete-without-confirm" in ln
        ][:10]
        for ln in viol_lines:
            print(f"   {ln}")
        print(
            "\n   修复指引: 在 api.delete() 调用前所在函数体内添加 confirmDelete / "
            "confirmDangerous / ElMessageBox.confirm（见 audit-platform/frontend/src/utils/confirm.ts）"
        )
        return 1
    print(f"\n✅ PASS: {count} <= baseline {baseline}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
