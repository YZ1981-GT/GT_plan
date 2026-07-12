<!--
  I3TabTargetedCheck.vue — I3-5 针对性检查表

  段落型检查（非表格）：减值迹象识别 / 商誉分摊合理性 / CGU划分一致性
  - 逐项结论(合理/不合理/需调整/待确认) + 琥珀色方法论
  - Section headers with AI buttons aligned right
  - 复核对话 button (inject openReviewDialog)
  - Font 13px

  3 Main Check Sections:
  1. 减值迹象识别 — 外部迹象(市场/技术/经济/利率) + 内部迹象(经营/报告/重组/决策)
  2. 商誉分摊至资产组(CGU)合理性 — 合并对价分配/协同效应/管理层考虑
  3. CGU划分一致性 — 与上年一致性/与管理层内部报告一致性/是否变更

  Spec: .kiro/specs/i3-goodwill/ Task 4.6
  Requirements: 8.1~8.2
-->
<template>
  <div class="i3-targeted-check">
    <!-- Section Header -->
    <div class="section-header">
      <span class="section-title">I3-5 针对性检查表</span>
      <div class="section-actions">
        <el-button size="small" type="primary" text @click="handleAiAssist">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <el-button size="small" type="default" text @click="handleReview">
          💬复核
        </el-button>
      </div>
    </div>

    <!-- 琥珀色方法论上下文 -->
    <div class="methodology-context">
      <p><strong>CAS8第六条 减值迹象规定：</strong>企业应当在资产负债表日判断资产是否存在可能发生减值的迹象。
      因企业合并所形成的商誉，无论是否存在减值迹象，每年都应当进行减值测试。
      减值迹象包括外部信息来源（市价大幅下跌、经济技术法律环境不利变化、市场利率提高、
      净资产账面价值大于市值）和内部信息来源（资产闲置终止或提前处置、经济绩效低于预期、
      资产组重组或业务处置计划）。含商誉的资产组应按CAS8第十八条进行年度减值测试，
      商誉不摊销，减值后不可转回。</p>
    </div>

    <!-- Section 1: 减值迹象识别 -->
    <el-card class="check-section" shadow="never">
      <template #header>
        <div class="check-section-header">
          <span class="check-section-title">一、减值迹象识别</span>
          <el-button size="small" type="primary" text @click="handleAiSection('impairmentIndicators')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <div class="check-section-body">
        <!-- 1.1 外部迹象 -->
        <div class="check-item">
          <div class="check-item-title">1.1 外部迹象检查（市场/技术/经济/利率）</div>
          <el-input
            v-model="sections.externalIndicators"
            type="textarea"
            :autosize="{ minRows: 4, maxRows: 12 }"
            :disabled="isReadonly"
            placeholder="请逐条检查以下外部减值迹象：&#10;① 资产的市价在当期是否大幅下跌，其跌幅明显高于因时间推移或正常使用而预计的下跌&#10;② 企业经营所处的经济、技术或法律等环境以及资产所处的市场在当期或将在近期发生重大变化，从而对企业产生不利影响&#10;③ 市场利率或者其他市场投资报酬率在当期已经提高，从而影响折现率，导致资产可收回金额大幅降低&#10;④ 有证据表明资产已经陈旧过时或其实体已经损坏&#10;⑤ 被收购方所在行业是否发生重大不利变化"
          />
          <div class="conclusion-row">
            <span class="conclusion-label">结论：</span>
            <el-select v-model="conclusions.externalIndicators" size="small" :disabled="isReadonly" placeholder="选择结论" style="width:180px">
              <el-option label="无减值迹象" value="无减值迹象" />
              <el-option label="存在减值迹象" value="存在减值迹象" />
              <el-option label="需进一步判断" value="需进一步判断" />
              <el-option label="待确认" value="待确认" />
            </el-select>
            <el-input
              v-model="remarks.externalIndicators"
              size="small"
              :disabled="isReadonly"
              placeholder="备注"
              style="flex:1;margin-left:12px"
            />
          </div>
        </div>
        <!-- 1.2 内部迹象 -->
        <div class="check-item">
          <div class="check-item-title">1.2 内部迹象检查（经营/报告/重组/决策）</div>
          <el-input
            v-model="sections.internalIndicators"
            type="textarea"
            :autosize="{ minRows: 4, maxRows: 12 }"
            :disabled="isReadonly"
            placeholder="请逐条检查以下内部减值迹象：&#10;① 有证据表明资产已经或将被闲置、终止使用或者计划提前处置&#10;② 企业内部报告的证据表明资产的经济绩效已经低于或者将低于预期（如经营现金流量或营业利润远低于预算）&#10;③ 资产所属的资产组或资产组组合存在重组或业务处置计划&#10;④ 被收购业务实际经营利润是否持续低于并购时的预期&#10;⑤ 管理层是否有证据表明即将出现的变化将对商誉产生不利影响"
          />
          <div class="conclusion-row">
            <span class="conclusion-label">结论：</span>
            <el-select v-model="conclusions.internalIndicators" size="small" :disabled="isReadonly" placeholder="选择结论" style="width:180px">
              <el-option label="无减值迹象" value="无减值迹象" />
              <el-option label="存在减值迹象" value="存在减值迹象" />
              <el-option label="需进一步判断" value="需进一步判断" />
              <el-option label="待确认" value="待确认" />
            </el-select>
            <el-input
              v-model="remarks.internalIndicators"
              size="small"
              :disabled="isReadonly"
              placeholder="备注"
              style="flex:1;margin-left:12px"
            />
          </div>
        </div>
      </div>
    </el-card>

    <!-- Section 2: 商誉分摊至资产组(CGU)合理性 -->
    <el-card class="check-section" shadow="never">
      <template #header>
        <div class="check-section-header">
          <span class="check-section-title">二、商誉分摊至资产组(CGU)合理性</span>
          <el-button size="small" type="primary" text @click="handleAiSection('cguAllocation')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <div class="check-section-body">
        <!-- 2.1 合并对价分摊 -->
        <div class="check-item">
          <div class="check-item-title">2.1 合并对价与商誉初始分摊</div>
          <el-input
            v-model="sections.mergerCostAllocation"
            type="textarea"
            :autosize="{ minRows: 3, maxRows: 10 }"
            :disabled="isReadonly"
            placeholder="请检查：&#10;① 商誉是否已在购买日分摊至预期从企业合并中受益的资产组或资产组组合&#10;② 分摊商誉的资产组或组合是否为企业内部管理目的监控商誉的最低水平&#10;③ 分摊商誉的资产组或组合是否不大于CAS35确定的经营分部&#10;④ 合并对价中可辨认净资产公允价值的计量是否充分"
          />
          <div class="conclusion-row">
            <span class="conclusion-label">结论：</span>
            <el-select v-model="conclusions.mergerCostAllocation" size="small" :disabled="isReadonly" placeholder="选择结论" style="width:180px">
              <el-option label="合理" value="合理" />
              <el-option label="不合理" value="不合理" />
              <el-option label="需调整" value="需调整" />
              <el-option label="待确认" value="待确认" />
            </el-select>
            <el-input
              v-model="remarks.mergerCostAllocation"
              size="small"
              :disabled="isReadonly"
              placeholder="备注"
              style="flex:1;margin-left:12px"
            />
          </div>
        </div>
        <!-- 2.2 协同效应 -->
        <div class="check-item">
          <div class="check-item-title">2.2 协同效应考虑</div>
          <el-input
            v-model="sections.synergyEffect"
            type="textarea"
            :autosize="{ minRows: 3, maxRows: 10 }"
            :disabled="isReadonly"
            placeholder="请检查：&#10;① 商誉分摊是否反映了企业合并所产生的协同效应归属于哪些资产组&#10;② 预期协同效应是否合理、有据可查（收入协同/成本协同/管理协同）&#10;③ 管理层对协同效应的量化是否在合理范围内&#10;④ 协同效应是否已在DCF预测中充分反映"
          />
          <div class="conclusion-row">
            <span class="conclusion-label">结论：</span>
            <el-select v-model="conclusions.synergyEffect" size="small" :disabled="isReadonly" placeholder="选择结论" style="width:180px">
              <el-option label="合理" value="合理" />
              <el-option label="不合理" value="不合理" />
              <el-option label="需调整" value="需调整" />
              <el-option label="待确认" value="待确认" />
            </el-select>
            <el-input
              v-model="remarks.synergyEffect"
              size="small"
              :disabled="isReadonly"
              placeholder="备注"
              style="flex:1;margin-left:12px"
            />
          </div>
        </div>
        <!-- 2.3 管理层考虑 -->
        <div class="check-item">
          <div class="check-item-title">2.3 管理层内部监控依据</div>
          <el-input
            v-model="sections.managementBasis"
            type="textarea"
            :autosize="{ minRows: 3, maxRows: 10 }"
            :disabled="isReadonly"
            placeholder="请检查：&#10;① 管理层内部报告是否按对应资产组/组合监控商誉绩效&#10;② 分摊层级是否与管理层监控商誉的最低层级一致&#10;③ 是否存在未分摊至资产组的商誉（若有需说明原因和后续计划）&#10;④ 管理层监控频率和方式是否适当"
          />
          <div class="conclusion-row">
            <span class="conclusion-label">结论：</span>
            <el-select v-model="conclusions.managementBasis" size="small" :disabled="isReadonly" placeholder="选择结论" style="width:180px">
              <el-option label="合理" value="合理" />
              <el-option label="不合理" value="不合理" />
              <el-option label="需调整" value="需调整" />
              <el-option label="待确认" value="待确认" />
            </el-select>
            <el-input
              v-model="remarks.managementBasis"
              size="small"
              :disabled="isReadonly"
              placeholder="备注"
              style="flex:1;margin-left:12px"
            />
          </div>
        </div>
      </div>
    </el-card>

    <!-- Section 3: CGU划分一致性 -->
    <el-card class="check-section" shadow="never">
      <template #header>
        <div class="check-section-header">
          <span class="check-section-title">三、CGU划分一致性</span>
          <el-button size="small" type="primary" text @click="handleAiSection('cguConsistency')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <div class="check-section-body">
        <!-- 3.1 与上年一致性 -->
        <div class="check-item">
          <div class="check-item-title">3.1 与上年CGU划分一致性</div>
          <el-input
            v-model="sections.priorYearConsistency"
            type="textarea"
            :autosize="{ minRows: 3, maxRows: 10 }"
            :disabled="isReadonly"
            placeholder="请检查：&#10;① 本年CGU划分是否与上年保持一致&#10;② 若发生变化，变化原因是否合理（业务重组/资产处置/新并购整合）&#10;③ 变化是否已按CAS8第十九条要求进行了追溯调整和充分披露&#10;④ 变更前后减值测试结论是否存在重大差异"
          />
          <div class="conclusion-row">
            <span class="conclusion-label">结论：</span>
            <el-select v-model="conclusions.priorYearConsistency" size="small" :disabled="isReadonly" placeholder="选择结论" style="width:180px">
              <el-option label="一致" value="一致" />
              <el-option label="不一致但合理" value="不一致但合理" />
              <el-option label="不一致且不合理" value="不一致且不合理" />
              <el-option label="待确认" value="待确认" />
            </el-select>
            <el-input
              v-model="remarks.priorYearConsistency"
              size="small"
              :disabled="isReadonly"
              placeholder="备注"
              style="flex:1;margin-left:12px"
            />
          </div>
        </div>
        <!-- 3.2 与管理层内部报告一致性 -->
        <div class="check-item">
          <div class="check-item-title">3.2 与管理层内部报告一致性</div>
          <el-input
            v-model="sections.internalReportConsistency"
            type="textarea"
            :autosize="{ minRows: 3, maxRows: 10 }"
            :disabled="isReadonly"
            placeholder="请检查：&#10;① CGU划分是否与管理层内部报告/绩效评价的报告单元一致&#10;② 是否存在CGU跨经营分部的情况（若有需特别说明合理性）&#10;③ 合并报告层面与子公司层面的CGU划分是否协调一致&#10;④ 管理层内部KPI考核单元是否与CGU划分逻辑吻合"
          />
          <div class="conclusion-row">
            <span class="conclusion-label">结论：</span>
            <el-select v-model="conclusions.internalReportConsistency" size="small" :disabled="isReadonly" placeholder="选择结论" style="width:180px">
              <el-option label="一致" value="一致" />
              <el-option label="不一致但合理" value="不一致但合理" />
              <el-option label="不一致且不合理" value="不一致且不合理" />
              <el-option label="待确认" value="待确认" />
            </el-select>
            <el-input
              v-model="remarks.internalReportConsistency"
              size="small"
              :disabled="isReadonly"
              placeholder="备注"
              style="flex:1;margin-left:12px"
            />
          </div>
        </div>
        <!-- 3.3 是否变更 -->
        <div class="check-item">
          <div class="check-item-title">3.3 CGU划分变更情况</div>
          <el-input
            v-model="sections.cguChangeStatus"
            type="textarea"
            :autosize="{ minRows: 3, maxRows: 10 }"
            :disabled="isReadonly"
            placeholder="请检查：&#10;① 本年是否存在CGU划分的变更&#10;② 变更原因是否经管理层正式批准并有书面依据&#10;③ 变更对商誉减值测试结论的影响程度（敏感性分析）&#10;④ 变更是否在财务报表附注中充分披露"
          />
          <div class="conclusion-row">
            <span class="conclusion-label">结论：</span>
            <el-select v-model="conclusions.cguChangeStatus" size="small" :disabled="isReadonly" placeholder="选择结论" style="width:180px">
              <el-option label="无变更" value="无变更" />
              <el-option label="有变更且合理" value="有变更且合理" />
              <el-option label="有变更但不合理" value="有变更但不合理" />
              <el-option label="待确认" value="待确认" />
            </el-select>
            <el-input
              v-model="remarks.cguChangeStatus"
              size="small"
              :disabled="isReadonly"
              placeholder="备注"
              style="flex:1;margin-left:12px"
            />
          </div>
        </div>
      </div>
    </el-card>

    <!-- 综合检查结论 -->
    <el-card class="overall-conclusion" shadow="never">
      <template #header>
        <span style="font-weight:600">综合检查结论</span>
      </template>
      <el-input
        v-model="overallConclusion"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="综合以上针对性检查结果，说明：&#10;1. 是否存在减值迹象（结合I3-6减值测试结果）&#10;2. 商誉分摊至CGU是否合理&#10;3. CGU划分是否一致、合规&#10;4. 后续跟进事项（若有）"
      />
    </el-card>

    <!-- 保存 -->
    <div class="table-actions" v-if="!isReadonly">
      <el-button size="small" type="success" @click="handleSave">保存</el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, inject, reactive } from 'vue'
