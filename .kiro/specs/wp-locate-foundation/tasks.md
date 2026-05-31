# 实施计划：底稿定位基础设施（wp-locate-foundation）

## 概述

后端统一坐标契约 → 前端 useCellLocate composable → 穿透扩展 → 降级处理。约 1.5 周。

## 任务

- [ ] 1. 后端：LocateTarget 坐标契约
  - [ ] 1.1 新建 `backend/app/schemas/locate_target.py`
    - LocateTarget dataclass（wp_code / wp_id / sheet_name / cell_ref / component_type / value / label）
    - Pydantic schema 用于 API 序列化
    - _Requirements: 1.1_
  - [ ] 1.2 wp_trace_service 输出映射为 LocateTarget
    - TraceItem → LocateTarget 转换函数
    - _Requirements: 1.2_
  - [ ] 1.3 report_trace_service 升级到 cell 级
    - 利用 cell_provenance 返回精确 LocateTarget（而非整个 parsed_data）
    - 无 cell_provenance 时降级到 sheet 级（cell_ref=None）
    - _Requirements: 1.3, 1.4_

- [ ] 2. 前端：useCellLocate composable
  - [ ] 2.1 新建 `audit-platform/frontend/src/composables/useCellLocate.ts`
    - `locateCell(target: LocateTarget): boolean` 主函数
    - 内部按 componentType 分派定位策略
    - 返回是否成功定位
    - _Requirements: 2.1, 5.1_
  - [ ] 2.2 实现 el-table 类定位策略
    - 适用：c-note-table / d-form-table / e-control-test
    - 逻辑：找到目标行 index → el-table scrollTo → 添加高亮 class → 3s 后移除
    - _Requirements: 2.2, 2.4_
  - [ ] 2.3 实现 GtIndexChip 类定位策略
    - 适用：a-program-console / b-index
    - 逻辑：querySelector 目标 chip → scrollIntoView → 闪烁动画 → 3s 淡出
    - _Requirements: 2.3, 2.4_
  - [ ] 2.4 实现通用 fallback 策略
    - 适用：h-static-doc / d-form-paragraph / d-form-qa / d-form-confirmation / d-form-review / 未知类型
    - 逻辑：scrollIntoView 最近匹配元素
    - _Requirements: 5.2_
  - [ ] 2.5 实现高亮幂等 + 淡出
    - 连续定位同一目标不叠加高亮
    - 3s CSS transition 淡出
    - _Requirements: 2.5_

- [ ] 3. GtWpRenderer 接入 locate 事件
  - [ ] 3.1 GtWpRenderer 监听 `workpaper:locate-cell` 事件
    - 接收 LocateTarget → 先切 sheet（如需要）→ 调 useCellLocate
    - _Requirements: 2.1_
  - [ ] 3.2 各子组件暴露定位接口（provide/inject 或 ref）
    - el-table 类组件暴露 `scrollToRow(index)` 方法
    - _Requirements: 2.2, 2.3_

- [ ] 4. 穿透带定位上下文
  - [ ] 4.1 扩展 usePenetrate.toWorkpaperEditor 签名
    - 加 `locate?: { sheet?: string; cell?: string }` 参数
    - 路由 push 时带 query `?sheet=xxx&cell=yyy`
    - _Requirements: 3.1_
  - [ ] 4.2 WorkpaperEditor onMounted 读 query 触发定位
    - 读 `route.query.sheet` / `route.query.cell` → 构建 LocateTarget → 调 locateCell
    - 无 query 时不触发（向后兼容）
    - _Requirements: 3.2, 3.3_

- [ ] 5. 定位失败降级
  - [ ] 5.1 实现降级逻辑
    - cell 失败 → 尝试 sheet 级 → 失败 → ElMessage.info 提示
    - _Requirements: 4.1, 4.2, 4.3_

- [ ] 6. 测试
  - [ ]* 6.1 useCellLocate 单元测试
    - 各 componentType 定位策略 + 高亮幂等 + 降级
    - _Requirements: 2.1-2.5, 4.1-4.3, 5.1-5.2_
  - [ ]* 6.2 Property 1-5 属性测试
    - LocateTarget 完整性 / HTML 覆盖率 / 幂等 / 降级不静默 / 穿透上下文传递
  - [ ]* 6.3 Playwright 集成验证
    - 从报表穿透到 D 类 HTML 底稿 → 断言目标行高亮可见
    - 从附注穿透到 B 目录底稿 → 断言 GtIndexChip 闪烁

- [ ] 7. Final Checkpoint
  - vitest 0 fail / vue-tsc 0 errors
  - useCellLocate 覆盖 9 类 HTML componentType + univer 委托
  - 穿透带 sheet/cell 参数端到端可用

- [ ] 8. 并发协作锁（HTML 编辑器 sheet 级锁，proposal 第二十二章补漏）
  - [ ] 8.1 HTML 渲染器接入 sheet 级软锁（复用 note_section_lock 模式）
    - _Requirements: 6.1, 6.4_
  - [ ] 8.2 presence 显示"X 正在编辑此 sheet"
    - _Requirements: 6.2_
  - [ ] 8.3 保存时乐观锁版本校验（parsed_data 带 version，冲突弹合并）
    - _Requirements: 6.3_

## 说明

- 这是路线图技术枢纽——wp-traceability-panel / wp-tsj-llm-review / wp-frontend-ux-polish 都依赖它
- 优先实现 C/D 类（el-table 定位，追溯需求最高），A/B/H 类可简化为 scrollIntoView
- Univer 定位已有（UniverEditorCore.onLocateCell），本 spec 只对齐接口不重写
- Playwright 集成验证依赖真实底稿数据（wp-generation-pipeline spec 先跑通）
