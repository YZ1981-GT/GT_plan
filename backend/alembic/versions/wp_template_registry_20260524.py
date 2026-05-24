"""Create wp_template_registry table + migrate data from dual JSON sources.

Revision ID: wp_template_registry_20260524
Revises: phase3_tb_balance_composite_index_20260527
Create Date: 2026-05-24

Requirements: Req 4 (advanced-query-enhancements-p1p2)
"""
import json
import logging
from pathlib import Path

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

logger = logging.getLogger("alembic.runtime.migration")

# revision identifiers
revision = "wp_template_registry_20260524"
down_revision = "phase3_tb_balance_composite_index_20260527"
branch_labels = None
depends_on = None

# Valid cycle codes: A~N + S (15 total)
VALID_CYCLES = ("A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L", "M", "N", "S")


def upgrade() -> None:
    # ─── DDL: Create table ───────────────────────────────────────────────
    op.create_table(
        "wp_template_registry",
        sa.Column("wp_code", sa.String(32), primary_key=True),
        sa.Column("wp_name", sa.String(255), nullable=False),
        sa.Column("cycle", sa.String(2), nullable=False),
        sa.Column("account_codes", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("sheets", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("applicable_standard", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("version", sa.Integer, nullable=False, server_default=sa.text("1")),
        sa.Column("source_origin", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "cycle IN ('A','B','C','D','E','F','G','H','I','J','K','L','M','N','S')",
            name="ck_wp_template_registry_cycle",
        ),
    )
    op.create_index("idx_wp_template_registry_cycle", "wp_template_registry", ["cycle"])
    op.create_index("idx_wp_template_registry_updated", "wp_template_registry", [sa.text("updated_at DESC")])
    op.create_index(
        "idx_wp_template_registry_account_codes",
        "wp_template_registry",
        ["account_codes"],
        postgresql_using="gin",
    )

    # ─── Data migration: dual-source merge ───────────────────────────────
    _migrate_data()


def downgrade() -> None:
    op.drop_index("idx_wp_template_registry_account_codes", table_name="wp_template_registry")
    op.drop_index("idx_wp_template_registry_updated", table_name="wp_template_registry")
    op.drop_index("idx_wp_template_registry_cycle", table_name="wp_template_registry")
    op.drop_table("wp_template_registry")


def _migrate_data() -> None:
    """Read from wp_account_mapping.json + step_sheet_mapping.json, merge, arbitrate conflicts, insert."""
    data_dir = Path(__file__).resolve().parent.parent.parent / "data"

    # ─── Load source A: wp_account_mapping.json ──────────────────────────
    source_a: dict[str, dict] = {}
    wp_account_path = data_dir / "wp_account_mapping.json"
    if wp_account_path.exists():
        with wp_account_path.open("r", encoding="utf-8") as f:
            raw = json.load(f)
        mappings = raw.get("mappings", []) if isinstance(raw, dict) else (raw if isinstance(raw, list) else [])
        for m in mappings:
            code = m.get("wp_code", "")
            if not code or "-" in code:
                continue
            if code in source_a:
                continue
            cycle = (m.get("cycle") or code[0]).upper()
            if cycle not in VALID_CYCLES:
                cycle = code[0].upper() if code[0].upper() in VALID_CYCLES else "S"
            source_a[code] = {
                "wp_code": code,
                "wp_name": m.get("wp_name", ""),
                "cycle": cycle,
                "account_codes": m.get("account_codes", []) or [],
                "sheets": [],
                "applicable_standard": [],
            }

    # ─── Load source B: step_sheet_mapping.json ──────────────────────────
    source_b: dict[str, dict] = {}
    step_sheet_path = data_dir / "step_sheet_mapping.json"
    if step_sheet_path.exists():
        with step_sheet_path.open("r", encoding="utf-8") as f:
            raw = json.load(f)
        mappings_dict = raw.get("mappings", {}) if isinstance(raw, dict) else {}
        for code, info in mappings_dict.items():
            if "-" in code:
                continue
            cycle = code[0].upper() if code else "S"
            if cycle not in VALID_CYCLES:
                cycle = "S"
            available_sheets = info.get("available_sheets", []) or []
            sheets_structured = [
                {"name": s, "is_aux": _is_aux_sheet(s), "sort_order": i}
                for i, s in enumerate(available_sheets)
            ]
            source_b[code] = {
                "wp_code": code,
                "wp_name": info.get("wp_name", ""),
                "cycle": cycle,
                "account_codes": [],
                "sheets": sheets_structured,
                "applicable_standard": [],
            }

    # ─── Merge with conflict arbitration ─────────────────────────────────
    all_codes = set(source_a.keys()) | set(source_b.keys())
    rows_to_insert: list[dict] = []

    for code in sorted(all_codes):
        a = source_a.get(code)
        b = source_b.get(code)

        if a and not b:
            rows_to_insert.append({**a, "source_origin": "wp_account_mapping"})
        elif b and not a:
            rows_to_insert.append({**b, "source_origin": "step_sheet_mapping"})
        else:
            # Both sources have this wp_code — arbitrate conflicts
            merged = {
                "wp_code": code,
                "wp_name": b["wp_name"] or a["wp_name"],
                "cycle": a["cycle"],  # prefer source A for cycle (has explicit cycle field)
            }

            # sheets: step_sheet_mapping wins (sheet 全集权威源)
            if a["sheets"] != b["sheets"]:
                logger.warning(
                    "wp_template_registry migrate conflict: wp_code=%s, field=%s, json_a=%s, json_b=%s, taken=%s",
                    code, "sheets", str(a["sheets"])[:100], str(b["sheets"])[:100], "step_sheet_mapping",
                )
            merged["sheets"] = b["sheets"]

            # account_codes: take union
            a_codes = set(a.get("account_codes") or [])
            b_codes = set(b.get("account_codes") or [])
            union_codes = sorted(a_codes | b_codes)
            if a_codes != b_codes and (a_codes and b_codes):
                logger.warning(
                    "wp_template_registry migrate conflict: wp_code=%s, field=%s, json_a=%s, json_b=%s, taken=%s",
                    code, "account_codes", str(list(a_codes))[:100], str(list(b_codes))[:100], "union",
                )
            merged["account_codes"] = union_codes

            # applicable_standard: take union
            a_std = set(a.get("applicable_standard") or [])
            b_std = set(b.get("applicable_standard") or [])
            union_std = sorted(a_std | b_std)
            if a_std != b_std and (a_std and b_std):
                logger.warning(
                    "wp_template_registry migrate conflict: wp_code=%s, field=%s, json_a=%s, json_b=%s, taken=%s",
                    code, "applicable_standard", str(list(a_std))[:100], str(list(b_std))[:100], "union",
                )
            merged["applicable_standard"] = union_std

            merged["source_origin"] = "merged"
            rows_to_insert.append(merged)

    # ─── Bulk insert ─────────────────────────────────────────────────────
    if rows_to_insert:
        table = sa.table(
            "wp_template_registry",
            sa.column("wp_code", sa.String),
            sa.column("wp_name", sa.String),
            sa.column("cycle", sa.String),
            sa.column("account_codes", JSONB),
            sa.column("sheets", JSONB),
            sa.column("applicable_standard", JSONB),
            sa.column("version", sa.Integer),
            sa.column("source_origin", sa.String),
        )
        op.bulk_insert(table, [
            {
                "wp_code": r["wp_code"],
                "wp_name": r["wp_name"],
                "cycle": r["cycle"],
                "account_codes": json.dumps(r["account_codes"]),
                "sheets": json.dumps(r["sheets"]),
                "applicable_standard": json.dumps(r["applicable_standard"]),
                "version": 1,
                "source_origin": r["source_origin"],
            }
            for r in rows_to_insert
        ])
    logger.info("wp_template_registry: inserted %d rows from dual-source merge", len(rows_to_insert))


def _is_aux_sheet(name: str) -> bool:
    """Determine if a sheet is auxiliary (GT_Custom, 修订前, 示例, 提示)."""
    aux_markers = ("GT_Custom", "(修订前)", "(示例)", "(提示)")
    return any(marker in name for marker in aux_markers)
