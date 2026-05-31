"""
测试 H3 命名澄清零回归：V1/V2 @see 互标 + V2 tag 改名

Validates: Bug 条件 C2, 属性 H3
"""
import ast
from pathlib import Path

# 项目根目录
_BACKEND = Path(__file__).parent.parent
_ROUTERS = _BACKEND / "app" / "routers"
_SERVICES = _BACKEND / "app" / "services"


def _read_docstring(filepath: Path) -> str:
    """读取文件模块级 docstring"""
    source = filepath.read_text(encoding="utf-8")
    tree = ast.parse(source)
    return ast.get_docstring(tree) or ""


class TestV1RouterAnnotation:
    """V1 router 文件头 @see 注释"""

    def test_v1_router_has_see_annotation(self):
        docstring = _read_docstring(_ROUTERS / "address_registry.py")
        assert "@see address_registry_v2" in docstring

    def test_v1_router_describes_runtime_directory(self):
        docstring = _read_docstring(_ROUTERS / "address_registry.py")
        assert "运行时动态地址目录" in docstring
        assert "公式编辑" in docstring


class TestV1ServiceAnnotation:
    """V1 service 文件头 @see 注释"""

    def test_v1_service_has_see_annotation(self):
        docstring = _read_docstring(_SERVICES / "address_registry.py")
        assert "@see address_registry_v2" in docstring

    def test_v1_service_describes_runtime_directory(self):
        docstring = _read_docstring(_SERVICES / "address_registry.py")
        assert "运行时动态地址目录" in docstring
        assert "公式编辑" in docstring


class TestV2RouterAnnotation:
    """V2 router 文件头 @see 注释"""

    def test_v2_router_has_see_annotation(self):
        docstring = _read_docstring(_ROUTERS / "address_registry_v2.py")
        assert "@see address_registry" in docstring

    def test_v2_router_describes_static_dependency_graph(self):
        docstring = _read_docstring(_ROUTERS / "address_registry_v2.py")
        assert "静态依赖图" in docstring
        assert "stale 影响分析" in docstring
        assert "linkage_graph 离线产物" in docstring


class TestV2TagRenamed:
    """V2 router tag 从 address-registry 改为 linkage-analysis"""

    def test_v2_router_tag_is_linkage_analysis(self):
        """确认 V2 router 的 tags 包含 linkage-analysis"""
        source = (_ROUTERS / "address_registry_v2.py").read_text(encoding="utf-8")
        # 确认新 tag 存在
        assert '"linkage-analysis"' in source or "'linkage-analysis'" in source

    def test_v2_router_tag_not_address_registry(self):
        """确认 V2 router 不再使用旧 tag address-registry-v2"""
        source = (_ROUTERS / "address_registry_v2.py").read_text(encoding="utf-8")
        # tags= 行不应包含旧名
        assert '"address-registry-v2"' not in source
        assert "'address-registry-v2'" not in source

    def test_v2_router_prefix_unchanged(self):
        """确认 V2 router 的 URL prefix 不变（仅 tag 改名）"""
        source = (_ROUTERS / "address_registry_v2.py").read_text(encoding="utf-8")
        assert '"/api/address-registry/v2"' in source
