# 设计：附注多表刷新与编辑反写

## 1. 现状确认与方案
- `disclosure_engine._build_table_data` 固定 `tables[0]`；loader 已有按索引接口。增加 keyword-only `table_index=0`，传入 resolver ctx，缺 binding 仍走原 legacy。
- 新增 `_build_section_table_data` 编排所有模板表；generate/get_detail/update 复用。保 seed columns/groups/guidance，按文本推标题，建立首表兼容镜像。
- update 在已有 note/来源判定后构表，扫描所有模板表依赖，公式开关内二遍求值，三态 merge，flush 不 commit。
- `_build_with_binding` 用 label 出现次数解析 `#N`，重复语义选自身 `_col{actual_col}`，不串取其他列。
- prior_year_note 缺显式表号时采用所在表号；显式引用不覆盖。evaluator 当前局部表 ctx 0 不变。

## 2. AR 局部生成（拒绝全库覆写）
- 在现有生成器新增四组 AR 校准入口，仅修改目标 binding.tables。
- 依据当前模板造完整表/列/行，对应旧表按已确认序号映射；只保留可证明适用的 manual 注解、合计注解，并更新几何。
- 不保留以 1122 总额重复填各分桶的 auto 源；无证明的明细列一律 manual，表级/章节级自定义其它字段保留。
- 派生合计按 `_backfill_totals` 现行分段规则重建；检查目标几何及非目标逐值不变；`--check` 不写文件，重复生成无 diff。

## 3. 前端纯投影与显式写入
- `useNoteTableProjection` 保 computed 副本，新增 WeakMap sidecar（投影表 -> 行/值/标签原坐标）；不写 sidecar 到 payload。
- 续表拼接逐行记录准确偏移，主表短行按主值列宽补 null，缺源坐标不可写；不按 header 猜源值下标。
- `sub_table_data` 通过 `_source_sub_table_key` + columns.key + 有效原行序列定位，处理数组和 `{rows}`，列/行不唯一时抛中文定位错误。
- `commitCellValue`/`commitRowLabel` 立即写源；`commitProjectedEdits` 对当前快照先校验所有变化，再批量反写；无变化不修改模式/元数据。
- `getStructureTable` 仅返回一对一普通 raw 表（不是投影）；undo 捕获稳定原对象。跨源续表或业务键子表返回 null，宿主禁用结构按钮并说明。
- 保存 prepare 回调先完成反写；仅发送原始结构。导出勾选按源索引集展开。

## 4. 宿主计算与保护
- 编辑事件使用真实新值且显式反写；纵向合计以 active 表计算，每个结果走 commit，横向公式无合计行也执行。
- 标签同步同一显示行关联的原标签；无法对应的填充空行不能静默写首表。
- 不触碰并行 useAutoSave；draft 仍读已反写原件。自动保存最终也经 prepare 校验。

## 5. 验证设计与风险
- 后端：三表同标签不同 auto 数、不同上年表号、完整 update manual/locked/workpaper、真实四组资源对账、非目标资源不变。
- 前端：纯读旧守卫不反转；非首表/续表/补空行/sub 有效原行、null/0、save raw payload、稳定结构 undo、export 源集合。
- 宿主测试必须验证真实事件接线（Vue 挂载或真实浏览器），不能只测算法拷贝。
- Playwright 所有 API 拦截为合成数据，PUT 只存内存再 GET；保存前保持业务页 blank。
- 主要风险是历史 semantic 污染与自定义模板异形；本轮不自动迁移存量，保持 manual/locked 优先，记录边界。

## 6. 改动成本与收益
- 生产文件预计 5 个（引擎、局部生成器、投影、保存、宿主）+ binding 资源 1 个；测试约 4–6 个，无依赖/迁移。
- 收益：同时堵住首表串取、增量降维、续表与非首表保存丢失；代价：跨源结构编辑暂禁用而非冒险整表覆盖。
- 并行合并节点隔离及共享 useAutoSave 完全排除，不 stash/reset/checkout，不操作业务库、不提交。
