"""Model client wrappers for Run 2 baselines.

Each provider lives in its own module so the model-baseline runner
stays transport-agnostic. The OpenAI wrapper (`openai_client.py`)
exposes `load_openai_client()` and `call_openai_contract_model()`.
"""
