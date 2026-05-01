"""
统一地址坐标注册表 API

GET  /api/address-registry          — 搜索地址（keyword/domain过滤）
GET  /api/address-registry/stats    — 注册表统计
GET  /api/address-registry/resolve  — 解析单个URI
POST /api/address-registry/validate — 校验公式引用有效性
POST /api/address-registry/jump     — 获取跳转路由
POST /api/address-registry/invalidate — 失效缓存
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.services.address_registry import (
    address_registry, parse_uri, formula_ref_to_uri,
    uri_to_formula_ref, build_jump_route,
)

router = APIRouter(prefix="/api/address-registry", tags=["地址坐标"])


@router.get("")
async def search_addresses(
    project_id: str = Query(...),
    year: int = Query(0),
    keyword: str = Query(''),
    domain: str = Query('', description="过滤域: report/note/wp/tb/aux"),
    template_type: str = Query('soe'),
    limit: int = Query(100),
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
):
    """搜索可引用地址（支持按域单独加载，减少首次加载量）"""
    entries = await address_registry.search(
        db, project_id, year, keyword, domain, template_type, limit
    )
    return {
        'total': len(entries),
        'items': [
            {
                'uri': e.uri,
                'domain': e.domain,
                'source': e.source,
                'path': e.path,
                'cell': e.cell,
                'label': e.label,
                'formula_ref': e.formula_ref,
                'jump_route': e.jump_route,
                'row_code': e.row_code,
                'account_code': e.account_code,
                'note_section': e.note_section,
                'wp_code': e.wp_code,
                'tags': e.tags,
            }
            for e in entries
        ],
    }


@router.get("/stats")
async def get_stats(
    project_id: str = Query(...),
    year: int = Query(0),
    template_type: str = Query('soe'),
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
):
    """获取注册表统计"""
    return await address_registry.get_stats(db, project_id, year, template_type)


@router.get("/resolve")
async def resolve_uri(
    uri: str = Query(...),
    project_id: str = Query(...),
    year: int = Query(0),
    template_type: str = Query('soe'),
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
):
    """解析单个URI为地址详情"""
    entry = await address_registry.resolve(db, project_id, year, uri, template_type)
    if not entry:
        return {'found': False, 'uri': uri}
    return {
        'found': True,
        'uri': entry.uri,
        'label': entry.label,
        'formula_ref': entry.formula_ref,
        'jump_route': entry.jump_route,
        'domain': entry.domain,
        'tags': entry.tags,
    }


@router.post("/validate")
async def validate_formula(
    body: dict,
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
):
    """校验公式中引用的地址是否有效"""
    formula = body.get('formula', '')
    project_id = body.get('project_id', '')
    year = body.get('year', 0)
    template_type = body.get('template_type', 'soe')

    issues = await address_registry.validate_formula_refs(
        db, project_id, year, formula, template_type
    )
    return {
        'valid': len(issues) == 0,
        'issues': issues,
        'formula': formula,
    }


@router.post("/jump")
async def get_jump_route(
    body: dict,
    _user=Depends(get_current_user),
):
    """根据URI或公式引用获取前端跳转路由"""
    uri = body.get('uri', '')
    formula_ref_input = body.get('formula_ref', '')
    project_id = body.get('project_id', '')
    year = body.get('year', 0)

    # 如果传的是公式引用，先转为URI
    if not uri and formula_ref_input:
        uri = formula_ref_to_uri(formula_ref_input) or ''

    if not uri:
        return {'route': '', 'error': '无法解析地址'}

    route = build_jump_route(uri, project_id, year)
    return {
        'route': route,
        'uri': uri,
        'formula_ref': uri_to_formula_ref(uri) or formula_ref_input,
    }


@router.post("/invalidate")
async def invalidate_cache(
    body: dict,
    _user=Depends(get_current_user),
):
    """精准失效地址缓存

    支持参数组合：
    - project_id 必填
    - year 可选：指定年度
    - domain 可选：指定域(report/tb/note/wp/aux)
    - template_type 可选：指定模板类型(soe/listed)
    - all 可选：true时清空全部缓存
    """
    if body.get('all'):
        address_registry.invalidate_all()
        return {'ok': True, 'scope': 'all'}

    project_id = body.get('project_id', '')
    if not project_id:
        return {'ok': False, 'error': 'project_id required'}

    address_registry.invalidate(
        project_id,
        year=body.get('year', 0),
        domain=body.get('domain', ''),
        template_type=body.get('template_type', ''),
    )
    return {'ok': True, 'scope': {
        'project_id': project_id,
        'year': body.get('year'),
        'domain': body.get('domain'),
        'template_type': body.get('template_type'),
    }}


@router.get("/parse")
async def parse_address(
    uri: str = Query(''),
    formula_ref: str = Query(''),
    _user=Depends(get_current_user),
):
    """工具接口：解析URI或公式引用"""
    result = {}
    if uri:
        result['uri_parts'] = parse_uri(uri)
        result['formula_ref'] = uri_to_formula_ref(uri)
    if formula_ref:
        result['uri'] = formula_ref_to_uri(formula_ref)
        if result.get('uri'):
            result['uri_parts'] = parse_uri(result['uri'])
    return result
