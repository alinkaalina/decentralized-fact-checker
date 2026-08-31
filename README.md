# Decentralized Fact-Checker

> An on-chain AI fact-checker for GenLayer. This smart contract autonomously fetches web content and uses LLM consensus to verify whether a specific claim is supported by the provided URL. Built for transparent, decentralized truth verification.

## 📖 Overview

The **WebFactChecker** contract acts as a decentralized oracle for truth. Instead of relying on a centralized API to verify claims, it leverages GenLayer's Intelligent Contracts to fetch live web data and uses an LLM consensus mechanism to determine if a specific statement is backed by the provided source.

This contract is designed with strict on-chain auditability in mind, preserving both the fetched evidence and the AI's reasoning for complete transparency.

## ⚙️ Architecture & GenLayer Integration

This contract heavily utilizes GenLayer's unique non-deterministic features and Equivalence Principles to ensure a secure and deterministic state across validators:

1. **Deterministic Web Fetching (`strict_eq`)**: 
   The contract uses `gl.nondet.web.get` wrapped in `gl.eq_principle.strict_eq`. This ensures that the leader node fetches the live web page, and validator nodes rigorously verify the exact same HTML payload, preventing state divergence due to dynamic web content.
2. **LLM Consensus (`prompt_comparative`)**: 
   The AI evaluation uses `gl.eq_principle.prompt_comparative`. Validators must agree on the exact core verdict (`ATTESTED`, `NOT_ATTESTED`, or `UNVERIFIABLE`), while allowing the natural language reasoning and quoted evidence to vary slightly between nodes.
3. **Evidence Truncation & State Preservation**: 
   Web pages are cleaned and truncated (max 10,000 characters) before being passed to the LLM. The raw fetch envelope and string lengths are preserved on-chain so reviewers can audit the exact data the LLM used to make its decision.

## 🛠 Contract Interface

### `create_fact_check(task_id: str, target_link: str, statement: str)`
Initializes a new fact-checking task.
- Validates the URL format (must be HTTP/HTTPS).
- Enforces minimum length for the factual claim.
- Sets initial state to `pending`.

### `execute_fact_check(task_id: str)`
Triggers the intelligent verification process.
- Fetches the URL content.
- Pre-filters hard 404s or empty pages to save LLM execution costs (outputs `UNVERIFIABLE`).
- Prompts the GenLayer LLM to evaluate the text against the statement.
- Updates the task state with the final verdict and rationale.

### `get_task_details(task_id: str) -> dict`
View method to retrieve the complete audit trail of a task, including the initiator, link, statement, final status, AI reasoning, and the truncated page excerpt.

## 🚀 Workflow Example

1. **Submit**: User calls `create_fact_check("task_1", "https://example.com/news", "The company launched product X on Monday.")`
2. **Execute**: User (or an automated keeper) calls `execute_fact_check("task_1")`.
3. **Consensus**: GenLayer nodes fetch the URL, run the LLM prompt, and reach consensus on whether the text confirms the claim.
4. **Result**: The task status becomes `ATTESTED` (supported), `NOT_ATTESTED` (unsupported/contradicted), or `UNVERIFIABLE` (bad link/missing context).

## 🛡 Security & Edge Cases Handled

- **Malformed URLs & Dead Links**: Safely caught by regex and HTTP status code checks before LLM invocation.
- **Context Window Limits**: Web text is whitespace-compressed and strictly truncated with an explicit `[+X chars omitted]` flag to prevent silent context loss.
- **LLM Hallucinations**: Prompt strictness forces the LLM to output a precise label on the first line and quote directly from the provided text, minimizing hallucination risks.

## 📄 License

This project is licensed under the MIT License.
