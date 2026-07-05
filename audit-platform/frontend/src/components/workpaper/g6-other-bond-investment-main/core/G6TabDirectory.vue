<template>
  <div class="g6-directory">
    <h3 class="sheet-title">底稿目录</h3>

    <div class="directory-layout">
      <!-- 左侧: 编制信息区 -->
      <div class="entity-info">
        <el-descriptions :column="1" border size="small" class="info-desc">
          <el-descriptions-item label="被审计单位">{{ entityName || '——' }}</el-descriptions-item>
          <el-descriptions-item label="截止日">{{ balanceSheetDate || '——' }}</el-descriptions-item>
          <el-descriptions-item label="编制人">{{ preparer || '——' }}</el-descriptions-item>
          <el-descriptions-item label="复核人">{{ reviewer || '——' }}</el-descriptions-item>
        </el-descriptions>

        <!-- 方法论上下文 -->
        <div class="methodology-context">
          <div class="methodology-bar" />
          <div class="methodology-content">
            <strong>关于工作底稿与审计程序索引号对应的说明</strong>
            <p>本底稿目录涵盖G6其他债权投资全部底稿。索引号G6A为程序表，G6-1至G6-4为实质性程序底稿(审定表/明细表/坏账准备/调整分录)，附注分上市公司/国企两版，G0-1至G0-8为投资循环函证底稿。各底稿通过索引号实现交叉引用与跳转。</p>
          </div>
        </div>
      </div>

      <!-- 右侧: 目录表（29行×8列 只读） -->
      <div class="directory-table">
        <el-table :data="directoryRows" border stripe style="width: 100%; font-size: 13px">
          <el-table-column prop="seq" label="序号" width="55" align="center" />
          <el-table-column prop="content" label="底稿名称" min-width="220" />
          <el-table-column label="底稿编码" width="120">
            <template #default="{ row }">
              <GtIndexChip v-if="row.indexCode" :value="row.indexCode" @click="emit('jump', row.indexCode)" />
              <span v-else>-</span>
            </template>
          </el-table-column>
          <el-table-column prop="preparer" label="编制人" width="80" />
          <el-table-column prop="prepareDate" label="编制日期" width="100" />
          <el-table-column prop="reviewer" label="复核人" width="80" />
          <el-table-column prop="reviewDate" label="复核日期" width="100" />
          <el-table-column label="页码" width="55" align="center">
            <template #default="{ row }">{{ row.pages || '-' }}</template>
          </el-table-column>
          <el-table-column label="备注" min-width="80">
            <template #default="{ row }">
              <span v-if="row.status === 'done'" class="status-done">✓ 已完成</span>
              <span v-else-if="row.status === 'pending'" class="status-pending">○ 待完成</span>
              <span v-else>{{ row.remark || '-' }}</span>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * G6TabDirectory.vue — 底稿目录（29行×8列 只读）
 *
 * Spec: .kiro/specs/g6-other-bond-investment-main/ Task 7.4
 * Requirements: 1.1
 *
 * 静态目录页渲染，支持 GtIndexChip 索引跳转
 * 无虚拟滚动（行数<50）
 * 底稿编码|底稿名称|编制人|编制日期|复核人|复核日期|页码|备注
 */
import { ref } from 'vue'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  htmlData: Record<string, any> | null
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const emit = defineEmits<{ jump: [code: string] }>()

// ═══ 编制信息（从htmlData加载） ═══
const entityName = ref(props.htmlData?.entityName || '')
const balanceSheetDate = ref(props.htmlData?.balanceSheetDate || '')
const preparer = ref(props.htmlData?.preparer || '')
const reviewer = ref(props.htmlData?.reviewer || '')

// ═══ 29行目录数据 ═══
interface DirectoryRow {
  seq: number
  content: string
  indexCode: string
  pages: string
  preparer: string
  prepareDate: string
  reviewer: string
  reviewDate: string
  remark: string
  status?: 'done' | 'pending' | ''
}

