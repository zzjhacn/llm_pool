<template>
  <el-container style="height: 100%">
    <el-aside width="200px" style="background: #001529">
      <div style="color: #fff; font-weight: 600; padding: 16px; font-size: 16px">模型池控制台</div>
      <el-menu
        background-color="#001529"
        text-color="#fff"
        active-text-color="#409eff"
        :default-active="active"
        router
      >
        <el-menu-item index="/models"><el-icon><Cpu /></el-icon>模型管理</el-menu-item>
        <el-menu-item index="/platforms"><el-icon><Connection /></el-icon>平台管理</el-menu-item>
        <el-menu-item index="/packages"><el-icon><Coin /></el-icon>额度包管理</el-menu-item>
        <el-menu-item index="/ledger"><el-icon><DataLine /></el-icon>账本看板</el-menu-item>
        <el-menu-item index="/chat-test"><el-icon><ChatDotRound /></el-icon>对话测试</el-menu-item>
      </el-menu>
    </el-aside>
    <el-container>
      <el-header style="background: #fff; display: flex; align-items: center; justify-content: flex-end; border-bottom: 1px solid #eee">
        <el-button text @click="logout">退出登录</el-button>
      </el-header>
      <el-main>
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()
const active = computed(() => route.path)

function logout() {
  localStorage.removeItem('admin_token')
  router.push('/login')
}
</script>
