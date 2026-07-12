<template>
  <div class="g1-biz-model">
    <div class="section-head">
      <h3 class="sheet-title">G1-8 业务模式分析（CAS22）</h3>
      <div class="head-actions">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow">新增投资项目</el-button>
        <span class="chip-wrap"><GtIndexChip value="wp:G1-1" /></span>
        <el-tag size="small" type="info">共 {{ rows.length }} 行</el-tag>
        <el-button size="small" @click="openReviewDialog('G1-8-conclusion')">💬复核</el-button>
      </div>
    </div>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：评价被审计单位金融资产业务模式（CAS22）判定的恰当性，确认业务模式与持有目的、交易频率、管理层意图一致，为金融资产分类适当性提供依据。"
      class="objective-alert"
    />

    <div class="methodology">
      业务模式判定依据 CAS22：以收取合同现金流量为目标（持有至收取）/ 既收取又出售 / 其他（出售）。
      应结合持有目的、历史交易频率、管理层意图及 KPI 考核机制综合判断。
    </div>

    <el-table :data="rows" border size="small" max-height="520">
      <el-table-column label="序号" width="60" fixed="left">
        <template #default="{ $index }">{{ $index + 1 }}</template>
      </el-table-column>
      <el-table-column label="投资项目" width="160" fixed="left">
        <template #default="{ row }">
          <el-input v-model="row.investItem" size="small" :disabled="isReadonly"
            @change="updateRow(row.id, { investItem: row.investItem })" />
        </template>
      </el-table-column>
      <el-table-column
        v-for="col in narrativeCols"
        :key="col.prop"
        :label="col.label"
        :min-width="col.minWidth"
      >
        <template #default="{ row }">
          <el-input v-model="row[col.prop]" type="textarea" :autosize="{ minRows: 1, maxRows: 6 }"
            size="small" :disabled="isReadonly" @change="updateRow(row.id, { [col.prop]: row[col.prop] })" />
        </template>
      </el-table-column>
      <el-table-column label="分类结论" width="150">
        <template #default="{ row }">
          <el-select v-model="row.conclusion" size="small" :disabled="isReadonly"
            @change="updateRow(row.id, { conclusion: row.conclusion })">
            <el-option v-for="o in CONCLUSION_OPTIONS" :key="o.value" :value="o.value" :label="o.label" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="审计评价" min-width="180">
        <template #default="{ row }">
          <el-input v-model="row.auditEval" type="textarea" :autosize="{ minRows: 1, maxRows: 6 }"
            size="small" :disabled="isReadonly" @change="updateRow(row.id, { auditEval: row.auditEval })" />
        </template>
      </el-table-column>
      <el-table-column label="操作" width="60" fixed="right">
        <template #default="{ row }">
          <el-button v-if="!isReadonly" size="small" type="danger" link @click="removeRow(row.id)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-card class="conclusion-card" shadow="never">
      <template #header>审计结论</template>
      <el-input v-model="conclusion" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }"
        :disabled="isReadonly" placeholder="对业务模式分析的整体复核结论..." />
    </el-card>

    <details class="prep-hint">
      <summary>📋 编制提示</summary>
      <ul>
        <li>业务模式在主体层面（而非单项工具层面）判定，交易性金融资产通常为「出售」模式。</li>
        <li>需关注历史交易频率与管理层意图的一致性，出售频繁支持 FVTPL 分类。</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, inject } from 'vue'
import { ElMessageBox } from 'element-plus'
import type { ChecklistResponse } from '../../composables/useF1FormData'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})

const DATA_KEY = 'G1-8-rows'
const CONCLUSION_KEY = 'G1-8-conclusion'

interface BusinessModelRow {
  id: string
  investItem: string
  bizModelDesc: string
  holdingPurpose: string
  tradeFrequency: string
  managementIntent: string
  kpiRelation: string
  conclusion: string
  auditEval: string
}

const narrativeCols = [
  { prop: 'bizModelDesc' as const, label: '业务模式描述', minWidth: 180 },
  { prop: 'holdingPurpose' as const, label: '持有目的', minWidth: 150 },
  { prop: 'tradeFrequency' as const, label: '历史交易频率', minWidth: 150 },
  { prop: 'managementIntent' as const, label: '管理层意图', minWidth: 150 },
  { prop: 'kpiRelation' as const, label: 'KPI考核关联', minWidth: 150 },
]

const CONCLUSION_OPTIONS = [
  { value: 'hold-collect', label: '持有至收取' },
  { value: 'sell', label: '出售' },
  { value: 'both', label: '兼有' },
]

function emptyRow(id: string): BusinessModelRow {
  return {
    id,
    investItem: '',
    bizModelDesc: '',
    holdingPurpose: '',
    tradeFrequency: '',
    managementIntent: '',
    kpiRelation: '',
    conclusion: '',
    auditEval: '',
  }
}

function loadRows(): BusinessModelRow[] {
  const raw = props.allResponses.get(DATA_KEY)?.conclusion
  if (!raw) return [emptyRow('1')]
  try {
    const parsed = JSON.parse(raw) as BusinessModelRow[]
    return Array.isArray(parsed) && parsed.length ? parsed : [emptyRow('1')]
  } catch {
    return [emptyRow('1')]
  }
}

const rows = ref<BusinessModelRow[]>(loadRows())
const conclusion = ref(props.allResponses.get(CONCLUSION_KEY)?.conclusion ?? '')

function persist() {
  if (props.isReadonly) return
  props.debouncedSave(DATA_KEY, { conclusion: JSON.stringify(rows.value) })
}

function updateRow(id: string, patch: Partial<BusinessModelRow>) {
  if (props.isReadonly) return
  rows.value = rows.value.map((r) => (r.id === id ? { ...r, ...patch } : r))
  persist()
}

async function addRow() {
  if (props.isReadonly) return
  try {
    const { value } = await ElMessageBox.prompt('请输入投资项目名称', '新增投资项目', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputPattern: /\S+/,
      inputErrorMessage: '投资项目名称不能为空',
    })
    rows.value = [...rows.value, { ...emptyRow(`row-${Date.now()}`), investItem: value }]
    persist()
  } catch {
    /* cancelled */
  }
}

function removeRow(id: string) {
  if (props.isReadonly || rows.value.length <= 1) return
  rows.value = rows.value.filter((r) => r.id !== id)
  persist()
}

watch(conclusion, (v) => {
  if (!props.isReadonly) props.debouncedSave(CONCLUSION_KEY, { conclusion: v })
})
</script>

<style scoped>
.g1-biz-model { padding: 12px; font-size: var(--wp-font-size, 13px); }
.g1-biz-model :deep(.el-table) { --el-table-font-size: var(--wp-font-size, 13px); font-size: var(--wp-font-size, 13px); }
.g1-biz-model :deep(.el-table .cell) { font-size: var(--wp-font-size, 13px); }
.section-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.sheet-title { margin: 0; font-size: 15px; }
.head-actions { display: flex; gap: 8px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }
.objective-alert { margin-bottom: 12px; }
.methodology { margin-bottom: 12px; padding: 8px 12px; background: #fdf6ec; border-left: 3px solid #e6a23c; font-size: 12px; color: #8a6d3b; border-radius: 2px; }
.conclusion-card { margin-top: 12px; }
.prep-hint { margin-top: 12px; font-size: 12px; color: #909399; }
.prep-hint summary { cursor: pointer; }
.prep-hint ul { margin: 8px 0 0; padding-left: 18px; }
</style>
