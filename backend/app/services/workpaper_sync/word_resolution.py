# -*- coding: utf-8 -*-
"""Word 域 canonical resolver —— config / download / callback / materialize / extract
的**唯一** DOCX 模板 + 运行态 artifact 解析入口。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 5 Task 58
Requirements: 7.7, 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.11, 9.12, 12.5
Properties: P39（config/callback 路径一致）/ P40（子码最具体）/ P41（缺失不异类型
回退）/ P42（路径安全）

═══ 一、与 `resolution.py::CanonicalResolutionService` 的分工 ═══

两者**不重叠**，方向是「本模块解析载体，那个模块解析已发布身份」：

* `CanonicalResolutionService` 处理**已发布 representation 域**：给定 content
  version + entry + generation，返回 published artifact + 非空 approved bundle。
  它要求 entry 已经过一次 `finalize`（Task 15/36），今天没有任何 Word entry 到达
  这一步（Task 59/60/62/63/64 才逐 entry 发布）。
* 本模块处理**模板 / 运行态载体域**：`wp_code → 最具体 DOCX 模板` 与
  `(project_id, wp_code) → canonical 运行态 docx 路径`。这一层今天就在被
  config/download/callback 使用，正是 Requirement 9.3 点名分叉的所在。

因此本模块**不重新实现** bundle/substrate 准入：那些判据在
`adapters/base.assert_substrate_usable`、`adapters/registry.assert_bundle_usable`
等处已就位，重写会让任一侧被短路都不改变行为（变异检验判 GREEN）。发布态解析请
继续走 `CanonicalResolutionService`；:meth:`WordCanonicalResolver.resolve` 只在
「还没有 published representation」的载体层回答「哪个文件」。

═══ 二、为什么五个意图共用一个函数 ═══

Task 58 的第 1 条是「config/download/callback/materialize/extract 全走同
resolver」。若每个意图各有一个解析函数（哪怕内部调同一 helper），「同一」就退化成
「作者记得都调」——`wp_onlyoffice_router` 的现状正是这个：读侧走
`_onlyoffice_storage_dir()`（`.../projects/{pid}/workpapers/onlyoffice/`），写侧
word-template 分支自己拼 `Path(f"storage/{project_id}/workpapers/{wp_code}.docx")`。

2026-08-29 磁盘实测这条分叉的后果：读侧 `.../workpapers/onlyoffice/` 下 16 份
docx，而写侧两个孤儿根下共 **159 份**（`backend/storage/{pid}/workpapers/` 134 +
`storage/{pid}/workpapers/` 25，后者是 CWD=仓库根时落的）。

所以本模块只暴露 :meth:`WordCanonicalResolver.resolve`，意图是**参数**不是分叉；
意图只决定「允不允许」（见 :data:`WORD_INTENT_POLICY`），不决定「解析到哪」。
Property 39 的守卫因此能对全部五个意图跑同一个断言：同 (project, wp_code) ⇒
`canonical_path` / `template_path` / `document_type` 逐字段相等。

═══ 三、最具体 wp_code 优先（Requirement 9.4 / P40）═══

既有 `wp_template_finder.find_template_file_any()` 的子码判据写死
`^A\\d+-\\d+` ⇒ `B2-1` / `B18-3-1` / `B40-1` 这类 B 子码被当**主码**处理，落进
「主程序表：xlsx 优先」分支并抢到父级 XLSX。2026-08-29 逐条实测：28 个
`word-template` wp_code 中 **9 个**（B18-3-1/B18-3-2/B2-1/B2-11/B2-3/B2-6/B2-8/
B40-1/B40-2）都在磁盘上有自己的 DOCX，却全部解析到父级 XLSX。

本模块的候选归属**不用**「文件名以 wp_code 开头」这种前缀判据，而是先从文件名
**派生**候选自己的 wp_code（:func:`derive_wp_code_from_filename`），再交给
`canonical_paths.specificity_rank` 排序。差别是可测的：`A17-7A审计项目团队成员…docx`
在前缀判据下会被算成 `A17-7` 的候选（`A17-7` 后面跟的是 `A`，不是数字），派生判据
下它归 `A17-7A`，对 `A17-7` 的具体度是 -1 ⇒ 不参与。

═══ 四、缺失 vs 类型不符是两个 verdict（Requirement 9.5 / P41）═══

`canonical_paths.pick_most_specific` 已把这两条分成
:class:`~app.services.workpaper_sync.canonical_paths.TemplateMissingError` 与
:class:`~app.services.workpaper_sync.canonical_paths.DocumentTypeMismatchError`，
本模块直接抛它们，**不包一层自己的类型**：包一层会让两条判据归一到同一个
`error_code`，其中一条永久不可达（本 spec 已实测 3 次这个形态）。

两条在**真实数据**上都可达，不是只有合成用例：

* `template_missing` —— `S33-REV` 在 `backend/wp_templates/` 下没有任何载体；
* `document_type_mismatch` —— `A16` / `A17` 的载体只有程序表 XLSX（子码 A16-1~7
  才是 DOCX），按 docx 意图解析父码必然撞上 XLSX。

═══ 五、fail closed，不返回 None ═══

:meth:`WordCanonicalResolver.resolve` 与 :func:`resolve_word_template` 找不到载体
时**抛可分辨异常**，绝不返回 `None` 让上游降级。`None` 会一路表现成「本项目无此
数据」，而 Volar/vitest/get_diagnostics/HEAD-swap 四层静态检查全绿 —— memory 里
记的「最贵的一类」fail-open。

唯一的例外是 :func:`resolve_own_docx_or_none`：它是给存量
`find_template_file_any()`（契约就是 `-> Path | None`，全库约 50 个非 Word 调用点）
的**桥**，只吞 `TemplateMissingError` / `DocumentTypeMismatchError` 两个**具体**
类型并记 DEBUG；:class:`PathBoundaryError` 一律向上抛（安全事件没有可返回的值）。
桥的两条限制条件（只认 exact-own DOCX、自有工作簿存在时不接管）见该函数的 docstring
—— 它们由 1539 个 wp_code 的全量 old/new 比对定出，不是拍的。

═══ 六、载体裁决三值：给宿主门控的可消费判据（Task 63）═══

第五节的「抛异常不返回 None」对**取文件**是对的，但宿主要回答的是另一个问题：
「这个 entry 该不该显示在线编辑入口」。让宿主自己 try/except 三个异常类型，等于把
判据复制到每个调用点；:func:`word_carrier_verdict` 因此把同一次解析归约成封闭三值
:class:`WordCarrierVerdict`，值域与裁决清册的 `unified_verdict` **同名同域**。

它解决的是一条实证缺陷（Task 63 的 `S33-REV`）：该 wp_code 在模板库零载体 ⇒
`find_template_file_any` 返回 `None` ⇒ `_word_template.render()` 直接 `return None`
⇒ render-config 里这个 sheet 没有 `template_structure` ⇒ 前端结构化视图落到
`<el-empty description="模板解析失败，请使用在线编辑模式"/>`，**而在线编辑对它同样
是死路**（自取 `onlyoffice-config` 也找不到模板）。审计师被指向一条不存在的路。

裁决必须由后端下发、不能让前端按 wp_code 字面量判：前端写 `wp_code === 'S33-REV'`
会在下一个零载体 wp_code 出现时静默失效，而且把裁决权从清册搬到了组件里。
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Final, Mapping

from app.services.workpaper_sync.canonical_paths import (
    TEMPLATE_ROOT,
    DocumentTypeMismatchError,
    PathBoundaryError,
    TemplateCandidate,
    TemplateMissingError,
    assert_document_type,
    assert_wp_code_segment,
    document_type_of,
    is_sub_code,
    onlyoffice_canonical_dir,
    onlyoffice_canonical_path,
    parent_code_of,
    pick_most_specific,
    specificity_rank,
)
from app.services.workpaper_sync.models import SyncDomainError

logger = logging.getLogger(__name__)

#: Word 域的文档类型。写成常量而不是到处写 `"docx"` 字面量，守卫按它断言。
WORD_DOCUMENT_TYPE: Final[str] = "docx"

#: 模板索引真源。`wp_template_finder.INDEX_FILE` 必须逐字节指向同一文件 ——
#: 守卫 `test_template_index_path_is_single_source` 双向锁死这一点。
TEMPLATE_INDEX_PATH: Final[Path] = TEMPLATE_ROOT / "_index.json"

#: 参考示例文件的 wp_code 占位（`list_available_templates()` 已跳过它）。
#: 这些文件名不含 wp_code，派生必然失败；显式登记让「派生失败数」有已知分母，
#: 而不是静默丢文件。
REFERENCE_WP_CODE: Final[str] = "_ref"

#: 从文件名派生候选自己的 wp_code。
#:
#: 形态 `{字母}{数字}[{字母}][-{段}]*`：
#: * `A9-1向治理层通报…docx`  → `A9-1`（`向` 不在 `[0-9A-Za-z]` 内，自然截断）
#: * `S12A 评估专家工作报告…docx` → `S12A`（尾字母段是 `[A-Z]*`）
#: * `A17-7A审计项目团队成员…docx` → `A17-7A`（**不是** `A17-7`）
#: * `D2-1至D2-4 应收账款-审定表明细表.xlsx` → `D2-1`（`至` 截断；对 `D2-2` 不适用）
_DERIVE_WP_CODE_RE: Final[re.Pattern[str]] = re.compile(
    r"^([A-Z]+\d+[A-Z]*(?:-[0-9A-Za-z]+)*)"
)


# ═══════════════════════════════════════════════════════════════════════════
# 0. 意图与策略
# ═══════════════════════════════════════════════════════════════════════════


class WordResolutionIntent(str, Enum):
    """Task 58 逐条点名的五个 Word 解析意图。**封闭枚举**。

    守卫按 `set(WordResolutionIntent)` 断言无遗漏 —— 漏登记一个意图（某天新增
    `preview` 却自己拼路径）会让「全走同 resolver」这条判据出现盲区。
    """

    config = "config"
    download = "download"
    callback = "callback"
    materialize = "materialize"
    extract = "extract"


@dataclass(frozen=True)
class WordIntentPolicy:
    """一个意图的**权限**（不是「解析到哪」——那对所有意图相同）。

    Attributes:
        may_provision_from_template: canonical 运行态文件不存在时，是否允许把模板
            作为首次打开的底本（`config` / `download` / `materialize`）。
        may_write_canonical: 是否允许写 canonical 文件（只有 `callback`）。
        requires_existing_canonical: 是否**必须**已有 canonical 文件。`extract`
            为真：从原始模板 extract 会把模板占位符当成审计师填的值回写 HTML。
    """

    may_provision_from_template: bool
    may_write_canonical: bool
    requires_existing_canonical: bool


#: 五个意图的策略表。**只**表达权限差异；路径解析对五者逐字段相同（Property 39）。
WORD_INTENT_POLICY: Final[Mapping[WordResolutionIntent, WordIntentPolicy]] = {
    WordResolutionIntent.config: WordIntentPolicy(True, False, False),
    WordResolutionIntent.download: WordIntentPolicy(True, False, False),
    # callback 是唯一写侧；它必须与读侧解析到**同一** canonical path（Requirement 9.3）。
    WordResolutionIntent.callback: WordIntentPolicy(False, True, False),
    WordResolutionIntent.materialize: WordIntentPolicy(True, False, False),
    # extract 必须读已耐久的 canonical 产物，禁止拿模板顶替。
    WordResolutionIntent.extract: WordIntentPolicy(False, False, True),
}


# ═══════════════════════════════════════════════════════════════════════════
# 1. 异常
# ═══════════════════════════════════════════════════════════════════════════


class WordResolutionError(SyncDomainError):
    error_code = "word_resolution_failed"


class WordCanonicalArtifactAbsentError(WordResolutionError):
    """意图要求已有 canonical 运行态文件，但它不存在（`extract`）。

    🔴 与 :class:`TemplateMissingError` **必须**是两个类型。二者都让调用方「拿不到
    可读文件」，语义完全不同：

    * `TemplateMissingError` = 这个 wp_code 在模板库里没有登记 DOCX（清册补一行，
      Task 63 裁决）；
    * `WordCanonicalArtifactAbsentError` = 模板有、但这个项目还没存过 OO 产物
      （审计师还没编辑过，或上一次 callback 落到了分叉路径）。

    共用一个类型时，把「extract 必须已有 canonical」这条门短路掉之后，模板缺失分支
    会抛同一类型把它遮蔽 ⇒ 只断言类型的守卫判 GREEN。
    """

    error_code = "word_canonical_artifact_absent"


class WordIntentNotPermittedError(WordResolutionError):
    """按意图策略不允许的操作（如非 callback 意图请求写句柄）。"""

    error_code = "word_intent_not_permitted"


#: 本模块可能抛出的**全部**失败 kind。守卫据它断言「每类各自可达且 error_code
#: 互不相同」——这比「每类各测一遍」强：后者在两类合并成同一 code 时全部仍绿。
WORD_RESOLUTION_FAILURE_CODES: Final[tuple[str, ...]] = (
    TemplateMissingError.error_code,
    DocumentTypeMismatchError.error_code,
    PathBoundaryError.error_code,
    WordCanonicalArtifactAbsentError.error_code,
    WordIntentNotPermittedError.error_code,
)


# ═══════════════════════════════════════════════════════════════════════════
# 2. 载体清册（真源：`backend/wp_templates/` 及其 `_index.json`）
# ═══════════════════════════════════════════════════════════════════════════


def derive_wp_code_from_filename(filename: str) -> str | None:
    """从模板文件名派生它自己的 wp_code；无法派生返回 None（不猜）。

    Examples:
        >>> derive_wp_code_from_filename("B2-11 与前任注册会计师的沟通函（…）.docx")
        'B2-11'
        >>> derive_wp_code_from_filename("S12A 评估专家工作报告.docx")
        'S12A'
        >>> derive_wp_code_from_filename("参考-审计指引第21号-管理建议书.docx") is None
        True
    """
    match = _DERIVE_WP_CODE_RE.match((filename or "").strip())
    return match.group(1) if match else None


def _read_index_relative_paths() -> tuple[str, ...]:
    """`_index.json` 里登记的相对路径（读不到时返回空元组并记 WARNING）。

    索引缺失/损坏**不**等于「模板库没有这个 wp_code」：磁盘扫描仍会兜住，
    :func:`collect_template_carriers` 因此对两个来源取并集。
    """
    if not TEMPLATE_INDEX_PATH.is_file():
        logger.warning("Word resolver: 模板索引不存在 %s（退回磁盘扫描）", TEMPLATE_INDEX_PATH)
        return ()
    try:
        payload = json.loads(TEMPLATE_INDEX_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as err:
        # 🔴 具体异常 + ERROR：宽泛 except 会把「索引结构变了」吞成「本项目无模板」。
        logger.error("Word resolver: 模板索引不可解析 %s: %s", TEMPLATE_INDEX_PATH, err)
        return ()
    files = payload.get("files") if isinstance(payload, dict) else None
    if not isinstance(files, list):
        logger.error("Word resolver: 模板索引缺 `files` 数组: %s", TEMPLATE_INDEX_PATH)
        return ()
    out: list[str] = []
    for entry in files:
        rel = entry.get("relative_path") if isinstance(entry, dict) else None
        if isinstance(rel, str) and rel.strip():
            out.append(rel.strip())
    return tuple(out)


@dataclass(frozen=True)
class TemplateCarrier:
    """模板库里的一个载体文件（已派生 wp_code、已判文档类型）。"""

    wp_code: str
    document_type: str
    path: Path

    @property
    def relative_path(self) -> str:
        return self.path.relative_to(TEMPLATE_ROOT).as_posix()


def _inventory_key() -> tuple[int, int, int]:
    """载体清册缓存键：索引文件的 (size, mtime_ns) + 顶层目录数。

    用**文件状态**而不是布尔 `_loaded` 做键：模板库在开发期会被换（memory 记过
    「参考副本已落后」的返工），`lru_cache` 无键时改了索引也不会重载。
    """
    try:
        stat = TEMPLATE_INDEX_PATH.stat()
        head = (stat.st_size, stat.st_mtime_ns)
    except OSError:
        head = (0, 0)
    try:
        dirs = sum(1 for child in TEMPLATE_ROOT.iterdir() if child.is_dir())
    except OSError:
        dirs = 0
    return (*head, dirs)


@lru_cache(maxsize=8)
def _load_carriers(_key: tuple[int, int, int]) -> tuple[TemplateCarrier, ...]:
    seen: set[str] = set()
    out: list[TemplateCarrier] = []

    def _push(path: Path, filename: str) -> None:
        key = path.as_posix()
        if key in seen or not path.is_file():
            return
        doc_type = document_type_of(path)
        code = derive_wp_code_from_filename(filename)
        if doc_type is None or code is None:
            return
        seen.add(key)
        out.append(TemplateCarrier(wp_code=code, document_type=doc_type, path=path))

    for rel in _read_index_relative_paths():
        # 索引里的相对路径是 Windows 反斜杠形态；`Path` 在 posix 上不会拆它，
        # 故统一先归一到 `/` 再拼，避免 Linux CI 下把整串当成一个文件名。
        candidate = TEMPLATE_ROOT / Path(rel.replace("\\", "/"))
        _push(candidate, candidate.name)

    try:
        subdirs = sorted(child for child in TEMPLATE_ROOT.iterdir() if child.is_dir())
    except OSError as err:
        logger.error("Word resolver: 模板库不可枚举 %s: %s", TEMPLATE_ROOT, err)
        subdirs = []
    for subdir in subdirs:
        try:
            entries = sorted(subdir.iterdir())
        except OSError:  # pragma: no cover - 权限异常
            continue
        for path in entries:
            _push(path, path.name)
    return tuple(out)


def template_carriers() -> tuple[TemplateCarrier, ...]:
    """模板库全部可归属载体（索引 ∪ 磁盘，按派生 wp_code 归属）。"""
    return _load_carriers(_inventory_key())


def collect_template_carriers(wp_code: str) -> tuple[TemplateCarrier, ...]:
    """对目标 wp_code **适用**的载体（`specificity_rank >= 0`）。

    适用集合 = 该 wp_code 自己的载体 ∪ 其祖先码的载体。祖先载体保留在集合里是
    **必需**的：Property 41 要求「只有父级 XLSX 时报 type mismatch」，若把父级候选
    先过滤掉，那条判据就落到 missing 分支上，Requirement 9.4 与 9.5 分不开。
    """
    target = (wp_code or "").strip()
    if not target:
        return ()
    return tuple(
        carrier
        for carrier in template_carriers()
        if specificity_rank(carrier.wp_code, target) >= 0
    )


def own_template_carriers(wp_code: str, *, document_type: str | None = None) -> tuple[TemplateCarrier, ...]:
    """该 wp_code **自己**的载体（不含祖先）。清册的「own_docx/own_xlsx」列。"""
    target = (wp_code or "").strip().upper()
    return tuple(
        carrier
        for carrier in template_carriers()
        if carrier.wp_code.upper() == target
        and (document_type is None or carrier.document_type == document_type)
    )


# ═══════════════════════════════════════════════════════════════════════════
# 3. 模板解析（P40 / P41 的唯一生产消费方）
# ═══════════════════════════════════════════════════════════════════════════


def resolve_word_template(wp_code: str) -> Path:
    """按最具体 wp_code 解析 DOCX 模板；失败 fail closed。

    Raises:
        TemplateMissingError: 该 wp_code 及其祖先都没有任何载体（如 `S33-REV`）。
        DocumentTypeMismatchError: 有载体但都不是 DOCX（如 `A16` 只有程序表 XLSX）
            —— **绝不**返回父级异类型文件。
        PathBoundaryError: 载体落在模板库外（软链接越界等）。
    """
    carriers = collect_template_carriers(wp_code)
    chosen = pick_most_specific(
        [TemplateCandidate(wp_code=c.wp_code, path=c.path) for c in carriers],
        wp_code=wp_code,
        expected_document_type=WORD_DOCUMENT_TYPE,
    )
    return chosen.path


def resolve_own_docx_or_none(wp_code: str) -> Path | None:
    """存量 `find_template_file_any()` 的桥：**自有** DOCX 且**无自有工作簿**时返回它。

    ═══ 桥规则的两个限制条件都是实测定出来的（2026-08-29 全量 1539 个 wp_code 比对）═══

    1. **只认 exact-own DOCX，不认祖先 DOCX。**
       `resolve_word_template()` 刻意把祖先候选留在集合里（Property 41 要靠它区分
       missing 与 mismatch）。但直接把它接到 `find_template_file_any` 前面会**倒转
       具体度**：`B30-13-1` 自己有 XLSX，其父 `B30-13` 有 DOCX ⇒ 祖先 DOCX 抢掉
       自有 XLSX（实测 `B30-13-1` / `B60-1` 两例）。祖先 DOCX 回退仍留在既有主码分支
       尾部，位置不变。

    2. **自有 XLSX/XLSM 存在时不接管。**
       `S33-1` 同时有 `S33-1财务报告内部控制制度.xlsx` 与 `S33-1程序修订说明.docx`；
       接管会把它的解析结果从工作簿翻成 Word，属无授权的格式翻转（该 wp_code 的
       Word 裁决归 Task 63）。

    加上这两条后，全量比对的行为变更恰好落在 Requirement 9.4 点名的缺陷族上：
    「子码有自己的 DOCX、没有自己的工作簿，却解析到**祖先**的 XLSX」——
    14 个 wp_code（9 个 `word-template` + `B2-12` / `B30-3` / `B30-4` / `B30-5` /
    `B60` 五个同族旁及项），且 `find_all_template_files` 差异为 0、无任何 wp_code
    从有解析变成 None。

    只吞 :class:`TemplateMissingError` / :class:`DocumentTypeMismatchError` 两个
    **具体**类型（都表示「这个 wp_code 的 Word 载体不成立」，调用方本就要继续试
    xlsx 链）。:class:`PathBoundaryError` 一律上抛 —— 越界是安全事件，没有可
    降级返回的值。
    """
    code = (wp_code or "").strip()
    if not code:
        return None
    if own_template_carriers(code, document_type="xlsx"):
        logger.debug(
            "Word resolver: wp_code=%s 有自有工作簿，桥不接管（格式翻转须由逐 entry 裁决）",
            code,
        )
        return None
    own_docx = own_template_carriers(code, document_type=WORD_DOCUMENT_TYPE)
    if not own_docx:
        logger.debug("Word resolver: wp_code=%s 无自有 DOCX 载体（继续试 xlsx 链）", code)
        return None
    try:
        # 仍经 `pick_most_specific`：自有载体可能多份（B2-3 / B5-1 / B5-2 各 2 份），
        # 排序与路径边界/类型复核必须走同一份实现，不在此处自写 min()。
        return pick_most_specific(
            [TemplateCandidate(wp_code=c.wp_code, path=c.path) for c in own_docx],
            wp_code=code,
            expected_document_type=WORD_DOCUMENT_TYPE,
        ).path
    except (TemplateMissingError, DocumentTypeMismatchError) as err:
        # 走到这里说明自有 DOCX 清册与 pick_most_specific 的判据不一致 —— 是**接线
        # 错误**而不是「本 wp_code 没有 Word 载体」，故记 ERROR 而不是 DEBUG。
        logger.error(
            "Word resolver: wp_code=%s 自有 DOCX 清册 %s 与 pick_most_specific 判据"
            "不一致（%s）—— 两侧判据必须锁死，不是「无模板」",
            code, [c.relative_path for c in own_docx], err,
        )
        return None


# ═══════════════════════════════════════════════════════════════════════════
# 3b. 载体裁决（Task 63：给宿主门控用的三值判据）
# ═══════════════════════════════════════════════════════════════════════════


class WordCarrierVerdict(str, Enum):
    """一个 wp_code 的 DOCX 载体裁决。**封闭三值**，与裁决清册同名同域。

    值域逐字等于 `backend/data/workpaper_word_template_adjudication.json` 每行的
    `unified_verdict`，守卫据此双向锁死：清册每一行的该字段必须等于本函数**现算**
    的结果。两侧同名同域是刻意的 —— 清册本身就是用 :func:`resolve_word_template`
    算出来的，若这里另起一套名字（`missing` / `mismatch`），「清册与运行态一致」
    就退化成人工对照表，改一侧不会打红。

    🔴 **没有第四个值**，特别是没有 `unknown` / `None`。「拿不准就给个中性值」
    在宿主门控上就是 fail-open：前端会把它当成「可以编辑」继续渲染在线编辑入口，
    而那条路对无载体 entry 是死路（Task 63 要移除的正是这种假切换）。
    :class:`PathBoundaryError` 同理**不**映射成 verdict，一律上抛：路径穿越是
    安全事件，把它表现成「本 wp_code 没有模板」会让越界尝试静默消失。
    """

    resolved_docx = "resolved_docx"
    document_type_mismatch = "document_type_mismatch"
    template_missing = "template_missing"

    @property
    def has_usable_docx_carrier(self) -> bool:
        """是否存在可用于 Word 域编辑的 DOCX 载体。

        只有 :attr:`resolved_docx` 为真。写成 `is resolved_docx` 而不是
        `not in (missing, mismatch)`：新增第四个 verdict 时前者立刻判假（保守），
        后者会把未知值当成「可编辑」放过去。
        """
        return self is WordCarrierVerdict.resolved_docx


def word_carrier_verdict(wp_code: str) -> WordCarrierVerdict:
    """现算该 wp_code 的 DOCX 载体裁决（宿主门控与清册对账的唯一判据）。

    实现刻意是「跑一次 :func:`resolve_word_template` 看它抛什么」，而**不是**读
    `workpaper_word_template_adjudication.json`：清册是生成物，生产代码读它会形成
    「运行态依赖生成物」的环，且清册 stale 时门控会按旧事实放行。反过来由 resolver
    现算，清册就成了可被守卫校验的**投影**而不是第二真源。

    Raises:
        PathBoundaryError: wp_code 越界（安全事件，不吞、不映射成 verdict）。
    """
    # 🔴 安全门必须在模板解析**之前**，与 :meth:`WordCanonicalResolver.resolve` 同序。
    #    少了这一行时 `wp_code="../B2-1"` 会先撞上 `TemplateMissingError`（模板库里
    #    确实没有叫 `../B2-1` 的载体）⇒ 路径穿越被吞成 verdict `template_missing`，
    #    宿主把它当「本底稿没有模板」正常显示，越界尝试静默消失。
    #    本函数首版就漏了它，被守卫 `test_path_boundary_is_not_swallowed_into_a_verdict`
    #    打红 —— 与 `resolve()` 里那条注释记载的是同一个形态。
    assert_wp_code_segment(wp_code)
    try:
        resolve_word_template(wp_code)
    except TemplateMissingError:
        return WordCarrierVerdict.template_missing
    except DocumentTypeMismatchError:
        return WordCarrierVerdict.document_type_mismatch
    return WordCarrierVerdict.resolved_docx


# ═══════════════════════════════════════════════════════════════════════════
# 4. 解析结果
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class WordResolution:
    """一次 Word 域解析的完整结果。

    Property 39 的判据：对同一 `(project_id, wp_code)`，五个意图返回的本对象除
    `intent` 外**逐字段相等**（`identity_tuple()` 已剔除 `intent`）。
    """

    intent: WordResolutionIntent
    project_id: str
    wp_code: str
    document_type: str
    template_path: Path
    template_relative_path: str
    canonical_dir: Path
    canonical_path: Path
    canonical_relative_path: str
    canonical_exists: bool

    def identity_tuple(self) -> tuple:
        """去掉 `intent` 的可比较身份（绝对路径也进来：分叉正是路径分叉）。"""
        return (
            self.project_id,
            self.wp_code,
            self.document_type,
            self.template_path,
            self.template_relative_path,
            self.canonical_dir,
            self.canonical_path,
            self.canonical_relative_path,
        )


# ═══════════════════════════════════════════════════════════════════════════
# 5. 服务
# ═══════════════════════════════════════════════════════════════════════════


class WordCanonicalResolver:
    """五个 Word 意图共用的解析服务。只读，不创建目录、不拷模板、不写文件。

    「不写」是刻意的：`provision`（首次从模板拷一份）与 `write`（callback 落盘）是
    调用方的动作，本模块只回答「往哪写/从哪读」。混进写操作会让 resolver 变成
    writer，`--check` 类只读守卫就无法安全调用它。
    """

    def resolve(
        self,
        *,
        intent: WordResolutionIntent | str,
        project_id: object,
        wp_code: str,
    ) -> WordResolution:
        """解析 (project, wp_code) → 唯一模板 + 唯一 canonical 运行态路径。

        顺序固定为：意图策略 → 模板（最具体 + 类型门）→ canonical 路径（边界 +
        类型）→ 存在性门。每一步都在下一步之前失败，因此 error_code 总是指向真正
        的第一个原因。

        把「canonical 存在性」放到最后是必需的：`extract` 在模板本身缺失时应报
        `template_missing`（清册要补一行），而不是 `word_canonical_artifact_absent`
        （那会把「没登记模板」误导成「审计师还没编辑过」）。
        """
        it = (
            intent
            if isinstance(intent, WordResolutionIntent)
            else WordResolutionIntent(intent)
        )
        policy = WORD_INTENT_POLICY[it]

        # ── ① 安全门最先（Property 42）───────────────────────────────────
        #
        # 🔴 必须在模板解析**之前**。放在后面时 `wp_code="../B2-1"` 会先撞上
        #    `TemplateMissingError`（模板库里没有叫 `../B2-1` 的载体），路径穿越
        #    判据就永久落在不可达分支上 —— 2026-08-29 首轮实测正是这个形态
        #    （期望 path_boundary_rejected，实得 template_missing）。
        assert_wp_code_segment(wp_code)

        template = resolve_word_template(wp_code)
        assert_document_type(template, WORD_DOCUMENT_TYPE)

        canonical_dir = onlyoffice_canonical_dir(project_id)
        canonical = onlyoffice_canonical_path(
            project_id, wp_code, document_type=WORD_DOCUMENT_TYPE
        )
        exists = canonical.is_file()

        if policy.requires_existing_canonical and not exists:
            raise WordCanonicalArtifactAbsentError(
                f"意图 {it.value} 必须读已存在的 canonical 运行态文件，但 "
                f"{canonical} 不存在 —— 禁止拿原始模板顶替（模板占位符会被当成"
                "审计师填的值回写 HTML）。若上一次保存落到了 "
                "`storage/{project}/workpapers/` 这类分叉路径，需先按 Requirement 9.3 "
                "归位，不得在读侧加第二条回退路径"
            )

        return WordResolution(
            intent=it,
            project_id=str(project_id),
            wp_code=wp_code.strip(),
            document_type=WORD_DOCUMENT_TYPE,
            template_path=template,
            template_relative_path=template.relative_to(TEMPLATE_ROOT).as_posix(),
            canonical_dir=canonical_dir,
            canonical_path=canonical,
            canonical_relative_path=canonical.name,
            canonical_exists=exists,
        )

    def resolve_write_target(
        self,
        *,
        project_id: object,
        wp_code: str,
        intent: WordResolutionIntent | str = WordResolutionIntent.callback,
    ) -> WordResolution:
        """写侧落盘目标 —— 与读侧 `config`/`download` **同一** canonical path。

        `intent` 可显式传入（默认 `callback`），因此「拿只读意图去写」这条判据是
        **可达**的：`resolve_write_target(intent="config", ...)` 抛
        :class:`WordIntentNotPermittedError`。写成固定 `callback` 会让该分支永久
        不可达（变异检验永远判 GREEN，等于没有这条判据）。

        解析本身仍走 :meth:`resolve`，故读写不可能分叉（Requirement 9.3 / P39）。
        """
        resolution = self.resolve(
            intent=intent, project_id=project_id, wp_code=wp_code
        )
        if not WORD_INTENT_POLICY[resolution.intent].may_write_canonical:
            raise WordIntentNotPermittedError(
                f"意图 {resolution.intent.value} 不得写 canonical 文件 —— "
                f"只有 callback 是写侧（may_write_canonical=True）"
            )
        return resolution


#: 进程级单例（服务无状态、只读）。
WORD_RESOLVER: Final[WordCanonicalResolver] = WordCanonicalResolver()


def word_canonical_write_target(project_id: object, wp_code: str) -> Path:
    """callback 落盘绝对路径（router 的唯一入口）。父目录尚未创建时由调用方 mkdir。"""
    return WORD_RESOLVER.resolve_write_target(
        project_id=project_id, wp_code=wp_code
    ).canonical_path


def is_word_sub_code(wp_code: str) -> bool:
    """子码判据（字母类无关）—— 转发 `canonical_paths.is_sub_code`，不复制正则。"""
    return is_sub_code(wp_code)


def word_parent_code(wp_code: str) -> str | None:
    """父码 —— 转发 `canonical_paths.parent_code_of`，不复制实现。"""
    return parent_code_of(wp_code)


__all__ = [
    "WORD_DOCUMENT_TYPE",
    "TEMPLATE_INDEX_PATH",
    "REFERENCE_WP_CODE",
    "WordResolutionIntent",
    "WordIntentPolicy",
    "WORD_INTENT_POLICY",
    "WordResolutionError",
    "WordCanonicalArtifactAbsentError",
    "WordIntentNotPermittedError",
    "WORD_RESOLUTION_FAILURE_CODES",
    "TemplateCarrier",
    "derive_wp_code_from_filename",
    "template_carriers",
    "collect_template_carriers",
    "own_template_carriers",
    "resolve_word_template",
    "resolve_own_docx_or_none",
    "WordCarrierVerdict",
    "word_carrier_verdict",
    "WordResolution",
    "WordCanonicalResolver",
    "WORD_RESOLVER",
    "word_canonical_write_target",
    "is_word_sub_code",
    "word_parent_code",
]
