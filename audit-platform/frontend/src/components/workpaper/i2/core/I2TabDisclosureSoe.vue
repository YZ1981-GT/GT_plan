<template>
  <div class="i2-disclosure-soe" data-testid="i2-disclosure-soe">
    <div class="section-header">
      <span class="section-title">开发支出附注披露表（国有企业）</span>
      <div class="section-actions">
        <GtIndexChip v-if="noteTarget" :value="noteTarget.chipValue" :context-project-id="props.projectId" />
        <el-button size="small" type="info" plain :disabled="isReadonly" data-testid="i2-soe-autofill" @click="handleAutoFill">
          从 I2-2/I2-6 取数
        </el-button>
        <el-button
          size="small"
          type="primary"
          plain
          :loading="isSyncing"
          :disabled="isReadonly || !props.projectId"
          data-testid="i2-soe-sync-notes"
          @click="syncToNotes"
        >同步到附注</el-button>
        <el-button size="small" type="primary" plain :disabled="!projectId" @click="jumpToNote('soe')">↩ 跳转回附注</el-button>
        <el-button size="small" type="success" :disabled="isReadonly" @click="handleSave">保存</el-button>
        <el-button size="small" type="default" text @click="handleReview">复核</el-button>
      </div>
    </div>

    <el-alert type="info" :closable="false" show-icon class="objective-alert">
      <template #title>编制目标</template>
      按项目列示开发支出期初、本期增减（内部开发/其他；转无形/转损益/其他）及期末；披露资本化时点、依据与研发进度。同步目标附注「{{ noteTarget?.sectionId || '八、28' }}」。
    </el-alert>

    <div class="methodology-context">
      <p>
        <b>编制逻辑：</b>期末＝期初＋内部开发＋其他增加－转无形－转损益－其他减少。
        项目与金额优先自 I2-2 带入；资本化时点/依据/进度自 I2-6 补齐。点「同步到附注」写入附注模块。
      </p>
    </div>

    <div class="tab-toolbar">
      <el-tag size="small" type="info">项目 {{ movementRows.length }}</el-tag>
      <el-tag size="small">期末合计 {{ fmtNum(movementSummary.end) }}</el-tag>
      <el-button size="small" @click="emit('navigate-sheet', 'I2-2')">← I2-2</el-button>
      <el-button size="small" @click="emit('navigate-sheet', '附注上市')">上市版 →</el-button>
    </div>

    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="block-title">
          <span>开发支出增减变动</span>
          <el-button size="small" plain :disabled="isReadonly" @click="addMovementRow">+ 项目</el-button>
        </div>
      </template>
      <el-table :data="movementRows" border size="small" max-height="480" show-summary :summary-method="summaryMethod">
        <el-table-column type="index" width="40" fixed />
        <el-table-column label="项目" min-width="130" fixed>
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.name" size="small" placeholder="课题/数据资源…" />
            <span v-else>{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期初余额" width="110" align="right">
          <template #default="{ row }">
            <WpAmountInput v-if="!isReadonly" v-model="row.beginBalance" :disabled="isReadonly" @change="onMovementChange(row)" />
            <span v-else>{{ fmtNum(row.beginBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期增加" align="center">
          <el-table-column label="内部开发支出" width="120" align="right">
            <template #default="{ row }">
              <WpAmountInput v-if="!isReadonly" v-model="row.increaseInternal" :disabled="isReadonly" @change="onMovementChange(row)" />
              <span v-else>{{ fmtNum(row.increaseInternal) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="其他" width="100" align="right">
            <template #default="{ row }">
              <WpAmountInput v-if="!isReadonly" v-model="row.increaseOther" :disabled="isReadonly" @change="onMovementChange(row)" />
              <span v-else>{{ fmtNum(row.increaseOther) }}</span>
            </template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="本期减少" align="center">
          <el-table-column label="确认为无形资产" width="120" align="right">
            <template #default="{ row }">
              <WpAmountInput v-if="!isReadonly" v-model="row.decreaseToIntangible" :disabled="isReadonly" @change="onMovementChange(row)" />
              <span v-else>{{ fmtNum(row.decreaseToIntangible) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="转入当期损益" width="120" align="right">
            <template #default="{ row }">
              <WpAmountInput v-if="!isReadonly" v-model="row.decreaseToExpense" :disabled="isReadonly" @change="onMovementChange(row)" />
              <span v-else>{{ fmtNum(row.decreaseToExpense) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="其他" width="100" align="right">
            <template #default="{ row }">
              <WpAmountInput v-if="!isReadonly" v-model="row.decreaseOther" :disabled="isReadonly" @change="onMovementChange(row)" />
              <span v-else>{{ fmtNum(row.decreaseOther) }}</span>
            </template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="期末余额" width="110" align="right">
          <template #default="{ row }">
            <span class="formula-cell">{{ fmtNum(row.endBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="资本化开始时点" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.capStartDate" size="small" placeholder="自I2-6" />
            <span v-else>{{ row.capStartDate || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="资本化依据" min-width="140">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.capBasis" size="small" />
            <span v-else>{{ row.capBasis || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="研发进度" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.progress" size="small" />
            <span v-else>{{ row.progress || '—' }}</span>
          </template>
        </el-table-column>
      </el-table>
      <p class="hint-blue">注：披露资本化开始时点、资本化的具体依据、截至期末的研发进度等。</p>
    </el-card>

    <el-card shadow="never" class="block-card">
      <template #header><span>附注文字说明</span></template>
      <el-input
        type="textarea"
        v-model="noteText"
        :disabled="isReadonly"
        :autosize="{ minRows: 3 }"
        placeholder="开发支出附注文字描述…"
      />
    </el-card>

    <el-card shadow="never" class="audit-card">
      <template #header><span>审计说明 / 结论</span></template>
      <el-input type="textarea" v-model="auditNote" :disabled="isReadonly" :autosize="{ minRows: 3 }" placeholder="审计说明…" />
      <el-input class="mt8" type="textarea" v-model="auditConclusion" :disabled="isReadonly" :autosize="{ minRows: 2 }" placeholder="审计结论…" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, toRef, inject, watch, onBeforeUnmount } from 'vue'
import { ElMessage } from 'element-plus'
import { useRouter } from 'vue-router'
import { buildNoteJumpRoute, type DisclosureVariant } from '@/views/composables/noteDisclosureReverseJump'
import GtIndexChip from '../../GtIndexChip.vue'
import { useI2Disclosure } from '../../composables/useI2Disclosure'
import { buildI2SoeSyncPayloads } from '../../composables/i2DisclosureSyncPayload'
import { api } from '@/services/apiProxy'
import { eventBus } from '@/utils/eventBus'
import { useDisclosureAutoSync } from '../../composables/useDisclosureAutoSync'

const props = defineProps<{
  sheetName: string
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  saveResponse: (sheetCode: string, data: Record<string, any>) => Promise<void>
  isReadonly?: boolean
  applicableStandards?: string[]
}>()

const emit = defineEmits<{ save: []; 'navigate-sheet': [sheetName: string] }>()
const openReviewDialog = inject<(section: string) => void>('openReviewDialog', () => {})

const router = useRouter()
// 跳转回附注模块（披露表 → 附注为单向推送；此处仅导航，方便相互编辑确认）
function jumpToNote(target: DisclosureVariant): void {
  const route = buildNoteJumpRoute(props.projectId || '', 'I2', target)
  if (!route) { ElMessage.warning('未找到对应的附注章节'); return }
  router.push(route)
}

const isSyncing = ref(false)
const autoSync = useDisclosureAutoSync({ isReadonly: () => props.isReadonly })
const allResponsesRef = toRef(props, 'allResponses')
const standardsRef = toRef(props, 'applicableStandards')

const disc = useI2Disclosure(allResponsesRef, {
  variant: 'soe',
  saveResponse: props.saveResponse,
  applicableStandards: standardsRef,
})

const {
  movementRows, noteText, auditNote, auditConclusion,
  movementSummary, noteTarget,
  addMovementRow, onMovementChange, autoFillFromSources, getSoeSnapshot, persistAll,
} = disc

function handleAutoFill() {
  const r = autoFillFromSources() as { ok: boolean; message: string; unmatched?: string[] }
  if (!r.ok) {
    ElMessage.info(r.message)
    return
  }
  if (r.unmatched?.length) ElMessage.warning(r.message)
  else ElMessage.success(r.message)
}

async function handleSave() {
  await persistAll()
  emit('save')
  ElMessage.success('附注披露（国企）已保存')
}

async function syncToNotes() {
  if (isSyncing.value || props.isReadonly || !props.projectId) return
  await persistAll()
  const payloads = buildI2SoeSyncPayloads(props.wpId, props.applicableStandards, getSoeSnapshot())
  if (!payloads.length) {
    ElMessage.warning('当前不适用国企附注同步')
    return
  }
  isSyncing.value = true
  try {
    let rows = 0
    for (const payload of payloads) {
      const result: any = await api.post(
        `/api/projects/${props.projectId}/disclosure-notes/sync-from-workpaper`,
        payload,
      )
      const data = result?.data ?? result
      rows += Number(data?.rows_synced ?? 0)
    }
    eventBus.emit('disclosure:note-text-updated' as any, {
      projectId: props.projectId,
      sectionIds: [noteTarget.value?.sectionId || '八、28'],
      wpId: props.wpId,
      sheet: '附注披露信息（国有企业）',
      wpCode: 'I2',
      variant: 'soe',
    })
    ElMessage.success(`已同步至附注 ${noteTarget.value?.sectionId || '八、28'}（${rows} 行）`)
  } catch (e: any) {
    ElMessage.error(e?.message || '同步失败')
  } finally {
    isSyncing.value = false
  }
}

watch(
  [
    () => disc.movementRows,
    () => disc.noteText,
    () => disc.auditNote,
    () => disc.auditConclusion,
  ],
  () => autoSync.scheduleAutoSync(syncToNotes),
  { deep: true },
)

function handleReview() { openReviewDialog('I2-附注披露-国企') }

function fmtNum(v: number): string {
  if (v == null || Number.isNaN(v)) return '—'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function summaryMethod({ columns }: { columns: { label?: string }[] }) {
  const s = movementSummary.value
  return columns.map((col, i) => {
    if (i === 0) return '合计'
    const l = col.label || ''
    if (l.includes('期初')) return fmtNum(s.begin)
    if (l.includes('内部')) return fmtNum(s.increaseInternal)
    if (l === '其他' && columns.filter((c) => (c.label || '') === '其他').length) {
      // ambiguous — leave blank for nested headers; totals bar covers
      return ''
    }
    if (l.includes('无形')) return fmtNum(s.decreaseToIntangible)
    if (l.includes('损益')) return fmtNum(s.decreaseToExpense)
    if (l.includes('期末')) return fmtNum(s.end)
    return ''
  })
}

onBeforeUnmount(() => autoSync.cancelPending())
</script>

<style scoped>
.i2-disclosure-soe { font-size: var(--wp-font-size, 13px); padding: 16px; }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; gap: 8px; flex-wrap: wrap; }
.section-title { font-size: 15px; font-weight: 600; color: #1f2937; }
.section-actions { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.objective-alert { margin-bottom: 10px; }
.methodology-context {
  background: #fffbeb; border-left: 4px solid #f59e0b; padding: 10px 14px;
  margin-bottom: 12px; border-radius: 4px; font-size: 12px; color: #92400e; line-height: 1.6;
}
.tab-toolbar { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; margin-bottom: 12px; }
.block-card { margin-bottom: 14px; }
.block-title { display: flex; justify-content: space-between; align-items: center; }
.hint-blue { font-size: 12px; color: #1d4ed8; margin: 8px 0 0; }
.formula-cell { color: #6366f1; font-weight: 500; border-bottom: 1px dashed #a5b4fc; }
.mt8 { margin-top: 8px; }
.audit-card { margin-top: 12px; }
</style>
