# Health Realtime WebRTC API & SDK 文档

> 基于 WebRTC 的实时语音交互 API，音频通过 WebRTC Media Track（UDP）传输，
> 信令和文本事件通过 DataChannel 传递。相比 WebSocket 方案延迟更低，
> 浏览器原生支持音频采集与播放，无需手动处理 PCM 编解码。
>
> 版本：v0.1 | 日期：2026-03-11

---

## 1. 架构概述

### 1.1 WebRTC vs WebSocket 路径对比

| 维度 | WebRTC（本文档） | WebSocket |
|---|---|---|
| 音频传输 | Media Track (UDP, Opus) | Base64 PCM over TCP |
| 信令/事件 | DataChannel (SCTP over UDP) | 同一 WebSocket 连接 |
| 延迟 | **最优**，UDP 无队头阻塞 | 弱网下 TCP 队头阻塞 +100~200ms |
| 浏览器音频 | 原生采集/播放，无需手动处理 | 需手动 PCM 编解码 + AudioContext 播放 |
| 适用场景 | 前端 Web/移动端、对延迟敏感 | 服务端对接、IoT、跨平台脚本 |
| 连接复杂度 | SDP 交换 + ICE | 单一 WebSocket 握手 |

### 1.2 连接架构

```
Client (Browser / Mobile)
    │
    │  1. POST /v1/realtime/sessions  (获取 ephemeral_key + ICE servers)
    │
    │  2. RTCPeerConnection
    │     ├── Audio Track (双向)  ← 语音输入输出
    │     └── DataChannel "events" ← 信令和文本事件
    │
    ▼
┌──────────────────────────────────┐
│         LiveKit SFU Server       │
│   Room 管理 / 媒体路由 / ICE     │
└──────────────┬───────────────────┘
               │
┌──────────────┴───────────────────┐
│         Agent Worker             │
│   VAD → STT → LLM → TTS         │
│   (音频通过 LiveKit Track 收发)   │
└──────────────────────────────────┘
```

### 1.3 核心优势

1. **音频零编码开销**：浏览器 WebRTC 栈自动处理采集、AEC（回声消除）、AGC（增益控制）、NS（噪声抑制）、Opus 编码
2. **UDP 抗弱网**：无 TCP 队头阻塞，丢包由 Opus FEC + NACK 自动恢复
3. **原生播放**：Agent 回复的音频通过 Remote Audio Track 直接在 `<audio>` 元素播放，无需手动解码

---

## 2. 连接流程

### 2.1 获取临时凭证

客户端通过 HTTP 请求获取临时凭证和 LiveKit 连接信息。

**请求**：

```
POST /v1/realtime/sessions
Authorization: Bearer sk-health-xxxxxxxxxxxx
Content-Type: application/json
```

```json
{
  "model": "health-assistant",
  "scene": "inquiry",
  "voice": "zhixiaobai"
}
```

**响应**：

```json
{
  "session_id": "sess_abc123",
  "token": "eyJhbGciOiJIUzI1NiIs...",
  "url": "wss://livekit.health.com",
  "ice_servers": [
    {
      "urls": ["stun:stun.health.com:3478"],
      "username": "",
      "credential": ""
    },
    {
      "urls": ["turn:turn.health.com:3478"],
      "username": "tmp_user_abc",
      "credential": "tmp_pass_xyz"
    }
  ],
  "expires_at": 1741700000
}
```

| 字段 | 说明 |
|---|---|
| `session_id` | 会话唯一标识，用于断线重连 |
| `token` | LiveKit Room Token（JWT，有效期 5 分钟，连接后自动续期） |
| `url` | LiveKit Server WebSocket URL（用于 WebRTC 信令） |
| `ice_servers` | STUN/TURN 服务器列表（NAT 穿透） |
| `expires_at` | 凭证过期时间戳 |

### 2.2 建立 WebRTC 连接

通过 LiveKit Client SDK 建立连接，SDK 内部完成 SDP 交换和 ICE 协商。

```
Client                           LiveKit Server              Agent Worker
  │                                   │                          │
  │── POST /v1/realtime/sessions ────►│                          │
  │◄── { token, url, ice_servers } ──│                          │
  │                                   │                          │
  │── room.connect(url, token) ──────►│                          │
  │   (SDP Offer/Answer + ICE)        │                          │
  │                                   │── Agent Dispatch ───────►│
  │◄── Audio Track (remote) ─────────│◄── TTS Audio Track ──────│
  │── Audio Track (local mic) ──────►│── Audio to Agent ────────►│
  │                                   │                          │
  │◄═══ DataChannel "events" ════════╪══════════════════════════╪
  │     (双向信令和文本事件)           │                          │
```

---

## 3. 事件协议（DataChannel）

WebRTC 连接建立后，音频通过 Media Track 自动流转，无需客户端手动发送音频帧。
文本信令通过 DataChannel 或 LiveKit Data API（`room.localParticipant.publishData`）传递。

### 3.1 事件总览（共 11 种）

#### Client → Server（3 种）

| 事件 | 说明 |
|---|---|
| `session.update` | 配置会话（指令、音色等） |
| `response.cancel` | 打断当前回复 |
| `input_image.send` | 发送图片（拍照识药等） |

#### Server → Client（8 种）

| 事件 | 核心 | 说明 |
|---|---|---|
| `session.created` | 核心 | 会话建立，Agent 就绪 |
| `session.updated` | 核心 | 配置确认 |
| `response.transcript.delta` | 核心 | Agent 回复文本流（实时字幕） |
| `input_audio_transcription.delta` | 核心 | 用户语音实时转写增量（interim） |
| `input_audio_transcription.completed` | 核心 | 用户语音最终转写结果 |
| `response.done` | 核心 | 回复完成 |
| `error` | 核心 | 错误 |
| `agent.state_changed` | 扩展 | Agent 状态（listening/thinking/speaking） |

> **与 WebSocket 版差异**：WebRTC 方案无需 `input_audio_buffer.append`（音频走 Media Track）、
> 无需 `input_audio_buffer.commit`（Server VAD 自动检测）、
> 无需 `response.audio.delta`（Agent 音频走 Remote Audio Track 自动播放）。
> 事件数从 12 种精简到 11 种。

---

## 4. Client 事件详情

### 4.1 session.update

连接建立后发送，配置会话参数。不发则使用默认值。

```json
{
  "type": "session.update",
  "session": {
    "instructions": "你是一个专业的健康管理助手",
    "scene": "inquiry",
    "voice": "zhixiaobai"
  }
}
```

| 字段 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `instructions` | string | 内置 prompt | 系统指令 |
| `scene` | string | `"inquiry"` | `inquiry`（问诊）/ `free_chat`（闲聊） |
| `voice` | string | `"zhixiaobai"` | TTS 音色 |

