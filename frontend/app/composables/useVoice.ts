import { Room, RoomEvent, Track, ConnectionState, ParticipantKind } from 'livekit-client'
import type { RemoteTrack, RemoteParticipant, TextStreamReader, Participant } from 'livekit-client'

// Must match manifest_voice_agent.py
export const AGENT_NAME = 'armstrong-manifest'
export const TOOLS_TOPIC = 'armstrong.tools'

export type AgentState = 'disconnected' | 'connecting' | 'initializing' | 'listening' | 'thinking' | 'speaking' | 'idle'
export interface Line { id: string, who: 'user' | 'agent', text: string, final: boolean, t: number }
export interface ToolCall {
  call_id: string
  name: string
  args: string
  status: 'running' | 'done' | 'error' | 'cancelled'
  progress: string[]
  result: string | null
  t: number
  ended?: number
}

/** A level meter (0..1) for a MediaStreamTrack. */
function meter(ctx: AudioContext, mst: MediaStreamTrack) {
  const src = ctx.createMediaStreamSource(new MediaStream([mst]))
  const an = ctx.createAnalyser()
  an.fftSize = 512
  src.connect(an)
  const buf = new Uint8Array(an.fftSize)
  return {
    level() {
      an.getByteTimeDomainData(buf)
      let sum = 0
      for (const v of buf) { const x = (v - 128) / 128; sum += x * x }
      return Math.min(1, Math.sqrt(sum / buf.length) * 4)
    },
    stop() { src.disconnect() },
  }
}

