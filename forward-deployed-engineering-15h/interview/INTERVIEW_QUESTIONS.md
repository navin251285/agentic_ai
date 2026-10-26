# Forward Deployed Engineering from First Principles to Enterprise Delivery — interview questions

44 questions at the bar used by top tech companies, from fundamentals to staff-level system design. Level = the engineering level the question is typically pitched at. Answers are not included: work them out, then check against the lessons or areas listed.

## Basic

### Fundamentals deep-dive

**1.** A customer's order API answers 429, 400, 401, 422, 502, 503 and then a read timeout. For each, say whether your client retries and how long it waits. Then explain why a POST that creates a credit needs an idempotency key even when the first call looked like a failure.  
*Mid-level (L4) · lessons 04 · Global capability centres, Top product companies, FAANG / big tech*  
Tests: Knows which HTTP failures are safe to retry, and why a write needs a stable idempotency key.
   - *Follow-up:* The 429 carries Retry-After: 30. What changes in your wait?
   - *Follow-up:* How do you build the key so two different credits for the same order item cannot share one?

**2.** A customer's integration is 3,000 lines of Python with no tests and a README that is out of date. The ops lead needs one change in three days. Describe your first day: what you read first, how you map the code, what you run on real input before you touch it, and what you would say you did not yet understand.  
*Mid-level (L4) · lessons 02 · Global capability centres, Top product companies*  
Tests: Learns an unfamiliar codebase fast, with a method and a clear list of unknowns.

### Coding

**3.** Write fetch_all(client, path) for a cursor-paginated API. It follows next_cursor until it is None, retries 429, 502, 503, 504 and transport errors up to 4 attempts with backoff, honours Retry-After, and raises at once on 401 or 422. For P pages and R retryable failures, how many requests are sent? State time and memory in terms of N total rows.  
*Senior (L5) · lessons 04 · Global capability centres, FAANG / big tech*  
Tests: Writes a bounded cursor loop with a precise retry rule, and states the request count and complexity.
   - *Follow-up:* Make it a generator so memory is O(page size). What changes for the caller?
   - *Follow-up:* The API returns the same next_cursor twice. How does your loop stop?

**4.** A customer's nightly order-lines file is 5 GB, with columns order_id, item, qty, unit and ordered_at. The pair (order_id, item) can repeat, and copies can disagree on qty. Item names vary in case and spacing (for example 'Eggs' and 'eggs '), so normalise before you compare. Write the dedup step: one pass, one row kept per key, and every disagreeing key written to a conflicts file, never resolved by guessing. State the time and memory complexity.  
*Senior (L5) · lessons 05 · FAANG / big tech, Global capability centres*  
Tests: Streams a large file, deduplicates by key without silently picking a copy, and reasons about memory.
   - *Follow-up:* The distinct keys no longer fit in RAM. What do you change, and what does it cost?
   - *Follow-up:* When quantities disagree, which copy wins, and who decides?

**5.** Write check_claim(rec, orders) for a case record with order_id, item and qty_claimed. orders maps order_id to a dict of item to qty_delivered. Return a list of problems, not an exception. The problems are: unknown order; item not on that order; qty_claimed above qty_delivered; and qty_claimed outside 1 to 20. Say what the lookup costs per case, and list the tests you would write.  
*Mid-level (L4) · lessons 06 · Global capability centres, Top product companies*  
Tests: Writes a practical validation function in the stack and tests every rule.

### Trade-offs and judgement

**6.** A customer's ops lead says, 'Our deliveries are bad,' and wants a fix by Friday. You have 45 minutes and one store's export. What do you ask in the first 20 minutes, and which three testable problems do you leave with, each with an observable, a test and an owner?  
*Senior (L5) · lessons 02 · Top product companies, FAANG / big tech, Global capability centres*  
Tests: Turns a vague complaint into testable problems with owners, and asks the right first questions.
   - *Follow-up:* The ops lead says it is obvious and cuts you off. What now?
   - *Follow-up:* Which of your three problems do you start with, and why?

