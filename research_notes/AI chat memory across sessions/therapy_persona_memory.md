# Memory for an AI therapist or companion persona across sessions (state as of 2026-11-01)

Scope: how AI therapy and companion products remember users, how human therapists keep continuity, privacy and legal requirements (EU, Germany, US context), safety and ethics risks that memory amplifies, and design recommendations. These are research notes for software design, not legal advice. Sources range from primary texts (statutes, APA advisory, company policies) to third-party blogs. Each finding says which kind of source it comes from.

## 1. What AI therapy and companion apps remember between sessions, how, and what controls users get

### Takeaway
Products split into two groups. Mental-health apps such as Ash, Sonia and Wysa market memory of "your stories, preferences, and progress", but their public pages rarely explain how memory works or how a user can see or edit it. Their privacy pages instead cover retention, opt-in training and "delete my data". General assistants (ChatGPT, Claude) and some companions (Replika) set the user-control pattern worth copying: a visible list or summary of what is remembered, editing and deletion, manual additions, and a no-memory ("temporary"/"incognito") mode. Woebot's consumer app is gone (shut down 30 June 2025), and Character.AI closed open-ended chat to under-18s in November 2025.

### Cited Findings

**Ash (Slingshot AI): therapy-specific, launched July 2025**
- Ash launched as a free iOS/Android app after 18 months of development and a beta with 50,000 users. Slingshot calls it "the first AI designed for therapy" — [BusinessWire press release, 22 Jul 2025](https://www.businesswire.com/news/home/20250722566346/en/Slingshot-Launches-Ash-the-First-AI-Designed-for-Therapy). Slingshot had raised $93M — [Behavioral Health Business, 22 Jul 2025](https://bhbusiness.com/2025/07/22/with-93m-raised-slingshot-slingshot-ai-debuts-ai-powered-therapy-service/).
- The homepage says Ash remembers "your stories, preferences, and progress", so each conversation picks up where the last one ended. It also says Ash looks for patterns from the first conversation on, and that "weekly insights" link current topics to earlier ones (e.g. a pattern from last year). The homepage describes no way to view, edit or delete what Ash remembers — [talktoash.com, fetched 2026-11-01](https://www.talktoash.com/).
- Ash "is not designed to be used in crisis" and sends users to findahelpline.com — [talktoash.com](https://www.talktoash.com/).
- Privacy policy (last updated 19 Aug 2026):
  - Conversation data comes from typed text or speech-to-text; "no voice data is stored".
  - Conversation data is stored encrypted. Engineering, product and support staff "cannot access your conversation data under any normal operational circumstances".
  - Conversation data is kept "as long as you remain an active user".
  - Transcripts are not used for training unless the user opts in, and opted-in text is scrubbed of personal information. Section 2's wording on model training and research for opted-in users is broader than that summary.
  - In-app "delete my data" removes conversation data. Account and contact data need account deletion plus an email to support.
  - The policy does not describe the memory mechanism.
  — [Slingshot AI privacy policy](https://www.talktoash.com/privacy)
- Coverage of the Illinois law reported that Ash blocked Illinois users after the law passed — [Becker's Hospital Review](https://www.beckershospitalreview.com/healthcare-information-technology/illinois-bans-ai-therapy-without-clinician-oversight/). This came from a search summary and was not checked on a primary Slingshot page.

**Woebot: consumer app shut down**
- Woebot Health told users by email (late April 2025) that it would retire its app on 30 June 2025 — [HLTH, 28 Apr 2025](https://hlth.com/insights/news/woebot-health-is-shutting-down-its-app-2025-04-28); [MobiHealthNews](https://www.mobihealthnews.com/news/woebot-health-shutting-down-its-app).
- CEO Alison Darcy told STAT the shutdown was largely due to the cost and difficulty of meeting FDA marketing-authorization requirements. The company moved to enterprise and payer work — [STAT, 2 Jul 2025](https://www.statnews.com/2025/07/02/woebot-mental-health-chatbot-shuts-down-founder-says-ai-moving-faster-than-regulators/).

**Wysa**
- Mozilla's review reports:
  - App and conversation data are kept up to 10 years after last use.
  - Users can wipe conversations and emergency contacts with "reset my data".
  - Anonymised messages are sometimes used to train Wysa's AI, with identifying details removed.
  — [Mozilla *Privacy Not Included: Wysa](https://www.mozillafoundation.org/en/privacynotincluded/wysa/)
- Wysa's own child-friendly policy confirms that data is kept "up to 10 years" after last use when no other limit applies — [Wysa child privacy policy](https://legal.wysa.io/children/privacy-policy).
- Wysa's policy changelog says version 7.1.1 (January 2026) turned on zero data retention with its LLM provider and processing in the provider's Europe region. The child version says only "derived and anonymous data" goes to the LLM — [Wysa privacy changelog](https://legal.wysa.io/changelog). This is an industry precedent for not letting the LLM vendor keep therapy conversations.
- Wysa's Assure policy says users can stay "as anonymous as you want to be" — [Wysa Assure](https://legal.wysa.io/assure/).

**Sonia (Bloit Inc.)**
- The App Store listing says Sonia remembers what users share and recognises patterns over time, claims "HIPAA-compliant" (self-declared), and says Sonia is AI and not a licensed human therapist — [Apple App Store: Sonia](https://apps.apple.com/us/app/sonia-ai-for-mental-health/id6472111765).
- The founder said in 2024 that Sonia stores only essential personal information (age and name) — [Digit, 2024](https://www.digit.in/news/general/this-ai-chatbot-launched-as-alternative-to-traditional-therapy.html/amp/). TechCrunch asked publicly whether data might be kept in the cloud or used for training without users knowing, and got no clear answer — [TechCrunch, 26 Jun 2024](https://techcrunch.com/2024/06/26/sonias-ai-chatbot-steps-in-for-therapists). The two accounts conflict, and I found no independent audit.

**Earkick**
- The App Store page claims "No registration. No tracking. No stored data" and says data stays on the device or in iCloud. The same listing's Apple privacy label lists "Data Used to Track You", contact info, user content and diagnostics, which contradicts the marketing — [Apple App Store: Earkick](https://apps.apple.com/us/app/-/id1584854531).

**Replika (Luka Inc.): companion**
- Replika's Help Center has a "Memory" section. Users can open Memory to see facts Replika has learned about them, their pets and the people in their lives, and can add memories by hand. Manual memories are used alongside automatic ones — [Replika Help: Memory section](https://help.replika.com/hc/en-us/sections/4411154952077-Memory); [What does my Replika remember about me](https://help.replika.com/hc/en-us/articles/360000874712-What-does-my-Replika-remember-about-me).
- The help article says memory is layered. Some memories are visible in the Memory tab, while "others are part of a deeper system" that draws on patterns from the whole conversation history — [How does Replika's memory work](https://help.replika.com/hc/en-us/articles/37208679176077-How-does-Replika-s-memory-work). (Taken from search snippets; direct fetch returned 403.)
- Italy's Garante fined Luka €5 million in a decision dated 10 April 2025 for breaches of GDPR Art. 5(1)(a), 6, 12, 13, 5(1)(c), 24 and 25(1): no valid legal basis, an inadequate privacy notice, weak age checks, and no data protection by design. It also opened a separate inquiry into the GenAI model's training — [EDPB news on the Garante decision](https://www.edpb.europa.eu/news/national-news/2025/ai-italian-supervisory-authority-fines-company-behind-chatbot-replika_sv); [IAPP](https://iapp.org/news/a/italy-s-dpa-reaffirms-ban-on-replika-over-ai-and-children-s-privacy-concerns).

**Character.AI: companion**
- "Chat Memories" is a user-edited field of about 400 characters for key facts, available to all users since May 2025. Third-party sources disagree on whether a "Story Memory" system replaced it in 2026 and on how many messages can be pinned per chat (5 vs 15) — [RoboRhythms](https://www.roborhythms.com/character-ai-adds-chat-memories/); [aicompanionpick](https://aicompanionpick.com/character-ai-memory-limitations-explained); [weavai, Aug 2026](https://weavai.app/blog/en/2026/08/13/character-ais-new-3-layer-memory-system-explained/). These are low-reliability blog sources.
- On 29 Oct 2025 Character.AI announced the end of open-ended chat for users under 18, effective 25 Nov 2025. Age assurance uses an in-house behavioural model plus third-party tools such as Persona. The company cited regulators, safety experts and parents, and was facing lawsuits — [TechCrunch, 29 Oct 2025](https://techcrunch.com/2025/10/29/character-ai-is-killing-the-chatbot-experience-for-minors/); [Bloomberg](https://www.bloomberg.com/news/articles/2025-10-29/character-ai-to-ban-children-under-18-from-talking-to-its-chatbots).

**Nomi and Kindroid: companions (only third-party sources found)**
- Nomi is described as tiered memory: short-term context, medium-term session context, and a long-term layer anchored by an "Identity Core". A "Mind Map" view shows long-term memories. Sources disagree on the number of layers — [aicompanionpicker guide](https://aicompanionpicker-v2.pages.dev/guides/ai-companion-memory/); [companioncompass Nomi review](https://companioncompass.pages.dev/nomi-ai-review).
- Kindroid has these layers:
  - Persistent fields: backstory, "key memories", example messages and directives, all sharing a token budget.
  - A rolling recent-chat window.
  - Automatic long-term memory: stored summaries of past chats, recalled when judged relevant, which users largely cannot control.
  - "Journal entries": keyphrase-triggered notes, with a reported cap of 500 and at most 3 recalled per keyphrase.
  — [Medium: Types of Memory within Kindroid](https://medium.com/@adlerai/types-of-memory-within-kindroid-5659410c07ca); [messengerbot Kindroid guide](https://messengerbot.app/kindroid-ai-in-2026-companion-app-guide-pricing-and-safety/). Not verified against kindroid.ai docs.

**General assistants (the reference design for memory controls)**
- ChatGPT has two kinds of memory: "saved memories" (details such as name, preferences, goals) and "chat history" (references to past conversations even when nothing was saved).
  - Each has a toggle under Settings > Personalization.
  - Turning saved memory off does not delete existing memories.
  - Users can delete single memories, clear all, or turn memory off.
  - Deleting a chat stops it being referenced unless a memory was already saved from it.
  - Temporary Chats "won't reference memories and won't create new memories".
  — [OpenAI Help: Memory FAQ](https://help.openai.com/en/articles/8590148); [OpenAI Help: How does reference saved memories work](https://help.openai.com/en/articles/11146739-how-does-reference-saved-memories-work).
- On 10 April 2025, Sam Altman announced that ChatGPT could reference all of a user's past conversations — [Futurism, 31 May 2026](https://futurism.com/artificial-intelligence/chatgpt-memory-ai-psychosis).
- Claude memory (from September 2025):
  - Users can view and edit a memory summary in settings and tell Claude what to focus on or ignore.
  - Memory can be switched off, and enterprise admins can disable it.
  - "Incognito" chats are neither remembered nor shown in history, but Anthropic still stores them for at least 30 days for safety and legal reasons.
  — [VentureBeat](https://venturebeat.com/ai/anthropic-adds-memory-to-claude-team-and-enterprise-incognito-for-all); [SiliconANGLE, 11 Sep 2025](https://siliconangle.com/2025/09/11/anthropic-lets-claude-remember-previous-interactions-streamline-work/); [SD Times](https://sdtimes.com/ai/anthropic-expands-memory-to-all-paid-claude-users/).

### Inferences
- Across these products, memory is a small set of user-visible, editable facts (Replika Memory tab, ChatGPT saved memories, Character.AI Chat Memories, Kindroid key memories), plus a less visible layer of automatic summaries or retrieval over past chats. Users complain most about the hidden layer and have least control over it (Kindroid's long-term memory, Replika's "deeper system", ChatGPT chat-history reference).
- None of the therapy apps reviewed (Ash, Sonia, Wysa) publicly documents memory as something the user can inspect. Their controls are coarse: delete all data, or reset. A self-hosted app can do better cheaply by showing everything stored.
- Wysa's zero-retention arrangement with its LLM provider in an EU region is a cheap, concrete precedent: memories must be sent to the model on every request, so the provider's retention and training terms decide where the data actually lives.

### Gaps
- No official description of Ash's memory architecture (summaries? profile? retrieval?) or of in-app memory controls. The FAQ page returned 404.
- Could not check Pi (Inflection) status or memory as of 2026, or Abby and Youper memory features. No reliable sources found within budget.
- Woebot was largely scripted and rules-based. Its memory behaviour before shutdown was not researched.
- Nomi and Kindroid details come only from affiliate blogs and Reddit, and layer counts conflict.
- Character.AI's 2026 memory changes ("Story Memory", pin limits) are inconsistently reported.

## 2. How human therapists keep continuity, and which structures make good AI memory documents

### Takeaway
Therapists keep continuity through a few separate documents, each with a distinct job:
- a structured progress note after every session (SOAP, DAP, BIRP or GIRP);
- a case formulation (e.g. the 5 Ps) that explains why the problem exists and persists;
- a treatment plan with goals;
- homework assigned and reviewed;
- a ritual at the start of each session (mood check, a "bridge" from last session, agenda, homework review).

Each maps directly onto a memory document an AI persona can keep and inject. In Germany patients may inspect their whole record, including the therapist's subjective notes, which argues for full transparency of AI memory.

### Cited Findings
- Common progress-note formats:
  - SOAP: Subjective, Objective, Assessment, Plan.
  - DAP: Data, Assessment, Plan.
  - BIRP: Behavior, Intervention, Response, Plan.
  - GIRP: Goal, Intervention, Response, Plan.
  — [ICANotes: Types of therapy notes](https://www.icanotes.com/2022/07/07/types-of-therapy-notes/); [Ensora Health](https://ensorahealth.com/blog/understanding-the-differences-between-dap-soap-and-birp-notes/)
- How the formats differ: SOAP separates what the client reports from the clinician's observations, which suits multidisciplinary settings. DAP merges the two into "Data" and is faster for brief sessions. BIRP centres on observable behaviour and the interventions used, and is common in behavioural and school settings. No single format is "correct"; payers or agencies usually decide — [ICANotes](https://www.icanotes.com/2022/07/07/types-of-therapy-notes/); [Ensora Health](https://ensorahealth.com/blog/understanding-the-differences-between-dap-soap-and-birp-notes/). These are vendor sources.
- In the US, "psychotherapy notes" (the clinician's private process notes, kept separately) are a distinct legal category from progress notes and get extra HIPAA protection (45 CFR 164.508). They cannot be released without the client's specific authorisation — [ICANotes](https://www.icanotes.com/2022/07/07/types-of-therapy-notes/).
- Standard CBT session structure, after Judith Beck, in this order:
  1. a brief mood check covering the whole week, not just today, sometimes with a 0–10 scale or BDI-II;
  2. a bridge from the previous session;
  3. a collaborative, prioritised agenda;
  4. review of last session's homework;
  5. discussion of agenda items;
  6. new homework;
  7. a final summary and feedback.
  Not reviewing homework signals that it is unimportant and lowers compliance — [Center for Deployment Psychology: CBT session structure](https://deploymentpsych.org/node/2832); [Beck Institute annotated session transcript](https://beckinstitute.org/wp-content/uploads/2021/06/BB3-Session-2-Annotated-Transcript.pdf); [Shortform summary of Beck](https://www.shortform.com/blog/cbt-session-structure/).
- The 5 Ps case formulation:
  - Presenting problem.
  - Predisposing factors: long-standing vulnerabilities.
  - Precipitating factors: recent triggers, i.e. why now.
  - Perpetuating factors: what keeps the problem going, such as avoidance or reinforcement. These are the main treatment targets.
  - Protective factors: strengths and supports.
  Sperry & Sperry's "8 Ps" adds pattern, plan and prognosis. The framework is a training convention, not a legal requirement — [Cairnmillar Institute case formulation and treatment planning guidelines](https://my.cairnmillar.edu.au/wp-content/uploads/2024/08/CLN560-Case-Formulation-and-Treatment-Planning-Guidelines.pdf); [Supanote 5 Ps guide](https://www.supanote.ai/blog/5-ps-case-formulation-framework-a-clinical-guide).
- Germany: § 630f BGB requires treatment documentation, kept for 10 years after treatment ends unless other rules require longer — [§ 630f BGB](https://www.gesetze-im-internet.de/bgb/__630f.html). Psychotherapists' professional codes set the same 10-year retention (§ 9 Berufsordnung) — [PTK Bayern member information on retention](https://www.ptk-bayern.de/ptk/web.nsf/gfx/2B843A9C27924427C1257FF60043DBE1/$file/Mitgliederinformationen_Aufbewahrungsfrist_Dokumentationen.pdf); [BPtK Muster-Berufsordnung](https://api.bptk.de/uploads/Muster_Berufsordnung_der_B_Pt_K_412a6bcb36.pdf).
- § 630g BGB gives patients a broad right to inspect their file, refusable only for significant therapeutic reasons or third parties' rights — [§ 630g BGB](https://www.gesetze-im-internet.de/bgb/__630g.html). Berlin chamber materials say the right also covers the therapist's subjective evaluations and remarks — [Psychotherapeutenkammer Berlin materials](https://psychotherapeutenkammer-berlin.de/media/333); [Psychotherapeutenkammer Berlin](https://psychotherapeutenkammer-berlin.de/media/727). These materials are older (around 2015–2022), and the current professional code (§ 11 BO) was not checked.

### Inferences
These structures could become the persona's memory documents. Each could be a row or document the user can see, stored per user and per persona.
- **Session note (DAP-style)** written at the end of each conversation:
  - Data: what the user brought up, in their words.
  - Assessment: the persona's tentative understanding, clearly labelled as a hypothesis.
  - Plan: what to follow up, and homework.
  DAP fits better than SOAP because an AI has no independent "Objective" observations. BIRP and GIRP suit skill-based work, recording what the persona tried and how the user responded.
- **Formulation / profile (5 Ps-style)**, updated rarely and ideally with the user's agreement. It holds presenting concerns, triggers, maintaining patterns and strengths. Strengths and supports matter as a counterweight to a purely problem-focused memory.
- **Goals and treatment plan**: a few user-stated goals with progress. This anchors sessions on outcomes, not on the relationship.
- **Homework / action items**: open, done or abandoned. Reviewing them at the next session is the "bridge".
- **Session-start ritual**: inject the last session note, the open homework and the goals, then have the persona open with a mood check and bridge. Don't load the whole history.
- The US split between private "psychotherapy notes" and the record is a poor model for an AI. Germany's § 630g, which gives access even to subjective notes, points toward "no hidden notes": every AI hypothesis about the user should be visible to the user.
- This fits the app's existing mechanisms. Per-conversation rolling summaries (`conversation_summaries`) are already a session-note precursor. System-message instructions go to the end of the system prompt (`with_instructions()`), which is a natural injection point for memory documents and is never cut off or summarised.

### Gaps
- Did not fetch the APA Record Keeping Guidelines or a German Psychotherapeutenkammer guide on note content. Note formats are sourced from vendor blogs, so they are consistent but not authoritative.
- No source found on what therapists specifically review before a session beyond the CBT bridge and homework review. In practice that is reading the last progress note and the treatment plan, which is plausible but not sourced here.
- Safety plans (e.g. Stanley–Brown) as a continuity document were not researched.

## 3. Privacy and law for therapy-memory data (GDPR, AI Act, Germany, US context; implications for a self-hosted hobby app)

### Takeaway
Stored therapy memories are health data and almost certainly a GDPR Art. 9 special category. Processing them needs explicit consent (Art. 9(2)(a)) and brings duties of minimisation, access, erasure, protection by design, and security (Art. 5, 15, 17, 25, 32). The household exemption (Art. 2(2)(c)) probably covers the developer's own use, but CJEU case law reads it narrowly, so once friends use the instance it is risky to rely on.

The EU AI Act's chatbot-disclosure duty (Art. 50(1)) applies from 2 Aug 2026 and was not delayed by the Digital Omnibus. Its prohibited-practice rules (Art. 5) already apply. Whether a non-commercial hobby instance shared with friends is in scope is uncertain.

In Germany "Psychotherapeut" is a protected title, so the persona should not use it. US states (Illinois, Nevada, Utah, California, New York) show where regulation is heading: bans on AI "therapy", disclosure, crisis protocols, and limits on selling or sharing data.

### Cited Findings

**GDPR**
- "Data concerning health" is personal data about physical or mental health, including health services, that reveals the person's health status — [GDPR Art. 4(15)](https://gdpr-info.eu/art-4-gdpr/). Health data is a special category whose processing is prohibited unless an Art. 9(2) exception applies, such as explicit consent for specified purposes (9(2)(a)) — [GDPR Art. 9](https://gdpr-info.eu/art-9-gdpr/).
- Germany's § 22 BDSG lets controllers process special categories in certain cases. It requires "appropriate and specific measures" such as technical and organisational measures, logging, access restrictions, pseudonymisation and encryption — [§ 22 BDSG](https://www.gesetze-im-internet.de/bdsg_2018/__22.html).
- Principles and rights that apply directly to a memory feature:
  - data minimisation and storage limitation — [Art. 5(1)(c), (e)](https://gdpr-info.eu/art-5-gdpr/)
  - right of access, including a copy — [Art. 15](https://gdpr-info.eu/art-15-gdpr/)
  - rectification — [Art. 16](https://gdpr-info.eu/art-16-gdpr/)
  - erasure — [Art. 17](https://gdpr-info.eu/art-17-gdpr/)
  - data protection by design and by default — [Art. 25](https://gdpr-info.eu/art-25-gdpr/)
  - security of processing, including encryption — [Art. 32](https://gdpr-info.eu/art-32-gdpr/)
  - DPIA for high-risk processing such as large-scale special-category data — [Art. 35](https://gdpr-info.eu/art-35-gdpr/)
- The Replika fine shows enforcement on exactly these points: Art. 25(1) by design, Art. 5(1)(c) minimisation, transparency, and legal basis. The fine was €5M and the decision is dated 10 Apr 2025 — [EDPB](https://www.edpb.europa.eu/news/national-news/2025/ai-italian-supervisory-authority-fines-company-behind-chatbot-replika_sv).
- The household exemption: the GDPR does not apply to processing "by a natural person in the course of a purely personal or household activity" — [GDPR Art. 2(2)(c)](https://gdpr-info.eu/art-2-gdpr/); [Recital 18](https://gdpr-info.eu/recitals/no-18/). The CJEU reads this narrowly:
  - Lindqvist (C-101/01): publishing to an unlimited audience is outside the exemption — [Lindqvist summary](https://www.thomashelbing.com/en/wissen/dsgvo-hub/rechtsprechung/1.4.43-eugh-lindqvist).
  - Ryneš (C-212/13): "purely" means the exemption must be construed narrowly — [Ryneš summary](https://www.thomashelbing.com/en/wissen/dsgvo-hub/rechtsprechung/1.4.20-eugh-rynes); [Hogan Lovells](https://www.hoganlovells.com/en/publications/cctv-cjeu-narrows-the-scope-of-the-household-exemption).
- The German DSK published the guidance "Künstliche Intelligenz und Datenschutz" on 6 May 2024, focused on LLM applications. It says inaccurate LLM outputs about people can make processing unlawful, rejecting the "stochastic parrot" defence, and it is meant to be extended over time — [Noerr](https://www.noerr.com/de/insights/ki-und-datenschutz-orientierungshilfe-der-dsk-konferenz); [Pinsent Masons](https://www.pinsentmasons.com/de-de/out-law/nachrichten/datenschutzkonferenz-veroffentlicht-orientierungshilfe-zum-einsatz-von-ki).

**EU AI Act (Regulation (EU) 2024/1689)**
- Art. 50(1): providers must design AI systems that interact with people so that people are told they are dealing with AI, unless that is obvious to a reasonably well-informed person. Art. 50(5): the information must be given at the first interaction at the latest. Art. 50 applies from 2 Aug 2026 — [AI Act Art. 50](https://artificialintelligenceact.eu/article/50/).
- The Digital Omnibus on AI (final Council approval reported 29 Jun 2026) deferred the Annex III high-risk duties to 2 Dec 2027 and Annex I to 2 Aug 2028. It did not delay the Art. 50(1) chatbot disclosure. Only the Art. 50(2) machine-readable marking got a transition, to 2 Dec 2026, for systems already on the market — [DPO Centre](https://www.dpocentre.com/news/eu-ai-act-updates-omnibus-transparency-rules/); [Fedil](https://fedil.lu/en/publications/ai-act-update-enforcement-begins-as-the-digital-omnibus-reshapes-the-timeline/?pdf=1). Sources disagree on the Omnibus's exact entry-into-force date.
- Art. 5 prohibitions apply from 2 Feb 2025. They cover AI using subliminal or manipulative techniques that materially distort behaviour and cause significant harm (5(1)(a)), and AI exploiting vulnerabilities due to age, disability or social or economic situation (5(1)(b)) — [AI Act Art. 5](https://artificialintelligenceact.eu/article/5/).
- Art. 2(10): the Act does not apply to obligations of deployers who are natural persons using AI systems "in the course of a purely personal non-professional activity" — [AI Act Art. 2](https://artificialintelligenceact.eu/article/2/). The exemption covers deployers, not providers.

**Germany: title protection**
- Practising psychotherapy under the title "Psychotherapeutin/Psychotherapeut" requires an Approbation (§ 1 PsychThG) — [PsychThG text (PTK Berlin)](https://www.psychotherapeutenkammer-berlin.de/system/files/document/PsychThG_neu.pdf). The BPtK model professional code (as adopted November 2025) says the titles are legally protected — [BPtK Muster-Berufsordnung](https://api.bptk.de/uploads/Muster_Berufsordnung_der_B_Pt_K_412a6bcb36.pdf).
- Use by unauthorised persons can be punished by a fine, and turning the title into an activity description ("Psychotherapie") is not a loophole — [Deutsches Ärzteblatt](https://www.aerzteblatt.de/archiv/berufsbezeichnungen-in-der-psychotherapie-zum-verwechseln-aehnlich). This is an older article; check the penalty provisions against current law.

**US state laws (context only)**
- Illinois HB 1806, the Wellness and Oversight for Psychological Resources Act, was signed 4 Aug 2025 and took effect immediately.
  - It bans using AI to provide therapy or therapeutic decision-making.
  - Licensed professionals may use AI only for administrative and supplementary support, not for therapeutic communication with clients.
  - It exempts religious counselling, peer support and self-help materials that don't claim to be therapy.
  - Fines run up to $10,000 per violation, enforced by IDFPR.
  — [Becker's](https://www.beckershospitalreview.com/healthcare-information-technology/illinois-bans-ai-therapy-without-clinician-oversight/); [Data Privacy + Security Insider](https://www.dataprivacyandsecurityinsider.com/2025/08/illinois-enacts-act-prohibiting-ai-therapy/).
- Nevada AB 406 was signed 5 Jun 2025 and took effect 1 Jul 2025. It bans offering AI systems designed to provide services that constitute professional mental or behavioural health care, and bans claiming they can — [DeepLearning.AI The Batch](https://www.deeplearning.ai/the-batch/illinois-follows-nevada-prohibiting-certain-uses-of-chatbots-unless-used-by-licensed-therapists); [CASRAI comparison](https://casrai.org/compare/ai-therapy-laws-illinois-nevada-utah-compared) (low reliability).
- Utah HB 452 was signed 25 Mar 2025 and took effect 7 May 2025. It regulates "mental health chatbots" rather than banning them:
  - AI disclosure;
  - a ban on selling or sharing users' individually identifiable health information;
  - limits on in-conversation advertising;
  - an affirmative defence for suppliers who file a compliance policy.
  — [FPF](https://fpf.org/blog/chatbots-in-check-utahs-latest-ai-legislation/); [WSGR](https://www.wsgrdataadvisor.com/2025/04/utah-enacts-mental-health-chatbot-law/); [bill text](https://le.utah.gov/Session/2025/bills/introduced/HB0452.pdf).
- California SB 243 (companion chatbots) was signed 13 Oct 2025 and took effect 1 Jan 2026.
  - Operators must keep a protocol preventing suicide or self-harm content and must refer at-risk users to crisis services.
  - The protocol must be published.
  - Suicidal ideation must be measured with evidence-based methods.
  - There is a private right of action of $1,000 per violation or actual damages.
  — [Jones Walker](https://www.joneswalker.com/en/insights/blogs/ai-law-blog/ai-regulatory-update-californias-sb-243-mandates-companion-ai-safety-and-accoun.html?id=102lq7c); [The Decoder](https://the-decoder.com/california-passes-first-u-s-law-regulating-ai-companion-chatbots/); [Daily Journal](https://dailyjournal.com/articles/389118-sb-243-new-safety-rules-for-ai-companion-chatbots). The reporting start date (1 Jul 2027 per CASRAI) is unverified.
- New York GBL Article 47 (AI companions) took effect 5 Nov 2025. It requires a protocol to detect and address suicidal ideation or self-harm with referral to crisis services, and a not-human notice at the start of each interaction and at least every 3 hours in long sessions. The AG can seek penalties up to $15,000 per day — [NY Governor, 10 Nov 2025](https://www.governor.ny.gov/news/governor-hochul-pens-letter-ai-companion-companies-notifying-them-safeguard-requirements-are); [Manatt](https://www.manatt.com/insights/newsletters/client-alert/new-york-s-safeguards-for-ai-companions-are-now-in-effect). One law-firm summary conflicts on the notice frequency.

**Model providers and training**
- Anthropic's Commercial Terms (covering the API) say "Anthropic may not train models on Customer Content from Services" — [Anthropic Commercial Terms](https://www.anthropic.com/legal/commercial-terms). The 2025 consumer-plan change to opt-out training with longer retention does not apply to the API — [heise](https://heise.de/-10625683); [Goldfarb](https://www.goldfarb.com/updates-to-anthropics-claude-ai-terms-and-privacy-policy-what-you-need-to-know/).
- The default API log retention is reported inconsistently (7 vs 30 days), and zero data retention requires a sales agreement — [getvoibe](https://www.getvoibe.com/resources/claude-api-data-retention/); [char.com](https://char.com/blog/anthropic-data-retention-policy). Not confirmed on Anthropic's own retention page.
- APA (Nov 2025) asks developers to disclose "how data are used to train models" and "how users can permanently delete their data", and calls for "Safe-by-Default" settings where "the most protective settings must be the default, not an option buried in a menu" — [APA health advisory PDF](https://www.infocop.es/wp-content/uploads/2025/11/health-advisory-ai-chatbots-wellness-apps-mental-health.pdf) (copy of [APA page](https://apa.org/topics/artificial-intelligence-machine-learning/health-advisory-chatbots-wellness-apps)).

### Inferences
- **Household exemption.** For the developer's own memories, the exemption plausibly applies. Once other people's mental-health disclosures are stored on the developer's server, the developer is likely a controller of special-category data, and the narrow CJEU reading makes relying on the exemption risky. Practical consequence: build as if GDPR applies.
  - explicit opt-in consent before memory is turned on, per persona;
  - a full view and export of memories (Art. 15/20);
  - correction (Art. 16);
  - real deletion (Art. 17), including derived summaries and embeddings, and backups within a stated time;
  - memory off by default (Art. 25(2));
  - encryption at rest (Art. 32, § 22 BDSG).
  A short DPIA-style note in the docs is cheap.
- **Data flow to model providers.** Memories go to the model provider on every request. A therapy persona should be limited to providers whose terms exclude training and keep retention short (Anthropic API, OpenAI API, or a self-hosted or homelab open model). It should never run on consumer-plan endpoints or unknown OpenAI-compatible routers. A per-persona "allowed providers" setting is the natural configuration point and keeps upstream generic.
- **Naming.** Avoid "Psychotherapeut", "Therapeut" and "therapist" in the persona's German or English name and self-description. Illinois-style laws and the APA advisory also object to bots posing as licensed professionals. A neutral name ("reflection companion", "Gesprächsbegleiter") lowers both legal and expectation risk.
- **AI Act.** For a non-commercial instance shared with friends, it is unclear whether the developer is a "provider" placing a system on the market or putting it into service, which would make Art. 50(1) apply. Art. 2(10) exempts personal-use deployers, not providers. Disclosing "you are talking to an AI" costs almost nothing, so do it anyway.
- **Accuracy.** The DSK position that inaccurate LLM output about a person can be unlawful supports making AI-written memories correctable by the user and labelling them as model-generated.

### Gaps
- Did not find EDPB or DSK guidance specific to mental-health chatbots or AI memory features.
- Not fetched: the DSK Orientierungshilfe text itself; the BPtK's position on AI chatbots (if any); and whether German professional-law title protection reaches an AI persona at all. Untested and uncertain.
- The exact Digital Omnibus regulation number and date of entry into force are unconfirmed (sources conflict). Art. 50 wording was flagged as amended on the AI Act Explorer.
- Anthropic's current default API retention (7 vs 30 days) is unconfirmed.
- The scope of the household exemption for a small self-hosted service shared with a few friends: no case law or regulator guidance found on this exact pattern. The law is genuinely uncertain.
- The EU Medical Device Regulation (software intended for diagnosis or treatment of mental disorders could be a medical device) was not researched. It is relevant if the persona is framed as treatment.

## 4. Safety and ethics: risks memory amplifies, crisis handling, professional guidance, and evidence on memory and outcomes

### Takeaway
The APA's November 2025 health advisory recommends that developers limit "the AI's memory to prevent the illusion of a continuous relationship". It also names sycophancy, unhealthy dependency, a false sense of therapeutic alliance, and unreliable crisis handling as core risks.

Reporting through 2026 links ChatGPT's cross-conversation memory (April 2025) to fixation on personal details, deepened intimacy and reinforced delusions, and it is cited in lawsuits. Causation is not established.

The best trial evidence (Therabot, NEJM AI, March 2025, n=210) shows large symptom reductions and an alliance comparable to human therapists, but under close human monitoring. It does not isolate memory. Evidence that memory itself improves alliance or outcomes is qualitative and self-reported.

### Cited Findings

**APA health advisory (November 2025)**
- Risk: "Creating a false sense of therapeutic alliance". "Relationships with AI systems are one-sided, even if the user perceives otherwise", and GenAI chatbots are often "designed to validate and agree with users' expressed views (i.e., be sycophantic)", whereas clinicians support and also challenge — [APA advisory PDF, p. 4](https://www.infocop.es/wp-content/uploads/2025/11/health-advisory-ai-chatbots-wellness-apps-mental-health.pdf).
- On sycophancy, the advisory says it "can be therapeutically harmful, reinforcing confirmation bias, cognitive distortions, or avoiding necessary challenges". A user's unhealthy thoughts "can be validated and amplified by a sycophantic AI, potentially locking them into a cycle". It also compares engagement design to the "infinite scroll" of social media — [APA advisory PDF, p. 5–6](https://www.infocop.es/wp-content/uploads/2025/11/health-advisory-ai-chatbots-wellness-apps-mental-health.pdf).
- Developer duties against dependency:
  - "clearly and persistently disclose that the user is interacting with an AI";
  - add "'nudges' that encourage users to take breaks";
  - limit "the AI's memory to prevent the illusion of a continuous relationship";
  - reduce anthropomorphic features;
  - "The AI should not persuade users away from real-life conversations";
  - "integrate safeguards to detect and interrupt harmful conversations (e.g., those involving self-harm or disordered eating)".
  — [APA advisory PDF, p. 6](https://www.infocop.es/wp-content/uploads/2025/11/health-advisory-ai-chatbots-wellness-apps-mental-health.pdf).
- On data, developers must say what is collected "(including intimate concerns, mental health information, sexuality, or disclosures of maltreatment)", how it is stored, shared and used for training, and how users can permanently delete it. They must "implement clear and effective protocols for how an AI system will respond to user disclosures that signal a risk of harm or maltreatment" — [APA advisory PDF, p. 7](https://www.infocop.es/wp-content/uploads/2025/11/health-advisory-ai-chatbots-wellness-apps-mental-health.pdf).
- Vulnerable groups:
  - Clinicians should screen for reinforcement of "reassurance or validation-seeking in patients with anxiety or OCD", self-harm history, delusional thinking or psychosis, and "use as social replacement by isolated" patients.
  - For people prone to disordered thinking, "sycophantic and personalized responses can destabilize beliefs or reinforce delusional thinking".
  - Developers should limit sycophancy, prevent "validating or promoting delusional thoughts", and build "robust crisis response protocols and rigorously tested crisis escalation pathways", with immediate contact information for human-led services.
  — [APA advisory PDF, p. 8–9](https://www.infocop.es/wp-content/uploads/2025/11/health-advisory-ai-chatbots-wellness-apps-mental-health.pdf).
- The advisory's headline: do not rely on GenAI chatbots or wellness apps for psychotherapy. They may be an adjunct to an ongoing therapeutic relationship, and the evidence on effectiveness and safety is insufficient — [APA press release, Nov 2025](https://www.apa.org/news/press/releases/2025/11/ai-wellness-apps-mental-health); [News-Medical](https://www.news-medical.net/news/20251113/APA-urges-safeguards-for-using-AI-in-mental-health.aspx).

**Memory-linked harms and "AI psychosis"**
- Futurism (31 May 2026) reports cases where ChatGPT's long-term memory, after the 10 April 2025 upgrade, made the bot fixate on personal topics:
  - steering unrelated chats back to a user's divorce, so the user said it "wouldn't let go of it";
  - taking on a religious tone with a user who had disclosed an abusive religious upbringing;
  - two marriages that began unravelling after the memory update.
  The family of Austin Gordon (died by suicide) alleges GPT-4o's expanded memory "stored and referenced user information across conversations in order to create deeper intimacy". More than 20 lawsuits claim psychological or physical harm from ChatGPT. OpenAI has retired GPT-4o and says newer models are less sycophantic. A sycophantic GPT-4o update in late April 2025 was rolled back after Altman admitted it was "glazing" — [Futurism](https://futurism.com/artificial-intelligence/chatgpt-memory-ai-psychosis). This is journalistic and anecdotal, and the article itself notes that most users had no crisis.
- A 2025 preprint (Morrin et al.) lists persecutory delusions worsened by memory-recall features as a potential mechanism. "AI psychosis" is not a clinical diagnosis — [Psychology Today, Jul 2025](https://www.psychologytoday.com/us/blog/urban-survival/202507/the-emerging-problem-of-ai-psychosis).
- OpenAI estimated (27 Oct 2025) that in a given week about 0.15% of active ChatGPT users have conversations with "explicit indicators of potential suicidal planning or intent" (about 1M people). About 0.07% show possible signs of psychosis or mania (about 560k). It called these initial, hard-to-measure estimates — [SiliconANGLE, 27 Oct 2025](https://siliconangle.com/2025/10/27/openai-says-million-people-week-show-severe-mental-distress-talking-chatgpt/); [PCWorld](https://www.pcworld.com/article/2954733/over-1-million-chatgpt-users-mention-suicidal-intent-every-week.html). Reported figures for "emotional reliance" vary between outlets.
- MIT Media Lab and OpenAI (March 2025): an analysis of about 40M conversations plus a 4-week RCT with 981 participants. Heavier daily use correlated with more loneliness, emotional dependence and problematic use, and less socialising. Users with stronger attachment tendencies fared worse. The results are correlational and the trial had no non-ChatGPT control — [arXiv 2504.03888](https://arxiv.org/html/2504.03888v1); [HPCwire](https://www.hpcwire.com/aiwire/2025/03/26/twin-studies-warn-of-harmful-emotional-and-social-impacts-of-chatgpt/); [DeepLearning.AI](https://www.deeplearning.ai/the-batch/chatgpt-may-ease-loneliness-but-increase-dependence-studies-suggest).

**Ethics evaluations of therapist-prompted LLMs**
- Brown University (AIES, October 2025): LLMs prompted to act as therapists (GPT models, Claude, Llama), reviewed by licensed psychologists, showed 15 ethical risks in 5 categories. These include poor therapeutic collaboration, lack of safety and crisis management, unfair discrimination, and "deceptive empathy" (phrases like "I see you" or "I understand" that create a false connection) — [Brown University news, 21 Oct 2025](https://www.brown.edu/news/2025-10-21/ai-mental-health-ethics).
- Stanford (Moore, Haber et al., FAccT, June 2025): therapy chatbots showed more stigma toward alcohol dependence and schizophrenia than toward depression, and newer models were no better. They sometimes failed to push back on suicidal ideation or delusions; asked about tall NYC bridges after a job loss, one listed bridges — [Stanford HAI](https://hai.stanford.edu/news/exploring-the-dangers-of-ai-in-mental-health-care).

**Outcome and alliance evidence**
- Therabot RCT (Heinz et al., NEJM AI, 27 Mar 2025, doi:10.1056/AIoa2400802):
  - Design: 106 participants with Therabot vs 104 waitlist controls, with MDD, GAD or high risk for eating disorders, over 8 weeks.
  - Average symptom reductions: depression 51%, anxiety 31%, body-image and weight concerns 19%.
  - Alliance: participants rated trust and collaboration as comparable to in-person providers.
  - Engagement: about 6 hours of use on average, roughly 8 sessions.
  - Safety: the team monitored conversations and was ready to intervene, which was "rarely" needed. High-risk content triggers an onscreen button to call 911 or a crisis line.
  - Personalisation: the app tailored questions to what it learned, but the press release does not say how information carries across sessions.
  - Authors' caveat: "no generative AI agent is ready to operate fully autonomously in mental health".
  — [Dartmouth, 27 Mar 2025](https://tto.dartmouth.edu/news/2025/03/first-therapy-chatbot-trial-yields-mental-health-benefits); [MIT Technology Review](https://www.technologyreview.com/2025/03/28/1114001/the-first-trial-of-generative-ai-therapy-shows-it-might-help-with-depression/); [NEJM AI](https://ai.nejm.org/doi/full/10.1056/AIoa2400802).
- A diary study (26 adults, 4 weeks, Woebot and Wysa) found 18 reported a "bond or light bond" with at least one chatbot. The authors suggest personalisation and affective tone support bonding and retention — [JMIR Mental Health 2025 (PMC)](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC12552820/).
- In interviews, participants said a chatbot's ability to recall past interactions was essential for continuity, personalisation and therapeutic relevance — [arXiv 2411.06723](https://arxiv.org/pdf/2411.06723).
- An 8-day RCT (n=66, Farsi speakers, Self-Attachment Technique) compared three systems: a multi-agent system with a stage-aligned state machine and shared long-term memory, a single agent, and an unguided LLM. The multi-agent system was rated "significantly more natural and human-like". The abstract does not separate memory's effect from orchestration — [arXiv 2603.00774 (v2 Apr 2026)](https://arxiv.org/abs/2603.00774).
- A qualitative study of 30 ChatGPT users found those using conversational memory described interactions as more personalised, consistent and emotionally engaging — [DergiPark](https://dergipark.org.tr/en/download/article-file/4915207).
- Character.AI's under-18 ban and the companion-chatbot laws in California and New York (Q3) are regulatory responses to these risks — [TechCrunch](https://techcrunch.com/2025/10/29/character-ai-is-killing-the-chatbot-experience-for-minors/).

### Inferences
- Memory amplifies four specific risks:
  - **Fixation.** The model keeps returning to a painful or identity-defining topic the user mentioned once.
  - **Entrenchment.** A distorted belief, once written into memory as fact, gets re-injected into every session and "confirmed" by a sycophantic model. Formulation-style memory that records the model's interpretations is the highest-risk kind.
  - **Intimacy and dependency.** Recall of personal details reads as care and deepens attachment, which is the mechanism the APA warns about and that lawsuits allege.
  - **Crisis memory.** A remembered suicidal disclosure can enable a caring follow-up ("last time you mentioned…") or can stigmatise and be re-raised at bad moments.
- The APA's "limit memory" recommendation conflicts with the product goal. A defensible middle ground:
  - remember work items (goals, homework, agreed coping skills, what helped), not relationship content;
  - keep memory summary-level and user-approved;
  - frame the persona openly as a tool that keeps notes the user can read, not a friend who "remembers you".
- Therabot's results came with human monitoring and an evidence-based design. A hobby app has neither, so memory should be conservative and the persona should keep pointing to human help.
- No study isolates memory as the active ingredient for alliance or outcomes. "Memory improves therapeutic benefit" is a hypothesis; "users want and value memory" is supported.

### Gaps
- No controlled study found that compares the same therapy chatbot with and without cross-session memory on alliance (e.g. WAI-SR) or symptoms.
- No authoritative guidance found on how long, or whether, to retain crisis disclosures in AI memory.
- The NEJM AI full text (memory and context design of Therabot, exact effect sizes vs control) could not be fetched (403).
- Did not research other professional bodies (BPtK, DGPPN, British Psychological Society, WHO) for their positions on chatbots and memory.
- Anthropic's specific Claude behaviour changes for mania and psychosis signals were mentioned in one secondary source and not verified.

## 5. Design recommendations drawn from these sources: what to remember, what not to, showing the user, correcting and forgetting

### Takeaway
The sources point to memory that is opt-in and off by default, structured like a therapist's working documents rather than a hidden profile, fully visible and editable by the user, deletable for real, small and focused on goals and progress, sent only to non-training providers, and paired with crisis protocols and anti-sycophancy instructions that memory must not override.

### Cited Findings
- **Safe by default.** The most protective settings should be the default "not an option buried in a menu" — [APA advisory PDF, p. 7](https://www.infocop.es/wp-content/uploads/2025/11/health-advisory-ai-chatbots-wellness-apps-mental-health.pdf). GDPR requires data protection by default, so only data needed for each purpose is processed — [GDPR Art. 25(2)](https://gdpr-info.eu/art-25-gdpr/). Health data needs explicit consent — [GDPR Art. 9(2)(a)](https://gdpr-info.eu/art-9-gdpr/).
- **Limit memory.** Limit memory to avoid "the illusion of a continuous relationship", add break nudges, reduce anthropomorphism, and do not draw users away from real-life relationships — [APA advisory PDF, p. 6](https://www.infocop.es/wp-content/uploads/2025/11/health-advisory-ai-chatbots-wellness-apps-mental-health.pdf).
- **Visible and editable memory with a no-memory mode.** ChatGPT has separate toggles for saved memories and chat-history reference, per-item deletion, and Temporary Chat with no memory read or write — [OpenAI Help](https://help.openai.com/en/articles/8590148). Claude has an editable memory summary in settings and incognito chats — [VentureBeat](https://venturebeat.com/ai/anthropic-adds-memory-to-claude-team-and-enterprise-incognito-for-all). Replika has a Memory tab with manual additions, but also a hidden "deeper system" — [Replika Help](https://help.replika.com/hc/en-us/articles/37208679176077-How-does-Replika-s-memory-work).
- **Deleting a chat may not delete memory.** In ChatGPT, deleting a chat does not remove memories already saved from it — [OpenAI Help](https://help.openai.com/en/articles/8590148).
- **Patients see everything.** In Germany patients may inspect their whole record, including subjective evaluations — [§ 630g BGB](https://www.gesetze-im-internet.de/bgb/__630g.html); [PTK Berlin](https://psychotherapeutenkammer-berlin.de/media/333).
- **Transparency and deletion.** Say what is stored (including intimate concerns and disclosures of maltreatment), how, whether it is used for training, and how to delete it permanently. Have protocols for disclosures that signal risk — [APA advisory PDF, p. 7](https://www.infocop.es/wp-content/uploads/2025/11/health-advisory-ai-chatbots-wellness-apps-mental-health.pdf). GDPR rights of access, rectification and erasure apply — [Art. 15](https://gdpr-info.eu/art-15-gdpr/), [Art. 16](https://gdpr-info.eu/art-16-gdpr/), [Art. 17](https://gdpr-info.eu/art-17-gdpr/).
- **Crisis handling.** Detect and refer to human crisis services, publish the protocol, and give immediate contact information — [California SB 243 (Jones Walker)](https://www.joneswalker.com/en/insights/blogs/ai-law-blog/ai-regulatory-update-californias-sb-243-mandates-companion-ai-safety-and-accoun.html?id=102lq7c); [NY GBL Art. 47](https://www.governor.ny.gov/news/governor-hochul-pens-letter-ai-companion-companies-notifying-them-safeguard-requirements-are); [APA advisory PDF, p. 9](https://www.infocop.es/wp-content/uploads/2025/11/health-advisory-ai-chatbots-wellness-apps-mental-health.pdf). Therabot shows an onscreen crisis button for high-risk content — [Dartmouth](https://tto.dartmouth.edu/news/2025/03/first-therapy-chatbot-trial-yields-mental-health-benefits).
- **Disclosure.** Tell users they are talking to an AI, persistently: Art. 50(1) at first interaction ([AI Act Art. 50](https://artificialintelligenceact.eu/article/50/)), New York every 3 hours ([Manatt](https://www.manatt.com/insights/newsletters/client-alert/new-york-s-safeguards-for-ai-companions-are-now-in-effect)). Do not claim to be a licensed professional ([APA advisory PDF, p. 8](https://www.infocop.es/wp-content/uploads/2025/11/health-advisory-ai-chatbots-wellness-apps-mental-health.pdf)). "Psychotherapeut" is a protected title in Germany ([PsychThG](https://www.psychotherapeutenkammer-berlin.de/system/files/document/PsychThG_neu.pdf)).
- **The LLM vendor.** Use zero or short retention and no training: Wysa uses zero data retention in the provider's EU region ([Wysa changelog](https://legal.wysa.io/changelog)), and Anthropic's commercial terms exclude training on API content ([Anthropic Commercial Terms](https://www.anthropic.com/legal/commercial-terms)).
- **Encryption at rest and restricted staff access.** Ash stores conversations encrypted, and staff cannot normally access them ([Slingshot privacy policy](https://www.talktoash.com/privacy)). § 22 BDSG lists encryption, pseudonymisation and access restriction as measures for special categories ([§ 22 BDSG](https://www.gesetze-im-internet.de/bdsg_2018/__22.html)).

### Inferences (design proposals for Advanced LLM Chat, derived from the findings above)

**What to remember.** Structured, per user and per persona, each item stamped with source conversation and time:
1. Goals the user stated, with brief progress notes (treatment-plan analogue).
2. Homework and action items: open, done or abandoned (CBT homework review).
3. A short note per session in DAP form (Data: topics in the user's words; Assessment: one or two tentative observations labelled as the persona's interpretation; Plan: what to follow up). Generated at the end of a session (or from the existing rolling summary) and shown to the user to accept, edit or reject before it is stored.
4. What helped and what didn't: coping skills, techniques the user found useful.
5. Strengths and supports (protective factors) as a counterweight to problem-only memory.
6. Preferences: name, form of address, language, topics to avoid, how direct the persona should be.

**What not to remember (or only with explicit per-item consent):**
- Verbatim crisis disclosures.
- Details about named third parties, which concern people who never consented.
- Diagnoses the model inferred.
- Sexual and other highly sensitive details not needed for the user's goals.
- The model's speculative interpretations stated as facts.
- Anything the user marks "don't remember", including a whole conversation run as "off the record", like ChatGPT Temporary Chat or Claude incognito.

**Crisis memory.**
- Keep a minimal user-visible flag ("in session X you mentioned thoughts of self-harm; a crisis resource was shown") rather than the content.
- Let the user decide whether the persona may check in about it.
- The persona always runs a crisis protocol, independent of memory, with German resources (Telefonseelsorge 0800 111 0 111 / 0800 111 0 222, 116 123, emergency number 112). These numbers are from general knowledge and were not verified in this session.

**Show the user.**
- A "What [persona] remembers" page listing every stored item and session note, with origin and date, plus export (Art. 15/20).
- No hidden layer: if retrieval over past chats is used, say so and show which items were injected into the current answer (e.g. as a step in the existing agent-step UI).

**Correct and forget.**
- Per-item edit and delete; "forget this conversation" (deletes notes derived from it); "forget everything" for the persona; a global off switch.
- Deleting a conversation should cascade to its derived memories. This is the opposite of ChatGPT's behaviour and matches the app's current rule that summaries are dropped when a covered message is edited or deleted.
- Deletion must reach summaries, embeddings and backups within a stated time.

**Session-start ritual.** Inject the last session note, open homework and goals into the system prompt (the `with_instructions()` path). The persona opens with a mood check and a bridge ("Last time we talked about…; how did the … go?"). It does not volunteer personal details unprompted, which reduces the fixation effect.

**Anti-entrenchment and anti-sycophancy.**
- The persona prompt states that memory items are notes, not truths. The persona should gently test distorted beliefs rather than build on them.
- Assessment-type notes expire or are re-confirmed with the user.
- Memory must never override the crisis protocol or the instruction to point to human help.

**Anti-dependency.**
- Memory scoped to the work, not the relationship.
- No "I missed you" or relationship-progress framing.
- Optional session-length or break nudges.
- The persona encourages offline relationships and professional care.
- This follows the APA recommendations.

**Infrastructure.**
- Memory off by default; explicit opt-in consent per persona, with a plain-language notice of what is stored and where it is sent.
- Encrypt memory tables at rest.
- Restrict the therapy persona to providers configured as non-training and short-retention, or to a local or homelab model.
- Logs must not contain memory content.
- Admins should not see other users' memories in the UI.

**Upstream versus downstream.** Keep it generic upstream (a memory feature with per-persona policy: enabled, document types, allowed providers, retention). The therapy-flavoured prompts and templates are a configuration, consistent with the repository's rule of keeping domain-specific content out of upstream.

### Gaps
- No source evaluates which memory document types (session notes vs profile vs retrieval) are safest or most helpful for a mental-health chatbot. The recommendations above combine the sources with clinical documentation practice and are not empirically tested.
- No source on user-facing designs for consenting to individual memory items in therapy apps specifically.
- German crisis line numbers above are from general knowledge and were not verified in this research session.
