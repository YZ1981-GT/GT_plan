<template>
  <div class="g8-disc" :data-testid="variant === 'listed' ? 'g8-disclosure-listed' : 'g8-disclosure-soe'">
    <div class="section-head">
      <h3 class="sheet-title">{{ disc.title.value }}</h3>
      <div class="head-actions">
        <el-button
          v-if="!isReadonly"
          size="small"
          type="primary"
          plain
          data-testid="g8-disclosure-sync-detail"
          @click="onSyncFromDetail"
        >↓ 从 G8-2 带入</el-button>
        <el-button
          v-if="!isReadonly"
          size="small"
          plain
          data-testid="g8-disclosure-sync-designation"
          @click="onSyncDesignation"
        >指定原因草稿</el-button>
        <GtReviewTrigger :section-id="variant === 'listed' ? 'G8-disclosure-listed' : 'G8-disclosure-soe'" />
      </div>
    </div>

    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 结构与 Excel 底稿一致：余额表 → 指定原因 → {{ variant === 'listed' ? 'OCI 变动表' : '期末明细表' }}。</p>
        <p>2. 建议先编 G8-2，再「从 G8-2 带入」；超额项目汇总为「其他」。余额「合计」期末应与 G8-1 审定数勾稽。</p>
        <p>3. 指定原因可从 G8-2/G8-5 生成草稿后人工改写；股利收入 G8-2 无对应列，需手工补录。</p>
      </div>
    </details>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      :title="objectiveTitle"
      class="objective-alert"
    />

    <el-alert
      v-if="disc.otherVariantHasContent.value"
      type="warning"
      :closable="false"
      show-icon
      class="sync-hint"
      data-testid="g8-disclosure-variant-mutex"
      :title="`「${disc.otherVariantLabel.value}」已有填报内容。通常只需编制适用主体类型的一张附注表，请确认是否误填两表。`"
    />

    <el-alert
      v-if="disc.completenessGaps.value.length"
      type="info"
      :closable="false"
      show-icon
      class="sync-hint"
      data-testid="g8-disclosure-completeness-gaps"
      :title="`完成缺口：${disc.completenessGaps.value.join('；')}（目录完成需：指定原因 + 与审定勾稽）`"
    />

    <el-alert
      v-if="disc.hasAdjCrossMismatch.value"
      type="warning"
      :closable="false"
      show-icon
      class="sync-hint"
      data-testid="g8-disclosure-adj-cross"
    >
      余额合计期末 {{ fmt(disc.primaryCurrentAmount.value) }} 与 G8-1 审定数
      {{ fmt(disc.adjudicatedAmount.value ?? 0) }} 差异
      {{ fmt(disc.adjCrossVariance.value ?? 0) }}。
      <el-button
        v-if="!isReadonly"
        link
        size="small"
        type="primary"
        data-testid="g8-disclosure-sync-adj"
        @click="onSyncAdjudicated"
      >写入审定数</el-button>
    </el-alert>
    <el-alert
      v-else-if="disc.adjudicatedAmount.value != null"
      type="success"
      :closable="false"
      show-icon
      class="sync-hint"
    >
      已同步审定数（1503）：{{ fmt(disc.adjudicatedAmount.value) }}，与余额合计期末勾稽一致。
      <el-button link size="small" @click="disc.pullLatestAdjudicated(false)">刷新</el-button>
    </el-alert>
    <el-alert v-else type="info" :closable="false" show-icon class="sync-hint">
      尚未发布 G8-1 审定数。请先在 G8-1 点击「发布审定数」，再回此表勾稽。
    </el-alert>

    <!-- 监管说明 / （1）标题 -->
    <p class="tpl-intro">{{ disc.introText.value }}</p>

    <!-- ① 余额表：项目 | 期末 | 上年年末/期初 -->
    <el-table
      :data="disc.balanceRows.value"
      border
      size="small"
      class="disc-table"
      :row-class-name="balanceRowClass"
      data-testid="g8-disclosure-balance-table"
    >
      <el-table-column :label="'项  目'" min-width="160">
        <template #default="{ row }">
          <span v-if="row.isTotal" class="total-label">{{ row.label }}</span>
          <el-input
            v-else-if="!isReadonly"
            :model-value="row.label"
            size="small"
            placeholder="项目名称"
            @update:model-value="(v: string) => disc.updateBalance(row.rowKey, 'label', v)"
          />
          <span v-else>{{ row.label || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="期末余额" width="140" align="right">
        <template #default="{ row }">
          <span v-if="row.isTotal" class="formula-cell">{{ fmt(row.closing) }}</span>
          <el-input-number
            v-else-if="!isReadonly"
            :model-value="row.closing"
            size="small"
            :controls="false"
            style="width:100%"
            @update:model-value="(v: number) => disc.updateBalance(row.rowKey, 'closing', v ?? 0)"
          />
          <span v-else>{{ fmt(row.closing) }}</span>
        </template>
      </el-table-column>
      <el-table-column :label="priorColLabel" width="140" align="right">
        <template #default="{ row }">
          <span v-if="row.isTotal" class="formula-cell">{{ fmt(row.prior) }}</span>
          <el-input-number
            v-else-if="!isReadonly"
            :model-value="row.prior"
            size="small"
            :controls="false"
            style="width:100%"
            @update:model-value="(v: number) => disc.updateBalance(row.rowKey, 'prior', v ?? 0)"
          />
          <span v-else>{{ fmt(row.prior) }}</span>
        </template>
      </el-table-column>
    </el-table>

    <!-- 指定原因（叙事，跨列） -->
    <div class="designation-block" data-testid="g8-disclosure-designation">
      <p class="designation-hint">{{ disc.designationHint.value }}</p>
      <div class="note-cell">
        <el-input
          :model-value="disc.designationText.value"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 6 }"
          :disabled="isReadonly"
          :placeholder="disc.designationPlaceholder.value"
          @update:model-value="disc.updateDesignation"
        />
        <el-button
          v-if="!isReadonly"
          size="small"
          link
          :loading="disc.sectionAiLoading.value.designation"
          data-testid="g8-disclosure-section-ai-designation"
          @click="disc.generateSectionAi('designation')"
        >🤖</el-button>
      </div>
    </div>

    <!-- 上市：OCI 变动表（6 列） -->
    <template v-if="variant === 'listed'">
      <el-table
        :data="disc.ociRows.value"
        border
        size="small"
        class="disc-table"
        data-testid="g8-disclosure-oci-table"
      >
        <el-table-column label="项  目" min-width="120">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.label"
              size="small"
              placeholder="项目"
              @update:model-value="(v: string) => disc.updateOci(row.rowKey, 'label', v)"
            />
            <span v-else>{{ row.label || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期计入其他综合收益的利得和损失" width="130" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.ociPeriod" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => disc.updateOci(row.rowKey, 'ociPeriod', v ?? 0)" />
            <span v-else>{{ fmt(row.ociPeriod) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期末累计计入其他综合收益的利得和损失" width="140" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.ociCumulative" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => disc.updateOci(row.rowKey, 'ociCumulative', v ?? 0)" />
            <span v-else>{{ fmt(row.ociCumulative) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期确认的股利收入" width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.dividend" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => disc.updateOci(row.rowKey, 'dividend', v ?? 0)" />
            <span v-else>{{ fmt(row.dividend) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="因终止确认转入留存收益的累计利得和损失" width="140" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.transferToRE" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => disc.updateOci(row.rowKey, 'transferToRE', v ?? 0)" />
            <span v-else>{{ fmt(row.transferToRE) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="终止确认的原因" min-width="140">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.derecogReason"
              size="small"
              @update:model-value="(v: string) => disc.updateOci(row.rowKey, 'derecogReason', v)"
            />
            <span v-else>{{ row.derecogReason || '—' }}</span>
          </template>
        </el-table-column>
      </el-table>
    </template>

    <!-- 国企：（2）期末明细表 -->
    <template v-else>
      <h4 class="section2-title">{{ disc.section2Title.value }}</h4>
      <el-table
        :data="disc.detailRows.value"
        border
        size="small"
        class="disc-table"
        :row-class-name="detailRowClass"
        data-testid="g8-disclosure-detail-table"
      >
        <el-table-column label="项目名称" min-width="120">
          <template #default="{ row }">
            <span v-if="row.isTotal" class="total-label">{{ row.label }}</span>
            <el-input
              v-else-if="!isReadonly"
              :model-value="row.label"
              size="small"
              placeholder="项目名称"
              @update:model-value="(v: string) => disc.updateDetail(row.rowKey, 'label', v)"
            />
            <span v-else>{{ row.label || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期确认的股利收入" width="120" align="right">
          <template #default="{ row }">
            <span v-if="row.isTotal" class="formula-cell">{{ fmt(row.dividend) }}</span>
            <el-input-number v-else-if="!isReadonly" :model-value="row.dividend" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => disc.updateDetail(row.rowKey, 'dividend', v ?? 0)" />
            <span v-else>{{ fmt(row.dividend) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期计入其他综合收益的利得或损失" width="140" align="right">
          <template #default="{ row }">
            <span v-if="row.isTotal" class="formula-cell">{{ fmt(row.ociPeriod) }}</span>
            <el-input-number v-else-if="!isReadonly" :model-value="row.ociPeriod" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => disc.updateDetail(row.rowKey, 'ociPeriod', v ?? 0)" />
            <span v-else>{{ fmt(row.ociPeriod) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="截至期末累计计入其他综合收益的利得或损失" width="150" align="right">
          <template #default="{ row }">
            <span v-if="row.isTotal" class="formula-cell">{{ fmt(row.ociCumulative) }}</span>
            <el-input-number v-else-if="!isReadonly" :model-value="row.ociCumulative" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => disc.updateDetail(row.rowKey, 'ociCumulative', v ?? 0)" />
            <span v-else>{{ fmt(row.ociCumulative) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="其他综合收益转入留存收益的金额" width="140" align="right">
          <template #default="{ row }">
            <span v-if="row.isTotal" class="formula-cell">{{ fmt(row.transferAmt) }}</span>
            <el-input-number v-else-if="!isReadonly" :model-value="row.transferAmt" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => disc.updateDetail(row.rowKey, 'transferAmt', v ?? 0)" />
            <span v-else>{{ fmt(row.transferAmt) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="其他综合收益转入留存收益的原因" min-width="140">
          <template #default="{ row }">
            <template v-if="row.isTotal">—</template>
            <el-input
              v-else-if="!isReadonly"
              :model-value="row.transferReason"
              size="small"
              @update:model-value="(v: string) => disc.updateDetail(row.rowKey, 'transferReason', v)"
            />
            <span v-else>{{ row.transferReason || '—' }}</span>
          </template>
        </el-table-column>
      </el-table>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, toRef } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import { useG8Disclosure } from '../../composables/useG8Disclosure'
import type { ChecklistResponse } from '../../composables/useF1FormData'

const props = defineProps<{
  variant: 'listed' | 'soe'
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  isReadonly: boolean
  debouncedSave: (id: string, d: Partial<ChecklistResponse>) => void
}>()

const disc = useG8Disclosure({
  variant: props.variant,
  wpId: toRef(props, 'wpId'),
  allResponses: computed(() => props.allResponses),
  debouncedSave: props.debouncedSave,
  isReadonly: computed(() => props.isReadonly),
})

const priorColLabel = computed(() =>
  props.variant === 'listed' ? '上年年末余额' : '期初余额',
)

const objectiveTitle = computed(() =>
  props.variant === 'listed'
    ? '审计目标：核实其他权益工具投资附注披露（上市公司格式）项目、金额与公允价值层次分类的完整准确，确认与审定表（科目1503）勾稽一致，披露符合企业会计准则及监管要求。'
    : '审计目标：核实其他权益工具投资附注披露（国有企业格式）项目、金额与 OCI 相关披露的完整准确，确认与审定表（科目1503）勾稽一致，披露符合企业会计准则要求。',
)

function onSyncAdjudicated() {
  disc.pullLatestAdjudicated(true)
  if (disc.adjudicatedAmount.value == null) {
    ElMessage.warning('尚无 G8-1 审定数，请先在审定表发布')
    return
  }
  ElMessage.success(`已将审定数 ${fmt(disc.adjudicatedAmount.value)} 写入余额合计口径`)
}

async function onSyncFromDetail() {
  if (disc.hasContent.value) {
    try {
      await ElMessageBox.confirm(
        '当前附注已有填报内容，从 G8-2 带入将覆盖余额表、OCI/明细及指定原因草稿。是否继续？',
        '确认覆盖',
        { type: 'warning', confirmButtonText: '覆盖带入', cancelButtonText: '取消' },
      )
    } catch {
      return
    }
  }
  const res = disc.syncFromDetail(true)
  if (!res.sourceCount) {
    ElMessage.warning('G8-2 尚无明细，请先编制明细表')
    return
  }
  const bits = [`已从 G8-2 带入 ${res.sourceCount} 项`]
  if (res.overflowCount) bits.push(`超额 ${res.overflowCount} 项已汇总为「其他」`)
  if (res.designationFilled) bits.push('已生成指定原因草稿')
  if (res.missingFields.includes('dividend')) bits.push('股利收入需手工补录')
  ElMessage.success(bits.join('；'))
}

async function onSyncDesignation() {
  if ((disc.designationText.value || '').trim()) {
    try {
      await ElMessageBox.confirm(
        '指定原因已有内容，生成草稿将覆盖现有文本。是否继续？',
        '确认覆盖',
        { type: 'warning', confirmButtonText: '覆盖', cancelButtonText: '取消' },
      )
    } catch {
      return
    }
  }
  const res = disc.syncDesignationOnly()
  if (!res.filled) {
    ElMessage.warning('G8-2 / G8-5 无可用指定原因，请先填写明细或指定适当性表')
    return
  }
  ElMessage.success('已写入指定原因草稿，请人工复核改写')
}

function balanceRowClass({ row }: { row: { isTotal?: boolean } }) {
  return row.isTotal ? 'row-total' : ''
}

function detailRowClass({ row }: { row: { isTotal?: boolean } }) {
  return row.isTotal ? 'row-total' : ''
}

function fmt(n: number): string {
  return Number(n || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.g8-disc { font-size: var(--wp-font-size, 13px); }
.section-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.sheet-title { margin: 0; font-size: 15px; }
.head-actions { display: flex; gap: 8px; }
.sync-hint { margin-bottom: 8px; }
.guidance-details { margin-bottom: 10px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: 12px; color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.objective-alert { margin-bottom: 10px; }
.tpl-intro { font-size: 12px; color: #606266; line-height: 1.6; margin: 8px 0 10px; }
.disc-table { margin-bottom: 12px; font-size: 13px; }
.designation-block {
  margin: 8px 0 14px;
  padding: 10px 12px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 4px;
}
.designation-hint { margin: 0 0 6px; font-size: 12px; color: #909399; }
.section2-title { margin: 4px 0 8px; font-size: 14px; font-weight: 600; }
.note-cell { display: flex; align-items: flex-start; gap: 4px; }
.total-label { font-weight: 600; }
.formula-cell { font-weight: 600; color: #409eff; }
:deep(.row-total) { background: #f5f7fa; font-weight: 600; }
</style>
