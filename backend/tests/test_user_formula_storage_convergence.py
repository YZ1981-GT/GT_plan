"""用户公式存储收敛守卫（formula-management-runtime-closure R4 / Wave 3）。

**要防的缺陷**

改造前用户公式**只**落 ``WorkingPaper.parsed_data['user_formulas']``，而运行时
求值器 ``FormulaRuntimeCoordinator._load_formulas`` 只 ``select(WpFormula)``::

    wp_user_formulas.py::update_user_formulas  → parsed_data['user_formulas']
    wp_formula.py::save_formula                → wp_formula 表
    coordinator._load_formulas                 → **只读 wp_formula**

⇒ 用户在公式管理里编辑保存的公式**永远不会被 coordinator 求值**（两套互不可见
的存储，共用同一入口却落到两个容器）。

**实证基线（2026-08-06）**

- ``wp_formula`` 表 **0 行**、``parsed_data ? 'user_formulas'`` **0 行**
  ⇒ 收敛零迁移压力，越晚越贵
- ``wp_user_formula`` 表与 ``WpUserFormula`` ORM 模型**都不存在**
  （全仓 ``WpUserFormula(`` 0 命中）⇒ R4 是「建立存储」不是「迁移存储」
- ``wp_formula`` 唯一索引 = ``(wp_id, sheet_name, target_cell)``
  —— **不含 project_id**（spec design 首版写错）
- ``formula_source`` 取值域 = ``('preset','custom','reference')``
  —— **没有 'user'**（design 首版写的 ``formula_source='user'`` 会被
  ``save()`` 以 ``invalid_formula_source`` 拒绝写库）

spec: .kiro/specs/formula-management-runtime-closure/
      Requirements 4.1~4.7 / 8.4 / Property 9~12
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_BACKEND = _REPO_ROOT / "backend"
_ROUTER = _BACKEND / "app" / "routers" / "wp_user_formulas.py"
_SERVICE = _BACKEND / "app" / "services" / "wp_formula_service.py"
_COORD = _BACKEND / "app" / "services" / "formula_runtime" / "coordinator.py"


def _strip_comments(src: str) -> str:
    """剥 # 注释与三引号串。

    🔴 必须先剥：本 spec 的注释/docstring 里**写满了被禁的旧写法**
    （``parsed_data["user_formulas"] =`` 作为反例出现），裸 ``in src``
    会把说明文字数成真实代码 = 假红。
    """
    src = re.sub(r'"""[\s\S]*?"""', '""', src)
    src = re.sub(r"'''[\s\S]*?'''", "''", src)
    return re.sub(r"(?m)#.*$", "", src)


ROUTER_SRC = _ROUTER.read_text(encoding="utf-8")
ROUTER_BARE = _strip_comments(ROUTER_SRC)


def _func_body(src: str, name: str) -> str:
    """按**圆括号配对**跳过参数列表再截函数体（到下一个顶层 def/@router）。

    🔴 不能用「声明后第一个 `{`/`:`」定位 —— 参数列表里的类型注解会误命中
    （memory 已记该坑）。这里按行缩进截取，锚点是 `async def <name>(`。
    """
    m = re.search(rf"(?m)^async def {re.escape(name)}\(", src)
    assert m, f"未找到 async def {name}（抽取器失效或函数已改名）"
    start = m.start()
    nxt = re.search(r"(?m)^(?:@router|async def |def |class )", src[m.end():])
    end = m.end() + (nxt.start() if nxt else len(src))
    return src[start:end]


# ─────────────────── 解析器自检（防断言空转） ───────────────────


class TestExtractionSelfCheck:
    def test_strip_comments_actually_strips(self):
        """剥注释必须真生效 —— 否则下面的「禁写入」断言全是假绿。"""
        probe = '# parsed_data["user_formulas"] = {}\nx = 1\n'
        assert 'parsed_data["user_formulas"]' not in _strip_comments(probe)
        # 反向：真实代码不得被剥掉
        assert "x = 1" in _strip_comments(probe)

    def test_router_source_nonempty(self):
        assert len(ROUTER_BARE) > 1000, "剥注释后源码过短，抽取器可能失效"
        for anchor in ("update_user_formulas", "list_user_formulas",
                       "restore_preset_formula"):
            assert anchor in ROUTER_BARE, f"锚点 {anchor} 不存在"

    def test_func_body_extractor_works(self):
        body = _func_body(ROUTER_BARE, "update_user_formulas")
        assert "payload.formulas" in body, "函数体抽取失效"
        # 不得把下一个端点吞进来
        assert "restore_preset_formula" not in body


# ─────────────────── Property 9：PUT 不再写 parsed_data ───────────────────


class TestPutWritesTableNotParsedData:
    def test_put_does_not_write_formula_body_to_parsed_data(self):
        """Property 9：PUT 不得把**公式本体**写回 `parsed_data`（收敛不双写）。

        🔴 **判据于 2026-08-07 按实证收窄**（spec formula-management-runtime-closure
        Task 17）：原断言是「源码不得含 `parsed_data['user_formulas'] =` 赋值」，
        判据**过宽** —— 它把「表结构无法承载的溯源元数据」也一起禁掉了，
        而 ``WpFormula`` **没有 ``original_preset`` 列**（逐列核实：V052 基础列 +
        V100 三类型扩展 + V104 生命周期列，无一可承载「覆盖了哪条预设」）。
        后果：`restore_preset_formula` 的 ``restored_to_preset`` 与 GET 的
        ``original_preset`` 都从遗留键取 ⇒ 「PUT 完全不写」使新公式的
        「恢复默认」恒返回 ``None``（属性测试 P29
        ``restore(override(preset)) == preset`` 打红暴露）。

        ⇒ 正确不变量不是「一个字节都不写」，而是「**不得双写公式本体**」：
        表 = 公式本体唯一权威（运行时 `_load_formulas` 只读它），
        遗留键 = 仅承载表无列的溯源字段。
        故这里断言写回的**值只含 ``original_preset``**，
        且不得出现 ``formula`` / ``formula_type`` / ``edited_by`` 等本体字段。
        """
        body = _func_body(ROUTER_BARE, "update_user_formulas")

        assigns = re.findall(
            r"parsed_data\[[\"']user_formulas[\"']\]\s*=\s*(\w+)", body
        )
        # 允许 0 次（未来若表侧补了列）或 1 次（写溯源）；多次赋值说明有分散写入
        assert len(assigns) <= 1, (
            f"PUT 对 parsed_data['user_formulas'] 有 {len(assigns)} 处赋值 —— "
            "溯源写入必须收敛到一处"
        )

        if not assigns:
            return  # 完全不写：Property 9 原始形态，同样合法

        var = assigns[0]
        # 被赋的变量必须是「只装 original_preset」的精简字典，
        # 且构造处显式限定键名 —— 否则等于把整份条目双写回去。
        assert re.search(
            rf"{var}\s*(?::\s*dict\[[^\]]*\])?\s*=\s*\{{\s*\}}", body
        ), f"未找到 {var} 的空字典初始化 —— 无法确认它只装溯源字段"
        assert re.search(
            rf"{var}\[[^\]]+\]\s*=\s*\{{\s*[\"']original_preset[\"']\s*:", body
        ), (
            f"{var} 的赋值不是「只含 original_preset 的精简条目」 —— "
            "公式本体不得双写回 parsed_data"
        )
        # 反向：本体字段不得进入该变量
        forbidden = re.search(
            rf"{var}\[[^\]]+\]\s*=\s*\{{[^}}]*[\"'](?:formula|formula_type|edited_by|edited_at)[\"']\s*:",
            body,
        )
        assert not forbidden, (
            f"{var} 里出现公式本体字段（{forbidden.group(0)[:60]}…）—— 两套存储未收敛"
        )

    def test_put_preserves_original_preset_trace(self):
        """PUT 必须保留 ``original_preset`` 溯源（否则「恢复默认」拿不回预设）。

        与上一条互为正反：上一条禁本体双写，这一条要求溯源不丢。
        两条同时成立才等价于「职责互斥的双存储」。
        """
        body = _func_body(ROUTER_BARE, "update_user_formulas")
        assert "original_preset" in body, (
            "PUT 未处理 original_preset —— restore_preset_formula 的 "
            "restored_to_preset 会恒为 None（WpFormula 无该列）"
        )
        assert "flag_modified" in body, (
            "写 JSONB 未 flag_modified —— 就地改嵌套不标脏，UPDATE 不会发出"
        )

    def test_put_calls_wp_formula_service_save(self):
        body = _func_body(ROUTER_BARE, "update_user_formulas")
        assert "wp_formula_service.save(" in body, (
            "PUT 未经 wp_formula_service.save 写表 —— 用户公式不会被 coordinator 求值"
        )

    def test_put_uses_valid_formula_source(self):
        """`formula_source` 必须在 service 的取值域内（'user' 会被拒绝写库）。"""
        from app.routers.wp_user_formulas import USER_FORMULA_SOURCE
        from app.services.wp_formula_service import _VALID_FORMULA_SOURCES

        assert USER_FORMULA_SOURCE in _VALID_FORMULA_SOURCES, (
            f"USER_FORMULA_SOURCE={USER_FORMULA_SOURCE!r} 不在 "
            f"{_VALID_FORMULA_SOURCES} 内，save() 会以 invalid_formula_source 拒绝"
        )
        assert USER_FORMULA_SOURCE != "user", (
            "'user' 不是合法来源（design 首版写错）"
        )

    def test_put_uses_valid_formula_type(self):
        from app.routers.wp_user_formulas import USER_FORMULA_TYPE
        from app.services.wp_formula_service import _VALID_FORMULA_TYPES

        assert USER_FORMULA_TYPE in _VALID_FORMULA_TYPES, (
            f"USER_FORMULA_TYPE={USER_FORMULA_TYPE!r} 不在 {_VALID_FORMULA_TYPES} 内"
        )

    def test_put_rolls_back_on_reject(self):
        """整批拒绝时必须回滚，不留半落状态。"""
        body = _func_body(ROUTER_BARE, "update_user_formulas")
        assert "db.rollback()" in body, "校验失败未回滚 → 可能留下半落的表行"


# ─────────────────── Property 9b：GET 保留读兼容 ───────────────────


class TestGetMergesLegacy:
    def test_get_reads_table(self):
        body = _func_body(ROUTER_BARE, "list_user_formulas")
        assert "list_by_wp(" in body, "GET 未从 wp_formula 表读 —— 收敛后读不回来"

    def test_get_keeps_legacy_compat_branch(self):
        """遗留读兼容分支必须存在。

        🔴 全库实测 `parsed_data ? 'user_formulas'` 为 0 行，故它是**纯保险**；
        删掉后若某环境存有历史数据就会静默丢失 —— 本断言就是防它被当死代码删。
        """
        body = _func_body(ROUTER_BARE, "list_user_formulas")
        assert re.search(r"parsed_data.*user_formulas", body), (
            "GET 丢失了 parsed_data['user_formulas'] 读兼容分支"
        )

    def test_get_response_shape_unchanged(self):
        """响应形状零改动（前端零改动红线）：仍返 wp_id/count/user_formulas。"""
        body = _func_body(ROUTER_BARE, "list_user_formulas")
        for key in ('"wp_id"', '"count"', '"user_formulas"'):
            assert key in body, f"GET 响应缺 {key} —— 破坏前端契约"


# ─────────────────── DELETE 同步清两侧 ───────────────────


class TestDeleteClearsBothSides:
    def test_delete_removes_table_row(self):
        body = _func_body(ROUTER_BARE, "restore_preset_formula")
        assert "db.delete(" in body, (
            "DELETE 未删 wp_formula 行 —— 删完 GET 仍会从表里读回"
        )

    def test_delete_also_clears_legacy_key(self):
        body = _func_body(ROUTER_BARE, "restore_preset_formula")
        assert "user_formulas.pop(" in body, (
            "DELETE 未清遗留键 —— 删掉表行后 GET 仍从 parsed_data 读回"
        )


# ─────────────────── Property 10：coordinator 能看见 ───────────────────


class TestCoordinatorSeesUserFormulas:
    def test_load_formulas_has_no_formula_source_filter(self):
        """Property 10：`_load_formulas` 不得按 formula_source 过滤。

        加了过滤 ⇒ `formula_source='custom'` 的用户公式被排除在 mutation plan 外，
        收敛就白做了。
        """
        src = _strip_comments(_COORD.read_text(encoding="utf-8"))
        m = re.search(r"async def _load_formulas[\s\S]*?return list\(", src)
        assert m, "未找到 _load_formulas 查询体（结构已变）"
        body = m.group(0)
        assert "formula_source" not in body, (
            "_load_formulas 出现 formula_source 过滤 —— 用户公式会被排除在求值外"
        )
        assert "select(WpFormula)" in body, "_load_formulas 不再查 WpFormula"


# ─────────────────── Property 11：cell_key 往返无损 ───────────────────


class TestCellKeyRoundtrip:
    @pytest.mark.parametrize(
        "cell_key",
        [
            "Sheet1!A1",
            "资产负债表(合并)!AB12",
            "附注披露信息（国企）!C7",
            "审定表 H1-1!Z999",
            "a b c!A1",
        ],
    )
    def test_split_join_roundtrip(self, cell_key: str):
        from app.routers.wp_user_formulas import join_cell_key, split_cell_key

        sheet, cell = split_cell_key(cell_key)
        assert join_cell_key(sheet, cell) == cell_key

    @pytest.mark.parametrize(
        "cell_key",
        [
            "Sheet1!A1",
            "资产负债表(合并)!AB12",
            "附注披露信息（国企）!C7",
            "审定表 H1-1!Z999",
        ],
    )
    def test_regex_accepts_what_split_handles(self, cell_key: str):
        """`_CELL_KEY_RE` 放行的形态，`split_cell_key` 必须能正确拆。"""
        from app.routers.wp_user_formulas import _CELL_KEY_RE, split_cell_key

        assert _CELL_KEY_RE.match(cell_key)
        sheet, cell = split_cell_key(cell_key)
        assert sheet and cell
        assert "!" not in sheet, "sheet 段不得含 !"

    def test_split_rejects_nothing_silently(self):
        """sheet 名含 `!` 时 `_CELL_KEY_RE` 应拒绝（保证 partition 语义安全）。"""
        from app.routers.wp_user_formulas import _CELL_KEY_RE

        assert not _CELL_KEY_RE.match("a!b!A1")


# ─────────────────── 读路径不抛异常 ───────────────────


class TestSafeFunctionName:
    @pytest.mark.parametrize(
        "expr,expected",
        [
            ("=TB('1001','期末余额')", "TB"),
            ("=WP('D2','x','y')", "WP"),
            ("garbage", None),
            ("", None),
            (None, None),
        ],
    )
    def test_never_raises(self, expr, expected):
        """GET 读回历史数据时表达式可能不合法 —— 不得让整个列表 500。"""
        from app.routers.wp_user_formulas import _safe_function_name

        assert _safe_function_name(expr) == expected


# ─────────────────── 唯一索引口径 ───────────────────


class TestUniqueIndexEvidence:
    def test_unique_index_is_wp_sheet_cell(self):
        """冲突键实测 = (wp_id, sheet_name, target_cell)，**不含 project_id**。

        design 首版写「冲突键 (project_id, wp_id, sheet_name, target_cell)」是错的；
        本断言把实测口径钉死，防按错口径写 upsert。
        """
        from app.models.workpaper_models import WpFormula

        uniques = {
            idx.name: [c.name for c in idx.columns]
            for idx in WpFormula.__table__.indexes
            if idx.unique
        }
        assert uniques, "WpFormula 无唯一索引（结构已变）"
        cols = next(iter(uniques.values()))
        assert cols == ["wp_id", "sheet_name", "target_cell"], (
            f"唯一索引列变了：{uniques}"
        )
        assert "project_id" not in cols


# ─── Property 26：年度真源必须是 `audit_year`（否则用户公式一条都存不进去）───
#
# spec: formula-management-runtime-closure Task 18（Requirements 4.1, 10.5）
#
# 🔴 **2026-08-07 真实库实测发现的第 13 处缺陷**：`update_user_formulas` 原按
# ``_project.audit_period_end.year if _project.audit_period_end else 0`` 取年度，
# 而全库 **8 个项目 `audit_period_end` 全部为 NULL**、`audit_year` 均已填
# （2025 / 2024）⇒ 每个项目都算出 ``year=0``。
#
# ``year`` 直接传给 ``validate_refs_via_acnr`` → TB 域按
# ``TrialBalance.year == 0`` 查得**空集** ⇒ 含 `TB()` 的用户公式**全部**被判
# 悬空引用并 422 拒绝保存，而报错文案是「引用地址在当前项目中不存在」
# （指向数据缺失，实为年度取错 = 误导排查方向）。
#
# 平台其余 30+ 处一律用 `audit_year`（如 `_f1_import_export.py` 的
# ``year = int(wp_row.audit_year or 0)``），本文件是唯一例外 ⇒ 属实现偏差不是设计。
#
# 判据落在**取值表达式形态**上而不是「文件里出现过 audit_year」——
# memory 已记同族坑：断言标识符存在抓不住「把条件改成恒假」。


class TestYearSourceIsAuditYear:
    """年度取值必须优先 `audit_year`，且 `audit_period_end` 只能作次选。"""

    def test_resolved_year_prefers_audit_year(self):
        body = _func_body(ROUTER_BARE, "update_user_formulas")
        assert re.search(r"_resolved_year\s*=", body), "未找到 _resolved_year 赋值"
        # `audit_year` 必须出现在 `audit_period_end` **之前**（or 的短路顺序）
        i_year = body.find("audit_year")
        i_end = body.find("audit_period_end")
        assert i_year >= 0, (
            "年度取值未使用 `audit_year` —— 全库 audit_period_end 皆为 NULL，"
            "只读它会让每个项目都算出 year=0，含 TB() 的用户公式全部 422"
        )
        assert i_end < 0 or i_year < i_end, (
            "`audit_period_end` 排在 `audit_year` 之前 —— 短路顺序反了"
        )

    def test_audit_period_end_alone_is_forbidden(self):
        """反向自检：改造前那个「只读 audit_period_end」的形态必须已消失。"""
        body = _func_body(ROUTER_BARE, "update_user_formulas")
        legacy = re.search(
            r"_resolved_year\s*=\s*\(?\s*_project\.audit_period_end\.year\s+if",
            body,
        )
        assert legacy is None, "旧的「只读 audit_period_end」形态复活了"

    def test_real_projects_have_audit_year_but_no_period_end(self):
        """把「为什么必须改」这条实证钉进守卫（不连库版：断言注释里的依据在册）。

        真实库判据由 `scripts/diagnose/diagnose_formula_runtime_state.py` 复算；
        这里只保证该实证依据不被静默删掉 —— 否则下个会话会觉得
        「读 audit_period_end 更语义化」而改回去。
        """
        assert "audit_period_end` 全部为 NULL" in ROUTER_SRC or (
            "audit_period_end" in ROUTER_SRC and "全部为 NULL" in ROUTER_SRC
        ), "年度真源的实证依据注释被删 —— 该修复会被下个会话回退"

    def test_platform_canonical_field_is_audit_year(self):
        """交叉锁死：平台其余消费点确实用 `audit_year`（证明本文件不是特例）。"""
        sample = (
            _BACKEND / "app" / "routers" / "wp_render_strategies"
            / "_f1_import_export.py"
        )
        src = _strip_comments(sample.read_text(encoding="utf-8"))
        assert re.search(r"audit_year\s+or\s+0", src), (
            "参照点 `_f1_import_export.py` 已不再用 `audit_year or 0` —— "
            "平台年度真源可能变了，请复核本守卫的前提"
        )
