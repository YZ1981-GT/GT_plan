"""四场景语义真源 — 底稿导入导出全生命周期（Task 10）

spec: workpaper-import-export-lifecycle-closure（R3.1~R3.4、R3.7、R3.8）

## 这个模块解决什么

用户的四个场景在改造前**没有语义区分**：UI 只有「导出/导入」两个裸按钮，
用户无从判断"我现在该点哪个"、"导出来的东西含不含我填的数据"。

而后端能力**早已建成**：`wp_bulk_router` 有 11 个端点、`bulk_tab/` 有 14 个模块
（`ZipAssembler` 带 sha256 + manifest.json、`bulk_import_service` 带拓扑序回传 +
`conflict_resolver` + `snapshot_guard` + `workflow_gate`、`bulk_async_runner` 带进度）。
**缺的只是语义标注与 UI 入口**，不是能力。

⇒ 本模块是**声明式绑定表**：把四场景与既有端点绑起来，并把「产物含什么」
「什么时点用」的中文说明收成单一真源。前端读它渲染，**不各写一份中文**（R3.7）。

## 🔴 不新造 per-cycle 端点（R3.1）

`SCENARIOS` 里每个 endpoint 都必须是 `app.routes` 里已存在的路径，
守卫 `test_scenario_registry.py` 逐条断言。这条防的是"为了四场景又写一套"。

## 命名偏离登记

design.md 的 `ScenarioSpec` 草案用了中文字段名（`产物说明` / `适用时点`）。
实现改为英文标识符 + 中文取值（`artifact_note` / `timing_note`）——
中文标识符在 Python 合法但会让 IDE 补全、序列化键名、前端 TS 类型全部带中文，
代价大于收益。**字段的值仍是中文**，R3.7 的「文案单一真源」不受影响。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

#: 四场景键 —— 与用户口述的四件事一一对应
ScenarioKey = Literal[
    "blank_template",   # ① 一键导出空白模板
    "fill_back",        # ② 填完导回
    "refresh_edit",     # ③ 四表取数后二次编辑再导回
    "archive_export",   # ④ 归档前后导出已完成底稿
]

Direction = Literal["export", "import", "round_trip"]
BulkMode = Literal["template", "data"]

#: bulk 端点前缀（项目级）。真实注册路径见 `app.routes`，守卫据此逐条核对。
_PREFIX = "/api/projects/{project_id}/bulk-tab"


@dataclass(frozen=True)
class ScenarioSpec:
    """单个场景的语义与端点绑定。

    Attributes:
        key: 场景键。
        label: 场景中文名（UI 标题）。
        artifact_note: **产物含什么** —— UI 直接展示，禁前端硬写（R3.7）。
        timing_note: **什么时点用** —— 同上。

    Note:
        🔴 三段文案的值必须是**可直接呈现的纯文本**，不得含 Markdown 标记
        （`**强调**` / 反引号代码块 / `[链接]()`）。

        2026-08-12 浏览器实测踩到：初版文案里写了 `**不含**`、`` `manifest.json` ``、
        `**仍可导出**`，而消费方 `WpBulkDialog.vue` 用的是纯文本插值 `{{ sc.artifactNote }}`
        ⇒ 用户看到的是字面量星号与反引号。截图见 spec evidence。

        修法选「真源去掉标记」而非「前端加 Markdown 渲染」，因为：
          · 单一真源的**值**若含渲染格式，每个消费方都得实现一套解析器 ——
            这份文案后续还要进 Word 导出说明页、Excel 自证边车，届时又各写一遍
          · 前端渲染需 `v-html`，凭空引入 XSS 面（哪怕当前数据受控）
        守卫 `test_bulk_scenario_ui_single_source.py::test_copy_is_plain_text` 钉死。
        export_endpoint: 导出端点路径模板；纯导入场景为 `None`。
        import_endpoint: 回传端点路径模板；纯导出场景为 `None`。
        mode: ZIP 的 `manifest.json` 里的 `mode` 值。用于**错用校验**（R3.5）：
            拿场景①的模板去场景③回传（或反之）时，两侧 mode 不符即拒绝。
        direction: 方向语义（供 UI 决定按钮组）。
        archived_allowed: 归档态下是否可用（R3.8：导出可用、导入拒绝）。
    """

    key: ScenarioKey
    label: str
    artifact_note: str
    timing_note: str
    export_endpoint: str | None
    import_endpoint: str | None
    mode: BulkMode
    direction: Direction
    archived_allowed: bool


#: 🔴 四场景单一真源。
#:
#: 场景②与③的 `import_endpoint` **必须相同**（R3.4：同一 import 通路），
#: 守卫按此断言 —— 分成两个端点会让回传逻辑分叉、冲突策略无法统一。
SCENARIOS: tuple[ScenarioSpec, ...] = (
    ScenarioSpec(
        key="blank_template",
        label="导出空白模板",
        artifact_note=(
            "仅含表格骨架与表头，不含任何项目数据。"
            "适合发给被审计单位或现场人员手工填写。"
        ),
        timing_note="开始编制前，或需要一份干净底稿重新填写时。",
        export_endpoint=f"{_PREFIX}/export-templates",
        import_endpoint=None,
        mode="template",
        direction="export",
        archived_allowed=True,
    ),
    ScenarioSpec(
        key="fill_back",
        label="导入填好的模板",
        artifact_note=(
            "把「导出空白模板」填好的 ZIP 原样传回，系统按 manifest 逐表写入底稿。"
        ),
        timing_note="拿到填好的模板之后。底稿处于复核通过/归档态时不可导入。",
        export_endpoint=None,
        import_endpoint=f"{_PREFIX}/import",
        mode="template",
        direction="import",
        archived_allowed=False,
    ),
    ScenarioSpec(
        key="refresh_edit",
        label="导出已取数数据 → 编辑 → 导回",
        artifact_note=(
            "含已从四表库取数的内容。取数列不可直接改（会被下次取数覆盖），"
            "可编辑列已在产物内标注。"
        ),
        timing_note="四表取数完成后需要批量微调时。改完用同一入口传回。",
        export_endpoint=f"{_PREFIX}/export-data",
        import_endpoint=f"{_PREFIX}/import",
        mode="data",
        direction="round_trip",
        archived_allowed=False,
    ),
    ScenarioSpec(
        key="archive_export",
        label="导出已完成底稿（归档用）",
        artifact_note=(
            "含全部已录入内容，附 manifest.json 与逐文件 sha256 校验值，"
            "可离线验证完整性。"
        ),
        timing_note="归档前留存或归档后调阅。归档态下仍可导出。",
        export_endpoint=f"{_PREFIX}/export-data",
        import_endpoint=None,
        mode="data",
        direction="export",
        archived_allowed=True,
    ),
)

_BY_KEY: dict[str, ScenarioSpec] = {s.key: s for s in SCENARIOS}


def get_scenario(key: str) -> ScenarioSpec:
    """按键取场景规格。

    Raises:
        KeyError: 未知场景键。**有意 fail-fast** —— 静默返 None 会让 UI
            渲染出空白入口，属"看着有功能实则不可用"的假绿形态。
    """
    if key not in _BY_KEY:
        raise KeyError(f"未知场景: {key!r}，取值域={tuple(_BY_KEY)}")
    return _BY_KEY[key]


def scenarios_for_ui() -> list[dict[str, object]]:
    """产出前端渲染所需的四场景描述（R3.7）。

    前端**只读本函数的输出**，不得自行拼中文说明 —— 守卫扫前端源码钉死。
    """
    return [
        {
            "key": s.key,
            "label": s.label,
            "artifactNote": s.artifact_note,
            "timingNote": s.timing_note,
            "exportEndpoint": s.export_endpoint,
            "importEndpoint": s.import_endpoint,
            "mode": s.mode,
            "direction": s.direction,
            "archivedAllowed": s.archived_allowed,
        }
        for s in SCENARIOS
    ]


@dataclass(frozen=True)
class ModeMismatch:
    """manifest `mode` 与目标场景不符的可读诊断（R3.5）。

    Attributes:
        manifest_mode: ZIP 的 `manifest.json` 里实际写的 mode。
        expected_mode: 目标场景要求的 mode。
        scenario_key: 目标场景键。
        message: 面向用户的中文错误（含**后果**与**下一步**，不只是"不匹配"）。
    """

    manifest_mode: str
    expected_mode: BulkMode
    scenario_key: str
    message: str


#: 错用后果说明 —— 按「实际拿到的 mode」分档，单一真源。
#:
#: 🔴 为什么必须说后果：只说"模式不匹配"用户不知道严重性。
#: 拿空白模板去覆盖已录入数据 = **清空数据**，这是不可逆的；
#: 反之拿数据包当模板填 = 把别人的数据当自己的底稿，属数据串项目。
_MISMATCH_CONSEQUENCE: dict[str, str] = {
    "template": (
        "该 ZIP 是「空白模板」包（不含任何已录入数据）。"
        "按当前场景导入会用空单元格覆盖底稿中已有的录入内容，且不可撤销。"
    ),
    "data": (
        "该 ZIP 是「含数据」包。"
        "按当前场景导入会把包内数据写入底稿，可能覆盖不属于本次编辑的内容。"
    ),
}


def validate_import_mode(
    manifest_mode: object,
    scenario_key: str,
) -> ModeMismatch | None:
    """校验 ZIP 的 `mode` 与目标场景是否相符（R3.5）。

    这是**零新增存储**的做法：`manifest_builder` 早已把 `mode` 写进
    `manifest.json`（实测字段确实存在），此前只是**没人读**——
    `bulk_import_service` 只取 `files` 与 `cycles` 两个键。

    Args:
        manifest_mode: `manifest.json` 的 `mode` 值（可能缺失或类型异常）。
        scenario_key: 目标场景键，必须是可回传的场景。

    Returns:
        `None` 表示相符（放行）；否则返回 `ModeMismatch`，调用方据此拒绝且**零写入**。

    Raises:
        KeyError: `scenario_key` 未知。
        ValueError: 该场景不可回传（无 `import_endpoint`）——
            拿纯导出场景来校验导入属调用方逻辑错，静默放行会让校验形同虚设。
    """
    spec = get_scenario(scenario_key)
    if spec.import_endpoint is None:
        raise ValueError(
            f"场景 {scenario_key!r} 不支持回传（无 import_endpoint），不应用于导入校验"
        )

    actual = str(manifest_mode) if manifest_mode is not None else ""

    # mode 缺失也算不符：无法判断包的性质就不能放行（fail-closed）
    if actual == spec.mode:
        return None

    if not actual:
        detail = "该 ZIP 的 manifest.json 缺少 mode 字段，无法确认它是模板包还是数据包。"
    else:
        detail = _MISMATCH_CONSEQUENCE.get(
            actual, f"该 ZIP 的 mode 为 {actual!r}，不是本场景期望的 {spec.mode!r}。"
        )

    message = (
        f"导入被拒绝：ZIP 类型与所选场景不匹配。\n"
        f"  所选场景：{spec.label}（期望 {spec.mode} 包）\n"
        f"  实际 ZIP：{actual or '未标注'}\n"
        f"  {detail}\n"
        f"  请改用与该 ZIP 匹配的场景，或重新导出正确类型的包。"
    )
    return ModeMismatch(
        manifest_mode=actual,
        expected_mode=spec.mode,
        scenario_key=scenario_key,
        message=message,
    )


def importable_scenario_keys() -> tuple[str, ...]:
    """可回传的场景键（有 `import_endpoint` 的）。"""
    return tuple(s.key for s in SCENARIOS if s.import_endpoint)


def all_endpoints() -> set[str]:
    """本注册表引用的全部端点路径（守卫据此核对 ⊆ `app.routes`）。"""
    out: set[str] = set()
    for s in SCENARIOS:
        if s.export_endpoint:
            out.add(s.export_endpoint)
        if s.import_endpoint:
            out.add(s.import_endpoint)
    return out


__all__ = [
    "SCENARIOS",
    "BulkMode",
    "Direction",
    "ModeMismatch",
    "ScenarioKey",
    "ScenarioSpec",
    "all_endpoints",
    "get_scenario",
    "importable_scenario_keys",
    "scenarios_for_ui",
    "validate_import_mode",
]
