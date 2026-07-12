<template>
  <div class="g1-disclosure">
    <div class="section-head">
      <h3 class="sheet-title">交易性金融资产附注披露（上市）</h3>
      <div class="head-actions">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="dis.addRow()">新增行</el-button>
        <el-button size="small" :disabled="isReadonly" @click="fillAiDraft">🤖AI辅助</el-button>
        <span class="chip-wrap"><GtIndexChip value="wp:G1-1" /></span>
        <el-tag size="small" type="info">共 {{ dis.rows.value.length }} 行</el-tag>
        <el-button size="small" @click="openReviewDialog('G1-note-listed')">💬复核</el-button>
      </div>
    </div>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：核实交易性金融资产附注披露（上市公司格式）项目、金额与公允价值层级分类的完整与准确，确认披露口径符合企业会计准则及监管要求，并与审定表（科目1501）勾稽一致。"
      class="objective-alert"
    />

    <el-alert
      v-if="dis.adjudicatedAmount.value !== null"
      type="success"
      :closable="false"
      class="sync-hint"
    >
      已同步审定表数据（科目1501）：期末审定数 {{ dis.adjudicatedAmount.value.toLocaleString() }}
    </el-alert>

    <div class="table-meta">
      共 {{ dis.rows.value.length }} 行 ·
      <span v-if="dis.enableVirtualScroll.value">虚拟滚动已启用（>{{ 50 }} 行）</span>
      <span v-else>标准表格</span>
    </div>

    <!-- 虚拟滚动（>50行） -->
    <el-table-v2
      v-if="dis.enableVirtualScroll.value"
      :columns="virtualColumns"
      :data="dis.rows.value"
      :width="960"
      :height="520"
      :row-height="40"
      :header-height="42"
      fixed
      class="virtual-table"
    />

    <!-- 标准表格（≤50行，可编辑） -->
    <el-table v-else :data="dis.rows.value" border size="small" max-height="520">
      <el-table-column label="项目" min-width="240">
        <template #default="{ row }">
          <el-input v-model="row.label" size="small" :disabled="isReadonly"
            @change="dis.updateCell(row.rowId, 'label', row.label)" />
        </template>
      </el-table-column>
      <el-table-column label="期末数" width="150" align="right">
        <template #default="{ row }">
          <el-input-number v-model="row.endAmount" size="small" :controls="false" :disabled="isReadonly" style="width: 100%"
            @change="dis.updateCell(row.rowId, 'endAmount', row.endAmount)" />
        </template>
      </el-table-column>
      <el-table-column label="上期数" width="150" align="right">
        <template #default="{ row }">
          <el-input-number v-model="row.priorAmount" size="small" :controls="false" :disabled="isReadonly" style="width: 100%"
            @change="dis.updateCell(row.rowId, 'priorAmount', row.priorAmount)" />
        </template>
      </el-table-column>
      <el-table-column label="备注" min-width="160">
        <template #default="{ row }">
          <el-input v-model="row.remark" size="small" :disabled="isReadonly"
            @change="dis.updateCell(row.rowId, 'remark', row.remark)" />
        </template>
      </el-table-column>
      <el-table-column label="操作" width="60" fixed="right">
        <template #default="{ row }">
          <el-button v-if="!isReadonly" size="small" type="danger" link @click="dis.removeRow(row.rowId)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="subtotal-line">
      <span class="subtotal-label">合计</span>
      期末数 {{ dis.subtotal.value.endAmount.toLocaleString() }} · 上期数 {{ dis.subtotal.value.priorAmount.toLocaleString() }}
    </div>

    <el-card class="conclusion-card" shadow="never">
      <template #header>附注说明</template>
      <el-input v-model="dis.noteText.value" type="textarea" :autosize="{ minRows: 3, maxRows: 10 }" :disabled="isReadonly"
        placeholder="交易性金融资产附注披露说明（上市公司格式）..." />
    </el-card>

    <details class="prep-hint">
      <summary>编制提示</summary>
      <ul>
        <li>上市公司附注需按公允价值层级（Level 1/2/3）分类披露交易性金融资产。</li>
        <li>审定表变更时通过 EventBus 自动同步期末审定数（科目1501）。</li>
        <li>附注说明保存后自动联动附注模块（disclosure:note-text-updated）。</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { toRef, computed, h, inject } from 'vue'
import { useG1Disclosure } from '../../composables/useG1Disclosure'
import type { ChecklistResponse } from '../../composables/useF1FormData'
import type { VirtualColumn } from '@/composables/useVirtualTable'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})

const dis = useG1Disclosure({
  variant: 'listed',
  allResponses: toRef(props, 'allResponses'),
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly'),
})

function fmtAmt(v: number): string {
  return v === 0 ? '-' : v.toLocaleString()
}

const virtualColumns = computed<VirtualColumn[]>(() => [
  {
    key: 'label',
    dataKey: 'label',
    title: '项目',
    width: 400,
    cellRenderer: ({ cellData }) => h('span', {}, cellData == null || cellData === '' ? '-' : String(cellData)),
  },
  {
    key: 'endAmount',
    dataKey: 'endAmount',
    title: '期末数',
    width: 180,
    align: 'right',
    cellRenderer: ({ cellData }) => h('span', {}, fmtAmt(Number(cellData) || 0)),
  },
  {
    key: 'priorAmount',
    dataKey: 'priorAmount',
    title: '上期数',
    width: 180,
    align: 'right',
    cellRenderer: ({ cellData }) => h('span', {}, fmtAmt(Number(cellData) || 0)),
  },
  {
    key: 'remark',
    dataKey: 'remark',
    title: '备注',
    width: 200,
    cellRenderer: ({ cellData }) => h('span', {}, cellData == null || cellData === '' ? '-' : String(cellData)),
  },
])

function fillAiDraft() {
  if (props.isReadonly) return
  const total = dis.subtotal.value.endAmount
  const draft =
    `本公司交易性金融资产（科目1501）期末余额为 ${total.toLocaleString()} 元，` +
    `以公允价值计量且其变动计入当期损益。按公允价值层级划分，Level 1 为活跃市场报价，` +
    `Level 2 为可观察输入估值，Level 3 为不可观察输入估值。公允价值变动损益已计入当期投资收益。`
  dis.noteText.value = dis.noteText.value ? `${dis.noteText.value}\n${draft}` : draft
}
</script>

<style scoped>
.g1-disclosure { padding: 12px; font-size: var(--wp-font-size, 13px); }
.g1-disclosure :deep(.el-table) { --el-table-font-size: var(--wp-font-size, 13px); font-size: var(--wp-font-size, 13px); }
.g1-disclosure :deep(.el-table .cell) { font-size: var(--wp-font-size, 13px); }
.section-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.sheet-title { margin: 0; font-size: 15px; }
.head-actions { display: flex; gap: 8px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }
.objective-alert { margin-bottom: 12px; }
.sync-hint { margin-bottom: 12px; }
.table-meta { font-size: 12px; color: #909399; margin-bottom: 8px; }
.virtual-table { border: 1px solid #ebeef5; }
.subtotal-line { margin-top: 10px; font-weight: 600; color: #303133; }
.subtotal-label { margin-right: 12px; }
.conclusion-card { margin-top: 12px; }
.prep-hint { margin-top: 12px; font-size: 12px; color: #909399; }
.prep-hint summary { cursor: pointer; }
.prep-hint ul { margin: 8px 0 0; padding-left: 18px; }
</style>
