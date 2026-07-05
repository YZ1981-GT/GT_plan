/**

 * D3 sheet 编码 → render-config sheet_name 映射

 */

export interface D3IndexRowDef {

  seq: number

  name: string

  code: string

  group: string

  applicable: boolean

}



export const D3_SHEET_LABEL_MAP: Record<string, string> = {

  D3: 'D3',

  D3A: '预收账款实质性程序表D3A',

  'D3-1': '审定表D3-1',

  'D3-2': '预收账款明细表D3-2',

  'D3-3': '调整分录汇总表D3-3',

  'D3-4': '预收账款分析表D3-4',

  'D3-5': '账龄1年以上的预收账款检查表D3-5',

  'D3-6': '关联关系及交易检查表D3-6',

  'D3-7': '预收账款检查表D3-7',

  附注上市: '附注披露信息（上市公司）',

  附注国企: '附注披露信息（国有企业）',

}



export const D3_INDEX_ROWS: D3IndexRowDef[] = [

  { seq: 1, name: '预收账款实质性程序表', code: 'D3A', group: '核心', applicable: true },

  { seq: 2, name: '预收账款审定表', code: 'D3-1', group: '核心', applicable: true },

  { seq: 3, name: '预收账款明细表', code: 'D3-2', group: '核心', applicable: true },

  { seq: 4, name: '调整分录汇总', code: 'D3-3', group: '核心', applicable: true },

  { seq: 5, name: '预收账款分析表', code: 'D3-4', group: '分析', applicable: true },

  { seq: 6, name: '账龄1年以上检查', code: 'D3-5', group: '检查', applicable: true },

  { seq: 7, name: '关联方检查', code: 'D3-6', group: '检查', applicable: true },

  { seq: 8, name: '凭证检查', code: 'D3-7', group: '检查', applicable: true },

  { seq: 9, name: '附注披露（上市公司）', code: '附注上市', group: '披露', applicable: true },

  { seq: 10, name: '附注披露（国企）', code: '附注国企', group: '披露', applicable: true },

]



/** 程序表索引号 → sheet_label */

export const D3_PROC_INDEX_SHEET_MAP: Record<string, string> = {

  'D3-1': D3_SHEET_LABEL_MAP['D3-1'],

  'D3-2': D3_SHEET_LABEL_MAP['D3-2'],

  'D3-4': D3_SHEET_LABEL_MAP['D3-4'],

  'D3-5': D3_SHEET_LABEL_MAP['D3-5'],

  'D3-6': D3_SHEET_LABEL_MAP['D3-6'],

  'D3-7': D3_SHEET_LABEL_MAP['D3-7'],

}



export function resolveD3SheetLabel(

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

  return D3_SHEET_LABEL_MAP[code] ?? code

}



export function getSheetNameFromD3Code(code: string): string {

  return D3_SHEET_LABEL_MAP[code] ?? code

}

