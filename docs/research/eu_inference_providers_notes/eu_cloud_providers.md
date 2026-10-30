# European cloud providers: serverless pay-per-token LLM inference for open-weight models (as of 2026-10-30)

Method note: I checked official pages on 2026-10-30. Scaleway's docs site returns HTTP 403 to automated fetchers, so I read Scaleway's docs from its public GitHub source repo (`scaleway/docs-content`, which the docs site is built from). The latest commits on the model page are dated 2026-10-15 ("add glm 5.3 and deepseek v4.1 flash") and 2026-10-19 ("update deprecated models"). The Scaleway pricing page loaded once browser headers were sent. I listed OVHcloud's live model list from its public `/v1/models` endpoint. Prices exclude VAT unless stated otherwise.

## Q1. Which providers serve the large open models people want (Kimi, DeepSeek, GLM, Qwen3+, gpt-oss), and which serve only small or older ones? (Includes catalog, prices, and Kimi naming)

### Takeaway
Among the big EU clouds, only **Scaleway** serves frontier-class Chinese open models serverless: GLM-5.3, DeepSeek-V4.1-Flash and DeepSeek-V4-Flash, plus Qwen3.5-397B and gpt-oss-120b. **Telekom/T-Systems** serves GLM-5.2 and GLM-5.3-Flash, but requires a €1,000/month minimum. **No big EU cloud serves Kimi.** Swiss **Infomaniak** serves Kimi-K2.6. A small German startup, **Lyceum**, claims to serve Kimi K3, DeepSeek V4 Pro and GLM-5.3 from EU data centres (vendor-reported, not independently verified). OVHcloud, IONOS and STACKIT top out at Qwen3.5-397B / Qwen3-VL-235B, gpt-oss-120b, Qwen3.8-27B and Llama 3.3 70B. "Kimi K3.1" exists only as Moonshot's own API model `kimi-k3.1-pro`: it has no open weights on Hugging Face, and no EU provider serves it.

### Cited Findings

