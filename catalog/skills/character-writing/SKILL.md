---
name: character-writing
description: Builds characters for stories, roleplay and worldbuilding together with the user, and plays them convincingly. It covers their core (what they want, what they need, the lie they believe and the wound behind it), flaws with consequences, voice, relationships and arc. It writes them up as a profile or as a roleplay character card (description, personality, scenario, first message, example dialogue). Use when the user wants to create, flesh out, revise or play a character, a side character, an NPC or an agent's persona, or says a character feels flat, generic or out of character.
---

# Character writing

A character is not a list of adjectives. A character is what they want, what they believe about the world, and what they do when it costs them something. Build that core first; looks, quirks and backstory only matter where they serve it.

## 1. Ask first, briefly

Before building, find out what the character is for. Ask at most four or five questions in one message, and offer a default or two options for each, so the user can just say "go":

- **Purpose:** a character in the user's story, a roleplay partner, an NPC for a game, a persona for an agent? What is their role towards the user's own character?
- **Genre and tone:** setting, era, how dark or light, what the user wants to see more or less of.
- **What's already fixed:** a name, a look, a scene the user has in mind, a relationship.
- **Output:** a profile to work with, a character card for roleplay, or straight into a scene.

If the user gives you little, don't interrogate them: make bold choices, say what you chose, and offer to change any of it.

## 2. Build the core

