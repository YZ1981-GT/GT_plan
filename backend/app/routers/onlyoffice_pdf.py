"""OnlyOffice 转 PDF 时回来取待转换文件的接口（``services/onlyoffice_pdf``）。

OnlyOffice 容器不带用户令牌，靠地址里的 HMAC 签名（2 分钟有效）鉴权；文件只在转换期间存在，
转换结束即删除。编号是 64 位随机十六进制，不含项目信息，不能拿来枚举项目文件。
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from app.services import onlyoffice_pdf

router = APIRouter(prefix="/api/onlyoffice-pdf", tags=["OnlyOffice 转 PDF"])


@router.get("/sources/{source_id}")
async def get_convert_source(source_id: str, expires: int = Query(...), sig: str = Query(..., max_length=128)):
    if not onlyoffice_pdf.verify_source(source_id, expires, sig):
        raise HTTPException(status_code=403, detail="签名无效或已过期")
    path = onlyoffice_pdf.source_path(source_id)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="待转换文件不存在")
    return FileResponse(path, media_type=onlyoffice_pdf.DOCX_MEDIA, filename="source.docx")
