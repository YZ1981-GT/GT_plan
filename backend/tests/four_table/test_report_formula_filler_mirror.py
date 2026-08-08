"""第二写入路径镜像守卫：`report_formula_service` ↔ V138 / 判据真源。

背景（spec `report-config-account-code-integrity` Task 7 实测）
--------------------------------------------------------------
`report_config.formula` 有**两条写入路径**：

1. `backend/migrations/V*.sql` 这类迁移（V137 / V138）；
2. :meth:`app.services.report_formula_service.ReportFormulaService.fill_all_formulas`
   —— 挂在 ``POST /api/report-config/seed`` 与 template_library 重建端点上。

第 2 条按**行名**索引四张表（``_BS_SPECIAL`` / ``_EQ_SPECIAL`` /
``_IMP_SPECIAL`` / ``_NAME_TO_ACCOUNT``），且 ``if cfg.formula: skip`` **只填 NULL 行**
—— 恰好正是 V138 置 NULL 的那一批。两条路径不同步时的后果不是"公式不一致"，
而是**V138 的成果被静默抹掉**：置 NULL 的 6 行会被原封填回刚删掉的错码。

本守卫锁死三件事：

* 镜像改码已落地（``FORMULA_FILLER_MIRRORED_CORRECTIONS``）；
* 派生行既被前置拦截、又从名索引表里删除（双保险）；
* 有意豁免按名拦截的行（``CFSS-016``）其 filler 侧公式形态保持正确。

不连库，纯源码 + 常量比对，可进 CI。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.services.four_table.report_config_account_names import (
    DERIVED_ROW_NAMES_WITHOUT_ACCOUNT,
    DERIVED_ROWS_EXEMPT_FROM_NAME_BLOCK,
    DERIVED_ROWS_WITHOUT_ACCOUNT,
    FORMULA_FILLER_MIRRORED_CORRECTIONS,
    FORMULA_FILLER_SUSPECTED_ISSUES,
    IMPAIRMENT_LOSS_CODE_BY_NAME,
    normalize_name,
)


# ---------------------------------------------------------------------------
# 定位与读取
# ---------------------------------------------------------------------------

#: 🔴 双哨兵向上查找仓库根：单哨兵不够稳（将来子目录出现同名文件即误停），
#: 目录做哨兵会被 `audit-platform/backend/app/routers` 这类历史空目录骗停。
_SENTINELS = (
    Path("backend/app/services/report_formula_service.py"),
    Path("backend/app/services/four_table/report_config_account_names.py"),
)


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    for candidate in here.parents:
        if all((candidate / s).is_file() for s in _SENTINELS):
            return candidate
    raise AssertionError(
        "找不到仓库根（双哨兵均未命中）；请检查 test 文件位置或哨兵路径是否已变更"
    )


REPO_ROOT = _repo_root()
FILLER_PATH = REPO_ROOT / "backend/app/services/report_formula_service.py"

#: 🔴 五张「特殊公式」名索引表 —— 漏一张就让针对它的断言以 `KeyError` 形式假失败
#: （首版漏 `_IS_SPECIAL`，6701/6702 互换守卫因此 4 条全炸）。
_TABLE_NAMES = (
    "_BS_SPECIAL",
    "_IS_SPECIAL",
    "_EQ_SPECIAL",
    "_IMP_SPECIAL",
    "_CFS_INDIRECT_SPECIAL",
)
_FALLBACK_TABLE_NAMES = ("_NAME_TO_ACCOUNT", "_NAME_TO_IS_ACCOUNT")


def _strip_line_comments(src: str) -> str:
    """去掉 ``#`` 行注释，保留字符串字面量所在行。

    🔴 必须剥注释：本 spec 的注释里**逐字写着被修正掉的错码**
    （「原写 4003 实为其他综合收益」），不剥会把说明文字数成真实引用。
    """
    out: list[str] = []
    for line in src.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        # 行内注释：只在 # 前不存在未闭合引号时截断（本文件无跨行字符串）
        idx = line.find("#")
        if idx >= 0 and line.count('"', 0, idx) % 2 == 0 and line.count("'", 0, idx) % 2 == 0:
            line = line[:idx]
        out.append(line)
    return "\n".join(out)


def _extract_dict_body(src: str, name: str) -> str:
    """截出 ``name: dict[...] = { ... }`` 的字典体（按花括号配对，不用固定窗口）。

    🔴 不用「声明后 N 个字符」这类固定窗口 —— 会溢出到下一个声明
    （memory 已登记的守卫自身缺陷范式）。
    """
    m = re.search(rf"^{re.escape(name)}\s*:\s*dict\[[^\]]*\]\s*=\s*\{{", src, re.M)
    assert m, f"{name} 声明未找到（filler 结构已变？）"
    start = m.end() - 1
    depth = 0
    for i in range(start, len(src)):
        if src[i] == "{":
            depth += 1
        elif src[i] == "}":
            depth -= 1
            if depth == 0:
                return src[start : i + 1]
    raise AssertionError(f"{name} 花括号未配对")


def _entries(body: str) -> dict[str, str]:
    """从字典体抽 ``"键": "值"`` 对（值为单行字符串字面量）。"""
    return {
        m.group(1): m.group(2)
        for m in re.finditer(r'"([^"]+)"\s*:\s*"((?:[^"\\]|\\.)*)"', body)
    }


FILLER_SRC_RAW = FILLER_PATH.read_text(encoding="utf-8")
FILLER_SRC = _strip_line_comments(FILLER_SRC_RAW)

NAME_TABLES: dict[str, dict[str, str]] = {
    name: _entries(_extract_dict_body(FILLER_SRC, name))
    for name in _TABLE_NAMES + _FALLBACK_TABLE_NAMES
}


# ---------------------------------------------------------------------------
# 自检：解析器没有空转
# ---------------------------------------------------------------------------


class TestExtractionActuallyWorks:
    """🔴 反向自检 —— 解析失效会让下面全部断言变成空转（恒绿）。"""

    def test_comment_stripper_removed_something_real(self) -> None:
        # 剥注释前源码里确实含被修正的错码（写在说明注释里）
        assert "4003" in FILLER_SRC_RAW, "注释里应留有被修正错码的说明，判据前提不成立"
        assert "4003" not in FILLER_SRC, "剥注释后 4003 仍在 → 存在真实残留或剥离失效"

    @pytest.mark.parametrize("table", _TABLE_NAMES + _FALLBACK_TABLE_NAMES)
    def test_each_table_non_trivial(self, table: str) -> None:
        assert len(NAME_TABLES[table]) >= 5, (
            f"{table} 只解析出 {len(NAME_TABLES[table])} 条 —— 解析器大概率失效"
        )

    def test_known_anchor_entries_present(self) -> None:
        assert NAME_TABLES["_BS_SPECIAL"].get("货币资金"), "锚点条目缺失，解析结果不可信"
        assert NAME_TABLES["_NAME_TO_ACCOUNT"].get("短期借款") == "2001"


# ---------------------------------------------------------------------------
# Property: 镜像改码已落地
# ---------------------------------------------------------------------------


class TestMirroredCorrectionsApplied:
    """每条 ``(行名, 错码, 正码)`` 在 filler 的名索引表里必须已用正码。"""

    @pytest.mark.parametrize("row_name", sorted(FORMULA_FILLER_MIRRORED_CORRECTIONS))
    def test_wrong_code_gone_right_code_present(self, row_name: str) -> None:
        wrong, right, reason = FORMULA_FILLER_MIRRORED_CORRECTIONS[row_name]
        found_in: list[str] = []
        for table, entries in NAME_TABLES.items():
            value = entries.get(row_name)
            if value is None:
                continue
            found_in.append(table)
            assert wrong not in value, (
                f"{table}[{row_name!r}] 仍在用错码 {wrong}：{value!r}\n"
                f"依据：{reason}"
            )
            assert right in value, (
                f"{table}[{row_name!r}] 未用正码 {right}：{value!r}\n依据：{reason}"
            )
        assert found_in, (
            f"{row_name!r} 在 filler 的任何名索引表里都找不到 —— "
            f"要么条目已被删除（此时应从 FORMULA_FILLER_MIRRORED_CORRECTIONS 移出并"
            f"改登记到 DERIVED_ROW_NAMES_WITHOUT_ACCOUNT），要么行名已漂移"
        )

    @pytest.mark.parametrize("row_name", sorted(FORMULA_FILLER_MIRRORED_CORRECTIONS))
    def test_wrong_code_absent_from_whole_file(self, row_name: str) -> None:
        """错码不得在**任何**公式里残留（含合计公式的加减项）。

        🔴 只查以该行名为键的条目不够 —— 权益合计公式里同样把库存股写成 4003、
        专项储备写成 4103，那是同一笔错误的另一处出现。同一科目在同一文件里
        有两个码就是双真源，守卫锁不住。
        """
        wrong, right, reason = FORMULA_FILLER_MIRRORED_CORRECTIONS[row_name]
        if wrong in _CODES_LEGITIMATELY_REUSED:
            pytest.skip(
                f"{wrong} 在本文件另有合法用途：{_CODES_LEGITIMATELY_REUSED[wrong]}"
            )
        hits = [
            (FILLER_SRC[: m.start()].count("\n") + 1, m.group(0))
            for m in re.finditer(rf"'{wrong}'", FILLER_SRC)
        ]
        assert not hits, (
            f"错码 {wrong}（{row_name}）仍在 filler 中残留于行 "
            f"{[ln for ln, _ in hits]}\n依据：{reason}"
        )


#: 被修正的错码里，**在本文件另有合法归属**的（不能全局禁用）。
#: 每条须写明合法用途 + 实证，否则上面那条全局断言会误杀。
_CODES_LEGITIMATELY_REUSED: dict[str, str] = {
    "1703": (
        "1703 的真实科目名就是「无形资产减值准备」，filler 的 "
        "_IMP_SPECIAL['无形资产减值准备'] / ['无形资产减值准备年初'] / 合计公式"
        "正确使用它。本 spec 修的是「开发支出」误用 1703，不是禁用该码。"
        "2026-08-05 实证"
    ),
}


# ---------------------------------------------------------------------------
# Property: 派生行拦截
# ---------------------------------------------------------------------------


class TestDerivedRowsBlocked:
    """V138 置 NULL 的行不得被第二写入路径按名回填。"""

    def test_gate_exists_in_fill_all_formulas(self) -> None:
        body = _function_body(FILLER_SRC, "fill_all_formulas")
        assert "DERIVED_ROW_NAMES_WITHOUT_ACCOUNT" in body, (
            "fill_all_formulas 里没有派生行拦截门 —— V138 置 NULL 的行会被按名填回错码"
        )

    def test_gate_runs_before_any_strategy(self) -> None:
        """拦截必须在策略 1（``_get_special``）之前，否则拦不住。"""
        body = _function_body(FILLER_SRC, "fill_all_formulas")
        gate = body.find("DERIVED_ROW_NAMES_WITHOUT_ACCOUNT")
        special = body.find("_get_special(")
        assert gate >= 0 and special >= 0, "拦截门或策略 1 调用点定位失败"
        assert gate < special, (
            "派生行拦截出现在 _get_special 之后 —— 特殊公式表会先命中，拦截形同虚设"
        )

    def test_gate_short_circuits(self) -> None:
        """命中拦截必须 ``continue``，只记数不跳过等于没拦。"""
        body = _function_body(FILLER_SRC, "fill_all_formulas")
        gate = body.find("DERIVED_ROW_NAMES_WITHOUT_ACCOUNT")
        tail = body[gate : gate + 400]
        assert "continue" in tail, "拦截门命中后未 continue，公式仍会被填充"

    @pytest.mark.parametrize("row_name", sorted(DERIVED_ROW_NAMES_WITHOUT_ACCOUNT))
    def test_not_a_key_in_any_name_table(self, row_name: str) -> None:
        """双保险：派生行名也不得作为键留在名索引表里。

        拦截门在，留着条目也用不到；但留着就是"拦截门一旦被删就静默回归错码"的
        隐患，而那种回归没有任何报错。
        """
        offenders = {
            table: entries[row_name]
            for table, entries in NAME_TABLES.items()
            if row_name in entries
        }
        assert not offenders, (
            f"派生行 {row_name!r} 仍作为键存在于 {list(offenders)}：{offenders}\n"
            f"它应保持 NULL（V138 已置 NULL），名索引表里不该有它"
        )

    @pytest.mark.parametrize("row_name", sorted(DERIVED_ROW_NAMES_WITHOUT_ACCOUNT))
    def test_normalization_agrees_on_both_sides(self, row_name: str) -> None:
        """两个归一函数对这批名字必须给出同一结果，否则拦截判定会漏。

        filler 有自己的 ``_normalize_name``，真源有 ``normalize_name``，
        剥离规则不完全相同（真源还剥尾部括注、循环剥前缀）。
        """
        filler_norm = _filler_normalize(row_name)
        assert filler_norm == row_name, (
            f"filler 的 _normalize_name({row_name!r}) = {filler_norm!r} —— "
            f"集合里应存归一后的形态"
        )
        assert normalize_name(row_name) == row_name, (
            f"真源 normalize_name({row_name!r}) = {normalize_name(row_name)!r}"
        )


# ---------------------------------------------------------------------------
# Property: 豁免行的公式形态锁死
# ---------------------------------------------------------------------------


class TestNameBlockExemptions:
    """有意不按名拦截的行，其 filler 侧公式必须仍然是"更好的那个"。"""

    def test_exemptions_are_subset_of_v138_null_rows(self) -> None:
        unknown = set(DERIVED_ROWS_EXEMPT_FROM_NAME_BLOCK) - set(
            DERIVED_ROWS_WITHOUT_ACCOUNT
        )
        assert not unknown, (
            f"豁免表登记了不属于 V138 置 NULL 清单的行：{sorted(unknown)}"
        )

    def test_exemptions_carry_evidence(self) -> None:
        for row_code, reason in DERIVED_ROWS_EXEMPT_FROM_NAME_BLOCK.items():
            assert len(reason) >= 30, f"{row_code} 豁免理由过短：{reason!r}"
            assert "2026-" in reason, f"{row_code} 豁免理由缺实证日期：{reason!r}"

    def test_inventory_decrease_formula_still_range_and_delta(self) -> None:
        """``CFSS-016 存货的减少``：豁免的前提是公式为区间 + 变动额。

        一旦有人把它改回单码 ``TB('1401')``（材料采购），豁免的依据就消失，
        该行必须重新纳入按名拦截 —— 本断言就是那个提醒。
        """
        assert "CFSS-016" in DERIVED_ROWS_EXEMPT_FROM_NAME_BLOCK, (
            "CFSS-016 已不在豁免表 —— 若已改为按名拦截，请同步删除本断言"
        )
        value = NAME_TABLES["_CFS_INDIRECT_SPECIAL"].get("存货的减少")
        assert value, "_CFS_INDIRECT_SPECIAL 里找不到「存货的减少」"
        assert value.count("SUM_TB(") == 2, (
            f"「存货的减少」不再是区间口径：{value!r} —— 豁免前提失效，"
            f"应把它重新加入 DERIVED_ROW_NAMES_WITHOUT_ACCOUNT"
        )
        assert "年初余额" in value and "期末余额" in value, (
            f"「存货的减少」不再是变动额口径：{value!r}"
        )
        assert not re.search(r"TB\('14\d\d'", value), (
            f"「存货的减少」回退成单码取数：{value!r}"
        )


# ---------------------------------------------------------------------------
# Property: 登记表纪律
# ---------------------------------------------------------------------------


class TestImpairmentLossCodesNotSwapped:
    """🔴 6701 / 6702 不得互换 —— 本轮影响面最大的一处（约 1.5 亿）。

    `account_chart` 实证零分歧：6701 = 资产减值损失、6702 = 信用减值损失；
    `report_config` 侧已由 V137 按同一结论修对。而第二写入路径（本文件被测对象）
    曾把两者整整互换 6 处，属"同一笔错误只修了迁移侧"的同型缺陷。
    """

    _TABLES = ("_IS_SPECIAL", "_CFS_INDIRECT_SPECIAL", "_IMP_SPECIAL")

    def test_registry_is_self_consistent(self) -> None:
        """反向自检：真源本身必须把两码分开（防被改成同一个码后断言空转）。"""
        assert IMPAIRMENT_LOSS_CODE_BY_NAME["资产减值损失"] == "6701"
        assert IMPAIRMENT_LOSS_CODE_BY_NAME["信用减值损失"] == "6702"
        assert len(set(IMPAIRMENT_LOSS_CODE_BY_NAME.values())) == 2, (
            "真源里两码已塌成一个，本类断言会失去意义"
        )

    @pytest.mark.parametrize("row_name", sorted(IMPAIRMENT_LOSS_CODE_BY_NAME))
    def test_filler_uses_registry_code(self, row_name: str) -> None:
        expected = IMPAIRMENT_LOSS_CODE_BY_NAME[row_name]
        wrong = "6701" if expected == "6702" else "6702"
        seen = 0
        for table in self._TABLES:
            value = NAME_TABLES[table].get(row_name)
            if value is None:
                continue
            seen += 1
            assert expected in value, (
                f"{table}[{row_name!r}] = {value!r} 未使用真源码 {expected}"
            )
            assert wrong not in value, (
                f"{table}[{row_name!r}] = {value!r} 仍含互换后的错码 {wrong}\n"
                f"判据：account_chart 实证 6701=资产减值损失 / 6702=信用减值损失，"
                f"report_config 侧 V137 已按此修对"
            )
        assert seen, (
            f"{row_name!r} 在三张表里都找不到 —— 条目被删则应从 "
            f"IMPAIRMENT_LOSS_CODE_BY_NAME 移出，否则本断言空转"
        )

    def test_combined_row_still_sums_both(self) -> None:
        """「资产减值准备」= 两者之和，不该被"顺手"改成单码。"""
        value = NAME_TABLES["_CFS_INDIRECT_SPECIAL"].get("资产减值准备")
        assert value, "_CFS_INDIRECT_SPECIAL 里找不到「资产减值准备」"
        assert "6701" in value and "6702" in value, (
            f"「资产减值准备」应为两码之和，现为 {value!r}"
        )


class TestNoDuplicateNameTableCopies:
    """🔴 名索引表必须**单一真源** —— 全仓不得存在第二份副本。

    2026-08-05 复盘实测：`backend/scripts/fix/fill_report_formulas.py` 是
    `report_formula_service` 的**脚本前身**，归档 spec 的 design 写明「保留作 CLI 入口，
    内部调 service」，但那次重构只做了前半截 —— service 建好了，脚本仍是 357 行独立副本，
    带着 service 已修掉的错码（专项储备 4103 / 开发支出 1703）且**完全没有派生行拦截门**。
    它因此长期是 `report_config.formula` 的**第三条写入路径**，跑一次就把 V138 白做。

    上面那批断言只读 service 一个文件，抓不到这种"另一份实现"。本类补的就是那个缺口：
    凡在 `backend/` 里出现 `{BS,IS,EQ,IMP,CFS_INDIRECT}_SPECIAL` 或 `NAME_TO_ACCOUNT`
    形态的字典声明，文件必须在允许名单内。
    """

    #: 允许持有名索引表的文件（相对仓库根）。加条目必须写明为什么它不是副本。
    _ALLOWED = {
        "backend/app/services/report_formula_service.py": "唯一真源",
    }

    #: 表名形态：可选前导下划线 + 表名 + `: dict[...] = {`
    _TABLE_RE = re.compile(
        r"^_?(BS|IS|EQ|IMP|CFS_INDIRECT)_SPECIAL\s*:\s*dict\[|"
        r"^_?NAME_TO_(?:IS_)?ACCOUNT\s*:\s*dict\[|"
        r"^_?(BS|IS|EQ|IMP|CFS_INDIRECT)_SPECIAL\s*=\s*\{|"
        r"^_?NAME_TO_(?:IS_)?ACCOUNT\s*=\s*\{",
        re.M,
    )

    _SKIP_PARTS = {"__pycache__", ".venv", "node_modules"}

    def _scan(self) -> dict[str, list[str]]:
        found: dict[str, list[str]] = {}
        for p in (REPO_ROOT / "backend").rglob("*.py"):
            if self._SKIP_PARTS & set(p.parts):
                continue
            try:
                src = p.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            names = [m.group(0).split(":")[0].split("=")[0].strip() for m in self._TABLE_RE.finditer(src)]
            if names:
                found[str(p.relative_to(REPO_ROOT)).replace("\\", "/")] = names
        return found

    def test_scanner_finds_the_single_source(self) -> None:
        """反向自检：扫描器必须能看见唯一真源，否则下面的断言是空转。"""
        found = self._scan()
        assert "backend/app/services/report_formula_service.py" in found, (
            f"扫描器没看见唯一真源 —— 表名形态可能已变。当前命中：{sorted(found)}"
        )
        assert len(found["backend/app/services/report_formula_service.py"]) >= 5, (
            "唯一真源里只扫到少数表，正则大概率失效"
        )

    def test_no_unauthorised_copies(self) -> None:
        found = self._scan()
        offenders = {f: names for f, names in found.items() if f not in self._ALLOWED}
        assert not offenders, (
            "发现名索引表副本（会成为 `report_config.formula` 的又一条写入路径）：\n"
            + "\n".join(f"  - {f}: {names}" for f, names in sorted(offenders.items()))
            + "\n\n应改为委托 `report_formula_service`，而不是维护第二份表。"
        )

    def test_cli_shell_delegates_to_service(self) -> None:
        """CLI 脚本必须委托 service，且不得自带策略实现。"""
        p = REPO_ROOT / "backend/scripts/fix/fill_report_formulas.py"
        if not p.exists():
            pytest.skip("fill_report_formulas.py 已删除（也是合法处置）")
        src = _strip_line_comments(p.read_text(encoding="utf-8"))
        assert "report_formula_service" in src, (
            "CLI 脚本未委托 service —— 它会再次变成独立的第三条写入路径"
        )
        for banned in ("_get_special", "def get_special", "def convert_formula", "def generate_sum_formula"):
            assert banned not in src, (
                f"CLI 脚本自带策略实现 `{banned}` —— 判据必须单一真源"
            )


class TestRegistryDiscipline:
    def test_mirrored_and_derived_do_not_overlap(self) -> None:
        """一个行名不能既"改码"又"置 NULL" —— 判据自相矛盾。"""
        overlap = set(FORMULA_FILLER_MIRRORED_CORRECTIONS) & set(
            DERIVED_ROW_NAMES_WITHOUT_ACCOUNT
        )
        assert not overlap, f"行名同时登记在改码表与派生行表：{sorted(overlap)}"

    def test_mirrored_and_suspected_do_not_overlap(self) -> None:
        overlap = set(FORMULA_FILLER_MIRRORED_CORRECTIONS) & set(
            FORMULA_FILLER_SUSPECTED_ISSUES
        )
        assert not overlap, (
            f"行名同时登记在已修表与待裁决表：{sorted(overlap)} —— "
            f"修了就该从待裁决移出"
        )

    @pytest.mark.parametrize("row_name", sorted(FORMULA_FILLER_MIRRORED_CORRECTIONS))
    def test_mirrored_entry_shape(self, row_name: str) -> None:
        wrong, right, reason = FORMULA_FILLER_MIRRORED_CORRECTIONS[row_name]
        assert re.fullmatch(r"\d{4}", wrong), f"{row_name} 错码格式非四位：{wrong!r}"
        assert re.fullmatch(r"\d{4}", right), f"{row_name} 正码格式非四位：{right!r}"
        assert wrong != right, f"{row_name} 错码与正码相同"
        assert len(reason) >= 30, f"{row_name} 理由过短（须带实证项目数）：{reason!r}"

    @pytest.mark.parametrize("row_name", sorted(FORMULA_FILLER_SUSPECTED_ISSUES))
    def test_suspected_entry_carries_evidence(self, row_name: str) -> None:
        reason = FORMULA_FILLER_SUSPECTED_ISSUES[row_name]
        assert len(reason) >= 30, f"{row_name} 待裁决理由过短：{reason!r}"
        assert "2026-" in reason, f"{row_name} 待裁决理由缺实证日期：{reason!r}"


# ---------------------------------------------------------------------------
# 反向自检：把改动"撤回"后守卫必须打红
# ---------------------------------------------------------------------------


class TestReverseSelfcheck:
    """🔴 在替身文本上复现修复前的形态，确认守卫会红。

    只看"全绿"证明不了守卫有效 —— 每条判据都要真做一次变异。
    """

    def test_wrong_code_in_entry_would_be_caught(self) -> None:
        mutated = '_BS_SPECIAL: dict[str, str] = {\n    "库存股": "TB(\'4003\',\'期末余额\')",\n}\n'
        entries = _entries(_extract_dict_body(mutated, "_BS_SPECIAL"))
        wrong, right, _ = FORMULA_FILLER_MIRRORED_CORRECTIONS["库存股"]
        assert wrong in entries["库存股"] and right not in entries["库存股"], (
            "变异样本未复现旧行为 —— 反向自检本身失效"
        )

    def test_derived_row_key_would_be_caught(self) -> None:
        mutated = (
            '_NAME_TO_ACCOUNT: dict[str, str] = {\n'
            '    "少数股东权益": "4201",\n'
            '}\n'
        )
        entries = _entries(_extract_dict_body(mutated, "_NAME_TO_ACCOUNT"))
        assert "少数股东权益" in entries, "变异样本未复现旧行为"
        assert "少数股东权益" in DERIVED_ROW_NAMES_WITHOUT_ACCOUNT, (
            "少数股东权益不在派生行集合里 —— 该断言已失去意义"
        )

    def test_missing_gate_would_be_caught(self) -> None:
        mutated = (
            "    def fill_all_formulas(self):\n"
            "        norm = _normalize_name(row_name)\n"
            "        formula = _get_special(row_name, report_type)\n"
            "        return formula\n"
        )
        body = _function_body(mutated, "fill_all_formulas")
        assert "DERIVED_ROW_NAMES_WITHOUT_ACCOUNT" not in body, (
            "变异样本未复现「缺拦截门」的形态"
        )

    def test_gate_after_strategy_would_be_caught(self) -> None:
        mutated = (
            "    def fill_all_formulas(self):\n"
            "        formula = _get_special(row_name, report_type)\n"
            "        if norm in DERIVED_ROW_NAMES_WITHOUT_ACCOUNT:\n"
            "            continue\n"
            "        return formula\n"
        )
        body = _function_body(mutated, "fill_all_formulas")
        assert body.find("DERIVED_ROW_NAMES_WITHOUT_ACCOUNT") > body.find(
            "_get_special("
        ), "变异样本未复现「拦截在策略之后」的形态"

    def test_single_code_inventory_formula_would_be_caught(self) -> None:
        mutated = (
            "_CFS_INDIRECT_SPECIAL: dict[str, str] = {\n"
            "    \"存货的减少\": \"TB('1401','年初余额')-TB('1401','期末余额')\",\n"
            "}\n"
        )
        value = _entries(_extract_dict_body(mutated, "_CFS_INDIRECT_SPECIAL"))["存货的减少"]
        assert value.count("SUM_TB(") != 2, "变异样本未复现单码形态"
        assert re.search(r"TB\('14\d\d'", value), "变异样本未复现单码形态"


# ---------------------------------------------------------------------------
# 局部工具
# ---------------------------------------------------------------------------


def _function_body(src: str, func_name: str) -> str:
    """按缩进截出函数体（到下一个同级或更浅缩进的 ``def`` / ``class``）。

    🔴 不用"声明后固定字符窗口" —— 会溢出到下一个函数（memory 已登记的守卫缺陷）。
    """
    # 🔴 缩进类必须写 `[ \t]*` 不能写 `\s*` —— re.M 下 `\s` 含换行，会从前面的空行
    #    开始匹配，m.start() 落在空行上、indent 被算成一大串换行的长度，
    #    结果 lines[0] 是空行、函数体被截成空串（本守卫首版即因此 3 条断言空转打红）。
    m = re.search(rf"^([ \t]*)(?:async\s+)?def\s+{re.escape(func_name)}\b", src, re.M)
    assert m, f"函数 {func_name} 未找到"
    indent = len(m.group(1))
    lines = src[m.start():].splitlines()
    body = [lines[0]]
    for line in lines[1:]:
        if line.strip() and not line.startswith(" " * (indent + 1)):
            if re.match(rf"^\s{{0,{indent}}}(?:async\s+)?(?:def|class)\s", line):
                break
        body.append(line)
    return "\n".join(body)


_FILLER_NOISE_RE = re.compile(r"^(加：|减：|其中：|加:|减:|其中:)\s*")


def _filler_normalize(name: str) -> str:
    """复刻 filler 的 ``_normalize_name``（守卫不 import 私有函数，改为复刻 + 自检）。"""
    out = re.sub(r"[△▲]", "", name)
    out = re.sub(r"^[一二三四五六七八九十]+、\s*", "", out)
    out = _FILLER_NOISE_RE.sub("", out)
    return (
        out.replace("：", "").replace(":", "").replace(" ", "").replace("\u3000", "").strip()
    )


class TestFillerNormalizeReplicaMatchesSource:
    """🔴 复刻函数必须与 filler 源码同款，否则上面的归一断言测的是别的东西。"""

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("减：库存股", "库存股"),
            ("一、营业收入", "营业收入"),
            ("△利息收入", "利息收入"),
            ("少数股东权益", "少数股东权益"),
            ("其中：应收账款坏账准备", "应收账款坏账准备"),
        ],
    )
    def test_replica_behaviour(self, raw: str, expected: str) -> None:
        assert _filler_normalize(raw) == expected

    def test_replica_regexes_still_present_in_source(self) -> None:
        """filler 改了归一规则时提醒同步复刻。"""
        body = _function_body(FILLER_SRC, "_normalize_name")
        for token in ("[△▲]", "一二三四五六七八九十", "加：", "\\u3000"):
            assert token in body or token.replace("\\u3000", "\u3000") in body, (
                f"filler 的 _normalize_name 已不含 {token!r} —— 请同步更新本文件的复刻实现"
            )
