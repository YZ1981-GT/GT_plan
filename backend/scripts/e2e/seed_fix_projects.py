"""E2E 夹具项目种子脚本 — FIX-A / FIX-B / FIX-INT / FIX-RP

构造或校验 completion-phase E2E 所需的最小项目数据，输出 manifest JSON 供 Playwright 使用。

用法（backend 目录）:
    python scripts/e2e/seed_fix_projects.py
    python scripts/e2e/seed_fix_projects.py --fix
    python scripts/e2e/seed_fix_projects.py --fix --output data/e2e_fix_projects.json

环境变量（可选，覆盖默认项目）:
    TEST_PROJECT_ID_FIX_A / FIX_B / FIX_INT / FIX_RP

Spec: completion-phase-infra e2e-matrix.md E-FIX
"""
from __future__ import annotations

import argparse
import asyncio
import io
import json
import os
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import UUID

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

_BACKEND = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_BACKEND))

_env_path = _BACKEND / ".env"
if _env_path.exists():
    for line in _env_path.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"'))

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings

DEFAULT_FIX_B = UUID("37814426-a29e-4fc2-9313-a59d229bf7b0")
DEFAULT_YEAR = 2025
# 本地 PG 与历史 e2e 硬编码 UUID 可能不一致，按名称兜底
FIX_B_NAME_HINTS = ("辽宁卫生", "和平药房", "陕西华氏")

# E2E 矩阵所需底稿（最小集）
FIX_B_WP_CODES = [
    "A7", "A8", "A8-1", "A9", "A9-1", "A10", "A11", "A11-1", "A14", "A15", "A15-1",
    "A16", "A16-1", "A18", "A18-1", "A18-2",
]
FIX_A_WP_CODES = [
    "A17", "A17-1", "A17-2-1", "A17-3", "A17-5", "A17-5-1", "A17-5-2", "A17-5-3", "A17-5-4", "A17-5-5",
    "A18", "A18-1", "A18-2",
    "A21-1", "A22-1", "A23-1", "A24-1", "A25-1",
]
FIX_INT_WP_CODES = ["B60", "A16-2", "A11-3"]
FIX_RP_WP_CODES = ["A7", "A7-1"]


@dataclass
class FixtureSpec:
    fixture_id: str
    description: str
    required_wp_codes: list[str]
    env_var: str
    default_project_id: UUID | None = None
    business_category: str | None = None
    scenario: str | None = None
    seed_a17_ch01: bool = False
    seed_related_party: bool = False
    needs_integrated_signal: bool = False


FIXTURES: list[FixtureSpec] = [
    FixtureSpec(
        fixture_id="FIX-B",
        description="B 类默认财报 — A7–A15、A16-1、A18",
        required_wp_codes=FIX_B_WP_CODES,
        env_var="TEST_PROJECT_ID_FIX_B",
        default_project_id=DEFAULT_FIX_B,
        business_category="B3",
    ),
    FixtureSpec(
        fixture_id="FIX-A",
        description="A 类 — A17 适用性、A17-5、A18",
        required_wp_codes=FIX_A_WP_CODES,
        env_var="TEST_PROJECT_ID_FIX_A",
        business_category="A1",
        seed_a17_ch01=True,
    ),
    FixtureSpec(
        fixture_id="FIX-INT",
        description="整合审计信号 — A16-2、A11-3",
        required_wp_codes=FIX_INT_WP_CODES,
        env_var="TEST_PROJECT_ID_FIX_INT",
        needs_integrated_signal=True,
    ),
    FixtureSpec(
        fixture_id="FIX-RP",
        description="A7 关联交易 — A16-7 推荐",
        required_wp_codes=FIX_RP_WP_CODES,
        env_var="TEST_PROJECT_ID_FIX_RP",
        seed_related_party=True,
    ),
]


@dataclass
class FixtureResult:
    fixture_id: str
    project_id: str | None = None
    project_name: str | None = None
    business_category: str | None = None
    ready: bool = False
    missing_wp_codes: list[str] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _parse_uuid(value: str | None) -> UUID | None:
    if not value:
        return None
    try:
        return UUID(value.strip())
    except ValueError:
        return None


async def _get_admin_user(db: AsyncSession):
    from app.models.core import User

    row = (await db.execute(sa.select(User).where(User.username == "admin"))).scalar_one_or_none()
    return row


