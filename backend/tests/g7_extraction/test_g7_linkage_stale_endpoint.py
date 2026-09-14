"""Wave 5 / Task 6.1 — G7 联动 stale 只读薄端点契约。

Design Decision 6：端点函数体**只委托** `load_linkage_stale_state`，不含任何
映射/计算/查询逻辑（源码断言），权限 readonly。
"""

from __future__ import annotations

import inspect

from app.routers import consol_worksheet_data as mod


def test_stale_endpoint_exists_and_registered():
    assert hasattr(mod, "get_g7_linkage_stale")
    paths = {getattr(r, "path", "") for r in mod.router.routes}
    assert "/api/consol-worksheet-data/g7-linkage/{project_id}/{year}/stale" in paths


def test_stale_endpoint_only_delegates():
    src = inspect.getsource(mod.get_g7_linkage_stale)
    # 唯一实质语句：委托既有 service
    assert "load_linkage_stale_state(db, project_id, year)" in src
    # 端点内不得含映射/计算/直接查询逻辑（避免第二套口径）
    for forbidden in ("db.execute", "for ", "build_", "_load_existing", ".fetchall", "SELECT"):
        assert forbidden not in src, f"stale 端点不应含 `{forbidden}`（应只委托 service）"


def test_stale_endpoint_readonly_permission():
    # readonly 依赖（require_project_access("readonly")）
    sig = inspect.signature(mod.get_g7_linkage_stale)
    user_param = sig.parameters.get("user")
    assert user_param is not None
    # 默认值是 Depends(require_project_access("readonly"))；断言源码声明 readonly
    src = inspect.getsource(mod.get_g7_linkage_stale)
    assert 'require_project_access("readonly")' in src
