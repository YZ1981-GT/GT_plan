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

# 🔴 Task 12（workpaper-html-onlyoffice-bidirectional-writeback-closure）：
# 路径边界（Property 42）、文档类型 fail-closed（Property 41）与子码最具体匹配
# （Property 40）三条判据统一由 `app.services.workpaper_sync.canonical_paths`
# 承担，本模块不再自写。该模块是**纯同步、零 ORM**的（否则会破坏本模块
# 「无 DB 依赖」的承诺，见上方 §设计约束）。
from app.services.workpaper_sync.canonical_paths import (
    DocumentTypeMismatchError,
    document_type_of,
    is_within_any_legacy_root,
)

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


WpFileVerdict = Literal[
    "file", "template_fallback", "empty", "missing", "path_rejected", "type_mismatch"
]

#: 判定结果取值域（守卫按它断言，禁止在调用方硬写字面量）
#:
#: 🔴 Task 12 新增两档，且**不得**合并进 `missing`：
#: * `path_rejected` —— 解析结果落在允许根之外（目录穿越 / 项目外绝对路径 /
#:   软链接越界）。语义是「这条路径本身不该被使用」，与「文件丢了」是两件事：
#:   前者要进安全日志与裁决清册，后者只要提示重新生成底稿。
#: * `type_mismatch` —— 命中了文件但类型与 adapter 期望不符（Requirement 9.5 /
#:   Property 41）。若并进 `missing`，「resolver 正确拒绝了父级异类型回退」就与
#:   「这个 wp_code 根本没登记模板」分不开，Requirement 9.4/9.5 无法各自验证。
WP_FILE_VERDICTS: tuple[WpFileVerdict, ...] = (
    "file",
    "template_fallback",
    "empty",
    "missing",
    "path_rejected",
    "type_mismatch",
)