**7.** Scope the two-week proof of concept for a delivery-triage request. Basket Bazaar's delivery-message export has a few thousand messages a week, and about 600 of them already carry an agent's label. The customer asks for four labels on every message (missing item, wrong item, late, damaged), a live feed from its store system and a dashboard for store managers. The sprint has 10 working days, one reserved for the demo. Give the one question the POC answers, the success criteria with baseline, target and test, what you cut and why, and a dated kill criterion.  
*Senior (L5) · lessons 03, 08 · Top product companies, Global capability centres*  
Tests: Scopes a POC: one question, numeric success criteria, a cut line, non-goals and a kill rule.
   - *Follow-up:* Day 3: the reviewed-label export and the message export have not arrived. What do you decide, and who hears it first?
   - *Follow-up:* The customer now asks for the dashboard inside the POC. What do you say?

**8.** A customer wants one LLM agent to read each refund request, decide the refund up to $500 and send the credit. Split the job between the model and plain code, and say which part must never be the model's call. Then name one case where you would tell the customer not to use an LLM at all, and why.  
*Mid-level (L4) · lessons 06 · Top product companies, Global capability centres*  
Tests: Decides which parts of a workflow suit a model and which need plain rules, using money as the test.

### Project deep-dive

**9.** Defend step 1 of the course's Basket Bazaar triage app as your own project. Why does the model never look up the order itself? What does plain code check after the model? Name one gap you would close before a customer uses it on Monday, and how you would close it.  
*Mid-level (L4) · lessons 05, 06 · Global capability centres, Top product companies*  
Tests: Defends one real design choice in the course app and names the gap before real use.
   - *Follow-up:* Why not let a vendor's agent framework run the whole loop?
   - *Follow-up:* How many model calls does one triage make, and what does each one cost?

### Behavioral

**10.** Tell me about a time you explained unfinished work to a non-technical stakeholder who wanted a yes or no. Answer in STAR form: situation, task, your actions, the result, and what you would change. Use a real example that involved a demo, open questions and a customer decision.  
*Senior (L5) · lessons 07 · FAANG / big tech, Top product companies, Global capability centres*  
Tests: Explains unfinished work honestly to a non-technical stakeholder, in STAR form.
   - *Follow-up:* What did you say when you did not know the answer?
   - *Follow-up:* How did you check the stakeholder understood what the demo did not prove?

## Intermediate

### Coding

**11.** Write a pytest regression gate. Inputs: the eval case ids, and two dicts from case id to pass or fail, one for the shipped prompt and one for the candidate. Fail when a case passed in the shipped run and fails in the candidate, when a case has no result in either run, or when the eval set has duplicate ids. Return the problems with reasons. State the time complexity for n cases.  
*Senior (L5) · lessons 11 · Global capability centres, Top product companies*  
Tests: Writes a regression gate that fails loudly on missing or duplicate results, and states its complexity.
   - *Follow-up:* A waiver lets the team accept one named regression. How does the gate record it, and when does it expire?
   - *Follow-up:* The eval file is empty. Should the gate pass or fail, and why?

**12.** Implement a cache for a support feature with three limits: max_entries, max_total_size in characters, and ttl_seconds, with the clock passed in so tests need no waiting. get and put are O(1) on average. A value larger than max_total_size is refused. An expired entry is a miss. The key includes the tenant and the prompt version. State the complexity and the tests you need.  
*Senior (L5) · lessons 18 · FAANG / big tech, Top product companies, Global capability centres*  
Tests: Implements an LRU cache with three limits, and states its complexity and edge cases.
   - *Follow-up:* Two threads call put at the same time. What breaks, and what do you add?
   - *Follow-up:* Three worker processes share the cache. Is an in-process cache still the right tool?

**13.** Write class RateLimiter(max_calls, window_s, clock) for a client that must never send more than max_calls requests in any window_s-second window. clock is a function that returns seconds as a float and is passed in, so tests need no waiting. acquire() returns True if a call may go now and records it, otherwise False. Use a sliding log. State the time and memory complexity per call. Handle max_calls of 1, a call exactly window_s after the oldest recorded call, and a burst that fills the window at one instant.  
*Senior (L5) · lessons 04, 18 · FAANG / big tech, Global capability centres*  
Tests: Writes a sliding-window rate limiter with an injected clock, states its cost and its boundary behaviour.
   - *Follow-up:* Your 200 workers each hold their own limiter. What does the customer's API see, and what do you change?
   - *Follow-up:* The API answers 429 with a Retry-After header. Where does that check go relative to acquire()?

