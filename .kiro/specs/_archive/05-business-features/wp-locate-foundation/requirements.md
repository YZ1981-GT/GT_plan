# 需求文档：底稿定位基础设施

## 引言

底稿模块的互动追溯（从报表/附注穿透到底稿并高亮定位）当前只有 Univer 格式支持 cell 定位，HTML 渲染器（占 57% 底稿）完全无定位能力。本 spec 建立统一定位基础设施，是溯源面板、TSJ 复核跳证据、穿透体验的共同地基。

## 需求

### 需求 1：统一 LocateTarget 坐标契约

**用户故事**：作为底稿模块维护者，我希望所有溯源/穿透的定位目标有统一的数据格式，以便前端用一套逻辑处理所有格式的底稿定位。

**验收标准**：
1. THE system SHALL 定义 `LocateTarget` 数据结构，包含 wp_code / wp_id / sheet_name / cell_ref / component_type / value / label
2. WHEN wp_trace_service 返回溯源结果，THEN SHALL 输出 LocateTarget 格式
3. WHEN report_trace_service 返回溯源结果，THEN SHALL 输出 LocateTarget 格式（含 cell 级精度，利用 cell_provenance）
4. WHEN LocateTarget 的 cell_ref 无法确定，THEN SHALL 至少包含 sheet_name（sheet 级定位）

### 需求 2：HTML 渲染器定位能力

**用户故事**：作为审计助理，我希望从报表/附注穿透到 HTML 类底稿时能自动定位高亮到目标位置，而非只打开底稿让我自己找。

**验收标准**：
1. WHEN 用户穿透到 HTML 类底稿并带 sheet+cell 参数，THEN HTML 渲染器 SHALL 切到目标 sheet 并滚动高亮到目标位置
2. WHEN 定位到 el-table 类组件（c-note-table / d-form-table），THEN SHALL 滚动到目标行并高亮该行
3. WHEN 定位到 GtIndexChip 类组件（a-program-console / b-index），THEN SHALL scrollIntoView 并闪烁动画
4. WHEN 高亮触发后 3 秒，THEN 高亮 SHALL 自动淡出
5. WHEN 同一目标连续定位两次，THEN 高亮不叠加（幂等）

### 需求 3：穿透带定位上下文

**用户故事**：作为审计助理，我希望从报表/附注穿透到底稿时，系统能直接跳到支撑该数字的具体位置，而非只打开底稿。

**验收标准**：
1. WHEN usePenetrate.toWorkpaperEditor 被调用，THEN SHALL 支持传入 `{sheet, cell}` 定位参数
2. WHEN 路由跳转到 WorkpaperEditor 带 query `?sheet=xxx&cell=yyy`，THEN 编辑器 onMounted SHALL 触发 locateCell
3. WHEN 定位参数缺失（只有 wpId），THEN SHALL 正常打开底稿不报错（向后兼容）

### 需求 4：定位失败优雅降级

**验收标准**：
1. IF cell 级定位失败（目标 cell 不存在/被折叠），THEN SHALL 降级到 sheet 级定位（切到对的 sheet）
2. IF sheet 级也失败，THEN SHALL 显示提示"已打开底稿但未能定位到目标位置（可能已变更）"
3. THE system SHALL 不静默失败——任何定位失败都有可见反馈

### 需求 5：9 类 HTML componentType 全覆盖

**验收标准**：
1. WHEN useCellLocate 处理任意 HTML componentType（a-program-console / b-index / c-note-table / d-form-table / d-form-paragraph / d-form-qa / d-form-confirmation / d-form-review / e-control-test / h-static-doc），THEN SHALL 有对应的定位策略（不返回"不支持"）
2. WHEN 新增 HTML componentType，THEN useCellLocate SHALL 有 fallback 策略（scrollIntoView 通用兜底）

### 需求 6：HTML 编辑器并发协作锁

**用户故事**：作为审计助理，我希望两人同时编辑同一张 HTML 底稿时有 sheet 级锁保护，以便不会互相覆盖对方的编辑。

**验收标准**：
1. WHEN 用户开始编辑某 sheet，THEN SHALL 获取该 sheet 的软锁（复用 note_section_lock 模式）
2. WHEN 另一用户尝试编辑同一 sheet，THEN SHALL 显示"X 正在编辑此 sheet"提示
3. WHEN 用户保存时版本冲突（parsed_data version 不一致），THEN SHALL 弹出合并/覆盖选择
4. WHEN 用户离开 sheet（切 tab/关闭），THEN SHALL 释放锁

## 范围边界

- 不做统一溯源面板 UI（wp-traceability-panel spec）
- 不做附件入网
- 不改 Univer 定位能力（已有）
- 不追求像素级精确（HTML 类到"行+高亮"足够）
- 优先 C/D 类（追溯需求高），A/B/H 类定位需求低可简化
