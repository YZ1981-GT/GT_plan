"""门禁子进程「内层退出码校验」工具——复用 §7.4③ 口径，防 RTK 吞失败退出码。

Task 8.5 · spec `formula-manager-closure`（需求 20.4、design §5 步骤 8 · 20.4、§7.4③）。

═══ 这个模块防的是什么 ═══

RTK（CLI token 压缩代理，shell 命令加 ``rtk`` 前缀压缩输出）在**外层包装**子命令。
审计报告（第八/九节）观察到：RTK 外层在子命令失败时**可能仍返回 exit 0**，使「只看
退出码」的门禁假绿——门禁子进程 `returncode == 0` 便当成通过，而被包装的真实命令其实
已失败。这与 memory 教训㉗⑦「`subprocess` 捕获输出『解码失败』不会让 run() 失败，只把
stdout 变 None、只断言 returncode 的测试必假绿」是同一类「外层码不可信」缺陷的两面。

§7.4③ 的修正口径（requirements 20.4 / design §7.4③）：
  门禁子进程**断言 stdout/stderr 含预期内容**（非仅看 returncode），并对 RTK 包装的
  命令**显式校验内层退出码或输出标志**。

═══ 本模块提供什么 ═══

:func:`run_gate_subprocess`
    运行门禁子进程并返回 :class:`GateRunResult`。无论命令是否经 RTK 包装：
      ① 子进程捕获输出设 ``PYTHONIOENCODING=utf-8`` + ``errors='replace'``（§7.4③，
         Windows 子进程 piped stdout 默认 gbk，中文按 utf-8 解码必炸 → stdout 变 None
         却不改退出码 ⇒ 只看 returncode 必假绿，教训㉗⑦）；
      ② **断言 stdout/stderr 含预期标记之一**（``expected_markers``）——缺标记即判
         ``marker_missing``（解码失败被吞 / 空转 / 根本没跑到预期分支）；
      ③ **推断内层退出码**：若 ``expected_markers`` 覆盖「成功标记 vs 失败标记」，内层
         成败由**输出标记**判定，不依赖 RTK 外层 returncode 的透传（这正是 20.4 的核心）。

:func:`assert_gate_passed`
    供门禁/测试调用的硬断言便捷入口：内层未通过（失败标记命中 / 预期成功标记缺失 /
    外层码非 0 但无可信成功标记）→ 抛 :class:`GateInnerFailure`，消息含 stdout 摘要。

:func:`is_rtk_wrapped`
    判断一条 argv 是否以 ``rtk`` 包装（供守卫 / 调用方识别需要内层校验的命令）。
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field
from typing import Sequence

__all__ = [
    "GateRunResult",
    "GateInnerFailure",
    "is_rtk_wrapped",
    "run_gate_subprocess",
    "assert_gate_passed",
]


class GateInnerFailure(RuntimeError):
    """门禁子进程「内层」判定为失败（而非只看外层 returncode）。"""


def is_rtk_wrapped(argv: Sequence[str]) -> bool:
    """判断一条命令是否以 ``rtk`` 前缀包装。

    识别 ``rtk <cmd> ...`` 形态（含绝对路径的 ``.../rtk`` / ``rtk.exe``）。
    空 argv、首元素非 rtk → False。
    """
    if not argv:
        return False
    head = str(argv[0]).strip().replace("\\", "/").rsplit("/", 1)[-1].lower()
    return head in ("rtk", "rtk.exe")


@dataclass(slots=True)
class GateRunResult:
    """门禁子进程一次运行的结果（内层成败由输出标记 + 退出码综合判定）。"""

    argv: list[str]
    returncode: int | None
    stdout: str
    stderr: str
    rtk_wrapped: bool
    #: 命中的预期标记集合（出现在 stdout+stderr 里的 expected_markers 子集）。
    markers_hit: list[str] = field(default_factory=list)
    #: 命中的失败标记集合（出现的 failure_markers 子集）。
    failure_markers_hit: list[str] = field(default_factory=list)

    @property
    def combined(self) -> str:
        return self.stdout + self.stderr

    @property
    def has_any_marker(self) -> bool:
        """是否命中**任一**预期标记（证明真的跑到了对应分支，而非空转/解码失败被吞）。"""
        return bool(self.markers_hit)

    def inner_passed(self) -> bool:
        """**内层**是否通过——不单看 RTK 外层 returncode（20.4 核心）。

        判定规则（任一不满足即 False）：
          1. 必须命中至少一个预期标记（stdout 为空 / 无标记 = 解码被吞或空转 → 不可信）。
          2. 不得命中任何失败标记（命中失败标记 = 内层确实失败，哪怕外层 returncode=0）。
          3. 若提供了「成功标记」判据（failure_markers 非空），则成败完全由标记定夺，
             外层 returncode 仅作兜底：无失败标记且命中预期标记 → 通过。
          4. 若未提供失败标记判据（纯标记存在性门），则还要求 returncode in (0, None=未取到
             时不作否决) —— 但只要命中标记且外层码非 0，仍判失败（外层码可信方向：非 0 必失败）。
        """
        if not self.has_any_marker:
            return False
        if self.failure_markers_hit:
            return False
        # 外层 returncode 的「非 0 一定是失败」方向可信（RTK 不会把失败硬改成非 0）；
        # 不可信的只是「0 可能掩盖内层失败」方向——那一侧已由失败标记兜住。
        if self.returncode is not None and self.returncode != 0 and not self._has_success_signal():
            return False
        return True

    def _has_success_signal(self) -> bool:
        """是否存在显式「成功/可接受」标记（如漂移 exit 2 本身是有效三态之一）。"""
        return bool(self.markers_hit) and not self.failure_markers_hit


def run_gate_subprocess(
    argv: Sequence[str],
    *,
    cwd: str | os.PathLike[str] | None = None,
    expected_markers: Sequence[str],
    failure_markers: Sequence[str] = (),
    timeout: float | None = None,
    env: dict[str, str] | None = None,
) -> GateRunResult:
    """运行门禁子进程，按 §7.4③ 捕获输出并判内层成败。

    Args:
      argv: 命令 argv（可含 ``rtk`` 前缀；内层校验不依赖 RTK 外层码透传）。
      cwd: 工作目录。
      expected_markers: **至少命中一个**的预期输出标记（缺全部 = marker_missing 假绿风险）。
      failure_markers: 命中即判内层失败的标记（如 ``[FAIL]`` / ``Error`` / ``Traceback``）；
        提供后成败由标记定夺，不信 RTK 外层 returncode 的「0=成功」方向。
      timeout: 子进程超时秒数。
      env: 额外环境变量（会并入 ``PYTHONIOENCODING=utf-8`` 基础环境）。

    Returns:
      :class:`GateRunResult`。
    """
    run_env = dict(os.environ)
    # §7.4③：强制 utf-8，避免 Windows gbk piped stdout 解码失败把 stdout 吞成 None。
    run_env["PYTHONIOENCODING"] = "utf-8"
    if env:
        run_env.update(env)

    try:
        proc = subprocess.run(
            list(argv),
            cwd=str(cwd) if cwd is not None else None,
            capture_output=True,
            encoding="utf-8",
            errors="replace",  # §7.4③：解码失败用替代字符，不静默吞成 None
            env=run_env,
            timeout=timeout,
        )
        returncode: int | None = proc.returncode
        stdout = proc.stdout or ""
        stderr = proc.stderr or ""
    except subprocess.TimeoutExpired as exc:
        returncode = None
        stdout = (exc.stdout or b"").decode("utf-8", "replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = (exc.stderr or b"").decode("utf-8", "replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")

    combined = stdout + stderr
    markers_hit = [m for m in expected_markers if m and m in combined]
    failure_hit = [m for m in failure_markers if m and m in combined]

    return GateRunResult(
        argv=list(argv),
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
        rtk_wrapped=is_rtk_wrapped(argv),
        markers_hit=markers_hit,
        failure_markers_hit=failure_hit,
    )


def assert_gate_passed(result: GateRunResult) -> None:
    """门禁硬断言：内层未通过 → 抛 :class:`GateInnerFailure`（消息含 stdout 摘要）。

    这是「断言 stdout 内容、非仅 returncode」的落点——即便 RTK 把外层码吞成 0，只要
    预期成功标记缺失或命中失败标记，本函数照样抛错。
    """
    if result.inner_passed():
        return

    snippet = result.combined.strip()[:2000]
    if not result.has_any_marker:
        raise GateInnerFailure(
            "门禁子进程无任何预期标记——stdout/stderr 为空或解码被吞（只看 returncode 必假绿，"
            f"教训㉗⑦）。argv={result.argv}（rtk_wrapped={result.rtk_wrapped}）、"
            f"returncode={result.returncode}。输出摘要:\n{snippet}"
        )
    if result.failure_markers_hit:
        raise GateInnerFailure(
            f"门禁子进程命中失败标记 {result.failure_markers_hit}（内层确实失败，哪怕外层 "
            f"returncode={result.returncode}——RTK 可能吞了内层失败码）。argv={result.argv}。"
            f"输出摘要:\n{snippet}"
        )
    raise GateInnerFailure(
        f"门禁子进程内层未通过：returncode={result.returncode}、命中标记={result.markers_hit}。"
        f"argv={result.argv}（rtk_wrapped={result.rtk_wrapped}）。输出摘要:\n{snippet}"
    )
