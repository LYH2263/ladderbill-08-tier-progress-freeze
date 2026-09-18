<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { getJSON, postJSON } from '../api'
import SegmentTable from '../components/SegmentTable.vue'

const route = useRoute()
const account = ref(null)
const progress = ref(null)
const bill = ref(null)
const verify = ref(null)
const kwh = ref(0)
const peak = ref(false)
const busy = ref(false)
const error = ref('')

const accountId = computed(() => +route.params.id)

async function loadAll() {
  error.value = ''
  try {
    const data = await getJSON(`/api/accounts/${accountId.value}`)
    account.value = data.account
    const r = data.readings[0]
    if (r && kwh.value === 0) {
      kwh.value = r.kwh
      peak.value = !!r.peak
    }
    await refreshProgress()
    await preview()
  } catch (e) {
    error.value = String(e.message || e)
  }
}

async function refreshProgress() {
  progress.value = await getJSON(`/api/accounts/${accountId.value}/year-progress`)
}

async function preview() {
  // 不落库试算：分段起点同样反映当前冻结态
  bill.value = await postJSON('/api/bill', {
    account_id: accountId.value,
    kwh: Number(kwh.value) || 0,
    peak: peak.value,
    persist: false,
  })
}

async function runPersisted() {
  busy.value = true
  error.value = ''
  try {
    bill.value = await postJSON('/api/bill', {
      account_id: accountId.value,
      kwh: Number(kwh.value) || 0,
      peak: peak.value,
      persist: true,
    })
    await refreshProgress()
  } catch (e) {
    error.value = String(e.message || e)
  } finally {
    busy.value = false
  }
}

async function freeze() {
  busy.value = true
  error.value = ''
  try {
    await postJSON(`/api/accounts/${accountId.value}/freeze`, {})
    await refreshProgress()
    await preview()
  } catch (e) {
    error.value = String(e.message || e)
  } finally {
    busy.value = false
  }
}

async function unfreeze() {
  busy.value = true
  error.value = ''
  try {
    await postJSON(`/api/accounts/${accountId.value}/unfreeze`, {})
    await refreshProgress()
    await preview()
  } catch (e) {
    error.value = String(e.message || e)
  } finally {
    busy.value = false
  }
}

async function recompute() {
  busy.value = true
  error.value = ''
  try {
    verify.value = await getJSON(`/api/accounts/${accountId.value}/recompute`)
  } catch (e) {
    error.value = String(e.message || e)
  } finally {
    busy.value = false
  }
}

