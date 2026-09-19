"""归档抽样记录章节 — 守卫

spec: sampling-evaluation-and-governance-closure
Validates: Requirements 8.1, 8.2, 8.3, 8.5, 8.6, 11.2, 11.3
Properties: Property 21

背景（2026-08-05 实证 F16）：`archive_completeness_service` /
`completeness_service` / `archive_manifest_service` 中 sampling/抽样/抽凭 提及数**全为 0**
—— 归档包完全不感知抽样，而 CAS 1314 的记录要求本身是归档件的组成部分。
"""

from __future__ import annotations

import inspect
from decimal import Decimal
from uuid import uuid4

import pytest

from app.services import archive_section_registry
from app.services.archive_generators import sampling_records_generator as gen


# ─── 注册 ────────────────────────────────────────────────────────────────────


def test_section_registered_with_unique_prefix():
    """章节已注册且前缀不与既有章节冲突。

    `register` 对同 order_prefix 是**覆盖**语义（后注册顶掉先注册），
    用已占前缀会静默删掉别人的章节 —— 立项时误用 05 就会顶掉「AI 贡献明细」。
    """
    sections = archive_section_registry.list_all()
    prefixes = [s.order_prefix for s in sections]
    assert len(prefixes) == len(set(prefixes)), f"归档章节前缀重复：{prefixes}"

    mine = [s for s in sections if s.order_prefix == gen.ARCHIVE_SECTION_PREFIX]
    assert len(mine) == 1, f"抽样记录章节未注册在前缀 {gen.ARCHIVE_SECTION_PREFIX}"
    assert mine[0].filename == gen.ARCHIVE_SECTION_FILENAME
    assert "1314" in mine[0].description


def test_ai_contributions_section_still_present():
    """反向断言：不得因新增章节而顶掉既有的「AI 贡献明细」（05）。"""
    sections = {s.order_prefix: s for s in archive_section_registry.list_all()}
    assert "05" in sections
    assert "AI" in sections["05"].description


def test_prefix_constant_is_not_05():
    assert gen.ARCHIVE_SECTION_PREFIX != "05", "05 已被 AI 贡献明细占用"


# ─── 生成内容（替身 DB）──────────────────────────────────────────────────────


class _Rec:
    """SamplingRecord 替身。"""

    def __init__(self, **kw):
        self.batch_id = kw.get("batch_id", uuid4())
        self.sampling_purpose = kw.get("sampling_purpose", "货币单元抽样（MUS）抽凭（年审阶段）")
        self.population_description = kw.get("population_description", "序时账；科目 1122")
        self.population_total_amount = kw.get("population_total_amount", Decimal("1000000.00"))
        self.population_total_count = kw.get("population_total_count", 500)
        self.sample_size = kw.get("sample_size", 30)
        self.sampling_method_description = kw.get(
            "sampling_method_description", "方法=货币单元抽样（MUS）；置信度=0.95"
        )
        self.sampling_method = kw.get("sampling_method", "mus")
        self.random_seed = kw.get("random_seed", 12345)
        self.dataset_id = kw.get("dataset_id", uuid4())
        self.deviations_found = kw.get("deviations_found", 2)
        self.misstatements_found = kw.get("misstatements_found", Decimal("500.00"))
        self.projected_misstatement = kw.get("projected_misstatement", Decimal("1200.00"))
        self.upper_misstatement_limit = kw.get("upper_misstatement_limit", Decimal("3000.00"))
        self.conclusion = kw.get("conclusion", "总体可接受：错报上限未超过可容忍错报")
        self.created_at = None


class _Proj:
    name = "测试项目"


class _Result:
    def __init__(self, value=None, rows=None, scalar_one=None):
        self._value = value
        self._rows = rows or []
        self._scalar_one = scalar_one

    def all(self):
        return self._rows

    def scalar(self):
        return self._value

    def scalar_one_or_none(self):
        return self._scalar_one


class _FakeSession:
    """按 execute 调用顺序返回预设结果：项目 → 记录列表 → 每批次凭证数。"""

    def __init__(self, rows, voucher_counts=None, raise_at=None):
        self._rows = rows
        self._counts = list(voucher_counts or [])
        self._n = 0
        self._raise_at = raise_at

    async def execute(self, stmt):  # noqa: ANN001
        self._n += 1
        if self._raise_at is not None and self._n == self._raise_at:
            raise RuntimeError("模拟查询失败")
        if self._n == 1:
            return _Result(scalar_one=_Proj())
        if self._n == 2:
            return _Result(rows=self._rows)
        return _Result(value=self._counts.pop(0) if self._counts else 0)


@pytest.mark.asyncio
async def test_no_batches_outputs_explicit_statement():
    """无抽样批次时输出明确说明，**不返回 None**（R8.5）。

    归档件里「明确说明未执行抽样」与「章节缺失」的审计含义不同。
    """
    out = await gen.generate_sampling_records(uuid4(), _FakeSession([]))
    assert out is not None
    text = out.decode("utf-8")
    assert "未执行抽样程序" in text
    assert "CAS 1314" in text


