"""``resync_data_line_anchors.py`` 的判据（spec formula-fetch-followup-defect-closure 7.1）。

为什么需要这个工具：R1.4 改了 M / J / K / L 循环前端 25 个文件，数据文件里 192 处 ``文件#L行号`` 锚点整体错位，
只有 M 循环一条判据（FormData 四个锚点）打红，其余 191 处无人看见。平移只认「未改动的行」：落在被改写的行上不猜。
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

_TOOL = Path(__file__).resolve().parents[3] / "backend" / "scripts" / "fix" / "resync_data_line_anchors.py"


def _load():
    spec = importlib.util.spec_from_file_location("resync_data_line_anchors", _TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_line_map_follows_unchanged_lines_and_skips_rewritten_ones() -> None:
    mod = _load()
    old = ["import a", "const X = 1", "function f() {", "  return 1", "}"]
    new = ["import a", "import b", "const X = 1", "function f() {", "  return 2", "}"]
    mapping = mod._line_map(old, new)
    assert mapping[1] == 1 and mapping[2] == 3 and mapping[3] == 4 and mapping[5] == 6, mapping
    assert 4 not in mapping, "被改写的行不能平移（不猜）"


def test_apply_moves_is_single_pass_and_exact() -> None:
    mod = _load()
    text = ('{"a": "audit-platform/x.ts#L100", "b": "audit-platform/x.ts#L101",\r\n'
            ' "c": "audit-platform/x.ts#L1000", "d": "audit-platform/y.ts#L100"}\r\n')
    table = {'"audit-platform/x.ts#L100"': '"audit-platform/x.ts#L101"',
             '"audit-platform/x.ts#L101"': '"audit-platform/x.ts#L102"'}
    out = mod.apply_moves(text, table)
    assert out == ('{"a": "audit-platform/x.ts#L101", "b": "audit-platform/x.ts#L102",\r\n'
                   ' "c": "audit-platform/x.ts#L1000", "d": "audit-platform/y.ts#L100"}\r\n'), out


def test_plan_end_to_end_in_a_scratch_repo(tmp_path) -> None:
    """真 git 仓库：源文件上方插一行 ⇒ 锚点 +1；锚点所在行被改写 ⇒ 列为无法平移；已跟踪但工作区删掉的数据文件跳过。"""
    import subprocess

    def git(*args: str) -> None:
        subprocess.run(["git", "-C", str(tmp_path), "-c", "user.email=t@t", "-c", "user.name=t", *args],
                       check=True, capture_output=True)

    src = tmp_path / "audit-platform" / "a.ts"
    src.parent.mkdir(parents=True)
    src.write_bytes(b"line1\r\nconst X = 1\r\nreturn 1\r\n")
    data = tmp_path / "backend" / "data"
    data.mkdir(parents=True)
    (data / "slice.json").write_bytes(b'{"x": "audit-platform/a.ts#L2", "y": "audit-platform/a.ts#L3"}\r\n')
    (data / "gone.json").write_bytes(b'{"z": "audit-platform/a.ts#L1"}\r\n')
    git("init", "-q")
    git("add", "-A")
    git("commit", "-q", "-m", "base")
    src.write_bytes(b"line1\r\nimport b\r\nconst X = 1\r\nreturn 2\r\n")
    (data / "gone.json").unlink()

    mod = _load()
    mod.ROOT = tmp_path
    moves, stuck = mod.plan("HEAD", None)
    assert moves == {"backend/data/slice.json": {'"audit-platform/a.ts#L2"': '"audit-platform/a.ts#L3"'}}, moves
    assert stuck == ["backend/data/slice.json: audit-platform/a.ts#L3 所在行在 HEAD 之后被改写或删除，无法平移"], stuck
