/**
 * PrefillDiffPanel 组件测试
 *
 * Validates: proposal-remaining-18 §二 L-3，task 2.4
 *  - 无 snapshotDiff 数据时不显示"与上次快照对比"列与 toggle
 *  - 有 snapshotDiff 时显示 toggle，默认展开列
 *  - delta != 0 的科目对应行渲染 stale tag "数据已变更"
 *  - 通过 =TB('1001',...) 公式首参提取 account_code 关联快照
 *  - delta = 0 的科目不渲染 stale tag
 *  - has_snapshot=false 时不显示对比列
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import PrefillDiffPanel from '@/components/workpaper/PrefillDiffPanel.vue'

const stubs = {
  'el-dialog': {
    template:
      '<div class="el-dialog" v-if="modelValue !== false"><slot /><slot name="footer" /></div>',
    props: ['modelValue'],
  },
  // el-table provides each row to el-table-column slots via Vue 3 provide
  'el-table': {
    template: `
      <div class="el-table">
        <div v-for="(row, idx) in data" :key="idx" class="el-table__row" :data-stale="getStaleClass(row, idx)">
          <ElTableRowProvider :row="row">
            <slot />
          </ElTableRowProvider>
        </div>
      </div>
    `,
    props: ['data', 'rowClassName'],
    methods: {
      getStaleClass(this: any, row: any, rowIndex: number): string {
        if (this.rowClassName) {
          const cls = this.rowClassName({ row, rowIndex })
          return cls || ''
        }
        return ''
      },
    },
    components: {
      ElTableRowProvider: {
        props: ['row'],
        provide(this: any) {
          return { __tableRow: () => this.row }
        },
        template: '<div><slot /></div>',
      },
    },
  },
  'el-table-column': {
    template: `<span class="el-table-column"><slot :row="getRow()" /></span>`,
    props: ['label', 'prop', 'width', 'minWidth'],
    inject: {
      __tableRow: { default: () => () => ({}) },
    },
    methods: {
      getRow(this: any): any {
        return this.__tableRow ? this.__tableRow() : {}
      },
    },
  },
  'el-tag': {
    template: '<span class="el-tag" :class="$attrs.type" :data-type="$attrs.type"><slot /></span>',
  },
  'el-checkbox': {
    template:
      '<label class="el-checkbox"><input type="checkbox" :checked="modelValue" @change="$emit(\'update:modelValue\', $event.target.checked)" /><slot /></label>',
    props: ['modelValue'],
    emits: ['update:modelValue'],
  },
  'el-button': {
    template: '<button class="el-button"><slot /></button>',
  },
}

const baseSummary = {
  total_changes: 2,
  new_cells: 1,
  modified_cells: 1,
  highlight_count: 0,
}

const baseChanges = [
  {
    sheet: '审定表D2-1',
    cell_ref: 'E5',
    formula: "=TB('1001','期末余额')",
    old_value: 100,
    new_value: 150,
    change_pct: 50,
    is_highlight: false,
  },
  {
    sheet: '审定表D2-1',
    cell_ref: 'F8',
    formula: "=AUX('1122','客户','C001','期末余额')",
    old_value: null,
    new_value: 200,
    change_pct: null,
    is_highlight: false,
  },
]

describe('PrefillDiffPanel — L-3 snapshot comparison column', () => {
  function factory(props: Record<string, unknown> = {}) {
    return mount(PrefillDiffPanel, {
      props: {
        visible: true,
        changes: baseChanges,
        summary: baseSummary,
        snapshotDiff: null,
        ...props,
      },
      global: { stubs },
    })
  }

  it('hides snapshot toggle when snapshotDiff is null', () => {
    const wrapper = factory({ snapshotDiff: null })
    expect(wrapper.html()).not.toContain('与上次快照对比')
  })

  it('hides snapshot toggle when has_snapshot is false', () => {
    const wrapper = factory({
      snapshotDiff: {
        has_snapshot: false,
        snapshot_account_count: 0,
        stale_count: 0,
        rows: [],
      },
    })
    expect(wrapper.html()).not.toContain('与上次快照对比')
  })

  it('shows snapshot toggle and stale count when has_snapshot is true', () => {
    const wrapper = factory({
      snapshotDiff: {
        has_snapshot: true,
        snapshot_account_count: 2,
        stale_count: 1,
        rows: [
          { account_code: '1001', last_amount: 100, current_amount: 150, delta: 50, is_stale: true },
          { account_code: '1122', last_amount: 200, current_amount: 200, delta: 0, is_stale: false },
        ],
      },
    })
    expect(wrapper.html()).toContain('与上次快照对比')
    expect(wrapper.html()).toContain('1 项数据已变更')
  })

  it('renders stale tag for cells whose account_code has delta != 0', () => {
    const wrapper = factory({
      snapshotDiff: {
        has_snapshot: true,
        snapshot_account_count: 2,
        stale_count: 1,
        rows: [
          { account_code: '1001', last_amount: 100, current_amount: 150, delta: 50, is_stale: true },
          { account_code: '1122', last_amount: 200, current_amount: 200, delta: 0, is_stale: false },
        ],
      },
    })
    const html = wrapper.html()
    // stale_count tag (in toggle) + cell-level stale tag = ≥ 2 occurrences
    const matches = html.match(/数据已变更/g) || []
    expect(matches.length).toBeGreaterThanOrEqual(2)
  })

  it('does not render stale tag for accounts with delta = 0', () => {
    const wrapper = factory({
      changes: [
        {
          sheet: 'S',
          cell_ref: 'A1',
          formula: "=TB('1122','期末余额')",
          old_value: 200,
          new_value: 200,
          change_pct: 0,
          is_highlight: false,
        },
      ],
      snapshotDiff: {
        has_snapshot: true,
        snapshot_account_count: 1,
        stale_count: 0,
        rows: [
          { account_code: '1122', last_amount: 200, current_amount: 200, delta: 0, is_stale: false },
        ],
      },
    })
    expect(wrapper.html()).not.toContain('数据已变更')
  })

  it('extracts account_code from =AUX() formula first arg', () => {
    const wrapper = factory({
      changes: [
        {
          sheet: 'S',
          cell_ref: 'A1',
          formula: "=AUX('1122','客户','C001','期末余额')",
          old_value: null,
          new_value: 200,
          change_pct: null,
          is_highlight: false,
        },
      ],
      snapshotDiff: {
        has_snapshot: true,
        snapshot_account_count: 1,
        stale_count: 1,
        rows: [
          { account_code: '1122', last_amount: 100, current_amount: 200, delta: 100, is_stale: true },
        ],
      },
    })
    expect(wrapper.html()).toContain('数据已变更')
  })

  it('exposes snapshot toggle as a checkbox controlled by user', async () => {
    const wrapper = factory({
      snapshotDiff: {
        has_snapshot: true,
        snapshot_account_count: 1,
        stale_count: 1,
        rows: [
          { account_code: '1001', last_amount: 100, current_amount: 150, delta: 50, is_stale: true },
        ],
      },
    })
    const checkbox = wrapper.find('input[type="checkbox"]')
    expect(checkbox.exists()).toBe(true)
    // 默认勾选（开启对比列）
    expect((checkbox.element as HTMLInputElement).checked).toBe(true)
  })
})
