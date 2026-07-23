"""B50 风险评估读取器 — 从 checklist_responses 重建认定层次风险结构。

统一 B50 → D~N / A17-1 / A17-6 / 程序表 的数据口径。

B50 专属组件（GtB50RiskAssessment.vue）把风险评估写入 checklist_responses，
item_id 采用如下前缀：
  - B50-T3-accounts                          科目清单（JSON 数组）
  - B50-T3-matrix-{account}-{assertion}-RMM  综合风险等级（conclusion=H/M/L）
  - B50-T3-matrix-{account}-{assertion}-IR    固有风险
  - B50-T3-matrix-{account}-{assertion}-CR    控制风险
  - B50-T3-matrix-{account}-{assertion}-SR    特别风险（conclusion=Y）
  - B50-T3-cycle-{account}                    相关业务循环（conclusion=D~N 字母代号）
  - B50-T3-plan-{account}-{reliance|subonly|approach}  应对方案（行级）
  - B50-T2-fs-{i}-{level|desc|...}            财务报表层次风险

历史上 risk_for_cycle / b50_risk_summary / a176 议程从 field_override_service
（scope='risk_assessment'）读取，但 B50 组件从不写入该表 → 联动恒空。本模块从
checklist_responses 这一单一真源重建结构，供全部下游消费者统一调用。
"""
from __future__ import annotations

import logging
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

_logger = logging.getLogger(__name__)

ASSERTION_CN: dict[str, str] = {
    "existence": "存在",
    "completeness": "完整性",
    "accuracy": "准确性",
    "cutoff": "截止",
    "classification": "分类",
    "presentation": "列报",
}
LEVEL_CN: dict[str, str] = {"H": "高", "M": "中", "L": "低"}
_LEVEL_ORDER = {"H": 3, "M": 2, "L": 1}
_ASSERTION_SUFFIXES = ("RMM", "IR", "CR", "SR")


async def _find_b50_wp_id(db: AsyncSession, project_id: UUID) -> str | None:
    """定位项目 B50 底稿 wp_id。"""
    try:
        row = await db.execute(
            sa.text(
                "SELECT wp.id FROM working_paper wp "
                "JOIN wp_index wi ON wp.wp_index_id = wi.id "
                "WHERE wp.project_id = :pid AND wi.wp_code = 'B50' "
                "LIMIT 1"
            ),
            {"pid": str(project_id)},
        )
        return row.scalar_one_or_none()
    except Exception as e:  # noqa: BLE001
        _logger.warning("B50 wp_id 查询失败 project=%s: %s", project_id, e)
        return None


def _parse_matrix_item_id(item_id: str) -> tuple[str, str, str] | None:
    """解析 B50-T3-matrix-{account}-{assertion}-{suffix} → (account, assertion, suffix)。"""
    body = item_id.removeprefix("B50-T3-matrix-")
    if body == item_id:
        return None
    # suffix 是最后一段
    last_dash = body.rfind("-")
    if last_dash <= 0:
        return None
    suffix = body[last_dash + 1:]
    if suffix not in _ASSERTION_SUFFIXES:
        return None
    rest = body[:last_dash]
    # assertion 是 rest 的最后一段
    ass_dash = rest.rfind("-")
    if ass_dash <= 0:
        return None
    assertion = rest[ass_dash + 1:]
    account = rest[:ass_dash]
    if not account or assertion not in ASSERTION_CN:
        return None
    return account, assertion, suffix


