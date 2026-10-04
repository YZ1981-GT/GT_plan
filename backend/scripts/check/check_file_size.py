"""文件行数卡点（pre-commit hook）。

migration-runner-resilience / 全局改进 #5 落地。

策略：
- 默认上限：backend Python ≤800 行，前端 .vue/.ts ≤1500 行
- whitelist：现有大文件列入 `backend/scripts/file_size_whitelist.txt`，
  每次模块打磨完成后从 whitelist 移除该文件（强制 ≤800/1500）
- 新加文件强制不超限（不在 whitelist 即检查）
- whitelist 中文件**仍然**检查"是否变得更大"：若行数 > whitelist 记录值 +5%，仍报错
  （防止"打磨倒退"）
- HARD_CAPS：已瘦身文件登记显式 ceiling，防止后续功能追加悄悄回弹膨胀
  （优先级高于 whitelist / 默认上限）

退出码：
- 0 = 通过
- 1 = 有文件超限
- 2 = whitelist 文件膨胀 >5%

用法：
    python backend/scripts/check_file_size.py [files...]

未传 files 则扫描 backend/app + audit-platform/frontend/src
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
WHITELIST_FILE = ROOT / "backend" / "scripts" / "file_size_whitelist.txt"

# 默认上限（按文件类型）
LIMITS = {
    ".py": 800,
    ".vue": 1500,
    ".ts": 1500,
    ".tsx": 1500,
}

# 硬上限（hard cap）：已完成瘦身的文件登记显式 ceiling，
# 即使远低于默认 LIMITS 也强制不得回弹超过该值，防止后续功能追加悄悄膨胀。
# gtdform-test-and-shrink（2026-05-30）：3 个 D 类 shell 拆分后登记 hard cap
# （实测 390/366/345 + ~15% 余量），后续触碰若超限必须再拆而非直接放宽。
HARD_CAPS = {
    "audit-platform/frontend/src/components/workpaper/GtDForm/GtDFormReview.vue": 450,
    "audit-platform/frontend/src/components/workpaper/GtDForm/GtDFormConfirmation.vue": 420,
    "audit-platform/frontend/src/components/workpaper/GtDForm/GtDFormParagraph.vue": 400,
    # DisclosureEditor.vue：2026-09-28 由 1800 更正为 3044（= 当前真实行数，splitlines 口径）。
    #
    # 🔴 **与 ReportView 的 1110 不同**：1800 是**曾经成立过**的有效约束，不是理想值。
    # 逐提交行数史实证：
    #   756120108 2026-06-06  1758  ← 瘦身达成
    #   0bcfadeed 2026-06-07  1793  ← 最后一个 <= 1800 的版本
    #   696bb1e55 2026-06-07  2091  ← 起，越过 1800
    #   55c5e0fe5 2026-08-22  3397  ← 单调增长至今
    # 所以**正解是继续瘦身，不是放宽**；本次更正只为解除「墙」效应，见下。
    #
    # 🔴 为什么必须更正：`HARD_CAPS` 是「超限即拒」**没有棘轮**。文件已 3397 而 cap 1800
    # ⇒ 任何触碰该文件的提交都被拒，**包括把它改小的提交**。2026-09-28 实测：一批把它从
    # 3398 减到 3044 的纯抽取重构被 pre-commit 拒绝 ⇒ 门禁事实上禁止了对它的**任何**改进，
    # 这也是它能一路涨到 3397 的一部分原因（人们绕开它而不是修它）。
    # 填真实值后门禁恢复为**只许变小的棘轮**：再加一行即打红。
    #
    # 🔴 **不加余量**（同 ReportView 那条的处置）：此处目的是防回弹，加余量等于预留膨胀空间。
    #
    # 待办（已逐块测绘，1800 目标不变）：当前 3044 = template 80 + script 1769 + styles 25。
    # script 内注释分区仍可抽 ~1235 行：恢复已删除章节 157 / 单元格激活编辑 124 /
    # 表格结构编辑 107 / 反向通知 104 / 详情缓存+hover 99 / 树快捷筛选 99 /
    # useStaleRefresh 74 / 结构编辑操作 68 / PermissionMatrix 68 / 转换规则 65 /
    # 打印预览 51 / 章节管理 48 …全抽完 script ~534 ⇒ 总计约 639，纯 script 路线即可达标，
    # **无需动模板**（模板侧主表区 437 行用 100 个绑定 / 对话框 247 行用 73 个 /
    # 覆盖层 170 行用 66 个，走 provide/inject 要塞约 250 个成员，是反模式，已排除）。
    # ⚠️ **每完成一批瘦身必须同步下调此值**，否则棘轮失效。
    "audit-platform/frontend/src/views/DisclosureEditor.vue": 3044,
    # ReportView.vue：2026-09-28 由 1110 更正为 1949（= 当前真实行数，splitlines 口径）。
    #
    # 🔴 **1110 是从未成立过的理想值**，不是被违反的有效约束。实证行数史：
    #   546adc654 2026-06-12  1104  ← 最后一个 <= 1110 的版本
    #   e8588091b 2026-06-13  1139  ← 起，连续 11 个提交、3 个月**从未**满足 1110
    #   f3354f539 2026-07-27  1941  ← 「调整分录集中登记」功能 +743 行
    #   55c5e0fe5 2026-08-22  1949  ← 当前内容与此版逐字节相同
    #   82f58ea44 2026-09-13     0  ← 被误删成空文件（路由页白屏 3 个月）
    # 门禁只扫**暂存文件**，该文件此间未被单独暂存过 ⇒ 超限从未被报出；
    # 而 0 字节期间行数为 1，反倒"满足"了 cap —— 文件被删空却门禁通过。
    #
    # 🔴 填真实值**不加余量**（对比同表 GtDForm 三项登记时加了 ~15%）：
    # 此处目的是防继续回弹，加余量等于预留膨胀空间。下次往本文件加任何一行
    # 都会打红 —— 那时必须先拆分（见下方待办）。
    #
    # 待办：report-view-slimdown 已归档但目标未达成（抽出 6 composable + 3 组件后
    # 又被功能开发加回 843 行）。真瘦身应另立 spec，按 ReportDialogs / 跨表核对 /
    # 多年度对比 / 报表分析 四个关注点继续切，不在本次 ADJ 接线范围内。
    "audit-platform/frontend/src/views/ReportView.vue": 1949,
}

EXCLUDE_PARTS = {".git", ".venv", "__pycache__", "node_modules", "dist", "build",
                 ".pytest_cache", ".hypothesis", "_archive", "auto-imports.d.ts",
                 "components.d.ts", "alembic"}

# 生成物后缀：与上面 `auto-imports.d.ts` / `components.d.ts` 同一意图 —— 由脚本生成的文件
# 「请拆分」不可执行（下次重新生成又会变回去），该管的是**生成器**（生成器本身是手写
# 代码，照常受本门约束）。按后缀而不是按 path part 判，因为文件名前缀各不相同。
GENERATED_SUFFIXES = (".generated.ts", ".generated.d.ts", "_pb2.py", ".gen.ts")


def load_whitelist() -> dict[str, int]:
    """读 whitelist：`path  baseline_lines`（空格分隔，# 注释）。"""
    if not WHITELIST_FILE.exists():
        return {}
    result: dict[str, int] = {}
    for line in WHITELIST_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) != 2:
            continue
        try:
            result[parts[0]] = int(parts[1])
        except ValueError:
            continue
    return result


