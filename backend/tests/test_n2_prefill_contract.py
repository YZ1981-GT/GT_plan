"""N2 审定表预填 **前后端契约** 守卫。

背景（2026-08-01 复盘实证的 P0）
--------------------------------
后端 `_build_adjudication_prefill` 曾返回 ``dict[str, float]``
（``{'N2-1-vat-audited': 123.45, ...}``），而前端 `N2TabAdjudication.vue` 用
``Array.isArray(pf) ? pf : null`` 判定 → **dict 传入恒得 null** →
`useN2Adjudication14` 落到 `DEFAULT_TAX_TYPES` 空行 → 审定表永远空 →
下游「披露表从审定表带入」也带不出任何数据。

**四层验证全绿查不出**：`props.htmlData` 是 `any` 故 TS/Volar 不报错；
vitest 从未喂真实 render 输出；浏览器实测的项目本就无持久化行，空行看起来「就是预期结果」。

本守卫锁死三件事：
1. 后端返回**数组**（不是 dict / 不是 scalar）
2. 数组项字段名与前端 `useN2Adjudication14` 的取值键**逐字一致**
3. 后端 `_CLASSIFY_KEY_TO_LABEL` 与前端 `n2TaxLabelMap.ts` 的
   `DISCLOSURE_LABEL_BY_CLASSIFY_KEY` + `normalizeTaxLabel` 合并规则**无漂移**

spec: n2-disclosure-and-extraction-alignment Task 6.1
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parent.parent / "app/routers/wp_render_strategies/_n2_taxes_payable.py"
_FRONTEND_ROOT = (
    Path(__file__).resolve().parents[2]
    / "audit-platform/frontend/src/components/workpaper"
)
_TAX_LABEL_MAP_TS = _FRONTEND_ROOT / "composables/n2TaxLabelMap.ts"
_ADJ_TAB_VUE = _FRONTEND_ROOT / "n2/core/N2TabAdjudication.vue"
_ADJ_COMPOSABLE_TS = _FRONTEND_ROOT / "composables/useN2Adjudication.ts"

_BACKEND_SRC = _BACKEND.read_text(encoding="utf-8")


def _strip_ts_comments(src: str) -> str:
    """去掉 TS 注释——守卫注释里常写反例，不去掉会误报。"""
    src = re.sub(r"/\*[\s\S]*?\*/", "", src)
    src = re.sub(r"//.*", "", src)
    return src


# ─── 1. 后端返回必须是数组 ───────────────────────────────────────────────────


def test_backend_return_annotation_is_list():
    """返回类型注解必须是 list（不能退回 dict）。"""
    m = re.search(r"async def _build_adjudication_prefill.*?-> (.*?):", _BACKEND_SRC, re.S)
    assert m, "_build_adjudication_prefill 未找到"
    ret = m.group(1).strip()
    assert ret.startswith("list["), f"返回类型必须是 list，实际: {ret}"


def test_render_declares_prefill_as_list():
    """render 内声明也必须是 list（防两处不一致）。"""
    assert "adjudication_prefill: list[dict[str, Any]] = []" in _BACKEND_SRC, (
        "render 内 adjudication_prefill 声明必须是 list[dict[str, Any]]"
    )


def test_no_legacy_dict_key_construction():
    """禁止旧 dict 键构造复活（这是 P0 的根因形态）。"""
    for banned in ('f"N2-1-{tt}-audited"', 'f"N2-1-{tt}-opening"'):
        assert banned not in _BACKEND_SRC, f"旧 dict 键构造复活: {banned}"


def test_all_return_paths_return_list():
    """所有 return 路径都返回 list（含异常分支），不能有 return dict。"""
    tree = ast.parse(_BACKEND_SRC)
    fn = None
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "_build_adjudication_prefill":
            fn = node
            break
    assert fn is not None, "_build_adjudication_prefill AST 未找到"
    returns = [n for n in ast.walk(fn) if isinstance(n, ast.Return)]
    assert returns, "无 return 语句"
    for r in returns:
        v = r.value
        # 允许：return []  /  return sorted(...)
        if isinstance(v, ast.List):
            continue
        if isinstance(v, ast.Call) and getattr(v.func, "id", "") == "sorted":
            continue
        pytest.fail(f"存在非 list 返回路径: {ast.dump(v)[:120]}")


# ─── 2. 字段名与前端取值键逐字一致 ───────────────────────────────────────────


def test_frontend_uses_array_is_array_guard():
    """前端确实用 Array.isArray 判定（本守卫的前提；若前端改判定方式须同步本测试）。"""
    src = _strip_ts_comments(_ADJ_TAB_VUE.read_text(encoding="utf-8"))
    assert "Array.isArray(pf)" in src, (
        "N2TabAdjudication.vue 不再用 Array.isArray(pf) 判定 —— "
        "契约前提变更，请同步更新本守卫与后端返回形态"
    )


def test_backend_fields_match_frontend_keys():
    """后端输出字段 ⊇ 前端 useN2Adjudication14 读取的键。"""
    ts = _strip_ts_comments(_ADJ_COMPOSABLE_TS.read_text(encoding="utf-8"))
    # 前端形如 p.tax_type ?? p.taxType ?? '其他'
    frontend_keys = set(re.findall(r"p\.([a-z_]+)\s*\?\?", ts))
    assert frontend_keys, "未从 useN2Adjudication.ts 抽到 p.xxx 取值键（正则失效？）"
    for key in frontend_keys:
        assert f'"{key}"' in _BACKEND_SRC, (
            f"前端读 p.{key} 但后端未输出该字段；前端键集={sorted(frontend_keys)}"
        )


def test_backend_emits_required_fields():
    """三个必需字段显式存在（反向自检：即便前端正则失效也守住）。"""
    for f in ("tax_type", "begin_unadj", "end_unadj"):
        assert f'"{f}"' in _BACKEND_SRC, f"后端缺必需字段 {f}"


# ─── 3. 后端映射表镜像前端 .ts（防双真源漂移）────────────────────────────────


def _backend_classify_key_to_label() -> dict[str, str]:
    m = re.search(r"_CLASSIFY_KEY_TO_LABEL: dict\[str, str\] = \{(.*?)\n\}", _BACKEND_SRC, re.S)
    assert m, "_CLASSIFY_KEY_TO_LABEL 未找到"
    ns: dict = {}
    exec("d = {" + m.group(1) + "\n}", ns)  # noqa: S102
    return ns["d"]


def _frontend_label_by_classify_key() -> dict[str, str]:
    """从 n2TaxLabelMap.ts 的 N2_TAX_LABEL_MAP 抽 classifyKey → disclosureLabel。"""
    ts = _strip_ts_comments(_TAX_LABEL_MAP_TS.read_text(encoding="utf-8"))
    m = re.search(r"export const N2_TAX_LABEL_MAP[^=]*=\s*\{(.*?)\n\}", ts, re.S)
    assert m, "N2_TAX_LABEL_MAP 未找到"
    out: dict[str, str] = {}
    for entry in re.finditer(
        r"disclosureLabel:\s*'([^']+)',\s*classifyKey:\s*'([^']+)'", m.group(1)
    ):
        out[entry.group(2)] = entry.group(1)
    assert out, "未从 N2_TAX_LABEL_MAP 抽到 classifyKey→label（正则失效？）"
    return out


def test_thirteen_fixed_rows_mirror_frontend():
    """13 固定行的 classifyKey→label 与前端逐条一致。"""
    backend = _backend_classify_key_to_label()
    frontend = _frontend_label_by_classify_key()
    assert len(frontend) == 13, f"前端 13 固定行数变了: {len(frontend)}"
    for key, label in frontend.items():
        assert key in backend, f"后端缺 classifyKey {key!r}（前端有）"
        assert backend[key] == label, (
            f"classifyKey {key!r} label 漂移: 后端={backend[key]!r} 前端={label!r}"
        )


def test_merge_rules_mirror_frontend_normalize():
    """合并规则与前端 normalizeTaxLabel 一致（iit→代扣代缴个人所得税 / 地方教育附加→教育费附加）。"""
    backend = _backend_classify_key_to_label()
    ts = _strip_ts_comments(_TAX_LABEL_MAP_TS.read_text(encoding="utf-8"))

    # 前端：normalizeTaxLabel('个人所得税') → '代扣代缴个人所得税'
    assert "return '代扣代缴个人所得税'" in ts, "前端 normalizeTaxLabel 缺个人所得税合并规则"
    assert backend.get("iit") == "代扣代缴个人所得税", (
        f"后端 iit 应合并到「代扣代缴个人所得税」，实际 {backend.get('iit')!r}"
    )

    # 前端：地方教育附加 → 教育费附加（用 includes('地方教育') 以容忍带科目前缀的真实科目名）
    assert "s.includes('地方教育')" in ts, (
        "前端 normalizeTaxLabel 缺地方教育附加合并规则（须用 includes 容忍 `应交税费_应交地方教育附加`）"
    )
    assert "return '教育费附加'" in ts, "前端 normalizeTaxLabel 缺「教育费附加」返回"
    assert backend.get("local-education") == "教育费附加", (
        f"后端 local-education 应合并到「教育费附加」，实际 {backend.get('local-education')!r}"
    )


def test_simple_vat_rule_present_on_both_sides():
    """🔴 「简易计税」归入增值税——前后端都必须有，且必须是**子串**匹配。

    源模板附注提示：「增值税，根据"应交税费-未交增值税、简易计税、
    转让金融商品应交增值税、代扣代缴增值税"科目贷方余额计算填列」。

    「简易计税」不含「增值税」子串，故通用条抓不到，必须单列；
    且真实科目名带前缀（`应交税费_简易计税`），精确匹配会漏。
    """
    # 后端
    assert '"简易计税" in name' in _BACKEND_SRC, (
        "后端 _classify_tax_type 缺「简易计税」→ vat 判定（源模板附注提示要求）"
    )
    # 前端（须用 includes 而非 ===）
    ts = _strip_ts_comments(_TAX_LABEL_MAP_TS.read_text(encoding="utf-8"))
    assert "s.includes('简易计税')" in ts, (
        "前端 normalizeTaxLabel 缺 includes('简易计税')（=== 精确匹配漏带前缀科目名）"
    )


def test_non_fixed_rows_keep_own_label():
    """源模板无固定行的税种保留自身名（走前端增行），不得被误映射进 13 固定行。"""
    backend = _backend_classify_key_to_label()
    frontend_labels = set(_frontend_label_by_classify_key().values())
    assert backend.get("stamp") == "印花税", "印花税应保留自身名"
    assert "印花税" not in frontend_labels, "印花税不应是 13 固定行之一（源模板没有）"


def test_sort_order_covers_thirteen_fixed_labels():
    """_LABEL_SORT_ORDER 覆盖且仅覆盖 13 固定行。"""
    m = re.search(r"_LABEL_SORT_ORDER: dict\[str, int\] = \{(.*?)\n\}", _BACKEND_SRC, re.S)
    assert m, "_LABEL_SORT_ORDER 未找到"
    ns: dict = {}
    exec("d = {" + m.group(1) + "\n}", ns)  # noqa: S102
    order = ns["d"]
    frontend_labels = set(_frontend_label_by_classify_key().values())
    assert set(order.keys()) == frontend_labels, (
        f"排序表与 13 固定行不一致\n  仅排序表有: {set(order) - frontend_labels}"
        f"\n  仅固定行有: {frontend_labels - set(order)}"
    )
    assert sorted(order.values()) == list(range(1, 14)), f"行序应为 1~13，实际 {sorted(order.values())}"


# ─── 4. 反向自检（防正则失效导致断言空转）────────────────────────────────────


def test_get_active_filter_called_with_full_signature():
    """🔴 `get_active_filter` 是 **async** 且签名 (db, table, project_id, year)。

    历史 bug（与 N5 同款）：单参调用 ``get_active_filter(ctx.project_id)`` →
    `TypeError` 被 ``except Exception`` 吞成 warning → TB 取数恒 0、预填恒空，
    且**无任何报错线索**。这比 dict/array 契约更底层，是 prefill 失效的第二层根因。

    实测项目 14fb8c10（active dataset 35 行 2221% 数据、year 匹配、无持久化行）
    在修复前 prefill 仍返回空数组，即由此坑造成。
    """
    stripped = "\n".join(
        ln for ln in _BACKEND_SRC.split("\n") if not ln.strip().startswith("#")
    )
    # 禁止单参调用复活
    assert "get_active_filter(ctx.project_id)" not in stripped, (
        "单参调用 get_active_filter(ctx.project_id) 复活 —— 真实签名需 (db, table, project_id, year)"
    )
    # 必须 await（async 函数）
    calls = re.findall(r"(\w*\s*=?\s*)(await\s+)?get_active_filter\(", stripped)
    assert calls, "未找到 get_active_filter 调用（反向自检）"
    for prefix, awaited in calls:
        assert awaited, f"get_active_filter 调用缺 await（async 函数）: {prefix!r}"
    # 必须传 4 个位置参数
    for m in re.finditer(r"await get_active_filter\(\s*([^)]*)\)", stripped, re.S):
        args = [a.strip() for a in m.group(1).split(",") if a.strip()]
        assert len(args) >= 4, (
            f"get_active_filter 位置参数不足 4 个（db, table, project_id, year）: {args}"
        )
        assert "ctx.db" in args[0], f"第 1 参应为 ctx.db，实际 {args[0]!r}"
        assert "__table__" in args[1], f"第 2 参应为 XxxTable.__table__，实际 {args[1]!r}"


def test_no_redundant_project_id_year_filter():
    """`get_active_filter` 已含 project_id + year + is_deleted，不应再手写重复条件。

    重复不致错但会掩盖「过滤器是否真生效」——曾出现「过滤器 TypeError 被吞、
    但手写条件仍在」导致查询看似正常却绕过数据集版本治理。
    """
    stripped = "\n".join(
        ln for ln in _BACKEND_SRC.split("\n") if not ln.strip().startswith("#")
    )
    assert "TbBalance.project_id == str(ctx.project_id)" not in stripped, (
        "手写 project_id 过滤应删除（get_active_filter 已含）"
    )


def test_selfcheck_sources_non_empty():
    assert len(_BACKEND_SRC) > 1000, "后端源码读取异常"
    assert len(_TAX_LABEL_MAP_TS.read_text(encoding="utf-8")) > 500, "n2TaxLabelMap.ts 读取异常"
    assert len(_ADJ_TAB_VUE.read_text(encoding="utf-8")) > 1000, "N2TabAdjudication.vue 读取异常"


def test_selfcheck_strip_comments_works():
    """stripComments 自检：原文含 // 注释，剥离后应变短。"""
    raw = _TAX_LABEL_MAP_TS.read_text(encoding="utf-8")
    assert "//" in raw or "/*" in raw, "样本无注释，自检无意义"
    assert len(_strip_ts_comments(raw)) < len(raw), "stripComments 未生效"
