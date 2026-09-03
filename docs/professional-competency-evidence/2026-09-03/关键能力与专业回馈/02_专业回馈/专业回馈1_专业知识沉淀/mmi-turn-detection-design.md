# MMI Turn Detection 完整设计方案

> 文档状态：V0 代码已实现；Phase 2 未完成；Phase 3 Active Canary 审计未通过  
> 模块名称：MMI Turn Detection  
> 英文全称：Multimodal Intelligence Turn Detection  
> 中文名称：多模态智能轮次检测  
> 简称：MMI-TD

## 1. 背景

传统 VAD 只能判断当前是否存在语音，不能判断：

- 用户是否已经表达完整。
- 用户停顿是句中停顿还是轮次结束。
- Agent 说话期间的用户语音是否为真实打断。
- 用户输入是否只是 backchannel，例如“嗯嗯”“好的”。
- 用户是否表达了“等一下”“我想想”等等待意图。

当前工程使用 LiveKit Agents 1.5.6，主要轮次链路为：

```text
Silero VAD
  → Streaming STT
  → LiveKit MultilingualModel
  → Dynamic Endpointing
  → VAD-mode Interruption
  → LLM / TTS
```

MMI-TD 在现有能力之上增加统一决策层，使用户轮次结束判断和 Agent 打断判断使用同一个协议、状态上下文和执行入口。

## 2. 目标与范围

### 2.1 目标

MMI-TD 需要使 Agent 能够：

```text
用户没有说完       → 继续听
用户已经说完       → 提交用户轮次并回复
用户真实打断       → 停止 Agent 输出并开始听用户
用户只是 backchannel → Agent 继续说
用户要求等待       → 保持安静并继续等待
无效短输入         → 不切换说话权
```

首版不训练新模型，使用 LiveKit 现有能力与规则策略实现。

### 2.2 接入范围

| 链路 | Shadow 模式 | Active 模式 |
|---|---:|---:|
| `pipeline` | 支持 | 支持 |
| `omni` | 支持 | 支持 |
| `realtime/qwen` | 支持 | 支持 |
| `realtime/aliyun` | 不接入 | 不接入 |

Aliyun Realtime 当前由服务端模型拥有 VAD、轮次检测和打断控制权，首版不由 MMI-TD 接管。

### 2.3 职责边界

MMI-TD 负责：

- 判断用户轮次是否结束。
- 判断是否继续等待用户。
- 识别等待意图。
- 判断用户是否真实打断 Agent。
- 判断输入是否为 backchannel 或无效输入。
- 决定何时提交用户轮次。
- 决定何时停止 Agent 输出。
- 决策日志、指标、灰度控制和故障降级。

MMI-TD 不负责：

- VAD 模型推理。
- STT 模型推理。
- 前端背景人声 Gate 和音频前置过滤。
- LLM 内容生成。
- TTS 合成。
- Aliyun Realtime 服务端轮次控制。

## 3. 核心设计决策

### 3.1 四个主动作

MMI-TD 的稳定输出协议使用四个主动作：

```python
class MMITurnAction(str, Enum):
    CONTINUE_LISTENING = "CONTINUE_LISTENING"
    START_SPEAKING = "START_SPEAKING"
    START_LISTENING = "START_LISTENING"
    CONTINUE_SPEAKING = "CONTINUE_SPEAKING"
```

| 动作 | 含义 | 执行语义 |
|---|---|---|
| `CONTINUE_LISTENING` | 用户尚未说完或需要继续等待 | 保持用户轮次，不提交 |
| `START_SPEAKING` | 用户轮次结束，Agent 可以回复 | 提交用户轮次 |
| `START_LISTENING` | 用户真实打断 | 停止 Agent 输出，进入用户轮次 |
| `CONTINUE_SPEAKING` | 用户没有形成有效打断 | Agent 继续输出 |

以下语义作为辅助字段表达，不扩展主动作集合：

```text
HOLD_SILENCE = CONTINUE_LISTENING + wait_intent=true
IGNORE       = CONTINUE_LISTENING / CONTINUE_SPEAKING + ignore_input=true
UNCERTAIN    = 保持当前方向 + observe_more_ms > 0
```

四动作协议避免将轮次动作、输入分类和临时观察状态混在一起，也便于后续训练模型。

### 3.2 动作与内部状态分离

四个主输出是瞬时动作决策，不是内部持久状态。MMI-TD Runtime 需要维护内部状态：

```text
IDLE
USER_SPEAKING
USER_PAUSING
AGENT_SPEAKING
OBSERVING_INTERRUPTION
WAITING_USER
TURN_COMMITTED
```

内部状态用于管理定时器、观察窗口、幂等执行和过期决策。

### 3.3 Endpointing 属于 MMI-TD

`CONTINUE_LISTENING` 和 `START_SPEAKING` 本质上是 endpointing 决策，因此 endpointing 必须属于 MMI-TD 的职责范围。

首版不调整当前 endpointing 体验，而是实现 `BaselineEndpointingPolicy`，复刻当前 LiveKit 行为，并继续使用已有配置：

```text
SESSION_ENDPOINTING_MODE
SESSION_MIN_ENDPOINTING_DELAY
SESSION_MAX_ENDPOINTING_DELAY
```

首版不引入第二套 MMI endpointing 时间配置，也不采用新的 `350ms / 1600ms` 参数。

