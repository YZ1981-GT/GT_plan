<template>
  <div class="h1-tab-stocktake-summary">
    <el-alert
      type="info"
      :closable="false"
      class="objective-alert"
      title="审计目标：按「了解管理→盘前检查→现场监盘→分类复盘→统计评价→结论」汇总固定资产监盘结果，证实存在性与账面真实性。"
    />

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <GtIndexChip value="wp:H1-11" :context-project-id="projectId" />
        <el-tag size="small" type="info">盘点 {{ stats.totalCount }} 项</el-tag>
        <el-tag size="small" :type="stats.matchRate >= 95 ? 'success' : 'warning'">
          相符率 {{ stats.matchRate }}%
        </el-tag>
      </div>
      <div class="toolbar-right">
        <el-button size="small" @click="emit('navigate-sheet', 'H1-9')">← H1-9 计划</el-button>
        <el-button size="small" @click="emit('navigate-sheet', 'H1-10')">H1-10 检查表</el-button>
        <el-button size="small" @click="emit('navigate-sheet', 'H1-16')">H1-16 权属</el-button>
        <el-button v-if="!isReadonly" size="small" @click="fieldMode = true">现场简录</el-button>
        <el-button v-if="!isReadonly" size="small" type="primary" plain @click="handleSyncUpstream">从 H1-9/10 回填</el-button>
        <el-button v-if="!isReadonly" size="small" type="warning" plain @click="handlePushConcerns">推送闲置/减值</el-button>
        <el-button size="small" @click="handleExport">导出小结</el-button>
        <el-button size="small" type="default" link @click="handleReview('H1-11')">💬 复核</el-button>
      </div>
    </div>

    <el-alert
      v-if="state.samplePlanGap.value && !state.samplePlanGap.value.ok"
      type="error"
      :closable="false"
      :title="`计划样本量对照：${state.samplePlanGap.value.message}`"
      class="logic-warn"
      show-icon
    />
    <el-tag v-else-if="state.samplePlanGap.value?.plannedSamples" size="small" type="success" class="logic-warn">
      {{ state.samplePlanGap.value.message }}
    </el-tag>
    <el-tag v-if="form.lastAutoSyncAt" size="small" type="info" class="logic-warn">
      H1-10 已自动同步 {{ form.lastAutoSyncAt.slice(0, 19).replace('T', ' ') }}
      <template v-if="form.manualOverrides?.length"> · 手改锁定 {{ form.manualOverrides.length }} 项</template>
    </el-tag>

    <!-- 完工程度闸门 -->
    <el-card id="sec-gate" shadow="never" class="block-card gate-card">
      <template #header>
        <div class="section-title">
          <span>完工程度闸门</span>
          <el-tag :type="state.completenessOk.value ? 'success' : 'warning'" size="small">
            {{ state.completenessOk.value ? '可签署' : `${incompleteCount} 项待补` }}
          </el-tag>
        </div>
      </template>
      <div class="gate-list">
        <div v-for="c in state.completeness.value" :key="c.id" class="gate-item" :class="{ ok: c.ok }">
          <span>{{ c.ok ? '✓' : '○' }} {{ c.label }}</span>
          <span v-if="!c.ok" class="gate-hint">{{ c.hint }}</span>
        </div>
      </div>
    </el-card>

    <el-alert
      v-for="(w, i) in state.logicWarnings.value"
      :key="i"
      type="warning"
      :closable="false"
      :title="w"
      class="logic-warn"
      show-icon
    />

    <!-- 分区导航 -->
    <nav class="sec-nav" aria-label="监盘小结分区">
      <button
        v-for="item in navItems"
        :key="item.id"
        type="button"
        class="sec-btn"
        :class="{ active: activeId === item.id }"
        @click="scrollTo(item.id)"
      >{{ item.label }}</button>
    </nav>

    <!-- 监盘附件（sheet 级） -->
    <div class="attach-bar">
      <span class="attach-label">监盘小结附件</span>
      <ItemAttachment
        v-if="projectId && wpId"
        :project-id="projectId"
        :wp-id="wpId"
        sheet-key="H1-11"
        :item-index="0"
        accept=".pdf,.png,.jpg,.jpeg,.xlsx,.xls,.doc,.docx"
      />
    </div>

    <!-- 〇、仪表板（H1-10 联动） -->
    <el-card id="sec-dash" shadow="never" class="block-card">
      <template #header>
        <div class="section-title">
          <span>〇、监盘结果仪表板（联动 H1-10）</span>
          <el-button size="small" link type="primary" @click="emit('navigate-sheet', 'H1-10')">打开检查表</el-button>
        </div>
      </template>
      <el-row :gutter="12">
        <el-col :span="6"><div class="stat-box"><div class="stat-label">盘点总数</div><div class="stat-value">{{ stats.totalCount }}</div></div></el-col>
        <el-col :span="6"><div class="stat-box success"><div class="stat-label">账实相符</div><div class="stat-value">{{ stats.matchCount }}</div></div></el-col>
        <el-col :span="6"><div class="stat-box warning"><div class="stat-label">盘盈</div><div class="stat-value">{{ stats.surplusCount }}</div></div></el-col>
        <el-col :span="6"><div class="stat-box danger"><div class="stat-label">盘亏</div><div class="stat-value">{{ stats.shortageCount }}</div></div></el-col>
      </el-row>
      <div class="match-rate-bar">
        <span>账实相符率</span>
        <el-progress :percentage="stats.matchRate" :stroke-width="12" :format="() => stats.matchRate + '%'" style="flex:1" />
      </div>
      <el-table v-if="surplusRows.length" :data="surplusRows" border size="small" class="mt-12" max-height="180">
        <el-table-column type="index" width="40" />
        <el-table-column prop="name" label="盘盈资产" min-width="120" />
        <el-table-column prop="diffAmount" label="金额" width="110" align="right">
          <template #default="{ row }">{{ fmtAmt(row.diffAmount) }}</template>
        </el-table-column>
        <el-table-column prop="diffReason" label="原因" min-width="140" />
      </el-table>
      <el-table v-if="shortageRows.length" :data="shortageRows" border size="small" class="mt-8" max-height="180">
        <el-table-column type="index" width="40" />
        <el-table-column prop="name" label="盘亏资产" min-width="120" />
        <el-table-column prop="diffAmount" label="金额" width="110" align="right">
          <template #default="{ row }"><span class="error-amount">{{ fmtAmt(row.diffAmount) }}</span></template>
        </el-table-column>
        <el-table-column prop="diffReason" label="原因" min-width="140" />
      </el-table>
    </el-card>

    <!-- 一、资产负债表日 -->
    <el-card id="sec-bs" shadow="never" class="block-card">
      <template #header><span>一、资产负债表日</span></template>
      <el-input
        v-model="form.bsDateNote"
        type="textarea"
        :autosize="{ minRows: 2 }"
        :disabled="isReadonly"
        placeholder="说明监盘日与资产负债表日的关系、截止性处理…"
        @change="persist"
      />
    </el-card>

    <!-- 二、主要资产存放情况 -->
    <el-card id="sec-loc" shadow="never" class="block-card">
      <template #header>
        <div class="section-title">
          <span>二、主要资产存放情况</span>
          <div class="title-actions">
            <el-button v-if="!isReadonly" size="small" :loading="ocrLoading === 'location'" @click="runOcr('location')">📎 OCR 权证/清单</el-button>
            <el-button v-if="!isReadonly" size="small" type="primary" @click="openLocationDialog()">+ 新增</el-button>
          </div>
        </div>
      </template>
      <p class="hint">提示：存放地点应与产权证/行驶证坐落核对；可 OCR 后确认回写。</p>
      <el-table :data="form.locations" border stripe size="small">
        <el-table-column type="index" label="序" width="44" />
        <el-table-column prop="assetCategory" label="资产类别" min-width="100" />
        <el-table-column prop="assetName" label="资产名称" min-width="120" />
        <el-table-column prop="storageLocation" label="存放地点" min-width="140" />
        <el-table-column prop="certIndex" label="权证/索引" width="120">
          <template #default="{ row }">
            <el-button v-if="row.certIndex" size="small" link type="primary" @click="openIndexPopup(row.certIndex)">{{ row.certIndex }}</el-button>
            <span v-else class="muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="附件" width="100" v-if="wpId">
          <template #default="{ row, $index }">
            <ItemAttachment
              :project-id="projectId"
              :wp-id="wpId"
              sheet-key="H1-11-loc"
              :item-index="$index"
              accept=".pdf,.png,.jpg,.jpeg"
            />
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="" width="100">
          <template #default="{ row }">
            <el-button size="small" link @click="openLocationDialog(row)">编辑</el-button>
            <el-button size="small" link type="danger" @click="state.removeLocation(row.rowId)">删</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 三、了解资产管理情况 -->
    <el-card id="sec-mgmt" shadow="never" class="block-card">
      <template #header><span>三、了解资产管理情况</span></template>
      <el-form label-width="200px" size="small">
        <el-form-item v-for="item in form.mgmtItems" :key="item.id" :label="item.label">
          <el-input v-model="item.answer" :disabled="isReadonly" placeholder="填写了解结果" @change="persist" />
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 四、参与盘点人员 -->
    <el-card id="sec-people" shadow="never" class="block-card">
      <template #header>
        <div class="section-title">
          <span>四、参与盘点人员</span>
          <div class="title-actions">
            <el-button v-if="!isReadonly" size="small" @click="openClientDialog()">+ 企业人员</el-button>
            <el-button v-if="!isReadonly" size="small" @click="openAuditorDialog()">+ 审计人员</el-button>
          </div>
        </div>
      </template>
      <h4 class="sub-h">1. 被审计单位人员</h4>
      <el-table :data="form.clientPersonnel" border size="small">
        <el-table-column type="index" width="40" />
        <el-table-column prop="department" label="部门" min-width="100" />
        <el-table-column prop="headcount" label="人数" width="70" align="right" />
        <el-table-column prop="names" label="姓名" min-width="120" />
        <el-table-column prop="responsibleArea" label="负责区域" min-width="120" />
        <el-table-column v-if="!isReadonly" width="90">
          <template #default="{ row }">
            <el-button size="small" link @click="openClientDialog(row)">编辑</el-button>
            <el-button size="small" link type="danger" @click="state.removeClientPersonnel(row.rowId)">删</el-button>
          </template>
        </el-table-column>
      </el-table>
      <h4 class="sub-h">2. 审计人员</h4>
      <el-table :data="form.auditorPersonnel" border size="small">
        <el-table-column type="index" width="40" />
        <el-table-column prop="names" label="姓名" min-width="140" />
        <el-table-column prop="responsibleArea" label="负责区域" min-width="140" />
        <el-table-column v-if="!isReadonly" width="90">
          <template #default="{ row }">
            <el-button size="small" link @click="openAuditorDialog(row)">编辑</el-button>
            <el-button size="small" link type="danger" @click="state.removeAuditorPersonnel(row.rowId)">删</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 五、盘点前检查程序 -->
    <el-card id="sec-pre" shadow="never" class="block-card">
      <template #header>
        <div class="section-title">
          <span>五、实际盘点前的检查程序</span>
          <el-button
            v-if="!isReadonly"
            size="small"
            :loading="ocrLoading === 'precheck'"
            @click="runOcr('precheck')"
          >📎 OCR 资料</el-button>
        </div>
      </template>
      <el-form-item label="现场观察说明" label-width="110px">
        <div class="field-with-ocr">
          <el-input
            v-model="form.siteObservationNote"
            type="textarea"
            :autosize="{ minRows: 3 }"
            :disabled="isReadonly"
            placeholder="描述现场环境、资产状况、盘点组织情况…"
            @change="persist"
          />
          <el-button
            v-if="!isReadonly"
            size="small"
            :loading="ocrLoading === 'narrative-site'"
            @click="runOcr('narrative', { target: 'siteObservationNote' })"
          >OCR 填入</el-button>
        </div>
      </el-form-item>
      <el-table :data="form.precheckItems" border size="small">
        <el-table-column prop="label" label="检查事项" min-width="200" />
        <el-table-column label="是否取得" width="120">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.obtained" size="small" style="width:100%" @change="persist">
              <el-option label="是" value="Y" />
              <el-option label="否" value="N" />
              <el-option label="不适用" value="NA" />
            </el-select>
            <span v-else>{{ ynLabel(row.obtained) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="索引" width="140">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              v-model="row.indexRef"
              size="small"
              placeholder="如 H1-10"
              @change="persist"
            >
              <template #append>
                <el-button v-if="row.indexRef" @click="openIndexPopup(row.indexRef)">开</el-button>
              </template>
            </el-input>
            <el-button v-else-if="row.indexRef" size="small" link type="primary" @click="openIndexPopup(row.indexRef)">{{ row.indexRef }}</el-button>
            <span v-else class="muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="附件" width="120" v-if="wpId">
          <template #default="{ $index }">
            <ItemAttachment
              :project-id="projectId"
              :wp-id="wpId"
              sheet-key="H1-11-pre"
              :item-index="$index"
            />
          </template>
        </el-table-column>
        <el-table-column prop="remark" label="备注" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.remark" size="small" @change="persist" />
            <span v-else>{{ row.remark || '—' }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 六、实际盘点时间 -->
    <el-card id="sec-time" shadow="never" class="block-card">
      <template #header><span>六、实际盘点时间</span></template>
      <el-form inline size="small">
        <el-form-item label="日期">
          <el-date-picker
            v-model="form.actualDate"
            type="date"
            value-format="YYYY-MM-DD"
            :disabled="isReadonly"
            @change="persist"
          />
        </el-form-item>
        <el-form-item label="开始">
          <el-time-select
            v-model="form.startTime"
            start="06:00"
            step="00:15"
            end="22:00"
            :disabled="isReadonly"
            @change="persist"
          />
        </el-form-item>
        <el-form-item label="结束">
          <el-time-select
            v-model="form.endTime"
            start="06:00"
            step="00:15"
            end="23:45"
            :disabled="isReadonly"
            @change="persist"
          />
        </el-form-item>
        <el-tag v-if="!state.timeRangeOk.value" type="danger" size="small">结束时间须晚于开始时间</el-tag>
      </el-form>
    </el-card>

    <!-- 七、企业实际盘点情况 -->
    <el-card id="sec-company" shadow="never" class="block-card">
      <template #header><span>七、企业实际盘点情况说明</span></template>
      <el-form label-width="100px" size="small">
        <el-form-item label="人员概况">
          <el-input
            v-model="form.companyPersonnelNote"
            type="textarea"
            :autosize="{ minRows: 2 }"
            :disabled="isReadonly"
            placeholder="姓名、部门、岗位…"
            @change="persist"
          />
        </el-form-item>
        <el-form-item label="分组情况">
          <el-table :data="form.groups" border size="small">
            <el-table-column prop="groupNo" label="组别" width="70" />
            <el-table-column label="盘点对象/规格" min-width="160">
              <template #default="{ row }">
                <el-input v-if="!isReadonly" v-model="row.countTarget" size="small" @change="persist" />
                <span v-else>{{ row.countTarget }}</span>
              </template>
            </el-table-column>
            <el-table-column label="记录人" width="120">
              <template #default="{ row }">
                <el-input v-if="!isReadonly" v-model="row.recorder" size="small" @change="persist" />
                <span v-else>{{ row.recorder }}</span>
              </template>
            </el-table-column>
            <el-table-column label="人数" width="90">
              <template #default="{ row }">
                <el-input-number
                  v-if="!isReadonly"
                  v-model="row.headcount"
                  :min="0"
                  size="small"
                  controls-position="right"
                  @change="persist"
                />
                <span v-else>{{ row.headcount }}</span>
              </template>
            </el-table-column>
          </el-table>
        </el-form-item>
        <el-form-item label="特殊情况">
          <el-input
            v-model="form.companySpecialNote"
            type="textarea"
            :autosize="{ minRows: 2 }"
            :disabled="isReadonly"
            @change="persist"
          />
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 八、审计人员复盘记录 -->
    <el-card id="sec-audit" shadow="never" class="block-card">
      <template #header>
        <div class="section-title">
          <span>八、审计人员复盘记录</span>
          <el-button
            v-if="!isReadonly"
            size="small"
            :loading="ocrLoading === 'narrative-obs'"
            @click="runOcr('narrative', { target: 'observationMethod' })"
          >OCR 填入</el-button>
        </div>
      </template>
      <el-form label-width="140px" size="small">
        <el-form-item label="抽样方法">
          <el-input
            v-model="form.samplingMethod"
            type="textarea"
            :autosize="{ minRows: 2 }"
            :disabled="isReadonly"
            placeholder="账面→实物 / 实物→账面…"
            @change="persist"
          />
        </el-form-item>
        <el-form-item label="观察方法">
          <el-input
            v-model="form.observationMethod"
            type="textarea"
            :autosize="{ minRows: 2 }"
            :disabled="isReadonly"
            @change="persist"
          />
        </el-form-item>
        <el-form-item label="盘点时停止流转">
          <el-radio-group v-model="form.movementStopped" :disabled="isReadonly" @change="persist">
            <el-radio value="Y">是</el-radio>
            <el-radio value="N">否</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="全程在场">
          <el-radio-group v-model="form.stayedOnSite" :disabled="isReadonly" @change="persist">
            <el-radio value="Y">是</el-radio>
            <el-radio value="N">否</el-radio>
          </el-radio-group>
        </el-form-item>
      </el-form>

      <div v-for="cat in form.categoryNotes" :key="cat.category" class="cat-block">
        <div class="cat-head">
          <h4>{{ cat.category }}</h4>
          <div class="title-actions">
            <el-input
              v-if="!isReadonly"
              v-model="cat.indexRef"
              size="small"
              style="width:140px"
              placeholder="检查记录索引"
              @change="persist"
            />
            <el-button
              v-if="cat.indexRef"
              size="small"
              link
              type="primary"
              @click="openIndexPopup(cat.indexRef)"
            >打开索引</el-button>
            <el-button
              v-if="!isReadonly && cat.category.startsWith('房屋')"
              size="small"
              :loading="ocrLoading === 'building'"
              @click="runOcr('building', { category: cat.category })"
            >📎 权证 OCR</el-button>
          </div>
        </div>
        <el-form label-width="220px" size="small">
          <el-form-item
            v-for="def in (CATEGORY_CHECK_DEFS[cat.category] || [])"
            :key="def.key"
            :label="def.label"
          >
            <el-input
              v-model="cat.checks[def.key]"
              :disabled="isReadonly"
              placeholder="是/否/说明"
              @change="persist"
            />
          </el-form-item>
          <el-form-item label="补充说明">
            <el-input
              v-model="cat.note"
              type="textarea"
              :autosize="{ minRows: 2 }"
              :disabled="isReadonly"
              @change="persist"
            />
          </el-form-item>
        </el-form>
      </div>
    </el-card>

    <!-- 九、异常情况 -->
    <el-card id="sec-abn" shadow="never" class="block-card">
      <template #header>
        <div class="section-title">
          <span>九、盘点中异常情况说明</span>
          <div class="title-actions">
            <el-button
              v-if="!isReadonly"
              size="small"
              @click="state.mergeAbnormalFromCheck()"
            >并入 H1-10 差异</el-button>
            <el-button
              v-if="!isReadonly"
              size="small"
              :loading="ocrLoading === 'narrative-abn'"
              @click="runOcr('narrative', { target: 'abnormalNote' })"
            >OCR 填入</el-button>
          </div>
        </div>
      </template>
      <el-table
        v-if="state.diffEvidence.value.length"
        :data="state.diffEvidence.value"
        border
        size="small"
        class="mb-8"
        max-height="200"
      >
        <el-table-column prop="name" label="资产" min-width="100" />
        <el-table-column prop="result" label="类型" width="80" />
        <el-table-column prop="diffAmount" label="差额" width="90" align="right">
          <template #default="{ row }">{{ fmtAmt(row.diffAmount) }}</template>
        </el-table-column>
        <el-table-column prop="diffReason" label="原因" min-width="120" />
        <el-table-column label="证据" width="100">
          <template #default="{ row }">
            <a v-if="row.photoUrl" :href="row.photoUrl" target="_blank" rel="noopener">照片</a>
            <el-button size="small" link type="primary" @click="emit('navigate-sheet', 'H1-10')">回检查表</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-input
        v-model="form.abnormalNote"
        type="textarea"
        :autosize="{ minRows: 3 }"
        :disabled="isReadonly"
        placeholder="记录盘点过程中发现的异常、差异及跟进…"
        @change="persist"
      />
    </el-card>

    <!-- 十、复盘记录/统计 -->
    <el-card id="sec-recount" shadow="never" class="block-card">
      <template #header>
        <div class="section-title">
          <span>十、复盘记录与统计</span>
          <div class="title-actions">
            <el-button
              v-if="!isReadonly"
              size="small"
              :loading="ocrLoading === 'recount'"
              @click="runOcr('recount')"
            >📎 OCR 复盘表</el-button>
            <el-button size="small" link type="primary" @click="openIndexPopup(form.recountIndex || 'H1-10')">
              索引 {{ form.recountIndex || 'H1-10' }}
            </el-button>
          </div>
        </div>
      </template>
      <p class="hint">注：复盘样本量应按审计准则确定；下列覆盖率/正确率自动计算。</p>
      <el-form label-width="140px" size="small">
        <el-form-item label="复盘人员">
          <el-input v-model="form.recountPersonnel" :disabled="isReadonly" @change="persist" />
        </el-form-item>
        <el-form-item label="复盘底稿索引">
          <el-input v-model="form.recountIndex" :disabled="isReadonly" placeholder="H1-10" @change="persist" />
        </el-form-item>
      </el-form>
      <el-row :gutter="12" class="mt-8">
        <el-col :span="12">
          <el-form label-width="130px" size="small">
            <el-form-item label="设备总台套">
              <el-input-number v-model="form.recountTotalUnits" :disabled="isReadonly" :min="0" @change="onRecountChange('recountTotalUnits')" />
              <el-tag v-if="form.manualOverrides?.includes('recountTotalUnits')" size="small" class="ml-8" type="info">已锁定</el-tag>
            </el-form-item>
            <el-form-item label="复盘台套">
              <el-input-number v-model="form.recountSampleUnits" :disabled="isReadonly" :min="0" @change="onRecountChange('recountSampleUnits')" />
            </el-form-item>
            <el-form-item label="数量覆盖率">
              <el-tag type="info">{{ fmtPct(rates.unitCoverage) }}</el-tag>
            </el-form-item>
            <el-form-item label="复盘正确台套">
              <el-input-number v-model="form.recountCorrectUnits" :disabled="isReadonly" :min="0" @change="onRecountChange('recountCorrectUnits')" />
            </el-form-item>
            <el-form-item label="数量正确率">
              <el-tag :type="(rates.unitAccuracy ?? 0) >= 95 ? 'success' : 'warning'">{{ fmtPct(rates.unitAccuracy) }}</el-tag>
            </el-form-item>
          </el-form>
        </el-col>
        <el-col :span="12">
          <el-form label-width="140px" size="small">
            <el-form-item label="固定资产总值(元)">
              <el-input-number v-model="form.recountTotalAmount" :disabled="isReadonly" :min="0" :precision="2" @change="onRecountChange('recountTotalAmount')" />
            </el-form-item>
            <el-form-item label="复盘账面值(元)">
              <el-input-number v-model="form.recountSampleAmount" :disabled="isReadonly" :min="0" :precision="2" @change="onRecountChange('recountSampleAmount')" />
            </el-form-item>
            <el-form-item label="金额覆盖率">
              <el-tag type="info">{{ fmtPct(rates.amountCoverage) }}</el-tag>
            </el-form-item>
            <el-form-item label="复盘正确金额">
              <el-input-number v-model="form.recountCorrectAmount" :disabled="isReadonly" :min="0" :precision="2" @change="onRecountChange('recountCorrectAmount')" />
            </el-form-item>
            <el-form-item label="金额正确率">
              <el-tag :type="(rates.amountAccuracy ?? 0) >= 95 ? 'success' : 'warning'">{{ fmtPct(rates.amountAccuracy) }}</el-tag>
            </el-form-item>
          </el-form>
        </el-col>
      </el-row>
    </el-card>

    <!-- 十一、盘点结束工作 -->
    <el-card id="sec-close" shadow="never" class="block-card">
      <template #header><span>十一、盘点结束工作说明</span></template>
      <el-form label-width="200px" size="small">
        <el-form-item label="人员对保管设备熟悉程度">
          <el-select v-model="form.evalFamiliarity" :disabled="isReadonly" style="width:200px" @change="persist">
            <el-option label="好" value="好" />
            <el-option label="一般" value="一般" />
            <el-option label="差" value="差" />
          </el-select>
        </el-form-item>
        <el-form-item label="盘点/复盘责任态度">
          <el-select v-model="form.evalAttitude" :disabled="isReadonly" style="width:200px" @change="persist">
            <el-option label="好" value="好" />
            <el-option label="一般" value="一般" />
            <el-option label="差" value="差" />
          </el-select>
        </el-form-item>
        <el-form-item label="被审计单位配合程度">
          <el-select v-model="form.evalCooperation" :disabled="isReadonly" style="width:200px" @change="persist">
            <el-option label="好" value="好" />
            <el-option label="一般" value="一般" />
            <el-option label="差" value="差" />
          </el-select>
        </el-form-item>
        <el-form-item label="已取得盘点差异说明">
          <el-radio-group v-model="form.diffExplanationObtained" :disabled="isReadonly" @change="persist">
            <el-radio value="Y">是</el-radio>
            <el-radio value="N">否</el-radio>
          </el-radio-group>
          <el-input
            v-model="form.diffExplanationIndex"
            size="small"
            style="width:160px;margin-left:12px"
            placeholder="索引"
            :disabled="isReadonly"
            @change="persist"
          />
          <ItemAttachment
            v-if="wpId"
            class="inline-attach"
            :project-id="projectId"
            :wp-id="wpId"
            sheet-key="H1-11-diff"
            :item-index="0"
          />
        </el-form-item>
        <el-form-item label="已取得复盘抽查情况表">
          <el-radio-group v-model="form.sampleTableObtained" :disabled="isReadonly" @change="persist">
            <el-radio value="Y">是</el-radio>
            <el-radio value="N">否</el-radio>
          </el-radio-group>
          <el-input
            v-model="form.sampleTableIndex"
            size="small"
            style="width:160px;margin-left:12px"
            placeholder="索引"
            :disabled="isReadonly"
            @change="persist"
          />
          <ItemAttachment
            v-if="wpId"
            class="inline-attach"
            :project-id="projectId"
            :wp-id="wpId"
            sheet-key="H1-11-sample"
            :item-index="0"
          />
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 结论与签署 -->
    <el-card id="sec-conclusion" shadow="never" class="block-card">
      <template #header>
        <div class="section-title">
          <span>监盘总结与审计结论</span>
          <div class="title-actions">
            <el-button v-if="!isReadonly" size="small" @click="handleRuleDraft">规则起草</el-button>
            <el-button v-if="!isReadonly" size="small" type="primary" :loading="aiLoading" @click="handleAiDraft">AI 起草</el-button>
          </div>
        </div>
      </template>
      <el-alert
        v-if="!state.completenessOk.value"
        type="warning"
        :closable="false"
        title="完工程度闸门未全部通过，仍可签署，但建议先补齐标黄项后再提交复核。"
        class="mb-8"
      />
      <el-input
        v-model="form.conclusion"
        type="textarea"
        :autosize="{ minRows: 4 }"
        :disabled="isReadonly"
        placeholder="总结监盘范围、覆盖率、账实相符情况、异常处理及对报表的影响结论…"
        @change="onConclusionChange"
      />
      <div class="sign-area">
        <div class="sign-row">
          <span>监盘人员：</span>
          <el-input v-if="!isReadonly" v-model="form.preparedBy" size="small" style="width:120px" @change="persist" />
          <span v-else>{{ form.preparedBy || '________' }}</span>
          <span class="ml-16">日期：</span>
          <el-date-picker
            v-if="!isReadonly"
            v-model="form.preparedDate"
            type="date"
            value-format="YYYY-MM-DD"
            size="small"
            @change="persist"
          />
          <span v-else>{{ form.preparedDate || '____年__月__日' }}</span>
        </div>
        <div class="sign-row mt-8">
          <span>复核人员：</span>
          <el-input v-if="!isReadonly" v-model="form.reviewedBy" size="small" style="width:120px" @change="persist" />
          <span v-else>{{ form.reviewedBy || '________' }}</span>
          <span class="ml-16">日期：</span>
          <el-date-picker
            v-if="!isReadonly"
            v-model="form.reviewedDate"
            type="date"
            value-format="YYYY-MM-DD"
            size="small"
            @change="persist"
          />
          <span v-else>{{ form.reviewedDate || '____年__月__日' }}</span>
        </div>
      </div>
    </el-card>

    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>H1-10 变更会自动刷新复盘统计；手改数字会锁定，不再被覆盖。</li>
        <li>完工程度闸门未全绿仍可签署，但建议补齐后再提交复核。</li>
        <li>「推送闲置/减值」写入 H1-4 行与 H1-14-stocktake-concerns；权证 OCR 可同步 H1-16。</li>
        <li>现场简录抽屉适合手机/平板快速记时间与异常；导出 JSON 便于归档。</li>
      </ul>
    </details>

    <!-- 行编辑弹窗：存放地点 -->
    <el-dialog v-model="locDialog.visible" title="编辑存放地点" width="520px" destroy-on-close>
      <el-form label-width="100px" size="small">
        <el-form-item label="资产类别"><el-input v-model="locDialog.draft.assetCategory" /></el-form-item>
        <el-form-item label="资产名称"><el-input v-model="locDialog.draft.assetName" /></el-form-item>
        <el-form-item label="存放地点"><el-input v-model="locDialog.draft.storageLocation" /></el-form-item>
        <el-form-item label="权证/索引"><el-input v-model="locDialog.draft.certIndex" placeholder="如 H1-16 / 权证号" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="locDialog.visible = false">取消</el-button>
        <el-button type="primary" @click="saveLocationDialog">确认回写</el-button>
      </template>
    </el-dialog>

    <!-- 行编辑弹窗：企业人员 -->
    <el-dialog v-model="clientDialog.visible" title="编辑企业盘点人员" width="520px" destroy-on-close>
      <el-form label-width="100px" size="small">
        <el-form-item label="部门"><el-input v-model="clientDialog.draft.department" /></el-form-item>
        <el-form-item label="人数"><el-input-number v-model="clientDialog.draft.headcount" :min="0" /></el-form-item>
        <el-form-item label="姓名"><el-input v-model="clientDialog.draft.names" /></el-form-item>
        <el-form-item label="负责区域"><el-input v-model="clientDialog.draft.responsibleArea" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="clientDialog.visible = false">取消</el-button>
        <el-button type="primary" @click="saveClientDialog">确认回写</el-button>
      </template>
    </el-dialog>

    <!-- 行编辑弹窗：审计人员 -->
    <el-dialog v-model="auditorDialog.visible" title="编辑审计人员" width="480px" destroy-on-close>
      <el-form label-width="100px" size="small">
        <el-form-item label="姓名"><el-input v-model="auditorDialog.draft.names" /></el-form-item>
        <el-form-item label="负责区域"><el-input v-model="auditorDialog.draft.responsibleArea" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="auditorDialog.visible = false">取消</el-button>
        <el-button type="primary" @click="saveAuditorDialog">确认回写</el-button>
      </template>
    </el-dialog>

    <!-- 索引联动弹窗 -->
    <el-dialog v-model="indexPopup.visible" :title="`索引联动：${indexPopup.ref}`" width="420px">
      <p>将跳转到关联工作底稿，便于交叉核对。</p>
      <el-button
        v-for="t in indexPopup.targets"
        :key="t.code"
        type="primary"
        plain
        style="margin:4px"
        @click="goIndex(t.code)"
      >{{ t.code }} {{ t.name }}</el-button>
      <template #footer>
        <el-button @click="indexPopup.visible = false">关闭</el-button>
      </template>
    </el-dialog>

    <!-- OCR 确认回写弹窗（可二次编辑） -->
    <el-dialog v-model="ocrDialog.visible" title="OCR 识别结果确认" width="560px" destroy-on-close>
      <el-alert type="info" :closable="false" title="请核对识别结果，可直接修改后再确认回写。附件已关联本条记录。" class="mb-8" />
      <el-form label-width="120px" size="small">
        <el-form-item v-for="(val, key) in ocrDialog.editable" :key="key" :label="ocrLabel(String(key))">
          <el-input
            v-if="typeof val === 'string' && val.length > 80"
            v-model="ocrDialog.editable[key]"
            type="textarea"
            :autosize="{ minRows: 3 }"
          />
          <el-input v-else v-model="ocrDialog.editable[key]" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="ocrDialog.visible = false">取消</el-button>
        <el-button type="primary" @click="confirmOcrWriteback">确认回写</el-button>
      </template>
    </el-dialog>

    <!-- 现场简录 -->
    <el-drawer v-model="fieldMode" title="现场简录" size="360px" direction="rtl">
      <el-form label-position="top" size="default">
        <el-form-item label="盘点日期">
          <el-date-picker v-model="form.actualDate" type="date" value-format="YYYY-MM-DD" style="width:100%" @change="persist" />
        </el-form-item>
        <el-form-item label="开始 / 结束">
          <div style="display:flex;gap:8px;width:100%">
            <el-time-select v-model="form.startTime" start="06:00" step="00:15" end="22:00" style="flex:1" @change="persist" />
            <el-time-select v-model="form.endTime" start="06:00" step="00:15" end="23:45" style="flex:1" @change="persist" />
          </div>
        </el-form-item>
        <el-form-item label="盘点时停止流转">
          <el-radio-group v-model="form.movementStopped" @change="persist">
            <el-radio value="Y">是</el-radio>
            <el-radio value="N">否</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="全程在场">
          <el-radio-group v-model="form.stayedOnSite" @change="persist">
            <el-radio value="Y">是</el-radio>
            <el-radio value="N">否</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="现场异常速记">
          <el-input v-model="form.abnormalNote" type="textarea" :rows="4" @change="persist" />
        </el-form-item>
        <el-form-item label="拍照/附件">
          <ItemAttachment
            v-if="projectId && wpId"
            :project-id="projectId"
            :wp-id="wpId"
            sheet-key="H1-11-field"
            :item-index="0"
            accept="image/*,.pdf"
          />
        </el-form-item>
        <el-button type="primary" style="width:100%" @click="fieldMode = false">完成</el-button>
      </el-form>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
/**
 * H1TabStocktakeSummary — H1-11 固定资产监盘小结
 * 对齐致同模板结构；支持分区导航、索引弹窗联动、附件+OCR确认回写+二次编辑
 */
import { computed, inject, reactive, ref, toRef } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/utils/http'
import GtIndexChip from '../../GtIndexChip.vue'
import ItemAttachment from '../../ItemAttachment.vue'
import { useH1Stocktake } from '../../composables/useH1Stocktake'
import { useStickySectionNav } from '../../composables/useStickySectionNav'
import {
  CATEGORY_CHECK_DEFS,
  H1_SUMMARY_OCR_LABELS,
  newAuditorRow,
  newClientPersonnelRow,
  newLocationRow,
  type SummaryAuditorRow,
  type SummaryLocationRow,
  type SummaryPersonnelRow,
} from '../../composables/h1StocktakeSummaryModel'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{ (e: 'navigate-sheet', sheetName: string): void }>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const saveResponse = inject<(id: string, val: any) => void>('saveResponse', () => {})

const allResponsesRef = computed(() => props.allResponses)
const state = useH1Stocktake(
  toRef(props, 'wpId'),
  toRef(props, 'projectId'),
  allResponsesRef as any,
  { onSave: (itemId, value) => saveResponse(itemId, value) },
)

const form = computed(() => state.summaryForm.value)
const rates = computed(() => state.recountRates.value)
const isReadonly = computed(() => props.isReadonly)

const stats = computed(() => ({
  totalCount: state.statistics.value.totalChecked,
  matchCount: state.statistics.value.matchCount,
  surplusCount: state.statistics.value.surplusCount,
  shortageCount: state.statistics.value.deficitCount,
  matchRate: Math.round(state.statistics.value.matchRate),
}))
const surplusRows = computed(() => state.surplusRows.value)
const shortageRows = computed(() => state.deficitRows.value)

const navItems = [
  { id: 'sec-gate', label: '闸门' },
  { id: 'sec-dash', label: '仪表板' },
  { id: 'sec-bs', label: '一·截止日' },
  { id: 'sec-loc', label: '二·存放' },
  { id: 'sec-mgmt', label: '三·管理' },
  { id: 'sec-people', label: '四·人员' },
  { id: 'sec-pre', label: '五·盘前' },
  { id: 'sec-time', label: '六·时间' },
  { id: 'sec-company', label: '七·企业盘点' },
  { id: 'sec-audit', label: '八·复盘' },
  { id: 'sec-abn', label: '九·异常' },
  { id: 'sec-recount', label: '十·统计' },
  { id: 'sec-close', label: '十一·结束' },
  { id: 'sec-conclusion', label: '结论' },
]
const { activeId, scrollTo } = useStickySectionNav(navItems)

const fieldMode = ref(false)
const aiLoading = ref(false)
const incompleteCount = computed(
  () => state.completeness.value.filter((c) => !c.ok).length,
)

function persist() {
  state.persistSummaryForm()
}

function onRecountChange(field: string) {
  state.markManualOverride(field)
  persist()
}

function onConclusionChange() {
  state.saveSummaryConclusion(form.value.conclusion)
}

function handleReview(id: string) {
  openReviewDialog(id)
}

function handleSyncUpstream() {
  ElMessageBox.confirm('将用 H1-9/H1-10 数据填入当前为空的字段（不覆盖已手改锁定项）。是否继续？', '从上游回填', {
    confirmButtonText: '回填',
    cancelButtonText: '取消',
  })
    .then(() => {
      state.syncFromUpstream()
      ElMessage.success('已回填，可继续二次编辑')
    })
    .catch(() => {})
}

function handlePushConcerns() {
  const r = state.pushConcernsToH4H14()
  ElMessage.success(`已推送关注 ${r.concernCount} 项（闲置新增 ${r.idleAdded}）→ H1-4 / H1-14`)
}

function handleExport() {
  const rows = state.getExportSnapshot()
  const blob = new Blob([JSON.stringify({ sheet: 'H1-11', exportedAt: new Date().toISOString(), rows, form: form.value }, null, 2)], {
    type: 'application/json;charset=utf-8',
  })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = `H1-11-监盘小结-${form.value.actualDate || 'export'}.json`
  a.click()
  URL.revokeObjectURL(a.href)
  ElMessage.success('已导出 JSON 归档快照')
}

async function handleRuleDraft() {
  const text = state.draftConclusionLocal()
  try {
    await ElMessageBox.confirm(text.slice(0, 500) + (text.length > 500 ? '…' : ''), '规则起草预览', {
      confirmButtonText: '填入结论',
      cancelButtonText: '取消',
    })
    state.applyConclusionDraft(text)
    ElMessage.success('已填入，可继续编辑')
  } catch { /* cancel */ }
}

async function handleAiDraft() {
  if (!props.wpId) return
  aiLoading.value = true
  try {
    const res = await http.post(`/api/workpapers/${props.wpId}/h1/ai-generate`, {
      section: 'stocktake-summary',
      existingContent: form.value.conclusion || '',
      relatedContext: {
        stats: stats.value,
        samplePlan: state.samplePlanGap.value,
        recountRates: rates.value,
        abnormalNote: form.value.abnormalNote,
        completeness: state.completeness.value,
        ruleDraft: state.draftConclusionLocal(),
      },
    }, { _silent: true } as any)
    const text = res.data?.content || res.data?.data?.content || ''
    if (!text) {
      ElMessage.warning('AI 未返回内容，已改用规则起草')
      state.applyConclusionDraft(state.draftConclusionLocal())
      return
    }
    await ElMessageBox.confirm(text.slice(0, 600) + (text.length > 600 ? '…' : ''), 'AI 起草确认', {
      confirmButtonText: '填入结论',
      cancelButtonText: '取消',
    })
    state.applyConclusionDraft(text)
    ElMessage.success('已填入，可继续编辑')
  } catch (e: any) {
    if (e !== 'cancel' && e?.message !== 'cancel') {
      ElMessage.warning('AI 起草失败，已改用规则起草')
      state.applyConclusionDraft(state.draftConclusionLocal())
    }
  } finally {
    aiLoading.value = false
  }
}

function ynLabel(v: string) {
  return ({ Y: '是', N: '否', NA: '不适用' } as Record<string, string>)[v] || '—'
}

function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtPct(v: number | null): string {
  return v == null ? '—' : `${v}%`
}

function ocrLabel(key: string): string {
  return H1_SUMMARY_OCR_LABELS[key] || key
}

// ─── 弹窗：地点 / 人员 ───────────────────────────────────────────────────────

const locDialog = reactive({
  visible: false,
  editingId: '' as string,
  draft: newLocationRow(),
})

function openLocationDialog(row?: SummaryLocationRow) {
  locDialog.editingId = row?.rowId || ''
  locDialog.draft = row ? { ...row } : newLocationRow()
  locDialog.visible = true
}

function saveLocationDialog() {
  if (locDialog.editingId) {
    const idx = form.value.locations.findIndex((r) => r.rowId === locDialog.editingId)
    if (idx >= 0) form.value.locations[idx] = { ...locDialog.draft }
  } else {
    state.addLocation(locDialog.draft)
  }
  persist()
  locDialog.visible = false
}

const clientDialog = reactive({
  visible: false,
  editingId: '' as string,
  draft: newClientPersonnelRow(),
})

function openClientDialog(row?: SummaryPersonnelRow) {
  clientDialog.editingId = row?.rowId || ''
  clientDialog.draft = row ? { ...row } : newClientPersonnelRow()
  clientDialog.visible = true
}

function saveClientDialog() {
  if (clientDialog.editingId) {
    const idx = form.value.clientPersonnel.findIndex((r) => r.rowId === clientDialog.editingId)
    if (idx >= 0) form.value.clientPersonnel[idx] = { ...clientDialog.draft }
  } else {
    state.addClientPersonnel(clientDialog.draft)
  }
  persist()
  clientDialog.visible = false
}

const auditorDialog = reactive({
  visible: false,
  editingId: '' as string,
  draft: newAuditorRow(),
})

function openAuditorDialog(row?: SummaryAuditorRow) {
  auditorDialog.editingId = row?.rowId || ''
  auditorDialog.draft = row ? { ...row } : newAuditorRow()
  auditorDialog.visible = true
}

function saveAuditorDialog() {
  if (auditorDialog.editingId) {
    const idx = form.value.auditorPersonnel.findIndex((r) => r.rowId === auditorDialog.editingId)
    if (idx >= 0) form.value.auditorPersonnel[idx] = { ...auditorDialog.draft }
  } else {
    state.addAuditorPersonnel(auditorDialog.draft)
  }
  persist()
  auditorDialog.visible = false
}

// ─── 索引弹窗联动 ────────────────────────────────────────────────────────────

const INDEX_MAP: { code: string; name: string; patterns: RegExp[] }[] = [
  { code: 'H1-9', name: '监盘计划', patterns: [/H1-9/i, /计划/] },
  { code: 'H1-10', name: '盘点检查表', patterns: [/H1-10/i, /检查|抽盘|复盘/] },
  { code: 'H1-8', name: '减少检查', patterns: [/H1-8/i] },
  { code: 'H1-16', name: '房屋权属', patterns: [/H1-16/i, /权证|房屋|产权/] },
  { code: 'H1-17', name: '运输权属', patterns: [/H1-17/i, /行驶证|车辆/] },
]

const indexPopup = reactive({
  visible: false,
  ref: '',
  targets: [] as { code: string; name: string }[],
})

function openIndexPopup(ref: string) {
  const text = (ref || '').trim()
  if (!text) return
  const hits = INDEX_MAP.filter((m) => m.patterns.some((p) => p.test(text)))
  indexPopup.ref = text
  indexPopup.targets = hits.length ? hits.map(({ code, name }) => ({ code, name })) : [
    { code: 'H1-10', name: '盘点检查表' },
    { code: 'H1-9', name: '监盘计划' },
  ]
  indexPopup.visible = true
}

function goIndex(code: string) {
  indexPopup.visible = false
  emit('navigate-sheet', code)
}

// ─── OCR 上传 → 确认 → 回写 ─────────────────────────────────────────────────

const ocrLoading = ref('')
const ocrDialog = reactive({
  visible: false,
  section: '' as string,
  target: '' as string,
  category: '' as string,
  attachmentId: '',
  editable: {} as Record<string, any>,
})

async function runOcr(
  section: 'location' | 'narrative' | 'precheck' | 'building' | 'recount',
  opts?: { target?: string; category?: string },
) {
  if (props.isReadonly || !props.wpId) return
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = 'image/*,.pdf'
  input.onchange = async () => {
    const file = input.files?.[0]
    if (!file) return
    const loadingKey =
      opts?.target === 'siteObservationNote' ? 'narrative-site'
        : opts?.target === 'observationMethod' ? 'narrative-obs'
          : opts?.target === 'abnormalNote' ? 'narrative-abn'
            : section
    ocrLoading.value = loadingKey
    try {
      const fd = new FormData()
      fd.append('file', file)
      const res = await http.post(
        `/api/workpapers/${props.wpId}/h1/stocktake-summary-ocr?section=${section}`,
        fd,
        { headers: { 'Content-Type': 'multipart/form-data' }, _silent: true } as any,
      )
      const data = res.data?.data ?? res.data ?? {}
      const fields = { ...(data.extracted_fields || {}) }
      if (data.attachment_id) fields.attachment_id = data.attachment_id
      const previewKeys = Object.keys(fields).filter((k) => k !== 'full_text' || !fields.content)
      if (!previewKeys.length && !fields.full_text) {
        ElMessageBox.alert('OCR 完成，未识别到可填充字段，请核对扫描件清晰度', '提示')
        return
      }
      // 去掉超长 full_text 若已有 content，避免弹窗过大；仍保留可编辑摘要
      const editable: Record<string, any> = {}
      for (const [k, v] of Object.entries(fields)) {
        if (k === 'full_text' && fields.content) continue
        if (v === '' || v == null) continue
        editable[k] = v
      }
      if (!Object.keys(editable).length && fields.full_text) {
        editable.content = String(fields.full_text).slice(0, 2000)
      }
      ocrDialog.section = section
      ocrDialog.target = opts?.target || ''
      ocrDialog.category = opts?.category || ''
      ocrDialog.attachmentId = String(data.attachment_id || '')
      ocrDialog.editable = editable
      ocrDialog.visible = true
    } catch {
      ElMessage.warning('OCR 识别失败，请稍后重试或手工录入')
    } finally {
      ocrLoading.value = ''
    }
  }
  input.click()
}

async function confirmOcrWriteback() {
  const f = form.value
  const e = ocrDialog.editable
  const section = ocrDialog.section
  const att = ocrDialog.attachmentId || e.attachment_id || ''

  if (section === 'location') {
    state.addLocation({
      assetCategory: String(e.assetCategory || ''),
      assetName: String(e.assetName || ''),
      storageLocation: String(e.storageLocation || e.address || ''),
      certIndex: String(e.certIndex || e.titleCertNo || ''),
      attachmentId: String(att),
      ocrResult: JSON.stringify(e),
    })
  } else if (section === 'precheck') {
    const type = String(e.documentType || '')
    const hit = f.precheckItems.find((p) => type && p.label.includes(type.slice(0, 4)))
      || f.precheckItems.find((p) => !p.obtained)
    if (hit) {
      hit.obtained = hit.obtained || 'Y'
      if (e.indexSuggestion) hit.indexRef = String(e.indexSuggestion)
      if (e.content) hit.remark = String(e.content)
      hit.attachmentId = String(att)
      hit.ocrResult = JSON.stringify(e)
    }
  } else if (section === 'building') {
    const cat = f.categoryNotes.find((c) => c.category === ocrDialog.category)
      || f.categoryNotes.find((c) => c.category.startsWith('房屋'))
    if (cat) {
      const bits = [
        e.titleCertNo ? `权证号 ${e.titleCertNo}` : '',
        e.owner ? `权利人 ${e.owner}` : '',
        e.address ? `坐落 ${e.address}` : '',
        e.buildingArea ? `面积 ${e.buildingArea}` : '',
        e.qtyMatchHint || '',
        e.content || '',
      ].filter(Boolean)
      cat.note = [cat.note, bits.join('；')].filter(Boolean).join('\n')
      if (e.titleCertNo && !cat.indexRef) cat.indexRef = `权证:${e.titleCertNo}`
    }
    try {
      await ElMessageBox.confirm('是否同步预填至 H1-16 房屋权属检查表？（仅填空）', '同步 H1-16', {
        confirmButtonText: '同步',
        cancelButtonText: '仅写小结',
      })
      const r = state.syncOcrToH116({ ...e, attachment_id: att })
      ElMessage.success(r.mode === 'add' ? '已新增 H1-16 行' : '已更新 H1-16 对应行')
    } catch { /* 仅写小结 */ }
  } else if (section === 'recount') {
    const numKeys = [
      'recountTotalUnits', 'recountSampleUnits', 'recountTotalAmount',
      'recountSampleAmount', 'recountCorrectUnits', 'recountCorrectAmount',
    ] as const
    for (const k of numKeys) {
      if (e[k] != null && e[k] !== '') (f as any)[k] = Number(e[k]) || (f as any)[k]
    }
    if (e.recountPersonnel) f.recountPersonnel = String(e.recountPersonnel)
    if (e.content && !f.abnormalNote) f.abnormalNote = String(e.content)
  } else if (section === 'narrative') {
    const text = String(e.content || e.full_text || '')
    const target = ocrDialog.target as keyof typeof f
    if (target && text) (f as any)[target] = text
  }

  persist()
  ocrDialog.visible = false
  ElMessage.success('已确认回写，可继续二次编辑')
}
</script>

<style scoped>
.h1-tab-stocktake-summary {
  padding: 12px 16px 24px;
  font-size: var(--wp-font-size, 13px);
  max-width: 1100px;
}
.objective-alert { margin-bottom: 10px; }
.logic-warn { margin-bottom: 6px; }
.tab-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
  flex-wrap: wrap;
}
.toolbar-left, .toolbar-right, .title-actions {
  display: flex;
  gap: 6px;
  align-items: center;
  flex-wrap: wrap;
}
.sec-nav {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-bottom: 12px;
  padding: 8px;
  background: var(--el-fill-color-lighter);
  border-radius: 6px;
  position: sticky;
  top: 0;
  z-index: 5;
}
.sec-btn {
  border: 1px solid transparent;
  background: transparent;
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 12px;
  cursor: pointer;
  color: var(--el-text-color-regular);
}
.sec-btn:hover { background: var(--el-fill-color); }
.sec-btn.active {
  background: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
  border-color: var(--el-color-primary-light-5);
}
.attach-bar {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}
.attach-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  padding-top: 6px;
}
.block-card { margin-bottom: 14px; }
.section-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  flex-wrap: wrap;
}
.stat-box {
  text-align: center;
  padding: 10px;
  border-radius: 6px;
  background: var(--el-fill-color-light);
}
.stat-box.success { background: var(--el-color-success-light-9); }
.stat-box.warning { background: var(--el-color-warning-light-9); }
.stat-box.danger { background: var(--el-color-danger-light-9); }
.stat-label { font-size: 12px; color: var(--el-text-color-secondary); }
.stat-value { font-size: 22px; font-weight: 700; margin-top: 2px; }
.match-rate-bar { display: flex; align-items: center; gap: 12px; margin-top: 12px; }
.hint { font-size: 12px; color: var(--el-text-color-secondary); margin: 0 0 8px; }
.sub-h { margin: 12px 0 6px; font-size: 13px; font-weight: 600; }
.cat-block {
  margin-top: 14px;
  padding-top: 10px;
  border-top: 1px dashed var(--el-border-color);
}
.cat-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 8px;
}
.cat-head h4 { margin: 0; font-size: 13px; }
.field-with-ocr { display: flex; flex-direction: column; gap: 6px; width: 100%; }
.inline-attach { display: inline-flex; margin-left: 8px; vertical-align: middle; }
.sign-area { margin-top: 16px; padding-top: 12px; border-top: 1px solid var(--el-border-color-lighter); }
.sign-row { display: flex; align-items: center; gap: 8px; }
.error-amount { color: var(--el-color-danger); }
.muted { color: var(--el-text-color-secondary); }
.mt-8 { margin-top: 8px; }
.mt-12 { margin-top: 12px; }
.mb-8 { margin-bottom: 8px; }
.ml-16 { margin-left: 16px; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
.gate-card { border-left: 3px solid var(--el-color-warning); }
.gate-list { display: grid; grid-template-columns: 1fr 1fr; gap: 6px 12px; }
.gate-item { font-size: 12px; color: var(--el-text-color-secondary); }
.gate-item.ok { color: var(--el-color-success); }
.gate-hint { display: block; font-size: 11px; opacity: 0.85; margin-left: 1.2em; }
.ml-8 { margin-left: 8px; }
</style>
