"""ExportUnitPolicy 真实接线守卫（spec platform-global-display-settings-closure 任务 10）。

## 这个守卫守的是什么

该 spec 的 2026-11-14 复核抓到一条「文件在但链路断」的典型：

- `backend/app/schemas/export_unit_policy.py` 定义完整（`ExportUnitRegion` /
  `ExportUnitPolicy` / `build_policy` / `UNIT_DIVISORS`）；
- `backend/tests/test_export_unit_policy.py` 只测 schema 自身（28 行）；
- 但 `git grep "from app.schemas.export_unit_policy" -- backend/app` **零命中**、
  `ExportUnitRegion` 在 `backend/app/services` **零命中** ⇒ 孤岛。
  后果：屏幕按万元显示、导出文件永远是元、且大多不标单位。

所以本文件不断言「schema 能构造」（那已有一条），而是断言**金额真的会按单位折算并落进文件**，
以及**单位口径只有一个来源**。

## 分组

1. 解析层不变量：`ALLOWED_UNITS` 与 schema 的 `UNIT_DIVISORS` 逐值一致、
   `_UNIT_LABELS` 与之同键（新增单位漏一个就红）。
2. 折算正确性：divisor=1/1000/10000 时 B 列值与 R7 单位标注同时正确
   （**必须两者同源** —— 只对一边就允许「标万元、值是元」）。
3. 精度：万元档用 Decimal 折算并 ROUND_HALF_UP 到 0.01，不出现 float 尾差。
4. 生产接线存在性（反向自检）：router 真的把 policy 传进 service，而不是只 import 不调用。
"""

from __future__ import annotations

import io
import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
from openpyxl import load_workbook
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.bad_debt_models import BadDebtDetailRow, ProvisionMethod
from app.models.base import Base
from app.schemas.bad_debt_schemas import CreateChildRowDTO, CreateParentRowDTO
from app.schemas.export_unit_policy import UNIT_DIVISORS, build_policy
from app.services.bad_debt_export_service import (
    _UNIT_LABELS,
    BadDebtExportService,
)
from app.services.bad_debt_nested_table_service import NestedTableService
from app.services.export_unit_policy_resolver import ALLOWED_UNITS

_DATA_START_ROW = 12
# R7 写单位标注：`_write_meta` 把它写在 **R7 第 14 列（N 列，右上角）**，
# 不是 A 列 —— 我第一版按 A 列断言，3 条用例全红，读源码才发现列位不同。
_META_UNIT_ROW = 7
_META_UNIT_COL = 14


# ─── 分组 1：口径一致性（纯函数，无 DB） ─────────────────────────────────────


def test_allowed_units_matches_schema_divisors():
    """解析层允许的单位集合必须与 schema 的 UNIT_DIVISORS 逐值一致。

    新增一个单位（例如 'bai' 百元）却忘记同步解析层 ⇒ 该单位会被静默当成 yuan，
    金额差 100 倍而没有一行报错。
    """
    assert set(ALLOWED_UNITS) == set(UNIT_DIVISORS), (
        f"ALLOWED_UNITS={sorted(ALLOWED_UNITS)} 与 "
        f"UNIT_DIVISORS={sorted(UNIT_DIVISORS)} 不一致"
    )


def test_unit_labels_cover_every_unit():
    """导出单位的中文标注必须覆盖 schema 的每一个单位，且除数语义正确。"""
    assert set(_UNIT_LABELS) == set(UNIT_DIVISORS)
    # 标签与除数必须语义一致，否则「标万元、除 1000」
    assert UNIT_DIVISORS["yuan"] == 1 and _UNIT_LABELS["yuan"] == "元"
    assert UNIT_DIVISORS["qian"] == 1000 and _UNIT_LABELS["qian"] == "千元"
    assert UNIT_DIVISORS["wan"] == 10000 and _UNIT_LABELS["wan"] == "万元"


def test_build_policy_digest_is_deterministic():
    """同一输入的 policy 摘要稳定（快照/digest 要对得上，重复导出的记录才能比对）。"""
    pid = uuid.uuid4()
    a = build_policy(pid, "wan")
    b = build_policy(pid, "wan")
    assert a.divisor == b.divisor == 10000
    assert a.canonical_digest == b.canonical_digest
    # 不同单位必须得到不同摘要（否则「元」和「万元」的快照无法区分）
    assert build_policy(pid, "yuan").canonical_digest != a.canonical_digest


# ─── 分组 2/3：折算真的落进文件 ──────────────────────────────────────────────


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all, tables=[BadDebtDetailRow.__table__]
        )
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()


async def _build_tree(session: AsyncSession) -> uuid.UUID:
    """一行父 + 一行子，子行 E 列 = 12000.00（便于用 10000 除数得到整齐结果）。"""
    svc = NestedTableService(session)
    wp = uuid.uuid4()
    p = await svc.create_parent_row(
        wp,
        CreateParentRowDTO(
            provision_method=ProvisionMethod.INDIVIDUAL, row_label="按单项评估计提"
        ),
    )
    await svc.create_child_row(
        p.id,
        CreateChildRowDTO(
            row_label="甲公司",
            amount_e=Decimal("12000.00"),
            amount_n=Decimal("12000.00"),
        ),
    )
    return wp


async def _export(session: AsyncSession, wp: uuid.UUID, unit: str):
    policy = build_policy(uuid.uuid4(), unit)  # type: ignore[arg-type]
    svc = BadDebtExportService(session)
    buf = await svc.export_bytes(wp, template_only=False, export_policy=policy)
    assert isinstance(buf, io.BytesIO)
    return load_workbook(io.BytesIO(buf.getvalue()))


