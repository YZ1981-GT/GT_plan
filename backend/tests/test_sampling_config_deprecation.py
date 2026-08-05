"""`sampling_config` 软弃用守卫（sampling-compliance-closure Wave 2 Task 15/16）

背景：`sampling_config` 表全库 0 行（10 个项目 / tb_ledger 697 万行），唯一写入点是
`sampling_service.create_config`，无实际消费方；而样本量/抽样间隔的单一真源已是
`sampling_methodology.py`（CAS 1314 泊松系数 + algo_version）。

本文件不删表不删端点（破坏性操作需用户单独授权），只钉死「不再新增写入点」。

Validates: Requirements 5.7, 5.8
Properties: Property 13
"""

from __future__ import annotations

import re
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent
_APP = _BACKEND / "app"
_SERVICE = _APP / "services" / "sampling_service.py"

# 改造时点基线：全仓构造 SamplingConfig( 的位置数（唯一一处 = create_config）
_SAMPLING_CONFIG_CTOR_BASELINE = 1


def _strip_comments(src: str) -> str:
    src = re.sub(r'"""[\s\S]*?"""', "", src)
    src = re.sub(r"'''[\s\S]*?'''", "", src)
    return re.sub(r"(?m)#.*$", "", src)


def _ctor_sites(name: str) -> list[tuple[str, int]]:
    """返回 backend/app 下（剥注释后）**实例化** `name(` 的 (文件, 次数)。

    排除 ORM 模型的类声明 `class SamplingConfig(Base):` —— 它是类型定义不是写入点，
    算进去会让「不超过基线」永远为假（首版即因此打红）。
    """
    ctor = re.compile(rf"(?<!class )\b{re.escape(name)}\(")
    out: list[tuple[str, int]] = []
    for path in sorted(_APP.rglob("*.py")):
        code = _strip_comments(path.read_text(encoding="utf-8"))
        n = len(ctor.findall(code))
        if n:
            out.append((str(path.relative_to(_BACKEND)).replace("\\", "/"), n))
    return out


class TestSamplingConfigDeprecation:
    def test_module_carries_deprecated_marker(self):
        src = _SERVICE.read_text(encoding="utf-8")
        assert ".. deprecated::" in src, "sampling_service 模块 docstring 须标注弃用"
        # 弃用说明须写明替代真源，否则后来者不知道该用什么
        assert "sampling_methodology" in src

    def test_sampling_config_ctor_sites_not_increased(self):
        """Property 13：`SamplingConfig(` 构造点数量不得超过基线。"""
        sites = _ctor_sites("SamplingConfig")
        total = sum(n for _, n in sites)
        assert total <= _SAMPLING_CONFIG_CTOR_BASELINE, (
            f"新增了 SamplingConfig 写入点（基线 {_SAMPLING_CONFIG_CTOR_BASELINE}）: {sites}"
        )

    def test_baseline_is_not_stale(self):
        """基线非零且确有其位置 —— 否则「不超过基线」是因为一处都没扫到（假绿）。"""
        sites = _ctor_sites("SamplingConfig")
        assert sites, "扫不到任何 SamplingConfig 构造点，疑似路径/剥注释过度"
        assert any("sampling_service.py" in f for f, _ in sites)

    def test_sampling_record_not_deprecated(self):
        """`SamplingRecord` 不在弃用范围（它是 canonical 抽样评价记录表）。"""
        src = _SERVICE.read_text(encoding="utf-8")
        assert "SamplingRecord` 不在弃用范围内" in src or "SamplingRecord**" in src or (
            "SamplingRecord" in src and "不在弃用范围" in src
        ), "须在弃用说明中明确 SamplingRecord 不受影响，避免后来者一起弃用"

    def test_reverse_selfcheck_strip_comments(self):
        raw = '"""说明：SamplingConfig( 只是文档里提到。"""\nx = 1  # SamplingConfig(\n'
        stripped = _strip_comments(raw)
        assert raw.count("SamplingConfig(") == 2
        assert "SamplingConfig(" not in stripped
