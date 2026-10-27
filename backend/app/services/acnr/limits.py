"""ACNR 批量解析 / 取值的共用上限（design §2.3）。

``/api/acnr/resolve-batch`` 与高级查询 ``acnr_targets``（T14）共用，改一处两处同时生效。
"""
from __future__ import annotations

#: 单次请求最多解析 / 取值的地址条数
ACNR_BATCH_LIMIT = 50

#: acnr_targets 整批解析时限（秒）：远低于前端 axios 180 秒超时，且不长时间占用数据库连接（R2-F9）
ACNR_BATCH_DEADLINE_S = 8
