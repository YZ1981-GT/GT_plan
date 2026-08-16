<template>
  <div class="g4-tab-ecl-measurement">
    <!-- 审计目标：对齐源底稿 G4-11 -->
    <el-alert type="info" :closable="false" show-icon class="objective-alert">
      <template #title>
        <span>审计目标：评价企业预期信用损失计量方法是否适当；计量是否反映无偏概率加权金额、是否考虑货币时间价值，以及是否无需付出不当成本或努力即可获取的合理且有依据的信息（含前瞻性信息）。</span>
      </template>
    </el-alert>

    <!-- 方法论：双路径测算 + 评价要点 -->
    <div class="methodology-context">
      <p><strong>编制逻辑（对齐致同源底稿 G4-11）：</strong></p>
      <ul>
        <li><strong>先定性后定量</strong>：评价计量方法与组合划分 → 抽样测算损失率 → 形成结论，测算结果可回填 G4-10「信用损失率」</li>
        <li><strong>PD/LGD 法</strong>：ECL率 = 期限折算PD × LGD；ECL = 账面余额 × ECL率（适用于有外部/内部评级映射条件的债权）</li>
        <li><strong>损失率法</strong>：ECL率 = 历史损失率 + 前瞻性调整；适用于难以拆分 PD/LGD 的组合</li>
        <li><strong>与三阶段衔接</strong>：Stage1 多用 12 个月 PD；Stage2/3 用整个存续期 ECL（参见 G4-9）</li>
      </ul>
    </div>

    <!-- 底稿链路提示 -->
    <div class="flow-hint">
      <el-tag size="small" type="info" effect="plain">G4-9 三阶段</el-tag>
      <span class="flow-arrow">→</span>
      <el-tag size="small" type="warning" effect="dark">G4-11 损失率测试（本表）</el-tag>
      <span class="flow-arrow">→</span>
      <el-tag size="small" type="success" effect="plain">G4-10 减值准备测算</el-tag>
    </div>

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <G4EclImportExportDropdown
          :wp-id="wpId"
          sheet="G4-11"
          :disabled="isReadonly"
          @imported="onImported"
        />
        <el-tag size="small" type="info">
          PD/LGD {{ pdLgdRows.length }} 行 · 损失率法 {{ lossRateRows.length }} 行
        </el-tag>
        <el-button
          size="small"
          :disabled="isReadonly"
          :loading="pullingG49"
          @click="pullFromG49"
        >
          从 G4-9 拉取项目
        </el-button>
        <el-button
          size="small"
          type="primary"
          plain
          :disabled="isReadonly"
          :loading="pushingRates"
          @click="syncRatesToG410"
        >
          回写损失率至 G4-10
        </el-button>
      </div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:G4-11" :context-project-id="projectId" /></span>
      </div>
    </div>

    <!-- 审计过程（源底稿第二节，可折叠） -->
    <details class="procedure-details" open>
      <summary>二、审计过程（核查清单）</summary>
      <ol class="procedure-list">
        <li>评价企业以单项或以组合为基础评估信用损失的依据是否适当；组合划分是否具有类似信用风险特征（金融工具类型、信用风险评级、初始确认日期、剩余期限等）。</li>
        <li>评价预期信用损失计量是否正确反映无偏概率加权、货币时间价值，以及无需付出不当成本或努力即可获取的合理且有依据信息（含对未来经济状况的预测）。</li>
        <li>针对抽样项目/组合，按企业采用的方法（PD/LGD 或损失率法）独立测算预期信用损失率，并与企业计提及上期历史损失率比较。</li>
      </ol>
    </details>

    <!-- ═══ (一) ECL计量方法评价 ═══ -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="section-header">
          <span class="section-title">(一) ECL计量方法评价</span>
          <div class="section-actions">
            <el-button size="small" :disabled="isReadonly || !aiAvailable" :loading="aiLoading" @click="handleAi('section1')">🤖 AI辅助</el-button>
            <el-button size="small" @click="openReview('G4-11-ecl-method-eval')">💬复核</el-button>
          </div>
        </div>
      </template>
      <el-table :data="methodEvaluation" border size="small" class="ecl-table">
        <el-table-column label="检查项目" prop="checkItem" min-width="120" />
        <el-table-column label="检查内容" prop="checkContent" min-width="180">
          <template #default="{ row }">
            <span class="check-content-text">{{ row.checkContent }}</span>
          </template>
        </el-table-column>
        <el-table-column label="企业采用方法" min-width="180">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.companyMethod"
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 4 }"
              placeholder="企业ECL计量方法..."
              @update:model-value="(v: string) => updateMethodEval(row.id, 'companyMethod', v)"
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
              @change="(v: string) => updateMethodEval(row.id, 'auditEvaluation', v)"
            >
              <el-option value="合理" label="合理" />
              <el-option value="基本合理" label="基本合理" />
              <el-option value="不合理" label="不合理" />
            </el-select>
            <span v-else>{{ row.auditEvaluation || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="说明" min-width="160">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.note"
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 4 }"
              placeholder="补充说明..."
              @update:model-value="(v: string) => updateMethodEval(row.id, 'note', v)"
            />
            <span v-else>{{ row.note || '-' }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ═══ (二) 组合划分依据 ═══ -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="section-header">
          <span class="section-title">(二) 组合划分依据</span>
          <div class="section-actions">
            <el-button size="small" :disabled="isReadonly" @click="handleAddGroup">+ 新增组合</el-button>
            <el-button size="small" :disabled="isReadonly || !aiAvailable" :loading="aiLoading" @click="handleAi('section2')">🤖 AI辅助</el-button>
            <el-button size="small" @click="openReview('G4-11-group-basis')">💬复核</el-button>
          </div>
        </div>
      </template>

      <el-empty v-if="groupBasis.length === 0" description="暂无组合，点击“新增组合”添加" :image-size="60" />
      <el-table v-else :data="groupBasis" border size="small" class="ecl-table">
        <el-table-column label="组合名称" min-width="120">
          <template #default="{ row }">
            <div class="name-cell">
              <span>{{ row.groupName }}</span>
              <el-button
                v-if="!isReadonly"
                size="small" type="danger" link
                @click="handleRemoveGroup(row.id, row.groupName)"
              >🗑️</el-button>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="划分依据" min-width="160">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.basis"
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 4 }"
              placeholder="如：外部评级 / 同业 / 剩余期限..."
              @update:model-value="(v: string) => updateGroupBasis(row.id, 'basis', v)"
            />
            <span v-else>{{ row.basis || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="信用风险特征" min-width="160">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.riskCharacteristic"
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 4 }"
              placeholder="风险特征描述..."
              @update:model-value="(v: string) => updateGroupBasis(row.id, 'riskCharacteristic', v)"
            />
            <span v-else>{{ row.riskCharacteristic || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="样本量" width="100" align="center">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.sampleSize"
              size="small"
              :min="0"
              :controls="false"
              style="width: 80px"
              @update:model-value="(v: number | undefined) => updateGroupBasis(row.id, 'sampleSize', v ?? 0)"
            />
            <span v-else>{{ row.sampleSize }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审计评价" width="100" align="center">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              :model-value="row.auditEvaluation"
              size="small"
              style="width: 100%"
              @change="(v: string) => updateGroupBasis(row.id, 'auditEvaluation', v)"
            >
              <el-option value="合理" label="合理" />
              <el-option value="不合理" label="不合理" />
            </el-select>
            <span v-else>{{ row.auditEvaluation || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="说明" min-width="140">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.note"
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 4 }"
              placeholder="补充说明..."
              @update:model-value="(v: string) => updateGroupBasis(row.id, 'note', v)"
            />
            <span v-else>{{ row.note || '-' }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ═══ (三) 信用损失率的确定（定量测算 + 参数评价） ═══ -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="section-header">
          <span class="section-title">(三) 信用损失率的确定</span>
          <div class="section-actions">
            <el-button size="small" @click="openReview('G4-11-parameter-eval')">💬复核</el-button>
          </div>
        </div>
      </template>

      <el-tabs v-model="rateTab" type="border-card" class="rate-tabs">
        <!-- Tab1: PD/LGD -->
        <el-tab-pane name="pdLgd">
          <template #label>
            <span>1. PD/LGD 法<code class="tab-hint">示例方法</code></span>
          </template>
          <G4EclPdGuidance />
          <div class="sub-toolbar">
            <span class="formula-tip">公式：期限折算PD = 1−(1−外部映射PD)^(月数/12)；ECL率 = PD × LGD；ECL = 余额 × ECL率</span>
            <el-button size="small" type="primary" plain :disabled="isReadonly" @click="handleAddPdLgd">+ 新增行</el-button>
          </div>
          <el-empty v-if="pdLgdRows.length === 0" description="暂无PD/LGD测算行，点击“新增行”添加抽样项目" :image-size="50" />
          <el-table v-else :data="pdLgdRows" border size="small" class="ecl-table calc-table" show-summary :summary-method="pdLgdSummary">
            <el-table-column label="投资项目/组合" min-width="130" fixed>
              <template #default="{ row }">
                <div class="name-cell">
                  <el-input
                    v-if="!isReadonly"
                    :model-value="row.projectName"
                    size="small"
                    placeholder="项目/组合"
                    @update:model-value="(v: string) => updatePdLgd(row.id, 'projectName', v)"
                  />
                  <span v-else>{{ row.projectName || '-' }}</span>
                  <el-button v-if="!isReadonly" size="small" type="danger" link @click="removePdLgd(row.id)">🗑️</el-button>
                </div>
              </template>
            </el-table-column>
            <el-table-column label="账面余额" min-width="110" align="right">
              <template #default="{ row }">
                <el-input-number
                  v-if="!isReadonly"
                  :model-value="row.bookBalance"
                  size="small"
                  :controls="false"
                  class="compact-num"
                  @change="(v: number | undefined) => updatePdLgd(row.id, 'bookBalance', v ?? 0)"
                />
                <span v-else>{{ fmtNum(row.bookBalance) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="剩余月数" width="90" align="center">
              <template #default="{ row }">
                <el-input-number
                  v-if="!isReadonly"
                  :model-value="row.remainingMonths"
                  size="small"
                  :controls="false"
                  :min="0"
                  class="compact-num"
                  @change="(v: number | undefined) => updatePdLgd(row.id, 'remainingMonths', v ?? 0)"
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
                  placeholder="阶段"
                  style="width: 100%"
                  @change="(v: string) => updatePdLgd(row.id, 'stage', v || '')"
                >
                  <el-option value="Stage1" label="Stage1" />
                  <el-option value="Stage2" label="Stage2" />
                  <el-option value="Stage3" label="Stage3" />
                </el-select>
                <span v-else>{{ row.stage || '-' }}</span>
              </template>
            </el-table-column>
            <el-table-column label="评级" width="110" align="center">
              <template #default="{ row }">
                <el-select
                  v-if="!isReadonly"
                  :model-value="row.rating"
                  size="small"
                  filterable
                  allow-create
                  default-first-option
                  clearable
                  placeholder="评级"
                  style="width: 100%"
                  @change="(v: string) => onPdLgdRatingChange(row.id, v || '')"
                >
                  <el-option
                    v-for="opt in G4_ECL_RATING_OPTIONS"
                    :key="opt"
                    :value="opt"
                    :label="opt"
                  />
                </el-select>
                <span v-else>{{ row.rating || '-' }}</span>
              </template>
            </el-table-column>
            <el-table-column label="外部映射PD" min-width="110" align="right">
              <template #default="{ row }">
                <el-input-number
                  v-if="!isReadonly"
                  :model-value="row.externalMappedPd"
                  size="small"
                  :controls="false"
                  :precision="6"
                  :step="0.0001"
                  :min="0"
                  :max="1"
                  class="compact-num"
                  @change="(v: number | undefined) => updatePdLgd(row.id, 'externalMappedPd', v ?? 0)"
                />
                <span v-else>{{ fmtPct(row.externalMappedPd) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="期限折算PD" min-width="110" align="right">
              <template #default="{ row }">
                <el-tooltip content="可覆写；默认 = 1−(1−外部映射PD)^(月数/12)" placement="top">
                  <el-input-number
                    v-if="!isReadonly"
                    :model-value="row.termAdjustedPd"
                    size="small"
                    :controls="false"
                    :precision="6"
                    :step="0.0001"
                    :min="0"
                    :max="1"
                    class="compact-num formula-input"
                    @change="(v: number | undefined) => updatePdLgd(row.id, 'termAdjustedPd', v ?? 0, true)"
                  />
                  <span v-else class="formula-cell">{{ fmtPct(row.termAdjustedPd) }}</span>
                </el-tooltip>
              </template>
            </el-table-column>
            <el-table-column label="LGD" width="100" align="right">
              <template #default="{ row }">
                <el-input-number
                  v-if="!isReadonly"
                  :model-value="row.lgd"
                  size="small"
                  :controls="false"
                  :precision="4"
                  :step="0.01"
                  :min="0"
                  :max="1"
                  class="compact-num"
                  @change="(v: number | undefined) => updatePdLgd(row.id, 'lgd', v ?? 0)"
                />
                <span v-else>{{ fmtPct(row.lgd) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="ECL率" width="100" align="right">
              <template #default="{ row }">
                <el-tooltip content="ECL率 = PD × LGD" placement="top">
                  <span class="formula-cell" :class="{ 'rate-warn': isRateVarianceHigh(row.eclRate, row.priorHistoricalLossRate) }">
                    {{ fmtPct(row.eclRate) }}
                  </span>
                </el-tooltip>
              </template>
            </el-table-column>
            <el-table-column label="预期信用损失" min-width="110" align="right">
              <template #default="{ row }">
                <el-tooltip content="ECL = 账面余额 × ECL率" placement="top">
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
                  :step="0.01"
                  :min="0"
                  :max="1"
                  class="compact-num"
                  @change="(v: number | undefined) => updatePdLgd(row.id, 'priorHistoricalLossRate', v ?? 0)"
                />
                <span v-else>{{ fmtPct(row.priorHistoricalLossRate) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="说明" min-width="120">
              <template #default="{ row }">
                <el-input
                  v-if="!isReadonly"
                  :model-value="row.note"
                  size="small"
                  placeholder="说明..."
                  @update:model-value="(v: string) => updatePdLgd(row.id, 'note', v)"
                />
                <span v-else>{{ row.note || '-' }}</span>
              </template>
            </el-table-column>
          </el-table>
          <p v-if="pdLgdVarianceCount > 0" class="variance-tip">
            ⚠ {{ pdLgdVarianceCount }} 行 ECL率与上期历史损失率差异超过 {{ (VARIANCE_THRESHOLD * 100).toFixed(0) }} 个百分点，请关注前瞻性调整或模型参数变动原因。
          </p>
        </el-tab-pane>

        <!-- Tab2: 损失率法 -->
        <el-tab-pane name="lossRate">
          <template #label>
            <span>2. 损失率法<code class="tab-hint">示例方法</code></span>
          </template>
          <div class="sub-toolbar">
            <span class="formula-tip">公式：ECL率 = 损失率 + 前瞻性调整；ECL = 余额 × ECL率（率均为小数，如 1%=0.01）</span>
            <el-button size="small" type="primary" plain :disabled="isReadonly" @click="handleAddLossRate">+ 新增行</el-button>
          </div>
          <el-empty v-if="lossRateRows.length === 0" description="暂无损失率法测算行，点击“新增行”添加" :image-size="50" />
          <el-table v-else :data="lossRateRows" border size="small" class="ecl-table calc-table" show-summary :summary-method="lossRateSummary">
            <el-table-column label="投资项目/组合" min-width="130" fixed>
              <template #default="{ row }">
                <div class="name-cell">
                  <el-input
                    v-if="!isReadonly"
                    :model-value="row.projectName"
                    size="small"
                    placeholder="项目/组合"
                    @update:model-value="(v: string) => updateLossRate(row.id, 'projectName', v)"
                  />
                  <span v-else>{{ row.projectName || '-' }}</span>
                  <el-button v-if="!isReadonly" size="small" type="danger" link @click="removeLossRate(row.id)">🗑️</el-button>
                </div>
              </template>
            </el-table-column>
            <el-table-column label="账面余额" min-width="110" align="right">
              <template #default="{ row }">
                <el-input-number
                  v-if="!isReadonly"
                  :model-value="row.bookBalance"
                  size="small"
                  :controls="false"
                  class="compact-num"
                  @change="(v: number | undefined) => updateLossRate(row.id, 'bookBalance', v ?? 0)"
                />
                <span v-else>{{ fmtNum(row.bookBalance) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="剩余月数" width="90" align="center">
              <template #default="{ row }">
                <el-input-number
                  v-if="!isReadonly"
                  :model-value="row.remainingMonths"
                  size="small"
                  :controls="false"
                  :min="0"
                  class="compact-num"
                  @change="(v: number | undefined) => updateLossRate(row.id, 'remainingMonths', v ?? 0)"
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
                  placeholder="阶段"
                  style="width: 100%"
                  @change="(v: string) => updateLossRate(row.id, 'stage', v || '')"
                >
                  <el-option value="Stage1" label="Stage1" />
                  <el-option value="Stage2" label="Stage2" />
                  <el-option value="Stage3" label="Stage3" />
                </el-select>
                <span v-else>{{ row.stage || '-' }}</span>
              </template>
            </el-table-column>
            <el-table-column label="评级" width="110" align="center">
              <template #default="{ row }">
                <el-select
                  v-if="!isReadonly"
                  :model-value="row.rating"
                  size="small"
                  filterable
                  allow-create
                  default-first-option
                  clearable
                  placeholder="评级"
                  style="width: 100%"
                  @change="(v: string) => updateLossRate(row.id, 'rating', v || '')"
                >
                  <el-option
                    v-for="opt in G4_ECL_RATING_OPTIONS"
                    :key="opt"
                    :value="opt"
                    :label="opt"
                  />
                </el-select>
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
                  :step="0.01"
                  :min="0"
                  :max="1"
                  class="compact-num"
                  @change="(v: number | undefined) => updateLossRate(row.id, 'lossRate', v ?? 0)"
                />
                <span v-else>{{ fmtPct(row.lossRate) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="说明" min-width="130">
              <template #default="{ row }">
                <el-input
                  v-if="!isReadonly"
                  :model-value="row.description"
                  size="small"
                  placeholder="损失率确定依据..."
                  @update:model-value="(v: string) => updateLossRate(row.id, 'description', v)"
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
                  :step="0.001"
                  class="compact-num"
                  @change="(v: number | undefined) => updateLossRate(row.id, 'forwardLookingAdj', v ?? 0)"
                />
                <span v-else>{{ fmtPct(row.forwardLookingAdj) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="ECL率" width="100" align="right">
              <template #default="{ row }">
                <el-tooltip content="ECL率 = 损失率 + 前瞻性调整" placement="top">
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
                  :step="0.01"
                  :min="0"
                  :max="1"
                  class="compact-num"
                  @change="(v: number | undefined) => updateLossRate(row.id, 'priorHistoricalLossRate', v ?? 0)"
                />
                <span v-else>{{ fmtPct(row.priorHistoricalLossRate) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="备注" min-width="100">
              <template #default="{ row }">
                <el-input
                  v-if="!isReadonly"
                  :model-value="row.note"
                  size="small"
                  @update:model-value="(v: string) => updateLossRate(row.id, 'note', v)"
                />
                <span v-else>{{ row.note || '-' }}</span>
              </template>
            </el-table-column>
          </el-table>
          <p v-if="lossRateVarianceCount > 0" class="variance-tip">
            ⚠ {{ lossRateVarianceCount }} 行 ECL率与上期历史损失率差异超过 {{ (VARIANCE_THRESHOLD * 100).toFixed(0) }} 个百分点，请说明前瞻性调整依据。
          </p>
        </el-tab-pane>

        <!-- Tab3: 参数来源评价 -->
        <el-tab-pane label="3. 参数来源评价" name="params">
          <div class="sub-toolbar">
            <span class="formula-tip">评价 PD / LGD / EAD 等参数数据来源与计算方法（定性，与上表定量测算互补）</span>
            <el-button size="small" :disabled="isReadonly" @click="handleAddParameter">+ 新增参数</el-button>
            <el-button size="small" :disabled="isReadonly || !aiAvailable" :loading="aiLoading" @click="handleAi('section3')">🤖 AI辅助</el-button>
          </div>
          <el-empty v-if="parameterEvaluation.length === 0" description="暂无参数，点击“新增参数”添加" :image-size="50" />
          <el-table v-else :data="parameterEvaluation" border size="small" class="ecl-table">
            <el-table-column label="参数名称" min-width="100">
              <template #default="{ row }">
                <div class="name-cell">
                  <span>{{ row.paramName }}</span>
                  <el-button
                    v-if="!isReadonly"
                    size="small" type="danger" link
                    @click="handleRemoveParameter(row.id, row.paramName)"
                  >🗑️</el-button>
                </div>
              </template>
            </el-table-column>
            <el-table-column label="数据来源" min-width="160">
              <template #default="{ row }">
                <el-input
                  v-if="!isReadonly"
                  :model-value="row.dataSource"
                  type="textarea"
                  :autosize="{ minRows: 1, maxRows: 4 }"
                  placeholder="外部评级映射 / 迁移矩阵 / 历史回收率..."
                  @update:model-value="(v: string) => updateParameterEval(row.id, 'dataSource', v)"
                />
                <span v-else>{{ row.dataSource || '-' }}</span>
              </template>
            </el-table-column>
            <el-table-column label="计算方法" min-width="160">
              <template #default="{ row }">
                <el-input
                  v-if="!isReadonly"
                  :model-value="row.calcMethod"
                  type="textarea"
                  :autosize="{ minRows: 1, maxRows: 4 }"
                  placeholder="计算方法..."
                  @update:model-value="(v: string) => updateParameterEval(row.id, 'calcMethod', v)"
                />
                <span v-else>{{ row.calcMethod || '-' }}</span>
              </template>
            </el-table-column>
            <el-table-column label="审计验证结果" min-width="160">
              <template #default="{ row }">
                <el-input
                  v-if="!isReadonly"
                  :model-value="row.verificationResult"
                  type="textarea"
                  :autosize="{ minRows: 1, maxRows: 4 }"
                  placeholder="验证结果..."
                  @update:model-value="(v: string) => updateParameterEval(row.id, 'verificationResult', v)"
                />
                <span v-else>{{ row.verificationResult || '-' }}</span>
              </template>
            </el-table-column>
            <el-table-column label="审计评价" width="120" align="center">
              <template #default="{ row }">
                <el-select
                  v-if="!isReadonly"
                  :model-value="row.auditEvaluation"
                  size="small"
                  style="width: 100%"
                  @change="(v: string) => updateParameterEval(row.id, 'auditEvaluation', v)"
                >
                  <el-option value="合理" label="合理" />
                  <el-option value="基本合理" label="基本合理" />
                  <el-option value="不合理" label="不合理" />
                </el-select>
                <span v-else>{{ row.auditEvaluation || '-' }}</span>
              </template>
            </el-table-column>
            <el-table-column label="说明" min-width="140">
              <template #default="{ row }">
                <el-input
                  v-if="!isReadonly"
                  :model-value="row.note"
                  type="textarea"
                  :autosize="{ minRows: 1, maxRows: 4 }"
                  placeholder="补充说明..."
                  @update:model-value="(v: string) => updateParameterEval(row.id, 'note', v)"
                />
                <span v-else>{{ row.note || '-' }}</span>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>
      </el-tabs>
    </el-card>

    <div class="audit-text-extras no-print">
      <el-button
        size="small"
        :disabled="isReadonly || !aiAvailable"
        :loading="aiLoading"
        @click="handleAi('conclusion')"
      >
        🤖 AI辅助
      </el-button>
      <el-button size="small" @click="openReview('G4-11-conclusion')">💬复核</el-button>
    </div>
    <G4AuditTextCards
      :wp-id="wpId"
      :is-readonly="isReadonly"
      v-model:note="auditNote"
      v-model:conclusion="conclusion"
      note-title="三、审计说明"
      conclusion-title="四、审计结论"
      note-placeholder="填写审计说明：抽样范围、采用的计量方法、与企业损失率/上期历史损失率的差异原因、拟调整事项及其影响等。"
      conclusion-placeholder="综合评价企业ECL计量方法、组合划分依据、信用损失率测算结果的合理性，以及减值准备是否充分..."
      @update:note="saveAuditNote"
      @update:conclusion="handleConclusionChange"
    />

    <details class="g4-guide-details">
      <summary>📋 编制提示</summary>
      <div class="g4-guide-content">
        <p>1. 先完成（一）（二）定性评价，再在（三）按企业实际采用方法选择 PD/LGD 或损失率法做抽样测算</p>
        <p>2. 比率一律按小数录入（1% 录 0.01）；灰色/公式列为自动计算，期限折算PD可覆写</p>
        <p>3. PD来源：外部评级映射、迁移矩阵、中证协减值指引附表；评级下拉可带出参考一年期PD（须替换为当期数据版本）</p>
        <p>4. LGD：历史回收率、担保物覆盖、行业基准；EAD 通常≈账面信用敞口</p>
        <p>5. 测算得到的 ECL率应与 G4-10「②信用损失率」勾稽；可用「回写损失率至 G4-10」同步（Stage3 默认跳过）</p>
        <p>6. 「从 G4-9 拉取项目」可带入投资项目/阶段/账面余额到当前测算 Tab</p>
        <p>7. Stage1 只计未来12个月PD；Stage2按整个剩余存续期；Stage3参考PD=100%，并结合LGD和预计回收现金流</p>
        <p>8. 与上期历史损失率差异超阈值时橙色高亮，须在审计说明中解释</p>
        <p>9. 《商业银行资本管理办法》的资本风险权重不等于会计PD，不得直接填入PD或信用损失率列</p>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * G4TabEclMeasurement.vue — G4-11 预期信用损失计量测试
 *
 * 对齐致同源底稿：目标 → 过程 → 方法评价 → 组合依据 →
 * 双路径定量测算（PD/LGD + 损失率法）+ 参数评价 → 说明 → 结论
 */
import { ref, inject, computed, watch, onMounted } from 'vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import type { SummaryMethod } from 'element-plus'
import { useG4EclFormData } from '../../composables/useG4EclFormData'
import GtIndexChip from '../../GtIndexChip.vue'
import G4AuditTextCards from '../../g4-bond-investment-main/G4AuditTextCards.vue'
import G4EclImportExportDropdown from '../G4EclImportExportDropdown.vue'
import G4EclPdGuidance from '../reference/G4EclPdGuidance.vue'
import type {
  MethodEvalRow,
  GroupBasisRow,
  ParameterEvalRow,
  PdLgdCalcRow,
  LossRateCalcRow,
} from '../../composables/useG4EclFormData'
import { useG4EclAiGenerate } from '../../composables/useG4EclAiGenerate'
import {
  collectEclRateUpdates,
  useG4EclImpairmentCalc,
} from '../../composables/useG4EclImpairmentCalc'
import {
  parseChecklistRows,
  parseG411MeasurementPayload,
  buildG411MeasurementPayload,
  normalizeInvestName,
  G4_9_ROWS_KEY,
  G4_10_ROWS_KEY,
  G4_11_MEASUREMENT_KEY,
  G4_ECL_RATE_UPDATED_EVENT,
} from '../../composables/g4CrossHelpers'
import { buildCanonicalPayload } from '../../composables/g4StorageContract'
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
  calcSumColumn,
  parseNum,
} from '../../composables/useG4EclFormulaEngine'

const props = defineProps<{
  htmlData: Record<string, any> | null
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const emit = defineEmits<{ imported: [] }>()

const VARIANCE_THRESHOLD = 0.02 // 2 个百分点

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})
const wpIdRef = computed(() => props.wpId)
const { generateAndConfirm, aiAvailable, loading: aiLoading } = useG4EclAiGenerate(wpIdRef)

function openReview(sectionId: string): void {
  openReviewDialog(sectionId)
}

const formData = useG4EclFormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

/** 仅用于 G4-11→G4-10 回写时重算减值公式链 */
const impairmentBridge = useG4EclImpairmentCalc()

const DEFAULT_METHOD_EVAL_ROWS: MethodEvalRow[] = [
  {
    id: 'me-1',
    checkItem: 'ECL计量方法选择',
    checkContent: '企业是否根据金融资产特征选择合适方法（个别/组合；PD/LGD或损失率法）',
    companyMethod: '',
    auditEvaluation: '合理',
    note: '',
  },
  {
    id: 'me-2',
    checkItem: '无偏概率加权',
    checkContent: '计量是否反映通过评价一系列可能结果而确定的无偏概率加权平均金额',
    companyMethod: '',
    auditEvaluation: '合理',
    note: '',
  },
  {
    id: 'me-3',
    checkItem: '货币时间价值',
    checkContent: '是否按实际利率（或近似利率）将预期现金短缺折现至报告日',
    companyMethod: '',
    auditEvaluation: '合理',
    note: '',
  },
  {
    id: 'me-4',
    checkItem: '前瞻性信息运用',
    checkContent: '是否合理考虑过去事项、当前状况及对未来经济状况的预测（无需不当成本或努力）',
    companyMethod: '',
    auditEvaluation: '合理',
    note: '',
  },
  {
    id: 'me-5',
    checkItem: '模型验证与数据质量',
    checkContent: '是否定期回测，历史违约/回收等基础数据是否完整、准确',
    companyMethod: '',
    auditEvaluation: '合理',
    note: '',
  },
]

const DEFAULT_PARAMETER_ROWS: ParameterEvalRow[] = [
  {
    id: 'pe-pd',
    paramName: 'PD（违约概率）',
    dataSource: '',
    calcMethod: '外部评级映射 / 迁移矩阵 / 剩余期限折算',
    verificationResult: '',
    auditEvaluation: '合理',
    note: '',
  },
  {
    id: 'pe-lgd',
    paramName: 'LGD（违约损失率）',
    dataSource: '',
    calcMethod: '历史回收率 / 担保覆盖 / 行业基准',
    verificationResult: '',
    auditEvaluation: '合理',
    note: '',
  },
  {
    id: 'pe-ead',
    paramName: 'EAD（违约风险敞口）',
    dataSource: '',
    calcMethod: '一般等于账面信用敞口；表外承诺考虑CCF',
    verificationResult: '',
    auditEvaluation: '合理',
    note: '',
  },
]

const rateTab = ref('pdLgd')
const methodEvaluation = ref<MethodEvalRow[]>([...DEFAULT_METHOD_EVAL_ROWS])
const groupBasis = ref<GroupBasisRow[]>([])
const parameterEvaluation = ref<ParameterEvalRow[]>([...DEFAULT_PARAMETER_ROWS])
const pdLgdRows = ref<PdLgdCalcRow[]>([])
const lossRateRows = ref<LossRateCalcRow[]>([])
const conclusion = ref('')
const pushingRates = ref(false)
const pullingG49 = ref(false)

async function onImported(): Promise<void> {
  try { await formData.loadAll() } catch { /* ignore */ }
  initFromData()
  emit('imported')
  ElMessage.success('G4-11 数据已导入并刷新')
}

/** 评级变更：带出参考一年期外部映射 PD，并重算期限折算 PD */
function onPdLgdRatingChange(rowId: string, rating: string): void {
  const row = pdLgdRows.value.find((r) => r.id === rowId)
  if (!row) return
  row.rating = rating
  const pd = lookupAnnualPdByRating(rating)
  if (pd != null) {
    row.externalMappedPd = pd
    recomputePdLgd(row, true)
  } else {
    saveAll()
  }
}

/**
 * 从 G4-9 拉取投资项目/阶段/账面余额到当前测算 Tab（按归一化名称合并，不覆盖已有手工输入余额）
 */
async function pullFromG49(): Promise<void> {
  if (props.isReadonly) return
  pullingG49.value = true
  try {
    try { await formData.loadAll() } catch { /* ignore */ }
    const g49 = parseChecklistRows(formData.allResponses.value.get(G4_9_ROWS_KEY))
    const sources = g49
      .filter((r: any) => String(r?.investProject || '').trim())
      .map((r: any) => ({
        projectName: String(r.investProject).trim(),
        stage: (r.auditStage || r.companyStage || '') as PdLgdCalcRow['stage'],
        bookBalance: Number(r.bookBalance) || 0,
      }))
    if (!sources.length) {
      ElMessage.warning('G4-9 无可用投资项目，请先完成三阶段划分')
      return
    }

    const targetIsPd = rateTab.value === 'pdLgd'
    const existing = targetIsPd ? pdLgdRows.value : lossRateRows.value
    const byName = new Map(existing.map((r) => [normalizeInvestName(r.projectName), r]))
    let added = 0
    let updated = 0

    for (const src of sources) {
      const key = normalizeInvestName(src.projectName)
      const hit = byName.get(key)
      if (hit) {
        if (src.stage) hit.stage = src.stage
        if (src.bookBalance > 0 && !parseNum(hit.bookBalance)) {
          hit.bookBalance = src.bookBalance
          if (targetIsPd) recomputePdLgd(hit as PdLgdCalcRow, false)
          else recomputeLossRate(hit as LossRateCalcRow)
        }
        updated += 1
      } else if (targetIsPd) {
        const row = emptyPdLgd(src.projectName)
        row.stage = src.stage || ''
        row.bookBalance = src.bookBalance
        recomputePdLgd(row, true)
        pdLgdRows.value.push(row)
        byName.set(key, row)
        added += 1
      } else {
        const row = emptyLossRate(src.projectName)
        row.stage = src.stage || ''
        row.bookBalance = src.bookBalance
        recomputeLossRate(row)
        lossRateRows.value.push(row)
        byName.set(key, row)
        added += 1
      }
    }
    saveAll()
    ElMessage.success(
      `已从 G4-9 同步至${targetIsPd ? 'PD/LGD' : '损失率法'}：新增 ${added}，更新 ${updated}`,
    )
  } catch {
    ElMessage.error('从 G4-9 拉取失败')
  } finally {
    pullingG49.value = false
  }
}

const NOTE_KEY = 'G4-11-ecl-measurement-audit-note'
const auditNote = ref('')

function saveAuditNote(val: string): void {
  if (props.isReadonly) return
  auditNote.value = val
  formData.debouncedSave(NOTE_KEY, { remark: val })
}

function fmtNum(n: number): string {
  return parseNum(n).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtPct(n: number): string {
  return `${(parseNum(n) * 100).toFixed(2)}%`
}

function isRateVarianceHigh(eclRate: number, prior: number): boolean {
  if (parseNum(prior) === 0 && parseNum(eclRate) === 0) return false
  return calcLossRateVariance(eclRate, prior) > VARIANCE_THRESHOLD
}

const pdLgdVarianceCount = computed(() =>
  pdLgdRows.value.filter((r) => isRateVarianceHigh(r.eclRate, r.priorHistoricalLossRate)).length,
)
const lossRateVarianceCount = computed(() =>
  lossRateRows.value.filter((r) => isRateVarianceHigh(r.eclRate, r.priorHistoricalLossRate)).length,
)

function emptyPdLgd(name = ''): PdLgdCalcRow {
  return {
    id: `pd-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
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

function emptyLossRate(name = ''): LossRateCalcRow {
  return {
    id: `lr-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
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
    row.termAdjustedPd = calcTermAdjustedPd(row.externalMappedPd, row.remainingMonths)
  }
  row.eclRate = calcEclRateFromPdLgd(row.termAdjustedPd, row.lgd)
  row.eclAmount = calcImpairmentProvision(row.bookBalance, row.eclRate)
}

function recomputeLossRate(row: LossRateCalcRow): void {
  row.eclRate = calcEclRateFromLossRate(row.lossRate, row.forwardLookingAdj)
  row.eclAmount = calcImpairmentProvision(row.bookBalance, row.eclRate)
}

onMounted(async () => {
  await formData.loadAll()
  initFromData()
  const note = formData.allResponses.value.get(NOTE_KEY)
  if (note?.remark) auditNote.value = note.remark
})

watch(() => props.htmlData, (newData) => {
  if (newData) initFromData()
})

function initFromData(): void {
  // 优先 checklist 持久化（G4-11-ecl-measurement.conclusion）
  const saved = formData.allResponses.value.get(G4_11_MEASUREMENT_KEY)
  let ecl: any = parseG411MeasurementPayload(saved?.conclusion || saved?.remark)
  if (!ecl) {
    ecl = formData.parseContent()?.eclMeasurement
  }
  if (!ecl) return

  if (ecl.methodEvaluation?.length) methodEvaluation.value = ecl.methodEvaluation
  if (ecl.groupBasis?.length) groupBasis.value = ecl.groupBasis
  if (ecl.parameterEvaluation?.length) {
    parameterEvaluation.value = ecl.parameterEvaluation
  }
  if (ecl.pdLgdRows?.length) {
    pdLgdRows.value = ecl.pdLgdRows.map((r: PdLgdCalcRow) => {
      const row = { ...emptyPdLgd(), ...r }
      recomputePdLgd(row, false)
      return row
    })
  }
  if (ecl.lossRateRows?.length) {
    lossRateRows.value = ecl.lossRateRows.map((r: LossRateCalcRow) => {
      const row = { ...emptyLossRate(), ...r }
      recomputeLossRate(row)
      return row
    })
  }
  if (typeof ecl.conclusion === 'string' && ecl.conclusion) {
    conclusion.value = ecl.conclusion
  }
}

function saveAll(): void {
  const payload = buildCanonicalPayload(
    G4_11_MEASUREMENT_KEY,
    buildG411MeasurementPayload({
      methodEvaluation: methodEvaluation.value,
      groupBasis: groupBasis.value,
      parameterEvaluation: parameterEvaluation.value,
      pdLgdRows: pdLgdRows.value,
      lossRateRows: lossRateRows.value,
      conclusion: conclusion.value,
    }),
  )
  formData.debouncedSave(G4_11_MEASUREMENT_KEY, payload)
}

async function syncRatesToG410(): Promise<void> {
  if (props.isReadonly) return
  pushingRates.value = true
  try {
    const measurementPayload = buildCanonicalPayload(
      G4_11_MEASUREMENT_KEY,
      buildG411MeasurementPayload({
        methodEvaluation: methodEvaluation.value,
        groupBasis: groupBasis.value,
        parameterEvaluation: parameterEvaluation.value,
        pdLgdRows: pdLgdRows.value,
        lossRateRows: lossRateRows.value,
        conclusion: conclusion.value,
      }),
    )
    await formData.saveImmediate(G4_11_MEASUREMENT_KEY, measurementPayload)
    const prefer = rateTab.value === 'pdLgd' ? 'pdLgd' : 'lossRate'
    const updates = collectEclRateUpdates(pdLgdRows.value, lossRateRows.value, prefer)
    if (!updates.length) {
      ElMessage.warning('无有效损失率可回写（请填写项目名称，并完成 ECL 率计算）')
      return
    }
    try { await formData.loadAll() } catch { /* ignore */ }
    const existing = parseChecklistRows(formData.allResponses.value.get(G4_10_ROWS_KEY))
    impairmentBridge.loadRows(existing as any[])
    const applied = impairmentBridge.applyEclRateUpdates(updates)
    const payload = buildCanonicalPayload(G4_10_ROWS_KEY, applied.rows)
    await formData.saveImmediate(G4_10_ROWS_KEY, payload)
    try {
      window.dispatchEvent(new CustomEvent(G4_ECL_RATE_UPDATED_EVENT, {
        detail: {
          updates,
          source: 'G4-11',
          written: true,
          prefer,
          matched: applied.matched,
          unmatched: applied.unmatched,
          matchReport: applied.matchReport,
        },
      }))
    } catch { /* silent */ }
    const report = applied.matchReport
    const skipHint = applied.skipped.length
      ? `；未匹配 ${report.unmatched.length}，ID匹配 ${report.byId.length}，名称匹配 ${report.byName.length}`
      : `（ID匹配 ${report.byId.length}，名称匹配 ${report.byName.length}）`
    ElMessage.success(`已回写 ${applied.count} 条损失率至 G4-10${skipHint}`)
  } catch {
    ElMessage.error('回写 G4-10 失败')
  } finally {
    pushingRates.value = false
  }
}

function updateMethodEval(rowId: string, field: keyof MethodEvalRow, value: unknown): void {
  const row = methodEvaluation.value.find((r) => r.id === rowId)
  if (!row) return
  ;(row as Record<string, unknown>)[field] = value
  saveAll()
}

function updateGroupBasis(rowId: string, field: keyof GroupBasisRow, value: unknown): void {
  const row = groupBasis.value.find((r) => r.id === rowId)
  if (!row) return
  ;(row as Record<string, unknown>)[field] = value
  saveAll()
}

async function handleAddGroup(): Promise<void> {
  try {
    const { value } = await ElMessageBox.prompt('请输入组合名称', '新增组合', {
      confirmButtonText: '确认',
      cancelButtonText: '取消',
      inputPattern: /\S+/,
      inputErrorMessage: '组合名称不能为空',
      inputPlaceholder: '例如：同外部评级组合',
    })
    if (value?.trim()) {
      groupBasis.value.push({
        id: `gb-${Date.now()}`,
        groupName: value.trim(),
        basis: '',
        riskCharacteristic: '',
        sampleSize: 0,
        auditEvaluation: '合理',
        note: '',
      })
      saveAll()
      ElMessage.success(`已新增组合"${value.trim()}"`)
    }
  } catch {
    /* cancel */
  }
}

async function handleRemoveGroup(rowId: string, groupName: string): Promise<void> {
  try {
    await ElMessageBox.confirm(`确认删除组合"${groupName}"？`, '删除确认', {
      confirmButtonText: '确认删除',
      cancelButtonText: '取消',
      type: 'warning',
    })
    groupBasis.value = groupBasis.value.filter((r) => r.id !== rowId)
    saveAll()
    ElMessage.success(`已删除"${groupName}"`)
  } catch {
    /* cancel */
  }
}

function updateParameterEval(rowId: string, field: keyof ParameterEvalRow, value: unknown): void {
  const row = parameterEvaluation.value.find((r) => r.id === rowId)
  if (!row) return
  ;(row as Record<string, unknown>)[field] = value
  saveAll()
}

async function handleAddParameter(): Promise<void> {
  try {
    const { value } = await ElMessageBox.prompt('请输入参数名称（如PD、LGD、EAD、CCF等）', '新增参数', {
      confirmButtonText: '确认',
      cancelButtonText: '取消',
      inputPattern: /\S+/,
      inputErrorMessage: '参数名称不能为空',
      inputPlaceholder: '例如：折现率',
    })
    if (value?.trim()) {
      parameterEvaluation.value.push({
        id: `pe-${Date.now()}`,
        paramName: value.trim(),
        dataSource: '',
        calcMethod: '',
        verificationResult: '',
        auditEvaluation: '合理',
        note: '',
      })
      saveAll()
      ElMessage.success(`已新增参数"${value.trim()}"`)
    }
  } catch {
    /* cancel */
  }
}

async function handleRemoveParameter(rowId: string, paramName: string): Promise<void> {
  try {
    await ElMessageBox.confirm(`确认删除参数"${paramName}"？`, '删除确认', {
      confirmButtonText: '确认删除',
      cancelButtonText: '取消',
      type: 'warning',
    })
    parameterEvaluation.value = parameterEvaluation.value.filter((r) => r.id !== rowId)
    saveAll()
    ElMessage.success(`已删除"${paramName}"`)
  } catch {
    /* cancel */
  }
}

/** PD/LGD：manualTermPd=true 表示用户覆写期限折算PD，不再用外部映射自动重算 */
function updatePdLgd(
  rowId: string,
  field: keyof PdLgdCalcRow,
  value: unknown,
  manualTermPd = false,
): void {
  const row = pdLgdRows.value.find((r) => r.id === rowId)
  if (!row) return
  ;(row as Record<string, unknown>)[field] = value
  if (field === 'termAdjustedPd' && manualTermPd) {
    recomputePdLgd(row, false)
  } else if (field === 'externalMappedPd' || field === 'remainingMonths') {
    recomputePdLgd(row, true)
  } else if (field === 'lgd' || field === 'bookBalance') {
    recomputePdLgd(row, false)
  } else if (field === 'priorHistoricalLossRate') {
    /* display only */
  }
  saveAll()
}

async function handleAddPdLgd(): Promise<void> {
  try {
    const { value } = await ElMessageBox.prompt('请输入投资项目/组合名称', '新增PD/LGD测算行', {
      confirmButtonText: '确认',
      cancelButtonText: '取消',
      inputPattern: /\S+/,
      inputErrorMessage: '名称不能为空',
    })
    if (value?.trim()) {
      const row = emptyPdLgd(value.trim())
      recomputePdLgd(row, true)
      pdLgdRows.value.push(row)
      saveAll()
      ElMessage.success('已新增测算行')
    }
  } catch {
    /* cancel */
  }
}

async function removePdLgd(rowId: string): Promise<void> {
  try {
    await ElMessageBox.confirm('确认删除该测算行？', '删除确认', {
      confirmButtonText: '确认删除',
      cancelButtonText: '取消',
      type: 'warning',
    })
    pdLgdRows.value = pdLgdRows.value.filter((r) => r.id !== rowId)
    saveAll()
  } catch {
    /* cancel */
  }
}

function updateLossRate(rowId: string, field: keyof LossRateCalcRow, value: unknown): void {
  const row = lossRateRows.value.find((r) => r.id === rowId)
  if (!row) return
  ;(row as Record<string, unknown>)[field] = value
  if (
    field === 'lossRate' ||
    field === 'forwardLookingAdj' ||
    field === 'bookBalance'
  ) {
    recomputeLossRate(row)
  }
  saveAll()
}

async function handleAddLossRate(): Promise<void> {
  try {
    const { value } = await ElMessageBox.prompt('请输入投资项目/组合名称', '新增损失率法测算行', {
      confirmButtonText: '确认',
      cancelButtonText: '取消',
      inputPattern: /\S+/,
      inputErrorMessage: '名称不能为空',
    })
    if (value?.trim()) {
      const row = emptyLossRate(value.trim())
      recomputeLossRate(row)
      lossRateRows.value.push(row)
      saveAll()
      ElMessage.success('已新增测算行')
    }
  } catch {
    /* cancel */
  }
}

async function removeLossRate(rowId: string): Promise<void> {
  try {
    await ElMessageBox.confirm('确认删除该测算行？', '删除确认', {
      confirmButtonText: '确认删除',
      cancelButtonText: '取消',
      type: 'warning',
    })
    lossRateRows.value = lossRateRows.value.filter((r) => r.id !== rowId)
    saveAll()
  } catch {
    /* cancel */
  }
}

const pdLgdSummary: SummaryMethod<PdLgdCalcRow> = ({ columns, data }) =>
  columns.map((col, idx) => {
    if (idx === 0) return '合计'
    const prop = (col as { property?: string }).property
    if (col.label === '账面余额') return fmtNum(calcSumColumn(data.map((r) => r.bookBalance)))
    if (col.label === '预期信用损失' || prop === 'eclAmount') {
      return fmtNum(calcSumColumn(data.map((r) => r.eclAmount)))
    }
    return ''
  })

const lossRateSummary: SummaryMethod<LossRateCalcRow> = ({ columns, data }) =>
  columns.map((col, idx) => {
    if (idx === 0) return '合计'
    if (col.label === '账面余额') return fmtNum(calcSumColumn(data.map((r) => r.bookBalance)))
    if (col.label === '预期信用损失') return fmtNum(calcSumColumn(data.map((r) => r.eclAmount)))
    return ''
  })

function handleConclusionChange(): void {
  saveAll()
}

async function handleAi(_section: string): Promise<void> {
  if (props.isReadonly) return
  const text = await generateAndConfirm(
    'ecl-method-evaluation',
    conclusion.value || '',
    {},
    'AI 审计结论',
  )
  if (text) {
    conclusion.value = text
    handleConclusionChange()
  }
}

defineExpose({
  toJSON: () => ({
    methodEvaluation: methodEvaluation.value,
    groupBasis: groupBasis.value,
    parameterEvaluation: parameterEvaluation.value,
    pdLgdRows: pdLgdRows.value,
    lossRateRows: lossRateRows.value,
    conclusion: conclusion.value,
  }),
})
</script>

<style scoped>
.g4-tab-ecl-measurement {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}

.objective-alert {
  margin-bottom: 12px;
}

.tab-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  flex-wrap: wrap;
  gap: 8px;
}
.tab-toolbar .toolbar-left,
.tab-toolbar .toolbar-right {
  display: flex;
  gap: 8px;
  align-items: center;
}
.tab-toolbar .chip-wrap {
  display: inline-flex;
  align-items: center;
}

.methodology-context {
  margin-bottom: 12px;
  padding: 12px 16px;
  background: #fffbeb;
  border-left: 4px solid #f59e0b;
  border-radius: 4px;
  font-size: 12px;
  line-height: 1.8;
}
.methodology-context p { margin: 0 0 4px; }
.methodology-context ul { margin: 0; padding-left: 18px; }
.methodology-context li { margin-bottom: 2px; }

.flow-hint {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}
.flow-arrow {
  color: #909399;
  font-size: 12px;
}

.procedure-details {
  margin-bottom: 14px;
  padding: 8px 12px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 4px;
  font-size: 12px;
}
.procedure-details summary {
  cursor: pointer;
  font-weight: 600;
  color: #475569;
}
.procedure-list {
  margin: 8px 0 0;
  padding-left: 18px;
  line-height: 1.7;
  color: #64748b;
}

.section-card { margin-bottom: 16px; }
.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.section-title { font-weight: 600; font-size: 14px; }
.section-actions { display: flex; gap: 8px; align-items: center; }

.rate-tabs { border: none; box-shadow: none; }
.rate-tabs :deep(.el-tabs__content) { padding: 12px 0 0; }
.tab-hint {
  margin-left: 4px;
  font-size: 11px;
  color: #94a3b8;
  background: transparent;
}
.sub-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
  flex-wrap: wrap;
}
.formula-tip {
  font-size: 11px;
  color: #64748b;
  flex: 1;
  min-width: 200px;
}

.ecl-table { font-size: var(--wp-font-size, 13px); }
.check-content-text { color: #606266; font-size: 12px; }
.name-cell {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 4px;
}
.compact-num { width: 100%; }
.formula-cell {
  color: #2563eb;
  font-variant-numeric: tabular-nums;
  cursor: help;
}
.formula-input :deep(.el-input__inner) {
  color: #2563eb;
}
.rate-warn {
  color: #ea580c !important;
  font-weight: 600;
}
.variance-tip {
  margin: 8px 0 0;
  font-size: 12px;
  color: #c2410c;
  background: #fff7ed;
  padding: 6px 10px;
  border-radius: 4px;
}

.audit-text-extras {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: 8px;
  margin-top: 14px;
}

.g4-guide-details { margin-top: 16px; }
.g4-guide-details summary {
  cursor: pointer;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
  font-weight: 600;
}
.g4-guide-content {
  padding: 8px 12px;
  background: #fffbeb;
  border-left: 3px solid #f59e0b;
  margin-top: 6px;
  font-size: 12px;
  line-height: 1.8;
}
.g4-guide-content p { margin: 0; }
</style>
