# Vector Databases: Foundations to Enterprise — syllabus

**Audience:** Python developers who know lists, dicts, functions and a little NumPy. No machine-learning background assumed.

**Outcome:** Build, evaluate, tune, operate and architect semantic and hybrid search systems on vector databases: from a NumPy toy to a replicated, sharded, Kubernetes-deployed, multi-tenant platform planned for billions of vectors, including failure drills, disaster recovery, zero-downtime change, governance, cost, and the newest techniques in the field.

**Running example:** Recipe finder — Everyone understands 'find me something like this to cook'. It starts as 5 recipes on a 2-D map and grows naturally to millions of recipes across many restaurants.

*How it grows:* 5 hand-scored recipes in 2-D (L1) -> 50 then ~2,000 embedded recipes with filters (L2) -> chunked instructions, sparse + dense hybrid search, reranking, late interaction, RAG (L3) -> 1M synthetic vectors for index benchmarks (L4) -> a tested, observed API service (L5) -> a 3-4 node replicated cluster under load and failure (L6 Part 6) -> a Kubernetes deployment planned for 1 billion vectors across regions (L6 Part 7) -> a multi-tenant platform serving thousands of restaurants and several product teams (L6 Part 8)

**Tools used:**

- **NumPy** — the idea from scratch (lessons 01-06, 27)
- **Qdrant 1.19 (local mode / Edge -> single server -> 3-4 node cluster in Docker Compose -> Helm chart qdrant/qdrant on kind)** — main vector database: collections, filters, hybrid, multivectors, quantization, sharding, replication, consensus, failover, tenancy, RBAC (lessons 07-24, 30-34, 37-71)
- **Milvus 3.0 (standalone)** — contrast: disaggregated storage/compute, DiskANN, lakehouse (lessons 45, 55, 56, 64)
- **Weaviate 1.39** — contrast: leaderless quorum replication (architecture lesson) (lessons 45, 48)
- **sentence-transformers 6 / fastembed** — dense, sparse, multivector and reranking models (small, CPU-friendly, not gated) (lessons 05, 18-23)
- **FAISS** — index internals and benchmarks (IVF, HNSW, PQ, RaBitQ, GPU) (lessons 28, 29, 31, 32, 33, 36, 57)
- **LanceDB + an S3-compatible store (RustFS)** — object-storage-first engine; backup target (lessons 42, 56, 60)
- **Postgres + pgvector 0.8.7** — vectors in a relational database (lessons 35)
- **FastAPI + pytest** — serving and testing (lessons 37-44, 67)
- **Docker Compose, kind, kubectl, Helm** — multi-node clusters and Kubernetes on a laptop (lessons 46-71)
- **Locust** — load, chaos and capacity tests (lessons 50, 53, 59, 62)

**LLM use:** light — lessons 25, 71 — Retrieval-augmented generation needs a model to write the answer; every other lesson runs without one. (recorded once, replayed without a key)

**71 lessons · about 55 hours**

## Part 1 · L1 Foundations: Meaning as numbers

| # | Lesson | You will be able to | Needs |
| --- | --- | --- | --- |
| 01 | Why keyword search misses meaning | Show a recipe query that keyword matching gets wrong and explain why meaning-based search finds it. | — |
| 02 | A vector is just a list of numbers | Place recipes as points on a 2-D 'sweet vs spicy' map and read a vector's dimensions. | — |
| 03 | Measuring closeness: distance, dot product and cosine | Compute Euclidean distance, dot product and cosine similarity by hand and with NumPy, and say when they disagree. | — |
| 04 | Nearest-neighbour search in ten lines | Write exact k-nearest-neighbour search over the toy recipes with NumPy. | — |
| 05 | Embeddings: turning text into vectors | Embed recipe descriptions with a small sentence-embedding model and see that similar meanings land close together. | download |
| 06 | Checkpoint: a recipe search engine with NumPy ⭐ | Build a working semantic recipe search over 50 recipes using only NumPy and saved embeddings. | — |

## Part 2 · L2 Core: Your first vector database

