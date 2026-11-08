<script setup lang="ts">
import { computed, nextTick, ref, watch } from "vue"

// 「其他（请输入）」是固定末项，内部只用 OTHER_VALUE 标记，
// 永远不作为业务值上抛——业务值在「其他」态下来自下方输入框。
const OTHER_VALUE = "__other__"

const props = withDefaults(
  defineProps<{
    /** 当前值；"" = 未选（首项）。处于「其他」态时为输入框实时内容。 */
    modelValue: string
    /** 普通选项，不含「其他」（「其他」固定由组件补在最后）。 */
    options: string[]
    /** select 首项（空值）的提示文案。 */
    placeholder: string
    /** 仅用于 placeholder 语义（该字段是否允许为空），校验仍由调用方做。 */
    allowEmpty?: boolean
  }>(),
  {
    allowEmpty: true,
  }
)

const emit = defineEmits<{
  (e: "update:modelValue", value: string): void
}>()

// select 当前展示值："" = 首项 / 某普通选项原文 / OTHER_VALUE
const selectValue = ref("")
// 「其他」态下输入框缓存的自定义值
const customText = ref("")
const customInput = ref<HTMLInputElement | null>(null)

// 输入框的 emit 会让 modelValue 下一 tick 原路回来，
// 用该标记跳过这次回环，避免把正在输入的内容误判为外部重置。
let selfEmitted = false

const isOther = computed(() => selectValue.value === OTHER_VALUE)

/** 按外部 modelValue 同步内部展示状态（首次挂载 / 弹窗重置 / 外部回填）。 */
function syncFromModelValue() {
  const value = props.modelValue

  if (value === "") {
    // 空 → 首项
    selectValue.value = ""
    customText.value = ""
    return
  }

  if (props.options.includes(value)) {
    // 值等于某选项 → select 显示该项
    selectValue.value = value
    customText.value = ""
    return
  }

  // 值非空且不是选项 → 自动进入「其他」态并回填输入框
  selectValue.value = OTHER_VALUE
  customText.value = value
}

syncFromModelValue()

watch(
  () => props.modelValue,
  () => {
    if (selfEmitted) {
      selfEmitted = false
      return
    }
    syncFromModelValue()
  }
)

function onSelectChange(event: Event) {
  selfEmitted = false
  selectValue.value = (event.target as HTMLSelectElement).value

  if (selectValue.value === OTHER_VALUE) {
    // 选「其他」→ 显示输入框并聚焦；此刻不 emit，值跟随输入实时 emit
    customText.value = ""
    void nextTick(() => {
      customInput.value?.focus()
    })
    return
  }

  // 选回任意普通项或首项空值 → 隐藏输入框并清空自定义缓存，直传选项文本
  customText.value = ""
  emit("update:modelValue", selectValue.value)
}

function onCustomInput(event: Event) {
  const value = (event.target as HTMLInputElement).value
  customText.value = value
  selfEmitted = true
  emit("update:modelValue", value)
}
</script>

<template>
  <div class="reason-select">
    <select
      :value="selectValue"
      @change="onSelectChange"
    >
      <option value="">
        {{ placeholder }}
      </option>

      <option
        v-for="option in options"
        :key="option"
        :value="option"
      >
        {{ option }}
      </option>

      <option :value="OTHER_VALUE">
        其他（请输入）
      </option>
    </select>

    <input
      v-if="isOther"
      ref="customInput"
      :value="customText"
      class="custom-input"
      type="text"
      placeholder="请输入自定义内容"
      @input="onCustomInput"
    />
  </div>
</template>

<style scoped>
.reason-select {
  display: flex;
  flex-direction: column;
  gap: 6px;
  width: 100%;
  font-size: 12px;
}

.reason-select select,
.reason-select input {
  width: 100%;
  min-height: 32px;
  padding: 6px 9px;
  color: #1a2a3a;
  font-size: 12px;
  background: #fff;
  border: 1px solid #d9d9d9;
  border-radius: 2px;
  outline: none;
}

.reason-select select:focus,
.reason-select input:focus {
  border-color: #1890ff;
  box-shadow: 0 0 0 2px rgba(24, 144, 255, 0.12);
}
</style>
