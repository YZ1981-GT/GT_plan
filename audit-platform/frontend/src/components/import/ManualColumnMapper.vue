<template>
  <div class="manual-column-mapper">
    <div class="mapper-header">
      <h4>关键列对应确认</h4>
      <p class="mapper-desc">
        系统已自动识别部分列，未识别的列请手动指定对应关系。
        <el-tag size="small" type="success">{{ matchedCount }}/{{ totalColumns }} 已匹配</el-tag>
      </p>
    </div>

    <!-- 必需列状态提示 -->
    <div class="required-status" v-if="missingRequired.length">
      <el-alert type="error" :closable="false" show-icon>
        <template #title>
          缺少必需列：{{ missingRequired.join('、') }}
          <span class="hint">（请在下方手动指定）</span>
        </template>
      </el-alert>
    </div>

    <!-- 列映射表格 -->
    <el-table :data="mappingRows" size="small" max-height="450" stripe>
      <!-- 原始列名 -->
      <el-table-column label="原始列名" min-width="150">
        <template #default="{ row }">
          <span class="original-header">{{ row.header }}</span>
          <el-tag v-if="row.sampleValue" size="small" effect="plain" class="sample-tag">
            示例: {{ row.sampleValue }}
          </el-tag>
        </template>
      </el-table-column>

      <!-- 映射状态 -->
      <el-table-column label="状态" width="80" align="center">
        <template #default="{ row }">
          <el-icon v-if="row.status === 'matched'" color="#67c23a" :size="16"><CircleCheck /></el-icon>
          <el-icon v-else-if="row.status === 'suggested'" color="#e6a23c" :size="16"><Warning /></el-icon>
          <el-icon v-else color="#c0c4cc" :size="16"><QuestionFilled /></el-icon>
        </template>
      </el-table-column>

      <!-- 对应字段选择 -->
      <el-table-column label="对应字段" min-width="200">
        <template #default="{ row }">
          <el-select
            v-model="row.mappedField"
            placeholder="选择对应字段"
            size="small"
            filterable
            clearable
            @change="onFieldChange(row)"
          >
            <el-option-group
              v-for="group in fieldGroups"
              :key="group.label"
              :label="group.label"
            >
              <el-option
                v-for="field in group.fields"
                :key="field.value"
                :value="field.value"
                :label="field.label"
                :disabled="isFieldUsed(field.value, row.header)"
              >
                <span>{{ field.label }}</span>
                <span v-if="isFieldUsed(field.value, row.header)" class="used-hint">（已使用）</span>
              </el-option>
            </el-option-group>
          </el-select>
          <!-- 模糊匹配建议 -->
          <div v-if="row.suggestion && !row.mappedField" class="suggestion">
            <el-button size="small" text type="primary" @click="acceptSuggestion(row)">
              采纳建议: {{ row.suggestion.label }} ({{ Math.round(row.suggestion.confidence * 100) }}%)
            </el-button>
          </div>
        </template>
      </el-table-column>

      <!-- 重要性 -->
      <el-table-column label="重要性" width="80" align="center">
        <template #default="{ row }">
          <el-tag v-if="row.importance === 'required'" size="small" type="danger" effect="plain">必需</el-tag>
          <el-tag v-else-if="row.importance === 'important'" size="small" type="warning" effect="plain">重要</el-tag>
          <el-tag v-else size="small" effect="plain">可选</el-tag>
        </template>
      </el-table-column>
    </el-table>

    <!-- 操作栏 -->
    <div class="mapper-actions">
      <el-button @click="autoMatchAll" size="small">自动匹配全部</el-button>
      <el-button @click="clearAll" size="small">清除全部</el-button>
      <el-divider direction="vertical" />
      <el-button type="primary" size="small" :disabled="!canConfirm" @click="onConfirm">
        确认映射 ({{ matchedCount }}/{{ totalColumns }})
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { CircleCheck, Warning, QuestionFilled } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { enhanceColumnMapping } from '@/services/commonApi'

interface MappingRow {
  header: string
  mappedField: string
  status: 'matched' | 'suggested' | 'unmatched'
  importance: 'required' | 'important' | 'optional'
  sampleValue: string
  suggestion: { value: string; label: string; confidence: number } | null
}

const props = defineProps<{
  projectId: string
  headers: string[]
  sampleData?: any[][]  // 前几行数据用于显示示例
  autoMapping?: Record<string, string>  // 系统自动匹配的结果
  dataType?: string  // balance / ledger / aux_balance / aux_ledger
}>()

const emit = defineEmits<{
  'confirm': [mapping: Record<string, string>]
}>()

const mappingRows = ref<MappingRow[]>([])

// 字段分组（中文标签）
const fieldGroups = [
  {
    label: '科目信息',
    fields: [
      { value: 'account_code', label: '科目编码' },
      { value: 'account_name', label: '科目名称' },
      { value: 'direction', label: '借贷方向' },
      { value: 'level', label: '科目级次' },
      { value: 'category', label: '科目类别' },
      { value: 'parent_code', label: '上级科目编码' },
    ],
  },
  {
    label: '金额',
    fields: [
      { value: 'opening_balance', label: '期初余额' },
      { value: 'opening_debit', label: '期初借方' },
      { value: 'opening_credit', label: '期初贷方' },
      { value: 'debit_amount', label: '借方发生额' },
      { value: 'credit_amount', label: '贷方发生额' },
      { value: 'closing_balance', label: '期末余额' },
      { value: 'closing_debit', label: '期末借方' },
      { value: 'closing_credit', label: '期末贷方' },
    ],
  },
  {
    label: '凭证信息',
    fields: [
      { value: 'voucher_date', label: '凭证日期' },
      { value: 'voucher_no', label: '凭证号' },
      { value: 'voucher_type', label: '凭证类型' },
      { value: 'entry_seq', label: '分录序号' },
      { value: 'summary', label: '摘要' },
      { value: 'counter_account', label: '对方科目' },
      { value: 'accounting_period', label: '会计期间' },
    ],
  },
  {
    label: '辅助核算',
    fields: [
      { value: 'aux_dimensions', label: '核算维度（混合）' },
      { value: 'aux_type', label: '辅助类型' },
      { value: 'aux_code', label: '辅助编码' },
      { value: 'aux_name', label: '辅助名称' },
    ],
  },
]

