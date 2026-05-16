# infra/aws — placeholder

First non-local deployment target: **AWS ECS Fargate**. Not Temporal Cloud.

Intended contents (not yet implemented):

- Terraform or CDK stacks for:
  - ECS Fargate services for `apps/api`, `apps/workers`, `apps/slack`,
    `apps/mcp`.
  - RDS Postgres (with `pgvector`).
  - A self-hosted Temporal cluster on Fargate.
  - Secrets Manager wiring for everything currently in `.env.example`
    (Slack, Monday, Sheets, tl;dv, Anthropic, optional Bedrock/Vertex).
- IAM roles scoped per service. The Tool Gateway service is the only one
  with read access to third-party credential secrets.

Until these are written, treat AWS deployment as a planned-but-not-built
item. Local Docker Compose is the supported runtime.
