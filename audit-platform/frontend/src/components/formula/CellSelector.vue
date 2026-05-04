<template>
  <el-dialog
    v-model="visible"
    title="可视化取数选择器"
    width="800px"
    append-to-body
    @close="onClose"
  >
    <div class="cell-selector">
      <!-- 数据源选择 -->
      <div class="source-tabs">
        <el-radio-group v-model="activeSource" size="small">
          <el-radio-button value="trial_balance">试算表</el-radio-button>
          <el-radio-button value="report">报表</el-radio-button>
          <el-radio-button value="note">附注</el-radio-button>
          <el-radio-button value="aux_balance">辅助余额</el-radio-button>
          <el-radio-button value="workpaper">底稿</el-radio-button>
        </el-radio-group>
      </div>

      <!-- 已选择的单元格列表 -->
      <div v-if="selectedCells.length" class="selected-cells">
        <div class="selected-header">
          <span>已选择 {{ selectedCells.length }} 个数据源</span>
          <el-select v-model="transform" size="small" style="width: 120px">
            <el-option value="direct" label="直接取值" />
            <el-option value="sum" label="求和" />
            <el-option value="diff" label="相减" />
            <el-option value="negate" label="取反" />
            <el-option value="abs" label="绝对值" />
          </el-select>
        </div>
        <div class="cell-tags">
          <el-tag
            v-for="(cell, idx) in selectedCells"
            :key="idx"
            closable
            size="small"
            @close="removeCell(idx)"
          >
            {{ formatCellLabel(cell) }}
          </el-tag>
        </div>
      </div>

      <!-- 试算表选择 -->
      <div v-if="activeSource === 'trial_balance'" class="source-panel">
        <el-input v-model="tbSearch" placeholder="搜索科目编码/名称" clearable size="small" style="margin-bottom: 8px" />
        <el-table
          :data="filteredTbData"
          size="small"
          max-height="300"
          highlight-current-row
          @row-click="onTbRowClick"
        >
          <el-table-column prop="account_code" label="科目编码" width="100" />
          <el-table-column prop="account_name" label="科目名称" min-width="120" />
          <el-table-column label="选择字段" width="200">
            <template #default="{ row }">
              <el-button-group size="small">
                <el-button @click.stop="selectTbCell(row, 'audited_amount')">审定数</el-button>
                <el-button @click.stop="selectTbCell(row, 'unadjusted_amount')">未审数</el-button>
                <el-button @click.stop="selectTbCell(row, 'opening_balance')">期初</el-button>
              </el-button-group>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <!-- 报表选择 -->
      <div v-if="activeSource === 'report'" class="source-panel">
        <el-input v-model="reportSearch" placeholder="搜索报表行" clearable size="small" style="margin-bottom: 8px" />
        <el-table :data="filteredReportData" size="small" max-height="300">
          <el-table-column prop="row_code" label="行次" width="80" />
          <el-table-column prop="row_name" label="项目" min-width="150" />
          <el-table-column label="选择" width="150">
            <template #default="{ row }">
              <el-button size="small" @click="selectReportCell(row, 'amount')">期末</el-button>
              <el-button size="small" @click="selectReportCell(row, 'prior_amount')">期初</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <!-- 附注选择 -->
      <div v-if="activeSource === 'note'" class="source-panel">
        <el-select v-model="noteSection" placeholder="选择附注章节" size="small" style="width: 200px; margin-bottom: 8px">
          <el-option v-for="s in noteSections" :key="s" :value="s" :label="s" />
        </el-select>
        <p class="hint">选择附注章节后，点击表格中的单元格进行选择（支持跳行跳列）</p>
      </div>

      <!-- 辅助余额选择 -->
      <div v-if="activeSource === 'aux_balance'" class="source-panel">
        <el-input v-model="auxSearch" placeholder="搜索科目/辅助编码" clearable size="small" style="margin-bottom: 8px" />
        <p class="hint">输入科目编码和辅助编码，选择期末/期初余额</p>
        <div class="aux-form">
          <el-input v-model="auxAccountCode" placeholder="科目编码" size="small" style="width: 120px" />
          <el-input v-model="auxCode" placeholder="辅助编码" size="small" style="width: 120px" />
          <el-button size="small" @click="selectAuxCell('closing_balance')">期末</el-button>
          <el-button size="small" @click="selectAuxCell('opening_balance')">期初</el-button>
        </div>
      </div>

      <!-- 底稿选择 -->
      <div v-if="activeSource === 'workpaper'" class="source-panel">
        <el-input v-model="wpCode" placeholder="底稿编号如E1-1" size="small" style="width: 150px; margin-bottom: 8px" />
        <el-select v-model="wpDataKey" size="small" style="width: 150px">
          <el-option value="audited_amount" label="审定数" />
          <el-option value="unadjusted_amount" label="未审数" />
          <el-option value="opening_balance" label="期初" />
        </el-select>
        <el-button size="small" type="primary" @click="selectWpCell">添加</el-button>
      </div>

      <!-- 描述 -->
      <div class="desc-input">
        <el-input v-model="description" placeholder="取数说明（如：货币资金期末=库存现金+银行存款）" size="small" />
      </div>
    </div>

    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" :disabled="!selectedCells.length" @click="onConfirm">
        确认生成规则
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useAddressRegistry } from '@/stores/addressRegistry'

const addrStore = useAddressRegistry()

const props = defineProps<{
  modelValue: boolean
  trialBalanceData?: any[]
  reportData?: any[]
  noteSections?: string[]
}>()

const emit = defineEmits<{
  'update:modelValue': [val: boolean]
  'confirm': [rule: any]
}>()

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