async def _get_project_row(db: AsyncSession, project_id: UUID) -> dict | None:
    r = await db.execute(
        sa.text(
            "SELECT id, name, client_name, business_category, scenario, audit_year "
            "FROM projects WHERE id = :pid AND is_deleted = false"
        ),
        {"pid": str(project_id)},
    )
    row = r.mappings().first()
    return dict(row) if row else None


async def _find_project_by_name(db: AsyncSession, name_hints: tuple[str, ...]) -> UUID | None:
    for hint in name_hints:
        r = await db.execute(
            sa.text(
                """
                SELECT id FROM projects
                WHERE is_deleted = false AND name LIKE :pat
                ORDER BY audit_year DESC NULLS LAST
                LIMIT 1
                """
            ),
            {"pat": f"%{hint}%"},
        )
        val = r.scalar_one_or_none()
        if val:
            return UUID(str(val))
    return None


async def _find_project_with_wp_codes(
    db: AsyncSession, wp_codes: list[str], category_prefix: str | None = None
) -> UUID | None:
    if not wp_codes:
        return None
    cat_clause = ""
    params: dict[str, Any] = {"codes": wp_codes, "need": len(wp_codes)}
    if category_prefix:
        cat_clause = "AND p.business_category LIKE :cat"
        params["cat"] = f"{category_prefix}%"

    r = await db.execute(
        sa.text(
            f"""
            SELECT p.id
            FROM projects p
            JOIN wp_index wi ON wi.project_id = p.id AND wi.is_deleted = false
            WHERE p.is_deleted = false {cat_clause}
            GROUP BY p.id
            HAVING COUNT(DISTINCT wi.wp_code) FILTER (WHERE wi.wp_code = ANY(:codes)) >= :need
            ORDER BY p.audit_year DESC NULLS LAST
            LIMIT 1
            """
        ),
        params,
    )
    val = r.scalar_one_or_none()
    return UUID(str(val)) if val else None


async def _find_integrated_project(db: AsyncSession) -> UUID | None:
    r = await db.execute(
        sa.text(
            """
            SELECT wp.project_id
            FROM working_paper wp
            JOIN wp_index wi ON wi.id = wp.wp_index_id
            JOIN projects p ON p.id = wp.project_id
            WHERE wp.is_deleted = false
              AND wi.is_deleted = false
              AND p.is_deleted = false
              AND wi.wp_code LIKE 'B60%'
            ORDER BY p.audit_year DESC NULLS LAST
            LIMIT 1
            """
        )
    )
    val = r.scalar_one_or_none()
    return UUID(str(val)) if val else None


async def _find_related_party_project(db: AsyncSession) -> UUID | None:
    r = await db.execute(
        sa.text(
            """
            SELECT wp.project_id
            FROM checklist_responses cr
            JOIN working_paper wp ON wp.id = cr.wp_id
            JOIN wp_index wi ON wi.id = wp.wp_index_id
            WHERE wi.wp_code = 'A7-1'
            GROUP BY wp.project_id
            HAVING COUNT(*) > 0
            LIMIT 1
            """
        )
    )
    val = r.scalar_one_or_none()
    return UUID(str(val)) if val else None


async def _existing_wp_codes(db: AsyncSession, project_id: UUID) -> set[str]:
    r = await db.execute(
        sa.text(
            "SELECT DISTINCT wp_code FROM wp_index "
            "WHERE project_id = :pid AND is_deleted = false"
        ),
        {"pid": str(project_id)},
    )
    return {row[0] for row in r.all() if row[0]}


async def _ensure_project_metadata(
    db: AsyncSession,
    project_id: UUID,
    business_category: str | None,
    scenario: str | None,
) -> list[str]:
    actions: list[str] = []
    sets: list[str] = []
    params: dict[str, Any] = {"pid": str(project_id)}
    if business_category:
        sets.append("business_category = :bc")
        params["bc"] = business_category
    if scenario:
        sets.append("scenario = :sc")
        params["sc"] = scenario
    if not sets:
        return actions
    await db.execute(
        sa.text(f"UPDATE projects SET {', '.join(sets)} WHERE id = :pid"),
        params,
    )
    actions.append(f"更新项目 metadata: {', '.join(sets)}")
    return actions


