<template>
  <div class="g1-classification" data-testid="g1-classification">
    <div class="section-head">
      <div class="title-block">
        <h3 class="sheet-title">G1-9 分类的适当性检查表</h3>
        <p class="sheet-sub">核实以公允价值计量且其变动计入当期损益的金融资产分类依据是否符合 CAS 22</p>
      </div>
      <div class="head-actions tab-toolbar">
        <el-button size="small" type="primary" plain :disabled="isReadonly" @click="cls.syncFromDetail(false)">
          从明细取数
        </el-button>
        <el-button size="small" plain :disabled="isReadonly" @click="cls.applyFromBusinessModel()">
          从 G1-8 带入依据
        </el-button>
        <el-button size="small" plain :disabled="isReadonly" @click="cls.applyFromSppi()">
          从 G1-10 带入 SPPI
        </el-button>
        <el-button size="small" type="primary" plain :disabled="isReadonly" @click="cls.applyJointFromUpstream()">
          G1-8+G1-10 联合写入
        </el-button>
        <el-button size="small" type="primary" :disabled="isReadonly" @click="cls.addRow()">新增项目</el-button>
        <G1ImportExportDropdown
          v-if="wpId"
          :wp-id="wpId"
          sheet="G1-9"
          :disabled="isReadonly"
          @imported="emit('imported')"
        />
        <span class="chip-wrap"><GtIndexChip value="wp:G1-2" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:G1-8" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:G1-10" /></span>
        <el-tag size="small" type="info">共 {{ cls.rows.value.length }} 行</el-tag>
        <el-button size="small" @click="openReviewDialog('G1-9-conclusion')">💬复核</el-button>
      </div>
    </div>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      title="审计目标：确定以公允价值计量且其变动计入当期损益的金融资产投资分类是否正确。"
      class="objective-alert"
    />

    <el-alert
      v-if="g18ModelLabel"
      type="success"
      :closable="false"
      class="g18-link-alert"
      :title="`G1-8 业务模式结论：${g18ModelLabel}${g18SuggestClass ? ` → 建议计量 ${g18SuggestClass}` : ''}（可「从 G1-8 带入」或「G1-8+G1-10 联合写入」）`"
    />

    <details class="procedure-block">
      <summary>二、审计过程（展开）</summary>
      <ol>
        <li>以公允价值计量且其变动计入当期损益的金融资产投资的指定是否符合准则要求、会计处理是否合理并与前期一致。</li>
        <li>
          就管理层将投资确定为非交易性的目的获取书面声明，询问管理层持有相关资产的目的，并实施下列程序印证：
          <ul>
            <li>2.1 考虑管理层以前所述投资持有目的的实际实施情况；</li>
            <li>2.2 复核预算、管理层会议纪要等，检查是否对投资持有目的进行了明确书面指定。</li>
          </ul>
        </li>
        <li>与管理层讨论金融资产分类是否符合企业会计准则，是否根据确定的分类选用了正确的核算方法。</li>
        <li>是否发现管理层在以前年度运用的重大判断和估计存在不合理情形；如存在，记录当年是否进行了恰当会计处理与披露。</li>
      </ol>
    </details>

    <div class="stats-bar">
      <span>已勾选依据 <b>{{ cls.stats.value.withBasis }}</b></span>
      <span v-if="cls.stats.value.missingBasis" class="warn">
        缺依据 <b>{{ cls.stats.value.missingBasis }}</b>
      </span>
      <span>交易性 {{ cls.stats.value.trading }} · 债务非SPPI {{ cls.stats.value.debtFail }} · 权益 {{ cls.stats.value.equity }} · 指定 {{ cls.stats.value.designated }}</span>
      <span class="total">期末账面合计 {{ fmt(cls.totalBookValue.value) }}</span>
    </div>

    <el-alert
      v-if="cls.stats.value.missingBasis"
      type="warning"
      :closable="false"
      class="missing-alert"
      :title="`有 ${cls.stats.value.missingBasis} 项已列示账面价值但未勾选任一分类依据，请补全「交易性 / 债务非SPPI / 权益 / 指定 / 其他」。`"
    />

    <el-table
      :data="tableRows"
      border
      size="small"
      max-height="560"
      :row-class-name="rowClassName"
    >
      <el-table-column label="投资项目" min-width="140" fixed>
        <template #default="{ row }">
          <template v-if="row.isTotal">
            <b>合计</b>
          </template>
          <el-input
            v-else
            :model-value="row.investItem"
            size="small"
            :disabled="isReadonly"
            @change="(v: string) => cls.updateRow(row.id, { investItem: v })"
          />
        </template>
      </el-table-column>

      <el-table-column label="期末账面价值" width="120" align="right">
        <template #default="{ row }">
          <template v-if="row.isTotal">
            <b>{{ fmt(row.closingBookValue) }}</b>
          </template>
          <WpAmountInput
            v-else
            :model-value="row.closingBookValue"
            size="small"
            style="width: 100%"
            :disabled="isReadonly"
            @change="(v: number) => cls.updateRow(row.id, { closingBookValue: v ?? 0 })"
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
              @change="(v: string) => cls.updateRow(row.id, { tradingNearTermSale: (v || '') as any })"
            >
              <el-option v-for="o in cls.ynOptions" :key="o.value" :label="o.label" :value="o.value" />
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
              @change="(v: string) => cls.updateRow(row.id, { tradingPortfolioShortTerm: (v || '') as any })"
            >
              <el-option v-for="o in cls.ynOptions" :key="o.value" :label="o.label" :value="o.value" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="衍生工具" width="100" align="center">
          <template #default="{ row }">
            <el-select
              v-if="!row.isTotal"
              :model-value="row.tradingDerivative"
              size="small"
              :disabled="isReadonly"
              clearable
              @change="(v: string) => cls.updateRow(row.id, { tradingDerivative: (v || '') as any })"
            >
              <el-option v-for="o in cls.ynOptions" :key="o.value" :label="o.label" :value="o.value" />
            </el-select>
          </template>
        </el-table-column>
      </el-table-column>

      <el-table-column label="债务工具：非SPPI" width="120" align="center">
        <template #header>
          <el-tooltip content="合同现金流量并非仅为对本金和以未偿付本金金额为基础的利息的支付（勾「是」表示未通过 SPPI，应分类为 FVTPL）" placement="top">
            <span>债务工具：非SPPI</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <el-select
            v-if="!row.isTotal"
            :model-value="row.debtSppiFail"
            size="small"
            :disabled="isReadonly"
            clearable
            @change="(v: string) => cls.updateRow(row.id, { debtSppiFail: (v || '') as any })"
          >
            <el-option v-for="o in cls.ynOptions" :key="o.value" :label="o.label" :value="o.value" />
          </el-select>
        </template>
      </el-table-column>

      <el-table-column label="权益工具投资" width="110" align="center">
        <template #default="{ row }">
          <el-select
            v-if="!row.isTotal"
            :model-value="row.equityInstrument"
            size="small"
            :disabled="isReadonly"
            clearable
            @change="(v: string) => cls.updateRow(row.id, { equityInstrument: (v || '') as any })"
          >
            <el-option v-for="o in cls.ynOptions" :key="o.value" :label="o.label" :value="o.value" />
          </el-select>
        </template>
      </el-table-column>

      <el-table-column label="初始指定消除错配" width="120" align="center">
        <template #header>
          <el-tooltip content="初始确认时指定为 FVTPL，能够消除或显著减少会计错配" placement="top">
            <span>初始指定消除错配</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <el-select
            v-if="!row.isTotal"
            :model-value="row.designatedMismatch"
            size="small"
            :disabled="isReadonly"
            clearable
            @change="(v: string) => cls.updateRow(row.id, { designatedMismatch: (v || '') as any })"
          >
            <el-option v-for="o in cls.ynOptions" :key="o.value" :label="o.label" :value="o.value" />
          </el-select>
        </template>
      </el-table-column>

      <el-table-column label="其他" min-width="120">
        <template #default="{ row }">
          <el-input
            v-if="!row.isTotal"
            :model-value="row.other"
            size="small"
            :disabled="isReadonly"
            @change="(v: string) => cls.updateRow(row.id, { other: v })"
          />
        </template>
      </el-table-column>

      <el-table-column label="分类依据（自动）" min-width="160">
        <template #default="{ row }">
          <span v-if="!row.isTotal" :class="{ 'basis-warn': !cls.hasFvtplBasis(row) && (row.closingBookValue || row.investItem) }">
            {{ cls.classifyBasisLabel(row) }}
          </span>
        </template>
      </el-table-column>

      <el-table-column label="书面文件索引号" width="120">
        <template #default="{ row }">
          <el-input
            v-if="!row.isTotal"
            :model-value="row.indexRef"
            size="small"
            :disabled="isReadonly"
            @change="(v: string) => cls.updateRow(row.id, { indexRef: v })"
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
            @click="cls.removeRow(row.id)"
          >
            删
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <G1AuditTextCards
      :wp-id="wpId"
      :is-readonly="isReadonly"
      v-model:note="auditNote"
      :conclusion="cls.auditConclusion.value"
      @update:conclusion="(v: string) => { cls.auditConclusion.value = v }"
      note-ai-section="classification-note"
      conclusion-ai-section="classification-conclusion"
      note-title="三、审计说明"
      conclusion-title="四、审计结论"
      note-placeholder="说明分类检查范围、与 G1-8/G1-10 勾稽结果、未勾选依据项目的核查情况及拟调整事项。"
      note-hint="覆盖交易性三情形、债务非SPPI、权益工具、初始指定及书面证据索引。"
      conclusion-placeholder="A、分类适当，未见异常。B、除上述应调整事项外，其余未见异常。C、因重大未调整事项或范围受限，不可确认。"
      :related-context="{
        行数: cls.stats.value.total,
        缺依据: cls.stats.value.missingBasis,
        期末合计: cls.totalBookValue.value,
      }"
    />

    <details class="prep-hint">
      <summary>📋 编制提示</summary>
      <ul>
        <li>本表对齐 Excel G1-9：验证「为何分类为 FVTPL」，不是重复做 SPPI/业务模式全过程（细节见 G1-10 / G1-8）。</li>
        <li>「交易性」三列满足任一即可；债务工具勾「非SPPI=是」表示未通过合同现金流测试，应计入 FVTPL。</li>
        <li>优先点「从明细取数」从 G1-2 带入投资项目与期末账面价值；书面证据填入索引号列。</li>
        <li>有账面价值但「分类依据（自动）」显示未勾选时，须补全依据或说明「其他」。</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import WpAmountInput from '../../shared/WpAmountInput.vue'
