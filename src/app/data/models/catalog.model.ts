/**
 * Model Catalog Data Models
 *
 * Mirrors backend/models/catalog.py and MessageUsage in backend/models/message.py.
 * The API contract is described in docs/model_catalog_api.md.
 */

export type ProviderKind = 'openai_compatible' | 'anthropic';
export type PrivacyTier = 'local' | 'eu' | 'trusted' | 'untrusted';
export type ReasoningMode = 'none' | 'optional' | 'always';
export type Currency = 'USD' | 'EUR';
export type ApiKeySource = 'stored' | 'env' | 'none';

export const PROVIDER_KINDS: ProviderKind[] = ['openai_compatible', 'anthropic'];
export const PRIVACY_TIERS: PrivacyTier[] = ['local', 'eu', 'trusted', 'untrusted'];
export const REASONING_MODES: ReasoningMode[] = ['none', 'optional', 'always'];
export const CURRENCIES: Currency[] = ['USD', 'EUR'];

/** Persona placeholders the backend fills in itself; they need no input. */
export const BUILT_IN_PERSONA_VARIABLES = ['date', 'user_name', 'language'];

// ============================================================================
// Usage
// ============================================================================

/** Token usage and cost of one assistant message, summed over all model calls. */
export interface IMessageUsage {
  inputTokens: number;
  outputTokens: number;  // Includes reasoning tokens
  reasoningTokens?: number | null;
  cachedInputTokens?: number | null;
  cost?: number | null;  // null when the model has no prices
  currency?: string | null;
}

// ============================================================================
// Providers
// ============================================================================

export interface IProviderBase {
  name: string;
  kind: ProviderKind;
  baseUrl?: string | null;
  apiKeyEnv?: string | null;
  privacyTier: PrivacyTier;
  currency: Currency;
  defaultHeaders?: Record<string, string> | null;
  notes?: string | null;
  enabled: boolean;
}

export interface IProviderCreate extends IProviderBase {
  apiKey?: string | null;
}

/** Partial update; fields left out stay unchanged. apiKey: left out = keep, "" = remove. */
export type IProviderUpdate = Partial<IProviderBase> & { apiKey?: string | null };

export interface IProviderOut extends IProviderBase {
  id: number;
  apiKeySource: ApiKeySource;
  apiKeyMasked?: string | null;
  modelCount: number;
  createdAt?: string | null;
  updatedAt?: string | null;
}

export interface IFetchedModel {
  id: string;
  ownedBy?: string | null;
  contextWindow?: number | null;
  alreadyAdded: boolean;
}

export interface IFetchModelsResponse {
  models: IFetchedModel[];
}

// ============================================================================
// Models
// ============================================================================

export interface IModelBase {
  providerId: number;
  displayName: string;
  modelId: string;
  description?: string | null;
  supportsTools: boolean;
  supportsVision: boolean;
  reasoning: ReasoningMode;
  reasoningPassback: boolean;
  contextWindow?: number | null;
  maxOutputTokens?: number | null;
  temperature?: number | null;
  topP?: number | null;
  reasoningEffort?: string | null;
  extraBody?: Record<string, unknown> | null;
  privacyTier?: PrivacyTier | null;  // null = inherit from the provider
  inputPricePerMtok?: number | null;
  outputPricePerMtok?: number | null;
  isAuxiliary: boolean;
  availableToGuests: boolean;
  enabled: boolean;
  sortOrder: number;
  notes?: string | null;
}

export type IModelCreate = IModelBase;

/** Partial update; fields left out stay unchanged, null clears an optional field. */
export type IModelUpdate = Partial<IModelBase>;

export interface IModelOut extends IModelBase {
  id: number;
  providerName: string;
  effectivePrivacyTier: PrivacyTier;
  currency: Currency;
}

/** A model as the picker sees it (GET /api/models). */
export interface IPublicModel {
  id: number;
  displayName: string;
  description?: string | null;
  providerName: string;
  privacyTier: PrivacyTier;  // Effective tier
  supportsTools: boolean;
  supportsVision: boolean;
  reasoning: ReasoningMode;
  contextWindow?: number | null;
  inputPricePerMtok?: number | null;
  outputPricePerMtok?: number | null;
  currency: Currency;
}

export interface IModelTestResult {
  ok: boolean;
  latencyMs: number;
  reply?: string | null;
  error?: string | null;
}

// ============================================================================
// Personas
// ============================================================================

export interface IPersonaVariable {
  name: string;  // ^[A-Za-z_][A-Za-z0-9_]*$
  label: string;
  default?: string | null;
}

export interface IPersonaBase {
  name: string;
  description?: string | null;
  systemPrompt: string;
  variables: IPersonaVariable[];
  defaultModelId?: number | null;
  availableToGuests: boolean;
  enabled: boolean;
  sortOrder: number;
}

export type IPersonaCreate = IPersonaBase;
export type IPersonaUpdate = Partial<IPersonaBase>;

export interface IPersonaOut extends IPersonaBase {
  id: number;
}

/** A persona as the picker sees it (GET /api/personas). */
export interface IPublicPersona {
  id: number;
  name: string;
  description?: string | null;
  systemPrompt: string;
  variables: IPersonaVariable[];
  defaultModelId?: number | null;
}

// ============================================================================
// Import and export
// ============================================================================

export interface IImportCounts {
  created: number;
  updated: number;
}

export interface IImportResult {
  providers: IImportCounts;
  models: IImportCounts;
  personas: IImportCounts;
  errors: string[];
}

/** The catalog file (snake_case keys, see docs/model_catalog_api.md). Passed through as-is. */
export interface ICatalogFile {
  version: number;
  providers?: Record<string, unknown>[];
  models?: Record<string, unknown>[];
  personas?: Record<string, unknown>[];
  [key: string]: unknown;
}

// ============================================================================
// Conversation selection
// ============================================================================

/** Values for a persona's variables, stored with the conversation. */
export type PersonaValues = Record<string, string>;

/** The model and persona picked for a conversation. null = the user's default model / no persona. */
export interface IConversationSelection {
  modelId: number | null;
  personaId: number | null;
  personaValues: PersonaValues | null;
}
