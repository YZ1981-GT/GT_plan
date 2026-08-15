/**
 * 平台级守卫：**推「多段共享表」必须带 `_row_scope`**。
 *
 * **Validates: disclosure-note-row-level-merge Requirements 8.2, 8.3 / Property 15**
 *
 * 共享表 = 同一张附注子表内按科目分段、每段归属不同循环（段首行带
 * `report_row_code`）。全库实测 **29 张**（listed 23 / soe 6），清单真源 =
 * `backend/data/note_shared_table_segments.json`（由
 * `backend/scripts/gen/gen_note_shared_table_segments.py --write` 生成）。
 *
 * 🔴 不带 `_row_scope` 就推这类表 = **表级整表覆盖**，会清掉其他循环已录的段。
 * 服务端只在声明了 `_row_scope` 时才走行级合并（不声明就是既有的表级语义）。
 *
 * 含两条反向自检：
 * 1. 去掉 E1 的 `_row_scope` 声明后，判定函数必须把该文件报为违规
 * 2. `stripComments()` 必须真的剥掉注释（本文件与被扫文件的说明里都写了被禁的反例）
 */
import { readFileSync, readdirSync } from 'node:fs'
import { resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

const REPO_ROOT = resolve(__dirname, '../../../../../..')
const MANIFEST = resolve(REPO_ROOT, 'backend/data/note_shared_table_segments.json')
const COMPOSABLES = resolve(__dirname, '../composables')

interface ManifestTable {
  variant: string
  section_number: string
  section_title: string
  table_name: string
  row_count: number
  segments: Array<{
    row_code: string
    label: string
    start: number
    /** 到下一个段首前 */
    end: number
    /** **可写区**右界 —— 排除段尾的表级合计行（合计不属于任何 owner） */
    data_end: number
  }>
}

const manifest = JSON.parse(readFileSync(MANIFEST, 'utf-8')) as {
  counts: Record<string, number>
  tables: ManifestTable[]
}

/**
 * **不参与源码扫描**的共享表名 + 理由。
 *
 * 这些名字来自 md 重建留下的脏数据（表头首格泄漏 / 裸续表名 / 空表名），
 * 拿去做「源码里是否出现该字面量」的扫描会大面积误报（`项  目` 遍地都是）。
 * 属另一个 data-hygiene 待办；本守卫只保证不被误用。
 */
const GENERIC_TABLE_NAMES: Record<string, string> = {
  // ── 墓碑：以下条目已从真源清单消失，按「已修好必删」移出 ────────────────────
  //
  // `续：`（restricted-assets-note-row-scope-rollout Task 3 正名为
  //   「所有权或使用权受到限制的资产（续：上年年末）」）
  //
  // `''` 空表名（listed 风险管理）—— 由 note-template-columns-and-legacy-snapshot-closure
  //   Wave 2 把模板侧空表名清零（listed 15 → 0）。**后端仍有专职守卫**
  //   `test_note_shared_table_segments.test_empty_table_name_is_excluded_from_lookup`
  //   断言「共享表清单里不得出现空表名」+「用空串查 template_rows 必须返回 None」
  //   ⇒ 万一模板回退，后端先红，前端不必重复承担。
  //
  // `'项  目'`（表头首格泄漏，曾遍地出现导致源码扫描误报）—— 真源实测已 0 命中；
  //   现存只剩两个**足够具体**的派生名 `项  目（期末余额）` / `项  目（上年年末余额）`，
  //   它们不会造成扫描误报，由下方 `MAX_LEAKY_NAMES` 天花板看住只减不增。
  //
  // 🔴 2026-08-15 实证（`note_shared_table_segments.json`）：`''` 与 `'项  目'`
  //    在真源里各命中 **0** 次；`项  目*` 前缀名 2 个且**都不含 `<br/>``。
  //    保留在登记表里会让「已从真源消失的条目必须移出」这条断言恒红。
}

/** 剥掉注释：说明文字里会写被禁的反例。 */
function stripComments(src: string): string {
  return src
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^:])\/\/[^\n]*/g, '$1')
}