import { computed, inject, ref, toRef, watch } from 'vue'
import { useG1Classification } from '../../composables/useG1Classification'
import type { ChecklistResponse } from '../../composables/useF1FormData'
import GtIndexChip from '../../GtIndexChip.vue'
import G1AuditTextCards from '../G1AuditTextCards.vue'
import G1ImportExportDropdown from '../G1ImportExportDropdown.vue'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  wpId?: string
}>()

const emit = defineEmits<{ imported: [] }>()

const wpId = computed(() => props.wpId ?? '')
const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})

const cls = useG1Classification({
  allResponses: toRef(props, 'allResponses'),
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly'),
})

const AUDIT_NOTE_KEY = 'G1-9-audit-note'
const auditNote = ref(props.allResponses.get(AUDIT_NOTE_KEY)?.remark ?? '')
watch(auditNote, (v) => {
  if (!props.isReadonly) props.debouncedSave(AUDIT_NOTE_KEY, { conclusion: null, remark: v })
})
watch(
  () => props.allResponses.get(AUDIT_NOTE_KEY)?.remark,
  (v) => { if (v != null && !auditNote.value) auditNote.value = v },
)

const tableRows = computed(() => [
  ...cls.rows.value,
  {
    id: '__total__',
    seq: 0,
    investItem: '合计',
    closingBookValue: cls.totalBookValue.value,
    tradingNearTermSale: '' as const,
    tradingPortfolioShortTerm: '' as const,
    tradingDerivative: '' as const,
    debtSppiFail: '' as const,
    equityInstrument: '' as const,
    designatedMismatch: '' as const,
    other: '',
    indexRef: '',
    isTotal: true,
  },
])

