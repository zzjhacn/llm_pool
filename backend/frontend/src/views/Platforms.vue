<template>
  <div>
    <div style="margin-bottom: 12px; display: flex; justify-content: space-between">
      <h3 style="margin: 0">平台管理</h3>
      <el-button type="primary" @click="openCreate">新增平台</el-button>
    </div>
    <el-table :data="rows" border>
      <el-table-column prop="id" label="ID" width="140" />
      <el-table-column prop="name" label="名称" />
      <el-table-column prop="api_base" label="API 地址" />
      <el-table-column prop="provider" label="厂商键" width="100" />
      <el-table-column prop="enabled" label="启用" width="90">
        <template #default="{ row }"><el-tag :type="row.enabled ? 'success' : 'info'">{{ row.enabled ? '是' : '否' }}</el-tag></template>
      </el-table-column>
      <el-table-column label="操作" width="160">
        <template #default="{ row }">
          <el-button size="small" @click="openEdit(row)">编辑</el-button>
          <el-button size="small" type="danger" @click="remove(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="visible" :title="editing ? '编辑平台' : '新增平台'" width="480px">
      <el-form :model="form" label-width="90px">
        <el-form-item label="ID"><el-input v-model="form.id" :disabled="editing" /></el-form-item>
        <el-form-item label="名称"><el-input v-model="form.name" /></el-form-item>
        <el-form-item label="API 地址"><el-input v-model="form.api_base" /></el-form-item>
        <el-form-item label="厂商键(provider)">
          <el-select v-model="form.provider" filterable allow-create default-first-option clearable placeholder="LiteLLM 厂商键，如 openai / dashscope" style="width: 100%">
            <el-option v-for="p in PROVIDER_OPTIONS" :key="p" :label="p" :value="p" />
          </el-select>
          <div style="color: #909399; font-size: 12px; line-height: 1.7; margin-top: 4px">
            由平台端点形态决定，旗下所有模型默认继承。OpenAI 兼容端点（<code>api_base</code> 含 <code>compatible-mode</code> 或结尾 <code>/v1</code>）选 <b>openai</b>；
            厂商原生端点才选 <b>dashscope</b>/<b>azure</b>/<b>bedrock</b> 等。留空按 <b>openai</b> 处理。
          </div>
        </el-form-item>
        <el-form-item label="Key"><el-input v-model="form.api_key" type="password" show-password /></el-form-item>
        <el-form-item label="启用"><el-switch v-model="form.enabled" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="visible = false">取消</el-button>
        <el-button type="primary" @click="submit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { api } from '../api'
import { ElMessage, ElMessageBox } from 'element-plus'

const PROVIDER_OPTIONS = [
  'openai', 'deepseek', 'dashscope', 'moonshot', 'azure', 'anthropic',
  'ollama', 'gemini', 'bedrock', 'groq', 'together',
]

const rows = ref([])
const visible = ref(false)
const editing = ref(false)
const form = ref({ id: '', name: '', api_base: '', provider: 'openai', api_key: '', enabled: true })

async function load() {
  const { data } = await api.listPlatforms()
  rows.value = data
}
function openCreate() {
  editing.value = false
  form.value = { id: '', name: '', api_base: '', provider: 'openai', api_key: '', enabled: true }
  visible.value = true
}
function openEdit(row) {
  editing.value = true
  form.value = { ...row }
  visible.value = true
}
async function submit() {
  if (editing.value) await api.updatePlatform(form.value.id, form.value)
  else await api.createPlatform(form.value)
  visible.value = false
  ElMessage.success('已保存')
  load()
}
async function remove(row) {
  await ElMessageBox.confirm(`确认删除平台 ${row.id}？`)
  await api.deletePlatform(row.id)
  ElMessage.success('已删除')
  load()
}
onMounted(load)
</script>
