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
const pulsing = computed(() => ['connecting', 'initializing', 'thinking'].includes(agentState.value))
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
  cancelled: 'text-neutral-500',
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
  <div class="min-h-screen bg-neutral-950 text-neutral-100 p-4 md:p-6">
    <header class="flex flex-wrap items-center gap-3 mb-4">
      <UButton to="/" size="sm" variant="ghost" color="neutral" icon="i-lucide-arrow-left">Control</UButton>
      <h1 class="text-xl font-semibold tracking-tight">Blackjack Robot</h1>
      <UBadge :color="agentHere ? 'success' : 'neutral'" variant="subtle" icon="i-lucide-audio-lines">agent</UBadge>
      <UBadge :color="robot.participants.value.includes('robot') ? 'success' : 'neutral'" variant="subtle" icon="i-lucide-bot">robot</UBadge>
      <span v-if="v.roomName.value && inCall" class="text-xs text-neutral-500 font-mono">{{ v.roomName.value }}</span>
    </header>

    <div class="grid gap-4 lg:grid-cols-[1fr_400px]">
      <!-- Conversation -->
      <section class="flex flex-col gap-4 min-w-0">
        <UCard :ui="{ body: 'p-6 sm:p-8' }">
          <div class="flex flex-col items-center gap-6">
            <div class="relative size-44 flex items-center justify-center">
              <div class="absolute inset-0 rounded-full ring-8 transition-all duration-300"
                   :class="[st.ring, pulsing ? 'animate-ping opacity-40' : 'opacity-60']" />
              <div class="size-32 rounded-full shadow-2xl transition-[background-color] duration-300 flex items-center justify-center"
                   :class="[st.color, pulsing && 'animate-pulse']"
                   :style="{ transform: `scale(${orbScale})`, transition: 'transform 80ms linear, background-color 300ms' }">
                <UIcon :name="agentState === 'thinking' ? 'i-lucide-brain' : agentState === 'speaking' ? 'i-lucide-audio-lines' : 'i-lucide-bot'"
                       class="size-12 text-neutral-950/70" />
              </div>
            </div>
            <div class="text-center">
              <div class="text-2xl font-semibold">{{ st.label }}</div>
              <div class="text-sm text-neutral-500 mt-1">
                <template v-if="!inCall">Press start and talk. The robot can move its arms.</template>
                <template v-else-if="!agentHere">Waiting for the agent worker to join…</template>
                <template v-else-if="!micOn">Mic muted. Type below instead.</template>
                <template v-else>Just talk. Say “stop” anytime.</template>
              </div>
            </div>

            <div class="flex flex-wrap justify-center gap-3">
              <UButton v-if="!inCall" size="xl" color="primary" icon="i-lucide-phone" @click="v.connect()">Start talking</UButton>
              <template v-else>
                <UButton size="xl" :color="micOn ? 'neutral' : 'warning'" :variant="micOn ? 'soft' : 'solid'"
                         :icon="micOn ? 'i-lucide-mic' : 'i-lucide-mic-off'" @click="v.toggleMic()">
                  {{ micOn ? 'Mute' : 'Unmute' }}
                  <span v-if="micOn" class="ml-1 inline-block w-10 h-1.5 rounded bg-neutral-800 overflow-hidden align-middle">
                    <span class="block h-full bg-emerald-400" :style="{ width: `${Math.round(micLevel * 100)}%` }" />
                  </span>
                </UButton>
                <UButton size="xl" color="neutral" variant="outline" icon="i-lucide-phone-off" @click="v.disconnect()">End</UButton>
              </template>
              <UButton size="xl" color="error" icon="i-lucide-octagon-x" class="font-bold px-8" @click="stopAll">STOP</UButton>
            </div>
            <UButton v-if="v.audioBlocked.value" color="warning" icon="i-lucide-volume-2" @click="v.unlockAudio()">Click to enable sound</UButton>
            <p v-if="v.micError.value" class="text-sm text-amber-400 text-center max-w-lg">{{ v.micError.value }}</p>
            <p v-if="error" class="text-sm text-red-400 text-center max-w-lg">{{ error }}</p>
          </div>
        </UCard>

        <UCard class="flex-1 flex flex-col" :ui="{ body: 'p-0 sm:p-0 flex-1 flex flex-col' }">
          <template #header>
            <div class="flex items-center justify-between">
              <span class="font-medium">Transcript</span>
              <span class="text-xs text-neutral-500">{{ lines.length }} lines</span>
            </div>
          </template>
          <div ref="scroller" class="h-[42vh] min-h-64 overflow-y-auto p-4 space-y-3">
            <div v-if="!lines.length" class="h-full flex flex-col items-center justify-center gap-3 text-neutral-500 text-sm">
              <span>Nothing said yet. Try:</span>
              <div class="flex flex-wrap justify-center gap-2">
                <UButton v-for="s in suggestions" :key="s" size="xs" variant="soft" color="neutral" :disabled="!agentHere" @click="v.say(s)">{{ s }}</UButton>
              </div>
            </div>
            <div v-for="l in lines" :key="l.id" class="flex" :class="l.who === 'user' ? 'justify-end' : 'justify-start'">
              <div class="max-w-[80%] rounded-2xl px-4 py-2 text-sm leading-relaxed"
                   :class="[l.who === 'user' ? 'bg-primary-500/15 text-primary-100 rounded-br-sm' : 'bg-neutral-800 rounded-bl-sm', !l.final && 'opacity-60 italic']">
                {{ l.text }}
              </div>
            </div>
          </div>
          <form class="border-t border-neutral-800 p-3 flex gap-2" @submit.prevent="send">
            <UInput v-model="draft" class="flex-1" placeholder="Type to the robot…" :disabled="!agentHere" />
            <UButton type="submit" icon="i-lucide-send" :disabled="!agentHere || !draft.trim()">Send</UButton>
          </form>
        </UCard>
      </section>

      <!-- Robot side -->
      <aside class="space-y-4">
        <div class="relative rounded-lg overflow-hidden bg-black border border-neutral-800 aspect-video">
          <video ref="camEl" autoplay playsinline muted class="w-full h-full object-contain" />
          <span class="absolute top-2 left-2 text-xs bg-black/60 px-2 py-0.5 rounded">Overhead</span>
          <div v-if="!robot.tracks.value.overhead_camera" class="absolute inset-0 flex items-center justify-center text-neutral-600 text-sm">no video</div>
        </div>

        <UCard :ui="{ body: 'p-0 sm:p-0' }">
          <template #header>
            <div class="flex items-center justify-between">
              <span class="font-medium">Robot actions</span>
              <UBadge v-if="tools.some(t => t.status === 'running')" color="warning" variant="subtle">
                {{ tools.filter(t => t.status === 'running').length }} running
              </UBadge>
            </div>
          </template>
          <div class="max-h-[60vh] overflow-y-auto divide-y divide-neutral-800">
            <div v-if="!tools.length" class="p-4 text-sm text-neutral-500">No actions yet. Tool calls show up here as the robot works.</div>
            <div v-for="c in tools" :key="c.call_id" class="p-3 space-y-1.5" :data-now="now">
              <div class="flex items-center gap-2">
                <UIcon :name="toolIcon[c.status]" class="size-4 shrink-0" :class="[toolColor[c.status], c.status === 'running' && 'animate-spin']" />
                <span class="font-mono text-sm font-medium">{{ c.name }}</span>
                <span class="flex-1" />
                <span class="text-xs text-neutral-500 tabular-nums">{{ time(c.t) }} · {{ elapsed(c) }}</span>
              </div>
              <div v-if="c.args && c.args !== '{}'" class="text-xs text-neutral-400 break-words">{{ prettyArgs(c.args) }}</div>
              <div v-for="(p, i) in c.progress.slice(-3)" :key="i" class="text-xs text-amber-300/80 pl-6 break-words">↳ {{ p }}</div>
              <div v-if="c.result" class="text-xs pl-6 break-words line-clamp-4" :class="c.status === 'error' ? 'text-red-300' : 'text-neutral-300'">{{ c.result }}</div>
            </div>
          </div>
        </UCard>
      </aside>
    </div>
  </div>
</template>
