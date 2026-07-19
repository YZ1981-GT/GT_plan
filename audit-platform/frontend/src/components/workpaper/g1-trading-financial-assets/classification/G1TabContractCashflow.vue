<template>
  <div class="g1-sppi" data-testid="g1-contract-cashflow">
    <div class="section-head">
      <div class="title-block">
        <h3 class="sheet-title">G1-10 合同现金流量特征分析</h3>
        <p class="sheet-sub">
          SPPI 逐项测试（CAS22）：按品种分区取证 → 自动建议结论 → 支撑 G1-9 分类
        </p>
      </div>
      <div class="head-actions">
        <G1ImportExportDropdown
          v-if="wpId"
          :wp-id="wpId"
          sheet="G1-10"
          :disabled="isReadonly"
          @imported="onImported"
        />
        <span class="chip-wrap"><GtIndexChip value="wp:G1-8" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:G1-9" /></span>
        <el-tag size="small" type="success">通过 {{ stats.pass }}</el-tag>
        <el-tag size="small" type="danger">不通过 {{ stats.fail }}</el-tag>
        <el-tag size="small" type="warning">待分析 {{ stats.further }}</el-tag>
        <el-button size="small" @click="openReviewDialog('G1-10-conclusion')">💬复核</el-button>
      </div>
    </div>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="objective-alert"
      title="审计目标：确定金融资产合同现金流量是否仅为对本金和以未偿付本金金额为基础的利息的支付（SPPI），并与业务模式（G1-8）结合支撑分类结论。"
    />

    <div class="methodology">
      <strong>二、审计过程要点：</strong>
      ①分析利息构成是否仅为货币时间价值、信用风险等基本借贷对价；
      ②评估利率重置/修改的货币时间价值；
      ③检查提前赎回、展期、杠杆、权益挂钩等条款；
      ④对理财/ABS/项目收益按品种执行保本判断、不现实评估或穿透测试。
    </div>

    <el-alert
      v-if="stats.mismatches"
      type="warning"
      :closable="false"
      class="warn-alert"
      :title="`有 ${stats.mismatches} 项结论与系统建议不一致（如含转股却标「通过」），请复核后确认覆盖理由。`"
    />

    <el-segmented
      v-model="activeSection"
      :options="sectionOptions"
      size="small"
      class="seg"
    />

    <!-- ════════════ (一) 债券 ════════════ -->
    <section v-show="activeSection === 'bond'" class="sec">
      <div class="sec-head">
        <h4>（一）债券投资（国债、企业债、公司债等）</h4>
        <el-button size="small" type="primary" :disabled="isReadonly" @click="addBond()">新增</el-button>
      </div>
      <p class="sec-hint">{{ G1_SPPI_GUIDANCE.bond }}</p>
      <el-table :data="store.bondRows" border size="small" max-height="420">
        <el-table-column label="#" prop="seq" width="44" />
        <el-table-column label="投资项目" min-width="120">
          <template #default="{ row }">
            <el-input :model-value="row.investItem" size="small" :disabled="isReadonly"
              @update:model-value="(v: string) => updateBond(row.id, { investItem: v })" />
          </template>
        </el-table-column>
        <el-table-column label="账面/面值" width="100" align="right">
          <template #default="{ row }">
            <el-input-number :model-value="row.bookOrFaceValue" size="small" :controls="false" style="width:100%"
              :disabled="isReadonly"
              @update:model-value="(v: number | undefined) => updateBond(row.id, { bookOrFaceValue: v ?? 0 })" />
          </template>
        </el-table-column>
        <el-table-column label="票面利率" width="90">
          <template #default="{ row }">
            <el-input :model-value="row.couponRate" size="small" :disabled="isReadonly" placeholder="3%"
              @update:model-value="(v: string) => updateBond(row.id, { couponRate: v })" />
          </template>
        </el-table-column>
        <el-table-column label="提前赎回" width="88" align="center">
          <template #default="{ row }">
            <el-select :model-value="row.hasEarlyRedemption" size="small" :disabled="isReadonly"
              @update:model-value="(v: string) => updateBond(row.id, { hasEarlyRedemption: v as any })">
              <el-option value="yes" label="是" /><el-option value="no" label="否" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="展期" width="80" align="center">
          <template #default="{ row }">
            <el-select :model-value="row.hasExtension" size="small" :disabled="isReadonly"
              @update:model-value="(v: string) => updateBond(row.id, { hasExtension: v as any })">
              <el-option value="yes" label="是" /><el-option value="no" label="否" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="权益转换" width="88" align="center">
          <template #default="{ row }">
            <el-select :model-value="row.hasEquityConversion" size="small" :disabled="isReadonly"
              @update:model-value="(v: string) => updateBond(row.id, { hasEquityConversion: v as any })">
              <el-option value="yes" label="是" /><el-option value="no" label="否" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="杠杆" width="80" align="center">
          <template #default="{ row }">
            <el-select :model-value="row.hasLeverage" size="small" :disabled="isReadonly"
              @update:model-value="(v: string) => updateBond(row.id, { hasLeverage: v as any })">
              <el-option value="yes" label="是" /><el-option value="no" label="否" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="建议" width="100">
          <template #default="{ row }">
            <el-tag size="small" :type="tagType(row.suggested)" effect="plain">{{ labelConc(row.suggested) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="结论" width="130">
          <template #default="{ row }">
            <el-select :model-value="row.conclusion" size="small" :disabled="isReadonly"
              :class="{ mismatch: row.suggested && row.conclusion && row.suggested !== row.conclusion }"
              @update:model-value="(v: string) => updateBond(row.id, { conclusion: v as any })">
              <el-option v-for="o in G1_SPPI_CONCLUSION_OPTIONS" :key="String(o.value)" :label="o.label" :value="o.value" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="分析说明" min-width="140">
          <template #default="{ row }">
            <el-input :model-value="row.analysisNote" size="small" type="textarea" :autosize="{ minRows: 1, maxRows: 3 }"
              :disabled="isReadonly" @update:model-value="(v: string) => updateBond(row.id, { analysisNote: v })" />
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="操作" width="56" fixed="right">
          <template #default="{ row }">
            <el-button link type="danger" size="small" @click="removeBond(row.id)">删</el-button>
          </template>
        </el-table-column>
      </el-table>
    </section>

    <!-- ════════════ (二) 理财第一步 ════════════ -->
    <section v-show="activeSection === 'wealth1'" class="sec">
      <div class="sec-head">
        <h4>（二）银行理财产品 — 第一步：是否保本保收益</h4>
        <div>
          <el-button size="small" :disabled="isReadonly" @click="pullFloatingToStep2()">浮动项→第二步</el-button>
          <el-button size="small" type="primary" :disabled="isReadonly" @click="addWealth1()">新增</el-button>
        </div>
      </div>
      <p class="sec-hint">{{ G1_SPPI_GUIDANCE.wealth }}</p>
      <el-table :data="store.wealthStep1" border size="small" max-height="420">
        <el-table-column label="投资项目" min-width="120">
          <template #default="{ row }">
            <el-input :model-value="row.investItem" size="small" :disabled="isReadonly"
              @update:model-value="(v: string) => updateWealth1(row.id, { investItem: v })" />
          </template>
        </el-table-column>
        <el-table-column label="投资总额" width="100" align="right">
          <template #default="{ row }">
            <el-input-number :model-value="row.totalAmount" size="small" :controls="false" style="width:100%"
              :disabled="isReadonly"
              @update:model-value="(v: number | undefined) => updateWealth1(row.id, { totalAmount: v ?? 0 })" />
          </template>
        </el-table-column>
        <el-table-column label="保证本金" width="88" align="center">
          <template #default="{ row }">
            <el-select :model-value="row.guaranteesPrincipal" size="small" :disabled="isReadonly"
              @update:model-value="(v: string) => updateWealth1(row.id, { guaranteesPrincipal: v as any })">
              <el-option value="yes" label="是" /><el-option value="no" label="否" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="固定收益" width="88" align="center">
          <template #default="{ row }">
            <el-select :model-value="row.fixedGuaranteed" size="small" :disabled="isReadonly"
              @update:model-value="(v: string) => updateWealth1(row.id, { fixedGuaranteed: v as any })">
              <el-option value="yes" label="是" /><el-option value="no" label="否" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="固定收益率" width="100">
          <template #default="{ row }">
            <el-input :model-value="row.fixedRate" size="small" :disabled="isReadonly"
              @update:model-value="(v: string) => updateWealth1(row.id, { fixedRate: v })" />
          </template>
        </el-table-column>
        <el-table-column label="浮动收益" width="88" align="center">
          <template #default="{ row }">
            <el-select :model-value="row.floatingGuaranteed" size="small" :disabled="isReadonly"
              @update:model-value="(v: string) => updateWealth1(row.id, { floatingGuaranteed: v as any })">
              <el-option value="yes" label="是" /><el-option value="no" label="否" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="浮动收益率" width="100">
          <template #default="{ row }">
            <el-input :model-value="row.floatingRate" size="small" :disabled="isReadonly"
              @update:model-value="(v: string) => updateWealth1(row.id, { floatingRate: v })" />
          </template>
        </el-table-column>
        <el-table-column label="建议" width="100">
          <template #default="{ row }">
            <el-tag size="small" :type="tagType(row.suggested)" effect="plain">{{ labelConc(row.suggested) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="结论" width="130">
          <template #default="{ row }">
            <el-select :model-value="row.conclusion" size="small" :disabled="isReadonly"
              @update:model-value="(v: string) => updateWealth1(row.id, { conclusion: v as any })">
              <el-option v-for="o in G1_SPPI_CONCLUSION_OPTIONS" :key="String(o.value)" :label="o.label" :value="o.value" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="操作" width="56" fixed="right">
          <template #default="{ row }">
            <el-button link type="danger" size="small" @click="removeWealth1(row.id)">删</el-button>
          </template>
        </el-table-column>
      </el-table>
    </section>

    <!-- ════════════ (二) 理财第二步 ════════════ -->
    <section v-show="activeSection === 'wealth2'" class="sec">
      <div class="sec-head">
        <h4>（二）银行理财产品 — 第二步：浮动收益是否不现实</h4>
        <el-button size="small" type="primary" :disabled="isReadonly" @click="addWealth2()">新增</el-button>
      </div>
      <p class="sec-hint">
        示例：挂钩 EUR/USD 且触发区间历史上几乎不可能达到时，可认定浮动条件「不现实」，仍通过 SPPI。
      </p>
      <el-table :data="store.wealthStep2" border size="small" max-height="420">
        <el-table-column label="投资项目" min-width="120">
          <template #default="{ row }">
            <el-input :model-value="row.investItem" size="small" :disabled="isReadonly"
              @update:model-value="(v: string) => updateWealth2(row.id, { investItem: v })" />
          </template>
        </el-table-column>
        <el-table-column label="固定收益率" width="100">
          <template #default="{ row }">
            <el-input :model-value="row.fixedRate" size="small" :disabled="isReadonly"
              @update:model-value="(v: string) => updateWealth2(row.id, { fixedRate: v })" />
          </template>
        </el-table-column>
        <el-table-column label="浮动收益确定方式" min-width="140">
          <template #default="{ row }">
            <el-input :model-value="row.floatingMethod" size="small" type="textarea" :autosize="{ minRows: 1, maxRows: 2 }"
              :disabled="isReadonly" placeholder="如：EUR/USD∈[a,b] 时额外收益"
              @update:model-value="(v: string) => updateWealth2(row.id, { floatingMethod: v })" />
          </template>
        </el-table-column>
        <el-table-column label="基础变量历史变动" min-width="140">
          <template #default="{ row }">
            <el-input :model-value="row.baseVariableHistory" size="small" type="textarea" :autosize="{ minRows: 1, maxRows: 2 }"
              :disabled="isReadonly" placeholder="历史区间/波动说明"
              @update:model-value="(v: string) => updateWealth2(row.id, { baseVariableHistory: v })" />
          </template>
        </el-table-column>
        <el-table-column label="是否不现实" width="100" align="center">
          <template #default="{ row }">
            <el-select :model-value="row.isUnrealistic" size="small" :disabled="isReadonly"
              @update:model-value="(v: string) => updateWealth2(row.id, { isUnrealistic: v as any })">
              <el-option value="yes" label="是" /><el-option value="no" label="否" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="建议" width="100">
          <template #default="{ row }">
            <el-tag size="small" :type="tagType(row.suggested)" effect="plain">{{ labelConc(row.suggested) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="结论" width="130">
          <template #default="{ row }">
            <el-select :model-value="row.conclusion" size="small" :disabled="isReadonly"
              @update:model-value="(v: string) => updateWealth2(row.id, { conclusion: v as any })">
              <el-option v-for="o in G1_SPPI_CONCLUSION_OPTIONS" :key="String(o.value)" :label="o.label" :value="o.value" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="操作" width="56" fixed="right">
          <template #default="{ row }">
            <el-button link type="danger" size="small" @click="removeWealth2(row.id)">删</el-button>
          </template>
        </el-table-column>
      </el-table>
    </section>

    <!-- ════════════ (三) 永续 ════════════ -->
    <section v-show="activeSection === 'perpetual'" class="sec">
      <div class="sec-head">
        <h4>（三）优先股、永续债</h4>
        <el-button size="small" type="primary" :disabled="isReadonly" @click="addPerpetual()">新增</el-button>
      </div>
      <p class="sec-hint">{{ G1_SPPI_GUIDANCE.perpetual }}</p>
      <el-table :data="store.perpetualRows" border size="small" max-height="420">
        <el-table-column label="投资项目" min-width="120">
          <template #default="{ row }">
            <el-input :model-value="row.investItem" size="small" :disabled="isReadonly"
              @update:model-value="(v: string) => updatePerpetual(row.id, { investItem: v })" />
          </template>
        </el-table-column>
        <el-table-column label="账面价值" width="100" align="right">
          <template #default="{ row }">
            <el-input-number :model-value="row.bookValue" size="small" :controls="false" style="width:100%"
              :disabled="isReadonly"
              @update:model-value="(v: number | undefined) => updatePerpetual(row.id, { bookValue: v ?? 0 })" />
          </template>
        </el-table-column>
        <el-table-column label="期限" width="80">
          <template #default="{ row }">
            <el-input :model-value="row.term" size="small" :disabled="isReadonly" placeholder="3+N"
              @update:model-value="(v: string) => updatePerpetual(row.id, { term: v })" />
          </template>
        </el-table-column>
        <el-table-column label="初始利率" width="90">
          <template #default="{ row }">
            <el-input :model-value="row.initialRate" size="small" :disabled="isReadonly"
              @update:model-value="(v: string) => updatePerpetual(row.id, { initialRate: v })" />
          </template>
        </el-table-column>
        <el-table-column label="递延股息" width="88" align="center">
          <template #default="{ row }">
            <el-select :model-value="row.hasDeferredDividend" size="small" :disabled="isReadonly"
              @update:model-value="(v: string) => updatePerpetual(row.id, { hasDeferredDividend: v as any })">
              <el-option value="yes" label="是" /><el-option value="no" label="否" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="递延计息" width="88" align="center">
          <template #default="{ row }">
            <el-select :model-value="row.deferredCompounds" size="small" :disabled="isReadonly"
              @update:model-value="(v: string) => updatePerpetual(row.id, { deferredCompounds: v as any })">
              <el-option value="yes" label="是" /><el-option value="no" label="否" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="可转固定数量权益" width="120" align="center">
          <template #default="{ row }">
            <el-select :model-value="row.convertibleToFixedEquity" size="small" :disabled="isReadonly"
              @update:model-value="(v: string) => updatePerpetual(row.id, { convertibleToFixedEquity: v as any })">
              <el-option value="yes" label="是" /><el-option value="no" label="否" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="建议" width="100">
          <template #default="{ row }">
            <el-tag size="small" :type="tagType(row.suggested)" effect="plain">{{ labelConc(row.suggested) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="结论" width="130">
          <template #default="{ row }">
            <el-select :model-value="row.conclusion" size="small" :disabled="isReadonly"
              @update:model-value="(v: string) => updatePerpetual(row.id, { conclusion: v as any })">
              <el-option v-for="o in G1_SPPI_CONCLUSION_OPTIONS" :key="String(o.value)" :label="o.label" :value="o.value" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="操作" width="56" fixed="right">
          <template #default="{ row }">
            <el-button link type="danger" size="small" @click="removePerpetual(row.id)">删</el-button>
          </template>
        </el-table-column>
      </el-table>
    </section>

    <!-- ════════════ (四) 可转债 ════════════ -->
    <section v-show="activeSection === 'convertible'" class="sec">
      <div class="sec-head">
        <h4>（四）可转换债券</h4>
        <el-button size="small" type="primary" :disabled="isReadonly" @click="addConvertible()">新增</el-button>
      </div>
      <el-alert type="warning" :closable="false" show-icon class="sec-warn"
        title="模板示例若写「通过 SPPI」但存在转股条款，应按准则改为不通过（嵌入权益衍生）。系统默认建议「不通过」。" />
      <p class="sec-hint">{{ G1_SPPI_GUIDANCE.convertible }}</p>
      <el-table :data="store.convertibleRows" border size="small" max-height="420">
        <el-table-column label="投资项目" min-width="120">
          <template #default="{ row }">
            <el-input :model-value="row.investItem" size="small" :disabled="isReadonly"
              @update:model-value="(v: string) => updateConvertible(row.id, { investItem: v })" />
          </template>
        </el-table-column>
        <el-table-column label="投资总额" width="100" align="right">
          <template #default="{ row }">
            <el-input-number :model-value="row.totalAmount" size="small" :controls="false" style="width:100%"
              :disabled="isReadonly"
              @update:model-value="(v: number | undefined) => updateConvertible(row.id, { totalAmount: v ?? 0 })" />
          </template>
        </el-table-column>
        <el-table-column label="期限" width="80">
          <template #default="{ row }">
            <el-input :model-value="row.term" size="small" :disabled="isReadonly"
              @update:model-value="(v: string) => updateConvertible(row.id, { term: v })" />
          </template>
        </el-table-column>
        <el-table-column label="票面利率" width="100">
          <template #default="{ row }">
            <el-input :model-value="row.couponRate" size="small" :disabled="isReadonly" placeholder="递进利率可文字填写"
              @update:model-value="(v: string) => updateConvertible(row.id, { couponRate: v })" />
          </template>
        </el-table-column>
        <el-table-column label="初始转股价" width="100">
          <template #default="{ row }">
            <el-input :model-value="row.initialConversionPrice" size="small" :disabled="isReadonly"
              @update:model-value="(v: string) => updateConvertible(row.id, { initialConversionPrice: v })" />
          </template>
        </el-table-column>
        <el-table-column label="含转股" width="88" align="center">
          <template #default="{ row }">
            <el-select :model-value="row.hasConversionFeature" size="small" :disabled="isReadonly"
              @update:model-value="(v: string) => updateConvertible(row.id, { hasConversionFeature: v as any })">
              <el-option value="yes" label="是" /><el-option value="no" label="否" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="建议" width="100">
          <template #default="{ row }">
            <el-tag size="small" :type="tagType(row.suggested)" effect="plain">{{ labelConc(row.suggested) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="结论" width="130">
          <template #default="{ row }">
            <el-select :model-value="row.conclusion" size="small" :disabled="isReadonly"
              :class="{ mismatch: row.suggested && row.conclusion && row.suggested !== row.conclusion }"
              @update:model-value="(v: string) => updateConvertible(row.id, { conclusion: v as any })">
              <el-option v-for="o in G1_SPPI_CONCLUSION_OPTIONS" :key="String(o.value)" :label="o.label" :value="o.value" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="特征说明" min-width="140">
          <template #default="{ row }">
            <el-input :model-value="row.featureDesc" size="small" type="textarea" :autosize="{ minRows: 1, maxRows: 2 }"
              :disabled="isReadonly" @update:model-value="(v: string) => updateConvertible(row.id, { featureDesc: v })" />
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="操作" width="56" fixed="right">
          <template #default="{ row }">
            <el-button link type="danger" size="small" @click="removeConvertible(row.id)">删</el-button>
          </template>
        </el-table-column>
      </el-table>
    </section>

    <!-- ════════════ (五) 项目收益 ════════════ -->
    <section v-show="activeSection === 'project'" class="sec">
      <div class="sec-head">
        <h4>（五）项目收益权、信托计划份额</h4>
        <el-button size="small" type="primary" :disabled="isReadonly" @click="addProject()">新增</el-button>
      </div>
      <p class="sec-hint">{{ G1_SPPI_GUIDANCE.project }}</p>
      <el-table :data="store.projectRows" border size="small" max-height="420">
        <el-table-column label="投资项目" min-width="120">
          <template #default="{ row }">
            <el-input :model-value="row.investItem" size="small" :disabled="isReadonly"
              @update:model-value="(v: string) => updateProject(row.id, { investItem: v })" />
          </template>
        </el-table-column>
        <el-table-column label="投资总额" width="100" align="right">
          <template #default="{ row }">
            <el-input-number :model-value="row.totalAmount" size="small" :controls="false" style="width:100%"
              :disabled="isReadonly"
              @update:model-value="(v: number | undefined) => updateProject(row.id, { totalAmount: v ?? 0 })" />
          </template>
        </el-table-column>
        <el-table-column label="期限" width="80">
          <template #default="{ row }">
            <el-input :model-value="row.term" size="small" :disabled="isReadonly"
              @update:model-value="(v: string) => updateProject(row.id, { term: v })" />
          </template>
        </el-table-column>
        <el-table-column label="票面利率" width="90">
          <template #default="{ row }">
            <el-input :model-value="row.couponRate" size="small" :disabled="isReadonly"
              @update:model-value="(v: string) => updateProject(row.id, { couponRate: v })" />
          </template>
        </el-table-column>
        <el-table-column label="基础资产现金流" min-width="130">
          <template #default="{ row }">
            <el-input :model-value="row.underlyingCashFlow" size="small" type="textarea" :autosize="{ minRows: 1, maxRows: 2 }"
              :disabled="isReadonly" @update:model-value="(v: string) => updateProject(row.id, { underlyingCashFlow: v })" />
          </template>
        </el-table-column>
        <el-table-column label="差额补足" min-width="110">
          <template #default="{ row }">
            <el-input :model-value="row.deficiencyCompensation" size="small" :disabled="isReadonly"
              @update:model-value="(v: string) => updateProject(row.id, { deficiencyCompensation: v })" />
          </template>
        </el-table-column>
        <el-table-column label="担保" min-width="100">
          <template #default="{ row }">
            <el-input :model-value="row.guarantee" size="small" :disabled="isReadonly"
              @update:model-value="(v: string) => updateProject(row.id, { guarantee: v })" />
          </template>
        </el-table-column>
        <el-table-column label="依赖项目运营" width="110" align="center">
          <template #default="{ row }">
            <el-select :model-value="row.cfDependsOnProjectOps" size="small" :disabled="isReadonly"
              @update:model-value="(v: string) => updateProject(row.id, { cfDependsOnProjectOps: v as any })">
              <el-option value="yes" label="是" /><el-option value="no" label="否" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="建议" width="100">
          <template #default="{ row }">
            <el-tag size="small" :type="tagType(row.suggested)" effect="plain">{{ labelConc(row.suggested) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="结论" width="130">
          <template #default="{ row }">
            <el-select :model-value="row.conclusion" size="small" :disabled="isReadonly"
              @update:model-value="(v: string) => updateProject(row.id, { conclusion: v as any })">
              <el-option v-for="o in G1_SPPI_CONCLUSION_OPTIONS" :key="String(o.value)" :label="o.label" :value="o.value" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="操作" width="56" fixed="right">
          <template #default="{ row }">
            <el-button link type="danger" size="small" @click="removeProject(row.id)">删</el-button>
          </template>
        </el-table-column>
      </el-table>
    </section>

    <!-- ════════════ (六) ABS ════════════ -->
    <section v-show="activeSection === 'abs'" class="sec">
      <div class="sec-head">
        <h4>（六）资产支持证券（ABS）</h4>
        <el-button size="small" type="primary" :disabled="isReadonly" @click="addAbs()">新增</el-button>
      </div>
      <p class="sec-hint">{{ G1_SPPI_GUIDANCE.abs }}</p>
      <el-table :data="store.absRows" border size="small" max-height="420">
        <el-table-column label="投资项目" min-width="120">
          <template #default="{ row }">
            <el-input :model-value="row.investItem" size="small" :disabled="isReadonly"
              @update:model-value="(v: string) => updateAbs(row.id, { investItem: v })" />
          </template>
        </el-table-column>
        <el-table-column label="投资总额" width="100" align="right">
          <template #default="{ row }">
            <el-input-number :model-value="row.totalAmount" size="small" :controls="false" style="width:100%"
              :disabled="isReadonly"
              @update:model-value="(v: number | undefined) => updateAbs(row.id, { totalAmount: v ?? 0 })" />
          </template>
        </el-table-column>
        <el-table-column label="期限" width="80">
          <template #default="{ row }">
            <el-input :model-value="row.term" size="small" :disabled="isReadonly"
              @update:model-value="(v: string) => updateAbs(row.id, { term: v })" />
          </template>
        </el-table-column>
        <el-table-column label="票面利率" width="90">
          <template #default="{ row }">
            <el-input :model-value="row.couponRate" size="small" :disabled="isReadonly" placeholder="次级可填「无」"
              @update:model-value="(v: string) => updateAbs(row.id, { couponRate: v })" />
          </template>
        </el-table-column>
        <el-table-column label="级次" width="100">
          <template #default="{ row }">
            <el-select :model-value="row.tranche" size="small" :disabled="isReadonly"
              @update:model-value="(v: string) => updateAbs(row.id, { tranche: v as any })">
              <el-option value="senior" label="优先" />
              <el-option value="mezzanine" label="中间" />
              <el-option value="subordinated" label="次级" />
              <el-option value="other" label="其他" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="基础资产现金流" min-width="120">
          <template #default="{ row }">
            <el-input :model-value="row.underlyingCashFlow" size="small" type="textarea" :autosize="{ minRows: 1, maxRows: 2 }"
              :disabled="isReadonly" @update:model-value="(v: string) => updateAbs(row.id, { underlyingCashFlow: v })" />
          </template>
        </el-table-column>
        <el-table-column label="信用风险比较" min-width="120">
          <template #default="{ row }">
            <el-input :model-value="row.creditRiskCompare" size="small" type="textarea" :autosize="{ minRows: 1, maxRows: 2 }"
              :disabled="isReadonly" placeholder="本档 vs 底层池平均"
              @update:model-value="(v: string) => updateAbs(row.id, { creditRiskCompare: v })" />
          </template>
        </el-table-column>
        <el-table-column label="穿透条件满足" width="110" align="center">
          <template #default="{ row }">
            <el-select :model-value="row.lookThroughOk" size="small" :disabled="isReadonly"
              @update:model-value="(v: string) => updateAbs(row.id, { lookThroughOk: v as any })">
              <el-option value="yes" label="是" /><el-option value="no" label="否" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="建议" width="100">
          <template #default="{ row }">
            <el-tag size="small" :type="tagType(row.suggested)" effect="plain">{{ labelConc(row.suggested) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="结论" width="130">
          <template #default="{ row }">
            <el-select :model-value="row.conclusion" size="small" :disabled="isReadonly"
              @update:model-value="(v: string) => updateAbs(row.id, { conclusion: v as any })">
              <el-option v-for="o in G1_SPPI_CONCLUSION_OPTIONS" :key="String(o.value)" :label="o.label" :value="o.value" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="操作" width="56" fixed="right">
          <template #default="{ row }">
            <el-button link type="danger" size="small" @click="removeAbs(row.id)">删</el-button>
          </template>
        </el-table-column>
      </el-table>
    </section>

    <G1AuditTextCards
      :wp-id="wpId"
      :is-readonly="isReadonly"
      v-model:note="auditNote"
      v-model:conclusion="auditConclusion"
      note-ai-section="sppi-note"
      conclusion-ai-section="sppi-conclusion"
      note-placeholder="三、审计说明：概述各品种 SPPI 测试范围、关键条款判断、与模板示例差异及拟调整事项。"
      note-hint="覆盖债券四特征、理财两步、可转债转股、ABS 穿透。"
      conclusion-placeholder="四、审计结论：合同现金流量特征是否通过 SPPI，以及对分类（G1-9）的影响。"
      :related-context="{
        通过: stats.pass,
        不通过: stats.fail,
        待分析: stats.further,
        不一致: stats.mismatches,
      }"
    />

    <details class="prep-hint">
      <summary>📋 编制提示（CAS22 关键判定框架）</summary>
      <ol>
        <li><b>基本借贷安排：</b>利息含货币时间价值、信用风险、流动性风险、管理成本及利润率；不含权益/商品等无关风险。</li>
        <li><b>修改的货币时间价值：</b>利率重置与期间不匹配时做基准测试，差异显著则不通过。</li>
        <li><b>提前还款/展期：</b>若展期期间仍为本金+利息且无杠杆，可仍通过；否则进一步分析。</li>
        <li><b>无追索权：</b>不必然失败，需穿透底层资产现金流特征。</li>
        <li><b>合同挂钩工具（ABS 等多档）：</b>穿透三条件——底层含 SPPI 工具、本档信用风险≤池平均、无其他改变现金流特征。</li>
        <li><b>极小/非真实特征：</b>影响超过极小且属真实特征 → 不通过；「不现实」浮动条件可忽略。</li>
      </ol>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, toRef, inject, watch, computed } from 'vue'
import GtIndexChip from '../../GtIndexChip.vue'
import G1AuditTextCards from '../G1AuditTextCards.vue'
import G1ImportExportDropdown from '../G1ImportExportDropdown.vue'
import {
  useG1ContractCashflow,
  G1_SPPI_SECTIONS,
  G1_SPPI_CONCLUSION_OPTIONS,
  G1_SPPI_GUIDANCE,
  type G1SppiConclusion,
  type G1SppiSectionKey,
} from '../../composables/useG1ContractCashflow'
import type { ChecklistResponse } from '../../composables/useF1FormData'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  wpId?: string
}>()

const emit = defineEmits<{ imported: [] }>()

const wpId = computed(() => props.wpId ?? '')
const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})

const {
  store,
  activeSection,
  auditConclusion,
  stats,
  loadAll,
  updateBond,
  addBond,
  removeBond,
  updateWealth1,
  addWealth1,
  removeWealth1,
  updateWealth2,
  addWealth2,
  removeWealth2,
  pullFloatingToStep2,
  updatePerpetual,
  addPerpetual,
  removePerpetual,
  updateConvertible,
  addConvertible,
  removeConvertible,
  updateProject,
  addProject,
  removeProject,
  updateAbs,
  addAbs,
  removeAbs,
} = useG1ContractCashflow({
  allResponses: toRef(props, 'allResponses'),
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly'),
})

function onImported() {
  loadAll()
  emit('imported')
}

const sectionOptions = G1_SPPI_SECTIONS.map((s) => ({ label: s.label, value: s.key as G1SppiSectionKey }))

const AUDIT_NOTE_KEY = 'G1-10-audit-note'
const auditNote = ref(props.allResponses.get(AUDIT_NOTE_KEY)?.remark ?? '')
watch(auditNote, (v) => {
  if (!props.isReadonly) props.debouncedSave(AUDIT_NOTE_KEY, { conclusion: null, remark: v })
})

function labelConc(c: G1SppiConclusion): string {
  if (c === 'PASS') return '通过'
  if (c === 'FAIL') return '不通过'
  if (c === 'FURTHER_ANALYSIS') return '待分析'
  return '—'
}

function tagType(c: G1SppiConclusion): 'success' | 'danger' | 'warning' | 'info' {
  if (c === 'PASS') return 'success'
  if (c === 'FAIL') return 'danger'
  if (c === 'FURTHER_ANALYSIS') return 'warning'
  return 'info'
}
</script>

<style scoped>
.g1-sppi { padding: 4px 4px 20px; font-size: var(--wp-font-size, 13px); color: #303133; }
.section-head {
  display: flex; justify-content: space-between; align-items: flex-start;
  gap: 12px; margin-bottom: 12px; flex-wrap: wrap;
}
.title-block { min-width: 220px; }
.sheet-title { margin: 0; font-size: 16px; font-weight: 600; color: #1f2a37; }
.sheet-sub { margin: 4px 0 0; font-size: 12px; color: #86909c; line-height: 1.4; }
.head-actions { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }
.objective-alert { margin-bottom: 10px; }
.methodology {
  margin-bottom: 10px; padding: 8px 12px; background: #fdf6ec;
  border-left: 3px solid #e6a23c; font-size: 12px; color: #8a6d3b; line-height: 1.55;
}
.warn-alert { margin-bottom: 10px; }
.seg { margin-bottom: 12px; flex-wrap: wrap; }
.sec { margin-bottom: 8px; }
.sec-head {
  display: flex; justify-content: space-between; align-items: center;
  gap: 8px; margin-bottom: 6px; flex-wrap: wrap;
}
.sec-head h4 { margin: 0; font-size: 13px; font-weight: 600; color: #1f2a37; }
.sec-hint { margin: 0 0 8px; font-size: 12px; color: #86909c; line-height: 1.5; }
.sec-warn { margin-bottom: 8px; }
.mismatch :deep(.el-input__wrapper) { box-shadow: 0 0 0 1px #e6a23c inset; }
.prep-hint { margin-top: 12px; font-size: 12px; color: #909399; }
.prep-hint summary { cursor: pointer; }
.prep-hint ol { margin: 8px 0 0; padding-left: 18px; line-height: 1.65; }
</style>