import { ElMessage } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import http from '@/utils/http'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'save', itemId: string, value: any): void
  (e: 'navigate-sheet', sheetName: string): void
}>()

const openReviewDialog = inject<(section: string) => void>('openReviewDialog', () => {})

const STORAGE_KEY = 'I3-5-targeted'

// --- Sections: textarea内容 ---
const sections = reactive({
  externalIndicators: '',
  internalIndicators: '',
  mergerCostAllocation: '',
  synergyEffect: '',
  managementBasis: '',
  priorYearConsistency: '',
  internalReportConsistency: '',
  cguChangeStatus: '',
})

// --- Conclusions: 逐项结论 ---
const conclusions = reactive({
  externalIndicators: '',
  internalIndicators: '',
  mergerCostAllocation: '',
  synergyEffect: '',
  managementBasis: '',
  priorYearConsistency: '',
  internalReportConsistency: '',
  cguChangeStatus: '',
})

// --- Remarks: 备注 ---
const remarks = reactive({
  externalIndicators: '',
  internalIndicators: '',
  mergerCostAllocation: '',
  synergyEffect: '',
  managementBasis: '',
  priorYearConsistency: '',
  internalReportConsistency: '',
  cguChangeStatus: '',
})

const overallConclusion = ref('')

// --- Load/Save ---
function loadData() {
  const raw = props.allResponses.get(STORAGE_KEY)
  if (!raw) return
  try {
    const parsed = typeof raw === 'string' ? JSON.parse(raw) : (raw.remark ? JSON.parse(raw.remark) : raw)
    if (parsed) {
      Object.keys(sections).forEach((k) => {
        if (parsed.sections?.[k]) (sections as any)[k] = parsed.sections[k]
      })
      Object.keys(conclusions).forEach((k) => {
        if (parsed.conclusions?.[k]) (conclusions as any)[k] = parsed.conclusions[k]
      })
      Object.keys(remarks).forEach((k) => {
        if (parsed.remarks?.[k]) (remarks as any)[k] = parsed.remarks[k]
      })
      overallConclusion.value = parsed.overallConclusion || ''
    }
  } catch { /* ignore parse errors */ }
}

