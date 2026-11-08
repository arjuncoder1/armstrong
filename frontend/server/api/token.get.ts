// LiveKit access token for the browser, minted where the frontend runs (the robot, a laptop, or a cloud host).
// Needs LIVEKIT_URL, LIVEKIT_API_KEY and LIVEKIT_API_SECRET in the server's environment (never sent to the browser).
// Optional ARMSTRONG_ACCESS_CODE: then the page must be opened with ?code=<it> (voice can move real arms).
import { createHmac, timingSafeEqual } from 'node:crypto'

const b64url = (v: string | Buffer) => Buffer.from(v).toString('base64url')

function sign(claims: Record<string, unknown>, secret: string) {
  const body = `${b64url(JSON.stringify({ alg: 'HS256', typ: 'JWT' }))}.${b64url(JSON.stringify(claims))}`
  return `${body}.${b64url(createHmac('sha256', secret).update(body).digest())}`
}

function sameText(a: string, b: string) {
  const x = Buffer.from(a), y = Buffer.from(b)
  return x.length === y.length && timingSafeEqual(x, y)
}

const NAME = /^[\w.-]{1,64}$/

export default defineEventHandler((event) => {
  const { LIVEKIT_URL: url, LIVEKIT_API_KEY: key, LIVEKIT_API_SECRET: secret, ARMSTRONG_ACCESS_CODE: code } = process.env
  if (!url || !key || !secret) throw createError({ statusCode: 503, statusMessage: 'LiveKit is not configured on this server' })

  const q = getQuery(event)
  if (code && !sameText(String(q.code ?? ''), code)) throw createError({ statusCode: 401, statusMessage: 'access code required' })
  const identity = String(q.identity ?? ''), room = String(q.room ?? ''), agent = q.agent ? String(q.agent) : ''
  if (!NAME.test(identity) || !NAME.test(room) || (agent && !NAME.test(agent))) throw createError({ statusCode: 400, statusMessage: 'bad identity, room or agent' })
  if (identity === 'robot') throw createError({ statusCode: 400, statusMessage: "identity 'robot' is the bridge's" })

  const now = Math.floor(Date.now() / 1000)
  const token = sign({
    iss: key, sub: identity, name: identity, jti: identity, nbf: now, exp: now + 6 * 3600,
    video: { roomJoin: true, room, canPublish: true, canSubscribe: true, canPublishData: true, canUpdateOwnMetadata: true },
    // Same as src/armstrong/stack.py: creating the room dispatches the voice agent.
    roomConfig: { name: room, minPlayoutDelay: 0, maxPlayoutDelay: 1, agents: agent ? [{ agentName: agent }] : [] },
  }, secret)
  setResponseHeader(event, 'Cache-Control', 'no-store')
  return { url, token }
})