### 3.4 Shadow-first

MMI-TD 必须先以 Shadow 模式运行：

- LiveKit 原生轮次检测和打断继续控制会话。
- MMI-TD 采集信号、生成决策并记录对比数据。
- MMI-TD 不执行 `commit`、`interrupt` 或 `clear`。

完成数据审核和规则调优后，才能进入 Active 灰度。

### 3.5 Active 模式必须独占控制权

LiveKit 的 VAD-mode interruption 会在达到时长和字数条件后自行暂停或打断 Agent。外层规则无法在打断发生前否决该动作。

因此 Active 模式必须使用：

```python
turn_detection = "manual"
```

并由唯一的 `MMITurnExecutor` 执行：

```text
START_SPEAKING  → session.commit_user_turn()
START_LISTENING → session.interrupt(force=True)
```

## 4. 总体架构

```text
LiveKit VAD / STT / Agent Events
                ↓
        MMISignalCollector
                ↓
       MMITurnContextStore
                ↓
         MMITurnDetector
       ├─ InterruptionPolicy
       └─ EndpointingPolicy
                ↓
        MMITurnDecision
                ↓
   ShadowRecorder / MMITurnExecutor
                ↓
       LiveKit public actions
```

### 4.1 模块职责

| 模块 | 职责 |
|---|---|
| `MMISignalCollector` | 订阅 LiveKit 事件并转换为统一信号 |
| `MMITurnContextStore` | 维护当前会话、用户轮次、Agent 输出和定时器状态 |
| `MMITurnDetector` | 根据上下文生成纯决策，不产生副作用 |
| `InterruptionPolicy` | Agent 输出期间判断是否切换到用户 |
| `EndpointingPolicy` | Agent 未输出时判断是否提交用户轮次 |
| `EOUService` | 封装 `MultilingualModel` 推理、超时和任务取消 |
| `ShadowRecorder` | 记录 MMI 决策与 LiveKit 实际行为 |
| `MMITurnExecutor` | Active 模式下执行 LiveKit 动作并保证幂等 |
| `MMITurnRuntime` | 管理会话级生命周期、模式、任务和故障降级 |

### 4.2 推荐目录

```text
backend/livekit_agent/mmi_turn_detection/
├── __init__.py
├── models.py
├── config.py
├── context_store.py
├── signal_collector.py
├── detector.py
├── rule_detector.py
├── interruption_policy.py
├── endpointing_policy.py
├── eou_service.py
├── executor.py
├── runtime.py
└── metrics.py
```

## 5. 统一输入协议

```python
@dataclass
class MMITurnContext:
    session_id: str
    turn_id: int
    event_id: int

    agent_state: str
    user_state: str
    tts_playing: bool
    awaiting_confirmation: bool

    vad_speech: bool
    speech_ms: int
    transcript_observe_ms: int
    silence_ms: int

    partial_text: str
    final_text: str
    stt_confidence: float | None

    eou_prob: float | None

    last_user_text: str
    last_agent_text: str

    wait_intent_active: bool
    locale: str
```

### 5.1 V0 信号可用性

| 信号 | V0 可用性 | 处理方式 |
|---|---|---|
| 用户和 Agent 状态 | 可用 | LiveKit 状态事件 |
| STT partial/final | 可用 | `user_input_transcribed` |
| speech/silence 时长 | 可用 | 状态时间戳与单调时钟计算 |
| STT 候选观察时长 | 可用 | 从当前轮次首个非空 partial/final transcript 开始计算 |
| EOU probability | 需主动调用 | `EOUService` 调用 `MultilingualModel` |
| STT confidence | 部分可用 | 必须视为可选信号 |
| awaiting confirmation | 需显式提供 | 由业务或 Agent 设置，不能仅靠文本猜测 |
| current TTS 播放文本 | V0 不可靠 | 使用 `last_agent_text` 替代 |

V0 不依赖以下字段：

```text
audio_chunk
dialog_summary
current_tts_text
partial_stability
background_prob
```

这些字段可在后续模型化阶段扩展。

## 6. 统一输出协议

```python
@dataclass
class MMITurnDecision:
    action: MMITurnAction
    confidence: float
    confidence_level: str
    reason: str

    eou_prob: float | None = None
    barge_in_score: float | None = None
    backchannel_score: float | None = None

    wait_intent: bool = False
    ignore_input: bool = False
    observe_more_ms: int = 0

    turn_id: int = 0
    based_on_event_id: int = 0
```

规则版中的 `confidence` 是规则评分，不应描述为经过校准的模型概率。日志中同时记录：

```text
confidence_level = HIGH / MEDIUM / LOW
```

后续模型实现可以输出经过校准的概率，但不改变协议结构。

## 7. 插件化 Detector

核心接口固定为：

```python
class MMITurnDetector(Protocol):
    async def detect(self, ctx: MMITurnContext) -> MMITurnDecision:
        ...
```

演进实现：

```text
RuleBasedMMITurnDetector
TextMMITurnDetector
AudioTextMMITurnDetector
HybridMMITurnDetector
```

V0 使用 `RuleBasedMMITurnDetector`。Detector 必须是纯决策模块：

- 不直接调用 LiveKit Session。
- 不维护不可追踪的后台任务。
- 不直接修改 ContextStore。
- 同一输入应产生稳定结果。

