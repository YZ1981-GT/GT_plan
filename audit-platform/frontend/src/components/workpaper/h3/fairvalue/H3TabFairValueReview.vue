<template>
  <div class="h3-tab-fair-value-review">
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 本表用于复核公允价值模式下投资性房地产期末余额的恰当性，核心逻辑：参考单价×面积 与 账面期末余额 比对。</p>
        <p>2. 参考单价应来自活跃交易市场或可靠外部来源（同类物业成交、评估机构报告、行业指数等），并在"来源"列注明。</p>
        <p>3. 差异率 &gt;20% 或收益法交叉验证超出 ±10% 合理区间时，须在差异原因列说明并执行假设挑战。</p>
        <p>4. 使用公允价值模式前提之一为"所在地有活跃的房地产交易市场"，一般指大中型城市城区。</p>
        <p>5. 可从 H3-2 明细表一键带入类别、面积、期初/期末公允价值；从 H3-14 带入月租金并反推资本化率。</p>
        <p>6. 参考单价来源列支持 📎 OCR 识别成交凭证；编制完成后与 H3-1/H3-2 自动勾稽。</p>
      </div>
    </details>

    <!-- 审计目标（对齐 Excel 模板） -->
    <el-alert
      type="info"
      :closable="false"
      class="objective-alert"
      title="审计目标：投资性房地产以恰当的金额包括在财务报表中，与之相关的计价或分摊调整已恰当记录，相关披露已得到恰当计量和描述。"
    />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <el-button size="small" type="primary" :disabled="isReadonly" @click="handleAddRow">+ 新增物业</el-button>
      <el-button size="small" :disabled="isReadonly" @click="handleImportH32">从 H3-2 带入</el-button>
      <el-button size="small" :disabled="isReadonly" @click="handleImportH14">从 H3-14 带入租金</el-button>
      <span class="chip-wrap"><GtIndexChip value="wp:H3-8" :context-project-id="projectId" /></span>
      <el-tag v-if="h31Reconcile.matched" size="small" type="success">H3-1勾稽一致</el-tag>
      <el-tag v-else-if="h31Reconcile.sourceTotal > 0" size="small" type="danger">H3-1差异</el-tag>
      <el-tag v-if="highDiffRows.length" size="small" type="danger">差异&gt;20% {{ highDiffRows.length }} 项</el-tag>
      <el-tag size="small" type="info">共 {{ reviewCalcRows.length }} 行</el-tag>
    </div>

    <!-- 跨表勾稽 -->
    <el-card shadow="never" class="reconcile-card">
      <template #header>
        <div class="section-title">
          <span>跨表勾稽</span>
          <span class="action-btns">
            <el-button size="small" link @click="emit('navigate-sheet', 'H3-1 审定表')">H3-1 →</el-button>
            <el-button size="small" link @click="emit('navigate-sheet', 'H3-2 明细表')">H3-2 →</el-button>
            <el-button size="small" link @click="emit('navigate-sheet', 'H3-14 租金收入')">H3-14 →</el-button>
          </span>
        </div>
      </template>
      <el-descriptions :column="3" border size="small">
        <el-descriptions-item label="H3-8 期末合计">{{ fmtNum(h31Reconcile.h38Total) }}</el-descriptions-item>
        <el-descriptions-item label="H3-1 审定数合计">
          <span :class="{ 'text-danger': !h31Reconcile.matched && h31Reconcile.sourceTotal > 0 }">
            {{ h31Reconcile.sourceTotal ? fmtNum(h31Reconcile.sourceTotal) : '-' }}
          </span>
        </el-descriptions-item>
        <el-descriptions-item label="H3-1 差异">
          <el-tag :type="h31Reconcile.matched ? 'success' : (h31Reconcile.sourceTotal ? 'danger' : 'info')" size="small">
            {{ h31Reconcile.sourceTotal ? fmtNum(h31Reconcile.diff) : '待编制' }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="H3-2 公允期末">{{ h32Reconcile.sourceTotal ? fmtNum(h32Reconcile.sourceTotal) : '-' }}</el-descriptions-item>
        <el-descriptions-item label="H3-2 差异" :span="2">
          <el-tag :type="h32Reconcile.matched ? 'success' : (h32Reconcile.sourceTotal ? 'warning' : 'info')" size="small">
            {{ h32Reconcile.sourceTotal ? fmtNum(h32Reconcile.diff) : '待编制' }}
          </el-tag>
        </el-descriptions-item>
      </el-descriptions>
      <p class="reconcile-note">{{ h31Reconcile.note }}</p>
    </el-card>

    <!-- 区域1：主复核表（对齐 Excel H3-8） -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="section-title">
          <span>二、审计过程：公允价值复核计算</span>
          <el-button size="small" @click="generateAI('H3-8-calc')">AI</el-button>
        </div>
      </template>
      <el-table :data="displayRows" border size="small" class="audit-table" :row-class-name="getMainRowClass">
        <el-table-column prop="category" label="类别" min-width="90" fixed>
          <template #default="{ row, $index }">
            <el-input v-if="!row.isSubtotal && !isReadonly" v-model="row.category" size="small" @change="onCalcRowChange($index, row)" />
            <span v-else>{{ row.category }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="assetName" label="名称" min-width="110" fixed>
          <template #default="{ row, $index }">
            <el-input v-if="!row.isSubtotal && !isReadonly" v-model="row.assetName" size="small" @change="onCalcRowChange($index, row)" />
            <span v-else>{{ row.assetName }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期初公允①" min-width="100" align="right">
          <template #default="{ row, $index }">
            <el-input v-if="!row.isSubtotal && !isReadonly" v-model.number="row.openingFairValue" size="small" @change="onCalcRowChange($index, row)" />
            <span v-else class="amount-cell">{{ fmtNum(row.openingFairValue) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="账面数" align="center">
          <el-table-column label="面积②" min-width="80" align="right">
            <template #default="{ row, $index }">
              <el-input v-if="!row.isSubtotal && !isReadonly" v-model.number="row.area" size="small" @change="onCalcRowChange($index, row)" />
              <span v-else class="amount-cell">{{ row.isSubtotal ? fmtNum(row.area) : fmtNum(row.area, 2) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="单价③÷②" min-width="90" align="right" class-name="formula-col">
            <template #default="{ row }">
              <span class="formula-value" title="期末余额÷面积">{{ fmtNum(row.bookUnitPrice) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="期末余额③" min-width="100" align="right">
            <template #default="{ row, $index }">
              <el-input v-if="!row.isSubtotal && !isReadonly" v-model.number="row.endingBalance" size="small" @change="onCalcRowChange($index, row)" />
              <span v-else class="amount-cell">{{ fmtNum(row.endingBalance) }}</span>
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column label="复核" align="center">
          <el-table-column label="参考单价④" min-width="110" align="right">
            <template #default="{ row, $index }">
              <div v-if="!row.isSubtotal && !isReadonly" class="ref-price-cell">
                <el-input v-model.number="row.refUnitPrice" size="small" @change="onCalcRowChange($index, row)" />
                <el-button size="small" link title="OCR识别成交凭证" @click="handleRefPriceOcr($index)">📎</el-button>
              </div>
              <span v-else class="amount-cell">{{ fmtNum(row.refUnitPrice) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="来源⑤" min-width="100">
            <template #default="{ row, $index }">
              <el-input v-if="!row.isSubtotal && !isReadonly" v-model="row.refPriceSource" size="small" placeholder="成交/评估/指数" @change="onCalcRowChange($index, row)" />
              <span v-else>{{ row.refPriceSource }}</span>
            </template>
          </el-table-column>
          <el-table-column label="公允价值⑥=②×④" min-width="110" align="right" class-name="formula-col">
            <template #default="{ row }">
              <span class="formula-value" title="面积×参考单价">{{ fmtNum(row.auditorFairValue) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="差异⑦=③-⑥" min-width="100" align="right" class-name="formula-col">
            <template #default="{ row }">
              <span class="formula-value" :class="{ 'text-danger': isHighDiff(row) }">{{ fmtNum(row.difference) }}</span>
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column label="差异原因⑧" min-width="110">
          <template #default="{ row, $index }">
            <el-input v-if="!row.isSubtotal && !isReadonly" v-model="row.diffReason" size="small" @change="onCalcRowChange($index, row)" />
            <span v-else>{{ row.diffReason }}</span>
          </template>
        </el-table-column>
        <el-table-column label="与上期一致⑨" width="100" align="center">
          <template #default="{ row, $index }">
            <el-select v-if="!row.isSubtotal && !isReadonly" v-model="row.methodConsistent" size="small" @change="onCalcRowChange($index, row)">
              <el-option label="是" value="是" />
              <el-option label="否" value="否" />
              <el-option label="不适用" value="不适用" />
            </el-select>
            <span v-else>{{ row.methodConsistent }}</span>
          </template>
        </el-table-column>
        <el-table-column label="索引" width="70">
          <template #default="{ row, $index }">
            <el-input v-if="!row.isSubtotal && !isReadonly" v-model="row.indexRef" size="small" @change="onCalcRowChange($index, row)" />
            <span v-else>{{ row.indexRef }}</span>
          </template>
        </el-table-column>
        <el-table-column label="备注" min-width="80">
          <template #default="{ row, $index }">
            <el-input v-if="!row.isSubtotal && !isReadonly" v-model="row.remark" size="small" @change="onCalcRowChange($index, row)" />
            <span v-else>{{ row.remark }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="60" align="center" fixed="right">
          <template #default="{ row, $index }">
            <el-button v-if="!row.isSubtotal && !isReadonly" size="small" type="danger" link @click="removeCalcRow($index)">删</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-alert type="warning" :closable="false" show-icon class="market-note">
      说明：投资性房地产使用公允价值模式前提条件之一的"投资性房地产所在地有活跃的房地产交易市场"，"所在地"一般是指投资性房地产所在的大中型城市的城区。企业选择公允价值模式，应当对所有投资性房地产采用公允价值模式，不得部分成本、部分公允。
    </el-alert>

    <!-- 区域2：评估师信息（补充） -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="section-title">
          <span>(补充) 评估师信息</span>
          <el-button size="small" @click="generateAI('H3-8-appraiser')">AI</el-button>
        </div>
      </template>
      <div class="info-grid">
        <div class="info-item">
          <label>评估机构</label>
          <el-input v-model="appraiserInfo.firm" size="small" :disabled="isReadonly" @change="onInfoChange" />
        </div>
        <div class="info-item">
          <label>资质等级</label>
          <el-input v-model="appraiserInfo.qualification" size="small" :disabled="isReadonly" @change="onInfoChange" />
        </div>
        <div class="info-item">
          <label>独立性声明</label>
          <el-select v-model="appraiserInfo.independence" size="small" :disabled="isReadonly" @change="onInfoChange">
            <el-option label="独立" value="独立" />
            <el-option label="存在关联" value="存在关联" />
          </el-select>
        </div>
      </div>
    </el-card>

    <!-- 区域3：评估方法与假设 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="section-title">
          <span>(补充) 评估方法与关键假设</span>
          <el-button size="small" @click="generateAI('H3-8-method')">AI</el-button>
        </div>
      </template>
      <el-input v-model="methodText" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" placeholder="描述评估方法(市场法/收益法/成本法)及关键参数假设..." :disabled="isReadonly" @change="onMethodChange" />
    </el-card>

    <!-- 区域4：收益法交叉验证 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="section-title">
          <span>(补充) 收益法交叉验证</span>
          <el-button size="small" @click="generateAI('H3-8-income')">AI</el-button>
        </div>
      </template>
      <el-table :data="reviewCalcRows" border size="small" class="audit-table" :row-class-name="getIncomeRowClass">
        <el-table-column prop="assetName" label="资产名称" min-width="120" />
        <el-table-column prop="rentAssumption" label="月租金假设" min-width="100" align="right">
          <template #default="{ row, $index }">
            <el-input v-model.number="row.rentAssumption" size="small" :disabled="isReadonly" @change="onCalcRowChange($index, row)" />
          </template>
        </el-table-column>
        <el-table-column prop="capRate" label="资本化率" width="90" align="right">
          <template #default="{ row, $index }">
            <el-input v-model.number="row.capRate" size="small" :disabled="isReadonly" placeholder="0.05" @change="onCalcRowChange($index, row)" />
          </template>
        </el-table-column>
        <el-table-column prop="growthRate" label="增长率" width="80" align="right">
          <template #default="{ row, $index }">
            <el-input v-model.number="row.growthRate" size="small" :disabled="isReadonly" placeholder="0.02" @change="onCalcRowChange($index, row)" />
          </template>
        </el-table-column>
        <el-table-column label="独立测算值" min-width="110" align="right" class-name="formula-col">
          <template #default="{ row }">
            <span class="formula-value" title="年租金/(资本化率-增长率)">{{ fmtNum(row.independentCalc) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="vs账面差异" min-width="100" align="right" class-name="formula-col">
          <template #default="{ row }">
            <span class="formula-value">{{ fmtNum(row.indVsBookDiff) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="在范围内" width="80" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.independentCalc > 0" :type="row.withinRange ? 'success' : 'danger'" size="small">
              {{ row.withinRange ? '是' : '否' }}
            </el-tag>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column prop="conclusion" label="结论" min-width="90">
          <template #default="{ row, $index }">
            <el-select v-model="row.conclusion" size="small" :disabled="isReadonly" @change="onCalcRowChange($index, row)">
              <el-option label="合理" value="合理" />
              <el-option label="偏高" value="偏高" />
              <el-option label="偏低" value="偏低" />
            </el-select>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 区域5：假设挑战 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="section-title">
          <span>(补充) 假设挑战清单</span>
          <span class="action-btns">
            <el-button size="small" :disabled="isReadonly" @click="addChallengeRow">+ 新增</el-button>
            <el-button size="small" @click="generateAI('H3-8-challenge')">AI</el-button>
          </span>
        </div>
      </template>
      <el-table :data="challengeRows" border size="small" class="audit-table">
        <el-table-column prop="assumption" label="关键假设" min-width="140">
          <template #default="{ row, $index }">
            <el-input v-model="row.assumption" size="small" :disabled="isReadonly" @change="onChallengeChange($index, row)" />
          </template>
        </el-table-column>
        <el-table-column prop="appraiserValue" label="评估师假设值" min-width="110">
          <template #default="{ row, $index }">
            <el-input v-model="row.appraiserValue" size="small" :disabled="isReadonly" @change="onChallengeChange($index, row)" />
          </template>
        </el-table-column>
        <el-table-column prop="auditorJudgment" label="审计师独立判断" min-width="120">
          <template #default="{ row, $index }">
            <el-input v-model="row.auditorJudgment" size="small" :disabled="isReadonly" @change="onChallengeChange($index, row)" />
          </template>
        </el-table-column>
        <el-table-column prop="difference" label="差异" min-width="90">
          <template #default="{ row, $index }">
            <el-input v-model="row.difference" size="small" :disabled="isReadonly" @change="onChallengeChange($index, row)" />
          </template>
        </el-table-column>
        <el-table-column prop="reasonableness" label="合理性结论" min-width="100">
          <template #default="{ row, $index }">
            <el-select v-model="row.reasonableness" size="small" :disabled="isReadonly" @change="onChallengeChange($index, row)">
              <el-option label="合理" value="合理" />
              <el-option label="偏乐观" value="偏乐观" />
              <el-option label="偏悲观" value="偏悲观" />
              <el-option label="不合理" value="不合理" />
            </el-select>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 审计说明 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="card-header">
          <span>三、审计说明</span>
          <span class="action-btns">
            <el-button size="small" :disabled="isReadonly" @click="handleDraftNote">生成说明草稿</el-button>
            <el-button size="small" @click="generateAI('H3-8')">AI</el-button>
            <el-button size="small" circle @click="openReview('H3-8')">💬</el-button>
          </span>
        </div>
      </template>
      <el-input :model-value="auditNote" type="textarea" :autosize="{ minRows: 4 }" placeholder="说明参考单价来源、差异原因、评估师胜任能力与独立性、方法与假设复核结论等。" :disabled="isReadonly" @change="saveAuditNote" />
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="card-header">
          <span>四、审计结论</span>
          <el-button size="small" :disabled="isReadonly" @click="handleDraftConclusion">生成结论草稿</el-button>
        </div>
      </template>
      <el-input :model-value="auditConclusion" type="textarea" :autosize="{ minRows: 3 }" placeholder="A、公允价值计量恰当。B、除下列事项外未见异常。C、存在重大问题，不可确认。" :disabled="isReadonly" @change="saveAuditConclusion" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
/**
 * H3TabFairValueReview.vue — H3-8 公允价值复核
 * 主表对齐致同 Excel 模板 + 评估师/收益法/假设挑战补充区域
 */
import { ref, computed, inject, toRef, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useH3FairValueReview, type FairValueReviewRow } from '../../composables/useH3FairValueReview'
import { useH3FormData } from '../../composables/useH3FormData'
import GtIndexChip from '../../GtIndexChip.vue'
import http from '@/utils/http'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
  measurementModel?: 'cost' | 'fair_value'
}>()

const emit = defineEmits<{
  (e: 'navigate-sheet', sheetName: string): void
}>()

const openReviewDialog = inject<(section: string) => void>('openReviewDialog', () => {})

const { getValue, setValue, saveImmediate } = useH3FormData({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  measurementModel: ref('fair_value') as any,
})

const {
  appraiserInfo, methodText, reviewCalcRows, challengeRows, subtotalRow, highDiffRows,
  h31Reconcile, h32Reconcile,
  updateAppraiserInfo, updateMethod, updateCalcRow, addCalcRow, removeCalcRow,
  addChallengeRow, updateChallengeRow, importFromH32, importRentalFromH14, applyRefPriceOcr,
  draftAuditNote, draftAuditConclusion,
} = useH3FairValueReview({
  allResponses: computed(() => props.allResponses) as any,
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  getValue, setValue, saveImmediate,
})

const NOTE_KEY = 'H3-8-audit-note'
const CONCLUSION_KEY = 'H3-8-audit-conclusion'
const auditNote = ref('')
const auditConclusion = ref('')

onMounted(() => {
  const n = props.allResponses.get(NOTE_KEY)
  if (n?.remark) auditNote.value = n.remark
  const c = props.allResponses.get(CONCLUSION_KEY)
  if (c?.remark) auditConclusion.value = c.remark
})

const displayRows = computed(() => {
  const st = subtotalRow.value
  return [
    ...reviewCalcRows.value,
    {
      rowId: 'subtotal',
      isSubtotal: true,
      category: '',
      assetName: '合计',
      openingFairValue: st.openingFairValue,
      area: st.area,
      bookUnitPrice: 0,
      endingBalance: st.endingBalance,
      refUnitPrice: 0,
      refPriceSource: '',
      auditorFairValue: st.auditorFairValue,
      difference: st.difference,
      diffReason: '',
      methodConsistent: '',
      indexRef: '',
      remark: '',
    },
  ]
})

function saveAuditNote(val: string) {
  if (props.isReadonly) return
  auditNote.value = val
  props.allResponses.set(NOTE_KEY, { item_id: NOTE_KEY, conclusion: null, remark: val })
  void saveImmediate(NOTE_KEY, val)
}

function saveAuditConclusion(val: string) {
  if (props.isReadonly) return
  auditConclusion.value = val
  props.allResponses.set(CONCLUSION_KEY, { item_id: CONCLUSION_KEY, conclusion: null, remark: val })
  void saveImmediate(CONCLUSION_KEY, val)
}

function onInfoChange() { updateAppraiserInfo(appraiserInfo) }
function onMethodChange() { updateMethod(methodText.value) }

function onCalcRowChange(index: number, row: FairValueReviewRow) {
  updateCalcRow(index, row)
  publishFairValueChanged()
}

function onChallengeChange(index: number, row: any) { updateChallengeRow(index, row) }

function publishFairValueChanged() {
  const totalChange = reviewCalcRows.value.reduce((sum, r) => sum + (r.difference || 0), 0)
  try {
    window.dispatchEvent(new CustomEvent('h3:fair-value-changed', {
      detail: { source: 'H3', totalFairValueChange: totalChange },
    }))
    window.dispatchEvent(new CustomEvent('g-cycle:source-fv', {
      detail: { source: 'H3', amount: totalChange },
    }))
  } catch { /* best effort */ }
  http.post(`/api/projects/${props.projectId}/events/publish`, {
    event_type: 'h3:fair-value-changed',
    payload: { wp_id: props.wpId, totalFairValueChange: totalChange },
  }).catch(() => { /* best effort */ })
}

function isHighDiff(row: FairValueReviewRow): boolean {
  if (!row.endingBalance) return Math.abs(row.difference) > 0
  return Math.abs(row.difference / row.endingBalance) > 0.2
}

function getMainRowClass({ row }: { row: any }): string {
  if (row.isSubtotal) return 'row-subtotal'
  if (isHighDiff(row)) return 'row-warn'
  return ''
}

function getIncomeRowClass({ row }: { row: FairValueReviewRow }): string {
  if (row.independentCalc > 0 && !row.withinRange) return 'row-danger'
  return ''
}

function fmtNum(v: number, digits = 2): string {
  if (!v && v !== 0) return '-'
  if (v === 0) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: digits, maximumFractionDigits: digits })
}

async function handleAddRow() {
  try {
    const { value } = await ElMessageBox.prompt('请输入投资性房地产名称', '新增物业', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
    })
    if (value?.trim()) addCalcRow({ assetName: value.trim() })
  } catch { /* cancelled */ }
}

function handleImportH32() {
  const result = importFromH32()
  if (result.ok) {
    ElMessage.success(result.message)
    publishFairValueChanged()
  } else {
    ElMessage.warning(result.message)
  }
}

function handleImportH14() {
  const result = importRentalFromH14()
  if (result.ok) {
    ElMessage.success(result.message)
    publishFairValueChanged()
  } else {
    ElMessage.warning(result.message)
  }
}

async function handleDraftNote() {
  const draft = draftAuditNote()
  if (auditNote.value?.trim()) {
    try {
      await ElMessageBox.confirm('当前已有审计说明，是否用草稿覆盖？', '生成说明草稿', {
        confirmButtonText: '覆盖',
        cancelButtonText: '取消',
        type: 'warning',
      })
    } catch {
      return
    }
  }
  saveAuditNote(draft)
  ElMessage.success('已生成审计说明草稿')
}

async function handleDraftConclusion() {
  const draft = draftAuditConclusion()
  if (auditConclusion.value?.trim()) {
    try {
      await ElMessageBox.confirm('当前已有审计结论，是否用草稿覆盖？', '生成结论草稿', {
        confirmButtonText: '覆盖',
        cancelButtonText: '取消',
        type: 'warning',
      })
    } catch {
      return
    }
  }
  saveAuditConclusion(draft)
  ElMessage.success('已生成审计结论草稿')
}

async function handleRefPriceOcr(index: number) {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = '.jpg,.jpeg,.png,.pdf'
  input.onchange = async () => {
    const file = input.files?.[0]
    if (!file) return
    try {
      const formData = new FormData()
      formData.append('file', file)
      const res = await http.post(
        `/api/workpapers/${props.wpId}/d4/contract-ocr`,
        formData,
        { headers: { 'Content-Type': 'multipart/form-data' } },
      )
      const ocrData = res.data?.data ?? res.data
      if (!ocrData) return
      await ElMessageBox.confirm(
        `OCR 识别结果：\n金额: ${ocrData.amount ?? '-'}\n日期: ${ocrData.date ?? '-'}\n来源: ${ocrData.counterparty ?? '-'}\n\n确认填入参考单价？`,
        'OCR 识别结果确认',
        { confirmButtonText: '确认填入', cancelButtonText: '取消', type: 'info' },
      )
      applyRefPriceOcr(index, ocrData)
      publishFairValueChanged()
      ElMessage.success('已填入参考单价')
    } catch (err: any) {
      if (err === 'cancel' || err?.toString?.().includes('cancel')) return
      ElMessage.error('OCR 识别失败')
    }
  }
  input.click()
}

function generateAI(section: string) {
  window.dispatchEvent(new CustomEvent('ai:generate', { detail: { section, wpId: props.wpId } }))
}

function openReview(section: string) { openReviewDialog(section) }
</script>

<style scoped>
.h3-tab-fair-value-review { padding: 16px; font-size: var(--wp-font-size, 13px); }
.guidance-details { margin-bottom: 12px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: var(--wp-font-size, 13px); color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.objective-alert { margin-bottom: 12px; }
.market-note { margin-bottom: 16px; }
.tab-toolbar { display: flex; justify-content: flex-end; align-items: center; gap: 8px; margin-bottom: 8px; flex-wrap: wrap; }
.chip-wrap { display: inline-flex; align-items: center; }
.audit-note-card { margin-top: 16px; }
.audit-note-card .card-header { display: flex; justify-content: space-between; align-items: center; font-weight: 500; }
.section-card { margin-bottom: 16px; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.action-btns { display: flex; gap: 4px; }
.info-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
.info-item label { display: block; font-size: 12px; color: var(--el-text-color-secondary); margin-bottom: 4px; }
.audit-table { font-size: var(--wp-font-size, 13px); }
.audit-table :deep(.formula-col) { background: var(--el-fill-color-lighter); }
.audit-table :deep(.row-danger) { background-color: #fef0f0 !important; }
.audit-table :deep(.row-warn) { background-color: #fef9e7 !important; }
.audit-table :deep(.row-subtotal) { font-weight: 600; background-color: #f5f7fa !important; }
.formula-value { border-bottom: 1px dashed var(--el-border-color); cursor: help; }
.text-danger { color: var(--el-color-danger); font-weight: 500; }
.amount-cell { font-variant-numeric: tabular-nums; }
.reconcile-card { margin-bottom: 16px; }
.reconcile-note { margin: 8px 0 0; font-size: 12px; color: #909399; line-height: 1.5; }
.ref-price-cell { display: flex; align-items: center; gap: 2px; }
.ref-price-cell .el-input { flex: 1; }
</style>
