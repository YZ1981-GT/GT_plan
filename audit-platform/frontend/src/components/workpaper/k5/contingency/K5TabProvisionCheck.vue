<!--
  K5TabProvisionCheck.vue — K5-7 预计负债检查表（凭证级测试）

  忠实反映致同源模板 K5-7（预计负债版，镜像 K1-12）：
    一、审计目标（存在/偿还义务/计价分摊 三认定）
    二、样本选取标准与规模（测试总体/特定样本/抽样总体/样本量/抽样方法/抽样过程）
    三、测试（1.本期发生额检查 2.期后实际支付/判决检查，凭证级明细 + 抽凭引擎 + 核对内容勾选）
    四、审计说明（检查比例表：本期借方/本期贷方 → 账面/检查/比例）
    五、审计结论

  复用 useK1VoucherCheck（通用凭证检查状态）+ 预计负债专属核对标签覆盖。
  科目 2701 预计负债（贷方/负债类）。

  🔴 与 K1-12 的关键差异（预计负债特异性）：
  - 核对内容5项对齐预计负债审计要点（非应收款通用）
  - 期后检查=期后实际支付/判决/转销（验证期末计量合理性），非"期后收款"
  - 检查比例仅计算本期借方/贷方（期末余额通过K5-4/5/6专项检查验证，不靠期后凭证比例）
  - 方法论上下文内嵌预计负债凭证审计关注要点
