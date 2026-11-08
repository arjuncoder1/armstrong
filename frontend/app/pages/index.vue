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
const canControl = computed(() => connected.value && dreamHere.value)
function setTask() {
  if (canControl.value && !busy.value && task.value.trim()) dream(RPC.setTask, { task: task.value.trim() })
}

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

const statusRows = computed(() => {
  const s = status.value
  if (!s) return []
  const keys = ['task', 'driving', 'active_operator', 'teleoperator_connected', 'presets']
  const rest = Object.keys(s).filter(k => !keys.includes(k))
  return [...keys.filter(k => k in s), ...rest].map(k => ({ k, v: typeof s[k] === 'object' ? JSON.stringify(s[k]) : String(s[k]) }))
})
</script>

<template>
  <WorkspaceShell title="Control room" description="A clear view. Every move in your hands.">
    <template #actions>
      <span class="connection-state" :class="{ online: connected }"><i />{{ connected ? 'Connected' : state === 'connecting' ? 'Connecting' : 'Disconnected' }}</span>
      <button class="icon-button" aria-label="Reconnect" :disabled="state === 'connecting'" @click="connect"><UIcon name="i-lucide-refresh-cw" /></button>
    </template>
    <div class="control-layout">
      <section class="vision-section" aria-label="Camera feeds">
        <div class="section-title"><h2>Robot vision</h2><span>{{ CAMERAS.filter(cam => tracks[cam]).length }} of 3 cameras live</span></div>
        <div class="camera-grid">
          <div v-for="cam in CAMERAS" :key="cam" class="camera-frame" :class="{ 'camera-main': cam === 'overhead_camera' }">
            <div class="camera-surface">
              <video :ref="el => setVideoEl(cam, el)" autoplay playsinline muted />
              <div v-if="!tracks[cam]" class="camera-placeholder">
                <span class="viewfinder"><UIcon name="i-lucide-video" /></span>
                <strong>{{ connected ? 'Waiting for camera' : 'Your view starts here' }}</strong>
                <p>{{ connected ? 'Video will appear when the feed is available.' : 'Connect the robot to see its perspective.' }}</p>
              </div>
              <span class="feed-state" :class="{ live: tracks[cam] }"><i />{{ tracks[cam] ? 'Live' : 'No signal' }}</span>
            </div>
            <div class="camera-caption"><span><UIcon :name="cam === 'overhead_camera' ? 'i-lucide-scan' : 'i-lucide-hand'" />{{ label[cam] }}</span><span>{{ cam === 'overhead_camera' ? 'Workspace view' : 'Wrist view' }}</span></div>
          </div>
        </div>
        <section class="activity-section">
          <div class="section-title"><h2>Activity</h2><span>{{ log.length }} events</span></div>
          <div class="event-list">
            <div v-for="(e, i) in log" :key="i" class="event-row" :class="e.level"><UIcon :name="e.level === 'error' ? 'i-lucide-circle-alert' : e.level === 'ok' ? 'i-lucide-check' : 'i-lucide-arrow-right'" /><p>{{ e.msg }}</p><time>{{ e.t }}</time></div>
            <div v-if="!log.length" class="quiet-empty"><UIcon name="i-lucide-list" /><span>Ready when you are. Session activity will appear here.</span></div>
          </div>
        </section>
      </section>
      <aside class="command-panel">
        <div class="command-heading"><h2>Command center</h2><UIcon name="i-lucide-sliders-horizontal" /></div>
        <div class="command-content">
          <div class="peer-row"><span><i :class="{ online: robotHere }" />Robot</span><b>{{ robotHere ? 'Online' : 'Offline' }}</b></div>
          <div class="peer-row"><span><i :class="{ online: dreamHere }" />Dream-1</span><b>{{ dreamHere ? 'Online' : 'Offline' }}</b></div>
          <form class="task-form" @submit.prevent="setTask">
            <label for="robot-task">What should the robot do?</label>
            <textarea id="robot-task" v-model="task" rows="3" placeholder="Describe a task…" />
            <button class="action-button primary" type="submit" :disabled="!canControl || busy || !task.trim()"><UIcon name="i-lucide-arrow-up-right" />{{ busy ? 'Sending…' : 'Set task' }}</button>
            <p class="field-help">{{ canControl ? 'Set a task, then start when the workspace is clear.' : 'Connect Robot and Dream-1 to begin.' }}</p>
          </form>
          <div class="playback-controls">
            <button class="action-button secondary" :disabled="!canControl || busy" @click="start"><UIcon name="i-lucide-play" />Start</button>
            <button class="action-button secondary" :disabled="!canControl" @click="stop"><UIcon name="i-lucide-pause" />Pause</button>
          </div>
          <button class="stop-button" @click="stop"><UIcon name="i-lucide-octagon-x" /><span>STOP</span><span>Pause Dream-1</span></button>
          <div class="panel-divider" />
          <h3>Arm controls</h3>
          <div class="arm-controls"><button :disabled="!connected || !robotHere" @click="park"><UIcon name="i-lucide-parking-circle" />Park arms</button><button :disabled="!connected || !robotHere" @click="home"><UIcon name="i-lucide-house" />Home arms</button></div>
          <button class="teleop-button" :disabled="!canControl || busy" @click="dream(RPC.toTeleop)">Switch to teleoperation<UIcon name="i-lucide-arrow-right" /></button>
        </div>
        <section class="policy-status">
          <div class="section-title"><h3>Dream-1 status</h3><span v-if="status" class="connection-state" :class="{ online: status.driving }"><i />{{ status.driving ? 'Driving' : 'Idle' }}</span></div>
          <p v-if="statusError" class="inline-error">{{ statusError }}</p>
          <dl v-if="statusRows.length" class="status-list"><template v-for="r in statusRows" :key="r.k"><dt>{{ r.k.replaceAll('_', ' ') }}</dt><dd>{{ r.v }}</dd></template></dl>
          <p v-else-if="!statusError" class="field-help">{{ connected ? 'Waiting for a status update.' : 'Status will appear once connected.' }}</p>
        </section>
      </aside>
    </div>
    <details class="session-details"><summary>Session details</summary><p>{{ identity }} · Other participants: {{ participants.filter(p => p !== ROBOT_IDENTITY && p !== DREAM_IDENTITY).join(', ') || 'none' }}</p></details>
    <UModal v-model:open="confirmOpen" :title="confirmCfg?.title" :description="confirmCfg?.desc"><template #footer><div class="flex gap-2 justify-end w-full"><UButton color="neutral" variant="ghost" @click="confirmOpen = false">Cancel</UButton><UButton color="error" @click="confirmYes">Yes, hands clear</UButton></div></template></UModal>
  </WorkspaceShell>
</template>
