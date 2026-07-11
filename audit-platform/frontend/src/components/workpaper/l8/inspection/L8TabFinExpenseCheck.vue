<template>
  <div class="l8-tab-fin-expense-check">
    <!-- ═══ 标题 + 操作栏 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">← 返回目录</el-button>
        <h3 class="section-title">L8-6 财务费用检查表</h3>
      </div>
      <div class="section-header-right">
        <el-button size="small" @click="handleReview">
          <el-icon><Check /></el-icon> 复核
        </el-button>
        <el-button type="primary" size="small" :loading="isSaving" @click="handleSave">
          保存
        </el-button>
      </div>
    </div>

    <!-- ═══ 审计目标 ═══ -->
    <el-alert type="info" :closable="false" show-icon style="margin-bottom: 12px">
      <template #title>
        <strong>审计目标：</strong>实质性检查财务费用各构成项目的完整、真实、合规与期间归属，核查利息资本化、汇兑损益、手续费及非金融机构利息税务合规性。
      </template>
    </el-alert>

    <!-- ═══ 方法论上下文 ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>财务费用实质性检查要点：</strong>
        ①利息支出完整性（与L1/L3/L4/L5测算核对）；②利息资本化合规性；
        ③汇兑损益合理性（外币报表折算一致）；④手续费真实性（银行对账单核对）；
        ⑤非金融机构利息税务合规（超标利息纳税调增）；⑥截止性（归属期间正确）。
      </div>
    </div>

    <!-- ═══ 检查项目清单 ═══ -->
    <div v-for="(section, sIdx) in checkSections" :key="section.id" class="check-section">
      <div class="check-section-header">
        <h4 class="check-section-title">{{ section.title }}</h4>
        <el-button size="small" @click="handleAI(section.id)">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
      </div>

      <el-table :data="section.items" border size="small" style="width: 100%">
        <el-table-column type="index" label="#" width="50" align="center" />
        <el-table-column label="检查内容" min-width="300">
          <template #default="{ row }">
            <span>{{ row.content }}</span>
          </template>
        </el-table-column>
        <el-table-column label="检查结论" width="160" align="center">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              :model-value="getCheckConclusion(section.id, row.key)"
              size="small"
              placeholder="选择"
              @change="(val: string) => setCheckConclusion(section.id, row.key, val)"
            >
              <el-option label="已核对无异常" value="pass" />
              <el-option label="存在异常" value="fail" />
              <el-option label="不适用" value="na" />
              <el-option label="待核实" value="pending" />
            </el-select>
            <el-tag v-else :type="getConclusionTag(getCheckConclusion(section.id, row.key))" size="small">
              {{ getConclusionLabel(getCheckConclusion(section.id, row.key)) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="备注/发现" min-width="200">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="getCheckRemark(section.id, row.key)"
              size="small"
              placeholder="检查发现"
              @change="(val: string) => setCheckRemark(section.id, row.key, val)"
            />
            <span v-else>{{ getCheckRemark(section.id, row.key) || '—' }}</span>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- ═══ 审计结论区（el-card包裹） ═══ -->
    <el-card shadow="never" class="conclusion-card">
      <template #header>
        <div class="section-header">
          <span class="card-title">审计结论</span>
          <el-button size="small" @click="handleAI('conclusion')">
            <el-icon><MagicStick /></el-icon> AI辅助
          </el-button>
        </div>
      </template>
      <el-input
        v-model="auditConclusion"
        type="textarea"
        :autosize="{ minRows: 4, maxRows: 10 }"
        placeholder="根据上述检查结果，对财务费用科目总体发表审计结论..."
        :disabled="isReadonly"
        @change="saveConclusion"
      />
    </el-card>

    <!-- ═══ 审计意见（el-card包裹） ═══ -->
    <el-card shadow="never" class="opinion-card">
      <template #header>
        <div class="section-header">
          <span class="card-title">审计意见</span>
          <el-button size="small" @click="handleAI('opinion')">
            <el-icon><MagicStick /></el-icon> AI辅助
          </el-button>
        </div>
      </template>
      <el-select
        v-model="auditOpinion"
        placeholder="选择审计意见"
        size="default"
        :disabled="isReadonly"
        style="width: 300px; margin-bottom: 12px"
        @change="saveOpinion"
      >
        <el-option label="审计程序充分，未发现重大错报" value="unqualified" />
        <el-option label="存在错报但已调整" value="adjusted" />
        <el-option label="存在未调整错报" value="unadjusted" />
        <el-option label="审计范围受限" value="limited" />
      </el-select>
      <el-input
        v-model="opinionNote"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 6 }"
        placeholder="补充说明..."
        :disabled="isReadonly"
        @change="saveOpinionNote"
      />
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="l8-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>逐项检查并选择结论（已核对无异常/存在异常/不适用/待核实）</li>
        <li>异常项必须填写备注说明具体发现</li>
        <li>结论应综合考虑各检查项目结果，保持与底稿其他sheet一致</li>
        <li>审计意见选择后需说明理由</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * L8TabFinExpenseCheck — L8-6 财务费用检查表
 *
 * Requirements: 7.1-7.5
 * - 多section检查清单（6大检查领域）
 * - 每section标题行有AI辅助按钮
 * - 结论区 + 审计意见区（el-card包裹）
 * - 下拉点选结论（减少手打）
 */
import { inject, onMounted, ref, reactive } from 'vue'
import { computed } from 'vue'
import { MagicStick, Check } from '@element-plus/icons-vue'
import { useL8FormData } from '../../composables/useL8FormData'

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate', sheetName: string): void
}>()

