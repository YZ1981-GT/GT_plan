"""`workpaper_sync.adapters` —— 文档无关 adapter protocol 与 fail-closed registry。

spec: `workpaper-html-onlyoffice-bidirectional-writeback-closure` Task 13（Wave 1）

本子包刻意**不**做 re-export：调用方按模块全路径 import
（`from app.services.workpaper_sync.adapters.base import ...`），与父包
`workpaper_sync/__init__.py` 的约定一致。理由是 re-export 会让「谁依赖谁」在
import 图上消失，Wave 3~5 的 adapter 逐 entry 迁移需要精确的辐射面。

* `base.py` —— protocol 与 `SyncContext` / `Projection` / `ProjectionMutation` /
  `MaterializeResult` / `UnmanagedRegionReport` 等文档无关类型；
* `registry.py` —— 启动期 fail-closed registry（matcher 重叠、probe gate、manifest
  profile 交叉校验、伪 bidirectional）。

本 Wave 不放任何 Excel/Word engine：`excel/` 与 `word/` 由 Tasks 36~38 / 59~61
建立，届时才实现 protocol。
"""
