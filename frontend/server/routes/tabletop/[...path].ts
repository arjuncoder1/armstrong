// Serves tools/blackjack/tabletop/ at /tabletop/ exactly as its authors wrote it for its own server (:8202),
// rewriting root-relative URLs on the fly so the files never need editing:
//   '/api/...', '/vendor/...', '/app.js' (any top-level entry) -> '/tabletop/...'
//   the :8204 camera base -> '/tabletop/cam' (proxied, see ./cam/[...path].ts)
// /tabletop/api/* and /tabletop/cam/* are more specific routes, so they never reach this handler.
import { readdir, readFile, stat } from 'node:fs/promises'
import { extname, join, resolve, sep } from 'node:path'

const TYPES: Record<string, string> = {
  '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.mjs': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8', '.json': 'application/json', '.svg': 'image/svg+xml', '.png': 'image/png',
  '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.webp': 'image/webp', '.glb': 'model/gltf-binary', '.hdr': 'image/vnd.radiance',
  '.urdf': 'application/xml', '.xml': 'application/xml', '.md': 'text/plain; charset=utf-8', '.txt': 'text/plain; charset=utf-8',
  '.mp3': 'audio/mpeg', '.wav': 'audio/wav', '.ogg': 'audio/ogg', '.woff2': 'font/woff2',
}
const TEXT = new Set(['.html', '.js', '.mjs', '.css'])
const CAMERA_BASE = /`\$\{location\.protocol\}\/\/\$\{location\.hostname\}:8204`/g

function rewrite(src: string, entries: string[]) {
  const names = ['api', ...entries].map(n => n.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|')
  return src
    .replace(CAMERA_BASE, '`${location.origin}/tabletop/cam`')
    .replace(new RegExp(`(["'\`(])/(?=(?:${names})(?:[/?#"'\`)]|$))`, 'g'), '$1/tabletop/')
}

export default defineEventHandler(async (event) => {
  const root = resolve(useRuntimeConfig(event).tabletopDir)
  const rel = decodeURIComponent(getRouterParam(event, 'path') ?? '') || 'index.html'
  let file = resolve(root, rel)
  if (file !== root && !file.startsWith(root + sep)) throw createError({ statusCode: 403 })
  try { if ((await stat(file)).isDirectory()) file = join(file, 'index.html') }
  catch { throw createError({ statusCode: 404 }) }

  const ext = extname(file).toLowerCase()
  setResponseHeader(event, 'Content-Type', TYPES[ext] ?? 'application/octet-stream')
  setResponseHeader(event, 'Cache-Control', 'no-cache')
  const body = await readFile(file).catch(() => { throw createError({ statusCode: 404 }) })
  if (!TEXT.has(ext)) return body
  return rewrite(body.toString('utf8'), await readdir(root))
})
