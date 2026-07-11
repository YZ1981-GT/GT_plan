<template>
  <div class="s13-branch">
    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" show-icon class="audit-objective">
      <template #title>审计目标</template>
      <div class="audit-objective-text">
        针对具体评价领域（通用评估 / 股份支付公允价值 / 金融工具公允价值），评价管理层利用专家编制信息在假设、方法、源数据和结论方面的适当性，及管理层对专家工作结果使用方式的恰当性。
      </div>
    </el-alert>

    <!-- 域选择器（el-segmented） -->
    <div class="domain-selector">
      <span class="domain-label">评价对象领域：</span>
      <el-segmented
        v-model="selectedDomain"
        :options="domainOptions"
        size="default"
      />
    </div>

    <!-- 当前域标题 + 方法论上下文 -->
    <div class="methodology-context">
      <p>{{ domainDescription }}</p>
    </div>

    <el-card shadow="never" class="audit-section">
      <template #header>
        <div class="section-header">
          <span>{{ resolvedSheetName }}</span>
          <div class="header-actions">
            <el-button
              v-if="!isReadonly"
              size="small"
              :icon="MagicStick"
              @click="handleAiAssist"
            >AI辅助</el-button>
            <el-button
              size="small"
              @click="handleOpenReview(`s13-branch-${selectedDomain}`, resolvedSheetName)"
            >复核</el-button>
          </div>
        </div>
      </template>

      <el-table
        :data="branchRows"
        border
        style="width: 100%; font-size: 13px"
      >
        <el-table-column type="index" label="序号" width="60" align="center" />
        <el-table-column prop="category" label="评价维度" width="140">
          <template #default="{ row }">
            <span>{{ row.category }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="criterion" label="评价内容/核查事项" min-width="360">
          <template #default="{ row }">
            <span>{{ row.criterion }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="result" label="评价结果" width="120" align="center">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              v-model="row.result"
              size="small"
              placeholder="—"
              style="width: 100px"
              @change="saveRows"
            >
              <el-option label="满意" value="满意" />
              <el-option label="基本满意" value="基本满意" />
              <el-option label="不满意" value="不满意" />
              <el-option label="N/A" value="N/A" />
            </el-select>
            <span v-else>{{ row.result || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="remark" label="说明/工作记录" min-width="200">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              v-model="row.remark"
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 4 }"
              size="small"
              placeholder="填写评价说明"
              @change="saveRows"
            />
            <span v-else>{{ row.remark || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="ref" label="索引号" width="90" align="center">
          <template #default="{ row }">
            <GtIndexChip v-if="row.ref" :value="row.ref" />
            <span v-else>—</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="audit-section conclusion-card">
      <template #header>
        <div class="section-header">
          <span>评价结论</span>
          <div class="header-actions">
            <el-button
              v-if="!isReadonly"
              size="small"
              :icon="MagicStick"
              @click="handleAiConclusion"
            >AI辅助</el-button>
            <el-button
              size="small"
              @click="handleOpenReview(`s13-branch-${selectedDomain}-conclusion`, '评价结论')"
            >复核</el-button>
          </div>
        </div>
      </template>
      <el-input
        v-if="!isReadonly"
        v-model="conclusion"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="填写评价结论"
        @change="saveConclusion"
      />
      <div v-else class="conclusion-text">{{ conclusion || '—' }}</div>
    </el-card>

    <!-- 编制提示 -->
    <details class="edit-hints">
      <summary>编制提示</summary>
      <p v-for="(hint, idx) in currentHints" :key="idx">{{ idx + 1 }}. {{ hint }}</p>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * S13BranchSheet.vue — S13 多分支子表（通用/股份支付/金融工具公允价值）
 *
 * 根据 ExpertDomain 选择显示 S13-3-2/S13-3-3/S13-3-4。
 * 使用 resolveExpertSubSheet 从 useS12S13ExpertBranch.ts 解析确定性 sheetName。
 *
 * 与 S12BranchSheet 结构一致，但评价内容侧重于管理层的专家（被审计单位聘用/委托）。
 *
 * 功能：
 * - el-segmented 域选择器（通用/股份支付/金融工具公允价值）
 * - 根据选择的 domain 动态展示对应评价表
 * - 方法论上下文（琥珀色块）
 * - 结论区 el-card + AI 按钮
 * - GtIndexChip 跨底稿引用
 * - readonly 禁编辑
 *
 * Spec: .kiro/specs/s-special-transaction-workpapers/ Task 4.3
 * Requirements: 4.1, 4.2, 4.3, 4.4
 */
import { ref, computed, watch, inject, onMounted } from 'vue'
import { defineAsyncComponent } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'
import {
  resolveExpertSubSheet,
  EXPERT_DOMAIN_LABELS,
  type ExpertDomain,
  type ExpertPrefix,
} from '../composables/useS12S13ExpertBranch'
import { useSExpertPersist } from '../composables/useSExpertPersist'

const GtIndexChip = defineAsyncComponent(() => import('../GtIndexChip.vue'))

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
  prefix: ExpertPrefix
  /** 主入口透传的持久化快照（已解包纯 Map） */
  allResponses?: Map<string, any>
}>()

// ─── 复核对话 ────────────────────────────────────────────────────────────────

const openReviewDialog = inject<(sectionId: string, sectionLabel?: string) => void>('openReviewDialog')

function handleOpenReview(sectionId: string, label: string) {
  openReviewDialog?.(sectionId, label)
}

// ─── 域选择 ──────────────────────────────────────────────────────────────────

const selectedDomain = ref<ExpertDomain>('general')

const domainOptions = [
  { label: EXPERT_DOMAIN_LABELS['general'], value: 'general' },
  { label: EXPERT_DOMAIN_LABELS['share-based-payment'], value: 'share-based-payment' },
  { label: EXPERT_DOMAIN_LABELS['financial-instrument-fair-value'], value: 'financial-instrument-fair-value' },
]

/** 使用 resolveExpertSubSheet 确定性解析当前 sheetName */
const resolvedSheetName = computed(() => {
  return resolveExpertSubSheet(props.prefix, selectedDomain.value)
})

const domainDescription = computed(() => {
  const descMap: Record<ExpertDomain, string> = {
    'general': '通用评价——适用于评价管理层利用评估师、精算师、工程师等一般性专家编制信息的适当性。注册会计师应关注管理层对专家工作结果的使用方式。',
    'share-based-payment': '股份支付专用评价——适用于评价管理层利用专家确定股份支付公允价值（如期权定价模型输入参数）的适当性。',
    'financial-instrument-fair-value': '金融工具公允价值专用评价——适用于评价管理层利用专家确定金融工具公允价值（如结构化产品/衍生品估值）的适当性。',
  }
  return descMap[selectedDomain.value]
})

// ─── 分支数据 ────────────────────────────────────────────────────────────────

const branchRows = ref<Array<{ category: string; criterion: string; result: string; remark: string; ref: string }>>([])

function loadBranchRows(domain: ExpertDomain) {
  if (domain === 'general') {
    branchRows.value = getGeneralRows()
  } else if (domain === 'share-based-payment') {
    branchRows.value = getShareBasedPaymentRows()
  } else {
    branchRows.value = getFinancialInstrumentRows()
  }
}

function getGeneralRows() {
  return [
    { category: '工作目的', criterion: '管理层的专家工作目的是否与财务报告计量/披露要求一致', result: '', remark: '', ref: '' },
    { category: '工作目的', criterion: '管理层对专家工作结果的使用方式是否恰当', result: '', remark: '', ref: '' },
    { category: '假设合理性', criterion: '管理层指定或认可的关键假设是否有合理依据', result: '', remark: '', ref: '' },
    { category: '假设合理性', criterion: '假设是否与行业数据、历史趋势和市场状况一致', result: '', remark: '', ref: '' },
    { category: '假设合理性', criterion: '是否存在管理层偏向的迹象（如持续偏向乐观估计）', result: '', remark: '', ref: '' },
    { category: '方法选择', criterion: '管理层的专家使用的方法是否适合标的资产/负债特征', result: '', remark: '', ref: '' },
    { category: '方法选择', criterion: '方法是否与上期保持一致（如有变更，变更理由是否充分）', result: '', remark: '', ref: '' },
    { category: '数据完整性', criterion: '专家使用的源数据是否来自被审计单位的会计记录', result: '', remark: '', ref: '' },
    { category: '数据完整性', criterion: '源数据是否完整、相关且经过适当验证', result: '', remark: '', ref: '' },
    { category: '结论合理性', criterion: '专家的结论与管理层在财务报表中的列报是否一致', result: '', remark: '', ref: '' },
    { category: '结论合理性', criterion: '如存在差异，管理层对差异的解释是否合理', result: '', remark: '', ref: '' },
    { category: '敏感性', criterion: '关键变量的敏感性分析结果是否合理', result: '', remark: '', ref: '' },
    { category: '后续事项', criterion: '估值日至报告日之间是否存在影响估值结论的重大后续事项', result: '', remark: '', ref: '' },
  ]
}

function getShareBasedPaymentRows() {
  return [
    { category: '计量模型', criterion: '管理层的专家选用的定价模型是否适合相应股份支付工具', result: '', remark: '', ref: '' },
    { category: '计量模型', criterion: '模型选择是否考虑了行权条件、限售期等条款特征', result: '', remark: '', ref: '' },
    { category: '关键参数', criterion: '标的股票/股权的公允价值输入是否可靠', result: '', remark: '', ref: '' },
    { category: '关键参数', criterion: '行权价格是否与授权协议一致', result: '', remark: '', ref: '' },
    { category: '关键参数', criterion: '预期波动率的计算依据和方法是否合理', result: '', remark: '', ref: '' },
    { category: '关键参数', criterion: '预期有效期是否反映实际行权行为模式', result: '', remark: '', ref: '' },
    { category: '关键参数', criterion: '无风险利率的选取是否恰当（期限匹配的国债收益率）', result: '', remark: '', ref: '' },
    { category: '关键参数', criterion: '预期股利率假设是否与公司股利政策一致', result: '', remark: '', ref: '' },
    { category: '条件处理', criterion: '市场条件是否已在模型中反映', result: '', remark: '', ref: '' },
    { category: '条件处理', criterion: '非市场条件（业绩指标）是否正确在可行权数量中调整', result: '', remark: '', ref: '' },
    { category: '管理层使用', criterion: '管理层是否正确使用专家结果进行费用分摊计算', result: '', remark: '', ref: '' },
  ]
}

function getFinancialInstrumentRows() {
  return [
    { category: '估值层级', criterion: '管理层的专家对公允价值层级的划分（Level 1/2/3）是否恰当', result: '', remark: '', ref: '' },
    { category: '估值层级', criterion: '是否优先使用活跃市场报价而非模型估值', result: '', remark: '', ref: '' },
    { category: '估值模型', criterion: '所用估值模型是否适合该金融工具的特征和复杂程度', result: '', remark: '', ref: '' },
    { category: '估值模型', criterion: '模型是否经过回测验证或独立检验', result: '', remark: '', ref: '' },
    { category: '关键输入', criterion: '折现率/收益率曲线的选取是否合理', result: '', remark: '', ref: '' },
    { category: '关键输入', criterion: '信用利差是否适当反映了发行人信用风险', result: '', remark: '', ref: '' },
    { category: '关键输入', criterion: '波动率参数的来源和时效是否可靠', result: '', remark: '', ref: '' },
    { category: '关键输入', criterion: '违约概率/回收率假设是否有合理依据', result: '', remark: '', ref: '' },
    { category: '结构条款', criterion: '嵌入衍生品是否已在估值中适当考虑', result: '', remark: '', ref: '' },
    { category: '结构条款', criterion: '提前赎回/转换等条款是否已反映在估值中', result: '', remark: '', ref: '' },
    { category: '市场数据', criterion: '使用的市场数据是否为估值日数据', result: '', remark: '', ref: '' },
    { category: '市场数据', criterion: '如有时滞，是否做了适当调整', result: '', remark: '', ref: '' },
    { category: '结论验证', criterion: '估值结果与经纪商报价或可比交易是否合理一致', result: '', remark: '', ref: '' },
    { category: '管理层使用', criterion: '管理层是否正确使用专家估值结果进行会计确认和披露', result: '', remark: '', ref: '' },
  ]
}

// 初始加载 + watch domain 变更（切换域时重载骨架并 seed 该域已存数据）
loadBranchRows(selectedDomain.value)
watch(selectedDomain, (newDomain) => {
  loadBranchRows(newDomain)
  conclusion.value = ''
  seedDomain(newDomain)
})

// ─── 结论 ────────────────────────────────────────────────────────────────────

const conclusion = ref('')

// ─── 持久化接线（load + save，item_id 按 prefix + domain） ────────────────────

const { seed, save } = useSExpertPersist(() => props.allResponses)

function domainRowsId(d: ExpertDomain): string {
  return `${props.prefix}-branch-${d}-rows`
}
function domainConclusionId(d: ExpertDomain): string {
  return `${props.prefix}-branch-${d}-conclusion`
}
function seedDomain(d: ExpertDomain): void {
  seed([
    { itemId: domainRowsId(d), ref: branchRows },
    { itemId: domainConclusionId(d), ref: conclusion },
  ])
}
function saveRows(): void {
  save(domainRowsId(selectedDomain.value), branchRows.value)
}
function saveConclusion(): void {
  save(domainConclusionId(selectedDomain.value), conclusion.value)
}

onMounted(() => seedDomain(selectedDomain.value))

// ─── 编制提示 ────────────────────────────────────────────────────────────────

const currentHints = computed(() => {
  const hintsMap: Record<ExpertDomain, string[]> = {
    'general': [
      '关注管理层对专家工作结果的使用方式——是否存在选择性使用或忽略不利结论。',
      '评价管理层是否有偏向性假设倾向。',
      '将专家结论与其他审计证据进行交叉验证。',
    ],
    'share-based-payment': [
      '核对定价模型输入参数与市场数据的一致性。',
      '区分市场条件（模型内）和非市场条件（可行权数量）的处理方式。',
      '确认管理层是否正确进行了等待期费用分摊。',
    ],
    'financial-instrument-fair-value': [
      '重点关注 Level 3 输入的合理性和不可观察变量的敏感度。',
      '核查信用调整和流动性折价是否适当。',
      '验证市场数据来源的可靠性和时效性。',
      '关注估值不确定性对财务报表的影响。',
    ],
  }
  return hintsMap[selectedDomain.value]
})

// ─── AI 辅助 ─────────────────────────────────────────────────────────────────

function handleAiAssist() {
  // TODO: 调用 AI 辅助
}

function handleAiConclusion() {
  // TODO: 调用 AI 辅助生成结论
}
</script>

<style scoped>
.s13-branch {
  padding: 12px;
}

.audit-objective {
  margin-bottom: 12px;
}

.audit-objective-text {
  font-size: 13px;
  line-height: 1.6;
}

.domain-selector {
  margin-bottom: 12px;
  display: flex;
  align-items: center;
  gap: 10px;
}

.domain-label {
  font-size: 13px;
  font-weight: 500;
  color: #303133;
  white-space: nowrap;
}

.methodology-context {
  margin-bottom: 12px;
  padding: 10px 14px;
  border-left: 3px solid #e6a23c;
  background: #fdf6ec;
  font-size: 12px;
  color: #606266;
  line-height: 1.5;
}

.audit-section {
  margin-bottom: 16px;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.header-actions {
  display: flex;
  gap: 8px;
}

.conclusion-card {
  margin-top: 16px;
}

.conclusion-text {
  white-space: pre-wrap;
  font-size: 13px;
  line-height: 1.6;
  color: #303133;
}

.edit-hints {
  margin-top: 16px;
  font-size: 12px;
  color: #909399;
}

.edit-hints summary {
  cursor: pointer;
  user-select: none;
}

.edit-hints p {
  margin: 4px 0;
  line-height: 1.5;
}
</style>
