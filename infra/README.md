# Infrastructure

The whole stack on AWS, described so it can be reviewed, repeated and thrown
away. Production is not a different architecture from the laptop: it is the
same containers with the database and the object store pointed elsewhere,
which is the point of the modular monolith in [ADR 0001](../docs/adr/0001-modular-monolith.md).

## What it builds

```
                       internet
                          │
              CloudFront ─┤  (optional: only with a domain)
                          │
                    Elastic IP
                          │
   ┌──────────────────────┴───────────────────────┐
   │  public subnet                                │
   │    EC2 t4g.small · the compose stack          │
   │      Traefik · API · worker · Redis · Ollama  │
   │    instance role: S3, SSM, Session Manager    │
   └──────────────────────┬───────────────────────┘
                          │ security group, port 5432 only
   ┌──────────────────────┴───────────────────────┐
   │  private subnets, no route to the internet    │
   │    RDS PostgreSQL 17 · pgvector · encrypted   │
   └───────────────────────────────────────────────┘

   S3          uploaded documents, versioned, private
   SSM         secrets, SecureString, read by the instance role
   CloudWatch  logs and the alarms that fire when the box is the problem
```

Thirty-eight resources. Six of them (DNS, the certificate, CloudFront) only
exist if `domain_name` is set.

## Running it

Terraform is not installed on the machine this was written on, so it runs in a
container with the provider cache on a disk that has room:

```bash
cd infra
docker run --rm -v "$PWD:/infra" -v /mnt/ssd1tb/tf-cache:/plugins \
  -e TF_PLUGIN_CACHE_DIR=/plugins -w /infra hashicorp/terraform:1.9 init

# with credentials, from here on
terraform plan -out=plan.tfplan
terraform apply plan.tfplan
```

**Never `apply` without reading the `plan`.** That is the entire reason this
exists rather than a console session.

## What it costs

Approximate, us-east-1, at the time of writing:

| | | per month |
| --- | --- | --- |
| EC2 | t4g.small on demand | ~15 USD |
| RDS | db.t4g.micro, 20 GB gp3, single AZ | ~15 USD |
| EBS | 40 GB gp3 | ~3 USD |
| Elastic IP | attached to a running instance | free |
| S3 | a few GB plus requests | ~1 USD |
| SSM, CloudWatch | at this size | ~1 USD |
| **total** | | **~35 USD** |

With a domain, CloudFront adds a few dollars and Route53 costs 0.50 per zone.

Two things were left out **because of what they cost**, and both are named
rather than hidden:

- **No NAT gateway** (~32 USD/month before any traffic). The instance sits in
  a public subnet with a security group instead. The database, which is the
  thing that must never be reachable, is in private subnets with no route out.
- **Single AZ for the database.** Multi-AZ doubles the RDS bill to remove a
  failure mode this project has not been hurt by, and it is why the SLO says
  99% and not 99.9%. Flip it when the objective changes, not before.

## Decisions worth knowing before changing anything

**Graviton (t4g) everywhere.** About 20% cheaper than x86 for the same work.
The images build multi-arch already.

**Ollama runs on the instance, not on its own.** Embedding is CPU-bound and
slow ([ADR 0002](../docs/adr/0002-embedding-model.md)), so on a t4g.small it
will contend with the API. That is a known and accepted limit at this size; the
first thing to split out when the load justifies it.

**No SSH by default.** `allowed_ssh_cidr` is empty, so nothing opens port 22.
Getting onto the box is `aws ssm start-session`, which needs no open port and
leaves a trail in CloudTrail that a shared key does not.

**IMDSv2 required.** The single mitigation that turns "an SSRF in the app" into
something other than "the instance credentials are gone".

**The API is never cached by CloudFront.** Every response is per user behind a
session cookie. A CDN in front of that is a data leak waiting for a cache key
collision. Only `/assets/*`, which Vite fingerprints, is cached.

**Secrets are created empty and filled in by hand.** The API keys come from
outside, so Terraform owns that the parameter exists and a human owns the
value. `ignore_changes` is what stops the next apply from helpfully putting the
placeholder back and taking the AI offline.

## State

The backend block is commented out and has to be enabled before this is used
for anything real. State holds the database password and every generated
secret, so it is not a file to leave on a laptop, and it is not created here
because a module cannot bootstrap the store that holds its own state.

## What is verified, and what is not

Run on 2026-08-14:

| | |
| --- | --- |
| `terraform init` | providers resolved and locked |
| `terraform fmt -check` | clean |
| `terraform validate` | **Success! The configuration is valid.** |
| bootstrap template rendered | every substitution correct |
| `terraform plan` | **not run** |
| `terraform apply` | **not run** |

`plan` and `apply` need real credentials and would create billable resources,
so this is where the verification honestly stops. `validate` proves the
configuration is internally consistent; it does not prove AWS will accept every
argument, that quotas allow it, or that the bootstrap works on a real machine.
The first `plan` against a real account is where those are found.
