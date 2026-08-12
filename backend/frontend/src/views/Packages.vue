<template>
  <div>
    <el-alert type="info" :closable="false" show-icon style="margin-bottom: 12px">
      <template #title>额度包 = 多个模型共享的采购资源池</template>
      <div style="line-height: 1.7">
        一个额度包可被<b>多个模型共用</b>；包的余额耗尽会<b>自动停用其下全部模型</b>。<br />
        <b>规则</b>：一个包只能是一种计费单位（token 或 call），挂到此包的模型计费方式必须一致；
        若模型不需要共享，请用「模型独立额度」模式，无需建包。
      </div>
    </el-alert>
    <div style="margin-bottom: 12px; display: flex; justify-content: space-between">
      <h3 style="margin: 0">额度包管理</h3>
      <el-button type="primary" @click="openCreate">新增额度包</el-button>
    </div>
    <el-table :data="rows" border>
      <el-table-column prop="id" label="ID" width="160" />
      <el-table-column prop="name" label="名称" />
      <el-table-column prop="unit" label="计费单位" width="100" />
      <el-table-column prop="capacity" label="总量" width="120" />
      <el-table-column prop="used" label="已用" width="120" />
      <el-table-column label="余额" width="120">
        <template #default="{ row }"><el-tag :type="row.balance > 0 ? 'success' : 'danger'">{{ row.balance }}</el-tag></template>
      </el-table-column>
      <el-table-column label="操作" width="160">
        <template #default="{ row }">
          <el-button size="small" @click="openEdit(row)">编辑</el-button>
          <el-button size="small" type="danger" @click="remove(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="visible" :title="editing ? '编辑额度包' : '新增额度包'" width="440px">
      <el-form :model="form" label-width="90px">
        <el-form-item label="ID"><el-input v-model="form.id" :disabled="editing" /></el-form-item>
        <el-form-item label="名称"><el-input v-model="form.name" /></el-form-item>
        <el-form-item label="计费单位">
          <el-select v-model="form.unit"><el-option label="token" value="token" /><el-option label="call" value="call" /></el-select>
        </el-form-item>
        <el-form-item label="总量"><el-input-number v-model="form.capacity" :min="0" /></el-form-item>
        <el-form-item label="已用"><el-input-number v-model="form.used" :min="0" /></el-form-item>
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

const rows = ref([])
const visible = ref(false)
const editing = ref(false)
const form = ref({ id: '', name: '', unit: 'token', capacity: 0, used: 0 })

async function load() {
  const { data } = await api.listPackages()
  rows.value = data
}
function openCreate() {
  editing.value = false
  form.value = { id: '', name: '', unit: 'token', capacity: 0, used: 0 }
  visible.value = true
}
function openEdit(row) {
  editing.value = true
  form.value = { ...row }
  visible.value = true
}
async function submit() {
  if (editing.value) await api.updatePackage(form.value.id, form.value)
  else await api.createPackage(form.value)
  visible.value = false
  ElMessage.success('已保存')
  load()
}
async function remove(row) {
  await ElMessageBox.confirm(`确认删除额度包 ${row.id}？`)
  await api.deletePackage(row.id)
  ElMessage.success('已删除')
  load()
}
onMounted(load)
</script>
