"""解引用迁移脚本行为守卫 —— Wave 5 Task 20

spec: workpaper-import-export-lifecycle-closure（R6.3~R6.6、R6.8）

## 判据为什么不连真库

`fix_wp_template_deref.py` 的破坏性部分（`_apply` / `_rollback`）已在 2026-08-12
对真实库跑过并复核（956/956 迁移、0 冲突、0 失败、回滚 3/3 闭环）。本文件守的是
**纯函数与门控逻辑**，用临时目录与构造数据即可完整覆盖：

* `_build_plan` —— 计划构造（幂等跳过 / 阻塞归类 / 目标去重 / 越界防护）
* `_target_rel` —— 路径形态（与既有惯例一致）
* `_resolve_source` —— 多基准解析
* `--apply` 无 `--confirm-destructive` 的门控
* 台账结构（回滚依赖它，字段缺一就回滚不了）

连真库的那两条状态断言在 `test_wp_templates_readonly.py`（用一次
`asyncio.run` 取快照，避免多次建连接池炸 event loop）。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[3]
_SCRIPT_REL = "backend/scripts/fix/fix_wp_template_deref.py"

sys.path.insert(0, str(_REPO / "backend"))

from scripts.fix.fix_wp_template_deref import (  # noqa: E402
    TEMPLATE_MARKER,
    _build_plan,
    _is_template_ref,
    _resolve_source,
    _safe_name,
    _target_rel,
)


# ---------------------------------------------------------------------------
# 路径形态
# ---------------------------------------------------------------------------


def test_target_rel_matches_existing_convention() -> None:
    """目标路径必须是既有惯例 `workpapers/{cycle}/{code}.xlsx`。

    平台里已有 101 份正常底稿是这个形态；换一套命名会让同目录下两种形态并存。
    """
    got = _target_rel("PID", "D", "D2-2")
    assert got == "storage/projects/PID/workpapers/D/D2-2.xlsx", got
    # POSIX 分隔符（存库用，Windows 反斜杠会让跨平台解析出岔）
    assert "\\" not in got


def test_target_rel_falls_back_when_cycle_blank() -> None:
    """cycle 缺失时用 `_` 占位而不是拼出 `//`（空段会让路径退化）。"""
    got = _target_rel("PID", "", "X1")
    assert got == "storage/projects/PID/workpapers/_/X1.xlsx", got
    assert "//" not in got


@pytest.mark.parametrize(
    "name,ok",
    [
        ("D2-2", True),
        ("C24", True),
        ("", False),
        (".", False),
        ("..", False),          # 路径穿越
        ("a/b", False),         # 分隔符
        ("a\\b", False),
        ('a"b', False),         # Windows 非法字符
        ("a:b", False),
    ],
)
def test_safe_name_rejects_traversal_and_illegal_chars(name: str, ok: bool) -> None:
    """名称合法性 —— 防 `..` 穿越与非法字符写进磁盘。"""
    assert _safe_name(name) is ok


# ---------------------------------------------------------------------------
# 源解析
# ---------------------------------------------------------------------------


def test_resolve_source_handles_absolute_and_missing(tmp_path: Path) -> None:
    real = tmp_path / "x.xlsx"
    real.write_bytes(b"abc")
    assert _resolve_source(str(real)) == real
    assert _resolve_source(str(tmp_path / "nope.xlsx")) is None
    assert _resolve_source("") is None
    assert _resolve_source("   ") is None


def test_is_template_ref_normalises_separators() -> None:
    """反斜杠路径也要能认出 —— 库里既有 `wp_templates\\D\\x.xlsx` 形态。"""
    assert _is_template_ref(f"{TEMPLATE_MARKER}/D/D1.xlsx")
    assert _is_template_ref("wp_templates\\D\\D1 应收票据.xlsx")
    assert not _is_template_ref("storage/projects/p/workpapers/D/D1.xlsx")
    assert not _is_template_ref(None)
    assert not _is_template_ref("")


# ---------------------------------------------------------------------------
# 计划构造
# ---------------------------------------------------------------------------


def _row(tmp_path: Path, **kw: object) -> dict[str, object]:
    src = tmp_path / f"{kw.get('wp_code', 'X')}.xlsx"
    if not src.exists():
        src.write_bytes(b"data")
    base = {
        "wp_id": "id-1",
        "project_id": "proj-1",
        "file_path": f"{TEMPLATE_MARKER}/{src.name}",
        "wp_code": "D1",
        "audit_cycle": "D",
        "cr_n": 0,
    }
    base.update(kw)
    # 让 _resolve_source 能找到：用绝对路径且含 marker
    if "file_path" not in kw:
        marker_dir = tmp_path / TEMPLATE_MARKER
        marker_dir.mkdir(exist_ok=True)
        real = marker_dir / src.name
        real.write_bytes(b"data")
        base["file_path"] = str(real)
    return base


def test_plan_is_idempotent_for_already_migrated(tmp_path: Path) -> None:
    """已不指向模板库的记录直接跳过 —— 幂等的基础（R6.4）。"""
    rows = [
        _row(tmp_path, wp_id="a"),
        {
            "wp_id": "b",
            "project_id": "proj-1",
            "file_path": "storage/projects/proj-1/workpapers/D/D1.xlsx",
            "wp_code": "D1",
            "audit_cycle": "D",
            "cr_n": 0,
        },
    ]
    built = _build_plan(rows)
    assert [i["wp_id"] for i in built["plan"]] == ["a"]
    assert built["skipped_not_template"] == 1


def test_plan_blocks_missing_source(tmp_path: Path) -> None:
    """源文件不存在 ⇒ 记 blocked，不放进 plan（复制不了就别改库）。"""
    rows = [
        {
            "wp_id": "a",
            "project_id": "p",
            "file_path": f"{TEMPLATE_MARKER}/does-not-exist.xlsx",
            "wp_code": "D1",
            "audit_cycle": "D",
            "cr_n": 0,
        }
    ]
    built = _build_plan(rows)
    assert built["plan"] == []
    assert len(built["blocked"]) == 1
    assert "源文件不存在" in built["blocked"][0]["reason"]


def test_plan_blocks_missing_wp_code(tmp_path: Path) -> None:
    """wp_code 缺失 ⇒ blocked（否则目标名会拼成 `None.xlsx`）。"""
    rows = [_row(tmp_path, wp_id="a", wp_code="")]
    built = _build_plan(rows)
    assert built["plan"] == []
    assert "wp_code 缺失" in built["blocked"][0]["reason"]


def test_plan_blocks_target_collision(tmp_path: Path) -> None:
    """两条记录算出同一目标 ⇒ 第二条 blocked，绝不让两份底稿写同一文件。"""
    rows = [
        _row(tmp_path, wp_id="a", wp_code="D1", audit_cycle="D"),
        _row(tmp_path, wp_id="b", wp_code="D1", audit_cycle="D"),
    ]
    built = _build_plan(rows)
    assert len(built["plan"]) == 1
    assert len(built["blocked"]) == 1
    assert "冲突" in built["blocked"][0]["reason"]


def test_plan_gives_each_project_its_own_copy(tmp_path: Path) -> None:
    """🔴 同一源被多项目共享时，必须产出**互不相同**的目标（R6.3 核心）。

    实测迁移前 303 个源路径被 2~4 个项目共享 —— 这正是要解除的问题。
    """
    marker_dir = tmp_path / TEMPLATE_MARKER
    marker_dir.mkdir(exist_ok=True)
    shared = marker_dir / "I4.xlsx"
    shared.write_bytes(b"shared")

    rows = [
        {
            "wp_id": f"id-{i}",
            "project_id": f"proj-{i}",
            "file_path": str(shared),
            "wp_code": "I4",
            "audit_cycle": "I",
            "cr_n": 0,
        }
        for i in range(4)
    ]
    built = _build_plan(rows)
    targets = {i["new_path"] for i in built["plan"]}
    assert len(built["plan"]) == 4
    assert len(targets) == 4, f"4 个项目应得 4 个独立目标，实际 {targets}"
    assert all("/workpapers/I/I4.xlsx" in t for t in targets)


def test_plan_records_out_of_scope_missing_files(tmp_path: Path) -> None:
    """非模板库但文件也不存在的记录 ⇒ 登记 out_of_scope（既存缺陷，不处理）。"""
    rows = [
        {
            "wp_id": "a",
            "project_id": "p",
            "file_path": "storage/projects/p/workpapers/B23-11.xlsx",
            "wp_code": "B23-11",
            "audit_cycle": "B",
            "cr_n": 0,
        }
    ]
    built = _build_plan(rows)
    assert built["plan"] == []
    assert len(built["out_of_scope"]) == 1
    assert "无源可复制" in built["out_of_scope"][0]["reason"]


# ---------------------------------------------------------------------------
# 门控（R6.8）
# ---------------------------------------------------------------------------


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, _SCRIPT_REL, *args],
        cwd=str(_REPO), check=False, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=600,
        # 🔴 `PYTHONIOENCODING` 不是多余参数，删掉本文件在 Windows 上立刻变红。
        # `capture_output=True` 下子进程 stdout 是管道，Windows 上 CPython 对管道
        # 按 locale 编码（cp936/GBK）写出，而不是 UTF-8；父进程这边的
        # `encoding="utf-8"` 只管解码那一半，管不到子进程用什么编码写。
        # ⇒ 脚本的中文文案按 GBK 编码、按 UTF-8 解码，下面 `"拒绝执行" in out`
        # 一类断言收到的是 `'�ܾ�ִ��...'` 乱码，判据被编码问题打红（假红）。
        # Linux CI 的 locale 本身是 UTF-8 故不暴露 —— Windows 本地专属，
        # 属 memory 已记的「PS/子进程把中文腌成乱码」编码坑。
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )


def test_apply_without_confirm_is_refused() -> None:
    """🔴 `--apply` 不带 `--confirm-destructive` 必须拒绝且 exit 非 0。

    这是唯一挡在 125 MB 复制 + 956 条改库前面的闸门。
    """
    proc = _run(["--apply"])
    assert proc.returncode != 0, "无确认参数却成功返回 ⇒ 门控失效"
    out = proc.stdout + proc.stderr
    assert "拒绝执行" in out
    assert "--confirm-destructive" in out


def test_mode_flags_are_mutually_exclusive() -> None:
    """四档模式互斥 —— 同时给两个应被 argparse 拒绝，避免语义含混。"""
    proc = _run(["--check", "--dry-run"])
    assert proc.returncode != 0


def test_check_mode_is_read_only_and_reports(tmp_path: Path) -> None:
    """`--check` 只读且产出报告（含 verdict 分布）。

    🔴 必须传 `--out tmp_path`：不传的话每跑一次测试就往版本库
    `backend/scripts/fix/_ledgers/` 塞一个 JSON —— 实测半小时累积 20 个。
    只读诊断没有留存价值，真凭证是 dry-run / apply / rollback 的台账。
    """
    proc = _run(["--check", "--out", str(tmp_path)])
    assert proc.returncode == 0, proc.stdout + proc.stderr
    out = proc.stdout + proc.stderr
    assert "报告已落盘" in out
    assert "verdict_before" in out
    produced = list(tmp_path.glob("deref_check_*.json"))
    assert len(produced) == 1, f"应恰好产出 1 个报告，实际 {produced}"


def test_check_does_not_pollute_ledger_dir_when_out_given(tmp_path: Path) -> None:
    """`--out` 生效性反向自检：给了 `--out` 就不该再往版本库目录写。

    防「加了参数但代码没用它」—— 那是 memory 记的「additive 注入即死代码」。
    """
    ledger_dir = _REPO / "backend" / "scripts" / "fix" / "_ledgers"
    before = {p.name for p in ledger_dir.glob("deref_check_*.json")} if ledger_dir.is_dir() else set()
    _run(["--check", "--out", str(tmp_path)])
    after = {p.name for p in ledger_dir.glob("deref_check_*.json")} if ledger_dir.is_dir() else set()
    assert after == before, f"--out 未生效，版本库目录多了：{sorted(after - before)}"


def test_no_mode_flag_is_rejected() -> None:
    """不给任何模式必须报错 —— 防「裸跑即执行」。"""
    proc = _run([])
    assert proc.returncode != 0


# ---------------------------------------------------------------------------
# 台账结构（回滚依赖它）
# ---------------------------------------------------------------------------


def test_apply_ledger_has_rollback_fields() -> None:
    """台账每条必须含回滚所需字段 —— 缺一就回滚不了。

    真实迁移已产出台账（2026-08-12），此处校验其结构而非重跑迁移。
    """
    ledger_dir = _REPO / "backend" / "scripts" / "fix" / "_ledgers"
    ledgers = sorted(ledger_dir.glob("deref_apply_*.json"))
    if not ledgers:
        pytest.skip("尚无 apply 台账（迁移未执行过）")

    # 🔴 取**有 migrated 条目**的最新台账，而不是单纯最新的一份。
    # 迁移已完成后再跑 apply 会因幂等而 migrated=[]，若取最新就永久 skip ——
    # 一条永久 skip 的断言等于不存在（假绿的一种）。
    entries: list[dict[str, object]] = []
    picked: Path | None = None
    for lg in reversed(ledgers):
        data = json.loads(lg.read_text(encoding="utf-8"))
        assert "migrated" in data, f"{lg.name} 缺 migrated 字段"
        if data["migrated"]:
            entries, picked = data["migrated"], lg
            break
    assert picked is not None, (
        f"{len(ledgers)} 个 apply 台账全部 migrated 为空 ⇒ 迁移从未真正写过数据，"
        "回滚字段无从校验"
    )

    required = {"wp_id", "old_path", "new_path", "sha256_before", "sha256_after", "ts"}
    for e in entries[:20]:
        missing = required - set(e)
        assert not missing, f"台账条目缺字段 {missing}：{e}"
        # 回滚要靠 old_path 指回模板库
        assert TEMPLATE_MARKER in e["old_path"].replace("\\", "/")
        assert e["sha256_before"] == e["sha256_after"], (
            "复制前后哈希应一致；不一致说明复制未完整却仍改了库"
        )


def test_ledger_records_out_of_scope_boundary() -> None:
    """台账必须写明**不做什么** —— 边界不写清，下次有人会以为漏了。

    只查 check / dryrun / apply 三类台账：`--rollback` 的报告是另一种结构
    （只有 reverted / failed / ledger），本就没有 `notes`。初版用
    `deref_*.json` 通配取到最新的 rollback 报告 ⇒ 假红。
    """
    ledger_dir = _REPO / "backend" / "scripts" / "fix" / "_ledgers"
    ledgers = sorted(
        p
        for pattern in ("deref_check_*.json", "deref_dryrun_*.json", "deref_apply_*.json")
        for p in ledger_dir.glob(pattern)
    )
    if not ledgers:
        pytest.skip("尚无迁移类台账")

    data = json.loads(ledgers[-1].read_text(encoding="utf-8"))
    notes = " ".join(data.get("notes") or [])
    assert notes, f"{ledgers[-1].name} 没有 notes 字段 ⇒ 边界未登记"
    assert "1564" in notes, "台账未写明空 file_path 的 1564 份不在范围"
    assert "checklist" in notes.lower(), "台账未写明 checklist 未被处理"


def test_rollback_ledger_shape_is_distinct() -> None:
    """回滚报告结构与迁移台账不同 —— 明确记下来，防上一条再被通配符误伤。"""
    ledger_dir = _REPO / "backend" / "scripts" / "fix" / "_ledgers"
    rollbacks = sorted(ledger_dir.glob("deref_rollback_*.json"))
    if not rollbacks:
        pytest.skip("尚无回滚报告")
    data = json.loads(rollbacks[-1].read_text(encoding="utf-8"))
    assert {"reverted", "failed", "ledger"} <= set(data), (
        f"回滚报告缺字段：{sorted(data)}"
    )
    assert "notes" not in data, (
        "回滚报告出现了 notes ⇒ 结构变了，需同步 test_ledger_records_out_of_scope_boundary "
        "的 glob 范围"
    )