const openReviewDialog = inject<(sectionId: string, sectionLabel?: string) => void>('openReviewDialog', () => {})

// ─── FormData ────────────────────────────────────────────────────────────────

const formData = useL8FormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

// ─── 检查清单结构（6大section） ─────────────────────────────────────────────

interface CheckItem {
  key: string
  content: string
}

interface CheckSection {
  id: string
  title: string
  items: CheckItem[]
}

const checkSections: CheckSection[] = [
  {
    id: 'interest-completeness',
    title: '一、利息支出完整性',
    items: [
      { key: 'i1', content: '与L1短期借款利息测算核对，差异在可接受范围' },
      { key: 'i2', content: '与L3长期借款利息测算核对，差异在可接受范围' },
      { key: 'i3', content: '与L4应付债券利息费用核对，差异在可接受范围' },
      { key: 'i4', content: '与L5未确认融资费用摊销核对，差异在可接受范围' },
      { key: 'i5', content: '利息支出合计与明细表L8-2对应项目一致' },
    ],
  },
  {
    id: 'interest-capitalization',
    title: '二、利息资本化合规性',
    items: [
      { key: 'c1', content: '利息资本化对象为符合条件的资产（CAS17）' },
      { key: 'c2', content: '资本化金额计算正确（加权平均法/专门借款法）' },
      { key: 'c3', content: '资本化起止时间合规（开始/暂停/停止三条件）' },
    ],
  },
  {
    id: 'fx-reasonableness',
    title: '三、汇兑损益合理性',
    items: [
      { key: 'f1', content: '汇率使用合理（交易日即期/期末资产负债表日即期）' },
      { key: 'f2', content: '外币报表折算汇兑差异计入其他综合收益（非财务费用）' },
      { key: 'f3', content: '汇兑损益资本化部分符合CAS17资本化条件' },
    ],
  },
  {
    id: 'fee-authenticity',
    title: '四、手续费真实性',
    items: [
      { key: 'h1', content: '银行手续费与银行对账单核对一致' },
      { key: 'h2', content: '手续费收费标准合理（参照银行公示费率）' },
      { key: 'h3', content: '大额手续费（>重要性水平5%）已取得充分证据' },
    ],
  },
  {
    id: 'non-fin-tax',
    title: '五、非金融机构利息税务合规',
    items: [
      { key: 't1', content: '非金融机构借款已识别并列入L8-4测算表' },
      { key: 't2', content: '超标利息金额已确认，纳税调增已提示' },
      { key: 't3', content: '关联方借款利率符合独立交易原则' },
    ],
  },
  {
    id: 'cutoff',
    title: '六、截止性',
    items: [
      { key: 'ct1', content: '报告期前后±5天序时账已检查（L8-5截止测试）' },
      { key: 'ct2', content: '跨期入账费用已识别并评估错报影响' },
      { key: 'ct3', content: '跨期事项是否需要调整分录' },
    ],
  },
]

// ─── 检查数据（per section per item） ────────────────────────────────────────

const checkData = reactive<Record<string, { conclusion: string; remark: string }>>({})

function getCheckConclusion(sectionId: string, itemKey: string): string {
  return checkData[`${sectionId}-${itemKey}`]?.conclusion || ''
}

