# Forward Deployed Engineering — Basic, Intermediate and Advanced

Forward deployed engineering means working inside a customer's team and building the software that makes their problem go away. This course teaches that job from first principles: how to find the real problem, scope a small proof of concept, connect it to the customer's systems, and show progress in a way non-engineers trust. The Basic level takes you from "what does this role do?" to one working proof of concept for one customer workflow. The Intermediate level makes that proof of concept safe to hand to a customer: evals, security, deployment into a restricted network, observability, runbooks, cost budgets and agent workflows. The Advanced level takes that proof of concept to production: handover to the customer's team, multi-tenancy, zero-downtime change, feeding field lessons back to product, security evidence, cost, failure drills and one full customer delivery.

The running example is **Basket Bazaar**, a fictional grocery company whose customers report delivery problems (missing, wrong or late items). You build a small triage tool for those reports.

## Who it's for

Software engineers who are moving toward customer-facing delivery, solutions engineers, and consultants who build AI or software features for a client. No prior customer-delivery experience is assumed. You should be comfortable reading and running Python.

## Prerequisites

- Python 3.12 and basic Python (functions, dictionaries, files, running a script).
- Basic HTTP: what a request and a JSON response look like.
- Nothing else for Basic. Intermediate assumes the Basic level (or equivalent): a working proof of concept and the terms it uses.
- Intermediate lessons 14–16 and 20 use Docker (Docker Desktop or Docker Engine with Compose). Without Docker these cells are skipped, and the recorded outputs in the notebook still show what you would see.
- Advanced assumes the Intermediate level (or equivalent): evals, security, deployment and observability. Advanced lessons 24, 28, 31 and 32 use Docker in the same way.

## Setup

