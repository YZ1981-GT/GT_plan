"""QC-19/20/24 门禁规则的 schema 契约守卫。

**为什么需要**：这三条规则原本引用的列在真库**全都不存在**
（`procedure_instances.name` / `working_paper_id` / `trim_category` /
`trim_status` / `trim_evidence_refs`），每次调用抛 `UndefinedColumnError`
被规则自身的 `except Exception` 吞掉后 `return None`。而 `return None` 在
`gate_engine` 里的含义是**「检查通过」** ⇒ 这三条 blocking 门禁自上线起
从未拦下过任何违规。

这是最危险的一类缺陷：安全门禁静默失效，日志里只有 error、
调用方看到的是"通过"，任何黑盒测试都发现不了。

裁剪状态的真实落库位置是 `workpaper_procedures`
（见 `services/wp_procedure_service.py` 的 trim：置 `status='not_applicable'`
+ `trimmed_by` + `trimmed_at` + `trim_reason`）。

本守卫**不连库**，静态校验两件事：
  1. 这三条规则的 SQL 不得再引用那批不存在的列；
  2. 它们必须查 `workpaper_procedures`（真实落库表）。
连库的行为判据（能拦下违规 / 不误报）见 pg 段测试。

**Validates**: QC-19 / QC-20 / QC-24 门禁有效性
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
TARGET = REPO_ROOT / "backend" / "app" / "services" / "gate_rules_phase14.py"

# 真库中**不存在**的列（原实现引用的），一旦重新出现即回归
PHANTOM_COLUMNS = [
    "trim_category",
    "trim_status",
    "trim_evidence_refs",
    "working_paper_id",
]

# 这三条规则必须查的真实表
REQUIRED_TABLE = "workpaper_procedures"
RULES_UNDER_GUARD = ["QC19MandatoryTrimRule", "QC20ConditionalNoEvidenceRule",
                     "QC24LLMTrimConflictRule"]


def _source() -> str:
    return TARGET.read_text(encoding="utf-8")


def _sql_only(src: str) -> str:
    """只取 text(...) 里的 SQL，避免把解释性注释里的列名当成代码引用。

    注释里**故意**写了这些 phantom 列名（说明历史缺陷），若不剥离注释，
    本守卫会对自己的说明文字打红 —— 那是假红。
    """
    blocks: list[str] = []
    for m in re.finditer(r'text\(\s*"""(.*?)"""', src, re.DOTALL):
        blocks.append(m.group(1))
    for m in re.finditer(r'text\(\s*((?:"(?:[^"\\]|\\.)*"\s*)+)\)', src, re.DOTALL):
        blocks.append(m.group(1))
    return "\n".join(blocks)


def test_no_phantom_trim_columns_in_sql():
    """三条规则的 SQL 不得再引用真库不存在的 trim 列。"""
    sql = _sql_only(_source())
    offenders = [c for c in PHANTOM_COLUMNS if re.search(rf"\b{c}\b", sql)]
    assert not offenders, (
        f"gate_rules_phase14.py 的 SQL 又引用了真库不存在的列：{offenders}\n"
        "这些列在 procedure_instances 上从不存在，会抛 UndefinedColumnError 并被\n"
        "规则的 except 吞成 return None（= 门禁通过）⇒ blocking 规则静默失效。\n"
        f"裁剪状态请查 {REQUIRED_TABLE}"
        "（is_mandatory / trimmed_at / trim_reason）。"
    )


def test_rules_query_real_trim_table():
    """三条规则必须查 workpaper_procedures（裁剪状态的真实落库表）。"""
    sql = _sql_only(_source())
    # 🔴 用词边界而不是 `in`：子串匹配下 `workpaper_procedures_XX` 也会命中
    #    `workpaper_procedures`，把表名改错反而照样通过（变异检验 M3 实测抓到）。
    assert re.search(rf"\b{REQUIRED_TABLE}\b(?!_)", sql), (
        f"未发现对 {REQUIRED_TABLE} 的查询 —— QC-19/20/24 的裁剪判据必须落在该表上。"
    )


@pytest.mark.parametrize("rule_cls", RULES_UNDER_GUARD)
def test_rule_logs_error_with_traceback(rule_cls: str):
    """三条规则的 except 分支必须带 exc_info=True。

    原实现只 `logger.error(f"...{e}")`，丢掉 traceback ⇒ 「列不存在」这类
    接线错误在日志里只剩一行摘要，排查时无法定位是哪条 SQL 的哪一列。
    本守卫要求保留堆栈，让静默失效至少在日志层面可追。
    """
    src = _source()
    idx = src.find(f"class {rule_cls}")
    assert idx != -1, f"未找到规则类 {rule_cls}"
    # 取该类到下一个 class 之间的片段
    nxt = src.find("\nclass ", idx + 1)
    body = src[idx: nxt if nxt != -1 else len(src)]
    assert "except Exception" in body, f"{rule_cls} 应保留 except（单规则失败不阻断整体评估）"
    assert "exc_info=True" in body, (
        f"{rule_cls} 的 except 分支缺 exc_info=True —— "
        "静默失效正是靠丢弃 traceback 长期隐形的。"
    )


def test_guard_sees_actual_sql():
    """反向自检：SQL 提取必须真取到内容，否则上面几条会变成永真。"""
    sql = _sql_only(_source())
    assert len(sql) > 500, f"仅提取到 {len(sql)} 字符 SQL —— 提取逻辑疑似失效"
    assert "SELECT" in sql.upper(), "提取结果里没有 SELECT —— 提取逻辑疑似失效"
