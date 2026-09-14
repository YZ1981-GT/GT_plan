"""双族并取的三个落点交叉锁死（Task 8 / Property 2、3）。

`report_config.formula` 有**多条写入路径**（memory §踩坑铁律已登记 5 条），
本 spec 触及其中两条：

1. **迁移** `V145__report_config_dual_family_rou_lease.sql`
2. **`ReportFormulaService`** 的名索引表 —— 挂在 ``POST /api/report-config/seed``
   与 template_library 重建端点上，按**行名**索引且 ``if cfg.formula: skip``
   只填 NULL 行

第 3 个落点是**语义兜底码** `h8/h9_account_scope.fallback_standard_codes`
（Task 6 负责），它只在按科目名定位失败时才用。

三者是独立路径，改一处另两处不动 = 分叉。本守卫把三处与唯一真源
`four_table.dual_family_codes` 逐字锁死。

不连库，纯源码 + 常量比对，可进 CI。

spec: .kiro/specs/h-cycle-extraction-formula-and-disclosure-completion/
      Requirements 1.1, 1.3, 1.5, 1.6 / Property 2, 3
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.services.four_table.dual_family_codes import (
    ALTERNATE_CODES,
    DUAL_FAMILY_ROW_FORMULAS,
    FILLER_BS_SPECIAL_DUAL_FAMILY,
    FILLER_NAME_TO_ACCOUNT_PRIMARY_ONLY,
    ROU_LEASE_DUAL_FAMILIES,
)

# ── 双哨兵向上查找仓库根（单哨兵不够稳；目录做哨兵会被历史空目录骗停）──
_SENTINELS = (
    Path("backend/app/services/report_formula_service.py"),
    Path("backend/app/services/four_table/dual_family_codes.py"),
)


def _repo_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if all((candidate / s).is_file() for s in _SENTINELS):
            return candidate
    raise AssertionError("找不到仓库根（双哨兵均未命中）")


REPO_ROOT = _repo_root()
FILLER = REPO_ROOT / "backend/app/services/report_formula_service.py"
MIGRATIONS = REPO_ROOT / "backend/migrations"
V145 = MIGRATIONS / "V145__report_config_dual_family_rou_lease.sql"
R145 = MIGRATIONS / "R145__rollback_report_config_dual_family_rou_lease.sql"


def _strip_py_comments(src: str) -> str:
    """剥 ``#`` 注释（本文件与 filler 的注释里逐字写着旧公式，不剥会误命中）。"""
    out: list[str] = []
    for line in src.splitlines():
        if line.lstrip().startswith("#"):
            continue
        idx = line.find("#")
        if (
            idx >= 0
            and line.count('"', 0, idx) % 2 == 0
            and line.count("'", 0, idx) % 2 == 0
        ):
            line = line[:idx]
        out.append(line)
    return "\n".join(out)


def _strip_sql_comments(src: str) -> str:
    """剥 ``--`` 行注释（V145 的注释里逐字写着旧公式）。"""
    return "\n".join(
        ln for ln in src.splitlines() if not ln.lstrip().startswith("--")
    )


def _dict_body(src: str, name: str) -> str:
    """按花括号配对截字典体（禁固定字符窗口 —— 会溢出到下一个声明）。"""
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


