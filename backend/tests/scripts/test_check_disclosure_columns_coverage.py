"""check_disclosure_columns_coverage.py 单元测试。

覆盖守卫的判定口径（disclosure-columns-coverage-rollout Task 5.3）：

- 载荷字段用 **ES6 对象简写**（``sub_table_data,`` / ``columns,``）时必须判为已覆盖
  —— L1/L3 四个 Tab 用的正是简写，旧正则只认 ``sub_table_data:`` 故假阴性；
- 反向：推了 ``sub_table_data`` 但通篇没有 ``columns`` 仍须判为未覆盖
  （放宽写法，不放宽实质要求）；
- allowlist 原因空白不生效（R4.3）。
"""

import sys
from pathlib import Path

# 确保 scripts/check 可 import
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "check"))

from check_disclosure_columns_coverage import (  # noqa: E402
    ALLOWLIST,
    _is_covered,
    allowlist_reason,
    blank_reason_entries,
    is_allowlisted,
)

# 真实形态：L1TabDisclosureListed.vue 的同步函数（对象简写）
SHORTHAND_CALL_SITE = """
async function syncToDisclosureNotes() {
  syncing.value = true
  try {
    const { sub_table_data, columns } = buildL1SyncPayload({
      variant: 'listed',
      categoryRows: categoryRows.value,
    })
    await http.post(`/api/projects/${props.projectId}/disclosure-notes/sync-from-workpaper`, {
      wp_id: props.wpId,
      section_id: L1_NOTE_SECTION.listed,
      sub_table_data,
      columns,
    })
  } finally {
    syncing.value = false
  }
}
"""

# 显式键形态（存量多数 Tab）
COLON_CALL_SITE = """
    await http.post(url + '/disclosure-notes/sync-from-workpaper', {
      wp_id: wpId,
      sub_table_data: { rows },
      columns: { rows: buildCols() },
    })
"""

# 反例：简写推了 sub_table_data，但整个文件没有 columns
SHORTHAND_WITHOUT_COLUMNS = """
    const { sub_table_data } = buildDemoSyncPayload({ variant: 'listed' })
    await http.post(url + '/disclosure-notes/sync-from-workpaper', {
      wp_id: wpId,
      sub_table_data,
    })
"""

# 反例：columns 只出现在 el-table summary-method 的类型注解里，且远离载荷
SUMMARY_METHOD_ONLY = """
function getSummary({ columns }: { columns: any[] }) {
  return columns.map(() => '')
}
""" + ("\n// filler\n" * 80) + """
    await http.post(url + '/disclosure-notes/sync-from-workpaper', {
      sub_table_data: { rows },
    })
"""


class TestIsCovered:
    """_is_covered：内联载荷字段识别。"""

    def test_object_shorthand_counts_as_covered(self):
        """ES6 简写 ``sub_table_data,`` / ``columns,`` 必须判为已覆盖。"""
        assert _is_covered(SHORTHAND_CALL_SITE) is True

    def test_explicit_colon_still_covered(self):
        """显式键写法行为不变（防回归）。"""
        assert _is_covered(COLON_CALL_SITE) is True

    def test_shorthand_without_columns_is_uncovered(self):
        """简写推了 sub_table_data 但通篇无 columns → 仍未覆盖。"""
        assert _is_covered(SHORTHAND_WITHOUT_COLUMNS) is False

    def test_summary_method_type_annotation_is_not_coverage(self):
        """远离载荷的 ``{ columns }: { columns: any[] }`` 不算覆盖（防假阳性）。"""
        assert _is_covered(SUMMARY_METHOD_ONLY) is False

    def test_known_builder_reference_is_covered(self):
        """引用 allowlist 内构造器即视为覆盖。"""
        text = "const payloads = buildF2SyncPayload({ variant: 'soe' })\n"
        assert _is_covered(text) is True

    def test_build_columns_helper_regex_is_covered(self):
        """命中 ``build[A-Z]\\w*Columns`` 的构造器即视为覆盖（无需扩白名单）。"""
        text = "import { buildL1ListedColumns } from '../../composables/l1NoteSectionMap'\n"
        assert _is_covered(text) is True

    def test_columns_property_access_is_not_a_field(self):
        """``columns.forEach`` 之类属性访问不得被当成载荷字段。"""
        text = """
    const cols = props.columns.filter(Boolean)
    columns.forEach((c) => c)
    await http.post(url + '/disclosure-notes/sync-from-workpaper', {
      sub_table_data,
    })
"""
        assert _is_covered(text) is False


class TestAllowlistReason:
    """allowlist 原因必填（R4.3）。"""

    def test_unregistered_path_has_no_reason(self):
        assert allowlist_reason("components/does/not/exist.vue") == ""
        assert is_allowlisted("components/does/not/exist.vue") is False

    def test_blank_reason_does_not_exempt(self, monkeypatch):
        monkeypatch.setitem(ALLOWLIST, "components/x/Y.vue", "   ")
        assert is_allowlisted("components/x/Y.vue") is False
        assert "components/x/Y.vue" in blank_reason_entries()

    def test_non_blank_reason_exempts(self, monkeypatch):
        monkeypatch.setitem(ALLOWLIST, "components/x/Z.vue", "Wave4 待迁移 — 源模板待补")
        assert is_allowlisted("components/x/Z.vue") is True
        assert "components/x/Z.vue" not in blank_reason_entries()