#: `--staged` 模式：按**暂存内容**而不是工作树内容计数。
#:
#: 🔴 为什么需要它（2026-09-28，spec d1-sync-row-table-engine-and-d1-coverage · X1）：
#:    pre-commit hook 用 `git diff --cached --name-only` 选**暂存文件**，却让本脚本去读
#:    **工作树内容** —— 选的是「你提交了什么」，量的是「工作树有什么」，内部不自洽。
#:
#:    实测后果：`excel_materialize.py` 我只提交了 +31 行（暂存 3691，在基线 3660+5%
#:    之内），但同一文件里另一条 lane 有 ~258 行**未提交**改动 ⇒ 门按工作树 3948 判我膨胀。
#:    这会逼人做两件错事之一：把基线抬到 3948（替别人预留额度 + 把别人的膨胀记到自己账上），
#:    或者 `--no-verify` 绕过（门直接失效）。
#:
#:    `--staged` 让「门量的东西」== 「commit 里真正是什么」。工作树模式保持默认，
#:    手动跑脚本时的行为逐字不变。
_STAGED_MODE = False


def count_lines(p: Path) -> int:
    """行数。🔴 **读不出来时抛，不返 0** —— 返 0 会让 `0 > limit` 恒假 ⇒ 门禁静默放行。

    历史缺陷（spec workpaper-sync-adopt-overwrite-and-refresh-source 复盘）：原实现是
    `except Exception: return 0`，配合 `main()` 对相对路径按**仓库根**解析，导致在
    `cwd=backend` 下传 `tests/…/x.py`（或任何拼错/不存在的路径）都 **exit=0 假通过** ——
    一个 1055 行的文件曾因此被报成「通过」。

    `--staged` 模式下读 `git show :<path>`（暂存内容）。取不到暂存内容时**抛**而不是
    静默回落工作树 —— 回落会让「我以为门量的是暂存」变成一句空话。
    """
    if _STAGED_MODE:
        import subprocess

        rel = str(p.relative_to(ROOT)).replace("\\", "/")
        proc = subprocess.run(
            ["git", "show", f":{rel}"], cwd=str(ROOT), capture_output=True
        )
        if proc.returncode != 0:
            raise OSError(
                f"--staged 模式下取不到 {rel} 的暂存内容（git show :{rel} "
                f"exit={proc.returncode}）—— 该文件未暂存？拒绝回落工作树"
            )
        return len(proc.stdout.decode("utf-8", "replace").splitlines())
    return len(p.read_text(encoding="utf-8").splitlines())


