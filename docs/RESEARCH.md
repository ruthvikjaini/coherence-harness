# Research notes — checked 28 October 2026

All sources below were read on their primary pages (arXiv abstract
pages, release listings) on 28 October 2026. Nothing in this project
is copied from a paper's code repository; the implementation is
independent, and the simulation numbers in the README are this
repository's own measurements.

## Primary sources used

### 1. Heng, "Global Coherence: When Every Agent Is Right and the Team Is Still Wrong"

- Author: Xin Heng. arXiv:2610.02036, submitted 1 October 2026,
  version 2 on 15 October 2026.
  https://arxiv.org/abs/2610.02036v1
- What it says: locally valid agent decisions can jointly produce an
  invalid result — a failure of shared state, not intelligence. The
  Observation-Aliasing Impossibility Theorem bounds what any policy
  can guarantee when indistinguishable worlds need different actions
  (best randomised worst-case success 1/k for k such worlds). The
  runtime semantics are X = (H, C, G, F; D): topology of overlapping
  scopes, categories of state-changing actions, reversible
  translations, a sheaf test for whether local views glue, and a
  minimal history of state-altering events. "Models propose; the
  harness owns shared state and governs commit."
- Reported results (the paper's, not this repo's): revision benchmark
  40/40 with the deciding event visible, 12–17/40 (chance 1/3) when
  hidden, 40/40 again with one authoritative fact restored; TeamBench
  budget exceeded in 5/5 ordinary runs, 4/5 with a visible live
  count, 0/5 with commit enforcement; tau2-bench Telecom
  current-state checks 0.07 after silent reverts vs harness 1.00.
- What was taken: the harness-owns-state design, the three commit
  modes (blind / visible / enforce), aliasing and gluing checks,
  stale-version rejection, silent-revert detection by re-reading
  current state, and the scenario shapes (shared budget, hidden
  deciding fact, silent revert, unit overlap).

### 2. Sun et al., "What Effort Level Should I Choose? On the Economics of Reasoning Effort in LLM Agents"

- Authors: Kaiser Sun, Yongchan Kwon, Zain Hasan, Shang Zhu,
  Kaitlyn Zhou, Federico Bianchi. arXiv:2610.34491, submitted
  25 October 2026. https://arxiv.org/abs/2610.34491
- What it says: reasoning effort is a credence good — buyers cannot
  tell whether the computation they paid for was necessary. Higher
  effort raises aggregate accuracy but frequently fails tasks lower
  effort solved; on tasks every level solves, the highest effort
  costs up to 42x the lowest; higher effort changes agent behaviour
  (more self-verification, more searching) without necessarily
  changing outcomes. Starting at the lowest effort and escalating
  only after a verified failure matches or improves on fixed maximum
  effort at lower cost.
- What was taken: the escalation policy (start low, escalate only on
  verified failure), the five-level ladder, and the 42x cost ratio
  as a parameter. The simulation's non-monotonic solving sets mirror
  the paper's finding that higher effort does not preserve
  lower-effort successes. No claim is made that the simulated cost
  ratios measure any real model.

## Companion sources checked

- Ding et al., "Agentic Data Engineering for LLMs: System Design and
  a Controlled Empirical Study", arXiv:2610.14238, 9 October 2026.
  Agents improve data-engineering strategies from experimental
  feedback, but later in-loop gains do not always improve held-out
  generalisation. Checked as an alternative topic; rejected because
  its core loop needs real model training to reproduce, and its
  "in-loop vs held-out gap" lesson is already covered here by the
  visible-vs-enforce distinction.
- AgenticBBO-Bench coverage (LAMDA group, arXiv October 2026):
  LLM agents vs classical black-box optimisers across five domains.
  Rejected: needs expensive black-box evaluations (database tuning,
  chip placement) that are not CPU-reproducible here.
- TRL v1.16.0 (15 October 2026, AWS Trainium support, AsyncGRPO
  prefix-tree speedup) and vLLM v0.32.0 (18 October 2026, structured
  decisions, low-precision KV caches). Checked for scale-up context
  only; this project is a coordination library and needs neither.
- Microsoft Agensh (October 2026, decentralised harness scaling to
  1,024 coding agents). Checked as related work: it removes the
  central orchestrator, which is the opposite architectural bet from
  Heng's harness-owned state. Cited here as a contrast, not used:
  at very large scale the orchestrator itself becomes a bottleneck,
  and a production deployment would need to decide where the
  coherence boundary sits. This repo implements the small-team,
  single-harness end of that trade-off.

## Rejected ideas

- A GRPO/RLVR trainer: Day 1 already covers it.
- Personalised test-time scaling / controller discovery: Day 2
  already covers it.
- Hallucination detection over live LLM output: needs model calls
  and a labelled corpus; not reproducible CPU-only without paid APIs.
- Benchmark decontamination via training-data detection: needs
  model weights and training corpora; not CPU-reproducible.
