"""地址坐标 mention 的**表级**粒度守卫

## 为什么是表级

地址目录（``address_registry``）登记到**单元格**（"资产负债表 > 存货 > 期末"），
但 AI 拿到整张表就能自己分析。让审计师去挑单元格既啰嗦，又因为同一坐标被多个来源
重复登记而在候选里列出好几条一模一样的项（浏览器实测：同一"资产负债表 > 存货 > 期末"
出现 4 次）。因此 mention 候选把 ``cell`` 维度聚合掉：一条候选 = 一张表。

## 本组守卫锁住的三件事

1. **粒度**：候选 id 是表级 URI（无 ``#cell``）、label 不含列名、同一张表不重复。
2. **域范围**：只有 ``tb`` / ``aux``（四表数据）。``report`` / ``note`` / ``wp`` 的
   表级引用已由「报表」「附注」「底稿」三个 mention 类型提供，重复列出会让同一张
   资产负债表在候选里出现两次。
3. **正文有真值**：``AddressEntry.value`` 在所有 ``build_*_entries`` 里都没赋值
   （恒 None），所以正文必须直接读业务表 —— 否则 AI 只拿到一句坐标元信息，
   一个数字都没有。
"""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest

from app.services.ai_chat.mention_service import (
    _ADDRESS_MENTION_DOMAINS,
    _address_sublabel,
    _load_address_content,
    _table_level_label,
)


# ---------------------------------------------------------------------------
# 域范围与聚合层级
# ---------------------------------------------------------------------------


def test_address_domains_exclude_types_covered_by_dedicated_mentions() -> None:
    """地址坐标只登记四表数据域；report/note/wp 由专门 mention 类型覆盖。"""
    assert set(_ADDRESS_MENTION_DOMAINS) == {"tb", "aux"}
    for excluded in ("report", "note", "wp"):
        assert excluded not in _ADDRESS_MENTION_DOMAINS, (
            f"{excluded} 域的表级引用已由专门 mention 类型提供，"
            "重复登记会让同一张表在候选里出现两次"
        )


def test_tb_aggregates_by_account_and_aux_by_account_dimension() -> None:
    """聚合键：试算表到科目、辅助余额到科目×维度（都不含列）。"""
    assert _ADDRESS_MENTION_DOMAINS["tb"] == ("source",)
    assert _ADDRESS_MENTION_DOMAINS["aux"] == ("source", "path")
    # 任何域都不得把 cell 列进聚合键 —— 那就退回单元格级了
    for domain, key_fields in _ADDRESS_MENTION_DOMAINS.items():
        assert "cell" not in key_fields, f"{domain} 的聚合键含 cell ⇒ 又变回单元格级"


# ---------------------------------------------------------------------------
# 表级 label / sublabel（纯函数）
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("cell_label", "expected"),
    [
        ("试算表 > 1001 库存现金 > 审定数", "试算表 > 1001 库存现金"),
        ("辅助余额 > 1122 应收账款 > 客户A > 期末", "辅助余额 > 1122 应收账款 > 客户A"),
        ("资产负债表 > 存货 > 期末", "资产负债表 > 存货"),
        ("只有一段", "只有一段"),
        ("", ""),
    ],
)
def test_table_level_label_drops_trailing_column(cell_label: str, expected: str) -> None:
    """表级 label = 单元格级 label 去掉末段列名。

    依赖 ``address_registry`` 各 ``build_*_entries`` 的统一 label 约定
    ``表 > 对象 > … > 列``，因此不在 mention 侧重拼一份命名。
    """
    assert _table_level_label(cell_label) == expected


def test_table_level_label_matches_registry_convention() -> None:
    """与 registry 的真实 label 格式对齐（双向锁死，防命名漂移）。

    这里直接用 ``build_trial_balance_entries`` / ``build_aux_entries`` 源码里的
    label 模板构造样例：若 registry 改了 label 格式而 mention 侧没跟上，本测试红。
    """
    code, name, col = "1001", "库存现金", "审定数"
    registry_tb_label = f"试算表 > {code} {name} > {col}"
    assert _table_level_label(registry_tb_label) == f"试算表 > {code} {name}"

    dim, acc_name = "客户A", "应收账款"
    registry_aux_label = f"辅助余额 > 1122 {acc_name} > {dim} > 期末"
    assert _table_level_label(registry_aux_label) == f"辅助余额 > 1122 {acc_name} > {dim}"