const directoryRows = ref<DirectoryRow[]>([
  // ═══ main组（本spec） ═══
  { seq: 1, content: '其他债权投资实质性程序表', indexCode: 'G6A', pages: '', preparer: '', prepareDate: '', reviewer: '', reviewDate: '', remark: '', status: '' },
  { seq: 2, content: '其他债权投资审定表', indexCode: 'G6-1', pages: '', preparer: '', prepareDate: '', reviewer: '', reviewDate: '', remark: '', status: '' },
  { seq: 3, content: '其他债权投资明细表', indexCode: 'G6-2', pages: '', preparer: '', prepareDate: '', reviewer: '', reviewDate: '', remark: '', status: '' },
  { seq: 4, content: '坏账准备测算表', indexCode: 'G6-3', pages: '', preparer: '', prepareDate: '', reviewer: '', reviewDate: '', remark: '', status: '' },
  { seq: 5, content: '调整分录汇总', indexCode: 'G6-4', pages: '', preparer: '', prepareDate: '', reviewer: '', reviewDate: '', remark: '', status: '' },
  { seq: 6, content: '附注披露信息（上市公司）', indexCode: 'G6-附注(上市)', pages: '', preparer: '', prepareDate: '', reviewer: '', reviewDate: '', remark: '', status: '' },
  { seq: 7, content: '附注披露信息（国企）', indexCode: 'G6-附注(国企)', pages: '', preparer: '', prepareDate: '', reviewer: '', reviewDate: '', remark: '', status: '' },
  { seq: 8, content: '底稿目录', indexCode: 'G6-目录', pages: '', preparer: '', prepareDate: '', reviewer: '', reviewDate: '', remark: '', status: '' },
  // ═══ SPPI组 ═══
  { seq: 9, content: '业务模式分析', indexCode: 'G6-5', pages: '', preparer: '', prepareDate: '', reviewer: '', reviewDate: '', remark: '', status: '' },
  { seq: 10, content: 'SPPI合同现金流测试', indexCode: 'G6-6', pages: '', preparer: '', prepareDate: '', reviewer: '', reviewDate: '', remark: '', status: '' },
  { seq: 11, content: '实际利率法利息测算', indexCode: 'G6-7', pages: '', preparer: '', prepareDate: '', reviewer: '', reviewDate: '', remark: '', status: '' },
  { seq: 12, content: '盘点倒轧表', indexCode: 'G6-8', pages: '', preparer: '', prepareDate: '', reviewer: '', reviewDate: '', remark: '', status: '' },
  { seq: 13, content: '结存表', indexCode: 'G6-9', pages: '', preparer: '', prepareDate: '', reviewer: '', reviewDate: '', remark: '', status: '' },
  // ═══ ECL组 ═══
  { seq: 14, content: '三阶段划分检查', indexCode: 'G6-10', pages: '', preparer: '', prepareDate: '', reviewer: '', reviewDate: '', remark: '', status: '' },
  { seq: 15, content: '减值测算表', indexCode: 'G6-11', pages: '', preparer: '', prepareDate: '', reviewer: '', reviewDate: '', remark: '', status: '' },
  { seq: 16, content: 'ECL计算底稿', indexCode: 'G6-12', pages: '', preparer: '', prepareDate: '', reviewer: '', reviewDate: '', remark: '', status: '' },
  { seq: 17, content: '凭证检查表', indexCode: 'G6-13', pages: '', preparer: '', prepareDate: '', reviewer: '', reviewDate: '', remark: '', status: '' },
  { seq: 18, content: '减值准备变动核对', indexCode: 'G6-14', pages: '', preparer: '', prepareDate: '', reviewer: '', reviewDate: '', remark: '', status: '' },
  { seq: 19, content: '转回合理性检查', indexCode: 'G6-15', pages: '', preparer: '', prepareDate: '', reviewer: '', reviewDate: '', remark: '', status: '' },
  // ═══ 函证组(G0共享) ═══
  { seq: 20, content: '函证控制表', indexCode: 'G0-1', pages: '', preparer: '', prepareDate: '', reviewer: '', reviewDate: '', remark: '', status: '' },
  { seq: 21, content: '函证发出清单', indexCode: 'G0-2', pages: '', preparer: '', prepareDate: '', reviewer: '', reviewDate: '', remark: '', status: '' },
  { seq: 22, content: '函证回收统计', indexCode: 'G0-3', pages: '', preparer: '', prepareDate: '', reviewer: '', reviewDate: '', remark: '', status: '' },
  { seq: 23, content: '差异核对表', indexCode: 'G0-4', pages: '', preparer: '', prepareDate: '', reviewer: '', reviewDate: '', remark: '', status: '' },
  { seq: 24, content: '替代程序底稿', indexCode: 'G0-5', pages: '', preparer: '', prepareDate: '', reviewer: '', reviewDate: '', remark: '', status: '' },
  { seq: 25, content: '函证样本表', indexCode: 'G0-6', pages: '', preparer: '', prepareDate: '', reviewer: '', reviewDate: '', remark: '', status: '' },
  { seq: 26, content: '函证模板-证券', indexCode: 'G0-7', pages: '', preparer: '', prepareDate: '', reviewer: '', reviewDate: '', remark: '', status: '' },
  { seq: 27, content: '函证模板-债券', indexCode: 'G0-8', pages: '', preparer: '', prepareDate: '', reviewer: '', reviewDate: '', remark: '', status: '' },
  // ═══ 其他 ═══
  { seq: 28, content: '审计说明', indexCode: '', pages: '', preparer: '', prepareDate: '', reviewer: '', reviewDate: '', remark: '', status: '' },
  { seq: 29, content: '审计结论', indexCode: '', pages: '', preparer: '', prepareDate: '', reviewer: '', reviewDate: '', remark: '', status: '' },
])
</script>

<style scoped>
.g6-directory { padding: 12px; font-size: 13px; }
.sheet-title { margin: 0 0 16px; font-size: 15px; font-weight: 600; }

.directory-layout { display: grid; grid-template-columns: 280px 1fr; gap: 16px; }
@media (max-width: 900px) { .directory-layout { grid-template-columns: 1fr; } }

.entity-info { display: flex; flex-direction: column; gap: 12px; }
.info-desc { width: 100%; }

.methodology-context { position: relative; padding: 12px 12px 12px 16px; background: #fffbe6; border-radius: 4px; }
.methodology-bar { position: absolute; left: 0; top: 0; bottom: 0; width: 4px; background: #d48806; border-radius: 4px 0 0 4px; }
.methodology-content { font-size: 12px; color: #614700; }
.methodology-content strong { display: block; margin-bottom: 4px; font-size: 13px; }
.methodology-content p { margin: 0; line-height: 1.6; }

.directory-table { overflow: auto; }
.status-done { color: #52c41a; font-size: 12px; }
.status-pending { color: #909399; font-size: 12px; }
</style>
