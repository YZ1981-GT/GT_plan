<!--
  G4TabVoucherCheck.vue — G4-13 凭证检查表（97行×19列 → 3区段Tab）

  3区段Tab切换（el-segmented）：
  - Tab1: 记账凭证基础列(8列): 日期|凭证编号|业务内容|对方科目|明细科目|借方金额|贷方金额|📎附件
  - Tab2: 支持性文件+核对内容(7列): 支持性文件描述|核对1~6(checkbox)|全部通过badge
  - Tab3: 结论+备注(4列): 索引号|是否异常(自动)|异常说明|备注

  分借方区/贷方区两个区块
  Tab切换行同步：切换Tab保持activeRowIndex
  Tab2: 6项checkbox核对，全✓显示绿色"全部通过"badge
  Tab3: 任一核对✗→自动设isAbnormal=true + 红色高亮
  顶部借贷平衡汇总区（差额红色显示）
  虚拟滚动（97行>50阈值）
  动态行增删 + GtIndexChip索引跳转

  Spec: .kiro/specs/g4-bond-investment-ecl/ Task 9.1
  Requirements: 6.1~6.12, 11.1, 11.5, 11.6, 11.9
-->
<template>
  <div class="g4-voucher-check">
    <!-- 顶部工具栏 -->
    <div class="section-head">
      <h3 class="sheet-title">G4-13 凭证检查表</h3>
      <div class="head-actions">
        <el-segmented v-model="vc.activeTab.value" :options="segmentOptions" size="small" />
        <el-button size="small" type="warning" :disabled="isReadonly" @click="showSampling = !showSampling">
          ⚡ 抽凭
        </el-button>
        <el-button size="small" type="primary" :disabled="isReadonly" @click="handleAddDebit">
          + 借方行
        </el-button>
        <el-button size="small" type="success" :disabled="isReadonly" @click="handleAddCredit">
          + 贷方行
        </el-button>
        <el-button size="small" @click="openReviewDialog('G4-13-voucher-check')">💬复核</el-button>
      </div>
    </div>

    <!-- 抽凭引擎（科目 1501 债权投资） -->
    <el-collapse v-if="showSampling && props.wpId && props.projectId && !isReadonly" class="sampling-collapse">
      <el-collapse-item title="⚡ 自动抽凭（科目 1501 债权投资）" name="sampling">
        <GtVoucherSamplingEngine
          account-code="1501"
          phase="final"
          default-method="random"
          :workpaper-id="props.wpId"
          :project-id="props.projectId"
          :year="currentYear"
          @filled="handleSamplingFilled"
        />
      </el-collapse-item>
    </el-collapse>

    <!-- 借贷平衡汇总区 -->
    <div class="balance-summary" :class="{ unbalanced: !vc.isBalanced.value }">
      <span class="balance-item">
        <span class="balance-label">借方合计：</span>
        <span class="balance-value">{{ fmtNum(vc.debitTotal.value) }}</span>
      </span>
      <span class="balance-item">
        <span class="balance-label">贷方合计：</span>
        <span class="balance-value">{{ fmtNum(vc.creditTotal.value) }}</span>
      </span>
      <span class="balance-item">
        <span class="balance-label">差额：</span>
        <span class="balance-value" :class="{ 'diff-red': !vc.isBalanced.value }">
          {{ fmtNum(vc.difference.value) }}
        </span>
      </span>
      <el-tag v-if="vc.isBalanced.value" type="success" size="small">借贷平衡</el-tag>
      <el-tag v-else type="danger" size="small">借贷不平衡</el-tag>
    </div>

    <!-- ═══ 借方区 ═══ -->
    <div class="section-block">
      <div class="block-header">（一）借方区</div>
      <el-table
        :data="debitDisplayRows"
        border
        size="small"
        max-height="320"
        highlight-current-row
        row-key="id"
        :row-class-name="getRowClassName"
        class="voucher-table"
        @current-change="onCurrentChange"
      >
        <template v-if="vc.activeTab.value === 'tab1'">
          <el-table-column label="序号" width="50" align="center" fixed>
            <template #default="{ row }">{{ row.seq }}</template>
          </el-table-column>
          <el-table-column label="日期" min-width="110">
            <template #default="{ row }">
              <el-date-picker v-if="!isReadonly" v-model="row.date" size="small"
                type="date" format="YYYY-MM-DD" value-format="YYYY-MM-DD"
                style="width: 100%" placeholder="选择日期" />
              <span v-else>{{ row.date }}</span>
            </template>
          </el-table-column>
          <el-table-column label="凭证编号" min-width="100">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" v-model="row.voucherNo" size="small" />
              <span v-else>{{ row.voucherNo }}</span>
            </template>
          </el-table-column>
          <el-table-column label="业务内容" min-width="140">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" v-model="row.businessContent" size="small" />
              <span v-else>{{ row.businessContent }}</span>
            </template>
          </el-table-column>
          <el-table-column label="对方科目" min-width="110">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" v-model="row.counterAccount" size="small" />
              <span v-else>{{ row.counterAccount }}</span>
            </template>
          </el-table-column>
          <el-table-column label="明细科目" min-width="110">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" v-model="row.detailAccount" size="small" />
              <span v-else>{{ row.detailAccount }}</span>
            </template>
          </el-table-column>
          <el-table-column label="借方金额" min-width="120" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly" v-model="row.debitAmount" size="small"
                :controls="false" class="compact-num" />
              <span v-else>{{ fmtNum(row.debitAmount) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="贷方金额" min-width="120" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly" v-model="row.creditAmount" size="small"
                :controls="false" class="compact-num" />
              <span v-else>{{ fmtNum(row.creditAmount) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="📎" width="70" align="center">
            <template #default="{ row }">
              <el-upload
                :show-file-list="false"
                accept="image/*,.pdf"
                :before-upload="(file: File) => handleRowOcr(row, file)"
                :disabled="isReadonly"
              >
                <el-button size="small" link :loading="ocrLoadingRowId === row.id" :disabled="isReadonly">
                  <el-icon :class="{ 'has-file': row.attachment }"><Paperclip /></el-icon>
                </el-button>
              </el-upload>
            </template>
          </el-table-column>
        </template>

        <!-- Tab2: 支持性文件+核对内容 -->
        <template v-if="vc.activeTab.value === 'tab2'">
          <el-table-column label="序号" width="50" align="center" fixed>
            <template #default="{ row }">{{ row.seq }}</template>
          </el-table-column>
          <el-table-column label="凭证编号" width="90" fixed>
            <template #default="{ row }">{{ row.voucherNo }}</template>
          </el-table-column>
          <el-table-column label="支持性文件描述" min-width="160">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" v-model="row.supportingDocDesc" size="small" />
              <span v-else>{{ row.supportingDocDesc }}</span>
            </template>
          </el-table-column>
          <el-table-column label="原始凭证完整" width="100" align="center">
            <template #default="{ row }">
              <el-checkbox v-model="row.checkOriginalComplete" :disabled="isReadonly"
                @change="onCheckChange(row)" />
            </template>
          </el-table-column>
          <el-table-column label="有授权批准" width="95" align="center">
            <template #default="{ row }">
              <el-checkbox v-model="row.checkAuthorized" :disabled="isReadonly"
                @change="onCheckChange(row)" />
            </template>
          </el-table-column>
          <el-table-column label="账务处理正确" width="100" align="center">
            <template #default="{ row }">
              <el-checkbox v-model="row.checkAccountingCorrect" :disabled="isReadonly"
                @change="onCheckChange(row)" />
            </template>
          </el-table-column>
          <el-table-column label="初始成本正确" width="100" align="center">
            <template #default="{ row }">
              <el-checkbox v-model="row.checkInitialCostCorrect" :disabled="isReadonly"
                @change="onCheckChange(row)" />
            </template>
          </el-table-column>
          <el-table-column label="利息计算正确" width="100" align="center">
            <template #default="{ row }">
              <el-checkbox v-model="row.checkInterestCorrect" :disabled="isReadonly"
                @change="onCheckChange(row)" />
            </template>
          </el-table-column>
          <el-table-column label="减值计提正确" width="100" align="center">
            <template #default="{ row }">
              <el-checkbox v-model="row.checkImpairmentCorrect" :disabled="isReadonly"
                @change="onCheckChange(row)" />
            </template>
          </el-table-column>
          <el-table-column label="状态" width="80" align="center">
            <template #default="{ row }">
              <el-tag v-if="vc.isAllChecked(row)" type="success" size="small">全部通过</el-tag>
              <el-tag v-else type="info" size="small">待核对</el-tag>
            </template>
          </el-table-column>
        </template>

        <!-- Tab3: 结论+备注 -->
        <template v-if="vc.activeTab.value === 'tab3'">
          <el-table-column label="序号" width="50" align="center" fixed>
            <template #default="{ row }">{{ row.seq }}</template>
          </el-table-column>
          <el-table-column label="凭证编号" width="90" fixed>
            <template #default="{ row }">{{ row.voucherNo }}</template>
          </el-table-column>
          <el-table-column label="索引号" width="100">
            <template #default="{ row }">
              <GtIndexChip v-if="row.indexRef" :value="row.indexRef" />
              <el-input v-else-if="!isReadonly" v-model="row.indexRef" size="small"
                placeholder="索引" />
            </template>
          </el-table-column>
          <el-table-column label="是否异常" width="85" align="center">
            <template #default="{ row }">
              <el-tag :type="row.isAbnormal ? 'danger' : 'success'" size="small">
                {{ row.isAbnormal ? '是' : '否' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="异常说明" min-width="180">
            <template #default="{ row }">
              <el-input v-if="!isReadonly && row.isAbnormal" v-model="row.abnormalNote"
                size="small" type="textarea" :autosize="{ minRows: 1, maxRows: 3 }" />
              <span v-else>{{ row.abnormalNote }}</span>
            </template>
          </el-table-column>
          <el-table-column label="备注" min-width="150">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" v-model="row.remark" size="small" />
              <span v-else>{{ row.remark }}</span>
            </template>
          </el-table-column>
        </template>

        <!-- 删除操作列（所有Tab共享） -->
        <el-table-column v-if="!isReadonly" label="" width="50" align="center" fixed="right">
          <template #default="{ row }">
            <el-popconfirm title="确认删除？" @confirm="vc.removeRow(row.id)">
              <template #reference>
                <el-icon class="delete-icon"><Delete /></el-icon>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- ═══ 贷方区 ═══ -->
    <div class="section-block">
      <div class="block-header">（二）贷方区</div>
      <el-table
        :data="creditDisplayRows"
        border
        size="small"
        max-height="320"
        highlight-current-row
        row-key="id"
        :row-class-name="getRowClassName"
        class="voucher-table"
        @current-change="onCurrentChange"
      >
        <template v-if="vc.activeTab.value === 'tab1'">
          <el-table-column label="序号" width="50" align="center" fixed>
            <template #default="{ row }">{{ row.seq }}</template>
          </el-table-column>
          <el-table-column label="日期" min-width="110">
            <template #default="{ row }">
              <el-date-picker v-if="!isReadonly" v-model="row.date" size="small"
                type="date" format="YYYY-MM-DD" value-format="YYYY-MM-DD"
                style="width: 100%" placeholder="选择日期" />
              <span v-else>{{ row.date }}</span>
            </template>
          </el-table-column>
          <el-table-column label="凭证编号" min-width="100">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" v-model="row.voucherNo" size="small" />
              <span v-else>{{ row.voucherNo }}</span>
            </template>
          </el-table-column>
          <el-table-column label="业务内容" min-width="140">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" v-model="row.businessContent" size="small" />
              <span v-else>{{ row.businessContent }}</span>
            </template>
          </el-table-column>
          <el-table-column label="对方科目" min-width="110">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" v-model="row.counterAccount" size="small" />
              <span v-else>{{ row.counterAccount }}</span>
            </template>
          </el-table-column>
          <el-table-column label="明细科目" min-width="110">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" v-model="row.detailAccount" size="small" />
              <span v-else>{{ row.detailAccount }}</span>
            </template>
          </el-table-column>
          <el-table-column label="借方金额" min-width="120" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly" v-model="row.debitAmount" size="small"
                :controls="false" class="compact-num" />
              <span v-else>{{ fmtNum(row.debitAmount) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="贷方金额" min-width="120" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly" v-model="row.creditAmount" size="small"
                :controls="false" class="compact-num" />
              <span v-else>{{ fmtNum(row.creditAmount) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="📎" width="70" align="center">
            <template #default="{ row }">
              <el-upload
                :show-file-list="false"
                accept="image/*,.pdf"
                :before-upload="(file: File) => handleRowOcr(row, file)"
                :disabled="isReadonly"
              >
                <el-button size="small" link :loading="ocrLoadingRowId === row.id" :disabled="isReadonly">
                  <el-icon :class="{ 'has-file': row.attachment }"><Paperclip /></el-icon>
                </el-button>
              </el-upload>
            </template>
          </el-table-column>
        </template>

        <!-- Tab2: 支持性文件+核对内容（贷方区） -->
        <template v-if="vc.activeTab.value === 'tab2'">
          <el-table-column label="序号" width="50" align="center" fixed>
            <template #default="{ row }">{{ row.seq }}</template>
          </el-table-column>
          <el-table-column label="凭证编号" width="90" fixed>
            <template #default="{ row }">{{ row.voucherNo }}</template>
          </el-table-column>
          <el-table-column label="支持性文件描述" min-width="160">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" v-model="row.supportingDocDesc" size="small" />
              <span v-else>{{ row.supportingDocDesc }}</span>
            </template>
          </el-table-column>
          <el-table-column label="原始凭证完整" width="100" align="center">
            <template #default="{ row }">
              <el-checkbox v-model="row.checkOriginalComplete" :disabled="isReadonly"
                @change="onCheckChange(row)" />
            </template>
          </el-table-column>
          <el-table-column label="有授权批准" width="95" align="center">
            <template #default="{ row }">
              <el-checkbox v-model="row.checkAuthorized" :disabled="isReadonly"
                @change="onCheckChange(row)" />
            </template>
          </el-table-column>
          <el-table-column label="账务处理正确" width="100" align="center">
            <template #default="{ row }">
              <el-checkbox v-model="row.checkAccountingCorrect" :disabled="isReadonly"
                @change="onCheckChange(row)" />
            </template>
          </el-table-column>
          <el-table-column label="初始成本正确" width="100" align="center">
            <template #default="{ row }">
              <el-checkbox v-model="row.checkInitialCostCorrect" :disabled="isReadonly"
                @change="onCheckChange(row)" />
            </template>
          </el-table-column>
          <el-table-column label="利息计算正确" width="100" align="center">
            <template #default="{ row }">
              <el-checkbox v-model="row.checkInterestCorrect" :disabled="isReadonly"
                @change="onCheckChange(row)" />
            </template>
          </el-table-column>
          <el-table-column label="减值计提正确" width="100" align="center">
            <template #default="{ row }">
              <el-checkbox v-model="row.checkImpairmentCorrect" :disabled="isReadonly"
                @change="onCheckChange(row)" />
            </template>
          </el-table-column>
          <el-table-column label="状态" width="80" align="center">
            <template #default="{ row }">
              <el-tag v-if="vc.isAllChecked(row)" type="success" size="small">全部通过</el-tag>
              <el-tag v-else type="info" size="small">待核对</el-tag>
            </template>
          </el-table-column>
        </template>

        <!-- Tab3: 结论+备注（贷方区） -->
        <template v-if="vc.activeTab.value === 'tab3'">
          <el-table-column label="序号" width="50" align="center" fixed>
            <template #default="{ row }">{{ row.seq }}</template>
          </el-table-column>
          <el-table-column label="凭证编号" width="90" fixed>
            <template #default="{ row }">{{ row.voucherNo }}</template>
          </el-table-column>
          <el-table-column label="索引号" width="100">
            <template #default="{ row }">
              <GtIndexChip v-if="row.indexRef" :value="row.indexRef" />
              <el-input v-else-if="!isReadonly" v-model="row.indexRef" size="small"
                placeholder="索引" />
            </template>
          </el-table-column>
          <el-table-column label="是否异常" width="85" align="center">
            <template #default="{ row }">
              <el-tag :type="row.isAbnormal ? 'danger' : 'success'" size="small">
                {{ row.isAbnormal ? '是' : '否' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="异常说明" min-width="180">
            <template #default="{ row }">
              <el-input v-if="!isReadonly && row.isAbnormal" v-model="row.abnormalNote"
                size="small" type="textarea" :autosize="{ minRows: 1, maxRows: 3 }" />
              <span v-else>{{ row.abnormalNote }}</span>
            </template>
          </el-table-column>
          <el-table-column label="备注" min-width="150">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" v-model="row.remark" size="small" />
              <span v-else>{{ row.remark }}</span>
            </template>
          </el-table-column>
        </template>

        <!-- 删除操作列（贷方区） -->
        <el-table-column v-if="!isReadonly" label="" width="50" align="center" fixed="right">
          <template #default="{ row }">
            <el-popconfirm title="确认删除？" @confirm="vc.removeRow(row.id)">
              <template #reference>
                <el-icon class="delete-icon"><Delete /></el-icon>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 底部审计结论 -->
    <el-card class="conclusion-card" shadow="never">
      <div class="conclusion-header">
        <span class="conclusion-title">审计结论</span>
        <el-button size="small" type="primary" link :disabled="isReadonly"
          @click="handleAiConclusion">
          🤖 AI生成
        </el-button>
      </div>
      <el-input
        v-model="conclusion"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="请输入凭证检查的审计结论..."
        :disabled="isReadonly"
      />
    </el-card>

    <!-- 编制提示 -->
    <details class="prep-hint">
      <summary>编制提示</summary>
      <ul>
        <li>凭证检查应按借方区和贷方区分别记录</li>
        <li>6项核对内容全部✓后显示"全部通过"标签</li>
        <li>任一核对项未通过(✗)将自动标记为异常行（红色高亮）</li>
        <li>借贷金额合计应平衡，差额以红色显示在顶部汇总区</li>
        <li>📎附件列可上传凭证附件进行OCR识别</li>
        <li>索引号可跳转至关联底稿</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * G4TabVoucherCheck.vue — G4-13 凭证检查表（97行×19列→3区段Tab）
 *
 * - el-segmented 切换 Tab1(记账凭证)/Tab2(支持性文件+核对)/Tab3(结论+备注)
 * - 分借方区/贷方区两个区块
 * - Tab2: 6项checkbox，全✓→绿色badge
 * - Tab3: 任一核对✗→自动isAbnormal=true+红色高亮
 * - 顶部借贷平衡汇总
 * - 动态行增删(ElMessageBox.prompt)
 * - GtIndexChip索引跳转
 * - inject openReviewDialog
 * - 集成 GtVoucherSamplingEngine 抽凭引擎
 * - 行级OCR：📎上传→POST /d4/contract-ocr→ElMessageBox确认→merge填入
 */
import { ref, computed, inject, onMounted } from 'vue'
import { Delete, Paperclip } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/utils/http'
import { useG4EclVoucherCheck } from '../../composables/useG4EclVoucherCheck'
import GtIndexChip from '../../GtIndexChip.vue'
import GtVoucherSamplingEngine from '../../voucher-sampling/GtVoucherSamplingEngine.vue'
import type { VoucherCheckRow } from '../../composables/useG4EclFormData'
import type { SampledVoucher, FillMode, Phase } from '../../composables/useSamplingAlgorithms'

const props = defineProps<{
  htmlData: Record<string, any> | null
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})

const vc = useG4EclVoucherCheck()
const conclusion = ref('')
const showSampling = ref(false)

// ─── 当前年份（从htmlData或默认） ────────────────────────────────────────────

const currentYear = computed(() => {
  const bsDate = props.htmlData?.bsDate as string | undefined
  if (bsDate && bsDate.length >= 4) return parseInt(bsDate.slice(0, 4), 10)
  return new Date().getFullYear() - 1
})

// ─── 区段Tab选项 ─────────────────────────────────────────────────────────────

const segmentOptions = [
  { label: '记账凭证', value: 'tab1' },
  { label: '支持性文件+核对', value: 'tab2' },
  { label: '结论+备注', value: 'tab3' },
]

// ─── 显示行 ─────────────────────────────────────────────────────────────────

const debitDisplayRows = computed(() => vc.debitRows.value)
const creditDisplayRows = computed(() => vc.creditRows.value)

// ─── 行同步（activeRowIndex 跨Tab保持） ─────────────────────────────────────

function onCurrentChange(row: VoucherCheckRow | null) {
  if (!row) return
  const allRows = vc.rows.value
  const idx = allRows.findIndex(r => r.id === row.id)
  if (idx >= 0) vc.activeRowIndex.value = idx
}

// ─── 行样式（Tab3异常行红色高亮） ───────────────────────────────────────────

function getRowClassName({ row }: { row: VoucherCheckRow }): string {
  if (row.isAbnormal) return 'row-abnormal'
  return ''
}

// ─── 核对checkbox变更 → 自动重算异常状态 ────────────────────────────────────

function onCheckChange(row: VoucherCheckRow): void {
  vc.recalcAbnormal(row)
}

// ─── 动态行增删 ─────────────────────────────────────────────────────────────

async function handleAddDebit() {
  await vc.addRow('debit')
}

async function handleAddCredit() {
  await vc.addRow('credit')
}

// ─── 抽凭引擎集成（Requirements: 6.3, 9.2） ─────────────────────────────────

function handleSamplingFilled(payload: { samples: SampledVoucher[]; phase: Phase; fillMode: FillMode }): void {
  // 将抽样结果映射为 fillVoucherSamples 所需格式
  const mappedSamples = payload.samples.map(s => ({
    voucherNo: s.voucherNo,
    date: s.voucherDate || '',
    businessContent: s.summary || '',
    counterAccount: s.counterpartAccount || '',
    detailAccount: s.accountName || '',
    debitAmount: s.debitAmount ? parseFloat(s.debitAmount) : 0,
    creditAmount: s.creditAmount ? parseFloat(s.creditAmount) : 0,
    section: (s.debitAmount && parseFloat(s.debitAmount) > 0 ? 'debit' : 'credit') as 'debit' | 'credit',
  }))
  vc.fillVoucherSamples(mappedSamples)
  ElMessage.success(`已填入 ${mappedSamples.length} 条抽凭样本`)
}

// ─── 行级OCR（Requirements: 6.4, 9.3） ──────────────────────────────────────

const ocrLoadingRowId = ref<string | null>(null)

/** OCR字段映射：OCR识别字段名 → VoucherCheckRow字段名 */
const OCR_FIELD_MAP: Record<string, keyof VoucherCheckRow> = {
  date: 'date',
  凭证日期: 'date',
  voucher_date: 'date',
  voucher_no: 'voucherNo',
  凭证号: 'voucherNo',
  凭证编号: 'voucherNo',
  summary: 'businessContent',
  摘要: 'businessContent',
  business_content: 'businessContent',
  业务内容: 'businessContent',
  counter_account: 'counterAccount',
  对方科目: 'counterAccount',
  detail_account: 'detailAccount',
  明细科目: 'detailAccount',
  debit_amount: 'debitAmount',
  借方金额: 'debitAmount',
  credit_amount: 'creditAmount',
  贷方金额: 'creditAmount',
  amount: 'debitAmount',
  金额: 'debitAmount',
}

/**
 * 将OCR识别结果映射为VoucherCheckRow可merge的字段对象
 */
function mapOcrToVoucherFields(fields: Record<string, any>): Partial<VoucherCheckRow> {
  const patch: Partial<VoucherCheckRow> = {}
  for (const [ocrKey, val] of Object.entries(fields)) {
    const target = OCR_FIELD_MAP[ocrKey]
    if (target && val != null && String(val).trim() !== '') {
      if (target === 'debitAmount' || target === 'creditAmount') {
        const num = parseFloat(String(val).replace(/,/g, ''))
        if (!isNaN(num)) (patch as any)[target] = num
      } else {
        (patch as any)[target] = String(val).trim()
      }
    }
  }
  return patch
}

/**
 * 渲染OCR识别结果预览HTML
 */
function renderOcrPreview(fields: Record<string, any>): string {
  const patch = mapOcrToVoucherFields(fields)
  const LABEL_MAP: Record<string, string> = {
    date: '日期',
    voucherNo: '凭证编号',
    businessContent: '业务内容',
    counterAccount: '对方科目',
    detailAccount: '明细科目',
    debitAmount: '借方金额',
    creditAmount: '贷方金额',
  }
  const lines = Object.entries(patch)
    .filter(([, v]) => v != null && String(v) !== '')
    .map(([k, v]) => `<div style="margin:4px 0"><b>${LABEL_MAP[k] || k}：</b>${v}</div>`)
  if (lines.length === 0) return '<div>未识别到可填充字段</div>'
  return `<div style="font-size:14px">${lines.join('')}</div>`
}

/**
 * 行级OCR处理：上传→OCR识别→确认→填入
 */
async function handleRowOcr(row: VoucherCheckRow, file: File): Promise<boolean> {
  if (props.isReadonly || !props.wpId) return false
  ocrLoadingRowId.value = row.id
  try {
    const formData = new FormData()
    formData.append('file', file)
    const res = await http.post(
      `/api/workpapers/${props.wpId}/d4/contract-ocr`,
      formData,
      { headers: { 'Content-Type': 'multipart/form-data' }, _silent: true } as any,
    )
    const fields: Record<string, any> = (res.data?.data ?? res.data)?.extracted_fields || {}
    if (!Object.keys(fields).length) {
      ElMessage.info('OCR完成，未识别到可填充字段')
      return false
    }
    const patch = mapOcrToVoucherFields(fields)
    if (Object.keys(patch).length === 0) {
      ElMessage.info('OCR完成，识别字段无法匹配当前行')
      return false
    }
    // 确认弹窗
    await ElMessageBox.confirm(renderOcrPreview(fields), 'OCR识别结果', {
      confirmButtonText: '填入',
      cancelButtonText: '取消',
      dangerouslyUseHTMLString: true,
    })
    // 合并填入
    Object.assign(row, patch)
    row.attachment = file.name
    ElMessage.success('已填入OCR识别结果')
  } catch (e: any) {
    if (e !== 'cancel' && e?.toString?.() !== 'cancel') {
      ElMessage.warning('OCR识别失败或已取消')
    }
  } finally {
    ocrLoadingRowId.value = null
  }
  return false // 阻止el-upload默认上传行为
}

// ─── AI生成审计结论 ─────────────────────────────────────────────────────────

function handleAiConclusion() {
  ElMessage.info('AI生成审计结论功能将在AI模块完成后启用')
}

// ─── 数字格式化 ─────────────────────────────────────────────────────────────

function fmtNum(v: unknown): string {
  if (v === 0) return '0.00'
  if (typeof v === 'number') {
    return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  }
  return String(v ?? '')
}

// ─── 数据加载 ───────────────────────────────────────────────────────────────

onMounted(() => {
  if (props.htmlData?.voucherCheck) {
    const data = props.htmlData.voucherCheck
    vc.loadRows(data.rows || [])
    if (data.conclusion) conclusion.value = data.conclusion
  }
})

// ─── 暴露序列化接口供父组件保存使用 ─────────────────────────────────────────

defineExpose({
  toJSON: () => ({
    ...vc.toJSON(),
    conclusion: conclusion.value,
  }),
})
</script>

<style scoped>
.g4-voucher-check {
  padding: 12px;
  font-size: 13px;
}

.section-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.sheet-title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
}

.head-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

/* 借贷平衡汇总区 */
.balance-summary {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 8px 12px;
  border-radius: 6px;
  background: #f0f9eb;
  border: 1px solid #e1f3d8;
  margin-bottom: 12px;
  transition: all 0.2s;
}

.balance-summary.unbalanced {
  background: #fef0f0;
  border-color: #fde2e2;
}

.balance-item {
  display: flex;
  align-items: center;
  gap: 4px;
}

.balance-label {
  color: #606266;
  font-size: 13px;
}

.balance-value {
  font-weight: 600;
  font-size: 14px;
  color: #303133;
}

.diff-red {
  color: #f56c6c !important;
  font-weight: 700;
}

/* 区块 */
.section-block {
  margin-bottom: 16px;
}

.block-header {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
  margin-bottom: 8px;
  padding: 4px 8px;
  background: #ecf5ff;
  border-radius: 4px;
  border-left: 3px solid #409eff;
}

/* 表格 */
.voucher-table {
  font-size: 13px;
}

.compact-num {
  width: 100%;
}

.compact-num :deep(.el-input__inner) {
  text-align: right;
}

/* 异常行：红色高亮 */
:deep(.row-abnormal) {
  background-color: #fef0f0 !important;
}
:deep(.row-abnormal td) {
  background-color: #fef0f0 !important;
}

/* 附件图标 */
.attach-icon {
  cursor: pointer;
  color: #909399;
  font-size: 16px;
  transition: color 0.2s;
}
.attach-icon:hover {
  color: #409eff;
}
.attach-icon.has-file {
  color: #67c23a;
}

/* 抽凭引擎折叠区 */
.sampling-collapse {
  margin-bottom: 12px;
}
.sampling-collapse :deep(.el-collapse-item__header) {
  font-size: 13px;
  font-weight: 500;
  color: #e6a23c;
}

/* el-upload行级OCR按钮 */
.has-file {
  color: #67c23a !important;
}

/* 删除图标 */
.delete-icon {
  cursor: pointer;
  color: #909399;
  transition: color 0.2s;
}
.delete-icon:hover {
  color: #f56c6c;
}

/* 审计结论卡片 */
.conclusion-card {
  margin-top: 16px;
}

.conclusion-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.conclusion-title {
  font-weight: 600;
  font-size: 14px;
}

/* 编制提示 */
.prep-hint {
  margin-top: 12px;
  font-size: 12px;
  color: #909399;
}
.prep-hint summary {
  cursor: pointer;
  font-weight: 500;
}
.prep-hint ul {
  margin: 8px 0 0;
  padding-left: 18px;
}
.prep-hint li {
  margin-bottom: 4px;
}
</style>
