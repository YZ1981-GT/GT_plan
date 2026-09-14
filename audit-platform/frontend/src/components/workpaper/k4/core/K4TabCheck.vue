<!--
  K4TabCheck.vue — K4-4 其他流动负债检查表（凭证级测试）

  忠实反映致同源模板 K4-4（镜像 K1-12）：
    一、审计目标（存在/义务/完整性/计价分摊 四认定，负债类完整性为重点）
    二、样本选取标准与规模（测试总体/特定样本/抽样总体/样本量/抽样方法/抽样过程）
    三、测试（本期发生额检查，凭证级明细 + 抽凭引擎 + 核对内容勾选）
    四、审计说明（检查比例表：本期借方/本期贷方 → 账面/检查/比例）
    五、审计结论

  复用 useK1VoucherCheck（通用凭证检查状态）。科目 2245 其他流动负债（贷方/负债类）。
  注：源模板 K4-4 仅"本期发生额检查"单表（无期后检查段）。

  K4 专属核对内容 5 项（覆盖 K1 通用标签）：
    1. 入账依据充分（预提有合同/协议/计算表支撑）
    2. 会计处理正确（科目归类/贷方增加借方减少方向对）
    3. 金额计量准确（与合同/计算表/发票金额一致）
    4. 记录期间正确（归属本期非跨期）
    5. 披露分类恰当（流动/非流动分类/报表列报正确）
