"""Task 63 守卫：9 个 B 子码错型 + `S33-REV` 的逐 entry 裁决、载体三值与假切换移除。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 6 Task 63
Requirements: 7.7, 9.4, 9.5, 12.5, 12.8, 12.10, 12.11, 12.12
Properties: P40（子码最具体）/ P41（缺失不异类型回退）/ P69（逐 entry evidence）/
P70（跨 entry 不复用）

═══ 判据形态：真实执行 / 结构，不是「源码里有没有这个串」═══

本文件刻意避开三种会假绿的写法：

* **不**断言「源码里出现 `template_missing` 字样」—— 改名/删调用后字面量仍在。载体
  三值一律**真喂 wp_code 跑一次** resolver 再比对。
* **不**用清册 JSON 的 `unified_verdict` 当期望值去对它自己 —— 那是自证。期望值由
  `word_carrier_verdict()` 现算，清册是被校验的一侧。
* **不**用「popup 配置文件里没有 `S33-REV` 这个串」判假切换已移除 —— 该文件的注释里
  逐字写着 `'S33-REV'`（那段注释正是解释它为什么被移除）。判据先剥注释，且剥注释器
  自带反向自检（:meth:`TestGuardSelfCheck.test_comment_stripper_really_strips`）。

═══ 变异脚本 ═══

`backend/scripts/diagnose/mutate_task63_subcode_guards.py`
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from app.services.workpaper_sync import canonical_paths as CP
from app.services.workpaper_sync.word_resolution import (
    WORD_DOCUMENT_TYPE,
    WordCarrierVerdict,
    own_template_carriers,
    resolve_word_template,
    word_carrier_verdict,
)

ROOT = Path(__file__).resolve().parents[3]
RECORD_PATH = ROOT / "backend" / "data" / "workpaper_sync_task63_subcode_adjudication.json"
LEDGER_PATH = ROOT / "backend" / "data" / "workpaper_word_template_adjudication.json"
GENERATOR = ROOT / "backend" / "scripts" / "gen" / "generate_workpaper_task63_subcode_adjudication.py"

FRONTEND = ROOT / "audit-platform" / "frontend" / "src" / "components" / "workpaper"
WORD_EDITOR = FRONTEND / "WorkpaperWordEditor.vue"
POPUP_CONFIG_FILES = (
    FRONTEND / "wpPopupDocxConfigs.ts",
    FRONTEND / "wpPopupDocxConfigsB.ts",
    FRONTEND / "wpPopupDocxConfigsS.ts",
)
RENDER_STRATEGY = ROOT / "backend" / "app" / "routers" / "wp_render_strategies" / "_word_template.py"

#: 只在 `wpPopupDocxConfigsS.ts` 的**注释**里出现的串 —— 剥注释器的反向自检锚点。
_COMMENT_ONLY_MARKER = "DEPRECATED 墓碑"


# ═══════════════════════════════════════════════════════════════════════════
# fixtures
# ═══════════════════════════════════════════════════════════════════════════


@pytest.fixture(scope="module")
def record() -> dict:
    assert RECORD_PATH.is_file(), (
        f"Task 63 裁决记录不存在: {RECORD_PATH} —— 请跑 {GENERATOR.name}"
    )
    return json.loads(RECORD_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def ledger() -> dict:
    return json.loads(LEDGER_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def owner63_codes(ledger: dict) -> list[str]:
    return sorted(r["wp_code"] for r in ledger["rows"] if r.get("owner_task") == "63")


def _strip_ts_comments(text: str) -> str:
    """与生成器同形的 TS 注释剥离（守卫侧独立实现，两边都被反向自检覆盖）。"""
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    return re.sub(r"^\s*//.*$", "", text, flags=re.MULTILINE)


def _strip_vue_comments(text: str) -> str:
    """剥掉 Vue 模板注释 `<!-- -->` 与 JS 注释。

    必需：本文件为门控写的 `<!-- ... -->` 注释里含 `hasNoUsableCarrier` 字样，
    不剥就无法区分「注释里提到」与「模板里真的用了」。
    """
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    return _strip_ts_comments(text)


def _popup_entry_codes() -> set[str]:
    entry_re = re.compile(r"^\s*'([^']+)':\s*\{", re.MULTILINE)
    codes: set[str] = set()
    for path in POPUP_CONFIG_FILES:
        codes.update(
            m.group(1)
            for m in entry_re.finditer(_strip_ts_comments(path.read_text(encoding="utf-8")))
        )
    return codes


def _popup_template_paths() -> dict[str, str]:
    """wp_code -> templatePath（剥注释后按条目块切分，不跨条目串味）。"""
    entry_re = re.compile(r"^\s*'([^']+)':\s*\{", re.MULTILINE)
    path_re = re.compile(r"templatePath:\s*'([^']*)'")
    out: dict[str, str] = {}
    for f in POPUP_CONFIG_FILES:
        text = _strip_ts_comments(f.read_text(encoding="utf-8"))
        marks = [(m.group(1), m.start()) for m in entry_re.finditer(text)]
        for i, (code, pos) in enumerate(marks):
            end = marks[i + 1][1] if i + 1 < len(marks) else len(text)
            pm = path_re.search(text[pos:end])
            if pm:
                out[code] = pm.group(1)
    return out


# ═══════════════════════════════════════════════════════════════════════════
# 1. 载体三值：封闭、现算、与清册双向锁
# ═══════════════════════════════════════════════════════════════════════════


class TestWordCarrierVerdict:
    def test_verdict_domain_is_closed_and_matches_ledger_domain(self, ledger: dict):
        """三值封闭，且值域与清册 `unified_verdict` 的取值域**相等**（不是包含）。

        相等比包含强：清册出现第四种 verdict（比如有人加了 `resolved_by_alias`）时，
        包含判据仍绿而门控会把它当「不可编辑」静默处理。
        """
        enum_domain = {m.value for m in WordCarrierVerdict}
        assert enum_domain == {"resolved_docx", "document_type_mismatch", "template_missing"}
        ledger_domain = {r["unified_verdict"] for r in ledger["rows"]}
        assert ledger_domain == enum_domain, (
            f"清册 unified_verdict 取值域 {sorted(ledger_domain)} 与 WordCarrierVerdict "
            f"{sorted(enum_domain)} 不等 —— 两侧必须同名同域，否则门控会把未知 verdict "
            "静默归到某一类"
        )

    @pytest.mark.parametrize(
        "verdict,expected_usable",
        [
            (WordCarrierVerdict.resolved_docx, True),
            (WordCarrierVerdict.document_type_mismatch, False),
            (WordCarrierVerdict.template_missing, False),
        ],
    )
    def test_only_resolved_docx_is_usable(self, verdict, expected_usable: bool):
        """逐个真喂进去，而不是只测 resolved_docx 那一个。"""
        assert verdict.has_usable_docx_carrier is expected_usable

    def test_verdict_matches_ledger_row_by_row(self, ledger: dict, owner63_codes: list[str]):
        """10 个 entry：resolver **现算** verdict 必须逐个等于清册登记值。

        期望值来自现算，清册是被校验的一侧 —— 反过来（读清册当期望去对清册）是自证。
        """
        by_code = {r["wp_code"]: r for r in ledger["rows"]}
        assert owner63_codes, "清册里 owner_task=63 的行为空 —— 分母为空时本测试是重言式"
        for code in owner63_codes:
            computed = word_carrier_verdict(code)
            assert computed.value == by_code[code]["unified_verdict"], (
                f"{code}: resolver 现算 {computed.value!r} 与清册登记 "
                f"{by_code[code]['unified_verdict']!r} 不一致 —— 清册 stale 或 resolver 行为漂移"
            )

    def test_path_boundary_is_not_swallowed_into_a_verdict(self):
        """越界 wp_code 必须抛 `PathBoundaryError`，不得被映射成任何 verdict。

        把它吞成 `template_missing` 会让路径穿越尝试表现成「本底稿没有模板」而静默消失。
        """
        with pytest.raises(CP.PathBoundaryError):
            word_carrier_verdict("../B2-1")

    def test_s33rev_is_template_missing_and_b_subcodes_are_resolved(self, record: dict):
        """真实数据两侧都非空：1 条 missing + 9 条 resolved。"""
        missing = [e["wp_code"] for e in record["entries"] if not e["has_usable_docx_carrier"]]
        usable = [e["wp_code"] for e in record["entries"] if e["has_usable_docx_carrier"]]
        assert missing == ["S33-REV"]
        assert len(usable) == 9 and all(c.startswith("B") for c in usable), (
            f"9 个可用载体 entry 应全是 B 子码，实得 {usable}"
        )
        # 现算复核：不信记录里的布尔，重跑一次。
        assert word_carrier_verdict("S33-REV") is WordCarrierVerdict.template_missing
        with pytest.raises(CP.TemplateMissingError):
            resolve_word_template("S33-REV")


# ═══════════════════════════════════════════════════════════════════════════
# 2. render 策略：两种「拿不到」必须可区分
# ═══════════════════════════════════════════════════════════════════════════


class TestCarrierAbsencePayload:
    def test_absent_carrier_yields_verdict_payload(self):
        from app.routers.wp_render_strategies._word_template import _carrier_absence_payload

        payload = _carrier_absence_payload("S33-REV")
        assert payload is not None, (
            "零载体 wp_code 必须返回裁决载荷 —— 返回 None 会让前端落到"
            "「模板解析失败，请使用在线编辑模式」，把审计师指向不存在的路"
        )
        assert payload["template_structure"] is None
        assert payload["word_carrier"] == {
            "wp_code": "S33-REV",
            "verdict": "template_missing",
            "has_usable_carrier": False,
        }

    def test_type_mismatch_also_yields_verdict_payload(self):
        """只有 xlsx 载体的 wp_code 同样不可 Word 编辑（A16 是真实反例）。"""
        from app.routers.wp_render_strategies._word_template import _carrier_absence_payload

        payload = _carrier_absence_payload("A16")
        assert payload is not None
        assert payload["word_carrier"]["verdict"] == "document_type_mismatch"
        assert payload["word_carrier"]["has_usable_carrier"] is False

    def test_usable_carrier_keeps_returning_none(self):
        """载体存在却读失败属真实异常 —— 必须保持 None，不得被裁决载荷掩盖。

        这条是本组最重要的判据：若 `_carrier_absence_payload` 对**任何** wp_code 都
        返回载荷，一次可修的磁盘/权限故障会被永久呈现为「此底稿无模板」。
        """
        from app.routers.wp_render_strategies._word_template import _carrier_absence_payload

        for code in ("B2-1", "B40-2", "S12A", "S34-1-1"):
            assert _carrier_absence_payload(code) is None, (
                f"{code} 有可用 DOCX 载体，读失败时必须让 None 原样冒泡"
            )

    def test_boundary_violation_returns_none_and_logs_error(self, caplog):
        """越界 wp_code：不放行编辑、不打 500、留 ERROR。

        这条分支在 `word_carrier_verdict` 补上安全门**之前是不可达的**（verdict 从不
        抛 PathBoundaryError，越界会被吞成 template_missing）—— 即「有一段 except 却
        永远进不去」的死代码。锁住它，防止安全门被挪走后它重新变成死代码。
        """
        import logging

        from app.routers.wp_render_strategies._word_template import _carrier_absence_payload

        with caplog.at_level(logging.ERROR):
            assert _carrier_absence_payload("../B2-1") is None
        assert any(
            r.levelno >= logging.ERROR and "越界" in r.getMessage() for r in caplog.records
        ), "越界 wp_code 未记 ERROR —— 接线缺口会被静默成「无模板」"

    def test_render_strategy_routes_all_three_failure_points(self):
        """三处失败点都改调裁决函数，没有一处仍裸 `return None`。

        结构判据：`render()` 函数体内 `_carrier_absence_payload(` 的出现次数必须等于
        三个失败分支数。只断言「函数存在」的话，把任一分支改回 `return None` 仍绿。
        """
        src = RENDER_STRATEGY.read_text(encoding="utf-8")
        body_start = src.index("async def render(")
        body = src[body_start:]
        calls = body.count("return _carrier_absence_payload(wp_code)")
        assert calls == 3, (
            f"`render()` 里应有 3 处 `return _carrier_absence_payload(wp_code)`"
            f"（路径为空 / FileNotFoundError / 解析异常），实得 {calls} 处"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 3. 假切换移除：popup 配置与宿主门控
# ═══════════════════════════════════════════════════════════════════════════


class TestFakeSwitchRemoved:
    def test_every_popup_template_path_exists_on_disk(self):
        """98 条 docx 弹窗配置的 `templatePath` 必须逐条在模板库实存。

        Task 63 勘查实测原有 3 条指向不存在的文件（S12A / S33-REV / S34-1-1）：
        「下载模板」按钮拿它取文件名，路径错时审计师下到的文件名与内容不符。
        """
        paths = _popup_template_paths()
        assert len(paths) >= 90, f"popup 配置条目数异常偏少（{len(paths)}）—— 解析可能失效"
        missing = {
            code: rel
            for code, rel in paths.items()
            if not (CP.TEMPLATE_ROOT / rel.split("wp_templates/", 1)[-1]).is_file()
        }
        assert not missing, (
            "以下 popup 配置的 templatePath 在模板库不存在（首个: "
            f"{sorted(missing)[0]}）：{json.dumps(missing, ensure_ascii=False, indent=2)}"
        )

    def test_s33rev_has_no_popup_docx_config_entry(self):
        """S33-REV 不得有 docx 弹窗配置 —— 它的两个动作对零载体必然失败。

        判据在**剥注释后**的源码上做：该文件注释里逐字写着 `'S33-REV'`。
        """
        assert "S33-REV" not in _popup_entry_codes(), (
            "S33-REV 仍有 docx 弹窗配置条目 —— 「在线编辑」与「下载模板」对零载体 "
            "wp_code 都必然失败，属 Requirement 12.8 的假切换"
        )

    def test_word_editor_gates_all_three_edit_entrypoints(self):
        """宿主三要素齐备：computed 判据 + 模板门控 + initGenericEditor 早退。

        三要素缺一即红。只查「文件里有 hasNoUsableCarrier」会被注释里的字样骗过，
        故先剥注释；只查 computed 定义不查模板消费会漏「定义了但没接上」这种死代码
        （本 spec 记的假绿第①源）。
        """
        src = _strip_vue_comments(WORD_EDITOR.read_text(encoding="utf-8"))

        assert re.search(r"const\s+hasNoUsableCarrier\s*=\s*computed", src), (
            "缺 hasNoUsableCarrier computed 定义"
        )
        assert "props.htmlData?.word_carrier?.has_usable_carrier === false" in src, (
            "门控判据必须是后端下发的 `has_usable_carrier === false` 显式比较 —— "
            "写成 `!has_usable_carrier` 会把「字段缺失」也当成无载体，"
            "按 wp_code 字面量判则会在下一个零载体 wp_code 上静默失效"
        )
        assert 'v-if="hasNoUsableCarrier"' in src, "模板未按裁决门控缺失说明块"
        assert 'v-if="!hasNoUsableCarrier && ' in src, "结构化视图未受门控"
        assert 'v-else-if="!hasNoUsableCarrier"' in src, "在线编辑区未受门控"
        assert re.search(
            r"function initGenericEditor\(\)[\s\S]{0,400}?if \(hasNoUsableCarrier\.value\) return",
            src,
        ), "initGenericEditor 缺第二道结构门（防 UI 外的调用路径拉起 OO）"

    def test_word_editor_has_no_wp_code_literal_gate(self):
        """门控里不得出现 `S33-REV` 字面量 —— 裁决权必须留在后端。"""
        src = _strip_vue_comments(WORD_EDITOR.read_text(encoding="utf-8"))
        assert "S33-REV" not in src, (
            "宿主组件出现 S33-REV 字面量 —— 「有没有载体」是磁盘事实，"
            "组件无从得知，只能由后端 word_carrier 回答"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 4. 裁决记录：可复算、对账、不越 Task 61 的门
# ═══════════════════════════════════════════════════════════════════════════


class TestAdjudicationRecord:
    def test_record_is_reproducible(self):
        """`--check` 必须通过 —— 手改 JSON 或真源漂移都打红。"""
        proc = subprocess.run(
            [sys.executable, str(GENERATOR), "--check"],
            cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        assert proc.returncode == 0, (
            f"裁决记录与现算不一致：\n{proc.stdout}\n{proc.stderr}"
        )

    def test_entry_count_matches_requirement_7_7(self, record: dict, ledger: dict):
        """entry 数 = 清册对账过的「9 个子码错型」+「1 条 missing」。

        两个加数都取自清册**现算/已对账**字段，不在本文件写死 10：写死 10 再断言
        长度是 10 属重言式。
        """
        declared_subcode = ledger["requirement_7_7"]["declared_subcode_wrong_type"]
        declared_missing = ledger["stats"]["by_adjudication"]["template_missing_adjudicated"]
        assert record["stats"]["entry_count"] == declared_subcode + declared_missing
        assert len(record["entries"]) == record["stats"]["entry_count"]

    def test_no_publication_happened(self, record: dict):
        """本轮不发布 definition/bundle/representation、不注册 adapter（Task 61 未过）。

        这条是「不为满足数字伪造 contract/bundle/finalize」的机器判据。
        """
        for e in record["entries"]:
            assert set(e["published"].values()) == {None}, (
                f"{e['wp_code']}: published 出现非 null 值 —— Task 61 未通过前"
                "不得发布 bundle / representation / adapter"
            )
            assert e["sync_test_run_id"] is None
            assert e["required_scenario_set_digest"] is None
        assert record["stats"]["published_artifacts"] == 0
        assert record["stats"]["registered_adapters"] == 0

    def test_pending_entries_are_unverifiable_and_blocked(self, record: dict):
        """有载体的 9 条必须是 UNVERIFIABLE 且逐条挂着阻塞项。"""
        pending = [e for e in record["entries"] if e["has_usable_docx_carrier"]]
        assert len(pending) == 9
        for e in pending:
            assert e["verification_state"] == "UNVERIFIABLE"
            assert e["capability_verdict"] == "pending_bidirectional"
            assert "Task 61" in e["blocked_by"], (
                f"{e['wp_code']}: 未登记 Task 61 阻塞 —— 缺它会让「为什么没启用」无处追溯"
            )

    def test_missing_entry_is_adjudicated_not_blocked(self, record: dict):
        """无载体的那条是**已裁决**而不是被阻塞 —— 它不等 Task 61。"""
        e = next(x for x in record["entries"] if not x["has_usable_docx_carrier"])
        assert e["verification_state"] == "ADJUDICATED_MISSING"
        assert e["capability_verdict"] == "single_html_no_carrier"
        assert e["blocked_by"] == []
        assert e["fake_switch"]["action"] == "removed"
        assert e["fake_switch"]["popup_config_entry_removed"] is True

    def test_blocking_preconditions_are_open(self, record: dict):
        """BP-16..BP-20 全部 open，且各有 what / must_fix_before。"""
        bps = {b["id"]: b for b in record["blocking_preconditions"]}
        assert set(bps) == {"BP-16", "BP-17", "BP-18", "BP-19", "BP-20"}
        for bid, b in sorted(bps.items()):
            assert b["status"] == "open", f"{bid} 已被改成非 open —— 解除需真实证据"
            assert b["what"].strip() and b["must_fix_before"].strip()
            assert b["blocks"], f"{bid} 未声明它阻塞什么"

    def test_s33rev_hint_is_pending_not_silently_applied(self, record: dict):
        """载体线索必须是「待确认」，且两个方案与连带缺陷都在案。"""
        hint = record["s33rev_carrier_hint"]
        assert hint["resolution"] == "pending_business_confirmation", (
            "线索被自行落实了 —— 改运行时权威模板库或加显式映射都需业务确认"
        )
        assert hint["candidate_carrier"]["exists"] is True
        assert hint["candidate_carrier"]["derived_wp_code"] == "S33-1", (
            "候选载体的派生 wp_code 必须记为 S33-1（正是笔误本身），"
            "记成 S33-REV 会掩盖「它今天不归 S33-REV」这个事实"
        )
        assert len(hint["evidence_that_it_belongs_to_s33rev"]) >= 3
        opts = {o["id"]: o for o in hint["options"]}
        assert set(opts) == {"OPT-A", "OPT-B"}
        assert sum(1 for o in opts.values() if o["recommended"]) == 1
        # 连带缺陷：严格 resolver 对 S33-1 的误指必须现算一致。
        assert hint["collateral_defect"]["strict_resolver_returns_for_s33_1"] == (
            resolve_word_template("S33-1").relative_to(CP.TEMPLATE_ROOT).as_posix()
        )

    def test_no_b_subcode_has_admissible_field_identity(self, record: dict):
        """9 个 B 子码的字段身份基础**实测不合法** —— 0 个可发布契约是结论，不是未做完。

        期望值现算复核：不信记录里的布尔，重跑一次 parser + XML 直读。
        """
        from app.services.wp_docx_template_parser import parse_template

        pending = [e for e in record["entries"] if e["has_usable_docx_carrier"]]
        assert len(pending) == 9
        assert record["stats"]["field_identity_admissible_entries"] == [], (
            "有 entry 被判「字段身份可发布契约」—— 若源模板真的补了 ${token}，"
            "请连同 BP-20 的解除条件一起更新，不要只改这一个数字"
        )
        assert record["stats"]["dollar_token_total"] == 0
        assert record["stats"]["legacy_chinese_derived_total"] > 0, (
            "legacy 派生数为 0 会让「身份基础不合法」这条判据失去分母"
        )
        for e in pending:
            basis = e["field_basis"]
            assert basis is not None, f"{e['wp_code']}: 缺 field_basis"
            # 现算复核 ${} 计数
            path = CP.TEMPLATE_ROOT / basis["template_relative_path"]
            structure = parse_template(str(path))
            dollar = [
                ph for ph in structure.placeholders
                if re.fullmatch(r"\$\{[A-Za-z_][A-Za-z0-9_]*(?::[^}]+)?\}", ph.pattern or "")
            ]
            assert len(dollar) == basis["dollar_token_count"], (
                f"{e['wp_code']}: 记录的 ${{}} 占位符数 {basis['dollar_token_count']} "
                f"与现算 {len(dollar)} 不一致"
            )
            assert basis["field_identity_admissible"] is (basis["dollar_token_count"] > 0)
            assert "BP-20" in e["blocked_by"], (
                f"{e['wp_code']}: 字段身份不合法却未挂 BP-20 —— 「为什么没发契约」失去追溯锚点"
            )

    def test_zero_structured_field_entries_are_registered(self, record: dict):
        """B40-1 / B40-2 连 legacy 字段都为 0 ⇒ 结构化岛为空集，契约会是空转。"""
        assert record["stats"]["zero_structured_field_entries"] == ["B40-1", "B40-2"]
        for code in ("B40-1", "B40-2"):
            e = next(x for x in record["entries"] if x["wp_code"] == code)
            assert e["field_basis"]["has_any_structured_field"] is False
            assert e["field_basis"]["legacy_chinese_derived_count"] == 0

    def test_no_word_contract_was_staged_for_b_subcodes(self, record: dict):
        """本轮**没有**为任何 B 子码落契约文件 —— 「不为满足数字伪造 contract」的落地判据。

        既查 staged 区也查生产区：只查生产区的话，往 staged 区塞 9 份
        `placeholder_generic_N` 契约仍然全绿。
        """
        staged = ROOT / "backend" / "data" / "workpaper_sync_word_contracts"
        prod = ROOT / "backend" / "data" / "workpaper_sync_contracts"
        codes = [e["wp_code"] for e in record["entries"]]
        for area in (staged, prod):
            if not area.is_dir():
                continue
            for f in area.glob("*.json"):
                text = f.read_text(encoding="utf-8")
                for code in codes:
                    assert f'"{code}' not in text and f"{code}!" not in text, (
                        f"{f.name} 里出现了 Task 63 的 wp_code {code} —— "
                        "BP-20 未解除前不得为这些 entry 落契约"
                    )

    def test_bp20_gives_resolution_paths_not_a_workaround(self, record: dict):
        """BP-20 必须给出解除路径，且明确不绕开。"""
        bp = next(b for b in record["blocking_preconditions"] if b["id"] == "BP-20")
        assert bp["status"] == "open"
        assert len(bp["resolution_paths"]) >= 2
        assert bp["not_worked_around_because"].strip()
        assert "placeholder_generic" in bp["what"], (
            "BP-20 的 what 未点出不合法身份的具体形态 —— 读者无法复核"
        )

    def test_entries_do_not_share_carriers(self, record: dict):
        """P70：10 个 entry 的 own_docx_carriers 两两无交集。"""
        seen: dict[str, str] = {}
        for e in record["entries"]:
            for rel in e["own_docx_carriers"]:
                assert rel not in seen, (
                    f"载体 {rel} 同时属于 {seen[rel]} 与 {e['wp_code']} —— 跨 entry 复用载体"
                )
                seen[rel] = e["wp_code"]

    def test_b2_3_ambiguity_is_registered(self, record: dict):
        """B2-3 两份载体的二义必须在案并阻塞它的契约发布。"""
        assert record["stats"]["carrier_ambiguity_entries"] == ["B2-3"]
        own = own_template_carriers("B2-3", document_type=WORD_DOCUMENT_TYPE)
        assert len(own) == 2, f"B2-3 应有 2 份自有 DOCX，实得 {len(own)}"
        bp19 = next(b for b in record["blocking_preconditions"] if b["id"] == "BP-19")
        assert "B2-3" in bp19["what"] and len(bp19["options"]) >= 2

    def test_carrier_ambiguity_adjudication_covers_every_ambiguous_entry(self, record: dict):
        """载体二义 entry 逐个有裁决段，且两份载体被证明是**不同文档**。

        `sha256` 互不相同这条是关键：若两份只是同一文档的重复副本，正确处置是删一份
        而不是拆 entry；断言它们不同才能支撑「两封是审计流程的两个阶段」这个判断。
        """
        adj = {a["wp_code"]: a for a in record["carrier_ambiguity_adjudication"]}
        assert sorted(adj) == record["stats"]["carrier_ambiguity_entries"]
        assert adj, "二义裁决段为空 —— 分母为空时本测试是重言式"
        for code, a in sorted(adj.items()):
            digests = [c["sha256"] for c in a["carriers"]]
            assert len(digests) == a["carrier_count"] >= 2
            assert len(set(digests)) == len(digests), (
                f"{code}: 两份载体 sha256 相同 ⇒ 它们是同一文档的副本，"
                "应删一份而不是拆 entry"
            )
            assert all(c["exists"] for c in a["carriers"])
            # resolver 现算只返回其中一份，另一份必须被登记为不可达
            chosen = resolve_word_template(code).relative_to(CP.TEMPLATE_ROOT).as_posix()
            assert a["resolver_currently_returns"] == chosen
            assert a["unreachable_in_word_domain"] == [
                c["relative_path"] for c in a["carriers"] if c["relative_path"] != chosen
            ]
            assert a["unreachable_in_word_domain"], (
                f"{code}: 无不可达载体 ⇒ 二义不成立，本条登记是多余的"
            )
            assert a["resolution"] == "pending_business_confirmation"
            assert {o["id"] for o in a["options"]} == {"OPT-SPLIT", "OPT-PRIMARY"}
            assert all(o["recommended"] is None for o in a["options"]), (
                f"{code}: 已自行选定方案 —— 两个方案都需业务给出正本归属或新 wp_code"
            )


# ═══════════════════════════════════════════════════════════════════════════
# 5. 守卫自检（反向：判据本身必须是可失效的）
# ═══════════════════════════════════════════════════════════════════════════


class TestGuardSelfCheck:
    def test_comment_stripper_really_strips(self):
        """剥注释器反向自检：只在注释里出现的串，剥完必须消失。

        没有这条，`_strip_ts_comments` / `_strip_vue_comments` 被改坏（比如漏 DOTALL）
        后依赖它们的判据仍会出结果 —— 只是结果恒错。
        """
        src = (FRONTEND / "wpPopupDocxConfigsS.ts").read_text(encoding="utf-8")
        assert _COMMENT_ONLY_MARKER in src, (
            f"自检锚点 {_COMMENT_ONLY_MARKER!r} 已不在 wpPopupDocxConfigsS.ts 的注释中 —— "
            "请换一个只在注释里出现的串，不要删掉本自检"
        )
        assert _COMMENT_ONLY_MARKER not in _strip_ts_comments(src)

    def test_s33rev_appears_in_comments_so_naive_grep_would_be_fooled(self):
        """证明「剥注释」不是多余动作：裸 grep 会判「S33-REV 还在配置里」。"""
        raw = (FRONTEND / "wpPopupDocxConfigsS.ts").read_text(encoding="utf-8")
        assert "S33-REV" in raw, (
            "配置文件注释里已无 S33-REV 说明 —— 移除裁决的理由应当留在原地可读"
        )
        assert "S33-REV" not in _strip_ts_comments(raw)

    def test_vue_comment_stripper_handles_html_comments(self):
        """Vue 模板注释也必须被剥 —— 门控块的 `<!-- -->` 里含判据名。"""
        sample = '<!-- hasNoUsableCarrier 说明 -->\n<div v-if="x" />'
        assert "hasNoUsableCarrier" not in _strip_vue_comments(sample)
        assert 'v-if="x"' in _strip_vue_comments(sample)