function setCheckConclusion(sectionId: string, itemKey: string, val: string) {
  const key = `${sectionId}-${itemKey}`
  if (!checkData[key]) checkData[key] = { conclusion: '', remark: '' }
  checkData[key].conclusion = val
  formData.saveField(`L8-6-${key}`, { conclusion: val })
}

function getCheckRemark(sectionId: string, itemKey: string): string {
  return checkData[`${sectionId}-${itemKey}`]?.remark || ''
}

function setCheckRemark(sectionId: string, itemKey: string, val: string) {
  const key = `${sectionId}-${itemKey}`
  if (!checkData[key]) checkData[key] = { conclusion: '', remark: '' }
  checkData[key].remark = val
  formData.debouncedSave(`L8-6-${key}`, { remark: val || null })
}

// ─── 结论标签映射 ────────────────────────────────────────────────────────────

function getConclusionTag(val: string): '' | 'success' | 'danger' | 'info' | 'warning' {
  const map: Record<string, any> = { pass: 'success', fail: 'danger', na: 'info', pending: 'warning' }
  return map[val] || ''
}

function getConclusionLabel(val: string): string {
  const map: Record<string, string> = { pass: '无异常', fail: '异常', na: '不适用', pending: '待核实' }
  return map[val] || '未选择'
}

// ─── 审计结论 + 意见 ─────────────────────────────────────────────────────────

const auditConclusion = ref('')
const auditOpinion = ref('')
const opinionNote = ref('')
const isSaving = ref(false)

function saveConclusion() {
  formData.debouncedSave('L8-6-conclusion', { remark: auditConclusion.value || null })
}

function saveOpinion() {
  formData.saveField('L8-6-opinion', { conclusion: auditOpinion.value })
}

function saveOpinionNote() {
  formData.debouncedSave('L8-6-opinionNote', { remark: opinionNote.value || null })
}

async function handleSave() {
  isSaving.value = true
  try {
    // 批量保存所有检查数据
    const items = Object.entries(checkData).map(([key, val]) => ({
      itemId: `L8-6-${key}`,
      data: { conclusion: val.conclusion || null, remark: val.remark || null },
    }))
    await formData.saveBatch(items)
  } finally {
    isSaving.value = false
  }
}

function handleAI(_section: string) { /* AI辅助待集成 */ }
function handleReview() { openReviewDialog?.('L8-6-check', '检查表') }

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(async () => {
  await formData.loadData()
  _restoreData()
})

function _restoreData() {
  // 恢复检查项结论和备注
  for (const section of checkSections) {
    for (const item of section.items) {
      const key = `${section.id}-${item.key}`
      const resp = formData.allResponses.value.get(`L8-6-${key}`)
      if (resp) {
        checkData[key] = {
          conclusion: resp.conclusion || '',
          remark: resp.remark || '',
        }
      }
    }
  }
  // 恢复结论/意见
  const conc = formData.allResponses.value.get('L8-6-conclusion')
  if (conc?.remark) auditConclusion.value = conc.remark
  const op = formData.allResponses.value.get('L8-6-opinion')
  if (op?.conclusion) auditOpinion.value = op.conclusion
  const opn = formData.allResponses.value.get('L8-6-opinionNote')
  if (opn?.remark) opinionNote.value = opn.remark
}
</script>

<style scoped>
.l8-tab-fin-expense-check { padding: 12px; font-size: 13px; }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; flex-wrap: wrap; gap: 8px; }
.section-header-left { display: flex; align-items: center; gap: 8px; }
.section-header-right { display: flex; align-items: center; gap: 8px; }
.section-title { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }
.methodology-context { border-left: 4px solid #e6a23c; background: #fdf6ec; padding: 12px 16px; border-radius: 0 6px 6px 0; margin-bottom: 16px; }
.methodology-text { font-size: 13px; color: #6b5900; line-height: 1.6; }
.check-section { margin-bottom: 20px; }
.check-section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.check-section-title { margin: 0; font-size: 14px; font-weight: 600; color: #303133; }
:deep(.el-table) { font-size: 13px; }
.conclusion-card { margin-top: 20px; }
.opinion-card { margin-top: 16px; }
.card-title { font-size: 14px; font-weight: 600; color: #303133; }
.l8-details-tip { margin-top: 16px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: 13px; color: #606266; }
.l8-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; }
.l8-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
