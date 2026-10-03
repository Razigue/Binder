# Local models

Binder runs the best chat model each machine supports, and checks again at every launch. Code:
`services/llm_models.py` (catalogue, choice, downloads, upgrades, cleanup), `services/setup.py`
(measuring the machine, `pick_model`, Binder's own Ollama).

## Choosing the model

`setup.memory_tier(ram, vram, apple)` climbs a ladder of named thresholds (`DENSE_VRAM`,
`DENSE_APPLE_RAM`, `MOE_BUDGET`, `MID_VRAM`, `MID_RAM`, `SMALL_RAM`, each with the reason in a
comment). The memory budget is RAM + VRAM, or RAM alone on Apple silicon (unified memory):

| Machine | Model |
| --- | --- |
| VRAM ≥ 20 GB, or Apple with RAM ≥ 48 GB | `qwen3.6:27b` (dense) |
| budget ≥ 32 GB, with or without a GPU | `qwen3.6:35b-a3b` (MoE, ~3B active per token) |
| VRAM ≥ 8 GB or RAM ≥ 15 GB | `qwen3.5:9b` |
| RAM ≥ 10 GB (or unknown) | `qwen3.5:4b` |
| less | `qwen3.5:2b` |

A mixture of experts reads only a few experts per token: Ollama keeps in RAM the layers the
graphics card cannot hold and the model stays fast, which is why the 35B-A3B wins over the dense
9B even on a processor alone. `pick_model` then steps down the ranks while the free disk lacks
`size × DISK_MARGIN`, or while the running Ollama is older than the model's `min_ollama`.

## What each model is given

`llm.Profile`, by model (`llm.PROFILES`; any other model gets `SMALL`):

| Profile | Models | Context | Document text | Agent tools | Reasoning on hard tasks |
| --- | --- | --- | --- | --- | --- |
| `SMALL` | 2B, 4B, 9B, outside the catalogue | 16k | 8,000 characters | 10, chosen per request | no |
| `LARGE` | 35B-A3B, 27B | 32k | 24,000 characters | all | with a graphics card |

Qwen 3.5 and 3.6 keep a key-value cache on a quarter of their layers only: a larger window costs
little memory. Every chat request uses the same window, or Ollama would reload the model.
`BINDER_LLM_CONTEXT` overrides the window. Reasoning (`llm.think_hard()`) is used for the rare,
decisive tasks: composing a letter and the second reading of doubted values. It needs the large
profile and a machine measured with a graphics card of 8 GB or more, or Apple silicon
(`setup._run`): on a processor alone it takes minutes per task. `BINDER_LLM_THINK=true` turns it
on for any model. The legal check's judgement does not reason: measured as accurate without it,
and minutes faster.

**Loaded ahead, kept loaded.** Once setup is ready, when the active model changes and when the
chat opens (`POST /api/llm/warm`, only if Ollama let the model go), `llm.warm()` loads the model
in the background with the requests' window and reads the agent's fixed prompt start once
(`loop.warm_prefix`: system prompt and tool schemas, `num_predict: 1`). Ollama keeps it in its
prompt cache, so a question only reads its own words instead of ~4,000 tokens, and the graphics
card's kernels and the speculative decoding are warmed up. Measured on an RTX 4080 Super with the
35B-A3B: a cold "hello" took 37 s (8 tok/s shown), the warm path answers in about a second at
~80 tok/s. Keep the prefix stable for this to work: the large profile sends every tool in a fixed
order, never reordered per request. With Binder's own Ollama the model stays loaded for the whole
session (`llm.keep_alive()`: `-1`; 30 minutes on a shared Ollama; `BINDER_LLM_KEEP_ALIVE`
overrides). A question asked while the model loads shows "Loading the local AI" (stream event
`loading`), and the load time appears apart in the answer's details (`ChatStats.load_seconds`),
never mixed into the model's speed.

**Same sender, same reading.** Before reading a document, `learning.example` looks for the issuer
of the library that its first lines name (the longest, so "EDF Entreprises" beats "EDF") and
shows the model how the last filed document of that issuer was read: category, type, issuer,
title, and which fields it had (not their values). Corrections the user made still apply after
the model (`learning.apply`). The evaluation (`scripts/evaluate.py`) reads each document alone,
without the example.

## Every launch

`setup._run` measures the machine (`setup.measure()`: RAM, graphics memory, free disk, Ollama
version; never cached), installs a model if none is there, then `llm_models.advise`. Graphics
memory is what Binder's Ollama reported at its start (`setup.ollama_gpu_bytes`, the
`inference compute` lines of `ollama.log`: NVIDIA, AMD, Intel, Vulkan alike, integrated graphics
left out), or `nvidia-smi`, whichever is larger.

