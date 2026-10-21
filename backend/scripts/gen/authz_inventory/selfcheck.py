"""合成样例自检框架（需求 1.6 / 9.8：每次生成或检查前先跑；任一判错即中文列出样例名、期望结果与实际结果）。

样例 = 名称 + 期望结果 + 求实际结果的无参函数（``Sample``）。``run_samples`` 逐个执行、按 ``==`` 比较；样例抛异常
也记为判错，实际结果写异常类型与信息。``ensure_samples`` 有判错即抛 ``SelfCheckFailed``（信息为中文清单），
调用方据此以退出码 1 失败、不写出产物。空样例集与重名样例直接报错 —— 不能让「没跑任何样例」冒充自检通过。

另提供合成源码的识别辅助 ``recognize_source`` / ``summarize``（只做源码识别，不做运行时路由表对账），以及
3 个演示样例 ``DEMO_SAMPLES``：框架自身的可运行示例。附注写端点清册的 9 个样例（需求 1.6，任务 8.2）为
``NOTE_INVENTORY_SAMPLES``：合成源码经 ``gates`` 识别、``classify`` 归类，比对类别、最高级别与识别问题；
9.8 的 10 个样例由影响清单脚本定义（任务 8.4）。在 ``backend/scripts/gen`` 下执行
``python -B -m authz_inventory.selfcheck`` 跑演示样例与附注清册样例。
"""

from __future__ import annotations

import dataclasses
import pprint
import sys
import textwrap
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from . import classify, gates, render

SAMPLE_FILE = "backend/app/routers/selfcheck_sample.py"  # 合成源码的虚拟位置（相对仓库根，不落盘）


@dataclass(frozen=True)
class Sample:
    name: str
    expected: Any
    run: Callable[[], Any]


@dataclass(frozen=True)
class Failure:
    name: str
    expected: Any
    actual: Any

    def message(self) -> str:
        return f"- 样例：{self.name}\n  期望：{_show(self.expected)}\n  实际：{_show(self.actual)}"


class SelfCheckFailed(RuntimeError):
    """内置合成样例自检判错（信息为中文清单）。"""


def _show(value: Any) -> str:
    if isinstance(value, str):
        return repr(value)  # 不折行：异常信息等长文本原样一行
    return pprint.pformat(value, width=110, sort_dicts=True).replace("\n", "\n        ")


def run_samples(samples: Iterable[Sample]) -> tuple[Failure, ...]:
    """逐个执行样例，返回判错的样例（全部按期望时为空）。"""
    items = tuple(samples)
    if not items:
        raise ValueError("自检没有任何样例")
    names = [s.name for s in items]
    repeated = sorted({n for n in names if names.count(n) > 1})
    if repeated:
        raise ValueError("自检样例重名：" + "、".join(repeated))
    failures = []
    for sample in items:
        try:
            actual = sample.run()
        except Exception as exc:  # 样例自身出错也是判错，不中断其余样例
            actual = f"抛出 {type(exc).__name__}：{exc}"
        if actual != sample.expected:
            failures.append(Failure(sample.name, sample.expected, actual))
    return tuple(failures)


def format_failures(failures: Iterable[Failure], total: int, *, title: str = "内置合成样例自检") -> str:
    items = tuple(failures)
    head = f"{title}未通过：{len(items)} / {total} 个样例判错，不写出产物。"
    return "\n".join([head, *(f.message() for f in items)])


def ensure_samples(samples: Iterable[Sample], *, title: str = "内置合成样例自检") -> int:
    """全部按期望时返回样例数；有判错抛 ``SelfCheckFailed``。"""
    items = tuple(samples)
    failures = run_samples(items)
    if failures:
        raise SelfCheckFailed(format_failures(failures, len(items), title=title))
    return len(items)


# ─── 合成源码的识别辅助 ────────────────────────────────────────────────────────


