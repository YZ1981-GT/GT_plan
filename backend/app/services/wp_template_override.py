"""Excel 模板覆盖层 —— 常量、异常与结构性断言。

## 这个模块解决什么

权威模板目录 ``backend/wp_templates/`` 是「所有项目所有底稿的生成基线」，
Requirement 9.9 要求它运行时只读（实测成立：全 ``backend/app/**`` 扫描含
``wp_templates`` 且含 write/save/copy/unlink/mkdir/open 的行，**0 条真实写入**）。

而审计师需要能改模板。这两件事不互斥 —— 前者约束的是一个**具体目录**，后者需要的是
一个**解析结果**。做法是在权威目录之上叠一层可版本化的覆盖：编辑产物落在
:data:`OVERRIDE_ROOT`，``wp_template_finder`` 增加一级优先解析。

## 本文件的范围（Wave 1）

只有常量、异常与**零 DB 零写入**的结构性断言。解析（``resolve_template``）、
落盘（``stage_override``）、版本化分别在 Wave 2 / Wave 3。

## 为什么互斥断言在 import 期执行

照 ``projection_lane_registry`` 的范式：接线错误要在 **import 期**就暴露，而不是等到
某个请求真的去写盘。若 :data:`OVERRIDE_ROOT` 与权威目录互相包含，那么"覆盖层写入"
与"写权威目录"就是同一件事，Requirement 1.1 结构性失守 —— 这种错误不该靠单测碰巧
覆盖到，应该让进程起不来。
"""

from __future__ import annotations

import dataclasses
import functools
import hashlib
import io
import logging
import os
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Final
from uuid import UUID

from app.models.template_library_models import TemplateLevel
from app.services.workpaper_sync.models import SyncDomainError

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════
# 1. 根目录常量
# ═══════════════════════════════════════════════════════════════════════════

#: ``backend/`` —— 本文件在 ``backend/app/services/`` 下，上三级即后端根。
#: 与 ``wp_template_finder.BACKEND_DIR`` 同一推导，不 import 它以免 Wave 2 接线
#: （finder 反向调用本模块）时形成循环。两处一致性由判据锁死，不靠约定。
BACKEND_DIR: Final[Path] = Path(__file__).resolve().parent.parent.parent

#: 权威模板目录 —— 运行时只读，476 条索引。本模块**永不**把它当写入目标。
AUTHORITATIVE_ROOT: Final[Path] = BACKEND_DIR / "wp_templates"

#: 覆盖层根。裁决见 design.md Gate 1：
#:
#: * ``.gitignore`` 已含 ``backend/storage/`` ⇒ 覆盖层文件不入 git，与
#:   ``working_paper.file_path`` 指向的运行时产物同等对待。
#: * ``backend/storage/`` 是后端进程**实际**的 storage 落点（后端 cwd 是 ``backend/``，
#:   ``STORAGE_ROOT=./storage``），已有 ``projects`` / ``workpapers`` / ``attachments``
#:   等具名子目录，增设一个具名子目录符合既有布局惯例。
#: * 备份扫描面覆盖已由 Task 101 落实（见 ``backend/scripts/_storage_roots.py``）——
#:   原备份脚本按 cwd 解析 ``./storage``，从仓库根跑时指向 ``<repo>/storage``，
#:   与运行时落点差 2027 个文件，覆盖层会在恢复时静默丢失。已修正为相对
#:   ``backend/`` 解析并把历史根一并纳入。
OVERRIDE_ROOT: Final[Path] = BACKEND_DIR / "storage" / "template_overrides"

#: 可在浏览器内编辑的格式。裁决见 design.md Gate 3：索引声明的 17 份 xlsm
#: **17/17 全含 ``vbaProject.bin``**，而 OO 往返是否保留 VBA 未取证 ⇒ 保守排除。
#: 🔴 这**不是**「可被覆盖的格式」—— 覆盖层本身格式无关，476/476 都可覆盖可回滚
#: （Requirement 7.2）。本常量只门控"产生覆盖文件的方式之一"。
EDITABLE_FORMATS: Final[frozenset[str]] = frozenset({".xlsx"})

#: 解析优先级，靠前者胜。作用域**复用** :class:`TemplateLevel`（裁决见 Gate 2）：
#: 平台无独立事务所实体（``backend/app/models/**`` 无 ``Firm``/``Org``/``Tenant``
#: 任何类），但该枚举已定义这三档 ⇒ 自造 ``OverrideScope`` 是重复造词。
SCOPE_PRIORITY: Final[tuple[TemplateLevel, ...]] = (
    TemplateLevel.project,
    TemplateLevel.group_custom,
    TemplateLevel.firm_default,
)


# ═══════════════════════════════════════════════════════════════════════════
# 2. 异常（fail-visible；不设 fail-open 分支）
# ═══════════════════════════════════════════════════════════════════════════
#
# 🔴 解析失败时**不得**静默回落到权威文件 —— 那会把「覆盖文件损坏」伪装成
#    「本来就没有覆盖」，审计师看到的是旧模板却以为是新的。解析层只在**确实没有
#    当前版本**时回落；文件存在但读不出、sha256 不符、版本行自相矛盾三种情形一律抛。


class TemplateOverrideError(SyncDomainError):
    """模板覆盖层基类。"""

    error_code = "template_override_error"


class OverrideRootEscapeError(TemplateOverrideError):
    """写入目标越出覆盖层根。

    两条触发路径：

    1. 单次写入的目标 ``resolve()`` 后不以 :data:`OVERRIDE_ROOT` 为前缀
       （``..`` 穿越 / 绝对路径 / 符号链接）。
    2. :data:`OVERRIDE_ROOT` 与 :data:`AUTHORITATIVE_ROOT` 互相包含 —— 此时
       **每一次**覆盖层写入都同时是写权威目录，结构性失守。

    降级即等于允许写权威目录，Requirement 1.1 直接失守。
    """

    error_code = "template_override_root_escape"


class OverrideExtensionMismatchError(TemplateOverrideError):
    """覆盖文件扩展名与权威文件不一致。

    用 xlsx 覆盖 docx 会让下游 componentType 分发错位。
    """

    error_code = "template_override_extension_mismatch"


class OverrideFormatNotEditableError(TemplateOverrideError):
    """目标格式不在 :data:`EDITABLE_FORMATS` 内（docx / doc / xls / xlsm）。

    xlsm 含宏且 OO 保留性未取证，放过去等于赌它保留。
    """

    error_code = "template_override_format_not_editable"


class OverrideScopeUnknownError(TemplateOverrideError):
    """``scope`` 不在 :class:`TemplateLevel` 三档内 —— 未知作用域会让解析优先级无定义。"""

    error_code = "template_override_scope_unknown"


class OverrideCurrentVersionAmbiguousError(TemplateOverrideError):
    """同作用域查出 >1 条 ``is_current``。

    部分唯一索引应已挡住；查出来说明索引缺失或被绕过，必须响亮失败而不是取第一条。
    """

    error_code = "template_override_current_version_ambiguous"


#: 全部异常类，供「error_code 两两不同」判据遍历。
OVERRIDE_ERRORS: Final[tuple[type[TemplateOverrideError], ...]] = (
    TemplateOverrideError,
    OverrideRootEscapeError,
    OverrideExtensionMismatchError,
    OverrideFormatNotEditableError,
    OverrideScopeUnknownError,
    OverrideCurrentVersionAmbiguousError,
)


# ═══════════════════════════════════════════════════════════════════════════
# 3. 结构性断言（零 DB、零写入）
# ═══════════════════════════════════════════════════════════════════════════


def _is_within(child: Path, ancestor: Path) -> bool:
    """``child`` 是否落在 ``ancestor`` 的递归面内（含相等）。

    用 ``relative_to`` 而不是字符串前缀比较 —— ``/a/bc`` 不是 ``/a/b`` 的后代，
    但字符串前缀判断会误判为是。
    """
    try:
        child.relative_to(ancestor)
    except ValueError:
        return False
    return True