Every user gets the best local AI their machine runs without thinking about it:

- The active model was **chosen by Binder** (`LlmConfig.auto`) and the recommendation ranks
  higher: the upgrade **downloads in the background** right away (`/api/setup` and `/api/llm`
  carry `upgrade`, `accepted`, with its progress). Binder switches once it is ready, deletes the
  former model and logs both in the activity.
- `POST /api/llm/upgrade/decline` stops it and stores the model in `LlmConfig.declined`: not
  fetched again until the recommendation becomes another model.
- **Never a downgrade**: when the active model ranks above what the memory runs, only a warning
  (`SetupStatus.warning`).
- A model **chosen by the user** (`PUT /api/llm/model`, or `BINDER_LLM_MODEL`): no offer and no
  warning; Settings > Local AI only shows the recommended model.

Settings saved before `auto` existed count as Binder's choice. Models outside the catalogue
(rank 0) are never compared.

**Only the models in use stay on the disk** (`llm_models.prune`, at each launch and after an
upgrade): every catalogue model and every `RETIRED` one other than the active chat model is
deleted from Binder's own Ollama, and logged. Never in a shared Ollama (other apps use it), never
a model installed outside Binder, never while a download runs (layers are shared), and never
before the active model is installed.

## Adding a model

At each new generation of models:

1. **Check the tag on the registry.** Size: the sum of the layers of
   `https://registry.ollama.ai/v2/library/<model>/manifests/<tag>`. Oldest Ollama that runs it:
   `requires` in the config blob of that manifest. Capabilities: the model's page on ollama.com
   must show **vision** and **tools** (Binder reads scans and calls tools).
2. **Ollama.** If `requires` is newer than `setup.OLLAMA_VERSION`, upgrade the pinned version and
   its checksums (see [configuration.md](configuration.md#local-ai-setup)). Raise
   `llm.MIN_OLLAMA_VERSION` only if every model needs it; otherwise set the entry's `min_ollama`.
3. **Catalogue** (`llm_models.CATALOG`): name, label and description keys, size, `rank` and
   `min_ollama`. Add `label_*` and `desc_*` in EN and FR to the catalogue `T`. Ranks order
   quality: renumber so the new model sits where it belongs; they must stay distinct.
4. **Thresholds** (`setup.memory_tier`): give the model its rung, as a named constant with a
   comment saying why (weights size, active parameters, what must fit in VRAM). A model that
   replaces another takes its rung; move the old one from the catalogue to
   `llm_models.RETIRED`, so the next launch deletes it from users' disks once they have the new
   one (they get the upgrade automatically).
5. **Measure** before switching the default: `scripts/evaluate.py --llm --model <tag>` and
   `scripts/evaluate_agent.py --model <tag>` (see [evaluation.md](evaluation.md),
   [agent.md](agent.md)).
6. **Profile** (`llm.PROFILES`): a model that runs on large machines only gets `LARGE`.
7. **Tests** (`tests/test_model_choice.py`): one case per rung of the ladder, the disk fallback,
   the Ollama version fallback; update `README.md` (which model for which computer).