-->
<template>
  <div class="k5-tab-provision-check">
    <div class="guide-banner">
      <div class="guide-step"><span class="gs-no">1</span>确认审计目标（三认定）</div>
      <div class="guide-step"><span class="gs-no">2</span>填写样本选取标准与规模</div>
      <div class="guide-step"><span class="gs-no">3</span>抽凭执行凭证级测试</div>
      <div class="guide-step"><span class="gs-no">4</span>核对检查比例，形成结论</div>
    </div>

    <div class="section-head">
      <h3 class="sheet-title">K5-7 预计负债检查表</h3>
      <div class="head-actions">
        <el-button size="small" type="primary" link @click="handleAiGenerate">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <el-button size="small" @click="handleReview">💬 复核</el-button>
        <el-button size="small" @click="$emit('navigate-sheet', '审定表K5-1')">复核底稿</el-button>
      </div>
    </div>

    <!-- 方法论上下文（预计负债凭证检查关注要点） -->
    <div class="methodology-context">
      <p><b>预计负债凭证检查关注要点：</b>①计提凭证是否有充分依据（律师函/合同/评估报告）且金额=最佳估计数；②转销/冲回凭证是否基于义务解除的客观证据（判决/和解/保修完成）；③期后实际支付/判决结果与期末计提金额的差异是否合理；④是否存在应确认而未确认的预计负债（完整性）；⑤对方科目是否恰当（计提→营业外支出6711/管理费用6602；转销→银行存款1002/营业外收入6301）。</p>
    </div>

    <!-- 一、审计目标 -->
    <el-alert type="info" :closable="false" class="audit-objective">
      <template #title><span class="ao-title">一、审计目标（认定）</span></template>
      <ol class="ao-list">
        <li><b>存在：</b>资产负债表中记录的预计负债是存在的，且已记录在恰当的账户中；</li>
        <li><b>义务：</b>记录的预计负债是被审计单位应当履行的偿还义务；</li>
        <li><b>计价和分摊：</b>预计负债以恰当的金额包括在财务报表中，与之相关的计价或分摊调整已恰当记录，相关披露已得到恰当计量和描述。</li>
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
        <div class="cg-item">
          <label>期末余额（检查比例基准）</label>
          <div class="cg-inline">
            <el-input-number v-model="criteria.endBalance" :controls="false" :disabled="isReadonly" size="small" placeholder="期末余额" class="num-md" @change="persist" />
            <span class="cg-unit">元</span>
          </div>
        </div>
        <div class="cg-item cg-full">
          <label>抽样过程</label>
          <el-input v-model="criteria.samplingProcess" type="textarea" :autosize="{ minRows: 2 }" :disabled="isReadonly" size="small"
            placeholder="使用IDEA（XX抽样工具）选择XX数量、金额XX的样本进行测试，抽样过程和结果见相关底稿" @change="persist" />
        </div>
      </div>
    </el-card>

    <!-- 三、测试 1. 本期发生额检查 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="card-header-row">
          <span class="card-title">三、测试 — 1. 本期发生额检查</span>
          <div>
            <el-button v-if="!isReadonly" size="small" type="primary" plain @click="openSampling('occurrence')"><el-icon><MagicStick /></el-icon> 抽凭</el-button>
            <el-button v-if="!isReadonly" size="small" @click="addOccurrenceRow(); persist()">＋ 手工新增</el-button>
          </div>
        </div>
      </template>
      <el-table :data="occurrenceRows" border size="small" :max-height="360" class="voucher-table" :row-class-name="abnormalRowClass">
        <el-table-column label="#" type="index" width="42" align="center" />
        <el-table-column label="明细项目/对方单位" min-width="140">
          <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.debtorName" size="small" @change="persist" /><span v-else>{{ row.debtorName || '-' }}</span></template>
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

    <!-- 三、测试 2. 期后实际支付/判决检查 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="card-header-row">
          <span class="card-title">三、测试 — 2. 期后实际支付/判决检查</span>
          <div>
            <el-button v-if="!isReadonly" size="small" type="primary" plain @click="openSampling('post')"><el-icon><MagicStick /></el-icon> 抽凭</el-button>
            <el-button v-if="!isReadonly" size="small" @click="addPostCollectionRow(); persist()">＋ 手工新增</el-button>
          </div>
        </div>
      </template>
      <div class="post-check-hint">
        <el-icon color="#e6a23c" style="margin-right:4px"><WarningFilled /></el-icon>
        <span>期后检查目的：验证期末预计负债金额合理性。关注期后实际支付/判决/和解金额与期末计提的差异。差异较大应评估是否需追溯调整。</span>
      </div>
      <el-table :data="postCollectionRows" border size="small" :max-height="300" class="voucher-table" :row-class-name="abnormalRowClass">
        <el-table-column label="#" type="index" width="42" align="center" />
        <el-table-column label="明细项目/对方单位" min-width="140">
          <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.debtorName" size="small" @change="persist" /><span v-else>{{ row.debtorName || '-' }}</span></template>
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
        <el-table-column label="实际支付/判决金额" min-width="110" align="right">
          <template #default="{ row }"><el-input-number v-if="!isReadonly" v-model="row.creditAmount" :controls="false" size="small" class="amount-input" @change="persist" /><span v-else class="amount-cell">{{ fmtAmt(row.creditAmount) }}</span></template>
        </el-table-column>
        <el-table-column label="vs期末计提差异" width="110" align="right">
          <template #default="{ row }">
            <el-tooltip content="正数=实际支付>期末计提（少提）；负数=实际支付<期末计提（多提）" placement="top">
              <span class="formula-cell formula-underline" :class="{ 'diff-warn': row.creditAmount && Math.abs(row.creditAmount - (row.debitAmount || 0)) > 0.01 }">
                {{ row.debitAmount ? fmtAmt(row.creditAmount - row.debitAmount) : '-' }}
              </span>
            </el-tooltip>
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
          <template #default="{ row }"><el-button size="small" type="danger" link @click="removePostCollectionRow(row.id); persist()">删除</el-button></template>
        </el-table-column>
        <template #append><div class="table-total">合计　期后发生额：{{ fmtAmt(postCollectionChecked) }}</div></template>
      </el-table>
    </el-card>

    <!-- 四、审计说明（检查比例表）-->
    <el-card shadow="never" class="section-card">
      <template #header><span class="card-title">四、审计说明 — 检查比例</span></template>
      <el-table :data="k5CheckRatios" border size="small" class="ratio-table">
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
      <div class="ratio-note">
        <el-icon color="#909399"><InfoFilled /></el-icon>
        <span>预计负债期末余额的验证通过 K5-4(质保)/K5-5(弃置)/K5-6(诉讼) 专项检查完成，不纳入本表检查比例计算。</span>
      </div>
      <el-alert v-if="k5LowRatioWarnings.length > 0" type="warning" :closable="false" show-icon class="ratio-warn">
        <template #title>检查比例偏低（&lt;30%）：{{ k5LowRatioWarnings.map(r => r.direction).join('、') }}，应扩大检查样本量或说明原因</template>
      </el-alert>
      <div class="note-block">
        <label>审计说明</label>
        <el-input v-model="auditNote" type="textarea" :autosize="{ minRows: 3 }" :disabled="isReadonly" placeholder="概述测试情况、结果；拟调整事项及分录、未调整事项及其影响等" @change="persist" />
      </div>
    </el-card>

    <div v-if="abnormalRows.length > 0" class="abnormal-summary">
      <div class="as-header">⚠️ 异常凭证摘要（{{ abnormalRows.length }} 笔）</div>
      <ul class="as-list">
        <li v-for="r in abnormalRows" :key="r.id"><b>{{ r.debtorName || '（未填明细项目）' }}</b> — 凭证 {{ r.voucherNo || '-' }}：{{ r.remark || '未说明' }}</li>
      </ul>
    </div>

    <el-card shadow="never" class="conclusion-card">
      <template #header><span class="card-title">五、审计结论</span></template>
      <el-select v-model="conclusionOption" :disabled="isReadonly" size="small" class="concl-select" placeholder="选择结论模板" @change="onConclusionOption">
        <el-option label="A、未见异常" value="A" />
        <el-option label="B、除上述重大不符事项作为调整事项予以调整外，其余未见异常" value="B" />
        <el-option label="C、由于存在重大未调整事项（或审计范围受限），不可确认" value="C" />
      </el-select>
      <el-input v-model="conclusion" type="textarea" :autosize="{ minRows: 2 }" :disabled="isReadonly" placeholder="基于上述检查情况，形成综合审计结论..." @change="persist" />
    </el-card>

    <details class="compile-hint">
      <summary>编制提示（CAS13 + CAS1314）</summary>
      <ul>
        <li>审计目标对应三项认定：存在、义务、计价和分摊</li>
        <li>样本选取：测试总体扣除特定样本得抽样总体；大额计提/转销、诉讼相关、异常款项应全部测试</li>
        <li><b>本期发生额检查（核心）：</b>
          <ul style="padding-left:16px;margin:2px 0">
            <li>计提凭证(贷方2701)：核对是否有充分计提依据(律师函/合同/评估)+金额是否=最佳估计数+对方科目恰当(6711/6602)</li>
            <li>转销凭证(借方2701)：核对是否基于义务解除客观证据(判决/和解/保修到期)+对方科目恰当(1002/6301)</li>
          </ul>
        </li>
        <li><b>期后检查：</b>截止日后实际支付/判决金额 vs 期末计提金额对比，差异较大评估是否需追溯调整（CAS13§16期后事项考虑）</li>
        <li>检查比例 = 检查金额 / 账面金额；比例偏低（&lt;30%）须扩样或说明</li>
        <li>期末余额合理性通过 K5-4(质保测算)/K5-5(弃置现值)/K5-6(诉讼评估) 专项底稿验证</li>
        <li>科目 2701 预计负债（贷方/负债类）：贷方=计提增加，借方=转销减少</li>
      </ul>
    </details>

    <el-dialog v-model="samplingVisible" title="抽凭引擎 — 预计负债(2701)" width="90%" top="5vh" destroy-on-close>
      <GtVoucherSamplingEngine v-if="samplingVisible" account-code="2701" phase="final" :workpaper-id="props.wpId" :project-id="props.projectId" :year="year" @filled="onSamplesFilled" />
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
/**
 * K5TabProvisionCheck.vue — K5-7 预计负债检查表（凭证级测试，复用 useK1VoucherCheck）
 *
 * Spec: .kiro/specs/k5-provisions/ | Task: 4.5, 6.3（源模板对齐重建）
 * 科目 2701 预计负债（贷方/负债类）。
 */
