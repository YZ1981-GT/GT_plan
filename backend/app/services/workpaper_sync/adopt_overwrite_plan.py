"""adopt 覆盖计划（Overwrite_Plan）的**纯数据模型**与稳定摘要。

spec: workpaper-sync-adopt-overwrite-and-refresh-source（Task 3.1）
ADR: ADR-AOS-001（后置 prune）/ ADR-AOS-002（作用域 = declared_table ∩ 本 row_section）/
ADR-AOS-003（dry_run 与真实执行共用同一计划纯函数）

═══ 为什么是独立模块，而不是塞进 `store_mirror.py` ═══

`store_mirror.mirror_projection_into_store` 是 **OO callback 与 adopt 两条路径共用的
同一份执行层**（该模块 docstring 明写抽取目的就是消除第二真源）。本 spec 的
Requirement 2 要求 OO 路径零改动，其 J2 判据是「`store_mirror.mirror_projection_into_store`
函数体内本 spec 符号命中为零」—— 把覆盖计划的类型塞进那个文件会直接削弱这条判据。
故独立成本模块（design §4.1 明写「🔴 **不**放进 `store_mirror.py`」）。

═══ 本模块做什么 ═══

* :class:`ItemOverwriteDelta` —— 逐 `(store item, 分区)` 的四个行身份清单；
* :class:`OverwritePlan` —— 整次 adopt 的声明式计划 + 顺序无关的稳定
  :attr:`OverwritePlan.digest`（即 `plan_digest`）；
* :class:`SkipReason` —— 删除侧跳过原因的**封闭**域（Requirement 4.1 / 4.2 / 4.3）；
* :class:`RowReader` —— 行枚举器的**协议声明**（`compute_overwrite_plan` 的签名需要它）；
* :func:`prune_undeclared_rows` —— **本 spec 唯一破坏性的代码路径**（Task 4.1）：删除侧的
  作用域门 / 空值二分 / 分区门三道保护，纯函数、不碰 DB（六道保护的第 4~6 道在 Task 6.x）。

═══ 本模块不做什么（各有归属任务，不得在此提前实现）═══

* `compute_overwrite_plan` 的聚合逻辑 → Task 4.2。🔴 本文件交付 Task 4.1 后已 **781** 行、
  距 800 门禁只剩 **19** 行 ⇒ Task 4.2 **必须**抽伴生模块（域内第四次同样处置）；
* :class:`RowReader` 对 provider 既有 `iter_store_rows` 门面的**适配实现** → Task 3.4，
  落在**伴生模块** `adopt_row_reader.py`（`diagnose_row_reader` / `resolve_row_reader`）。
  🔴 为什么不在本文件里：`.py` 行数门禁上限 **800**
  （`backend/scripts/check/check_file_size.py` 的 `LIMITS`），适配层追加后本文件 1172 行 ⇒
  提交必被拒，而门禁自己的处置顺序明写「优先拆分 / 抽伴生模块，确有必要才改 whitelist 基线」。
  域内先例：`phase5_g9_store_facade.py`（G9 触到同一门禁）/ `pilot_h1_store_merge.py`。
  🔴 依赖方向**单向**（伴生模块 → 本模块），本模块**不**反向 re-export —— 双向 top-level
  import 在「先 import 伴生模块」的顺序下会拿到半初始化模块而 `ImportError`；
  调用方（Task 4.2）直接从 `adopt_row_reader` 取两个入口即可；
* 接进 `adopt_substrate_response.py`、响应 wire form、`changed_item_count` → Task 6.x
  （🔴 Task 6.4 必须从 `deltas` **派生** `changed_item_count`，不得新增字段，也不得
  再取自 `_diff_snapshots`：ADR-AOS-003 附注实测那个观测量**两个方向都不可信**，
  既会漏报（`applied <= 0 and base_rows` 跳过写库）也会虚报（`json.dumps` 与前端
  `JSON.stringify` 的分隔符差异使真库 200 条大载荷里 155 条重序列化即漂移））。

═══ 三条纪律 ═══

1. **零写入面**：两个类均 `frozen=True`，容器一律 `tuple` / 只读 `Mapping`，且
   `__post_init__` 调**既有** `adapters.base.assert_no_mutation_surface` 实测
   （不自造第二份检查）。计划会被塞进审计 details 做快照，一旦它握着 session，
   「计划不 commit」这条边界就只是注释。
2. **派生量一律不存字段**：四个计数是 `len(清单)`、两侧总行数是 `sum(逐表行数)`、
   跳过清单是 `deltas` 的投影。存一份就是第二真源，两份不一致时没人知道该信哪个。
3. **禁按键名兜底**：行身份键现算 **7** 种取值（`rowId` / `id` / `rowKey` / `key` /
   `month` / `metricName` / `rowUuid`，design § Overview）。本模块的类型对行身份一律
   只当**不透明字符串**看待，不含任何键名假设；身份从哪个键取出来是
   :class:`RowReader`（Task 3.4）的事。
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass, field
from enum import Enum
from itertools import combinations
from types import MappingProxyType
from typing import Any, Collection, Final, Iterator, Mapping, Protocol

#: digest 的**格式域分隔前缀**。归一形态或序列化方式一旦变化，这里必须同步改版本号 ——
#: 否则改动只会静默算出另一个 64 位 hex，看起来仍是合法 digest（见 `OverwritePlan.digest`）。
DIGEST_FORMAT: Final[str] = "aos-overwrite-plan/v1"

#: 四个行身份清单的字段名（Requirement 1.7）。**计数一律 `len()` 派生，不存字段。**
_ROW_LIST_FIELDS: Final[tuple[str, ...]] = (
    "rows_added",
    "rows_deleted",
    "rows_updated",
    "rows_ghost_dropped",
)

#: 必须两两不相交的三个清单（Property 4）。
#:
#: 🔴 `rows_ghost_dropped` **刻意不在内**：Property 3 才是幽灵行语义的归属
#: （「既不出现在结果行集中，也必定出现在 `rows_ghost_dropped` 清单中」）。把
#: ghost ∩ added = ∅ 这条判断挪进构造器，Task 4.5 的变异测试就再也看不到它是否成立 ——
#: 构造不出违例的 property 测试是假绿，不是更强的保护。
_DISJOINT_FIELDS: Final[tuple[str, ...]] = ("rows_added", "rows_deleted", "rows_updated")


class OverwritePlanShapeError(Exception):
    """计划形态不合法（行身份非字符串 / 清单内重复 / 三清单相交 / 跳过却带删除清单等）。

    命名与 `adapters.base.ProjectionShapeError`、`excel_workbook_row_change.RowChangeKindError`
    同风格。它是**编程错误**而不是用户输入错误：`compute_overwrite_plan`（Task 4.2）
    自己算出自相矛盾的计划时当场抛，不留给下游去发现。

    🔴 与 Task 6.2 的三个 domain 错误类分工不同：那三个映射 4xx/5xx，本类不映射
    —— 它出现即说明计划计算有 bug，应当以 500 + 堆栈暴露，不得被翻译成用户可重试的提示。
    """

    error_code = "adopt_overwrite_plan_shape"


class SkipReason(str, Enum):
    """删除侧被跳过的原因。**封闭枚举**，一码一因，禁合并。

    🔴 **为什么不是自由字符串、更不许一律写 `no_row_reader`**：Task 1.2 的交叉核发现，
    判为不可枚举、但注册表 `StoreItemSpec.kind` 明写 `rows` 的条目现算 **18** 条
    （B 分母；A 分母 **19** 条）—— 把它们登记成「载荷不是可按行身份枚举的行数组」就是
    **失效的白名单条目**，Requirement 4.3 的「白名单无失效条目」判据会打红。原因必须
    按真实成因分桶。design §4.1 第 2 步与 § Data Models 响应示例里的 `no_row_reader`
    是 §4.1b（Task 1.2）之前的粗粒度写法，已被四个原因桶取代，故本域内**没有**它。

    🔴 **新增成员必须同时更新 Requirement 4.3 的白名单校验（Task 4.8）**：那条判据是
    「逐条核原因类型」而不是「是否取不到门面」—— 新原因没进校验表就等于开了个后门。

    🔴 **载荷不可解析不在本域内**：非法 JSON / JSON 对象 / JSON 标量 / 含非对象元素的
    数组，Requirement 4.4 要求 fail visible（`AdoptStorePayloadUnreadableError`，
    Task 6.2），不得降级成「跳过」——「当成零行处理」正是那条 AC 点名禁止的。
    """

    #: provider 模块 `importlib.import_module` 抛异常 —— **缺陷**，不是形态使然。
    #: Task 1.2 现算此桶为 **0**，且配了变异对照（import 一个不存在的模块必被检出）
    #: ⇒ 这个 0 是真的 0，不是探针瞎。保留成员，让它再次出现时有处可登记。
    import_failed = "import_failed"

    #: 模块 import 成功，但不暴露 `iter_store_rows` 属性（含 re-export）。
    #: Task 1.2 现算 B 分母 **46** 条 —— 多数是**欠门面**（能力缺口），不是形态使然。
    absent = "absent"

    #: 门面在，但签名不认 `store_item_id` ⇒ 硬绑**别的** item。
    #: Task 1.2 现算 B 分母 **54** 条。
    #:
    #: 🔴 不得「凑合用」：D4 的门面硬绑 `STORE_ITEM_ID='D4-2-rows'` 且写死
    #: `ROW_IDENTITY_STORE_KEY='rowId'`，而同模块另有 `metricName` / `month` / `id`
    #: 三种身份键 ⇒ 拿 `rowId` 去枚举 D4-22 / D4-23 / D4-35 会取不到身份而抛错或错配。
    #: 这正是「禁自造 `row.get('rowId')` 兜底」这条裁决的现场实证。
    item_blind = "item_blind"

    #: 门面 item-aware，但喂本 item 即抛。Task 1.2 现算 **4** 条，属**真缺陷**。
    #:
    #: 🔴 现算这 4 条经归因**全部**落在下一个成员的形态上 ⇒ 登记时一律用更精确的
    #: `row_reader_bound_to_other_entry`；本成员保留给「抛错但成因尚未归因」的情形，
    #: 不是它的同义词。
    item_unresolvable = "item_unresolvable"

    #: G3 / G4 / G5 / G6 四家的 store 门面全部 re-export 自 `phase5_g9_store_facade`，
    #: 而该模块的 `specs_for` 惰性取的是 **G9** 主模块 ⇒ 门面被借给了别的 entry。
    #: Task 1.2 §(6) 登记为**跨 spec 工单**，本 spec 不修（它落在 OO 镜像共用路径上，
    #: 属 Requirement 2 的保护区）。
    #:
    #: 🔴 既不是 `absent` 也不是形态使然 —— 这 4 条的 R3 替代路径成立，工单修好即可
    #: 转入可枚举。写成 `absent` 会让它作为**缺陷**的可见性消失。
    row_reader_bound_to_other_entry = "row_reader_bound_to_other_entry"

    #: adapter 级：该 adapter 根本没有 store item 可谈（Task 1.2 现算 B 分母 **2** 条：
    #: `a51.cashflow_audit` / `c2.control_test_summary`）。
    #:
    #: 🔴 `skipped_items` 的元素是 `(item_id, reason)`，而此原因没有 item_id 可填 ⇒
    #: 它**是否**落进清单由 Task 4.2 裁定；若登记，第一位放 adapter_id。
    no_store_item = "no_store_item"


class RowReader(Protocol):
    """从 store 载荷枚举行身份的**协议**。适配实现是 Task 3.4，本模块只声明形态。

    形态直接对齐引擎 `phase5_row_table_sheet.iter_store_rows(spec, payload)` —— 它
    yield `(row_identity, row)`，且已经做了 Requirement 4.4 要的事：非数组即抛、
    元素非对象即抛、缺稳定身份即抛、重复身份即抛。适配层做**薄转发**，不另写一份解析
    （另写就是第二真源，必与执行侧漂移）。

    🔴 `isinstance(x, RowReader)` 这类形态检查**不是能力证明**，故本协议刻意不加
    `@runtime_checkable`：Task 1.2 的 L4 教训是 G 循环那几家的 `iter_store_rows` 是
    生成器函数，`specs_for` 的抛错发生在**第一次迭代**而不是调用时 ⇒ 只调不消费会
    全判通过。判「能不能枚举」必须真调 + 真消费 + 正面判据（合成 1 行必须真 yield 出
    那个身份）。
    """

    def iter_rows(self, payload: Any) -> Iterator[tuple[str, Mapping[str, Any]]]:
        """yield `(row_identity, row)`。载荷形态非法一律抛，不得静默当成零行。

        `payload` 刻意宽松（JSON 文本 / bytes / 已解析序列），与引擎门面一致 ——
        store 侧载荷来自 `checklist_responses.remark`，调用方拿到的形态并不统一。
        """
        ...

    def section_of(self, row: Mapping[str, Any]) -> str | None:
        """本行的分区归属；无分区维度返回 `None`。

        🔴 **禁硬编码字段名（含 `"section"`）**：取值必须读
        `RowTableSheetSpec.row_section_field`。现算 6 个多分区 store item 的分区字段名
        共 **5** 种取值（`acctClass` / `agingCategory` / `maturityCategory`（g4 与 g6
        共用）/ `sectionKey` / `section`），且合同清单里的
        `"row_section_field": "section"` 是**描述性元数据不是真源** —— 5 处清单里 4 处
        与功能声明值不符（design § Overview 已登记该既存漂移，本 spec 只登记不修）。
        """
        ...


def _canonical_json(obj: Any) -> str:
    """digest 的**唯一**序列化形态。改这里就是改 digest 的定义（见 `OverwritePlan.digest`）。

    `sort_keys=True` 让键序不参与身份；`separators=(",", ":")` 去掉 `json.dumps` 默认的
    空格（🔴 ADR-AOS-003 附注实测：正是这个默认分隔符与前端 `JSON.stringify` 的紧凑形态
    不一致，才让真库 200 条大载荷里 155 条「重序列化即字符串漂移」）；`ensure_ascii=False`
    让中文按原样进摘要，不因转义形态影响结果。
    """
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _frozen_counts(raw: Any, *, label: str) -> Mapping[str, int]:
    """把逐表行数归一成**只读** Mapping，并逐条校验键值形态。

    `dict` 满足 `Mapping` 但可变 —— 直接存进 frozen dataclass 只是「字段不可重绑」，
    调用方手里那份 dict 仍能改计划内容。故一律 copy 后 `MappingProxyType` 封死
    （与 `excel_materialize.SheetCellIndex` 同款做法）。
    """
    if raw is None:
        return MappingProxyType({})
    if not isinstance(raw, Mapping):
        raise OverwritePlanShapeError(
            f"{label} 必须是 Mapping，实得 {type(raw).__name__}"
        )
    counts: dict[str, int] = {}
    for key, value in raw.items():
        if not isinstance(key, str) or not key.strip():
            raise OverwritePlanShapeError(f"{label} 的键不是非空 table_key（实得 {key!r}）")
        # 🔴 `bool` 是 `int` 的子类：不单独排除的话 `{"t": True}` 会被当成「1 行」通过。
        if isinstance(value, bool) or not isinstance(value, int):
            raise OverwritePlanShapeError(
                f"{label}[{key!r}] 必须是 int 行数，实得 {type(value).__name__}（{value!r}）"
            )
        if value < 0:
            raise OverwritePlanShapeError(f"{label}[{key!r}] 行数不得为负，实得 {value}")
        counts[key] = value
    return MappingProxyType(counts)


@dataclass(frozen=True, kw_only=True)
class ItemOverwriteDelta:
    """一个 `(store item, 分区)` 在本次 adopt 覆盖中的行集差异（Requirement 1.7）。

    🔴 **粒度是 `(item_id, table_key, row_section)`，不是 item** —— 这是设计骨架之外
    多出来的一维，理由是 Task 1.2 §(4b) 的两条实测样本：

    * 真分区：`G5-2-rows` 一个 store item 就有 **12** 个真分区（`sectionKey` =
      `s1_/s2_/s3_ × finance_lease/installment_sale/installment_service/other`），
      `G3-2-detail-rows` 有 2 个（`agingCategory`）⇒ Requirement 1.4「只删本次声明分区」
      不是理论风险，delta 必须能按分区分开表达，否则删除侧只能整表做差集、直接删掉
      兄弟分区的行；
    * 重复计数陷阱：`D1-memo-rows` / `I5-2-rows` 各有 **2 个 spec 但无分区字段** ⇒
      逐 spec 枚举会把同一行数两次。本类把 `row_section` 纳入身份，`OverwritePlan`
      才能在构造时断言 `(item_id, table_key, row_section)` 不重复 —— 这是那条缺陷的
      第一道拦。🔴 **真正的去重仍由 Task 4.1 按 `(store_item_id, row_section_value)`
      兑现**，本类只保证「重复了一定会被看见」。

    `kw_only=True` 也不是骨架里的写法：`rows_added` / `rows_deleted` / `rows_updated`
    三个字段同类型且相邻，位置传参一旦错位是**静默**的 —— 而「把新增当成删除」正是本
    spec 唯一破坏性的那一侧。关键字强制使这类错位在语法层就不可能。
    """

    #: store item 身份（`checklist_responses.item_id`）。
    item_id: str
    #: 本 delta 对应的 declared_table。`None` = 不可枚举形态 ⇒ 必须同时给 `skipped_reason`。
    table_key: str | None = None
    #: substrate 有 / store 无 ⇒ 追加（受幽灵行门约束，被剔除的进 `rows_ghost_dropped`）。
    rows_added: tuple[str, ...] = ()
    #: store 有 / substrate 无 ⇒ **删除**。本 spec 唯一破坏性的一侧。
    rows_deleted: tuple[str, ...] = ()
    #: 两侧都有 ⇒ 字段以 substrate 为权威更新。
    rows_updated: tuple[str, ...] = ()
    #: 本次新增但锚点业务名为空、被既有幽灵行门剔除的身份（Requirement 1.6）。
    rows_ghost_dropped: tuple[str, ...] = ()
    #: 非 `None` 即本 item 的**删除侧**被跳过，原因逐条可读（Requirement 4.1 / 4.2）。
    skipped_reason: SkipReason | None = None
    #: 分区归属（`RowTableSheetSpec.row_section_value`）。`None` = 本 item 无分区维度。
    row_section: str | None = None

    def __post_init__(self) -> None:
        # 零写入面实测：复用生产守卫，不在本模块另写一份检查。
        from app.services.workpaper_sync.adapters.base import (
            assert_no_mutation_surface,
        )

        assert_no_mutation_surface(self, label="ItemOverwriteDelta")

        if not isinstance(self.item_id, str) or not self.item_id.strip():
            raise OverwritePlanShapeError(
                f"delta 缺 item_id（实得 {self.item_id!r}）—— 跳过清单、审计 details 与"
                "回滚快照都按 item_id 定位，空身份等于这条记录无从追溯"
            )
        if self.table_key is not None and (
            not isinstance(self.table_key, str) or not self.table_key.strip()
        ):
            raise OverwritePlanShapeError(
                f"{self.item_id} 的 table_key 非法（实得 {self.table_key!r}）—— 「不可枚举」"
                "必须用 None 表达，空串会与真实 table_key 混为一谈"
            )

        self._normalise_row_section()
        self._normalise_skipped_reason()
        self._validate_row_lists()
        self._validate_scope_and_skip()

    # ── 归一 ──────────────────────────────────────────────────────────

    def _normalise_row_section(self) -> None:
        """空串分区归一成 `None`，使「无分区」只有一种表达。

        🔴 理由是 digest 的稳定性：引擎 `RowTableSheetSpec.row_section_value` 默认就是
        `""`（design § Overview 全形态对账里那 1 处「引擎默认 `''`」），若 `""` 与 `None`
        两种写法并存，同一份逻辑计划会算出两个不同 digest，Requirement 3.4 的 409 就会
        对着自己误报。

        🔴 留给 Task 4.1 的约束：`row_section_field` 非空**而** `row_section_value` 为
        `""` 是一种退化声明（语义 = 「该字段为空的那些行」这一**真分区**），它与「无分区」
        在本模型里不可区分 ⇒ Task 4.1 遇到时必须当场抛，不得静默归一。

        现算（🔴 现算值，禁写死；交付时须重算）：6 个多分区 provider 的
        `managed_row_table_specs()` 共 **22** 条 spec，声明了 `row_section_field` 的 **20**
        条里 `row_section_value` 为空串的是 **0** 条 ⇒ 当前树上没有这种退化声明，归一是
        安全的。**变异对照**：同一段扫描在「声明了 field」一侧命中 **20** 非零 ⇒ 这个 0
        不是扫描器失效。另 2 条（`G4-7-items` / `G6-5-fair-value-data`）是 field 与 value
        **都**为空串 —— 那是真正的「无分区」（引擎 `if spec.row_section_field:` 根本不过滤），
        与 Task 1.2 §(4b)「G4/G6 灰度开关未开主明细表」一致，归一成 `None` 正确。
        """
        if self.row_section is None:
            return
        if not isinstance(self.row_section, str):
            raise OverwritePlanShapeError(
                f"{self.item_id} 的 row_section 必须是 str 或 None，"
                f"实得 {type(self.row_section).__name__}"
            )
        if not self.row_section.strip():
            object.__setattr__(self, "row_section", None)

    def _normalise_skipped_reason(self) -> None:
        """接受 `SkipReason` 或其字面值，一律归一成枚举成员；域外取值当场抛。"""
        reason = self.skipped_reason
        if reason is None or isinstance(reason, SkipReason):
            return
        try:
            normalised = SkipReason(str(reason))
        except ValueError as exc:
            raise OverwritePlanShapeError(
                f"{self.item_id} 的 skipped_reason {reason!r} 不在封闭域 "
                f"{sorted(r.value for r in SkipReason)} 内 —— 自由字符串会让 "
                "Requirement 4.3 的「白名单无失效条目」判据形同虚设（Task 1.2 现算：判为"
                "不可枚举但 kind 明写 rows 的条目有 18 条，正是被粗粒度原因掩盖的那一批）"
            ) from exc
        object.__setattr__(self, "skipped_reason", normalised)

    # ── 校验 ──────────────────────────────────────────────────────────

    def _validate_row_lists(self) -> None:
        """四个清单逐条校验形态 + 清单内不重复 + 三清单两两不相交。"""
        for name in _ROW_LIST_FIELDS:
            value = getattr(self, name)
            if not isinstance(value, tuple):
                raise OverwritePlanShapeError(
                    f"{self.item_id}.{name} 必须是 tuple，实得 {type(value).__name__} —— "
                    "list 让调用方与计划共享同一份可变对象，计划进了审计快照后仍可被改"
                )
            for ordinal, identity in enumerate(value):
                if not isinstance(identity, str) or not identity.strip():
                    raise OverwritePlanShapeError(
                        f"{self.item_id}.{name} 第 {ordinal} 项不是非空行身份"
                        f"（实得 {identity!r}）—— 行身份是不透明字符串，不得用 None/空串占位"
                    )
            repeated = sorted(k for k, n in Counter(value).items() if n > 1)
            if repeated:
                raise OverwritePlanShapeError(
                    f"{self.item_id}.{name} 出现重复行身份 {repeated} —— 计数由 len() 派生，"
                    "重复会让「N 行」虚报。🔴 最可能的成因是逐 spec 枚举没去重："
                    "`D1-memo-rows` / `I5-2-rows` 各有 2 个 spec 但无分区字段，两个 spec 都"
                    "会 yield 全表（Task 1.2 §(4b)）⇒ Task 4.1 须按 "
                    "(store_item_id, row_section_value) 去重"
                )

        for left, right in combinations(_DISJOINT_FIELDS, 2):
            overlap = sorted(set(getattr(self, left)) & set(getattr(self, right)))
            if overlap:
                raise OverwritePlanShapeError(
                    f"{self.item_id} 的 {left} 与 {right} 相交于 {overlap} —— 一个行身份"
                    "只能落在追加 / 删除 / 更新之一（Property 4）：三者按「两侧各有无」"
                    "互斥定义，相交说明分类逻辑有 bug"
                )

    def _validate_scope_and_skip(self) -> None:
        """`table_key is None` ⇒ 必须有原因；被跳过 ⇒ 删除清单必须为空。"""
        if self.table_key is None and self.skipped_reason is None:
            raise OverwritePlanShapeError(
                f"{self.item_id} 的 table_key 为 None 却没给 skipped_reason —— "
                "`table_key=None` 的语义就是「不可枚举形态，跳过删除侧」（design §4.1），"
                "不登记原因会让 Requirement 4.2 的显式跳过清单漏掉这一条"
            )
        if self.skipped_reason is not None and self.rows_deleted:
            raise OverwritePlanShapeError(
                f"{self.item_id} 已按 {self.skipped_reason.value} 跳过，却带了 "
                f"{len(self.rows_deleted)} 条 rows_deleted —— Requirement 4.1 跳过的是"
                "**删除侧**；带着删除清单等于把「做不到」写成了「悄悄删了一部分」，"
                "正是那条 AC 要消灭的「静默部分覆盖」"
            )
        # 🔴 刻意**不**要求 added / updated 也为空：Requirement 4.1 只说跳过删除侧。
        #    merge（追加 + 更新）由 `store_mirror` 正常跑完，prune 才是被跳过的那一步。

    # ── 派生量（一律不存字段）────────────────────────────────────────

    @property
    def rows_added_count(self) -> int:
        return len(self.rows_added)

    @property
    def rows_deleted_count(self) -> int:
        return len(self.rows_deleted)

    @property
    def rows_updated_count(self) -> int:
        return len(self.rows_updated)

    @property
    def rows_ghost_dropped_count(self) -> int:
        return len(self.rows_ghost_dropped)

    @property
    def is_skipped(self) -> bool:
        return self.skipped_reason is not None

    @property
    def key(self) -> tuple[str, str | None, str | None]:
        """本 delta 的身份三元组 —— `OverwritePlan` 据此断言不重复。"""
        return (self.item_id, self.table_key, self.row_section)

    def canonical_form(self) -> dict[str, Any]:
        """digest 用的归一形态：清单排序、枚举取 `.value`、派生量不入。

        排序是 Property 6「顺序无关」的实现手段 —— 清单元素的顺序是枚举顺序的副产物，
        不是语义；同一份计划换个枚举顺序必须算出同一个 digest。
        """
        return {
            "item_id": self.item_id,
            "table_key": self.table_key,
            "row_section": self.row_section,
            "rows_added": sorted(self.rows_added),
            "rows_deleted": sorted(self.rows_deleted),
            "rows_updated": sorted(self.rows_updated),
            "rows_ghost_dropped": sorted(self.rows_ghost_dropped),
            "skipped_reason": None if self.skipped_reason is None else self.skipped_reason.value,
        }


@dataclass(frozen=True, kw_only=True)
class OverwritePlan:
    """一次 adopt 覆盖的**声明式计划**。dry_run 与真实执行共用同一份（ADR-AOS-003）。

    骨架之外的三处差异，理由同一条 —— **派生量不存字段**：

    * `store_row_count` / `substrate_row_count` 由 `sum(逐表行数)` 派生（现有
      `_dry_run_summary` 本来就是 `sum(counts.values())`，两处存就必然有一天不等）；
    * `skipped_items` 由 `deltas` 投影派生（见 :attr:`skipped_items`）；
    * 四个计数由 `len()` 派生（见 :class:`ItemOverwriteDelta`）。

    🔴 `store_rows_by_table` / `substrate_rows_by_table` **不能**派生，必须存：store 侧
    一张表的行数 = 未变 + 删除 + 更新，而「未变」不在任何 delta 里；substrate 侧同理
    还含被幽灵门剔除的身份。这两个 Mapping 是原始事实，两个总数才是它们的函数。
    """

    #: 逐 `(item, table, 分区)` 的行集差异。被跳过的 item 也**必须**有一条（见 `skipped_items`）。
    deltas: tuple[ItemOverwriteDelta, ...] = ()
    #: store 侧逐 declared_table 的**可枚举**行数。不可枚举形态的 item 不在其中。
    store_rows_by_table: Mapping[str, int] = field(default_factory=dict)
    #: substrate 侧逐 declared_table 行数（= `projection.row_keys` 逐表长度）。
    substrate_rows_by_table: Mapping[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        from app.services.workpaper_sync.adapters.base import (
            assert_no_mutation_surface,
        )

        assert_no_mutation_surface(self, label="OverwritePlan")

        if not isinstance(self.deltas, tuple):
            raise OverwritePlanShapeError(
                f"deltas 必须是 tuple，实得 {type(self.deltas).__name__}"
            )
        for ordinal, delta in enumerate(self.deltas):
            if not isinstance(delta, ItemOverwriteDelta):
                raise OverwritePlanShapeError(
                    f"deltas 第 {ordinal} 项不是 ItemOverwriteDelta，"
                    f"实得 {type(delta).__name__} —— 裸 dict 绕过全部形态校验"
                )
        repeated = sorted(
            str(key) for key, n in Counter(d.key for d in self.deltas).items() if n > 1
        )
        if repeated:
            raise OverwritePlanShapeError(
                f"deltas 出现重复的 (item_id, table_key, row_section) {repeated} —— "
                "同一分区只能有一条 delta，重复会让计数与跳过清单双重虚报。🔴 最可能的"
                "成因是逐 spec 枚举没按 (store_item_id, row_section_value) 去重"
                "（Task 1.2 §(4b)：`D1-memo-rows` / `I5-2-rows` 各 2 个 spec 无分区字段）"
            )

        object.__setattr__(
            self, "store_rows_by_table",
            _frozen_counts(self.store_rows_by_table, label="store_rows_by_table"),
        )
        object.__setattr__(
            self, "substrate_rows_by_table",
            _frozen_counts(self.substrate_rows_by_table, label="substrate_rows_by_table"),
        )

    # ── 派生量（一律不存字段）────────────────────────────────────────

    @property
    def store_row_count(self) -> int:
        """store 侧可枚举行总数 —— `sum(store_rows_by_table.values())`。"""
        return sum(self.store_rows_by_table.values())

    @property
    def substrate_row_count(self) -> int:
        """substrate 侧行总数 —— `sum(substrate_rows_by_table.values())`。"""
        return sum(self.substrate_rows_by_table.values())

    @property
    def skipped_items(self) -> tuple[tuple[str, SkipReason], ...]:
        """被跳过的 `(item_id, 原因)` **显式清单**（Requirement 4.2：清单，不是总数）。

        🔴 **派生而不是字段**：跳过集合完全由 `deltas` 里 `skipped_reason` 非空的条目
        决定。另存一份就是第二真源 —— 「响应里报了 3 条跳过、`deltas` 里却有 5 条带原因」
        这种自相矛盾没人能发现。

        ⇒ 代价（Task 4.2 必须照办）：**每个被跳过的 item 也要产一条 delta**
        （`table_key=None`、四清单为空、原因非空）。这正是 Requirement 1.7「逐 item」
        想要的形态，且比骨架里「delta 只放成功项、跳过项另列一张表」更少一处漏登记的
        机会。同一 item 多个分区都被跳过时按 `(item_id, reason)` 去重。
        """
        seen: dict[tuple[str, SkipReason], None] = {}
        for delta in self.deltas:
            if delta.skipped_reason is not None:
                seen[(delta.item_id, delta.skipped_reason)] = None
        return tuple(sorted(seen, key=lambda pair: (pair[0], pair[1].value)))

    def canonical_form(self) -> dict[str, Any]:
        """digest 的归一形态。派生量刻意不入 —— 它们是入 digest 字段的函数。"""
        return {
            "deltas": sorted(
                (delta.canonical_form() for delta in self.deltas), key=_canonical_json
            ),
            "store_rows_by_table": dict(sorted(self.store_rows_by_table.items())),
            "substrate_rows_by_table": dict(sorted(self.substrate_rows_by_table.items())),
        }

    @property
    def digest(self) -> str:
        """`plan_digest` —— 顺序无关、内容敏感的 sha256（Requirement 3.3 / Property 6）。

        🔴 **序列化形态是本模块的对外约定，改它等于让所有已发出的 digest 失效**：前端在
        dry_run 拿到 digest、真实执行时回传，服务端重算值必须与之逐字符相等
        （Requirement 3.4 的 409 就靠这一条）。故显式钉死四步：

        1. 归一：:meth:`canonical_form` —— 全部清单排序、`SkipReason` 取 `.value`、
           派生量不入、`row_section` 空串已在 delta 构造时归一成 `None`；
        2. 序列化：:func:`_canonical_json`（`sort_keys=True` / `ensure_ascii=False` /
           `separators=(",", ":")`）；
        3. 域分隔：正文前置 :data:`DIGEST_FORMAT` 与一个换行符，使「格式改了」在版本号上
           可见，而不是静默算出另一个同样合法的 64 位 hex；
        4. 摘要：`hashlib.sha256(...).hexdigest()` —— 小写 hex，满足 `models.is_digest`。

        **顺序无关**：任意清单被置换、任意 delta 被重排、任意 Mapping 键序不同 ⇒ digest
        不变（第 1、2 步各管一半：清单靠排序、字典键靠 `sort_keys`）。
        **内容敏感**：任一行身份、任一逐表行数、任一 `table_key` / `row_section` /
        `skipped_reason` 变化 ⇒ digest 必变。计数不单独入 digest 也仍然敏感 ——
        计数是 `len(清单)`，清单变了摘要就变了。
        """
        return hashlib.sha256(
            f"{DIGEST_FORMAT}\n{_canonical_json(self.canonical_form())}".encode("utf-8")
        ).hexdigest()


def _declared_identities(raw: Any, *, table_key: str) -> frozenset[str]:
    """`row_keys[table_key]` → 身份集合。逐条校验，**空集合是合法值**（Requirement 1.3 的清空）。

    🔴 `str` / `bytes` 必须当场拒收：它们满足 `Collection` 却会被**逐字符**迭代 ——
    `row_keys={"t": "r1"}` 会被读成声明了 `{'r', '1'}` 两个身份，于是真正的 `r1`
    落进「未声明」⇒ **被删**。这是本函数唯一能造成误删的输入形态。
    """
    if isinstance(raw, (str, bytes, bytearray)):
        raise OverwritePlanShapeError(
            f"row_keys[{table_key!r}] 是 {type(raw).__name__} 而不是身份序列 —— 字符串会被逐字符"
            "迭代成一堆假身份，真身份反而落进「未声明」而被删"
        )
    if not isinstance(raw, Collection):
        raise OverwritePlanShapeError(
            f"row_keys[{table_key!r}] 必须是身份集合，实得 {type(raw).__name__}"
        )
    out: set[str] = set()
    for identity in raw:
        if not isinstance(identity, str) or not identity.strip():
            raise OverwritePlanShapeError(
                f"row_keys[{table_key!r}] 含非法行身份 {identity!r} —— 行身份是不透明非空字符串"
            )
        out.add(identity)
    return frozenset(out)


def _reject_unreadable_payload(payload: Any, *, reader: RowReader) -> None:
    """把不可解析/非数组载荷交给 reader 抛**它自己的**原生异常（Requirement 4.4）。

    🔴 不自己抛 `json.JSONDecodeError` 或自造文案：引擎的原生异常
    （`RowTableStorePayloadError`，文案带 `store_item_id`）才是 Task 6.2 要翻译成 422 的那个；
    本模块的 `OverwritePlanShapeError` 刻意不映射状态码，拿它兜住会把 422 变成 500。
    """
    for _identity, _row in reader.iter_rows(payload):
        break
    raise OverwritePlanShapeError(
        f"载荷形态为 {type(payload).__name__}，本函数无从按位置重建，而 reader 却没有拒收它 —— "
        "reader 的 fail-visible 语义已弱化（Requirement 4.4）"
    )


def _as_row_list(payload: Any, *, reader: RowReader) -> list[Any] | None:
    """载荷 → **原始元素 list**（不复制元素）。`None` = 无载荷，无从谈删除。

    🔴 为什么必须自己拿到这个 list：删除侧要产出「保留哪些元素」的新载荷，而
    `reader.iter_rows` **只 yield 声明分区命中的行** —— 分区值未声明的行根本不会被 yield。
    若从 yield 出的行反过来重建载荷，那些行会凭空消失（正是 Requirement 1.4 要防的误删）。
    故一律以**原始 list** 为底、只摘掉被判删的那几个位置。

    🔴 这里只做 `json.loads` 一步归一，**不做任何形态校验** —— 非 list / 元素非对象 /
    缺身份 / 重复身份全部交给引擎（它已逐条做了，见 `RowReader` docstring）。
    """
    if payload is None:
        return None
    if isinstance(payload, list):
        return payload
    if isinstance(payload, (str, bytes, bytearray)):
        try:
            parsed = json.loads(payload)
        except ValueError:
            _reject_unreadable_payload(payload, reader=reader)
            raise AssertionError("unreachable")  # pragma: no cover
        if isinstance(parsed, list):
            return parsed
    _reject_unreadable_payload(payload, reader=reader)
    raise AssertionError("unreachable")  # pragma: no cover


def prune_undeclared_rows(
    payload: Any,
    *,
    row_keys: Mapping[str, Collection[str]],
    reader: RowReader,
) -> tuple[Any, tuple[str, ...]]:
    """删除侧剪枝：只删「声明了的 table ∩ 声明了的分区」里未声明的行身份。

    **纯函数** —— 不碰 DB、不写文件、不改入参（保留的行对象原样复用，不复制也不改动）。
    ADR-AOS-001（后置 prune：merge 跑完再剪）/ ADR-AOS-002（作用域 = declared_table ∩ 本 row_section）。

    ═══ 返回 ═══

    `(新载荷, 被删身份)`。**零删除时第一个元素是入参对象本身**（`is` 相等）——
    Requirement 1.2 的「保持原样不变」按字面兑现，连重序列化都不会发生
    （ADR-AOS-003 附注实测：`json.dumps` 与前端 `JSON.stringify` 的分隔符差异会让真库 200 条
    大载荷里 155 条「重序列化即字符串漂移」，白白虚报一次 item 变更）。
    有删除时第一个元素是**保留行的新 list**（原序）；序列化归调用方，本函数不碰。
    第二个元素按身份排序去重，故 `len()` 即「删了几行」。
    🔴 已知表达局限：同一身份串若同时出现在两个分区且只有一侧被删，它在清单里仍只出现一次
    （`ItemOverwriteDelta` 的粒度是 `(item, table, 分区)`，按分区分桶是 Task 4.2 的活）。

    ═══ 签名为何偏离 design §4.1 骨架的 `declared: frozenset[str]` ═══

    骨架是**每表一个身份集**，那样 Requirement 1.3 的二分就根本无从表达 ——「不在键集合」
    与「在键集合但值为空元组」在一个 `frozenset` 里长得一模一样（都是空）。本任务恰恰要
    兑现这条二分，故必须拿到**整份** `row_keys` 并用 `in` 判键集合。

    ═══ 三条门 ═══

    1. **作用域门**（Requirement 1.2）：只有 `table_key in row_keys` 的 scope 参与删除侧。
       与 overlay 的 `in` 判据、materialize 收敛的
       `dynamic_table.table_key in projection.row_keys` 是**同一条规则的第三处落地**。
    2. **空值二分**（Requirement 1.3）：`in` 判**键集合**，不用 `.get()`。
       `.get(table_key) or ()` 会把「未声明」和「声明为空」压成同一个空集 ⇒ 未声明的表被**清空**，
       那是本 spec 唯一破坏性路径上最严重的一种错。
    3. **分区门**（Requirement 1.4）：行的分区归属取自 `reader.section_of(row)`，**逐字**去
       `in_scope` 里查；查不到即作用域外 ⇒ 保留。兄弟分区（声明了 spec 但其 table 不在
       `row_keys` 里）与分区值未声明的行都落在这条上。
       🔴 引擎 `iter_store_rows` 明写「三段读同一个数组」⇒ 做 `base - projection` 全量差集
       会直接删掉兄弟分区的行。

    ═══ 去重（ADR-AOS-005 §5(3)）═══

    `D1-memo-rows` / `I5-2-rows` 各有 2 个 spec 但无 `row_section_field` ⇒ 引擎不过滤、
    逐 spec 枚举会把**同一行 yield 两次**。本函数按**位置**记删除、按**身份**收清单
    （`dict` 保序去重）⇒ 同一行只删一次、只登记一次。
    `adopt_row_reader._declared_scopes` 与 `adopt_row_reader_r3.dedup_specs` 都**不替本函数
    兑现这条**（前者去重 `(table_key, 分区)` 整对，后者去重 spec；两者 docstring 已如此声明）。

    ═══ 当场抛：**三类 / 共 7 处** ═══

    1. **reader 形态不一致（3 处，全在本函数体内）**：不带 `declared_scopes`（无从把行的分区
       映射到 table）· **退化声明** —— `section_field` 非空而某 scope 分区值是 `""`，语义是
       「该字段为空的那些行」这一**真分区**，与「无分区」在 `ItemOverwriteDelta` 里不可区分
       （Task 3.1 `_normalise_row_section` 明写「Task 4.1 遇到时必须当场抛，不得静默归一」；
       现算 0 例，判据仍须在）· 反向不一致 —— `section_field` 为空却声明了分区（`section_of`
       将恒为 `None` 而永不命中 ⇒ 静默少删）。
    2. **`row_keys` 形态非法（3 处，在 `_declared_identities`）**：裸 `str` / 非集合 / 元素不是
       非空字符串。第一条是本函数唯一能造成**误删**的输入形态（逐字符迭代成假身份）。
    3. **reader yield 出不属于入参 list 的行对象（1 处）**：无从按位置删；静默跳过会让计划报了
       删除而落库没删（Requirement 3.8 当场破）。

    🔴 载荷**不可解析 / 非数组**不在上述三类内 —— 由引擎原生异常穿透
    （`RowTableStorePayloadError`，Requirement 4.4），见 :func:`_reject_unreadable_payload`。
    """
    scopes = tuple(getattr(reader, "declared_scopes", ()) or ())
    if not scopes:
        raise OverwritePlanShapeError(
            "reader 未给出 declared_scopes —— 行的分区归属就无从映射到 declared_table，"
            "作用域门（Requirement 1.2）与分区门（Requirement 1.4）都无从判定"
        )
    section_field = str(getattr(reader, "section_field", "") or "")

    # ── 作用域门 + 空值二分：`in` 判键集合，**不得**换成 `.get()` ──────────────
    in_scope: dict[str | None, set[str]] = {}
    for table_key, section in scopes:
        if section_field and section == "":
            raise OverwritePlanShapeError(
                f"{table_key!r} 声明了 row_section_field {section_field!r} 却把分区值留空 —— "
                "这是退化声明（语义 = 「该字段为空的那些行」这一真分区），与「无分区」在计划"
                "模型里不可区分，必须先在 provider 侧显式化，不得在此静默归一"
            )
        if not section_field and section is not None:
            raise OverwritePlanShapeError(
                f"reader 的 section_field 为空却声明了分区 {section!r}（table {table_key!r}）—— "
                "行的 section_of 将恒为 None 而永不命中该分区，删除侧会静默少删"
            )
        if table_key not in row_keys:  # 🔴 未声明 ⇒ 一个字节都不碰
            continue
        in_scope.setdefault(section, set()).update(
            _declared_identities(row_keys[table_key], table_key=table_key)
        )
    if not in_scope:
        return payload, ()

    rows = _as_row_list(payload, reader=reader)
    if not rows:
        return payload, ()

    position_of: dict[int, int] = {}
    for ordinal, element in enumerate(rows):
        position_of.setdefault(id(element), ordinal)

    doomed: set[int] = set()
    deleted: dict[str, None] = {}
    for identity, row in reader.iter_rows(rows):
        declared = in_scope.get(reader.section_of(row))  # 🔴 逐字查，不归一进「无分区」桶
        if declared is None or identity in declared:
            continue
        ordinal = position_of.get(id(row))
        if ordinal is None:
            raise OverwritePlanShapeError(
                f"reader yield 出的行 {identity!r} 不是入参载荷的元素（reader 自己又解析了一遍）"
                " —— 无从按位置删除；静默跳过会让计划报了删除而落库没删（Requirement 3.8）"
            )
        doomed.add(ordinal)
        deleted[identity] = None
    if not doomed:
        return payload, ()
    kept = [element for ordinal, element in enumerate(rows) if ordinal not in doomed]
    return kept, tuple(sorted(deleted))


__all__ = [
    "DIGEST_FORMAT",
    "ItemOverwriteDelta",
    "OverwritePlan",
    "OverwritePlanShapeError",
    "RowReader",
    "SkipReason",
    "prune_undeclared_rows",
]
