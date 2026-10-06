<template>
  <div>
    <h1>{{ props.layer }} 层 · 钉值与预警分叉</h1>
    <router-link v-for="x in rows" :key="x.id" class="lot" :to="'/lots/' + x.id">
      {{ x.name }} ×{{ x.qty_remain }} · {{ x.expiry }}<span v-if="x.override_days != null" class="pin">📌{{ x.override_days }}d</span>
    </router-link>
  </div>
</template>
<script setup>
import { ref, watch, onMounted } from 'vue'
import { api } from '../api'
const props = defineProps({ layer: String })
const rows = ref([])
async function load() { rows.value = await api('/fridge?layer=' + props.layer) }
watch(() => props.layer, load)
onMounted(load)
</script>