async def load_b50_accounts(db: AsyncSession, project_id: UUID) -> list[dict]:
    """从 checklist_responses 重建 B50 认定层次风险（按科目聚合）。

    返回 list[dict]，每项：
      {
        "account": str,
        "cycle": str|None,             # D~N 字母代号 / 'pervasive'
        "reliance": str|None,
        "substantive_only": str|None,  # 'Y'/'N'
        "approach": str|None,          # 'substantive'/'combined'
        "cells": {assertion: {"rmm": 'H'|'M'|'L'|None, "special": bool}},
        "max_risk": 'H'|'M'|'L'|None,
        "has_special": bool,
      }
    """
    b50_wp = await _find_b50_wp_id(db, project_id)
    if not b50_wp:
        return []
    try:
        res = await db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark FROM checklist_responses "
                "WHERE wp_id = :wp AND item_id LIKE 'B50-T3-%'"
            ),
            {"wp": str(b50_wp)},
        )
        rows = res.fetchall()
    except Exception as e:  # noqa: BLE001
        _logger.warning("B50 checklist_responses 查询失败 project=%s: %s", project_id, e)
        return []
    if not rows:
        return []

    accounts: dict[str, dict] = {}

    def _ensure(name: str) -> dict:
        if name not in accounts:
            accounts[name] = {
                "account": name,
                "cycle": None,
                "reliance": None,
                "substantive_only": None,
                "approach": None,
                "cells": {},
            }
        return accounts[name]

    for r in rows:
        item_id = r.item_id
        conclusion = r.conclusion
        # cycle
        if item_id.startswith("B50-T3-cycle-"):
            name = item_id.removeprefix("B50-T3-cycle-")
            if name:
                _ensure(name)["cycle"] = conclusion or None
            continue
        # plan-{account}-{field}
        if item_id.startswith("B50-T3-plan-"):
            body = item_id.removeprefix("B50-T3-plan-")
            fdash = body.rfind("-")
            if fdash > 0:
                name = body[:fdash]
                field = body[fdash + 1:]
                acc = _ensure(name)
                if field == "reliance":
                    acc["reliance"] = conclusion or None
                elif field == "subonly":
                    acc["substantive_only"] = conclusion or None
                elif field == "approach":
                    acc["approach"] = conclusion or None
            continue
        # matrix cell
        parsed = _parse_matrix_item_id(item_id)
        if parsed:
            account, assertion, suffix = parsed
            acc = _ensure(account)
            cell = acc["cells"].setdefault(assertion, {"rmm": None, "special": False})
            if suffix == "RMM":
                cell["rmm"] = conclusion or None
            elif suffix == "SR":
                cell["special"] = (conclusion == "Y")
            continue

    # 派生 max_risk / has_special
    result: list[dict] = []
    for acc in accounts.values():
        max_lvl: str | None = None
        has_special = False
        for cell in acc["cells"].values():
            lvl = cell.get("rmm")
            if lvl and (max_lvl is None or _LEVEL_ORDER.get(lvl, 0) > _LEVEL_ORDER.get(max_lvl, 0)):
                max_lvl = lvl
            if cell.get("special"):
                has_special = True
        # 管理层凌驾控制永远是特别风险
        if acc["account"] == "管理层凌驾控制":
            has_special = True
        acc["max_risk"] = max_lvl
        acc["has_special"] = has_special
        result.append(acc)
    return result


async def load_b50_risks(db: AsyncSession, project_id: UUID) -> list[dict]:
    """展平为认定层次风险清单（每个已评估/特别风险的单元格一项）。

    返回 list[dict]，每项：
      {risk_id, account, assertion, assertion_cn, risk_level, is_special_risk, cycle, description}
    """
    accounts = await load_b50_accounts(db, project_id)
    risks: list[dict] = []
    for acc in accounts:
        name = acc["account"]
        cycle = acc["cycle"]
        for assertion, cell in acc["cells"].items():
            rmm = cell.get("rmm")
            special = cell.get("special") or (name == "管理层凌驾控制")
            if not rmm and not special:
                continue
            assertion_cn = ASSERTION_CN.get(assertion, assertion)
            level_cn = LEVEL_CN.get(rmm or "", rmm or "")
            desc = f"{name} - {assertion_cn}认定"
            if rmm:
                desc = f"【{level_cn}风险】" + desc
            if special:
                desc += "（特别风险）"
            risks.append({
                "risk_id": f"{name}-{assertion}",
                "account": name,
                "assertion": assertion,
                "assertion_cn": assertion_cn,
                "risk_level": rmm or "",
                "is_special_risk": special,
                "cycle": cycle,
                "description": desc,
            })
    return risks


