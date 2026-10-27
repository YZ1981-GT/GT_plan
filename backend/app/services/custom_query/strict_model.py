"""高级查询顶层请求模型的严格基类与 ``acnr_targets`` 共享类型（acnr-foundation-defect-closure T14，design §2.3）。

- ``StrictRequestModel``：请求体含未声明的键 ⇒ 422，中文消息点名该键（原来 pydantic 默认静默丢弃，前端发了
  ``acnr_targets`` 也不报错）。只作用于顶层请求模型（``QueryDSL`` / 业务视图 ``QueryRequest``），嵌套模型不变。
- ``AcnrTargetList``：单项去首尾空白后非空且不超过 512 个字符、条数不超过 ``ACNR_BATCH_LIMIT``（与
  ``/api/acnr/resolve-batch`` 共用）、不去重；不合格 ⇒ ``PydanticCustomError`` 中文消息（FastAPI 422）。
  校验放在这里而不写进路由，路由与各模型只改字段类型（R2-N8）。
"""
from __future__ import annotations

from typing import Annotated, Any

from fastapi import HTTPException
from pydantic import AfterValidator, BaseModel, ConfigDict, TypeAdapter, ValidationError, model_validator
from pydantic_core import PydanticCustomError

from app.services.acnr.limits import ACNR_BATCH_LIMIT

__all__ = [
    "ACNR_TARGET_MAX_CHARS", "AcnrTargetList", "StrictRequestModel", "TemplateConfig", "check_acnr_targets",
    "check_template_config", "template_config_rejected",
]

#: 单个单元格引用的最大字符数（去首尾空白后计）
ACNR_TARGET_MAX_CHARS = 512


class StrictRequestModel(BaseModel):
    """未声明的字段一律拒收（422），消息点名第一个未声明的键。"""

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def _reject_unknown_fields(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        allowed: set[str] = set()
        for name, info in cls.model_fields.items():
            allowed.add(name)
            if info.alias:
                allowed.add(info.alias)
        for key in data:
            if key not in allowed:
                raise PydanticCustomError(
                    "unknown_field", "请求包含未声明的字段「{key}」，已拒绝", {"key": str(key)},
                )
        return data


def check_acnr_targets(targets: list[str]) -> list[str]:
    """``AcnrTargetList`` 的校验函数（模板保存 / 执行也调用它，T15）。原样返回，不去重、不改写。"""
    if len(targets) > ACNR_BATCH_LIMIT:
        raise PydanticCustomError(
            "acnr_targets_too_many", "单次最多选择 {limit} 个单元格，当前 {count} 个",
            {"limit": ACNR_BATCH_LIMIT, "count": len(targets)},
        )
    for pos, item in enumerate(targets, start=1):
        text = item.strip()
        if not text:
            raise PydanticCustomError("acnr_target_empty", "第 {index} 个单元格引用为空", {"index": pos})
        if len(text) > ACNR_TARGET_MAX_CHARS:
            raise PydanticCustomError(
                "acnr_target_too_long", "第 {index} 个单元格引用超过 {max} 个字符",
                {"index": pos, "max": ACNR_TARGET_MAX_CHARS},
            )
    return targets


AcnrTargetList = Annotated[list[str], AfterValidator(check_acnr_targets)]

_TARGETS = TypeAdapter(AcnrTargetList)


def check_template_config(config: dict) -> dict:
    """保存模板时校验 ``config.acnr_targets``（R2-N5 第一道：不合格 422、不入库）；其余键原样，不改写。"""
    raw = config.get("acnr_targets")
    if raw is None:
        return config
    try:
        _TARGETS.validate_python(raw)
    except ValidationError as exc:
        first = exc.errors()[0]
        reason = first["msg"] if first.get("type", "").startswith("acnr_target") else "须为单元格引用文本的列表"
        raise PydanticCustomError(
            "template_acnr_targets_invalid", "模板里的单元格取值目标不合法：{reason}", {"reason": reason},
        ) from None
    return config


#: 模板创建 / 更新请求的 ``config`` 字段类型（路由只改字段类型，R2-N8）
TemplateConfig = Annotated[dict, AfterValidator(check_template_config)]

_TEMPLATE_FIELD_LABELS = {"acnr_targets": "单元格取值目标", "year": "年度", "limit": "每页行数", "offset": "起始行"}


def template_config_rejected(exc: ValidationError) -> HTTPException:
    """执行模板时由模板 config 构造查询请求失败（R2-N5 第二道）⇒ 422，中文点名模板里的非法项，不 500。"""
    problems: list[str] = []
    for err in exc.errors():
        loc = str(err["loc"][0]) if err.get("loc") else "config"
        label = _TEMPLATE_FIELD_LABELS.get(loc, f"字段「{loc}」")
        if err.get("type", "").startswith("acnr_target"):
            problems.append(f"{label}：{err['msg']}")
        elif loc == "year":
            problems.append(f"{label}缺失或不在 2000~2100 之间")
        else:
            problems.append(f"{label}取值不合法")
    return HTTPException(status_code=422, detail={
        "error_code": "TEMPLATE_CONFIG_INVALID", "message": "模板配置不合法，未执行查询：" + "；".join(problems),
    })