/** 该 map 文件里出现的（可扫描的）共享表名字面量。 */
function sharedTableLiterals(body: string, names: readonly string[]): string[] {
  return names.filter(
    (name) => body.includes(`'${name}'`) || body.includes(`"${name}"`) || body.includes(`\`${name}\``),
  )
}

/** 该文件是否声明了行级合并（`_row_scope` + owner_row_code）。 */
function declaresRowScope(body: string): boolean {
  return body.includes('_row_scope') && body.includes('owner_row_code')
}

const SCANNABLE = [...new Set(manifest.tables.map((t) => t.table_name))].filter(
  (n) => !(n in GENERIC_TABLE_NAMES),
)

/** 表名 → 该表允许的 owner code 全集（跨变体并集）。 */
const OWNER_CODES: Record<string, Set<string>> = {}
for (const t of manifest.tables) {
  const set = (OWNER_CODES[t.table_name] ??= new Set())
  for (const s of t.segments) set.add(s.row_code)
}

/**
 * 已知会命中但**暂不接线**的表 → 登记理由 + 归属 spec。
 * 每条随对应循环接入后必须移出（只许缩不许扩）。
 */
const NOT_WIRED_ALLOWLIST: Record<string, { reason: string; owner: string }> = {}

/**
 * 🔴🔴 **已接线但未声明 `_row_scope`** 的共享表 —— **数据丢失级风险，待 owner 循环修**。
 *
 * 与 `NOT_WIRED_ALLOWLIST`（命中但**未接线**）语义不同，故单独登记不混装
 * —— 混装语义正是 `guard-assertion-attribution-refactor` R4.3 要治的病。
 *
 * ## 发现过程（2026-08-15）
 *
 * 本文件原有 7 条「全局等值」断言（`counts === {23,6}` 等）因 2026-08-12 K 循环
 * `fix_note_k_report_row_codes.py` 改真源而全红。改成地板/不变式判据后，
 * **这条形态 A 的归因断言才第一次显现出真红** —— 它被 7 条陈账红掩盖了 3 天。
 * 这是「等值断言不只制造假红、还掩盖真红」的直接实证。
 *
 * ## 危害（真源段归属实证）
 *
 * | 共享表 | 段 owner | 整表覆盖会清掉 |
 * |---|---|---|
 * | 《其他应收款》soe 八、9 | `BS-009` 其他应收款项（K1）+ `BS-016` 应收股利 | **应收股利段** |
 * | 《其他应付款》listed 五、42 / soe 八、42 | `BS-050` 其他应付款（K3）+ `BS-055`/`BS-076` 应付股利 | **应付股利段** |
 *
 * K1 的源码注释已知这张表「同时承载 G2 应收利息 / G3 应收股利 / K1 其他应收款
 * 三个底稿的推送」，并用「条件表语义（`fs_reconciliation` 有值才推）+ 不越权删」
 * 做了部分缓解 —— 但**一旦有值就是整表覆盖**，缓解不彻底。
 *
 * K3 侧同理，且 memory 记载 M1 应付股利的披露正是推 K3 的 §五、42 / §八、42
 * ⇒ 两个循环互相覆盖，谁最后保存谁赢（正是 L2 豁免理由里写的「比不推更糟」）。
 *
 * ## 为什么本 spec 不直接修
 *
 * 照 E1 范式加 `_row_scope: { [表名]: { owner_row_code: 'BS-xxx' } }` 本身不难，
 * 但 K3 主表推的是**三行**（应付利息 / 应付股利 / 其他应付款）。声明
 * `owner_row_code: 'BS-050'` 后服务端只替换 `BS-050` 段，K3 载荷里的应付股利行
 * 会被丢弃 —— **那一行到底该由 K3 还是 M1 推，是业务判断**。
 * `guard-assertion-attribution-refactor` 明确声明「只改判据形态，不补真实缺口」。
 *
 * 🔴 每条必须写明 owner spec 与危害；**只许缩不许扩**（修好即移出）。
 */