watch(() => props.allResponses, () => loadData(), { immediate: true })

async function handleSave() {
  const payload = {
    sections: { ...sections },
    conclusions: { ...conclusions },
    remarks: { ...remarks },
    overallConclusion: overallConclusion.value,
  }
  emit('save', STORAGE_KEY, JSON.stringify(payload))
  ElMessage.success('针对性检查表已保存')
}

// --- AI辅助 ---
async function handleAiAssist() {
  try {
    const res = await http.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section: 'I3-5-targeted-all',
      prompt: '商誉针对性检查表：请根据CAS8减值迹象识别要求，综合分析商誉减值迹象（外部+内部）、商誉分摊至CGU合理性、CGU划分一致性三大维度',
      context: JSON.stringify({ sections, conclusions }),
    })
    if (res.data?.data?.content) {
      ElMessage.success('AI内容已生成，请查看各检查项')
      applyAiResult(res.data.data.content, null)
    }
  } catch {
    ElMessage.warning('AI辅助暂不可用，请手动填写')
  }
}

async function handleAiSection(sectionKey: string) {
  const sectionNameMap: Record<string, string> = {
    impairmentIndicators: '减值迹象识别——外部迹象(市场/技术/经济/利率) + 内部迹象(经营/报告/重组/决策)',
    cguAllocation: '商誉分摊至资产组(CGU)合理性——合并对价分配/协同效应/管理层考虑',
    cguConsistency: 'CGU划分一致性——与上年一致性/与管理层内部报告一致性/是否变更',
  }
  try {
    const res = await http.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section: `I3-5-targeted-${sectionKey}`,
      prompt: `商誉针对性检查：${sectionNameMap[sectionKey] || sectionKey}`,
      context: JSON.stringify({ sections, conclusions }),
    })
    if (res.data?.data?.content) {
      applyAiResult(res.data.data.content, sectionKey)
      ElMessage.success('AI内容已生成')
    }
  } catch {
    ElMessage.warning('AI辅助暂不可用，请手动填写')
  }
}

