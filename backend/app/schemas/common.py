"""统一响应模型"""

from typing import Any, Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """成功响应格式

    Validates: Requirements 4.1
    """

    code: int = 200
    message: str = "success"
    data: T | None = None


class ErrorResponse(BaseModel):
    """错误响应格式

    Validates: Requirements 4.2
    """

    code: int
    message: str
    detail: Any = None
