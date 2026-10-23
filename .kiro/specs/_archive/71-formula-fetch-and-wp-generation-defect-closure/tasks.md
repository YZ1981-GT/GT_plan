# 取数结果错误 / 底稿生成流程 / 测试欠账 收口 —— 任务

> 证据口径：「base」= 本 spec 改动前的 HEAD `54e73f695`，在干净 worktree 里跑；「本 spec」= 同一 HEAD + 本 spec 全部文件的临时提交。
> 变异 = 在独立 worktree 里逐条改坏生产代码、跑对应守卫、逐字节恢复（sha256 校验），「打红」才算守卫有效。
> 2026-10-23 18:09 本目录被并发会话移入 `_archive/71-…` 并改写了本文件（把本 spec 尚未提交的改动当成其他 spec 的既有代码，
> 写「本 spec 新增改动仅 1 个文件」）；以下按实际改动与实测证据重写，原任务编号不变。

## 1. 测试基础（R8 / R7）

- [x] 1.1 删 `pytest.ini` 的 `pythonpath = tests`，裸导入改 `tests.` 限定；浏览器抽样测试默认跳过；守卫三条（R8.1~R8.3）
  - 守卫 `test_pytest_import_isolation.py` 9 passed（ini 不得把测试目录放进 pythonpath、测试文件不得裸导入测试根目录模块、子进程不带 `-p no:playwright` 能完成收集）；变异 M8a（加回 pythonpath）/ M8b（裸导入回退）打红
  - 子进程用例（不带 `-p no:playwright` 起 pytest）改用 pytest 启动时的环境：同进程先收集过 `tests/e2e` 时，其 conftest 设的 sqlite `DATABASE_URL` 会让子进程导入 conftest 即 TypeError（定向回归发现；变异 M8e / M8f 打红）
  - 补（R8b，全量回归卡死时发现）：`tests/load_test.py` 符合 pytest `*_test.py` 收集规则，导入 locust 时 gevent `monkey.patch_all()` 让 TestClient / asyncio 死锁（全量 0 CPU、30 分钟无输出）。`conftest.collect_ignore` 排除它 + 收集结束钩子发现 threading 被打补丁即 `UsageError`；守卫 4 例在上述 9 例内，变异 M8c / M8d 打红；`pytest --co tests/load_test.py` 实测退出码 4 并给出原因
- [x] 1.2 d-cycle 测试替身按现行签名与鉴权链修复（`user=`、`get` / `get_bind`、管理员身份）（R7.1）
  - `_endpoint_doubles.py` / `_aux_sqlite.py`：替身补 `get` / `get_bind`（门禁代码原样执行、记录触达），直调端点显式传 `None`，公式行改真 `WpFormula` 瞬态实例，D6 归集替换统一入口 `aggregate_d_cycle_aux`
- [x] 1.3 d-cycle 其余失败逐条定根因并修（生产缺陷修代码 / 契约过时按现行契约更新）（R7.2）
  - 生产缺陷：D6 明细 seed 漏传年度（`aggregate_d6_detail_rows` 年度缺省 0 ⇒ 真实数据上恒空），改为必传、render 取 `ctx.year`，无年度不 seed
  - `tests/d_cycle_extraction`：base 84 条红 → 本 spec 533 passed / 11 skipped / 0 failed；变异 M7a~M7f（漏传年度 / 行构建写派生列 / 鉴权门短路 / D4 预设回旧口径 / 手工优先失效 / 子开关与改或）全部打红

## 2. 生成与保存流程（R4 / R5 / R6）

- [x] 2.1 `/working-papers/generate` 接收 `selected_templates` 并回报 `ignored_codes`；端点测试 + 跨语言契约（R4）
  - 请求模型 `extra="forbid"`（字段漂移报 422，不再静默丢弃）；`select_generation_codes` = 模板集 ∩ 选中；回执 `ignored_codes` + 前端 `summarizeWorkpaperGenerateResult` 如实提示；变异 M4a / M4b 打红
  - 浏览器实测（【测试】生成底稿裁剪验收有限公司_2025）：模板集 1025 个编码、裁剪弹窗只勾 D2 / E1 → 请求体 `selected_templates: ["E1","D2"]`，回执 `created: 2`，库里只有这 2 份底稿
  - 同一次实测发现请求带 `year: 2026`（底稿管理页不带 `?year=` 时取今年）：改按 `resolveEffectiveAuditYear`（路由 > 本项目审计年度 > 去年），`workpaperListYear.spec.ts` 3 例，变异 LY1~LY3 打红；改后浏览器（和平 2025，不带 `?year=`，只读）页面年度 = 2025
