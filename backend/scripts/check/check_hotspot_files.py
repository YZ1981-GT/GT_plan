"""热点文件 pull 检测 + 超大文件 baseline 治理。

原始功能（pre-commit hook）：
- staged 文件含 git_hotspot_files.txt 中的项 + 本地 behind > 0 即拒
- single 模式仅警告；multi 模式阻断 commit

P1-1 扩展功能（baseline 治理）：
- 扫描 Vue 文件行数，与 baseline 对比
- 扫描 Python service 文件行数，与 baseline 对比
- 对指定专项治理文件标记跟踪
- 输出 JSON baseline 文件供 CI 消费

用法：
    # 原始 pre-commit 模式
    python backend/scripts/check/check_hotspot_files.py file1 file2 ...

    # baseline 生成/检查模式
    python backend/scripts/check/check_hotspot_files.py --baseline
    python backend/scripts/check/check_hotspot_files.py --check-baseline

退出码：
    0 = 通过 / baseline 无膨胀
    1 = 阻断 / 发现超标文件
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HOTSPOT_LIST = ROOT / "backend" / "scripts" / "git_hotspot_files.txt"

# --- Baseline 配置 ---
BASELINE_DIR = ROOT / "backend" / "scripts" / "check" / "baselines"
VUE_BASELINE_FILE = BASELINE_DIR / "vue_file_lines_baseline.json"
PYTHON_SERVICE_BASELINE_FILE = BASELINE_DIR / "python_service_lines_baseline.json"

# 扫描路径
VUE_SCAN_DIRS = [
    ROOT / "audit-platform" / "frontend" / "src",
]
PYTHON_SERVICE_SCAN_DIRS = [
    ROOT / "backend" / "app" / "services",
]

# Vue 文件行数阈值（超过此行数记入 baseline）
VUE_LINE_THRESHOLD = 300
# Python service 文件行数阈值
PYTHON_SERVICE_LINE_THRESHOLD = 400

# 专项治理文件（P1-1.4）
SPECIAL_GOVERNANCE_FILES = {
    "LedgerPenetration.vue": {
        "reason": "明细账穿透组件，复杂度极高，含月小计/余额/辅助账多模式",
        "target_lines": 800,
        "owner": "待指定",
    },
    "DisclosureEditor.vue": {
        "reason": "附注编辑器，富文本+表格混合编辑，功能密集",
        "target_lines": 600,
        "owner": "待指定",
    },
    "TrialBalance.vue": {
        "reason": "试算平衡表主视图，含科目映射/调整/穿透多功能",
        "target_lines": 600,
        "owner": "待指定",
    },
    "ReportView.vue": {
        "reason": "报表视图，已完成瘦身（2944→965 行），需守住 HARD_CAP 1110",
        "target_lines": 1110,
        "owner": "待指定",
    },
}

# Python 专项治理文件
SPECIAL_GOVERNANCE_PY = {
    "consol_disclosure_service.py": {
        "reason": "合并附注服务，1736 行，待拆分",
        "target_lines": 800,
        "owner": "待指定",
    },
    "migration_runner.py": {
        "reason": "迁移运行器，1026 行，待拆分",
        "target_lines": 600,
        "owner": "待指定",
    },
}


def count_lines(filepath: Path) -> int:
    """统计文件行数。"""
    try:
        return len(filepath.read_text(encoding="utf-8", errors="replace").splitlines())
    except (OSError, UnicodeDecodeError):
        return 0


def scan_vue_files() -> dict[str, int]:
    """扫描所有 Vue 文件行数，返回超过阈值的文件。"""
    results: dict[str, int] = {}
    for scan_dir in VUE_SCAN_DIRS:
        if not scan_dir.exists():
            continue
        for vue_file in scan_dir.rglob("*.vue"):
            lines = count_lines(vue_file)
            if lines >= VUE_LINE_THRESHOLD:
                rel_path = str(vue_file.relative_to(ROOT)).replace("\\", "/")
                results[rel_path] = lines
    return dict(sorted(results.items(), key=lambda x: -x[1]))


def scan_python_services() -> dict[str, int]:
    """扫描 Python service 文件行数，返回超过阈值的文件。"""
    results: dict[str, int] = {}
    for scan_dir in PYTHON_SERVICE_SCAN_DIRS:
        if not scan_dir.exists():
            continue
        for py_file in scan_dir.rglob("*.py"):
            if py_file.name.startswith("_") and py_file.name != "__init__.py":
                continue
            lines = count_lines(py_file)
            if lines >= PYTHON_SERVICE_LINE_THRESHOLD:
                rel_path = str(py_file.relative_to(ROOT)).replace("\\", "/")
                results[rel_path] = lines
    return dict(sorted(results.items(), key=lambda x: -x[1]))


def find_special_governance_status(
    vue_data: dict[str, int], py_data: dict[str, int]
) -> dict:
    """检查专项治理文件当前状态。"""
    status: dict = {"vue": {}, "python": {}}

    for filename, meta in SPECIAL_GOVERNANCE_FILES.items():
        found = False
        for path, lines in vue_data.items():
            if path.endswith(filename):
                status["vue"][filename] = {
                    "path": path,
                    "current_lines": lines,
                    "target_lines": meta["target_lines"],
                    "over_target": lines > meta["target_lines"],
                    "reason": meta["reason"],
                    "owner": meta["owner"],
                }
                found = True
                break
        if not found:
            # 搜索整个前端目录
            for scan_dir in VUE_SCAN_DIRS:
                for vue_file in scan_dir.rglob(filename):
                    lines = count_lines(vue_file)
                    rel_path = str(vue_file.relative_to(ROOT)).replace("\\", "/")
                    status["vue"][filename] = {
                        "path": rel_path,
                        "current_lines": lines,
                        "target_lines": meta["target_lines"],
                        "over_target": lines > meta["target_lines"],
                        "reason": meta["reason"],
                        "owner": meta["owner"],
                    }
                    found = True
                    break

    for filename, meta in SPECIAL_GOVERNANCE_PY.items():
        for path, lines in py_data.items():
            if path.endswith(filename):
                status["python"][filename] = {
                    "path": path,
                    "current_lines": lines,
                    "target_lines": meta["target_lines"],
                    "over_target": lines > meta["target_lines"],
                    "reason": meta["reason"],
                    "owner": meta["owner"],
                }
                break

    return status


def generate_baseline() -> dict:
    """生成完整 baseline JSON。"""
    vue_data = scan_vue_files()
    py_data = scan_python_services()
    governance = find_special_governance_status(vue_data, py_data)

    baseline = {
        "_meta": {
            "description": "超大文件行数 baseline，用于 CI 检测膨胀",
            "vue_threshold": VUE_LINE_THRESHOLD,
            "python_service_threshold": PYTHON_SERVICE_LINE_THRESHOLD,
            "usage": "python backend/scripts/check/check_hotspot_files.py --check-baseline",
        },
        "vue_files": vue_data,
        "python_services": py_data,
        "special_governance": governance,
        "summary": {
            "vue_over_threshold": len(vue_data),
            "python_over_threshold": len(py_data),
            "vue_top5": dict(list(vue_data.items())[:5]),
            "python_top5": dict(list(py_data.items())[:5]),
        },
    }
    return baseline


def save_baseline() -> None:
    """保存 baseline 到 JSON 文件。"""
    BASELINE_DIR.mkdir(parents=True, exist_ok=True)

    vue_data = scan_vue_files()
    py_data = scan_python_services()

    vue_baseline = {
        "_meta": {
            "threshold": VUE_LINE_THRESHOLD,
            "description": "Vue 文件行数 baseline（超过阈值的文件）",
        },
        "files": vue_data,
    }

    py_baseline = {
        "_meta": {
            "threshold": PYTHON_SERVICE_LINE_THRESHOLD,
            "description": "Python service 文件行数 baseline（超过阈值的文件）",
        },
        "files": py_data,
    }

    VUE_BASELINE_FILE.write_text(
        json.dumps(vue_baseline, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    PYTHON_SERVICE_BASELINE_FILE.write_text(
        json.dumps(py_baseline, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # 同时输出完整 baseline 到 stdout
    full = generate_baseline()
    print(json.dumps(full, ensure_ascii=False, indent=2))
    print(f"\n✅ Baseline 已保存:")
    print(f"   Vue: {VUE_BASELINE_FILE.relative_to(ROOT)}")
    print(f"   Python: {PYTHON_SERVICE_BASELINE_FILE.relative_to(ROOT)}")
    print(f"   Vue 超标文件: {len(vue_data)} 个")
    print(f"   Python 超标文件: {len(py_data)} 个")


def check_baseline() -> int:
    """对比当前与 baseline，报告膨胀。退出码 1 = 有新增超标文件。"""
    if not VUE_BASELINE_FILE.exists() or not PYTHON_SERVICE_BASELINE_FILE.exists():
        print("⚠️  Baseline 文件不存在，请先运行 --baseline 生成", file=sys.stderr)
        return 1

    vue_baseline = json.loads(VUE_BASELINE_FILE.read_text(encoding="utf-8"))
    py_baseline = json.loads(PYTHON_SERVICE_BASELINE_FILE.read_text(encoding="utf-8"))

    current_vue = scan_vue_files()
    current_py = scan_python_services()

    baseline_vue_files = set(vue_baseline.get("files", {}).keys())
    baseline_py_files = set(py_baseline.get("files", {}).keys())

    # 检查新增超标文件
    new_vue = set(current_vue.keys()) - baseline_vue_files
    new_py = set(current_py.keys()) - baseline_py_files

    # 检查已有文件膨胀（行数增长超 10%）
    grown_vue: list[str] = []
    for path, lines in current_vue.items():
        if path in vue_baseline.get("files", {}):
            old_lines = vue_baseline["files"][path]
            if lines > old_lines * 1.1:  # 膨胀超 10%
                grown_vue.append(f"  {path}: {old_lines} → {lines} (+{lines - old_lines})")

    grown_py: list[str] = []
    for path, lines in current_py.items():
        if path in py_baseline.get("files", {}):
            old_lines = py_baseline["files"][path]
            if lines > old_lines * 1.1:
                grown_py.append(f"  {path}: {old_lines} → {lines} (+{lines - old_lines})")

    # 检查专项治理文件
    governance = find_special_governance_status(current_vue, current_py)
    governance_violations: list[str] = []
    for category in ("vue", "python"):
        for filename, info in governance.get(category, {}).items():
            if info.get("over_target"):
                governance_violations.append(
                    f"  ❌ {filename}: {info['current_lines']} 行 (目标 ≤{info['target_lines']})"
                )

    has_issues = bool(new_vue or new_py or grown_vue or grown_py)

    if new_vue:
        print(f"🆕 新增 Vue 超标文件 ({len(new_vue)} 个):", file=sys.stderr)
        for f in sorted(new_vue):
            print(f"  {f}: {current_vue[f]} 行", file=sys.stderr)

    if new_py:
        print(f"🆕 新增 Python 超标文件 ({len(new_py)} 个):", file=sys.stderr)
        for f in sorted(new_py):
            print(f"  {f}: {current_py[f]} 行", file=sys.stderr)

    if grown_vue:
        print(f"📈 Vue 文件膨胀 (>10%):", file=sys.stderr)
        for line in grown_vue:
            print(line, file=sys.stderr)

    if grown_py:
        print(f"📈 Python 文件膨胀 (>10%):", file=sys.stderr)
        for line in grown_py:
            print(line, file=sys.stderr)

    if governance_violations:
        print(f"\n🎯 专项治理文件状态:", file=sys.stderr)
        for line in governance_violations:
            print(line, file=sys.stderr)

    if not has_issues and not governance_violations:
        print("✅ 无新增超标文件，无膨胀", file=sys.stderr)

    return 1 if has_issues else 0


# === 原始 pre-commit 功能 ===


def load_hotspot_files() -> set[str]:
    if not HOTSPOT_LIST.exists():
        return set()
    return {
        line.strip()
        for line in HOTSPOT_LIST.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    }


def get_git_mode() -> str:
    return os.environ.get("GIT_MODE", "single").lower()


def get_behind_count() -> int:
    try:
        branch_result = subprocess.run(
            ["git", "symbolic-ref", "--short", "HEAD"],
            capture_output=True, text=True, encoding="utf-8", timeout=10,
        )
        branch = branch_result.stdout.strip()
        if not branch:
            return 0
        result = subprocess.run(
            ["git", "rev-list", "--count", f"HEAD..origin/{branch}"],
            capture_output=True, text=True, encoding="utf-8", timeout=10,
        )
        s = result.stdout.strip()
        return int(s) if s.isdigit() else 0
    except Exception:
        return 0


def normalize(path: str) -> str:
    return path.replace("\\", "/").lstrip("./")


def main_precommit(files: list[str]) -> int:
    """原始 pre-commit 检测逻辑。"""
    if not files:
        return 0

    hotspot = load_hotspot_files()
    if not hotspot:
        return 0

    mode = get_git_mode()
    has_hotspot = [f for f in files if normalize(f) in hotspot]
    if not has_hotspot:
        return 0

    behind = get_behind_count()
    if behind == 0:
        return 0

    msg = (
        f"❌ 检测到热点文件改动 + 本地 behind 远程 {behind} commit:\n"
        + "\n".join(f"   - {f}" for f in has_hotspot)
        + "\n\n"
        + "   建议先 `git pull --rebase origin <branch>` 再 commit\n"
        + "   避免覆盖他人改动（INDEX.md / memory.md 等高频冲突文件）"
    )

    if mode == "multi":
        print(msg, file=sys.stderr)
        print(f"   GIT_MODE=multi → 阻断 commit", file=sys.stderr)
        return 1
    else:
        print(msg, file=sys.stderr)
        print(f"   GIT_MODE={mode} → 仅警告，未阻断", file=sys.stderr)
        return 0


def main() -> int:
    args = sys.argv[1:]

    if "--baseline" in args:
        save_baseline()
        return 0
    elif "--check-baseline" in args:
        return check_baseline()
    else:
        return main_precommit(args)


if __name__ == "__main__":
    raise SystemExit(main())
