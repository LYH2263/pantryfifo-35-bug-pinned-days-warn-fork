<template>
  <div>
    <h1>设置 · 钉值与预警分叉</h1>
    <label>warn_days（临期预警阈值，天）：</label>
    <input type="number" min="0" step="1" v-model.number="warn" />
    <button @click="save">保存</button>
    <p v-if="msg" class="muted">{{ msg }}</p>
    <pre>{{ s }}</pre>
  </div>
</template>
<script setup>
import { ref, onMounted } from 'vue'
import { api } from '../api'
import { refreshAlerts } from '../alerts'
const s = ref('')
const warn = ref(3)
const msg = ref('')
async function load() {
  const j = await api('/settings')
  s.value = JSON.stringify(j, null, 2)
  warn.value = Number(j.warn_days ?? 3)
}
async function save() {
  try {
    await api('/settings', { method: 'POST', body: JSON.stringify({ warn_days: warn.value }) })
    msg.value = '已保存'
    await load()
    await refreshAlerts()
  } catch (e) { msg.value = e.message }
}
onMounted(load)
</script>