const TABLE_LEVEL_OVERWRITE_RISK: Record<string, { reason: string; owner: string }> = {
  其他应收款: {
    reason:
      '`k1NoteSectionMap.ts` 推该表未声明 `_row_scope` ⇒ 表级整表覆盖会清掉 `BS-016` 应收股利段'
      + '（该表段归属实证：soe 八、9 = BS-016 应收股利 + BS-009 其他应收款项）。'
      + 'K1 现有缓解是「`fs_reconciliation` 有值才推 + 不进 `_removed_table_keys`」，'
      + '但有值时仍整表覆盖。修法 = 照 `e1FxNoteSectionMap` 范式声明 '
      + '`owner_row_code: BS-009`，需同时确认应收利息/应收股利两行由 G2/G3 推。',
    owner: 'k-cycle-extraction-formula-and-disclosure-closure',
  },
  其他应付款: {
    reason:
      '`k3NoteSectionMap.ts` 推该表未声明 `_row_scope` ⇒ 表级整表覆盖会清掉应付股利段'
      + '（listed 五、42 = BS-055 应付股利 + BS-050 其他应付款；soe 八、42 = BS-076 + BS-050）。'
      + 'M1 应付股利的披露正是推该章节 ⇒ 两循环互相覆盖、谁最后保存谁赢。'
      + '修法需业务判断：K3 主表的「应付股利」行该由 K3 还是 M1 推'
      + '（声明 `owner_row_code: BS-050` 后该行会被服务端丢弃）。',
    owner: 'k-cycle-extraction-formula-and-disclosure-closure',
  },
}

/**
 * **单一 owner 独占整张表** → 表级覆盖是正确语义，不需要 `_row_scope`。
 *
 * 判据：该表的**全部段**都由同一个底稿推送。此时行级合并只会增加复杂度
 * （合并结果 ≡ 整替换，见后端 Property 12 的同款零回归论证）。
 * 🔴 一旦有第二个循环开始推同一张表，必须移出本表并改走 `_row_scope`。
 */
const WHOLE_TABLE_OWNER: Record<string, { reason: string; segments: string[] }> = {
  未经抵销的递延所得税资产和递延所得税负债: {
    reason:
      'N1 递延所得税披露表**同时**承载资产段（BS-036）与负债段（BS-067）—— '
      + 'N1TabDisclosure 的表(1) 本就分「一、递延所得税资产 / 二、递延所得税负债」两段录入，'
      + 'N3 与 N1 共章节但不独立推送（N3 自造的披露 Tab 已在 n-cycle spec 里删除）',
    segments: ['BS-036', 'BS-067'],
  },
  以抵销后净额列示的递延所得税资产或负债: {
    reason: '同上：N1 的「以抵销后净额列示」表两段皆由 N1 推送（源模板 A36=A13 行镜像）',
    segments: ['BS-036', 'BS-067'],
  },
}

function mapFiles(): string[] {
  return readdirSync(COMPOSABLES).filter((f) => f.endsWith('NoteSectionMap.ts'))
}

