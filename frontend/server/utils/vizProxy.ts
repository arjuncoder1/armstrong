import type { H3Event } from 'h3'

/** Forward /tabletop/<prefix>/<rest>?<query> to <target>/<upstreamPrefix><rest>?<query> (the robot's tabletop services).
 *
 * The tabletop server rejects requests whose Origin doesn't match its Host, so other websites can't drive the game.
 * Behind this proxy the browser's Origin is this app, never the upstream's host, so we enforce that same rule here
 * against this app's own host first, and only then present the request to the upstream as same-origin. */
export function vizProxy(event: H3Event, target: string, upstreamPrefix: string) {
  const origin = getRequestHeader(event, 'origin')
  const host = getRequestHeader(event, 'x-forwarded-host') ?? getRequestHeader(event, 'host')
  if (origin && new URL(origin).host !== host) {
    throw createError({ statusCode: 403, statusMessage: 'Cross-origin request rejected' })
  }

  const base = target.replace(/\/$/, '')
  const rest = getRouterParam(event, 'path') ?? ''
  const query = getRequestURL(event).search
  const upstream = new URL(base).origin
  return proxyRequest(event, `${base}/${upstreamPrefix}${rest}${query}`, {
    headers: origin ? { origin: upstream, referer: `${upstream}/` } : {},
  })
}
