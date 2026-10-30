# Hyperscalers and US inference specialists for open-weight LLMs (EU residency and privacy fallback), as of 2026-10-30

Scope note: I pulled most facts directly from official docs, pricing pages and public model-list APIs on 2026-10-30. Where a page shows a "last updated" date, I give it. Anything that rests only on aggregators (BenchLM, usagepricing, azurespeed, modelcompare, getmaxim, morphllm, standardcompute) is marked **[third-party]**. Anything I could not confirm is marked **[unverified]**. Every provider below has a US parent company, so the US CLOUD Act caveat applies to all of them, even when processing is pinned to an EU region (see Inferences under Q1 and Q2).

## Q0 (constraint check): What are the current Kimi models called, and who serves them?

### Takeaway
No model is called just "Kimi K3.1". The current model is **Kimi K3.1 Pro**, released 2026-10-23, plus a faster **K3.1 Pro Highspeed** variant. For now it is API-only: Moonshot says the weights will be released "by Nov 4" (2026). The newest Kimi model with weights already published is **Kimi K3** (July 2026, 2.8T total / 104B active, 1M context, vision). Many US hosts serve K3, and AWS Bedrock serves it through cross-region inference profiles only. At hyperscalers, older Kimi models are still common: K2.5 on Bedrock in-region in the EU, K2.5/K2.6/K2.7-Code on Azure, and only K2 Thinking on Vertex.

