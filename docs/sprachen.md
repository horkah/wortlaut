# Andere Sprachen - a blueprint

**Kurz auf Deutsch, der Rest auf Englisch.** Was zu tun ist, um wortlaut in
einer weiteren Sprache zu betreiben. Englisch geschrieben, weil wer diese
Arbeit macht, vermutlich nicht auf Deutsch arbeitet. Die Grundannahme gilt
durchgehend: **Ein Profil, eine Sprache.**

---

## One profile, one language

A speaker profile fixes one language for its entire life. The prompt corpus,
the recordings, the fine-tuned model, the evaluation and the dictation all
inherit it. A person who wants wortlaut in German and in Spanish gets two
profiles, two corpora, two models.

This falls out of what the project is for. Whisper is told the language up
front rather than detecting it, because on short utterances detection spends
part of the budget that should go to listening. Mixing two languages into one
profile would mean either detecting per utterance - giving that advantage
away - or training one adapter on two phoneme inventories from a few hundred
utterances. And WER is computed against the prompt; a corpus in two languages
produces one number that describes neither.

---

## What is in place

German (`de`) and English (`en`) are supported. **One place defines the
languages**, their labels and the default: `wortlaut/sprachen.py`
(`UNTERSTUETZT`, `VORGABE`). Everything else reads the profile.

| Language-aware | Where |
|---|---|
| Profile creation offers the supported languages, served by the backend; `de-DE` is stored as `de`, an unknown code is a 422 | `GET /api/sprachen`, `Verwaltung.svelte`, `api/speakers.py` |
| The checked access token carries the language, so every app has it without a second query | `wortlaut/zugang.py` → `Sprecherzugang.sprache` |
| Whisper adapters take the language and pass it through; base models are the multilingual checkpoints | `wortlaut/whisper/` |
| The training job records its language; trainer and evaluator read it | `services/auftraege.py` → `finetune.py`, `bewerten.py` |
| Evaluation and dictation use the speaker's language | `hoeren/services/auswertung.py`, `schreiben/backend/deps.py` |
| The chunker has a per-language measure: characters per second and the abbreviations whose full stop is no sentence end | `wortlaut/text/chunker.py` (`MASSE`) |
| The LLM instruction names the language it must write in | `wortlaut/text/llm.py` |
| OCR reads with the profile's dictionary | `wortlaut/text/ocr.py` |
| Probe sentences exist per language | `apps/hoeren/backend/api/prompts.py`, `packages/ui/Audio.svelte` |
| Server and browser voices are filtered by the profile language; without one the browser sets none | `wortlaut/vorlesen.py`, `packages/ui/speak.ts` |
| Error metrics normalise Unicode-aware | `wortlaut/metriken.py` |
| Timestamps are stored in UTC and formatted in the browser | `packages/ui/zeit.ts` |

The voice list arrives with `/api/zugang` after the first render, so it has to
be `$derived`; a `$state` initialised once keeps the unfiltered list.

---

## Adding a language

For a new language, in this order - each step makes the next testable:

1. **Add the code** to `sprachen.UNTERSTUETZT`. Profile form, job,
   evaluation and dictation follow.
2. **A voice.** `scripts/vorlesen.py --hole <voice>` and a label in
   `vorlesen.PiperMotor.BESCHREIBUNG`. Synthesize a sentence with the
   language's awkward sounds, listen, and read it back through Whisper. A
   `Missing phoneme from id map` on stderr is not necessarily a fault: current
   espeak-ng emits some letters decomposed, and smaller models were trained
   through the same loss - "repairing" it made German voices worse (see the
   comment in `vorlesen.py`). Turkish, Czech or Vietnamese can hit the same.
3. **Chunker measure** in `chunker.MASSE`: characters per second and
   abbreviations. It affects prompt length only; approximately right is
   enough.
4. **Probe sentences** in `prompts.PROBESAETZE` and `Audio.svelte`, and the
   Tesseract dictionary (`tesseract-ocr-<lang>` in the `Dockerfile`).
5. **A first prompt text**, generated or uploaded. Good prompts - idiomatic,
   common vocabulary, phonetically varied - are editorial work in every
   language; budget time for a native speaker to review them.
6. **Create a profile, record ten utterances, run the baseline evaluation.
   Stop and read the number.** The cheapest honest answer to whether the
   language is viable.
7. **Translate the interface** (below).

### Still German

* **The interface.** 35 Svelte files, roughly 8,700 lines, no i18n
  scaffolding; every string is a German literal. The mechanical part -
  extract, catalogue, store - is known. What costs is that this German is
  written, not generated; decide early whether the other language gets the
  same voice or a plainer one. **Leave the wire format alone**: German nouns
  in routes and fields are the internal vocabulary.
* **Number formatting on the server.** `_zahl` in
  `apps/lernen/backend/api/laeufe.py` writes decimal commas; send numbers and
  format them in the browser. The browser side is collected in
  `ANZEIGE_GEBIET` (`packages/ui/sprache.ts`) - deliberately the interface
  locale, not the profile language: a Spanish profile on a German interface
  is read aloud in Spanish, with German decimals in the table.
* **Legacy encodings.** `text/upload.py` falls back to Latin-1 for non-UTF-8
  files - a German guess that mangles Greek, Cyrillic or Turkish legacy files.
  Detect the encoding or refuse non-UTF-8.
* **Punctuation.** The chunker's sentence and clause patterns fit Latin and
  Cyrillic, not `。`, `؟`, `،`, the Greek `;`, Armenian or Ethiopic.

---

## What is genuinely hard

**Prompt corpora worth recording.** A person with dysarthria records a few
hundred utterances, once, and it is tiring. They have to cover the language's
sounds well enough for the fine-tune to generalise. That needs a native
speaker in the loop - a staffing problem, not an engineering one.

**Dysarthria in a low-resource language.** The effects multiply: a worse
baseline, and the same few hundred utterances to close a larger gap. Below
Tier 1, run the baseline evaluation before promising anything.

**Word error rate without spaces.** Chinese, Japanese, Thai, Lao, Khmer,
Burmese and Cantonese have no word boundaries. WER, MER and WIL split on
whitespace and become meaningless; CER stays valid. It needs a per-language
tokeniser or CER-only scoring, and `genauigkeit()` and everything built on it
would follow.

**Right-to-left scripts.** Arabic, Hebrew, Persian, Urdu, Pashto, Sindhi and
Yiddish need `dir="rtl"` and mirrored layout, with care where text and numbers
mix - the prompt display in „hören" and the segment list in „schreiben". The
CSS does not anticipate this.

**Model size.** German works from `whisper-small`. For a language Whisper knows
less well, the smallest usable checkpoint may be `medium` or `large-v3` - GPU
memory, training time and the shared card change with it.

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
fine-tuning.

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
| No word boundaries | `zh`, `yue`, `ja`, `th`, `lo`, `km`, `my`, `bo` | WER/MER/WIL invalid; score on CER only |
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
