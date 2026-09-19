# -*- coding: utf-8 -*-
"""canonical 路径与文档类型判据 —— **纯同步、零 ORM、零 DB** 的单一真源。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 1 Task 12
Requirements: 9.1, 9.2, 9.4, 9.5, 9.6, 9.11, 9.12
Properties: P40 / P41 / P42

═══ 为什么必须与 `artifacts.py` 分成两个模块 ═══

`artifacts.py`（Task 11）导入 `sqlalchemy` 与 `AsyncSession`；而
`app/services/wp_export/wp_file_resolver.py` 的模块 docstring 明文承诺
「纯同步、无 DB、无 ORM 依赖」—— 让它 import 一个拖进 SQLAlchemy 的模块就违约。

但「路径边界判据」**只能有一份实现**（否则改一处另一处不红，正是本 spec 要消灭的
分叉）。因此本模块承担判据本体，`artifacts.py::CanonicalArtifactRepository._resolve_within`
改为**调用**本模块并把异常包成它自己的 `ArtifactPathError`（保留 Task 11 的
error_code 契约）。方向是「ORM 层依赖纯层」，不是反过来。

═══ 三条判据的来源 ═══

* **P42 路径安全**：判据是 `os.path.realpath` **之后**仍在 root 内。只做字符串
  前缀比较拦不住软链接越界（Task 7 fs7 真建了链接，realpath 解析到 `%TEMP%`）。
* **P40 子码最具体优先**：Requirement 9.4 明确「对**所有**适用子码按最具体
  wp_code 优先解析 DOCX，不得只对 A 类特殊处理」。既有
  `wp_template_finder.find_template_file_any()` 的 `is_sub_code` 正则写死
  `^A\\d+-\\d+` ⇒ `B12-1` 这类子码直接落到「主程序表：xlsx 优先」分支并抢到父级
  XLSX。本模块的 :func:`is_sub_code` 用与字母无关的 `^[A-Z]+\\d+-` 判据。
* **P41 缺失不异类型回退**：`expected_document_type` 指定后，解析器只允许该类型的
  扩展名；命中别的类型一律 :class:`DocumentTypeMismatchError`，**绝不**返回父级
  异类型文件。「缺失」与「类型不符」是两个不同 verdict，不可合并成一个布尔。
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from app.services.workpaper_sync.models import SyncDomainError

# ═══════════════════════════════════════════════════════════════════════════
# 0. 路径基准
# ═══════════════════════════════════════════════════════════════════════════

#: 本文件位于 backend/app/services/workpaper_sync/canonical_paths.py
#:   parents[0]=workpaper_sync parents[1]=services parents[2]=app parents[3]=backend
BACKEND_ROOT: Final[Path] = Path(__file__).resolve().parents[3]
REPO_ROOT: Final[Path] = BACKEND_ROOT.parent

#: 运行时权威模板源（Requirement 9.1）。只读，本 spec 全程不写。
TEMPLATE_ROOT: Final[Path] = BACKEND_ROOT / "wp_templates"


# ═══════════════════════════════════════════════════════════════════════════
# 1. 异常（每个都带 error_code；禁止被宽泛 except 降级成成功）
# ═══════════════════════════════════════════════════════════════════════════


class PathBoundaryError(SyncDomainError):
    """路径越界（Property 42）：目录穿越、项目外绝对路径、软链接越界、跨 root 复用。"""

    error_code = "path_boundary_rejected"

    def __init__(self, *, reason: str, detail: str) -> None:
        self.reason = reason
        self.detail = detail
        super().__init__(f"{reason}：{detail}")


class DocumentTypeMismatchError(SyncDomainError):
    """解析到的文件类型与 adapter 期望不符（Requirement 9.5 / Property 41）。

    🔴 与 :class:`TemplateMissingError` **必须**是两个类型。二者都会让调用方
    「拿不到文件」，但语义完全不同：
    * `TemplateMissingError` = 这个 wp_code 根本没有登记模板（清册里要补一行）；
    * `DocumentTypeMismatchError` = 有文件但类型错（resolver 正确地拒绝了父级
      异类型回退，清册要记的是「已按最具体子码 fail closed」）。

    共用一个异常类型时，「不异类型回退」这条判据会被「缺失」分支永久遮蔽 ——
    把 type 门短路掉之后，missing 分支抛同一类型，变异检验判 GREEN。
    """

    error_code = "document_type_mismatch"

    def __init__(self, *, expected: str, observed: str, path: str) -> None:
        self.expected = expected
        self.observed = observed
        self.path = path
        super().__init__(
            f"文档类型不符：期望 {expected}，实得 {observed}（{path}）；"
            "resolver 不得回退到父级异类型文件"
        )


class TemplateMissingError(SyncDomainError):
    """按最具体 wp_code 找不到任何该类型的模板（Requirement 9.5）。"""

    error_code = "template_missing"

    def __init__(self, *, wp_code: str, expected: str) -> None:
        self.wp_code = wp_code
        self.expected = expected
        super().__init__(
            f"wp_code={wp_code!r} 没有登记 {expected} 模板；"
            "必须进入裁决清册，禁止回退父级异类型文件"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 2. 路径边界判据（Property 42 的唯一实现）
# ═══════════════════════════════════════════════════════════════════════════


def resolve_within_root(root: Path | str, relative: str, *, boundary: str) -> Path:
    """把 root 内相对路径解析成绝对路径；越界即 :class:`PathBoundaryError`。

    Args:
        root: 边界根（项目根 / storage base / 模板库根）。
        relative: 相对路径（允许 Windows 反斜杠）。
        boundary: 诊断用边界名，进 `reason`（`outside_{boundary}`）。

    判据是 `realpath` 之后仍等于 root 或以 root 为祖先。`realpath` 会把
    `..`、软链接、8.3 短名一并展开，是唯一能同时拦住三类越界的写法。
    """
    if relative is None or not str(relative).strip():
        raise PathBoundaryError(
            reason="empty_relative_path", detail="relative_path 不得为空或纯空白"
        )
    root_real = Path(os.path.realpath(str(root)))
    candidate = Path(os.path.realpath(os.path.join(str(root_real), str(relative))))
    if candidate != root_real and root_real not in candidate.parents:
        raise PathBoundaryError(
            reason=f"outside_{boundary}",
            detail=f"relative={relative!r} 解析为 {candidate}，不在 {root_real} 内",
        )
    return candidate


def join_within_root(root: Path | str, relative: str, *, boundary: str) -> Path:
    """边界判据同 :func:`resolve_within_root`，但返回**未 realpath 展开**的拼接结果。

    两者的分工：

    * :func:`resolve_within_root` —— 需要「文件系统上的规范路径」时用（artifact
      去重、md5 比对）；
    * 本函数 —— 需要「保持调用方给的 root 形态」时用（canonical 目录/文件路径）。

    🔴 存在的理由不是风格：Windows 的 `%TEMP%` 常挂在 junction 下，`realpath` 会把
    `C:\\Users\\x\\AppData\\Local\\Temp\\...` 展开成另一条串。若 canonical 路径构造
    带着 realpath 展开，`monkeypatch.setattr(settings, "STORAGE_ROOT", str(tmp_path))`
    的调用方就会拿到与 `tmp_path / ...` 不相等的路径 —— 表现为「路径突然被改写」这类
    极难查的假红。

    安全性不因此下降：边界判据仍由 :func:`resolve_within_root` 在 **realpath 之后**
    执行（软链接越界照样被拒），本函数只是把「返回哪种表示」与「判据」解耦。
    """
    resolve_within_root(root, relative, boundary=boundary)
    return Path(root) / Path(str(relative).replace("\\", "/"))


def assert_within_root(root: Path | str, absolute: Path | str, *, boundary: str) -> Path:
    """断言一个**已是绝对**的路径落在 root 内（跨 project / 跨 root 复用判据）。"""
    root_real = Path(os.path.realpath(str(root)))
    target = Path(os.path.realpath(str(absolute)))
    if target != root_real and root_real not in target.parents:
        raise PathBoundaryError(
            reason=f"outside_{boundary}",
            detail=f"{target} 不在 {root_real} 内",
        )
    return target


def is_within_root(root: Path | str, absolute: Path | str) -> bool:
    """布尔版边界判据（供需要「不抛异常只分档」的调用方，如 legacy resolver）。"""
    try:
        assert_within_root(root, absolute, boundary="root")
    except PathBoundaryError:
        return False
    return True


#: legacy 项目存储根的目录名（`backend/storage/projects/{project_id}`）。
#: 单一真源：WOPI 云端双写、`WpStorageService` 归档都必须从这里取，不得各自拼
#: `Path(__file__).parent.parent.parent / "storage" / "projects"`（那是第二权威，
#: 且一旦文件搬家就静默指向错目录）。
LEGACY_STORAGE_DIRNAME: Final[str] = "storage"
LEGACY_PROJECTS_DIRNAME: Final[str] = "projects"


def legacy_storage_root() -> Path:
    """legacy 项目存储根（`backend/storage/projects`）—— 单一真源。"""
    return BACKEND_ROOT / LEGACY_STORAGE_DIRNAME / LEGACY_PROJECTS_DIRNAME


def legacy_project_storage_root(project_id: object) -> Path:
    """某个项目的 legacy 存储根（`backend/storage/projects/{project_id}`）。"""
    return legacy_storage_root() / str(project_id)


#: legacy `working_paper.file_path` 允许落地的根集合（按优先级）。
#: 只有这三个根：模板库（TEMPLATE_REL 形态）、backend（STORAGE_REL 形态）、
#: 仓库根（历史 ABSOLUTE 形态）。`/tmp/...` 这类历史脏数据落在三者之外 ⇒ 被判越界。
def legacy_roots() -> tuple[Path, ...]:
    """legacy 路径边界根（去重保序）。

    做成函数而非模块级常量：`Path.cwd()` 在导入期取值会被 `monkeypatch.chdir`
    骗过（导入一次、后续 chdir 不生效）——`wp_file_resolver` 已记录过同一个坑。
    """
    seen: list[Path] = []
    for base in (Path.cwd(), BACKEND_ROOT, REPO_ROOT):
        real = Path(os.path.realpath(str(base)))
        if real not in seen:
            seen.append(real)
    return tuple(seen)


def is_within_any_legacy_root(absolute: Path | str) -> bool:
    """legacy 解析结果是否落在允许的根内（Property 42 对存量路径的落地形态）。"""
    return any(is_within_root(root, absolute) for root in legacy_roots())


# ═══════════════════════════════════════════════════════════════════════════
# 3. 文档类型判据（Property 41）
# ═══════════════════════════════════════════════════════════════════════════

#: document_type → 允许的扩展名集合。`xlsm` 与 `xlsx` 同族，`doc` 与 `docx` 同族。
DOCUMENT_TYPE_SUFFIXES: Final[dict[str, frozenset[str]]] = {
    "xlsx": frozenset({".xlsx", ".xlsm"}),
    "docx": frozenset({".docx", ".doc"}),
}

_SUFFIX_TO_TYPE: Final[dict[str, str]] = {
    suffix: doc_type
    for doc_type, suffixes in DOCUMENT_TYPE_SUFFIXES.items()
    for suffix in suffixes
}


def document_type_of(path: Path | str) -> str | None:
    """按扩展名判文档类型；未知扩展名返回 None（不猜）。"""
    return _SUFFIX_TO_TYPE.get(Path(str(path)).suffix.lower())


def assert_document_type(path: Path | str, expected: str) -> None:
    """断言文件类型 == expected，否则 :class:`DocumentTypeMismatchError`。

    Requirement 9.5：类型与 adapter 不符 SHALL 显式报错，**禁止回退父级异类型文件**。
    """
    if expected not in DOCUMENT_TYPE_SUFFIXES:
        raise DocumentTypeMismatchError(
            expected=expected, observed="<unknown-expected>", path=str(path)
        )
    observed = document_type_of(path)
    if observed != expected:
        raise DocumentTypeMismatchError(
            expected=expected, observed=observed or Path(str(path)).suffix.lower() or "<none>",
            path=str(path),
        )


# ═══════════════════════════════════════════════════════════════════════════
# 4. 子码最具体匹配（Property 40）
# ═══════════════════════════════════════════════════════════════════════════

#: 子码判据：**字母类无关**。`A9-1` / `B12-1` / `S33-REV` 都是子码。
#: 既有 `wp_template_finder` 写死 `^A\d+-\d+` ⇒ B/S 子码被当主码处理并抢父级 XLSX。
_SUB_CODE_RE: Final[re.Pattern[str]] = re.compile(r"^[A-Z]+\d+-[0-9A-Za-z]")


def is_sub_code(wp_code: str) -> bool:
    """是否为子码（`{字母}{数字}-{...}`）。判据与字母类无关（Requirement 9.4）。"""
    if not wp_code or not isinstance(wp_code, str):
        return False
    return bool(_SUB_CODE_RE.match(wp_code.strip().upper()))


def parent_code_of(wp_code: str) -> str | None:
    """子码的父码（`B12-1` → `B12`）；主码返回 None。"""
    if not is_sub_code(wp_code):
        return None
    return wp_code.strip().split("-", 1)[0]


def specificity_rank(candidate_code: str, wp_code: str) -> int:
    """候选 wp_code 相对目标的「具体度」：越大越具体，-1 表示不适用。

    * 完全相等 → 最高（长度即具体度上限）
    * 目标是候选的**子码**（候选是父码）→ 按候选长度给低分
    * 其余 → -1（不适用，禁止参与匹配）
    """
    a = (candidate_code or "").strip().upper()
    b = (wp_code or "").strip().upper()
    if not a or not b:
        return -1
    if a == b:
        return len(a) + 1000
    if b.startswith(f"{a}-"):
        return len(a)
    return -1


@dataclass(frozen=True)
class TemplateCandidate:
    """一个候选模板文件（供最具体匹配排序）。"""

    wp_code: str
    path: Path

    @property
    def document_type(self) -> str | None:
        return document_type_of(self.path)


def pick_most_specific(
    candidates: list[TemplateCandidate], *, wp_code: str, expected_document_type: str
) -> TemplateCandidate:
    """在候选里按「最具体 wp_code + 类型必须相符」挑一个；否则 fail closed。

    🔴 判定顺序刻意是 **先按类型过滤、再按具体度排序**，且「有异类型候选但无同类型
    候选」必须抛 :class:`DocumentTypeMismatchError` 而不是 :class:`TemplateMissingError`。
    反过来写（先排序后判类型）会让「父级 XLSX 抢占子码 DOCX」这条判据落到
    missing 分支上 —— Requirement 9.4 与 9.5 就分不开了。
    """
    if expected_document_type not in DOCUMENT_TYPE_SUFFIXES:
        raise DocumentTypeMismatchError(
            expected=str(expected_document_type), observed="<unknown-expected>", path="<candidates>"
        )
    applicable = [
        c for c in candidates
        if specificity_rank(c.wp_code, wp_code) >= 0 and c.path.is_file()
    ]
    typed = [c for c in applicable if c.document_type == expected_document_type]
    if not typed:
        if applicable:
            worst = sorted(
                applicable,
                key=lambda c: (-specificity_rank(c.wp_code, wp_code), len(c.path.name)),
            )[0]
            raise DocumentTypeMismatchError(
                expected=expected_document_type,
                observed=worst.document_type or worst.path.suffix.lower() or "<none>",
                path=str(worst.path),
            )
        raise TemplateMissingError(wp_code=wp_code, expected=expected_document_type)
    typed.sort(key=lambda c: (-specificity_rank(c.wp_code, wp_code), len(c.path.name)))
    best = typed[0]
    best_rank = specificity_rank(best.wp_code, wp_code)
    exact = [c for c in typed if specificity_rank(c.wp_code, wp_code) == best_rank]
    # 同具体度多命中：按文件名长度取最短（与既有 finder 的「最短文件名优先」一致），
    # 但**不允许**跨具体度回退 —— 父码候选永不抢占子码候选。
    chosen = exact[0]
    assert_within_root(TEMPLATE_ROOT, chosen.path, boundary="template_root")
    assert_document_type(chosen.path, expected_document_type)
    return chosen


# ═══════════════════════════════════════════════════════════════════════════
# 5. 运行态 canonical 目录（Task 58 / Requirement 9.2 · 9.3）
# ═══════════════════════════════════════════════════════════════════════════
#
# 🔴 为什么这几行必须在**本模块**而不是在 router 里
#
# Requirement 9.3 点名的分叉是真实存在的（2026-08-29 实测）：
#
#   读侧 `wp_onlyoffice_router._onlyoffice_storage_dir()`
#     → `{STORAGE_ROOT}/projects/{project_id}/workpapers/onlyoffice/{wp_code}.docx`
#   写侧 word-template callback 分支
#     → `Path(f"storage/{project_id}/workpapers/{wp_code}.docx")`   ← 相对 CWD！
#
# 两者既缺 `projects/` 段也缺 `onlyoffice/` 段，且写侧是**相对路径** ⇒ CWD 一变落
# 到另一个根。磁盘实测后果：`backend/storage/{pid}/workpapers/*.docx` 134 份 +
# `storage/{pid}/workpapers/*.docx` 25 份，共 **159 份 OO 存盘落在读侧永不查看的位置**，
# 而读侧的 `.../workpapers/onlyoffice/` 下只有 16 份 docx。审计师在 OO 里改的 Word
# 底稿因此「保存成功但下次打开又是旧的」。
#
# 把段名与绝对化规则收敛到这里，读写两侧都只能调同一个函数，分叉在**构造上**消失。

#: 运行态 canonical 目录的固定段（单一真源；禁止在 router / service 里再拼一次）。
ONLYOFFICE_PROJECTS_DIRNAME: Final[str] = "projects"
ONLYOFFICE_WORKPAPERS_DIRNAME: Final[str] = "workpapers"
ONLYOFFICE_EDITOR_DIRNAME: Final[str] = "onlyoffice"

#: `document_type` → canonical 落盘扩展名。与 :data:`DOCUMENT_TYPE_SUFFIXES` 的
#: **接受集**刻意分开：接受 `.xlsm`/`.doc`（存量模板确实有），但新落盘只用主扩展名。
CANONICAL_SUFFIX_BY_TYPE: Final[dict[str, str]] = {"xlsx": ".xlsx", "docx": ".docx"}

#: wp_code 作为**文件名段**的合法形态。放行字母/数字/`-`/`_`/`.`，其余（含 `/`、
#: `\`、`..`、空格）一律拒 —— 它会被直接拼进文件名，是最典型的穿越入口。
_WP_CODE_FILENAME_RE: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def assert_wp_code_segment(wp_code: str, *, label: str = "wp_code") -> str:
    """断言 wp_code 可安全用作**文件名段**；否则 :class:`PathBoundaryError`。

    🔴 必须作为独立可调用判据存在，而不是内联在 :func:`onlyoffice_canonical_path`
    里：调用方（`WordCanonicalResolver.resolve`）要在**模板解析之前**先跑安全门。
    内联时 `wp_code="../B2-1"` 会先在模板解析阶段抛 `TemplateMissingError`（没有
    叫 `../B2-1` 的载体），把路径穿越判据永久遮蔽成不可达分支 —— 2026-08-29 变异
    检验实测到这个形态。安全门必须最先，与 `wp_file_resolver` 里「边界 → 类型 →
    命中」的同一理由。
    """
    code = (wp_code or "").strip()
    if not _WP_CODE_FILENAME_RE.match(code):
        raise PathBoundaryError(
            reason=f"invalid_{label}_segment",
            detail=(
                f"{label} 段形态非法（禁止路径分隔符 / `..` / 空白，它会被直接拼进"
                f"文件名）: {wp_code!r}"
            ),
        )
    return code


def storage_root() -> Path:
    """`settings.STORAGE_ROOT` 的 **CWD 免疫**绝对化。

    生产 `STORAGE_ROOT='./storage'` 且 `start-dev.bat` 里 `cd /d backend` ⇒ 实际是
    `backend/storage`。相对值在这里锚到 :data:`BACKEND_ROOT`，取值与生产逐字节相同，
    但从仓库根跑脚本/测试时不再漂到 `<repo>/storage`（那正是 25 份孤儿文件的成因）。

    settings 是 pydantic 配置对象，不引入 ORM/DB，不破坏本模块「纯同步、零 ORM」的承诺。
    """
    from app.core.config import settings  # 局部 import：保持本模块可被纯路径场景单测

    raw = Path(str(settings.STORAGE_ROOT))
    return raw if raw.is_absolute() else (BACKEND_ROOT / raw)


def project_canonical_root(project_id: object) -> Path:
    """项目独立存储根（Requirement 9.2：不得写回模板库、不得跨项目共享）。"""
    pid = assert_wp_code_segment(str(project_id), label="project_id")
    return join_within_root(
        storage_root(),
        f"{ONLYOFFICE_PROJECTS_DIRNAME}/{pid}",
        boundary="storage_root",
    )


def onlyoffice_canonical_dir(project_id: object) -> Path:
    """某项目的 OO 运行态 canonical 目录 —— 读写两侧唯一入口。"""
    return join_within_root(
        project_canonical_root(project_id),
        f"{ONLYOFFICE_WORKPAPERS_DIRNAME}/{ONLYOFFICE_EDITOR_DIRNAME}",
        boundary="project_canonical_root",
    )


def onlyoffice_canonical_path(
    project_id: object, wp_code: str, *, document_type: str
) -> Path:
    """某项目某 wp_code 的 canonical 运行态文件绝对路径。

    Args:
        document_type: `"xlsx"` / `"docx"`；决定落盘扩展名并被
            :func:`assert_document_type` 复核（Property 41 在路径层的落点）。

    Raises:
        PathBoundaryError: wp_code 含路径分隔符 / `..` / 空白，或解析越界。
        DocumentTypeMismatchError: `document_type` 未登记。
    """
    if document_type not in CANONICAL_SUFFIX_BY_TYPE:
        raise DocumentTypeMismatchError(
            expected=str(document_type), observed="<unknown-expected>", path="<canonical>"
        )
    code = assert_wp_code_segment(wp_code)
    target = join_within_root(
        onlyoffice_canonical_dir(project_id),
        f"{code}{CANONICAL_SUFFIX_BY_TYPE[document_type]}",
        boundary="onlyoffice_canonical_dir",
    )
    assert_document_type(target, document_type)
    return target


__all__ = [
    "BACKEND_ROOT",
    "REPO_ROOT",
    "TEMPLATE_ROOT",
    "PathBoundaryError",
    "DocumentTypeMismatchError",
    "TemplateMissingError",
    "resolve_within_root",
    "join_within_root",
    "assert_within_root",
    "is_within_root",
    "LEGACY_STORAGE_DIRNAME",
    "LEGACY_PROJECTS_DIRNAME",
    "legacy_storage_root",
    "legacy_project_storage_root",
    "legacy_roots",
    "is_within_any_legacy_root",
    "DOCUMENT_TYPE_SUFFIXES",
    "document_type_of",
    "assert_document_type",
    "is_sub_code",
    "parent_code_of",
    "specificity_rank",
    "TemplateCandidate",
    "pick_most_specific",
    # Task 58：运行态 canonical 目录（读写两侧唯一入口）
    "ONLYOFFICE_PROJECTS_DIRNAME",
    "ONLYOFFICE_WORKPAPERS_DIRNAME",
    "ONLYOFFICE_EDITOR_DIRNAME",
    "CANONICAL_SUFFIX_BY_TYPE",
    "assert_wp_code_segment",
    "storage_root",
    "project_canonical_root",
    "onlyoffice_canonical_dir",
    "onlyoffice_canonical_path",
]
