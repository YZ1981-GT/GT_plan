# Tasks — A1-11 业务报告签发流转控制表

## 1. 注册与配置

- [x] 1.1 在 `htmlRendererRegistry.ts` 的 `HtmlComponentType` union 中新增 `'a1-11-signing-form'`
- [x] 1.2 在 `REGISTRY_LIST` 中新增注册条目：componentType=`a1-11-signing-form`, icon='✍️', label='A1-11 签发流转控制表', emits=['save','completed'], contextProps='standard'
- [x] 1.3 添加 lazy import: `const GtA111SigningForm = defineAsyncComponent(() => import('./GtA111SigningForm.vue'))`
- [x] 1.4 更新 `wp_code_overrides.json`：将 `"A1-11": "wp-popup-signing"` 改为 `"A1-11": "a1-11-signing-form"`
- [x] 1.5 后端 `checklist_responses.py` 中 conclusion 校验增加 `A1-11-` 前缀分支（允许 Y/N/NA/A/B/C/null）

## 2. 组合式函数

- [x] 2.1 创建 `composables/useA111FormData.ts` — 数据加载/自动填充/debounce保存逻辑
  - 从 GET checklist-responses 加载已有数据
  - 从 GET /api/projects/:pid 获取 project context
  - 自动填充映射（仅无已有记录时填充）
  - debounce 2s 文本字段保存 / 签字立即保存
  - 组件卸载时 flush 未保存数据
- [x] 2.2 创建 `composables/useA111Signing.ts` — 签字流转状态管理
  - SIGN_SLOTS 配置常量
  - requiredSlots(businessCategory) 计算
  - progress 计算 (signed/total)
  - isAllSigned / isReadonly 计算
  - signAction(slotId, userName) 方法

## 3. Vue 组件实现

- [x] 3.1 创建 `GtA111SigningForm.vue` 骨架 — script setup + props/emits 定义
- [x] 3.2 实现基本信息区（6字段：委托人名称、约定书编号、企业性质、行业、业务分类、首次承接）
- [x] 3.3 实现报告信息区（3字段：报告标题、收件人全称、附送说明）
- [x] 3.4 实现签字流转区 — 6 槽位表格（姓名+签字按钮+日期），含进度条
- [x] 3.5 实现报告管理区（部门、文号、份数、打字校对/打印/印章管理员签字行）
- [x] 3.6 实现已签发报告修改区（Amendment_Section）— 修改原因 + 重新签字
- [x] 3.7 实现注释区（CAS 准则引用静态文本）
- [x] 3.8 实现只读模式 — 所有字段禁用 + 顶部"已完成签发"横幅
- [x] 3.9 实现响应式布局 — CSS Grid 表格结构 + <768px 单列折叠

## 4. 打印样式

- [x] 4.1 添加 `@media print` 样式 — 隐藏按钮/输入边框，保留文本+签字结果，A4 竖版布局

## 5. Property-Based Tests（fast-check）

- [x] 5.1 Property 1: Required signing slots determined by business category — 生成随机 category → 验证 requiredSlots 返回正确集合
- [x] 5.2 Property 2: Readonly mode equals all-required-signed OR external readonly — 生成随机 (category, signStates, externalReadonly) → 验证 isReadonly 计算
- [x] 5.3 Property 3: Signing progress computation — 生成随机 (category, signStates) → 验证 progress 分子/分母
- [x] 5.4 Property 4: Auto-fill only populates empty fields — 生成随机 (projectContext, existingResponses) → 验证合并结果
- [x] 5.5 Property 5: Signing action records correct data — 生成随机 (slotId, userName, today) → 验证 output 格式
- [x] 5.6 Property 6: Signed slot disables interaction — 生成随机 signState → 验证 UI 状态映射
- [x] 5.7 Property 7: Amendment reason validation — 生成随机空白字符串 → 验证拒绝；生成非空字符串 → 验证接受
- [x] 5.8 Property 8: Amendment history item_id sequencing — 生成随机 amendment 序列 → 验证 item_id 前缀递增

## 6. Unit Tests（vitest）

- [x] 6.1 注册契约测试 — 验证 registry 包含 `a1-11-signing-form`，wp_code_overrides 映射正确
- [x] 6.2 组件行为测试 — 签字操作 emit、debounce 保存、readonly 禁用
- [x] 6.3 amendment 流程测试 — 启动修改 → 填写原因 → 签字 → 重新锁定

## 7. 后端 PBT（hypothesis）

- [x] 7.1 Property 9: Data persistence round-trip — 生成随机 A1-11- items → PUT → GET → 验证一致性
- [x] 7.2 Conclusion 白名单校验 — 生成随机 (A1-11- item_id, conclusion) → 验证合法值通过、非法值 422
