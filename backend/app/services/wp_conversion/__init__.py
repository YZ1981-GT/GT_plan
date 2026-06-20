"""wp_conversion — ``WpStandardConversionService`` 的拆分子包（pass4 大文件拆分）。

主 class ``WpStandardConversionService`` 通过 mixin 继承组合底稿生成相关方法，
保持所有方法仍挂在实例上（测试以 ``service.method()`` 访问），对外入口/签名零变更。
"""
from __future__ import annotations

from app.services.wp_conversion._generate import WpConversionGenerateMixin

__all__ = ["WpConversionGenerateMixin"]