def assert_override_root_disjoint_from_authoritative(
    override_root: Path | None = None,
    authoritative_root: Path | None = None,
) -> None:
    """断言覆盖层根与权威目录**互不包含**。

    三种失守情形均抛 :class:`OverrideRootEscapeError`：

    * 覆盖层根是权威目录的**后代**（如 ``wp_templates/overrides``）
    * 覆盖层根是权威目录的**祖先**（如 ``backend/``）
    * 两者**相等**

    参数默认取模块常量；给参数只为让判据能构造三种情形，无参调用行为与
    design.md 的签名一致。
    """
    override = (override_root or OVERRIDE_ROOT).resolve()
    authoritative = (authoritative_root or AUTHORITATIVE_ROOT).resolve()

    if override == authoritative:
        raise OverrideRootEscapeError(
            f"覆盖层根与权威模板目录相同：{override}。"
            "此时每一次覆盖层写入都是写权威目录，Requirement 1.1 结构性失守。"
        )
    if _is_within(override, authoritative):
        raise OverrideRootEscapeError(
            f"覆盖层根 {override} 落在权威模板目录 {authoritative} 之内。"
            "覆盖层写入会直接改动权威基线。"
        )
    if _is_within(authoritative, override):
        raise OverrideRootEscapeError(
            f"权威模板目录 {authoritative} 落在覆盖层根 {override} 之内。"
            "覆盖层的清理/回滚操作会波及权威基线。"
        )


def assert_error_codes_distinct() -> None:
    """断言 :data:`OVERRIDE_ERRORS` 的 ``error_code`` 两两不同。

    共用 ``error_code`` 会让调用方无法区分该重试、该改扩展名、还是该报运维 ——
    与 ``ScopeIntegrityError`` / ``QuarantinedIncomingError`` 分家的理由同源。
    """
    seen: dict[str, str] = {}
    for exc in OVERRIDE_ERRORS:
        code = exc.error_code
        if code in seen:
            raise AssertionError(
                f"error_code 重复：{exc.__name__} 与 {seen[code]} 同为 {code!r}"
            )
        seen[code] = exc.__name__


# ═══════════════════════════════════════════════════════════════════════════
# 4. 只读解析（Requirement 2.1 / 2.2 / 2.4 / 2.5）
# ═══════════════════════════════════════════════════════════════════════════
#
# ## 🔴 为什么"当前版本"由文件系统布局承载，而不是解析时查 DB
#
# design.md 的 ``resolve_template`` 签名是**同步**的、没有 session 参数；而
# ``wp_template_finder`` 的三个公开入口也是同步的，被 ``wp_template_init_service``
# 等同步调用。Requirement 2.3 要求这三个入口签名与返回类型不变（零回归）⇒ 覆盖层
# 解析**必须同步**，不能在解析路径里 await 一个 async session。
#
# 于是布局本身编码"当前版本"：
#
#     OVERRIDE_ROOT/{scope_seg}/{wp_code}/{authoritative_stem}/current{ext}
#     OVERRIDE_ROOT/{scope_seg}/{wp_code}/{authoritative_stem}/versions/{version_id}{ext}
#
#     scope_seg = firm_default | group_custom/{group_id} | project/{project_id}
#
# 🔴 **必须**按权威文件的 stem 再分一级目录，不能只到 ``{wp_code}/current{ext}``。
# 原因：一个 wp_code 可以对多份权威文件（``D2`` 的 ``D2-1至D2-4 …xlsx`` 等），
# ``find_template_file`` 取其中的"主"文件而 ``find_all_template_files`` 取全部。
# 若覆盖层只按 wp_code 定位，覆盖主文件后 ``find_template_file`` 会返回覆盖文件、
# ``find_all_template_files`` 仍返回全部权威文件 —— **同一份模板在两个入口下不一致**。
# 按 stem 分目录让三个入口共用同一套定位规则。
#
# ``current{ext}`` 存在 = 该作用域有当前版本。DB 版本表（Wave 3）承载元数据
# （作者 / 时间 / 父版本 / sha256）与并发唯一性，是**审计记录**；``current{ext}``
# 是它的同步可读投影。
#
# 这确实是两处状态，风险要说清：两侧可能不一致。缓解是把"写 current + 写版本行"
# 收在 ``stage_override`` / 回滚 / 删除**同一个函数**里，并由 Wave 3 的
# Property 16~19 断言两侧一致。**不接受**「解析时以 DB 为准、写入时以文件为准」
# 这种各读一侧的形态 —— 那才是真正会漂移的。
#
# ## 不 fail-open
#
# 解析只在**确实没有当前版本**（``current{ext}`` 不存在）时回落到下一层。
# 文件存在但读不出一律抛 —— 静默回落会把「覆盖文件损坏」伪装成「本来就没有覆盖」，
# 审计师看到旧模板却以为是新的。

#: 当前版本的文件名主干。``current.xlsx`` / ``current.docx`` 等。
CURRENT_STEM: Final[str] = "current"

#: 历史版本存放的子目录名。
VERSIONS_DIRNAME: Final[str] = "versions"

#: 版本 id 标记文件的后缀 —— ``current.version`` 里存着当前版本的 UUID。
CURRENT_VERSION_MARKER_SUFFIX: Final[str] = ".version"

#: ``current.*`` 里**不是模板文件**的那些后缀。
#:
#: 🔴 这个集合是必须的，不是防御性冗余：解析用 ``glob("current.*")`` 找当前版本，
#:    而 ``activate_staged_override`` 在同目录写 ``current.version``。第一版没排除它，
#:    于是 glob 拿到两个文件、判「多个当前版本」并抛 ``OverrideCurrentVersionAmbiguousError``
#:    —— 一激活就再也解析不出来。判据当场红在这里。
#:
#: 与 :data:`CURRENT_VERSION_MARKER_SUFFIX` 同源派生，将来加别的元数据文件时
#: 只要仍从这里派生文件名就不会漏（由判据 `test_metadata_suffixes_cover_what_activate_writes`
#: 双向锁死）。
CURRENT_METADATA_SUFFIXES: Final[frozenset[str]] = frozenset({CURRENT_VERSION_MARKER_SUFFIX})


@dataclass(frozen=True)
class TemplateResolution:
    """解析结果 —— 路径 + 来源（Requirement 2.2）。

    不返回裸 ``Path``：那样调用方无法回答「这份底稿用的是谁的模板」。

    ``sha256`` 是**惰性** property 而不是 eager 字段。原因是性能：``find_template_file``
    在生成底稿时被频繁调用，而权威目录里最大的 xlsx 近 900 KB —— 每次解析都摘要
    等于给每次模板查找加一次全文件读。惰性 + 按 (path, mtime, size) 缓存后，
    只有真正要 digest 的调用方（版本化、无损判据）才付这个代价。
    """

    path: Path
    #: ``"authoritative"`` | ``"override:project"`` | ``"override:group_custom"``
    #: | ``"override:firm_default"``
    origin: str
    wp_code: str
    #: 覆盖层才有；权威文件为 None。
    version_id: str | None = None

    @property
    def sha256(self) -> str:
        return _file_sha256(self.path)

    @property
    def is_override(self) -> bool:
        return self.origin.startswith("override:")

    @property
    def scope(self) -> TemplateLevel | None:
        """覆盖层来源的作用域；权威文件为 None。"""
        if not self.is_override:
            return None
        return TemplateLevel(self.origin.split(":", 1)[1])


def _file_sha256(path: Path) -> str:
    """文件 sha256，按 (path, mtime_ns, size) 缓存。

    用 sha256 而不是 mtime 判"是否更新"（design 拒绝方案 9）——
    mtime 在拷贝 / 同步中不可靠。这里的 mtime 只用于**缓存失效**，不作判据。
    """
    stat = path.stat()
    return _sha256_cached(str(path), stat.st_mtime_ns, stat.st_size)


