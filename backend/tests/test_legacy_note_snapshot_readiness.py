"""legacy 附注快照迁移就绪度守卫（不连库，可进 CI）。

spec: note-template-columns-and-legacy-snapshot-closure（Task 3）

钉死三件事
----------
1. **四类判定边界**（`manual` / `single_row` / `by_name` / `positional`）—— 用替身
   fixture 覆盖，防迁移器被「顺手优化」后把不安全的章节放进自动迁移。
2. **列头安全闸不可绕过** —— `select_migratable(require_columns=True)` 必须排除
   「模板无 columns」的章节；`--require-columns` 默认开启；`positional` 不在
   `ALWAYS_MIGRATABLE_KINDS` 里。
3. **备份/回滚往返无损** —— `build_migrated_table_data` → `build_rollback_table_data`
   逐字节还原（时间戳只落在被弹出的 `_legacy_backup` 里，不污染还原结果）。

另外覆盖本 spec 新增的 `classify_legacy_note`（探针纯函数）对「纯表名漂移」的判定，
它是 Wave 2 `legacy_aliases` 与 Wave 4 `by_alias` 的判据来源。
"""

from __future__ import annotations

import copy
import importlib.util
import inspect
import re
import sys
from pathlib import Path
from typing import Any

import pytest

_HERE = Path(__file__).resolve()
BACKEND_ROOT = _HERE.parents[1]

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


def _load(path: Path, name: str):
    assert path.exists(), f"文件缺失：{path}"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


MIG = _load(
    BACKEND_ROOT / "scripts" / "fix" / "migrate_legacy_note_snapshots.py",
    "note_legacy_migrator_for_readiness_guard",
)
PROBE = _load(
    BACKEND_ROOT / "scripts" / "diagnose" / "diagnose_note_columns_coverage.py",
    "note_columns_probe_for_readiness_guard",
)


# ---------------------------------------------------------------------------
# 替身构造
# ---------------------------------------------------------------------------


def _row(label: str, row_type: str = "data") -> dict[str, Any]:
    return {"label": label, "row_type": row_type, "values": {}}


def _tpl_table(name: str, *, columns: bool = True, headers: list[str] | None = None):
    t: dict[str, Any] = {"name": name, "headers": headers or ["项目", "期末余额"]}
    if columns:
        t["columns"] = [
            {"key": "项目", "label": "项目", "flat": True},
            {"key": "期末余额", "label": "期末余额", "flat": True},
        ]
    return t


def _plan(
    table_data: dict[str, Any],
    template_tables: list[dict[str, Any]] | None,
    *,
    note_section: str = "五、9",
):
    return MIG.build_note_plan(
        note_id="n1",
        project="p1",
        note_section=note_section,
        section_title="替身章节",
        table_data=table_data,
        template_tables=template_tables,
    )


# ---------------------------------------------------------------------------
# Property 7：四类判定边界
# ---------------------------------------------------------------------------