-->
<template>
  <div class="k4-tab-check">
    <div class="guide-banner">
      <div class="guide-step"><span class="gs-no">1</span>确认审计目标（四认定）</div>
      <div class="guide-step"><span class="gs-no">2</span>填写样本选取标准与规模</div>
      <div class="guide-step"><span class="gs-no">3</span>抽凭执行凭证级测试（逐笔5项核对）</div>
      <div class="guide-step"><span class="gs-no">4</span>核对检查比例，处理异常，形成结论</div>
    </div>

    <div class="section-head">
      <h3 class="sheet-title">K4-4 其他流动负债检查表</h3>
      <div class="head-actions">
        <el-button size="small" type="primary" link @click="handleAiGenerate">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <el-button size="small" @click="handleReview">💬 复核</el-button>
      </div>
    </div>

    <!-- 方法论提示（源模板凭证筛选建议） -->
    <div class="methodology-block">
      <div class="methodology-title">凭证筛选注意事项（源模板提示）</div>
      <div class="methodology-content">
        抽样时应注意排除以下类型分录（不属于其他流动负债实质性变动）：
        <b>结转类</b>（期末结转损益/本年利润）、<b>薪酬计提类</b>（应付职工薪酬计提已在J循环测试）、
        <b>折旧摊销类</b>（固定资产折旧/无形资产摊销已在H/I循环测试）。
        抽样总体应聚焦于真实业务发生的借贷方变动（预提费用确认/待转销项税额转出/应付退货款变动等）。
      </div>
    </div>

    <!-- 一、审计目标 -->
    <el-alert type="info" :closable="false" class="audit-objective">
      <template #title><span class="ao-title">一、审计目标（认定）</span></template>
      <ol class="ao-list">
        <li><b>存在：</b>资产负债表中记录的其他流动负债是存在的，且已记录在恰当的账户中；</li>
        <li><b>完整性：</b>所有应当记录的其他流动负债均已记入账簿，不存在未入账的隐性负债（<em>负债类核心认定</em>）；</li>
        <li><b>义务：</b>记录的其他流动负债是被审计单位应当履行的现时偿还义务；</li>
        <li><b>计价和分摊：</b>其他流动负债以恰当的金额包括在财务报表中，与之相关的计价或分摊调整已恰当记录，相关披露已得到恰当计量和描述。</li>
      </ol>
    </el-alert>

    <!-- 二、样本选取标准与规模 -->
    <el-card shadow="never" class="section-card">
      <template #header><span class="card-title">二、样本选取标准与规模</span></template>
      <div class="criteria-grid">
        <div class="cg-item">
          <label>测试总体（借方）</label>
          <div class="cg-inline">
            <el-input-number v-model="criteria.populationDebitCount" :controls="false" :disabled="isReadonly" size="small" placeholder="笔数" class="num-sm" @change="persist" />
            <span class="cg-unit">笔</span>
            <el-input-number v-model="criteria.populationDebitAmount" :controls="false" :disabled="isReadonly" size="small" placeholder="金额" class="num-md" @change="persist" />
            <span class="cg-unit">元</span>
          </div>
        </div>
        <div class="cg-item">
          <label>测试总体（贷方）</label>
          <div class="cg-inline">
            <el-input-number v-model="criteria.populationCreditCount" :controls="false" :disabled="isReadonly" size="small" placeholder="笔数" class="num-sm" @change="persist" />
            <span class="cg-unit">笔</span>
            <el-input-number v-model="criteria.populationCreditAmount" :controls="false" :disabled="isReadonly" size="small" placeholder="金额" class="num-md" @change="persist" />
            <span class="cg-unit">元</span>
          </div>
        </div>
        <div class="cg-item cg-full">
          <label>特定样本</label>
          <el-input v-model="criteria.specificSample" :disabled="isReadonly" size="small"
            placeholder="大额（XX金额以上）、关联方/关联交易形成的款项、异常款项全部测试" @change="persist" />
        </div>
        <div class="cg-item">
          <label>抽样总体</label>
          <div class="cg-inline">
            <el-input-number v-model="criteria.samplingPopulationCount" :controls="false" :disabled="isReadonly" size="small" placeholder="笔数" class="num-sm" @change="persist" />
            <span class="cg-unit">笔</span>
            <el-input-number v-model="criteria.samplingPopulationAmount" :controls="false" :disabled="isReadonly" size="small" placeholder="金额" class="num-md" @change="persist" />
            <span class="cg-unit">元</span>
          </div>
        </div>
        <div class="cg-item">
          <label>抽样样本量</label>
          <div class="cg-inline">
            <el-input-number v-model="criteria.sampleSize" :controls="false" :disabled="isReadonly" size="small" placeholder="样本量" class="num-sm" @change="persist" />
            <span class="cg-unit">笔</span>
          </div>
        </div>
        <div class="cg-item">
          <label>抽样方法</label>
          <el-select v-model="criteria.samplingMethod" :disabled="isReadonly" size="small" @change="persist">
            <el-option label="随机选样" value="随机选样" />
            <el-option label="系统选样" value="系统选样" />
            <el-option label="货币单元抽样" value="货币单元抽样" />
            <el-option label="随意选样（非统计抽样）" value="随意选样" />
          </el-select>
        </div>
        <div class="cg-item cg-full">
          <label>抽样过程</label>
          <el-input v-model="criteria.samplingProcess" type="textarea" :autosize="{ minRows: 2 }" :disabled="isReadonly" size="small"
            placeholder="使用IDEA（XX抽样工具）选择XX数量、金额XX的样本进行测试，抽样过程和结果见相关底稿" @change="persist" />
        </div>
      </div>
    </el-card>

    <!-- 三、测试 — 本期发生额检查 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="card-header-row">
          <span class="card-title">三、测试 — 本期发生额检查</span>
          <div class="header-right">
            <span class="check-progress" :class="checkProgressClass">
              核对进度：{{ fullyCheckedCount }}/{{ occurrenceRows.length }} 笔
              <el-tag v-if="occurrenceRows.length > 0" :type="checkProgressRatio >= 1 ? 'success' : checkProgressRatio >= 0.5 ? 'warning' : 'info'" size="small" style="margin-left:4px">
                {{ (checkProgressRatio * 100).toFixed(0) }}%
              </el-tag>
            </span>
            <el-button v-if="!isReadonly" size="small" type="primary" plain @click="openSampling"><el-icon><MagicStick /></el-icon> 抽凭</el-button>
            <el-button v-if="!isReadonly" size="small" @click="addOccurrenceRow(); persist()">＋ 手工新增</el-button>
          </div>
        </div>
      </template>
      <el-table :data="occurrenceRows" border size="small" :max-height="420" class="voucher-table" :row-class-name="abnormalRowClass">
        <el-table-column label="#" type="index" width="42" align="center" />
        <el-table-column label="明细项目" min-width="130">
          <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.debtorName" size="small" @change="persist" /><span v-else>{{ row.debtorName || '-' }}</span></template>
        </el-table-column>
        <el-table-column label="选取原因" width="110">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.selectionReason" size="small" placeholder="原因" @change="persist">
              <el-option v-for="reason in SELECTION_REASONS" :key="reason" :label="reason" :value="reason" />
            </el-select>
            <el-tag v-else-if="row.selectionReason" size="small" :type="row.selectionReason === '大额' ? 'danger' : row.selectionReason === '关联方' ? 'warning' : 'info'">{{ row.selectionReason }}</el-tag>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column label="日期" width="120">
          <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.date" size="small" placeholder="YYYY-MM-DD" @change="persist" /><span v-else>{{ row.date || '-' }}</span></template>
        </el-table-column>
        <el-table-column label="凭证编号" width="110">
          <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.voucherNo" size="small" @change="persist" /><span v-else>{{ row.voucherNo || '-' }}</span></template>
        </el-table-column>
        <el-table-column label="业务内容" min-width="150">
          <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.businessContent" size="small" @change="persist" /><span v-else>{{ row.businessContent || '-' }}</span></template>
        </el-table-column>
        <el-table-column label="对方科目" min-width="110">
          <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.offsetAccount" size="small" @change="persist" /><span v-else>{{ row.offsetAccount || '-' }}</span></template>
        </el-table-column>
        <el-table-column label="借方金额" min-width="110" align="right">
          <template #default="{ row }"><el-input-number v-if="!isReadonly" v-model="row.debitAmount" :controls="false" size="small" class="amount-input" @change="persist" /><span v-else class="amount-cell">{{ fmtAmt(row.debitAmount) }}</span></template>
        </el-table-column>
        <el-table-column label="贷方金额" min-width="110" align="right">
          <template #default="{ row }"><el-input-number v-if="!isReadonly" v-model="row.creditAmount" :controls="false" size="small" class="amount-input" @change="persist" /><span v-else class="amount-cell">{{ fmtAmt(row.creditAmount) }}</span></template>
        </el-table-column>
        <el-table-column label="核对内容" width="180" align="center">
          <template #header>
            <el-tooltip placement="top">
              <template #content><div v-for="(lbl, i) in checkLabels" :key="i">{{ i + 1 }}. {{ lbl }}</div></template>
              <span class="col-help">核对内容 ⓘ</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <el-checkbox-group :model-value="checkedValues(row)" :disabled="isReadonly" class="check-group" @update:model-value="(v: any) => setChecks(row, v as number[])">
              <el-checkbox v-for="(lbl, i) in checkLabels" :key="i" :value="i" :label="i + 1" />
            </el-checkbox-group>
          </template>
        </el-table-column>
        <el-table-column label="是否异常" width="80" align="center">
          <template #default="{ row }"><el-switch v-model="row.abnormal" :disabled="isReadonly" size="small" @change="persist" /></template>
        </el-table-column>
        <el-table-column label="索引号" width="90">
          <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.indexNo" size="small" @change="persist" /><span v-else>{{ row.indexNo || '-' }}</span></template>
        </el-table-column>
        <el-table-column label="备注说明" min-width="120">
          <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.remark" size="small" @change="persist" /><span v-else>{{ row.remark || '-' }}</span></template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="操作" width="56" align="center" fixed="right">
          <template #default="{ row }"><el-button size="small" type="danger" link @click="removeOccurrenceRow(row.id); persist()">删除</el-button></template>
        </el-table-column>
        <template #append><div class="table-total">合计　借方：{{ fmtAmt(occurrenceDebitChecked) }}　贷方：{{ fmtAmt(occurrenceCreditChecked) }}</div></template>
      </el-table>
    </el-card>

    <!-- 四、审计说明（检查比例表：本期借方/本期贷方）-->
    <el-card shadow="never" class="section-card">
      <template #header><span class="card-title">四、审计说明 — 检查比例</span></template>
      <el-alert v-if="k41DebitTotal > 0 || k41CreditTotal > 0" type="success" :closable="false" show-icon style="margin-bottom:8px">
        <template #title>账面金额已自动从 K4-1 审定表取数（本期借方 {{ fmtAmt(k41DebitTotal) }} / 本期贷方 {{ fmtAmt(k41CreditTotal) }}）</template>
      </el-alert>
      <el-alert v-else type="info" :closable="false" style="margin-bottom:8px">
        <template #title>提示：请先编制 K4-1 审定表并保存，检查比例的"账面金额"将自动联动取数</template>
      </el-alert>
      <el-table :data="k4CheckRatios" border size="small" class="ratio-table">
        <el-table-column label="方向" prop="direction" width="120" />
        <el-table-column label="账面金额" align="right"><template #default="{ row }"><span class="amount-cell">{{ fmtAmt(row.bookAmount) }}</span></template></el-table-column>
        <el-table-column label="检查金额" align="right"><template #default="{ row }"><span class="amount-cell">{{ fmtAmt(row.checkedAmount) }}</span></template></el-table-column>
        <el-table-column label="检查比例" width="130" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.ratio != null" :type="row.ratio < 0.3 ? 'danger' : row.ratio < 0.6 ? 'warning' : 'success'" size="small" effect="plain">{{ (row.ratio * 100).toFixed(1) }}%</el-tag>
            <span v-else class="muted">—</span>
          </template>
        </el-table-column>
      </el-table>
      <el-alert v-if="lowRatioWarnings.length > 0" type="warning" :closable="false" show-icon class="ratio-warn">
        <template #title>检查比例偏低（&lt;30%）：{{ lowRatioWarnings.map(r => r.direction).join('、') }}，应扩大检查样本量或说明原因</template>
      </el-alert>
      <div class="note-block">
        <label>审计说明</label>
        <el-input v-model="auditNote" type="textarea" :autosize="{ minRows: 3 }" :disabled="isReadonly" placeholder="概述测试情况、结果；拟调整事项及分录、未调整事项及其影响等" @change="persist" />
      </div>
    </el-card>

    <div v-if="abnormalRows.length > 0" class="abnormal-summary">
      <div class="as-header">⚠️ 异常凭证处理（{{ abnormalRows.length }} 笔）</div>
      <el-table :data="abnormalRows" border size="small" style="margin-top:8px">
        <el-table-column label="明细项目" prop="debtorName" min-width="120">
          <template #default="{ row }"><b>{{ row.debtorName || '（未填）' }}</b></template>
        </el-table-column>
        <el-table-column label="凭证号" prop="voucherNo" width="100" />
        <el-table-column label="金额" width="120" align="right">
          <template #default="{ row }">{{ fmtAmt(row.debitAmount || row.creditAmount) }}</template>
        </el-table-column>
        <el-table-column label="异常说明" prop="remark" min-width="150">
          <template #default="{ row }"><span>{{ row.remark || '未说明异常原因' }}</span></template>
        </el-table-column>
        <el-table-column label="处理决策" width="140">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.disposalDecision" size="small" placeholder="选择" @change="persist">
              <el-option label="需调整(→K4-3)" value="adjust" />
              <el-option label="不调整(说明)" value="not_adjust" />
              <el-option label="继续追查" value="investigate" />
              <el-option label="无实质影响" value="immaterial" />
            </el-select>
            <el-tag v-else-if="row.disposalDecision" size="small" :type="row.disposalDecision === 'adjust' ? 'danger' : 'info'">
              {{ { adjust: '需调整', not_adjust: '不调整', investigate: '追查中', immaterial: '无影响' }[row.disposalDecision] || row.disposalDecision }}
            </el-tag>
            <span v-else class="muted">待决策</span>
          </template>
        </el-table-column>
      </el-table>
      <el-alert v-if="adjustNeededCount > 0" type="error" :closable="false" style="margin-top:8px" show-icon>
        <template #title>{{ adjustNeededCount }} 笔异常凭证需调整 → 请在 K4-3 编制相应调整分录</template>
      </el-alert>
    </div>

    <el-card shadow="never" class="conclusion-card">
      <template #header><span class="card-title">五、审计结论</span></template>
      <el-select v-model="conclusionOption" :disabled="isReadonly" size="small" class="concl-select" placeholder="选择结论模板" @change="onConclusionOption">
        <el-option label="A、未见异常" value="A" />
        <el-option label="B、除上述重大不符事项作为调整事项予以调整外，其余未见异常" value="B" />
        <el-option label="C、由于存在重大未调整事项（或审计范围受限），不可确认" value="C" />
      </el-select>
      <el-alert v-if="conclusionOption === 'B' && adjustNeededCount > 0" type="warning" :closable="false" style="margin-bottom:8px" show-icon>
        <template #title>已标记 {{ adjustNeededCount }} 笔需调整 → 请确认已在 K4-3 编制对应调整分录（AJE）</template>
      </el-alert>
      <el-alert v-if="conclusionOption === 'B' && adjustNeededCount === 0" type="info" :closable="false" style="margin-bottom:8px">
        <template #title>提示：选择了B结论（有调整事项），但上方异常凭证未标记"需调整"，请核实</template>
      </el-alert>
      <el-input v-model="conclusion" type="textarea" :autosize="{ minRows: 2 }" :disabled="isReadonly" placeholder="基于上述检查情况，形成综合审计结论..." @change="persist" />
    </el-card>

    <details class="compile-hint">
      <summary>编制提示（CAS 1314 + 负债类审计要点）</summary>
      <ul>
        <li><b>负债类核心认定=完整性</b>：负债容易少计（隐性负债/未入账义务），应重点关注期后偿付倒查、合同义务搜索、预提充分性</li>
        <li>审计目标对应四项认定：存在、<em>完整性（重点）</em>、义务、计价和分摊</li>
        <li>样本选取：测试总体扣除特定样本得抽样总体；大额、关联方、异常款项应全部测试</li>
        <li>本期发生额检查：逐笔核对记账凭证与原始凭证，检查会计处理与披露是否正确</li>
        <li>检查比例 = 检查金额 / 账面金额（自动从K4-1审定表取数）；比例偏低（&lt;30%）须扩样或说明</li>
        <li>核对内容5项（K4专属）：入账依据/会计处理/金额计量/记录期间/披露分类</li>
        <li>抽凭引擎复用序时账，科目 2245 其他流动负债（贷方/负债类）</li>
        <li>每笔凭证应标注选取原因（大额/关联方/随机/MUS高值等），便于复核追溯抽样依据</li>
      </ul>
    </details>

    <el-dialog v-model="samplingVisible" title="抽凭引擎 — 其他流动负债(2245)" width="90%" top="5vh" destroy-on-close>
      <GtVoucherSamplingEngine v-if="samplingVisible" account-code="2245" phase="final" :workpaper-id="props.wpId" :project-id="props.projectId" :year="year" @filled="onSamplesFilled" />
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
/**
 * K4TabCheck.vue — K4-4 其他流动负债检查表（凭证级测试，复用 useK1VoucherCheck）
 *
 * Spec: k4-other-current-liabilities Task 4.4（源模板对齐重建）
 * 科目 2245 其他流动负债（贷方/负债类）。源模板仅本期发生额单表。
 *
 * 增强：
 * - K4 专属 5 项核对内容（覆盖 K1 通用标签）
 * - 检查比例"账面金额"自动从 K4-1 审定表取（本期借方/贷方发生额）
 * - 测试选取原因列（大额/关联方/随机/MUS高值/其他）
 * - 真实 AI 辅助（/ai/generate-text 端点）
 * - 版本快照（scheduleAutoSnapshot）
 */