> 音频格式由 WebRTC 协商自动确定（Opus/48kHz），客户端无需手动配置。
> Server VAD 始终开启（Silero VAD，Agent 端控制），不可配置。

---

### 4.2 response.cancel

打断 Agent 当前正在生成的回复。发送后 Agent 立即停止 TTS 输出，Remote Audio Track 静音。

```json
{
  "type": "response.cancel"
}
```

---

### 4.3 input_image.send

发送图片进行视觉分析（拍照识药、皮肤检测等场景）。

```json
{
  "type": "input_image.send",
  "image": "data:image/jpeg;base64,/9j/4AAQ...",
  "prompt": "帮我看看这是什么药"
}
```

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `image` | string | 是 | Base64 编码的图片（支持 JPEG/PNG，建议 < 1MB） |
| `prompt` | string | 否 | 图片分析引导文本 |

---

## 5. Server 事件详情

### 5.1 session.created

WebRTC 连接成功、Agent 加入 Room 后返回的第一个事件。

```json
{
  "event_id": "evt_001",
  "type": "session.created",
  "session": {
    "id": "sess_abc123",
    "model": "health-assistant",
    "voice": "zhixiaobai"
  }
}
```

---

### 5.2 session.updated

确认 `session.update` 配置已生效。

```json
{
  "event_id": "evt_002",
  "type": "session.updated",
  "session": {
    "id": "sess_abc123",
    "instructions": "你是一个专业的健康管理助手",
    "scene": "inquiry",
    "voice": "zhixiaobai"
  }
}
```

---

### 5.3 response.transcript.delta

Agent 回复的文本流增量，用于展示实时字幕。音频通过 Remote Audio Track 自动播放，此事件仅传递文本。

```json
{
  "event_id": "evt_003",
  "type": "response.transcript.delta",
  "response_id": "resp_001",
  "delta": "您好，关于您描述的"
}
```

---

### 5.4 input_audio_transcription.delta

用户语音的实时转写增量（interim 结果）。用户说话过程中持续推送，用于展示"用户正在说..."的实时文字效果。

```json
{
  "event_id": "evt_004",
  "type": "input_audio_transcription.delta",
  "item_id": "item_001",
  "delta": "我最近总是感觉"
}
```

> 每次推送为当前识别到的完整中间文本（非增量 diff），客户端直接替换显示即可。
> 当 VAD 检测到用户说完后，会触发 `input_audio_transcription.completed` 发送最终结果。

---

### 5.5 input_audio_transcription.completed

用户语音的最终转写结果（Server VAD 检测到用户说完后触发）。

```json
{
  "event_id": "evt_005",
  "type": "input_audio_transcription.completed",
  "item_id": "item_001",
  "transcript": "我最近总是感觉头疼"
}
```

---

### 5.7 response.done

一次回复生成完毕。

```json
{
  "event_id": "evt_006",
  "type": "response.done",
  "response": {
    "id": "resp_001",
    "status": "completed",
    "transcript": "您好，关于您描述的头疼症状，我想了解几个问题...",
    "usage": {
      "input_tokens": 150,
      "output_tokens": 85
    }
  }
}
```

| status | 说明 |
|---|---|
| `completed` | 正常完成 |
| `cancelled` | 被 `response.cancel` 打断 |
| `failed` | 生成失败 |

---

### 5.8 error

```json
{
  "event_id": "evt_007",
  "type": "error",
  "error": {
    "code": "agent_unavailable",
    "message": "Agent 未在规定时间内加入房间"
  }
}
```

常见错误码：

| code | 说明 |
|---|---|
| `auth_failed` | 凭证无效或过期 |
| `agent_unavailable` | Agent 未就绪 |
| `rate_limit_exceeded` | 超出频率限制 |
| `session_expired` | 会话已过期 |
| `internal_error` | 服务内部错误 |

---

### 5.9 agent.state_changed（扩展事件）

Agent 状态变更，用于驱动 UI 动效（语音动画、状态指示器等）。

```json
{
  "event_id": "evt_008",
  "type": "agent.state_changed",
  "state": "thinking",
  "previous_state": "listening"
}
```

| state | 含义 | UI 建议 |
|---|---|---|
| `listening` | 正在收听用户说话 | 显示收音动画 |
| `thinking` | 正在思考/生成回复 | 显示加载动画 |
| `speaking` | 正在语音回复 | 显示声波动画 |

---

## 6. 交互时序

### 6.1 完整对话（一问一答）

```
Client                              Server (LiveKit + Agent)
  │                                      │
  │── POST /v1/realtime/sessions ───────►│
  │◄── { token, url } ─────────────────│
  │                                      │
  │── room.connect(url, token) ─────────►│  WebRTC 握手
  │◄── Audio Track (bidirectional) ─────│
  │◄── DataChannel "events" ────────────│
  │                                      │
  │◄─ [DC] session.created ────────────│
  │── [DC] session.update ─────────────►│
  │◄─ [DC] session.updated ────────────│
  │                                      │
  │  [Agent 开场白]                       │
  │◄─ [DC] agent.state_changed:speaking │
  │◄─ [AudioTrack] 🔊 TTS 音频 ────────│  自动播放
  │◄─ [DC] response.transcript.delta ──│  ×N (实时字幕)
  │◄─ [DC] response.done ─────────────│
  │◄─ [DC] agent.state_changed:listen. │
  │                                      │
  │  [用户说话]                           │
  │── [AudioTrack] 🎤 麦克风音频 ──────►│  自动采集
  │◄─ [DC] input_audio_transcription   │
  │        .delta ─────────────────────│  ×N (实时转写)
  │                                      │  ↓ VAD 检测到说完
  │◄─ [DC] input_audio_transcription   │
  │        .completed ─────────────────│
  │◄─ [DC] agent.state_changed:think.  │
  │                                      │
  │  [Agent 回复]                        │
  │◄─ [DC] agent.state_changed:speak.  │
  │◄─ [AudioTrack] 🔊 TTS 音频 ────────│  自动播放
  │◄─ [DC] response.transcript.delta ──│  ×N
  │◄─ [DC] response.done ─────────────│
  │◄─ [DC] agent.state_changed:listen. │
```

### 6.2 用户打断

```
Client                              Server
  │                                      │
  │◄─ [AudioTrack] 🔊 Agent 说话中 ────│
  │◄─ [DC] response.transcript.delta ──│
  │                                      │
  │  [用户开始说话，VAD 检测到]           │
  │── [AudioTrack] 🎤 用户音频 ────────►│  VAD 自动打断
  │◄─ [DC] response.done (cancelled) ──│
  │◄─ [DC] agent.state_changed:listen. │
  │                                      │
  │  [或客户端主动打断]                   │
  │── [DC] response.cancel ────────────►│
  │◄─ [DC] response.done (cancelled) ──│
```

