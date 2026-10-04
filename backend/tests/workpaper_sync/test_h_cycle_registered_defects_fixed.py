# -*- coding: utf-8 -*-
r"""H 循环规划期登记的缺陷 —— **已修复，且必须保持修复**。

spec: `h-cycle-sync-foundation-and-first-canary` / `h4-h8-sub-entry-lanes-and-seed-identity-defects`
      / `h2-h6-h10-pilot-cross-reference-lanes`

═══ 为什么这些判据从 Task 50 搬到这里 ═══════════════════════════════════════

`test_task50_h_cycle_migration.py` 是**规划期**快照：它记录「H 循环迁移前长什么样」，
其中包括 slice 登记的 10 条阻断项（BP-1~BP-10）。它对缺陷的判据是
「**实测命中数等于登记条数**」—— 也就是说，缺陷**还在**才绿。

本轮迁移把其中三条真修了：

  · **BP-5** H8 四表种子写进零消费键 —— 写入目标 `H8-2-detail-prefill` → `H8-2-rows`
    （真实主键）；
  · **BP-6** family_a 三处主表种子的行身份取数组下标 —— 改用
    `hSeedRowIdentity.buildHSeedRowIds()`，身份来自**科目编码**（稳定 + 可重现），
    缺编码时回落随机后缀，**绝不**回落下标；
  · **BP-7** H8 披露载荷的列键用 label —— `key: c.label` → `key: c.key`。

于是那几条判据必须**翻面**：从「缺陷还在才绿」变成「缺陷没了才绿，回退即红」。翻面后
它们回答的问题也变了 —— 不再是「迁移前什么样」，而是「这几条缺陷现在还在吗」。
问后者的人不该被迫读 2800 行的规划期快照，所以单独成文。

🔴 **扫描口径共用 Task 50 的实现，不另抄一份**。Task 50 的 `_label_key_hits` /
`_positional_identity_hits` / `_h_cycle_files` 等是「全 H 循环穷举」的唯一实现；抄第二份
就会出现「两个扫描器各自漂移」——那正是这批判据要防的东西。跨测试模块 import 下划线
助手不算优雅，但比两份口径安全。
"""
from __future__ import annotations

import pathlib
import re

import pytest

from tests.workpaper_sync.test_task50_h_cycle_migration import (
    COMPOSABLES,
    H8_SYNC_PAYLOAD,
    ROOT,
    _h_cycle_files,
    _label_key_hits,
    _load,
    _positional_identity_hits,
    _resolve_repo,
    _strip_ts_comments,
    _value_expr_after_key,
    _POSITIONAL_IDENTITY_TOKEN,
    MANIFEST_SLICE_PATH,
    FRONTEND,
    BACKEND,
)


@pytest.fixture(scope="module")
def manifest_slice() -> dict:
    return _load(MANIFEST_SLICE_PATH)


@pytest.fixture(scope="module")
def h_files() -> list[pathlib.Path]:
    return _h_cycle_files()


