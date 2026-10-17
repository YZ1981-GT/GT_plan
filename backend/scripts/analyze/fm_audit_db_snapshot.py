# -*- coding: utf-8 -*-
"""公式管理平台审计 —— 可复现只读数据快照脚本。

对应文档 `docs/proposals/formula-management-platform-audit-2026-10-17.md` 第十一节
「当前数据快照」与「静态数据口径」的每一个计数，提供 [指标名 → 实际 SQL/命令 → 实测值]
的可重跑取证。长期保留、可重跑；输出稳定排序 JSON（无时间戳/机器名/绝对路径）供幂等门禁用。

铁律：
- 只读 DB：全部 SELECT/COUNT，绝不 INSERT/UPDATE/DELETE/DDL。
- 每条指标在 autocommit 连接上独立执行；执行前先用 information_schema 确认表/列存在，
  缺失输出「表不存在」/「列不存在」而非崩溃；单条异常被捕获为该指标的错误字符串，不影响其余。
- 凭据只从 .env（经 os.environ）读取；绝不把任何密码字面量写入脚本或输出。打印连接信息时
  只显示 `@` 之后的 host/db 片段。

运行（cwd=worktree 根）：
    chcp 65001
    .venv\\Scripts\\python.exe backend\\scripts\\analyze\\fm_audit_db_snapshot.py --format table
    .venv\\Scripts\\python.exe backend\\scripts\\analyze\\fm_audit_db_snapshot.py --format json
    .venv\\Scripts\\python.exe backend\\scripts\\analyze\\fm_audit_db_snapshot.py --static

运行（cwd=backend，走主仓库 venv，worktree 内无独立 venv）：
    chcp 65001
    ..\\..\\..\\.venv\\Scripts\\python.exe scripts\\analyze\\fm_audit_db_snapshot.py --format table
"""
from __future__ import annotations

import argparse
import glob
import io
import json
import os
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# utf-8 stdout（PowerShell 中文输出需先 chcp 65001）
# ---------------------------------------------------------------------------
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

# worktree/仓库根（backend/scripts/analyze/<此文件> → parents[3]）
ROOT = Path(__file__).resolve().parents[3]


# ---------------------------------------------------------------------------
# env 加载 + 同步 URL 构造（绝不打印/写入密码）
# ---------------------------------------------------------------------------
def _load_env() -> None:
    """按候选顺序加载 .env（override=False，先命中者优先）。

    worktree 根通常无 .env（git-ignored），回退到主仓库 .env / backend/.env。
    """
    try:
        from dotenv import load_dotenv
    except Exception:  # pragma: no cover
        return
    candidates = [
        ROOT / ".env",
        ROOT / "backend" / ".env",
        Path("d:/GT_plan/.env"),
        Path("d:/GT_plan/backend/.env"),
    ]
    for cand in candidates:
        try:
            if cand.exists():
                load_dotenv(cand, override=False)
        except Exception:  # pragma: no cover
            continue


def build_sync_url() -> str:
    """优先 DATABASE_URL（去 +asyncpg 得同步 URL），否则用 PG_* 拼装。"""
    url = os.environ.get("DATABASE_URL")
    if url:
        # psycopg2 不认 +asyncpg / +psycopg 等驱动后缀
        url = re.sub(r"\+\w+", "", url, count=1)
        return url
    user = os.environ.get("PG_USER")
    pwd = os.environ.get("PG_PASSWORD")
    db = os.environ.get("PG_DB")
    port = os.environ.get("PG_PORT", "5432")
    host = os.environ.get("PG_HOST", "localhost")
    if not (user and pwd and db):
        raise RuntimeError(
            "缺少数据库凭据：未在 .env 找到 DATABASE_URL，也未找到完整 PG_USER/PG_PASSWORD/PG_DB"
        )
    return f"postgresql://{user}:{pwd}@{host}:{port}/{db}"


def _safe_target(url: str) -> str:
    """只取 `@` 之后的 host/db 片段用于打印，绝不泄露密码。"""
    at = url.rfind("@")
    return url[at + 1:] if at >= 0 else "(无法解析)"


