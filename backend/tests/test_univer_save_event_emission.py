"""univer-save WORKPAPER_SAVED 事件发布契约回归测试（2026-06-12 修复）。

根因：`working_paper.save_univer_data` 第 7 步"事件发布（触发五环联动）"
早期把裸 dict 传给 `event_bus.publish()`，且包在 `asyncio.create_task(...)`
+ `try/except: pass` 中：
- publish 内 `_build_dedup_key` 访问 `.event_type` → dict 无此属性 → AttributeError
- create_task 中抛出的异常无处捕获，连 except 都进不去 → 静默
结果：Univer 编辑器保存底稿后 WORKPAPER_SAVED **从未真正分发**，
一致性比对 / B51 高风险触发 / 底稿域地址失效 / prefill stale 全部失联。

修复：改用真实 `EventPayload`，并从项目 audit_period_end 推导 year
（year-dependent handler 如 B514/B515/H-lease/I-RD 依赖 payload.year）。

本测试用源码静态检查守护契约（HTTP 全链路需重型 fixture，单测守发布形态最稳）。
"""
from __future__ import annotations

import inspect

from app.routers import working_paper


def _save_univer_source() -> str:
    return inspect.getsource(working_paper.save_univer_data)


def test_publish_uses_event_payload_not_dict():
    """事件发布必须构建 EventPayload，禁止裸 dict。"""
    src = _save_univer_source()
    # 必须导入并构建 EventPayload
    assert "EventPayload(" in src, "univer-save 必须用 EventPayload 构建事件"
    assert "event_type=EventType.WORKPAPER_SAVED" in src
    # 禁止回退到裸 dict 形态（旧 bug 特征：'event_type': "WORKPAPER_SAVED" 字符串键）
    assert '"event_type": "WORKPAPER_SAVED"' not in src, (
        "检测到裸 dict 事件载荷残留（旧 bug 形态）"
    )


def test_publish_derives_year():
    """必须从项目推导 year 并传入 payload（year-dependent handler 依赖）。"""
    src = _save_univer_source()
    assert "year=saved_year" in src, "WORKPAPER_SAVED payload 必须携带推导的 year"
    assert "audit_period_end" in src, "year 应从 Project.audit_period_end 推导"


def test_publish_failure_is_logged_not_silently_passed():
    """发布失败必须记录日志，不再 except: pass 静默吞掉。"""
    src = _save_univer_source()
    # except 分支必须 warning 记录，而非裸 pass
    assert "WORKPAPER_SAVED 事件发布失败" in src, (
        "发布失败必须记录 warning，禁止静默 except: pass"
    )


def test_payload_carries_required_extra_fields():
    """payload.extra 必须含 wp_id（下游 handler 读取键）。"""
    src = _save_univer_source()
    assert '"wp_id": str(wp_id)' in src
    assert '"trigger": "univer_save"' in src
