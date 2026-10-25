# Design Document

## Preserved business model
D4-29 为客户粒度 `D4-29-rows`；D4-30 为 `{customers,customDimensions}` 转置矩阵；D4-31 为单份 `InterviewData` 问卷，保留多选数组 `q1_relation` 与四章节；D4-32 为六组 `GroupData` 流水。源 xlsx 逐 sheet 核定后才能确定列头和稳定 row/column ids。

## Architecture
IO 使用 `_d4_import_export.py` 专用 parser/exporter 与正确 item_id 映射，前端使用 `useD4ImportExport`。D4-29 的客户导入必须先核定 D4-2/D4-3 的真实客户明细来源，禁止沿用错误的 `D2-detail-rows` 路径或产品汇总替代客户粒度。D4-30 维度列与 customDimensions 合并保留；D4-31 单行 gate 保留问卷结构和 q1_relation 数组；D4-32 通过显式分组列恢复六组，未知值进入人工映射。

公式由 F-SHELL effective definition 统一治理，preset/custom 可编辑 expression/refs/params；后端权威执行，前端预览，Excel 投影同声明。统一平台 mutation、sync、三方合并、contract/representation/durable ack。IPO 风险先形成发现记录，人工确认方向/金额/证据后才调用 `useD4InspectionWriteback`；A13 与 D4-1 说明使用独立持久 ack、source identity、去重、重试和防回环。

## Boundaries
不得把整笔客户收入、资金流水或 amount=0 描述项自动推 A13；不得把 reason/“否”非空当异常；不得猜未知分组/科目；不得丢动态 id、问卷多选或自定义维度；不得以 A13 代替双模式同步或以 Excel 优先。