import { ref, computed, inject, onMounted, defineAsyncComponent } from 'vue'
import { ElMessage } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import { useK1VoucherCheck, type K1VoucherRow } from '../../composables/useK1VoucherCheck'
import http from '@/utils/http'
import type { WorkpaperRuntimeContext } from '../../composables/useWorkpaperScaffold'
import { WorkpaperRuntimeContextKey } from '../../composables/useWorkpaperScaffold'

const GtVoucherSamplingEngine = defineAsyncComponent(() => import('../../voucher-sampling/GtVoucherSamplingEngine.vue'))

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
  year?: number
}>()
const emit = defineEmits<{
  (e: 'save', itemId: string, value: any): void
  (e: 'navigate-sheet', sheetName: string): void
}>()
const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const runtime = inject<WorkpaperRuntimeContext | null>(WorkpaperRuntimeContextKey, null)

const year = computed(() => props.year ?? new Date().getFullYear())
const allResponsesRef = computed(() => props.allResponses)

// ═══ K4 专属核对内容标签（覆盖 K1 通用的 5 项）═══
const K4_CHECK_LABELS = [
  '入账依据充分（预提有合同/协议/计算表支撑）',
  '会计处理正确（科目归类/方向对）',
  '金额计量准确（与合同/计算表/发票一致）',
  '记录期间正确（归属本期非跨期）',
  '披露分类恰当（流动/非流动/列报）',
] as const

