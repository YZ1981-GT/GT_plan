<!--
  G5TabVoucherCheck.vue — G5-12 长期应收款凭证检查表

  对齐致同源模板「凭证检查表G5-12」：
    一、测试目标（存在/权利义务/计价分摊）
    二、样本选取方法与规模
    三、测试（1.本期发生额 2.期后处置、新增 + 五项核对 + 抽凭）
    四、审计说明（检查比例，除零安全）
    五、审计结论（A/B/C）
    编制说明：选取方法结构化折叠（全部/特定/抽样 + 扩体系数表）
-->
<template>
  <div class="g5-voucher-check">
    <div class="guide-banner">
      <div class="guide-step"><span class="gs-no">1</span>确认测试目标（三认定）</div>
      <div class="guide-step"><span class="gs-no">2</span>填写样本选取方法与规模</div>
      <div class="guide-step"><span class="gs-no">3</span>抽凭执行本期/期后检查</div>
      <div class="guide-step"><span class="gs-no">4</span>核对检查比例，形成结论</div>
    </div>

    <div class="section-head">
      <h3 class="sheet-title">G5-12 凭证检查表</h3>
      <div class="head-actions tab-toolbar">
        <GtIndexChip value="wp:G5-12" />
        <el-tag size="small" type="info">本期 {{ occurrenceRows.length }} · 期后 {{ postPeriodRows.length }}</el-tag>
        <el-tag v-if="abnormalRows.length" size="small" type="danger">异常 {{ abnormalRows.length }}</el-tag>
        <GtReviewTrigger section-id="g5-12-voucher-check" />
        <G5ImportExportDropdown :wp-id="props.wpId" sheet="G5-12" :disabled="!!props.readonly" @imported="onImported" />
      </div>
    </div>

    <!-- 一、测试目标 -->
    <el-alert type="info" :closable="false" class="audit-objective" show-icon>
      <template #title><span class="ao-title">一、测试目标（认定）</span></template>
      <ol class="ao-list">
        <li><b>存在：</b>资产负债表中记录的长期应收款是存在的，且已经记录在恰当的账户中；</li>
        <li><b>权利和义务：</b>记录的长期应收款由被审计单位拥有或控制；</li>
        <li><b>计价和分摊：</b>长期应收款以恰当的金额包括在财务报表中，与之相关的计价或分摊调整已恰当记录，相关披露已得到恰当计量和描述。</li>
      </ol>
    </el-alert>

    <!-- 二、样本选取 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="card-header-row">
          <span class="card-title">二、样本选取方法与规模</span>
          <div class="hdr-btns">
            <el-button v-if="!isReadonly" size="small" type="primary" plain @click="importFromG52">从 G5-2 带入发生额</el-button>
            <el-button size="small" link type="primary" @click="showSamplingGuide = true">抽样方法说明</el-button>
          </div>
        </div>
      </template>
      <div class="criteria-grid">
        <div class="cg-item">
          <label>测试总体（借方发生额）</label>
          <div class="cg-inline">
            <el-input-number v-model="criteria.populationDebitCount" :controls="false" :disabled="isReadonly"
              size="small" placeholder="笔数" class="num-sm" @change="persist" />
            <span class="cg-unit">笔</span>
            <el-input-number v-model="criteria.populationDebitAmount" :controls="false" :disabled="isReadonly"
              size="small" placeholder="金额" class="num-md" @change="persist" />
            <span class="cg-unit">元</span>
          </div>
        </div>
        <div class="cg-item">
          <label>测试总体（贷方发生额）</label>
          <div class="cg-inline">
            <el-input-number v-model="criteria.populationCreditCount" :controls="false" :disabled="isReadonly"
              size="small" placeholder="笔数" class="num-sm" @change="persist" />
            <span class="cg-unit">笔</span>
            <el-input-number v-model="criteria.populationCreditAmount" :controls="false" :disabled="isReadonly"
              size="small" placeholder="金额" class="num-md" @change="persist" />
            <span class="cg-unit">元</span>
          </div>
        </div>
        <div class="cg-item cg-full">
          <label>特定样本（全部测试项）</label>
          <el-input v-model="criteria.specificSample" :disabled="isReadonly" size="small"
            placeholder="XX金额以上（大额）、关联方/关联交易、异常款项全部测试，共XX笔"
            @change="persist" />
        </div>
        <div class="cg-item">
          <label>抽样总体（测试总体 − 特定样本）</label>
          <div class="cg-inline">
            <el-input-number v-model="criteria.samplingPopulationCount" :controls="false" :disabled="isReadonly"
              size="small" placeholder="笔数" class="num-sm" @change="persist" />
            <span class="cg-unit">笔</span>
            <el-input-number v-model="criteria.samplingPopulationAmount" :controls="false" :disabled="isReadonly"
              size="small" placeholder="金额" class="num-md" @change="persist" />
            <span class="cg-unit">元</span>
          </div>
        </div>
        <div class="cg-item">
          <label>确定的抽样样本量</label>
          <div class="cg-inline">
            <el-input-number v-model="criteria.sampleSize" :controls="false" :disabled="isReadonly"
              size="small" placeholder="样本量" class="num-sm" @change="persist" />
            <span class="cg-unit">笔</span>
          </div>
        </div>
        <div class="cg-item">
          <label>抽样方法</label>
          <el-select v-model="criteria.samplingMethod" :disabled="isReadonly" size="small" @change="persist">
            <el-option label="随机选样" value="随机选样" />
            <el-option label="系统选样" value="系统选样" />
            <el-option label="货币单元抽样（MUS）" value="货币单元抽样" />
            <el-option label="随意选样（非统计抽样）" value="随意选样" />
          </el-select>
        </div>
        <div class="cg-item">
          <label>账面本期借方（检查比例分母，可勾 G5-2）</label>
          <el-input-number v-model="criteria.bookDebitOccurrence" :controls="false" :disabled="isReadonly"
            size="small" class="num-md" @change="persist" />
        </div>
        <div class="cg-item">
          <label>账面本期贷方（检查比例分母，可勾 G5-2）</label>
          <el-input-number v-model="criteria.bookCreditOccurrence" :controls="false" :disabled="isReadonly"
            size="small" class="num-md" @change="persist" />
        </div>
        <div class="cg-item cg-full">
          <label>抽样过程</label>
          <el-input v-model="criteria.samplingProcess" type="textarea" :autosize="{ minRows: 2 }"
            :disabled="isReadonly" size="small"
            placeholder="使用IDEA（或平台抽凭引擎）选择XX笔、金额占比XX%的样本；选样过程与结果见相关底稿"
            @change="persist" />
        </div>
      </div>
      <el-alert type="warning" :closable="false" show-icon class="criteria-tip">
        选取路径：全部项目 → 特定项目 → 审计抽样。特定项目≠审计抽样；MUS 常用于测试存在/高估，大额项目效率更高。详见「抽样方法说明」。
      </el-alert>
    </el-card>

    <!-- 三、测试 — 本期 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="card-header-row">
          <span class="card-title">三、测试 — 1. 本期发生额检查</span>
          <div class="hdr-btns">
            <el-tag size="small" type="info" class="check-legend" effect="plain">
              核对：1完整 2批准 3账务 4初始成本 5对手一致
            </el-tag>
            <el-button v-if="!isReadonly" size="small" type="primary" plain @click="openSampling('occurrence')">抽凭</el-button>
            <el-button v-if="!isReadonly" size="small" @click="addOccurrenceRow(); persist()">＋ 手工新增</el-button>
          </div>
        </div>
      </template>
      <p class="check-desc">测试内容：{{ checkLabels.map((l, i) => `${i + 1}.${l}`).join('；') }}</p>
      <el-table :data="occurrenceRows" border size="small" :max-height="380" class="voucher-table"
        :row-class-name="abnormalRowClass">
        <el-table-column label="#" type="index" width="42" align="center" fixed />
        <el-table-column label="日期" width="118">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.date" size="small" placeholder="YYYY-MM-DD" @change="persist" />
            <span v-else>{{ row.date || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="凭证编号" width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.voucherNo" size="small" @change="persist" />
            <span v-else>{{ row.voucherNo || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="业务内容" min-width="140">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.businessContent" size="small" @change="persist" />
            <span v-else>{{ row.businessContent || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="对方科目" width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.offsetAccount" size="small" @change="persist" />
            <span v-else>{{ row.offsetAccount || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="对方明细" width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.offsetSubAccount" size="small" @change="persist" />
            <span v-else>{{ row.offsetSubAccount || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="借方金额" width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.debitAmount" :controls="false" size="small"
              class="amount-input" @change="persist" />
            <span v-else class="amount-cell">{{ fmtAmt(row.debitAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="贷方金额" width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.creditAmount" :controls="false" size="small"
              class="amount-input" @change="persist" />
            <span v-else class="amount-cell">{{ fmtAmt(row.creditAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="支持性文件" min-width="110">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.supportingDoc" size="small" @change="persist" />
            <span v-else>{{ row.supportingDoc || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="核对内容" width="168" align="center">
          <template #header>
            <el-tooltip placement="top">
              <template #content>
                <div v-for="(lbl, i) in checkLabels" :key="i">{{ i + 1 }}. {{ lbl }}</div>
              </template>
              <span class="col-help">核对内容 ⓘ</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <el-checkbox-group :model-value="checkedValues(row)" :disabled="isReadonly" class="check-group"
              @update:model-value="(v: any) => setChecks(row, v as number[])">
              <el-checkbox v-for="(_, i) in checkLabels" :key="i" :value="i" :label="i + 1" />
            </el-checkbox-group>
          </template>
        </el-table-column>
        <el-table-column label="索引号" width="80">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.indexNo" size="small" @change="persist" />
            <span v-else>{{ row.indexNo || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="异常" width="64" align="center">
          <template #default="{ row }">
            <el-switch v-model="row.abnormal" :disabled="isReadonly" size="small" @change="persist" />
          </template>
        </el-table-column>
        <el-table-column label="备注" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.remark" size="small" @change="persist" />
            <span v-else>{{ row.remark || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="操作" width="56" align="center" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="danger" link @click="removeOccurrenceRow(row.id); persist()">删</el-button>
          </template>
        </el-table-column>
        <template #append>
          <div class="table-total">
            合计　借方：{{ fmtAmt(occurrenceDebitChecked) }}　贷方：{{ fmtAmt(occurrenceCreditChecked) }}
          </div>
        </template>
      </el-table>
    </el-card>

    <!-- 三、测试 — 期后 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="card-header-row">
          <span class="card-title">三、测试 — 2. 期后处置、新增检查</span>
          <div class="hdr-btns">
            <el-button v-if="!isReadonly" size="small" type="primary" plain @click="openSampling('post')">抽凭</el-button>
            <el-button v-if="!isReadonly" size="small" @click="addPostPeriodRow(); persist()">＋ 手工新增</el-button>
          </div>
        </div>
      </template>
      <el-table :data="postPeriodRows" border size="small" :max-height="300" class="voucher-table"
        :row-class-name="abnormalRowClass">
        <el-table-column label="#" type="index" width="42" align="center" fixed />
        <el-table-column label="日期" width="118">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.date" size="small" placeholder="YYYY-MM-DD" @change="persist" />
            <span v-else>{{ row.date || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="凭证编号" width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.voucherNo" size="small" @change="persist" />
            <span v-else>{{ row.voucherNo || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="业务内容" min-width="140">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.businessContent" size="small" @change="persist" />
            <span v-else>{{ row.businessContent || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="对方科目" width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.offsetAccount" size="small" @change="persist" />
            <span v-else>{{ row.offsetAccount || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="借方金额" width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.debitAmount" :controls="false" size="small"
              class="amount-input" @change="persist" />
            <span v-else class="amount-cell">{{ fmtAmt(row.debitAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="贷方金额" width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.creditAmount" :controls="false" size="small"
              class="amount-input" @change="persist" />
            <span v-else class="amount-cell">{{ fmtAmt(row.creditAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="核对内容" width="168" align="center">
          <template #default="{ row }">
            <el-checkbox-group :model-value="checkedValues(row)" :disabled="isReadonly" class="check-group"
              @update:model-value="(v: any) => setChecks(row, v as number[])">
              <el-checkbox v-for="(_, i) in checkLabels" :key="i" :value="i" :label="i + 1" />
            </el-checkbox-group>
          </template>
        </el-table-column>
        <el-table-column label="异常" width="64" align="center">
          <template #default="{ row }">
            <el-switch v-model="row.abnormal" :disabled="isReadonly" size="small" @change="persist" />
          </template>
        </el-table-column>
        <el-table-column label="备注" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.remark" size="small" @change="persist" />
            <span v-else>{{ row.remark || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="操作" width="56" align="center" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="danger" link @click="removePostPeriodRow(row.id); persist()">删</el-button>
          </template>
        </el-table-column>
        <template #append>
          <div class="table-total">
            合计　借方：{{ fmtAmt(postDebitChecked) }}　贷方：{{ fmtAmt(postCreditChecked) }}
          </div>
        </template>
      </el-table>
    </el-card>

    <!-- 四、审计说明 + 检查比例 -->
    <el-card shadow="never" class="section-card">
      <template #header><span class="card-title">四、审计说明 — 检查比例</span></template>
      <el-table :data="checkRatios" border size="small" class="ratio-table">
        <el-table-column label="方向" prop="direction" width="110" />
        <el-table-column label="账面金额" align="right">
          <template #default="{ row }">
            <span class="amount-cell">{{ row.bookAmount > 0 ? fmtAmt(row.bookAmount) : '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="检查金额" align="right">
          <template #default="{ row }"><span class="amount-cell">{{ fmtAmt(row.checkedAmount) }}</span></template>
        </el-table-column>
        <el-table-column label="检查比例" width="120" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.ratio != null" size="small" effect="plain"
              :type="row.ratio < 0.3 ? 'danger' : row.ratio < 0.6 ? 'warning' : 'success'">
              {{ (row.ratio * 100).toFixed(1) }}%
            </el-tag>
            <span v-else class="muted" title="分母为零时不显示比例（避免 #DIV/0!）">—</span>
          </template>
        </el-table-column>
      </el-table>
      <el-alert v-if="lowRatioWarnings.length" type="warning" :closable="false" show-icon class="ratio-warn">
        检查比例偏低（&lt;30%）：{{ lowRatioWarnings.map(r => r.direction).join('、') }}，应扩大样本量或在说明中解释原因。
      </el-alert>
      <div class="note-block">
        <label>审计说明</label>
        <el-input v-model="auditNote" type="textarea" :autosize="{ minRows: 3 }" :disabled="isReadonly"
          placeholder="概述：（1）程序测试情况与结果；（2）拟调整事项及分录、未调整事项及影响、审计范围受限情况。"
          @change="persist" />
      </div>
    </el-card>

    <div v-if="abnormalRows.length" class="abnormal-summary">
      <div class="as-header">
        异常凭证摘要（{{ abnormalRows.length }} 笔）
        <el-button v-if="!isReadonly" size="small" type="danger" plain class="push-btn" @click="pushAbnormalToG54">
          推送 G5-4
        </el-button>
      </div>
      <ul class="as-list">
        <li v-for="r in abnormalRows" :key="r.id">
          <b>{{ r.voucherNo || '（无凭证号）' }}</b>
          {{ r.businessContent || r.date || '' }} — {{ r.remark || '未说明' }}
        </li>
      </ul>
    </div>

    <!-- 五、审计结论 -->
    <el-card shadow="never" class="conclusion-card">
      <template #header><span class="card-title">五、审计结论</span></template>
      <el-select v-model="conclusionOption" :disabled="isReadonly" size="small" class="concl-select"
        placeholder="选择参考结论模板" @change="onConclusionOption">
        <el-option label="A、未见异常" value="A" />
        <el-option label="B、除上述重大不符事项作为调整事项予以调整外，其余未见异常" value="B" />
        <el-option label="C、由于存在重大未调整事项（或审计范围受限），不可确认" value="C" />
      </el-select>
      <el-input v-model="conclusion" type="textarea" :autosize="{ minRows: 2 }" :disabled="isReadonly"
        placeholder="基于上述检查形成综合审计结论…" @change="persist" />
    </el-card>

    <details class="compile-hint">
      <summary>编制提示（CAS 1231 / CAS 1314 · 科目 1531）</summary>
      <ul>
        <li>认定覆盖：存在、权利和义务、计价和分摊（与源模板测试目标一致）</li>
        <li>样本路径：测试总体扣除特定样本得抽样总体；大额/关联方/异常应全部测试后再抽样</li>
        <li>五项核对：原始凭证完整、授权批准、账务处理、初始成本、还款人与交易对手一致</li>
        <li>期后表覆盖截止日后处置与新增，支撑截止与存在认定</li>
        <li>检查比例 = 检查金额 ÷ 账面金额；账面为 0 时显示「—」而非 #DIV/0!；比例 &lt;30% 须扩样或说明</li>
        <li>异常项应追查并视情况计入 G5-4 调整分录汇总</li>
      </ul>
    </details>

    <!-- 抽凭 -->
    <el-dialog v-model="samplingVisible" title="抽凭引擎 — 长期应收款(1531)" width="90%" top="5vh" destroy-on-close>
      <GtVoucherSamplingEngine
        v-if="samplingVisible"
        :account-code="G5_ACCOUNT_CODE"
        :phase="samplingTarget === 'occurrence' ? 'current' : 'post'"
        :workpaper-id="props.wpId"
        :project-id="props.projectId"
        :year="auditYear"
        @filled="onSamplesFilled"
      />
    </el-dialog>

    <!-- 抽样方法说明（结构化，对应源模板 R52–99） -->
    <el-drawer v-model="showSamplingGuide" title="选取测试项目的方法（源模板编制说明）" size="480px">
      <div class="samp-guide">
        <section>
          <h4>1. 选取全部项目</h4>
          <p>下列情形应考虑 100% 测试：</p>
          <ul>
            <li>总体由少量大额项目构成；</li>
            <li>存在特别风险且其他方法未提供充分、适当证据；</li>
            <li>信息系统自动重复计算，全查符合成本效益。</li>
          </ul>
          <p class="muted-block">特别风险示例：舞弊；重大非常规交易（并购、债务重组、非货币交换等）；重大关联交易；重大判断/会计估计；重大复杂交易；高度自动化仅实质程序不足等。</p>
        </section>
        <section>
          <h4>2. 选取特定项目</h4>
          <ul>
            <li>大额或关键项目；超过某一金额的全部项目；</li>
            <li>为获取特定信息或测试控制活动而选取的项目。</li>
          </ul>
          <p class="warn-line">按判断选取特定项目易产生非抽样风险；特定项目检查≠审计抽样。</p>
        </section>
        <section>
          <h4>3. 审计抽样</h4>
          <p>对低于 100% 的项目实施程序，使每一抽样单元均有被选取机会。统计抽样须同时满足：随机选取 + 概率论评价（含计量抽样风险）。</p>
          <p>细节测试尤其高估时，以货币单位为抽样单元（MUS）通常效率高；可按金额分层，把资源投向大额。</p>
          <p class="formula">参考样本量 = 账面价值 × 风险系数 ÷（可容忍错报 − 预计错报 × 扩展系数）</p>
          <table class="exp-table">
            <thead><tr><th>误受风险</th><th>预计错报扩展系数</th></tr></thead>
            <tbody>
              <tr><td>1%</td><td>1.9</td></tr>
              <tr><td>5%</td><td>1.6</td></tr>
              <tr><td>10%</td><td>1.5</td></tr>
            </tbody>
          </table>
          <p>基本选样：随机数表/计算机辅助、系统选样、随意选样。平台抽凭引擎支持随机/系统/MUS/分层/特定。</p>
        </section>
      </div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, toRef, computed, onMounted, defineAsyncComponent } from 'vue'
import {
  useG5VoucherCheck,
  type G5VoucherRow,
} from '../../composables/useG5VoucherCheck'
import { G5_ACCOUNT_CODE } from '../../composables/g5Constants'
import { useInjectedG5FormData } from '../../composables/useG5LonRecFormData'
import { createEmptyEntry } from '../../composables/useG5Adjustment'
import { G5_ITEM_IDS, readCanonicalRaw } from '../../composables/g5StorageContract'
import { parseRowsRemark } from '../../composables/g5CrossHelpers'
import G5ImportExportDropdown from '../G5ImportExportDropdown.vue'
import GtIndexChip from '../../GtIndexChip.vue'
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import { ElMessage } from 'element-plus'

const GtVoucherSamplingEngine = defineAsyncComponent(
  () => import('../../voucher-sampling/GtVoucherSamplingEngine.vue'),
)

const props = defineProps<{
  htmlData?: any
  wpId: string
  projectId: string
  readonly?: boolean
}>()
const emit = defineEmits<{ imported: [] }>()

const isReadonly = computed(() => !!props.readonly)
const auditYear = computed(() => {
  const raw = props.htmlData?.project_context?.audit_year
    ?? props.htmlData?.projectContext?.audit_year
    ?? props.htmlData?.audit_year
  if (raw) return Number(raw) || new Date().getFullYear()
  return new Date().getFullYear()
})
const g5Notes = useInjectedG5FormData({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
})

const {
  itemId, checkLabels,
  criteria, occurrenceRows, postPeriodRows, auditNote, conclusion, conclusionOption,
  checkRatios, lowRatioWarnings, abnormalRows,
  occurrenceDebitChecked, occurrenceCreditChecked, postDebitChecked, postCreditChecked,
  loadFromMap, addOccurrenceRow, addPostPeriodRow, removeOccurrenceRow, removePostPeriodRow,
  fillFromSamples, applyConclusionTemplate, applyFromBalanceRows, buildAbnormalAdjDrafts, serialize,
} = useG5VoucherCheck({ allResponses: g5Notes.allResponses as any })

const G5_4_KEY = 'G5-4-rows'
const PUSH_MARK = '来自G5-12凭证检查'

const samplingVisible = ref(false)
const samplingTarget = ref<'occurrence' | 'post'>('occurrence')
const showSamplingGuide = ref(false)

onMounted(async () => {
  try { await g5Notes.loadAll() } catch { /* ignore */ }
  loadFromMap(g5Notes.allResponses.value)
})

function persist(): void {
  if (isReadonly.value) return
  const json = serialize()
  g5Notes.debouncedSave(itemId, { remark: json, conclusion: json })
  // 同步兼容旧 keys，避免他处读旧字段时报空
  g5Notes.debouncedSave('G5-12-audit-note', { remark: auditNote.value, conclusion: null })
  g5Notes.debouncedSave('G5-12-audit-conclusion', { remark: conclusion.value, conclusion: null })
}

async function onImported(): Promise<void> {
  try { await g5Notes.loadAll() } catch { /* ignore */ }
  loadFromMap(g5Notes.allResponses.value)
  emit('imported')
}

function checkedValues(row: G5VoucherRow): number[] {
  return row.checks.map((c, i) => (c ? i : -1)).filter((i) => i >= 0)
}
function setChecks(row: G5VoucherRow, vals: number[]): void {
  row.checks = checkLabels.map((_, i) => vals.includes(i))
  persist()
}

function openSampling(target: 'occurrence' | 'post'): void {
  samplingTarget.value = target
  samplingVisible.value = true
}
function onSamplesFilled(payload: { samples: any[] }): void {
  fillFromSamples(samplingTarget.value, payload?.samples ?? [])
  samplingVisible.value = false
  persist()
}

function onConclusionOption(val: string): void {
  applyConclusionTemplate(val)
  persist()
}

async function importFromG52(): Promise<void> {
  if (isReadonly.value) return
  try { await g5Notes.loadAll() } catch { /* ignore */ }
  const list = parseRowsRemark(g5Notes.allResponses.value.get(G5_ITEM_IDS.G5_2_ROWS))
  if (!list.length) {
    ElMessage.warning('未找到 G5-2 明细数据，请先在余额明细表录入')
    return
  }
  const result = applyFromBalanceRows(list)
  persist()
  if (!result.filled) {
    ElMessage.warning('G5-2 尚未填写借方/贷方发生额，请在 G5-2「债务人基础信息」中录入后再带入')
    return
  }
  const relatedTip = result.relatedCount ? `；关联方 ${result.relatedCount} 户已写入特定样本` : ''
  ElMessage.success(
    `已带入账面发生额：借方 ${fmtAmt(result.debit)} / 贷方 ${fmtAmt(result.credit)}${relatedTip}`,
  )
}

async function pushAbnormalToG54(): Promise<void> {
  if (isReadonly.value) return
  const drafts = buildAbnormalAdjDrafts()
  if (!drafts.length) {
    ElMessage.info('无异常凭证可推送')
    return
  }
  try { await g5Notes.loadAll() } catch { /* ignore */ }
  const existing = parseRowsRemark(g5Notes.allResponses.value.get(G5_4_KEY))
  const kept = existing.filter((e: any) => !String(e.remark || '').includes(PUSH_MARK))
  const added = drafts.map((d, i) => {
    const e = createEmptyEntry(kept.length + i + 1, d.description)
    e.accountCode = d.accountCode
    e.accountName = d.accountName
    e.reportItem = '长期应收款'
    e.debitAmount = d.debitAmount
    e.creditAmount = d.creditAmount
    e.indexRef = d.indexRef
    e.remark = d.remark
    e.category = '其他'
    e.entryType = 'AJE'
    return e
  })
  const next = [...kept, ...added]
  const json = JSON.stringify(next)
  await g5Notes.saveImmediate(G5_4_KEY, { remark: json, conclusion: json })
  try {
    window.dispatchEvent(new CustomEvent('g5:voucher-abnormal-pushed', {
      detail: { count: added.length },
    }))
  } catch { /* silent */ }
  ElMessage.success(`已向 G5-4 推送 ${added.length} 条异常备忘（金额待追查补录）`)
}

function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return Number(val).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
function abnormalRowClass({ row }: { row: G5VoucherRow }): string {
  return row.abnormal ? 'abnormal-row' : ''
}
</script>

<style scoped>
.g5-voucher-check { padding: 4px 2px 12px; font-size: var(--wp-font-size, 13px); }

.guide-banner {
  display: grid; grid-template-columns: repeat(4, 1fr); gap: 6px;
  background: linear-gradient(135deg, #eef4ff 0%, #e0ecff 100%);
  border: 1px solid #c6dbff; border-radius: 6px; padding: 7px 12px; margin-bottom: 10px;
}
.guide-step { display: flex; align-items: center; gap: 6px; font-size: 12px; color: #1e40af; }
.gs-no {
  display: inline-flex; align-items: center; justify-content: center;
  width: 18px; height: 18px; border-radius: 50%; background: #2563eb; color: #fff;
  font-size: 11px; font-weight: 600; flex-shrink: 0;
}

.section-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; gap: 8px; }
.sheet-title { font-size: 15px; font-weight: 600; margin: 0; }
.head-actions { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }

.audit-objective { margin-bottom: 10px; }
.ao-title { font-weight: 600; }
.ao-list { margin: 4px 0 0; padding-left: 18px; line-height: 1.55; font-size: 12px; }

.section-card { margin-bottom: 10px; }
.section-card :deep(.el-card__header) { padding: 8px 14px; }
.section-card :deep(.el-card__body) { padding: 12px 14px; }
.card-title { font-weight: 600; }
.card-header-row { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.hdr-btns { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.check-legend { font-size: 11px; }

.criteria-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px 18px; }
.cg-item { display: flex; flex-direction: column; gap: 4px; }
.cg-item.cg-full { grid-column: 1 / -1; }
.cg-item label { font-size: 12px; color: var(--el-text-color-secondary); }
.cg-inline { display: flex; align-items: center; gap: 5px; }
.cg-unit { font-size: 12px; color: var(--el-text-color-secondary); }
.num-sm { width: 78px; }
.num-md { width: 130px; }
.criteria-tip { margin-top: 10px; }

.check-desc { margin: 0 0 8px; font-size: 12px; color: var(--el-color-danger); line-height: 1.5; }
.voucher-table { font-size: var(--wp-font-size, 13px); }
.amount-cell { font-variant-numeric: tabular-nums; }
.amount-input { width: 100%; }
.col-help { cursor: help; border-bottom: 1px dashed var(--el-border-color); }
.check-group { display: flex; flex-wrap: wrap; gap: 0 2px; justify-content: center; }
.check-group :deep(.el-checkbox) { margin-right: 2px; }
.table-total {
  padding: 6px 12px; text-align: right; font-size: 12px;
  color: var(--el-text-color-regular); font-weight: 600;
}
.voucher-table :deep(.abnormal-row td) { background-color: #fef2f2 !important; }

.ratio-table { max-width: 640px; }
.ratio-warn { margin-top: 10px; }
.muted { color: var(--el-text-color-placeholder); }
.note-block { margin-top: 10px; display: flex; flex-direction: column; gap: 4px; }
.note-block label { font-size: 12px; color: var(--el-text-color-secondary); }

.abnormal-summary {
  margin-bottom: 10px; padding: 10px 12px; border-radius: 6px;
  background: #fef2f2; border: 1px solid #fecaca;
}
.as-header {
  font-weight: 600; color: var(--el-color-danger); margin-bottom: 6px;
  display: flex; align-items: center; justify-content: space-between; gap: 8px;
}
.push-btn { flex-shrink: 0; }
.as-list { padding-left: 18px; margin: 0; line-height: 1.7; color: var(--el-color-danger-dark-2); }

.conclusion-card { margin-bottom: 10px; }
.concl-select { width: 100%; margin-bottom: 8px; }

.compile-hint { margin-top: 6px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; line-height: 1.8; }

.samp-guide section { margin-bottom: 16px; }
.samp-guide h4 { margin: 0 0 6px; font-size: 14px; }
.samp-guide p, .samp-guide ul { font-size: 12px; line-height: 1.7; margin: 4px 0; }
.samp-guide ul { padding-left: 18px; }
.muted-block { color: var(--el-text-color-secondary); background: #f5f7fa; padding: 8px; border-radius: 4px; }
.warn-line { color: var(--el-color-warning-dark-2); }
.formula {
  font-family: ui-monospace, Consolas, monospace; background: #f0f5ff; padding: 8px;
  border-radius: 4px; font-size: 11px;
}
.exp-table { width: 100%; border-collapse: collapse; font-size: 12px; margin-top: 8px; }
.exp-table th, .exp-table td { border: 1px solid #dcdfe6; padding: 6px 10px; text-align: center; }
.exp-table th { background: #f5f7fa; }

@media (max-width: 960px) {
  .guide-banner { grid-template-columns: 1fr 1fr; }
  .criteria-grid { grid-template-columns: 1fr; }
}
</style>