def test_sublabel_tells_which_columns_are_available() -> None:
    """副标签告诉审计师这张表有哪些列可用（表级引用的关键信息）。"""
    assert _address_sublabel([]) == "数据表"
    assert _address_sublabel(["期末", "期初"]) == "2 列：期末、期初"
    many = _address_sublabel(["未审数", "审定数", "AJE调整", "RJE调整"])
    assert many.startswith("4 列：")
    assert many.endswith("…"), "超过 3 列要有省略号，否则副标签会被撑长"


# ---------------------------------------------------------------------------
# 搜索：表级聚合行为（registry 用替身，不连库）
# ---------------------------------------------------------------------------


class _FakeEntry:
    """AddressEntry 的最小替身（只带聚合用到的字段）。"""

    def __init__(self, domain, source, path, cell, label, jump_route=""):
        self.domain = domain
        self.source = source
        self.path = path
        self.cell = cell
        self.label = label
        self.jump_route = jump_route


def _install_fake_registry(monkeypatch, entries_by_domain: dict[str, list]) -> list[int]:
    """替换 address_registry.get_domain，返回调用计数容器。"""
    from app.services import address_registry as ar

    calls: list[int] = []

    async def _fake_get_domain(db, project_id, year, template_type, domain):
        calls.append(year)
        return entries_by_domain.get(domain, [])

    monkeypatch.setattr(ar.address_registry, "get_domain", _fake_get_domain)
    return calls


@pytest.mark.asyncio
async def test_search_aggregates_cells_into_one_candidate_per_table(monkeypatch) -> None:
    """同一张表的多个单元格 ⇒ 一条候选，列被收集进 sublabel。"""
    from app.services.ai_chat.mention_service import MentionSearchService

    _install_fake_registry(
        monkeypatch,
        {
            "tb": [
                _FakeEntry("tb", "1001", "", "未审数", "试算表 > 1001 库存现金 > 未审数"),
                _FakeEntry("tb", "1001", "", "审定数", "试算表 > 1001 库存现金 > 审定数"),
                _FakeEntry("tb", "1001", "", "AJE调整", "试算表 > 1001 库存现金 > AJE调整"),
                _FakeEntry("tb", "1002", "", "审定数", "试算表 > 1002 银行存款 > 审定数"),
            ],
            "aux": [
                _FakeEntry("aux", "1122", "客户A", "期末", "辅助余额 > 1122 应收账款 > 客户A > 期末"),
                _FakeEntry("aux", "1122", "客户A", "期初", "辅助余额 > 1122 应收账款 > 客户A > 期初"),
                _FakeEntry("aux", "1122", "客户B", "期末", "辅助余额 > 1122 应收账款 > 客户B > 期末"),
            ],
        },
    )

    out = await MentionSearchService(None)._search_address("%", uuid4(), 20, 2025)

    ids = [c.id for c in out]
    # 4 张表：tb 两个科目 + aux 两个 (科目,维度)
    assert ids == [
        "tb://1001", "tb://1002",
        "aux://1122/客户A", "aux://1122/客户B",
    ], f"表级聚合结果不符（实际 {ids}）"

    # 粒度判据：没有任何 id 保留 #cell
    assert all("#" not in c.id for c in out), "候选仍是单元格级"
    # 去重判据
    assert len(set(ids)) == len(ids)
    # label 不含列名
    by_id = {c.id: c for c in out}
    assert by_id["tb://1001"].label == "试算表 > 1001 库存现金"
    assert by_id["aux://1122/客户A"].label == "辅助余额 > 1122 应收账款 > 客户A"
    # 三个单元格聚合成一张表，列都收进 sublabel
    assert by_id["tb://1001"].sublabel.startswith("3 列：")


@pytest.mark.asyncio
async def test_search_keyword_matches_table_level_label(monkeypatch) -> None:
    """关键词在表级 label / 科目码 / 维度上匹配。"""
    from app.services.ai_chat.mention_service import MentionSearchService

    _install_fake_registry(
        monkeypatch,
        {
            "tb": [
                _FakeEntry("tb", "1001", "", "审定数", "试算表 > 1001 库存现金 > 审定数"),
                _FakeEntry("tb", "1002", "", "审定数", "试算表 > 1002 银行存款 > 审定数"),
            ],
            "aux": [],
        },
    )
    svc = MentionSearchService(None)

    hit = await svc._search_address("%银行%", uuid4(), 10, 2025)
    assert [c.id for c in hit] == ["tb://1002"]

    by_code = await svc._search_address("%1001%", uuid4(), 10, 2025)
    assert [c.id for c in by_code] == ["tb://1001"]

    miss = await svc._search_address("%不存在的科目%", uuid4(), 10, 2025)
    assert miss == []


