<script setup lang="ts">
import { ConnectionState } from 'livekit-client'
import { useVoice } from '~/composables/useVoice'
import type { AgentState, ToolCall } from '~/composables/useVoice'
import { useArmstrong, DREAM_IDENTITY, RPC } from '~/composables/useArmstrong'

const v = useVoice()
const { agentState, agentHere, micOn, lines, tools, error, agentLevel, micLevel, conn } = v

// Robot room (overhead camera + Dream-1 pause for STOP); independent of the voice room.
const robot = useArmstrong()
const camEl = ref<HTMLVideoElement | null>(null)
watch([() => robot.tracks.value.overhead_camera, camEl], ([t, el], [prev]) => {
  if (prev && prev !== t) prev.detach()
  if (t && el) t.attach(el)
}, { flush: 'post' })
onMounted(() => robot.connect())

const inCall = computed(() => conn.value === ConnectionState.Connected || conn.value === ConnectionState.Connecting || conn.value === ConnectionState.Reconnecting)

const STATE: Record<AgentState, { label: string, color: string, ring: string }> = {
  disconnected: { label: 'Offline', color: 'bg-neutral-700', ring: 'ring-neutral-700/30' },
  connecting: { label: 'Connecting…', color: 'bg-neutral-500', ring: 'ring-neutral-500/30' },
  initializing: { label: 'Waking up…', color: 'bg-neutral-400', ring: 'ring-neutral-400/30' },
  idle: { label: 'Idle', color: 'bg-neutral-400', ring: 'ring-neutral-400/30' },
  listening: { label: 'Listening', color: 'bg-emerald-500', ring: 'ring-emerald-500/30' },
  thinking: { label: 'Thinking', color: 'bg-amber-400', ring: 'ring-amber-400/30' },
  speaking: { label: 'Speaking', color: 'bg-sky-400', ring: 'ring-sky-400/30' },
}
const st = computed(() => STATE[agentState.value] ?? STATE.idle)
const orbScale = computed(() => {
  const lvl = agentState.value === 'speaking' ? agentLevel.value : agentState.value === 'listening' ? micLevel.value * 0.6 : 0
  return 1 + lvl * 0.35
})

// Transcript auto-scroll
const scroller = ref<HTMLElement | null>(null)
watch(() => lines.value.map(l => l.text).join('|').length, async () => {
  await nextTick()
  scroller.value?.scrollTo({ top: scroller.value.scrollHeight, behavior: 'smooth' })
})

const draft = ref('')
async function send() {
  const text = draft.value
  draft.value = ''
  await v.say(text)
}

async function stopAll() {
  if (v.room.value) await v.say('STOP. Freeze everything right now.')
  if (robot.participants.value.includes(DREAM_IDENTITY)) await robot.rpc(DREAM_IDENTITY, RPC.pause, '{}')
}

const toolIcon: Record<ToolCall['status'], string> = {
  running: 'i-lucide-loader-circle',
  done: 'i-lucide-check',
  error: 'i-lucide-x',
  cancelled: 'i-lucide-ban',
}
const toolColor: Record<ToolCall['status'], string> = {
  running: 'text-amber-400',
  done: 'text-emerald-400',
  error: 'text-red-400',
  cancelled: 'text-neutral-400',
}
function prettyArgs(a: string) {
  try {
    const o = JSON.parse(a)
    return Object.entries(o).map(([k, val]) => `${k}: ${typeof val === 'string' ? val : JSON.stringify(val)}`).join(' · ')
  }
  catch { return a }
}
const time = (t: number) => new Date(t).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
const elapsed = (c: ToolCall) => `${(((c.ended ?? Date.now()) - c.t) / 1000).toFixed(1)}s`

// Tick so running tool timers update
const now = ref(Date.now())
let clock: ReturnType<typeof setInterval> | undefined
onMounted(() => { clock = setInterval(() => { now.value = Date.now() }, 500) })
onBeforeUnmount(() => clearInterval(clock))

const suggestions = ['What can you see?', 'Pick up the card in front of you', 'Open your right gripper', 'How is the task going?']
</script>

