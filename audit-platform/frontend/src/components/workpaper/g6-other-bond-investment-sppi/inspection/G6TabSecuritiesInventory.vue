<template>
  <div class="g6-tab-securities-inventory">
    <!-- ═══ Section 标题 + 复核按钮 ═══ -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="section-header">
          <span class="section-title">有价证券盘点表（G6-9）</span>
          <div class="section-actions">
            <el-tag v-if="inventory.varianceCount.value > 0" type="danger" size="small">
              {{ inventory.varianceCount.value }}项差异
            </el-tag>
            <el-button size="small" @click="openReview('G6-9-securities-inventory')">💬复核</el-button>
          </div>
        </div>
      </template>

      <!-- ═══ 29行×7列 盘点表格 ═══ -->
      <el-table
        :data="inventory.items.value"
        border
        size="small"
        class="inventory-table"
        highlight-current-row
        row-key="id"
      >
        <!-- 序号 -->
        <el-table-column label="序号" width="50" align="center">
          <template #default="{ row }">
            {{ row.seq }}
          </template>
        </el-table-column>

        <!-- 证券名称 -->
        <el-table-column label="证券名称" min-width="200">
          <template #default="{ row }">
            <div class="name-cell">
              <el-input
                v-if="!props.isReadonly"
                :model-value="row.securitiesName"
                size="small"
                placeholder="证券名称..."
                @update:model-value="(v: string) => inventory.updateItem(row.id, 'securitiesName', v)"
              />
              <span v-else>{{ row.securitiesName || '-' }}</span>
              <el-button
                v-if="!props.isReadonly"
                size="small"
                type="danger"
                link
                class="delete-btn"
                @click="inventory.removeItem(row.id)"
              >🗑️</el-button>
            </div>
          </template>
        </el-table-column>

        <!-- 证券代码 -->
        <el-table-column label="证券代码" width="120">
          <template #default="{ row }">
            <el-input
              v-if="!props.isReadonly"
              :model-value="row.securitiesCode"
              size="small"
              placeholder="代码..."
              @update:model-value="(v: string) => inventory.updateItem(row.id, 'securitiesCode', v)"
            />
            <span v-else>{{ row.securitiesCode || '-' }}</span>
          </template>
        </el-table-column>

        <!-- 面值 -->
        <el-table-column label="面值" width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!props.isReadonly"
              :model-value="row.faceValue"
              size="small"
              :controls="false"
              :precision="2"
              style="width: 90px"
              @update:model-value="(v: number | undefined) => inventory.updateItem(row.id, 'faceValue', v ?? 0)"
            />
            <span v-else>{{ fmtNum(row.faceValue) }}</span>
          </template>
        </el-table-column>

        <!-- 数量(盘点) -->
        <el-table-column label="数量(盘点)" width="120" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!props.isReadonly"
              :model-value="row.countQuantity"
              size="small"
              :controls="false"
              :precision="0"
              style="width: 100px"
              @update:model-value="(v: number | undefined) => inventory.updateItem(row.id, 'countQuantity', v ?? 0)"
            />
            <span v-else>{{ row.countQuantity }}</span>
          </template>
        </el-table-column>

        <!-- 数量(账面) -->
        <el-table-column label="数量(账面)" width="120" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!props.isReadonly"
              :model-value="row.bookQuantity"
              size="small"
              :controls="false"
              :precision="0"
              style="width: 100px"
              @update:model-value="(v: number | undefined) => inventory.updateItem(row.id, 'bookQuantity', v ?? 0)"
            />
            <span v-else>{{ row.bookQuantity }}</span>
          </template>
        </el-table-column>

        <!-- 差异（公式列: 盘点-账面，红色高亮） -->
        <el-table-column label="差异" width="100" align="right">
          <template #default="{ row }">
            <el-tooltip content="盘点数量 - 账面数量" placement="top">
              <span
                class="formula-cell"
                :style="inventory.getVarianceCellStyle(row)"
              >{{ row.variance }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
      </el-table>

      <!-- 新增行按钮 -->
      <div class="bottom-actions">
        <el-button
          v-if="!props.isReadonly"
          type="primary"
          size="small"
          @click="inventory.addItem()"
        >
          + 新增行
        </el-button>
        <span class="row-count">共 {{ inventory.totalCount.value }} 行</span>
      </div>
    </el-card>

    <!-- ═══ 审计结论 ═══ -->
    <el-card shadow="never" class="conclusion-card">
      <template #header>
        <div class="section-header">
          <span class="section-title">审计结论</span>
        </div>
      </template>
      <el-input
        v-model="inventory.auditConclusion.value"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 10 }"
        :disabled="props.isReadonly"
        placeholder="对有价证券盘点结果的审计结论..."
        @input="handleSave"
      />
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="guide-details">
      <summary>📋 编制提示</summary>
      <div class="guide-content">
        <p>1. 盘点日应与被审计单位确认，通常为资产负债表日或临近日期</p>
        <p>2. 逐项核对证券名称、代码与登记结算机构持仓数据是否一致</p>
        <p>3. 差异（盘点数量 - 账面数量）不为零时需追查原因，关注是否存在未入账或重复入账</p>
        <p>4. 如盘点日非资产负债表日，需编制倒轧表（G6-10）将盘点结果推算至基准日</p>
        <p>5. 获取第三方托管机构的对账单作为盘点依据，核实与公司记录的一致性</p>
        <p>6. 关注限售/质押/冻结证券的标注是否完整</p>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * G6TabSecuritiesInventory.vue — G6-9 有价证券盘点表（29行×7列）
 *
 * Spec: .kiro/specs/g6-other-bond-investment-sppi/ Task 10.2
 * Requirements: 6.1, 6.4
 *
 * 功能：
 * - 29行×7列表格: 序号/证券名称/证券代码/面值/数量(盘点)/数量(账面)/差异(公式)
 * - 动态行增删(ElMessageBox.prompt) + 审计结论 + 编制提示 + 复核按钮
 * - 差异列: 公式计算(盘点-账面)，虚线下划线+cursor:help+tooltip+红色高亮(≠0)
 */
