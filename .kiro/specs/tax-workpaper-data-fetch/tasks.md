# 任务：税审底稿取数、公式计算与保存

- [x] 1. 生成脚本产出计算模型与结构化取数规则（R1、design §2§3）
  - [x] 1.1 `backend/scripts/gen/tax_workpaper_rules.py` 解析 202 条规则 → 1,815 个取数项、28 张列表；解析不了即失败点名；纠正 16 条写进模型 `corrections`
  - [x] 1.2 `tax_workpaper_model.py` → `backend/data/tax_workpaper_model.json`（192 个 sheet、8,062 个公式、0 解析失败、0 环）
  - [x] 1.3 前端 `sheets/*.json` 值格带 `ref` / `role` / `fmt`；`--check` exit 0
- [x] 2. 公式引擎 `tax_formula_engine.py` + `tax_workbook.py`（依赖闭包 + 拓扑序；隐式交集）；`test_tax_formula_engine.py`
- [x] 3. 取数 `tax_workpaper_fetch.py` + `tax_workpaper_rule_runner.py`；`test_tax_workpaper_rule_runner.py`
- [x] 4. 存储与接口
  - [x] 4.1 迁移 **V230 / R230**（V211~V219 已被其他分支占用，本地库已应用别分支 V211）+ ORM `TaxWorkpaperInput`；本地库已落表
  - [x] 4.2 `tax_workpaper_service.py`
  - [x] 4.3 router `tax_workpapers.py`（`router_registry/system.py` 注册）；`test_tax_workpaper_api.py`（取数 / 公式 / 保存读回 / 409 / 非法输入 422 / 只读 403 / 非成员 403 / 404）
  - 后端三组测试 51 passed
- [x] 5. 前端
  - [x] 5.1 `apiPaths.taxWorkpapers` + `taxWorkpaperApi.ts`
  - [x] 5.2 `TaxWorkpaperGrid.vue`（显示 / 填写 / 着色 / 悬停规则）+ `TaxWorkpaperSheetPanel.vue`（保存、放弃修改、重新取数、问题列表、版本冲突提示）
  - [x] 5.3 `TaxWorkpaperParamsPanel.vue`（索引页表头信息）；切表时未保存修改二次确认
  - [x] 5.4 eslint / 单区域 vue-tsc 0 错误
- [x] 6. 浏览器实测（四川医药 2025）：3-07-02 明细名称与期末余额取数、悬停规则原文、填写审核调整额 100 → 保存 → 审核确认额重算 1,304.59 → 刷新读回；表头信息默认值与下拉选项；实测写入的 1 行已删除，表恢复 0 行

## 交付勘误 / 范围外
- 「审计调整」「审核调整额」列不自动取数（人工填写），与 R2 一致。
- 四川医药项目大量「未找到明细科目」：该项目客户科目名与样表规则不同（如主营业务成本下无「销售商品」），且有错位导入（应付职工薪酬在账上是 2151 应付工资未映射到 2211）；属数据问题，用户重新导入并改映射后即可取到。
- 导入 / 导出按钮仍不开放；「有 / 无」标记仍存浏览器本地。
