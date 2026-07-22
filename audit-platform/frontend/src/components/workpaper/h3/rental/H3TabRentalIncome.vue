<template>
  <div class="h3-tab-rental-income">
    <details class="guidance-details">
      <summary>编制提示</summary>
      <div class="guidance-content">
        <p>1. 对齐致同 H3-14：获取租金明细与合同 → 按「本期月数×月租金」重算应计 → 与账面已计比对差异 → 说明原因并索引协议。</p>
        <p>2. 差异⑤=应计③−已计④（正数表示账面少计）；|差异|显著或差异率&gt;5%须查明原因。</p>
        <p>3. 右侧「日后未折现租赁收款额」支撑附注租赁披露；月度明细/到期管理为增强分析区。</p>
        <p>4. 审计说明须勾稽「其他业务收入—租金」；结果经 EventBus 联动附注与收入循环。</p>
      </div>
    </details>

    <el-alert
      type="info"
      :closable="false"
      class="objective-alert"
      title="审计目标：确定投资性房地产租金收入已恰当计入财务报表，计价分摊调整已正确记录，计量与披露恰当。"
    />

    <div class="methodology-context">
      <p>
        编制思路：取得或编制租金收入明细 →
        <b>测算本期应计租金</b>（①租赁月数×②月租金=③应计）→
        与账面④已计比对得出⑤差异并说明原因 →
        核对租赁协议索引 → 填列日后未折现收款额供披露 →
        勾稽其他业务收入。
      </p>
    </div>

    <div class="tab-toolbar">
      <span class="chip-wrap"><GtIndexChip value="wp:H3-14" :context-project-id="projectId" /></span>
      <el-tag size="small" type="info">共 {{ contractRows.length }} 份合同</el-tag>
      <el-tag v-if="contractSummary.abnormalCount > 0" size="small" type="danger">
        租金差异 {{ contractSummary.abnormalCount }} 项
      </el-tag>
      <el-tag v-if="expiryAlerts.length > 0" size="small" type="warning">
        即将到期 {{ expiryAlerts.length }} 份
      </el-tag>
      <el-tag
        v-if="plReconcile.status === 'match'"
        size="small"
        type="success"
      >6051勾稽一致</el-tag>
      <el-tag
        v-else-if="plReconcile.status === 'mismatch'"
        size="small"
        type="danger"
      >6051差异 {{ fmtNum(plReconcile.diff) }}</el-tag>
    </div>

    <!-- 其他业务收入勾稽 -->
    <el-card shadow="never" class="reconcile-card">
      <template #header>
        <div class="section-title">
          <span>其他业务收入（6051）勾稽</span>
          <el-button size="small" :loading="tb6051Loading" @click="onRefreshTb">刷新TB勾稽</el-button>
        </div>
      </template>
      <el-descriptions :column="4" border size="small">
        <el-descriptions-item label="本表已计④合计">{{ fmtNum(contractSummary.bookedTotal) }}</el-descriptions-item>
        <el-descriptions-item label="TB 6051发生额">{{ plReconcile.tb6051Amount != null ? fmtNum(plReconcile.tb6051Amount) : '—' }}</el-descriptions-item>
        <el-descriptions-item label="勾稽差异">
          <span :class="{ 'text-warn': plReconcile.status === 'mismatch' }">
            {{ plReconcile.tb6051Amount != null ? fmtNum(plReconcile.diff) : '—' }}
          </span>
        </el-descriptions-item>
        <el-descriptions-item label="状态">
          <el-tag v-if="plReconcile.status === 'match'" size="small" type="success">一致</el-tag>
          <el-tag v-else-if="plReconcile.status === 'mismatch'" size="small" type="danger">不一致</el-tag>
          <el-tag v-else size="small" type="info">待取数</el-tag>
        </el-descriptions-item>
      </el-descriptions>
      <p class="reconcile-note">{{ plReconcile.note }}</p>
    </el-card>

    <!-- D4-3 租金分项勾稽 -->
    <el-card shadow="never" class="reconcile-card">
      <template #header>
        <div class="section-title">
          <span>D4-3 其他业务收入 — 租金分项勾稽</span>
          <span class="action-btns">
            <el-button size="small" :loading="d43Loading" @click="onRefreshD43">刷新 D4-3</el-button>
            <el-button size="small" :disabled="isReadonly || !d43Aggregate.items.length" @click="onApplyD43('fillEmpty')">同步已计④（填空）</el-button>
            <el-button size="small" :disabled="isReadonly || !d43Aggregate.items.length" @click="onApplyD43('overwrite')">同步已计④（覆盖）</el-button>
          </span>
        </div>
      </template>
      <el-descriptions :column="4" border size="small">
        <el-descriptions-item label="本表已计④合计">{{ fmtNum(contractSummary.bookedTotal) }}</el-descriptions-item>
        <el-descriptions-item label="D4-3租金分项">{{ d43Reconcile.d43Total != null ? fmtNum(d43Reconcile.d43Total) : '—' }}</el-descriptions-item>
        <el-descriptions-item label="勾稽差异">
          <span :class="{ 'text-warn': d43Reconcile.status === 'mismatch' }">
            {{ d43Reconcile.d43Total != null ? fmtNum(d43Reconcile.diff) : '—' }}
          </span>
        </el-descriptions-item>
        <el-descriptions-item label="匹配项数">{{ d43Reconcile.itemCount || '—' }}</el-descriptions-item>
      </el-descriptions>
      <el-table
        v-if="d43Aggregate.items.length"
        :data="d43Aggregate.items"
        border
        size="small"
        class="d43-table"
        max-height="160"
      >
        <el-table-column prop="item" label="D4-3 项目" min-width="160" />
        <el-table-column label="本期审定" width="120" align="right">
          <template #default="{ row }">{{ fmtNum(row.currentAudited) }}</template>
        </el-table-column>
        <el-table-column label="上期审定" width="120" align="right">
          <template #default="{ row }">{{ fmtNum(row.priorAudited) }}</template>
        </el-table-column>
      </el-table>
      <p class="reconcile-note">{{ d43Reconcile.note }}</p>
    </el-card>

    <!-- 区域1：核心测算（对齐 Excel 主表） -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="section-title">
          <span>(1) 租金收入测算（应计 vs 已计）</span>
          <span class="action-btns">
            <el-button size="small" :disabled="isReadonly" @click="onImportH32('addNew')">从 H3-2 带入资产</el-button>
            <el-button size="small" :disabled="isReadonly || !contractRows.length" @click="onImportH32('fillEmpty')">补全资产信息</el-button>
            <el-button size="small" :disabled="isReadonly || !contractRows.length" @click="onFillMonths">推算本期月数</el-button>
            <el-button size="small" :disabled="!contractRows.length" @click="onDraftNote">生成勾稽说明</el-button>
            <el-button size="small" type="primary" :disabled="isReadonly" @click="addContractRow()">+ 新增</el-button>
            <el-button size="small" @click="generateAI('H3-14-contract')">AI</el-button>
          </span>
        </div>
      </template>

      <el-table
        :data="displayRows"
        border
        size="small"
        class="audit-table"
        max-height="480"
        :row-class-name="getDisplayRowClass"
      >
        <el-table-column label="#" width="42" fixed>
          <template #default="{ row, $index }">
            <span v-if="row.rowKind === 'data'">{{ dataRowSeq(row, $index) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="类别" width="110" fixed>
          <template #default="{ row }">
            <template v-if="row.rowKind === 'data' && row.dataIndex != null">
              <el-select
                v-model="contractRows[row.dataIndex].category"
                size="small"
                :disabled="isReadonly"
                @change="onContractChange(row.dataIndex!, contractRows[row.dataIndex])"
              >
                <el-option label="房屋、建筑物" value="building" />
                <el-option label="土地使用权" value="land" />
              </el-select>
            </template>
          </template>
        </el-table-column>
        <el-table-column label="项目名称" min-width="120" fixed>
          <template #default="{ row }">
            <span v-if="row.rowKind !== 'data'" class="subtotal-label">{{ row.label }}</span>
            <el-input
              v-else-if="row.dataIndex != null"
              v-model="contractRows[row.dataIndex].assetName"
              size="small"
              :disabled="isReadonly"
              @change="onContractChange(row.dataIndex!, contractRows[row.dataIndex])"
            />
          </template>
        </el-table-column>
        <el-table-column label="承租人" min-width="100">
          <template #default="{ row }">
            <el-input
              v-if="row.rowKind === 'data' && row.dataIndex != null"
              v-model="contractRows[row.dataIndex].tenant"
              size="small"
              :disabled="isReadonly"
              @change="onContractChange(row.dataIndex!, contractRows[row.dataIndex])"
            />
          </template>
        </el-table-column>
        <el-table-column label="租赁期间" min-width="210">
          <template #default="{ row }">
            <div v-if="row.rowKind === 'data' && row.dataIndex != null" class="date-pair">
              <el-date-picker
                v-model="contractRows[row.dataIndex].leaseStart"
                type="date"
                value-format="YYYY-MM-DD"
                size="small"
                placeholder="起"
                style="width: 118px"
                :disabled="isReadonly"
                @change="onContractChange(row.dataIndex!, contractRows[row.dataIndex])"
              />
              <el-date-picker
                v-model="contractRows[row.dataIndex].leaseEnd"
                type="date"
                value-format="YYYY-MM-DD"
                size="small"
                placeholder="止"
                style="width: 118px"
                :disabled="isReadonly"
                @change="onContractChange(row.dataIndex!, contractRows[row.dataIndex])"
              />
            </div>
          </template>
        </el-table-column>
        <el-table-column label="合同总金额" width="110" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.rowKind === 'data' && row.dataIndex != null"
              v-model="contractRows[row.dataIndex].contractAmount"
              :controls="false"
              size="small"
              :disabled="isReadonly"
              @change="onContractChange(row.dataIndex!, contractRows[row.dataIndex])"
            />
            <span v-else class="formula-value">{{ fmtNum(row.contractAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="租赁面积" width="90" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.rowKind === 'data' && row.dataIndex != null"
              v-model="contractRows[row.dataIndex].area"
              :controls="false"
              size="small"
              :disabled="isReadonly"
              @change="onContractChange(row.dataIndex!, contractRows[row.dataIndex])"
            />
          </template>
        </el-table-column>
        <el-table-column label="租赁月数①" width="90" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.rowKind === 'data' && row.dataIndex != null"
              v-model="contractRows[row.dataIndex].monthsThisYear"
              :controls="false"
              :min="0"
              :max="12"
              size="small"
              :disabled="isReadonly"
              @change="onContractChange(row.dataIndex!, contractRows[row.dataIndex])"
            />
          </template>
        </el-table-column>
        <el-table-column label="月租金②" width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.rowKind === 'data' && row.dataIndex != null"
              v-model="contractRows[row.dataIndex].monthlyRent"
              :controls="false"
              size="small"
              :disabled="isReadonly"
              @change="onContractChange(row.dataIndex!, contractRows[row.dataIndex])"
            />
          </template>
        </el-table-column>
        <el-table-column label="应计③=①×②" width="110" align="right" class-name="formula-col">
          <template #default="{ row }">
            <span class="formula-value">{{ fmtNum(row.expectedRent) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="已计④" width="110" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.rowKind === 'data' && row.dataIndex != null"
              v-model="contractRows[row.dataIndex].bookedRent"
              :controls="false"
              size="small"
              :disabled="isReadonly"
              @change="onContractChange(row.dataIndex!, contractRows[row.dataIndex])"
            />
            <span v-else class="formula-value">{{ fmtNum(row.bookedRent) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="差异⑤=③−④" width="110" align="right" class-name="formula-col">
          <template #default="{ row }">
            <span
              class="formula-value"
              :class="{ 'text-warn': Math.abs(row.incomeDiff) > 0.01 }"
            >{{ fmtNum(row.incomeDiff) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="差异原因" min-width="120">
          <template #default="{ row }">
            <el-input
              v-if="row.rowKind === 'data' && row.dataIndex != null"
              v-model="contractRows[row.dataIndex].diffReason"
              size="small"
              :disabled="isReadonly"
              @change="onContractChange(row.dataIndex!, contractRows[row.dataIndex])"
            />
          </template>
        </el-table-column>
        <el-table-column label="协议索引号" width="100">
          <template #default="{ row }">
            <el-input
              v-if="row.rowKind === 'data' && row.dataIndex != null"
              v-model="contractRows[row.dataIndex].contractIndex"
              size="small"
              :disabled="isReadonly"
              @change="onContractChange(row.dataIndex!, contractRows[row.dataIndex])"
            />
          </template>
        </el-table-column>

        <el-table-column label="资产负债表日后未折现租赁收款额" align="center">
          <el-table-column label="第1年" width="90" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="row.rowKind === 'data' && row.dataIndex != null"
                v-model="contractRows[row.dataIndex].futureY1"
                :controls="false"
                size="small"
                :disabled="isReadonly"
                @change="onContractChange(row.dataIndex!, contractRows[row.dataIndex])"
              />
            </template>
          </el-table-column>
          <el-table-column label="第2年" width="90" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="row.rowKind === 'data' && row.dataIndex != null"
                v-model="contractRows[row.dataIndex].futureY2"
                :controls="false"
                size="small"
                :disabled="isReadonly"
                @change="onContractChange(row.dataIndex!, contractRows[row.dataIndex])"
              />
            </template>
          </el-table-column>
          <el-table-column label="第3年" width="90" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="row.rowKind === 'data' && row.dataIndex != null"
                v-model="contractRows[row.dataIndex].futureY3"
                :controls="false"
                size="small"
                :disabled="isReadonly"
                @change="onContractChange(row.dataIndex!, contractRows[row.dataIndex])"
              />
            </template>
          </el-table-column>
          <el-table-column label="第4年" width="90" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="row.rowKind === 'data' && row.dataIndex != null"
                v-model="contractRows[row.dataIndex].futureY4"
                :controls="false"
                size="small"
                :disabled="isReadonly"
                @change="onContractChange(row.dataIndex!, contractRows[row.dataIndex])"
              />
            </template>
          </el-table-column>
          <el-table-column label="第5年" width="90" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="row.rowKind === 'data' && row.dataIndex != null"
                v-model="contractRows[row.dataIndex].futureY5"
                :controls="false"
                size="small"
                :disabled="isReadonly"
                @change="onContractChange(row.dataIndex!, contractRows[row.dataIndex])"
              />
            </template>
          </el-table-column>
          <el-table-column label="5年后" width="90" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="row.rowKind === 'data' && row.dataIndex != null"
                v-model="contractRows[row.dataIndex].futureAfter"
                :controls="false"
                size="small"
                :disabled="isReadonly"
                @change="onContractChange(row.dataIndex!, contractRows[row.dataIndex])"
              />
            </template>
          </el-table-column>
          <el-table-column label="合计" width="100" align="right" class-name="formula-col">
            <template #default="{ row }">
              <span class="formula-value">{{ fmtNum(row.futureTotal) }}</span>
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column label="操作" width="92" fixed="right">
          <template #default="{ row }">
            <template v-if="row.rowKind === 'data' && row.dataIndex != null">
              <el-button
                size="small"
                type="primary"
                link
                :disabled="isReadonly"
                title="上传租赁合同 OCR 识别"
                @click="handleRentalOcr(row.dataIndex!)"
              >📎OCR</el-button>
              <el-button
                size="small"
                type="danger"
                link
                :disabled="isReadonly"
                @click="onRemove(row.dataIndex!)"
              >删</el-button>
            </template>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 区域2：月度明细（增强） -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="section-title">
          <span>(2) 月度租金收入明细（增强：可回填已计④）</span>
          <el-button size="small" @click="generateAI('H3-14-monthly')">AI</el-button>
        </div>
      </template>
      <el-table :data="contractRows" border size="small" class="audit-table" :row-class-name="getMonthlyRowClass">
        <el-table-column prop="assetName" label="资产" min-width="100" fixed />
        <el-table-column v-for="m in 12" :key="m" :label="`${m}月`" width="75" align="right">
          <template #default="{ row, $index }">
            <el-input-number v-model="row.monthlyActual[m - 1]" :controls="false" size="small" :disabled="isReadonly" @change="onMonthlyChange($index, row)" />
          </template>
        </el-table-column>
        <el-table-column label="累计" min-width="90" align="right" class-name="formula-col">
          <template #default="{ row }">
            <span class="formula-value">{{ fmtNum(sumMonthly(row)) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="vs应计差异率" width="110" align="right" class-name="formula-col">
          <template #default="{ row }">
            <span class="formula-value" :class="{ 'text-warn': Math.abs(calcMonthlyDiffRate(row)) > 5 }">
              {{ calcMonthlyDiffRate(row).toFixed(1) }}%
            </span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 区域3：到期管理（增强） -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="section-title">
          <span>(3) 到期管理（增强）</span>
          <el-button size="small" @click="generateAI('H3-14-expiry')">AI</el-button>
        </div>
      </template>
      <el-table :data="contractRows" border size="small" class="audit-table" :row-class-name="getExpiryRowClass">
        <el-table-column prop="assetName" label="资产" min-width="120" />
        <el-table-column prop="tenant" label="租户" min-width="100" />
        <el-table-column prop="leaseEnd" label="合同到期日" width="110" />
        <el-table-column label="到期月数" width="80" align="right" class-name="formula-col">
          <template #default="{ row }">
            <span class="formula-value" :class="{ 'text-expiry': row.monthsToExpiry != null && row.monthsToExpiry <= 3 }">
              {{ row.monthsToExpiry ?? '-' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="renewalStatus" label="续租状态" width="110">
          <template #default="{ row, $index }">
            <el-select v-model="row.renewalStatus" size="small" :disabled="isReadonly" clearable @change="onContractChange($index, row)">
              <el-option label="已续租" value="已续租" />
              <el-option label="洽谈中" value="洽谈中" />
              <el-option label="未续租" value="未续租" />
              <el-option label="空置" value="空置" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column prop="vacancyForecast" label="空置预测" min-width="100">
          <template #default="{ row, $index }">
            <el-input v-model="row.vacancyForecast" size="small" :disabled="isReadonly" @change="onContractChange($index, row)" />
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <div class="toolbar">
      <el-dropdown size="small" @command="handleExportCmd">
        <el-button size="small" :loading="importing">导入导出 ▾</el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="export-template">导出模板</el-dropdown-item>
            <el-dropdown-item command="export-data">导出数据</el-dropdown-item>
            <el-dropdown-item command="import-data">导入数据</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
      <input ref="fileInputRef" type="file" accept=".xlsx,.xls" class="hidden-file" @change="onFileSelected" />
    </div>

    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="card-header">
          <span>三、审计说明</span>
          <span class="action-btns">
            <el-button size="small" @click="generateAI('H3-14')">AI</el-button>
            <el-button size="small" circle @click="openReview('H3-14')">💬</el-button>
          </span>
        </div>
      </template>
      <el-input
        :model-value="auditNote"
        type="textarea"
        :autosize="{ minRows: 5 }"
        placeholder="1. 租赁收入与其他业务收入的勾稽情况&#10;2. 应计与已计差异原因&#10;3. 到期/空置及对估值影响"
        :disabled="isReadonly"
        @change="saveAuditNote"
      />
    </el-card>

    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="card-header"><span>四、审计结论</span></div>
      </template>
      <el-input
        :model-value="auditConclusion"
        type="textarea"
        :autosize="{ minRows: 3 }"
        placeholder="填写审计结论：A、租金收入真实完整、截止恰当。B、除下列事项外未见异常。C、存在重大异常，不可确认。"
        :disabled="isReadonly"
        @change="saveAuditConclusion"
      />
    </el-card>
  </div>
</template>

<script setup lang="ts">
/**
 * H3TabRentalIncome.vue — H3-14 租金收入测算
 * 核心区对齐 Excel（应计/已计/差异/日后收款）+ 月度/到期增强
 */
import { ref, computed, inject, toRef, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  useH3RentalIncome,
  sumMonthlyActual,
  type RentalContractRow,
  type RentalDisplayRow,
} from '../../composables/useH3RentalIncome'
import { useH3FormData } from '../../composables/useH3FormData'
import { useH3ImportExport } from '../../composables/useH3ImportExport'
import GtIndexChip from '../../GtIndexChip.vue'
import http from '@/utils/http'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
  measurementModel?: 'cost' | 'fair_value'
  htmlData?: any
}>()

defineEmits<{
  (e: 'navigate-sheet', sheetName: string): void
}>()

const openReviewDialog = inject<(section: string) => void>('openReviewDialog', () => {})

const { getValue, setValue, saveImmediate } = useH3FormData({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  measurementModel: ref('cost') as any,
})

const {
  contractRows,
  displayRows,
  contractSummary,
  expiryAlerts,
  plReconcile,
  d43Reconcile,
  d43Aggregate,
  tb6051Loading,
  d43Loading,
  addContractRow,
  removeContractRow,
  updateContractRow,
  updateMonthlyData,
  fillMonthsThisYear,
  buildNoteDraft,
  refreshTbReconcile,
  refreshD43Reconcile,
  importFromH32,
  applyD43BookedRent,
  loadData,
} = useH3RentalIncome({
  allResponses: computed(() => props.allResponses) as any,
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  measurementModel: computed(() => props.measurementModel ?? 'cost') as any,
  htmlData: computed(() => props.htmlData),
  getValue,
  setValue,
  saveImmediate,
})

const { exportTemplate, exportData, importData, importing } = useH3ImportExport({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  measurementModel: computed(() => props.measurementModel ?? 'cost') as any,
  onImported: async () => {
    loadData()
    await refreshTbReconcile()
    publishRentalIncomeCalculated()
  },
})

const fileInputRef = ref<HTMLInputElement | null>(null)

const NOTE_KEY = 'H3-14-audit-note'
const CONCLUSION_KEY = 'H3-14-audit-conclusion'
const auditNote = ref('')
const auditConclusion = ref('')

onMounted(() => {
  const n = props.allResponses.get(NOTE_KEY)
  if (n?.remark) auditNote.value = n.remark
  const c = props.allResponses.get(CONCLUSION_KEY)
  if (c?.remark) auditConclusion.value = c.remark
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

function onContractChange(index: number, row: RentalContractRow) {
  updateContractRow(index, row)
  publishRentalIncomeCalculated()
}

/** 租赁合同 OCR：上传 → 识别 → 确认 → 回填承租人/租期/月租金/面积 */
async function handleRentalOcr(index: number) {
  if (props.isReadonly) return
  const row = contractRows.value[index]
  if (!row) return
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = '.pdf,.png,.jpg,.jpeg'
  input.onchange = async () => {
    const file = input.files?.[0]
    if (!file) return
    const loading = ElMessage({ message: '正在识别租赁合同…', type: 'info', duration: 0 })
    try {
      const formData = new FormData()
      formData.append('file', file)
      const res = await http.post(
        `/api/workpapers/${props.wpId}/h3/contract-ocr`,
        formData,
        { headers: { 'Content-Type': 'multipart/form-data' } },
      )
      loading.close()
      const data = res.data?.data ?? res.data
      const f = data?.extracted_fields ?? {}
      const monthly = Number(f.monthlyRent) || 0
      const area = Number(f.area) || 0
      const total = Number(f.contractAmount) || Number(data?.amount) || 0
      await ElMessageBox.confirm(
        `识别结果（置信度 ${(Number(data?.confidence) * 100).toFixed(0)}%）：\n` +
          `承租方：${f.counterparty || '-'}\n标的：${f.assetName || '-'}\n` +
          `租期：${f.leaseStart || '-'} ~ ${f.leaseEnd || '-'}\n月租金：${monthly || '-'}\n` +
          `面积：${area || '-'} ㎡\n合同总额：${total || '-'}\n\n确认填入第 ${index + 1} 行？`,
        '租赁合同 OCR 识别结果',
        { confirmButtonText: '确认填入', cancelButtonText: '取消', type: 'info' },
      )
      if (f.counterparty && !row.tenant) row.tenant = f.counterparty
      if (f.assetName && !row.assetName) row.assetName = f.assetName
      if (f.leaseStart) row.leaseStart = f.leaseStart
      if (f.leaseEnd) row.leaseEnd = f.leaseEnd
      if (monthly > 0) row.monthlyRent = monthly
      if (area > 0) row.area = area
      if (total > 0) row.contractAmount = total
      if (f.contractNo && !row.contractIndex) row.contractIndex = String(f.contractNo)
      updateContractRow(index, row)
      publishRentalIncomeCalculated()
      ElMessage.success('已填入识别结果；可点「推算本期月数」按起止日重算租赁月数')
    } catch (err: any) {
      loading.close()
      if (err === 'cancel' || String(err).includes('cancel')) return
      console.warn('[H3-14 rental OCR]', err)
      ElMessage.error('识别失败，请重试或手工录入')
    }
  }
  input.click()
}

function onMonthlyChange(index: number, row: RentalContractRow) {
  updateMonthlyData(index, row)
  publishRentalIncomeCalculated()
}

function onRemove(index: number) {
  removeContractRow(index)
  publishRentalIncomeCalculated()
}

function onFillMonths() {
  const n = fillMonthsThisYear()
  ElMessage.success(n ? `已推算 ${n} 行本期租赁月数` : '未能根据起止日推算月数，请检查租赁期间')
  publishRentalIncomeCalculated()
}

function onDraftNote() {
  const draft = buildNoteDraft()
  saveAuditNote(draft)
  ElMessage.success('已生成勾稽说明草稿')
}

async function onRefreshTb() {
  await refreshTbReconcile()
  ElMessage.success('已刷新 6051 勾稽')
}

async function onRefreshD43() {
  const agg = await refreshD43Reconcile()
  ElMessage.success(agg.items.length ? agg.message : (agg.message || 'D4-3 无租金分项'))
  publishRentalIncomeCalculated()
}

function onImportH32(mode: 'addNew' | 'fillEmpty') {
  const result = importFromH32(mode)
  ElMessage.success(result.message)
  if (result.added || result.updated) publishRentalIncomeCalculated()
}

function onApplyD43(mode: 'fillEmpty' | 'overwrite') {
  const result = applyD43BookedRent(mode)
  ElMessage.success(result.message)
  if (result.updated) publishRentalIncomeCalculated()
}

function dataRowSeq(row: RentalDisplayRow, displayIndex: number): number {
  if (row.rowKind !== 'data') return 0
  let seq = 0
  for (let i = 0; i <= displayIndex; i++) {
    if (displayRows.value[i]?.rowKind === 'data') seq++
  }
  return seq
}

function getDisplayRowClass({ row }: { row: RentalDisplayRow }): string {
  if (row.rowKind === 'categorySubtotal') return 'row-subtotal'
  if (row.rowKind === 'grandTotal') return 'row-grand-total'
  if (Math.abs(row.incomeDiff) > 0.01) return 'row-warn'
  return ''
}

async function handleExportCmd(cmd: string) {
  if (cmd === 'export-template') await exportTemplate('H3-14')
  else if (cmd === 'export-data') await exportData('H3-14')
  else if (cmd === 'import-data') fileInputRef.value?.click()
}

async function onFileSelected(ev: Event) {
  const file = (ev.target as HTMLInputElement).files?.[0]
  ;(ev.target as HTMLInputElement).value = ''
  if (!file) return
  await importData('H3-14', file)
  ElMessageBox.alert('导入完成。若页面未刷新，请切换 sheet 后返回查看。', '提示')
}

function publishRentalIncomeCalculated() {
  const totalExpected = contractSummary.value.expectedTotal
  const totalAnnualRent = contractSummary.value.totalAnnualRent
  http.post(`/api/projects/${props.projectId}/events/publish`, {
    event_type: 'h3:rental-income-calculated',
    payload: {
      wp_id: props.wpId,
      totalAnnualRent,
      totalExpectedRent: totalExpected,
      totalBookedRent: contractSummary.value.bookedTotal,
      totalDiff: contractSummary.value.diffTotal,
      futureLeaseReceipts: contractSummary.value.futureTotal,
    },
  }).catch(() => { /* best effort */ })
}

function sumMonthly(row: RentalContractRow): number {
  return sumMonthlyActual(row)
}

/** 月度累计 vs 应计③ 的差异率 */
function calcMonthlyDiffRate(row: RentalContractRow): number {
  const expected = row.expectedRent || (row.monthlyRent * (row.monthsThisYear || 12))
  const actual = sumMonthly(row)
  if (!expected) return 0
  return ((actual - expected) / expected) * 100
}


function getMonthlyRowClass({ row }: { row: RentalContractRow }): string {
  if (Math.abs(calcMonthlyDiffRate(row)) > 5) return 'row-warn'
  return ''
}

function getExpiryRowClass({ row }: { row: RentalContractRow }): string {
  if (row.monthsToExpiry != null && row.monthsToExpiry <= 3) return 'row-expiry'
  if (row.renewalStatus === '空置') return 'row-vacant'
  return ''
}

function fmtNum(v: number): string {
  if (v == null || Number.isNaN(v) || v === 0) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function generateAI(section: string) {
  window.dispatchEvent(new CustomEvent('ai:generate', { detail: { section, wpId: props.wpId } }))
}
function openReview(section: string) { openReviewDialog(section) }
</script>

<style scoped>
.h3-tab-rental-income { padding: 16px; font-size: var(--wp-font-size, 13px); }
.guidance-details { margin-bottom: 12px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: var(--wp-font-size, 13px); color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.objective-alert { margin-bottom: 8px; }
.methodology-context {
  margin-bottom: 12px;
  padding: 8px 12px;
  background: var(--el-fill-color-lighter);
  border-radius: 4px;
  color: #606266;
  line-height: 1.6;
  font-size: var(--wp-font-size, 13px);
}
.methodology-context p { margin: 0; }
.tab-toolbar { display: flex; justify-content: flex-end; align-items: center; gap: 8px; margin-bottom: 8px; flex-wrap: wrap; }
.chip-wrap { display: inline-flex; align-items: center; }
.audit-note-card { margin-top: 16px; }
.audit-note-card .card-header { display: flex; justify-content: space-between; align-items: center; font-weight: 500; }
.section-card { margin-bottom: 16px; }
.section-title { display: flex; align-items: center; justify-content: space-between; gap: 8px; flex-wrap: wrap; }
.action-btns { display: flex; gap: 4px; flex-wrap: wrap; }
.audit-table { font-size: var(--wp-font-size, 13px); }
.audit-table :deep(.formula-col) { background: var(--el-fill-color-lighter); }
.audit-table :deep(.row-subtotal) { background-color: #f5f7fa !important; font-weight: 600; }
.audit-table :deep(.row-grand-total) { background-color: #e8f4ff !important; font-weight: 700; }
.subtotal-label { font-weight: 600; color: #303133; }
.reconcile-card { margin-bottom: 16px; }
.reconcile-note { margin: 8px 0 0; font-size: 12px; color: #909399; line-height: 1.5; }
.d43-table { margin-top: 8px; }
.hidden-file { display: none; }
.audit-table :deep(.row-warn) { background-color: #fef9e7 !important; }
.audit-table :deep(.row-expiry) { background-color: #fff3e0 !important; }
.audit-table :deep(.row-vacant) { background-color: #fef9e7 !important; }
.formula-value { border-bottom: 1px dashed var(--el-border-color); cursor: help; }
.text-warn { color: var(--el-color-warning); font-weight: 600; }
.text-expiry { color: #e65100; font-weight: 600; }
.toolbar { margin-bottom: 12px; }
.date-pair { display: flex; gap: 4px; align-items: center; }
.audit-table :deep(.el-input-number) { width: 100%; }
</style>
