/**
 * useAlternativeK06Data — K0-6 其他应付款替代程序数据 composable
 *
 * confirmation-alternative-factory-convergence Task 12（K06 迁移，压轴）：
 * 本 composable 已迁移为 Shared_Core 工厂 `createAlternativeConfirmationData` 的
 * 薄适配器——构造 K06 的 AltConfig（**不传 htmlData**，工厂不 init/watch）+ 调工厂
 * + 旁挂 K06 的异质 IO（loadAll / persistAll / importFromSummary / loading）。
 *
 * K06 是异质最大的一套：其 `loadAll` 是 http（render-config 提取 K0-6 sheet）而非
 * 内存 htmlData；其 `persistAll` 逐块 POST checklist-responses（item_id
 * `K0-6-alt-{entity}-block{N}-rows`）。这两处 IO 逐字保留在适配器，**不进工厂**（零回归关键）。
 *
 * 零回归约束：default export、positional 构造 `(wpId, projectId)`、命名比例方法
 * `getPostPaymentRatio`/`getReconcileRatio`、返回对象形状与类型
 * （`UseAlternativeK06DataReturn`，buildPayload 返回 `AlternativeK06Payload`）、
 * 导出 `BLOCK_TITLES_K06` / `getSumFieldsK06` 逐字不变；K06 现有 characterization
 * spec（含 IO mock 断言）不改任何断言必须全绿。
 *
 * Master-Detail（债权人公司→4 区块检查表）
 * 4区块：
 * ① 期后付款检查
 * ② 期末余额支持性证据
 * ③ 本期发生额检查
 * ④ 往来对账/协议证据
 *
 * K06 差异（经 AltConfig 声明）：
 * - format = 'alternative-k06-v1'
 * - getSumFields = getSumFieldsK06（本文件内 SUM_FIELDS_MAP + 导出函数，逐字保留）
 * - defaultBalance = () => ({ item_name: '其他应付款' })
 * - baseAmount = parseNum(c.balance?.closing_balance ?? c.balance?.credit_amount ?? 0)
 * - ratios：block1 postPayment（paymentAmount）→ receipt_check_ratio；
 *           block4 reconcile（amount）→ shipment_check_ratio
 * - metricRatioKeys：metrics.receipt_ratio←postPayment、shipment_ratio←reconcile
 * - calcTotal/calcRatio/parseNum 注入 useK0FormulaEngine（保证与原实现逐字等价）
 *
 * Requirements: 1.1, 1.2, 1.3, 2.7, 3.1, 3.3, 5.2
 */
import { ref, type Ref, type ComputedRef } from 'vue'
import type {
  AlternativeCompany,
  AlternativeD05Metrics,
  CheckRow,
  BlockType,
} from '../../alternativeD05/alternativeD05Types'
import {
  calcCheckRatio,
  calcBlockTotal,
  parseNum,
} from './useK0FormulaEngine'
import { createAlternativeConfirmationData } from '../../coordination/createAlternativeConfirmationData'
import http from '@/utils/http'

// ─── Constants ──────────────────────────────────────────────────────────────

const FORMAT_VERSION = 'alternative-k06-v1' as const
const ITEM_NAME = '其他应付款'

// ─── K0-6 Block 列配置 ──────────────────────────────────────────────────────

/** K0-6 区块①期后付款检查 需求和的字段 */
const BLOCK1_SUM_FIELDS = ['amount', 'paymentAmount']

/** K0-6 区块②期末余额支持性证据 需求和的字段 */
const BLOCK2_SUM_FIELDS = ['amount']

/** K0-6 区块③本期发生额 需求和的字段 */
const BLOCK3_SUM_FIELDS = ['amount']

/** K0-6 区块④往来对账/协议证据 需求和的字段 */
const BLOCK4_SUM_FIELDS = ['amount']

const SUM_FIELDS_MAP: Record<string, string[]> = {
  block1: BLOCK1_SUM_FIELDS,
  block2: BLOCK2_SUM_FIELDS,
  block3: BLOCK3_SUM_FIELDS,
  block4: BLOCK4_SUM_FIELDS,
}

export const BLOCK_TITLES_K06: Record<BlockType, string> = {
  block1: '①期后付款检查',
  block2: '②期末余额支持性证据',
  block3: '③本期发生额检查',
  block4: '④往来对账/协议证据',
}