<template>
  <WorkspaceShell title="Voice studio" description="Talk naturally. Watch the robot respond.">
    <template #actions><span class="connection-state" :class="{ online: agentHere }"><i />{{ agentHere ? 'Agent connected' : 'Agent offline' }}</span></template>
    <div class="voice-layout">
      <section class="conversation-panel">
        <div class="voice-stage" :class="{ 'voice-active': inCall }">
          <div class="voice-stage-top"><span><UIcon name="i-lucide-audio-lines" />Blackjack Robot</span><span class="voice-state">{{ st.label }}</span></div>
          <div class="voice-visual" aria-hidden="true"><span v-for="n in 9" :key="n" :style="{ height: `${18 + (5 - Math.abs(5 - n)) * 12}px`, transform: `scaleY(${inCall ? orbScale : 0.65})` }" /></div>
          <h2>{{ !inCall ? 'A conversation away.' : agentState === 'listening' ? 'Go ahead, I’m listening.' : agentState === 'speaking' ? 'Let’s talk.' : st.label }}</h2>
          <p>{{ !inCall ? 'Start a conversation to see, plan, and act together.' : !agentHere ? 'Waiting for the agent worker to join…' : !micOn ? 'Microphone muted. You can still type below.' : 'Speak naturally. Say “stop” anytime.' }}</p>
          <div class="voice-buttons">
            <button v-if="!inCall" class="action-button primary" @click="v.connect()"><UIcon name="i-lucide-mic" />Start talking<UIcon name="i-lucide-arrow-up-right" /></button>
            <template v-else><button class="action-button secondary" @click="v.toggleMic()"><UIcon :name="micOn ? 'i-lucide-mic' : 'i-lucide-mic-off'" />{{ micOn ? 'Mute mic' : 'Unmute mic' }}</button><button class="action-button secondary" @click="v.disconnect()"><UIcon name="i-lucide-phone-off" />End call</button></template>
          </div>
          <span class="voice-caution">The robot can move its arms. Keep the workspace clear.</span>
          <button v-if="v.audioBlocked.value" class="action-button secondary" @click="v.unlockAudio()">Enable sound</button>
          <p v-if="v.micError.value" role="alert" class="inline-error">{{ v.micError.value }}</p><p v-if="error" role="alert" class="inline-error">{{ error }}</p>
        </div>
        <div class="transcript-heading section-title"><h2>Conversation</h2><span>{{ lines.length }} messages</span></div>
        <div ref="scroller" class="transcript-scroll">
          <div v-if="!lines.length" class="conversation-empty"><h3>Where should we start?</h3><p>Try one of these, or ask something of your own.</p><div class="suggestions"><button v-for="s in suggestions" :key="s" :disabled="!agentHere" @click="v.say(s)">{{ s }}<UIcon name="i-lucide-arrow-up-right" /></button></div></div>
          <div v-for="l in lines" :key="l.id" class="message" :class="{ 'message-user': l.who === 'user', 'message-partial': !l.final }"><span>{{ l.who === 'user' ? 'You' : 'Robot' }}</span><p>{{ l.text }}</p></div>
        </div>
        <form class="message-composer" @submit.prevent="send"><input v-model="draft" aria-label="Message to the robot" placeholder="Or type a message…" :disabled="!agentHere" /><button type="submit" aria-label="Send message" :disabled="!agentHere || !draft.trim()"><UIcon name="i-lucide-arrow-up" /></button></form>
      </section>
      <aside class="voice-monitor">
        <div class="section-title"><h2>Robot vision</h2><span class="connection-state" :class="{ online: robot.participants.value.includes('robot') }"><i />{{ robot.participants.value.includes('robot') ? 'Online' : 'Offline' }}</span></div>
        <div class="camera-frame"><div class="camera-surface"><video ref="camEl" autoplay playsinline muted /><div v-if="!robot.tracks.value.overhead_camera" class="camera-placeholder"><span class="viewfinder"><UIcon name="i-lucide-video" /></span><strong>Waiting for camera</strong><p>The robot’s perspective will appear here.</p></div><span class="feed-state" :class="{ live: robot.tracks.value.overhead_camera }"><i />{{ robot.tracks.value.overhead_camera ? 'Live' : 'No signal' }}</span></div><div class="camera-caption"><span><UIcon name="i-lucide-scan" />Overhead</span><span>Workspace view</span></div></div>
        <button class="stop-button" @click="stopAll"><UIcon name="i-lucide-octagon-x" /><span>STOP</span><span>Stop robot activity</span></button>
        <section class="robot-actions"><div class="section-title"><h2>Robot actions</h2><span>{{ tools.filter(t => t.status === 'running').length }} running</span></div><div v-if="!tools.length" class="actions-empty"><UIcon name="i-lucide-workflow" /><h3>Nothing in motion yet.</h3><p>Actions appear here as the robot works through your requests.</p></div>
          <div v-for="c in tools" :key="c.call_id" class="tool-entry" :data-now="now"><div class="tool-title"><UIcon :name="toolIcon[c.status]" :class="[toolColor[c.status], c.status === 'running' && 'animate-spin']" /><strong>{{ c.name }}</strong><span>{{ elapsed(c) }}</span></div><div class="tool-meta">{{ time(c.t) }} · {{ c.status }}</div><p v-if="c.args && c.args !== '{}'">{{ prettyArgs(c.args) }}</p><p v-for="(p, i) in c.progress.slice(-3)" :key="i">{{ p }}</p><p v-if="c.result" :class="{ 'inline-error': c.status === 'error' }">{{ c.result }}</p></div>
        </section>
        <p v-if="v.roomName.value && inCall" class="session-details">Room: {{ v.roomName.value }}</p>
      </aside>
    </div>
  </WorkspaceShell>
</template>