# ---------------------------------------------------------------------------
# 只读查询封装：information_schema 存在性检查 + 单条异常隔离
# ---------------------------------------------------------------------------
class Db:
    def __init__(self, url: str):
        import psycopg2

        self.conn = psycopg2.connect(url)
        self.conn.autocommit = True  # 每条查询独立事务，首条失败不级联

    def close(self) -> None:
        try:
            self.conn.close()
        except Exception:  # pragma: no cover
            pass

    def table_exists(self, table: str) -> bool:
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_schema='public' AND table_name=%s",
                (table,),
            )
            return cur.fetchone() is not None

    def column_exists(self, table: str, col: str) -> bool:
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_schema='public' AND table_name=%s AND column_name=%s",
                (table, col),
            )
            return cur.fetchone() is not None

    def scalar(self, sql: str):
        with self.conn.cursor() as cur:
            cur.execute(sql)
            row = cur.fetchone()
            return row[0] if row else None


# ---------------------------------------------------------------------------
# 指标定义：每条含 {label, sql, value}
# ---------------------------------------------------------------------------
def collect_db_metrics(db: Db) -> list[dict]:
    """覆盖第十一节「当前数据快照」每一个 DB 计数。

    每条指标描述依赖的表/列；缺失时 value 记为「表不存在」/「列不存在」，
    单条执行异常被捕获为错误字符串。
    """
    metrics: list[dict] = []

    def add(label: str, sql: str, *, table: str | None = None,
            cols: tuple[str, ...] = ()) -> None:
        # 存在性前置检查
        if table is not None and not db.table_exists(table):
            metrics.append({"label": label, "sql": sql, "value": f"表不存在({table})"})
            return
        for c in cols:
            if table is not None and not db.column_exists(table, c):
                metrics.append({"label": label, "sql": sql, "value": f"列不存在({table}.{c})"})
                return
        try:
            val = db.scalar(sql)
            metrics.append({"label": label, "sql": sql,
                            "value": int(val) if val is not None else 0})
        except Exception as e:  # noqa: BLE001 — autocommit 下单条失败不影响其余
            metrics.append({"label": label, "sql": sql, "value": f"查询错误: {e!r}"})

    # ---- projects ----
    add("projects.total", "SELECT COUNT(*) FROM projects", table="projects")
    add("projects.active(未删)", "SELECT COUNT(*) FROM projects WHERE is_deleted=false",
        table="projects", cols=("is_deleted",))
    add("projects.active.report_scope=standalone",
        "SELECT COUNT(*) FROM projects WHERE is_deleted=false AND report_scope='standalone'",
        table="projects", cols=("is_deleted", "report_scope"))
    add("projects.active.report_scope=consolidated",
        "SELECT COUNT(*) FROM projects WHERE is_deleted=false AND report_scope='consolidated'",
        table="projects", cols=("is_deleted", "report_scope"))
    add("projects.active.report_scope IS NULL",
        "SELECT COUNT(*) FROM projects WHERE is_deleted=false AND report_scope IS NULL",
        table="projects", cols=("is_deleted", "report_scope"))

    # ---- wp_index / working_paper ----
    add("wp_index.rows", "SELECT COUNT(*) FROM wp_index", table="wp_index")
    add("wp_index.distinct_project", "SELECT COUNT(DISTINCT project_id) FROM wp_index",
        table="wp_index", cols=("project_id",))
    add("wp_index.distinct_wp_code", "SELECT COUNT(DISTINCT wp_code) FROM wp_index",
        table="wp_index", cols=("wp_code",))
    add("working_paper.rows", "SELECT COUNT(*) FROM working_paper", table="working_paper")
    add("working_paper.distinct_project", "SELECT COUNT(DISTINCT project_id) FROM working_paper",
        table="working_paper", cols=("project_id",))

    # ---- wp_formula（分类三列各自，非同一列三值） ----
    add("wp_formula.total", "SELECT COUNT(*) FROM wp_formula", table="wp_formula")
    add("wp_formula.refs 非空(jsonb)",
        "SELECT COUNT(*) FROM wp_formula WHERE refs IS NOT NULL "
        "AND refs::text NOT IN ('null','[]','{}')",
        table="wp_formula", cols=("refs",))
    add("wp_formula.source_scope 非空(jsonb)",
        "SELECT COUNT(*) FROM wp_formula WHERE source_scope IS NOT NULL "
        "AND source_scope::text NOT IN ('null','[]','{}')",
        table="wp_formula", cols=("source_scope",))
    add("wp_formula.binding 非空(jsonb)",
        "SELECT COUNT(*) FROM wp_formula WHERE binding IS NOT NULL "
        "AND binding::text NOT IN ('null','[]','{}')",
        table="wp_formula", cols=("binding",))
    add("wp_formula.computed(last_computed_at 非空)",
        "SELECT COUNT(*) FROM wp_formula WHERE last_computed_at IS NOT NULL",
        table="wp_formula", cols=("last_computed_at",))
    add("wp_formula.列category='auto_calc'",
        "SELECT COUNT(*) FROM wp_formula WHERE category='auto_calc'",
        table="wp_formula", cols=("category",))
    add("wp_formula.列formula_source='custom'",
        "SELECT COUNT(*) FROM wp_formula WHERE formula_source='custom'",
        table="wp_formula", cols=("formula_source",))
    add("wp_formula.列lifecycle_state='saved'",
        "SELECT COUNT(*) FROM wp_formula WHERE lifecycle_state='saved'",
        table="wp_formula", cols=("lifecycle_state",))
    add("wp_formula.所属项目软删(is_deleted=true)",
        "SELECT COUNT(*) FROM wp_formula f JOIN projects p ON p.id=f.project_id "
        "WHERE p.is_deleted=true",
        table="wp_formula", cols=("project_id",))
    add("wp_formula.所属项目未删(is_deleted=false)",
        "SELECT COUNT(*) FROM wp_formula f JOIN projects p ON p.id=f.project_id "
        "WHERE p.is_deleted=false",
        table="wp_formula", cols=("project_id",))

    # ---- report_config（全局模板表，无 project_id，按 applicable_standard 区分） ----
    add("report_config.rows", "SELECT COUNT(*) FROM report_config", table="report_config")
    add("report_config.未删rows",
        "SELECT COUNT(*) FROM report_config WHERE is_deleted=false",
        table="report_config", cols=("is_deleted",))
    add("report_config.含公式(formula 非空非空串)",
        "SELECT COUNT(*) FROM report_config WHERE formula IS NOT NULL AND formula<>''",
        table="report_config", cols=("formula",))
    add("report_config.distinct_applicable_standard",
        "SELECT COUNT(DISTINCT applicable_standard) FROM report_config",
        table="report_config", cols=("applicable_standard",))

    # ---- financial_report ----
    add("financial_report.rows", "SELECT COUNT(*) FROM financial_report", table="financial_report")
    add("financial_report.formula_used 非空rows",
        "SELECT COUNT(*) FROM financial_report WHERE formula_used IS NOT NULL AND formula_used<>''",
        table="financial_report", cols=("formula_used",))
    add("financial_report.含公式_distinct项目",
        "SELECT COUNT(DISTINCT project_id) FROM financial_report "
        "WHERE formula_used IS NOT NULL AND formula_used<>''",
        table="financial_report", cols=("formula_used", "project_id"))
    add("financial_report.克隆判定_distinct(row_code+formula_used)对",
        "SELECT COUNT(*) FROM (SELECT DISTINCT row_code, formula_used FROM financial_report "
        "WHERE formula_used IS NOT NULL AND formula_used<>'') t",
        table="financial_report", cols=("row_code", "formula_used"))
    add("financial_report.含公式_跨项目公式冲突行数(应为0)",
        "SELECT COUNT(*) FROM (SELECT row_code FROM financial_report "
        "WHERE formula_used IS NOT NULL AND formula_used<>'' "
        "GROUP BY row_code HAVING COUNT(DISTINCT formula_used) > 1) t",
        table="financial_report", cols=("row_code", "formula_used"))

    # ---- disclosure_notes（JSONB table_data 内键存在/非空用 jsonb 操作符） ----
    add("disclosure_notes.rows", "SELECT COUNT(*) FROM disclosure_notes", table="disclosure_notes")
    add("disclosure_notes.未删rows",
        "SELECT COUNT(*) FROM disclosure_notes WHERE is_deleted=false",
        table="disclosure_notes", cols=("is_deleted",))
    add("disclosure_notes.distinct_项目",
        "SELECT COUNT(DISTINCT project_id) FROM disclosure_notes",
        table="disclosure_notes", cols=("project_id",))
    add("disclosure_notes.is_stale=true",
        "SELECT COUNT(*) FROM disclosure_notes WHERE is_stale=true",
        table="disclosure_notes", cols=("is_stale",))
    add("disclosure_notes.table_data 含键 _formulas",
        "SELECT COUNT(*) FROM disclosure_notes "
        "WHERE jsonb_typeof(table_data)='object' AND table_data ? '_formulas'",
        table="disclosure_notes", cols=("table_data",))
    add("disclosure_notes._formulas 非空对象",
        "SELECT COUNT(*) FROM disclosure_notes "
        "WHERE jsonb_typeof(table_data)='object' AND table_data ? '_formulas' "
        "AND jsonb_typeof(table_data->'_formulas')='object' "
        "AND table_data->'_formulas' <> '{}'::jsonb",
        table="disclosure_notes", cols=("table_data",))
    add("disclosure_notes.table_data 含键 _user_formulas",
        "SELECT COUNT(*) FROM disclosure_notes "
        "WHERE jsonb_typeof(table_data)='object' AND table_data ? '_user_formulas'",
        table="disclosure_notes", cols=("table_data",))
    add("disclosure_notes._user_formulas 非空对象",
        "SELECT COUNT(*) FROM disclosure_notes "
        "WHERE jsonb_typeof(table_data)='object' AND table_data ? '_user_formulas' "
        "AND jsonb_typeof(table_data->'_user_formulas')='object' "
        "AND table_data->'_user_formulas' <> '{}'::jsonb",
        table="disclosure_notes", cols=("table_data",))
    add("disclosure_notes.table_data 含键 check_presets",
        "SELECT COUNT(*) FROM disclosure_notes "
        "WHERE jsonb_typeof(table_data)='object' AND table_data ? 'check_presets'",
        table="disclosure_notes", cols=("table_data",))

    # ---- tb_detail_formulas（存 projects.wizard_state JSONB） ----
    add("projects.wizard_state 含 tb_detail_formulas 的项目数",
        "SELECT COUNT(*) FROM projects "
        "WHERE jsonb_typeof(wizard_state)='object' AND wizard_state ? 'tb_detail_formulas'",
        table="projects", cols=("wizard_state",))

    # ---- 其余运行/推送表 ----
    add("cross_check_results.rows", "SELECT COUNT(*) FROM cross_check_results",
        table="cross_check_results")
    add("formula_runtime_outbox.rows", "SELECT COUNT(*) FROM formula_runtime_outbox",
        table="formula_runtime_outbox")
    add("formula_push_run.rows", "SELECT COUNT(*) FROM formula_push_run",
        table="formula_push_run")
    add("formula_push_state.rows", "SELECT COUNT(*) FROM formula_push_state",
        table="formula_push_state")

    # ---- 合并（consol） ----
    add("consol_note_formula.rows(全部)", "SELECT COUNT(*) FROM consol_note_formula",
        table="consol_note_formula")
    add("consol_note_formula.未删rows",
        "SELECT COUNT(*) FROM consol_note_formula WHERE is_deleted=false",
        table="consol_note_formula", cols=("is_deleted",))
    add("consol_push_run.rows", "SELECT COUNT(*) FROM consol_push_run",
        table="consol_push_run")
    add("consol_note_data.rows", "SELECT COUNT(*) FROM consol_note_data",
        table="consol_note_data")

    return metrics


