/**

 * D1 sheet 编码 → render-config sheet_name 映射

 * 默认名与 workpaper_template_analysis.json 中 xlsx sheet 名对齐

 */

export interface D1IndexRowDef {

  seq: number

  name: string

  code: string

  group: string

  tabKey: string

  applicable: boolean

}



/** code → 默认 sheet_label（可被 htmlData.sheets 覆盖） */

export const D1_SHEET_LABEL_MAP: Record<string, string> = {

  D1A: '应收票据审计程序表D1A',

  'D1-1': '审定表D1-1',

  'D1-2': '原值明细表（按类别）D1-2',

  'D1-3': '原值明细表（按客户）D1-3',

  'D1-4': '坏账准备明细表D1-4',

  'D1-5': '调整分录汇总表D1-5',

  'D1-6': '应收票据业务模式分析D1-6',

  'D1-7': '应收票据备查簿核对D1-7',

  'D1-8': '应收票据贴现、票据已背书未到期明细表D1-8',

  'D1-9': '应收票据贴息检查表D1-9',

  'D1-10': '应收票据监盘D1-10',

  'D1-11': '关联方关系及交易检查表D1-11',

  'D1-12': '应收票据质押检查表D1-12',

  'D1-13': '应收票据检查表D1-13',

  'D1-14': '应收票据坏账准备会计政策检查D1-14',

  'D1-15': '应收票据坏账准备测试表D1-15',

  'D1-16': '坏账准备转回、核销检查表D1-16',

  附注上市: '附注披露信息（上市公司）',

  附注国企: '附注披露信息（国有企业）',

}



export const D1_INDEX_ROWS: D1IndexRowDef[] = [

  { seq: 1, name: '应收票据审计程序表', code: 'D1A', group: '核心', tabKey: 'procedure', applicable: true },

  { seq: 2, name: '应收票据审定表', code: 'D1-1', group: '核心', tabKey: 'adjudication', applicable: true },

  { seq: 3, name: '原值明细表（按类别）', code: 'D1-2', group: '核心', tabKey: 'detail-category', applicable: true },

  { seq: 4, name: '原值明细表（按客户）', code: 'D1-3', group: '核心', tabKey: 'detail-customer', applicable: true },

  { seq: 5, name: '坏账准备计算表', code: 'D1-4', group: '核心', tabKey: 'bad-debt', applicable: true },

  { seq: 6, name: '调整分录汇总', code: 'D1-5', group: '核心', tabKey: 'adjustment', applicable: true },

  { seq: 7, name: '业务模式分析', code: 'D1-6', group: '分析', tabKey: 'business-model', applicable: true },

  { seq: 8, name: '备查簿核对', code: 'D1-7', group: '检查', tabKey: 'memo', applicable: true },

  { seq: 9, name: '贴现背书明细', code: 'D1-8', group: '检查', tabKey: 'endorsement', applicable: true },

  { seq: 10, name: '贴息检查', code: 'D1-9', group: '检查', tabKey: 'interest', applicable: true },

  { seq: 11, name: '票据监盘', code: 'D1-10', group: '检查', tabKey: 'inventory', applicable: true },

  { seq: 12, name: '关联方检查', code: 'D1-11', group: '检查', tabKey: 'related-party', applicable: true },

  { seq: 13, name: '质押检查', code: 'D1-12', group: '检查', tabKey: 'pledge', applicable: true },

  { seq: 14, name: '一般检查表', code: 'D1-13', group: '检查', tabKey: 'sampling', applicable: true },

  { seq: 15, name: 'ECL会计政策一致性', code: 'D1-14', group: 'ECL', tabKey: 'ecl-policy', applicable: true },

  { seq: 16, name: 'ECL测试数据', code: 'D1-15', group: 'ECL', tabKey: 'ecl-test', applicable: true },

  { seq: 17, name: '转回核销检查', code: 'D1-16', group: '检查', tabKey: 'writeoff', applicable: true },

  { seq: 18, name: '附注披露（上市公司）', code: '附注上市', group: '披露', tabKey: '附注上市', applicable: true },

  { seq: 19, name: '附注披露（国企）', code: '附注国企', group: '披露', tabKey: '附注国企', applicable: true },

]



/** 程序表索引号 → sheet_label */

export const D1_PROC_INDEX_SHEET_MAP: Record<string, string> = {

  'D1-1': D1_SHEET_LABEL_MAP['D1-1'],

  'D1-2': D1_SHEET_LABEL_MAP['D1-2'],

  'D1-3': D1_SHEET_LABEL_MAP['D1-3'],

  'D1-4': D1_SHEET_LABEL_MAP['D1-4'],

  'D1-6': D1_SHEET_LABEL_MAP['D1-6'],

  'D1-7': D1_SHEET_LABEL_MAP['D1-7'],

  'D1-8': D1_SHEET_LABEL_MAP['D1-8'],

  'D1-9': D1_SHEET_LABEL_MAP['D1-9'],

  'D1-10': D1_SHEET_LABEL_MAP['D1-10'],

  'D1-11': D1_SHEET_LABEL_MAP['D1-11'],

  'D1-12': D1_SHEET_LABEL_MAP['D1-12'],

  'D1-13': D1_SHEET_LABEL_MAP['D1-13'],

  'D1-14': D1_SHEET_LABEL_MAP['D1-14'],

  'D1-15': D1_SHEET_LABEL_MAP['D1-15'],

  'D1-16': D1_SHEET_LABEL_MAP['D1-16'],

}



export function resolveD1SheetLabel(

  code: string,

  availableSheets?: Array<{ sheet_name?: string }>,

): string {

  if (availableSheets?.length) {

    const codeRe = new RegExp(`${code.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\s*$`)

    const hit = availableSheets.find(s => s.sheet_name && codeRe.test(s.sheet_name))

    if (hit?.sheet_name) return hit.sheet_name

    if (code === '附注上市') {

      const d = availableSheets.find(s => s.sheet_name?.includes('附注') && s.sheet_name?.includes('上市'))

      if (d?.sheet_name) return d.sheet_name

    }

    if (code === '附注国企') {

      const d = availableSheets.find(s => s.sheet_name?.includes('附注') && (s.sheet_name?.includes('国企') || s.sheet_name?.includes('国有')))

      if (d?.sheet_name) return d.sheet_name

    }

  }

  return D1_SHEET_LABEL_MAP[code] ?? code

}



export function getSheetNameFromD1Code(code: string): string {

  return D1_SHEET_LABEL_MAP[code] ?? code

}



export const D1_VIRTUAL_SCROLL_THRESHOLD = 30