async def _ensure_wp_codes(
    db: AsyncSession, project_id: UUID, missing: list[str], year: int
) -> list[str]:
    """为 E2E 创建最小 wp_index + working_paper 记录（不依赖 trial_balance 门禁）。"""
    if not missing:
        return []

    import json
    from pathlib import Path

    from app.models.workpaper_models import WorkingPaper, WpIndex, WpSourceType, WpStatus

    lib_path = Path(__file__).resolve().parent.parent.parent / "data" / "gt_template_library.json"
    template_lib: dict[str, dict] = {}
    if lib_path.exists():
        try:
            with open(lib_path, encoding="utf-8-sig") as f:
                lib_data = json.load(f)
            items = lib_data.get("templates", lib_data) if isinstance(lib_data, dict) else lib_data
            for item in items:
                if isinstance(item, dict):
                    template_lib[item.get("code", item.get("wp_code", ""))] = item
        except Exception:
            pass

    mapping_path = Path(__file__).resolve().parent.parent.parent / "data" / "wp_account_mapping.json"
    wp_name_map: dict[str, str] = {}
    if mapping_path.exists():
        try:
            with open(mapping_path, encoding="utf-8-sig") as f:
                raw = json.load(f)
            for item in raw.get("mappings", []):
                if item.get("wp_code") and item.get("wp_name"):
                    wp_name_map[item["wp_code"]] = item["wp_name"]
        except Exception:
            pass

    project_wp_dir = Path("storage") / "projects" / str(project_id) / "workpapers"
    created = 0
    failures: list[str] = []

    for code in missing:
        try:
            async with db.begin_nested():
                lib_entry = template_lib.get(code, {})
                wp_name = (
                    lib_entry.get("name")
                    or lib_entry.get("wp_name")
                    or wp_name_map.get(code)
                    or f"底稿{code}"
                )
                cycle = lib_entry.get("cycle_prefix") or (code[0] if code else "A")
                cycle_dir = project_wp_dir / cycle
                cycle_dir.mkdir(parents=True, exist_ok=True)
                src_path = str(lib_entry.get("file_path") or "")
                ext = ".docx" if src_path.lower().endswith(".docx") else ".xlsx"
                dest = cycle_dir / f"{code}{ext}"

                wp_index = WpIndex(
                    project_id=project_id,
                    wp_code=code,
                    wp_name=wp_name,
                    audit_cycle=cycle,
                    status=WpStatus.not_started,
                )
                db.add(wp_index)
                await db.flush()

                if not dest.exists():
                    dest.write_bytes(b"")

                wp = WorkingPaper(
                    project_id=project_id,
                    wp_index_id=wp_index.id,
                    file_path=str(dest),
                    source_type=WpSourceType.template,
                    file_version=1,
                )
                db.add(wp)
            created += 1
        except Exception as exc:
            failures.append(f"{code}: {exc}")

    msg = f"创建最小底稿记录: {created}/{len(missing)}"
    if failures:
        msg += f"; 失败 {len(failures)}: {failures[0]}"
    return [msg]


async def _get_wp_id(db: AsyncSession, project_id: UUID, wp_code: str) -> UUID | None:
    r = await db.execute(
        sa.text(
            """
            SELECT wp.id FROM working_paper wp
            JOIN wp_index wi ON wi.id = wp.wp_index_id
            WHERE wp.project_id = :pid AND wi.wp_code = :code AND wp.is_deleted = false
            LIMIT 1
            """
        ),
        {"pid": str(project_id), "code": wp_code},
    )
    val = r.scalar_one_or_none()
    return UUID(str(val)) if val else None


async def _seed_a17_ch01(db: AsyncSession, project_id: UUID) -> list[str]:
    wp_id = await _get_wp_id(db, project_id, "A17-1")
    if not wp_id:
        return ["跳过 A17-1 ch01：无 A17-1 底稿"]
    existing = await db.execute(
        sa.text(
            "SELECT 1 FROM checklist_responses WHERE wp_id = :wp AND item_id = 'A17-1-ch01' LIMIT 1"
        ),
        {"wp": str(wp_id)},
    )
    if existing.scalar_one_or_none():
        return ["A17-1-ch01 已存在"]
    proj = await _get_project_row(db, project_id)
    client = (proj or {}).get("client_name") or "E2E测试公司"
    remark = f"被审计单位：{client}\n审计期间：{DEFAULT_YEAR}年1月1日至12月31日\n（E2E seed）"
    await db.execute(
        sa.text(
            """
            INSERT INTO checklist_responses (id, project_id, wp_id, item_id, remark, created_at, updated_at)
            VALUES (:id, :pid, :wp_id, 'A17-1-ch01', :remark, NOW(), NOW())
            """
        ),
        {"id": str(uuid.uuid4()), "pid": str(project_id), "wp_id": str(wp_id), "remark": remark},
    )
    return ["写入 A17-1-ch01 样例（E18 小结生成）"]


