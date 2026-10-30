# 任务：批量建项与合并企业树导入收口

需求见 requirements.md，设计见 design.md。按交付单元执行；完成项必须有代码和通过证据，浏览器写入只使用【测试】项目。

- [x] 0. 现状、设计与基线
  - [x] 0.1 追踪平台/合并三处入口、五个 API、模板/解析/建项/自动根/树/链接链路，区分空白模板回导与现有树回导
  - [x] 0.2 浏览器只读复现原样模板 4 行可导入、确认按钮首屏外；核对事务、权限、重复键、多年度和测试缺口
  - [x] 0.3 完成 requirements/design/tasks；确认只复用一套内核，迁移号实施时动态取
  - [x] 0.4 登记 INDEX；基线：后端 58 passed / 16.90s，前端 7 passed / 1.88s（既有 Vue 未 stub warning）

- [x] 1. P0 正确性与安全
  - [x] 1.1 拆出工作簿协议：数据 sheet 零示例、示例独立、四类下拉、版本/表头/整数年度/文件膨胀限制、openpyxl 离事件循环
  - [x] 1.2 预校验重复键改 `(code,year,scope)`，一次预取 DB，库存覆盖后构树；循环/重复/构树异常阻断
  - [x] 1.3 修导入事务：legacy 逐行 SAVEPOINT、计划 apply 整批原子；失败回执零假成功，自动根按 `(ultimate,year)`
  - [x] 1.4 batch create 仅 admin/partner/manager；选中项目导出全集合 readonly 鉴权；错误不泄露内部异常
  - [x] 1.5 manager 新建项目同事务挂经理委派与 edit 成员；新根同样处理，复用根团队不动

- [x] 2. 单次上传计划与性能
  - [x] 2.1 动态分配 V220/R220；新增计划 ORM、状态/幂等键/过期/JSONB/索引三层一致，临时 schema PG 正反向通过并已由 MigrationRunner 应用
  - [x] 2.2 实现 canonical request/hash、DB 动作分类、summary、最终树预览和错误工作簿
  - [x] 2.3 新增 validate/apply/status/errors API；生产 UI 确认只传 validation_id + idempotency_key，旧 import 走安全兼容路径
  - [x] 2.4 apply 锁计划、受影响年度项目锁、关系全集 CAS，整批原子创建/更新/自动根/成员/链接/回执；响应丢失重放
  - [x] 2.5 批量预取、延迟 ORM flush 和新项目经理批量初始化消除逐行往返；真 PG 回滚基准 500 行：admin 计划/执行 324.8/344.9ms，manager 353.9/521.9ms

- [x] 3. 现有树导出与关系回导
  - [x] 3.1 安全保留选中项目导出；新增合并根当前树导出，服务端推导成员并逐项目鉴权
  - [x] 3.2 模板追加 action/project_id/base_hash；现有行只许更新三码关系，新行可创建，跳过显式可见
  - [x] 3.3 扩展集团关系单一入口支持显式 parent/ultimate/relation、counterpart 同步和延迟年度链接重算
  - [x] 3.4 批量关系更新写 ORM + wizard_state + 审计；企业级双口径 CAS、年度全集锁、最终图循环/冲突、归档与无权 fail-closed

- [x] 4. 前端体验
  - [x] 4.1 BatchImportDialog 增加 project/consolidation mode；合并模式提供新模板和当前树导出
  - [x] 4.2 改 80vh 步骤式弹窗、固定操作栏、两级展开、summary 与异常/改动标签，窄屏 CSS 收口
  - [x] 4.3 上传一次、计划确认/轮询/幂等恢复；失败保留文件和预览，支持错误 Excel，展示真实中文错误
  - [x] 4.4 平台、左栏与合并入口刷新正确；合并成功可进入新根，未选根时不误导

- [x] 5. 自动化验证
  - [x] 5.1 后端模板/解析/动作/多年度/原子回滚/成员/幂等/CAS 测试；故障注入发生在真实 production 路径下一层 flush
  - [x] 5.2 TestClient 角色矩阵、混合授权 ID、计划归属、归档与响应信封；PG 迁移/回滚/唯一约束
  - [x] 5.3 前端 mode/步骤/上传一次/错误恢复/固定 footer/TreeV2 测试，scoped vue-tsc、ESLint 与相关回归
  - [x] 5.4 关键反向断言覆盖：改表头、空模板、同键异载荷、flush 中断、关系 CAS、隐藏 counterpart 变化、网络丢响应均在预期断言打红；相关选集全绿无需 HEAD 失败归因

- [ ] 6. 浏览器与收尾
  - [ ] 6.1 原样新模板 0 行、错误模板中文提示、500 行预览性能与桌面/390px 弹窗走查
  - [ ] 6.2 【测试】集团完成导出→改关系→预览差异→应用→树刷新→幂等重放；恢复原关系并清理新建项目
  - [ ] 6.3 对账 DB 项目/成员/委派/计划/审计和临时文件；更新验收记录、INDEX 与记忆，诚实登记外部依赖

## 验收记录

待实施。