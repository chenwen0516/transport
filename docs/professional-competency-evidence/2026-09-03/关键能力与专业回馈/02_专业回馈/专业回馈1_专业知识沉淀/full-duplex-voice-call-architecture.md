# 全双工语音通话系统 — 架构与功能梳理

## 系统总体架构

```
┌──────────────────────────────────────────────────────────────────┐
│                        前端 (Next.js)                            │
│  ┌─────────────────────────────────────────────────────────┐     │
│  │              app/chat/call/page.tsx                      │     │
│  │  ┌──────────┐  ┌──────────┐  ┌───────────────────────┐  │     │
│  │  │VoiceVisu-│  │VideoPre- │  │   VoiceSubtitles      │  │     │
│  │  │ alizer   │  │  view    │  │  (实时字幕/VLM状态)    │  │     │
│  │  └──────────┘  └──────────┘  └───────────────────────┘  │     │
│  │  ┌──────────────────────────────────────────────────┐   │     │
│  │  │        useLiveKitCall (核心 Hook)                  │   │     │
│  │  │  Room连接 / 音频轨道 / 视频轨道 / 转录 / 状态     │   │     │
│  │  └──────────────────────────────────────────────────┘   │     │
│  └─────────────────────────────────────────────────────────┘     │
│                            │ WebRTC                              │
│                            ▼                                     │
│              POST /api/livekit/token                             │
│                   (Manager FastAPI)                               │
└──────────────────────────────────────────────────────────────────┘
                             │
                      LiveKit SFU Server
                             │
┌──────────────────────────────────────────────────────────────────┐
│                    后端 Agent (Python)                            │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │                     main.py (入口)                          │  │
│  │   AgentServer → prewarm(VAD) → entrypoint(ctx)             │  │
│  │      ├── Config (单例, .env 配置)                           │  │
│  │      ├── SessionManager / OmniSessionManager               │  │
│  │      ├── SessionEventHandlers                              │  │
│  │      └── HealthAssistantAgent / OmniHealthAssistantAgent   │  │
│  └────────────────────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │              HealthAssistantAgent (核心)                     │  │
│  │   Pipeline: Audio → VAD → STT → LLM → TTS → Audio         │  │
│  │   ┌─────────────┐  ┌──────────────┐  ┌─────────────────┐  │  │
│  │   │AudioFilter   │  │ Text LLM     │  │ Vision LLM      │  │  │
│  │   │(近场人声过滤)│  │ (对话推理)    │  │ (图像分析/VLM) │  │  │
│  │   └─────────────┘  └──────────────┘  └─────────────────┘  │  │
│  │   ┌─────────────┐  ┌──────────────┐  ┌─────────────────┐  │  │
│  │   │ STT Plugin  │  │ TTS Plugin   │  │TranscriptionSvc │  │  │
│  │   │(火山/华为)   │  │(火山/华为)    │  │ (字幕推送)      │  │  │
│  │   └─────────────┘  └──────────────┘  └─────────────────┘  │  │
│  └────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

---

## 一、后端核心架构

### 1. 入口与生命周期 (`main.py`)

| 阶段 | 说明 |
|------|------|
| **prewarm** | Worker 启动时预加载 Silero VAD 模型 |
| **entrypoint** | 收到 RTC 会话请求后，根据 `PIPELINE_MODE` 选择 pipeline 或 omni 模式 |
| **on_session_end** | 会话结束后保存 session report (JSON) |

支持两种运行模式：

- **Pipeline 模式**：VAD → STT → LLM → TTS 分离管线，使用 `HealthAssistantAgent`
- **Omni 模式**：Qwen3-Omni 多模态端到端，使用 `OmniHealthAssistantAgent`

### 2. HealthAssistantAgent (`health_agent.py`) — 核心 Agent

继承 LiveKit `Agent` 基类，实现以下处理节点：

| 节点 | 功能 |
|------|------|
| `stt_node` | STT 前置音频过滤（近场人声过滤器，过滤背景人声） |
| `transcription_node` | 转写文本处理 |
| `llm_node` | 大模型推理与回复 |
| `tts_node` | 语音合成 |

#### (a) 视觉分析工具 (`analyze_camera_image`)

通过 `@function_tool()` 装饰器注册为 LLM 可调用的工具，LLM 自主判断何时需要视觉能力：

```
用户说"帮我看看这个药" → LLM判断需视觉 → 调用 analyze_camera_image
→ 选帧+裁剪+缩放 → VLM推理 → 返回分析结果 → LLM整合回复
```

#### (b) 视频帧管理（环形缓冲 + 清晰度选帧）

- 环形缓冲 `deque(maxlen=30)` 保留最近约 1 秒的帧
- 基于 **Laplacian 方差**评估清晰度，从最近 5 帧中选最清晰的
- 帧过期检测：超过 5 秒无新帧则判定摄像头关闭

#### (c) 帧处理流水线

根据分析重点（药品/报告/食物/伤口）动态调整：

| 场景 | 目标分辨率 | 中心裁剪比例 |
|------|-----------|-------------|
| general | 768px | 不裁剪 |
| 药品 | 1024px | 70% |
| 报告 | 1024px | 75% |
| 食物 | 768px | 65% |
| 伤口 | 1024px | 60% |

#### (d) 视觉意图预判 + VLM 预分析（延迟优化核心）

这是降低 VLM 响应延迟的关键策略：

1. **意图预判**：在 `on_user_turn_completed` 中，通过关键词（"看看"、"帮我看"等）和正则模式检测用户是否有视觉意图
2. **预分析并行**：一旦检测到视觉意图，**立即截帧 + 启动后台 VLM 预分析**，与主 LLM 推理并行执行
3. **缓存命中**：当主 LLM 实际调用 `analyze_camera_image` 时，直接返回预分析缓存结果，避免重复推理
4. **否定语境排除**：防止"关了摄像头"等被误判为视觉意图

#### (e) 其他优化特性

- **VLM 冷启动预热**：首次收到视频轨道时发送轻量请求预热模型
- **可取消推理**：用户打断说话时立即取消正在运行的 VLM 任务
- **VLM 流式结果推送**：分析结果通过转录通道实时推送到前端字幕
- **视觉上下文持久化**：最近一次 VLM 结果注入后续对话上下文
- **即时反馈**：VLM 开始分析时推送"好的，让我看一下"文字反馈

### 3. 音频过滤 (`audio_filter.py`)

`NearFieldVoiceFilter` — 基于能量和谐波噪声比（HNR）的近场人声过滤器：

- 低能量帧 → 替换为静音（过滤背景噪音）
- HNR 低于阈值 → 替换为静音（过滤远场/背景人声）
- 防止 STT 被环境中其他人的说话声干扰

### 4. 转录服务 (`transcription.py`)

通过 LiveKit Transcription API 将 Agent 的文字推送到客户端，支持：

- `publish_interim()` — 临时转录（前端显示中间状态）
- `publish_final()` — 最终转录
- 用于 VLM 状态反馈（`[VLM_STATUS]` 前缀标记）

### 5. 插件体系 (`plugins/`)

| 类别 | 可用提供商 |
|------|-----------|
| **STT** | 火山引擎、火山大模型 STT、华为云 SIS、自定义 WebSocket |
| **TTS** | 火山引擎、华为云（标准/大模型）、自定义 |
| **LLM** | OpenAI 兼容（硅基流动/火山等）、自定义 |
| **Omni** | Qwen3-Omni 多模态 |

通过 `config.py` 的工厂函数按 `.env` 配置动态创建：`create_stt_from_config()`、`create_tts_from_config()`、`create_llm_pair_from_config()`

### 6. 配置中心 (`config.py`)

单例模式，从 `.env` 加载所有配置项，涵盖：Agent 名称、VAD 参数、LLM/STT/TTS 提供商与模型、会话参数、音频过滤参数、Omni 配置等。

---

## 二、前端核心架构

### 1. 通话页面 (`app/chat/call/page.tsx`)

顶层页面，整合所有子模块，布局分三段：

| 区域 | 内容 |
|------|------|
| **Header** | 场景选择器（多轮问诊/自由对话）+ Agent 切换设置 |
| **Main** | 语音模式：VoiceVisualizer + 状态文字 + 字幕；视频模式：VideoPreview + 状态文字 + 字幕 |
| **Footer** | 控制按钮（静音/摄像头/挂断/字幕开关） |

支持的 Agent 选项：`Pipeline(dev1)`、`Pipeline(prod)`、`Omni`

### 2. 核心 Hook (`hooks/use-livekit-call.ts`)

状态管理核心，负责：

| 功能 | 说明 |
|------|------|
| **Room 连接** | 通过后端 API 获取 Token，连接 LiveKit Room |
| **音频管理** | 麦克风控制、噪声门控、静音切换 |
| **视频管理** | 摄像头开关、前后摄切换、本地预览 |
| **转录管理** | 接收 LiveKit Transcription 事件，维护 `TranscriptMessage[]` |
| **Agent 状态** | 监听 Agent 状态变化（idle/listening/thinking/speaking） |

关键类型定义：

- `LiveKitStatus`: `idle | connecting | connected | reconnecting | error`
- `AgentState`: `idle | listening | thinking | speaking`
- `CallMode`: `voice | video`

### 3. UI 组件

| 组件 | 功能 |
|------|------|
| `VoiceVisualizer` | Canvas 动画可视化，根据 Agent 状态展示不同动效（聆听/思考/说话） |
| `VoiceSubtitles` | 实时字幕组件，区分用户/助手消息，支持临时转录和 VLM 状态标记 |
| `VideoPreview` | 本地摄像头预览，支持前摄镜像、前后切换按钮 |
| `AuthGuard` | 鉴权守卫，未登录跳转 `/login` |

### 4. 对话历史 (`hooks/use-chat-history.ts`)

通话结束后自动保存对话记录：

- 将最终转录消息转为聊天消息格式
- 通过后端 API 持久化对话历史

---

## 三、核心数据流（全双工通话）

```
用户说话                                       Agent 回答
   │                                              ▲
   ▼                                              │
