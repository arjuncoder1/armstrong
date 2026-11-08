<script setup lang="ts">
defineProps<{ title: string, description: string }>()
const route = useRoute()
</script>

<template>
  <div class="workspace">
    <aside class="workspace-nav">
      <NuxtLink to="/" class="brand" aria-label="Armstrong home">
        <span class="brand-symbol"><UIcon name="i-lucide-orbit" /></span>
        <span>armstrong<span class="brand-period">.</span></span>
      </NuxtLink>
      <div class="workspace-label">Your workspace</div>
      <nav aria-label="Main navigation">
        <NuxtLink to="/" :class="{ selected: route.path === '/' }"><UIcon name="i-lucide-sliders-horizontal" />Control room<UIcon name="i-lucide-chevron-right" class="nav-arrow" /></NuxtLink>
        <NuxtLink to="/voice" :class="{ selected: route.path === '/voice' }"><UIcon name="i-lucide-audio-lines" />Voice studio<UIcon name="i-lucide-chevron-right" class="nav-arrow" /></NuxtLink>
        <a href="/tabletop/index.html"><UIcon name="i-lucide-box" />Viz<UIcon name="i-lucide-chevron-right" class="nav-arrow" /></a>
      </nav>
      <div class="nav-foot"><UIcon name="i-lucide-bot" class="size-5" /><div>Blackjack Robot<span>Armstrong workspace</span></div></div>
    </aside>
    <div class="workspace-body">
      <header class="page-header"><div><h1>{{ title }}</h1><p>{{ description }}</p></div><div class="header-actions"><slot name="actions" /></div></header>
      <main><slot /></main>
      <footer class="workspace-footer"><span>Armstrong <span class="footer-divider">/</span> Human direction. Robot action.</span><span>Keep the workspace clear while arms are moving.</span></footer>
    </div>
  </div>
</template>