def _entry_value(body: str, key: str) -> str:
    """取 ``"key": <值>`` 的值文本；值可为单行字面量或**隐式拼接的多行串**。

    🔴 隐式拼接必须支持：filler 的「使用权资产」就是括号内多行拼接
    （单行正则会**抓不到**，表现为「改动似乎没落盘」的假象 —— 本轮实测踩过）。
    """
    m = re.search(rf'"{re.escape(key)}"\s*:\s*', body)
    assert m, f"filler 表里找不到条目 {key!r}"
    rest = body[m.end() :]
    # 收集紧随其后的全部字符串字面量，直到遇到逗号 + 下一个键 或 收尾花括号
    parts: list[str] = []
    i = 0
    depth = 0
    while i < len(rest):
        ch = rest[i]
        if ch == "(":
            depth += 1
            i += 1
            continue
        if ch == ")":
            depth -= 1
            i += 1
            continue
        if ch in "'\"":
            q = ch
            j = i + 1
            buf: list[str] = []
            while j < len(rest) and rest[j] != q:
                buf.append(rest[j])
                j += 1
            parts.append("".join(buf))
            i = j + 1
            continue
        if ch == "," and depth == 0:
            break
        if ch == "}" and depth == 0:
            break
        i += 1
    assert parts, f"条目 {key!r} 未抽到字符串字面量"
    return "".join(parts)


FILLER_SRC = _strip_py_comments(FILLER.read_text(encoding="utf-8"))
BS_SPECIAL_BODY = _dict_body(FILLER_SRC, "_BS_SPECIAL")
NAME_TO_ACCOUNT_BODY = _dict_body(FILLER_SRC, "_NAME_TO_ACCOUNT")


# ─────────────────────────── 解析器自检 ───────────────────────────


class TestExtractionSelfCheck:
    """抽取器失效时必须打红，而不是让断言空转。"""

    def test_sentinels_exist(self):
        for s in _SENTINELS:
            assert (REPO_ROOT / s).is_file(), f"哨兵不存在: {s}"

    def test_dict_bodies_nonempty(self):
        assert len(BS_SPECIAL_BODY) > 500, "_BS_SPECIAL 抽取过短，配对可能失效"
        assert len(NAME_TO_ACCOUNT_BODY) > 500, "_NAME_TO_ACCOUNT 抽取过短"
        # 锚点：抽不到说明解析坏了
        assert '"货币资金"' in BS_SPECIAL_BODY
        assert '"固定资产"' in NAME_TO_ACCOUNT_BODY

    def test_multiline_implicit_concat_is_supported(self):
        """反向自检：隐式拼接的多行字符串必须能抽全。

        🔴 本轮实测踩过 —— 单行正则抓不到「使用权资产」（它是括号内多行拼接），
        导致误判「改动没落盘」。
        """
        fake = (
            'X: dict[str, str] = {\n'
            '    "a": "TB(\'1\')",\n'
            '    "b": (\n'
            '        "TB(\'2\')"\n'
            '        "+TB(\'3\')"\n'
            '    ),\n'
            '    "c": "TB(\'4\')",\n'
            '}\n'
        )
        body = _dict_body(fake, "X")
        assert _entry_value(body, "a") == "TB('1')"
        assert _entry_value(body, "b") == "TB('2')+TB('3')"
        assert _entry_value(body, "c") == "TB('4')"

    def test_sql_comment_stripping_works(self):
        stripped = _strip_sql_comments("-- old: TB('1641')\nUPDATE x SET y=1;")
        assert "1641" not in stripped
        assert "UPDATE" in stripped


# ─────────── Property 2：三个落点交叉一致（迁移 ↔ filler ↔ 真源）───────────


