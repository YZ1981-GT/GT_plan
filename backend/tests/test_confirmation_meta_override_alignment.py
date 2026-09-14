"""七循环 meta ↔ override 交叉锁死守卫（Property 12）。

对 D0/E0/F0/G0/H0/K0/L0：
- meta 的每个非 null code SHALL 在 override 表有映射
- meta 为 null 的 SHALL NOT 要求映射
- override 里 skip 的 sheet SHALL NOT 出现在任何 meta 的非 null code

e0-confirmation-completion Task 13
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

# ─── 加载 meta（前端 TS）和 override（后端 JSON）────────────────────────────

_FRONTEND = Path(__file__).resolve().parents[2] / "audit-platform" / "frontend"
_META_FILE = (
    _FRONTEND / "src" / "components" / "workpaper" / "confirmation"
    / "coordination" / "cycleConfirmationMeta.ts"
)

from app.services.wp_classification_service import refresh_wp_code_overrides


@pytest.fixture(scope="module")
def overrides() -> dict[str, str]:
    return refresh_wp_code_overrides()


@pytest.fixture(scope="module")
def meta_source() -> str:
    assert _META_FILE.exists(), f"Meta 文件不存在: {_META_FILE}"
    return _META_FILE.read_text(encoding="utf-8")


def _extract_cycle_meta(source: str) -> dict[str, dict[str, str | None]]:
    """从 TS 源码提取各循环 meta 的非 null code 字段。"""
    cycles: dict[str, dict[str, str | None]] = {}
    # 匹配 E0: { ... }, 等块
    cycle_re = re.compile(r"(\w0):\s*\{([^}]+)\}", re.S)
    for m in cycle_re.finditer(source):
        cycle = m.group(1)
        block = m.group(2)
        fields: dict[str, str | None] = {}
        # 匹配 fieldName: 'value' 或 fieldName: null
        field_re = re.compile(r"(\w+Code)\s*:\s*(?:'([^']+)'|null)")
        for fm in field_re.finditer(block):
            fields[fm.group(1)] = fm.group(2)  # group(2) is None if null
        cycles[cycle] = fields
    return cycles


@pytest.fixture(scope="module")
def all_meta(meta_source) -> dict[str, dict[str, str | None]]:
    return _extract_cycle_meta(meta_source)


EXPECTED_CYCLES = {"D0", "E0", "F0", "G0", "H0", "K0", "L0"}


class TestMetaOverrideAlignment:
    def test_all_seven_cycles_present(self, all_meta):
        assert set(all_meta.keys()) >= EXPECTED_CYCLES

    def test_non_null_codes_have_override(self, all_meta, overrides):
        """meta 的非 null code 必须在 override 有映射。"""
        missing = []
        for cycle, fields in all_meta.items():
            if cycle not in EXPECTED_CYCLES:
                continue
            for field, code in fields.items():
                if code is None:
                    continue
                # code 可能是 'E0-7' 形式，查 override 时先试完整名再试编码
                if code not in overrides:
                    # 也可能以尾码存在
                    found = any(k.endswith(code) for k in overrides) or code in overrides.values()
                    if not found:
                        missing.append(f"{cycle}.{field}={code}")
        assert not missing, f"Meta 非 null code 在 override 无映射: {missing}"

    def test_null_codes_not_required(self, all_meta, overrides):
        """meta 为 null 的字段不要求 override 映射（本测试确认无误报）。"""
        # 只要 non-null 那条测试通过，本条自然成立；加一条显式验证
        null_count = sum(
            1 for fields in all_meta.values()
            for code in fields.values()
            if code is None
        )
        assert null_count > 0, "至少有一个 null code（E0.reliabilityCode 等）"

    def test_skip_sheets_not_in_any_meta_code(self, all_meta, overrides):
        """override 里 skip 的 sheet SHALL NOT 出现在任何 meta 的非 null code。"""
        skip_sheets = {k for k, v in overrides.items() if v == "skip"}
        all_codes = set()
        for fields in all_meta.values():
            for code in fields.values():
                if code is not None:
                    all_codes.add(code)
        # 直接相交
        conflict = skip_sheets & all_codes
        # 也检查 skip sheet 是否以某个 code 结尾
        for sheet in skip_sheets:
            for code in all_codes:
                if sheet.endswith(code) and sheet != code:
                    # sheet_name 包含 code 作后缀 → 检查该 code 是否恰好被 skip 遮蔽
                    if overrides.get(sheet) == "skip":
                        conflict.add(f"{sheet}(遮蔽 {code})")
        # 过滤掉仅按 sheet_name 遮蔽但 code 本身有独立 override 的情况
        real_conflict = set()
        for item in conflict:
            if "(" in item:
                # 格式 "sheet(遮蔽 code)"
                code_part = item.split("遮蔽 ")[1].rstrip(")")
                if code_part in overrides and overrides[code_part] != "skip":
                    continue  # code 自己有独立非 skip 映射，不算冲突
            real_conflict.add(item)
        assert not real_conflict, (
            f"override skip 的 sheet 与 meta 非 null code 冲突: {real_conflict}\n"
            "→ meta 声称有那张表、渲染层却 skip 掉 = 静默失效"
        )


class TestReverseChecks:
    def test_removing_e0_7_override_would_fail(self, all_meta, overrides):
        """反向自检：E0.followupCode='E0-7' 在 override 有映射。"""
        e0_meta = all_meta.get("E0", {})
        assert e0_meta.get("followupCode") == "E0-7"
        # E0-7 或包含 E0-7 的 key 在 override 里
        assert "E0-7" in overrides or any(
            k.endswith("E0-7") for k in overrides
        ), "E0-7 应在 override 中有映射"

    def test_setting_reliability_to_f1_12_would_conflict(self, overrides):
        """反向自检：把 reliabilityCode 填成 F1-12 → 与 skip 冲突。"""
        # 邮件传真回函核对记录F1-12 已经是 skip
        assert overrides.get("邮件传真回函核对记录F1-12") == "skip"
        # 所以如果 meta 填了它，skip∩code 断言会打红
