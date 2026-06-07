# Reno Memo RAG — Expert Evaluation Plan

## Purpose

Demonstrate, to a domain expert (a Reno City Council subject-matter expert),
how grounding a Claude Code-built RAG system in published research changes the
quality and accuracy of its output, compared to a standard "vanilla" RAG system
with no research grounding.

This is a qualitative, side-by-side comparison — not a benchmark that produces
a single score. The expert reads paired outputs from the same prompt and judges
them against their own knowledge of what is true about Reno city governance.

---

## What is being tested

Two separate experiments. They test different things and should not be merged.

### Experiment A — structured data
Both systems start from the finished CityThread spreadsheet. Extraction is
already done and held constant. This isolates the effect of research grounding
on **retrieval and reasoning** — how the system finds relevant memos and how it
reasons across them.

### Experiment B — raw PDFs
Neither system receives the spreadsheet. Both fetch the raw council memo PDFs
from their public URLs and perform their own parsing and extraction. This tests
the effect of research grounding on **the entire pipeline**, including
extraction — which is what most of the research corpus is actually about.

### Why both, and what to expect
Most of the research (entity normalization, coreference resolution, bounded
relation vocabulary, sequential extraction, memo-level chunking) governs
extraction quality. The spreadsheet already did all of that by hand. So:

- **Experiment A** likely shows a *modest* difference. Both systems inherit
  clean, normalized, human-curated data. The research-grounded system should
  still reason better across documents and link related memos more reliably,
  but the vanilla system is not starting from garbage.

- **Experiment B** likely shows a *larger* difference. Here the research-grounded
  system builds a structured knowledge base from messy source documents, while
  the vanilla system retrieves text fragments. This is where the research earns
  its keep.

The contrast between A and B is itself a primary finding. Frame it honestly:
you are not fine-tuning one system against another — you are contrasting two
philosophies. In Experiment B especially, "a system that builds a structured
knowledge base" vs. "a system that retrieves text fragments" are nearly
different species. Name that plainly to the expert; it is more credible than
pretending the comparison is apples-to-apples.

---

## The four systems

| Label | Experiment | Data source | Research grounding |
|-------|-----------|-------------|--------------------|
| A-research | A | Spreadsheet | Full (CLAUDE.md + ARCHITECTURE.md) |
| A-vanilla  | A | Spreadsheet | None |
| B-research | B | Raw PDFs    | Full |
| B-vanilla  | B | Raw PDFs    | None |

### The vanilla baseline (A-vanilla and B-vanilla)
Truly standard, industry-default RAG. No research-derived design at all:
- Chunk documents at a fixed token size (e.g. 512 tokens, fixed overlap)
- Embed every chunk with an off-the-shelf embedding model
- At query time: embed the query, retrieve top-k chunks by cosine similarity
- Stuff the retrieved chunks into the prompt with a generic instruction
  ("Answer the question using the context below")
- No entity normalization, no relationship graph, no bounded relation vocab,
  no sequential extraction, no structured reasoning prompt, no thread/flag
  awareness, no citation requirement

For B-vanilla, "documents" means the raw PDF text — chunked and embedded with
no extraction step at all. The LLM sees raw chunks of memo text, not structured
fields.

### The research system (A-research and B-research)
The system built per ARCHITECTURE.md and constrained by CLAUDE.md. For
Experiment B, it runs the full extraction pipeline (normalization, coreference,
sequential bounded-vocab extraction, memo-level chunking) on the raw PDFs before
any retrieval.

### What must be held constant across each pair
- Same Claude model and version for generation in both systems of a pair
- Same prompts (see prompt set below)
- Same source documents
- Same output format presented to the expert

The *only* difference within a pair is the research grounding. Document the
exact model version, embedding model, chunk size, and k value in the run log so
the comparison is reproducible.

---

## The prompt set

Write 10–15 prompts before running anything. They must be real questions a
council staffer or informed citizen would ask, and they must require
cross-document reasoning — not single-memo lookups, which both systems handle
trivially and which therefore reveal nothing.

Good prompt shapes:
- "What is the current status of the parking revenue problem, and what is
  blocking it?" (requires linking JAN-003, FEB-018, APR-004)
- "Are code enforcement cases rising, and is the new citation policy the cause?"
  (requires the weekly reports plus MAR-002, and a causal judgment)
- "Which long-running issues have seen no progress across the quarter?"
  (requires recognizing stalled threads)
