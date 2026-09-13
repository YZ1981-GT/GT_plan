"""自定义底稿三入口的稳定 action id 契约。

Spec: custom-workpaper-template-ingestion-and-sync-closure
Requirements: 1.1, 1.2, 1.3, 1.4, 1.6

设计口径
========

Requirement 1.4 要求：telemetry、审计、幂等与 UI 表达动作时必须使用稳定 action id，
不能只靠中文按钮文字。原先三条链完全靠端点路径 + 中文文案区分：

* `GtCustomWpBatchDialog` 的「确认创建」→ POST create-custom-batch（只提交清单行，
  零二进制）；
* `/api/custom-templates` 的 `POST ""` → 只落 `template_file_path` 字符串元数据；
* `ingest_excel_template` —— **基线不存在**（见 T01 §A3）。

本模块是三条 action 的唯一真源：路由、service、审计、测试都从这里取值，不再各自
散写字面量。

🔴 三者的成功语义互斥（Requirement 1.6）。`success_semantics` 描述的是「这个 action
真实造成的副作用」，不是营销文案：

* `batch_create_blank` —— 只创建空白底稿记录，**不**保存/解析/发布任何 Excel 模板；
* `maintain_metadata` —— 只维护名称/分类/描述，**不**接收二进制、不生成 preflight /
  candidate / publication、不改变项目 artifact；
* `ingest_excel_template` —— 才是摄取真实 multipart 字节，进入 quarantine/preflight
  生命周期。

原先「上传成功」这类文案同时被三条链复用，正是 Requirement 1.6 要消除的混淆。
"""
from __future__ import annotations

from dataclasses import dataclass

# ─────────────────────────────────────────────────────────────────────────────
# 1) 稳定 action id —— 精确三值，不得增删
# ─────────────────────────────────────────────────────────────────────────────

BATCH_CREATE_BLANK: str = "batch_create_blank"
MAINTAIN_METADATA: str = "maintain_metadata"
INGEST_EXCEL_TEMPLATE: str = "ingest_excel_template"

#: 全平台唯一的三条 action id。顺序固定：批量空白 → 元数据 → 摄取。
ACTION_IDS: tuple[str, ...] = (
    BATCH_CREATE_BLANK,
    MAINTAIN_METADATA,
    INGEST_EXCEL_TEMPLATE,
)

ACTION_ID_SET: frozenset[str] = frozenset(ACTION_IDS)


@dataclass(frozen=True, slots=True)
class ActionSpec:
    """一条入口的语义契约。

    Attributes:
        action_id: 稳定 id（Requirement 1.4），用于 telemetry / 审计 / 幂等键前缀。
        ui_label: 中文按钮文字，**仅用于展示**，禁止作为行为判据。
        side_effects: 真实副作用的可读枚举（Requirement 1.6）。
        consumes_binary: 是否接收真实二进制。只有摄取入口为 True。
        produces_publication: 是否可能产出 publication。基线下三条都为 False。
    """

    action_id: str
    ui_label: str
    side_effects: tuple[str, ...]
    consumes_binary: bool
    produces_publication: bool


#: 三条入口的完整语义。`side_effects` 用于生成成功文案，禁止越界描述。
ACTION_SPECS: dict[str, ActionSpec] = {
    BATCH_CREATE_BLANK: ActionSpec(
        action_id=BATCH_CREATE_BLANK,
        ui_label="确认创建",
        side_effects=("create_blank_workpaper_rows",),
        consumes_binary=False,
        produces_publication=False,
    ),
    MAINTAIN_METADATA: ActionSpec(
        action_id=MAINTAIN_METADATA,
        ui_label="保存模板信息",
        side_effects=("update_template_metadata",),
        consumes_binary=False,
        produces_publication=False,
    ),
    INGEST_EXCEL_TEMPLATE: ActionSpec(
        action_id=INGEST_EXCEL_TEMPLATE,
        ui_label="上传 Excel 自定义模板",
        side_effects=(
            "quarantine_bytes",
            "preflight",
            "create_mapping_draft",
            "freeze_candidate",
        ),
        consumes_binary=True,
        produces_publication=False,  # finalize 是独立 action（Task 11），不在摄取内
    ),
}


class UnknownActionId(ValueError):
    """请求携带未登记的 action id。

    🔴 不静默回落到「第一个 action」：回落会让错误的字节被当摄取处理（越权写 quarantine）。
    """


def spec_for(action_id: str) -> ActionSpec:
    """按 action id 取语义契约；未登记即抛错。"""
    try:
        return ACTION_SPECS[action_id]
    except KeyError:
        raise UnknownActionId(
            f"未登记的 action id: {action_id!r}（合法取值 {sorted(ACTION_IDS)}）"
        ) from None


def success_message(action_id: str, *, created: int = 0, skipped: int = 0) -> str:
    """生成只描述真实副作用的成功文案（Requirement 1.6）。

    🔴 判据是 `consumes_binary` / `produces_publication`，不是中文字串匹配。
    任何一条都**不会**输出「模板已上传」或「模板已发布」——摄取入口在 finalize 前
    也不发布（Task 11 的 visibility saga 才做发布）。
    """
    spec = spec_for(action_id)
    if spec.action_id == BATCH_CREATE_BLANK:
        return f"已创建 {created} 个空白底稿，跳过 {skipped} 个"
    if spec.action_id == MAINTAIN_METADATA:
        return "已保存模板名称、分类或描述（未接收任何文件，未生成候选或发布）"
    if spec.action_id == INGEST_EXCEL_TEMPLATE:
        return "已接收文件并进入隔离预检（未发布、未生成项目底稿）"
    # 单文件不可达：ACTION_SPECS 是封闭枚举，这里只为类型完整。
    raise UnknownActionId(f"无可生成文案的 action id: {action_id!r}")


def is_ingestion(action_id: str) -> bool:
    """是否是摄取入口（唯一会碰真实字节的入口）。"""
    return spec_for(action_id).consumes_binary
