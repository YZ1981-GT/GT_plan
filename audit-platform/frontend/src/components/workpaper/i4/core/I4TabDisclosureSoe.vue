<template>
  <div class="i4-tab-disclosure-soe">
    <el-alert
      type="info"
      :closable="false"
      class="objective-alert"
      title="审计目标：核实长期待摊费用附注披露（国有企业）完整准确——账面余额滚动与 I4-2/I4-1 勾稽，并同步至附注八、30。"
    />

    <div class="guide-area">
      <div class="guide-grid">
        <div class="guide-step"><span class="step-num">①</span> 从 I4-2 按类别聚合期初/增加/摊销/其他减少</div>
        <div class="guide-step"><span class="step-num">②</span> 期末 = 期初 + 增加 − 摊销 − 其他减少</div>
        <div class="guide-step"><span class="step-num">③</span> 其他减少须填写原因（国企格式特有列）</div>
        <div class="guide-step"><span class="step-num">④</span> 「同步到附注」写入附注模块 §八、30</div>
      </div>
    </div>

    <div class="methodology-block">
      <div class="methodology-title">编制要点（国有企业）</div>
      <div class="methodology-content">
        国企附注分列「本期摊销额」「其他减少额」，并要求披露其他减少原因。
        摊销直接冲减账面余额，不做原值/累计摊销双层披露。
      </div>
    </div>

    <div class="toolbar-row">
      <el-button size="small" type="primary" plain :disabled="isReadonly" @click="disc.syncFromDetail(false)">
        从 I4-2 同步
      </el-button>
      <el-button size="small" :disabled="isReadonly" @click="disc.syncFromDetail(true)">强制覆盖同步</el-button>
      <el-button size="small" type="success" :loading="disc.isSyncing.value" :disabled="isReadonly" @click="syncToDisclosureNotes()">
        同步到附注 {{ disc.noteTarget.value.sectionId }}
      </el-button>
      <el-button size="small" type="primary" plain :disabled="!projectId" @click="jumpToNote('soe')">↩ 跳转回附注</el-button>
      <el-button size="small" type="primary" :disabled="isReadonly" @click="handleAdd">+ 新增项目</el-button>
      <el-tag size="small" type="info">目标章节 {{ disc.noteTarget.value.chipValue }}</el-tag>
      <span v-if="disc.reconcileDiff.value != null" class="reconcile">
        与明细期末差
        <b :class="{ 'text-danger': Math.abs(disc.reconcileDiff.value) > 0.01 }">{{ fmtAmt(disc.reconcileDiff.value) }}</b>
      </span>
      <span v-if="disc.reconcileVsAdj.value != null" class="reconcile">
        与审定合计差
        <b :class="{ 'text-danger': Math.abs(disc.reconcileVsAdj.value) > 0.01 }">{{ fmtAmt(disc.reconcileVsAdj.value) }}</b>
      </span>
    </div>

    <el-card shadow="never" class="disc-card">
      <template #header>
        <div class="card-header">
          <span>长期待摊费用附注披露（国有企业）</span>
          <span class="hint">期末自动计算</span>
        </div>
      </template>

      <el-table :data="disc.rows.value" border stripe size="small" show-summary :summary-method="getSummary">
        <el-table-column type="index" label="#" width="40" />
        <el-table-column prop="item" label="项目" min-width="150">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.item"
              size="small"
              placeholder="如：使用权资产改良及维护"
              @update:model-value="(v: string) => disc.updateCell(row.rowId, 'item', v)"
            />
            <span v-else>{{ row.item }}</span>
            <el-tag v-if="row.isAutoFilled" size="small" type="info" class="auto-badge">自动</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="期初余额" width="110" align="right">
          <template #default="{ row }">
            <WpAmountInput
              v-if="!isReadonly"
              v-model="row.beginBalance"
              size="small"
              :disabled="isReadonly"
              @change="(v: number) => disc.updateCell(row.rowId, 'beginBalance', v)"
            />
            <span v-else class="amt">{{ fmtAmt(row.beginBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期增加额" width="110" align="right">
          <template #default="{ row }">
            <WpAmountInput
              v-if="!isReadonly"
              v-model="row.increase"
              size="small"
              :disabled="isReadonly"
              @change="(v: number) => disc.updateCell(row.rowId, 'increase', v)"
            />
            <span v-else class="amt">{{ fmtAmt(row.increase) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期摊销额" width="110" align="right">
          <template #default="{ row }">
            <WpAmountInput
              v-if="!isReadonly"
              v-model="row.amortization"
              size="small"
              :disabled="isReadonly"
              @change="(v: number) => disc.updateCell(row.rowId, 'amortization', v)"
            />
            <span v-else class="amt">{{ fmtAmt(row.amortization) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="其他减少额" width="110" align="right">
          <template #default="{ row }">
            <WpAmountInput
              v-if="!isReadonly"
              v-model="row.otherDecrease"
              size="small"
              :disabled="isReadonly"
              @change="(v: number) => disc.updateCell(row.rowId, 'otherDecrease', v)"
            />
            <span v-else class="amt">{{ fmtAmt(row.otherDecrease) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" width="110" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="= 期初 + 增加 − 摊销 − 其他减少">{{ fmtAmt(row.endBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="其他减少的原因" min-width="140">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.otherDecreaseReason"
              size="small"
              :placeholder="row.otherDecrease ? '必填原因' : '无则空'"
              @update:model-value="(v: string) => disc.updateCell(row.rowId, 'otherDecreaseReason', v)"
            />
            <span v-else>{{ row.otherDecreaseReason || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="操作" width="56" align="center">
          <template #default="{ row }">
            <el-button type="danger" link size="small" @click="disc.removeRow(row.rowId)">删</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card shadow="never" class="disc-card">
      <template #header>
        <div class="card-header">
          <span>其他说明</span>
          <el-button
            size="small"
            type="primary"
            link
            :loading="disc.isAiGenerating.value"
            :disabled="isReadonly"
            @click="handleAi"
          >AI生成</el-button>
        </div>
      </template>
      <el-input
        type="textarea"
        :model-value="disc.otherNote.value"
        :disabled="isReadonly"
        :autosize="{ minRows: 3 }"
        placeholder="摊销政策、受益期间、重大变动等…"
        @change="disc.saveOtherNote"
      />
    </el-card>

    <el-card shadow="never" class="disc-card">
      <template #header><div class="card-header"><span>审计说明</span></div></template>
      <el-input
        type="textarea"
        :model-value="disc.auditNote.value"
        :disabled="isReadonly"
        :autosize="{ minRows: 3 }"
        placeholder="披露与明细/审定勾稽、其他减少原因核查…"
        @change="disc.saveAuditNote"
      />
    </el-card>

    <el-card shadow="never" class="disc-card">
      <template #header><div class="card-header"><span>审计结论</span></div></template>
      <el-input
        type="textarea"
        :model-value="disc.auditConclusion.value"
        :disabled="isReadonly"
        :autosize="{ minRows: 2 }"
        placeholder="A、附注披露完整准确，已同步八、30。B、除下列事项外未见异常。C、存在重大披露差异，不可确认。"
        @change="disc.saveAuditConclusion"
      />
    </el-card>

    <details class="compile-hint" open>
      <summary>编制说明</summary>
      <ol>
        <li>本表对齐源底稿「附注披露（国有企业）」：分列摊销额与其他减少额，并披露减少原因。</li>
        <li>数据优先自 I4-2 聚合；同步写入 note_template §八、30「长期待摊费用」子表。</li>
        <li>其他减少额非零时，原因列应填写（处置、转销、重分类等）。</li>
      </ol>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * I4TabDisclosureSoe — 附注披露（国有企业）
 * 对齐源表 + 同步附注八、30
 */
import { computed, ref, onBeforeUnmount, watch } from 'vue'
import { useDisclosureAutoSync } from '../../composables/useDisclosureAutoSync'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRouter } from 'vue-router'
import { buildNoteJumpRoute, type DisclosureVariant } from '@/views/composables/noteDisclosureReverseJump'
import { useI4Disclosure } from '../../composables/useI4Disclosure'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
  applicableStandards?: string[]
}>()

const emit = defineEmits<{
  'navigate-sheet': [sheetName: string]
  'save': [itemId: string, value: any]
}>()

const router = useRouter()
// 跳转回附注模块（披露表 → 附注为单向推送；此处仅导航，方便相互编辑确认）
function jumpToNote(target: DisclosureVariant): void {
  const route = buildNoteJumpRoute(props.projectId || '', 'I4', target)
  if (!route) { ElMessage.warning('未找到对应的附注章节'); return }
  router.push(route)
}

const variant = ref<'soe'>('soe')
const disc = useI4Disclosure(
  computed(() => props.wpId),
  computed(() => props.projectId),
  computed(() => props.allResponses),
  {
    variant,
    applicableStandards: () => props.applicableStandards,
    onSave: (itemId, value) => emit('save', itemId, typeof value === 'string' ? value : JSON.stringify(value)),
  },
)

async function handleAdd(): Promise<void> {
  try {
    const { value } = await ElMessageBox.prompt('请输入披露项目名称', '新增项目', {
      inputPattern: /\S+/,
      inputErrorMessage: '名称不能为空',
    })
    disc.addRow(value)
  } catch { /* cancel */ }
}

async function handleAi(): Promise<void> {
  const text = await disc.generateNoteText()
  if (text) {
    disc.saveOtherNote(text)
    ElMessage.success('已生成其他说明')
  }
}

function getSummary({ columns }: { columns: any[] }): string[] {
  const t = disc.totals.value
  return columns.map((col: any, i: number) => {
    if (i === 0) return '合计'
    if (col.label === '期初余额') return fmtAmt(t.beginBalance)
    if (col.label === '本期增加额') return fmtAmt(t.increase)
    if (col.label === '本期摊销额') return fmtAmt(t.amortization)
    if (col.label === '其他减少额') return fmtAmt(t.otherDecrease)
    if (col.label === '期末余额') return fmtAmt(t.endBalance)
    return ''
  })
}

function fmtAmt(val: number | null | undefined): string {
  if (val == null || Math.abs(val) < 1e-9) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

const autoSync = useDisclosureAutoSync({ isReadonly: () => props.isReadonly })

async function syncToDisclosureNotes() {
  await disc.syncToNotes()
}

// [auto-sync] 监听实际数据（历史实现是 syncToDisclosureNotes 里调度自己 → 800ms 周期无限 POST，
// 且让 disclosureAutoSyncCoverage 守卫误判为「已接自动同步」= 假接入）。
// 🔴 不加 `_xxxMounted` 一次性防护：Vue watch 默认 immediate:false，挂载本身不触发；
//    该防护会吞掉「切走再切回后的第一次编辑」（平台铁律）。
watch(
  [
    () => disc.rows,
    () => disc.currentPortion,
    () => disc.footnote,
    () => disc.otherNote,
    () => disc.auditNote,
    () => disc.auditConclusion,
  ],
  () => autoSync.scheduleAutoSync(syncToDisclosureNotes),
  { deep: true },
)

onBeforeUnmount(() => autoSync.cancelPending())
</script>

<style scoped>
.i4-tab-disclosure-soe { padding: 16px; font-size: var(--wp-font-size, 13px); }
.objective-alert { margin-bottom: 12px; }
.guide-area {
  background: linear-gradient(135deg, #e8f4fd 0%, #d4ecfb 100%);
  border-radius: 8px; padding: 12px 16px; margin-bottom: 12px;
}
.guide-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.guide-step { display: flex; gap: 6px; font-size: 13px; }
.step-num { font-weight: 700; color: var(--el-color-primary); }
.methodology-block {
  border-left: 4px solid #d97706; background: #fffbeb;
  padding: 10px 14px; margin-bottom: 12px; border-radius: 4px;
  font-size: 12px; color: #92400e; line-height: 1.7;
}
.methodology-title { font-weight: 600; margin-bottom: 4px; }
.toolbar-row {
  display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: 12px;
}
.reconcile { margin-left: auto; font-size: 12px; color: var(--el-text-color-secondary); }
.disc-card { margin-bottom: 12px; }
.disc-card :deep(.el-card__header) { padding: 8px 16px; background: #fafafa; }
.card-header { display: flex; justify-content: space-between; align-items: center; font-weight: 500; }
.hint { font-size: 12px; color: var(--el-text-color-secondary); font-weight: 400; }
.formula-cell { border-bottom: 1px dashed var(--el-border-color); cursor: help; font-variant-numeric: tabular-nums; }
.amt { font-variant-numeric: tabular-nums; }
.auto-badge { margin-left: 6px; }
.text-danger { color: var(--el-color-danger); }
.compile-hint { font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; color: var(--el-text-color-primary); }
.compile-hint ol { padding-left: 20px; margin: 8px 0 0; }
.compile-hint li { margin-bottom: 4px; line-height: 1.5; }
</style>
