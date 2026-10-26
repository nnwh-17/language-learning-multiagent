# Agents

Each agent is a PydanticAI `Agent` in [src/jplearn/agents/](../src/jplearn/agents/) with a
typed output model, its own instructions (`INSTRUCTIONS` at the top of the file) and a few
tools. The orchestrator decides which one to use from the tool descriptions in its own
`INSTRUCTIONS`.

| Agent (node id) | Orchestrator tool | Its tools | Returns |
|---|---|---|---|
| Orchestrator (`orchestrator`) | the UI runs it | all tools in this column | `OrchestratorReply`, or `DeferredToolRequests` for approvals |
| Analyzer (`analyzer`) | `analyze_japanese` | `tokenize_japanese` (Sudachi + JMdict) | `Breakdown` |
| Explainer (`explainer`) | `explain_concept` | `lookup_word` (JMdict) | `Explanation` |
| Flashcard agent (`flashcards`) | `draft_flashcards` | `break_down` (runs the Analyzer), `findNotes` (Anki, read-only) | `CardDraft` |
| Example sentences (`examples`) | `generate_examples` | `lookup_word` (JMdict), plus an output check | `ExampleSet` |
| Researcher (`researcher`) | `find_material` | `search_web` (DuckDuckGo), `fetch_page` | `Material` |

The orchestrator also has `lookup_word` (JMdict) for quick "what does X mean" questions, and
the two Anki write tools that need approval: `add_flashcards` and `add_examples_to_card`.

## Orchestrator

[orchestrator.py](../src/jplearn/agents/orchestrator.py). Plans each request, delegates, and
writes the reply the user sees.

- `OrchestratorReply.plan` is shown to the user, so it is written in plain words.
- Replies add furigana in brackets the first time a kanji appears; the web UI renders it
  above the kanji.
- Also defines the helpers the UIs share: `tools_used()`, `describe_approval()` and
  `stream_reply()`.

## Analyzer

[analyzer.py](../src/jplearn/agents/analyzer.py). Word-by-word breakdown of Japanese text:
translation, each word's reading, dictionary form and meaning, and grammar points.

- It must call `tokenize_japanese` first and use its readings and parts of speech instead of
  guessing. Content words (nouns, verbs, adjectives...) come with their JMdict meanings.
- Sudachi splits conjugations into pieces (食べ + たかっ + た); the agent merges them back
  into one word and explains the pieces in `note`.
- The Flashcard agent reuses it through `break_down`.

## Explainer

[explainer.py](../src/jplearn/agents/explainer.py). Answers "why / how / what's the
difference" questions so that the idea clicks.

- `Explanation` holds the core idea, one or two analogies (each with where it breaks down),
  related or easily confused items, short examples (ideally minimal pairs), common mistakes,
  and a question to check understanding.
- Analogies draw on languages the learner knows, from their saved preferences, otherwise
  English.
- Looks words up in JMdict before explaining their meaning.

## Flashcard agent

[flashcards.py](../src/jplearn/agents/flashcards.py). Drafts Anki cards; it cannot add them.

1. Breaks the text down with the Analyzer.
2. Picks words and grammar worth studying, skipping particles, names and very basic words.
3. Checks Anki for existing cards with one `findNotes` search and lists those in `skipped`.
4. Returns a `CardDraft` (deck plus cards). The deck defaults to `JPLEARN_DECK`.

The orchestrator then calls `add_flashcards` with the draft, which waits for the user's
approval. The module also holds the Anki write helpers that tool uses:

- `add_cards()` adds the cards as *Basic* notes (Front/Back fields). Anki skips duplicates.
- `add_examples()` appends example sentences to the user's existing card for a word in any
  deck, skipping sentences already on it, or creates the card if there is none.

## Example sentences

[examples.py](../src/jplearn/agents/examples.py). Writes example sentences for one or more
words, at the learner's level (default N5–N4).

- Covers different meanings first, then different forms (polite/plain, past, negative,
  te-form).
- **Output check:** `check_examples` tokenizes every sentence and rejects any that don't
  contain the target word in some conjugation (`uses_word()`). The model gets up to 2 retries
  to fix them. This only works for words, not grammar patterns like 〜てしまう; those are
  better sent to the Explainer.

## Researcher

[researcher.py](../src/jplearn/agents/researcher.py). Finds Japanese reading material on the
web and returns one passage (at most ~600 characters) with its URL, level and summary.

- At most 3 searches and 3 page fetches per request. Search returns 5 results; pages are cut
  to 8,000 characters with a 20-second timeout.
- Network errors are returned to the model as text, so one failed fetch doesn't end the run.
- Returns at most 4 lines of song lyrics, for copyright reasons.

## Adding an agent

1. Create `agents/<name>.py`: an output model, `INSTRUCTIONS`, and
   `Agent(get_model(), output_type=..., instructions=INSTRUCTIONS, capabilities=[Observe("<id>")])`.
   Then call `use_user_context(agent, "<id>")` so it gets the learner's saved preferences.
   [explainer.py](../src/jplearn/agents/explainer.py) is a small example to copy.
2. Give the orchestrator a tool that runs it, passing `usage=ctx.usage`:

   ```python
   @orchestrator.tool
   async def my_tool(ctx: RunContext, request: str) -> MyOutput:
       """What it does and when to use it. The model reads this."""
       result = await my_agent.run(request, usage=ctx.usage)
       return result.output
   ```

3. Describe the tool in the orchestrator's `INSTRUCTIONS`: what it does and when to use it.
4. In [architecture.py](../src/jplearn/architecture.py), add a `Node("<id>", ...)` whose
   `calls` use the same tool names as the code, add it to the orchestrator's `calls`, and
   add the `(node, agent)` pair to `check_against_agents()`. The Agents panel and the
   Preferences dropdown pick it up from there.
5. Run `python scripts/healthcheck.py`. It fails if the diagram and the agents' tools
   disagree.

To change an existing agent's behaviour, edit its `INSTRUCTIONS` or the `Field`
descriptions on its output model; the model reads both.