- **Want:** something concrete and external they are after right now (to win the tournament, to get her brother out of prison, to be left alone).
- **Need:** what they actually have to realise or change, usually something inner (that she can't save him alone, that being left alone is not the same as being safe).
- **The lie:** a false belief that keeps the want and the need apart ("people only stay if you're useful to them"). The arc is the lie being tested.
- **The wound:** the event that made the lie feel true. Backstory belongs in the character only where it explains how they act now; cut the rest or keep it as a secret.
- **A contradiction:** two traits that pull against each other (gentle with animals, cruel when humiliated; a careful planner who gambles). Contradictions are what make a character surprising and still believable.
- **Flaws that cost something:** a real flaw makes them lose things in the story: friends, chances, fights. "Cares too much" and "too honest" are not flaws. Check for a Mary Sue: does the world bend to spare them, are they good at everything, does everyone like them? Then give them earned skills with clear limits, and let them fail.
- **Proactivity, relatability, capability:** a strong character is high on one, medium on another and low on the third, and the arc moves these. A character who acts on their own, rather than waiting for things to happen, carries a scene even when they're unlikeable.
- **Under pressure:** decide what they do when cornered, when they lose, when someone they love is threatened, when they're tempted. Choices under pressure reveal the character; put such moments into scenes.
- **Side characters may be flat on purpose:** one vivid trait, one want and one function in the story is enough. Not everyone needs a wound.

## 3. Voice

How they talk is how the reader (and the model playing them) knows them:

- **Sentence shape:** short and blunt, long and winding, questions instead of statements, trailing off.
- **Words:** what they always say, what they would never say, how formal they are, slang or jargon of their world. Use a dialect or verbal tic lightly; a little goes a long way.
- **What they avoid:** the topics they deflect, and how (a joke, anger, changing the subject).
- **Sample lines:** write three to five lines in different moods (calm, angry, lying, tender, scared). They pin the voice down better than any description.

## 4. Relationships and arc

- **Towards the user's character:** what do they want from them, what do they hide from them, what would make them trust or betray them?
- **Two or three other relationships** with tension in them: a rival, a debt, someone they failed.
- **The arc:** positive (they give up the lie), negative (they cling to it and lose), or flat (they already know the truth and change the people around them). Note what may change during the story and what must stay fixed (their name, their past, how they look).

## 5. Avoid the defaults

Language models reach for the same choices again and again. Avoid them on purpose:

- **Names:** not Elara, Lyra, Kael, Seraphina, Aria, Thorne, Voss, Silas or Marcus Chen. Pick names that fit the culture, era and class of the character. Offer three options for an important name.
- **Traits:** not "fiercely independent", "a mysterious past", "a heart of gold", "piercing eyes" or "sarcastic but secretly caring". Replace each with a specific detail that shows it.
- **For the key choices** (the want, the lie, the contradiction, the look), think of three clearly different options and take the least obvious one that still fits. A trope is fine when it's chosen; twist one part of it.

## 6. Writing it up

### As a profile (stories, worldbuilding)

```
Name, age, role in the story
Look: three concrete details, at least one that says something about them
Want / Need / Lie / Wound
Contradiction
Flaw, and what it costs them
Skills and their limits
Voice: how they talk + 3 to 5 sample lines
Relationships: to the user's character, and 2 or 3 others
Arc: where they start, where they could end
Secrets, and hooks for scenes
```

### As a character card (roleplay)

Cards follow the Character Card V2/V3 format (SillyTavern and others): `description`, `personality`, `scenario`, `first_mes` (the first message), `mes_example` (example dialogue), and optionally `system_prompt` and `post_history_instructions`. How to write them:

- **Plain prose,** in the third person, organised under short headings. Don't use W++ or other pseudo-code formats: models read prose better, and it costs fewer tokens.
- **Size:** description, personality and scenario are sent with every message. Keep them to about 400 to 1,000 tokens together; a whole scenario with several characters may need more.
- **Show behaviour, not labels.** Not "she is jealous", but "when her sister gets praise, she finds something wrong with it, then feels ashamed and overcompensates". Models miss subtext, so spell out what each flaw looks like in action.
- **The model copies words, not meanings.** The words you choose pull the writing: "dominant" plays differently from "assertive", "witty" differently from "sarcastic". Don't mention what you don't want ("she never talks about the war" makes the war come up): describe what she does instead.
- **Permanent and temporary:** what is always true goes in the description. Things that change (where they are, their mood, what just happened) go in the scenario or the first message, or they will show up in every scene.
- **The most important traits last:** what comes at the end of the description weighs more with the model.
- **First message:** it sets the style, length and point of view of the whole roleplay more than anything else. Write it the way the replies should be: one point of view, one tense, a scene with a direction. Never let it act, speak or feel for the user's character. End on something the user can react to, not a question.
- **Example dialogue:** two to four short exchanges that show different sides of the character (with `<START>` between them and `{{char}}` and `{{user}}` as names). They teach the voice better than descriptions.
- **Keep the parts apart:** instructions on how to write belong in the system prompt, not the card. The user's own character goes in the user's persona, not the card.

### As an agent in this app

An admin can make the character an agent on the Agents page. The agent's prompt then holds the character in prose (who they are, how they talk, the situation), followed by a few rules for playing them (see the next section). Example lines go into the prompt as well, since agents have no example dialogue field.

## 7. Playing a character

When you play a character yourself:

- **Speak and act from their want and their fear,** not from an assistant's wish to help. A character can refuse, lie, be wrong, keep a grudge or want something the user doesn't.
- **Resist the drift towards niceness.** Language models soften villains and turn conflict into hugs; it's a measured effect. Antagonists stay antagonists, and cold characters warm up slowly and for a reason. Malice can be quiet and clever rather than loud.
- **Never write the user's character:** not their actions, their words or their feelings. Describe what your characters do and leave the reaction to the user.
- **Move the scene.** Every reply should change something: new information, a decision, a complication, a cost.
- **Stay consistent.** What has been established about a character (names, scars, history, how they talk) stays true. In a long conversation, look at the profile or card again before an important scene.
- **Out of character:** when the user steps out of the story (OOC, brackets), answer briefly as yourself, then go back in.

## 8. Keep it

If you have the knowledge base tools, save a finished character as a note of its own (the profile or card), with a line in your memory that points to it, so the character stays the same in later conversations. When the character changes during the story, update the note.

## Checklist

- Do they want something concrete, and is something inner in the way?
- Does a flaw cost them something in the story?
- Is there one contradiction?
- Can you hear their voice in the sample lines?
- Did you replace every default name and stock trait with something specific?
- For a card: prose, behaviour instead of labels, nothing unwanted mentioned, a first message that never acts for the user?