async def _seed_related_party_row(db: AsyncSession, project_id: UUID) -> list[str]:
    wp_id = await _get_wp_id(db, project_id, "A7-1")
    if not wp_id:
        return ["跳过关联交易 seed：无 A7-1 底稿"]
    count_r = await db.execute(
        sa.text("SELECT COUNT(*) FROM checklist_responses WHERE wp_id = :wp"),
        {"wp": str(wp_id)},
    )
    if int(count_r.scalar_one() or 0) > 0:
        return ["A7-1 checklist 已有数据"]
    await db.execute(
        sa.text(
            """
            INSERT INTO checklist_responses (id, project_id, wp_id, item_id, conclusion, remark, created_at, updated_at)
            VALUES (:id, :pid, :wp_id, 'E2E-RP-ROW-1', 'Y', 'E2E seed 关联交易样例行', NOW(), NOW())
            """
        ),
        {"id": str(uuid.uuid4()), "pid": str(project_id), "wp_id": str(wp_id)},
    )
    return ["写入 A7-1 关联交易样例行（A16-7 推荐信号）"]


async def _resolve_fix_b_id(db: AsyncSession) -> UUID | None:
    env_id = _parse_uuid(os.environ.get("TEST_PROJECT_ID_FIX_B"))
    if env_id and await _get_project_row(db, env_id):
        return env_id
    if await _get_project_row(db, DEFAULT_FIX_B):
        return DEFAULT_FIX_B
    by_name = await _find_project_by_name(db, FIX_B_NAME_HINTS)
    if by_name:
        return by_name
    return await _find_project_with_wp_codes(db, FIX_B_WP_CODES)


async def _resolve_project_id(
    db: AsyncSession, spec: FixtureSpec, fix_b_id: UUID | None
) -> UUID | None:
    env_id = _parse_uuid(os.environ.get(spec.env_var))
    if env_id and await _get_project_row(db, env_id):
        return env_id
    if spec.default_project_id and await _get_project_row(db, spec.default_project_id):
        return spec.default_project_id

    if spec.fixture_id == "FIX-A":
        found = await _find_project_with_wp_codes(db, spec.required_wp_codes, "A")
        if found:
            return found
        return fix_b_id

    if spec.fixture_id == "FIX-INT":
        found = await _find_integrated_project(db)
        if found and await _get_project_row(db, found):
            return found
        return fix_b_id

    if spec.fixture_id == "FIX-RP":
        found = await _find_related_party_project(db)
        if found and await _get_project_row(db, found):
            return found
        return fix_b_id

    return fix_b_id


async def _process_fixture(
    db: AsyncSession,
    spec: FixtureSpec,
    project_id: UUID | None,
    year: int,
    do_fix: bool,
) -> FixtureResult:
    result = FixtureResult(fixture_id=spec.fixture_id)
    if project_id is None:
        result.warnings.append("未找到可用项目")
        return result

    proj = await _get_project_row(db, project_id)
    if not proj:
        result.warnings.append(f"项目 {project_id} 不存在")
        return result

    result.project_id = str(project_id)
    result.project_name = proj.get("name")
    result.business_category = proj.get("business_category")

    existing = await _existing_wp_codes(db, project_id)
    result.missing_wp_codes = [c for c in spec.required_wp_codes if c not in existing]

    if do_fix:
        if spec.business_category or spec.scenario:
            result.actions.extend(
                await _ensure_project_metadata(
                    db, project_id, spec.business_category, spec.scenario
                )
            )
            proj = await _get_project_row(db, project_id)
            if proj:
                result.business_category = proj.get("business_category")
        if result.missing_wp_codes:
            result.actions.extend(
                await _ensure_wp_codes(db, project_id, result.missing_wp_codes, year)
            )
            existing = await _existing_wp_codes(db, project_id)
            result.missing_wp_codes = [c for c in spec.required_wp_codes if c not in existing]
        if spec.seed_a17_ch01:
            result.actions.extend(await _seed_a17_ch01(db, project_id))
        if spec.seed_related_party:
            result.actions.extend(await _seed_related_party_row(db, project_id))
        if spec.needs_integrated_signal and "B60" in result.missing_wp_codes:
            result.warnings.append("整合审计信号仍缺 B60 底稿")

    prefix_ok = True
    if spec.business_category and result.business_category and spec.fixture_id == "FIX-A":
        prefix_ok = result.business_category.upper().startswith(spec.business_category[0])
    elif spec.business_category and result.business_category and spec.fixture_id == "FIX-B":
        # FIX-B 以底稿齐备为主；同项目被 FIX-A 覆写为 A 类时仍可用
        prefix_ok = True

    result.ready = len(result.missing_wp_codes) == 0 and prefix_ok
    if spec.fixture_id == "FIX-A" and result.business_category and not result.business_category.upper().startswith("A"):
        result.warnings.append(
            f"business_category={result.business_category} 非 A 类；请 --fix 或手动设为 A1/A2"
        )
        if not do_fix:
            result.ready = False

    return result