onMounted(loadAll)
watch(() => route.params.id, loadAll)
</script>
<template>
  <div class="page" v-if="account">
    <h1>{{ account.name }}</h1>
    <p class="muted">表号 {{ account.meter_no }} · {{ account.note }}</p>
    <p v-if="error" class="err">{{ error }}</p>

    <div class="panel">
      <h3>
        {{ progress?.year }} 年档位进度
        <span v-if="progress?.frozen" class="tag tag-frozen">已冻结</span>
        <span v-else class="tag tag-live">实时累计</span>
      </h3>
      <div class="stat-row">
        <div><div class="stat-num">{{ progress?.year_kwh ?? '—' }}</div><div class="muted">年累计净电量(kWh)</div></div>
        <div><div class="stat-num">{{ progress?.tier_base_kwh ?? '—' }}</div><div class="muted">当前阶梯起点(kWh)</div></div>
        <div><div class="stat-num">{{ progress?.run_count ?? '—' }}</div><div class="muted">年内已计费笔数</div></div>
      </div>
      <div v-if="progress?.frozen && progress.freeze" class="freeze-line">
        冻结点 <strong>#{{ progress.freeze.id }}</strong>：{{ progress.freeze.frozen_kwh }} kWh
        <span class="muted">· {{ progress.freeze.created_at }}</span>
      </div>
      <div class="actions">
        <button v-if="!progress?.frozen" :disabled="busy" @click="freeze">冻结本年度档位进度</button>
        <button v-else class="btn-warn" :disabled="busy" @click="unfreeze">解冻（恢复实时累计）</button>
        <button class="btn-ghost" :disabled="busy" @click="recompute">重算校验</button>
      </div>
      <div v-if="verify" class="verify" :class="verify.consistent ? 'ok' : 'bad'">
        重算：明细 {{ verify.run_count }} 笔，累计 {{ verify.year_kwh }} kWh，
        {{ verify.consistent ? '累计与运行明细一致 ✓' : '校验不一致 ✗' }}
        <div v-for="c in verify.freeze_checks" :key="c.freeze_id" class="muted">
          冻结点 #{{ c.freeze_id }}（{{ c.status }}）快照 {{ c.snapshot_year_kwh }}，
          截至冻结点运行合计 {{ c.runs_up_to_freeze }}，{{ c.consistent ? '一致' : '不一致' }}
        </div>
      </div>
    </div>

    <div class="panel">
      <h3>本户测算</h3>
      <div class="form-row">
        <label>电量(kWh) <input type="number" v-model.number="kwh" min="0" step="1" /></label>
        <label><input type="checkbox" v-model="peak" @change="preview" /> 尖峰</label>
        <button class="btn-ghost" :disabled="busy" @click="preview">试算</button>
        <button :disabled="busy" @click="runPersisted">计算并入库</button>
      </div>
      <div v-if="bill" class="bill-summary">
        <p>合计 <strong class="hero-num" style="font-size:1.5rem">¥{{ bill.total }}</strong></p>
        <ul class="kv">
          <li>当前年累计：<strong>{{ bill.year_kwh }}</strong> kWh</li>
          <li>若本笔入库预计年累计：<strong>{{ bill.projected_year_kwh }}</strong> kWh</li>
          <li>冻结点：<strong>{{ bill.freeze ? bill.freeze.frozen_kwh : '—' }}</strong> kWh
            <span v-if="bill.frozen" class="tag tag-frozen">冻结态</span></li>
          <li>本段新增电量：<strong>{{ bill.segment_added_kwh }}</strong> kWh</li>
          <li>分段起点：<strong>{{ bill.start_kwh ?? bill.tier_base_kwh }}</strong> kWh</li>
        </ul>
      </div>
      <SegmentTable :rows="bill?.segments || []" />
    </div>

    <div class="panel">
      <h3>冻结点记录</h3>
      <table v-if="progress?.freeze_points?.length">
        <thead><tr><th>#</th><th>状态</th><th>冻结点电量</th><th>冻结时年累计</th><th>冻结时间</th><th>备注</th></tr></thead>
        <tbody>
          <tr v-for="p in progress.freeze_points" :key="p.id">
            <td>{{ p.id }}</td>
            <td>
              <span :class="['tag', p.status === 'frozen' ? 'tag-frozen' : 'tag-history']">
                {{ p.status === 'frozen' ? '冻结中' : '已解冻' }}
              </span>
            </td>
            <td>{{ p.frozen_kwh }}</td>
            <td>{{ p.year_kwh }}</td>
            <td class="muted">{{ p.created_at }}</td>
            <td class="muted">{{ p.note || '—' }}</td>
          </tr>
        </tbody>
      </table>
      <p v-else class="muted">本年暂无冻结点</p>
    </div>

    <div class="panel">
      <h3>年内已计费运行</h3>
      <table v-if="progress?.runs?.length">
        <thead><tr><th>运行#</th><th>净电量(kWh)</th><th>时间</th></tr></thead>
        <tbody>
          <tr v-for="r in progress.runs" :key="r.run_id">
            <td>{{ r.run_id }}</td><td>{{ r.kwh }}</td><td class="muted">{{ r.created_at }}</td>
          </tr>
        </tbody>
      </table>
      <p v-else class="muted">本年暂无计费运行</p>
    </div>
  </div>
</template>

<style scoped>
.stat-row { display: flex; gap: 2rem; flex-wrap: wrap; margin: 0.75rem 0; }
.stat-num { font-size: 1.6rem; font-weight: 700; color: var(--accent); }
.tag { font-size: 0.75rem; padding: 0.1rem 0.5rem; border-radius: 999px; margin-left: 0.5rem; vertical-align: middle; }
.tag-frozen { background: #f0b34a; color: #221a08; }
.tag-live { background: color-mix(in srgb, var(--accent) 25%, transparent); color: var(--accent); }
.tag-history { background: color-mix(in srgb, var(--muted) 30%, transparent); color: var(--muted); }
.actions { display: flex; gap: 0.6rem; flex-wrap: wrap; margin-top: 0.5rem; }
.btn-warn { background: #f0b34a; color: #221a08; }
.btn-ghost { background: transparent; color: var(--accent); border: 1px solid var(--accent); }
button:disabled { opacity: 0.5; cursor: not-allowed; }
.form-row { display: flex; flex-wrap: wrap; gap: 1rem; align-items: end; margin-bottom: 0.75rem; }
input[type=number] { width: 6rem; margin-left: 0.35rem; }
.kv { list-style: none; padding: 0; margin: 0.5rem 0; display: grid; grid-template-columns: repeat(auto-fit, minmax(15rem, 1fr)); gap: 0.25rem 1.5rem; }
.freeze-line { margin: 0.5rem 0; }
.verify { margin-top: 0.75rem; padding: 0.6rem 0.75rem; border-radius: 8px; }
.verify.ok { background: color-mix(in srgb, var(--accent) 15%, transparent); }
.verify.bad { background: color-mix(in srgb, #e05b5b 20%, transparent); }
.err { color: #e08b8b; }
</style>