class TestPlanKindBoundaries:
    def test_by_name_when_all_names_are_business_names(self) -> None:
        td = {
            "_tables": [
                {"name": "交易性金融资产", "rows": [_row("a"), _row("b")]},
                {"name": "应收款项融资", "rows": [_row("c")]},
            ]
        }
        tpl = [_tpl_table("交易性金融资产"), _tpl_table("应收款项融资")]
        p = _plan(td, tpl)
        assert p.kind == "by_name", p.reason
        assert [t.target_name for t in p.tables] == ["交易性金融资产", "应收款项融资"]

    def test_pure_name_drift_falls_back_to_positional(self) -> None:
        """表名漂移（快照名是表头首格泄漏）必判 ``positional``，不是 ``manual``。

        这是本 spec 收益最大的一块（108 个 section）：迁移器把它归 positional，
        需 ``--include-positional`` 才迁 → Wave 2 写 ``legacy_aliases`` 后可升级。
        """
        td = {
            "_tables": [
                {"name": "项  目", "headers": ["项  目", "期末"], "rows": [_row("a")]},
                {"name": "种  类", "headers": ["种  类", "期末"], "rows": [_row("b")]},
            ]
        }
        tpl = [_tpl_table("交易性金融资产"), _tpl_table("应收票据分类")]
        p = _plan(td, tpl)
        assert p.kind == "positional", f"应判 positional，实为 {p.kind}：{p.reason}"
        assert "按序对齐" in p.reason
        # 按序对齐后目标名取的是模板名
        assert [t.target_name for t in p.tables] == ["交易性金融资产", "应收票据分类"]

    def test_renaming_one_snapshot_table_upgrades_to_by_name(self) -> None:
        """反向自检：把快照表名改成模板真名后必须由 ``positional`` 升为 ``by_name``。

        这条证明「正名/alias 能带来升级」不是空想，也证明 positional 判定不是死代码。
        """
        tpl = [_tpl_table("交易性金融资产"), _tpl_table("应收票据分类")]
        drift = {
            "_tables": [
                {"name": "项  目", "headers": ["项  目"], "rows": [_row("a")]},
                {"name": "种  类", "headers": ["种  类"], "rows": [_row("b")]},
            ]
        }
        assert _plan(drift, tpl).kind == "positional"

        renamed = copy.deepcopy(drift)
        renamed["_tables"][0]["name"] = "交易性金融资产"
        renamed["_tables"][0]["headers"] = ["项目"]
        renamed["_tables"][1]["name"] = "应收票据分类"
        renamed["_tables"][1]["headers"] = ["项目"]
        assert _plan(renamed, tpl).kind == "by_name"

    def test_duplicate_names_never_by_name(self) -> None:
        """重名必不判 ``by_name`` —— `sub_table_data` 以表名为键，重名会丢整表。"""
        td = {
            "_tables": [
                {"name": "其他应收款（续）", "rows": [_row("a")]},
                {"name": "其他应收款（续）", "rows": [_row("b")]},
            ]
        }
        tpl = [_tpl_table("其他应收款（续）"), _tpl_table("其他应收款（续2）")]
        p = _plan(td, tpl)
        assert p.kind != "by_name"
        assert p.kind == "positional"
        assert "重名" in p.reason

    def test_count_mismatch_with_unmatched_names_is_manual(self) -> None:
        td = {"_tables": [{"name": "项  目", "headers": ["项  目"], "rows": [_row("a")]}]}
        tpl = [_tpl_table("A"), _tpl_table("B")]
        p = _plan(td, tpl)
        assert p.kind == "manual"
        assert "无法安全对齐" in p.reason

    def test_by_name_does_not_require_equal_table_counts(self) -> None:
        """钉死一条容易误解的既有语义：``by_name`` **不要求**快照表数 == 模板表数。

        只要快照每个表名都是业务名、无重名、且都能在模板中命中，就判 ``by_name``
        并只迁这些表 —— 模板里多出来的表在附注里保持空骨架。写守卫/写迁移报告时
        别按「表数必须相等」推断类别。
        """
        td = {"_tables": [{"name": "A", "headers": ["项目"], "rows": [_row("a")]}]}
        p = _plan(td, [_tpl_table("A"), _tpl_table("B")])
        assert p.kind == "by_name"
        assert [t.target_name for t in p.tables] == ["A"]

    def test_rows_only_single_template_table_is_single_row(self) -> None:
        td = {"rows": [_row("a"), _row("b"), _row("h", "header_label")]}
        p = _plan(td, [_tpl_table("交易性金融资产")])
        assert p.kind == "single_row"
        assert p.tables[0].row_count == 2
        assert p.tables[0].dropped_header_label_rows == 1

    def test_rows_only_multi_template_tables_is_manual(self) -> None:
        td = {"rows": [_row("a")]}
        p = _plan(td, [_tpl_table("A"), _tpl_table("B")])
        assert p.kind == "manual"
        assert "无法确定归属" in p.reason

    def test_section_not_in_template_is_manual(self) -> None:
        p = _plan({"_tables": [{"name": "A", "rows": [_row("a")]}]}, [])
        assert p.kind == "manual"
        assert "模板中无此章节" in p.reason


