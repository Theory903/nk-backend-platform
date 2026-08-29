Yes. If the platform supports both **PostgreSQL and MongoDB**, make them **first-class persistence options**, not “Postgres plus a random Mongo connector.”

The important part is deciding **which data belongs where**.

## Updated universal data architecture

```text id="u8j3kv"
                         APPLICATION
                              │
              ┌───────────────┼────────────────┐
              │               │                │
              ▼               ▼                ▼
        PostgreSQL         MongoDB           Redis
        System of Truth    Document Store    Hot State
              │               │                │
              │               │                │
              └───────────────┼────────────────┘
                              │
                       Event / Outbox
                              │
                 ┌────────────┴────────────┐
                 ▼                         ▼
              Streams                    Kafka
                 │                         │
                 ▼                         ▼
             Workers                 Event Platform
                 │                         │
        ┌────────┼────────┐         ┌──────┼──────┐
        ▼        ▼        ▼         ▼      ▼      ▼
      Search  Analytics  AI       CDC   ETL   Integrations
```

# PostgreSQL vs MongoDB

Don't make it:

> PostgreSQL for some things, Mongo for other things.

Make the decision based on **data shape and consistency requirements**.

| Workload                            | PostgreSQL | MongoDB |
| ----------------------------------- | ---------: | ------: |
| Users                               |      ★★★★★ |         |
| Authentication                      |      ★★★★★ |         |
| RBAC                                |      ★★★★★ |         |
| Billing                             |      ★★★★★ |         |
| Payments                            |      ★★★★★ |         |
| Orders                              |      ★★★★★ |         |
| Financial transactions              |      ★★★★★ |         |
| Inventory                           |      ★★★★★ |         |
| Tenant/membership                   |      ★★★★★ |         |
| Relational business data            |      ★★★★★ |         |
| Complex joins                       |      ★★★★★ |         |
| Strong transactions                 |      ★★★★★ |         |
| Audit metadata                      |      ★★★★★ |         |
| Configuration                       |       ★★★★ |    ★★★★ |
| Highly flexible documents           |            |   ★★★★★ |
| Nested JSON documents               |       ★★★★ |   ★★★★★ |
| Content/document metadata           |        ★★★ |   ★★★★★ |
| CMS-like content                    |        ★★★ |   ★★★★★ |
| Product catalogs                    |       ★★★★ |   ★★★★★ |
| Event-shaped application data       |        ★★★ |   ★★★★★ |
| User-generated arbitrary schemas    |            |   ★★★★★ |
| Rapidly changing document structure |         ★★ |   ★★★★★ |
| Large aggregate documents           |        ★★★ |   ★★★★★ |
| Chat/message documents              |        ★★★ |   ★★★★★ |
| IoT/device payloads                 |        ★★★ |   ★★★★★ |
| Unstructured application metadata   |        ★★★ |   ★★★★★ |

MongoDB is particularly useful when the application's natural unit is a **document/aggregate**, rather than a set of heavily relational entities.

---

# The rule I would put into your framework

### PostgreSQL by default

Use PostgreSQL when:

```text id="eq4v0k"
relationships matter
transactions matter
constraints matter
financial correctness matters
authorization matters
reporting joins matter
```

Examples:

```text id="j2xvps"
users
organizations
memberships
roles
permissions
subscriptions
invoices
payments
orders
inventory
workflow metadata
API keys
security events
```

---

# MongoDB when document flexibility matters

Use MongoDB when:

```text id="4p2gk4"
schema changes frequently
documents are naturally nested
relationships are limited
aggregate reads dominate
different records have different shapes
```

Examples:

```text id="v3f3bw"
CMS documents
AI agent state
scraped documents
product catalogs
device telemetry
user-generated metadata
content objects
integration payloads
external API snapshots
document extraction results
```

---

# Don't duplicate truth

This is critical.

Avoid:

```text id="zj2x5c"
User
 ├── PostgreSQL
 └── MongoDB
```

unless there is a deliberate synchronization architecture.

Instead:

```text id="q3n9n5"
PostgreSQL
    │
    │ source of truth
    ▼
Outbox
    │
    ▼
Kafka / Stream
    │
    ▼
MongoDB projection
```

Mongo becomes a **derived read model** when necessary.

Or the reverse for Mongo-native workloads:

```text id="9j5j5y"
MongoDB
   │
   ▼
Change Stream
   │
   ▼
Kafka
   │
   ├── Search
   ├── Analytics
   └── Other services
```

MongoDB Change Streams let applications subscribe to real-time data changes without continuously polling the database, and can watch collections, databases, or an entire deployment. ([mongodb.com](https://www.mongodb.com/docs/manual/changeStreams/?utm_source=chatgpt.com))

That is much better than:

```text id="3px7q8"
while True:
    mongo.find(...)
    sleep(2)
```

---

# MongoDB Change Streams should be part of your event layer

Your abstraction should look like:

```text id="k1m2j8"
                   Event Source
                       │
        ┌──────────────┼──────────────┐
        │              │              │
        ▼              ▼              ▼
   PostgreSQL       MongoDB       Application
     Outbox       Change Stream      Events
        │              │              │
        └──────────────┼──────────────┘
                       ▼
                 Event Backbone
                       │
                 ┌─────┴─────┐
                 ▼           ▼
              Redis        Kafka
                 │           │
                 ▼           ▼
              Realtime    Consumers
```

---

# MongoDB should also have a caching layer

Don't assume Mongo replaces Redis.

You can have:

```text id="z5l0or"
L1 Memory
    ↓
Redis
    ↓
MongoDB
```

for a Mongo-native workload.

Example:

```text id="x8o0ki"
GET product
 ↓
L1
 ↓ miss
Redis
 ↓ miss
Mongo
 ↓
Redis
 ↓
L1
```

---

# MongoDB-specific production features to expose

Your framework should abstract these:

```text id="xw4m0n"
MongoRepository
├── CRUD
├── bulk operations
├── transactions
├── aggregation
├── indexes
├── TTL indexes
├── change streams
├── optimistic concurrency
├── pagination
├── projections
├── sessions
├── retryable writes
└── read/write concerns
```

Particularly:

### TTL indexes

Excellent for temporary Mongo data:

```text id="3f1r4g"
sessions
temporary tokens
temporary documents
cache-like records
expiring data
```

MongoDB supports TTL indexes that automatically remove documents after a configured period. ([mongodb.com](https://www.mongodb.com/docs/manual/core/index-ttl/?utm_source=chatgpt.com))

But for ultra-hot ephemeral state, Redis is usually the better fit.

---

# MongoDB transactions

MongoDB supports multi-document transactions, but don't use them to recreate a relational database badly.

If you need:

```text id="4g5r8d"
invoice
payment
ledger
balance
```

with heavy relational invariants, PostgreSQL remains the obvious default.

If you need:

```text id="6cq3xq"
agent_state
 ├── messages
 ├── tools
 ├── context
 ├── metadata
 └── execution
```

Mongo is much more natural.

---

# MongoDB for your AI platform

This is where Mongo becomes particularly useful.

For example:

```text id="x2g7nw"
Agent
{
    identity: {...},
    configuration: {...},
    memory: {...},
    tools: [...],
    policies: [...],
    metadata: {...}
}
```

That is a natural document.

But don't put the whole platform into Mongo.

Use:

```text id="l0bqv1"
PostgreSQL
├── tenant
├── user
├── membership
├── billing
├── authorization
└── audit

MongoDB
├── agent documents
├── flexible metadata
├── extracted documents
├── integration payloads
└── dynamic schemas

Redis
├── agent runtime state
├── locks
├── rate limits
├── sessions
└── hot context
```

That's a much cleaner separation.

---

# Updated storage decision tree

I'd literally put this into your architecture documentation:

```text id="0h1s9w"
                    What is this data?
                           │
          ┌────────────────┼────────────────┐
          │                │                │
          ▼                ▼                ▼
      Relational       Document         Ephemeral
       /critical        /flexible          /hot
          │                │                │
          ▼                ▼                ▼
     PostgreSQL         MongoDB           Redis
          │                │                │
          └────────────────┼────────────────┘
                           │
                      Need events?
                           │
                    ┌──────┴──────┐
                    │             │
                   No            Yes
                    │             │
                    ▼             ▼
                  Done       Stream/Event Bus
                                  │
                           ┌──────┴──────┐
                           │             │
                       moderate        huge/replay
                           │             │
                           ▼             ▼
                     Redis Streams     Kafka
```

---

# Your complete persistence matrix now

| Requirement                 | Technology        |
| --------------------------- | ----------------- |
| Relational source of truth  | PostgreSQL        |
| Financial data              | PostgreSQL        |
| Auth/identity               | PostgreSQL        |
| RBAC                        | PostgreSQL        |
| Tenant/membership           | PostgreSQL        |
| Transactions                | PostgreSQL        |
| Complex relationships       | PostgreSQL        |
| Flexible documents          | MongoDB           |
| Dynamic schemas             | MongoDB           |
| CMS/content                 | MongoDB           |
| AI agent documents          | MongoDB           |
| Integration payloads        | MongoDB           |
| Scraped/raw structured data | MongoDB           |
| Device/IoT documents        | MongoDB           |
| Hot cache                   | Redis             |
| Sessions                    | Redis             |
| Rate limits                 | Redis             |
| Locks                       | Redis             |
| Idempotency                 | Redis + DB        |
| Presence                    | Redis             |
| Realtime fanout             | Redis Pub/Sub     |
| Short-lived stream          | Redis Streams     |
| Background jobs             | Redis Streams     |
| Durable event backbone      | Kafka             |
| DB event publishing         | Outbox / CDC      |
| Mongo event publishing      | Change Streams    |
| Search                      | OpenSearch        |
| Analytics                   | ClickHouse        |
| Files                       | S3/Object Storage |
| Long workflows              | Temporal          |
| Vector retrieval            | pgvector/Qdrant   |
| Metrics                     | Prometheus        |
| Logs                        | Loki              |
| Traces                      | OpenTelemetry     |

---

# One more thing I'd add: a Data Access Layer

For your universal backend, don't let application code directly care whether it's PostgreSQL or MongoDB.

Define:

```text id="0l1g7m"
Repository
│
├── SQLRepository
│
└── DocumentRepository
```

and:

```text id="xq4gko"
Cache
│
├── MemoryCache
└── RedisCache

EventBus
│
├── InProcessBus
├── RedisStreamBus
└── KafkaBus

Database
│
├── PostgreSQL
└── MongoDB
```

Then the application can choose the storage intentionally without becoming coupled to infrastructure.

## The resulting platform becomes

```text id="8j0v1n"
                    NoKnown Platform
                           │
       ┌───────────────────┼───────────────────┐
       ▼                   ▼                   ▼
   PostgreSQL           MongoDB              Redis
   Truth                Documents            Speed
       │                   │                   │
       └──────────────┬────┴───────────────────┘
                      ▼
                Event Abstraction
                      │
              ┌───────┴────────┐
              ▼                ▼
        Redis Streams        Kafka
              │                │
              └───────┬────────┘
                      ▼
              Workers / Services
                      │
       ┌──────────────┼───────────────┐
       ▼              ▼               ▼
   OpenSearch      ClickHouse       Object Store
```

That gives you a **polyglot persistence architecture without polyglot chaos**.

And that's the distinction I'd preserve: **support many technologies at the infrastructure boundary, but keep application-level contracts simple.**