// 弹窗打开时，如果 store 已加载则优先使用 store 数据
watch(visible, (v) => {
  if (v && addrStore.loaded) {
    // store 数据可用，无需额外操作
  }
})

const activeSource = ref('trial_balance')
const selectedCells = ref<any[]>([])
const transform = ref('direct')
const description = ref('')

// ─── 数据源：优先 store，回退 props ───

// 试算表
const tbSearch = ref('')
const filteredTbData = computed(() => {
  // 优先使用 store 中的试算表地址
  if (addrStore.loaded && addrStore.tbAddresses.length > 0) {
    const entries = addrStore.tbAddresses
    if (!tbSearch.value) return entries.slice(0, 50)
    const kw = tbSearch.value.toLowerCase()
    return entries.filter(e =>
      (e.account_code || '').includes(kw) || (e.label || '').toLowerCase().includes(kw)
    ).slice(0, 50)
  }
  // 回退到 props
  const data = props.trialBalanceData || []
  if (!tbSearch.value) return data.slice(0, 50)
  const kw = tbSearch.value.toLowerCase()
  return data.filter((r: any) =>
    (r.account_code || '').includes(kw) || (r.account_name || '').toLowerCase().includes(kw)
  ).slice(0, 50)
})

// 报表
const reportSearch = ref('')
const filteredReportData = computed(() => {
  // 优先使用 store 中的报表地址
  if (addrStore.loaded && addrStore.reportAddresses.length > 0) {
    const entries = addrStore.reportAddresses
    if (!reportSearch.value) return entries
    const kw = reportSearch.value.toLowerCase()
    return entries.filter(e =>
      (e.row_code || '').includes(kw) || (e.label || '').toLowerCase().includes(kw)
    )
  }
  // 回退到 props
  const data = props.reportData || []
  if (!reportSearch.value) return data
  const kw = reportSearch.value.toLowerCase()
  return data.filter((r: any) =>
    (r.row_code || '').includes(kw) || (r.row_name || '').toLowerCase().includes(kw)
  )
})

// 附注
const noteSection = ref('')
const noteSections = computed(() => {
  // 优先使用 store 中的附注地址提取章节列表
  if (addrStore.loaded && addrStore.noteAddresses.length > 0) {
    const sections = [...new Set(addrStore.noteAddresses.map(e => e.note_section).filter(Boolean))]
    return sections.length > 0 ? sections as string[] : props.noteSections || []
  }
  return props.noteSections || []
})

// 辅助余额
const auxSearch = ref('')
const auxAccountCode = ref('')
const auxCode = ref('')

// 底稿
const wpCode = ref('')
const wpDataKey = ref('audited_amount')

function selectTbCell(row: any, field: string) {
  // 兼容 store AddressEntry 和 legacy row 格式
  const code = row.account_code || row.standard_account_code || ''
  const name = row.account_name || row.label || ''
  selectedCells.value.push({
    type: 'trial_balance',
    account_code: code,
    field,
    _label: `${code} ${name} · ${fieldLabel(field)}`,
  })
}

function selectReportCell(row: any, field: string) {
  const code = row.row_code || ''
  const name = row.row_name || row.label || ''
  selectedCells.value.push({
    type: 'report',
    row_code: code,
    field,
    _label: `[${code}] ${name} · ${field === 'amount' ? '期末' : '期初'}`,
  })
}

function selectAuxCell(field: string) {
  if (!auxAccountCode.value) return
  selectedCells.value.push({
    type: 'aux_balance',
    account_code: auxAccountCode.value,
    aux_code: auxCode.value,
    field,
    _label: `辅助 ${auxAccountCode.value}:${auxCode.value || '*'} · ${field === 'closing_balance' ? '期末' : '期初'}`,
  })
}

function selectWpCell() {
  if (!wpCode.value) return
  selectedCells.value.push({
    type: 'workpaper',
    wp_code: wpCode.value,
    data_key: wpDataKey.value,
    _label: `底稿 ${wpCode.value} · ${fieldLabel(wpDataKey.value)}`,
  })
}

function onTbRowClick(_row: any) {
  // 行点击不做操作，通过按钮选择字段
}

function removeCell(idx: number) {
  selectedCells.value.splice(idx, 1)
}

function formatCellLabel(cell: any) {
  return cell._label || `${cell.type}:${cell.account_code || cell.row_code || cell.wp_code}`
}

function fieldLabel(field: string) {
  const map: Record<string, string> = {
    audited_amount: '审定数',
    unadjusted_amount: '未审数',
    opening_balance: '期初',
    aje_adjustment: 'AJE',
    rje_adjustment: 'RJE',
    amount: '期末',
    prior_amount: '期初',
    closing_balance: '期末',
  }
  return map[field] || field
}

function onConfirm() {
  const sources = selectedCells.value.map(c => {
    const { _label, ...source } = c
    return source
  })
  emit('confirm', {
    sources,
    transform: transform.value,
    description: description.value,
  })
  selectedCells.value = []
  description.value = ''
  visible.value = false
}

function onClose() {
  // 不清空已选，用户可能误关
}
</script>

<style scoped>
.cell-selector { min-height: 400px; }
.source-tabs { margin-bottom: 12px; }
.selected-cells { margin-bottom: 12px; padding: 8px 12px; background: #f9f7fc; border-radius: 6px; }
.selected-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px; font-size: 13px; color: #606266; }
.cell-tags { display: flex; flex-wrap: wrap; gap: 4px; }
.source-panel { min-height: 200px; }
.hint { font-size: 12px; color: #909399; margin: 4px 0; }
.aux-form { display: flex; gap: 8px; align-items: center; }
.desc-input { margin-top: 12px; }
</style>
