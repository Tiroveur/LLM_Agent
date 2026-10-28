# AgentLLM

An autonomous agent that runs technical tasks inside a Docker sandbox (Ubuntu), driven by a local LLM through [Ollama](https://ollama.com) and [LangChain](https://www.langchain.com/).

Three roles share the work:

- **Strategist**: rewrites the user's request into short instructions (expected input / expected output).
- **Executor**: a tool loop (write a file, run a command, etc.) that acts inside the container.
- **Supervisor**: reads the executor's action log, approves or rejects it, and sends its remarks back for another attempt.

A security guard asks for human approval before any file write or command that looks dangerous.

## How it works

```
User task
   │
   ▼
Strategist  ──►  "input / output" instructions
   │
   ▼
Executor  ⇄  Tools  ⇄  Docker sandbox
   │
   │  report: final summary + log of tool calls
   ▼
Supervisor ── rejection + remarks ──►  new attempt (3 rounds max)
   │
   ▼ approval
Done
```

The same Ollama model can play all three roles, which avoids loading a different model into memory each time the role changes.

## Requirements

- Python 3.11 or later (the project uses `tomllib`)
- [uv](https://docs.astral.sh/uv/)
- [Docker](https://www.docker.com/)
- [Ollama](https://ollama.com), with a model that supports native tool calling

Tested setup: Windows for Ollama and WSL environment, RTX 4070 Laptop (8 GB VRAM), 32 GB RAM.

## Installation

```bash
git clone https://github.com/Tiroveur/LLM_Agent.git
cd AgentLLM
uv sync
ollama pull maternion/mimo-v2.6-heretic:9b
```

## Preparing the container

The agent connects to a container that is **already running** (default name: `agent-sandbox`). The `ShareFolder` directory is mounted read-only at `/mnt/shared`: the agent reads your files there and works only in `/tmp`.

Example in PowerShell:

```powershell
docker run -d --name agent-sandbox `
  -v "${PWD}\ShareFolder:/mnt/shared:ro" `
  ubuntu:24.04 sleep infinity

docker exec agent-sandbox bash -c "apt-get update && apt-get install -y python3"
```

`python3` is required inside the container, because file writing goes through a small Python script. Adapt the commands to your image and needs (see the Security section to harden the container).

## Usage

```bash
uv run python -m agentllm.main
```

Options:

| Option | Default | Description |
|---|---|---|
| `--max-steps`, `-m` | `15` | Maximum number of agent iterations per attempt |
| `--container`, `-c` | `agent-sandbox` | Name of the Docker container to use |

Then type your task at the prompt, for example:

```
write a Python script that lists the files in /mnt/shared and saves the result in /tmp/list.txt
```

The strategist rewrites the request, the executor carries it out, then the supervisor approves it or asks for a fix (3 attempts at most).

> Depending on how `pyproject.toml` is configured, the launch command may instead be `uv run python src/agentllm/main.py`.

> The interactive prompts and security alerts are currently in French.

## Configuration

Shared settings are defined at the top of `src/agentllm/multi_agent.py`:

| Constant | Current value | Purpose |
|---|---|---|
| `MODEL` | `maternion/mimo-v2.6-heretic:9b` | Ollama model used by all three roles |
| `NUM_CTX` | `8192` | Context window size |

Keep the **same model and the same `NUM_CTX`** everywhere: Ollama reloads the model whenever the parameters change, which slows things down a lot.

Choosing a model according to your VRAM (validate with `src/debug.py`):

| VRAM | Models to try |
|---|---|
| 8 GB | `qwen3:8b`, `maternion/mimo-v2.6-heretic:9b` |
| 12 to 16 GB | `qwen3:14b`, `gpt-oss:20b` |
| 24 GB or more | `qwen3-coder:30b` |

## Agent tools

| Tool | Purpose |
|---|---|
| `write_file` | Writes a file in `/tmp` (content sent as Base64) |
| `edit_file` | Makes a targeted edit to an existing file |
| `extract_archive` | Extracts an archive |
| `run_bash` | Runs a command in the container |
| `finish_task` | Ends the task and provides the final summary |

## Security

The guard (`src/agentllm/security.py`) analyses the content of files being written and commands being run, including the content of `/tmp/...` scripts referenced in a command. When it finds a suspicious pattern (recursive deletion, disk formatting, network access, dynamic code execution, etc.), it shows the alert and asks for confirmation:

- `o` (or `y`): allow this once
- `n`: refuse (the agent is told and must find another approach)
- `t`: allow and stop asking for this exact content for the rest of the session

The rules live in `src/agentllm/security_rules.toml`: add, remove or change them without touching the code. Each rule has a level (`HIGH` or `MEDIUM`), a regular expression and a reason shown on screen.

**Limitations to be aware of:**

- These rules are a safety net, not a boundary: obfuscated or dynamically built code can slip through.
- The real safeguard is the container. Consider starting it with `--memory`, `--pids-limit`, `--security-opt no-new-privileges`, a non-root user, and never mounting `docker.sock`. Note that `--cap-drop ALL` can prevent `apt-get` from working; preinstall the packages in the image in that case.
- If you use a model modified to remove its refusals ("abliterated", "heretic"), it has no safeguards of its own: your human approvals and the sandbox are then your only protection.

## Project structure

```
.
├── LICENSE
├── README.md
├── README.fr.md
├── pyproject.toml
├── uv.lock
├── ShareFolder/                  # mounted read-only at /mnt/shared
└── src/
    ├── debug.py                  # quick tool-calling test for an Ollama model
    └── agentllm/
        ├── main.py               # entry point (interactive loop)
        ├── agent.py              # executor: tool loop, report for the supervisor
        ├── multi_agent.py        # strategist + supervisor, MODEL / NUM_CTX constants
        ├── sandbox.py            # connection to the Docker container
        ├── security.py           # guard and human approval
        ├── security_rules.toml   # editable detection rules
        └── tools/                # tools exposed to the LLM
```

## Troubleshooting

**The model writes JSON in its reply instead of calling a tool.**
Some models (notably `qwen2.5-coder`) do not emit the tags that Ollama's template expects, so the call stays in the text. The agent includes a fallback that recovers this JSON, but switching models is the most reliable fix. Test with `src/debug.py`: the response should contain a `tool_calls` key. Make sure the instruction is sent with the `user` role, not `system`.

**The model is slow or inconsistent.**
Check with `ollama ps` that the model fits in VRAM (ideally `100% GPU`). Lower `NUM_CTX` if a CPU share appears, and enable:

```powershell
setx OLLAMA_FLASH_ATTENTION 1
setx OLLAMA_KV_CACHE_TYPE q8_0
```

then restart Ollama. The agent prints a `[timing]` line on each call (loading, prompt, generation) to help find the cause of slowdowns.

**`Impossible de démarrer l'agent ou Docker` (agent or Docker failed to start).**
Check that the container exists and is running (`docker ps`) and that its name matches the `--container` option.

## License

See the [LICENSE](LICENSE) file.
