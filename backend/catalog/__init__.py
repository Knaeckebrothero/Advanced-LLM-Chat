"""
Model catalog: LLM providers (API accounts), models and personas (the "agents" of the UI).

- resolver: which model answers a conversation, as a ModelConfig for the runtime,
  and the persona's prompt and tool groups
- service: create, update and list catalog entries (shared by the API and the catalog file)
- catalog_file: JSON import, export and seeding from MODEL_CATALOG_FILE
- fetch: a provider's GET /models list

Providers come only from the catalog file and their API keys only from
environment variables. The contract is in docs/model_catalog_api.md.
"""
