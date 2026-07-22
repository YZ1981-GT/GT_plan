<template>
  <div class="h1-tab-title-building">
    <el-alert type="info" :closable="false" show-icon class="obj-alert">
      <template #title>
        审计目标：记录的房屋建筑物由被审计单位拥有或控制；权证齐全且与账面勾稽；抵押/查封等受限情形已识别并支持附注披露。
      </template>
    </el-alert>

    <div class="tab-toolbar" style="display:flex;justify-content:flex-end;align-items:center;gap:8px;margin-bottom:8px;flex-wrap:wrap">
      <GtIndexChip value="wp:H1-16" :context-project-id="projectId" />
      <el-tag size="small" type="info">共 {{ buildingRows.length }} 项</el-tag>
    </div>

    <div class="methodology-context">
      <p>
        从 H1-2 房屋建筑物明细确定检查总体 → 核对不动产权证/房屋所有权证（权利人、坐落、面积、用途、他项权利）→
        账面原值/净值勾稽 → 抵押/查封索引至附注受限资产。每次审计须重新取得权证原件并与复印件核对。
      </p>
    </div>

    <el-card shadow="never" class="coverage-card">
      <template #header><span>检查范围</span></template>
      <div class="coverage-grid">
        <div class="coverage-item">
          <span class="coverage-label">账面栋数</span>
          <el-input-number
            v-if="!isReadonly"
            v-model="coverage.bookCount"
            :controls="false"
            size="small"
            :min="0"
            @change="saveCoverage"
          />
          <span v-else>{{ coverage.bookCount ?? '-' }}</span>
        </div>
        <div class="coverage-item">
          <span class="coverage-label">本次检查</span>
          <el-tag size="small">{{ buildingRows.length }}</el-tag>
        </div>
        <div class="coverage-item">
          <span class="coverage-label">检查方式</span>
          <el-select
            v-if="!isReadonly"
            v-model="coverage.method"
            size="small"
            style="width:100px"
            @change="saveCoverage"
          >
            <el-option label="全查" value="全查" />
            <el-option label="抽样" value="抽样" />
          </el-select>
          <span v-else>{{ coverage.method || '-' }}</span>
        </div>
        <div class="coverage-item coverage-wide">
          <span class="coverage-label">抽样说明</span>
          <el-input
            v-if="!isReadonly"
            v-model="coverage.sampleNote"
            size="small"
            placeholder="抽样方法、样本量及代表结论；重大/抵押房产是否必查"
            @change="saveCoverage"
          />
          <span v-else>{{ coverage.sampleNote || '-' }}</span>
        </div>
      </div>
    </el-card>

    <!-- 未办证在建转固清单（单独提示） -->
    <el-alert
      v-if="buildingStats.uncertifiedCipCount > 0"
      type="warning"
      :closable="false"
      show-icon
      class="cip-alert"
    >
      <template #title>
        未办证在建转固 {{ buildingStats.uncertifiedCipCount }} 项，账面净值合计 {{ fmtAmt(buildingStats.uncertifiedCipNetTotal) }}
        —— 须说明办证进度、预计办证日，并评估对权属认定/披露的影响
      </template>
    </el-alert>
    <el-card v-if="buildingStats.uncertifiedCipCount > 0" shadow="never" class="cip-card">
      <template #header>
        <div class="section-title">
          <span>未办证在建转固清单</span>
          <el-button
            v-if="!isReadonly"
            size="small"
            type="primary"
            link
            @click="appendCipNoteToAudit"
          >一键写入审计说明</el-button>
        </div>
      </template>
      <el-table :data="uncertifiedCipRows" border size="small" max-height="220">
        <el-table-column prop="assetCode" label="资产编号" width="100" />
        <el-table-column prop="name" label="资产名称" min-width="120" />
        <el-table-column prop="netValue" label="净值" width="110" align="right">
          <template #default="{ row }">{{ fmtAmt(row.netValue) }}</template>
        </el-table-column>
        <el-table-column prop="completionDate" label="转固日期" width="120">
          <template #default="{ row }">
            <el-date-picker
              v-if="!isReadonly"
              v-model="row.completionDate"
              type="date"
              value-format="YYYY-MM-DD"
              size="small"
              style="width:110px"
              @change="onCell(row, 'completionDate')"
            />
            <span v-else>{{ row.completionDate || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="expectedCertDate" label="预计办证日" width="120">
          <template #default="{ row }">
            <el-date-picker
              v-if="!isReadonly"
              v-model="row.expectedCertDate"
              type="date"
              value-format="YYYY-MM-DD"
              size="small"
              style="width:110px"
              @change="onCell(row, 'expectedCertDate')"
            />
            <span v-else>{{ row.expectedCertDate || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="cipNote" label="办证进度说明" min-width="160">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              v-model="row.cipNote"
              size="small"
              placeholder="规划验收/测绘/登记进度"
              @change="onCell(row, 'cipNote')"
            />
            <span v-else>{{ row.cipNote || '-' }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card shadow="never">
      <template #header>
        <div class="section-title">
          <span>H1-16 房屋建筑物权属检查 <el-tag size="small" type="info">共 {{ buildingRows.length }} 项</el-tag></span>
          <div class="title-actions">
            <el-button
              size="small"
              type="primary"
              plain
              :disabled="isReadonly || h12BuildingCount === 0"
              @click="handleImportH12"
            >从 H1-2 带入</el-button>
            <el-button
              size="small"
              type="warning"
              plain
              :disabled="isReadonly || buildingStats.mortgagedCount === 0"
              @click="handleSyncDisclosure"
            >同步抵押至附注</el-button>
            <el-button size="small" type="primary" :disabled="isReadonly" @click="handleAddRow">+ 新增</el-button>
            <el-button size="small" type="default" link @click="handleReview('H1-16')">💬 复核</el-button>
          </div>
        </div>
      </template>

      <el-table
        :data="buildingRows"
        border
        stripe
        size="small"
        max-height="520"
        class="title-table"
        :row-class-name="rowClassName"
      >
        <el-table-column type="index" width="40" fixed />

        <!-- A. 财务账面记录 -->
        <el-table-column label="财务账面记录" align="center">
          <el-table-column prop="assetCode" label="资产编号" width="100" fixed>
            <template #default="{ row }">
              <el-input v-if="!isReadonly" v-model="row.assetCode" size="small" @change="onCell(row, 'assetCode')" />
              <span v-else>{{ row.assetCode }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="name" label="资产名称" min-width="110" fixed>
            <template #default="{ row }">
              <el-input v-if="!isReadonly" v-model="row.name" size="small" @change="onCell(row, 'name')" />
              <span v-else>{{ row.name }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="bookValue" label="原值" width="110" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly" v-model="row.bookValue" :controls="false" size="small" @change="onCell(row, 'bookValue')" />
              <span v-else class="amount-cell">{{ fmtAmt(row.bookValue) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="accumDep" label="累计折旧" width="100" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly" v-model="row.accumDep" :controls="false" size="small" @change="onCell(row, 'accumDep')" />
              <span v-else class="amount-cell">{{ fmtAmt(row.accumDep) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="impairment" label="减值准备" width="100" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly" v-model="row.impairment" :controls="false" size="small" @change="onCell(row, 'impairment')" />
              <span v-else class="amount-cell">{{ fmtAmt(row.impairment) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="净值" width="110" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="净值=原值-累计折旧-减值准备">{{ fmtAmt(row.netValue) }}</span>
            </template>
          </el-table-column>
        </el-table-column>

        <!-- B. 权证记载 -->
        <el-table-column label="权证记载" align="center">
          <el-table-column prop="titleCertNo" label="权证编号" width="130">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" v-model="row.titleCertNo" size="small" @change="onCell(row, 'titleCertNo')" />
              <span v-else>{{ row.titleCertNo }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="owner" label="权利人" width="120">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" v-model="row.owner" size="small" @change="onCell(row, 'owner')" />
              <span v-else>{{ row.owner }}</span>
            </template>
          </el-table-column>
          <el-table-column label="权利人为被审计单位" width="130" align="center">
            <template #default="{ row }">
              <el-select v-if="!isReadonly" v-model="row.isOwnerEntity" size="small" style="width:70px" @change="onCell(row, 'isOwnerEntity')">
                <el-option label="是" value="Y" />
                <el-option label="否" value="N" />
              </el-select>
              <el-tag v-else :type="row.isOwnerEntity === 'Y' ? 'success' : 'danger'" size="small">
                {{ row.isOwnerEntity === 'Y' ? '是' : '否' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="coOwnership" label="共有情况" width="90">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" v-model="row.coOwnership" size="small" placeholder="单独/共有" @change="onCell(row, 'coOwnership')" />
              <span v-else>{{ row.coOwnership || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="address" label="房屋坐落" min-width="140">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" v-model="row.address" size="small" @change="onCell(row, 'address')" />
              <span v-else>{{ row.address }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="issueDate" label="登记时间" width="120">
            <template #default="{ row }">
              <el-date-picker
                v-if="!isReadonly"
                v-model="row.issueDate"
                type="date"
                value-format="YYYY-MM-DD"
                size="small"
                style="width:110px"
                @change="onCell(row, 'issueDate')"
              />
              <span v-else>{{ row.issueDate || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="propertyNature" label="权利类型" width="100">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" v-model="row.propertyNature" size="small" placeholder="如国有/出让" @change="onCell(row, 'propertyNature')" />
              <span v-else>{{ row.propertyNature || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="usage" label="规划用途" width="90">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" v-model="row.usage" size="small" @change="onCell(row, 'usage')" />
              <span v-else>{{ row.usage }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="buildingArea" label="建筑面积㎡" width="100" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly" v-model="row.buildingArea" :controls="false" size="small" @change="onCell(row, 'buildingArea')" />
              <span v-else>{{ row.buildingArea || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="usefulLife" label="使用期限" width="100">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" v-model="row.usefulLife" size="small" @change="onCell(row, 'usefulLife')" />
              <span v-else>{{ row.usefulLife || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="otherRights" label="他项权利" width="100">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" v-model="row.otherRights" size="small" placeholder="抵押/查封等" @change="onCell(row, 'otherRights')" />
              <span v-else>{{ row.otherRights || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="certCopyIndex" label="权证索引" width="100">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" v-model="row.certCopyIndex" size="small" placeholder="复印件索引" @change="onCell(row, 'certCopyIndex')" />
              <span v-else>{{ row.certCopyIndex || '-' }}</span>
            </template>
          </el-table-column>
        </el-table-column>

        <!-- C. 抵押情况 -->
        <el-table-column label="抵押情况" align="center">
          <el-table-column label="抵押受限" width="80" align="center">
            <template #default="{ row }">
              <el-select v-if="!isReadonly" v-model="row.isMortgaged" size="small" style="width:56px" @change="onCell(row, 'isMortgaged')">
                <el-option label="是" value="Y" />
                <el-option label="否" value="N" />
              </el-select>
              <el-tag v-else-if="row.isMortgaged === 'Y'" type="warning" size="small">有</el-tag>
              <span v-else>-</span>
            </template>
          </el-table-column>
          <el-table-column prop="mortgageArea" label="抵押面积" width="90" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="!isReadonly && row.isMortgaged === 'Y'"
                v-model="row.mortgageArea"
                :controls="false"
                size="small"
                @change="onCell(row, 'mortgageArea')"
              />
              <span v-else>{{ row.isMortgaged === 'Y' ? (row.mortgageArea || '-') : '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="mortgageAmount" label="抵押价值" width="110" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="!isReadonly && row.isMortgaged === 'Y'"
                v-model="row.mortgageAmount"
                :controls="false"
                size="small"
                @change="onCell(row, 'mortgageAmount')"
              />
              <span v-else class="amount-cell">{{ row.isMortgaged === 'Y' ? fmtAmt(row.mortgageAmount) : '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="mortgageNature" label="抵押性质" width="100">
            <template #default="{ row }">
              <el-input
                v-if="!isReadonly && row.isMortgaged === 'Y'"
                v-model="row.mortgageNature"
                size="small"
                placeholder="最高额等"
                @change="onCell(row, 'mortgageNature')"
              />
              <span v-else>{{ row.isMortgaged === 'Y' ? (row.mortgageNature || '-') : '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="mortgagee" label="抵押权人" width="110">
            <template #default="{ row }">
              <el-input
                v-if="!isReadonly && row.isMortgaged === 'Y'"
                v-model="row.mortgagee"
                size="small"
                @change="onCell(row, 'mortgagee')"
              />
              <span v-else>{{ row.isMortgaged === 'Y' ? (row.mortgagee || '-') : '-' }}</span>
            </template>
          </el-table-column>
        </el-table-column>

        <!-- D. 在建转固 / 未办证 -->
        <el-table-column label="在建转固" align="center">
          <el-table-column label="在建转固" width="80" align="center">
            <template #default="{ row }">
              <el-select v-if="!isReadonly" v-model="row.fromCip" size="small" style="width:56px" @change="onCell(row, 'fromCip')">
                <el-option label="是" value="Y" />
                <el-option label="否" value="N" />
              </el-select>
              <el-tag v-else-if="row.fromCip === 'Y'" type="warning" size="small">是</el-tag>
              <span v-else>-</span>
            </template>
          </el-table-column>
          <el-table-column prop="completionDate" label="转固日期" width="120">
            <template #default="{ row }">
              <el-date-picker
                v-if="!isReadonly && row.fromCip === 'Y'"
                v-model="row.completionDate"
                type="date"
                value-format="YYYY-MM-DD"
                size="small"
                style="width:110px"
                @change="onCell(row, 'completionDate')"
              />
              <span v-else>{{ row.fromCip === 'Y' ? (row.completionDate || '-') : '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="expectedCertDate" label="预计办证" width="120">
            <template #default="{ row }">
              <el-date-picker
                v-if="!isReadonly && row.fromCip === 'Y'"
                v-model="row.expectedCertDate"
                type="date"
                value-format="YYYY-MM-DD"
                size="small"
                style="width:110px"
                @change="onCell(row, 'expectedCertDate')"
              />
              <span v-else>{{ row.fromCip === 'Y' ? (row.expectedCertDate || '-') : '-' }}</span>
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column prop="checkConclusion" label="核对结论" width="110" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.checkConclusion" size="small" style="width:100px" @change="onCell(row, 'checkConclusion')">
              <el-option label="相符" value="相符" />
              <el-option label="不符" value="不符" />
              <el-option label="未取得权证" value="未取得权证" />
            </el-select>
            <el-tag v-else :type="checkTagType(row.checkConclusion)" size="small">{{ row.checkConclusion || '-' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="remark" label="备注" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.remark" size="small" @change="onCell(row, 'remark')" />
            <span v-else>{{ row.remark }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="OCR" width="56" align="center" fixed="right">
          <template #default="{ row }">
            <el-button
              link
              size="small"
              :loading="ocrLoadingId === row.rowId"
              title="上传权证扫描件 OCR 预填"
              @click="handleOcr(row)"
            >📎</el-button>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="操作" width="50" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="danger" link @click="removeBuildingRow(row.rowId)">删</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="summary-bar">
        <span>总计: {{ buildingStats.totalChecked }} 项</span>
        <span>账面净值合计: <b>{{ fmtAmt(buildingStats.bookNetTotal) }}</b></span>
        <span>权属异常: <b :class="{ 'error-amount': buildingStats.ownerAnomalyCount > 0 }">{{ buildingStats.ownerAnomalyCount }}</b></span>
        <span>不符/未取得: <b :class="{ 'error-amount': buildingStats.mismatchCount > 0 }">{{ buildingStats.mismatchCount }}</b></span>
        <span>
          未办证转固: <b :class="{ 'warn-amount': buildingStats.uncertifiedCipCount > 0 }">{{ buildingStats.uncertifiedCipCount }}</b>
          （净值 {{ fmtAmt(buildingStats.uncertifiedCipNetTotal) }}）
        </span>
        <span>
          有抵押: <b :class="{ 'warn-amount': buildingStats.mortgagedCount > 0 }">{{ buildingStats.mortgagedCount }}</b>
          ，合计 {{ fmtAmt(buildingStats.mortgageAmountTotal) }}
        </span>
      </div>
    </el-card>

    <el-card shadow="never" class="note-card">
      <template #header><span>审计说明</span></template>
      <el-input
        v-model="auditNoteText"
        type="textarea"
        :autosize="{ minRows: 6 }"
        :disabled="isReadonly"
        :placeholder="notePlaceholder"
        @change="saveAuditNote"
      />
    </el-card>

    <el-card shadow="never" class="note-card">
      <template #header><span>审计结论</span></template>
      <el-input
        v-model="conclusion"
        type="textarea"
        :autosize="{ minRows: 3 }"
        :disabled="isReadonly"
        :placeholder="conclusionPlaceholder"
        @change="saveAuditConclusion"
      />
    </el-card>

    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>不动产权证/房屋所有权证是权属核心证据；每次审计须重新取得原件并与复印件核对</li>
        <li>权利人非被审计单位标红；须补充代持/控制权证据并评估确认条件（CAS4）</li>
        <li>他项权利栏有抵押/查封时同步勾选抵押受限；须核对附注“所有权受限资产”披露</li>
        <li>净值=原值−累计折旧−减值准备；与 H1-2 房屋建筑物明细勾稽</li>
        <li>未办证在建转固房产单独列示：填转固日/预计办证日/办证进度，并可一键写入审计说明</li>
        <li>行末 📎 上传权证扫描件 → OCR 预填权证字段（仅填空，不覆盖已有值）</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, inject, toRef, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  useH1TitleCheck,
  H1_PROPERTY_OCR_FIELD_LABELS,
  type BuildingRow,
} from '../../composables/useH1TitleCheck'
import GtIndexChip from '../../GtIndexChip.vue'
import http from '@/utils/http'

const props = defineProps<{ wpId: string; projectId: string; allResponses: Map<string, any>; isReadonly: boolean }>()
const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const saveResponse = inject<(id: string, val: any) => void>('saveResponse', () => {})
const allResponsesRef = computed(() => props.allResponses)

const conclusion = ref('')
const auditNoteText = ref('')
const ocrLoadingId = ref('')
const coverage = ref<{ bookCount: number | null; method: string; sampleNote: string }>({
  bookCount: null,
  method: '全查',
  sampleNote: '',
})

const NOTE_KEY = 'H1-16-audit-note'
const CONCLUSION_KEY = 'H1-16-audit-conclusion'
const COVERAGE_KEY = 'H1-16-coverage'

const notePlaceholder = [
  '1. 权证是否齐全；权利人是否为被审计单位（代持需说明控制依据）；坐落/面积/用途与账面是否一致',
  '2. 房屋抵押/查封等受限情况：抵押面积、抵押价值、抵押权人及合同索引；是否已纳入附注受限资产披露',
  '3. 未办证在建转固房产：转固日、预计办证日、办证进度及对权属认定的影响',
  '4. 例外事项及调整建议',
].join('\n')

const conclusionPlaceholder =
  '经检查，除上述例外外，检查的房屋建筑物权属证明齐全，权利人与被审计单位一致，抵押受限已充分识别并与附注披露相符；未办证在建转固房产已单独列示并说明办证进度。 / 存在下列重大例外：……'

function saveAuditNote() { saveResponse(NOTE_KEY, auditNoteText.value) }
function saveAuditConclusion() { saveResponse(CONCLUSION_KEY, conclusion.value) }
function saveCoverage() { saveResponse(COVERAGE_KEY, JSON.stringify(coverage.value)) }

onMounted(() => {
  const n = props.allResponses.get(NOTE_KEY)
  if (n?.remark) auditNoteText.value = n.remark
  const c = props.allResponses.get(CONCLUSION_KEY)
  if (c?.remark) conclusion.value = c.remark
  const cov = props.allResponses.get(COVERAGE_KEY)
  if (cov?.remark) {
    try {
      const parsed = JSON.parse(cov.remark)
      if (parsed && typeof parsed === 'object') coverage.value = { ...coverage.value, ...parsed }
    } catch { /* ignore */ }
  }
})

const {
  buildingRows,
  buildingStats,
  uncertifiedCipRows,
  h12BuildingCount,
  addBuildingRow,
  removeBuildingRow,
  updateBuildingCell,
  mergeBuildingOcrResult,
  importBuildingsFromH12,
  syncMortgagedBuildingsToDisclosure,
} = useH1TitleCheck(
  toRef(props, 'wpId'),
  toRef(props, 'projectId'),
  allResponsesRef as any,
  { onSave: (itemId, value) => saveResponse(itemId, value) },
)

async function handleAddRow() {
  const { value: name } = await ElMessageBox.prompt('建筑物名称', '新增', { confirmButtonText: '确定', cancelButtonText: '取消' })
  if (name) addBuildingRow(name)
}
function handleImportH12() {
  const { added, skipped, total } = importBuildingsFromH12()
  if (total === 0) {
    ElMessage.warning('H1-2 中未找到房屋建筑物分类明细')
    return
  }
  ElMessage.success(`已从 H1-2 带入 ${added} 项（跳过 ${skipped}，源 ${total}）`)
}
function handleSyncDisclosure() {
  const n = syncMortgagedBuildingsToDisclosure()
  ElMessage.success(n > 0 ? `已同步 ${n} 项抵押房屋至附注受限资产` : '无抵押房屋可同步')
}
function appendCipNoteToAudit() {
  const lines = uncertifiedCipRows.value.map((r, i) => {
    const parts = [
      `${i + 1}. ${[r.assetCode, r.name].filter(Boolean).join(' ') || '未命名'}`,
      `净值${fmtAmt(r.netValue)}`,
      r.completionDate ? `转固${r.completionDate}` : '',
      r.expectedCertDate ? `预计办证${r.expectedCertDate}` : '',
      r.cipNote || '办证进度待补充',
    ].filter(Boolean)
    return parts.join('；')
  })
  const block = [
    '【未办证在建转固】',
    ...lines,
    `合计 ${buildingStats.value.uncertifiedCipCount} 项，净值 ${fmtAmt(buildingStats.value.uncertifiedCipNetTotal)}。`,
  ].join('\n')
  auditNoteText.value = auditNoteText.value
    ? `${auditNoteText.value.trim()}\n\n${block}`
    : block
  saveAuditNote()
  ElMessage.success('已写入审计说明')
}

/** 行级权证 OCR：📎 → POST /h1/property-title-ocr → 确认 → 仅填空预填 */
async function handleOcr(row: BuildingRow) {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = 'image/*,.pdf'
  input.onchange = async () => {
    const file = input.files?.[0]
    if (!file) return
    const formData = new FormData()
    formData.append('file', file)
    ocrLoadingId.value = row.rowId
    try {
      const res = await http.post(
        `/api/workpapers/${props.wpId}/h1/property-title-ocr`,
        formData,
        { headers: { 'Content-Type': 'multipart/form-data' }, _silent: true } as any,
      )
      const data = res.data?.data ?? res.data
      const fields = { ...(data?.extracted_fields || {}) }
      if (data?.attachment_id) fields.attachment_id = data.attachment_id
      const previewEntries = Object.entries(fields)
        .filter(([k, v]) => k !== 'attachment_id' && v !== '' && v != null && v !== 0)
        .map(([k, v]) => `${H1_PROPERTY_OCR_FIELD_LABELS[k] || k}: ${v}`)
      if (!previewEntries.length) {
        ElMessageBox.alert('OCR 完成，未识别到可填充字段，请核对扫描件清晰度后重试', '提示')
        return
      }
      const confPct = Math.round(Number(data?.confidence || 0) * 100)
      await ElMessageBox.confirm(
        `置信度 ${confPct}%\n\n${previewEntries.join('\n')}\n\n确认填入空白字段？`,
        '权证 OCR 识别结果',
        { confirmButtonText: '填入', cancelButtonText: '取消', type: confPct < 50 ? 'warning' : 'info' },
      )
      const filled = mergeBuildingOcrResult(row.rowId, fields)
      ElMessage.success(filled.length ? `已预填 ${filled.length} 个字段` : '无可填空字段（已有值未覆盖）')
    } catch (e: any) {
      if (e !== 'cancel' && e?.message !== 'cancel') {
        ElMessage.warning('权证 OCR 失败，请稍后重试或手工录入')
      }
    } finally {
      ocrLoadingId.value = ''
    }
  }
  input.click()
}

function onCell(row: BuildingRow, field: keyof BuildingRow) {
  updateBuildingCell(row.rowId, field, (row as any)[field])
}
function handleReview(id: string) { openReviewDialog(id) }
function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
function checkTagType(v: string): 'success' | 'danger' | 'warning' | 'info' {
  if (v === '相符') return 'success'
  if (v === '不符') return 'danger'
  if (v === '未取得权证') return 'warning'
  return 'info'
}
function rowClassName({ row }: { row: BuildingRow }) {
  if (row.isOwnerEntity === 'N' || row.checkConclusion === '不符' || row.checkConclusion === '未取得权证') {
    return 'row-anomaly'
  }
  if (row.fromCip === 'Y' && !(row.titleCertNo || '').trim()) {
    return 'row-warn'
  }
  if (row.isMortgaged === 'Y' || row.isRestricted === 'Y') {
    return 'row-warn'
  }
  return ''
}
</script>

<style scoped>
.h1-tab-title-building { padding: 16px; font-size: var(--wp-font-size, 13px); }
.obj-alert { margin-bottom: 12px; }
.methodology-context {
  border-left: 3px solid var(--el-color-warning);
  background: #fffbe6;
  padding: 10px 14px;
  margin-bottom: 12px;
  border-radius: 4px;
  font-size: 12px;
}
.coverage-card { margin-bottom: 12px; }
.cip-alert { margin-bottom: 8px; }
.cip-card { margin-bottom: 12px; }
.coverage-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(120px, 1fr));
  gap: 12px;
  align-items: center;
}
.coverage-item { display: flex; align-items: center; gap: 8px; }
.coverage-wide { grid-column: 1 / -1; }
.coverage-label { color: var(--el-text-color-secondary); white-space: nowrap; font-size: 12px; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.title-actions { display: flex; gap: 8px; flex-wrap: wrap; }
.title-table { font-size: var(--wp-font-size, 13px); }
.amount-cell { text-align: right; font-variant-numeric: tabular-nums; }
.formula-cell {
  border-bottom: 1px dashed var(--el-border-color);
  cursor: help;
  font-variant-numeric: tabular-nums;
}
.error-amount { color: var(--el-color-danger); }
.warn-amount { color: var(--el-color-warning); }
.summary-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 24px;
  padding: 10px 12px;
  margin-top: 12px;
  background: var(--el-fill-color-light);
  border-radius: 4px;
}
.note-card { margin-top: 12px; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
:deep(.row-anomaly) { background: #fef0f0 !important; }
:deep(.row-warn) { background: #fdf6ec !important; }
</style>
