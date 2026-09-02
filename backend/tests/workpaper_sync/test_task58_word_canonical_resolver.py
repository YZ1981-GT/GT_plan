# -*- coding: utf-8 -*-
"""Task 58 守卫：统一 Word canonical resolver + 完整模板裁决清册。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 5 Task 58
Requirements: 7.7, 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.11, 9.12, 12.5
Properties: P39 / P40 / P41 / P42

═══ 每条 Property 的 oracle 落在哪 ═══

* **P39 config/callback Word 路径一致** —— 对同一 `(project_id, wp_code)` 真跑
  **五个意图**，断言 `WordResolution.identity_tuple()` 逐字段相等；再断言
  `wp_onlyoffice_router` 的读侧 `_onlyoffice_storage_dir()` 与写侧 callback 目标
  **AST 上真的都指向** `canonical_paths` / `word_resolution` 的入口（不是「有 import」
  ——那是 grep 式判据）。
* **P40 子码模板最具体** —— 用**真实模板库**逐条跑清册里 9 个受影响 B 子码，断言
  各自解析到**自己的** DOCX，且父级 XLSX 确实存在（父级存在是这条判据的前提，
  不成立就成了空转）。
* **P41 缺失不异类型回退** —— 真实数据两个反例：`S33-REV`（无任何载体 ⇒
  `template_missing`）与 `A16` / `A17`（只有程序表 XLSX ⇒ `document_type_mismatch`）。
  两类**必须**是不同异常类型 + 不同 error_code。
* **P42 路径安全** —— 目录穿越（project 段与 wp_code 段各一条）、项目外绝对路径、
  软链接越界、跨项目复用，逐条真建文件/链接后执行。

═══ 反假绿设计 ═══

1. **每类失败 kind 各自可达 + error_code 互不相同**
   `test_failure_kinds_are_reachable_and_mutually_distinct` 把五类失败**真的各触发
   一次**并收集 `(type, error_code)`，断言两个集合的基数都等于 5。这比「每类各测一遍」
   强：后者在两类被合并成同一 kind 时**全部仍绿**。
2. **清册判据落在真实执行上**
   清册守卫不查「某 wp_code 出现在 JSON 里」，而是按该 wp_code **真的 resolve 一次**
   再与 JSON 的 `unified_verdict` / `unified_relative_path` 逐字段比对。
3. **零比对不算通过**
   每个批量断言前先断言分母非空（`test_empty_projection_is_not_a_pass` 范式）。
4. **期望值来自源侧或字面量，不用被测函数算**
   18/9/1 从 `requirements.md` AC 7.7 原文抠出；载体路径从 `backend/wp_templates/`
   直接 glob；`pick_most_specific` 的期望结果写字面文件名。
"""

from __future__ import annotations

import ast
import json
import os
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:  # pragma: no cover - import 环境自举
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

from app.services import wp_template_finder as FINDER  # noqa: E402
from app.services.workpaper_sync import canonical_paths as CP  # noqa: E402
from app.services.workpaper_sync import word_resolution as WR  # noqa: E402

_LEDGER_JSON = _BACKEND / "data" / "workpaper_word_template_adjudication.json"
_ROUTER_PY = _BACKEND / "app" / "routers" / "wp_onlyoffice_router.py"
_FINDER_PY = _BACKEND / "app" / "services" / "wp_template_finder.py"
_WORD_RESOLUTION_PY = _BACKEND / "app" / "services" / "workpaper_sync" / "word_resolution.py"
_CANONICAL_PATHS_PY = _BACKEND / "app" / "services" / "workpaper_sync" / "canonical_paths.py"

#: 合成 project_id（只用于路径解析，不写盘）。
_PID = "11111111-2222-3333-4444-555555555555"

# 双哨兵：单哨兵会被历史空目录骗停
assert (_BACKEND / "app" / "main.py").is_file(), "哨兵失效：backend/app/main.py 不存在"
assert (_BACKEND / "wp_templates").is_dir(), "哨兵失效：backend/wp_templates 不存在"


def _read(path: Path) -> str:
    assert path.is_file(), f"文件不存在: {path}"
    return path.read_text(encoding="utf-8")


def _stripped(path: Path) -> str:
    """剥注释/docstring 后的源码 —— 本 spec 的改造说明必然原样写出被禁形态。"""
    sys.path.insert(0, str(_BACKEND / "scripts" / "gen"))
    from generate_workpaper_resolver_migration_matrix import (  # noqa: PLC0415
        strip_comments_and_docstrings,
    )

    text = strip_comments_and_docstrings(_read(path))
    # 反向自检：剥完还留着说明性中文长句 ⇒ 剥失败，后续「未出现」的结论不可信
    assert "Requirement 9.3 点名的分叉" not in text, "strip 失效：注释未被剥掉"
    return text


@pytest.fixture(scope="module")
def ledger() -> dict:
    assert _LEDGER_JSON.is_file(), (
        f"裁决清册缺失: {_LEDGER_JSON} —— 先跑 "
        "`py -3 backend/scripts/gen/generate_workpaper_word_template_adjudication.py --apply`"
    )
    payload = json.loads(_read(_LEDGER_JSON))
    assert payload.get("schema_version") == "word-template-adjudication:v1"
    assert payload.get("rows"), "清册 rows 为空 —— 空清册会让全部逐行断言恒成立（假绿）"
    return payload


def _rows(ledger: dict, **filters) -> list[dict]:
    out = [
        row
        for row in ledger["rows"]
        if all(row.get(key) == value for key, value in filters.items())
    ]
    return out


# ═══════════════════════════════════════════════════════════════════════════
# Property 39：config / download / callback / materialize / extract 同一路径
# ═══════════════════════════════════════════════════════════════════════════


