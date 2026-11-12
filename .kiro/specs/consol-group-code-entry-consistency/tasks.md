# 三码入口一致与改上级并发保护 — 任务

需求 `requirements.md` R1~R8；设计 `design.md`。按交付单元分批，每批独立可验证。验证在「最新 HEAD + 本 spec 改动」的干净分离头 worktree（仓库根 `tmp_group_code_entry/verify_wt`）上跑；连 PG 的用例显式设 `DATABASE_URL` 指向一次性库，不写共享库。

- [ ] 1. 规范化单一来源（R1；design §2.1、§4）
  - [ ] 1.1 `uscc_validator.py` 新增 `normalize_uscc_input`（NFKC → strip → upper，空串 → None）与 `format_code_error(label, reason)`；`project_creation_grant_service.normalize_company_code` 改为先规范化再校验（授权侧对空值与非法值的原有行为用既有测试钉住）
  - [ ] 1.2 `uscc_test_vectors.json` 增 `normalization` 组；`test_uscc_validator.py` 与 `uscc_validator.spec.ts` 各读一遍，逐条断言规范化结果与校验结论
  - [ ] 1.3 前端 `uscc_validator.ts` 新增 `normalizeUsccInput`；`BasicInfoStep.vue` 三个输入框失焦写回规范化值，三条校验规则对规范化值校验
  - [ ] 1.4 变异：去掉 NFKC、去掉 upper、前端不写回，各须红在向量或组件用例上

- [ ] 2. 写入口改造与报错统一（R1.2、R2.1~R2.4；design §1.1、§3.3）
  - [ ] 2.1 单建（`project_creation_coordinator`）、`create_project`、`normalize_group_fields`、`reparent_project` 与路由 inline strip 统一走规范化；`create_project` 入库写规范值；企业代码报错带字段名
  - [ ] 2.2 `BasicInfoSchema` 三码 `field_validator(mode="before")`；`update_step` 校验失败用中文字段名表
  - [ ] 2.3 `uniqueness_checker.check_uniqueness` 增仅限关键字参数 `exclude_project_id`；`update_step` 在企业代码 / 年度 / 口径变化时校验 USCC + 判唯一，冲突 409
  - [ ] 2.4 批量 `parse_row` 文案改为 `"{字段}：{原因}"`
  - [ ] 2.5 新 `backend/tests/test_group_code_entry_consistency.py`：同一组输入经单建、向导保存、批量预校验、拖拽四入口，结论一致、入库值相同、文案一致；向导改代码撞唯一 → 409
  - [ ] 2.6 变异：任一入口改回不规范化；入库改回原值；批量文案改回「格式错误：」；唯一性判断删除

- [ ] 3. 向导改企业代码：越权、授权与影响检查（R2.5、R2.6、R6；design §1.7、§1.8、§2.5、§2.6、§3.4）
  - [ ] 3.1 向导保存与确认两个路由改 `require_project_access("edit")`，`current_user` 作 `actor` 传入 `update_step`；鉴权基线 `_IDENTITY_ONLY_BASELINE` 按棘轮下调
  - [ ] 3.2 `update_step` 企业代码有变化时在 `prepare_group_fields` 之前依次：授权 → 年度锁后重验 → 唯一性 → 影响检查；`actor is None` 拒绝；403 包装文案；授权快照变化 409
  - [ ] 3.3 新 `services/company_code_change_guard.py`：`code_change_impacts` 五类引用按旧代码、同年度计数（无年度列的表按所属合并项目年度）；有引用 409 `COMPANY_CODE_IN_USE` 带 `impacts`
  - [ ] 3.4 节点身份列登记守卫：ORM 元数据中 `node_key` / `entity_node_key` / `node_company_code` 列须在影响清单或豁免表（附理由）；内置变异
  - [ ] 3.5 前端 `stores/wizard.ts` 的 `saveStep` 增可选 `onForbidden` / `onConflict`；`ProjectWizard.vue` 基本信息保存遇 `COMPANY_CODE_IN_USE` 弹 `ElMessageBox.alert` 列出影响项，遇授权 403 显示原因，表单保留
  - [ ] 3.6 测试：新 `test_wizard_company_code_change.py`（design §5「改代码授权 / 改代码影响 / 节点身份列登记」三行）；`test_project_wizard_router.py` 非成员 403 / 成员通过；前端向导 spec 两种弹窗
  - [ ] 3.7 变异：删授权调用；授权挪到 `prepare_group_fields` 之后（库存查询先于授权的用例须红）；`actor is None` 改放行；影响检查任一类删除；不按年度过滤；路由改回只校登录

- [ ] 4. Excel 模板与读取（R3；design §1.3、§2.4）
  - [ ] 4.1 模板三列数据区 `number_format = "@"`，示例行改文本值；错误明细文件代码列按文本写出读到的原值
  - [ ] 4.2 新 `_code_cell`：数字类型单元格报针对性错误；第二次 `data_only=False` 只读加载、只扫三列，公式且缓存为空的报错
  - [ ] 4.3 `batch_project_export` 删 `group_fields_hash` 回退分支（`action=="update"` 无基线即 `ValueError`）；删除 `group_fields_hash`
  - [ ] 4.4 测试（`test_batch_project_import_closure.py` 增例）：int / float / 公式无缓存 / 公式有缓存 / 文本五种单元格；模板三列格式与示例类型；导出 update 行 hash 等于 `entity_group_fields_hash`
  - [ ] 4.5 变异：数字单元格改回 `str()`；公式无缓存改回当空；恢复旧 hash 回退