@functools.lru_cache(maxsize=2048)
def _sha256_cached(path_str: str, _mtime_ns: int, _size: int) -> str:
    digest = hashlib.sha256()
    with open(path_str, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _scope_dir(scope: TemplateLevel, *, project_id: UUID | None, group_id: UUID | None) -> Path | None:
    """某作用域下的目录；该作用域所需的 id 缺失时返回 None（= 该层不参与解析）。"""
    if scope is TemplateLevel.firm_default:
        return OVERRIDE_ROOT / TemplateLevel.firm_default.value
    if scope is TemplateLevel.group_custom:
        if group_id is None:
            return None
        return OVERRIDE_ROOT / TemplateLevel.group_custom.value / str(group_id)
    if scope is TemplateLevel.project:
        if project_id is None:
            return None
        return OVERRIDE_ROOT / TemplateLevel.project.value / str(project_id)
    raise OverrideScopeUnknownError(
        f"未知作用域 {scope!r}；已知三档：{[s.value for s in SCOPE_PRIORITY]}"
    )


def override_dir_for(
    wp_code: str,
    authoritative: Path,
    scope: TemplateLevel,
    *,
    project_id: UUID | None = None,
    group_id: UUID | None = None,
) -> Path | None:
    """某作用域下、覆盖某份权威文件的目录；该作用域所需 id 缺失时 None。

    是覆盖层定位的**唯一**入口 —— 解析、落盘、版本化都走它，避免三处各拼一次路径。
    """
    base = _scope_dir(scope, project_id=project_id, group_id=group_id)
    if base is None:
        return None
    return base / wp_code / authoritative.stem


def _find_current_override(
    wp_code: str,
    authoritative: Path,
    scope: TemplateLevel,
    *,
    project_id: UUID | None,
    group_id: UUID | None,
) -> Path | None:
    """该作用域下覆盖 ``authoritative`` 的当前版本文件；没有则 None。

    只认与权威文件**同扩展名**的 ``current``（Requirement 2.6 —— 不得用 xlsx 覆盖
    docx）。同时存在多个扩展名的 ``current`` 一律抛，不"挑一个"。
    """
    code_dir = override_dir_for(
        wp_code, authoritative, scope, project_id=project_id, group_id=group_id
    )
    if code_dir is None or not code_dir.is_dir():
        return None

    present = sorted(
        p
        for p in code_dir.glob(f"{CURRENT_STEM}.*")
        if p.is_file() and p.suffix.lower() not in CURRENT_METADATA_SUFFIXES
    )
    if len(present) > 1:
        raise OverrideCurrentVersionAmbiguousError(
            f"{wp_code} / {authoritative.stem} 在 {scope.value} 下有多个当前版本："
            f"{[p.name for p in present]}。解析优先级无定义，不得挑一个。"
        )
    if not present:
        return None

    only = present[0]
    if only.suffix.lower() != authoritative.suffix.lower():
        # 扩展名不符 ⇒ 该层不参与解析。落盘侧的扩展名门（Wave 3）本应挡住，
        # 这里再兜一次是因为覆盖层文件可能被人手动放进去。
        return None
    return only


def _resolve_against(
    wp_code: str,
    authoritative: Path,
    *,
    project_id: UUID | None,
    group_id: UUID | None,
) -> TemplateResolution:
    """对一份权威文件按四层优先级解析出最终结果。"""
    for scope in SCOPE_PRIORITY:
        hit = _find_current_override(
            wp_code, authoritative, scope,
            project_id=project_id, group_id=group_id,
        )
        if hit is not None:
            return TemplateResolution(
                path=hit,
                origin=f"override:{scope.value}",
                wp_code=wp_code,
                version_id=_read_version_id(hit),
            )
    return TemplateResolution(path=authoritative, origin="authoritative", wp_code=wp_code)


def resolve_template(
    wp_code: str,
    *,
    project_id: UUID | None = None,
    group_id: UUID | None = None,
) -> TemplateResolution | None:
    """按四层优先级解析主模板：``project`` > ``group_custom`` > ``firm_default`` > 权威。

    覆盖层为空时行为等价于 :func:`wp_template_finder.find_template_file`
    （Requirement 2.3 零回归，由 Property 6 逐条锁死 476 条索引）。

    权威侧解析不出模板时返回 None 且**不查覆盖层** —— "覆盖"必须有被覆盖对象，
    而 Requirement 2.6 的扩展名一致要求也需要一份权威文件作参照。
    """
    from app.services.wp_template_finder import find_template_file_unresolved

    authoritative = find_template_file_unresolved(wp_code)
    if authoritative is None:
        return None
    return _resolve_against(
        wp_code, authoritative, project_id=project_id, group_id=group_id
    )


def resolve_all_templates(
    wp_code: str,
    *,
    project_id: UUID | None = None,
    group_id: UUID | None = None,
) -> list[TemplateResolution]:
    """多文件底稿的全部模板，逐份按四层优先级解析。

    覆盖是**逐文件**的：同一个 ``wp_code`` 的 3 份权威文件里只覆盖了 1 份时，
    另 2 份仍解析为 ``authoritative``。整组一起换掉会让"改一份"变成"必须全改"。
    """
    from app.services.wp_template_finder import find_all_template_files_unresolved

    return [
        _resolve_against(wp_code, authoritative, project_id=project_id, group_id=group_id)
        for authoritative in find_all_template_files_unresolved(wp_code)
    ]


def resolve_template_any(
    wp_code: str,
    *,
    project_id: UUID | None = None,
    group_id: UUID | None = None,
) -> TemplateResolution | None:
    """对应 :func:`wp_template_finder.find_template_file_any` 的覆盖层解析。

    与 :func:`resolve_template` 分开是因为权威侧的两个入口**解析规则不同**
    （``find_template_file_any`` 有自有 DOCX 优先、A 子码不得回退父表等分支）。
    合成一个会让某一侧的规则被另一侧悄悄改写。
    """
    from app.services.wp_template_finder import find_template_file_any_unresolved

    authoritative = find_template_file_any_unresolved(wp_code)
    if authoritative is None:
        return None
    return _resolve_against(
        wp_code, authoritative, project_id=project_id, group_id=group_id
    )


def _read_version_id(current_path: Path) -> str | None:
    """从 ``current{ext}`` 旁的 ``current.version`` 读版本 id。

    缺这个文件时返回 None 而不抛 —— 版本表在 Wave 3 才建，此前 staged 的覆盖文件
    没有版本 id 是**部署期状态**而非运行期错误。Wave 3 接版本表后由
    Property 16 断言"每个 current 都有版本 id"。
    """
    marker = current_path.with_name(f"{CURRENT_STEM}{CURRENT_VERSION_MARKER_SUFFIX}")
    if not marker.is_file():
        return None
    value = marker.read_text(encoding="utf-8").strip()
    return value or None


# ═══════════════════════════════════════════════════════════════════════════
# 5. 落盘（Requirement 1.1 / 1.2 / 2.6 / 5.2）
# ═══════════════════════════════════════════════════════════════════════════
#
# ## 两处状态的写入顺序（Task 13 依此实现，这里先把裁决写死）
#
# 覆盖层有两处状态：DB 版本表（审计记录）与 `current{ext}`（解析读的同步投影）。
# 二者不可能原子。裁决顺序：**先提交 DB，再切 current**。
#
# * DB 提交成功、current 切换失败 ⇒ 有台账、未生效。审计师看到的是**旧**模板，
#   而台账说有新版本 —— 不一致可被一致性检查发现并**幂等补切**。
# * 反序（先切 current 后提交 DB）失败时 ⇒ **已生效、无台账**。审计师看到的是改过的
#   模板，而系统说不出它来自哪个版本、谁改的。审计证据链断一环，且无法自动修。
#
# ⇒ 宁可「改了但没生效」，不要「生效了但说不出来源」。R154 的回滚说明同此逻辑。

#: 文件名里不允许出现的片段 —— 它们会让 `wp_code` / stem 变成路径而不是名字。
_PATH_INJECTION_TOKENS: Final[tuple[str, ...]] = ("..", "/", "\\", "\x00")


@dataclass(frozen=True)
class StagedOverride:
    """一份已落盘、**尚未生效**的覆盖版本。

    `stage_override` 只把字节写进 ``versions/``；把它变成当前版本是
    ``activate_override``（Task 13）的事。拆两步的理由见上文写入顺序裁决 ——
    "落盘"与"生效"必须能分开失败。
    """

    version_id: str
    wp_code: str
    authoritative_stem: str
    scope: TemplateLevel
    extension: str
    #: ``versions/{version_id}{ext}`` 的绝对路径
    staged_path: Path
    #: 相对 :data:`OVERRIDE_ROOT`，写进版本表的 ``file_relpath``（统一用 ``/``）
    relpath: str
    sha256: str
    #: 该作用域下的 ``current{ext}`` 应在的位置（此刻可能还不存在）
    current_path: Path
    #: 相对**编辑起点**的 `pageSetup` 业务属性真实变化（:func:`diff_page_setup`）。
    #:
    #: 只有浏览器内编辑路径会填 —— `stage_override` 本身不知道"编辑前"是什么，
    #: 上传替换路径的"前后"也没有可比语义（那是用户主动换了一份文件）。
    #:
    #: 空 tuple = 打印设置等价。它**不是**告警：OO 往返实测 0 项真差异
    #: （14 项 `horizontalDpi`/`verticalDpi` 是设备绑定属性，已排除）。非空时说明
    #: 用户在编辑器里真改了纸张/缩放/方向，属于正常编辑结果，回给前端仅作提示。
    page_setup_changes: tuple[PageSetupChange, ...] = ()


def _assert_no_path_injection(label: str, value: str) -> None:
    """``wp_code`` / stem 必须是**名字**而不是路径。

    这是越界门之外的纵深防御：即使 `..` 穿越被 resolve 后的前缀检查挡住，
    含 ``/`` 的 wp_code 也会凭空造出子目录层级，让同一份模板可以由两个不同的
    ``wp_code`` 写到同一个位置（唯一索引形同虚设）。
    """
    if not value or not value.strip():
        raise OverrideRootEscapeError(f"{label} 不得为空")
    for token in _PATH_INJECTION_TOKENS:
        if token in value:
            raise OverrideRootEscapeError(
                f"{label}={value!r} 含非法片段 {token!r} —— 它必须是名字而不是路径"
            )
    if Path(value).is_absolute():
        raise OverrideRootEscapeError(
            f"{label}={value!r} 是绝对路径。注意 `base / '/abs'` 在 pathlib 里会**丢弃 base**，"
            "这类输入必须在拼路径之前就拒绝"
        )


def assert_target_within_override_root(target: Path) -> Path:
    """越界门（Property 1）：目标 ``resolve()`` 后必须以 :data:`OVERRIDE_ROOT` 为前缀。

    `resolve()` 同时解掉 ``..`` 与**符号链接**，所以三种越界形态（``..`` 穿越 /
    绝对路径 / 符号链接指向外部）由同一条检查覆盖。

    返回 resolve 后的路径，调用方一律用返回值落盘 —— 若用原始未 resolve 的路径写盘，
    这道门就只是个装饰。
    """
    root = OVERRIDE_ROOT.resolve()
    resolved = target.resolve()
    if not _is_within(resolved, root):
        raise OverrideRootEscapeError(
            f"写入目标 {resolved} 不在覆盖层根 {root} 之内。"
            "覆盖层写入绝不允许落到权威目录或任何其它位置。"
        )
    return resolved


def _assert_extension_matches(authoritative: Path, extension: str) -> None:
    """扩展名门（Property 9 / Requirement 2.6）。"""
    expected = authoritative.suffix.lower()
    if extension.lower() != expected:
        raise OverrideExtensionMismatchError(
            f"覆盖文件扩展名 {extension!r} 与权威文件 {authoritative.name!r} 的 "
            f"{expected!r} 不一致 —— 用 xlsx 覆盖 docx 会让下游 componentType 分发错位"
        )


def _assert_format_editable(extension: str) -> None:
    """格式门（Requirement 5.2）—— **只**用于浏览器内编辑这条路径。

    🔴 不要把它加到上传替换路径上：覆盖层本身格式无关，476/476 都可覆盖可回滚
    （Requirement 7.2 的覆盖面表）。把这道门加到上传替换上等于把 127 份非 xlsx
    模板的可覆盖能力砍掉。
    """
    if extension.lower() not in EDITABLE_FORMATS:
        raise OverrideFormatNotEditableError(
            f"{extension!r} 不在可浏览器内编辑的格式集合 {sorted(EDITABLE_FORMATS)} 内。"
            "xlsm 含 vbaProject.bin 且 OO 往返保留性未取证（Gate 3）；"
            "docx / doc / xls 走上传替换，同样进版本表、同样可回滚。"
        )


def stage_override(
    wp_code: str,
    authoritative: Path,
    scope: TemplateLevel,
    payload: bytes,
    *,
    version_id: str,
    source_extension: str | None = None,
    project_id: UUID | None = None,
    group_id: UUID | None = None,
    require_editable_format: bool = False,
) -> StagedOverride:
    """把一份覆盖字节落到覆盖层的 ``versions/`` 下，**不**改当前版本。

    :param source_extension: **来源**文件的扩展名。上传替换路径必须传（取自上传文件名）
        —— 那是 Requirement 2.6 真正要挡的场景：用户拿一个 xlsx 去替换 docx 模板。
        浏览器内编辑路径可省略（OO 保存回来的必是同格式），此时取权威文件的扩展名。

        🔴 这个参数不能省掉：第一版把 ``extension = authoritative.suffix`` 再拿它和
        ``authoritative`` 比，那道门**恒真**、是死代码（假绿第①源）。门要有意义，
        被比较的两侧必须来自不同来源。
    :param require_editable_format: 浏览器内编辑路径传 True（只放 xlsx）；
        上传替换路径传 False（476/476 都可覆盖）。两条路径共用本函数是
        AC 5.5 的要求 —— 上传替换不得另开一条绕过两道门的通道。
    :raises OverrideRootEscapeError: 目标越出覆盖层根，或 wp_code/stem 不是名字
    :raises OverrideExtensionMismatchError: 来源扩展名与权威文件不一致
    :raises OverrideFormatNotEditableError: ``require_editable_format`` 且格式不可编辑
    :raises OverrideScopeUnknownError: 作用域不在三档内，或缺该作用域所需的 id
    """
    _assert_no_path_injection("wp_code", wp_code)
    _assert_no_path_injection("authoritative_stem", authoritative.stem)
    _assert_no_path_injection("version_id", version_id)

    extension = source_extension if source_extension is not None else authoritative.suffix
    _assert_extension_matches(authoritative, extension)
    if require_editable_format:
        _assert_format_editable(extension)
    # 门过了之后一律用权威文件的扩展名落盘，避免大小写差异（`.XLSX` vs `.xlsx`）
    # 在文件系统上造出两个 current。
    extension = authoritative.suffix

    code_dir = override_dir_for(
        wp_code, authoritative, scope, project_id=project_id, group_id=group_id
    )
    if code_dir is None:
        raise OverrideScopeUnknownError(
            f"作用域 {scope.value!r} 缺少必需的标识："
            f"project 需 project_id、group_custom 需 group_id（收到 "
            f"project_id={project_id!r} group_id={group_id!r}）"
        )

    versions_dir = assert_target_within_override_root(code_dir / VERSIONS_DIRNAME)
    target = assert_target_within_override_root(versions_dir / f"{version_id}{extension}")
    current_path = assert_target_within_override_root(code_dir / f"{CURRENT_STEM}{extension}")

    versions_dir.mkdir(parents=True, exist_ok=True)

    # 临时文件 + os.replace：任何一步抛错，覆盖层原有文件完好无损。
    # 临时文件与目标**同目录**，否则 os.replace 可能跨设备失败。
    tmp = target.with_name(f".{target.name}.staging")
    try:
        tmp.write_bytes(payload)
        os.replace(tmp, target)
    finally:
        if tmp.exists():
            tmp.unlink()

    digest = hashlib.sha256(payload).hexdigest()
    relpath = target.resolve().relative_to(OVERRIDE_ROOT.resolve()).as_posix()

    return StagedOverride(
        version_id=version_id,
        wp_code=wp_code,
        authoritative_stem=authoritative.stem,
        scope=scope,
        extension=extension,
        staged_path=target,
        relpath=relpath,
        sha256=digest,
        current_path=current_path,
    )


def activate_staged_override(staged: StagedOverride) -> None:
    """把已落盘的版本切成当前版本（写 ``current{ext}`` 与 ``current.version``）。

    🔴 调用方必须**先提交 DB 版本行**再调本函数 —— 见本节顶部的写入顺序裁决。
    本函数幂等：重复调用结果相同，故一致性检查可以安全地补切。
    """
    target = assert_target_within_override_root(staged.current_path)
    marker = assert_target_within_override_root(
        staged.current_path.with_name(f"{CURRENT_STEM}{CURRENT_VERSION_MARKER_SUFFIX}")
    )
    target.parent.mkdir(parents=True, exist_ok=True)

    payload = staged.staged_path.read_bytes()
    tmp = target.with_name(f".{target.name}.staging")
    try:
        tmp.write_bytes(payload)
        os.replace(tmp, target)
    finally:
        if tmp.exists():
            tmp.unlink()

    tmp_marker = marker.with_name(f".{marker.name}.staging")
    try:
        tmp_marker.write_text(staged.version_id, encoding="utf-8")
        os.replace(tmp_marker, marker)
    finally:
        if tmp_marker.exists():
            tmp_marker.unlink()


def deactivate_override(
    wp_code: str,
    authoritative: Path,
    scope: TemplateLevel,
    *,
    project_id: UUID | None = None,
    group_id: UUID | None = None,
) -> bool:
    """删除该作用域的当前版本投影，使解析回落到下一层（Requirement 4.5）。

    只摘 ``current{ext}`` 与 ``current.version``，**不动** ``versions/`` 下的历史文件，
    也不删版本表的行（DB 层有 BEFORE DELETE 触发器兜底）。

    :return: 是否真的摘掉了什么（幂等：已无当前版本时返回 False）
    """
    code_dir = override_dir_for(
        wp_code, authoritative, scope, project_id=project_id, group_id=group_id
    )
    if code_dir is None:
        raise OverrideScopeUnknownError(
            f"作用域 {scope.value!r} 缺少必需的标识（project_id={project_id!r} group_id={group_id!r}）"
        )
    removed = False
    for name in (f"{CURRENT_STEM}{authoritative.suffix}", f"{CURRENT_STEM}{CURRENT_VERSION_MARKER_SUFFIX}"):
        candidate = code_dir / name
        if not candidate.exists():
            continue
        assert_target_within_override_root(candidate)
        candidate.unlink()
        removed = True
    return removed


# ═══════════════════════════════════════════════════════════════════════════
# 6. OnlyOffice 模板编辑会话（Requirement 3.1 ~ 3.7）
# ═══════════════════════════════════════════════════════════════════════════
#
# ## 为什么要一份"工作副本"
#
# 会话要让审计师看到**全部 sheet**（否则改一处会静默打断跨 sheet 取数链），而"全部可见"
# 需要改 `xl/workbook.xml` —— 权威模板不许被写。所以先把当前解析结果复制到覆盖层的
# 编辑区，只对**副本**改可见性。权威目录字节零触碰（Property 3 逐份锁死）。
#
# ## 保存时必须把 workbook.xml 还原成源模板的样子
#
# 若照原样落盘，覆盖版本的 sheet 可见性就跟权威模板不一样了 —— 权威模板刻意隐藏的 sheet
# 会在覆盖版本里变可见。那是**用户没要求过的语义漂移**。故 commit 时用
# `excel_sheet_visibility.plan_restore_workbook_part` 还原（sheet 名序列未变时整体换回源
# workbook.xml，变了则按名字还原可见性）。
#
# ## 落盘路径不含任何 xlsx 中间层（Requirement 3.6 / Property 15）
#
# 从工作副本到覆盖层是**逐字节**搬运：`read_bytes()` → `stage_override(payload=…)`。
# 唯一被改动的部件是 `xl/workbook.xml`，且改动经 zip 级手术（只换那一个部件、其余连
# `ZipInfo` 原样搬），不经 openpyxl / Univer / exceljs。
# 反面教材见 design.md：openpyxl 全量重写在 K11 实测把 zip 部件 37→19、共享公式主格
# 12→0、非空缓存值 716→28、样式索引全表重排、中文表名写成数字实体。

#: 编辑会话工作副本的落点（在覆盖层内，故受越界门保护）。
EDITING_DIRNAME: Final[str] = ".editing"


# ── pageSetup 校验（Requirement 3.4 的可达成口径）─────────────────────────────
#
# ## 🔴 实测：OO 编辑保存会丢 printerSettings.bin，但**不丢打印设置**
#
# 2026-09-04 用 Playwright 真开 DocEditor → forcesave → callback 取证（K11，7 sheet）：
#
# | 指标 | 前 | 后 |
# |---|---:|---:|
# | zip 部件 | 37 | 27 |
# | `printerSettings*.bin` | 7 | **0** |
# | `worksheets/_rels` | 7 | 1 |
# | `pageSetup` 元素 | 7 | **7** |
# | 其中带 `r:id` | 7 | **0** |
# | 跨 sheet 引用（解字符实体后） | 291 | **291** |
#
# 看着像"丢了打印设置"，逐属性核对后**真差异 0 项**：OO 把设置从
# `printerSettings.bin` **内联到了 `pageSetup` 属性**上（`scale` 70/75/93/65/95 逐个对上，
# `paperSize` / `orientation` / `fitToWidth` / `fitToHeight` / `blackAndWhite` 全在），
# 还补齐了 Excel 默认值。丢的只是 **DEVMODE** —— 绑定到做模板那台机器打印机的驱动级
# 设置（纸盒、分辨率、双面）。它在别人机器上打开时 Excel 本来就 fallback 到默认打印机。
#
# ## 所以**不要**去"修复"它
#
# 把 `printerSettings.bin` 搬回来需要给 `pageSetup` 加回 `r:id` 并重建 rels ——
# 那是**内容级**改动，风险远大于丢 DEVMODE；而补回的 DEVMODE 对使用者无意义。
# 这段注释就是为了拦住将来把它当缺陷去修的人。
#
# ## 该做的是校验**业务属性**等价
#
# 纸张 / 缩放 / 方向 / 适应页数 / 黑白 —— 那才是审计底稿打印归档在意的东西。
# 下面这组常量与两个纯函数把它变成可测的。

#: 与打印机无关、对模板有业务意义的 `pageSetup` 属性。
PAGE_SETUP_MEANINGFUL_ATTRS: Final[tuple[str, ...]] = (
    "paperSize", "scale", "orientation", "fitToWidth", "fitToHeight",
    "blackAndWhite", "draft", "firstPageNumber", "useFirstPageNumber",
    "copies", "pageOrder", "cellComments", "errors",
)

#: 绑定到具体打印机、OO 往返必然改写的属性 —— 刻意**不**参与比对。
#: `r:id` 指向 DEVMODE；`horizontalDpi`/`verticalDpi`/`usePrinterDefaults` 是设备能力。
PAGE_SETUP_DEVICE_BOUND_ATTRS: Final[frozenset[str]] = frozenset({
    "r:id", "horizontalDpi", "verticalDpi", "usePrinterDefaults",
})

#: Excel 默认值。原始模板**省略**而 OO **显式写出**，两者语义相同 ⇒ 比对前必须归一，
#: 否则 14 项良性差异会被当成真损失（实测就是这个数）。
PAGE_SETUP_DEFAULTS: Final[dict[str, str]] = {
    "scale": "100",
    "fitToWidth": "1",
    "fitToHeight": "1",
    "orientation": "default",
    "pageOrder": "downThenOver",
    "blackAndWhite": "0",
    "draft": "0",
    "firstPageNumber": "1",
    "useFirstPageNumber": "0",
    "copies": "1",
    "cellComments": "none",
    "errors": "displayed",
}

#: `orientation` 的 `default` 在 Excel 里由 Excel 自行决定，实际落到 portrait。
#: 省略（=default）与显式 portrait 视为等价。
_ORIENTATION_EQUIVALENT: Final[frozenset[frozenset[str]]] = frozenset({
    frozenset({"default", "portrait"}),
})

_PAGE_SETUP_RE = re.compile(r"<pageSetup\b([^>]*?)/?>")
_XML_ATTR_RE = re.compile(r'([\w:]+)="([^"]*)"')


@dataclass(frozen=True)
class PageSetupChange:
    """一处 `pageSetup` 业务属性的真实变化。"""

    sheet_part: str
    attribute: str
    before: str
    after: str

    def as_dict(self) -> dict[str, str]:
        return {
            "sheet_part": self.sheet_part,
            "attribute": self.attribute,
            "before": self.before,
            "after": self.after,
        }


def read_page_setup_attributes(data: bytes) -> dict[str, dict[str, str]]:
    """逐 sheet 取出 `<pageSetup>` 的属性（原样，不归一）。"""
    out: dict[str, dict[str, str]] = {}
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        for name in sorted(
            n for n in zf.namelist()
            if n.startswith("xl/worksheets/") and n.endswith(".xml")
        ):
            text = zf.read(name).decode("utf-8", "replace")
            found = _PAGE_SETUP_RE.search(text)
            out[name] = dict(_XML_ATTR_RE.findall(found.group(1))) if found else {}
    return out


def _normalised(attrs: dict[str, str], key: str) -> str:
    """取值；缺失时填 Excel 默认值（省略 == 默认）。"""
    if key in attrs:
        return attrs[key]
    return PAGE_SETUP_DEFAULTS.get(key, "")


def _values_equivalent(key: str, before: str, after: str) -> bool:
    if before == after:
        return True
    if key == "orientation" and frozenset({before, after}) in _ORIENTATION_EQUIVALENT:
        return True
    return False


def diff_page_setup(before: bytes, after: bytes) -> tuple[PageSetupChange, ...]:
    """`pageSetup` 业务属性的**真实**变化（已归一默认值、已排除设备绑定属性）。

    返回空 tuple = 打印设置等价。sheet 部件集合不同时只比对交集，并把
    新增/消失的 sheet 各报一条（`attribute` 为 ``"<sheet>"``）。
    """
    a = read_page_setup_attributes(before)
    b = read_page_setup_attributes(after)

    changes: list[PageSetupChange] = []
    for part in sorted(set(a) | set(b)):
        if part not in a:
            changes.append(PageSetupChange(part, "<sheet>", "<缺>", "存在"))
            continue
        if part not in b:
            changes.append(PageSetupChange(part, "<sheet>", "存在", "<缺>"))
            continue
        for key in PAGE_SETUP_MEANINGFUL_ATTRS:
            if key in PAGE_SETUP_DEVICE_BOUND_ATTRS:
                continue
            va, vb = _normalised(a[part], key), _normalised(b[part], key)
            if not _values_equivalent(key, va, vb):
                changes.append(PageSetupChange(part, key, va, vb))
    return tuple(changes)


@dataclass(frozen=True)
class TemplateEditSession:
    """一次模板编辑会话。

    ``source_workbook_xml`` 是会话开始时源模板的 ``xl/workbook.xml`` 全文 —— commit 时
    用它还原可见性。记全文而不是记「哪些 sheet 隐藏」，因为整体换回比逐属性还原可靠
    （`activeTab` / `firstSheet` / `definedNames` 一并精确还原）。
    """

    session_id: str
    wp_code: str
    scope: TemplateLevel
    #: 会话开始时解析到的模板（**可能是某层覆盖文件**，即 `current.xlsx`）
    source_path: Path
    #: 🔴 **权威**侧的那份 —— 覆盖层定位（`override_dir_for` 的 `authoritative_stem`）
    #: 与扩展名门都必须用它。
    #:
    #: 用 `source_path` 会错：已有覆盖时它是 `current.xlsx`，`stem` 就成了 `"current"`，
    #: 于是第二次保存会把版本落到 `{wp_code}/current/` 而不是 `{wp_code}/{权威stem}/`
    #: —— 目录对不上，解析再也找不到它。
    authoritative_path: Path
    source_sha256: str
    source_origin: str
    #: OO 实际打开、并会回写的那份工作副本
    working_path: Path
    #: 源模板的 workbook.xml 全文（xlsx 才有；docx 等为 None）
    source_workbook_xml: str | None
    project_id: UUID | None = None
    group_id: UUID | None = None

    @property
    def is_ooxml_workbook(self) -> bool:
        return self.source_workbook_xml is not None


def editing_dir_for(session_id: str) -> Path:
    """某次会话的工作目录（覆盖层内）。"""
    _assert_no_path_injection("session_id", session_id)
    return OVERRIDE_ROOT / EDITING_DIRNAME / session_id


def prepare_template_edit_session(
    wp_code: str,
    scope: TemplateLevel,
    *,
    session_id: str,
    project_id: UUID | None = None,
    group_id: UUID | None = None,
    require_editable_format: bool = True,
) -> TemplateEditSession:
    """建立编辑会话：复制当前模板到覆盖层编辑区，并让全部 sheet 可见。

    :raises TemplateOverrideError: 该 wp_code 解析不到模板
    :raises OverrideFormatNotEditableError: ``require_editable_format`` 且格式不可编辑
    :raises OverrideRootEscapeError: session_id / wp_code 不是名字，或目标越界
    """
    from app.services.workpaper_sync.excel_sheet_visibility import (
        read_workbook_part,
        restore_all_sheets_visible,
    )
    from app.services.wp_template_finder import find_template_file_any_unresolved

    # 🔴 用 `_any` 口径而不是 `resolve_template`（后者只认 xlsx/xlsm）。
    #
    # 理由是**格式门会形同虚设**：`find_template_file` 对 `B2-1` 这类 docx 子码会回退到
    # 父级 XLSX，于是 docx 模板永远解析成 xlsx、格式门永远放行、"docx 置灰"根本测不出来。
    # `find_template_file_any` 才是下游（`wp_template_init_service` 等）真正用的入口，
    # 覆盖层必须跟它同口径 —— 否则「覆盖的那份」和「生成底稿用的那份」会是两个文件。
    resolution = resolve_template_any(wp_code, project_id=project_id, group_id=group_id)
    if resolution is None:
        raise TemplateOverrideError(
            f"{wp_code} 解析不到模板 —— 模板库里不存在的 wp_code（如自定义底稿）不能编辑模板"
        )
    authoritative = find_template_file_any_unresolved(wp_code)
    if authoritative is None:
        # resolve_template 非 None 就意味着权威侧解析得到，这里为 None 说明两者口径漂移
        raise TemplateOverrideError(
            f"{wp_code} 能解析出覆盖层结果却解析不到权威文件 —— 两个入口口径不一致"
        )

    extension = authoritative.suffix
    if require_editable_format:
        _assert_format_editable(extension)

    work_dir = assert_target_within_override_root(editing_dir_for(session_id))
    work_dir.mkdir(parents=True, exist_ok=True)
    working = assert_target_within_override_root(
        work_dir / f"{resolution.path.stem}{extension}"
    )

    # 逐字节复制 —— 不经任何 xlsx 库
    payload = resolution.path.read_bytes()
    tmp = working.with_name(f".{working.name}.staging")
    try:
        tmp.write_bytes(payload)
        os.replace(tmp, working)
    finally:
        if tmp.exists():
            tmp.unlink()

    source_workbook_xml: str | None = None
    if extension.lower() in {".xlsx", ".xlsm"}:
        # 先记源 workbook.xml，再改副本的可见性（顺序反了就记到改后的了）
        source_workbook_xml = read_workbook_part(working)
        restore_all_sheets_visible(working)

    return TemplateEditSession(
        session_id=session_id,
        wp_code=wp_code,
        scope=scope,
        source_path=resolution.path,
        authoritative_path=authoritative,
        source_sha256=resolution.sha256,
        source_origin=resolution.origin,
        working_path=working,
        source_workbook_xml=source_workbook_xml,
        project_id=project_id,
        group_id=group_id,
    )


def commit_template_edit_session(
    session: TemplateEditSession,
    *,
    version_id: str,
) -> StagedOverride:
    """把工作副本落成一个新的覆盖版本（**尚未生效**）。

    先把 ``xl/workbook.xml`` 还原成源模板的样子，再**逐字节**交给
    :func:`stage_override`。调用方随后 `record_override_version` → commit →
    `activate_staged_override`（顺序见 §5 的写入顺序裁决）。

    顺带算出 `pageSetup` 业务属性的前后差异并挂到返回值上（见
    :attr:`StagedOverride.page_setup_changes`）。**这不是门** —— 差异非空不阻止保存，
    因为"用户在编辑器里改了纸张方向"是合法编辑。它存在的意义是：OO 往返会**丢掉**
    ``printerSettings*.bin``（K11 实测 7 → 0），若哪天 OO 换版本连业务属性一起改写，
    这里会立刻显性化，而不是等审计师打印时才发现。
    """
    from app.services.workpaper_sync.excel_sheet_visibility import (
        restore_workbook_part_from_source,
    )

    if not session.working_path.is_file():
        raise TemplateOverrideError(
            f"会话 {session.session_id} 的工作副本不存在：{session.working_path}"
        )

    if session.source_workbook_xml is not None:
        # zip 级还原：只换 xl/workbook.xml，其余部件连 ZipInfo 原样搬
        restore_workbook_part_from_source(
            session.working_path, session.source_workbook_xml
        )

    payload = session.working_path.read_bytes()
    staged = stage_override(
        session.wp_code,
        # 🔴 用 authoritative_path 而不是 source_path —— 见 TemplateEditSession 的字段说明
        session.authoritative_path,
        session.scope,
        payload,
        version_id=version_id,
        source_extension=session.working_path.suffix,
        project_id=session.project_id,
        group_id=session.group_id,
        require_editable_format=False,  # 建会话时已把过门；此处只落盘
    )

    # 🔴 比对基线是 `source_path`（编辑起点，可能是上一层的 current.xlsx）而不是
    # `authoritative_path` —— 否则第二次编辑会把第一次的合法改动重复报一遍。
    if session.is_ooxml_workbook:
        return attach_page_setup_changes(
            staged, session.source_path.read_bytes(), payload, label=session.session_id
        )

    return staged


def attach_page_setup_changes(
    staged: StagedOverride,
    baseline: bytes,
    payload: bytes,
    *,
    label: str,
) -> StagedOverride:
    """算出 `pageSetup` 业务属性差异并挂到 `staged` 上。

    两条写入路径（浏览器内编辑 / 上传替换）共用本函数 —— 拆成两份实现必然漂移，
    且 fail-open 防护也得写两遍。

    :param baseline: 比对基线的**字节**（编辑路径 = 编辑起点；上传路径 = 被替换的那份）
    :param label: 出错时写进日志的标识（会话 id 或 wp_code）
    """
    try:
        changes = diff_page_setup(baseline, payload)
    except (OSError, zipfile.BadZipFile, KeyError, ValueError) as exc:
        # 🔴 不能 fail-open 成静默空 tuple：那样"比对没跑"和"比对通过"长得一样
        # （fail-open 掩盖接线错误）。降级成一条显式记录，调用方与日志都能看见。
        logger.warning(
            "%s 的 pageSetup 比对失败（%s: %s）—— 保存不受影响，"
            "但本次无法判断打印设置是否等价",
            label,
            type(exc).__name__,
            exc,
        )
        changes = (
            PageSetupChange("<比对失败>", type(exc).__name__, str(exc)[:200], ""),
        )
    return dataclasses.replace(staged, page_setup_changes=changes)


#: 会话元数据文件名（落在会话工作目录内）。
SESSION_MANIFEST_NAME: Final[str] = "session.json"


def save_session_manifest(session: TemplateEditSession) -> Path:
    """把会话元数据落盘。

    🔴 **不用进程内字典**：OO 的 callback 是另一个请求（甚至可能落到别的 worker
    进程），进程内状态会在多 worker 下随机丢失，表现为"保存时报会话不存在"。
    落盘后 callback 可以无状态地重建会话。
    """
    import json

    target = assert_target_within_override_root(
        editing_dir_for(session.session_id) / SESSION_MANIFEST_NAME
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "session_id": session.session_id,
        "wp_code": session.wp_code,
        "scope": session.scope.value,
        "source_path": str(session.source_path),
        "authoritative_path": str(session.authoritative_path),
        "source_sha256": session.source_sha256,
        "source_origin": session.source_origin,
        "working_path": str(session.working_path),
        "source_workbook_xml": session.source_workbook_xml,
        "project_id": str(session.project_id) if session.project_id else None,
        "group_id": str(session.group_id) if session.group_id else None,
    }
    tmp = target.with_name(f".{target.name}.staging")
    try:
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, target)
    finally:
        if tmp.exists():
            tmp.unlink()
    return target


