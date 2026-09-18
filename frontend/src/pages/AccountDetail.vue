<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { getJSON, postJSON } from '../api'
import SegmentTable from '../components/SegmentTable.vue'

const route = useRoute()
const data = ref(null)
const bill = ref(null)
const annual = ref(null)
const verify = ref(null)
const peak = ref(false)
const kwhInput = ref(100)
const busy = ref(false)
const error = ref('')

const account = computed(() => data.value?.account)
const point = computed(() => annual.value?.freeze_point)

const fmtTime = (s) => (s ? s.slice(0, 19).replace('T', ' ') : '—')

const load = async () => {
  error.value = ''
  verify.value = null
  try {
    data.value = await getJSON(`/api/accounts/${route.params.id}`)
    annual.value = await getJSON(`/api/accounts/${route.params.id}/annual`)
    const r = data.value.readings[0]
    if (r) {
      kwhInput.value = r.kwh
      await preview(r.kwh, !!r.peak)
    }
  } catch (e) {
    error.value = e.message
  }
}

const preview = async (kwh, isPeak) => {
  bill.value = await postJSON('/api/bill', {
    account_id: +route.params.id,
    kwh,
    peak: isPeak,
    persist: false,
  })
}

const runCalc = async (persist) => {
  busy.value = true
  error.value = ''
  try {
    bill.value = await postJSON('/api/bill', {
      account_id: +route.params.id,
      kwh: kwhInput.value,
      peak: peak.value,
      persist,
    })
    if (persist) annual.value = await getJSON(`/api/accounts/${route.params.id}/annual`)
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}

const doFreeze = async () => {
  busy.value = true
  error.value = ''
  try {
    annual.value = await postJSON(`/api/accounts/${route.params.id}/freeze`, {})
    verify.value = null
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}

const doUnfreeze = async () => {
  busy.value = true
  error.value = ''
  try {
    annual.value = await postJSON(`/api/accounts/${route.params.id}/unfreeze`, {})
    verify.value = null
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}

const doVerify = async () => {
  busy.value = true
  error.value = ''
  try {
    verify.value = await getJSON(`/api/accounts/${route.params.id}/annual/verify`)
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}

onMounted(load)
watch(() => route.params.id, load)
</script>

<template>
  <div class="page" v-if="account">
    <h1>{{ account.name }}</h1>
    <p class="muted">表号 {{ account.meter_no }} · {{ account.note }}</p>
    <p v-if="error" class="err">{{ error }}</p>

    <div class="panel" v-if="annual">
      <div class="annual-head">
        <h3>{{ annual.year }} 年度档位进度</h3>
        <span class="badge" :class="annual.frozen ? 'on' : 'off'">
          {{ annual.frozen ? '❄ 已冻结' : '实时累计' }}
        </span>
      </div>
      <div class="stat-row">
        <div class="stat"><span class="muted">年累计净电量</span><strong>{{ annual.accumulated_kwh }}</strong> kWh</div>
        <div class="stat"><span class="muted">分段累进起点</span><strong>{{ annual.start_kwh }}</strong> kWh</div>
        <div class="stat" v-if="point">
          <span class="muted">冻结点电量</span><strong>{{ point.frozen_kwh }}</strong> kWh
          <span class="muted">· {{ fmtTime(point.frozen_at) }}</span>
        </div>
      </div>
      <div class="btn-row">
        <button v-if="!annual.frozen" :disabled="busy" @click="doFreeze">冻结当前累计</button>
        <button v-else class="ghost" :disabled="busy" @click="doUnfreeze">解冻（恢复实时累计）</button>
        <button class="ghost" :disabled="busy" @click="doVerify">重算校验</button>
        <button class="ghost" @click="load">刷新</button>
      </div>

      <div v-if="verify" class="verify">
        <p>
          校验结果：
          <strong :class="verify.consistent ? 'ok' : 'bad'">
            {{ verify.consistent ? '一致 ✓' : '不一致 ✗' }}
          </strong>
          <span class="muted">
            · 累计 {{ verify.accumulated_kwh }} / 明细合计 {{ verify.detail_total_kwh }} kWh
            · 共 {{ verify.run_count }} 笔已落库测算
          </span>
        </p>
        <table v-if="verify.details.length">
          <thead><tr><th>测算#</th><th>净电量(kWh)</th><th>落库时间</th></tr></thead>
          <tbody>
            <tr v-for="d in verify.details" :key="d.run_id">
              <td>{{ d.run_id }}</td><td>{{ d.kwh }}</td><td>{{ fmtTime(d.created_at) }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div v-if="annual.history?.length" class="history">
        <h4>冻结点记录</h4>
        <table>
          <thead><tr><th>#</th><th>冻结电量(kWh)</th><th>冻结时间</th><th>状态</th><th>解冻时间</th></tr></thead>
          <tbody>
            <tr v-for="h in annual.history" :key="h.id">
              <td>{{ h.id }}</td>
              <td>{{ h.frozen_kwh }}</td>
              <td>{{ fmtTime(h.frozen_at) }}</td>
              <td>{{ h.unfrozen_at ? '已解冻' : '生效中' }}</td>
              <td>{{ fmtTime(h.unfrozen_at) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <div class="panel">
      <h3>测算</h3>
      <div class="form-row">
        <label>电量(kWh) <input type="number" v-model.number="kwhInput" min="0" step="1" /></label>
        <label><input type="checkbox" v-model="peak" /> 尖峰</label>
        <button :disabled="busy" @click="runCalc(true)">计算并入库</button>
        <button class="ghost" :disabled="busy" @click="runCalc(false)">仅试算</button>
      </div>
      <div v-if="bill">
        <p class="muted" v-if="bill.base_kwh">
          本段自年累计 <strong>{{ bill.base_kwh }}</strong> kWh 起累进
          <template v-if="annual?.frozen">（冻结点 {{ annual.freeze_point?.frozen_kwh }} kWh）</template>
        </p>
        <p v-if="bill.annual">
          本段新增 <strong>{{ bill.annual.added_kwh }}</strong> kWh ·
          年累计 <strong>{{ bill.annual.accumulated_kwh }}</strong> kWh
        </p>
        <p>合计 <strong class="hero-num" style="font-size:1.5rem">¥{{ bill.total }}</strong></p>
        <SegmentTable :rows="bill.segments" />
      </div>
    </div>
  </div>
</template>

<style scoped>
.annual-head { display: flex; align-items: center; gap: 0.75rem; }
.badge { padding: 0.15rem 0.6rem; border-radius: 999px; font-size: 0.85rem; font-weight: 600; }
.badge.on { background: color-mix(in srgb, #6db8ff 25%, transparent); color: #9ecfff; }
.badge.off { background: color-mix(in srgb, var(--accent) 20%, transparent); color: var(--accent); }
.stat-row { display: flex; flex-wrap: wrap; gap: 1.5rem; margin: 0.5rem 0 0.8rem; }
.stat { display: flex; flex-direction: column; }
.stat strong { font-size: 1.35rem; color: var(--text); }
.btn-row { display: flex; gap: 0.6rem; flex-wrap: wrap; }
button.ghost { background: transparent; border: 1px solid var(--muted); color: var(--text); }
.form-row { display: flex; flex-wrap: wrap; gap: 1rem; align-items: end; margin-bottom: 0.8rem; }
input[type=number] { width: 6rem; margin-left: 0.35rem; }
.verify, .history { margin-top: 0.9rem; padding-top: 0.7rem; border-top: 1px solid color-mix(in srgb, var(--muted) 30%, transparent); }
.ok { color: var(--accent); }
.bad { color: #ff8a8a; }
.err { color: #ff8a8a; }
</style>
