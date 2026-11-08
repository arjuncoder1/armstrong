<script setup lang="ts">
import { useArmstrong, CAMERAS, ROBOT_IDENTITY, DREAM_IDENTITY, RPC } from '~/composables/useArmstrong'
import type { Camera } from '~/composables/useArmstrong'

const { identity, state, participants, tracks, log, connect, rpc } = useArmstrong()

const task = ref('pick up the card')
const status = ref<Record<string, unknown> | null>(null)
const statusError = ref<string | null>(null)
const busy = ref(false)

const robotHere = computed(() => participants.value.includes(ROBOT_IDENTITY))
const dreamHere = computed(() => participants.value.includes(DREAM_IDENTITY))
const connected = computed(() => state.value === 'connected')

// video elements
const videoEls: Partial<Record<Camera, HTMLVideoElement>> = {}
function setVideoEl(cam: Camera, el: unknown) {
  if (el instanceof HTMLVideoElement) videoEls[cam] = el
}
watch(tracks, (now, before) => {
  for (const cam of CAMERAS) {
    const el = videoEls[cam]
    const t = now[cam]
    if (before?.[cam] && before[cam] !== t) before[cam]!.detach()
    if (t && el) t.attach(el)
  }
}, { flush: 'post' })

const label: Record<Camera, string> = {
  overhead_camera: 'Overhead',
  left_wrist_camera: 'Left wrist',
  right_wrist_camera: 'Right wrist',
}

// Dream RPCs
async function dream(method: string, body: object = {}) {
  busy.value = true
  try {
    const reply = await rpc(DREAM_IDENTITY, method, JSON.stringify(body))
    if (reply) {
      try { status.value = JSON.parse(reply) } catch { /* non-JSON reply, logged already */ }
    }
  }
  finally { busy.value = false }
}

async function pollStatus() {
  if (!connected.value) return
  if (!dreamHere.value) {
    statusError.value = 'Dream node not in room. Start it: uv run main.py dream'
    return
  }
  const reply = await rpc(DREAM_IDENTITY, RPC.status, '{}', true)
  if (reply) {
    try { status.value = JSON.parse(reply); statusError.value = null }
    catch { statusError.value = `non-JSON status: ${reply}` }
  }
  else statusError.value = 'dream.status failed'
}

// Confirm dialog
const confirmOpen = ref(false)
const confirmCfg = ref<{ title: string, desc: string, action: () => Promise<void> } | null>(null)
function ask(title: string, desc: string, action: () => Promise<void>) {
  confirmCfg.value = { title, desc, action }
  confirmOpen.value = true
}
async function confirmYes() {
  const a = confirmCfg.value?.action
  confirmOpen.value = false
  if (a) await a()
}

const start = () => ask('Start Dream-1?', 'Dream-1 will drive the real arms. Arms will move, hands clear?', () => dream(RPC.resume))
const park = () => ask('Park arms?', 'The robot will park both arms. Arms will move, hands clear?', async () => { await rpc(ROBOT_IDENTITY, RPC.park, 'park') })
const home = () => ask('Home arms?', 'Both arms go to home and both grippers OPEN (anything held drops). Arms will move, hands clear?', async () => { await rpc(ROBOT_IDENTITY, RPC.home, 'grippers_empty') })
const stop = () => dream(RPC.pause)

let timer: ReturnType<typeof setInterval> | undefined
onMounted(() => {
  connect()
  timer = setInterval(pollStatus, 2000)
})
onBeforeUnmount(() => clearInterval(timer))

const stateColor = computed(() => connected.value ? 'success' : state.value === 'error' ? 'error' : 'warning')
const statusRows = computed(() => {
  const s = status.value
  if (!s) return []
  const keys = ['task', 'driving', 'active_operator', 'teleoperator_connected', 'presets']
  const rest = Object.keys(s).filter(k => !keys.includes(k))
  return [...keys.filter(k => k in s), ...rest].map(k => ({ k, v: typeof s[k] === 'object' ? JSON.stringify(s[k]) : String(s[k]) }))
})
</script>