- "What funding cliffs are approaching and what depends on them?"
- "Where do the memos contradict each other or show competing priorities?"

Avoid:
- Single-memo factual lookups ("when was the IPS agreement approved")
- Questions whose answer isn't knowable from the memos (both systems will
  hallucinate or refuse, revealing nothing about the research)

Lock the prompt set before any run. Use the identical set for all four systems.

---

## Ground truth

The expert is the ground truth. This is the strength of the design — you are
not asking an LLM to grade an LLM. You are asking a human who knows Reno
governance to judge accuracy against reality.

Two layers of reference are available:

1. **The expert's own knowledge** — the primary standard. The expert reads each
   output and judges whether it is accurate, complete, and correctly reasoned.

2. **The spreadsheet's curated analysis** — the 12 issue threads, 10 flags, and
   14 decisions are human-curated cross-document patterns. Use these to *write*
   prompts and to give the expert a reference point, but the expert's judgment
   overrides them.

Do not pre-write "correct answers" yourself. The expert supplies the standard.

---

## What the expert sees per prompt

For each prompt, present the two outputs **side by side, blinded**. Strip any
label that reveals which system is which. Randomize left/right per prompt so the
expert can't learn a position pattern.

### Experiment A output package
- The prose answer
- The source memos cited (global_ids + titles)

### Experiment B output package
- The prose answer
- The source memos cited
- **The extracted data behind the answer** — the structured representation each
  system built from the raw PDFs (entities, relationships, fields). This is
  essential for B: it lets the expert see *why* one answer is better, not just
  *that* it is. A fragmented or duplicated knowledge base is visible here even
  when the prose answer looks superficially fine.

---

## What the expert is asked to do

Do not ask for a score. Ask for structured qualitative judgment. For each
blinded pair, the expert answers:

1. **Which output is more accurate to what actually happened in Reno?**
   (Left / Right / Tie) — with a one-line reason.

2. **Where is each output wrong, incomplete, or misleading?**
   Free text. This is the most valuable data you collect.

3. **Does either output invent, conflate, or misattribute anything?**
   Hallucination and entity confusion are exactly what the research is meant to
   prevent — flag them explicitly.

4. **For Experiment B only: is the extracted data behind each answer sound?**
   Are the same entities split into duplicates? Are relationships wrong or
   missing? Is anything fabricated?

After all pairs are judged, unblind and ask the expert a synthesis question:
**now that you know which system used the research, what patterns do you see in
how they differ, and what would you change?** This is where you get the "what we
need to change" signal you're after.

---

## Run protocol

1. Lock the prompt set (10–15 prompts).
2. Build all four systems. Log exact model, embedding model, chunk size, k.
3. Run every prompt through all four systems. Save raw outputs verbatim — never
   edit a system's output before showing the expert.
4. Assemble blinded, randomized side-by-side packages (A pairs and B pairs).
5. Expert reviews A pairs and B pairs, answering the four questions per pair.
6. Unblind. Run the synthesis question.
7. Write up: per-prompt notes, recurring failure patterns, and the A-vs-B
   contrast.

---

## Honesty guardrails

These protect you from running an experiment that looks rigorous but isn't.

- **Blind the outputs.** If the expert knows which system is "the good one,"
  their judgment is contaminated. Strip labels, randomize position.
- **Never edit a system's output** before the expert sees it. Show what the
  system actually produced, warts included.
- **Report ties and losses.** If the research system loses or ties on some
  prompts, that is a finding, not a failure to hide. An expert will trust the
  whole evaluation more if it admits where the research didn't help.
- **Expect A to be modest.** If Experiment A shows little difference, that is
  the correct and expected result given the spreadsheet already encodes the
  extraction work. Do not treat a small A difference as a problem to engineer
  away. The story is in the A-vs-B contrast.
- **Don't over-claim from a small prompt set.** With 10–15 prompts this is a
  qualitative demonstration, not statistical proof. Say so. The value is the
  expert's specific, reasoned observations — not a win count.

---

## What this evaluation produces

- A set of paired, expert-annotated outputs showing concretely how the two
  approaches differ on real questions
- A list of specific failure modes in each system, in the expert's own words
- A clear read on whether research grounding matters more for extraction
  (Experiment B) than for retrieval and reasoning over already-clean data
  (Experiment A)
- A prioritized "what to change" list grounded in expert judgment rather than
  self-assessment