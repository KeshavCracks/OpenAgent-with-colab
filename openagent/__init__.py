"""OpenAgent Harness.

A low-RAM local agent harness: UI, orchestration, tools, skills, memory and
developer observability run on the local machine; heavy LLM inference is
delegated to short-lived remote GPU backends (Google Colab, then Kaggle),
reached through an OpenAI-compatible llama.cpp server. No model weights are
bundled in this repository and no credentials are ever read from or written
to version control -- see openagent.config for the secrets policy.
"""

__version__ = "0.1.0"
