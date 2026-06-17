# Implementation Plan

## P0: audit-sheet 渲染 + 准则说明

- [ ] 1. 确认 A4-1 当前 classification 路由（应走 audit-sheet）
- [ ] 2. render-config 返回 guidance_items（准则说明数据）
- [ ] 3. audit-sheet 组件增加 guidance tooltip（section 标题旁 ⓘ 图标）
- [ ] 4. 验证：打开 A4-1 能看到准则提示 + 正常编辑

## P1: 动态分部列

- [ ] 5. parsed_data.segment_columns 存储动态分部名称
- [ ] 6. 前端 audit-sheet 检测 segment_columns 渲染动态列
- [ ] 7. 增删分部列 UI（最多 10 列）
- [ ] 8. 合计列自动公式

## P2: 数据联动（预留）

- [ ]* 9. 营业收入/费用从试算表按分部取数
- [ ]* 10. 资产/负债从合并报表分部附注取数