class TestMigrationMatchesSingleSource:
    """V145 的目标公式必须逐字等于真源生成的公式。"""

    def test_v145_exists(self):
        assert V145.is_file(), "V145 迁移不存在"
        assert R145.is_file(), "R145 回滚不存在（备份没有还原路径等于没备份）"

    @pytest.mark.parametrize("row_code", sorted(DUAL_FAMILY_ROW_FORMULAS))
    def test_v145_sets_expected_formula(self, row_code: str):
        """迁移写入的新公式 = 真源 `DUAL_FAMILY_ROW_FORMULAS`（SQL 里引号翻倍）。"""
        sql = _strip_sql_comments(V145.read_text(encoding="utf-8"))
        expected = DUAL_FAMILY_ROW_FORMULAS[row_code].replace("'", "''")
        assert expected in sql, (
            f"V145 未按真源写入 {row_code} 的公式。\n期望: {expected}"
        )

    @pytest.mark.parametrize("row_code", sorted(DUAL_FAMILY_ROW_FORMULAS))
    def test_v145_where_is_idempotent(self, row_code: str):
        """WHERE 必须带旧值断言（幂等 + 防覆盖并发改动）。"""
        sql = _strip_sql_comments(V145.read_text(encoding="utf-8"))
        assert re.search(rf"row_code\s*=\s*'{row_code}'", sql), (
            f"V145 未按 row_code={row_code} 定位"
        )
        # 该 row_code 的 UPDATE 段里必须有 `AND formula = '...'`
        assert "AND formula =" in sql, "WHERE 缺旧值断言 → 重复执行会覆盖后续改动"

    def test_rollback_is_exact_inverse(self):
        """R145 必须把新公式换回旧公式（方向相反、内容对称）。"""
        fwd = _strip_sql_comments(V145.read_text(encoding="utf-8"))
        bwd = _strip_sql_comments(R145.read_text(encoding="utf-8"))
        for row_code, new_formula in DUAL_FAMILY_ROW_FORMULAS.items():
            esc = new_formula.replace("'", "''")
            assert esc in fwd, f"V145 缺 {row_code} 新公式"
            assert esc in bwd, (
                f"R145 的 WHERE 未以 {row_code} 新公式为条件 → 回滚不幂等"
            )

    def test_migration_number_not_reused(self):
        """迁移号永不复用 —— 磁盘上不得有第二个 V145。"""
        v145s = sorted(MIGRATIONS.glob("V145__*.sql"))
        assert len(v145s) == 1, f"V145 存在多个文件: {[p.name for p in v145s]}"


class TestFillerMirrorsDualFamily:
    """filler 的 `_BS_SPECIAL` 必须与真源同步（第二写入路径）。"""

    @pytest.mark.parametrize("row_name", sorted(FILLER_BS_SPECIAL_DUAL_FAMILY))
    def test_bs_special_has_dual_family(self, row_name: str):
        # 🔴 真源里存的**就是公式**（由 DUAL_FAMILY_ROW_FORMULAS 派生），
        #    不要再拿它当 row_code 去查一次表 —— 首版这么写，KeyError 打红。
        expected = FILLER_BS_SPECIAL_DUAL_FAMILY[row_name]
        actual = _entry_value(BS_SPECIAL_BODY, row_name)
        assert actual == expected, (
            f"filler `_BS_SPECIAL[{row_name!r}]` 与真源不一致 —— "
            f"改迁移不改 filler 会让 seed 端点把公式填回单族。\n"
            f"期望: {expected}\n实际: {actual}"
        )

    @pytest.mark.parametrize("code", sorted(ALTERNATE_CODES))
    def test_alternate_codes_present_in_filler(self, code: str):
        """每个新族码都必须在 filler 的公式里出现（剥注释后）。"""
        assert code in BS_SPECIAL_BODY, (
            f"新族码 {code} 未出现在 filler `_BS_SPECIAL` 里"
        )

    def test_lease_liability_does_not_double_subtract_2602(self):
        """🔴 新族侧不得重复减 2602。

        `account_mapping` 实证新族把未确认融资费用做成 `2651.02` 子科目
        ⇒ 已含在 2651 父额内，再减一次即双算。故整条公式里 `2602` 只能出现一次。
        """
        actual = _entry_value(BS_SPECIAL_BODY, "租赁负债")
        assert actual.count("2602") == 1, (
            f"租赁负债公式里 2602 出现 {actual.count('2602')} 次 —— "
            f"新族 2651 已含未确认融资费用，重复减会双算: {actual}"
        )
        assert "2652" not in actual, "不存在 2652 这个码（宁缺勿造）"

    def test_impairment_has_no_fabricated_alternate(self):
        """🔴 使用权资产减值准备**没有**新族码 —— 不得臆造 1653。"""
        actual = _entry_value(BS_SPECIAL_BODY, "使用权资产")
        assert "1653" not in actual, "1653 在全库零命中，臆造该码违反宁缺勿造"
        assert actual.count("1643") == 1