### 6.3 拍照识药

```
Client                              Server
  │                                      │
  │── [DC] input_image.send ───────────►│  发送图片
  │◄─ [DC] agent.state_changed:think.  │
  │                                      │  ↓ VLM 分析
  │◄─ [DC] agent.state_changed:speak.  │
  │◄─ [AudioTrack] 🔊 分析结果语音 ────│
  │◄─ [DC] response.transcript.delta ──│  ×N
  │◄─ [DC] response.done ─────────────│
```

---

## 7. SDK 使用指南

### 7.1 依赖

SDK 以内部模块形式提供（`lib/realtime/`），依赖 `livekit-client`：

```bash
npm install livekit-client
```

### 7.2 快速开始（Vanilla TypeScript）

```typescript
import { LiveKitTransport } from '@/lib/realtime'

const transport = new LiveKitTransport()

// 1. 监听事件
transport.on('state_changed', (state) => {
  console.log('连接:', state) // disconnected | connecting | connected | reconnecting
})

transport.on('agent.state_changed', (state) => {
  console.log('Agent:', state) // idle | listening | thinking | speaking
})

transport.on('transcript', (message) => {
  console.log(`[${message.role}]`, message.text, message.isFinal ? '(final)' : '(interim)')
})

transport.on('error', (err) => {
  console.error('[Error]', err.code, err.message)
})

// 2. 连接（tokenProvider 由应用层实现，SDK 不关心鉴权细节）
await transport.connect({
  tokenProvider: async (agentName) => {
    const res = await fetch(`/api/livekit/token?agentName=${agentName}`, { method: 'POST' })
    return res.json() // { token, room, ws_url }
  },
  model: 'health-assistant',
  initialMode: 'voice',
})

// 3. 麦克风控制
await transport.setMicrophoneEnabled(true)   // 开麦
await transport.setMicrophoneEnabled(false)  // 静音

// 4. 摄像头控制
await transport.setCameraEnabled(true, 'user')  // 前置摄像头
await transport.switchCamera()                   // 切换前后摄像头

// 5. 断开
transport.disconnect()
```

### 7.3 React Hook 用法

```tsx
import { useRealtimeSession, type TokenProvider } from '@/lib/realtime'
import { authPost } from '@/lib/auth-fetch'

const tokenProvider: TokenProvider = async (agentName, tokenMode) => {
  const params = new URLSearchParams()
  if (agentName) params.set('agentName', agentName)
  if (tokenMode) params.set('tokenMode', tokenMode)
  const query = params.toString()
  const url = query ? `/api/livekit/token?${query}` : '/api/livekit/token'
  const res = await authPost(url)
  if (!res.ok) throw new Error('获取 Token 失败')
  return res.json()
}

function VoiceChat() {
  const {
    state,           // 'disconnected' | 'connecting' | 'connected' | 'reconnecting'
    agentState,      // 'idle' | 'listening' | 'thinking' | 'speaking'
    transcripts,     // TranscriptMessage[]
    error,
    isMuted,
    isCameraOn,
    facingMode,
    localVideoRef,
    connect,
    disconnect,
    toggleMute,
    toggleCamera,
    switchCamera,
  } = useRealtimeSession({
    tokenProvider,
    initialMode: 'voice',
  })

  return (
    <div>
      <div className="status">
        连接：{state} | Agent：{agentState}
      </div>

      <div className="transcripts">
        {transcripts
          .filter(t => t.isFinal || t.role === 'assistant')
          .map((msg) => (
            <div key={msg.id} className={msg.role}>
              {msg.text}
            </div>
          ))}
      </div>

      <div className="controls">
        {state === 'disconnected' ? (
          <button onClick={() => connect('health-assistant')}>开始对话</button>
        ) : (
          <>
            <button onClick={toggleMute}>{isMuted ? '取消静音' : '静音'}</button>
            <button onClick={toggleCamera}>{isCameraOn ? '关闭摄像头' : '打开摄像头'}</button>
            <button onClick={() => disconnect()}>结束</button>
          </>
        )}
      </div>
    </div>
  )
}
```

### 7.4 SDK API 参考

#### LiveKitTransport（Transport 层）

底层传输类，不依赖 React，可在任何 JS 环境使用。

```typescript
class LiveKitTransport extends TypedEventEmitter<TransportEvents> {
  /** 当前连接状态 */
  readonly state: TransportState

  /** 当前 Agent 状态 */
  readonly agentState: AgentState

  /** 麦克风静音状态 */
  readonly isMuted: boolean

  /** 摄像头开关状态 */
  readonly isCameraOn: boolean

  /** 摄像头朝向 */
  readonly facingMode: FacingMode

  /** 建立 WebRTC 连接 */
  connect(config: RealtimeSessionConfig): Promise<void>

  /** 断开连接 */
  disconnect(): void

  /** 麦克风开关 */
  setMicrophoneEnabled(enabled: boolean): Promise<void>

  /** 摄像头开关 */
  setCameraEnabled(enabled: boolean, facingMode?: FacingMode): Promise<void>

  /** 切换前后摄像头 */
  switchCamera(): Promise<void>

  /** 获取本地视频轨道（用于 attach 到 <video> 元素） */
  getLocalVideoTrack(): MediaStreamTrack | null

  /** 事件监听 */
  on<E extends keyof TransportEvents>(event: E, handler: TransportEvents[E]): this
  off<E extends keyof TransportEvents>(event: E, handler: TransportEvents[E]): this
}
```

#### useRealtimeSession（React Hook 层）

封装 `LiveKitTransport`，将事件映射为 React 状态。

```typescript
function useRealtimeSession(options: UseRealtimeSessionOptions): UseRealtimeSessionReturn

interface UseRealtimeSessionOptions extends RealtimeSessionConfig {
  onError?: (error: string) => void
  onTranscript?: (message: TranscriptMessage) => void
  onAgentStateChange?: (state: AgentState) => void
}

interface UseRealtimeSessionReturn {
  state: TransportState            // 'disconnected' | 'connecting' | 'connected' | 'reconnecting'
  agentState: AgentState           // 'idle' | 'listening' | 'thinking' | 'speaking'
  error: string | null
  transcripts: TranscriptMessage[] // 用户 STT 和 Agent 回复统一列表

  isMuted: boolean
  isCameraOn: boolean
  facingMode: FacingMode           // 'user' | 'environment'
  localVideoRef: RefObject<HTMLVideoElement | null>

  connect: (agentName?: string, tokenMode?: string) => Promise<boolean>
  disconnect: () => void
  toggleMute: () => Promise<void>
  toggleCamera: () => Promise<void>
  switchCamera: () => Promise<void>
}
```