def load_session_manifest(session_id: str) -> TemplateEditSession:
    """从磁盘重建会话。

    :raises TemplateOverrideError: 会话不存在或元数据损坏 —— **不** fail-open 成
        「当作新会话」，那会让保存落到错误的 wp_code 上。
    """
    import json

    path = assert_target_within_override_root(
        editing_dir_for(session_id) / SESSION_MANIFEST_NAME
    )
    if not path.is_file():
        raise TemplateOverrideError(f"编辑会话 {session_id} 不存在或已结束")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise TemplateOverrideError(
            f"编辑会话 {session_id} 的元数据无法读取：{exc}"
        ) from exc

    try:
        scope = TemplateLevel(payload["scope"])
    except (KeyError, ValueError) as exc:
        raise OverrideScopeUnknownError(
            f"会话 {session_id} 的 scope 非法：{payload.get('scope')!r}"
        ) from exc

    return TemplateEditSession(
        session_id=payload["session_id"],
        wp_code=payload["wp_code"],
        scope=scope,
        source_path=Path(payload["source_path"]),
        authoritative_path=Path(payload["authoritative_path"]),
        source_sha256=payload["source_sha256"],
        source_origin=payload["source_origin"],
        working_path=Path(payload["working_path"]),
        source_workbook_xml=payload.get("source_workbook_xml"),
        project_id=UUID(payload["project_id"]) if payload.get("project_id") else None,
        group_id=UUID(payload["group_id"]) if payload.get("group_id") else None,
    )


