<script setup lang="ts">
import { defineAsyncComponent } from "vue";

const ConfigEditorPage = defineAsyncComponent(() => import("./ConfigEditorPage.vue"));
</script>

<template>
  <ConfigEditorPage />
</template>
