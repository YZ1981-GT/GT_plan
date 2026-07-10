# Implementation Plan: 往来款账龄配置动态化

## Overview

将 D2/D3/F1/K1/K3/G5 六类往来款明细表的账龄段配置从硬编码提升为项目级动态配置。后端使用 Python (FastAPI)，前端使用 TypeScript (Vue 3 + Element Plus)。实现分为：后端服务+API → 前端 composable → 各明细表改造 → 导入导出适配 → D6 ECL 联动 → 旧数据迁移。

## Tasks

- [x] 1. 后端 AgingConfigService 核心逻辑
  - [x] 1.1 创建 AgingConfigService 模块和数据模型
    - 创建 `backend/app/services/aging_config_service.py`
    - 定义 `AgingPreset` 枚举 (THREE_YEAR/FIVE_YEAR/CUSTOM)
    - 定义 `AgingSegment` Pydantic 模型 (key/label/dayFrom/dayTo)
    - 定义 `AgingConfigPayload` 和 `AgingConfigResponse` 模型
    - 实现 `PRESET_SEGMENTS` 常量 (三年段4区间/五年段6区间的预定义)
    - 实现 `DEFAULT_SUBJECT_PRESETS` 常量 (D2/K1/K3/G5→FIVE_YEAR, D3/F1→THREE_YEAR)
    - 实现 `resolve_segments(preset, custom_segments)` 方法
    - 实现 `validate_config(payload)` 方法 (段数2-10/非空label/label唯一)
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_

  - [x]* 1.2 编写 AgingConfigService 属性测试
    - **Property 1: Preset resolution returns correct segments**
    - **Property 2: Default preset inference by subject**
    - **Property 3: Configuration round-trip preservation**
    - **Property 4: Validation rejects invalid configurations**
    - **Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5, 2.3**

  - [x] 1.3 实现 get_config 和 save_config 持久化逻辑
    - 实现 `get_config(project_id)` 从 wizard_state.aging_config 读取配置
    - 无配置时返回默认值 (基于 subject 推断 preset)
    - 实现 `save_config(project_id, payload)` 写入 wizard_state
    - 实现 `get_effective_segments(project_id, subject)` 含 subject_overrides 解析
    - _Requirements: 1.2, 1.3, 2.5, 10.1_

  - [x]* 1.4 编写 get_config/save_config 单元测试
    - 测试默认配置推断逻辑
    - 测试 subject_overrides 覆盖逻辑
    - 测试无 wizard_state 时的兜底行为
    - _Requirements: 1.2, 2.5, 10.1_

- [x] 2. 后端 API 端点
  - [x] 2.1 创建 aging_config 路由模块
    - 创建 `backend/app/routers/aging_config.py`
    - 实现 `GET /api/projects/{project_id}/aging/config` 端点
    - 实现 `PUT /api/projects/{project_id}/aging/config` 端点 (含校验→422)
    - 实现 `GET /api/aging/presets` 端点 (返回预定义段列表)
    - 在 router_registry 注册路由
    - _Requirements: 2.1, 2.2, 2.3, 2.4_

  - [x]* 2.2 编写 API 端点单元测试
    - 测试 GET 正常返回结构
    - 测试 PUT 校验失败返回 422 (空 label/重复 label/段数超限)
    - 测试 PUT 成功保存并返回配置
    - 测试 GET /api/aging/presets 返回预设定义
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

- [x] 3. Checkpoint - 后端核心服务验证
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. 前端 useAgingConfig composable
  - [x] 4.1 创建 useAgingConfig composable
    - 创建 `frontend/src/composables/useAgingConfig.ts`
    - 定义 `AgingSegment`/`AgingBand`/`UseAgingConfigReturn` TypeScript 接口
    - 实现 `useAgingConfig(projectId, subject?)` composable
    - 实现 GET API 调用获取配置
    - 实现 segments→bands 转换逻辑 (生成 priorField/currentField/auditedField)
    - 实现 per-project-session 缓存逻辑
    - 实现 EventBus 监听 `aging-config:changed` 事件刷新配置
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

  - [x]* 4.2 编写 useAgingConfig 属性测试
    - **Property 5: Config-to-bands transformation with subject override**
    - **Property 6: Three-period subject row generation (D2/K1/K3/G5)**
    - **Property 7: Two-period subject row generation (D3/F1)**
    - **Validates: Requirements 3.1, 3.2, 3.4, 4.1, 5.1, 5.2, 6.1, 6.2, 6.3**