## 8. Endpointing Policy

### 8.1 BaselineEndpointingPolicy

目标是保持当前 LiveKit Dynamic Endpointing 行为：

```text
用户开始说话
  → 取消 pending endpointing timer

新轮次的首个非空 STT 可能早于 VAD speech-start 到达
  → 若上一轮已提交，由该 STT 直接开启新 turn，后续 VAD 事件不得清空已收到文本

用户停止说话或 final transcript 更新
  → 启动或刷新 EOU 推理

EOU 判断语义可能完整
  → 使用 min_endpointing_delay

EOU 判断语义可能未完成
  → 使用 max_endpointing_delay

仅有 partial transcript 且缺少可靠 EOU 完成证据
  → 使用 max_endpointing_delay，避免 final transcript 到达前提前提交

等待期间用户重新开口
  → 取消提交

达到目标 delay
  → START_SPEAKING
```

LiveKit 的 `user_state=listening` 通常在 VAD 已累计 `min_silence_duration` 后才发出。早期实现曾将这段 VAD 静音时间计入 MMI 的 `silence_ms`，但当前 LiveKit 手动轮次模式下，FDB Active 基线表明这会把 `550ms` VAD 静音直接抵扣 endpointing delay，导致事件到达后立即提交。默认 `vad_silence_offset_ms` 因此设为 `0`，从 `user_state=listening` 到达后完整等待 `min_endpointing_delay`；该补偿项仅保留为显式兼容开关，不再自动继承 VAD 配置。完整 Active 回归证明将全局 `min_endpointing_delay` 提高到 `1.0s` 虽能减少自然停顿抢话，却会把 Candor 正常接话平均延迟提高到 `7.634s`。当前策略采用三档等待：EOU 达到 `eou_complete_threshold_floor=0.20` 时使用 `0.5s`；EOU 高于模型原始 unlikely 阈值但低于 `0.20` 时使用 `1.5s`；EOU 低于模型原始阈值、仅有 partial 或文本明显不完整时使用 `3.0s`。最终转写明确以英文或中文问号结束时，也可作为强完成信号使用 `0.5s`。首轮 SpeakerGate 尚在注册且明确返回 `locked=false` 时仍优先使用 `3.0s` 保护；目标说话人锁定后的回调会重新计算剩余等待，使最终完整轮次不必承担整个最大延迟。endpoint 提交使用独立的 `endpoint_target_latch_max_ms=15000` 保存本逻辑轮次内的 `TARGET_CONFIDENT` 结果，避免长句在结束时因 3 秒实时打断锁存过期而被丢弃；打断路径仍使用 `target_latch_max_ms=3000`。

### 8.2 EOUService

LiveKit 公开事件不会直接提供 `MultilingualModel` 的 EOU 概率，因此由 `EOUService` 独立调用。

调用约束：

- 只在用户停止说话、final transcript 更新或必要的观察窗口结束时调用。
- 不对每个 partial transcript 调用。
- 新输入到达时取消旧推理任务。
- 设置独立于规则决策的推理超时，默认 `500ms`，避免模型冷启动或调度抖动造成大量空值。
- 推理异常时回退当前基线延迟策略。

### 8.3 Wait Intent

等待表达示例：

```text
等一下
我想想
稍等
先别说
```

命中后：

```text
action = CONTINUE_LISTENING
wait_intent = true
```

Runtime 需要：

- 取消普通 endpointing timer。
- 进入 `WAITING_USER`。
- 用户重新说话时退出等待态。
- 设置等待上限，防止会话永久停留。

建议初始最大等待时间为 15 秒。超时后的提示或继续等待由产品策略决定，不应直接等价为提交空用户轮次。

## 9. Interruption Policy

### 9.1 基本原则

Agent 正在说话时，VAD 或 STT 都可以产生候选打断。MMI-TD 必须结合文本、时长和会话状态判断是否真正切换说话权。

VAD speaking 事件可能缺失或晚于 STT transcript，因此保留两个独立时长：

```text
speech_ms              = LiveKit VAD speaking 时长
transcript_observe_ms  = 当前轮次首个 STT transcript 到当前的观察时长
effective_observe_ms   = max(speech_ms, transcript_observe_ms)
```

规则决策使用 `effective_observe_ms`，日志同时保留两个原始时长。STT-only 候选必须经过观察窗口，
不能在首个瞬时 partial 到达时直接触发普通打断；明确 backchannel 可立即忽略。

### 9.2 决策优先级

```text
1. 强打断意图 + effective_observe_ms 达标
   → START_LISTENING

2. Agent 正在等待确认 + 有效短回答
   → START_LISTENING

3. 明确 backchannel
   → CONTINUE_SPEAKING + ignore_input

4. 空文本、无效文本或极短语音
   → CONTINUE_SPEAKING + observe_more_ms

5. 普通有效插话达到 effective_observe_ms 与文本要求
   → START_LISTENING

6. 无 VAD speaking 的 final STT 短回答达到独立观察时长与文本要求
   → START_LISTENING

7. 信息不足
   → CONTINUE_SPEAKING + observe_more_ms
```

