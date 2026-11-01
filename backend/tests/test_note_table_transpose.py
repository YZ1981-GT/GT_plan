"""跨口径转置表行列互换映射（spec note-table-structure-formula-pull-closure R14）。

判据分两层：
 ① `note_table_transpose` 纯函数：启用条件（含非空门槛、名字下限）与互换视图本身；
 ② `consol_note_standalone_reader.read_source_table` 的接入：只在正常认列失败后重试，
    成功路径一律不受影响（这是本次改动最大的风险面）。
"""
from __future__ import annotations

import pytest

from app.services.consol_note_standalone_reader import read_source_table
from app.services.note_table_transpose import MIN_NAMES, looks_transposed, transpose_view


# ─── 夹具 ────────────────────────────────────────────────────────────────────


def consol_table() -> dict:
    """合并模板：项目作行、期间作列。"""
    return {
        "name": "固定资产变动",
        "headers": ["项 目", "期末余额", "上年年末余额"],
        "rows": [
            {"label": "房屋及建筑物", "values": [None, None]},
            {"label": "机器设备", "values": [None, None]},
            {"label": "运输工具", "values": [None, None]},
        ],
    }


def standalone_transposed() -> dict:
    """单体：期间作行、项目作列（与合并正好互换）。"""
    return {
        "_tables": [{
            "name": "固定资产变动",
            "headers": ["期 间", "房屋及建筑物", "机器设备", "运输工具"],
            "rows": [
                {"label": "期末余额", "values": [1000, 2000, 300]},
                {"label": "上年年末余额", "values": [900, 1800, 250]},
            ],
        }],
    }


def standalone_same_orientation() -> dict:
    """单体与合并同口径（正常路径）。"""
    return {
        "_tables": [{
            "name": "固定资产变动",
            "headers": ["项 目", "期末余额", "上年年末余额"],
            "rows": [
                {"label": "房屋及建筑物", "values": [1000, 900]},
                {"label": "机器设备", "values": [2000, 1800]},
                {"label": "运输工具", "values": [300, 250]},
            ],
        }],
    }


# ─── ① 启用条件 ──────────────────────────────────────────────────────────────


class TestLooksTransposed:
    def test_真互换_命中(self):
        assert looks_transposed(consol_table(), standalone_transposed()["_tables"][0]) is True

    def test_同口径_不命中(self):
        assert looks_transposed(consol_table(), standalone_same_orientation()["_tables"][0]) is False

    def test_空表_不命中(self):
        """🔴 空集满足任何「⊆」：没有非空门槛时这一条会 True。"""
        assert looks_transposed(consol_table(), {"headers": [], "rows": []}) is False
        assert looks_transposed({"headers": [], "rows": []}, standalone_transposed()["_tables"][0]) is False

    def test_合并表只有行没有数据列_不命中(self):
        tbl = {"headers": ["项 目"], "rows": consol_table()["rows"]}
        assert looks_transposed(tbl, standalone_transposed()["_tables"][0]) is False

    def test_名字数量低于下限_不命中(self):
        """1×N：名字太少，巧合命中率高。"""
        assert MIN_NAMES == 2
        small_consol = {"headers": ["项 目", "期末余额"], "rows": [{"label": "机器设备", "values": [None]}]}
        small_sa = {"headers": ["期 间", "机器设备"], "rows": [{"label": "期末余额", "values": [1]}]}
        assert looks_transposed(small_consol, small_sa) is False

    def test_只差一个名字也不命中(self):
        """要求全部命中：合并多一行而单体列里没有 ⇒ 不启用（宁漏不误判）。"""
        c = consol_table()
        c["rows"].append({"label": "电子设备", "values": [None, None]})
        assert looks_transposed(c, standalone_transposed()["_tables"][0]) is False

    def test_非字典入参_不命中(self):
        assert looks_transposed(None, standalone_transposed()["_tables"][0]) is False
        assert looks_transposed(consol_table(), None) is False
        assert looks_transposed(consol_table(), [1, 2]) is False

    def test_名字按_norm_归一比较(self):
        """全角/空白差异不该挡住判定（`项 目` vs `项目`）。"""
        sa = standalone_transposed()["_tables"][0]
        sa["headers"] = ["期 间", "房屋及 建筑物", "机器设备", "运输工具"]
        assert looks_transposed(consol_table(), sa) is True

    def test_真库假阳_行名与列名同集合的对称表_不命中(self):
        """🔴 真库现场（2026-11-01 扫 10808 对，唯一命中且是假阳）：

        五、28「商誉减值测试关键假设」行名 = 列名 = {毛利率, 增长率, 折现率}
        （列头 `资产组/业务` 本该填实际资产组名）。①②同时满足但两边本来同口径，
        转置会把数据转错位 ⇒ 必须由条件 ④「角色真的对调」排除。
        """
        table = {
            "name": "商誉减值测试关键假设",
            "headers": ["资产组/业务", "毛利率", "增长率", "折现率"],
            "rows": [
                {"label": "毛利率", "values": [None, None, None]},
                {"label": "增长率", "values": [None, None, None]},
                {"label": "折现率", "values": [None, None, None]},
            ],
        }
        # 合并模板与单体实际在真库里逐字相同
        assert looks_transposed(table, dict(table)) is False

    def test_列名留在原维度_不命中(self):
        """合并的数据列名同时也是单体的列名 ⇒ 没有对调。"""
        sa = standalone_transposed()["_tables"][0]
        sa["headers"] = ["期 间", "房屋及建筑物", "机器设备", "期末余额"]
        assert looks_transposed(consol_table(), sa) is False

    def test_行名留在原维度_不命中(self):
        sa = standalone_transposed()["_tables"][0]
        sa["rows"].append({"label": "机器设备", "values": [1, 2, 3]})
        assert looks_transposed(consol_table(), sa) is False


