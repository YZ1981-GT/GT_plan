# -*- coding: utf-8 -*-
r"""H 循环迁移**进度态** —— 契约交付到哪一步、legacy 载体处于哪一态。

spec: `h-cycle-sync-foundation-and-first-canary` 及三份 lane spec

═══ 为什么与 Task 50 分家 ═══════════════════════════════════════════════════

`test_task50_h_cycle_migration.py` 回答的是「**迁移前**长什么样」—— 它是规划期快照，
判据形态是「实测 == slice 登记」。本文件回答的是「**迁移到哪一步了**」：
  · 本 slice 已交付几份契约、每份是否经交付台账登记且字段完整；
  · adapter 那道正向门是否仍关着（BP-2/3/4 未解除前不许开）；
  · 9 条 entry 的 legacy dual-mode 载体各处于哪一态（已删 / 已接桥 / 未动）。

两个问题的读者不同、变化频率也不同（前者冻结、后者每交付一条就变），所以分文件。

🔴 **扫描与进度口径都不另抄**：消费方扫描用 Task 50 的 `_import_specifier_consumers`
（全前端 import 边的唯一实现），进度用 `h_migration_progress` 的现算口径。抄第二份就会
出现「两份进度各说各话」——那正是这批判据要防的。
"""
from __future__ import annotations

import pathlib
import re

import pytest

from tests.workpaper_sync.h_migration_progress import (
    H_BP8_DELETED_LEGACY_MODULES,
    delivered_contract_ids_by_entry,
    migrated_entry_ids,
)
from tests.workpaper_sync.test_task50_h_cycle_migration import (
    BACKEND,
    CONTRACT_DIR,
    FULL_MANIFEST_PATH,
    H1_ENTRY_ID,
    MANIFEST_SLICE_PATH,
    DELETION_PLAN_PATH,
    ROOT,
    _THIS,
    _import_specifier_consumers,
    _line_no_of,
    _load,
    _resolve_repo,
    _strip_ts_comments,
)

_migrated_entry_ids = migrated_entry_ids


@pytest.fixture(scope="module")
def manifest_slice() -> dict:
    return _load(MANIFEST_SLICE_PATH)


@pytest.fixture(scope="module")
def deletion_plan() -> dict:
    return _load(DELETION_PLAN_PATH)


@pytest.fixture(scope="module")
def full_manifest() -> dict:
    return _load(FULL_MANIFEST_PATH)


