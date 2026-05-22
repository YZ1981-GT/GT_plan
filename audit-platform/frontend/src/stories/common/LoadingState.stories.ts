import type { Meta, StoryObj } from '@storybook/vue3'
import LoadingState from '@/components/common/LoadingState.vue'

const meta = {
  title: 'Common/LoadingState',
  component: LoadingState,
  tags: ['autodocs'],
} satisfies Meta<typeof LoadingState>

export default meta
type Story = StoryObj<typeof meta>

export const Default: Story = {
  args: {
    loading: true,
    skeleton: true,
    rows: 3,
  },
}

export const SpinnerMode: Story = {
  args: {
    loading: true,
    skeleton: false,
    text: '正在加载数据...',
  },
}

export const EmptyState: Story = {
  args: {
    loading: false,
    empty: true,
    emptyText: '暂无底稿数据',
  },
}

export const ErrorState: Story = {
  args: {
    loading: false,
    error: true,
    errorText: '网络连接失败，请稍后重试',
  },
}

export const ContentLoaded: Story = {
  args: {
    loading: false,
    empty: false,
    error: false,
  },
  render: (args) => ({
    components: { LoadingState },
    setup: () => ({ args }),
    template: '<LoadingState v-bind="args"><p>数据加载完成，这里是实际内容。</p></LoadingState>',
  }),
}
