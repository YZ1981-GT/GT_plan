# 三码入口一致与改上级并发保护 — 任务

需求 `requirements.md` R1~R8；设计 `design.md`。按交付单元分批，每批独立可验证。验证在「最新 HEAD + 本 spec 改动」的干净分离头 worktree（仓库根 `tmp_group_code_entry/verify_wt`）上跑；连 PG 的用例显式设 `DATABASE_URL` 指向一次性库，不写共享库。

- [x] 1. 规范化单一来源（R1；design §2.1、§4）
  - [x] 1.1 `uscc_validator.py` 新增 `normalize_uscc_input`（NFKC → strip → upper，空串 → None）与 `format_code_error(label, reason)`；`project_creation_grant_service.normalize_company_code` 改为先规范化再校验（授权侧对空值与非法值的原有行为用既有测试钉住）
  - [x] 1.2 `uscc_test_vectors.json` 增 `normalization` 组；`test_uscc_validator.py` 与 `uscc_validator.spec.ts` 各读一遍，逐条断言规范化结果与校验结论
  - [x] 1.3 前端 `uscc_validator.ts` 新增 `normalizeUsccInput`；`BasicInfoStep.vue` 三个输入框失焦写回规范化值，三条校验规则对规范化值校验
  - [x] 1.4 变异：去掉 NFKC、去掉 upper、前端不写回，各须红在向量或组件用例上

- [x] 2. 写入口改造与报错统一（R1.2、R2.1~R2.4；design §1.1、§3.3）
  - [x] 2.1 单建（`project_creation_coordinator`）、`create_project`、`normalize_group_fields`、`reparent_project` 与路由 inline strip 统一走规范化；`create_project` 入库写规范值；企业代码报错带字段名
  - [x] 2.2 `BasicInfoSchema` 三码 `field_validator(mode="before")`；`update_step` 校验失败用中文字段名表
  - [x] 2.3 `uniqueness_checker.check_uniqueness` 增仅限关键字参数 `exclude_project_id`；`update_step` 在企业代码 / 年度 / 口径变化时校验 USCC + 判唯一，冲突 409
  - [x] 2.4 批量 `parse_row` 文案改为 `"{字段}：{原因}"`
  - [x] 2.5 新 `backend/tests/test_group_code_entry_consistency.py`：同一组输入经单建、向导保存、批量预校验、拖拽四入口，结论一致、入库值相同、文案一致；向导改代码撞唯一 → 409
  - [x] 2.6 变异：任一入口改回不规范化；入库改回原值；批量文案改回「格式错误：」；唯一性判断删除

- [x] 3. 向导改企业代码：越权、授权与影响检查（R2.5、R2.6、R6；design §1.7、§1.8、§2.5、§2.6、§3.4）
  - [x] 3.1 向导保存与确认两个路由改 `require_project_access("edit")`，`current_user` 作 `actor` 传入 `update_step`；鉴权基线 `_IDENTITY_ONLY_BASELINE` 按棘轮下调
  - [x] 3.2 `update_step` 企业代码有变化时在 `prepare_group_fields` 之前依次：授权 → 年度锁后重验 → 唯一性 → 影响检查；`actor is None` 拒绝；403 包装文案；授权快照变化 409
  - [x] 3.3 新 `services/company_code_change_guard.py`：`code_change_impacts` 五类引用按旧代码、同年度计数（无年度列的表按所属合并项目年度）；有引用 409 `COMPANY_CODE_IN_USE` 带 `impacts`
  - [x] 3.4 节点身份列登记守卫：ORM 元数据中 `node_key` / `entity_node_key` / `node_company_code` 列须在影响清单或豁免表（附理由）；内置变异
  - [x] 3.5 前端 `stores/wizard.ts` 的 `saveStep` 增可选 `onForbidden` / `onConflict`；`ProjectWizard.vue` 基本信息保存遇 `COMPANY_CODE_IN_USE` 弹 `ElMessageBox.alert` 列出影响项，遇授权 403 显示原因，表单保留
  - [x] 3.6 测试：新 `test_wizard_company_code_change.py`（design §5「改代码授权 / 改代码影响 / 节点身份列登记」三行）；`test_project_wizard_router.py` 非成员 403 / 成员通过；前端向导 spec 两种弹窗
  - [x] 3.7 变异：删授权调用；授权挪到 `prepare_group_fields` 之后（库存查询先于授权的用例须红）；`actor is None` 改放行；影响检查任一类删除；不按年度过滤；路由改回只校登录

- [x] 4. Excel 模板与读取（R3；design §1.3、§2.4）
  - [x] 4.1 模板三列数据区 `number_format = "@"`，示例行改文本值；错误明细文件代码列按文本写出读到的原值
  - [x] 4.2 新 `_code_cell`：数字类型单元格报针对性错误；第二次 `data_only=False` 只读加载、只扫三列，公式且缓存为空的报错
  - [x] 4.3 `batch_project_export` 删 `group_fields_hash` 回退分支（`action=="update"` 无基线即 `ValueError`）；删除 `group_fields_hash`
  - [x] 4.4 测试（`test_batch_project_import_closure.py` 增例）：int / float / 公式无缓存 / 公式有缓存 / 文本五种单元格；模板三列格式与示例类型；导出 update 行 hash 等于 `entity_group_fields_hash`
  - [x] 4.5 变异：数字单元格改回 `str()`；公式无缓存改回当空；恢复旧 hash 回退

- [x] 5. 拖拽改上级 CAS（R4；design §2.3、§3.1）
  - [x] 5.1 `UpdateParentCodeRequest.expected_parent_company_code`（按 `model_fields_set` 判是否提供，缺失 428）；`reparent_project(..., expected_parent_code=_UNCHECKED)` 在锁与 refresh 之后比较，不一致 409（dict detail 含当前值）
  - [x] 5.2 前端 `ConsolidationHub.vue` 拖拽带 `dragData.parentCompanyCode ?? null`；409 走 `consolReparent.ts` 新判定函数，提示并 reload，不重试
  - [x] 5.3 后端测试：过期期望值 409 且两口径项目库值不变；缺字段 428；null 期望值对无上级项目通过；既有 `test_group_links_reparent.py` / `test_group_links_sync.py` / `test_parent_code_update.py` 的 PATCH 补期望值
  - [x] 5.4 vitest `ConsolidationHub.reparent.spec.ts`：请求体带期望值；409 提示与 reload；其余错误路径不变
  - [x] 5.5 变异：删比较；比较挪到加锁之前（并发用例须红）；缺字段改放行；前端不带期望值

