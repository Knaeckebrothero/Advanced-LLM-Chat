# Vendor first-party APIs (Moonshot, DeepSeek, Z.ai, Alibaba/Qwen, MiniMax, Mistral) and LLM aggregators/routers: privacy and usability for an EU (Germany) hobbyist

Research date: 2026-10-30. All pages were fetched on that date unless noted. Page "last updated" dates are given where the page shows one. "Unverified" means the claim comes only from a third-party or secondary source, or could not be checked against the vendor's own page.

## Q1: Is it reasonable for a privacy-minded EU user to send chats directly to Moonshot, DeepSeek or Z.ai (and how do Alibaba, MiniMax and Mistral compare)? What are the concrete risks under their own terms and according to regulators?

### Takeaway
DeepSeek is the clearest "no" for anything personal. Its own policy says data is collected, processed and stored in the PRC and used for training, with opt-out only by email. Its API terms are under PRC law with no DPA. EU regulators have acted against it: an Italian block since Jan 2025, and the Berlin DPA's DSA notice to Apple and Google, which they refused as of June 2026. Moonshot (Kimi international) is a Singapore entity storing data in Singapore. Its July 2026 API terms allow content to be used to "improve the Services," and an opt-out exists only through an enterprise agreement, so it is roughly as risky for training and slightly less for jurisdiction. Z.ai (Singapore entity) has the best paper position of the three. Its API DPA says it does not store API content, but it names no GDPR representative and no transfer mechanism. Alibaba Model Studio offers a Frankfurt region with an "EU" deployment scope, and Mistral is an EU vendor, so these are the realistic options for EU-only processing. MiniMax's API privacy terms could not be verified.

### Cited Findings