STT-only final 短回答使用更短但独立的阈值，初始配置为 `250ms + 2 个有效字符`。
该规则位于 backchannel 和无效文本过滤之后，用于覆盖“清朝”“北京呢”等上下文短回答；
单个瞬时 partial 或“嗯”“好的”等 backchannel 不会触发该规则。

### 9.3 强打断意图

初始词表可包括：

```text
停
等等
等一下
不是
不对
错了
取消
重新
换成
改成
别说了
```

不能只进行简单子串匹配。例如：

```text
不要停止服药
```

包含“停止”，但不代表要求 Agent 停止输出。强打断识别需要考虑：

- 短句边界。
- 否定范围。
- 是否为对 Agent 的控制意图。
- 用户语音持续时长。

### 9.4 Backchannel

初始 backchannel 可包括：

```text
嗯
嗯嗯
哦
好的
对
是
行
明白
知道了
```

Backchannel 不是永久静态词表。以下情况仍可能是有效回答：

- Agent 正在询问确认问题。
- Agent 请求用户在多个选项中选择。
- Agent 明确等待“是/否”回答。

因此 `awaiting_confirmation` 应由业务显式设置，并优先于 backchannel 规则。

### 9.5 推荐初始参数

```text
强打断最短语音：150ms
普通插话最短语音：600ms
普通插话最少中文字符：5
普通观察窗口：400ms
最大观察时长：800ms
```

STT confidence 缺失时不能作为否决依据。

## 10. Runtime 与内部状态机

### 10.1 关键状态转移

```text
IDLE / USER_PAUSING
  + user speaking
  → USER_SPEAKING

USER_SPEAKING
  + user stopped
  → USER_PAUSING
  → endpointing policy

USER_PAUSING
  + START_SPEAKING
  → TURN_COMMITTED

USER_PAUSING
  + wait_intent
  → WAITING_USER

AGENT_SPEAKING
  + user candidate speech
  → OBSERVING_INTERRUPTION
  → interruption policy

OBSERVING_INTERRUPTION
  + START_LISTENING
  → USER_SPEAKING

OBSERVING_INTERRUPTION
  + CONTINUE_SPEAKING
  → AGENT_SPEAKING
```

### 10.2 ContextStore 必须维护

```text
turn_id
event_id
agent_speech_id
pending_endpointing_timer
pending_observation_timer
pending_eou_task
committed
interrupted_agent_speech_id
wait_intent_active
consecutive_error_count
```

所有计时使用单调时钟，避免系统时间调整影响时长判断。

## 11. Action Executor

Active 模式下只有 `MMITurnExecutor` 可以执行轮次动作。

```text
START_SPEAKING
  → session.commit_user_turn()

START_LISTENING
  → session.interrupt(force=True)

CONTINUE_LISTENING
  → 不调用 LiveKit 动作，维护或刷新 timer

CONTINUE_SPEAKING
  → 不停止输出；必要时清理无效用户输入
```

`clear_user_turn()` 必须谨慎使用。只有确认输入应忽略，且不会破坏随后用户有效插话时才可调用。

LiveKit 1.5.6 的 `session.commit_user_turn()` 返回 `asyncio.Future[str]`。该
Future 仅在 STT flush 完成并已触发 end-of-turn 后完成。因此：

```text
await session.commit_user_turn() 成功
  → 本次提交已由 LiveKit 接受并触发 EOU
  → Runtime 立即确认 committed
  → 不再等待 conversation_item_added，也不允许超时后盲目重试
```

`conversation_item_added(role=user)` 在 Active 模式只作为审计事件，不能作为
`commit_user_turn()` 的二阶段确认或修改当前轮次状态。该事件不包含 commit request ID，
迟到旧事件与当前轮次甚至可能具有相同文本，无法可靠关联。否则 LLM 或 Agent hook 延迟
会被误判为提交失败或当前轮次确认，导致重复 commit、误确认和轮次卡住。

### 11.1 并发与幂等约束

执行前必须验证：

```text
decision.turn_id == current_turn_id
decision.based_on_event_id 未过期
本轮尚未 commit
当前 agent speech 尚未 interrupt
用户没有重新开始说话
Runtime 当前处于 ACTIVE 且未降级
```

强制约束：

```text
同一 turn_id 最多 commit 一次
同一 agent_speech_id 最多 interrupt 一次
用户重新开口立即取消 endpointing timer
新 partial/final 到达后旧观察任务失效
过期决策不得执行
```

## 12. 运行模式与回退

### 12.1 三种运行模式

```python
class MMIMode(str, Enum):
    OFF = "off"
    SHADOW = "shadow"
    ACTIVE = "active"
```

| 模式 | LiveKit 原生控制 | MMI-TD 决策 | MMI-TD 执行动作 |
|---|---:|---:|---:|
| `OFF` | 是 | 否 | 否 |
| `SHADOW` | 是 | 是 | 否 |
| `ACTIVE` | 否 | 是 | 是 |

### 12.2 OFF / SHADOW 模式

保持当前 LiveKit 原生配置：

```python
turn_handling={
    "turn_detection": MultilingualModel(),
    "endpointing": current_endpointing_config,
    "interruption": current_vad_interruption_config,
}
```

### 12.3 ACTIVE 模式

```python
turn_handling={
    "turn_detection": "manual",
    "interruption": {
        "enabled": True,
        "discard_audio_if_uninterruptible": False,
    },
}
```

