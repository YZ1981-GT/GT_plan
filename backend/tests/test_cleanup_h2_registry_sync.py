"""
Property-based test for H2: registry 同步.

**Validates: Requirements C3, Property H2**

验证 sync_registry_from_json 后：
1. wp_template_registry 行数 == JSON templates 中唯一 code 数
2. 幂等性：重跑结果不变
3. 字段映射正确（code→wp_code, name→wp_name, cycle_prefix→cycle）
"""

import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from hypothesis import given, settings, HealthCheck, assume
from hypothesis import strategies as st

# 仓库根目录
REPO_ROOT = Path(__file__).parent.parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

JSON_PATH = BACKEND_DIR / "data" / "gt_template_library.json"


def _load_json_templates() -> list[dict]:
    """加载 gt_template_library.json 中的 templates 列表。"""
    if not JSON_PATH.exists():
        return []
    raw = JSON_PATH.read_bytes()
    library = json.loads(raw.decode("utf-8-sig"))
    return library.get("templates", [])


def _unique_codes(templates: list[dict]) -> set[str]:
    """提取 templates 中所有唯一的 code。"""
    codes = set()
    for tpl in templates:
        code = tpl.get("code", tpl.get("wp_code", ""))
        if code:
            codes.add(code)
    return codes


# ─── 确定性验证测试 ───────────────────────────────────────────────


class TestH2RegistrySyncDeterministic:
    """H2: registry 同步 — 确定性验证。"""

    def test_json_file_exists(self):
        """gt_template_library.json 存在。"""
        assert JSON_PATH.exists(), f"JSON 文件不存在: {JSON_PATH}"

    def test_json_has_templates(self):
        """JSON 文件包含 templates 列表且非空。"""
        templates = _load_json_templates()
        assert len(templates) > 0, "JSON templates 列表为空"

    def test_json_templates_have_required_fields(self):
        """每条 template 都有 code/name/cycle_prefix 字段。"""
        templates = _load_json_templates()
        for i, tpl in enumerate(templates):
            code = tpl.get("code", tpl.get("wp_code", ""))
            assert code, f"templates[{i}] 缺少 code 字段: {tpl}"
            name = tpl.get("name", tpl.get("wp_name", ""))
            assert name, f"templates[{i}] (code={code}) 缺少 name 字段"
            cycle = tpl.get("cycle_prefix", "")
            assert cycle, f"templates[{i}] (code={code}) 缺少 cycle_prefix 字段"

    def test_unique_code_count_matches_total(self):
        """唯一 code 数 == JSON 中声明的 total_count（或实际去重数）。"""
        templates = _load_json_templates()
        codes = _unique_codes(templates)
        # JSON 中 code 应该是唯一的（scan 脚本 seen_codes 去重）
        assert len(codes) == len(templates), (
            f"存在重复 code: unique={len(codes)}, total={len(templates)}"
        )

    @pytest.mark.asyncio
    async def test_sync_registry_row_count_equals_json(self):
        """
        **Validates: Requirements C3**

        sync_registry_from_json 后 registry 行数 == JSON unique code 数。
        使用 mock db 验证 upsert 调用次数。
        """
        templates = _load_json_templates()
        unique_codes = _unique_codes(templates)

        # Mock AsyncSession
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock()
        mock_db.commit = AsyncMock()

        import scripts.analyze.scan_wp_templates as scan_mod

        await scan_mod.sync_registry_from_json(db=mock_db)

        # execute 调用次数 == unique code 数（每条 template 一次 upsert）
        upsert_call_count = mock_db.execute.call_count
        assert upsert_call_count == len(unique_codes), (
            f"upsert 调用次数 {upsert_call_count} != unique codes {len(unique_codes)}"
        )

    @pytest.mark.asyncio
    async def test_sync_idempotent(self):
        """
        **Validates: Requirements C3**

        幂等性：连续两次调用 sync_registry_from_json，execute 调用次数相同。
        """
        import scripts.analyze.scan_wp_templates as scan_mod

        # 第一次
        mock_db1 = AsyncMock()
        mock_db1.execute = AsyncMock()
        mock_db1.commit = AsyncMock()

        await scan_mod.sync_registry_from_json(db=mock_db1)
        count1 = mock_db1.execute.call_count

        # 第二次
        mock_db2 = AsyncMock()
        mock_db2.execute = AsyncMock()
        mock_db2.commit = AsyncMock()

        await scan_mod.sync_registry_from_json(db=mock_db2)
        count2 = mock_db2.execute.call_count

        assert count1 == count2, (
            f"幂等性失败: 第一次 {count1} 次, 第二次 {count2} 次"
        )

    @pytest.mark.asyncio
    async def test_field_mapping_correct(self):
        """
        **Validates: Requirements C3**

        字段映射验证：code→wp_code, name→wp_name, cycle_prefix→cycle。
        """
        templates = _load_json_templates()
        if not templates:
            pytest.skip("无 templates 数据")

        mock_db = AsyncMock()
        captured_params = []

        async def capture_execute(sql, params=None):
            if params:
                captured_params.append(params)

        mock_db.execute = capture_execute
        mock_db.commit = AsyncMock()

        import scripts.analyze.scan_wp_templates as scan_mod

        await scan_mod.sync_registry_from_json(db=mock_db)

        assert len(captured_params) > 0, "未捕获到任何 upsert 参数"

        # 验证第一条记录的字段映射
        first_tpl = templates[0]
        first_param = captured_params[0]

        assert first_param["wp_code"] == first_tpl.get("code", first_tpl.get("wp_code", ""))
        assert first_param["wp_name"] == first_tpl.get("name", first_tpl.get("wp_name", ""))
        assert first_param["cycle"] == first_tpl.get("cycle_prefix", first_tpl.get("code", "")[0])