#### TokenProvider

SDK 不关心鉴权细节（localStorage / cookie / API Key），只要求应用层提供一个返回 LiveKit 连接三元组的函数。

```typescript
interface TokenResponse {
  token: string    // LiveKit Room Token (JWT)
  room: string     // Room 名称
  ws_url: string   // LiveKit Server WebSocket URL
}

type TokenProvider = (
  agentName?: string,
  tokenMode?: string,
) => Promise<TokenResponse>
```

#### RealtimeSessionConfig

```typescript
interface RealtimeSessionConfig {
  /** Token 提供者（必须由应用层提供） */
  tokenProvider: TokenProvider

  /** Agent 名称，传递给 tokenProvider */
  model?: string

  /** Token 环境模式，传递给 tokenProvider */
  tokenMode?: string

  /** 初始通话模式 */
  initialMode?: 'voice' | 'video'

  /** NoiseGate 配置，传 false 禁用 */
  noiseGate?: NoiseGateOptions | false

  /** 音频采集配置 */
  audio?: {
    autoGainControl?: boolean    // 默认 false（防止远处人声被自动放大）
    echoCancellation?: boolean   // 默认 true
    noiseSuppression?: boolean   // 默认 true
  }

  /** 视频采集配置 */
  video?: {
    resolution?: { width: number; height: number; frameRate: number }
    facingMode?: 'user' | 'environment'
  }
}
```

#### Transport 事件

```typescript
interface TransportEvents {
  /** 连接状态变更 */
  'state_changed': (state: TransportState, previous: TransportState) => void

  /** Agent 状态变更 */
  'agent.state_changed': (state: AgentState, previous: AgentState) => void

  /** 转录消息（用户 STT 和 Agent 回复统一推送） */
  'transcript': (message: TranscriptMessage) => void

  /** 麦克风静音状态变更 */
  'mute_changed': (muted: boolean) => void

  /** 摄像头状态变更 */
  'camera_changed': (enabled: boolean, facingMode: FacingMode) => void

  /** 错误 */
  'error': (error: { code: string; message: string }) => void
}
```

#### 数据结构

```typescript
type TransportState = 'disconnected' | 'connecting' | 'connected' | 'reconnecting'
type AgentState = 'idle' | 'listening' | 'thinking' | 'speaking'
type FacingMode = 'user' | 'environment'

interface TranscriptMessage {
  id: string
  role: 'user' | 'assistant'
  text: string
  isFinal: boolean
  timestamp: Date
}
```

---

## 8. 音频处理

### 8.1 WebRTC 音频流水线

WebRTC 方案下，浏览器和 LiveKit SDK 自动处理整条音频流水线：

```
上行 (用户 → Agent):
  麦克风采集 (48kHz)
  → 浏览器 AEC/AGC/NS (自动)
  → Opus 编码 (自动)
  → WebRTC ICE/DTLS 传输 (UDP)
  → LiveKit SFU 转发
  → Agent Worker 接收
  → VAD (Silero) → STT → LLM → TTS

下行 (Agent → 用户):
  Agent TTS 输出
  → LiveKit Opus 编码 (自动)
  → WebRTC 传输 (UDP)
  → 浏览器 Opus 解码 (自动)
  → <audio> 元素 / AudioContext 播放 (自动)
```

客户端无需处理任何音频编解码、重采样、Base64 转换。

### 8.2 音频质量增强（可选）

SDK 内置自适应 NoiseGate（软噪声门），在浏览器 AEC/NS 之上对近端音频进一步降噪，过滤远处低音量人声：

```typescript
useRealtimeSession({
  tokenProvider,
  audio: {
    echoCancellation: true,    // 回声消除（默认开启）
    noiseSuppression: true,    // 噪声抑制（默认开启）
    autoGainControl: false,    // 自动增益（默认关闭，防止远处人声被放大）
  },
  noiseGate: {                 // 默认开启，传 false 禁用
    multiplier: 3.0,           // 语音需比噪声底大 ~10dB
    attackTime: 0.02,
    releaseTime: 0.2,
  },
})
```

NoiseGate 会根据 Agent 状态自动调整灵敏度：
- `listening`：宽松（multiplier=2.0），正常收音
- `thinking`：适中（multiplier=3.0），抑制背景噪声
- `speaking`：严格（multiplier=5.0），只通过近距离打断语音

---

## 9. 安全与鉴权

### 9.1 鉴权流程

```
Client                     API Server                  LiveKit
  │                            │                          │
  │── POST /v1/realtime/       │                          │
  │   sessions                 │                          │
  │   Authorization: Bearer    │                          │
  │   sk-health-xxx ──────────►│                          │
  │                            │── 验证 API Key           │
  │                            │── 创建 Room ────────────►│
  │                            │── 签发 Room Token        │
  │◄── { token, url } ────────│                          │
  │                            │                          │
  │── room.connect(url, token)─┼─────────────────────────►│
  │   (token 由 LiveKit 验证)  │                          │
```

### 9.2 安全建议

| 场景 | 方案 |
|---|---|
| 前端直接调用 | 通过自有后端代理 `/v1/realtime/sessions`，不暴露 API Key |
| 服务端调用 | 直接使用 API Key |
| Token 过期 | SDK 自动处理 LiveKit Token 续期 |
| TURN 凭证 | 临时凭证，5 分钟有效，按需刷新 |

**前端安全接入模式**（推荐）：

```typescript
import { authPost } from '@/lib/auth-fetch'
import type { TokenProvider } from '@/lib/realtime'

const tokenProvider: TokenProvider = async (agentName, tokenMode) => {
  const params = new URLSearchParams()
  if (agentName) params.set('agentName', agentName)
  if (tokenMode) params.set('tokenMode', tokenMode)
  const query = params.toString()
  const url = query ? `/api/livekit/token?${query}` : '/api/livekit/token'
  const res = await authPost(url)  // 自动附带用户 JWT
  if (!res.ok) throw new Error('获取 Token 失败')
  return res.json() // { token, room, ws_url }
}
```

---

## 10. 断线重连

SDK 内置自动重连机制，对上层应用透明。

```
Client                              Server
  │                                      │
  │══ WebRTC 连接中 ═══════════════════│
  │                                      │
  │  ✕ 网络断开                          │
  │◄─ state_changed: reconnecting ─────│
  │                                      │
  │  ... 网络恢复 ...                    │
  │── 自动重连 (带 session_id) ────────►│
  │   (ICE Restart / 重新连接)           │
  │◄─ state_changed: connected ────────│
  │                                      │
  │  对话上下文保持，继续交互              │
```

