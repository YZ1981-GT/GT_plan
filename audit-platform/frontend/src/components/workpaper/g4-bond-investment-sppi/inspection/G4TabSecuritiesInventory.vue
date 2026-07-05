<template>
  <div class="g4-tab-securities-inventory">
    <!-- Section标题 + 复核按钮 -->
    <div class="section-header">
      <h3 class="section-title">G4-7 有价证券盘点表</h3>
      <div class="section-actions">
        <el-button size="small" type="primary" plain @click="emitAi('inventory-conclusion')">
          <el-icon><MagicStick /></el-icon> AI
        </el-button>
        <el-button size="small" :icon="ChatDotRound" @click="handleReview('G4-7有价证券盘点表')">复核</el-button>
      </div>
    </div>

    <!-- 盘点信息头 -->
    <el-form :model="header" label-width="80px" size="small" class="inventory-header-form" :disabled="isReadonly">
      <el-row :gutter="16">
        <el-col :span="8">
          <el-form-item label="盘点单位">
            <el-input v-model="header.company" @change="inventoryLogic.updateHeader({ company: header.company })" />
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item label="盘点日期">
            <el-date-picker
              v-model="header.countDate"
              type="date"
              value-format="YYYY-MM-DD"
              style="width: 100%;"
              @change="inventoryLogic.updateHeader({ countDate: header.countDate })"
            />
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item label="会计主管">
            <el-input v-model="header.accountingSupervisor" @change="inventoryLogic.updateHeader({ accountingSupervisor: header.accountingSupervisor })" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-row :gutter="16">
        <el-col :span="8">
          <el-form-item label="出纳">
            <el-input v-model="header.cashier" @change="inventoryLogic.updateHeader({ cashier: header.cashier })" />
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item label="监盘人">
            <el-input v-model="header.observer" @change="inventoryLogic.updateHeader({ observer: header.observer })" />
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item label="盘点人">
            <el-input v-model="header.counter" @change="inventoryLogic.updateHeader({ counter: header.counter })" />
          </el-form-item>
        </el-col>
      </el-row>
    </el-form>

    <!-- 明细表格 -->
    <el-table
      :data="items"
      border
      stripe
      size="small"
      show-summary
      :summary-method="getSummary"
      class="inventory-detail-table"
    >
      <el-table-column label="序号" prop="seq" width="60" align="center" />
      <el-table-column label="证券名称" min-width="140">
        <template #default="{ row }">
          <el-input
            v-model="row.securitiesName"
            size="small"
            :disabled="isReadonly"
            @change="inventoryLogic.updateItem(row.id, { securitiesName: row.securitiesName })"
          />
        </template>
      </el-table-column>
      <el-table-column label="面值" min-width="110">
        <template #default="{ row }">
          <el-input-number
            v-model="row.faceValue"
            size="small"
            :controls="false"
            :disabled="isReadonly"
            @change="inventoryLogic.updateItem(row.id, { faceValue: row.faceValue })"
          />
        </template>
      </el-table-column>
      <el-table-column label="数量" min-width="90">
        <template #default="{ row }">
          <el-input-number
            v-model="row.quantity"
            size="small"
            :controls="false"
            :disabled="isReadonly"
            @change="inventoryLogic.updateItem(row.id, { quantity: row.quantity })"
          />
        </template>
      </el-table-column>
      <el-table-column label="总计" min-width="120">
        <template #default="{ row }">
          <el-tooltip content="总计 = 面值 × 数量" placement="top">
            <span class="formula-cell">{{ row.total.toFixed(2) }}</span>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column label="票面利率(%)" min-width="110">
        <template #default="{ row }">
          <el-input-number
            v-model="row.couponRate"
            size="small"
            :controls="false"
            :precision="4"
            :disabled="isReadonly"
            @change="inventoryLogic.updateItem(row.id, { couponRate: row.couponRate })"
          />
        </template>
      </el-table-column>
      <el-table-column label="到期日" min-width="130">
        <template #default="{ row }">
          <el-date-picker
            v-model="row.maturityDate"
            type="date"
            value-format="YYYY-MM-DD"
            size="small"
            style="width: 100%;"
            :disabled="isReadonly"
            @change="inventoryLogic.updateItem(row.id, { maturityDate: row.maturityDate })"
          />
        </template>
      </el-table-column>
      <el-table-column label="操作" width="60" align="center">
        <template #default="{ row }">
          <el-button
            type="danger"
            link
            size="small"
            :disabled="isReadonly || items.length <= 1"
            @click="inventoryLogic.removeItem(row.id)"
          >
            删除
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 新增行 + 导入导出 -->
    <div class="table-actions">
      <el-button size="small" type="primary" plain :disabled="isReadonly" @click="inventoryLogic.addItem()">
        + 新增盘点明细
      </el-button>
      <slot name="importExport" />
    </div>

    <!-- 审计说明 + 审计结论 -->
    <el-card shadow="never" class="conclusion-card">
      <template #header>
        <span>审计说明</span>
      </template>
      <el-input
        v-model="auditDescription"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 6 }"
        placeholder="请输入审计说明..."
        :disabled="isReadonly"
        @change="inventoryLogic.setAuditDescription(auditDescription)"
      />
    </el-card>

    <el-card shadow="never" class="conclusion-card">
      <template #header>
        <span>审计结论</span>
      </template>
      <el-input
        v-model="auditConclusion"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 6 }"
        placeholder="请输入审计结论..."
        :disabled="isReadonly"
        @change="inventoryLogic.setAuditConclusion(auditConclusion)"
      />
    </el-card>

    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>编制提示</summary>
      <div class="guidance-content">
        <p>1. 盘点信息头：填写盘点单位（被审计单位）、盘点日期、相关人员信息。</p>
        <p>2. 明细表：逐项记录实际盘点到的有价证券，总计=面值×数量（自动计算）。</p>
        <p>3. 合计行自动汇总面值、数量和总计。</p>
        <p>4. 盘点结果将用于G4-8盘点倒轧表，将盘点日实存调节至报表日。</p>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * G4TabSecuritiesInventory.vue — G4-7 有价证券盘点表
 *
 * Spec: .kiro/specs/g4-bond-investment-sppi/ Task 7.2
 * Requirements: 4.1~4.8, 9.1~9.5
 *
 * 完整实现：
 * - 盘点信息头 el-form（盘点单位/日期/会计主管/出纳/监盘人/盘点人）
 * - 明细 el-table（序号/证券名称/面值/数量/总计公式/票面利率/到期日）
 * - 合计行 + 审计说明/审计结论（el-card + textarea + AI按钮）
 * - 动态行增删 + 导入导出 slot + 复核对话
 */
