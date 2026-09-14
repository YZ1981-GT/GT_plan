# -*- coding: utf-8 -*-
"""source-backed entry profile 事实层：`editability` / `room_model` / `scenario_profile`
的**独立可观测来源**。

spec: `workpaper-html-onlyoffice-bidirectional-writeback-closure` Task 73（Task 1 欠账收口）
Requirements 1.2（owner）/ 1.3 / 1.4 / 1.5 / 1.6 / 1.7 / 1.8 / 12.12 / 12.14
Properties 3 / 6

## 这个模块存在的原因

`entry_profile.py`（Task 13）定义了三个机器字段的**封闭取值域**与交叉规则，但
`backend/data/workpaper_sync_entry_manifest.json` 里一个字段都没有 ⇒ RG-15/16/17 只能在
手搓 fixture 上跑，对真实数据结构性不可达（假绿第①源）。本模块补上缺的那一半：**从
与业务裁决无关的源码事实推导三个字段**，并提供消费侧的**实测观察**。

## 🔴 反重言式（本模块最重要的一条约束）

**禁止**从 `capability` / `html_store` / `migration_state` / `adapter_id` 推导任何 profile
字段。这四个字段来自 reviewed overlay（业务裁决）；用它们推导 profile 会让
`_CAPABILITY_EDITABILITY` / `_CAPABILITY_ROOM_MODEL` 与 RG-15/16/17 变成「用 A 推出 B
再断言 B 与 A 一致」—— 恒真、永远不可能发现真实漂移，也就是假绿第③源（把派生值锁成
自己的基线）。那比现在的欠账更糟：欠账是**可见的红**，重言式是**永久的绿**。

因此推导函数的入参**结构上**不含业务裁决字段（:class:`HostSourceFacts` /
:class:`ComponentSourceFacts` 里没有 capability），另有两道判据：

1. :func:`assert_derivation_ignores_business_adjudication` —— AST 传递闭包扫描推导链路，
   出现 `capability` 等键名即抛。生成器在推导前**无条件调用**它（生产消费方，不是只有
   守卫在读）。
2. 行为判据（守卫侧）：把 overlay 的 capability 全部改成别的值重跑生成器，三个字段必须
   逐字节不变。

## 三个字段各自的独立事实来源

======================  ==========================================================
字段                    独立可观测事实
======================  ==========================================================
`editability`           ① 宿主是否真的被任何生产源码引用（零入边 = 不可达旧桩）
                        ② 宿主模板给挂载点传的 `readonly` 绑定形态（AST attribute 事实）
                        ③ canonical 组件自己的 `readonly` prop 默认值
`room_model`            ① 组件/宿主实际请求的 OO config 端点字面量
                        ② 该端点是否真有后端路由（无路由 ⇒ 服务端给不出 doc_key）
                        ③ 该路由的 doc_key 表达式里有没有用户/会话成分
                        ④ 宿主是否存在客户端本地 doc_key 兜底（`Date.now()` 之类）
`scenario_profile`      上述事实 + 挂载基数（`v-for` 动态 / 单例）+ room service 接线态
======================  ==========================================================

`capability` 因此仍然是**能真的失败**的交叉判据：例如某 entry 被裁决为 `single_html`，
而源码事实是「它确实挂载了 OO 编辑器、doc_key 由 wp 维度共享」⇒ RG-15 打红。这正是
Requirement 1.5 想暴露的「不可兑现的切换」。

## 「尚不可观测」如何诚实表达

Task 21 的 room service（`rooms.derive_doc_key` + participant lease）**尚未接线到任何
生产路由**（本模块 :func:`room_service_wiring` 用 AST 实扫，当前 0 个调用点）。因此
`scenario_profile.room_service_state` 恒为 `pending_room_service`，而
:func:`observe_room_facts` 会把实测到的 legacy 事实（mtime 耦合 / 无 lease）交给 RG-17
⇒ 每条 entry 都 fail closed。**不手填一个「看起来合理」的布尔**：AC 1.2 明文禁止可漂移
布尔与人工豁免决定 required scenarios。
"""

from __future__ import annotations

import ast
import hashlib
import os
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Final, Mapping, Sequence

from app.services.workpaper_sync.definitions import canonical_digest
from app.services.workpaper_sync.entry_profile import (
    DescriptorFacts,
    DescriptorMode,
    Editability,
    RoomFacts,
    RoomModel,
)
from app.services.workpaper_sync.models import SyncDomainError

_BACKEND: Final[Path] = Path(__file__).resolve().parents[3]
_REPO: Final[Path] = _BACKEND.parent
_FRONTEND_SRC: Final[Path] = _REPO / "audit-platform" / "frontend" / "src"
_ROUTERS: Final[Path] = _BACKEND / "app" / "routers"

#: Task 2 的红基线（唯一 source-backed「宿主是否仍显示模式切换」真源）。
#: 🔴 只读 `ui_characterization.mode_switch_visible`（纯源码事实）；**绝不**读
#: `flags.single_mode_switch_visible` —— 后者已经把 capability 揉进来了，拿它当
#: descriptor 事实就是重言式。
LEGACY_BASELINE_PATH: Final[Path] = (
    _BACKEND / "data" / "workpaper_sync_legacy_baseline.json"
)

#: 与 `discover-workpaper-sync-mounts.mjs` 的 EXCLUDED_SEGMENTS 同域：入边统计只看生产源码。
_EXCLUDED_SEGMENTS: Final[frozenset[str]] = frozenset(
    {
        "__tests__", "__fixtures__", "fixtures", "test", "tests", "e2e", "stories",
        "archive", "_archive", "node_modules",
    }
)

_SOURCE_SUFFIXES: Final[tuple[str, ...]] = (".vue", ".ts", ".tsx", ".js")

_IMPORT_RE: Final[re.Pattern[str]] = re.compile(
    r"""(?:from|import\s*\(|require\()\s*['"]([^'"]+)['"]"""
)
_TAG_RE: Final[re.Pattern[str]] = re.compile(r"<([A-Z][A-Za-z0-9_]*)\b")

