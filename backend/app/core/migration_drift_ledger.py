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
    KnownChecksumDrift(
        "189",
        "3376d39236144cf901dd360ff58fb74a10ffc5ce0cdcd121840135e108aa069c",
        "a9c6b4cb58b79259d004ca6c74c4f9a76b7e6f11808b8340610b0398d5a1687b",
        "应用时为 V189__deliverable_edit_and_writeback_integrity.sql（trio spec），后被并发会话替换为"
        " V189__create_share_change_event_table.sql：原 deliverable 相关对象（deliverable_section_state/"
        "word_export_task_versions/working_paper 两新列）由 V191 补建；share_change_event 表/约束/索引"
        " 3 个对象经逐列核验（22 列）在 public 全部存在。两份内容的效果均已在库中生效，无需补迁移。",
    ),
    KnownChecksumDrift(
        "200",
        "0f61eac8389d5dfc48024894e3817e1297bff9dad44a2c1a5a500fe07d010b14",
        "a7de9ae311bc753c73a3cd43b397d71a8cdd1db3d97cb4d028a95f28596bc677",
        "应用时为 V200__consol_note_mapping_reuse_and_reference.sql（consol-note-pull spec），后被"
        "partner-manager-edit-permission spec 替换为 V200__partner_manager_edit_level_backfill.sql："
        "原 consol_note_mapping 相关对象（consol_note_mapping_rule_template/consol_note_mapping_rule/"
        "consol_note_mapping_binding 3 表 + 3 PK 索引）经逐对象核验在 public 全部存在；替换后的"
        " partner_manager 回填内容由 V201 执行。两份内容的效果均已在库中生效，无需补迁移。",
    ),
    KnownChecksumDrift(
        "201",
        "a7de9ae311bc753c73a3cd43b397d71a8cdd1db3d97cb4d028a95f28596bc677",
        "eedeb59b41f868a49d7c7c6c94516e0b4ac636babdf5a2291bb5dd1048efc5d9",
        "应用后注释中版本号从 200 改为 201（R200 改为 R201）；SQL 语句体不变。"
        "project_user_level_backfill 表（7 列）经逐列核验在 public 存在，回填 CTE 幂等。无需补迁移。",
    ),
    # ── 2026-10-25 本地拉取后新增的 11 条 checksum 漂移 ──────────────
    KnownChecksumDrift(
        "005",
        "4c3b449f79b731e05b0d5a956d6f45974e58bd0c13254f3767c6b7ccb42a5a72",
        "1f090aa8e4b386f8fed4d1a0aadb7d997d8c3d7f4d6dd6afa4a4d83ebb907d97",
        "V005__enable_rls.sql 应用后被编辑；RLS 策略在真库已生效（health/startup 无 RLS 异常），"
        "效果由 V178 修补（repair_v005）。无需补迁移。",
    ),
    KnownChecksumDrift(
        "006",
        "5d8bc687d6955c41991a8c6e6fa2e779dbaf57ab3adacc0fa00117753062a826",
        "e208aa45e2fd7711e28da2198c1d84761c5d9043a4af2879b53c733fdd3e7924",
        "V006__eqcr_snapshots.sql 应用后被编辑；eqcr_snapshots 表在真库存在且可查。无需补迁移。",
    ),
    KnownChecksumDrift(
        "010",
        "75b4426d7af3aa6329f7aa27c0df2c3e8d23fec96a297f17afdcb56052ea53f7",
        "14a8718657cfb215d5532f0cf61be2f7f8ad1f91d6a4e4c93b60ea2de8adbea4",
        "V010__work_hour_entries.sql 应用后被编辑；work_hour_entries 表在真库存在且可查。无需补迁移。",
    ),
    KnownChecksumDrift(
        "016",
        "1b8bd5a05e34057a30282e5b0d48c0d5cb5ba0c10f1129172432d157c5ca4aed",
        "d7ad301fcb44bcfffa59274533df28e3bca34b8d064cf5cc953d46aebdeeb69c",
        "V016__add_kb_document_version.sql 应用后被编辑；knowledge_documents 表含版本列，在真库存在。"
        "无需补迁移。",
    ),
    KnownChecksumDrift(
        "017",
        "4eaa3d8d8c33f7fd57d2afa48ceb5326cc58b4d6e47f280ebcb0af8ab965aed3",
        "fb46b27d6ab7f2e37c1c67c0a7969dbd3360b94e4684cd426aa0b8301caba3b6",
        "V017__fix_schema_drift.sql 应用后被编辑；schema 修补内容（ALTER/ADD COLUMN）在真库已存在。"
        "无需补迁移。",
    ),
    KnownChecksumDrift(
        "019",
        "72eadeb331edeab7e9738d64984cfb74a0e657f9d37f357c61e65a41c5a2d1f6",
        "ee63dd219d63ceadb782949e7cd67a6ffc74e5c9c705b15db63d20f33d6ad495",
        "V019__add_note_section_id_columns.sql 应用后被编辑；disclosure_notes 的 section_id 列在真库存在。"
        "无需补迁移。",
    ),
    KnownChecksumDrift(
        "051",
        "48054d52f39a257c013aec7b9966bf7c45b122fa32378c943c3a37101ef36fcf",
        "5fac975524e9fddf96e47c869cce17a976ea2f24cdac23179b5b9c56e882a9f1",
        "V051__fix_schema_drift_orm_extra.sql 应用后被编辑；ORM 对齐修补内容在真库已生效。"
        "无需补迁移。",
    ),
    KnownChecksumDrift(
        "057",
        "d345271b6d5e092e835f10863d244962976836fc33012c268ce9dce1ba686dd4",
        "bf087518cfe47ac97adbd1e990b0022b50dcfbeb3a817fa2e83586c1c01f1b79",
        "V057__editing_locks.sql 应用后被编辑；editing_locks 表在真库存在且可查。无需补迁移。",
    ),
    KnownChecksumDrift(
        "178",
        "5a544282c1314395638ef47d8b021ca7412e3c69f01a3ec2b8962c37eae6ab99",
        "4384501c68be36e24208ef3d7e3850233200506ded9cfc05ce993502c5aca4e2",
        "应用时为 V178__repair_v005_admin_query_all_reports.sql，后被替换为"
        " V178__consol_worksheet_runtime_cas_and_formula_binding.sql：原 repair 内容（RLS 策略修补）"
        "与替换后的 consol_worksheet 相关对象均已在真库生效。无需补迁移。",
    ),
    KnownChecksumDrift(
        "179",
        "2b11af3830502c80976021eb6a50370fa0854ea551eb11b3f699ebc6009ffbf2",
        "a409a2fe4519fe6f1e273fdc79697c35175d2b4ed41af75d8778615243c45f4b",
        "应用时为 V179__repair_v019_disclosure_notes_constraint_and_indexes.sql，后被替换为"
        " V179__report_config_adjustment_formula.sql：原 disclosure_notes 修补与替换后的"
        " report_config 调整列均已在真库生效。无需补迁移。",
    ),
    KnownChecksumDrift(
        "180",
        "52add1c191649fb5fa1ebd9eeff034687541ae871b539ef1c69405b532bcb809",
        "aef632fae5926a558f8e40709df985d506cd0fac2167039b3bbac15abe166e23",
        "应用时为 V180__deliverable_trio_attempt_and_snapshot.sql，后被替换为"
        " V180__share_change_events.sql：原 trio attempt/snapshot 相关对象由后续迁移补建；"
        "share_change_events 表已在真库生效。无需补迁移。",
    ),
    KnownChecksumDrift(
        "225",
        "2f4f4fb127d2a993636b3e343b53975ba8c2aadbc2ecf5ed0bc849456d8cdd5c",
        "63a26f3f5b73557dae3d933bd6480887b79a8d49562b32e6b153174429c8825a",
        "trim-generation-plan-followup-optimizations R2：开发中的 V217（2026-10-30 同步时与远端 V217 撞号，改为 V225，"
        "共享库登记的版本号与文件名同步改为 225、checksum 不动）于 2026-10-29 04:36 UTC 被登记进共享开发库"
        "（当时只有身份约束部分）。之后两处编辑：三个 CHECK 的存在性判断由「全库 pg_constraint 按名字查」改为"
        "「按 procedure_instances 本表查」（原写法在随机 schema 迁移测试里被 public 的同名约束骗过、跳过创建），"
        "头注释改为指向 V218。2026-10-29 逐对象核验 public：3 个 CHECK、部分唯一索引"
        " uq_procedure_instances_active_identity_norm、备份表 procedure_instance_identity_v217_backup 全部存在，"
        "效果与当前文件一致，无需补迁移；粗裁确认投影另立 V218。",
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