- [x] 5. 前端旧数据迁移工具
  - [x] 5.1 创建 useAgingMigration composable
    - 创建 `frontend/src/composables/useAgingMigration.ts`
    - 实现 `D2_FLAT_TO_SEGMENT` 映射常量 (18 个 flat→nested 字段映射)
    - 实现 `isLegacyD2Format(raw)` 检测函数
    - 实现 `migrateD2FlatToNested(raw)` 转换函数
    - 实现 `migrateD3F1Keys(raw, segments)` 转换函数
    - 实现配置变更时的数据保留逻辑 (已有段保留/新增段零初始化)
    - _Requirements: 4.3, 5.3, 5.4, 10.2, 10.3, 10.4_

  - [x]* 5.2 编写迁移工具属性测试
    - **Property 8: D2 legacy flat-to-nested migration preserves all values**
    - **Property 9: D3/F1 legacy key migration preserves values**
    - **Property 10: Config change preserves existing segment data**
    - **Property 11: Serialization produces exclusively nested format**
    - **Validates: Requirements 4.2, 4.3, 4.5, 5.3, 5.4, 10.2, 10.3, 10.4**

- [x] 6. Checkpoint - 前端核心 composable 验证
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. D2 明细表账龄动态化改造
  - [x] 7.1 改造 useD2Detail composable 支持动态账龄
    - 引入 useAgingConfig composable 获取 segments/bands
    - 将 DetailRow 数据结构从 flat 字段迁移到 nested keyed (agingPrior/agingCurrent/agingAudited)
    - 加载时调用 migrateD2FlatToNested 处理旧格式数据
    - 保存时序列化为 nested 格式 (不再输出 flat 字段)
    - 监听 aging-config:changed 事件，保留已有段数据/零初始化新增段
    - _Requirements: 4.1, 4.2, 4.3, 4.5, 10.2, 10.3, 10.4_

  - [x] 7.2 改造 D2 Tab Detail 视图动态渲染账龄列
    - 基于 bands 数组动态生成 el-table-column (每个 band 生成3列: 期初/期末未审/期末审定)
    - 移除硬编码的 5 年段 6×3=18 列定义
    - 确保列标题从 band.label 读取
    - _Requirements: 4.4_

- [x] 8. D3/F1 明细表账龄动态化改造
  - [x] 8.1 改造 useD3Detail 和 useF1Detail composable
    - 引入 useAgingConfig composable (subject='D3'/'F1')
    - 将 DetailRow 数据结构改为 nested keyed (agingPrior/agingAudited, 无 agingCurrent)
    - 加载时调用 migrateD3F1Keys 处理旧格式数据
    - 保存时序列化为 nested 格式
    - _Requirements: 5.1, 5.2, 5.3, 5.4_

  - [x] 8.2 改造 D3/F1 Tab Detail 视图动态渲染账龄列
    - 基于 bands 数组动态生成 el-table-column (每个 band 生成2列: 期初/期末审定)
    - 移除硬编码的 3 年段列定义
    - _Requirements: 5.5_

- [x] 9. K1/K3/G5 明细表账龄动态化改造
  - [x] 9.1 改造 useK1Detail/useK3Detail/useG5Detail composable
    - 引入 useAgingConfig composable (subject='K1'/'K3'/'G5')
    - 采用与 D2 相同的 nested keyed 结构 (agingPrior/agingCurrent/agingAudited)
    - 加载时检测旧格式并自动迁移
    - _Requirements: 6.1, 6.2, 6.3_

  - [x] 9.2 改造 K1/K3/G5 Tab Detail 视图动态渲染账龄列
    - 基于 bands 数组动态生成 el-table-column (3×N 列模式)
    - 移除各自硬编码的列定义
    - _Requirements: 6.4_

- [x] 10. Checkpoint - 明细表改造验证
  - Ensure all tests pass, ask the user if questions arise.

