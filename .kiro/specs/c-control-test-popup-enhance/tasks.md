# Implementation Plan: C2~C15 控制测试弹窗增强

## Overview

为 C2~C15 控制测试底稿的 L1 Dialog 和 Cx-2 偏差评价弹窗增加两项功能：编制提示琥珀块（Guidance JSON → render-config → 前端 `<details>` 渲染）和附件 OCR 上下文选择器（OcrAttachmentPicker.vue + useOcrAttachmentCache composable）。后端使用 Python (FastAPI)，前端使用 TypeScript (Vue 3 + Element Plus)。

## Tasks

- [ ] 1. 创建 C2~C15 Guidance JSON 文件（L1 Dialog 用）
  - [ ] 1.1 创建 C2~C8 的 Guidance JSON 文件
    - 在 `backend/data/wp_guidance/` 目录下创建 `C2.json` ~ `C8.json`（7 个文件）
    - 每个文件包含 wp_code/title/sections/source 字段
    - sections 内容从 BCD 类底稿 md 源模板提取红字方法论注解
    - source 字段固定为 "static_json"
    - _Requirements: 1.1, 1.2, 1.3, 1.4_

  - [ ] 1.2 创建 C9~C15 的 Guidance JSON 文件
    - 在 `backend/data/wp_guidance/` 目录下创建 `C9.json` ~ `C15.json`（7 个文件）
    - 格式与 C2~C8 一致：wp_code/title/sections/source
    - sections 内容从对应源模板提取
    - _Requirements: 1.1, 1.2, 1.3, 1.4_

- [ ] 2. 创建 C2~C15 Guidance JSON 文件（Cx-2 偏差评价用）
  - [ ] 2.1 创建 C2-2~C8-2 的 Guidance JSON 文件
    - 在 `backend/data/wp_guidance/` 目录下创建 `C2-2.json` ~ `C8-2.json`（7 个文件）
    - wp_code 为 "C{n}-2" 格式，title 含"偏差评价 — 编制提示"
    - sections 内容从偏差评价相关源模板提取红字注解
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 3.1_

  - [ ] 2.2 创建 C9-2~C15-2 的 Guidance JSON 文件
    - 在 `backend/data/wp_guidance/` 目录下创建 `C9-2.json` ~ `C15-2.json`（7 个文件）
    - 格式与 C2-2~C8-2 一致
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 3.1_

- [ ] 3. 后端 render 策略增强 `_load_guidance`
  - [ ] 3.1 在 `_c_control_test.py` 中实现 `_load_guidance` 函数
    - 实现从 `backend/data/wp_guidance/` 加载 JSON 文件的纯函数
    - 文件不存在时返回 None（不抛异常）
    - JSON 解析失败时 logger.warning 并返回 None
    - 校验 data 必须是 dict 且包含 "sections" key
    - _Requirements: 7.1, 7.2, 7.3_

  - [ ] 3.2 在 render() 函数中集成 guidance 加载
    - 在 render 返回的 html_data 中新增 `guidance` 字段（L1 用，加载 `C{n}.json`）
    - 新增 `guidance_cx2` 字段（Cx-2 用，加载 `C{n}-2.json`）
    - 缺失时返回 null，前端 v-if 隐藏
    - _Requirements: 7.1, 7.2, 7.3_

  - [ ]* 3.3 编写 `_load_guidance` 单元测试
    - 测试文件存在时正确解析返回
    - 测试文件不存在时返回 None
    - 测试 JSON 格式错误时返回 None
    - 测试缺少 sections 字段时返回 None
    - **Property 1: Guidance 加载 — 有效循环编号返回正确 guidance**
    - **Property 7: Guidance 缺失 — 安全降级**
    - **Validates: Requirements 7.1, 7.2, 7.3, 2.6, 3.4**

