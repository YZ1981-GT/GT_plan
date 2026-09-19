"""CanonicalAddress 值对象 — ACNR 内部唯一标识 (Req-6)

frozen dataclass，纯无副作用模块（no IO, no DB, no imports beyond stdlib/dataclass）。

URI / formula_ref / index_ref / addr_id 四种语法输入收敛到同一 CanonicalAddress。
custom_flat profile（2参 WP(code,cell)）仅作边界兼容 adapter，
内部存储统一为 3参标准形态的 canonical addr_id。

FormulaReverseIndex 边端点全部使用 canonical addr_id。

Requirements: Req-6
"""
from __future__ import annotations

import re
from dataclasses import dataclass


# ─── addr_id 格式约定 ─────────────────────────────────────────────────────────
# domain=wp 时: {parent}/{sheet}/{coordinate}  (3段) 或 {parent}/{sheet} (2段)
# domain=tb/report/note/aux 时: {parent}/{sheet}/{coordinate} 或更简
# addr_id property 输出: domain 隐含在 parent/sheet/coordinate 组合中，
#   对 wp 域直接拼 parent/sheet/coordinate，对非 wp 域加前缀标识。
# 设计选择: addr_id 不含 domain 前缀（保持与现有 catalog addr_id 格式兼容），
#   domain 信息通过 CanonicalAddress 结构体保持，round-trip 解析依赖段数规则。

# ─── 公式引用正则 ──────────────────────────────────────────────────────────────
_RE_WP_3 = re.compile(
    r"WP\(\s*'([^']+)'\s*,\s*'([^']+)'\s*,\s*'([^']+)'\s*\)"
)
_RE_WP_2 = re.compile(
    r"WP\(\s*'([^']+)'\s*,\s*'([^']+)'\s*\)"
)


