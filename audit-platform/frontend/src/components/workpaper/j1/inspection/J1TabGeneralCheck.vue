<!--
  J1TabGeneralCheck.vue — J1-8 应付职工薪酬检查表（凭证级测试）

  致同源模板 J1-8：
    一、测试目标（发生/完整性准确性/截止）
    二、样本选取标准与规模
    三、测试（三区凭证检查：贷方计提+借方发放+期后支付）
    四、审计说明 — 检查比例
    五、审计结论

  复用 useK1VoucherCheck。科目 2211 应付职工薪酬（贷方/负债类）。
  源模板特点：
    - 贷方检查含"职工薪酬计算表"列（月份/人数/金额/是否恰当审批）
    - 借方检查含"付款审批单/银行回单"列
    - 期后支付区用于验证完整性（是否漏提）
-->
<template>
  <div class="j1-general-check">
    <div class="guide-banner">
      <div class="guide-step"><span class="gs-no">1</span>确认测试目标</div>
      <div class="guide-step"><span class="gs-no">2</span>样本选取标准</div>
      <div class="guide-step"><span class="gs-no">3</span>凭证级测试（三区）</div>
      <div class="guide-step"><span class="gs-no">4</span>检查比例+结论</div>
    </div>

    <div class="section-head">
      <h3 class="sheet-title">J1-8 应付职工薪酬检查表</h3>
      <div class="head-actions">
        <el-popover placement="bottom-end" :width="260" trigger="click">
          <template #reference>
            <el-button size="small">⚙ 列设置</el-button>
          </template>
          <div class="col-prefs">
            <div class="col-prefs-title">显示/隐藏列</div>
            <el-checkbox v-for="col in columnDefs" :key="col.key" v-model="col.visible" size="small" @change="persistColumnPrefs">
              {{ col.label }}
            </el-checkbox>
            <el-divider style="margin:8px 0" />
            <el-button size="small" link @click="resetColumnPrefs">重置默认</el-button>
          </div>
        </el-popover>
        <el-button size="small" type="primary" link @click="handleAiGenerate">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <el-button size="small" @click="handleReview">💬 复核</el-button>
      </div>
    </div>

    <!-- 一、测试目标 -->
    <el-alert type="info" :closable="false" class="audit-objective">
      <template #title><span class="ao-title">一、测试目标（认定）</span></template>
      <ol class="ao-list">
        <li><b>发生：</b>利润表中记录的应付职工薪酬计提已发生且与被审计单位有关；</li>
        <li><b>完整性与准确性：</b>所有应计提的职工薪酬均已记录，金额恰当（人数×单价×月数与审批一致）；</li>
        <li><b>截止：</b>薪酬计提/发放已记录于正确的会计期间（跨期计提完整性）。</li>
      </ol>
    </el-alert>

    <!-- 方法论（琥珀色） -->
    <div class="methodology-context">
      <p>应付职工薪酬（2211）为<strong>贷方/负债类</strong>科目（期末=期初+贷方-借方）。贷方检查对应<strong>计提/增加</strong>（检查凭证+薪酬计算表/审批单）；借方检查对应<strong>发放/减少</strong>（付款审批单+银行回单+代扣代缴凭证）；期后支付检查用于验证资产负债表日应付未付薪酬的<strong>完整性</strong>（是否存在漏提）。核对要点：①原始凭证齐全 ②与记账凭证相符 ③计算正确（人数/比例/月份） ④审批手续完整 ⑤期间归属正确。</p>
    </div>

    <!-- 二、样本选取 -->
    <el-card shadow="never" class="section-card">
      <template #header><span class="card-title">二、样本选取标准与规模</span></template>
      <div class="criteria-grid">
        <div class="cg-item">
          <label>测试总体（贷方发生额）</label>
          <div class="cg-inline">
            <el-input-number v-model="criteria.populationCreditCount" :controls="false" :disabled="isReadonly" size="small" placeholder="笔数" class="num-sm" @change="persist" />
            <span class="cg-unit">笔</span>
            <el-input-number v-model="criteria.populationCreditAmount" :controls="false" :disabled="isReadonly" size="small" placeholder="金额" class="num-md" @change="persist" />
            <span class="cg-unit">元</span>
          </div>
        </div>
        <div class="cg-item">
          <label>测试总体（借方发生额）</label>
          <div class="cg-inline">
            <el-input-number v-model="criteria.populationDebitCount" :controls="false" :disabled="isReadonly" size="small" placeholder="笔数" class="num-sm" @change="persist" />
            <span class="cg-unit">笔</span>
            <el-input-number v-model="criteria.populationDebitAmount" :controls="false" :disabled="isReadonly" size="small" placeholder="金额" class="num-md" @change="persist" />
            <span class="cg-unit">元</span>
          </div>
        </div>
        <div class="cg-item cg-full">
          <label>特定样本</label>
          <el-input v-model="criteria.specificSample" :disabled="isReadonly" size="small"
            placeholder="大额单笔计提（XX万以上）、关联方代付、非常规薪酬项目全部测试" @change="persist" />
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
            placeholder="使用IDEA选取XX笔贷方计提+XX笔借方发放进行检查" @change="persist" />
        </div>
      </div>
    </el-card>

    <!-- 三、测试 — 贷方检查（计提/增加） -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="card-header-row">
          <span class="card-title">三-A、贷方检查（计提/增加）</span>
          <div>
            <el-button v-if="!isReadonly" size="small" type="primary" plain @click="openSampling('credit')"><el-icon><MagicStick /></el-icon> 抽凭(贷方)</el-button>
            <el-button v-if="!isReadonly" size="small" @click="addOccurrenceRow(); persist()">＋ 新增</el-button>
          </div>
        </div>
      </template>
      <el-table :data="occurrenceRows" border size="small" :max-height="400" class="voucher-table" :row-class-name="abnormalRowClass">
        <el-table-column label="#" type="index" width="42" align="center" />
        <el-table-column v-if="isColVisible('debtorName')" label="薪酬项目" min-width="120">
          <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.debtorName" size="small" @change="persist" /><span v-else>{{ row.debtorName || '-' }}</span></template>
        </el-table-column>
        <el-table-column v-if="isColVisible('date')" label="日期" width="110">
          <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.date" size="small" placeholder="YYYY-MM-DD" @change="persist" /><span v-else>{{ row.date || '-' }}</span></template>
        </el-table-column>
        <el-table-column v-if="isColVisible('voucherNo')" label="凭证编号" width="110">
          <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.voucherNo" size="small" @change="persist" /><span v-else>{{ row.voucherNo || '-' }}</span></template>
        </el-table-column>
        <el-table-column v-if="isColVisible('businessContent')" label="业务内容/摘要" min-width="140">
          <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.businessContent" size="small" @change="persist" /><span v-else>{{ row.businessContent || '-' }}</span></template>
        </el-table-column>
        <el-table-column v-if="isColVisible('offsetAccount')" label="对方科目" min-width="110">
          <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.offsetAccount" size="small" @change="persist" /><span v-else>{{ row.offsetAccount || '-' }}</span></template>
        </el-table-column>
        <el-table-column v-if="isColVisible('creditAmount')" label="贷方金额" width="120" align="right">
          <template #default="{ row }"><el-input-number v-if="!isReadonly" v-model="row.creditAmount" :controls="false" size="small" class="amount-input" @change="persist" /><span v-else class="amount-cell">{{ fmtAmt(row.creditAmount) }}</span></template>
        </el-table-column>
        <el-table-column v-if="isColVisible('checks')" label="核对内容" width="170" align="center">
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
        <el-table-column v-if="isColVisible('abnormal')" label="异常" width="70" align="center">
          <template #default="{ row }"><el-switch v-model="row.abnormal" :disabled="isReadonly" size="small" @change="persist" /></template>
        </el-table-column>
        <el-table-column v-if="isColVisible('remark')" label="备注" min-width="110">
          <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.remark" size="small" @change="persist" /><span v-else>{{ row.remark || '-' }}</span></template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="操作" width="56" align="center" fixed="right">
          <template #default="{ row }"><el-button size="small" type="danger" link @click="removeOccurrenceRow(row.id); persist()">删除</el-button></template>
        </el-table-column>
        <template #append><div class="table-total">贷方合计：{{ fmtAmt(occurrenceCreditChecked) }}</div></template>
      </el-table>
    </el-card>

    <!-- 三-B、借方检查（发放/减少） -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="card-header-row">
          <span class="card-title">三-B、借方检查（发放/减少）</span>
          <div>
            <el-button v-if="!isReadonly" size="small" type="primary" plain @click="openSampling('debit')"><el-icon><MagicStick /></el-icon> 抽凭(借方)</el-button>
            <el-button v-if="!isReadonly" size="small" @click="addPostCollectionRow(); persist()">＋ 新增</el-button>
          </div>
        </div>
      </template>
      <el-table :data="postCollectionRows" border size="small" :max-height="400" class="voucher-table" :row-class-name="abnormalRowClass">
        <el-table-column label="#" type="index" width="42" align="center" />
        <el-table-column v-if="isColVisible('debtorName')" label="薪酬项目" min-width="120">
          <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.debtorName" size="small" @change="persist" /><span v-else>{{ row.debtorName || '-' }}</span></template>
        </el-table-column>
        <el-table-column v-if="isColVisible('date')" label="日期" width="110">
          <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.date" size="small" placeholder="YYYY-MM-DD" @change="persist" /><span v-else>{{ row.date || '-' }}</span></template>
        </el-table-column>
        <el-table-column v-if="isColVisible('voucherNo')" label="凭证编号" width="110">
          <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.voucherNo" size="small" @change="persist" /><span v-else>{{ row.voucherNo || '-' }}</span></template>
        </el-table-column>
        <el-table-column v-if="isColVisible('businessContent')" label="业务内容/摘要" min-width="140">
          <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.businessContent" size="small" @change="persist" /><span v-else>{{ row.businessContent || '-' }}</span></template>
        </el-table-column>
        <el-table-column v-if="isColVisible('offsetAccount')" label="对方科目" min-width="110">
          <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.offsetAccount" size="small" @change="persist" /><span v-else>{{ row.offsetAccount || '-' }}</span></template>
        </el-table-column>
        <el-table-column v-if="isColVisible('debitAmount')" label="借方金额" width="120" align="right">
          <template #default="{ row }"><el-input-number v-if="!isReadonly" v-model="row.debitAmount" :controls="false" size="small" class="amount-input" @change="persist" /><span v-else class="amount-cell">{{ fmtAmt(row.debitAmount) }}</span></template>
        </el-table-column>
        <el-table-column v-if="isColVisible('checks')" label="核对内容" width="170" align="center">
          <template #header>
            <el-tooltip placement="top">
              <template #content><div v-for="(lbl, i) in debitCheckLabels" :key="i">{{ i + 1 }}. {{ lbl }}</div></template>
              <span class="col-help">核对内容 ⓘ</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <el-checkbox-group :model-value="checkedValues(row)" :disabled="isReadonly" class="check-group" @update:model-value="(v: any) => setChecks(row, v as number[])">
              <el-checkbox v-for="(lbl, i) in debitCheckLabels" :key="i" :value="i" :label="i + 1" />
            </el-checkbox-group>
          </template>
        </el-table-column>
        <el-table-column v-if="isColVisible('abnormal')" label="异常" width="70" align="center">
          <template #default="{ row }"><el-switch v-model="row.abnormal" :disabled="isReadonly" size="small" @change="persist" /></template>
        </el-table-column>
        <el-table-column v-if="isColVisible('remark')" label="备注" min-width="110">
          <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.remark" size="small" @change="persist" /><span v-else>{{ row.remark || '-' }}</span></template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="操作" width="56" align="center" fixed="right">
          <template #default="{ row }"><el-button size="small" type="danger" link @click="removePostCollectionRow(row.id); persist()">删除</el-button></template>
        </el-table-column>
        <template #append><div class="table-total">借方合计：{{ fmtAmt(postDebitChecked) }}</div></template>
      </el-table>
    </el-card>

    <!-- 三-C、期后支付检查 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="card-header-row">
          <span class="card-title">三-C、期后支付检查（完整性验证）</span>
          <el-button v-if="!isReadonly" size="small" @click="addPostPeriodRow(); persist()">＋ 新增</el-button>
        </div>
      </template>
      <el-table :data="postPeriodRows" border size="small" :max-height="260" class="voucher-table">
        <el-table-column label="#" type="index" width="42" align="center" />
        <el-table-column label="支付日期" width="120">
          <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.date" size="small" @change="persist" /><span v-else>{{ row.date || '-' }}</span></template>
        </el-table-column>
        <el-table-column label="凭证编号" width="110">
          <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.voucherNo" size="small" @change="persist" /><span v-else>{{ row.voucherNo || '-' }}</span></template>
        </el-table-column>
        <el-table-column label="薪酬项目/摘要" min-width="150">
          <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.debtorName" size="small" @change="persist" /><span v-else>{{ row.debtorName || '-' }}</span></template>
        </el-table-column>
        <el-table-column label="支付金额" width="130" align="right">
          <template #default="{ row }"><el-input-number v-if="!isReadonly" v-model="row.debitAmount" :controls="false" size="small" class="amount-input" @change="persist" /><span v-else class="amount-cell">{{ fmtAmt(row.debitAmount) }}</span></template>
        </el-table-column>
        <el-table-column label="归属期间" width="130">
          <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.businessContent" size="small" placeholder="如2025年12月" @change="persist" /><span v-else>{{ row.businessContent || '-' }}</span></template>
        </el-table-column>
        <el-table-column label="是否应计提" width="100" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.remark" size="small" placeholder="—" @change="persist">
              <el-option label="是(漏提)" value="是" /><el-option label="否" value="否" /><el-option label="待定" value="待定" />
            </el-select>
            <span v-else>{{ row.remark || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="操作" width="56" align="center">
          <template #default="{ row }"><el-button size="small" type="danger" link @click="removePostPeriodRow(row.id); persist()">删除</el-button></template>
        </el-table-column>
        <template #append><div class="table-total">期后支付合计：{{ fmtAmt(postPeriodTotal) }}</div></template>
      </el-table>
    </el-card>

    <!-- 四、审计说明 — 检查比例 -->
    <el-card shadow="never" class="section-card">
      <template #header><span class="card-title">四、审计说明 — 检查比例</span></template>
      <el-table :data="j1CheckRatios" border size="small" class="ratio-table">
        <el-table-column label="方向" prop="direction" width="140" />
        <el-table-column label="本期发生额" align="right"><template #default="{ row }"><span class="amount-cell">{{ fmtAmt(row.bookAmount) }}</span></template></el-table-column>
        <el-table-column label="检查金额" align="right"><template #default="{ row }"><span class="amount-cell">{{ fmtAmt(row.checkedAmount) }}</span></template></el-table-column>
        <el-table-column label="检查比例" width="130" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.ratio != null" :type="row.ratio < 0.3 ? 'danger' : row.ratio < 0.6 ? 'warning' : 'success'" size="small" effect="plain">{{ (row.ratio * 100).toFixed(1) }}%</el-tag>
            <span v-else class="muted">—</span>
          </template>
        </el-table-column>
      </el-table>
      <el-alert v-if="lowRatioWarnings.length > 0" type="warning" :closable="false" show-icon class="ratio-warn">
        <template #title>检查比例偏低（&lt;30%），应扩大检查样本量或说明原因</template>
      </el-alert>
      <div class="note-block">
        <label>审计说明</label>
        <el-input v-model="auditNote" type="textarea" :autosize="{ minRows: 3 }" :disabled="isReadonly" placeholder="说明检查过程/发现/比例合理性..." @change="persist" />
      </div>
    </el-card>

    <!-- 异常摘要 -->
    <div v-if="abnormalRows.length > 0" class="abnormal-summary">
      <div class="as-header">⚠️ 异常凭证摘要（{{ abnormalRows.length }} 笔）</div>
      <ul class="as-list">
        <li v-for="r in abnormalRows" :key="r.id"><b>{{ r.debtorName || '（未填）' }}</b> — 凭证 {{ r.voucherNo || '-' }}：{{ r.remark || '未说明' }}</li>
      </ul>
    </div>

    <!-- 五、审计结论 -->
    <el-card shadow="never" class="conclusion-card">
      <template #header><span class="card-title">五、审计结论</span></template>
      <el-select v-model="conclusionOption" :disabled="isReadonly" size="small" class="concl-select" placeholder="选择结论模板" @change="onConclusionOption">
        <el-option label="A、未见异常" value="A" />
        <el-option label="B、除上述重大不符事项作为调整事项予以调整外，其余未见异常" value="B" />
        <el-option label="C、由于存在重大未调整事项（或审计范围受限），不可确认" value="C" />
      </el-select>
      <el-input v-model="conclusion" type="textarea" :autosize="{ minRows: 2 }" :disabled="isReadonly" placeholder="基于上述检查情况，形成综合审计结论..." @change="persist" />
    </el-card>

    <!-- 编制提示 -->
    <details class="compile-hint">
      <summary>编制提示（CAS 9 职工薪酬 + 审计准则）</summary>
      <ul>
        <li>科目 2211 应付职工薪酬（贷方/负债类），期末=期初+贷方-借方</li>
        <li>贷方检查=计提/增加（工资/社保/公积金/福利/工会经费），核对薪酬计算表+审批</li>
        <li>借方检查=发放/减少（银行转账/现金/代扣代缴），核对付款审批+银行回单+个税代扣</li>
        <li>核对内容：①原始凭证齐全 ②与记账凭证相符 ③计算正确 ④审批手续完整 ⑤期间归属正确</li>
        <li>期后支付检查：资产负债表日后支付的薪酬中属于报告期应计未计部分→漏提</li>
        <li>重点关注：年终奖跨期计提/社保基数调整/高管薪酬/辞退福利确认</li>
      </ul>
    </details>

    <!-- 抽凭引擎 -->
    <el-dialog v-model="samplingVisible" title="抽凭引擎 — 应付职工薪酬(2211)" width="90%" top="5vh" destroy-on-close>
      <GtVoucherSamplingEngine v-if="samplingVisible" account-code="2211" :phase="samplingPhase" :workpaper-id="props.wpId" :project-id="props.projectId" :year="yearNum" @filled="onSamplesFilled" />
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
/**
 * J1TabGeneralCheck — J1-8 应付职工薪酬凭证级检查表
 * 科目 2211（贷方/负债类）。三区：贷方+借方+期后。
 * 复用 useK1VoucherCheck composable。
 * 自持久化模式（J1 composable-internal persist pattern）。
 */
import { ref, reactive, computed, onMounted, defineAsyncComponent } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'
import { http } from '@/utils/http'
import { useK1VoucherCheck, type K1VoucherRow } from '../../composables/useK1VoucherCheck'

const GtVoucherSamplingEngine = defineAsyncComponent(() => import('../../voucher-sampling/GtVoucherSamplingEngine.vue'))

const props = defineProps<{
  wpId: string
  projectId: string
  htmlData?: Record<string, unknown> | null
}>()

const isReadonly = computed(() => false)
const yearNum = computed(() => {
  const d = props.htmlData as any
  return d?.year ?? new Date().getFullYear()
})

// ─── 本地 allResponses Map（自持久化，不依赖父级传递） ─────────────────────
const localAllResponses = ref(new Map<string, any>())
const allResponsesRef = computed(() => localAllResponses.value)

const ITEM_ID = 'J1-8-voucher-check'

const {
  itemId, checkLabels,
  criteria, occurrenceRows, postCollectionRows, auditNote, conclusion, conclusionOption,
  checkRatios, lowRatioWarnings, abnormalRows,
  occurrenceCreditChecked, occurrenceDebitChecked,
  load, addOccurrenceRow, removeOccurrenceRow,
  addPostCollectionRow, removePostCollectionRow,
  fillFromSamples, serialize,
} = useK1VoucherCheck({ allResponses: allResponsesRef as any, itemId: ITEM_ID })

// 借方检查的核对内容标签（发放）
const debitCheckLabels = [
  '付款审批单齐全',
  '银行回单/转账凭证',
  '代扣代缴凭证（个税/社保/公积金）',
  '与薪酬发放表相符',
  '发放金额与审批一致',
]

// 检查比例保留贷方+借方两行
const j1CheckRatios = computed(() => checkRatios.value)

// 期后支付区（独立管理）
const postPeriodRows = ref<K1VoucherRow[]>([])
const postPeriodTotal = computed(() => postPeriodRows.value.reduce((s, r) => s + (r.debitAmount || 0), 0))
const postDebitChecked = computed(() => postCollectionRows.value.reduce((s, r) => s + (r.debitAmount || 0), 0))

function addPostPeriodRow() {
  postPeriodRows.value.push({
    id: `pp-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
    debtorName: '', date: '', voucherNo: '', businessContent: '',
    offsetAccount: '', offsetSubAccount: '',
    creditAmount: 0, debitAmount: 0,
    supportingDoc: '',
    checks: [false, false, false, false, false],
    abnormal: false, indexNo: '', remark: '',
  })
}
function removePostPeriodRow(id: string) {
  postPeriodRows.value = postPeriodRows.value.filter(r => r.id !== id)
}

// ─── selfLoad 从 checklist-responses 恢复 ────────────────────────────────────
onMounted(async () => {
  try {
    const res = await http.get(`/api/workpapers/${props.wpId}/checklist-responses`)
    const items: Array<{ item_id: string; remark?: string; conclusion?: string }> = res.data?.data || res.data || []
    for (const item of items) {
      if (item.item_id === ITEM_ID) {
        localAllResponses.value.set(ITEM_ID, { item_id: ITEM_ID, remark: item.remark, conclusion: item.conclusion })
      }
      if (item.item_id === 'J1-8-post-period') {
        try { postPeriodRows.value = JSON.parse(item.remark || '[]') } catch { /* */ }
      }
    }
    load()
  } catch (e) {
    console.warn('[J1-8] selfLoad failed:', e)
  }
})

// ─── 列设置 ─────────────────────────────────────────────────────────────────
const COL_PREFS_KEY = 'j1-8-column-prefs'
interface ColDef { key: string; label: string; visible: boolean }
const columnDefs = reactive<ColDef[]>([
  { key: 'debtorName', label: '薪酬项目', visible: true },
  { key: 'date', label: '日期', visible: true },
  { key: 'voucherNo', label: '凭证编号', visible: true },
  { key: 'businessContent', label: '业务内容', visible: true },
  { key: 'offsetAccount', label: '对方科目', visible: true },
  { key: 'creditAmount', label: '贷方金额', visible: true },
  { key: 'debitAmount', label: '借方金额', visible: true },
  { key: 'checks', label: '核对内容', visible: true },
  { key: 'abnormal', label: '异常', visible: true },
  { key: 'remark', label: '备注', visible: true },
])
function isColVisible(key: string): boolean { return columnDefs.find(c => c.key === key)?.visible ?? true }
function persistColumnPrefs(): void {
  try { localStorage.setItem(COL_PREFS_KEY, JSON.stringify(columnDefs.map(c => ({ key: c.key, visible: c.visible })))) } catch { /* */ }
}
function loadColumnPrefs(): void {
  try {
    const saved = localStorage.getItem(COL_PREFS_KEY)
    if (!saved) return
    const prefs: Array<{ key: string; visible: boolean }> = JSON.parse(saved)
    for (const p of prefs) { const col = columnDefs.find(c => c.key === p.key); if (col) col.visible = p.visible }
  } catch { /* */ }
}
function resetColumnPrefs(): void {
  for (const col of columnDefs) col.visible = true
  persistColumnPrefs()
}
loadColumnPrefs()

// ─── Persistence（J1 自持久化模式） ──────────────────────────────────────────
let persistTimer: ReturnType<typeof setTimeout> | null = null
function persist() {
  if (persistTimer) clearTimeout(persistTimer)
  persistTimer = setTimeout(doPersist, 800)
}

async function doPersist() {
  try {
    const data = serialize()
    localAllResponses.value.set(ITEM_ID, { item_id: ITEM_ID, remark: data, conclusion: null })
    const items = [
      { item_id: ITEM_ID, remark: data, conclusion: conclusion.value || null },
      { item_id: 'J1-8-post-period', remark: JSON.stringify(postPeriodRows.value), conclusion: null },
    ]
    await http.put(`/api/workpapers/${props.wpId}/checklist-responses`, { items })
  } catch (e) {
    console.warn('[J1-8] persist failed:', e)
  }
}

// ─── Handlers ────────────────────────────────────────────────────────────────
function checkedValues(row: K1VoucherRow): number[] {
  return row.checks.map((c, i) => (c ? i : -1)).filter(i => i >= 0)
}
function setChecks(row: K1VoucherRow, vals: number[]): void {
  row.checks = Array.from({ length: 5 }, (_, i) => vals.includes(i))
  persist()
}

const samplingVisible = ref(false)
const samplingPhase = ref<'current' | 'post'>('current')
function openSampling(direction: 'credit' | 'debit') {
  samplingPhase.value = direction === 'credit' ? 'current' : 'post'
  samplingVisible.value = true
}
function onSamplesFilled(payload: { samples: any[] }) {
  const target = samplingPhase.value === 'current' ? 'occurrence' : 'post'
  fillFromSamples(target, payload?.samples ?? [])
  samplingVisible.value = false
  persist()
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

async function handleAiGenerate() {
  try {
    await http.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section: 'voucher-check',
      prompt: '请基于已检查的薪酬凭证情况，生成审计说明',
      context: { itemId: ITEM_ID, occurrenceCount: occurrenceRows.value.length, postCount: postCollectionRows.value.length },
    })
  } catch { /* */ }
}
function handleReview() { /* 复核对话暂桩 */ }
</script>

<style scoped>
.j1-general-check { padding: 12px 14px; font-size: var(--wp-font-size, 13px); }
.guide-banner { display: grid; grid-template-columns: repeat(4, 1fr); gap: 6px; background: linear-gradient(135deg, #eef4ff 0%, #e0ecff 100%); border: 1px solid #c6dbff; border-radius: 6px; padding: 7px 12px; margin-bottom: 10px; }
.guide-step { display: flex; align-items: center; gap: 6px; font-size: 12px; color: #1e40af; }
.gs-no { display: inline-flex; align-items: center; justify-content: center; width: 18px; height: 18px; border-radius: 50%; background: #2563eb; color: #fff; font-size: 11px; font-weight: 600; flex-shrink: 0; }
.section-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; }
.sheet-title { font-size: 15px; font-weight: 600; margin: 0; }
.head-actions { display: flex; gap: 8px; align-items: center; }
.col-prefs { max-height: 320px; overflow-y: auto; }
.col-prefs-title { font-weight: 600; margin-bottom: 8px; font-size: 13px; }
.col-prefs :deep(.el-checkbox) { display: block; margin-bottom: 4px; }
.audit-objective { margin-bottom: 10px; }
.audit-objective :deep(.el-alert__content) { padding: 2px 0; }
.ao-title { font-weight: 600; }
.ao-list { margin: 4px 0 0; padding-left: 18px; line-height: 1.55; font-size: 12px; }
.methodology-context { background: #fffbeb; border-left: 4px solid #f59e0b; padding: 10px 14px; margin-bottom: 12px; border-radius: 4px; font-size: var(--wp-font-size, 13px); color: #78350f; line-height: 1.6; }
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
