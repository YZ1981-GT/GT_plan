# 任务：合并自动建树范围外问题收口

> 每个任务完成须有代码 + 测试通过证据。B1 后端鉴权 → B2 状态名 → B3 合并范围 → B4 验收。

## B1 后端鉴权与读法

- [x] 1. 报表域端点改项目级（R1.1 / R1.3）
  - `reports.py` 3、`report_line_mapping.py` 10、`report_related_workpapers.py` 1、`report_export.py` 1、`report_mapping.py` 3、`wp_report_analysis.py` 6；读 readonly、写 edit
- [x] 2. 请求体项目与第二个项目（R1.2 / R2）
  - 生成报表 `assert_project_permission(edit)`；期初核对上年项目、参照复制来源项目 readonly + RLS 设回；`deps.readable_project_ids`；行次映射参照复制按 `client_name` / 按来源项目 id、去掉任意项目退路；列映射可参照项目过滤、复制校验来源、保存 / 复制真落库；前端两个参照入口
- [x] 3. `require_operation` 归档守卫与成员校验（R3）
  - 依赖内归档守卫 → 矩阵 → `assert_project_permission(readonly)`；改写 `test_require_operation.py` 与集成用例
- [x] 4. 端点级测试与基线（R1.4 / R3.3）
  - 权限世界表驱动（非成员 403 + 门禁执行、只读成员拦写、按级别放行、定级表核对）；三维基线下调并钉住；`require_operation` 口径可伪证、请求体维不认它
- [x] 4a. 向导基本信息读法（R6）
  - `wizard_basic_info_data`；`derive_from_wizard`、模板填充回退、试算平衡表汇总；向导确认保持准则的测试

## B2 状态名

- [x] 5. 调整分录状态名一致（R4）
  - 状态机状态 / 动作名；底稿侧集中登记标签派生自常量；后端与前端守卫（含直读字典）

## B3 合并范围

- [x] 6. 合并范围成员读企业树（R5.1）
  - `consol_scope_members.tree_subsidiaries`；附注正文变量、程序表取数改读；测试
- [x] 7. 合并总览改提示树版本（R5.2）
  - `ConsolidationHub` 读预览、提示、打开树版本弹窗、拖拽后重读；vitest
- [x] 8. 删除旧范围校对 / 同步（R5.3）
  - 路由、服务、测试；台账与鉴权清单重生成

## B4 验收

- [x] 9. 回归、静态检查与变异
  - 后端 / 前端回归与 HEAD 逐条比；单区域 vue-tsc；行数门；磁盘变异逐条打红并逐字节恢复
  - 结果见 design §4：最终 HEAD 上后端 224 个文件、前端 159 个 spec 新增失败 0；vue-tsc 0（埋错两处都报）；变异 47 条全部打红
- [x] 10. 浏览器实测与收尾
  - 合并总览提示与弹窗、报表页、参照复制；INDEX / memory；提交只含本 spec 改动块并推送
  - 浏览器实测另修 1 处：试算表「参照其他单位」来源下拉列出了本项目（选了只会 400）
