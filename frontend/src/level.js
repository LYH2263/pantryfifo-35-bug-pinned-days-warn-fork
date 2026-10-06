// 分层角标与批次详情同一结论（后端 lot_level 下发的 level / days_left）：
// 已钉批按生效到期日算剩余天数，主行仍显示入库到期日。
export function pinBadge(x) {
  if (x.override_days == null) return ''
  if (x.level === 'expired') return '📌已过期'
  if (x.days_left == null) return '📌'
  return `📌剩${x.days_left}天`
}
