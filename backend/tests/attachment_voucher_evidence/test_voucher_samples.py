"""「凭证」类声明的逐笔样本统计、链接证据类型参与判定、归档章节与完整性（需求 5、6，ADR-AVE-06）。

回归背景：D2 / D3 的「凭证」声明只看附件类型，从别的底稿引用来的附件（附件类型是源底稿选的）不算；抽凭样本与
证据没有关联，归档章节只列批次统计量，看不出哪几笔样本缺原件。
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest_asyncio

from app.models.workpaper_models import SampledVoucher, SamplingRecord
from app.models.wp_optimization_models import EvidenceLink
from tests.attachment_security_baseline._world import add_attachment, add_wp, sqlite_attachment_world
from tests.attachment_voucher_evidence._vk import vk


@pytest_asyncio.fixture
async def world(monkeypatch):
    async with sqlite_attachment_world(monkeypatch) as w:
        await w.db.run_sync(lambda s: [t.create(s.connection(), checkfirst=True)
                                       for t in (SampledVoucher.__table__, SamplingRecord.__table__)])
        yield w


async def _sample(world, wp, no, *, d="2025-01-07", vtype="记", company="default", batch=True, phase="final"):
    return await world._add(SampledVoucher(
        project_id=world.target.id, year=2025, voucher_no=no, voucher_date=date.fromisoformat(d) if d else None,
        voucher_type=vtype, company_code=company, phase=phase, working_paper_id=wp.id,
        batch_id=uuid.uuid4() if batch else None,
    ))


async def _evidence(world, wp, key, *, file_name, attachment_type="evidence", evidence_type="voucher"):
    who = await world.edit_member()
    att = await add_attachment(world, world.target, file_name=file_name, attachment_type=attachment_type)
    await world._add(EvidenceLink(wp_id=wp.id, attachment_id=att.id, evidence_type=evidence_type,
                                  voucher_key=key, created_by=who.user.id))
    return att


async def _scene(world):
    wp = await add_wp(world, world.target, wp_code="D2-4")
    await _sample(world, wp, "0003")                       # 两个来源登记同一张凭证 ⇒ 一笔
    await _sample(world, wp, "0003", batch=False)
    await _sample(world, wp, "0004")                       # 没有证据
    await _sample(world, wp, "0005", vtype=None, company=None)  # 旧登记：凭证字 / 主体按通配
    await _sample(world, wp, "0006", d=None)               # 旧登记缺日期
    att = await _evidence(world, wp, vk("0003"), file_name="记-0003 凭证.pdf")
    await _evidence(world, wp, vk("0005", vtype="转", company="主体甲"), file_name="转-0005.pdf")
    return wp, att


async def test_breakdown_counts_each_voucher_once(world):
    from app.services.voucher_evidence import voucher_sample_breakdown

    wp, _att = await _scene(world)
    got = await voucher_sample_breakdown(world.db, world.target.id, wp.id)
    assert (got["total"], got["with_evidence"], got["missing"], got["truncated"]) == (4, 2, 2, False)
    assert [m["label"] for m in got["missing_items"]] == ["2025-01-07 记-0004", "记-0006"]
    assert got["missing_items"][1]["reason"].startswith("旧登记缺凭证日期")
    assert got["missing_items"][0]["source"] == "engine"
    other = await add_wp(world, world.target, wp_code="D2-5")
    assert await voucher_sample_breakdown(world.db, world.target.id, other.id) is None


async def test_requirement_satisfied_by_link_type_and_carries_samples(world):
    from app.services.attachment_wp_view import evaluate_wp_evidence_requirements

    wp, _att = await _scene(world)   # 附件类型是「审计证据」，链接类型是「凭证」
    reqs = await evaluate_wp_evidence_requirements(world.db, wp.id)
    voucher = next(r for r in reqs if r["type"] == "voucher")
    assert voucher["satisfied"] is True
    assert (voucher["samples"]["total"], voucher["samples"]["missing"]) == (4, 2)
    assert "breakdown" not in voucher  # 函证的逐笔键不复用


async def test_archive_chapter_lists_sample_evidence(world):
    from app.services.archive_generators.sampling_records_generator import generate_sampling_records

    _wp, att = await _scene(world)
    text = (await generate_sampling_records(world.target.id, world.db)).decode("utf-8")
    assert "本项目未执行抽样程序" in text   # 没有抽凭批次记录，仍列样本证据
    assert "抽凭样本证据" in text and "登记样本 4 笔，已取得证据 2 笔，缺证据 2 笔" in text
    assert f"2025-01-07 记-0003：{str(att.id)[:8]} 记-0003 凭证.pdf" in text
    assert "缺证据样本：" in text and "2025-01-07 记-0004" in text and "旧登记缺凭证日期" in text


async def test_completeness_lists_missing_samples(world):
    from app.services.archive_completeness_evidence import check_evidence

    await _scene(world)
    gaps, unreplied = await check_evidence(world.db, world.target.id)
    assert unreplied == []
    assert [(g.wp_code, g.status) for g in gaps] == [
        ("D2-4", "2 笔抽凭样本未取得凭证证据（共 4 笔）：2025-01-07 记-0004、记-0006"),
    ]