**Kimi naming (what is current)**
- Moonshot's official model list (read 2026-10-30) names `kimi-k3.1-pro`: "The first model of the new K3.1 series and Kimi's most capable flagship to date: a 3T-class model with native visual understanding and a 1M-token context window". It also lists `kimi-k3.1-pro-highspeed`, plus `kimi-k3` ("previous-generation flagship and the world's first open-source 3T-class model (2.8 trillion parameters)… 1M-token context") and `kimi-k2.7-code` / `kimi-k2.7-code-highspeed` (256k context) — [Moonshot/Kimi platform docs – models](https://platform.kimi.ai/docs/models)
- The same page says that from 2026-10-31, K2-series models are no longer available to new users of Moonshot's own API, and that all K2 models will be retired by end of December 2026. kimi-k2.5 was discontinued 2026-08-31. — [Moonshot/Kimi platform docs](https://platform.kimi.ai/docs/models)
- Hugging Face org `moonshotai` (queried via API on 2026-10-30) lists open-weight repos `Kimi-K3`, `Kimi-K2.7-Code`, `Kimi-K2.6`, `Kimi-K2.5` and `Kimi-K2-Thinking`. **There is no K3.1 repo.** — [Hugging Face moonshotai](https://huggingface.co/moonshotai)
- Third-party sites report "Kimi K3.1 Pro" released 2026-10-23, priced $2/$10 per M tokens on Moonshot's API. Other commentary says K3.1 was only teased. Treat the release date and price as unverified. — [Vals.ai](https://www.vals.ai/models/kimi_kimi-k3.1-pro); [RuntimeWire](https://runtimewire.com/models/moonshotai/kimi-k3.1-pro); [Magica](https://magica.com/news/moonshot-teases-kimi-k3-1-inside-kimi-code)
- Kimi K3 was launched 2026-07-16 as a ~2.8T-parameter MoE with 1M context (secondary sources) — [llm-stats](https://llm-stats.com/models/kimi-k3); [ProPakistani](https://propakistani.pk/2026/07/17/kimi-k3-launched-as-worlds-best-open-ai-model/)
- Other current open-weight versions on Hugging Face (2026-10-30):
  - Z.ai: GLM-5.3 and GLM-5.3-Flash (created 2026-08-25), GLM-5.2 (2026-06-16)
  - DeepSeek: DeepSeek-V4.1-Flash (2026-09-10), DeepSeek-V4.1-Flash-1017 (2026-10-17), DeepSeek-V4-Pro-0813, DeepSeek-V4-Flash-0731
  - Sources: [HF zai-org](https://huggingface.co/zai-org); [HF deepseek-ai](https://huggingface.co/deepseek-ai)

**Scaleway Generative APIs – Serverless (France)**
- Serverless text and code models per the supported-models doc (Serverless = "Yes"):
  - Z.ai: `glm-5.3` (256k ctx, 16k max output); `glm-5.2` (deprecated 2026-10-16, EOL 2026-11-16, then routed to glm-5.3)
  - DeepSeek: `deepseek-v4.1-flash` (text and vision, 256k ctx, 32k out); `deepseek-v4-flash-0731` (256k, 32k out)
  - Qwen: `qwen3.8-27b` (vision, 256k); `qwen3.6-35b-a3b` (vision, 256k); `qwen3.5-397b-a17b` (vision, 250k ctx, 16k out); `qwen3-235b-a22b-instruct-2507` (250k)
  - Others: `gemma-4-26b-a4b-it`; `gpt-oss-120b` (128k); `llama-3.3-70b-instruct` (100k serverless); `mistral-medium-3.5-128b` (vision, 180k); `mistral-small-3.2-24b-instruct-2506` (vision, 128k)
  - Not serverless (dedicated only): `mistral-large-3-675b-instruct-2512`, `minimax-m2.5`, `gpt-oss-20b`, `qwen3.5-122b-a10b`
  - **No Kimi model of any kind.**
  - Sources: [Scaleway supported models (GitHub source of docs page)](https://github.com/scaleway/docs-content/blob/main/pages/generative-apis/reference-content/supported-models.mdx); [docs page](https://www.scaleway.com/en/docs/generative-apis/reference-content/supported-models/)
- Scaleway serverless prices, € per M tokens input / output, Paris region, read 2026-10-30 — [Scaleway pricing](https://www.scaleway.com/en/pricing/model-as-a-service/):

  | Model | Input | Output | Cached input |
  |---|---|---|---|
  | glm-5.3 | €1.80 | €5.50 | – |
  | glm-5.2 | €1.80 | €5.50 | – |
  | deepseek-v4.1-flash-1017 | €0.60 | €1.80 | €0.12 |
  | deepseek-v4-flash-0731 | €0.40 | €0.80 | €0.08 |
  | qwen3.5-397b-a17b | €0.60 | €3.60 | – |
  | qwen3.8-27b | €0.60 | €3.30 | €0.12 |
  | qwen3.6-35b-a3b | €0.25 | €1.50 | – |
  | qwen3-235b-a22b-instruct-2507 | €0.75 | €2.25 | – |
  | gpt-oss-120b | €0.15 | €0.60 | – |
  | llama-3.3-70b-instruct | €0.90 | €0.90 | – |
  | mistral-medium-3.5-128b | €1.50 | €7.50 | – |
  | mistral-small-3.2-24b-instruct-2506 | €0.15 | €0.35 | – |
  | gemma-4-26b-a4b-it | €0.25 | €0.50 | – |

  - Free tier: first 1,000,000 tokens (plus 60 min of audio).
  - Batches API: −50%.
- The pricing page names the DeepSeek model `deepseek-v4.1-flash-1017`, while the docs table names it `deepseek-v4.1-flash`. Hugging Face has both `DeepSeek-V4.1-Flash` and `DeepSeek-V4.1-Flash-1017`. Check the exact model string with `GET /v1/models`. — [Scaleway pricing](https://www.scaleway.com/en/pricing/model-as-a-service/); [Scaleway supported models source](https://github.com/scaleway/docs-content/blob/main/pages/generative-apis/reference-content/supported-models.mdx)
- The minimum billing unit is 1,000 tokens. The free tier is applied to the most expensive tokens first. — [Scaleway Generative APIs FAQ (source)](https://github.com/scaleway/docs-content/blob/main/pages/generative-apis/faq.mdx)

**OVHcloud AI Endpoints (France)**
- Live `/v1/models` on 2026-10-30 returned 22 models. The only text LLMs are:
  - Qwen: `Qwen3.5-397B-A17B`, `Qwen3.8-27B`, `Qwen3.6-27B`, `Qwen3.5-9B`, `Qwen2.5-VL-72B-Instruct`
  - OpenAI: `gpt-oss-120b`, `gpt-oss-20b`
  - Mistral: `Mistral-Small-3.2-24B-Instruct-2506`, `Mistral-Nemo-Instruct-2407`
  - Meta: `Meta-Llama-3_3-70B-Instruct`
  - **No Kimi, DeepSeek or GLM.**
  - Sources: [OVH AI Endpoints /v1/models](https://oai.endpoints.kepler.ai.cloud.ovh.net/v1/models); [OVH catalog](https://www.ovhcloud.com/en/public-cloud/ai-endpoints/catalog/)
- OVH catalog prices, € per M tokens input / output — [OVH catalog](https://www.ovhcloud.com/en/public-cloud/ai-endpoints/catalog/):
  - Qwen3.5-397B-A17B €0.6 / €3.6
  - Qwen3.8-27B €0.4 / €2.7
  - Qwen3.6-27B €0.4 / €2.7
  - Qwen3.5-9B €0.1 / €0.15
  - gpt-oss-120b €0.08 / €0.4
  - gpt-oss-20b €0.04 / €0.15
  - Meta-Llama-3_3-70B-Instruct €0.67 / €0.67
  - Qwen2.5-VL-72B €0.91 / €0.91
  - Mistral-Small-3.2-24B €0.09 / €0.28 (EOL 2026-11-04)
  - Mistral-Nemo €0.13 / €0.13 (EOL 2026-11-04)
  - The Qwen Guard models and SDXL are free.

**IONOS AI Model Hub (Germany)**
- LLMs listed: Qwen3.5 9B, Mistral Small 24B, Qwen3.8 27B, Llama 3.3 70B, GPT-OSS 120B and Qwen3.5 397B A17B, plus a coding model, Qwen3 Coder Next 80B. **No Kimi, DeepSeek or GLM.** — [IONOS LLMs](https://docs.ionos.com/cloud/ai/ai-model-hub/models/llms); [IONOS models index](https://docs.ionos.com/cloud/ai/ai-model-hub/models)
- Model identifiers and serving details from the model cards:
  - `Qwen/Qwen3.5-397B-A17B`: FP8, 262k
  - `openai/gpt-oss-120b`: MXFP4, 128k
  - `meta-llama/Llama-3.3-70B-Instruct`: AWQ INT4, 128k
  - `Qwen/Qwen3.8-27B`: INT4, 262k
  - `mistralai/Mistral-Small-24B-Instruct`: links to Mistral-Small-3.2-24B-Instruct-2506, fp8, 128k
  - Sources: [Qwen3.5 397B card](https://docs.ionos.com/cloud/ai/ai-model-hub/models/llms/qwen3-5-397b); [GPT-OSS 120B card](https://docs.ionos.com/cloud/ai/ai-model-hub/models/llms/openai-gpt-oss-120b); [Llama 3.3 card](https://docs.ionos.com/cloud/ai/ai-model-hub/models/llms/meta-llama-3-3-70b); [Qwen3.8 27B card](https://docs.ionos.com/cloud/ai/ai-model-hub/models/llms/qwen3-8-27b); [Mistral Small card](https://docs.ionos.com/cloud/ai/ai-model-hub/models/llms/mistral-small-24b)
- Retired or retiring models include Llama 3.1 405B (2026-09-15), Llama 3.1 8B (2026-10-15) and Mistral Nemo (2026-10-22) — [IONOS models index](https://docs.ionos.com/cloud/ai/ai-model-hub/models)
- IONOS EUR price list (v2026-10-29), € per M tokens input / output — [IONOS price list (EUR)](https://docs.ionos.com/cloud/support/general-information/price-list/ionos-cloud-eur-en):
  - Qwen3.5-9B 0.10 / 0.15
  - Mistral Small 24B 0.10 / 0.30
  - gpt-oss-120b 0.15 / 0.65
  - Llama 3.3 70B 0.65 / 0.65
  - Qwen3.8-27B 0.40 / 2.70
  - Qwen3.5-397B-A17B 0.60 / 3.60
  - Qwen3-Coder-Next (80B) 0.15 / 0.80

**STACKIT AI Model Serving (Germany, Schwarz Group)**
- Shared models (page last updated 2026-10-15) — [STACKIT available shared models](https://docs.stackit.cloud/products/data-and-ai/ai-model-serving/basics/available-shared-models/):
  - `Qwen/Qwen3-VL-235B-A22B-Instruct-FP8` (premium, 200k ctx, vision)
  - `Qwen/Qwen3.8-27B` (262k, vision, reasoning)
  - `Qwen/Qwen3.6-27B` (deprecated)
  - `cortecs/Llama-3.3-70B-Instruct-FP8-Dynamic` (128k, 4,096 max generation)
  - gpt-oss-120b (131k)
  - `google/gemma-4-31B-it` (256k)
  - `openai/gpt-oss-20b`
  - Embeddings
  - **No Kimi, DeepSeek or GLM.**
- Release notes: Qwen3.8-27B added 2026-09-08 (Qwen3.6-27B to be migrated by 2026-12-08); Gemma-4-31B added 2026-07-14; gpt-oss-20b added 2026-03-04; Qwen3-VL-235B added 2026-01-19; GPT-OSS-120B added 2025-12-10 — [STACKIT release notes](https://docs.stackit.cloud/products/data-and-ai/ai-model-serving/release-notes/)
- Prices, € per M tokens input / output (EU01) — [STACKIT AI Model Serving product page](https://stackit.com/en/products/data-ai/stackit-ai-model-serving):
  - Gemma 4 31B 0.45 / 0.65
  - gpt-oss-120b 0.45 / 0.65
  - gpt-oss-20b 0.15 / 0.25
  - Llama 3.3 70B FP8 0.45 / 0.65
  - Qwen3-VL-235B-A22B FP8 1.50 / 1.75
  - Qwen3.6 27B 0.45 / 0.65
  - Qwen3.8 27B 0.45 / 0.65

**Open Telekom Cloud / T-Systems "AI Foundation Services" (Germany)**
- The LLM page lists 39 models. Those hosted on T-Cloud Public in Germany are below, € per M tokens input / output, with cached input in brackets — [T-Systems AIFS LLM list](https://docs.llmhub.t-systems.net/models/llms/):
  - GLM 5.2: 1M ctx, €1.50 / €3.50 (€0.225)
  - GLM 5.3 Flash: 1M ctx, €0.20 / €0.60 (€0.03)
  - GPT-OSS 120B: 128k, €0.20 / €0.65
  - Gemma 4: €0.60 / €1.20
  - Mistral Small 4: €0.60 / €1.20
  - NVIDIA Nemotron 3 Super 120B FP8: €0.60 / €1.20
  - Qwen 3.6 35B FP8: €0.60 / €1.20
  - Qwen 3.8 27B FP8: €0.50 / €2.50
  - The rest are closed models (GPT-5.x/6, Claude, Gemini, Mistral Medium 3) that are forwarded to Azure or GCP.
  - **No Kimi and no DeepSeek on the current list**, although the FAQ still names DeepSeek generically.
- Prices valid from 2026-08-01 — [T-Systems Essential plan](https://docs.llmhub.t-systems.net/plans/essential/)

**Infomaniak AI Tools (Switzerland – not EU)**
- LLM prices, CHF per M tokens input / output, excl. VAT — [Infomaniak AI prices](https://www.infomaniak.com/en/hosting/ai-tools/prices):
  - `moonshotai/Kimi-K2.6` 0.60 / 3.00
  - `Qwen/Qwen3.5-397B-A17B-FP8` 0.80 / 3.60
  - `Qwen/Qwen3.8-27B-FP8` 0.40 / 3.00
  - `mistralai/Mistral-Small-4-119B-2603` 0.20 / 0.75
  - `mistralai/Ministral-3-14B-Instruct-2512` 0.30 / 0.40
  - `google/gemma-4-31B-it` 0.20 / 0.40
  - `swiss-ai/Apertus-v1.5-70B` 0.70 / 2.50
  - **No DeepSeek, GLM or gpt-oss.**

**Other EU offerings found**
- **Regolo.ai (Seeweb S.r.l., Italy)**, € per M tokens input / output — [Regolo pricing](https://regolo.ai/pricing/):
  - glm5.2 2.00 / 5.20
  - gpt-oss-120b 1.00 / 4.20
  - gpt-oss-20b 0.10 / 0.42
  - qwen3.5-122b 1.00 / 4.20
  - qwen3.8-27b 0.50 / 2.10
  - mistral-small-4-119b 0.50 / 2.10
  - gemma4-31b 0.40 / 2.10
  - apertus-70b 0.40 / 2.10
  - qwen3.5-9b 0.07 / 0.35
  - No Kimi or DeepSeek chat models (deepseek-ocr-2 only).
  - The page says rates change on 2026-11-01.
- **Lyceum Technology (Lyceum Technology Germany GmbH)** serverless models, $ per M tokens input / output — [Lyceum models](https://lyceum.technology/models/):
  - `moonshotai/kimi-k3` $3.00 / $15.00 (1M ctx)
  - `moonshotai/kimi-k2.7-code` $1.25 / $4.50
  - `deepseek/deepseek-v4-pro-0813` $2.00 / $4.00
  - `deepseek/deepseek-v4.1-flash` $0.50 / $1.50
  - `deepseek/deepseek-v4-flash-0731` $0.25 / $0.30
  - `z-ai/glm-5.3` $1.40 / $4.40
  - `z-ai/glm-5.3-flash` $0.20 / $0.50
  - `z-ai/glm-5.2` $1.50 / $4.50
  - `qwen/qwen3.8-2.4t-a95b` $2.50 / $6.00
  - `qwen/qwen3.8-27b` $0.40 / $2.40
  - Its magazine says the serverless models "run in Paris and Finland" (regions read 2026-10-23) — [Lyceum article](https://lyceum.technology/magazine/which-open-weight-models-are-actually-hosted-in/)
- Other vendors claim EU hosting of Kimi K3, DeepSeek V4.1 Flash or GLM 5.3, but I did not verify them: LLMBase (Germany), Helmcode, and the gateway Opper. LLMBase itself says "model processing may vary". — [LLMBase](https://llmbase.ai/); [Helmcode](https://helmcode.com/security/open-models-eu); [Opper provider directory](https://opper.ai/providers)

### Inferences
- If you need Kimi from a European jurisdiction, the verified options are Infomaniak (K2.6, Swiss) and Lyceum (K3, a German startup whose claims are self-reported). Moonshot is phasing K2 out of its own API by Dec 2026. That doesn't stop third parties hosting K2.6 open weights, but K2.6 is now a generation behind K3.
- For DeepSeek V4.x and GLM-5.3 at an established EU hyperscaler with self-serve pay-as-you-go, Scaleway is the only verified option.
- OVH, IONOS and STACKIT are effectively "Qwen + gpt-oss + Llama 3.3" providers. Their largest models are Qwen3.5-397B-A17B (OVH, IONOS) and Qwen3-VL-235B (STACKIT). These are capable, but they are not the Kimi/DeepSeek/GLM tier.
- Same model, different prices:
  - gpt-oss-120b: OVH €0.08/€0.40, Scaleway €0.15/€0.60, IONOS €0.15/€0.65, Telekom €0.20/€0.65, STACKIT €0.45/€0.65, Regolo €1.00/€4.20.
  - Qwen3.5-397B: €0.60/€3.60 at OVH, IONOS and Scaleway alike.

### Gaps
- Nebius Token Factory (Nebius Group N.V., Amsterdam) likely serves Kimi, DeepSeek and GLM from EU sites, but its pricing page rendered empty to my fetcher. I could not verify models, regions or terms.
- Not researched for lack of budget: Exoscale, Hetzner, UpCloud, Gcore, Berget AI, Cortecs, Mistral La Plateforme (first-party Mistral models only). I found no evidence either way on whether Hetzner, Exoscale or UpCloud offer serverless token APIs.
- I could not confirm from Moonshot directly whether Kimi K3.1 Pro weights will be released. Only K3 has an open-weight repo.
- Lyceum's underlying infrastructure ("Paris and Finland") and its operator are not disclosed. It may be reselling another cloud's capacity.

## Q2. Does each API support OpenAI-compatible /v1/chat/completions with streaming and tool/function calling (LangChain ChatOpenAI + bind_tools)?

### Takeaway
All six main providers expose an OpenAI-compatible `/v1/chat/completions` and document tool calling for most current models. Three provider-specific traps:
- **Scaleway's gpt-oss-120b does not support tool calling via Chat Completions**; Scaleway says to use the Responses API.
- **STACKIT warns that sending `"tools": []` makes some Llama models hallucinate tool calls.**
- **OVH's Qwen2.5-VL-72B has no function calling.**

Streaming is explicitly documented for Scaleway, IONOS and T-Systems (including streamed tool calls at T-Systems). For OVH, STACKIT and Infomaniak it is implied by OpenAI compatibility but not shown explicitly.

### Cited Findings
- **Scaleway**
  - Base URL `https://api.scaleway.ai/v1` — [Scaleway quickstart source](https://github.com/scaleway/docs-content/blob/main/pages/generative-apis/quickstart.mdx)
  - Supported Chat Completions parameters include `stream`, `tools`, `tool_choice` and `response_format`. Unsupported: `frequency_penalty`, `n`, `top_logprobs`, `logit_bias`, `user`. — [Scaleway OpenAI compatibility](https://www.scaleway.com/en/docs/generative-apis/reference-content/openai-compatibility/) ([source](https://github.com/scaleway/docs-content/blob/main/pages/generative-apis/reference-content/openai-compatibility.mdx), validated 2026-04-24)
  - "Supports function calling: Yes" and "parallel tool-calling: Yes" for glm-5.3, glm-5.2, deepseek-v4.1-flash, deepseek-v4-flash-0731, qwen3.5-397b-a17b, qwen3.8-27b, qwen3.6-35b-a3b, qwen3-235b-a22b-instruct-2507, mistral-medium-3.5-128b, mistral-small-3.2 and llama-3.3-70b. Gemma-3-27b has only "Partial" support. — [Scaleway supported models source](https://github.com/scaleway/docs-content/blob/main/pages/generative-apis/reference-content/supported-models.mdx)
  - GLM-5.3 reasoning efforts: `none`/`low`/`high`/`max`. DeepSeek-V4.1-Flash: `none`/`low`/`high`/`max`. — same source
  - gpt-oss-120b: "Currently, this model should be used through the Responses API, because the Chat Completions API does not yet support tool-calling for this model." — same source
  - Usage stats are returned on streaming responses, at least for Dedicated Deployments (incremented per chunk) — [Scaleway OpenAI compatibility](https://www.scaleway.com/en/docs/generative-apis/reference-content/openai-compatibility/)
- **OVHcloud**
  - AI Endpoints is "designed to be compatible with the OpenAI API". Features listed include "Function Calling (Tools)", JSON mode and structured outputs — [OVH AI Endpoints capabilities](https://docs.ovhcloud.com/en/guides/public-cloud/ai-machine-learning/ai-endpoints-capabilities) (lastUpdated 2026-10-29)
  - The catalog marks function calling "Yes" for Qwen3.8-27B, Qwen3.5-397B, Qwen3.6-27B, Qwen3.5-9B, gpt-oss-120b/20b, Mistral-Small-3.2, Llama-3.3-70B and Mistral-Nemo, and "No" for Qwen2.5-VL-72B. Vision is "Yes" for the Qwen3.x models and Mistral-Small-3.2. — [OVH catalog](https://www.ovhcloud.com/en/public-cloud/ai-endpoints/catalog/)
  - Unified base URL observed: `https://oai.endpoints.kepler.ai.cloud.ovh.net/v1` — [OVH /v1/models](https://oai.endpoints.kepler.ai.cloud.ovh.net/v1/models)
- **IONOS**
  - OpenAI-compatible endpoints include `POST /v1/chat/completions`, models, embeddings and images — [IONOS overview](https://docs.ionos.com/cloud/ai/ai-model-hub/overview)
  - The Qwen3.5 397B and GPT-OSS 120B model cards show Streaming / Reasoning / Tool calling all "Supported" — [Qwen3.5 397B card](https://docs.ionos.com/cloud/ai/ai-model-hub/models/llms/qwen3-5-397b); [GPT-OSS 120B card](https://docs.ionos.com/cloud/ai/ai-model-hub/models/llms/openai-gpt-oss-120b)
  - Tool calling how-to uses `OpenAI(base_url=IONOS_API_URL, …)`. "Not all Large Language Models… support tool calling… check the individual model cards." — [IONOS tool calling how-to](https://docs.ionos.com/cloud/ai/ai-model-hub/how-tos/tool-calling)
  - IONOS also documents a Responses API — [IONOS docs index](https://docs.ionos.com/cloud/llms.txt)
- **STACKIT**
  - Base URL `https://api.openai-compat.model-serving.eu01.onstackit.cloud/v1`; endpoints `/chat/completions`, `/completions`, `/models`. Features: "Tool calling enabled" (Qwen3-VL-235B, Llama 3.3) and "Tool calling & Reasoning enabled" (Qwen3.8-27B, gpt-oss-120b/20b, Gemma-4-31B). — [STACKIT available shared models](https://docs.stackit.cloud/products/data-and-ai/ai-model-serving/basics/available-shared-models/)
  - Known issue: sending `"tools": []` can cause some Llama-based models to generate hallucinated function calls, so omit the key when there are no tools. — [STACKIT FAQ](https://docs.stackit.cloud/products/data-and-ai/ai-model-serving/faq/)
  - Docs include LangChain tutorials and a tool-calling how-to — [STACKIT getting started](https://docs.stackit.cloud/products/data-and-ai/ai-model-serving/getting-started/getting-started-with-shared-models/)
- **T-Systems AIFS**
  - "Most LLMs… support streaming + tool/function calling." The table marks Streaming ✓ and Tool calling ✓ for every T-Cloud-hosted production model (GLM 5.2, GLM 5.3 Flash, GPT-OSS 120B, Qwen 3.8 27B, etc.). Reasoning tokens are reported in `usage.reasoning_tokens` or `completion_tokens_details.reasoning_tokens` depending on the model. — [T-Systems AIFS LLM list](https://docs.llmhub.t-systems.net/models/llms/)
  - The function-calling guide covers "Streaming — Stream function calling responses in real-time", and there is a LangChain integration guide — [T-Systems function calling guide](https://docs.llmhub.t-systems.net/guides/function-calling/)
- **Infomaniak**
  - "Access the best open source AI models via OpenAI-compatible APIs" and "Function calling to connect your models to your applications" — [Infomaniak AI Tools](https://www.infomaniak.com/en/hosting/ai-tools)
  - API reference exists at `/2/ai/{product_id}/openai/v1/chat/completions` (page is JS-rendered, so contents unread) — [Infomaniak developer portal](https://developer.infomaniak.com/docs/api/post/2/ai/%7Bproduct_id%7D/openai/v1/chat/completions)

### Inferences
- For LangChain `ChatOpenAI(base_url=…)` plus `bind_tools`:
  - Scaleway works with GLM, DeepSeek and Qwen.
  - Scaleway gpt-oss-120b needs `use_responses_api=True`, or another model.
  - IONOS, STACKIT, OVH and T-Systems should work with their current Qwen and gpt-oss models.
- Infomaniak's base URL includes a per-account `product_id`, so the base URL is account-specific. This is an inference from the API path.
- Streaming tool-call deltas are confirmed only for T-Systems. Run a quick smoke test (stream=True with bound tools) on any provider before committing.

### Gaps
- No explicit streaming plus tool-calling example was found for OVH, STACKIT or Infomaniak.
- Vision support at Infomaniak (Kimi-K2.6 is multimodal upstream) is unverified on Infomaniak's API.

## Q3. What do the terms say about logging, retention and training on prompts? Is a DPA available?

### Takeaway
Every provider states that prompts are **not used for training**. Retention wording differs:
- **IONOS** has the strongest, most specific statement: prompts and outputs are never logged or persisted, no sub-processors, EU-only staff access, and the DPA is part of every contract automatically.
- **Scaleway** has a "Zero Data Retention" default, with two carve-outs: requests that cause abnormal errors or look malicious may be stored for up to 2 weeks, and prefix/KV caching (no prompt text) cannot be disabled.
- **STACKIT** stores no customer data, but logs the user's email and subject ID for 30 days.
- **T-Systems** does not store or show prompts for T-Cloud models; the DPA is on request. Its closed models go to Azure or GCP under third-party terms.
- **OVH**, **Infomaniak** and **Lyceum** make short marketing-level "not stored / not used for training" claims.

### Cited Findings
- **Scaleway**
  - "By default we apply a Zero Data Retention Policy." Metadata and token counts are collected, "excluding the actual content of the prompts".
  - Caching stores "only intermediate values such as prefix hashes or KV values", is ephemeral, isolated per project and "cannot be disabled".
  - On misuse or errors (e.g., HTTP 500) Scaleway "may store temporarily… the full content of HTTP requests… for up to two weeks".
  - Data is "not used for training"; anonymized usage data is kept up to 6 months.
  - Scaleway is the data processor. GDPR compliant; personal data stored in Paris.
  - "As a European company, Scaleway's AI services are not subject to extraterritorial laws such as the American Cloud Act."
  - Source: [Scaleway Generative APIs privacy policy](https://www.scaleway.com/en/docs/generative-apis/reference-content/data-privacy/) ([source](https://github.com/scaleway/docs-content/blob/main/pages/generative-apis/reference-content/data-privacy.mdx), validated 2025-10-03). It supplements the [AI Services Specific Conditions](https://www-uploads.scaleway.com/Specific_Conditions_AI_Services_275907180f.pdf).
- **OVHcloud**
  - "Our infrastructure, hosted in Europe, adheres to European data protection regulations. Data is not stored or shared during or after model use." — [OVH AI Endpoints capabilities](https://docs.ovhcloud.com/en/guides/public-cloud/ai-machine-learning/ai-endpoints-capabilities)
- **IONOS**
  - "The content of your prompts and of the outputs… is never logged and is never accessed by IONOS CLOUD personnel… not written to any log or to persistent storage; … not used to train, fine-tune or otherwise improve any model."
  - Only metadata (timestamp, model, token counts) is recorded.
  - "No third-party sub-processors". Operational access only by staff located in the EU.
  - ISO 27001 data centres; BSI C5 scope.
  - The DPA "applies as part of your contract… does not require separate signature".
  - Source: [IONOS Data Handling](https://docs.ionos.com/cloud/ai/ai-model-hub/governance-and-compliance/data-handling)
- **STACKIT**
  - "Your data and queries are neither stored nor used to train models." — [STACKIT product page](https://stackit.com/en/products/data-ai/stackit-ai-model-serving)
  - Service certificate v1.4 (valid from 2026-11-06): "Customer data is not stored permanently. The e-mail and subject ID are stored temporarily (30 days) in the logs of the service." — [STACKIT service certificate v1.4 (PDF)](https://stackit.com/en/asset/download/61500/file/Service_Certificate_STACKIT_AI_Model_Serving_1-4.pdf?version=10)
  - The FAQ says STACKIT does not store request data and does not train on customer data — [STACKIT FAQ](https://docs.stackit.cloud/products/data-and-ai/ai-model-serving/faq/)
- **T-Systems AIFS**
  - Category 1 (T-Cloud) models: "Customer prompts and returned results are not stored and not viewable by Telekom or third parties"; "Not used for model training".
  - Category 2 (GPT/Claude/Gemini/Mistral Medium) "may process data worldwide" under the third party's terms.
  - "A Data Processing Agreement (DPA) based on Telekom's template is available on request."
  - Source: [T-Systems Enterprise Trust](https://docs.llmhub.t-systems.net/reference/enterprise-trust/)
- **Infomaniak**
  - "Your queries are neither recorded nor used to train models or improve our services"; "full compliance with the FADP and GDPR"; data centres in Switzerland — [Infomaniak AI Tools](https://www.infomaniak.com/en/hosting/ai-tools)
- **Lyceum**
  - "We don't keep your prompts or outputs, and we never use them for training. GPUs run in European data centres." — [Lyceum models](https://lyceum.technology/models/)
- **Regolo**
  - Advertises "Zero Data Retention" with a certificate. The pricing page does not state a training policy. — [Regolo pricing](https://regolo.ai/pricing/)

### Inferences
- For a privacy-focused hobby app, IONOS has the clearest written no-logging guarantee, but it is commercial-only (see Q4). Scaleway's policy is detailed and nearly as strong; the small carve-outs are error and abuse debugging (≤2 weeks) and mandatory KV caching.
- At T-Systems, only the T-Cloud-hosted models get the strong guarantees. Picking a GPT, Claude or Gemini model on the same API key changes the data regime.

### Gaps
- I did not read OVH's AI Endpoints Conditions or Infomaniak's full AI terms or DPA, so their exact retention periods for abuse logs are unknown.
- Whether individuals (as opposed to companies) can execute a DPA with Scaleway, OVH or Infomaniak is not stated on the pages read. A GDPR DPA is mainly relevant when the customer is itself a controller processing others' data.

## Q4. Can a private individual sign up and pay per use? (Also: jurisdiction, data-centre location, CLOUD Act exposure, and rate limits)

### Takeaway
- **Most hobbyist-friendly:** Scaleway (1M free tokens, pay-as-you-go, limits increase after ID verification), OVH (anonymous trial at 2 RPM, then pay per token per Public Cloud project) and Infomaniak (1M free credits, card required, monthly billing).
- **IONOS** explicitly says its offer is "for commercial use only".
- **T-Systems** needs a €1,000/month minimum on its entry plan (a free trial key exists).
- **STACKIT** trial registrations are "manually checked… if you qualify". Individual eligibility is unconfirmed.

All of these are EU or Swiss companies. Only Scaleway makes an explicit "not subject to the US CLOUD Act" statement in its AI service terms.

### Cited Findings
- **Scaleway** (Scaleway SAS, Paris)
  - Serverless models are hosted "in a secure data center located in Paris, France, operated by OPCORE"; future locations will stay in Europe — [Scaleway Generative APIs FAQ (source)](https://github.com/scaleway/docs-content/blob/main/pages/generative-apis/faq.mdx)
  - Free tier is 1,000,000 tokens; after that, billing per token — same source
  - Organization quotas apply once a valid payment method is registered, and are "upgraded when you verify your identity". Example headers show 600 requests/min and 1,000,000 tokens/min. Users can set per-project limits and per-user daily or monthly budgets. Batches API has no rate limit. — [Scaleway rate limits (source)](https://github.com/scaleway/docs-content/blob/main/pages/generative-apis/reference-content/rate-limits.mdx) (validated 2026-10-23)
  - Registered office: 8 rue de la Ville l'Évêque, 75008 Paris; CLOUD Act statement as quoted in Q3 — [Scaleway privacy policy](https://www.scaleway.com/en/docs/generative-apis/reference-content/data-privacy/)
- **OVHcloud**
  - Rate limits: anonymous 2 requests/min per IP per model; with an API key, 400 requests/min per Public Cloud project per model; 2 MB request body (10 MB for vision models); no other usage caps — [OVH AI Endpoints capabilities](https://docs.ovhcloud.com/en/guides/public-cloud/ai-machine-learning/ai-endpoints-capabilities)
  - The catalogue and playground need "no sign-up required" — [OVH catalog](https://www.ovhcloud.com/en/public-cloud/ai-endpoints/catalog/)
  - Infrastructure is "hosted in Europe". An older French version reportedly named Gravelines, but the current FR page no longer does. — [OVH capabilities](https://docs.ovhcloud.com/en/guides/public-cloud/ai-machine-learning/ai-endpoints-capabilities)
- **IONOS**
  - "The offer for the IONOS CLOUD products is for commercial use only." — [IONOS price list (EUR)](https://docs.ionos.com/cloud/support/general-information/price-list/ionos-cloud-eur-en)
  - Inference runs in IONOS data centres in Germany — [IONOS Data Handling](https://docs.ionos.com/cloud/ai/ai-model-hub/governance-and-compliance/data-handling)
  - Contracting entities include IONOS CLOUD GmbH (DE), Spain SLU, France SAS and UK Ltd. Price lists also exist for "IONOS CLOUD Inc." — [IONOS Data Handling](https://docs.ionos.com/cloud/ai/ai-model-hub/governance-and-compliance/data-handling); [IONOS price lists](https://docs.ionos.com/cloud/support/general-information/price-list)
  - Rate limits: 5 requests/s base and 10 requests/s burst, per model per contract. No published TPM cap. — [IONOS rate limits](https://docs.ionos.com/cloud/ai/ai-model-hub/how-tos/rate-limits)
- **STACKIT** (Schwarz Digits Cloud GmbH & Co. KG, Bad Friedrichshall; region EU01)
  - Free 30-day trial; "All registrations are manually checked by us. If you qualify…". Billing is token-based. — [STACKIT product page](https://stackit.com/en/products/data-ai/stackit-ai-model-serving)
  - Prerequisites are a STACKIT customer account, user account and project; creating a token is an "Order fee-based" action — [STACKIT getting started](https://docs.stackit.cloud/products/data-and-ai/ai-model-serving/getting-started/getting-started-with-shared-models/)
  - Rate limits are per project, combining RPM and TPM, where TPM = prompt + 5×generation tokens — [STACKIT rate limits](https://docs.stackit.cloud/products/data-and-ai/ai-model-serving/how-tos/rate-limits-on-shared-models-_stackit-ai-model-serving/)
  - Per-model limits — [STACKIT available shared models](https://docs.stackit.cloud/products/data-and-ai/ai-model-serving/basics/available-shared-models/):
    - Qwen3-VL-235B: 350k TPM / 30 RPM
    - Qwen3.8-27B: 350k TPM / 45 RPM
    - gpt-oss-120b: 200k TPM / 30 RPM
    - Gemma-4-31B and gpt-oss-20b: 200k TPM / 80 RPM
- **T-Systems AIFS** (T-Systems International; models hosted on T-Cloud Public in Germany)
  - "The monthly minimum revenue for models on the Essential rate plan is: € 1,000"; pricing valid from 2026-08-01 — [T-Systems Essential plan](https://docs.llmhub.t-systems.net/plans/essential/)
  - Plans are ordered via the T-Cloud Marketplace. A free trial key is available. Example limits for GPT-OSS 120B: Essential 300 RPM / 300k input TPM, Agentic 1,000 RPM / 2M TPM. These are best-effort and not in the SLA. — [T-Systems AIFS FAQ](https://docs.llmhub.t-systems.net/faq/)
  - Test/Preview models have dynamic rate limits and can be withdrawn without notice — [T-Systems Test plan](https://docs.llmhub.t-systems.net/plans/test/)
  - The service targets "companies" — [T-Systems AIFS FAQ](https://docs.llmhub.t-systems.net/faq/)
- **Infomaniak** (Switzerland; data centres in Switzerland)
  - "Get started with 1M free credits"; "no commitment period" — [Infomaniak AI prices](https://www.infomaniak.com/en/hosting/ai-tools/prices)
  - Usage is billed at month-end by tokens. Account creation requires "registering a valid payment card" for anti-fraud identity confirmation. — [Infomaniak AI Tools](https://www.infomaniak.com/en/hosting/ai-tools)
- **Regolo**
  - 30-day free trial with no credit card, 1M tokens/day and stricter rate limits. Pay-as-you-go, or a Core plan (€39/month list) aimed at "solo builders". — [Regolo pricing](https://regolo.ai/pricing/)

### Inferences
- Best fits for a privacy-minded hobbyist who needs tool calling and big models:
  - **Scaleway**: GLM-5.3 and DeepSeek-V4.x; individual-friendly free tier; explicit no-CLOUD-Act statement.
  - **Infomaniak**: Kimi-K2.6 and Qwen3.5-397B under Swiss law, outside the EU. Switzerland has an EU adequacy decision; that is general knowledge, not verified here.
  - **OVH**: cheapest gpt-oss-120b and Qwen3.5-397B, but no Kimi, DeepSeek or GLM.
- IONOS's "commercial use only" clause and T-Systems' €1,000 minimum effectively rule them out for a private hobbyist.
- IONOS has a US entity (IONOS CLOUD Inc.) in its group. Whether that creates CLOUD Act exposure for EU data is a legal question I did not resolve; IONOS itself says operational access is EU-only.
- OVH has a US subsidiary too (general knowledge, not verified here), and the same caveat applies.

### Gaps
- I could not confirm from official pages whether Scaleway, OVHcloud or STACKIT accept private individuals (non-business) for these specific services, or whether VAT ID or company details are required. Scaleway's account-creation doc did not load in a usable form.
- I could not verify Scaleway's exact default Organization quotas for unverified vs. ID-verified accounts. They are on a separate quotas page I couldn't fetch.
- I did not verify CLOUD Act statements for OVH, IONOS, STACKIT, T-Systems or Infomaniak from their own documents, and I did not research parent-company structures beyond page footers.
- I found no official parent or jurisdiction details, sign-up rules, tool-calling docs or terms for Lyceum. Its claims are vendor-reported only.
