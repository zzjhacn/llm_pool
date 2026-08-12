<template>
  <div>
    <div style="margin-bottom: 12px; display: flex; justify-content: space-between; align-items: center">
      <h3 style="margin: 0">模型管理</h3>
      <div>
        <el-select v-model="filterPlatform" clearable placeholder="按平台筛选" style="width: 160px; margin-right: 12px">
          <el-option v-for="p in platforms" :key="p.id" :label="p.id" :value="p.id" />
        </el-select>
        <el-button type="primary" @click="openCreate">新增模型</el-button>
      </div>
    </div>

    <el-alert type="info" :closable="false" show-icon style="margin-bottom: 12px">
      <template #title>额度来源有三种模式（新增/编辑时必选其一）</template>
      <div style="line-height: 1.7">
        <b>① 共享额度包</b>：多个模型共用一个额度包，包的余额耗尽会<b>自动停用其下全部模型</b>（适合集中采购、多模型分摊）。<br />
        <b>② 模型独立额度</b>：不建额度包，直接在模型上设置自己的总量，耗尽<b>仅停用自己</b>（适合各模型独立核算）。<br />
        <b>③ 无额度（兜底）</b>：不计额度、不扣减，永远可用，仅作最后兜底（如 escape 模型）。<br />
        <span style="color: #e6a23c">注意：共享包与独立额度<b>不能同时设置</b>；共享包的计费单位必须与模型计费方式一致。</span>
      </div>
    </el-alert>

    <el-table :data="displayRows" border>
      <el-table-column prop="id" label="ID" width="140" />
      <el-table-column prop="name" label="名称" width="120" sortable/>
      <el-table-column prop="platform_id" label="平台" width="110" />
      <el-table-column label="能力" prop="capabilities" min-width="150" sortable>
        <template #default="{ row }">
          <el-tag v-for="c in row.capabilities" :key="c" size="small" style="margin-right: 4px">{{ c }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="expired_at" label="到期日期" width="120" :formatter="dateFormatter" sortable/>
      <el-table-column prop="billing_type" label="计费" width="70" />
      <el-table-column label="额度来源" width="110">
        <template #default="{ row }">
          <el-tag v-if="row.quota_source === 'package'" type="primary">共享包</el-tag>
          <el-tag v-else-if="row.quota_source === 'self'" type="success">独立额度</el-tag>
          <el-tag v-else type="info">无额度</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="余额" prop="quota_balance" width="120" sortable>
        <template #default="{ row }">
          <span v-if="row.quota_source === 'none'" style="color: #909399">∞ 无限</span>
          <el-tag v-else :type="row.quota_balance > 0 ? 'success' : 'danger'">
            {{ row.quota_balance }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="140">
        <template #default="{ row }">
          <el-tag :type="row.enabled ? 'success' : 'info'">{{ row.enabled ? '启用' : '停用' }}</el-tag>
          <el-tag v-if="row.manual_disabled" type="warning" size="small">手动关</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="220">
        <template #default="{ row }">
          <el-button size="small" @click="openEdit(row)">编辑</el-button>
          <el-button size="small" :type="row.enabled ? 'warning' : 'success'" @click="toggle(row)">{{ row.enabled ? '停用' : '启用' }}</el-button>
          <el-button size="small" type="danger" @click="remove(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="visible" :title="editing ? '编辑模型' : '新增模型'" width="600px">
      <el-alert type="warning" :closable="false" style="margin-bottom: 12px">
        请先选择「额度来源」：共享包 / 独立额度 / 无额度，三者选一且互斥。
      </el-alert>
      <el-form :model="form" label-width="100px">
        <el-form-item label="ID（网关别名）">
          <el-input v-model="form.id" :disabled="editing" placeholder="客户端调用时传的 model 值，如 qwen-max / qwen-flash-latest" />
          <div style="color: #909399; font-size: 12px; line-height: 1.7; margin-top: 4px">
            <b>网关侧模型别名（路由键）</b>：客户端在 OpenAI 兼容接口里传的 <code>model</code> 字段值，也是 <code>GET /v1/models</code> 返回的标识、可 pin 锁定。
            它<b>不必等于厂商模型名</b>——可起一个好记的别名（如 <code>qwen-flash-latest</code>），再在下方「厂商模型」映射到真实串 <code>qwen3.7-flash-2026-07-15</code>。一经创建不可修改。
          </div>
        </el-form-item>
        <el-form-item label="展示名"><el-input v-model="form.name" /></el-form-item>
        <el-form-item label="厂商模型">
          <el-input v-model="form.provider_model" placeholder="实际发给厂商/LiteLLM 的模型串，如 qwen3.7-flash-2026-07-15" />
          <div style="color: #909399; font-size: 12px; line-height: 1.7; margin-top: 4px">
            <b>网关 → 厂商的实际模型串</b>，与上方「ID」解耦。例如 ID 用别名 <code>qwen-flash-latest</code>，这里填厂商真实名 <code>qwen3.7-flash-2026-07-15</code>。
            provider 前缀由所属平台决定，无需在此填写。
          </div>
        </el-form-item>
        <el-form-item label="平台">
          <el-select v-model="form.platform_id"><el-option v-for="p in platforms" :key="p.id" :label="p.id" :value="p.id" /></el-select>
        </el-form-item>
        <el-form-item label="能力">
          <el-select v-model="form.capabilities" multiple filterable allow-create default-first-option placeholder="可多选，也可输入自定义能力" style="width: 100%">
            <el-option v-for="c in CAPABILITY_OPTIONS" :key="c" :label="c" :value="c" />
          </el-select>
        </el-form-item>

        <el-form-item label="额度来源">
          <el-radio-group v-model="form.quota_mode">
            <el-radio-button value="package">共享额度包</el-radio-button>
            <el-radio-button value="self">模型独立额度</el-radio-button>
            <el-radio-button value="none">无额度(兜底)</el-radio-button>
          </el-radio-group>
        </el-form-item>

        <template v-if="form.quota_mode === 'package'">
          <el-form-item label="额度包">
            <el-select v-model="form.package_id" clearable @change="onPackageChange">
              <el-option v-for="p in packages" :key="p.id" :label="`${p.id}（${p.unit}, 余 ${p.balance}）`" :value="p.id" />
            </el-select>
          </el-form-item>
          <el-alert type="info" :closable="false" size="small" style="margin: 0 0 12px 100px">
            计费方式将自动锁定为所选包的计费单位（{{ form.billing_type }}）。
          </el-alert>
        </template>

        <template v-else-if="form.quota_mode === 'self'">
          <el-form-item label="计费方式">
            <el-select v-model="form.billing_type"><el-option label="按Token" value="token" /><el-option label="按次" value="call" /></el-select>
          </el-form-item>
          <el-form-item label="独立额度总量">
            <el-input-number v-model="form.quota_capacity" :min="0" :step="1000" />
            <span style="margin-left: 8px; color: #909399">（单位与上方计费方式一致：token 数 / 次）</span>
          </el-form-item>
          <el-alert type="info" :closable="false" size="small" style="margin: 0 0 12px 100px">
            该额度仅此模型使用，耗尽后自动停用本模型，不影响其他模型。
          </el-alert>
        </template>

        <template v-else>
          <el-alert type="warning" :closable="false" size="small" style="margin: 0 0 12px 100px">
            无额度模式：不扣减、不限量、永远可路由，仅建议用于兜底（escape）模型。
          </el-alert>
        </template>

        <template v-if="form.billing_type === 'call' && form.quota_mode !== 'package'">
          <el-form-item label="每次价格"><el-input-number v-model="form.price_per_call" :min="0" :step="0.01" /></el-form-item>
        </template>
        <template v-else-if="form.quota_mode !== 'package'">
          <el-form-item label="输入价/1k"><el-input-number v-model="form.price_input" :min="0" :step="0.001" /></el-form-item>
          <el-form-item label="输出价/1k"><el-input-number v-model="form.price_output" :min="0" :step="0.001" /></el-form-item>
        </template>

        <el-form-item label="质量档"><el-input-number v-model="form.quality_tier" :min="1" :max="5" /></el-form-item>
        <el-form-item label="延迟档"><el-input-number v-model="form.latency_tier" :min="1" :max="5" /></el-form-item>
        <el-form-item label="到期日"><el-date-picker v-model="form.expired_at" type="date" value-format="YYYY-MM-DD" placeholder="不填则不过期" /></el-form-item>
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
import { ref, computed, onMounted } from 'vue'
import { api } from '../api'
import { ElMessage, ElMessageBox } from 'element-plus'

const CAPABILITY_OPTIONS = [
  'chat', 'code', 'vision', 'function_calling', 'long_context', 'reasoning', 'embedding', 'tool_use',
  'json_schema', 'json_object',
]

const rows = ref([])
const platforms = ref([])
const packages = ref([])
const visible = ref(false)
const editing = ref(false)
const filterPlatform = ref('')
const form = ref(blank())

const displayRows = computed(() =>
  filterPlatform.value ? rows.value.filter((r) => r.platform_id === filterPlatform.value) : rows.value,
)

function dateFormatter(row,col,cellValue,idx) {
  return cellValue?.split('T')[0] || ''
}

function blank() {
  return {
    id: '', name: '', provider_model: '', platform_id: '', capabilities: [],
    billing_type: 'token', price_input: 0, price_output: 0, price_per_call: 0,
    quality_tier: 2, latency_tier: 3, package_id: null, quota_mode: 'package',
    quota_capacity: null, expired_at: '', enabled: true,
  }
}

function modeOf(row) {
  if (row.package_id) return 'package'
  if (row.quota_capacity != null) return 'self'
  return 'none'
}

async function load() {
  const [m, p, pk] = await Promise.all([api.listModels(), api.listPlatforms(), api.listPackages()])
  rows.value = m.data
  platforms.value = p.data
  packages.value = pk.data
}
function onPackageChange(pid) {
  const pkg = packages.value.find((x) => x.id === pid)
  if (pkg) form.value.billing_type = pkg.unit  // 共享包计费方式跟随包单位
}
function openCreate() {
  editing.value = false
  form.value = blank()
  visible.value = true
}
function openEdit(row) {
  editing.value = true
  form.value = { ...row, package_id: row.package_id || null, quota_mode: modeOf(row) }
  visible.value = true
}
async function submit() {
  const payload = { ...form.value, expired_at: form.value.expired_at || null }
  delete payload.quota_mode
  delete payload.provider        // provider 归平台所有，不在模型侧维护
  delete payload.effective_provider
  if (form.value.quota_mode === 'package') {
    payload.package_id = form.value.package_id || null
    payload.quota_capacity = null
    payload.quota_used = null
  } else if (form.value.quota_mode === 'self') {
    payload.package_id = null
    payload.quota_capacity = form.value.quota_capacity
    if (!editing.value) payload.quota_used = 0
  } else {
    payload.package_id = null
    payload.quota_capacity = null
    payload.quota_used = null
  }
  if (editing.value) await api.updateModel(form.value.id, payload)
  else await api.createModel(payload)
  visible.value = false
  ElMessage.success('已保存')
  load()
}
async function toggle(row) {
  await api.toggleModel(row.id, !row.enabled)
  ElMessage.success('已更新')
  load()
}
async function remove(row) {
  await ElMessageBox.confirm(`确认删除模型 ${row.id}？`)
  await api.deleteModel(row.id)
  ElMessage.success('已删除')
  load()
}
onMounted(load)
</script>
