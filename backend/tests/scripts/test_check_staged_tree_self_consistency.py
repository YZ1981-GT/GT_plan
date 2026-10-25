# -*- coding: utf-8 -*-
"""`check_staged_tree_self_consistency.py` 的自测。

spec: d1-sync-row-table-engine-and-d1-coverage · X5-i

═══ 核心要证明的一件事 ═══

物化出来的是 **index（暂存区）内容**，不是工作树内容。这是本门全部价值所在 ——
本轮三处漏提交的形态正是「工作树绿、提交后红」，读错了源就什么都守不住。

证明方式是**直接**的：对一个 index ≠ 工作树的文件，逐字节比对导出结果
（`git show :<path>` 相同 / 工作树不同）。比「门的 rc 有差异」这种间接证据强，
而且是纯读操作，不动工作树。
"""
from __future__ import annotations

import importlib.util
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[3]
_CHECK = (
    _REPO / "backend" / "scripts" / "check" / "check_staged_tree_self_consistency.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("_stsc", _CHECK)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _lf(data: bytes) -> bytes:
    """行尾归一。

    🔴 必须归一（2026-09-28 实测）：`git checkout-index` 会应用 `.gitattributes` 的
    行尾转换（导出成工作树格式 CRLF），而 `git show :<path>` 返回 blob 原始内容（LF）。
    逐字节比对会在第一个换行处就假红 —— 内容其实完全一致。
    与「PowerShell 的行数/编码显示不可信」同族：**先排除表示层差异再下结论**。
    """
    return data.replace(b"\r\n", b"\n")


def _divergent_py() -> str | None:
    """找一个 index 与工作树**真有内容差异**的 backend .py（不含仅行尾差异）。

    仅行尾差异的文件在归一化后两边相等 ⇒ 用它做「!= 工作树」那一半判据会假红。
    """
    proc = subprocess.run(
        ["git", "diff", "--name-only"], cwd=str(_REPO),
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    for line in proc.stdout.splitlines():
        p = line.strip()
        if not (p.startswith("backend/") and p.endswith(".py")):
            continue
        index_bytes = subprocess.run(
            ["git", "show", f":{p}"], cwd=str(_REPO), capture_output=True
        ).stdout
        try:
            worktree_bytes = (_REPO / p).read_bytes()
        except OSError:
            continue
        if _lf(index_bytes) != _lf(worktree_bytes):
            return p
    return None


def test_materialised_tree_is_the_index_not_the_worktree() -> None:
    """🔴 决定性判据：导出内容 == `git show :<path>`，且 != 工作树内容。"""
    rel = _divergent_py()
    if rel is None:
        pytest.skip(
            "当前没有「index 与工作树不同」的 backend .py —— 本条需要那种文件才能"
            "区分两个源（不构造假数据：git 索引状态就是被测对象本身）"
        )
    mod = _load()
    tmp = Path(tempfile.mkdtemp(prefix="gt_stsc_test_"))
    try:
        mod._materialise(tmp)
        got = (tmp / rel).read_bytes()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    index_bytes = subprocess.run(
        ["git", "show", f":{rel}"], cwd=str(_REPO), capture_output=True
    ).stdout
    worktree_bytes = (_REPO / rel).read_bytes()

    assert _lf(got) == _lf(index_bytes), (
        f"{rel} 的导出内容与 index 不一致（已排除行尾差异）—— 物化源错了"
    )
    assert _lf(got) != _lf(worktree_bytes), (
        f"{rel} 的导出内容等于**工作树** —— 那正是本门要避免的口径"
    )


def test_materialisation_scope_is_whole_repo_not_narrowed() -> None:
    """🔴 物化范围必须是**全仓已跟踪文件**，不得再收窄。

    两次收窄都被实测打脸（见门的 docstring）：
      ① 只导 `.py/.json/.yaml` ⇒ golden digest 对十余家 provider 报
         `[SKIP] 探针覆盖的权威模板缺失`（它真的读 `backend/wp_templates/*.xlsx`）；
      ② 只导 `backend/` ⇒ 又报 `[SKIP] d4: ... .kiro/specs/.../evidence/*.json` 不存在。
    两次都是「我以为它只读代码」这个推演。收窄的代价是门跑不满而我以为它过了。
    """
    mod = _load()
    assert mod._INCLUDE_SUFFIXES is None, (
        "后缀过滤又回来了 —— 会让被测门因缺资源而 SKIP，拿到假绿"
    )
    assert mod._PATHSPEC == (), "pathspec 被收窄 —— 同上"

    paths = mod._staged_paths()
    assert paths, "没收集到任何文件"
    # 必须包含二进制模板与 spec 目录 —— 这两类正是两次踩坑的对象
    assert any(p.endswith(".xlsx") for p in paths), "没有 xlsx ⇒ golden digest 会 SKIP"
    assert any(p.startswith(".kiro/specs/") for p in paths), (
        "没有 .kiro/specs ⇒ d4 的 evidence 读不到会 SKIP"
    )


def test_unexpected_skip_makes_the_gate_fail_even_at_rc_zero() -> None:
    """🔴 「跑不满」不算过：门自己 exit 0 但输出含非预期 SKIP ⇒ 仍判失败。

    这是本门最容易假绿的一处 —— 首版就是这么骗过我的。
    """
    mod = _load()
    gate = "backend/scripts/check/check_sync_provider_golden_digest.py"
    # 非预期标签 ⇒ 必须报出来
    assert mod.unexpected_skips(gate, "[SKIP] d4: evidence json 缺失\n✅ 全绿\n") == ["d4"]
    # 预期标签（门自己登记的 f1）⇒ 不报
    assert mod.unexpected_skips(gate, "[SKIP] f1: 签名不兼容\n✅ 全绿\n") == []
    # 混合 ⇒ 只报非预期那个
    assert mod.unexpected_skips(
        gate, "[SKIP] f1: x\n[SKIP] g10: 模板缺失\n"
    ) == ["g10"]
    # 解析不出标签的 SKIP 行也算非预期（宁可误报，不放过）
    assert mod.unexpected_skips(gate, "[SKIP] 没有冒号的怪行\n"), (
        "解析不出标签时必须算非预期 —— 放过就回到「跑不满也算过」"
    )


def test_expected_skips_are_registered_per_gate_not_globally() -> None:
    """预期 SKIP 必须按门登记 —— 全局白名单会让 A 门的豁免泄漏到 B 门。"""
    mod = _load()
    assert isinstance(mod._EXPECTED_SKIPS, dict)
    for gate_rel, labels in mod._EXPECTED_SKIPS.items():
        assert (_REPO / gate_rel).exists(), f"{gate_rel} 不存在"
        assert labels, f"{gate_rel} 的预期 SKIP 列表为空 —— 该删这条登记"
    # 另一道门不得继承 golden digest 的 f1 豁免
    other = "backend/scripts/check/check_store_item_two_way_parity.py"
    assert mod.unexpected_skips(other, "[SKIP] f1: x\n") == ["f1"], (
        "f1 豁免泄漏到了另一道门"
    )


def test_pre_push_hook_source_invokes_this_gate() -> None:
    """本门必须真的被 pre-push 调用 —— 否则它只是个没人跑的脚本。

    🔴 按「剔掉 `#` 开头行后再匹配」判定，不做全文 `in`：本轮已经栽过一次
    （用 `'--staged' in text` 判断 hook 装好了没，命中的是自己写的注释）。
    """
    hook = _REPO / ".git-hooks" / "pre-push"
    lines = [
        l.strip() for l in hook.read_text(encoding="utf-8").split("\n")
        if l.strip() and not l.strip().startswith("#")
    ]
    hits = [l for l in lines if "check_staged_tree_self_consistency.py" in l]
    assert hits, "pre-push 源里没有（非注释的）本门调用行"
    assert any("if !" in l or "||" in l or "exit" in l for l in hits) or len(hits) >= 1


def test_installed_pre_push_matches_source_or_tells_you_to_install() -> None:
    """已装的 pre-push 与源不一致时要说出来 —— `.git/hooks/` 不在版本控制里。"""
    src = _REPO / ".git-hooks" / "pre-push"
    installed = _REPO / ".git" / "hooks" / "pre-push"
    if not installed.exists():
        pytest.skip(".git/hooks/pre-push 不存在（CI 正常）—— 本地请跑 .git-hooks/install.ps1")

    def _calls(p: Path) -> list[str]:
        return [
            l.strip() for l in p.read_text(encoding="utf-8", errors="replace").split("\n")
            if l.strip() and not l.strip().startswith("#")
            and "check_staged_tree_self_consistency.py" in l
        ]

    assert _calls(installed) == _calls(src), (
        "已装的 pre-push 与 .git-hooks/ 源不一致 —— 你对 hook 的修改不会生效。\n"
        "修复：powershell -File .git-hooks/install.ps1"
    )


def test_expected_skips_are_still_actually_skipped() -> None:
    """反向断言：登记的预期 SKIP 必须**真的仍在 SKIP**（否则该删登记）。

    在真实工作树上跑被测门并检查输出 —— 比在物化树上跑快，且结论等价
    （f1 的签名不兼容与检出无关）。
    """
    mod = _load()
    for gate_rel, labels in mod._EXPECTED_SKIPS.items():
        proc = subprocess.run(
            [__import__("sys").executable, str(_REPO / gate_rel)],
            cwd=str(_REPO / "backend"), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=900,
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        for label in labels:
            assert f"[SKIP] {label}" in out, (
                f"{gate_rel} 已不再跳过 {label} —— 请从 _EXPECTED_SKIPS 删除该条"
                f"（棘轮只许变短）"
            )


def test_gates_are_declared_with_reasons_and_are_committed() -> None:
    """每道门要写明「为什么在暂存树上跑它有意义」，且门本身必须已入库。"""
    mod = _load()
    assert mod._GATES, "门列表为空"
    for gate_rel, why in mod._GATES:
        assert (_REPO / gate_rel).exists(), f"{gate_rel} 不存在"
        assert why and len(why) >= 8, f"{gate_rel} 缺少足以判读的理由"
        tracked = subprocess.run(
            ["git", "ls-files", "--error-unmatch", "--", gate_rel],
            cwd=str(_REPO), capture_output=True,
        ).returncode == 0
        assert tracked, f"{gate_rel} 未入库 —— 暂存树里会找不到它"


def test_missing_gate_in_tree_is_reported_not_silently_skipped() -> None:
    """变异：门脚本不在暂存树里时必须报 127，不能静默当成通过。

    这是「静默跳过 = 假绿」那条纪律在本门的落点。
    """
    mod = _load()
    tmp = Path(tempfile.mkdtemp(prefix="gt_stsc_empty_"))
    try:
        rc, msg = mod._run_gate(tmp, "backend/scripts/check/check_does_not_exist_xyz.py")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    assert rc == 127, f"缺门时应返回 127，实得 {rc}"
    assert "未入库" in msg or "没有" in msg, msg


def test_materialise_refuses_empty_collection(monkeypatch) -> None:
    """变异：收集为空时必须**抛**，不能物化一棵空树然后让门「通过」。"""
    mod = _load()
    monkeypatch.setattr(mod, "_staged_paths", lambda: [])
    tmp = Path(tempfile.mkdtemp(prefix="gt_stsc_none_"))
    try:
        with pytest.raises(RuntimeError, match="口径"):
            mod._materialise(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
