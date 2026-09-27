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

Run the test suite with:

```bash
python -m unittest discover -s tests -v
```
