# 任务：程序裁剪 → 底稿生成 → 委派 → 可见性 链条闭环

> 用户裁决与需求见 requirements.md，设计见 design.md。每个任务完成须附测试结果；外部依赖未实测的如实标 `[ ]*`。

## 批 1 科目有无数据（需求 1）

- [x] 1. 新建 `trim_subject_scope.py`（四表规格 + 映射表兜底的科目口径、逐项目按名定位、余额 / 期初 / 发生 / 客户未映射判定、证据）
  - 实测修正：四表定位「只取第一个命中的名字」会把存货定位到材料采购（重药安徽材料采购 0、库存商品 1.59 亿），判有无数据改为全部候选名并集（`match_slot_all_names`）
- [x] 2. 改写 `procedure_trim_scope.resolve_subject_data_availability`（兼容旧字段，新增 `subject_unknown` / `evidence`），删除旧映射加载与 `procedure_trim_account_map.json`，重写 `test_procedure_trim_scope.py`（16 passed）
- [x] 3. 前端决策内核档 4 加金额矛盾守卫，更新受影响用例并补矛盾用例（裁剪判定相关 5 个文件 191 passed；原 4 条用例的夹具是「无数据 + 金额 100 万」的自相矛盾输入，改为金额未出现 / 0）
- [x] 4. 真库只读对照（`test_trim_subject_scope_pg.py` 1 passed + 一次性探针）：重药安徽 23 个已裁码中只有 H3 有数据；F2 存货、H1、F4、M2 有数据；和平药房 2024 的 H8（1641）、M9（3102）按名称定位到平台标准表码且有数据；宜宾临港店实收资本客户码映射到标准码 4001（该项目标准表里 4001 是生产成本，映射本身有误，判定跟随项目映射）

## 批 2 生成只保留裁剪后的（需求 2）

- [x] 5. 新建 `procedure_scope_retention.py`（保留范围、区间展开、子表前缀、fail-closed、回收站同码）+ 单测
  - 判定改为「最近一级有程序行的编码决定」，母码断点含「数字后紧跟字母」（`M4A` 资本公积程序表跟随 `M4`）；安徽受影响 138 张（原 132 + 6 张程序表）；`ProcedureService._expand_range_wp_code` 改调同一展开函数
  - `test_procedure_scope_retention.py` 11 passed；`test_procedure_scope_retention_pg.py` 1 passed（安徽全部底稿编码与独立朴素口径逐个一致）
- [x] 6. 接入七个生成入口 + 回执字段 + `/generate` 两端点 edit 鉴权 + 模板列表 `trimmed` 标记 + 前端回执提示与弹窗不预选
  - 另含自定义底稿单条 / 批量 / 预览、准则切换预览 / 执行（鉴权与保留范围，见 design §8）；鉴权棘轮 200→193；顺带修跨项目模板复制三处既有缺陷与 IPO / B60 单条保存点
  - 前端：弹窗已裁项不预选、禁用、标「已裁剪：跟随 X」，全选跳过，列表读不到时弹窗内说明；回执提示两类跳过编码（前端 3 文件 12 passed）
- [x] 7. 各入口过滤与回执测试（含 5xx 回退路径、全链第 8 步、准则转换）
  - `test_generation_entries_retention.py` 12 passed；受影响既有用例补真实项目成员（不 override 鉴权）；相关 27 个后端测试文件 672 passed
  - 变异 5 个全部打红（去字母断点 / 去子表前缀 / 生成分流不拆 / 同级已裁优先 / 读取失败吞掉），在验证 worktree 注入、逐字节恢复
  - HEAD 干净检出同样红、与本 spec 无关：`test_template_engine` 模板集种子 3 例、`test_custom_workpaper_projection` 前端注册表 1 例、`test_lazy_import_resolvability` 2 例

## 批 3 回收站联动与委派（需求 3、4）

- [x] 8. 新建 `workpaper_recycle_service.py`（计划 / 移入 / 恢复 / 实质内容判定）+ 真库事务回滚测试
  - `test_workpaper_recycle_service_pg.py` 1 passed（真库：唯一索引不含 is_deleted ⇒ 同码只能恢复；公式推送行不算人工填写；按原因恢复；纪元逐次递增）
