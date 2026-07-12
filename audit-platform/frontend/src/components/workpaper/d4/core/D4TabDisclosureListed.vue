<script setup lang="ts">
/**
 * D4TabDisclosureListed — 附注披露（上市公司版）
 *
 * 4子节卡片:
 * (一) 营业收入和营业成本（跨sheet自动取数 D4-1/D4-2/M循环）
 * (二) 合同收入分解（按商品/服务/地区/时段，动态行）
 * (三) 前五大客户收入（动态行+自动占比+关联方标记）
 * (四) 合同资产/合同负债变动（动态行+自动差额）
 *
 * 底部：审计说明textarea + AI辅助按钮 + 编制提示折叠
 */
import { ref, computed, onMounted, inject } from 'vue'
import { useDebounceFn } from '@vueuse/core'
import http from '@/utils/http'
import { useD4Disclosure, type ContractBalanceRow } from '../../composables/useD4Disclosure'
import { parseNum } from '../../composables/useD4FormulaEngine'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)

// ─── Debounced batch save ──────────────────────────────────────────────────
const pendingItems = ref<any[]>([])
const debouncedFlush = useDebounceFn(async () => {
  if (pendingItems.value.length === 0) return
  const items = [...pendingItems.value]
  pendingItems.value = []
  try {
    await http.put(`/api/workpapers/${props.wpId}/checklist-responses`, { items }, { _silent: true } as any)
  } catch { /* silent */ }
}, 2000)

function saveBatch(items: any[]) {
  pendingItems.value.push(...items)
  debouncedFlush()
}

// ─── Composable ──────────────────────────────────────────────────────────────
const allResponsesRef = computed(() => props.allResponses) as any
const wpIdRef = computed(() => props.wpId) as any
const projectIdRef = computed(() => props.projectId) as any
const isReadonlyRef = computed(() => props.isReadonly) as any

const {
  crossSheetRevenue, crossSheetCost,
  isRefreshing, lastRefreshTime, refreshFromTb,
  section1Data, section1Total, grossMarginRate, priorGrossMarginRate,
  section2Rows, section2Total, addSection2Row, removeSection2Row, updateSection2,
  section3Rows, section3Total, addSection3Row, removeSection3Row, updateSection3,
  section4Rows, section4Total, addSection4Row, removeSection4Row, updateSection4,
  noteTexts, updateNote,
} = useD4Disclosure({
  allResponses: allResponsesRef,
  wpId: wpIdRef,
  projectId: projectIdRef,
  variant: 'listed',
  saveBatch,
  isReadonly: isReadonlyRef,
})

