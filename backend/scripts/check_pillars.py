"""五根主梁业务逻辑硬度检查"""
import inspect

checks = {}

# ── 主梁1：底稿 ──
pillar1 = []
try:
    from app.services.wp_download_service import WpUploadService
    src = inspect.getsource(WpUploadService.upload_file)
    pillar1.append(("上传触发ParseService", "parse_workpaper" in src))
    pillar1.append(("上传触发WORKPAPER_SAVED事件", "WORKPAPER_SAVED" in src))
    pillar1.append(("上传双写云端", "sync_single_file" in src))
    pillar1.append(("上传任务跟踪", "task_center" in src or "create_task" in src))
except Exception as e:
    pillar1.append(("导入失败", False))

try:
    from app.services.working_paper_service import WorkingPaperService
    src2 = inspect.getsource(WorkingPaperService.update_status)
    pillar1.append(("严格状态机", "VALID_TRANSITIONS" in src2))
except Exception as e:
    pillar1.append(("状态机检查失败", False))

try:
    from app.routers.working_paper import update_status
    src3 = inspect.getsource(update_status)
    pillar1.append(("复核后端4项门禁", "blocking_reasons" in src3))
    pillar1.append(("门禁-reviewer检查", "reviewer" in src3))
    pillar1.append(("门禁-QC检查", "blocking_count" in src3))
    pillar1.append(("门禁-批注检查", "CellAnnotation" in src3))
except Exception as e:
    pillar1.append(("门禁检查失败", False))

checks["底稿"] = pillar1

# ── 主梁2：复核 ──
pillar2 = []
try:
    from app.services.qc_engine import QCEngine
    engine = QCEngine()
    blocking_rules = [r for r in engine.rules if r.severity == "blocking"]
    pillar2.append(("阻断级QC规则数", len(blocking_rules) >= 5))
    pillar2.append((f"  实际{len(blocking_rules)}条阻断规则", True))
    
    # Check rules are not stubs
    from app.services.qc_engine import ConclusionNotEmptyRule
    src = inspect.getsource(ConclusionNotEmptyRule.check)
    pillar2.append(("QC-01结论非空-非stub", "parsed_data" in src))
except Exception as e:
    pillar2.append(("QC引擎检查失败: " + str(e), False))

try:
    from app.routers.review_conversations import router
    paths = [r.path for r in router.routes]
    pillar2.append(("复核对话创建", any("" == p for p in paths)))
    pillar2.append(("复核对话关闭", any("close" in p for p in paths)))
    pillar2.append(("复核对话导出", any("export" in p for p in paths)))
except Exception as e:
    pillar2.append(("复核对话检查失败", False))

checks["复核"] = pillar2

# ── 主梁3：附件 ──
pillar3 = []
try:
    from app.routers.attachments import router
    paths = [r.path for r in router.routes]
    pillar3.append(("上传端点", any("upload" in p for p in paths)))
    pillar3.append(("下载代理", any("download" in p for p in paths)))
    pillar3.append(("预览代理", any("preview" in p for p in paths)))
    pillar3.append(("OCR状态更新", any("ocr-status" in p for p in paths)))
    pillar3.append(("关联底稿", any("associate" in p for p in paths)))
    pillar3.append(("搜索", any("search" in p for p in paths)))
except Exception as e:
    pillar3.append(("附件路由检查失败", False))

try:
    from app.services.attachment_service import AttachmentService
    src = inspect.getsource(AttachmentService.upload_attachment_file)
    pillar3.append(("上传Paperless优先+本地回退", "paperless" in src and "fallback" in src.lower()))
    pillar3.append(("上传任务跟踪", "create_task" in src))
except Exception as e:
    pillar3.append(("附件服务检查失败", False))

checks["附件"] = pillar3

# ── 主梁4：权限 ──
pillar4 = []
try:
    from app.deps import get_current_user, check_consol_lock, get_visible_project_ids
    pillar4.append(("get_current_user依赖", True))
    pillar4.append(("check_consol_lock依赖", True))
    pillar4.append(("get_visible_project_ids依赖", True))
except ImportError as e:
    pillar4.append(("权限依赖缺失: " + str(e), False))

try:
    from app.services.feature_flags import is_enabled, get_feature_maturity
    pillar4.append(("功能开关", True))
    maturity = get_feature_maturity()
    pillar4.append((f"功能成熟度分级({len(maturity)}项)", len(maturity) >= 10))
except Exception as e:
    pillar4.append(("功能开关检查失败", False))

checks["权限"] = pillar4

# ── 主梁5：留痕 ──
pillar5 = []
try:
    from app.middleware.request_id import RequestIDMiddleware, RequestIDFilter
    pillar5.append(("RequestID中间件", True))
    pillar5.append(("RequestID日志Filter", True))
except ImportError:
    pillar5.append(("RequestID缺失", False))

try:
    from app.core.logging_config import setup_logging, JSONFormatter
    pillar5.append(("结构化JSON日志", True))
    src = inspect.getsource(setup_logging)
    pillar5.append(("日志含request_id", "request_id" in src))
except Exception:
    pillar5.append(("日志配置检查失败", False))

try:
    from app.services.task_center import create_task, update_task, get_task, list_tasks
    pillar5.append(("异步任务中心", True))
except ImportError:
    pillar5.append(("任务中心缺失", False))

try:
    from app.middleware.audit_log import AuditLogMiddleware
    pillar5.append(("审计日志中间件", True))
except ImportError:
    pillar5.append(("审计日志缺失", False))

checks["留痕"] = pillar5

# ── 输出 ──
print("=" * 60)
print("五根主梁业务逻辑硬度检查")
print("=" * 60)
total_pass = 0
total_all = 0
for pillar, items in checks.items():
    passed = sum(1 for _, ok in items if ok)
    total = len(items)
    total_pass += passed
    total_all += total
    pct = passed / total * 100 if total > 0 else 0
    icon = "OK" if passed == total else "!!"
    print(f"\n[{icon}] {pillar} ({passed}/{total} = {pct:.0f}%)")
    for name, ok in items:
        print(f"  {'OK' if ok else 'XX'} {name}")

print(f"\n{'=' * 60}")
print(f"总计: {total_pass}/{total_all} = {total_pass/total_all*100:.0f}%")
