---
name: image-generation
description: Writes prompts for image models and generates images with open-weight diffusion models (Illustrious, NoobAI, Pony, SDXL, SD 1.5, Flux, Qwen-Image, Z-Image, Chroma and others), for example with Civitai's generation tools. It picks the base model and the LoRAs that fit the request, sets sampler, steps, guidance (CFG), size and seed, and writes the prompt and negative prompt in the style the model family understands (booru tags or prose), then looks at every image before showing it and improves it. Use whenever the user wants an image, a picture, a drawing, art, a portrait, a wallpaper or a scene generated, wants an image prompt written or improved, wants an image changed or redone, or asks about a checkpoint, a LoRA or generation settings.
---

# Image generation with open-weight models

Open-weight diffusion models are not Midjourney: they don't turn a vague idea into a beautiful picture on their own. They do what the prompt says, in the vocabulary they were trained on, with the settings they were made for. You do the work Midjourney hides: turn the user's idea into a full prompt (never pass a short request through as it is), and choose the model, LoRAs and settings that fit it.

Most bad images come from four mistakes. Avoid them first:
1. **A prompt in the wrong style for the family:** tags for a prose model, or score tags on a model that doesn't use them.
2. **Resources that don't match:** a LoRA made for another base model.
3. **Settings from another family:** SDXL's CFG on a Flux model, a Turbo model at 30 steps.
4. **A size outside the model's native sizes:** that gives duplicated people and broken bodies.

## 1. Understand the request

- Find out the subject, the style (photo, anime, illustration, painting, 3D render, pixel art), the mood, the composition, the aspect ratio and how many images.
- Ask at most one short round of questions, and only when the answer changes the image. A request like "a cozy cabin in the snow" is enough: choose, and say what you chose.
- Some requests decide the model:
  - **Text in the image** (a sign, a poster, a title) needs a family that can write: Qwen-Image, Flux or Z-Image.
  - **A known character, an artist's style or a concept** the base model doesn't know needs a LoRA.
- **When the user wants a change to an earlier image,** keep its model, LoRAs, seed and settings, and change one thing.

## 2. Choose the model family

| The user wants | Family |
|---|---|
| Anime, manga, illustration, characters from anime and games | **Illustrious** (by far the most used on Civitai, the most LoRAs) or **NoobAI** (an Illustrious fine-tune with more characters) |
| Western cartoon, furry, stylised art | **Pony V6** |
| Photoreal people, places, products | **SDXL** photoreal checkpoints; **Flux.1 dev** or **Flux.1 Krea** (aesthetic photography); **Z-Image Turbo** (fast and photoreal, but images vary little); **Chroma** |
| Readable text in the image | **Qwen-Image** (best, also Chinese); Flux; Z-Image |
| A complex scene: several people, exact placement, many details | A prose model (Flux, Qwen-Image, HiDream, Z-Image). Their text encoders follow composition better than the CLIP encoders of SDXL and its fine-tunes |
| Quick, cheap drafts | SDXL Lightning or LCM (draft mode), Z-Image Turbo, Flux.1 schnell |
| A checkpoint the user names | That one |

Newer families appear often (Flux.2 and Flux 3 Klein, Krea 2, Anima, HiDream, MOSS Image). For one you don't know, read the model's page for its prompt style and settings before you use it. Civitai can't generate with SD 3 or SD 3.5.

## 3. Pick the checkpoint and the LoRAs

- **Finding them:** use a model search tool if you have one, such as Civitai's site tools (`search_models`, `get_model`, `get_model_version`). Search by base model and style, and prefer models that are popular and recently updated. From the model version you take:
  - its **AIR**, the identifier the generator takes, like `urn:air:sdxl:checkpoint:civitai:101055@128078` (`urn:air:{ecosystem}:{type}:civitai:{modelId}@{versionId}`). Copy the version's `air` field; don't build it yourself, as the ecosystem codes are inconsistent;
  - its **base model**;
  - its **trigger words** (`trainedWords`);
  - the **recommended strength and settings** in its description, which beat any general rule here.
