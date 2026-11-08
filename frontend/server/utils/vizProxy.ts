import type { H3Event } from 'h3'

/** Forward /tabletop/<prefix>/<rest>?<query> to <target>/<upstreamPrefix><rest>?<query> (the robot's tabletop services). */
export function vizProxy(event: H3Event, target: string, upstreamPrefix: string) {
  const rest = getRouterParam(event, 'path') ?? ''
  const query = getRequestURL(event).search
  return proxyRequest(event, `${target.replace(/\/$/, '')}/${upstreamPrefix}${rest}${query}`)
}