From the course folder:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m ipykernel install --user --name tut-forward-deployed-engineering-15h
```

Then start Jupyter (`.venv/bin/jupyter notebook notebooks/`) or open the notebooks in VS Code and pick the `tut-forward-deployed-engineering-15h` kernel.

**Keys (optional).** Lessons 06, 09, 11, 12, 18, 19, 20, 28 and 32 call a model. Their model calls are recorded and replayed, so they run with no key. To use a live model, copy `.env.example` to `.env` and fill in `GOOGLE_CLOUD_API_KEY` (or `GOOGLE_CLOUD_PROJECT` and `GOOGLE_CLOUD_LOCATION`). `.env` is never committed.

## How to run

Run the notebooks in order. Each lesson builds on the one before it. Every lesson ends with a checkpoint or a "Key terms" list, and the answers to each Try-it are in a hidden `solution` cell.

## What `TUT_ENABLE` does

Cells that need something this machine may not have are tagged (`needs-llm`, `needs-download`, `needs-docker`, `needs-k8s`, `needs-cloud`, `needs-gpu`, `slow`) and print a one-line notice instead of running. To run them, set the tags, for example `TUT_ENABLE=llm`. Basic needs only `needs-llm` (replayed without a key). Intermediate also has `needs-docker` cells in lessons 14, 15, 16 and 20, and Advanced in lessons 24, 28, 31 and 32; they run with `TUT_ENABLE=docker` on a machine with Docker. `TUT_ENABLE=all` runs everything you have set up.

## Lessons

| # | Lesson | Level | Priority | Needs |
|---|---|---|---|---|
| 01 | [Why forward deployed engineering, and when you don't need it](notebooks/01_why-forward-deployed-engineering.ipynb) | L1 | core | none |
| 02 | [Finding the real problem: discovery and decomposition](notebooks/02_discovery-and-decomposition.ipynb) | L1 | core | none |
| 03 | [Scoping a proof of concept and a two-week sprint](notebooks/03_scoping-the-poc-sprint.ipynb) | L1 | core | none |
| 04 | [Integrating with a customer's API: auth, pagination, retries, idempotency](notebooks/04_integrate-a-customer-api.ipynb) | L1 | core | none |
| 05 | [Ingesting customer data: files, pipelines and deduplication](notebooks/05_pipelines-and-deduplication.ipynb) | L1 | core | none |
| 06 | [A customer workflow with structured output and tool calling](notebooks/06_structured-output-and-tool-calling.ipynb) | L1 | core | model (replayed) |
| 07 | [Explaining progress to non-engineers and running a live demo](notebooks/07_explaining-progress-and-demos.ipynb) | L1 | core | none |
| 08 | [Timelines, risk and success metrics for a customer engagement](notebooks/08_engagement-delivery-basics.ipynb) | L1 | professional | none |
| 09 | [Checkpoint: a working proof of concept for one customer workflow](notebooks/09_basic-poc-checkpoint.ipynb) | L1 | core | model (replayed) |

**Essentials path** (core lessons only): 01–07 and 09. **Professional path** adds 08.

### Intermediate

| # | Lesson | Level | Priority | Needs |
|---|---|---|---|---|
| 10 | [Why customer AI needs evals: failures you can't see](notebooks/10_why-evals-for-customer-ai.ipynb) | L3 | core | none |
| 11 | [Build an eval set from real failures](notebooks/11_eval-set-from-real-failures.ipynb) | L3 | core | model (replayed) |
| 12 | [Grading outputs with code, model and human graders](notebooks/12_graders-code-model-human.ipynb) | L3 | professional | model (replayed) |
| 13 | [Authentication, secrets and least privilege in a customer system](notebooks/13_enterprise-auth-and-secrets.ipynb) | L3 | core | none |
| 14 | [Deploying into a customer environment with Docker Compose](notebooks/14_customer-environment-compose.ipynb) | L3 | core | Docker |
| 15 | [Deploying into a restricted network: private networks and an egress proxy](notebooks/15_restricted-network-lab.ipynb) | L3 | core | Docker |
| 16 | [Observing a customer system: logs, traces and metrics](notebooks/16_observability-logs-traces-metrics.ipynb) | L3 | core | Docker |
| 17 | [Runbooks and incident response for a customer deployment](notebooks/17_runbooks-and-incidents.ipynb) | L3 | core | none |
| 18 | [Cost, latency and caching: budgets for a customer's AI features](notebooks/18_cost-and-latency-budgets.ipynb) | L3 | core | model (replayed) |
| 19 | [Agent workflows for a customer: tools, MCP servers and guardrails](notebooks/19_agent-workflows-tools-and-mcp.ipynb) | L3 | professional | model (replayed) |
| 20 | [Checkpoint: an evaluated, deployable proof of concept](notebooks/20_intermediate-checkpoint.ipynb) | L3 | core | Docker, model (replayed) |

**Essentials path** (core lessons only): 10, 11, 13–18 and 20. **Professional path** adds 12 and 19.

### Advanced

| # | Lesson | Level | Priority | Needs |
|---|---|---|---|---|
| 21 | [From proof of concept to production: what changes](notebooks/21_from-poc-to-production.ipynb) | L5 | core | none |
| 22 | [Handover: documentation and enabling the customer's team](notebooks/22_handoff-docs-and-enablement.ipynb) | L5 | professional | none |
| 23 | [Per-customer configuration and multi-tenancy](notebooks/23_multi-tenant-customer-config.ipynb) | L5 | professional | none |
| 24 | [Zero-downtime changes: rolling upgrades and migrations](notebooks/24_zero-downtime-rollout.ipynb) | L5 | professional | Docker |
| 24a | [Long batch jobs: restart, reconcile and finish on time](notebooks/24a_long-batch-jobs-restart-and-reconcile.ipynb) | L5 | professional | Docker |
| 25 | [Productizing field work: reusable components, custom vs core](notebooks/25_productizing-field-work.ipynb) | L5 | core | none |
| 26 | [Feedback loops to product: writing a field report](notebooks/26_field-feedback-to-product.ipynb) | L5 | professional | none |
| 27 | [Security reviews and compliance evidence](notebooks/27_security-reviews-and-compliance.ipynb) | L5 | core | none |
| 28 | [Failure drill: a model provider goes down](notebooks/28_model-provider-failure-drill.ipynb) | L5 | professional | Docker, model (replayed) |
| 29 | [Cost engineering: unit economics for a customer deployment](notebooks/29_cost-unit-economics.ipynb) | L5 | professional | none |
| 30 | [Ambiguity and the business case: saying no and saying what it is worth](notebooks/30_ambiguity-and-the-business-case.ipynb) | L5 | professional | none |
| 31 | [Delivering one customer deployment end to end](notebooks/31_end-to-end-customer-delivery.ipynb) | L5 | core | Docker |
| 32 | [Final checkpoint: the customer delivery drill](notebooks/32_final-delivery-drill.ipynb) | L5 | core | Docker, model (replayed) |

**Essentials path** (core lessons only): 21, 25, 27, 31 and 32. **Professional path** adds 22, 23, 24, 26, 28, 29 and 30.

**Prerequisites for Advanced.** The Basic and Intermediate levels: a proof of concept, evals, security, deployment into a restricted network, observability and cost budgets. Lesson 21 names what a proof of concept lacks; the Intermediate lessons supply the parts it lacks.

**Before you start the Advanced level, set the token.** The app's `/api` routes need `TRIAGE_SERVICE_TOKEN` in the course `.env`. The course `.env` ships without it, so the app answers 503 on `/api` until you add one. The app's [GUIDE](app/GUIDE.md) explains how to make the token and where to put it.

## Build the app step by step

The course builds one real app alongside the notebooks: a local FastAPI backend with a one-page web UI. Basic adds step 1, a triage API and page. Intermediate adds step 2 (stored cases, retries and one error shape) and step 3 (service tokens, per-store limits, tracing and an eval gate). Advanced adds step 4, which runs and finishes the app with one start command and one check.

- [app/README.md](app/README.md): what the app is and how to run it.
- [app/GUIDE.md](app/GUIDE.md): the step-by-step build.

## Interview questions and projects

- Basic projects: [projects/BASIC_PROJECTS.pdf](projects/BASIC_PROJECTS.pdf)
- Intermediate projects: [projects/INTERMEDIATE_PROJECTS.pdf](projects/INTERMEDIATE_PROJECTS.pdf)
- Advanced projects: [projects/ADVANCED_PROJECTS.pdf](projects/ADVANCED_PROJECTS.pdf)
- Interview questions: [interview/INTERVIEW_QUESTIONS.pdf](interview/INTERVIEW_QUESTIONS.pdf)

Note: the question bank has 44 questions, every one approved by the interview reviewer. Only 6 of them are system design (13.6%), below the kit's 15% minimum, so it is published without that check. A system-design question on lesson 24a was rejected in review and is not included.

## Full syllabus (PDF)

[SYLLABUS.pdf](SYLLABUS.pdf) — the whole course, Basic through Enterprise, with the coverage checks.

## Industry reading

- [Building effective agents](https://www.anthropic.com/engineering/building-effective-agents) — Anthropic Engineering (Basic)
- [Designing robust and predictable APIs with idempotency](https://stripe.com/blog/idempotency) — Stripe, 2017, classic (Basic)
- [Timeouts, retries, and backoff with jitter](https://aws.amazon.com/builders-library/timeouts-retries-and-backoff-with-jitter/) — Amazon Builders' Library, 2019, classic (Basic)
- [Demystifying evals for AI agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents) — Anthropic Engineering (Intermediate)
- [Creating custom LLM judges to improve AI agent accuracy](https://www.databricks.com/en/blog/building-custom-llm-judges-ai-agent-accuracy) — Databricks (Intermediate)
- [Beyond permission prompts: making Claude Code more secure and autonomous](https://www.anthropic.com/engineering/claude-code-sandboxing) — Anthropic Engineering (Intermediate)

## Where next

Once you finish the course, these paths build on it (start any of them with `/tutorial "<path>" basic reuse:forward-deployed-engineering-15h`):

- **Forward Deployed AI Engineer / Applied AI Engineer** (role, established)
- **Generative AI Solutions Architect** (role, established)
- **Agent evaluation engineering** (discipline, growing)
- **Harness engineering** (discipline, emerging)
- **AI gateways, sandboxing and agent security** (technology, growing)
- **Site reliability engineering for AI systems** (discipline, established)

## Installed versions

Tested in a fresh venv built from `requirements.txt` on Python 3.12.13:

fastapi 0.162.0 · uvicorn 0.54.0 · pydantic 2.14.1 · httpx 0.28.1 · pytest 9.1.1 · langchain-core 1.7.0 · langchain-google-genai 4.4.2 · tenacity 9.1.4 · mcp 2.3.0 · opentelemetry-sdk 1.45.1 · scikit-learn 1.9.1 · pandas 3.1.0 · python-pptx 1.0.2 · reportlab 5.1.0

## Troubleshooting

- **`wait_exponential_jitter() got an unexpected keyword argument 'multiplier'`** — the venv has tenacity 9.1.x. The pin in `requirements.txt` is `tenacity>=8.2.3,<9.2.0` (because `langchain-google-genai` constrains it). Lesson 04 uses `initial=`, which works on that version. Do not upgrade to tenacity 9.2 without also changing the pin.
- **Docker cells skipped** — Intermediate lessons 14, 15, 16 and 20, and Advanced lessons 24, 28, 31 and 32, need Docker. Install Docker, then run with `TUT_ENABLE=docker`.
- **The app answers 503 on `/api`** — the course `.env` has no `TRIAGE_SERVICE_TOKEN`, so the app refuses `/api` calls until you add one. Make a token and put it in `.env` as the app's [GUIDE](app/GUIDE.md) explains. Never paste the token into a notebook or a commit.
- **Lesson shows "skipped" for a cell** — the cell is tagged for something this machine doesn't have. See "What `TUT_ENABLE` does".
- **Model call fails with no key** — the lesson uses its recording. If it still fails, check that `data/llm_cassettes/` is present in the course folder.
