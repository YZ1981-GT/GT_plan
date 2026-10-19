"""守卫脚本共享的 spec 目录解析 helper。

背景（铁律：归档必须同步守卫）：
    spec 完成后会从 active 目录 `.kiro/specs/<name>/` 归档到
    `.kiro/specs/_archive/<nn>-xxx/<name>/`。守卫脚本若把 active 路径写死，
    spec 一归档就对任何 clean checkout 恒红——而恒红的门禁等价于门禁失效
    （红成常态 → 没人看 → 真缺陷藏在里面）。更糟的是它报的是误导性的
    "文件不存在"而不是 spec 的真实状态。

    因此所有需要读 spec 目录文件（tasks.md / design.md / requirements.md /
    evidence/ 等）的守卫，都应通过本 helper 解析目录：active 优先，
    否则回退到 `_archive/**` 下的同名目录。

这个 helper 本身是"单一来源"——所有守卫共用它，避免每个脚本各自复制一份
归档回退逻辑（那又会变成"多份拷贝漂移"的反模式）。
"""
from __future__ import annotations

from pathlib import Path

# GT_plan 仓库根：本文件位于 backend/scripts/check/_spec_dir.py，parents[3] = 根
_REPO_ROOT = Path(__file__).resolve().parents[3]
_SPECS_ROOT = _REPO_ROOT / ".kiro" / "specs"


def resolve_spec_dir(
    spec_name: str,
    *,
    require_files: "list[str] | tuple[str, ...] | None" = None,
    repo_root: Path | None = None,
) -> Path:
    """定位名为 ``spec_name`` 的 spec 目录。

    active 优先；否则回退到 `_archive/*/` 下的同名目录（取第一个确实存在的）。
    两者都找不到时返回 active 路径，让下游 check 报出清晰的"目录/文件不存在"
    错误，而不是在这里静默吞掉。

    🔴 ``require_files``：一个目录"存在"不代表它是**正确的** spec 目录。
       实战踩到：active 目录可能是只落了一个产物文件（如 release_evidence.json）
       的**空壳**，真正的 spec 三件套（requirements/design/tasks.md）已经归档。
       若只按"目录存在"选 active，守卫会读不到它要的文件而误红。因此当调用方
       传入 ``require_files`` 时，active 必须**同时包含全部**这些文件才被选中，
       否则跳过 active、回退到真正包含这些文件的 archive 目录。

    Args:
        spec_name: spec 目录名，例如 "formula-runtime-convergence"。
        require_files: 可选，判定一个候选目录是否"合格"所需的相对文件名列表
            （如 ["tasks.md"] 或 ["requirements.md", "design.md", "tasks.md"]）。
            省略时只要目录存在即视为合格（向后兼容）。
        repo_root: 可选，覆盖仓库根（便于测试）。默认用本模块推导的根。

    Returns:
        解析到的 spec 目录 Path。
    """
    specs_root = (repo_root / ".kiro" / "specs") if repo_root is not None else _SPECS_ROOT

    def _qualifies(d: Path) -> bool:
        if not d.exists():
            return False
        if require_files:
            return all((d / f).exists() for f in require_files)
        return True

    active = specs_root / spec_name
    if _qualifies(active):
        return active

    archive_root = specs_root / "_archive"
    if archive_root.exists():
        for candidate in sorted(archive_root.glob(f"*/{spec_name}")):
            if _qualifies(candidate):
                return candidate

    return active
