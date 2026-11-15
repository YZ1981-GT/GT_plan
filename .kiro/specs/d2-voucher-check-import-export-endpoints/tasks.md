# D2-7 凭证检查表导入导出端点 — 任务

> 2026-11-04 只写三件套，未实施（用户定：另立 spec）。来源：spec `voucher-workflow-linkage-lineage-closure` design §15.4。

- [x] 1. 常量与前后端对拍（design §2）
  - 后端常量：两工作表名、17 列表头；守卫读前端 `useD2VcImportExport.ts` 字面量逐值比对
  - AC：任一侧改名 / 改顺序即红（变异证明）

- [x] 2. 导出模板与导出数据端点（R1、R2，design §3）
  - 新模块 `_d2_vc_import_export.py` + `router_registry/workpaper.py` 登记；读门；请求体校验；文本单元格写法
  - AC：端点级用例（读门、404、422、公式文本、表名表头）全绿；变异去掉读门 / 文本写法打红

- [x] 3. 导入数据端点（R3，design §3）
  - 写门；扩展名 / 大小 / 解析失败；日期与数值转换；5000 行截断 + warnings
  - AC：端点级用例全绿；往返用例（导出 → 导入逐格相等）；变异去掉写门 / 日期转换 / 截断打红

- [x] 4. 前端提示（R4，design §4）
  - 三个请求带 `_silent: true`；失败只显示一条中文提示（blob 响应用 FileReader 解析 JSON；后端 detail/message 优先取；网络错误用中文兜底）
  - AC：组合式函数用例覆盖成功、后端 4xx 原因、网络错误三种；单区域 vue-tsc 不新增

