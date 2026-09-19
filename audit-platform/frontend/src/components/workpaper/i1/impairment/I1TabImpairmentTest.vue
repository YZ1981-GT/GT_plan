<template>
  <div class="i1-tab-impairment-test">
    <div class="methodology-block">
      <p>
        <strong>编制逻辑（CAS8）：</strong>
        寿命不确定须每年测试；寿命确定仅在有减值迹象时测试。
        判定 → ②账面(原值−摊销，不含减值) → ③④(I1-13) → ⑤=MAX(③,④)
        → ⑥=MAX(②−⑤,0) → ⑧=MAX(⑥−⑦,0) / ⑨=MAX(⑦−⑥,0)（⑨仅待查，禁止转回）。
      </p>
      <p class="methodology-note">
        说明：年末必须对「使用寿命不确定的无形资产」进行减值测试；
        「使用寿命确定的无形资产」只有在发生资产减值迹象时才进行减值测试。
      </p>
    </div>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="objective-alert"
      title="审计目标：核实本期无形资产减值准备计提是否合理；可收回金额与账面价值比较后确定应补提金额，确认减值损失一经确认不得转回。"
    />

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <span class="chip-wrap"><GtIndexChip value="wp:I1-12" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ impairmentRows.length }} 行</el-tag>
        <el-tag v-if="impairmentSummary.totalSupplement > 0" type="danger" size="small">
          应补提 {{ fmtAmt(impairmentSummary.totalSupplement) }}
        </el-tag>
        <el-tag v-if="impairmentSummary.totalOverProvision > 0" type="warning" size="small">
          多提待查 {{ fmtAmt(impairmentSummary.totalOverProvision) }}
        </el-tag>
        <el-tag v-if="!prepValidation.ok" type="danger" size="small">
          编制校验 {{ prepValidation.messages.length }} 项
        </el-tag>
        <el-tag v-if="missingRecoverableRows.length" type="danger" size="small">
          缺 I1-13 {{ missingRecoverableRows.length }}
        </el-tag>
        <el-tag v-if="staleSyncCount" type="warning" size="small">
          与 I1-13 不一致 {{ staleSyncCount }}
        </el-tag>
      </div>
      <div class="toolbar-right">
        <GtIndexChip value="wp:I1-2" :context-project-id="projectId" />
        <GtIndexChip value="wp:I1-7" :context-project-id="projectId" />
        <GtIndexChip value="wp:I1-13" :context-project-id="projectId" />
      </div>
    </div>

    <el-alert
      v-if="missingRecoverableRows.length"
      type="error"
      :closable="false"
      show-icon
      class="mb-8"
      :title="`须测试闸门：${missingRecoverableRows.length} 项须完成 I1-13 可收回测算`"
      :description="`待测：${missingRecoverableRows.map(r => r.name).filter(Boolean).slice(0, 6).join('、')}${missingRecoverableRows.length > 6 ? '…' : ''}。请点「建 I1-13 测算组」后完成测算并回填。`"
    />
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-header">
          <span class="section-title">I1-12 减值准备测试表</span>
          <div class="section-header-actions">
            <el-button size="small" :disabled="isReadonly" @click="handleSeedFromDetail">从 I1-2 带入②</el-button>
            <el-button size="small" :disabled="isReadonly" @click="handleSyncFromI17">从 I1-7 同步寿命</el-button>
            <el-button size="small" :disabled="isReadonly" @click="handleSeedI13">建 I1-13 测算组</el-button>
            <el-button size="small" :disabled="isReadonly" @click="handleLinkFromI13">回填 I1-13(③④)</el-button>
            <el-button
              size="small"
              type="warning"
              plain
              :disabled="isReadonly || impairmentSummary.totalSupplement < 0.01"
              @click="handleSwitchI111"
            >
              切换 I1-11 含减值
            </el-button>
            <el-button size="small" type="warning" plain :disabled="isReadonly" @click="handlePushToI111">
              回写 I1-11
            </el-button>
            <el-button size="small" :disabled="isReadonly || !projectId" @click="handlePublishK11">推送 K11</el-button>
            <el-button size="small" :disabled="isReadonly || !projectId" @click="handleReconcileK11">核对 K11</el-button>
            <el-button size="small" type="primary" plain :disabled="isReadonly" @click="handleAddRow">新增行</el-button>
            <el-dropdown v-if="!isReadonly" trigger="click" @command="handleExportImport">
              <el-button size="small" :loading="ieBusy">导入导出 ▾</el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="export-template">导出模板</el-dropdown-item>
                  <el-dropdown-item command="export-data">导出数据</el-dropdown-item>
                  <el-dropdown-item command="import-data" divided>导入数据</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
            <input ref="fileInputRef" type="file" accept=".xlsx,.xls" style="display:none" @change="onFileSelected" />
            <el-button size="small" circle @click="openReview('I1-12')">💬</el-button>
          </div>
        </div>
      </template>

      <el-alert
        v-if="!prepValidation.ok"
        type="warning"
        :closable="false"
        show-icon
        class="mb-8"
        :title="prepValidation.messages[0]"
        :description="prepValidation.messages.slice(1).join('；') || undefined"
      />

      <el-card v-if="syncChecks.length" shadow="never" class="sync-card mb-8">
        <template #header>
          <div class="section-header">
            <span>与 I1-13 回写一致性</span>
            <el-tag v-if="staleSyncCount" size="small" type="danger">{{ staleSyncCount }} 项待处理</el-tag>
            <el-tag v-else size="small" type="success">全部一致/无需测</el-tag>
            <el-button
              v-if="!isReadonly && staleSyncCount"
              size="small"
              type="warning"
              @click="handleLinkFromI13"
            >
              回填 I1-13(③④)
            </el-button>
          </div>
        </template>
        <el-table :data="syncChecks" border size="small" max-height="220">
          <el-table-column prop="name" label="资产名称" min-width="110" />
          <el-table-column label="状态" width="100" align="center">
            <template #default="{ row }">
              <el-tag
                size="small"
                :type="row.status === 'synced' ? 'success' : row.status === 'no-test' ? 'info' : 'danger'"
              >
                {{ syncStatusLabel(row.status) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="I1-12⑤" width="100" align="right">
            <template #default="{ row }">{{ fmtAmt(row.i12Recoverable) }}</template>
          </el-table-column>
          <el-table-column label="I1-13" width="100" align="right">
            <template #default="{ row }">{{ fmtAmt(row.i13Recoverable) }}</template>
          </el-table-column>
          <el-table-column prop="message" label="说明" min-width="180" />
        </el-table>
      </el-card>

      <el-table
        :data="impairmentRows"
        border
        stripe
        size="small"
        class="impairment-table"
        max-height="520"
        :row-class-name="getRowClassName"
        show-summary
        :summary-method="getSummary"
      >
        <el-table-column type="index" label="#" width="44" align="center" fixed />

        <el-table-column prop="category" label="类别" min-width="100" fixed>
          <template #default="{ row, $index }">
            <el-select
              v-if="!isReadonly"
              :model-value="row.category"
              size="small"
              filterable
              allow-create
              style="width:100%"
              @change="(v: string) => handleFieldUpdate($index, 'category', v)"
            >
              <el-option v-for="c in categoryOptions" :key="c" :label="c" :value="c" />
            </el-select>
            <span v-else>{{ row.category || '-' }}</span>
          </template>
        </el-table-column>

        <el-table-column prop="name" label="项目名称" min-width="120" fixed>
          <template #default="{ row, $index }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.name"
              size="small"
              @update:model-value="(v: string) => handleFieldUpdate($index, 'name', v)"
            />
            <span v-else>{{ row.name || '-' }}</span>
          </template>
        </el-table-column>

        <el-table-column label="寿命不确定" width="100" align="center">
          <template #header>
            <el-tooltip content="使用寿命是否不确定；为「是」则每年须减值测试" placement="top">
              <span>寿命不确定</span>
            </el-tooltip>
          </template>
          <template #default="{ row, $index }">
            <el-select
              v-if="!isReadonly"
              :model-value="row.indefiniteLife"
              size="small"
              style="width:100%"
              @change="(v: string) => handleFieldUpdate($index, 'indefiniteLife', v)"
            >
              <el-option label="是" value="Y" />
              <el-option label="否" value="N" />
              <el-option label="—" value="" />
            </el-select>
            <span v-else>{{ ynLabel(row.indefiniteLife) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="有迹象" width="90" align="center">
          <template #header>
            <el-tooltip content="是否存在减值迹象（见下方迹象清单）" placement="top">
              <span>有迹象</span>
            </el-tooltip>
          </template>
          <template #default="{ row, $index }">
            <el-select
              v-if="!isReadonly"
              :model-value="row.hasIndication"
              size="small"
              style="width:100%"
              @change="(v: string) => handleFieldUpdate($index, 'hasIndication', v)"
            >
              <el-option label="√ 有" value="Y" />
              <el-option label="× 无" value="N" />
              <el-option label="—" value="" />
            </el-select>
            <span v-else>{{ ynLabel(row.hasIndication) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="①迹象描述" min-width="130">
          <template #default="{ row, $index }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.indicationDesc"
              size="small"
              :disabled="row.hasIndication !== 'Y'"
              @update:model-value="(v: string) => handleFieldUpdate($index, 'indicationDesc', v)"
            />
            <span v-else>{{ row.indicationDesc || '-' }}</span>
          </template>
        </el-table-column>

        <el-table-column label="须测试" width="70" align="center">
          <template #header>
            <el-tooltip content="寿命不确定 OR 有迹象 → 须测试" placement="top">
              <span class="formula-header">须测试</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <el-tag :type="row.needTest ? 'warning' : 'info'" size="small">
              {{ row.needTest ? '是' : '否' }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column label="②账面价值" width="110" align="right">
          <template #header>
            <el-tooltip content="原值−累计摊销（不含减值），自 I1-2 带入" placement="top">
              <span class="formula-header">②账面价值</span>
            </el-tooltip>
          </template>
          <template #default="{ row, $index }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.bookValue"
              :controls="false"
              size="small"
              class="amt-input"
              @change="(v: number | undefined) => handleFieldUpdate($index, 'bookValue', v ?? 0)"
            />
            <span v-else class="amt-cell">{{ fmtAmt(row.bookValue) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="③公允净额" width="110" align="right">
          <template #header>
            <el-tooltip content="公允价值减去处置费用后的净额（I1-13）" placement="top">
              <span class="formula-header">③公允净额</span>
            </el-tooltip>
          </template>
          <template #default="{ row, $index }">
            <el-input-number
              v-if="!isReadonly && !row.linkedToDcf"
              :model-value="row.fairValueLessDisposal"
              :controls="false"
              size="small"
              class="amt-input"
              :disabled="!row.needTest"
              @change="(v: number | undefined) => handleFieldUpdate($index, 'fairValueLessDisposal', v ?? 0)"
            />
            <span v-else class="amt-cell">{{ fmtAmt(row.fairValueLessDisposal) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="④DCF现值" width="110" align="right">
          <template #header>
            <el-tooltip content="预计未来现金流量的现值（I1-13）" placement="top">
              <span class="formula-header">④DCF现值</span>
            </el-tooltip>
          </template>
          <template #default="{ row, $index }">
            <el-input-number
              v-if="!isReadonly && !row.linkedToDcf"
              :model-value="row.dcfValue"
              :controls="false"
              size="small"
              class="amt-input"
              :disabled="!row.needTest"
              @change="(v: number | undefined) => handleFieldUpdate($index, 'dcfValue', v ?? 0)"
            />
            <span v-else class="amt-cell">{{ fmtAmt(row.dcfValue) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="⑤可收回" width="100" align="right">
          <template #header>
            <el-tooltip content="⑤=MAX(③,④)；无须测试时为 0" placement="top">
              <span class="formula-header">⑤可收回</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <div class="recoverable-cell">
              <span class="formula-cell">{{ fmtAmt(row.recoverableAmount) }}</span>
              <GtIndexChip v-if="row.needTest" value="I1-13" label="DCF" @click="navigateToSheet('I1-13')" />
            </div>
          </template>
        </el-table-column>

        <el-table-column label="⑥应计提" width="100" align="right">
          <template #header>
            <el-tooltip content="⑥=MAX(②−⑤,0)" placement="top">
              <span class="formula-header">⑥应计提</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-cell" :class="{ 'error-amount': row.shouldProvision > 0 }">
              {{ fmtAmt(row.shouldProvision) }}
            </span>
          </template>
        </el-table-column>

        <el-table-column label="⑦已计提" width="110" align="right">
          <template #header>
            <el-tooltip content="期末账面已计提的减值准备（可自 I1-2 减值期末带入）" placement="top">
              <span class="formula-header">⑦已计提</span>
            </el-tooltip>
          </template>
          <template #default="{ row, $index }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.alreadyProvided"
              :controls="false"
              size="small"
              class="amt-input"
              @change="(v: number | undefined) => handleFieldUpdate($index, 'alreadyProvided', v ?? 0)"
            />
            <span v-else class="amt-cell">{{ fmtAmt(row.alreadyProvided) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="⑧应补提" width="100" align="right">
          <template #header>
            <el-tooltip content="⑧=MAX(⑥−⑦,0)" placement="top">
              <span class="formula-header">⑧应补提</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-cell" :class="{ 'error-amount': row.supplement > 0 }">
              {{ fmtAmt(row.supplement) }}
            </span>
          </template>
        </el-table-column>

        <el-table-column label="⑨多提待查" width="100" align="right">
          <template #header>
            <el-tooltip content="⑨=MAX(⑦−⑥,0)；仅调查，禁止转回" placement="top">
              <span class="formula-header">⑨多提待查</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-cell" :class="{ 'warn-amount': row.overProvision > 0 }">
              {{ fmtAmt(row.overProvision) }}
            </span>
          </template>
        </el-table-column>

        <el-table-column label="索引号" width="110">
          <template #default="{ row, $index }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.indexRef"
              size="small"
              :placeholder="row.needTest ? '须含I1-13' : ''"
              @update:model-value="(v: string) => handleFieldUpdate($index, 'indexRef', v)"
            />
            <span v-else>{{ row.indexRef || '-' }}</span>
          </template>
        </el-table-column>

        <el-table-column prop="conclusion" label="结论" min-width="100" align="center">
          <template #default="{ row, $index }">
            <el-select
              v-if="!isReadonly"
              :model-value="row.conclusion"
              size="small"
              style="width:100%"
              @change="(v: string) => handleFieldUpdate($index, 'conclusion', v)"
            >
              <el-option label="适当" value="适当" />
              <el-option label="需补提" value="需补提" />
              <el-option label="需关注" value="需关注" />
              <el-option label="无需测试" value="无需测试" />
            </el-select>
            <el-tag
              v-else
              :type="row.conclusion === '适当' || row.conclusion === '无需测试' ? 'success' : 'danger'"
              size="small"
            >
              {{ row.conclusion || '待判' }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column v-if="!isReadonly" label="" width="50" align="center" fixed="right">
          <template #default="{ $index }">
            <el-button size="small" type="danger" link @click="handleRemoveRow($index)">✕</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="summary-row" v-if="impairmentRows.length">
        <span class="summary-label">合计</span>
        <span class="summary-item">②账面 <strong>{{ fmtAmt(impairmentSummary.totalBookValue) }}</strong></span>
        <span class="summary-item">⑥应计提 <strong>{{ fmtAmt(impairmentSummary.totalShouldProvision) }}</strong></span>
        <span class="summary-item">⑦已计提 <strong>{{ fmtAmt(impairmentSummary.totalAlreadyProvided) }}</strong></span>
        <span class="summary-item" :class="{ 'error-amount': impairmentSummary.totalSupplement > 0.005 }">
          ⑧应补提 <strong>{{ fmtAmt(impairmentSummary.totalSupplement) }}</strong>
        </span>
        <span class="summary-item" :class="{ 'warn-amount': impairmentSummary.totalOverProvision > 0.005 }">
          ⑨多提待查 <strong>{{ fmtAmt(impairmentSummary.totalOverProvision) }}</strong>
        </span>
      </div>

      <el-alert
        v-if="k11Reconcile.message && k11Reconcile.message !== '尚未核对 K11'"
        :type="k11Reconcile.isMatch ? 'success' : 'error'"
        :closable="false"
        show-icon
        class="result-alert"
        :title="k11Reconcile.message"
      />
      <el-alert
        v-if="impairmentSummary.totalSupplement > 0"
        type="warning"
        :closable="false"
        show-icon
        class="result-alert"
        :title="`应补提减值准备 ${fmtAmt(impairmentSummary.totalSupplement)} 元；保存时已自动推送 K11。请点「切换 I1-11 含减值」后重算摊销。`"
      />
      <el-alert
        v-if="impairmentSummary.totalOverProvision > 0"
        type="error"
        :closable="false"
        show-icon
        class="result-alert"
        :title="`多提待查 ${fmtAmt(impairmentSummary.totalOverProvision)} 元：请查处置结转等原因，禁止做减值转回分录（CAS8）。`"
      />
    </el-card>

    <el-card v-if="categorySummary.length" shadow="never" class="block-card">
      <template #header>
        <div class="section-header"><span class="section-title">按类别汇总（勾稽用）</span></div>
      </template>
      <el-table :data="categorySummary" border size="small" max-height="240">
        <el-table-column prop="category" label="类别" min-width="120" />
        <el-table-column label="②账面价值" align="right" min-width="110">
          <template #default="{ row }">{{ fmtAmt(row.bookValue) }}</template>
        </el-table-column>
        <el-table-column label="⑥应计提" align="right" min-width="100">
          <template #default="{ row }">{{ fmtAmt(row.shouldProvision) }}</template>
        </el-table-column>
        <el-table-column label="⑦已计提" align="right" min-width="100">
          <template #default="{ row }">{{ fmtAmt(row.alreadyProvided) }}</template>
        </el-table-column>
        <el-table-column label="⑧应补提" align="right" min-width="100">
          <template #default="{ row }">
            <span :class="{ 'error-amount': row.supplement > 0 }">{{ fmtAmt(row.supplement) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="section-header"><span>三、审计说明</span></div>
      </template>
      <el-input
        v-model="auditNote"
        type="textarea"
        :autosize="{ minRows: 4, maxRows: 10 }"
        placeholder="填写：减值迹象识别依据、寿命不确定项清单、I1-13 关键与折现率、与 I1-2/I1-11 勾稽、多提待查原因及处理（结转≠转回）…"
        :disabled="isReadonly"
        @blur="saveAuditNote"
      />
    </el-card>

    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="section-header">
          <span>四、审计结论</span>
          <el-button
            size="small"
            plain
            :disabled="isReadonly || needTestGatePending"
            @click="fillConclusionDraft"
          >
            填入结论模板
          </el-button>
          <el-tag v-if="needTestGatePending" size="small" type="danger">须完成 I1-13 后方可定稿</el-tag>
        </div>
      </template>
      <el-input
        v-model="auditConclusion"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="经审计：（1）迹象识别…（2）可收回金额…（3）⑧应补提…（4）⑨多提待查…（5）减值准备在重大方面…"
        :disabled="isReadonly || needTestGatePending"
        @blur="saveAuditConclusion"
      />
    </el-card>

    <div class="jump-targets">
      <span class="jump-label">跨表联动：</span>
      <el-button size="small" link type="primary" @click="navigateToSheet('I1-2')">I1-2 明细</el-button>
      <el-button size="small" link type="primary" @click="navigateToSheet('I1-7')">I1-7 寿命检查</el-button>
      <el-button size="small" link type="primary" @click="navigateToSheet('I1-11')">I1-11 含减值摊销</el-button>
      <el-button size="small" link type="primary" @click="navigateToSheet('I1-13')">I1-13 可收回</el-button>
      <GtIndexChip value="wp:K11" :context-project-id="projectId" />
    </div>

    <details class="edit-tips" open>
      <summary>编制提示与减值迹象清单</summary>
      <ul>
        <li>先「从 I1-2 带入②」，再「从 I1-7 同步寿命」；判定迹象后「建 I1-13」→「回填③④」</li>
        <li>②=原值−累计摊销（不含减值）；⑦取 I1-2 减值期末；保存时⑧自动推送 K11</li>
        <li>有⑧补提时点「切换 I1-11 含减值」并回写减值金额后重算摊销</li>
        <li>⑥=MAX(②−⑤,0)；⑧=MAX(⑥−⑦,0)；⑨&gt;0 只调查不转回；处置结转≠转回</li>
      </ul>
      <p class="indicator-title">资产发生减值的迹象：</p>
      <ol class="indicator-list">
        <li v-for="(t, i) in I1_IMPAIRMENT_INDICATORS" :key="i">{{ t }}</li>
      </ol>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * I1TabImpairmentTest.vue — I1-12 减值准备测试表
 * 对齐 Excel：寿命/迹象闸门 → ②~⑨ → I1-13 回写；CAS8 不得转回拆 ⑧/⑨
 */
import { ref, inject, toRef, computed, onMounted, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  useI1Impairment,
  I1_IMPAIRMENT_INDICATORS,
} from '../../composables/useI1Impairment'
import type { I1ImpairmentTestRow } from '../../composables/useI1Impairment'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate-sheet', sheetName: string): void
  (e: 'save', itemId?: string, value?: any): void
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})

const allResponsesRef = computed(() => props.allResponses)

const {
  impairmentRows,
  impairmentSummary,
  categorySummary,
  prepValidation,
  highlightedRowIds,
  syncChecks,
  staleSyncCount,
  missingRecoverableRows,
  needTestGatePending,
  addImpairmentRow,
  removeImpairmentRow,
  updateImpairmentField,
  seedFromDetail,
  syncFromUsefulLife,
  seedFromImpairment,
  linkRecoverableToImpairment,
  pushToAmortWithImpair,
  switchAmortToWithImpairment,
  publishToK11,
  reconcileWithK11,
  k11Reconcile,
  buildImpairmentConclusionDraft,
  assertCanConclude,
  exportImpairmentXlsx,
  importImpairmentXlsx,
} = useI1Impairment(
  toRef(props, 'wpId'),
  allResponsesRef as any,
  {
    onSave: (itemId: string, value: any) => emit('save', itemId, value),
  },
)

const ieBusy = ref(false)
const fileInputRef = ref<HTMLInputElement | null>(null)

function syncStatusLabel(status: string): string {
  switch (status) {
    case 'synced': return '一致'
    case 'stale': return '不一致'
    case 'missing-i13': return '缺测算'
    case 'no-test': return '无须测'
    default: return status
  }
}

const categoryOptions = [
  '土地使用权', '房屋使用权', '专利权', '非专利技术', '商标权',
  '著作权', '特许权', '软件', '探矿权/采矿权', '数据资源', '其他',
]

const auditNote = ref('')
const auditConclusion = ref('')

const NOTE_KEY = 'I1-12-audit-note'
const CONCLUSION_KEY = 'I1-12-audit-conclusion'

function loadAuditText(): void {
  const n = props.allResponses.get(NOTE_KEY)
  if (n) auditNote.value = (n.remark ?? n.conclusion ?? '') as string
  const c = props.allResponses.get(CONCLUSION_KEY)
  if (c) auditConclusion.value = (c.remark ?? c.conclusion ?? '') as string
}

onMounted(loadAuditText)
watch(() => props.allResponses, loadAuditText, { deep: true })

function saveAuditNote(): void {
  if (props.isReadonly) return
  emit('save', NOTE_KEY, auditNote.value)
}

function saveAuditConclusion(): void {
  if (props.isReadonly) return
  const gate = assertCanConclude()
  if (!gate.ok) {
    ElMessage.error(gate.message)
    return
  }
  emit('save', CONCLUSION_KEY, auditConclusion.value)
}

function fillConclusionDraft(): void {
  const gate = assertCanConclude()
  if (!gate.ok) {
    ElMessage.error(gate.message)
    return
  }
  auditConclusion.value = buildImpairmentConclusionDraft()
  saveAuditConclusion()
  ElMessage.success('已填入结论模板')
}

function getRowClassName({ row }: { row: I1ImpairmentTestRow }): string {
  if (highlightedRowIds.value.has(row.rowId)) return 'row-highlight-danger'
  return ''
}

function getSummary({ columns, data }: { columns: any[]; data: I1ImpairmentTestRow[] }) {
  const sums: string[] = []
  columns.forEach((col, index) => {
    if (index === 0) {
      sums[index] = '合'
      return
    }
    const prop = col.property
    const map: Record<string, keyof typeof impairmentSummary.value> = {
      bookValue: 'totalBookValue',
      fairValueLessDisposal: 'totalFairValue',
      dcfValue: 'totalDcf',
      recoverableAmount: 'totalRecoverable',
      shouldProvision: 'totalShouldProvision',
      alreadyProvided: 'totalAlreadyProvided',
      supplement: 'totalSupplement',
      overProvision: 'totalOverProvision',
    }
    // 无 property 时按 label 粗匹配
    const label = String(col.label || '')
    let key = prop ? map[prop] : undefined
    if (!key) {
      if (label.includes('②')) key = 'totalBookValue'
      else if (label.includes('③')) key = 'totalFairValue'
      else if (label.includes('④')) key = 'totalDcf'
      else if (label.includes('⑤')) key = 'totalRecoverable'
      else if (label.includes('⑥')) key = 'totalShouldProvision'
      else if (label.includes('⑦')) key = 'totalAlreadyProvided'
      else if (label.includes('⑧')) key = 'totalSupplement'
      else if (label.includes('⑨')) key = 'totalOverProvision'
    }
    if (key) {
      sums[index] = fmtAmt(impairmentSummary.value[key])
    } else {
      sums[index] = index === 1 ? `共${data.length}行` : ''
    }
  })
  return sums
}

function handleFieldUpdate(index: number, field: string, value: any) {
  updateImpairmentField(index, field as any, value)
}

async function handleAddRow() {
  try {
    const { value: name } = await ElMessageBox.prompt('请输入资产名称', '新增减值测试行', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputPattern: /\S+/,
      inputErrorMessage: '资产名称不能为空',
    })
    if (name) addImpairmentRow({ name: name.trim() })
  } catch { /* cancelled */ }
}

function handleRemoveRow(index: number) {
  removeImpairmentRow(index)
}

function handleSeedFromDetail() {
  const r = seedFromDetail()
  ElMessage({ type: r.ok ? 'success' : 'warning', message: r.message })
}

function handleSyncFromI17() {
  const r = syncFromUsefulLife()
  ElMessage({ type: r.ok ? 'success' : 'warning', message: r.message })
}

function handleSeedI13() {
  const r = seedFromImpairment()
  ElMessage({ type: r.ok ? 'success' : 'warning', message: r.message })
  if (r.ok) navigateToSheet('I1-13')
}

function handleLinkFromI13() {
  const r = linkRecoverableToImpairment()
  ElMessage({ type: r.ok ? 'success' : 'warning', message: r.message })
}

function handlePushToI111() {
  const r = pushToAmortWithImpair({ createMissing: true })
  ElMessage({ type: r.ok ? 'success' : 'warning', message: r.message })
  if (r.ok) navigateToSheet('I1-11')
}

function handleSwitchI111() {
  const r = switchAmortToWithImpairment({ alsoPushRows: true })
  ElMessage({ type: r.ok ? 'success' : 'warning', message: r.message })
  if (r.ok) navigateToSheet('I1-11')
}

function handlePublishK11() {
  publishToK11()
  ElMessage.success(`已推送本期补提⑧ ${fmtAmt(impairmentSummary.value.totalSupplement)} 至 K11`)
}

async function handleReconcileK11() {
  const r = await reconcileWithK11(props.projectId)
  ElMessage({ type: r.isMatch ? 'success' : 'warning', message: r.message })
}

function navigateToSheet(code: string) {
  emit('navigate-sheet', code)
}

async function handleExportImport(command: string) {
  ieBusy.value = true
  try {
    if (command === 'export-template') {
      await exportImpairmentXlsx('template')
      ElMessage.success('已导出模板')
    } else if (command === 'export-data') {
      await exportImpairmentXlsx('data')
      ElMessage.success('已导出数据')
    } else if (command === 'import-data') {
      fileInputRef.value?.click()
    }
  } catch (e: any) {
    ElMessage.error(e?.message || '导入导出失败')
  } finally {
    ieBusy.value = false
  }
}

async function onFileSelected(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  ;(e.target as HTMLInputElement).value = ''
  if (!file) return
  try {
    await ElMessageBox.confirm(
      `即将导入「${file.name}」到 I1-12，已有测算行将被覆盖。确认？`,
      '导入确认',
      { type: 'warning' },
    )
  } catch {
    return
  }
  ieBusy.value = true
  try {
    const r = await importImpairmentXlsx(file, true)
    ElMessage.success(`已导入 ${r.imported} 行`)
  } catch (err: any) {
    ElMessage.error(err?.message || '导入失败')
  } finally {
    ieBusy.value = false
  }
}

function openReview(id: string) {
  openReviewDialog(id)
}

function ynLabel(v: string): string {
  if (v === 'Y') return '是'
  if (v === 'N') return '否'
  return '—'
}

function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.i1-tab-impairment-test { padding: 16px; font-size: var(--wp-font-size, 13px); }

.methodology-block {
  border-left: 4px solid var(--el-color-warning);
  background: #fffbeb;
  padding: 12px 16px;
  margin-bottom: 16px;
  font-size: 12px;
  color: var(--el-text-color-regular);
  line-height: 1.6;
}
.methodology-note { margin: 8px 0 0; color: var(--el-text-color-secondary); }

.objective-alert { margin-bottom: 12px; }
.mb-8 { margin-bottom: 8px; }
.result-alert { margin-top: 8px; }

.tab-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  flex-wrap: wrap;
  gap: 8px;
}
.tab-toolbar .toolbar-left,
.tab-toolbar .toolbar-right { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
.chip-wrap { display: inline-flex; align-items: center; }

.block-card { margin-bottom: 16px; }
.section-header { display: flex; align-items: center; justify-content: space-between; gap: 8px; flex-wrap: wrap; }
.section-title { font-weight: 600; }
.section-header-actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }

.impairment-table { font-size: var(--wp-font-size, 13px); }
.amt-cell { font-variant-numeric: tabular-nums; }
.amt-input { width: 100%; }

.formula-header {
  border-bottom: 1px dashed var(--el-border-color);
  cursor: help;
}
.formula-cell {
  border-bottom: 1px dashed var(--el-border-color);
  cursor: help;
  font-variant-numeric: tabular-nums;
}

.error-amount { color: var(--el-color-danger); font-weight: 600; }
.warn-amount { color: var(--el-color-warning); font-weight: 600; }
:deep(.row-highlight-danger) { background-color: #fef0f0 !important; }
:deep(.row-highlight-danger td) { background-color: #fef0f0 !important; }

.recoverable-cell {
  display: flex;
  align-items: center;
  gap: 4px;
  justify-content: flex-end;
}

.summary-row {
  padding: 12px 0;
  font-size: var(--wp-font-size, 13px);
  border-top: 2px solid var(--el-border-color);
  margin-top: 12px;
  display: flex;
  gap: 20px;
  flex-wrap: wrap;
  align-items: center;
}
.summary-label { font-weight: 700; min-width: 40px; }
.summary-item { font-variant-numeric: tabular-nums; }

.audit-note-card { margin-bottom: 12px; }

.jump-targets {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-wrap: wrap;
  margin: 8px 0 12px;
}
.jump-label { font-size: 12px; color: var(--el-text-color-secondary); }

.edit-tips { margin-top: 8px; font-size: 12px; color: var(--el-text-color-secondary); }
.edit-tips summary { cursor: pointer; font-weight: 500; }
.edit-tips ul { padding-left: 20px; margin-top: 8px; line-height: 1.8; }
.indicator-title { margin: 12px 0 4px; font-weight: 600; color: var(--el-text-color-regular); }
.indicator-list { padding-left: 20px; margin: 0; line-height: 1.7; }
</style>
