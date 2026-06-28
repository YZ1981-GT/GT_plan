# Tasks — A3-8 商誉减值测试专属组件

- [x] 1. 后端模板解析器 `a3_8_goodwill_parser.py`
  - 解析 A3-8 主表（资产组列 + 分摊表行）+ A3-8-1（公允价值/DCF/WACC 区块 + 编制说明文本）
  - 清洗 `#DIV/0!`→null，提取编制说明 9 项减值原因 + WACC 参数定义
  - _Requirements: 1, 2, 3, 4, 7, 8_

- [x] 2. 后端渲染策略 `_a3_8_goodwill.py` + 注册
  - `render(ctx)` 返回 `{impairmentData, recoverableData, responses}`，合并 field_overrides(scope=`a3_8_goodwill:{wp_id}`)
  - RENDERER_DISPATCH + VALID_COMPONENT_TYPES 注册 `a3-8-goodwill-impairment`
  - _Requirements: 6, 8_

- [x] 3. 前端 composable `useA38Goodwill.ts` — 公式引擎
  - total/diff/impairment、DCF 折现、终值、WACC(CAPM)、可收回金额孰高、减值损失两次分摊
  - responses 状态 + 2s debounce field-overrides 保存 + selfLoad(force_component_type)
  - _Requirements: 1, 2, 3, 4, 6_

- [x] 4. 前端组件 `GtA38GoodwillImpairment.vue`
  - 双模式 el-segmented + 4 Tab（减值主表/减值损失分摊/可收回金额/WACC）+ 编制说明折叠
  - 增删行、自动计算列只读展示、零值横杠、超限提示
  - GtIndexChip 核对区(I3-2/I3-6/I3-7) + jump-to-workpaper emit + 核对提示文案
  - OnlyOffice 健康检查降级
  - _Requirements: 1, 2, 3, 4, 5, 6, 7_

- [x] 5. 注册 htmlRendererRegistry + overrides 切换
  - registry 加 `a3-8-goodwill-impairment`；htmlRendererRegistry.spec.ts expected 列表同步
  - wp_code_overrides.json A3-8/A3-8-1 → `a3-8-goodwill-impairment`
  - _Requirements: 8_

- [x] 6. PBT (fast-check) — 公式引擎性质（12 tests 全绿）
  - 减值非负、diff 单调、分摊总和守恒(Σ=减值损失)、WACC 边界(D+E=0→null)、折现系数随 n 递减
  - _Requirements: 1, 2, 3, 4_

- [x] 7. 后端测试（5 tests 全绿）
  - parser round-trip 结构稳定、render 合并 overrides 不丢失、注册契约、overrides 映射
  - _Requirements: 6, 8_

- [x] 8. vitest 组件单测（14 tests 全绿）
  - composable 计算单测（合计/差额/减值/WACC/DCF/孰高/分摊）
  - _Requirements: 1, 2, 3, 4, 5, 6_

- [x] 9. Playwright E2E — 后端渲染链路验证
  - render-config?force_component_type 返回完整结构（impairmentData/recoverableData/responses）status 200
  - 注：测试项目 0ec33 未生成 A3-8 wp 实例，全 UI 流程待有 A3-8 实例的合并项目验证
  - _Requirements: 1, 3, 4, 5, 6_
