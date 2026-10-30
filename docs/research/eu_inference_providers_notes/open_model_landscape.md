# Open-Weight LLM Landscape (late October 2026) and Self-Hosting Options

Research date: 2026-10-30. Scope: Part 1 = open-weight models worth testing in a LangChain/LangGraph chat app with tool calling; Part 2 = self-hosting hardware, inference servers on AMD ROCm, EU per-hour GPU rental.

General caveat for the report writer: the release cadence in 2026 is extremely fast. Many details below come from secondary blogs because vendor pages render benchmarks as images. Where only a secondary source exists, it is marked "(secondary)". Where sources conflict, both are given. Artificial Analysis (AA) changed its Intelligence Index methodology very recently, so AA scores from different weeks are not comparable.

---

## Which 5-10 open models are most worth testing in late 2026, and why?

### Takeaway
The open-weight frontier in late October 2026 is a cluster of very large Chinese MoE models: Kimi K3 / K3.1 Pro (Moonshot), GLM-5.3 (Z.ai), DeepSeek V4 / V4.1, MiniMax M3 / M3.1 Flash, Qwen3.8, and MiMo-V2.6-Pro (Xiaomi). Western entries are Mistral Large 4 (released 29 Oct 2026), Meta's Muse Spark Open (15 Oct 2026), Google Gemma 4 and the older gpt-oss. "Kimi K3.1" exists, but its exact name is **Kimi K3.1 Pro** (plus a "Highspeed" variant). It launched 23/24 Oct 2026 as API-only, and Moonshot says the weights will be published by 4 Nov 2026. A shortlist to test: Kimi K3 (K3.1 Pro once its weights land), GLM-5.3, DeepSeek V4.1 Flash 1017, MiniMax M3.1 Flash, Qwen3.8 (27B locally, 2.4T via rental or API), Gemma 4 31B/26B, gpt-oss-120b/20b, Mistral Large 4, and optionally Muse Spark Open or MiMo-V2.6-Pro.

### Cited Findings

