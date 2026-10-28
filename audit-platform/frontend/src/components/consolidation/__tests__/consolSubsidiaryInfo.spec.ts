/**
 * 基本信息表按企业树带出（spec consol-autotree-linkage-closure R4 / 任务 17）纯逻辑
 */
import { describe, it, expect } from 'vitest'
import type { ConsolTreeNode } from '@/services/consolidationApi'
import {
  alignInfoRows,
  infoRatio,
  mergeImportedInfoRows,
  treeMemberInfos,
  worksheetCompanyColumns,
  type InfoRowLike,
} from '../composables/consolSubsidiaryInfo'

function n(key: string, name: string, extra: Partial<ConsolTreeNode> = {}, children: ConsolTreeNode[] = []): ConsolTreeNode {
  const [code, role] = key.split(':') as [string, ConsolTreeNode['role']]
  return {
    project_id: null, company_code: code, company_name: name, parent_company_code: null, ultimate_company_code: null,
    consol_level: 1, children, node_key: key, role, kind: children.length ? 'aggregate' : 'data', display_name: name,
    relation: null, host_project_id: null, flags: [], via: [], mode: null, ...extra,
  }
}

/** G 集团：差额户、母公司户、合并子公司 A、经 M 间接持有的 S（M 本身也是成员）、分公司不在成员里 */
const TREE = n('G:consol', '某集团', { ultimate_company_code: 'G' }, [
  n('G:consol_elim', '某集团（差额户）'),
  n('G:parent', '某集团（母公司户）', {}, [n('GB:branch', '北京分公司', { relation: 'branch' })]),
  n('A:consol', '甲公司', { parent_company_code: 'G', ultimate_company_code: 'G' }, [n('A:consol_elim', '甲公司（差额户）')]),
  n('M:subsidiary', '中间控股', { parent_company_code: 'G', ultimate_company_code: 'G' }),
  n('S:subsidiary', '乙公司', { parent_company_code: 'M', ultimate_company_code: 'G', via: ['M'] }),
  n('S:subsidiary', '乙公司（重复）', { parent_company_code: 'M' }),
])

interface Row extends InfoRowLike { account_subject: string }
const mk = (): Row => ({
  company_name: '', company_code: '', parent_code: '', ultimate_controller: '', ultimate_controller_code: '',
  holding_type: '直接', indirect_holder: '', account_subject: '', non_common_ratio: null, common_ratio: null, no_consol_ratio: null,
})

describe('treeMemberInfos', () => {
  it('只取根下子公司类成员（树序、去重）；三码与最终控制方取自企业树，间接持有按「经 X」预填', () => {
    const members = treeMemberInfos(TREE)
    expect(members.map((m) => m.company_code)).toEqual(['A', 'M', 'S'])
    expect(members[0]).toEqual({
      company_name: '甲公司', company_code: 'A', parent_code: 'G', ultimate_controller: '某集团', ultimate_controller_code: 'G',
      holding_type: '直接', indirect_holder: '',
    })
    expect(members[2]).toMatchObject({ parent_code: 'M', holding_type: '间接', indirect_holder: '中间控股' })
    expect(treeMemberInfos(null)).toEqual([])
  })
})

describe('alignInfoRows', () => {
  it('树带出的字段覆盖，其余字段按企业代码保留；新企业按树预填；不在树中的已填行留在表尾；空行丢弃；幂等', () => {
    const members = treeMemberInfos(TREE)
    const saved: Row[] = [
      { ...mk(), company_name: '旧名甲', company_code: 'A', parent_code: 'X', account_subject: '长期股权投资', non_common_ratio: 60 },
      { ...mk(), company_name: '已转出公司', company_code: 'Z', account_subject: '其他非流动资产' },
      { ...mk(), company_name: '只填了名称' },
      mk(),
      { ...mk(), company_code: 'S', holding_type: '直接', account_subject: '长期股权投资' },
    ]
    const rows = alignInfoRows(saved, members, mk)
    expect(rows.map((r) => r.company_code)).toEqual(['A', 'M', 'S', 'Z', ''])
    expect(rows[0]).toMatchObject({ company_name: '甲公司', parent_code: 'G', ultimate_controller: '某集团', account_subject: '长期股权投资', non_common_ratio: 60 })
    // 新出现的 M 按树预填；已保存过的 S 保留用户选的「直接」
    expect(rows[1]).toMatchObject({ company_name: '中间控股', holding_type: '直接', account_subject: '' })
    expect(rows[2]).toMatchObject({ company_name: '乙公司', parent_code: 'M', holding_type: '直接', account_subject: '长期股权投资' })
    expect(rows[3].company_name).toBe('已转出公司')
    expect(rows[4].company_name).toBe('只填了名称')
    // 不改入参
    expect(saved[0].company_name).toBe('旧名甲')
    expect(alignInfoRows(rows, members, mk)).toEqual(rows)
    // 全新（无保存）：成员行，间接持有的新企业预填「间接 / 中间控股」
    const fresh = alignInfoRows([mk(), mk()], members, mk)
    expect(fresh.map((r) => [r.company_code, r.holding_type, r.indirect_holder])).toEqual([
      ['A', '直接', ''], ['M', '直接', ''], ['S', '间接', '中间控股'],
    ])
  })
})

describe('worksheetCompanyColumns / infoRatio', () => {
  it('企业树可用时只认企业树（不在树中的行不进企业列），比例取基本信息表填写值；不可用时回退已填行', () => {
    const members = treeMemberInfos(TREE)
    const rows = alignInfoRows([
      { ...mk(), company_code: 'A', common_ratio: 80 },
      { ...mk(), company_name: '已转出公司', company_code: 'Z', non_common_ratio: 30 },
    ], members, mk)
    expect(worksheetCompanyColumns(members, rows)).toEqual([
      { name: '甲公司', code: 'A', ratio: 80 }, { name: '中间控股', code: 'M', ratio: 0 }, { name: '乙公司', code: 'S', ratio: 0 },
    ])
    expect(worksheetCompanyColumns(null, rows).map((c) => c.code)).toEqual(['A', 'M', 'S', 'Z'])
    expect(infoRatio({ non_common_ratio: null, common_ratio: null, no_consol_ratio: 15 })).toBe(15)
    expect(infoRatio(undefined)).toBe(0)
  })
})

describe('mergeImportedInfoRows', () => {
  it('按企业代码只更新可编辑字段（树带出的五列不改），匹配不上的列出并跳过，不新增行', () => {
    const current: Row[] = [{ ...mk(), company_name: '甲公司', company_code: 'A', parent_code: 'G' }]
    const res = mergeImportedInfoRows(current, [
      { company_code: ' A ', company_name: '改名甲', parent_code: 'HACK', account_subject: '长期股权投资', non_common_ratio: 51 },
      { company_code: 'Q', company_name: '外部公司' },
      { company_name: '没代码' },
      {},
    ], ['company_name', 'company_code', 'parent_code', 'account_subject', 'non_common_ratio'])
    expect(res.rows).toHaveLength(1)
    expect(res.rows[0]).toMatchObject({ company_name: '甲公司', parent_code: 'G', account_subject: '长期股权投资', non_common_ratio: 51 })
    expect(res.updated).toBe(1)
    expect(res.unmatched).toEqual(['Q', '没代码', '（未填企业代码）'])
    expect(current[0].account_subject).toBe('')
  })
})
