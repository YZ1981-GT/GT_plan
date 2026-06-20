"""ReviewPromptMixin：AI 复核（提示词驱动）

review_workpaper_with_prompt、load_review_prompt、_base_review_prompt（property）、
_audit_cycle_aliases（类属性）、check_pending_confirmations。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select, func

from app.models.ai_models import (
    AIContent,
    AIContentType,
    AIConfirmationStatus,
    ConfidenceLevel,
)
from app.services.ai_service import AIService

logger = logging.getLogger(__name__)


class ReviewPromptMixin:
    """提示词驱动的 AI 复核相关方法"""

    async def review_workpaper_with_prompt(
        self,
        project_id: UUID,
        workpaper_id: UUID,
        ai_service: AIService,
    ) -> list[AIContent]:
        """
        提示词驱动的底稿AI智能复核

        1. 通过 workpaper_id 查找 wp_index 获取 audit_cycle
        2. 通过 audit_cycle 匹配 TSJ/ 下对应的审计复核提示词文件
        3. 将提示词注入 LLM system prompt
        4. LLM 按提示词框架逐项检查底稿
        5. 输出结构化复核发现
        6. 每个发现存入 ai_content 表

        Args:
            project_id: 项目ID
            workpaper_id: 底稿ID
            ai_service: AI服务实例

        Returns:
            list[AIContent]: 复核发现列表
        """
        from app.models.workpaper_models import WpIndex, WorkingPaper

        # 1. 获取底稿索引信息
        result = await self.db.execute(
            select(WpIndex).where(
                WpIndex.project_id == project_id,
                WpIndex.is_deleted == False,  # noqa: E712
            )
        )
        wp_indexes = result.scalars().all()

        # 查找匹配的底稿
        target_wp = None
        audit_cycle = None
        for wp in wp_indexes:
            # 获取底稿文件
            wp_file_result = await self.db.execute(
                select(WorkingPaper).where(
                    WorkingPaper.wp_index_id == wp.id,
                    WorkingPaper.is_deleted == False,  # noqa: E712
                )
            )
            wp_files = wp_file_result.scalars().all()
            for wf in wp_files:
                if str(wf.id) == str(workpaper_id):
                    target_wp = wf
                    audit_cycle = wp.audit_cycle
                    break
            if target_wp:
                break

        if not target_wp:
            logger.warning(f"Workpaper {workpaper_id} not found")
            return []

        # 2. 加载审计复核提示词（从 TSJ/ 目录按 audit_cycle 匹配）
        review_prompt = await self.load_review_prompt(audit_cycle or "general")

        # 3. 读取底稿文件内容，注入提示词占位符 {{#sys.files#}}
        workpaper_content = ""
        try:
            if target_wp.file_path:
                import os
                if os.path.exists(target_wp.file_path):
                    with open(target_wp.file_path, encoding="utf-8") as f:
                        workpaper_content = f.read()
                elif target_wp.content_text:
                    workpaper_content = target_wp.content_text
        except Exception as e:
            logger.warning(f"Failed to read workpaper file: {e}")

        # 4. 替换提示词中的 {{#sys.files#}} 占位符
        if workpaper_content:
            # 截断过长内容避免超出上下文窗口
            max_len = 8000
            if len(workpaper_content) > max_len:
                workpaper_content = workpaper_content[:max_len] + "\n... (内容已截断)"
            prompt_content = review_prompt.replace("{{#sys.files#}}", workpaper_content)
        else:
            prompt_content = review_prompt.replace(
                "{{#sys.files#}}",
                f"[底稿文件 ID: {workpaper_id}]（文件内容不可用）"
            )

        # 5. 构建复核请求
        prompt = f"""{prompt_content}

## 底稿信息
- 底稿ID: {workpaper_id}
- 项目ID: {project_id}
- 审计循环: {audit_cycle or 'general'}

