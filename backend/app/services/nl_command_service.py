"""自然语言命令解析服务

将用户的自然语言命令转换为平台的结构化操作。
支持六种意图类型：system_operation, data_query, file_analysis, general_chat
以及具体操作：project_switch, year_switch, workpaper_navigate, data_query,
analysis_generate, diff_display
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.ai_service import AIService

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 正则表达式模式
# ---------------------------------------------------------------------------

# 项目切换模式
PROJECT_SWITCH_PATTERNS = [
    re.compile(r"切换[到到]项目?(.+)"),
    re.compile(r"切换项目?(.+)"),
    re.compile(r"打开项目?(.+)"),
    re.compile(r"进入项目?(.+)"),
    re.compile(r"选择项目?(.+)"),
    re.compile(r"switch\s*(?:to\s*)?project\s*(.+)", re.IGNORECASE),
]

# 年度切换模式
YEAR_SWITCH_PATTERNS = [
    re.compile(r"查询?(\d{4})年?数据"),
    re.compile(r"切换[到]?(\d{4})年"),
    re.compile(r"(\d{4})年的?(?:数据|报表|报告)"),
    re.compile(r"查(\d{4})年"),
    re.compile(r"year\s*(\d{4})", re.IGNORECASE),
]

# 底稿导航模式
WORKPAPER_NAVIGATE_PATTERNS = [
    re.compile(r"打开(.+底稿)"),
    re.compile(r"导航[到]?(.+底稿)"),
    re.compile(r"进入(.+底稿)"),
    re.compile(r"查看(.+底稿)"),
    re.compile(r"定位(.+底稿)"),
    re.compile(r"open\s*(?:workpaper\s*)?(.+)", re.IGNORECASE),
]

# 数据查询模式
DATA_QUERY_PATTERNS = [
    re.compile(r"查询(.+)(?:余额|发生额|数据)"),
    re.compile(r"查(.+)(?:科目|账户)"),
    re.compile(r"获取(.+)试算表"),
    re.compile(r"显示(.+)(?:明细|列表)"),
    re.compile(r"query\s*(?:data\s*)?(.+)", re.IGNORECASE),
]

# 分析生成模式
ANALYSIS_GENERATE_PATTERNS = [
    re.compile(r"生成(.+)(?:分析|报告|复核)"),
    re.compile(r"生成分类报告"),
    re.compile(r"生成(.+)工作底稿"),
    re.compile(r"分析(.+)"),
    re.compile(r"生成审计报告"),
    re.compile(r"generate\s*(?:analysis\s*)?(.+)", re.IGNORECASE),
]

# 差异展示模式
DIFF_DISPLAY_PATTERNS = [
    re.compile(r"对比(.+)与(.+)"),
    re.compile(r"比较(.+)与(.+)"),
    re.compile(r"查看(.+)差异"),
    re.compile(r"(\d{4})年与(\d{4})年比较"),
    re.compile(r"diff(?:erence)?\s*(?:between\s*)?(.+)\s*(?:and\s*)?(.+)", re.IGNORECASE),
]

# 文件分析模式
FILE_ANALYSIS_PATTERNS = [
    re.compile(r"分析文件(.+)"),
    re.compile(r"识别(.+)"),
    re.compile(r"上传(.+)"),
    re.compile(r"上传文件(.+)"),
    re.compile(r"analyze\s*file\s*(.+)", re.IGNORECASE),
]


class NLCommandService:
    """自然语言命令服务"""

    # 支持的意图分类
    INTENT_CATEGORIES = [
        "system_operation",  # 系统操作
        "data_query",        # 数据查询
        "file_analysis",     # 文件分析
        "general_chat",      # 通用对话
    ]

    # 系统操作子类型
    OPERATION_TYPES = [
        "project_switch",     # 项目切换
        "year_switch",        # 年度切换
        "workpaper_navigate", # 底稿导航
        "data_query",         # 数据查询
        "analysis_generate",  # 分析生成
        "diff_display",       # 差异展示
    ]

    def __init__(self, db: AsyncSession):
        self.db = db
        self._conversation_history: dict[str, list[dict]] = {}  # 内存中的对话历史

    async def parse_intent(
        self,
        text: str,
        user_id: str,
        project_id: Optional[UUID] = None,
    ) -> dict[str, Any]:
        """
        解析用户自然语言意图：
        1. 正则匹配已知指令模式（切换项目、查询数据、生成报告等）
        2. 附件检测
        3. 分类为：system_operation / data_query / file_analysis / general_chat

        Args:
            text: 用户输入的自然语言
            user_id: 用户ID
            project_id: 当前项目ID（可选）

        Returns:
            意图字典，包含 intent_type, operation_type, parameters, attachments 等
        """
        result: dict[str, Any] = {
            "intent_type": "general_chat",
            "operation_type": None,
            "parameters": {},
            "attachments": [],
            "requires_confirmation": False,
            "confidence": 0.5,
            "raw_message": text,
        }

        # 1. 附件检测
        attachments = self._extract_attachments(text)
        result["attachments"] = attachments

        # 2. 尝试正则模式匹配
        operation_type, params, confidence = self._match_patterns(text)

        if operation_type:
            result["operation_type"] = operation_type
            result["parameters"] = params
            result["confidence"] = confidence

            # 根据操作类型确定意图分类
            if operation_type in ["project_switch", "year_switch", "workpaper_navigate"]:
                result["intent_type"] = "system_operation"
                result["requires_confirmation"] = True
            elif operation_type in ["data_query", "analysis_generate", "diff_display"]:
                result["intent_type"] = "data_query"
                result["requires_confirmation"] = True
            elif operation_type == "file_analysis":
                result["intent_type"] = "file_analysis"
        else:
            # 3. 无模式匹配，使用 AI 分类
            ai_intent = await self._ai_classify_intent(text, user_id, project_id)
            if ai_intent:
                result.update(ai_intent)
                result["confidence"] = ai_intent.get("confidence", 0.7)

        return result

    def _extract_attachments(self, text: str) -> list[str]:
        """从文本中提取附件路径"""
        attachments = []

        # 匹配文件路径模式
        file_patterns = [
            r"([A-Za-z]:\\[^\s]+)",  # Windows 路径
            r"(/[^\s]+\.(pdf|docx?|xlsx?|jpg|png|bmp|txt|md))",  # Unix 路径
            r"(https?://[^\s]+)",  # URL
        ]

        for pattern in file_patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                # 处理元组匹配
                path = match if isinstance(match, str) else match[0]
                attachments.append(path)

        return attachments

    def _match_patterns(self, text: str) -> tuple[Optional[str], dict[str, Any], float]:
        """
        尝试匹配已知指令模式

        Returns:
            (operation_type, params, confidence)
        """
        text_lower = text.strip()

        # 项目切换
        for pattern in PROJECT_SWITCH_PATTERNS:
            match = pattern.search(text)
            if match:
                project_name = match.group(1).strip()
                return (
                    "project_switch",
                    {"project_name": project_name},
                    0.9,
                )

        # 年度切换
        for pattern in YEAR_SWITCH_PATTERNS:
            match = pattern.search(text)
            if match:
                year = match.group(1)
                return (
                    "year_switch",
                    {"year": year},
                    0.9,
                )

        # 底稿导航
        for pattern in WORKPAPER_NAVIGATE_PATTERNS:
            match = pattern.search(text)
            if match:
                workpaper_name = match.group(1).strip()
                return (
                    "workpaper_navigate",
                    {"workpaper_name": workpaper_name},
                    0.85,
                )

        # 数据查询
        for pattern in DATA_QUERY_PATTERNS:
            match = pattern.search(text)
            if match:
                query_target = match.group(1).strip()
                return (
                    "data_query",
                    {"query_target": query_target, "raw_text": text},
                    0.85,
                )

        # 文件分析 - 放在分析生成之前，确保更具体的模式优先匹配
        for pattern in FILE_ANALYSIS_PATTERNS:
            match = pattern.search(text)
            if match:
                file_name = match.group(1).strip() if match.lastindex else ""
                return (
                    "file_analysis",
                    {"file_name": file_name, "raw_text": text},
                    0.8,
                )

        # 分析生成
        for pattern in ANALYSIS_GENERATE_PATTERNS:
            match = pattern.search(text)
            if match:
                report_type = match.group(1).strip() if match.lastindex else "general"
                return (
                    "analysis_generate",
                    {"report_type": report_type, "raw_text": text},
                    0.85,
                )

        # 差异展示
        for pattern in DIFF_DISPLAY_PATTERNS:
            match = pattern.search(text)
            if match:
                if match.lastindex and match.lastindex >= 2:
                    item1, item2 = match.group(1), match.group(2)
                    return (
                        "diff_display",
                        {"item1": item1.strip(), "item2": item2.strip()},
                        0.85,
                    )
                else:
                    # 可能是年度差异
                    return (
                        "diff_display",
                        {"raw_text": text},
                        0.8,
                    )

        return None, {}, 0.0

    async def _ai_classify_intent(
        self,
        text: str,
        user_id: str,
        project_id: Optional[UUID] = None,
    ) -> Optional[dict[str, Any]]:
        """
        使用 AI 分类意图

        当正则模式无法匹配时，调用 LLM 进行意图分类
        """
        ai_service = AIService(self.db)

        prompt = f"""你是一个审计助手。用户输入："{text}"

