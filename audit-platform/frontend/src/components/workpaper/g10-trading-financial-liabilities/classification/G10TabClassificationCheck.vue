<template>
  <div class="g10-classification" data-testid="g10-classification-check">
    <div class="section-head">
      <div class="title-block">
        <h3 class="sheet-title">G10-4 分类的适当性检查表</h3>
        <p class="sheet-sub">核实以公允价值计量且其变动计入当期损益的金融负债分类依据是否符合 CAS 22/37</p>
      </div>
      <div class="head-actions tab-toolbar">
        <G10ImportExportDropdown :wp-id="wpId" sheet="G10-4" @imported="emit('imported')" />
        <el-button size="small" type="primary" plain :disabled="isReadonly" @click="cc.syncFromDetail(false)">
          从明细取数
        </el-button>
        <el-button size="small" plain :disabled="isReadonly" @click="cc.applyFromDerivativeCheck()">
          从 G10-8 带入
        </el-button>
        <el-button
          size="small"
          type="warning"
          plain
          :disabled="isReadonly || !cc.classificationIssues.value.length"
          data-testid="g10-classification-push-adj"
          @click="cc.pushReclassificationDrafts()"
        >
          生成重分类草稿→G10-3
        </el-button>
        <el-button size="small" type="primary" :disabled="isReadonly" @click="cc.addRow()">新增项目</el-button>
        <el-button size="small" :loading="cc.aiLoading.value" :disabled="isReadonly" @click="cc.generateAiConclusion()">
          🤖 AI 结论
        </el-button>
        <el-button
          v-if="!isReadonly"
          size="small"
          type="success"
          plain
          :loading="cc.procedureMarking.value"
          data-testid="g10-classification-mark-procedure"
          @click="onMarkProcedure"
        >
          {{ cc.procedureMarked.value ? '已回填 G10A（可重写）' : '回填 G10A 分类程序' }}
        </el-button>
        <span class="chip-wrap"><GtIndexChip value="wp:G10-2" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:G10-8" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:G10-4" /></span>
        <el-tag size="small" type="info">共 {{ cc.rows.value.length }} 行</el-tag>
        <GtReviewTrigger section-id="G10-4-classification" />
      </div>
    </div>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      title="审计目标：确定以公允价值计量且其变动计入当期损益的金融负债分类是否正确。"
      class="objective-alert"
    />

    <el-alert
      v-if="g108Conclusion"
      type="success"
      :closable="false"
      class="g108-link-alert"
      :title="`G10-8 衍生工具核查结论：${g108Conclusion}（可「从 G10-8 带入」关联索引并预填衍生负债依据）`"
    />

    <details class="procedure-block">
      <summary>二、审计过程（展开）</summary>
      <ol>
        <li>以公允价值计量且其变动计入当期损益的金融负债的指定是否符合准则要求、会计处理是否合理并与前期一致。</li>
        <li>
          就管理层将负债确定为交易性的目的获取书面声明，询问管理层持有相关负债的目的，并实施下列程序印证：
          <ul>
            <li>2.1 考虑管理层以前所述负债持有目的的实际实施情况；</li>
            <li>2.2 复核预算、管理层会议纪要等，检查是否对负债持有目的进行了明确书面指定。</li>
          </ul>
        </li>
        <li>与管理层讨论金融负债分类是否符合企业会计准则，是否根据确定的分类选用了正确的核算方法。</li>
        <li>是否发现管理层在以前年度运用的重大判断和估计存在不合理情形；如存在，记录当年是否进行了恰当会计处理与披露。</li>
      </ol>
    </details>

    <div class="stats-bar">
      <span>已勾选依据 <b>{{ cc.stats.value.withBasis }}</b></span>
      <span v-if="cc.stats.value.missingBasis" class="warn">
        缺依据 <b>{{ cc.stats.value.missingBasis }}</b>
      </span>
      <span v-if="cc.stats.value.categoryMismatch" class="warn">
        类别不一致 <b>{{ cc.stats.value.categoryMismatch }}</b>
      </span>
      <span v-if="cc.reclassStats.value.pending" class="warn">
        G10-3待复核 <b>{{ cc.reclassStats.value.pending }}</b>
      </span>
      <span v-if="cc.reclassStats.value.confirmed">
        已确认 <b>{{ cc.reclassStats.value.confirmed }}</b>
      </span>
      <span>交易性 {{ cc.stats.value.trading }} · 初始指定 {{ cc.stats.value.designated }}</span>
      <span class="total">期末账面合计 {{ fmt(cc.totalBookValue.value) }}</span>
    </div>

    <el-alert
      v-if="cc.classificationIssues.value.length"
      type="warning"
      :closable="false"
      class="missing-alert"
      :title="`有 ${cc.classificationIssues.value.length} 项存在分类问题，可生成 RJE 草稿至 G10-3 或补全依据。`"
    >
      <ul class="issue-list">
        <li v-for="item in cc.classificationIssues.value.slice(0, 6)" :key="item.rowId">
          {{ item.liabilityName }}（{{ fmt(item.closingBookValue) }}）：{{ item.reason }}
        </li>
        <li v-if="cc.classificationIssues.value.length > 6">…共 {{ cc.classificationIssues.value.length }} 项</li>
      </ul>
    </el-alert>

    <el-alert
      v-else-if="cc.stats.value.missingBasis"
      type="warning"
      :closable="false"
      class="missing-alert"
      :title="`有 ${cc.stats.value.missingBasis} 项已列示账面价值但未勾选任一分类依据，请补全「交易性 / 初始指定」列。`"
    />

    <el-table
      :data="tableRows"
      border
      size="small"
      max-height="560"
      :row-class-name="rowClassName"
    >
      <el-table-column label="项目名称" min-width="140" fixed>
        <template #default="{ row }">
          <template v-if="row.isTotal"><b>合计</b></template>
          <el-input
            v-else
            :model-value="row.liabilityName"
            size="small"
            :disabled="isReadonly"
            @change="(v: string) => cc.updateRow(row.id, { liabilityName: v })"
          />
        </template>
      </el-table-column>

      <el-table-column label="G10-2类别" width="88" align="center">
        <template #default="{ row }">
          <span v-if="!row.isTotal" class="cat-tag">{{ row.liabilityCategory || '—' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="期末账面价值" width="120" align="right">
        <template #default="{ row }">
          <template v-if="row.isTotal"><b>{{ fmt(row.closingBookValue) }}</b></template>
          <WpAmountInput
            v-else
            :model-value="row.closingBookValue"
            size="small"
            style="width: 100%"
            :disabled="isReadonly"
            @change="(v: number) => cc.updateRow(row.id, { closingBookValue: v ?? 0 })"
          />
        </template>
      </el-table-column>

      <el-table-column label="「交易性」[需属于下列任一情形之一]" align="center">
        <el-table-column label="近期出售或回购" width="110" align="center">
          <template #default="{ row }">
            <el-select
              v-if="!row.isTotal"
              :model-value="row.tradingNearTermSale"
              size="small"
              :disabled="isReadonly"
              clearable
              @change="(v: string) => cc.updateRow(row.id, { tradingNearTermSale: (v || '') as any })"
            >
              <el-option v-for="o in cc.ynOptions" :key="o.value" :label="o.label" :value="o.value" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="组合短期获利" width="110" align="center">
          <template #default="{ row }">
            <el-select
              v-if="!row.isTotal"
              :model-value="row.tradingPortfolioShortTerm"
              size="small"
              :disabled="isReadonly"
              clearable
              @change="(v: string) => cc.updateRow(row.id, { tradingPortfolioShortTerm: (v || '') as any })"
            >
              <el-option v-for="o in cc.ynOptions" :key="o.value" :label="o.label" :value="o.value" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="衍生金融负债" width="110" align="center">
          <template #header>
            <el-tooltip content="衍生金融负债（不包括被指定为有效套期工具的衍生工具）" placement="top">
              <span>衍生金融负债</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <el-select
              v-if="!row.isTotal"
              :model-value="row.tradingDerivative"
              size="small"
              :disabled="isReadonly"
              clearable
              @change="(v: string) => cc.updateRow(row.id, { tradingDerivative: (v || '') as any })"
            >
              <el-option v-for="o in cc.ynOptions" :key="o.value" :label="o.label" :value="o.value" />
            </el-select>
          </template>
        </el-table-column>
      </el-table-column>

      <el-table-column label="「初始确认时指定」[满足下列条件之一]" align="center">
        <el-table-column label="消除会计错配" width="110" align="center">
          <template #header>
            <el-tooltip content="初始确认时指定为 FVTPL，能够消除或显著减少会计错配" placement="top">
              <span>消除会计错配</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <el-select
              v-if="!row.isTotal"
              :model-value="row.designatedMismatch"
              size="small"
              :disabled="isReadonly"
              clearable
              @change="(v: string) => cc.updateRow(row.id, { designatedMismatch: (v || '') as any })"
            >
              <el-option v-for="o in cc.ynOptions" :key="o.value" :label="o.label" :value="o.value" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="公允价值管理" width="110" align="center">
          <template #header>
            <el-tooltip content="根据正式书面文件，按公允价值为基础进行管理并评价业绩" placement="top">
              <span>公允价值管理</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <el-select
              v-if="!row.isTotal"
              :model-value="row.designatedFvManagement"
              size="small"
              :disabled="isReadonly"
              clearable
              @change="(v: string) => cc.updateRow(row.id, { designatedFvManagement: (v || '') as any })"
            >
              <el-option v-for="o in cc.ynOptions" :key="o.value" :label="o.label" :value="o.value" />
            </el-select>
          </template>
        </el-table-column>
      </el-table-column>

      <el-table-column label="分类依据（自动）" min-width="150">
        <template #default="{ row }">
          <span
            v-if="!row.isTotal"
            :class="{ 'basis-warn': !cc.hasClassificationBasis(row) && (row.closingBookValue || row.liabilityName) }"
          >
            {{ cc.classifyBasisLabel(row) }}
          </span>
        </template>
      </el-table-column>

      <el-table-column label="重分类" width="88" align="center">
        <template #default="{ row }">
          <el-tag
            v-if="!row.isTotal && cc.getReclassStatus(row.id) !== 'none'"
            size="small"
            :type="reclassTagType(row.id)"
          >
            {{ cc.getReclassStatusLabel(row.id) }}
          </el-tag>
          <span v-else-if="!row.isTotal" class="reclass-none">—</span>
        </template>
      </el-table-column>

      <el-table-column label="书面文件索引号" width="120">
        <template #default="{ row }">
          <el-input
            v-if="!row.isTotal"
            :model-value="row.indexRef"
            size="small"
            :disabled="isReadonly"
            @change="(v: string) => cc.updateRow(row.id, { indexRef: v })"
          />
        </template>
      </el-table-column>

      <el-table-column label="操作" width="60" fixed="right">
        <template #default="{ row }">
          <el-button
            v-if="!row.isTotal && !isReadonly"
            size="small"
            type="danger"
            link
            @click="cc.removeRow(row.id)"
          >
            删
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <G10AuditTextCards
      :wp-id="wpId"
      :is-readonly="isReadonly"
      v-model:note="auditNote"
      :conclusion="cc.auditConclusion.value"
      @update:conclusion="(v: string) => { cc.auditConclusion.value = v }"
      note-ai-section="classification-note"
      conclusion-ai-section="classification-conclusion"
      note-title="三、审计说明"
      conclusion-title="四、审计结论"
      note-placeholder="说明分类检查范围、与 G10-2/G10-8 勾稽结果、未勾选依据项目的核查情况及拟调整事项。"
      note-hint="覆盖交易性三情形、初始指定两情形及书面证据索引。"
      conclusion-placeholder="A、分类适当，未见异常。B、除上述应调整事项外，其余未见异常。C、因重大未调整事项或范围受限，不可确认。"
      :related-context="{
        行数: cc.stats.value.total,
        缺依据: cc.stats.value.missingBasis,
        期末合计: cc.totalBookValue.value,
      }"
    />

    <details class="prep-hint">
      <summary>📋 编制提示</summary>
      <ul>
        <li>本表对齐 Excel G10-4：验证「为何分类为 FVTPL」，公允价值测试见 G10-5/G10-6，衍生工具细节见 G10-8。</li>
        <li>「交易性」三列满足任一即可；「初始确认时指定」两列满足任一即可。</li>
        <li>优先点「从明细取数」从 G10-2 带入项目名称、类别与期末账面价值；指定类自动预填「初始指定」列。</li>
        <li>「G10-3」列显示重分类草稿状态：待复核 / 已确认；在 G10-3 点「已复核」后此处同步更新。</li>
        <li>缺依据或 G10-2 类别与勾选不一致时，可「生成重分类草稿→G10-3」；草稿为 RJE（借 2101 / 贷 2501），须复核对方科目。</li>
        <li>有账面价值但「分类依据（自动）」显示未勾选时，须补全依据或考虑提请重分类调整。</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import WpAmountInput from '../../shared/WpAmountInput.vue'
import { computed, ref, toRef, watch, inject } from 'vue'
import { useG10ClassificationCheck } from '../../composables/useG10ClassificationCheck'
import {
  confirmNavigateToSheet,
  dispatchProcedureFocus,
} from '../../composables/g8CrossHelpers'
import {
  G10A_CLASSIFICATION_PROGRAM_NOS,
  G10A_PROCEDURE_SHEET,
} from '../../composables/g10FvCrossHelpers'
import type { ChecklistResponse } from '../../composables/useF1FormData'
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import GtIndexChip from '../../GtIndexChip.vue'
import G10AuditTextCards from '../G10AuditTextCards.vue'
import G10ImportExportDropdown from '../G10ImportExportDropdown.vue'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  projectId?: string
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

const emit = defineEmits<{ imported: [] }>()
const jumpToSection = inject<((sheetName: string) => void) | null>('jumpToSection', null)

const cc = useG10ClassificationCheck({
  allResponses: toRef(props, 'allResponses'),
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly'),
  wpId: toRef(props, 'wpId'),
  projectId: computed(() => props.projectId || ''),
})

const NOTE_KEY = 'G10-4-classification-audit-note'
const auditNote = ref(props.allResponses.get(NOTE_KEY)?.remark ?? '')
watch(auditNote, (v) => {
  if (!props.isReadonly) props.debouncedSave(NOTE_KEY, { item_id: NOTE_KEY, conclusion: null, remark: v })
})

const tableRows = computed(() => [
  ...cc.rows.value,
  {
    id: '__total__',
    seq: 0,
    liabilityName: '合计',
    closingBookValue: cc.totalBookValue.value,
    tradingNearTermSale: '' as const,
    tradingPortfolioShortTerm: '' as const,
    tradingDerivative: '' as const,
    designatedMismatch: '' as const,
    designatedFvManagement: '' as const,
    indexRef: '',
    isTotal: true,
  },
])

function rowClassName({ row }: { row: { isTotal?: boolean; id: string } }) {
  if (row.isTotal) return 'row-total'
  const raw = cc.rows.value.find((r) => r.id === row.id)
  if (!raw) return ''
  if (cc.getReclassStatus(row.id) === 'pending') return 'row-reclass-pending'
  if (cc.getReclassStatus(row.id) === 'confirmed') return 'row-reclass-confirmed'
  const cat = raw.liabilityCategory || ''
  if ((raw.closingBookValue || raw.liabilityName) && !cc.hasClassificationBasis(raw)) return 'row-missing-basis'
  if (cc.getCategoryMismatchReason(raw, cat)) return 'row-category-mismatch'
  return ''
}

function reclassTagType(rowId: string): 'success' | 'warning' | 'info' {
  const s = cc.getReclassStatus(rowId)
  if (s === 'pending') return 'warning'
  if (s === 'confirmed') return 'success'
  return 'info'
}

function fmt(n: number): string {
  if (n == null || !Number.isFinite(n) || n === 0) return '—'
  return n.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
}

async function onMarkProcedure() {
  const n = await cc.markProcedureComplete()
  if (n < 0) return
  dispatchProcedureFocus({
    programNos: [...G10A_CLASSIFICATION_PROGRAM_NOS],
    sheetCode: 'G10A',
    sheetName: G10A_PROCEDURE_SHEET,
  })
  const go = await confirmNavigateToSheet({
    title: '已回填 G10A',
    message: `分类适当性程序（步骤 ${[...G10A_CLASSIFICATION_PROGRAM_NOS].join('/')}）已标记完成。是否前往 G10A 程序表查看？`,
    confirmText: '前往 G10A',
  })
  if (go && jumpToSection) {
    jumpToSection('G10A')
    setTimeout(() => {
      dispatchProcedureFocus({
        programNos: [...G10A_CLASSIFICATION_PROGRAM_NOS],
        sheetCode: 'G10A',
        sheetName: G10A_PROCEDURE_SHEET,
      })
    }, 400)
  }
}

const g108Conclusion = computed(() => props.allResponses.get('G10-derivative-conclusion')?.conclusion?.trim() || '')
</script>

<style scoped>
.g10-classification { padding: 12px; font-size: var(--wp-font-size, 13px); }
.g10-classification :deep(.el-table) {
  --el-table-font-size: var(--wp-font-size, 13px);
  font-size: var(--wp-font-size, 13px);
}
.section-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}
.title-block { min-width: 200px; }
.sheet-title { margin: 0; font-size: 16px; font-weight: 600; color: #1f2a37; }
.sheet-sub { margin: 4px 0 0; font-size: 12px; color: #909399; }
.head-actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.chip-wrap { display: inline-flex; }
.objective-alert { margin-bottom: 10px; }
.g108-link-alert { margin-bottom: 10px; }
.procedure-block {
  margin-bottom: 12px;
  padding: 8px 12px;
  background: #f5f7fa;
  border-left: 3px solid #409eff;
  border-radius: 4px;
  font-size: 12px;
  color: #606266;
}
.procedure-block summary { cursor: pointer; font-weight: 500; color: #409eff; }
.procedure-block ol { margin: 8px 0 0; padding-left: 18px; line-height: 1.6; }
.procedure-block ul { margin: 4px 0; padding-left: 18px; }
.stats-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  margin-bottom: 10px;
  padding: 8px 12px;
  background: #f8f9fb;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: 12px;
  color: #606266;
}
.stats-bar .warn { color: #e6a23c; }
.stats-bar .total { margin-left: auto; font-weight: 600; color: #303133; }
.missing-alert { margin-bottom: 10px; }
.basis-warn { color: #e6a23c; }
:deep(.row-total) { font-weight: 600; background: #f5f7fa; }
:deep(.row-missing-basis) { background: #fdf6ec; }
:deep(.row-category-mismatch) { background: #fef0f0; }
:deep(.row-reclass-pending) { background: #fdf6ec; }
:deep(.row-reclass-confirmed) { background: #f0f9eb; }
.reclass-none { color: #c0c4cc; font-size: 12px; }
.issue-list { margin: 4px 0 0; padding-left: 18px; font-size: 12px; }
.cat-tag { font-size: 12px; color: #606266; }
.prep-hint { margin-top: 12px; font-size: 12px; color: #909399; }
.prep-hint summary { cursor: pointer; }
.prep-hint ul { margin: 8px 0 0; padding-left: 18px; }
</style>
