<template>
  <div>
    <h1>批次详情 #{{ props.id }}</h1>
    <p v-if="error" class="err">{{ error }}</p>
    <div v-if="lot" class="card">
      <p>
        <b>{{ lot.name }}</b> · {{ layerLabel[lot.layer] || lot.layer }}层
        · 剩余 {{ lot.qty_remain }}/{{ lot.qty_in }} {{ lot.unit }}
      </p>
      <p>入库到期日：{{ lot.expiry || '未填' }} <span class="muted">（主行始终显示此日期）</span></p>
      <p>
        状态：{{ lot.status }}
        <span v-if="lot.data_quality !== 'clean'" class="muted">· 数据 {{ lot.data_quality }}</span>
      </p>
      <p>
        紧急结论：<b :class="lot.level">{{ levelText }}</b>
        <span class="muted">（生效到期日 {{ lot.effective_expiry || '—' }} · warn_days={{ lot.warn_days }}）</span>
      </p>
      <p v-if="lot.override_days != null">
        📌 已钉 {{ lot.override_days }} 天 · 写入日 {{ lot.override_set_at }}
        <button v-if="lot.status === 'on_shelf'" @click="clear">清除钉值</button>
      </p>
      <template v-if="lot.status === 'on_shelf'">
        <label>手钉可放天数（正整数）：</label>
        <input type="number" min="1" step="1" v-model.number="days" />
        <button @click="submit">提交钉值</button>
      </template>
      <p v-else class="muted">仅在架批可写入钉值</p>
    </div>
  </div>
</template>
<script setup>
import { ref, computed, onMounted } from 'vue'
import { api } from '../api'
import { refreshAlerts } from '../alerts'
const props = defineProps({ id: String })
const lot = ref(null)
const days = ref(3)
const error = ref('')
const layerLabel = { upper: '上', mid: '中', lower: '下' }
const levelText = computed(() => {
  if (!lot.value) return ''
  if (lot.value.level === 'expired') return '已过期'
  if (lot.value.level === 'soon') return `临期 · 剩 ${lot.value.days_left} 天`
  if (lot.value.days_left == null) return '正常'
  return `正常 · 剩 ${lot.value.days_left} 天`
})
async function load() { lot.value = await api('/lots/' + props.id) }
async function submit() {
  error.value = ''
  try {
    // 响应即后端按统一规则重算的详情；再刷顶条 → 两处同一结论
    lot.value = await api('/lots/' + props.id + '/override', {
      method: 'POST', body: JSON.stringify({ override_days: days.value }),
    })
    await refreshAlerts()
  } catch (e) { error.value = e.message }
}
async function clear() {
  error.value = ''
  try {
    lot.value = await api('/lots/' + props.id + '/override', {
      method: 'POST', body: JSON.stringify({ override_days: null }),
    })
    await refreshAlerts()
  } catch (e) { error.value = e.message }
}
onMounted(async () => { try { await load() } catch (e) { error.value = e.message } })
</script>
