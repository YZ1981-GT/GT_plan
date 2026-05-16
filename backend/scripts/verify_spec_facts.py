"""通用 spec 假设核验工具 — 长期保留，可被任何 spec Sprint 0 任务复用。

替代散落各 spec 的一次性 verifier 脚本（如 _verify_template_library_facts.py）。
读取 `.kiro/specs/{spec_id}/snapshot.json` 配置，执行：

  1. JSON seed 文件结构 + 条目数核验
  2. 计算值（如多文件 entries 求和）
  3. DB 表 COUNT(*) 核验
  4. 缺失文件清单核验（防止 spec 引用不存在的 seed）
  5. router_registry §N 占用检查
  6. ORM 模型字段排除检查
  7. Alembic 链路叶子节点核验

任何条目偏差 ≥ tolerance_percent 触发 WARN/FAIL，输出对比表 + 退出码。

用法：
    python backend/scripts/verify_spec_facts.py template-library-coordination
    python backend/scripts/verify_spec_facts.py audit-chain-generation
    python backend/scripts/verify_spec_facts.py --all  # 核验全部 spec

退出码：0=全部 OK / 1=有 WARN（≥5%偏差） / 2=有 FAIL（缺文件 / 字段错位 / 链路断裂）
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

# Windows console GBK 兼容：强制 stdout/stderr UTF-8
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# ─── 路径 ─────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
REPO_ROOT = BACKEND_DIR.parent
SPECS_DIR = REPO_ROOT / ".kiro" / "specs"
ALEMBIC_DIR = BACKEND_DIR / "alembic" / "versions"
ROUTER_REGISTRY = BACKEND_DIR / "app" / "router_registry.py"


# ─── 工具函数 ─────────────────────────────────────────────────────────────
def _load_json(path: Path) -> Any:
    if not path.exists():
        return None
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _resolve_path(rel: str) -> Path:
    """解析配置中的相对路径（相对仓库根）。"""
    return REPO_ROOT / rel


def _safe_count(data: Any, structure: str, key: str | None) -> int | None:
    if data is None:
        return None
    if structure == "dict":
        if not isinstance(data, dict):
            return None
        if key:
            v = data.get(key)
            return len(v) if isinstance(v, list | dict) else None
        return len(data)
    if structure == "list":
        return len(data) if isinstance(data, list) else None
    return None


def _pct_delta(actual: int | None, expected: int | None) -> str:
    if actual is None or expected is None:
        return "N/A"
    if expected == 0:
        return "0%" if actual == 0 else "∞"
    return f"{(actual - expected) / expected * 100:+.1f}%"


def _status(actual: int | None, expected: int | None, tolerance: float) -> str:
    if actual is None or expected is None:
        return "WARN"
    if expected == 0:
        return "OK" if actual == 0 else "FAIL"
    pct = abs(actual - expected) / expected * 100
    if pct < tolerance:
        return "OK"
    if pct < 20.0:
        return "WARN"
    return "FAIL"


# ─── 步骤 ─────────────────────────────────────────────────────────────────
def verify_json_sources(snapshot: dict, tolerance: float) -> list[dict]:
    print("\n" + "=" * 80)
    print("[1/7] JSON seed 文件结构 + 条目数")
    print("=" * 80)
    rows: list[dict] = []
    for name, cfg in (snapshot.get("json_sources") or {}).items():
        path = _resolve_path(cfg["path"])
        data = _load_json(path)
        actual = _safe_count(data, cfg.get("structure", "dict"), cfg.get("key"))
        expected = cfg.get("expected_count")
        status = _status(actual, expected, tolerance) if actual is not None else "FAIL"
        delta = _pct_delta(actual, expected)
        var = cfg.get("var_name", "")
        readonly = cfg.get("readonly", False)
        marker = "🔒" if readonly else "  "
        actual_str = "MISSING" if actual is None else str(actual)
        print(f"  {marker} {name:<35} expected={str(expected):>6} actual={actual_str:>8} delta={delta:>8} {status}")
        rows.append({
            "category": "json_source",
            "name": name,
            "expected": expected,
            "actual": actual,
            "delta": delta,
            "status": status,
            "var_name": var,
        })
    return rows


def verify_computed_values(snapshot: dict, json_results: list[dict], tolerance: float) -> list[dict]:
    print("\n" + "=" * 80)
    print("[2/7] 计算值（多文件求和等）")
    print("=" * 80)
    json_actuals = {r["name"]: r["actual"] for r in json_results}
    rows: list[dict] = []
    for name, cfg in (snapshot.get("computed_values") or {}).items():
        formula = cfg.get("formula", "")
        # 简单解析：仅支持加法（dn + b + cas 形式）
        parts = [p.strip() for p in formula.split("+")]
        actual = 0
        all_present = True
        for p in parts:
            v = json_actuals.get(p)
            if v is None:
                all_present = False
                break
            actual += v
        if not all_present:
            actual = None  # type: ignore
        expected = cfg.get("expected_count")
        status = _status(actual, expected, tolerance)
        delta = _pct_delta(actual, expected)
        actual_str = "N/A" if actual is None else str(actual)
        print(f"     {name:<35} expected={str(expected):>6} actual={actual_str:>8} delta={delta:>8} {status}")
        rows.append({
            "category": "computed",
            "name": name,
            "expected": expected,
            "actual": actual,
            "delta": delta,
            "status": status,
        })
    return rows


def verify_db_tables(snapshot: dict, tolerance: float) -> list[dict]:
    print("\n" + "=" * 80)
    print("[3/7] DB 表 COUNT 核验（PG）")
    print("=" * 80)

    db_tables = snapshot.get("db_tables") or {}
    if not db_tables:
        print("  (无 DB 核验项)")
        return []

    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        env_path = BACKEND_DIR / ".env"
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                if line.startswith("DATABASE_URL="):
                    db_url = line.split("=", 1)[1].strip()
                    break

    rows: list[dict] = []
    if not db_url:
        print("  [SKIP] DATABASE_URL 未设置，跳过 DB 核验")
        for name in db_tables:
            rows.append({"category": "db", "name": name, "status": "SKIP"})
        return rows

    sync_url = db_url.replace("postgresql+asyncpg://", "postgresql://")
    try:
        import psycopg2  # type: ignore
    except ImportError:
        print("  [SKIP] psycopg2 未安装，跳过 DB 核验")
        for name in db_tables:
            rows.append({"category": "db", "name": name, "status": "SKIP"})
        return rows

    try:
        conn = psycopg2.connect(sync_url)
    except Exception as e:
        print(f"  [SKIP] DB 连接失败: {e}")
        for name in db_tables:
            rows.append({"category": "db", "name": name, "status": "SKIP"})
        return rows

    cur = conn.cursor()
    for name, cfg in db_tables.items():
        try:
            cur.execute(cfg["query"])
            row = cur.fetchone()
            actual = int(row[0] or 0) if row else 0
        except Exception as e:
            actual = None
            conn.rollback()
            print(f"  [ERROR] {name}: {e}")
        # 兼容 expected_count_min（最低值）
        expected = cfg.get("expected_count")
        expected_min = cfg.get("expected_count_min")
        if expected is None and expected_min is not None and actual is not None:
            status = "OK" if actual >= expected_min else "FAIL"
            delta = f">= {expected_min}" if status == "OK" else f"< {expected_min}"
            expected_display: int | str = f">={expected_min}"
        else:
            status = _status(actual, expected, tolerance)
            delta = _pct_delta(actual, expected)
            expected_display = expected
        actual_str = "N/A" if actual is None else str(actual)
        print(f"     {name:<35} expected={str(expected_display):>6} actual={actual_str:>8} delta={delta:>8} {status}")
        rows.append({
            "category": "db",
            "name": name,
            "expected": expected_display,
            "actual": actual,
            "delta": delta,
            "status": status,
        })
    cur.close()
    conn.close()
    return rows


def verify_missing_files(snapshot: dict) -> list[dict]:
    print("\n" + "=" * 80)
    print("[4/7] 缺失文件清单（spec 显式声明不存在的）")
    print("=" * 80)
    cfg = snapshot.get("missing_files") or {}
    files = cfg.get("files") or []
    if not files:
        print("  (无缺失文件断言)")
        return []
    rows: list[dict] = []
    for rel in files:
        path = _resolve_path(rel)
        exists = path.exists()
        # 期望: 不存在 → 存在则 FAIL（spec 假设错位）
        status = "FAIL" if exists else "OK"
        marker = "⚠存在" if exists else "✗不存在"
        print(f"     {rel:<60} {marker:>8} {status}")
        rows.append({"category": "missing_file", "name": rel, "exists": exists, "status": status})
    return rows


def verify_router_section(snapshot: dict) -> list[dict]:
    print("\n" + "=" * 80)
    print("[5/7] router_registry §N 占用检查")
    print("=" * 80)
    cfg = snapshot.get("router_assertions") or {}
    if not cfg or not ROUTER_REGISTRY.exists():
        print("  (无 router 断言或文件不存在)")
        return []
    text = ROUTER_REGISTRY.read_text(encoding="utf-8")
    rows: list[dict] = []
    for key, sub in cfg.items():
        # key 如 "section_54" → 提取数字
        m = re.search(r"section_(\d+)", key)
        if not m:
            continue
        n = int(m.group(1))
        expected_handler = sub.get("expected_handler", "")
        # 在文本中查找 §n 或 ═══ n. 或 import 该 handler
        n_pattern = rf"(═══\s*{n}\.|§\s*{n}[.\s])"
        section_used = bool(re.search(n_pattern, text))
        handler_present = expected_handler in text if expected_handler else True
        if section_used and handler_present:
            status = "OK"
            note = f"§{n} 已注册 + handler 存在"
        elif section_used and not handler_present:
            status = "WARN"
            note = f"§{n} 已用但 handler '{expected_handler}' 未导入"
        else:
            status = "FAIL"
            note = f"§{n} 未注册"
        print(f"     §{n:<3} expected_handler={expected_handler!r:<35} {status}")
        print(f"         {note}")
        rows.append({"category": "router", "name": key, "status": status, "note": note})
    return rows


def verify_orm_assertions(snapshot: dict) -> list[dict]:
    print("\n" + "=" * 80)
    print("[6/7] ORM 模型字段排除检查")
    print("=" * 80)
    cfg = snapshot.get("orm_assertions") or {}
    if not cfg:
        print("  (无 ORM 断言)")
        return []
    rows: list[dict] = []
    for class_name, sub in cfg.items():
        rel = sub.get("file", "")
        path = _resolve_path(rel)
        if not path.exists():
            print(f"     [FAIL] {class_name}: 文件不存在 {rel}")
            rows.append({"category": "orm", "name": class_name, "status": "FAIL", "note": "file missing"})
            continue
        text = path.read_text(encoding="utf-8")
        # 提取 class 块
        m = re.search(rf"class {class_name}\([^)]*\):.*?(?=\nclass\s|\Z)", text, flags=re.DOTALL)
        if not m:
            print(f"     [FAIL] {class_name}: 未在 {rel} 中找到 class 定义")
            rows.append({"category": "orm", "name": class_name, "status": "FAIL", "note": "class not found"})
            continue
        class_text = m.group(0)
        forbidden = sub.get("must_not_have_field")
        if forbidden:
            has = bool(re.search(rf"\b{re.escape(forbidden)}\s*[:=]", class_text))
            status = "FAIL" if has else "OK"
            note = f"forbidden field {forbidden!r} {'存在' if has else '不存在'}"
            print(f"     {class_name:<30} must_not_have={forbidden!r:<25} {status}")
            print(f"         {note}")
            rows.append({"category": "orm", "name": class_name, "status": status, "note": note})
    return rows


def verify_alembic_leaf(snapshot: dict) -> list[dict]:
    print("\n" + "=" * 80)
    print("[7/7] Alembic 链路叶子节点核验")
    print("=" * 80)
    cfg = snapshot.get("alembic_assertions") or {}
    if not cfg or not ALEMBIC_DIR.exists():
        print("  (无 Alembic 断言或目录不存在)")
        return []

    revisions: dict[str, str | None] = {}
    for py_file in ALEMBIC_DIR.glob("*.py"):
        try:
            text = py_file.read_text(encoding="utf-8")
        except Exception:
            continue
        rev_m = re.search(r"^revision\s*=\s*['\"]([^'\"]+)['\"]", text, flags=re.MULTILINE)
        down_m = re.search(
            r"^down_revision\s*=\s*(?:['\"]([^'\"]+)['\"]|None)",
            text, flags=re.MULTILINE,
        )
        if rev_m:
            revisions[rev_m.group(1)] = down_m.group(1) if (down_m and down_m.group(1)) else None

    referenced = {d for d in revisions.values() if d}
    leaves = sorted(rev for rev in revisions.keys() if rev not in referenced)
    expected_leaf = cfg.get("leaf_revision", "")
    expected_pred = cfg.get("predecessor", "")

    rows: list[dict] = []
    is_leaf = expected_leaf in leaves
    pred_match = revisions.get(expected_leaf) == expected_pred if expected_leaf else False
    if is_leaf and pred_match:
        status = "OK"
        note = f"叶子节点 {expected_leaf!r} 正确 + predecessor 正确"
    elif is_leaf and not pred_match:
        status = "WARN"
        note = f"叶子节点正确但 predecessor 实际为 {revisions.get(expected_leaf)!r}（期望 {expected_pred!r}）"
    elif expected_leaf in revisions and not is_leaf:
        successors = [r for r, d in revisions.items() if d == expected_leaf]
        status = "WARN"
        note = f"{expected_leaf!r} 不是叶子（被 {successors} 接续，叶子已变）"
    else:
        status = "FAIL"
        note = f"{expected_leaf!r} 不在 Alembic 链路"
    print(f"     leaf={expected_leaf!r:<55} {status}")
    print(f"         {note}")
    print(f"         当前所有叶子: {leaves}")
    rows.append({"category": "alembic", "name": expected_leaf, "status": status, "note": note})
    return rows


# ─── 汇总 ─────────────────────────────────────────────────────────────────
def render_summary(spec_id: str, all_rows: list[dict]) -> int:
    print("\n" + "=" * 80)
    print(f"汇总：{spec_id}")
    print("=" * 80)
    by_status: dict[str, int] = {}
    for r in all_rows:
        s = r.get("status", "?")
        by_status[s] = by_status.get(s, 0) + 1
    for s in ("OK", "WARN", "FAIL", "SKIP"):
        if s in by_status:
            print(f"  {s}: {by_status[s]}")
    fail = by_status.get("FAIL", 0)
    warn = by_status.get("WARN", 0)
    if fail > 0:
        print(f"\n  ✗ 存在 {fail} 项 FAIL — spec 假设错位，必须先修订三件套再实施")
        return 2
    if warn > 0:
        print(f"\n  ⚠ 存在 {warn} 项 WARN — 偏差 ≥ 5%，建议更新 snapshot.json 或核查数据")
        return 1
    print(f"\n  ✓ 全部 OK — 可进入 Sprint 1 实施")
    return 0


# ─── Main ─────────────────────────────────────────────────────────────────
def verify_spec(spec_id: str) -> int:
    spec_dir = SPECS_DIR / spec_id
    snapshot_path = spec_dir / "snapshot.json"
    if not snapshot_path.exists():
        print(f"[ERROR] {snapshot_path} 不存在 — 该 spec 未提供 snapshot.json")
        print(f"        建议在 {spec_dir} 创建 snapshot.json 并填写 N_* 基准值")
        return 2

    snapshot = _load_json(snapshot_path)
    if not isinstance(snapshot, dict):
        print(f"[ERROR] {snapshot_path} 不是合法 JSON 对象")
        return 2

    tolerance = float(snapshot.get("tolerance_percent", 5))

    print("=" * 80)
    print(f"verify_spec_facts.py — {spec_id}")
    print(f"snapshot taken at: {snapshot.get('snapshot_taken_at', 'unknown')}")
    print(f"tolerance: ±{tolerance}%")
    print("=" * 80)

    all_rows: list[dict] = []
    json_rows = verify_json_sources(snapshot, tolerance)
    all_rows += json_rows
    all_rows += verify_computed_values(snapshot, json_rows, tolerance)
    all_rows += verify_db_tables(snapshot, tolerance)
    all_rows += verify_missing_files(snapshot)
    all_rows += verify_router_section(snapshot)
    all_rows += verify_orm_assertions(snapshot)
    all_rows += verify_alembic_leaf(snapshot)

    return render_summary(spec_id, all_rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="通用 spec 假设核验工具")
    parser.add_argument("spec_id", nargs="?", help="spec 目录名（如 template-library-coordination）")
    parser.add_argument("--all", action="store_true", help="核验全部含 snapshot.json 的 spec")
    args = parser.parse_args()

    if args.all:
        worst = 0
        for sub in sorted(SPECS_DIR.glob("*/snapshot.json")):
            spec_id = sub.parent.name
            print("\n" + "#" * 80)
            print(f"# {spec_id}")
            print("#" * 80)
            code = verify_spec(spec_id)
            worst = max(worst, code)
        return worst

    if not args.spec_id:
        parser.print_help()
        return 2
    return verify_spec(args.spec_id)


if __name__ == "__main__":
    sys.exit(main())