def discard_template_edit_session(session_id: str) -> bool:
    """清掉会话工作目录。幂等。

    :return: 是否真的删掉了什么
    """
    import shutil

    work_dir = editing_dir_for(session_id)
    if not work_dir.is_dir():
        return False
    assert_target_within_override_root(work_dir)
    shutil.rmtree(work_dir)
    return True


# ═══════════════════════════════════════════════════════════════════════════
# 7. 版本表操作（Requirement 4.1 ~ 4.5）
# ═══════════════════════════════════════════════════════════════════════════
#
# 表 = `workpaper_template_override_version`（迁移 V154）。
#
# ## 为什么这些函数是 async 而解析层是同步
#
# 解析必须同步（finder 的三个公开入口是同步的，Requirement 2.3 要求签名不变），
# 所以"当前版本"由文件系统投影承载。版本表是**审计记录**，只在写路径与查询路径上用，
# 那两处都在 async 请求里 ⇒ 这里用 async 接 session。
#
# 🔴 本节不 import 任何 DB 引擎，只接调用方给的 session ⇒ 解析层仍是零 DB，
#    Property 5 的「import 期断言不需要数据库」不受影响。
#
# ## service 只 flush 不 commit
#
# 平台惯例：router 层统一 commit。配合本文件 §5 的写入顺序裁决，router 的顺序必须是
#
#     stage_override(...)            # 落盘 versions/
#     record_override_version(...)   # INSERT + is_current 转移（flush）
#     await session.commit()         # ← DB 先落定
#     activate_staged_override(...)  # 再切 current{ext}
#
# 反序会造出「已生效、无台账」，见 §5。