<template>
  <div class="min-h-screen bg-neutral-950 text-neutral-100 p-4 md:p-6">
    <header class="flex flex-wrap items-center gap-3 mb-4">
      <h1 class="text-xl font-semibold tracking-tight">Armstrong</h1>
      <UBadge :color="stateColor" variant="subtle">{{ state }}</UBadge>
      <UBadge :color="robotHere ? 'success' : 'neutral'" variant="subtle" icon="i-lucide-bot">robot</UBadge>
      <UBadge :color="dreamHere ? 'success' : 'neutral'" variant="subtle" icon="i-lucide-brain">dream-1</UBadge>
      <span class="text-xs text-neutral-500">{{ identity }} · others: {{ participants.filter(p => p !== ROBOT_IDENTITY && p !== DREAM_IDENTITY).join(', ') || 'none' }}</span>
      <div class="flex-1" />
      <UButton to="/voice" size="sm" color="primary" variant="soft" icon="i-lucide-mic">Voice</UButton>
      <UButton size="sm" variant="ghost" icon="i-lucide-refresh-cw" @click="connect">Reconnect</UButton>
    </header>

    <div class="grid gap-4 lg:grid-cols-[1fr_380px]">
      <section class="space-y-3">
        <div v-for="row in [['overhead_camera'], ['left_wrist_camera', 'right_wrist_camera']] as Camera[][]" :key="row[0]"
             :class="row.length > 1 ? 'grid grid-cols-2 gap-3' : ''">
          <div v-for="cam in row" :key="cam" class="relative rounded-lg overflow-hidden bg-black border border-neutral-800 aspect-video">
            <video :ref="el => setVideoEl(cam, el)" autoplay playsinline muted class="w-full h-full object-contain" />
            <span class="absolute top-2 left-2 text-xs bg-black/60 px-2 py-0.5 rounded">{{ label[cam] }}</span>
            <div v-if="!tracks[cam]" class="absolute inset-0 flex items-center justify-center text-neutral-600 text-sm">no video</div>
          </div>
        </div>
      </section>

      <aside class="space-y-4">
        <UCard>
          <template #header><span class="font-medium">Task</span></template>
          <div class="space-y-3">
            <UInput v-model="task" class="w-full" placeholder="pick up the card" @keydown.enter="dream(RPC.setTask, { task })" />
            <div class="grid grid-cols-3 gap-2">
              <UButton block variant="soft" :loading="busy" @click="dream(RPC.setTask, { task })">Set task</UButton>
              <UButton block color="success" icon="i-lucide-play" @click="start">Start</UButton>
              <UButton block color="warning" variant="soft" icon="i-lucide-pause" @click="dream(RPC.pause)">Pause</UButton>
            </div>
            <UButton block size="xl" color="error" icon="i-lucide-octagon-x" class="h-16 text-lg font-bold justify-center" @click="stop">STOP</UButton>
            <div class="grid grid-cols-3 gap-2">
              <UButton block variant="outline" color="neutral" @click="park">Park arms</UButton>
              <UButton block variant="outline" color="neutral" @click="home">Home arms</UButton>
              <UButton block variant="outline" color="neutral" @click="dream(RPC.toTeleop)">To teleop</UButton>
            </div>
          </div>
        </UCard>

        <UCard>
          <template #header>
            <div class="flex items-center justify-between">
              <span class="font-medium">Dream-1 status</span>
              <UBadge v-if="status" :color="status.driving ? 'success' : 'neutral'" variant="subtle">
                {{ status.driving ? 'driving' : 'not driving' }}
              </UBadge>
            </div>
          </template>
          <p v-if="statusError" class="text-sm text-amber-400 mb-2">{{ statusError }}</p>
          <dl v-if="statusRows.length" class="text-sm grid grid-cols-[auto_1fr] gap-x-3 gap-y-1">
            <template v-for="r in statusRows" :key="r.k">
              <dt class="text-neutral-500">{{ r.k }}</dt><dd class="break-all">{{ r.v }}</dd>
            </template>
          </dl>
          <p v-else-if="!statusError" class="text-sm text-neutral-500">waiting for status…</p>
        </UCard>

        <UCard :ui="{ body: 'p-0 sm:p-0' }">
          <template #header><span class="font-medium">Event log</span></template>
          <div class="max-h-72 overflow-y-auto font-mono text-xs p-3 space-y-1">
            <div v-for="(e, i) in log" :key="i" :class="{ 'text-red-400': e.level === 'error', 'text-emerald-400': e.level === 'ok', 'text-neutral-400': e.level === 'info' }">
              <span class="text-neutral-600">{{ e.t }}</span> {{ e.msg }}
            </div>
            <div v-if="!log.length" class="text-neutral-600">no events</div>
          </div>
        </UCard>
      </aside>
    </div>

    <UModal v-model:open="confirmOpen" :title="confirmCfg?.title" :description="confirmCfg?.desc">
      <template #footer>
        <div class="flex gap-2 justify-end w-full">
          <UButton color="neutral" variant="ghost" @click="confirmOpen = false">Cancel</UButton>
          <UButton color="error" @click="confirmYes">Yes, hands clear</UButton>
        </div>
      </template>
    </UModal>
  </div>
</template>