const {
  itemId,
  criteria, occurrenceRows, auditNote, conclusion, conclusionOption,
  checkRatios, lowRatioWarnings, abnormalRows,
  occurrenceDebitChecked, occurrenceCreditChecked,
  load, addOccurrenceRow, removeOccurrenceRow,
  fillFromSamples, serialize,
} = useK1VoucherCheck({ allResponses: allResponsesRef as any, itemId: 'K4-4-voucher-check' })

// 用 K4 专属标签覆盖通用 checkLabels
const checkLabels = K4_CHECK_LABELS

// 源模板 K4-4 检查比例仅 本期借方/本期贷方（无期末余额行）
// 🔴 账面金额自动从 K4-1 审定表取（本期借方=合计行debit, 本期贷方=合计行credit）
const k41DebitTotal = computed(() => {
  const item = props.allResponses.get('K4-1-subtotal-debit')
  const v = item?.remark ?? item?.value ?? item
  return Number(v) || 0
})
const k41CreditTotal = computed(() => {
  const item = props.allResponses.get('K4-1-subtotal-credit')
  const v = item?.remark ?? item?.value ?? item
  return Number(v) || 0
})

const k4CheckRatios = computed(() => {
  const baseRatios = checkRatios.value.filter(r => r.direction !== '期末余额')
  // 用精确检查金额（仅5项全勾的行）覆盖 useK1VoucherCheck 的粗略合计
  // 如果 K4-1 有数据，用 K4-1 审定表数据覆盖账面金额
  return baseRatios.map(r => {
    let bookAmount = r.bookAmount
    let checkedAmount = r.checkedAmount
    if (r.direction === '本期借方') {
      checkedAmount = preciseCheckedDebit.value
      if (k41DebitTotal.value > 0) bookAmount = k41DebitTotal.value
    }
    if (r.direction === '本期贷方') {
      checkedAmount = preciseCheckedCredit.value
      if (k41CreditTotal.value > 0) bookAmount = k41CreditTotal.value
    }
    const ratio = bookAmount > 0 && checkedAmount > 0 ? checkedAmount / bookAmount : null
    return { ...r, bookAmount, checkedAmount, ratio }
  })
})