# ---------------------------------------------------------------------------
# 静态数据口径（TASK 2）：每条给 [指标名 → 命令/SQL → 实测值]
# 可现场复现者直接计算；service 派生、单文件无法复现者标「口径未复现」。
# ---------------------------------------------------------------------------
def collect_static_metrics() -> list[dict]:
    out: list[dict] = []

    def add(label: str, cmd: str, value) -> None:
        out.append({"label": label, "cmd": cmd, "value": value})

    # override 映射
    try:
        p = ROOT / "backend" / "app" / "data" / "wp_code_overrides.json"
        d = json.loads(p.read_text(encoding="utf-8"))
        add("override 映射数", "len(json wp_code_overrides.json)", len(d))
        add("override distinct componentType", "len(set(values))", len(set(d.values())))
    except Exception as e:  # noqa: BLE001
        add("override 映射数", "wp_code_overrides.json", f"读取错误: {e!r}")

    # 前端 registry componentType（membership = 6 个 entries 数组条目和）
    try:
        entry_dir = (ROOT / "audit-platform" / "frontend" / "src" / "components"
                     / "workpaper" / "registry" / "entries")
        total = 0
        per = {}
        for f in sorted(glob.glob(str(entry_dir / "*.ts"))):
            txt = Path(f).read_text(encoding="utf-8")
            n = len(re.findall(r"componentType:\s*", txt))
            per[Path(f).name] = n
            total += n
        add("前端 registry componentType",
            "sum(regex 'componentType:' over registry/entries/*.ts)",
            {"total": total, **per})
    except Exception as e:  # noqa: BLE001
        add("前端 registry componentType", "registry/entries/*.ts", f"读取错误: {e!r}")

    # formula_push rules
    try:
        p = ROOT / "backend" / "data" / "formula_push_rules.json"
        d = json.loads(p.read_text(encoding="utf-8"))
        rules = d.get("rules") or []
        from collections import Counter
        by_stage = Counter(str(r.get("stage")) for r in rules)
        page_keys = {r.get("page_key") for r in rules if r.get("page_key")}
        add("formula_push rules 总数", "len(formula_push_rules.json['rules'])", len(rules))
        add("formula_push rules 按 stage",
            "Counter(rule['stage'])", dict(sorted(by_stage.items())))
        add("formula_push distinct page_key",
            "len(set(rule['page_key']))", len(page_keys))
    except Exception as e:  # noqa: BLE001
        add("formula_push rules 总数", "formula_push_rules.json", f"读取错误: {e!r}")

    # ACNR global_catalog
    try:
        p = ROOT / "backend" / "data" / "acnr" / "global_catalog.json"
        cat = json.loads(p.read_text(encoding="utf-8"))
        add("ACNR sheets", "len(acnr/global_catalog.json['sheets'])",
            len(cat.get("sheets") or []))
        add("ACNR cells", "len(acnr/global_catalog.json['cells'])",
            len(cat.get("cells") or []))
    except Exception as e:  # noqa: BLE001
        add("ACNR sheets", "acnr/global_catalog.json", f"读取错误: {e!r}")

    # render schema yaml 数
    try:
        rs_dir = ROOT / "backend" / "data" / "ledger_adapters" / "wp_render_schema"
        yamls = glob.glob(str(rs_dir / "**" / "*.yaml"), recursive=True)
        add("render schema yaml 文件数",
            "count(*.yaml under backend/data/ledger_adapters/wp_render_schema)", len(yamls))
    except Exception as e:  # noqa: BLE001
        add("render schema yaml 文件数", "ledger_adapters/wp_render_schema", f"读取错误: {e!r}")

    # classification（DB 表）—— 由 --format 的 DB 段补齐，这里仅给出 SQL 口径
    add("classification rows (DB)",
        "SELECT COUNT(*) FROM workpaper_sheet_classification  （见 --format table 的 DB 段扩展）",
        "见 DB 扩展指标 classification.*")

    # service 派生、单文件/单表无法复现者：显式标注「口径未复现」
    for label in [
        "CWR refs/targets（cross_wp_references 服务派生）",
        "L3 dependencies（address_registry_v2 依赖图服务派生）",
        "unified graph nodes/edges（统一依赖图服务派生）",
        "resolved refs（V2 resolved 快照服务派生）",
        "prefill mappings（prefill 服务派生）",
        "surfaced catalog 81/598/2301（wp_formula.py 静态目录运行期组装）",
    ]:
        add(label, "服务/运行期派生，非单一文件或表", "口径未复现，沿用 84def65b 值（静态证据，运行时待验）")

    return out


