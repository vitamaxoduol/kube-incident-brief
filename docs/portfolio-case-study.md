# kube-incident-brief portfolio case study

I developed kube-incident-brief as a personal backend and reliability engineering
project, using AI assistance for implementation, code walkthroughs, and debugging.
The result is a local FastAPI service that turns supplied Kubernetes events,
logs, or policy excerpts into a structured incident brief. It combines a Gemini
integration with input validation, evidence citations, request timeouts, and
repeatable offline tests.

An on-call engineer needs to distinguish what an event reports from what might
explain it. A failed image pull and a registry timeout establish a symptom, but
do not identify its cause. The project explores how an AI-generated summary can
help organize that evidence while keeping uncertainty visible and giving the
engineer specific next checks.

The API exposes one endpoint, `POST /incidents/analyze`. It accepts an ordered
list of evidence strings and returns observations, possible causes, and next
checks. Each observation and hypothesis cites the submitted items using IDs
assigned by the application. Possible causes can remain empty when the evidence
does not support an explanation.

The implementation separates three responsibilities: [Pydantic schemas](../app/schemas.py)
define accepted data, a small [Gemini function](../app/gemini.py) handles the
external request, and the [FastAPI endpoint](../app/main.py) coordinates
generation, validation, and HTTP responses. Input is limited to 1–30 items of
1–2,000 characters after trimming. Returned JSON is validated in Python, including
checking every citation against the evidence count. Provider calls have a
30-second deadline with SDK retries disabled. Missing configuration, timeouts,
and upstream failures produce controlled errors without exposing raw provider
messages or evidence values.

Two [fictional examples](../examples/) demonstrate the intended behavior. The
first contains a Harbor image-pull timeout and kubelet backoff. The second adds
a clearly labeled synthetic Kyverno policy excerpt that rewrites matching image
references to the Harbor mirror. That extra evidence suggests a possible
explanation for the Harbor reference, but it does not prove that the policy
mutated this particular pod or caused the timeout. The demo shows how additional
context can inform an investigation while leaving its central questions open.

Live testing exposed a bug in the AI-assisted implementation. The offline tests
passed, but the endpoint returned HTTP 502. Inspecting a sanitized provider
diagnostic showed that Gemini had rejected an `additional_properties` field
emitted by the SDK's `response_schema` conversion. The original mock verified
parts of the request and supplied a successful response; it did not reproduce
the provider's schema acceptance rules.

The fix used `response_json_schema=IncidentBrief.model_json_schema()` to send the
Pydantic-generated JSON Schema through the SDK's native JSON Schema option.
Python's strict response and citation validation remained in place. The
[SDK request test](../tests/test_gemini.py) was strengthened to check the actual
serialized field, reject the previously problematic spelling, and preserve the
rules forbidding extra properties and requiring citations. The updated test
failed against the previous implementation and passed after the correction.
Subsequent live requests for both examples returned HTTP 200. This was a useful
lesson in reviewing generated code: a passing mock test is evidence about the
behavior it exercises, while provider compatibility also needs live verification.

Verification during development included **54 passing offline tests**, a fresh
Python 3.12 environment installation, and checks of the documented Uvicorn startup
command. Tests cover successful requests, input boundaries, invalid citations,
malformed output, missing credentials, and timeout handling. They use fake
provider functions or an HTTP mock transport through the real SDK; automated
tests require no Gemini key. A [GitHub Actions workflow](../.github/workflows/tests.yml)
installs dependencies and runs pytest on pushes and pull requests. The live
examples were verified using `gemini-3.5-flash-lite`; the configured default,
`gemini-3.5-flash`, was not live-verified.

The outcome is a runnable portfolio prototype demonstrating an AI API integration
and the engineering checks around it. It has no cluster access and executes no
commands. It sends submitted evidence to Gemini, has no authentication or rate
limiting, and is intended for local use. Prompt instructions encourage grounded
reasoning and read-only suggestions, but cannot guarantee either. Citation
validation proves that an evidence item exists, not that it supports the model's
claim. The two live examples are smoke tests, not a measurement of diagnostic
accuracy, production reliability, or incident-resolution time.

Reviewers can follow the [README](../README.md) to run the offline suite and try
both examples with their own key. The project demonstrates input and output
validation, dependency injection, provider error handling, regression testing,
and reviewing AI-assisted work against observable behavior.
