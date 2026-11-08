// /tabletop/cam/* -> overhead camera service (:8204) /*
export default defineEventHandler(event => vizProxy(event, useRuntimeConfig(event).vizCamUrl, ''))
