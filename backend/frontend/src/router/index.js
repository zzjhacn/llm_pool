import { createRouter, createWebHistory } from 'vue-router'
import Login from '../views/Login.vue'
import MainLayout from '../layout/MainLayout.vue'
import Platforms from '../views/Platforms.vue'
import Models from '../views/Models.vue'
import Packages from '../views/Packages.vue'
import Ledger from '../views/Ledger.vue'
import ChatTest from '../views/ChatTest.vue'

const routes = [
  { path: '/login', component: Login },
  {
    path: '/',
    component: MainLayout,
    redirect: '/models',
    meta: { requiresAuth: true },
    children: [
      { path: 'platforms', component: Platforms, meta: { title: '平台管理' } },
      { path: 'models', component: Models, meta: { title: '模型管理' } },
      { path: 'packages', component: Packages, meta: { title: '额度包管理' } },
      { path: 'ledger', component: Ledger, meta: { title: '账本看板' } },
      { path: 'chat-test', component: ChatTest, meta: { title: '对话测试' } },
    ],
  },
]

const router = createRouter({ history: createWebHistory(), routes })

router.beforeEach((to) => {
  if (to.meta.requiresAuth && !localStorage.getItem('admin_token')) {
    return '/login'
  }
  if (to.path === '/login' && localStorage.getItem('admin_token')) {
    return '/'
  }
})

export default router