class TestProperty39SingleWordResolver:
    """五个意图共用一个解析函数，且 router 读写两侧真的都指向它。"""

    def test_intent_enum_is_closed_and_covers_task_58_five(self):
        """封闭枚举恰好是 Task 58 点名的五个意图。"""
        assert {intent.value for intent in WR.WordResolutionIntent} == {
            "config", "download", "callback", "materialize", "extract",
        }
        # 策略表必须覆盖全部意图 —— 漏一个会在 `WORD_INTENT_POLICY[it]` 抛 KeyError，
        # 但那是运行期偶发；此处结构性锁死。
        assert set(WR.WORD_INTENT_POLICY) == set(WR.WordResolutionIntent)

    def test_all_five_intents_resolve_identical_paths(self, tmp_path: Path, monkeypatch):
        """同 (project, wp_code) 下五个意图的解析身份逐字段相等（P39 的本体）。

        `extract` 要求 canonical 已存在，故先真建一个文件 —— 这样五个意图**全部**
        走完整路径，而不是把 extract 排除在比对之外（排除等于放弃 1/5 覆盖）。
        """
        monkeypatch.setattr(CP, "storage_root", lambda: tmp_path)
        canonical = CP.onlyoffice_canonical_path(_PID, "B2-1", document_type="docx")
        canonical.parent.mkdir(parents=True, exist_ok=True)
        canonical.write_bytes(b"PK\x03\x04word")

        identities = {}
        for intent in WR.WordResolutionIntent:
            resolution = WR.WORD_RESOLVER.resolve(
                intent=intent, project_id=_PID, wp_code="B2-1"
            )
            identities[intent.value] = resolution.identity_tuple()

        assert len(identities) == 5, "分母不足 5 —— 未真正遍历全部意图"
        assert len(set(identities.values())) == 1, (
            f"五个意图解析出不同身份：{ {k: v[6] for k, v in identities.items()} } —— "
            "Requirement 9.3 点名的正是这种「一侧读 A、另一侧写 B」"
        )

    def test_write_target_equals_read_target(self, tmp_path: Path, monkeypatch):
        """写侧 `word_canonical_write_target` == 读侧 `config` 意图的 canonical path。"""
        monkeypatch.setattr(CP, "storage_root", lambda: tmp_path)
        read_side = WR.WORD_RESOLVER.resolve(
            intent="config", project_id=_PID, wp_code="B2-1"
        ).canonical_path
        write_side = WR.word_canonical_write_target(_PID, "B2-1")
        assert read_side == write_side

    def test_read_only_intent_cannot_be_used_to_write(self, tmp_path: Path, monkeypatch):
        """拿只读意图请求写句柄 ⇒ `WordIntentNotPermittedError`（该分支可达）。"""
        monkeypatch.setattr(CP, "storage_root", lambda: tmp_path)
        with pytest.raises(WR.WordIntentNotPermittedError):
            WR.WORD_RESOLVER.resolve_write_target(
                project_id=_PID, wp_code="B2-1", intent="config"
            )

    def test_only_callback_may_write(self):
        """写权限恰好只给 callback（表驱动，禁止两处各写一份）。"""
        writable = {
            intent.value
            for intent, policy in WR.WORD_INTENT_POLICY.items()
            if policy.may_write_canonical
        }
        assert writable == {"callback"}

    def test_only_extract_requires_existing_canonical(self):
        """只有 extract 强制 canonical 已存在（禁止用原始模板顶替审计师内容）。"""
        strict = {
            intent.value
            for intent, policy in WR.WORD_INTENT_POLICY.items()
            if policy.requires_existing_canonical
        }
        assert strict == {"extract"}

    def test_router_read_side_delegates_to_canonical_paths(self):
        """`_onlyoffice_storage_dir` 的函数体里**真有**对统一入口的调用。

        判据是 AST 里的 `ast.Call`，不是「模块出现过某字符串」—— 后者在把委派改回
        自拼、只留 import 时仍然绿（本仓库实测过这个形态）。
        """
        src = _stripped(_ROUTER_PY)
        sys.path.insert(0, str(_BACKEND / "scripts" / "gen"))
        from generate_workpaper_resolver_migration_matrix import (  # noqa: PLC0415
            called_names,
            function_source,
        )

        body = function_source(src, "_onlyoffice_storage_dir")
        assert body, "取不到 `_onlyoffice_storage_dir` 函数体 —— 判据无从落地"
        assert "onlyoffice_canonical_dir" in called_names(body), (
            "读侧未调用 `canonical_paths.onlyoffice_canonical_dir` —— "
            "自拼 `STORAGE_ROOT / projects / ... / onlyoffice` 就是 Requirement 9.3 的分叉源"
        )

    def test_router_callback_no_longer_hardcodes_divergent_word_path(self):
        """callback 里不得再出现自拼的 `storage/{project_id}/workpapers/...docx`。

        存量原文是 `Path(f"storage/{project_id}/workpapers/{wp_code}.docx")`：缺
        `projects/` 与 `onlyoffice/` 两段且**相对 CWD**。2026-08-29 磁盘实测其后果 ——
        `backend/storage/{pid}/workpapers/` 134 份 + `storage/{pid}/workpapers/` 25 份
        docx 落在读侧永不查看的位置，而读侧目录只有 16 份。
        """
        src = _stripped(_ROUTER_PY)
        assert 'f"storage/{project_id}/workpapers/' not in src, (
            "callback 仍在自拼分叉路径（Requirement 9.3）"
        )
        sys.path.insert(0, str(_BACKEND / "scripts" / "gen"))
        from generate_workpaper_resolver_migration_matrix import (  # noqa: PLC0415
            called_names,
            function_source,
        )

        body = function_source(src, "post_sheet_onlyoffice_callback")
        assert body, "取不到 callback 函数体"
        assert "word_canonical_write_target" in called_names(body), (
            "callback 未调用统一写侧入口 `word_canonical_write_target`"
        )


# ═══════════════════════════════════════════════════════════════════════════
# Property 40：子码模板最具体匹配
# ═══════════════════════════════════════════════════════════════════════════