#: 版本表名 —— 单一真源，判据与查询共用，避免两处各写一遍字面量。
OVERRIDE_VERSION_TABLE: Final[str] = "workpaper_template_override_version"


def _scope_id_params(
    scope: TemplateLevel, project_id: UUID | None, group_id: UUID | None
) -> dict[str, UUID | None]:
    """按作用域规范化 (project_id, group_id) —— 与 V154 的 ck_wptov_scope_ids 对齐。

    多余的 id 一律置 None：给 firm_default 传 project_id 会被 CHECK 拒，
    在这里就归一掉比让 DB 抛更清楚。
    """
    if scope is TemplateLevel.project:
        if project_id is None:
            raise OverrideScopeUnknownError("scope=project 必须给 project_id")
        return {"project_id": project_id, "group_id": None}
    if scope is TemplateLevel.group_custom:
        if group_id is None:
            raise OverrideScopeUnknownError("scope=group_custom 必须给 group_id")
        return {"project_id": None, "group_id": group_id}
    if scope is TemplateLevel.firm_default:
        return {"project_id": None, "group_id": None}
    raise OverrideScopeUnknownError(
        f"未知作用域 {scope!r}；已知三档：{[s.value for s in SCOPE_PRIORITY]}"
    )


async def record_override_version(
    session,
    staged: StagedOverride,
    *,
    project_id: UUID | None = None,
    group_id: UUID | None = None,
    created_by: UUID | None = None,
):
    """登记新版本并把 ``is_current`` 转移给它（Requirement 4.1）。

    先把该作用域下原有的当前版本置为非当前并**取回它的 id 作父版本**，再插入新行。
    两步在同一事务里 —— 反序会撞部分唯一索引 ``uq_wptov_one_current_per_scope``。

    只 flush 不 commit：调用方 commit 之后才可以 :func:`activate_staged_override`。

    :return: 新版本的 ``version_id``（= ``staged.version_id``）
    """
    import sqlalchemy as sa

    ids = _scope_id_params(staged.scope, project_id, group_id)
    key = {
        "wp_code": staged.wp_code,
        "authoritative_stem": staged.authoritative_stem,
        "scope": staged.scope.value,
        **ids,
    }

    # ① 摘掉旧的当前版本，同时取回它的 id 当父版本。
    #    `project_id IS NOT DISTINCT FROM :project_id` 而不是 `=` —— firm_default 下
    #    两个 id 都是 NULL，用 `=` 会因三值逻辑永不匹配，于是旧当前版本摘不掉、
    #    紧随的 INSERT 撞唯一索引。这条是本函数最容易写错的一行。
    demote = await session.execute(
        sa.text(
            f"""
            UPDATE {OVERRIDE_VERSION_TABLE}
               SET is_current = false
             WHERE wp_code = :wp_code
               AND authoritative_stem = :authoritative_stem
               AND scope = :scope
               AND project_id IS NOT DISTINCT FROM :project_id
               AND group_id IS NOT DISTINCT FROM :group_id
               AND is_current
            RETURNING id
            """
        ),
        key,
    )
    previous = demote.scalars().all()
    if len(previous) > 1:
        raise OverrideCurrentVersionAmbiguousError(
            f"{staged.wp_code}/{staged.authoritative_stem} 在 {staged.scope.value} 下查出 "
            f"{len(previous)} 条当前版本 —— 部分唯一索引缺失或被绕过"
        )
    parent_version_id = previous[0] if previous else None

    await session.execute(
        sa.text(
            f"""
            INSERT INTO {OVERRIDE_VERSION_TABLE}
                (id, wp_code, authoritative_stem, scope, project_id, group_id,
                 file_relpath, extension, sha256, is_current, parent_version_id, created_by)
            VALUES
                (:id, :wp_code, :authoritative_stem, :scope, :project_id, :group_id,
                 :file_relpath, :extension, :sha256, true, :parent_version_id, :created_by)
            """
        ),
        {
            "id": staged.version_id,
            **key,
            "file_relpath": staged.relpath,
            "extension": staged.extension,
            "sha256": staged.sha256,
            "parent_version_id": parent_version_id,
            "created_by": created_by,
        },
    )
    await session.flush()
    return staged.version_id


