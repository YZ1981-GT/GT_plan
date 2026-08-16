<template>
  <div class="h4-tab-stocktake-plan">
    <el-alert
      type="info"
      :closable="false"
      class="objective-alert"
      title="审计目标：参照固定资产监盘计划范式，按「风险评估→了解存放/内控→计划安排→双向抽盘」制定工程物资监盘计划，支撑 H4-6 执行与 H4-6B 小结。"
    />

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <GtIndexChip value="wp:H4-6A" :context-project-id="projectId" />
        <el-tag size="small" :type="planReady ? 'success' : 'danger'">
          {{ planReady ? '可进 H4-6' : `缺 ${blockers.length} 项` }}
        </el-tag>
        <el-tag v-if="plan.existenceRiskLevel" size="small" type="info">
          风险 {{ plan.existenceRiskLevel }} · 建议覆盖≥{{ riskCoverageHint }}%
        </el-tag>
      </div>
      <div class="toolbar-right">
        <el-button v-if="!isReadonly" size="small" :disabled="!plan.existenceRiskLevel" @click="onApplyRisk">
          按风险填覆盖率
        </el-button>
        <el-button v-if="!isReadonly" size="small" @click="onDraftConclusion">起草结论</el-button>
        <el-button v-if="!isReadonly" size="small" type="primary" plain @click="onPushToCheck">回填→H4-6</el-button>
        <el-button size="small" type="primary" @click="emit('navigate-sheet', 'H4-6')">进入 H4-6 →</el-button>
        <el-button size="small" @click="emit('navigate-sheet', 'H4-6B')">H4-6B 小结 →</el-button>
        <el-button size="small" type="default" link @click="openReview('H4-6A')">💬 复核</el-button>
      </div>
    </div>

    <el-alert
      v-for="(b, i) in blockers"
      :key="i"
      type="warning"
      :closable="false"
      show-icon
      :title="b"
      style="margin-bottom:6px"
    />

    <ItemAttachment
      v-if="projectId && wpId"
      :project-id="projectId"
      :wp-id="wpId"
      sheet-key="H4-6A"
      :item-index="0"
      accept=".pdf,.png,.jpg,.jpeg,.xlsx,.xls,.doc,.docx"
    />

    <el-card shadow="never" class="block-card">
      <template #header><span>一、存在性认定重大错报风险</span></template>
      <el-form label-width="110px" size="small">
        <el-form-item label="风险程度">
          <el-radio-group
            :model-value="plan.existenceRiskLevel"
            :disabled="isReadonly"
            @update:model-value="(v: string) => updatePlan('existenceRiskLevel', v as any)"
          >
            <el-radio value="低">低</el-radio>
            <el-radio value="中">中</el-radio>
            <el-radio value="高">高</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="评估说明">
          <el-input
            :model-value="plan.existenceRiskNote"
            type="textarea"
            :rows="2"
            :disabled="isReadonly"
            placeholder="结合固有风险、控制风险、以前年度发现等…"
            @update:model-value="(v: string) => updatePlan('existenceRiskNote', v)"
          />
        </el-form-item>
      </el-form>
    </el-card>

    <el-card shadow="never" class="block-card">
      <template #header><span>二、了解工程物资存放与管理</span></template>
      <el-form label-width="110px" size="small">
        <el-form-item label="存放概况">
          <el-input
            :model-value="plan.storageOverview"
            type="textarea"
            :rows="2"
            :disabled="isReadonly"
            placeholder="仓库/工地堆场分布、保管责任、长期积压情况…"
            @update:model-value="(v: string) => updatePlan('storageOverview', v)"
          />
        </el-form-item>
        <el-form-item label="内控概况">
          <el-input
            :model-value="plan.controlOverview"
            type="textarea"
            :rows="2"
            :disabled="isReadonly"
            placeholder="入库、领用、盘点制度与执行情况…"
            @update:model-value="(v: string) => updatePlan('controlOverview', v)"
          />
        </el-form-item>
        <el-form-item label="以前年度">
          <el-input
            :model-value="plan.priorYearFindings"
            type="textarea"
            :rows="2"
            :disabled="isReadonly"
            placeholder="以前年度监盘发现及本年关注点…"
            @update:model-value="(v: string) => updatePlan('priorYearFindings', v)"
          />
        </el-form-item>
      </el-form>

      <div class="loc-head">
        <span>存放地点明细</span>
        <el-button v-if="!isReadonly" size="small" type="primary" @click="addLocation">+ 地点</el-button>
      </div>
      <el-table :data="plan.locations" border size="small" empty-text="可登记主要仓库/堆场">
        <el-table-column label="地点" min-width="120">
          <template #default="{ row }">
            <el-input
              :model-value="row.location"
              size="small"
              :disabled="isReadonly"
              @update:model-value="(v: string) => updateLocation(row.rowId, { location: v })"
            />
          </template>
        </el-table-column>
        <el-table-column label="物资类别" min-width="120">
          <template #default="{ row }">
            <el-input
              :model-value="row.materialTypes"
              size="small"
              :disabled="isReadonly"
              @update:model-value="(v: string) => updateLocation(row.rowId, { materialTypes: v })"
            />
          </template>
        </el-table-column>
        <el-table-column label="估计金额" width="110">
          <template #default="{ row }">
            <WpAmountInput
              :model-value="row.estimatedAmount"
              size="small"
              :disabled="isReadonly"
              @update:model-value="(v: number | undefined) => updateLocation(row.rowId, { estimatedAmount: v ?? 0 })"
            />
          </template>
        </el-table-column>
        <el-table-column label="备注" min-width="100">
          <template #default="{ row }">
            <el-input
              :model-value="row.remark"
              size="small"
              :disabled="isReadonly"
              @update:model-value="(v: string) => updateLocation(row.rowId, { remark: v })"
            />
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" width="50">
          <template #default="{ row }">
            <el-button link type="danger" size="small" @click="removeLocation(row.rowId)">删</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card shadow="never" class="block-card">
      <template #header><span>三、监盘计划安排</span></template>
      <el-form label-width="110px" size="small">
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="计划日期">
              <el-input
                :model-value="plan.stocktakeDate"
                :disabled="isReadonly"
                placeholder="YYYY-MM-DD 或期间"
                @update:model-value="(v: string) => updatePlan('stocktakeDate', v)"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="参与人员">
              <el-input
                :model-value="plan.participants"
                :disabled="isReadonly"
                placeholder="项目组监盘人员"
                @update:model-value="(v: string) => updatePlan('participants', v)"
              />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="监盘方法">
              <el-select
                :model-value="plan.method"
                :disabled="isReadonly"
                style="width:100%"
                allow-create
                filterable
                @update:model-value="(v: string) => updatePlan('method', v)"
              >
                <el-option label="抽盘" value="抽盘" />
                <el-option label="全面盘点" value="全面盘点" />
                <el-option label="抽盘+观察" value="抽盘+观察" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="计划覆盖率%">
              <el-input-number
                :model-value="plan.plannedCoveragePct ?? undefined"
                :disabled="isReadonly"
                :controls="false"
                :precision="1"
                style="width:100%"
                @update:model-value="(v: number | undefined) => updatePlan('plannedCoveragePct', v ?? null)"
              />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="监盘范围">
          <el-input
            :model-value="plan.scope"
            type="textarea"
            :rows="2"
            :disabled="isReadonly"
            placeholder="期末工程物资类别/仓库范围…"
            @update:model-value="(v: string) => updatePlan('scope', v)"
          />
        </el-form-item>
        <el-form-item label="样本量说明">
          <el-input
            :model-value="plan.sampleSizeNote"
            type="textarea"
            :rows="2"
            :disabled="isReadonly"
            placeholder="特定样本、抽样方法、IDEA 选样等…"
            @update:model-value="(v: string) => updatePlan('sampleSizeNote', v)"
          />
        </el-form-item>
        <el-form-item label="双向抽盘">
          <el-input
            :model-value="plan.bidirectionalNote"
            type="textarea"
            :rows="2"
            :disabled="isReadonly"
            @update:model-value="(v: string) => updatePlan('bidirectionalNote', v)"
          />
        </el-form-item>
        <el-form-item label="与管理层沟通">
          <el-input
            :model-value="plan.managementCommunication"
            type="textarea"
            :rows="2"
            :disabled="isReadonly"
            placeholder="沟通时间、对象、对方确认事项…"
            @update:model-value="(v: string) => updatePlan('managementCommunication', v)"
          />
        </el-form-item>
      </el-form>
    </el-card>

    <el-card shadow="never" class="block-card">
      <template #header><span>四、监盘计划结论</span></template>
      <el-input
        :model-value="plan.planConclusion"
        type="textarea"
        :rows="4"
        :disabled="isReadonly"
        placeholder="就监盘计划是否适当发表结论…"
        @update:model-value="(v: string) => updatePlan('planConclusion', v)"
      />
    </el-card>

    <details class="hint">
      <summary>编制提示</summary>
      <ul>
        <li>本表参照固定资产（H1-9）监盘计划结构，按工程物资场景精简。</li>
        <li>计划完成后可「回填→H4-6」，将日期/人员/范围写入检查表过程段。</li>
        <li>执行记录在 H4-6；现场察看小结在 H4-6B。</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import WpAmountInput from '../../shared/WpAmountInput.vue'
