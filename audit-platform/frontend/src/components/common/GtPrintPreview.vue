<template>
  <el-dialog
    v-model="visible"
    title="打印预览"
    width="90%"
    top="3vh"
    :close-on-click-modal="false"
    append-to-body
    class="gt-print-preview-dialog"
  >
    <div class="gt-print-controls">
      <el-select v-model="paperSize" size="small" style="width: 120px">
        <el-option label="A4 纵向" value="a4-portrait" />
        <el-option label="A4 横向" value="a4-landscape" />
        <el-option label="A3 横向" value="a3-landscape" />
      </el-select>
      <el-checkbox v-model="showGridLines" size="small">显示网格线</el-checkbox>
      <el-checkbox v-model="showHeader" size="small">显示表头</el-checkbox>
      <span style="flex:1" />
      <el-button type="primary" size="small" @click="handlePrint">🖨️ 打印</el-button>
    </div>

    <div ref="printAreaRef" class="gt-print-area" :class="[paperSize, { 'no-grid': !showGridLines }]">
      <div v-if="title" class="gt-print-title">{{ title }}</div>
      <div v-if="subtitle" class="gt-print-subtitle">{{ subtitle }}</div>

      <table class="gt-print-table" border="1" cellspacing="0" cellpadding="4">
        <thead v-if="showHeader">
          <tr>
            <th v-for="col in printColumns" :key="col.prop" :style="{ width: col.width ? col.width + 'px' : 'auto' }">
              {{ col.label }}
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(row, ri) in data" :key="ri">
            <td v-for="col in printColumns" :key="col.prop" :style="{ textAlign: (col.align || 'left') as any }">
              {{ formatValue(row, col) }}
            </td>
          </tr>
        </tbody>
      </table>

      <div class="gt-print-footer">
        <span>{{ footerLeft }}</span>
        <span>共 {{ data.length }} 行</span>
        <span>{{ footerRight || new Date().toLocaleDateString() }}</span>
      </div>
    </div>
  </el-dialog>
</template>

<script setup lang="ts">
/**
 * GtPrintPreview — 打印预览弹窗 [R10.6]
 *
 * 提供表格数据的打印预览和打印功能。
 * 支持纸张大小选择、网格线开关、表头开关。
 */
import { ref, computed } from 'vue'

interface PrintColumn {
  prop: string
  label: string
  width?: number | string
  align?: string
  formatter?: (value: any, row: any) => string
}

const props = withDefaults(defineProps<{
  modelValue: boolean
  data: Record<string, any>[]
  columns: PrintColumn[]
  title?: string
  subtitle?: string
  footerLeft?: string
  footerRight?: string
}>(), {
  title: '',
  subtitle: '',
  footerLeft: '',
  footerRight: '',
})

const emit = defineEmits<{
  (e: 'update:modelValue', val: boolean): void
}>()

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const paperSize = ref('a4-portrait')
const showGridLines = ref(true)
const showHeader = ref(true)
const printAreaRef = ref<HTMLElement | null>(null)

const printColumns = computed(() => props.columns.filter((c: any) => !c.hidden))

function formatValue(row: Record<string, any>, col: PrintColumn): string {
  if (col.formatter) return col.formatter(row[col.prop], row)
  const val = row[col.prop]
  return val == null || val === '' ? '' : String(val)
}

function handlePrint() {
  const el = printAreaRef.value
  if (!el) return

  const printWindow = window.open('', '_blank', 'width=900,height=700')
  if (!printWindow) return

  const orientation = paperSize.value.includes('landscape') ? 'landscape' : 'portrait'

  printWindow.document.write(`
    <!DOCTYPE html>
    <html>
    <head>
      <title>${props.title || '打印预览'}</title>
      <style>
        @page { size: ${orientation}; margin: 15mm; }
        body { font-family: 'Microsoft YaHei', sans-serif; font-size: var(--gt-font-size-xs); }
        .gt-print-title { text-align: center; font-size: var(--gt-font-size-xl); font-weight: bold; margin-bottom: 8px; }
        .gt-print-subtitle { text-align: center; font-size: var(--gt-font-size-sm); color: var(--gt-color-text-secondary); margin-bottom: 12px; }
        table { width: 100%; border-collapse: collapse; }
        th, td { border: 1px solid #333; padding: 4px 8px; font-size: var(--gt-font-size-xs); }
        th { background: var(--gt-color-border-lighter); font-weight: bold; }
        .gt-print-footer { display: flex; justify-content: space-between; margin-top: 12px; font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); }
        ${!showGridLines.value ? 'th, td { border: none; }' : ''}
      </style>
    </head>
    <body>${el.innerHTML}</body>
    </html>
  `)
  printWindow.document.close()
  printWindow.focus()
  setTimeout(() => {
    printWindow.print()
    printWindow.close()
  }, 300)
}
</script>

<style scoped>
.gt-print-controls {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
  padding: 8px 12px;
  background: var(--gt-color-bg);
  border-radius: 4px;
}

.gt-print-area {
  border: 1px solid #ddd;
  padding: 20px;
  background: white;
  min-height: 400px;
  max-height: 70vh;
  overflow: auto;
}

.gt-print-area.a4-landscape {
  min-width: 800px;
}

.gt-print-title {
  text-align: center;
  font-size: var(--gt-font-size-xl);
  font-weight: bold;
  margin-bottom: 8px;
}

.gt-print-subtitle {
  text-align: center;
  font-size: var(--gt-font-size-sm);
  color: var(--gt-color-text-secondary);
  margin-bottom: 12px;
}

.gt-print-table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--gt-font-size-xs);
}

.gt-print-table th,
.gt-print-table td {
  border: 1px solid #333;
  padding: 4px 8px;
}

.gt-print-table th {
  background: var(--gt-color-border-lighter);
  font-weight: bold;
  font-size: var(--gt-font-size-xs);
}

.no-grid .gt-print-table th,
.no-grid .gt-print-table td {
  border: none;
  border-bottom: 1px solid #eee;
}

.gt-print-footer {
  display: flex;
  justify-content: space-between;
  margin-top: 12px;
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-text-tertiary);
}
</style>
