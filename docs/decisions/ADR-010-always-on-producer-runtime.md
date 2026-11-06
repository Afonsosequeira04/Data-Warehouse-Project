# ADR-010: Where the Always-On Ingestion Producers Run

## Status

Proposed

## Context

The replanned platform ingests six public sources with two different shapes (`docs/data-sources.md`):

- **Batch and micro-batch**: NASA FIRMS, USGS Water Data, NOAA buoys, GDACS. These fit the existing model: an Airflow task runs on a schedule, writes raw JSON to S3, and exits.
- **Streaming**: EMSC earthquakes and AISstream vessel positions. Both are WebSocket feeds. A producer must hold an open connection, reconnect on failure, validate each message, and write to Kinesis. This process is not a scheduled task; it is a long-running service (ADR-008).

Airflow on MWAA cannot host that service. MWAA is treated as an ephemeral environment (D-005): it is created for a work window and destroyed afterwards. Destroying MWAA would kill a producer, and a producer that only runs during a window cannot deliver a continuous stream. The producer therefore needs a runtime that can stay up independently of MWAA, while remaining under Afonso's manual cost control.

Constraints that already apply:

- The repository is public; no credentials in Git (AGENTS.md).
- Streaming and its compute are not bound by the US$10/month batch guardrail or by Free Edition limits; the model is defined in ADR-011 (Proposed).
- Terraform is split into persistent and ephemeral AWS stacks (D-006). Kinesis and any producer compute must live in a root that is applied and destroyed manually, never by merge-to-`main` CI.
- ECS is listed as out of scope in AGENTS.md today. Using it requires this ADR to be Accepted and AGENTS.md to say so explicitly.
- No unverified cost figures are assumed here. Actual prices must be checked before any apply.

This ADR does not decide the producer's internal design (reconnect policy, batching, schema validation). It decides only where that process runs.

## Decision Being Considered

Where should the always-on WebSocket producers (EMSC, AISstream) run, given that MWAA is ephemeral, compute is not covered by the batch cost guardrail, and every billable resource must be created and destroyed manually?

## Options

### Option 1: Afonso's local machine

Run the producer as a local process (for example, a Python service started in a terminal or under a process manager) during a planned streaming window.

**Trade-offs:**
- Pros: Zero cloud compute cost; no new AWS service; the fastest path to prove the EMSC and AISstream connections and payload shapes.
- Cons: The producer stops when the laptop sleeps, loses network, or is closed, which undermines "always-on" freshness; no clean remote operations story; not a portfolio-grade demonstration of a deployed service; secrets end up on a personal machine.
- Best use: a short spike to validate feeds, not the durable runtime.

### Option 2: Amazon ECS Fargate task (recommended)

Run each producer (or one producer handling both feeds) as a containerized task on ECS Fargate in a dedicated `aws/streaming` Terraform root, started and stopped on demand.

**Trade-offs:**
- Pros: No server to patch or maintain; the container is defined in the repository and reproducible; task role and secrets can be scoped tightly; the service is independent of MWAA; stopping the task ends the compute charge; a clear, demonstrable "deployed streaming producer" story.
- Cons: Introduces ECS, which is currently out of scope, so AGENTS.md and the architecture must change; image build and registry (for example, a private ECR repository) become part of the streaming root; Fargate bills for task uptime, so the window must be explicit; adds Terraform surface and one more failure mode.
- Notes: The exact task size, image build path, and registry choice are implementation details to be decided when ADR-008 and this ADR are Accepted. Current pricing must be verified before apply.

### Option 3: Small EC2 instance

Run the producer on a single small EC2 instance that is started for a streaming window and stopped afterwards.

**Trade-offs:**
- Pros: Simple mental model; SSH and process supervision are familiar; no container build pipeline.
- Cons: A server to patch and secure; the instance is billable while running and can be forgotten; storing and rotating credentials on the host is riskier; the platform gains a pet server, which is the opposite of the rest of the design.
- Best use: a fallback if the container path is blocked.

## Consequences

### Architecture

- Option 2 adds ECS Fargate and a container registry to the streaming Terraform root. Kinesis, Databricks Structured Streaming, and the dbt models from ADR-008 stay as described there.
- Options 1 and 3 keep the AWS footprint smaller but weaken the "always-on" claim and the reproducibility of the producer.

### Cost

- Option 1 has no direct cloud compute cost but is not continuous.
- Option 2 and Option 3 bill while the producer is running. The streaming budget envelope is defined in ADR-011 (Proposed); no monthly figure is assumed here. Whichever option is chosen, the streaming window, start command, and stop/destroy command must be documented, and Afonso creates and destroys the resources manually.

### Operations

- Every option requires a documented start/stop procedure and a way to confirm the producer is alive (health signal, logs, Kinesis records arriving).
- Option 2 centralizes logs in CloudWatch and makes restarts reproducible; Option 1 depends on Afonso's machine state; Option 3 needs host-level supervision.
- Streaming never runs through merge-to-`main` CI. It is started deliberately.

### Security

- Producer credentials (AISstream key, Kinesis write access) must come from AWS Secrets Manager or the task's IAM role, never from the repository.
- Option 2 allows a narrow task role; Option 3 requires care to avoid long-lived credentials on disk; Option 1 is the weakest option because secrets live on a personal machine.

### Developer experience

- Option 2 requires a Dockerfile, an image build, and a registry, which is more upfront work but a better portfolio artifact.
- Option 1 is the fastest to try and the least representative.
- Option 3 is simple but invites configuration drift.

### Timeline

- Option 1 can validate feeds quickly and can be used as a spike even if Option 2 is accepted for the real runtime.
- Option 2 adds container and registry work before the first streaming window.
- Option 3 sits between the two.

## Decision

*To be filled when Accepted: which option was chosen and why.*

## Related

- ADR-008: Streaming ingestion path (EMSC + AISstream → Kinesis → Databricks)
- ADR-011: Compute and budget model for streaming and large-volume extensions (Proposed)
- ADR-004: MWAA ephemeral operating model
- D-005: MWAA is ephemeral; a producer cannot depend on it
- D-006: Persistent and ephemeral Terraform stacks
- `docs/data-sources.md`: source list and ingestion modes
- `docs/business-questions.md`: BQ-001, BQ-002, BQ-005
