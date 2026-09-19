<template>
  <div class="l1-tab-disclosure-soe">
    <!-- ═══ 返回目录 + 标题 + AI辅助 ═══ -->
    <div class="disclosure-header">
      <div class="disclosure-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">← 返回目录</el-button>
        <h3 class="disclosure-title">附注披露信息核对（国有企业）</h3>
      </div>
      <div class="disclosure-header-right">
        <el-button size="small" type="success" :loading="syncing" :disabled="isReadonly" @click="syncToDisclosureNotes">
          同步到附注（八、33）
        </el-button>
        <el-button size="small" type="primary" plain :disabled="!projectId" @click="jumpToNote('soe')">↩ 跳转回附注</el-button>
        <el-tag type="info" effect="dark" size="small">国有企业版</el-tag>
      </div>
    </div>

    <!-- ═══ 方法论上下文 ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>国有企业附注披露（对齐源模板）：</strong>
        (1) 短期借款分类按借款类别（质押/抵押/保证/信用）列示期末余额、年初余额，数据由审定表 L1-1 各分类审定数自动派生（披露 → 审定 → 明细 链一致）；
        (2) 已逾期未偿还的短期借款情况（债权单位/期末余额/借款利率）由审计师录入，可从 L1-7 逾期检查带入。
      </div>
    </div>

    <!-- ═══ (1) 短期借款分类（自审定表派生·只读） ═══ -->
    <div class="block-section">
      <h4 class="block-title">（1）短期借款分类</h4>
      <el-table :data="categoryDisplay" border size="small" style="width:100%" :row-class-name="rowCls">
        <el-table-column prop="category" label="借款类别" min-width="140" />
        <el-table-column label="期末余额" width="180" align="right">
          <template #default="{ row }"><span class="formula-value">{{ fmt(row.endBalance) }}</span></template>
        </el-table-column>
        <el-table-column label="年初余额" width="180" align="right">
          <template #default="{ row }"><span class="formula-value">{{ fmt(row.beginBalance) }}</span></template>
        </el-table-column>
      </el-table>
      <div class="derive-hint">期末/年初余额 = 审定表 L1-1 各分类审定期末/期初数（自动派生）</div>
    </div>

    <!-- ═══ (2) 已逾期未偿还的短期借款情况 ═══ -->
    <div class="block-section">
      <div class="block-head">
        <h4 class="block-title">（2）已逾期未偿还的短期借款情况</h4>
        <div v-if="!isReadonly" class="block-actions">
          <el-button size="small" @click="handleImportOverdue">从 L1-7 逾期检查带入</el-button>
          <el-button size="small" type="primary" plain @click="addOverdueRow">+ 新增</el-button>
        </div>
      </div>
      <el-table :data="overdueRows" border size="small" style="width:100%" show-summary :summary-method="getOverdueSummary">
        <el-table-column type="index" label="序号" width="55" align="center" />
        <el-table-column label="债权单位" min-width="180">
          <template #default="{ row, $index }">
            <el-input v-if="!isReadonly" :model-value="row.borrower" size="small" placeholder="债权单位" @input="(v:string)=>updateOverdueRow($index,'borrower',v)" />
            <span v-else>{{ row.borrower || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" width="150" align="right">
          <template #default="{ row, $index }">
            <el-input-number v-if="!isReadonly" :model-value="row.endBalance" :controls="false" size="small" style="width:100%" @change="(v:number|undefined)=>updateOverdueRow($index,'endBalance',v??0)" />
            <span v-else>{{ fmt(row.endBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="借款利率(%)" width="130" align="right">
          <template #default="{ row, $index }">
            <el-input-number v-if="!isReadonly" :model-value="row.rate" :controls="false" :precision="4" size="small" style="width:100%" @change="(v:number|undefined)=>updateOverdueRow($index,'rate',v??0)" />
            <span v-else>{{ row.rate ? row.rate + '%' : '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="" width="60" align="center">
          <template #default="{ $index }"><el-button type="danger" text size="small" @click="removeOverdueRow($index)">删除</el-button></template>
        </el-table-column>
      </el-table>
    </div>

    <!-- ═══ 说明 ═══ -->
    <el-card shadow="never" class="note-card">
      <template #header><span class="card-title">说明</span></template>
      <el-input :model-value="noteText" type="textarea" :autosize="{ minRows: 3 }" :disabled="isReadonly"
        :placeholder="NOTE_PLACEHOLDER" @input="updateNote" />
    </el-card>

    <!-- ═══ 审计结论 + AI ═══ -->
    <el-card shadow="never" class="note-card">
      <template #header>
        <div class="conclusion-header"><span class="card-title">审计结论</span>
          <el-button size="small" type="primary" plain :loading="aiLoading" :disabled="isReadonly" @click="handleAiConclusion">🤖 AI生成结论</el-button>
        </div>
      </template>
      <el-input :model-value="conclusionText" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="请输入附注披露核对结论..." :disabled="isReadonly" @input="updateConclusion" />
    </el-card>

    <details class="l1-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>分类表 4 类（信用/抵押/保证/质押）期末/年初余额自审定表 L1-1 各分类审定数派生，与明细表 L1-2 勾稽一致</li>
        <li>逾期借款须注明债权单位、期末余额、借款利率，并在期后事项反映报表日后是否已偿还、展期条件</li>
        <li>说明：①资产负债表日后已偿还金额 ②已到期或展期的展期条件、新到期日</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * L1TabDisclosureSoe — 附注披露信息核对（国有企业，2026-07 复盘重建）
 *
 * 对齐致同源模板：(1) 短期借款分类（4类·自审定表 L1-1 派生）+ (2) 已逾期未偿还情况（审计师录入）+ 说明。
 * ⚠️ 旧版为 bank-level 手工录入 + 死链交叉校验（读 L1-detail-total-end 从不写 → 恒"一致"）。
 */
import { computed, inject, toRef, ref, onMounted, onUnmounted, onBeforeUnmount, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import http from '@/utils/http'
import { eventBus } from '@/utils/eventBus'
import type { useL1FormData } from '@/composables/useL1FormData'
import { useL1DisclosureData } from '@/composables/useL1DisclosureData'
import { L1_NOTE_SECTION, buildL1SyncPayload } from '../../composables/l1NoteSectionMap'
import { buildNoteJumpRoute } from '@/views/composables/noteDisclosureReverseJump'
import { useDisclosureAutoSync } from '../../composables/useDisclosureAutoSync'

const props = defineProps<{ wpId: string; projectId: string; isReadonly: boolean }>()
defineEmits<{ (e: 'navigate', sheetName: string): void }>()

const formData = inject<ReturnType<typeof useL1FormData>>('l1FormData')!
const isReadonlyRef = toRef(props, 'isReadonly')
const router = useRouter()

function jumpToNote(variant: 'listed' | 'soe') {
  const route = buildNoteJumpRoute(props.projectId, 'L1', variant)
  if (route) router.push(route)
}

const {
  categoryRows, categoryTotal, overdueRows, overdueTotal,
  addOverdueRow, removeOverdueRow, updateOverdueRow, importFromOverdueCheck,
  noteText, conclusionText, updateNote, updateConclusion,
} = useL1DisclosureData(formData, { variant: 'soe', isReadonly: isReadonlyRef })

const NOTE_PLACEHOLDER =
  '① 资产负债表日后已偿还金额 ___ 元。\n' +
  '② 已到期短期借款或展期的，若已到期的短期借款获得展期，应说明展期条件、新到期日等。'

// 分类表 + 合计行
const categoryDisplay = computed(() => [
  ...categoryRows.value.map(r => ({ ...r, _isTotal: false })),
  { category: '合  计', beginBalance: categoryTotal.value.begin, endBalance: categoryTotal.value.end, _isTotal: true },
])

function rowCls({ row }: { row: any }): string { return row._isTotal ? 'total-row' : '' }

function getOverdueSummary({ columns }: { columns: any[] }) {
  const sums: string[] = []
  columns.forEach((_c: any, i: number) => {
    if (i === 1) sums[i] = '合计'
    else if (i === 2) sums[i] = fmt(overdueTotal.value)
    else sums[i] = ''
  })
  return sums
}

function handleImportOverdue() {
  const n = importFromOverdueCheck()
  if (n > 0) ElMessage.success(`已从 L1-7 带入 ${n} 笔逾期借款`)
  else ElMessage.info('L1-7 逾期检查暂无逾期数据可带入')
}

const aiLoading = ref(false)
async function handleAiConclusion() {
  if (props.isReadonly) return
  aiLoading.value = true
  try {
    const context: Record<string, string> = {
      期末合计: String(categoryTotal.value.end),
      年初合计: String(categoryTotal.value.begin),
      分类明细: categoryRows.value.map(r => `${r.category}:期末${r.endBalance}`).join('；'),
      逾期笔数: String(overdueRows.value.length),
      逾期合计: String(overdueTotal.value),
    }
    const res = await http.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section: 'L1-disclosure-soe-conclusion',
      prompt: '请基于国有企业短期借款附注披露数据生成核对结论，说明分类披露完整性、与审定表/明细勾稽、逾期披露情况。',
      existingContent: conclusionText.value,
      context,
    })
    const content = (res.data?.data ?? res.data)?.content
    if (content) updateConclusion(content)
    else ElMessage.info('AI 未返回内容，请手动撰写')
  } catch {
    ElMessage.info('AI 辅助暂不可用，请手动撰写')
  } finally {
    aiLoading.value = false
  }
}

// ─── 同步到附注模块 ─────────────────────────────────────────────────────────
const syncing = ref(false)
async function syncToDisclosureNotes() {
  if (props.isReadonly || !props.projectId) return
  syncing.value = true
  try {
    const { sub_table_data, columns } = buildL1SyncPayload({
      variant: 'soe',
      categoryRows: categoryRows.value,
      categoryTotal: categoryTotal.value,
      overdueRows: overdueRows.value,
      conclusionText: conclusionText.value,
    })
    await http.post(`/api/projects/${props.projectId}/disclosure-notes/sync-from-workpaper`, {
      wp_id: props.wpId,
      sheet_name: 'L1-note-soe',
      section_id: L1_NOTE_SECTION.soe,
      current_standard: 'soe_standalone',
      sub_table_data,
      columns,
    })
    ElMessage.success(`已同步到附注（${L1_NOTE_SECTION.soe}）`)
    eventBus.emit('disclosure:note-text-updated' as any, {
      wpCode: 'L1',
      accountCode: '2001',
      projectId: props.projectId,
      sectionIds: [L1_NOTE_SECTION.soe],
    })
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '同步到附注失败')
  } finally {
    syncing.value = false
  }
}

function fmt(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  if (val < 0) return `(${Math.abs(val).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })})`
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// ─── EventBus: 审定表变化后自动刷新披露分类表 ──────────────────────────────────
function onAdjudicatedRefresh() {
  formData.selfLoad()
}

onMounted(() => {
  eventBus.on('substantive:adjudicated' as any, onAdjudicatedRefresh)
})

onUnmounted(() => {
  eventBus.off('substantive:adjudicated' as any, onAdjudicatedRefresh)
})

// ─── 保存后自动同步到附注（防抖/非阻塞/失败静默）──────────────────────────────
const autoSync = useDisclosureAutoSync({ isReadonly: () => props.isReadonly })
onBeforeUnmount(() => autoSync.cancelPending())
watch(
  [overdueRows, noteText, conclusionText],
  () => {
    autoSync.scheduleAutoSync(syncToDisclosureNotes)
  },
  { deep: true },
)
</script>

<style scoped>
.l1-tab-disclosure-soe { padding: 12px; font-size: var(--wp-font-size, 13px); }
.disclosure-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.disclosure-header-left { display: flex; align-items: center; gap: 12px; }
.disclosure-title { font-size: 15px; font-weight: 600; color: #303133; margin: 0; }

.methodology-context { border-left: 4px solid #f59e0b; background: #fffbeb; padding: 10px 14px; border-radius: 0 6px 6px 0; margin-bottom: 16px; font-size: var(--wp-font-size, 13px); color: #78350f; line-height: 1.6; }
.methodology-text strong { color: #b45309; }

.block-section { margin-bottom: 20px; }
.block-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.block-actions { display: flex; gap: 8px; }
.block-title { margin: 0 0 8px; font-size: 14px; font-weight: 600; color: #303133; }
.derive-hint { margin-top: 6px; font-size: 12px; color: #909399; }

.formula-value { color: #409eff; font-weight: 500; }
:deep(.total-row) { background-color: #f0f9eb !important; font-weight: 700; }
:deep(.el-table) { font-size: var(--wp-font-size, 13px); }
:deep(.el-table th .cell) { font-size: var(--wp-font-size, 13px); font-weight: 600; }

.note-card { margin-top: 16px; }
.card-title { font-size: 14px; font-weight: 600; color: #303133; }
.conclusion-header { display: flex; align-items: center; justify-content: space-between; }
.note-card :deep(.el-textarea__inner) { font-size: var(--wp-font-size, 13px); }

.l1-details-tip { margin-top: 16px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #606266; }
.l1-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; margin-bottom: 8px; }
.l1-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
