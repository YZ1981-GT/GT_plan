<template>
  <div class="s21-basic-info">
    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" show-icon class="audit-objective">
      <template #title>审计目标</template>
      <div class="audit-objective-text">
        了解并记录被审计单位数据资产的基本信息（名称、类型、取得方式、原始成本、摊销方法、使用年限），关注数据资产确认条件（可辨认性、控制、未来经济利益流入）是否满足。
      </div>
    </el-alert>

    <el-card shadow="never" class="audit-section">
      <template #header>
        <div class="section-header">
          <span>数据资产的基本情况 S21-1</span>
        </div>
      </template>

      <el-table
        :data="assetRows"
        border
        style="width: 100%; font-size: 13px"
      >
        <el-table-column type="index" label="序号" width="60" align="center" />
        <el-table-column prop="name" label="数据资产名称" min-width="150">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              v-model="row.name"
              size="small"
              placeholder="资产名称"
            />
            <span v-else>{{ row.name || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="type" label="资产类型" width="120" align="center">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              v-model="row.type"
              size="small"
              placeholder="选择"
            >
              <el-option label="自建" value="自建" />
              <el-option label="外购" value="外购" />
              <el-option label="接受捐赠" value="接受捐赠" />
              <el-option label="合作开发" value="合作开发" />
            </el-select>
            <span v-else>{{ row.type || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="acquisitionDate" label="取得日期" width="130" align="center">
          <template #default="{ row }">
            <el-date-picker
              v-if="!isReadonly"
              v-model="row.acquisitionDate"
              type="date"
              size="small"
              value-format="YYYY-MM-DD"
              placeholder="选择日期"
              style="width: 100%"
            />
            <span v-else>{{ row.acquisitionDate || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="originalCost" label="原始成本(元)" width="140" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              v-model="row.originalCost"
              :controls="false"
              :precision="2"
              size="small"
              placeholder="0.00"
              style="width: 100%"
            />
            <span v-else>{{ fmtAmount(row.originalCost) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="amortizationMethod" label="摊销方法" width="120" align="center">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              v-model="row.amortizationMethod"
              size="small"
              placeholder="选择"
            >
              <el-option label="直线法" value="直线法" />
              <el-option label="产量法" value="产量法" />
              <el-option label="加速摊销" value="加速摊销" />
            </el-select>
            <span v-else>{{ row.amortizationMethod || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="usefulLife" label="预计使用年限" width="110" align="center">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              v-model="row.usefulLife"
              size="small"
              placeholder="年"
            />
            <span v-else>{{ row.usefulLife || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="residualRate" label="残值率(%)" width="100" align="center">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              v-model="row.residualRate"
              :controls="false"
              :precision="2"
              :min="0"
              :max="100"
              size="small"
              placeholder="0"
              style="width: 100%"
            />
            <span v-else>{{ row.residualRate != null ? row.residualRate + '%' : '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="description" label="简要描述" min-width="200">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              v-model="row.description"
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 3 }"
              size="small"
              placeholder="数据资产简要描述"
            />
            <span v-else>{{ row.description || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="操作" width="70" align="center">
          <template #default="{ $index }">
            <el-button type="danger" link size="small" @click="removeRow($index)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 动态行操作 -->
      <div v-if="!isReadonly" class="row-actions">
        <el-button size="small" type="primary" plain @click="addRow">
          + 新增数据资产
        </el-button>
      </div>
    </el-card>

    <!-- 审计说明 -->
    <el-card shadow="never" class="audit-conclusion-card">
      <template #header>
        <div class="section-header">
          <span>审计说明</span>
        </div>
      </template>
      <el-input
        v-model="auditNote"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="填写数据资产基本情况的审计说明"
      />
    </el-card>

    <!-- 编制提示 -->
    <details class="edit-hints">
      <summary>编制提示</summary>
      <p>列示被审计单位所有数据资产的基本信息，包括名称、类型、取得方式、原始成本、摊销方法和预计使用年限。</p>
      <p>重点关注数据资产的确认条件是否满足（可辨认性、控制、未来经济利益流入）。</p>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * GtS21BasicInfo.vue — 数据资产的基本情况 S21-1
 *
 * 功能：
 * - 列示数据资产基本信息（名称/类型/取得日期/原始成本/摊销方法/使用年限/残值率）
 * - 支持动态行增减
 * - 审计说明文本区
 *
 * Spec: .kiro/specs/s-estimate-calculation-workpapers/ Task 4.2
 */
import { ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import { fmtAmount } from '@/utils/formatters'

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

interface AssetRow {
  name: string
  type: string
  acquisitionDate: string
  originalCost: number
  amortizationMethod: string
  usefulLife: string
  residualRate: number | null
  description: string
}

const assetRows = ref<AssetRow[]>([
  { name: '', type: '', acquisitionDate: '', originalCost: 0, amortizationMethod: '直线法', usefulLife: '', residualRate: 0, description: '' },
])

const auditNote = ref('')

async function addRow() {
  try {
    const { value } = await ElMessageBox.prompt('请输入数据资产名称', '新增数据资产', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputPlaceholder: '数据资产名称',
    })
    if (value) {
      assetRows.value.push({
        name: value,
        type: '',
        acquisitionDate: '',
        originalCost: 0,
        amortizationMethod: '直线法',
        usefulLife: '',
        residualRate: 0,
        description: '',
      })
    }
  } catch {
    // 取消
  }
}

function removeRow(index: number) {
  assetRows.value.splice(index, 1)
}
</script>

<style scoped>
.s21-basic-info {
  padding: 12px;
}
.audit-objective {
  margin-bottom: 12px;
}
.audit-objective-text {
  font-size: 13px;
  line-height: 1.6;
}
.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.row-actions {
  margin-top: 12px;
}
.audit-conclusion-card {
  margin-top: 16px;
}
.edit-hints {
  margin-top: 16px;
  font-size: 12px;
  color: #909399;
}
.edit-hints summary {
  cursor: pointer;
  user-select: none;
}
</style>
