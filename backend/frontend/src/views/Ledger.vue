<template>
  <div>
    <div style="margin-bottom: 12px; display: flex; justify-content: space-between; align-items: center">
      <h3 style="margin: 0">账本看板</h3>
      <div>
        <el-button @click="sync">同步启停状态</el-button>
        <el-button type="primary" @click="load">刷新</el-button>
      </div>
    </div>

    <el-row :gutter="16" style="margin-bottom: 16px">
      <el-col :span="8"><el-card>累计成本 <b>¥{{ summary.total_cost.toFixed(4) }}</b></el-card></el-col>
      <el-col :span="8"><el-card>累计调用 <b>{{ summary.total_calls }}</b> 次</el-card></el-col>
      <el-col :span="8"><el-card>累计消耗资源 <b>{{ summary.total_units }}</b></el-card></el-col>
    </el-row>

    <el-card style="margin-bottom: 16px">
      <div ref="chart" style="height: 320px"></div>
    </el-card>

    <el-card>
      <div style="margin-bottom: 8px; font-weight: 600">最近调用</div>
      <el-table :data="summary.recent" border>
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column prop="model_id" label="模型" width="160" />
        <el-table-column prop="units" label="消耗资源" width="120" />
        <el-table-column prop="cost" label="成本" width="120">
          <template #default="{ row }">¥{{ Number(row.cost).toFixed(4) }}</template>
        </el-table-column>
        <el-table-column prop="created_at" label="时间" />
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted, reactive, nextTick } from 'vue'
import * as echarts from 'echarts'
import { api } from '../api'
import { ElMessage } from 'element-plus'

const summary = reactive({ total_cost: 0, total_calls: 0, total_units: 0, by_model: [], recent: [] })
const chart = ref(null)

async function load() {
  const { data } = await api.ledger()
  Object.assign(summary, data)
  await nextTick()
  renderChart()
}
async function sync() {
  await api.sync()
  ElMessage.success('已同步')
  load()
}
function renderChart() {
  if (!chart.value) return
  const inst = echarts.getInstanceByDom(chart.value) || echarts.init(chart.value)
  inst.setOption({
    tooltip: { trigger: 'axis' },
    legend: { data: ['成本', '调用次数'] },
    xAxis: { type: 'category', data: summary.by_model.map((b) => b.model_id) },
    yAxis: [{ type: 'value', name: '成本' }, { type: 'value', name: '次数' }],
    series: [
      { name: '成本', type: 'bar', data: summary.by_model.map((b) => Number(b.cost.toFixed(4))) },
      { name: '调用次数', type: 'line', yAxisIndex: 1, data: summary.by_model.map((b) => b.calls) },
    ],
  })
}
onMounted(load)
</script>
