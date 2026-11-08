// /tabletop/api/* -> tabletop server (tools/blackjack/tabletop_server.py, :8202) /api/*
export default defineEventHandler(event => vizProxy(event, useRuntimeConfig(event).vizApiUrl, 'api/'))
