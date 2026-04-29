<template>
  <div class="gt-formula-bar" v-if="visible">
    <!-- 地址显示 -->
    <div class="addr-box">
      <span class="addr-label">{{ currentAddr || '--' }}</span>
      <el-tag v-if="isMerged" size="small" type="warning" effect="plain">
        合并 {{ mergeRange }}
      </el-tag>
    </div>

    <!-- 公式/值编辑 -->
    <div class="formula-box">
      <span class="fx-icon">fx</span>
      <input
        ref="formulaInput"
        class="formula-input"
        :value="displayFormula"
        :placeholder="hasFormula ? '公式' : '值'"
        @focus="editing = true"
        @blur="onBlur"
        @keydown.enter="onConfirm"
        @keydown.escape="onCancel"
      />
      <div class="formula-actions" v-if="editing">
        <el-button size="small" type="primary" text @click="onConfirm">✓</el-button>
        <el-button size="small" text @click="onCancel">✗</el-button>
        <el-button size="small" text @click="openSelector">📋 选择</el-button>
      </div>
    </div>

    <!-- 公式类型标签 -->
    <div class="formula-meta" v-if="formulaType">
      <el-tag size="small" :type="formulaTypeColor" effect="plain">{{ formulaTypeLabel }}</el-tag>
      <span class="formula-desc" v-if="formulaDesc">{{ formulaDesc }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'

interface CellInfo {
  cell: string
  address: string
  value: any
  formula: string | null
  formula_type: string | null
  formula_desc: string | null
  fetch_rule_id: string | null
  merge: { range: string; rowspan: number; colspan: number } | null
  is_merged: boolean
}

const props = defineProps<{
  visible?: boolean
  cellInfo: CellInfo | null
}>()

const emit = defineEmits<{
  'update-formula': [cell: string, formula: string]
  'update-value': [cell: string, value: string]
  'open-selector': []
}>()

const editing = ref(false)
const formulaInput = ref<HTMLInputElement>()

const currentAddr = computed(() => props.cellInfo?.address || '')
const isMerged = computed(() => props.cellInfo?.is_merged || false)
const mergeRange = computed(() => props.cellInfo?.merge?.range || '')
const hasFormula = computed(() => !!props.cellInfo?.formula)
const formulaType = computed(() => props.cellInfo?.formula_type || '')
const formulaDesc = computed(() => props.cellInfo?.formula_desc || '')

const displayFormula = computed(() => {
  if (props.cellInfo?.formula) return props.cellInfo.formula
  const val = props.cellInfo?.value
  if (val === null || val === undefined) return ''
  return String(val)
})

const formulaTypeLabel = computed(() => {
  const map: Record<string, string> = {
    vertical_sum: '纵向合计',
    horizontal_balance: '横向平衡',
    book_value: '账面价值',
    cross_table: '跨表引用',
  }
  return map[formulaType.value] || formulaType.value
})

const formulaTypeColor = computed(() => {
  if (formulaType.value === 'cross_table') return 'warning'
  if (formulaType.value === 'vertical_sum') return ''
  return 'info'
})

function onConfirm() {
  const input = formulaInput.value
  if (!input || !props.cellInfo) return

  const val = input.value.trim()
  if (val.startsWith('=')) {
    emit('update-formula', props.cellInfo.cell, val)
  } else {
    emit('update-value', props.cellInfo.cell, val)
  }
  editing.value = false
}

function onCancel() {
  editing.value = false
  // 恢复原值
  if (formulaInput.value) {
    formulaInput.value.value = displayFormula.value
  }
}

function onBlur() {
  // 延迟关闭，允许点击按钮
  setTimeout(() => { editing.value = false }, 200)
}

function openSelector() {
  emit('open-selector')
}
</script>

<style scoped>
.gt-formula-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 12px;
  background: #fafafa;
  border-bottom: 1px solid #e8e8e8;
  min-height: 32px;
  font-size: 13px;
}
.addr-box {
  display: flex;
  align-items: center;
  gap: 4px;
  min-width: 80px;
  padding: 2px 8px;
  background: #fff;
  border: 1px solid #dcdfe6;
  border-radius: 4px;
  font-family: monospace;
  font-size: 12px;
  font-weight: 600;
  color: #4b2d77;
}
.formula-box {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 4px;
  background: #fff;
  border: 1px solid #dcdfe6;
  border-radius: 4px;
  padding: 2px 8px;
}
.fx-icon {
  font-style: italic;
  font-weight: bold;
  color: #909399;
  font-size: 12px;
  user-select: none;
}
.formula-input {
  flex: 1;
  border: none;
  outline: none;
  font-family: "Consolas", "Monaco", monospace;
  font-size: 12px;
  background: transparent;
}
.formula-input:focus {
  color: #303133;
}
.formula-actions {
  display: flex;
  gap: 2px;
}
.formula-meta {
  display: flex;
  align-items: center;
  gap: 6px;
}
.formula-desc {
  font-size: 11px;
  color: #909399;
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
