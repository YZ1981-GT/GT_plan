"""OnlyOffice 保存产物的最小 OOXML 规范化。

OnlyOffice 会给 ``word/numbering.xml`` 的编号级别写 ``<w:isLgl w:val="false"/>``。
按 OOXML，显式 false 与不写等价；但 LibreOffice 误把元素「存在」当成开启 legal numbering，
把 ``japaneseCounting`` 的「七、」渲染成十进制「7、」。本模块只删除该假值元素，
不改 true/on/1，也不重序列化 XML；无命中 / 非法 zip 原样返回输入字节。

Spec: deliverable-writeback-and-online-edit-integrity AC-5.6 / design §3.3。
"""
from __future__ import annotations

import logging
import re
import zipfile
from io import BytesIO

logger = logging.getLogger(__name__)

_NUMBERING_PART = "word/numbering.xml"
_FALSE_IS_LGL = re.compile(
    rb"<w:isLgl\b(?=[^>]*\bw:val\s*=\s*['\"](?:false|0|off)['\"])[^>]*/\s*>",
    re.IGNORECASE,
)


def normalize_onlyoffice_docx(content: bytes) -> bytes:
    """删除 numbering.xml 中显式为假的 ``w:isLgl``；其余 zip 条目字节不变。

    非 docx / 损坏 zip / 缺 numbering.xml / 无假值命中均原样返回。回调保存不能因兼容性修复失败
    而丢用户编辑；异常只记 warning 并保留原始文件。
    """
    if not content:
        return content
    try:
        with zipfile.ZipFile(BytesIO(content), "r") as source:
            if _NUMBERING_PART not in source.namelist():
                return content
            numbering = source.read(_NUMBERING_PART)
            normalized, count = _FALSE_IS_LGL.subn(b"", numbering)
            if count == 0:
                return content

            out = BytesIO()
            with zipfile.ZipFile(out, "w") as target:
                for info in source.infolist():
                    payload = normalized if info.filename == _NUMBERING_PART else source.read(info.filename)
                    # 复用原 ZipInfo（时间、权限、压缩方法等）；只让目标库重新计算 CRC / size。
                    target.writestr(info, payload)
            logger.info("OnlyOffice docx 编号规范化：删除 %d 个显式 false 的 w:isLgl", count)
            return out.getvalue()
    except (zipfile.BadZipFile, KeyError, OSError, ValueError):
        logger.warning("OnlyOffice docx 编号规范化失败，保留原始字节", exc_info=True)
        return content
