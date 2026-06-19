# Implementation Plan

## P0: Univer 渲染 + 准则说明面板

- [x] 1. 确认 A4/A4-1 当前渲染路径正确（A4→a-program-console, A4-1→Univer/audit-sheet）
- [x] 2. 提取准则列报要求说明（解释3号八(三)(四)）到结构化数据
- [x] 3. 前端 guidance 面板展示准则说明（折叠面板3块：分部利润/其他信息/客户）
- [x] 4. 集成验证

## P1: 结构化渲染

- [x] 5. componentType 路由注册 `segment-report`
- [x] 6. 前端 GtSegmentReport.vue 组件（动态分部列+合计+本期/上期Tab）
- [x] 7. 地区信息交叉表 + 主要客户列表
- [x] 8. 准则说明 hover tooltip（蓝色文字对应的列报要求）
- [x] 9. 集成验证 + Playwright E2E
