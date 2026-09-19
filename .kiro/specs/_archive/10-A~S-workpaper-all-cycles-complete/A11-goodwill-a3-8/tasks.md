# Implementation Plan

## P0: Univer 渲染 + 编制说明面板

- [x] 1. 确认 A3-8/A3-8-1 当前 Univer 渲染正常（class_code 路由验证）
- [x] 2. 提取编制说明内容到结构化数据（后端解析模板或硬编码 JSON）
- [x] 3. 前端侧栏 guidance 面板展示编制说明（6条规则+WACC/CAPM公式+参数定义）
- [x] 4. 集成验证

## P1: 结构化渲染 + 计算引擎

- [x] 5. componentType 路由注册 `goodwill-impairment`
- [x] 6. 后端 WACC/DCF 计算引擎服务
- [x] 7. 前端 GtGoodwillImpairment.vue 组件（减值测试表+可收回金额计算）
- [x] 8. 数据持久化（计算参数+结果存 parsed_data）
- [x] 9. 集成验证 + Playwright E2E
