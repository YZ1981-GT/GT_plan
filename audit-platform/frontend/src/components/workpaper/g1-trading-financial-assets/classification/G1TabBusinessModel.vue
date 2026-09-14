<template>
  <div class="g1-biz-model" data-testid="g1-business-model">
    <div class="section-head">
      <h3 class="sheet-title">G1-8 业务模式分析</h3>
      <div class="head-actions tab-toolbar">
        <span class="chip-wrap"><GtIndexChip value="wp:G1-9" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:G1-10" /></span>
        <el-button
          v-if="!isReadonly"
          size="small"
          plain
          @click="bm.applyTradingPathHints()"
        >
          填入交易性示例路径
        </el-button>
        <el-button size="small" @click="openReviewDialog('G1-8-conclusion')">💬复核</el-button>
      </div>
    </div>

    <details class="guidance-details">
      <summary>📋 编制提示与准则指引</summary>
      <div class="guidance-content">
        <p><strong>审计目标：</strong>确定管理交易性金融资产的业务模式，并与合同现金流量特征（G1-10）结合，支撑分类结论。</p>
        <p>1. 业务模式是事实而非仅管理层声明，应在组合层次（而非单项工具）确定。</p>
        <p>2. 关注历史出售频率/金额、绩效评价与报酬是否基于公允价值、是否为交易目的持有。</p>
        <p>3. 交易性金融资产通常属于「其他业务模式」，计量为 FVTPL；若结论为持有收取，需复核科目归属。</p>
        <p>4. 若不同组合管理目标不同，启用（二）次级组合分别判定。</p>
      </div>
    </details>

    <el-alert
      type="info"
      :closable="false"
      class="objective-alert"
      title="审计目标：评价管理交易性金融资产的业务模式判断是否恰当，并与 SPPI（G1-10）/分类检查（G1-9）勾稽，确认分类计量基础。"
    />

    <div class="methodology">
      CAS22：业务模式决定现金流量来源是收取合同现金流量、出售，或二者兼有。
      出售本身不必然改变模式；频繁且重大的出售通常表明不以收取合同现金流量为目标。
    </div>

    <!-- (一) 单一业务模式问卷 -->
    <el-divider content-position="left">
      <span class="divider-title">(一) 以单一业务模式管理所有交易性金融资产</span>
    </el-divider>

    <div class="questionnaire-list">
      <div
        v-for="item in bm.questionnaire.value"
        :key="item.id"
        class="questionnaire-item"
        :class="{ indented: item.indent }"
      >
        <div class="question-row">
          <span class="question-seq">{{ item.seq }}.</span>
          <span class="question-text">{{ item.question }}</span>
          <el-radio-group
            :model-value="item.answer"
            :disabled="isReadonly"
            size="small"
            class="question-radio"
            @update:model-value="(v: boolean | string | number | undefined) => bm.setAnswer(item.id, v as boolean | null)"
          >
            <el-radio :value="true">是</el-radio>
            <el-radio :value="false">否</el-radio>
          </el-radio-group>
        </div>
        <div class="explanation-row">
          <el-input
            :model-value="item.explanation"
            type="textarea"
            :autosize="{ minRows: 1, maxRows: 4 }"
            placeholder="实际情况及未来预期说明（选填）"
            :disabled="isReadonly"
            @update:model-value="(v: string) => bm.setExplanation(item.id, v)"
          />
        </div>
      </div>
    </div>

    <div class="audit-evaluation">
      <label class="field-label">审计评价</label>
      <el-input
        :model-value="bm.auditEvaluation.value"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 6 }"
        placeholder="综合说明业务模式判断依据、与历史出售及绩效评价的一致性…"
        :disabled="isReadonly"
        @update:model-value="bm.setAuditEvaluation"
      />
    </div>

    <div class="conclusion-area">
      <span class="conclusion-label">结论：</span>
      <el-tag
        :color="bm.conclusionChip.value.color"
        :type="bm.conclusionChip.value.type"
        size="large"
        effect="dark"
        round
      >
        {{ bm.conclusionChip.value.label }}
      </el-tag>
    </div>

    <el-alert
      v-if="bm.crossCheckWarning.value"
      :title="bm.crossCheckWarning.value"
      type="warning"
      show-icon
      :closable="false"
      class="cross-check-warning"
    />

    <!-- (二) 次级组合 -->
    <el-divider content-position="left">
      <span class="divider-title">(二) 将交易性金融资产拆分为次级组合分别确定业务模式</span>
    </el-divider>

    <div class="sub-portfolio-toggle">
      <span class="field-label">是否适用：</span>
      <el-radio-group
        :model-value="bm.hasSubPortfolios.value"
        :disabled="isReadonly"
        size="small"
        @update:model-value="(v: boolean | string | number | undefined) => bm.setHasSubPortfolios(!!v)"
      >
        <el-radio :value="true">是，需分拆为次级组合</el-radio>
        <el-radio :value="false">否，单一业务模式适用</el-radio>
      </el-radio-group>
    </div>

    <div v-if="bm.hasSubPortfolios.value" class="sub-portfolios-section">
      <el-table :data="bm.subPortfolios.value" border size="small" empty-text="暂无次级组合，点击下方新增。">
        <el-table-column label="组合" min-width="140">
          <template #default="{ row }">
            <el-input
              :model-value="row.name"
              size="small"
              :disabled="isReadonly"
              @change="(v: string) => bm.updateSubPortfolio(row.id, { name: v })"
            />
          </template>
        </el-table-column>
        <el-table-column label="组合依据" min-width="160">
          <template #default="{ row }">
            <el-input
              :model-value="row.basis"
              size="small"
              :disabled="isReadonly"
              @change="(v: string) => bm.updateSubPortfolio(row.id, { basis: v })"
            />
          </template>
        </el-table-column>
        <el-table-column label="业务模式" min-width="160">
          <template #default="{ row }">
            <el-select
              :model-value="row.businessModel"
              size="small"
              :disabled="isReadonly"
              style="width: 100%"
              @change="(v: string) => bm.updateSubPortfolio(row.id, { businessModel: v })"
            >
              <el-option
                v-for="opt in modelOptions"
                :key="opt"
                :label="opt"
                :value="opt"
              />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="列报项目" min-width="140">
          <template #default="{ row }">
            <el-input
              :model-value="row.reportItem"
              size="small"
              :disabled="isReadonly"
              @change="(v: string) => bm.updateSubPortfolio(row.id, { reportItem: v })"
            />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="60" fixed="right">
          <template #default="{ row }">
            <el-button
              v-if="!isReadonly"
              size="small"
              type="danger"
              link
              @click="bm.removeSubPortfolio(row.id)"
            >删</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-button
        v-if="!isReadonly"
        class="add-sub-btn"
        type="primary"
        plain
        size="small"
        @click="bm.addSubPortfolio()"
      >
        + 新增次级组合
      </el-button>
    </div>

    <G1AuditTextCards
      :wp-id="wpId"
      :is-readonly="isReadonly"
      v-model:note="auditNote"
      :conclusion="bm.auditConclusion.value"
      @update:conclusion="bm.setAuditConclusion"
      note-ai-section="business-model-note"
      conclusion-ai-section="business-model-conclusion"
      note-placeholder="填写审计说明：了解管理层如何管理资产、绩效评价与出售历史；问卷结论与实际情况是否一致。"
      note-hint="覆盖业务模式层次、出售分析与结论依据。"
      conclusion-hint="明确业务模式类型，并说明与 G1-9/G1-10 分类勾稽结果。"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, toRef, computed, inject, watch } from 'vue'
