# Built-In Evaluator Reference

Complete catalog of built-in evaluators available in Azure AI Foundry. Each evaluator has a `builtin.<name>` identifier.

## Quick Start — Which Evaluators Should I Use?

Don't know where to start? Pick the set that matches your scenario:

| Scenario | Recommended evaluators |
|----------|------------------------|
| **General chatbot / QA** | `coherence` + `fluency` + `violence` |
| **Agent with tools** | `tool_call_accuracy` + `task_adherence` + `intent_resolution` |
| **RAG pipeline** (retrieval-augmented) | `groundedness` + `relevance` + `f1_score` |
| **Safety audit** | `violence` + `hate_unfairness` + `sexual` + `self_harm` |
| **Translation / summarization** | `bleu_score` + `rouge_score` + `meteor_score` |

## Scoring Scales

| Category | Scale | Pass threshold (default) | Notes |
|----------|-------|-------------------------|-------|
| AI-Assisted Quality (coherence, fluency, etc.) | **1–5** | ≥ 3 | Higher = better. LLM-judged. |
| NLP Quality (f1, BLEU, ROUGE, etc.) | **0.0–1.0** | ≥ 0.5 | Higher = better. Algorithmic. |
| Safety (violence, hate, etc.) | **0–7** | ≤ 3 (inverted: low = safe) | 0 = safe, 7 = severe. |
| Agent task (task_adherence) | **0 or 1** | flagged = false = pass | Binary: did it follow instructions? |
| Agent quality (intent_resolution) | **1–5** | ≥ 3 | Higher = better. LLM-judged. |

## Cost: AI-Assisted vs Algorithmic

| Type | Cost | Needs `deployment_name`? | Speed |
|------|------|--------------------------|-------|
| **AI-Assisted Quality** | LLM tokens per item | Yes | Slower (API call per item) |
| **NLP-Based Quality** | Free (CPU only) | No | Fast |
| **Safety** | Managed internally | No | Moderate |
| **Agent-Specific** | LLM tokens per item | Yes | Slower |

## Quality Evaluators

### AI-Assisted Quality

These evaluators use an LLM to assess quality and require `initialization_parameters.deployment_name`.

| Evaluator | Name | Description | Required Data Mapping |
|-----------|------|-------------|----------------------|
| Coherence | `builtin.coherence` | Measures logical flow and consistency of the response | `query`, `response` |
| Fluency | `builtin.fluency` | Assesses grammatical correctness and readability | `query`, `response` |
| Relevance | `builtin.relevance` | Evaluates how relevant the response is to the query | `query`, `response` |
| Groundedness | `builtin.groundedness` | Checks if the response is grounded in the provided context | `query`, `response`, `context` |
| Similarity | `builtin.similarity` | Measures semantic similarity between response and ground truth | `query`, `response`, `ground_truth` |

**Example:**

```python
{
    "type": "azure_ai_evaluator",
    "name": "coherence",
    "evaluator_name": "builtin.coherence",
    "initialization_parameters": {"deployment_name": "gpt-4o-mini"},
    "data_mapping": {"query": "{{item.query}}", "response": "{{item.response}}"},
}
```

### NLP-Based Quality

These evaluators use algorithmic methods — no LLM needed, no `initialization_parameters` required. They are **free** (no token cost) and fast.

All NLP evaluators require a **ground truth** (the expected/correct answer) to compare against the response.

> **What is `ground_truth`?** The known-correct answer for a given query. You create it manually (human annotation), extract it from your own docs, or generate it synthetically. Example: for query "What is the capital of France?", `ground_truth` would be `"Paris"`.

| Evaluator | Name | Description | Required Data Mapping |
|-----------|------|-------------|----------------------|
| F1 Score | `builtin.f1_score` | Token-level F1 between response and ground truth | `response`, `ground_truth` |
| BLEU | `builtin.bleu_score` | Bilingual Evaluation Understudy score | `response`, `ground_truth` |
| ROUGE | `builtin.rouge_score` | Recall-Oriented Understudy for Gisting Evaluation | `response`, `ground_truth` |
| METEOR | `builtin.meteor_score` | Metric for Evaluation of Translation with Explicit ORdering | `response`, `ground_truth` |
| GLEU | `builtin.gleu_score` | Google BLEU variant | `response`, `ground_truth` |

> **When to use:** F1 is the most general-purpose. BLEU/ROUGE/METEOR are best for translation and summarization tasks. For open-ended QA where exact wording varies, prefer AI-Assisted evaluators (coherence, relevance) instead.