@pytest.mark.asyncio
async def test_search_without_year_returns_empty_and_skips_registry(monkeypatch) -> None:
    """没有年度 ⇒ 直接返回空，**不得**拿 year=0 去查一张必然为空的表。

    改造前 `_search_address` 向 registry 写死 ``year=0``，而
    ``build_trial_balance_entries`` / ``build_aux_entries`` 都按 year 过滤业务表
    ⇒ 试算表与辅助余额两域恒空，地址坐标候选里只剩不按年度过滤的 report 域。
    """
    from app.services.ai_chat.mention_service import MentionSearchService

    calls = _install_fake_registry(
        monkeypatch,
        {"tb": [_FakeEntry("tb", "1001", "", "审定数", "试算表 > 1001 库存现金 > 审定数")]},
    )

    out = await MentionSearchService(None)._search_address("%", uuid4(), 10, None)
    assert out == []
    assert calls == [], "year 缺失时不应发起任何域构建"


@pytest.mark.asyncio
async def test_search_passes_real_year_to_registry(monkeypatch) -> None:
    """反向对照：有年度时必须把**真实 year** 透传给 registry（不是 0）。"""
    from app.services.ai_chat.mention_service import MentionSearchService

    calls = _install_fake_registry(monkeypatch, {"tb": [], "aux": []})
    await MentionSearchService(None)._search_address("%", uuid4(), 10, 2025)

    assert calls, "未调用域构建"
    assert set(calls) == {2025}, f"传给 registry 的 year 应为 2025，实际 {calls}"
    assert 0 not in calls, "又把 year=0 传下去了 ⇒ 四表域会恒空"


@pytest.mark.asyncio
async def test_search_orders_trial_balance_before_aux(monkeypatch) -> None:
    """试算表排在辅助余额之前（不依赖中文字符的 Unicode 序）。"""
    from app.services.ai_chat.mention_service import MentionSearchService

    _install_fake_registry(
        monkeypatch,
        {
            "aux": [_FakeEntry("aux", "1122", "客户A", "期末", "辅助余额 > 1122 应收账款 > 客户A > 期末")],
            "tb": [_FakeEntry("tb", "9999", "", "审定数", "试算表 > 9999 zz末位科目 > 审定数")],
        },
    )

    out = await MentionSearchService(None)._search_address("%", uuid4(), 10, 2025)
    domains = [c.id.split("://", 1)[0] for c in out]
    assert domains == ["tb", "aux"], (
        f"试算表应优先于辅助余额（后者动辄上万维度组合），实际 {domains}"
    )


# ---------------------------------------------------------------------------
# 正文：必须是真实数值，不是坐标元信息
# ---------------------------------------------------------------------------


class _Result:
    def __init__(self, rows, scalar=None):
        self._rows = rows
        self._scalar = scalar

    def all(self):
        return self._rows

    def scalar_one_or_none(self):
        return self._scalar

    def scalar_one(self):
        return self._scalar

    def scalar(self):
        return self._scalar


class _FakeDb:
    """最小 db 替身；记录执行过的 SQL 以便断言过滤口径。"""

    def __init__(self, rows=None, scalar=None):
        self._rows = rows or []
        self._scalar = scalar
        self.statements: list[str] = []

    async def execute(self, statement=None, *_a, **_kw):
        self.statements.append(str(statement))
        return _Result(self._rows, self._scalar)

    async def rollback(self):
        return None


class _AccountCategory(str):
    """模拟真实的 AccountCategory 枚举 —— str(枚举) 是 'AccountCategory.asset'。

    守卫用替身时必须复现**真实形态**：早先这里放的是 "流动资产" 字符串，
    于是"枚举 repr 泄漏到正文"这个缺陷在测试里根本不可能出现，只有真实库实测
    才暴露（正文里出现了 `科目类别: AccountCategory.asset`）。
    """

    def __str__(self) -> str:  # noqa: D105
        return "AccountCategory.asset"


class _TbRow:
    standard_account_code = "1001"
    account_name = "库存现金"
    account_category = _AccountCategory("asset")
    opening_balance = Decimal("1000.00")
    unadjusted_amount = Decimal("2500.50")
    aje_adjustment = Decimal("-500.00")
    rje_adjustment = Decimal("0")
    audited_amount = Decimal("2000.50")