// ═══ 测试选取原因（每行可选） ═══
const SELECTION_REASONS = ['大额', '关联方', '随机抽样', 'MUS高值', '异常', '其他'] as const

// ═══ 核对完成度统计 ═══
/** 全部5项核对打勾的行数 = "已完成核对" */
const fullyCheckedCount = computed(() =>
  occurrenceRows.value.filter(r => r.checks.every(Boolean)).length
)
/** 核对完成率 */
const checkProgressRatio = computed(() => {
  if (occurrenceRows.value.length === 0) return 0
  return fullyCheckedCount.value / occurrenceRows.value.length
})
const checkProgressClass = computed(() => {
  if (checkProgressRatio.value >= 1) return 'progress-done'
  if (checkProgressRatio.value >= 0.5) return 'progress-half'
  return 'progress-low'
})

// ═══ 精确检查金额（仅全部5项勾选的行才计入"已检查金额"）═══
const preciseCheckedDebit = computed(() =>
  occurrenceRows.value
    .filter(r => r.checks.every(Boolean))
    .reduce((sum, r) => sum + (r.debitAmount || 0), 0)
)
const preciseCheckedCredit = computed(() =>
  occurrenceRows.value
    .filter(r => r.checks.every(Boolean))
    .reduce((sum, r) => sum + (r.creditAmount || 0), 0)
)

