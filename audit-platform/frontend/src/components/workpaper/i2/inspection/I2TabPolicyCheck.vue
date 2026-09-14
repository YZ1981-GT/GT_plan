<template>
  <div class="i2-tab-policy-check">
    <div class="section-header">
      <span class="section-title">I2-4 会计政策检查</span>
      <div class="section-actions">
        <el-button size="small" type="default" text @click="handleReview">复核</el-button>
      </div>
    </div>

    <!-- 一、审计目标 -->
    <el-alert type="info" :closable="false" show-icon class="objective-alert">
      <template #title>一、审计目标</template>
      确认与研发费用/开发支出有关的金额及其他数据已恰当记录，相关披露已得到恰当计量和描述；
      评价会计政策是否符合企业会计准则、是否反映业务实际，并与同行业及前期一贯比较。
    </el-alert>

    <div class="methodology-context">
      <p>
        <b>编制逻辑：</b>访谈管理层了解业务与研发模式 → 核验立项/实验/结题等流程资料 →
        对照 CAS6 评价资本化与归集政策 → 同业对标 → 形成合理性分析与结论。
        资本化五条件的项目级判断见
        <el-button size="small" type="primary" link @click="emit('navigate-sheet', 'I2-6')">I2-6</el-button>。
      </p>
      <p>
        <b>研究 vs 开发（CAS6）：</b>研究阶段支出全部费用化；开发阶段满足五条件方可资本化；
        无法区分时全部费用化。研发费用应从开发支出贷方转出，不宜直接列支损益。
      </p>
    </div>

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <GtIndexChip value="wp:I2" :context-project-id="props.projectId" />
        <GtIndexChip value="wp:I2-6" :context-project-id="props.projectId" />
        <el-tag size="small" :type="completeness.ok ? 'success' : 'warning'">
          完成度 {{ completeness.progress }}%
        </el-tag>
        <el-tag size="small" type="info">CAS 段落 {{ casCompletedCount }}/{{ casItems.length }}</el-tag>
      </div>
      <div class="toolbar-right">
        <el-select
          v-if="!isReadonly"
          placeholder="同业行业模板"
          size="small"
          clearable
          style="width: 140px"
          @change="(id: string) => id && handleApplyIndustry(id)"
        >
          <el-option
            v-for="t in I2_INDUSTRY_PEER_TEMPLATES"
            :key="t.id"
            :label="t.label"
            :value="t.id"
          />
        </el-select>
        <el-button size="small" :disabled="isReadonly" @click="handleSyncProjects">带入I2-7项目</el-button>
        <el-button size="small" @click="emit('navigate-sheet', 'I2-3')">← I2-3</el-button>
        <el-button size="small" @click="emit('navigate-sheet', 'I2-5')">I2-5 →</el-button>
        <el-button size="small" type="success" :disabled="isReadonly" @click="handleSave">保存</el-button>
      </div>
    </div>

    <div class="guide-area">
      <div class="guide-grid">
        <div class="guide-step"><span class="step-num">①</span> 访谈管理层</div>
        <div class="guide-step"><span class="step-num">②</span> 核验研发流程资料</div>
        <div class="guide-step"><span class="step-num">③</span> CAS6 政策段落评价</div>
        <div class="guide-step"><span class="step-num">④</span> 同业对比 + 合理性结论</div>
      </div>
    </div>

    <!-- 完成度闸门 -->
    <el-card shadow="never" class="gate-card" :class="{ 'gate-ok': completeness.ok }">
      <template #header>
        <div class="block-title">
          <span>完成度闸门</span>
          <el-tag :type="completeness.ok ? 'success' : 'danger'" size="small">
            {{ completeness.ok ? '可关闭本检查项' : '未达标' }}
          </el-tag>
        </div>
      </template>
      <el-progress :percentage="completeness.progress" :stroke-width="10" style="margin-bottom:10px" />
      <div class="gate-list">
        <div v-for="c in completeness.items" :key="c.id" class="gate-item" :class="{ ok: c.ok }">
          <span>{{ c.ok ? '✓' : '○' }} {{ c.label }}</span>
          <span class="gate-hint">{{ c.hint }}</span>
        </div>
      </div>
    </el-card>

    <!-- 二、审计过程 -->
    <div class="section-label">二、审计过程</div>

    <!-- (0) 访谈 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <span class="block-title-text">1. 访谈管理层 — 了解业务类型、研发项目流程与模式</span>
      </template>
      <el-descriptions :column="2" border size="small">
        <el-descriptions-item label="访谈对象">
          <el-input v-if="!isReadonly" v-model="interview.interviewee" size="small" placeholder="姓名/职务" />
          <span v-else>{{ interview.interviewee || '—' }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="访谈日期">
          <el-date-picker
            v-if="!isReadonly"
            v-model="interview.interviewDate"
            type="date"
            size="small"
            value-format="YYYY-MM-DD"
            style="width:100%"
          />
          <span v-else>{{ interview.interviewDate || '—' }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="业务类型">
          <el-input v-if="!isReadonly" v-model="interview.businessTypes" size="small" placeholder="如：软件产品 / 医药研发…" />
          <span v-else>{{ interview.businessTypes || '—' }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="研发模式">
          <el-input v-if="!isReadonly" v-model="interview.rdModel" size="small" placeholder="自主 / 委外 / 合作…" />
          <span v-else>{{ interview.rdModel || '—' }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="与前期政策是否一致" :span="2">
          <el-radio-group v-if="!isReadonly" v-model="interview.consistencyWithPrior">
            <el-radio value="是">是</el-radio>
            <el-radio value="否">否</el-radio>
            <el-radio value="不适用">不适用</el-radio>
          </el-radio-group>
          <span v-else>{{ interview.consistencyWithPrior || '—' }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="研发项目流程摘要" :span="2">
          <el-input
            v-if="!isReadonly"
            v-model="interview.rdProcessSummary"
            type="textarea"
            :autosize="{ minRows: 2, maxRows: 5 }"
            placeholder="简述立项→研发→验收/结题流程，以及资本化时点如何确定…"
          />
          <span v-else>{{ interview.rdProcessSummary || '—' }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="访谈记录/其他" :span="2">
          <el-input
            v-if="!isReadonly"
            v-model="interview.notes"
            type="textarea"
            :autosize="{ minRows: 2, maxRows: 4 }"
            placeholder="关键答复、异常关注点…"
          />
          <span v-else>{{ interview.notes || '—' }}</span>
        </el-descriptions-item>
      </el-descriptions>
    </el-card>

    <!-- (1) 研发流程 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="block-title">
          <span>（1）研发流程 — 资料获取与核验</span>
          <el-tag size="small" type="info">要素可按实际情况增减</el-tag>
        </div>
      </template>
      <el-table :data="processItems" border size="small" class="process-table">
        <el-table-column type="index" label="#" width="40" align="center" />
        <el-table-column prop="label" label="检查要素" min-width="180" />
        <el-table-column label="检查结果" width="160" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.status" size="small" clearable placeholder="选择" style="width:100%">
              <el-option label="是（已获取/已检查）" value="是" />
              <el-option label="否（缺失/未获取）" value="否" />
              <el-option label="不适用" value="不适用" />
              <el-option label="未检查" value="未检查" />
            </el-select>
            <el-tag v-else :type="processStatusType(row.status)" size="small">{{ row.status || '—' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="查阅情况说明" min-width="200">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.evidence" size="small" placeholder="文件名称/关键发现" />
            <span v-else>{{ row.evidence || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="索引号" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.indexRef" size="small" />
            <span v-else>{{ row.indexRef || '—' }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- (2) 会计政策 CAS 段落 -->
    <div class="sub-label">（2）会计政策 — CAS6 相关条款评价</div>
    <el-card
      v-for="(item, idx) in casItems"
      :key="item.key"
      shadow="never"
      class="check-card"
      :class="{ 'check-card-done': item.conclusion === '是' || item.conclusion === '不适用' }"
    >
      <template #header>
        <div class="card-title-row">
          <span class="check-title">{{ idx + 1 }}. {{ item.label }}</span>
          <el-tag v-if="item.conclusion" :type="conclusionTagType(item.conclusion)" size="small">
            {{ item.conclusion === '是' ? '符合' : item.conclusion === '否' ? '不符合' : item.conclusion }}
          </el-tag>
        </div>
      </template>

      <details class="cas-reference">
        <summary>{{ item.casRef.slice(0, 48) }}…（展开准则依据）</summary>
        <p>{{ item.casRef }}</p>
      </details>

      <div class="field-group">
        <label>被审计单位实际政策：</label>
        <el-input
          v-model="item.actualPolicy"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 5 }"
          :disabled="isReadonly"
          placeholder="描述被审计单位就此方面的实际会计政策（归集、资本化时点、工时分摊、高新/加计扣除等）…"
        />
      </div>
      <div class="field-group">
        <label>审计师评价：</label>
        <el-input
          v-model="item.evaluation"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 5 }"
          :disabled="isReadonly"
          placeholder="评价是否符合准则、是否符合研发业务特点及行业惯例…"
        />
      </div>
      <div class="field-group conclusion-group">
        <label>结论：</label>
        <el-radio-group v-model="item.conclusion" :disabled="isReadonly">
          <el-radio value="是">符合</el-radio>
          <el-radio value="否">不符合</el-radio>
          <el-radio value="不适用">不适用</el-radio>
        </el-radio-group>
      </div>
      <div v-if="item.conclusion === '否'" class="field-group n-explanation">
        <label>不符合原因及影响：</label>
        <el-input
          v-model="item.explanationIfNo"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 4 }"
          :disabled="isReadonly"
          placeholder="必须说明不符合准则的具体原因和对审计的潜在影响…"
        />
        <el-alert v-if="!item.explanationIfNo" type="error" :closable="false" show-icon>
          结论为「不符合」时必须填写原因说明
        </el-alert>
        <el-button
          v-if="!isReadonly"
          size="small"
          type="warning"
          plain
          style="margin-top:8px"
          @click="handleDraftAje(item)"
        >
          生成 AJE 草稿 → I2-3
        </el-button>
      </div>
    </el-card>

    <!-- (2) 同行业 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="block-title">
          <span>（2）续 — 同行业相关政策</span>
          <el-button size="small" type="primary" plain :disabled="isReadonly" @click="addPeerRow">+ 同业公司</el-button>
        </div>
      </template>
      <el-table :data="peerRows" border size="small">
        <el-table-column type="index" label="#" width="40" />
        <el-table-column label="同业公司" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.companyName" size="small" placeholder="公司简称" />
            <span v-else>{{ row.companyName || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="资料来源" min-width="110">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.source" size="small" placeholder="年报/招股书…" />
            <span v-else>{{ row.source || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="资本化政策要点" min-width="160">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.capitalizationPolicy" size="small" />
            <span v-else>{{ row.capitalizationPolicy || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="费用归集要点" min-width="140">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.costAggregation" size="small" />
            <span v-else>{{ row.costAggregation || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="工时/人员分摊" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.staffAllocation" size="small" />
            <span v-else>{{ row.staffAllocation || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="备注" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.remark" size="small" />
            <span v-else>{{ row.remark || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="" width="56" align="center">
          <template #default="{ row }">
            <el-button size="small" type="danger" text @click="removePeerRow(row.rowId)">删</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- (3) 合理性分析 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="block-title">
          <span>（3）合理性分析</span>
          <el-button size="small" :disabled="isReadonly" @click="applyReasonNarrativeToNote">写入审计说明</el-button>
        </div>
      </template>
      <el-descriptions :column="2" border size="small">
        <el-descriptions-item label="检查的研发项目">
          <el-input
            v-if="!isReadonly"
            v-model="reasonableness.inspectedProjects"
            size="small"
            placeholder="项目名称或索引，如：项目A、B / I2-6"
          />
          <span v-else>{{ reasonableness.inspectedProjects || '—' }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="政策主题">
          <el-input v-if="!isReadonly" v-model="reasonableness.policyTopic" size="small" />
          <span v-else>{{ reasonableness.policyTopic || '—' }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="是否合理">
          <el-radio-group v-if="!isReadonly" v-model="reasonableness.isReasonable">
            <el-radio value="是">合理</el-radio>
            <el-radio value="否">不合理</el-radio>
            <el-radio value="不适用">不适用</el-radio>
          </el-radio-group>
          <span v-else>{{ reasonableness.isReasonable || '—' }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="理由" :span="2">
          <el-input
            v-if="!isReadonly"
            v-model="reasonableness.reasons"
            type="textarea"
            :autosize="{ minRows: 3, maxRows: 6 }"
            placeholder="①……；②……；③……"
          />
          <span v-else>{{ reasonableness.reasons || '—' }}</span>
        </el-descriptions-item>
      </el-descriptions>
      <div class="narrative-preview">
        <span class="narrative-label">叙述预览：</span>
        <span>{{ reasonNarrative }}</span>
      </div>
    </el-card>

    <!-- 三、审计说明 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header><span>三、审计说明</span></template>
      <el-input
        type="textarea"
        :model-value="auditNote"
        :disabled="isReadonly"
        :autosize="{ minRows: 5 }"
        placeholder="记录访谈要点、流程核验发现、政策差异及处理…"
        @change="saveAuditNote"
      />
    </el-card>

    <!-- 四、审计结论 -->
    <el-card shadow="never" class="audit-conclusion-card">
      <template #header>
        <div class="block-title">
          <span>四、审计结论</span>
          <el-button size="small" :disabled="isReadonly" @click="applyDefaultConclusion">填入模板结论</el-button>
        </div>
      </template>
      <el-input
        type="textarea"
        :model-value="auditConclusion"
        :disabled="isReadonly"
        :autosize="{ minRows: 3 }"
        placeholder="被审计单位研发费用/开发支出会计政策和会计估计与企业会计准则的规定一致…"
        @change="saveAuditConclusion"
      />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { toRef, inject } from 'vue'
import { ElMessage } from 'element-plus'
import GtIndexChip from '../../GtIndexChip.vue'
import { useI2PolicyCheck } from '../../composables/useI2PolicyCheck'
import { I2_INDUSTRY_PEER_TEMPLATES } from '../../composables/i2EnhancementHelpers'
import type { I2PolicyCasItem } from '../../composables/i2PolicyCheckModel'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  saveResponse: (sheetCode: string, data: Record<string, any>) => Promise<void>
  isReadonly?: boolean
}>()

const emit = defineEmits<{
  save: []
  'navigate-sheet': [sheetName: string]
}>()

const openReviewDialog = inject<(section: string) => void>('openReviewDialog', () => {})

const {
  interview,
  processItems,
  casItems,
  peerRows,
  reasonableness,
  auditNote,
  auditConclusion,
  completeness,
  reasonNarrative,
  casCompletedCount,
  addPeerRow,
  removePeerRow,
  applyDefaultConclusion,
  applyReasonNarrativeToNote,
  applyIndustryTemplate,
  syncProjectsFromI27,
  draftAjeFromCasNo,
  persistAll,
  saveAuditNote,
  saveAuditConclusion,
} = useI2PolicyCheck(toRef(props, 'allResponses'), { saveResponse: props.saveResponse })

async function handleSave() {
  if (props.isReadonly) return
  await persistAll()
  emit('save')
  ElMessage.success('会计政策检查已保存')
}

function handleApplyIndustry(id: string) {
  const r = applyIndustryTemplate(id)
  if (r.ok) ElMessage.success(r.message)
  else ElMessage.warning(r.message)
}

function handleSyncProjects() {
  const r = syncProjectsFromI27()
  if (r.ok) ElMessage.success(r.message)
  else ElMessage.warning(r.message)
}

async function handleDraftAje(item: I2PolicyCasItem) {
  const r = await draftAjeFromCasNo(item)
  if (r.ok) {
    ElMessage.success(r.message)
    emit('navigate-sheet', 'I2-3')
  } else {
    ElMessage.warning(r.message)
  }
}

function handleReview() {
  openReviewDialog('I2-4-会计政策检查')
}

function conclusionTagType(conclusion: string): 'success' | 'danger' | 'info' {
  if (conclusion === '是') return 'success'
  if (conclusion === '否') return 'danger'
  return 'info'
}

function processStatusType(status: string): 'success' | 'danger' | 'info' | 'warning' {
  if (status === '是') return 'success'
  if (status === '否') return 'danger'
  if (status === '未检查') return 'warning'
  return 'info'
}
</script>

<style scoped>
.i2-tab-policy-check { padding: 16px; font-size: var(--wp-font-size, 13px); }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-title { font-size: 15px; font-weight: 600; color: #1f2937; }
.section-actions { display: flex; align-items: center; gap: 4px; }
.objective-alert { margin-bottom: 12px; }
.methodology-context {
  border-left: 4px solid #d97706; background: #fffbeb; padding: 10px 14px;
  margin-bottom: 14px; border-radius: 4px; font-size: 12px; color: #92400e; line-height: 1.7;
}
.methodology-context p { margin: 0 0 4px; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; gap: 8px; flex-wrap: wrap; }
.toolbar-left, .toolbar-right { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.guide-area { margin-bottom: 12px; padding: 10px 12px; background: #f0f9eb; border: 1px solid #e1f3d8; border-radius: 6px; }
.guide-grid { display: flex; flex-wrap: wrap; gap: 10px 16px; }
.guide-step { font-size: 12px; color: #529b2e; }
.step-num {
  display: inline-flex; align-items: center; justify-content: center;
  width: 18px; height: 18px; border-radius: 50%; background: #67c23a; color: #fff;
  font-size: 11px; margin-right: 4px;
}
.gate-card { margin-bottom: 14px; }
.gate-card.gate-ok { border-left: 3px solid var(--el-color-success); }
.gate-list { display: flex; flex-direction: column; gap: 6px; }
.gate-item { display: flex; justify-content: space-between; gap: 12px; font-size: 12px; color: #6b7280; }
.gate-item.ok { color: #059669; }
.gate-hint { color: #9ca3af; }
.section-label { font-size: 14px; font-weight: 700; color: #1f2937; margin: 8px 0 10px; }
.sub-label { font-size: 13px; font-weight: 600; color: #374151; margin: 4px 0 10px; }
.block-card { margin-bottom: 14px; }
.block-card :deep(.el-card__header) { padding: 10px 16px; background: #fafafa; }
.block-title { display: flex; align-items: center; justify-content: space-between; gap: 8px; flex-wrap: wrap; font-weight: 600; }
.block-title-text { font-weight: 600; }
.check-card { margin-bottom: 12px; }
.check-card-done { border-left: 3px solid var(--el-color-success); }
.card-title-row { display: flex; align-items: center; justify-content: space-between; }
.check-title { font-weight: 600; color: #374151; }
.cas-reference {
  margin-bottom: 12px; padding: 8px 12px; background: var(--el-fill-color-light);
  border-radius: 4px; font-size: 12px; color: var(--el-text-color-secondary); line-height: 1.5;
}
.cas-reference summary { cursor: pointer; font-weight: 500; }
.cas-reference p { margin: 8px 0 0; }
.field-group { margin-bottom: 12px; }
.field-group label { display: block; font-weight: 500; margin-bottom: 4px; }
.conclusion-group { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.n-explanation { border-left: 3px solid var(--el-color-danger); padding-left: 12px; }
.process-table { font-size: var(--wp-font-size, 13px); }
.narrative-preview {
  margin-top: 10px; padding: 10px 12px; background: #f8fafc; border: 1px dashed #cbd5e1;
  border-radius: 6px; font-size: 12px; color: #475569; line-height: 1.7;
}
.narrative-label { font-weight: 600; color: #334155; margin-right: 6px; }
.audit-note-card, .audit-conclusion-card { margin-top: 14px; }
</style>
