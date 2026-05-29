"""Spec 四向覆盖矩阵生成器

扫描指定 spec 的三件套 + 集成测试，自动构建 Requirements ↔ Tasks ↔ Tests ↔ Properties 四向映射，
输出 markdown 表格，可嵌入 tasks.md 末尾或 docs/spec-coverage/{spec_id}.md。

数据来源：
  1. requirements.md：`### 需求 N` + `WHEN ... THEN ...` 编号（如 1.2 / 21.3）
  2. design.md：`### Property N: title` + `**Coverage: [Tested: test_xxx]**`
  3. tasks.md：`- [x] N.M task_text` + `_Requirements: x.y, z.w_`
  4. backend/tests/test_*{spec_keyword}*.py：函数 docstring `Validates: Property X / Requirement Y`

输出：
  - 横向 4 列：Requirement | Task | Test | Property
  - 末尾汇总：覆盖率统计 + 未覆盖项清单

用法：python build_spec_coverage_matrix.py {spec_id} [--output path]
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Windows console GBK 兼容
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
REPO_ROOT = BACKEND_DIR.parent
SPECS_DIR = REPO_ROOT / ".kiro" / "specs"
TESTS_DIR = BACKEND_DIR / "tests"


# ─── 解析 ────────────────────────────────────────────────────────────────
REQ_HEADER_RE = re.compile(r"^###\s+需求\s+(\d+)[:：]?\s*(.+?)$", re.MULTILINE)
REQ_AC_RE = re.compile(r"^\d+\.\s+(?:WHEN|IF|THE)", re.MULTILINE)
TASK_RE = re.compile(r"^\s*-\s+\[([ x*])\]\s+(\d+(?:\.\d+)?)\s+(.+?)$", re.MULTILINE)
TASK_REQ_REF_RE = re.compile(r"_Requirements:\s*([^_]+)_")
PROPERTY_RE = re.compile(r"^###\s+Property\s+(\d+):\s*(.+?)$", re.MULTILINE)
COVERAGE_RE = re.compile(
    r"\*\*Coverage:\s*\[(Tested|Pending|Skipped):\s*([^\]]+)\]\*\*"
)
PROP_VALIDATES_RE = re.compile(r"\*\*Validates:\s*([^\*]+?)\*\*")
TEST_FUNC_RE = re.compile(r"^(?:async\s+)?def\s+(test_\w+)\s*\(", re.MULTILINE)
TEST_VALIDATES_RE = re.compile(r"Validates:\s*([^\n\.]+?)(?:\n|$)")


def parse_requirements(path: Path) -> dict[int, str]:
    """req_num → title"""
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    return {int(m.group(1)): m.group(2).strip() for m in REQ_HEADER_RE.finditer(text)}


def parse_tasks(path: Path) -> list[dict]:
    """list of {id, status, text, req_refs}"""
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    tasks = []
    for m in TASK_RE.finditer(text):
        status_char = m.group(1)
        task_id = m.group(2)
        task_text = m.group(3)[:60].strip()
        # 后续 50 行内查找 _Requirements: x.y_ 引用
        start = m.end()
        sample = text[start:start + 2000]
        req_match = TASK_REQ_REF_RE.search(sample)
        req_refs = []
        if req_match:
            for ref in re.findall(r"\d+(?:\.\d+)?", req_match.group(1)):
                main = int(ref.split(".")[0])
                req_refs.append(main)
        tasks.append({
            "id": task_id,
            "status": "x" if status_char == "x" else ("*" if status_char == "*" else " "),
            "text": task_text,
            "req_refs": sorted(set(req_refs)),
        })
    return tasks


def parse_properties(path: Path) -> dict[int, dict]:
    """prop_num → {title, coverage_kind, coverage_value, requirements}"""
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    properties = {}
    matches = list(PROPERTY_RE.finditer(text))
    for i, m in enumerate(matches):
        num = int(m.group(1))
        title = m.group(2).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        block = text[start:end]
        cov = COVERAGE_RE.search(block)
        val = PROP_VALIDATES_RE.search(block)
        req_refs = []
        if val:
            for ref in re.findall(r"Requirements?\s+([\d\.\s,]+)", val.group(1)):
                for r in re.findall(r"\d+(?:\.\d+)?", ref):
                    req_refs.append(int(r.split(".")[0]))
        properties[num] = {
            "title": title,
            "coverage_kind": cov.group(1) if cov else None,
            "coverage_value": cov.group(2).strip() if cov else None,
            "requirements": sorted(set(req_refs)),
        }
    return properties


def parse_tests(test_files: list[Path]) -> dict[str, dict]:
    """func_name → {file, properties, requirements}"""
    result = {}
    for tf in test_files:
        if not tf.exists():
            continue
        text = tf.read_text(encoding="utf-8")
        for fm in TEST_FUNC_RE.finditer(text):
            func = fm.group(1)
            start = fm.end()
            sample = text[start:start + 2000]
            ds = re.search(r'"""(.+?)"""', sample, flags=re.DOTALL)
            if not ds:
                continue
            doc = ds.group(1)
            props = []
            reqs = []
            for vm in TEST_VALIDATES_RE.finditer(doc):
                line = vm.group(1)
                for p in re.findall(r"Property\s+(\d+)", line):
                    props.append(int(p))
                for r in re.findall(r"Requirements?\s+([\d\.\s,/]+)", line):
                    for n in re.findall(r"\d+(?:\.\d+)?", r):
                        reqs.append(int(n.split(".")[0]))
            result[func] = {
                "file": tf.name,
                "properties": sorted(set(props)),
                "requirements": sorted(set(reqs)),
            }
    return result


# ─── 矩阵构建 ────────────────────────────────────────────────────────────
def build_matrix(spec_id: str) -> str:
    spec_dir = SPECS_DIR / spec_id
    requirements = parse_requirements(spec_dir / "requirements.md")
    properties = parse_properties(spec_dir / "design.md")
    tasks = parse_tasks(spec_dir / "tasks.md")

    keyword = spec_id.split("-")[0]
    test_files = list(TESTS_DIR.glob(f"test_*{keyword}*.py"))
    tests = parse_tests(test_files)

    # 反向映射
    req_to_tasks: dict[int, list[str]] = {}
    for t in tasks:
        for r in t["req_refs"]:
            req_to_tasks.setdefault(r, []).append(f"{t['id']} {'✓' if t['status'] == 'x' else '○'}")

    req_to_props: dict[int, list[int]] = {}
    for pn, p in properties.items():
        for r in p["requirements"]:
            req_to_props.setdefault(r, []).append(pn)

    req_to_tests: dict[int, list[str]] = {}
    for func, info in tests.items():
        for r in info["requirements"]:
            req_to_tests.setdefault(r, []).append(func[:30])
        # 通过 Property 间接关联
        for pn in info["properties"]:
            for r in properties.get(pn, {}).get("requirements", []):
                req_to_tests.setdefault(r, []).append(f"{func[:30]}（via P{pn}）")

    # 生成 markdown
    out = []
    out.append(f"# Spec 覆盖矩阵：{spec_id}")
    out.append("")
    out.append(f"自动生成于 `backend/scripts/build_spec_coverage_matrix.py`，扫描：")
    out.append(f"- requirements.md：{len(requirements)} 个需求")
    out.append(f"- design.md：{len(properties)} 个 Property")
    out.append(f"- tasks.md：{len(tasks)} 个 task（已完成 {sum(1 for t in tasks if t['status'] == 'x')}）")
    out.append(f"- 测试文件：{len(test_files)} 个，{len(tests)} 个测试函数带 Validates 标签")
    out.append("")
    out.append("## 四向映射表（按需求编号横向展开）")
    out.append("")
    out.append("| 需求 | 标题 | 关联 Tasks | 关联 Properties | 关联 Tests |")
    out.append("|---|---|---|---|---|")
    for n in sorted(requirements.keys()):
        title = requirements[n][:30]
        ts = ", ".join(req_to_tasks.get(n, [])) or "—"
        ps = ", ".join(f"P{p}" for p in req_to_props.get(n, [])) or "—"
        es = ", ".join(req_to_tests.get(n, [])) or "—"
        out.append(f"| {n} | {title} | {ts} | {ps} | {es} |")

    # 反向漏报
    out.append("")
    out.append("## 漏报检查")
    out.append("")
    uncovered_reqs = [n for n in requirements if n not in req_to_tasks]
    if uncovered_reqs:
        out.append(f"- ⚠ {len(uncovered_reqs)} 个需求无对应 task：{uncovered_reqs}")
    else:
        out.append("- ✓ 全部需求都有对应 task")

    untested_props = [n for n, p in properties.items() if p["coverage_kind"] != "Tested"]
    if untested_props:
        out.append(f"- ⚠ {len(untested_props)} 个 Property 无自动化测试（[Pending/Skipped]）：{untested_props}")
    else:
        out.append("- ✓ 全部 Property 都有自动化测试")

    out.append("")
    out.append("## 汇总")
    out.append("")
    total_reqs = len(requirements)
    covered_reqs = total_reqs - len(uncovered_reqs)
    total_props = len(properties)
    tested_props = total_props - len(untested_props)
    out.append(f"- 需求 → Task 覆盖：{covered_reqs}/{total_reqs} = {covered_reqs * 100 // total_reqs if total_reqs else 0}%")
    out.append(f"- Property → Test 覆盖：{tested_props}/{total_props} = {tested_props * 100 // total_props if total_props else 0}%")
    return "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser(description="Spec 四向覆盖矩阵生成器")
    parser.add_argument("spec_id", help="spec 目录名")
    parser.add_argument("--output", default=None, help="输出文件路径（默认 stdout）")
    args = parser.parse_args()

    md = build_matrix(args.spec_id)
    if args.output:
        Path(args.output).write_text(md, encoding="utf-8")
        print(f"已写入 {args.output}", file=sys.stderr)
    else:
        print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