@pytest.mark.asyncio
async def test_complete_record_contains_all_cas1314_fields():
    """章节须含全部 CAS 1314 记录项（R8.2）。"""
    out = await gen.generate_sampling_records(
        uuid4(), _FakeSession([(_Rec(), "D2")], voucher_counts=[30])
    )
    text = out.decode("utf-8")
    for label in [
        "抽样目的",
        "总体描述",
        "总体金额",
        "总体笔数",
        "样本量",
        "样本量确定依据",
        "抽样方法",
        "随机种子",
        "抽样框版本",
        "偏差笔数",
        "推断错报",
        "错报上限",
        "结论",
    ]:
        assert label in text, f"归档章节缺少记录项：{label}"
    assert "D2" in text
    assert "已登记凭证数: 30" in text


@pytest.mark.asyncio
async def test_none_amount_shows_not_recorded_not_zero():
    """未记录的金额显示「未记录」而非 0 —— 两者审计含义完全不同。"""
    rec = _Rec(projected_misstatement=None, population_total_amount=None, random_seed=None)
    out = await gen.generate_sampling_records(
        uuid4(), _FakeSession([(rec, "F3")], voucher_counts=[0])
    )
    text = out.decode("utf-8")
    assert "推断错报: 未记录" in text
    assert "总体金额: 未记录" in text
    assert "随机种子: 未记录" in text


@pytest.mark.asyncio
async def test_incomplete_batch_listed_separately():
    """记录不完整的批次单独列出（R8.3）。"""
    rec = _Rec(projected_misstatement=None, upper_misstatement_limit=None, conclusion=None)
    out = await gen.generate_sampling_records(
        uuid4(), _FakeSession([(rec, "K1")], voucher_counts=[5])
    )
    text = out.decode("utf-8")
    assert "记录不完整的抽样批次" in text
    assert "缺少抽样评价" in text


@pytest.mark.asyncio
async def test_complete_batch_not_listed_as_incomplete():
    out = await gen.generate_sampling_records(
        uuid4(), _FakeSession([(_Rec(), "D2")], voucher_counts=[30])
    )
    assert "记录不完整的抽样批次" not in out.decode("utf-8")


@pytest.mark.asyncio
async def test_generation_failure_returns_placeholder_not_raise(caplog):
    """生成失败 → 占位说明 + WARNING，不抛出（R8.6：不得让归档整体失败）。"""
    out = await gen.generate_sampling_records(uuid4(), _FakeSession([], raise_at=1))
    assert out is not None
    text = out.decode("utf-8")
    assert "本章节生成失败" in text
    assert "未丢失" in text, "占位说明须告知原始留痕仍在，避免误判为数据丢失"


@pytest.mark.asyncio
async def test_multiline_conclusion_is_indented():
    """结论含 Wave 2 三项摘要（多行）时须逐行缩进，不破坏文本结构。"""
    rec = _Rec(conclusion="总体可接受\n【偏差性质】系统性偏差 2 笔（1800.00 元）")
    out = await gen.generate_sampling_records(
        uuid4(), _FakeSession([(rec, "D2")], voucher_counts=[1])
    )
    text = out.decode("utf-8")
    assert "    总体可接受" in text
    assert "    【偏差性质】系统性偏差 2 笔（1800.00 元）" in text


# ─── 结构约束 ────────────────────────────────────────────────────────────────


def test_generator_excludes_soft_deleted_records():
    """已撤销批次（软删）不得出现在归档件里。"""
    src = inspect.getsource(gen._generate)
    assert "SamplingRecord.is_deleted == sa.false()" in src
    assert "SampledVoucher.is_deleted == sa.false()" in src


def test_generator_never_raises_by_construction():
    """公开入口必须整体 try/except（归档不得因单章节失败而整体失败）。"""
    src = inspect.getsource(gen.generate_sampling_records)
    assert "except Exception" in src
    assert "return await _generate" in src


def test_registry_wrapper_exists():
    """registry 侧的包装函数存在且指向本模块。"""
    src = inspect.getsource(archive_section_registry)
    assert "_sampling_records_generator" in src
    assert "generate_sampling_records" in src


def test_reverse_selfcheck_duplicate_prefix_would_overwrite():
    """反向自检：证明同前缀确实会覆盖（这正是不能用 05 的原因）。"""
    before = len(archive_section_registry.list_all())
    try:
        archive_section_registry.register(
            gen.ARCHIVE_SECTION_PREFIX, "夺舍.txt", gen.generate_sampling_records, "probe"
        )
        after = archive_section_registry.list_all()
        assert len(after) == before, "同前缀注册应覆盖而非新增"
        mine = [s for s in after if s.order_prefix == gen.ARCHIVE_SECTION_PREFIX]
        assert mine[0].filename == "夺舍.txt"
    finally:
        # 还原
        archive_section_registry.register(
            gen.ARCHIVE_SECTION_PREFIX,
            gen.ARCHIVE_SECTION_FILENAME,
            gen.generate_sampling_records,
            "CAS 1314 抽样记录汇总（总体/样本量依据/抽样框版本/偏差/推断错报/结论）",
        )
    restored = [
        s
        for s in archive_section_registry.list_all()
        if s.order_prefix == gen.ARCHIVE_SECTION_PREFIX
    ]
    assert restored[0].filename == gen.ARCHIVE_SECTION_FILENAME