- [x] 9. `apply_scheme` 联动（移入 / 恢复 / 级联按归属匹配 / 恢复执行时 reopen）+ preview `recycle_preview` + apply 确认参数 + 前端保存前确认
  - 联动放 `procedure_trim_recycle.py`；`test_procedure_trim_recycle.py` 4 passed；前端 `trimRecycleConfirm` 用例通过
  - 准则切换（批 2 遗留）同走回收站：`test_standard_conversion_recycle_pg.py` 1 passed（见 design §8 批 3）
- [x] 10. 回收站路由：底稿两层恢复、禁止彻底删除、项目鉴权与清空限 admin + 测试
  - `test_recycle_bin_workpapers.py` 4 passed
- [x] 11. 委派拦截（已粗裁 / 已细裁）+ `_enforce_scope` 有效范围与主管免检 + 程序委派 `scope_gaps` / 扩权 + 测试
  - `test_delegation_trim_scope_guard.py` 16 passed；既有委派测试夹具角色改审计员（主管免检，见 design §8）
- [x] 12. 旁路收口（batch-assign 项目过滤并走 `delegate_lead`、batch-assign-enhanced、复核页指派、人员交接、wp_mapping 410）+ 测试
  - `test_delegation_bypass_entries.py` 9 passed；受影响既有用例（批量分配 / 交接 / pm 全流程 / 通知 / WOPI 质控）83 passed
- [x] 13. 前端 `useScopeExpansionRetry` 接入主编下拉、程序委派向导、控制台行委派、批量分配弹窗 + 测试
  - 组合函数 10、建议分配 / 向导 / 下拉 4、批量弹窗 3、控制台 3、接口 4 例通过；相邻 4 个前端测试文件 98 passed
  - 批 3 验收：变异 35 个（B01~B29、F01~F06）全部红在预期断言上；ESLint 0 错误（44 条告警与 HEAD 相同）；单区域 vue-tsc 13 条报错与 HEAD 相同、注入类型错误能报出

## 批 4 可见范围（需求 5）

- [x] 14. 新建 `effective_scope.py`；分类器主管识别（中文别名、多条委派）与范围；`get_user_scope_cycles` 对齐；附注过滤去 fail-open + 测试（更新原 spec 中「多条委派即受限」的用例并注明裁决）
  - `effective_scope.py` 批 3 已建；分类器与 `get_user_scope_cycles` 改调它；附注目录树 / 就绪度空范围即空；调整分录取循环科目失败不再放行全部；委派通知受限成员没勾选写「未勾选」
  - `test_effective_scope_consumers.py` 8 passed；按裁决改写的既有用例（注明裁决）：`test_role_classifier`、`test_task6_role_acceptance`、`test_task17_capacity_and_role_acceptance`、DSH `test_task1_resource_access`、`test_ai_chat_mcp_tools_data`；多份人员记录仍按受限（见需求 5.3 实施修订）
  - 变异 6 个（B30~B35）红在预期断言上；可见性 / DSH / AI 工具 / 调整 / 试算表 / 附注相关 17 个文件回归，余下 3 条红 HEAD 同样红（MissingGreenlet 1、附注准则冲突 2）

## 批 5 细裁与行级编辑（需求 6、7）

- [x] 15. 新建 `procedure_row_trim_service.py` + 两个行级裁剪端点（PG 真库测试：导入定义、物化、绑定、取消 / 恢复、委派被拒）
  - 不整表物化：只建这一行的定义与任务（插入即绑定），同程序号新旧任务一起裁 / 恢复，恢复不建任务（见 design §8 批 5）
  - `test_program_row_trim_and_access.py` 13 passed（真库回滚：往返与幂等、同号多任务、自加行 / 无模板 422、跨项目 404、裁后委派被拒、端点只给委派人、投影不认粗裁级联）
- [x] 16. render-config 适用性投影（两条路径）+ 前端 `useProgramRowTrim` 接入控制台 + 完成率排除不适用 + 测试
  - 投影只在最近一次行级决定（控制台 / 方案行条目）是恢复时改回待执行，粗裁级联与恢复不算，页面原有不适用不动，已存数据深拷贝；控制台裁剪 / 恢复先落任务、成功才改页面（组合函数合并为 `useProgramRowControl`）；完成率与进度条排除不适用
