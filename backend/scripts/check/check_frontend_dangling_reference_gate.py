# -*- coding: utf-8 -*-
"""前端「悬空引用 / 缺失导出」门禁 —— 构建期查不出、运行时才炸的那一类。

2026-09-03 一次普查抓到两批缺陷，共同点是四层静态检查全绿、只有运行时才暴露：

* 缺失导出（34 条）：6 个 useK*FormulaEngine.ts 收敛到共享模型时删掉了
  parseNum / calcAuditedAmount 两个导出，消费方还在 import ⇒ esbuild 依赖预打包
  直接失败、vite dev server 起不来。既有的 5 个 K 单测/PBT 同时变红，但没人看。
* 悬空引用（13 处）：引用了既未声明也未导入的名字。esbuild 与浏览器一样把未解析
  标识符当全局，所以构建期零报错，运行时才抛 "X is not a function"。典型：
  PrefillDiffPanel.vue 只 import 了 useDisplayPrefsStore 工厂却从未建实例，
  模板渲染就调 prefs.fmt ⇒ 面板一打开白屏；useH3CrossSheet.ts 把判定收敛到
  useH3Adjustment 的单一真源后删了本地副本、漏了 import ⇒ 调整分录汇总一算就抛。

两类共同病因是重构惯性：收敛到单一真源时删掉本地副本，漏了最后一步 import。
方向是对的、代码看着很干净 —— 只有可执行判据能拦住。
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[3]
FRONTEND = _REPO / "audit-platform" / "frontend"
GATE_ESLINTRC = FRONTEND / "eslintrc.dangling-refs.cjs"
AUTO_IMPORTS_DTS = FRONTEND / "src" / "auto-imports.d.ts"
EXEMPTIONS = _REPO / "backend" / "data" / "frontend_dangling_reference_exemptions.json"
REGISTER = _REPO / "backend" / "data" / "frontend_broken_import_register.json"


class GateError(RuntimeError):
    """门禁自身无法运行（缺文件 / 工具跑不起来）。禁 fail-open。"""

def load_auto_import_globals() -> set[str]:
    """自动导入的全局名，现读 unplugin-auto-import 的生成物。

    不手抄那 75 个名字：手抄即第二真源，插件的 imports 清单一改，门禁就开始误报/漏报。
    """
    if not AUTO_IMPORTS_DTS.is_file():
        raise GateError(
            f"缺 {AUTO_IMPORTS_DTS} —— 它是 unplugin-auto-import 的生成物，"
            "跑一次 vite dev/build 会重生成。没有它无法区分自动导入与真悬空引用"
        )
    return set(re.findall(r"const (\w+):", AUTO_IMPORTS_DTS.read_text(encoding="utf-8")))


def load_exemptions() -> list[dict[str, Any]]:
    if not EXEMPTIONS.is_file():
        raise GateError(f"缺豁免表 {EXEMPTIONS}")
    doc = json.loads(EXEMPTIONS.read_text(encoding="utf-8"))
    rows = doc.get("type_only_globals") or []
    for row in rows:
        if not row.get("name") or not row.get("reason") or not row.get("source"):
            raise GateError(f"豁免条目必须同时有 name / source / reason：{row}")
    return rows


def iter_source_files() -> list[Path]:
    src = FRONTEND / "src"
    return [p for p in list(src.rglob("*.ts")) + list(src.rglob("*.vue")) if p.is_file()]

def assert_exemptions_are_never_called(
    exemptions: list[dict[str, Any]], files: list[Path]
) -> list[dict[str, Any]]:
    """反滥用判据：豁免名不得出现在调用位置。

    豁免表最容易退化成「打红就加一行」。这条把它变成**可核验的声明**：想拿豁免掩盖一个
    真的悬空函数时，`Name(` / `new Name(` 会被抓到并打红。
    """
    names = [row["name"] for row in exemptions]
    hits: list[dict[str, Any]] = []
    for path in files:
        text = path.read_text(encoding="utf-8", errors="replace")
        for name in names:
            for form in (name + "(", "new " + name + "("):
                idx = text.find(form)
                while idx != -1:
                    before = text[idx - 1] if idx > 0 else " "
                    # 前一个字符是标识符字符时说明命中的是别的名字的尾部（如 XEventListener(）
                    if not (before.isalnum() or before in "_$."):
                        hits.append({
                            "name": name,
                            "form": form,
                            "file": str(path.relative_to(FRONTEND)).replace("\\", "/"),
                            "line": text[:idx].count("\n") + 1,
                        })
                    idx = text.find(form, idx + 1)
    return hits

def run_eslint_no_undef(out_json: Path) -> list[dict[str, Any]]:
    """跑专用最小配置的 no-undef，返回逐条 finding。"""
    if not GATE_ESLINTRC.is_file():
        raise GateError(f"缺门禁专用 eslint 配置 {GATE_ESLINTRC}")
    cmd = [
        "npx", "eslint", "--no-eslintrc", "-c", GATE_ESLINTRC.name,
        "--ext", ".ts,.vue", "src", "-f", "json", "-o", str(out_json),
    ]
    proc = subprocess.run(
        cmd, cwd=str(FRONTEND), capture_output=True, text=True,
        encoding="utf-8", errors="replace", shell=True,
    )
    if not out_json.is_file():
        raise GateError(
            "eslint 没产出报告 —— 门禁无法判定（禁 fail-open）。\n"
            f"stdout={proc.stdout[-800:]}\nstderr={proc.stderr[-800:]}"
        )
    doc = json.loads(out_json.read_text(encoding="utf-8"))
    rows: list[dict[str, Any]] = []
    for entry in doc:
        for msg in entry.get("messages") or []:
            if msg.get("ruleId") != "no-undef":
                continue
            m = re.search(r"'([^']+)'", msg.get("message", ""))
            rows.append({
                "name": m.group(1) if m else "?",
                "file": entry["filePath"].replace("\\", "/").split("/frontend/")[-1],
                "line": msg.get("line"),
            })
    return rows

def run_vite_optimize(log: Path) -> dict[str, Any]:
    """跑 vite optimize —— 全量扫源码图，任何缺失导出即失败。无豁免。

    这条就是当初 dev server 起不来的那条报错，秒级可复现。
    """
    vite_bin = FRONTEND / "node_modules" / "vite" / "bin" / "vite.js"
    if not vite_bin.is_file():
        raise GateError(f"缺 {vite_bin} —— 先在 frontend 跑 npm install")
    proc = subprocess.run(
        ["node", str(vite_bin), "optimize", "--force"],
        cwd=str(FRONTEND), capture_output=True, text=True,
        encoding="utf-8", errors="replace", shell=True,
    )
    text = (proc.stdout or "") + (proc.stderr or "")
    log.write_text(text, encoding="utf-8")
    missing = re.findall(r'No matching export in "([^"]+)" for import "([^"]+)"', text)
    return {
        "exit_code": proc.returncode,
        "error_markers": text.count("[ERROR]"),
        "missing_export_count": len(missing),
        "missing_exports": [{"module": a, "name": b} for a, b in missing[:40]],
        "log": str(log),
    }

def classify(rows: list[dict[str, Any]], auto: set[str], exempt: set[str]) -> dict[str, Any]:
    """把 no-undef findings 分三桶。只有 `dangling` 桶算失败。"""
    buckets: dict[str, list[dict[str, Any]]] = {
        "auto_import": [], "type_only_exempt": [], "dangling": []
    }
    for row in rows:
        if row["name"] in auto:
            buckets["auto_import"].append(row)
        elif row["name"] in exempt:
            buckets["type_only_exempt"].append(row)
        else:
            buckets["dangling"].append(row)
    return buckets


# ═══════════════════════════════════════════════════════════════════════════
# 判据三：具名 import 必须在目标模块里真的有对应 export
# ═══════════════════════════════════════════════════════════════════════════
#
# 🔴 为什么不能只靠 `vite optimize`：变异 M14 实测证明它有洞。把
# `shared/plAdjudicationModel.ts` 的 `export function parseNum` 去掉 export 后，
# 6 个 K 引擎的 `import { parseNum } from './shared/plAdjudicationModel'` 断了，
# 而 optimize **不报**（它只在「消费方 → 引擎」那层扫出缺失导出，不查
# 「引擎 → 共享模型」这条边）。于是同一个病（2026-08-02 那次改瘦）换个位置就漏网。
#
# 本判据直接做静态交叉核验：逐个相对 import 解析目标模块的导出名集合。不依赖打包器，
# 秒级，且覆盖每一条边。
#
# 保守原则（宁漏勿误报）：只核验目标是 `.ts` 的边；目标含无法解析的 `export *` 时整块跳过；
# default / namespace import 不查。

#: `import { a } from 'x'` / `import type { a } from 'x'`（不含 `export ... from`）
#: 🔴 全部用 re.M 行首锚定、**不消费换行**。首版写成 `(?:^|\n)\s*...\s*`，尾部的
#: `\s*` 会把下一行的换行吃掉，于是**相邻的 export {} 语句只有第一条能匹配** ——
#: 实测 h7ListedDisclosureModel.ts 的 `export { emptyMovement, num, rawCell, setCell }`
#: 整条漏掉，被误报成 4 条断边。这是「正则消费边界」类缺陷，74→37→真实值三轮才收敛。
_IMPORT_RE = re.compile(
    r"^[ \t]*import\s+(?:type\s+)?\{([^}]*)\}[ \t]*from[ \t]*['\"]([^'\"]+)['\"]", re.M
)
_BRACE_EXPORT_RE = re.compile(
    r"^[ \t]*export\s+(?:type\s+)?\{([^}]*)\}[ \t]*(?:from[ \t]*['\"]([^'\"]+)['\"])?", re.M
)
_STAR_REEXPORT_RE = re.compile(
    r"^[ \t]*export[ \t]*\*[ \t]*(?:as\s+\w+[ \t]*)?from[ \t]*['\"]([^'\"]+)['\"]", re.M
)
_DECL_EXPORT_RE = re.compile(
    r"^[ \t]*export\s+(?:declare\s+)?(?:default\s+)?"
    r"(?:async\s+)?(?:function\*?|const|let|var|class|type|interface|enum|abstract\s+class)"
    r"\s+(\w+)", re.M
)


def _resolve_module(importer: Path, spec: str) -> Path | None:
    """解析相对 / `@/` import 到磁盘文件。

    🔴 返回 `None` 的语义**按 spec 形态分两种，不可混为一谈**（首版 docstring 写
    「解析不出返回 None（当作外部包，不查）」，那句话对相对/别名 spec 是错的，
    且已造成一次真实漏网 —— 见下）：

    * **裸 spec**（`vue` / `element-plus`）—— 真的是外部包，跳过是对的。
    * **相对 / `@/` spec 解析不出** —— 相对路径**不可能**是外部包，这就是
      「import 路径写错」这条断边本身。本函数仍返回 `None`，但**它不是本模块的
      判据范围**：调用方 `assert_named_imports_resolve` 只回答「目标模块解析到了、
      但没导出这个名字」，回答不了「目标模块根本解析不到」。

    后一问的**唯一真源**是前端既有守卫
    `src/__tests__/FrontendReferenceIntegrity.spec.ts`（helper
    `_helpers/frontendSourceScan.findBrokenModuleReferences`）：它用
    `computeStringMask` 排掉字符串字面量里的代码快照、用 `isResolvableSpecifier`
    区分裸/相对、`moduleExists` 试全套后缀与 index，并带 `KNOWN_DEAD_MODULE_FILES`
    逐条署名登记（「清单只减不增」）。该守卫已挂在 `governance-checks.yml`。
    **本门禁刻意不重实现一遍** —— 重实现的后果是两份判据强度不同的第二真源，
    弱的那份会给出虚假安全感（本门禁 2026-09-03 实测正是如此：
    `D2TabAnalysis.vue` 里一条 `../composables/useExcelIO`（真源在
    `@/composables/useExcelIO`）解析不到，被本函数当外部包静默跳过，
    而 `findBrokenModuleReferences` 能抓到）。改由 `assert_owner_guard_is_wired()`
    断言那个所有者守卫仍在 CI 里，防它被删后本门禁静默变窄。
    """
    if spec.startswith("@/"):
        base = FRONTEND / "src" / spec[2:]
    elif spec.startswith("."):
        base = (importer.parent / spec).resolve()
    else:
        return None
    # 🔴 不能用 with_suffix：它**替换**已有后缀，`./x.generated` 会被解析成 `x.ts`
    #    （首版实测造出「模块 import 自己」的假断边）。必须是**追加**后缀。
    cands = (
        base,
        base.parent / (base.name + ".ts"),
        base.parent / (base.name + ".vue"),
        base / "index.ts",
        base / "index.vue",
    )
    for cand in cands:
        if cand.is_file():
            return cand
    if base.suffix in (".ts", ".vue") and base.is_file():
        return base
    return None


def _names_in_brace(block: str) -> list[str]:
    """解析 `{ a, b as c, type d, default as e }` 里被引用的**源名**。"""
    out: list[str] = []
    for part in block.split(","):
        p = part.strip()
        if not p:
            continue
        p = re.sub(r"^type\s+", "", p)
        src = p.split(" as ")[0].strip()
        if src and re.fullmatch(r"\w+", src):
            out.append(src)
    return out

def module_exports(path: Path, _seen: set[Path] | None = None) -> set[str] | None:
    """模块导出名集合。export * 链解析不动时返回 None（调用方跳过，宁漏勿误报）。"""
    _seen = set() if _seen is None else _seen
    if path in _seen or path.suffix != ".ts":
        return None
    _seen.add(path)
    text = path.read_text(encoding="utf-8", errors="replace")
    names: set[str] = set(_DECL_EXPORT_RE.findall(text))
    for block, _spec in _BRACE_EXPORT_RE.findall(text):
        for part in block.split(","):
            piece = part.strip()
            if not piece:
                continue
            if piece.startswith("type "):
                piece = piece[5:].strip()
            exposed = piece.split(" as ")[-1].strip()
            if exposed and exposed.isidentifier():
                names.add(exposed)
    for spec in _STAR_REEXPORT_RE.findall(text):
        target = _resolve_module(path, spec)
        if target is None:
            return None
        inner = module_exports(target, _seen)
        if inner is None:
            return None
        names.update(inner)
    return names


#: 「相对/别名 spec 解析不到」这条判据的所有者守卫（见 `_resolve_module` docstring）。
#: 本门禁不重实现它，只断言它仍被 CI 真实调用 —— 否则删掉那一步就能让本门禁静默变窄。
OWNER_GUARD_SPEC = "src/__tests__/FrontendReferenceIntegrity.spec.ts"
OWNER_GUARD_HELPER = "findBrokenModuleReferences"
_WORKFLOW = _REPO / ".github" / "workflows" / "governance-checks.yml"


def assert_owner_guard_is_wired() -> dict[str, Any]:
    """断言「模块解析不到」判据的所有者守卫真实存在且真被 CI 调用。

    三条各自独立（任一被绕过都要打红）：
    1. 守卫文件在磁盘上；
    2. 它真的调用了 `findBrokenModuleReferences`（不是只 import 不调用 —— 那是
       additive 死代码形态）；
    3. CI workflow 里有一条 step 真的以 vitest 跑它（不是注释掉、不是只在名字里提）。
    """
    facts: dict[str, Any] = {
        "spec": OWNER_GUARD_SPEC,
        "spec_exists": False,
        "helper_invoked": False,
        "ci_step_present": False,
    }
    spec_path = FRONTEND / OWNER_GUARD_SPEC
    facts["spec_exists"] = spec_path.is_file()
    if facts["spec_exists"]:
        text = spec_path.read_text(encoding="utf-8", errors="replace")
        facts["helper_invoked"] = bool(
            re.search(r"\b" + OWNER_GUARD_HELPER + r"\s*\(", text)
        )
    if _WORKFLOW.is_file():
        for line in _WORKFLOW.read_text(encoding="utf-8", errors="replace").splitlines():
            bare = line.strip()
            if bare.startswith("#"):
                continue
            if "vitest" in bare and OWNER_GUARD_SPEC.split("/")[-1] in bare:
                facts["ci_step_present"] = True
                break
    return facts


def assert_named_imports_resolve(files: list[Path]) -> list[dict[str, Any]]:
    """逐条相对具名 import 核验目标模块真的导出了它。返回断掉的边。"""
    broken: list[dict[str, Any]] = []
    cache: dict[Path, set[str] | None] = {}
    for path in files:
        text = path.read_text(encoding="utf-8", errors="replace")
        for block, spec in _IMPORT_RE.findall(text):
            target = _resolve_module(path, spec)
            if target is None or target.suffix != ".ts":
                continue
            if target not in cache:
                cache[target] = module_exports(target)
            exported = cache[target]
            if exported is None:
                continue
            for name in _names_in_brace(block):
                if name == "default" or name in exported:
                    continue
                broken.append({
                    "importer": str(path.relative_to(FRONTEND)).replace("\\", "/"),
                    "target": str(target.relative_to(FRONTEND)).replace("\\", "/"),
                    "name": name,
                })
    return broken


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="前端悬空引用 / 缺失导出门禁")
    parser.add_argument("--skip-optimize", action="store_true",
                        help="只跑 no-undef 那条（本地快速回归用；CI 不要加）")
    parser.add_argument("--json", dest="json_path", default=None)
    args = parser.parse_args(argv)

    auto = load_auto_import_globals()
    exemptions = load_exemptions()
    exempt_names = {row["name"] for row in exemptions}
    files = iter_source_files()

    abuse = assert_exemptions_are_never_called(exemptions, files)
    owner_guard = assert_owner_guard_is_wired()
    broken_imports = assert_named_imports_resolve(files)
    reg_doc = json.loads(REGISTER.read_text(encoding="utf-8")) if REGISTER.is_file() else {}
    register = reg_doc.get("entries") or []
    for row in register:
        for field in ("importer", "target", "name", "owner", "reason"):
            if not row.get(field):
                raise GateError(
                    "已知断边登记必须五项齐全（importer/target/name/owner/reason）："
                    + json.dumps(row, ensure_ascii=False)
                )
    reg_keys = {(r["importer"], r["target"], r["name"]) for r in register}
    live_keys = {(r["importer"], r["target"], r["name"]) for r in broken_imports}
    new_breakage = [r for r in broken_imports
                    if (r["importer"], r["target"], r["name"]) not in reg_keys]
    stale_register = [r for r in register
                     if (r["importer"], r["target"], r["name"]) not in live_keys]
    eslint_json = _REPO / "tmp_dangling_gate_eslint.json"
    rows = run_eslint_no_undef(eslint_json)
    buckets = classify(rows, auto, exempt_names)

    optimize: dict[str, Any] = {"skipped": True}
    if not args.skip_optimize:
        optimize = run_vite_optimize(_REPO / "tmp_dangling_gate_optimize.log")
    failures: list[str] = []
    missing_owner = [k for k in ("spec_exists", "helper_invoked", "ci_step_present")
                     if not owner_guard.get(k)]
    if missing_owner:
        failures.append(
            "「模块解析不到」判据的所有者守卫失守：" + ", ".join(missing_owner)
            + f"（{OWNER_GUARD_SPEC}）。本门禁的第三判据只覆盖「目标解析到了但没导出这个名字」，"
            "覆盖不了「目标模块根本解析不到」—— 后者的唯一真源是那个守卫。它一旦被删或"
            "不再被 CI 调用，本门禁会静默变窄（2026-09-03 实测漏过一条真断边）"
        )
    if abuse:
        failures.append(
            "豁免表被滥用：以下豁免名出现在调用位置，说明它是**值**不是类型，"
            "正确做法是补 import 或补定义，不是加进豁免表 —— " + json.dumps(abuse[:8], ensure_ascii=False)
        )
    if new_breakage:
        failures.append(
            str(len(new_breakage)) + " 条**新**具名 import 断边（目标模块无对应 export）。"
            "这一类构建期不报、运行时才抛；vite optimize 对「引擎→共享模型」这层边有洞"
            "（变异 M14 实测），故本判据独立存在。明细见 report.new_breakage"
        )
    if stale_register:
        failures.append(
            str(len(stale_register)) + " 条已知断边登记已失效（那些边已经修好了）——"
            "必须把它们从 frontend_broken_import_register.json 删掉。这条防止登记表退化成"
            "垃圾场，也保证表里每一行都还是真问题。明细见 report.stale_register"
        )
    if buckets["dangling"]:
        failures.append(
            str(len(buckets["dangling"])) + " 处悬空引用（引用了既未声明也未导入的名字，"
            "构建期不报、运行时抛 X is not a function）"
        )
    if not args.skip_optimize:
        if optimize.get("missing_export_count"):
            failures.append(
                str(optimize["missing_export_count"]) + " 条缺失导出（vite optimize），"
                "dev server 会起不来"
            )
        if optimize.get("error_markers"):
            failures.append("vite optimize 报了 " + str(optimize["error_markers"]) + " 个 [ERROR]")

    report = {
        "gate": "frontend-dangling-reference/1",
        "auto_import_globals": len(auto),
        "exemptions": [row["name"] for row in exemptions],
        "exemption_abuse_hits": abuse,
        "owner_guard": owner_guard,
        "source_files_scanned": len(files),
        "broken_named_imports": len(broken_imports),
        "register_entries": len(register),
        "new_breakage": new_breakage,
        "stale_register": stale_register,
        "no_undef_total": len(rows),
        "buckets": {k: len(v) for k, v in buckets.items()},
        "dangling": buckets["dangling"],
        "vite_optimize": optimize,
        "failures": failures,
        "verdict": "passed" if not failures else "failed",
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.json_path:
        Path(args.json_path).write_text(text, encoding="utf-8")
    print(text)
    return 0 if not failures else 1


if __name__ == "__main__":  # pragma: no cover - CLI
    raise SystemExit(main())
