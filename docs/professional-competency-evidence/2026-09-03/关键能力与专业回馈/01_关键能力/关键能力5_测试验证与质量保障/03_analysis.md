# Pipeline Agent multi-turn Voice E2E analysis

## Release decision

**NO-GO.** The deployed `health-assistant-ziyan-dev` completed the real
LiveKit/Qwen3-TTS test, but only 24 of 44 turns passed (54.55%), and none of
the 12 multi-turn scenarios passed in full.

The primary blocker is not STT or Router-SLM latency. It is the coordination
between session-auto Speaker Gate and active MMI-FD: 11 correctly transcribed
turns were retracted before routing with
`target_speaker_not_confirmed`, so they produced no routing trace, subtitle,
answer, or output audio.

## Scope

- 12 scenarios and 44 turns, with one persistent LiveKit room per scenario.
- Qwen3 TTS (`Voice_Clone`, 24 kHz) generated every user turn.
- Real Pipeline Agent STT, active MMI-FD, session-auto Speaker Gate,
  V2-S Command-SLM, RAG, Web Search, Weather and Vision were exercised.
- The Vision scenario published a deterministic LiveKit camera track and
  verified two visual follow-ups before attempting to leave visual mode.
- Deterministic checks covered user STT CER, action, skills, slots, tool
  invocation, user/assistant subtitles, and Agent output audio.

This run does not provide a semantic/claim-level LLM score for every answer.
In particular, a correct `web.search` route is not treated as proof that every
factual claim is supported by the returned evidence.

## Results by scenario

| Scenario | Passed turns | Result |
|---|---:|---|
| Weather context inheritance | 2/4 | Failed |
| Weather clarification | 3/4 | Failed |
| Weather correction | 1/3 | Failed |
| Pending-plan cancellation | 1/3 | Failed |
| RAG follow-up | 2/4 | Failed |
| RAG router priority | 0/3 | Failed |
| Web entity follow-up | 3/4 | Failed |
| Web cache isolation | 3/4 | Failed |
| Temporal router boundary | 3/4 | Failed |
| Multi-skill composition | 1/4 | Failed |
| Intent switch and return | 3/4 | Failed |
| Vision follow-up and exit | 2/3 | Failed |

For the 31 turns that reached routing, 24 passed all deterministic checks
(77.42%). Thirteen turns never produced a routing trace.

## Accuracy and latency

| Metric | Result |
|---|---:|
| STT within CER 0.20 | 43/44 (97.73%) |
| Mean CER | 1.69% |
| Audio-send start to final user STT P50 / P95 | 2.801 s / 4.095 s |
| Final user STT to response transcript P50 / P95 | 5.424 s / 8.179 s |
| Full turn, including input and answer playback P50 / P95 | 19.187 s / 30.642 s |
| Full turn maximum | 46.678 s |
| Command-SLM router P50 / P95 | 0.900 s / 1.327 s |
| Weather invocation P50 / P95 | 2.332 s / 5.622 s |
| RAG invocation P50 / P95 | 1.321 s / 1.749 s |
| Web invocation P50 / P95 | 0.224 s / 0.272 s |

The STT timing includes the duration of the spoken input. Full-turn timing
includes answer audio playback and the settle window, so it should not be
compared directly with text-only routing benchmarks.

## Actionable findings

### P0 — Speaker Gate and MMI-FD race drops complete turns

Eleven turns had correct final STT text but were first marked
`target_speaker_pending`, then retracted as
`target_speaker_not_confirmed`. The failure is especially common around
session-auto enrollment/lock and prevents the turn from reaching intent
routing at all.

The fix should make the current utterance's final Speaker Gate verdict
available atomically to MMI-FD. A newly locked gate must not imply that the
utterance which created the lock is unconfirmed. Until fixed, active MMI-FD
plus session-auto Speaker Gate is not suitable for release gating.

### P0 — Pending-plan cancel path can leave the session unusable

“算了，不查了” was transcribed only as “算了”, committed by MMI-FD, but
produced no cancel trace or answer. The next complete story request was then
discarded with `empty_turn_timeout`. Cancellation needs an explicit,
observable action and acknowledgement, followed by a clean session state.

### P1 — Weather context does not preserve a composite slot state

“杭州天气” → “后天呢” works, but “那上海呢” loses the inherited date and
asks for it again. A later “还是看杭州吧” also lacks the date. Location and
date must be updated independently on one persistent weather context object.

The correction scenario also lost “南京” after the second turn was dropped,
and “日期也改成后天” fell back to Chat while verbally answering with the stale
Beijing context.

### P1 — Multi-skill slot extraction treats discourse words as locations

For “结合明天天气和刚才的指南…”, the weather location became `结合`.
For “只说天气就行”, it became `只说` and the date reset to today. The
CommandPlan validator needs a city/entity validity check and should inherit
the previous valid weather slots when the new turn contains no explicit city
or date.

### P1 — RAG follow-up and Vision boundary remain unstable

- “刚才的资料来自哪里” left RAG and went to ordinary Chat.
- “根据健康资料看看冰红茶…” added `vision.analyze` because “看看” was
  interpreted as visual intent, then clarified for an image.
- Actual Vision correctly read the generated screen and answered two
  successive image questions. The explicit exit turn was dropped by the
  Speaker Gate/MMI-FD race before its Chat routing could be verified.

### P1 — Grounded Web Search routing works better than answer quality

Temporal and entity questions generally reached `web.search`, and unrelated
Chat after Web did not reuse World Cup content. However:

- the first “八仙导演” answer failed closed;
- after the intervening follow-up was dropped, a later turn still asserted a
  2026 release fact;
- current-TV and Zhou Xingchi queries often returned only “insufficient web
  evidence”.

Add a claim/evidence judge to the Voice E2E suite before using Web route
success as a grounded-answer release metric.

## Recommended order

1. Fix Speaker Gate → MMI-FD verdict handoff and add a regression where the
   enrollment-completing utterance must be committed.
2. Fix cancel/recovery state and rerun the 12 scenarios.
3. Persist and validate composite weather slots.
4. Add city/entity validation to CommandPlan and tighten the visual boundary.
5. Add a claim-level grounded-answer judge for Web Search.

Do not tune Router-SLM latency first: its P95 was 1.327 seconds and is not the
dominant cause of this release failure.