class TestProperty40MostSpecificSubCode:
    """每个登记 B 子码解析为自己的 DOCX；父级 XLSX 存在也不得抢占。"""

    def test_sub_code_criterion_is_letter_class_agnostic(self):
        """子码判据与字母类无关（Requirement 9.4 原文「不得只对 A 类特殊处理」）。"""
        for code in ("A9-1", "B2-1", "B18-3-1", "B40-1", "S33-REV", "E1-3", "D2-2"):
            assert WR.is_word_sub_code(code), f"{code} 应判为子码"
        for code in ("D2", "F2", "A16", "G7", "S12A", ""):
            assert not WR.is_word_sub_code(code), f"{code} 不应判为子码"

    def test_finder_no_longer_uses_a_only_regex_for_sub_code_decision(self):
        """`find_template_file_any` 的自有-DOCX 探测在 A-only 分支**之前**。

        判据是**结构**（AST 语句序）而不是「文件里有没有那个正则」：正则仍保留在
        文件里（A 子码「不得回退父程序表」那条既有严格性还用它），所以字符串判据
        必然假绿。
        """
        tree = ast.parse(_read(_FINDER_PY))
        func = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "find_template_file_any"
        )
        docx_probe_line = None
        a_only_line = None
        for node in ast.walk(func):
            if isinstance(node, ast.Call):
                target = node.func
                name = getattr(target, "id", None) or getattr(target, "attr", None)
                if name == "_resolve_most_specific_docx" and docx_probe_line is None:
                    docx_probe_line = node.lineno
                if name == "match" and a_only_line is None:
                    src_seg = ast.get_source_segment(_read(_FINDER_PY), node) or ""
                    if "_LEGACY_A_ONLY_SUB_CODE_RE" in src_seg:
                        a_only_line = node.lineno
        assert docx_probe_line is not None, (
            "`find_template_file_any` 未调用 `_resolve_most_specific_docx` —— "
            "统一 resolver 成了死代码（假绿第①源）"
        )
        assert a_only_line is not None, "取不到 A-only 分支的判断位置"
        assert docx_probe_line < a_only_line, (
            f"自有-DOCX 探测在 L{docx_probe_line}，A-only 分支在 L{a_only_line} —— "
            "顺序反了则 B/S 子码仍会先落进主码分支抢父级 XLSX"
        )

    def test_type_filter_precedes_specificity_sort(self):
        """类型过滤必须在具体度排序**之前**（`pick_most_specific` 的判定顺序本体）。

        真实反例 `B30-13-1`：自有 XLSX（exact，具体度最高）+ 父级 `B30-13` 的 DOCX。

        * 先按类型过滤 ⇒ 候选只剩父级 DOCX ⇒ 返回它（有 DOCX 可用就用）；
        * 反过来先排序 ⇒ exact 的 XLSX 胜出，再被末尾类型门打回 ⇒ 表现成
          「明明有 DOCX 却报类型不符」。

        少了这一条，把类型过滤挪到排序之后在**受测的其他用例上**行为等价（末尾那道
        `assert_document_type` 会抛同一类型的异常），变异检验判 GREEN。
        """
        assert WR.own_template_carriers("B30-13-1", document_type="xlsx"), "反例前提失效"
        assert not WR.own_template_carriers("B30-13-1", document_type="docx")
        resolved = WR.resolve_word_template("B30-13-1")
        assert CP.document_type_of(resolved) == "docx"
        assert WR.derive_wp_code_from_filename(resolved.name) == "B30-13", (
            f"应返回父级 B30-13 的 DOCX，实得 {resolved.name}"
        )

    def test_bridge_rejects_ancestor_only_docx(self, tmp_path: Path, monkeypatch):
        """桥只认 exact-own DOCX：只有祖先 DOCX 时必须返回 None。

        ⚠️ 本例用**合成模板根**：真实模板库里「无自有工作簿 + 无自有 DOCX + 有祖先
        DOCX」的 wp_code 数量实测为 **0**（1539 个 wp_code 全量扫过），所以这条不变式
        在真实数据上没有实例。用合成根是为了让它**可达**而不是空转 —— 否则把
        `own_template_carriers` 换成 `collect_template_carriers` 在真实数据上行为等价，
        「只认 exact-own」这条限制没有任何判据（实测确认过它会判 GREEN）。
        """
        root = tmp_path / "wp_templates"
        (root / "Z").mkdir(parents=True)
        (root / "Z" / "Z9 父级说明.docx").write_bytes(b"PK\x03\x04word")
        (root / "_index.json").write_text(
            json.dumps({"files": []}, ensure_ascii=False), encoding="utf-8"
        )
        monkeypatch.setattr(WR, "TEMPLATE_ROOT", root)
        monkeypatch.setattr(CP, "TEMPLATE_ROOT", root)
        monkeypatch.setattr(WR, "TEMPLATE_INDEX_PATH", root / "_index.json")
        WR._load_carriers.cache_clear()
        try:
            assert not WR.own_template_carriers("Z9-1"), "合成根构造失败：Z9-1 不应有自有载体"
            # 严格 API **允许**祖先 DOCX —— missing 与 mismatch 的区分要靠祖先候选
            strict = WR.resolve_word_template("Z9-1")
            assert WR.derive_wp_code_from_filename(strict.name) == "Z9"
            # 桥**不允许** —— 拿父级 Word 顶替会倒转具体度
            assert WR.resolve_own_docx_or_none("Z9-1") is None
        finally:
            WR._load_carriers.cache_clear()

    def test_registered_b_sub_codes_resolve_own_docx_not_parent_xlsx(self, ledger: dict):
        """清册里 9 个受影响 B 子码逐条真跑：拿到自己的 DOCX，且父级 XLSX 确实存在。

        「父级 XLSX 存在」是这条判据的**前提**：若父级本来就没有工作簿，
        「不得抢占」就是空转（假绿第④源：真实数据上分支不可达）。
        """
        rows = _rows(ledger, adjudication="subcode_docx_recovered")
        assert len(rows) == 9, f"受影响子码分母应为 9，实得 {len(rows)}: {[r['wp_code'] for r in rows]}"
        for row in rows:
            code = row["wp_code"]
            # ① 父级工作簿确实存在（前提可达）
            ancestor_xlsx = [
                anc for anc in row["ancestor_carriers"] if anc["document_type"] == "xlsx"
            ]
            assert ancestor_xlsx, f"{code}: 没有父级 XLSX ⇒「不得抢占」这条判据在该行空转"
            for anc in ancestor_xlsx:
                assert (CP.TEMPLATE_ROOT / anc["relative_path"]).is_file()
            # ② 真跑一次统一 resolver（不是查清册字符串）
            resolved = WR.resolve_word_template(code)
            assert CP.document_type_of(resolved) == "docx", f"{code} 解析到非 DOCX"
            derived = WR.derive_wp_code_from_filename(resolved.name)
            assert derived is not None and derived.upper() == code.upper(), (
                f"{code} 解析到 {resolved.name}（归属 {derived}）—— 不是自己的 DOCX"
            )
            # ③ 存量分支的去向确实是父级工作簿（清册记录的缺陷成立）
            assert row["legacy_verdict"] == "parent_workbook", (
                f"{code}: 清册记 legacy_verdict={row['legacy_verdict']}，"
                "该行不该归入 subcode_docx_recovered"
            )

    def test_legacy_finder_now_returns_own_docx_for_affected_codes(self, ledger: dict):
        """存量入口 `find_template_file_any()` 对这 9 个码也已返回自有 DOCX。

        与上一条不同：上一条测**新** resolver，这一条测**旧调用点是否真的改到了**。
        缺这一条时把 `_resolve_most_specific_docx` 从 finder 里删掉，上一条仍全绿。
        """
        rows = _rows(ledger, adjudication="subcode_docx_recovered")
        assert rows, "分母为空"
        for row in rows:
            got = FINDER.find_template_file_any(row["wp_code"])
            assert got is not None, f"{row['wp_code']}: 存量入口返回 None"
            assert CP.document_type_of(got) == "docx", (
                f"{row['wp_code']}: 存量入口仍返回 {Path(got).name}"
            )

    def test_parent_docx_does_not_preempt_own_workbook(self):
        """祖先 DOCX 不得抢占自有工作簿（桥的第 1 条限制）。

        真实反例：`B30-13-1` 自有 XLSX，其父 `B30-13` 有 DOCX。若桥接受祖先 DOCX，
        `B30-13-1` 的解析会从自有工作簿翻成父级 Word —— 具体度倒转。
        """
        assert WR.own_template_carriers("B30-13-1", document_type="xlsx"), (
            "B30-13-1 的自有 XLSX 不在了 —— 该反例失效，需换一个具体度倒转样本"
        )
        assert WR.resolve_own_docx_or_none("B30-13-1") is None
        got = FINDER.find_template_file_any("B30-13-1")
        assert got is not None and CP.document_type_of(got) == "xlsx", (
            f"B30-13-1 应仍解析到自有工作簿，实得 {got and Path(got).name}"
        )

    def test_own_workbook_blocks_format_flip(self):
        """自有工作簿存在时桥不接管（桥的第 2 条限制）。

        真实反例：`S33-1` 同时有 `S33-1财务报告内部控制制度.xlsx` 与
        `S33-1程序修订说明.docx`。接管会把它从工作簿翻成 Word —— 属无授权的格式翻转。
        """
        assert WR.own_template_carriers("S33-1", document_type="xlsx")
        assert WR.own_template_carriers("S33-1", document_type="docx")
        assert WR.resolve_own_docx_or_none("S33-1") is None

    def test_derived_attribution_beats_prefix_attribution(self):
        """按派生 wp_code 归属，`A17-7A` 的文件不算 `A17-7` 的载体。

        存量 `_match_filename_prefix` 的前缀判据会把 `A17-7A审计…docx` 算成
        `A17-7` 的候选（`A17-7` 后跟的是字母不是数字）。派生判据把它归 `A17-7A`。
        """
        assert FINDER._match_filename_prefix(
            "A17-7A审计项目团队成员独立性声明书（适用于中国及国际审计准则）-专业技术委员会审核委员适用.docx",
            "A17-7",
        ), "前缀判据的形态变了 —— 本对照失效"
        own = WR.own_template_carriers("A17-7", document_type="docx")
        assert len(own) == 1, f"A17-7 的自有 DOCX 应恰好 1 份，实得 {[c.relative_path for c in own]}"
        assert "A17-7A" not in Path(own[0].relative_path).name


