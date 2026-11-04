# 任务

- [x] 1. 后端拆差额来源：`fs_balance_sources.py`（期末 / 上年年末两列，各项之和 = 差额、残差单列）；`financial_statements` 接 `checks[].sources` 与 `notice_sources`，受限成员 / 导出不算
- [x] 2. 后端测试：余额表与序时账不一致 + 未映射两源各自金额且合计 = 差额；无序时账指到页；手工修改；受限成员无来源；ABC餐饮真实数据只读核对
- [x] 3. 前端：类型 + `fsIssueSources.ts::sourceLink` + `CitarFsIssueSources.vue`，单体财务报表页接线（离开前未保存确认、提示类按钮改用 `notice_sources`）
- [x] 4. 源头页定位：`useCitarRowLocate.ts` + `.citar-located`；账务查询科目余额表、试算平衡表、底稿映射读 `?locate=`
- [x] 5. 前端测试 + ESLint + 单区域类型检查
- [x] 6. 浏览器实测（ABC餐饮_2025）：期末不平 → 5801 行高亮；序时账按 5801 筛选

## 执行记录（2026-11-04）
- 后端 `test_tax_assurance_api.py` + `test_tax_assurance_rules.py` 50 passed（新增 4 例：两源合计 = 差额 / 无序时账 / 系数 / 手工修改来源）
- 前端 `src/citar` 31 passed（新增 `citarSourceLocate.spec.ts` 5 例、定位用例 +1）；ESLint、单区域 vue-tsc 无报错
- ABC餐饮_2025 真实接口：期末 −11,340.42 拆出唯一来源「科目余额表本期发生额与序时账不一致：5801 以前年度损益调整 −11,340.42」，无残差；
  无头浏览器：点开到账务查询科目余额表 5801 行高亮并滚入可视区；「看序时账」显示该科目 0 条分录；试算平衡表 `?locate=6901`、底稿映射 `?locate=5801` 均定位
- 发现未改：科目余额表页 5801 期末列显示「借 11,340.42」，按期初 + 借 − 贷应为贷方（存储为负数 + 贷方方向，页面 `side()` 再翻一次方向）