def count_lines_or_none(p: Path) -> int | None:
    """给 `--print-current-violations` 这类**批量扫描**用：读不出来返回 None 并跳过。

    与 :func:`count_lines` 的分工：批量扫描面对整个仓库，个别文件编码异常不该中断扫描；
    而**显式传入**的路径读不出来是调用方的错，必须 fail visible（见 `main()`）。
    """
    try:
        return count_lines(p)
    except OSError:
        return None
    except UnicodeDecodeError:
        return None


def check_file(rel_path: str, abs_path: Path, whitelist: dict[str, int]) -> tuple[int, str]:
    """检查单文件。返回 (exit_code, message)。"""
    suffix = abs_path.suffix
    limit = LIMITS.get(suffix)
    if limit is None:
        return 0, ""
    if rel_path.endswith(GENERATED_SUFFIXES):
        return 0, ""
    # 🔴 读不出来 = **违规**，既不是「通过」也不该抛栈：把它报成一条可读的失败。
    #    （历史缺陷是把它当 0 行 ⇒ 静默通过；直接让异常冒泡又会变成难读的 traceback。）
    try:
        lines = count_lines(abs_path)
    except (OSError, UnicodeDecodeError) as exc:
        return 1, (
            f"❌ [读取失败] {rel_path}: {type(exc).__name__} —— 无法按 UTF-8 读取，"
            "行数判据无从成立（**不视为通过**）"
        )

    # hard cap 优先：已瘦身文件登记的显式 ceiling，防退化
    if rel_path in HARD_CAPS:
        cap = HARD_CAPS[rel_path]
        if lines > cap:
            return 1, (
                f"❌ [硬上限] {rel_path}: {lines} 行 > hard cap {cap}；"
                f"该文件已瘦身登记 ceiling，新增逻辑请继续拆分而非放宽上限"
            )
        return 0, ""

    if rel_path in whitelist:
        baseline = whitelist[rel_path]
        # 允许 ±5% 浮动避免抖动
        threshold = int(baseline * 1.05)
        if lines > threshold:
            return 2, (
                f"❌ [膨胀] {rel_path}: {lines} 行 > whitelist 基线 {baseline} +5% "
                f"({threshold})；打磨应让文件变小不变大"
            )
        return 0, ""

    if lines > limit:
        return 1, (
            f"❌ [超限] {rel_path}: {lines} 行 > 上限 {limit}；"
            f"请拆分或加入 whitelist（仅历史大文件许可）"
        )
    return 0, ""


