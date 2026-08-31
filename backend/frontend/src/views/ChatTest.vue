<template>
  <div>
    <div style="margin-bottom: 12px; display: flex; justify-content: space-between; align-items: center">
      <h3 style="margin: 0">对话测试</h3>
      <div>
        <el-radio-group v-model="mode" size="small">
          <el-radio-button label="chat">对话</el-radio-button>
          <el-radio-button label="embedding">嵌入</el-radio-button>
        </el-radio-group>
      </div>
    </div>

    <el-alert type="info" :closable="false" show-icon style="margin-bottom: 12px">
      <template #title>使用说明（{{ mode === 'chat' ? '对话' : '嵌入' }}）</template>
      <div style="line-height: 1.7">
        · 通过网关的 OpenAI 兼容接口验证模型能力：对话走 <code>/v1/chat/completions</code>，嵌入走 <code>/v1/embeddings</code>。<br />
        · <b>网关 Key</b>：调业务接口所需的 key（默认 <code>gpk-default</code>，部署时由 <code>LLM_POOL_GATEWAY_KEYS</code> 决定），仅本机 localStorage 记忆、不落库。<br />
        · <b>模型</b>留空 = 由网关按策略自动选择（对话按能力/余额/成本；嵌入按 embedding 能力）；指定则锁定到该模型。<br />
        · 指定的模型若<b>不存在 / 已停用 / 已过期 / 额度耗尽</b>，网关按「未传」处理自动改选，并在结果区给出降级提示；仅<b>能力不满足</b>（强一致场景，如指定仅支持 json_object 的模型却要 json_schema）仍会直接报错。<br />
        · 接口返回中 <b>model</b> 字段即本次实际路由到的模型，可据此判断自动路由结果。
      </div>
    </el-alert>

    <el-row :gutter="16">
      <!-- 左：请求表单 -->
      <el-col :span="14">
        <el-form label-width="92px" label-position="right">
          <el-form-item label="网关 Key">
            <el-input v-model="gwKey" type="password" show-password placeholder="gpk-default" style="max-width: 360px" />
          </el-form-item>
          <el-form-item label="模型">
            <el-select v-model="modelId" clearable filterable placeholder="自动选择（留空）" style="width: 100%">
              <el-option
                v-for="m in models"
                :key="m.id"
                :label="`${m.id}（${m.platform_id}）${m.enabled ? '' : ' · 已停用'}`"
                :value="m.id"
              />
            </el-select>
            <div style="color: #909399; font-size: 12px; margin-top: 4px">来自模型管理列表；留空则由网关自动挑选。</div>
          </el-form-item>

          <!-- 对话模式专属 -->
          <template v-if="mode === 'chat'">
            <el-form-item label="温度">
              <el-slider v-model="temperature" :min="0" :max="2" :step="0.1" show-input style="width: 100%" />
            </el-form-item>
            <el-form-item label="最大 Token">
              <el-input-number v-model="maxTokens" :min="1" :max="32000" :step="256" controls-position="right" />
              <span style="margin-left: 8px; color: #909399">留空 = 不限制</span>
            </el-form-item>
            <el-form-item label="System Prompt">
              <el-input v-model="systemPrompt" type="textarea" :rows="5" placeholder="可选；留空则仅发送 User Prompt" />
            </el-form-item>
            <el-form-item label="User Prompt">
              <el-input v-model="userPrompt" type="textarea" :rows="6" placeholder="必填：本次对话的用户消息" />
            </el-form-item>
          </template>

          <!-- 嵌入模式专属 -->
          <template v-else>
            <el-form-item label="嵌入文本">
              <el-input v-model="embedText" type="textarea" :rows="8" placeholder="每行一条文本；支持批量嵌入（空行自动忽略）" />
              <div style="color: #909399; font-size: 12px; margin-top: 4px">每行视为一条独立输入，返回对应向量。</div>
            </el-form-item>
            <el-form-item label="编码格式">
              <el-select v-model="encodingFormat" clearable placeholder="默认 float" style="width: 200px">
                <el-option label="float（默认）" value="float" />
                <el-option label="base64" value="base64" />
              </el-select>
            </el-form-item>
          </template>

          <el-form-item>
            <el-button type="primary" :loading="loading" :disabled="loading" @click="send">
              {{ loading ? '请求中…' : '发送' }}
            </el-button>
            <el-button @click="reset">清空输入</el-button>
          </el-form-item>
        </el-form>
      </el-col>

      <!-- 右：结果 -->
      <el-col :span="10">
        <div v-if="meta" style="margin-bottom: 12px">
          <el-alert
            v-if="meta.pinDropped"
            type="warning"
            :closable="false"
            show-icon
            style="margin-bottom: 12px"
            :title="`指定的模型 ${meta.pinRequested} 在本网关暂不可用，已自动改选为 ${meta.model}`"
          />
          <el-descriptions :column="1" border size="small">
            <el-descriptions-item label="路由模型">{{ meta.model }}</el-descriptions-item>
            <el-descriptions-item label="耗时">{{ meta.elapsed }} ms</el-descriptions-item>
            <el-descriptions-item v-if="mode === 'embedding'" label="向量数 / 维度">
              {{ meta.count }} / {{ meta.dim }}
            </el-descriptions-item>
            <el-descriptions-item label="Token(提示/补全/合计)">
              {{ meta.prompt }} / {{ meta.completion }} / {{ meta.total }}
            </el-descriptions-item>
          </el-descriptions>
        </div>

        <el-alert v-if="error" type="error" :closable="false" show-icon style="margin-bottom: 12px" :title="error" />

        <el-card v-if="result || loading" shadow="never" style="height: 420px; overflow: auto">
          <template #header><span style="font-weight: 600">{{ mode === 'chat' ? '助手回复' : '嵌入结果' }}</span></template>
          <pre v-if="result" style="white-space: pre-wrap; word-break: break-word; margin: 0; font-family: inherit; line-height: 1.7">{{ result }}</pre>
          <span v-else-if="loading" style="color: #909399">等待响应…</span>
        </el-card>

        <el-empty v-if="!result && !error && !loading" description="发送后将在此显示结果" />
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, watch, onMounted } from 'vue'
import axios from 'axios'
import { api } from '../api'
import { ElMessage } from 'element-plus'