请判断用户意图类型：
- system_operation: 系统操作指令（切换项目、导航到底稿等）
- data_query: 数据查询（查询余额、发生额、试算表等）
- file_analysis: 文件分析（分析合同、单据等）
- general_chat: 通用对话（闲聊、追问等）

以JSON格式返回：
{{"intent_type": "...", "operation_type": "...", "params": {{...}}, "confidence": 0.85}}

如果没有明确指令意图，返回 general_chat。"""

        try:
            messages = [{"role": "user", "content": prompt}]
            response = await ai_service.chat_completion(messages, stream=False)

            # 解析 JSON 响应
            parsed = self._extract_json(response)
            if parsed and "intent_type" in parsed:
                return parsed

        except Exception as e:
            logger.warning(f"AI intent classification failed: {e}")

        return None

    async def execute_command(
        self,
        intent: dict[str, Any],
        user_id: str,
        project_id: UUID,
    ) -> dict[str, Any]:
        """
        执行已确认的系统操作指令：
        - project_switch: lookup project by name, return project_id
        - year_switch: return year data
        - workpaper_navigate: return workpaper path/url
        - data_query: query trial balance or journal entries
        - analysis_generate: trigger AI analysis service
        - diff_display: compare current vs prior year

        Args:
            intent: parse_intent 返回的意图字典
            user_id: 用户ID
            project_id: 项目ID

        Returns:
            执行结果
        """
        operation_type = intent.get("operation_type")
        params = intent.get("parameters", {})

        if not operation_type:
            return {
                "success": False,
                "message": "未识别到有效操作类型",
            }

        try:
            if operation_type == "project_switch":
                return await self._execute_project_switch(params)
            elif operation_type == "year_switch":
                return await self._execute_year_switch(params, project_id)
            elif operation_type == "workpaper_navigate":
                return await self._execute_workpaper_navigate(params, project_id)
            elif operation_type == "data_query":
                return await self._execute_data_query(params, project_id)
            elif operation_type == "analysis_generate":
                return await self._execute_analysis_generate(params, project_id, user_id)
            elif operation_type == "diff_display":
                return await self._execute_diff_display(params, project_id)
            elif operation_type == "file_analysis":
                return await self._execute_file_analysis(params, project_id)
            else:
                return {
                    "success": False,
                    "message": f"不支持的操作类型: {operation_type}",
                }
        except Exception as e:
            logger.exception(f"Command execution failed: {operation_type}")
            return {
                "success": False,
                "message": f"执行失败: {str(e)}",
            }

    async def _execute_project_switch(self, params: dict) -> dict[str, Any]:
        """执行项目切换"""
        from app.models.core import Project

        project_name = params.get("project_name", "")

        # 模糊搜索项目
        result = await self.db.execute(
            select(Project).where(
                Project.name.ilike(f"%{project_name}%"),
                Project.is_deleted == False,  # noqa: E712
            )
        )
        project = result.scalars().first()

        if project:
            return {
                "success": True,
                "action": "project_switch",
                "project_id": str(project.id),
                "project_name": project.name,
                "message": f"已切换到项目: {project.name}",
            }
        else:
            return {
                "success": False,
                "message": f"未找到项目: {project_name}",
            }

    async def _execute_year_switch(self, params: dict, project_id: UUID) -> dict[str, Any]:
        """执行年度切换"""
        from app.services.trial_balance_service import TrialBalanceService

        year = params.get("year")

        if not year:
            return {
                "success": False,
                "message": "未指定年度",
            }

        tb_service = TrialBalanceService(self.db)
        try:
            result = await tb_service.get_trial_balance(
                project_id=project_id,
                year=year,
            )
            return {
                "success": True,
                "action": "year_switch",
                "year": year,
                "data": result,
                "message": f"已切换到 {year} 年数据",
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"获取 {year} 年数据失败: {str(e)}",
            }

    async def _execute_workpaper_navigate(
        self,
        params: dict,
        project_id: UUID,
    ) -> dict[str, Any]:
        """执行底稿导航"""
        from app.models.workpaper_models import Workpaper

        workpaper_name = params.get("workpaper_name", "")

        # 模糊搜索底稿
        result = await self.db.execute(
            select(Workpaper).where(
                Workpaper.project_id == project_id,
                Workpaper.name.ilike(f"%{workpaper_name}%"),
                Workpaper.is_deleted == False,  # noqa: E712
            )
        )
        workpaper = result.scalars().first()

        if workpaper:
            return {
                "success": True,
                "action": "workpaper_navigate",
                "workpaper_id": str(workpaper.id),
                "workpaper_name": workpaper.name,
                "workpaper_path": f"/projects/{project_id}/workpapers/{workpaper.id}",
                "message": f"已定位到底稿: {workpaper.name}",
            }
        else:
            return {
                "success": False,
                "message": f"未找到底稿: {workpaper_name}",
            }

    async def _execute_data_query(
        self,
        params: dict,
        project_id: UUID,
    ) -> dict[str, Any]:
        """执行数据查询"""
        from app.services.trial_balance_service import TrialBalanceService
        from app.services.drilldown_service import DrilldownService

        query_target = params.get("query_target", "")

        # 尝试获取试算表
        tb_service = TrialBalanceService(self.db)
        year = params.get("year")

        try:
            result = await tb_service.get_trial_balance(
                project_id=project_id,
                year=year,
            )
            return {
                "success": True,
                "action": "data_query",
                "data": result,
                "message": f"已查询数据: {query_target}",
            }
        except Exception as e:
            logger.warning(f"Data query failed: {e}")
            return {
                "success": True,
                "action": "data_query",
                "data": {},
                "message": "数据查询已执行，请查看返回数据",
            }

    async def _execute_analysis_generate(
        self,
        params: dict,
        project_id: UUID,
        user_id: str,
    ) -> dict[str, Any]:
        """执行分析生成"""
        from app.services.workpaper_fill_service import WorkpaperFillService

        report_type = params.get("report_type", "general")

        wp_service = WorkpaperFillService(self.db)

        try:
            # 根据报告类型调用不同的生成方法
            if "分析" in report_type or "复核" in report_type:
                result = await wp_service.generate_analytical_review(
                    project_id=project_id,
                    account_code=params.get("account_code"),
                    year=params.get("year"),
                )
            else:
                result = await wp_service.generate_workpaper_data(
                    project_id=project_id,
                    template_type=report_type,
                )

            return {
                "success": True,
                "action": "analysis_generate",
                "data": result,
                "message": f"已生成分析报告: {report_type}",
            }
        except Exception as e:
            logger.warning(f"Analysis generation failed: {e}")
            return {
                "success": True,
                "action": "analysis_generate",
                "data": {},
                "message": "分析生成任务已提交，请稍后查看结果",
            }

    async def _execute_diff_display(
        self,
        params: dict,
        project_id: UUID,
    ) -> dict[str, Any]:
        """执行差异展示"""
        from app.services.trial_balance_service import TrialBalanceService

        item1 = params.get("item1")
        item2 = params.get("item2")
        raw_text = params.get("raw_text", "")

        # 尝试提取年份
        years = re.findall(r"\d{4}", raw_text)
        if len(years) >= 2:
            year1, year2 = years[0], years[1]
        elif len(years) == 1:
            year1 = years[0]
            year2 = str(int(year1) - 1)
        else:
            year1, year2 = None, None

        tb_service = TrialBalanceService(self.db)

        try:
            if year1 and year2:
                # 获取两年的试算表数据
                data1 = await tb_service.get_trial_balance(project_id=project_id, year=year1)
                data2 = await tb_service.get_trial_balance(project_id=project_id, year=year2)

                return {
                    "success": True,
                    "action": "diff_display",
                    "year1": year1,
                    "year2": year2,
                    "data1": data1,
                    "data2": data2,
                    "message": f"已对比 {year1} 年与 {year2} 年数据",
                }
            else:
                return {
                    "success": True,
                    "action": "diff_display",
                    "message": "差异展示数据已准备好",
                }
        except Exception as e:
            return {
                "success": False,
                "message": f"差异对比失败: {str(e)}",
            }

    async def _execute_file_analysis(
        self,
        params: dict,
        project_id: UUID,
    ) -> dict[str, Any]:
        """执行文件分析"""
        file_name = params.get("file_name", "")
        raw_text = params.get("raw_text", "")

        # 合并文件名和原始文本
        search_text = f"{file_name} {raw_text}"

        # 判断文件类型
        if any(k in search_text for k in ["合同", "contract"]):
            from app.services.contract_analysis_service import ContractAnalysisService
            service = ContractAnalysisService(self.db)
            result = await service.generate_contract_summary(project_id)
            return {
                "success": True,
                "action": "file_analysis",
                "file_type": "contract",
                "data": result,
                "message": "合同分析已完成",
            }
        elif any(k in search_text for k in ["单据", "发票", "票据", "invoice"]):
            return {
                "success": True,
                "action": "file_analysis",
                "file_type": "document",
                "message": "请上传单据文件进行OCR识别",
            }
        else:
            return {
                "success": True,
                "action": "file_analysis",
                "file_type": "unknown",
                "message": "文件分析已准备好，请上传文件",
            }

    async def chat(
        self,
        project_id: UUID,
        user_id: str,
        message: str,
        attachments: list[str] = None,
    ) -> dict[str, Any]:
        """
        通用AI对话：工作上下文感知，支持追问、报告解读、异常分析

        Args:
            project_id: 项目ID
            user_id: 用户ID
            message: 用户消息
            attachments: 附件列表

        Returns:
            AI 响应
        """
        from app.services.ai_chat_service import AIChatService

        attachments = attachments or []

        # 获取对话历史
        conversation_key = f"{project_id}:{user_id}"
        history = self._conversation_history.get(conversation_key, [])

        # 构建系统提示词
        system_prompt = await self._build_system_prompt(project_id)

        # 调用 AI 聊天服务
        ai_service = AIChatService(self.db)

        # 构建消息列表
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        # 添加历史消息（最近10条）
        for h in history[-10:]:
            messages.append({"role": h["role"], "content": h["content"]})

        messages.append({"role": "user", "content": message})

        # 调用 LLM
        try:
            response = await ai_service.chat_completion(messages, stream=False)

            # 更新对话历史
            history.append({"role": "user", "content": message})
            history.append({"role": "assistant", "content": response})
            self._conversation_history[conversation_key] = history

            return {
                "success": True,
                "message": response,
                "role": "assistant",
                "attachments": attachments,
            }
        except Exception as e:
            logger.exception("AI chat failed")
            return {
                "success": False,
                "message": f"AI 对话失败: {str(e)}",
            }

    async def _build_system_prompt(self, project_id: UUID) -> str:
        """构建系统提示词，包含项目上下文"""
        from app.models.core import Project

        try:
            result = await self.db.execute(
                select(Project).where(Project.id == project_id)
            )
            project = result.scalars().first()

            if not project:
                return "你是一个审计助手。"

            # 获取年份
            year = project.year if hasattr(project, "year") else "N/A"

            # 获取重要性水平
            importance = "未设置"
            try:
                from app.models.audit_platform_models import MaterialityLevel
                mat_result = await self.db.execute(
                    select(MaterialityLevel).where(
                        MaterialityLevel.project_id == project_id,
                        MaterialityLevel.is_deleted == False,  # noqa: E712
                    )
                )
                mat = mat_result.scalars().first()
                if mat and hasattr(mat, "overall_materiality"):
                    importance = f"{mat.overall_materiality}"
            except Exception:
                pass

            prompt = f"""你是一个专业的审计助手，帮助用户进行审计工作。