- [x] 6. 重复项目与关系冲突弹窗（R7；design §1.9、§2.7、§3.5）
  - [x] 6.1 `Diagnostic.project_ids`，`duplicate_project` / `relation_conflict` 填两条记录 id；`consol_group_tree.py` 超 800 行时先拆出诊断类型
  - [x] 6.2 新 `consolTreeConflicts.ts`（筛选、签名、推送前确认）与 `ConsolTreeConflictDialog.vue`；`ConsolidationIndex.vue` 树加载后按会话签名弹出
  - [x] 6.3 合并工作台、`ConsolPushPanel.vue`、`ConsolTrialBalanceTab.vue` 三个手工推送入口接推送前确认；公式变更自动推送不接
  - [x] 6.4 测试：`test_consol_group_tree.py` 两类诊断带真实 id；vitest 弹出 / 去重 / 签名变化再弹 / 「去修改」路由 / 三入口取消不推送、确认推送、取诊断失败照推并提示 / 只有其他诊断不弹
  - [x] 6.5 变异：推送入口删确认；签名改恒等（变化后不再弹须红）；筛选误纳其他诊断

- [x] 7. 差额表端点越权（R5；design §1.6、§3.2）
  - [x] 7.1 `consol_worksheet.py` 的 recalc / pivot / pivot templates 三处加一致性检查，执行统一用 `project_id`
  - [x] 7.2 新 `backend/tests/test_consol_worksheet_project_scope.py`：三端点 body 与 query 不一致 → 422 且服务函数未被调用；一致时照常调用
  - [x] 7.3 新 `backend/tests/test_route_body_project_id_consistency.py`：AST 守卫，基线 0；内置变异（临时源码删比较须打红）
  - [x] 7.4 变异：三端点各删一次比较

- [x] 8. 回归与门禁
  - [x] 8.1 后端：本 spec 新增与改动的测试 + 建项 / 批量 / 集团关系 / 授权 / 企业树相关既有测试（`test_group_links*.py`、`test_batch_project_*.py`、`test_parent_code_update.py`、`test_project_wizard_router.py`、`test_project_creation_grant*.py`、`test_uscc_validator.py`、`test_consol_group_tree.py`、`test_project_endpoint_authorization_baseline.py`）；失败项与干净 HEAD 逐节点比对，新增失败 0
  - [x] 8.2 前端：`uscc_validator.spec.ts`、向导、合并总览、合并工作台、推送面板、合并试算表相关 vitest；改动文件区域 vue-tsc 相对 HEAD 新增 0
  - [x] 8.3 行数门（design §7）、暂存树自洽检查通过