// ═══ 异常处理决策统计 ═══
const adjustNeededCount = computed(() =>
  abnormalRows.value.filter((r: any) => r.disposalDecision === 'adjust').length
)

onMounted(() => load())

function checkedValues(row: K1VoucherRow): number[] {
  return row.checks.map((c, i) => (c ? i : -1)).filter(i => i >= 0)
}
function setChecks(row: K1VoucherRow, vals: number[]): void {
  row.checks = K4_CHECK_LABELS.map((_, i) => vals.includes(i))
  persist()
}

const samplingVisible = ref(false)
function openSampling() { samplingVisible.value = true }
function onSamplesFilled(payload: { samples: any[], methodology?: string }) {
  fillFromSamples('occurrence', payload?.samples ?? [])
  // 自动标注选取原因：根据抽凭引擎方法学推断
  const method = payload?.methodology || ''
  const reason = method.includes('MUS') ? 'MUS高值'
    : method.includes('随机') ? '随机抽样'
    : method.includes('系统') ? '随机抽样'
    : '随机抽样' // 默认
  // 为新填入的行（尚无选取原因）打标
  for (const row of occurrenceRows.value) {
    if (!(row as any).selectionReason) {
      ;(row as any).selectionReason = reason
    }
  }
  samplingVisible.value = false
  persist()
}