@dataclass(frozen=True, slots=True)
class CanonicalAddress:
    """ACNR 内部唯一标识值对象。

    Attributes:
        domain: 域标识 — 'wp' | 'tb' | 'report' | 'note' | 'aux'
        parent: 父级编码 — wp_code / account_code / report_code / note_code / aux_type
        sheet: Sheet 编码 — sheet_code / ''（无 sheet 时空字符串）
        coordinate: 坐标 — cell_address / semantic_slug / ''（无坐标时空字符串）
    """

    domain: str
    parent: str
    sheet: str
    coordinate: str

    @property
    def addr_id(self) -> str:
        """输出 canonical addr_id 字符串。

        格式（wp 域）:
            - 有 coordinate: {parent}/{sheet}/{coordinate}
            - 无 coordinate 有 sheet: {parent}/{sheet}
            - 仅 parent: {parent}

        格式（非 wp 域）:
            - 前缀: {domain}://{parent}/{sheet}/{coordinate}
            - 简化: {domain}://{parent}  (无 sheet/coordinate)
        """
        if self.domain == "wp":
            if self.coordinate:
                return f"{self.parent}/{self.sheet}/{self.coordinate}"
            elif self.sheet:
                return f"{self.parent}/{self.sheet}"
            else:
                return self.parent
        else:
            # 非 wp 域带 domain:// 前缀
            parts = [self.parent]
            if self.sheet:
                parts.append(self.sheet)
            if self.coordinate:
                parts.append(self.coordinate)
            return f"{self.domain}://{'/'.join(parts)}"

    @classmethod
    def from_addr_id(cls, s: str) -> "CanonicalAddress":
        """从 addr_id 字符串解析为 CanonicalAddress。

        支持格式:
            - wp 域: {parent}/{sheet}/{coordinate} 或 {parent}/{sheet} 或 {parent}
            - 非 wp 域: {domain}://{parent}/{sheet}/{coordinate}
        """
        if not s:
            raise ValueError("addr_id 不能为空")

        # 检测非 wp 域前缀
        for prefix in ("tb://", "report://", "note://", "aux://"):
            if s.startswith(prefix):
                domain = prefix.rstrip(":/")
                body = s[len(prefix):]
                parts = body.split("/") if body else []
                return cls(
                    domain=domain,
                    parent=parts[0] if len(parts) > 0 else "",
                    sheet=parts[1] if len(parts) > 1 else "",
                    coordinate="/".join(parts[2:]) if len(parts) > 2 else "",
                )

        # wp 域: 按 "/" 分段
        parts = s.split("/")
        if len(parts) >= 3:
            return cls(
                domain="wp",
                parent=parts[0],
                sheet=parts[1],
                coordinate="/".join(parts[2:]),
            )
        elif len(parts) == 2:
            return cls(domain="wp", parent=parts[0], sheet=parts[1], coordinate="")
        else:
            return cls(domain="wp", parent=parts[0], sheet="", coordinate="")

    @classmethod
    def from_uri(cls, uri: str) -> "CanonicalAddress":
        """从 URI 语法解析为 CanonicalAddress。

        支持格式:
            - wp://D2/明细表D2-2#E100  → domain=wp, parent=D2, sheet=明细表D2-2, coordinate=E100
            - wp://D2/D2-2#E100        → domain=wp, parent=D2, sheet=D2-2, coordinate=E100
            - wp://D2/D2-2             → domain=wp, parent=D2, sheet=D2-2, coordinate=''
            - wp://D2                   → domain=wp, parent=D2, sheet='', coordinate=''
            - tb://1001/审定数          → domain=tb, parent=1001, sheet=审定数, coordinate=''
            - report://BS-005/当期金额  → domain=report, parent=BS-005, sheet=当期金额, coordinate=''
            - note://五、3              → domain=note, parent=五、3, sheet='', coordinate=''
            - aux://consol/item         → domain=aux, parent=consol, sheet=item, coordinate=''
        """
        if not uri:
            raise ValueError("URI 不能为空")

        # 检测 schema 前缀
        if "://" not in uri:
            raise ValueError(f"无效 URI 格式（缺 scheme://）: {uri}")

        scheme, body = uri.split("://", 1)
        domain = scheme.lower()

        if domain not in ("wp", "tb", "report", "note", "aux"):
            raise ValueError(f"不支持的 URI scheme: {scheme}")

        if domain == "wp":
            # wp://parent/sheet#cell 或 wp://parent/sheet 或 wp://parent
            if "#" in body:
                path_part, cell_part = body.rsplit("#", 1)
                parts = path_part.split("/")
                return cls(
                    domain="wp",
                    parent=parts[0] if parts else "",
                    sheet=parts[1] if len(parts) > 1 else "",
                    coordinate=cell_part,
                )
            else:
                parts = body.split("/")
                return cls(
                    domain="wp",
                    parent=parts[0] if parts else "",
                    sheet=parts[1] if len(parts) > 1 else "",
                    coordinate="/".join(parts[2:]) if len(parts) > 2 else "",
                )
        else:
            # 非 wp 域: {domain}://{parent}/{sheet}/{coordinate}
            parts = body.split("/") if body else []
            return cls(
                domain=domain,
                parent=parts[0] if len(parts) > 0 else "",
                sheet=parts[1] if len(parts) > 1 else "",
                coordinate="/".join(parts[2:]) if len(parts) > 2 else "",
            )

    @classmethod
    def from_formula_ref(cls, formula_ref: str) -> "CanonicalAddress":
        """从公式引用语法解析为 CanonicalAddress。

        支持格式:
            - WP('D2','明细表D2-2','E100')     → 3参标准: parent=D2, sheet=明细表D2-2, coordinate=E100
            - WP('D2','D2-2','E100')           → 3参标准: parent=D2, sheet=D2-2, coordinate=E100
            - WP('CUST-01','B7')               → 2参 custom_flat: parent=CUST-01, sheet=CUST-01, coordinate=B7
              (内部统一为3参标准形态: sheet=parent)

        custom_flat profile（2参）仅作边界兼容 adapter，
        内部存储统一为 3参标准形态的 canonical addr_id。
        """
        if not formula_ref:
            raise ValueError("formula_ref 不能为空")

        # 尝试 3 参匹配
        m3 = _RE_WP_3.search(formula_ref)
        if m3:
            parent, sheet, coordinate = m3.group(1), m3.group(2), m3.group(3)
            return cls(domain="wp", parent=parent, sheet=sheet, coordinate=coordinate)

        # 尝试 2 参匹配 (custom_flat → 内部统一为 3 参)
        m2 = _RE_WP_2.search(formula_ref)
        if m2:
            first, second = m2.group(1), m2.group(2)
            # custom_flat: WP(wp_code, cell) → parent=wp_code, sheet=wp_code, coordinate=cell
            return cls(domain="wp", parent=first, sheet=first, coordinate=second)

        raise ValueError(f"无法解析 formula_ref: {formula_ref}")

    @classmethod
    def from_index_ref(cls, index_ref: str) -> "CanonicalAddress":
        """从索引命名空间语法解析为 CanonicalAddress。

        支持格式:
            - cell:D2-2!E100   → domain=wp, parent=D2-2的parent, sheet=D2-2, coordinate=E100
            - wp:D2-2          → domain=wp, parent=推导, sheet=D2-2, coordinate=''
            - sheet:D2-2       → 同 wp:D2-2
            - tb:1001          → domain=tb, parent=1001, sheet='', coordinate=''
            - note:五、3        → domain=note, parent=五、3, sheet='', coordinate=''

        注意: cell/wp/sheet 命名空间需要推导 parent_wp_code。
        对于无法推导的情况，parent 取 sheet_code 的基础码（去掉后缀数字）。
        """
        if not index_ref or ":" not in index_ref:
            raise ValueError(f"无效 index_ref 格式: {index_ref}")

        ns, target = index_ref.split(":", 1)
        ns_lower = ns.lower()

        if ns_lower == "cell":
            # cell:D2-2!E100
            if "!" in target:
                sheet_code, cell = target.split("!", 1)
                parent = _infer_parent_wp_code(sheet_code)
                return cls(domain="wp", parent=parent, sheet=sheet_code, coordinate=cell)
            else:
                raise ValueError(f"cell: 命名空间缺少 '!' 分隔符: {index_ref}")

        elif ns_lower in ("wp", "sheet"):
            # wp:D2-2 / sheet:D2-2
            sheet_code = target
            parent = _infer_parent_wp_code(sheet_code)
            return cls(domain="wp", parent=parent, sheet=sheet_code, coordinate="")

        elif ns_lower == "tb":
            return cls(domain="tb", parent=target, sheet="", coordinate="")

        elif ns_lower == "note":
            return cls(domain="note", parent=target, sheet="", coordinate="")

        elif ns_lower == "report":
            return cls(domain="report", parent=target, sheet="", coordinate="")

        elif ns_lower == "aux":
            return cls(domain="aux", parent=target, sheet="", coordinate="")

        else:
            # 其他命名空间（adj/att/eqcr/calc/sample/confirm）→ 归入 aux
            return cls(domain="aux", parent=target, sheet=ns_lower, coordinate="")


# ─── Helper ──────────────────────────────────────────────────────────────────

# 从 sheet_code 推导 parent_wp_code:
# D2-2 → D2, H1-13 → H1, K10 → K10, D2-2A → D2
_RE_PARENT_WP_CODE = re.compile(r"^([A-Z]\d+)")


def _infer_parent_wp_code(sheet_code: str) -> str:
    """从 sheet_code 推导 parent_wp_code。

    规则: 取前缀字母+数字部分（去掉 -N 后缀）。
    例: D2-2 → D2, H1-13 → H1, K10 → K10, D2-2A → D2
    """
    m = _RE_PARENT_WP_CODE.match(sheet_code)
    if m:
        return m.group(1)
    return sheet_code