@pytest.mark.asyncio
async def test_trial_balance_table_content_carries_real_amounts() -> None:
    """试算表表级正文含各列**真实金额**，不是"域/URI/公式引用"元信息。"""
    content, label = await _load_address_content(
        _FakeDb(scalar=_TbRow()), "tb://1001", uuid4(), 2025
    )

    assert label == "试算表 > 1001 库存现金"
    assert content is not None
    # 🔴 改造前正文长这样：「地址坐标: … | 域: tb | 公式引用: TB('1001','审定数')」
    #    —— 一个数字都没有，AI 拿到等于没拿到
    assert "2,500.50" in content, "未审数金额未进入正文"
    assert "2,000.50" in content, "审定数金额未进入正文"
    assert "-500.00" in content, "AJE 调整未进入正文"
    for column_label in ("期初余额", "未审数", "AJE调整", "RJE调整", "审定数"):
        assert column_label in content, f"缺列 {column_label}"
    # 不该再出现纯坐标元信息
    assert "URI:" not in content and "公式引用:" not in content


@pytest.mark.asyncio
async def test_content_never_leaks_english_enum_repr() -> None:
    """正文不得泄漏英文枚举 repr（UI/上下文全中文）。

    真实库实测抓出过 `科目类别: AccountCategory.asset` —— ORM 列是枚举，
    直接插值就会带出类名。
    """
    content, _ = await _load_address_content(
        _FakeDb(scalar=_TbRow()), "tb://1001", uuid4(), 2025
    )
    assert content is not None
    assert "AccountCategory" not in content, "英文枚举 repr 泄漏到给模型的正文里"
    assert "asset" not in content


@pytest.mark.asyncio
async def test_four_table_reads_go_through_active_dataset_filter() -> None:
    """四表取数必须按 active 数据集过滤（平台铁律），不能裸写 is_deleted。

    真实库实测：裸过滤会把 superseded 版本的行一起查出来 —— 同一银行账户输出
    两条完全相同的明细（仅 dataset_id 不同），模型会误判为两个账户。
    """
    db = _FakeDb(scalar=_TbRow())
    await _load_address_content(db, "tb://1001", uuid4(), 2025)

    sql = " ".join(db.statements)
    assert "dataset" in sql.lower(), (
        "SQL 里没有任何 dataset 相关条件 ⇒ 没走 get_active_filter，"
        f"会读到历史版本数据。实际 SQL: {sql[:400]}"
    )


@pytest.mark.asyncio
async def test_aux_query_is_distinct() -> None:
    """辅助余额查询去重，避免冗余存储导致同一维度重复列出。"""
    db = _FakeDb(rows=[_AuxRow()])
    await _load_address_content(db, "aux://1122/客户A", uuid4(), 2025)

    sql = " ".join(db.statements).upper()
    assert "DISTINCT" in sql, "aux 查询未去重，同一维度会重复出现在正文里"


@pytest.mark.asyncio
async def test_no_year_means_no_four_table_content() -> None:
    """没有年度 ⇒ 不取四表正文（与搜索阶段同一约束，不猜年度）。"""
    db = _FakeDb(scalar=_TbRow())
    content, label = await _load_address_content(db, "tb://1001", uuid4(), None)
    assert content is None and label is None
    assert db.statements == [], "year 缺失时不应发起任何四表查询"


class _AuxRow:
    account_name = "应收账款"
    aux_type_name = "客户"
    aux_type = "customer"
    aux_name = "客户A"
    aux_code = "C001"
    opening_balance = Decimal("100.00")
    debit_amount = Decimal("50.00")
    credit_amount = Decimal("30.00")
    closing_balance = Decimal("120.00")


@pytest.mark.asyncio
async def test_aux_table_content_lists_rows_without_cross_type_summing() -> None:
    """辅助余额表级正文逐行列出并带辅助类型（按 aux_type 冗余存储，禁跨类型求和）。"""
    content, label = await _load_address_content(
        _FakeDb(rows=[_AuxRow()]), "aux://1122/客户A", uuid4(), 2025
    )

    assert label == "辅助余额 > 1122 应收账款 > 客户A"
    assert content is not None
    assert "客户 · 客户A" in content, "应带上辅助类型，便于模型区分同名维度"
    for amount in ("100.00", "50.00", "30.00", "120.00"):
        assert amount in content, f"缺金额 {amount}"
    assert "期初" in content and "期末" in content


@pytest.mark.asyncio
async def test_unknown_or_legacy_cell_level_uri_reports_unavailable() -> None:
    """非法 URI 与已不再提供的域 ⇒ 返回 None（由调用方记 unavailable）。

    历史会话里可能存着旧的单元格级 report/wp URI；此时必须诚实报不可用，
    不能编一段坐标元信息冒充正文。
    """
    db = _FakeDb()
    for uri in ("", "不是URI", "report://BS/BS-002#期末", "wp://E1-1/审定表#B7"):
        content, label = await _load_address_content(db, uri, uuid4(), 2025)
        assert content is None, f"{uri!r} 竟然返回了正文"
        assert label is None