### Debugging

**14.** A code review flags this in a customer-facing service: claims = jwt.decode(token, options={"verify_signature": False}), then if "credits:write" in claims.get("scope", ""): write_credit(). The customer's tokens are RS256 and the public key is in config. Explain what a crafted token can do against this code. Write the failing test: what token does it send to POST /credits, what must the API answer, and what must be true of write_credit()? Then give the fix. Last, say what a 401 and a 403 from the customer's API each tell you.  
*Senior (L5) · lessons 13 · Global capability centres, FAANG / big tech*  
Tests: Finds an unverified-token bug, writes the test that shows it, fixes it in order, and reads 401 and 403 correctly.

**15.** A release of the triage service reads its secret setting name on the first request, not at start-up. After the deploy on the customer's Compose host, the container stays up, /health answers ok, the deploy's up --wait passes, and every triage request returns 500. Why did the health wait pass, and how do you find the cause from the container logs? Then give the fix, the change that stops the next release from shipping the same gap, and the one-command rollback the change board can run. The image tag comes from TRIAGE_TAG.  
*Mid-level (L4) · lessons 14 · Global capability centres, Top product companies*  
Tests: Diagnoses a config failure that a health check missed, and plans a safe rollback with pinned tags.

**16.** A customer says triage was slow for an hour yesterday. p95 for /triage went from 0.4 s to 9 s for 60 minutes. Request rate was flat. About 7% of triage requests in that hour were retried, and the retried requests were the slow ones. The trace of one slow request shows 8 s in the customer API span. You have a metric of requests and latency by route, structured logs with a request id, and a trace for each call. What do you check next, and what can the data not tell you?  
*Senior (L5) · lessons 04, 16 · Global capability centres, FAANG / big tech*  
Tests: Reads metric and trace data to choose the next check, separates retry waits from the customer's time, and names what the data cannot show.

**17.** After a deploy, triage answers normally for about 90 minutes, then every call to the customer's API fails with 'pool timeout' until the container restarts. Open connections rise by about one a minute while the request rate stays flat. The helper that calls the customer's API creates a new HTTP client for each call and closes the response only on the success path. What do you check first, what do you change, and how do you prove the fix before the next release?  
*Senior (L5) · lessons 04, 16 · Global capability centres, FAANG / big tech*  
Tests: Traces a connection leak from a metric trend to the error path, and proves the fix with a repeatable test.
   - *Follow-up:* The leak only shows up when the customer's API returns 429 at night. How do you reproduce it?

### System design

**18.** Design authentication for a customer's order API that your triage service calls every few seconds. Security forbids shared passwords and wants one identity per integration, least-privilege scopes and no secret in code. Give the token flow, the scopes for a reader and a credit writer, the token lifetime and where the client secret lives.  
*Senior (L5) · lessons 13 · Global capability centres, Top product companies, FAANG / big tech*  
Tests: Designs service-account authentication with least privilege, token lifetime and secret rotation.
   - *Follow-up:* A support agent must approve each credit through the customer's SSO. Where does the human's identity fit?
   - *Follow-up:* A client secret shows up in a log file. Walk through the first hour.

**19.** A customer's security team runs the triage service on a network with no route to the internet, and the model API is outside. Design the path from the service to the model: how the service reaches the model through the egress proxy, what the customer allows and logs, and the test that proves a direct call fails. Then name one NO_PROXY entry that, left out, produces an error that points at the wrong place, and say what the caller sees.  
*Senior (L5) · lessons 14, 15 · Global capability centres, FAANG / big tech*  
Tests: Designs a locked-down network path to an external model, with a tested allowlist.
   - *Follow-up:* The model vendor moves to a new hostname next quarter. What breaks, and what changes?
   - *Follow-up:* The customer adds a second region with the same rules. What is identical, and what is per region?