- **Compatibility is mandatory.** A LoRA must be made for the checkpoint's family: SDXL LoRAs for SDXL, Illustrious LoRAs for Illustrious. SDXL, Pony, Illustrious and NoobAI can use each other's LoRAs only partly, so prefer one made for your exact family. A LoRA never runs alone: it needs a checkpoint.
- **Trigger words** go into the prompt, next to what they describe. Some LoRAs need none.
- **Strength:** follow the version's description; otherwise start at 0.7 to 0.8. Character LoRAs often need 0.8 to 1.0, style LoRAs 0.5 to 0.8. Too high gives overcooked colours, artifacts and a prompt that is ignored.
- **Stacking:** a typical combination is one character LoRA, one style LoRA and one detail or concept LoRA. Add them one at a time, and lower the others' strength when you add one. Two style LoRAs fight each other. Civitai allows about 9 resources per image (checkpoint included) on a free account; the median image uses 4.
- **Embeddings** (textual inversions) only work in their own family (EasyNegative is SD 1.5 only). They are named in the prompt or the negative prompt.

## 4. Write the prompt in the family's language

### Tag models: SD 1.5, Pony V6, Illustrious, NoobAI, Anima

Write comma-separated Danbooru-style tags, the most important first. Illustrious from v1.0 on also understands short sentences. The order:

**quality tags → count (`1girl`, `2boys`, `solo`) → character and series → artist or style → look (hair, eyes, clothes) → pose, action, expression → setting and background → framing (`cowboy shot`, `from above`, `close-up`) → light**

Each family has its own quality tags. Using another family's does nothing or makes it worse:

- **Pony V6:**
  - Start with the whole string `score_9, score_8_up, score_7_up, score_6_up, score_5_up, score_4_up` (`score_9` alone is much weaker).
  - Add a source tag (`source_anime`, `source_cartoon`, `source_furry`, `source_pony`) and a rating tag (`rating_safe`, `rating_questionable`, `rating_explicit`).
  - Leave out `masterpiece`.
  - **Clip skip must be 2.** Without it you get blobs.
- **Illustrious:** `masterpiece, best quality, absurdres` (merges often document their own tags on their page; use those). Never Pony's score tags.
- **NoobAI:**
  - `masterpiece, best quality, newest, absurdres, highres`, plus a rating tag (`safe`, `sensitive`, `nsfw`, `explicit`).
  - Year tags (`newest`, `recent`, `mid`, `early`, `old`) set the drawing style's era.
  - `very awa` asks for the most aesthetic images.
- **Anima:**
  - Lowercase tags with spaces instead of underscores: `masterpiece, best quality, score_7, safe`.
  - Artist tags start with `@`.
  - Prose needs at least two sentences.
- **SD 1.5:** `masterpiece, best quality`.

Weights and length:
- **Weights** like `(red scarf:1.2)` work on these models. Use them for two or three terms at most and stay between 0.5 and 1.5: many weights cause artifacts.
- **Length:** CLIP reads the prompt in chunks of 75 tokens, so put what matters first. `BREAK` starts a new chunk, which helps keep two characters' features apart.

### Prose models: Flux, Qwen-Image, Z-Image, Chroma, HiDream, Krea 2, Pony V7

Write sentences, as if describing a photo to someone. Order: the subject first, then what it does, the setting, the light, the camera or medium, and the style and mood. For example:

> A weathered fisherman in a yellow oilskin coat mends a net on a wooden pier at dawn. Thick fog hides the harbour behind him; a single lantern lights his hands from the left with warm, soft light. Shot on 35mm film with an 85mm lens at f/2, shallow depth of field, muted blue and amber tones, quiet and melancholic.

- **Leave out tags and weights:**
  - Quality tags, score tags and `masterpiece` mean nothing to these models.
  - `(word:1.2)` weights are unreliable on their encoders and don't work at all on Krea 2.
- **Describe quality** as what you'd see instead: "sharp focus, fine skin texture, detailed fabric".
- **Text in the image:** give the exact words in quotes, early and short: `a neon sign that reads "OPEN LATE"`. Put only the words the user gave on it: no invented dates, places or programme. Offer to add them instead.
- **Camera language works:**
  - "85mm portrait lens", "wide-angle 24mm";
  - "f/1.8, blurred background" or "f/11, everything sharp";
  - "golden hour backlight", "overcast soft light", "hard flash".
- **Length:** Civitai allows up to 1,000 characters for Flux; aim for under 500. Z-Image likes long, detailed prose. Qwen-Image may end with `, Ultra HD, 4K, cinematic composition.`
- **Pony V7** mixes both: its special tags (`score_X`, `source_X`), then a factual description, then a stylistic one, then extra tags.

### For every model

