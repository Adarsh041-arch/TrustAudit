# V1 Blocked: `ChatGoogleGenerativeAI` Constructor Hangs Indefinitely

**Filed:** 2026-07-26
**Status:** Open / blocking V1 execution
**Priority:** Critical (V1 is completely inoperable)

## Symptom

Every code path that constructs `ChatGoogleGenerativeAI` from `langchain-google-genai` hangs
indefinitely with no error message, no timeout, and no CPU activity. The process must be
killed externally.

```python
from langchain_google_genai import ChatGoogleGenerativeAI
model = ChatGoogleGenerativeAI(model="gemini-2.5-flash", api_key="...")
# hangs forever
```

## Affected version

| Package | Version |
|---------|---------|
| `langchain-google-genai` | **4.2.1** |
| `google-genai` | (underlying SDK, unknown) |
| `langchain-core` | (installed alongside) |

## What hangs

The constructor on line 135 of `app/vlm.py`:

```python
class VLMClient:
    def __init__(self, model_name="gemini-2.5-flash", api_key=None):
        self.model = ChatGoogleGenerativeAI(
            model=model_name,
            api_key=api_key or os.getenv("GOOGLE_API_KEY"),
            temperature=0.1,
            max_output_tokens=16384,
        )
```

Because `build_graph()` calls `get_vlm_client()` indirectly through the graph nodes, even
`from app.graph import build_graph` hangs at module level in many paths (the import itself
does not hang, but the first model construction does).

## Affected entrypoints

| Entrypoint | What happens |
|---|---|
| `python main.py` | Constructs `AuditState`, calls `graph.invoke()` → first model call hangs |
| `python evaluation/measure_v1_baseline.py` | Hangs on first document after starting iteration |
| `python -c "from app.graph import build_graph"` | Module imports OK, but `build_graph()` returns a compiled graph; any `graph.invoke()` hangs |
| `uvicorn backend.server:app` | Not tested, but likely same on first model call |
| Any test importing V1 | No V1 tests exist, but if they did — same result |

## What DOES work

The underlying `google.genai` SDK works fine directly:

```python
import google.genai
client = google.genai.Client(api_key="...")
response = client.models.generate_content(model="gemini-2.5-flash", contents="hi")
# works
```

This confirms the issue is specific to `langchain-google-genai`'s wrapper layer — likely in
its authentication, credential resolution, or async-in-sync initialization.

## Root cause hypothesis

The most likely cause is one of:

1. **Async deadlock.** `ChatGoogleGenerativeAI` in v4 may initialise an async event loop or
   background thread that deadlocks with the calling thread. This is a known class of bugs
   in LangChain's v4 genai integration (the SDK was rewritten around `google.genai` which is
   async-native).

2. **Credential resolution hang.** The constructor may attempt to resolve ADC (Application
   Default Credentials) via a network call to the metadata server, which times out or hangs
   on Windows when no metadata server is present.

3. **`google-genai` version mismatch.** `langchain-google-genai` 4.2.1 may require a specific
   `google-genai` minor version that is not installed, and the error is swallowed during
   init.

## Workaround available

The project's offline shims in `evaluation/offline_shims.py` use a `MockVLMClient` stub, but
they are only used by `measure_v1_baseline.py`. The baseline script still hangs because the
shims are installed *after* the graph import:

```python
# evaluation/measure_v1_baseline.py
from app.graph import build_graph  # module-level ChatGoogleGenerativeAI import
# ...
```

## To reproduce

```powershell
# Set a valid API key
$env:GOOGLE_API_KEY = "your-key-here"

# Run the CLI (will hang)
python main.py

# Or isolate to the constructor:
python -c "from langchain_google_genai import ChatGoogleGenerativeAI; ChatGoogleGenerativeAI(model='gemini-2.5-flash')"
```

## Tentative fixes to try

| Fix | Complexity | Notes |
|-----|-----------|-------|
| Pin `langchain-google-genai` to v3.x | Low | v3 may use the older SDK path; breaking API changes possible |
| Replace `langchain-google-genai` with raw `google.genai` calls | Medium | VLM-specific — changes `app/vlm.py` |
| Set `GOOGLE_APPLICATION_CREDENTIALS` or disable ADC | Low | If hypothesis #2 is correct |
| Pass `api_key` explicitly on every call | Low | Already being done, no effect |
| Upgrade to latest `langchain-google-genai` | Low | 4.2.1 may already be the latest |

## V2 impact

V2 does not use `langchain-google-genai` at all. Its VLM gateway (`audit_v2/gateway/`) is
designed to use the native `google.genai` SDK, which works. V1 being blocked does not block
V2 development — however, it does block re-measuring the V1 baseline for the §6 comparison
gate, and it means V1 cannot serve as a fallback during V2 rollout.