### Production and scale

**20.** A new triage prompt must ship before a Friday freeze. The gate fails on one of 12 eval cases that the shipped prompt passes, though the average rose from 11.4 to 11.6 of 12. The customer's ops lead wants it live anyway. Walk through the release decision: what the gate says, who decides, what you offer the customer, and what the release note records.  
*Senior (L5) · lessons 11, 14, 20 · Top product companies, Global capability centres*  
Tests: Runs a release decision under a gate, a regression and a deadline, with the record that proves it.
   - *Follow-up:* The customer signs a waiver for the one case. How is it recorded, and when does it expire?
   - *Follow-up:* The gate ran on last month's eval file. How would the release note show that?

**21.** One customer's support feature has doubled its model bill in a month, at about 20,000 messages a day. The team's first idea is a cheaper model. Before you touch the model, what do you measure, which two changes do you make first, and what budget do you set per customer? What happens when the budget is breached?  
*Senior (L5) · lessons 18 · Global capability centres, Top product companies*  
Tests: Diagnoses cost growth from measurement before any change, and sets per-tenant budgets.
   - *Follow-up:* Case histories have grown to 200 messages. What does the context trim keep, and what does it lose?
   - *Follow-up:* How do you warn the customer about a budget breach before the invoice arrives?

### Trade-offs and judgement

**22.** Your triage feature has a 12-case eval set. The shipped prompt scores 12 of 12, and the candidate also scores 12 of 12. A teammate says equal scores mean ship the candidate, because it reads cleaner. Both score 12 of 12. What does that tell you? What do you check before you agree? Then say how you would make the set separate the two prompts: the case-by-case results you compare, and the cases near the decision boundary you add.  
*Senior (L5) · lessons 10, 11 · Global capability centres, Top product companies*  
Tests: Judges whether equal eval scores mean no change, and proposes a case set that can tell prompts apart.
   - *Follow-up:* A new case from the support queue fails on the shipped prompt and passes on the candidate. What does that tell you, and does the gate treat it differently from a case that breaks?
   - *Follow-up:* The candidate fixes two cases and breaks one that the shipped prompt passed. What does the gate do, and who signs the decision?

**23.** An agent can look up orders and propose refunds through an MCP server with six tools, one of which issues a refund. Keep it from refunding the wrong order or refunding without approval. Name the layers: which tools the model is offered, what the server checks, where a person approves, and how you test refusals without a model.  
*Senior (L5) · lessons 19 · FAANG / big tech, Top product companies*  
Tests: Keeps tool use and money movement inside layers of control, tested without a model.

**24.** Your answer cache for a customer's support replies has a 45% hit rate. This morning the customer changed its refund window, and some cached answers still quote the old one. How do you set the time to live, how do you invalidate on a policy change, and what do you tell the customer about answers served from the cache in the last hour?  
*Senior (L5) · lessons 07, 18 · Top product companies, Global capability centres*  
Tests: Sets a cache lifetime and an invalidation rule for a policy change, and a customer-facing plan.

### Project deep-dive

**25.** Defend the app's storage and retries as your own project. Each case is stored in a CSV with a dedup key built from the normalised order, item and issue. Model and transient failures are retried up to the number of tries set in TRIAGE_MODEL_ATTEMPTS, and other errors return a clear message. Why a CSV and not a database at this stage? Why this key? When do you change each choice?  
*Senior (L5) · lessons 04, 05, 11 · Global capability centres, FAANG / big tech, Top product companies*  
Tests: Defends a storage and retry design with its limits, and names the triggers to change it.

## Advanced

### Fundamentals deep-dive

**26.** Triage notes sometimes contain an email, a phone number or a card number. Describe the path from the raw note to the stored note and the audit log, and what each step must prove. Why keep a redacted copy rather than edit in place, and why must the audit log hold no note text?  
*Senior (L5) · lessons 27 · Global capability centres, Top product companies, FAANG / big tech*  
Tests: Explains a personal-data path with a test, a redacted copy and an audit log that holds no content.