import { useG1BusinessModel, G1_BIZ_MODEL_CHIP } from '../../composables/useG1BusinessModel'
import type { ChecklistResponse } from '../../composables/useF1FormData'
import GtIndexChip from '../../GtIndexChip.vue'
import G1AuditTextCards from '../G1AuditTextCards.vue'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  wpId?: string
}>()

const wpId = computed(() => props.wpId ?? '')
const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})

const bm = useG1BusinessModel({
  allResponses: toRef(props, 'allResponses'),
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly'),
})

const modelOptions = [
  G1_BIZ_MODEL_CHIP.HOLD_COLLECT.label,
  G1_BIZ_MODEL_CHIP.HOLD_AND_SELL.label,
  G1_BIZ_MODEL_CHIP.OTHER.label,
]

const AUDIT_NOTE_KEY = 'G1-8-audit-note'
const auditNote = ref(props.allResponses.get(AUDIT_NOTE_KEY)?.remark ?? '')
watch(auditNote, (v) => {
  if (!props.isReadonly) props.debouncedSave(AUDIT_NOTE_KEY, { conclusion: null, remark: v })
})
</script>

<style scoped>
.g1-biz-model { padding: 12px; font-size: var(--wp-font-size, 13px); }
.section-head {
  display: flex; justify-content: space-between; align-items: flex-start;
  gap: 12px; margin-bottom: 12px; flex-wrap: wrap;
}
.sheet-title { margin: 0; font-size: 16px; font-weight: 600; color: #1f2a37; }
.head-actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.chip-wrap { display: inline-flex; align-items: center; }
.guidance-details { margin-bottom: 10px; font-size: 12px; color: #606266; }
.guidance-details summary { cursor: pointer; color: #4b2d77; font-weight: 500; }
.guidance-content { margin-top: 8px; }
.guidance-content p { margin: 4px 0; }
.objective-alert { margin-bottom: 10px; }
.methodology {
  margin-bottom: 12px; padding: 8px 12px; background: #fdf6ec;
  border-left: 3px solid #e6a23c; font-size: 12px; color: #8a6d3b; border-radius: 2px;
}
.divider-title { font-weight: 600; color: #303133; }
.questionnaire-list { display: flex; flex-direction: column; gap: 12px; margin-bottom: 14px; }
.questionnaire-item.indented { margin-left: 24px; padding-left: 12px; border-left: 2px solid #e4e7ed; }
.question-row {
  display: flex; align-items: flex-start; gap: 8px; flex-wrap: wrap; margin-bottom: 6px;
}
.question-seq { font-weight: 600; color: #606266; min-width: 28px; }
.question-text { flex: 1; min-width: 200px; color: #303133; line-height: 1.5; }
.question-radio { flex-shrink: 0; }
.explanation-row { margin-left: 36px; }
.audit-evaluation { margin-bottom: 12px; }
.field-label { display: block; font-weight: 600; margin-bottom: 6px; color: #606266; font-size: 13px; }
.conclusion-area {
  display: flex; align-items: center; gap: 10px; margin: 12px 0;
  padding: 10px 14px; background: #f8f9fb; border-radius: 6px; border: 1px solid #ebeef5;
}
.conclusion-label { font-weight: 600; color: #303133; }
.cross-check-warning { margin-bottom: 12px; }
.sub-portfolio-toggle {
  display: flex; align-items: center; gap: 12px; margin-bottom: 12px; flex-wrap: wrap;
}
.sub-portfolios-section { margin-bottom: 16px; }
.add-sub-btn { margin-top: 10px; }
</style>