- [x] 9. 浏览器实测
  - [x] 9.1 【测试】项目向导：输入小写、全角、首尾带空格的代码，失焦显示规范值，保存后库值为规范值；实测后复原
    - 环境：前端 `http://127.0.0.1:3030`（chrome-devtools MCP）+ 后端 9980（health 200，migration complete，schema_drift critical=0），admin 登录；测试项目 `【测试】三码入口规范化验收有限公司`（id `da1d591e-b0d9-437e-b3d4-114538ab0fac`，年度 2025，单户）。
    - 创建入口（`POST /api/projects`）：企业代码输入 `91330100xgc0000011`（小写）→ 失焦显示 `91330100XGC0000011`；上级代码输入全角 `９１３３０１００ＸＧＣ０００００２４` → 失焦显示 `91330100XGC0000024`；控制方代码输入全角 `９１３３０１００ＸＧＣ０００００３７` → 失焦显示 `91330100XGC0000037`。
    - 首尾空格：写入 ` 91330100xgc0000011 `（20 字符，含首尾空格）后触发真实失焦 → 显示 `91330100XGC0000011`，且未出现「统一社会信用代码必须为 18 位」错误（R2.2：先规范化再判长度成立）。边界说明（如实记录，非缺陷）：三码输入框带 `maxlength="18"`（`b034d2f3c` 之前即有的既有行为），用户逐字键入或粘贴 20 字符时浏览器会先截成 18 字符（实测显示 `" 91330100xgc000001"`），这时尾部校验位被截掉、规范化后判长度错——这是 maxlength 与「18 位定长」共同作用的正常结果；把首尾空格截进来不影响可见行为：一旦值确实以空格开头且被 blur，空格同样被剥掉。
    - 保存入口（`PUT /api/projects/{id}/wizard/basic_info`，从项目列表重进向导 `?projectId=`）：先把三码分别置为「首尾空格+小写」/ 小写 / 全角，真实失焦后三个输入框均显示规范化值（校验错误 0 条），再点「保存」成功跳回项目列表。
    - 库内值（PG `projects`，两次写入后现查）：`company_code='91330100XGC0000011'`、`parent_company_code='91330100XGC0000024'`、`ultimate_company_code='91330100XGC0000037'`；`length()` 均 18，`= btrim(...)` 与 `= upper(...)` 全为 true。
    - 复核：重进向导回填值即规范值；浏览器 console 无与三码 / 规范化相关错误（仅既有 `GtStatusTag` prop 警告）。
    - 复原：`DELETE /api/projects/da1d591e-...` 软删（200 `{"deleted": true}`），现查 `is_deleted=true`、`deleted_at=2026-11-12 14:14:46Z`；三码 live 行数 0、总行数 1（仅该测试项目），全库未删除项目数回到 20，与实测前一致。
    - 探针：`tmp_group_code_entry/gen_codes.py`（生成合法 USCC 码），已用 `tmp_group_code_entry/` 目录承载并清理。
  - [x] 9.2 【测试】经理账号改企业代码：无授权看到授权提示；对有下级的【测试】企业改代码看到影响清单弹窗；无引用的新【测试】项目改代码成功后复原
    - 环境：前端 `http://127.0.0.1:3030`（chrome-devtools MCP）+ 后端 9980（health 200，migration complete，schema_drift critical=0）；全部【测试】数据经平台正式端点创建，未动任何真实业务项目。
    - 场景 A（无授权经理改码 → 授权 403）：账号 `ce_mgr_20261112`（role=manager，停用前 is_active=true；人员档案「【测试】代码入口验收经理」经 `POST /api/users/{id}/staff-binding` 绑定、经 `POST /api/projects/{id}/assignments` 写入本项目 manager/edit 成员行）；授权前提经 admin 的 `GET /api/users/project-creation-grants` 实测确认——全库有效授权 **0 条**，该经理授权列表空。项目 `【测试】代码入口授权验收有限公司_2025`（`ae15992f-6ab8-4642-ac50-6638a8728506`，库值 `9150000FGXUAT4001R`），输入新码 `9150000FGXUAT4002W` → 点「保存」→ `PUT /api/projects/{id}/wizard/basic_info` **403**，响应体 `{"error_code":"COMPANY_CREATION_NOT_AUTHORIZED","message":"修改企业代码需要该代码的建项授权：有 1 个企业代码暂无建项授权，请联系管理员授权"}`；页面 toast 原文「修改企业代码需要该代码的建项授权：有 1 个企业代码暂无建项授权，请联系管理员授权」，表单保留（输入框仍为新码、未跳转）；库值未变（`company_code` 仍 `9150000FGXUAT4001R`、`updated_at` 未变），向导快照 `wizard_state.steps.basic_info.data.company_code` 也仍为旧码。
    - 场景 B（有下级的【测试】企业改码 → 影响清单弹窗）：操作者 admin（partner/admin 直通授权，专注验证影响检查维度，符合 R2.5「只有企业代码要求授权」）。两个【测试】项目临时搭出引用关系：`【测试】代码入口上级验收有限公司_2025`（`ab6c4436-c6bb-4213-b0c4-7402a10ddfbb`，`9150000FGXUAT40030`）为 `【测试】代码入口下级验收有限公司_2025`（`0fee5b84-be6c-4903-a4d5-172e5d493264`，`9150000FGXUAT40043`）的 `parent_company_code` 与 `ultimate_company_code`。改上级码为 `9150000FGXUAT40056` → 保存 → **409**，响应体 `{"error_code":"COMPANY_CODE_IN_USE","message":"企业代码已被以下数据引用，不能直接修改：以旧代码为上级的其他项目 1 条、以旧代码为最终控制方的其他项目 1 条。如需更正代码，请先联系管理员处理关联数据。","impacts":[{"kind":"parent_refs","label":"以旧代码为上级的其他项目","count":1},{"kind":"ultimate_refs","label":"以旧代码为最终控制方的其他项目","count":1}]}`；界面弹出 `ElMessageBox.alert`，标题「企业代码无法修改」，正文原文「企业代码已被以下数据引用，不能直接修改：以旧代码为上级的其他项目 1 条、以旧代码为最终控制方的其他项目 1 条。如需更正代码，请先联系管理员处理关联数据。 • 以旧代码为上级的其他项目：1 条 • 以旧代码为最终控制方的其他项目：1 条 请先处理关联数据后再修改企业代码。」（逐条 listing 由 `impacts` 生成，含 label 与 count），点「知道了」关闭；库值未变（`company_code` 仍 `9150000FGXUAT40030`、`updated_at` 未变）。授权维度说明：本场景用 admin 操作（partner/admin 直通建项授权），故 409 分支纯由影响检查触发，未被授权判断拦截。
    - 场景 C（无引用新【测试】项目改码成功 → 复原）：项目 `【测试】代码入口无引用验收有限公司_2025`（`32560773-e3e1-4991-b4b1-2f7ecc8aac79`，`9150000FGXUAT40069`，无下级、无合并数据：改前现查 `parent_company_code` / `ultimate_company_code` / `consol_note_data` / `consol_worksheet` / `consol_note_mapping_binding` / `share_change_event` / 同企业另一口径 全部为 0）；改码为 `9150000FGXUAT4007C` → 保存 → **200**，页面提示「项目信息已保存」并跳回项目列表；库值 `company_code='9150000FGXUAT4007C'`（`updated_at` 14:30:09Z 已更新）。复原：再从项目列表重进向导把码改回 `9150000FGXUAT40069` → **200**，现查库值 `9150000FGXUAT40069`，与实测前一致。
    - 复原与对账（逐项）：四个【测试】项目经 `DELETE /api/projects/{id}` 软删（均 200 `{"deleted": true}`，`is_deleted=true`、`deleted_at=2026-11-12 14:32:31Z`）；`DELETE /api/staff/{id}?revoke_assignments=true` 撤销委派 1 条 + 项目成员行 1 条；经理账号经 `PUT /api/users/{id}` 停用（`is_active=false`），复核登录 **401**「用户名或密码错误」。基线 → 收尾同口径现查：未删除项目 **20 → 20**；`project_users` live **8 → 8**（总行 113 → 114，多出的 1 行是软删成员行）；`project_assignments` live **4 → 4**（总行 113 → 113）；`project_creation_grants` live **0 → 0**（总行 2 → 2，本次未新增授权）；`staff_members` live **7 → 7**（总行 270 不变，收尾时人员档案已软删）；`users` 总数 **130 → 131**（新增的 `ce_mgr_20261112` 保留为停用账号：本次只新建这一个账号且已停用，启用账号集合与实测前一致；平台无删除用户端点，停用后登录 401 已复核）。三码现查无残留：`9150000FGXUAT400*` 前缀未删除项目 0 行。
    - 探针：`tmp_group_code_entry/`（`codes.py` 现算合法 USCC 码、`setup.py` 建/复原/对账、`grants_check.py` 核授权前提、`verify_cleanup.py` 复核停用与人员档案），留证后整体删除。
  - [x] 9.3 下载模板，用 openpyxl 写入数字类型代码与无缓存公式后导入，预校验列出针对性提示（无 Excel 环境时以此代替手工输入，并在记录里写明）
    - 环境：前端 `http://127.0.0.1:3030`（chrome-devtools MCP）+ 后端 9980（health 200，migration complete，schema_drift critical=0），admin 登录；本机**没有 Excel**，故按任务允许的方式用 openpyxl 构造工作簿代替手工 Excel 输入（下方逐项写明，非真实 Excel 的环节单独标注）。
    - 模板下载（真实 HTTP）：`GET /api/projects/batch-template?mode=project` → **200**，`content-type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`、`content-disposition: attachment; filename*=UTF-8''%E5%BB%BA%E9%A1%B9%E6%A8%A1%E6%9D%BF.xlsx`、26,366 B；sheet 为 `数据 / 填写示例 / 说明事项 / _GT_OPTIONS / _GT_META`。界面「批量导入」弹窗「下载建项模板」按钮经浏览器再取一次同为 **200**（26,367 B，两次仅压缩时间戳字节差异）。
    - 模板三列格式核对（R3.1，现读）：`数据` sheet 的 B（企业代码）/ H（上级企业代码）/ I（最终控制方代码），第 2、3、100、501 行 `number_format` 全部 `"@"`；数据区 2~501 行三列**没有任何**非文本非空单元格（现算清单为空）。`填写示例` sheet 的 `B2=91110000100000000R`、`H3=91110000100000000R`、`I4=91110000100000000R` 均为 `str`、`data_type="s"`、`number_format="@"`。
    - 构造覆盖文件（`tmp_group_code_entry/codes_import.xlsx`，基于上面下载的真实模板改 5 行，企业代码各不同以避免「重复行」错误掩盖三码提示）：第 2 行 B 列 int；第 3 行 H 列 float；第 4 行 I 列公式 `=H4` 无缓存；第 5 行 B 列公式 `="9150000FGXUAT930D4"` **补了缓存值**；第 6 行 H 列文本 `  9150000fgxuat930bx  `（首尾空格+小写）。落盘形态经 XML 现读确认：B2/H3 是 `t="n"` 数字单元格（openpyxl 把 18 位 int 写成了 `9.11100002e+17`）、I4 是 `<f>H4</f><v/>`（无缓存）、B5 是 `<f>"…"</f><v>9150000FGXUAT930D4</v>`（有缓存）、H6 是 `inlineStr`。三码合法性先经 `validate_uscc` 现算全部 valid。
    - **说明（非假绿，如实登记）**：①真实 Excel 粘贴 18 位数字后落盘是「整数文本 + 15 位有效数字截断」（`<v>911100002000000000</v>`、`t="n"`），openpyxl 写 18 位 int 落盘则是指数形态 `9.11100002e+17`——两者都是数字单元格但形态不同，因此**额外做了一个变体**（`codes_import_true_int.xlsx`：把 B2 的 `<v>` 改成整数文本）覆盖真正的整数形态，两种形态的提示文案均已验证（见下）。②openpyxl 没有公开的公式缓存写入 API，「公式有缓存」这一行是写出后再只改 `xl/worksheets/sheet1.xml` 的 `<v>`（`t="str"`），其余仍走真实 xlsx → `load_data_sheet` 读取链；与 `test_batch_project_import_code_types.py` 同一做法。
    - 预校验（真实 `POST /api/projects/batch-validate?mode=project`，multipart + 幂等键）→ **200**，`valid=false`、`total_rows=5`、`summary={create:2, update:0, unchanged:0, skip:0, auto_root:1, error:3}`、`template_version="2"`。逐条文案原文（与 R3.2 / R3.3 逐字一致）：
      - 第 2 行（int 企业代码）：「企业代码：单元格被 Excel 识别为数字，请将该列设为文本后重新输入（读到 9.11100002e+17）」
      - 整数形态变体第 2 行（`<v>911100002000000000</v>`）：「企业代码：单元格被 Excel 识别为数字，请将该列设为文本后重新输入（读到 911100002000000000）」（两次 200，`valid=false`、`error:3`）
      - 第 3 行（float 上级企业代码）：「上级企业代码：单元格被 Excel 识别为数字，请将该列设为文本后重新输入（读到 9.11100002e+17）」
      - 第 4 行（公式无缓存，最终控制方代码）：「最终控制方代码：公式没有计算结果，请在 Excel 中重新计算保存或粘贴为值」
      - 第 5 行（公式有缓存，企业代码）：**无三码错误**，且进入 `tree_preview` 为 `plannedAction=create`、`nodeKey=9150000FGXUAT930D4@2051` ⇒ 确实是用了缓存值（R3.3 后半句）。
      - 第 6 行（文本首尾空格+小写，上级企业代码）：**无三码错误**，`tree_preview` 里 `parentCompanyCode=9150000FGXUAT930BX` ⇒ 按 R1 规范化后通过（对照行成立）。
    - 错误明细回显（R3.4，真实 `GET /api/projects/batch-imports/{validation_id}/errors.xlsx` → **200**，5,903 B，sheet `错误明细`）：三列代码单元格 `number_format="@"`、`data_type="s"`，且写的是**系统读到的原值**（第 2 行 B=`9.11100002e+17`、第 3 行 H=`9.11100002e+17`、第 4 行 I=`=H4`；整数变体第 2 行 B=`911100002000000000`），错误原因列与预校验文案逐字相同。
    - 界面实测（chrome-devtools，`http://127.0.0.1:3030/projects` → 「批量导入」→ 上传 `codes_import.xlsx` → 「预校验并生成计划」）：弹窗进入「3. 核对执行计划」，红色横幅「预校验未通过：发现 3 项阻断问题」，汇总卡「新建 2 / 更新关系 0 / 无变化 0 / 跳过 0 / 自动合并根 1 / 错误行 3」，「阻断问题」表明细三行与上面第 2/3/4 行文案**逐字一致**，页面右下出现「预校验存在阻断问题，请下载错误明细并修正」，「确认执行」保持禁用；点「下载错误明细」触发真实 `GET /api/projects/batch-imports/9303bfb1-…/errors.xlsx` → **200**。console 无与三码 / 批量导入相关报错（仅既有 `GtStatusTag` prop 警告与一次与本流程无关的 403 静态资源）。
    - 未执行导入：全程**只**走预校验（`batch-validate` / `batch-imports/{id}` / `errors.xlsx`），未调用 `batch-apply`，未创建任何项目。
    - 库内对账（PG `audit_platform`，同口径现查）：未删除项目 **20 → 20**、`projects` 总行 **128 → 128**；`project_batch_import_plans` 基线 **0 → 预校验后 4 → 收尾 0**（预校验按设计会持久化计划行；经 `pg_constraint` 现算确认该表**无任何引用它的外键**后，按主键精确 `DELETE` 本次产生的 4+1 条 `status=invalid` 计划行，不按时间/项目范围扫描）；本次构造的 `9150000FGXUAT930*` 前缀项目行 **0**；`note_text_batch_applications` 9 / `import_batches` 34 / `adjustment_import_batches` 0 均与基线一致。
    - 回归证据：`python -m pytest backend/tests/test_batch_project_code_cells.py backend/tests/test_batch_project_import_code_types.py -p no:playwright -q` → **30 passed**（tasks 4.4 / 4.5 的五类单元格单测仍全绿）。
    - 探针与清理：`tmp_group_code_entry/`（`fetch_template.py` 走真实端点下载模板并核三列格式、`gen_codes.py` 现算合法 USCC、`build_workbook.py` 造五类单元格、`preview.py` 走真实预校验+错误明细、`patch_true_int.py` + `preview_variants.py` 覆盖整数落盘形态、`db_counts.py` / `plan_rows.py` / `cleanup.py` / `cleanup2.py` 对账与精确清理），留证后整体删除；上传界面用的临时副本 `audit-platform/frontend/tmp_task93_codes.xlsx` 已删除。

  - [x] 9.4 两个标签页打开合并总览，先后拖拽同一节点：后者提示「已被他人调整」并刷新；实测后把上级恢复原值并对账两口径项目
    - 环境：前端 `http://127.0.0.1:3030`、后端 `9980`；健康端点 200，Postgres / Redis healthy，migration complete，schema_drift critical=0；Chrome DevTools MCP，两个标签页均以 admin 登录并打开 `/consolidation`。
    - 临时数据：通过正式 `POST /api/projects` 创建四个仅用于本次验收的【测试】项目：上级甲 `196f05a0-eea1-4d5e-bf7a-8ace5671cc8e`（合并）、上级乙 `7207aac2-5b7c-493e-9739-80d681c19ec0`（合并）、目标合并项目 `62861683-59b4-4bb7-a526-eb796af3cd22`、目标单户项目 `44049824-5ddc-4553-ad70-fbb19895cbc5`；根项目复用既有【测试】项目 `3a3930db-3f14-431c-a919-913d04a23eca`，未修改真实业务项目。
    - 基线（首次拖拽前 PG 与企业树接口逐值一致）：目标合并 / 单户两行的 `company_code=9150000FGXUAT9402P`，`parent_company_code=9150000FGXUAT9400H`，`parent_company_name=【测试】三码并发上级甲有限公司`，`ultimate_company_code=9150000FGXUAT000P1`；企业树节点同为 `parentCompanyCode=9150000FGXUAT9400H`，并识别 `consolidatedProjectId=62861683-59b4-4bb7-a526-eb796af3cd22`、`standaloneProjectId=null`（合并树接口按合并口径返回，PG 同时核对两口径）。
    - A 页先拖目标节点至上级乙并确认：真实 `PATCH /api/projects/62861683-59b4-4bb7-a526-eb796af3cd22/parent-code` 返回 200；请求体含 `expected_parent_company_code=9150000FGXUAT9400H`，响应 `parent_company_code=9150000FGXUAT9401L`，`synced` 同时列目标合并项目与目标单户项目。
    - B 页保持旧树并拖同一节点至上级乙：只发 1 次 PATCH，请求体仍含 `expected_parent_company_code=9150000FGXUAT9400H`；响应 409，原文 `{"error_code":"PARENT_CODE_CONFLICT","message":"企业树已被他人调整，已刷新为最新结构","current_parent_company_code":"9150000FGXUAT9401L"}`。页面即时显示标题「层级已被调整」和提示「企业树已被他人调整，已刷新为最新结构」，随后请求企业树 GET 刷新，未出现第二次 PATCH / 自动重试；刷新后目标节点位于上级乙下。
    - 恢复与第二轮 UI 取证：A 页再将目标从乙拖回甲并成功 200；B 页用旧 `expected_parent_company_code=9150000FGXUAT9401L` 再请求，409 原文 `current_parent_company_code=9150000FGXUAT9400H`，同样只刷新不重试；Chrome DevTools 快照捕获了上述中文提示。补测缺少 `expected_parent_company_code` 返回 428，原文为「请刷新企业树后重试（缺少改前上级）」，未写入。
    - 收尾对账（删除临时项目之前）：PG 两口径目标行均恢复为 `parent_company_code=9150000FGXUAT9400H`、`parent_company_name=【测试】三码并发上级甲有限公司`；企业树接口目标节点同为 `parentCompanyCode=9150000FGXUAT9400H`。随后按正式 `DELETE /api/projects/{id}` 依次软删四个临时项目，四次均返回 200 `deleted=true`。
    - 清理后对账：PG 未删除项目数 `20`（与基线一致），四个临时项目 `temp_live=0`、`temp_total=4`（保留平台回收站软删记录），临时项目 `project_users=0`、`project_assignments=0`；企业树接口不再返回 `9400/9401/9402` 临时节点，既有【测试】根节点仍存在且上级为空。控制台仅记录本次预期的 409/428 HTTP 错误，无 JavaScript 运行时错误。
    - 一次性脚本 / 输出均位于仓库根 `tmp_group_code_entry/`；本次验收结束后删除该临时目录。
  - [x] 9.5 `initScript` 拦截企业树接口注入两类诊断：进入合并工作台弹窗、「我知道了」后刷新不再弹、三个推送入口出现确认框
    - 环境：前端 `http://127.0.0.1:3030`、后端 `9980`；health 200，Postgres / Redis healthy，migration complete，schema drift critical=0；Chrome DevTools MCP，admin 会话；只使用既有【测试】合并项目 `3a3930db-3f14-431c-a919-913d04a23eca`（2025）与 `80b4355b-65a1-4554-83ff-524dcd7af099`（2098）。未使用 Playwright、未改生产代码、未创建临时项目或上传文件。
    - 注入形态：仅在导航前通过 `initScript` 包装 fetch / XHR，拦截真实 `GET /api/consolidation/worksheet/tree?project_id=...`，先解析原响应并保留原 `data.tree`、`mode`、`scope_version` 等字段，再写入 `data.diagnostics`。每次响应 `treePreserved=true`；注入 `duplicate_project` 与 `relation_conflict`，两类均带真实 UUID `[3a3930db-3f14-431c-a919-913d04a23eca, 80b4355b-65a1-4554-83ff-524dcd7af099]`，另注入负对照 `test_info_only`（`project_ids=[]`）。本次每次导航实际拦截 3 次企业树响应，未出现 malformed payload。
    - 首次弹窗：进入 `3a3930db-3f14-431c-a919-913d04a23eca` 合并工作台后出现标题「企业树冲突提示」，说明原文「企业树按下列规则取值，计算与推送仍可继续。」；弹窗逐条显示「测试诊断：发现重复项目，企业树按合并口径项目取值」与「测试诊断：企业关系存在冲突，企业树按合并口径关系取值」，每条显示两个「去修改（项目 UUID）」按钮。`test_info_only` 仅出现在页面普通提示「企业树有 2 条需要关注的提示」中，未进入冲突弹窗。
    - 会话去重：点击「我知道了」后写入 `sessionStorage` 键 `gt:consol-tree-conflicts:{project_id}:{year}`，值为排序后的两类 `[code,message]` 签名；同一注入签名重新导航后 `visibleConflictDialogs=[]`，未再次弹窗。将 `duplicate_project` 文案改为「测试诊断：发现重复项目，企业树按合并口径项目取值（签名变更）」后重新导航，冲突弹窗再次出现，证明签名变化会重弹。
    - `ConsolPushPanel.vue`：在合并报表页打开「⚙️ 公式管理」→「📤 合并推送」后，看到「📤 立即推送」；点击后先 GET 企业树并弹标题「企业树存在冲突」，正文「企业树存在重复项目或集团关系冲突，系统会按提示的一方取值。」及两条注入诊断，按钮为「取消 / 仍要推送」。点击「取消」后没有发出 `/api/consolidation/{project_id}/{year}/push` POST/PUT。
    - `ConsolTrialBalanceTab.vue`：切换「合并试算平衡表」，点击「📤 重新推送」后同样先 GET 企业树并出现标题「企业树存在冲突」、同样两类诊断和「取消 / 仍要推送」；点击「取消」后没有发出推送 POST/PUT。
    - 合并工作台手工入口：`3a3930db-3f14-431c-a919-913d04a23eca` 页面 stale 提示「子企业数据已变化，建议重新推送（3 行待更新）」和按钮「立即重新推送」均可见；点击后先被既有前置对话框拦截，标题「有未保存的合并工作区修改」，正文「推送合并结果前，请先处理未保存修改。」「待处理：合并工作底稿·基本信息表」，按钮「取消 / 放弃修改 / 保存并继续」。为避免丢弃并发会话草稿选择「取消」，未进入企业树冲突确认框，也未发出推送请求；该入口的冲突确认路径因此保持阻塞，不能标记完成。
    - 网络 / 控制台：取消两个人工入口后均只有企业树 GET，没有对应 push POST/PUT；最终页面无 JavaScript error，唯一持续 console warning 为「项目详情缺少或含非法 amount_unit，按元显示」（既有项目数据警告）。`80b...` 公式管理走查期间另见一次既有 `GET /api/disclosure-notes/80b4355b-65a1-4554-83ff-524dcd7af099/2098` 404，和本任务注入/取消路径无关。
    - 误触与数据对账：曾误点 `80b...` 工作台顶部「🔄 更新合并结果」（不是手工推送入口），产生 `POST /api/consolidation/80b4355b-65a1-4554-83ff-524dcd7af099/2098/refresh-all`（200）。任务 `5d34851c-bb7d-4f99-8625-f1b9436aba1e` 后续终态为 `stale`，错误 `INPUT_VERSION_CHANGED`，6 步完成、reconciliation diff=0，未形成正式成功结果；生成的 report run `4147247a-6233-4712-9367-795fcd33e69f` 仅为该全量刷新产物。只读对账显示 `consol_push_run` 仍为 5 条、最新时间仍为 `2026-10-10`，本次取消路径未新增推送运行；未执行确认推送。该误触刷新非本任务推送验收，因缺少刷新前快照且无安全删除入口未擅自删除，需用户/后续治理任务决定是否清理其测试产物。
    - 结论：弹窗、负对照、同签名去重、签名变化重弹、`ConsolPushPanel` 与 `ConsolTrialBalanceTab` 的取消门均已实测；合并工作台手工入口被既有未保存修改前置门阻塞，且误触一次测试项目全量刷新未完成安全数据清理，故保持 `[-]`，不标 `[x]`。未生成截图或临时上传文件，证据保留在本次 Chrome DevTools 快照 / 网络详情中。
    - 阻塞已解决复验记录（2026-11-13，追加，不覆盖上条历史结论）：先用正式 `POST /api/projects` 建立干净临时合并工作台 `273f0dd1-059a-4dec-8bf0-a5733a38c476`（2097）及下级 `6dbd7ffc-3606-4475-a720-bf6493a5fd7d`，真实树 200 且新页无未保存草稿；记录树版本 v1。仅在该临时项目的 `ConsolPushPanel` 点击「仍要推送」，`POST /api/consolidation/{pid}/2097/push` 返回 operation `c8ef7e06-9096-401e-9e4f-7ae75e4a1838`，终态 `succeeded`，worksheet/trial/report/notes 四步均 succeeded，report run `39b63485-334d-4f8a-9a67-6bd7a45010a4`；随后临时项目及备用父项目共 6 个经正式 DELETE 全部 200，GET 均 404，活跃项目数回到 20。
    - 第三个入口改用 Chrome DevTools 隔离 context `task95-clean80` 的新 admin 页，未出现「有未保存的合并工作区修改」对话框。为产生真实待推送状态，先将【测试】下级 `7cd13170-0480-42f3-9b43-f030e4b798d5` 临时移入同年度备用父项目，`push-status` 实为 `is_stale=true, stale_rows=2`；页面显示「子企业数据已变化，建议重新推送（2 行待更新）」和「立即重新推送」。`initScript` 只改真实企业树 XHR 响应，保留 `data.tree/mode/scope_version`，注入 `duplicate_project`、`relation_conflict` 及 `test_info_only` 负对照；点击后确认框标题「企业树存在冲突」，正文「企业树存在重复项目或集团关系冲突，系统会按提示的一方取值。」并逐条显示两类诊断，按钮「取消 / 仍要推送」。点击「取消」后可见对话框为空，网络中只有企业树 GET，匹配推送端点的 POST/PUT 为 0；未执行该既有项目的确认推送。
    - 复原与清理：既有下级合并/单户两行均恢复 `parent_company_code=91110000100000000R`、原上级名称和 `parent_project_id`；正式 `POST /api/consolidation/trial/recalculate` 返回原 2 行金额，随后 `push-status` 为 `is_stale=false, stale_rows=0`。误触的 operation `5d34851c-bb7d-4f99-8625-f1b9436aba1e` 只读确认终态 `stale`、错误 `INPUT_VERSION_CHANGED`、6 步完成、reconciliation diff=0；其 report run `4147247a-6233-4712-9367-795fcd33e69f` 通过 published 读取返回 409 `PUBLISHED_REPORT_NOT_FOUND`，不是正式结果。operation 取消仅支持 queued，仓库现有路由没有 operation/report-run 删除或回收入口，故按安全要求保留并登记为范围外残留，未手工 DELETE 共享库行或改审计数据。
    - 浏览器证据：无 JavaScript/page runtime error；持续的 `amount_unit` warning 和表单缺少 id/name issue 为既有提示；本轮 404（临时项目软删后的只读核对、错误 operation URL）与 409（未发布 report run、预期冲突）均为验收探针请求，不是页面运行时故障。`tmp_group_code_entry/` 已清空，未改生产代码、未提交/推送。
  - [x] 9.6 在 `http://192.168.20.60:3030` 复测 9.1、9.4、9.5