const GW_KEY_LS = 'llm_pool_gw_key'

const mode = ref('chat')
const gwKey = ref(localStorage.getItem(GW_KEY_LS) || 'gpk-default')
watch(gwKey, (v) => localStorage.setItem(GW_KEY_LS, v || 'gpk-default'))

const models = ref([])
const modelId = ref('')
const temperature = ref(0.7)
const maxTokens = ref(null)
const systemPrompt = ref('')
const userPrompt = ref('')
const embedText = ref('')
const encodingFormat = ref('')

const loading = ref(false)
const result = ref('')
const error = ref('')
const meta = ref(null)

// 独立实例：业务接口用网关 Key（api-key 头），不复用管理面 admin_token。
const chatHttp = axios.create({ baseURL: '' })

// 指定模型被网关降级时回写的响应头（axios 会把 header 名转成小写）
function pinInfo(resp) {
  const h = (resp && resp.headers) || {}
  const dropped = h['x-llm-pool-pin-dropped']
  if (!dropped) return {}
  return { pinDropped: dropped, pinRequested: h['x-llm-pool-pin-requested'] || '' }
}

onMounted(async () => {
  try {
    const r = await api.listModels()
    models.value = r.data || []
  } catch (e) {
    ElMessage.warning('加载模型列表失败（不影响测试，可手动留空自动路由）')
  }
})

function reset() {
  systemPrompt.value = ''
  userPrompt.value = ''
  embedText.value = ''
  result.value = ''
  error.value = ''
  meta.value = null
}

async function send() {
  if (!gwKey.value.trim()) {
    ElMessage.warning('请填写网关 Key')
    return
  }

  loading.value = true
  result.value = ''
  error.value = ''
  meta.value = null

  const t0 = performance.now()
  try {
    let resp
    if (mode.value === 'chat') {
      if (!userPrompt.value.trim()) {
        ElMessage.warning('请填写 User Prompt')
        loading.value = false
        return
      }
      const messages = []
      if (systemPrompt.value.trim()) messages.push({ role: 'system', content: systemPrompt.value })
      messages.push({ role: 'user', content: userPrompt.value })
      const body = { messages, temperature: temperature.value, stream: false }
      if (modelId.value) body.model = modelId.value
      if (maxTokens.value != null) body.max_tokens = maxTokens.value
      resp = await chatHttp.post('/v1/chat/completions', body, {
        headers: { 'api-key': gwKey.value.trim() },
      })
      const data = resp.data
      const choice = data.choices && data.choices[0]
      result.value = choice?.message?.content ?? JSON.stringify(data, null, 2)
      const u = data.usage || {}
      meta.value = {
        model: data.model,
        prompt: u.prompt_tokens ?? '—',
        completion: u.completion_tokens ?? '—',
        total: u.total_tokens ?? '—',
        elapsed: Math.round(performance.now() - t0),
        ...pinInfo(resp),
      }
    } else {
      const lines = embedText.value.split('\n').map((s) => s.trim()).filter(Boolean)
      if (!lines.length) {
        ElMessage.warning('请填写嵌入文本（每行一条）')
        loading.value = false
        return
      }
      const body = { input: lines }
      if (modelId.value) body.model = modelId.value
      if (encodingFormat.value) body.encoding_format = encodingFormat.value
      resp = await chatHttp.post('/v1/embeddings', body, {
        headers: { 'api-key': gwKey.value.trim() },
      })
      const data = resp.data
      const arr = data.data || []
      const dim = arr.length ? (arr[0].embedding || []).length : 0
      const preview = arr
        .slice(0, 2)
        .map((d, i) => `【第 ${i + 1} 条】\n${JSON.stringify(d.embedding)}`)
        .join('\n\n')
      result.value =
        `共 ${arr.length} 条向量，维度 ${dim}。\n` +
        `编码格式：${data.encoding_format || 'float'}\n\n` +
        `前 2 条预览：\n${preview}`
      const u = data.usage || {}
      meta.value = {
        model: data.model,
        count: arr.length,
        dim,
        prompt: u.prompt_tokens ?? '—',
        completion: 0,
        total: u.total_tokens ?? '—',
        elapsed: Math.round(performance.now() - t0),
        ...pinInfo(resp),
      }
    }
  } catch (e) {
    const status = e.response?.status
    const detail = e.response?.data?.detail ?? e.message
    error.value = `HTTP ${status || '网络错误'}：${detail}`
  } finally {
    loading.value = false
  }
}
</script>