- [x] 2.2 `generate-from-codes` 走 `init_workpaper_from_template`；名称源；`blank_codes`；准则转换同款逻辑；端点测试断言真实页签（R5）
  - 新模块 `wp_generate_file.materialize_workpaper_file`（按编码生成 / 准则转换生成共用）；找不到模板仍建空白册但单列 `blank_codes`；落文件后失败删孤儿文件；变异 M5a / M5b 打红
  - 真实环境（同一【测试】项目，前置条件要试算表 ⇒ 临时插 1 行试算表、用完删除）：`["H1","ZZ9"]` → H1 落真实模板 26 个页签（底稿目录 / 程序表 H1A / 审定表 H1-1 …），名称「固定资产」；ZZ9 空白册并回报 `blank_codes: ["ZZ9"]`
- [x] 2.3 自定义底稿编辑器按项目口径保存；后端缺省按项目口径；前后端测试（R6）
  - 后端 `template_type` 改可选，缺省取底稿所属项目的 `projects.template_type`（单条 / 批量同口径）；前端 `GtCustomWpEditor` 不再传写死的 `soe`；变异 M6a / M6b 打红

## 3. 推送规则科目（R1）

- [x] 3.1 binding 科目改从口径单一来源取（H6 / H8 / H9 / I1 / I2）；I5 无科目声明（R1.1~R1.3）
  - 另按同根因扩到 G6 / G8、K1、J / L / M 附注直推、H8 / H9 附注主表合行（见 design §9.1）；变异 M1a~M1j 全部打红
- [x] 3.2 规则清单与 Tier A 预设：H8 / H9 / I2 / I6 公式改正，I5 删锚点规则（R1.1 / R1.4）
- [x] 3.3 守卫：上下文缺口清单清零、binding 科目必须是标准码；重生成覆盖率与独占键生成物；相关测试按新口径更新（R1.5）
  - `test_formula_push_account_single_source.py`（新）+ 推送相关 18 个文件 760 passed；余 2 条红（L6 / N3 sync_registry）base 同样红，非本 spec 引入

## 4. 地址库 50000（R3）

- [x] 4.1 后端上限常量、参数校验、`total` / `returned` / `truncated` / `truncated_domains`；端点测试（R3.1 / R3.2）
  - `test_address_registry_limit.py` 10 passed；变异 M3a~M3d 打红；真库只读：`limit=50001` → 422
  - 定向回归发现本 spec 两个新测试同进程互相干扰：`monkeypatch.setattr` 在单例实例上替换 `_get_domain`，撤销时把原方法写成实例属性，
    挡住之后的类级替换（地址库用例取到真实地址 8323 条）⇒ 改为类级替换，地址库用例先隔离单例；两文件同进程 22 passed
- [x] 4.2 前端常量、`shallowRef`、截断提示与 `isDomainComplete`、刷新单飞；公式编辑弹窗同常量；跨语言常量守卫（R3.1 / R3.2 / R3.4）
  - 变异 F3b / F3c / F3f 打红
- [x] 4.3 `FormulaRefPicker` 附注 / 报表插入用登记写法（R3.3）
  - 变异 F3d / F3e 打红；截断提示只列选择器页签真受影响的域（浏览器实测后修，变异 FH1~FH4 打红）
  - 浏览器实测（和平药房_2025，只读）：地址库取回 50000 条、只截断辅助余额，选择器不再误提示；「其他附注」页签 1425 条（= 后端该域条数）；插入得 `NOTE('八、1','合计','期末余额')`，后端引用校验有效（原拼法 `…'期末')` 判 not_found）；未保存

## 5. PREV 三参（R2）

