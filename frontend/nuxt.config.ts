export default defineNuxtConfig({
  compatibilityDate: '2025-07-15',
  modules: ['@nuxt/ui'],
  css: ['~/assets/css/main.css'],
  ssr: false,
  devtools: { enabled: false },
  app: { head: { title: 'Armstrong Control', htmlAttrs: { class: 'dark' } } },
  colorMode: { preference: 'dark', fallback: 'dark' },
  runtimeConfig: {
    public: {
      tokenUrl: 'http://127.0.0.1:8787/token',
      room: 'armstrong-local',
    },
  },
})