[麦克风采集]                                  [扬声器播放]
   │                                              ▲
   ▼                                              │
[WebRTC 上行音频]                          [WebRTC 下行音频]
   │                                              ▲
   ▼                                              │
[LiveKit SFU]  ◄──── 转录事件(字幕) ────►  [前端字幕显示]
   │                                              ▲
   ▼                                              │
[AudioFilter 近场过滤]                       [TTS 语音合成]
   │                                              ▲
   ▼                                              │
[VAD 语音端点检测]                           [LLM 文本回复]
   │                                              ▲
   ▼                                              │
[STT 语音识别]  ──────────────────────────►  [LLM 推理]
                                                  │
                        如需视觉 ─────►  [VLM 图像分析]
                                            ▲
                                            │
                                     [视频帧 环形缓冲]
                                            ▲
                                            │
                                     [WebRTC 上行视频]
                                            ▲
                                            │
                                       [用户摄像头]
```

---

## 四、测试关注点建议

| 维度 | 测试项 |
|------|--------|
| **基础通话** | 连接/断开/重连、语音全双工、延迟与音质 |
| **打断能力** | 用户打断 Agent 说话、VLM 分析中打断 |
| **视觉功能** | 开/关摄像头、前后摄切换、VLM 分析准确性、预分析命中率 |
| **音频过滤** | 背景人声过滤效果、近场远场区分 |
| **字幕** | 实时转录准确性、VLM 状态提示、字幕开关 |
| **边界场景** | 网络抖动/断网恢复、摄像头权限拒绝、长时间通话稳定性 |
| **多 Agent 切换** | dev1/prod/omni 模式切换、场景切换 |
| **对话保存** | 通话结束后对话历史完整性 |
| **性能指标** | STT 延迟、LLM TTFT、TTS 延迟、VLM TTFC、端到端响应时间 |