async def promote_override_version(session, version_id: UUID | str):
    """回滚 —— 把某个历史版本置为当前，**不删任何行**（Requirement 4.2 / 4.3）。

    :return: 该版本行的字典（供调用方拿 ``file_relpath`` 去切 ``current{ext}``）
    :raises TemplateOverrideError: 版本不存在
    """
    import sqlalchemy as sa

    row = (
        await session.execute(
            sa.text(
                f"""
                SELECT id, wp_code, authoritative_stem, scope, project_id, group_id,
                       file_relpath, extension, sha256, is_current, parent_version_id
                  FROM {OVERRIDE_VERSION_TABLE}
                 WHERE id = :id
                """
            ),
            {"id": str(version_id)},
        )
    ).mappings().first()
    if row is None:
        raise TemplateOverrideError(f"覆盖版本 {version_id} 不存在")

    key = {
        "wp_code": row["wp_code"],
        "authoritative_stem": row["authoritative_stem"],
        "scope": row["scope"],
        "project_id": row["project_id"],
        "group_id": row["group_id"],
        "id": str(version_id),
    }
    # 先全摘再置一 —— 同一语句里 `is_current = (id = :id)` 也可以，但那会 UPDATE 整条
    # 版本链的每一行（触发 immutable trigger 逐行求值），行多时无谓开销。
    await session.execute(
        sa.text(
            f"""
            UPDATE {OVERRIDE_VERSION_TABLE}
               SET is_current = false
             WHERE wp_code = :wp_code
               AND authoritative_stem = :authoritative_stem
               AND scope = :scope
               AND project_id IS NOT DISTINCT FROM :project_id
               AND group_id IS NOT DISTINCT FROM :group_id
               AND is_current
               AND id <> :id
            """
        ),
        key,
    )
    await session.execute(
        sa.text(f"UPDATE {OVERRIDE_VERSION_TABLE} SET is_current = true WHERE id = :id"),
        {"id": str(version_id)},
    )
    await session.flush()
    return dict(row)


