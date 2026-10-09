"""已知 checksum 漂移登记表（spec migration-integrity-and-enum-drift-closure Requirement 3）。

「已应用迁移被事后编辑」时 schema_version 里的 checksum 与磁盘文件不再一致，编辑内容
**不会**在已有库上执行。``MigrationRunner.detect_checksum_drift()`` 能检出这种漂移，
但此前全仓零调用方 —— 7 条漂移（其中 V128 真的缺效果）长期不可见。

本表登记**逐条审阅过**的漂移：每条写明应用时 / 当前两个 checksum 与结论。判据
（:func:`unexplained_checksum_drift`）按 ``(version, stored, current)`` **三元组**比较：

* 文件再被改（current 变）→ 实测三元组对不上 ⇒「未解释」；离线守卫（登记 current ≠ 磁盘实算）也直接红；
* 有人改了 schema_version 的登记值（stored 变）→「未解释」；
* 文件被还原成应用时版本 → 真库漂移消失，离线守卫同样红（登记 current ≠ 磁盘），提示删除该登记项。

所以登记表不是永久豁免：它只对「审阅时看到的那一次编辑」成立。

已知盲区（如实写明）：若有人把 schema_version 的登记值**改写成当前 checksum**，漂移消失而离线守卫
仍绿 —— 这与「新库按当前文件执行」在库里无法区分。这正是下面禁止改写 schema_version 的原因。

🔴 新增漂移的正确处置顺序：先现查真库确认编辑内容是否已生效（逐对象核验），
缺效果就写补齐迁移（先例 V168 / V171），最后才登记。**不要**改写 schema_version 的 checksum
—— 那会抹掉「这个文件被事后编辑过」的唯一证据。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Protocol


@dataclass(frozen=True)
class KnownChecksumDrift:
    version: str
    #: schema_version 里的登记值（应用时的文件 checksum）
    stored: str
    #: 审阅时磁盘文件的 checksum（sha256，行尾按 read_text 归一化）
    current: str
    #: 中文结论：编辑内容是否已在库中生效、由谁补齐、为何不补
    resolution: str


KNOWN_CHECKSUM_DRIFTS: tuple[KnownChecksumDrift, ...] = (
    KnownChecksumDrift(
        "042",
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        "b8632f44c89899edb401e1a9e25c83e7825d9f5d7662bc8d96a4b9b40df3e5fc",
        "应用时为空文件（checksum = sha256 空串，登记时间早于内容提交）：编辑器建空文件后 reload 的"
        " worker 抢先跑了迁移，后写入的 ADD VALUE 'knowledge_doc' 从未执行。已由 V168 补回；"
        "零语句迁移此后由 EmptyMigrationError 拒绝登记，不会复发。",
    ),
    KnownChecksumDrift(
        "046",
        "def75227a4e1131c5c167874b1b900c80dcb71234821b8c6eac29f70283d8cbd",
        "00d520236f55633279e3898ae1dc7964b4b6e87bfb75adf8ed72a6d82fd97144",
        "应用后被编辑；2026-09-29 逐对象核验当前文件声明的 6 个对象在 public 全部存在，无需补迁移。",
    ),
    KnownChecksumDrift(
        "105",
        "1fa373a69bf8bef559974e64266fd481f563f3888140dcfb890f305e9a8d4f9b",
        "073aad20fb69461efc3549c60acfe7b8bed1dfa52c4e66763c5a21f166d35d61",
        "登记名带 (applied_via_V110_repair)：V105 与另一迁移同号冲突被跳过，由 V110 修复迁移补跑；"
        "逐对象核验当前文件声明的 41 个对象在 public 全部存在。",
    ),
    KnownChecksumDrift(
        "128",
        "0727d53bec3e6b4e671a7cdbf3492fb74364f6177acdb48a4d1bbe5c9f2f849e",
        "66ca05c3e1941762a8c57d16ce088a0ec01f4031a84cc42f11c947f6180cb79e",
        "登记值对应 2026-07-26 00:04 首版（833a37fa5）；同日 17:06（04580b855）原地改写：触发器换绑"
        " evgov_forbid_update/delete()、新增两条表注释 —— 从未在库上执行。已由 V171 补齐"
        "（并把 evgov 函数体钉回 V108/V111 原文，不重放改写版里写错的 restrict_violation）。",
    ),
    KnownChecksumDrift(
        "143",
        "manual",
        "94aee11171545b73dd33d4f723e8856439afca5d6d8e8928cc5a064417e22406",
        "登记值为字面量 manual（人工补登，未记 checksum）；逐对象核验当前文件声明的 2 个对象在 public 全部存在。",
    ),
    KnownChecksumDrift(
        "151",
        "e4b72b02a2c0983825bd4c6c5b32f0cbec979f1fd9e565033e918cc4687533f2",
        "74a73cf1327e024c70e9db30da4eacabecfc210e2427379e1e6409448a1979c5",
        "应用后被编辑；逐对象核验当前文件声明的 198 个对象（表/索引/函数/触发器/约束）在 public 全部存在。",
    ),
    KnownChecksumDrift(
        "163",
        "fbfd336a38fffeddf07fc2c4b189aaca2ad500763b848df31d7bc6b42f960cb9",
        "d002d0f2f9abc71b2a91b8c15b0c140fd1237f59b6730b0a992c944743a7d329",
        "应用后被编辑；逐对象核验当前文件声明的 7 个对象在 public 全部存在。",
    ),
)


class _Drift(Protocol):
    version: str
    stored_checksum: str
    current_checksum: str | None


def _key(version: str, stored: str | None, current: str | None) -> tuple[str, str, str]:
    return (str(version), str(stored or ""), str(current or ""))


_KNOWN_KEYS: frozenset[tuple[str, str, str]] = frozenset(
    _key(k.version, k.stored, k.current) for k in KNOWN_CHECKSUM_DRIFTS
)


def unexplained_checksum_drift(drifts: Iterable[_Drift]) -> list[_Drift]:
    """实测漂移中未被登记表**逐字**解释的（三元组任一不同即未解释）。"""
    return [
        d for d in drifts
        if _key(d.version, d.stored_checksum, d.current_checksum) not in _KNOWN_KEYS
    ]
