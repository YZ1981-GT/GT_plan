"""项目分类单一来源（spec trim-generation-plan-followup-optimizations R4）。

``projects.business_category`` 只放质控业务分类（致同 2025 业务分类参考标准：A / A1~A8、B / B1~B6、C），
``projects.scenario`` 放专项场景（normal / ipo / listed / refinancing / transfer / restructure / fraud_response）。
历史上 ``business_category`` 还被写成 ``IPO`` / ``refinancing`` 这类场景值，各模块再各自按首字母、子串或
中文别名解释，同一项目在生成计划、模板列表、D4、F2、A16 推荐里判出不同结果。

:func:`resolve` 是唯一解释入口（纯函数）：

- 分类码只认参考标准登记的码（去首尾空白、大写）；空值、未登记值 ⇒ ``category_code=None``、``defaulted=True``、
  组别按 C（只用于判定，不写回数据库）。
- 场景只认登记值；V219 迁移前残留在分类列里的 ``IPO`` / ``refinancing`` 在场景仍为 normal 时按场景解释，
  所以迁移前后各模块判定一致。
- 适用性标签 ``tags`` 对齐模板 ``applicable_when.business_category`` 的声明值（ipo / listed / neeq /
  restructuring / refinancing / fraud_risk）：来自场景、参考标准里语义等价的细分类（A1 上市公司、A2 IPO 首次申报、
  A3 重大资产重组、A4 再融资、A7 境外上市、B1 新三板 / 北交所）和上市公司报表模板。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping
from uuid import UUID

CATEGORY_GROUPS = ("A", "B", "C")
DEFAULT_GROUP = "C"

SCENARIOS = ("normal", "ipo", "listed", "refinancing", "transfer", "restructure", "fraud_response")
DEFAULT_SCENARIO = "normal"
SCENARIO_LABELS = {
    "normal": "常规年审",
    "ipo": "IPO 申报",
    "listed": "上市公司年审",
    "refinancing": "再融资",
    "transfer": "新三板挂牌",
    "restructure": "重大资产重组",
    "fraud_response": "舞弊应对",
}

#: V219 迁移前残留在分类列里的场景值（大写比较）→ 场景。
LEGACY_SCENARIO_CATEGORIES = {"IPO": "ipo", "REFINANCING": "refinancing"}

SCENARIO_TAGS = {
    "ipo": "ipo",
    "listed": "listed",
    "refinancing": "refinancing",
    "transfer": "neeq",
    "restructure": "restructuring",
    "fraud_response": "fraud_risk",
}
CATEGORY_TAGS = {"A1": "listed", "A2": "ipo", "A3": "restructuring", "A4": "refinancing", "A7": "listed", "B1": "neeq"}
#: 资本市场类标签（与前端 ``IPO_BIZ_KEYWORDS`` 同一组）。
CAPITAL_MARKET_TAGS = frozenset({"ipo", "listed", "neeq", "restructuring", "refinancing"})
ALL_TAGS = tuple(sorted(CAPITAL_MARKET_TAGS | {"fraud_risk"}))

_REFERENCE = Path(__file__).resolve().parents[2] / "data" / "business_category_reference.json"


@lru_cache(maxsize=1)
def category_codes() -> frozenset[str]:
    """参考标准登记的全部分类码：组别 A / B / C + 各组细分类码。"""
    data = json.loads(_REFERENCE.read_text(encoding="utf-8"))
    codes = set(CATEGORY_GROUPS)
    for group, body in (data.get("categories") or {}).items():
        codes.add(str(group).upper())
        for sub in (body or {}).get("subcategories") or ():
            if isinstance(sub, Mapping) and sub.get("code"):
                codes.add(str(sub["code"]).strip().upper())
    return frozenset(codes)


class ClassificationValueError(ValueError):
    """写入的分类码 / 场景不在登记值内（路由回 422）。"""


def normalize_category(value: Any) -> str | None:
    """严格归一（写入用）：空 ⇒ None；登记码 ⇒ 大写码；其他（含旧场景值 IPO）⇒ :class:`ClassificationValueError`。"""
    text = str(value).strip().upper() if value is not None else ""
    if not text:
        return None
    if text not in category_codes():
        raise ClassificationValueError(
            f"质控业务分类只能是 A / A1~A8、B / B1~B6 或 C，收到「{value}」；IPO / 再融资等请填专项场景")
    return text


def normalize_scenario(value: Any) -> str:
    """严格归一（写入用）：空 ⇒ normal；登记值 ⇒ 小写值；其他 ⇒ :class:`ClassificationValueError`。"""
    text = str(value).strip().lower() if value is not None else ""
    if not text:
        return DEFAULT_SCENARIO
    if text not in SCENARIOS:
        raise ClassificationValueError(f"专项场景只能是 {' / '.join(SCENARIOS)}，收到「{value}」")
    return text


@dataclass(frozen=True)
class ProjectClassification:
    category_code: str | None
    category_group: str
    defaulted: bool
    scenario: str
    tags: frozenset[str]

    @property
    def is_ipo(self) -> bool:
        return "ipo" in self.tags

    @property
    def is_refinancing(self) -> bool:
        return "refinancing" in self.tags

    @property
    def is_capital_market(self) -> bool:
        return bool(self.tags & CAPITAL_MARKET_TAGS)

    def has_tag(self, tag: str) -> bool:
        return str(tag or "").strip().lower() in self.tags

    def flags(self) -> dict[str, bool]:
        """模板 ``applicable_when.business_category`` 判定用的 ``biz_<标签>`` flags。"""
        return {f"biz_{tag}": tag in self.tags for tag in ALL_TAGS}

    def as_dict(self) -> dict[str, Any]:
        return {
            "category_code": self.category_code,
            "category_group": self.category_group,
            "defaulted": self.defaulted,
            "scenario": self.scenario,
            "scenario_label": SCENARIO_LABELS[self.scenario],
            "is_ipo": self.is_ipo,
            "is_refinancing": self.is_refinancing,
            "is_capital_market": self.is_capital_market,
            "tags": sorted(self.tags),
        }


def resolve(business_category: Any, scenario: Any = None, template_type: Any = None) -> ProjectClassification:
    """宽松解释（读取用，永不抛错）：未登记的分类码按未填写、未登记的场景按 normal。"""
    raw_category = str(business_category).strip().upper() if business_category is not None else ""
    code = raw_category if raw_category in category_codes() else None
    raw_scenario = str(scenario).strip().lower() if scenario is not None else ""
    resolved_scenario = raw_scenario if raw_scenario in SCENARIOS else DEFAULT_SCENARIO
    if resolved_scenario == DEFAULT_SCENARIO and raw_category in LEGACY_SCENARIO_CATEGORIES:
        resolved_scenario = LEGACY_SCENARIO_CATEGORIES[raw_category]
    tags: set[str] = set()
    if resolved_scenario in SCENARIO_TAGS:
        tags.add(SCENARIO_TAGS[resolved_scenario])
    if code in CATEGORY_TAGS:
        tags.add(CATEGORY_TAGS[code])
    if str(template_type or "").strip().lower() == "listed":
        tags.add("listed")
    return ProjectClassification(
        category_code=code,
        category_group=code[0] if code else DEFAULT_GROUP,
        defaulted=code is None,
        scenario=resolved_scenario,
        tags=frozenset(tags),
    )


def project_classification(project: Any) -> ProjectClassification:
    """ORM 项目（或带同名属性的对象）的分类。"""
    return resolve(
        getattr(project, "business_category", None),
        getattr(project, "scenario", None),
        getattr(project, "template_type", None),
    )


async def load_project_classification(db, project_id: UUID | str) -> ProjectClassification:
    """按项目 id 读分类；项目不存在按全默认（C 组、normal、无标签）。"""
    import sqlalchemy as sa

    from app.models.core import Project

    row = (await db.execute(
        sa.select(Project.business_category, Project.scenario, Project.template_type)
        .where(Project.id == (project_id if isinstance(project_id, UUID) else UUID(str(project_id))))
    )).first()
    return resolve(*row) if row else resolve(None)
