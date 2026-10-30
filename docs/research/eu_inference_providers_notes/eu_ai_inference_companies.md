# European AI-native inference companies and EU LLM routers serving open-weight models (pay-per-token), as of 2026-10-30

Method note: model catalogs for Berget, Cortecs, Regolo, Inceptron and Sference were pulled live on 2026-10-30 from their public, unauthenticated OpenAI-style `/v1/models` endpoints, so they are primary data. Nebius's catalog needs a login, so its prices come from a third-party snapshot dated 2026-10-20 (benchlm.ai). Many vendor web pages render client-side and could not be read; those gaps are listed. Jurisdiction labels: EU = EU member state; UK and Swiss entities are marked as such.

## Q1. Who serves the large open models today (Kimi, DeepSeek, GLM, Qwen, gpt-oss, MiniMax, Mistral, Llama), where, and at what price?

### Takeaway
Late-2026 open models are Kimi K3 / K2.6 / K2.7-Code, DeepSeek V4 / V4.1 Flash / V4 Pro, GLM-5.1 to 5.3 (plus 5.3-Flash), Qwen3.5 / 3.6 / 3.8, gpt-oss-120b/20b and MiniMax M3. Several EU-native companies serve them: Nebius (NL), Berget (SE), Inceptron (SE), TensorX (IE), Arkane (FR), Regolo (IT), Mistral (FR), plus Sference (UK HQ per PitchBook, compute in the EEA). The Cortecs router (AT) aggregates them. "Kimi K3.1" exists only as **Kimi K3.1 Pro**, which is API-only from Moonshot since 2026-10-23, with weights due 2026-11-04. No EU host can serve it yet. Berget has already announced a migration from Kimi-K3 to Kimi-K3.1-Pro.

### Cited Findings