# ─── 科目 → 业务循环 启发式映射（B50-3 确定审计范围预填用）──────────────────
# 按 account_name 关键词匹配（比科目编码前缀更稳健，PRC 编码常有歧义）。
# 顺序敏感：更具体的关键词在前。返回 D~N 字母码，无匹配返回 ''（由审计师手选）。
_CYCLE_KEYWORDS: list[tuple[str, str]] = [
    # E 货币资金
    ("货币资金", "E"), ("库存现金", "E"), ("银行存款", "E"), ("其他货币资金", "E"),
    ("存放中央银行", "E"),
    # K 其他往来/损益（须在 D/F 应收应付之前，避免"其他应收款"被误判）
    ("其他应收款", "K"), ("其他应付款", "K"), ("其他流动资产", "K"), ("其他流动负债", "K"),
    ("销售费用", "K"), ("管理费用", "K"), ("其他收益", "K"), ("营业外收入", "K"),
    ("营业外支出", "K"), ("资产减值损失", "K"), ("信用减值损失", "K"),
    # G 投资（应收股利/利息归投资循环，须在 D 应收之前）
    ("交易性金融资产", "G"), ("债权投资", "G"), ("其他债权投资", "G"), ("长期股权投资", "G"),
    ("其他权益工具投资", "G"), ("其他非流动金融资产", "G"), ("应收股利", "G"), ("应收利息", "G"),
    ("投资收益", "G"), ("公允价值变动", "G"),
    # D 收入与应收
    ("应收票据", "D"), ("应收账款", "D"), ("应收款项融资", "D"), ("合同资产", "D"),
    ("预收", "D"), ("合同负债", "D"), ("营业收入", "D"), ("主营业务收入", "D"), ("其他业务收入", "D"),
    # F 采购、存货与应付
    ("预付", "F"), ("存货", "F"), ("原材料", "F"), ("库存商品", "F"), ("在产品", "F"),
    ("发出商品", "F"), ("委托加工", "F"), ("周转材料", "F"), ("消耗性生物资产", "F"),
    ("应付票据", "F"), ("应付账款", "F"), ("营业成本", "F"), ("主营业务成本", "F"),
    # H 固定资产与在建
    ("固定资产", "H"), ("在建工程", "H"), ("工程物资", "H"), ("投资性房地产", "H"),
    ("生产性生物资产", "H"), ("油气资产", "H"),
    # I 无形资产及其他长期资产
    ("无形资产", "I"), ("开发支出", "I"), ("商誉", "I"), ("长期待摊费用", "I"), ("使用权资产", "I"),
    # J 职工薪酬
    ("职工薪酬", "J"),
    # L 借款与债务
    ("短期借款", "L"), ("长期借款", "L"), ("应付债券", "L"), ("租赁负债", "L"), ("财务费用", "L"),
    ("拆入资金", "L"), ("向中央银行借款", "L"),
    # M 所有者权益
    ("实收资本", "M"), ("股本", "M"), ("资本公积", "M"), ("盈余公积", "M"),
    ("未分配利润", "M"), ("库存股", "M"), ("其他综合收益", "M"), ("专项储备", "M"),
    ("一般风险准备", "M"),
    # N 税金
    ("应交税费", "N"), ("递延所得税", "N"), ("所得税费用", "N"), ("税金及附加", "N"),
]


def cycle_for_account(name: str, code: str = "") -> str:
    """按科目名称关键词启发式映射业务循环代号（D~N）；无匹配返回 ''。"""
    n = (name or "").strip()
    if not n:
        return ""
    for kw, cyc in _CYCLE_KEYWORDS:
        if kw in n:
            return cyc
    return ""