# ─── 属性测试（Hypothesis）─────────────────────────────────────────


# 生成合法的底稿模板条目
@st.composite
def template_entry(draw):
    """生成一条合法的底稿模板 JSON 条目。"""
    prefix = draw(st.sampled_from(list("ABCDEFGHIJKLMNS")))
    num = draw(st.integers(min_value=1, max_value=99))
    code = f"{prefix}{num}"
    name = draw(st.text(
        alphabet=st.characters(whitelist_categories=("L", "N")),
        min_size=1, max_size=20,
    ))
    return {
        "code": code,
        "name": name,
        "wp_type": "substantive",
        "cycle_prefix": prefix,
        "cycle_name": f"{prefix}类",
        "file_path": f"templates/{code}.xlsx",
        "description": "",
    }


@st.composite
def template_library(draw):
    """生成一个合法的 gt_template_library.json 结构（唯一 code）。"""
    entries = draw(st.lists(template_entry(), min_size=1, max_size=15))
    # 去重 code
    seen = set()
    unique_entries = []
    for e in entries:
        if e["code"] not in seen:
            seen.add(e["code"])
            unique_entries.append(e)
    assume(len(unique_entries) >= 1)
    return {
        "description": "test",
        "version": "test",
        "scan_source": "test",
        "total_count": len(unique_entries),
        "templates": unique_entries,
    }


class TestH2Property:
    """H2 属性测试：sync 后 registry 行数 == JSON unique code 数。"""

    @given(lib=template_library())
    @settings(
        max_examples=15,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
    )
    @pytest.mark.asyncio
    async def test_upsert_count_equals_unique_codes(self, lib: dict):
        """
        **Validates: Requirements C3**

        属性：对任意合法的 template library JSON，sync_registry_from_json
        执行的 upsert 次数恰好等于 JSON 中唯一 code 的数量。
        """
        import tempfile
        import scripts.analyze.scan_wp_templates as scan_mod

        unique_codes = {t["code"] for t in lib["templates"]}

        mock_db = AsyncMock()
        call_count = 0

        async def counting_execute(sql, params=None):
            nonlocal call_count
            if params:
                call_count += 1

        mock_db.execute = counting_execute
        mock_db.commit = AsyncMock()

        # Create temp directory structure and patch ROOT
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_root = Path(tmpdir)
            data_dir = tmp_root / "data"
            data_dir.mkdir(parents=True, exist_ok=True)
            target = data_dir / "gt_template_library.json"
            target.write_text(json.dumps(lib, ensure_ascii=False), encoding="utf-8")

            original_root = scan_mod.ROOT
            scan_mod.ROOT = tmp_root
            try:
                call_count = 0
                await scan_mod.sync_registry_from_json(db=mock_db)
            finally:
                scan_mod.ROOT = original_root

        assert call_count == len(unique_codes), (
            f"upsert 次数 {call_count} != unique codes {len(unique_codes)}"
        )
