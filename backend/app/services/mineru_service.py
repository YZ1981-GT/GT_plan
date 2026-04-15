"""MinerU 文档解析服务 - 用于复杂文档场景

支持：
- 学术论文解析（Markdown/JSON输出）
- 表格识别与提取
- 公式识别（LaTeX）
- 版面分析与结构化

支持两种模式：
1. CLI 模式：直接调用本地 mineru 命令（推荐用于打包部署）
2. HTTP 模式：调用远程 MinerU API 服务（推荐用于独立服务部署）
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class MinerUService:
    """MinerU 文档解析服务 - 支持 CLI 和 HTTP 模式"""

    def __init__(self):
        self.api_url = getattr(settings, "MINERU_API_URL", "http://localhost:8000")
        self.enabled = getattr(settings, "MINERU_ENABLED", False)
        self.timeout = 300  # 5分钟超时
        # 使用 CLI 模式（直接调用本地 mineru 命令）
        self.use_cli = getattr(settings, "MINERU_USE_CLI", True)

    async def is_available(self) -> bool:
        """检查 MinerU 服务是否可用"""
        if not self.enabled:
            return False

        if self.use_cli:
            # CLI 模式：检查 mineru 命令是否可用
            try:
                result = await asyncio.create_subprocess_exec(
                    "mineru",
                    "--version",
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                stdout, stderr = await result.communicate()
                return result.returncode == 0
            except Exception as exc:
                logger.warning(f"MinerU CLI check failed: {exc}")
                return False
        else:
            # HTTP 模式：检查 API 服务是否可用
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.get(f"{self.api_url}/health")
                    return response.status_code == 200
            except Exception as exc:
                logger.warning(f"MinerU API health check failed: {exc}")
                return False

    async def parse_document(
        self,
        file_path: str,
        output_format: str = "markdown",
    ) -> dict[str, Any]:
        """解析复杂文档

        Args:
            file_path: 文件路径
            output_format: 输出格式（markdown/json）

        Returns:
            {
                "text": "完整文本",
                "markdown": "Markdown格式",
                "tables": [{"html": "...", "data": [...]}],
                "formulas": [{"latex": "...", "position": {...}}],
                "structure": {...},
                "engine": "mineru"
            }
        """
        if not self.enabled:
            raise RuntimeError("MinerU service is not enabled")

        if self.use_cli:
            return await self._parse_document_cli(file_path, output_format)
        else:
            return await self._parse_document_http(file_path, output_format)

    async def _parse_document_cli(
        self,
        file_path: str,
        output_format: str,
    ) -> dict[str, Any]:
        """使用 CLI 模式解析文档"""
        try:
            # 创建临时输出目录
            with tempfile.TemporaryDirectory() as temp_dir:
                output_path = Path(temp_dir) / "output"

                # 调用 mineru CLI
                cmd = [
                    "mineru",
                    "-p", file_path,
                    "-o", str(output_path),
                    "-b", "pipeline",  # 使用 pipeline 后端
                ]

                result = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                stdout, stderr = await asyncio.wait_for(
                    result.communicate(),
                    timeout=self.timeout,
                )

                if result.returncode != 0:
                    error_msg = stderr.decode("utf-8", errors="ignore")
                    raise RuntimeError(f"MinerU CLI failed: {error_msg}")

                # 读取输出文件
                markdown_file = output_path / f"{Path(file_path).stem}.md"
                if markdown_file.exists():
                    with open(markdown_file, "r", encoding="utf-8") as f:
                        markdown_content = f.read()
                else:
                    markdown_content = ""

                # 读取 JSON 结构文件（如果存在）
                json_file = output_path / f"{Path(file_path).stem}.json"
                structure = {}
                if json_file.exists():
                    with open(json_file, "r", encoding="utf-8") as f:
                        structure = json.load(f)

                return {
                    "text": markdown_content,
                    "markdown": markdown_content,
                    "tables": structure.get("tables", []),
                    "formulas": structure.get("formulas", []),
                    "structure": structure,
                    "engine": "mineru",
                }

        except asyncio.TimeoutError:
            raise RuntimeError("MinerU CLI timeout")
        except Exception as exc:
            logger.error(f"MinerU CLI parse failed: {exc}")
            raise

    async def _parse_document_http(
        self,
        file_path: str,
        output_format: str,
    ) -> dict[str, Any]:
        """使用 HTTP 模式解析文档"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                # 调用 MinerU API
                with open(file_path, "rb") as f:
                    files = {"file": f}
                    params = {"output_format": output_format}
                    response = await client.post(
                        f"{self.api_url}/parse",
                        files=files,
                        params=params,
                    )

                if response.status_code != 200:
                    raise RuntimeError(f"MinerU API returned {response.status_code}")

                result = response.json()
                return {
                    "text": result.get("text", ""),
                    "markdown": result.get("markdown", ""),
                    "tables": result.get("tables", []),
                    "formulas": result.get("formulas", []),
                    "structure": result.get("structure", {}),
                    "engine": "mineru",
                }

        except Exception as exc:
            logger.error(f"MinerU HTTP parse failed: {exc}")
            raise

    async def extract_tables(self, file_path: str) -> list[dict[str, Any]]:
        """提取表格"""
        if not self.enabled:
            raise RuntimeError("MinerU service is not enabled")

        if self.use_cli:
            # CLI 模式：从 parse_document 结果中提取表格
            result = await self.parse_document(file_path, output_format="markdown")
            return result.get("tables", [])
        else:
            # HTTP 模式：调用 API
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    with open(file_path, "rb") as f:
                        files = {"file": f}
                        response = await client.post(
                            f"{self.api_url}/extract/tables",
                            files=files,
                        )

                    if response.status_code != 200:
                        raise RuntimeError(f"MinerU API returned {response.status_code}")

                    return response.json().get("tables", [])

            except Exception as exc:
                logger.error(f"MinerU extract tables failed: {exc}")
                raise

    async def extract_formulas(self, file_path: str) -> list[dict[str, Any]]:
        """提取公式"""
        if not self.enabled:
            raise RuntimeError("MinerU service is not enabled")

        if self.use_cli:
            # CLI 模式：从 parse_document 结果中提取公式
            result = await self.parse_document(file_path, output_format="markdown")
            return result.get("formulas", [])
        else:
            # HTTP 模式：调用 API
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    with open(file_path, "rb") as f:
                        files = {"file": f}
                        response = await client.post(
                            f"{self.api_url}/extract/formulas",
                            files=files,
                        )

                    if response.status_code != 200:
                        raise RuntimeError(f"MinerU API returned {response.status_code}")

                    return response.json().get("formulas", [])

            except Exception as exc:
                logger.error(f"MinerU extract formulas failed: {exc}")
                raise

    async def recognize_for_ocr(self, file_path: str) -> dict[str, Any]:
        """用于 OCR 识别的简化接口（兼容 UnifiedOCRService 格式）

        Returns:
            {
                "text": "完整文本",
                "engine": "mineru",
                "regions": [],
                "tables": [...],
                "formulas": [...]
            }
        """
        result = await self.parse_document(file_path, output_format="markdown")
        return {
            "text": result["text"],
            "engine": "mineru",
            "regions": [],  # MinerU 不返回区域信息
            "tables": result.get("tables", []),
            "formulas": result.get("formulas", []),
        }
