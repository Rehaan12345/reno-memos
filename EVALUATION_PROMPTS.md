# Reno Memo RAG — Evaluation Prompt Set

Use the identical set for all four systems (A-research, A-vanilla, B-research,
B-vanilla). Lock this list before any run. Present outputs blinded and
randomized per the EVALUATION_PLAN.

Each prompt below has two parts:
- **Prompt** — exactly what gets sent to every system, verbatim.
- **Reference key** — for YOUR use only. Never shown to the expert. Lists the
  memos/threads a complete answer should draw on, and the cross-document move
  the prompt is designed to force. Use it to spot when a system misses.

---

## Section 1 — Stalled / unresolved issues
Tests whether a system recognizes that an issue persists unchanged across
months. Vanilla retrieval tends to return the most recent or most keyword-dense
memo and miss the "no movement over time" pattern.

### Prompt 1
> What is the current status of the parking revenue recovery effort, and what
> is the single biggest thing blocking it?

**Reference key:** Thread "Parking Revenue Recovery" — JAN-003, FEB-018, APR-004.
The blocker is the Nevada DMV holds, unresolved since June 2025 (flagged High
priority, 5+ months no movement). A strong answer names the DMV hold as the
bottleneck and notes it has persisted across all three memos. Weak answer just
summarizes parking revenue figures from one memo.

### Prompt 2
> Which long-running issues have shown no meaningful progress across the
> January–April period? Name them and explain what is stuck.

**Reference key:** Flags with "no change"/"pending — no movement" status:
Seniors EngAGED funding cliff (JAN-008, APR-010 — identical status 4 months
apart), Nevada DMV holds (JAN-003, FEB-018, APR-004). Forces recognition of
stasis across documents. Vanilla systems struggle — "no change" is the absence
of new content, which keyword retrieval doesn't surface well.

### Prompt 3
> Is there a funding cliff approaching for any city program, and what happens
> if nothing is done?

**Reference key:** Seniors EngAGED ARPA funding — Dec 2026 cliff (JAN-008,
APR-010). No successor funding identified across 4 months of tracking. 1,720
participants Q4 2025 → 1,256 Q1 2026. Program ceases end of 2026 without action.

---

## Section 2 — Causal / interpretive judgments
Tests whether a system can hold two data series together and reason about
cause, rather than report them separately.

### Prompt 4
> Code enforcement cases have been rising. Is the new citation policy
> responsible for the increase, or was the trend already underway?

**Reference key:** Flag "Code enforcement cases nearly 4× in 16 weeks" —
33 cases (Jan 2) → 125 (Apr 23). New daily citation policy effective Mar 3
(MAR-002). The key insight: the rising trend *predates* the policy, so the
policy cannot be the sole cause. Weekly report memos + MAR-002 + the Code
Enforcement Weekly Cases metric series. Tests resistance to the easy (wrong)
causal story.

### Prompt 5
> What does the homelessness and outreach data tell us about whether the city's
> approach is working? Be specific about tensions in the numbers.

**Reference key:** Thread "Homelessness & Outreach" — FEB-008, FEB-009, MAR-003,
MAR-004, MAR-018, APR-002, APR-014, APR-015. Tension: enforcement metrics
(arrests highest of year in Mar at 96, camping in parks +113% MoM) rising
alongside service requests, while housing placements are inconsistent month to
month (9→6→11→4). A good answer names the tension between rising enforcement and
inconsistent housing outcomes. Multiple Clean & Safe metric series support this.

### Prompt 6
> The local economy — is it improving or weakening? The memos seem to point in
> different directions.

**Reference key:** Thread "Economic Conditions" — JAN-014, MAR-001, MAR-023.
Mixed picture: wages up, inflation down, tourism up (Jan 2026 strongest at
307K), unemployment low and falling — BUT consumer confidence weakened (CCI
84.5, lowest since May 2014), rents rising 12 consecutive months, 2 WARN notices
(244 jobs) in April. A strong answer holds the contradiction rather than
picking a side. Several economic metric series support this.

---

## Section 3 — Cross-department / connection prompts
Tests the relationship graph specifically. These require linking memos from
different departments that a keyword search would not co-retrieve.

### Prompt 7
> Are there any cases where one department's decision depends on or affects
> another department's work? Walk me through one.