### Cited Findings
- Moonshot's announcement: "Kimi K3.1 Pro, the first model in our new K3.1 series and our most capable 3T-class open-weight model to date, with a 1-million-token context window." It is "available today on Kimi.ai, Kimi Work, Kimi Code, and the Kimi API. The full model weights will be released by Nov 4." The Highspeed variant "delivers 2-3× the speed." — [Kimi blog: Kimi K3.1 Pro](https://www.kimi.ai/blog/kimi-k3-1-pro)
- K3.1 Pro launched 2026-10-23 and ranks 4th on the Artificial Analysis Intelligence Index with a score of 55, up from 44 for Kimi K3. — [Artificial Analysis launch article](https://artificialanalysis.ai/articles/kimi-k3-1-pro-launch-benchmarks). A different AA model page lists a score of 46. I could not resolve the conflict, which was flagged in search snippets — [AA model page](https://artificialanalysis.ai/models/kimi-k3-1-pro)
- Kimi K3: an MoE model with 2.8T total and 104B active parameters, native vision and a 1,048,576-token context — [Modal model library](https://modal.com/library/moonshot/kimi-k3). Launched July 16, 2026 with weights to follow — [TechRepublic](https://www.techrepublic.com/article/news-apac-china-kimi-k3-moonshot-ai/). DeepInfra's `moonshotai/Kimi-K3` entry was created 2026-07-27 — [DeepInfra public model list API](https://api.deepinfra.com/models/list)
- Earlier models in the family: K2.5 (January 2026), K2.6 (April 20, 2026, open-sourced) — [CnTechPost](https://cntechpost.com/2026/04/21/moonshot-releases-open-sources-latest-model-kimi-k2-6-2/); K2.7-Code (June 12, 2026, per the Azure version string) — [Azure region availability](https://learn.microsoft.com/en-us/azure/foundry/foundry-models/concepts/models-sold-directly-by-azure-region-availability)
- Artificial Analysis lists 14 API providers for Kimi K3 (Max): "Databricks, Fireworks, Modal, Together AI, Makora, LithosAI (ULTRA CHAT), DigitalOcean, Baseten, Parasail, Nebius, Inco (FAST), Amazon, Kimi, and Inco". The page also notes "Kimi has launched a newer release, Kimi K3.1 Pro" — [AA Kimi K3 providers](https://artificialanalysis.ai/models/kimi-k3/providers)
- In the search snippet, the AA K3.1 Pro provider page showed only 2 providers — [AA K3.1 Pro providers](https://artificialanalysis.ai/models/kimi-k3-1-pro/providers). Novita's public model API lists `moonshotai/kimi-k3.1-pro` at $2.00 in / $10.00 out and `moonshotai/kimi-k3.1-pro-highspeed` at $4.00 / $20.00 per 1M tokens, both tagged function-calling — [Novita /openai/v1/models](https://api.novita.ai/openai/v1/models)
- Kimi models on hyperscalers today:
  - Bedrock: Kimi K3 (Global, US and India cross-region profiles only), Kimi K2.5 (in-region), Kimi K2 Thinking (pricing listed for US, Mumbai, São Paulo, Tokyo and Sydney only) — [Bedrock regional availability](https://docs.aws.amazon.com/bedrock/latest/userguide/models-region-compatibility.html), [Bedrock pricing](https://aws.amazon.com/bedrock/pricing/)
  - Azure (sold by Azure): Kimi-K2.7-Code (preview), Kimi-K2.6 (preview), Kimi-K2.5 (preview) — [Azure models sold directly](https://learn.microsoft.com/en-us/azure/ai-foundry/foundry-models/concepts/models-sold-directly-by-azure)
  - Azure via Fireworks on Foundry: Kimi K2, K2.5, K2.6 — [Fireworks on Foundry](https://learn.microsoft.com/en-us/azure/foundry/how-to/fireworks/enable-fireworks-models)
  - Vertex: Kimi K2 Thinking only — [Vertex MaaS overview](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/maas/overview)
  - Cloudflare Workers AI: Kimi K3, K2.6, K2.7-Code — [Cloudflare Kimi K3](https://developers.cloudflare.com/ai/models/moonshotai/kimi-k3/), [Workers AI model index](https://developers.cloudflare.com/workers-ai/llms.txt)

### Inferences
- If the user means "Kimi K3.1", they almost certainly mean K3.1 Pro. Until weights ship (promised by Nov 4), any third-party host other than Moonshot is probably proxying Moonshot's own API, which is China-based, rather than self-hosting. That matters for privacy. Novita's listing should be treated as possibly a pass-through until confirmed.
- After the weights release, expect the K3 host set (Fireworks, Together, DeepInfra, Baseten, Bedrock, Cloudflare and others) to add K3.1 Pro within days to weeks. That is a pattern-based expectation, not a confirmed fact.

### Gaps
- I could not confirm whether Novita's K3.1 Pro is self-hosted or proxied. I found no Bedrock, Azure or Vertex announcement for K3.1 Pro.
- AA reports two different Intelligence Index figures for K3.1 Pro (55 and 46). I did not resolve this.

## Q1: Which hyperscalers serve Kimi, DeepSeek, GLM, Qwen or gpt-oss as serverless models in EU regions, and through which (OpenAI-compatible) API?

### Takeaway
**AWS Bedrock is the only hyperscaler that clearly pins a broad set of these models to EU regions with a documented OpenAI-compatible Chat Completions endpoint, tool calling and streaming.** It serves the following in-region in EU regions: gpt-oss-120b/20b (Frankfurt, Stockholm, Milan, Ireland, London), several Qwen3 models (Frankfurt and others), GLM 4.7 Flash (Frankfurt and others), MiniMax M2.1/M2.5 (Frankfurt and others), and DeepSeek V3.2, Kimi K2.5, GLM 5 and GLM 4.7 (Stockholm and London only). The newest flagships, **Kimi K3 and GLM 5.3, are reachable from EU regions only through Global cross-region inference (no EU pinning)**, and Bedrock has no DeepSeek V4.

**Azure's EU Data Zone covers only DeepSeek-V4-Flash and Mistral-Large-3** among the non-OpenAI "sold by Azure" models. All Kimi models there are Global-only, and Fireworks-on-Foundry is explicitly excluded from the EU Data Boundary.

**Vertex AI lists EU endpoints for open models but makes no EU ML-processing commitment for any of them** (DeepSeek, Qwen, Kimi, GLM, gpt-oss, MiniMax). Only partner Mistral models have EU commitments.

Cloudflare Workers AI has a rich catalog and OpenAI compatibility, but I found no documented EU pinning. OCI is unclear.

### Cited Findings

#### AWS Bedrock (Amazon Web Services, US; regional docs fetched 2026-10-30)
- **EU in-region availability**, per model. Columns on the source page are In-Region bedrock-mantle / In-Region bedrock-runtime / Geo / Global. "Y" means available; "Global only" means no In-Region or Geo option from that EU region. Source: [Bedrock regional availability by model](https://docs.aws.amazon.com/bedrock/latest/userguide/models-region-compatibility.html)
  - gpt-oss-120b and gpt-oss-20b: in-region (mantle and runtime) in eu-central-1 Frankfurt, eu-north-1 Stockholm, eu-south-1 Milan, eu-west-1 Ireland, eu-west-2 London. GPT OSS Safeguard 120B/20B: Milan, Ireland, London.
  - Qwen3 235B A22B 2507: Frankfurt, Stockholm, Milan, London. Qwen3 32B and Qwen3-Coder-30B-A3B: Frankfurt, Stockholm, Milan, Ireland, London. Qwen3 Coder 480B A35B: Stockholm, London. Qwen3 VL 235B A22B and Qwen3 Next 80B A3B: Milan, Ireland, London. Qwen3 Coder Next: London only.
  - DeepSeek V3.2 and DeepSeek-V3.1: in-region Stockholm and London (no Geo/Global). DeepSeek-R1: US only. **No DeepSeek V4 listed.**
  - Kimi K2.5: in-region Stockholm and London. **Kimi K3: Global only from all eight EU/European regions** (Frankfurt, Zurich, Stockholm, Milan, Spain, Ireland, London, Paris).
  - GLM 4.7 Flash: Frankfurt, Stockholm, Milan, Ireland, London. GLM 4.7 and GLM 5: Stockholm and London. **GLM 5.3: Global only from EU regions.**
  - MiniMax M2.1 and M2.5: Frankfurt, Stockholm, Milan, Ireland, London. MiniMax M2: Milan, Ireland, London.
  - Mistral open models: Devstral 2 123B in Frankfurt, Stockholm, Milan, Ireland, London; Magistral Small 2509, Ministral 3 (3B/8B/14B) and Voxtral in Milan, Ireland, London; Pixtral Large via EU Geo cross-region; **Mistral Large 3 has no EU rows**.
  - Gemma 4 (31B, 26B-A4B, E2B): Frankfurt, mantle only. NVIDIA Nemotron 3 Super 120B: Frankfurt, Stockholm, Milan, Ireland, London.
- The Kimi K3 card states: "available through US and India Geo, and Global cross-Region inference". Model ID `moonshotai.kimi-k3`, profiles `us.moonshotai.kimi-k3` and `global.moonshotai.kimi-k3`. Supported endpoint: bedrock-runtime only, not bedrock-mantle. APIs: Chat Completions and Responses. Image input is supported. Response streaming and client-side tool calling are supported. Converse "has known limitations with this model". Prices per 1M tokens: Global CRIS $3.00 in / $15.00 out / $0.30 cache read / $3.75 cache write; US CRIS $3.30 / $16.50. Priority tier costs 1.75x and Flex 0.5x. "The burndown rate ... is 10x for output tokens" against quotas. — [Bedrock Kimi K3 model card](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-moonshot-ai-kimi-k3.html)
- Bedrock Standard-tier prices per 1M input/output tokens, from [Bedrock pricing](https://aws.amazon.com/bedrock/pricing/):
  - DeepSeek v3.2: US $0.62/$1.85; "Europe (Stockholm)" group $0.74/$2.22.
  - Kimi K2.5: US $0.60/$3.00; Stockholm $0.72/$3.60. Kimi K2 Thinking: US $0.60/$2.50.
  - GLM 5: US $1.00/$3.20; Stockholm $1.20/$3.84; London $1.55/$4.96.
  - GLM 5.3: Global CRIS $1.68/$5.28; US CRIS $1.848/$5.808.
  - MiniMax M2/M2.1/M2.5: $0.30/$1.20. The page rendered this table without a region label; it is probably the US rate **[unverified region]**.
  - gpt-oss-120b: Sydney $0.1545/$0.618. The EU and US cells were rendered by JavaScript and did not come through **[gap]**.
- **OpenAI-compatible API.** bedrock-runtime "InvokeModel / Converse / Chat Completions / Responses API / Messages API ... The OpenAI-compatible APIs are called on the /openai/v1 paths of this endpoint". bedrock-mantle also offers Chat Completions. Client-side tool use is supported on both endpoints. Per-token prices are identical on both. — [Bedrock inference endpoints](https://docs.aws.amazon.com/bedrock/latest/userguide/endpoints.html)
  - Base URLs: `OPENAI_BASE_URL="https://bedrock-runtime.<region>.amazonaws.com/openai/v1"` or `https://bedrock-mantle.<region>.api.aws/v1`, with `OPENAI_API_KEY="<your Bedrock API key>"`.
  - "bedrock-runtime doesn't implement the OpenAI-compatible GET /models operation".
  - "GPT OSS models support Chat Completions, Converse, and Invoke on bedrock-runtime, but they don't support the Responses API there." — [Bedrock Responses API / mantle doc](https://docs.aws.amazon.com/bedrock/latest/userguide/bedrock-mantle.html)
- Model cards list "Client-side tool calling" and "Response streaming" as supported, with Chat Completions among supported APIs, for DeepSeek V3.2, Kimi K2.5, GLM 5, GLM 5.3, MiniMax M2.5 and Qwen3 235B 2507. gpt-oss-120b additionally supports server-side tool calling. Kimi K2.5 accepts image input; DeepSeek V3.2, GLM 5/5.3, MiniMax M2.5 and Qwen3 235B do not. — [DeepSeek V3.2 card](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-deepseek-deepseek-v3-2.html), [Kimi K2.5 card](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-moonshot-ai-kimi-k2-5.html), [GLM 5 card](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-zai-glm-5.html), [GLM 5.3 card](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-zai-glm-5-3.html), [gpt-oss-120b card](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-openai-gpt-oss-120b.html), [MiniMax M2.5 card](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-minimax-minimax-m2-5.html), [Qwen3 235B card](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-qwen-qwen3-235b-a22b-2507.html)
- An older community test, from when the endpoint first launched, reported that `response_format` with a JSON schema was unsupported and function calling was incomplete, and that non-gpt-oss models were rejected. The current model cards above supersede this, but it is a reason to test tool calling end to end. — [dev.to AWS Builders test](https://dev.to/aws-builders/aws-launches-openai-compatible-api-for-bedrock-and-i-did-some-tests-49cd)
- **Privacy.**
  - Bedrock runs each provider's model in "Model Deployment Accounts ... owned and operated by the Amazon Bedrock service team. Model providers don't have any access to those accounts ... they don't have access to Amazon Bedrock logs or to customer prompts and completions." — [Bedrock data protection](https://docs.aws.amazon.com/bedrock/latest/userguide/data-protection.html)
  - Account-level `data_retention_mode`: `none` = "Zero data retention. No request or response data is written to durable storage by AWS or shared with the model provider ... Chat Completions and Messages requests are never retained." `default` = "the data retention policy of the model applies ... AWS may retain the data for safety and abuse-prevention purposes. The model provider does not receive it." So guaranteed ZDR is **opt-in** (set mode `none`).
  - Retention for human review (`aws_review`) currently applies only to certain Claude models, for up to 30 days. "If cross-region inference is enabled ... retained inputs and outputs are stored in destination Regions." — [Bedrock data retention](https://docs.aws.amazon.com/bedrock/latest/userguide/data-retention.html)
  - Responses API: `store` defaults to true, with 30-day retention. "a request that uses a global inference profile can store data in any commercial Region that profile routes to. If you have data residency requirements, use a geographic inference profile rather than a global one." — [Bedrock Responses API doc](https://docs.aws.amazon.com/bedrock/latest/userguide/bedrock-mantle.html)
- **Speed.** Artificial Analysis measured "Amazon" at 313.2 output tokens/s for Kimi K3 (Max), third-fastest of 14 providers, with 7.64 s time to first answer token (TTFAT). The region was not stated. — [AA Kimi K3 providers](https://artificialanalysis.ai/models/kimi-k3/providers)

#### Microsoft Azure AI Foundry (Microsoft, US; models page updated 2026-10-29, region page updated 2026-09-04)
- **Open models "sold by Azure"**, all chat-completion with "Tool calling: Yes": DeepSeek-V4-Pro, DeepSeek-V4-Flash, DeepSeek-V4-Flash-0731 (preview), DeepSeek-V3.2, DeepSeek-V3.2-Speciale (1M context for V4, 128K for V3.2); Kimi-K2.7-Code, Kimi-K2.6 and Kimi-K2.5 (all preview, text+image input, 262,144 context); Mistral-Large-3, mistral-medium-3-5; Llama-4-Maverick, Llama-3.3-70B; gpt-oss-120b and gpt-oss-20b (preview, text only); Qwen3-32B, Qwen3.6-35B-A3B, Qwen3.8-27B (these appear in the training tables; I could not confirm their serverless inference availability). The page says "gpt-oss-120b requires a Foundry project to deploy". Its CLI example uses `--sku-name "GlobalStandard"`. — [Azure models sold directly by Azure](https://learn.microsoft.com/en-us/azure/ai-foundry/foundry-models/concepts/models-sold-directly-by-azure)
- **Data Zone Standard (EU)**, for "other Foundry Models sold by Azure", in the regions francecentral, germanywestcentral, italynorth, polandcentral, spaincentral, swedencentral and westeurope: **only DeepSeek-V4-Flash and Mistral-Large-3**. DeepSeek-V4-Pro is in the US data zone only. Kimi-K2.5/K2.6/K2.7-Code, DeepSeek-V3.2/V3.2-Speciale and DeepSeek-V4-Flash-0731 appear only under Global Standard (and Global Provisioned). DeepSeek-V3.2 also has Data Zone Provisioned. gpt-oss did not appear in any Data Zone table I parsed. — [Azure region availability for models sold by Azure](https://learn.microsoft.com/en-us/azure/foundry/foundry-models/concepts/models-sold-directly-by-azure-region-availability)
- "DataZone types: Processed only within the Microsoft-specified data zone (US or EU) ... The EU Data Zone processes data within regions located in countries covered by the Azure EU Data Boundary." — [Azure deployment types](https://learn.microsoft.com/en-us/Azure/ai-foundry/openai/how-to/deployment-types)
- **Fireworks on Foundry** offers Kimi (K2, K2.5, K2.6), GLM (4.7, 4.8), gpt-oss-120b and Qwen (qwen3.5-9B/35B-A3B/112B-A10B/397B), with pay-per-token as Data Zone Standard or Global Standard. Key terms:
  - "data is shared between Microsoft and Fireworks AI, and different compliance and data handling rules will apply"
  - "Fireworks on Foundry is currently excluded from EU Data Boundary commitments"
  - Enterprise default quota is 10M TPM per region per subscription
  - OpenAI SDK base_url pattern `https://YOUR_RESOURCE.services.ai.azure.com/providers/fireworks/v1`
  - Page updated 2026-10-20 — [Enable Fireworks models in Foundry](https://learn.microsoft.com/en-us/azure/foundry/how-to/fireworks/enable-fireworks-models)
- **Price** (DeepSeek-V4-Flash): Data Zone Standard $0.21 in / $0.56 out / $0.031 cached per 1M; Global $0.19 / $0.51 **[third-party, derived from the Azure Retail Prices API]** — [azurespeed](https://www.azurespeed.com/AzureAiModelPricing/Models/deepseek-deepseek-v-4-flash)
- **Privacy** (models sold by Azure):
  - Prompts and completions "are NOT used to train any generative AI foundation models without your permission". "The models are stateless".
  - Abuse monitoring may select samples of prompts and completions for human review, stored in a per-geography data store. Approved customers can get "modified abuse monitoring", but "managed customers may apply". In practice this is an application process, likely out of reach for a hobbyist **[inference]**.
  - Responses API, Assistants threads and Stored completions persist data.
  - For Global deployments, "prompts and responses may be processed in any geography where the relevant model sold by Azure is deployed". — [Azure Foundry data privacy](https://learn.microsoft.com/en-us/azure/ai-foundry/responsible-ai/openai/data-privacy)

#### Google Cloud Vertex AI Model Garden MaaS (Google, US; locations page updated 2026-10-29, data residency page updated 2026-10-28)
- **Managed open models**: DeepSeek-V4.1-Flash (preview), DeepSeek-V3.2, V3.1, R1-0528, DeepSeek-OCR; Qwen3 Next 80B Instruct/Thinking, Qwen3 Coder, Qwen3 235B; **Kimi K2 Thinking (the only Kimi)**; GLM 5.2 (preview), GLM 5, GLM 4.7; gpt-oss-120b/20b; MiniMax M2; Llama 4 Maverick/Scout and Llama 3.3; Gemma 4 26B A4B. Partner models include Mistral Medium 3, Mistral Small 3.1 and Codestral 2. — [Vertex MaaS overview](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/maas/overview), [Vertex locations](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/learn/locations)
- The locations page lists global, `us` and `eu` multi-region endpoints plus europe-west1/2/3/4/6/8/9, europe-north1, europe-central2 and europe-southwest1 for these models. It also warns that endpoints don't guarantee data residency or in-region ML processing. — [Vertex locations](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/learn/locations)
- **ML processing commitments (data residency page), open models table**:
  - Has a US multi-region commitment: DeepSeek-OCR, R1-0528, V3.1, gpt-oss 120B/20B, Kimi K2 Thinking, MiniMax M2, Qwen3 (all four), Llama, Gemma 4.
  - Has no commitment in any listed column: DeepSeek-V3.2, DeepSeek-V4.1-Flash, GLM 5, GLM 5.2.
  - GLM 4.7: Singapore only.
  - **None of the DeepSeek/Qwen/Kimi/GLM/gpt-oss/MiniMax models has an "EU multi-region" commitment.** Only the embeddings do.
  - In the partner table, Mistral Medium 3, Mistral Small 3.1, Mistral OCR and Codestral 2 have EU multi-region and Netherlands (europe-west4) commitments.
  - "The European Union multi-region (eu) endpoint strictly covers data residency within EU member states ... the United Kingdom and Switzerland, are excluded." — [Vertex data residency](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/learn/data-residency)
- **OpenAI-compatible API**: `POST https://LOCATION-aiplatform.googleapis.com/v1/projects/PROJECT_ID/locations/LOCATION/endpoints/openapi/chat/completions` with `stream: true` (SSE) supported. The global endpoint "can process and serve your requests from any region". Authentication in the samples is `Authorization: Bearer $(gcloud auth print-access-token)`, an OAuth access token, not a static API key. — [Vertex: call open model APIs](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/maas/call-open-model-apis). The MaaS docs include a "Function calling" page — [Vertex MaaS overview nav](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/maas/overview)
- **Prices** **[third-party]**:
  - Kimi K2 Thinking $0.60 / $2.50 — [getmaxim](https://www.getmaxim.ai/bifrost/llm-cost-calculator/provider/vertex_ai/model/kimi-k2-thinking-maas)
  - GLM-5 $1.00 / $3.20 — [modelcompare.dev](https://modelcompare.dev/providers/google-vertex)
  - gpt-oss-120b $0.15 / $0.60 and gpt-oss-20b $0.075 / $0.30 at GA launch — [Google dev forum GA post](https://discuss.google.dev/t/now-ga-openais-gpt-oss-qwen3-models-on-vertex-ai-as-open-model-apis/253945)
  - The current official Vertex pricing page fetched today no longer contained these models; it covered Gemini and others. — [Vertex pricing](https://cloud.google.com/vertex-ai/generative-ai/pricing)

#### Cloudflare Workers AI (Cloudflare, US) — optional
- The catalog includes @cf/moonshotai/kimi-k3, kimi-k2.6, kimi-k2.7-code; @cf/deepseek-ai/deepseek-v4-pro-0813, deepseek-v4-flash-0731, deepseek-v4.1-flash-1017; @cf/zai-org/glm-5.3, glm-5.3-flash, glm-5.2, glm-4.7-flash; @cf/openai/gpt-oss-120b and gpt-oss-20b; @cf/qwen/qwen3.8-27b and qwen3-30b-a3b-fp8; @cf/nvidia/nemotron-3-120b-a12b; @cf/mistralai/mistral-small-3.1-24b-instruct — [Workers AI llms.txt index](https://developers.cloudflare.com/workers-ai/llms.txt)
- Kimi K3 on Workers AI: 1,048,576 context, $3.00 in / $15.00 out / $0.30 cached per 1M. Called via `https://api.cloudflare.com/client/v4/accounts/$ID/ai/v1/chat/completions`. — [Cloudflare Kimi K3](https://developers.cloudflare.com/ai/models/moonshotai/kimi-k3/)
- OpenAI-compatible Chat Completions with baseURL `.../accounts/{id}/ai/v1`. The Responses API is supported only for gpt-oss models. — [Workers AI OpenAI compatibility](https://developers.cloudflare.com/workers-ai/configuration/open-ai-compatibility/)
- **Privacy** (updated Oct 16, 2026): "Zero data retention: ... For standard inference requests that do not invoke a stateful feature, Cloudflare does not retain inputs or outputs". "No training". Operational metadata is retained. — [Workers AI data usage](https://developers.cloudflare.com/workers-ai/platform/data-usage/)

#### Oracle OCI Generative AI — optional
- OCI offers gpt-oss-120b/20b. Oracle's gpt-oss-20b page gives conflicting statements on dedicated versus on-demand availability. Oracle has a "New Regions for OpenAI gpt-oss" release note and private endpoints in the EU Sovereign Central (Frankfurt) region. I could not confirm the current Frankfurt on-demand model list. — [OCI models by region](https://docs.oracle.com/iaas/Content/generative-ai/model-endpoint-regions.htm), [OCI gpt-oss-20b](https://docs.oracle.com/iaas/Content/generative-ai/openai-gpt-oss-20b.htm), [OCI gpt-oss regions release note](https://docs.oracle.com/iaas/releasenotes/generative-ai/gpt-oss-regions.htm)

### Inferences
- **Best hyperscaler fit for the app (LangChain `ChatOpenAI` + `bind_tools`)**: Bedrock in **eu-central-1 Frankfurt** or **eu-north-1 Stockholm**, with base_url `https://bedrock-runtime.eu-north-1.amazonaws.com/openai/v1` and a Bedrock API key.
  - Stockholm has the widest EU in-region open-model set: DeepSeek V3.2, Kimi K2.5, GLM 5, GLM 4.7, Qwen3 235B/32B/Coder, gpt-oss and MiniMax M2.5.
  - Frankfurt has gpt-oss, Qwen3, GLM 4.7 Flash and MiniMax M2.5, but not DeepSeek, Kimi or GLM 5.
  - Set `data_retention_mode` to `none` for guaranteed ZDR.
  - Avoid `global.*` profiles (Kimi K3, GLM 5.3) if EU processing is the goal.
- London (eu-west-2) is UK, not EU, and Zurich is Switzerland. Vertex explicitly excludes both from "EU", and they would not satisfy a strict "EU-only" rule even though the UK and Switzerland have GDPR adequacy decisions. That adequacy point is general knowledge, not fetched.
- On Vertex, using an EU regional endpoint for open models does not come with an EU ML-processing commitment. For residency purposes, Vertex is not a reliable EU option for Kimi, DeepSeek, GLM, Qwen or gpt-oss today. Its OAuth tokens also need refreshing (gcloud access tokens are short-lived; the ~1 h lifetime is general knowledge, not checked today), which complicates a plain `ChatOpenAI(api_key=...)` setup.
- On Azure, the only EU-pinnable open models relevant here are DeepSeek-V4-Flash and Mistral-Large-3, via a Data Zone Standard deployment in an EU region. Kimi on Azure is Global-only.
- **CLOUD Act**: Amazon, Microsoft, Google, Cloudflare and Oracle are US companies. EU-region processing reduces transfer exposure but does not remove US legal access risk. This is a legal background fact, not taken from the fetched pages.

### Gaps
- Bedrock gpt-oss and MiniMax prices for EU regions did not render (JavaScript templating). I did not check DeepSeek V3.2 pricing for London.
- I did not confirm on the official page whether Azure's Foundry `/openai/v1` endpoint works with LangChain `ChatOpenAI` tool calling and streaming for the DeepSeek, Kimi and Mistral deployments. The models page only says "Tool calling: Yes". There is also no official Azure price for DeepSeek-V4-Flash.
- Official Vertex MaaS prices were not found on Google's pricing page today.
- I did not determine whether Cloudflare Workers AI can pin inference to EU locations (for example via the Data Localization Suite).
- OCI's Frankfurt on-demand catalog is unconfirmed.
- I did not verify current new-account credits ($200 AWS, $200 Azure, $300 GCP are commonly cited) or default Bedrock per-model quotas for new accounts.

## Q2: Which US specialists offer zero data retention by default, and do any have EU-region inference?

### Takeaway
**Default ZDR or no-retention** for serverless inference, per official docs:
- **Fireworks**: ZDR by default for open models, except the Responses API with store=True.
- **DeepInfra**: memory-only, no content logs.
- **Cerebras**: privacy policy says inputs and outputs are not retained.
- **Baseten**: ZDR for synchronous Model APIs.
- **Cloudflare Workers AI**.
- **Groq**: no retention by default, but it may keep reliability/abuse logs for up to 30 days unless you flip a self-serve ZDR toggle.

**Together AI is the exception.** By default it stores prompts and responses and "may use them for product improvements"; ZDR is an opt-in org setting.

**No US specialist offers self-serve, EU-pinned serverless inference.**
- Fireworks: "EU-only Serverless" is sales-only, and its data-residency enforcement is Enterprise-only (dedicated deployments can run in the EUROPE multi-region or EU_FRANKFURT_1).
- Together: EU only via dedicated or VPC deployments.
- Baseten: a region "compliance policy" is enabled via support.
- Groq: has a Helsinki data center but stores data in US GCP buckets and documents no EU residency.

### Cited Findings

#### Together AI (US)
- "By default, Together stores the prompts you send and the responses models return, and may use them for product improvements ... Organization admins can turn storage off ... which enables zero data retention (ZDR)."
- "Data sharing for training other models is opt-in and not enabled by default".
- "Allow passthrough models: On by default", meaning prompts are forwarded to third-party providers under their policies.
- Geo-specific inference "keeps inference processing in the United States" via `us-api.together.ai`; for GDPR it supports "private networking and virtual private cloud (VPC) deployments, including in EU regions" through dedicated endpoints or sales.
- "DeepSeek models are hosted in Together's secure North America data centers." — [Together privacy and security](https://docs.together.ai/docs/privacy-and-security)
- "ZDR is not enabled by default. To enable it ... Set Store prompts and model responses to No." With ZDR, content "is not persisted to non-volatile storage". — [Together ZDR](https://docs.together.ai/docs/zero-data-retention)
- SOC 2 Type 2 completed — [Together blog](https://together.ai/blog/soc-2-compliance)
- Rate limits are dynamic and best-effort: "Together may limit requests", returning 429/503, and "Model-specific limits" may apply. — [Together rate limits](https://docs.together.ai/docs/serverless/rate-limits). The "Limited tier" must add a payment method before changing privacy settings — [Together privacy and security](https://docs.together.ai/docs/privacy-and-security)

#### Fireworks AI (US)
- "Fireworks has Zero Data Retention by default ... does not log or store prompt or generation data for any open models, without explicit user opt-in." Prompt caching keeps data "in volatile memory for several minutes".
- Responses API: `store=True` is the default, with retention up to 30 days; opt out with `store=False`. — [Fireworks ZDR / data handling](https://docs.fireworks.ai/guides/security_compliance/data_handling)
- Certifications: SOC 2 Type II, HIPAA, ISO 27001 / 27701 / 42001; controls mapped to GDPR. — [Fireworks data security](https://docs.fireworks.ai/guides/security_compliance/data_security)
- US-only serverless is available at `https://us.api.fireworks.ai` (Kimi K3, DeepSeek V4.1 Flash, GLM 5.3, GLM 5.3 Flash, Muse Spark Open) at "1.5x the base model serverless prices". "For EU-only Serverless, contact sales." — [Fireworks US-only serverless](https://docs.fireworks.ai/serverless/us-only-serverless)
- "Data residency is available on Enterprise accounts." The default "None" region on `api.fireworks.ai` means "Any model | Any region". — [Fireworks data residency](https://docs.fireworks.ai/accounts/data-residency)
- Dedicated deployments: multi-regions include `EUROPE`; single regions include `EU_FRANKFURT_1` (H100), `EU_ICELAND_1` and `EU_ICELAND_2`. Iceland is EEA, not EU. — [Fireworks regions](https://docs.fireworks.ai/deployments/regions)
- Rate limits are adaptive, per account and per model, measured in TPM. Higher spending tiers raise the upper bounds. — [Fireworks serverless rate limits](https://docs.fireworks.ai/serverless/rate-limits)

#### DeepInfra (US)
- "Input data is not stored to disk during inference — it exists only in memory". Outputs are not stored. "We do not train on your data", except for Google and Anthropic models. "We do not log the content of your requests. We log only metadata". Bulk/batch requests may be stored briefly, encrypted. — [DeepInfra data privacy](https://deepinfra.com/docs/data)
- The site displays "SOC 2 Certified" and "ISO 27001 Certified" badges. — [DeepInfra security](https://deepinfra.com/security)
- I found no EU region documented **[gap]**.

#### Groq (US)
- "By default, Groq does not retain customer data for inference requests". It may log inputs and outputs for troubleshooting or abuse "for up to 30 days". "All customers may enable Zero Data Retention (ZDR) in Data Controls settings". "All customer data is retained in Google Cloud Platform (GCP) buckets located in the United States ... Customers can rely on standard contractual clauses (SCCs)". — [Groq: Your data](https://console.groq.com/docs/your-data)
- Groq announced a Helsinki, Finland data center with Equinix on 2025-07-06, accessible via private connections and Equinix Fabric. — [Groq news](https://groq.com/news/groq-launches-european-data-center-footprint-in-helsinki-finland)
- SOC 2 Type II, per a Groq community post. HIPAA BAA status is contradictory across sources. — [Groq community](https://community.groq.com/t/is-groq-soc-2-compliant/82)

#### Cerebras (US)
- "We do not retain inputs and outputs associated with our training, inference and chatbot Services. We delete logs associated with [them] when they are no longer necessary". — [Cerebras privacy policy, s.6](https://www.cerebras.ai/privacy-policy)
- New accounts get "$5 in free credits after adding a verified payment method", expiring after 30 days, with "No" permanently free tier.
- Free Trial limits: gpt-oss-120b 5 RPM, 30K uncached TPM, 1M tokens/day.
- Developer (pay-as-you-go) limits: gpt-oss-120b 1K RPM / 1M uncached TPM; qwen-3.8-27b 300 RPM / 150K TPM. — [Cerebras rate limits](https://inference-docs.cerebras.ai/support/rate-limits)
- I found no EU region documented **[gap]**.

#### Baseten (US)
- "Baseten maintains SOC 2 Type II certification and HIPAA compliance ... Baseten does not store model inputs, outputs, or weights by default. This zero data retention (ZDR) policy applies to synchronous inference." Async inputs are stored while queued. — [Baseten secure inference](https://docs.baseten.co/observability/security)
- "Model APIs use a shared endpoint, and the regions serving a model can change. If your workloads must stay in specific regions, contact support ... to enable a Model APIs compliance policy." — [Baseten Model APIs overview](https://docs.baseten.co/inference/model-apis/overview)

#### Novita AI (US-registered per its policy; corporate details not verified)
- The privacy policy (last updated May 13, 2026) allows transfers "to countries outside your country or region, including the United States" under SCCs or the DPF, and says "Personal Information will not be used for model training". It says nothing specific about API prompt retention. — [Novita privacy policy](https://novita.ai/legal/privacy-policy)
- A third-party review says ZDR is Novita's default for content and that region pinning is undocumented **[third-party]**. — [standardcompute: Novita](https://standardcompute.com/providers/novita)

#### SambaNova, Hyperbolic, Lambda
- **SambaNova**: since 2026-08-14 the free tier requires a card before API calls **[third-party]** — [usagepricing: SambaNova](https://www.usagepricing.com/blueprint/sambanova). Its official docs did not load for me **[gap]**.
- **Hyperbolic**: serverless inference API retired around 2026-09-24, then relaunched around 2026-10-15 for paying accounts only **[third-party snapshots]** — [usagepricing: retired](https://www.usagepricing.com/blueprint/activity/hyperbolic-2026-09-24-serverless-inference-api-retired), [usagepricing: relaunch](https://www.usagepricing.com/blueprint/activity/hyperbolic-2026-10-15-inference-api-relaunch)
- **Lambda**: the Inference API is marked sunset ("shutdown set for September 25th") in favor of self-hosting on GPU instances. The year conflicts across sources; a forum thread suggests 2025. — [Lambda docs](https://docs.lambda.ai/public-cloud/lambda-inference-api), [Lambda forum](https://deeptalk.lambda.ai/t/sunsetting-chat-sunsetting-inference/4744). Not a viable option.

#### Other prominent hosts in the 2026 AA provider lists
- Kimi K3: Databricks, Modal, Parasail, DigitalOcean, Makora, Inco, LithosAI, Nebius — [AA Kimi K3 providers](https://artificialanalysis.ai/models/kimi-k3/providers)
- gpt-oss-120b: CoreWeave — [AA gpt-oss-120b](https://artificialanalysis.ai/models/gpt-oss-120b/providers)
- DeepSeek V4 Pro 0813: Systalyze, GMI — [AA DeepSeek V4 Pro](https://artificialanalysis.ai/models/deepseek-v4-pro/providers)
- GLM-5.3: Multiverse Computing, Supernova — [AA GLM-5.3](https://artificialanalysis.ai/models/glm-5-3/providers)
- DeepSeek V4.1 Flash: Bitdeer AI, SiliconFlow — [AA DeepSeek V4.1 Flash](https://artificialanalysis.ai/models/deepseek-v4-1-flash/providers)
- Nebius and Multiverse Computing are European and fall outside this note's scope; I did not research them.

### Inferences
- For a hobbyist who wants strong privacy with no paperwork, the cleanest defaults are Fireworks, DeepInfra, Baseten, Cerebras and Cloudflare (no content retention by default). Groq gets there with one self-serve toggle. Together requires turning off "Store prompts and model responses", and possibly "Allow passthrough models", before use.
- No specialist meets "EU processing" without an enterprise contract. Fireworks' default serverless routing ("Any region") may process prompts anywhere, including outside both the US and the EU. All of these companies are US-incorporated, so the CLOUD Act applies regardless of data center location (legal background, not from the fetched pages).
- For a strict EU-residency fallback, Bedrock in Frankfurt or Stockholm with retention mode `none` beats every US specialist, at the cost of older model versions (Kimi K2.5 instead of K3, DeepSeek V3.2 instead of V4, GLM 5 instead of 5.3).

### Gaps
- DPAs: none of the specialist pages I fetched linked a self-serve DPA explicitly (Together's is via its enterprise team per a third-party source; others not checked).
- I could not verify Novita's own ZDR statement or Novita's corporate jurisdiction.
- I did not fetch official rate limits for new accounts at DeepInfra, Novita or Baseten. Groq's free-plan limits were not captured; only Developer plan limits were.
- I did not find EU region options for DeepInfra, Cerebras, Novita or SambaNova.

## Q3: How do prices and speeds compare for the same models across providers?

### Takeaway
For the flagship open models, the US specialists mostly converge on the same list prices:
- Kimi K3: about $3 / $15 at Together, Fireworks, Cloudflare and Novita, and on Bedrock via Global CRIS. DeepInfra is cheapest at $2.85 / $14.25.
- GLM-5.3: about $1.40 / $4.40 at Together, Fireworks and Novita. DeepInfra lists $0.90 / $4.00 before an active discount. Bedrock Global is $1.68 / $5.28.
- DeepSeek V4.1 Flash: about $0.30 / $1.20. DeepInfra is $0.20 / $0.60 before discount.
- gpt-oss-120b: $0.15 / $0.60 at Groq, Together and Fireworks. DeepInfra and Novita are far cheaper at about $0.04–0.05 / $0.17–0.25.

EU-pinned options cost more and use older versions. On Bedrock Stockholm: DeepSeek V3.2 $0.74 / $2.22, Kimi K2.5 $0.72 / $3.60, GLM 5 $1.20 / $3.84. Azure EU Data Zone DeepSeek-V4-Flash is about $0.21 / $0.56 (third-party figure). Fireworks charges +50% for US-only routing; Together charges +25% for its US geo endpoint.

Speed: Cerebras is the clear leader on gpt-oss-120b (~1,663 t/s measured), ahead of SambaNova (~708) and Groq (~471). On big MoE models, specialized "FAST" endpoints lead. Bedrock was third-fastest on Kimi K3 at 313 t/s.

### Cited Findings
Prices are USD per 1M tokens, input / output, standard tier, list price. Format: `model — provider: price (source)`.

- **Kimi K3**
  - Bedrock Global $3.00/$15.00; US $3.30/$16.50 — [Bedrock Kimi K3 card](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-moonshot-ai-kimi-k3.html)
  - Together $3.00/$15.00; US-only $3.75/$18.75 — [Together serverless models](https://docs.together.ai/docs/serverless-models)
  - Fireworks $3.00/$15.00 (cached $0.30); Fast $4.50/$22.50; US $4.50/$22.50 — [Fireworks pricing](https://docs.fireworks.ai/serverless/pricing)
  - DeepInfra $2.85/$14.25 (mxfp4) — [DeepInfra model API](https://api.deepinfra.com/models/list)
  - Cloudflare $3.00/$15.00 — [Cloudflare Kimi K3](https://developers.cloudflare.com/ai/models/moonshotai/kimi-k3/)
  - Novita $3.00/$15.00 — [Novita models API](https://api.novita.ai/openai/v1/models)
  - Baseten $3.00/$15.00 **[third-party, BenchLM snapshot 2026-10-20]** — [BenchLM Baseten](https://benchlm.ai/hosts/baseten)
- **Kimi K3.1 Pro**: Novita $2.00/$10.00; Highspeed $4.00/$20.00 — [Novita models API](https://api.novita.ai/openai/v1/models)
- **Kimi K2.6 / K2.5**
  - DeepInfra K2.6 $0.75/$3.50; K2.5 $0.45/$2.25 (K2.5 is marked deprecated) — [DeepInfra model API](https://api.deepinfra.com/models/list)
  - Novita K2.6 $0.80/$3.40 — [Novita models API](https://api.novita.ai/openai/v1/models)
  - Bedrock K2.5: US $0.60/$3.00, Stockholm $0.72/$3.60 — [Bedrock pricing](https://aws.amazon.com/bedrock/pricing/)
- **DeepSeek V4 Pro (0813)**
  - Together $1.32/$3.96 (NVFP4) — [Together](https://docs.together.ai/docs/serverless-models)
  - DeepInfra $1.30/$2.60 (fp8) — [DeepInfra](https://api.deepinfra.com/models/list)
  - Novita $1.32/$3.96 (V4 Pro non-0813 is $1.60/$3.20) — [Novita](https://api.novita.ai/openai/v1/models)
- **DeepSeek V4.1 Flash**
  - Together $0.30/$1.20 — [Together](https://docs.together.ai/docs/serverless-models)
  - Fireworks $0.30/$1.20; US $0.45/$1.80 — [Fireworks](https://docs.fireworks.ai/serverless/pricing)
  - Novita $0.30/$1.20 — [Novita](https://api.novita.ai/openai/v1/models)
  - DeepInfra list $0.20/$0.60 with a 30% discount flag; AA reports DeepInfra at $0.14/$0.42 — [DeepInfra](https://api.deepinfra.com/models/list), [AA DeepSeek V4.1 Flash](https://artificialanalysis.ai/models/deepseek-v4-1-flash/providers)
- **DeepSeek V4 Flash** (older): DeepInfra $0.09/$0.18 — [DeepInfra](https://api.deepinfra.com/models/list). Azure Data Zone $0.21/$0.56 **[third-party]** — [azurespeed](https://www.azurespeed.com/AzureAiModelPricing/Models/deepseek-deepseek-v-4-flash)
- **DeepSeek V3.2**: Bedrock US $0.62/$1.85, Stockholm $0.74/$2.22 — [Bedrock pricing](https://aws.amazon.com/bedrock/pricing/). DeepInfra $0.26/$0.38 — [DeepInfra](https://api.deepinfra.com/models/list)
- **GLM-5.3**
  - Together $1.40/$4.40 (FP4) — [Together](https://docs.together.ai/docs/serverless-models)
  - Fireworks $1.40/$4.40; Fast or US $2.10/$6.60 — [Fireworks](https://docs.fireworks.ai/serverless/pricing)
  - Novita $1.40/$4.40 — [Novita](https://api.novita.ai/openai/v1/models)
  - DeepInfra list $0.90/$4.00 with a 37.5% discount flag — [DeepInfra](https://api.deepinfra.com/models/list)
  - Bedrock Global $1.68/$5.28 — [Bedrock pricing](https://aws.amazon.com/bedrock/pricing/)
- **GLM-5.3 Flash**: Together, Fireworks, Novita and DeepInfra all $0.15/$0.50 — [Together](https://docs.together.ai/docs/serverless-models), [Fireworks](https://docs.fireworks.ai/serverless/pricing), [Novita](https://api.novita.ai/openai/v1/models), [DeepInfra](https://api.deepinfra.com/models/list)
- **GLM 5**: Bedrock US $1.00/$3.20, Stockholm $1.20/$3.84, London $1.55/$4.96 — [Bedrock pricing](https://aws.amazon.com/bedrock/pricing/). Novita $1.00/$3.20 — [Novita](https://api.novita.ai/openai/v1/models)
- **gpt-oss-120b**
  - Groq $0.15/$0.60 at ~500 t/s (Developer plan: 250K TPM, 1K RPM) — [Groq models](https://console.groq.com/docs/models)
  - Together $0.15/$0.60 — [Together](https://docs.together.ai/docs/serverless-models)
  - Fireworks $0.15/$0.60 — [Fireworks](https://docs.fireworks.ai/serverless/pricing)
  - DeepInfra $0.037/$0.17 — [DeepInfra](https://api.deepinfra.com/models/list)
  - Novita $0.05/$0.25 — [Novita](https://api.novita.ai/openai/v1/models)
  - Cerebras $0.35/$0.75 **[third-party]** — [morphllm](https://www.morphllm.com/cerebras-pricing)
  - Bedrock Sydney $0.1545/$0.618 (EU price not rendered) — [Bedrock pricing](https://aws.amazon.com/bedrock/pricing/)
  - Vertex $0.15/$0.60 at launch **[older]** — [Google forum](https://discuss.google.dev/t/now-ga-openais-gpt-oss-qwen3-models-on-vertex-ai-as-open-model-apis/253945)
- **Qwen 3.8**
  - Qwen3.8-2.4T-A95B: Together $2.00/$6.00 — [Together](https://docs.together.ai/docs/serverless-models)
  - Qwen 3.8 Max: Fireworks $2.00/$6.00 — [Fireworks](https://docs.fireworks.ai/serverless/pricing)
  - Qwen3.8-27B: Groq $0.80/$4.00 at 450 t/s — [Groq](https://console.groq.com/docs/models); DeepInfra $0.20/$2.50 — [DeepInfra](https://api.deepinfra.com/models/list); Cerebras $0.99/$1.49 **[third-party, single source]** — [morphllm](https://www.morphllm.com/cerebras-pricing)
- **MiniMax M3**: Fireworks $0.30/$1.20 — [Fireworks](https://docs.fireworks.ai/serverless/pricing). DeepInfra $0.28/$1.10 — [DeepInfra](https://api.deepinfra.com/models/list). Novita $0.30/$1.20 — [Novita](https://api.novita.ai/openai/v1/models)
- **MiniMax M2.5 (EU in-region)**: Bedrock $0.30/$1.20; region label unclear — [Bedrock pricing](https://aws.amazon.com/bedrock/pricing/)
- **Speed and blended price, Artificial Analysis** (blended price uses a 7:2:1 cache-hit/input/output ratio):
  - **gpt-oss-120b (high), 16 providers**: fastest are Cerebras 1,663.1 t/s, SambaNova 708.3 t/s, Groq 471.1 t/s; lowest latency Cerebras 1.59 s; cheapest blended CoreWeave $0.04, DeepInfra $0.05, Novita $0.07 — [AA gpt-oss-120b](https://artificialanalysis.ai/models/gpt-oss-120b/providers)
  - **Kimi K3 (Max), 14 providers**: fastest are Inco (FAST) 542.6, LithosAI 447.3, Amazon 313.2, Parasail 168.6 t/s; cheapest blended Makora $1.79, Databricks $2.31, Fireworks $2.31; prices vary up to 2.6x — [AA Kimi K3](https://artificialanalysis.ai/models/kimi-k3/providers)
  - **DeepSeek V4 Pro 0813 (Max), 10 providers**: fastest are Systalyze 231.3, Baseten 140.2, Nebius 134.9 t/s; DeepInfra $1.30/$2.60 among the cheapest — [AA DeepSeek V4 Pro](https://artificialanalysis.ai/models/deepseek-v4-pro/providers)
  - **DeepSeek V4.1 Flash (Max), 18 providers**: fastest are Baseten (FAST) 831.6, Together AI 379.6, CoreWeave 336.7 t/s; cheapest DeepInfra ($0.07 blended) — [AA DeepSeek V4.1 Flash](https://artificialanalysis.ai/models/deepseek-v4-1-flash/providers)
  - **GLM-5.3 (Max), 27 providers**: fastest are LithosAI 685.1, Supernova 556.9, Inco (FAST) 494.0 t/s — [AA GLM-5.3](https://artificialanalysis.ai/models/glm-5-3/providers)
  - **GLM-5.3-Flash, 24 providers**: fastest are Inco (FAST) 1,476.7, LithosAI 1,449.4 t/s — [AA GLM-5.3 Flash](https://artificialanalysis.ai/models/glm-5-3-flash/providers)
- Vendor-claimed speeds: Cerebras gpt-oss-120b "~3000" t/s, qwen-3.8-27b "~1850" t/s — [Cerebras model catalog](https://inference-docs.cerebras.ai/models/overview). Groq: gpt-oss-120b 500 t/s, gpt-oss-20b 1000 t/s, Qwen3.8-27B 450 t/s — [Groq models](https://console.groq.com/docs/models)

### Inferences
- The EU-residency premium on Bedrock is roughly 20% versus US in-region (Stockholm compared with US for DeepSeek V3.2, Kimi K2.5 and GLM 5), plus a version lag. London is about 55% more expensive than US for GLM 5.
- DeepInfra is consistently the cheapest US host. Its "discount" field appears to reflect an active discount: AA's DeepInfra V4.1 Flash price equals list × (1 − 0.3). On that basis, DeepInfra's current effective GLM-5.3 price would be about $0.56 / $2.50 (my calculation; AA did not confirm it).
- For a chat app, Kimi K3 at $15/M output is about 4–6x the output price of GLM-5.3 or DeepSeek V4 Pro. GLM-5.3 Flash or DeepSeek V4.1 Flash at about $0.15–0.30 in are the cost-efficient defaults.

### Gaps
- Official prices are missing for Cerebras, Baseten (official page), SambaNova, Vertex MaaS (current) and Azure.
- AA results are snapshots; the Kimi K3 page notes cache data "updated Oct 26, 2026". The AA "Amazon" region for Kimi K3 is not stated.
- DeepInfra's discount semantics are not documented. Several DeepInfra entries (Kimi-K2.5, Kimi-K2.7-Code, Qwen3.8-2.4T, gpt-oss-120b-Turbo) carry past "deprecated" timestamps.

## Q4: Does each provider support OpenAI-compatible tool/function calling with streaming (LangChain ChatOpenAI + custom base_url + bind_tools)?

### Takeaway
Yes, for all the viable options. Each exposes an OpenAI-style `/v1/chat/completions` endpoint with streaming, and documents tool calling for the relevant models:
- **Bedrock**: `bedrock-runtime.{region}.amazonaws.com/openai/v1`, with a Bedrock API key as bearer. Model cards confirm client-side tool calling and streaming for DeepSeek V3.2, Kimi K2.5/K3, GLM 5/5.3, MiniMax M2.5, Qwen3 and gpt-oss.
- **Together, Fireworks, DeepInfra, Groq, Cerebras, Baseten, Novita and Cloudflare Workers AI**: all document this.
- **Vertex**: works too, but authenticates with short-lived Google OAuth tokens.
- **Azure**: models list "Tool calling: Yes", but I did not verify the exact v1 endpoint details today.

Hyperbolic (uncertain status) and Lambda (sunset) are not recommended.

### Cited Findings
- **Bedrock**: Chat Completions on both bedrock-runtime and bedrock-mantle; "Client-side tool use" is supported on both. — [Bedrock endpoints](https://docs.aws.amazon.com/bedrock/latest/userguide/endpoints.html). The Kimi K3 card lists "Response streaming" and "Client-side tool calling", and says "For Kimi K3, we recommend using the Chat Completions API". — [Kimi K3 card](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-moonshot-ai-kimi-k3.html). Other model cards say the same (see Q1). Bedrock API keys are required for the OpenAI SDK. — [Bedrock Responses/mantle doc](https://docs.aws.amazon.com/bedrock/latest/userguide/bedrock-mantle.html)
- **Azure Foundry**: DeepSeek V3.2/V4 and Kimi K2.5/K2.6/K2.7-Code are listed with "Tool calling: Yes" and "Response formats: Text, JSON" (Text only for Kimi). — [Azure models sold directly](https://learn.microsoft.com/en-us/azure/ai-foundry/foundry-models/concepts/models-sold-directly-by-azure). The Fireworks-on-Foundry example uses the OpenAI SDK with `base_url="https://YOUR_RESOURCE.services.ai.azure.com/providers/fireworks/v1"`. — [Fireworks on Foundry](https://learn.microsoft.com/en-us/azure/foundry/how-to/fireworks/enable-fireworks-models)
- **Vertex**: OpenAI chat completions at `.../endpoints/openapi/chat/completions`, streaming via SSE, with a gcloud access token as bearer. — [Vertex open model APIs](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/maas/call-open-model-apis). A "Function calling" doc exists for MaaS. — [Vertex MaaS overview](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/maas/overview)
- **Together**: the serverless table marks "Function calling: Yes" and "Structured outputs: Yes" for every listed chat model (DeepSeek V4, Kimi K3, GLM-5.x, gpt-oss-120b, Qwen3.x, MiniMax M3.1 Flash). — [Together serverless models](https://docs.together.ai/docs/serverless-models). Docs cover single, parallel and multi-turn function calling and vision function calling. — [Together docs index](https://docs.together.ai/llms.txt)
- **Fireworks**: docs cover "Text Models ... with chat completions, streaming, tool use, and structured outputs" and "Tool Calling". The API is OpenAI-compatible at `https://api.fireworks.ai/inference/v1/chat/completions` (US: `us.api.fireworks.ai`). — [Fireworks docs index](https://docs.fireworks.ai/llms.txt), [Fireworks US-only serverless](https://docs.fireworks.ai/serverless/us-only-serverless)
- **DeepInfra**: the model list tags Kimi K3, DeepSeek V4 Pro / V4.1 Flash, GLM-5.3, gpt-oss-120b, MiniMax M3 and others with `openai` and `tools` (and `multimodal` where applicable). — [DeepInfra model API](https://api.deepinfra.com/models/list)
- **Groq**: OpenAI-compatible endpoints under `/openai/v1/chat/completions`. — [Groq: Your data (endpoint table)](https://console.groq.com/docs/your-data). Tool use was not re-verified today, but Groq's docs have long supported it **[unverified today]**.
- **Cerebras**: base_url `https://api.cerebras.ai/v1`. "openai 3.5.0 passed Cerebras compatibility tests for model listing, Chat Completions, Completions, and streaming". "Tool streaming: Use standard streaming with stream: true." External HTTPS image URLs are not supported; use base64. — [Cerebras OpenAI compatibility](https://inference-docs.cerebras.ai/resources/openai). Tool calling supports `tool_choice`, strict mode and parallel calls. — [Cerebras tool calling](https://inference-docs.cerebras.ai/capabilities/tool-use)
- **Baseten**: base_url `https://inference.baseten.co/v1`, with Chat Completions, Responses and Messages (beta). "The language models in this table support tool calling." — [Baseten Model APIs](https://docs.baseten.co/inference/model-apis/overview)
- **Novita**: OpenAI-compatible base URL `https://api.novita.ai/openai`. — [Novita docs index](https://novita.ai/docs/llms.txt). Models are tagged `function-calling`, `structured-outputs` and `reasoning`. — [Novita models API](https://api.novita.ai/openai/v1/models)
- **Cloudflare**: OpenAI-compatible `/ai/v1/chat/completions`. — [Workers AI OpenAI compatibility](https://developers.cloudflare.com/workers-ai/configuration/open-ai-compatibility/). The GLM-5.3 entry mentions "function" calling. — [Workers AI index](https://developers.cloudflare.com/workers-ai/llms.txt)

### Inferences
- **LangChain notes.**
  - Bedrock's bedrock-runtime lacks `GET /models`. That is harmless for `ChatOpenAI`, but it breaks any model-listing UI.
  - Vertex needs a token-refresh wrapper.
  - Reasoning models (Kimi, DeepSeek V4, GLM-5.x) return reasoning content in non-standard fields on many hosts. `ChatOpenAI` may drop it, so the app's "reasoning steps" UI may need provider-specific handling.
  - Test parallel tool calls and streamed tool-call deltas per provider. The early Bedrock community test is a reminder that "OpenAI-compatible" can be partial.
- Image input (relevant to the app's vision feature) is available for Kimi K2.5/K3 on Bedrock, Kimi on Azure, Kimi K3 on Cerebras' enabled endpoints, and models tagged multimodal on DeepInfra. It is not available for DeepSeek V3.2, GLM 5/5.3 or Qwen3 235B on Bedrock.

### Gaps
- I did not test any endpoint live.
- Groq tool-calling docs and Azure's Foundry OpenAI v1 endpoint path were not re-verified today.
- Vertex function-calling support per open model was not checked model by model.
- Whether Fireworks, Together and others return reasoning in `reasoning_content` versus `<think>` tags was not checked.
