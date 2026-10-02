# Local models

Binder runs the best chat model each machine supports, and checks again at every launch. Code:
`services/llm_models.py` (catalogue, choice, downloads, upgrade offer), `services/setup.py`
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

## Every launch

`setup._run` measures the machine (`setup.measure()`: RAM, NVIDIA VRAM, free disk, Ollama
version; never cached), installs a model if none is there, then `llm_models.advise`:

- The active model was **chosen by Binder** (`LlmConfig.auto`) and the recommendation ranks
  higher: the upgrade is **offered** (`/api/setup` and `/api/llm` carry `upgrade`, with its
  size), never downloaded silently. `POST /api/llm/upgrade` downloads it; Binder switches once it
  is ready, keeps the former model installed and logs the switch in the activity.
- `POST /api/llm/upgrade/decline` stores the model in `LlmConfig.declined`: not offered again
  until the recommendation becomes another model.
- **Never a downgrade**: when the active model ranks above what the memory runs, only a warning
  (`SetupStatus.warning`).
- A model **chosen by the user** (`PUT /api/llm/model`, or `BINDER_LLM_MODEL`): no offer and no
  warning; Settings > Local AI only shows the recommended model.

Settings saved before `auto` existed count as Binder's choice. Models outside the catalogue
(rank 0) are never compared.

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
   replaces another takes its rung; drop the old one from the catalogue (installed copies stay
   usable, shown as installed outside Binder).
5. **Measure** before switching the default: `scripts/evaluate.py --llm --model <tag>` and
   `scripts/evaluate_agent.py --model <tag>` (see [evaluation.md](evaluation.md),
   [agent.md](agent.md)).
6. **Tests** (`tests/test_model_choice.py`): one case per rung of the ladder, the disk fallback,
   the Ollama version fallback; update `README.md` (which model for which computer).
