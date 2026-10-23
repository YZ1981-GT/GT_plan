"""
统一地址坐标注册表 API

@see address_registry_v2 — 本模块=运行时动态地址目录（公式编辑用）

GET  /api/address-registry          — 搜索地址（keyword/domain过滤）
GET  /api/address-registry/stats    — 注册表统计
GET  /api/address-registry/resolve  — 解析单个URI
POST /api/address-registry/validate — 校验公式引用有效性
POST /api/address-registry/jump     — 获取跳转路由
POST /api/address-registry/invalidate — 失效缓存
"""
import asyncio

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.offloop_json import encode_object_with_chunked_array, preencoded_json_response
from app.deps import get_current_user
from app.services.address_registry import (
    ADDRESS_DOMAIN_ORDER, ADDRESS_REGISTRY_MAX_LIMIT,
    AddressEntry, address_registry, parse_uri, formula_ref_to_uri,
    uri_to_formula_ref, build_jump_route,
)

router = APIRouter(prefix="/api/address-registry", tags=["地址坐标-公式编辑选址(V1)"])


@router.get("")
async def search_addresses(
    project_id: str = Query(...),
    year: int = Query(0),
    keyword: str = Query(''),
    domain: str = Query('', description="过滤域: report/note/wp/tb/aux"),
    template_type: str = Query('soe'),
    # 超过上限直接 422（不静默截断成上限）；前端整库加载取的就是这个上限
    limit: int = Query(100, ge=1, le=ADDRESS_REGISTRY_MAX_LIMIT),
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
):
    """搜索可引用地址（支持按域单独加载，减少首次加载量）。

    ``total`` = 真实匹配数，``returned`` = 本次返回条数，``truncated`` = 是否被 ``limit`` 截断，
    ``truncated_domains`` = 有地址没返回的域（前端据此不把这些域当成完整的，spec
    formula-fetch-and-wp-generation-defect-closure R3.2）。原 ``total`` 是截断后的条数，看不出截断。
    """
    matched = await address_registry.match(db, project_id, year, keyword, domain, template_type)
    # 整库可达 5 万条 / 27 MB：在工作线程里分块编码并直接返回字节（不经 jsonable_encoder，
    # 中间件按字节拼信封）。事件循环上原先要停 1.1 s（spec writeback-followup-issue-closure R5）
    body = await asyncio.to_thread(encode_search_payload, matched, limit)
    return preencoded_json_response(body)


def _search_item(e: AddressEntry) -> dict:
    return {
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


def encode_search_payload(matched: list[AddressEntry], limit: int) -> bytes:
    """搜索响应的业务载荷字节（键与顺序同原 dict 返回值）。同步纯函数，由路由放进工作线程。"""
    entries = matched[:limit]
    cut = {e.domain for e in matched[limit:]}
    head = {
        'total': len(matched),
        'returned': len(entries),
        'truncated': len(matched) > limit,
        'truncated_domains': [d for d in ADDRESS_DOMAIN_ORDER if d in cut] + sorted(cut - set(ADDRESS_DOMAIN_ORDER)),
    }
    return encode_object_with_chunked_array(head, 'items', (_search_item(e) for e in entries))


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
    """精准失效地址缓存（L1 内存 + L2 Redis 同步删除）

    支持参数组合：
    - project_id 必填
    - year 可选：指定年度
    - domain 可选：指定域(report/tb/note/wp/aux)
    - template_type 可选：指定模板类型(soe/listed)
    - all 可选：true时清空全部缓存
    """
    if body.get('all'):
        await address_registry.invalidate_all_async()
        return {'ok': True, 'scope': 'all'}

    project_id = body.get('project_id', '')
    if not project_id:
        return {'ok': False, 'error': 'project_id required'}

    await address_registry.invalidate_async(
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