请按提示词框架逐项检查底稿，输出结构化复核发现。
"""
        try:
            response = await ai_service.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
            )
            if hasattr(response, "__aiter__"):
                content_parts = []
                async for part in response:
                    content_parts.append(part)
                content_text = "".join(content_parts)
            else:
                content_text = str(response)
        except Exception as e:
            logger.warning(f"AI chat failed for workpaper review: {e}")
            content_text = "【底稿复核】AI复核暂时不可用，请手动复核。"

        # 4. 创建 AI 内容记录
        ai_content = AIContent(
            project_id=project_id,
            workpaper_id=workpaper_id,
            content_type=AIContentType.risk_alert,
            content_text=content_text,
            data_sources={
                "audit_cycle": audit_cycle,
                "review_type": "prompt_driven",
            },
            generation_model="unknown",
            generation_time=datetime.now(timezone.utc),
            confidence_level=ConfidenceLevel.medium,
            confirmation_status=AIConfirmationStatus.pending,
        )
        self.db.add(ai_content)
        await self.db.commit()
        await self.db.refresh(ai_content)

        return [ai_content]

    async def load_review_prompt(self, audit_cycle: str) -> str:
        """
        加载审计复核提示词

        按科目名称关键词匹配 TSJ/ 下的 .md 文件
        未匹配到时返回通用复核提示词模板

        Args:
            audit_cycle: 审计循环（如 "cash"、"receivable"）

        Returns:
            str: 提示词内容
        """
        import os
        import re
        import glob

        # 1. 查找 TSJ 目录（程序数据：backend/data/tsj_review_prompts/）
        # 环境变量 TSJ_PROMPT_DIR / TSJ_KNOWLEDGE_DIR 可覆盖
        tsj_base = os.environ.get("TSJ_PROMPT_DIR") or os.environ.get("TSJ_KNOWLEDGE_DIR")
        if not tsj_base:
            # __file__ = backend/app/services/wp_fill/_review_prompt.py
            # → 上溯到 backend/ 后定位 data/tsj_review_prompts
            # （比原 workpaper_fill_service.py 深一层 wp_fill/，故多上溯一级保持解析到 backend/）
            backend_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
            tsj_base = os.path.join(backend_root, "data", "tsj_review_prompts")
        tsj_base = os.path.abspath(tsj_base)

        if not os.path.isdir(tsj_base):
            logger.warning(f"TSJ prompt directory not found: {tsj_base}")
            return self._base_review_prompt

        # 2. 收集所有 .md 文件
        md_files = glob.glob(os.path.join(tsj_base, "*.md"))
        if not md_files:
            logger.warning(f"No .md files found in {tsj_base}")
            return self._base_review_prompt

        # 3. 构造关键词匹配模式（支持中文和英文别名）
        cycle_keywords = self._audit_cycle_aliases.get(audit_cycle.lower(), [audit_cycle])

        matched_file = None
        matched_score = 0

        for md_path in md_files:
            fname = os.path.basename(md_path)
            score = 0
            for kw in cycle_keywords:
                # 匹配文件名中包含关键词（忽略"审计复核提示词"通用部分）
                name_without_suffix = re.sub(r"审计复核提示词\.md$", "", fname)
                if kw.lower() in name_without_suffix.lower():
                    score += 2
                if kw.lower() in fname.lower():
                    score += 1
            if score > matched_score:
                matched_score = score
                matched_file = md_path

        # 4. 读取匹配到的文件内容
        if matched_file and matched_score > 0:
            try:
                with open(matched_file, encoding="utf-8") as f:
                    content = f.read().strip()
                logger.info(f"Loaded TSJ prompt: {os.path.basename(matched_file)} (score={matched_score})")
                return content
            except Exception as e:
                logger.warning(f"Failed to read TSJ file {matched_file}: {e}")

        # 5. 未匹配时按通用关键词模糊搜索
        generic_keywords = ["总体", "general", "审计方案"]
        for md_path in md_files:
            fname = os.path.basename(md_path)
            for kw in generic_keywords:
                if kw.lower() in fname.lower():
                    try:
                        with open(md_path, encoding="utf-8") as f:
                            content = f.read().strip()
                        logger.info(f"Fallback TSJ prompt (generic): {fname}")
                        return content
                    except Exception as e:
                        logger.debug("读取 TSJ prompt 文件失败 %s: %s", fname, e)

        logger.info("No matching TSJ prompt found, using base prompt")
        return self._base_review_prompt

    @property
    def _base_review_prompt(self) -> str:
        """通用复核提示词模板"""
        return """你是审计师，请对审计底稿进行智能复核。

## 复核框架

### 1. 审计认定检查
- 存在性：账面记录是否存在
- 完整性：所有交易是否记录
- 权利和义务：资产是否属于被审计单位
- 计价或分摊：金额是否正确
- 准确性、分类和截止：是否正确记录

### 2. 程序执行检查
- 审计程序是否完整执行
- 样本量是否充分
- 替代程序是否充分

### 3. 数据完整性检查
- 勾稽关系是否正确
- 小计合计是否准确
- 期初期末是否连续

### 4. 风险评估复核
- 异常事项是否标注
- 高风险领域是否充分关注
- 审计结论是否有充分证据支持

请按上述框架检查底稿，识别潜在问题并给出建议。
"""

    # 审计循环关键词别名映射（支持中英文通用术语）
    _audit_cycle_aliases: dict[str, list[str]] = {
        "cash": ["现金", "货币资金"],
        "bank": ["银行", "货币资金"],
        "receivable": ["应收", "应收账款", "其他应收"],
        "payable": ["应付", "应付账款", "其他应付"],
        "inventory": ["存货", "库存"],
        "fixed_asset": ["固定资产", "折旧"],
        "intangible": ["无形", "资产"],
        "revenue": ["收入", "销售", "营业"],
        "expense": ["费用", "成本", "支出"],
        "tax": ["税", "税费", "增值税"],
        "loan": ["借款", "贷款", "金融负债", "应付债券"],
        "equity": ["权益", "股本", "资本", "实收"],
        "investment": ["投资", "金融资产", "债权", "股权"],
        "goodwill": ["商誉", "减值"],
        "lease": ["租赁", "使用权"],
        "consolidation": ["合并", "抵消", "子公司"],
        "contingent": ["或有", "预计负债", "担保"],
        "related_party": ["关联", "关联方", "交易"],
        "subsequent": ["期后", "后续"],
        "going_concern": ["持续经营", "重大不确定"],
        "general": ["总体", "审计方案", "general"],
    }

    async def check_pending_confirmations(
        self,
        project_id: UUID,
        workpaper_id: UUID = None,
    ) -> int:
        """
        检查底稿中未确认的AI内容数量

        Args:
            project_id: 项目ID
            workpaper_id: 底稿ID（可选）

        Returns:
            int: 未确认数量
        """
        query = select(func.count(AIContent.id)).where(
            AIContent.project_id == project_id,
            AIContent.confirmation_status == AIConfirmationStatus.pending,
            AIContent.is_deleted == False,  # noqa: E712
        )
        if workpaper_id:
            query = query.where(AIContent.workpaper_id == workpaper_id)

        result = await self.db.execute(query)
        count = result.scalar()
        return count or 0
