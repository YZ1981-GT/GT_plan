"""附注 K 段首码 ↔ `report_config` **连库**对账（Property 39）。

Requirement 11.2 明令「`report_row_code` SHALL 与 `report_config` 对账后填写，
SHALL NOT 按行名猜」。故本守卫**必须连真实库**：静态表只能证明「脚本里写了什么」，
证明不了「那个码在报表配置里确实是这一行」。

判据取自 `fix_note_k_report_row_codes.PLAN`（唯一真源）：

- 每个 ``stamps`` 项：码在**该变体的两个准则**下必须存在，且 ``row_name`` 与声明的
  ``report_row_name`` 逐字相等 ⇒ 拦「码存在但指的是别的行」（平台已有 `BS-016`
  两侧异义、`BS-022/025/026` 连续偏移一位的先例）。
- 每个 ``no_code`` 项：该行名在**该变体**下必须**零命中** ⇒ 这是「宁缺勿造」的正面
  举证。若哪天 `report_config` 补了这行，本守卫打红，提醒去补码而不是让它继续空着。

🔴 连不上库时**判红而非 skip**（与 `test_k_cycle_row_code_evidence` 同规矩）：
skip 会让整组判据静默空转，而这组判据正是「不许按行名猜」的唯一执行者。

🔴 一次性取全部快照（单个 `asyncio.run`）：每个测试各自 `async` 会污染共享连接池，
第二个起报 ``NoneType has no attribute send``。

spec: .kiro/specs/k-cycle-extraction-formula-and-disclosure-closure/
      Requirements 11.1, 11.2, 11.5 / Property 39
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

_ROOT = Path(__file__).resolve().parents[3]
_FIX = _ROOT / "backend/scripts/fix/fix_note_k_report_row_codes.py"

#: 变体 → `report_config.applicable_standard` 的两个取值
_STANDARDS = {
    "listed": ("listed_consolidated", "listed_standalone"),
    "soe": ("soe_consolidated", "soe_standalone"),
}


def _load_fix_module():
    spec = importlib.util.spec_from_file_location("_k_rowcode_fix", _FIX)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_k_rowcode_fix"] = mod
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.modules.pop("_k_rowcode_fix", None)
    return mod


_FIXMOD = _load_fix_module()
PLAN = _FIXMOD.PLAN


@dataclass
class _Snapshot:
    ok: bool = False
    error: str = ""
    #: ``{(standard, row_code): row_name}``
    by_code: dict[tuple[str, str], str] = field(default_factory=dict)
    #: ``{(standard, like_pattern): 命中行数}``
    like_hits: dict[tuple[str, str], int] = field(default_factory=dict)


def _database_url() -> str:
    from app.core.config import settings

    return str(settings.DATABASE_URL)


async def _load() -> _Snapshot:
    snap = _Snapshot()
    codes = sorted(
        {
            (std, s["row_code"])
            for e in PLAN
            for s in e["stamps"]
            for std in _STANDARDS[e["variant"]]
        }
    )
    likes = sorted(
        {
            (std, n["absent_name_like"])
            for e in PLAN
            for n in e["no_code"]
            for std in _STANDARDS[e["variant"]]
        }
    )
    engine = create_async_engine(_database_url(), poolclass=None, future=True)
    try:
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as sess:
            for std, code in codes:
                rows = (
                    await sess.execute(
                        text(
                            "SELECT row_name FROM report_config "
                            "WHERE is_deleted = false AND applicable_standard = :std "
                            "AND row_code = :code"
                        ),
                        {"std": std, "code": code},
                    )
                ).scalars().all()
                if rows:
                    snap.by_code[(std, code)] = str(rows[0])
            for std, pat in likes:
                n = (
                    await sess.execute(
                        text(
                            "SELECT COUNT(*) FROM report_config "
                            "WHERE is_deleted = false AND applicable_standard = :std "
                            "AND row_name LIKE :pat"
                        ),
                        {"std": std, "pat": pat},
                    )
                ).scalar()
                snap.like_hits[(std, pat)] = int(n or 0)
        snap.ok = True
    except Exception as exc:  # noqa: BLE001 - 连库失败要带原因判红
        snap.error = f"{type(exc).__name__}: {exc}"
    finally:
        await engine.dispose()
    return snap


_SNAP: _Snapshot = asyncio.run(_load())


def _require_db() -> None:
    if not _SNAP.ok:
        pytest.fail(
            f"无法连库取 report_config 快照：{_SNAP.error}\n"
            "本守卫按 Requirement 11.2 必须连库（禁静态冻结表），"
            "连不上时判红而非 skip —— skip 会让整组判据静默空转。"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Property 39：段首码在 report_config 里确实是声明的那一行
# ─────────────────────────────────────────────────────────────────────────────


def test_plan_is_not_empty() -> None:
    """反向自检：PLAN 为空会让下面全部断言空转。"""
    assert len(PLAN) >= 4, f"PLAN 只有 {len(PLAN)} 条，真源可疑"
    assert sum(len(e["stamps"]) for e in PLAN) >= 7


def test_every_stamp_code_exists_in_report_config() -> None:
    _require_db()
    missing = [
        (e["variant"], e["section"], s["label"], s["row_code"], std)
        for e in PLAN
        for s in e["stamps"]
        for std in _STANDARDS[e["variant"]]
        if (std, s["row_code"]) not in _SNAP.by_code
    ]
    assert not missing, (
        f"段首码在 report_config 该准则下不存在（永不勾稽）：{missing}"
    )


def test_every_stamp_code_points_at_declared_row_name() -> None:
    """码必须指向声明的那一行 —— 拦「码存在但异义」。"""
    _require_db()
    bad = []
    for e in PLAN:
        for s in e["stamps"]:
            want = s["report_row_name"]
            for std in _STANDARDS[e["variant"]]:
                got = _SNAP.by_code.get((std, s["row_code"]))
                if got is not None and got != want:
                    bad.append(
                        (e["variant"], e["section"], s["label"], s["row_code"], std, got, want)
                    )
    assert not bad, (
        "段首码在 report_config 里指的是别的行（形态同 BS-016 两侧异义 / "
        f"BS-022~026 偏移一位）：{bad}"
    )


def test_no_code_rows_really_have_zero_hits() -> None:
    """「宁缺勿造」的正面举证：登记无码的行名在本变体下必须零命中。

    哪天 `report_config` 补了这行，本守卫打红 —— 那时应当去补码，
    而不是让主表那一行永远没有 owner。
    """
    _require_db()
    unexpected = [
        (e["variant"], e["section"], n["label"], std, _SNAP.like_hits[(std, n["absent_name_like"])])
        for e in PLAN
        for n in e["no_code"]
        for std in _STANDARDS[e["variant"]]
        if _SNAP.like_hits.get((std, n["absent_name_like"]), 0) > 0
    ]
    assert not unexpected, (
        "登记为「report_config 零命中」的行名其实有命中 —— 登记理由失效，"
        f"应改为补码：{unexpected}"
    )


def test_snapshot_really_queried_something() -> None:
    """反向自检：快照必须真取到数据。

    没有这条，`by_code` 全空时上面两条会「无对象可查」而全绿 —— 那是最典型的
    连库守卫空转形态（fail-open 掩盖接线错误）。
    """
    _require_db()
    assert _SNAP.by_code, "report_config 快照为空 —— 查询或连接接错了"
    assert len(_SNAP.by_code) >= 8, f"只取到 {len(_SNAP.by_code)} 条码，判据源可疑"
    assert _SNAP.like_hits, "无码行的 LIKE 计数为空 —— 查询没跑"


# ─────────────────────────────────────────────────────────────────────────────
# Requirement 11.1 / 11.5：模板侧齐备 + 豁免登记（幂等脚本已覆盖，此处只做端到端）
# ─────────────────────────────────────────────────────────────────────────────


def test_templates_carry_all_planned_codes() -> None:
    """模板里 PLAN 的每个码都已落地（离线，端到端复核脚本 `--check`）。"""
    import json

    docs = {
        "listed": json.loads(
            (_ROOT / "backend/data/note_template_listed.json").read_text(encoding="utf-8")
        ),
        "soe": json.loads(
            (_ROOT / "backend/data/note_template_soe.json").read_text(encoding="utf-8")
        ),
    }
    missing = []
    for e in PLAN:
        sec = next(
            (
                s
                for s in docs[e["variant"]]["sections"]
                if str(s.get("section_number") or "").strip() == e["section"]
            ),
            None,
        )
        tbl = next(
            (
                t
                for t in (sec or {}).get("tables") or []
                if str(t.get("name") or "").strip() == e["table"]
            ),
            None,
        )
        rows = (tbl or {}).get("rows") or []
        for s in e["stamps"]:
            hit = next(
                (
                    r
                    for r in rows
                    if isinstance(r, dict)
                    and str(r.get("label") or "").strip() == s["label"]
                ),
                None,
            )
            if hit is None or str(hit.get("report_row_code") or "") != s["row_code"]:
                missing.append((e["variant"], e["section"], s["label"], s["row_code"]))
    assert not missing, f"模板缺段首码（owner 推送会整表 fail-closed）：{missing}"


def test_shared_tables_become_locatable_after_stamping() -> None:
    """端到端：补码后 `find_segment` 对每个 owner 都能定位到段。

    这条才是 Requirement 11.1 的真正验收面 —— 「模板里有这个字符串」不等于
    「运行期定位得到段」。用生产函数 `resolve_segment_window` 直接验。
    """
    from app.services.note_shared_table_segments import resolve_segment_window

    bad = []
    for e in PLAN:
        for s in e["stamps"]:
            seg = resolve_segment_window(
                e["variant"], e["section"], e["table"], s["row_code"]
            )
            if seg is None or seg.start >= seg.data_end:
                bad.append((e["variant"], e["section"], s["label"], s["row_code"], seg))
    assert not bad, f"补码后仍定位不到可写段（fail-closed 未解除）：{bad}"


def test_row_code_fix_script_is_idempotent() -> None:
    """`fix_note_k_report_row_codes.py --check` 必须归零。

    它同时看守三件事：码齐备 / 无码行没被偷偷造码 / 覆盖面（多 owner 章节都进了
    补码计划、单 owner 章节都登记了豁免，owner 数从
    `note_workpaper_sync_registry.json` 反查）。
    """
    import subprocess

    r = subprocess.run(
        [sys.executable, str(_FIX), "--check"],
        cwd=str(_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert r.returncode == 0, (
        f"段首码幂等脚本 --check 未归零（exit={r.returncode}）：\n"
        f"{(r.stdout or '')[-1500:]}"
    )


def test_shared_table_manifest_has_no_drift() -> None:
    """段集合变了必须同步重生成清单（否则前端「该不该带 `_row_scope`」判据陈旧）。"""
    import subprocess

    r = subprocess.run(
        [
            sys.executable,
            str(_ROOT / "backend/scripts/gen/gen_note_shared_table_segments.py"),
            "--check",
        ],
        cwd=str(_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert r.returncode == 0, (
        "共享表清单与模板漂移 —— 补码后须重跑 --write：\n"
        f"{(r.stdout or '')[-1500:]}"
    )


def test_total_rows_stay_outside_writable_window() -> None:
    """`合计` 行必须落在可写区之外 —— owner 推送不得删掉表级合计。"""
    from app.services.note_shared_table_segments import (
        resolve_segment_window,
        template_rows,
    )

    checked = 0
    for e in PLAN:
        rows = template_rows(e["variant"], e["section"], e["table"])
        assert rows, f"{e['variant']} §{e['section']} 取不到模板行"
        last = rows[-1]
        if str(last.get("row_type") or "") != "total":
            continue
        for s in e["stamps"]:
            seg = resolve_segment_window(
                e["variant"], e["section"], e["table"], s["row_code"]
            )
            if seg is None:
                continue
            assert seg.data_end <= len(rows) - 1, (
                f"{e['variant']} §{e['section']} 段 {s['row_code']} 的可写区盖住了合计行"
            )
            checked += 1
    assert checked >= 6, f"只核到 {checked} 个段，判据可疑"