def recognize_source(source: str, function: str, *, file: str = SAMPLE_FILE) -> gates.EndpointGates:
    """在合成源码里识别端点 ``function`` 的第一条路由声明；模块级问题并入结果的 issues。"""
    info = gates.analyze_module(file, textwrap.dedent(source))
    declared = [d for d in info.declared_routes() if d.function == function]
    if not declared:
        raise ValueError(f"合成源码里没有端点 {function}（模块级问题：{[i.message() for i in info.issues]}）")
    result = gates.recognize_endpoint(info, declared[0])
    return dataclasses.replace(result, issues=tuple(info.issues) + result.issues)


def summarize(result: gates.EndpointGates) -> dict[str, Any]:
    """识别结果的比对视图：非中性门禁（名称、来源、级别、条件执行、辅助函数链、参数名、静态参数）、最高级别、问题。"""
    forms = sorted(((u.name, u.via, u.level, u.conditional, u.chain, u.param, u.params)
                    for u in result.uses if u.category != "neutral"), key=repr)
    return {"forms": tuple(forms), "max_level": gates.max_level(result.uses),
            "issues": tuple(sorted((i.kind, i.name) for i in result.issues))}


_HEAD = '''
from fastapi import APIRouter, Depends

from app.deps import get_current_user, require_project_access

router = APIRouter(prefix="/api/selfcheck")
'''

_SIGNATURE_EDIT = _HEAD + '''
@router.post("/{project_id}/signature")
async def endpoint(project_id: str, _=Depends(require_project_access("edit"))):
    return None
'''

_TEXT_ONLY = _HEAD + '''
@router.post("/{project_id}/text-only")
async def endpoint(project_id: str, user=Depends(get_current_user)):
    """require_project_access("edit") 只写在 docstring 里。"""
    # await assert_project_permission(db, user, project_id, "edit")  —— 只在注释里
    text = 'Depends(require_project_access("edit"))'
    return text
'''

_UNKNOWN_DEPENDENCY = _HEAD + '''
from app.somewhere import load_tenant


@router.post("/{project_id}/unknown")
async def endpoint(project_id: str, tenant=Depends(load_tenant)):
    return tenant
'''


def _demo(source: str) -> Callable[[], dict[str, Any]]:
    return lambda: summarize(recognize_source(source, "endpoint"))


DEMO_SAMPLES = (
    Sample('签名依赖 require_project_access("edit")（参数名为 _）',
           {"forms": (("require_project_access", "signature", "edit", False, (), "_", ()),),
            "max_level": "edit", "issues": ()}, _demo(_SIGNATURE_EDIT)),
    Sample('只在 docstring、注释与字符串里写有 require_project_access("edit")',
           {"forms": (("get_current_user", "signature", None, False, (), "user", ()),),
            "max_level": None, "issues": ()}, _demo(_TEXT_ONLY)),
    Sample("挂载未登记的依赖 ⇒ 报未识别依赖",
           {"forms": (), "max_level": None, "issues": ((gates.UNKNOWN_DEPENDENCY, "load_tenant"),)},
           _demo(_UNKNOWN_DEPENDENCY)),
)


# ─── 附注写端点清册的自检样例（需求 1.6，任务 8.2）──────────────────────────────

_NOTE_HEAD = '''
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import assert_project_permission, get_current_user, require_project_access
from app.services.note_edit_gate import assert_note_edit_access

router = APIRouter(prefix="/api/selfcheck/{project_id}")
'''

_NO_AUTH = '''
@router.post("/no-auth")
async def endpoint(project_id: str, db: AsyncSession = Depends(get_db)):
    return None
'''

_LOGIN_ONLY = '''
@router.post("/login-only")
async def endpoint(project_id: str, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    return None
'''

_TEXT_ONLY_EDIT = '''
@router.post("/text-only")
async def endpoint(project_id: str, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    """权限：require_project_access("edit")（只写在 docstring 里，签名与函数体都没有挂载）。"""
    # _=Depends(require_project_access("edit"))  —— 只在注释里
    # await assert_project_permission(db, user, project_id, "edit")
    return None
'''

