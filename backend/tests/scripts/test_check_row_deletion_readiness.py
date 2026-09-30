"""``check_row_deletion_readiness`` 的守卫。

为什么这些判据长这样
====================

「工具能跑且输出非空」是**最弱**的判据形态 —— 它在工具把所有表都误判成
「模板缺失」时同样全绿（那时 `tables_audited=0`、输出照样非空）。所以本文件的每条
判据都要么**锁住语料分母**，要么**能被一次真实变异打红**：

* 分母类：契约份数 / 受管行表数 **现算**并与 `contracts` 真源交叉，禁写死数字；
* 口径类：报告必须自带 `measured` 声明（下游引用时能判断与别处的数字是否同一件事）；
* 单调性：`--count` 变大 ⇒ 可删数**不增**（这条能咬住「count 没传进生产判定」这类接线错）；
* 反向：把模板根指到空目录 ⇒ 必须 **exit 2** 并说「不是都不可删」，而不是报 100% 可删。

逐条变异反证（2026-09-29 实测，四条全部打红）
=============================================

============================  =========================================
摘掉的修复                      实际打红的判据
============================  =========================================
`count` 不传进生产判定            ``TestCountIsNotDecorative``
受阻表混进已体检（分母虚高）        ``test_audited_plus_blocked_accounts_for_every_candidate``
                              ＋ ``test_empty_template_root_exits_two``
`measured.not_measured` 清空     ``TestMeasurementDeclaration``
语料坏了不 fail-closed           ``TestFailsClosedOnBrokenCorpus``
============================  =========================================

🔴 第二条的**预期标错过一次**：我原以为会由 ``TestPerRowAccounting`` 咬住，实测不是 ——
受阻表的 ``managed_rows`` 是 0，逐行账照样闭合。是「已体检数与明细条数对账」和
「空模板根必须 exit 2」这两条抓到的。**变异反证要看红在哪条路径上**，只看「红了」
会让人误以为某条判据在起作用。

Requirements: 复盘追加项（删行链路开表准入）
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

os.environ.setdefault("DB_DISABLE_SSL", "True")

from app.services.workpaper_sync import contracts as C  # noqa: E402
from scripts.check import check_row_deletion_readiness as T  # noqa: E402


@pytest.fixture(scope="module")
def report() -> dict:
    return T.run_audit()


class TestDenominatorsAreLive:
    """分母现算，与 `contracts` 真源交叉（禁写死）。"""

    def test_contract_file_count_matches_the_live_corpus(self, report: dict) -> None:
        live = len(sorted(C.CONTRACTS_DIR.glob("*.json")))
        assert report["contract_files"] == live, (
            f"工具报 {report['contract_files']} 份契约、真源现算 {live} 份 —— "
            "分母漂了，逐表结论全部失去参照"
        )
        assert live > 0, "契约目录为空 —— 语料本身没了"

    def test_row_identity_tables_are_a_strict_subset_of_all_tables(
        self, report: dict
    ) -> None:
        assert 0 < report["tables_with_row_identity"] <= report["tables_total"], (
            "有行身份的表数必须落在 (0, 表总数] 内；"
            f"实得 {report['tables_with_row_identity']} / {report['tables_total']}"
        )

    def test_unparseable_contracts_are_classified_not_swallowed(
        self, report: dict
    ) -> None:
        """不可解析的契约要**登记原因**，不能静默消失。

        它们是分母的一部分：静默跳过会让「128 张全体检过」看起来像满覆盖。
        """
        assert isinstance(report["contracts_unparseable"], dict)
        for name, reason in report["contracts_unparseable"].items():
            assert ":" in reason, f"{name} 的失败原因没带异常类型：{reason!r}"

    def test_audited_plus_blocked_accounts_for_every_candidate(
        self, report: dict
    ) -> None:
        """体检 + 受阻 == 候选表数，一张都不许凭空消失。"""
        rows = report["tables"]
        audited = [t for t in rows if t["blocked_by"] is None]
        blocked = [t for t in rows if t["blocked_by"] is not None]
        assert len(audited) == report["tables_audited"]
        assert len(blocked) == len(report["tables_blocked"])
        assert len(rows) == report["tables_with_row_identity"], (
            "候选表数与逐表明细条数不等 —— 中间有表被静默丢弃"
        )


class TestPerRowAccounting:
    """逐行账必须闭合 —— 可删 + 锁死 == 受管。"""

    def test_totals_close(self, report: dict) -> None:
        assert report["deletable_rows"] + report["locked_rows"] == report[
            "managed_rows"
        ], "可删 + 锁死 != 受管行 —— 有行既不在可删也不在锁死集合里"

    def test_each_table_closes_too(self, report: dict) -> None:
        for t in report["tables"]:
            if t["blocked_by"] is not None:
                continue
            assert t["deletable_count"] + t["locked_count"] == t["managed_rows"], (
                f"{t['table_key']} 逐行账不闭合："
                f"{t['deletable_count']}+{t['locked_count']} != {t['managed_rows']}"
            )
            first, last = t["region"]
            assert t["managed_rows"] == last - first + 1, (
                f"{t['table_key']} 受管行数与区间长度不等（区 {first}..{last}）"
            )

    def test_every_locked_row_has_a_reason(self, report: dict) -> None:
        """锁死行必须给得出原因 —— 「锁了但说不出为什么」等于结论不可复核。"""
        for t in report["tables"]:
            if t["blocked_by"] is not None or not t["locked_count"]:
                continue
            assert t["lock_reasons"], (
                f"{t['table_key']} 锁死 {t['locked_count']} 行却一个原因都没给"
            )

    def test_qualified_keys_have_no_duplicates(self, report: dict) -> None:
        """清单用限定键 —— 裸 `table_key` 跨契约不唯一（实测 3 份契约共用一个）。"""
        for field in ("fully_deletable_tables", "zero_deletable_tables"):
            keys = report[field]
            assert len(keys) == len(set(keys)), f"{field} 有重复项：无从定位是哪张表"
            for k in keys:
                assert k.count("::") == 2, (
                    f"{field} 的 {k!r} 不是 `契约::sheet::table` 限定键"
                )


class TestMeasurementDeclaration:
    """报告必须自带口径声明（铁律㉗：两个口径的数不可互相「纠正」）。"""

    def test_measured_block_is_present_and_specific(self, report: dict) -> None:
        m = report["measured"]
        for key in ("region_source", "substrate", "delete_count", "not_measured"):
            assert m.get(key), f"measured 缺 {key} —— 下游无从判断这份数字量的是什么"
        assert "未" in m["substrate"] or "原始" in m["substrate"]
        assert "GT_" in m["not_measured"], (
            "`not_measured` 必须点名它**没**量插桩工作簿的运行时区，"
            "否则这份数字会被当成上线准入结论"
        )

    def test_delete_count_is_echoed(self) -> None:
        rep = T.run_audit(count=3)
        assert rep["measured"]["delete_count"] == 3, (
            "`--count` 没回显到报告里 —— 两份不同 count 的 JSON 会长得一模一样"
        )


class TestCountIsNotDecorative:
    """`--count` 必须真的传进生产判定。"""

    def test_deletable_is_monotonically_non_increasing(self) -> None:
        """删更多行 ⇒ 可删起点数不增。

        🔴 这条是 `--count` 的**接线判据**：如果 count 没传进
        `find_undeletable_rows` / `find_dangling_sites`，四个 count 会得到**完全相同**
        的数字，下面的 `distinct > 1` 就打红。
        """
        counts = [T.run_audit(count=n)["deletable_rows"] for n in (1, 2, 5)]
        assert counts == sorted(counts, reverse=True) or len(set(counts)) > 1, (
            f"可删数随 count 非单调：{counts}"
        )
        for a, b in zip(counts, counts[1:]):
            assert b <= a, f"删更多行反而可删数变多：{counts}"
        assert len(set(counts)) > 1, (
            f"count=1/2/5 得到完全相同的可删数 {counts} —— "
            "`--count` 很可能没传进生产判定（装饰性开关）"
        )


class TestFailsClosedOnBrokenCorpus:
    """反向：语料坏了要 exit 2，**不能**报成「100% 可删」。"""

    def test_empty_template_root_exits_two(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(T, "TEMPLATE_ROOT", tmp_path / "nonexistent")
        rc = T.main([])
        captured = capsys.readouterr()
        assert rc == 2, (
            "模板根指到空目录时工具没 exit 2 —— 它会把「一张表都读不到」"
            "报成体检通过"
        )
        assert "不是" in captured.err, "失败信息没澄清这不是「都不可删」"

    def test_healthy_corpus_exits_zero(self) -> None:
        assert T.main(["--table", "endorse_discount_rows"]) == 0

    def test_zero_deletable_table_is_not_a_failure(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """「某表 0 行可删」是要报告的**事实**，不是失败。

        把它做成失败会逼着人改契约让脚本变绿 —— 那正好是本工具要防的事。
        """
        real = T.run_audit

        def _all_locked(**kwargs: object) -> dict:
            rep = real(**kwargs)  # type: ignore[arg-type]
            for t in rep["tables"]:
                if t["blocked_by"] is None:
                    t["deletable_count"] = 0
                    t["locked_count"] = t["managed_rows"]
            rep["deletable_rows"] = 0
            rep["locked_rows"] = rep["managed_rows"]
            return rep

        monkeypatch.setattr(T, "run_audit", _all_locked)
        assert T.main(["--json"]) == 0


class TestRendererDoesNotLie:
    """文本渲染不得把受阻表混进「可删比例」里。"""

    def test_blocked_tables_are_reported_separately(self, report: dict) -> None:
        text = T._render(report)
        if report["tables_blocked"]:
            assert "未能体检" in text
            for b in report["tables_blocked"]:
                assert b["blocked_by"].split(":")[0] in text, (
                    f"受阻原因 {b['blocked_by']!r} 没出现在报告里"
                )

    def test_json_mode_is_machine_readable(self, capsys: pytest.CaptureFixture[str]) -> None:
        T.main(["--json", "--table", "endorse_discount_rows"])
        payload = json.loads(capsys.readouterr().out)
        assert payload["tool"] == "check_row_deletion_readiness"
        assert payload["tables"], "--json 模式输出了空 tables"


class TestZeroDeletablePatternIsClassifiedNotJustListed:
    """🔴 「整表零可删」必须给出**结构性归类**，不能只丢一串表名。

    缘起：修掉「表头行被算进受管行」的口径缺陷后，浮出 **9 张**整表零可删的表
    （修之前是 0 张）。只报表名的话，读者要从 96 张候选里反推「为什么这几张不行」。
    实测这 9 张的锁死原因**全部**是 `single_cell` ⇒ 它们是**一个**结构性问题
    （`-2` 明细页的行被跨 sheet 单格引用指着）的 9 个实例，要做的判断是一次性的。

    🔴 归类维度是**锁死原因**而不是 sheet 名：首版按 sheet 名形态切，得 4 族
    （`明细表G#-#` / `H#-#` / `I#-#` / `租赁负债明细表H#-#`），而那 4 族的原因完全相同
    —— 把一个问题报成 4 个，读者会以为要做 4 次判断。下面 `test_reason_axis_...`
    这条用同一批数据两种切法的**族数差**把这个选择钉住。
    """

    def test_pattern_block_is_present_and_consistent(self, report: dict) -> None:
        pat = report["zero_deletable_pattern"]
        assert pat["table_count"] == len(report["zero_deletable_tables"]), (
            f"归类里 {pat['table_count']} 张、清单里 "
            f"{len(report['zero_deletable_tables'])} 张 —— 两侧必须同分母"
        )
        assert sum(f["table_count"] for f in pat["families"]) == pat["table_count"], (
            "各族表数之和 != 总数 —— 有表在归类时丢了"
        )

    def test_every_family_has_a_single_reason_or_is_flagged(self, report: dict) -> None:
        """🔴 每族必须能说出**共同原因**；说不出就要显式标为「归类失败」。

        少了这条，一个原因混杂的族会被当成「归类结果」端给读者。
        """
        pat = report["zero_deletable_pattern"]
        for fam in pat["families"]:
            if len(fam["lock_reasons"]) != 1:
                key = ",".join(fam["lock_reasons"])
                assert key in pat["mixed_reason_families"], (
                    f"族 {fam['lock_reasons']} 原因不唯一却没被标进 mixed_reason_families"
                )

    def test_reason_axis_gives_fewer_families_than_sheet_name_axis(
        self, report: dict
    ) -> None:
        """🔴 反向对照：同一批数据按 sheet 名切会得到**更多**族。

        这条证明「按原因归类」不是随手选的维度 —— 若两种切法族数相同，
        本条会红，届时应重新判断哪个维度才是决策依据。
        """
        import re

        rows = [
            t
            for t in report["tables"]
            if t["blocked_by"] is None and t["managed_rows"] and not t["deletable_count"]
        ]
        if not rows:
            pytest.skip("当前没有整表零可删的表 ⇒ 本条对照空转")
        by_reason = {",".join(sorted(t["lock_reasons"])) for t in rows}
        by_sheet = {re.sub(r"\d+", "#", t["excel_name"]) for t in rows}
        assert len(by_reason) < len(by_sheet), (
            f"按原因切得 {len(by_reason)} 族、按 sheet 名切得 {len(by_sheet)} 族 —— "
            "两者不再有区分度，归类维度的选择需要重新论证"
        )

    def test_verdict_matches_the_family_count(self, report: dict) -> None:
        pat = report["zero_deletable_pattern"]
        n = len(pat["families"])
        expected = (
            "none"
            if n == 0
            else ("single_structural_pattern" if n == 1 and not pat["mixed_reason_families"] else "multiple_patterns")
        )
        assert pat["verdict"] == expected, (
            f"verdict={pat['verdict']!r} 与族数 {n} / mixed="
            f"{pat['mixed_reason_families']} 不符"
        )

    def test_renderer_surfaces_the_pattern_not_just_names(self, report: dict) -> None:
        """🔴 文本渲染必须把归类讲出来（JSON 里有、人看的那份没有 = 等于没做）。"""
        pat = report["zero_deletable_pattern"]
        text = T._render(report)
        if not pat["table_count"]:
            assert "整表零可删（禁开表）：（无）" in text
            return
        assert "禁开表" in text
        assert str(pat["table_count"]) in text
        for fam in pat["families"]:
            for reason in fam["lock_reasons"]:
                assert reason in text, f"族原因 {reason} 没出现在文本报告里"


class TestBlockedTablesAreClassifiedByShapeNotLumped:
    """🔴 「未能体检」必须按形态分类，且分类本身要能被伪证。

    修之前 4 张表都报同一个 `footer_marker_not_found`，把三种不同的事混在一起：

    ============================================  ========================================
    真实形态                                        正确处置
    ============================================  ========================================
    契约 marker 与模板差一个**尾随冒号**              放宽尾随标点后能搜到 ⇒ 应进体检
    （实测 G4-7：模板 `三、审计说明：` vs 契约 `三、审计说明`）
    `footer_anchor` 为 **None**（合法形态，           登记为「本工具取不到区间」，
    引擎对它跳过 footer 校验）                        并写明**不等于「不可删」**
    **转置表**（一行一个字段、一列一个业务对象）        删「行」本身不成立 ⇒ 单独一类
    ============================================  ========================================

    只放宽**尾随标点**、不做模糊匹配：模糊匹配会让 `合计` 命中 `合计（不含税）` 之类的
    别的行 —— 那是**静默错答**，比找不到更坏。下面有一条专门钉这件事。
    """

    def test_every_blocked_reason_is_a_known_class(self, report: dict) -> None:
        known = (
            "transposed_table_row_deletion_not_applicable",
            "no_footer_anchor_region_unknown",
            "footer_marker_not_found",
            "template_missing",
            "sheet_not_in_template",
            "bad_anchor",
            "empty_region",
        )
        for b in report["tables_blocked"]:
            assert b["blocked_by"].split(":")[0] in known, (
                f"{b['table_key']} 的受阻原因 {b['blocked_by'][:60]!r} 不属已知类 —— "
                "出现新形态时应显式归类，不要塞进现有类"
            )

    def test_transposed_tables_are_a_separate_class(self, report: dict) -> None:
        """🔴 转置表单独一类：对它们谈「删物理行」不成立（删的应该是列）。

        分类依据是 `table_key` 含 `transposed`。这条同时防两个方向：
        含该后缀的必须归入转置类；转置类里不得混入不含该后缀的表。
        """
        blocked = {b["table_key"]: b["blocked_by"] for b in report["tables_blocked"]}
        transposed_class = {
            k for k, v in blocked.items() if v.startswith("transposed_table")
        }
        for key, reason in blocked.items():
            if "transposed" in key:
                assert key in transposed_class, (
                    f"{key} 带 transposed 后缀却归入 {reason.split(':')[0]!r}"
                )
        for key in transposed_class:
            assert "transposed" in key, (
                f"{key} 被归入转置类但 table_key 里没有 transposed —— 分类依据被放宽了"
            )

    def test_no_footer_anchor_reason_says_it_is_not_undeletable(
        self, report: dict
    ) -> None:
        """🔴 「取不到区间」的文案必须澄清它**不等于「不可删」**。

        少了这句，读者会把这几张表当成「禁开表」而不是「本工具没覆盖」——
        两者的后续动作完全不同。
        """
        for b in report["tables_blocked"]:
            if b["blocked_by"].startswith(("no_footer_anchor", "transposed_table")):
                assert "不等于" in b["blocked_by"], (
                    f"{b['table_key']} 的文案没澄清「取不到区间 ≠ 不可删」："
                    f"{b['blocked_by'][:80]}"
                )

    def test_marker_match_tolerates_only_trailing_punctuation(self) -> None:
        """🔴 变异反证：尾随标点放宽了，**别的**差异一律不放宽。

        模糊匹配的危害是静默错答（`合计` 命中 `合计（不含税）` ⇒ 区间末行取错，
        算出来的可删行数是错的但看起来很正常）。本条用一组正反样本钉住边界。
        """
        import io
        import zipfile

        NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"

        def probe(cell_text: str, marker: str) -> int | None:
            xml = (
                f'<worksheet xmlns="{NS}"><sheetData>'
                f'<row r="5"><c r="A5" t="inlineStr"><is><t>{cell_text}</t></is></c></row>'
                f"</sheetData></worksheet>"
            )
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w") as zf:
                zf.writestr("xl/worksheets/sheet1.xml", xml)
            footer = type("F", (), {"marker": marker, "search_column": "A"})()
            with zipfile.ZipFile(io.BytesIO(buf.getvalue())) as zf:
                return T._footer_row_by_marker(
                    zf, part="xl/worksheets/sheet1.xml", footer=footer, from_row=1
                )

        # 应命中：只差尾随标点（G4-7 的真实形态）
        assert probe("三、审计说明：", "三、审计说明") == 5, "尾随全角冒号没被放宽"
        assert probe("合计", "合计") == 5, "完全相同却没命中"
        assert probe("合计:", "合计") == 5, "尾随半角冒号没被放宽"

        # 不应命中：内容真的不同（放宽成模糊匹配就会在这里出错答）
        assert probe("合计（不含税）", "合计") is None, (
            "`合计（不含税）` 命中了 `合计` —— 匹配被放宽成模糊匹配，"
            "会静默取错区间末行"
        )
        assert probe("小计", "合计") is None, "`小计` 命中了 `合计`"
        assert probe("本年合计", "合计") is None, (
            "`本年合计` 命中了 `合计` —— 前缀差异不该被放宽"
        )
