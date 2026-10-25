"""test_adj_single_source_guard.py — P4 守卫：禁第二份 ADJ 净额取数实现.

spec: adj-formula-repair-and-approval-gate-wiring · 阶段 2 任务 2.6
属性 P4 · P12

验证：除 adjustment_amount_source.py 和 trial_balance_service.py（批量路径）外，
不得有直接构建「从 adjustment_entries 查 SUM(debit-credit) 净额」SQL 的第二份实现。

注意区分：
- ✅ 借贷平衡验证（|sum(debits)-sum(credits)| < 0.01）—— 不是净额取数
- ✅ 底稿内的 debit/credit 列计算 —— 不涉及 adjustments 表聚合
- ❌ JOIN adjustments 做 SUM 聚合按科目取净额 —— 这是要收敛到 adj_net 的模式
"""
from __future__ import annotations

import re
from pathlib import Path


_BACKEND = Path(__file__).resolve().parents[1]
_APP = _BACKEND / "app"

# 授权文件白名单（允许直接操作 adjustment 表做聚合的模块）
_AUTHORIZED_MODULES = {
    "adjustment_amount_source.py",   # 单一取数函数（本 spec 新建）
    "trial_balance_service.py",       # 批量路径（保留 SQL 形态，口径已对齐）
}


def _find_raw_sql_adj_net_queries() -> list[tuple[str, int, str]]:
    """扫描 app/ 下使用裸 SQL 查 adjustment_entries 净额的文件。

    特征：sa.text(...) 内同时包含 adjustment_entries 和 debit_amount - credit_amount。
    """
    hits = []
    pattern = re.compile(r"adjustment_entries.*debit.*credit|credit.*debit.*adjustment_entries", re.IGNORECASE | re.DOTALL)

    for fp in _APP.rglob("*.py"):
        if fp.name in _AUTHORIZED_MODULES:
            continue
        if "__pycache__" in str(fp):
            continue
        try:
            text = fp.read_text(encoding="utf-8")
        except Exception:
            continue

        # 查找 sa.text() 块内的裸 SQL
        for m in re.finditer(r'sa\.text\(\s*"""(.*?)"""\s*\)', text, re.DOTALL):
            sql_block = m.group(1)
            if pattern.search(sql_block):
                # 找出行号
                start = m.start()
                lineno = text[:start].count("\n") + 1
                hits.append((str(fp.relative_to(_BACKEND)), lineno, sql_block[:80].strip()))

    return hits


class TestAdjSingleSourceGuard:
    """P4：全仓除授权模块外不得有第二份 ADJ 净额裸 SQL 实现。"""

    def test_no_raw_sql_adj_net_outside_authorized(self):
        """扫描 app/ 下非授权模块，不得有裸 SQL 查 adjustment_entries 净额。

        wp_cross_check_service 原先有一份裸 SQL 实现，任务 2.3 已改调 adj_net。
        若有人重新引入裸 SQL 取数，此守卫打红。
        """
        hits = _find_raw_sql_adj_net_queries()
        assert not hits, (
            f"P4 违规：以下 {len(hits)} 处在授权模块外使用裸 SQL 查 adjustment_entries 净额：\n"
            + "\n".join(f"  {p}:{ln}: {c}" for p, ln, c in hits[:10])
        )

    def test_authorized_module_has_adj_net(self):
        """P12 正样本：adj_net 函数在授权模块中存在。"""
        from app.services.adjustment_amount_source import adj_net
        import inspect
        assert inspect.iscoroutinefunction(adj_net)

    def test_cross_check_no_longer_has_raw_sql(self):
        """验证 wp_cross_check_service._get_adj_value 不再含裸 SQL。

        复盘修正：原断言是三元表达式 `(A or B) if C else True`，只检查**第一个**
        sa.text 块（该文件另有 trial_balance 的裸 SQL 在前），若 ADJ 裸 SQL 出现在
        第二个块之后就抓不到。现改为逐块遍历。
        """
        fp = _APP / "services" / "wp_cross_check_service.py"
        text = fp.read_text(encoding="utf-8")

        offending = [
            block[:80].strip()
            for block in re.findall(r'sa\.text\(\s*"""(.*?)"""\s*\)', text, re.DOTALL)
            if "adjustment_entries" in block
        ]
        assert not offending, (
            f"wp_cross_check_service 仍有 {len(offending)} 处裸 SQL 查 adjustment_entries：\n"
            + "\n".join(f"  {o}" for o in offending)
        )

    def test_cross_check_guard_is_not_vacuous(self):
        """P12：上一测试的扫描器非空转——对含目标串的样本必须命中。"""
        sample = 'x = sa.text("""SELECT 1 FROM adjustment_entries ae""")\n'
        hits = [
            b for b in re.findall(r'sa\.text\(\s*"""(.*?)"""\s*\)', sample, re.DOTALL)
            if "adjustment_entries" in b
        ]
        assert len(hits) == 1, "扫描器对正样本未命中 ⇒ 上一测试是恒绿的"