### Coding

**27.** A customer's script totals quantities per item and reports 14 eggs where the true count is 45. It ignores dozens and duplicate copies. Write a characterisation test first. Pin only the totals the old code gets right (milk and bread), and record eggs as a documented known difference with its reason, without pinning 14 as correct. Then write one failing eggs test that expects 45 after the fix, and never edit the pinned values. Then refactor into a core function and a customer config, so a second customer needs only a new config.  
*Senior (L5) · lessons 25, 05 · Global capability centres, Top product companies*  
Tests: Refactors safely behind a characterisation check, and separates core from customer config.
   - *Follow-up:* Which function must never mention the customer's name, and how would you check that automatically?

**28.** Each line of the service log is JSON with request_id, event (received, model_call_start, model_call_end, replied) and ts_ms, an integer. Write a function that reads an iterable of lines, groups them by request_id, orders each group by ts_ms, and returns each request's total time from received to replied and its largest gap between two events. Lines can be out of order, a request can lack replied, and the file may not fit in memory. State the time and memory complexity.  
*Senior (L5) · lessons 16 · FAANG / big tech, Global capability centres*  
Tests: Writes a streaming group-and-order function that handles missing and out-of-order events.
   - *Follow-up:* The log file is 40 GB. How do you group it without holding everything in memory?

**29.** Write a Pydantic model StoreConfig with store_id (it must be on a known list of stores), max_qty_per_line (an integer from 1 to 100) and late_after_hours (an integer from 1 to 168). Then write three pytest tests: a valid row loads, a zero limit fails with the field named in the message, and an unknown store is rejected. Say when this check must run, why, and state the cost per row.  
*Mid-level (L4) · lessons 06, 23 · Global capability centres, Top product companies*  
Tests: Validates customer configuration at load time, with tested rules and no silent defaults.

### Debugging

**30.** A reviewer reads this route in the multi-store service: path = f'stores/{store_id}.csv', then pd.read_csv(path), and the only check is os.path.exists(path). A caller sends store_id='../orders_all', a file one level above stores/ that holds every store's lines. What does the caller get? Why does the existence check not help? Write the fix.  
*Senior (L5) · lessons 23 · Global capability centres, FAANG / big tech*  
Tests: Spots a path traversal that leaks another tenant's data, and writes the fix and its test.
   - *Follow-up:* The team strips '../' and rejects slashes. Is that enough? What about encoded input or a symlink?

### System design

**31.** The triage service runs on two nodes behind a proxy at 20 requests a second. The next release adds a missing_items column to the orders file both nodes read, and changes how the service answers. Design the rollout so no request fails: the order of steps, the health gate, the data change, the rollback at each step, and when the old column is removed.  
*Staff (L6+) · lessons 24, 14 · Global capability centres, FAANG / big tech*  
Tests: Designs a zero-downtime rollout with expand, deploy and contract, and a rollback at each step.
   - *Follow-up:* The team wants to drop the old column in the same release. What breaks, and when is it safe?
   - *Follow-up:* Version 2 has a bug found after the cleanup step. What is your rollback now?

**32.** Customer two must go live in six weeks, reusing the triage service built for customer one. Design the reference deployment: what is shared core, what is per-customer config and code, which environment each customer gets, how a release reaches both, and how the second customer's data and secrets stay apart from the first's.  
*Staff (L6+) · lessons 21, 25, 14 · Top product companies, FAANG / big tech*  
Tests: Designs a reusable reference deployment, with a clear shared core and a per-customer boundary.
   - *Follow-up:* Customer one wants a change only they need, and the release pipeline is shared. How does that change ship?
   - *Follow-up:* Customer two's network blocks the container registry you use. What is your fallback?