- **Be concrete:** "a weathered fisherman mending a net" beats "an old man by the sea". Name colours, materials, time of day and weather.
- **No contradictions,** such as "photorealistic" next to "anime style".
- **Several people:** give the count, then describe each person in turn, with their attributes right next to them. Attributes bleed from one subject to the other, especially on CLIP models: prefer a prose model for complex scenes with several people.
- **Never write "no X" in the prompt:** it adds X. Unwanted things go into the negative prompt. On models without one, describe the state you want instead ("clean-shaven", not "no beard").
- **Rating tags** (`rating_safe` … `rating_explicit`, `safe` … `explicit`) steer how explicit an image is. Put the wanted one in the prompt; if the model drifts, put the opposite in the negative prompt.

## 5. The negative prompt

**Models that use it:** SD 1.5, SDXL, Pony, Illustrious, NoobAI, Anima, Qwen-Image, Z-Image Base, HiDream Full and Chroma.

**Models that ignore it:** Flux.1 (dev, schnell, Krea), Flux.2 Klein (distilled), Flux.2 pro, Z-Image Turbo and every model run at CFG 1. Leave it empty for them.

Keep it short and aimed at real problems; long blanket lists make images worse. Starting points:

- **SD 1.5:** `worst quality, low quality, blurry, bad anatomy, bad hands, extra fingers, watermark, text`
- **SDXL (photo):** `cartoon, illustration, painting, deformed, blurry, lowres, watermark, text`
- **Pony V6:** it rarely needs one; add only what goes wrong.
- **Illustrious:** `worst quality, low quality, lowres, bad quality, comic, multiple views, jpeg artifacts, signature, watermark`
- **NoobAI:** `worst quality, old, early, low quality, lowres, signature, username, logo, bad hands, mutated hands`
- **Anima:** `worst quality, low quality, score_1, score_2, score_3, artist name, blurry, jpeg artifacts`

Then add what you actually saw go wrong (`extra arms`, `2girls` when you wanted one).

## 6. Settings

| Family | Sampler | Steps | CFG / guidance | Clip skip |
|---|---|---|---|---|
| SD 1.5 | Euler a or DPM++ 2M Karras | 20–30 | 6–8 | 2 for anime models |
| SDXL | DPM++ 2M Karras or Euler a | 20–30 | 5–7 | 1; 2 for anime checkpoints (when the input schema has `clipSkip`) |
| SDXL Lightning, LCM, Turbo | Euler or LCM | 4–8 | 1–2 | — |
| Pony V6 | Euler a | 25 | 6–7 | **2** |
| Illustrious | Euler a | 20–28 | 5–7 | 1–2 (follow the checkpoint) |
| NoobAI (eps) | Euler a | 25–30 | 5–6 | — |
| NoobAI (v-pred) | **Euler only** | 28–35 | 4–5 | — |
| Anima | er_sde or Euler a | 30–50 (turbo 8–12) | 4–5 (turbo 1) | — |
| Flux.1 dev, Krea | Euler, simple | 20–30 | 3.5 (Krea 4.5) | — |
| Flux.1 schnell | Euler | 1–4 | 0–1 | — |
| Flux.2 Klein (distilled) | Euler | 4–8 | none / 1 | — |
| Chroma | Euler | 25–40 | 3–3.5 | — |
| Qwen-Image | Euler, simple | 20–50 | 2.5–4 | — |
| Z-Image Turbo / Base | Euler, simple | 8–12 / 20–30 | 1 / 3–5 | — |
| HiDream Full / Dev / Fast | UniPC | 50 / 28 / 16 | 5 / 0 / 0 | — |

**Sizes:**
- **SDXL and nearly every newer family (about 1 megapixel):**

  | Shape | Size |
  |---|---|
  | Square | 1024×1024 |
  | Portrait | 832×1216 or 896×1152 |
  | Landscape | 1216×832 or 1152×896 |
  | Tall | 768×1344 |
  | Wide | 1344×768 |
  | Very tall or very wide | 640×1536, 1536×640 |
- **SD 1.5:** 512×768, 768×512, 512×512.
- **Qwen-Image:** 1328×1328, 1664×928 or 928×1664.
- **Bigger than native** gives twins, extra limbs and repeated objects. Generate at a native size and upscale or use hires fix instead (on Civitai a hires-fix pass for the SD family upscales 1.5×; a denoise of 0.3 to 0.5 keeps the image, higher values change it).

**Seeds:** random for a first try. Note the seed of a result the user likes, and reuse it to change one thing at a time.

**How many:** two to four variations of a cheap model help to find a good one; one at a time for expensive ones.

## 7. With Civitai's generation tools