# ---------------------------------------------------------------------------
# Property 8：列头安全闸
# ---------------------------------------------------------------------------


class TestRequireColumnsGate:
    def test_missing_template_columns_excludes_whole_section(self) -> None:
        td = {
            "_tables": [
                {"name": "A", "rows": [_row("a")]},
                {"name": "B", "rows": [_row("b")]},
            ]
        }
        # B 无 columns → 整章被排除（不得部分迁移）
        tpl = [_tpl_table("A"), _tpl_table("B", columns=False)]
        p = _plan(td, tpl)
        assert p.kind == "by_name"
        assert [t.columns_from_template for t in p.tables] == [True, False]

        picked, counters = MIG.select_migratable(
            [p], kinds=MIG.allowed_kinds(include_positional=False), require_columns=True
        )
        assert picked == []
        assert counters["skipped_no_columns"] == 1

    def test_gate_off_would_select_it_reverse_selfcheck(self) -> None:
        """反向自检：关掉闸门时该章节会被选中 —— 证明上一条不是恒排除的空转。"""
        td = {"_tables": [{"name": "A", "rows": [_row("a")]}]}
        p = _plan(td, [_tpl_table("A", columns=False)])
        picked, _ = MIG.select_migratable(
            [p], kinds=MIG.allowed_kinds(include_positional=False), require_columns=False
        )
        assert len(picked) == 1

    def test_positional_not_in_always_migratable(self) -> None:
        assert "positional" not in MIG.ALWAYS_MIGRATABLE_KINDS
        assert set(MIG.ALWAYS_MIGRATABLE_KINDS) == {"by_name", "single_row"}
        assert "positional" not in MIG.allowed_kinds(include_positional=False)
        assert "positional" in MIG.allowed_kinds(include_positional=True)

    def test_require_columns_defaults_to_true_in_cli(self) -> None:
        """CLI 默认必须开闸，且只提供 ``--no-require-columns`` 这一个关闭入口。"""
        src = inspect.getsource(MIG.main)
        src_nc = _strip_py_comments(src)
        assert "set_defaults(require_columns=True)" in src_nc, (
            "CLI 未把 require_columns 默认设为 True"
        )
        # 关闭入口恰一个，且带 🔴 语义的长 help；不得有短别名
        assert src_nc.count('"--no-require-columns"') == 1
        assert "--no-columns" not in src_nc, "出现了绕过安全闸的快捷别名"

    def test_apply_requires_confirm(self) -> None:
        src = _strip_py_comments(inspect.getsource(MIG))
        assert "_REFUSE_MSG" in src
        assert re.search(r"args\.confirm", src), "找不到 --confirm 校验"


def _strip_py_comments(src: str) -> str:
    """剥掉 ``#`` 行注释与三引号 docstring，防注释里的反例被数成真实代码。"""
    out: list[str] = []
    in_doc = False
    delim = ""
    for line in src.splitlines():
        s = line
        if in_doc:
            if delim in s:
                s = s.split(delim, 1)[1]
                in_doc = False
            else:
                continue
        while True:
            m = re.search(r'("""|\'\'\')', s)
            if not m:
                break
            d = m.group(1)
            rest = s[m.end() :]
            if d in rest:
                s = s[: m.start()] + rest.split(d, 1)[1]
                continue
            s = s[: m.start()]
            in_doc = True
            delim = d
            break
        s = re.sub(r"#.*$", "", s)
        out.append(s)
    return "\n".join(out)


