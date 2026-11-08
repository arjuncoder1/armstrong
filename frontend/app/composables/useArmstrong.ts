import { Room, RoomEvent, RpcError, Track, ConnectionState } from 'livekit-client'
import type { RemoteTrack, RemoteTrackPublication, RemoteParticipant } from 'livekit-client'

// Must match thirdparty/portal-makermods/src/utils/common.py
export const ROBOT_IDENTITY = 'robot'
export const DREAM_IDENTITY = 'policy-dream-1-tasks'
export const RPC = {
  status: 'dream.status',
  setTask: 'dream.set_task',
  pause: 'dream.pause',
  resume: 'dream.resume',
  toTeleop: 'dream.to_teleop',
  home: 'home', // payload HOME_CONFIRMED = "grippers_empty" (manifest_bridge.py)
  park: 'park', // payload PARK_ONLY = "park"
} as const
export const CAMERAS = ['overhead_camera', 'left_wrist_camera', 'right_wrist_camera'] as const
export type Camera = (typeof CAMERAS)[number]

const HINTS: Record<string, string> = {
  [DREAM_IDENTITY]: 'Start the Dream node: uv run main.py dream',
  [ROBOT_IDENTITY]: 'Start the robot bridge (Portal robot peer for the Maker Arms)',
}

export interface LogEntry { t: string, level: 'info' | 'ok' | 'error', msg: string }

export function useArmstrong() {
  const config = useRuntimeConfig()
  const room = shallowRef<Room | null>(null)
  const state = ref<ConnectionState | string>('disconnected')
  const participants = ref<string[]>([])
  const tracks = shallowRef<Partial<Record<Camera, RemoteTrack>>>({})
  const log = ref<LogEntry[]>([])
  const identity = `web-${Math.random().toString(36).slice(2, 8)}`

  function addLog(level: LogEntry['level'], msg: string) {
    log.value.unshift({ t: new Date().toLocaleTimeString(), level, msg })
    if (log.value.length > 200) log.value.pop()
  }

  function refreshParticipants() {
    participants.value = room.value ? [...room.value.remoteParticipants.keys()].sort() : []
  }

  function setTrack(name: string, track: RemoteTrack | null) {
    if (!(CAMERAS as readonly string[]).includes(name)) return
    const next = { ...tracks.value }
    if (track) next[name as Camera] = track
    else delete next[name as Camera]
    tracks.value = next
  }

  async function connect() {
    if (room.value) await room.value.disconnect()
    state.value = 'connecting'
    try {
      const url = `${config.public.tokenUrl}?identity=${encodeURIComponent(identity)}&room=${encodeURIComponent(config.public.room as string)}`
      const res = await fetch(url)
      if (!res.ok) throw new Error(`token endpoint ${res.status}`)
      const { url: wsUrl, token } = await res.json() as { url: string, token: string }
      const r = new Room({ adaptiveStream: true, dynacast: false })
      r.on(RoomEvent.ConnectionStateChanged, (s) => { state.value = s })
        .on(RoomEvent.ParticipantConnected, (p: RemoteParticipant) => { addLog('info', `${p.identity} joined`); refreshParticipants() })
        .on(RoomEvent.ParticipantDisconnected, (p: RemoteParticipant) => { addLog('info', `${p.identity} left`); refreshParticipants() })
        .on(RoomEvent.TrackSubscribed, (t: RemoteTrack, pub: RemoteTrackPublication) => {
          if (t.kind === Track.Kind.Video) setTrack(pub.trackName, t)
        })
        .on(RoomEvent.TrackUnsubscribed, (_t: RemoteTrack, pub: RemoteTrackPublication) => setTrack(pub.trackName, null))
        .on(RoomEvent.Disconnected, () => { tracks.value = {}; refreshParticipants() })
      await r.connect(wsUrl, token, { autoSubscribe: true })
      room.value = r
      refreshParticipants()
      addLog('ok', `connected as ${identity}`)
    }
    catch (e) {
      state.value = 'error'
      addLog('error', `connect failed: ${(e as Error).message}. Is the LiveKit server (7880) and token endpoint (8787) running?`)
    }
  }

  async function rpc(dest: string, method: string, payload: string, quiet = false): Promise<string | null> {
    const r = room.value
    if (!r || r.state !== ConnectionState.Connected) {
      if (!quiet) addLog('error', `${method}: not connected`)
      return null
    }
    if (!r.remoteParticipants.has(dest)) {
      if (!quiet) addLog('error', `${method}: ${dest} not in room. ${HINTS[dest] ?? ''}`)
      return null
    }
    try {
      const reply = await r.localParticipant.performRpc({ destinationIdentity: dest, method, payload, responseTimeout: 15000 })
      if (!quiet) addLog('ok', `${method} → ${reply}`)
      return reply
    }
    catch (e) {
      let msg = (e as Error).message
      if (e instanceof RpcError && e.code === RpcError.ErrorCode.RECIPIENT_NOT_FOUND) msg = `${dest} not in room. ${HINTS[dest] ?? ''}`
      if (!quiet) addLog('error', `${method} failed: ${msg}`)
      return null
    }
  }

  onBeforeUnmount(() => { room.value?.disconnect() })

  return { identity, room, state, participants, tracks, log, addLog, connect, rpc }
}