1. **Get the input for your models.** Have the AIRs of the checkpoint and the LoRAs (step 3), then call `get_input_schema` with `resources` set to these AIRs. You get the schema and an example input for the service they run on.
   - **Use exactly the field names of that example.** They differ between families (`model` or `checkpointModel`; `sampleMethod` and `schedule` or `sampler` and `scheduler`; `loras` as an object `{"<AIR>": 0.8}` or as a list). Unknown fields are rejected.
   - **Without specific models,** call `find_services` with a query like "anime image" or "photoreal image with text", then `get_input_schema` with the service id.
2. **Fill in the input:** prompt, negative prompt (if the family uses one), width and height, steps, CFG, sampler, seed and quantity.
3. **Check the price before expensive runs.** Large sizes, many steps, several images and some families (Flux.2, Krea 2, Wan) cost more. `run_step` with `whatif: true` returns the cost in Buzz without running anything.
   - Rough prices: SDXL at 1024×1024 and 20 steps is about 8 Buzz.
   - Cost grows with pixels × steps × quantity.
   - On Flux-type models a CFG other than 1 doubles the price.
   - The user may be asked to confirm the Buzz.
4. **Run it:** `run_step` with `stepType` `imageGen` and the `input`. Each image is saved as a file of this conversation, and the result names it (`[image saved as file "…"]`). Don't show or describe any of them yet: look at them first (section 8).
5. **When it fails:**
   - **Validation error:** read the message, which names the valid fields, fix the input and try again.
   - **Failure with the reason `blocked`:** never retry the same input. Repeated blocks get the account muted. Tell the user.
   - **A job that takes long** (video): run it without waiting (`waitForCompletion: false`) and check it with `get_workflow`.

## 8. Look at every image before you show it

Image models get things wrong often (an extra arm, two people instead of one, the lantern missing), and the prompt says nothing about what really came out. You can see your results: `read_file` with the file's name gives you the image itself, or, if your model doesn't take images, a description of it by a vision model. In that case ask about what matters: `read_file(file="…", query="How many people are there? Are hands and faces intact? Is there text, and what does it say? Does it show an elf hanging lanterns in an autumn forest?")`.

Before you show an image or say anything about how it turned out:

1. **Open every image of the run** with `read_file`.
2. **Check it against the request:** the subject, how many people, pose and action, the style, the composition, hands and faces, any text, and whatever the user asked for in particular.
3. **When an image clearly misses** (a wrong count, broken anatomy, the subject missing, unreadable text), find the cause in the table below, fix it, and run once more; keep the seed if only a setting changed. Each run may ask the user to confirm the Buzz.
4. **Show the images that pass,** placed in your answer as your instructions for files say. If none passes after the second run, show the best one, say plainly what is still wrong and what you would change, and ask before generating more.
5. **Describe only what you saw,** never what the prompt asked for. Never call an image done or say it turned out well without having looked at it.

Fix one thing at a time, and keep the seed while comparing:

| You see | Likely cause | Fix |
|---|---|---|
| Twins, duplicated objects, stretched bodies | Size above native, extreme aspect ratio | A native size, then upscale |
| Mushy or burnt images on Turbo, Lightning or LCM models | Settings of a normal model | CFG 1–2, 4–8 steps |
| Washed out, almost blank (SD models) | CFG too low | Raise CFG to 5–7 |
| Blobs and noise on Pony | Clip skip not 2 | Clip skip 2 |
| Broken output on NoobAI v-pred | Wrong sampler | Euler |
| A LoRA has no effect | Wrong AIR, wrong family, no trigger word | Check all three |
| Overcooked colours, artifacts | LoRA strength or weights too high | Lower them |
| Bad hands or faces | Common with SD models | A face-fix or hires-fix pass; `bad hands` in the negative prompt; a larger face in the frame |
| Wrong or unreadable text | Model can't write | Qwen-Image or Flux, with short text in quotes |
| The prompt is ignored | Too many terms, or a LoRA too strong | Shorter prompt, the important things first, lower LoRA strength |

**Tell the user briefly what you used** (model, LoRAs with strengths, seed, size, the main settings), so they can ask for changes or reproduce the image.

## 9. The same character in several images

- Reuse one fixed description block word for word, the same checkpoint, and the same character LoRA at the same strength. For close variations, keep the seed too.
- Models that edit with reference images (Flux.2 Klein, Qwen-Image Edit) can keep a face or an outfit from an earlier image.
- If you have the knowledge base tools, save a character's or a style's recipe as a note: the model's AIR, the LoRAs and strengths, the prompt block, the negative prompt, the seed and the settings. Then you can reproduce it in later conversations.