由 MMI-TD 独占调用公开 Session 动作。

### 12.4 回退策略

主要回退方式是对新会话关闭 Active：

```text
MMI_TD_MODE=off
```

新创建的会话恢复 LiveKit 原生轮次检测和打断方案。

不建议同一 Active 会话运行中自动热切换回 `MultilingualModel + VAD interruption`，原因包括：

- 用户音频缓冲和内部 timer 状态可能不一致。
- LiveKit 原生控制器可能立即处理旧信号。
- 可能出现重复 commit、旧 TTS 恢复或当前轮次丢失。
- LiveKit 公开更新接口不能完整恢复所有 interruption 配置。

### 12.5 单会话 Fail-safe

Active 会话发生故障时，不热切换到 LiveKit 原生控制器，而进入保守的 MMI fail-safe：

```text
停止执行普通 MMI 决策
取消所有 pending timer 和推理任务
记录严重告警

用户停止说话达到当前 max_endpointing_delay
  → commit user turn

Agent 说话期间用户持续有效发声达到保守阈值
  → interrupt Agent
```

自动进入 fail-safe 的条件：

```text
连续决策异常达到阈值
Detector 决策超时
Executor 动作执行异常
上下文状态不一致
重复 commit / interrupt 防线触发
```

回退层级：

```text
一级：MMI ACTIVE 正常控制
二级：单会话 MMI fail-safe
三级：关闭 Active，新会话恢复 LiveKit 原生方案
四级：全局关闭 MMI-TD Runtime
```

## 13. 配置设计

```text
# 运行模式
MMI_TD_MODE=off
MMI_TD_ACTIVE_PERCENTAGE=0
MMI_TD_ENABLED_PIPELINES=pipeline,omni,realtime_qwen

# 规则参数
MMI_TD_STRONG_INTERRUPT_MIN_MS=150
MMI_TD_ORDINARY_INTERRUPT_MIN_MS=600
MMI_TD_ORDINARY_INTERRUPT_MIN_CHARS=3
MMI_TD_STT_ONLY_FINAL_INTERRUPT_MIN_MS=250
MMI_TD_STT_ONLY_FINAL_INTERRUPT_MIN_CHARS=2
MMI_TD_OBSERVE_MS=400
MMI_TD_MAX_OBSERVE_MS=800
MMI_TD_WAIT_INTENT_MAX_MS=15000

# 稳定性与降级
MMI_TD_DECISION_TIMEOUT_MS=200
MMI_TD_EOU_TIMEOUT_MS=500
MMI_TD_MAX_CONSECUTIVE_ERRORS=3
MMI_TD_FAIL_SAFE_ENABLED=true
MMI_TD_FAIL_SAFE_INTERRUPT_MS=1200

# 独立日志
MMI_TD_LOG_FILE_ENABLED=true
MMI_TD_LOG_FILE=tmp/mmi_turn_detection.log
MMI_TD_LOG_LEVEL=INFO
MMI_TD_LOG_TO_CONSOLE=false

# Endpointing 继续使用现有配置
SESSION_ENDPOINTING_MODE=dynamic
SESSION_MIN_ENDPOINTING_DELAY=0.5
SESSION_MAX_ENDPOINTING_DELAY=3.0
```

灰度分流需要基于稳定会话标识，例如：

```python
bucket = int(hashlib.sha256(room_id.encode()).hexdigest()[:8], 16) % 100
is_active = bucket < active_percentage
```

同一会话生命周期内模式不可变化。

MMI-TD 的 Runtime、EOU 和 Executor 日志统一写入独立文件。默认关闭控制台传播，避免与 LiveKit dev logger 重复输出。开发环境可使用：

```bash
tail -f backend/livekit_agent/tmp/mmi_turn_detection.log
```

## 14. 日志与指标

### 14.1 决策日志

每次决策至少记录：

```json
{
  "session_id": "...",
  "turn_id": 12,
  "event_id": 48,
  "mode": "shadow",
  "agent_state": "speaking",
  "user_state": "speaking",
  "speech_ms": 680,
  "transcript_observe_ms": 720,
  "silence_ms": 0,
  "partial_text": "不是上海",
  "final_text": "",
  "eou_prob": null,
  "action": "START_LISTENING",
  "confidence_level": "HIGH",
  "barge_in_score": 0.9,
  "backchannel_score": 0.0,
  "wait_intent": false,
  "ignore_input": false,
  "observe_more_ms": 0,
  "reason": "strong_interrupt_intent",
  "executed": false
}
```

日志不得记录不必要的原始音频或敏感对话全文。生产环境应支持文本脱敏和采样。

### 14.2 核心指标

```text
真实打断召回率
真实打断响应时延
backchannel 误打断率
抢话率
等待过久率
用户说完到 Agent 开口时延
MMI 预测 endpoint 时间与 LiveKit 实际时间差
重复 commit / interrupt 数
过期决策执行数
Fail-safe 触发率
```

错误类型：

```text
EARLY_CUTOFF
LATE_RESPONSE
FALSE_INTERRUPT_BACKCHANNEL
MISSED_INTERRUPT
NOISE_COMMIT
STALE_DECISION
DUPLICATE_COMMIT
DUPLICATE_INTERRUPT
FAIL_SAFE_TRIGGERED
```