class TestRegisteredDefectsStayFixed:
    """**Validates: Requirements 6.4, 6.5, 12.11, 14.1**

    三条阻断项（BP-5 / BP-6-familyA / BP-7）各自：
      ① 现算必须为**零**（回退即红）；
      ② slice 侧的登记数**保持原值**（那是修复前的历史事实，append-only 不回填 ——
        有人把登记改成 0 想让判据自洽也会打红）；
      ③ 修复手法真在源码里（换个写法把缺陷改回来同样被抓）。
    """

    def test_label_as_key_hits_are_exactly_the_declared_deviations(
        self, manifest_slice: dict, h_files: list[pathlib.Path]
    ) -> None:
        """🔴 BP-7 **已修复**（2026-09-27），判据随之翻面为「保持为无」。

        原判据要求实测命中数**等于** slice 声明的各 1 条，并注明「少一处 = 已修好但
        登记未删，两个方向都打红」。`h-cycle-sync-*` 的 H8 交付把
        `h8DisclosureSyncPayload.ts` 的列键从 `key: c.label` 改成 `key: c.key`
        （取值端本来就按 `c.key`，所以改的是键的来源不是取值口径）⇒ 两种形态现算均为 0。

        按原判据的指示处置：**不回填 slice**（append-only 审计轨迹，那两个 1 是修复前的
        历史事实），改为在此断言「已修好且保持为零」，并逐条核对修复真在源码里。
        这比原判据严 —— 原判据允许存在 1 处，现在一处都不许有。
        """
        block = manifest_slice["dynamic_column_identity"]
        declared = block["hardcoded_scan_result"]["patterns"]
        hits = _label_key_hits(h_files)
        # ① 现算必须为零（新引入任何一处 label-as-key 立刻打红）
        assert hits["column_key_is_label"] == [], (
            f"column_key_is_label 出现新命中：{hits['column_key_is_label']} —— "
            "BP-7 已修复，不得回退"
        )
        assert hits["row_cell_key_is_label"] == [], (
            f"row_cell_key_is_label 出现新命中：{hits['row_cell_key_is_label']}"
        )
        # ② slice 侧的历史事实保持不变（有人偷偷把 1 改成 0 想让判据自洽 ⇒ 打红）
        assert declared["column_key_is_label"] == 1, (
            "slice 的 column_key_is_label 登记被改动 —— 那是修复前快照，append-only 不回填"
        )
        assert declared["row_cell_key_is_label"] == 1
        deviations = block["deviations"]
        assert len(deviations) == 1, "声明的背离条数变了，判据需重写"
        assert deviations[0]["entry_id"] == "xlsx/gt-h8-right-of-use-assets"
        assert deviations[0]["registered_as"] == "BP-7"
        # ③ 修复真在源码里：列键取 `c.key`，且仍**同时**带 label（label 只作展示）
        payload = _strip_ts_comments(H8_SYNC_PAYLOAD.read_text(encoding="utf-8"))
        assert re.search(r"key:\s*c\.key\b", payload), (
            "h8DisclosureSyncPayload.ts 的列键不再是 `c.key` ⇒ BP-7 的修复被改掉了"
        )
        assert re.search(r"label:\s*c\.label\b", payload), (
            "列定义丢了 label 字段 ⇒ key/label 解耦的另一半（展示名）没了"
        )

    def test_positional_identity_inventory_is_exhaustive_and_partitioned(
        self, manifest_slice: dict, h_files: list[pathlib.Path]
    ) -> None:
        """🔴 BP-6 的 **family_a（3 条真缺陷）已修复**（2026-09-27），判据随之分段。

        修复手法：三处主表种子原本是 `rowId: \\`seed-${idx}\\`` 一类**位置派生**身份，
        现在统一改成 `rowId: seedRowIds[idx]`，其中 `seedRowIds` 由
        `composables/hSeedRowIdentity.ts::buildHSeedRowIds` 一次性生成**随机** id 数组
        —— 下标只用来「取第几个随机 id」，身份本身不再由位置决定，删中间行也不会让
        后续行改身份。

        判据分段（**不回填 slice**，那 17 条与三族划分是修复前的历史事实）：
          · family_a ⇒ 现算必须为**空**（修复后不得回退）；
          · family_b / family_c ⇒ 逐条仍须与实测等值（它们**未**修，仍是真登记）；
          · 总数 ⇒ 现算 == 声明总数 − family_a 数。
        """
        inventory = manifest_slice["dynamic_row_identity"]["positional_identity_inventory"]
        hits = _positional_identity_hits(h_files)
        family_a = {h["source_ref"] for h in inventory["family_a_true_defect_primary_table_seed"]["hits"]}
        family_b = set(inventory["family_b_index_only_as_prefix_into_a_random_generator"]["hits"])
        family_c = set(
            inventory["family_c_index_as_fallback_on_non_primary_derived_tables"]["hits"]
        )
        assert len(family_a) == inventory["family_a_true_defect_primary_table_seed"]["count"]
        assert len(family_b) == inventory[
            "family_b_index_only_as_prefix_into_a_random_generator"
        ]["count"]
        assert len(family_c) == inventory[
            "family_c_index_as_fallback_on_non_primary_derived_tables"
        ]["count"]
        assert not (family_a & family_b) and not (family_a & family_c) and not (family_b & family_c), (
            "三族有重叠 ⇒ 分类不是划分"
        )
        actual = {f"{rel}#L{no}" for rel, no, _k, _e in hits}
        # ① family_a 已修 ⇒ 实测集合里**不得**再出现主表种子的位置化身份。
        #    判据不按「原 3 个行号」比对（行号会位移），而是按「主表种子文件 +
        #    rowId 表达式仍含位置 token」现扫：文件整体换位置也逃不掉。
        family_a_files = {ref.split("#L")[0] for ref in family_a}
        regressed = sorted(ref for ref in actual if ref.split("#L")[0] in family_a_files)
        assert regressed == [], (
            f"BP-6 的 family_a 已修复，但这些主表种子文件里又出现位置化身份：{regressed}"
        )
        # ② family_b / family_c 未修 ⇒ 仍须逐条等值。
        assert family_b | family_c == actual, (
            "位置化清单（family_b ∪ family_c）与实测集合不等：\n"
            f"  仅在声明里：{sorted((family_b | family_c) - actual)}\n"
            f"  仅在实测里：{sorted(actual - (family_b | family_c))}"
        )
        # ③ 总数关系自洽（slice 的 total_hits 是修复前的 17）。
        assert len(hits) == inventory["total_hits"] - len(family_a), (
            f"位置化命中实测 {len(hits)} 条，应为声明总数 {inventory['total_hits']} "
            f"减去已修的 family_a {len(family_a)} 条"
        )
        # ④ 修复真在源码里：三处主表种子都改用随机 id 数组。
        for rel in sorted(family_a_files):
            body = (ROOT / rel).read_text(encoding="utf-8", errors="replace")
            assert "seedRowIds" in body, (
                f"{rel}: 找不到 seedRowIds ⇒ BP-6 的修复手法被改掉了"
            )
        seed_module = COMPOSABLES / "hSeedRowIdentity.ts"
        assert seed_module.exists(), "缺 hSeedRowIdentity.ts ⇒ BP-6 的修复实现没了"
        seed_src = _strip_ts_comments(seed_module.read_text(encoding="utf-8"))
        assert re.search(r"export function buildHSeedRowIds", seed_src), (
            "hSeedRowIdentity.ts 里找不到 buildHSeedRowIds"
        )
        # 🔴 身份来源必须是「稳定业务标识优先 + 随机保底」，**不是**随机而已：
        #    修复裁决（HC-7 族 A）选的是科目编码，因为它还满足「可重现」——
        #    用户清空重种子时 OO 侧既有行不会全部变成新行。随机后缀只是缺编码时的保底。
        assert re.search(r"normalizeAccountCode", seed_src), (
            "找不到科目编码归一 ⇒ 身份不再基于稳定业务标识，BP-6 的裁决被改掉了"
        )
        assert re.search(r"Math\.random|randomUUID", seed_src), (
            "缺随机保底 ⇒ 源数据无科目编码时会退回不稳定形态"
        )
        # 签名级防复发：生成函数**不得**接受下标参数（接受了就可能再被下标喂进去）。
        sig = re.search(r"export function buildHSeedRowId\s*\(([^)]*)\)", seed_src)
        assert sig, "找不到 buildHSeedRowId 的签名"
        assert not re.search(r"\b(idx|index|i)\s*[:,)]", sig.group(1)), (
            f"buildHSeedRowId 的签名又出现下标参数：{sig.group(1)!r} ⇒ BP-6 可复发"
        )

    def test_family_a_hits_write_to_the_declared_key(self, manifest_slice: dict) -> None:
        """构造点与写入点可能在不同文件（H4 就是），故按 writes_to_key_site 分别核。

        🔴 family_a 已修（见上一条判据）⇒ 原来那句「声明为位置化，实测其 rowId
        表达式**是**位置化」必然打红。判据翻面为三件仍然可复核、且修复后更该成立的事：
          ① 每条 hit 的 entry_id 仍属本 slice（登记不许指向别的循环）；
          ② 写入点文件里仍**有**那个主表键（修复不该顺手改键名 —— 改了就是数据错位）；
          ③ 构造点行现算**不再**是位置化（回退即打红），且改用了随机 id 数组。
        """
        inventory = manifest_slice["dynamic_row_identity"]["positional_identity_inventory"]
        entry_ids = {e["entry_id"] for e in manifest_slice["independent_entries"]}
        hits = inventory["family_a_true_defect_primary_table_seed"]["hits"]
        assert hits, "family_a 登记为空 ⇒ 本判据分母恒空"
        for hit in hits:
            assert hit["entry_id"] in entry_ids, f"{hit['source_ref']}: entry_id 不属本 slice"
            source_path = _resolve_repo(hit["source_ref"])
            body = source_path.read_text(encoding="utf-8")
            # ③ 现算：该文件里任何 `rowId:` 赋值都不得再是位置派生
            for no, line in enumerate(body.splitlines(), 1):
                expr = _value_expr_after_key(line, "rowId")
                if expr is None:
                    continue
                assert not _POSITIONAL_IDENTITY_TOKEN.search(expr), (
                    f"{hit['source_ref'].split('#L')[0]}#L{no}: BP-6 已修复，"
                    f"这里又出现位置化 rowId：{expr.strip()[:90]!r}"
                )
            assert "seedRowIds" in body, (
                f"{hit['source_ref'].split('#L')[0]}: 找不到 seedRowIds ⇒ 修复手法被改掉"
            )
            # ② 写入点的键：**BP-5 同批修复**把 H8 的写入目标从孤儿键
            #    `H8-2-detail-prefill` 改成真实主键 `H8-2-rows`，所以这里不能再要求
            #    「声明的 writes_to_key 仍在源码里」—— 那正是要被改掉的东西。
            #    判据翻面：写入点必须写**该 entry 的真实主表键**；若声明的 key 与真实
            #    主键不同（即那条孤儿键），则它不得再出现在**代码**里（注释不算）。
            key = hit["writes_to_key"]
            entry = next(e for e in manifest_slice["independent_entries"] if e["entry_id"] == hit["entry_id"])
            real_key = entry["html_counterpart"]["primary_table"]["item_id"]
            site_path = _resolve_repo(hit["writes_to_key_site"])
            site_source = site_path.read_text(encoding="utf-8")
            assert f"'{real_key}'" in site_source or f'"{real_key}"' in site_source, (
                f"{hit['source_ref']}: 写入点 {hit['writes_to_key_site']} 里找不到真实主表键 "
                f"{real_key!r}"
            )
            if key != real_key:
                code_only = _strip_ts_comments(site_source)
                assert key not in code_only, (
                    f"{hit['source_ref']}: BP-5 已把写入目标从孤儿键 {key!r} 改为 "
                    f"{real_key!r}，但剥注释后代码里仍出现 {key!r} ⇒ 修复不彻底"
                )
        assert inventory["family_a_true_defect_primary_table_seed"]["registered_as"] == "BP-6"

    def test_h8_seed_key_has_exactly_one_occurrence_in_the_repo(
        self, manifest_slice: dict
    ) -> None:
        """🔴 BP-5 **已修复**（2026-09-27）：H8 四表种子的写入目标从孤儿键
        `H8-2-detail-prefill` 改成真实主键 `H8-2-rows`。

        原判据要求孤儿键全仓恰 1 处命中、且那 1 处是声明的**写入点**。修复后：
        孤儿键在代码里 0 处，只在修复注记的**注释**里留 1 处（供人追溯）。
        判据翻面 —— 比原判据严：原判据容忍 1 处写入，现在**一处写入都不许有**。

        注释豁免是有边界的：只允许出现在注释里，且必须能在同文件找到真实主键的写入。
        """
        entry = next(
            e
            for e in manifest_slice["independent_entries"]
            if e["entry_id"] == "xlsx/gt-h8-right-of-use-assets"
        )
        block = entry["html_counterpart"]["orphan_seed_key"]
        key = block["key"]
        real_key = entry["html_counterpart"]["primary_table"]["item_id"]
        assert key != real_key, "BP-5 的前提（种子键 != 主表键）不成立"

        code_hits: list[str] = []
        comment_hits: list[str] = []
        for base, exts in ((FRONTEND, (".ts", ".vue")), (BACKEND / "app", (".py",))):
            for path in base.rglob("*"):
                if not (path.is_file() and path.suffix in exts):
                    continue
                text = path.read_text(encoding="utf-8", errors="replace")
                if key not in text:
                    continue
                # 🔴 逐行分「代码命中」与「注释命中」：`_strip_ts_comments` 只吃
                #    ts/vue，.py 用 `#` 判。剥完还在的就是真代码。
                stripped = (
                    _strip_ts_comments(text)
                    if path.suffix in (".ts", ".vue")
                    else "\n".join(
                        ln for ln in text.splitlines() if not ln.lstrip().startswith("#")
                    )
                )
                stripped_lines = set(stripped.splitlines())
                for no, line in enumerate(text.splitlines(), 1):
                    if key not in line:
                        continue
                    ref = f"{path.relative_to(ROOT).as_posix()}#L{no}"
                    (code_hits if line in stripped_lines else comment_hits).append(ref)

        assert code_hits == [], (
            f"BP-5 已修复，但孤儿键 {key!r} 仍出现在**代码**里：{code_hits}"
        )
        assert len(comment_hits) == 1, (
            f"孤儿键 {key!r} 的注释命中应恰 1 处（BP-5 修复注记），实测 {comment_hits}"
        )
        # 注释命中必须与 slice 声明的写入点**同文件**（行号会位移，不逐字比）
        assert comment_hits[0].split("#L")[0] == block["write_site"].split("#L")[0], (
            f"修复注记所在文件 {comment_hits[0]} 与声明的写入点 {block['write_site']} 不同文件"
        )
        assert block["read_sites"] == []
        # 真实主键的写入必须在同一文件里（证明目标是「改了」而不是「删了」）
        fixed_file = ROOT / comment_hits[0].split("#L")[0]
        fixed_src = fixed_file.read_text(encoding="utf-8")
        assert f"'{real_key}'" in fixed_src or f'"{real_key}"' in fixed_src, (
            f"{fixed_file.name}: 找不到真实主键 {real_key!r} 的写入 ⇒ 种子路径被删而不是改"
        )