function persist() {
  const data = serialize()
  props.allResponses.set(itemId, { item_id: itemId, conclusion: null, remark: data })
  emit('save', itemId, { remark: data })
  // 版本快照
  scheduleAutoSnapshot()
}

function scheduleAutoSnapshot() {
  try { runtime?.version?.scheduleAutoSnapshot?.() } catch { /* silent */ }
}

function onConclusionOption(val: string) {
  const map: Record<string, string> = {
    A: '经对其他流动负债本期发生额进行凭证检查，未发现异常事项。',
    B: '除上述重大不符事项应当作为调整事项予以调整外，其余未发现异常。',
    C: '由于存在重大未调整事项（或审计范围受到限制无法获取充分、适当证据），不可确认。',
  }
  if (map[val] && !conclusion.value) conclusion.value = map[val]
  persist()
}
function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return Number(val).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
function abnormalRowClass({ row }: { row: K1VoucherRow }): string { return row.abnormal ? 'abnormal-row' : '' }

// ═══ 真实 AI 辅助（接统一 /ai/generate-text 端点） ═══
async function handleAiGenerate(): Promise<void> {
  try {
    const abnormalSummary = abnormalRows.value.length > 0
      ? `异常凭证${abnormalRows.value.length}笔：${abnormalRows.value.map(r => `${r.debtorName || '未填'}(${r.remark || '未说明'})`).join('；')}`
      : '未发现异常凭证'
    const ratioSummary = k4CheckRatios.value
      .map(r => `${r.direction}：账面${fmtAmt(r.bookAmount)}，检查${fmtAmt(r.checkedAmount)}，比例${r.ratio != null ? (r.ratio * 100).toFixed(1) + '%' : '—'}`)
      .join('；')

    const res = await http.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      prompt: '请根据凭证检查情况，生成K4其他流动负债检查表的审计说明（概述测试情况、测试结果、异常事项及处理意见）',
      context: {
        科目: '2245 其他流动负债（负债类，完整性为核心认定）',
        检查比例: ratioSummary,
        异常情况: abnormalSummary,
        检查笔数: String(occurrenceRows.value.length),
        年度: String(year.value),
      },
      existingContent: auditNote.value || '',
      section: 'K4-4-voucher-check-note',
    })
    const content = res?.data?.data?.content || res?.data?.content || ''
    if (content) {
      auditNote.value = auditNote.value ? `${auditNote.value}\n\n${content}` : content
      persist()
      ElMessage.success('AI 已生成审计说明')
    } else {
      ElMessage.warning('AI 未返回内容')
    }
  } catch {
    ElMessage.warning('AI 生成失败，请稍后重试')
  }
}

function handleReview() { openReviewDialog('K4-4-check') }
</script>

<style scoped>
.k4-tab-check { padding: 12px 14px; font-size: var(--wp-font-size, 13px); }