// ─── Types ──────────────────────────────────────────────────────────────────

export interface AlternativeK06Payload {
  _format: typeof FORMAT_VERSION
  companies: AlternativeCompany[]
}

export interface K01UnrepliedEntity {
  entity_name: string
  confirm_index?: string
  confirm_amount?: number
  unreplied_reason?: string
}

export interface AlternativeK06Summary {
  /** 函证项目（其他应付款） */
  investmentType: string
  /** 年初余额 */
  openingBalance: number
  /** 借方发生额 */
  debitAmount: number
  /** 贷方发生额 */
  creditAmount: number
  /** 期末余额 */
  closingBalance: number
  /** 期后付款检查比例 */
  postCheckRatio: number
  /** 往来对账比例 */
  reconcileRatio: number
}


// ─── Helpers ────────────────────────────────────────────────────────────────

export function getSumFieldsK06(blockType: string): string[] {
  return SUM_FIELDS_MAP[blockType] ?? []
}

// ─── Composable Return ──────────────────────────────────────────────────────

export interface UseAlternativeK06DataReturn {
  companies: Ref<AlternativeCompany[]>
  isDirty: Ref<boolean>
  selectedCompanyId: Ref<string | null>
  loading: Ref<boolean>
  addCompany: (partial?: Partial<AlternativeCompany>) => AlternativeCompany
  deleteCompany: (companyId: string) => void
  updateCompany: (companyId: string, field: string, value: any) => void
  importCompanies: (items: Partial<AlternativeCompany>[]) => void
  importFromSummary: () => Promise<number>
  addBlockRow: (companyId: string, blockType: BlockType) => CheckRow | undefined
  deleteBlockRow: (companyId: string, blockType: BlockType, rowId: string) => void
  updateBlockField: (companyId: string, blockType: BlockType, rowId: string, field: string, value: any) => void
  getBlockTotal: (company: AlternativeCompany, blockType: BlockType) => Record<string, number>
  getPostPaymentRatio: (company: AlternativeCompany) => number | null
  getReconcileRatio: (company: AlternativeCompany) => number | null
  getCompletionStatus: (company: AlternativeCompany) => { completed: number; total: number; rate: number }
  hasAbnormal: (company: AlternativeCompany) => boolean
  metrics: ComputedRef<AlternativeD05Metrics>
  loadAll: () => void
  persistAll: () => AlternativeK06Payload
  buildPayload: () => AlternativeK06Payload
}

// ─── Composable（工厂适配器） ────────────────────────────────────────────────