| 参数 | 默认值 | 说明 |
|---|---|---|
| 重连超时 | 30s | 超时后触发 `state_changed: disconnected` |
| 重连间隔 | 指数退避 1s → 8s | 自动递增 |
| Room 保活 | 30s | Server 端 Room 保活时长 |

---

## 11. 与 WebSocket 极简版事件对照

| WebSocket 事件 | WebRTC 对应 | 变化说明 |
|---|---|---|
| `input_audio_buffer.append` | **不需要** | 音频走 Media Track |
| `input_audio_buffer.commit` | **不需要** | Server VAD 自动提交 |
| `response.audio.delta` | **不需要** | 音频走 Remote Audio Track |
| `session.update` | `session.update` | 相同，去掉 audio format 字段 |
| `response.cancel` | `response.cancel` | 相同 |
| `session.created` | `session.created` | 相同 |
| `session.updated` | `session.updated` | 相同 |
| `response.audio_transcript.delta` | `response.transcript.delta` | 简化命名 |
| — | `input_audio_transcription.delta`（新增） | 用户实时转写增量，WS 极简版无此事件 |
| `conversation.item.input_audio_transcription.completed` | `input_audio_transcription.completed` | 简化命名 |
| `response.done` | `response.done` | 相同 |
| `error` | `error` | 相同 |
| `agent.state_changed` | `agent.state_changed` | 相同 |
| — | `input_image.send`（新增） | 拍照识药等视觉场景 |

**总结**：WebRTC 方案 10 种事件（3 Client + 7 Server） vs WebSocket 方案 12 种事件。
音频相关的 3 种事件（append/commit/audio.delta）被 WebRTC Media Track 替代。

---

## 12. 完整示例

### 12.1 浏览器端（React + useRealtimeSession）

> 对应实际代码：`frontend/app/chat/call/page.tsx`

```tsx
import { useRealtimeSession, type TokenProvider, type TokenResponse } from '@/lib/realtime'
import { authPost } from '@/lib/auth-fetch'

const tokenProvider: TokenProvider = async (agentName, tokenMode) => {
  const params = new URLSearchParams()
  if (agentName) params.set('agentName', agentName)
  if (tokenMode) params.set('tokenMode', tokenMode)
  const query = params.toString()
  const url = query ? `/api/livekit/token?${query}` : '/api/livekit/token'
  const res = await authPost(url)
  if (!res.ok) throw new Error('获取 Token 失败')
  return res.json() as Promise<TokenResponse>
}

function CallPage() {
  const {
    state: status,
    agentState,
    error,
    transcripts,
    isMuted,
    isCameraOn,
    facingMode,
    localVideoRef,
    connect,
    disconnect,
    toggleMute,
    toggleCamera,
    switchCamera,
  } = useRealtimeSession({
    tokenProvider,
    initialMode: 'voice',
    onError: (err) => console.error('Realtime call error:', err),
  })

  const isConnecting = status === 'connecting' || status === 'reconnecting'

  return (
    <div>
      {/* 状态显示 */}
      <div>连接：{status} | Agent：{agentState}</div>
      {error && <div className="error">{error}</div>}

      {/* 转录消息列表 */}
      <div className="transcripts">
        {transcripts
          .filter(t => t.isFinal || t.role === 'assistant')
          .map(msg => (
            <div key={msg.id} className={msg.role}>{msg.text}</div>
          ))}
      </div>

      {/* 视频预览（摄像头开启时） */}
      {isCameraOn && (
        <video
          ref={localVideoRef}
          autoPlay
          playsInline
          muted
          style={{ transform: facingMode === 'user' ? 'scaleX(-1)' : 'none' }}
        />
      )}

      {/* 控制按钮 */}
      {status === 'disconnected' ? (
        <button onClick={() => connect('health-assistant')} disabled={isConnecting}>
          开始对话
        </button>
      ) : (
        <div>
          <button onClick={toggleMute}>{isMuted ? '取消静音' : '静音'}</button>
          <button onClick={toggleCamera}>{isCameraOn ? '关闭摄像头' : '打开摄像头'}</button>
          {isCameraOn && <button onClick={switchCamera}>切换摄像头</button>}
          <button onClick={disconnect}>结束对话</button>
        </div>
      )}
    </div>
  )
}
```

### 12.2 服务端 Token 签发（Python / FastAPI）

```python
from fastapi import FastAPI, Depends, HTTPException
from livekit.api import AccessToken, VideoGrants
from pydantic import BaseModel
import time, secrets

app = FastAPI()

LIVEKIT_URL = "wss://livekit.health.com"
LIVEKIT_API_KEY = "your-livekit-api-key"
LIVEKIT_API_SECRET = "your-livekit-api-secret"

class SessionRequest(BaseModel):
    model: str = "health-assistant"
    scene: str = "inquiry"
    voice: str = "zhixiaobai"

class SessionResponse(BaseModel):
    session_id: str
    token: str
    url: str

@app.post("/v1/realtime/sessions", response_model=SessionResponse)
async def create_session(req: SessionRequest, api_key: str = Depends(verify_api_key)):
    session_id = f"sess_{secrets.token_hex(12)}"
    room_name = f"health-rtc-{session_id}"

    token = (
        AccessToken(LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
        .with_identity(f"user-{session_id}")
        .with_grants(VideoGrants(
            room_join=True,
            room=room_name,
            can_publish=True,
            can_subscribe=True,
        ))
        .with_metadata(json.dumps({
            "scene": req.scene,
            "voice": req.voice,
        }))
        .to_jwt()
    )

    return SessionResponse(
        session_id=session_id,
        token=token,
        url=LIVEKIT_URL,
    )
```

---

## 13. 后续扩展（按需添加）

| 优先级 | 能力 | 说明 |
|---|---|---|
| P1 | `input_audio_transcription.delta` | 用户语音实时转写增量（interim 结果） |
| P1 | 视频流分析 | 通过 Camera Track 实时推送视频帧给 VLM |
| P2 | `response.function_call` | Function Calling 结果透传（当前服务端执行） |
| P2 | 多语言切换 | 运行时切换 STT/TTS 语言 |
| P3 | 屏幕共享分析 | Screen Share Track + VLM |
| P3 | 多人会话 | 多个用户加入同一 Room |

---

## 附录 A：与 OpenAI Realtime WebRTC API 对比