- [x] 10. 收尾
  - [x] 10.1 review 文档 §0.5 / §10 / §10.1 标注 P1-1 / P1-2 / P1-5 的落地方式、拍板结果与 P2-1 / P2-2 不做理由
    - 完成记录（2026-11-12）：修改 `docs/proposals/consolidation-three-code-tree-and-formula-chain-review-2026-11-10.md` 的 §0.5.3、§10 三项 P1/P2 状态和 §10.1.1；未改生产代码、迁移或无关 spec。
    - 结果：P1-1 记录锁后 refresh 的 `expected_parent_company_code` CAS 及不复用 `entity_group_fields_hash`；P1-2 记录前后端共享规范化/四入口一致；P1-5 记录文本列、数字/公式提示、原值回写和 hash 硬门；P2-1/P2-2 记录不做理由、影响与后续边界。
    - 证据来源：当前 `group_links.py`、`project_wizard.py`、`uscc_validator.py`、`batch_project_workbook.py`、`batch_project_export.py` 与前端对应实现；`test_group_code_entry_consistency.py`、`test_parent_code_update.py`、`test_group_code_entry_cas_mutations.py`、`test_batch_project_code_cells.py`、`test_batch_project_import_code_types.py`、`uscc_validator.spec.ts`、`BasicInfoStep.normalize.spec.ts`、`ConsolidationHub.reparent.spec.ts`；tasks 9.1、9.3、9.4 运行记录。
    - 验证：`rtk python -m pytest tests/test_group_code_entry_consistency.py tests/test_parent_code_update.py tests/test_batch_project_code_cells.py tests/test_batch_project_import_code_types.py tests/test_group_code_entry_cas_mutations.py -p no:playwright -q` → 89 passed；`node node_modules/vitest/vitest.mjs run src/utils/__tests__/uscc_validator.spec.ts src/components/wizard/__tests__/BasicInfoStep.normalize.spec.ts src/views/__tests__/ConsolidationHub.reparent.spec.ts --reporter=dot` → 3 files / 107 passed；文档差异检查待收尾执行。
  - [x] 10.2 在 `.kiro/specs/INDEX.md` 登记本 spec（基于最新 HEAD 副本只加本行，CRLF 与表格列数校验）
    - 完成记录（2026-11-12）：基于最新 HEAD `a24407efdd16a5bca22836a3df5f1f32c79fc750` 读取 INDEX，仅修正本 spec 登记行为 `55/57`；代码 8/8，浏览器 9.1~9.4、9.6 完成，9.5 保留既有未保存修改门阻塞与误触刷新未清理说明，10.1~10.2 完成。
    - 验证：`requirements.md` / `design.md` / `tasks.md` 三件套存在且链接可读；INDEX 为 UTF-8、1197 行均 CRLF、无 BOM；Active 表 24 行每行恰 4 个未转义 pipe，目标行同样为 4 个。
    - 差异：INDEX 相对 HEAD 仅目标行 1 行替换（`0/57` → `55/57`）；未修改生产代码、其他 spec 或历史文档。一次性探针位于 `tmp_group_code_entry/`，验证后删除。