# ═══════════════════════════════════════════════════════════════════════════
# Property 41：模板缺失不异类型回退
# ═══════════════════════════════════════════════════════════════════════════


class TestProperty41NoCrossTypeFallback:
    """缺 DOCX 时返回明确 missing / type mismatch，绝不返回父级 XLSX。"""

    def test_missing_and_mismatch_are_distinct_types_and_codes(self):
        assert CP.TemplateMissingError is not CP.DocumentTypeMismatchError
        assert not issubclass(CP.TemplateMissingError, CP.DocumentTypeMismatchError)
        assert not issubclass(CP.DocumentTypeMismatchError, CP.TemplateMissingError)
        assert CP.TemplateMissingError.error_code != CP.DocumentTypeMismatchError.error_code

    def test_s33_rev_has_no_carrier_and_fails_as_template_missing(self, ledger: dict):
        """真实数据：`S33-REV` 在模板库无任何载体 ⇒ `template_missing`。"""
        rows = _rows(ledger, wp_code="S33-REV")
        assert len(rows) == 1, "S33-REV 未进清册 —— Requirement 7.7 点名它必须逐一裁决"
        row = rows[0]
        assert row["own_docx_carriers"] == [] and row["own_xlsx_carriers"] == []
        assert row["adjudication"] == "template_missing_adjudicated"
        assert row["owner_task"] == "63"
        with pytest.raises(CP.TemplateMissingError):
            WR.resolve_word_template("S33-REV")

    @pytest.mark.parametrize("parent_code", ["A16", "A17"])
    def test_workbook_only_parent_fails_as_type_mismatch_not_missing(
        self, parent_code: str, ledger: dict
    ):
        """真实数据：A16/A17 父码只有程序表 XLSX ⇒ `document_type_mismatch`。

        这条把「异类型 fail closed」钉在**真实载体**上，而不是合成目录 —— 假绿第④源
        要求「必须真有一个 DOCX 请求撞上 XLSX 模板」。
        """
        rows = _rows(ledger, wp_code=parent_code)
        assert len(rows) == 1, f"{parent_code} 未进清册"
        row = rows[0]
        assert row["own_xlsx_carriers"], f"{parent_code} 的自有工作簿不在了 —— 反例失效"
        assert row["own_docx_carriers"] == []
        assert row["unified_verdict"] == "document_type_mismatch"
        with pytest.raises(CP.DocumentTypeMismatchError) as excinfo:
            WR.resolve_word_template(parent_code)
        # 报错必须指出观测到的类型，否则调用方无法区分「没登记」与「类型错」
        assert excinfo.value.expected == "docx"
        assert excinfo.value.observed == "xlsx"

    def test_bridge_never_returns_cross_type_file(self, ledger: dict):
        """桥的返回值只可能是 None 或 DOCX —— 逐行真跑全清册。"""
        assert ledger["rows"], "分母为空"
        checked = 0
        for row in ledger["rows"]:
            got = WR.resolve_own_docx_or_none(row["wp_code"])
            checked += 1
            if got is not None:
                assert CP.document_type_of(got) == "docx", (
                    f"{row['wp_code']}: 桥返回了 {Path(got).name}（非 DOCX）"
                )
        assert checked == len(ledger["rows"]) == 50, f"实际比对 {checked} 行"

    def test_path_boundary_error_is_not_swallowed_by_bridge(self, monkeypatch):
        """桥只吞 missing / mismatch；`PathBoundaryError` 必须上抛（安全事件）。"""

        def _boom(*_args, **_kwargs):
            raise CP.PathBoundaryError(reason="outside_template_root", detail="synthetic")

        monkeypatch.setattr(WR, "pick_most_specific", _boom)
        with pytest.raises(CP.PathBoundaryError):
            WR.resolve_own_docx_or_none("B2-1")


