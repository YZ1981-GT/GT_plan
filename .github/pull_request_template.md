## 变更说明

<!-- 简要描述本次变更的目的和范围 -->

## 变更类型

- [ ] 新功能
- [ ] Bug 修复
- [ ] 重构
- [ ] 文档
- [ ] 配置/CI

## 全局治理自检（新增代码必填）

> 参考 `platform-maintenance-governance` spec，新增代码应逐项确认。
> 不涉及的项打 N/A。

- [ ] **全局组件**：新增页面是否使用了已有全局组件（GtPageHeader/GtToolbar/GtAmountCell/GtEmpty/GtTableExtended）？如否，请说明原因
- [ ] **金额 Decimal**：新增金额字段是否使用 Decimal 序列化？是否避免了原生浮点计算？
- [ ] **枚举字典**：新增状态/类型字段是否进入 `system_dicts`？是否避免了前端硬编码中文 label？
- [ ] **路由权限**：新增 API 路由是否在 `router_registry` 注册？是否配置了权限和错误码？
- [ ] **AI 确认**：新增 AI 输出是否有人工确认机制（suggestion→draft→confirmed）？
- [ ] **穿透契约**：新增跨模块引用是否使用 LinkageContract？是否避免了手写 route 字符串？
- [ ] **跨 spec 共享原子**：如果依赖 ProjectContext/PermissionMatrix/LinkageContract/EvidenceRef/useEditStateMachine，确认该原子已 merge main 且测试绿
- [ ] **数据库三层一致**：如涉及 DB 变更，migration + ORM + service 三层是否一致？

## 测试

- [ ] 新增/修改的代码有对应测试
- [ ] `vitest run` / `pytest` 通过（无新增失败）

## 关联

<!-- 关联 Issue / Spec / ADR -->