**33.** A customer's dispatch desk depends on a triage service that calls one model provider. At peak the primary serves 20 requests a second. The desk needs an answer, or 'held for a person', within 60 seconds. The provider has a 40-minute outage on a Friday. Design the keyword-rules fallback behind a circuit breaker: when the breaker opens and closes, what the rules return, what they get wrong and how the eval set shows it, and what you tell the ops lead. Say what you leave out of the first version.  
*Senior (L5) · lessons 11, 28 · FAANG / big tech, Top product companies, Global capability centres*  
Tests: Designs a keyword-rules fallback behind a circuit breaker, works the load arithmetic, measures what the rules get wrong, and states the state of the system.
   - *Follow-up:* The drill's breaker trips on one failure. What should the production breaker wait for, and what does a too-low value do all day?
   - *Follow-up:* The customer wants the rules fallback switched on automatically, with no one on call. What do you need in place first?

**34.** The triage service runs on two nodes in the customer's Compose stack; the customer's on-call now gets the pages. Peak is 20 requests a second. For one hour, a fault in the customer's order API adds 3 seconds to 1 in 10 triage requests. Every page rule fires over a 5-minute window and only with at least 100 requests in it. Design alerting that pages on-call for this fault and no other: for each alert, the signal it reads and why, the rule, and the page's fields. Which signal would you not page on for this fault, and why?  
*Senior (L5) · lessons 16, 17, 22 · Global capability centres, Top product companies*  
Tests: Designs one latency alert from the metric, log and trace signals, with a window, a page that carries its runbook, and a named signal that stays silent.
   - *Follow-up:* The rule has paged 40 times in one week with no customer impact. What do you change in the rule, and what do you risk losing?
   - *Follow-up:* Node a is slow and node b is healthy, and the proxy splits requests evenly. Does your alert say which node is slow, and what must the metric carry to do that?

### Production and scale

**35.** After a two-minute outage, the customer's order API is down for twenty minutes. Your job runs 200 workers. Each retries a 503 four times with a fixed one-second wait, and each retry is a fresh request. What does the customer's API see, why does the outage last longer, and what do you change in the client and in the job?  
*Senior (L5) · lessons 04, 28 · FAANG / big tech, Global capability centres*  
Tests: Explains synchronised retries, and designs jittered, capped retries with keyed writes.
   - *Follow-up:* A 429 arrives with Retry-After: 30. What does the client do with it, and does that attempt count toward the cap?
   - *Follow-up:* Some of these calls are writes. Which changes are safe for them without an idempotency key?

**36.** A customer's security team sends an eight-question questionnaire on data residency, personal data in notes, audit logs and access, due Friday. Two answers have no evidence in your pack: the audit log you hold was written by a notebook, not the running service, and no independent assurance report exists yet. What do you send for each answer, and what do you refuse to write?  
*Senior (L5) · lessons 27, 13 · Global capability centres, Top product companies*  
Tests: Answers a security questionnaire with evidence, and refuses to claim what is not proven.
   - *Follow-up:* The auditor asks for the production audit log. What do you provide, and what do you refuse?
   - *Follow-up:* Their CISO asks for a yes on a control you have not built. What do you say?

**37.** You hand the triage service to a customer's operations team of six, with two on-call engineers who did not build it. You leave next Friday. What goes in the handover pack, which alerts have runbooks, who owns each alert after you leave, and how do you prove the on-call can run it without you? Name the acceptance test you accept and the one you refuse.  
*Staff (L6+) · lessons 22, 17 · Top product companies, Global capability centres*  
Tests: Defines a handover the customer's team proves it can run alone.
   - *Follow-up:* Their on-call runs the drill and skips the verify step. Do you sign off?
   - *Follow-up:* Who owns the cost alert after handover?

### Trade-offs and judgement

**38.** You have 15 minutes on a steering call. The customer's ops lead asks, 'When is it live?' You will show the proof of concept live. It reads one 200-row CSV on a laptop, keeps its key in a local settings file, and has been right on every test message. What gap list do you show, in what order do you close the gaps, what date do you quote, and what do you not promise yet?  
*Senior (L5) · lessons 21, 07, 22 · Top product companies, Global capability centres*  
Tests: Gives an honest date and gap list in a live presentation, without promising from a demo.
   - *Follow-up:* The customer's network team says the POC cannot leave their VPC for six weeks. Does your date move, and what do you say?

