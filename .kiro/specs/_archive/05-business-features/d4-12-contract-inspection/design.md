# D4-12 合同检查表升级 — 设计文档

## 架构概览

```
┌───────────────────────────────────────────────────────┐
│  D4TabContract.vue (重写)                              │
│  ┌─────────────────────────────────────────────────┐  │
│  │ 顶部工具条: el-segmented + 导入导出dropdown      │  │
│  │             + GtIndexChip(D4-5/D4-17/D4-4)      │  │
│  ├─────────────────────────────────────────────────┤  │
│  │ 概览横幅: 覆盖率进度 + 合同数量 + 添加按钮       │  │
│  ├─────────────────────────────────────────────────┤  │
│  │ 合同卡片区: el-tabs(card) 横向切换               │  │
│  │  ┌────────────────────────────────────────────┐ │  │
│  │  │ 每份合同卡片:                              │ │  │
│  │  │  上传区(el-upload拖拽) + OCR状态           │ │  │
│  │  │  20字段表单(分组: 基础/条款/收入确认/结论)  │ │  │
│  │  │  结论下拉                                  │ │  │
│  │  └────────────────────────────────────────────┘ │  │
│  ├─────────────────────────────────────────────────┤  │
│  │ 编制提示折叠区(4段details)                       │  │
│  ├─────────────────────────────────────────────────┤  │
│  │ 审计意见区(el-card): 说明 + 结论 + AI辅助        │  │
│  └─────────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────┘
```

## 组件拆分

### 前端文件
1. `d4/inspection/D4TabContract.vue` — 主组件(重写)
2. `composables/useD4ContractInspection.ts` — 新composable(D4-12专属逻辑)
3. `d4/inspection/D4ContractCard.vue` — 单份合同卡片子组件

### 后端文件
4. `backend/app/routers/_d4_contract_ocr.py` — OCR提取+LLM结构化端点

## 数据结构

### ContractInspectionItem (单份合同)
```typescript
interface ContractInspectionItem {
  id: string                    // uuid
  indexNo: string               // "D4-12-1" ~ "D4-12-N"
  // 基础信息
  contractNo: string            // 合同编号
  counterparty: string          // 交易对方名称
  signDate: string              // 合同签订日期
  serviceContent: string        // 服务内容/提供产品名称
  contractAmount: number        // 合同金额
  // 交付条款
  deliveryTime: string          // 交货时间/服务期间
  deliveryMethod: string        // 交货方式/提供服务方式
  settlementMethod: string      // 结算方式
  settlementTime: string        // 结算时间
  // 合同条款
  warrantyClause: string        // 质量保证条款
  returnClause: string          // 销售退回条款
  breachClause: string          // 违约条款
  specialTerms: string          // 特殊约定
  // 签署确认
  isSigned: string              // 订立双方是否签字 (Y/N/NA)
  isSealed: string              // 订立双方是否盖章 (Y/N/NA)
  // 收入确认
  recognitionMethod: string     // 时段法/时点法
  acceptanceClause: string      // 验收条款
  recognitionTime: string       // 收入确认时间
  controlTransferDoc: string    // 表明控制权转移的单据名称
  specialTransaction: string    // 是否涉及特定交易及说明
  // 结论
  conclusion: string            // 结论
  // 附件
  attachmentId?: string         // 关联附件ID
  attachmentName?: string       // 附件文件名
  ocrStatus?: 'none' | 'processing' | 'done' | 'failed'
}
```

### 持久化方案
- 主键: `D4-12-contracts-v2` → JSON数组(所有合同)
- 审计说明: `D4-12-note` → remark
- 审计结论: `D4-12-conclusion` → remark
- 总收入(覆盖率分母): 读 `D4-adj-revenue-total` 或 allResponses中D4-1审定表数据

## 后端OCR端点设计

```
POST /api/workpapers/{wp_id}/d4/contract-ocr
Content-Type: multipart/form-data
Body: file (PDF/图片)

Response:
{
  "attachment_id": "uuid",
  "ocr_text": "...",
  "extracted_fields": {
    "contractNo": "HT-2025-001",
    "counterparty": "XX有限公司",
    "signDate": "2025-03-15",
    "contractAmount": 1500000,
    ...其他字段
  },
  "confidence": 0.85
}
```

### 处理链路
1. 接收文件 → 存储到附件系统(process_record_service)
2. 调用UnifiedOCRService识别文本
3. 将OCR文本 + 20字段schema发送给vLLM结构化提取
4. 返回提取结果 + confidence

### LLM Prompt设计
```
你是审计合同信息提取专家。请从以下OCR文本中提取销售合同的关键信息。
严格按JSON格式返回以下字段（不确定的填空字符串）：
{schema}

OCR文本：
{ocr_text}
```

## UI交互流程

### 添加合同
1. 点击"+ 添加合同" → ElMessageBox.prompt输入合同备注名（如"XX公司采购合同"）
2. 创建新卡片，切换到该卡片
3. 用户可选择：手动填写 或 上传合同附件触发OCR

### OCR填充流程
1. 在合同卡片内上传PDF/图片
2. 显示processing状态（上传+识别中）
3. 后端返回结果后弹窗预览（左侧附件预览/右侧提取字段表格）
4. 用户确认 → 自动填充20字段（已有内容的字段提示是否覆盖）
5. 用户可手动修正

### 结论判定
- 每份合同结论: Y(合规) / N(存在问题) / NA(不适用)
- 汇总结论自动生成: "共检查N份合同，金额XX万元，覆盖率XX%，N份合规，N份存在问题"

## 样式规范
- 合同卡片: 圆角12px + 微紫渐变header(GT配色)
- 字段分组用分隔线(基础信息/交付条款/合同条款/签署确认/收入确认)
- Y/N/NA字段用el-radio-group
- 文本字段用el-input(短)/el-input textarea(长)
- 金额字段用el-input-number
- 覆盖率<60%显示警告色