Shadow 模式不能仅以“是否与 LiveKit 一致”作为正确标准。MMI-TD 的目标包括修正 LiveKit 原生行为，因此关键场景需要人工标签或可验证的测试真值。

原生打断标注必须以 Assistant conversation item 的 `interrupted=true` 为权威信号。
`agent_state` 从 `speaking` 切换到其他状态只能用于暂存停止前上下文，不能直接判定为原生打断，
因为用户开始说话时 Agent 也可能恰好自然播报完成。

## 15. 测试方案

### 15.1 单元测试

规则测试：

```text
强打断意图 → START_LISTENING
否定语境中的“停止”不触发强打断
普通有效插话 → START_LISTENING
backchannel → CONTINUE_SPEAKING
确认问题后的短回答 → START_LISTENING
等待表达 → CONTINUE_LISTENING + wait_intent
语义完整且达到基线延迟 → START_SPEAKING
语义未完整时等待到 max delay
```

竞态和幂等测试：

```text
用户重新开口取消 pending commit
final transcript 到达使旧 EOU 任务失效
同一轮多个事件只 commit 一次
同一 Agent speech 只 interrupt 一次
过期观察任务不能执行动作
Fail-safe 取消所有 pending task
```

### 15.2 Shadow 集成测试

复用现有 realtime 测试体系，并新增：

```text
强打断词音频
普通有效插话
backchannel
极短输入
wait intent
语义未完成停顿
确认问句短回答
打断后完成发言并正常回复
```

### 15.3 Active 上线阻断条件

```text
重复 commit = 0
重复 interrupt = 0
过期决策执行 = 0
强打断召回率 ≥ 95%
backchannel 误打断率 ≤ 3%
规则执行异常率 = 0
Fail-safe 路径测试通过
关闭 Active 后新会话可恢复 LiveKit 原生方案
```

## 16. 实施计划与阶段测试门禁

每个 Phase 必须满足对应退出条件后才能进入下一阶段。测试通过表示达到当前阶段定义的可验证门槛，不代表系统不存在任何缺陷；生产灰度仍必须持续监控并保留回退能力。

当前实施状态：

| Phase | 开发状态 | 阶段状态 |
|---|---|---|
| Phase 0：协议和规则实现 | 已实现 | 自动化测试已通过，仍需持续补充 LiveKit 契约测试 |
| Phase 1：Shadow Runtime | 已实现 | 待真实房间和性能验证 |
| Phase 2：Shadow 数据审核 | 未实现 | 待采集和审核真实数据 |
| Phase 3：Active Canary | 已开始内部测试 | 未通过；曾出现重复 commit 和会话卡住，禁止扩大灰度 |
| Phase 4：全量与模型化演进 | 仅保留了可插拔接口 | 未开始 |

### 16.1 Phase 0：协议和规则实现

实施内容：

- 实现输入输出协议、ContextStore 和 Detector 接口。
- 实现 BaselineEndpointingPolicy、RuleBasedInterruptionPolicy 和 EOUService。
- 实现 MMITurnExecutor 的幂等与陈旧决策保护。
- 此阶段不修改生产 LiveKit 控制行为。

测试方法：

```text
规则表驱动测试
  → 强打断、普通插话、backchannel、确认短答、wait intent、未完整表达

状态机测试
  → speaking/listening/agent speaking/等待态之间的合法转换

Timer 与竞态测试
  → 新事件取消旧 timer、旧 EOU 结果失效、过期决策不可执行

幂等和异常测试
  → 同一轮只 commit 一次、同一 speech 只 interrupt 一次、执行失败允许重试

配置兼容测试
  → OFF/SHADOW 保留原生配置，ACTIVE 使用 manual turn detection
```

退出条件：

```text
规则、状态机、timer、竞态和幂等自动化测试全部通过
重复 commit = 0
重复 interrupt = 0
过期决策执行 = 0
OFF 模式不实例化 MMI Runtime，不改变 LiveKit 原生行为
静态检查、编译检查和配置校验通过
```

未通过处理：阻止进入 Shadow；修复后必须重新执行完整 Phase 0 测试集。

### 16.2 Phase 1：Shadow Runtime

实施内容：

- 接入 `pipeline`、`omni` 和 `realtime/qwen`，Aliyun 保持原生控制。
- 订阅 LiveKit 状态、转录、对话项和 false interruption 事件。
- 记录 MMI 决策与 LiveKit 原生实际动作。
- Shadow 只观测，不执行 `commit`、`interrupt` 或 `clear`。
- 在 LiveKit 原生动作发生前保存上下文快照，并基于该快照生成同时刻 MMI 对照决策，避免状态切换后重新解释旧事件。

测试方法：

```text
本地 Runtime 集成测试
  → 回放合成事件流，验证 Shadow 产生决策但不执行动作

真实房间冒烟测试
  → 三条目标 pipeline 分别覆盖正常问答、打断、backchannel、wait intent

故障注入测试
  → EOU 超时、事件乱序、重复事件、Session close、空转写

行为对照测试
  → 同一测试集分别运行 OFF 与 SHADOW，比较 LiveKit 实际动作和用户可感知结果

性能测试
  → 记录 CPU、内存、事件处理延迟、EOU 调用耗时和任务泄漏
```

退出条件：