// ─── Format helpers ──────────────────────────────────────────────────────────
function fmtAmt(v: number): string {
  if (v === 0) return '-'
  if (v < 0) return `(${Math.abs(v).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })})`
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtPct(v: number): string {
  if (!v && v !== 0) return '-'
  return v.toFixed(2) + '%'
}

// ─── AI 辅助生成 ─────────────────────────────────────────────────────────────
const aiLoading = ref(false)

async function aiGenerate(noteKey: string, task: string) {
  if (aiLoading.value || props.isReadonly) return
  aiLoading.value = true
  try {
    const res = await http.post(`/api/workpapers/${props.wpId}/d4/ai-generate`, {
      section: 'adj-note',
      existingContent: noteTexts.value[noteKey] || '',
      relatedContext: {
        task,
        variant: 'listed',
        revenue: crossSheetRevenue.value,
        cost: crossSheetCost.value,
      },
    }, { _silent: true } as any)
    const data = res.data?.data ?? res.data
    if (data?.generated_text) {
      updateNote(noteKey, data.generated_text)
    }
  } catch { /* silent - AI不可用时不报错 */ }
  finally { aiLoading.value = false }
}

// ─── 公式管理 ────────────────────────────────────────────────────────────────
const showFormulaDrawer = ref(false)

// 公式映射表：描述每个自动填充单元格的数据来源
const formulaMap = [
  { field: '主营业务-本期收入', source: 'trial_balance', formula: 'SUM(audited_amount WHERE standard_account_code=6001)', account: '6001' },
  { field: '其他业务-本期收入', source: 'trial_balance', formula: 'SUM(audited_amount WHERE standard_account_code=6051)', account: '6051' },
  { field: '主营业务-本期成本', source: 'trial_balance', formula: 'SUM(audited_amount WHERE standard_account_code=6401)', account: '6401' },
  { field: '其他业务-本期成本', source: 'trial_balance', formula: 'SUM(audited_amount WHERE standard_account_code=6402)', account: '6402' },
  { field: '主营业务-上期收入', source: 'trial_balance(year-1)', formula: 'SUM(audited_amount WHERE code=6001, year=prior)', account: '6001' },
  { field: '其他业务-上期收入', source: 'trial_balance(year-1)', formula: 'SUM(audited_amount WHERE code=6051, year=prior)', account: '6051' },
  { field: '主营业务-上期成本', source: 'trial_balance(year-1)', formula: 'SUM(audited_amount WHERE code=6401, year=prior)', account: '6401' },
  { field: '其他业务-上期成本', source: 'trial_balance(year-1)', formula: 'SUM(audited_amount WHERE code=6402, year=prior)', account: '6402' },
  { field: '毛利率', source: '计算', formula: '(总收入 - 总成本) / 总收入 × 100%', account: '-' },
]
</script>

<template>
  <div class="d4-disclosure-listed">
    <!-- 工具栏 -->
    <div class="disclosure-toolbar">
      <el-button size="small" :loading="isRefreshing" @click="refreshFromTb">🔄 全量刷新取数</el-button>
      <el-button size="small" @click="showFormulaDrawer = true">ƒx 公式管理</el-button>
      <span v-if="lastRefreshTime" class="toolbar-hint">
        上次取数：{{ lastRefreshTime.slice(0,16).replace('T',' ') }}
      </span>
    </div>

    <!-- 公式管理抽屉 -->
    <el-drawer v-model="showFormulaDrawer" title="公式管理 - 数据来源映射" size="480px" direction="rtl">
      <div class="formula-drawer-content">
        <p class="formula-desc">以下字段从试算表(trial_balance)自动提取审定数，点击"🔄全量刷新取数"更新。</p>
        <el-table :data="formulaMap" border size="small" style="width: 100%">
          <el-table-column prop="field" label="字段" width="160" />
          <el-table-column prop="source" label="数据源" width="130" />
          <el-table-column prop="formula" label="公式/取数逻辑" min-width="200">
            <template #default="{ row }">
              <code class="formula-code">{{ row.formula }}</code>
            </template>
          </el-table-column>
          <el-table-column prop="account" label="科目" width="60" align="center" />
        </el-table>
        <el-divider />
        <h4>自动提取区域（刷新时从其他sheet汇总）</h4>
        <ul class="formula-manual-list">
          <li>(2) 按行业/产品类型 — 从D4-2主营明细按产品名汇总 + D4-3其他收入</li>
          <li>(3) 按地区 — 需手工录入（地区维度数据暂无对应sheet）</li>
        </ul>
        <h4>手工填写区域</h4>
        <ul class="formula-manual-list">
          <li>(4) 收入分解信息 — 手工录入时点/时段分解</li>
          <li>(5)~(8) 文字描述 — 手工填写或AI生成</li>
        </ul>
      </div>
    </el-drawer>
    <!-- (1) 营业收入和营业成本 -->
    <el-card class="section-card" shadow="never">
      <template #header>
        <div class="section-header-row">
          <span class="section-title">(1) 营业收入和营业成本</span>
          <div class="header-actions">
            <el-tag size="small" type="info" effect="plain">TB:6001</el-tag>
            <el-tag size="small" type="info" effect="plain">TB:6051</el-tag>
            <el-tag size="small" type="info" effect="plain">TB:6401</el-tag>
            <el-tag size="small" type="info" effect="plain">TB:6402</el-tag>
          </div>
        </div>
      </template>
      <div v-if="lastRefreshTime" class="refresh-hint">
        数据来源：trial_balance 审定数 · 公式：收入=6001+6051, 成本=6401+6402, 毛利=收入-成本 · {{ lastRefreshTime.slice(0,16).replace('T',' ') }}
      </div>
      <!-- 方法论上下文 -->
      <div class="method-context">
        <p>1. 处置投资性房地产的收入在"其他业务收入"列示，相应结转成本至"其他业务成本"，不计入"资产处置损益"。</p>
        <p>2. 停工停产期间继续计提固定资产折旧和无形资产摊销，计入营业成本。</p>
        <p>3. 披露本公司前期已经履行(或部分履行)的履约义务在本期调整的收入金额及原因。</p>
      </div>
      <el-table :data="[...section1Data, section1Total]" border size="small" class="disclosure-table">
        <el-table-column prop="category" label="项目" min-width="120" />
        <el-table-column label="本期收入" min-width="110" align="right">
          <template #default="{ row }"><span :class="row.rowId !== '__total__' ? 'cross-sheet-cell' : 'font-bold'">{{ fmtAmt(row.currentRevenue) }}</span></template>
        </el-table-column>
        <el-table-column label="本期成本" min-width="110" align="right">
          <template #default="{ row }"><span :class="[row.currentCost === 0 ? 'placeholder-cell' : 'cross-sheet-cell', row.rowId === '__total__' ? 'font-bold' : '']">{{ row.currentCost === 0 ? '待刷新' : fmtAmt(row.currentCost) }}</span></template>
        </el-table-column>
        <el-table-column label="上期收入" min-width="110" align="right">
          <template #default="{ row }"><span :class="row.rowId === '__total__' ? 'font-bold' : ''">{{ fmtAmt(row.priorRevenue) }}</span></template>
        </el-table-column>
        <el-table-column label="上期成本" min-width="110" align="right">
          <template #default="{ row }"><span :class="row.rowId === '__total__' ? 'font-bold' : ''">{{ row.priorCost === 0 ? '-' : fmtAmt(row.priorCost) }}</span></template>
        </el-table-column>
      </el-table>
      <div class="note-area"><el-input :model-value="noteTexts['note-1']" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" placeholder="说明：披露前期已履行的履约义务在本期调整的收入金额及原因..." :disabled="isReadonly" @input="(v: string) => updateNote('note-1', v)" /></div>
    </el-card>

    <!-- (2) 按行业/产品类型划分 -->
    <el-card class="section-card" shadow="never">
      <template #header>
        <div class="section-header-row">
          <span class="section-title">(2) 营业收入、营业成本按行业（或产品类型）划分</span>
          <div class="header-actions">
            <el-button size="small" :disabled="isReadonly" @click="addSection2Row">+ 添加行</el-button>
          </div>
        </div>
      </template>
      <el-table :data="section2Rows" border size="small" class="disclosure-table">
        <el-table-column label="主要产品类型（或行业）" min-width="180">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.category" size="small" placeholder="如：消费品/汽车/能源/销售材料..." @change="(v: string) => updateSection2(row.rowId, 'category', v)" />
            <span v-else>{{ row.category || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期收入" min-width="110" align="right">
          <template #default="{ row }"><el-input v-if="!isReadonly" :model-value="row.currentAmount" size="small" type="number" @change="(v: string) => updateSection2(row.rowId, 'currentAmount', v)" /><span v-else>{{ fmtAmt(row.currentAmount) }}</span></template>
        </el-table-column>
        <el-table-column label="本期成本" min-width="110" align="right">
          <template #default="{ row }"><el-input v-if="!isReadonly" :model-value="row.priorAmount" size="small" type="number" @change="(v: string) => updateSection2(row.rowId, 'priorAmount', v)" /><span v-else>{{ fmtAmt(row.priorAmount) }}</span></template>
        </el-table-column>
        <el-table-column width="50" align="center">
          <template #default="{ row }"><el-button v-if="!isReadonly" type="danger" size="small" link @click="removeSection2Row(row.rowId)">删</el-button></template>
        </el-table-column>
      </el-table>
      <div v-if="section2Rows.length > 0" class="subtotal-row">合计：收入 <span class="font-bold">{{ fmtAmt(section2Total.currentAmount) }}</span> / 成本 <span class="font-bold">{{ fmtAmt(section2Total.priorAmount) }}</span></div>
      <div class="note-area"><el-input :model-value="noteTexts['note-2']" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" placeholder="说明..." :disabled="isReadonly" @input="(v: string) => updateNote('note-2', v)" /></div>
    </el-card>

    <!-- (3) 按地区划分 -->
    <el-card class="section-card" shadow="never">
      <template #header>
        <div class="section-header-row">
          <span class="section-title">(3) 营业收入、营业成本按地区划分</span>
          <div class="header-actions">
            <el-button size="small" :disabled="isReadonly" @click="addSection3Row">+ 添加行</el-button>
          </div>
        </div>
      </template>
      <el-table :data="section3Rows" border size="small" class="disclosure-table">
        <el-table-column label="主要经营地区" min-width="160">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.name" size="small" placeholder="如：东北/华北/西北/华东..." @change="(v: string) => updateSection3(row.rowId, 'name', v)" />
            <span v-else>{{ row.name || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期收入" min-width="110" align="right">
          <template #default="{ row }"><el-input v-if="!isReadonly" :model-value="row.amount" size="small" type="number" @change="(v: string) => updateSection3(row.rowId, 'amount', v)" /><span v-else>{{ fmtAmt(row.amount) }}</span></template>
        </el-table-column>
        <el-table-column label="本期成本" min-width="110" align="right">
          <template #default="{ row }"><el-input v-if="!isReadonly" :model-value="row.proportion" size="small" type="number" @change="(v: string) => updateSection3(row.rowId, 'proportion', v)" /><span v-else>{{ fmtAmt(row.proportion) }}</span></template>
        </el-table-column>
        <el-table-column width="50" align="center">
          <template #default="{ row }"><el-button v-if="!isReadonly" type="danger" size="small" link @click="removeSection3Row(row.rowId)">删</el-button></template>
        </el-table-column>
      </el-table>
      <div v-if="section3Rows.length > 0" class="subtotal-row">合计：收入 <span class="font-bold">{{ fmtAmt(section3Total.amount) }}</span> / 成本 <span class="font-bold">{{ fmtAmt(section3Total.proportion) }}</span></div>
      <div class="note-area"><el-input :model-value="noteTexts['note-3']" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" placeholder="说明..." :disabled="isReadonly" @input="(v: string) => updateNote('note-3', v)" /></div>
    </el-card>

    <!-- (4) 收入分解信息（时点/时段） -->
    <el-card class="section-card" shadow="never">
      <template #header>
        <div class="section-header-row">
          <span class="section-title">(4) 营业收入、营业成本按分解信息</span>
          <div class="header-actions">
            <el-button size="small" :disabled="isReadonly" @click="addSection4Row()">+ 添加行</el-button>
          </div>
        </div>
      </template>
      <div class="method-context">
        <p>企业应考虑：①财务报表之外披露的收入信息；②管理层定期复核的经营分部信息；③使用者评价财务业绩的信息类型。</p>
        <p>分解类别包括：商品类型、经营地区、客户类型、合同类型（固定造价/成本加成）、转让时间（时点/时段）、合同期限、销售渠道等。租赁收入需单独披露。</p>
      </div>
      <el-table :data="(section4Rows as any[])" border size="small" class="disclosure-table">
        <el-table-column label="项目" min-width="160">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.item || row.dimension || ''" size="small" placeholder="如：在某一时点确认/在某一时段确认/租赁收入..." @change="(v: string) => updateSection4(row.rowId, 'item', v)" />
            <span v-else>{{ row.item || row.dimension || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期收入" min-width="110" align="right">
          <template #default="{ row }"><el-input v-if="!isReadonly" :model-value="row.endBalance || row.currentAmount || 0" size="small" type="number" @change="(v: string) => updateSection4(row.rowId, 'endBalance', v)" /><span v-else>{{ fmtAmt(row.endBalance || row.currentAmount || 0) }}</span></template>
        </el-table-column>
        <el-table-column label="本期成本" min-width="110" align="right">
          <template #default="{ row }"><el-input v-if="!isReadonly" :model-value="row.beginBalance || row.priorAmount || 0" size="small" type="number" @change="(v: string) => updateSection4(row.rowId, 'beginBalance', v)" /><span v-else>{{ fmtAmt(row.beginBalance || row.priorAmount || 0) }}</span></template>
        </el-table-column>
        <el-table-column width="50" align="center">
          <template #default="{ row }"><el-button v-if="!isReadonly" type="danger" size="small" link @click="removeSection4Row(row.rowId)">删</el-button></template>
        </el-table-column>
      </el-table>
      <div class="note-area"><el-input :model-value="noteTexts['note-4']" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" placeholder="说明：收入分解维度选择依据..." :disabled="isReadonly" @input="(v: string) => updateNote('note-4', v)" /></div>
    </el-card>

    <!-- (5) 履约义务的说明 -->
    <el-card class="section-card" shadow="never">
      <template #header>
        <div class="section-header-row">
          <span class="section-title">(5) 履约义务的说明</span>
          <el-button size="small" :disabled="isReadonly || aiLoading" :loading="aiLoading" @click="aiGenerate('note-5', '根据项目合同信息，生成履约义务相关披露文本')">🤖 AI生成</el-button>
        </div>
      </template>
      <div class="method-context">
        <p>披露与履约义务相关的信息，包括：履行时间（通常的履行时间）、重要的支付条款、企业承诺转让的商品的性质（包括说明企业是否作为代理人）、企业承担的预期将退还给客户的款项等类似义务、质量保证的类型及相关义务等。</p>
      </div>
      <el-input :model-value="noteTexts['note-5'] || ''" type="textarea" :autosize="{ minRows: 4, maxRows: 12 }" placeholder="请填写履约义务相关信息..." :disabled="isReadonly" @input="(v: string) => updateNote('note-5', v)" />
    </el-card>

    <!-- (6) 与剩余履约义务有关的信息 -->
    <el-card class="section-card" shadow="never">
      <template #header>
        <div class="section-header-row">
          <span class="section-title">(6) 与剩余履约义务有关的信息</span>
          <el-button size="small" :disabled="isReadonly || aiLoading" :loading="aiLoading" @click="aiGenerate('note-6', '生成剩余履约义务披露文本，包含交易价格总额和确认时间')">🤖 AI生成</el-button>
        </div>
      </template>
      <div class="method-context">
        <p>披露：①分摊至本期末尚未履行(或部分未履行)履约义务的交易价格总额；②上述金额确认为收入的预计时间。</p>
        <p>说明是否存在任何对价金额未纳入交易价格（如因可变对价限制要求而未计入的部分）。</p>
        <p>简化操作方法适用条件：一是原预计合同期限不超过一年；二是企业有权发出账单且账单金额能代表已履约部分价值。采用简化方法的应提供定性说明。</p>
      </div>
      <el-input :model-value="noteTexts['note-6'] || ''" type="textarea" :autosize="{ minRows: 4, maxRows: 12 }" placeholder="披露分摊至尚未履行的履约义务的交易价格总额及确认为收入的预计时间..." :disabled="isReadonly" @input="(v: string) => updateNote('note-6', v)" />
    </el-card>

    <!-- (7) 重大合同变更或重大交易价格调整 -->
    <el-card class="section-card" shadow="never">
      <template #header>
        <div class="section-header-row">
          <span class="section-title">(7) 重大合同变更【或重大交易价格调整】</span>
          <el-button size="small" :disabled="isReadonly || aiLoading" :loading="aiLoading" @click="aiGenerate('note-7', '生成重大合同变更披露文本')">🤖 AI生成</el-button>
        </div>
      </template>
      <el-input :model-value="noteTexts['note-7'] || ''" type="textarea" :autosize="{ minRows: 3, maxRows: 10 }" placeholder="披露重大合同变更或重大交易价格调整相关的信息、会计处理方法及对收入的影响金额。" :disabled="isReadonly" @input="(v: string) => updateNote('note-7', v)" />
    </el-card>

    <!-- (8) 试运行销售收入 -->
    <el-card class="section-card" shadow="never">
      <template #header>
        <div class="section-header-row">
          <span class="section-title">(8) 试运行销售收入</span>
          <el-button size="small" :disabled="isReadonly || aiLoading" :loading="aiLoading" @click="aiGenerate('note-8', '生成试运行销售收入披露文本')">🤖 AI生成</el-button>
        </div>
      </template>
      <el-input :model-value="noteTexts['note-8'] || ''" type="textarea" :autosize="{ minRows: 3, maxRows: 10 }" placeholder="披露试运行期间的销售收入及相关会计处理（如适用）。" :disabled="isReadonly" @input="(v: string) => updateNote('note-8', v)" />
    </el-card>

    <!-- 报表校对区 -->
    <el-card class="section-card reconcile-card" shadow="never">
      <template #header>
        <div class="section-header-row">
          <span class="section-title">📊 报表校对</span>
          <el-button size="small" :loading="isRefreshing" @click="refreshFromTb">🔄 重新校对</el-button>
        </div>
      </template>
      <div class="reconcile-grid">
        <div class="reconcile-item">
          <span class="reconcile-label">审定表收入合计</span>
          <span class="reconcile-value">{{ fmtAmt(crossSheetRevenue.totalRevenue) }}</span>
        </div>
        <div class="reconcile-item">
          <span class="reconcile-label">本表(1)收入合计</span>
          <span class="reconcile-value">{{ fmtAmt(section1Total.currentRevenue) }}</span>
        </div>
        <div class="reconcile-item" :class="{ 'reconcile-diff': Math.abs(crossSheetRevenue.totalRevenue - section1Total.currentRevenue) > 0.01 }">
          <span class="reconcile-label">差异</span>
          <span class="reconcile-value">{{ fmtAmt(crossSheetRevenue.totalRevenue - section1Total.currentRevenue) }}</span>
        </div>
      </div>
      <div class="reconcile-note">数据应与附注模块"营业收入"章节一致。差异≠0时请检查审定表是否已更新。</div>
    </el-card>

  </div>
</template>

<style scoped>
.d4-disclosure-listed { padding: 12px; font-size: var(--wp-font-size, 13px); }
.d4-disclosure-listed :deep(*) { font-size: var(--wp-font-size, 13px); }
.disclosure-toolbar { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; padding: 8px 12px; background: #f5f7fa; border-radius: 6px; }
.toolbar-hint { font-size: 12px; color: #909399; margin-left: auto; }
.formula-drawer-content { padding: 0 4px; }
.formula-desc { font-size: var(--wp-font-size, 13px); color: #606266; margin-bottom: 12px; }
.formula-code { font-size: 11px; background: #f5f7fa; padding: 2px 4px; border-radius: 2px; color: #409eff; word-break: break-all; }
.formula-manual-list { font-size: var(--wp-font-size, 13px); color: #606266; padding-left: 20px; }
.formula-manual-list li { margin-bottom: 6px; }
.section-card { margin-bottom: 16px; }
.section-card :deep(.el-card__header) { padding: 10px 16px; background: #fafafa; }
.section-title { font-size: var(--wp-font-size, 13px); font-weight: 600; color: #303133; }
.section-header-row { display: flex; justify-content: space-between; align-items: center; }
.header-actions { display: flex; gap: 6px; align-items: center; }
.disclosure-table { font-size: var(--wp-font-size, 13px); }
.disclosure-table :deep(th) { font-size: var(--wp-font-size, 13px); background: #f5f7fa !important; }
.cross-sheet-cell { background-color: #e6f7ff; padding: 2px 6px; border-radius: 2px; border-bottom: 1px dashed #91caff; cursor: help; }
.method-context { margin-bottom: 12px; padding: 8px 12px; border-left: 3px solid #e6a23c; background: #fdf6ec; border-radius: 0 4px 4px 0; font-size: 12px; color: #865c0a; line-height: 1.6; }
.method-context p { margin: 0 0 4px; }
.method-context p:last-child { margin-bottom: 0; }
.placeholder-cell { color: #c0c4cc; font-style: italic; }
.font-bold { font-weight: 600; }
.subtotal-row { margin-top: 8px; padding: 6px 12px; background: #f5f7fa; border-radius: 4px; font-size: var(--wp-font-size, 13px); color: #606266; }
.note-area { margin-top: 12px; }
.refresh-hint { font-size: var(--wp-font-size, 13px); color: #909399; margin-bottom: 8px; padding: 4px 8px; background: #f0f9ff; border-radius: 3px; }
.reconcile-card :deep(.el-card__header) { background: #f0f9eb; }
.reconcile-grid { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 12px; padding: 8px 0; }
.reconcile-item { display: flex; flex-direction: column; align-items: center; padding: 8px; background: #fafafa; border-radius: 4px; }
.reconcile-label { font-size: 12px; color: #909399; margin-bottom: 4px; }
.reconcile-value { font-size: 14px; font-weight: 600; color: #303133; }
.reconcile-diff { background: #fef0f0; }
.reconcile-diff .reconcile-value { color: #f56c6c; }
.reconcile-note { font-size: 12px; color: #909399; margin-top: 8px; }
</style>