import { ref, computed, inject, onMounted, defineAsyncComponent } from 'vue'
import { MagicStick, WarningFilled, InfoFilled } from '@element-plus/icons-vue'
import { useK1VoucherCheck, type K1VoucherRow } from '../../composables/useK1VoucherCheck'

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

const year = computed(() => props.year ?? new Date().getFullYear())
const allResponsesRef = computed(() => props.allResponses)

const {
  itemId, checkLabels: _originalCheckLabels,
  criteria, occurrenceRows, postCollectionRows, auditNote, conclusion, conclusionOption,
  checkRatios, lowRatioWarnings, abnormalRows,
  occurrenceDebitChecked, occurrenceCreditChecked, postCollectionChecked,
  load, addOccurrenceRow, addPostCollectionRow, removeOccurrenceRow, removePostCollectionRow,
  fillFromSamples, serialize,
} = useK1VoucherCheck({ allResponses: allResponsesRef as any, itemId: 'K5-7-voucher-check' })

/**
 * 预计负债专属核对内容5项（覆盖 K1-12 的通用标签）
 * 对齐预计负债审计特异关注点：
 * 1. 计提/转销依据充分性（律师函/合同/判决/评估报告）
 * 2. 金额与最佳估计数/实际支付一致
 * 3. 对方科目恰当（计提→6711/6602；转销→1002/6301）
 * 4. 会计期间正确（计提时点=义务确认时点；转销时点=义务解除时点）
 * 5. 与专项检查表（K5-4/5/6）结论一致
 */