# ─── ① 互换视图 ──────────────────────────────────────────────────────────────


class TestTransposeView:
    def test_行列互换且数值跟着走(self):
        view = transpose_view(standalone_transposed()["_tables"][0], label_header="项 目")
        assert view is not None
        assert view["headers"] == ["项 目", "期末余额", "上年年末余额"]
        assert [r["label"] for r in view["rows"]] == ["房屋及建筑物", "机器设备", "运输工具"]
        assert [r["values"] for r in view["rows"]] == [[1000, 900], [2000, 1800], [300, 250]]
        assert view["_transposed"] is True

    def test_不带出分组与多级表头(self):
        """转置后原分组语义不成立，带着会让认列按错的父表头比对。"""
        src = standalone_transposed()["_tables"][0]
        src["_column_groups"] = [{"group": "期末", "start": 1, "span": 2}]
        src["multi_header"] = [["期 间", "期末", ""], ["", "A", "B"]]
        view = transpose_view(src)
        assert "_column_groups" not in view
        assert "multi_header" not in view

    def test_缺格补_None(self):
        src = {"headers": ["期 间", "A", "B"], "rows": [{"label": "期末余额", "values": [1]}]}
        view = transpose_view(src)
        assert [r["values"] for r in view["rows"]] == [[1], [None]]

    def test_标签列列头缺省取原表(self):
        view = transpose_view(standalone_transposed()["_tables"][0])
        assert view["headers"][0] == "期间"  # norm 后（column_paths 走 norm）

    def test_空表返回_None(self):
        assert transpose_view({"headers": [], "rows": []}) is None
        assert transpose_view({"headers": ["项 目", "A"], "rows": []}) is None
        assert transpose_view(None) is None

    def test_跳过占位行(self):
        src = standalone_transposed()["_tables"][0]
        src["rows"].append({"label": "可无限量添加行", "row_type": "expandable", "values": []})
        view = transpose_view(src)
        assert view["headers"] == ["期间", "期末余额", "上年年末余额"]

    def test_列表形态的行(self):
        src = {"headers": ["期 间", "甲", "乙"], "rows": [["期末余额", 5, 6], ["上年年末余额", 7, 8]]}
        view = transpose_view(src)
        assert [r["label"] for r in view["rows"]] == ["甲", "乙"]
        assert [r["values"] for r in view["rows"]] == [[5, 7], [6, 8]]


# ─── ② 读取层接入 ────────────────────────────────────────────────────────────