## 9.6 内网复测完成记录（2026-11-13，Chrome DevTools MCP）

- 目标地址严格为 `http://192.168.20.60:3030`，未使用 `127.0.0.1` / `localhost`，未使用 Playwright MCP。首次 document HTTP 200，未登录重定向 `/login?redirect=/`；`admin/admin123` 登录 HTTP 200 后进入 `/`，项目列表 API HTTP 200。
- `GET /api/health` HTTP 200：`status=healthy`，Postgres/Redis=`ok`，migration `complete=true`（applied 260、pending 空），schema drift `critical_count=0`，startup failed 空。最终内网页面无 JavaScript error；只见既有 amount_unit warning、表单 id/name issue 等非本次功能错误。
- 内网 HTTP 安全上下文只读结果：`window.isSecureContext=false`；`crypto.randomUUID`、`crypto.subtle`、`navigator.locks`、`navigator.clipboard` 均为 `undefined`。未修改生产代码；页面加载、登录、树请求和三码向导均未因能力缺失产生运行时错误。

### 9.1 内网向导三码规范化

- 正式 `POST /api/projects` 创建临时【测试】单户 `06ebfcc7-6ba1-4df9-9518-41e2bc02331e`（2096，初始企业代码 `9150000FGXUAT96036`）。
- 在 `/projects/new?projectId=...` 真实输入并失焦：小写企业代码 `9150000fgxuat96036` → `9150000FGXUAT96036`；全角上级代码 `９１５００００ＦＧＸＵＡＴ９６０２３` → `9150000FGXUAT96023`；小写控制方代码 `9150000fgxuat9600w` → `9150000FGXUAT9600W`，错误提示清空。
- 首尾空格边界通过同一真实输入元素派发 input 后点击表单标题触发真实 blur handler：` 9150000fgxuat96036 `、` ９１５００００ＦＧＸＵＡＴ９６０２３ `、` 9150000fgxuat9600w ` 均显示规范化大写值。输入框既有 `maxlength=18` 会把正常填充的 20 字符截断，故该截断边界单独如实记录，没有把截断误报为成功。
- 点击「保存」触发 `PUT /api/projects/{id}/wizard/basic_info` HTTP 200，页面回 `/projects` 并显示「项目信息已保存」。随后 `GET /api/projects/{id}` 与 `/wizard` 均 200，返回规范值；PG 逐值读回 `company_code=9150000FGXUAT96036`、`parent_company_code=9150000FGXUAT96023`、`ultimate_company_code=9150000FGXUAT9600W`，`is_deleted=false`。
- 该临时项目经正式 `DELETE /api/projects/{id}` HTTP 200、`deleted=true` 软删；未强行写空集团关系，避免影响共享库其他夹具。

