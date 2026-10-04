# -*- coding: utf-8 -*-
"""H 循环迁移进度的**现算**口径 —— 供规划期冻结快照判据「翻面」使用。

spec: `h-cycle-sync-foundation-and-first-canary` 等四份 H spec

═══ 为什么单独一个模块 ═══════════════════════════════════════════════════════

`test_task50_h_cycle_migration.py` 是**规划期**产物：它拍下「H 循环尚未迁移」那一刻的
快照，slice 里所有 `path#Lnn`、消费方清单、缺陷登记都是那一刻的事实。迁移一开工，
它的前提逐条被推翻 —— 而推翻它的**不是缺陷**，是进展。

判据要跟着分派，就需要一份「哪几条已迁移 / 哪几个 legacy 载体已删」的真源。这份真源
必须满足两件事：
  ① **现算**，不是手写清单（手写会与实际进展漂移，两份进度各说各话）；
  ② 放在 `h_cycle_facts.py` 与 Task 50 之外 —— 前者已到行数上限，后者是被守的对象，
    把进度口径塞进被守对象里等于让它自己给自己发豁免。
"""
from __future__ import annotations

import functools
import re
from pathlib import Path
from typing import Callable, Final, Mapping

from tests.workpaper_sync.h_cycle_facts import H_ENTRY_IDS, wired_entry_codes

_REPO: Final[Path] = Path(__file__).resolve().parents[3]

#: BP-8 收口时**删除**的 legacy 载体（删除前它们已零生产消费、零测试消费）。
#:
#: 🔴 这是一份**删除账本**，不是豁免名单：判据用它做双向划分 —— 在册的必须确已不存在，
#:    不在册的必须仍存在。想靠往这里加名字把红改绿，就必须真的把文件删掉，而删文件会被
#:    消费方现算判据拦住（还有消费方就删不掉）。
#:
#: 删除依据见 commit `91933bd68`（删前逐个查过生产边与测试边都为 0）。
H_BP8_DELETED_LEGACY_MODULES: Final[Mapping[str, str]] = {
    "useH5DualMode.ts": "宿主 GtH5OilGasAssets 内联了第二份 currentMode/switchMode 实现，本文件零消费",
    "useH7DualMode.ts": "宿主 GtH7BiologicalAssets 内联了第二份实现，本文件零消费",
    "useH6FormData.ts": "H6 宿主自持久化，本载体零生产消费（其测试直调用例同批改写）",
    "useH8FormData.ts": "H8 逐 Tab 自持久化，本载体零生产消费",
    "useH9FormData.ts": "H9 宿主内联持久化，本载体零生产消费",
}


@functools.lru_cache(maxsize=1)
def delivered_contract_ids_by_entry() -> Mapping[str, str]:
    """现算**平台交付台账**里属 H 循环九条 entry 的 `{entry_id: contract_id}`。

    台账是唯一可信来源：`test_task13_contract_registry` 对它双向锁死（每条须有真实
    `provider_module`、磁盘契约文件存在、entry 在 source-backed manifest 里），
    故这份映射不可伪造 —— 想让某条 entry 出现在这里，必须真交付一份契约。
    """
    from app.services.workpaper_sync.adapters.delivered_contracts_ledger import (
        DELIVERED_PER_ENTRY_CONTRACTS,
    )

    mine = set(H_ENTRY_IDS)
    return {
        str(row["entry_id"]): str(row["contract_id"])
        for row in DELIVERED_PER_ENTRY_CONTRACTS
        if str(row.get("entry_id", "")) in mine
    }


@functools.lru_cache(maxsize=1)
def migrated_entry_ids() -> frozenset[str]:
    """现算**已接统一双向桥**的 entry_id 集合（真源在前端 `H_OO_WIRED_ROWS_CODES`）。

    不写死名单：`wired_entry_codes()` 从前端受管清单现读短码（`H9` / `H6` / …），
    这里映射回 entry_id。新接一条 entry 自动进入，判据侧无需改动。
    """
    codes = wired_entry_codes()
    out = {
        eid
        for eid in H_ENTRY_IDS
        # entry_id 形如 `xlsx/gt-h9-lease-liabilities` ⇒ 取 `h9` 归一成 `H9`
        if (m := re.match(r"xlsx/gt-(h\d+)-", eid)) and m.group(1).upper() in codes
    }
    assert out, "现算迁移集为空 —— 真源 H_OO_WIRED_ROWS_CODES 解析失败，判据会全面假红"
    return frozenset(out)


def relocate_lines(
    *,
    entry_id: str,
    ref: str,
    predicate: Callable[[str], bool],
    what: str,
    migrated: frozenset[str],
) -> list[int]:
    """把冻结的 `path#Lnn` 解析成**当前**行号集合。

    ═══ 分派规则 ═══

    接桥改动了 H2/H6/H8/H9 四个宿主（插 import、插 `flushPendingSaves`、换
    `useHSyncMode`），其下方所有行号整体位移。**行号位移不是语义漂移**，而 slice 是
    append-only 审计轨迹、不回填（同 K 循环 `test_task53` 的处置）。所以：

      · 冻结行号**仍然命中** ⇒ 返回 `[frozen]`，等价于原判据，严格锁死
        （未被改动的 entry 不许悄悄漂）；
      · 冻结行号**不再命中** ⇒ 该 entry 必须真的在现算迁移集里（否则说明是无关改动把
        站点搞丢了，照旧打红），然后按内容再定位，返回**全部**命中行。

    🔴 位移分支返回全集而不是「挑第一处」：H6 宿主实测有 2 处 `http.put(`
    （防抖到点 + flush），挑第一处等于放过第二处。调用方对**每一处**施加判据
    ⇒ 比原判据更严（载体里多出一个打别的端点的写入会被抓住）。
    """
    path = _REPO / ref.split("#L")[0]
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    match = re.search(r"#L(\d+)", ref)
    assert match, f"引用 {ref!r} 里没有 #Lxx 行号"
    frozen = int(match.group(1))
    if 0 < frozen <= len(lines) and predicate(lines[frozen - 1]):
        return [frozen]
    actual = lines[frozen - 1].strip()[:90] if 0 < frozen <= len(lines) else "<行号越界>"
    assert entry_id in migrated, (
        f"{entry_id}: {ref} 指向的行不再是{what}（实际 {actual!r}），"
        "且该 entry **不在现算迁移集里** ⇒ 不是接桥造成的行号位移，是站点真的丢了"
    )
    found = [no for no, line in enumerate(lines, 1) if predicate(line)]
    assert found, f"{entry_id}: 按内容在 {ref.split('#L')[0]} 里再定位{what}，一处也没找到"
    return found
