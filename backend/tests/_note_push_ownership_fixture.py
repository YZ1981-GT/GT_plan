"""test_formula_push_note_skip 的归属矩阵夹具（伴生模块）。

S3（formula-writer-ownership-and-stale）起公式推送只写归属矩阵声明的格：
本文件用例自造的章节 / 表名不在真实矩阵里 ⇒ 一律 blocked。那些用例考的是
「合计重算 / 兜底 / 章节定位」等推送语义，归属判定本身由
``tests/formula_writer_ownership/`` 覆盖，故这里提供一份放行自造格的矩阵。
"""
from __future__ import annotations

#: 用例自造章节（真实归属矩阵里没有）
SELF_MADE_CHAPTERS = ("五、22", "八、64", "八、9", "八、42", "五、62", "八、999")
#: 用例自造表名
SELF_MADE_TABLES = ("应交税费", "营业收入和营业成本", "营业收入、营业成本", "其他应收款", "其他应付款",
                    "递延所得税负债", "固定资产", "短期借款")
#: 推送在这些表上写的列
SELF_MADE_COLUMNS = ("end_amount", "prior_amount")


def self_made_matrix():
    """放行全部自造表 / 章节的矩阵（推送是这些格的唯一写方）。"""
    from app.services.note_write_ownership import (
        ANY_TABLE,
        CELL_PREFIX,
        MatrixEntry,
        OwnershipMatrix,
        PUSH_WRITER,
    )

    entries = {(ANY_TABLE, "*"): MatrixEntry(PUSH_WRITER)}
    entries.update({(table, CELL_PREFIX + col): MatrixEntry(PUSH_WRITER)
                    for table in SELF_MADE_TABLES for col in SELF_MADE_COLUMNS})
    return OwnershipMatrix(
        chapters={(tt, sec): entries for tt in ("soe", "listed") for sec in SELF_MADE_CHAPTERS},
        identity={"formula_push": PUSH_WRITER},
    )


def install(monkeypatch) -> None:
    import app.services.note_write_ownership as own

    monkeypatch.setattr(own, "load_matrix", lambda path=None: self_made_matrix())