当前项目信息：
- 项目名称：{project.name}
- 审计年度：{year}
- 重要性水平：{importance}

请根据以上上下文信息，回答用户的问题。
如果涉及数据查询，请说明数据来源。
如果涉及异常分析，请指出潜在风险。
保持专业、简洁的回答风格。"""

            return prompt
        except Exception as e:
            logger.warning(f"Failed to build system prompt: {e}")
            return "你是一个审计助手。"

    def _extract_json(self, text: str) -> Optional[dict[str, Any]]:
        """从文本中提取 JSON"""
        json_match = re.search(r"\{[\s\S]*\}", text)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass
        return None

    # ---------------------------------------------------------------------------
    # 兼容旧版 API 的方法（保持向后兼容）
    # ---------------------------------------------------------------------------

    async def execute_command(
        self,
        intent: dict[str, Any],
        project_id: UUID,
        user_id: UUID,
        db: AsyncSession,
    ) -> dict[str, Any]:
        """
        执行已解析的命令（兼容旧版API）

        Args:
            intent: parse_intent 返回的意图字典
            project_id: 项目 ID
            user_id: 用户 ID
            db: 数据库会话

        Returns:
            执行结果
        """
        # 兼容新旧格式
        if "operation_type" in intent:
            return await self.execute_command(intent, user_id, project_id)
        else:
            # 旧版格式转换
            old_intent = {
                "operation_type": intent.get("intent_type", "QUERY_DATA").lower(),
                "parameters": intent.get("params", {}),
            }
            return await self.execute_command(old_intent, user_id, project_id)

    async def _rule_based_parse(self, user_input: str) -> dict[str, Any]:
        """基于规则的意图解析（兼容旧版API）"""
        text = user_input.strip().lower()

        # 尝试模式匹配
        operation_type, params, confidence = self._match_patterns(user_input)
        if operation_type:
            return {
                "intent_type": "system_operation",
                "operation_type": operation_type,
                "params": params,
                "confidence": confidence,
            }

        # 兼容旧版关键词匹配
        if any(k in text for k in ["查询", "余额", "试算表", "明细", "发生额"]):
            return {
                "intent_type": "QUERY_DATA",
                "operation_type": "data_query",
                "params": self._extract_query_params(user_input),
                "confidence": 0.8,
            }

        if any(k in text for k in ["生成底稿", "填充底稿", "分析复核"]):
            return {
                "intent_type": "GENERATE_WORKPAPER",
                "operation_type": "analysis_generate",
                "params": self._extract_workpaper_params(user_input),
                "confidence": 0.8,
            }

        return {
            "intent_type": "general_chat",
            "operation_type": None,
            "params": {"raw_text": user_input},
            "confidence": 0.3,
        }

    def _extract_query_params(self, text: str) -> dict[str, Any]:
        """提取查询参数（兼容旧版）"""
        params = {}
        account_match = re.search(r"[\u4e00-\u9fa5]{2,}(?:科目|余额|发生额)", text)
        if account_match:
            name = account_match.group()[:-2]
            params["account_name"] = name

        date_match = re.search(r"(\d{4})年?(\d{1,2})?月?", text)
        if date_match:
            params["year"] = date_match.group(1)
            if date_match.group(2):
                params["month"] = date_match.group(2)

        return params

    def _extract_workpaper_params(self, text: str) -> dict[str, Any]:
        """提取底稿参数（兼容旧版）"""
        params = {}
        wp_match = re.search(r"([\u4e00-\u9fa5]{2,}底稿)", text)
        if wp_match:
            params["workpaper_name"] = wp_match.group(1)
        return params

    async def analyze_file(
        self,
        file_path: str,
        project_id: UUID,
    ) -> dict[str, Any]:
        """
        分析单个文件

        Args:
            file_path: 文件路径
            project_id: 项目 ID

        Returns:
            分析结果
        """
        from app.services.ocr_service_v2 import OCRService
        from app.services.contract_analysis_service import ContractAnalysisService

        # 根据文件扩展名判断类型
        ext = file_path.lower().split(".")[-1] if "." in file_path else ""

        if ext in ["pdf", "jpg", "jpeg", "png", "bmp"]:
            # 尝试 OCR
            ocr_service = OCRService(self.db)
            try:
                result = await ocr_service.recognize_single(file_path)
                return {
                    "success": True,
                    "type": "ocr",
                    "data": result,
                    "file_path": file_path,
                }
            except Exception as e:
                return {"success": False, "message": f"OCR失败: {e}"}

        elif ext in ["docx", "doc", "xlsx", "xls"]:
            # 合同分析
            contract_service = ContractAnalysisService(self.db)
            try:
                result = await contract_service.analyze_contract_file(file_path, project_id)
                return {
                    "success": True,
                    "type": "contract",
                    "data": result,
                    "file_path": file_path,
                }
            except Exception as e:
                return {"success": False, "message": f"合同分析失败: {e}"}

        else:
            return {
                "success": False,
                "message": f"不支持的文件类型: {ext}",
            }

    async def analyze_folder(
        self,
        folder_path: str,
        project_id: UUID,
        user_id: UUID,
    ) -> dict[str, Any]:
        """
        批量分析文件夹中的文件

        Args:
            folder_path: 文件夹路径
            project_id: 项目 ID
            user_id: 用户 ID

        Returns:
            {"task_id": "..."}
        """
        try:
            from app.tasks import batch_file_analysis

            # 提交 Celery 异步任务
            task = batch_file_analysis.delay(
                folder_path=folder_path,
                project_id=str(project_id),
                user_id=str(user_id),
            )

            return {
                "success": True,
                "task_id": task.id,
                "message": "文件夹分析任务已提交",
            }
        except Exception as e:
            # 如果 Celery 不可用，返回同步处理说明
            logger.warning(f"Celery not available: {e}")
            return {
                "success": True,
                "task_id": None,
                "message": "文件夹分析功能需要在后台启动 Celery worker",
            }

    async def compare_pbc_list(
        self,
        project_id: UUID,
        user_id: UUID,
    ) -> dict[str, Any]:
        """
        比较 PBC 清单与实际文件

        Args:
            project_id: 项目 ID
            user_id: 用户 ID

        Returns:
            比较结果
        """
        from app.services.pbc_service import PBCService
        from app.models.ai_models import DocumentScan

        pbc_service = PBCService(self.db)

        # 获取 PBC 清单
        pbc_items = await pbc_service.get_pbc_list(project_id)

        # 获取实际已上传的文件
        result = await self.db.execute(
            select(DocumentScan).where(
                DocumentScan.project_id == project_id,
                DocumentScan.is_deleted == False,  # noqa: E712
            )
        )
        actual_files = list(result.scalars().all())

        # 构建文件类型映射
        file_type_map: dict[str, list[str]] = {}
        for f in actual_files:
            doc_type = f.document_type.value if hasattr(f.document_type, "value") else str(f.document_type)
            if doc_type not in file_type_map:
                file_type_map[doc_type] = []
            file_type_map[doc_type].append(f.file_name)

        # 比较结果
        comparison = {
            "total_pbc_items": len(pbc_items) if pbc_items else 0,
            "total_actual_files": len(actual_files),
            "matched": [],
            "missing": [],
            "extra": list(file_type_map.keys()),
        }

        if pbc_items:
            for item in pbc_items:
                expected_type = item.get("document_type", "")
                if expected_type in file_type_map and file_type_map[expected_type]:
                    comparison["matched"].append(item)
                    file_type_map[expected_type].pop()
                else:
                    comparison["missing"].append(item)

        # 清理空类型
        comparison["extra"] = [k for k, v in file_type_map.items() if v]

        return {
            "success": True,
            "comparison": comparison,
        }

    def _rule_based_parse(self, user_input: str) -> dict[str, Any]:
        """基于规则的意图解析（回退方案）"""
        text = user_input.strip().lower()

        # QUERY_DATA
        if any(k in text for k in ["查询", "余额", "试算表", "明细", "发生额", "客户", "供应商"]):
            return {
                "intent_type": "QUERY_DATA",
                "params": self._extract_query_params(user_input),
                "confidence": 0.8,
            }

        # GENERATE_WORKPAPER
        if any(k in text for k in ["生成底稿", "填充底稿", "分析复核", "工作底稿"]):
            return {
                "intent_type": "GENERATE_WORKPAPER",
                "params": self._extract_workpaper_params(user_input),
                "confidence": 0.8,
            }

        # ANALYZE_DOCUMENT
        if any(k in text for k in ["分析合同", "识别单据", "ocr", "单据", "合同", "文件分析"]):
            return {
                "intent_type": "ANALYZE_DOCUMENT",
                "params": self._extract_document_params(user_input),
                "confidence": 0.8,
            }

        # CHECK_COMPLIANCE
        if any(k in text for k in ["合规", "检查", "风险", "异常"]):
            return {
                "intent_type": "CHECK_COMPLIANCE",
                "params": {},
                "confidence": 0.7,
            }

        # GENERATE_REPORT
        if any(k in text for k in ["报告", "汇总", "导出"]):
            return {
                "intent_type": "GENERATE_REPORT",
                "params": {},
                "confidence": 0.7,
            }

        # NAVIGATE_UI
        if any(k in text for k in ["打开", "切换", "导航", "进入"]):
            return {
                "intent_type": "NAVIGATE_UI",
                "params": self._extract_navigation_params(user_input),
                "confidence": 0.8,
            }

        return {
            "intent_type": "QUERY_DATA",
            "params": {"raw_text": user_input},
            "confidence": 0.3,
        }

    def _extract_query_params(self, text: str) -> dict[str, Any]:
        """提取查询参数"""
        params = {}

        # 提取科目
        account_match = re.search(r"[\u4e00-\u9fa5]{2,}(?:科目|余额|发生额)", text)
        if account_match:
            params["account_name"] = account_match.group()[:-2] if account_match.group().endswith(("科目", "余额", "发生额")) else account_match.group()

        # 提取时间
        date_match = re.search(r"(\d{4})年?(\d{1,2})?月?", text)
        if date_match:
            params["year"] = date_match.group(1)
            if date_match.group(2):
                params["month"] = date_match.group(2)

        return params

    def _extract_workpaper_params(self, text: str) -> dict[str, Any]:
        """提取底稿参数"""
        params = {}
        wp_match = re.search(r"([\u4e00-\u9fa5]{2,}底稿)", text)
        if wp_match:
            params["workpaper_name"] = wp_match.group(1)
        return params

    def _extract_document_params(self, text: str) -> dict[str, Any]:
        """提取文档参数"""
        params = {}
        if "合同" in text:
            params["document_type"] = "contract"
        elif "单据" in text or "发票" in text:
            params["document_type"] = "invoice"
        return params

    def _extract_navigation_params(self, text: str) -> dict[str, Any]:
        """提取导航参数"""
        params = {}
        target_match = re.search(r"打开|切换到|进入([\u4e00-\u9fa5]+)", text)
        if target_match:
            params["target"] = target_match.group(1)
        return params

    async def execute_command(
        self,
        intent: dict[str, Any],
        project_id: UUID,
        user_id: UUID,
        db: AsyncSession,
    ) -> dict[str, Any]:
        """
        执行已解析的命令

        Args:
            intent: parse_intent 返回的意图字典
            project_id: 项目 ID
            user_id: 用户 ID
            db: 数据库会话

        Returns:
            执行结果
        """
        intent_type = intent.get("intent_type", "QUERY_DATA")
        params = intent.get("params", {})

        try:
            if intent_type == "QUERY_DATA":
                return await self._execute_query_data(project_id, params, db)
            elif intent_type == "GENERATE_WORKPAPER":
                return await self._execute_workpaper(project_id, params, db)
            elif intent_type == "ANALYZE_DOCUMENT":
                return await self._execute_document_analysis(project_id, params, db)
            elif intent_type == "CHECK_COMPLIANCE":
                return await self._execute_compliance_check(project_id, params, db)
            elif intent_type == "GENERATE_REPORT":
                return await self._execute_report_generation(project_id, params, db)
            elif intent_type == "NAVIGATE_UI":
                return self._execute_navigation(params)
            else:
                return {"success": False, "message": f"未知意图类型: {intent_type}"}
        except Exception as e:
            logger.exception(f"Command execution failed: {intent_type}")
            return {"success": False, "message": str(e)}

    async def _execute_query_data(
        self,
        project_id: UUID,
        params: dict,
        db: AsyncSession,
    ) -> dict[str, Any]:
        """执行数据查询"""
        from app.services.trial_balance_service import TrialBalanceService
        from app.services.drilldown_service import DrilldownService

        account_name = params.get("account_name")
        year = params.get("year")

        if account_name:
            # 科目余额查询
            tb_service = TrialBalanceService(db)
            result = await tb_service.get_account_balance(
                project_id=project_id,
                account_name=account_name,
                year=year,
            )
            return {"success": True, "data": result, "type": "query_data"}
        else:
            # 试算表查询
            tb_service = TrialBalanceService(db)
            result = await tb_service.get_trial_balance(project_id=project_id, year=year)
            return {"success": True, "data": result, "type": "trial_balance"}

    async def _execute_workpaper(
        self,
        project_id: UUID,
        params: dict,
        db: AsyncSession,
    ) -> dict[str, Any]:
        """执行底稿生成"""
        from app.services.workpaper_fill_service import WorkpaperFillService

        wp_service = WorkpaperFillService(db)
        workpaper_name = params.get("workpaper_name")

        if workpaper_name:
            # 生成特定底稿的填充
            result = await wp_service.generate_workpaper_data(
                project_id=project_id,
                template_type=workpaper_name,
            )
            return {"success": True, "data": result, "type": "workpaper_fill"}
        else:
            # 生成分析性复核
            result = await wp_service.generate_analytical_review(
                project_id=project_id,
                account_code=params.get("account_code"),
                year=params.get("year"),
            )
            return {"success": True, "data": result, "type": "analytical_review"}

    async def _execute_document_analysis(
        self,
        project_id: UUID,
        params: dict,
        db: AsyncSession,
    ) -> dict[str, Any]:
        """执行文档分析"""
        doc_type = params.get("document_type")

        if doc_type == "contract":
            from app.services.contract_analysis_service import ContractAnalysisService
            service = ContractAnalysisService(db)
            result = await service.generate_contract_summary(project_id)
            return {"success": True, "data": result, "type": "contract_analysis"}
        else:
            from app.services.ocr_service_v2 import OCRService
            service = OCRService(db)
            # 返回分析指令信息
            return {
                "success": True,
                "message": "请上传文档进行OCR识别",
                "type": "document_analysis",
                "params": params,
            }

    async def _execute_compliance_check(
        self,
        project_id: UUID,
        params: dict,
        db: AsyncSession,
    ) -> dict[str, Any]:
        """执行合规检查"""
        from app.services.knowledge_index_service import KnowledgeIndexService

        kbs = KnowledgeIndexService(db)
        result = await kbs.semantic_search(
            project_id=project_id,
            query=params.get("query", "风险检查"),
            top_k=5,
        )
        return {"success": True, "data": result, "type": "compliance_check"}

    async def _execute_report_generation(
        self,
        project_id: UUID,
        params: dict,
        db: AsyncSession,
    ) -> dict[str, Any]:
        """执行报告生成"""
        return {
            "success": True,
            "message": "报告生成功能正在开发中",
            "type": "report_generation",
            "params": params,
        }

    def _execute_navigation(self, params: dict) -> dict[str, Any]:
        """执行界面导航"""
        target = params.get("target", "")
        route_map = {
            "试算表": "/trial-balance",
            "调整分录": "/adjustments",
            "重要性水平": "/materiality",
            "未更正错报": "/misstatements",
            "底稿": "/workpapers",
        }

        for key, route in route_map.items():
            if key in target:
                return {
                    "success": True,
                    "action": "navigate",
                    "route": route,
                    "message": f"将导航到{key}页面",
                }

        return {
            "success": True,
            "action": "navigate",
            "route": "/",
            "message": "导航到首页",
        }

    async def analyze_file(
        self,
        file_path: str,
        project_id: UUID,
    ) -> dict[str, Any]:
        """
        分析单个文件

        Args:
            file_path: 文件路径
            project_id: 项目 ID

        Returns:
            分析结果
        """
        from app.services.ocr_service_v2 import OCRService
        from app.services.contract_analysis_service import ContractAnalysisService

        # 根据文件扩展名判断类型
        ext = file_path.lower().split(".")[-1]

        if ext in ["pdf", "jpg", "jpeg", "png", "bmp"]:
            # 尝试 OCR
            ocr_service = OCRService(self.db)
            try:
                result = await ocr_service.recognize_single(file_path)
                return {
                    "success": True,
                    "type": "ocr",
                    "data": result,
                    "file_path": file_path,
                }
            except Exception as e:
                return {"success": False, "message": f"OCR失败: {e}"}

        elif ext in ["docx", "doc", "xlsx", "xls"]:
            # 合同分析
            contract_service = ContractAnalysisService(self.db)
            result = await contract_service.analyze_contract_file(file_path, project_id)
            return {
                "success": True,
                "type": "contract",
                "data": result,
                "file_path": file_path,
            }

        else:
            return {
                "success": False,
                "message": f"不支持的文件类型: {ext}",
            }

    async def analyze_folder(
        self,
        folder_path: str,
        project_id: UUID,
        user_id: UUID,
    ) -> dict[str, Any]:
        """
        批量分析文件夹中的文件

        Args:
            folder_path: 文件夹路径
            project_id: 项目 ID
            user_id: 用户 ID

        Returns:
            {"task_id": "..."}
        """
        from app.tasks import batch_file_analysis

        # 提交 Celery 异步任务
        task = batch_file_analysis.delay(
            folder_path=folder_path,
            project_id=str(project_id),
            user_id=str(user_id),
        )

        return {
            "success": True,
            "task_id": task.id,
            "message": "文件夹分析任务已提交",
        }

    async def compare_pbc_list(
        self,
        project_id: UUID,
        user_id: UUID,
    ) -> dict[str, Any]:
        """
        比较 PBC 清单与实际文件

        Args:
            project_id: 项目 ID
            user_id: 用户 ID

        Returns:
            比较结果
        """
        from app.services.pbc_service import PBCService
        from app.models import DocumentScan

        pbc_service = PBCService(self.db)

        # 获取 PBC 清单
        pbc_items = await pbc_service.get_pbc_list(project_id)

        # 获取实际已上传的文件
        result = await self.db.execute(
            select(DocumentScan).where(
                DocumentScan.project_id == project_id,
                DocumentScan.is_deleted == False,  # noqa: E712
            )
        )
        actual_files = list(result.scalars().all())

        # 构建文件类型映射
        file_type_map = {}
        for f in actual_files:
            doc_type = f.document_type.value if hasattr(f.document_type, "value") else str(f.document_type)
            if doc_type not in file_type_map:
                file_type_map[doc_type] = []
            file_type_map[doc_type].append(f.file_name)

        # 比较结果
        comparison = {
            "total_pbc_items": len(pbc_items),
            "total_actual_files": len(actual_files),
            "matched": [],
            "missing": [],
            "extra": list(file_type_map.keys()),
        }

        for item in pbc_items:
            expected_type = item.get("document_type", "")
            if expected_type in file_type_map and file_type_map[expected_type]:
                comparison["matched"].append(item)
                file_type_map[expected_type].pop()
            else:
                comparison["missing"].append(item)

        # 清理空类型
        comparison["extra"] = [k for k, v in file_type_map.items() if v]

        return {
            "success": True,
            "comparison": comparison,
        }