function rowClassName({ row }: { row: { isTotal?: boolean; id: string } }) {
  if (row.isTotal) return 'row-total'
  const raw = cls.rows.value.find((r) => r.id === row.id)
  if (raw && (raw.closingBookValue || raw.investItem) && !cls.hasFvtplBasis(raw)) return 'row-missing-basis'
  return ''
}

function fmt(n: number): string {
  if (n == null || !Number.isFinite(n) || n === 0) return '—'
  return n.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
}

/** G1-8 结论勾稽展示 */
const g18ModelLabel = computed(() => {
  const item = props.allResponses.get('G1-8-model-result')
  if (!item || item.remark === 'INCOMPLETE') return ''
  return item.conclusion || ''
})
const g18SuggestClass = computed(() => {
  const code = props.allResponses.get('G1-8-model-result')?.remark
  if (code === 'OTHER') return 'FVTPL'
  if (code === 'HOLD_AND_SELL') return 'FVOCI'
  if (code === 'HOLD_COLLECT') return 'AC'
  return ''
})
</script>

<style scoped>
.g1-classification { padding: 12px; font-size: var(--wp-font-size, 13px); }
.g1-classification :deep(.el-table) {
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
.g18-link-alert { margin-bottom: 10px; }
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
.prep-hint { margin-top: 12px; font-size: 12px; color: #909399; }
.prep-hint summary { cursor: pointer; }
.prep-hint ul { margin: 8px 0 0; padding-left: 18px; }
</style>
