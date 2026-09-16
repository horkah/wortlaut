# Andere Sprachen - a blueprint

**Kurz auf Deutsch, der Rest auf Englisch.** Diese Notiz beschreibt, was zu tun
ist, um wortlaut in einer anderen Sprache als Deutsch zu betreiben - Spanisch
und Englisch sind die naheliegenden ersten Fälle. Sie ist bewusst englisch
geschrieben, anders als alles übrige hier: Wer diese Arbeit macht, arbeitet
vermutlich nicht auf Deutsch, und eine Anleitung zum Übersetzen sollte nicht
selbst erst übersetzt werden müssen.

Die Grundannahme steht am Anfang und gilt durchgehend: **Ein Profil, eine
Sprache.** Wer wortlaut in zwei Sprachen nutzen will, bekommt zwei Profile. Das
ist keine Einschränkung, die wegverhandelt werden sollte - siehe
[One profile, one language](#one-profile-one-language).

---

## One profile, one language

A speaker profile fixes one language for its entire life. Everything hanging
off the profile inherits it: the prompt corpus, the recordings, the fine-tuned
model, the evaluation, the dictation. A person who wants wortlaut in German and
in Spanish gets two profiles, two corpora, two models.

This is not a simplification to be undone later. It falls out of what the
project is for. A fine-tune is a model that has learned *this one person's*
speech; Whisper is told the language up front rather than guessing it
(`training/finetune.py:349`), because on short utterances a model that has to
detect the language first spends part of its budget on that instead of on
listening. Mixing two languages into one profile would mean either detecting
per utterance — giving away exactly the advantage — or training one adapter on
two phoneme inventories with a few hundred utterances, which is a good way to
get a model that is worse at both.

It also keeps the corpus honest. WER is computed against the prompt; a corpus
with two languages in it produces one number that describes neither.

The column already exists. `Sprecher.sprache` is in the schema
(`apps/hoeren/backend/db/models.py:30`), the create endpoint accepts it
(`apps/hoeren/backend/api/speakers.py:29`), the datasheet prints it
(`services/export.py:146`), and three of the four views display it. What is
missing is everything that should *read* it.

---

## What already works

More than you would expect. The language is threaded through the recognition
path already; it is the surrounding machinery that assumes German.

| Already language-agnostic | Where |
|---|---|
| Whisper adapters take a language argument and pass it straight through | `wortlaut/whisper/__init__.py:35`, `local.py:120`, `remote.py:20` |
| Base models are the **multilingual** checkpoints, not the `.en` variants | `whisper-small`, `whisper-medium`, `whisper-large-v3` (`apps/lernen/backend/config.py:68`) |
| Evaluation in „hören" reads the speaker's language and uses it | `apps/hoeren/backend/api/auswertung.py:309` → `services/auswertung.py:254` |
| Error metrics normalise Unicode-aware (`\w` with `re.UNICODE`) | `wortlaut/metriken.py` |
| The TTS engine interface knows nothing about German | `wortlaut/vorlesen.py` — the voice key is `<engine>/<locale>-<voice>-<quality>` |
| Piper voice downloads parse any locale out of the voice name | `scripts/vorlesen.py:_pfadteile` |
| Timestamps are stored in UTC and formatted client-side | `packages/ui/zeit.ts` |
| The corpus layout is per speaker, so two profiles never collide | Grundentscheidung 6 |

So the recogniser, the trainer and the storage layer are ready. The work is in
the layers above and beside them.

---

## What has to change

Ordered roughly by effort. File references are the starting points, not an
exhaustive diff.

### 1. Let someone actually choose the language — trivial

The API accepts `sprache`; the UI never sends it. `sprecherAnlegen` takes
`{ name, basismodell }` (`apps/hoeren/frontend/src/lib/api.ts:90`) and
`Verwaltung.svelte:65` calls it with exactly those two. Every profile ever
created on this server is therefore `de`, whatever the docs say —
`docs/hoeren.md` already claims the creation form asks for a language, and it
does not.

Add the field to the form, the type and the call. Offer a short curated list,
not all hundred codes: the languages this installation has prompts and a voice
for.

### 2. Carry the language into the training job — small, and load-bearing

`finetune.py:352` and `bewerten.py:246` both read `auftrag.get("sprache") or
"de"`. Nothing ever writes that key. `auftraege.Auftrag`
(`apps/lernen/backend/services/auftraege.py:57`) has no such field, and
`api/laeufe.py:1004` constructs the job without one.

The consequence is not subtle. A Spanish profile would train with German forced
decoder tokens (`modell.generation_config.language = sprache`,
`finetune.py:367`) and be evaluated as German. The model would emit German
spellings of Spanish sounds and the WER would be garbage — and nothing anywhere
would report an error.

Add `sprache` to `Auftrag`, fill it from the speaker profile at job creation,
and it flows to both the trainer and the evaluator, which already read it.
This is a handful of lines and it is the single most important one in this
list.

### 3. Make „schreiben" ask the speaker, not the config — small

Dictation uses a server-wide setting: `Einstellungen.sprache = "de"`
(`apps/schreiben/backend/config.py:71`), passed at `api/segments.py:54` and
`:104`. With one language per profile this is wrong by construction as soon as
a second language exists on the server.

The speaker id is already in hand at both call sites. Two options:

* Look the speaker up, the way `tempo_fuer` already looks up a model state
  (`apps/schreiben/backend/deps.py:141`).
* Better: put the language in the released model's manifest, next to the tempo
  factor that already lives there. Then „schreiben" needs no access to
  „hören"'s corpus database, which keeps the app boundary intact — and a model
  state carries the language it was trained for, which is the truthful place
  for it.

Keep `WORTLAUT_SPRACHE` as the fallback for a speaker with no model yet.

### 4. Retune the chunker — medium, and genuinely per-language

`wortlaut/text/chunker.py` cuts prompt text into 3–12 second speakable units.
Three things in it are German:

* `ZEICHEN_PRO_SEKUNDE = 13.0` — characters per second of clear reading. This
  is a property of the language's orthography, not a universal. Spanish runs
  faster per character, English is somewhere near German, and for Chinese or
  Japanese a character is a whole syllable or morpheme, so the constant is off
  by a factor of several.
* `_ABKUERZUNG` — a regex of German abbreviations (`z. B.`, `bzw.`, `Abb.`)
  whose full stop is not a sentence end.
* `_SATZENDE` and `_TEILSATZ` — fine for Latin and Cyrillic punctuation, wrong
  for Chinese/Japanese full stops (`。`), Arabic (`؟`, `،`), Greek question
  marks (`;`), Armenian, Ethiopic.

Turn the three into a per-language table with German as one entry. For any
language without spaces the unit-length estimate needs a different basis
entirely — see the restrictions table at the end.

This affects prompt length only, not scoring, so a rough value is tolerable and
a missing one is not fatal. Get it approximately right and move on.

### 5. Parametrise the prompt generator — trivial, plus editorial work

`wortlaut/text/llm.py:15` hard-codes a German system instruction
(„Du schreibst deutsche Vorlesetexte…"). `Auftrag` carries topic, age range and
length but no language.

Adding the language to the instruction is a five-line change. Producing prompts
that are actually *good* in the target language is not a code problem: the
sentences have to be idiomatic, common-vocabulary, and phonetically varied
enough to be worth recording. Budget real time for reviewing what the model
writes, in every language you add.

The upload route (`text/upload.py`) needs one fix: the Latin-1 fallback at
line 52 is a German-specific guess and will silently mangle Greek, Cyrillic or
Turkish legacy files. Either detect the encoding or refuse non-UTF-8.

### 6. Voices — medium, and the catalogue decides for you

Server-side TTS is the good path and it is already language-agnostic in
structure. What is German is the label table (`vorlesen.PiperMotor.BESCHREIBUNG`)
and the known-voices list in `scripts/vorlesen.py`.

Piper's catalogue covers **52 language families**. English has 38 voices and
Spanish 9, and both reach `high` quality — better coverage than German, which
has exactly one `high` voice. So for the two languages in the question, this
step is: run `--hole`, add a label, done.

Two traps:

* **The phoneme-table mismatch is not German-specific.** The repair in
  `vorlesen._zusammengesetzt` exists because current espeak-ng emits `ç`
  decomposed while older models only list the precomposed form. The same class
  of mismatch will hit other languages with precomposed letters — Turkish,
  Czech, Vietnamese, anything with stacked diacritics. When adding a voice,
  synthesize a sentence that exercises the language's awkward sounds and check
  stderr for `Missing phoneme from id map`. Silence there is the test.
* **Browser fallback defaults to German.** `packages/ui/speak.ts` defaults to
  `'de'` in `stimmen()` and `stimmeVerfuegbar()`, and `sprich()` falls back to
  `'de-DE'` (line 88). `Einstellungen.svelte:57` calls `stimmen()` with no
  argument, so the device-voice list is always filtered to German. Thread the
  profile language through. While you are there: server voices are currently
  offered unfiltered, so a German voice shows up for a Spanish profile.

Both probe sentences are German and need a per-language equivalent:
`PROBESATZ` (`apps/hoeren/backend/api/prompts.py:126`) and `PROBE`
(`packages/ui/Einstellungen.svelte:39`).

### 7. Translate the interface — the big one

35 Svelte files, roughly 8,700 lines, and **no i18n scaffolding of any kind**.
Every string is a German literal in markup. Two locale-specific formatters sit
beside them, and both are helpfully single-source:

* `packages/ui/zeit.ts` — `14.09.2026, 14:38`. Already documented as the only
  place that formats a timestamp for humans. Swap for `Intl.DateTimeFormat`.
* `_zahl` (`apps/lernen/backend/api/laeufe.py:677`) — decimal comma. This one
  formats on the *server*, which is the wrong side for a locale decision; the
  same argument the project already made for timestamps applies. Send numbers
  and format them in the browser.

The mechanical part — extract strings, add a catalogue, wire a store — is a
known quantity. The part that will actually cost you is that this project's
German is *written*, not generated: it argues, it uses em-dashes and
subordinate clauses, it addresses the reader. Translating it into flat UI
English loses something real, and translating it well is a writing job, not a
string swap. Decide early whether the other language gets the same voice or a
plainer one, and say so in the style guide, because otherwise every contributor
will decide differently.

Two smaller notes while translating: several error messages name German
concepts that only make sense with the German UI, and the API itself uses
German nouns on the wire (`sprache`, `basismodell`, `vorlage`) and in its route
names. **Leave the wire format alone.** It is the project's internal vocabulary,
it is consistent, and renaming it would touch every file for no user-visible
gain.

---

## What is genuinely hard

Everything above is bounded work. These are not.

**Prompt corpora that are worth recording.** A person with dysarthria will
record a few hundred utterances, once, and it is tiring. Those utterances have
to cover the language's sounds well enough that a fine-tune generalises. In
German this was solved by having someone read and judge the text. There is no
shortcut in a language you do not speak — you need a native speaker in the
loop, and that is a staffing problem rather than an engineering one.

**Dysarthria in a low-resource language.** The two effects multiply. Whisper's
baseline for, say, Telugu is already far worse than for Spanish; a speaker with
impaired articulation starts from that worse baseline, and the fine-tune has to
close a much larger gap with the same few hundred utterances. For anything
below Tier 1 in the table, run the baseline evaluation in „hören" *before*
promising anyone that this will work. The evaluation exists precisely so that
this question can be answered with a number instead of a hope.

**Word error rate in languages without spaces.** Chinese, Japanese, Thai, Lao,
Khmer, Burmese and Cantonese have no word boundaries in the orthography. WER,
MER and WIL as computed in `metriken.py` split on whitespace and become
meaningless — typically reporting near-100% error for a perfect transcript. CER
stays valid. This is not a bug to fix in an afternoon: it needs either a
per-language tokeniser or a decision to score those languages on CER alone,
and the composite `genauigkeit()` and every chart and threshold built on it
would have to follow. Until then, treat those languages as CER-only and say so
in the UI.

**Right-to-left scripts.** Arabic, Hebrew, Persian, Urdu, Pashto, Sindhi and
Yiddish need `dir="rtl"`, mirrored layout, and care wherever text and numbers
mix — the prompt display in „hören" and the segment editor in „schreiben" are
the exposed places. Nothing in the current CSS anticipates this.

**Model size.** German works acceptably from `whisper-small`. For a language
Whisper knows less well, the smallest checkpoint that still produces usable
text may be `medium` or `large-v3` — which changes GPU memory, training time
and the shared-card arithmetic in `compose.yaml`. Check this before planning
capacity, not after.

---

## Order of work

For a new language, in this order, because each step makes the next one
testable:

1. Add `sprache` to `Auftrag` and fill it at job creation *(§2)*. Without this
   nothing downstream can be trusted.
2. Add the language picker to profile creation *(§1)*.
3. Download a Piper voice, add its label, verify no missing phonemes *(§6)*.
4. Set the chunker constants for the language *(§4)*.
5. Parametrise the LLM instruction; write or upload a first prompt text *(§5)*.
6. Create a profile, record ten utterances, run the baseline evaluation. **Stop
   here and read the number.** This is the cheapest honest answer to whether
   the language is viable at all.
7. Point „schreiben" at the profile's language *(§3)*.
8. Translate the interface *(§7)*.

Steps 1–6 are a few days. Step 8 is the project.

---

## Languages Whisper supports

All 100 codes below are accepted by the tokenizer shipped in this image
(`faster_whisper.tokenizer._LANGUAGE_CODES`; Cantonese `yue` was added with
large-v3). Accepted is not the same as usable.

The tiers are **approximate** and follow the per-language Fleurs evaluation in
the Whisper paper. Treat them as a planning aid, not a specification — and note
that for wortlaut the base model's error rate is the *starting point*, not the
result: the whole purpose of the project is to improve on it for one speaker.
The „Voice" column is Piper's best available quality for that language, which
decides whether prompts can be read aloud from the server or fall back to
whatever the browser offers.

### Tier 1 — Whisper is reliable here

Large share of the training data; the base model is usable before any
fine-tuning. Both languages in the original question are here, both with
`high`-quality voices.

| Language | Code | Voice |
|---|---|---|
| Afrikaans | `af` | — |
| Bosnian | `bs` | — |
| Bulgarian | `bg` | medium |
| Cantonese | `yue` | — |
| Catalan | `ca` | medium |
| Chinese | `zh` | medium |
| Croatian | `hr` | — |
| Czech | `cs` | medium |
| Danish | `da` | medium |
| Dutch | `nl` | medium |
| English | `en` | **high** |
| Finnish | `fi` | medium |
| French | `fr` | medium |
| Galician | `gl` | — |
| German | `de` | **high** |
| Greek | `el` | medium |
| Hebrew | `he` | medium |
| Hungarian | `hu` | medium |
| Indonesian | `id` | medium |
| Italian | `it` | **high** |
| Japanese | `ja` | medium |
| Korean | `ko` | medium |
| Macedonian | `mk` | — |
| Malay | `ms` | — |
| Norwegian | `no` | medium |
| Nynorsk | `nn` | — |
| Polish | `pl` | **high** |
| Portuguese | `pt` | medium |
| Romanian | `ro` | medium |
| Russian | `ru` | medium |
| Slovak | `sk` | medium |
| Spanish | `es` | **high** |
| Swedish | `sv` | medium |
| Tagalog | `tl` | — |
| Thai | `th` | medium |
| Turkish | `tr` | medium |
| Ukrainian | `uk` | **high** |
| Vietnamese | `vi` | medium |

### Tier 2 — usable, with noticeably higher error

Expect a worse baseline and a larger gap for the fine-tune to close. Run the
evaluation before committing to a speaker.

| Language | Code | Voice |
|---|---|---|
| Albanian | `sq` | medium |
| Arabic | `ar` | medium |
| Armenian | `hy` | medium |
| Azerbaijani | `az` | — |
| Bashkir | `ba` | — |
| Basque | `eu` | medium |
| Belarusian | `be` | — |
| Bengali | `bn` | medium |
| Estonian | `et` | medium |
| Faroese | `fo` | — |
| Georgian | `ka` | medium |
| Hindi | `hi` | medium |
| Icelandic | `is` | medium |
| Javanese | `jw` | — |
| Kannada | `kn` | — |
| Kazakh | `kk` | **high** |
| Latin | `la` | — |
| Latvian | `lv` | medium |
| Lithuanian | `lt` | — |
| Luxembourgish | `lb` | medium |
| Maltese | `mt` | — |
| Maori | `mi` | — |
| Marathi | `mr` | medium |
| Mongolian | `mn` | — |
| Nepali | `ne` | medium |
| Occitan | `oc` | — |
| Persian | `fa` | medium |
| Punjabi | `pa` | — |
| Serbian | `sr` | medium |
| Sindhi | `sd` | — |
| Slovenian | `sl` | medium |
| Sundanese | `su` | — |
| Swahili | `sw` | medium |
| Tamil | `ta` | — |
| Tatar | `tt` | — |
| Telugu | `te` | medium |
| Urdu | `ur` | medium |
| Uzbek | `uz` | — |
| Welsh | `cy` | medium |
| Yiddish | `yi` | — |

### Tier 3 — experimental

Whisper's reported error rates here range from poor to worse than useless; on
Fleurs, large-v3 is measured at roughly 90% WER for Pashto and *above* 100% for
Malayalam and Assamese, meaning the output contains more errors than the
reference contains words. Do not promise a speaker anything in these languages
without measuring first, and expect the fine-tune to be doing most of the work
rather than refining a decent baseline.

| Language | Code | Voice |
|---|---|---|
| Amharic | `am` | — |
| Assamese | `as` | — |
| Breton | `br` | — |
| Gujarati | `gu` | — |
| Haitian Creole | `ht` | — |
| Hausa | `ha` | — |
| Hawaiian | `haw` | — |
| Khmer | `km` | — |
| Lao | `lo` | — |
| Lingala | `ln` | — |
| Malagasy | `mg` | — |
| Malayalam | `ml` | medium |
| Myanmar | `my` | — |
| Pashto | `ps` | — |
| Sanskrit | `sa` | — |
| Shona | `sn` | — |
| Sinhala | `si` | — |
| Somali | `so` | — |
| Tajik | `tg` | — |
| Tibetan | `bo` | — |
| Turkmen | `tk` | — |
| Yoruba | `yo` | — |

### Cross-cutting restrictions

These apply regardless of tier and are properties of the writing system, not of
Whisper's accuracy.

| Restriction | Languages | Consequence |
|---|---|---|
| No word boundaries | `zh`, `yue`, `ja`, `th`, `lo`, `km`, `my`, `bo` | WER/MER/WIL invalid; score on CER only *(see above)* |
| Right-to-left script | `ar`, `he`, `fa`, `ur`, `ps`, `sd`, `yi` | UI needs `dir="rtl"` and mirrored layout |
| Non-Latin punctuation | `zh`, `ja`, `ar`, `el`, `hy`, `am`, `th` | Chunker sentence/clause regexes need per-language sets |
| No Piper voice | 49 of the 100 | Prompts fall back to the browser voice — on iOS that is the compact system voice only *(see `packages/ui/speak.ts`)* |
| Character-per-second estimate meaningless | `zh`, `yue`, `ja`, `th`, `km`, `my` | Chunker unit length needs a different basis than `len(text)` |

---

Sources for the tiering: the per-language evaluation in
[Robust Speech Recognition via Large-Scale Weak Supervision](https://arxiv.org/abs/2212.04356)
and the language breakdown in the
[openai/whisper](https://github.com/openai/whisper) repository. Voice coverage
computed from the [rhasspy/piper-voices](https://huggingface.co/rhasspy/piper-voices)
catalogue, September 2026.
