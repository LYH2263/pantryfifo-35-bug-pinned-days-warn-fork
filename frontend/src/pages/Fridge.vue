<template>
  <div>
    <h1>冰箱分层</h1>
    <p class="muted">竖列分层 · FEFO 消费走「消费」页 · 主行入库到期日，📌角标为钉后剩余天数（同详情/紧急条/收走） · 点批次进详情钉可放天数</p>
    <div class="fridge">
      <section v-for="L in layers" :key="L" class="shelf">
        <h3>{{ label[L] }}</h3>
        <router-link v-for="x in by(L)" :key="x.id" class="lot" :to="'/lots/' + x.id">
          {{ x.name }} ×{{ x.qty_remain }} · {{ x.expiry }}<span
            v-if="x.override_days != null" class="pin" :class="x.level">{{ pinBadge(x) }}</span>
        </router-link>
      </section>
    </div>
    <button style="margin-top:12px" @click="sweep">过期下架</button>
  </div>
</template>
<script setup>
import { ref, onMounted } from 'vue'
import { api } from '../api'
import { refreshAlerts } from '../alerts'
import { pinBadge } from '../level'
const rows = ref([])
const layers = ['upper','mid','lower']
const label = { upper: '上层', mid: '中层', lower: '下层' }
function by(L) { return rows.value.filter(r => r.layer === L) }
async function load() { rows.value = await api('/fridge') }
async function sweep() {
  await api('/expire-sweep', { method: 'POST', body: '{}' })
  await load()
  await refreshAlerts()
}
onMounted(load)
</script>