- [ ] 4. Checkpoint - 后端 Guidance 加载验证
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 5. 前端 L1 Dialog 琥珀块渲染
  - [ ] 5.1 在 GtCControlTest.vue 的 L1 Dialog 中添加琥珀块模板
    - 从 html_data.guidance 读取 guidance 数据
    - 使用 `<details class="amber-context">` 渲染可折叠块
    - summary 文本为"编制提示"
    - v-for 渲染 sections 数组的 heading（加粗）+ content（pre-wrap）
    - v-if="guidanceL1?.sections?.length" 条件渲染（无数据时隐藏）
    - readonly 模式下仍展示琥珀块
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_

  - [ ] 5.2 添加 `.amber-context` CSS 样式
    - 左边线: 4px solid #d97706 (amber-600)
    - 背景: #fffbeb (amber-50)
    - 字体: 12px, line-height 1.6
    - summary: font-weight 600, color #92400e
    - section heading: color #78350f, section content: color #451a03
    - _Requirements: 2.2_

- [ ] 6. 前端 Cx-2 偏差评价弹窗琥珀块渲染
  - [ ] 6.1 在偏差评价区域添加琥珀块模板
    - 从 html_data.guidance_cx2 读取 guidance 数据
    - 复用相同 `<details class="amber-context">` 模板和样式
    - 放置在偏差评价内容区域顶部
    - v-if="guidanceCx2?.sections?.length" 条件渲染
    - readonly 模式下仍展示
    - _Requirements: 3.1, 3.2, 3.3, 3.4_

- [ ] 7. 创建 useOcrAttachmentCache composable
  - [ ] 7.1 实现 composable 核心逻辑
    - 创建 `frontend/src/composables/useOcrAttachmentCache.ts`
    - 定义 `AttachmentItem` 接口 (id/file_name/file_type/file_size/created_at/ocrEligible)
    - 实现 `ocrCache: Ref<Map<string, string>>` OCR 结果缓存（组件生命周期）
    - 实现 `attachmentList: Ref<AttachmentItem[]>` 附件列表缓存（dialog session）
    - 实现 `loadAttachments(wpId)` 方法，已加载则跳过
    - 实现 `runOcr(wpId, attachmentId, file)` 方法，已缓存则直接返回
    - 实现 `resetListCache()` 方法（dialog 关闭时调用）
    - 实现 `isOcrEligible(fileName)` 纯函数（.pdf/.png/.jpg/.jpeg/.tiff/.bmp/.gif）
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 4.2, 4.3_

  - [ ]* 7.2 编写 useOcrAttachmentCache 属性测试
    - **Property 3: OCR 可识别性分类**
    - **Property 4: OCR 缓存避免重复调用**
    - **Validates: Requirements 4.2, 4.3, 6.1, 6.2, 6.3**

- [ ] 8. 创建 OcrAttachmentPicker.vue 组件
  - [ ] 8.1 实现 OcrAttachmentPicker 组件
    - 创建 `frontend/src/components/workpaper/cControlTest/OcrAttachmentPicker.vue`
    - Props: wpId/projectId/visible(v-model)/ocrCache
    - Emits: update:visible/confirm(payload)/cancel
    - visible 时调用 loadAttachments 获取附件列表
    - 渲染 checkbox 列表：文件名 + OCR 可识别标记
    - 不可识别格式的附件 checkbox 禁用 + tooltip "仅支持 PDF/图片"
    - 确认按钮：对未缓存附件逐个调用 OCR 端点 `/d4/contract-ocr`
    - OCR 结果拼接并截断到 3000 字符 + "…（已截断）"标记
    - 失败附件收集 ID 通过 confirm payload 返回
    - 无附件时显示"暂无附件"空状态
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.6, 5.1, 5.4_

  - [ ]* 8.2 编写 OCR 文本截断属性测试
    - **Property 5: OCR 文本拼接与截断**
    - **Property 6: OCR 部分失败容错**
    - **Validates: Requirements 4.4, 4.6, 5.3**