- [x] 5. 浏览器实测（design §5 最后一行）
  - `[x]` 依赖可用的 D2 底稿与可写环境（【测试】项目或隔离临时库）—— 用隔离临时库 `gt_tmp_d2vc`（pg_dump 共享库，排除 tb_ledger/tb_aux_ledger/tb_aux_balance/tb_aux_balance_summary/logs/task_history 六张大表数据；底稿文件复制到 `tmp_d2_vc_browser/storage` 并改指临时库，共享 `backend/wp_storage` 未动），后端 9981 + 前端 3031，D2-7 底稿 `a544a961…`（项目 `4c77f3e8…`【测试】公式同步甲有限公司_2025）
  - AC：导出模板 → 填写 → 导入 → 合并 → 保存 → 刷新回读；导出数据文件内容与界面一致；console 无新增错误
  - 证据（2026-11-15，隔离临时库 gt_tmp_d2vc + 后端 9981 + 前端 3031，node playwright 无头自起，脚本与产物 `tmp_d2_vc_browser/`）
    - 路由在位：三个端点未登录均 **401**（非 404），`s0-route-presence.json`
    - **s1 导出模板 ✅** 下载 `D2-7_凭证检查表模板.xlsx`；openpyxl 打开两工作表名逐字一致（本期增减变动检查 / 期后收款调整检查）、第一行 17 列表头与前端 `COLUMN_HEADERS` 逐值相同且全为 `s`、`freeze_panes=A2`；提示「凭证检查表模板已导出」
    - **s2 填写 ✅** 本期区 1 行（`VC-EXIST-001` / 2025-03-15 / 1000 / 核对内容1=原核对-金额一致 / 备注=界面原有行），期后区 1 行（`VC-POST-UI` / 2025-08-01 / 贷 888）；走 Excel 方式（双击 → 输入 → Enter）
    - **s3 导入合并 ✅** 上传两工作表夹具（①同凭证身份 ②新凭证 ③`=`/`+`/`-`/`@` 开头文本 ④datetime 日期 ⑤整数与小数金额 + 空行 + 无凭证号行 + 期后区独有行）；回执 `sheets` 两个精确命名工作表、`warnings=[]`；合并后本期 **4 行**（`VC-EXIST-001` 未新增且原核对结果保留 = 同凭证身份合并不覆盖）、期后 **2 行**（两区不串），提示「成功导入 5 行数据」
    - **s4 保存 ✅** 6 次 `PUT /checklist-responses` 全 **200**，`require_if_match=true`，`if_match` 逐次取上次回执版本（严格 CAS）
    - **s5 刷新回读 ✅** 整页 reload 后两区 4+2 行逐格与保存前一致；唯一文本差异是附件列 `📎=SUM(A1:A2)` → `📎 =SUM(A1:A2)`（渲染空格，DB 值逐字节相同，已核 `db-verify.txt`）
    - **s6 导出数据 ✅** 文件两工作表表头逐值正确、行数 4+2 与界面一致；按列名逐值对账 **0 处不符**（`s6-compare.txt`）；`=`/`+`/`-`/`@` 开头共 **6 个单元格全为文本单元格**（`data_type == 's'`，无一是公式）
    - **s7 R4 失败提示 ✅** 非 `.xlsx` → 只一条「仅支持 .xlsx 文件」；损坏 xlsx → 只一条「文件无法解析，请确认上传的是未损坏的 .xlsx 文件」；两次均**无**英文 `Request failed with status code …`
    - console 归因：**page error 0**；console error 2 条，均为 s7 故意造的失败所对应的 `Failed to load resource: 400`（浏览器对 4xx 的固有记录，非应用报错）。`requestfailed` 全为导航/刷新时被取消的后台 GET（`net::ERR_ABORTED`），非本 spec 引入
    - 走查中发现并修复（本 spec 范围）：`exportTemplate` 错误分支只读对象字段、**不解析 blob 响应体**，后端写明的原因被兜底文案盖掉（实测界面显示「导出模板失败，请检查网络后重试」而非后端原因；同一时刻 `exportData` 正常）⇒ 三个请求收敛到同一个 `resolveFailureReason`（blob → 文本 → JSON；字符串 detail → message → 对象 detail.message → 非 JSON 原文），新增用例「模板导出读取 blob message」钉住；变异（退回旧实现）该用例**打红**、恢复后 34 passed
    - 清理对账（隔离库内）：临时库 `gt_tmp_d2vc` 里写入仅 `checklist_responses` 的 `D2-vc-current-rows`（4 行）/ `D2-vc-post-rows`（2 行）两行（`working_paper` 仅 `updated_at`/`content_version` 变化）；按走查前快照 `db/before.json` 恢复后 `identical_to_before = True`（`logs/db_restore.txt`），二次 `after` 比对 0 处差异（`logs/db_after2.txt`）
    - 收尾对账（2026-11-15 实做，先前此段描述为未执行的计划态，已更正）：①停掉本次走查起的进程 —— 后端 9981 为 `.venv` `run_uvicorn.py` 的 reload 父子（PID 52668→92924，启动 14:59:37，父 `run_backend.bat`）、前端 3031 为 `node vite.js --port 3031`（PID 77600，启动 15:00:54，父 `run_frontend.bat`，子 esbuild 35268），按 PID 逐个 `Stop-Process -Force` 后 `Get-NetTCPConnection -LocalPort 9981,3031 -State Listen` 计数 **0**、六个 PID 全 gone；②`DROP DATABASE IF EXISTS gt_tmp_d2vc` 前先核 `pg_stat_activity` 该库连接数（停后端后 **0**），DROP 返回 `DROP DATABASE`，复查 `pg_database` 中 `gt_tmp%` **为空**（`gt_e2e_d2vc` / `gt_adj_accept_1115` / `gt_display_candidate_20261106` / `gt_llm_probe` 与共享 `audit_platform` 均未动）；③共享库未被本次走查写入 —— `audit_platform` 里 `wp_id='a544a961…'` 只有走查前就有的 `D2-adj-tb-amount`（cv=5、created 2026-10-29 09:33:54、updated 2026-11-15 02:50:53、remark `0`，与快照逐值一致），`D2-vc-current-rows` / `D2-vc-post-rows` 在共享库 **count=0**，`working_paper` 该行仍 `content_revision=0 / file_version=1 / updated 2026-10-29 09:33:47 / unknown / not_started / not_submitted / draft`；④共享 `backend/wp_storage` 未改（3459 个文件，2026-11-15 改动 **0** 个，最新写入停在 2026-11-09 14:47:54；底稿文件副本在 `tmp_d2_vc_browser/storage`，11 个文件）；⑤`tmp_d2_vc_browser/verify_wt` 不存在、`git worktree list` 无该条目（无需 prune），`tmp_d2_vc_browser/` 按计划保留供任务 6 引用

- [-] 6. 登记与提交
  - INDEX.md 登记状态；干净检出跑本 spec 测试；行数门；推送按 `push_version.py`
