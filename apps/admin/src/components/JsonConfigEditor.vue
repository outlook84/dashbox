<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from "vue";
import { defaultKeymap, history, historyKeymap, indentWithTab } from "@codemirror/commands";
import { json, jsonParseLinter } from "@codemirror/lang-json";
import {
  bracketMatching,
  defaultHighlightStyle,
  foldGutter,
  foldKeymap,
  indentOnInput,
  syntaxHighlighting
} from "@codemirror/language";
import { linter, lintGutter } from "@codemirror/lint";
import { Compartment, EditorState } from "@codemirror/state";
import {
  drawSelection,
  dropCursor,
  EditorView,
  highlightActiveLine,
  highlightActiveLineGutter,
  keymap,
  lineNumbers,
  rectangularSelection
} from "@codemirror/view";

const props = defineProps<{ modelValue: string; readonly?: boolean }>();
const emit = defineEmits<{ "update:modelValue": [value: string] }>();

const editorRoot = ref<HTMLElement | null>(null);
const readOnlyConfig = new Compartment();
const editableConfig = new Compartment();
let view: EditorView | null = null;

function editorExtensions() {
  return [
    lineNumbers(),
    highlightActiveLineGutter(),
    foldGutter(),
    history(),
    drawSelection(),
    dropCursor(),
    rectangularSelection(),
    indentOnInput(),
    bracketMatching(),
    syntaxHighlighting(defaultHighlightStyle, { fallback: true }),
    json(),
    lintGutter(),
    linter(jsonParseLinter()),
    highlightActiveLine(),
    EditorView.lineWrapping,
    readOnlyConfig.of(EditorState.readOnly.of(Boolean(props.readonly))),
    editableConfig.of(EditorView.editable.of(!props.readonly)),
    keymap.of([indentWithTab, ...defaultKeymap, ...historyKeymap, ...foldKeymap]),
    EditorView.updateListener.of((update) => {
      if (!update.docChanged) return;
      const next = update.state.doc.toString();
      if (next !== props.modelValue) {
        emit("update:modelValue", next);
      }
    })
  ];
}

onMounted(() => {
  if (!editorRoot.value) return;
  view = new EditorView({
    parent: editorRoot.value,
    state: EditorState.create({
      doc: props.modelValue,
      extensions: editorExtensions()
    })
  });
});

watch(
  () => props.modelValue,
  (next) => {
    if (!view || next === view.state.doc.toString()) return;
    view.dispatch({
      changes: { from: 0, to: view.state.doc.length, insert: next }
    });
  }
);

watch(
  () => props.readonly,
  (next) => {
    if (!view) return;
    view.dispatch({
      effects: [
        readOnlyConfig.reconfigure(EditorState.readOnly.of(Boolean(next))),
        editableConfig.reconfigure(EditorView.editable.of(!next))
      ]
    });
  }
);

onBeforeUnmount(() => {
  view?.destroy();
  view = null;
});
</script>

<template>
  <div ref="editorRoot" class="json-editor" />
</template>

<style scoped>
.json-editor {
  border: 1px solid var(--color-border);
  border-radius: 3px;
  flex: 1 1 auto;
  height: max(560px, calc(100vh - 200px));
  min-height: 520px;
  overflow: hidden;
}

.json-editor:focus-within {
  border-color: var(--color-brand-focus);
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--color-brand-focus) 14%, transparent);
}

:deep(.cm-editor) {
  background: #ffffff;
  color: #1f2937;
  font-family:
    "Cascadia Code", "Cascadia Mono", "SFMono-Regular", "SF Mono", Menlo,
    Monaco, Consolas, "Roboto Mono", "Droid Sans Mono", "Liberation Mono",
    "DejaVu Sans Mono", monospace;
  font-size: 13px;
  height: 100%;
  line-height: 1.55;
}

:deep(.cm-scroller) {
  font-family:
    "Cascadia Code", "Cascadia Mono", "SFMono-Regular", "SF Mono", Menlo,
    Monaco, Consolas, "Roboto Mono", "Droid Sans Mono", "Liberation Mono",
    "DejaVu Sans Mono", monospace;
  overflow: auto;
}

:deep(.cm-gutters) {
  background: #f8fafc;
  border-right: 1px solid #e5e7eb;
  color: #6b7280;
}

:deep(.cm-activeLine),
:deep(.cm-activeLineGutter) {
  background: #f3f7f4;
}

:deep(.cm-foldGutter span) {
  cursor: pointer;
}

:deep(.cm-diagnostic) {
  font-size: 12px;
}
</style>
