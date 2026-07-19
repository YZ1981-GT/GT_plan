<template>
  <div class="g6-tab-ecl-measurement" data-testid="g6-ecl-measurement">
    <el-alert type="info" :closable="false" show-icon class="objective-alert">
      <template #title>
        审计目标：评价企业预期信用损失计量方法是否适当；是否反映无偏概率加权、货币时间价值，以及无需付出不当成本或努力即可获取的合理且有依据的信息（含前瞻性信息）。
      </template>
    </el-alert>

    <div class="methodology-context">
      <p class="methodology-title">编制逻辑（对齐 Excel G6-13）：</p>
      <p>① 评价计量方法与组合划分 → ② PD/LGD 或损失率法抽样测算 → ③ 回写 G6-12 损失率</p>
      <p>PD/LGD：ECL率 = 期限折算PD × LGD（Stage1 展望期封顶 12 个月）；损失率法：ECL率 = 损失率 + 前瞻性调整</p>
    </div>

    <div class="flow-hint">
      <el-tag size="small" type="info" effect="plain">G6-11 三阶段</el-tag>
      <span class="flow-arrow">→</span>
      <el-tag size="small" type="warning" effect="dark">G6-13 计量测试（本表）</el-tag>
      <span class="flow-arrow">→</span>
      <el-tag size="small" type="success" effect="plain">G6-12 减值测算</el-tag>
    </div>

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <span class="chip-wrap"><GtIndexChip value="wp:G6-13" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:G6-12" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:G6-11" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">
          PD/LGD {{ pdLgdRows.length }} · 损失率法 {{ lossRateRows.length }}
        </el-tag>
        <G6EclImportExportDropdown
          :wp-id="wpId"
          sheet="G6-13"
          :disabled="isReadonly"
          @imported="onImported"
        />
        <el-button size="small" :disabled="isReadonly" :loading="pulling" @click="pullFromG611">
          从 G6-11 拉取项目
        </el-button>
        <el-button
          size="small"
          type="primary"
          plain
          :disabled="isReadonly"
          :loading="pushing"
          @click="syncRatesToG612"
        >
          回写损失率至 G6-12
        </el-button>
      </div>
      <div class="toolbar-right">
        <el-button
          size="small"
          :disabled="isReadonly || !aiAvailable"
          :loading="aiLoading"
          @click="handleAi"
        >🤖 AI</el-button>
        <el-button size="small" @click="openReview('G6-13-ecl-measurement')">💬复核</el-button>
      </div>
    </div>

    <!-- (一) 方法评价 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="section-header">
          <span class="section-title">(一) ECL计量方法评价</span>
        </div>
      </template>
      <el-table :data="methodEvaluation" border size="small">
        <el-table-column label="检查项目" prop="checkItem" min-width="120" />
        <el-table-column label="检查内容" prop="checkContent" min-width="200" />
        <el-table-column label="企业采用方法" min-width="160">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.companyMethod"
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 3 }"
              @update:model-value="(v: string) => { row.companyMethod = v; saveAll() }"
            />
            <span v-else>{{ row.companyMethod || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审计评价" width="120" align="center">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              :model-value="row.auditEvaluation"
              size="small"
              style="width: 100%"
              @change="(v: string) => { row.auditEvaluation = v as any; saveAll() }"
            >
              <el-option value="合理" label="合理" />
              <el-option value="基本合理" label="基本合理" />
              <el-option value="不合理" label="不合理" />
            </el-select>
            <span v-else>{{ row.auditEvaluation || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="说明" min-width="120">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.note"
              size="small"
              @update:model-value="(v: string) => { row.note = v; saveAll() }"
            />
            <span v-else>{{ row.note || '-' }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- (二) 组合依据 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="section-header">
          <span class="section-title">(二) 确定组合的依据</span>
          <el-button v-if="!isReadonly" size="small" type="primary" @click="addGroupBasis">+ 组合</el-button>
        </div>
      </template>
      <el-table :data="groupBasis" border size="small">
        <el-table-column label="组合名称" min-width="120">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.groupName"
              size="small"
              @change="(v: string) => { row.groupName = v; saveAll() }"
            />
            <span v-else>{{ row.groupName }}</span>
          </template>
        </el-table-column>
        <el-table-column label="划分依据" min-width="160">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.basis"
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 3 }"
              @update:model-value="(v: string) => { row.basis = v; saveAll() }"
            />
            <span v-else>{{ row.basis || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="共同风险特征" min-width="140">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.riskCharacteristic"
              size="small"
              @change="(v: string) => { row.riskCharacteristic = v; saveAll() }"
            />
            <span v-else>{{ row.riskCharacteristic || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="样本量" width="90" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.sampleSize"
              size="small"
              :controls="false"
              class="amt"
              @change="(v: number | undefined) => { row.sampleSize = v ?? 0; saveAll() }"
            />
            <span v-else>{{ row.sampleSize }}</span>
          </template>
        </el-table-column>
        <el-table-column label="评价" width="100" align="center">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              :model-value="row.auditEvaluation"
              size="small"
              style="width: 100%"
              @change="(v: string) => { row.auditEvaluation = v as any; saveAll() }"
            >
              <el-option value="合理" label="合理" />
              <el-option value="不合理" label="不合理" />
            </el-select>
            <span v-else>{{ row.auditEvaluation || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="" width="50" align="center">
          <template #default="{ $index }">
            <el-button link type="danger" size="small" @click="groupBasis.splice($index, 1); saveAll()">删</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!groupBasis.length" description="请新增组合并说明划分依据" :image-size="48" />
    </el-card>

    <!-- (三) 双路径测算 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="section-header">
          <span class="section-title">(三) 单项/组合计提的预期信用损失率</span>
          <el-segmented v-model="rateTab" :options="rateTabOptions" size="small" />
        </div>
      </template>

      <!-- PD/LGD -->
      <div v-show="rateTab === 'pdLgd'">
        <div class="sub-toolbar">
          <el-tag size="small" type="warning">【方法可选】PD/LGD</el-tag>
          <el-tag v-if="pdLgdVarianceCount > 0" size="small" type="danger">
            {{ pdLgdVarianceCount }} 项与上期差异&gt;2%
          </el-tag>
          <el-button v-if="!isReadonly" size="small" type="primary" @click="addPdLgdRow">+ 行</el-button>
        </div>
        <el-table :data="pdLgdRows" border size="small" show-summary :summary-method="pdLgdSummary">
          <el-table-column label="投资项目/组合" min-width="130">
            <template #default="{ row }">
              <el-input
                v-if="!isReadonly"
                :model-value="row.projectName"
                size="small"
                @change="(v: string) => { row.projectName = v; saveAll() }"
              />
              <span v-else>{{ row.projectName }}</span>
            </template>
          </el-table-column>
          <el-table-column label="账面余额" min-width="110" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="!isReadonly"
                :model-value="row.bookBalance"
                size="small"
                :controls="false"
                class="amt"
                @change="(v: number | undefined) => { row.bookBalance = v ?? 0; recomputePdLgd(row); saveAll() }"
              />
              <span v-else>{{ fmtNum(row.bookBalance) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="剩余月数" width="90" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="!isReadonly"
                :model-value="row.remainingMonths"
                size="small"
                :controls="false"
                :precision="0"
                class="amt"
                @change="(v: number | undefined) => { row.remainingMonths = v ?? 0; recomputePdLgd(row, true); saveAll() }"
              />
              <span v-else>{{ row.remainingMonths }}</span>
            </template>
          </el-table-column>
          <el-table-column label="阶段" width="100" align="center">
            <template #default="{ row }">
              <el-select
                v-if="!isReadonly"
                :model-value="row.stage"
                size="small"
                clearable
                style="width: 100%"
                @change="(v: string) => { row.stage = v as any; recomputePdLgd(row, true); saveAll() }"
              >
                <el-option value="Stage1" label="Stage1" />
                <el-option value="Stage2" label="Stage2" />
                <el-option value="Stage3" label="Stage3" />
              </el-select>
              <span v-else>{{ row.stage || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="评级" width="100" align="center">
            <template #default="{ row }">
              <el-select
                v-if="!isReadonly"
                :model-value="row.rating"
                size="small"
                filterable
                allow-create
                style="width: 100%"
                @change="(v: string) => onRatingChange(row, v)"
              >
                <el-option v-for="r in ratingOptions" :key="r" :value="r" :label="r" />
              </el-select>
              <span v-else>{{ row.rating || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="外部映射违约率" min-width="120" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="!isReadonly"
                :model-value="row.externalMappedPd"
                size="small"
                :controls="false"
                :precision="6"
                class="amt"
                @change="(v: number | undefined) => { row.externalMappedPd = v ?? 0; recomputePdLgd(row, true); saveAll() }"
              />
              <span v-else>{{ fmtPct(row.externalMappedPd, 4) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="期限折算PD" min-width="110" align="right">
            <template #default="{ row }">
              <el-tooltip content="1−(1−一年期PD)^(月数/12)；可覆写">
                <el-input-number
                  v-if="!isReadonly"
                  :model-value="row.termAdjustedPd"
                  size="small"
                  :controls="false"
                  :precision="6"
                  class="amt"
                  @change="(v: number | undefined) => { row.termAdjustedPd = v ?? 0; recomputePdLgd(row, false); saveAll() }"
                />
                <span v-else class="formula-cell">{{ fmtPct(row.termAdjustedPd, 4) }}</span>
              </el-tooltip>
            </template>
          </el-table-column>
          <el-table-column label="LGD" width="90" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="!isReadonly"
                :model-value="row.lgd"
                size="small"
                :controls="false"
                :precision="4"
                class="amt"
                @change="(v: number | undefined) => { row.lgd = v ?? 0; recomputePdLgd(row, false); saveAll() }"
              />
              <span v-else>{{ fmtPct(row.lgd) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="预期信用损失率" min-width="120" align="right">
            <template #default="{ row }">
              <el-tooltip content="ECL率 = PD × LGD">
                <span class="formula-cell" :class="{ 'rate-warn': isRateVarianceHigh(row.eclRate, row.priorHistoricalLossRate) }">
                  {{ fmtPct(row.eclRate) }}
                </span>
              </el-tooltip>
            </template>
          </el-table-column>
          <el-table-column label="预期信用损失" min-width="110" align="right">
            <template #default="{ row }">
              <el-tooltip content="ECL = 账面余额 × ECL率">
                <span class="formula-cell">{{ fmtNum(row.eclAmount) }}</span>
              </el-tooltip>
            </template>
          </el-table-column>
          <el-table-column label="上期历史损失率" min-width="120" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="!isReadonly"
                :model-value="row.priorHistoricalLossRate"
                size="small"
                :controls="false"
                :precision="4"
                class="amt"
                @change="(v: number | undefined) => { row.priorHistoricalLossRate = v ?? 0; saveAll() }"
              />
              <span v-else>{{ fmtPct(row.priorHistoricalLossRate) }}</span>
            </template>
          </el-table-column>
          <el-table-column v-if="!isReadonly" label="" width="50" align="center">
            <template #default="{ $index }">
              <el-button link type="danger" size="small" @click="pdLgdRows.splice($index, 1); saveAll()">删</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <!-- 损失率法 -->
      <div v-show="rateTab === 'lossRate'">
        <div class="sub-toolbar">
          <el-tag size="small" type="warning">【方法可选】损失率法</el-tag>
          <el-tag v-if="lossRateVarianceCount > 0" size="small" type="danger">
            {{ lossRateVarianceCount }} 项与上期差异&gt;2%
          </el-tag>
          <el-button v-if="!isReadonly" size="small" type="primary" @click="addLossRateRow">+ 行</el-button>
        </div>
        <el-table :data="lossRateRows" border size="small" show-summary :summary-method="lossRateSummary">
          <el-table-column label="投资项目/组合" min-width="130">
            <template #default="{ row }">
              <el-input
                v-if="!isReadonly"
                :model-value="row.projectName"
                size="small"
                @change="(v: string) => { row.projectName = v; saveAll() }"
              />
              <span v-else>{{ row.projectName }}</span>
            </template>
          </el-table-column>
          <el-table-column label="账面余额" min-width="110" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="!isReadonly"
                :model-value="row.bookBalance"
                size="small"
                :controls="false"
                class="amt"
                @change="(v: number | undefined) => { row.bookBalance = v ?? 0; recomputeLossRate(row); saveAll() }"
              />
              <span v-else>{{ fmtNum(row.bookBalance) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="剩余月数" width="90" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="!isReadonly"
                :model-value="row.remainingMonths"
                size="small"
                :controls="false"
                :precision="0"
                class="amt"
                @change="(v: number | undefined) => { row.remainingMonths = v ?? 0; saveAll() }"
              />
              <span v-else>{{ row.remainingMonths }}</span>
            </template>
          </el-table-column>
          <el-table-column label="阶段" width="100" align="center">
            <template #default="{ row }">
              <el-select
                v-if="!isReadonly"
                :model-value="row.stage"
                size="small"
                clearable
                style="width: 100%"
                @change="(v: string) => { row.stage = v as any; saveAll() }"
              >
                <el-option value="Stage1" label="Stage1" />
                <el-option value="Stage2" label="Stage2" />
                <el-option value="Stage3" label="Stage3" />
              </el-select>
              <span v-else>{{ row.stage || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="评级" width="90" align="center">
            <template #default="{ row }">
              <el-input
                v-if="!isReadonly"
                :model-value="row.rating"
                size="small"
                @change="(v: string) => { row.rating = v; saveAll() }"
              />
              <span v-else>{{ row.rating || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="损失率" width="100" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="!isReadonly"
                :model-value="row.lossRate"
                size="small"
                :controls="false"
                :precision="4"
                class="amt"
                @change="(v: number | undefined) => { row.lossRate = v ?? 0; recomputeLossRate(row); saveAll() }"
              />
              <span v-else>{{ fmtPct(row.lossRate) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="说明" min-width="120">
            <template #default="{ row }">
              <el-input
                v-if="!isReadonly"
                :model-value="row.description"
                size="small"
                @change="(v: string) => { row.description = v; saveAll() }"
              />
              <span v-else>{{ row.description || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="前瞻性调整" min-width="110" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="!isReadonly"
                :model-value="row.forwardLookingAdj"
                size="small"
                :controls="false"
                :precision="4"
                class="amt"
                @change="(v: number | undefined) => { row.forwardLookingAdj = v ?? 0; recomputeLossRate(row); saveAll() }"
              />
              <span v-else>{{ fmtPct(row.forwardLookingAdj) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="预期信用损失率" min-width="120" align="right">
            <template #default="{ row }">
              <el-tooltip content="ECL率 = 损失率 + 前瞻性调整">
                <span class="formula-cell" :class="{ 'rate-warn': isRateVarianceHigh(row.eclRate, row.priorHistoricalLossRate) }">
                  {{ fmtPct(row.eclRate) }}
                </span>
              </el-tooltip>
            </template>
          </el-table-column>
          <el-table-column label="预期信用损失" min-width="110" align="right">
            <template #default="{ row }">
              <span class="formula-cell">{{ fmtNum(row.eclAmount) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="上期历史损失率" min-width="120" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="!isReadonly"
                :model-value="row.priorHistoricalLossRate"
                size="small"
                :controls="false"
                :precision="4"
                class="amt"
                @change="(v: number | undefined) => { row.priorHistoricalLossRate = v ?? 0; saveAll() }"
              />
              <span v-else>{{ fmtPct(row.priorHistoricalLossRate) }}</span>
            </template>
          </el-table-column>
          <el-table-column v-if="!isReadonly" label="" width="50" align="center">
            <template #default="{ $index }">
              <el-button link type="danger" size="small" @click="lossRateRows.splice($index, 1); saveAll()">删</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </el-card>

    <!-- 参数评价（精简） -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="section-header"><span class="section-title">(四) 关键参数评价</span></div>
      </template>
      <el-table :data="parameterEvaluation" border size="small">
        <el-table-column label="参数" prop="paramName" width="140" />
        <el-table-column label="数据来源" min-width="140">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.dataSource"
              size="small"
              @change="(v: string) => { row.dataSource = v; saveAll() }"
            />
            <span v-else>{{ row.dataSource || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="估计方法" min-width="160" prop="calcMethod" />
        <el-table-column label="验证结果" min-width="140">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.verificationResult"
              size="small"
              @change="(v: string) => { row.verificationResult = v; saveAll() }"
            />
            <span v-else>{{ row.verificationResult || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="评价" width="120" align="center">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              :model-value="row.auditEvaluation"
              size="small"
              style="width: 100%"
              @change="(v: string) => { row.auditEvaluation = v as any; saveAll() }"
            >
              <el-option value="合理" label="合理" />
              <el-option value="基本合理" label="基本合理" />
              <el-option value="不合理" label="不合理" />
            </el-select>
            <span v-else>{{ row.auditEvaluation || '-' }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card shadow="never" class="section-card">
      <template #header><div class="section-header"><span class="section-title">审计说明</span></div></template>
      <el-input
        type="textarea"
        :model-value="auditNote"
        :disabled="isReadonly"
        :autosize="{ minRows: 4 }"
        placeholder="概述方法评价、组合划分、抽样测算及与上期损失率差异原因。"
        @update:model-value="saveAuditNote"
      />
    </el-card>

    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="section-header">
          <span class="section-title">审计结论</span>
          <el-button size="small" :disabled="isReadonly || !aiAvailable" :loading="aiLoading" @click="handleAi">🤖 AI</el-button>
        </div>
      </template>
      <el-input
        v-model="conclusion"
        type="textarea"
        :disabled="isReadonly"
        :autosize="{ minRows: 3 }"
        placeholder="A、计量方法适当、参数合理。B、除下述事项外未见异常。C、存在重大不当事项须调整。"
        @change="saveAll"
      />
    </el-card>

    <details class="guide-details">
      <summary>编制提示</summary>
      <div class="guide-content">
        <p>1. 比率按小数录入（1%=0.01）；ECL率/金额为公式列。</p>
        <p>2. PD/LGD：ECL率=期限折算PD×LGD；损失率法：ECL率=损失率+前瞻调整。</p>
        <p>3. 评级下拉可带出参考一年期PD（示例映射，须替换为当期数据）。</p>
        <p>4. 「回写损失率至 G6-12」按项目名匹配写入②信用损失率（默认跳过 Stage3）。</p>
        <p>5. 与上期历史损失率差异&gt;2% 橙色高亮，须在说明中解释。</p>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * G6TabEclMeasurement.vue — 对齐 Excel《预期信用损失的计量测试G6-13》
 */
import { ref, computed, inject, onMounted, onBeforeUnmount, watch } from 'vue'
import { ElMessage } from 'element-plus'
import type { SummaryMethod } from 'element-plus'
import {
  useG6EclFormData,
  type MethodEvalRow,
  type GroupBasisRow,
  type ParameterEvalRow,
  type PdLgdCalcRow,
  type LossRateCalcRow,
  type EclMeasurementData,
} from '../../composables/useG6EclFormData'
import {
  useG6EclImpairmentCalc,
  collectEclRateUpdates,
} from '../../composables/useG6EclImpairmentCalc'
import { useG6EclAiGenerate } from '../../composables/useG6EclAiGenerate'
import {
  parseG6ChecklistRows,
  parseG6ChecklistPayload,
  G6_11_ROWS_KEY,
  G6_ECL_RATE_UPDATED_EVENT,
} from '../../composables/g6CrossHelpers'
import {
  G4_ECL_RATING_OPTIONS,
  lookupAnnualPdByRating,
} from '../../composables/g4EclRatingPdMap'
import {
  calcTermAdjustedPd,
  calcEclRateFromPdLgd,
  calcEclRateFromLossRate,
  calcImpairmentProvision,
  calcLossRateVariance,
  parseNum,
} from '@/composables/useG6EclFormulaEngine'
import GtIndexChip from '../../GtIndexChip.vue'
import G6EclImportExportDropdown from '../G6EclImportExportDropdown.vue'

const props = defineProps<{
  htmlData: Record<string, any> | null
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const emit = defineEmits<{ imported: [] }>()

const VARIANCE_THRESHOLD = 0.02
const DATA_KEY = 'G6-13-ecl-measurement'
const NOTE_KEY = 'G6-13-ecl-measurement-audit-note'
const G612_KEY = 'G6-12-impairment-calc-data'

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})
function openReview(id: string) { openReviewDialog(id) }

const wpIdRef = computed(() => props.wpId)
const isReadonly = computed(() => props.isReadonly)
const { generateAndConfirm, aiAvailable, loading: aiLoading } = useG6EclAiGenerate(wpIdRef)
const formData = useG6EclFormData({
  wpId: wpIdRef,
  projectId: computed(() => props.projectId),
})
const impairmentBridge = useG6EclImpairmentCalc()

const ratingOptions = G4_ECL_RATING_OPTIONS
const rateTab = ref<'pdLgd' | 'lossRate'>('pdLgd')
const rateTabOptions = [
  { label: '1、PD/LGD法', value: 'pdLgd' },
  { label: '2、损失率法', value: 'lossRate' },
]

const DEFAULT_METHOD: MethodEvalRow[] = [
  { id: 'me-1', checkItem: 'ECL计量方法选择', checkContent: '是否根据金融资产特征选择合适方法（单项/组合；PD/LGD或损失率法）', companyMethod: '', auditEvaluation: '合理', note: '' },
  { id: 'me-2', checkItem: '无偏概率加权', checkContent: '计量是否反映通过评价一系列可能结果而确定的无偏概率加权平均金额', companyMethod: '', auditEvaluation: '合理', note: '' },
  { id: 'me-3', checkItem: '货币时间价值', checkContent: '是否按实际利率（或近似利率）将预期现金短缺折现至报告日', companyMethod: '', auditEvaluation: '合理', note: '' },
  { id: 'me-4', checkItem: '前瞻性信息运用', checkContent: '是否合理考虑过去事项、当前状况及对未来经济状况的预测', companyMethod: '', auditEvaluation: '合理', note: '' },
  { id: 'me-5', checkItem: '模型验证与数据质量', checkContent: '是否定期回测，历史违约/回收等基础数据是否完整、准确', companyMethod: '', auditEvaluation: '合理', note: '' },
]

const DEFAULT_PARAMS: ParameterEvalRow[] = [
  { id: 'pe-pd', paramName: 'PD（违约概率）', dataSource: '', calcMethod: '外部评级映射 / 迁移矩阵 / 剩余期限折算', verificationResult: '', auditEvaluation: '合理', note: '' },
  { id: 'pe-lgd', paramName: 'LGD（违约损失率）', dataSource: '', calcMethod: '历史回收率 / 担保覆盖 / 行业基准', verificationResult: '', auditEvaluation: '合理', note: '' },
  { id: 'pe-ead', paramName: 'EAD（违约风险敞口）', dataSource: '', calcMethod: '一般等于账面信用敞口', verificationResult: '', auditEvaluation: '合理', note: '' },
]

const methodEvaluation = ref<MethodEvalRow[]>([...DEFAULT_METHOD])
const groupBasis = ref<GroupBasisRow[]>([])
const parameterEvaluation = ref<ParameterEvalRow[]>([...DEFAULT_PARAMS])
const pdLgdRows = ref<PdLgdCalcRow[]>([])
const lossRateRows = ref<LossRateCalcRow[]>([])
const conclusion = ref('')
const auditNote = ref('')
const pulling = ref(false)
const pushing = ref(false)

function emptyPdLgd(name = '', stableId = ''): PdLgdCalcRow {
  const id = stableId || `pd-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`
  return {
    id,
    crossSheetInvestmentId: id,
    projectName: name,
    bookBalance: 0,
    remainingMonths: 12,
    stage: '',
    rating: '',
    externalMappedPd: 0,
    termAdjustedPd: 0,
    lgd: 0.45,
    eclRate: 0,
    eclAmount: 0,
    priorHistoricalLossRate: 0,
    note: '',
  }
}

function emptyLossRate(name = '', stableId = ''): LossRateCalcRow {
  const id = stableId || `lr-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`
  return {
    id,
    crossSheetInvestmentId: id,
    projectName: name,
    bookBalance: 0,
    remainingMonths: 12,
    stage: '',
    rating: '',
    lossRate: 0,
    description: '',
    forwardLookingAdj: 0,
    eclRate: 0,
    eclAmount: 0,
    priorHistoricalLossRate: 0,
    note: '',
  }
}

function recomputePdLgd(row: PdLgdCalcRow, autoTermPd = true): void {
  if (autoTermPd) {
    row.termAdjustedPd = calcTermAdjustedPd(row.externalMappedPd, row.remainingMonths, row.stage)
  }
  row.eclRate = calcEclRateFromPdLgd(row.termAdjustedPd, row.lgd)
  row.eclAmount = calcImpairmentProvision(row.bookBalance, row.eclRate)
}

function recomputeLossRate(row: LossRateCalcRow): void {
  row.eclRate = calcEclRateFromLossRate(row.lossRate, row.forwardLookingAdj)
  row.eclAmount = calcImpairmentProvision(row.bookBalance, row.eclRate)
}

function onRatingChange(row: PdLgdCalcRow, rating: string): void {
  row.rating = rating
  const pd = lookupAnnualPdByRating(rating)
  if (pd != null) {
    row.externalMappedPd = pd
    recomputePdLgd(row, true)
  }
  saveAll()
}

function isRateVarianceHigh(eclRate: number, prior: number): boolean {
  if (parseNum(prior) === 0 && parseNum(eclRate) === 0) return false
  return calcLossRateVariance(eclRate, prior) > VARIANCE_THRESHOLD
}

const pdLgdVarianceCount = computed(() =>
  pdLgdRows.value.filter(r => isRateVarianceHigh(r.eclRate, r.priorHistoricalLossRate)).length,
)
const lossRateVarianceCount = computed(() =>
  lossRateRows.value.filter(r => isRateVarianceHigh(r.eclRate, r.priorHistoricalLossRate)).length,
)

function addGroupBasis(): void {
  groupBasis.value.push({
    id: `gb-${Date.now()}`,
    groupName: `组合${groupBasis.value.length + 1}`,
    basis: '',
    riskCharacteristic: '',
    sampleSize: 0,
    auditEvaluation: '',
    note: '',
  })
  saveAll()
}

function addPdLgdRow(): void {
  const row = emptyPdLgd()
  recomputePdLgd(row)
  pdLgdRows.value.push(row)
  saveAll()
}

function addLossRateRow(): void {
  const row = emptyLossRate()
  recomputeLossRate(row)
  lossRateRows.value.push(row)
  saveAll()
}

function fmtNum(n: number): string {
  const v = parseNum(n)
  if (Math.abs(v) < 1e-9) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtPct(n: number, digits = 2): string {
  return `${(parseNum(n) * 100).toFixed(digits)}%`
}

const pdLgdSummary: SummaryMethod<PdLgdCalcRow> = ({ columns, data }) => {
  const sums: string[] = []
  columns.forEach((col, i) => {
    if (i === 0) { sums[i] = '合计'; return }
    const prop = col.property
    if (prop === 'bookBalance' || col.label === '账面余额') {
      sums[i] = fmtNum(data.reduce((s, r) => s + parseNum(r.bookBalance), 0))
    } else if (col.label === '预期信用损失') {
      sums[i] = fmtNum(data.reduce((s, r) => s + parseNum(r.eclAmount), 0))
    } else sums[i] = ''
  })
  return sums
}

const lossRateSummary: SummaryMethod<LossRateCalcRow> = ({ columns, data }) => {
  const sums: string[] = []
  columns.forEach((col, i) => {
    if (i === 0) { sums[i] = '合计'; return }
    if (col.label === '账面余额') {
      sums[i] = fmtNum(data.reduce((s, r) => s + parseNum(r.bookBalance), 0))
    } else if (col.label === '预期信用损失') {
      sums[i] = fmtNum(data.reduce((s, r) => s + parseNum(r.eclAmount), 0))
    } else sums[i] = ''
  })
  return sums
}

function buildPayload(): EclMeasurementData {
  return {
    schemaVersion: 2,
    methodEvaluation: methodEvaluation.value,
    groupBasis: groupBasis.value,
    parameterEvaluation: parameterEvaluation.value,
    pdLgdRows: pdLgdRows.value,
    lossRateRows: lossRateRows.value,
    conclusion: conclusion.value,
  }
}

function saveAll(): void {
  if (props.isReadonly) return
  formData.debouncedSave(DATA_KEY, { conclusion: JSON.stringify(buildPayload()) })
}

function saveAuditNote(val: string): void {
  if (props.isReadonly) return
  auditNote.value = val
  formData.debouncedSave(NOTE_KEY, { conclusion: null, remark: val })
}

/** 旧问卷 → 新结构迁移 */
function migrateEclMeasurement(raw: any): EclMeasurementData {
  if (!raw) {
    return {
      schemaVersion: 2,
      methodEvaluation: [...DEFAULT_METHOD],
      groupBasis: [],
      parameterEvaluation: [...DEFAULT_PARAMS],
      pdLgdRows: [],
      lossRateRows: [],
      conclusion: '',
    }
  }
  if (raw.schemaVersion >= 2 || raw.pdLgdRows || raw.methodEvaluation) {
    return {
      schemaVersion: 2,
      methodEvaluation: raw.methodEvaluation?.length ? raw.methodEvaluation : [...DEFAULT_METHOD],
      groupBasis: raw.groupBasis || [],
      parameterEvaluation: raw.parameterEvaluation?.length ? raw.parameterEvaluation : [...DEFAULT_PARAMS],
      pdLgdRows: raw.pdLgdRows || [],
      lossRateRows: raw.lossRateRows || [],
      conclusion: raw.conclusion || '',
    }
  }
  // 旧 5-section 问卷：保留为参数评价备注线索
  const params = [...DEFAULT_PARAMS]
  const noteBits: string[] = []
  for (const key of ['pdSection', 'lgdSection', 'eadSection', 'discountRateSection', 'forwardLookingSection'] as const) {
    const rows = raw[key]
    if (Array.isArray(rows) && rows.length) {
      noteBits.push(`${key}:${rows.length}项`)
    }
  }
  if (noteBits.length && params[0]) {
    params[0].note = `已从旧问卷迁移（${noteBits.join('；')}），请按双路径测算表重新填列`
  }
  return {
    schemaVersion: 2,
    methodEvaluation: [...DEFAULT_METHOD],
    groupBasis: [],
    parameterEvaluation: params,
    pdLgdRows: [],
    lossRateRows: [],
    conclusion: '',
    methodologyContext: raw.methodologyContext,
  }
}

function applyPayload(ecl: EclMeasurementData): void {
  methodEvaluation.value = ecl.methodEvaluation?.length ? ecl.methodEvaluation : [...DEFAULT_METHOD]
  groupBasis.value = ecl.groupBasis || []
  parameterEvaluation.value = ecl.parameterEvaluation?.length ? ecl.parameterEvaluation : [...DEFAULT_PARAMS]
  pdLgdRows.value = (ecl.pdLgdRows || []).map((r) => {
    const row = { ...emptyPdLgd(), ...r }
    recomputePdLgd(row, false)
    return row
  })
  lossRateRows.value = (ecl.lossRateRows || []).map((r) => {
    const row = { ...emptyLossRate(), ...r }
    recomputeLossRate(row)
    return row
  })
  conclusion.value = ecl.conclusion || ''
}

function initFromData(): void {
  const saved = formData.allResponses.value.get(DATA_KEY)
  let raw: any = null
  if (saved?.conclusion) {
    try { raw = JSON.parse(saved.conclusion) } catch { /* ignore */ }
  }
  if (!raw) raw = formData.parseContent()?.eclMeasurement
  if (!raw && props.htmlData?.eclMeasurement) raw = props.htmlData.eclMeasurement
  applyPayload(migrateEclMeasurement(raw))
}

function normalizeName(n: string): string {
  return String(n || '').trim().replace(/\s+/g, '').toLowerCase()
}

async function pullFromG611(): Promise<void> {
  if (props.isReadonly) return
  pulling.value = true
  try {
    try { await formData.loadAll() } catch { /* ignore */ }
    const fromRows = parseG6ChecklistRows(formData.allResponses.value.get(G6_11_ROWS_KEY))
    const content = formData.parseContent?.()
    const stageRows =
      (fromRows.length ? fromRows : null)
      || content?.stageClassification?.rows
      || props.htmlData?.stageClassification?.rows
      || []
    const sources = (stageRows as any[])
      .filter(r => String(r?.investProject || '').trim())
      .map(r => ({
        projectName: String(r.investProject).trim(),
        crossSheetInvestmentId: String(r.crossSheetInvestmentId || r.id || '').trim(),
        stage: (r.auditStage || r.companyStage || '') as PdLgdCalcRow['stage'],
        bookBalance: Number(r.bookBalance || r.amortizedCost) || 0,
      }))
    if (!sources.length) {
      ElMessage.warning('G6-11 无可用投资项目，请先完成三阶段划分')
      return
    }
    const targetIsPd = rateTab.value === 'pdLgd'
    const existing = targetIsPd ? pdLgdRows.value : lossRateRows.value
    const byId = new Map(
      existing
        .map(r => [String(r.crossSheetInvestmentId || r.id || '').trim(), r] as const)
        .filter(([id]) => id),
    )
    const byName = new Map(existing.map(r => [normalizeName(r.projectName), r]))
    let added = 0
    let updated = 0
    for (const src of sources) {
      const key = normalizeName(src.projectName)
      let hit = src.crossSheetInvestmentId
        ? byId.get(src.crossSheetInvestmentId)
        : undefined
      if (!hit) hit = byName.get(key)
      if (hit) {
        if (src.stage) hit.stage = src.stage
        if (src.crossSheetInvestmentId) {
          hit.crossSheetInvestmentId = hit.crossSheetInvestmentId || src.crossSheetInvestmentId
        }
        if (src.bookBalance > 0 && !parseNum(hit.bookBalance)) {
          hit.bookBalance = src.bookBalance
        }
        if (targetIsPd) recomputePdLgd(hit as PdLgdCalcRow, true)
        else recomputeLossRate(hit as LossRateCalcRow)
        updated += 1
      } else if (targetIsPd) {
        const row = emptyPdLgd(src.projectName, src.crossSheetInvestmentId)
        row.stage = src.stage || ''
        row.bookBalance = src.bookBalance
        recomputePdLgd(row, true)
        pdLgdRows.value.push(row)
        byName.set(key, row)
        if (row.crossSheetInvestmentId) byId.set(row.crossSheetInvestmentId, row)
        added += 1
      } else {
        const row = emptyLossRate(src.projectName, src.crossSheetInvestmentId)
        row.stage = src.stage || ''
        row.bookBalance = src.bookBalance
        recomputeLossRate(row)
        lossRateRows.value.push(row)
        byName.set(key, row)
        if (row.crossSheetInvestmentId) byId.set(row.crossSheetInvestmentId, row)
        added += 1
      }
    }
    saveAll()
    ElMessage.success(`已从 G6-11 同步：新增 ${added}，更新 ${updated}`)
  } catch {
    ElMessage.error('从 G6-11 拉取失败')
  } finally {
    pulling.value = false
  }
}

async function onImported(): Promise<void> {
  try {
    await formData.loadAll()
    initFromData()
  } catch { /* ignore */ }
  emit('imported')
}

async function syncRatesToG612(): Promise<void> {
  if (props.isReadonly) return
  pushing.value = true
  try {
    saveAll()
    const prefer = rateTab.value === 'pdLgd' ? 'pdLgd' : 'lossRate'
    const updates = collectEclRateUpdates(pdLgdRows.value, lossRateRows.value, prefer)
    if (!updates.length) {
      ElMessage.warning('无有效损失率可回写（请填写项目名称并完成 ECL 率计算）')
      return
    }
    try { await formData.loadAll() } catch { /* ignore */ }
    const payload = parseG6ChecklistPayload(formData.allResponses.value.get(G612_KEY))
    const existing = Array.isArray(payload)
      ? payload
      : (Array.isArray(payload?.rows) ? payload.rows : [])
    const priorConclusion = typeof payload?.conclusion === 'string' ? payload.conclusion : ''
    impairmentBridge.loadRows(existing)
    const applied = impairmentBridge.applyEclRateUpdates(updates)
    for (const r of impairmentBridge.rows.value) impairmentBridge.recalcRow(r)
    await formData.saveImmediate(G612_KEY, {
      conclusion: JSON.stringify({
        rows: impairmentBridge.toJSON(),
        conclusion: priorConclusion,
      }),
    })
    const json = JSON.stringify(impairmentBridge.toJSON())
    await formData.saveImmediate('G6-12-rows', { remark: json, conclusion: json })
    try {
      window.dispatchEvent(new CustomEvent(G6_ECL_RATE_UPDATED_EVENT, {
        detail: {
          updates,
          matched: applied.matched,
          unmatched: applied.unmatched,
          skipped: applied.skipped,
          written: true,
        },
      }))
    } catch { /* ignore */ }
    ElMessage.success(
      `已回写 G6-12：匹配 ${applied.count}；未匹配 ${applied.unmatched.length}；跳过 ${applied.skipped.length}`
        + (applied.matchReport.ambiguous.length
          ? `；重名冲突 ${applied.matchReport.ambiguous.length}`
          : ''),
    )
    emit('imported')
  } catch {
    ElMessage.error('回写 G6-12 失败')
  } finally {
    pushing.value = false
  }
}

async function handleAi(): Promise<void> {
  if (props.isReadonly) return
  const text = await generateAndConfirm(
    'ecl-measurement-conclusion',
    conclusion.value || '',
    {
      methodEvaluation: methodEvaluation.value,
      groupCount: groupBasis.value.length,
      pdLgdCount: pdLgdRows.value.length,
      lossRateCount: lossRateRows.value.length,
    },
    'AI ECL计量结论',
  )
  if (text) {
    conclusion.value = text
    saveAll()
  }
}

onMounted(async () => {
  await formData.loadAll()
  initFromData()
  const n = formData.allResponses.value.get(NOTE_KEY)
  if (n?.remark) auditNote.value = n.remark
})

onBeforeUnmount(() => {
  saveAll()
  formData.flushPending()
})

watch(() => props.htmlData, (d) => {
  if (d) initFromData()
})

defineExpose({ toJSON: buildPayload })
</script>

<style scoped>
.g6-tab-ecl-measurement { padding: 12px; font-size: var(--wp-font-size, 13px); }
.objective-alert { margin-bottom: 12px; }
.methodology-context {
  border-left: 4px solid #e6a23c; background: #fdf6ec;
  padding: 10px 14px; margin-bottom: 10px; border-radius: 0 4px 4px 0;
  font-size: 12px; line-height: 1.7; color: #6b5900;
}
.methodology-title { font-weight: 600; margin: 0 0 4px; }
.methodology-context p { margin: 2px 0; }
.flow-hint { display: flex; align-items: center; gap: 6px; margin-bottom: 10px; flex-wrap: wrap; }
.flow-arrow { color: #909399; }
.tab-toolbar {
  display: flex; justify-content: space-between; gap: 8px; margin-bottom: 12px; flex-wrap: wrap;
}
.toolbar-left, .toolbar-right { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
.chip-wrap { display: inline-flex; }
.section-card { margin-bottom: 14px; }
.section-header { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.section-title { font-weight: 600; font-size: 14px; }
.sub-toolbar { display: flex; gap: 8px; align-items: center; margin-bottom: 8px; flex-wrap: wrap; }
.amt { width: 100%; }
.amt :deep(.el-input__inner) { text-align: right; }
.formula-cell { border-bottom: 1px dashed #909399; cursor: help; }
.rate-warn { color: #e6a23c; font-weight: 600; }
.guide-details { margin-top: 12px; font-size: 12px; color: #606266; }
.guide-details summary { cursor: pointer; font-weight: 600; }
.guide-content {
  margin-top: 6px; padding: 8px 12px; background: #fffbeb;
  border-left: 3px solid #f59e0b; line-height: 1.8;
}
.guide-content p { margin: 0; }
</style>