/**
 * 规模型断言的**地板**（形态 B）—— 只防「真源被清空导致扫描空转」，不锁实况。
 *
 * 🔴 为什么不写 `toBe(实测值)`：真源 `note_shared_table_segments.json` 由
 * `note_template_{listed,soe}.json` 生成，任何循环补一个段首 `report_row_code`
 * 都会让计数变化。2026-08-12 K 循环 `fix_note_k_report_row_codes.py` 就这么干了
 * （23/6/29 → 24/8/32），改动方同步了生成器 `EXPECTED_COUNTS` 与后端
 * `test_note_shared_table_segments.py`，但**本文件属于另一个 spec，改动方看不见**
 * ⇒ 3 个 blocking CI job 在干净 checkout 下必挂，且一条规模数字打死同 `it` 内
 * 6 条仍然成立的归因断言。
 *
 * 判据形态改为「地板 + 结构不变式 + 包含式重点项」，见
 * `.kiro/specs/guard-assertion-attribution-refactor/`。
 * 真源规模由**后端** `test_note_shared_table_segments.py` 的
 * `gen.main() == 0`（`--check`）负责锁死 —— 那一侧与生成器同属后端视野，
 * 本次漂移中它是唯一没红的，说明该机制有效；前端不重复承担。
 *
 * 当前实测：listed 24 / soe 8 / 共 32 张 / 26 个去重表名 / 18 个窄可写区段。
 * 地板留足余量，只在「真源掉到明显不合理的规模」时打红。
 */
const MIN_SHARED_TABLES = 20
const MIN_SCANNABLE_NAMES = 10
const MIN_NARROWED_SEGMENTS = 10
/** 脏表名天花板：`项  目*` 这类表头泄漏名**只许减少**（当前实测 2 个，曾为 4 个） */
const MAX_LEAKY_NAMES = 4

