<template>
  <div class="i2-disclosure-listed" data-testid="i2-disclosure-listed">
    <div class="section-header">
      <span class="section-title">开发支出附注披露表（上市公司）</span>
      <div class="section-actions">
        <GtIndexChip v-if="noteTarget" :value="noteTarget.chipValue" :context-project-id="props.projectId" />
        <el-button size="small" type="info" plain :disabled="isReadonly" data-testid="i2-listed-autofill" @click="handleAutoFill">
          从 I2-2/I2-6/I2-7 取数
        </el-button>
        <el-button
          size="small"
          type="primary"
          plain
          :loading="isSyncing"
          :disabled="isReadonly || !props.projectId"
          data-testid="i2-listed-sync-notes"
          @click="syncToNotes"
        >同步到附注</el-button>
        <el-button size="small" type="primary" plain :disabled="!projectId" @click="jumpToNote('listed')">↩ 跳转回附注</el-button>
        <el-button size="small" type="success" :disabled="isReadonly" @click="handleSave">保存</el-button>
        <el-button size="small" type="default" text @click="handleReview">复核</el-button>
      </div>
    </div>

    <el-alert type="info" :closable="false" show-icon class="objective-alert">
      <template #title>编制目标</template>
      按 15 号文披露研发投入（费用化/资本化）及开发支出项目滚动；重要资本化项目须说明时点、依据与进度；减值准备分项列示。同步目标附注「{{ noteTarget?.sectionId || '五、27' }}」。
    </el-alert>

    <div class="methodology-context">
      <p>
        <b>联动逻辑：</b>费用化金额 ↔ I6 研发费用；资本化金额 ↔ 开发支出（I2）。
        项目滚动从 I2-2 取数，资本化时点/依据/进度从 I2-6 补齐（避免源表 #REF!）。
        性质表资本化列可由 I2-7 本期增加费用性质粗映射。点「同步到附注」写入附注模块。
      </p>
    </div>

    <div class="tab-toolbar">
      <el-tag size="small" type="info">项目 {{ movementRows.length }}</el-tag>
      <el-tag size="small">本期资本化(性质) {{ fmtNum(natureSummary.currentCapitalized) }}</el-tag>
      <el-tag size="small">内部开发增加 {{ fmtNum(movementSummary.increaseInternal) }}</el-tag>
      <el-tag
        v-if="natureVsMovementDiff != null && Math.abs(natureVsMovementDiff) > 0.005"
        size="small"
        type="warning"
      >性质资本化≠滚动内部开发 {{ fmtNum(natureVsMovementDiff) }}</el-tag>
      <el-button size="small" @click="emit('navigate-sheet', 'I2-2')">← I2-2</el-button>
      <el-button size="small" @click="emit('navigate-sheet', 'I2-6')">I2-6</el-button>
      <el-button size="small" @click="emit('navigate-sheet', '附注国企')">国企版 →</el-button>
    </div>

    <!-- ① 按性质 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="block-title">
          <span>① 研发投入按性质（本期/上期 × 费用化/资本化）</span>
          <el-button size="small" plain :disabled="isReadonly" @click="handleAddNatureRow">+ 费用性质</el-button>
        </div>
      </template>
      <p class="hint">应披露本期及上期发生额，并分别列示费用化金额和资本化金额（15号文第二十六条）。</p>
      <p class="hint">源模板固定 6 类（人工费/材料费/水电燃气费/折旧费/无形资产摊销/外购在研项目）不可删；「+ 费用性质」对应源表可扩位，需先命名。</p>
      <el-table :data="natureRows" border size="small" max-height="320" show-summary :summary-method="natureSummaryMethod">
        <el-table-column type="index" width="40" />
        <el-table-column label="项  目" min-width="140">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.name" size="small" />
            <span v-else>{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期发生额" align="center">
          <el-table-column label="费用化金额" width="120" align="right">
            <template #default="{ row }">
              <WpAmountInput v-if="!isReadonly" v-model="row.currentExpensed" :disabled="isReadonly" />
              <span v-else>{{ fmtNum(row.currentExpensed) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="资本化金额" width="120" align="right">
            <template #default="{ row }">
              <WpAmountInput v-if="!isReadonly" v-model="row.currentCapitalized" :disabled="isReadonly" />
              <span v-else>{{ fmtNum(row.currentCapitalized) }}</span>
            </template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="上期发生额" align="center">
          <el-table-column label="费用化金额" width="120" align="right">
            <template #default="{ row }">
              <WpAmountInput v-if="!isReadonly" v-model="row.priorExpensed" :disabled="isReadonly" />
              <span v-else>{{ fmtNum(row.priorExpensed) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="资本化金额" width="120" align="right">
            <template #default="{ row }">
              <WpAmountInput v-if="!isReadonly" v-model="row.priorCapitalized" :disabled="isReadonly" />
              <span v-else>{{ fmtNum(row.priorCapitalized) }}</span>
            </template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="操作" width="64" align="center">
          <template #default="{ row }">
            <el-button
              v-if="!isReadonly && !isI2NatureDefaultRow(row)"
              size="small"
              type="danger"
              link
              @click="handleRemoveNatureRow(row)"
            >删</el-button>
            <span v-else class="muted">—</span>
          </template>
        </el-table-column>
      </el-table>
      <p class="hint-blue">费用化应对应「研发费用」；资本化应对应「开发支出」。</p>
    </el-card>

    <!-- ② 项目滚动 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="block-title">
          <span>② 开发支出项目滚动</span>
          <el-button size="small" plain :disabled="isReadonly" @click="addMovementRow">+ 项目</el-button>
        </div>
      </template>
      <el-table :data="movementRows" border size="small" max-height="400" show-summary :summary-method="movementSummaryMethod">
        <el-table-column type="index" width="40" fixed />
        <el-table-column label="项目" min-width="130" fixed>
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.name" size="small" />
            <span v-else>{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期初数" width="110" align="right">
          <template #default="{ row }">
            <WpAmountInput v-if="!isReadonly" v-model="row.beginBalance" :disabled="isReadonly" @change="onMovementChange(row)" />
            <span v-else>{{ fmtNum(row.beginBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期增加" align="center">
          <el-table-column label="内部开发" width="110" align="right">
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
          <el-table-column label="转无形资产" width="110" align="right">
            <template #default="{ row }">
              <WpAmountInput v-if="!isReadonly" v-model="row.decreaseToIntangible" :disabled="isReadonly" @change="onMovementChange(row)" />
              <span v-else>{{ fmtNum(row.decreaseToIntangible) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="计入损益" width="110" align="right">
            <template #default="{ row }">
              <WpAmountInput v-if="!isReadonly" v-model="row.decreaseToExpense" :disabled="isReadonly" @change="onMovementChange(row)" />
              <span v-else>{{ fmtNum(row.decreaseToExpense) }}</span>
            </template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="期末数" width="110" align="right">
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
    </el-card>

    <!-- ③ 重要资本化 -->
    <el-card shadow="never" class="block-card green-block">
      <template #header>
        <div class="block-title">
          <span>（1）重要的资本化研发项目</span>
          <el-button size="small" plain :disabled="isReadonly" @click="addImportantRow">+ 行</el-button>
        </div>
      </template>
      <el-table :data="importantRows" border size="small" max-height="280">
        <el-table-column type="index" width="40" />
        <el-table-column label="项目" min-width="120">
          <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.name" size="small" /><span v-else>{{ row.name }}</span></template>
        </el-table-column>
        <el-table-column label="研发进度" min-width="100">
          <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.progress" size="small" /><span v-else>{{ row.progress }}</span></template>
        </el-table-column>
        <el-table-column label="预计完成时间" min-width="120">
          <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.expectedCompletion" size="small" /><span v-else>{{ row.expectedCompletion }}</span></template>
        </el-table-column>
        <el-table-column label="经济利益产生方式" min-width="140">
          <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.economicBenefit" size="small" /><span v-else>{{ row.economicBenefit }}</span></template>
        </el-table-column>
        <el-table-column label="开始资本化时点" min-width="120">
          <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.capStartDate" size="small" /><span v-else>{{ row.capStartDate }}</span></template>
        </el-table-column>
        <el-table-column label="资本化具体依据" min-width="140">
          <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.capBasis" size="small" /><span v-else>{{ row.capBasis }}</span></template>
        </el-table-column>
      </el-table>
      <el-input
        class="mt8"
        type="textarea"
        :model-value="noteCap"
        :disabled="isReadonly"
        :autosize="{ minRows: 2 }"
        placeholder="重要资本化项目文字说明…"
        @change="(v: string) => (noteCap = v)"
      />
    </el-card>

    <!-- ④ 减值 -->
    <el-card shadow="never" class="block-card green-block">
      <template #header>
        <div class="block-title">
          <span>（2）开发支出减值准备</span>
          <el-button size="small" plain :disabled="isReadonly" @click="addImpairmentRow">+ 行</el-button>
        </div>
      </template>
      <el-table :data="impairmentRows" border size="small" max-height="240">
        <el-table-column type="index" width="40" />
        <el-table-column label="项目" min-width="140">
          <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.name" size="small" /><span v-else>{{ row.name }}</span></template>
        </el-table-column>
        <el-table-column label="期初余额" width="110" align="right">
          <template #default="{ row }">
            <WpAmountInput v-if="!isReadonly" v-model="row.beginBalance" :disabled="isReadonly" />
            <span v-else>{{ fmtNum(row.beginBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期计提" width="110" align="right">
          <template #default="{ row }">
            <WpAmountInput v-if="!isReadonly" v-model="row.provision" :disabled="isReadonly" />
            <span v-else>{{ fmtNum(row.provision) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期减少" width="110" align="right">
          <template #default="{ row }">
            <WpAmountInput v-if="!isReadonly" v-model="row.decrease" :disabled="isReadonly" />
            <span v-else>{{ fmtNum(row.decrease) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" width="110" align="right">
          <template #default="{ row }">
            <span class="formula-cell">{{ fmtNum(row.beginBalance + row.provision - row.decrease) }}</span>
          </template>
        </el-table-column>
      </el-table>
      <el-input
        class="mt8"
        type="textarea"
        :model-value="noteImpairTest"
        :disabled="isReadonly"
        :autosize="{ minRows: 2 }"
        placeholder="说明减值测试情况…"
        @change="(v: string) => (noteImpairTest = v)"
      />
    </el-card>

    <el-card shadow="never" class="block-card">
      <template #header><span>外购在研项目 / 附注文字</span></template>
      <el-input
        type="textarea"
        :model-value="notePurchased"
        :disabled="isReadonly"
        :autosize="{ minRows: 2 }"
        placeholder="外购在研项目资本化或费用化的判断依据（15号文第二十八条）…"
        @change="(v: string) => (notePurchased = v)"
      />
      <el-input
        class="mt8"
        type="textarea"
        :model-value="noteText"
        :disabled="isReadonly"
        :autosize="{ minRows: 3 }"
        placeholder="其他附注文字说明…"
        @change="(v: string) => (noteText = v)"
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
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRouter } from 'vue-router'
import { buildNoteJumpRoute, type DisclosureVariant } from '@/views/composables/noteDisclosureReverseJump'
import GtIndexChip from '../../GtIndexChip.vue'
import { useI2Disclosure } from '../../composables/useI2Disclosure'
import { isI2NatureDefaultRow, type I2NatureRow } from '../../composables/i2DisclosureModel'
import { buildI2ListedSyncPayloads } from '../../composables/i2DisclosureSyncPayload'
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
  variant: 'listed',
  saveResponse: props.saveResponse,
  applicableStandards: standardsRef,
})

const {
  natureRows, movementRows, importantRows, impairmentRows,
  noteText, noteCap, noteImpairTest, notePurchased,
  auditNote, auditConclusion,
  natureSummary, movementSummary, natureVsMovementDiff, noteTarget,
  addNatureRow, removeNatureRow, addMovementRow, addImportantRow, addImpairmentRow,
  onMovementChange, autoFillFromSources, getListedSnapshot, persistAll,
} = disc

/**
 * 增行前必先命名（平台底稿交互铁律：动态行新增需命名的必须先 prompt）。
 * 对齐源模板 `附注披露（上市公司）!A15 = ……` 唯一可扩位；撞名由
 * `addI2NatureRow` 纯函数判定并返回 false，此处只负责提示。
 */
async function handleAddNatureRow(): Promise<void> {
  if (props.isReadonly) return
  let name = ''
  try {
    const { value } = await ElMessageBox.prompt('请输入费用性质名称', '新增费用性质', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputPlaceholder: '如：委外研发费、专利申请费',
      inputValidator: (v: string) => (String(v ?? '').trim() ? true : '名称不能为空'),
    })
    name = String(value ?? '').trim()
  } catch {
    return // 用户取消
  }
  if (!addNatureRow(name)) {
    ElMessage.warning(`「${name}」与源模板固定类别或已有行重名，请换一个名称`)
    return
  }
  ElMessage.success(`已新增费用性质「${name}」`)
}

async function handleRemoveNatureRow(row: I2NatureRow): Promise<void> {
  if (props.isReadonly) return
  if (isI2NatureDefaultRow(row)) {
    ElMessage.warning('源模板固定的 6 类费用性质不可删除')
    return
  }
  if (!removeNatureRow(row.rowId)) {
    ElMessage.warning('该行不可删除')
    return
  }
  ElMessage.success('已删除')
}

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
  ElMessage.success('附注披露（上市公司）已保存')
}

async function syncToNotes() {
  if (isSyncing.value || props.isReadonly || !props.projectId) return
  await persistAll()
  const payloads = buildI2ListedSyncPayloads(props.wpId, props.applicableStandards, getListedSnapshot())
  if (!payloads.length) {
    ElMessage.warning('当前不适用上市附注同步')
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
      sectionIds: [noteTarget.value?.sectionId || '五、27'],
      wpId: props.wpId,
      sheet: '附注披露信息（上市公司）',
      wpCode: 'I2',
      variant: 'listed',
    })
    ElMessage.success(`已同步至附注 ${noteTarget.value?.sectionId || '五、27'}（${rows} 行）`)
  } catch (e: any) {
    ElMessage.error(e?.message || '同步失败')
  } finally {
    isSyncing.value = false
  }
}

watch(
  [
    () => disc.natureRows,
    () => disc.movementRows,
    () => disc.importantRows,
    () => disc.impairmentRows,
    () => disc.noteText,
    () => disc.noteCap,
    () => disc.noteImpairTest,
    () => disc.notePurchased,
    () => disc.auditNote,
    () => disc.auditConclusion,
  ],
  () => autoSync.scheduleAutoSync(syncToNotes),
  { deep: true },
)

function handleReview() { openReviewDialog('I2-附注披露-上市') }

function fmtNum(v: number): string {
  if (v == null || Number.isNaN(v)) return '—'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function natureSummaryMethod({ columns }: { columns: { label?: string }[] }) {
  const s = natureSummary.value
  // 🔴 两级表头下四个金额列的叶子 label 重复（「费用化金额」「资本化金额」各出现两次），
  // 无法按 label 唯一匹配 ⇒ 按出现次序取值（源模板列序：本期费用化/本期资本化/上期费用化/上期资本化）。
  const ordered = [s.currentExpensed, s.currentCapitalized, s.priorExpensed, s.priorCapitalized]
  let seen = 0
  return columns.map((col, i) => {
    if (i === 0) return '合计'
    const l = col.label || ''
    if (l === '费用化金额' || l === '资本化金额') {
      const v = ordered[seen]
      seen += 1
      return v == null ? '' : fmtNum(v)
    }
    return ''
  })
}

function movementSummaryMethod({ columns }: { columns: { label?: string }[] }) {
  const s = movementSummary.value
  return columns.map((col, i) => {
    if (i === 0) return '合计'
    const l = col.label || ''
    if (l === '期初数') return fmtNum(s.begin)
    if (l.includes('内部')) return fmtNum(s.increaseInternal)
    if (l === '其他' && columns.some((c) => (c.label || '').includes('内部'))) return fmtNum(s.increaseOther)
    if (l.includes('无形')) return fmtNum(s.decreaseToIntangible)
    if (l.includes('损益')) return fmtNum(s.decreaseToExpense)
    if (l === '期末数') return fmtNum(s.end)
    return ''
  })
}

onBeforeUnmount(() => autoSync.cancelPending())
</script>

<style scoped>
.i2-disclosure-listed { font-size: var(--wp-font-size, 13px); padding: 16px; }
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
.green-block { background: #f0fdf4; }
.block-title { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.hint { font-size: 12px; color: #64748b; margin: 0 0 8px; }
.hint-blue { font-size: 12px; color: #1d4ed8; margin: 8px 0 0; }
.muted { color: #cbd5e1; }
.formula-cell { color: #6366f1; font-weight: 500; border-bottom: 1px dashed #a5b4fc; }
.mt8 { margin-top: 8px; }
.audit-card { margin-top: 12px; }
</style>
