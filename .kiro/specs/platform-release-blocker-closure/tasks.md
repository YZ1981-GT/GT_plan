# 平台发布阻断项收口 — 任务

## A. 候选基线

- [x] 1. 从最新远端建立锁定 detached worktree，记录代码、DB、浏览器和健康检查基线
- [x] 2. 创建 requirements/design/tasks 三件套，冻结本批边界与共享库写入停点

## B. 可启动与保存真实性

- [ ] 3. 修复 AI 笔记导出契约；DshPanel 改首次打开再加载并提供局部失败态
- [ ] 4. 修复 Univer 非 2xx 假成功、冲突覆盖语义和业务回执校验
- [ ] 5. 自动保存增加 boolean 失败与编辑代际，保存期间新编辑不得被旧回执清除

## C. 复核主链

- [ ] 6. 抽取单笔/批量共用的提交复核服务，门禁 fail-closed，程序状态同事务
- [ ] 7. 编辑器与底稿列表切到唯一提交入口；两条旧提交接口返回 410
- [ ] 8. 退回→修改→编制完成→重提闭环；复核层级角色真正参与授权
- [ ] 9. 复核通过/归档后的所有底稿写入口统一后端锁定

## D. 项目隔离

- [ ] 10. Metabase 嵌入鉴权、正式密钥配置、删除 A5-1 debug 路由
- [ ] 11. 导入 SSE 绑定 project/job；接管请求 reason 与 manager 角色对齐
- [ ] 12. 复核意见绑定 wp/review 且 actor 取登录用户；review-config 加项目门
- [ ] 13. 用户公式 v2 实验接口 fail-closed 410；补安全端点测试

## E. 出具可信度

- [ ] 14. 报表前 TB 重算失败阻断；前端一键全套切正式 trio，旧入口 410
- [ ] 15. 合并附注导出改读根节点 ConsolNoteData；readiness 按单体/合并分流
- [ ] 16. trio snapshot 纳入内容/版本摘要，并补 retry 漂移测试

## F. 迁移与发布

- [ ] 17. 启动只读核对磁盘/DB 迁移集合；pending/failed/critical drift 使 readyz 503
- [ ] 18. 修复 build:verify、verified preview、Docker package scripts 与 Vite outDir
- [ ] 19. CI 覆盖 spec/**，将本批安全、runtime import、迁移完整性测试接成阻断门

## G. 验收

- [ ] 20. 后端相关单元/端点测试、前端相关 vitest、类型与 runtime import 通过
- [ ] 21. 一次性 PostgreSQL 从空库跑全迁移并验证 V229/readiness；不写共享库
- [ ] 22. 独立端口浏览器验证登录、项目、TB、底稿、复核、报表、附注、trio 主链
- [ ] 23. 五角色复核、语义审查、INDEX 登记；同步最新远端后单 commit 与版本化推送

## 外部停点

- [ ]* 24. 共享库执行待迁移、调查审计链 10 个分叉、重建膨胀索引与验证 invalid constraints——执行前单独取得用户批准