@pytest.mark.asyncio
async def test_yuan_keeps_raw_amount_and_labels_yuan(session):
    """yuan（divisor=1）：金额原值，R7 标「元」。"""
    wp = await _build_tree(session)
    ws = (await _export(session, wp, "yuan")).active

    # R7 单位标注
    assert ws.cell(_META_UNIT_ROW, _META_UNIT_COL).value == "金额单位：元"
    # 子行 E 列（第 5 列）= 12000.00 原值
    assert ws.cell(_DATA_START_ROW + 1, 5).value == 12000


@pytest.mark.asyncio
async def test_wan_divides_amount_and_labels_wan(session):
    """wan（divisor=10000）：金额被折算，R7 标「万元」。

    🔴 这两条必须一起断言 —— 只对金额就会允许「折算对了但标错单位」的跳变，
    只对标签就会允许「标万元、值是元」这种最危险的不一致。
    """
    wp = await _build_tree(session)
    ws = (await _export(session, wp, "wan")).active

    assert ws.cell(_META_UNIT_ROW, _META_UNIT_COL).value == "金额单位：万元"
    # 12000 / 10000 = 1.2
    assert abs(float(ws.cell(_DATA_START_ROW + 1, 5).value) - 1.2) < 1e-9


@pytest.mark.asyncio
async def test_qian_divides_amount_and_labels_qian(session):
    """qian（divisor=1000）：金额折算，R7 标「千元」。"""
    wp = await _build_tree(session)
    ws = (await _export(session, wp, "qian")).active

    assert ws.cell(_META_UNIT_ROW, _META_UNIT_COL).value == "金额单位：千元"
    assert abs(float(ws.cell(_DATA_START_ROW + 1, 5).value) - 12.0) < 1e-9


@pytest.mark.asyncio
async def test_wan_uses_decimal_rounding_not_float(session):
    """万元以上折算按 Decimal ROUND_HALF_UP 到 0.01，不留 float 尾差。

    取 12345.67 / 10000 = 1.234567 → 应为 1.23（四舍五入到分），
    若用 float 直接除并写回，会出现 1.2345669999999999 这类值。
    """
    svc_tree = NestedTableService(session)
    wp = uuid.uuid4()
    p = await svc_tree.create_parent_row(
        wp,
        CreateParentRowDTO(
            provision_method=ProvisionMethod.INDIVIDUAL, row_label="按单项评估计提"
        ),
    )
    await svc_tree.create_child_row(
        p.id,
        CreateChildRowDTO(row_label="丙公司", amount_e=Decimal("12345.67")),
    )

    ws = (await _export(session, wp, "wan")).active
    got = ws.cell(_DATA_START_ROW + 1, 5).value
    # 1.234567 → 1.23（两位小数，四舍五入）
    assert Decimal(str(got)) == Decimal("1.23"), f"期望 1.23，实得 {got!r}"
    # 反向：不得出现 float 尾差（把 1.23 写成 1.2299999... 之类）
    assert str(got) in {"1.23", "1.2"}, f"值不应带 float 尾差：{got!r}"


@pytest.mark.asyncio
async def test_no_policy_keeps_legacy_yuan_behaviour(session):
    """不传 policy 时行为与改造前一致（元原值、不标单位），保证旧调用方零影响。"""
    wp = await _build_tree(session)
    svc = BadDebtExportService(session)
    buf = await svc.export_bytes(wp, template_only=False)  # 不传 export_policy
    ws = load_workbook(io.BytesIO(buf.getvalue())).active

    assert ws.cell(_META_UNIT_ROW, _META_UNIT_COL).value is None  # 旧行为：不写单位
    assert ws.cell(_DATA_START_ROW + 1, 5).value == 12000  # 原值


# ─── 分组 4：生产接线存在性（反向自检） ─────────────────────────────────────


def test_router_actually_passes_policy_into_service():
    """router 必须真的把 policy 传进 service，而不是只 import 不调用。

    这一条是「孤岛」这一类缺陷的专用判据：文件在、import 在、单测绿，
    但生产调用点没接线 —— 2026-11-14 复核就是靠这种反向断言才抓到
    `ExportUnitPolicy` 零消费方。
    """
    from pathlib import Path

    router_src = (
        Path(__file__).resolve().parents[1] / "app" / "routers" / "bad_debt_rows.py"
    ).read_text(encoding="utf-8")

    # 必须是真实解析调用 + 真实入参传递
    assert "resolve_export_policy" in router_src
    assert "export_policy=policy" in router_src, (
        "router 必须把 policy 作为 export_policy 传入 export_bytes；"
        "只 import resolve_export_policy 而不传 = 假接线"
    )


def test_resolver_is_the_only_reader_of_project_amount_unit():
    """`projects.amount_unit` 的正式导出读取只允许出现在解析层。

    口径只有一个来源是这条设计的全部意义。若别的 service 也开始自己查这一列，
    就会出现两套换算口径（正如 `conflict_resolution` 与 `conflicts` 两份判据分叉那次）。
    """
    from pathlib import Path

    services_dir = Path(__file__).resolve().parents[1] / "app" / "services"
    allowed = {"export_unit_policy_resolver.py"}
    offenders: list[str] = []
    for p in services_dir.rglob("*.py"):
        if p.name in allowed:
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        # 只在「查 project 的 amount_unit 列」这一形态上判，避免误伤配置读写服务
        if "amount_unit" in text and "Project.amount_unit" in text:
            offenders.append(str(p.relative_to(services_dir)))

    assert offenders == [], (
        "以下 service 自行读取 Project.amount_unit 做导出口径，应改为经 "
        f"export_unit_policy_resolver: {offenders}"
    )