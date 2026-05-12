"""Metabase 数据可视化集成服务

功能：
- 获取嵌入 URL（JWT signed embedding）
- 预置仪表板 SQL 查询模板
- Redis 缓存仪表板查询结果

Validates: Requirements 13.1-13.6
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any
from uuid import UUID

import jwt


class MetabaseService:
    """Metabase 集成服务"""

    def __init__(
        self,
        metabase_url: str = "http://localhost:3000",
        embedding_secret: str = "audit-metabase-secret-key",
        redis: Any = None,
        cache_manager: Any = None,
    ):
        self.metabase_url = metabase_url.rstrip("/")
        self.embedding_secret = embedding_secret
        self.redis = redis
        self._cache = cache_manager  # CacheManager instance (preferred)

    # ------------------------------------------------------------------
    # 嵌入 URL 生成（JWT signed embedding）
    # ------------------------------------------------------------------

    def get_embed_url(
        self,
        resource_type: str = "dashboard",
        resource_id: int = 1,
        params: dict | None = None,
    ) -> str:
        """生成 Metabase 嵌入 URL

        Args:
            resource_type: "dashboard" 或 "question"
            resource_id: 仪表板或问题的 ID
            params: 传递给仪表板的参数（如 project_id, year）
        """
        payload = {
            "resource": {resource_type: resource_id},
            "params": params or {},
            "exp": int(time.time()) + 600,  # 10 分钟过期
        }
        token = jwt.encode(payload, self.embedding_secret, algorithm="HS256")
        return f"{self.metabase_url}/embed/{resource_type}/{token}#bordered=false&titled=true"

    # ------------------------------------------------------------------
    # 预置仪表板配置
    # ------------------------------------------------------------------

    def get_dashboard_configs(self) -> list[dict]:
        """获取预置仪表板配置列表"""
        return [
            {
                "id": "project_overview",
                "name": "项目进度看板",
                "description": "底稿完成率、复核完成率、距归档截止日天数",
                "metabase_dashboard_id": 1,
                "params": ["project_id"],
            },
            {
                "id": "account_overview",
                "name": "账套总览",
                "description": "总账余额、明细账余额、凭证数量",
                "metabase_dashboard_id": 2,
                "params": ["project_id", "year", "company_code"],
            },
            {
                "id": "account_penetration",
                "name": "科目穿透",
                "description": "选中科目→自动生成穿透查询视图",
                "metabase_dashboard_id": 3,
                "params": ["project_id", "year", "account_code"],
            },
            {
                "id": "aux_analysis",
                "name": "辅助账分析",
                "description": "按维度（客户/供应商/部门）的余额分析",
                "metabase_dashboard_id": 4,
                "params": ["project_id", "year", "account_code"],
            },
            {
                "id": "voucher_trend",
                "name": "凭证趋势",
                "description": "凭证数量和金额的时间序列图",
                "metabase_dashboard_id": 5,
                "params": ["project_id", "year"],
            },
        ]

    # ------------------------------------------------------------------
    # SQL 查询模板
    # ------------------------------------------------------------------

    def get_sql_templates(self) -> list[dict]:
        """获取预置 SQL 查询模板"""
        return [
            {
                "id": "total_ledger",
                "name": "总账查询",
                "sql": """
SELECT l.account_code, l.account_name,
       SUM(l.debit_amount) as debit_total,
       SUM(l.credit_amount) as credit_total
FROM tb_ledger l
WHERE l.project_id = {{project_id}} AND l.year = {{year}}
  AND EXISTS (
    SELECT 1 FROM ledger_datasets d
    WHERE d.id = l.dataset_id AND d.status = 'active'
  )
GROUP BY l.account_code, l.account_name
ORDER BY l.account_code;
""",
            },
            {
                "id": "detail_ledger",
                "name": "明细账查询",
                "sql": """
SELECT l.voucher_date, l.voucher_no, l.account_code, l.account_name,
       l.debit_amount, l.credit_amount, l.summary
FROM tb_ledger l
WHERE l.project_id = {{project_id}} AND l.year = {{year}}
  AND l.account_code = {{account_code}}
  AND EXISTS (
    SELECT 1 FROM ledger_datasets d
    WHERE d.id = l.dataset_id AND d.status = 'active'
  )
ORDER BY l.voucher_date, l.voucher_no;
""",
            },
            {
                "id": "voucher_query",
                "name": "凭证查询",
                "sql": """
SELECT l.voucher_no, l.voucher_date, l.account_code, l.account_name,
       l.debit_amount, l.credit_amount, l.summary