_SIGNATURE_EDIT = '''
@router.post("/signature-edit")
async def endpoint(project_id: str, db: AsyncSession = Depends(get_db), _=Depends(require_project_access("edit"))):
    return None
'''

_HELPER_EDIT = '''
async def _check_project(db, user, project_id, level):
    await assert_project_permission(db, user, project_id, level)


@router.post("/helper-edit")
async def endpoint(project_id: str, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    await _check_project(db, user, project_id, "edit")
    return None
'''

_NOTE_GATE = '''
@router.post("/note-edit-gate")
async def endpoint(project_id: str, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    await assert_note_edit_access(db, user, project_id, consol_lock=False)
    return None
'''

_SIGNATURE_READONLY = '''
@router.post("/signature-readonly")
async def endpoint(project_id: str, db: AsyncSession = Depends(get_db), _=Depends(require_project_access("readonly"))):
    return None
'''

_NOT_IMPLEMENTED = '''
@router.post("/not-implemented")
async def endpoint(project_id: str):
    """尚未实现。"""
    raise HTTPException(status_code=501, detail="功能尚未实现")
'''

_UNREGISTERED = '''
from app.somewhere import load_tenant


@router.post("/unregistered")
async def endpoint(project_id: str, tenant=Depends(load_tenant)):
    return tenant
'''


def _note_view(source: str) -> Callable[[], dict[str, Any]]:
    """合成源码 → 清册的比对视图：类别（不归类为 None）、最高级别、识别问题（种类，名称）。"""

    def run() -> dict[str, Any]:
        result = recognize_source(_NOTE_HEAD + source, "endpoint")
        return {"category": classify.classify(SAMPLE_FILE, result).category, "max_level": gates.max_level(result.uses),
                "issues": tuple(sorted((issue.kind, issue.name) for issue in result.issues))}

    return run


def _expect(category: str | None, max_level: str | None = None,
            issues: tuple[tuple[str, str], ...] = ()) -> dict[str, Any]:
    return {"category": category, "max_level": max_level, "issues": issues}


NOTE_INVENTORY_SAMPLES = (
    Sample("无任何鉴权依赖 → I", _expect("I"), _note_view(_NO_AUTH)),
    Sample("只依赖登录 → I", _expect("I"), _note_view(_LOGIN_ONLY)),
    Sample('只在 docstring 与注释里写有 require_project_access("edit")、签名与函数体都没有挂载 → I',
           _expect("I"), _note_view(_TEXT_ONLY_EDIT)),
    Sample('签名依赖 require_project_access("edit") → E', _expect("E", "edit"), _note_view(_SIGNATURE_EDIT)),
    Sample("函数体经同文件辅助函数以 edit 级判定 → E", _expect("E", "edit"), _note_view(_HELPER_EDIT)),
    Sample("调用附注编辑门禁 → E", _expect("E", "review"), _note_view(_NOTE_GATE)),
    Sample('签名依赖 require_project_access("readonly") → R', _expect("R", "readonly"), _note_view(_SIGNATURE_READONLY)),
    Sample("函数体只抛出「未实现」错误 → S", _expect("S"), _note_view(_NOT_IMPLEMENTED)),
    Sample("挂载未登记的依赖 → 报未识别依赖、不归类",
           _expect(None, issues=((gates.UNKNOWN_DEPENDENCY, "load_tenant"),)), _note_view(_UNREGISTERED)),
)


def main() -> int:
    render.utf8_console()
    for title, samples in (("演示样例自检", DEMO_SAMPLES), ("附注写端点清册内置合成样例自检", NOTE_INVENTORY_SAMPLES)):
        try:
            count = ensure_samples(samples, title=title)
        except SelfCheckFailed as exc:
            print(exc, file=sys.stderr)
            return 1
        print(f"{title}通过：{count} 个样例全部按期望")
    return 0


if __name__ == "__main__":
    sys.exit(main())