import { computed, inject, onMounted, watch } from 'vue'
import { useG6SppiInventory } from '../../composables/useG6SppiInventory'
import { useG6SppiFormData } from '../../composables/useG6SppiFormData'
import type { SecuritiesInventoryData } from '../../composables/useG6SppiInventory'

const props = defineProps<{
  htmlData: Record<string, any> | null
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'save'): void
}>()

// ─── 复核对话 inject ───
const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})

function openReview(sectionId: string): void {
  openReviewDialog(sectionId)
}

// ─── 数据层 ───
const formData = useG6SppiFormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})
const inventory = useG6SppiInventory()

// ─── 数据加载 ───
onMounted(async () => {
  await formData.loadAll()
  initFromData()
})

watch(() => props.htmlData, (newData) => {
  if (newData) initFromData()
})

function initFromData(): void {
  const content = formData.parseContent()
  if (content.inventory) {
    inventory.loadData(content.inventory as SecuritiesInventoryData)
  }
}

// ─── 保存逻辑 ───
function handleSave(): void {
  formData.debouncedSave('G6-9-securities-inventory-data', {
    conclusion: JSON.stringify(inventory.toJSON()),
  })
  emit('save')
}

// watch items 深度变化自动保存
watch(() => inventory.items.value, () => {
  handleSave()
}, { deep: true })

// watch auditConclusion 变化保存（input事件已处理，此处为编程式修改）
watch(() => inventory.auditConclusion.value, () => {
  handleSave()
})

// ─── 数字格式化 ───
function fmtNum(v: number | undefined, decimals = 2): string {
  if (v === undefined || v === null) return '-'
  return Number(v).toLocaleString('zh-CN', { minimumFractionDigits: decimals, maximumFractionDigits: decimals })
}

// ─── 暴露接口 ───
defineExpose({
  toJSON: () => inventory.toJSON(),
})
</script>

<style scoped>
.g6-tab-securities-inventory {
  padding: 12px;
  font-size: 13px;
}

/* ─── Section卡片 ─── */
.section-card {
  margin-bottom: 16px;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.section-title {
  font-weight: 600;
  font-size: 14px;
}

.section-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

/* ─── 表格 ─── */
.inventory-table {
  font-size: 13px;
}

/* ─── 名称单元格 ─── */
.name-cell {
  display: flex;
  align-items: center;
  gap: 4px;
}

.name-cell .el-input {
  flex: 1;
}

.delete-btn {
  flex-shrink: 0;
}

/* ─── 公式列样式（虚线下划线+cursor:help） ─── */
.formula-cell {
  border-bottom: 1px dashed #909399;
  cursor: help;
  padding: 2px 4px;
  display: inline-block;
}

/* ─── 底部操作 ─── */
.bottom-actions {
  display: flex;
  gap: 12px;
  align-items: center;
  margin: 12px 0;
}

.row-count {
  color: #909399;
  font-size: 12px;
}

/* ─── 审计结论 ─── */
.conclusion-card {
  margin-bottom: 16px;
}

/* ─── 编制提示 ─── */
.guide-details {
  margin-top: 16px;
}

.guide-details summary {
  cursor: pointer;
  font-size: 13px;
  color: #606266;
  font-weight: 600;
}

.guide-content {
  padding: 8px 12px;
  background: #fffbeb;
  border-left: 3px solid #f59e0b;
  margin-top: 6px;
  font-size: 12px;
  line-height: 1.8;
}

.guide-content p {
  margin: 0;
}
</style>
