"""阶段 1 PBT: P1 缓存一致 + P2 校验拦截

**Validates: Requirements 1.4, 2.2**

属性:
- P1 缓存一致: Redis L2 缓存结果 == DB 构建结果；invalidate 后 L1+L2 同步失效
- P2 校验拦截: 含悬空引用的公式 validate_formula_refs 返非空 issues
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from app.services.address_registry import (
    AddressEntry,
    AddressRegistryService,
    _CacheSlot,
)

# ═══════════════════════════════════════════
# Strategies
# ═══════════════════════════════════════════

# 合法域名
domains = st.sampled_from(["tb", "report", "note", "wp"])

# 项目 ID（简短随机字符串模拟 UUID）
project_ids = st.from_regex(r"[a-f0-9]{8}", fullmatch=True)

# 年份
years = st.integers(min_value=2020, max_value=2030)

# 模板类型
template_types = st.sampled_from(["soe", "listed"])

# 科目编码
account_codes = st.from_regex(r"[0-9]{4}", fullmatch=True)

# 列名
cell_names = st.sampled_from(["审定数", "未审数", "期末", "期初", "本期", "上期"])


@st.composite
def address_entries(draw, domain=None):
    """生成随机 AddressEntry"""
    d = domain or draw(domains)
    code = draw(account_codes)
    cell = draw(cell_names)
    uri = f"{d}://{code}#{cell}"
    return AddressEntry(
        uri=uri,
        domain=d,
        source=code,
        path="",
        cell=cell,
        label=f"测试 > {code} > {cell}",
        formula_ref=f"TB('{code}','{cell}')" if d == "tb" else f"REPORT('{code}','{cell}')",
    )


@st.composite
def entry_lists(draw, min_size=1, max_size=5):
    """生成 AddressEntry 列表"""
    return draw(st.lists(address_entries(), min_size=min_size, max_size=max_size))


# 生成含悬空引用的公式（引用不在 registry 中的科目）
@st.composite
def dangling_formulas(draw):
    """生成含悬空引用的公式字符串（科目 9xxx 保证不在 registry）"""
    code = draw(st.from_regex(r"9[0-9]{3}", fullmatch=True))
    cell = draw(cell_names)
    return f"TB('{code}','{cell}')"


# ═══════════════════════════════════════════
# P1: 缓存一致属性
# ═══════════════════════════════════════════


class TestP1CacheConsistency:
    """P1 缓存一致: Redis L2 == DB 构建 + invalidate 同步

    **Validates: Requirements 1.4**
    """

    @settings(max_examples=5, suppress_health_check=[HealthCheck.too_slow])
    @given(
        project_id=project_ids,
        year=years,
        template_type=template_types,
        domain=domains,
        entries=entry_lists(),
    )
    @pytest.mark.asyncio
    async def test_redis_l2_equals_db_build_after_write_through(
        self, project_id, year, template_type, domain, entries
    ):
        """∀ (project_id, year, template_type, domain) →
        redis_get(key) after set == original entries

        验证: DB 构建后回写 Redis，再从 Redis 读取的结果与原始 entries 一致。
        """
        service = AddressRegistryService()

        # 模拟 Redis 存储
        redis_store: dict[str, str] = {}

        fake_redis = AsyncMock()

        async def mock_get(key):
            return redis_store.get(key)

        async def mock_set(key, value, **kwargs):
            redis_store[key] = value

        fake_redis.get = mock_get
        fake_redis.set = mock_set

        # 第一次调用: L1 miss → L2 miss → DB 构建 → 回写 L1+L2
        build_fn_map = {
            "tb": "app.services.address_registry.build_trial_balance_entries",
            "report": "app.services.address_registry.build_report_entries",
            "note": "app.services.address_registry.build_note_entries",
            "wp": "app.services.address_registry.build_workpaper_entries",
        }
        build_fn = build_fn_map[domain]

        with patch.object(service, "_get_redis", return_value=fake_redis), \
             patch(build_fn, new=AsyncMock(return_value=entries)):
            result_from_db = await service.get_domain(
                MagicMock(), project_id, year, template_type, domain
            )

        # 验证 DB 构建结果正确返回
        assert len(result_from_db) == len(entries)
        for orig, got in zip(entries, result_from_db):
            assert orig.uri == got.uri
            assert orig.domain == got.domain

        # 验证 Redis 中已有缓存
        slot_key = service._slot_key(project_id, year, template_type, domain)
        redis_key = service._redis_key(slot_key)
        assert redis_key in redis_store

        # 清空 L1，模拟另一个 worker 从 Redis 读取
        service._slots.clear()

        with patch.object(service, "_get_redis", return_value=fake_redis):
            result_from_redis = await service.get_domain(
                None, project_id, year, template_type, domain
            )

        # 核心断言: Redis L2 读取结果 == 原始 DB 构建结果
        assert len(result_from_redis) == len(entries)
        for orig, got in zip(entries, result_from_redis):
            assert orig.uri == got.uri
            assert orig.domain == got.domain
            assert orig.label == got.label
            assert orig.formula_ref == got.formula_ref

    @settings(max_examples=5)
    @given(
        project_id=project_ids,
        year=years,
        template_type=template_types,
        domain=domains,
        entries=entry_lists(),
    )
    @pytest.mark.asyncio
    async def test_invalidate_clears_l1_and_l2(
        self, project_id, year, template_type, domain, entries
    ):
        """∀ key → after invalidate(key), redis_get(key) == None AND L1[key] not present

        验证: invalidate_async 后 L1 内存和 L2 Redis 同步失效。
        """
        service = AddressRegistryService()

        # 模拟 Redis 存储
        redis_store: dict[str, str] = {}
        deleted_keys: list[str] = []

        fake_redis = AsyncMock()

        async def mock_get(key):
            return redis_store.get(key)

        async def mock_set(key, value, **kwargs):
            redis_store[key] = value

        async def mock_delete(*keys):
            for k in keys:
                redis_store.pop(k, None)
                deleted_keys.append(k)

        fake_redis.get = mock_get
        fake_redis.set = mock_set
        fake_redis.delete = mock_delete

        slot_key = service._slot_key(project_id, year, template_type, domain)

        # 预填 L1 + L2
        service._slots[slot_key] = _CacheSlot(
            entries=entries, built_at=time.time(), domain=domain
        )
        redis_store[service._redis_key(slot_key)] = json.dumps(
            [asdict(e) for e in entries], ensure_ascii=False
        )

        # 执行 invalidate_async
        with patch.object(service, "_get_redis", return_value=fake_redis):
            await service.invalidate_async(project_id, year=year, domain=domain)

        # 核心断言: L1 已清空
        assert slot_key not in service._slots

        # 核心断言: L2 Redis key 已删除
        redis_key = service._redis_key(slot_key)
        assert redis_key not in redis_store
        assert redis_key in deleted_keys


# ═══════════════════════════════════════════
# P2: 校验拦截属性
# ═══════════════════════════════════════════


class TestP2ValidationInterception:
    """P2 校验拦截: 含悬空引用的公式 validate_formula_refs 返非空

    **Validates: Requirements 2.2**
    """

    @settings(max_examples=5)
    @given(
        project_id=project_ids,
        year=years,
        template_type=template_types,
        formula=dangling_formulas(),
    )
    @pytest.mark.asyncio
    async def test_dangling_refs_detected(
        self, project_id, year, template_type, formula
    ):
        """∀ formula with refs not in address_registry →
        validate_formula_refs returns non-empty list

        验证: 公式引用的地址不在注册表中时，校验返回非空 issues。
        """
        service = AddressRegistryService()

        # 注册表中只有 1001~1005 的科目（9xxx 保证不在）
        registry_entries = [
            AddressEntry(
                uri=f"tb://{code}#{cell}",
                domain="tb",
                source=code,
                path="",
                cell=cell,
                label=f"试算表 > {code} > {cell}",
                formula_ref=f"TB('{code}','{cell}')",
            )
            for code in ["1001", "1002", "1003", "1004", "1005"]
            for cell in ["审定数", "未审数", "期末", "期初", "本期", "上期"]
        ]

        # Mock: get_domain 返回已知注册表（只有 1001~1005）
        async def mock_get_domain(db, pid, yr, tpl, dom):
            if dom == "tb":
                return registry_entries
            return []

        with patch.object(service, "_get_domain", side_effect=mock_get_domain):
            issues = await service.validate_formula_refs(
                MagicMock(), project_id, year, formula, template_type
            )

        # 核心断言: 悬空引用被检出
        assert len(issues) > 0
        assert all(issue["status"] == "not_found" for issue in issues)
        # 每个 issue 包含 ref/uri/message
        for issue in issues:
            assert "ref" in issue
            assert "uri" in issue
            assert "message" in issue