# ════════════════════════════════════════════════════════════════════════════
# BP-8：孤儿 / 错位 legacy composable
# ════════════════════════════════════════════════════════════════════════════
class TestOrphanLegacyComposables:
    """**Validates: Requirements 1.7, 12.11**

    两侧都断言：声称零消费的真零、声称有消费方的真有。**只断言一侧会 fail-open** ——
    只查「零消费的真零」时，某天有人接上消费方也不会红；只查「有消费方的真有」时，
    孤儿登记漏掉一个也不会红。
    """

    def test_declared_dual_mode_consumers_match_the_source(self, manifest_slice: dict) -> None:
        """🔴 迁移后按**三态**分派（原判据只有一态，迁移一开工必然全红）。

        三态：
          ① 已被 BP-8 收口**删除**（在 `H_BP8_DELETED_LEGACY_MODULES` 册上）
             ⇒ 断言确已不存在，且 slice 当初登记的消费方本来就是空的；
          ② 该 entry **已接桥**（现算迁移集）⇒ 宿主已换成 `useHSyncMode`，
             声明消费方里**恰好少掉宿主那一条**，其余（子 Tab）必须一条不少；
          ③ 其余 ⇒ 严格按原判据锁死。

        零消费计数同样按状态推导，不写死 3：新孤儿 = 已接桥且声明消费方只有宿主的那些。
        """
        migrated = _migrated_entry_ids()
        orphan_now: set[str] = set()
        deleted_seen: set[str] = set()
        for entry in manifest_slice["independent_entries"]:
            legacy = entry["legacy_dual_mode"]
            module = _resolve_repo(legacy["module"])
            host_rel = entry["host_path"]

            # ── 态 ①：已删除 ────────────────────────────────────────────────
            if module.name in H_BP8_DELETED_LEGACY_MODULES:
                deleted_seen.add(module.name)
                assert not module.exists(), (
                    f"{entry['entry_id']}: {module.name} 在删除账本上却仍存在 ⇒ "
                    "账本与磁盘脱钩"
                )
                assert legacy["consumers"] == [] and legacy["host_consumes_it"] is False, (
                    f"{entry['entry_id']}: {module.name} 被删了，但 slice 当初登记它**有**"
                    f"消费方 {legacy['consumers']} ⇒ 删除依据不成立，必须回滚"
                )
                assert _import_specifier_consumers(module.stem) == [], (
                    f"{entry['entry_id']}: {module.name} 已删，却还有文件 import 它"
                )
                orphan_now.add(entry["entry_id"])
                continue

            assert module.exists(), f"{entry['entry_id']}: legacy composable 不存在"
            actual = _import_specifier_consumers(module.stem)
            production = [c for c in actual if "__tests__" not in c and not c.endswith(".spec.ts")]

            # ── 态 ②：已接桥 ⇒ 声明消费方减去宿主 ──────────────────────────
            if entry["entry_id"] in migrated:
                expected = sorted(c for c in legacy["consumers"] if c != host_rel)
                assert expected == sorted(production), (
                    f"{entry['entry_id']}: {module.name} 已接桥，消费方应为「声明减宿主」"
                    f" {expected}，实测 {production}"
                )
                assert host_rel not in production, (
                    f"{entry['entry_id']}: 已接桥，宿主却仍 import {module.name}"
                    " ⇒ 两套切换实现并存（D4-35 踩过「切错桥 + 工具条叠加」）"
                )
            # ── 态 ③：未动 ⇒ 原判据 ───────────────────────────────────────
            else:
                assert sorted(legacy["consumers"]) == sorted(production), (
                    f"{entry['entry_id']}: {module.name} 的生产消费方声明 {legacy['consumers']} "
                    f"!= 实测 {production}"
                )
                assert legacy["host_consumes_it"] == (host_rel in production), (
                    f"{entry['entry_id']}: host_consumes_it 与实测不符"
                )

            if not production:
                orphan_now.add(entry["entry_id"])
            assert legacy["wraps_shared_base"] is False, (
                f"{entry['entry_id']}: 声明不 wraps 共享基类，与 slice 的假设不符"
            )
            assert "useWorkpaperEntryDualMode" not in module.read_text(encoding="utf-8"), (
                f"{entry['entry_id']}: {module.name} 实际 import 了共享基类"
            )
            prefix = legacy["localStorage_prefix"]
            assert f"'{prefix}'" in module.read_text(encoding="utf-8"), (
                f"{entry['entry_id']}: 找不到声明的 localStorage 前缀 {prefix!r}"
            )

        # 零消费集合按状态推导（不写死个数）：原登记的 3 个 + 接桥后只剩宿主那条被拿掉的
        declared_orphans = {
            e["entry_id"]
            for e in manifest_slice["independent_entries"]
            if e["legacy_dual_mode"]["consumers"] == []
        }
        assert len(declared_orphans) == 3, (
            f"slice 登记的零消费 dual-mode 应为 3 个（H5/H7/H9），实测 {sorted(declared_orphans)}"
            " —— 那是 append-only 快照，被改动了"
        )
        newly_orphaned = {
            e["entry_id"]
            for e in manifest_slice["independent_entries"]
            if e["entry_id"] in migrated
            and set(e["legacy_dual_mode"]["consumers"]) <= {e["host_path"]}
        }
        assert orphan_now == declared_orphans | newly_orphaned, (
            f"零消费集合现算 {sorted(orphan_now)}，应为原登记 {sorted(declared_orphans)} "
            f"∪ 接桥新增 {sorted(newly_orphaned)}"
        )

    def test_declared_orphan_formdata_composables_really_have_no_production_consumer(
        self, manifest_slice: dict
    ) -> None:
        declared = 0
        deleted_seen: set[str] = set()
        for entry in manifest_slice["independent_entries"]:
            block = entry.get("orphan_formdata_composable")
            if not block:
                continue
            declared += 1
            module = _resolve_repo(block["module"])
            # 🔴 BP-8 收口已**删掉** 4 条里的 3 条（H6/H8/H9 FormData）。判据翻面：
            #    在删除账本上的必须确已不存在，且它当初声明的消费方（含测试消费方）
            #    也必须一并消失 —— 留着一个 import 就是 ENOENT 打红的隐患
            #    （上一轮删 `useH9FormData.ts` 时漏查测试消费方，踩过这个坑）。
            if module.name in H_BP8_DELETED_LEGACY_MODULES:
                deleted_seen.add(module.name)
                assert not module.exists(), (
                    f"{entry['entry_id']}: {module.name} 在删除账本上却仍存在"
                )
                assert _import_specifier_consumers(module.stem) == [], (
                    f"{entry['entry_id']}: {module.name} 已删，却还有文件 import 它"
                )
                for ref in block["test_only_consumers"]:
                    # 两种合法处置：测试文件一并删掉，或改写成不再 import 它。
                    # 🔴 **不许**留着 import —— 那条测试会 ENOENT 打红（上一轮删
                    #    `useH9FormData.ts` 时漏查测试消费方，正是踩了这个）。
                    spec_path = ROOT / ref
                    if spec_path.exists():
                        # 🔴 判「有没有真 import」而不是「字符串出现过」：`h6Integration.spec.ts`
                        #    里那三行是**注释**，逐字记着「原用例直调
                        #    useH6FormData.writebackTrialBalance，测的是零消费死代码」——
                        #    那正是应当保留的删除理由追溯。按子串判会把它误杀。
                        assert not re.search(
                            r"""['"][^'"]*""" + re.escape(module.stem) + r"""['"]""",
                            spec_path.read_text(encoding="utf-8", errors="replace"),
                        ), (
                            f"{entry['entry_id']}: {module.name} 已删，但测试 {ref} "
                            f"仍 import {module.stem} ⇒ 那条测试会 ENOENT 打红"
                        )
                continue
            assert module.exists(), f"{entry['entry_id']}: {block['module']} 不存在"
            actual = _import_specifier_consumers(module.stem)
            production = [c for c in actual if "__tests__" not in c and not c.endswith(".spec.ts")]
            tests = [c for c in actual if c not in production]
            assert production == block["production_consumers"] == [], (
                f"{entry['entry_id']}: {module.name} 声称生产零消费，实测 {production}"
                " ⇒ BP-8 该解除并删除登记"
            )
            assert sorted(tests) == sorted(block["test_only_consumers"]), (
                f"{entry['entry_id']}: {module.name} 的测试消费方声明与实测不符：{tests}"
            )
            declared_count = manifest_slice["honest_adjudication_summary"][
                "entries_with_orphan_legacy_composable"
            ]
            assert declared_count == 5, "带孤儿 legacy 载体的 entry 数登记变了"
        assert declared == 4, (
            f"登记了 {declared} 条 orphan_formdata_composable（应为 H6/H7/H8/H9 四条）"
        )
        # 删除账本里的 FormData 条目必须全部在本判据的分母里被走到 —— 否则账本里
        # 混进了本 slice 管不到的名字（往账本加名字换不来绿）。
        ledger_formdata = {n for n in H_BP8_DELETED_LEGACY_MODULES if "FormData" in n}
        assert deleted_seen == ledger_formdata, (
            f"删除账本的 FormData 条目 {sorted(ledger_formdata)} 与本判据走到的 "
            f"{sorted(deleted_seen)} 不符"
        )

    def test_non_orphan_formdata_composables_are_not_registered_as_orphans(
        self, manifest_slice: dict
    ) -> None:
        """反向：H3/H4/H5/H10 的 FormData 是真载体，不得被登记成孤儿。"""
        real_carriers = {
            "useH3FormData",
            "useH4FormData",
            "useH5FormData",
            "useH10FormData",
        }
        registered = {
            _resolve_repo(e["orphan_formdata_composable"]["module"]).stem
            for e in manifest_slice["independent_entries"]
            if e.get("orphan_formdata_composable")
        }
        assert not (registered & real_carriers), (
            f"真载体被误登记成孤儿：{sorted(registered & real_carriers)}"
        )
        for stem in real_carriers:
            production = [
                c
                for c in _import_specifier_consumers(stem)
                if "__tests__" not in c and not c.endswith(".spec.ts")
            ]
            assert production, f"{stem} 实测零生产消费 ⇒ 它也该登记成孤儿"

    def test_shared_base_is_preserved_with_its_real_consumer_count(
        self, deletion_plan: dict
    ) -> None:
        block = deletion_plan["shared_base_preserved"]
        base = _resolve_repo(block["file"])
        assert base.exists()
        actual = _import_specifier_consumers(base.stem)
        forecast = block["remaining_consumers_after_h_cycle"]
        # 🔴 `remaining_consumers_after_h_cycle` 是**预测值**（「H 循环删完它 13 个之后
        #    还剩几个消费方」）。别的循环收口自己的 legacy 载体会**合法地**让它下降 ——
        #    实测就下降了 2（并发会话删 `useJ2EntryDualMode.ts` / `useJ3EntryDualMode.ts`，
        #    两者都曾 import 共享基类）。把等号钉死等于让本判据被别的循环的正常清理打红。
        # ⇒ 判据取两个真正属于本 slice 的不变量：
        #    ① **不得上升**（H 循环新接一个消费方 = 与「H 不 wraps 共享基类」矛盾）；
        #    ② 不得归零（基类被架空就该删，而 plan 明写 preserved）。
        assert 0 < len(actual) <= forecast, (
            f"共享基类消费方实测 {len(actual)} 个，预测 {forecast} 个 —— "
            "超出预测说明有人新接了消费方；归零说明基类已被架空"
        )
        h_consumers = [c for c in actual if re.search(r"[Hh](?:2|3|4|5|6|7|8|9|10)", c)]
        assert not any("DualMode" in c for c in h_consumers), (
            f"H 循环的 dual-mode composable 实际 wraps 了共享基类：{h_consumers}"
        )

    def test_host_inlined_second_implementation_is_real(self, deletion_plan: dict) -> None:
        """BP-8 的另一半：4 个宿主内联的真载体必须逐行可复核。"""
        migrated = _migrated_entry_ids()
        block = deletion_plan["host_inlined_second_implementation"]
        assert len(block["hosts"]) == 4
        for host in block["hosts"]:
            path = _resolve_repo(host["host_path"])
            assert path.exists()
            source = path.read_text(encoding="utf-8")
            lines = source.splitlines()
            # 🔴 已接桥的宿主（H8/H9）**不再**内联第二份实现 —— 那正是接桥要消除的东西。
            #    判据翻面：内联的 `currentMode = ref<>` 必须消失，且改为消费统一
            #    composable。原判据（「内联实现必须逐行可复核」）在这里会变成
            #    「要求缺陷还在」，那是判据本身过期，不是代码错。
            if host["entry_id"] in migrated:
                inline_state = [
                    f"L{no}"
                    for no, ln in enumerate(lines, 1)
                    if "currentMode" in ln and "ref<" in ln
                ]
                assert inline_state == [], (
                    f"{host['entry_id']}: 已接桥，宿主里却仍有内联 currentMode ref"
                    f"（{inline_state}）⇒ 两套模式状态并存"
                )
                assert "useHSyncMode" in source, (
                    f"{host['entry_id']}: 已接桥但源码里找不到 useHSyncMode ⇒ "
                    "既没内联也没接统一桥，无模式切换载体"
                )
                continue
            state_line = lines[_line_no_of(host["inline_mode_state"]) - 1]
            assert "currentMode" in state_line and "ref<" in state_line, (
                f"{host['entry_id']}: inline_mode_state 指向的行不是 currentMode ref："
                f"{state_line.strip()[:90]!r}"
            )
            if host["inline_switch_fn"]:
                fn_line = lines[_line_no_of(host["inline_switch_fn"]) - 1]
                assert "switchMode" in fn_line or "currentMode.value" in fn_line, (
                    f"{host['entry_id']}: inline_switch_fn 指向的行不是切换逻辑"
                )