- [x] 5.1 `prior_year_context`：上年数据来源 + 上年项目查找单一来源（报表上期改调）（R2.1）
- [x] 5.2 三参解析器：字段定义（本项目 > 全局 > 预设，审定表回退「未审数」）、允许的取数函数、上年严格求值（R2.1 / R2.2）
- [x] 5.3 接入严格路径、底稿可编辑公式（去拒收）、统一预载层与 L1（三参值 / 缺数）、重新预填；两参同一上年来源 + 列名（R2.2~R2.4）
  - **初次预填不写三参值**（偏离设计，依据见 design §9.1）
- [x] 5.4 测试（真 ORM 行：上年项目四种情形、字段定义三层、函数白名单、缺数不写 0）+ 函数支持矩阵口径（R2）
  - `test_prev_prior_wp_field.py`（新）12 passed；R2 相关 7 个文件 76 passed；变异 M2a~M2j 全部打红
  - 真库只读：和平 2025 → 上年来源和平 2024；192 格三参中 130 格有值，其中 123 格（纯试算表定义）逐格对 SQL 0 差异；56 格无定义、4 格占位、2 格序时账 / 底稿引用，均报原因不写 0；安徽 2025 全部报「没有上年项目」
  - 浏览器实测（【测试】项目 D2 底稿 → 底稿面板 → 公式）：把提取公式改成 `PREV('D2','审定表D2-1','审定数')` 保存成功，提示「公式已保存，但 D2-adj-tb-amount 没有算出值（已留空）：…本项目没有 2024 年试算表，没有上年项目…」；随后「恢复默认」，库里该底稿公式行为 0
  - 实测中发现底稿面板恒按日历年传年度（2025 年度项目在 2026 年保存提取公式，本年试算表有的科目也判「引用地址不存在」），已修：编辑器把项目审计年度传给面板（变异 FY1~FY3 打红）
  - 「未审数」定义里有换不到列的试算表取数（单参 TB 等）⇒ 不取并写明原因（变异 M2k / M2l 打红）

## 6. 回归与交付

- [x] 6.1 一次性变异（每项至少 2 条）+ 干净 worktree 对比 HEAD 失败集合 + 单区域 vue-tsc
  - 变异 59 条全部打红（R1 / R4~R6 16、R7 6、R8 2、R2 / R3 后端 / R8b 16、R3 前端 5、提示与面板年度 7、底稿管理页年度 3、三参换列写法 2、子进程环境 2）
  - 全量 pytest（同参数，干净 worktree）：base `54e73f695` 2811 failed / 62927 passed / 584 errors；本 spec 2719 failed / 63125 passed /
    583 errors。base 红而本 spec 不红 109 条；本 spec 新红 16 条逐条处理（13 条修掉、3 条为 base 上同样间歇的失败），见 design §9.2
  - 最终提交树定向回归（HEAD `5f4e8b54c` + 本 spec，后端 96 个目标 / 前端 330 个文件）：同组目标在 base 整组复跑对比，新增失败 0
  - vitest：相关 92 个文件 1043 passed；11 条红在 base 逐条同样红（同一断言消息）
  - 单区域 vue-tsc：改动文件的报错集合与 base 相同（探针 TS2322 命中，证明检查在跑）；`WorkpaperEditor.vue` 单区域也内存溢出，只改了一处传参
- [x] 6.2 真库只读核对（推送规则取数、PREV 三参在和平 2025 / 2024 上的结果、地址库各域条数）+ 浏览器实测（地址选择器、生成底稿）
  - 证据见上文各任务；写入型实测只在临时【测试】项目 `c3774ad5`（用完走删除接口进回收站）
- [x] 6.3 提交并推送到 `spec/disclosure-note-doc-upload-and-batch-fill`；INDEX / memory 更新
  - 实施提交 `d9f08b55c`（本 spec 103 个文件 + INDEX / memory 本 spec 的两段），推送后 `git ls-remote` = `d9f08b55c`；pre-push 的两道检查
    （分支命名 / 暂存树自洽）在推送树上手工跑过、均 exit 0（钩子在 detached HEAD 下跳过）
  - 收尾提交：全量对比里本 spec 新红的 3 组测试按新契约改写 / 桩住口径查询、resolver 迁移矩阵重生成，INDEX / memory 状态改为 19/19