def scan_default() -> list[Path]:
    """默认扫描全仓代码文件。"""
    targets: list[Path] = []
    for d in ("backend/app", "audit-platform/frontend/src"):
        root = ROOT / d
        if not root.exists():
            continue
        for f in root.rglob("*"):
            if not f.is_file() or f.suffix not in LIMITS:
                continue
            if any(p in f.parts for p in EXCLUDE_PARTS):
                continue
            targets.append(f)
    return targets


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="文件行数卡点")
    parser.add_argument("files", nargs="*", help="检查文件路径（pre-commit 传入）")
    parser.add_argument("--print-current-violations", action="store_true",
                        help="输出当前所有超限文件，用于生成 whitelist 基线")
    parser.add_argument(
        "--staged", action="store_true",
        help="按**暂存内容**计数（pre-commit 用）。默认读工作树。见 `_STAGED_MODE` 的说明："
             "hook 选的是暂存文件，量的却是工作树，并发 lane 的未提交改动会误判到你头上。",
    )
    args = parser.parse_args(argv)
    if args.staged:
        global _STAGED_MODE
        _STAGED_MODE = True

    whitelist = load_whitelist()

    if args.print_current_violations:
        # 用于初始化 whitelist：列出所有超限文件 + 当前行数
        for f in scan_default():
            rel = str(f.relative_to(ROOT)).replace("\\", "/")
            limit = LIMITS.get(f.suffix, 99999)
            lines = count_lines_or_none(f)
            if lines is not None and lines > limit:
                print(f"{rel} {lines}")
        return 0

    explicit = bool(args.files)
    if explicit:
        files = [ROOT / Path(f) for f in args.files]
    else:
        files = scan_default()

    exit_code = 0
    messages: list[str] = []

    # 🔴 **显式传入**的路径必须存在：原实现 `if not f.exists(): continue` 会把「路径拼错」
    #    静默变成「检查通过」。相对路径一律按**仓库根**解析（见下方 usage 提示），
    #    所以在 `cwd=backend` 下传 `tests/…` 是最常见的踩法。
    if explicit:
        missing = [str(f) for f in files if not f.exists() or not f.is_file()]
        if missing:
            print(
                "❌ [路径不存在] 以下显式传入的路径解析不到文件（相对路径按**仓库根**解析）：",
                file=sys.stderr,
            )
            for m in missing:
                print(f"    {m}", file=sys.stderr)
            print(
                "  提示：从仓库根传 `backend/xxx.py` / `audit-platform/frontend/src/xxx.vue`；"
                "在 backend/ 目录下传 `tests/...` 会拼成 <repo>/tests/... 而不存在。",
                file=sys.stderr,
            )
            return 2

    for f in files:
        if not f.exists() or not f.is_file():
            continue
        rel = str(f.resolve().relative_to(ROOT)).replace("\\", "/") if f.is_absolute() \
              else str(f).replace("\\", "/")
        if any(p in Path(rel).parts for p in EXCLUDE_PARTS):
            continue
        if Path(rel).suffix not in LIMITS:
            continue
        code, msg = check_file(rel, f if f.is_absolute() else (ROOT / rel), whitelist)
        if msg:
            messages.append(msg)
        if code > exit_code:
            exit_code = code

    if messages:
        print("\n".join(messages), file=sys.stderr)
        print("", file=sys.stderr)
        print(f"共 {len(messages)} 个文件超限/膨胀。", file=sys.stderr)
        print(f"whitelist 路径: {WHITELIST_FILE.relative_to(ROOT)}", file=sys.stderr)

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
