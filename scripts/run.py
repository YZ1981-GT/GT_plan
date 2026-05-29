"""统一脚本入口 — scripts/ 目录 dispatcher。

用法：
    python scripts/run.py e2e-smoke          # YG4001 最小样本 smoke
    python scripts/run.py e2e-batch          # 九家样本批量上传
    python scripts/run.py e2e-full           # 全流程深度验证
    python scripts/run.py e2e-curl           # YG36 端到端 HTTP
    python scripts/run.py lint-api           # Vue 硬编码 API 路径检查
    python scripts/run.py lint-signature     # signature_level 残留检查
    python scripts/run.py lint-seed          # seed JSON schema 验证
    python scripts/run.py lint-spec          # spec 文档引用验证
    python scripts/run.py lint-deadlink      # 前端 API 死链检查
    python scripts/run.py diag-yg2101       # B3 性能诊断
    python scripts/run.py gen-deps          # 服务依赖图
    python scripts/run.py gen-bindings      # 附注 bindings.json
    python scripts/run.py gen-report-seed   # 报表种子提取
    python scripts/run.py build-mineru      # MinerU Docker 构建
    python scripts/run.py list              # 列出所有可用命令

设计原则：
- 不合并各脚本代码（保持独立可维护）
- 仅做 dispatcher（subprocess 调用）
- 统一入口减少记忆负担
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = Path(__file__).resolve().parent

# Python 路径
PYTHON = str(ROOT / ".venv" / "Scripts" / "python.exe") if (ROOT / ".venv" / "Scripts" / "python.exe").exists() else "python"

COMMANDS = {
    "e2e-smoke": ("python", "scripts/e2e_yg4001_smoke.py"),
    "e2e-batch": ("python", "scripts/e2e_9_companies_batch.py"),
    "e2e-full": ("python", "scripts/e2e_full_pipeline_validation.py"),
    "e2e-curl": ("python", "scripts/e2e_http_curl.py"),
    "lint-api": ("bash", "scripts/check-api-hardcode.sh"),
    "lint-signature": ("python", "scripts/check_signature_level_usage.py"),
    "lint-seed": ("python", "scripts/validate_seed_files.py"),
    "lint-spec": ("python", "scripts/validate_spec_references.py"),
    "lint-deadlink": ("node", "scripts/dead-link-check.js"),
    "diag-yg2101": ("python", "scripts/b3_diag_yg2101.py"),
    "gen-deps": ("python", "scripts/gen_service_deps.py"),
    "gen-bindings": ("python", "scripts/generate_note_template_bindings.py"),
    "gen-report-seed": ("python", "scripts/extract_report_seed.py"),
    "build-mineru": ("bash", "scripts/build-mineru.sh"),
}


def list_commands():
    print("可用命令：")
    print()
    for name, (runtime, path) in sorted(COMMANDS.items()):
        exists = "✓" if (ROOT / path).exists() else "✗"
        print(f"  {exists} {name:20s} → {runtime} {path}")
    print()
    print(f"用法: python scripts/run.py <command> [args...]")


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("list", "--help", "-h"):
        list_commands()
        return 0

    cmd = sys.argv[1]
    extra_args = sys.argv[2:]

    if cmd not in COMMANDS:
        print(f"未知命令: {cmd}", file=sys.stderr)
        print(f"用 'python scripts/run.py list' 查看可用命令", file=sys.stderr)
        return 1

    runtime, script_path = COMMANDS[cmd]
    full_path = ROOT / script_path

    if not full_path.exists():
        print(f"脚本不存在: {full_path}", file=sys.stderr)
        return 1

    if runtime == "python":
        cmd_line = [PYTHON, str(full_path)] + extra_args
    elif runtime == "bash":
        cmd_line = ["bash", str(full_path)] + extra_args
    elif runtime == "node":
        cmd_line = ["node", str(full_path)] + extra_args
    else:
        cmd_line = [runtime, str(full_path)] + extra_args

    print(f"[run] {' '.join(cmd_line)}")
    result = subprocess.run(cmd_line, cwd=str(ROOT))
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
