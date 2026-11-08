import { fileURLToPath } from 'node:url'

export default defineNuxtConfig({
  compatibilityDate: '2025-07-15',
  modules: ['@nuxt/ui'],
  css: ['~/assets/css/main.css'],
  ssr: false,
  devtools: { enabled: false },
  app: { head: { title: 'Armstrong Control', htmlAttrs: { class: 'dark' } } },
  colorMode: { preference: 'dark', fallback: 'dark' },
  runtimeConfig: {
    // Robot tabletop services behind the Viz tab (server/routes/tabletop). Override with NUXT_VIZ_API_URL / NUXT_VIZ_CAM_URL,
    // e.g. http://amd-halo.local:8202 when the frontend runs on a laptop.
    vizApiUrl: 'http://127.0.0.1:8202',
    vizCamUrl: 'http://127.0.0.1:8204',
    // The 3D tabletop's source folder, served live at /tabletop/ (server/routes/tabletop/[...path].ts). NUXT_TABLETOP_DIR.
    tabletopDir: fileURLToPath(new URL('../tools/blackjack/tabletop', import.meta.url)),
    public: {
      tokenUrl: 'http://127.0.0.1:8787/token',
      room: 'armstrong-local',
    },
  },
})