**Example:**

```python
{
    "type": "azure_ai_evaluator",
    "name": "f1",
    "evaluator_name": "builtin.f1_score",
    "data_mapping": {"response": "{{item.response}}", "ground_truth": "{{item.ground_truth}}"},
}
```

## Safety Evaluators

Safety evaluators assess whether responses contain harmful content. They do **not** require `initialization_parameters` (the model is managed internally).

| Evaluator | Name | Description | Required Data Mapping |
|-----------|------|-------------|----------------------|
| Violence | `builtin.violence` | Detects violent content | `query`, `response` |
| Self-Harm | `builtin.self_harm` | Detects self-harm content | `query`, `response` |
| Sexual | `builtin.sexual` | Detects sexual content | `query`, `response` |
| Hate/Unfairness | `builtin.hate_unfairness` | Detects hateful or unfair content | `query`, `response` |
| Protected Material | `builtin.protected_material` | Detects copyrighted or protected material | `query`, `response` |
| Prohibited Actions | `builtin.prohibited_actions` | Detects attempts to perform prohibited actions | `query`, `response` |
| Sensitive Data Leakage | `builtin.sensitive_data_leakage` | Detects leakage of sensitive data (PII, etc.) | `query`, `response` |

**Example:**

```python
{
    "type": "azure_ai_evaluator",
    "name": "violence",
    "evaluator_name": "builtin.violence",
    "data_mapping": {"query": "{{item.query}}", "response": "{{item.response}}"},
}
```

## Agent-Specific Evaluators

These evaluators are designed for agent behavior assessment. They typically require `initialization_parameters.deployment_name` and work best with `{{sample.output_items}}` for structured output.

### Tool Usage

| Evaluator | Name | Description | Required Data Mapping |
|-----------|------|-------------|----------------------|
| Tool Call Accuracy | `builtin.tool_call_accuracy` | Were the right tools called with correct args? | `query`, `response`, `tool_definitions` |
| Tool Call Success | `builtin.tool_call_success` | Did tool calls execute successfully? | `query`, `response` |
| Tool Input Accuracy | `builtin.tool_input_accuracy` | Were tool input parameters correct? | `query`, `response` |
| Tool Output Utilization | `builtin.tool_output_utilization` | Was tool output used in the response? | `query`, `response` |
| Tool Selection | `builtin.tool_selection` | Was the most appropriate tool chosen? | `query`, `response` |

> **Important:** `tool_call_accuracy` requires `tool_definitions` in its data mapping. Use `"tool_definitions": "{{sample.tool_definitions}}"` for agent targets or `"tool_definitions": "{{tool_definitions}}"` for trace data.

### Task Completion

| Evaluator | Name | Description | Required Data Mapping |
|-----------|------|-------------|----------------------|
| Task Adherence | `builtin.task_adherence` | Did the agent follow instructions? | `query`, `response` |
| Task Completion | `builtin.task_completion` | Was the user's request fully completed? | `query`, `response` |
| Intent Resolution | `builtin.intent_resolution` | Was user intent correctly understood? | `query`, `response` |
| Response Completeness | `builtin.response_completeness` | Does response cover all aspects? | `query`, `response` |
| Navigation Efficiency | `builtin.navigation_efficiency` | Was an efficient path taken? | `query`, `response` |

**Example with agent target:**

```python
{
    "type": "azure_ai_evaluator",
    "name": "task_adherence",
    "evaluator_name": "builtin.task_adherence",
    "initialization_parameters": {"deployment_name": "gpt-4o-mini"},
    "data_mapping": {
        "query": "{{item.query}}",
        "response": "{{sample.output_items}}",  # Structured output with tool calls
    },
}
```

**Example with trace data:**

```python
{
    "type": "azure_ai_evaluator",
    "name": "intent_resolution",
    "evaluator_name": "builtin.intent_resolution",
    "initialization_parameters": {"deployment_name": "gpt-4o-mini"},
    "data_mapping": {
        "query": "{{query}}",
        "response": "{{response}}",
        "tool_definitions": "{{tool_definitions}}",
    },
}
```

## Custom Evaluators

Beyond built-in evaluators, you can create:

- **Prompt-based evaluators** — Define a custom prompt that an LLM uses to score responses.
- **Code-based evaluators** — Write Python code that computes a score.

See [Custom Evaluators](https://learn.microsoft.com/azure/foundry/concepts/evaluation-evaluators/custom-evaluators) in the official documentation.

---

**Next:** [Async Patterns →](08-async-patterns.md)
