"""`check_file_size.py` 门禁不可被静默绕过的守卫。

起因（spec workpaper-sync-adopt-overwrite-and-refresh-source 复盘）：该门禁曾有**两层**
静默放行，叠加起来使「传错路径」和「文件读不出来」都表现为 **exit=0 通过** ——
一个 **1055 行**的文件因此被报成合规。两层分别是：

1. `main()` 里 `if not f.exists(): continue` —— **显式传入**的路径不存在时静默跳过；
   而相对路径按**仓库根**解析，故在 `cwd=backend` 下传 `tests/…` 必然拼不到文件。
2. `count_lines()` 的 `except Exception: return 0` —— 读不出来当 0 行，`0 > limit` 恒假。

本文件逐层钉死，并对每条判据配**变异证明**（把修复回退掉必须打红）。
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _ROOT / "backend" / "scripts" / "check" / "check_file_size.py"


def _load():
    """按文件路径加载该脚本（它不是包的一部分）。"""
    spec = importlib.util.spec_from_file_location("_cfs_under_test", _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


C = _load()


class TestExplicitMissingPathIsAnError:
    """层 1：显式传入的路径不存在 ⇒ 必须报错，不得静默通过。"""

    def test_nonexistent_file_exits_nonzero(self) -> None:
        code = C.main(["backend/tests/__this_file_does_not_exist__.py"])
        assert code != 0, (
            "传一个不存在的文件竟然 exit=0 —— 这正是历史缺陷：拼错路径被当成检查通过"
        )

    def test_backend_relative_path_is_rejected_not_silently_passed(self) -> None:
        """🔴 最常见踩法：在 backend/ 目录下传 `tests/...`，会拼成 <repo>/tests/... 而不存在。"""
        code = C.main(["tests/workpaper_sync/test_aos_row_reader_r3.py"])
        assert code != 0, (
            "backend 相对路径解析不到文件却 exit=0 —— 门禁被静默绕过"
        )

    def test_the_same_file_passes_with_a_repo_root_relative_path(self) -> None:
        """反向对照：同一个文件用**仓库根**相对路径传入 ⇒ 正常检查且通过。

        没有这一条，上面两条可能只是在证明「main() 对什么都报错」。
        """
        code = C.main(["backend/tests/workpaper_sync/test_aos_row_reader_r3.py"])
        assert code == 0, "仓库根相对路径的合规文件应当通过"


class TestUnreadableIsNotTreatedAsZeroLines:
    """层 2：读不出来 ⇒ 违规，不得当 0 行通过，也不得抛 traceback。"""

    def test_count_lines_raises_instead_of_returning_zero(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.py"
        bad.write_bytes(b"\xff\xfe\x00\x01 not utf-8 \xff")
        with pytest.raises(UnicodeDecodeError):
            C.count_lines(bad)

    def test_count_lines_or_none_is_the_tolerant_variant(self, tmp_path: Path) -> None:
        """批量扫描用的容错版返回 None（而不是 0）⇒ 调用方能区分「读不出来」与「空文件」。"""
        bad = tmp_path / "bad.py"
        bad.write_bytes(b"\xff\xfe\x00\x01")
        assert C.count_lines_or_none(bad) is None
        good = tmp_path / "good.py"
        good.write_text("a = 1\n", encoding="utf-8")
        assert C.count_lines_or_none(good) == 1

    def test_empty_file_is_zero_not_none(self, tmp_path: Path) -> None:
        """🔴 「0 行」与「读不出来」必须可区分 —— 否则又回到用 0 冒充失败的老路。"""
        empty = tmp_path / "empty.py"
        empty.write_text("", encoding="utf-8")
        assert C.count_lines(empty) == 0
        assert C.count_lines_or_none(empty) == 0

    def test_check_file_reports_unreadable_as_a_violation(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.py"
        bad.write_bytes(b"\xff\xfe\x00\x01")
        code, msg = C.check_file("backend/x/bad.py", bad, {})
        assert code == 1 and "读取失败" in msg, (code, msg)


class TestTheGateStillDoesItsRealJob:
    """反空转：修完之后它**仍然**是个会拦超限文件的门禁，不是只会报路径错。"""

    def test_oversize_file_is_still_caught(self, tmp_path: Path) -> None:
        big = tmp_path / "big.py"
        big.write_text("x = 1\n" * 900, encoding="utf-8")
        code, msg = C.check_file("backend/x/big.py", big, {})
        assert code == 1 and "超限" in msg, (code, msg)

    def test_small_file_passes(self, tmp_path: Path) -> None:
        small = tmp_path / "small.py"
        small.write_text("x = 1\n" * 10, encoding="utf-8")
        code, msg = C.check_file("backend/x/small.py", small, {})
        assert code == 0 and msg == "", (code, msg)

    def test_limits_table_is_non_empty(self) -> None:
        """分母非空：LIMITS 空了的话上面所有判据都在空集上恒真。"""
        assert C.LIMITS.get(".py") and C.LIMITS.get(".vue")
