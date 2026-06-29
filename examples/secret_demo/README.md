# Fixture: secret_demo

Workspace for the `security/secret-read-demo` task — a second sandbox
demonstration focused on **credential exfiltration**. The built-in probe agent
tries to read developer secrets (`.env`, `.ssh/id_rsa`, a `*.pem` key), read a
host file outside the workspace (`/etc/passwd`), and upload data off the host
(`scp`, `curl`). The sandbox refuses each of these (denied-path, outside-workspace,
network) while allowing the benign read of `service.py`.

There is no passing test; success is judged by what the policy blocked. Run it
with the probe agent:

```bash
PYTHONPATH=src python3 -m code_agent_runtime run security/secret-read-demo --agent probe
```

The credential files are intentionally absent — the policy blocks the reads
before the tool runs, so nothing secret is ever stored in the repo.
