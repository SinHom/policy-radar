<script setup>
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import AppHeader from './components/AppHeader.vue'
import AppSidebar from './components/AppSidebar.vue'

const route = useRoute()
const mobileMenuOpen = ref(false)
</script>

<template>
  <AppHeader @toggle-menu="mobileMenuOpen = !mobileMenuOpen" />
  <div class="max-w-7xl mx-auto px-6 py-6 flex gap-6">
    <AppSidebar :open="mobileMenuOpen" @navigate="mobileMenuOpen = false" />
    <main class="flex-1 min-w-0">
      <router-view />
    </main>
  </div>
</template>