# ═══════════════════════════════════════════════════════════════════════════
# Property 42：路径安全
# ═══════════════════════════════════════════════════════════════════════════


class TestProperty42PathSafety:
    """目录穿越、项目外绝对路径、软链接越界、跨项目复用均被拒。"""

    def test_project_segment_traversal_rejected(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr(CP, "storage_root", lambda: tmp_path)
        for bad in ("../../etc", "..", "a/b", "a\\b", " ", "p\x00"):
            with pytest.raises(CP.PathBoundaryError):
                WR.WORD_RESOLVER.resolve(intent="config", project_id=bad, wp_code="B2-1")

    def test_wp_code_segment_traversal_rejected_before_template_lookup(
        self, tmp_path: Path, monkeypatch
    ):
        """wp_code 段的安全门必须在**模板解析之前**跑。

        🔴 首轮实测正是这里出的问题：安全门原本内联在 `onlyoffice_canonical_path()`
        里（模板解析之后），于是 `../B2-1` 先撞上 `TemplateMissingError`（模板库里
        没有叫 `../B2-1` 的载体），路径穿越判据落在**永久不可达**分支上。
        """
        monkeypatch.setattr(CP, "storage_root", lambda: tmp_path)
        for bad in ("../B2-1", "B2-1/../../x", "B2-1\\..\\x", ".."):
            with pytest.raises(CP.PathBoundaryError):
                WR.WORD_RESOLVER.resolve(intent="config", project_id=_PID, wp_code=bad)

    def test_symlink_escape_rejected(self, tmp_path: Path, monkeypatch):
        """软链接越界：只做字符串前缀比较拦不住，判据必须在 realpath 之后。"""
        root = tmp_path / "root"
        outside = tmp_path / "outside"
        (root / "projects").mkdir(parents=True)
        outside.mkdir()
        link = root / "projects" / "escaped"
        try:
            link.symlink_to(outside, target_is_directory=True)
        except (OSError, NotImplementedError):
            pytest.skip("当前环境不允许建目录软链接（Windows 需开发者模式/管理员）")
        monkeypatch.setattr(CP, "storage_root", lambda: root)
        with pytest.raises(CP.PathBoundaryError):
            CP.onlyoffice_canonical_dir("escaped")

    def test_cross_project_reuse_rejected(self, tmp_path: Path, monkeypatch):
        """跨项目复用：A 项目的 canonical 路径不落在 B 项目根内。"""
        monkeypatch.setattr(CP, "storage_root", lambda: tmp_path)
        a = CP.onlyoffice_canonical_path("proj-a", "B2-1", document_type="docx")
        b_root = CP.project_canonical_root("proj-b")
        assert not CP.is_within_root(b_root, a)
        with pytest.raises(CP.PathBoundaryError):
            CP.assert_within_root(b_root, a, boundary="project_canonical_root")

    def test_storage_root_is_cwd_immune(self, tmp_path: Path, monkeypatch):
        """相对 `STORAGE_ROOT` 锚到 `BACKEND_ROOT`，不随 CWD 漂移。

        `storage/{pid}/workpapers/` 下那 25 份孤儿 docx 正是 CWD=仓库根时落的。
        """
        from app.core import config as app_config

        monkeypatch.setattr(app_config.settings, "STORAGE_ROOT", "./storage")
        monkeypatch.chdir(tmp_path)
        assert CP.storage_root() == CP.BACKEND_ROOT / "storage"

    def test_absolute_storage_root_is_preserved_verbatim(self, tmp_path: Path, monkeypatch):
        """绝对 `STORAGE_ROOT` 逐字保留（不被 realpath 改写）——存量调用方依赖它。"""
        from app.core import config as app_config

        monkeypatch.setattr(app_config.settings, "STORAGE_ROOT", str(tmp_path))
        assert CP.storage_root() == tmp_path
        assert CP.onlyoffice_canonical_dir(_PID) == (
            tmp_path / "projects" / _PID / "workpapers" / "onlyoffice"
        )

    def test_extension_spoofing_rejected(self, tmp_path: Path, monkeypatch):
        """扩展名伪装：canonical 路径的类型必须与声明一致。"""
        monkeypatch.setattr(CP, "storage_root", lambda: tmp_path)
        with pytest.raises(CP.DocumentTypeMismatchError):
            CP.onlyoffice_canonical_path(_PID, "B2-1", document_type="pdf")
        assert CP.onlyoffice_canonical_path(
            _PID, "B2-1", document_type="docx"
        ).suffix == ".docx"

    def test_resolved_template_stays_inside_template_root(self, ledger: dict):
        """全清册的解析结果都落在 `backend/wp_templates/` 内。"""
        checked = 0
        for row in ledger["rows"]:
            if row["unified_verdict"] != "resolved_docx":
                continue
            path = WR.resolve_word_template(row["wp_code"])
            CP.assert_within_root(CP.TEMPLATE_ROOT, path, boundary="template_root")
            checked += 1
        assert checked == 42, f"应有 42 行可解析，实得 {checked}"


# ═══════════════════════════════════════════════════════════════════════════
# 失败 kind 的可达性与互异性（反假绿第 1 条）
# ═══════════════════════════════════════════════════════════════════════════


class TestFailureKindsDistinctAndReachable:
    """五类失败**各自可达**且 `error_code` 互不相同。

    🔴 这条比「每类各测一遍」强：后者在两类被合并成同一 kind 时**全部仍绿**。
    """

    def test_failure_kinds_are_reachable_and_mutually_distinct(
        self, tmp_path: Path, monkeypatch
    ):
        monkeypatch.setattr(CP, "storage_root", lambda: tmp_path)
        observed: list[tuple[type, str]] = []

        cases = (
            ("template_missing", dict(intent="config", project_id=_PID, wp_code="S33-REV")),
            ("document_type_mismatch", dict(intent="config", project_id=_PID, wp_code="A16")),
            ("path_boundary", dict(intent="config", project_id="../x", wp_code="B2-1")),
            ("canonical_absent", dict(intent="extract", project_id=_PID, wp_code="B2-1")),
        )
        for label, kwargs in cases:
            with pytest.raises(Exception) as excinfo:  # noqa: PT011 - 就是要收集类型
                WR.WORD_RESOLVER.resolve(**kwargs)  # type: ignore[arg-type]
            err = excinfo.value
            code = getattr(err, "error_code", None)
            assert code, f"{label}: 异常缺 error_code —— Requirement 5.12 要求可定位"
            observed.append((type(err), code))

        with pytest.raises(WR.WordIntentNotPermittedError) as excinfo:
            WR.WORD_RESOLVER.resolve_write_target(
                project_id=_PID, wp_code="B2-1", intent="download"
            )
        observed.append((type(excinfo.value), excinfo.value.error_code))

        assert len(observed) == 5, "分母不足 5 —— 有 kind 未被真实触发"
        assert len({t for t, _ in observed}) == 5, (
            f"失败类型被合并：{sorted(t.__name__ for t, _ in observed)} —— "
            "合并后其中几条永久不可达（本 spec 已实测 3 次这个形态）"
        )
        assert len({c for _, c in observed}) == 5, (
            f"error_code 被合并：{sorted(c for _, c in observed)}"
        )
        assert {c for _, c in observed} == set(WR.WORD_RESOLUTION_FAILURE_CODES), (
            "实测到的 kind 与登记清单不一致 —— 清单必须与真实可达集合双向锁死"
        )

    def test_resolver_never_returns_none(self):
        """严格 API 找不到载体时抛异常，绝不返回 None（fail-open 是最贵的一类）。"""
        for code in ("S33-REV", "A16", "ZZ99-NOPE"):
            with pytest.raises((CP.TemplateMissingError, CP.DocumentTypeMismatchError)):
                result = WR.resolve_word_template(code)
                assert result is None, "不该走到这里"


# ═══════════════════════════════════════════════════════════════════════════
# 裁决清册（Requirement 7.7 / 12.5）
# ═══════════════════════════════════════════════════════════════════════════


class TestAdjudicationLedger:
    """清册分母来自真源、逐行有裁决、数字与 AC 7.7 双向锁死。"""

    def test_ledger_is_in_sync_with_sources(self):
        """`--check` 通过 —— 清册与真源一致且逐行已裁决。"""
        sys.path.insert(0, str(_BACKEND / "scripts" / "gen"))
        from generate_workpaper_word_template_adjudication import main  # noqa: PLC0415

        argv = sys.argv
        sys.argv = ["gen", "--check"]
        try:
            assert main() == 0, "清册与真源不一致或有未裁决行 —— 重跑 --apply"
        finally:
            sys.argv = argv

    def test_denominator_comes_from_sources_not_a_hand_written_list(self, ledger: dict):
        """分母 = componentType 真源里的 `word-template` ∪ A16/A17 前缀，不含手写清单。"""
        overrides = json.loads(
            _read(_BACKEND / "app" / "data" / "wp_code_overrides.json")
        )
        expected_generic = {k for k, v in overrides.items() if v == "word-template"}
        expected_chain = {
            k
            for k in overrides
            if (k.upper().startswith("A16") or k.upper().startswith("A17"))
            and overrides[k] != "word-template"
        }
        got_generic = {r["wp_code"] for r in _rows(ledger, ledger_class="generic_word_template")}
        got_chain = {
            r["wp_code"] for r in ledger["rows"] if r["ledger_class"].startswith("dedicated_chain")
        }
        assert expected_generic and expected_chain, "源侧分母为空 —— 后面全部断言空转"
        assert got_generic == expected_generic
        assert got_chain == expected_chain

        # 🔴 同时比对**生成器现算的**分母，而不是只比落盘 JSON：只比 JSON 时把
        # `ledger_wp_codes()` 里的某个分支短路掉，本用例仍然全绿（实测过 —— 只有
        # digest 用例会红，于是「分母来自真源」这条判据实际上没有守卫）。
        sys.path.insert(0, str(_BACKEND / "scripts" / "gen"))
        from generate_workpaper_word_template_adjudication import (  # noqa: PLC0415
            ledger_wp_codes,
        )

        live = ledger_wp_codes(overrides)
        assert live, "生成器现算的分母为空"
        live_generic = {code for code, klass in live if klass == "generic_word_template"}
        live_chain = {code for code, klass in live if klass.startswith("dedicated_chain")}
        assert live_generic == expected_generic, (
            "生成器现算的 generic 分母与源侧不一致 —— 分母被生成器悄悄收缩了"
        )
        assert live_chain == expected_chain, (
            "生成器现算的专用链分母与源侧不一致 —— A16/A17 链被漏掉"
        )
        assert len(live) == len(ledger["rows"]) == 50

    def test_ledger_counts_match_requirement_7_7(self, ledger: dict):
        """18 / 9 / 1 与 requirements.md AC 7.7 原文声明的数字逐条相等。

        期望值从**需求原文**抠，实测值从**模板库 + 真实 resolver 调用**得来 ——
        两条独立推导互相锁死。任一侧漂移（改了模板库或改了需求文本）都打红，
        必须重新裁决而不是改数字凑。
        """
        sys.path.insert(0, str(_BACKEND / "scripts" / "gen"))
        from generate_workpaper_word_template_adjudication import (  # noqa: PLC0415
            requirement_7_7_counts,
        )

        declared = requirement_7_7_counts()
        assert declared["declared_generic_docx"] == 18
        assert declared["declared_subcode_wrong_type"] == 9
        stats = ledger["stats"]
        assert stats["generic_docx_direct"] == declared["declared_generic_docx"]
        assert stats["subcode_docx_recovered"] == declared["declared_subcode_wrong_type"]
        assert stats["template_missing_adjudicated"] == 1, "S33-REV 是唯一缺失行"
        assert stats["row_count"] == 50 == 28 + 22

    def test_every_row_has_a_registered_adjudication_and_owner(self, ledger: dict):
        assert ledger["rows"], "分母为空"
        for row in ledger["rows"]:
            assert row["adjudication"] in WR_ADJUDICATIONS, (
                f"{row['wp_code']}: 裁决 {row['adjudication']!r} 未登记"
            )
            assert row["owner_task"], f"{row['wp_code']}: 缺 owner_task"
            assert row["source_refs"] or row["adjudication"] == "template_missing_adjudicated", (
                f"{row['wp_code']}: 既无 source_ref 也不是「无载体」—— 裁决无据"
            )

    def test_carrier_inventory_and_resolver_agree(self, ledger: dict):
        """载体清册与 resolver 是两条独立推导；不一致即接线错误。"""
        assert ledger["rows"], "分母为空"
        sys.path.insert(0, str(_BACKEND / "scripts" / "gen"))
        from generate_workpaper_word_template_adjudication import (  # noqa: PLC0415
            unified_verdict,
        )

        for row in ledger["rows"]:
            code = row["wp_code"]
            got_verdict, got_path = unified_verdict(code)
            assert got_verdict == row["unified_verdict"], f"{code}: verdict 漂移"
            assert got_path == row["unified_relative_path"], f"{code}: 路径漂移"
            if row["own_docx_carriers"]:
                assert got_verdict == "resolved_docx", (
                    f"{code}: 清册说有自有 DOCX {row['own_docx_carriers']}，"
                    f"resolver 却报 {got_verdict} —— 两侧判据未锁死"
                )
            if not row["own_docx_carriers"] and not any(
                anc["document_type"] == "docx" for anc in row["ancestor_carriers"]
            ):
                assert got_verdict != "resolved_docx", (
                    f"{code}: 清册说无任何 DOCX 载体，resolver 却解析出 {got_path}"
                )

    def test_adjudication_derivation_is_a_total_function(self):
        """裁决派生函数的真值表逐条断言（不依赖清册里恰好存在某类行）。"""
        sys.path.insert(0, str(_BACKEND / "scripts" / "gen"))
        from generate_workpaper_word_template_adjudication import (  # noqa: PLC0415
            derive_adjudication,
        )

        base = dict(ledger_class="generic_word_template", own_docx=1)
        assert derive_adjudication(
            **base, unified="resolved_docx", legacy="parent_workbook",
            affected_by_legacy_a_only_defect=True,
        ) == "subcode_docx_recovered"
        # A 子码不受该缺陷影响 ⇒ direct（哪怕 legacy 也命中父级工作簿）
        assert derive_adjudication(
            **base, unified="resolved_docx", legacy="parent_workbook",
            affected_by_legacy_a_only_defect=False,
        ) == "generic_docx_direct"
        assert derive_adjudication(
            **base, unified="resolved_docx", legacy="none",
            affected_by_legacy_a_only_defect=True,
        ) == "generic_docx_direct"
        assert derive_adjudication(
            ledger_class="generic_word_template", own_docx=0, unified="template_missing",
            legacy="none", affected_by_legacy_a_only_defect=True,
        ) == "template_missing_adjudicated"
        assert derive_adjudication(
            ledger_class="dedicated_chain_a16", own_docx=1, unified="resolved_docx",
            legacy="none", affected_by_legacy_a_only_defect=True,
        ) == "dedicated_chain_child_docx"
        assert derive_adjudication(
            ledger_class="dedicated_chain_a17", own_docx=0,
            unified="document_type_mismatch", legacy="own_workbook",
            affected_by_legacy_a_only_defect=False,
        ) == "dedicated_chain_workbook_only"
        # 祖先 DOCX 被解析出来但该码**没有自有** DOCX ⇒ 仍是 workbook_only
        # （`own_docx > 0` 这个合取项必须真的起作用）
        assert derive_adjudication(
            ledger_class="dedicated_chain_a17", own_docx=0, unified="resolved_docx",
            legacy="none", affected_by_legacy_a_only_defect=True,
        ) == "dedicated_chain_workbook_only"
        # generic Word 入口只有异类型载体 ⇒ 与「完全无载体」同归 missing 一类，
        # 但**不得**落到 generic_docx_direct（那会把「解析不到 DOCX」记成「已正确解析」）
        assert derive_adjudication(
            ledger_class="generic_word_template", own_docx=0,
            unified="document_type_mismatch", legacy="parent_workbook",
            affected_by_legacy_a_only_defect=True,
        ) == "template_missing_adjudicated"
        # 专用链行的 `template_missing` 优先于 chain 分支 —— 否则「无载体」会被
        # 记成「只有工作簿」，Task 63/64 的责任归属就错了
        assert derive_adjudication(
            ledger_class="dedicated_chain_a16", own_docx=0, unified="template_missing",
            legacy="none", affected_by_legacy_a_only_defect=True,
        ) == "template_missing_adjudicated"

    def test_carrier_ambiguity_rows_are_flagged_for_downstream(self, ledger: dict):
        """多载体行必须被标出来给 Task 62/63 逐一裁决，不能悄悄取一个。"""
        flagged = set(ledger["stats"]["carrier_ambiguity_rows"])
        assert flagged == {"B2-3", "B5-1", "B5-2"}, (
            f"多载体行集合变了：{sorted(flagged)} —— 需重新裁决取哪一份"
        )
        for code in flagged:
            assert len(WR.own_template_carriers(code, document_type="docx")) > 1
            # 取值仍必须确定（同具体度按文件名最短，与既有 finder 一致）
            first = WR.resolve_word_template(code)
            second = WR.resolve_word_template(code)
            assert first == second, f"{code}: 多载体下解析结果不稳定"

    def test_unattributed_index_files_are_reference_only(self, ledger: dict):
        """派生失败的索引文件只能是 `_reference/` 参考示例 —— 分母闭合，不静默丢文件。"""
        unattributed = ledger["stats"]["unattributed_index_files"]
        assert unattributed, "派生失败集合为空 ⇒ 该判据空转（参考示例本应派生失败）"
        for rel in unattributed:
            assert rel.startswith("_reference/"), (
                f"{rel} 派生不出 wp_code 却不在 `_reference/` 下 —— 可能是真丢了载体"
            )

    def test_template_index_path_is_single_source(self):
        """`wp_template_finder.INDEX_FILE` 与 `word_resolution.TEMPLATE_INDEX_PATH` 同一文件。"""
        assert FINDER.INDEX_FILE.resolve() == WR.TEMPLATE_INDEX_PATH.resolve()
        assert FINDER.TEMPLATES_DIR.resolve() == CP.TEMPLATE_ROOT.resolve()

    def test_s33_rev_carrier_hint_is_recorded_as_open_debt(self, ledger: dict):
        """`S33-1程序修订说明.docx` 与 S33-REV 同名业务含义 —— 登记为上游债，不擅自改名。

        S33-REV 的 `wp_name` 是「综合核查-程序修订说明」（`wp_account_mapping.json`），
        而模板库里那份文档挂在 `S33-1` 前缀下。本守卫只锁「事实还在」，改名/显式映射
        由 Task 63 裁决 —— Requirement 9.9 要求权威模板的可见结构与 source_ref 守卫
        锁死，运行时不得临时改写模板库。
        """
        hint = CP.TEMPLATE_ROOT / "S" / "S33-1程序修订说明.docx"
        assert hint.is_file(), (
            "S33-1程序修订说明.docx 不在了 —— 若已按 Task 63 裁决改名/新增 S33-REV 载体，"
            "请同步更新本守卫与清册"
        )
        rows = _rows(ledger, wp_code="S33-REV")
        assert rows[0]["unified_verdict"] == "template_missing", (
            "S33-REV 已能解析到载体 ⇒ 上游债已还，本守卫应改为断言解析成功"
        )


#: 裁决取值域（从生成器读，不在测试里抄第二份）
def _load_adjudications() -> tuple[str, ...]:
    sys.path.insert(0, str(_BACKEND / "scripts" / "gen"))
    from generate_workpaper_word_template_adjudication import (  # noqa: PLC0415
        ADJUDICATIONS,
    )

    return ADJUDICATIONS


WR_ADJUDICATIONS = _load_adjudications()


# ═══════════════════════════════════════════════════════════════════════════
# 反向自检：判据不是空转
# ═══════════════════════════════════════════════════════════════════════════


class TestGuardSelfCheck:
    """用替身复现旧行为，证明上面的判据真的会红。"""

    def test_a_only_regex_would_miss_b_sub_codes(self):
        """存量 A-only 正则对 9 个受影响码全部不命中（缺陷成立的直接证据）。"""
        nine = ["B18-3-1", "B18-3-2", "B2-1", "B2-11", "B2-3", "B2-6", "B2-8", "B40-1", "B40-2"]
        for code in nine:
            assert not FINDER._LEGACY_A_ONLY_SUB_CODE_RE.match(code), f"{code} 被 A-only 命中"
            assert WR.is_word_sub_code(code), f"{code} 未被统一判据识别为子码"
        assert FINDER._LEGACY_A_ONLY_SUB_CODE_RE.match("A9-1"), "A-only 正则形态变了"

    def test_prefix_only_boundary_check_is_fooled_by_traversal(self):
        """只做字符串前缀比较的边界判据拦不住 `..`（对照：本模块用形态白名单）。"""
        naive_ok = "projects/../../etc".startswith("projects/")
        assert naive_ok, "对照失效"
        with pytest.raises(CP.PathBoundaryError):
            CP.assert_wp_code_segment("../../etc", label="project_id")

    def test_resolver_is_not_dead_code(self):
        """`pick_most_specific` 真的被生产路径调用（假绿第①源的直接判据）。"""
        sys.path.insert(0, str(_BACKEND / "scripts" / "gen"))
        from generate_workpaper_resolver_migration_matrix import (  # noqa: PLC0415
            called_names,
        )

        calls = called_names(_stripped(_WORD_RESOLUTION_PY))
        assert "pick_most_specific" in calls, (
            "`canonical_paths.pick_most_specific` 无生产消费方 —— Task 12 交付的"
            "最具体匹配实现仍是死代码"
        )
        finder_calls = called_names(_stripped(_FINDER_PY))
        assert "resolve_own_docx_or_none" in finder_calls, (
            "存量 finder 未委派统一 Word resolver"
        )

    def test_canonical_dir_segments_are_declared_once(self):
        """canonical 目录段名只在 `canonical_paths` 出现一次（禁止第二处拼装）。"""
        router = _stripped(_ROUTER_PY)
        assert '"onlyoffice"' not in router and "'onlyoffice'" not in router, (
            "router 里仍有 `onlyoffice` 目录段字面量 —— 段名必须只在 canonical_paths 声明"
        )
        cp_src = _stripped(_CANONICAL_PATHS_PY)
        assert 'ONLYOFFICE_EDITOR_DIRNAME: Final[str] = "onlyoffice"' in cp_src
