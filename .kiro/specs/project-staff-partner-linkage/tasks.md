# 任务

- [x] 1. 完成人员档案选择的后端保存、校验及详情回填。既有业务测试 10 passed，隔离 SQLite 保存回读探针 29 项通过。
- [x] 2. 完成前端候选、经理联动、旧项目回填及错误状态。既有回归 19 passed，四个改动生产文件局部 vue-tsc 通过。
- [x] 3. 运行既有业务回归、隔离保存回读和 Playwright 页面验证，记录实际结果。见下方验证记录。
- [ ] 4. 重启共享后端使新契约生效，再核对运行时 Schema。当前 9980 的 BasicInfoSchema 尚无新增 staff 字段，未擅自重启。

## 验证记录（2026-10-29，本地 sw-dev1.0，未提交）
- 后端现有 TestCreateProject / TestGetWizardState / TestUpdateStep：10 passed；SQLite 外键开启的隔离探针 29 项通过，包含真实生产 create/update/get 与详情回读，无账号、同名、归属 ID 优先、旧协议保留、清空及非法组合。不创建账号或团队委派；临时探针已删。
- 前端既有 BasicInfoStep.group / BasicInfoStep.recommend / wizard.group：19 passed。两份组件测试仅补 staffApi mock，避免新增网络泄漏；未新增永久测试。
- 四个前端生产文件局部 vue-tsc 通过；发现同表单原有 company_subtype=null 索引错误，一并加空值判断。git diff --check 通过。
- Playwright 隔离模拟：205 个人员跨两页，合伙人过滤、经理按姓名/档案 ID 归属、切换清空、无账号人员选择、真实表单提交请求、模拟保存回填与编辑提交、旧用户 UUID 唯一映射、清空禁用、不完整列表拒收、重试恢复均通过。所有写请求拦截，未写真实人员或项目库。
- 真实只读验证：人员 API 200，共 4 人、1 位合伙人；项目页显示该合伙人，经理下拉与档案归属一致（2 人），未选合伙人时禁用。截图 .playwright-mcp/page-2026-10-29T07-52-12-957Z.png。
- 运行时阻塞：3030 代理到 Python/FastAPI 9980，health 200；但当前 /openapi.json 的 BasicInfoSchema 尚不含两 staff 字段，说明运行进程未加载本次契约。不能把前端联动通过当成线上保存完成。共享服务未重启、真实 PostgreSQL 写入未实测。
- 未新增迁移；人员 ID 使用既有 JSONB，原项目账号外键语义不变。工作区既有人员管理改动原样保留，未提交 Git。
