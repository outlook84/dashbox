<script setup lang="ts">
import { HelpCircle } from "@lucide/vue";
import { NIcon, NTooltip } from "naive-ui";
import { computed, onBeforeUnmount, onMounted, ref } from "vue";

defineProps<{
  label: string;
  tooltip: string;
}>();

const isMobileTooltip = ref(false);
const mobileTooltipOpen = ref(false);
const tooltipId = Symbol("field-label-tooltip");

const desktopTooltipTrigger = computed(() => (isMobileTooltip.value ? "manual" : "hover"));

let mediaQuery: MediaQueryList | undefined;

const closeTooltipEvent = "dashbox:close-field-label-tooltips";

function updateTooltipMode() {
  isMobileTooltip.value = mediaQuery?.matches ?? false;
  if (!isMobileTooltip.value) {
    mobileTooltipOpen.value = false;
  }
}

function toggleMobileTooltip(event: Event) {
  if (!isMobileTooltip.value) {
    return;
  }
  event.preventDefault();
  event.stopPropagation();
  const nextOpen = !mobileTooltipOpen.value;
  if (nextOpen) {
    window.dispatchEvent(new CustomEvent(closeTooltipEvent, { detail: tooltipId }));
  }
  mobileTooltipOpen.value = nextOpen;
}

function closeMobileTooltip() {
  mobileTooltipOpen.value = false;
}

function closeOtherMobileTooltip(event: Event) {
  if (event instanceof CustomEvent && event.detail === tooltipId) {
    return;
  }
  closeMobileTooltip();
}

onMounted(() => {
  mediaQuery = window.matchMedia("(max-width: 760px), (pointer: coarse)");
  updateTooltipMode();
  mediaQuery.addEventListener("change", updateTooltipMode);
  window.addEventListener("click", closeMobileTooltip);
  window.addEventListener(closeTooltipEvent, closeOtherMobileTooltip);
});

onBeforeUnmount(() => {
  mediaQuery?.removeEventListener("change", updateTooltipMode);
  window.removeEventListener("click", closeMobileTooltip);
  window.removeEventListener(closeTooltipEvent, closeOtherMobileTooltip);
});
</script>

<template>
  <span class="field-label">
    <span>{{ label }}</span>
    <NTooltip :trigger="desktopTooltipTrigger" :show="isMobileTooltip ? false : undefined">
      <template #trigger>
        <NIcon
          class="field-label-help"
          size="14"
          :aria-label="tooltip"
          :aria-expanded="isMobileTooltip ? mobileTooltipOpen : undefined"
          :role="isMobileTooltip ? 'button' : undefined"
          :tabindex="isMobileTooltip ? 0 : undefined"
          @click="toggleMobileTooltip"
          @keydown.enter.prevent="toggleMobileTooltip"
          @keydown.space.prevent="toggleMobileTooltip"
        >
          <HelpCircle />
        </NIcon>
      </template>
      {{ tooltip }}
    </NTooltip>
    <Teleport to="body">
      <div v-if="isMobileTooltip && mobileTooltipOpen" class="field-label-mobile-tooltip" role="tooltip" @click.stop>
        {{ tooltip }}
      </div>
    </Teleport>
  </span>
</template>
