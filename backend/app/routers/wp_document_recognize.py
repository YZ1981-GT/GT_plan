"""原始凭证识别路由（已退役）— wp-evidence-collection spec Task 3

端点（均返回 410 并指明替代入口）：
  POST /api/projects/{project_id}/document-recognize        批量识别
  GET  /api/projects/{project_id}/document-recognize/types  支持类型

退役原因（spec voucher-workflow-linkage-lineage-closure R9.3，ADR-VWL-09）：
- 只校验登录，按附件 id 读附件时不校验附件属于哪个项目（任一登录用户可读他人项目附件的元数据）；
- 识别实现是桩：大模型只拿到文件名，结果却标「recognized」；
- 唯一的前端入口 ``DocumentRecognizeDialog.vue`` 没有挂载到任何页面，请求路径也少了 ``/api`` 前缀。
底稿证据入口（``workpaper_evidence_intake``：先建附件、校验底稿与项目，再识别）与附件识别已覆盖这项能力。
处理函数不读库、不调模型；识别服务 ``wp_document_recognizer`` 另有单测引用，暂留。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.deps import get_current_user

router = APIRouter(
    prefix="/projects/{project_id}/document-recognize",
    tags=["原始凭证识别"],
)

RETIRED_DETAIL = {
    "error_code": "ENDPOINT_RETIRED",
    "message": "单据识别入口已停用：请在底稿内用「上传证据」识别，或到附件管理查看、确认附件的识别结果",
}


@router.post("")
async def recognize_documents(project_id: str, user=Depends(get_current_user)):
    """已退役：返回 410。"""
    raise HTTPException(status_code=410, detail=RETIRED_DETAIL)


@router.get("/types")
async def get_doc_types(project_id: str, user=Depends(get_current_user)):
    """已退役：返回 410。"""
    raise HTTPException(status_code=410, detail=RETIRED_DETAIL)
