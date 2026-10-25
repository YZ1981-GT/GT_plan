"""公式推送引擎（spec chain-closure-phase2-formula-push-engine）。

四表 / 试算表 / 调整分录大厅的数据经公式内核推送到底稿与附注；E1 货币资金为首个 binding。

子模块：
* ``policy``      —— 三态判定纯函数（写 / 保留 / 待确认）
* ``rules``       —— 声明式推送规则清单加载与校验（``backend/data/formula_push_rules.json``）
* ``sources``     —— 公式上下文取数（试算表审定口径 / 大厅已确认调整，按标准码前缀与报表同口径）
* ``bindings``    —— 各底稿的取数、目标展开与写入叠加层（``e1`` + 纯计算 ``e1_calc``）
* ``note_writer`` —— 附注主表单元格定位与读写（口径对齐 ``note_sub_table_projector``）
* ``engine``      —— ``run`` / ``run_and_commit``：判定 → 写底稿（CAS）→ 写附注 → 状态与运行记录 → SSE
* ``results``     —— 运行结果数据类（纯数据，试跑回滚后仍可读）
* ``panel``       —— 公式管理面板操作：采用公式值 / 锁定 / 查询视图
* ``triggers``    —— ``TRIAL_BALANCE_UPDATED`` / ``WORKPAPER_SAVED(E1)`` 事件注册
"""
