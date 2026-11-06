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

- [ ] 5. 浏览器实测（design §5 最后一行）
  - `[ ]*` 依赖可用的 D2 底稿与可写环境（【测试】项目或隔离临时库）
  - AC：导出模板 → 填写 → 导入 → 合并 → 保存 → 刷新回读；导出数据文件内容与界面一致；console 无新增错误

- [ ] 6. 登记与提交
  - INDEX.md 登记状态；干净检出跑本 spec 测试；行数门；推送按 `push_version.py`