def _print_results(results: list[FixtureResult]) -> None:
    print()
    print("=" * 100)
    print(f"{'夹具':<10} {'就绪':<6} {'项目':<38} {'缺失底稿':<30}")
    print("-" * 100)
    for r in results:
        status = "✅" if r.ready else "❌"
        pid = (r.project_id or "-")[:36]
        missing = ",".join(r.missing_wp_codes[:3])
        if len(r.missing_wp_codes) > 3:
            missing += f" +{len(r.missing_wp_codes) - 3}"
        print(f"{r.fixture_id:<10} {status:<6} {pid:<38} {missing or '-':<30}")
        for w in r.warnings:
            print(f"           ⚠ {w}")
        for a in r.actions:
            print(f"           → {a}")
    print("=" * 100)


def _build_manifest(results: list[FixtureResult]) -> dict:
    by_id = {r.fixture_id: r for r in results}
    fix_a = by_id.get("FIX-A")
    fix_b = by_id.get("FIX-B")
    return {
        "year": DEFAULT_YEAR,
        "fixtures": {
            r.fixture_id: {
                "project_id": r.project_id,
                "project_name": r.project_name,
                "business_category": r.business_category,
                "ready": r.ready,
                "missing_wp_codes": r.missing_wp_codes,
                "warnings": r.warnings,
            }
            for r in results
        },
        "env": {
            "TEST_PROJECT_ID": (fix_b.project_id if fix_b and fix_b.project_id else ""),
            "TEST_PROJECT_ID_FIX_A": (fix_a.project_id if fix_a and fix_a.project_id else ""),
            "TEST_PROJECT_ID_FIX_B": (fix_b.project_id if fix_b and fix_b.project_id else ""),
            "TEST_PROJECT_ID_FIX_INT": (
                (by_id.get("FIX-INT") or FixtureResult("")).project_id or ""
            ),
            "TEST_PROJECT_ID_FIX_RP": (
                (by_id.get("FIX-RP") or FixtureResult("")).project_id or ""
            ),
            "RUN_FULL_E2E": "1",
        },
        "playwright_hint": (
            "set RUN_FULL_E2E=1 && set TEST_PROJECT_ID=<FIX-B或FIX-A ID> && "
            "npx playwright test e2e/"
        ),
    }


async def main() -> int:
    parser = argparse.ArgumentParser(description="E2E FIX 夹具项目 seed/verify")
    parser.add_argument("--fix", action="store_true", help="补齐 metadata / 缺失底稿 / 样例数据")
    parser.add_argument("--year", type=int, default=DEFAULT_YEAR)
    parser.add_argument(
        "--output",
        type=str,
        default=str(_BACKEND / "data" / "e2e_fix_projects.json"),
        help="manifest JSON 输出路径",
    )
    args = parser.parse_args()

    url = settings.DATABASE_URL
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)

    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_async_engine(url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    print("=" * 60)
    print("  E2E FIX 夹具 seed / verify")
    print(f"  mode={'--fix 补齐' if args.fix else '只读校验'}  year={args.year}")
    print("=" * 60)

    results: list[FixtureResult] = []
    async with async_session() as db:
        fix_b_id = await _resolve_fix_b_id(db)

        resolved: dict[str, UUID | None] = {}
        for spec in FIXTURES:
            resolved[spec.fixture_id] = await _resolve_project_id(db, spec, fix_b_id)

        for spec in FIXTURES:
            fr = await _process_fixture(
                db, spec, resolved[spec.fixture_id], args.year, args.fix
            )
            results.append(fr)

        if args.fix:
            await db.commit()

    _print_results(results)

    manifest = _build_manifest(results)
    out_path = Path(args.output)
    if not out_path.is_absolute():
        out_path = _BACKEND / out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nmanifest → {out_path}")
    print("\nPlaywright 环境变量示例:")
    for k, v in manifest["env"].items():
        if v:
            print(f"  set {k}={v}")

    await engine.dispose()
    all_ready = all(r.ready for r in results)
    return 0 if all_ready else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
