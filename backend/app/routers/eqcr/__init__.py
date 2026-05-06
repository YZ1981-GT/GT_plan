"""EQCR 工作台路由包

将原 eqcr.py（71KB, 38 端点）按业务域拆分为子模块，
通过本 __init__.py 统一导出 router 对象。

路由前缀：/api/eqcr（与拆分前一致，所有端点 URL 不变）。
"""

from fastapi import APIRouter

from .workbench import router as workbench_router
from .opinions import router as opinions_router
from .notes import router as notes_router
from .related_parties import router as related_parties_router
from .shadow_compute import router as shadow_compute_router
from .gate import router as gate_router
from .memo import router as memo_router
from .time_tracking import router as time_tracking_router
from .independence import router as independence_router
from .prior_year import router as prior_year_router
from .metrics import router as metrics_router
from .constants import router as constants_router

# Re-export schemas for backward compatibility with tests
from .schemas import (  # noqa: F401
    EqcrOpinionCreate,
    EqcrOpinionUpdate,
    ShadowComputeRequest,
    EqcrApproveRequest,
    EqcrUnlockOpinionRequest,
    EqcrNoteCreate,
    EqcrNoteUpdate,
    RelatedPartyCreate,
    RelatedPartyUpdate,
    RelatedPartyTransactionCreate,
    RelatedPartyTransactionUpdate,
    EqcrMemoSaveRequest,
    EqcrTimeTrackStartRequest,
    EqcrTimeTrackStopRequest,
    AnnualDeclarationSubmitRequest,
    LinkPriorYearRequest,
    VALID_RELATION_TYPES,
    VALID_TRANSACTION_TYPES,
    WRITABLE_PROJECT_ROLES,
)

# Re-export endpoint functions for backward compatibility with tests
from .notes import (  # noqa: F401
    list_eqcr_notes,
    create_eqcr_note,
    update_eqcr_note,
    delete_eqcr_note,
    share_note_to_team,
)
from .workbench import list_my_eqcr_projects, get_eqcr_project_overview  # noqa: F401
from .opinions import (  # noqa: F401
    get_eqcr_materiality,
    get_eqcr_estimates,
    get_eqcr_related_parties,
    get_eqcr_going_concern,
    get_eqcr_opinion_type,
    create_eqcr_opinion,
    update_eqcr_opinion,
)
from .shadow_compute import eqcr_shadow_compute, list_shadow_computations  # noqa: F401
from .gate import eqcr_approve, eqcr_unlock_opinion  # noqa: F401
from .memo import generate_eqcr_memo, preview_eqcr_memo, save_eqcr_memo, finalize_eqcr_memo  # noqa: F401
from .time_tracking import eqcr_time_track_start, eqcr_time_track_stop, eqcr_time_summary  # noqa: F401
from .independence import check_annual_declaration, get_annual_questions, submit_annual_declaration  # noqa: F401
from .prior_year import get_prior_year_comparison, link_prior_year, get_eqcr_component_auditors  # noqa: F401
from .metrics import get_eqcr_metrics  # noqa: F401

router = APIRouter(prefix="/api/eqcr", tags=["eqcr"])

router.include_router(workbench_router)
router.include_router(opinions_router)
router.include_router(notes_router)
router.include_router(related_parties_router)
router.include_router(shadow_compute_router)
router.include_router(gate_router)
router.include_router(memo_router)
router.include_router(time_tracking_router)
router.include_router(independence_router)
router.include_router(prior_year_router)
router.include_router(metrics_router)
router.include_router(constants_router)