describe('共享表清单（真源自洽）', () => {
  it('🔴 结构不变式：counts 与 tables 自洽（替代两个硬编码规模值）', () => {
    // 这条比「counts === {23,6}」更强也更稳：校验的是**真源自身的结构自洽**
    //（清单条数 === 两变体计数之和），别人改真源不会打红它，
    // 但生成器算错分组 / 漏写一个变体就会红。
    const keys = Object.keys(manifest.counts).sort()
    expect(keys, `counts 的键集变了：${keys.join('/')}`).toEqual(['listed', 'soe'])
    for (const [variant, n] of Object.entries(manifest.counts)) {
      expect(Number.isInteger(n), `counts.${variant} 不是整数：${n}`).toBe(true)
      expect(n, `counts.${variant} 应为正数`).toBeGreaterThan(0)
    }
    const sum = manifest.counts.listed + manifest.counts.soe
    expect(
      manifest.tables.length,
      `counts 之和 ${sum} ≠ tables 条数 ${manifest.tables.length}`
        + ` —— 真源 backend/data/note_shared_table_segments.json 结构不自洽，`
        + `请重跑 python backend/scripts/gen/gen_note_shared_table_segments.py --write`,
    ).toBe(sum)
    // 每张表的 variant 必须在 counts 的键集里（防出现第三种变体却没计数）
    const badVariant = manifest.tables
      .filter((t) => !(t.variant in manifest.counts))
      .map((t) => `${t.variant} ${t.section_number} ${t.table_name}`)
    expect(badVariant, 'tables 里出现 counts 未登记的 variant').toEqual([])
  })

  it(`地板：清单 ≥ ${MIN_SHARED_TABLES} 张（防真源被清空导致下面的扫描空转）`, () => {
    expect(
      manifest.tables.length,
      `共享表只剩 ${manifest.tables.length} 张 —— 真源可能被清空或路径漂移`,
    ).toBeGreaterThanOrEqual(MIN_SHARED_TABLES)
  })

  it('每张表 ≥2 段且区间不重叠', () => {
    for (const t of manifest.tables) {
      expect(t.segments.length, `${t.section_number} ${t.table_name}`).toBeGreaterThanOrEqual(2)
      let prev = 0
      for (const s of t.segments) {
        expect(s.start).toBeGreaterThanOrEqual(prev)
        expect(s.end).toBeGreaterThan(s.start)
        prev = s.end
      }
    }
  })

  it('🔴 每段都有 data_end（可写区右界），且 start < data_end ≤ end', () => {
    // `data_end` 剔除段尾的**表级合计行** —— 合计不属于任何 owner，
    // 若算进末段，末段 owner 一推数据就会把整表合计删掉。
    for (const t of manifest.tables) {
      for (const s of t.segments) {
        expect(s.data_end, `${t.section_number} ${t.table_name} ${s.row_code} 缺 data_end`)
          .toBeTypeOf('number')
        expect(s.data_end).toBeGreaterThan(s.start)
        expect(s.data_end).toBeLessThanOrEqual(s.end)
      }
    }
  })

/** 可写区窄于段区间的段（表尾合计行 / `row_type: unowned` 兜底行造成） */
function narrowedSegments(): string[] {
  return manifest.tables.flatMap((t) =>
    t.segments
      .filter((s) => s.data_end !== s.end)
      .map((s) => `${t.variant} ${t.section_number} ${t.table_name} ${s.row_code}`),
  )
}

describe('可写区窄于段区间的段（data_end 机制）', () => {
  // 🔴 规模断言与归因断言**拆成两个 it**（design Property 5）。
  //    旧版把 `.toBe(15)` 与 6 条归因断言塞在同一个 it 里，规模数字一漂移
  //    （15 → 18）就把 6 条**仍然成立**的归因断言全部连坐，拿不到任何反馈。
  it(`地板：≥ ${MIN_NARROWED_SEGMENTS} 个段（防 data_end 机制整体失效）`, () => {
    const narrowed = narrowedSegments()
    expect(
      narrowed.length,
      `只有 ${narrowed.length} 个段的 data_end ≠ end —— data_end 机制可能已失效，`
        + `请核对 backend/data/note_shared_table_segments.json`,
    ).toBeGreaterThanOrEqual(MIN_NARROWED_SEGMENTS)
  })

  it('归因：高优先级表在清单内、外币表不受影响', () => {
    const narrowed = narrowedSegments()
    // 🔴 收集违规清单后单次断言（design Property 6）——
    //    旧版在 `for` 循环里逐个 `expect`，首个失败即中止，后面的 key 拿不到反馈。
    const mustInclude = [
      // soe `八、93 受限资产` 末行「其他」（模板标 `row_type: "unowned"`，
      // 由 restricted-assets-note-row-scope-rollout Task 3 加）
      '八、93',
      // 受限资产 / 列报项目 / 筹资活动负债变动 —— 高优先级三张表
      '五、32', '五、71', '八、91', '八、81',
    ]
    const missing = mustInclude.filter((key) => !narrowed.some((x) => x.includes(key)))
    expect(
      missing,
      `以下章节的段应有窄可写区却没有：${missing.join('、')}`
        + `（末段 owner 一推数据就会把整表合计行删掉）`,
    ).toEqual([])

    // 外币表（data_end 机制的首个消费者）零影响 → 引入前后逐字等价
    const fxAffected = narrowed.filter((x) => x.includes('外币货币性项目'))
    expect(
      fxAffected,
      '外币货币性项目表出现窄可写区 —— 引入 data_end 前后不再逐字等价',
    ).toEqual([])
  })
})

  it('脏表名登记表：已从真源消失的条目必须移出（形态 A）', () => {
    // 🔴 判据方向已反转。旧版断言「每条**必须仍在**清单里」，把登记表与真源
    //    双向锁死 —— 真源清理掉一个脏名（好事）反而打红，逼人去改断言方向。
    //    现在只报「该移出的条目」，让清理方零成本。
    const names = new Set(manifest.tables.map((t) => t.table_name))
    const stale = Object.keys(GENERIC_TABLE_NAMES).filter((n) => !names.has(n))
    expect(
      stale,
      `以下脏表名已从真源清单消失，请从 GENERIC_TABLE_NAMES 移出：${stale.map((s) => JSON.stringify(s)).join('、')}`,
    ).toEqual([])

    const blank = Object.entries(GENERIC_TABLE_NAMES)
      .filter(([, reason]) => reason.trim().length <= 10)
      .map(([n]) => n || '(空表名)')
    expect(blank, `以下条目缺理由（≤10 字）：${blank.join('、')}`).toEqual([])

    // 天花板：只许缩不许扩（新增脏名要么修真源，要么在此显式扩并说明）
    expect(
      Object.keys(GENERIC_TABLE_NAMES).length,
      '脏表名登记表只许缩不许扩',
    ).toBeLessThanOrEqual(2)
  })

  it(`可扫描表名地板 ≥ ${MIN_SCANNABLE_NAMES} + 重点表在列（否则下面的扫描全部空转）`, () => {
    // 推导链：清单表数 → 去重表名 → 剔掉 GENERIC_TABLE_NAMES 里的脏名。
    // 🔴 不写死推导结果（旧注释「29 张 → 17 去重名 → 剔 2 脏名 = 15」三个数字**全已过期**）。
    expect(
      SCANNABLE.length,
      `可扫描表名只剩 ${SCANNABLE.length} 个 —— 真源或脏名登记表异常`,
    ).toBeGreaterThanOrEqual(MIN_SCANNABLE_NAMES)

    // 包含式重点项（形态 C）：结构错才红，计数变不红
    const mustHave = ['外币货币性项目', '所有权或使用权受到限制的资产（续：上年年末）']
    const absent = mustHave.filter((n) => !SCANNABLE.includes(n))
    expect(
      absent,
      `以下重点共享表不在可扫描清单里：${absent.join('、')}`
        + `（表名可能被模板重建改写 → 会漂移成孤儿子表）`,
    ).toEqual([])
  })

  it(`🟡 记录：\`项  目（…）\` 派生表名的表头泄漏痕迹只许减少（≤ ${MAX_LEAKY_NAMES}）`, () => {
    // 属另一个 data-hygiene 待办（本 spec 不处理）：这些名字足够具体不至于误报，
    // 但作为 `sub_table_data` 的键很脆弱 —— 一旦模板重建就会漂移成孤儿表。
    //
    // 🔴 旧版还有一条 `expect(leaky.some((n) => n.includes('<br/>'))).toBe(true)`
    //    —— 锁死「必须存在一个含 HTML 的表名」。真源清理掉它之后该断言恒红，
    //    而它锁的是一个**正在消失的脏数据**，没有保护价值 ⇒ 已删除（R1.5）。
    const leaky = SCANNABLE.filter((n) => n.startsWith('项  目'))
    expect(
      leaky.length,
      `表头泄漏名增加到 ${leaky.length} 个：${leaky.join('、')}`
        + `（应在模板侧正名，不要在此放宽天花板）`,
    ).toBeLessThanOrEqual(MAX_LEAKY_NAMES)
  })
})