- [x] 11. 账龄配置 UI 管理界面
  - [x] 11.1 创建 AgingConfigDialog 组件
    - 创建 `frontend/src/components/workpaper/AgingConfigDialog.vue`
    - 实现三种预设选择 (el-radio-group: 3年段/5年段/自定义)
    - 预设模式下展示只读段标签
    - 自定义模式下展示可编辑段列表 (add/remove 按钮)
    - 实现实时校验 (非空/不重复) 禁用确认按钮
    - 实现 subject-level override 切换 (允许不同科目使用不同预设)
    - 确认时调用 PUT API + dispatch EventBus 事件
    - 已有数据变更时弹确认警告 (段被移除将丢失数据)
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6_

  - [x]* 11.2 编写 AgingConfigDialog 单元测试
    - 测试预设切换 UI 行为
    - 测试自定义段校验逻辑
    - 测试确认提交流程
    - _Requirements: 7.1, 7.2, 7.3, 7.4_

- [x] 12. 导入导出适配
  - [x] 12.1 改造导出服务支持动态账龄列头
    - 修改各明细表的导出模板生成逻辑
    - 基于 useAgingConfig.bands 动态生成列头 (3N for D2/K1/K3/G5, 2N for D3/F1)
    - 确保导出的列头与当前项目配置一致
    - _Requirements: 8.1_

  - [x] 12.2 改造导入服务支持 label 匹配
    - 导入时按列头 label 匹配当前配置的 segment
    - 不匹配的列报 warning 并跳过
    - 配置变更后导入旧模板时尝试按 label 映射
    - _Requirements: 8.2, 8.3, 8.4_

  - [x]* 12.3 编写导入导出属性测试
    - **Property 12: Export header generation from bands**
    - **Property 13: Import label matching maps correctly**
    - **Validates: Requirements 8.1, 8.2, 8.3, 8.4**

- [x] 13. D6 坏账准备 ECL 联动
  - [x] 13.1 改造 D6 ECL 计算 composable 联动账龄配置
    - 引入 useAgingConfig 获取当前段定义
    - ECL 分组创建时按 segments 初始化行 (替代硬编码6行)
    - 配置变更时：已有段保留 lossRate/bookBalance，新增段零初始化，移除段标记归档
    - _Requirements: 9.1, 9.2, 9.3_

  - [x]* 13.2 编写 ECL 联动属性测试
    - **Property 14: ECL group syncs with aging config**
    - **Validates: Requirements 9.1, 9.2, 9.3**

- [x] 14. 集成与串联
  - [x] 14.1 EventBus 配置变更通知链路串联
    - 后端 save_config 成功后 publish `aging-config:changed` 事件
    - 前端 useAgingConfig 监听 window event 触发 refresh
    - 各 Detail composable 响应式更新列定义
    - AgingConfigDialog 入口集成到项目设置页面
    - _Requirements: 3.3, 3.5, 4.5_

  - [x]* 14.2 编写集成测试
    - 测试完整 PUT→EventBus→前端刷新链路
    - 测试 D6 ECL 联动端到端
    - 测试导入导出 XLSX 往返
    - _Requirements: 3.3, 9.2, 8.1, 8.2_

- [x] 15. Final checkpoint - 全链路验证
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties (14 properties from design)
- Unit tests validate specific examples and edge cases
- 后端使用 Python (FastAPI + Pydantic)，前端使用 TypeScript (Vue 3 + Element Plus)
- 旧数据迁移在首次加载时自动完成，无需数据库迁移脚本
- EventBus 通知使用 window.dispatchEvent 模式与现有架构一致

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "1.3"] },
    { "id": 2, "tasks": ["1.4", "2.1"] },
    { "id": 3, "tasks": ["2.2", "4.1"] },
    { "id": 4, "tasks": ["4.2", "5.1"] },
    { "id": 5, "tasks": ["5.2", "7.1", "8.1", "9.1"] },
    { "id": 6, "tasks": ["7.2", "8.2", "9.2", "11.1"] },
    { "id": 7, "tasks": ["11.2", "12.1", "12.2", "13.1"] },
    { "id": 8, "tasks": ["12.3", "13.2", "14.1"] },
    { "id": 9, "tasks": ["14.2"] }
  ]
}
```