import { inject, toRef } from 'vue'
import { ChatDotRound, MagicStick } from '@element-plus/icons-vue'
import { useG4SppiInventory } from '@/composables/useG4SppiInventory'

const props = defineProps<{
  htmlData: Record<string, any> | null
  wpId: string
  projectId: string
  isReadonly: boolean
  allResponses: any
  debouncedSave: (itemId: string, data: any) => void
}>()

const emit = defineEmits<{
  (e: 'aiGenerate', section: string): void
}>()

// ─── 复核对话 inject ────────────────────────────────────────────────────────
const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog')
function handleReview(sectionId: string): void {
  openReviewDialog?.(sectionId)
}
function emitAi(section: string): void {
  emit('aiGenerate', section)
}

// ─── composable ──────────────────────────────────────────────────────────────
const inventoryLogic = useG4SppiInventory({
  allResponses: toRef(props, 'allResponses'),
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly'),
})

const { header, items, summary, auditDescription, auditConclusion } = inventoryLogic

// ─── 合计行方法 ────────────────────────────────────────────────────────────
function getSummary({ columns }: { columns: any[]; data: any[] }) {
  const sums: string[] = []
  columns.forEach((col: any, idx: number) => {
    if (idx === 0) { sums[idx] = '合计'; return }
    if (col.property === 'seq' || idx === 0) { sums[idx] = ''; return }
    switch (idx) {
      case 2: // 面值
        sums[idx] = summary.value.faceValueTotal.toFixed(2)
        break
      case 3: // 数量
        sums[idx] = String(summary.value.quantityTotal)
        break
      case 4: // 总计
        sums[idx] = summary.value.totalTotal.toFixed(2)
        break
      default:
        sums[idx] = ''
    }
  })
  return sums
}
</script>

<style scoped>
.g4-tab-securities-inventory { font-size: 13px; }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-title { margin: 0; font-size: 15px; font-weight: 600; }
.section-actions { display: flex; gap: 6px; align-items: center; }

.inventory-header-form { margin-bottom: 16px; }

.inventory-detail-table { margin-bottom: 8px; }

.formula-cell {
  border-bottom: 1px dashed #909399;
  cursor: help;
  padding-bottom: 1px;
}

.table-actions {
  display: flex;
  gap: 8px;
  margin: 8px 0 16px;
}

.conclusion-card { margin: 12px 0; }
.conclusion-card :deep(.el-card__header) {
  padding: 8px 16px;
  font-size: 13px;
  font-weight: 500;
}

.guidance-details {
  margin-top: 16px;
  border: 1px solid #ebeef5;
  border-radius: 4px;
  padding: 8px 12px;
}
.guidance-details summary {
  cursor: pointer;
  font-weight: 500;
  color: #606266;
}
.guidance-content {
  margin-top: 8px;
  font-size: 12px;
  color: #909399;
  line-height: 1.8;
}
.guidance-content p { margin: 0; }
</style>
