# 旧制度损益科目自动映射到新准则 6xxx — 任务

- [x] 1. 新模块 `legacy_pl_crosswalk.py`：两张对照表 + 判定 + 取目标码（R1 / R2）
- [x] 2. `mapping_service` 接线：`auto_suggest` 判定一次、`_match_single` 优先查对照表，目标码缺失回退（R1 / R3）；登记行数白名单（1035）
- [x] 3. 映射页匹配方式中文名（R4；顺带补「坏账二级」）
- [x] 4. 测试 `test_legacy_pl_crosswalk.py` 22 例；内存变异 4 条（去新准则排除 / 去最少命中数 / 不传对照表 / 对照值改错）全部打红、对照组全绿
- [x] 5. 存量修复：两个项目各 69 行，只读清单 → 备份 → 改映射 → 全量重算 → 核对利润表（R5，见 design §6；一次性脚本已删）
- [x] 6. （实施中发现）报表合计行排在明细前恒 0：`report_row_order.evaluation_order` 接入报表引擎四处求值循环（design §5）；
       测试 `test_report_row_order.py` 6 例，变异 3 条（改回按行号 / 不认 SUM_ROW / 输出不恢复行号顺序）全部打红
- [ ] 7. 浏览器实测：账务查询利润表、试算平衡表、映射页「旧制度对照」标签（待后端重启）

验收记录：引用报表引擎 / 映射 / 试算表的 25 个测试文件 468 passed、15 failed；15 个全部是改前已有的失败
（`test_mapping_service` 2 例在改动前基线即红；`test_audit_report` 3 + `test_cfs_worksheet` 10 在干净检出 HEAD 上逐条同红）。