**39.** The customer wants six stores after a one-store pilot. The six-store build is $24,000, of which the pilot is $8,000. Running cost is $3,600 a year for six stores. The problem costs the customer $43,200 a year. Define the share as the share of those annual losses the system prevents. At a 50% share, prevented losses are $21,600 a year. The pilot may show a 30% share, which scales the benefit in proportion. Compute the payback in months and the three-year net at 50% and at 30%. Then say what you offer.  
*Senior (L5) · lessons 30, 08 · Top product companies, Global capability centres*  
Tests: Builds a payback case with sensitivity, and offers a go or no-go pilot instead of a yes or no.

**40.** A customer has asked for the same change three times in six weeks: re-running the totals after a late file. Your team fixes it by hand each time, about 2 hours. Product has no slot this quarter. Write the field report: each number and its source, the evidence rows, core or custom with the reason, one ask with an owner and a date, and the evidence that would prove you wrong.  
*Senior (L5) · lessons 26, 25 · Top product companies, Global capability centres*  
Tests: Writes a sourced field report that makes a clear product decision possible.
   - *Follow-up:* Product asks: is this one customer or many? What data do you answer with?

### Project deep-dive

**41.** Defend the triage app at 10 times scale as your own project. Today it reads one orders file and keeps cases in a CSV on one server. At about 200,000 messages a day across 10 customers, what breaks first, what do you change first, and what would you not do yet? Name the numbers you would watch.  
*Staff (L6+) · lessons 16, 18, 20, 23 · FAANG / big tech, Top product companies*  
Tests: Defends a scale plan with the first breaking point, the first changes and the numbers to watch.
   - *Follow-up:* Three workers now write the CSV store. What fails, and what do you move to?
   - *Follow-up:* The model quota is shared by all tenants. How do you stop one noisy tenant from using all of it?

**42.** Your claim is that triage is 90% right. Defend it as your own project. What exactly does the 90% measure, and on which cases? Then say what a person checks on each release sample, how you measure agreement between that person and the model grader, and what you do when they disagree on a case.  
*Senior (L5) · lessons 11, 12, 20 · Global capability centres, Top product companies*  
Tests: Defends a quality claim with what it measures, the human check and its agreement with the grader.
   - *Follow-up:* The team re-labels three cases after the candidate fails them. What do you do?

### Behavioral

**43.** Tell me about an engagement where the work cost more than the contract paid, or was about to. Answer in STAR form. What did you measure first, what did you tell the customer and when, what changed in scope or price, and what was the result in numbers?  
*Senior (L5) · lessons 29, 30 · FAANG / big tech, Global capability centres, Top product companies*  
Tests: Owns a real engagement cost overrun, with measured numbers and early written communication.
   - *Follow-up:* Which number was your guess at the start, and which did you measure?
   - *Follow-up:* What would you tell a new engineer to check in week one?

**44.** Tell me about a production incident on a customer system where you owned the fix or the customer communication. Answer in STAR form. What did you do in the first 15 minutes, how did you choose between rolling back and debugging, how did you restore the data, and what changed afterwards?  
*Senior (L5) · lessons 17, 24 · FAANG / big tech, Global capability centres*  
Tests: Runs an incident in the right order: stop the harm, restore safely, then learn.
   - *Follow-up:* What was your recovery target, and did you meet it?
   - *Follow-up:* What did the runbook say before the incident, and what changed in it?

## Mock interview loops

Practise these as one sitting each (45–60 minutes, answers out loud, a timer on). Question numbers refer to the list above.

- **Global capability centres (GCCs):** #26 (Fundamentals deep-dive), #3 (Coding), #14 (Debugging), #25 (Project deep-dive)
- **Top product companies:** #11 (Coding), #18 (System design), #6 (Trade-offs and judgement), #25 (Project deep-dive)
- **FAANG / big tech:** #3 (Coding), #18 (System design), #35 (Production and scale), #10 (Behavioral)

Levels: mid ≈ SDE-2 / Engineer II (FAANG L4); senior ≈ Senior Engineer / Lead at GCCs and product companies (FAANG L5); staff ≈ Staff / Principal (FAANG L6+).