def test_strip_py_comments_reverse_selfcheck() -> None:
    """反向自检：剥注释确实生效（原文含被禁字样、剥后不含）。"""
    sample = '''
def f():
    """禁用词 --no-columns 出现在 docstring 里"""
    # 禁用词 --no-columns 出现在行注释里
    return 1
'''
    assert "--no-columns" in sample
    assert "--no-columns" not in _strip_py_comments(sample)
    assert "return 1" in _strip_py_comments(sample)


# ---------------------------------------------------------------------------
# Property 9 / 21 / 23：迁移与回滚往返
# ---------------------------------------------------------------------------


class TestMigrateRollbackRoundTrip:
    @pytest.fixture()
    def legacy(self) -> dict[str, Any]:
        return {
            "rows": [_row("top")],
            "_tables": [
                {
                    "name": "交易性金融资产",
                    "headers": ["项目", "期末余额"],
                    "rows": [_row("a"), _row("hdr", "header_label"), _row("b")],
                },
                {"name": "应收款项融资", "headers": ["项目"], "rows": [_row("c")]},
            ],
            "_note_texts": [{"section": "x", "title": "说明", "text": "保留我"}],
        }

    def test_row_count_conserved(self, legacy) -> None:
        tpl = [_tpl_table("交易性金融资产"), _tpl_table("应收款项融资")]
        p = _plan(legacy, tpl)
        migrated = MIG.build_migrated_table_data(legacy, p, tpl)
        before = sum(len(t["rows"]) for t in legacy["_tables"])
        dropped = sum(t.dropped_header_label_rows for t in p.tables)
        after = sum(len(v) for v in migrated["sub_table_data"].values())
        assert after == before - dropped == 3

    def test_other_top_level_keys_preserved(self, legacy) -> None:
        tpl = [_tpl_table("交易性金融资产"), _tpl_table("应收款项融资")]
        migrated = MIG.build_migrated_table_data(legacy, _plan(legacy, tpl), tpl)
        assert migrated["_note_texts"] == legacy["_note_texts"]
        assert migrated["_source"] == MIG.MIGRATED_SOURCE
        assert "rows" not in migrated and "_tables" not in migrated
        assert set(migrated["_sub_table_columns"]) == {
            "交易性金融资产",
            "应收款项融资",
        }

    def test_rollback_restores_byte_identical(self, legacy) -> None:
        tpl = [_tpl_table("交易性金融资产"), _tpl_table("应收款项融资")]
        original = copy.deepcopy(legacy)
        migrated = MIG.build_migrated_table_data(legacy, _plan(legacy, tpl), tpl)
        restored = MIG.build_rollback_table_data(migrated)
        assert restored == original, "回滚未逐字节还原"
        assert legacy == original, "build_migrated_table_data 改了入参"

    def test_rollback_returns_none_without_backup(self) -> None:
        assert MIG.build_rollback_table_data({"sub_table_data": {}}) is None
        assert MIG.build_rollback_table_data(None) is None
        assert MIG.build_rollback_table_data("not-a-dict") is None

    def test_migration_is_idempotent_on_backup(self, legacy) -> None:
        """二次迁移不得覆盖最早那份备份。"""
        tpl = [_tpl_table("交易性金融资产"), _tpl_table("应收款项融资")]
        first = MIG.build_migrated_table_data(legacy, _plan(legacy, tpl), tpl)
        backup1 = copy.deepcopy(first[MIG.LINEAGE_KEY][MIG.BACKUP_KEY])
        second = MIG.build_migrated_table_data(first, _plan(first, tpl), tpl)
        assert second[MIG.LINEAGE_KEY][MIG.BACKUP_KEY] == backup1

    def test_already_migrated_detection(self, legacy) -> None:
        tpl = [_tpl_table("交易性金融资产"), _tpl_table("应收款项融资")]
        migrated = MIG.build_migrated_table_data(legacy, _plan(legacy, tpl), tpl)
        assert MIG._already_migrated(migrated) is True
        assert MIG._already_migrated(legacy) is False


