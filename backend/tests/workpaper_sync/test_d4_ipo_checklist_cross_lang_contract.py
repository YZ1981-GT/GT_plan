# -*- coding: utf-8 -*-
"""D4-25~28 IPO 检查表：前后端跨语言契约守卫（第四边）。

spec: d4-ipo-checklist-dual-mode-writeback-and-formula · Wave 2

为什么需要这条守卫：
- 后端 provider（phase5_d4_ipo_checklist_sheets）与前端 ipoChecklistSchema + 4 个 D4Tab*.vue
  之间没有任何一层测试直接比对。前端 d4IpoSyncHostWiring.spec.ts 只断言「前端 sheetKey 常量
  == 'd4-25-managed'」，**从不看后端实际发出的 sheet_key**；后端自己的 roundtrip 测试也不看前端。
- 结果：后端曾把 sheet_key 生成成 'd425-managed'（无连字符），前端传 'd4-25-managed'（带连字符），
  `readStoreProjection` 按 sheetKey 查后端契约 → 查不到 → OO 双向回写静默失败，而所有单侧测试全绿。
  这是「跨语言契约守卫层级不够」的假绿第②变体（比渲染层死代码更隐蔽，因为两侧各自的常量都对）。
- 本守卫把两侧的**真值**（后端 sheet_key 字段 + 前端 .vue 里的 D4_2X_SHEET_KEY 字面量 +
  前端 ipoChecklistSchema 列 key）拉到一起逐张比对，任一侧漂移即打红。
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.services.workpaper_sync import phase5_d4_ipo_checklist_sheets as CK

REPO = Path(__file__).resolve().parents[3]
IPO_DIR = REPO / "audit-platform/frontend/src/components/workpaper/d4/ipo"
SCHEMA_TS = IPO_DIR / "ipoChecklistSchema.ts"

# 后端 sheet_code → 前端 .vue 文件 + ipoChecklistSchema 列数组常量名
HOST_BY_CODE = {
    "D4-25": ("D4TabDealer.vue", "D4_25_COLUMNS"),
    "D4-26": ("D4TabOverseas.vue", "D4_26_COLUMNS"),
    "D4-27": ("D4TabUndisclosedRp.vue", "D4_27_COLUMNS"),
    "D4-28": ("D4TabCustomerChecklist.vue", "D4_28_COLUMNS"),
}


def _front_sheet_key(code: str) -> str:
    """从前端 .vue 里抓 `D4_2X_SHEET_KEY = '...'` 字面量。"""
    vue = IPO_DIR / HOST_BY_CODE[code][0]
    src = vue.read_text(encoding="utf-8-sig")
    m = re.search(rf"D4_{code.split('-')[1]}_SHEET_KEY\s*=\s*'([^']+)'", src)
    assert m, f"{code}: 前端未定义 D4_{code.split('-')[1]}_SHEET_KEY 常量（sheetKey 被内联，破坏可锁死性）"
    return m.group(1)


def _front_column_keys(varname: str) -> list[str]:
    """从 ipoChecklistSchema.ts 抓某列数组的 key 序列。"""
    ts = SCHEMA_TS.read_text(encoding="utf-8-sig")
    m = re.search(varname + r"\s*[:=\w\[\]<> ,]*=\s*\[(.*?)\n\]", ts, re.S)
    assert m, f"{varname}: ipoChecklistSchema 未找到该列数组"
    return re.findall(r"key:\s*'([^']+)'", m.group(1))


@pytest.mark.parametrize("code", CK.CHECKLIST_SHEET_CODES)
def test_backend_sheet_key_matches_frontend_literal(code: str) -> None:
    """后端 sheet_key 必须等于前端 .vue 里的 D4_2X_SHEET_KEY 字面量（OO 按 sheetKey 查契约）。"""
    be = CK._SHEETS[code]["sheet_key"]
    fe = _front_sheet_key(code)
    assert be == fe, (
        f"{code}: 后端 sheet_key={be!r} 与前端 D4_2X_SHEET_KEY={fe!r} 不一致 —— "
        f"readStoreProjection 按前端 sheetKey 查后端契约会查不到，OO 双向回写静默失败。"
    )
    # 命名约定：d4-2X-managed（连字符在 d4 与 2X 之间）
    assert be == f"d4-{code.split('-')[1]}-managed", f"{code}: sheet_key 命名约定应为 d4-{code.split('-')[1]}-managed，实得 {be}"


@pytest.mark.parametrize("code", CK.CHECKLIST_SHEET_CODES)
def test_backend_json_path_subset_of_frontend_column_keys(code: str) -> None:
    """后端每列 json_path 必须是前端 ipoChecklistSchema 列 key 的子集（否则投影映射到不存在的字段）。"""
    be_keys = [spec[4] for spec in CK._SHEETS[code]["fields"]]
    fe_keys = set(_front_column_keys(HOST_BY_CODE[code][1]))
    missing = [k for k in be_keys if k not in fe_keys]
    assert not missing, (
        f"{code}: 后端 json_path {missing} 不在前端 ipoChecklistSchema 列 key 里 —— 投影会写入不存在的字段。"
    )


@pytest.mark.parametrize("code", CK.CHECKLIST_SHEET_CODES)
def test_frontend_derived_columns_not_managed(code: str) -> None:
    """前端派生列（不在后端受管契约里）必须恰好是已登记的 mask/派生列，禁意外列漏管。"""
    be_keys = {spec[4] for spec in CK._SHEETS[code]["fields"]}
    fe_keys = set(_front_column_keys(HOST_BY_CODE[code][1]))
    unmanaged = fe_keys - be_keys
    # 仅 D4-27 的 total 是源模板内嵌 =SUM 派生列（入 FORMULA_MASK，不应受管）；其余表不得有未受管列。
    allowed = {"total"} if code == "D4-27" else set()
    unexpected = unmanaged - allowed
    assert not unexpected, (
        f"{code}: 前端列 {sorted(unexpected)} 未被后端受管 —— 若是计算列应显式进 FORMULA_MASK，否则是漏管。"
    )
    if code == "D4-27":
        assert "M15:M24" in CK._SHEETS["D4-27"]["formula_mask"], "D4-27 total 列必须入 FORMULA_MASK"
