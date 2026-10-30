"""
Model catalog: LLM providers (API accounts), models and personas.

- crypto: Fernet encryption of API keys entered in the UI
- resolver: which model answers a conversation, as a ModelConfig for the runtime
- service: create, update and list catalog entries (shared by the API and the catalog file)
- catalog_file: JSON import, export and seeding from MODEL_CATALOG_FILE
- fetch: a provider's GET /models list

The contract is in docs/model_catalog_api.md.
"""
