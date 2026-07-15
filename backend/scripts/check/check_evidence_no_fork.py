#!/usr/bin/env python3
"""
check_evidence_no_fork.py — Evidence Governance 禁止分叉 CI 守卫

强制 `attachment-ocr-ai-evidence-governance-hardening` 治理层 **只委托** 八项
既有引擎（AttachmentService / UnifiedOCRService / KnowledgeIndexService /
AiContentLog(Service) / ACNR / StalePropagationEngine / DeliverableService /
ArchiveOrchestrator），禁止复制、分叉或影子实现。

清单单一真源：backend/data/evidence_governance/adapter_contract_manifest.json

扫描 governance_scan_roots（默认 backend/app/services|routers/evidence_governance）
下的 .py，拦截三类分叉反模式：

  A. 重定义 canonical class/函数名（如再写一个 `class AttachmentService` /
     `def full_resolve` / `def invalidate`）。
  B. 复制引擎私有实现（fork_markers，如 `_paperless_uri` / `_bfs` /
     `_http_recognize` / `_vector_search` 等被搬进治理层）。
  C. 绕过引擎直连外部依赖（治理层直接 httpx 调 paperless / OCR / 向量库，
     而不是委托引擎）。

零依赖（仅 stdlib，含 ast）。显式 UTF-8 读写。

Usage:
    python check_evidence_no_fork.py            # 报告模式（退出码恒 0）
    python check_evidence_no_fork.py --strict   # 严格模式（CI 用，有违规退出码 1）

Feature: attachment-ocr-ai-evidence-governance-hardening
Task: 1.5
Requirements: R1, R5, R7, R8, R9, R11, R12, R15
"""
from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path

# ─── UTF-8 输出（Windows GBK 控制台防崩）───────────────────────────────────────
try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent.parent  # GT_plan/
MANIFEST_PATH = (
    PROJECT_ROOT
    / "backend"
    / "data"
    / "evidence_governance"
    / "adapter_contract_manifest.json"
)

# ─── C 类：绕过引擎直连外部依赖的 host 关键字 ──────────────────────────────────
# 治理层不得直接 HTTP 调这些外部端点；必须委托对应引擎。
FORBIDDEN_DIRECT_HOSTS = (
    "/api/documents/post_document",  # paperless 上传
    "/api/documents/",               # paperless 读取/搜索
    "/recognize",                    # OCR 服务容器
)


def load_manifest(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def collect_canonical_symbols(manifest: dict) -> set[str]:
    """canonical class 名 + canonical 模块级函数名（禁止在治理层重定义）。"""
    names: set[str] = set()
    for eng in manifest.get("engines", []):
        kind = eng.get("kind")
        if kind in ("class", "orm_model"):
            names.add(eng["symbol"])
        elif kind == "module":
            for fn in eng.get("required_functions", []):
                names.add(fn["name"])
    return names


def collect_fork_markers(manifest: dict) -> set[str]:
    markers: set[str] = set()
    for eng in manifest.get("engines", []):
        markers.update(eng.get("fork_markers", []))
    return markers


def scan_file(
    filepath: Path,
    canonical_symbols: set[str],
    fork_markers: set[str],
) -> list[dict]:
    """AST 扫描单文件，返回分叉命中列表。"""
    hits: list[dict] = []
    try:
        source = filepath.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return hits

    try:
        tree = ast.parse(source, filename=str(filepath))
    except SyntaxError as exc:  # 语法错也报出来，不静默
        hits.append(
            {"line": exc.lineno or 0, "kind": "SYNTAX_ERROR", "name": str(exc.msg)}
        )
        return hits

    for node in ast.walk(tree):
        # A + B：重定义 canonical 符号 / 复制引擎私有实现
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            name = node.name
            if name in canonical_symbols:
                hits.append(
                    {
                        "line": node.lineno,
                        "kind": "REDEFINE_CANONICAL",
                        "name": name,
                    }
                )
            elif name in fork_markers:
                hits.append(
                    {
                        "line": node.lineno,
                        "kind": "COPY_ENGINE_INTERNAL",
                        "name": name,
                    }
                )

    # C：绕过引擎直连外部依赖（字符串字面量含 forbidden host）
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            for host in FORBIDDEN_DIRECT_HOSTS:
                if host in node.value:
                    hits.append(
                        {
                            "line": getattr(node, "lineno", 0),
                            "kind": "BYPASS_ENGINE_DIRECT_CALL",
                            "name": host,
                        }
                    )
    return hits


def scan_roots(
    roots: list[Path],
    canonical_symbols: set[str],
    fork_markers: set[str],
) -> tuple[list[dict], int]:
    """扫描全部 governance 根，返回 (violations, files_scanned)。"""
    violations: list[dict] = []
    files_scanned = 0
    for root in roots:
        if not root.exists():
            continue
        for fpath in sorted(root.rglob("*.py")):
            if "__pycache__" in fpath.parts:
                continue
            files_scanned += 1
            hits = scan_file(fpath, canonical_symbols, fork_markers)
            if hits:
                rel = fpath.relative_to(PROJECT_ROOT).as_posix()
                violations.append({"file": rel, "hits": hits})
    return violations, files_scanned


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Evidence Governance 禁止分叉守卫"
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="严格模式（检出分叉退出码 1）",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=MANIFEST_PATH,
        help="adapter_contract_manifest.json 路径",
    )
    args = parser.parse_args()

    print("[Evidence No-Fork] 扫描治理层是否复制/分叉八项既有引擎...")
    print(f"  Manifest: {args.manifest}")

    if not args.manifest.exists():
        print(f"[FAIL] 清单不存在: {args.manifest}")
        return 1 if args.strict else 0

    manifest = load_manifest(args.manifest)
    canonical_symbols = collect_canonical_symbols(manifest)
    fork_markers = collect_fork_markers(manifest)

    roots = [
        PROJECT_ROOT / r for r in manifest.get("governance_scan_roots", [])
    ]
    print(f"  Scan roots: {manifest.get('governance_scan_roots', [])}")
    print(f"  Canonical symbols guarded: {len(canonical_symbols)}")
    print(f"  Fork markers guarded: {len(fork_markers)}")

    violations, files_scanned = scan_roots(roots, canonical_symbols, fork_markers)

    print(f"\n  Governance files scanned: {files_scanned}")
    print(f"  Files with fork violations: {len(violations)}")

    if violations:
        print("\n  [VIOLATION] 检测到治理层分叉/复制既有引擎：")
        for v in violations:
            print(f"    - {v['file']}:")
            for h in v["hits"]:
                print(f"        L{h['line']} [{h['kind']}] {h['name']}")
        print(
            "\n  修复：治理层只能通过 canonical import 委托引擎，删除复制/重定义/直连；"
            "\n  引擎契约见 adapter_contract_manifest.json。"
        )
        if args.strict:
            print(f"\n[FAIL] {len(violations)} 个治理文件包含分叉反模式。")
            return 1
    else:
        print("\n[OK] 治理层未复制/分叉任何既有引擎。")

    return 0


if __name__ == "__main__":
    sys.exit(main())