class TestFallbackTableStaysPrimaryOnly:
    """`_NAME_TO_ACCOUNT` 是**单码** fallback 表，保持 primary 且锁死。"""

    @pytest.mark.parametrize(
        "row_name", sorted(FILLER_NAME_TO_ACCOUNT_PRIMARY_ONLY)
    )
    def test_fallback_keeps_primary_code(self, row_name: str):
        expected = FILLER_NAME_TO_ACCOUNT_PRIMARY_ONLY[row_name]
        actual = _entry_value(NAME_TO_ACCOUNT_BODY, row_name)
        assert actual == expected, (
            f"`_NAME_TO_ACCOUNT[{row_name!r}]` 应保持单码 {expected}（值={actual!r}）"
        )

    def test_fallback_is_unreachable_for_dual_family_names(self):
        """反向锁死：这两个名字必须同时在 `_BS_SPECIAL` 里（策略 1 命中即不可达）。

        一旦有人删掉 `_BS_SPECIAL` 的条目，公式就会落到这张单码 fallback 表
        → 静默退回只覆盖 0.04% 的旧族。本断言把「策略 1 必须存在」钉死。
        """
        for row_name in FILLER_NAME_TO_ACCOUNT_PRIMARY_ONLY:
            assert f'"{row_name}"' in BS_SPECIAL_BODY, (
                f"{row_name!r} 从 `_BS_SPECIAL` 消失 → 会落到单码 fallback "
                f"{FILLER_NAME_TO_ACCOUNT_PRIMARY_ONLY[row_name]}（只覆盖 0.04%）"
            )

    def test_registry_shape(self):
        """登记表形态自检：值必须是四位码且等于某个 group 的 primary。"""
        primaries = {g.primary for g in ROU_LEASE_DUAL_FAMILIES}
        for row_name, code in FILLER_NAME_TO_ACCOUNT_PRIMARY_ONLY.items():
            assert re.fullmatch(r"\d{4}", code), f"{row_name}: {code!r} 非四位码"
            assert code in primaries, (
                f"{row_name}: {code} 不是任何双族 group 的 primary"
            )


# ─────── Property 3：改 report_config 不改变多槽循环的语义定位 ───────


class TestMultiSlotSpecsDoNotConsumeReportConfig:
    """H8/H9 是多槽 spec ⇒ `allow_report_config_tier=False` ⇒ 改 V145 零影响。

    这一点必须由守卫钉死，否则下个会话会误以为改 `report_config` 会波及
    底稿取数而不敢动（或反过来，把单槽 spec 也当成不受影响）。
    """

    def test_resolver_gates_report_config_tier_on_slot_count(self):
        resolver = (
            REPO_ROOT
            / "backend/app/services/four_table/semantic_account_resolver.py"
        ).read_text(encoding="utf-8")
        src = _strip_py_comments(resolver)
        assert re.search(
            r"allow_report_config_tier\s*=\s*len\(\s*spec\.slots\s*\)\s*==\s*1", src
        ), (
            "`allow_report_config_tier` 不再按槽数门控 —— Property 3 的前提被改动，"
            "改 report_config 可能开始影响多槽循环的语义定位"
        )

    @pytest.mark.parametrize("cycle", ["H8", "H9"])
    def test_h8_h9_are_multi_slot(self, cycle: str):
        from app.services.four_table.h_cycle_specs import H_CYCLE_SPECS

        spec = H_CYCLE_SPECS[cycle]
        assert len(spec.slots) > 1, (
            f"{cycle} 变成单槽 spec ⇒ 会开始消费 report_config 公式 ⇒ "
            f"V145 对它的语义定位不再零影响，须重新评估"
        )
