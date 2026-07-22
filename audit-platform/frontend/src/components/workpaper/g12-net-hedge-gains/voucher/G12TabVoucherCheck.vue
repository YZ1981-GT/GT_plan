<template>
  <div class="g12-vc" data-testid="g12-voucher-check">
    <div class="section-head">
      <h3 class="sheet-title">G12-6 净敞口套期收益凭证检查表</h3>
      <div class="head-actions">
        <el-button size="small" type="warning" :disabled="isReadonly" data-testid="g12-open-sampling" @click="showSampling = true">
          ⚡ 抽凭
        </el-button>
        <CycleImportExportDropdown :wp-id="wpId" api-prefix="g12" sheet="G12-6" :disabled="isReadonly" @imported="onImported" />
        <el-button size="small" :disabled="isReadonly" data-testid="g12-export-memo" @click="exportMemo">📄 抽样备忘</el-button>
        <el-button
          v-if="!isReadonly"
          size="small"
          type="info"
          plain
          :disabled="!vc.rows.value.length"
          data-testid="g12-sync-g125"
          @click="onSyncNetExposure"
        >勾稽 G12-5</el-button>
        <el-button
          v-if="!isReadonly"
          size="small"
          type="info"
          plain
          :disabled="!vc.rows.value.length"
          data-testid="g12-cite-fv"
          @click="onBatchCiteFv"
        >引用 G12-4 估值</el-button>
        <el-button
          v-if="!isReadonly"
          size="small"
          type="warning"
          plain
          :loading="vc.a13Pushing.value"
          :disabled="vc.quantitativeAbnormalCount.value <= 0"
          data-testid="g12-push-adj"
          @click="onPushAbnormal"
        >
          推送异常→G12-3
          <template v-if="vc.quantitativeAbnormalCount.value">（{{ vc.quantitativeAbnormalCount.value }}）</template>
        </el-button>
        <span class="chip-wrap"><GtIndexChip value="wp:G12-2" /></span>
        <el-button
          v-if="!isReadonly && projectId"
          size="small"
          type="success"
          plain
          :loading="vc.procedureMarking.value"
          :disabled="!vc.rows.value.length"
          data-testid="g12-mark-g12a"
          @click="onMarkProcedure"
        >
          {{ vc.procedureMarked.value ? '已回填 G12A（可重写）' : '回填 G12A 凭证程序' }}
        </el-button>
        <GtReviewTrigger section-id="G12-6-voucher" />
        <el-button size="small" type="primary" plain :disabled="isReadonly" @click="vc.addRow()">+ 新增</el-button>
      </div>
    </div>

    <el-alert type="info" :closable="false" class="objective-alert">
      <template #title>
        <div class="ao-wrap">
          <div class="ao-title">一、审计目标</div>
          <ol class="ao-list">
            <li>确定记录的投资收益（净敞口套期收益 6103）是否已发生，且与被审计单位有关（发生）；</li>
            <li>确定所有应当记录的净敞口套期收益是否均已记录（完整性）；</li>
            <li>确定与净敞口套期收益有关的金额及其他数据是否已恰当记录，套期会计处理与披露是否符合 CAS24（准确性、分类）。</li>
          </ol>
        </div>
      </template>
    </el-alert>

    <div class="sampling-params-card" data-testid="g12-vc-params">
      <h4 class="card-title">二、样本选取方法与规模</h4>
      <div class="params-grid">
        <div class="param-item param-item-wide">
          <span class="param-label">测试总体</span>
          <el-input
            :model-value="vc.samplingParams.value.testPopulation"
            size="small"
            :disabled="isReadonly"
            placeholder="如：科目6103本期发生额共XX笔、金额XX"
            @change="(v: string) => vc.updateSampling('testPopulation', v)"
          />
        </div>
        <div class="param-item param-item-wide">
          <span class="param-label">特定样本</span>
          <el-input
            :model-value="vc.samplingParams.value.specificSamples"
            size="small"
            :disabled="isReadonly"
            placeholder="大额、套期无效部分、Level3 估值、关联方等必选样本"
            @change="(v: string) => vc.updateSampling('specificSamples', v)"
          />
        </div>
        <div class="param-item param-item-wide">
          <span class="param-label">抽样总体</span>
          <el-input
            :model-value="vc.samplingParams.value.samplingPopulation"
            size="small"
            :disabled="isReadonly"
            placeholder="测试总体扣除特定样本后的剩余总体"
            @change="(v: string) => vc.updateSampling('samplingPopulation', v)"
          />
        </div>
        <div class="param-item">
          <span class="param-label">抽样方法</span>
          <el-select
            :model-value="vc.samplingParams.value.samplingMethod"
            size="small"
            clearable
            :disabled="isReadonly"
            style="width:100%"
            @change="(v: string) => vc.updateSampling('samplingMethod', v ?? '')"
          >
            <el-option v-for="o in G12_SAMPLING_METHOD_OPTIONS" :key="o.value" :label="o.label" :value="o.value" />
          </el-select>
        </div>
        <div class="param-item">
          <span class="param-label">目标样本量</span>
          <el-input-number
            :model-value="vc.samplingParams.value.targetSampleSize"
            size="small"
            :min="0"
            :controls="false"
            :disabled="isReadonly"
            style="width:100%"
            @change="(v: number | undefined) => vc.updateSampling('targetSampleSize', v ?? 0)"
          />
        </div>
        <div class="param-item">
          <span class="param-label">本期发生额</span>
          <div class="param-with-action">
            <el-input-number
              :model-value="vc.samplingParams.value.populationAmount"
              size="small"
              :min="0"
              :controls="false"
              :disabled="isReadonly"
              style="flex:1"
              @change="(v: number | undefined) => vc.updateSampling('populationAmount', v ?? 0)"
            />
            <el-button
              v-if="!isReadonly"
              size="small"
              link
              type="primary"
              data-testid="g12-vc-pull-population"
              :disabled="vc.g12PopulationHint.value <= 0"
              @click="vc.pullPopulationFromHedgeDetail()"
            >从G12-2带入</el-button>
          </div>
          <span v-if="vc.g12PopulationHint.value > 0" class="hint-text">
            G12-2 套期损益合计 {{ fmt(vc.g12PopulationHint.value) }}
          </span>
        </div>
        <div class="param-item">
          <span class="param-label">总体笔数</span>
          <el-input-number
            :model-value="vc.samplingParams.value.populationCount"
            size="small"
            :min="0"
            :controls="false"
            :disabled="isReadonly"
            style="width:100%"
            @change="(v: number | undefined) => vc.updateSampling('populationCount', v ?? 0)"
          />
        </div>
        <div class="param-item param-item-wide">
          <span class="param-label">抽样过程</span>
          <el-input
            :model-value="vc.samplingParams.value.samplingProcess"
            size="small"
            :disabled="isReadonly"
            placeholder="如：使用 IDEA/抽凭引擎按 MUS 或金额抽取…"
            @change="(v: string) => vc.updateSampling('samplingProcess', v)"
          />
        </div>
      </div>
      <div class="sampling-calc-row">
        <span v-if="vc.suggestedSampleSize.value != null">公式样本量：<b>{{ vc.suggestedSampleSize.value }}</b></span>
        <span v-else class="muted">填写账面价值与可容忍错报后可计算样本量</span>
        <el-button v-if="!isReadonly && vc.suggestedSampleSize.value" size="small" link type="primary" @click="onApplySuggested">采用公式样本量</el-button>
        <span class="sep">|</span>
        <span>进度 {{ vc.currentSampleSize.value }} / {{ vc.samplingParams.value.targetSampleSize || '—' }}</span>
        <el-progress :percentage="vc.progressPct.value" :stroke-width="8" style="flex:1;max-width:200px;margin-left:8px" />
      </div>
      <div class="ratio-row" data-testid="g12-vc-ratio">
        <span>已查金额（合计）{{ fmt(vc.sampleAbsAmount.value) }}</span>
        <span>本期发生额 {{ fmt(vc.samplingParams.value.populationAmount) }}</span>
        <span>检查比例 <b>{{ vc.inspectionRatioPct.value == null ? '—' : `${vc.inspectionRatioPct.value.toFixed(1)}%` }}</b></span>
      </div>
      <el-alert
        v-if="vc.lowInspectionRatio.value"
        type="warning"
        :closable="false"
        show-icon
        class="ratio-alert"
        title="检查比例低于 30%，请扩大样本量或在审计说明中解释原因。"
      />
    </div>

    <div class="check-legend methodology-block">
      <div class="legend-title">三、测试 — 核对内容说明</div>
      <ol class="legend-list">
        <li v-for="d in G12_VOUCHER_CHECK_DEFS" :key="d.key">{{ d.title }}</li>
      </ol>
      <p class="legend-note">核对项为三态：未测 / 通过 / 不通过；任一「不通过」或强制异常 → 标异常；「未测」不计入异常。套期关系编号须与 G12-2/G12-4 一致。</p>
    </div>

    <GCycleProcedureCutoffPanel
      v-if="!isReadonly && wpId && projectId"
      :wp-id="wpId"
      :project-id="projectId"
      :account-code="G12_ACCOUNT_CODE"
      cycle="g12"
      fill-target-hint="样本将回填至 G12-6 凭证检查表"
    />

    <div class="source-filter-bar" data-testid="g12-source-filter">
      <span class="filter-label">来源分池：</span>
      <el-radio-group
        :model-value="vc.sourceFilter.value"
        size="small"
        @update:model-value="(v: string | number | boolean | undefined) => { vc.sourceFilter.value = String(v) as G12VoucherSourceFilter }"
      >
        <el-radio-button value="all">全部 {{ vc.sourceCounts.value.all }}</el-radio-button>
        <el-radio-button value="抽凭">抽凭 {{ vc.sourceCounts.value['抽凭'] }}</el-radio-button>
        <el-radio-button value="截止">截止 {{ vc.sourceCounts.value['截止'] }}</el-radio-button>
        <el-radio-button value="手工">手工 {{ vc.sourceCounts.value['手工'] }}</el-radio-button>
      </el-radio-group>
      <span class="chip-wrap"><GtIndexChip value="wp:G12-6" :context-project-id="projectId" /></span>
    </div>

    <div class="cross-link-bar" data-testid="g12-net-exposure-link">
      <span class="filter-label">G12-5 勾稽：</span>
      <el-tag size="small" type="success">匹配 {{ vc.netExposureSummary.value.ok }}</el-tag>
      <el-tag size="small" type="warning">未完整 {{ vc.netExposureSummary.value.incomplete }}</el-tag>
      <el-tag size="small" type="danger">缺失 {{ vc.netExposureSummary.value.missing }}</el-tag>
      <el-tag size="small" type="info">无编号 {{ vc.netExposureSummary.value.noId }}</el-tag>
      <span class="summary-muted">按套期关系编号自动匹配净敞口检查行；点「勾稽 G12-5」可将匹配通过项回写核对⑤</span>
    </div>

    <div class="summary-bar">
      <el-tag size="small" type="info">共 {{ vc.filteredRows.value.length }} 行</el-tag>
      <el-tag size="small" type="warning">未测 {{ vc.untestedCount.value }}</el-tag>
      <el-tag size="small" :type="vc.abnormalCount.value > 0 ? 'danger' : 'success'">异常 {{ vc.abnormalCount.value }}</el-tag>
      <el-tag size="small" :type="vc.cutoffAbnormalCount.value > 0 ? 'warning' : 'info'">截止跨期 {{ vc.cutoffAbnormalCount.value }}</el-tag>
      <span class="summary-sep">|</span>
      <span>借贷 {{ fmt(vc.debitTotal.value) }} / {{ fmt(vc.creditTotal.value) }}</span>
      <span class="summary-muted">检查比例 {{ vc.inspectionRatioPct.value == null ? '—' : `${vc.inspectionRatioPct.value.toFixed(1)}%` }}</span>
    </div>

    <div v-if="vc.useVirtualScroll.value" class="virtual-toolbar">
      <el-alert type="info" :closable="false" class="virtual-hint">
        行数较多（{{ vc.filteredRows.value.length }} 行）· 建议导出或分区编辑
      </el-alert>
    </div>

    <div class="segment-tabs">
      <el-segmented v-model="vc.activeTab.value" :options="tabOptions" size="small" />
    </div>

    <el-table
      :data="vc.filteredRows.value"
      border
      stripe
      size="small"
      style="width:100%;font-size:13px"
      max-height="480"
      :row-class-name="({ row }) => row.isAbnormal ? 'g12-vc-abnormal' : ''"
    >
      <el-table-column prop="seq" label="序号" width="52" align="center" fixed />
      <template v-if="vc.activeTab.value === 'basic'">
        <el-table-column label="日期" width="110">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.voucherDate" size="small"
              @update:model-value="(v: string) => vc.updateRow(row.rowId, { voucherDate: v })" />
            <span v-else>{{ row.voucherDate }}</span>
          </template>
        </el-table-column>
        <el-table-column label="凭证编号" width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.voucherNo" size="small"
              @update:model-value="(v: string) => vc.updateRow(row.rowId, { voucherNo: v })" />
            <span v-else>{{ row.voucherNo }}</span>
          </template>
        </el-table-column>
        <el-table-column label="业务内容" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.businessContent" size="small"
              @update:model-value="(v: string) => vc.updateRow(row.rowId, { businessContent: v })" />
            <span v-else>{{ row.businessContent }}</span>
          </template>
        </el-table-column>
        <el-table-column label="套期关系编号" width="110">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.hedgeRelationId" size="small" placeholder="↔ G12-2"
              @update:model-value="(v: string) => vc.updateRow(row.rowId, { hedgeRelationId: v })" />
            <span v-else>{{ row.hedgeRelationId }}</span>
          </template>
        </el-table-column>
        <el-table-column label="对方科目" width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.counterAccount" size="small"
              @update:model-value="(v: string) => vc.updateRow(row.rowId, { counterAccount: v })" />
            <span v-else>{{ row.counterAccount }}</span>
          </template>
        </el-table-column>
        <el-table-column label="借方" width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.debitAmount" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => vc.updateRow(row.rowId, { debitAmount: v ?? 0 })" />
            <span v-else>{{ fmt(row.debitAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="贷方" width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.creditAmount" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => vc.updateRow(row.rowId, { creditAmount: v ?? 0 })" />
            <span v-else>{{ fmt(row.creditAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="来源" width="72">
          <template #default="{ row }">
            <el-tag size="small" type="info">{{ row.source || '手工' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="📎" width="60">
          <template #default="{ row }">
            <el-button size="small" link :disabled="isReadonly" :loading="ocrLoading === row.rowId" @click="uploadOcr(row)">📎</el-button>
          </template>
        </el-table-column>
      </template>
      <template v-else-if="vc.activeTab.value === 'check'">
        <el-table-column label="支持性文件" min-width="160">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.supportingDocDesc" size="small"
              @update:model-value="(v: string) => vc.updateRow(row.rowId, { supportingDocDesc: v })" />
            <span v-else>{{ row.supportingDocDesc }}</span>
            <el-button
              v-if="!isReadonly"
              link
              size="small"
              type="primary"
              data-testid="g12-cite-fv-row"
              @click="onCiteFvRow(row.rowId)"
            >引用G12-4</el-button>
          </template>
        </el-table-column>
        <el-table-column
          v-for="def in G12_VOUCHER_CHECK_DEFS"
          :key="def.key"
          :label="def.label"
          :title="def.title"
          width="88"
          align="center"
        >
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              :model-value="g12CheckSelectValue((row as any)[def.key])"
              size="small"
              @change="(v: string) => vc.updateRow(row.rowId, { [def.key]: parseG12CheckSelect(v) } as any)"
            >
              <el-option v-for="o in G12_CHECK_STATE_OPTIONS" :key="o.value" :label="o.label" :value="o.value" />
            </el-select>
            <span v-else>{{ formatG12CheckState((row as any)[def.key]) }}</span>
          </template>
        </el-table-column>
      </template>
      <template v-else>
        <el-table-column label="索引号" width="88">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.indexNo" size="small"
              @update:model-value="(v: string) => vc.updateRow(row.rowId, { indexNo: v })" />
            <GtIndexChip v-else-if="row.indexNo" :value="row.indexNo" />
          </template>
        </el-table-column>
        <el-table-column label="是否异常" width="88">
          <template #default="{ row }">
            <el-tag :type="row.isAbnormal ? 'danger' : 'success'" size="small">{{ row.isAbnormal ? '是' : '否' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="强制异常" width="88" align="center">
          <template #default="{ row }">
            <el-switch
              v-if="!isReadonly"
              :model-value="row.forceAbnormal"
              size="small"
              @update:model-value="(v: boolean) => vc.updateRow(row.rowId, { forceAbnormal: !!v })"
            />
            <span v-else>{{ row.forceAbnormal ? '是' : '否' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="异常说明" min-width="140">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.abnormalDesc" size="small"
              @update:model-value="(v: string) => vc.updateRow(row.rowId, { abnormalDesc: v })" />
            <span v-else>{{ row.abnormalDesc }}</span>
          </template>
        </el-table-column>
        <el-table-column label="风险等级" width="100">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" :model-value="row.riskLevel" size="small"
              @change="(v: string) => vc.updateRow(row.rowId, { riskLevel: v })">
              <el-option v-for="l in G12_RISK_LEVELS" :key="l.value" :label="l.label" :value="l.value" />
            </el-select>
            <span v-else>{{ row.riskLevel }}</span>
          </template>
        </el-table-column>
        <el-table-column label="备注" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.remark" size="small"
              @update:model-value="(v: string) => vc.updateRow(row.rowId, { remark: v })" />
            <span v-else>{{ row.remark }}</span>
          </template>
        </el-table-column>
      </template>
      <el-table-column v-if="!isReadonly" label="操作" width="56" fixed="right">
        <template #default="{ row }">
          <el-button link type="danger" size="small" @click="vc.removeRow(row.rowId)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-card shadow="never" class="audit-note-card">
      <template #header><div class="card-header"><span>四、审计说明</span></div></template>
      <el-input
        :model-value="vc.auditNote.value"
        type="textarea"
        :autosize="{ minRows: 5 }"
        :disabled="isReadonly"
        placeholder="填写审计说明：可概述样本选取方法、样本量、逐笔核对结果、异常事项及处理。"
        @change="vc.updateAuditNote"
      />
    </el-card>

    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="card-header">
          <span>五、审计结论</span>
          <el-button size="small" :loading="vc.aiLoading.value" :disabled="isReadonly" @click="vc.generateAiConclusion()">🤖 AI</el-button>
        </div>
      </template>
      <el-input
        :model-value="vc.auditConclusion.value"
        type="textarea"
        :autosize="{ minRows: 3 }"
        :disabled="isReadonly"
        placeholder="A、未见异常。B、除上述重大不符事项应作为调整事项予以调整外，其余未见异常。C、由于存在重大未调整事项或审计范围受限，不可确认。"
        @change="vc.updateAuditConclusion"
      />
    </el-card>

    <details class="guidance-details">
      <summary>📋 编制提示（CAS24 套期会计）</summary>
      <div class="guidance-content">
        <p>1. 本表对净敞口套期收益（6103）抽取凭证，验证发生、完整、准确及套期会计处理正确性。</p>
        <p>2. 先填写「样本选取」；可用「从G12-2带入」填充本期发生额。检查比例 = 已查样本金额 ÷ 本期发生额。</p>
        <p>3. 六项核对为三态；截止跨期可强制异常。可用「勾稽 G12-5」按套期关系编号回写核对⑤；「引用 G12-4 估值」写入支持性文件并回写核对⑥。</p>
        <p>4. 抽凭引擎回填时自动写入 MUS 间隔/可容忍错报等至「抽样过程」。编制完成后可「回填 G12A」步骤 10。</p>
      </div>
    </details>

    <el-dialog
      v-model="showSampling"
      title="G12-6 抽凭引擎（科目6103）"
      width="960px"
      destroy-on-close
      append-to-body
    >
      <GtVoucherSamplingEngine
        v-if="showSampling && wpId && projectId"
        :account-code="G12_ACCOUNT_CODE"
        phase="final"
        default-method="mus"
        :workpaper-id="wpId"
        :project-id="projectId"
        :year="engineYear"
        @filled="onSampleFilled"
      />
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, toRef, computed, onMounted, onBeforeUnmount, inject } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/utils/http'
import {
  useG12VoucherCheck,
  type G12VoucherRow,
  type G12VoucherSourceFilter,
} from '../../composables/useG12VoucherCheck'
import { G12_ACCOUNT_CODE, G12_RISK_LEVELS } from '../../composables/g12Constants'
import {
  G12_VOUCHER_CHECK_DEFS,
  G12_SAMPLING_METHOD_OPTIONS,
  G12_CHECK_STATE_OPTIONS,
  formatG12CheckState,
  g12CheckSelectValue,
  parseG12CheckSelect,
} from '../../composables/g12VoucherConstants'
import { G12A_VOUCHER_PROGRAM_NOS, G12A_PROCEDURE_SHEET } from '../../composables/g12VoucherCross'
import { confirmNavigateToSheet, dispatchProcedureFocus } from '../../composables/g8CrossHelpers'
import { GCYCLE_CUTOFF_EVENT, type GCycleCutoffFilledDetail } from '../../composables/gCycleCutoffFill'
import { useWorkpaperAuditYear } from '../../composables/workpaperAuditYear'
import type { ChecklistResponse } from '../../composables/useF1FormData'
import GtVoucherSamplingEngine from '../../voucher-sampling/GtVoucherSamplingEngine.vue'
import CycleImportExportDropdown from '../../shared/CycleImportExportDropdown.vue'
import GCycleProcedureCutoffPanel from '../../shared/GCycleProcedureCutoffPanel.vue'
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  projectId: string
  isReadonly: boolean
  debouncedSave: (id: string, d: Partial<ChecklistResponse>) => void
}>()

const emit = defineEmits<{ imported: [] }>()
const jumpToSection = inject<((sheetName: string) => void) | null>('jumpToSection', null)
const auditYearRef = useWorkpaperAuditYear()
const engineYear = computed(() => auditYearRef.value ?? new Date().getFullYear())
const showSampling = ref(false)

const vc = useG12VoucherCheck({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  year: computed(() => auditYearRef.value ?? null),
  allResponses: toRef(props, 'allResponses'),
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly'),
})

const ocrLoading = ref<string | null>(null)

const tabOptions = [
  { label: '凭证基础', value: 'basic' },
  { label: '核对内容', value: 'check' },
  { label: '结论', value: 'conclusion' },
]

function onCutoffFilled(e: Event) {
  const detail = (e as CustomEvent<GCycleCutoffFilledDetail>).detail
  if (!detail?.samples?.length) return
  vc.applyCutoffResults(detail.samples, detail.fillMode ?? 'append')
}

onMounted(() => {
  window.addEventListener(GCYCLE_CUTOFF_EVENT.g12, onCutoffFilled as EventListener)
})

onBeforeUnmount(() => {
  window.removeEventListener(GCYCLE_CUTOFF_EVENT.g12, onCutoffFilled as EventListener)
})

async function onImported() {
  emit('imported')
  vc.reloadFromStore()
}

function onSampleFilled(payload: {
  samples?: Array<{
    summary?: string
    amount?: number
    debitAmount?: number | string
    creditAmount?: number | string
    voucherDate?: string
    voucherNo?: string
    counterpartAccount?: string
    abnormal?: boolean
    isHighValue?: boolean
    selectionReason?: string
  }>
  method?: string
  fillMode?: 'append' | 'merge' | 'replace'
  methodology?: {
    samplingMethod?: string
    samplingInterval?: string | null
    sampleSize?: number
    suggestedSampleSize?: number | null
    tolerableMisstatement?: number | null
    expectedMisstatement?: number | null
    confidenceLevel?: number | null
    accountCodes?: string[]
    randomSeed?: string | null
  }
}) {
  const samples = payload.samples ?? []
  if (!samples.length) return
  const n = vc.applySamplingFill({
    samples: samples.map((s) => ({
      summary: s.summary,
      debitAmount: typeof s.debitAmount === 'string' ? Number(s.debitAmount) : s.debitAmount,
      creditAmount: typeof s.creditAmount === 'string' ? Number(s.creditAmount) : s.creditAmount,
      amount: s.amount,
      voucherDate: s.voucherDate,
      voucherNo: s.voucherNo,
      counterpartAccount: s.counterpartAccount,
      abnormal: s.abnormal,
      isHighValue: s.isHighValue,
      selectionReason: s.selectionReason,
    })),
    method: payload.method,
    fillMode: payload.fillMode ?? 'append',
    methodology: payload.methodology,
  })
  showSampling.value = false
  if (n > 0) {
    ElMessage.success(`已回填 ${n} 笔抽凭样本${payload.methodology?.samplingInterval ? '，MUS 参数已写入抽样过程' : ''}`)
  } else {
    ElMessage.info('未回填任何样本（可能已存在相同凭证号）')
  }
}

function onApplySuggested() {
  const n = vc.applySuggestedSampleSize()
  if (n) ElMessage.success(`已采用公式样本量 ${n}`)
}

function onSyncNetExposure() {
  const n = vc.syncFromNetExposure()
  const s = vc.netExposureSummary.value
  if (n > 0) {
    ElMessage.success(`已按 G12-5 勾稽回写核对⑤ ${n} 行（匹配 ${s.ok} / 缺失 ${s.missing} / 未完整 ${s.incomplete}）`)
  } else {
    ElMessage.info(`未回写：匹配 ${s.ok}，缺失 ${s.missing}，未完整 ${s.incomplete}，无编号 ${s.noId}（仅对核对⑤=未测且匹配完整的行回写）`)
  }
}

function onBatchCiteFv() {
  const n = vc.batchCiteFv()
  if (n > 0) ElMessage.success(`已引用 G12-4 估值依据 ${n} 行（写入支持性文件，未测的核对⑥置为通过）`)
  else ElMessage.info('无可引用行：请填写套期关系编号并确保 G12-4 有对应估值方法/来源/层次')
}

function onCiteFvRow(rowId: string) {
  const res = vc.citeFvForRow(rowId)
  if (res.ok) ElMessage.success(res.message)
  else ElMessage.warning(res.message)
}

async function onPushAbnormal() {
  const n = await vc.pushAbnormalToAdjustment()
  if (n > 0 && jumpToSection) {
    const go = await confirmNavigateToSheet({
      title: '已推送至 G12-3',
      message: `已追加 ${n} 笔调整草稿，是否前往 G12-3 查看？`,
      confirmText: '前往 G12-3',
    })
    if (go) jumpToSection('调整分录汇总G12-3')
  }
}

async function onMarkProcedure() {
  const res = await vc.markProcedureComplete()
  if (!res.ok) {
    ElMessage.warning(res.message)
    return
  }
  ElMessage.success(res.message)
  dispatchProcedureFocus({
    programNos: [...G12A_VOUCHER_PROGRAM_NOS],
    sheetCode: 'G12A',
    sheetName: G12A_PROCEDURE_SHEET,
  })
  if (jumpToSection) {
    const go = await confirmNavigateToSheet({
      title: '已回填 G12A',
      message: res.message + '，是否前往程序表查看？',
      confirmText: '前往 G12A',
    })
    if (go) jumpToSection(G12A_PROCEDURE_SHEET)
  }
}

function exportMemo() {
  const md = vc.buildMemo()
  const blob = new Blob([md], { type: 'text/markdown;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `G12-6_抽样备忘_${new Date().toISOString().slice(0, 10)}.md`
  a.click()
  URL.revokeObjectURL(url)
  ElMessage.success('已导出抽样备忘')
}

async function uploadOcr(row: G12VoucherRow) {
  if (props.isReadonly || !props.wpId) return
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = 'image/*,.pdf'
  input.onchange = async () => {
    const file = input.files?.[0]
    if (!file) return
    ocrLoading.value = row.rowId
    try {
      const fd = new FormData()
      fd.append('file', file)
      const res = await http.post(`/api/workpapers/${props.wpId}/d4/contract-ocr`, fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
        _silent: true,
      } as any)
      const fields = (res.data?.data ?? res.data)?.extracted_fields || {}
      if (!Object.keys(fields).length) { ElMessage.info('OCR未识别到字段'); return }
      await ElMessageBox.confirm(`识别到 ${Object.keys(fields).length} 个字段，填入当前行？`, 'OCR')
      vc.updateRow(row.rowId, {
        attachment: file.name,
        voucherNo: fields.voucher_no || row.voucherNo,
        voucherDate: fields.date || row.voucherDate,
        businessContent: fields.summary || fields.business_content || row.businessContent,
      })
      ElMessage.success('OCR已填入')
    } catch (e) {
      if (e !== 'cancel') ElMessage.warning('OCR失败，请手动填写')
    } finally {
      ocrLoading.value = null
    }
  }
  input.click()
}

function fmt(v: number) {
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.g12-vc { padding: 12px; font-size: var(--wp-font-size, 13px); }
.section-head { display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: 8px; margin-bottom: 8px; }
.sheet-title { margin: 0; font-size: 16px; }
.head-actions { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
.chip-wrap { display: inline-flex; align-items: center; }
.objective-alert { margin-bottom: 12px; }
.ao-wrap { font-size: 12px; }
.ao-title { font-weight: 600; margin-bottom: 4px; }
.ao-list { margin: 0; padding-left: 18px; line-height: 1.55; }
.sampling-params-card { margin-bottom: 12px; padding: 12px; background: #fafbfc; border: 1px solid #ebeef5; border-radius: 6px; }
.card-title { margin: 0 0 10px; font-size: 14px; font-weight: 600; }
.params-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }
.param-item { display: flex; flex-direction: column; gap: 4px; }
.param-item-wide { grid-column: span 2; }
.param-label { font-size: 12px; color: #606266; }
.param-with-action { display: flex; gap: 4px; align-items: center; }
.hint-text { font-size: 11px; color: #909399; }
.sampling-calc-row, .ratio-row { display: flex; align-items: center; gap: 8px; margin-top: 10px; font-size: 12px; flex-wrap: wrap; }
.ratio-alert { margin-top: 8px; }
.muted { color: #909399; }
.sep { color: #dcdfe6; }
.methodology-block { margin-bottom: 12px; padding: 10px 12px; background: #f5f7fa; border-radius: 4px; font-size: 12px; }
.legend-title { font-weight: 600; margin-bottom: 6px; }
.legend-list { margin: 0 0 6px; padding-left: 20px; line-height: 1.6; }
.legend-note { margin: 0; color: #606266; }
.source-filter-bar { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; flex-wrap: wrap; }
.cross-link-bar { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; flex-wrap: wrap; font-size: 12px; }
.filter-label { font-size: 12px; color: #606266; }
.summary-bar { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; flex-wrap: wrap; font-size: 12px; }
.summary-sep { color: #dcdfe6; }
.summary-muted { color: #909399; }
.virtual-toolbar { margin-bottom: 8px; }
.virtual-hint { margin: 0; }
.segment-tabs { margin-bottom: 8px; }
.audit-note-card { margin-top: 16px; }
.audit-note-card .card-header { display: flex; justify-content: space-between; align-items: center; font-weight: 500; }
.guidance-details { margin-top: 16px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: 13px; color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
:deep(.g12-vc-abnormal) { background: #fef0f0 !important; }
</style>