```text
Shadow 执行 commit / interrupt 次数 = 0
OFF 与 SHADOW 的 LiveKit 实际动作差异 = 0
三条目标 pipeline 的关键事件和决策日志完整率 ≥ 99.9%
关闭或断开会话后无残留 MMI 后台任务
决策异常不影响原生会话
Shadow 新增 P95 事件处理延迟 ≤ 20ms
```

未通过处理：保持 `MMI_TD_MODE=off` 或仅限内部 Shadow，不进入数据审核和 Active。

### 16.3 Phase 2：Shadow 数据审核

实施内容：

- 建立带真值的场景集和人工审核流程。
- 审核 false interruption、missed interruption、early cutoff、late response。
- 调整词表、规则评分和观察窗口。
- 验证 BaselineEndpointingPolicy 与当前体验基本一致，并识别预期改进项。

测试方法：

```text
固定基准集
  → 每类关键场景至少包含明确正例、负例和边界样本

双人独立标注
  → 标注真实动作、错误类型和允许的 endpoint 时间窗口

离线回放
  → 对固定输入重复运行 Detector，验证结果确定性

分层统计
  → 按 pipeline、场景、语速、句长和 Agent 状态分别统计

回归对比
  → 每次规则调整同时运行新版本、上一版本和 LiveKit 原生基线
```

最低数据要求：

```text
强打断、普通插话、backchannel、wait intent、语义未完整各 ≥ 200 个有效样本
至少覆盖 pipeline、omni、realtime/qwen
人工标注分歧样本完成复审
```

退出条件：

```text
强打断召回率 ≥ 95%
backchannel 误打断率 ≤ 3%
普通有效插话召回率达到评审确认的上线阈值
EARLY_CUTOFF 和 LATE_RESPONSE 不劣于 LiveKit 原生基线
固定基准集连续两次规则迭代无指标回退
所有高严重度失败样本均有归因、规则修复或明确接受理由
```

未通过处理：继续 Shadow、调整规则并重新审核；禁止开启 Active。

### 16.4 Phase 3：Active Canary

实施内容：

- Active 会话切换为 `turn_detection="manual"`，由 MMITurnExecutor 独占执行动作。
- 保持 OFF 对照组，并按稳定会话标识进行固定分桶。
- 仅从单一 Agent、单一环境和小比例房间开始灰度。
- 验证单会话 fail-safe、全局关闭和新会话回退 LiveKit 原生方案。

建议灰度阶梯：

```text
内部测试房间
  → 1%
  → 5%
  → 10%
  → 25%
  → 50%

每级至少观察一个完整业务周期；指标稳定后才可升级。
```

测试方法：

```text
Active 端到端测试
  → 正常问答、长停顿、连续发言、真实打断、backchannel、wait intent

并发和耐久测试
  → 多房间并发、长会话、多轮连续打断、快速重复开口

故障注入
  → Detector 超时/异常、EOU 异常、commit/interrupt 异常、事件乱序

回退演练
  → 触发单会话 fail-safe
  → 设置 MMI_TD_MODE=off
  → 验证新会话恢复 LiveKit 原生配置

A/B 对照
  → Active 与 OFF 对照组比较错误率、延迟、会话完成率和用户主动重说率
```

每一级灰度的通过条件：

```text
重复 commit = 0
重复 interrupt = 0
过期决策执行 = 0
规则或 Executor 未处理异常率 = 0
Fail-safe 能在故障注入时按预期触发
关闭 Active 后所有新会话恢复 LiveKit 原生方案
核心业务成功率不劣于 OFF 对照组
强打断召回率和 backchannel 误打断率满足 Phase 2 门槛
P95 用户说完到 Agent 开口时延不劣于基线超过 100ms
```

自动阻断或回退条件：

```text
出现重复 commit、重复 interrupt 或过期决策执行
出现无法提交用户轮次或无法停止 Agent 的系统性故障
高严重度错误率超过 OFF 对照组预设告警线
Fail-safe 触发率异常升高
关键日志缺失导致无法审计
```

触发后停止提高灰度比例；严重问题立即将 `MMI_TD_MODE=off`，让新会话恢复 LiveKit 原生方案。

### 16.5 Phase 4：全量与模型化演进

实施内容：

- Active 稳定后逐步提高比例直至全量。
- 基于 Shadow 和 Active 日志构建脱敏、版本化标注数据集。
- 演进为 Hybrid、Text 或 Audio-Text Detector，但保持 `TurnContext → TurnDecision` 协议不变。
- 规则 Detector 始终作为模型低置信度和故障时的回退实现。

测试方法：

```text
模型离线测试
  → 独立训练/验证/测试集，防止会话和用户泄漏

规则与模型对照
  → 在同一固定基准集比较召回率、误触发率和 endpoint 延迟

鲁棒性测试
  → 空文本、长文本、噪声转写、语言切换、缺失特征和超时

性能和容量测试
  → 推理 P50/P95/P99、吞吐、资源占用和超时率

Shadow 模型测试
  → 模型先仅观测，不直接替换 Active Detector

模型 Canary
  → 使用与 Phase 3 相同的固定分桶、灰度阶梯、回退和阻断机制
```

模型替换规则版的退出条件：

```text
独立测试集上的关键指标显著优于或不劣于规则基线
模型 P99 决策耗时小于配置的决策超时
模型超时、异常和低置信度均能可靠回退规则 Detector
Shadow 数据审核通过
模型 Canary 各级通过且业务指标不劣于规则 Active
数据版本、模型版本和决策日志可完整追溯
```

