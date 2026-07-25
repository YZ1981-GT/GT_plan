<template>
  <div class="i5-tab-disclosure-soe">
    <el-alert
      type="info"
      :closable="false"
      class="objective-alert"
      title="审计目标：核实其他非流动资产附注披露（国有企业）完整准确——分类期末/年初余额与 I5-2/I5-1 勾稽，并同步至附注八、32。"
    />

    <div class="guide-area">
      <div class="guide-grid">
        <div class="guide-step"><span class="step-num">①</span> 从 I5-2 按分类聚合期末余额与年初余额</div>
        <div class="guide-step"><span class="step-num">②</span> 国企版为简化对比表（无减值分列）</div>
        <div class="guide-step"><span class="step-num">③</span> 不存在的项目请删除；可增补实际分类</div>
        <div class="guide-step"><span class="step-num">④</span> 「同步到附注」写入附注模块 §八、32</div>
      </div>
    </div>

    <div class="methodology-block">
      <div class="methodology-title">编制要点（国有企业）</div>
      <div class="methodology-content">
        对齐源底稿「其他非流动资产附注披露表（国有企业）」：项目 / 期末余额 / 年初余额。
        同步附注时写入 note_template「期末余额 / 期初余额」。
      </div>
    </div>

    <div class="toolbar-row">
      <el-button size="small" type="primary" plain :disabled="isReadonly" @click="disc.syncFromDetail(false)">
        从 I5-2 同步
      </el-button>
      <el-button size="small" :disabled="isReadonly" @click="disc.syncFromDetail(true)">强制覆盖同步</el-button>
      <el-button size="small" type="success" :loading="disc.isSyncing.value" :disabled="isReadonly" @click="disc.syncToNotes()">
        同步到附注 {{ disc.noteTarget.value.sectionId }}
      </el-button>
      <el-button size="small" type="primary" plain :disabled="!projectId" @click="jumpToNote('soe')">↩ 跳转回附注（八、32）</el-button>
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
          <span>其他非流动资产附注披露表（国有企业）</span>
          <span class="hint">根据实际情况列示；不存在的项目请删除</span>
        </div>
      </template>

      <el-table :data="disc.rows.value" border stripe size="small" show-summary :summary-method="getSummary">
        <el-table-column type="index" label="#" width="40" />
        <el-table-column prop="item" label="项目" min-width="180">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.item"
              size="small"
              placeholder="如：预付工程款"
              @update:model-value="(v: string) => disc.updateCell(row.rowId, 'item', v)"
            />
            <span v-else>{{ row.item }}</span>
            <el-tag v-if="row.isAutoFilled" size="small" type="info" class="auto-badge">自动</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" width="150" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.endBookValue"
              :controls="false"
              size="small"
              :precision="2"
              @change="(v: number) => disc.updateCell(row.rowId, 'endBookValue', v ?? 0)"
            />
            <span v-else class="amt">{{ fmtAmt(row.endBookValue) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="年初余额" width="150" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.priorBookValue"
              :controls="false"
              size="small"
              :precision="2"
              @change="(v: number) => disc.updateCell(row.rowId, 'priorBookValue', v ?? 0)"
            />
            <span v-else class="amt">{{ fmtAmt(row.priorBookValue) }}</span>
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
          <span>说明</span>
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
        placeholder="重大项目构成、变动原因等…"
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
        placeholder="披露与明细/审定勾稽情况…"
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
        placeholder="A、附注披露完整准确，已同步八、32。B、除下列事项外未见异常。C、存在重大披露差异，不可确认。"
        @change="disc.saveAuditConclusion"
      />
    </el-card>

    <details class="compile-hint" open>
      <summary>编制说明</summary>
      <ol>
        <li>本表对齐源底稿「附注披露（国有企业）」：项目 / 期末余额 / 年初余额。</li>
        <li>数据优先自 I5-2 聚合；同步附注写入 note_template §八、32。</li>
        <li>合计应与 I5-1 审定合计勾稽一致。</li>
      </ol>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * I5TabDisclosureSoe — 附注披露（国有企业）
 * 对齐源表 + 同步附注八、32
 */
import { computed, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRouter } from 'vue-router'
import { buildNoteJumpRoute, type DisclosureVariant } from '@/views/composables/noteDisclosureReverseJump'
import { useI5Disclosure } from '../../composables/useI5Disclosure'

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

const variant = ref<'soe'>('soe')
const disc = useI5Disclosure(
  computed(() => props.wpId),
  computed(() => props.projectId),
  computed(() => props.allResponses),
  {
    variant,
    applicableStandards: () => props.applicableStandards,
    onSave: (itemId, value) => emit('save', itemId, typeof value === 'string' ? value : JSON.stringify(value)),
  },
)

const router = useRouter()
// 跳转回附注模块（披露表 → 附注为单向推送；此处仅导航，方便相互编辑确认）
function jumpToNote(target: DisclosureVariant): void {
  const route = buildNoteJumpRoute(props.projectId, 'I5', target)
  if (!route) { ElMessage.warning('未找到对应的附注章节'); return }
  router.push(route)
}

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
    ElMessage.success('已生成说明')
  }
}

function getSummary({ columns }: { columns: any[] }): string[] {
  const t = disc.totals.value
  return columns.map((col: any, i: number) => {
    if (i === 0) return ''
    if (i === 1) return '合计'
    if (col.label === '期末余额') return fmtAmt(t.endBookValue)
    if (col.label === '年初余额') return fmtAmt(t.priorBookValue)
    return ''
  })
}

function fmtAmt(val: number | null | undefined): string {
  if (val == null || Math.abs(val) < 1e-9) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.i5-tab-disclosure-soe { padding: 16px; font-size: var(--wp-font-size, 13px); }
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
.card-header { display: flex; justify-content: space-between; align-items: center; font-weight: 500; gap: 8px; }
.hint { font-size: 12px; color: var(--el-text-color-secondary); font-weight: 400; }
.amt { font-variant-numeric: tabular-nums; }
.auto-badge { margin-left: 6px; }
.text-danger { color: var(--el-color-danger); }
.compile-hint { font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; color: var(--el-text-color-primary); }
.compile-hint ol { padding-left: 20px; margin: 8px 0 0; }
.compile-hint li { margin-bottom: 4px; line-height: 1.5; }
</style>