/* 方法论琥珀块 */
.methodology-block { border-left: 4px solid #f59e0b; background: #fffbeb; border-radius: 4px; padding: 10px 14px; margin-bottom: 10px; }
.methodology-title { font-weight: 600; color: #92400e; margin-bottom: 4px; font-size: 12px; }
.methodology-content { font-size: 12px; color: #78350f; line-height: 1.6; }
.guide-banner { display: grid; grid-template-columns: repeat(4, 1fr); gap: 6px; background: linear-gradient(135deg, #eef4ff 0%, #e0ecff 100%); border: 1px solid #c6dbff; border-radius: 6px; padding: 7px 12px; margin-bottom: 10px; }
.guide-step { display: flex; align-items: center; gap: 6px; font-size: 12px; color: #1e40af; }
.gs-no { display: inline-flex; align-items: center; justify-content: center; width: 18px; height: 18px; border-radius: 50%; background: #2563eb; color: #fff; font-size: 11px; font-weight: 600; flex-shrink: 0; }
.section-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; }
.sheet-title { font-size: 15px; font-weight: 600; margin: 0; }
.head-actions { display: flex; gap: 8px; align-items: center; }
.audit-objective { margin-bottom: 10px; }
.audit-objective :deep(.el-alert__content) { padding: 2px 0; }
.ao-title { font-weight: 600; }
.ao-list { margin: 4px 0 0; padding-left: 18px; line-height: 1.55; font-size: 12px; }
.section-card { margin-bottom: 10px; }
.section-card :deep(.el-card__header) { padding: 8px 14px; }
.section-card :deep(.el-card__body) { padding: 12px 14px; }
.card-title { font-weight: 600; }
.card-header-row { display: flex; align-items: center; justify-content: space-between; }
.criteria-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px 18px; }
.cg-item { display: flex; flex-direction: column; gap: 4px; }
.cg-item.cg-full { grid-column: 1 / -1; }
.cg-item label { font-size: 12px; color: var(--el-text-color-secondary); }
.cg-inline { display: flex; align-items: center; gap: 5px; }
.cg-unit { font-size: 12px; color: var(--el-text-color-secondary); }
.num-sm { width: 78px; }
.num-md { width: 130px; }
.header-right { display: flex; align-items: center; gap: 8px; }
.check-progress { font-size: 12px; color: var(--el-text-color-secondary); }
.check-progress.progress-done { color: var(--el-color-success); font-weight: 600; }
.check-progress.progress-half { color: var(--el-color-warning); }
.check-progress.progress-low { color: var(--el-text-color-placeholder); }
.voucher-table { font-size: var(--wp-font-size, 13px); }
.amount-cell { font-variant-numeric: tabular-nums; }
.amount-input { width: 100%; }
.col-help { cursor: help; border-bottom: 1px dashed var(--el-border-color); }
.check-group { display: flex; flex-wrap: wrap; gap: 0 4px; }
.check-group :deep(.el-checkbox) { margin-right: 4px; }
.table-total { padding: 6px 12px; text-align: right; font-size: 12px; color: var(--el-text-color-regular); font-weight: 600; }
.voucher-table :deep(.abnormal-row td) { background-color: #fef2f2 !important; }
.ratio-table { max-width: 640px; }
.ratio-warn { margin-top: 12px; }
.muted { color: var(--el-text-color-placeholder); }
.note-block { margin-top: 14px; display: flex; flex-direction: column; gap: 6px; }
.note-block label { font-size: 12px; color: var(--el-text-color-secondary); }
.abnormal-summary { margin-bottom: 10px; padding: 10px 12px; border-radius: 6px; background: #fef2f2; border: 1px solid #fecaca; }
.as-header { font-weight: 600; color: var(--el-color-danger); margin-bottom: 6px; }
.as-list { padding-left: 18px; margin: 0; line-height: 1.7; color: var(--el-color-danger-dark-2); }
.conclusion-card { margin-bottom: 10px; }
.conclusion-card :deep(.el-card__header) { padding: 8px 14px; }
.conclusion-card :deep(.el-card__body) { padding: 12px 14px; }
.concl-select { width: 100%; margin-bottom: 8px; }
.compile-hint { margin-top: 6px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 18px; margin-top: 8px; line-height: 1.7; }
</style>
