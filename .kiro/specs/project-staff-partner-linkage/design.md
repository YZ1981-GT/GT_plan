# 设计

## 现状确认
- BasicInfoStep.vue 从 /api/users/ 按 partner/manager 两角色独立筛选，未联动。
- staff_members.title 表示职级；现行人员界面维护 partner_name，partner_id 尚无完整维护链。
- projects.partner_id/manager_id 外键指 users.id，人员档案的 user_id 可空，不能直接传 staff.id。
- 现有 staff-partner-select 只处理人员管理页所属合伙人下拉，不覆盖项目表单。

## 实现
- 在 BasicInfo 增加 signing_partner_staff_id、manager_staff_id；利用既有 wizard_state.steps.basic_info.data JSONB 持久化，不增加表或迁移。
- 后端独立小服务解析并校验人员；有 partner_id 时优先精确匹配，否则按唯一的合伙人姓名匹配，同名且无明确归属 ID 时拒绝猜测。
- 新前端提交 staff ID，后端取人员档案 user_id 写既有账号字段，未绑账号则账号字段为空。此操作不创建账号、不变更权限或团队委派。
- 旧客户端未携带 staff 字段时保留既有用户 UUID 契约；编辑已有新格式项目时保留人员选择，不因旧客户端缺字段丢失。
- 使用 composable 分页加载完整人员档案并在本地计算候选，避免快速切换合伙人的请求竞态；不修改已有人员管理 composable。
- 用户 change 事件清空经理；初始化回填仅做唯一用户关联映射，不触发清空。旧账号不能唯一匹配档案时提示重新选择。
- 项目详情响应补回账号及人员字段，支持无向导状态兜底；确认页优先读人员 ID 对应姓名。

## 范围与收益
约 8 个生产文件：表单、composable、store、确认页、Schema、向导服务、人员解析服务、响应组装。收益是名单来源与人员档案一致且无账号人员可用；风险为双标识兼容，以创建/更新/回填验证控制。不扩展组织树、不改变人员状态筛选规则。

## 验证
运行现有向导前端/后端业务回归；隔离内存库验证真实保存与回读，浏览器用明确标识的模拟人员验证联动和请求载荷，不持久化业务测试人员或项目。按用户要求不新增永久测试文件；验证记录完成后追加。
