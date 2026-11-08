<script setup lang="ts">
// The 3D blackjack tabletop keeps its own UI: /viz just opens it (served at /tabletop/, see nuxt.config.ts).
if (import.meta.client) window.location.replace('/tabletop/index.html')
</script>

<template>
  <div />
</template>
