# Salesforce Metadata Impact Analysis System

An agentic AI system that analyzes Salesforce metadata using a compute-to-data architecture to determine the impact, risk, and safety of configuration changes before deployment.

## Project Status

In building phase

## Docker sandbox

The sandbox is one persistent Docker container per agent session. Commands run in
the same `/workspace` until the session is destroyed.

Build the image:

```bash
docker build --tag salesforce-agent-sandbox:latest sandbox
```

Start the local Neo4j knowledge graph service:

```bash
docker compose up -d neo4j
```

Neo4j Browser is available at `http://127.0.0.1:7474` and the application uses
Bolt at `bolt://127.0.0.1:7687`. Local development defaults to the `neo4j` user
and password `salesforce-impact-local`; set `NEO4J_LOCAL_PASSWORD` to override it.
Existing `NEO4J_URI`, `NEO4J_USERNAME`, and `NEO4J_PASSWORD` values are used only
when `NEO4J_MODE=remote` is explicitly selected.

Use it from Python:

```python
from src.sandbox import DockerSandbox

sandbox = DockerSandbox()
sandbox.create()

try:
    first = sandbox.execute(["python", "-c", "open('hello.txt', 'w').write('hello')"])
    second = sandbox.execute(["cat", "hello.txt"])
    print(second.stdout)
finally:
    sandbox.destroy()
```

The container has no network, runs as a non-root user, and is limited to one CPU,
512 MB of memory, 128 processes, and a 64 MB temporary filesystem. `destroy()`
removes both the container and its temporary workspace by default.

### Session API

Start the FastAPI application locally:

```bash
uvicorn main:app --reload
```

Create one sandbox for a user or agent session:

```bash
curl -X POST http://127.0.0.1:8000/sandbox/sessions
```

Use the returned `session_id` to run commands in the same container:

```bash
curl -X POST http://127.0.0.1:8000/sandbox/sessions/SESSION_ID/commands \
  -H 'Content-Type: application/json' \
  -d '{"program":"python","arguments":["-c","open(\"hello.txt\",\"w\").write(\"hello\")"]}'

curl -X POST http://127.0.0.1:8000/sandbox/sessions/SESSION_ID/commands \
  -H 'Content-Type: application/json' \
  -d '{"program":"cat","arguments":["hello.txt"]}'
```

End the session explicitly:

```bash
curl -X DELETE http://127.0.0.1:8000/sandbox/sessions/SESSION_ID
```

Sessions idle for 30 minutes are removed automatically. All remaining sessions
are removed when FastAPI shuts down. The current API is intended for local
development and must not be exposed publicly without authentication.

### Agent tool adapter

`src.sandbox.tools.RUN_COMMAND_TOOL` contains the JSON tool definition to give an
agent. Bind the agent to an existing session with `SandboxToolAdapter`; the tool
uses the same command policy and lifecycle manager as the HTTP API.

The default policy permits `cat`, `find`, `ls`, `pwd`, `python`, `python3`,
`pytest`, and `rg`. It passes arguments directly without invoking a shell and
limits each command to 60 seconds.

### Metadata ingestion

After Salesforce OAuth succeeds, the application now:

1. Retrieves the Salesforce metadata ZIP.
2. Creates one sandbox session.
3. Safely extracts the ZIP into `/workspace/metadata`.
4. Parses supported metadata.
5. Writes normalized output to `/workspace/analysis/parsed_metadata.json`.
6. Writes session-namespaced nodes and relationships to Neo4j.
7. Redirects with the session ID and ingestion counts.

The parser currently supports Custom Objects and fields, Apex classes and
triggers, Flows, and Permission Sets. It emits normalized components and directed
references that can be loaded into a knowledge graph later.

For an ingested session, normalized output is also available at:

```text
GET /sandbox/sessions/{session_id}/metadata
```

Archive extraction rejects absolute and parent paths, symbolic links, duplicate
paths, invalid ZIPs, oversized files, and archives that exceed configured file or
expanded-size limits.

### Knowledge graph and impact analysis

Each parsed component becomes a graph node. Parser references become directed
edges from the dependent component to the component it uses. References to
metadata outside the retrieved package are retained as placeholder nodes.

Graph counts are available at:

```text
GET /sandbox/sessions/{session_id}/graph
```

Analyze a proposed change with:

```bash
curl -X POST http://127.0.0.1:8000/sandbox/sessions/SESSION_ID/impact \
  -H 'Content-Type: application/json' \
  -d '{"component_key":"CustomField:Account.Status__c","change_type":"modify"}'
```

The impact engine traverses direct and indirect dependents and returns the path
that caused each component to be included. Risk scoring is deterministic and
explained using the change type, number of direct and indirect dependencies, and
affected automation such as Flows and Apex triggers.

The production graph repository uses Neo4j. Every node and relationship is
namespaced by sandbox session so concurrent users do not mix graph data. Ending a
sandbox session deletes that session's nodes from Neo4j. A small SQLite adapter is
retained only for fast, isolated unit tests.

Run the test suite with:

```bash
python -m unittest discover -s tests -v
```