async def load_b50_fs_risks(db: AsyncSession, project_id: UUID) -> list[dict]:
    """读取 B50-2 财务报表层次风险（Tab2）。

    返回 list[dict]：{seq, description, is_special, level, refindex, b60ref}
    """
    b50_wp = await _find_b50_wp_id(db, project_id)
    if not b50_wp:
        return []
    try:
        res = await db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark FROM checklist_responses "
                "WHERE wp_id = :wp AND item_id LIKE 'B50-T2-%'"
            ),
            {"wp": str(b50_wp)},
        )
        by_id = {r.item_id: r for r in res.fetchall()}
    except Exception as e:  # noqa: BLE001
        _logger.warning("B50-T2 查询失败 project=%s: %s", project_id, e)
        return []
    count_row = by_id.get("B50-T2-count")
    try:
        count = int((count_row.remark if count_row else "0") or 0)
    except (TypeError, ValueError):
        count = 0
    out: list[dict] = []
    for i in range(count):
        desc = (by_id.get(f"B50-T2-fs-{i}-desc").remark if by_id.get(f"B50-T2-fs-{i}-desc") else "") or ""
        desc = desc.strip()
        if not desc:
            continue
        special = by_id.get(f"B50-T2-fs-{i}-special")
        level = by_id.get(f"B50-T2-fs-{i}-level")
        refindex = by_id.get(f"B50-T2-fs-{i}-refindex")
        b60ref = by_id.get(f"B50-T2-fs-{i}-b60ref")
        out.append({
            "seq": i + 1,
            "description": desc,
            "is_special": (special.conclusion == "Y") if special else False,
            "level": (level.conclusion if level else "") or "",
            "refindex": (refindex.remark if refindex else "") or "",
            "b60ref": (b60ref.remark if b60ref else "") or "",
        })
    return out


async def format_b50_summary_text(db: AsyncSession, project_id: UUID) -> str:
    """把 B50 风险评估格式化为可读文本，供 B60 总体策略章节拉取。

    结构：一、财务报表层次风险；二、认定层次风险（高/中）；三、特别风险（须细节测试）。
    """
    fs_risks = await load_b50_fs_risks(db, project_id)
    assertion_risks = await load_b50_risks(db, project_id)

    parts: list[str] = []

    if fs_risks:
        lines = ["一、财务报表层次重大错报风险："]
        for r in fs_risks:
            tag = "【特别风险】" if r["is_special"] else ""
            ref = f"（相关索引：{r['refindex']}）" if r["refindex"] else ""
            lines.append(f"{r['seq']}. {tag}{r['description']}{ref}")
        parts.append("\n".join(lines))

    high_mid = [r for r in assertion_risks if r["risk_level"] in ("H", "M") and not r["is_special_risk"]]
    if high_mid:
        lines = ["二、认定层次重大错报风险（高/中）："]
        for idx, r in enumerate(high_mid, 1):
            cyc = f"[循环{r['cycle']}]" if r.get("cycle") else ""
            lines.append(f"{idx}. {r['description']}{cyc}")
        parts.append("\n".join(lines))

    specials = [r for r in assertion_risks if r["is_special_risk"]]
    if specials:
        lines = ["三、特别风险（须以细节测试等实质性程序应对，不得仅用分析程序）："]
        for idx, r in enumerate(specials, 1):
            cyc = f"[循环{r['cycle']}]" if r.get("cycle") else ""
            lines.append(f"{idx}. {r['description']}{cyc}")
        parts.append("\n".join(lines))

    return "\n\n".join(parts)


def cycle_matches(risk_cycle: str | None, target: str | None) -> bool:
    """判断风险的 cycle 是否匹配目标循环代号（大小写不敏感，首字母对齐）。"""
    if not target:
        return True  # 未指定目标 → 全部匹配
    if not risk_cycle:
        return False
    rc = str(risk_cycle).strip().upper()
    tg = str(target).strip().upper()
    if rc == tg:
        return True
    # 目标可能是完整 table_code（如 'D2A'）→ 取首字母
    if tg and tg[0] == rc:
        return True
    return False