#### Verification: what is "Kimi K3.1"?
- Moonshot released **Kimi K3.1 Pro** as "the first model in a new K3.1 series", alongside **K3.1 Pro Highspeed**, said to be about 2-3x faster with the same capabilities. Announcement date is 24 Oct 2026, though the article header says 23 Oct. — [Unite.AI](https://www.unite.ai/moonshot-ai-releases-kimi-k3-1-pro-first-model-in-new-k3-1-series/)
- K3.1 Pro is a post-trained version of Kimi K3 with "substantially larger post-training compute". It has about 3T parameters ("3T-class"), a 1M-token context (1,048,576 for higher Kimi Code tiers), and accepts image and video input. — [Unite.AI](https://www.unite.ai/moonshot-ai-releases-kimi-k3-1-pro-first-model-in-new-k3-1-series/)
- Open weights for K3.1 Pro are "expected by November 4, 2026". As of the Sunday after launch, one report found no K3.1 listing on Hugging Face. — [Unite.AI](https://www.unite.ai/moonshot-ai-releases-kimi-k3-1-pro-first-model-in-new-k3-1-series/); [Technology.org](https://www.technology.org/2026/10/26/moonshot-kimi-k3-1-pro-cyber-capabilities/)
- K3.1 Pro runs in thinking mode only: requests with thinking disabled return HTTP 400. `reasoning_effort` takes low, high or max (default max). A mistyped model ID silently falls back to "K2.8 Preview" without thinking. — [Unite.AI](https://www.unite.ai/moonshot-ai-releases-kimi-k3-1-pro-first-model-in-new-k3-1-series/)
- Vendor benchmarks: Terminal-Bench 4.0 65.7% (vs. Claude Opus 5.5 at 66.4% and GPT-6 Astra at 58.2%). Kimi Hallu Bench Hard claim-level hallucination fell from 23.4% to 8.3%. SWE-bench, tau-bench and BFCL are not reported. — [Unite.AI](https://www.unite.ai/moonshot-ai-releases-kimi-k3-1-pro-first-model-in-new-k3-1-series/)
- Moonshot removed cyber-related training data, which lowered its in-house exploit benchmark from 90.5% to 81.0% before the open-weight release (secondary). — [Technology.org](https://www.technology.org/2026/10/26/moonshot-kimi-k3-1-pro-cyber-capabilities/); [The Next Web](https://thenextweb.com/news/moonshot-kimi-k3-1-pro-open-weight-cyber)
- In AA's updated, more private-test-set-based index, "Kimi K3.1 Pro (weights not yet released) is the top open weights model at 46" (search snippet; the page returned 403 when fetched). — [Cybernews](https://cybernews.com/ai-news/artificial-analysis-leaderboard-update-open-weight-ai-ranking-hit/)
- VentureBeat reports allegations that influencers promoted K3.1 Pro without disclosing paid relationships. — [VentureBeat](https://venturebeat.com/technology/moonshots-kimi-k3-1-pro-flirts-with-open-weights-leadership-amid-paid-influencer-scandal-allegations)
- API pricing of $2 / $10 per M input/output tokens appears only in a search-result summary, unverified. — [Basic Tutorials](https://basic-tutorials.com/news/kimi-k3-1-pro-moonshots-new-ai-model-at-a-competitive-price/)

#### Moonshot Kimi K3 (current downloadable flagship)
- **Kimi K3** (API id `kimi-k3`) is a MoE model with **2.8T total / 104B activated** parameters. It has 93 layers (69 Kimi Delta Attention + 24 Gated MLA), 896 experts with 16 selected per token, a 160K vocabulary and a **1,048,576-token context**. It takes text and image input through a 401M MoonViT-V2 encoder, and the intro also claims video understanding. — [GitHub MoonshotAI/Kimi-K3](https://github.com/MoonshotAI/Kimi-K3)
- Thinking is **always on** and returns `reasoning_content`, with `reasoning_effort` set to low/high/max. The model was trained in "preserved thinking" mode, so for multi-turn and tool-call conversations the full assistant message (including `reasoning_content` and `tool_calls`) **must be passed back unchanged**. — [GitHub MoonshotAI/Kimi-K3](https://github.com/MoonshotAI/Kimi-K3)
- Vendor benchmarks at max reasoning: GPQA-Diamond 93.5, HLE-Full 43.5 (56.0 with tools), Terminal-Bench 2.1 88.3, BrowseComp 91.2, OSWorld-Verified 84.8, **MCPMark-Verified 94.5**, τ³-Banking 33.4, MMMU-Pro 81.6. — [GitHub MoonshotAI/Kimi-K3](https://github.com/MoonshotAI/Kimi-K3)
- Weights use MXFP4 with MXFP8 activations via quantization-aware training. Recommended engines are vLLM, SGLang and TokenSpeed. — [GitHub MoonshotAI/Kimi-K3](https://github.com/MoonshotAI/Kimi-K3)
- The hosted API launched 16 July 2026. Open-weight dates conflict: 26 July per [Roo newsletter](https://roo.beehiiv.com/p/kimi-k3-open-weights-license-benchmarks) vs. 27 July per [explainx](https://explainx.ai/blog/kimi-k3-open-weights-2-8-trillion-parameters-july-2026) and [Layer3 Labs](https://www.layer3labs.io/open-weights/kimi-k3-open-weights-guide).
- The open weights are about **1.4 TB** (headline). — [Techi](https://www.techi.com/kimi-k3-open-weights-inference-economics/)

#### DeepSeek V4 / V4.1
- **DeepSeek-V4 Preview** was released **24 Apr 2026**: **V4-Pro 1.6T total / 49B active** and **V4-Flash 284B / 13B active**, both with a **1M context**. Both have Thinking and Non-Thinking modes. The API supports OpenAI ChatCompletions and Anthropic formats. The legacy `deepseek-chat`/`deepseek-reasoner` names were retired after 24 Jul 2026. — [DeepSeek API news](https://api-docs.deepseek.com/news/news260424/)
- Weights are MIT-licensed, and the instruct models use FP4 + FP8 mixed precision (secondary). — [MorphLLM](https://www.morphllm.com/deepseek-v4); [Winbuzzer](https://winbuzzer.com/2026/04/27/deepseek-v4-open-weights-launch-xcxwbn/)
- Later builds: V4-Flash-0731 (31 Jul) and V4-Pro-0813 (GA 12-13 Aug). One source says the GA card lists 1.7T for V4-Pro rather than 1.6T (secondary, unverified). — [Yotta Labs](https://www.yottalabs.ai/post/deepseek-v4-release-date-specs-how-to-access-2026); [HF community blog](https://huggingface.co/blog/ResterChed/deepseek-v4-flash-official-release)
- **DeepSeek V4.1 Flash** shipped open weights on 10 Sep 2026 under MIT. It is now superseded by **V4.1 Flash 1017**, a dated update (about 17 Oct) that raised coding and agentic scores. — [Artificial Analysis model page](https://artificialanalysis.ai/models/deepseek-v4-1-flash); [MindStudio](https://www.mindstudio.ai/blog/deepseek-v4-1-flash-1017-release); [Cellcog](https://cellcog.ai/blog/deepseek-v4-1-flash-release-date/)
- V4.1 Flash is described as natively multimodal with 1M context and MIT weights (secondary). — [Oxen docs](https://docs.oxen.ai/inference-api/reference/models/deepseek-v4-1-flash). There is a tech report on KV-cache compression. — [arXiv 2609.19969](https://arxiv.org/pdf/2609.19969)
- AA lists **V4.1 Flash 1017 (Max)** at **552B total / 16B active**, 1M context, $0.2 blended price, 176 tok/s. That is larger than V4-Flash's 284B, so the two "Flash" generations differ in size. — [Artificial Analysis open-source models](https://artificialanalysis.ai/models/open-source)

#### Z.ai GLM-5.x
- GLM-5 was released 11 Feb 2026 under MIT ([HF blog](https://huggingface.co/blog/mlabonne/glm-5)); Wikipedia says 12 Feb. GLM-5.1 was released openly 7 Apr 2026. — [Wikipedia Z.ai](https://en.wikipedia.org/wiki/Z.ai)
- GLM-5.2 is a 753B open-weights model under MIT, reported to beat GPT-5.5 on several long-horizon coding benchmarks at about 1/6 the cost. — [VentureBeat](https://venturebeat.com/technology/z-ais-open-weights-glm-5-2-beats-gpt-5-5-on-multiple-long-horizon-coding-benchmarks-for-1-6th-the-cost)
- **GLM-5.3** launched API-only in mid-August (14 vs. 18 Aug conflict). Its weights appeared on HF on **28 Aug 2026** in BF16 and FP8, after a safety hold. It has about **744B total / 40B active**, a **1M context** and 128K max output. API price is $1.40 / $4.40 per M tokens. — [RunAIHome](https://runaihome.com/blog/glm-5-3-open-weights-live-hardware-guide-2026/); [Z.ai on X](https://x.com/Zai_org/status/2093354097122455713). AA instead lists 753B / 40B. — [AA open-source](https://artificialanalysis.ai/models/open-source)
- **GLM-5.3-Flash** is a 320B MoE under **MIT** with weights from 26 Aug 2026. It uses a new `glm5_next` architecture that needed a llama.cpp merge still in progress at the end of August, and Ollama/LM Studio support was pending. — [RunAIHome](https://runaihome.com/blog/glm-5-3-open-weights-live-hardware-guide-2026/)
- On τ²-bench, GLM-5.2 is listed at 99.1% (AA-sourced, harness not normalized) — [BenchLM](https://benchlm.ai/benchmarks/tau2-bench); GLM-5 is at 89.7% (marked unverified) — [Codesota](https://www.codesota.com/benchmark/tau2-bench)

#### Alibaba Qwen 3.5 / 3.6 / 3.8
- Official repo release list: **Qwen3.8-2.4T-A95B** (12 Aug 2026), **Qwen3.8-27B** (14 Aug 2026), Qwen3.6-35B-A3B (16 Apr), Qwen3.6-27B (22 Apr), Qwen3.5-397B-A17B (16 Feb), Qwen3.5-122B-A10B / 35B-A3B / 27B (24 Feb), Qwen3.5-9B/4B/2B/0.8B (2 Mar). — [GitHub QwenLM/Qwen3.8](https://github.com/QwenLM/Qwen3.8)
- Qwen3.8 has tunable reasoning depth via `reasoning_effort` and `preserve_thinking` (Qwen3.6 introduced thinking preservation). The serve commands use `--reasoning-parser qwen3` and **`--tool-call-parser qwen3_coder`** with `--enable-auto-tool-choice`, plus a 262,144-token context for 27B. Qwen3.5 is a "Unified Vision-Language Foundation". The repo is Apache-2.0, and per-model licenses are on HF. — [GitHub QwenLM/Qwen3.8](https://github.com/QwenLM/Qwen3.8)
- Qwen3.5 is Apache 2.0 — [Codersera](https://codersera.com/blog/qwen-3-5-complete-guide-2026/). Qwen3.7 (Max/Plus, May-June 2026) appears to be closed. — [Wikipedia Qwen](https://en.wikipedia.org/wiki/Qwen)
- AA scores **Qwen3.8 27B (Xhigh)** at 20 (dense, 256k context, 37 tok/s), the best open model under 40B on the current AA page. — [AA open-source](https://artificialanalysis.ai/models/open-source)

#### MiniMax M3 / M3.1
- **MiniMax M3** launched 1 Jun 2026 with up to 1M context (512K guaranteed). It takes text, image and video input and produces text. Weights are on HF as `MiniMaxAI/MiniMax-M3` with an official MXFP8 quant, and llama.cpp support was still in open PRs. Vendor benchmarks: SWE-Bench Pro 59.0%, Terminal-Bench 2.1 66.0%, BrowseComp 83.5%, **MCP Atlas 74.2%**. — [Codersera MiniMax M3](https://codersera.com/blog/minimax-m3-developer-guide/); [MiniMax blog](https://www.minimax.io/blog/minimax-m3)
- Early reports said the weights had not shipped at launch (since resolved per later sources). — [AI Insiders](https://aiinsiders.net/article/minimax-m3-ships-api-first-with-weights-still-pending)
- M3 is licensed under the "MiniMax Community License", not a standard OSI license (secondary). — [Verdent](https://www.verdent.ai/guides/minimax-m3-coding-agents)
- **MiniMax M3.1 Flash** reached GA on 19 Oct 2026: 428B / 23B MoE, 1M context, always-on reasoning, $0.15 / $0.60 per M tokens. — [Codersera M3.1 Flash](https://codersera.com/blog/minimax-m3-1-flash-complete-guide-2026/amp/); [AA open-source](https://artificialanalysis.ai/models/open-source). AA score conflict: 29 on the current AA open-source page vs. "43" in a Codersera teaser (likely different index versions).
- OpenRouter lists tool calling and JSON-schema structured outputs for M3. — [OpenRouter](https://openrouter.ai/minimax/minimax-m3)

#### OpenAI gpt-oss
- gpt-oss-120b and gpt-oss-20b were released 5 Aug 2025 under Apache 2.0. The 120b fits on a single 80 GB GPU and the 20b runs in about 16 GB. — [OpenAI](https://openai.com/index/introducing-gpt-oss/); [Built In](https://builtin.com/articles/openai-gpt-oss-release)
- As of June 2026 there was no new gpt-oss generation, only gpt-oss-safeguard. — [frankx.ai](https://www.frankx.ai/blog/gpt-oss-analysis-2026). One outlier claims a 9 Jun 2026 family with 8B/20B/120B and 256k context, uncorroborated. — [freeainews](https://freeainews.com/open-source/openai-gpt-oss-open-weight-2026/). gpt-oss does not appear on AA's current top-13 open list. — [AA open-source](https://artificialanalysis.ai/models/open-source)

#### Mistral
- **Mistral Large 4 ("Le Chonk")** has open weights "today" after a preview earlier in the month. It has about 1T parameters (the HF repo name `Mistral-Large-4-1T-A52B` implies 52B active), is natively multimodal, and has three reasoning modes (Low/Medium/High, default High). Vendor benchmarks: AA Coding Agent Index 48% using about 47% fewer tokens than GLM-5.3, Terminal-Bench 4.0 41%, BrowseComp 84.5%. API price is $0.70 / $2.10 per M. Self-hosting via vLLM or SGLang. — [Mistral](https://mistral.ai/news/mistral-large-4-oss/)
- The weights were released **29 Oct 2026**. — [Tech Insider](https://tech-insider.org/mistral-large-4-open-weights-cybersecurity-51-percent-2026/). AA: Mistral Large 4 (High) scores 26, 1.1T / 52B, 1M context, 161 tok/s. — [AA open-source](https://artificialanalysis.ai/models/open-source)
- Mistral Large 3 was Apache 2.0; Large 4 moved to a custom license (see the licensing section). — [Mistral](https://mistral.ai/news/mistral-large-4-oss/)

#### Meta (Llama is effectively over; Muse is the new line)
- **Muse Spark Open** was released **15 Oct 2026**: 816B total / 42B active, 1M context, "natively multimodal". Meta calls it "the most capable US open-weight model to date". It runs on SGLang, vLLM, TensorRT-LLM, Transformers, MLX, **llama.cpp** and Unsloth, with optimizations for AMD, Apple, Intel and NVIDIA. Meta demonstrated it on two M5 Ultra Mac Studios (512 GB each) with MLX. — [Meta research blog](https://research.meta.ai/blog/muse-spark-open); [HF model card](https://huggingface.co/meta-models/Muse-Spark-Open-816B-A42B)
- Hosted at launch by Baseten, Fireworks, Groq, Modal, Nebius, OpenRouter and Together. — [AI at Meta on X](https://x.com/AIatMeta/status/2110779758334386491). AA scores Muse Spark Open (Xhigh) at 25. — [AA open-source](https://artificialanalysis.ai/models/open-source)
- Meta also released **Muse Glimmer 30B** (dense, Apache 2.0, 10 Aug 2026). Meta "ended the open Llama line in April 2026", and Llama 4 Behemoth was never released. The latest Llamas remain Llama 4 Scout (109B/17B) and Maverick (400B/17B) from April 2025 (secondary). — [innFactory](https://innfactory.ai/en/ai-models/meta-llama/)

#### Google Gemma 4
- **Gemma 4** was released **2 Apr 2026** in four sizes: E2B and E4B (128K context, image/video/audio), a **26B MoE with 3.8B active** and a **31B dense** model (up to 256K context, image/video). It supports function calling, structured JSON and system instructions, under **Apache 2.0**. The 31B ranks #3 and the 26B #6 among open models on the Arena text leaderboard. BF16 weights fit on a single 80 GB H100, and quantized versions run on consumer GPUs. Supported runtimes include Ollama, llama.cpp, vLLM, LM Studio and AMD ROCm. — [Google blog](https://blog.google/innovation-and-ai/technology/developers-tools/gemma-4/); [Google Open Source blog](https://opensource.googleblog.com/2026/03/gemma-4-expanding-the-gemmaverse-with-apache-20.html)

#### Other prominent 2026 open releases (from AA's current open-weights list)
- AA Intelligence Index v5.0 open-weights top 13, as fetched 2026-10-30 (no snapshot date shown):
  - DeepSeek V4.1 Flash 1017 (Max), 32
  - GLM-5.3 (Max), 32
  - **MiMo-V2.6-Pro** (Xiaomi; 1.0T/42B), 30
  - **Ling 3.1 Flash 1019** (560B/25B), 29
  - MiniMax-M3.1-Flash, 29
  - **Step 5 Preview** (600B/27B), 29
  - Mistral Large 4 (High), 26
  - Muse Spark Open, 25
  - Qwen3.8 27B, 20
  - K2 Horizon 375B A23B, 18
  - Beam 1.0, 18
  - **Nemotron 3.5 Super VL** (120B/12B, 1M ctx, 439 tok/s), 14
  - Inkling, 12

  — [AA open-source](https://artificialanalysis.ai/models/open-source)
- AA's recent move toward private test sets "widened the gap" between open and closed models (headline and snippet). — [Cybernews](https://cybernews.com/ai-news/artificial-analysis-leaderboard-update-open-weight-ai-ranking-hit/). A third-party October deep-dive puts MiMo-V2.6-Pro at 46.3, inconsistent with AA's own page showing 30. — [Margrop blog](https://blog.margrop.net/en/post/aa-intelligence-index-october-2026-leaderboard-deep-dive-and-model-selection-guide/)

### Inferences
- **Recommended shortlist for this app**, with reasons:
  1. **Kimi K3 → K3.1 Pro**: best open model on AA's newest index and strongest vendor-reported agentic/MCP numbers. Weights for K3.1 are due 4 Nov. Thinking is mandatory, which matters for the app (see the tool-calling section).
  2. **GLM-5.3**: tied #1 on AA v5 open, with a strong τ²-bench history in the GLM-5.x line. Use GLM-5.3-Flash (MIT) as the "big but nearly local" variant.
  3. **DeepSeek V4.1 Flash 1017**: tied #1 on AA v5 open, MIT, very cheap on hosted providers, 1M context, thinking and non-thinking modes. V4-Pro is the bigger option.
  4. **MiniMax M3.1 Flash**: cheap, fast, always-on reasoning, with a first-class vLLM tool parser.
  5. **Qwen3.8-27B** and **Qwen3.6-35B-A3B**: the best homelab-class models, permissively licensed, with a standard `qwen3_coder` tool parser.
  6. **Gemma 4 31B / 26B-A3.8B**: Apache 2.0, explicit function calling, day-one ROCm/Ollama/llama.cpp support, and top-3/top-6 open on Arena.
  7. **gpt-oss-120b / 20b**: older but stable, Apache 2.0. The app already prepends a gpt-oss-style `Reasoning: <level>` directive to the system prompt (`backend/services/llm_provider.py`, `wrap_system_prompt_with_reasoning`), so it is the lowest-friction baseline.
  8. **Mistral Large 4**: EU vendor, multimodal, released yesterday. Rental or API only.
  9. Optional: **Muse Spark Open** (top US open model, attribution license) or **MiMo-V2.6-Pro** (license not verified).
- The two "Flash" lines are not small: DeepSeek V4.1 Flash is 552B, MiniMax M3.1 Flash 428B and GLM-5.3-Flash 320B. In 2026 "Flash" means a cheaper MoE, not a consumer-GPU model.

### Gaps
- No primary page confirmed AA's current overall rank for Kimi K3.1 Pro: the Cybernews page returned 403, and a secondary report says it ranked 4th overall behind Opus 5.5 models and Meta's Muse Wonder.
- The Kimi K3.1 open-weight license is not yet published.
- Xiaomi MiMo-V2.6-Pro, Ling 3.1 Flash (presumably Ant Group, unverified), Step 5 Preview (presumably StepFun, unverified), Beam 1.0, K2 Horizon, Inkling and Nemotron 3.5 Super VL were not researched beyond the AA table: no license, release date or tool-calling data. "K2 Horizon" is not confirmed to be a Moonshot model.
- Whether Mistral released smaller 2026 models (Small 4, Devstral, Ministral successors) was not verified. The Large 4 page mentions only Voxtral and Timestral.
- The Qwen3.8-2.4T and Qwen3.8-27B per-model licenses were not checked on HF. The repo is Apache-2.0, but the weights license is "on the model card".
- No LMArena numeric standings were retrieved apart from Google's "#3 / #6 open" claim for Gemma 4.

---

## Which have reliable tool calling (the app's agent uses tools via LangChain bind_tools)?

### Takeaway
All the shortlisted models advertise native function calling, and the self-hosted path is the same for every one: an OpenAI-compatible server (vLLM/SGLang with `--enable-auto-tool-choice --tool-call-parser <model-specific>`, or llama.cpp with Jinja templates) feeding `ChatOpenAI(base_url=...)`, which is exactly what this app's `OPENAI_BASE_URL` path does. The best tool-use evidence is vendor-reported: Kimi K3 (MCPMark 94.5), the GLM-5.x line (τ²-bench), MiniMax M3 (MCP Atlas 74.2), and Qwen and Gemma (well-known parsers). No reliable, normalized 2026 BFCL ranking exists for the newest open models. The main risk for this app is not parsing but **reasoning-state round-tripping**: Kimi K3/K3.1 (and Qwen3.8 with `preserve_thinking`) expect `reasoning_content` passed back with `tool_calls`.

### Cited Findings
- Kimi K3: for "multi-turn and tool-call conversations" the full assistant message including `reasoning_content` and `tool_calls` must be passed back unchanged. Thinking cannot be disabled. — [GitHub MoonshotAI/Kimi-K3](https://github.com/MoonshotAI/Kimi-K3). K3.1 Pro returns HTTP 400 if thinking is disabled. — [Unite.AI](https://www.unite.ai/moonshot-ai-releases-kimi-k3-1-pro-first-model-in-new-k3-1-series/)
- Kimi K3 vendor agentic scores: MCPMark-Verified 94.5, OSWorld-Verified 84.8, BrowseComp 91.2, τ³-Banking 33.4. BFCL and τ²-bench are not reported. — [GitHub MoonshotAI/Kimi-K3](https://github.com/MoonshotAI/Kimi-K3)
- Qwen3.5-3.8 serve recipes use `--tool-call-parser qwen3_coder --enable-auto-tool-choice --reasoning-parser qwen3` for vLLM, SGLang and TokenSpeed, all with OpenAI-compatible APIs. — [GitHub QwenLM/Qwen3.8](https://github.com/QwenLM/Qwen3.8)
- MiniMax M3.1 Flash on vLLM: `--enable-auto-tool-choice --tool-call-parser minimax_m3` (secondary). — [Codersera M3.1 Flash](https://codersera.com/blog/minimax-m3-1-flash-complete-guide-2026/amp/). M3 also supports tools and JSON-schema structured outputs on OpenRouter. — [OpenRouter](https://openrouter.ai/minimax/minimax-m3). Vendor MCP Atlas score is 74.2%. — [Verdent](https://www.verdent.ai/guides/minimax-m3-coding-agents)
- Gemma 4 natively supports function calling, structured JSON output and system instructions. — [Google blog](https://blog.google/innovation-and-ai/technology/developers-tools/gemma-4/). A community gist reports that Ollama v0.20.0 had Gemma 4 tool-call parsing and streaming problems that were fixed in llama.cpp built from source. — [gist (daniel-farina)](https://gist.github.com/daniel-farina/87dc1c394b94e45bb700d27e9ea03193). A community vLLM ROCm build runs Gemma 4 with a dedicated Gemma 4 tool-call parser on RDNA4. — search result summary of [vLLM RDNA4 community builds](https://hub.docker.com/r/tcclaviger/vllm-rocm-rdna4-mxfp4)
- DeepSeek V4 has Thinking and Non-Thinking modes and supports the OpenAI and Anthropic API formats. It is integrated with agent harnesses (Claude Code, OpenCode, OpenClaw), but the release note does not describe tool-calling specifics. — [DeepSeek API news](https://api-docs.deepseek.com/news/news260424/)
- τ²-bench (multi-turn tool use): GLM-5.2 at 99.1% is the open-weight leader per AA-sourced data, though BenchLM notes results "do not use one guaranteed-common harness". — [BenchLM τ²](https://benchlm.ai/benchmarks/tau2-bench). Codesota (unverified entries) has GLM-5 at 89.7%, then Step-3.5-Flash, Qwen3.5-397B-A17B and Qwen3.5-35B-A3B. — [Codesota](https://www.codesota.com/benchmark/tau2-bench)
- BFCL v4 aggregator snapshot (27 Oct 2026): top entry is an unverifiable "BTL-3" (88.5%), then closed Qwen3.7 Max at 75.0%. Open entries include Ling 3.0 Flash at 73.0% and Kimi K2.5 at 68.3%. The newest open models (K3, GLM-5.3, V4.1, M3.1) are not listed. — [BenchLM BFCL v4](https://benchlm.ai/benchmarks/bfcl-v4). Other BFCL aggregators look stale. — [llm-stats BFCL](https://llm-stats.com/benchmarks/bfcl); [PricePerToken BFCL v3](https://pricepertoken.com/leaderboards/benchmark/bfcl-v3)
- llama.cpp server handles OpenAI-style tools via Jinja chat templates and function-call parsing. — [DEV Community 2026 comparison](https://dev.to/rosgluk/llamacpp-vs-ollama-in-2026-which-runtime-should-you-run-4k7f). In 2025, streaming combined with tools did not work in llama-server (may be fixed since). — [Simon Willison](https://simonwillison.net/2025/May/28/llama-server-tools)
- Ollama's OpenAI compatibility covers Chat Completions and Responses. — [DEV Community](https://dev.to/rosgluk/llamacpp-vs-ollama-in-2026-which-runtime-should-you-run-4k7f)
- In-repo fact: the app builds `langchain_openai.ChatOpenAI` with an optional `OPENAI_BASE_URL`, calls `self.llm.bind_tools(self.tools)` in `backend/services/agent.py`, and expresses reasoning level as a `Reasoning: <level>` system-prompt prefix (`backend/services/llm_provider.py`), which is the gpt-oss/Harmony convention. — local code (`backend/services/llm_provider.py` lines 26-70, 146-173; `backend/services/agent.py` line 92)

### Inferences
- **Most reliable for this app's bind_tools loop, in order of expected friction:**
  - Lowest: Qwen3.6/3.8 via vLLM (`qwen3_coder`), gpt-oss, and DeepSeek V4/V4.1 in non-thinking mode.
  - Low: Gemma 4 (use vLLM or current llama.cpp rather than older Ollama), MiniMax M3.1 Flash (`minimax_m3`) and GLM-5.3.
  - Highest: Kimi K3/K3.1, because of mandatory thinking and the preserved `reasoning_content` requirement.
- To unverified knowledge, `langchain_openai.ChatOpenAI` does not round-trip a non-standard `reasoning_content` field on assistant messages. If so, Kimi K3/K3.1 multi-step tool loops through this app could degrade or error. A test should check whether the LangGraph agent passes the prior assistant message (with reasoning) back intact, or whether a provider-specific LangChain integration or a custom message converter is needed.
- The app's `Reasoning: high` system-prompt directive only affects gpt-oss. For Kimi, Qwen3.8 and DeepSeek, effort is set via `reasoning_effort` or API params (Qwen also needs `--reasoning-parser` server-side so reasoning does not leak into `content`).
- Vendor "agentic" benchmarks (MCPMark, MCP Atlas, Terminal-Bench, BrowseComp) are more informative for an agent app than BFCL, but they are self-reported. A small in-app eval over the app's own Neo4j and web-search tools is the only trustworthy check.

### Gaps
- No official BFCL v4 (gorilla.cs.berkeley.edu) or official τ²-bench repo numbers were retrieved for the October 2026 open models. The aggregators are inconsistent or include unverifiable entries.
- vLLM/SGLang tool-parser names for Kimi K3, GLM-5.3, DeepSeek V4.1 and Mistral Large 4 were not confirmed in docs. The K3 repo links recipes but names no parser.
- Whether LangChain `ChatOpenAI` preserves `reasoning_content` (it may drop it) was not verified in this session.
- LM Studio tool-calling behaviour on ROCm was not verified.

---

## Which licenses or usage restrictions matter for a private EU user?

### Takeaway
For a private, non-commercial EU hobbyist, almost none of the 2026 restrictions bite. The custom licenses (Kimi K3, GLM-5.3, Mistral Ecosystem, Muse, MiniMax Community) target large-revenue companies or Model-as-a-Service resellers. The one real EU problem is **Meta's Llama 4 license, which excludes EU-domiciled users**, and Meta's newer Muse Spark Open license does not. Cleanest licenses: Apache 2.0 (Gemma 4, Qwen3.5 family, gpt-oss, Muse Glimmer 30B) and MIT (DeepSeek V4/V4.1, GLM-5/5.2, GLM-5.3-Flash).

### Cited Findings
- **Apache 2.0**:
  - Gemma 4, the first Gemma under an OSI license; earlier Gemmas had a custom policy Google could change. — [Google Open Source blog](https://opensource.googleblog.com/2026/03/gemma-4-expanding-the-gemmaverse-with-apache-20.html); [GIGAZINE](https://gigazine.net/gsc_news/en/20260403-google-released-gemma-4/)
  - Qwen3.5. — [Codersera](https://codersera.com/blog/qwen-3-5-complete-guide-2026/)
  - gpt-oss. — [OpenAI](https://openai.com/index/introducing-gpt-oss/)
  - Muse Glimmer 30B. — [innFactory](https://innfactory.ai/en/ai-models/meta-llama/)
- **MIT**:
  - DeepSeek V4 and V4.1 Flash. — [MorphLLM](https://www.morphllm.com/deepseek-v4); [AA model page](https://artificialanalysis.ai/models/deepseek-v4-1-flash)
  - GLM-5. — [HF blog](https://huggingface.co/blog/mlabonne/glm-5)
  - GLM-5.2 and GLM-5.3-Flash. — [RunAIHome](https://runaihome.com/blog/glm-5-3-open-weights-live-hardware-guide-2026/)
- **Kimi K3 License** (custom; Moonshot calls K3 "open-weight", not open source):
  - A Model-as-a-Service business with more than $20M aggregate revenue in any 12 months needs a separate agreement.
  - Products with more than 100M MAU or more than $20M monthly revenue must display "Kimi K3" in the UI (secondary).
  - Sources: [Layer3 Labs](https://www.layer3labs.io/open-weights/kimi-k3-open-weights-guide); [GitHub](https://github.com/MoonshotAI/Kimi-K3) (names the license only); [AY Automate](https://www.ayautomate.com/blog/kimi-k3-open-weight-release)
- **GLM-5.3 License** (custom, not OSI):
  - Permits use, modification, sale, fine-tuning and derivatives.
  - Companies with more than $10B revenue in any 12 months must pass Z.ai's security review before commercial use.
  - Sources: [RunAIHome](https://runaihome.com/blog/glm-5-3-open-weights-live-hardware-guide-2026/); [The New Stack](https://thenewstack.io/zai-glm-weights-license/) (headline: "new license aims at hyperscalers")
- **Mistral Large 4: "Mistral Ecosystem Open-Weight license"** (modified MIT):
  - Free use, modification, fine-tuning and commercial use.
  - Businesses running a Model-as-a-Service offering need a separate commercial license.
  - Source: [Mistral](https://mistral.ai/news/mistral-large-4-oss/)
- **Muse Model License** (Muse Spark Open, dated Oct 2026):
  - Limited commercial terms.
  - MaaS offerings above $20M gross revenue over 12 months need a separate agreement.
  - "Built with Muse Spark Open" attribution is required.
  - No territorial exclusion, so the EU is not excluded; Meta Platforms Ireland is the licensor for Europe.
  - Sources: [Meta blog](https://research.meta.ai/blog/muse-spark-open); [innFactory](https://innfactory.ai/en/ai-models/meta-llama/); [ibl.ai](https://ibl.ai/blog/meta-muse-spark-open-weight-licence-self-host-reality)
- **Llama 4 Community License**: "explicitly excludes use and distribution within the EU", so companies domiciled or headquartered in the EU may not use or host Scout or Maverick (secondary summary; exact clause not quoted). — [innFactory](https://innfactory.ai/en/ai-models/meta-llama/)
- **MiniMax M3**: "MiniMax Community License", not a standard permissive license (terms not retrieved). — [Verdent](https://www.verdent.ai/guides/minimax-m3-coding-agents)
- Moonshot says it will not release open weights that push the frontier of cyber capability, and trimmed K3.1 Pro's cyber skills before release. — [The Next Web](https://thenextweb.com/news/moonshot-kimi-k3-1-pro-open-weight-cyber)
- GPU-cloud jurisdiction: AWS and Microsoft are US companies subject to the US CLOUD Act even in EU data centers. — [Kontinent](https://kontinent.ai/en/blog/gpu-prices-europe)

### Inferences
- For a private hobbyist running models at home or on rented EU GPUs, the revenue and MAU thresholds (Kimi K3, Muse, GLM-5.3, Mistral MaaS clause) are irrelevant. Attribution clauses (Muse, Kimi at scale) only matter if the app is published as a product.
- **Avoid Llama 4** for an EU user; there is little reason to use it anyway, since Meta ended the line. Muse Spark Open is EU-usable with attribution.
- If the app might later be offered to others as a hosted service (i.e., MaaS), the Mistral Ecosystem license and the Kimi/Muse MaaS clauses become relevant. MIT/Apache models (DeepSeek, GLM-5.2/5.3-Flash, Qwen3.5, Gemma 4, gpt-oss) remain unconditional.
- Using the vendors' own hosted APIs (Moonshot, DeepSeek, Z.ai) sends data to non-EU providers. Self-hosting or EU-hosted inference avoids this. This is a GDPR/data-residency consideration, not a model-license one (no source retrieved on vendor data-processing terms).

### Gaps
- The full Kimi K3 License text, MiniMax Community License text, Muse Model License text and Llama 4 EU clause wording were not read in the primary. All thresholds above come from secondary summaries.
- Licenses for MiMo-V2.6-Pro, Step 5, Ling 3.1, Nemotron 3.5 and the Qwen3.8 weights were not verified.
- EU AI Act obligations for open-weight GPAI models (which fall mainly on providers, not private deployers) were not researched in this session.

---

## What can a homelab realistically run, and with which server software on AMD GPUs?

### Takeaway
On one or two consumer or workstation AMD GPUs (24-64 GB VRAM), the realistic tier is Qwen3.6-35B-A3B, Qwen3.8-27B, Gemma 4 31B / 26B-A3.8B, Muse Glimmer 30B, gpt-oss-20b, and gpt-oss-120b with CPU offload. A 128 GB Strix Halo or a big-RAM box with MoE offload stretches to about 100-300B MoEs (Qwen3.5-122B, Nemotron 3.5 Super, GLM-5.3-Flash at 1-bit, DeepSeek V4-Flash at low bits), at low speed. All frontier models (Kimi K3/K3.1, DeepSeek V4-Pro/V4.1 Flash, GLM-5.3, Mistral Large 4, Muse Spark Open, MiniMax M3.x, Qwen3.8-2.4T) need about 400 GB to 1.4 TB and are rental/API territory. On AMD: AMD officially ships vLLM for RDNA3/RDNA4/Strix Halo (vLLM 0.29 on ROCm 10.1), but RDNA support is still rougher than on Instinct. llama.cpp (ROCm/HIP or Vulkan) is the most robust option for quantized GGUF, and Ollama sometimes lags on new AMD cards and new model parsers. EU rental: H100 around €2.80-3.50/GPU-h, H200 around €3.00-4.80, B200 around €6.57, and 8-GPU nodes for 750 GB-1.4 TB models cost roughly €35-65/h.

### Cited Findings

#### Hardware data points (sourced)
- **GLM-5.3** (744B) Unsloth GGUF sizes: 1-bit ~217 GB (~230 GB RAM+VRAM, 3-6 tok/s), 2-bit 239 GB (245 GB+, 3-9 tok/s), 4-bit ~420 GB (~450 GB, "server territory"), FP8 ~750 GB (8 datacenter GPUs). Not suitable for 24 GB VRAM. A 256 GB+ Mac Studio or DDR5 CPU-offload box can run 2-bit at 3-9 tok/s, batch-only. Four RTX PRO 6000 (384 GB, about $64k) only clear 2-bit. — [RunAIHome](https://runaihome.com/blog/glm-5-3-open-weights-live-hardware-guide-2026/)
- **GLM-5.3-Flash** (320B): 1-bit GGUF is 93 GB, estimated at 10-20 tok/s on a 128 GB Strix Halo. For a 24 GB GPU the article recommends **Qwen3.6-35B-A3B** locally and an API for hard problems. — [RunAIHome](https://runaihome.com/blog/glm-5-3-open-weights-live-hardware-guide-2026/)
- **Kimi K3**: weights are about 1.4 TB. — [Techi](https://www.techi.com/kimi-k3-open-weights-inference-economics/). It needs a multi-GPU or multi-node server, and 24-32 GB consumer GPUs cannot host it. Ollama is useful only as a client to a hosted endpoint. — [Layer3 Labs](https://www.layer3labs.io/open-weights/kimi-k3-open-weights-guide). Layer3 Labs also claims a 512 GB Mac Studio can run a 4-bit quant, which contradicts the 1.4 TB native MXFP4 size (see Inferences).
- **Muse Spark Open** (816B/42B) was demonstrated on two Mac Studios with 512 GB each, using MLX. — [Meta blog](https://research.meta.ai/blog/muse-spark-open)
- **Gemma 4 26B/31B**: BF16 fits on one 80 GB H100, and quantized versions run on consumer GPUs. The ROCm stack is supported. — [Google blog](https://blog.google/innovation-and-ai/technology/developers-tools/gemma-4/)
- **gpt-oss**: the 120b fits on a single 80 GB GPU and the 20b in about 16 GB. — [OpenAI](https://openai.com/index/introducing-gpt-oss/); [Built In](https://builtin.com/articles/openai-gpt-oss-release)
- **Qwen3.8-27B**: 256K context. Local options are llama.cpp (GGUF), MLX, Unsloth quants and `transformers serve`. — [GitHub QwenLM/Qwen3.8](https://github.com/QwenLM/Qwen3.8)

#### Inference servers on AMD ROCm (sourced)
- **vLLM (official AMD distribution)**:
  - AMD's ROCm docs list vLLM 0.29.0 on ROCm 10.1.0 (Docker `rocm/vllm:rocm10.1.0_ubuntu24.04_py3.14-pytorch_2.13.0_vllm-0.29.0`), vLLM 0.27.0 on ROCm 10.0.0, and vLLM 0.23.x on ROCm 7.14.x (separate CDNA and RDNA images).
  - Supported Radeon hardware: RX 9070/9060/9050 (gfx1200/1201), RX 7900/7800/7700/7600 (gfx1100-1102), Radeon PRO W7900/W7800/W7700/V710, Radeon AI PRO R9700/R9600, and Ryzen AI Max (gfx1151, Strix Halo). Instinct: MI300X/MI325X/MI350X/MI355X.
  - Known issue: slow warmup on Radeon in vLLM v0.21-v0.25 (use ≥0.26).
  - Source: [AMD ROCm docs: vLLM](https://rocm.docs.amd.com/projects/ai-ecosystem/en/latest/inference/vllm.html)
- **vLLM, community caveats**:
  - ROCm support for consumer RDNA GPUs in vLLM is called "experimental". — [lemonade-sdk/vllm-rocm](https://github.com/lemonade-sdk/vllm-rocm/)
  - An RDNA4 FP8 patch has not been upstreamed. — [vLLM issue #28649](https://github.com/vllm-project/vllm/issues/28649)
  - gfx1201 is not in vLLM's platform detection for the FP8 Triton path. — [vLLM forum](https://discuss.vllm.ai/t/native-fp8-wmma-support-for-amd-rdna4-rx-9070-xt-r9700-in-vllm/1900)
  - Community RDNA4 Docker builds run Qwen3-Coder (`qwen3_coder` parser) and Gemma 4 (Gemma 4 parser, vLLM 0.30.0 ROCm) with auto tool choice. — [tcclaviger docker image](https://hub.docker.com/r/tcclaviger/vllm-rocm-rdna4-mxfp4)
- **llama.cpp**:
  - On an RX 9070 XT, llama-server with Vulkan reached 62 tok/s vs. vLLM ROCm at 48 tok/s in one community benchmark. — [ivangotoy/llama-server-rdna4-vulkan](https://github.com/ivangotoy/llama-server-rdna4-vulkan)
  - ROCm/HIP and Vulkan backends, an OpenAI-compatible API, and an Ollama-compatible shim. — [PromptQuorum](https://www.promptquorum.com/power-local-llm/llama-cpp-explained)
  - Tool calling via Jinja templates. — [DEV Community](https://dev.to/rosgluk/llamacpp-vs-ollama-in-2026-which-runtime-should-you-run-4k7f)
  - New architectures lag: MiniMax M3 support was still in open PRs ([Codersera](https://codersera.com/blog/minimax-m3-developer-guide/)), and GLM-5.3-Flash's `glm5_next` merge was pending in late August ([RunAIHome](https://runaihome.com/blog/glm-5-3-open-weights-live-hardware-guide-2026/)).
- **Ollama**:
  - A third-party RX 9070 project (May 2026) says the official Windows installer bundles libraries compiled against ROCm 6.4.2, and RDNA4 (RX 9000) is "too new" for that build, so a workaround is needed. — [xnyzer/ollama-rocm](https://github.com/xnyzer/ollama-rocm)
  - ROCm 6.4.1 formally added RDNA4 support on specific Ubuntu/RHEL releases in May 2025. — [Phoronix](https://www.phoronix.com/news/AMD-ROCm-6.4.1-Released)
  - Gemma 4 tool-call parsing and streaming bugs in Ollama v0.20.0 were fixed in llama.cpp first. — [gist](https://gist.github.com/daniel-farina/87dc1c394b94e45bb700d27e9ea03193)
  - One blog says Ollama 0.30.0 (May 2026) now links llama.cpp directly instead of a fork (single source, unverified). — [DEV Community](https://dev.to/rosgluk/llamacpp-vs-ollama-in-2026-which-runtime-should-you-run-4k7f)
- **SGLang**: recommended by Moonshot (Kimi K3), Qwen, Mistral (Large 4) and Meta. Meta reports custom Helion kernels in SGLang giving 1.03-3.95x kernel speedups on NVIDIA and AMD GPUs. — [Meta blog](https://research.meta.ai/blog/muse-spark-open); [GitHub QwenLM/Qwen3.8](https://github.com/QwenLM/Qwen3.8); [Mistral](https://mistral.ai/news/mistral-large-4-oss/)
- **LM Studio** is listed among Gemma 4's supported runtimes. — [Google blog](https://blog.google/innovation-and-ai/technology/developers-tools/gemma-4/)

#### EU per-hour GPU rental (on-demand, per GPU-hour, excl. VAT, as of 8 Oct 2026)
- Source for all rows below: [Kontinent](https://kontinent.ai/en/blog/gpu-prices-europe).
- **H100 80 GB**:
  - OVHcloud: €2.80
  - Scaleway PCIe (Paris/Warsaw): €2.87
  - Scaleway SXM in 8-GPU nodes: €3.17
  - Verda (ex-DataCrunch) SXM: €3.48
  - Nebius SXM (Finland): €4.02
  - T Cloud: €5.22
  - AWS Stockholm: €6.58
  - Azure: €7.37-14.06
- **H200 141 GB**:
  - IONOS PCIe (DE, per-minute billing): €3.00
  - Verda: €4.54
  - Nebius (FI/FR): €4.83
  - OVHcloud 8x: €5.25
- **B200 180 GB**: Verda €6.57.
- **B300**:
  - Scaleway 8x288 GB (Paris): €7.50
  - Verda 268 GB: €8.27
- **A100 80 GB**: Verda €1.67; OVHcloud €2.75.
- **L40S 48 GB**: about €1.39-1.47 (Nebius, OVH, Verda, Scaleway).
- **RTX PRO 6000 Blackwell 96 GB**: Hetzner GEX63 €1.60 (hourly plus a one-time setup fee); IONOS €2.10.
- **Price moves and billing**:
  - Nebius and Verda raised prices between 24 Sep and 8 Oct 2026 (Nebius H100 $3.85 to $4.50; Verda H100 €2.95 to €3.48).
  - Verda spot is about half price; Nebius reservations are up to 35% off.
  - Scaleway prices are per-minute.
- **Market context**:
  - H100 SXM median $3.45/h and B200 SXM median $6.85/h (28 Sep 2026). — [gpuperhour](https://gpuperhour.com/gpu-price-index)
  - H100 on-demand median $3.70 across 39 providers. — [getdeploying](https://getdeploying.com/gpu-price-trends)
  - Nebius HGX B200 is reported at $8.50 and B300 at $9.50/GPU-h from 1 Oct 2026 (secondary). — [Spheron](https://www.spheron.network/blog/gpu-cloud-pricing-comparison-2026/)
  - Hetzner H100 is quoted at about $2.80/h by [Spheron EU guide](https://www.spheron.network/blog/gpu-cloud-providers-europe-2026/), but Kontinent lists only RTX PRO GPUs for Hetzner (conflict).

### Inferences
- **Sizing rule of thumb**: Q4 GGUF is about 0.55-0.6 bytes/param plus KV cache. This puts the realistic homelab tiers at:
  - **24 GB** (e.g., RX 7900 XTX): Qwen3.6-35B-A3B Q4 (about 20 GB, fast thanks to 3B active), Qwen3.8-27B Q4 (about 16-17 GB plus context), Gemma 4 31B Q4 (about 18-19 GB) or 26B-A3.8B, Muse Glimmer 30B Q4, gpt-oss-20b.
  - **32 GB** (Radeon AI PRO R9700) **or 2x24/2x32 GB**: the same models at Q6/Q8 with long context, and gpt-oss-120b with expert offload to system RAM.
  - **128 GB Strix Halo (Ryzen AI Max)**: gpt-oss-120b, Qwen3.5-122B-A10B Q4 (about 70 GB), Nemotron 3.5 Super (120B/12B), GLM-5.3-Flash 1-bit (93 GB, sourced).
  - **256 GB+ system RAM + one GPU (MoE expert offload)**: DeepSeek V4-Flash 284B/13B at Q3-Q4 (about 130-170 GB), GLM-5.3 at 2-bit (sourced, 3-9 tok/s), MiniMax M3.1 Flash 428B/23B at about 2-3 bit. All are slow and batch-ish.
  - **Not homelab**: Kimi K3/K3.1 (about 1.4 TB), DeepSeek V4-Pro (1.6T) and V4.1 Flash (552B), GLM-5.3 at ≥Q4, Mistral Large 4 (1T), Muse Spark Open (816B, unless two 512 GB Macs), Qwen3.8-2.4T.
- **Layer3 Labs' claim** that Kimi K3 at 4-bit fits a 512 GB Mac Studio is implausible: the native weights are already about 4-bit (MXFP4) at about 1.4 TB.
- **RunAIHome's "8x H100 runs GLM-5.3 FP8"** is also inconsistent with its own ~750 GB figure (8x80 GB = 640 GB). 8x H200 (1,128 GB) is the realistic minimum for FP8.
- **Server choice for AMD at home**:
  - llama.cpp `llama-server --jinja` (ROCm or Vulkan; try Vulkan on RDNA4) for GGUF and MoE offload. It is the most robust option and exposes an OpenAI API that works with `ChatOpenAI(base_url=...)`.
  - vLLM via AMD's official `rocm/vllm` image for unquantized or FP8 dense/MoE models that fit in VRAM. It gives the best tool-parser coverage (`qwen3_coder`, `minimax_m3`, Gemma 4) and reasoning parsers. Expect RDNA-specific rough edges (FP8 paths, warmup).
  - Ollama is the easiest, but lags on new AMD GPUs and new model templates and parsers; verify tool calling per model.
  - SGLang and TokenSpeed matter mainly on rented NVIDIA or Instinct servers; consumer RDNA support was not verified.
- **Rental sizing for occasional big-model tests**, computed from Kontinent's per-GPU prices (multiplied by GPU count):
  - DeepSeek V4-Flash (FP4/FP8, likely about 160-180 GB): 2x H200 for about €6-10/h, or 1x B200 at €6.57/h (tight).
  - MiniMax M3.1 Flash or Qwen3.5-397B (FP8, about 400-430 GB): 4x H200 for about €12-19/h.
  - GLM-5.3 FP8 (~750 GB), Muse Spark Open (~816 GB at FP8) or DeepSeek V4-Pro: 8x H200 for about €36-39/h (Verda or Nebius).
  - Mistral Large 4 (1T, FP8 about 1.05 TB plus KV): 8x B200 at about €53/h.
  - Kimi K3/K3.1 (~1.4 TB): 8x B300 at about €60/h (Scaleway) to €66/h (Verda). 8x B200 (1.44 TB) is too tight once the KV cache is included.
  - For a hobbyist, hosted EU-region APIs (e.g., Nebius, which hosts Muse Spark Open) or OpenRouter are far cheaper than renting 8-GPU nodes for a few test chats.

### Gaps
- Measured tok/s for the recommended local models on specific AMD cards (7900 XTX, R9700, Strix Halo) were not retrieved, apart from the one RX 9070 XT llama.cpp vs. vLLM benchmark and the GLM-5.3-Flash Strix Halo estimate.
- Exact GGUF sizes for Qwen3.6-35B-A3B, Qwen3.8-27B, Gemma 4, DeepSeek V4-Flash and MiniMax M3.1 Flash were not retrieved; the figures above are computed estimates.
- SGLang's support status on consumer RDNA GPUs, LM Studio's ROCm runtime and tool-calling behaviour, and Ollama's official AMD support matrix (current release notes) were not found in primary sources.
- Whether Ollama or LM Studio have builds for Kimi K3, GLM-5.3, DeepSeek V4.1 or MiniMax M3.1 was not confirmed.
- Scaleway's B200 pricing and the availability of multi-GPU (8x) configurations at IONOS H200 were not verified; per-provider minimum rental terms are only partially covered.
- The user's specific AMD GPU model is unknown, so the tier recommendation is generic.
