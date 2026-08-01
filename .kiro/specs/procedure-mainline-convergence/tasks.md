# Implementation Plan: 程序裁剪与委派主链收敛

## Overview

把程序粗裁、底稿主编和程序行委派收敛到各自单一真源。所有任务均为必做；只有实现与对应验证完成后才可标记 `[x]`，`[-]` 表示正在执行。

## Tasks

- [x] 1. 建立增量 spec 与真实基线
  - [x] 1.1 创建三件套并更新 INDEX 顶部执行说明
  - [x] 1.2 记录旧 API、直接写、rollout 与 epoch 接线基线
- [-] 2. 收敛前端粗裁与参照方案
  - [ ] 2.1 `ProcedureTrimming.vue` 改用 canonical preview/apply
  - [ ] 2.2 参照项目按源 wp_code/status 转换，不读 UUID scheme
  - [ ] 2.3 模板、自定义模板、Workpaper Lead API 收敛到 apiPaths/commonApi
  - [ ] 2.4 删除旧 `getMyProcedureTasks` 聚合与旧生产 API 导出
- [ ] 3. 下线后端旧写链并补全授权
  - [ ] 3.1 旧 trim/scheme/execution/assign 稳定返回 410
  - [ ] 3.2 init/custom/template/lead/materialize 写入口统一 Delegator 守卫
  - [ ] 3.3 新增语义明确 Workpaper Lead API，复用 lead 原子事务
- [ ] 4. 修复物化主链
  - [ ] 4.1 preview 同步物化后直接返回 ready
  - [ ] 4.2 materialize 兼容 POST 返回 succeeded，job GET 410
  - [ ] 4.3 移除生产 preview 对进程内 job store 的依赖
- [ ] 5. 收敛程序行状态机
  - [ ] 5.1 `_UNSET` 修复 old/new assignee/reviewer 快照
  - [ ] 5.2 reassign 支持 reviewer 变化并新增 reviewer-only `set_reviewer`
  - [ ] 5.3 reopen 清空执行人历史准确且 no-op 零副作用
- [ ] 6. 建立唯一行委派协调器
  - [ ] 6.1 新增 Coordinator 与只记录 visibility effects 的事务原语
  - [ ] 6.2 DelegationService 分类 reviewer_update 并全部走 Coordinator
  - [ ] 6.3 atomic 整批回滚，best_effort 每任务 savepoint
- [ ] 7. 接入授权缓存与 rollout fail-fast
  - [ ] 7.1 Wp_Bound_Gate 注入持久 epoch cache
  - [ ] 7.2 rollout 值域统一并增加 paused
  - [ ] 7.3 lifespan 启动校验与 `.env.example` 说明
- [ ] 8. 扩展架构守卫并清理真实债务 baseline
  - [ ] 8.1 禁止旧前端/服务调用及人员字段旁路写
  - [ ] 8.2 禁止 materialize job 回流并强制 epoch cache 接线
  - [ ] 8.3 只移除本轮实际清理的 baseline 条目
- [ ] 9. 自动化验证
  - [ ] 9.1 后端 reviewer/事务/materialize/410/rollout/epoch 针对性测试
  - [ ] 9.2 前端 canonical/参照/409/两层委派 Vitest
  - [ ] 9.3 strict guard、相关回归测试与 Vite 校验
- [ ] 10. fresh-navigation Playwright 验收
  - [ ] 10.1 经理粗裁、参照、主编与行委派 round-trip
  - [ ] 10.2 reviewer-only、助理执行、复核退回/通过、撤权拒绝与旧端点 410
  - [ ] 10.3 通知/SSE、刷新持久化与 console 0 error
- [ ] 11. 收尾
  - [ ] 11.1 按实测结果更新 tasks、INDEX 与 memory，未验证项不得标绿

## Notes

- 不修改本地 `.env`，不强制切换 `task_source`，不执行生产配置或数据删除。
- 旧写接口先稳定返回 410；Git 与迁移承担回滚，不保留第二套线上写链。
- 修改后必须运行 targeted pytest/Vitest、strict guard、Vite 校验及 fresh-navigation Playwright。

## Task Dependency Graph

```text
1 → 2 → 3 → 4
        └→ 5 → 6
4,6 → 7 → 8 → 9 → 10 → 11
```