- [ ] 5. 拖拽改上级 CAS（R4；design §2.3、§3.1）
  - [ ] 5.1 `UpdateParentCodeRequest.expected_parent_company_code`（按 `model_fields_set` 判是否提供，缺失 428）；`reparent_project(..., expected_parent_code=_UNCHECKED)` 在锁与 refresh 之后比较，不一致 409（dict detail 含当前值）
  - [ ] 5.2 前端 `ConsolidationHub.vue` 拖拽带 `dragData.parentCompanyCode ?? null`；409 走 `consolReparent.ts` 新判定函数，提示并 reload，不重试
  - [ ] 5.3 后端测试：过期期望值 409 且两口径项目库值不变；缺字段 428；null 期望值对无上级项目通过；既有 `test_group_links_reparent.py` / `test_group_links_sync.py` / `test_parent_code_update.py` 的 PATCH 补期望值
  - [ ] 5.4 vitest `ConsolidationHub.reparent.spec.ts`：请求体带期望值；409 提示与 reload；其余错误路径不变
  - [ ] 5.5 变异：删比较；比较挪到加锁之前（并发用例须红）；缺字段改放行；前端不带期望值

- [ ] 6. 重复项目与关系冲突弹窗（R7；design §1.9、§2.7、§3.5）
  - [ ] 6.1 `Diagnostic.project_ids`，`duplicate_project` / `relation_conflict` 填两条记录 id；`consol_group_tree.py` 超 800 行时先拆出诊断类型
  - [ ] 6.2 新 `consolTreeConflicts.ts`（筛选、签名、推送前确认）与 `ConsolTreeConflictDialog.vue`；`ConsolidationIndex.vue` 树加载后按会话签名弹出
  - [ ] 6.3 合并工作台、`ConsolPushPanel.vue`、`ConsolTrialBalanceTab.vue` 三个手工推送入口接推送前确认；公式变更自动推送不接
  - [ ] 6.4 测试：`test_consol_group_tree.py` 两类诊断带真实 id；vitest 弹出 / 去重 / 签名变化再弹 / 「去修改」路由 / 三入口取消不推送、确认推送、取诊断失败照推并提示 / 只有其他诊断不弹
  - [ ] 6.5 变异：推送入口删确认；签名改恒等（变化后不再弹须红）；筛选误纳其他诊断

- [ ] 7. 差额表端点越权（R5；design §1.6、§3.2）
  - [ ] 7.1 `consol_worksheet.py` 的 recalc / pivot / pivot templates 三处加一致性检查，执行统一用 `project_id`
  - [ ] 7.2 新 `backend/tests/test_consol_worksheet_project_scope.py`：三端点 body 与 query 不一致 → 422 且服务函数未被调用；一致时照常调用
  - [ ] 7.3 新 `backend/tests/test_route_body_project_id_consistency.py`：AST 守卫，基线 0；内置变异（临时源码删比较须打红）
  - [ ] 7.4 变异：三端点各删一次比较

- [ ] 8. 回归与门禁
  - [ ] 8.1 后端：本 spec 新增与改动的测试 + 建项 / 批量 / 集团关系 / 授权 / 企业树相关既有测试（`test_group_links*.py`、`test_batch_project_*.py`、`test_parent_code_update.py`、`test_project_wizard_router.py`、`test_project_creation_grant*.py`、`test_uscc_validator.py`、`test_consol_group_tree.py`、`test_project_endpoint_authorization_baseline.py`）；失败项与干净 HEAD 逐节点比对，新增失败 0
  - [ ] 8.2 前端：`uscc_validator.spec.ts`、向导、合并总览、合并工作台、推送面板、合并试算表相关 vitest；改动文件区域 vue-tsc 相对 HEAD 新增 0
  - [ ] 8.3 行数门（design §7）、暂存树自洽检查通过

- [ ] 9. 浏览器实测
  - [ ] 9.1 【测试】项目向导：输入小写、全角、首尾带空格的代码，失焦显示规范值，保存后库值为规范值；实测后复原
  - [ ] 9.2 【测试】经理账号改企业代码：无授权看到授权提示；对有下级的【测试】企业改代码看到影响清单弹窗；无引用的新【测试】项目改代码成功后复原
  - [ ] 9.3 下载模板，用 openpyxl 写入数字类型代码与无缓存公式后导入，预校验列出针对性提示（无 Excel 环境时以此代替手工输入，并在记录里写明）
  - [ ] 9.4 两个标签页打开合并总览，先后拖拽同一节点：后者提示「已被他人调整」并刷新；实测后把上级恢复原值并对账两口径项目
  - [ ] 9.5 `initScript` 拦截企业树接口注入两类诊断：进入合并工作台弹窗、「我知道了」后刷新不再弹、三个推送入口出现确认框
  - [ ] 9.6 在 `http://192.168.20.60:3030` 复测 9.1、9.4、9.5

- [ ] 10. 收尾
  - [ ] 10.1 review 文档 §0.5 / §10 / §10.1 标注 P1-1 / P1-2 / P1-5 的落地方式、拍板结果与 P2-1 / P2-2 不做理由
  - [ ] 10.2 在 `.kiro/specs/INDEX.md` 登记本 spec（基于最新 HEAD 副本只加本行，CRLF 与表格列数校验）