#: OO config 端点字面量（组件/宿主里实际请求的那一条）。
#: 🔴 字符类里排掉 `\n`：首版写成 `[^'"`]*` 时，`GtB60DocxPane.vue` 顶部注释里的
#: 「切到在线编辑前先 GET onlyoffice-config」被一对跨 12 行的引号吞成一个「端点」，
#: 于是该 entry 被判成 `frontend_endpoint_without_backend_route` ⇒ room_model 假事实。
_ENDPOINT_RE: Final[re.Pattern[str]] = re.compile(
    r"""['"`]([^'"`\n]*onlyoffice-config[^'"`\n]*)['"`]"""
)

#: `withDefaults(defineProps<...>(), { readonly: false })` 里的默认值。
_READONLY_DEFAULT_RE: Final[re.Pattern[str]] = re.compile(
    r"^\s*readonly\s*:\s*(true|false)\s*,?\s*$", re.M
)
#: `readonly?: boolean` / `readonly: boolean` 的 prop 声明。
_READONLY_PROP_RE: Final[re.Pattern[str]] = re.compile(r"^\s*readonly\??\s*:\s*boolean", re.M)
#: `mode?: 'edit' | 'view'` + `props.mode || 'edit'`：OnlyOfficeWordDialog 这类没有
#: readonly prop、改用 mode 表达可编辑性的组件。
_MODE_DEFAULT_EDIT_RE: Final[re.Pattern[str]] = re.compile(
    r"""props\.mode\s*\|\|\s*['"]edit['"]"""
)

#: 客户端本地 doc_key 兜底：只在**doc_key 赋值行**上判定。
#: 🔴 不能对整文件搜 `Date.now()` —— `GtOnlyOfficeSheet.vue` 用它生成容器 DOM id
#: （L129），与 doc_key 无关；整文件搜会把 181 条 xlsx entry 全判成 per-client（假事实）。
_DOC_KEY_LINE_RE: Final[re.Pattern[str]] = re.compile(r"document[_-]?[kK]ey")
_CLIENT_LOCAL_TOKEN_RE: Final[re.Pattern[str]] = re.compile(
    r"Date\.now\(\)|Math\.random\(\)|crypto\.randomUUID\(\)|performance\.now\(\)"
)

#: 路由 doc_key 表达式里的「用户/会话成分」。出现即说明 room 不是 wp 维度共享。
_PER_USER_TOKEN_RE: Final[re.Pattern[str]] = re.compile(
    r"\b(?:user_id|current_user|session_id|participant|_user\.id)\b"
)
#: 路由 doc_key 表达式里的 mtime 成分（Property 6 的反例）。
_MTIME_TOKEN_RE: Final[re.Pattern[str]] = re.compile(
    r"\b(?:st_mtime(?:_ns)?|st_ctime(?:_ns)?|getmtime|getctime)\b"
)

#: fact code 封闭域。写成常量而不是散落字面量：manifest 里存的是这些码，
#: 守卫要按码断言，散落字面量改一处就静默漂移。
FACT_HOST_UNREACHABLE: Final[str] = "host_unreachable_zero_inbound_references"
FACT_MOUNT_PINS_READONLY: Final[str] = "all_mounts_pin_readonly_true"
FACT_COMPONENT_DEFAULT_READONLY: Final[str] = "component_readonly_prop_defaults_true"
FACT_HOST_RUNTIME_READONLY: Final[str] = "host_forwards_runtime_readonly_flag"
FACT_COMPONENT_DEFAULT_EDITABLE: Final[str] = "component_readonly_prop_defaults_editable"
FACT_NO_ROOM_FOR_UNREACHABLE: Final[str] = "unreachable_host_opens_no_room"
FACT_WP_SCOPED_DOC_KEY: Final[str] = "server_doc_key_scoped_to_wp_without_user_component"
FACT_CLIENT_LOCAL_DOC_KEY: Final[str] = "client_local_doc_key_fallback"
FACT_ENDPOINT_WITHOUT_ROUTE: Final[str] = "frontend_endpoint_without_backend_route"
FACT_PER_USER_DOC_KEY: Final[str] = "server_doc_key_includes_user_component"

#: room service 接线态。Task 21 的 room service 接线后由生成器自动翻转，
#: manifest digest 随之变化 ⇒ 全部 evidence 自动 stale（design 的 stale policy）。
ROOM_SERVICE_PENDING: Final[str] = "pending_room_service"
ROOM_SERVICE_WIRED: Final[str] = "room_service_wired"

#: scenario profile payload 的 schema 版本。改 payload 形状必须同时进位，
#: 否则 `scenario_profile_digest` 在语义变化时可能撞回旧值。
SCENARIO_PROFILE_SCHEMA_VERSION: Final[int] = 1


class EntrySourceFactError(SyncDomainError):
    """源码事实不可确定 —— 一律 fail closed，不允许「找不到就给个默认值」。"""

    error_code = "entry_source_fact_unavailable"


# ═══════════════════════════════════════════════════════════════════════════
# 0. 生产源码索引（入边 = 可达性）
# ═══════════════════════════════════════════════════════════════════════════


def _is_production_source(path: Path) -> bool:
    if path.suffix not in _SOURCE_SUFFIXES:
        return False
    name = path.name
    if name.endswith(".d.ts"):
        # 🔴 `components.d.ts` 是 unplugin-vue-components 自动生成的**全量**声明文件，
        # 它提到每一个组件，所以永远不能当可达性证据。实测：把它算进入边后
        # `GtG6OtherBondEcl.vue`（overlay 已裁决的不可达旧桩）也有入边 ⇒ 判据恒真。
        return False
    if re.search(r"\.(spec|test|stories)\.", name):
        return False
    return not name.startswith("~$")


