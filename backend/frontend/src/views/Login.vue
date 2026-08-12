<template>
  <div style="height: 100%; display: flex; align-items: center; justify-content: center; background: #001529">
    <el-card style="width: 360px">
      <h2 style="margin-top: 0">模型池管理登录</h2>
      <el-form :model="form" @submit.prevent="onSubmit">
        <el-form-item>
          <el-input v-model="form.username" placeholder="用户名" :prefix-icon="User" />
        </el-form-item>
        <el-form-item>
          <el-input v-model="form.password" type="password" placeholder="密码" :prefix-icon="Lock" show-password @keyup.enter="onSubmit" />
        </el-form-item>
        <el-button type="primary" style="width: 100%" :loading="loading" @click="onSubmit">登录</el-button>
      </el-form>
    </el-card>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { User, Lock } from '@element-plus/icons-vue'
import { api } from '../api'
import { ElMessage } from 'element-plus'

const router = useRouter()
const form = ref({ username: 'admin', password: '' })
const loading = ref(false)

async function onSubmit() {
  loading.value = true
  try {
    const { data } = await api.login(form.value.username, form.value.password)
    localStorage.setItem('admin_token', data.token)
    router.push('/')
  } catch (e) {
    ElMessage.error('登录失败：' + (e.response?.data?.detail || e.message))
  } finally {
    loading.value = false
  }
}
</script>