const checkLabels = [
  '计提/转销依据充分（律师函/合同/判决）',
  '金额与最佳估计数或实际支付一致',
  '对方科目恰当（6711/6602/1002/6301）',
  '会计期间正确（义务确认/解除时点）',
  '与专项检查表（K5-4/5/6）结论一致',
]

/**
 * K5 检查比例表：仅计算本期借方/贷方发生额的检查比例。
 * 期末余额不参与本表比例计算（通过K5-4/5/6专项检查验证）。
 */
const k5CheckRatios = computed(() => checkRatios.value.filter(r => r.direction !== '期末余额'))
const k5LowRatioWarnings = computed(() => k5CheckRatios.value.filter(r => r.ratio != null && r.ratio < 0.3 && r.bookAmount > 0))

onMounted(() => load())

function checkedValues(row: K1VoucherRow): number[] {
  return row.checks.map((c, i) => (c ? i : -1)).filter(i => i >= 0)
}
function setChecks(row: K1VoucherRow, vals: number[]): void {
  row.checks = checkLabels.map((_, i) => vals.includes(i))
  persist()
}

const samplingVisible = ref(false)
const samplingTarget = ref<'occurrence' | 'post'>('occurrence')
function openSampling(target: 'occurrence' | 'post') { samplingTarget.value = target; samplingVisible.value = true }
function onSamplesFilled(payload: { samples: any[] }) {
  fillFromSamples(samplingTarget.value, payload?.samples ?? [])
  samplingVisible.value = false
  persist()
}

function persist() {
  const data = serialize()
  props.allResponses.set(itemId, { item_id: itemId, conclusion: null, remark: data })
  emit('save', itemId, { remark: data })
}
function onConclusionOption(val: string) {
  const map: Record<string, string> = {
    A: '未见异常。',
    B: '除上述重大不符事项应当作为调整事项予以调整外，其余未见异常。',
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
function handleAiGenerate() { emit('save', 'K5-7-ai-trigger', { remark: 'provision-voucher-check' }) }
function handleReview() { openReviewDialog('K5-7-check') }
</script>

<style scoped>
.k5-tab-provision-check { padding: 12px 14px; font-size: var(--wp-font-size, 13px); }
.methodology-context { background: #fffbeb; border-left: 4px solid #f59e0b; padding: 10px 14px; margin-bottom: 10px; border-radius: 4px; font-size: var(--wp-font-size, 13px); color: #78350f; line-height: 1.6; }
.post-check-hint { display: flex; align-items: flex-start; gap: 4px; margin-bottom: 8px; padding: 6px 10px; background: #fef3c7; border-radius: 4px; font-size: 12px; color: #92400e; line-height: 1.5; }
.ratio-note { display: flex; align-items: center; gap: 6px; margin-top: 8px; font-size: 12px; color: #909399; }
.formula-cell { font-family: 'JetBrains Mono', monospace; font-size: 12px; color: #303133; }
.formula-underline { border-bottom: 1px dashed #909399; cursor: help; }
.diff-warn { color: #e6a23c; font-weight: 600; }
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