def _resolve_import(importer: Path, spec: str) -> Path | None:
    """把 import 说明符解析成真实文件。

    🔴 必须解析成**路径**再比对，不能比 basename：`htmlRendererRegistry.ts` 里
    `const GtG6OtherBondEcl = defineAsyncComponent(() => import('./GtG6OtherBondInvestmentEcl.vue'))`
    的**变量名**恰好等于旧桩文件名 —— 按 basename 比对会把旧桩判成可达。
    """
    if spec.startswith("@/"):
        base = _FRONTEND_SRC / spec[2:]
    elif spec.startswith("."):
        base = (importer.parent / spec).resolve()
    else:
        return None
    candidates = (
        base,
        base.with_name(base.name + ".vue"),
        base.with_name(base.name + ".ts"),
        base / "index.vue",
        base / "index.ts",
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


@dataclass(frozen=True)
class FrontendReferenceIndex:
    """生产前端源码的入边索引（import 目标 + 模板标签用法）。"""

    scanned_files: int
    imports: Mapping[str, tuple[str, ...]]
    tags: Mapping[str, tuple[str, ...]]

    def inbound(self, host_path: str) -> tuple[str, ...]:
        """引用 `host_path` 的生产文件（不含自身）。

        两条都算入边：`import ... from './GtX.vue'`（显式）与模板里的 `<GtX ...>`
        （unplugin 全局自动注册，宿主可以不写 import）。只看 import 会把
        auto-import 的宿主误判成不可达。
        """
        component_name = Path(host_path).stem
        hits = {item for item in self.imports.get(host_path, ()) if item != host_path}
        hits |= {item for item in self.tags.get(component_name, ()) if item != host_path}
        return tuple(sorted(hits))


@lru_cache(maxsize=1)
def frontend_reference_index() -> FrontendReferenceIndex:
    if not _FRONTEND_SRC.is_dir():
        raise EntrySourceFactError(f"前端源码根不存在: {_FRONTEND_SRC}")
    imports: dict[str, set[str]] = {}
    tags: dict[str, set[str]] = {}
    scanned = 0
    for dirpath, dirnames, filenames in os.walk(_FRONTEND_SRC):
        dirnames[:] = [name for name in dirnames if name.lower() not in _EXCLUDED_SEGMENTS]
        directory = Path(dirpath)
        for name in filenames:
            path = directory / name
            if not _is_production_source(path):
                continue
            scanned += 1
            relative = _relative(path)
            text = path.read_text(encoding="utf-8", errors="replace")
            for match in _IMPORT_RE.finditer(text):
                target = _resolve_import(path, match.group(1))
                if target is not None:
                    imports.setdefault(_relative(target), set()).add(relative)
            for match in _TAG_RE.finditer(text):
                tags.setdefault(match.group(1), set()).add(relative)
    if scanned == 0:
        raise EntrySourceFactError("前端生产源码扫描到 0 个文件 —— 入边判据会恒为空（假绿）")
    return FrontendReferenceIndex(
        scanned_files=scanned,
        imports={key: tuple(sorted(value)) for key, value in imports.items()},
        tags={key: tuple(sorted(value)) for key, value in tags.items()},
    )


def _relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(_REPO).as_posix()
    except ValueError:
        return path.as_posix()


def _read_source(relative: str) -> str:
    path = (_REPO / relative).resolve()
    try:
        path.relative_to(_REPO)
    except ValueError as exc:
        raise EntrySourceFactError(f"源码路径越界: {relative}") from exc
    if not path.is_file():
        raise EntrySourceFactError(f"源码文件不存在: {relative}")
    return path.read_text(encoding="utf-8", errors="replace")


def strip_source_comments(source: str) -> str:
    """去掉 HTML/块/行注释，保留行数（行号仍可用作证据）。

    必须剥注释：`GtB60DocxPane.vue` 的文件头注释里就写着「切到在线编辑前先 GET
    onlyoffice-config」，不剥就会被当成一条真实请求端点（实测踩过）。
    """

    def blank(match: re.Match[str]) -> str:
        return "\n" * match.group(0).count("\n")

    without_html = re.sub(r"<!--[\s\S]*?-->", blank, source)
    without_block = re.sub(r"/\*[\s\S]*?\*/", blank, without_html)
    # 🔴 行注释只能吃**水平**空白：写成 `^\s*//` 时 `\s` 也匹配换行，一串空行 + 一条 `//`
    # 会被整段吞掉 ⇒ 行号左移（实测 `WorkpaperWordEditor.vue` 1365 → 1332 行，provenance
    # 的 `#Lnn` 全部指错行）。`[ \t]*` 保留分组回填，行数逐行守恒。
    return re.sub(r"(?m)^([ \t]*)//.*$", r"\1", without_block)


@lru_cache(maxsize=1)
def _assert_comment_stripping() -> bool:
    """反向自检：注释里的端点必须被剥掉、真实代码必须留下。"""
    # 🔴 注释里的端点必须**带引号**，否则这个探针测不到剥注释这件事：`_ENDPOINT_RE`
    # 只认引号内的字面量，不带引号的注释文本本来就不会命中 ⇒ 剥不剥都是 1 hit（首版
    # 就是这么写的，变异检验判 GREEN 才发现）。
    probe = (
        '<!-- <img src="/api/dead/onlyoffice-config"> -->\n'
        "/* const dead = '/api/block/onlyoffice-config' */\n"
        "// const gone = '/api/line/onlyoffice-config'\n"
        "const live = `/api/workpapers/${id}/sheets/${s}/onlyoffice-config`\n"
    )
    stripped = strip_source_comments(probe)
    hits = [match.group(1) for match in _ENDPOINT_RE.finditer(stripped)]
    if hits != ["/api/workpapers/${id}/sheets/${s}/onlyoffice-config"]:
        raise EntrySourceFactError(
            f"strip_source_comments/_ENDPOINT_RE 反向自检失败: {hits!r} —— "
            "注释里的端点会被当成真实请求，room_model 会得到假事实"
        )
    # 行数守恒：provenance 的 `#Lnn` 是按剥注释后的文本算的，丢一行就指错行。
    line_probe = "a\n\n\n    // dead\n\nb\n"
    if strip_source_comments(line_probe).count("\n") != line_probe.count("\n"):
        raise EntrySourceFactError(
            "strip_source_comments 改变了行数 —— provenance 的 `#Lnn` 会整体偏移"
            "（`^\\s*//` 的 `\\s` 会吃掉前面的空行，实测过）"
        )
    return True


def _endpoint_facts(relative: str) -> tuple[tuple[str, str], ...]:
    """`(normalized_path, source_ref)` 形式的 OO config 端点事实。"""
    _assert_comment_stripping()
    out: list[tuple[str, str]] = []
    text = strip_source_comments(_read_source(relative))
    for match in _ENDPOINT_RE.finditer(text):
        normalized = normalize_endpoint(match.group(1))
        if not normalized.startswith("/"):
            continue
        line = text.count("\n", 0, match.start()) + 1
        out.append((normalized, f"{relative}#L{line}"))
    return tuple(sorted(set(out)))


def normalize_endpoint(raw: str) -> str:
    """把前端模板串/后端路由路径都归一成 `/api/workpapers/*/sheets/*/onlyoffice-config`。"""
    value = raw.split("?", 1)[0].strip()
    value = re.sub(r"\$\{[^}]*\}", "*", value)
    value = re.sub(r"\{[^}]*\}", "*", value)
    value = re.sub(r"/+", "/", value)
    return value.rstrip("/")


def _client_local_doc_key(relative: str) -> str | None:
    """doc_key 赋值行上的客户端本地兜底证据（`file#Lnn`），没有则 None。"""
    text = strip_source_comments(_read_source(relative))
    for index, line in enumerate(text.split("\n"), 1):
        if _DOC_KEY_LINE_RE.search(line) and _CLIENT_LOCAL_TOKEN_RE.search(line):
            return f"{relative}#L{index}"
    return None


# ═══════════════════════════════════════════════════════════════════════════
# 1. 后端 doc_key provider 事实
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class DocKeyProvider:
    """一个 OO config 路由的 doc_key 事实。"""

    endpoint: str
    source_ref: str
    doc_key_expression: str
    includes_mtime: bool
    includes_user: bool
    probe_kind: str  # behavioral | static_expression

    @property
    def server_provided(self) -> bool:
        return True


@lru_cache(maxsize=1)
def doc_key_providers() -> Mapping[str, DocKeyProvider]:
    """从 `backend/app/routers/*.py` 实扫所有 `onlyoffice-config` GET 路由的 doc_key 事实。

    fail closed 两处：路由函数体里找不到 doc_key 表达式即抛；一条路由都没找到即抛
    （否则前端端点全部「无路由」，room_model 会集体退化成 exclusive = 假事实）。
    """
    providers: dict[str, DocKeyProvider] = {}
    for path in sorted(_ROUTERS.glob("*.py")):
        text = path.read_text(encoding="utf-8", errors="replace")
        if "onlyoffice-config" not in text:
            continue
        prefix_match = re.search(r"APIRouter\(\s*prefix\s*=\s*['\"]([^'\"]+)['\"]", text)
        prefix = prefix_match.group(1) if prefix_match else ""
        try:
            tree = ast.parse(text)
        except SyntaxError as exc:  # pragma: no cover - 生产源码语法错时必须炸开
            raise EntrySourceFactError(f"路由文件无法解析: {_relative(path)}: {exc}") from exc
        for node in tree.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            route_path = _route_path_of(node)
            if route_path is None or "onlyoffice-config" not in route_path:
                continue
            endpoint = normalize_endpoint(prefix + route_path)
            expression, expression_line = _doc_key_expression(node, text, path)
            behavioral = _behavioral_mtime_probe(tree, text, expression)
            providers[endpoint] = DocKeyProvider(
                endpoint=endpoint,
                source_ref=f"{_relative(path)}#L{expression_line}",
                doc_key_expression=expression,
                includes_mtime=(
                    behavioral if behavioral is not None else bool(_MTIME_TOKEN_RE.search(expression))
                ),
                includes_user=bool(_PER_USER_TOKEN_RE.search(expression)),
                probe_kind="behavioral" if behavioral is not None else "static_expression",
            )
    if not providers:
        raise EntrySourceFactError(
            "backend/app/routers 下未发现任何 onlyoffice-config 路由 —— "
            "doc_key provider 判据会恒空，room_model 将集体退化（假事实）"
        )
    return providers


def _route_path_of(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str | None:
    for decorator in node.decorator_list:
        if not isinstance(decorator, ast.Call):
            continue
        func = decorator.func
        if not isinstance(func, ast.Attribute) or func.attr not in {"get", "post"}:
            continue
        if decorator.args and isinstance(decorator.args[0], ast.Constant):
            value = decorator.args[0].value
            if isinstance(value, str):
                return value
    return None


def _doc_key_expression(
    node: ast.FunctionDef | ast.AsyncFunctionDef, text: str, path: Path
) -> tuple[str, int]:
    """路由函数体里 doc_key / document_key 的赋值表达式源码。"""
    lines = text.split("\n")
    best: tuple[str, int] | None = None
    for child in ast.walk(node):
        target_names: list[str] = []
        value: ast.expr | None = None
        if isinstance(child, ast.Assign):
            target_names = [
                target.id for target in child.targets if isinstance(target, ast.Name)
            ]
            value = child.value
        elif isinstance(child, ast.Dict):
            for key, item in zip(child.keys, child.values):
                if (
                    isinstance(key, ast.Constant)
                    and isinstance(key.value, str)
                    and key.value in {"document_key", "doc_key"}
                ):
                    target_names = [key.value]
                    value = item
        if not target_names or value is None:
            continue
        if not any(name in {"doc_key", "document_key"} for name in target_names):
            continue
        snippet = "\n".join(lines[value.lineno - 1 : value.end_lineno]).strip()
        candidate = (snippet, value.lineno)
        if best is None or len(snippet) > len(best[0]):
            best = candidate
    if best is None:
        raise EntrySourceFactError(
            f"{_relative(path)}::{node.name} 未找到 doc_key/document_key 表达式 —— "
            "无法确定该入口的 room 身份事实（fail closed，不猜）"
        )
    return best


def _behavioral_mtime_probe(tree: ast.Module, text: str, expression: str) -> bool | None:
    """真执行探针：doc_key 表达式调用的是模块级纯函数时，实测它是否随 mtime 变化。

    只对「可独立提取执行」的 helper 生效（当前唯一命中
    `wp_onlyoffice_router._generate_doc_key`）；其余返回 `None`，由静态表达式判定接管，
    并在 `probe_kind` 里如实标注 —— **不把静态结论冒充实测**。
    """
    call = re.search(r"\b(_[A-Za-z0-9_]*doc_key[A-Za-z0-9_]*)\s*\(", expression)
    if call is None:
        return None
    name = call.group(1)
    function = next(
        (
            node
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
        ),
        None,
    )
    if function is None or isinstance(function, ast.AsyncFunctionDef):
        return None
    parameters = [arg.arg for arg in function.args.args]
    if len(parameters) != 2:
        return None
    module = ast.Module(body=[function], type_ignores=[])
    namespace: dict[str, Any] = {"hashlib": hashlib, "Path": Path}
    try:
        exec(compile(ast.fix_missing_locations(module), "<doc_key_probe>", "exec"), namespace)
    except Exception:  # noqa: BLE001 - 提取失败时退回静态判定，绝不吞成 False
        return None
    probe = namespace.get(name)
    if not callable(probe):
        return None

    import tempfile

    with tempfile.TemporaryDirectory() as directory:
        witness = Path(directory) / "doc_key_probe.bin"
        witness.write_bytes(b"probe")
        stat = witness.stat()
        try:
            before = probe(witness, "PROBE-1")
            os.utime(witness, ns=(stat.st_mtime_ns + 1_000_000_000, stat.st_mtime_ns + 1_000_000_000))
            after = probe(witness, "PROBE-1")
        except Exception:  # noqa: BLE001 - 同上：无法执行则交回静态判定
            return None
    return before != after


@lru_cache(maxsize=1)
def room_service_wiring() -> tuple[str, ...]:
    """Task 21 room service 在 `workpaper_sync` 之外的生产调用点（当前应为空）。

    非空即说明 room service 已接线，`room_service_state` 随之翻转成
    `room_service_wired`、manifest digest 变化、全部 evidence 自动 stale。
    """
    hits: list[str] = []
    app_root = _BACKEND / "app"
    for dirpath, dirnames, filenames in os.walk(app_root):
        dirnames[:] = [name for name in dirnames if name != "__pycache__"]
        if "workpaper_sync" in Path(dirpath).as_posix():
            continue
        for name in sorted(filenames):
            if not name.endswith(".py"):
                continue
            path = Path(dirpath) / name
            text = path.read_text(encoding="utf-8", errors="replace")
            for index, line in enumerate(text.split("\n"), 1):
                if re.search(r"\bderive_doc_key\b|\bRoomService\b", line):
                    hits.append(f"{_relative(path)}#L{index}")
    return tuple(hits)


# ═══════════════════════════════════════════════════════════════════════════
# 2. 组件与宿主事实
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class ComponentSourceFacts:
    """canonical 挂载组件自身的源码事实（3 个组件，各自只解析一次）。"""

    component: str
    canonical_file: str
    readonly_default: str  # "false" | "true" | "undefined" | "absent"
    editable_by_default: bool
    endpoints: tuple[tuple[str, str], ...]
    client_local_doc_key: str | None
    source_refs: tuple[str, ...]


@lru_cache(maxsize=8)
def component_source_facts(component: str, canonical_file: str) -> ComponentSourceFacts:
    text = _read_source(canonical_file)
    refs: list[str] = []
    default_match = _READONLY_DEFAULT_RE.search(text)
    if default_match is not None:
        readonly_default = default_match.group(1)
        refs.append(f"{canonical_file}#L{text.count(chr(10), 0, default_match.start()) + 1}")
        editable_by_default = readonly_default == "false"
    elif _READONLY_PROP_RE.search(text) is not None:
        prop_match = _READONLY_PROP_RE.search(text)
        assert prop_match is not None
        readonly_default = "undefined"
        refs.append(f"{canonical_file}#L{text.count(chr(10), 0, prop_match.start()) + 1}")
        editable_by_default = True
    elif _MODE_DEFAULT_EDIT_RE.search(text) is not None:
        mode_match = _MODE_DEFAULT_EDIT_RE.search(text)
        assert mode_match is not None
        readonly_default = "absent"
        refs.append(f"{canonical_file}#L{text.count(chr(10), 0, mode_match.start()) + 1}")
        editable_by_default = True
    else:
        raise EntrySourceFactError(
            f"{canonical_file} 既没有 readonly prop 默认值、也没有 `props.mode || 'edit'` "
            "默认可编辑证据 —— 无法确定该组件默认是否可编辑（fail closed，不猜）"
        )
    endpoints = _endpoint_facts(canonical_file)
    client_local = _client_local_doc_key(canonical_file)
    return ComponentSourceFacts(
        component=component,
        canonical_file=canonical_file,
        readonly_default=readonly_default,
        editable_by_default=editable_by_default,
        endpoints=endpoints,
        client_local_doc_key=client_local,
        source_refs=tuple(refs),
    )


@dataclass(frozen=True)
class HostSourceFacts:
    """一条 entry 的宿主侧源码事实。

    🔴 刻意**不含** capability / html_store / migration_state / adapter_id：反重言式的
    第一道保障是「推导函数拿不到业务裁决字段」。
    """

    entry_id: str
    host_path: str
    document_type: str
    component: str
    canonical_file: str
    mount_count: int
    dynamic_mount: bool
    readonly_binding: str  # literal_true | literal_false | runtime_expression | absent
    readonly_refs: tuple[str, ...]
    inbound_references: tuple[str, ...]
    endpoints: tuple[tuple[str, str], ...]
    client_local_doc_key: str | None
    mount_source_refs: tuple[str, ...] = field(default_factory=tuple)

    @property
    def host_reachable(self) -> bool:
        return bool(self.inbound_references)


def _readonly_binding_of(mounts: Sequence[Mapping[str, Any]], host_path: str) -> tuple[str, tuple[str, ...]]:
    """挂载点的 `readonly` 绑定形态（按最「可编辑」的那个挂载点归并）。

    归并规则：只要有**一个**挂载点可能可编辑，这条 entry 就是可编辑的 —— 反过来
    （取最严格的那个）会把「同一宿主里一个 tab 只读、另一个可编辑」误判成整体只读。
    """
    kinds: list[str] = []
    refs: list[str] = []
    for mount in mounts:
        line = int((mount.get("sourceSpan") or {}).get("startLine") or 0)
        found = None
        for attribute in mount.get("attributes") or []:
            name = str(attribute.get("argument") or attribute.get("name") or "").lower()
            if name not in {"readonly", "read-only"}:
                continue
            expression = str(attribute.get("expression") or "").strip()
            if expression in {"true", "'true'", '"true"'} or (
                attribute.get("kind") == "attribute" and expression in {"", "true"}
            ):
                found = "literal_true"
            elif expression in {"false", "'false'", '"false"'}:
                found = "literal_false"
            else:
                found = "runtime_expression"
            refs.append(f"{host_path}#L{line}")
            break
        kinds.append(found or "absent")
    for preferred in ("literal_false", "runtime_expression", "absent"):
        if preferred in kinds:
            return preferred, tuple(sorted(set(refs)))
    return "literal_true", tuple(sorted(set(refs)))


def host_source_facts(
    *,
    entry_id: str,
    host_path: str,
    document_type: str,
    mounts: Sequence[Mapping[str, Any]],
) -> HostSourceFacts:
    if not mounts:
        raise EntrySourceFactError(f"entry {entry_id}: 无挂载点事实，无法推导 profile")
    components = {str(mount.get("component") or "") for mount in mounts}
    if len(components) != 1 or not next(iter(components)):
        raise EntrySourceFactError(f"entry {entry_id}: 挂载组件不唯一: {sorted(components)}")
    component = next(iter(components))
    canonical_files = {str(mount.get("canonicalComponentFile") or "") for mount in mounts}
    if len(canonical_files) != 1 or not next(iter(canonical_files)):
        raise EntrySourceFactError(f"entry {entry_id}: canonical 组件文件不唯一")
    canonical_file = next(iter(canonical_files))
    binding, refs = _readonly_binding_of(mounts, host_path)
    component_facts = component_source_facts(component, canonical_file)
    host_endpoints = _endpoint_facts(host_path)
    return HostSourceFacts(
        entry_id=entry_id,
        host_path=host_path,
        document_type=document_type,
        component=component,
        canonical_file=canonical_file,
        mount_count=len(mounts),
        dynamic_mount=any(
            str(mount.get("runtimeCardinality") or "") == "dynamic" for mount in mounts
        ),
        readonly_binding=binding,
        readonly_refs=refs,
        inbound_references=frontend_reference_index().inbound(host_path),
        endpoints=tuple(sorted(set(host_endpoints) | set(component_facts.endpoints))),
        client_local_doc_key=(
            _client_local_doc_key(host_path) or component_facts.client_local_doc_key
        ),
        mount_source_refs=tuple(
            sorted(
                {
                    f"{host_path}#L{int((mount.get('sourceSpan') or {}).get('startLine') or 0)}"
                    for mount in mounts
                }
            )
        ),
    )


# ═══════════════════════════════════════════════════════════════════════════
# 3. 推导（结构上拿不到业务裁决字段）
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class DerivedEntryProfile:
    """一条 entry 的三个 source-backed 字段 + 逐字段来源。"""

    editability: Editability
    room_model: RoomModel
    scenario_profile: Mapping[str, Any]
    profile_source: Mapping[str, Any]

    @property
    def scenario_profile_id(self) -> str:
        return str(self.scenario_profile["profile_id"])

    @property
    def scenario_profile_digest(self) -> str:
        return canonical_digest(dict(self.scenario_profile))

    def as_entry_fields(self) -> dict[str, Any]:
        return {
            "editability": self.editability.value,
            "room_model": self.room_model.value,
            "scenario_profile": dict(self.scenario_profile),
            "profile_source": dict(self.profile_source),
        }


def derive_editability(host: HostSourceFacts, component: ComponentSourceFacts) -> tuple[Editability, str]:
    if not host.host_reachable:
        return Editability.unreachable, FACT_HOST_UNREACHABLE
    if host.readonly_binding == "literal_true":
        return Editability.readonly, FACT_MOUNT_PINS_READONLY
    if component.readonly_default == "true" and host.readonly_binding == "absent":
        return Editability.readonly, FACT_COMPONENT_DEFAULT_READONLY
    if host.readonly_binding in {"runtime_expression", "literal_false"}:
        return Editability.editable, FACT_HOST_RUNTIME_READONLY
    if component.editable_by_default:
        return Editability.editable, FACT_COMPONENT_DEFAULT_EDITABLE
    return Editability.readonly, FACT_COMPONENT_DEFAULT_READONLY


def derive_room_model(
    host: HostSourceFacts,
) -> tuple[RoomModel, str, tuple[str, ...], tuple[str, ...]]:
    """room 身份事实 → `(room_model, 主因 fact code, source_refs, 全部缺陷 fact codes)`。

    `exclusive` 的三种来源都表示「doc_key 不保证跨用户一致」，按**根因优先**排序：

    1. 前端请求的端点在后端**没有路由** —— 服务端根本给不出 doc_key。这是本次实测发现的
       真实缺陷：`WorkpaperWordEditor.vue#L995` 请求 `/api/workpapers/*/onlyoffice-config`，
       而后端只有 `/api/projects/*/working-papers/*/onlyoffice-config` 与
       `/api/workpapers/*/sheets/*/onlyoffice-config`。
    2. 客户端本地 doc_key 兜底（`Date.now()` 之类）—— 每个浏览器各自一个 key。
    3. 服务端 doc_key 里含用户成分。

    主因只有一条，但**全部**命中的缺陷都记进 `doc_key_defects`：只留主因会让另外两条
    fact code 在真实数据上永不出现，下一个人会以为它们是死分支。
    """
    if not host.host_reachable:
        return RoomModel.none, FACT_NO_ROOM_FOR_UNREACHABLE, (), ()
    if not host.endpoints:
        raise EntrySourceFactError(
            f"entry {host.entry_id}: 宿主与 canonical 组件都没有 OO config 端点字面量 —— "
            "无法确定 room 身份来源（fail closed，不猜 shared）"
        )
    providers = doc_key_providers()
    refs: list[str] = []
    defects: list[str] = []
    unmatched: list[str] = []
    per_user = False
    for endpoint, source_ref in host.endpoints:
        provider = providers.get(endpoint)
        if provider is None:
            unmatched.append(endpoint)
            refs.append(source_ref)
            continue
        refs.append(provider.source_ref)
        per_user = per_user or provider.includes_user
    if unmatched:
        defects.append(FACT_ENDPOINT_WITHOUT_ROUTE)
    if host.client_local_doc_key:
        defects.append(FACT_CLIENT_LOCAL_DOC_KEY)
        refs.append(host.client_local_doc_key)
    if per_user:
        defects.append(FACT_PER_USER_DOC_KEY)
    sources = tuple(sorted(set(refs)))
    if defects:
        return RoomModel.exclusive, defects[0], sources, tuple(defects)
    return RoomModel.shared, FACT_WP_SCOPED_DOC_KEY, sources, ()


def derive_entry_profile(
    host: HostSourceFacts, component: ComponentSourceFacts | None = None
) -> DerivedEntryProfile:
    """三字段推导的唯一入口。入参只有源码事实 —— 没有 capability 可读。"""
    facts = component or component_source_facts(host.component, host.canonical_file)
    editability, editability_fact = derive_editability(host, facts)
    room_model, room_fact, room_refs, room_defects = derive_room_model(host)
    room_state = ROOM_SERVICE_WIRED if room_service_wiring() else ROOM_SERVICE_PENDING
    cardinality = "dynamic" if host.dynamic_mount else "single"
    profile_id = ".".join(
        (
            host.document_type,
            editability.value,
            room_model.value,
            cardinality,
            room_state,
            "v1",
        )
    )
    scenario_profile: dict[str, Any] = {
        "profile_id": profile_id,
        "schema_version": SCENARIO_PROFILE_SCHEMA_VERSION,
        "document_type": host.document_type,
        "editability": editability.value,
        "room_model": room_model.value,
        "mount_cardinality": cardinality,
        "mount_count": host.mount_count,
        "host_reachable": host.host_reachable,
        "readonly_binding": host.readonly_binding,
        "component_readonly_default": facts.readonly_default,
        "doc_key_identity": room_fact,
        "doc_key_defects": list(room_defects),
        "room_service_state": room_state,
    }
    # 🔴 payload 只用 JSON 原生类型（list 而非 tuple）：manifest 是 JSON，回读后 tuple
    # 会变 list，`build_manifest(...) == json.load(...)` 的等值判据会因类型不同而假红。
    profile_source: dict[str, Any] = {
        "editability_fact": editability_fact,
        "room_model_fact": room_fact,
        "source_refs": sorted(
            set(facts.source_refs) | set(host.readonly_refs) | set(room_refs)
        )[:6],
        "inbound_reference_count": len(host.inbound_references),
        "inbound_reference_sample": list(host.inbound_references[:2]),
    }
    return DerivedEntryProfile(
        editability=editability,
        room_model=room_model,
        scenario_profile=scenario_profile,
        profile_source=profile_source,
    )


# ═══════════════════════════════════════════════════════════════════════════
# 4. 反重言式结构判据（生成器无条件调用）
# ═══════════════════════════════════════════════════════════════════════════

#: 业务裁决字段名。推导链路里出现任何一个即判非法。
BUSINESS_ADJUDICATION_KEYS: Final[tuple[str, ...]] = (
    "capability",
    "html_store",
    "migration_state",
    "adapter_id",
)

#: 推导链路入口。AST 检查从这些函数开始做**传递闭包**。
_DERIVATION_ENTRY_FUNCTIONS: Final[tuple[str, ...]] = (
    "derive_entry_profile",
    "derive_editability",
    "derive_room_model",
)


def assert_derivation_ignores_business_adjudication(source: str | None = None) -> None:
    """AST 传递闭包：推导链路不得触碰 `capability` 等业务裁决字段。

    `source` 只给守卫用：本函数默认读**自己的模块源码**，那样就无法验证「真读了
    capability 时它会不会抛」——守卫只能证明当前源码合规，不能证明判据本身有效。
    传入一份合成源码即可双向验证（合规 → 不抛；读 capability → 抛）。

    三个刻意的实现选择（与 `rooms._doc_key_source_is_mtime_free` 同范式）：

    1. **不用 grep**：本模块 docstring 里到处写着 `capability`（解释为什么不能读它），
       grep 会恒命中 ⇒ 判据把错值当基线（假绿第③源）。
    2. **只查推导链路**：:func:`observe_descriptor_facts` 等消费侧函数**必须**读
       capability（那是交叉校验的另一侧）。整模块一起查会把正当行为判红，接着就会有人
       去放宽判据。
    3. **传递闭包**：有人加一个 `_capability_of(entry)` helper 再从 `derive_*` 调用，
       只看直接函数体的检查会漏过去。
    """
    tree = ast.parse(source if source is not None else Path(__file__).read_text(encoding="utf-8"))
    functions: dict[str, ast.FunctionDef | ast.AsyncFunctionDef] = {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    if not _DERIVATION_ENTRY_FUNCTIONS:
        # 🔴 入口清单被清空时必须判红：否则 `len(pending) != len(entries)` 退化成
        # `0 != 0`，循环一次都不进 ⇒ 恒通过（vacuous truth 掏空判据）。
        raise EntrySourceFactError("推导链路入口清单为空 —— 反重言式判据会恒通过")
    pending = [name for name in _DERIVATION_ENTRY_FUNCTIONS if name in functions]
    if len(pending) != len(_DERIVATION_ENTRY_FUNCTIONS):
        raise EntrySourceFactError(
            "推导链路入口函数被改名或删除 —— 反重言式判据已失效: "
            f"{sorted(set(_DERIVATION_ENTRY_FUNCTIONS) - set(functions))}"
        )
    visited: set[str] = set()
    while pending:
        name = pending.pop()
        if name in visited:
            continue
        visited.add(name)
        for node in ast.walk(functions[name]):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if node.value in BUSINESS_ADJUDICATION_KEYS:
                    raise EntrySourceFactError(
                        f"{name}() 读取了业务裁决字段 {node.value!r} —— profile 一旦从 "
                        "capability 派生，RG-15/16/17 就变成恒真的重言式（假绿第③源）"
                    )
            if isinstance(node, ast.Attribute) and node.attr in BUSINESS_ADJUDICATION_KEYS:
                raise EntrySourceFactError(
                    f"{name}() 读取了业务裁决属性 .{node.attr} —— 同上，禁止重言式派生"
                )
            if isinstance(node, ast.Call):
                func = node.func
                callee = getattr(func, "attr", None) or getattr(func, "id", None)
                if callee in functions and callee not in visited:
                    pending.append(callee)


# ═══════════════════════════════════════════════════════════════════════════
# 5. 消费侧实测观察（RG-16 / RG-17 的另一侧）
# ═══════════════════════════════════════════════════════════════════════════


@lru_cache(maxsize=1)
def _legacy_baseline() -> Mapping[str, Any]:
    import json

    try:
        payload = json.loads(LEGACY_BASELINE_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise EntrySourceFactError(
            f"Task 2 红基线缺失: {LEGACY_BASELINE_PATH} —— 没有 source-backed UI 事实时"
            "不得推断 descriptor mode"
        ) from exc
    except Exception as exc:  # noqa: BLE001
        raise EntrySourceFactError(f"红基线不可读: {LEGACY_BASELINE_PATH}: {exc}") from exc
    entries = payload.get("entries")
    if not isinstance(entries, list) or not entries:
        raise EntrySourceFactError("红基线 entries 为空 —— descriptor 判据会恒空")
    return {str(item.get("entry_id")): item for item in entries}


def observe_descriptor_facts(entry: Mapping[str, Any]) -> DescriptorFacts | None:
    """宿主**当前实际提供**的模式事实（RG-16 的另一侧）。

    Task 25 的 `EditorLaunchDescriptor` 还不存在，所以「宿主 offer 了哪些视图」就是
    今天唯一存在的 descriptor 事实：

    * 宿主仍显示结构化视图 ↔ OO 视图的模式切换 ⇒ 它对用户**宣称**双向 ⇒ `bidirectional`
    * 只挂 OO 面板、没有切换 ⇒ `single_onlyoffice`
    * 宿主不可达 ⇒ 根本不该产出 descriptor ⇒ 返回 `None`

    只读 `ui_characterization.mode_switch_visible`（纯源码 UI 事实）。**绝不**读
    `flags.single_mode_switch_visible` —— 那一项已经把 capability 揉进去了。
    """
    entry_id = str(entry.get("entry_id") or "")
    facts = host_source_facts(
        entry_id=entry_id,
        host_path=str(entry.get("host_path") or ""),
        document_type=str(entry.get("document_type") or ""),
        mounts=list(entry.get("mounts") or []),
    )
    if not facts.host_reachable:
        return None
    legacy = _legacy_baseline().get(entry_id)
    if legacy is None:
        raise EntrySourceFactError(
            f"entry {entry_id} 不在 Task 2 红基线里 —— manifest 与红基线 entry 集合必须一致"
        )
    switch_visible = bool(
        (legacy.get("ui_characterization") or {}).get("mode_switch_visible")
    )
    return DescriptorFacts(
        mode=DescriptorMode.bidirectional if switch_visible else DescriptorMode.single_onlyoffice,
        exposes_mode_switch=switch_visible,
    )


def observe_room_facts(entry: Mapping[str, Any]) -> RoomFacts:
    """entry 当前 room 的**实测**事实（RG-17 的另一侧）。

    🔴 刻意**不读** manifest 里存的 `room_model` / `scenario_profile.doc_key_identity`：
    RG-17 比的是「冻结的 manifest 裁决」↔「运行时真实行为」。若两侧都从 manifest 读，
    RG-17 就退化成自我比对，永远发现不了 doc_key 实现漂移（假绿第③源）。

    `participant_lease` 由 :func:`room_service_wiring` 决定：lease 是 room service 的
    能力，room service 一个生产调用点都没有 ⇒ 今天没有任何 entry 有 lease。
    """
    entry_id = str(entry.get("entry_id") or "")
    facts = host_source_facts(
        entry_id=entry_id,
        host_path=str(entry.get("host_path") or ""),
        document_type=str(entry.get("document_type") or ""),
        mounts=list(entry.get("mounts") or []),
    )
    if not facts.host_reachable:
        # 不可达宿主永远不会发出 config 请求 ⇒ 没有 doc_key、没有 room、没有 lease。
        # 这里若照常返回组件端点的 provider 事实，就等于宣称一个从不存在的 room。
        return RoomFacts(shared_doc_key=False, doc_key_includes_mtime=False, participant_lease=False)
    providers = doc_key_providers()
    includes_mtime = False
    matched = False
    for endpoint, _ref in facts.endpoints:
        provider = providers.get(endpoint)
        if provider is None:
            continue
        matched = True
        includes_mtime = includes_mtime or provider.includes_mtime
    shared = matched and not facts.client_local_doc_key
    return RoomFacts(
        shared_doc_key=shared,
        doc_key_includes_mtime=includes_mtime,
        participant_lease=bool(room_service_wiring()),
    )


def clear_source_fact_caches() -> None:
    """清空全部源码事实缓存（守卫改写临时源码后必须调用）。"""
    frontend_reference_index.cache_clear()
    component_source_facts.cache_clear()
    doc_key_providers.cache_clear()
    room_service_wiring.cache_clear()
    _legacy_baseline.cache_clear()


__all__ = [
    "LEGACY_BASELINE_PATH",
    "BUSINESS_ADJUDICATION_KEYS",
    "SCENARIO_PROFILE_SCHEMA_VERSION",
    "ROOM_SERVICE_PENDING",
    "ROOM_SERVICE_WIRED",
    "FACT_HOST_UNREACHABLE",
    "FACT_MOUNT_PINS_READONLY",
    "FACT_COMPONENT_DEFAULT_READONLY",
    "FACT_HOST_RUNTIME_READONLY",
    "FACT_COMPONENT_DEFAULT_EDITABLE",
    "FACT_NO_ROOM_FOR_UNREACHABLE",
    "FACT_WP_SCOPED_DOC_KEY",
    "FACT_CLIENT_LOCAL_DOC_KEY",
    "FACT_ENDPOINT_WITHOUT_ROUTE",
    "FACT_PER_USER_DOC_KEY",
    "EntrySourceFactError",
    "FrontendReferenceIndex",
    "DocKeyProvider",
    "ComponentSourceFacts",
    "HostSourceFacts",
    "DerivedEntryProfile",
    "frontend_reference_index",
    "doc_key_providers",
    "room_service_wiring",
    "component_source_facts",
    "host_source_facts",
    "derive_editability",
    "derive_room_model",
    "derive_entry_profile",
    "assert_derivation_ignores_business_adjudication",
    "observe_descriptor_facts",
    "observe_room_facts",
    "normalize_endpoint",
    "clear_source_fact_caches",
]