**Reference key:** Tests relationship-graph traversal. Candidates: parking
(City Manager's Office) depends on Nevada DMV / Dept of Public Safety (state);
housing affordability (HAND) connects to homelessness PSH units (FEB-014
Hi-Way 40). Vanilla systems with no relationship layer will struggle to surface
a genuine cross-department dependency.

### Prompt 8
> What's happening with affordable housing, and is the pipeline keeping pace
> with the rising rents?

**Reference key:** Thread "Housing & Affordability" — JAN-006, FEB-014, FEB-015,
APR-008 — linked to the rents-rising flag (JAN-014, MAR-001, MAR-023). Two Feb
wins: Hi-Way 40 (28 PSH units) + NAHA fee waivers ($1.25M, 703 units). But the
answer should connect this to rents rising 12 straight months and judge that
the pipeline is insufficient to offset at scale. Forces a link between a housing
thread and an economic flag.

### Prompt 9
> Which technology systems is the city replacing or upgrading, and which one is
> the most urgent?

**Reference key:** Thread "Technology Modernisation" — MAR-005 (ERP), MAR-010
(Hexagon CAD/RMS). ERP is more urgent: Tyler New World has payroll calculation
errors (FLSA overtime), procurement not yet started, Council authorization
pending (Medium flag). Hexagon is on track for late 2026 go-live. A good answer
ranks ERP above Hexagon and explains why.

---

## Section 4 — Contradiction / competing-priority prompts
The hardest class. Tests whether a system can identify where memos disagree or
where two valid goals compete.

### Prompt 10
> Where do the memos reveal competing priorities or decisions that sit in
> tension with each other?

**Reference key:** Open-ended — tests synthesis. Candidates: Lear Theater
(FEB-002, MAR-012) has two distinct pending decisions in tension — operational
tree removal (safety, near-term) vs. strategic building future ($18–22M
renovation). Homelessness enforcement vs. housing. There is no single "right"
answer; judge whether the system surfaces a real tension with evidence vs.
inventing one.

### Prompt 11
> The Lear Theater — what decisions are pending and what makes this complicated?

**Reference key:** Thread "Lear Theater" — FEB-002, MAR-012. Two distinct
decisions: (1) operational — two American Linden trees (largest in Reno) flagged
for removal by end of April, safety risk; (2) strategic — building future,
$18–22M renovation vs. $1.6M near-term stabilization, Council action requested
Apr 8. High community interest (180 attendees, 441 survey responses). A strong
answer separates the two decisions rather than conflating them.

### Prompt 12
> Has the waste management rate increase been finalized, and what does it mean
> for residents?

**Reference key:** Thread "Waste Management" — FEB-011, MAR-008, MAR-009,
APR-006. Franchise fee increase 8% → 14% approved (FEB-009 decision), reflected
in April billing — residential 96-gal cart $25.20 → $28.38 effective April 1
(MAR-009). Composting feasibility analysis still in progress. Tests whether the
system connects the decision to its concrete resident impact.

---

## Section 5 — Coverage / recall prompts
Tests whether a system can assemble a complete picture across many memos, where
missing one is a visible failure.

### Prompt 13
> Give me a complete picture of every governance and appointments issue in the
> quarter — vacancies, term expirations, all of it.

**Reference key:** Thread "Governance & Appointments" — JAN-002, MAR-015,
APR-013. Persistent vacancies: Access Advisory Board (6 seats across all three
vacancy reports), Ward 6 NAB consistently understaffed, Charter Committee (9),
Senior Residents Advisory Board (4). RTAA Board appointments (MAR-015), HRC +
Ward 2/4 NAB terms expiring Apr 30 (APR-013). Tests recall — easy to return one
vacancy report and miss the others.

### Prompt 14
> What are all the high-priority issues the city should be watching right now?

**Reference key:** The three High-priority flags: code enforcement 4× increase,
Seniors EngAGED funding cliff, Nevada DMV holds. A strong answer returns all
three with their signals. Tests whether the system can surface the flag layer or
reconstruct it from memos. Vanilla systems with no flag awareness must rebuild
this from scratch and will likely miss at least one.

### Prompt 15
> Summarize the most significant decisions Council made this quarter and who
> they affect.

**Reference key:** Decisions table — 14 entries. Notable: Waste Management fee
increase (FEB-009), $4.2M Community Project Funding (FEB-005), Virginia Range
Horse Fencing $686K (FEB-006), Trego Battery Storage 200MW CUP (MAR-011), NAHA
housing awards (FEB-014, FEB-015), no sewer fee increase (APR-009). Tests
whether the system surfaces the decisions layer and attributes impact correctly.

---

## Expert scoring sheet (one per blinded pair)

Fill one of these per prompt. The expert never sees the reference key above.

```
Prompt #: ____    Experiment: A / B

                          ┌─────────────┬─────────────┐
                          │  OUTPUT 1   │  OUTPUT 2   │
                          │  (left)     │  (right)    │
┌─────────────────────────┼─────────────┼─────────────┤
│ More accurate to what   │             │             │
│ actually happened?      │   ☐         │   ☐    ☐ tie │
├─────────────────────────┼─────────────┴─────────────┤
│ One-line reason:        │                            │
├─────────────────────────┼────────────────────────────┤
│ Where is each output    │  Output 1:                 │
│ wrong, incomplete, or   │                            │
│ misleading?             │  Output 2:                 │
├─────────────────────────┼────────────────────────────┤
│ Does either invent,     │  Output 1:                 │
│ conflate, or            │                            │
│ misattribute anything?  │  Output 2:                 │
├─────────────────────────┼────────────────────────────┤
│ (Exp B only) Is the     │  Output 1:                 │
│ extracted data behind   │                            │
│ the answer sound?       │  Output 2:                 │
│ Duplicate entities?     │                            │
│ Wrong/missing links?    │  Output 2:                 │
│ Fabrications?           │                            │
└─────────────────────────┴────────────────────────────┘
```

---

## Synthesis questions (asked once, after all pairs, post-unblinding)

1. Now that you know which system used the research grounding, what consistent
   patterns do you see in how the two approaches differ?

2. Which differences matter most for someone actually using this to understand
   Reno governance?

3. What is each system getting wrong that we most need to fix?

4. (Experiment B) Did the structured-extraction system produce a knowledge base
   you would trust more than raw retrieval? Where did its extraction help, and
   where did it still fall short?