# ---------------------------------------------------------------------------
# 扩展 DB 指标：classification 相关（只读，补齐静态口径里的 DB 型计数）
# ---------------------------------------------------------------------------
def collect_classification_metrics(db: Db) -> list[dict]:
    metrics: list[dict] = []

    def add(label: str, sql: str, *, table: str | None = None,
            cols: tuple[str, ...] = ()) -> None:
        if table is not None and not db.table_exists(table):
            metrics.append({"label": label, "sql": sql, "value": f"表不存在({table})"})
            return
        for c in cols:
            if table is not None and not db.column_exists(table, c):
                metrics.append({"label": label, "sql": sql, "value": f"列不存在({table}.{c})"})
                return
        try:
            val = db.scalar(sql)
            metrics.append({"label": label, "sql": sql,
                            "value": int(val) if val is not None else 0})
        except Exception as e:  # noqa: BLE001
            metrics.append({"label": label, "sql": sql, "value": f"查询错误: {e!r}"})

    t = "workpaper_sheet_classification"
    add("classification.rows", f"SELECT COUNT(*) FROM {t}", table=t)
    add("classification.distinct_wp_code", f"SELECT COUNT(DISTINCT wp_code) FROM {t}",
        table=t, cols=("wp_code",))
    add("classification.is_real_workpaper=true",
        f"SELECT COUNT(*) FROM {t} WHERE is_real_workpaper=true",
        table=t, cols=("is_real_workpaper",))
    return metrics