# ---------------------------------------------------------------------------
# 探针纯函数：纯表名漂移判定（Wave 2 / Wave 4 的判据来源）
# ---------------------------------------------------------------------------


def _probe_tpl_section(names: list[str], *, columns: bool = True) -> dict[str, Any]:
    tables = [
        PROBE.scan_table(_tpl_table(n, columns=columns), index=i)
        for i, n in enumerate(names)
    ]
    return {"scope": PROBE.SCOPE_UNREGISTERED, "tables": tables}


class TestClassifyLegacyNote:
    def test_pure_name_drift(self) -> None:
        td = {
            "_tables": [
                {"name": "项  目", "headers": ["项  目"], "rows": [_row("a")]},
                {"name": "种  类", "headers": ["种  类"], "rows": [_row("b")]},
            ]
        }
        got = PROBE.classify_legacy_note(
            note_section="五、9",
            table_data=td,
            tpl_section=_probe_tpl_section(["交易性金融资产", "应收票据分类"]),
        )
        assert got["verdict"] == "pure_name_drift"
        assert got["not_in_tpl"] == 2 and got["migratable"] == 0

    def test_one_name_matches_is_not_pure_drift(self) -> None:
        """反向自检：只要有一个名字能命中模板就不判纯漂移（否则会误对齐）。"""
        td = {
            "_tables": [
                {"name": "交易性金融资产", "headers": ["项目"], "rows": [_row("a")]},
                {"name": "种  类", "headers": ["种  类"], "rows": [_row("b")]},
            ]
        }
        got = PROBE.classify_legacy_note(
            note_section="五、9",
            table_data=td,
            tpl_section=_probe_tpl_section(["交易性金融资产", "应收票据分类"]),
        )
        assert got["verdict"] != "pure_name_drift"
        assert got["verdict"] == "positional"

    def test_count_mismatch_is_not_pure_drift(self) -> None:
        td = {"_tables": [{"name": "项  目", "headers": ["项  目"], "rows": [_row("a")]}]}
        got = PROBE.classify_legacy_note(
            note_section="五、9",
            table_data=td,
            tpl_section=_probe_tpl_section(["A", "B"]),
        )
        assert got["verdict"] == "count_mismatch"

    def test_template_leak_name_blocks_pure_drift(self) -> None:
        """模板侧自己也是泄漏名时不得判纯漂移（对齐目标本身不可信）。

        构造要点：快照名与模板名**必须不同**（否则会先命中 ``matched`` 而走不到
        ``tpl_all_meaningful`` 这条判据，变异检验会因此静默通过 —— 首版 fixture
        正是这样漏掉了 M8）。
        """
        td = {"_tables": [{"name": "种  类", "headers": ["种  类"], "rows": [_row("a")]}]}
        tpl = {
            "scope": PROBE.SCOPE_UNREGISTERED,
            "tables": [
                PROBE.scan_table(
                    {"name": "项  目", "headers": ["项  目"], "columns": []}, index=0
                )
            ],
        }
        got = PROBE.classify_legacy_note(
            note_section="五、9", table_data=td, tpl_section=tpl
        )
        assert got["verdict"] != "pure_name_drift", (
            "模板名本身是表头泄漏名时不得按位置对齐"
        )

    def test_tpl_no_columns_counted_separately_from_not_in_tpl(self) -> None:
        td = {"_tables": [{"name": "A", "headers": ["项目"], "rows": [_row("a")]}]}
        got = PROBE.classify_legacy_note(
            note_section="五、9",
            table_data=td,
            tpl_section=_probe_tpl_section(["A"], columns=False),
        )
        assert got["tpl_no_columns"] == 1
        assert got["not_in_tpl"] == 0
        assert got["migratable"] == 0

    def test_section_not_in_template(self) -> None:
        td = {"_tables": [{"name": "A", "rows": [_row("a")]}]}
        got = PROBE.classify_legacy_note(
            note_section="X", table_data=td, tpl_section=None
        )
        assert got["verdict"] == "section_not_in_template"
