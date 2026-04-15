"""统一响应包装中间件

成功响应（2xx）自动包装为 {"code": status_code, "message": "success", "data": <payload>}

Validates: Requirements 4.1
"""

import json

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response


# 跳过包装的路径前缀
_SKIP_PATHS = ("/docs", "/redoc", "/openapi.json", "/wopi/", "/api/events/")


class ResponseWrapperMiddleware(BaseHTTPMiddleware):
    """将 2xx JSON 响应统一包装为 ApiResponse 格式。"""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # 跳过文档路径
        if request.url.path.startswith(_SKIP_PATHS):
            return await call_next(request)

        response = await call_next(request)

        # 仅处理 2xx 状态码
        if not (200 <= response.status_code < 300):
            return response

        # 仅处理 JSON 响应
        content_type = response.headers.get("content-type", "")
        if "application/json" not in content_type:
            return response

        # 跳过 SSE 流式响应
        if "text/event-stream" in content_type:
            return response

        # 读取原始响应体
        body_bytes = b""
        async for chunk in response.body_iterator:  # type: ignore[union-attr]
            if isinstance(chunk, str):
                body_bytes += chunk.encode("utf-8")
            else:
                body_bytes += chunk

        # 尝试解析 JSON
        try:
            payload = json.loads(body_bytes)
        except (json.JSONDecodeError, UnicodeDecodeError):
            # 无法解析则原样返回
            return Response(
                content=body_bytes,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.media_type,
            )

        # 已经是 ApiResponse 格式则跳过
        if isinstance(payload, dict) and "code" in payload and "message" in payload:
            return Response(
                content=body_bytes,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.media_type,
            )

        # 包装为统一格式
        wrapped = {
            "code": response.status_code,
            "message": "success",
            "data": payload,
        }
        wrapped_bytes = json.dumps(wrapped, ensure_ascii=False).encode("utf-8")

        # 去掉原始 Content-Length，Response 会自动根据新 body 计算
        headers = {k: v for k, v in response.headers.items() if k.lower() != "content-length"}

        return Response(
            content=wrapped_bytes,
            status_code=response.status_code,
            headers=headers,
            media_type="application/json",
        )