#: 中文原因文案（唯一真源，ZIP 跳过清单与前端提示共用）
VERDICT_LABELS: dict[str, str] = {
    "file": "底稿文件已就绪",
    "template_fallback": "底稿文件缺失，已回退空白模板",
    "empty": "未配置底稿文件路径（file_path 为空）",
    "missing": "底稿文件不存在（路径已配置但磁盘上找不到）",
    "path_rejected": "底稿文件路径越界（不在允许的存储根内，已拒绝）",
    "type_mismatch": "底稿文件类型与所需格式不符（已拒绝回退异类型文件）",
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
    expected_document_type: str | None = None,
) -> WpFileResolution:
    """把 `working_paper.file_path` 解析成一个**可读文件**的绝对路径。

    Args:
        file_path: `working_paper.file_path` 原值（可为 None / 空串 / 相对 / 绝对）。
        wp_code: 底稿编码，仅用于模板库回退；为 None 时不回退。
        allow_template_fallback: 是否允许回退到 `wp_templates` 模板库。
            打包/下载场景建议 True（空白模板 + 清单标注 优于整份缺失）；
            哈希/校验场景应传 False（模板哈希不等于底稿哈希）。
        expected_document_type: `"xlsx"` / `"docx"`。给定时启用类型门
            （Requirement 9.5 / Property 41）：命中的文件类型不符即判 `type_mismatch`，
            **绝不**回退到父级异类型文件。为 None 时不做类型判定（兼容既有调用方）。

    Returns:
        :class:`WpFileResolution`。`path` 非 None 时保证 `is_file()` 为真，
        且落在允许的存储根内（Property 42）。

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
            expected_document_type=expected_document_type,
        )

    # ─── Step 2/3: 逐个候选试 is_file() + 边界 + 类型 ────────────────────
    for candidate in _candidates(str(file_path)):
        tried.append(str(candidate))
        try:
            hit = candidate.is_file()
        except OSError as err:  # 权限 / 路径过长等
            logger.debug("resolve_wp_file: 候选路径检查失败 %s: %s", candidate, err)
            continue
        if not hit:
            continue
        # 🔴 判定顺序：边界 → 类型 → 命中。反过来写会让「项目外绝对路径」先按
        #    类型放行/拒绝，安全判据被业务判据遮蔽（Property 42 是安全门，必须最先）。
        if not is_within_any_legacy_root(candidate):
            logger.error(
                "resolve_wp_file: 路径越界被拒 raw=%r resolved=%s（Property 42）",
                file_path, candidate,
            )
            return WpFileResolution(
                path=None,
                verdict="path_rejected",
                reason=VERDICT_LABELS["path_rejected"],
                raw=str(file_path),
                tried=tuple(tried),
            )
        if expected_document_type is not None and (
            document_type_of(candidate) != expected_document_type
        ):
            logger.error(
                "resolve_wp_file: 文档类型不符被拒 raw=%r resolved=%s 期望=%s 实得=%s"
                "（Property 41：禁止回退异类型文件）",
                file_path, candidate, expected_document_type, document_type_of(candidate),
            )
            return WpFileResolution(
                path=None,
                verdict="type_mismatch",
                reason=VERDICT_LABELS["type_mismatch"],
                raw=str(file_path),
                tried=tuple(tried),
            )
        return WpFileResolution(
            path=candidate,
            verdict="file",
            reason=VERDICT_LABELS["file"],
            raw=str(file_path),
            tried=tuple(tried),
        )

    # ─── Step 4/5: 模板库回退 → missing ─────────────────────────────────
    return _template_fallback(
        wp_code=wp_code,
        allow=allow_template_fallback,
        raw=file_path,
        tried=tuple(tried),
        blank=False,
        expected_document_type=expected_document_type,
    )


def _template_fallback(
    *,
    wp_code: str | None,
    allow: bool,
    raw: str | None,
    tried: tuple[str, ...],
    blank: bool,
    expected_document_type: str | None = None,
) -> WpFileResolution:
    """模板库回退。失败时按 `blank` 区分 `empty` / `missing`；类型不符判 `type_mismatch`。"""
    terminal: WpFileVerdict = "empty" if blank else "missing"

    if not allow or not wp_code:
        return WpFileResolution(
            path=None,
            verdict=terminal,
            reason=VERDICT_LABELS[terminal],
            raw=raw if raw is None else str(raw),
            tried=tried,
        )

    tpl = None
    try:
        # 局部 import：`wp_template_finder` 会读磁盘索引 JSON，
        # 模块级 import 会让本模块在无模板库的环境下不可导入。
        from app.services.wp_template_init_service import find_template_file_any

        tpl = find_template_file_any(wp_code)
    except ImportError as err:
        # 🔴 Task 12：把原来的 `except Exception` 收窄成两类具体异常并升级到 ERROR。
        #    fail-open 的代价在 memory 里是「最贵的一类」：宽泛 except 会把
        #    「函数名写错 / 索引 JSON 结构变了 / 传错参数」全吞成 WARNING，
        #    表现为「这份底稿没有模板」，而四层静态检查全绿。
        logger.error(
            "resolve_wp_file: 模板库模块不可导入 wp_code=%s: %s（部署缺件，非「无模板」）",
            wp_code, err,
        )
    except (OSError, ValueError, KeyError, TypeError) as err:
        logger.error(
            "resolve_wp_file: 模板库回退失败 wp_code=%s: %s（索引损坏或调用形态错，"
            "不是「该 wp_code 无模板」）",
            wp_code, err,
        )

    if tpl is not None:
        tpl_path = Path(tpl)
        tried = (*tried, str(tpl_path))
        # 🔴 模板库也可能返回目录/失效路径，同样必须 is_file() 把关
        if tpl_path.is_file():
            resolved = tpl_path.resolve()
            if not is_within_any_legacy_root(resolved):
                logger.error(
                    "resolve_wp_file: 模板库返回越界路径被拒 wp_code=%s path=%s",
                    wp_code, resolved,
                )
                return WpFileResolution(
                    path=None,
                    verdict="path_rejected",
                    reason=VERDICT_LABELS["path_rejected"],
                    raw=raw if raw is None else str(raw),
                    tried=tried,
                )
            if expected_document_type is not None and (
                document_type_of(resolved) != expected_document_type
            ):
                # Property 41 的核心反例：`find_template_file_any()` 对 B/S 子码会
                # 回退到父级 XLSX。此处显式拒绝，不返回异类型文件。
                logger.error(
                    "resolve_wp_file: 模板库回退命中异类型文件被拒 wp_code=%s path=%s "
                    "期望=%s 实得=%s（Requirement 9.5：禁止回退父级异类型文件）",
                    wp_code, resolved, expected_document_type, document_type_of(resolved),
                )
                return WpFileResolution(
                    path=None,
                    verdict="type_mismatch",
                    reason=VERDICT_LABELS["type_mismatch"],
                    raw=raw if raw is None else str(raw),
                    tried=tried,
                )
            return WpFileResolution(
                path=resolved,
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


def resolve_template_docx(wp_code: str) -> WpFileResolution:
    """按最具体 wp_code 解析 DOCX 模板（Property 40/41 的存量入口）。

    与 `resolve_wp_file(..., expected_document_type="docx")` 的区别：本函数**不看**
    `working_paper.file_path`，只走模板库，供「只要模板、不要底稿实例」的场景
    （Word config / 通用 DOCX 裁决清册）使用。类型不符一律 `type_mismatch`，
    绝不返回父级 XLSX。

    🔴 `blank=False` 是刻意的：本函数根本不读 `file_path`，所以「找不到」只能是
    **模板缺失**（`missing`），不能是 `empty`（其文案为「未配置底稿文件路径
    （file_path 为空）」）。传 `blank=True` 会让 Requirement 9.5 要求的「模板缺失
    显式报错」在清册里显示成「没配路径」，把部署缺件误导成数据没填。
    """
    return _template_fallback(
        wp_code=wp_code,
        allow=True,
        raw=None,
        tried=(),
        blank=False,
        expected_document_type="docx",
    )


__all__ = [
    "BACKEND_ROOT",
    "REPO_ROOT",
    "VERDICT_LABELS",
    "WP_FILE_VERDICTS",
    "WpFileResolution",
    "WpFileVerdict",
    "resolve_wp_file",
    "resolve_template_docx",
]