### 9.4 内网双标签页 CAS

- page 1 与 page 4 均从 `http://192.168.20.60:3030/consolidation` 加载同一企业树；page 4 单独以 admin 登录，两个页面均为 Chrome DevTools 页面。四个临时项目经正式 POST 创建，均为 2096【测试】项目。
- 为满足同一 `el-tree` 的拖拽约束，先把临时上级乙正式 PATCH 到上级甲下，再两页重载；A 页将目标节点拖到上级乙并确认，真实 PATCH HTTP 200，请求体含 `expected_parent_company_code=9150000FGXUAT9600W`，回执同步合并/单户两口径。
- B 页保持旧树再次拖拽并确认，只发 1 次同 URL PATCH，旧期望值仍为 `9150000FGXUAT9600W`；HTTP 409，响应 `error_code=PARENT_CODE_CONFLICT`、`message=企业树已被他人调整，已刷新为最新结构`、`current_parent_company_code=9150000FGXUAT96010`。页面显示「层级已被调整」及同文提示，随后刷新树且没有第二次 PATCH / 自动重试。
- A 页再将目标拖回上级甲并确认，随后正式 PATCH 将夹具上级乙恢复为无上级；恢复后 PG 两口径目标项目均为 `parent_company_code=9150000FGXUAT9600W`、上级名称「【测试】内网三码复测上级甲」、`relation_to_parent=subsidiary`、`ultimate_company_code=9150000FGXUAT9600W`。企业树 API HTTP 200 与 PG 逐值一致。

