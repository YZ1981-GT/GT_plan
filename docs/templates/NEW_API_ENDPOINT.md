# 新增 API 端点"三件套"模板

新增任何 API 端点时，必须同时完成以下三步，确保前后端联动一致性。

---

## 1. 后端实现（backend/app/routers/xxx.py）

```python
"""模块说明"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.deps import get_current_user

router = APIRouter(prefix="/your-module", tags=["模块名"])


@router.get("")
async def list_items(
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """端点说明"""
    # 实现逻辑
    pass
```

注册到 `router_registry.py` 对应的业务域分组。

---

## 2. apiPaths 定义（audit-platform/frontend/src/services/apiPaths.ts）

```typescript
export const yourModule = {
  list: '/api/your-module',
  detail: (id: string) => `/api/your-module/${id}`,
  create: '/api/your-module',
} as const
```

并添加到底部 `API` 聚合导出对象中。

---

## 3. 前端 Service 调用（audit-platform/frontend/src/services/yourModuleApi.ts）

```typescript
import http from '@/utils/http'
import { yourModule as P } from './apiPaths'

export async function getItems() {
  const { data } = await http.get(P.list)
  return data
}

export async function getItem(id: string) {
  const { data } = await http.get(P.detail(id))
  return data
}
```

---

## 验证清单

- [ ] 后端路由已注册到 `router_registry.py`
- [ ] `apiPaths.ts` 已添加路径定义
- [ ] 前端 service 使用 apiPaths 常量（不硬编码）
- [ ] `node scripts/dead-link-check.js` 通过
- [ ] `npx vue-tsc --noEmit` 零错误
- [ ] `docs/API_CHANGELOG.md` 已更新