export function useVoice() {
  const config = useRuntimeConfig()
  const room = shallowRef<Room | null>(null)
  const conn = ref<ConnectionState | 'error'>(ConnectionState.Disconnected)
  const agentState = ref<AgentState>('disconnected')
  const agentHere = ref(false)
  const micOn = ref(true)
  const lines = ref<Line[]>([])
  const tools = ref<ToolCall[]>([])
  const error = ref<string | null>(null)
  const agentLevel = ref(0)
  const micLevel = ref(0)
  const roomName = ref('')
  const audioBlocked = ref(false) // browser refused autoplay: needs one more click
  const micError = ref<string | null>(null)

  let audioCtx: AudioContext | null = null
  let agentMeter: ReturnType<typeof meter> | null = null
  let micMeter: ReturnType<typeof meter> | null = null
  let raf = 0
  const audioEls: HTMLMediaElement[] = []

  function upsertLine(id: string, who: Line['who'], text: string, final: boolean) {
    const i = lines.value.findIndex(l => l.id === id)
    if (i >= 0) lines.value[i] = { ...lines.value[i]!, text, final }
    else lines.value.push({ id, who, text, final, t: Date.now() })
  }

  function isAgent(p: Participant) {
    return p.kind === ParticipantKind.AGENT
  }

  function readAgentState(p: Participant) {
    const s = p.attributes['lk.agent.state'] as AgentState | undefined
    if (s) agentState.value = s
  }

  function onTool(msg: Record<string, unknown>) {
    const id = String(msg.call_id)
    const t = typeof msg.t === 'number' ? msg.t * 1000 : Date.now()
    let call = tools.value.find(c => c.call_id === id)
    if (msg.type === 'started') {
      if (!call) tools.value.unshift({ call_id: id, name: String(msg.name), args: String(msg.args ?? ''), status: 'running', progress: [], result: null, t })
      return
    }
    if (!call) {
      call = { call_id: id, name: '?', args: '', status: 'running', progress: [], result: null, t }
      tools.value.unshift(call)
      call = tools.value[0]!
    }
    if (msg.type === 'progress' && msg.message) call.progress.push(String(msg.message))
    if (msg.type === 'ended') {
      call.status = (msg.status as ToolCall['status']) ?? 'done'
      call.result = msg.message == null ? null : String(msg.message)
      call.ended = t
    }
  }

  function tick() {
    agentLevel.value = agentLevel.value * 0.6 + (agentMeter?.level() ?? 0) * 0.4
    micLevel.value = micLevel.value * 0.6 + (micOn.value ? (micMeter?.level() ?? 0) : 0) * 0.4
    raf = requestAnimationFrame(tick)
  }

  async function connect() {
    // Create/resume the AudioContext synchronously inside the click: Safari refuses it after any await.
    audioCtx ??= new AudioContext()
    audioCtx.resume().catch(() => {})
    await disconnect()
    micError.value = null
    error.value = null
    lines.value = []
    tools.value = []
    conn.value = ConnectionState.Connecting
    agentState.value = 'connecting'
    // A fresh room per session: token-config dispatch only fires when the room is created.
    roomName.value = `armstrong-voice-${Math.random().toString(36).slice(2, 8)}`
    const identity = `user-${Math.random().toString(36).slice(2, 6)}`
    try {
      const q = new URLSearchParams({ identity, room: roomName.value, agent: AGENT_NAME })
      // Deployed with ARMSTRONG_ACCESS_CODE: open the page as ...?code=<it> (server/api/token.get.ts).
      const code = new URLSearchParams(location.search).get('code')
      if (code) q.set('code', code)
      const res = await fetch(`${config.public.tokenUrl}?${q}`)
      if (res.status === 401) throw new Error('access code required: open this page with ?code=<access code>')
      if (!res.ok) throw new Error(`token endpoint ${res.status}`)
      const { url, token } = await res.json() as { url: string, token: string }

      const r = new Room({ adaptiveStream: true, audioCaptureDefaults: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } })
      r.on(RoomEvent.ConnectionStateChanged, (s) => {
        conn.value = s
        if (s === ConnectionState.Disconnected) agentState.value = 'disconnected'
      })
        .on(RoomEvent.ParticipantConnected, (p: RemoteParticipant) => {
          if (isAgent(p)) { agentHere.value = true; readAgentState(p) }
        })
        .on(RoomEvent.ParticipantDisconnected, (p: RemoteParticipant) => {
          if (isAgent(p)) { agentHere.value = false; agentState.value = 'disconnected' }
        })
        .on(RoomEvent.ParticipantAttributesChanged, (_c, p: Participant) => { if (isAgent(p)) readAgentState(p) })
        .on(RoomEvent.TrackSubscribed, (t: RemoteTrack, _pub, p: RemoteParticipant) => {
          if (t.kind !== Track.Kind.Audio) return
          const el = t.attach()
          el.style.display = 'none'
          document.body.appendChild(el)
          audioEls.push(el)
          if (isAgent(p) && audioCtx) { agentMeter?.stop(); agentMeter = meter(audioCtx, t.mediaStreamTrack) }
        })
        .on(RoomEvent.TrackUnsubscribed, (t: RemoteTrack) => { t.detach().forEach(el => el.remove()) })
        .on(RoomEvent.AudioPlaybackStatusChanged, () => { audioBlocked.value = !r.canPlaybackAudio })
        .on(RoomEvent.DataReceived, (payload, _p, _k, topic) => {
          if (topic !== TOOLS_TOPIC) return
          try { onTool(JSON.parse(new TextDecoder().decode(payload))) } catch { /* ignore */ }
        })

      r.registerTextStreamHandler('lk.transcription', async (reader: TextStreamReader, info) => {
        const a = reader.info.attributes ?? {}
        const id = a['lk.segment_id'] ?? reader.info.id
        const final = a['lk.transcription_final'] === 'true'
        const who: Line['who'] = info.identity === r.localParticipant.identity ? 'user' : 'agent'
        let text = ''
        for await (const chunk of reader) {
          text += chunk
          upsertLine(id, who, text, final)
        }
        upsertLine(id, who, text, final || who === 'agent')
      })

      await r.connect(url, token)
      room.value = r
      // Neither of these is fatal: without audio you get the transcript, without the mic you can type.
      try { await r.startAudio() }
      catch { /* handled below */ }
      audioBlocked.value = !r.canPlaybackAudio
      try {
        await r.localParticipant.setMicrophoneEnabled(true)
        micOn.value = true
        const micPub = r.localParticipant.getTrackPublication(Track.Source.Microphone)
        if (micPub?.track?.mediaStreamTrack && audioCtx) micMeter = meter(audioCtx, micPub.track.mediaStreamTrack)
      }
      catch (e) {
        micOn.value = false
        micError.value = (e as Error).name === 'NotAllowedError'
          ? 'Microphone blocked. Allow it for this site (address bar → site settings), then press Unmute. You can type meanwhile.'
          : `Microphone failed: ${(e as Error).message}`
      }
      for (const p of r.remoteParticipants.values()) if (isAgent(p)) { agentHere.value = true; readAgentState(p) }
      if (!agentHere.value) agentState.value = 'initializing'
      cancelAnimationFrame(raf)
      raf = requestAnimationFrame(tick)
    }
    catch (e) {
      conn.value = 'error'
      agentState.value = 'disconnected'
      const err = e as Error
      error.value = err.name === 'NotAllowedError'
        ? `Browser blocked it: ${err.message}`
        : `${err.message}. Is the stack running (uv run main.py stack) and the agent worker (uv run main.py manifest-voice dev)?`
    }
  }

  async function disconnect() {
    cancelAnimationFrame(raf)
    agentMeter?.stop(); micMeter?.stop(); agentMeter = micMeter = null
    audioEls.splice(0).forEach(el => el.remove())
    await room.value?.disconnect()
    room.value = null
    agentHere.value = false
    agentLevel.value = micLevel.value = 0
    audioBlocked.value = false
  }

  async function toggleMic() {
    const r = room.value
    if (!r) return
    const want = !micOn.value
    try {
      await r.localParticipant.setMicrophoneEnabled(want)
      micOn.value = want
      micError.value = null
      const mst = r.localParticipant.getTrackPublication(Track.Source.Microphone)?.track?.mediaStreamTrack
      if (want && mst && audioCtx && !micMeter) micMeter = meter(audioCtx, mst)
    }
    catch (e) {
      micOn.value = false
      micError.value = (e as Error).name === 'NotAllowedError'
        ? 'Microphone still blocked. Allow it in the site settings, then try again.'
        : `Microphone failed: ${(e as Error).message}`
    }
  }

  /** Click handler for when the browser blocked playback. */
  async function unlockAudio() {
    audioCtx?.resume().catch(() => {})
    try { await room.value?.startAudio() } catch { /* still blocked */ }
    audioBlocked.value = !(room.value?.canPlaybackAudio ?? true)
  }

  /** Typed message to the agent (its text input on lk.chat). */
  async function say(text: string) {
    const r = room.value
    if (!r || !text.trim()) return
    upsertLine(`typed-${Date.now()}`, 'user', text.trim(), true)
    await r.localParticipant.sendText(text.trim(), { topic: 'lk.chat' })
  }

  onBeforeUnmount(() => { disconnect(); audioCtx?.close().catch(() => {}) })

  return { room, conn, agentState, agentHere, micOn, lines, tools, error, agentLevel, micLevel, roomName, audioBlocked, micError, connect, disconnect, toggleMic, unlockAudio, say }
}
