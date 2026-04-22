# Data Provenance — SWE-bench Verified

## Source

**Benchmark:** SWE-bench Verified  
**Task descriptions:** `princeton-nlp/SWE-bench_Verified` on HuggingFace  
**Trajectories:** SWE-agent runs on the Verified split  

Known public trajectory sources (confirm availability before acquisition):
- Local SWE-agent trajectory JSON files from a fresh SWE-agent run
- HuggingFace model submission trajectory datasets

## Acquisition command

From a local directory of SWE-agent trajectory JSON files (one per instance):

```bash
python scripts/acquire_swe.py \
    --source /path/to/swe_agent_trajectories/ \
    --out data/swe_bench_verified/ \
    --target 500
```

Or from a HuggingFace trajectory dataset:

```bash
python scripts/acquire_swe.py \
    --source <hf-dataset-id> \
    --out data/swe_bench_verified/ \
    --target 500
```

Set `HF_TOKEN` environment variable if the dataset is gated.

## Date accessed

Not yet acquired — fill in when acquisition runs.

## Schema

One trajectory per line in `trajectories.jsonl`.  Each line is a JSON object
using the same schema as `data/terminal_bench/trajectories.jsonl` with
`"source": "swe"`.

SWE-bench-specific event args:
- `file_edit` events may arise from `git diff`, `git apply`, or SWE-agent
  editor commands (`edit`, `create`, `insert`, etc.)
- `context_update` token counts are derived from `info.model_stats.tokens_sent`
  and `info.model_stats.tokens_received`

## License / consent considerations

SWE-bench Verified is a publicly released benchmark derived from GitHub issues
and pull requests in open-source repositories.  The benchmark is released under
MIT license.  Trajectory data from SWE-agent runs are generated outputs; no
additional consent is required.  Confirm license of any specific HuggingFace
trajectory dataset before publication.

## Gate 2

**Requirement:** ≥ 400 usable trajectories (spec §5, Gate 2)  
**Usable definition:** ≥ 15 parsed events AND outcome ∈ {"pass", "fail"}  
**Status:** Not yet checked — run acquire_swe.py and verify exit code 0
