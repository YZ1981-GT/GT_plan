# -*- coding: utf-8 -*-
"""H lane 2 判据：BP-5 / BP-6 / BP-7 三条专属缺陷的修复断言（HS-P4~P8）。

spec: `h4-h8-sub-entry-lanes-and-seed-identity-defects` · Tasks 7 / 8 / 9
Requirements 3 / 4 / 5

裁决正文在 `h-cycle-sync-foundation-and-first-canary/design.md`（HC-6 / HC-7），
本文件只做 lane 2 的实例化断言。

═══ 三条缺陷的实际后果（修之前）═══

* **BP-5**：H8 四表种子写进 `H8-2-detail-prefill` —— 该键**全仓零读取点**
  （`useH8Detail.ts` 读的是 `ROWS_KEY = 'H8-2-rows'`）⇒ 这段种子代码**从未生效**。
  真库正向实证：`H8-2-detail-prefill` 零载荷、`H8-2-rows` 是空数组 `[]`。
* **BP-6**：三处种子行身份取**数组下标**（`seed-${i}` / `seed-${idx}`）⇒
  源科目清单增删一个叶子就整体串位，把 A 科目的金额写进 B 科目的行，
  而 roundtrip 只看到「同一 rowId、数据变了」**不会报错**。
* **BP-7**：H8 附注同步把稳定动态列 key 降级成**可变中文 label**
  （`key: c.label` / `row[c.label]`）⇒ ①改类别名即列身份漂移 ②两个同名类别撞成一列。
  这是全 H 循环**唯一**背离 H7 动态列范式（SK-1）的地方。
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

from tests.workpaper_sync import h_cycle_facts as F  # noqa: E402

_WP = F.WORKPAPER_DIR
_CO = F.COMPOSABLES


# ═══════════════════════════════════════════════════════════════════════════
# HS-P4　BP-5 修复：写入目标从 `H8-2-detail-prefill` → `H8-2-rows`
# ═══════════════════════════════════════════════════════════════════════════


class TestHsP4Bp5WriteTargetFix:
    """修后 `H8-2-detail-prefill` 字面量全仓命中 == 0。"""

    def test_h8_detail_prefill_literal_is_gone_from_production_code(self) -> None:
        """🔴 BP-5 的**唯一**可执行判据：该键在生产源码里**零读取点**、
        仅在注释/文档里作为历史记录出现。"""
        assert F.key_read_sites("H8-2-detail-prefill") == ()
        # 生产命中 = 0（注释/字符串文档里的提及不影响运行时）
        hits = F.resolve_item_key_hits("H8-2-detail-prefill")
        for rel in hits.production_files:
            text = next(f.text for f in F.frontend_files() if f.rel == rel)
            # 确保只在注释里出现，不在可执行语句里
            for line in text.splitlines():
                stripped = line.strip()
                if "H8-2-detail-prefill" in stripped:
                    assert stripped.startswith("//") or stripped.startswith("*"), (
                        f"{rel}: H8-2-detail-prefill 出现在可执行语句：{stripped[:100]}"
                    )

    def test_seed_now_writes_to_the_real_primary_key(self) -> None:
        """种子代码改后必须写进 `H8-2-rows`（真实主键）。"""
        text = (_WP / "GtH8RightOfUseAssets.vue").read_text(encoding="utf-8", errors="replace")
        assert "map.set('H8-2-rows'" in text, "种子写入目标应为 H8-2-rows"
        # 旧键只在注释里（历史记录），不在可执行 map.set / item_id 语句里
        executable_uses = [
            line.strip()
            for line in text.splitlines()
            if "H8-2-detail-prefill" in line
            and not line.strip().startswith("//")
            and not line.strip().startswith("*")
        ]
        assert executable_uses == [], f"旧键仍在可执行语句：{executable_uses[:3]}"

    def test_bp5_vs_h7_distinction_still_holds(self) -> None:
        """BP-5 修完后 `H8-2-detail-prefill` 零命中；H7 的同形不受影响。"""
        for key in ("H7-2-cost-rows", "H7-2-fair-rows"):
            hits = F.resolve_item_key_hits(key)
            assert hits.resolved, f"{key} 不应受影响"


# ═══════════════════════════════════════════════════════════════════════════
# HS-P6　BP-6 修复：种子行身份从数组下标 → 稳定业务标识
# ═══════════════════════════════════════════════════════════════════════════


class TestHsP6Bp6SeedIdentityFix:
    """修后全 H `seed-${idx}` / `seed-${i}` 命中 == 0；种子身份收敛到单一实现。"""

    def test_seed_index_pattern_is_completely_gone(self) -> None:
        """🔴 三处全改完后，全 H 作业面里 `` rowId:`seed-${ `` 命中 → **0**。"""
        hits = F.scan_identity_family(F.FAMILY_B_RE, exclude_family_a=False)
        assert hits == (), f"仍有 seed-${{idx}} 形态残留：{hits}"

    def test_seed_identity_helper_is_the_single_implementation(self) -> None:
        """三处改动共用 `hSeedRowIdentity.buildHSeedRowIds` —— 单一实现，不各写一遍。"""
        consumers = F.count_consumers("buildHSeedRowIds")
        assert len(consumers.production) >= 3, consumers.production
        expected_sites = {
            "components/workpaper/GtH8RightOfUseAssets.vue",
            "components/workpaper/composables/h4DetailPrefill.ts",
            "components/workpaper/GtH2ConstructionInProgress.vue",
        }
        actual_files = {rel.split(":")[0] for rel in consumers.production}
        assert expected_sites <= actual_files, actual_files - expected_sites

    def test_seed_helper_uses_account_code_not_index(self) -> None:
        """签名上不接受下标参数 —— 杜绝 BP-6 复发。"""
        text = (_CO / "hSeedRowIdentity.ts").read_text(encoding="utf-8", errors="replace")
        assert "accountCode" in text
        assert "idx" not in text.split("function buildHSeedRowId")[1].split("{")[0]
        assert "index" not in text.split("function buildHSeedRowId")[1].split("{")[0]

    def test_backend_prefill_is_not_involved(self) -> None:
        """HC/Req：后端 prefill **引擎**零参与 ⇒ 修复只在前端。

        🔴 `prefill_formula_mapping.json` 的 H 前缀条目虽有 24 条，但 `sheet` 字段
        绝大多数是 `None`（占位）——真正参与引擎计算的条件是 `sheet` **非空**且
        `prefill_anchor_map.py` / `prefill_engine.py` 有对应字面量。
        H0 函证的 `sheet='函证结果汇总表H0-1'` 是唯一例外（它不在 H2~H10 作业面）。
        """
        import json

        mappings = json.loads(
            (F.BACKEND / "data" / "prefill_formula_mapping.json").read_text(encoding="utf-8")
        )["mappings"]
        # H2~H10 的**四表种子**路径后端零参与。
        # 🔴 `prefill_formula_mapping.json` 里 H2~H10 的条目**都有** sheet 字段 ——
        # 但那些是「审定表预填公式」与「明细表 TB 预填公式」，走的是**单元格预填引擎**
        # （`prefill_engine.py` 的 `TB()` / `ADJ()` / `PREV()` / `WP()` 公式），
        # 不是「种子行列表」（`detail_prefill` → `H*-2-rows`）。
        # 两条路径的区别是**产出物不同**：
        #   - 单元格预填 ⇒ 写进单个 cell_ref 的**标量值**（如 `H2-1!期初余额`）
        #   - 四表种子 ⇒ 写进 `H*-2-rows` 的**行对象数组**（`[{rowId, ...}, ...]`）
        # BP-6 说的「后端零参与」特指**后者**。判据：
        #   `prefill_anchor_map.py` 与 `prefill_engine.py` 里**没有**按行组装种子的 H* 逻辑
        anchor_map = (F.BACKEND / "app" / "services" / "prefill_anchor_map.py").read_text(encoding="utf-8")
        engine = (F.BACKEND / "app" / "services" / "prefill_engine.py").read_text(encoding="utf-8")
        import re

        # 不得出现「按 H2~H10 组装 detail_prefill 行列表」的逻辑
        for src, name in ((anchor_map, "prefill_anchor_map"), (engine, "prefill_engine")):
            h_seed_patterns = re.findall(r"detail_prefill.*H[2-9]|H[2-9].*detail_prefill|H10.*detail_prefill", src)
            assert h_seed_patterns == [], f"{name} 出现了 H 明细种子逻辑：{h_seed_patterns[:3]}"


# ═══════════════════════════════════════════════════════════════════════════
# HS-P8　BP-7 修复：H8 附注列键从可变 label → 稳定 key
# ═══════════════════════════════════════════════════════════════════════════


class TestHsP8Bp7DisclosureColumnKeyFix:
    """修后全 H 背离 H7 动态列范式 == 0 处。"""

    def test_h8_disclosure_columns_use_stable_key_not_label(self) -> None:
        """🔴 列定义的 `key` 必须取自 `c.key`（稳定槽键），**不是** `c.label`（可变中文）。"""
        text = (_CO / "h8DisclosureSyncPayload.ts").read_text(encoding="utf-8", errors="replace")
        # cats.map 的映射函数体内：应取 c.key（列数据键），c.label 只用于展示
        cats_map_body = re.search(r"cats\.map\(\(c\)\s*=>\s*\(\{(.*?)\}\)", text, re.S)
        assert cats_map_body, "buildH8ListedColumns 的 cats.map 映射体消失了"
        body = cats_map_body.group(1)
        assert "key: c.key" in body, f"列 key 应取 c.key，实得：{body}"
        assert "key: c.label" not in body, "列 key 不得取 c.label"

    def test_h8_subtable_rows_use_stable_key_not_label(self) -> None:
        """🔴 行数据的列键也必须是 `c.key`（与列定义**必须同时改**）。"""
        text = (_CO / "h8DisclosureSyncPayload.ts").read_text(encoding="utf-8", errors="replace")
        # 文件里 buildH8ListedSubTableData 出现多次（函数声明 + export）——
        # 取第三段（函数体之后）才能找到 `for (const c of cats)` 循环
        parts = text.split("buildH8ListedSubTableData")
        assert len(parts) >= 3, f"buildH8ListedSubTableData 出现 {len(parts)-1} 次"
        fn_body = parts[2]  # 函数体在第三段
        assert "row[c.key]" in fn_body, "行数据列键应为 c.key"
        assert "row[c.label]" not in fn_body, "行数据列键不得为 c.label"

    def test_total_column_uses_reserved_key_not_chinese_literal(self) -> None:
        """🔴 合计列的 key 不能用中文 `'合计'` —— 用户可能自定义同名类别导致撞键。"""
        text = (_CO / "h8DisclosureSyncPayload.ts").read_text(encoding="utf-8", errors="replace")
        assert "H8_LISTED_TOTAL_COLUMN_KEY" in text
        assert re.search(r"H8_LISTED_TOTAL_COLUMN_KEY\s*=\s*'__total__'", text)

    def test_sk1_paradigm_is_satisfied_after_fix(self) -> None:
        """修复后满足 SK-1：key 由稳定前缀+序号构成（或已有语义键），label 独立可改。"""
        text = (_CO / "h8ListedDisclosureModel.ts").read_text(encoding="utf-8", errors="replace")
        # H8 默认分类有 4 个稳定 key
        for expected_key in ("buildings", "machinery", "transport", "other"):
            assert f"key: '{expected_key}'" in text, f"默认分类应保留稳定 key '{expected_key}'"
        # label 是独立字段
        assert "label:" in text

    def test_no_other_h_cycle_site_violates_sk1_after_fix(self) -> None:
        """🔴 修完后全 H 背离 H7 范式的地方从 1 处 → **0 处**。"""
        text = (_CO / "h8DisclosureSyncPayload.ts").read_text(encoding="utf-8", errors="replace")
        # 列定义里不应再有 `key: c.label`
        violations = re.findall(r"key:\s*c\.label", text)
        assert violations == [], violations