export default function useAlternativeK06Data(wpId: string, projectId: string): UseAlternativeK06DataReturn {
  const core = createAlternativeConfirmationData({
    format: FORMAT_VERSION,
    getSumFields: getSumFieldsK06,
    // K06 默认 balance 带 item_name='其他应付款'
    defaultBalance: () => ({ item_name: ITEM_NAME }),
    // 比例分母基数：期末余额（closing_balance 缺失时回退 credit_amount；均无/0 → emptyBase='null'）
    baseAmount: (c: AlternativeCompany) =>
      parseNum(c.balance?.closing_balance ?? c.balance?.credit_amount ?? 0),
    ratios: [
      { key: 'postPayment', block: 'block1', fields: ['paymentAmount'], payloadKey: 'receipt_check_ratio' },
      { key: 'reconcile', block: 'block4', fields: ['amount'], payloadKey: 'shipment_check_ratio' },
    ],
    emptyBase: 'null',
    // metrics receipt_ratio←postPayment、shipment_ratio←reconcile
    metricRatioKeys: { receipt: 'postPayment', shipment: 'reconcile' },
    // 注入 useK0FormulaEngine 纯函数，保证与原实现逐字等价
    calcTotal: calcBlockTotal,
    calcRatio: calcCheckRatio,
    parseNum,
    // K06 不传 htmlData → 工厂不 init/watch，改由适配器 loadAll() 自管 http 载入
  })

  // ─── K06 附加能力（旁挂，不进工厂） ───────────────────────────────────────

  const loading = ref(false)

  /**
   * 期后付款检查比例 = 区块①付款金额合计 / 期末余额（命名别名 → core.getRatio）
   */
  function getPostPaymentRatio(company: AlternativeCompany): number | null {
    return core.getRatio(company, 'postPayment')
  }

  /**
   * 往来对账比例 = 区块④对账覆盖金额合计 / 期末余额（命名别名 → core.getRatio）
   */
  function getReconcileRatio(company: AlternativeCompany): number | null {
    return core.getRatio(company, 'reconcile')
  }

  function buildPayload(): AlternativeK06Payload {
    return core.buildPayload() as AlternativeK06Payload
  }

  // ─── Load / Persist（异质 IO，逐字保留原实现，不进工厂） ──────────────────

  function loadAll() {
    loading.value = true
    http
      .get(`/api/workpapers/${wpId}/render-config`)
      .then((res) => {
        const data = res.data?.data ?? res.data
        const sheets = data?.sheets ?? []
        const sheet = sheets.find((s: any) => s.sheet_name?.includes('K0-6'))
        const htmlData = sheet?.html_data
        if (htmlData && htmlData._format === FORMAT_VERSION) {
          core.companies.value = Array.isArray(htmlData.companies)
            ? htmlData.companies.map(core._ensureCompanyId)
            : []
        } else {
          core.companies.value = []
        }
        core.isDirty.value = false
      })
      .catch(() => {
        core.companies.value = []
      })
      .finally(() => {
        loading.value = false
      })
  }

  function persistAll(): AlternativeK06Payload {
    const payload = buildPayload()
    // Persist each company's block rows with item_id prefix pattern
    for (const company of core.companies.value) {
      const entityKey = company._company_id || company.entity_name || 'unknown'
      const blocks: BlockType[] = ['block1', 'block2', 'block3', 'block4']
      for (let i = 0; i < blocks.length; i++) {
        const itemId = `K0-6-alt-${entityKey}-block${i + 1}-rows`
        const rows = core._getBlockRows(company, blocks[i])
        http.post(`/api/workpapers/${wpId}/checklist-responses`, {
          item_id: itemId,
          remark: JSON.stringify(rows),
        }).catch(() => { /* silent */ })
      }
    }
    core.isDirty.value = false
    return payload
  }

  /**
   * 从 K0-1 函证汇总表带入未回函公司（对标 D0-1→D0-6 模式）
   * 调用后端 API 获取 K0-1 未回函列表，按 confirm_index 去重后插入
   * @returns 新增公司数量
   *
   * 逐字保留原实现：直接 push 带 closing_balance 的公司（core.importCompanies
   * 不带 closing_balance 语义，故此处保留原内联 push + core._generateId 以零回归）。
   */
  async function importFromSummary(): Promise<number> {
    loading.value = true
    try {
      const res = await http.get<K01UnrepliedEntity[]>(
        `/api/workpapers/${wpId}/k0/unreplied-entities`,
        { params: { sheet: 'K0-6' } },
      )
      const entities: K01UnrepliedEntity[] = res.data?.data ?? res.data ?? []
      if (!entities.length) return 0

      const existingIndexes = new Set(
        core.companies.value.map((c) => c.confirm_index).filter(Boolean),
      )
      const newItems = entities.filter(
        (e) => !e.confirm_index || !existingIndexes.has(e.confirm_index),
      )
      if (!newItems.length) return 0

      const maxSeq = core.companies.value.reduce((max, c) => Math.max(max, c.seq ?? 0), 0)
      newItems.forEach((item, i) => {
        core.companies.value.push({
          _company_id: core._generateId(),
          seq: maxSeq + i + 1,
          entity_name: item.entity_name || '',
          confirm_index: item.confirm_index,
          _source: 'auto',
          sampling: {},
          balance: {
            item_name: ITEM_NAME,
            closing_balance: item.confirm_amount ?? 0,
          },
          block1_rows: [],
          block2_rows: [],
          block3_rows: [],
          block4_rows: [],
          conclusion: {},
        })
      })
      core.isDirty.value = true
      return newItems.length
    } finally {
      loading.value = false
    }
  }

  // ─── Init（保留原 init 时机：构造末尾 http loadAll） ──────────────────────

  loadAll()

  return {
    ...core,
    loading,
    getPostPaymentRatio,
    getReconcileRatio,
    importFromSummary,
    loadAll,
    persistAll,
    // 工厂 buildPayload 返回 {_format:string,...}，收窄为 AlternativeK06Payload
    buildPayload,
  }
}