FROM tb_ledger l
WHERE l.project_id = {{project_id}} AND l.year = {{year}}
  AND l.voucher_no = {{voucher_no}}
  AND EXISTS (
    SELECT 1 FROM ledger_datasets d
    WHERE d.id = l.dataset_id AND d.status = 'active'
  )
ORDER BY l.account_code;
""",
            },
            {
                "id": "aux_query",
                "name": "辅助账查询",
                "sql": """
SELECT ab.aux_type, ab.aux_code, ab.aux_name,
       ab.opening_balance, ab.debit_amount, ab.credit_amount, ab.closing_balance
FROM tb_aux_balance ab
WHERE ab.project_id = {{project_id}} AND ab.year = {{year}}
  AND ab.account_code = {{account_code}}
  AND EXISTS (
    SELECT 1 FROM ledger_datasets d
    WHERE d.id = ab.dataset_id AND d.status = 'active'
  )
ORDER BY ab.aux_type, ab.aux_code;
""",
            },
        ]

    # ------------------------------------------------------------------
    # 缓存
    # ------------------------------------------------------------------

    async def get_cached_or_fetch(
        self, cache_key: str, fetch_fn, ttl: int = 300,
    ) -> Any:
        """从缓存获取或执行查询（优先 CacheManager，降级 raw Redis）"""
        if self._cache:
            try:
                cached = await self._cache.get("metabase", cache_key)
                if cached is not None:
                    return cached
            except Exception:
                pass
        elif self.redis:
            try:
                cached = await self.redis.get(cache_key)
                if cached:
                    return json.loads(cached)
            except Exception:
                pass

        result = await fetch_fn()

        if self._cache:
            try:
                await self._cache.set("metabase", cache_key, result, ttl=ttl)
            except Exception:
                pass
        elif self.redis:
            try:
                await self.redis.setex(cache_key, ttl, json.dumps(result, default=str))
            except Exception:
                pass

        return result

    async def invalidate_dashboard_cache(self, project_id: UUID) -> int:
        """清除项目相关的仪表板缓存"""
        if self._cache:
            return await self._cache.invalidate_namespace("metabase")

        if not self.redis:
            return 0
        pattern = f"metabase:dashboard:*:{project_id}:*"
        try:
            keys = []
            async for key in self.redis.scan_iter(match=pattern):
                keys.append(key)
            if keys:
                await self.redis.delete(*keys)
            return len(keys)
        except Exception:
            return 0

    # ------------------------------------------------------------------
    # 仪表板下钻（Task 14.5）
    # ------------------------------------------------------------------

    def get_drilldown_config(self) -> list[dict]:
        """获取下钻路径配置：定义从仪表板图表到明细数据的穿透路径"""
        return [
            {
                "id": "balance_to_ledger",
                "name": "总账余额 → 明细账",
                "source": "account_overview",
                "source_field": "account_code",
                "target_level": "ledger",
                "description": "点击科目余额，查看该科目的序时账明细",
            },
            {
                "id": "ledger_to_voucher",
                "name": "明细账 → 凭证",
                "source": "account_penetration",
                "source_field": "voucher_no",
                "target_level": "voucher",
                "description": "点击序时账分录，查看完整凭证",
            },
            {
                "id": "balance_to_aux",
                "name": "总账余额 → 辅助账",
                "source": "account_overview",
                "source_field": "account_code",
                "target_level": "aux_balance",
                "description": "点击科目余额，查看辅助核算维度余额",
            },
            {
                "id": "aux_to_detail",
                "name": "辅助账余额 → 辅助明细",
                "source": "aux_analysis",
                "source_field": "aux_code",
                "target_level": "aux_ledger",
                "description": "点击辅助核算余额，查看辅助明细账",
            },
            {
                "id": "trend_to_ledger",
                "name": "凭证趋势 → 明细账",
                "source": "voucher_trend",
                "source_field": "voucher_date",
                "target_level": "ledger",
                "description": "点击趋势图数据点，查看该日期的序时账",
            },
        ]

    def build_drilldown_url(
        self,
        project_id: str,
        year: int,
        target_level: str,
        params: dict,
    ) -> str:
        """构建下钻目标 URL（前端路由路径）

        Args:
            project_id: 项目ID
            year: 年度
            target_level: 目标层级 (ledger/voucher/aux_balance/aux_ledger)
            params: 下钻参数 (account_code, voucher_no, aux_code 等)
        """
        base = f"/projects/{project_id}/ledger"
        query_parts = [f"year={year}", f"level={target_level}"]
        for k, v in params.items():
            if v is not None:
                query_parts.append(f"{k}={v}")
        return f"{base}?{'&'.join(query_parts)}"