| # | Lesson | You will be able to | Needs |
| --- | --- | --- | --- |
| 07 | What a vector database adds to NumPy | List what breaks in the NumPy version at real scale and which vector-database feature fixes each. | — |
| 08 | Create a collection: size and distance | Create a collection with the right vector size and distance metric, and explain both choices. | — |
| 09 | Store points: ids, vectors and payloads | Insert recipes as points with ids, vectors and a payload of metadata, and read them back. | — |
| 10 | Query: top-k results and scores | Run similarity queries, choose k, and interpret scores and score thresholds. | — |
| 11 | Filter by metadata | Filter by cuisine, time and diet, create payload indexes for the fields you filter on, use full-text filters, and page through results with scroll. | — |
| 12 | Update, upsert and delete safely | Change payloads, replace vectors and delete points without breaking search. | — |
| 13 | In-memory, on-disk and server modes | Choose between qdrant-client local mode (dev/testing only: it ignores search params), Qdrant Edge (in-process with real indexes) and the server, and move the same code between them. | docker |
| 14 | Load a dataset in batches | Ingest a few thousand recipes efficiently with batching and stable ids, and measure the speed-up. | — |
| 15 | Checkpoint: a filtered recipe finder ⭐ | Build a recipe finder that answers natural-language queries with filters over a few thousand recipes. | — |

## Part 3 · L3 Practical: Search people actually trust