function applyAiResult(content: string, targetSection: string | null) {
  if (targetSection === 'impairmentIndicators') {
    // 外部+内部合并写入外部（可人工分拆）
    sections.externalIndicators = content
  } else if (targetSection === 'cguAllocation') {
    sections.mergerCostAllocation = content
  } else if (targetSection === 'cguConsistency') {
    sections.priorYearConsistency = content
  }
  // 全量模式不自动填充（避免覆盖已有内容），只提示用户查看
}

// --- 复核对话 ---
function handleReview() {
  openReviewDialog('I3-5-针对性检查')
}
</script>

<style scoped>
.i3-targeted-check {
  font-size: var(--wp-font-size, 13px);
  padding: 16px;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.section-title {
  font-size: 15px;
  font-weight: 600;
  color: #1f2937;
}

.section-actions {
  display: flex;
  align-items: center;
  gap: 4px;
}

/* 琥珀色方法论上下文 — CAS8第六条 */
.methodology-context {
  background: #fffbeb;
  border-left: 4px solid #f59e0b;
  padding: 10px 14px;
  margin-bottom: 16px;
  border-radius: 4px;
  font-size: 12px;
  color: #92400e;
  line-height: 1.7;
}

.methodology-context p {
  margin: 0;
}

/* 检查卡片 */
.check-section {
  margin-bottom: 16px;
}

.check-section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.check-section-title {
  font-size: 14px;
  font-weight: 600;
  color: #374151;
}

.check-section-body {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* 检查项 */
.check-item {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.check-item-title {
  font-size: var(--wp-font-size, 13px);
  font-weight: 500;
  color: #4b5563;
}

.conclusion-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 4px;
}

.conclusion-label {
  font-weight: 500;
  color: #374151;
  white-space: nowrap;
  font-size: 12px;
}

/* 综合结论 */
.overall-conclusion {
  margin-top: 8px;
}

/* 保存 */
.table-actions {
  display: flex;
  gap: 8px;
  margin-top: 16px;
}
</style>