> 参考：[OpenAI Realtime API with WebRTC](https://developers.openai.com/api/docs/guides/realtime-webrtc)

### A.1 总体架构差异

```
OpenAI WebRTC:
  Client ──── RTCPeerConnection (raw) ────► OpenAI Realtime Server (端到端模型)
              DataChannel "oai-events"

Health WebRTC:
  Client ──── LiveKit Client SDK ────► LiveKit SFU ────► Agent Worker (Pipeline: VAD→STT→LLM→TTS)
              LiveKit Data API
```

| 维度 | OpenAI Realtime WebRTC | Health Realtime WebRTC |
|---|---|---|
| **模型架构** | 端到端 Speech-to-Speech（`gpt-realtime`） | Pipeline（VAD→STT→LLM→TTS）或 Omni 模型 |
| **WebRTC 层** | 原生 `RTCPeerConnection` API | LiveKit Client SDK（封装 WebRTC） |
| **媒体架构** | P2P-like（Client ↔ OpenAI Server） | SFU（Client ↔ LiveKit SFU ↔ Agent） |
| **DataChannel** | 手动创建 `"oai-events"` | LiveKit Data API（`publishData`）封装 |
| **SDK 抽象层级** | 低层（raw WebRTC）或 Agents SDK（高层） | `@health/realtime-sdk`（中高层，含 React Hooks） |

### A.2 连接流程对比

#### OpenAI：两种连接模式

**模式 A — Unified Interface（推荐）**：

```
Client                      App Server                 OpenAI
  │                             │                         │
  │── createOffer() ───────────►│                         │
  │   (SDP offer)               │── POST /v1/realtime/    │
  │                             │   calls (multipart:     │
  │                             │   sdp + session config)─►│
  │                             │◄── SDP answer ─────────│
  │◄── setRemoteDescription ───│                         │
  │                             │                         │
  │═══ WebRTC 连接建立 ════════╪═════════════════════════╪
```

**模式 B — Ephemeral Token**：

```
Client                      App Server                 OpenAI
  │── GET /token ──────────────►│                         │
  │                             │── POST /v1/realtime/    │
  │                             │   client_secrets ──────►│
  │                             │◄── ephemeral_key ──────│
  │◄── { key } ────────────────│                         │
  │                                                       │
  │── POST /v1/realtime/calls (SDP + ephemeral_key) ─────►│
  │◄── SDP answer ───────────────────────────────────────│
  │                                                       │
  │═══ WebRTC 连接建立 ══════════════════════════════════╪
```

#### Health：LiveKit Token 模式

```
Client                      App Server                 LiveKit SFU
  │── POST /v1/realtime/ ─────►│                         │
  │   sessions                  │── 创建 Room + Token ───►│
  │◄── { token, url } ────────│                         │
  │                                                       │
  │── room.connect(url, token) ──────────────────────────►│
  │   (LiveKit SDK 内部完成 SDP 交换 + ICE)               │
  │◄── Audio Track + DataChannel ────────────────────────│
```

| 对比点 | OpenAI | Health |
|---|---|---|
| SDP 交换 | 开发者手动 `createOffer` → POST → `setRemoteDescription` | LiveKit SDK 内部自动完成 |
| 鉴权方式 | Ephemeral Key 或 Unified SDP+Config | LiveKit Room Token (JWT) |
| ICE/TURN | OpenAI 托管（内置） | 自建 STUN/TURN，Token 接口返回 `ice_servers` |
| 连接步骤数 | 2-3 步（手动 WebRTC 操作） | 1 步（`room.connect()` 一行代码） |
| 开发者感知 WebRTC | **是**，需理解 SDP/ICE | **否**，SDK 完全封装 |

### A.3 事件协议对比

#### OpenAI WebRTC DataChannel 事件（主要）

OpenAI 在 WebRTC 模式下通过 DataChannel `"oai-events"` 传递所有非音频事件，事件集与 WebSocket 模式完全相同（28+ 种）：

| Client → Server | Server → Client |
|---|---|
| `session.update` | `session.created` / `session.updated` |
| `input_audio_buffer.append` (可选，非 mic 音频) | `input_audio_buffer.speech_started` / `speech_stopped` / `committed` |
| `input_audio_buffer.commit` / `clear` | `conversation.item.created` / `added` / `done` |
| `conversation.item.create` / `delete` / `truncate` | `response.created` / `done` |
| `response.create` / `cancel` | `response.output_audio.delta` / `done` |
| | `response.output_audio_transcript.delta` / `done` |
| | `response.output_text.delta` / `done` |
| | `response.function_call_arguments.delta` / `done` |
| | `error` |

#### Health WebRTC DataChannel 事件

| Client → Server (3 种) | Server → Client (7 种) |
|---|---|
| `session.update` | `session.created` / `session.updated` |
| `response.cancel` | `response.transcript.delta` |
| `input_image.send` | `input_audio_transcription.completed` |
| | `response.done` |
| | `error` |
| | `agent.state_changed` |

#### 逐事件详细对照表

> 以下列出 OpenAI Realtime API GA 的全部事件，逐一标注 Health WebRTC 的对应方案和设计决策。

**Client → Server 事件**

| # | OpenAI 事件 | Health 对应 | 状态 | 设计决策 |
|---|---|---|---|---|
| 1 | `session.update` | `session.update` | **保留（简化）** | 去掉 `audio.input/output.format`（WebRTC 自动协商）、`turn_detection`（固定 Silero）、`tools`（服务端定义）；新增 `scene` 字段 |
| 2 | `input_audio_buffer.append` | — | **移除** | WebRTC Audio Track 自动传输麦克风音频，无需手动推送 |
| 3 | `input_audio_buffer.commit` | — | **移除** | Server VAD 始终开启，自动检测语音结束并提交 |
| 4 | `input_audio_buffer.clear` | — | **移除** | VAD 自动管理缓冲区，客户端无需干预 |
| 5 | `conversation.item.create` | `input_image.send`（仅图片） | **简化** | OpenAI 支持 text/audio/image 多类型注入；Health 仅保留图片场景并用专用事件，文本通过语音交互，音频走 Track |
| 6 | `conversation.item.delete` | — | **移除** | 对话历史由 Agent 端管理，客户端不操作 |
| 7 | `conversation.item.truncate` | — | **移除** | 同上 |
| 8 | `response.create` | — | **移除** | Server VAD 自动触发回复；禁用 VAD 的 Push-to-talk 场景暂不支持 |
| 9 | `response.cancel` | `response.cancel` | **保留** | 打断语义相同 |

**Server → Client 事件**

| # | OpenAI 事件 | Health 对应 | 状态 | 设计决策 |
|---|---|---|---|---|
| 1 | `session.created` | `session.created` | **保留** | 语义相同 |
| 2 | `session.updated` | `session.updated` | **保留** | 语义相同 |
| 3 | `conversation.created` | — | **移除** | 连接即创建对话，无需单独事件 |
| 4 | `conversation.item.added` | — | **移除** | 对话项管理为服务端内部逻辑 |
| 5 | `conversation.item.created` | — | **移除** | 同上 |
| 6 | `conversation.item.done` | — | **移除** | 同上 |
| 7 | `conversation.item.deleted` | — | **移除** | 客户端无删除操作，无需确认 |
| 8 | `conversation.item.truncated` | — | **移除** | 客户端无截断操作，无需确认 |
| 9 | `conversation.item.input_audio_transcription.delta` | — | **暂不支持** | P1 扩展：`input_audio_transcription.delta`（实时转写中间结果） |
| 10 | `conversation.item.input_audio_transcription.completed` | `input_audio_transcription.completed` | **保留（简化命名）** | 去掉 `conversation.item.` 前缀，更简洁 |
| 11 | `input_audio_buffer.speech_started` | — | **移除** | VAD 状态由 Agent 端管理；客户端通过 `agent.state_changed` 感知 |
| 12 | `input_audio_buffer.speech_stopped` | — | **移除** | 同上 |
| 13 | `input_audio_buffer.committed` | — | **移除** | VAD 自动提交，客户端无需确认 |
| 14 | `input_audio_buffer.cleared` | — | **移除** | 无 clear 操作，无需确认 |
| 15 | `response.created` | — | **移除** | 用 `agent.state_changed: thinking` 替代 |
| 16 | `response.output_item.added` | — | **移除** | 细粒度生命周期事件，极简版不需要 |
| 17 | `response.output_item.done` | — | **移除** | 同上 |
| 18 | `response.content_part.added` | — | **移除** | 同上 |
| 19 | `response.content_part.done` | — | **移除** | 同上 |
| 20 | `response.output_audio.delta` | — | **移除** | 音频通过 WebRTC Remote Audio Track 直接播放 |
| 21 | `response.output_audio.done` | — | **移除** | `response.done` 已标志回复结束 |
| 22 | `response.output_audio_transcript.delta` | `response.transcript.delta` | **保留（简化命名）** | 去掉 `output_audio_` 前缀 |
| 23 | `response.output_audio_transcript.done` | — | **移除** | `response.done.transcript` 中包含完整文本 |
| 24 | `response.output_text.delta` | — | **合并** | 纯文本回复合并到 `response.transcript.delta` |
| 25 | `response.output_text.done` | — | **移除** | `response.done.transcript` 中包含完整文本 |
| 26 | `response.function_call_arguments.delta` | — | **移除** | Function Calling 服务端执行，不透传客户端 |
| 27 | `response.function_call_arguments.done` | — | **移除** | 同上 |
| 28 | `response.done` | `response.done` | **保留** | 语义相同，payload 包含完整 transcript 和 usage |
| 29 | `rate_limits.updated` | — | **移除** | 限流由服务端管控，客户端通过 error 事件感知 |
| 30 | `error` | `error` | **保留** | 语义相同 |
| — | — | `agent.state_changed` | **新增** | Health 特有；OpenAI 无内置 Agent 状态事件 |

#### 事件分类汇总

| 分类 | OpenAI 事件数 | Health 事件数 | 说明 |
|---|---|---|---|
| Session 管理 | 3 (created + updated + conversation.created) | 2 (created + updated) | Health 合并 conversation.created |
| 音频 Buffer | 6 (append + commit + clear + speech_started/stopped + committed) | **0** | WebRTC Media Track 完全替代 |
| 对话项管理 | 8 (item.create/delete/truncate + added/created/done/deleted/truncated) | **0** | Agent 端内部管理 |
| 用户转写 | 2 (transcription.delta + completed) | 1 (completed) | delta 为 P1 扩展 |
| 回复生命周期 | 5 (response.created + output_item.added/done + content_part.added/done) | **0** | 用 `agent.state_changed` 替代 |
| 回复音频 | 2 (output_audio.delta + done) | **0** | WebRTC Audio Track 替代 |
| 回复文本/转写 | 4 (output_audio_transcript.delta/done + output_text.delta/done) | 1 (transcript.delta) | 合并为统一文本流 |
| Function Call | 2 (arguments.delta + done) | **0** | 服务端执行 |
| 打断控制 | 2 (response.create + cancel) | 1 (cancel) | VAD 自动触发，无需 create |
| 图片/视觉 | 0（复用 conversation.item.create） | 1 (input_image.send) | Health 专用事件 |
| 限流/错误 | 2 (rate_limits.updated + error) | 1 (error) | — |
| Agent 状态 | **0** | 1 (agent.state_changed) | **Health 独有** |
| **总计** | **~36** | **10** | Health 精简 72% |

### A.4 Session 配置对比

```json
// OpenAI session.update
{
  "type": "session.update",
  "session": {
    "model": "gpt-realtime",
    "instructions": "You are a helpful assistant",
    "audio": {
      "input": { "format": { "type": "audio/pcm", "rate": 24000 } },
      "output": { "format": { "type": "audio/pcm", "rate": 24000 }, "voice": "marin" }
    },
    "turn_detection": {
      "type": "semantic_vad",
      "eagerness": "medium",
      "silence_duration_ms": 500
    },
    "tools": [{ "type": "function", "name": "get_weather", ... }],
    "input_audio_noise_reduction": { "type": "near_field" },
    "input_audio_transcription": { "model": "gpt-4o-transcribe" }
  }
}
```

```json
// Health session.update
{
  "type": "session.update",
  "session": {
    "instructions": "你是一个专业的健康管理助手",
    "scene": "inquiry",
    "voice": "zhixiaobai"
  }
}
```

| 配置项 | OpenAI | Health | 说明 |
|---|---|---|---|
| 模型 | `model: "gpt-realtime"` | 连接时指定 | — |
| 系统指令 | `instructions` | `instructions` | 相同 |
| 音色 | `audio.output.voice` | `voice` | Health 扁平化 |
| 音频格式 | `audio.input/output.format` | **无需配置** | WebRTC 自动协商 Opus |
| VAD | `turn_detection` (server_vad / semantic_vad / none) | **不可配置**（固定 Silero） | Health 由 Agent 端统一管控 |
| VAD 灵敏度 | `eagerness`, `silence_duration_ms` | — | — |
| 降噪 | `input_audio_noise_reduction` | SDK `audio` 选项 | 层级不同 |
| 转写模型 | `input_audio_transcription.model` | — | Health 固定使用内置 STT |
| Function Calling | `tools[]` | — | Health 服务端定义，不暴露客户端 |
| 场景 | — | **`scene`** | Health 特有（inquiry / free_chat） |

### A.5 音频处理对比

| 环节 | OpenAI | Health |
|---|---|---|
| 上行编码 | 浏览器 → Opus → OpenAI Server | 浏览器 → Opus → LiveKit SFU → Agent |
| 下行解码 | OpenAI Server → Opus → 浏览器 | Agent → LiveKit SFU → Opus → 浏览器 |
| 中间节点 | 无（端到端） | LiveKit SFU（1 跳） |
| AEC/AGC/NS | 浏览器 WebRTC 栈 | 浏览器 WebRTC 栈 + 可选 NoiseGate |
| 非 mic 音频 | 可通过 DataChannel `input_audio_buffer.append` 发送 | 不支持（仅 Media Track） |
| 音频回放 | `<audio>` 元素自动播放 | `<audio>` 元素自动播放 |

### A.6 Function Calling 对比

```
OpenAI（客户端执行）:
  Server ── function_call_arguments.done ──► Client
  Client ── conversation.item.create        (执行函数)
             (function_call_output) ────────► Server
  Server ── response.done ─────────────────► Client

Health（服务端执行）:
  Agent Worker 内部完成 function call，客户端无感知
  Client 只收到最终的语音回复
```

| 对比点 | OpenAI | Health |
|---|---|---|
| 执行位置 | **客户端**（通过事件透传） | **服务端**（Agent Worker 内网） |
| 安全性 | 工具定义暴露给客户端 | 工具定义不暴露，更安全 |
| 灵活性 | 客户端可自定义执行逻辑 | 服务端统一控制 |
| 延迟 | 需客户端网络往返 | 内网调用，更快 |

### A.7 客户端代码对比

#### OpenAI（原生 WebRTC）

```javascript
// 1. 获取 ephemeral key
const tokenRes = await fetch("/token");
const EPHEMERAL_KEY = (await tokenRes.json()).value;

// 2. 创建 PeerConnection
const pc = new RTCPeerConnection();

// 3. 设置音频播放
const audio = document.createElement("audio");
audio.autoplay = true;
pc.ontrack = (e) => (audio.srcObject = e.streams[0]);

// 4. 获取麦克风
const ms = await navigator.mediaDevices.getUserMedia({ audio: true });
pc.addTrack(ms.getTracks()[0]);

// 5. 创建 DataChannel
const dc = pc.createDataChannel("oai-events");
dc.addEventListener("message", (e) => {
  const event = JSON.parse(e.data);
  // 处理 28+ 种事件...
});

// 6. SDP 交换
const offer = await pc.createOffer();
await pc.setLocalDescription(offer);
const sdpRes = await fetch("https://api.openai.com/v1/realtime/calls", {
  method: "POST",
  body: offer.sdp,
  headers: { Authorization: `Bearer ${EPHEMERAL_KEY}`, "Content-Type": "application/sdp" },
});
await pc.setRemoteDescription({ type: "answer", sdp: await sdpRes.text() });
```

#### Health（SDK 封装）

```javascript
import { HealthRealtimeClient } from '@health/realtime-sdk'

const client = new HealthRealtimeClient({
  tokenProvider: () => fetch('/api/token', { method: 'POST' }).then(r => r.json())
})

await client.connect({ model: 'health-assistant', scene: 'inquiry' })
await client.setMicrophoneEnabled(true)

client.on('agent.state_changed', (state) => { /* listening|thinking|speaking */ })
client.on('response.transcript.delta', (delta) => { /* 实时字幕 */ })
client.on('response.done', (resp) => { /* 回复完成 */ })
```

| 对比点 | OpenAI 原生 | Health SDK |
|---|---|---|
| 代码量 | ~25 行（不含事件处理） | ~8 行（含事件处理） |
| WebRTC 知识要求 | 需理解 SDP、ICE、PeerConnection、DataChannel | 无需（SDK 封装） |
| 音频设备管理 | 手动 `getUserMedia` + `addTrack` | `setMicrophoneEnabled(true)` |
| 事件处理 | 需处理 28+ 种事件 | 10 种事件 |
| 断线重连 | 需自行实现 | SDK 内置 |
| React 支持 | 无内置（或用 Agents SDK） | `useRealtimeSession` Hook |

### A.8 综合对比总结

| 维度 | OpenAI Realtime WebRTC | Health Realtime WebRTC | 评价 |
|---|---|---|---|
| **接入复杂度** | 中等（需理解 WebRTC 基础） | **低**（SDK 一行 connect） | Health 更易接入 |
| **协议完整度** | **高**（28+ 事件全覆盖） | 中（10 事件覆盖核心场景） | OpenAI 更灵活 |
| **延迟** | **最优**（端到端模型） | 优（Pipeline 多环节但 SFU 转发快） | OpenAI 略优 |
| **VAD 控制** | **高**（semantic_vad 等可配） | 低（固定 Silero，不可配） | OpenAI 更灵活 |
| **安全性** | 中（tools 暴露客户端） | **高**（tools 服务端执行） | Health 更安全 |
| **扩展性** | 受 OpenAI 模型能力限制 | **高**（可替换 STT/LLM/TTS） | Health 更灵活 |
| **视觉能力** | 通过 `input_image` 支持 | 通过 `input_image.send` + Camera Track | 相当 |
| **Agent 状态** | 无内置 | **`agent.state_changed` 内置** | Health UI 体验更好 |
| **SDK 质量** | Agents SDK (TypeScript) | `@health/realtime-sdk` (含 React Hooks) | 相当 |
| **费用** | 按 token/音频时长计费 | 自建可控 | Health 成本可控 |

---

## 附录 B：三种接入方式速查（Health 内部）

| | WebRTC（本文档） | WebSocket |
|---|---|---|
| 文档 | `realtime-webrtc-api.md` | `realtime-websocket-api.md` |
| 事件数 | **10** | 14 |
| 音频传输 | Media Track (UDP) | Base64 PCM (TCP) |
| 延迟 | **最优** | +50ms (强网) / +200ms (弱网) |
| 浏览器支持 | 原生 | 需手动音频处理 |
| 适用场景 | Web 前端、移动端 | 服务端对接、IoT、需自管音频流的客户端 |
| 连接方式 | HTTP + WebRTC SDP | 单一 WebSocket |
| 客户端音频编码 | 不需要 | 需 Base64 + PCM |

## 附录 C：事件数量对比

```
vLLM              ███░░░░░░░░░░░░░░░░░░░░░░  7
WebRTC（本文档）  ████░░░░░░░░░░░░░░░░░░░░░  10
智谱 / WS极简版   █████░░░░░░░░░░░░░░░░░░░░  12
阿里云 Omni       ██████░░░░░░░░░░░░░░░░░░░  ~17
WS 完整版         ████████░░░░░░░░░░░░░░░░░  21
OpenAI GA         ██████████░░░░░░░░░░░░░░░  28+
```