全量后仍需保留：

```text
OFF 原生回退
规则 Detector 回退
固定回归基准集
持续线上指标和错误样本审核
周期性回退演练
```

### 16.6 统一测试证据与阶段签署

每次 Phase 验收必须产出可追溯测试报告，至少包含：

```text
测试计划 ID 和执行时间
代码 commit、配置版本、规则或模型版本
测试数据集版本、样本量和场景分布
pipeline、环境和灰度比例
全部门禁指标及其分母、分子和置信区间
失败样本、错误分类、严重度和处置结论
回退演练结果
验收人和最终结论
```

Phase 0 当前自动化检查命令：

```bash
cd backend/livekit_agent
uv run --with pytest --with pytest-asyncio pytest test/mmi_turn_detection -q
uv run --with ruff ruff check mmi_turn_detection test/mmi_turn_detection
.venv/bin/python -m compileall -q .
git diff --check
```

阶段签署规则：

```text
任何阻断指标失败
  → 当前 Phase 判定失败

仅非阻断指标轻微回退
  → 必须记录接受理由、风险所有者和修复期限

测试数据、日志或指标不完整
  → 不得判定通过

进入下一 Phase 前
  → 必须冻结本阶段通过的配置、规则和测试基准
```

## 17. 设计合理性与优化空间

### 17.1 当前设计的合理性

- 四动作协议足以覆盖 full-duplex 轮次保持和说话权切换。
- Endpointing 与 interruption 由同一上下文和决策层统一管理。
- Detector、Runtime 和 Executor 分离，避免规则与副作用耦合。
- Shadow-first 降低替换 LiveKit 原生控制器的风险。
- Active 使用 manual turn detection，确保 MMI-TD 拥有最终决策权。
- 保留新会话恢复 LiveKit 原生方案和单会话 fail-safe。
- 插件接口允许后续替换为模型，而无需重构 LiveKit 接入。

### 17.2 后续优化方向

1. **规则评分校准**

   使用 Shadow 标注数据将规则分数校准为可解释的置信度，并识别不同规则之间的冲突。

2. **显式业务状态**

   由业务显式提供 `awaiting_confirmation`、结构化输入阶段等状态，减少仅靠文本推断造成的错误。

3. **动态场景 Profile**

   在保持 V0 基线稳定后，可为普通聊天、结构化输入、慢速表达等场景提供不同策略，但仍复用同一动作协议。

4. **模型化 Detector**

   先引入 Text 或 Hybrid Detector，解决规则难以覆盖的语义边界；音频文本模型仅在有明确数据收益后引入。

5. **更精确的播放上下文**

   后续若能够稳定获取当前播放文本和播放位置，可提升插话相关性、纠错意图和 backchannel 判断。

6. **跨语言规则**

   当前规则层已支持 `zh-CN`、`en-US` 和中英文混说，并支持从 JSON 文件增量添加、删除或整类替换关键词。后续增加阿语等语言时，应继续扩展独立 locale 规则包和标准化逻辑。

### 17.3 中英文可配置关键词规则

规则层由 `MultilingualPatternMatcher` 统一提供，默认同时加载中文和英文规则。未配置外部文件时使用代码内置默认规则；外部配置加载或校验失败时记录告警并回退默认规则。

配置入口：

```text
MMI_TD_PATTERNS_FILE=mmi_turn_detection/mmi-patterns.json
MMI_TD_PATTERN_LOCALES=zh-CN,en-US
```

正式初始规则文件：

```text
backend/livekit_agent/mmi_turn_detection/mmi-patterns.json
```

初始版本 `2026-06-09.initial-v1` 完整迁移了此前 Shadow/Active 多轮测试使用的中文写死规则，并补充英文初始规则。正式文件对中英文均设置 `replace_defaults=true`，因此运行时规则完全由文件内容决定；代码内置规则只作为配置文件异常时的兜底。

每个 locale 支持：

```text
strong_interrupt.exact
strong_interrupt.prefixes
strong_interrupt.contains
strong_interrupt.exclusions
strong_interrupt.repeated_prefixes
backchannels
confirmations
wait_expressions
incomplete_suffixes
noise_expressions
```

默认配置采用增量合并。可通过：

```json
{
  "replace_defaults": true
}
```

清空该 locale 的内置默认规则后重新定义；也可以使用 `remove` 删除指定默认规则。

每条决策日志包含：

```text
pattern_version
matched_rule
matched_pattern
```

用于关联规则版本、定位误判来源并执行 badcase 回归。

## 18. 最终方案摘要

首版 MMI-TD 采用：

```text
四动作主协议
  +
RuleBasedMMITurnDetector
  +
BaselineEndpointingPolicy
  +
RuleBasedInterruptionPolicy
  +
Shadow-first
  +
Active manual turn detection
  +
单一 MMITurnExecutor
  +
turn_id / event_id 幂等控制
  +
单会话 fail-safe
  +
新会话回退 LiveKit 原生方案
```

该设计在不训练新模型的前提下，能够统一管理用户轮次结束和 Agent 打断，并为后续 Text、Audio-Text 或 Hybrid Detector 保留稳定的升级接口。
