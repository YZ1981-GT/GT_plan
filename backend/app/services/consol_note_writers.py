"""合并附注 ``consol_note_data.data`` 写入方登记。

本登记表只描述合并附注数据域的生产写入边界。它与单体附注的
``app.services.note_writers`` 分开维护：合并附注允许同一章节由明细映射、
公式、子树汇总等按不同坐标共同写入，登记的重点是入口完整性和保护元数据
依据，而不是单体附注的字段所有权矩阵。

``entrypoint`` 使用 ``backend`` 包相对模块的 ``模块:限定名`` 形式，限定名
包含类名时保留类层级。后续 AST 守卫以该字符串做登记表双向对账；不要把
路由包装函数另列为 writer，它们在 ``trigger`` 中作为触发入口记录，实际
持久化责任归到本表登记的生产函数。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

WriterRole = Literal["automatic", "manual", "structural", "stale"]

# ``role`` 同时是写入类别；保留显式常量供守卫和调用方校验登记值。
ROLES = frozenset({"automatic", "manual", "structural", "stale"})

# 这些是触发入口的权限/执行上下文，不等同于 writer role。
PERMISSION_LEVELS = frozenset({"edit", "background", "system"})


@dataclass(frozen=True)
class ConsolNoteWriterSpec:
    """一个实际持久化入口的稳定登记。

    ``protection_basis`` 只对 automatic writer 填写，值必须是生产函数体实际
    引用的保护函数名。``permission`` 记录该入口可能由哪类上下文触发；同一
    service 同时被 HTTP 和后台任务调用时用元组保留两种事实。
    """

    writer_id: str
    entrypoint: str
    trigger: str
    role: WriterRole
    permission: tuple[str, ...] = ()
    protection_basis: tuple[str, ...] = ()
    evidence: str = ""

    @property
    def write_kind(self) -> str:
        """兼容把 ``role`` 称为写入类别的调用方。"""
        return self.role

    @property
    def permission_levels(self) -> tuple[str, ...]:
        """权限级别的可读别名，避免调用方自行解释 ``permission``。"""
        return self.permission


def _w(
    writer_id: str,
    entrypoint: str,
    trigger: str,
    role: WriterRole,
    *,
    permission: tuple[str, ...] = (),
    protection_basis: tuple[str, ...] = (),
    evidence: str = "",
) -> ConsolNoteWriterSpec:
    return ConsolNoteWriterSpec(
        writer_id=writer_id,
        entrypoint=entrypoint,
        trigger=trigger,
        role=role,
        permission=permission,
        protection_basis=protection_basis,
        evidence=evidence,
    )


_AUTOMATIC_DETAIL_PROTECTION = ("section_locked", "protected_cells")
_AUTOMATIC_CELL_PROTECTION = ("protected_cells",)


# 直接改变 consol_note_data.data 的入口。路由、任务和前端批量导入都写在
# trigger 中，entrypoint 保持为 AST 可定位的真实持久化函数。
CONSOL_NOTE_WRITERS: tuple[ConsolNoteWriterSpec, ...] = (
    _w(
        "consol-note-manual-save",
        "app.services.consol_node_scope:save_scoped_note_record",
        "PUT /api/consol-note-sections/data/{project_id}/{year}/{section_id}；ConsolNoteTab 手工保存与逐章节 Excel 批量导入（force_overwrite=true）",
        "manual",
        permission=("edit",),
        evidence="record.data=...；ConsolNoteData(...)；赢家重读后仍写同一 data",
    ),
    _w(
        "consol-note-detail-mapping",
        "app.services.consol_note_detail_apply_service:apply_detail_refresh",
        "POST /api/projects/{project_id}/consol-note-detail-refresh/apply；重新汇总的数据叶子",
        "automatic",
        permission=("edit", "background"),
        protection_basis=_AUTOMATIC_DETAIL_PROTECTION,
        evidence="note_record.data=data；调用 section_locked / protected_cells",
    ),
    _w(
        "consol-note-formula-fill",
        "app.services.consol_note_formula_service:fill_by_formula",
        "POST fill-by-formula、POST refresh、POST apply-formulas，以及推送/试算表事件后台刷新",
        "automatic",
        permission=("edit", "background"),
        protection_basis=_AUTOMATIC_DETAIL_PROTECTION,
        evidence="record.data=data；调用 section_locked / protected_cells",
    ),
    _w(
        "consol-note-subtree-aggregate",
        "app.services.consol_note_subtree_reaggregate:_Run._aggregate",
        "POST /api/consolidation/notes/{project_id}/{year}/reaggregate 及异步重新汇总任务",
        "automatic",
        permission=("edit", "background"),
        protection_basis=_AUTOMATIC_DETAIL_PROTECTION,
        evidence="record.data=data；聚合节点按 protected_cells 保留格并检查 section_locked",
    ),
    _w(
        "consol-note-topn-rerank",
        "app.services.consol_note_topn:write_topn",
        "明细映射/子树汇总命中前 N 名章节时的单位重排写入",
        "automatic",
        permission=("edit", "background"),
        protection_basis=_AUTOMATIC_CELL_PROTECTION,
        evidence="record.data=data；write_topn 逐格调用 protected_cells，调用方先检查整节锁定",
    ),
    _w(
        "consol-note-custom-query-cell-writeback",
        "app.services.custom_query.snapshot_writer_modules:write_note_cell",
        "custom-query SnapshotWriter 的附注单格回写（cell-writeback/确认链路）",
        "manual",
        permission=("edit",),
        evidence="原生 UPDATE consol_note_data SET data；回写数值列同时登记 manual_cells",
    ),
    # 这些 helper 会把空行或已有 data 复制到节点专属行；它们不产生新的金额/文字，
    # 但确实会 db.add(ConsolNoteData)，所以登记为 structural 而不是遗漏。
    _w(
        "consol-note-detail-row-initialization",
        "app.services.consol_note_detail_apply_service:_load_or_create_note_data",
        "明细映射首次处理某项目/年度/章节/节点时创建空的合并附注行",
        "structural",
        permission=("edit", "background"),
        evidence="ConsolNoteData(data={})；仅初始化行，实际内容由 apply_detail_refresh 写入",
    ),
    _w(
        "consol-note-formula-node-copy",
        "app.services.consol_note_formula_service:_copy_note_data_record",
        "公式填入根节点从 legacy NULL 行复制到节点专属行",
        "structural",
        permission=("edit", "background"),
        evidence="ConsolNoteData(data=copy.deepcopy(source.data))；不计算或改写来源内容",
    ),
    _w(
        "consol-note-subtree-node-initialization",
        "app.services.consol_note_subtree_reaggregate:_Run._writable_record",
        "子树汇总/TopN 首次写节点时复制 legacy 行或创建空节点行",
        "structural",
        permission=("edit", "background"),
        evidence="ConsolNoteData(data=source copy 或 {})；随后由已登记 automatic writer 写值",
    ),
    # 只改状态列的入口单独登记为 stale；它们不改 data，也不要求保护格解析。
    _w(
        "consol-note-stale-before-push",
        "app.services.consol_push_service:_mark_notes_stale",
        "合并推送开始前把项目年度全部合并附注标为待更新",
        "stale",
        permission=("background",),
        evidence="sa.update(ConsolNoteData).values(is_stale=True)，不写 data",
    ),
    _w(
        "consol-note-stale-formula-year",
        "app.services.formula_settings.propagation:mark_in_year",
        "公式设置传播按年度/章节标记合并附注待更新（domain=consol_note）",
        "stale",
        permission=("system", "background"),
        evidence="sa.update(ConsolNoteData).values(is_stale=True)，不写 data",
    ),
    _w(
        "consol-note-stale-formula-txn",
        "app.services.formula_settings.stale_marks:mark_consol_note_stale",
        "公式定义写入同事务内标记受影响合并附注待更新",
        "stale",
        permission=("system", "background"),
        evidence="sa.update(ConsolNoteData).values(is_stale=True)，不写 data",
    ),
    _w(
        "consol-note-stale-source-section",
        "app.services.consol_note_value_change_service:on_note_section_saved",
        "子企业附注保存后按已确认绑定标记上级合并附注待更新",
        "stale",
        permission=("background",),
        evidence="仅赋值 record.is_stale=True 并 flush，不改 record.data",
    ),
)

# AST 守卫的双向对账入口。原因必须说明命中为何不属于合并附注内容写入，不能用
# 空值豁免；这里列的是会读取 ConsolNoteData 或编排已登记 writer 的生产函数。
CONSOL_NOTE_WRITER_EXCLUSIONS: dict[str, str] = {
    "app.models.consol_note_data_models:ConsolNoteData": (
        "ORM 模型声明和列映射，不执行 db.add/UPDATE，不是写入入口"
    ),
    "app.services.custom_query.fetchers.disclosure:_query_disclosure": (
        "仅 SELECT consol_note_data.data 生成自定义查询结果，不 flush/commit，不修改 data"
    ),
    "app.services.consol_snapshot_service:_capture_consol_notes": (
        "签发快照只读 ConsolNoteData 并序列化分片，不写回业务行"
    ),
    "app.services.consol_readiness_service:load_readiness_facts": (
        "就绪检查只读取 is_stale/source_mode 统计，不修改合并附注"
    ),
    "app.services.custom_query.writeback_preview:WritebackPreviewService._target_in_project": (
        "回写预览只按记录 ID 查询并校验归属，实际 data 写入由 write_note_cell 登记"
    ),
    "app.services.consol_note_formula_service:_note_data_record": (
        "公式服务的精确行读取 helper，仅 SELECT，不创建或更新记录"
    ),
    "app.services.consol_note_formula_service:_note_data_record_exact": (
        "公式服务的节点行读取 helper，仅 SELECT，不创建或更新记录"
    ),
    "app.services.consol_note_topn:topn_denominator": (
        "TopN 分母只读取另一章节已保存数据，不修改 consol_note_data"
    ),
    "app.services.consol_note_formula_refresh_handler:handle_consol_note_formula_refresh": (
        "事件刷新器只做开关/陈旧检查并调用 fill_note_sections，内容写入归 fill_by_formula"
    ),
    "app.services.consol_push_service:_refresh_notes": (
        "推送编排器只调用 stale 标记和 fill_note_sections；直接写入入口已分别登记"
    ),
    "app.services.consol_note_reaggregate_executor:execute_consol_note_reaggregate": (
        "耐久任务只校验权限/租约并调用 reaggregate_subtree，直接写入归 _Run 方法"
    ),
    "app.routers.consol_note_sections:save_note_data": (
        "HTTP 参数校验和事务错误映射；实际 data 持久化由 save_scoped_note_record 完成"
    ),
    "app.routers.consol_note_sections:_load_note_record": (
        "章节 GET 使用的作用域读取 helper，仅加载基准行，不修改 consol_note_data"
    ),
    "app.routers.consol_note_sections:_save_note_record": (
        "章节 PUT 的异常映射 helper，只转调已登记 save_scoped_note_record，不直接写 data"
    ),
    "app.routers.consol_note_sections:fill_note_by_formula": (
        "单章 HTTP 编排；实际 data 持久化由 fill_by_formula 完成"
    ),
    "app.routers.consol_note_sections:refresh_note_by_formula": (
        "刷新 HTTP 编排；实际 data 持久化由 fill_by_formula 完成"
    ),
    "app.routers.consol_note_sections:apply_all_formulas": (
        "批量逐章节 HTTP 编排；实际 data 持久化由 fill_note_sections/fill_by_formula 完成"
    ),
    "app.routers.consol_notes:reaggregate_consol_notes": (
        "重新汇总 HTTP 编排；实际 data 持久化由 reaggregate_subtree 内已登记入口完成"
    ),
    "app.routers.consol_note_detail_templates:api_apply_detail_refresh": (
        "明细映射 HTTP 编排；实际 data 持久化由 apply_detail_refresh 完成"
    ),
    "app.services.consol_artifact_service:collect_workpaper_payload": (
        "交付/签发快照只读取合并附注字段组成 artifact，不 flush/commit，不写业务行"
    ),
    "app.services.consol_node_scope:digest_of": (
        "只按内存 record/data 计算 SHA-256 摘要，不访问数据库、不写字段"
    ),
    "app.services.consol_node_scope:_last_write_source": (
        "只读取 data._last_write_source 生成冲突提示，不修改记录"
    ),
    "app.services.consol_node_scope:_note_scope_filter": (
        "只构造 SELECT 条件表达式，不执行查询或写入"
    ),
    "app.services.consol_node_scope:_load_exact_note_record": (
        "作用域 helper 只 SELECT 精确节点行，写入竞态处理仍在 save_scoped_note_record"
    ),
    "app.services.consol_node_scope:load_scoped_note_record": (
        "作用域 helper 只读取 GET/服务层基准行，不修改 data"
    ),
    "app.services.consol_node_scope:load_scoped_note_records": (
        "作用域 helper 只批量 SELECT 合并附注行，不修改 data"
    ),
    "app.services.consol_note_subtree_reaggregate:_Run._load_records": (
        "重新汇总预取节点记录到内存工作集，后续实际写入由 _aggregate/write_topn 登记"
    ),
    "app.services.consol_note_subtree_reaggregate:_Run._aggregate_topn": (
        "TopN 子树编排只读取下级并调用 write_topn，未直接赋值 data"
    ),
    "app.services.consol_note_subtree_reaggregate:_Run._records": (
        "只从内存缓存读取节点记录，不持久化"
    ),
    "app.services.consol_note_subtree_reaggregate:_Run._exact_record": (
        "只从内存缓存读取精确节点记录，不持久化"
    ),
    "app.services.consol_note_subtree_reaggregate:_Run._source_record": (
        "只选择节点/legacy 基准记录，不持久化"
    ),
    "app.services.consol_note_subtree_reaggregate:_Run._refresh_exact_record": (
        "写入后的补读 helper 只 SELECT 并刷新内存缓存，不更新 data"
    ),
    "app.services.consol_note_subtree_reaggregate:_Run._snapshot": (
        "只更新公式快照字段 last_formula_value，不修改 consol_note_data.data"
    ),
    "app.services.custom_query.snapshot_writer:SnapshotWriter._write_note_cell": (
        "模块薄委托只转发到 snapshot_writer_modules.write_note_cell，实际 SQL 写入已登记"
    ),
    "app.services.custom_query.version_capture:_table_map": (
        "仅导入模型并返回 SQLAlchemy metadata 表映射，版本捕获准备步骤不写业务数据"
    ),
    "app.services.deliverable_readiness_sources:ReadinessSourceChecks._check_notes": (
        "交付就绪检查仅读取合并附注来源和 stale 状态，不写入业务行"
    ),
}


def writer_by_id(writer_id: str) -> ConsolNoteWriterSpec | None:
    """按稳定 writer_id 查登记。"""
    return next((item for item in CONSOL_NOTE_WRITERS if item.writer_id == writer_id), None)


def writers_with_role(role: str) -> tuple[ConsolNoteWriterSpec, ...]:
    """返回指定写入类别的登记项。"""
    return tuple(item for item in CONSOL_NOTE_WRITERS if item.role == role)


def writer_by_entrypoint(entrypoint: str) -> ConsolNoteWriterSpec | None:
    """按 AST 守卫使用的模块限定名查登记。"""
    return next((item for item in CONSOL_NOTE_WRITERS if item.entrypoint == entrypoint), None)


__all__ = [
    "CONSOL_NOTE_WRITERS",
    "CONSOL_NOTE_WRITER_EXCLUSIONS",
    "ConsolNoteWriterSpec",
    "PERMISSION_LEVELS",
    "ROLES",
    "WriterRole",
    "writer_by_entrypoint",
    "writer_by_id",
    "writers_with_role",
]