### 9.5 内网诊断弹窗、去重和三入口

- 导航前 initScript 只拦 `GET /api/consolidation/worksheet/tree?project_id=...` fetch/XHR 响应，保留原 `data.tree`、`mode`、`scope_version`，追加 `duplicate_project`、`relation_conflict`、负对照 `test_info_only`。三次拦截均 `treePreserved=true`，无注入错误。
- 临时合并项目首次进入弹「企业树冲突提示」，两类诊断逐条显示真实项目 UUID 的「去修改」按钮；`test_info_only` 只在普通企业树提示中出现，没有进入冲突弹窗。
- 点击「我知道了」后写入 `gt:consol-tree-conflicts:{project_id}:2096` 签名；同签名 reload 不再弹。改变 duplicate 文案后 reload，冲突弹窗重新出现。以上均在内网地址完成。
- 临时项目 `ee3cb880-da29-42b7-ac68-0606e67b0aca` 的 `ConsolPushPanel` 通过「⚙️ 公式管理」→「📤 合并推送」进入，点击「立即推送」先弹「企业树存在冲突」，点击「仍要推送」确认仅作用于该临时项目。推送 run `1a21468c-c581-4b4d-8f29-3cf107fd9ebb` / operation `05f62515-a7cb-48e2-a288-664c00e54fd2` 最终 succeeded，worksheet/trial/report/notes 四步均 succeeded。
- 同一临时项目「试算平衡表」的「📤 重新推送」先弹同一冲突确认框；点击「取消」后网络只有企业树 GET，没有推送 POST/PUT。
- 既有【测试】项目 `3a3930db-3f14-431c-a919-913d04a23eca` 的 stale 横幅显示「子企业数据已变化，建议重新推送（3 行待更新）」；为不丢弃未知草稿，点击「保存并继续」而非「放弃修改」，真实 `PUT /api/consol-worksheet-data/{id}/2025/info` HTTP 200。再次点击 stale 入口后出现冲突确认框，点击「取消」；网络中没有对应推送 POST/PUT。
- 清理期间临时项目还原了目标上级、临时 `account_subject=1001` 改动，并将既有【测试】项目 `4c77f3e8-3938-4628-8836-1435dda4ddea` 临时改挂上级后正式恢复原上级。四个内网 2096 临时项目均正式 DELETE 200；PG 最终 live 项目数回到 20，`【测试】内网三码复测%` live=0、软删总记录 5（含 9.1），临时成员/委派 live 均 0；既有 `4c77...` 与 `3a...` 关系逐值恢复。
- 一次性证据曾写入仓库根 `tmp_group_code_entry/session-evidence.md`，记录了健康检查、安全上下文、HTTP/PG/API/弹窗/清理结果；本次记录写入 tasks.md 后删除临时目录。未修改生产代码、未提交、未推送。