- [x] 17. 新建 `program_row_guard.py`；`/save` 行级合并；field-overrides 鉴权与本人行校验；`program-row-access` 端点 + 测试
  - `test_program_row_guard.py` 10 passed（合并口径 + `/save` 接线：先合并后落盘、读不到归属 503 不落盘）；字段覆盖 GET 补成员、POST 补 edit 与本人行，鉴权棘轮 87→84 并登记回归钉子
- [x] 18. 前端 `useProgramRowAccess` + 控制台行只读与按钮可见性 + 测试
  - 受限用户只本人行可编辑、其余只读显示执行人；新增给可改全部行的人，裁剪 / 批量裁剪 / 委派只给委派人；`/save` 回执没生效的程序号在编辑器提示
  - 前端用例：组合函数 7、控制台行级 7、接口 3，既有控制台 / 完成率用例按新行为更新（相关 12 个文件 106 passed）
  - 批 5 验收：变异 34 个（B36~B58、F07~F17）全部红在预期断言上；后端相关 20 个文件 317 passed；ESLint 0 错误、告警与 HEAD 相同；单区域 vue-tsc 21 条与 HEAD 逐条相同、注入类型错误能报出

## 批 6 数据处置与验收（需求 8、9）

- [x] 19. `scripts/fix/recycle_trimmed_workpapers.py`（dry-run → 复核误裁恢复 → 移入回收站并备份 → 重新生成 → 对账，可重跑）；在重药安徽执行并记录结果
  - 内核 `procedure_trim_cleanup.py`；`test_procedure_trim_cleanup_pg.py` 2 passed（真库回滚：误裁恢复、其余移入、对账与幂等、实质内容未确认 409、不变式不成立整体回滚）；变异 B59~B66 红在预期断言上
  - 重药安徽：H3 有数据（期末 10,763,907.81、本期借方 7,689,744.44）恢复执行并记更正理由；其余 22 个裁剪行管的 131 张底稿两层移入回收站（`kind=trim`），级联取消 17 条任务；按原模板集重新生成新建 0；对账：在用 929 / 回收站 131 / 仍在用的已裁底稿 0 / 回收站底稿下未关闭任务 0；第二次 dry-run 0 动作；备份 `backend/backups/recycle_trimmed_0ec33ac9-…_20261025_111754.json`（与 design §8 批 6 的偏差同记）
- [x] 20. 变异检验（design §5 清单逐个打红）
  - 全量 130 个（后端 B01~B101、前端 F01~F29）在验证 worktree 逐个注入、逐字节恢复，全部红在预期断言上；补齐批 1 / 批 2 / 批 3 漏做的：生成入口逐个去过滤（B67~B76）、保留范围内核（B77~B81）、级联恢复只重开级联取消的 / 只恢复因裁剪移入的（B83~B84）、回收站路由（B96~B101）、科目有无数据（B82、B85~B95）、档 4 矛盾守卫与生成弹窗 / 回执 / 保存前确认 / 回收站页（F18~F29）
  - 首轮未打红 2 个并已处理：B32 预期列表误列 PBT 用例（抽样 5 例很少抽到主管，由两条确定性用例打红）；B94 真映射表没有 A/B/C/S 主条目（真数据上等价）⇒ 补临时映射文件用例。为此新增 / 补强用例：保存前确认四个入口的接线（4 例）、`canonicalTrimApply` 确认标记（2 例）、回收站页底稿行（1 例）、按类型清空底稿 409、映射表循环过滤（1 例）
- [x] 21. 回归：相关后端测试集、前端 vitest、单区域 vue-tsc、ESLint；行数门白名单登记
  - 后端：引用改动模块的测试 ∪ 各批专项（192 个文件，排除提交真库的 6 个）4704 passed / 752 failed / 7 errors；失败用例所在 44 个文件在 HEAD（bf7685b1d）干净检出复跑，只在工作树红的 3 条：架构债务基线 `GtAProgramConsole` 指纹（批 5 改动，债务形态未变，已刷新）、EQCR 消费方登记表（主管名单改由 ROLE_MAP 派生后已无字面量，登记条目移除）、并发会话未提交模块 `entry_scoped_registration`（与本 spec 无关）；其余 749 条 HEAD 同样红（循环导入导出校验的组件类型断言过期、`test_note_edit_stamp_writers` 缺表、懒导入 3 处等）
  - 前端：引用改动模块的 49 个用例文件 627 passed / 4 failed + 1 个文件加载失败，HEAD 干净检出同样红（`composables.spec` 1、`WorkpaperListShell` 3、`WorkpaperEditorShell` 路由 mock）；单区域 vue-tsc 21 条与 HEAD 逐条相同、两个新用例文件注入类型错误能报出；ESLint 0 错误、46 条告警与 HEAD 相同
  - 行数门：本 spec 改动的 123 个文件通过；HEAD 已超限且未登记的 3 个测试文件按改前行数登记白名单（1104 / 863 / 972）