**Kimi naming and status**
- Kimi K3 launched on Moonshot's API on 2026-07-16, and Moonshot promised weights by 2026-07-27 — [emergent.sh](https://emergent.sh/news/kimi-k3-release-date). Reports say it has 2.8T parameters and 1M context — [llmgateway.io](https://llmgateway.io/blog/kimi-k3-open-weights); [howaiworks.ai](https://howaiworks.ai/blog/moonshot-kimi-k3-release-announcement).
- The Hugging Face repo `moonshotai/Kimi-K3` is public and ungated, with license tag `license:other` and lastModified 2026-09-02 — [HF API](https://huggingface.co/api/models/moonshotai/Kimi-K3). Secondary sources disagree on the license: "modified MIT" per [claudelog](https://claudelog.com/faqs/what-is-kimi-k3/) versus "Commercial Use Restricted" per [techjacksolutions](https://techjacksolutions.com/?p=66310). Unresolved.
- Moonshot released **Kimi K3.1 Pro** through its API on 2026-10-23 as a post-trained K3 variant with 1M context. Weights are "planned for release on November 4". Moonshot API pricing is $2 input / $10 output per M (citing Simon Willison) — [letsdatascience.com, 2026-10-23](https://letsdatascience.com/news/moonshot-releases-kimi-k31-pro-api-open-weights-due-nov-4-786e160c). The HF repos `moonshotai/Kimi-K3.1-Pro` and `moonshotai/Kimi-K3.1` return 401 (not public) — [HF API](https://huggingface.co/api/models/moonshotai/Kimi-K3.1-Pro).
- Earlier Kimi models still served: K2.6 (2026-04-20) and K2.7 Code (June 2026) — [cntechpost](https://cntechpost.com/2026/04/21/moonshot-releases-open-sources-latest-model-kimi-k2-6-2/); [Wikipedia](https://en.wikipedia.org/wiki/Kimi_(chatbot)).
- Berget's model API lists `moonshotai/Kimi-K3` with `lifecycle_status: upgrading`, `upgrade_to: moonshotai/Kimi-K3.1-Pro` and `end_of_life: 2026-11-06` — [api.berget.ai/v1/models](https://api.berget.ai/v1/models).

**Nebius Token Factory (formerly Nebius AI Studio). EU (Netherlands); parent Nebius Group N.V., NASDAQ: NBIS**
- The parent is Nebius Group N.V. (NASDAQ: NBIS). The contracting entity is "the applicable Nebius entity identified in the relevant Terms of Service". Data may be accessed by "Nebius group entities in the United States, Israel or Serbia". Public (serverless) endpoints show the location "Global", "decided dynamically". Dedicated endpoints have a fixed, chosen region. Retained data is stored in Finland — [Nebius Legal Quick Guide](https://docs.tokenfactory.nebius.com/legal/legal-quick-guide).
- Press release: "Zero-retention inference in EU or US datacenters" — [Nebius newsroom](https://nebius.com/newsroom/nebius-launches-nebius-token-factory-to-deliver-production-ai-inference-at-scale). A third party lists Nebius as "EU, Finland" — [opper.ai](https://opper.ai/provider/nebius). Unconfirmed by Nebius for serverless.
- Catalog (USD per M input/output, benchlm snapshot 2026-10-20, secondary): Kimi-K3 $3.00/$15.00; Kimi-K2.6 $0.95/$4.00; Kimi-K2.7-Code $0.95/$4.00; DeepSeek-V4.1-Flash $0.30/$1.20; DeepSeek-V4-Pro $1.75/$3.50; DeepSeek-V4-Pro-0813 $1.32/$3.96; DeepSeek-V4-Flash-0731 $0.14/$0.28; GLM-5.3, GLM-5.2 and GLM-5.1 each $1.40/$4.40; GLM-5.3-Flash $0.15/$0.50; Qwen3.8-27B $0.45/$3.00; Qwen3.5-397B-A17B $0.60/$3.60; Qwen3-235B-A22B-Instruct-2507 $0.20/$0.60; Qwen3-30B-A3B-Instruct-2507 $0.10/$0.30; gpt-oss-120b $0.15/$0.60; MiniMax-M3 $0.30/$1.20; Hermes-4-405B $1.00/$3.00; Nemotron-3-Ultra-550b $1.00/$3.00; Gemma-3-27b $0.10/$0.30; Muse Spark Open (Meta) $1.25/$4.25. No Llama is listed — [benchlm.ai/hosts/nebius](https://benchlm.ai/hosts/nebius).
- Models come in "Base" and "Fast" flavors. Append `-fast` to the model name for the low-latency flavor, which is priced differently — [Nebius inference overview](https://docs.tokenfactory.nebius.com/ai-models-inference/overview.md).
- Base URL `https://api.tokenfactory.nebius.com/v1/`, OpenAI SDK compatible. Sign-up is via Google or GitHub — [Nebius docs home](https://docs.tokenfactory.nebius.com/).

**Berget AI. EU (Sweden): Berget AI AB, org. no. 559504-7522**
- Live catalog (EUR per M, excl. VAT) — [api.berget.ai/v1/models](https://api.berget.ai/v1/models):
  - `moonshotai/Kimi-K3`: €3 / €15, cached input €0.90, MXFP4 quantization, vision, function_calling and streaming true, EOL 2026-11-06, to be upgraded to Kimi-K3.1-Pro.
  - `zai-org/GLM-5.3-Flash`: €0.25 / €0.50, FP8, vision, tools.
  - `mistralai/Mistral-Small-3.2-24B-Instruct-2506`: €0.30 / €0.30.
  - `google/gemma-4-31B-it`: €0.25 / €0.50.
  - Also: Qwen3.5-2B and other small "system-one" preview models, Whisper STT variants, and multilingual-e5 embeddings.
  - No DeepSeek, gpt-oss, Qwen-large or Llama.
- Models are "hosted in Sweden" — [berget.ai/models](https://berget.ai/models). The DPA says "All Berget AI data centres are within the European Economic Area". Sub-processors: AI Iron AB (GPU bare metal), Acebit AB (network/ops), Obenet AB (colocation), Stripe Payments Europe Ltd (card payments). No US company is named — [Berget DPA, last updated 2026-10-22](https://berget.ai/dpa).

**Mistral AI La Plateforme / "Mistral Studio". EU (France)**
- Mistral now serves **third-party open-weight models** besides its own: "Z.ai GLM 5.3", "Z.ai GLM 5.3 Flash" and "DeepSeek V4.1 Flash 1017". The GLM 5.3 card reads: "A third-party open weight text model from Z.ai with a 1M-token context window". GLM 5.2 (`zai-glm-5-2`) appears in the deprecated table. No Kimi, Qwen or gpt-oss — [Mistral models docs](https://docs.mistral.ai/getting-started/models/).
- Mistral's own models: Mistral Large 4 (v26.10), Mistral Medium 3.5, Mistral Small 4, Mistral Large 3, Ministral 3 14B/8B/3B, Codestral, Voxtral, OCR and others — [Mistral models docs](https://docs.mistral.ai/getting-started/models/).
- Public pricing page shows "Mistral Large" at $0.5 input / $1.5 output per M, batch at -50%, and cached input "up to 90%" off. Prices for the GLM and DeepSeek models were not visible — [mistral.ai/pricing](https://mistral.ai/pricing).
- Cortecs lists "mistral" as an upstream provider for glm-5.3, glm-5.3-flash, glm-5.2 and deepseek-v4.1-flash-1017. This corroborates that Mistral hosts them — [api.cortecs.ai/v1/models](https://api.cortecs.ai/v1/models).

**Regolo.ai. EU (Italy): SEEWEB s.r.l., Frosinone; DHH group branding**
- Live model IDs: `glm5.2`, `gpt-oss-120b`, `gpt-oss-20b`, `qwen3.5-122b`, `qwen3.5-9b`, `qwen3.8-27b`, `mistral-small-4-119b`, `gemma4-31b`, `apertus-70b` (Swiss Apertus), `brick-complexity-pro`, `brick-v1-beta`, `deepseek-ocr-2`, plus embedding, reranker, image and Whisper models. **No Kimi, no DeepSeek LLM, no MiniMax** — [api.regolo.ai/v1/models](https://api.regolo.ai/v1/models).
- PAYG prices (EUR per M, excl. VAT): glm5.2 €2.00/€5.20; gpt-oss-120b €1.00/€4.20; gpt-oss-20b €0.10/€0.42; qwen3.5-122b €1.00/€4.20; qwen3.8-27b €0.50/€2.10; qwen3.5-9b €0.07/€0.35; mistral-small-4-119b €0.50/€2.10; gemma4-31b €0.40/€2.10; apertus-70b €0.40/€2.10. The page notes "a pricing update takes effect November 1" — [regolo.ai/pricing](https://regolo.ai/pricing).
- Entity: SEEWEB s.r.l., Via A. Vona 66, Frosinone. The policy does not name data-center cities — [Regolo privacy policy](https://regolo.ai/privacy-policy/).

**Inceptron. EU (Sweden): Inceptron AB, Lund**
- Swedish company in Lund with its own compiler. Serves serverless open models and dedicated GPUs. Infrastructure is "inside the EU" — [infrabase.ai](https://infrabase.ai/inference-apis/inceptron); [Kilo blog](https://blog.kilo.ai/p/kilo-partners-with-inceptron-for).
- Live catalog. Per-token prices are converted here to per M. The API uses OpenRouter-style fields and does not state a currency, so USD is assumed (unverified): `zai-org/GLM-5.2` 1.20/4.40; `zai-org/GLM-5.3` 1.20/2.20; `zai-org/GLM-5.3-Flash` 0.17/0.60; `moonshotai/Kimi-K2.6` 0.624/3.50 (vision); `moonshotai/Kimi-K2.7-Code` 0.56/3.10 (vision); `deepseek-ai/DeepSeek-V4-Flash-0731` 0.13/0.46. All models list `tools`, `reasoning`, `json_mode` and `structured_outputs` — [api.inceptron.io/v1/models](https://api.inceptron.io/v1/models).

**TensorX (formerly Tensorix). EU (Ireland): TensorX Ltd., company no. 796387**
- The homepage says "TensorX-owned EU GPUs" and "EU Sovereign Infrastructure", with a "Full OpenAI-compatible API". Featured models: `deepseek/deepseek-v4.1-flash-1017`, `z-ai/glm-5.3`, `z-ai/glm-5.3-flash`, `moonshotai/kimi-k3`, `minimax/minimax-m3.1-flash`, `qwen/qwen3.8-2.4t-a95b`, and "42+ models" — [tensorx.ai](https://tensorx.ai/).
- Directories place inference in Dublin and Helsinki ([infrabase](https://infrabase.ai/inference-apis/tensorix)), in Dublin, Helsinki or Paris ([Eden AI](https://www.edenai.co/providers/tensorx)), or in Ireland only ([Requesty](https://www.requesty.ai/models/tensorx)). These conflict and are unverified. Dealroom reports a $10M raise; founded 2025 — [dealroom](https://dealroom.co/news/161383-tensorx-raises-10m-to-build-gdpr-hardened-ai-inference-in-europe/).
- Through Cortecs, TensorX is the sole provider of qwen3.8-2.4t-a95b (€2.244/€5.386) and minimax-m3.1-flash (€0.273/€1.094), and one of several providers for kimi-k3, glm-5.3, deepseek-v4-pro-0813 and minimax-m3 — [api.cortecs.ai/v1/models](https://api.cortecs.ai/v1/models). Its own API at `api.tensorix.ai/v1` requires a key.

**Sference. Labelled UK: PitchBook lists HQ London; compute "EEA-resident"**
- PitchBook lists Sference as founded in 2026 and headquartered in London — [PitchBook](https://pitchbook.com/profiles/company/1440493-12). Opper describes compute inside the EEA with ZDR by default — [Opper blog](https://opper.ai/blog/sference-partnership). Website: "Every request runs on European GPUs" — [sference.com](https://www.sference.com).
- Live catalog (USD per M, input/output/cached): `moonshotai/Kimi-K3` 3.00/15.00/0.45 (vision, tools, thinking); `zai-org/GLM-5.3` and `zai-org/GLM-5.2` 1.20/4.20; `zai-org/GLM-5.3-Flash` 0.20/0.60 (vision); `deepseek-ai/DeepSeek-V4-Flash` and `-0731` 0.28/0.56; `deepseek-ai/DeepSeek-V4.1-Flash` and `-1017` 0.50/1.50 (vision). All list tools — [api.sference.com/v1/models](https://api.sference.com/v1/models).
- Tiers: Realtime at list price; Priority 1.3×; Flex 0.7× (up to 30 min wait); Batch 0.5× (24h) — [sference.com](https://www.sference.com).

**Arkane. EU (France, Lyon)**
- Cortecs provider page: Lyon, France (arkanecloud.com). Payloads are processed within France. Zero data retention — [cortecs.ai/providerView/arkane](https://cortecs.ai/providerView/arkane).
- Via Cortecs, Arkane serves kimi-k3, deepseek-v4-pro (€1.526/€3.052 per Cortecs), deepseek-v3.2, glm-5.2, glm-5.3, minimax-m3, qwen3.8-27b and deepseek-v4.1-flash — [api.cortecs.ai/v1/models](https://api.cortecs.ai/v1/models).

**Infercom. EU (Luxembourg)**
- Infercom is a sovereign inference API serving open LLMs on its own SambaNova hardware at Equinix Munich MU4 — [infrabase.ai/european](https://infrabase.ai/european); [SambaNova press](https://sambanova.ai/press/sambanova-powers-eus-first-sovereign-ai-inference-service-with-infercom); [Paperjam](https://en.paperjam.lu/article/infercom-launches-first-european-sovereign-inference-ai-1). It is OpenAI-compatible — [HF infercomai](https://huggingface.co/infercomai).
- Via Cortecs it serves only gpt-oss-120b and gemma-4-31b-it — [api.cortecs.ai/v1/models](https://api.cortecs.ai/v1/models).

**Other EU providers seen in Cortecs's "Sovereign Cloud" list (not independently researched)**
- AKI (AKI.IO, "European AI API for open-source models on EU infrastructure" — [infrabase.ai/european](https://infrabase.ai/european)) serves apertus-70b, kolibri-1, glm-5.3, qwen3.6-35b-a3b, qwen3.8-27b, gpt-oss-120b and deepseek-v4.1-flash-1017.
- Entrim serves glm-5.3, glm-5.3-flash, qwen3.8-27b and deepseek-v4.1-flash-1017.
- Both per [api.cortecs.ai/v1/models](https://api.cortecs.ai/v1/models).

**Cortecs aggregated catalog (EUR per M; 108 models; live 2026-10-30)** — [api.cortecs.ai/v1/models](https://api.cortecs.ai/v1/models)
- **Kimi:**
  - kimi-k3: €2.693/€13.464 via nebius, tensorix, berget, arkane, sference.
  - kimi-k2.7-code: €0.589/€2.962 via tensorix, inceptron.
  - kimi-k2.6: €0.426/€2.666 via inceptron.
- **DeepSeek:**
  - deepseek-v4.1-flash-1017: €0.182/€0.547 via tensorix, sference, aki, entrim, mistral, arkane.
  - deepseek-v4-flash-0731: €0.074/€0.371.
  - deepseek-v4-pro: €1.526/€3.052 via arkane.
  - deepseek-v4-pro-0813: €1.795/€3.59 via tensorix.
  - deepseek-v3.2: €0.449/€1.346 via arkane.
- **GLM:**
  - glm-5.3: €0.459/€1.836 via 8 providers including mistral and scaleway.
  - glm-5.3-flash: €0.09/€0.314.
  - glm-5.2: €0.808/€2.908.
  - glm-5.1: €1.242/€3.903 via nebius.
  - glm-4.7-flash: amazon_ireland only.
- **Qwen:**
  - qwen3.8-27b: €0.09/€0.359 via 8 providers.
  - qwen3.8-2.4t-a95b: €2.244/€5.386.
  - qwen3.5-397b-a17b: €0.60/€3.60 via scaleway, ovh, ionos.
  - qwen3-235b-a22b-instruct-2507: €0.179/€0.537.
- **gpt-oss:**
  - gpt-oss-120b: €0.08/€0.40 via scaleway, nebius, ionos, ovh, amazon_ireland, infercom, aki.
  - gpt-oss-20b: €0.04/€0.15 via ovh, amazon_ireland.
- **MiniMax:**
  - minimax-m3: €0.269/€1.077 via tensorix, arkane.
  - minimax-m3.1-flash: via tensorix.
  - minimax-m2, m2.1, m2.5: amazon_ireland only.
- **Llama:** llama-3.3-70b-instruct €0.65/€0.65 via scaleway, ovh, ionos.
- **Mistral:**
  - mistral-large-4-0: €0.687/€2.11.
  - mistral-medium-3.5: €1.375/€7.04.
  - mistral-small-2603: €0.14/€0.561.
  - mistral-small-3.2: €0.09/€0.28.
  - The listing also includes Claude, Gemini and GPT models via AWS, Google and Azure EU regions.

### Inferences
- The Cortecs Kimi-K3 price of €2.693/€13.464 equals $3/$15 at about 0.898 EUR/USD. Cortecs appears to convert upstream USD list prices to EUR, so the price parity across Nebius, Sference and Berget is real: about $3/€3 input and $15/€15 output per M for Kimi K3 everywhere in the EU. Moonshot's own K3.1 Pro API, at $2/$10, is cheaper but China-based.
- Kimi K3.1 Pro weights are due on 2026-11-04, and Berget's K3 end-of-life is 2026-11-06. EU hosts, starting with Berget, will likely offer "Kimi-K3.1-Pro" within days of the weight release. That is not available as of 2026-10-30.
- For the user's stack, the best price/capability fits are GLM-5.3 (tools, 1M context), DeepSeek-V4.1-Flash-1017 (cheap, vision, tools) and Kimi K3 (frontier, expensive). The Kimi K3 cost per M is about 15 to 30 times that of GLM-5.3-Flash or DeepSeek-V4.1-Flash.
- Regolo is the outlier on price: its gpt-oss-120b at €1.00/€4.20 is about 6 to 12 times Nebius ($0.15/$0.60) or Cortecs (€0.08/€0.40). It also lacks Kimi and DeepSeek LLMs.
- CLOUD Act exposure, judged from corporate structure (legal inference, not legal advice):
  - Nebius has US group entities that may access data, and serverless locations are "Global". Highest exposure among the EU-native companies.
  - Cortecs routes to AWS, Google and Azure EU regions, which are exposed, unless Sovereign Cloud is enabled.
  - Berget names only Swedish sub-processors plus Stripe's Irish entity for payment data. Lowest apparent exposure.
  - Infercom sits in an Equinix (US-owned) colocation facility. Colocation providers typically have no logical data access, so exposure is minor.

### Gaps
- Nebius's official price list and per-model hosting region could not be read (login-gated catalog). Prices are from a 2026-10-20 third-party snapshot.
- Mistral's per-token prices for GLM 5.3, GLM 5.3 Flash and DeepSeek V4.1 Flash, and its inference data-center locations, were not found on official pages.
- Inceptron's currency, TensorX's own price list, and TensorX's data-center cities are unverified.
- Not covered: Fluidstack (no serverless API found in this session), Langdock (no results), and Aleph Alpha / PhariaAI. One secondary source says Aleph Alpha's legacy per-token Luminous API is wound down, PhariaAI is quote-only, and reports an April 2026 Cohere deal; all unverified — [usagepricing.com](https://usagepricing.com/blueprint/aleph-alpha).
- Nscale (UK) serverless: an OpenAI-compatible API and a "$5 free credit" are claimed in [Nscale blog](https://www.nscale.com/blog/from-idea-to-inference-in-minutes-welcome-to-nscale-serverless). The catalog endpoint `inference.api.nscale.com/v1/models` requires auth, and the models and prices could not be verified.
- Newer EU names were seen but not researched: Xference, Italian private inference on Aruba data centres launched in April 2026 ([Intelligent CIO](https://www.intelligentcio.com/eu/2026/04/28/xference-launches-european-private-ai-infrastructure-from-aruba-data-centres/)); and the Melious and LLMrouter.eu gateways ([european-alternatives.eu](https://european-alternatives.eu/category/ai-gateways)).
- Arkane's, Entrim's and AKI's legal entities and data-center locations were not verified beyond the Cortecs pages.

## Q2. Does each support OpenAI-compatible tool/function calling with streaming, the hard requirement for LangChain ChatOpenAI with a custom base_url and bind_tools?

### Takeaway
Every EU-native provider here exposes an OpenAI-compatible `/v1/chat/completions` endpoint. Per-model tool support is machine-readable for Berget, Cortecs, Inceptron and Sference, and every large open chat model listed there advertises `tools`. Berget explicitly flags `function_calling: true` together with `streaming: true`. Nebius documents OpenAI-format function calling. Streamed tool calls specifically are not documented anywhere and should be smoke-tested per model.

### Cited Findings
- **Berget:** per-model capability flags. Kimi-K3, GLM-5.3-Flash, Mistral-Small-3.2 and gemma-4-31B all have `function_calling: true`, `streaming: true` and `json_mode: true`; Kimi-K3, GLM-5.3-Flash and gemma-4 also have `vision: true` — [api.berget.ai/v1/models](https://api.berget.ai/v1/models). Its docs describe an OpenAI-compatible API — [docs.berget.ai](https://docs.berget.ai/models/overview).
- **Nebius:** "outputs tool invocation instructions in an OpenAI-compatible function calling format". Supports `tool_choice` (auto or a forced function). The doc example uses `meta-llama/Meta-Llama-3.1-8B-Instruct-fast` — [Nebius Function calling](https://docs.tokenfactory.nebius.com/ai-models-inference/function-calling.md). Base URL `https://api.tokenfactory.nebius.com/v1/` — [Nebius docs](https://docs.tokenfactory.nebius.com/).
- **Cortecs:** OpenAI SDK with base URL `https://api.cortecs.ai/v1/`. It also accepts tools built for "OpenAI or Anthropic endpoints" — [cortecs.ai](https://cortecs.ai). The per-model `supported_features` include `tools` for all Kimi, DeepSeek, GLM-5.x, Qwen3.5+, gpt-oss and MiniMax entries. Exceptions without tools: gemma-3-27b, qwen2.5-vl-72b, mixtral-8x7B, mistral-7b-v0.2 and the qwen3guard models — [api.cortecs.ai/v1/models](https://api.cortecs.ai/v1/models).
- **Inceptron:** all six models list `tools`, `json_mode`, `structured_outputs` and `reasoning` — [api.inceptron.io/v1/models](https://api.inceptron.io/v1/models).
- **Sference:** `tools.supported: true` on all chat models. Endpoints: `/v1/chat/completions`, `/v1/responses`, `/v1/batch`, `/v1/messages`. The site says "Streaming, tool calls, and your own fine-tunes on the hot path" — [api.sference.com/v1/models](https://api.sference.com/v1/models); [sference.com](https://www.sference.com).
- **TensorX:** "Full OpenAI-compatible API". Platform-level tool calling is not stated — [tensorx.ai](https://tensorx.ai/). Cortecs lists TensorX-served models with `tools` — [api.cortecs.ai/v1/models](https://api.cortecs.ai/v1/models).
- **Regolo:** the `/v1/models` endpoint is OpenAI-compatible but exposes no capability flags — [api.regolo.ai/v1/models](https://api.regolo.ai/v1/models).
- **Infercom:** OpenAI-compatible — [HF infercomai](https://huggingface.co/infercomai).

### Inferences
- Berget, Inceptron, Sference and Cortecs are the safest drop-ins for `ChatOpenAI(base_url=..., model=...)` plus `bind_tools`, because tool support is declared per model.
- Reasoning models (Kimi K3, GLM-5.x, DeepSeek V4.x) may stream "reasoning" fields that LangChain's ChatOpenAI ignores. This does not break tool calls but may hide thinking traces.
- Through Cortecs, the upstream that serves a given request can change between requests. Tool-call formatting quirks may therefore vary unless a provider is pinned.

### Gaps
- No provider explicitly documents tool calls **while streaming** (incremental `tool_calls` deltas). Berget's flags imply both are supported but not necessarily combined.
- Regolo's and Mistral's tool-calling support for GLM, gpt-oss and Qwen was not verified from official docs in this session.
- Nebius's per-model tool support is unknown, because the catalog is login-gated.
- No verified data on vision for Nebius models.

## Q3. What do the terms say about storing prompts, retention and training?

### Takeaway
Berget (DPA dated 2026-10-22), Regolo, Cortecs, TensorX, Arkane and Sference all claim zero retention of prompt content and no training. **Nebius retains inputs and outputs by default** to speed up speculative decoding, unless you switch on ZDR yourself, though it never trains on them. **Mistral may train on Free-tier API data**, gives pay-as-you-go users an opt-out, and grants ZDR only on approved request for paid organizations.

### Cited Findings
- **Nebius:**
  - "Unless you enable Zero Data Retention, we keep your inputs and outputs to speed up inference". ZDR is toggled in the account profile and "applies at the organization level".
  - "We do not use your content to train, fine-tune or improve any AI models". Retained data is stored in Finland; no retention period is stated.
  - GDPR compliant; a DPA is incorporated into the Terms of Service for "all our customers"; sub-processor additions get 15 days' notice.
  - Source: [Nebius Legal Quick Guide](https://docs.tokenfactory.nebius.com/legal/legal-quick-guide).
- **Berget:**
  - Serverless inference has zero data retention. It "does not store prompts, uploaded or streamed files, or outputs after completed inference calls", and nothing is written to persisted disks.
  - It logs only metadata: HTTP calls, status codes, timestamps, token counts and API keys.
  - It does not train on serverless inputs or outputs and does not share them with model providers for training.
  - Source: [Berget DPA, Appendix 2, updated 2026-10-22](https://berget.ai/dpa).
  - A third party says ZDR is on by default with no logging — [opper.ai](https://opper.ai/provider/berget).
- **Regolo:**
  - Inputs and outputs are "cancelled at the end of every Regolo.ai session", and the retention table says "Never". Usage logs record "request type (without the content)".
  - "Other uses of the input data are not expected or possible". Training is not explicitly mentioned.
  - Sources: [Regolo privacy policy](https://regolo.ai/privacy-policy/). The pricing page markets "zero-retention" and links a ZDR certificate — [regolo.ai/pricing](https://regolo.ai/pricing).
- **Mistral:**
  - Free mode: "we may use your data (input and output) to train our artificial intelligence models", with opt-out available. Pay-as-you-go: "Customers retain full control over this processing and have the right to opt out at any time". Source: [Mistral help 347617](https://help.mistral.ai/en/articles/347617-do-you-use-my-user-data-to-train-your-artificial-intelligence-models).
  - A secondary source reports that the PAYG opt-out is the "Anonymous improvement data" setting in the Admin panel — [aipricing.guru, 2026-09-02](https://www.aipricing.guru/news/mistral-user-data-training-default-opt-out-september-2026/).
  - ZDR is "available on paid plans for supported stateless API calls" and covers chat completions. You must request it with a "legitimate reason", and Mistral "may approve or deny it". ZDR excludes agents, batch, conversations, files and Labs models. Training opt-out is a separate control — [Mistral ZDR docs](https://docs.mistral.ai/admin/monitor-comply/zero-data-retention).
  - The default API retention (third parties say 30 days for abuse monitoring) was not confirmed on official pages.
- **Cortecs:**
  - "Never stores your prompts or uses them for model training". Payload is "processed strictly in temporary memory and deleted immediately after the request is finished". Standard providers are "prohibited from training on your data" — [cortecs.ai](https://cortecs.ai).
  - The ZDR setting routes only to "endpoints that do not retain data" — [Cortecs data governance docs](https://docs.cortecs.ai/security-and-compliance/data-governance-and-controls).
- **TensorX:** "Zero data retention by design". Logging and training are not stated — [tensorx.ai](https://tensorx.ai/). Requesty describes "ephemeral enclaves" with nothing stored or logged — [Requesty](https://www.requesty.ai/models/tensorx). Secondary.
- **Sference:** retention is configurable: inputs are deleted per your configured policy, and compliance logs (model version, region, timestamps) are kept. It "never trains on customer data, contractually and technically" — [sference.com](https://www.sference.com). Opper says ZDR is the default — [Opper blog](https://opper.ai/blog/sference-partnership).
- **Arkane:** zero data retention, processing in France — [cortecs.ai/providerView/arkane](https://cortecs.ai/providerView/arkane).

### Inferences
- A privacy-focused hobbyist using Nebius must enable ZDR on day one. Otherwise prompts are retained, location "Global", for an unstated period.
- On Mistral, Free-tier API keys should not be used for private chats. On PAYG, toggle the training opt-out.
- Berget's DPA is the most specific and most recent primary document. Its language is concrete: no persisted disk, metadata-only logs.

### Gaps
- Inceptron's privacy policy and DPA were not read.
- Retention periods for metadata logs (Berget) and for retained data (Nebius) are not stated.
- Regolo's ZDR certificate contents and Regolo's data-center cities were not verified.
- Whether TensorX and Sference publish a DPA was not verified.

## Q4. EU routers (Cortecs, Eden AI and others): do they guarantee EU-only routing, and what are the underlying providers' terms?

### Takeaway
Cortecs (Cortecs GmbH, Vienna) is the only EU router found with an explicit EU-sovereign mode. Requests stay in Europe by default. The "Sovereign Cloud" setting restricts routing to 12 EU-established providers: AKI, Arkane, Berget, Entrim, Inceptron, Infercom, IONOS, Mistral, Nebius, OVH, Scaleway and TensorX. The default pool also includes the EU regions of Amazon, Google and Microsoft, plus Sference (UK HQ). Cortecs acts as the single data processor, with providers as its sub-processors. Eden AI (France) is a general aggregator with no EU-routing statement found.

### Cited Findings
- Cortecs: "By default, all requests remain within Europe and your data is not used for AI training". Sovereign Cloud restricts routing to providers "based and regulated within the EU". Settings apply "project-wide or per request". Providers with ISO 27001 show a badge. A quantization setting controls routing to quantized endpoints — [Cortecs data governance docs](https://docs.cortecs.ai/security-and-compliance/data-governance-and-controls).
- Cortecs is the primary data processor; "one DPA is integrated into our Terms"; providers are its sub-processors. "We take the responsibility for our providers" — [Cortecs data governance docs](https://docs.cortecs.ai/security-and-compliance/data-governance-and-controls).
- Sovereign Cloud providers: AKI, Arkane, Berget, Entrim, Inceptron, Infercom, Ionos, Mistral, Nebius, OVH, Scaleway, TensorX. Other listed providers: Amazon, Google, Microsoft, Sference. 16 active in total. Users can exclude specific providers — [cortecs.ai](https://cortecs.ai).
- The live catalog's provider IDs include `amazon_ireland`, `amazon_paris`, `google`, `google_priority`, `azure_sc` and `azure_spc` (hyperscaler EU regions). Some open models route **only** through AWS Ireland: glm-4.7-flash, minimax-m2/m2.1/m2.5, qwen3-32b, qwen3-coder-30b, qwen3-vl-235b and gpt-oss-safeguard-120b. Others mix sovereign and AWS providers, for example gpt-oss-120b and gpt-oss-20b — [api.cortecs.ai/v1/models](https://api.cortecs.ai/v1/models).
- Nebius, a Sovereign Cloud member at Cortecs, labels its own public endpoints "Global" with dynamic location. Its group entities in the US, Israel and Serbia may access data — [Nebius Legal Quick Guide](https://docs.tokenfactory.nebius.com/legal/legal-quick-guide).
- Fees: the homepage says "a flat 5% service fee when topping up" ([cortecs.ai](https://cortecs.ai)). The pricing page describes the 5% as a service fee on token charges at upstream rates, billed in EUR ([cortecs.ai/pricing](https://cortecs.ai/pricing)). The two pages conflict on where the fee applies. Rate limits: "No. We offer unrestricted access to platform-wide limits" ([cortecs.ai](https://cortecs.ai)).
- Third-party claims: Cortecs is ISO-certified and claims EU-sovereign, AI Act and GDPR status — [european-alternatives.eu](https://european-alternatives.eu/product/cortecs).
- Eden AI (France): 5.5% platform fee on self-serve, "no markup on provider pricing", Stripe-prepaid credits with auto-refill. The plans page makes no EU-routing or retention statement — [Eden AI plans](https://www.edenai.co/docs/v3/overview/plans-prices). Eden AI lists TensorX as a provider — [Eden AI TensorX](https://www.edenai.co/providers/tensorx).

### Inferences
- With Sovereign Cloud plus ZDR enabled, Cortecs should avoid AWS, Google, Azure and Sference. It could still route to Nebius, whose serverless location is "Global" and which retains data by default unless ZDR is on. Whether Cortecs's ZDR filter excludes Nebius unless Nebius ZDR is active is not documented. The safest configuration is Sovereign Cloud plus ZDR plus an explicit exclusion of Nebius, or pinning providers per request.
- Cortecs's single-DPA model is simpler for an individual than signing DPAs with each upstream provider.

### Gaps
- Cortecs's full Terms and DPA text and its sub-processor list were not read. No per-provider retention table was found.
- Whether Sovereign Cloud is a contractual guarantee or a routing setting: the homepage does not call it a guarantee.
- Eden AI's data-retention and EU-routing terms, and the Melious and LLMrouter.eu gateways, were not researched.
- Langdock (Germany) was not researched; no results returned.

## Q5. Can a private individual sign up and pay per use (hobbyist suitability)?

### Takeaway
Hobbyists can pay as they go with no monthly fee on Regolo (PAYG plan, 30-day trial without a card), Cortecs (prepaid top-ups by card), Nebius (sign up with Google or GitHub) and Mistral (PAYG, with a training opt-out). Berget has **no pure PAYG**: there is a free €5 trial (card required), and after that a Starter plan at €25/month, whose credits roll over for 12 months. Sference targets companies.

### Cited Findings
- **Berget:**
  - Trial at €0 with €5 credits and basic rate limits. Starter €25/month (with a €25 top-up), Team €50/month (€55 credits), Enterprise €500/month.
  - "We don't offer pure pay-as-you-go without a plan". A card is required at signup. Unused credits roll over and are valid for 12 months.
  - The Trial is described "For the hobbyist", and the FAQ mentions Swedish private individuals as customers.
  - Source: [berget.ai/pricing](https://berget.ai/pricing).
- **Regolo:**
  - 30-day free trial with "no credit card", 1M tokens/day and stricter limits.
  - Pay-as-you-go at €0 monthly fee. Core €39/month (600M tokens/month, 20M/day, 70% off the first 3 months); Boost €89; Pro €169; Scale €319.
  - Per-key budgets can be set. Plan caps conflict between the FAQ and the plan cards. Prices change on November 1.
  - Source: [regolo.ai/pricing](https://regolo.ai/pricing).
- **Cortecs:**
  - Prepaid credit card with auto top-up, or invoice; billing in EUR. "All features unlocked from day one". No free tier is stated — [cortecs.ai/pricing](https://cortecs.ai/pricing).
  - Budgets and low-balance alerts per team, user or key — [cortecs.ai](https://cortecs.ai).
- **Nebius:**
  - Sign up at tokenfactory.nebius.com with Google or GitHub — [Nebius docs](https://docs.tokenfactory.nebius.com/).
  - Rate limits: baseline 60 RPM and 400,000 TPM, auto-scaling ×1.2 per 15-minute window at 80% or more utilization, up to a 20× hard ceiling. Higher needs an Enterprise plan. HTTP 429 when exceeded — [Nebius rate limits](https://docs.tokenfactory.nebius.com/ai-models-inference/rate-limits.md).
- **Mistral:** a Free plan exists, where API data may be used for training, plus PAYG — [mistral.ai/pricing](https://mistral.ai/pricing); [Mistral help](https://help.mistral.ai/en/articles/347617-do-you-use-my-user-data-to-train-your-artificial-intelligence-models).
- **Sference:** targets companies "from Series A up to enterprises". Accounts are created at app.sference.com with no minimum spend for serverless — [sference.com](https://www.sference.com).
- **Eden AI:** self-serve PAYG credits via Stripe plus a 5.5% fee — [Eden AI plans](https://www.edenai.co/docs/v3/overview/plans-prices).
- **Nscale (UK):** "$5 free credit" — [Nscale blog](https://www.nscale.com/blog/from-idea-to-inference-in-minutes-welcome-to-nscale-serverless).

### Inferences
- Best fit for a privacy-focused hobbyist who needs Kimi, DeepSeek or GLM with tools:
  - **Cortecs** with Sovereign Cloud plus ZDR: broadest catalog, one DPA, prepaid EUR.
  - **Berget**: strongest primary-source privacy terms and Swedish-only sub-processors, but a €25/month minimum after the trial and a narrow catalog (Kimi-K3, GLM-5.3-Flash, Mistral Small, Gemma 4).
  - **Nebius**: cheapest broad catalog, but ZDR must be enabled manually, endpoints are "Global", and US group access is possible.
  - **Regolo**: no-card trial and PAYG, but higher prices and no Kimi or DeepSeek.
- For an occasional user of Kimi K3 at €3/€15 per M, Berget's €25/month plan would mostly roll over credits. PAYG via Cortecs is likely cheaper unless usage is steady.

### Gaps
- Individual (non-business) eligibility is not stated explicitly for Cortecs, Nebius, TensorX, Inceptron or Sference.
- Payment methods, minimum top-ups and free credits for Nebius, TensorX and Inceptron are unverified.
- No numeric rate limits for Berget, Regolo (apart from daily token caps), TensorX, Inceptron or Sference.
- Nebius's billing model for individuals (card versus prepaid) was not verified in this session.
