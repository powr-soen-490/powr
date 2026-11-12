---
name: LLL - Release 1
about: Architectural Gap Idenficiation
labels: LLL
---

Don't forget to do the following:
- set the issue title properly: e.g., [LLL] [Architecture: Real-time Telemetry Pipeline] Spike - Apache Kafka Stream Processing
- set the issue milestone to "Release 1"
- assign the issue to yourself
- erase this section

## 1. Architectural Context
Explicitly cite the specific component, layer, or non-functional requirement from your System Architecture Document that this spike addresses. For example:
>In Section x.x of our architecture design, we are building the Real-time Telemetry Pipeline. Our project has a strict performance constraint: it has to process data packets from 500 sensors at the same time (around 2,000 events per second) without lagging or crashing the database. To handle this kind of load, we need an asynchronous message broker to queue the incoming data.

## 2. Knowledge Gap
State exactly why your current academic background leaves you unprepared for this task. For example:
>In SOEN 341 and 343, we only built basic monolithic apps with simple HTTP REST APIs connected directly to a SQL database. I have zero experience with event-driven streaming, message queues, or distributed systems. I don't know how to set up a broker or configure consumers safely.

## 3. Targeted Learning Plan
List the professional or primary sources (official documentation, specifications, RFCs) you will study. For example:
>I'm going to spend the next week researching these specific resources: 
> - Apache Kafka Official Docs: Reading the "Core Concepts" section to understand Topics, Partitions, and Consumer Groups
> - Confluent Developer Guides: Looking at their architectural blueprints for event-driven systems
> - node-rdkafka GitHub Repo: Reviewing their codebase examples to see how to connect Kafka to a Node.js backend.

## 4. Definition of Done
Define a measurable, technical proof-of-concept success criterion. For example:
> This spike is done when I can build a working, isolated demo in a test branch that:
> - Runs an Apache Kafka broker locally inside a Docker container.
> - Uses a script to blast 2,500 dummy JSON payloads into the queue.
> - Has a separate consumer service read and log every single payload successfully with zero data loss.