**DeepSeek (Hangzhou DeepSeek Artificial Intelligence Co., Ltd., PRC)**
- Controller is "Hangzhou DeepSeek Artificial Intelligence Co., Ltd." with "its registered address in China". Policy "Last Update: Feb 10, 2026" — [DeepSeek Privacy Policy](https://cdn.deepseek.com/policies/en-US/deepseek-privacy-policy.html)
- Location: "we directly collect, process and store your Personal Data in People's Republic of China" — [DeepSeek Privacy Policy](https://cdn.deepseek.com/policies/en-US/deepseek-privacy-policy.html)
- Collected: "text input, voice input, prompt, uploaded files, photos, feedback, chat history". Retention: "for as long as you have an account", with no fixed period — [DeepSeek Privacy Policy](https://cdn.deepseek.com/policies/en-US/deepseek-privacy-policy.html)
- Training is a stated purpose. Users may "opt-out of using your Personal Data for training our models", but the only described route is an email to privacy@deepseek.com. No settings toggle is described. Legal basis for training is legitimate interest, or consent in some cases — [DeepSeek Privacy Policy](https://cdn.deepseek.com/policies/en-US/deepseek-privacy-policy.html)
- EU/UK representative: the Feb 2026 policy names Prighter Group "with its local partners as our privacy representative". Transfer safeguards are mentioned only generically ("Where required, we will use appropriate safeguards"), and no SCCs are named — [DeepSeek Privacy Policy](https://cdn.deepseek.com/policies/en-US/deepseek-privacy-policy.html)
- API scope: the privacy policy says downstream developer apps "are not covered by this privacy policy" (the developer is controller). It still covers payment data for open-platform paid services — [DeepSeek Privacy Policy](https://cdn.deepseek.com/policies/en-US/deepseek-privacy-policy.html)
- The Open Platform ToS (release Apr 22, 2026; effective Apr 29, 2026) is governed by "the laws of the People's Republic of China in the mainland", with disputes in the court at DeepSeek's registered office. It has no DPA, does not address storage or retention of API inputs and outputs, and has no training opt-out — [DeepSeek Open Platform ToS](https://cdn.deepseek.com/policies/en-US/deepseek-open-platform-terms-of-service.html)

**Regulatory actions against DeepSeek**
- Italy: the Garante requested information on Jan 28, 2025 and ordered an urgent limitation (block) for Italian users on Jan 30, 2025 — [Dataconomy, 2025-01-31](https://dataconomy.com/2025/01/31/the-first-stone-italy-blocks-deepseek-over-data-privacy-concerns/); [ThePrint](https://theprint.in/tech/italys-regulator-blocks-chinese-ai-app-deepseek-on-data-protection/2471191). A secondary source claims the ban was still active as of March 2026 (unverified) — [Waimakers](https://www.waimakers.com/en/resources/ai-data-security/deepseek)
- Germany (Berlin DPA, Meike Kamp): on May 6, 2025 the DPA asked DeepSeek to remove the app voluntarily or stop the transfers, and got no response — [the-decoder](https://the-decoder.com/?p=24877). On June 27, 2025 it reported the app to Apple and Google as illegal content under the Digital Services Act. The grounds were unlawful transfer of German users' data to China and failure to show EU-equivalent protection, given Chinese authorities' extensive access rights — [TechCrunch, 2025-06-27](https://techcrunch.com/2025/06/27/germany-tells-apple-google-to-remove-deepseek-from-the-countrys-app-stores); [macerkopf, 2025-06-27](https://www.macerkopf.de/2025/06/27/berliner-datenschutzbehoerde-ki-app-deepseek/); [GBHackers, 2025-06-30](https://gbhackers.com/germany-urges-apple-and-google-to-ban-chinese-ai-app/)
- Germany follow-up (June 23, 2026): Apple and Google refused to remove the app. The Berlin DPA coordinated with the DPAs of Baden-Württemberg, Rheinland-Pfalz and Bremen and informed the Bundesnetzagentur's Digital Services Coordinator. It plans to use the DSA complaint system and, failing that, an Art. 21 DSA out-of-court dispute settlement body. As of the article the app had not been removed — [iphone-ticker.de, 2026-06-23](https://www.iphone-ticker.de/apple-und-google-verweigern-deepseek-sperre-280220/)
- Other DPAs: in early 2025 several national DPAs opened proceedings because DeepSeek had no EU representative — [heise](https://heise.de/-10289557) (title/snippet only, not fetched). Ireland's DPC sought details on processing — [GBHackers](https://gbhackers.com/germany-urges-apple-and-google-to-ban-chinese-ai-app/). A June 2026 compliance guide claims "at least 11" EU DPAs are investigating and that Greece ordered an EU representative (unverified, secondary) — [Waimakers](https://www.waimakers.com/en/resources/ai-data-security/deepseek)
- No source found for an EU-wide ban or an EDPB binding decision on DeepSeek as of 2026-10-30. An EU-wide ban would need consensus among regulators — [NBC/CNBC](https://www.nbcchicago.com/news/business/money-report/germany-tells-apple-google-to-block-deepseek-as-the-chinese-ai-app-faces-rising-pressure-in-europe/3777637/)

**Moonshot AI / Kimi (international: Moonshot AI PTE. LTD., Singapore)**
- platform.moonshot.ai now 301-redirects to platform.kimi.ai — observed when fetching [platform.moonshot.ai/docs/pricing/chat](https://platform.kimi.ai/docs/pricing/chat)
- API terms (Kimi OpenPlatform, last updated July 30, 2026): the contracting entity is Moonshot AI PTE. LTD. The terms are governed by Singapore law, with SIAC arbitration in Singapore and a one-year limit on bringing claims — [Kimi Model Use Agreement](https://platform.kimi.ai/docs/agreement/modeluse)
- Training: "We may use Content to provide, maintain, develop, support, and improve the Services." To restrict this, customers "may contact Moonshot AI to discuss available enterprise arrangements or separate written agreements". There is no self-service opt-out. The terms contain no GDPR or EU provisions and no data location clause — [Kimi Model Use Agreement](https://platform.kimi.ai/docs/agreement/modeluse)
- Privacy policy (last updated Apr 30, 2025): "We store the information we collect in secure servers located in Singapore". Data may be stored outside the user's country, and China is not mentioned. User content (prompts, files) is kept "while your account is active". Training ("training and refining our underlying technology, such as machine learning models") is a stated purpose, with no training opt-out described. Sec. 10 covers the EEA, CH and UK (legal bases, rights) but names no EU representative or DPO. Contact is api-service@moonshot.ai — [Kimi OpenPlatform Privacy Policy](https://platform.kimi.ai/docs/agreement/userprivacy)
- Third-party trackers say Moonshot offers no ZDR and has no public SOC 2 or ISO 27001 claim. A Kimi help page saying API data is not used for training appears to refer to the China platform (api.moonshot.cn), not the Singapore one (unverified) — [StandardCompute, verified 2026-09-02](https://standardcompute.com/providers/moonshotai); [DevelopersDigest](https://www.developersdigest.tech/models/data-retention/moonshot)

**Z.ai / Zhipu (international: JINGSHENG HENGXING TECHNOLOGY PTE. LTD, Singapore)**
- Controller is "JINGSHENG HENGXING TECHNOLOGY PTE.LTD" and affiliates, 10 Anson Road, #26-03 International Plaza, Singapore. Policy last updated Sep 29, 2025. "We generally provide the Services from Singapore". Data "may be transferred and processed outside the jurisdiction in which you reside", with no named transfer mechanism — [Z.ai Privacy Policy](https://docs.z.ai/legal-agreement/privacy-policy)
- The API DPA states: "The Company do not store any of the content the Customer or its End Users provide or generate while using our Services" (DPA §4(b)). Processing is limited to "providing and supporting API Services" (DPA §1(a)), which suggests no training on API content, though the DPA does not say so explicitly. Other API data is deleted after termination — [Z.ai Privacy Policy / DPA](https://docs.z.ai/legal-agreement/privacy-policy)
- The consumer policy names training as a purpose, with no opt-out named. It has no GDPR section and no EU representative or DPO. The only contact is user_feedback@z.ai — [Z.ai Privacy Policy](https://docs.z.ai/legal-agreement/privacy-policy)

**Alibaba Cloud Model Studio (Qwen)**
- Regions: China (Beijing) cn-beijing, Singapore ap-southeast-1 (dashscope-intl.aliyuncs.com), Germany (Frankfurt) eu-central-1 with deployment scopes "Global, EU", plus Tokyo, Hong Kong and US (Virginia). "Regions determine the access point and data storage location". Inference runs in the selected deployment scope and results return to the region for storage. The "Global" scope is for "a larger inference resource pool" when there are no compliance requirements. Each region has separate keys, endpoints and model lists. Page last updated Oct 13, 2026 — [Model Studio Regions](https://www.alibabacloud.com/help/en/model-studio/regions)
- Frankfurt uses only workspace-dedicated endpoints (`{WorkspaceId}.eu-central-1.maas.aliyuncs.com`), with no DashScope domain. Batch and fine-tuning are only in Singapore and Beijing. The DashScope domain gets no new features after Sep 30, 2026 — [Model Studio Regions](https://www.alibabacloud.com/help/en/model-studio/regions)
- No statement on use of customer data for training was found on the pricing or models pages — [Model Studio pricing](https://help.aliyun.com/en/model-studio/model-pricing)

**MiniMax**
- The app and web privacy policy names Nanonoble Pte. Ltd. (Singapore) — [MiniMax App/Web Privacy Policy](https://www.minimax.io/audio/doc/privacy-policy.html)
- Unverified (third-party): the API privacy policy is dated Mar 30, 2026, names Nanonoble Pte. Ltd. at 152 Beach Road, Singapore, and stores data in the US. Transfers to the Shanghai parent are permitted. No ZDR, DPA or trust page was found — [StandardCompute, verified 2026-09-02](https://standardcompute.com/providers/minimax). The official API privacy page (platform.minimax.io/protocol/privacy-policy) returned no readable text to the fetcher.

**Mistral AI (France/EU) for comparison**
- Mistral Studio free mode: Mistral "may use your input and output for training", and you can opt out at any time. Pay-as-you-go customers "retain full control over this processing" and can opt out at any time. Vibe individual plans train by default unless the user opts out. Thumbs-up/down feedback authorises training use on any plan. The help page shows no exact date ("Updated over a week ago") — [Mistral Help: Do you use my user data to train](https://help.mistral.ai/en/articles/323757-do-you-use-my-user-data-to-train-your-artificial-intelligence-models)
- Conflicting: a search snippet of another Mistral help article says La Plateforme API data is not used for training, Scale (paid) customers are opted out by default, and Experiment (free) users opt out via the Admin Console Privacy menu (snippet only, page not fetched) — [Mistral Help: opt out](https://help.mistral.ai/en/articles/455207-can-i-opt-out-of-my-input-or-output-data-being-used-for-training)
- Unverified: a ConductAtlas summary of Mistral's Commercial Terms says data sent to experimental "Labs Models" is used for training by default, other opt-outs do not carry over, and ZDR can be enabled for Labs models in Studio — [ConductAtlas](https://conductatlas.com/platform/mistral-ai/mistral-ai-commercial-terms/labs-models-training-opt-out-carve-out/)
- The pricing page lists "Opt-out" for model training in its plan table — [Mistral Pricing](https://mistral.ai/pricing)
- EU hosting: Requesty's docs list "Mistral: hosted in the EU by default" — [Requesty EU routing](https://docs.requesty.ai/features/eu-routing). OpenRouter's EU in-region catalogue includes Mistral as an EU provider — [OpenRouter Business EU](https://openrouter.ai/business/eu)

### Inferences
- **DeepSeek direct API:** this is not reasonable for chats that contain personal data (your own or anyone else's). Storage and processing are in the PRC under PRC-law terms, the API has no DPA, training is on by default with an email-only opt-out, and the Berlin and Italian DPAs consider transfers to China unlawful in substance. The Berlin DPA's finding concerns the consumer app, but the transfer reasoning applies equally to API traffic, since the API also processes in China.
- **Moonshot direct API:** Singapore storage is a weaker jurisdictional concern than the PRC. However, the July 2026 terms explicitly allow use of content to improve the services (read: training) unless you have an enterprise agreement. For a hobbyist that means your chats can be trained on. There is no EU representative, no DPA and no ZDR. It is acceptable only for non-personal, non-sensitive prompts.
- **Z.ai direct API:** this is the strongest of the three on paper ("do not store any of the content" in the DPA). There is still no GDPR representative and no named transfer mechanism, and the parent company is Chinese. Treat the no-storage claim as an unaudited contractual statement.
- **GDPR framing:** a private hobbyist using a chat app for personal purposes likely falls under the household exemption (Art. 2(2)(c) GDPR) for their own processing. The practical risk is therefore not a fine against the user but loss of control: data could be retained, trained on, or reached by foreign authorities, with weak enforceability of rights against a PRC or Singapore entity. If the app is ever opened to other users, the operator becomes a controller and Chapter V transfer rules bite. Transfers to China then look hard to justify, given the Berlin DPA's reasoning.
- **Better routes to the same models:** for the same open-weight models, an EU-hosted provider (Mistral itself serves GLM 5.3 and DeepSeek V4.1 Flash, see Q2), Alibaba's Frankfurt "EU" scope, or OpenRouter EU in-region routing (see Q3) removes the China and Singapore hop.

### Gaps
- Moonshot China platform (platform.moonshot.cn) terms on API training were not fetched. The claim that the China platform says "API data not used for training" is unverified.
- Z.ai China platform (bigmodel.cn, Beijing Zhipu Huazhang) terms were not researched. Zhipu's US Entity List status (from prior knowledge, Jan 2025) was not re-verified.
- Alibaba Model Studio's data-use and training policy was not found; the privacy and data-security docs for Model Studio need checking. The contracting entity for international accounts was not verified.
- MiniMax's official API privacy policy text could not be retrieved, so all MiniMax privacy claims are unverified.
- Mistral's API retention period (e.g., abuse monitoring) and the exact wording of its current DPA were not verified, and the two Mistral help articles conflict.
- No primary Garante document from 2026 on DeepSeek was found. Whether the Italian limitation still stands in Oct 2026 is unverified.
- The ZDR offerings of Moonshot, DeepSeek or MiniMax (if any) are unconfirmed beyond third-party trackers.

## Q2: What are the exact current model names, prices, API features and signup options for each vendor (e.g., what is "Kimi K3.1" actually called)?

### Takeaway
"Kimi K3.1" is **Kimi K3.1 Pro**. It has been on Moonshot's API since Oct 23, 2026, with open weights promised by Nov 4, 2026. The API ID is reportedly `kimi-k3.1-pro`, plus a `-highspeed` variant, and the base K3 is `kimi-k3`. DeepSeek's current API models are `deepseek-flash` (DeepSeek-V4.1-Flash-1017) and `deepseek-v4-pro` (DeepSeek-V4-Pro-0813). Z.ai's newest flagship is GLM-5.3. Qwen's current tops are `qwen3.8-max`, `qwen3.7-plus` and `qwen3.8-flash`. MiniMax's are MiniMax-M3 and MiniMax-M3.1-Flash. Mistral's newest is Mistral Large 4 (v26.10). All six vendors offer OpenAI-style APIs; tool calling is confirmed officially for DeepSeek, and the others rely on vendor statements or third-party docs.

### Cited Findings

**Moonshot / Kimi**
- Kimi K3.1 Pro was released on the API on Oct 23, 2026 with a 1M-token context. Moonshot says "Full model weights will be released by Nov 4, 2026", and most headline benchmarks are company-reported — [LetsDataScience](https://letsdatascience.com/news/moonshot-releases-kimi-k31-pro-api-open-weights-due-nov-4-786e160c); [Hora de Codar](https://horadecodar.com.br/kimi-k31-pro/)
- Kimi K3 launched Jul 16, 2026 (app and API), with open weights scheduled for Jul 27, 2026. It has a reported 2.8T parameters — [Emergent](https://emergent.sh/news/kimi-k3-release-date); [nexos.ai](https://nexos.ai/blog/kimi-k3/)
- The official pricing page lists display names Kimi K3.1 Pro, Kimi K3, Kimi K2.7 Code and Kimi K2.6. The K3 series has 1,048,576 tokens of context and K2 has 262,144. The page says K2 models stop being offered to new users from Oct 31, 2026, with all K2 retired by end of Dec 2026. Context caching is automatic (default TTL 5 min), and K3 cache writes are billed by TTL (5 min / 1 h). Prices exclude taxes. The price tables did not render in the fetch — [Kimi pricing](https://platform.kimi.ai/docs/pricing/chat)
- Kimi's help page lists `kimi-k3` (flagship, up to 1M context) and `kimi-k2.6` (text, image and video, thinking and non-thinking). The platform is "compatible with the OpenAI API format", billing is pay-as-you-go with no subscription, and you register at platform.kimi.ai — [Kimi API overview](https://www.kimi.ai/help/kimi-api/api-overview)
- Unverified (aggregators citing the official rate card): `kimi-k3.1-pro` costs $2.00 input, $0.20 cached input and $10.00 output per 1M tokens. Cache writes cost $2 (5 min) or $4 (1 h). `kimi-k3.1-pro-highspeed` costs twice that ($4 / $20). K3.1 Pro is about one-third cheaper per token than K3 — [Crazyrouter, Oct 2026](https://crazyrouter.com/en/pricing/kimi-k3-1-pro); [eesel.ai](https://www.eesel.ai/blog/kimi-k3-1-pro-pricing)
- Unverified (tutorials): the base URL is `https://api.moonshot.ai/v1`, with standard `tool_calls`, tool_choice and streaming deltas for reasoning and content — [DataCamp](https://www.datacamp.com/tutorial/kimi-k3-tutorial); [Apidog](https://apidog.com/blog/kimi-k3-api/)

**DeepSeek**
- Models: `deepseek-flash` maps to DeepSeek-V4.1-Flash-1017, and `deepseek-v4-pro` maps to DeepSeek-V4-Pro-0813. Both have 1M context, up to 384K output, and thinking on by default. The legacy names `deepseek-v4-flash` and `deepseek-v4-flash-vision-exp` now route to V4.1-Flash-1017 — [DeepSeek pricing](https://api-docs.deepseek.com/quick_start/pricing)
- Prices per 1M tokens, off-peak / peak (USD):

  | Model | Cache hit | Cache miss | Output |
  |---|---|---|---|
  | `deepseek-flash` | $0.003 / $0.006 | $0.15 / $0.30 | $0.60 / $1.20 |
  | `deepseek-v4-pro` | $0.022 / $0.044 | $0.66 / $1.32 | $1.98 / $3.96 |

  Peak hours are 01:00–04:00 and 06:00–10:00 UTC, Mon–Fri — [DeepSeek pricing](https://api-docs.deepseek.com/quick_start/pricing)
- Features: JSON output, tool calls, Responses API, Anthropic API format, prefix completion and FIM (beta) for both models. Vision is Flash-only. Search and Fetch tools cost $0.75 per 1,000 requests, billed from Nov 1, 2026. The pricing page does not mention streaming — [DeepSeek pricing](https://api-docs.deepseek.com/quick_start/pricing)

**Z.ai (GLM)**
- GLM-5.3 is listed first under "Latest Models". Prices per 1M tokens (USD), input / cached / output:

  | Model | Input | Cached | Output |
  |---|---|---|---|
  | GLM-5.3 | $1.40 | $0.26 | $4.40 |
  | GLM-5.3-Flash | $0.15 | $0.03 | $0.50 |
  | GLM-5.3-FlashX | $0.37 | $0.075 | $1.25 |
  | GLM-5.2 / GLM-5.1 | $1.40 | $0.26 | $4.40 |
  | GLM-5 | $1.00 | $0.20 | $3.20 |
  | GLM-4.7 / 4.6 / 4.5 | $0.60 | $0.11 | $2.20 |

  GLM-4.7-Flash, GLM-4.5-Flash and GLM-4.6V-Flash are free. The page uses display names, not API IDs, and shows no date — [Z.ai pricing](https://docs.z.ai/guides/overview/pricing)
- Unverified: the API ID is likely `glm-5.3` at the international endpoint `https://api.z.ai/api/paas/v4/chat/completions`. Third-party hosts use `zai-org/GLM-5.3` instead — [dev.to guide](https://dev.to/hassann/how-to-use-the-glm-53-api-4ie9); [SiliconFlow](https://www.siliconflow.com/blog/glm-5-3-api-guide); [Requesty model page](https://www.requesty.ai/models-new/zai/glm-5.3)

**Alibaba Model Studio (Qwen)**
- The text-generation models listed first are `qwen3.8-max` (complex reasoning and coding), `qwen3.7-plus` (balanced) and `qwen3.8-flash` (fast and cheap). The page was last updated Oct 28, 2026 — [Model Studio models](https://www.alibabacloud.com/help/en/model-studio/models)
- Official pricing page, displayed in CNY per 1M tokens (input / output):

  | Model | Singapore | Frankfurt "Global" | Frankfurt "EU" |
  |---|---|---|---|
  | `qwen3.8-max` | 14.988 / 44.965 | 12 / 36 | not listed |
  | `qwen3.7-plus` (0–256K) | 2.998 / 11.991 | 2 / 8 | not listed |
  | `qwen3.8-flash` | 1.094 / 3.427 | 0.8 / 2.7 | 1.094 / 3.427 |

  Open-weight models such as qwen3.5-397b-a17b, qwen3.6-35b-a3b and qwen3.8-27b are also listed — [Model Studio pricing](https://help.aliyun.com/en/model-studio/model-pricing)
- Unverified (third-party): in USD, Singapore `qwen3.8-max` is about $2 input and $6 output. A dated snapshot `qwen3.8-max-0902` exists, and the free quota applies only to the Singapore region — [Usagebox](https://usagebox.com/articles/qwen-api-pricing-2026); [Aireiter](https://aireiter.com/blog/qwen3-8-max-0902-api)

**MiniMax**
- Prices per 1M tokens (USD), input / cache read / output:

  | Model | Input | Cache read | Output |
  |---|---|---|---|
  | MiniMax-M3.1-Flash | $0.15 | $0.015 | $0.60 |
  | MiniMax-M3 (≤512k input) | $0.30 | $0.06 | $1.20 |
  | MiniMax-M3 (>512k input) | $0.60 | $0.12 | $2.40 |

  MiniMax-M3 prices are described as a "Permanent 50% off". Priority tier costs 1.5x (`service_tier: priority`). The page shows pricing notices dated Jul 22 and Aug 20, 2026 and does not state OpenAI compatibility or tool calling — [MiniMax pricing](https://platform.minimax.io/docs/guides/pricing)

**Mistral**
- Current generalist models: Mistral Large 4 (v26.10, Mistral Ecosystem Open Weight License), Mistral Medium 3.5 (v26.04, Modified MIT), Mistral Small 4 (v26.03, Apache 2.0), Mistral Large 3 (v25.12, Apache 2.0), Ministral 3 14B/8B/3B (v25.12). Mistral also hosts third-party Z.ai GLM 5.3 / GLM 5.3 Flash and DeepSeek V4.1 Flash 1017 (MIT). Magistral and Devstral appear only in the deprecated table — [Mistral models](https://docs.mistral.ai/getting-started/models/)
- Price: "Mistral Large" costs $0.50 input / $1.50 output per 1M tokens, the only API price shown on the page. Batch is 50% off and cached input up to 90% off — [Mistral pricing](https://mistral.ai/pricing)

### Inferences
- The project's backend already supports OpenAI-compatible base URLs (`OPENAI_BASE_URL` in CLAUDE.md), so any of these vendors, or OpenRouter, Requesty or Mistral, could be plugged in without new provider code. Moonshot, DeepSeek, Z.ai and Alibaba (compatible mode) all advertise OpenAI-format APIs.
- Notable for the user: Mistral, an EU vendor, now serves GLM 5.3 and DeepSeek V4.1 Flash directly. That lets you use Chinese open-weight models without any data going to a Chinese or Singaporean company.
- For Kimi in particular, the K2 retirement (no new users from Oct 31, 2026) means only the K3 family will be available on Moonshot's own API for new signups. The EU-hosted options for Kimi on OpenRouter are currently only K2.6 and K2.7 Code (see Q3).

### Gaps
- Official Kimi prices and exact API IDs (`kimi-k3.1-pro`, `kimi-k3.1-pro-highspeed`) were not rendered on the official page. They come from aggregators.
- Z.ai's exact API ID for GLM-5.3 is not confirmed on an official page.
- Official USD prices for Qwen were not retrieved; the help.aliyun.com page displayed CNY.
- Mistral's per-model API prices (Large 4, Medium 3.5, Small 4) and exact API IDs were not shown on the fetched pages.
- Signup and payment details for individuals outside China (card or PayPal acceptance, KYC, phone verification) were not verified for DeepSeek, Z.ai, MiniMax or Alibaba. Kimi says only that it is pay-as-you-go via registration at platform.kimi.ai.
- Streaming support was not stated on DeepSeek's pricing page. It is generally standard, but not verified here.
- MiniMax's context length and API compatibility were not stated on its pricing page.

## Q3: With OpenRouter, can you enforce ZDR plus EU-only providers per request or per account, and what do those settings guarantee?

### Takeaway
Yes, with caveats. ZDR can be enforced per account (per model group, including "all other models"), per guardrail, or per request (`provider.zdr: true`, OR-combined so it can only add enforcement). Training providers can be excluded with `data_collection: "deny"` or the account setting. Provider allow-lists are possible per account (a ceiling) and per request (`only`). True EU-only processing, where OpenRouter itself decrypts and routes in the EU and only EU, EEA, UK or CH endpoints are used with no fallback outside, requires the paid **Business** plan (8% fee on credit purchases) or Enterprise, and the `eu.openrouter.ai` base URL plus an optional "europe" data-region guardrail. Account, billing and security metadata may still be processed in the US. The ZDR and data-policy labels reflect OpenRouter's own tracking and agreements, not independent audits.

### Cited Findings

**Per-request controls**
- The `provider` object in a request accepts:

  | Parameter | Effect |
  |---|---|
  | `order` | Tries the listed providers first |
  | `allow_fallbacks` | Set to `false` to fail instead of falling back |
  | `require_parameters` | Only providers supporting every request parameter |
  | `data_collection` | `"deny"` excludes providers that may store non-transiently and train |
  | `zdr: true` | Only endpoints with a Zero Data Retention policy |
  | `only` / `ignore` | Allow-list / deny-list of provider slugs |
  | `quantizations`, `sort`, `max_price` | Filtering and sorting |

  — [OpenRouter Provider Routing](https://openrouter.ai/docs/features/provider-routing)
- The Data Policy tag on model pages is OpenRouter's "best knowledge", not a definitive statement of each third party's policy. `zdr` filters model inference only. The Advisor and Subagent server tools forward `zdr` to inner model calls, but their tool backends are not filtered — [OpenRouter Provider Routing](https://openrouter.ai/docs/features/provider-routing)

**Account-level controls and how they combine**
- Account settings cover data-policy filtering, ZDR per model group (Anthropic, OpenAI, Google, SpaceXAI, "all other models"), allowed providers and ignored providers, all in privacy settings. Per-request `zdr` is OR-combined with account and guardrail settings, so a request "cannot turn off" account enforcement. Account allowed providers act as a ceiling and the request's `only` narrows within it; if nothing satisfies both, the request returns a 404. Account and request ignore-lists are merged — [OpenRouter Provider Routing](https://openrouter.ai/docs/features/provider-routing); [OpenRouter ZDR](https://openrouter.ai/docs/features/zdr)
- Guardrails can set `enforce_zdr_*`, allowed models and allowed providers per API key or member. Guardrails intersect, so a key-level guardrail can only narrow what the workspace allows — [OpenRouter ZDR](https://openrouter.ai/docs/features/zdr); [OpenRouter Business EU](https://openrouter.ai/business/eu)

**What ZDR actually means and guarantees**
- Definition: the provider "does not store your data for any period of time". Some endpoints do not train but still retain data, for example for abuse scanning or legal reasons — [OpenRouter ZDR](https://openrouter.ai/docs/features/zdr)
- How ZDR status is determined:
  - OpenRouter tracks each endpoint's policy and sometimes negotiates special agreements.
  - If it cannot confirm a policy, "it assumes the endpoint both retains and trains".
  - BYOK ZDR declarations are recorded but "not independently verified".
  - Implicit in-memory prompt caching at the provider "is not treated as retaining data".
  - ZDR does not cover plugins or tools such as web search. Under ZDR the Firecrawl engine is rejected.

  — [OpenRouter ZDR](https://openrouter.ai/docs/features/zdr)
- CSAM: ZDR traffic is subject to CSAM screening. A policy update dated Oct 27, 2026 screens all inference requests, ZDR included, in flight, and flagged content "may be retained for human review, reporting, and preservation" — [OpenRouter ZDR](https://openrouter.ai/docs/features/zdr); [OpenRouter Data Collection](https://openrouter.ai/docs/guides/privacy/data-collection)
- The programmatic ZDR endpoint list is at `https://openrouter.ai/api/v1/endpoints/zdr` — [OpenRouter ZDR](https://openrouter.ai/docs/features/zdr)
- Provider retention: OpenRouter "doesn't change routing based on retention" unless you use ZDR. Retention terms come from each provider's own terms. The training opt-out "has no bearing on OpenRouter's own policies" — [OpenRouter Privacy & Logging](https://openrouter.ai/docs/features/privacy-and-logging)

**OpenRouter's own logging**
- "OpenRouter does not store your prompts or responses" unless you opt in or content is flagged as potential CSAM. Private input/output logging is off by default (Observability settings). Product-improvement use is off by default; opting in gives a 1% discount. Per-request metadata is stored (token counts, latency, etc.; "not exhaustive") and excludes content. OpenRouter "samples a small number of prompts for categorization". For accounts that have not opted in, these are stored anonymously and categorised by a ZDR model. No retention periods are stated — [OpenRouter Data Collection](https://openrouter.ai/docs/guides/privacy/data-collection)
- Privacy policy (last updated Aug 31, 2026):
  - Operator is OpenRouter, Inc. under New York law.
  - "OpenRouter does not use your Inputs or Outputs for model training".
  - Inputs containing personal data "will also be collected by us".
  - General retention is "as long as is reasonably necessary".
  - Image, audio and video are not persisted beyond routing (with exceptions).
  - Analytics use Google Analytics and PostHog.
  - Transfers rely on adequacy (Art. 45) and SCCs (Art. 46), with no Data Privacy Framework mention.
  - No EU representative is named, and no sub-processor list is published in the policy.

  — [OpenRouter Privacy Policy](https://openrouter.ai/privacy)

**EU in-region routing**
- Requests to `eu.openrouter.ai` go only to shared provider endpoints in Europe (EU, EEA, UK and Switzerland). OpenRouter "never silently falls back to a shared endpoint outside the region"; the request errors instead. Prompts and completions are decrypted in the EU. OpenRouter input/output logging is skipped for regional requests even if enabled. A data-region guardrail set to `europe` makes requests via other domains fail with 403. Base URL `https://eu.openrouter.ai/api/v1`, same API key — [OpenRouter Business EU](https://openrouter.ai/business/eu)
- Not in region: account, billing, auth, security logs, abuse-monitoring metadata and other operational records "may be processed in the US", under a DPA with SCCs. Batch API jobs run in the US. Rejected on the EU domain: web search, web fetch, files, image generation, Auto Router and other multi-model routers, and the Batch API — [OpenRouter Business EU](https://openrouter.ai/business/eu)
- Plans: included in Business (no contract or minimum, 8% platform fee on credit purchases) and Enterprise. Not available on Standard (5.5% fee) — [OpenRouter Business EU](https://openrouter.ai/business/eu); [OpenRouter pricing (search snippet)](https://openrouter.ai/pricing.md). The Business tier launched around Sep 7, 2026 per a third-party tracker — [UsagePricing](https://www.usagepricing.com/blueprint/activity/openrouter-2026-09-07-business-tier-launch)
- EU catalogue at fetch time (69 models, 5 providers; refreshed hourly):

  | Provider | Models |
  |---|---|
  | Azure | 24 OpenAI models |
  | Mistral | 20, plus GLM 5.2 and 5.3 |
  | Amazon Bedrock | 17, incl. Claude, Nova, gpt-oss-120b/20b |
  | Google | 13, Claude and Gemini Flash Lite |
  | Inceptron | 6 open-weight: DeepSeek V4 Flash 0731, Kimi K2.6, Kimi K2.7 Code, GLM 5.2, GLM 5.3, GLM 5.3 Flash |

  Qwen is absent, and Kimi K3 / K3.1 Pro and DeepSeek V4 Pro are not in the EU catalogue — [OpenRouter Business EU](https://openrouter.ai/business/eu)

### Inferences
- **Standard (free-to-join) plan:** you can enforce `zdr: true` plus `data_collection: "deny"` account-wide and add an account-level allowed-provider list. That is a strong "no training, no retention per OpenRouter's records" setup. But you cannot guarantee EU processing: OpenRouter itself (US company) decrypts and routes the request, and a provider allow-list of "EU companies" does not guarantee that the specific endpoint is EU-hosted.
- **Business plan plus `eu.openrouter.ai` plus a "europe" data-region guardrail plus account ZDR:** this is the strongest enforceable configuration. Content stays in the EU/EEA/UK/CH, there is no out-of-region fallback, and OpenRouter content logging is skipped. Remaining exposure: US-processed account and abuse metadata, the CSAM in-flight screening (which may retain flagged content), and reliance on OpenRouter's characterisation of each endpoint's retention. A UK or Swiss endpoint counts as "Europe" but is outside the EU, though both have EU adequacy decisions.
- **Extra party in the data path:** OpenRouter, Inc. (US) is a processor seeing plaintext prompts in addition to the inference provider. With in-region routing it does so on EU infrastructure, but it remains a US company subject to US legal process.
- **Model availability:** for the Chinese open-weight models the user cares about, OpenRouter EU currently offers GLM 5.2/5.3 (Mistral or Inceptron), DeepSeek V4 Flash 0731 and Kimi K2.6/K2.7 Code (Inceptron), but not the newest Kimi K3.x, DeepSeek V4 Pro or any Qwen.

### Gaps
- No exact retention periods are given for OpenRouter's metadata or account data.
- OpenRouter's documentation does not explain how ZDR and provider filters interact with regional routing in edge cases. Whether all five EU providers are marked ZDR was not verified; check `/api/v1/endpoints/zdr` against the EU models API.
- Inceptron's own identity, location and data policy were not researched.
- Whether the regional DPA is available to Business self-serve customers, versus Enterprise only, is not explicit.
- How the Oct 27, 2026 CSAM screening is implemented (which model, where, and retention for flagged items) is not detailed.

## Q4: How do other aggregators (Requesty, LiteLLM-based hosted routers, Not Diamond / Martian, Hugging Face Inference Providers) handle privacy, and how far can you restrict them to EU or privacy-respecting providers?

### Takeaway
Requesty has the most explicit EU story among the alternatives. It runs an EU gateway in Frankfurt (`router.eu.requesty.ai`), has org-level "Restrict regions → EU" and per-key approved-model lists, and offers a GDPR Art. 28 DPA on request. Its pages conflict on whether zero retention of bodies is the default. Hugging Face says its router stores no request or response bodies (30-day debug logs without user data) but defers entirely to each provider's policy. Not Diamond is a router recommender rather than a proxy. LiteLLM is best self-hosted, which removes the extra party entirely. No usable information on Martian was found.

### Cited Findings
- **Requesty:**
  - The EU endpoint (OpenAI-compatible) is `https://router.eu.requesty.ai/v1`. Requesty processing (routing, logging, caching, analytics) runs in Frankfurt (AWS eu-central-1): "All processing and storage by Requesty stays in the EU".
  - The EU endpoint covers only Requesty's own layer. A global model ID can still send inference outside the EU, so use EU-region model IDs.
  - Restriction: an org admin can set Compliance → "Serving region" → "Restrict regions" → EU, after which Global, US and AP requests are rejected. Per key or team, approved-model lists filtered by EU region are available.
  - Listed EU-hosted models include AWS Bedrock `@eu-*`, Vertex `@eu`, and Azure `@francecentral` / `@swedencentral`. "Mistral: hosted in the EU by default".
  - The page does not state the default body-storage behaviour.

  — [Requesty EU routing docs](https://docs.requesty.ai/features/eu-routing)
- **Requesty DPA and retention:** a GDPR Art. 28 DPA is provided on email request to sales. The FAQ says "Request and response bodies are not stored. Observability runs on metadata only". The security page says org-wide zero retention is enabled on written request, which conflicts with that. Marketing figures (customers, uptime) are self-reported — [Requesty DPA](https://www.requesty.ai/dpa); [Requesty Security](https://www.requesty.ai/security); [Requesty EU](https://www.requesty.ai/eu-new)
- **Hugging Face Inference Providers:** "Hugging Face does not store any user data for training purposes. We do not store the request body or response when routing requests through Hugging Face. Logs are kept for debugging purposes for up to 30 days, but no user data or tokens are stored". For data handling it refers users to each provider's own policies. Routing uses TLS, and the Hub is SOC 2 Type 2 certified. "External providers are responsible for their own security measures". No date is shown — [HF Inference Providers Security](https://huggingface.co/docs/inference-providers/security)
- **Not Diamond:** the service is "not a proxy". Natural-language inputs are deleted after routing, and `hash_content=true` enables fuzzy hashing for stricter privacy. The page appears dated: it says SOC-2 compliance will be complete "in 2024" — [Not Diamond privacy docs](https://docs.notdiamond.ai/docs/privacy-security-and-local-deployments)
- **LiteLLM:** "no data or telemetry is stored on LiteLLM Servers when you self host". The cloud offering has US regions (N. California, Virginia) and an EU region in Frankfurt — [LiteLLM data security](https://litellm-dwo5s32yr-clerkieai.vercel.app/docs/data_security) (a vercel-hosted mirror of the LiteLLM docs). When self-hosted, spend logs with request and response data are not encrypted and cached prompts and completions are stored in plaintext — [LiteLLM security/encryption FAQ](https://docs.litellm.ai/docs/proxy/security_encryption_faq.md)
- **EUrouter** (EU-focused alternative gateway): claims zero data retention for API request and response bodies by default (self-description, unverified) — [EUrouter privacy](https://www.eurouter.ai/privacy)

### Inferences
- Every hosted router adds a second processor that sees plaintext prompts. The privacy value of a router is therefore limited to two things: enforcing provider choice, and its own no-logging promise. Neither is independently audited in the sources found, apart from HF's SOC 2 for the Hub.
- Requesty with the EU endpoint and org-level region restriction is roughly comparable to OpenRouter Business EU. It may be cheaper for a hobbyist, but no fee comparison was done, and its retention defaults need a written confirmation or DPA.
- For a self-hosted chat app, self-hosting LiteLLM (or just configuring the backend's `OPENAI_BASE_URL` per provider) and calling EU providers such as Mistral or Alibaba Frankfurt EU scope directly removes the extra party entirely. That is the most privacy-preserving option, at the cost of managing several accounts.
- Hugging Face Inference Providers gives no documented way to restrict routing to EU providers, so EU residency depends on manually selecting a provider and checking its policy.

### Gaps
- No information on Martian's data handling was found.
- No fee comparison (Requesty and others versus OpenRouter's 5.5% / 8%) was done.
- Whether Requesty's zero-retention is the default or opt-in is unresolved (conflicting pages).
- The list of HF Inference Providers that are EU-hosted, and whether HF offers provider pinning by region, was not researched.
- Whether LiteLLM Cloud's EU region keeps logs in the EU and stores bodies by default was not verified.