- [ ] 9. Checkpoint - 前端组件核心验证
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 10. L1 Dialog AI 按钮集成 OCR 附件选择
  - [ ] 10.1 改造 CControlTestSubPage.vue AI 生成流程
    - 在 AI 按钮点击时弹出 OcrAttachmentPicker
    - 用户确认后获取 ocrText
    - 将 ocrText 追加到 AI 生成端点的 context 参数中，key = "参考资料（OCR识别）"
    - 无选择时跳过，仅使用表单字段 context 生成
    - 失败附件通过 ElMessage.warning 提示用户
    - _Requirements: 4.1, 4.3, 4.4, 4.5, 4.6_

- [ ] 11. Cx-2 偏差评价 AI 按钮集成 OCR 附件选择
  - [ ] 11.1 改造偏差评价区域 AI 生成流程
    - 复用 OcrAttachmentPicker 组件和 useOcrAttachmentCache composable
    - 用户确认后将 ocrText 追加到 context["参考资料（OCR识别）"]
    - 无附件时禁用附件选择选项，直接执行 AI 生成
    - 失败附件通过 ElMessage.warning 提示
    - _Requirements: 5.1, 5.2, 5.3, 5.4_

- [ ] 12. Dialog 生命周期缓存管理
  - [ ] 12.1 集成缓存管理到 Dialog 开关逻辑
    - L1 Dialog 打开时初始化 useOcrAttachmentCache
    - L1 Dialog 关闭时调用 resetListCache() 清除附件列表缓存
    - ocrCache 在组件生命周期内保持（重复 AI 生成不重复 OCR）
    - 监听 EventBus `attachment:uploaded` 事件刷新附件列表
    - Cx-2 Dialog 复用相同缓存策略
    - _Requirements: 6.1, 6.2, 6.3, 6.4_

- [ ] 13. 集成联调与串联
  - [ ] 13.1 端到端功能串联验证
    - 验证 render-config 端点返回 guidance/guidance_cx2 字段
    - 验证 L1 Dialog 打开时正确显示琥珀块
    - 验证 Cx-2 Dialog 打开时正确显示偏差评价琥珀块
    - 验证 AI 按钮→OcrAttachmentPicker→OCR→AI 生成完整链路
    - 验证无 guidance JSON 时琥珀块安静隐藏
    - _Requirements: 2.1, 3.1, 4.1, 5.1, 7.1_

  - [ ]* 13.2 编写集成测试
    - 测试 render-config 返回 guidance 字段正确性
    - 测试 OCR context 正确传递到 AI 端点
    - **Property 2: Guidance section 完整渲染**
    - **Validates: Requirements 2.1, 2.3, 4.4, 5.3, 7.1, 7.2**

- [ ] 14. Final checkpoint - 全链路验证
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate 7 universal correctness properties from design document
- 14 个 L1 Guidance JSON (C2~C15) + 14 个 Cx-2 Guidance JSON (C2-2~C15-2) = 共 28 个文件
- 后端 `_load_guidance` 是纯函数，无需数据库迁移
- OcrAttachmentPicker 为独立子组件，L1 Dialog 和 Cx-2 Dialog 共用
- useOcrAttachmentCache 的 ocrCache 组件生命周期持久，attachmentList 随 dialog 关闭清除
- OCR 文本总长截断到 3000 字符，超出部分标记"…（已截断）"
- 琥珀块使用 `<details>` 原生 HTML 元素实现折叠，无需额外 JS

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "2.1", "2.2"] },
    { "id": 1, "tasks": ["3.1"] },
    { "id": 2, "tasks": ["3.2", "3.3"] },
    { "id": 3, "tasks": ["5.1", "5.2", "6.1", "7.1"] },
    { "id": 4, "tasks": ["7.2", "8.1"] },
    { "id": 5, "tasks": ["8.2", "10.1", "11.1", "12.1"] },
    { "id": 6, "tasks": ["13.1"] },
    { "id": 7, "tasks": ["13.2"] }
  ]
}
```
