import type { RouteLocationNormalizedLoaded } from 'vue-router'

/**
 * DefaultLayout 里页面组件与 ErrorBoundary 的 key（spec platform-perf-hotspots R6）。
 *
 * 默认 `fullPath`：任何 query 变化都重挂页面 —— 多数页面依赖这一点（底稿编辑器 `?sheet=&cell=`、附注、
 * 调整分录等只在挂载时读 query）。
 * 路由 `meta.reuseOnQueryChange` 为真的页面自己监听会变的 query，只在路径或 `?year=` 变化时重挂
 * （年度变了数据要整页重取，仍按原样重挂）。底稿列表切视图原先整页重挂、全部接口重取。
 */
export function routeViewKey(
  route: Pick<RouteLocationNormalizedLoaded, 'path' | 'fullPath' | 'query' | 'meta'>,
): string {
  if (route.meta?.reuseOnQueryChange !== true) return route.fullPath
  const year = route.query?.year
  const yearPart = Array.isArray(year) ? year.join(',') : (year ?? '')
  return yearPart ? `${route.path}?year=${yearPart}` : route.path
}
