"""E2E FIX 夹具的**声明层**：wp_code 清单 / 模板映射 / FixtureSpec / FixtureResult。

从 `seed_fix_projects.py` 抽出（2026-09-28）。这一层是纯声明数据与两个 dataclass，
不碰 DB、不读 CLI 参数，因此：

* 可被测试直接 import 取权威清单（`tests/scripts/test_seed_fix_f2_e2e.py` 正是这么用的），
  不必再手抄一份 —— 手抄那份漏了 `F2-29` 导致该测试长期恒红；
* `seed_fix_projects.py` 从 871 行降到 ≤800，退出文件行数门禁白名单。

`seed_fix_projects` 仍 re-export 本模块的公开名，既有 import 路径不变。

Spec: completion-phase-infra e2e-matrix.md E-FIX
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID

_BACKEND = Path(__file__).resolve().parent.parent.parent

DEFAULT_FIX_B = UUID("37814426-a29e-4fc2-9313-a59d229bf7b0")
DEFAULT_YEAR = 2025
# 本地 PG 与历史 e2e 硬编码 UUID 可能不一致，按名称兜底
FIX_B_NAME_HINTS = ("辽宁卫生", "和平药房", "陕西华氏")

# E2E 矩阵所需底稿（最小集）
FIX_B_WP_CODES = [
    "A7", "A8", "A8-1", "A9", "A9-1", "A10", "A11", "A11-1", "A14", "A15", "A15-1",
    "A16", "A16-1", "A18", "A18-1", "A18-2",
]
FIX_A_WP_CODES = [
    "A17", "A17-1", "A17-2-1", "A17-3", "A17-5", "A17-5-1", "A17-5-2", "A17-5-3", "A17-5-4", "A17-5-5",
    "A18", "A18-1", "A18-2",
    "A21-1", "A22-1", "A23-1", "A24-1", "A25-1",
]
FIX_INT_WP_CODES = ["B60", "A16-2", "A11-3"]
FIX_RP_WP_CODES = ["A7", "A7-1"]

# F 循环 HTML E2E（与 e2e/f2-*.spec.ts 对齐）
F2_E2E_WP_CODES = [
    "F2-1",
    "F2-21", "F2-22", "F2-23", "F2-24", "F2-25", "F2-26",
    # 检查类 bundle：截止 F2-29~32 + 采购/领用/委托 F2-33~35（同 xlsx）
    "F2-29",
    "F2-47",
    "F2-55",
    "F2-70",
]

# I 循环 HTML E2E（I6-4 针对性检查 + I6↔I2 VR-I6-01）
I6_E2E_WP_CODES = ["I6", "I2"]

# wp_code → backend/wp_templates/F 下源 xlsx（同码多底稿共用 bundle 文件）
F2_WP_TEMPLATE_FILES: dict[str, str] = {
    "F2-1": "F2-1至F2-14 存货及跌价准备-审定明细表类（Leap-常规程序）.xlsx",
    "F2-21": "F2-21至F2-26 存货及跌价准备 - 盘点类（Leap应对措施- 存货监盘）.xlsx",
    "F2-22": "F2-21至F2-26 存货及跌价准备 - 盘点类（Leap应对措施- 存货监盘）.xlsx",
    "F2-23": "F2-21至F2-26 存货及跌价准备 - 盘点类（Leap应对措施- 存货监盘）.xlsx",
    "F2-24": "F2-21至F2-26 存货及跌价准备 - 盘点类（Leap应对措施- 存货监盘）.xlsx",
    "F2-25": "F2-21至F2-26 存货及跌价准备 - 盘点类（Leap应对措施- 存货监盘）.xlsx",
    "F2-26": "F2-21至F2-26 存货及跌价准备 - 盘点类（Leap应对措施- 存货监盘）.xlsx",
    "F2-29": "F2-29至F2-35 存货及跌价准备 -检查类（Leap应对措施-检查）.xlsx",
    "F2-47": "F2-47至F2-49 存货及跌价准备 -跌价准备测试（Leap应对措施-会计估计）.xlsx",
    "F2-55": "F2-55至F2-58 合同履约成本.xlsx",
    "F2-70": "F2-61至F2-72 存货及跌价准备-IPO 上市 新三板 重组 舞弊应对.xlsx",
}

WP_TEMPLATES_F = _BACKEND / "wp_templates" / "F"


@dataclass
class FixtureSpec:
    fixture_id: str
    description: str
    required_wp_codes: list[str]
    env_var: str
    default_project_id: UUID | None = None
    business_category: str | None = None
    scenario: str | None = None
    seed_a17_ch01: bool = False
    seed_related_party: bool = False
    seed_i6_e2e: bool = False
    needs_integrated_signal: bool = False


FIXTURES: list[FixtureSpec] = [
    FixtureSpec(
        fixture_id="FIX-B",
        description="B 类默认财报 — A7–A15、A16-1、A18",
        required_wp_codes=FIX_B_WP_CODES,
        env_var="TEST_PROJECT_ID_FIX_B",
        default_project_id=DEFAULT_FIX_B,
        business_category="B3",
    ),
    FixtureSpec(
        fixture_id="FIX-A",
        description="A 类 — A17 适用性、A17-5、A18",
        required_wp_codes=FIX_A_WP_CODES,
        env_var="TEST_PROJECT_ID_FIX_A",
        business_category="A1",
        seed_a17_ch01=True,
    ),
    FixtureSpec(
        fixture_id="FIX-INT",
        description="整合审计信号 — A16-2、A11-3",
        required_wp_codes=FIX_INT_WP_CODES,
        env_var="TEST_PROJECT_ID_FIX_INT",
        needs_integrated_signal=True,
    ),
    FixtureSpec(
        fixture_id="FIX-RP",
        description="A7 关联交易 — A16-7 推荐",
        required_wp_codes=FIX_RP_WP_CODES,
        env_var="TEST_PROJECT_ID_FIX_RP",
        seed_related_party=True,
    ),
    FixtureSpec(
        fixture_id="FIX-F",
        description="F 循环 E2E — 存货审定/监盘/跌价/履约/IPO",
        required_wp_codes=F2_E2E_WP_CODES,
        env_var="TEST_PROJECT_ID_FIX_F",
        default_project_id=DEFAULT_FIX_B,
        business_category="IPO",
    ),
    FixtureSpec(
        fixture_id="FIX-I6",
        description="I6 研发费用 HTML E2E — I6-4 针对性检查 + I6↔I2 VR-I6-01",
        required_wp_codes=I6_E2E_WP_CODES,
        env_var="TEST_PROJECT_ID_FIX_I6",
        default_project_id=DEFAULT_FIX_B,
        seed_i6_e2e=True,
    ),
]


@dataclass
class FixtureResult:
    fixture_id: str
    project_id: str | None = None
    project_name: str | None = None
    business_category: str | None = None
    ready: bool = False
    missing_wp_codes: list[str] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    i6_wp_id: str | None = None
