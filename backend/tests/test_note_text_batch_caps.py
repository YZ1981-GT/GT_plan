"""附注正文批量写入：章节数上限（2026-10-15 拍板 Word 解析章节上限 500 → 1000）。

从 ``test_note_text_batch_endpoints.py`` 拆出（该文件已到行数门禁 800），复用同一套端点夹具与请求 helper。
"""

from __future__ import annotations

import pytest

from tests import test_note_text_batch_endpoints as _endpoints
from tests.test_note_text_batch_endpoints import _docx, _item, _parse, _preview

#: 复用端点测试的夹具（pytest 按名注入）
env = _endpoints.env


class TestSectionCap:
    """2026-10-15 拍板：Word 解析章节上限 500 → 1000（国企合并 412 章只剩 18% 余量）。

    解析结果要原样回传给预览 / 写入：请求体里来源章节数、手工映射数的上限必须跟着解析上限走，
    否则「解析成功、预览 422」。
    """

    @pytest.mark.asyncio
    async def test_full_cap_parse_previews_and_overflow_is_truncated_with_warning(self, env):
        from app.services.note_document_parser import MAX_SECTIONS

        assert MAX_SECTIONS == 1000
        blocks = [("公司基本情况", "本公司成立于2001年。")] + [(f"补充事项{i}", f"说明{i}。") for i in range(MAX_SECTIONS)]
        resp = await _parse(env, _docx(*blocks))
        assert resp.status_code == 200, resp.text
        parsed = resp.json()
        assert len(parsed["sections"]) == MAX_SECTIONS  # 1001 章截到 1000 章
        assert [w for w in parsed["warnings"] if "超过上限 1000" in w], parsed["warnings"]
        preview = await _preview(env, {"source_kind": "upload", "parsed_source": parsed})
        assert preview.status_code == 200, preview.text[:300]
        assert _item(preview.json(), "公司基本情况")["target_note_id"] == str(env["ids"]["basic"])

    def test_request_caps_follow_parse_cap(self):
        from app.models.note_content_template_schemas import BatchApplyRequest, BatchPreviewRequest, ParsedSource
        from app.services.note_document_parser import MAX_SECTIONS

        def cap(model, field: str) -> int:
            return next(m.max_length for m in model.model_fields[field].metadata if hasattr(m, "max_length"))

        assert cap(ParsedSource, "sections") == MAX_SECTIONS
        assert cap(BatchPreviewRequest, "manual_mappings") == cap(BatchApplyRequest, "manual_mappings") == MAX_SECTIONS
