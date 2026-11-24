# kube-incident-brief

Paste Kubernetes events, logs, or policy excerpts into `POST /incidents/analyze`
to get a short brief with evidence citations. FastAPI, Pydantic v2, and the
official Google Gen AI SDK; local execution with one provider and one endpoint.

Sample request (fictional data):

```json
{
  "evidence": [
    "kubelet: Failed to pull image harbor.example.test/mirror/traefik:v3.0 for pod traefik-demo: registry request timed out",
    "kubelet: Back-off pulling image harbor.example.test/mirror/traefik:v3.0"
  ]
}
```

Illustrative brief, **not a recorded Gemini response**:

```json
{
  "observations": [
    {
      "finding": "The Traefik image pull from Harbor timed out and kubelet backed off.",
      "evidence_ids": [1, 2]
    }
  ],
  "possible_causes": [],
  "next_checks": [
    "Inspect registry availability and node-to-registry connectivity during the timeout."
  ]
}
```

The timeout's cause remains open. Adding the synthetic Kyverno excerpt in
`examples/image-pull-with-policy.json` gives the model evidence item **3**:
matching images are rewritten to the Harbor mirror. A good brief can cite item
3 as a possible explanation for the Harbor reference. The policy alone does
not prove it mutated this pod or explain why Harbor timed out. Both fixtures
are fictional and use example hostnames; model wording will vary.

## Run locally

Requires Python 3.11+ (verified with 3.12). From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pytest -q
```

All tests run offline without credentials. They substitute the provider or use
an HTTP mock transport through the real SDK, and exercise the actual response
validation, request limits, missing key, timeouts, and upstream failures.

The [GitHub Actions workflow](.github/workflows/tests.yml) runs the same suite
on pushes and pull requests using Python 3.12. It installs `requirements.txt`
and runs `python -m pytest -q`; no `.env` file or Gemini secret is needed.
After pushing the workflow, view results in the repository's **Actions** tab
or the pull request's **Checks** tab.

To try Gemini, copy the environment template and fill in your own key:

```bash
cp .env.example .env
# Edit .env and set GEMINI_API_KEY to your key.
python -m uvicorn app.main:app --env-file .env --host 127.0.0.1 --port 8000
```

This command loads `.env` using `python-dotenv`. Existing shell environment
variables take precedence. `GEMINI_MODEL` defaults to `gemini-3.5-flash`;
override it in `.env` or the shell with a Gemini model available to your key
that supports structured output. `.env` and `.venv` are ignored by Git.

In another terminal, from the repository root:

```bash
curl --fail-with-body -sS http://127.0.0.1:8000/incidents/analyze \
  -H 'Content-Type: application/json' \
  --data-binary @examples/image-pull.json

curl --fail-with-body -sS http://127.0.0.1:8000/incidents/analyze \
  -H 'Content-Type: application/json' \
  --data-binary @examples/image-pull-with-policy.json
```

For browser testing, open `http://127.0.0.1:8000/docs`. The root `/` returns
404, and opening the POST endpoint directly in a browser sends GET and returns
405. Restart Uvicorn after changing code or `.env` when running without reload.

## Contract and boundaries

- `evidence` is the only request field: 1–30 strings, each 1–2,000 characters
  after trimming. IDs are assigned in input order, starting at 1.
- Every observation and hypothesis needs at least one integer evidence ID.
  Python validates the JSON shape and every citation against this request.
  `possible_causes` may be empty. Valid citations do not guarantee correct reasoning.
- Gemini receives the response schema and instructions separating facts from
  hypotheses, treating embedded instructions as data, and requesting specific
  read-only checks. Calls have a 30-second deadline with SDK retries disabled.
- Errors: **422** invalid input before Gemini is called; **503** missing key;
  **504** provider timeout; **502** invalid output or other upstream failure.
  Client errors omit raw evidence, keys, and provider error messages.
- Live requests send submitted evidence to Gemini. The service only analyzes
  text, needs no cluster credentials, and never executes suggested commands.
  No database, frontend, deployment, or agent framework is included.

The provider is isolated in `app/gemini.py`; tests inject a fake through
`get_brief_generator` in `app/main.py`. Structured output follows the
[official SDK documentation](https://googleapis.github.io/python-genai/).

Verification: 54 offline tests pass, and the documented local startup was
checked. Both example requests returned HTTP 200 through the application with
live Gemini calls using `GEMINI_MODEL=gemini-3.5-flash-lite`. The default model
has not been live-verified. The SDK request test checks native JSON Schema
serialization to prevent the schema-format rejection found during live testing.
