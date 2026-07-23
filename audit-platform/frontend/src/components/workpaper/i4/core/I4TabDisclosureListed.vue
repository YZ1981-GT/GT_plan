<template>
  <div class="i4-tab-disclosure-listed">
    <el-alert
      type="info"
      :closable="false"
      class="objective-alert"
      title="审计目标：核实长期待摊费用附注披露（上市公司）完整准确——账面余额滚动与 I4-2/I4-1 勾稽，并同步至附注五、29。"
    />

    <div class="guide-area">
      <div class="guide-grid">
        <div class="guide-step"><span class="step-num">①</span> 从 I4-2 按类别聚合期初/增加/摊销/其他减少</div>
        <div class="guide-step"><span class="step-num">②</span> 期末 = 期初 + 增加 − 摊销 − 其他减少（摊销直接冲减账面）</div>
        <div class="guide-step"><span class="step-num">③</span> 填写一年内到期信息性金额与说明（不重分类流动资产）</div>
        <div class="guide-step"><span class="step-num">④</span> 「同步到附注」写入附注模块 §五、29</div>
      </div>
    </div>

    <div class="methodology-block">
      <div class="methodology-title">编制要点（上市公司）</div>
      <div class="methodology-content">
        长期待摊费用无单独累计摊销备抵，附注为账面余额滚动表。同步时「本期减少」= 本期摊销 + 其他减少。
        准则提示：摊销期限不足一年的部分仍在本项目列报，不转入「一年内到期的非流动资产」。
      </div>
    </div>

    <div class="toolbar-row">
      <el-button size="small" type="primary" plain :disabled="isReadonly" @click="disc.syncFromDetail(false)">
        从 I4-2 同步
      </el-button>
      <el-button size="small" :disabled="isReadonly" @click="disc.syncFromDetail(true)">强制覆盖同步</el-button>
      <el-button size="small" type="success" :loading="disc.isSyncing.value" :disabled="isReadonly" @click="disc.syncToNotes()">
        同步到附注 {{ disc.noteTarget.value.sectionId }}
      </el-button>
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
          <span>长期待摊费用变动表</span>
          <span class="hint">期末自动计算</span>
        </div>
      </template>

      <el-table :data="disc.rows.value" border stripe size="small" show-summary :summary-method="getSummary">
        <el-table-column type="index" label="#" width="40" />
        <el-table-column prop="item" label="项目" min-width="160">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.item"
              size="small"
              placeholder="如：使用权资产改良及维护支出"
              @update:model-value="(v: string) => disc.updateCell(row.rowId, 'item', v)"
            />
            <span v-else>{{ row.item }}</span>
            <el-tag v-if="row.isAutoFilled" size="small" type="info" class="auto-badge">自动</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="期初数" width="120" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.beginBalance"
              :controls="false"
              size="small"
              :precision="2"
              @change="(v: number) => disc.updateCell(row.rowId, 'beginBalance', v ?? 0)"
            />
            <span v-else class="amt">{{ fmtAmt(row.beginBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期增加" width="120" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.increase"
              :controls="false"
              size="small"
              :precision="2"
              @change="(v: number) => disc.updateCell(row.rowId, 'increase', v ?? 0)"
            />
            <span v-else class="amt">{{ fmtAmt(row.increase) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期减少">
          <el-table-column label="本期摊销" width="110" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="!isReadonly"
                :model-value="row.amortization"
                :controls="false"
                size="small"
                :precision="2"
                @change="(v: number) => disc.updateCell(row.rowId, 'amortization', v ?? 0)"
              />
              <span v-else class="amt">{{ fmtAmt(row.amortization) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="其他减少" width="110" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="!isReadonly"
                :model-value="row.otherDecrease"
                :controls="false"
                size="small"
                :precision="2"
                @change="(v: number) => disc.updateCell(row.rowId, 'otherDecrease', v ?? 0)"
              />
              <span v-else class="amt">{{ fmtAmt(row.otherDecrease) }}</span>
            </template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="期末数" width="120" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="= 期初 + 增加 − 摊销 − 其他减少">{{ fmtAmt(row.endBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="操作" width="56" align="center">
          <template #default="{ row }">
            <el-button type="danger" link size="small" @click="disc.removeRow(row.rowId)">删</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card shadow="never" class="disc-card footnote-card">
      <template #header><div class="card-header"><span>一年内到期说明（信息性）</span></div></template>
      <div class="portion-row">
        <span>1年内到期的长期待摊费用</span>
        <el-input-number
          v-if="!isReadonly"
          :model-value="disc.currentPortion.value"
          :controls="false"
          size="small"
          :precision="2"
          @change="(v: number) => disc.saveCurrentPortion(v ?? 0)"
        />
        <b v-else>{{ fmtAmt(disc.currentPortion.value) }}</b>
        <span>元（仍列报于本项目，详见附注提示）</span>
      </div>
      <p class="footnote-text">{{ disc.footnote.value }}</p>
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
        placeholder="主要构成、摊销方法、重大变动说明…"
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
        placeholder="披露与明细/审定勾稽情况、一年内到期信息披露…"
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
        placeholder="A、附注披露完整准确，已同步五、29。B、除下列事项外未见异常。C、存在重大披露差异，不可确认。"
        @change="disc.saveAuditConclusion"
      />
    </el-card>

    <details class="compile-hint" open>
      <summary>编制说明</summary>
      <ol>
        <li>本表对齐源底稿「附注披露（上市公司）」：项目滚动，非原值+累计摊销双矩阵。</li>
        <li>数据优先自 I4-2 按费用类型/资产类型聚合；手工修改后取消「自动」标记，强制覆盖可重刷。</li>
        <li>同步附注时写入 note_template §五、29「长期待摊费用」子表；本期减少=摊销+其他减少。</li>
        <li>一年内到期金额为信息性披露，不改变列报分类。</li>
      </ol>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * I4TabDisclosureListed — 附注披露（上市公司）
 * 对齐源表 + 同步附注五、29
 */
import { computed, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
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

const variant = ref<'listed'>('listed')
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
    if (col.label === '期初数') return fmtAmt(t.beginBalance)
    if (col.label === '本期增加') return fmtAmt(t.increase)
    if (col.label === '本期摊销') return fmtAmt(t.amortization)
    if (col.label === '其他减少') return fmtAmt(t.otherDecrease)
    if (col.label === '期末数') return fmtAmt(t.endBalance)
    return ''
  })
}

function fmtAmt(val: number | null | undefined): string {
  if (val == null || Math.abs(val) < 1e-9) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.i4-tab-disclosure-listed { padding: 16px; font-size: var(--wp-font-size, 13px); }
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
.portion-row { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin-bottom: 8px; }
.footnote-text { margin: 0; font-size: 12px; color: #6b21a8; line-height: 1.6; }
.compile-hint { font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; color: var(--el-text-color-primary); }
.compile-hint ol { padding-left: 20px; margin: 8px 0 0; }
.compile-hint li { margin-bottom: 4px; line-height: 1.5; }
</style>