| # | Lesson | You will be able to | Needs |
| --- | --- | --- | --- |
| 16 | Measuring search quality | Build a small labelled query set and compute recall@k, precision@k and MRR for the recipe finder. | — |
| 17 | Chunking long text | Split long recipe instructions into chunks, measure (with lesson 16's metrics) which chunk size retrieves best, and return one result per recipe with query_points_groups. | — |
| 18 | Choosing an embedding model | Compare two embedding models on your own test set by quality and vector size, truncate a Matryoshka model's vectors, and know the theoretical limits of single-vector embeddings (the LIMIT result). | download |
| 19 | Sparse vectors: BM25 and learned sparse | Build sparse keyword vectors with Qdrant's built-in BM25 (models.Document(model='Qdrant/bm25') with the IDF modifier) and a learned sparse model, and see which exact-term queries they win. | download |
| 20 | Hybrid search: fusing dense and sparse | Run dense and sparse searches as prefetches in one Query API call and fuse them with reciprocal rank fusion (RrfQuery, with weights). | — |
| 21 | Reranking the top results | Rerank the top candidates with a cross-encoder and adjust final scores with formula queries (boost by rating and freshness). | download |
| 22 | Named vectors: more than one vector per item | Store separate named vectors for title and ingredients and query the right one for the job. | — |
| 23 | Late interaction: one vector per token | Store token-level multivectors with max_sim comparison, show where ColBERT-style late interaction beats one vector per recipe, and use MUVERA to make it fast enough to serve. | download |
| 24 | Beyond plain top-k: diverse and example-based results | Make result lists diverse with maximal marginal relevance, and search from examples with recommendation queries ('more like these, less like that'). | — |
| 25 | Retrieval-augmented generation | Answer cooking questions with an LLM grounded in retrieved recipes, with citations to recipe ids, and defend against instructions injected into recipe text. | llm |
| 26 | Checkpoint: hybrid, reranked and measured ⭐ | Ship a recipe search with hybrid retrieval, reranking and an evaluation report that proves it beats plain vector search. | — |

## Part 4 · L4 Advanced: How indexes really work

| # | Lesson | You will be able to | Needs |
| --- | --- | --- | --- |
| 27 | Why exact search stops scaling | Measure brute-force query time from 10k to 1M synthetic vectors, explain the growth, and see distances concentrate and 'hub' points appear as dimensions rise. | slow |
| 28 | IVF: search fewer clusters | Build an IVF index with FAISS and tune nlist and nprobe against recall and speed. | — |
| 29 | HNSW: navigable graphs | Explain how HNSW finds neighbours and tune M, ef_construction and ef_search with measurements. | — |
| 30 | Inside a collection: segments, WAL and the optimizer | Watch writes flow through the write-ahead log into segments, see the optimizer build indexes and vacuum deletes, and measure indexing lag and its effect on search (indexed_only, indexing_threshold). | docker |
| 31 | Benchmarking recall, latency and memory | Run a fair benchmark of flat, IVF and HNSW indexes with FAISS and read the trade-off curve; know what VectorDBBench and VIBE add and why ann-benchmarks is no longer maintained. | slow |
| 32 | Quantization: smaller vectors, faster search | Apply scalar, product and binary quantization and measure memory saved against recall lost, with rescoring. | slow |
| 33 | Fewer bits per dimension: RaBitQ and TurboQuant | Compare 1.5-bit, 2-bit and asymmetric binary quantization with RaBitQ (FAISS) and Qdrant's TurboQuant on the same data, and read the published reproducibility dispute critically. | docker, slow |
| 34 | Filtered ANN: why filters break graphs | Show how pre-filtering and post-filtering fail at different selectivities, and how filter-aware HNSW links built from payload indexes (lesson 11) and ACORN search fix it. | docker |
| 35 | Choosing a vector store: pgvector vs dedicated engines | Run the recipe search in Postgres with pgvector 0.8.7 (HNSW, IVFFlat, iterative scans; pgvectorscale noted) next to Qdrant, and use a decision guide to pick between an extension, a dedicated engine, a library and a serverless service. | docker |
| 36 | Checkpoint: index design report ⭐ | Choose and justify an index and quantization setup for 1M recipes with a target of p95 < 50 ms and recall@10 > 0.95. | slow |

## Part 5 · L5 Production: Running it for real

| # | Lesson | You will be able to | Needs |
| --- | --- | --- | --- |
| 37 | Serving search behind an API | Expose the recipe finder as a FastAPI endpoint with input validation, timeouts and connection reuse. | — |
| 38 | Ingestion pipelines and embedding versions | Build an idempotent pipeline that adds, updates and deletes recipes and records which model made each vector. | — |
| 39 | Testing search systems | Write unit tests, golden-query tests and a recall regression test that fails CI when quality drops. | — |
| 40 | Observability: latency, errors and quality drift | Expose Qdrant's /metrics and telemetry, track optimizer progress, the slow-request log and memory reporting, propagate x-request-id/traceparent through the API, and alert on latency, errors and quality drift. | — |
| 41 | Security and access control | Secure the database and API, enforce per-user access with filters, and defend RAG against injected text. | docker |
| 42 | Backups, restores and collection aliases | Take and restore snapshots to an S3-compatible store, and point the app at a collection alias so a restored collection can be swapped in with no code change; practise a restore drill. | docker |
| 43 | Cost and capacity planning | Build a capacity and cost model (RAM per vector, quantization savings, replicas) for one server, set disk quotas (PUT /quotas, HTTP 507), and note that memory tiers (lesson 55) will lower it further. | — |
| 44 | Checkpoint: production-ready recipe search ⭐ | Deliver a tested, observable, secured recipe search service with a runbook. Include a runbook: restore, re-index, rotate keys, disk-full, slow queries. | docker |

## Part 6 · L6 Enterprise: Distributed vector search: clusters from the inside

| # | Lesson | You will be able to | Needs |
| --- | --- | --- | --- |
| 45 | How a distributed vector database is built | Draw the write and read paths of a shared-nothing cluster (Qdrant: Raft for topology, shards and replicas), a disaggregated one (Milvus 3.0: proxy, coordinator, streaming/query/data nodes, Woodpecker WAL, object storage) and a leaderless-quorum one (Weaviate), and say what each design is good at. | — |
| 46 | Run a 3-node cluster on your laptop | Start a 3-node Qdrant cluster with Docker Compose, join the peers, and read the cluster state from its API. | docker |
| 47 | Sharding: splitting a collection across nodes | Create a sharded collection, see which node holds each shard, and trace how one query fans out to every shard and merges the top-k. Plan the shard count up front (the 12-shard rule: 12 divides evenly over 1, 2, 3, 4, 6 and 12 nodes), because open-source Qdrant cannot reshard. | docker |
| 48 | Replication and consistency levels | Configure replication_factor and write_consistency_factor, compare read consistency settings, and measure the latency cost of stronger guarantees. Measure read-your-writes under ordering weak vs strong with route affinity, and run Weaviate's R+W>N quorum as a contrast lab. | docker |
| 49 | Consensus: who decides the cluster's shape | Explain what Raft agrees on in the cluster (topology, collections, shard placement, not every point), find the leader, and see what happens when a majority is lost. Then lose the majority and recover with /cluster/recover and a forced peer removal. | docker |
| 50 | Chaos drill: lose a node under load | Kill a node while a load generator searches and writes, record errors and p95 latency before, during and after, and watch replica states recover through shard transfer. Add a network-partition drill (docker network disconnect) and a disk-full drill; watch Dead/Partial replicas and wal_delta fall back to stream_records. | docker, slow |
| 51 | Scaling out and in: move, replicate and drop shards | Add a fourth node and move and replicate shards onto it under load, then scale in with drop_replica and DELETE /cluster/peer; reshard by building a new collection and swapping its alias (built-in resharding is Cloud only, shown as a read-along). | docker |
| 52 | User-defined sharding: shard keys | Place data by a shard key (region or large tenant), query a single shard key, and decide between automatic and user-defined sharding. Include time-based shard keys and measure hot-shard skew when one chain dominates traffic. | docker |
| 53 | Checkpoint: a cluster that survives failure ⭐ | Run a 3-node replicated cluster under load, kill and restore a node, scale out, and deliver a report with error rates, p95 latency and recovery time. | docker, slow |

## Part 7 · L6 Enterprise: Extreme scale and Kubernetes operations

| # | Lesson | You will be able to | Needs |
| --- | --- | --- | --- |
| 54 | Billion-scale maths: when RAM runs out | Calculate memory, disk and node counts for 10M, 100M and 1B vectors at different dimensions, precisions and replication, and decide what must move to disk. | — |
| 55 | Memory tiers and disk-based search | Place vectors, indexes and payloads in Qdrant's cold/cached/pinned memory tiers, measure latency and recall against all-in-RAM, and explain how DiskANN's Vamana graph searches from SSD (Milvus DISKANN). | docker, slow |
| 56 | Vectors on object storage: serverless and lakehouse engines | Run LanceDB over a local S3-compatible store, measure cold vs warm query latency, and explain how object-storage-first engines (turbopuffer, Amazon S3 Vectors, Milvus 3.0 lakehouse) trade latency for cost. | docker, cloud |
| 57 | GPU vector search: when it pays off (read-along) | Explain GPU indexes (CAGRA, GPU IVF-PQ via cuVS) and Qdrant's GPU HNSW indexing, why they raise throughput and index-build speed more than single-query latency, and compare published numbers with a CPU baseline. | gpu |
| 58 | Deploy a vector database cluster to Kubernetes | Deploy a 3-replica Qdrant cluster to a local kind cluster with the official Helm chart, with persistent volumes, resource limits and health probes, and run the recipe search against it. Use Helm v4.3 and a digest-pinned kind node, enable the PodDisruptionBudget (off by default), and explain why an HPA does not fit stateful shards. | k8s |
| 59 | Load testing and tail latency | Load-test the cluster with realistic query mixes, find the throughput at which p99 latency breaks the SLO, and turn the results into a QPS-per-node capacity model. | docker, slow |
| 60 | High availability, disaster recovery and multiple regions | Back up the cluster to object storage, restore it into a new cluster, measure RPO and RTO, and compare multi-zone and multi-region patterns (active-passive, active-active, per-region clusters). Prove that one node's snapshot is not a cluster backup, restore a full collection from per-node snapshots with measured RTO, and use a listener node for DR. | docker |
| 61 | Zero-downtime upgrades and index changes | Upgrade the cluster one node at a time under load (client first, at most 3 minor versions apart), change index and quantization settings safely, roll out enforce_internal_auth and rotate keys with alt_api_key under load, and know Milvus 3.0's rollback limit once Storage V3 is used. | docker, k8s |
| 62 | Checkpoint: production cluster on Kubernetes ⭐ | Deliver a Helm-deployed cluster on kind with replication, backups, a load-test report and a capacity plan for 1 billion vectors. Include an OOMKill drill: memory limits vs mmap page cache on kind. | k8s, slow |

## Part 8 · L6 Enterprise: Enterprise architecture, governance and the frontier

| # | Lesson | You will be able to | Needs |
| --- | --- | --- | --- |
| 63 | Multi-tenancy at scale | Choose between collection-per-tenant, payload partitioning with tenant indexes, shard keys per large tenant, and tiered tenancy, and implement promotion of a tenant that grows. | docker |
| 64 | Changing embedding models without downtime | Migrate to a new embedding model with a shadow collection, dual writes, backfill, offline and online evaluation, and an alias switch with a rollback plan. Also migrate between vendors (Milvus to Qdrant with the Qdrant migration tool) with baseline and integrity checks. | docker |
| 65 | Security, governance and compliance at organisation scale | Apply JWT RBAC with per-collection scoped tokens, TLS, encryption at rest with encrypted volumes (Qdrant's built-in option is Cloud only), audit logging, data residency by region, a verified right-to-erasure flow across vectors, backups and caches, and harden the deployment (unprivileged image, read-only rootfs, snapshot-recovery SSRF). | docker |
| 66 | Cost engineering at scale | Model total cost for self-hosted, managed and serverless (object-storage based) vector search, attribute cost per tenant and per query, and apply the biggest levers. Use published numbers: Notion's -60% search spend moving to turbopuffer, S3 Vectors' 'up to 90%' claim, and $0.20 per 1M tokens to re-embed with Gemini. | — |
| 67 | A shared retrieval platform for many teams | Build a shared retrieval gateway in FastAPI with per-team JWT tokens scoped to collections, per-team quotas, and an SLO check on p99 latency and recall, and define ownership and self-service onboarding. | docker |
| 68 | The frontier: what's new and where vector search is heading | Explain the most important developments of the last 12 months (Qdrant 1.16-1.19, Milvus 3.0 External Collections and SINDI, S3 Vectors GA, turbopuffer ANN v3, VectorDBBench 2.0, ST6 MultiVectorEncoder, TurboQuant and its dispute, embedding-inversion and hubness attacks) and judge which matter for the recipe platform. | — |
| 69 | Case studies and architecture decisions | Use published case studies (Notion, Uber at 1.5B vectors with p99 < 120 ms, turbopuffer customers, Tripadvisor (vendor-written), Shopee) to write an architecture decision record for a new product. | — |
| 70 | Incident reviews: learning from the drills | Turn the earlier drills (node loss, partition, quorum loss, disk full, OOMKill, hot shard) into blameless postmortems with timelines, detection gaps, and the runbook and alert changes each one justifies. | — |
| 71 | Capstone: an enterprise recipe search platform ⭐ | Design, build and document a multi-tenant, replicated, Kubernetes-deployed hybrid search platform with evaluation, observability, DR plan, cost model and ADRs. | k8s, docker, llm |

## Enterprise depth coverage

Every item of the Enterprise depth checklist (`standards/LEVELS.md`) and where it is taught.

| Checklist item | Lessons |
| --- | --- |
| 1 distributed architecture internals | 45, 49 |
| 2 cluster operations hands-on | 46, 47, 48, 51, 52 |
| 3 failure and recovery | 50, 53, 49, 70 |
| 4 extreme scale | 54, 55, 56, 57 |
| 5 kubernetes and infrastructure | 58, 62 |
| 6 performance engineering at scale | 59, 53 |
| 7 high availability and disaster recovery | 42, 60 |
| 8 zero-downtime change | 61, 64, 51 |
| 9 multi-tenancy and isolation | 52, 63 |
| 10 security and compliance at org scale | 41, 65 |
| 11 cost engineering | 43, 66 |
| 12 platform and organisation patterns | 67, 70 |
| 13 frontier | 68 |
| 14 case studies | 69 |

## Out of scope

- **Training or fine-tuning embedding models** — a separate topic; this course chooses and evaluates existing models
- **Full RAG and agent engineering (prompting, agents, eval frameworks)** — covered only as far as retrieval feeds an LLM; deserves its own course
- **Writing a vector database engine from scratch** — L4 and Part 6 explain internals by running real engines instead
- **Real multi-region cloud deployments** — lesson 60 runs backup/restore and failover locally and covers multi-region patterns as a cited read-along; no cloud account needed
- **Vendor-by-vendor tours of every managed service** — lessons 35, 66, 69 give decision guides; the patterns transfer
- **ANN algorithms from scratch and most research-stage techniques (NSG/Vamana builds, SOAR, LVQ, LSH theory, streaming ANN, lower bounds, private search)** — covered in track ann-algorithms-research; this track keeps the labs that change how you run a database (RaBitQ/TurboQuant, ACORN, late interaction/MUVERA, Matryoshka, hubness)
- **Qdrant Cloud-only features hands-on (resharding, auto-rebalancing, Multi-AZ zone awareness, built-in encryption at rest, Cloud RBAC/SSO)** — need a paid Cloud account; lessons 51, 60 and 65 teach the open-source equivalent and show these as read-alongs

⭐ = checkpoint project for that part.
