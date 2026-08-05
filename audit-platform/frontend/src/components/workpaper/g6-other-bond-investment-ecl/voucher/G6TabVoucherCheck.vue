<template>
  <div class="g6-voucher-check">
  <!-- 抽样方法学（来自抽凭引擎回填，底稿正文可见 → 归档与复核可追溯） -->
  <WpSamplingMethodologyBar :methodology="methodology" />

    <div class="guide-banner">
      <div><b>1</b> 确认测试总体</div>
      <div><b>2</b> 特定项目全部测试</div>
      <div><b>3</b> 抽取本期及期后样本</div>
      <div><b>4</b> 完成六项核对并评价例外</div>
    </div>

    <div class="section-head">
      <h3>G6-15 其他债权投资凭证检查表</h3>
      <div class="head-actions">
        <GtIndexChip value="wp:G6-15" :context-project-id="projectId" />
        <GtIndexChip value="wp:G6-12" :context-project-id="projectId" />
        <GtIndexChip value="wp:G6-14" :context-project-id="projectId" />
        <el-tag size="small" type="info">本期 {{ vc.occurrenceRows.value.length }} · 期后 {{ vc.postPeriodRows.value.length }}</el-tag>
        <el-tag v-if="vc.abnormalRows.value.length" size="small" type="danger">异常 {{ vc.abnormalRows.value.length }}</el-tag>
        <el-button size="small" @click="openReviewDialog('G6-15-voucher-check')">复核</el-button>
        <G6EclImportExportDropdown
          :wp-id="wpId"
          sheet="G6-15"
          :disabled="isReadonly"
          @imported="onImported"
        />
      </div>
    </div>

    <el-alert type="info" :closable="false" show-icon class="objective">
      <template #title><b>一、审计目标</b></template>
      <ol>
        <li>记录的其他债权投资真实存在，并记录于恰当账户；</li>
        <li>相关投资由被审计单位拥有或控制；</li>
        <li>初始成本、利息、公允价值、减值和处置等计量与列报恰当。</li>
      </ol>
    </el-alert>

    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="card-header">
          <span>二、样本选取标准与规模</span>
          <el-button size="small" link type="primary" @click="showSamplingGuide = true">选样方法说明</el-button>
        </div>
      </template>
      <div class="criteria-grid">
        <div class="criteria-item">
          <label>测试总体—借方</label>
          <div class="inline">
            <el-input-number v-model="vc.criteria.value.populationDebitCount" :controls="false" :disabled="isReadonly" size="small" />
            <span>笔</span>
            <el-input-number v-model="vc.criteria.value.populationDebitAmount" :controls="false" :disabled="isReadonly" size="small" />
            <span>元</span>
          </div>
        </div>
        <div class="criteria-item">
          <label>测试总体—贷方</label>
          <div class="inline">
            <el-input-number v-model="vc.criteria.value.populationCreditCount" :controls="false" :disabled="isReadonly" size="small" />
            <span>笔</span>
            <el-input-number v-model="vc.criteria.value.populationCreditAmount" :controls="false" :disabled="isReadonly" size="small" />
            <span>元</span>
          </div>
        </div>
        <div class="criteria-item full">
          <label>特定样本说明</label>
          <el-input v-model="vc.criteria.value.specificSample" :disabled="isReadonly" size="small"
            placeholder="大额、关联方/关联交易、异常项目全部测试" />
        </div>
        <div class="criteria-item">
          <label>特定样本（全部测试）</label>
          <div class="inline">
            <el-input-number v-model="vc.criteria.value.specificSampleCount" :controls="false" :disabled="isReadonly" size="small" />
            <span>笔</span>
            <el-input-number v-model="vc.criteria.value.specificSampleAmount" :controls="false" :disabled="isReadonly" size="small" />
            <span>元</span>
          </div>
        </div>
        <div class="criteria-item">
          <label>抽样总体（总体 − 特定）</label>
          <div class="inline">
            <el-input-number v-model="vc.criteria.value.samplingPopulationCount" :controls="false" :disabled="isReadonly" size="small" />
            <span>笔</span>
            <el-input-number v-model="vc.criteria.value.samplingPopulationAmount" :controls="false" :disabled="isReadonly" size="small" />
            <span>元</span>
          </div>
        </div>
        <div class="criteria-item">
          <label>代表性样本量 / 方法</label>
          <div class="inline">
            <el-input-number v-model="vc.criteria.value.sampleSize" :controls="false" :disabled="isReadonly" size="small" />
            <span>笔</span>
            <el-select v-model="vc.criteria.value.samplingMethod" :disabled="isReadonly" size="small">
              <el-option label="随机选样" value="随机选样" />
              <el-option label="系统选样" value="系统选样" />
              <el-option label="货币单元抽样（MUS）" value="货币单元抽样" />
              <el-option label="分层抽样" value="分层抽样" />
              <el-option label="随意选样（非统计）" value="随意选样" />
              <el-option label="选取全部项目" value="选取全部项目" />
            </el-select>
          </div>
        </div>
        <div class="criteria-item">
          <label>本期发生额分母—借方</label>
          <el-input-number v-model="vc.criteria.value.bookDebitOccurrence" :controls="false" :disabled="isReadonly" size="small" />
        </div>
        <div class="criteria-item">
          <label>本期发生额分母—贷方</label>
          <el-input-number v-model="vc.criteria.value.bookCreditOccurrence" :controls="false" :disabled="isReadonly" size="small" />
        </div>
        <div class="criteria-item full">
          <label>抽样过程</label>
          <el-input v-model="vc.criteria.value.samplingProcess" type="textarea" :autosize="{ minRows: 2 }"
            :disabled="isReadonly" placeholder="记录抽样工具、参数、样本数量及选样过程底稿索引" />
        </div>
      </div>
      <el-alert type="warning" :closable="false" class="sampling-tip">
        测试总体 → 大额/关联方/异常等特定项目全部测试 → 剩余总体实施审计抽样。特定项目检查不能推断至总体。
      </el-alert>
    </el-card>

    <div class="summary-strip">
      <div>
        <span>本期借方检查</span>
        <b>{{ fmtAmount(vc.occurrenceDebitChecked.value) }}</b>
        <el-tag size="small" :type="ratioType(vc.debitRatio.value)">{{ fmtRatio(vc.debitRatio.value) }}</el-tag>
      </div>
      <div>
        <span>本期贷方检查</span>
        <b>{{ fmtAmount(vc.occurrenceCreditChecked.value) }}</b>
        <el-tag size="small" :type="ratioType(vc.creditRatio.value)">{{ fmtRatio(vc.creditRatio.value) }}</el-tag>
      </div>
      <div><span>期后借方</span><b>{{ fmtAmount(vc.postDebitChecked.value) }}</b></div>
      <div><span>期后贷方</span><b>{{ fmtAmount(vc.postCreditChecked.value) }}</b></div>
    </div>

    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="card-header table-tools">
          <div>
            <el-segmented v-model="vc.activePeriod.value" :options="periodOptions" size="small" />
            <el-segmented v-model="vc.activeTab.value" :options="tabOptions" size="small" />
          </div>
      <div>
            <el-tag size="small" type="info">特定 {{ vc.specificRows.value.length }} · 代表性 {{ vc.representativeRows.value.length }}</el-tag>
            <el-button v-if="!isReadonly" size="small" type="primary" plain @click="openSampling">抽凭</el-button>
            <el-button v-if="!isReadonly" size="small" @click="vc.addRow()">＋ 手工新增</el-button>
          </div>
        </div>
      </template>

      <p class="section-description">
        {{ vc.activePeriod.value === 'occurrence' ? '三、测试 — 1. 本期发生额检查' : '三、测试 — 2. 期后处置、新增检查' }}
        <span v-if="vc.activePeriod.value === 'post'" class="muted">（抽凭年度 {{ samplingYear }}，默认 1–3 月）</span>
      </p>

      <el-table
        :data="pagedRows"
        border
        size="small"
        row-key="id"
        :max-height="460"
        :row-class-name="rowClassName"
      >
        <el-table-column label="#" prop="seq" width="46" fixed align="center" />

        <template v-if="vc.activeTab.value === 'base'">
          <el-table-column label="日期" width="122">
            <template #default="{ row }">
              <el-date-picker v-if="!isReadonly" v-model="row.date" type="date" format="YYYY-MM-DD"
                value-format="YYYY-MM-DD" size="small" style="width: 100%" />
              <span v-else>{{ row.date || '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="凭证编号" width="110">
            <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.voucherNo" size="small" /><span v-else>{{ row.voucherNo }}</span></template>
          </el-table-column>
          <el-table-column label="业务内容" min-width="160">
            <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.businessContent" size="small" /><span v-else>{{ row.businessContent }}</span></template>
          </el-table-column>
          <el-table-column label="业务类型" width="130">
            <template #default="{ row }">
              <el-select v-if="!isReadonly" v-model="row.businessType" size="small" clearable>
                <el-option v-for="item in businessTypes" :key="item" :label="item" :value="item" />
              </el-select>
              <span v-else>{{ row.businessType }}</span>
            </template>
          </el-table-column>
          <el-table-column label="对方科目" width="120">
            <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.counterAccount" size="small" /><span v-else>{{ row.counterAccount }}</span></template>
          </el-table-column>
          <el-table-column label="对方明细科目" width="130">
            <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.detailAccount" size="small" /><span v-else>{{ row.detailAccount }}</span></template>
          </el-table-column>
          <el-table-column label="借方金额" width="125" align="right">
            <template #default="{ row }"><el-input-number v-if="!isReadonly" v-model="row.debitAmount" :controls="false" size="small" /><span v-else>{{ fmtAmount(row.debitAmount) }}</span></template>
          </el-table-column>
          <el-table-column label="贷方金额" width="125" align="right">
            <template #default="{ row }"><el-input-number v-if="!isReadonly" v-model="row.creditAmount" :controls="false" size="small" /><span v-else>{{ fmtAmount(row.creditAmount) }}</span></template>
          </el-table-column>
          <el-table-column label="选样类别" width="110">
            <template #default="{ row }">
              <el-select v-if="!isReadonly" v-model="row.selectionCategory" size="small">
                <el-option label="特定项目" value="specific" />
                <el-option label="代表性抽样" value="representative" />
                <el-option label="手工补录" value="manual" />
              </el-select>
              <span v-else>{{ selectionLabel(row.selectionCategory) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="来源/选样原因" min-width="150">
            <template #default="{ row }">
              <div>{{ row.source || '手工' }}</div>
              <small class="muted">{{ row.selectionReason }}</small>
            </template>
          </el-table-column>
          <el-table-column label="附件" width="88" align="center">
            <template #default="{ row }">
              <el-upload :show-file-list="false" accept="image/*,.pdf"
                :before-upload="(file: File) => vc.handleRowOcr(row, file)" :disabled="isReadonly">
                <el-button link size="small" :loading="vc.ocrLoadingRowId.value === row.id"
                  :title="row.attachmentId ? `已落库 ${row.attachmentId}` : (row.attachment || '上传')">
                  <el-icon :class="{ attached: row.attachmentId || row.attachment }"><Paperclip /></el-icon>
                </el-button>
              </el-upload>
            </template>
          </el-table-column>
        </template>

        <template v-else-if="vc.activeTab.value === 'checks'">
          <el-table-column label="凭证编号" prop="voucherNo" width="110" fixed />
          <el-table-column label="支持性文件" min-width="170">
            <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.supportingDoc" size="small" /><span v-else>{{ row.supportingDoc }}</span></template>
          </el-table-column>
          <el-table-column v-for="(check, index) in checkFields" :key="check.key"
            :label="`${index + 1}.${check.short}`" width="112" align="center">
            <template #default="{ row }">
              <el-select :model-value="row[check.key]" :disabled="isReadonly" size="small"
                @update:model-value="(value: any) => vc.setCheck(row, check.key, value)">
                <el-option label="— 未检查" value="" />
                <el-option label="Y 通过" value="Y" />
                <el-option label="N 不通过" value="N" />
                <el-option label="N/A 不适用" value="NA" />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="90" align="center">
            <template #default="{ row }">
              <el-tag v-if="row.isAbnormal" type="danger" size="small">异常</el-tag>
              <el-tag v-else-if="vc.isAllChecked(row)" type="success" size="small">已完成</el-tag>
              <el-tag v-else type="warning" size="small">待完成</el-tag>
            </template>
          </el-table-column>
        </template>

        <template v-else>
          <el-table-column label="凭证编号" prop="voucherNo" width="110" fixed />
          <el-table-column label="索引号" width="110">
            <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.indexRef" size="small" /><GtIndexChip v-else-if="row.indexRef" :value="row.indexRef" :context-project-id="projectId" /></template>
          </el-table-column>
          <el-table-column label="人工标记异常" width="110" align="center">
            <template #default="{ row }"><el-switch :model-value="row.manualAbnormal" :disabled="isReadonly" @change="(v: any) => vc.setManualAbnormal(row, !!v)" /></template>
          </el-table-column>
          <el-table-column label="是否异常" width="82" align="center">
            <template #default="{ row }"><el-tag :type="row.isAbnormal ? 'danger' : 'success'" size="small">{{ row.isAbnormal ? '是' : '否' }}</el-tag></template>
          </el-table-column>
          <el-table-column label="异常说明" min-width="180">
            <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.abnormalNote" type="textarea" :autosize="{ minRows: 1, maxRows: 3 }" /><span v-else>{{ row.abnormalNote }}</span></template>
          </el-table-column>
          <el-table-column label="风险等级" width="95">
            <template #default="{ row }">
              <el-select v-if="!isReadonly" v-model="row.riskLevel" size="small" clearable>
                <el-option label="高" value="高" /><el-option label="中" value="中" /><el-option label="低" value="低" />
              </el-select>
              <span v-else>{{ row.riskLevel }}</span>
            </template>
          </el-table-column>
          <el-table-column label="处理建议" min-width="160">
            <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.suggestion" size="small" /><span v-else>{{ row.suggestion }}</span></template>
          </el-table-column>
          <el-table-column label="备注说明" min-width="150">
            <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.remark" size="small" /><span v-else>{{ row.remark }}</span></template>
          </el-table-column>
        </template>

        <el-table-column v-if="!isReadonly" label="操作" width="58" fixed="right" align="center">
          <template #default="{ row }"><el-button link type="danger" size="small" @click="vc.removeRow(row.id)">删</el-button></template>
        </el-table-column>
      </el-table>
      <div class="pager-row">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :total="vc.currentRows.value.length"
          :page-sizes="[20, 50, 100]"
          layout="total, sizes, prev, pager, next"
          small
          background
        />
      </div>
    </el-card>

    <el-alert v-if="qualityWarnings.length" type="warning" :closable="false" show-icon class="quality-gate">
      <template #title>完成性检查：{{ qualityWarnings.join('；') }}</template>
    </el-alert>
    <el-alert v-else type="success" :closable="false" show-icon class="quality-gate" title="样本计划、逐笔核对和例外说明已完成" />

    <el-card v-if="vc.rowValidationErrors.value.length" shadow="never" class="section-card">
      <template #header><b>字段质量问题（{{ vc.rowValidationErrors.value.length }} 笔）</b></template>
      <ul class="exception-list">
        <li v-for="item in vc.rowValidationErrors.value.slice(0, 12)" :key="item.id">
          <b>{{ item.voucherNo || '无凭证号' }}</b> — {{ item.errors.join('；') }}
        </li>
      </ul>
    </el-card>

    <el-card v-if="vc.abnormalRows.value.length" shadow="never" class="section-card">
      <template #header><b>异常凭证摘要（{{ vc.abnormalRows.value.length }} 笔）</b></template>
      <ul class="exception-list">
        <li v-for="row in vc.abnormalRows.value" :key="row.id">
          <b>{{ row.voucherNo || '无凭证号' }}</b> · {{ row.businessType || row.businessContent || '未填写业务内容' }}
          — {{ row.abnormalNote || '异常原因待补充' }}
          <span v-if="row.riskLevel" class="muted">（风险{{ row.riskLevel }}）</span>
        </li>
      </ul>
    </el-card>

    <el-card shadow="never" class="section-card">
      <template #header><b>四、审计说明</b></template>
      <el-input v-model="auditNote" type="textarea" :disabled="isReadonly" :autosize="{ minRows: 3 }"
        placeholder="概述抽样总体、方法、样本覆盖、六项核对结果、异常处理及范围限制。" />
    </el-card>

    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="card-header">
          <b>五、审计结论</b>
          <el-button size="small" type="primary" link :disabled="isReadonly || !aiAvailable" :loading="aiLoading" @click="generateConclusion">AI 生成</el-button>
        </div>
      </template>
      <el-select v-model="conclusionOption" :disabled="isReadonly" size="small" class="conclusion-select" @change="applyConclusion">
        <el-option label="A、未见异常" value="A" />
        <el-option label="B、除重大不符事项外未见异常" value="B" />
        <el-option label="C、存在重大未调整事项或范围受限" value="C" />
      </el-select>
      <el-input v-model="conclusion" type="textarea" :disabled="isReadonly" :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="基于样本覆盖及例外事项形成结论。" />
    </el-card>

    <details class="guide-details">
      <summary>📋 编制提示</summary>
      <div class="guide-content">
        <p>1. 本表用于对科目 1503 本期发生额及期后处置/新增进行凭证检查，验证存在、权利、计价与截止。</p>
        <p>2. 编制顺序：①填写测试总体（借/贷笔数与金额）→②列明须全部测试的特定样本 →③确定抽样总体=总体−特定 →④用抽凭引擎或手工补样本。</p>
        <p>3. 本期发生额与期后样本分 Tab 编制；期后样本注意截止日（资产负债表日）前后归属，勿混入本期。</p>
        <p>4. 每笔样本完成六项核对（记账凭证、合同/交割、资金收付、计价、截止、披露相关）；未完成核对的行会高亮提示。</p>
        <p>5. 异常凭证须填写异常说明与风险等级，并在「异常凭证摘要」中评价；拟调整事项索引至 G6-4。</p>
        <p>6. 覆盖率过低（如&lt;30%）或明显&gt;100% 时先复核总体/样本口径，再撰写审计说明与结论。</p>
        <p>7. 结论建议与 G6-1 审定、G6-4 调整、G6A 程序执行情况交叉引用；导入导出后请重新核对样本完整性。</p>
      </div>
    </details>

    <el-dialog v-model="samplingVisible" :title="`抽凭引擎 — ${vc.activePeriod.value === 'occurrence' ? '本期发生额' : '期后处置、新增'}`"
      width="90%" top="5vh" destroy-on-close>
      <GtVoucherSamplingEngine
        v-if="samplingVisible"
        account-code="1503"
        phase="final"
        default-method="random"
        :workpaper-id="wpId"
        :project-id="projectId"
        :year="samplingYear"
        :initial-period-range="vc.activePeriod.value === 'post' ? [1, 2, 3] : undefined"
        @filled="onSamplesFilled"
      />
    </el-dialog>

    <el-drawer v-model="showSamplingGuide" title="选取测试项目的方法" size="480px">
      <div class="sampling-guide">
        <h4>选取全部项目</h4>
        <p>总体由少量大额项目构成、存在特别风险或全查更具成本效益时适用。</p>
        <h4>选取特定项目</h4>
        <p>大额、关联方、异常及关键项目应全部测试；其结果不能推断至剩余总体。</p>
        <h4>审计抽样</h4>
        <p>剩余总体可采用随机、系统、MUS或分层抽样。统计抽样应保留随机种子、参数和总体快照。</p>
        <p><b>MUS参考：</b>样本规模＝账面价值×风险系数÷（可容忍错报－预计错报×扩展系数）。</p>
      </div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, inject, onMounted, onBeforeUnmount, ref, watch } from 'vue'
import WpSamplingMethodologyBar from '../../shared/WpSamplingMethodologyBar.vue'
import { useSamplingMethodologyPersist, buildChecklistDirectPersist, snapshotToResponseMap } from '../../composables/shared/useSamplingMethodologyPersist'
import type { SamplingMethodologySnapshot } from '../../composables/shared/samplingFillTarget'
import { Paperclip } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import G6EclImportExportDropdown from '../G6EclImportExportDropdown.vue'
import GtIndexChip from '../../GtIndexChip.vue'
import GtVoucherSamplingEngine from '../../voucher-sampling/GtVoucherSamplingEngine.vue'
import { useG6EclFormData } from '../../composables/useG6EclFormData'
import { useG6EclAiGenerate } from '../../composables/useG6EclAiGenerate'
import {
  G6_VOUCHER_BUSINESS_TYPES,
  G6_VOUCHER_CONCLUSION_KEY,
  G6_VOUCHER_CONCLUSION_TEMPLATES,
  G6_VOUCHER_CRITERIA_KEY,
  G6_VOUCHER_NOTE_KEY,
  G6_VOUCHER_ROW_KEY,
  createEmptyVoucherCriteria,
  useG6EclVoucherCheck,
} from '@/composables/useG6EclVoucherCheck'
import {
  fetchG612ImpairmentRows,
  fetchG614ReversalWriteOffData,
  G6_12_DATA_KEY,
  G6_14_DATA_KEY,
} from '@/components/workpaper/composables/g6CrossHelpers'

const props = defineProps<{
  htmlData: Record<string, any> | null
  wpId: string
  projectId: string
  isReadonly: boolean
}>()
const emit = defineEmits<{ imported: [] }>()
const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})
const wpIdRef = computed(() => props.wpId)
const projectIdRef = computed(() => props.projectId)
const formData = useG6EclFormData({ wpId: wpIdRef, projectId: projectIdRef })
const vc = useG6EclVoucherCheck(wpIdRef, projectIdRef, computed(() => props.htmlData))
const { generateAndConfirm, aiAvailable, loading: aiLoading } = useG6EclAiGenerate(wpIdRef)
const loaded = ref(false)
const auditNote = ref('')
const conclusion = ref('')
const conclusionOption = ref('')
const samplingVisible = ref(false)
const showSamplingGuide = ref(false)
const page = ref(1)
const pageSize = ref(50)
const businessTypes = G6_VOUCHER_BUSINESS_TYPES

const periodOptions = [
  { label: '本期发生额', value: 'occurrence' },
  { label: '期后处置、新增', value: 'post' },
]
const tabOptions = [
  { label: '凭证基础', value: 'base' },
  { label: '支持文件与核对', value: 'checks' },
  { label: '例外与索引', value: 'result' },
]
const checkFields = [
  { key: 'checkOriginal', short: '原始凭证' },
  { key: 'checkAuthorized', short: '授权批准' },
  { key: 'checkAccounting', short: '账务处理' },
  { key: 'checkInitialCost', short: '初始成本' },
  { key: 'checkInterest', short: '利息计算' },
  { key: 'checkFairValue', short: '公允价值' },
] as const

/** 审计年度（资产负债表日年份） */
const auditYear = computed(() => {
  const date = String(props.htmlData?.bsDate || '')
  if (/^\d{4}/.test(date)) return Number(date.slice(0, 4))
  const raw = props.htmlData?.project_context?.audit_year
    ?? props.htmlData?.projectContext?.audit_year
    ?? props.htmlData?.audit_year
  if (raw) return Number(raw) || new Date().getFullYear() - 1
  return new Date().getFullYear() - 1
})
/** 期后抽凭用次年；本期用审计年度 */
const samplingYear = computed(() =>
  vc.activePeriod.value === 'post' ? auditYear.value + 1 : auditYear.value,
)

const pagedRows = computed(() => {
  const start = (page.value - 1) * pageSize.value
  return vc.currentRows.value.slice(start, start + pageSize.value)
})

watch(() => vc.activePeriod.value, () => { page.value = 1 })

const qualityWarnings = computed(() => [...vc.gateWarnings.value])

function selectionLabel(cat: string): string {
  if (cat === 'specific') return '特定项目'
  if (cat === 'representative') return '代表性抽样'
  if (cat === 'manual') return '手工补录'
  return cat || '—'
}
function parseStored<T>(itemId: string): T | null {
  const response = formData.allResponses.value.get(itemId)
  const raw = response?.conclusion || response?.remark
  if (!raw) return null
  try { return JSON.parse(raw) as T } catch { return null }
}
function saveJson(itemId: string, value: unknown): void {
  const json = JSON.stringify(value)
  formData.debouncedSave(itemId, { conclusion: json, remark: json })
}
function fmtAmount(value: unknown): string {
  return (Number(value) || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
function fmtRatio(value: number | null): string {
  // eslint-disable-next-line gt-audit/no-amount-toFixed
  return value == null ? '未设置分母' : `${(value * 100).toFixed(1)}%`
}
function ratioType(value: number | null): 'info' | 'warning' | 'success' {
  if (value == null) return 'info'
  if (value > 1.001) return 'warning'
  if (value < 0.3) return 'warning'
  return 'success'
}
function rowClassName({ row }: { row: any }): string {
  if (row.isAbnormal) return 'row-abnormal'
  if (!vc.isAllChecked(row)) return 'row-incomplete'
  return ''
}
function openSampling(): void {
  samplingVisible.value = true
}
const methodologyStore = ref(snapshotToResponseMap(props.htmlData))
const rawMethodologyPersist = buildChecklistDirectPersist({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})
async function methodologyDirectPersist(itemId: string, remark: string) {
  // 无 allResponses 的宿主：写库同时更新本地只读表，供 bar 即时反映
  methodologyStore.value.set(itemId, { remark })
  await rawMethodologyPersist(itemId, remark)
}
/**
 * 抽样方法学留痕（R6.3/R6.4）：把 `filled` 载荷里的 methodology 落到固定 item key，
 * 并在抽凭区渲染到底稿正文 —— 复核与归档看的是底稿，不是后台抽凭日志。
 */
const { methodology, persistMethodology } = useSamplingMethodologyPersist({
  wpCode: 'G6',
  allResponses: methodologyStore,
  persist: methodologyDirectPersist,
  isReadonly: computed(() => props.isReadonly === true),
})

function onSamplesFilled(payload: { samples: any[]; fillMode?: 'append' | 'replace' | 'merge'; method?: string }): void {
  // 方法学先落库：即便回填 0 条，「抽过样且方法学如此」也是应留的痕
  void persistMethodology((payload as { methodology?: SamplingMethodologySnapshot })?.methodology)

  const result = vc.fillVoucherSamples(vc.activePeriod.value, payload.samples, {
    mode: payload.fillMode === 'merge' ? 'append' : payload.fillMode,
    method: payload.method,
    bsDate: String(props.htmlData?.bsDate || ''),
  })
  samplingVisible.value = false
  const parts = [`已填入 ${result.added} 笔`]
  if (result.skipped) parts.push(`跳过重复 ${result.skipped} 笔`)
  if (result.rejectedPostDated) parts.push(`剔除截止日前 ${result.rejectedPostDated} 笔`)
  ElMessage.success(parts.join('，'))
  refreshCrossCoverage()
}
async function applyConclusion(option: string): Promise<void> {
  const template = G6_VOUCHER_CONCLUSION_TEMPLATES[option] || ''
  if (!template) return
  if (conclusion.value && conclusion.value !== template) {
    try {
      await ElMessageBox.confirm(
        '当前结论正文与所选模板不同，是否用模板正文覆盖？',
        '替换审计结论',
        { confirmButtonText: '覆盖', cancelButtonText: '仅切换选项', type: 'warning' },
      )
      conclusion.value = template
    } catch {
      // 保留正文，只切换选项
    }
  } else {
    conclusion.value = vc.applyConclusionTemplate(option, conclusion.value)
  }
}
async function generateConclusion(): Promise<void> {
  const text = await generateAndConfirm('voucher-conclusion', conclusion.value, {
    本期样本数: vc.occurrenceRows.value.length,
    期后样本数: vc.postPeriodRows.value.length,
    特定样本数: vc.specificRows.value.length,
    代表性样本数: vc.representativeRows.value.length,
    异常样本数: vc.abnormalRows.value.length,
    未完成核对数: vc.incompleteRows.value.length,
    借方检查比例: fmtRatio(vc.debitRatio.value),
    贷方检查比例: fmtRatio(vc.creditRatio.value),
    抽样方法: vc.criteria.value.samplingMethod,
    异常摘要: vc.abnormalSummaryForAi(),
    覆盖缺口: vc.crossCoverageGaps.value,
  }, 'AI 审计结论')
  if (text) conclusion.value = text
}

async function refreshCrossCoverage(): Promise<void> {
  const [remoteG12, remoteG14] = await Promise.all([
    fetchG612ImpairmentRows(props.projectId, props.wpId),
    fetchG614ReversalWriteOffData(props.projectId, props.wpId),
  ])

  let impairmentRows = remoteG12
  if (!impairmentRows.length) {
    const g12 = parseStored<any>(G6_12_DATA_KEY)
    impairmentRows = Array.isArray(g12) ? g12 : (g12?.rows || [])
  }

  let reversals: any[] = []
  let writeOffs: any[] = []
  if (remoteG14) {
    reversals = remoteG14.reversals
    writeOffs = remoteG14.writeOffs
    if (!reversals.length && Array.isArray(remoteG14.rows)) {
      reversals = remoteG14.rows.filter((r: any) => r?.type !== '核销')
      writeOffs = remoteG14.rows.filter((r: any) => r?.type === '核销')
    }
  } else {
    const g14 = parseStored<any>(G6_14_DATA_KEY)
    reversals = Array.isArray(g14?.reversals) ? g14.reversals : (g14?.rows || [])
    writeOffs = Array.isArray(g14?.writeOffs) ? g14.writeOffs : []
  }

  vc.evaluateCrossCoverage({ impairmentRows, reversals, writeOffs })
}

watch(vc.rows, rows => {
  if (loaded.value && !props.isReadonly) saveJson(G6_VOUCHER_ROW_KEY, rows)
}, { deep: true })
watch(vc.criteria, value => {
  if (loaded.value && !props.isReadonly) saveJson(G6_VOUCHER_CRITERIA_KEY, value)
}, { deep: true })
watch(auditNote, value => {
  if (loaded.value && !props.isReadonly) formData.debouncedSave(G6_VOUCHER_NOTE_KEY, { conclusion: null, remark: value })
})
watch([conclusion, conclusionOption], ([text, option]) => {
  if (loaded.value && !props.isReadonly) saveJson(G6_VOUCHER_CONCLUSION_KEY, { text, option })
})

async function loadStoredData(): Promise<void> {
  await formData.loadAll()
  const storedRows = parseStored<any[]>(G6_VOUCHER_ROW_KEY)
  if (storedRows) vc.loadRows(storedRows)
  else if (props.htmlData?.voucherCheck) vc.loadRows(props.htmlData.voucherCheck)

  vc.criteria.value = {
    ...createEmptyVoucherCriteria(),
    ...(parseStored<any>(G6_VOUCHER_CRITERIA_KEY) || props.htmlData?.voucherCheck?.criteria || {}),
  }
  const note = formData.allResponses.value.get(G6_VOUCHER_NOTE_KEY)
  auditNote.value = note?.remark || props.htmlData?.voucherCheck?.auditNote || ''
  const storedConclusion = parseStored<{ text?: string; option?: string }>(G6_VOUCHER_CONCLUSION_KEY)
  conclusion.value = storedConclusion?.text || props.htmlData?.voucherCheck?.conclusion || ''
  conclusionOption.value = storedConclusion?.option || props.htmlData?.voucherCheck?.conclusionOption || ''
  refreshCrossCoverage()
}
async function onImported(): Promise<void> {
  loaded.value = false
  await loadStoredData()
  loaded.value = true
  emit('imported')
  ElMessage.success('G6-15 导入数据已重新加载')
}

onMounted(async () => {
  await loadStoredData()
  loaded.value = true
})

function flushPersist(): void {
  if (props.isReadonly || !loaded.value) return
  saveJson(G6_VOUCHER_ROW_KEY, vc.rows.value)
  saveJson(G6_VOUCHER_CRITERIA_KEY, vc.criteria.value)
  formData.debouncedSave(G6_VOUCHER_NOTE_KEY, { conclusion: null, remark: auditNote.value })
  saveJson(G6_VOUCHER_CONCLUSION_KEY, { text: conclusion.value, option: conclusionOption.value })
  formData.flushPending()
}

onBeforeUnmount(() => {
  flushPersist()
})

defineExpose({
  toJSON: () => ({
    ...vc.toJSON(),
    auditNote: auditNote.value,
    conclusion: conclusion.value,
    conclusionOption: conclusionOption.value,
  }),
})
</script>

<style scoped>
.g6-voucher-check { padding: 12px; font-size: var(--gt-font-size-sm); }
.guide-banner { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; padding: 10px 12px; margin-bottom: 12px; background: var(--gt-color-bg-fill); border: 1px solid var(--gt-color-border); }
.guide-banner div { text-align: center; color: var(--gt-color-text-secondary); }
.guide-banner b { display: inline-flex; width: 20px; height: 20px; justify-content: center; align-items: center; margin-right: 4px; border-radius: 50%; background: var(--gt-color-primary); color: var(--gt-color-white); }
.section-head, .card-header, .table-tools, .head-actions, .inline, .summary-strip { display: flex; align-items: center; }
.section-head, .card-header, .table-tools { justify-content: space-between; }
.section-head h3 { margin: 0; font-size: var(--gt-font-size-lg); }
.head-actions, .inline, .table-tools > div { gap: 8px; }
.objective, .section-card, .quality-gate { margin-bottom: 14px; }
.objective ol { margin: 6px 0 0; padding-left: 20px; line-height: 1.7; }
.criteria-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px 18px; }
.criteria-item { display: flex; flex-direction: column; gap: 5px; }
.criteria-item.full { grid-column: 1 / -1; }
.criteria-item label { color: var(--gt-color-text-secondary); font-weight: 600; }
.criteria-item :deep(.el-input-number) { width: 150px; }
.criteria-item.full :deep(.el-input), .criteria-item.full :deep(.el-textarea) { width: 100%; }
.sampling-tip { margin-top: 12px; }
.summary-strip { flex-wrap: wrap; gap: 22px; padding: 10px 14px; margin-bottom: 14px; border: 1px solid var(--gt-color-border); background: var(--gt-color-bg-page); }
.summary-strip > div { display: flex; align-items: center; gap: 8px; }
.summary-strip span { color: var(--gt-color-text-secondary); }
.summary-strip b { font-variant-numeric: tabular-nums; }
.table-tools > div { display: flex; }
.section-description { margin: 0 0 10px; font-weight: 600; }
.muted { color: var(--gt-color-text-tertiary); }
.attached { color: var(--gt-color-success); }
:deep(.row-abnormal td.el-table__cell) { background: var(--gt-color-danger-light) !important; }
:deep(.row-incomplete td.el-table__cell) { background: var(--gt-color-warning-light); }
.exception-list { margin: 0; padding-left: 20px; line-height: 1.8; }
.conclusion-select { width: 420px; margin-bottom: 10px; }
.pager-row { display: flex; justify-content: flex-end; margin-top: 10px; }
.sampling-guide { line-height: 1.7; color: var(--gt-color-text-secondary); }
.sampling-guide h4 { color: var(--gt-color-text-primary); margin-bottom: 4px; }
.guide-details { margin-top: 16px; }
.guide-details summary {
  cursor: pointer;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
  font-weight: 600;
}
.guide-content {
  padding: 8px 12px;
  background: #fffbeb;
  border-left: 3px solid #f59e0b;
  margin-top: 6px;
  font-size: 12px;
  line-height: 1.8;
}
.guide-content p { margin: 0; }
@media (max-width: 900px) {
  .guide-banner, .criteria-grid { grid-template-columns: 1fr; }
  .criteria-item.full { grid-column: auto; }
  .section-head { align-items: flex-start; gap: 10px; }
  .head-actions { flex-wrap: wrap; justify-content: flex-end; }
}
</style>