async def clear_current_override(
    session,
    wp_code: str,
    authoritative_stem: str,
    scope: TemplateLevel,
    *,
    project_id: UUID | None = None,
    group_id: UUID | None = None,
) -> int:
    """删除覆盖 —— 该作用域下不再有当前版本，解析回落下一层（Requirement 4.5）。

    **不删行**（V154 有 BEFORE DELETE 触发器兜底）。

    :return: 被摘掉的当前版本条数（0 或 1）
    """
    import sqlalchemy as sa

    ids = _scope_id_params(scope, project_id, group_id)
    result = await session.execute(
        sa.text(
            f"""
            UPDATE {OVERRIDE_VERSION_TABLE}
               SET is_current = false
             WHERE wp_code = :wp_code
               AND authoritative_stem = :authoritative_stem
               AND scope = :scope
               AND project_id IS NOT DISTINCT FROM :project_id
               AND group_id IS NOT DISTINCT FROM :group_id
               AND is_current
            RETURNING id
            """
        ),
        {
            "wp_code": wp_code,
            "authoritative_stem": authoritative_stem,
            "scope": scope.value,
            **ids,
        },
    )
    affected = len(result.scalars().all())
    await session.flush()
    return affected


async def count_affected_workpapers(session, wp_code: str) -> list[dict]:
    """该 ``wp_code`` 下**已存在**的底稿数，按项目分组（Requirement 6.1）。

    这是「改模板会不会动到已经做完的底稿」的答案的前半段。后半段是
    Requirement 6.2 的声明：**不回溯改写**已生成底稿 —— 它们继续用自己的文件。
    所以这个数字的意义是「有多少份底稿是用旧模板生成的」，供业务合伙人判断是否需要
    人工重做，而不是系统会自动改它们。

    🔴 ``working_paper`` 表**没有** ``wp_code`` 列（它在 ``wp_index``），必须 JOIN。
    直接在 working_paper 上找 wp_code 会拿到空结果，于是"受影响面"恒为 0 ——
    那是最糟的形态：报告说"不影响任何底稿"而实际上影响了几百份。
    """
    import sqlalchemy as sa

    rows = (
        await session.execute(
            sa.text(
                """
                SELECT wi.project_id AS project_id, count(*) AS workpaper_count
                  FROM working_paper wp
                  JOIN wp_index wi ON wi.id = wp.wp_index_id
                 WHERE wi.wp_code = :wp_code
                   AND coalesce(wi.is_deleted, false) = false
                   AND coalesce(wp.is_deleted, false) = false
                 GROUP BY wi.project_id
                 ORDER BY wi.project_id
                """
            ),
            {"wp_code": wp_code},
        )
    ).mappings().all()
    return [
        {"project_id": str(r["project_id"]), "workpaper_count": int(r["workpaper_count"])}
        for r in rows
    ]


async def list_override_versions(
    session,
    wp_code: str,
    authoritative_stem: str,
    scope: TemplateLevel,
    *,
    project_id: UUID | None = None,
    group_id: UUID | None = None,
) -> list[dict]:
    """该作用域下的全部版本，新的在前。非当前版本仍可读（Requirement 4.2）。"""
    import sqlalchemy as sa

    ids = _scope_id_params(scope, project_id, group_id)
    rows = (
        await session.execute(
            sa.text(
                f"""
                SELECT id, wp_code, authoritative_stem, scope, project_id, group_id,
                       file_relpath, extension, sha256, is_current, parent_version_id,
                       created_by, created_at
                  FROM {OVERRIDE_VERSION_TABLE}
                 WHERE wp_code = :wp_code
                   AND authoritative_stem = :authoritative_stem
                   AND scope = :scope
                   AND project_id IS NOT DISTINCT FROM :project_id
                   AND group_id IS NOT DISTINCT FROM :group_id
                 ORDER BY created_at DESC, id DESC
                """
            ),
            {
                "wp_code": wp_code,
                "authoritative_stem": authoritative_stem,
                "scope": scope.value,
                **ids,
            },
        )
    ).mappings().all()
    return [dict(r) for r in rows]


# ── import 期执行：接线错误在 import 就暴露，不等某个请求真去写盘 ──────────────
assert_override_root_disjoint_from_authoritative()
assert_error_codes_distinct()


__all__ = [
    "BACKEND_DIR",
    "AUTHORITATIVE_ROOT",
    "OVERRIDE_ROOT",
    "EDITABLE_FORMATS",
    "SCOPE_PRIORITY",
    "CURRENT_STEM",
    "VERSIONS_DIRNAME",
    "TemplateOverrideError",
    "OverrideRootEscapeError",
    "OverrideExtensionMismatchError",
    "OverrideFormatNotEditableError",
    "OverrideScopeUnknownError",
    "OverrideCurrentVersionAmbiguousError",
    "OVERRIDE_ERRORS",
    "TemplateResolution",
    "StagedOverride",
    "assert_override_root_disjoint_from_authoritative",
    "assert_error_codes_distinct",
    "assert_target_within_override_root",
    "override_dir_for",
    "resolve_template",
    "resolve_all_templates",
    "resolve_template_any",
    "stage_override",
    "activate_staged_override",
    "deactivate_override",
    "EDITING_DIRNAME",
    "SESSION_MANIFEST_NAME",
    "TemplateEditSession",
    "editing_dir_for",
    "prepare_template_edit_session",
    "commit_template_edit_session",
    "save_session_manifest",
    "load_session_manifest",
    "discard_template_edit_session",
    "OVERRIDE_VERSION_TABLE",
    "record_override_version",
    "promote_override_version",
    "clear_current_override",
    "count_affected_workpapers",
    "list_override_versions",
]
