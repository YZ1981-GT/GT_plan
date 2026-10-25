# -*- coding: utf-8 -*-
"""OO→HTML 物化计划复用三方提取里同一份 incoming 的逐 binding 提取结果。

spec: oo-return-to-form-dead-end-and-save-speed · R3 · P8

═══ 为什么 ═══

一次 OO 保存的 apply 在同一份 durable incoming 上提取两遍：

1. `oo_to_html.extract_three_way` → `ExcelSyncAdapter.extract(incoming)`：每个 binding 一次
   `extract_projection`，带 base 做受保护格篡改分类；
2. 随后 `ContentMutationService` → `adapter.materialize(substrate=incoming)`：
   `excel_materialize._plan_materialize_step` 对每个 binding 再跑一次 `extract_projection`，
   不带 baseline。

两遍的输入只差 baseline，而 baseline 只影响 `protected_findings`（`_classify_protected_tamper`
是它唯一的读者），写入计划从不读这一项（只读 region / scan / formula_inventory / projection /
identity_inventory）。所以第二遍直接用第一遍的结果：去掉 findings 后，与不带 baseline 的
重新提取逐字段相同。

═══ 何时复用（全部满足才用，任一不满足照常提取）═══

* 同一个 adapter 实例：登记挂在实例的 `_baseline` 上（OO→HTML 每个 operation 一个实例）；
* 文件内容相同：按字节 sha256 比，不按路径 / mtime。链式回落的后续趟读的是中间产物，内容
  不同自然不命中；写入用的是中性化副本（G7）等其它副本时整份不取；
* 唯一例外：写入用的是「只把 `_GT_SYNC` runtime binding 从冻结 base 重注回去」的副本
  （`reinject_runtime_binding_from_base_if_needed`；OnlyOffice 保存常把那个隐藏 sheet 掏空，
  真实保存几乎每次都走这条）。提取不读那个隐藏 part 的内容（判据钉住：掏空与重注后逐字段
  相同），且取出时逐个 zip 部件核对两份文件只差这一个 part ⇒ 副本的字节摘要也认；
* substrate 形态（role / kind / state）、binding、冻结定义（同一对象）、limits、是否保留
  identity 清册全都相同；
* 第一遍没有退役身份：只有同一次提交里反读刚物化的产物才带它，保留门的判据随它变。

登记只在 incoming 形态的提取里发生；物化开头取出即删（一次登记只给一次物化用）。
"""
from __future__ import annotations

import dataclasses
import hashlib
import zipfile
from pathlib import Path
from typing import Any, Callable, Iterable

from app.services.workpaper_sync.adapters.base import SubstrateRole

__all__ = ["IncomingViews", "record_incoming_views", "take_incoming_views"]

_STORE_KEY = "incoming_views"


def _shape_key(shape: Iterable[Any]) -> tuple[str, ...]:
    """(role, kind, state) → 值元组：枚举与同值字符串视为同一形态（engine 两种都收）。"""
    return tuple(str(getattr(part, "value", part)) for part in shape)


@dataclasses.dataclass
class IncomingViews:
    """一次 incoming 提取的逐 binding 结果（findings 已去掉），连同复用判据要比对的输入。"""

    content_sha256: str
    shape: tuple[str, ...]
    definitions: Any
    limits: Any
    #: table_key → (binding, 是否保留 identity 清册, 去掉 findings 的 outcome)
    views: dict[str, tuple[Any, bool, Any]] = dataclasses.field(default_factory=dict)
    #: 重注了 runtime binding 的写入副本的 sha256（见模块 docstring 的唯一例外；取出时才填）。
    alias_sha256: str | None = None
    #: 已核对过内容的源字节对象：单趟物化的全部 binding 共用一份字节，只算一次 sha256。
    _verified: bytes | None = dataclasses.field(default=None, repr=False)

    def add(self, binding: Any, retain_identity_inventory: bool, outcome: Any) -> None:
        self.views[binding.table_key] = (
            binding,
            bool(retain_identity_inventory),
            dataclasses.replace(outcome, protected_findings=()),
        )

    def view_for(
        self,
        *,
        source_bytes: bytes,
        binding: Any,
        shape: Iterable[Any],
        definitions: Any,
        limits: Any,
        retain_identity_inventory: bool,
    ) -> Any | None:
        """判据全部满足 ⇒ 该 binding 的 outcome；否则 None（调用方照常提取）。"""
        found = self.views.get(binding.table_key)
        if found is None:
            return None
        view_binding, retained, outcome = found
        if (
            view_binding != binding
            or retained != bool(retain_identity_inventory)
            or _shape_key(shape) != self.shape
            or definitions is not self.definitions
            or limits != self.limits
        ):
            return None
        if self._verified is not source_bytes:
            if hashlib.sha256(source_bytes).hexdigest() not in (self.content_sha256, self.alias_sha256):
                return None
            self._verified = source_bytes
        return outcome


def _ignore(binding: Any, retain_identity_inventory: bool, outcome: Any) -> None:
    return None


def record_incoming_views(
    adapter: Any, *, artifact: Path, shape: Iterable[Any], retired: Iterable[str]
) -> Callable[[Any, bool, Any], None]:
    """`adapter.extract` 开头调；返回逐 binding 的登记函数。

    incoming 形态且无退役身份 ⇒ 新建一份登记（替换上一份）；否则返回空操作、不动已有登记
    （base / current 是已发布形态，不影响之前登记的 incoming）。
    """
    key = _shape_key(shape)
    if key[0] != SubstrateRole.incoming.value or tuple(retired or ()):
        return _ignore
    views = IncomingViews(
        content_sha256=hashlib.sha256(Path(artifact).read_bytes()).hexdigest(),
        shape=key,
        definitions=adapter.definitions,
        limits=adapter._limits,
    )
    adapter._baseline[_STORE_KEY] = views
    return views.add


def take_incoming_views(
    adapter: Any, substrate: Path, substrate_for_write: Path, *, reinjected: Path | None = None
) -> IncomingViews | None:
    """物化开头调：取出并删掉登记。

    写入用原 substrate ⇒ 用；用的是 `reinjected`（只重注了 runtime binding 的副本）且逐部件核对
    只差那个隐藏 part ⇒ 也用（认副本的字节摘要）；其它副本（G7 中性化等）⇒ 不用。
    """
    views = adapter._baseline.pop(_STORE_KEY, None)
    if views is None:
        return None
    if substrate_for_write is substrate:
        return views
    if (
        reinjected is not None
        and substrate_for_write is reinjected
        and _differs_only_in_sheet(substrate, reinjected, adapter.binding.metadata_sheet)
    ):
        views.alias_sha256 = hashlib.sha256(Path(reinjected).read_bytes()).hexdigest()
        return views
    return None


def _differs_only_in_sheet(original: Path, copy: Path, sheet_name: str) -> bool:
    """两份 xlsx 除 `sheet_name` 那一个 worksheet part 外逐部件相同（名字、CRC、大小）。"""
    from app.services.workpaper_sync.excel_extract import _sheet_parts

    with zipfile.ZipFile(original) as zf_a, zipfile.ZipFile(copy) as zf_b:
        part = _sheet_parts(zf_b).get(sheet_name)
        if part is None:
            return False
        left = {i.filename: (i.CRC, i.file_size) for i in zf_a.infolist() if i.filename != part}
        right = {i.filename: (i.CRC, i.file_size) for i in zf_b.infolist() if i.filename != part}
    return left == right
