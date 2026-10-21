# Personalize your journal

Run these commands from the deployment checkout: the directory whose Compose
file starts your running containers. A separate source checkout is not the live
deployment. Start both services and finish model/web-tool setup first.

## Let Hermes set it up

```bash
./quietlight.sh personalize
```

This opens an interactive terminal conversation. For example:

> I build software for small businesses. Follow practical advances in software
> engineering, accessibility, and cybersecurity. I know programming but want
> unfamiliar concepts explained. Give me five useful stories, not launch hype.

Hermes reads the current settings, asks a few questions, and proposes a brief.
After you approve, it saves through the same validated API as the website.
It preserves the schedule unless you ask to change it. Existing private settings
are sent to your model provider during this conversation.

For subsequent changes, rerun `personalize` and say something like “Keep my
topics, but focus on open-source tools and reduce the briefing to four stories.”
Interactive terminal/tool approvals still apply. If Hermes cannot apply a change,
use the file workflow below; it should not claim success without a successful save.

## Use any LLM

Copy this prompt into your preferred assistant, along with the JSON below:

```text
Help me configure a QuietLight research journal. Ask me one short round of
questions about my interests, intended use, background, preferred depth, sources
to favour or avoid, and briefing length. Propose reasonable defaults for anything
I skip. Then return a complete JSON object using exactly the supplied keys.

Make prompt a useful editorial brief: what to research, what each story should
explain, evidence standards, language/depth, and what to omit. Make topics focused.
Use sources only for sources I request or you can confidently identify; an empty
list lets the researcher choose primary sources. Do not invent URLs.

Constraints: prompt 10–12000 characters; topics, sources, and exclude are arrays
of at most 40 strings of at most 2000 characters each; maximum_items is an integer
1–12; lookback_days is an integer 1–30. schedule.enabled is a boolean and
schedule.time is HH:MM in Europe/London. schedule.cadence is daily, weekdays, or
weekly; schedule.weekday is an integer 0 (Sunday) through 6 (Saturday), used for
weekly schedules. Leave scheduling disabled on first setup.
For an update, preserve existing settings I did not ask to change, including the
schedule. Do not include passwords, API keys, private file paths, or extra fields.
Return valid JSON without comments, ready to save as settings.draft.json.
```

Starter JSON (also available in `research/settings.example.json`):

```json
{
  "prompt": "Prepare a concise briefing on science and technology. Explain what changed, the evidence, why it matters, and practical implications. Define unfamiliar terms, cite primary sources, distinguish preprints from reviewed work, and avoid hype. Quiet days should be short.",
  "topics": ["Science and technology developments with practical implications"],
  "sources": [],
  "exclude": ["Rumours, unsupported promotional claims, and repetitive coverage"],
  "maximum_items": 6,
  "lookback_days": 3,
  "schedule": {"enabled": false, "time": "08:00", "cadence": "daily", "weekday": 1}
}
```

Save the returned JSON as `data/research/settings.draft.json`, review it, then run:

```bash
./quietlight.sh configure data/research/settings.draft.json
./quietlight.sh generate
```

`configure` replaces the editable research settings and schedule with the supplied
values. It validates them before saving and does not start a research run. To
update an existing setup, first run `./quietlight.sh preferences` and give that
JSON to the assistant instead of the starter. This output contains your private
interests: share it only with a provider you trust. Keep drafts under ignored `data/`.

After reviewing the edition, optionally enable daily research:

```bash
./quietlight.sh schedule 08:00
./quietlight.sh schedule off
```

The last command pauses it again; use whichever action you want. The machine must
be awake and Docker running. Scheduling uses Europe/London, not an inferred local
timezone. Neither personalization nor setup starts paid research automatically.

## Where settings live

The journal writes the brief, topics, filters, and limits to
`data/research/profile.json`, and timing to the original topic's entry in
`data/research/journal/topics.json`, under the deployment directory. The old
`journal/schedule.json` remains a migration fallback for topics not yet edited.
These are private runtime files, excluded from Git.
The helpers authenticate internally; you do not need to find or paste an access
key. Provider credentials remain configured separately through `./quietlight.sh setup`.
