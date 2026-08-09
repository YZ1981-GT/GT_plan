"""底稿物理文件路径解析 — 单一真源（wp-export-file-path-resolution）

## 为什么需要这个模块

`working_paper.file_path` 在真实库里有**四种形态**（2026-08-09 实测 2798 份未软删底稿）：

| 形态          | 数量 | 样例                                                        |
|---------------|------|-------------------------------------------------------------|
| `EMPTY`       | 1564 | `''`（空字符串）                                            |
| `TEMPLATE_REL`|  956 | `wp_templates/I/I3 商誉.xlsx`（相对 backend/）              |
| `STORAGE_REL` |  246 | `storage\\projects\\<uuid>\\workpapers\\D\\D2-2.xlsx`       |
| `ABSOLUTE`    |    6 | `D:\\GT_plan\\backend\\wp_storage\\<uuid>\\<uuid>.xlsx`     |
| `OTHER_REL`   |   26 | `/tmp/03ab248f.xlsx`（历史脏数据）                          |

而各调用方各写一份路径判定，形态覆盖面互不相同：

- `WpDownloadService.download_pack` — 裸 `Path(fp).exists()`，**无任何回退**
- `WpDownloadService.download_single` — `.exists()` 失败后拼 `backend/` 再试一次
- `WpExportEngine._resolve_docx_template` — 拼项目根 + 回退模板库
- `wp_render_config_helpers._resolve_template_path` — `.is_file()` + 回退模板库

## 🔴🔴🔴 头号缺陷：`Path('')` 的 `.exists()` 返回 True

`Path('')` 归一成 `WindowsPath('.')`（当前工作目录），`.exists()` 为 **True** 而
`.is_file()` 为 **False**。`download_pack` 只判 `.exists()` ⇒ 对那 1564 份空
`file_path` 的底稿执行 `zf.write(Path(''), 'D/xxx.xlsx')`，把**当前目录**写成一个
名为 `D/xxx.xlsx/` 的**目录条目** ⇒ 用户解压出一堆空文件夹，表现为「模板导不出来，
都是空的」。基线实测：2798 份里 `file=1000 / DIR_ENTRY=1564 / skip=234`。

## 判定顺序（`resolve_wp_file`）

1. `file_path` 为 None/空白 → 跳过路径层，直接进模板库回退
2. 绝对路径 → `.is_file()` 命中即返回
3. 相对路径 → 依次试 `cwd` / `BACKEND_ROOT` / `REPO_ROOT`，首个 `.is_file()` 命中即返回
4. 以上都不中且 `allow_template_fallback=True` → `find_template_file_any(wp_code)`
5. 全不中 → `verdict='missing'`

**恒定后置条件**：返回的 `path` 要么是 `None`，要么 `path.is_file()` 为真。
绝不返回目录（这是本模块存在的首要理由，`Property 4` 钉死）。

## 设计约束

- **纯同步、无 DB、无 ORM 依赖** —— 便于 `download_pack`（异步）与 render（同步）共用，
  也便于守卫直接单测。
- **`is_file()` 而非 `exists()`** —— 唯一可靠的「这是一个可读文件」判据。
- **`verdict` 分档而非布尔** —— 调用方要区分「本来就没配路径」（`empty`）、
  「配了但文件丢了」（`missing`）、「回退到模板库」（`template_fallback`），
  这三者在跳过清单里的处置与文案完全不同；退化成布尔会让 ZIP 的
  `_skipped.txt` 无法给出可操作的原因。
- **`allow_template_fallback` 可关** —— 「导出这份底稿的实际内容」与
  「拿一份空白模板凑数」是两件事；批量打包默认开（有胜于无 + 清单标注来源），
  而校验/哈希类场景应关掉，避免把模板哈希当成底稿哈希。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)

# ─── 路径基准 ────────────────────────────────────────────────────────────────
# 本文件位于 backend/app/services/wp_export/wp_file_resolver.py
#   parents[0] = wp_export
#   parents[1] = services
#   parents[2] = app
#   parents[3] = backend      ← BACKEND_ROOT（生产 cwd，start-dev.bat 里 cd /d backend）
#   parents[4] = 仓库根        ← REPO_ROOT
BACKEND_ROOT = Path(__file__).resolve().parents[3]
REPO_ROOT = Path(__file__).resolve().parents[4]

#: 相对路径的尝试基准，顺序即优先级。
#: 🔴 `Path.cwd()` 必须在最前 —— 生产 cwd 就是 BACKEND_ROOT，但测试/脚本可能
#: 从仓库根跑，两者都要能命中（memory 已记「pytest 从 backend/ 跑会让 16 个
#: 用相对路径的测试假红」，此处两个基准都试可免疫 CWD 差异）。
def _relative_bases() -> tuple[Path, ...]:
    """相对路径基准列表（去重、保序）。

    有意做成函数而非模块级常量：`Path.cwd()` 在导入期取值会被测试里的
    `monkeypatch.chdir` 骗过（导入一次、后续 chdir 不生效）。
    """
    seen: list[Path] = []
    for base in (Path.cwd(), BACKEND_ROOT, REPO_ROOT):
        if base not in seen:
            seen.append(base)
    return tuple(seen)


WpFileVerdict = Literal["file", "template_fallback", "empty", "missing"]

#: 判定结果取值域（守卫按它断言，禁止在调用方硬写字面量）
WP_FILE_VERDICTS: tuple[WpFileVerdict, ...] = (
    "file",
    "template_fallback",
    "empty",
    "missing",
)

#: 中文原因文案（唯一真源，ZIP 跳过清单与前端提示共用）
VERDICT_LABELS: dict[str, str] = {
    "file": "底稿文件已就绪",
    "template_fallback": "底稿文件缺失，已回退空白模板",
    "empty": "未配置底稿文件路径（file_path 为空）",
    "missing": "底稿文件不存在（路径已配置但磁盘上找不到）",
}


@dataclass(frozen=True)
class WpFileResolution:
    """底稿物理文件解析结果。

    Attributes:
        path: 可读文件的绝对路径；`None` 表示不可达。
            **后置条件**：非 None 时 `path.is_file()` 必为真。
        verdict: 判定档位，取值 ⊆ :data:`WP_FILE_VERDICTS`。
        reason: 中文原因（供 ZIP 跳过清单 / 日志 / 前端提示直接展示）。
        raw: 原始 `file_path`（未归一），用于日志与排查。
        tried: 实际尝试过的候选路径（按顺序），排查用。
    """

    path: Path | None
    verdict: WpFileVerdict
    reason: str
    raw: str | None = None
    tried: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        """是否拿到了一个可读文件（含模板回退）。"""
        return self.path is not None

    @property
    def is_fallback(self) -> bool:
        """是否来自模板库回退（内容不是底稿实际录入）。"""
        return self.verdict == "template_fallback"


def _is_blank(file_path: str | None) -> bool:
    """空 / 纯空白 / None 都算「未配置路径」。

    🔴 这是本模块的核心判据之一：`Path('')` 会被 `.exists()` 判 True，
    必须在构造 Path **之前**就拦掉。
    """
    return file_path is None or not str(file_path).strip()


def _candidates(file_path: str) -> list[Path]:
    """构造候选绝对路径列表（保序、去重）。

    Windows 反斜杠与 POSIX 斜杠都能被 `Path` 正确解析，无需手工替换。
    """
    raw = str(file_path).strip()
    p = Path(raw)

    out: list[Path] = []

    def _push(candidate: Path) -> None:
        try:
            resolved = candidate.resolve()
        except (OSError, ValueError):  # 非法路径字符等
            return
        if resolved not in out:
            out.append(resolved)

    if p.is_absolute():
        _push(p)
        return out

    for base in _relative_bases():
        _push(base / p)
    return out


def resolve_wp_file(
    file_path: str | None,
    wp_code: str | None = None,
    *,
    allow_template_fallback: bool = True,
) -> WpFileResolution:
    """把 `working_paper.file_path` 解析成一个**可读文件**的绝对路径。

    Args:
        file_path: `working_paper.file_path` 原值（可为 None / 空串 / 相对 / 绝对）。
        wp_code: 底稿编码，仅用于模板库回退；为 None 时不回退。
        allow_template_fallback: 是否允许回退到 `wp_templates` 模板库。
            打包/下载场景建议 True（空白模板 + 清单标注 优于整份缺失）；
            哈希/校验场景应传 False（模板哈希不等于底稿哈希）。

    Returns:
        :class:`WpFileResolution`。`path` 非 None 时保证 `is_file()` 为真。

    Examples:
        >>> r = resolve_wp_file("", "D2")           # doctest: +SKIP
        >>> r.verdict in ("template_fallback", "empty")
        True
        >>> r.path is None or r.path.is_file()
        True
    """
    tried: list[str] = []

    # ─── Step 1: 空路径直接进回退（绝不构造 Path('')）────────────────────
    if _is_blank(file_path):
        return _template_fallback(
            wp_code=wp_code,
            allow=allow_template_fallback,
            raw=file_path,
            tried=(),
            blank=True,
        )

    # ─── Step 2/3: 逐个候选试 is_file() ─────────────────────────────────
    for candidate in _candidates(str(file_path)):
        tried.append(str(candidate))
        try:
            if candidate.is_file():
                return WpFileResolution(
                    path=candidate,
                    verdict="file",
                    reason=VERDICT_LABELS["file"],
                    raw=str(file_path),
                    tried=tuple(tried),
                )
        except OSError as err:  # 权限 / 路径过长等
            logger.debug("resolve_wp_file: 候选路径检查失败 %s: %s", candidate, err)

    # ─── Step 4/5: 模板库回退 → missing ─────────────────────────────────
    return _template_fallback(
        wp_code=wp_code,
        allow=allow_template_fallback,
        raw=file_path,
        tried=tuple(tried),
        blank=False,
    )


def _template_fallback(
    *,
    wp_code: str | None,
    allow: bool,
    raw: str | None,
    tried: tuple[str, ...],
    blank: bool,
) -> WpFileResolution:
    """模板库回退。失败时按 `blank` 区分 `empty` / `missing`。"""
    terminal: WpFileVerdict = "empty" if blank else "missing"

    if not allow or not wp_code:
        return WpFileResolution(
            path=None,
            verdict=terminal,
            reason=VERDICT_LABELS[terminal],
            raw=raw if raw is None else str(raw),
            tried=tried,
        )

    try:
        # 局部 import：`wp_template_finder` 会读磁盘索引 JSON，
        # 模块级 import 会让本模块在无模板库的环境下不可导入。
        from app.services.wp_template_init_service import find_template_file_any

        tpl = find_template_file_any(wp_code)
    except Exception as err:  # noqa: BLE001 — 模板库不可用不应打断导出
        logger.warning(
            "resolve_wp_file: 模板库回退失败 wp_code=%s: %s", wp_code, err
        )
        tpl = None

    if tpl is not None:
        tpl_path = Path(tpl)
        tried = (*tried, str(tpl_path))
        # 🔴 模板库也可能返回目录/失效路径，同样必须 is_file() 把关
        if tpl_path.is_file():
            return WpFileResolution(
                path=tpl_path.resolve(),
                verdict="template_fallback",
                reason=VERDICT_LABELS["template_fallback"],
                raw=raw if raw is None else str(raw),
                tried=tried,
            )

    return WpFileResolution(
        path=None,
        verdict=terminal,
        reason=VERDICT_LABELS[terminal],
        raw=raw if raw is None else str(raw),
        tried=tried,
    )


__all__ = [
    "BACKEND_ROOT",
    "REPO_ROOT",
    "VERDICT_LABELS",
    "WP_FILE_VERDICTS",
    "WpFileResolution",
    "WpFileVerdict",
    "resolve_wp_file",
]