class TestReaderIntegration:
    def test_转置来源能拉到数且标明认表方式(self):
        got = read_source_table(standalone_transposed(), consol_table=consol_table())
        assert got.table_choice == "transposed"
        assert got.reason is None
        assert [r["label"] for r in got.rows] == ["房屋及建筑物", "机器设备", "运输工具"]
        assert [r["values"] for r in got.rows] == [[1000, 900], [2000, 1800], [300, 250]]
        assert got.table_name == "固定资产变动"

    def test_同口径走原路径_不转置(self):
        """🔴 成功路径必须零影响：否则本来认对的表会被转置搞坏。"""
        got = read_source_table(standalone_same_orientation(), consol_table=consol_table())
        assert got.table_choice != "transposed"
        assert [r["values"] for r in got.rows] == [[1000, 900], [2000, 1800], [300, 250]]

    def test_既不同口径也不互换_保留原因不换成转置报错(self):
        other = {"_tables": [{
            "name": "完全不相干的表",
            "headers": ["科目", "金额"],
            "rows": [{"label": "银行存款", "values": [1]}, {"label": "库存现金", "values": [2]}],
        }]}
        got = read_source_table(other, consol_table=consol_table())
        assert got.table_choice != "transposed"
        assert got.reason is not None

    def test_没有合并模板表时不尝试转置(self):
        got = read_source_table(standalone_transposed(), consol_table=None)
        assert got.table_choice != "transposed"

    def test_空来源仍报原因(self):
        got = read_source_table({}, consol_table=consol_table())
        assert got.rows == []
        assert got.reason == "单体附注该章节没有表格数据"

    @pytest.mark.parametrize("label", ["房屋及建筑物", "机器设备", "运输工具"])
    def test_转置行带出同名序号与分组(self, label):
        got = read_source_table(standalone_transposed(), consol_table=consol_table())
        row = next(r for r in got.rows if r["label"] == label)
        assert row["_occurrence"] == 0
        assert "_group" in row and "_group_occurrence" in row


# ─── ② 前置门禁本身（白盒）────────────────────────────────────────────────────


class TestRetryGates:
    """`read_source_table` 在走转置重试前的两道前置门禁。

    🔴 这两道门**不是正确性判据**：`looks_transposed` 已经足够严，摘掉它们结果也不变
    （变异 M6 / M8 据此存活过一轮）。它们的作用是「成功路径零额外开销」与类型安全，
    所以只能白盒断言「门真的拦住了」——按结果断言永远测不到。
    """

    @staticmethod
    def _spy(monkeypatch):
        calls: list[tuple] = []
        import app.services.note_table_transpose as mod

        real = mod.looks_transposed

        def spy(consol, standalone):
            calls.append((consol, standalone))
            return real(consol, standalone)

        monkeypatch.setattr(mod, "looks_transposed", spy)
        return calls

    def test_正常认列成功时不跑转置判定(self, monkeypatch):
        calls = self._spy(monkeypatch)
        got = read_source_table(standalone_same_orientation(), consol_table=consol_table())
        assert got.matched_columns, "前提：这条用例必须走通正常认列，否则判据空转"
        assert calls == [], "成功路径不该为每张表再跑一次转置判定"

    def test_没有合并模板表时不跑转置判定(self, monkeypatch):
        calls = self._spy(monkeypatch)
        read_source_table(standalone_transposed(), consol_table=None)
        assert calls == []

    def test_没有合并模板表且认列也失败时不跑转置判定且不崩(self, monkeypatch):
        """转置判定与视图都要读 `consol_table`：少了类型门就会在 None 上 AttributeError。

        单体表只有标签列 ⇒ 一个数据列都认不上 ⇒ 过得了 `_may_be_transposed` 那道门，
        只剩类型门拦着（M8 变异靠这条用例才测得到）。
        """
        calls = self._spy(monkeypatch)
        only_label = {"_tables": [{
            "name": "只有行名的表",
            "headers": ["项 目"],
            "rows": [{"label": "甲", "values": []}, {"label": "乙", "values": []}],
        }]}
        got = read_source_table(only_label, consol_table=None)  # 不得抛异常
        assert got.matched_columns == []
        assert calls == []

    def test_认列失败时才跑转置判定(self, monkeypatch):
        calls = self._spy(monkeypatch)
        got = read_source_table(standalone_transposed(), consol_table=consol_table())
        assert got.table_choice == "transposed"
        assert calls, "认列失败必须触发转置判定"
