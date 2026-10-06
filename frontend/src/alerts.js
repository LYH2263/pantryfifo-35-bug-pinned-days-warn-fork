import { ref } from 'vue'
import { api } from './api'

// 顶条共享状态：任何页面改了钉值 / warn_days / 下架 / 消费后都调 refreshAlerts，
// 保证顶条与批次详情对同一批得出同一紧急结论（后端同一规则重算）。
export const alerts = ref([])

export async function refreshAlerts() {
  try { alerts.value = await api('/alerts') } catch { alerts.value = [] }
}

export function alertText(a) {
  const tag = a.level === 'expired' ? '已过期' : `剩${a.days_left}天`
  return (a.override_days != null ? '📌' : '') + a.name + '(' + tag + ')'
}