import { computed, toRef, inject } from 'vue'
import { ElMessage } from 'element-plus'
import { useH4StocktakePlan } from '../../composables/useH4StocktakePlan'
import GtIndexChip from '../../GtIndexChip.vue'
import ItemAttachment from '../../ItemAttachment.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{ (e: 'navigate-sheet', sheetName: string): void }>()
const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})

const {
  plan, blockers, planReady, riskCoverageHint,
  updatePlan, addLocation, removeLocation, updateLocation,
  applyRiskCoverage, draftPlanConclusionText, pushPlanToCheckMeta,
} = useH4StocktakePlan({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: toRef(props, 'allResponses') as any,
})

const isReadonly = computed(() => props.isReadonly)
const projectId = computed(() => props.projectId)
const wpId = computed(() => props.wpId)

function onApplyRisk() {
  applyRiskCoverage()
  ElMessage.success(`已按风险填入建议覆盖率 ${riskCoverageHint.value}%`)
}
function onDraftConclusion() {
  draftPlanConclusionText()
  ElMessage.success('已起草计划结论')
}
function onPushToCheck() {
  const r = pushPlanToCheckMeta()
  ElMessage[r.ok ? 'success' : 'info'](r.message)
  if (r.ok) emit('navigate-sheet', 'H4-6')
}
function openReview(id: string) { openReviewDialog(id) }
</script>

<style scoped>
.h4-tab-stocktake-plan { padding: 16px; font-size: var(--wp-font-size, 13px); display: flex; flex-direction: column; gap: 12px; }
.objective-alert { margin-bottom: 0; }
.tab-toolbar { display: flex; justify-content: space-between; gap: 8px; flex-wrap: wrap; }
.toolbar-left, .toolbar-right { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.block-card { margin: 0; }
.loc-head { display: flex; justify-content: space-between; align-items: center; margin: 8px 0; font-weight: 600; font-size: 13px; }
.hint { font-size: 12px; color: var(--el-text-color-secondary); }
.hint summary { cursor: pointer; font-weight: 500; }
.hint ul { padding-left: 20px; margin-top: 8px; line-height: 1.7; }
</style>
