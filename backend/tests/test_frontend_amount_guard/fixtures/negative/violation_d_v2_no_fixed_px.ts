// No violation: uses CSS variable, not fixed px
const columns = [
  {
    key: 'amount',
    cellRenderer: ({ cellData }: any) => {
      return h('span', { style: { fontSize: 'var(--gt-display-font-size)' } }, cellData)
    },
  },
]
