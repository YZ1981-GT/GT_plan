"""clean checkout 总验（spec `onlyoffice-sheet-open-via-published-artifact` task 5.6）。

═══ 为什么需要这个脚本 ═══

本 spec 的交付物跨四层：生成物（JSON）· 后端（reader / resolver / 门）· 前端（三态 / 文案）·
守卫（契约 / 变异 / 清单）。它们各自有测试，但**没有任何单一入口**回答这个问题：

> 「在一个干净的 clone 里，这些交付物真的都在、且都能跑起来吗？」

「本地全绿」不等于「干净检出可用」—— 本仓为此付过代价（spec 标 100% 但产物未入库；
已提交代码引用未提交模块）。本脚本把六项检查串成一个可重复执行的入口。

═══ 六项检查（spec 5.6 逐条）═══

1. **生成物 `--check`**：三个生成器（sheet bindings / legacy ledger / 前端契约）都必须通过；
2. **交付物入库**：本 spec 的全部关键文件必须被 `git ls-files` 跟踪；
3. **路由注册**：`entry-identity` 必须真的挂在应用路由表上（不是只写了 router）；
4. **后端测试**：本 spec 的守卫选集必须全绿；
5. **前端定向测试**：三态 + 文案 + 契约守卫必须全绿；
6. **行数门**：本 spec 触碰的文件都必须在门内。

═══ 用法 ═══

```powershell
python backend/scripts/check/check_sheet_open_clean_checkout.py
python backend/scripts/check/check_sheet_open_clean_checkout.py --skip-tests   # 只查静态项
```

退出码：0 = 全过；1 = 有检查失败；2 = 环境缺失（比如不在仓库根跑）。
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
BACKEND = REPO / "backend"
FRONTEND = REPO / "audit-platform" / "frontend"

#: 本 spec 的关键交付物（必须入库）。
DELIVERABLES = (
    # 生成物
    "backend/data/workpaper_sync_sheet_open_bindings.json",
    "backend/data/workpaper_sync_legacy_onlyoffice_callers.json",
    "audit-platform/frontend/src/components/workpaper/sync/workpaperSyncContract.generated.ts",
    # 生成器
    "backend/scripts/gen/generate_workpaper_sync_sheet_open_bindings.py",
    "backend/scripts/gen/generate_legacy_onlyoffice_caller_ledger.py",
    # 后端实现
    "backend/app/services/workpaper_sync/sheet_open_bindings.py",
    "backend/app/services/workpaper_sync/sheet_published_artifact.py",
    "backend/app/services/workpaper_sync/descriptor_view_identity.py",
    "backend/app/routers/_wp_onlyoffice_legacy_url_gate.py",
    # 前端实现
    "audit-platform/frontend/src/components/workpaper/composables/onlyOfficeEntryConfig.ts",
    # 守卫
    "backend/tests/workpaper_sync/test_sheet_open_bindings.py",
    "backend/tests/workpaper_sync/test_sheet_open_binding_resolver.py",
    "backend/tests/workpaper_sync/test_sheet_published_artifact.py",
    "backend/tests/workpaper_sync/test_sheet_descriptor_view_identity.py",
    "backend/tests/workpaper_sync/test_sheet_entry_identity_endpoint.py",
    "backend/tests/workpaper_sync/test_sheet_entry_identity_router_shape.py",
    "backend/tests/workpaper_sync/test_sheet_legacy_gate_binding_states.py",
    "backend/tests/workpaper_sync/test_sheet_legacy_caller_ledger.py",
    "backend/tests/workpaper_sync/test_sheet_open_unit_contract.py",
    "backend/tests/workpaper_sync/test_sheet_open_mutation_suite.py",
    "audit-platform/frontend/src/components/workpaper/composables/__tests__/onlyOfficeEntryConfig.spec.ts",
    "audit-platform/frontend/src/components/workpaper/composables/__tests__/onlyOfficeEntryConfigContract.spec.ts",
    "audit-platform/frontend/src/components/workpaper/__tests__/GtOnlyOfficeSheet.spec.ts",
)

#: 三个生成器（相对仓库根）。
GENERATORS = (
    "backend/scripts/gen/generate_workpaper_sync_sheet_open_bindings.py",
    "backend/scripts/gen/generate_legacy_onlyoffice_caller_ledger.py",
    "backend/scripts/gen/generate_workpaper_sync_frontend_contract.py",
)

#: 后端守卫选集。
BACKEND_TESTS = (
    "backend/tests/workpaper_sync/test_sheet_open_bindings.py",
    "backend/tests/workpaper_sync/test_sheet_open_binding_resolver.py",
    "backend/tests/workpaper_sync/test_sheet_published_artifact.py",
    "backend/tests/workpaper_sync/test_sheet_descriptor_view_identity.py",
    "backend/tests/workpaper_sync/test_sheet_entry_identity_endpoint.py",
    "backend/tests/workpaper_sync/test_sheet_entry_identity_router_shape.py",
    "backend/tests/workpaper_sync/test_sheet_legacy_gate_binding_states.py",
    "backend/tests/workpaper_sync/test_sheet_legacy_caller_ledger.py",
    "backend/tests/workpaper_sync/test_sheet_open_unit_contract.py",
)

#: 变异残留靶点：各轮变异脚本**实际注入过**的精确字符串 → 标签。
#:
#: 🔴 只列「注入后**不可能**是任何人手写」的形态。合法但语义错的变异（如
#: `document_scope="single_sheet"`）在正常代码里也可能出现，不能作为残留判据。
#:
#: 为什么需要这道检查：变异脚本的 `finally` 会被 Ctrl+C 绕过。本轮实测踩到 5.3 的
#: M4 残留（`if (value !== undefined && value !== null) return 'pending'`）让 3 条
#: 前端用例红了很久 —— 而那是「变异残留」而非「功能坏了」，极易误诊。
MUTATION_RESIDUE = {
    "if (value !== undefined && value !== null) return 'pending'": "5.3-M4 未知状态当 pending",
    "(lambda **k: None)(": "lambda 吞 target",
    "(lambda **k: k['target_sheet'])(": "lambda 透传",
    "if (false && identity.reason !== null)": "5.3-M2 migrated 回退旧式",
    "if False and target_sheet:": "5.4-M3 整册带 target 放行",
    "if False and target:": "5.4-M3 整册带 target 放行",
    "if False:  # mutated": "变异标记",
    "# 变异：回退模板（本 spec 明禁）": "5.4-M04 模板回退",
    '"effective_entry_id": "docx/gt-a16-bundle"': "5.4-M02 伪造父级",
    "getattr(artifact, 'project_id', project_id)": "5.1-M2 从 artifact 反推 project",
    "path = None  # 变异：吞掉边界拒绝": "5.1-M1 边界被吞",
}

#: 前端定向测试。
FRONTEND_SPECS = (
    "src/components/workpaper/composables/__tests__/onlyOfficeEntryConfig.spec.ts",
    "src/components/workpaper/composables/__tests__/onlyOfficeEntryConfigContract.spec.ts",
    "src/components/workpaper/__tests__/GtOnlyOfficeSheet.spec.ts",
)


@dataclass
class Result:
    name: str
    ok: bool
    detail: str = ""

    def render(self) -> str:
        mark = "OK  " if self.ok else "FAIL"
        line = f"[{mark}] {self.name}"
        return f"{line}\n        {self.detail}" if self.detail else line


def _run(cmd: list[str], *, cwd: Path, extra_pythonpath: Path | None = None) -> tuple[int, str]:
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    if extra_pythonpath is not None:
        # 🔴 必须显式设 PYTHONPATH：probe 脚本放在仓库根、而 `app` 包在 backend/ 下。
        # 只靠 `cwd=BACKEND` 不够（脚本路径在仓库根 ⇒ sys.path[0] 是仓库根）。
        existing = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = (
            f"{extra_pythonpath}{os.pathsep}{existing}" if existing else str(extra_pythonpath)
        )
    proc = subprocess.run(
        cmd, cwd=cwd, capture_output=True, text=True, errors="replace", env=env
    )
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


# ── 检查 1：生成物 --check ───────────────────────────────────────────────────


def check_generators() -> Result:
    failures: list[str] = []
    for rel in GENERATORS:
        rc, out = _run([sys.executable, rel, "--check"], cwd=REPO)
        if rc != 0:
            failures.append(
                f"{rel}: {out.strip()[:300]}\n"
                f"        （改了调用方 / 源文件后必须重跑该生成器的 --apply —— 这是预期行为）"
            )
    if failures:
        return Result("生成物 --check（三个生成器）", False, "\n        ".join(failures))
    return Result("生成物 --check（三个生成器）", True, f"{len(GENERATORS)} 个全部一致")


# ── 检查 2：交付物入库 ──────────────────────────────────────────────────────


def check_tracked() -> Result:
    missing: list[str] = []
    for rel in DELIVERABLES:
        rc, _ = _run(["git", "ls-files", "--error-unmatch", rel], cwd=REPO)
        if rc != 0:
            missing.append(rel)
    if missing:
        return Result(
            "交付物入库（git ls-files）",
            False,
            f"未跟踪 {len(missing)} 个：\n        " + "\n        ".join(missing),
        )
    return Result("交付物入库（git ls-files）", True, f"{len(DELIVERABLES)} 个全部已跟踪")


# ── 检查 3：路由注册 ────────────────────────────────────────────────────────


def check_route_registration() -> Result:
    """`entry-identity` 必须真的挂在**应用**路由表上。

    🔴 只查 `wp_sync_router.router.routes` 不够：模块级 router 存在但没注册到
    `router_registry` 时，生产恒 404（本仓踩过：E1 三个识别端点建好 3 个月没登记）。
    所以这里 import 真实 app 并扫 `app.routes`。
    """
    probe = REPO / "tmp_sheet_open_route_probe.py"
    probe.write_text(
        '''import json
import sys

from app.main import app

needle = "/sync/entry-identity"
hits = [
    {"path": r.path, "methods": sorted(getattr(r, "methods", []) or [])}
    for r in app.routes
    if needle in str(getattr(r, "path", ""))
]
print(json.dumps(hits, ensure_ascii=False))
''',
        encoding="utf-8",
    )
    try:
        rc, out = _run(
            [sys.executable, str(probe)], cwd=BACKEND, extra_pythonpath=BACKEND
        )
    finally:
        probe.unlink(missing_ok=True)
    if rc != 0:
        return Result("路由注册（真实 app.routes）", False, f"探测失败：{out.strip()[-400:]}")
    # 🔴 `app.main` 导入时会有 JWT 弱密钥等**警告**打到 stderr ⇒ 不能取最后一行。
    # 找第一个以 `[` 开头的行（probe 只输出一个 JSON 数组）。
    payload_line = next(
        (ln for ln in out.splitlines() if ln.strip().startswith("[")), None
    )
    if payload_line is None:
        return Result(
            "路由注册（真实 app.routes）",
            False,
            f"输出里找不到 JSON 数组：{out.strip()[-400:]}",
        )
    try:
        hits = json.loads(payload_line)
    except ValueError:
        return Result(
            "路由注册（真实 app.routes）",
            False,
            f"JSON 无法解析：{payload_line[:300]}",
        )
    if not hits:
        return Result(
            "路由注册（真实 app.routes）", False, "app.routes 里找不到 /sync/entry-identity"
        )
    return Result(
        "路由注册（真实 app.routes）", True, f"{hits[0]['path']} methods={hits[0]['methods']}"
    )


# ── 检查 4：后端测试 ────────────────────────────────────────────────────────


def check_backend_tests() -> Result:
    rc, out = _run(
        [sys.executable, "-m", "pytest", *BACKEND_TESTS, "-q", "-p", "no:playwright",
         "--no-header", "--tb=no", "-rf"],
        cwd=REPO,
    )
    tail = [ln for ln in out.splitlines() if ln.strip()][-1:] or ["(无输出)"]
    if rc != 0:
        failed = [ln for ln in out.splitlines() if ln.startswith(("FAILED", "ERROR"))]
        return Result(
            "后端测试（守卫选集）",
            False,
            f"{tail[0]}\n        " + "\n        ".join(failed[:8]),
        )
    return Result("后端测试（守卫选集）", True, tail[0])


# ── 检查 5：前端定向测试 ────────────────────────────────────────────────────


def check_frontend_tests() -> Result:
    if not (FRONTEND / "node_modules" / "vitest" / "vitest.mjs").is_file():
        return Result(
            "前端定向测试",
            False,
            "缺 node_modules/vitest —— 干净检出需先 `npm ci`（本项在无依赖环境下无法执行）",
        )
    rc, out = _run(
        ["node", "node_modules/vitest/vitest.mjs", "run", *FRONTEND_SPECS, "--reporter=basic"],
        cwd=FRONTEND,
    )
    tail = [ln for ln in out.splitlines() if "Tests" in ln][-1:] or ["(无 Tests 摘要)"]
    if rc != 0:
        return Result("前端定向测试", False, tail[0])
    return Result("前端定向测试", True, tail[0])


# ── 检查 6：行数门 ──────────────────────────────────────────────────────────


def check_file_size() -> Result:
    rc, out = _run(
        [sys.executable, "backend/scripts/check/check_file_size.py", *DELIVERABLES],
        cwd=REPO,
    )
    if rc != 0:
        offenders = [ln.strip() for ln in out.splitlines() if "膨胀" in ln or "超限" in ln]
        return Result(
            "行数门（本 spec 触碰的文件）", False,
            "\n        ".join(offenders[:6]) or out.strip()[-400:],
        )
    return Result("行数门（本 spec 触碰的文件）", True, f"{len(DELIVERABLES)} 个全部在门内")


# ── 检查 7：变异残留 ────────────────────────────────────────────────────────


def check_mutation_residue() -> Result:
    """本 spec 触碰的生产文件里不得残留变异代码。

    🔴 这道检查独立于变异脚本（后者会被 Ctrl+C 绕过 finally）。命中任何一条都说明
    上一次变异没有恢复干净 —— 那不是「功能坏了」，是「工作树脏了」。
    """
    findings: list[str] = []
    for rel in DELIVERABLES:
        if not rel.endswith((".py", ".ts", ".vue")):
            continue
        # 🔴 只查**生产代码**：测试文件里提到变异形态是正当的（它们是判据的说明文字 /
        # 变异套件的靶点定义）。首版把 DELIVERABLES 全扫 ⇒ 4 处误报全是测试文件。
        if rel.startswith("backend/tests/") or "/__tests__/" in rel:
            continue
        path = REPO / rel
        if not path.is_file():
            continue
        body = path.read_text(encoding="utf-8")
        for needle, label in MUTATION_RESIDUE.items():
            if needle in body:
                lineno = body[: body.index(needle)].count("\n") + 1
                findings.append(f"{rel}:{lineno} [{label}]")
    if findings:
        return Result(
            "变异残留（生产代码）",
            False,
            "发现残留（上一次变异未恢复干净）：\n        " + "\n        ".join(findings),
        )
    prod_count = sum(
        1 for rel in DELIVERABLES
        if rel.endswith((".py", ".ts", ".vue"))
        and not rel.startswith("backend/tests/")
        and "/__tests__/" not in rel
    )
    return Result(
        "变异残留（生产代码）",
        True,
        f"{len(MUTATION_RESIDUE)} 类靶点 × {prod_count} 个生产文件，无残留",
    )


# ── 主流程 ──────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip-tests", action="store_true",
        help="只跑静态检查（生成物 / 入库 / 路由 / 行数门），跳过测试",
    )
    args = parser.parse_args(argv)

    if not (REPO / ".git").exists():
        print(f"[FAIL] 不在仓库根（缺 .git）：{REPO}", file=sys.stderr)
        return 2

    results: list[Result] = [
        check_generators(),
        check_tracked(),
        check_route_registration(),
        # 变异残留必须**始终**检查（不受 --skip-tests 影响）：它是最容易误诊的一类问题。
        check_mutation_residue(),
    ]
    if not args.skip_tests:
        results.append(check_backend_tests())
        results.append(check_frontend_tests())
    results.append(check_file_size())

    print("═" * 78)
    print("sheet 打开链路 clean checkout 总验（spec task 5.6）")
    print("═" * 78)
    for result in results:
        print(result.render())

    failed = [r for r in results if not r.ok]
    print("─" * 78)
    if failed:
        print(f"结果：{len(failed)} / {len(results)} 项失败")
        for r in failed:
            print(f"  · {r.name}")
        return 1
    print(f"结果：{len(results)} / {len(results)} 项全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