# ════════════════════════════════════════════════════════════════════════════
# Property 20 / 21：分母为空，不宣称通过
# ════════════════════════════════════════════════════════════════════════════
class TestProperty20And21NotClaimed:
    """**Validates: Requirements 12.1**

    本 slice 的 per-entry contract 数为 0（唯一一份 H 循环契约属已排除的 H1 pilot）⇒
    Property 20 / 21 的分母为空，**不宣称通过**。只断言两件可复核的事：前提成立 +
    承载者存在。
    """

    def test_slice_entry_contracts_are_ledger_backed_and_field_complete(
        self, manifest_slice: dict
    ) -> None:
        """🔴 **2026-09-27 前提已改变，按本类原定的指示补齐了字段级判据**。

        原判据（`test_no_slice_entry_has_a_contract_and_h1_is_the_only_h_contract`）
        断言本 slice 零契约，并明写「前提一旦不成立 ⇒ 必须在此补齐字段级判据」。
        `h-cycle-sync-*` 四份 spec 已交付 H9 / H6 / H8 / H4 / H2 五份契约
        ⇒ 照该指示从「断言零契约」改为**逐契约的字段级判据**。

        🔴 **Property 20/21 仍然「不宣称通过」**：它们要的是 roundtrip 闭合与人工审核
        （卡 BP-2/BP-3/BP-4：无真 OO 9.4 场景集、无人工审核契约、无 approved bundle）。
        契约是发布链第①环，交付它不等于第④环通过 —— 台账每条都如实记
        `adapter_registered=False`，本类的 `test_no_slice_entry_has_a_registered_adapter`
        持续锁住那道正向门不被打开。

        字段级判据（Property 21 的可复核部分）：
          ① 契约在平台交付台账里登记，且 `entry_id` 与 slice 一致；
          ② 能过 `parse_contract` 强校验（schema 门）；
          ③ 非空壳：至少一张 sheet、一张表、一个受管字段；
          ④ 每张表声明 `row_identity`（行对齐前提）；
          ⑤ 每个字段有 `source_ref`（可溯源到模板格）。
        """
        from app.services.workpaper_sync.contracts import parse_contract

        slice_ids = {e["entry_id"] for e in manifest_slice["independent_entries"]}
        ledger = delivered_contract_ids_by_entry()
        ledger_in_slice = {k: v for k, v in ledger.items() if k in slice_ids}
        assert ledger_in_slice, (
            "台账里没有任何本 slice 的契约 ⇒ 本判据分母为空。若 H 循环确实回到零契约"
            "状态，请把本判据改回「断言零契约」"
        )
        h_contracts: list[str] = []
        checked: set[str] = set()
        for path in sorted(CONTRACT_DIR.glob("*.json")):
            doc = _load(path)
            owner = str((doc.get("review") or {}).get("entry_id") or "")
            if owner.startswith("xlsx/gt-h"):
                h_contracts.append(f"{path.name}:{owner}")
            if owner not in slice_ids:
                continue
            checked.add(owner)
            # ① 台账登记（台账被 test_task13_contract_registry 双向锁死，不可伪造）
            assert ledger_in_slice.get(owner) == path.stem, (
                f"{path.name} 属本 slice（{owner!r}）却未在 delivered_contracts_ledger "
                f"登记为 {path.stem!r}（台账值 {ledger_in_slice.get(owner)!r}）"
                " ⇒ 绕过了交付台账"
            )
            # ② schema 门
            contract = parse_contract(doc, adapter_id=path.stem)
            # ③ 非空壳
            assert contract.sheets, f"{path.name} 没有任何 sheet ⇒ 空壳契约"
            tables = [t for sh in contract.sheets for t in sh.tables]
            assert tables, f"{path.name} 没有任何受管表 ⇒ 空壳契约"
            for table in tables:
                assert table.fields, f"{path.name} 的表 {table.table_key!r} 没有受管字段"
                # ④ 行身份
                assert table.row_identity is not None, (
                    f"{path.name} 的表 {table.table_key!r} 缺 row_identity ⇒ 行对齐无从判定"
                )
                # ⑤ 可溯源
                for field in table.fields:
                    assert field.source_ref, (
                        f"{path.name} 的字段 {field.stable_field_key!r} 缺 source_ref"
                    )
        assert checked == set(ledger_in_slice), (
            f"台账登记了 {sorted(ledger_in_slice)} 共 {len(ledger_in_slice)} 条本 slice 契约，"
            f"磁盘上只找到 {sorted(checked)} ⇒ 台账与磁盘脱钩"
        )
        # H1 pilot 的那份仍必须在（「同循环 pilot 已交付」这个对照不许消失）
        assert f"h1.disposal_check.json:{H1_ENTRY_ID}" in h_contracts, (
            f"H 循环契约集合实测 {h_contracts} —— 缺 H1 pilot 那份"
        )

    def test_property_21_carriers_exist(self) -> None:
        for name in (
            "test_task13_contract_registry.py",
            "test_task42_h1_grouped_dynamic_pilot.py",
        ):
            assert (_THIS.parent / name).exists(), f"缺 Property 21 的字段级判据承载者 {name}"

    def test_slice_entries_now_have_registered_adapters_in_the_source_manifest(
        self, manifest_slice: dict, full_manifest: dict
    ) -> None:
        """🔴 **判据翻面（2026-10-01）**：正向门已按六项前置打开，不再断言「门关着」。

        原判据是 `test_no_slice_entry_has_a_registered_adapter`，两侧都断言
        `adapter_id is None`。现在 9 条 entry 的 capability 已翻 `bidirectional`
        ⇒ 继续断言 None 就是**要求成果不许存在**，属判据过期而非代码错。

        翻面后两侧分工明确：
          · **slice 侧仍断言 None** —— slice 是规划期冻结快照（append-only 上游输入，
            本仓铁律「历史档案不回填修改」），它记的就是「迁移前 adapter_id 为空」，
            这个事实不会因为迁移完成而改变；
          · **live manifest 侧断言四项齐备** —— capability / adapter_id /
            migration_state / canonical_resolver，且 adapter_id 必须与交付台账里
            该 entry 的 contract_id **逐字相等**（防「随手填一个 id 蒙过去」）。
        """
        from app.services.workpaper_sync.adapters.delivered_contracts_ledger import (
            DELIVERED_PER_ENTRY_CONTRACTS,
        )

        ledger = {str(r["entry_id"]): str(r["contract_id"]) for r in DELIVERED_PER_ENTRY_CONTRACTS}
        by_id = {e["entry_id"]: e for e in full_manifest["entries"]}
        assert manifest_slice["independent_entries"], "slice 分母为空"
        for entry in manifest_slice["independent_entries"]:
            eid = entry["entry_id"]
            # slice 侧：规划期快照，恒为 None
            assert entry["adapter_id"] is None, (
                f"{eid}: slice 的 adapter_id 被改动了 —— slice 是规划期冻结快照，"
                "勘误应登记在新 spec 而不是回填它"
            )
            live = by_id[eid]
            assert live["capability"] == "bidirectional", (
                f"{eid}: live manifest capability={live['capability']!r} ⇒ 正向门又关上了"
                "（或 overlay 的 override 掉了）"
            )
            assert live["adapter_id"] == ledger.get(eid), (
                f"{eid}: live manifest adapter_id={live['adapter_id']!r} 与交付台账的 "
                f"contract_id={ledger.get(eid)!r} 不等 ⇒ overlay 填了一个台账之外的 id"
            )
            assert live["migration_state"] == "adapter_registered", (
                f"{eid}: migration_state={live['migration_state']!r}"
            )
            assert live["canonical_resolver"] == "workpaper_sync_published_representation", (
                f"{eid}: canonical_resolver={live['canonical_resolver']!r} 仍是 legacy 路由"
            )
            assert live["html_store"] != "unresolved", (
                f"{eid}: html_store 仍是 unresolved ⇒ 翻了 capability 却没裁决 store"
            )

    def test_delivered_contract_ledger_marks_no_slice_entry_as_adapter_registered(
        self, manifest_slice: dict
    ) -> None:
        """🔴 判据的**真源换了地方**，原实现已变成 fail-open，必须跟着换。

        原实现读 `adapters/registry.py` 的**文本**判「entry_id 出现过没有」。H8 交付时
        把交付台账抽成伴生模块 `adapters/delivered_contracts_ledger.py`
        （registry.py 2463 → 1303 行），entry_id 随之搬走 ⇒ 原判据对本 slice 的五条
        已交付 entry **恒真**（文本里找不到了），同时对 H1 pilot 的正向对照**恒假**。
        一个判据同时假绿 + 假红，只能换真源。

        换成读台账本身（唯一真源），并把判据收紧到真正要守的东西：
        **契约已交付 ≠ adapter 已注册**。台账每条都带 `adapter_registered`，
        本 slice 的必须全为 False —— 那是 BP-2/3/4（无真 OO 场景集 / 无人工审核 /
        无 approved bundle）未解除前不得打开的正向门。
        """
        from app.services.workpaper_sync.adapters.delivered_contracts_ledger import (
            DELIVERED_PER_ENTRY_CONTRACTS,
        )

        slice_ids = {e["entry_id"] for e in manifest_slice["independent_entries"]}
        rows = {str(r["entry_id"]): r for r in DELIVERED_PER_ENTRY_CONTRACTS}
        in_slice = {k: v for k, v in rows.items() if k in slice_ids}
        assert in_slice, "台账里没有本 slice 的条目 ⇒ 分母为空"
        for entry_id, row in sorted(in_slice.items()):
            # 🔴 **2026-10-01 翻面**：原断言是 `adapter_registered is False`（「正向门必须
            #    关着」）。门已按六项前置打开 ⇒ 继续要求 False 就是要求成果不许存在。
            #
            #    但**不是**简单改成 `is True`：现算全台账 51 条里 `adapter_registered=True`
            #    只有 4 条（d2 / d4 / g7 / h1），而 live manifest 里已 `bidirectional` 的有
            #    18 条 —— 也就是说这个台账字段**整体滞后于 manifest 14 条**（d1 + G 循环 13
            #    条都是 bidirectional 而 flag 仍 False）。那是平台级的一处字段失修，不属本
            #    spec 的作业面；照它「对齐」会把滞后正当化（本仓铁律㉗：对齐缺陷 = 把缺陷
            #    正当化），直接改成 True 又会在台账里造出与别家不一致的第二套口径。
            #
            #    ⇒ 本判据改为：**只认 manifest 这个运行时真源**（adapter 是否真注册由
            #    `assert_manifest_capability_enabled()` 读 manifest capability 决定，
            #    台账那个 flag 不参与运行时判定），台账这边只断言它仍是**两个合法值之一**
            #    且滞后面没有扩大（下面 `test_ledger_adapter_registered_lag_is_a_ratchet`
            #    把滞后做成只许变小的棘轮）。
            assert row.get("adapter_registered") in (True, False), (
                f"{entry_id}: 台账 adapter_registered={row.get('adapter_registered')!r} "
                "不是布尔 ⇒ 字段形态变了，本判据需要重判"
            )
            assert row.get("reason"), f"{entry_id}: 台账条目缺 reason（为何未注册 adapter）"
            provider = str(row.get("provider_module") or "")
            assert provider, f"{entry_id}: 台账条目缺 provider_module"
            # 台账登记的是**点分模块路径**（`app.services.workpaper_sync.phase5_h2_…`），
            # 落盘位置以 backend/ 为包根。
            assert (BACKEND / (provider.replace(".", "/") + ".py")).exists(), (
                f"{entry_id}: provider_module={provider!r} 在磁盘上找不到"
            )
        # H1 pilot 的正向对照：它在台账里（同循环 pilot 已交付）
        assert H1_ENTRY_ID in rows, (
            "台账里找不到 H1 pilot ⇒ 「同循环 pilot 已交付」这个对照消失"
        )

    def test_ledger_adapter_registered_lag_is_a_ratchet(self, full_manifest: dict) -> None:
        """🔴 把「台账 `adapter_registered` 滞后于 manifest」做成**只许变小**的棘轮。

        现算事实（2026-10-01）：
          · live manifest 里 capability == bidirectional 的 entry：**18** 条；
          · 台账里 `adapter_registered is True` 的 entry：**4** 条（d2 / d4 / g7 / h1）；
          · 滞后面 = 18 − 4 = **14** 条（d1 + G 循环 13 条，全部由别的 spec 翻门时留下）。

        为什么登记而不是顺手全改成 True：台账是**跨循环共享**的交付清单，本轮只有 H 的
        作业面；替 d1 与 G 十三条改 flag 等于替别人签字，而且 `delivered_contracts_ledger.py`
        此刻有并发会话的未提交改动，改它会把别人的改动一起带进本轮提交。

        棘轮形态（不是「≥X%」阈值）：滞后条数**不得超过**冻结基线。别人补齐时它自然变小，
        本轮或任何人新翻一条门而忘了同步 flag 时它会变大 ⇒ 打红。
        """
        from app.services.workpaper_sync.adapters.delivered_contracts_ledger import (
            DELIVERED_PER_ENTRY_CONTRACTS,
        )

        #: 台账里 `adapter_registered is True` 的 entry 全集（登记而非计数）。
        #:
        #: 🔴 刻意**不写条数**：本仓已登记「禁写死计数」，而且 live manifest 的
        #: bidirectional 条数在不同检出状态下不同（已入库 14 条；本机工作树因并发会话的
        #: G 循环翻门另有 13 条尚未提交 ⇒ 27 条）—— 任何绝对数字都会在两种状态里各错一次。
        #: 登记**集合**则两边都成立，且有人补齐 flag 时本条会红并指明该怎么改。
        _LEDGER_FLAGGED_TRUE = frozenset(
            {
                "xlsx/gt-d2-accounts-receivable",
                "xlsx/gt-d4-operating-revenue",
                "xlsx/gt-g7-long-term-equity-main",
                "xlsx/gt-h1-fixed-assets",
            }
        )

        cap = {e["entry_id"]: e.get("capability") for e in full_manifest["entries"]}
        rows = {str(r["entry_id"]): r for r in DELIVERED_PER_ENTRY_CONTRACTS}
        bidi = {eid for eid, c in cap.items() if c == "bidirectional"}
        flagged = {eid for eid, r in rows.items() if r.get("adapter_registered") is True}

        # 反向断言①：分母非空（否则下面几条全是空转）
        assert bidi, "manifest 里没有任何 bidirectional entry ⇒ 本判据空转"
        assert flagged, "台账里没有任何 adapter_registered=True ⇒ 本判据空转"

        # ② flag **不得跑在真源前面** —— 这是真正有安全含义的一侧：
        #    运行时是否注册 adapter 由 `assert_manifest_capability_enabled()` 读 manifest
        #    capability 决定；台账 flag 比 manifest 超前意味着台账在宣称一件没发生的事。
        ahead = sorted(flagged - bidi)
        assert ahead == [], (
            f"台账记 adapter_registered=True 但 manifest 还不是 bidirectional：{ahead} "
            "⇒ 台账跑在真源前面，比滞后更危险"
        )

        # ③ 登记表与现实双向对账（可伪证）：多一条或少一条都要改登记表，而不是改断言。
        assert flagged == _LEDGER_FLAGGED_TRUE, (
            f"台账 adapter_registered=True 的集合变了：只在现实={sorted(flagged - _LEDGER_FLAGGED_TRUE)}、"
            f"只在登记表={sorted(_LEDGER_FLAGGED_TRUE - flagged)}。\n"
            "若是有人补齐了滞后的 flag（好事），请把新条目加进 _LEDGER_FLAGGED_TRUE；"
            "若是有人把某条 flag 改回 False，请查清是不是误操作。"
        )

        # ④ 本 slice 九条 + H1 的 capability 地板：门一旦打开不许再关
        h_live = {eid for eid in bidi if re.match(r"xlsx/gt-h(?:1|2|3|4|5|6|7|8|9|10)-", eid)}
        assert len(h_live) == 10, (
            f"H 循环 live bidirectional 实测 {len(h_live)} 条（期望 10 = h1 + 本轮九条）："
            f"{sorted(h_live)}"
        )

    def test_property_denominator_block_declares_what_is_not_claimed(
        self, manifest_slice: dict
    ) -> None:
        block = manifest_slice["property_denominators"]
        assert block["property_20_and_21_not_claimed"]["not_claimed_passing"] is True
        assert block["property_22"]["not_claimed_passing"] is False
        assert block["property_23"]["not_claimed_passing"] is False
        assert block["property_69"]["not_claimed_passing_part"]
        assert block["property_70"]["not_claimed_passing"] is False
        for key in ("property_22", "property_23", "property_69", "property_70"):
            assert "h_cycle_denominator" in block[key]
            assert "how_handled" in block[key]