# ---------------------------------------------------------------------------
# 输出
# ---------------------------------------------------------------------------
def print_table(title: str, rows: list[dict], key: str) -> None:
    print(f"\n==== {title} ====")
    for m in rows:
        print(f"- {m['label']}")
        print(f"    {key}: {m[key]}")
        print(f"    实测值: {m['value']}")


def to_json_obj(db_metrics, cls_metrics, static_metrics) -> dict:
    """稳定排序，无时间戳/机器名/绝对路径。"""
    return {
        "db_metrics": sorted(
            [{"label": m["label"], "sql": m["sql"], "value": m["value"]}
             for m in db_metrics],
            key=lambda x: x["label"],
        ),
        "classification_metrics": sorted(
            [{"label": m["label"], "sql": m["sql"], "value": m["value"]}
             for m in cls_metrics],
            key=lambda x: x["label"],
        ),
        "static_metrics": sorted(
            [{"label": m["label"], "cmd": m["cmd"], "value": m["value"]}
             for m in static_metrics],
            key=lambda x: x["label"],
        ),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="公式管理平台审计只读数据快照")
    ap.add_argument("--format", choices=["table", "json"], default="table",
                    help="table=人读中文表格（默认）；json=稳定排序 JSON（幂等门禁用）")
    ap.add_argument("--static", action="store_true",
                    help="只打印静态数据口径（不连 DB）")
    args = ap.parse_args()

    _load_env()

    if args.static:
        static_metrics = collect_static_metrics()
        print_table("静态数据口径（TASK 2）", static_metrics, key="cmd")
        return 0

    url = build_sync_url()
    # 连接信息写 stderr，保持 --format json 的 stdout 为纯 JSON（幂等门禁友好）
    print(f"[连接目标] {_safe_target(url)}  （密码不打印）", file=sys.stderr)
    db = Db(url)
    try:
        db_metrics = collect_db_metrics(db)
        cls_metrics = collect_classification_metrics(db)
    finally:
        db.close()
    static_metrics = collect_static_metrics()

    if args.format == "json":
        obj = to_json_obj(db_metrics, cls_metrics, static_metrics)
        print(json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2))
    else:
        print_table("当前数据快照（只读 PG 事务，TASK 1）", db_metrics, key="sql")
        print_table("分类表扩展（classification，DB）", cls_metrics, key="sql")
        print_table("静态数据口径（TASK 2）", static_metrics, key="cmd")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