// 必需字段（按数据类型）
const requiredFields: Record<string, string[]> = {
  balance: ['account_code'],
  ledger: ['account_code', 'voucher_date', 'voucher_no'],
  aux_balance: ['account_code', 'aux_type'],
  aux_ledger: ['account_code'],
  account_chart: ['account_code', 'account_name'],
}

const totalColumns = computed(() => props.headers.length)
const matchedCount = computed(() => mappingRows.value.filter(r => r.mappedField).length)
const missingRequired = computed(() => {
  const required = requiredFields[props.dataType || 'balance'] || ['account_code']
  const mapped = new Set(mappingRows.value.filter(r => r.mappedField).map(r => r.mappedField))
  return required.filter(f => !mapped.has(f)).map(f => {
    const allFields = fieldGroups.flatMap(g => g.fields)
    return allFields.find(ff => ff.value === f)?.label || f
  })
})
const canConfirm = computed(() => missingRequired.value.length === 0)

function isFieldUsed(fieldValue: string, currentHeader: string): boolean {
  return mappingRows.value.some(r => r.mappedField === fieldValue && r.header !== currentHeader)
}

function onFieldChange(row: MappingRow) {
  row.status = row.mappedField ? 'matched' : 'unmatched'
}

function acceptSuggestion(row: MappingRow) {
  if (row.suggestion) {
    row.mappedField = row.suggestion.value
    row.status = 'matched'
  }
}

async function autoMatchAll() {
  // 调用后端模糊匹配
  const existingMapping: Record<string, string> = {}
  for (const row of mappingRows.value) {
    if (row.mappedField) {
      existingMapping[row.header] = row.mappedField
    }
  }

  try {
    const result = await enhanceColumnMapping(props.projectId, props.headers, existingMapping)

    // 应用自动匹配结果
    for (const [header, field] of Object.entries(result.enhanced)) {
      const row = mappingRows.value.find(r => r.header === header)
      if (row && !row.mappedField) {
        row.mappedField = field
        row.status = 'matched'
      }
    }

    // 显示建议
    for (const sug of result.suggestions) {
      const row = mappingRows.value.find(r => r.header === sug.header)
      if (row && !row.mappedField) {
        const allFields = fieldGroups.flatMap(g => g.fields)
        const fieldInfo = allFields.find(f => f.value === sug.suggested_field)
        row.suggestion = {
          value: sug.suggested_field,
          label: fieldInfo?.label || sug.suggested_field,
          confidence: sug.confidence,
        }
        row.status = 'suggested'
      }
    }

    ElMessage.success(`自动匹配完成：${Object.keys(result.enhanced).length} 个确认，${result.suggestions.length} 个建议`)
  } catch {
    ElMessage.error('自动匹配失败')
  }
}

function clearAll() {
  for (const row of mappingRows.value) {
    row.mappedField = ''
    row.status = 'unmatched'
    row.suggestion = null
  }
}

function onConfirm() {
  const mapping: Record<string, string> = {}
  for (const row of mappingRows.value) {
    if (row.mappedField) {
      mapping[row.header] = row.mappedField
    }
  }
  emit('confirm', mapping)
}

// 初始化
onMounted(() => {
  const required = new Set(requiredFields[props.dataType || 'balance'] || ['account_code'])
  const allFields = fieldGroups.flatMap(g => g.fields)

  mappingRows.value = props.headers.map((h, idx) => {
    const autoField = props.autoMapping?.[h] || ''
    const sampleValue = props.sampleData?.[0]?.[idx] != null ? String(props.sampleData[0][idx]).slice(0, 20) : ''

    // 判断重要性
    let importance: 'required' | 'important' | 'optional' = 'optional'
    if (autoField && required.has(autoField)) importance = 'required'
    else if (required.has(autoField)) importance = 'important'
    // 未匹配但列名看起来像必需字段
    if (!autoField) {
      for (const rf of required) {
        const fieldInfo = allFields.find(f => f.value === rf)
        if (fieldInfo && (h.includes(fieldInfo.label.slice(0, 2)) || fieldInfo.label.includes(h.slice(0, 2)))) {
          importance = 'required'
          break
        }
      }
    }

    return {
      header: h,
      mappedField: autoField,
      status: autoField ? 'matched' : 'unmatched',
      importance,
      sampleValue,
      suggestion: null,
    } as MappingRow
  })
})
</script>

<style scoped>
.manual-column-mapper { padding: 12px 0; }
.mapper-header h4 { margin: 0 0 4px; font-size: 15px; }
.mapper-desc { font-size: 13px; color: #606266; margin: 0 0 12px; display: flex; align-items: center; gap: 8px; }
.required-status { margin-bottom: 12px; }
.required-status .hint { font-size: 12px; color: #909399; }
.original-header { font-weight: 500; }
.sample-tag { margin-left: 6px; font-size: 11px; max-width: 120px; overflow: hidden; text-overflow: ellipsis; }
.suggestion { margin-top: 4px; }
.used-hint { font-size: 11px; color: #c0c4cc; margin-left: 4px; }
.mapper-actions { margin-top: 12px; display: flex; align-items: center; gap: 8px; }
</style>
