import type { Meta, StoryObj } from '@storybook/vue3'
import TableSearchBar from '@/components/common/TableSearchBar.vue'

const meta = {
  title: 'Common/TableSearchBar',
  component: TableSearchBar,
  tags: ['autodocs'],
} satisfies Meta<typeof TableSearchBar>

export default meta
type Story = StoryObj<typeof meta>

export const Default: Story = {
  args: {
    isVisible: true,
    keyword: '',
    matchInfo: '0/0',
    hasMatches: false,
    caseSensitive: false,
  },
}

export const WithMatches: Story = {
  args: {
    isVisible: true,
    keyword: '银行',
    matchInfo: '1/3',
    hasMatches: true,
    caseSensitive: false,
  },
}

export const WithReplace: Story = {
  args: {
    isVisible: true,
    keyword: '应收',
    replaceText: '应付',
    matchInfo: '2/5',
    hasMatches: true,
    caseSensitive: false,
    showReplace: true,
  },
}

export const CaseSensitive: Story = {
  args: {
    isVisible: true,
    keyword: 'ABC',
    matchInfo: '0/0',
    hasMatches: false,
    caseSensitive: true,
  },
}