- [x] 22. 浏览器实测（admin 裁剪 → 生成 → 委派；审计员视角只见本人底稿、只能改本人行）
  - 【测试】程序裁剪链条验收有限公司_2025 + 审计员 ptgd_auditor，全程走界面：团队分配（审计员勾 D）→ 粗裁 H3 → 生成弹窗 H3 及 H3-1~6 禁用、标「已裁剪：跟随 H3」→ 生成 D2 / E1 / H1 → 批量委派 D2 / E1（E1 出范围提示 → 填理由扩权）→ 控制台细裁 H1A 第 2 行（任务不适用 / 已取消，进度 0/21）并恢复 → 程序委派向导（预览目标 1 + 可见范围缺口提示，填理由扩权 H）
  - 审计员：列表只见 D2 / E1 / H1；H1A 只有第 2 行可改（执行中 / 已完成，无裁剪），其余只读显示执行人，无新增 / 批量裁剪 / 勾选框；接口改第 1 行 403、第 2 行改不适用 403、裁剪端点 403
  - 粗裁 H1 → 确认移入回收站 → H1 两层软删（去向 `kind=trim`）、H1A/2 级联取消、审计员列表不再有 H1、直接访问 404；回收站页 H1「长期保留」只有恢复，点恢复提示「仍在程序裁剪中标为不执行」；恢复执行 → 底稿回来、任务回到待委派（须重新委派），审计员看得到（范围含 H）但没有可改的行
  - 实测发现并修复 5 处（见 design §8 批 7）：人员委派弹窗关闭不保存、参照项目列表恒空、回收站报错提示两遍、粗裁保存后行上「程序裁剪 ›」仍指向已移入回收站的底稿、控制台超 1900 行守卫（委派对话框抽到 `useProgramRowDelegate`，1916→1822）；变异 F30~F65 共 36 个 + 抽取后重跑 F01 / F05 / F08~F11，全部红在预期断言上
  - 回归：任务 21 的前端选集只按 import 找用例，漏了读源码的守卫（大组件行数守卫因此漏网）⇒ 选集加上读源码的用例（74 个文件 1248 例），9 红 + 1 个文件加载失败与 HEAD（58f7afb42）逐条相同；单区域 vue-tsc 与 HEAD 相同（团队分配两个文件 0 错，HEAD 的 TS2349 即参照项目缺陷）；ESLint 0 错误、65 条告警与 HEAD 相同；行数门通过
  - 清理：项目从项目列表删除（进回收站）、人员档案删除 ptgd_auditor；用户账号平台没有停用 / 删除入口，仍为启用，待用户决定
- [x] 23. 收尾：本文件勾选与验收摘要、INDEX.md 登记、memory 更新、清理探针
  - 探针目录与两个验证 worktree（含 node_modules 联接、单区域 tsconfig）已删除并 prune；`.kiro/specs/_archive` 无改动

## 验收摘要

- 链条：粗裁 / 细裁的结果决定生成（七个入口只生成保留项）、委派（已裁 / 回收站底稿拒绝，跨循环须填理由扩权）、可见（审计员按团队分配的循环，主管看全部）与编辑（程序表整表可见、只能改本人行）；粗裁移入 / 恢复与回收站、任务级联同一事务
- 科目判定按项目科目映射后的标准科目（四表规格 + 映射兜底），重药安徽误裁 1 个（H3）已恢复，已裁 22 个程序的 131 张底稿移入回收站
- 测试：变异 166 个（后端 B01~B101、前端 F01~F65）全部红在预期断言上；后端 192 个相关文件、前端 74 个文件的失败集合与 HEAD 逐条相同；浏览器实测 admin / 审计员两个视角全流程通过（实测中修 5 处）
- 未尽：执行人填写的状态 / 说明按今年存、按审计年度读（属 `audit-year-calendar-fallback-ratchet`）；测试用户无停用入口仍启用；其余范围外登记见 design §7、§8
