"""四场景 UI 文案单一真源守卫 —— Wave 4 Task 18

spec: workpaper-import-export-lifecycle-closure（R3.7 / R3.8）

## 为什么这条守卫必须在后端

判据要拿 `scenario_registry.SCENARIOS` 的**真实文案值**去比对前端源码。
写在前端就得把那些中文句子再抄一份到测试里 —— 抄的那份自己就是第二份真源，
后端一改文案、守卫就 stale 且**不会打红**（memory 记的「守卫把错值当基线锁死」）。

放在后端可以 `import` 真源直接取值，改文案时守卫自动跟着变。

## 判据是「文案是否出现在前端源码」，不是「有没有调接口」

只查「前端有没有 fetch /scenarios」是 grep 式判据：加个调用但仍用硬写文案渲染，
守卫照样绿。所以这里正查两件事：
  ① 真源里每条 `artifact_note` / `timing_note` / `label` 的**特征片段**
     都不得出现在前端源码里
  ② 前端**确实**读了 `/bulk-tab/scenarios` 且把三个字段绑到了模板上

## 反向自检

`test_guard_would_catch_hardcoded_copy` 用真源文案做一次「假装前端抄了文案」的
判定演练 —— 若判定函数恒返 False（比如特征片段抽取失效），该测试会打红，
避免上面两条空转。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.services.bulk_tab.scenario_registry import SCENARIOS, scenarios_for_ui

_REPO = Path(__file__).resolve().parents[2]
_DIALOG = (
    _REPO
    / "audit-platform/frontend/src/components/workpaper/bulk-tab/WpBulkDialog.vue"
)
#: 前端可能抄文案的范围 —— 整个 bulk-tab 目录 + 批量 composable
_FE_SCAN_ROOTS = (
    _REPO / "audit-platform/frontend/src/components/workpaper/bulk-tab",
    _REPO / "audit-platform/frontend/src/composables/useBulkTabImportExport.ts",
)

#: 中文特征片段最小长度 —— 太短会误伤通用词（如「导出」「导入」）
_MIN_FRAGMENT = 8


def _fragments_of(text: str) -> list[str]:
    """把一段中文文案切成可判定的特征片段。

    按标点切分后只留足够长的片段：这样既不会因为前端换了标点而漏判，
    也不会拿「导出」这种通用词去误伤 UI 词汇。
    """
    parts = re.split(r"[。；；，,、\n\*\*「」（）()：:]+", text)
    return [p.strip() for p in parts if len(p.strip()) >= _MIN_FRAGMENT]


def _frontend_sources() -> dict[str, str]:
    out: dict[str, str] = {}
    for root in _FE_SCAN_ROOTS:
        if root.is_file():
            out[root.name] = root.read_text(encoding="utf-8")
            continue
        assert root.is_dir(), f"扫描根不存在：{root}（守卫必须打红而非跳过）"
        for path in root.rglob("*"):
            if path.suffix not in {".vue", ".ts"}:
                continue
            if "__tests__" in path.parts:
                continue
            out[path.relative_to(root.parent).as_posix()] = path.read_text(
                encoding="utf-8"
            )
    assert out, "没扫到任何前端源码 —— 扫描逻辑失效，断言已空转"
    return out


def _find_hardcoded(sources: dict[str, str]) -> list[str]:
    """返回「前端源码里出现了真源文案片段」的命中清单。"""
    hits: list[str] = []
    for spec in SCENARIOS:
        for field, text in (
            ("artifact_note", spec.artifact_note),
            ("timing_note", spec.timing_note),
        ):
            for frag in _fragments_of(text):
                for name, src in sources.items():
                    if frag in src:
                        hits.append(f"{name} 出现 {spec.key}.{field} 片段: {frag!r}")
    return hits


def test_frontend_does_not_hardcode_scenario_copy() -> None:
    """🔴 前端不得硬写四场景的产物/时点说明（R3.7）。"""
    hits = _find_hardcoded(_frontend_sources())
    assert not hits, (
        "前端源码里出现了 scenario_registry 的文案片段（= 文案有两份真源）：\n"
        + "\n".join(f"  {h}" for h in hits)
        + "\n→ 应改为渲染 GET /bulk-tab/scenarios 下发的 artifactNote / timingNote"
    )


def test_guard_would_catch_hardcoded_copy() -> None:
    """反向自检：若前端真抄了文案，上一条必须能抓到。

    做法：构造一份「假前端源码」= 真源文案本身，判定函数必须命中。
    这防的是 `_fragments_of` 抽不出片段（返回空列表）导致上一条恒绿。
    """
    fake = {
        "fake.vue": "\n".join(
            [s.artifact_note for s in SCENARIOS] + [s.timing_note for s in SCENARIOS]
        )
    }
    hits = _find_hardcoded(fake)
    assert len(hits) >= len(SCENARIOS) * 2, (
        f"判定函数只在'全抄'的假源码里命中 {len(hits)} 条，"
        f"期望至少 {len(SCENARIOS) * 2} 条 ⇒ 特征片段抽取失效，主断言已空转"
    )


def test_fragments_extraction_is_not_degenerate() -> None:
    """每条真源文案都必须能抽出至少一个特征片段（否则该条不受保护）。"""
    barren = [
        f"{s.key}.{field}"
        for s in SCENARIOS
        for field, text in (
            ("artifact_note", s.artifact_note),
            ("timing_note", s.timing_note),
        )
        if not _fragments_of(text)
    ]
    assert not barren, (
        f"以下文案抽不出 >={_MIN_FRAGMENT} 字的特征片段，硬写它们不会被发现：{barren}"
    )


def test_frontend_reads_scenarios_endpoint() -> None:
    """前端确实调了 `/bulk-tab/scenarios`（否则四场景无从渲染）。"""
    src = _DIALOG.read_text(encoding="utf-8")
    assert "bulk-tab/scenarios" in src, (
        "WpBulkDialog.vue 未请求 /bulk-tab/scenarios ⇒ 场景说明无来源"
    )


def _scenario_card_block(src: str) -> str:
    """截出场景卡片的模板片段（`v-for="sc in scenarios"` 所在的那块）。

    🔴 为什么必须按块判而不是全文判（2026-08-12 变异检验 M18 暴露）

    初版用 `re.search(r"\\.timingNote\\b", 全文)`，把「文件里任何位置提到过」
    当成「卡片里渲染了」。变异检验删掉卡片里的 `{{ sc.timingNote }}` 后守卫**仍绿**
    —— 因为 options 步骤的场景回显（`currentScenario.timingNote`）还在，
    足以让全文判据命中。而用户在选择场景那一屏看到的说明已经少了一段。

    ⇒ 判据收窄到卡片块内。截取方式用**花括号/标签配对**而非固定字符窗口
      （memory 铁律：截函数体禁固定字符窗口）。
    """
    anchor = src.find('v-for="sc in scenarios"')
    assert anchor != -1, "找不到场景卡片的 v-for 锚点 —— 截取失效，断言会空转"

    # 从锚点往前找到最近的 <el-tooltip 或 <div 起始，往后找到该结构闭合
    start = src.rfind("<el-tooltip", 0, anchor)
    if start == -1:
        start = src.rfind("<div", 0, anchor)
    assert start != -1, "找不到卡片块起始标签"

    # 向后配对：数 <div 与 </div>，遇到 </el-tooltip> 也视为块尾
    end = src.find("</el-tooltip>", anchor)
    if end == -1:
        depth = 0
        i = anchor
        while i < len(src):
            if src.startswith("<div", i):
                depth += 1
            elif src.startswith("</div>", i):
                depth -= 1
                if depth <= 0:
                    end = i
                    break
            i += 1
    assert end != -1 and end > start, "卡片块闭合标签未找到"
    block = src[start:end]
    assert len(block) > 80, f"截出的卡片块只有 {len(block)} 字符，疑似截取错位"
    return block


def test_frontend_binds_all_three_copy_fields_inside_card() -> None:
    """三个文案字段都在**场景卡片块内**渲染 —— 只请求不渲染等于没接。

    🔴 这条防的正是 memory 记的「additive 注入即死代码」：拉了数据但没有消费方，
    四层守卫全绿，用户看到的还是空白卡片。
    """
    block = _scenario_card_block(_DIALOG.read_text(encoding="utf-8"))
    missing = [
        field
        for field in ("label", "artifactNote", "timingNote")
        if not re.search(rf"sc\.{field}\b", block)
    ]
    assert not missing, (
        f"场景卡片块内未渲染 {missing} ⇒ 这些文案拉了没用，用户看不到\n"
        f"（判据只看卡片块，不看文件其它位置 —— 别处提到不代表卡片里显示了）"
    )


def test_card_block_extraction_is_bounded() -> None:
    """反向自检：卡片块截取既不能落空，也不能退化成整份文件。

    若截出的块 == 全文，上一条就退回了被 M18 证伪的全文判据。
    """
    src = _DIALOG.read_text(encoding="utf-8")
    block = _scenario_card_block(src)
    assert len(block) < len(src) * 0.6, (
        f"截出的卡片块占全文 {len(block) / len(src):.0%}，过大 ⇒ 判据已退化为全文匹配"
    )


def test_frontend_renders_all_four_scenarios_generically() -> None:
    """必须用 v-for 遍历渲染，而不是写死四个卡片。

    写死四个即使文案来自后端，也会在后端增删场景时不同步 —— 场景数同样是真源。
    """
    src = _DIALOG.read_text(encoding="utf-8")
    assert re.search(r'v-for="sc in scenarios"', src), (
        "四场景应 v-for 遍历后端返回的列表，不得写死卡片"
    )
    # 反向：不得出现按场景键分支的硬编码
    for spec in SCENARIOS:
        assert f"'{spec.key}'" not in src or spec.key in {"import"}, (
            f"WpBulkDialog.vue 出现场景键字面量 '{spec.key}' ⇒ 疑似按键硬编码分支"
        )


def test_archive_gating_comes_from_backend() -> None:
    """归档态可用性由后端下发，前端不得自己判 ProjectStatus（R3.8）。

    门控真源是 `workflow_gate._BLOCKED_STATUSES`；前端再判一次就是第二份规则，
    分叉后会出现「按钮亮着但导入被静默跳过」。
    """
    src = _DIALOG.read_text(encoding="utf-8")
    assert "disabledReason" in src, "未消费后端下发的 disabledReason ⇒ 置灰无原因提示"
    assert "sc.disabled" in src, "未消费后端下发的 disabled ⇒ 归档态仍可点"
    for banned in ("ProjectStatus", "'archived'", '"archived"'):
        assert banned not in src, (
            f"WpBulkDialog.vue 出现 {banned!r} ⇒ 前端自己判归档状态（规则第二份）"
        )


def test_scenarios_endpoint_registered_and_readonly() -> None:
    """端点真实注册，且是 GET（读取语义）。"""
    from app.main import app

    target = "/api/projects/{project_id}/bulk-tab/scenarios"
    found = {
        getattr(r, "path", ""): sorted(getattr(r, "methods", []) or [])
        for r in app.routes
    }
    assert target in found, f"{target} 未注册 ⇒ 前端拿不到场景真源"
    assert "GET" in found[target], f"{target} 应为 GET，实际 {found[target]}"


def test_ui_payload_shape_matches_frontend_interface() -> None:
    """后端下发键集 ⊇ 前端 `BulkScenario` 接口声明的字段。

    🔴 Vue/TS 对「后端少给一个字段」没有任何运行期信号 —— 模板插值出 `undefined`
    会渲染成空字符串，看起来只是"说明是空的"。故在此做结构对账。
    """
    backend_keys = set(scenarios_for_ui()[0].keys()) | {"disabled", "disabledReason"}
    src = _DIALOG.read_text(encoding="utf-8")
    m = re.search(r"interface BulkScenario \{([\s\S]*?)\n\}", src)
    assert m, "WpBulkDialog.vue 未声明 BulkScenario 接口"
    fe_keys = set(re.findall(r"^\s*(\w+)\s*[?]?:", m.group(1), re.M))
    missing = sorted(fe_keys - backend_keys)
    assert not missing, (
        f"前端声明了后端不下发的字段（模板会渲染出空白）：{missing}\n"
        f"  后端键集={sorted(backend_keys)}"
    )


@pytest.mark.parametrize("spec", SCENARIOS, ids=lambda s: s.key)
def test_every_scenario_has_nonempty_copy(spec) -> None:  # noqa: ANN001
    """每个场景的三段文案都非空 —— 空文案会渲染成空白卡片。"""
    assert spec.label.strip(), f"{spec.key} 缺 label"
    assert spec.artifact_note.strip(), f"{spec.key} 缺 artifact_note"
    assert spec.timing_note.strip(), f"{spec.key} 缺 timing_note"


#: 会被纯文本消费方原样显示出来的 Markdown 标记
_MARKDOWN_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\*\*[^*]+\*\*", "**强调**"),
    (r"(?<!\w)`[^`]+`", "`代码`"),
    (r"\[[^\]]+\]\([^)]*\)", "[链接](url)"),
    (r"(?m)^\s*[-*+]\s+", "列表项"),
    (r"(?m)^#{1,6}\s+", "标题 #"),
)


@pytest.mark.parametrize("spec", SCENARIOS, ids=lambda s: s.key)
def test_copy_is_plain_text(spec) -> None:  # noqa: ANN001
    """🔴 三段文案必须是纯文本 —— 消费方是纯文本插值，Markdown 会原样显示。

    2026-08-12 浏览器实测抓到的真实缺陷：`**不含**` / `` `manifest.json` `` /
    `**仍可导出**` 在 `WpBulkDialog.vue` 的 `{{ sc.artifactNote }}` 里显示成
    字面量星号和反引号。

    这类缺陷**所有静态守卫都查不出**（文案是合法字符串、类型正确、端点也通），
    只有真在浏览器里看一眼才发现 —— 所以补这条把它变成可回归的判据。
    """
    offenders: list[str] = []
    for field, text in (
        ("label", spec.label),
        ("artifact_note", spec.artifact_note),
        ("timing_note", spec.timing_note),
    ):
        for pattern, human in _MARKDOWN_PATTERNS:
            m = re.search(pattern, text)
            if m:
                offenders.append(f"{field} 含 {human}: {m.group(0)!r}")
    assert not offenders, (
        f"场景 {spec.key} 的文案含 Markdown 标记，消费方（纯文本插值）会原样显示：\n"
        + "\n".join(f"  {o}" for o in offenders)
        + "\n→ 真源的值必须是可直接呈现的文本；要强调请用中文表达，"
        "不要指望消费方实现 Markdown 解析"
    )


def test_plain_text_guard_would_catch_markdown() -> None:
    """反向自检：若文案真含 Markdown，上一条必须能抓到。

    防 `_MARKDOWN_PATTERNS` 写错正则导致主断言恒绿。
    """
    samples = {
        "**强调**": "仅含表格骨架，**不含**任何数据。",
        "`代码`": "附 `manifest.json` 校验值。",
        "[链接](url)": "详见[文档](http://x)。",
    }
    for human, text in samples.items():
        hit = any(re.search(p, text) for p, _ in _MARKDOWN_PATTERNS)
        assert hit, f"判定漏掉了 {human} 形态：{text!r} ⇒ 主断言已空转"


# ═══════════════════════════════════════════════════════════════════════════
# 端点级实测 —— 真实走一遍 HTTP，验证响应形态与归档门控
#
# 🔴 为什么必须真跑一次：上面那些断言都是**静态判据**（读源码 / 读路由表）。
# 静态判据查不出「端点抛 500」「信封包装后前端取不到 scenarios」这类问题 ——
# 而这正是 memory 记的 fail-open 高发处：前端 `resp.data?.data ?? resp.data`
# 兜底写法，一旦信封层级变了会静默拿到 undefined，界面只是"没有卡片"。
# ═══════════════════════════════════════════════════════════════════════════


@pytest.fixture
def scenario_client_factory():  # noqa: ANN201
    """构造带鉴权覆盖 + 可控项目状态的测试客户端。"""
    import uuid as _uuid
    from contextlib import asynccontextmanager

    from httpx import ASGITransport, AsyncClient

    from app.core.database import get_db
    from app.deps import get_current_user, require_project_access
    from app.main import app as real_app
    from app.models.base import ProjectStatus as _PS

    @asynccontextmanager
    async def _make(project_status: str):
        project_id = _uuid.uuid4()
        user = type("U", (), {"id": _uuid.uuid4(), "username": "t", "role": "manager"})()

        class _FakeProject:
            def __init__(self, status: str) -> None:
                self.id = project_id
                self.status = status

        class _FakeDb:
            async def get(self, model, pk):  # noqa: ANN001, ANN202, ARG002
                return _FakeProject(project_status)

        overrides = dict(real_app.dependency_overrides)
        real_app.dependency_overrides[get_current_user] = lambda: user
        real_app.dependency_overrides[get_db] = lambda: _FakeDb()
        # require_project_access 是工厂 —— 覆盖它产出的每个依赖
        for route in real_app.routes:
            for dep in getattr(getattr(route, "dependant", None), "dependencies", []):
                call = getattr(dep, "call", None)
                if call and getattr(call, "__qualname__", "").startswith(
                    "require_project_access"
                ):
                    real_app.dependency_overrides[call] = lambda: user
        try:
            transport = ASGITransport(app=real_app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                yield ac, project_id, _PS
        finally:
            real_app.dependency_overrides = overrides

    return _make


@pytest.mark.asyncio
async def test_endpoint_returns_four_scenarios_live(scenario_client_factory) -> None:  # noqa: ANN001
    """执行态项目：四场景全部返回且都不禁用。"""
    async with scenario_client_factory("execution") as (client, project_id, _PS):
        resp = await client.get(f"/api/projects/{project_id}/bulk-tab/scenarios")

    assert resp.status_code == 200, f"端点返回 {resp.status_code}: {resp.text[:400]}"
    body = resp.json()
    # ResponseWrapperMiddleware 会把 2xx JSON 包成 {code,message,data}
    payload = body.get("data", body)
    assert isinstance(payload, dict), f"响应形态异常：{body!r}"

    scenarios = payload.get("scenarios")
    assert isinstance(scenarios, list) and len(scenarios) == len(SCENARIOS), (
        f"期望 {len(SCENARIOS)} 个场景，实际 {scenarios!r}"
    )
    assert payload.get("isArchived") is False
    for item in scenarios:
        assert item["disabled"] is False, f"{item['key']} 在执行态被禁用"
        assert item["disabledReason"] is None
        for field in ("label", "artifactNote", "timingNote"):
            assert item[field], f"{item['key']}.{field} 为空 ⇒ 卡片会渲染空白"


@pytest.mark.asyncio
async def test_endpoint_disables_import_when_archived_live(
    scenario_client_factory,  # noqa: ANN001
) -> None:
    """归档态：导入类禁用且带原因，导出类仍可用（R3.8）。"""
    async with scenario_client_factory("archived") as (client, project_id, _PS):
        resp = await client.get(f"/api/projects/{project_id}/bulk-tab/scenarios")

    assert resp.status_code == 200, f"端点返回 {resp.status_code}: {resp.text[:400]}"
    payload = resp.json().get("data", resp.json())
    assert payload["isArchived"] is True

    by_key = {s["key"]: s for s in payload["scenarios"]}
    # 导出类（archivedAllowed=True）必须仍可用 —— 归档后调阅不了就违背归档意义
    for key in ("blank_template", "archive_export"):
        assert by_key[key]["disabled"] is False, f"{key} 在归档态被误禁用（导出应可用）"

    # 导入类必须禁用且**带可读原因**（只置灰不说原因等于让用户猜）
    for key in ("fill_back", "refresh_edit"):
        item = by_key[key]
        assert item["disabled"] is True, f"{key} 归档态未禁用 ⇒ 点了会被静默跳过"
        assert item["disabledReason"], f"{key} 禁用但无原因说明"
        assert "归档" in item["disabledReason"]


@pytest.mark.asyncio
async def test_endpoint_404_on_missing_project(scenario_client_factory) -> None:  # noqa: ANN001
    """项目不存在时 404，而不是返回一份空场景列表。

    返回空列表会让 UI 显示"没有可用操作"，用户无从判断是权限、状态还是脏数据。
    """
    import uuid as _uuid

    from app.core.database import get_db
    from app.main import app as real_app

    async with scenario_client_factory("execution") as (client, _pid, _PS):
        class _EmptyDb:
            async def get(self, model, pk):  # noqa: ANN001, ANN202, ARG002
                return None

        real_app.dependency_overrides[get_db] = lambda: _EmptyDb()
        resp = await client.get(f"/api/projects/{_uuid.uuid4()}/bulk-tab/scenarios")

    assert resp.status_code == 404, f"期望 404，实际 {resp.status_code}: {resp.text[:300]}"
