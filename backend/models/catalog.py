"""
Model catalog API models: providers, models and personas.

The API contract is described in docs/model_catalog_api.md. API keys are
write-only: requests may carry `apiKey`, responses only say whether a key is
set and show a masked version.
"""
from datetime import datetime
from typing import Any, List, Literal, Optional
from pydantic import BaseModel, Field

ProviderKind = Literal["openai_compatible", "anthropic"]
PrivacyTier = Literal["local", "eu", "trusted", "untrusted"]
ReasoningMode = Literal["none", "optional", "always"]
Currency = Literal["USD", "EUR"]


# Providers

class ProviderBase(BaseModel):
    """One API account."""
    name: str
    kind: ProviderKind
    baseUrl: Optional[str] = None  # None = the SDK default
    apiKeyEnv: Optional[str] = None  # Name of an environment variable holding the key
    privacyTier: PrivacyTier
    currency: Currency = "USD"
    defaultHeaders: Optional[dict[str, str]] = None
    notes: Optional[str] = None
    enabled: bool = True


class ProviderCreate(ProviderBase):
    apiKey: Optional[str] = None  # Stored encrypted; never returned


class ProviderUpdate(BaseModel):
    """Partial update; fields left out stay unchanged."""
    name: Optional[str] = None
    kind: Optional[ProviderKind] = None
    baseUrl: Optional[str] = None
    apiKeyEnv: Optional[str] = None
    privacyTier: Optional[PrivacyTier] = None
    currency: Optional[Currency] = None
    defaultHeaders: Optional[dict[str, str]] = None
    notes: Optional[str] = None
    enabled: Optional[bool] = None
    apiKey: Optional[str] = None  # Left out or null = keep the stored key, "" = remove it


class ProviderOut(ProviderBase):
    id: int
    apiKeySource: Literal["stored", "env", "none"]  # Where the key comes from at runtime
    apiKeyMasked: Optional[str] = None  # "sk-…1234"; only for stored keys
    modelCount: int = 0
    createdAt: Optional[datetime] = None
    updatedAt: Optional[datetime] = None


class FetchedModel(BaseModel):
    """One entry of a provider's GET /models list."""
    id: str
    ownedBy: Optional[str] = None
    contextWindow: Optional[int] = None
    alreadyAdded: bool = False  # A catalog model of this provider already uses this id


class FetchModelsResponse(BaseModel):
    models: List[FetchedModel]


class ModelTestResult(BaseModel):
    """Result of POST /api/admin/models/{id}/test: one short request to the model."""
    ok: bool
    latencyMs: int
    reply: Optional[str] = None
    error: Optional[str] = None


# Models

class ModelBase(BaseModel):
    """One model offered in the picker."""
    providerId: int
    displayName: str
    modelId: str  # API model name
    description: Optional[str] = None
    supportsTools: bool = True
    supportsVision: bool = False
    reasoning: ReasoningMode = "none"
    reasoningPassback: bool = False
    contextWindow: Optional[int] = None
    maxOutputTokens: Optional[int] = None
    temperature: Optional[float] = None
    topP: Optional[float] = None
    reasoningEffort: Optional[str] = None
    extraBody: Optional[dict[str, Any]] = None
    privacyTier: Optional[PrivacyTier] = None  # None = inherit from the provider
    inputPricePerMtok: Optional[float] = None  # In the provider's currency
    outputPricePerMtok: Optional[float] = None
    isAuxiliary: bool = False  # Used for titles and speech preprocessing
    availableToGuests: bool = False
    enabled: bool = True
    sortOrder: int = 0
    notes: Optional[str] = None


class ModelCreate(ModelBase):
    pass


class ModelUpdate(BaseModel):
    """Partial update; fields left out stay unchanged. Send null to clear an optional field."""
    providerId: Optional[int] = None
    displayName: Optional[str] = None
    modelId: Optional[str] = None
    description: Optional[str] = None
    supportsTools: Optional[bool] = None
    supportsVision: Optional[bool] = None
    reasoning: Optional[ReasoningMode] = None
    reasoningPassback: Optional[bool] = None
    contextWindow: Optional[int] = None
    maxOutputTokens: Optional[int] = None
    temperature: Optional[float] = None
    topP: Optional[float] = None
    reasoningEffort: Optional[str] = None
    extraBody: Optional[dict[str, Any]] = None
    privacyTier: Optional[PrivacyTier] = None
    inputPricePerMtok: Optional[float] = None
    outputPricePerMtok: Optional[float] = None
    isAuxiliary: Optional[bool] = None
    availableToGuests: Optional[bool] = None
    enabled: Optional[bool] = None
    sortOrder: Optional[int] = None
    notes: Optional[str] = None


class ModelOut(ModelBase):
    id: int
    providerName: str
    effectivePrivacyTier: PrivacyTier  # The model's tier, else the provider's
    currency: Currency


class PublicModel(BaseModel):
    """A model as the picker sees it (GET /api/models)."""
    id: int
    displayName: str
    description: Optional[str] = None
    providerName: str
    privacyTier: PrivacyTier  # Effective tier
    supportsTools: bool
    supportsVision: bool
    reasoning: ReasoningMode
    contextWindow: Optional[int] = None
    inputPricePerMtok: Optional[float] = None
    outputPricePerMtok: Optional[float] = None
    currency: Currency


# Personas

class PersonaVariable(BaseModel):
    """A {{name}} placeholder in a persona's system prompt."""
    name: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    label: str
    default: Optional[str] = None


class PersonaBase(BaseModel):
    name: str
    description: Optional[str] = None
    systemPrompt: str  # May use {{variables}} and the built-ins {{date}}, {{user_name}}, {{language}}
    variables: List[PersonaVariable] = []
    defaultModelId: Optional[int] = None
    availableToGuests: bool = False
    enabled: bool = True
    sortOrder: int = 0


class PersonaCreate(PersonaBase):
    pass


class PersonaUpdate(BaseModel):
    """Partial update; fields left out stay unchanged."""
    name: Optional[str] = None
    description: Optional[str] = None
    systemPrompt: Optional[str] = None
    variables: Optional[List[PersonaVariable]] = None
    defaultModelId: Optional[int] = None
    availableToGuests: Optional[bool] = None
    enabled: Optional[bool] = None
    sortOrder: Optional[int] = None


class PersonaOut(PersonaBase):
    id: int


class PublicPersona(BaseModel):
    """A persona as the picker sees it (GET /api/personas)."""
    id: int
    name: str
    description: Optional[str] = None
    systemPrompt: str
    variables: List[PersonaVariable] = []
    defaultModelId: Optional[int] = None


# Import and export

class ImportCounts(BaseModel):
    created: int = 0
    updated: int = 0


class ImportResult(BaseModel):
    """Result of POST /api/admin/catalog/import. The file format is in docs/model_catalog_api.md."""
    providers: ImportCounts
    models: ImportCounts
    personas: ImportCounts
    errors: List[str] = []
