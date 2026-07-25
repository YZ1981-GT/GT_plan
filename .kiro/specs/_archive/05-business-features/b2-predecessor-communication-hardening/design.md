# B2 前任沟通模块加固 — 设计

## 架构总览

复用现有机制，零迁移。预填信息与结构化评价数据全部存 `checklist_responses`（项目级 `project_id` + `item_id`），前端经既有 bundle/word-template/dedicated 组件渲染。

## R1/R2 信函占位符自动填充

### 后端 `_prefill_word_template`（wp_editor_router.py）扩展
- 新增中文 `【】` 占位符替换分支（现仅支持 `{{token}}`）。
- 预填触发时，若 wp_code 属 B2 系列，额外查询项目级前任信息：
  ```sql
  SELECT remark FROM checklist_responses WHERE project_id=:pid AND item_id='B2-predecessor-info'
  ```
  remark 为 JSON：`{firmName, contactPerson, contactPhone, fax, address, zipCode}`。
- 中文替换映射（值为空则保留占位符）：
  | 占位符 | 来源 |
  |---|---|
  | `【被审计单位名称】` | projects.client_name / name |
  | `【20××】` | audit_period_end 年份 |
  | `【前任会计师事务所的名称】` `【前任会计师事务所名称】` | predecessor-info.firmName |
- 联系方式区（联系人/电话/传真/地址/邮编）：仅当 predecessor-info 提供了对应项目组联系方式时，替换信函尾部空白联系方式行。以"标签冒号后追加"方式实现（匹配段落文本 `联系人：` 等），避免误伤。
- 复用现有段落/表格 run 替换逻辑，`_replace_cn_placeholders` 与 `{{token}}` 同一遍历。

### 属性
- P1（幂等）：已有快照 → 返回 False 不重复预填。
- P2（空值保留）：predecessor-info 缺失 → 前任所占位符原样保留。
- P3（原模板不变）：替换在 storage 快照上执行。

## R2 前端录入

- `GtB2Bundle.vue` 新增首个 tab「基础信息」→ 新组件 `GtB2PredecessorInfo.vue`：
  - 表单字段：前任所名称、项目组联系人、电话、传真、地址、邮编。
  - 保存：PUT `/api/workpapers/{wpId}/checklist-responses`，item_id `B2-predecessor-info`，remark=JSON。
  - 顶部 el-alert 提示"先录入再打开信函"。
- wpId 用 B2 主程序表 wp_id（bundle 的 props.wpId），project_id 用于预填跨底稿读取。

## R3 Bundle 流程台账 + 适用性

- `GtB2Bundle.vue` 扩 TABS：基础信息 / 程序表 / 流程总览 / B2-5 + 动态子底稿链接。
- 流程总览 `GtB2FlowOverview.vue`：复用 `GtBArchitectureTree` 泳道范式（三场景泳道：委托前沟通/委托后查阅/前任评价），每卡片=底稿编码+名称+状态 tag+跳转。状态来自 checklist_responses 完成度 + docx 快照是否存在。
- 适用性：`B2-applicability` JSON 存三开关（firstEngagement/reviewPredecessorWp/ipoReaudit），缺省全 true；据此 filter 泳道卡片与子底稿 tab。参考 memory「适用性自动判断」。

## R4 B2-12 结构化专属组件

- 新 componentType `b2-12-evaluation`；wp_code_overrides `B2-12` 从 `word-template` 改为 `b2-12-evaluation`。
- 前端 `GtB212Evaluation.vue`：
  - 上：9 步了解程序 `el-table`（序号/程序[只读]/了解情况记录[textarea]/📎附件），第 8 步 5 子项 checkbox 组。
  - 下：7 点结论判断矩阵（结论项[只读]/是否存在[select 是·否·不适用]/应对措施[textarea]/对审计计划影响[textarea]），"是"行高亮。
  - 结论区 🤖AI（`POST /api/workpapers/{wp_id}/ai/generate-text` section=`b2-12-conclusion`）+ 💬 复核。
  - 持久化 item_id `B2-12-steps` / `B2-12-conclusions` / `B2-12-note`（JSON 存 remark）。
- 后端 render 策略 `_b2_12_evaluation.py`：输出 client_name/audit_year + responses_snapshot；注册 RENDERER_DISPATCH + dedicated_component_types（若属 whole-wp）。
- 保留 word 导出：dedicated 组件 + 既有 export（本 spec 不做 docx 导出，后续可加）。

## R5 B2-5 决策向导

- B2-5 仍在 bundle 内。将 `GtDForm` 渲染替换为专属 `GtB25Evaluation.vue`：
  - 答复评价 el-radio-group（充分/有限/未答复）互斥。
  - 未答复 → el-alert 联动提示催函。
  - 接受/不接受 el-radio + 理由 checkbox 组（源模板固定理由）+ 自由补充。
  - 持久化 item_id `B2-5-evaluation`（JSON）。

## R6 沟通问题→B50 联动（可选）

- B2-3/B2-11 答复结构化后，`pushToB50` 按钮 emit `eventBus.emit('b50:push-risk-factor', {...})`，B50-1 消费追加风险因素行。若 B50 侧无现成消费入口则记为待接线，不强做。

## 白名单

- `checklist_responses.py` 新增 `B2-` 前缀分支（pass，freeform）：predecessor-info / applicability / B2-12-* / B2-5-evaluation 均自由格式。

## 正确性属性
- P1 幂等预填 / P2 空值保留 / P3 原模板不变 / P4 中文占位符替换正确 / P5 B2-12 七点矩阵"存在"高亮 / P6 适用性过滤不误删程序表 / P7 B2-5 答复三选一互斥 / P8 checklist B2- 前缀 freeform 通过校验。

## 任务依赖波次
- Wave0：R1 后端预填（+P1/P2/P4 PBT）+ 白名单
- Wave1：R2 基础信息录入 + R3 Bundle 台账/适用性
- Wave2：R4 B2-12 结构化
- Wave3（可选）：R5 B2-5 向导 + R6 B50 联动