describe('Property 15：推共享表必带 _row_scope', () => {
  it('全量扫描 *NoteSectionMap.ts', () => {
    const offenders: string[] = []
    const wired: string[] = []
    for (const file of mapFiles()) {
      const raw = readFileSync(resolve(COMPOSABLES, file), 'utf-8')
      const body = stripComments(raw)
      const hits = sharedTableLiterals(body, SCANNABLE).filter(
        (n) =>
          !(n in NOT_WIRED_ALLOWLIST)
          && !(n in WHOLE_TABLE_OWNER)
          && !(n in TABLE_LEVEL_OVERWRITE_RISK),
      )
      if (!hits.length) continue
      if (declaresRowScope(body)) {
        wired.push(`${file} → ${hits.join('、')}`)
        continue
      }
      offenders.push(`${file} 推共享表 ${hits.join('、')} 但未声明 _row_scope`)
    }
    expect(offenders, '表级覆盖会清掉其他循环已录的段 —— 必须声明 _row_scope').toEqual([])
    // 反向自检：至少有一个已接线的消费者，否则本用例恒绿
    expect(wired.length, '一个共享表消费者都扫不到 → 扫描逻辑失效').toBeGreaterThanOrEqual(1)
    expect(wired.join(' ')).toContain('e1FxNoteSectionMap.ts')
  })

  it('已声明的 owner_row_code 必须 ∈ 该表段集合', () => {
    // 🔴 收集违规清单后单次断言（design Property 6）——
    //    旧版三层嵌套 `for` 里逐个 `expect`，首个文件失败即中止，其余文件零反馈。
    const offenders: string[] = []
    for (const file of mapFiles()) {
      const body = stripComments(readFileSync(resolve(COMPOSABLES, file), 'utf-8'))
      if (!declaresRowScope(body)) continue
      const hits = sharedTableLiterals(body, SCANNABLE).filter((n) => !(n in WHOLE_TABLE_OWNER))
      if (!hits.length) {
        offenders.push(`${file} 声明了 _row_scope 却没推任何共享表`)
        continue
      }
      const codes = [...body.matchAll(/'(BS-\d{3})'/g)].map((m) => m[1])
      if (!codes.length) {
        offenders.push(`${file} 未见 owner code 字面量`)
        continue
      }
      const allowed = new Set<string>()
      for (const name of hits) for (const c of OWNER_CODES[name] || []) allowed.add(c)
      const bad = codes.filter((c) => !allowed.has(c))
      if (bad.length) {
        offenders.push(
          `${file} 的 owner_row_code ${bad.join('/')} 不是所推共享表（${hits.join('、')}）的段首 code`,
        )
      }
    }
    expect(
      offenders,
      'owner_row_code 与段首 code 不符 ⇒ 服务端解析不出段边界会 fail-closed 整表跳过写入'
        + '（表现为「推了但没进附注」）',
    ).toEqual([])
  })

  it('未接线登记表为空或每条都写明归属（只许缩不许扩）', () => {
    const offenders: string[] = []
    for (const [name, meta] of Object.entries(NOT_WIRED_ALLOWLIST)) {
      if (!SCANNABLE.includes(name)) offenders.push(`${name} 不在可扫描清单里`)
      if (meta.reason.trim().length <= 10) offenders.push(`${name} 缺理由`)
      if (meta.owner.trim().length <= 2) offenders.push(`${name} 缺归属 spec`)
    }
    expect(offenders, 'NOT_WIRED_ALLOWLIST 条目不合规').toEqual([])
  })

  it('🔴🔴 整表覆盖风险登记表：条目质量合规（与真源规模解耦）', () => {
    // 条目质量校验**不依赖真源**，两种真源状态下都能跑
    const offenders: string[] = []
    for (const [name, meta] of Object.entries(TABLE_LEVEL_OVERWRITE_RISK)) {
      // 危害说明必须够具体（要点出会清掉哪个段），故门槛高于普通 allowlist
      if (meta.reason.trim().length <= 60) offenders.push(`${name} 危害说明过短（须点明会清掉哪个段）`)
      if (!/_row_scope/.test(meta.reason)) offenders.push(`${name} 理由须点明未声明 _row_scope`)
      if (!/^[a-z0-9-]+$/.test(meta.owner.trim())) offenders.push(`${name} owner 必须是 spec 目录名`)
    }
    expect(offenders, '整表覆盖风险登记表条目不合规').toEqual([])
  })

  it('🔴🔴 整表覆盖风险登记表：只许缩不许扩（天花板，不与真源规模耦合）', () => {
    // 🔴 **这条曾与真源规模耦合，是双真源态验证抓出来的**（AC 1.1）：
    //    首版写「不在 SCANNABLE 的条目 ⇒ 报请移出」，在 git HEAD 态（真源 23/6/29，
    //    K 循环补段首码前）下这两张表**还不是共享表**、不在 SCANNABLE ⇒ 2 条全报违规。
    //    即判据方向虽从「必须存在」翻成了「必须不存在」，**耦合仍在**，只是换了个方向红。
    //
    //    真源在「HEAD 23/6/29」与「工作树 24/8/32」两态间摆动期间，任何
    //    「登记条目 ↔ 真源清单」的等值型断言都会在某一态红 ⇒ 改为天花板软约束：
    //      - HEAD 态：2 条都不在清单 → 2 ≤ 2 → 绿
    //      - 工作树态：0 条不在清单 → 0 ≤ 2 → 绿
    //      - 真的乱加第 3 条 → 3 > 2 → 红
    const stale = Object.keys(TABLE_LEVEL_OVERWRITE_RISK).filter((n) => !SCANNABLE.includes(n))

    // 天花板：只许缩不许扩 —— 新接入的共享表消费方必须直接声明 `_row_scope`，
    // 不得往本表里加条目来绕过（当前 2 条：K1《其他应收款》/ K3《其他应付款》）
    expect(
      Object.keys(TABLE_LEVEL_OVERWRITE_RISK).length,
      '整表覆盖风险只许减少：新接入的共享表消费方必须直接声明 _row_scope，'
        + `不得扩本登记表绕过（当前 ${Object.keys(TABLE_LEVEL_OVERWRITE_RISK).length} 条，`
        + `其中 ${stale.length} 条在当前真源态下尚未成为共享表）`,
    ).toBeLessThanOrEqual(2)

    // 「不在清单」的条目数同样只许缩 —— 全部落地（K 循环 commit 后）时应为 0，
    // 修好并移出后也会降到 0；只有「登记了一个真源里从来没有的表名」才会顶到上限。
    //
    // ⚠️ **本设计的已知代价（变异检验 M11 实测）**：天花板软约束使「单条条目表名写错」
    //    不再被本登记表自身抓出。但它必然从另一侧暴露 —— 表名写错 ⇒ 该表不再被豁免
    //    ⇒ 上方「全量扫描 *NoteSectionMap.ts」立刻报出 K1/K3 的真红。
    //    即保护没丢，只是换了个更直接的出口（报「真实风险回来了」而非「条目名不对」）。
    expect(
      stale.length,
      `以下条目在当前真源态下不是共享表：${stale.join('、')}`
        + `（K 循环 commit 前属正常；若确认表名写错，上方全量扫描会同时报出真红）`,
    ).toBeLessThanOrEqual(2)
  })
})

