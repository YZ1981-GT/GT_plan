# Sprint 1（P0）需求文档 — 快速修复与基础设施

## 目标

1 周内完成 6 项零风险高收益修复，为 Sprint 2 的角色功能深化打基础。

## 需求清单

### R8-S1-01：/confirmation 路由修复
- 侧栏"函证"指向 `/confirmation`，但 router 无此路径，点击 404
- 新建 `views/ConfirmationHub.vue`（stub 页面）
- router 添加 `/confirmation` route with `meta: { developing: true }`
- 守卫触发跳转到 DevelopingPage

### R8-S1-02：confirm.ts 补齐 + ElMessageBox.confirm 全局替换
- 当前 `utils/confirm.ts` 有 5 个函数（confirmDelete/confirmBatch/confirmDangerous/confirmLeave/confirmRestore）
- 新增 7 个语义化函数：confirmVersionConflict / confirmSignature / confirmForceReset / confirmRollback / confirmShare / confirmDuplicateAction / confirmForcePass
- 替换所有 `.vue` 文件中直接 `ElMessageBox.confirm` 调用（当前 30+ 处，分布在 **10 个合并工作表组件** + 7 个 view + 10+ 个 component）
- CI 卡点：grep `ElMessageBox\.confirm` 基线设为 5（允许极少数特殊场景）

### R8-S1-03：Adjustments "转错报"按钮（联动断点 1）
- 后端 `misstatement_service.create_from_rejected_aje` 已存在
- 后端 `UnconvertedRejectedAJERule` GateRule 已注册到 sign_off
- 前端 `Adjustments.vue` 对 `review_status === 'rejected'` 的行增加"转为错报"操作按钮
- 点击调 `POST /api/projects/{pid}/adjustments/{id}/convert-to-misstatement`
- 成功后弹 confirm 询问"是否立即查看未更正错报表"
- 加 `v-permission="'adjustment:convert_to_misstatement'"` 权限控制

### R8-S1-04：全局年度上下文 store
- 新建 `stores/projectYear.ts`（defineStore）
- 字段：currentProjectId / currentYear / setYear / setProject
- 所有视图从 store 读年度，URL query 只作为进入时初始值
- GtInfoBar `:show-year="true"` 绑定 store
- 切年度 → store 更新 → eventBus 发 `year:changed` → 订阅视图 reload
- router guard 统一注入 `?year=` query

### R8-S1-05：http interceptor 5xx/超时/断网统一提示
- `utils/http.ts` response interceptor 增加：
  - 5xx：ElNotification error "服务器错误，请稍后重试"（8 秒，可关闭）
  - ECONNABORTED：ElNotification warning "请求超时"
  - !navigator.onLine：ElNotification warning "网络已断开"
- 新建 `utils/feedback.ts` 封装 ElMessage/ElNotification 统一入口
- 所有新代码走 feedback，旧代码逐步迁移

### R8-S1-06：AI 输入 mask_context 全路径审计
- 核查 `note_ai.py` / `wp_ai.py` / `ai_unified.py` 是否调用 `export_mask_service.mask_context`
- 未调用的补齐
- 新增单元测试验证 mask_context 在 LLM 调用前执行
- 确保所有 AI 端点的 prompt 构建经过脱敏

## 验收标准

- [ ] `/confirmation` 点击跳 DevelopingPage 而非 404
- [ ] ElMessageBox.confirm 直接调用 ≤ 5 处
- [ ] Adjustments 被拒行有"转为错报"按钮
- [ ] 切年度后 TrialBalance/ReportView/DisclosureEditor 自动 reload
- [ ] 后端 5xx 时前端显示友好提示（不是白屏）
- [ ] AI 端点 prompt 不含未脱敏客户名/金额