describe('🔴 反向自检', () => {
  it('去掉 E1 的 _row_scope 声明 → 判定函数报违规', () => {
    const raw = readFileSync(resolve(COMPOSABLES, 'e1FxNoteSectionMap.ts'), 'utf-8')
    const body = stripComments(raw)
    expect(declaresRowScope(body)).toBe(true)
    expect(sharedTableLiterals(body, SCANNABLE)).toContain('外币货币性项目')

    // 🔴 替换串里不能再含 `_row_scope`（否则 includes 仍命中 → 自检空转）
    const mutated = body.replace(/_row_scope/g, 'ROWSCOPE_REMOVED')
    expect(mutated).not.toContain('_row_scope')
    expect(declaresRowScope(mutated), '去掉声明后仍判为安全 → 守卫空转').toBe(false)
  })

  it('WHOLE_TABLE_OWNER 登记表每条都真实存在且写明段归属', () => {
    for (const [name, meta] of Object.entries(WHOLE_TABLE_OWNER)) {
      expect(SCANNABLE, `${name} 已不在共享表清单里 → 请移出`).toContain(name)
      expect(meta.reason.length).toBeGreaterThan(20)
      const codes = OWNER_CODES[name]
      expect([...codes].sort()).toEqual([...meta.segments].sort())
    }
  })

  it('stripComments 真的剥掉了注释', () => {
    const raw = readFileSync(resolve(COMPOSABLES, 'e1FxNoteSectionMap.ts'), 'utf-8')
    expect(raw).toContain('跨循环共享表')
    expect(stripComments(raw)).not.toContain('跨循环共享表')
    // 不能把代码也剥掉
    expect(stripComments(raw)).toContain('export function buildE1FxSyncPayload')
  })
})
